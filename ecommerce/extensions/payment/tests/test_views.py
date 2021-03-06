""" Tests of the Payment Views. """
import ddt
from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from factory.django import mute_signals

import mock
from oscar.apps.order.exceptions import UnableToPlaceOrder
from oscar.apps.payment.exceptions import PaymentError, UserCancelled, TransactionDeclined, GatewayError
from oscar.core.loading import get_class, get_model
from oscar.test import factories
from oscar.test.contextmanagers import mock_signal_receiver

from testfixtures import LogCapture
from ecommerce.extensions.order.constants import PaymentEventTypeName

from ecommerce.extensions.fulfillment.status import ORDER
from ecommerce.extensions.payment.processors.cybersource import Cybersource
from ecommerce.extensions.payment.processors.paypal import Paypal
from ecommerce.extensions.payment.processors.stripe import StripeProcessor
from ecommerce.extensions.payment.tests.mixins import PaymentEventsMixin, CybersourceMixin, PaypalMixin
from ecommerce.extensions.payment.views import CybersourceNotifyView, PaypalPaymentExecutionView, StripeCheckoutView
from ecommerce.core.tests.patched_httpretty import httpretty
from ecommerce.tests.testcases import TestCase

Basket = get_model('basket', 'Basket')
Order = get_model('order', 'Order')
PaymentEvent = get_model('order', 'PaymentEvent')
PaymentEventType = get_model('order', 'PaymentEventType')
PaymentProcessorResponse = get_model('payment', 'PaymentProcessorResponse')
Source = get_model('payment', 'Source')
SourceType = get_model('payment', 'SourceType')

post_checkout = get_class('checkout.signals', 'post_checkout')


@ddt.ddt
class CybersourceNotifyViewTests(CybersourceMixin, PaymentEventsMixin, TestCase):
    """ Test processing of CyberSource notifications. """

    def setUp(self):
        super(CybersourceNotifyViewTests, self).setUp()

        self.user = factories.UserFactory()
        self.billing_address = self.make_billing_address()

        self.basket = factories.create_basket()
        self.basket.owner = self.user
        self.basket.freeze()

        self.processor = Cybersource()
        self.processor_name = self.processor.NAME

    def _assert_payment_data_recorded(self, notification):
        """ Ensure PaymentEvent, PaymentProcessorResponse, and Source objects are created for the basket. """

        # Ensure the response is stored in the database
        self.assert_processor_response_recorded(self.processor_name, notification[u'transaction_id'], notification,
                                                basket=self.basket)

        # Validate a payment Source was created
        reference = notification[u'transaction_id']
        source_type = SourceType.objects.get(code=self.processor_name)
        label = notification[u'req_card_number']
        self.assert_payment_source_exists(self.basket, source_type, reference, label)

        # Validate that PaymentEvents exist
        paid_type = PaymentEventType.objects.get(code='paid')
        self.assert_payment_event_exists(self.basket, paid_type, reference, self.processor_name)

    def _assert_processing_failure(self, notification, status_code, error_message, log_level='ERROR'):
        """Verify that payment processing operations fail gracefully."""
        logger_name = 'ecommerce.extensions.payment.views'
        with LogCapture(logger_name) as l:
            response = self.client.post(reverse('cybersource_notify'), notification)

            self.assertEqual(response.status_code, status_code)

            self.assert_processor_response_recorded(
                self.processor_name,
                notification[u'transaction_id'],
                notification,
                basket=self.basket
            )

            l.check(
                (
                    logger_name,
                    'INFO',
                    'Received CyberSource merchant notification for transaction [{transaction_id}], '
                    'associated with basket [{basket_id}].'.format(
                        transaction_id=notification[u'transaction_id'],
                        basket_id=self.basket.id
                    )
                ),
                (logger_name, log_level, error_message)
            )

    # Disable the normal signal receivers so that we can verify the state of the created order.
    @mute_signals(post_checkout)
    def test_accepted(self):
        """
        When payment is accepted, the following should occur:
            1. The response is recorded and PaymentEvent/Source objects created.
            2. An order for the corresponding basket is created.
            3. The order is fulfilled.
        """

        # The basket should not have an associated order if no payment was made.
        self.assertFalse(Order.objects.filter(basket=self.basket).exists())

        notification = self.generate_notification(
            self.processor.secret_key,
            self.basket,
            billing_address=self.billing_address,
        )

        with mock_signal_receiver(post_checkout) as receiver:
            response = self.client.post(reverse('cybersource_notify'), notification)

            # Validate that a new order exists in the correct state
            order = Order.objects.get(basket=self.basket)
            self.assertIsNotNone(order, 'No order was created for the basket after payment.')
            self.assertEqual(order.status, ORDER.OPEN)

            # Validate the order's line items
            self.assertListEqual(list(order.lines.values_list('product__id', flat=True)),
                                 list(self.basket.lines.values_list('product__id', flat=True)))

            # Verify the post_checkout signal was emitted
            self.assertEqual(receiver.call_count, 1)
            __, kwargs = receiver.call_args
            self.assertEqual(kwargs['order'], order)

        # The view should always return 200
        self.assertEqual(response.status_code, 200)

        # Validate the payment data was recorded for auditing
        self._assert_payment_data_recorded(notification)

        # The basket should be marked as submitted. Refresh with data from the database.
        basket = Basket.objects.get(id=self.basket.id)
        self.assertTrue(basket.is_submitted)
        self.assertIsNotNone(basket.date_submitted)

    @ddt.data('CANCEL', 'DECLINE', 'ERROR', 'blah!')
    def test_not_accepted(self, decision):
        """
        When payment is NOT accepted, the processor's response should be saved to the database. An order should NOT
        be created.
        """

        notification = self.generate_notification(self.processor.secret_key, self.basket, decision=decision)
        response = self.client.post(reverse('cybersource_notify'), notification)

        # The view should always return 200
        self.assertEqual(response.status_code, 200)

        # The basket should not have an associated order if no payment was made.
        self.assertFalse(Order.objects.filter(basket=self.basket).exists())

        # Ensure the response is stored in the database
        self.assert_processor_response_recorded(self.processor_name, notification[u'transaction_id'], notification,
                                                basket=self.basket)

    @ddt.data(
        (PaymentError, 200, 'ERROR', 'CyberSource payment failed for basket [{basket_id}]. '
                                     'The payment response was recorded in entry [{response_id}].'),
        (UserCancelled, 200, 'INFO', 'CyberSource payment did not complete for basket [{basket_id}] because '
                                     '[UserCancelled]. The payment response was recorded in entry [{response_id}].'),
        (TransactionDeclined, 200, 'INFO', 'CyberSource payment did not complete for basket [{basket_id}] because '
                                           '[TransactionDeclined]. The payment response was recorded in entry '
                                           '[{response_id}].'),
        (KeyError, 500, 'ERROR', 'Attempts to handle payment for basket [{basket_id}] failed.')
    )
    @ddt.unpack
    def test_payment_handling_error(self, error_class, status_code, log_level, error_message):
        """
        Verify that CyberSource's merchant notification is saved to the database despite an error handling payment.
        """
        notification = self.generate_notification(
            self.processor.secret_key,
            self.basket,
            billing_address=self.billing_address,
        )
        with mock.patch.object(
            CybersourceNotifyView,
            'handle_payment',
            side_effect=error_class
        ) as fake_handle_payment:
            self._assert_processing_failure(
                notification,
                status_code,
                error_message.format(basket_id=self.basket.id, response_id=1),
                log_level
            )
            self.assertTrue(fake_handle_payment.called)

    def test_unable_to_place_order(self):
        """ When payment is accepted, but an order cannot be placed, log an error and return HTTP 200. """

        notification = self.generate_notification(
            self.processor.secret_key,
            self.basket,
            billing_address=self.billing_address,
        )

        # Verify that anticipated errors are handled gracefully.
        with mock.patch.object(CybersourceNotifyView, 'handle_order_placement',
                               side_effect=UnableToPlaceOrder) as fake_handle_order_placement:
            error_message = 'Payment was received, but an order for basket [{basket_id}] could not be placed.'.format(
                basket_id=self.basket.id,
            )
            self._assert_processing_failure(notification, 500, error_message)
            self.assertTrue(fake_handle_order_placement.called)

        # Verify that unanticipated errors are also handled gracefully.
        with mock.patch.object(CybersourceNotifyView, 'handle_order_placement',
                               side_effect=KeyError) as fake_handle_order_placement:
            error_message = 'Payment was received, but an order for basket [{basket_id}] could not be placed.'.format(
                basket_id=self.basket.id,
            )
            self._assert_processing_failure(notification, 500, error_message)
            self.assertTrue(fake_handle_order_placement.called)

    def test_invalid_basket(self):
        """ When payment is accepted for a non-existent basket, log an error and record the response. """
        order_number = '{}-{}'.format(self.partner.short_code.upper(), 101986)

        notification = self.generate_notification(
            self.processor.secret_key,
            self.basket,
            billing_address=self.billing_address,
            req_reference_number=order_number,
        )
        response = self.client.post(reverse('cybersource_notify'), notification)

        self.assertEqual(response.status_code, 400)
        self.assert_processor_response_recorded(self.processor_name, notification[u'transaction_id'], notification)

    @ddt.data(('line2', 'foo'), ('state', 'bar'))
    @ddt.unpack
    @mock.patch('ecommerce.extensions.payment.views.CybersourceNotifyView.handle_order_placement')
    def test_optional_fields(self, field_name, field_value, mock_placement_handler):
        """ Ensure notifications are handled properly with or without keys/values present for optional fields. """

        def check_notification_address(notification, expected_address):
            response = self.client.post(reverse('cybersource_notify'), notification)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(mock_placement_handler.called)
            actual_address = mock_placement_handler.call_args[0][6]
            self.assertEqual(actual_address.summary, expected_address.summary)

        cybersource_key = 'req_bill_to_address_{}'.format(field_name)

        # Generate a notification without the optional field set.
        # Ensure that the Cybersource key does not exist in the notification,
        # and that the address our endpoint parses from the notification is
        # equivalent to the original.
        notification = self.generate_notification(
            self.processor.secret_key,
            self.basket,
            billing_address=self.billing_address,
        )
        self.assertNotIn(cybersource_key, notification)
        check_notification_address(notification, self.billing_address)

        # Add the optional field to the billing address in the notification.
        # Ensure that the Cybersource key now does exist, and that our endpoint
        # recognizes and parses it correctly.
        billing_address = self.make_billing_address({field_name: field_value})
        notification = self.generate_notification(
            self.processor.secret_key,
            self.basket,
            billing_address=billing_address,
        )
        self.assertIn(cybersource_key, notification)
        check_notification_address(notification, billing_address)

    def test_invalid_signature(self):
        """
        If the response signature is invalid, the view should return a 400. The response should be recorded, but an
        order should NOT be created.
        """
        notification = self.generate_notification(self.processor.secret_key, self.basket)
        notification[u'signature'] = u'Tampered'
        response = self.client.post(reverse('cybersource_notify'), notification)

        # The view should always return 200
        self.assertEqual(response.status_code, 400)

        # The basket should not have an associated order
        self.assertFalse(Order.objects.filter(basket=self.basket).exists())

        # The response should be saved.
        self.assert_processor_response_recorded(self.processor_name, notification[u'transaction_id'], notification,
                                                basket=self.basket)


@ddt.ddt
class PaypalPaymentExecutionViewTests(PaypalMixin, PaymentEventsMixin, TestCase):
    """Test handling of users redirected by PayPal after approving payment."""

    def setUp(self):
        super(PaypalPaymentExecutionViewTests, self).setUp()

        self.basket = factories.create_basket()
        self.basket.owner = factories.UserFactory()
        self.basket.freeze()

        self.processor = Paypal()
        self.processor_name = self.processor.NAME

        # Dummy request from which an HTTP Host header can be extracted during
        # construction of absolute URLs
        self.request = RequestFactory().post('/')

    @httpretty.activate
    def _assert_execution_redirect(self, payer_info=None, url_redirect=None):
        """Verify redirection to the configured receipt page after attempted payment execution."""
        self.mock_oauth2_response()

        # Create a payment record the view can use to retrieve a basket
        self.mock_payment_creation_response(self.basket)
        self.processor.get_transaction_parameters(self.basket, request=self.request)

        creation_response = self.mock_payment_creation_response(self.basket, find=True)
        execution_response = self.mock_payment_execution_response(self.basket, payer_info=payer_info)

        response = self.client.get(reverse('paypal_execute'), self.RETURN_DATA)
        self.assertRedirects(
            response,
            url_redirect or u'{}?orderNum={}'.format(self.processor.receipt_url, self.basket.order_number),
            fetch_redirect_response=False
        )

        return creation_response, execution_response

    def _assert_order_placement_failure(self, error_message):
        """Verify that order placement fails gracefully."""
        logger_name = 'ecommerce.extensions.payment.views'
        with LogCapture(logger_name) as l:
            __, execution_response = self._assert_execution_redirect()

            # Verify that the payment execution response was recorded despite the error
            self.assert_processor_response_recorded(
                self.processor_name,
                self.PAYMENT_ID,
                execution_response,
                basket=self.basket
            )

            l.check(
                (
                    logger_name,
                    'INFO',
                    'Payment [{payment_id}] approved by payer [{payer_id}]'.format(
                        payment_id=self.PAYMENT_ID,
                        payer_id=self.PAYER_ID
                    )
                ),
                (logger_name, 'ERROR', error_message)
            )

    @ddt.data(
        None,  # falls back to PaypalMixin.PAYER_INFO, a fully-populated payer_info object
        {"shipping_address": None},  # minimal data, which may be sent in some Paypal execution responses
    )
    def test_payment_execution(self, payer_info):
        """Verify that a user who has approved payment is redirected to the configured receipt page."""
        self._assert_execution_redirect(payer_info=payer_info)
        # even if an exception occurs during handling of the payment notification, we still redirect the
        # user to the receipt page.  Therefore in addition to checking that the response had the correct
        # redirection, we also need to check that the order was actually created.
        self.get_order(self.basket)

    def test_payment_error(self):
        """
        Verify that a user who has approved payment is redirected to the configured receipt page when payment
        execution fails.
        """
        with mock.patch.object(PaypalPaymentExecutionView, 'handle_payment',
                               side_effect=PaymentError) as fake_handle_payment:
            logger_name = 'ecommerce.extensions.payment.views'
            with LogCapture(logger_name) as l:
                creation_response, __ = self._assert_execution_redirect(url_redirect=self.processor.error_url)
                self.assertTrue(fake_handle_payment.called)

                # Verify that the payment creation response was recorded despite the error
                self.assert_processor_response_recorded(
                    self.processor_name,
                    self.PAYMENT_ID,
                    creation_response,
                    basket=self.basket
                )

                l.check(
                    (
                        logger_name,
                        'INFO',
                        'Payment [{payment_id}] approved by payer [{payer_id}]'.format(
                            payment_id=self.PAYMENT_ID,
                            payer_id=self.PAYER_ID
                        )
                    ),
                )

    def test_unanticipated_error_during_payment_handling(self):
        """
        Verify that a user who has approved payment is redirected to the configured receipt page when payment
        execution fails in an unanticipated manner.
        """
        with mock.patch.object(PaypalPaymentExecutionView, 'handle_payment',
                               side_effect=KeyError) as fake_handle_payment:
            logger_name = 'ecommerce.extensions.payment.views'
            with LogCapture(logger_name) as l:
                creation_response, __ = self._assert_execution_redirect()
                self.assertTrue(fake_handle_payment.called)

                # Verify that the payment creation response was recorded despite the error
                self.assert_processor_response_recorded(
                    self.processor_name,
                    self.PAYMENT_ID,
                    creation_response,
                    basket=self.basket
                )

                l.check(
                    (
                        logger_name,
                        'INFO',
                        'Payment [{payment_id}] approved by payer [{payer_id}]'.format(
                            payment_id=self.PAYMENT_ID,
                            payer_id=self.PAYER_ID
                        )
                    ),
                    (
                        logger_name,
                        'ERROR',
                        'Attempts to handle payment for basket [{basket_id}] failed.'.format(basket_id=self.basket.id)
                    ),
                )

    def test_unable_to_place_order(self):
        """
        Verify that a user who has approved payment is redirected to the configured receipt page when the payment
        is executed but an order cannot be placed.
        """
        with mock.patch.object(PaypalPaymentExecutionView, 'handle_order_placement',
                               side_effect=UnableToPlaceOrder) as fake_handle_order_placement:
            error_message = 'Payment was received, but an order for basket [{basket_id}] could not be placed.'.format(
                basket_id=self.basket.id,
            )
            self._assert_order_placement_failure(error_message)
            self.assertTrue(fake_handle_order_placement.called)

    def test_unanticipated_error_during_order_placement(self):
        """Verify that unanticipated errors during order placement are handled gracefully."""
        with mock.patch.object(PaypalPaymentExecutionView, 'handle_order_placement',
                               side_effect=KeyError) as fake_handle_order_placement:
            error_message = 'Payment was received, but an order for basket [{basket_id}] could not be placed.'.format(
                basket_id=self.basket.id,
            )
            self._assert_order_placement_failure(error_message)
            self.assertTrue(fake_handle_order_placement.called)

    @httpretty.activate
    def test_payment_error_with_duplicate_payment_id(self):
        """
        Verify that we fail gracefully when PayPal sends us the wrong payment ID,
        logging the exception and redirecting the user to an LMS checkout error page.
        """
        logger_name = 'ecommerce.extensions.payment.views'
        with LogCapture(logger_name) as l:
            self.mock_oauth2_response()

            # Create payment records with different baskets which will have same payment ID
            self.mock_payment_creation_response(self.basket)
            self.processor.get_transaction_parameters(self.basket, request=self.request)

            dummy_basket = factories.create_basket()
            self.mock_payment_creation_response(dummy_basket)
            self.processor.get_transaction_parameters(dummy_basket, request=self.request)

            self._assert_error_page_redirect()
            l.check(
                (
                    logger_name,
                    'INFO',
                    'Payment [{payment_id}] approved by payer [{payer_id}]'.format(
                        payment_id=self.PAYMENT_ID,
                        payer_id=self.PAYER_ID
                    )
                ),
                (
                    logger_name,
                    'ERROR',
                    'Duplicate payment ID [{payment_id}] received from PayPal.'.format(payment_id=self.PAYMENT_ID),
                ),
            )

    @httpretty.activate
    def test_payment_error_with_no_basket(self):
        """
        Verify that we fail gracefully when any Exception occurred in _get_basket() method,
        logging the exception and redirecting the user to an LMS checkout error page.
        """
        with mock.patch.object(PaymentProcessorResponse.objects, 'get', side_effect=Exception):
            logger_name = 'ecommerce.extensions.payment.views'
            with LogCapture(logger_name) as l:
                self.mock_oauth2_response()
                self.mock_payment_creation_response(self.basket)
                self.processor.get_transaction_parameters(self.basket, request=self.request)
                self._assert_error_page_redirect()

                l.check(
                    (
                        logger_name,
                        'INFO',
                        'Payment [{payment_id}] approved by payer [{payer_id}]'.format(
                            payment_id=self.PAYMENT_ID,
                            payer_id=self.PAYER_ID
                        )
                    ),
                    (
                        logger_name,
                        'ERROR',
                        'Unexpected error during basket retrieval while executing PayPal payment.'
                    ),
                )

    def _assert_error_page_redirect(self):
        """Verify redirection to the configured checkout error page after attempted failed payment execution."""
        response = self.client.get(reverse('paypal_execute'), self.RETURN_DATA)

        self.assertRedirects(
            response,
            self.processor.error_url,
            fetch_redirect_response=False
        )


@mock.patch('ecommerce.extensions.payment.views.call_command')
class PaypalProfileAdminViewTests(TestCase):
    path = reverse('paypal_profiles')

    def get_response(self, is_superuser, expected_status, data=None):
        user = self.create_user(is_superuser=is_superuser)
        self.client.login(username=user.username, password=self.password)
        response = self.client.get(self.path, data=data or {})
        self.assertEqual(response.status_code, expected_status)
        return response

    def test_superuser_required(self, mock_call_command):
        """ Verify the view is only accessible to superusers. """
        response = self.client.get(self.path)
        self.assertFalse(mock_call_command.called)
        self.assertEqual(response.status_code, 404)

        self.get_response(False, 404)
        self.assertFalse(mock_call_command.called)

    def test_valid_action_required(self, mock_call_command):
        self.get_response(True, 400)
        self.assertFalse(mock_call_command.called)

        self.get_response(True, 400, {"action": "invalid"})
        self.assertFalse(mock_call_command.called)

        self.get_response(True, 200, {"action": "list"})
        self.assertTrue(mock_call_command.called)

    def test_command_exception(self, mock_call_command):
        mock_call_command.side_effect = Exception("oof")
        self.get_response(True, 500, {"action": "list"})
        self.assertTrue(mock_call_command.called)


class StripeCheckoutTest(TestCase):
    def setUp(self):
        super(StripeCheckoutTest, self).setUp()

        self.basket = factories.create_basket()
        self.user = factories.UserFactory()
        self.user.set_password('password')
        self.user.save()
        self.basket.owner = self.user
        self.basket.freeze()

        self.stripe_cc_token = "tok_stripeMockToken"
        self.charge_id = "tx_stripeMockToken"

        self.processor = Paypal()
        self.processor_name = self.processor.NAME

        self.url = reverse("stripe_checkout", kwargs={"basket": self.basket.pk})

        source_type, __ = SourceType.objects.get_or_create(name='stripe')
        total = self.basket.total_incl_tax

        self.payment_source = Source(
            source_type=source_type,
            currency="usd",
            amount_allocated=total,
            amount_debited=total,
            reference=self.charge_id,
            label='Stripe',
            card_type=None
        )

        event_type, __ = PaymentEventType.objects.get_or_create(
            name=PaymentEventTypeName.PAID
        )

        self.payment_event = PaymentEvent(
            event_type=event_type,
            amount=total,
            reference=self.charge_id,
            processor_name='stripe'
        )

    def _login_user(self):
        self.assertTrue(self.client.login(
            username=self.user.username,
            password='password'
        ), "Couldn't login the client")

    def test_successful_payment(self):
        self._login_user()

        handle_payment_response = self.payment_source, self.payment_event
        with mock.patch.object(
            StripeProcessor, 'handle_processor_response', return_value=handle_payment_response
        ) as handle_payment:
            response = self.client.post(self.url, data={"stripeToken": self.stripe_cc_token})

        handle_payment.assert_called_once_with(self.stripe_cc_token, basket=self.basket)

        # Check if payment_source and payment_event got saved to the db
        self.assertTrue(self.payment_source.pk is not None)
        self.assertTrue(self.payment_event.pk is not None)

        self.assertTrue(response.status_code, 302)
        self.assertTrue(response['Location'], StripeProcessor().receipt_url)

    def test_invalid_basket_id(self):
        self._login_user()

        invalid_id = 9999
        self.assertNotEqual(self.basket.pk, invalid_id)

        self.url = reverse("stripe_checkout", kwargs={"basket": invalid_id})

        handle_payment_response = self.payment_source, self.payment_event
        with mock.patch.object(
            StripeProcessor, 'handle_processor_response', return_value=handle_payment_response
        ) as handle_payment:
            response = self.client.post(self.url, data={"stripeToken": self.stripe_cc_token})

        handle_payment.assert_not_called()

        self.assertTrue(self.payment_source.pk is None)
        self.assertTrue(self.payment_event.pk is None)

        self.assertTrue(response.status_code, 302)
        self.assertTrue(response['Location'], StripeProcessor().error_url)

    def test_not_logged_user(self):
        handle_payment_response = self.payment_source, self.payment_event
        with mock.patch.object(
            StripeProcessor, 'handle_processor_response', return_value=handle_payment_response
        ) as handle_payment:
            response = self.client.post(self.url, data={"stripeToken": self.stripe_cc_token})

        handle_payment.assert_not_called()

        self.assertTrue(self.payment_source.pk is None)
        self.assertTrue(self.payment_event.pk is None)

        self.assertTrue(response.status_code, 302)
        self.assertTrue(response['Location'], settings.LOGIN_URL)

    def test_payment_failed(self):
        self._login_user()

        with mock.patch.object(
            StripeProcessor, 'handle_processor_response', side_effect=GatewayError
        ):
            logger_name = 'ecommerce.extensions.payment.views'
            with LogCapture(logger_name) as log_capture:
                response = self.client.post(self.url, data={"stripeToken": self.stripe_cc_token})

        self.assertTrue(response.status_code, 302)
        self.assertTrue(response['Location'], StripeProcessor().error_url)
        log_capture.check(
            (
                logger_name,
                'INFO',
                'Payment error for basket [%d] failed.' % self.basket.id
            )
        )

    def test_payment_threw_an_exception(self):
        self._login_user()

        with mock.patch.object(
            StripeProcessor, 'handle_processor_response', side_effect=ValueError
        ):
            logger_name = 'ecommerce.extensions.payment.views'
            with LogCapture(logger_name) as log_capture:
                response = self.client.post(self.url, data={"stripeToken": self.stripe_cc_token})

        self.assertTrue(response.status_code, 302)
        self.assertTrue(response['Location'], StripeProcessor().error_url)

        log_capture.check(
            (
                logger_name,
                'ERROR',
                'Attempts to handle payment for basket [%d] failed.' % self.basket.id
            )
        )

    def test_order_placement_failure(self):
        self._login_user()
        handle_payment_response = self.payment_source, self.payment_event

        # Need to patch both phases of payment handling
        with mock.patch.object(
            StripeProcessor, 'handle_processor_response', return_value=handle_payment_response
        ), mock.patch.object(
            StripeCheckoutView, 'handle_order_placement', side_effect=UnableToPlaceOrder
        ):
            logger_name = 'ecommerce.extensions.payment.views'
            with LogCapture(logger_name) as log_capture:
                with self.assertRaises(UnableToPlaceOrder):
                    self.client.post(self.url, data={"stripeToken": self.stripe_cc_token})

        log_capture.check(
            (
                logger_name,
                'ERROR',
                'Payment was executed, but an order was not created for basket [%d].' % self.basket.id
            )
        )
