# noinspection PyUnresolvedReferences
import logging

from django.db import models
from jsonfield.fields import JSONField
from oscar.apps.offer.abstract_models import AbstractRange

from core.url_utils import get_course_discovery_client

logger = logging.getLogger(__name__)


class Range(AbstractRange):
    catalog = models.ForeignKey('catalogue.Catalog', blank=True, null=True, related_name='ranges')
    catalog_query = models.CharField(max_length=255, blank=True, null=True)
    course_seat_types = JSONField(null=True)

    def contains_product(self, product):
        if self.catalog_query:
            try:
                response = get_course_discovery_client().\
                           api.v1.course_runs.contains.get(query=self.catalog_query,
                                                           course_ids=product.course_id,
                                                           seat_types=",".join(self.course_seat_types))
                if (product.attr.certificate_type.lower() in [seat.lower() for seat in self.course_seat_types]):
                    return ((response[product.course_id][product.attr.certificate_type.lower()]) or
                            super(Range, self).contains_product(product))  # pylint: disable=bad-super-call
            except:
                logger.error('ERROR: Could not contact Course Discovery Service')
                return False
        elif self.catalog:
            return (
                product.id in self.catalog.stock_records.values_list('product', flat=True) or
                super(Range, self).contains_product(product)  # pylint: disable=bad-super-call
            )
        return super(Range, self).contains_product(product)  # pylint: disable=bad-super-call

    contains = contains_product

    def num_products(self):
        return len(self.all_products())

    def all_products(self):
        # TODO:  Get all course runs for query and seat type.
        if self.catalog:
            catalog_products = [record.product for record in self.catalog.stock_records.all()]
            return catalog_products + list(super(Range, self).all_products())  # pylint: disable=bad-super-call
        return super(Range, self).all_products()  # pylint: disable=bad-super-call

from oscar.apps.offer.models import *  # noqa pylint: disable=wildcard-import,unused-wildcard-import,wrong-import-position
