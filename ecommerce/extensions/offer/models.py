# noinspection PyUnresolvedReferences
from django.db import models
from jsonfield.fields import JSONField
from oscar.apps.offer.abstract_models import AbstractRange


class Range(AbstractRange):
    catalog = models.ForeignKey('catalogue.Catalog', blank=True, null=True, related_name='ranges')
    catalog_query = models.CharField(max_length=255, blank=True, null=True)
    course_seat_types = JSONField(null=True)

    def contains_product(self, product):
        # TODO: Add logic to call course_discovery to check the course_run against the query string
        if self.course_seat_types:
            return (product.attr.certificate_type.lower() in
                    [seat.lower() for seat in self.course_seat_types] or  # pylint: disable=not-an-iterable
                    super(Range, self).contains_product(product))  # pylint: disable=bad-super-call
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
        if self.catalog:
            catalog_products = [record.product for record in self.catalog.stock_records.all()]
            return catalog_products + list(super(Range, self).all_products())  # pylint: disable=bad-super-call
        return super(Range, self).all_products()  # pylint: disable=bad-super-call

from oscar.apps.offer.models import *  # noqa pylint: disable=wildcard-import,unused-wildcard-import,wrong-import-position
