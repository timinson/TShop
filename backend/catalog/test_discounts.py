import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.models import Category, Product, ProductVariant
from orders.models import Order
from orders.privacy import PRIVACY_POLICY_VERSION


class DiscountTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Phones', slug='phones')
        self.product = Product.objects.create(category=self.category, name='Sale', slug='sale', discount_percent=25)
        self.variant = ProductVariant.objects.create(product=self.product, color='Black', price='100.50', stock=5)

    def test_catalog_prices_and_rounding_match_variant_filter(self):
        data = self.client.get('/api/products/sale/').json()
        self.assertEqual(data['min_price'], '75.38')
        self.assertEqual(data['min_original_price'], '100.50')
        self.assertEqual(data['discount_percent'], 25)
        self.assertEqual(data['variants'][0]['price'], '75.38')
        self.assertEqual(data['variants'][0]['original_price'], '100.50')
        self.assertEqual(self.client.get('/api/products/?min_price=75.38&max_price=75.38').json()['count'], 1)
        self.assertEqual(self.client.get('/api/products/?max_price=75.37').json()['count'], 0)

    def test_discount_filter_sorting_and_no_discount_contract(self):
        regular = Product.objects.create(category=self.category, name='Regular', slug='regular')
        ProductVariant.objects.create(product=regular, color='White', price='80', stock=1)
        result = self.client.get('/api/products/?ordering=price').json()['results']
        self.assertEqual([p['id'] for p in result], [self.product.pk, regular.pk])
        self.assertIsNone(result[1]['min_original_price'])
        self.assertIsNone(result[1]['variants'][0]['original_price'])
        self.assertEqual(self.client.get('/api/products/?discounted=true').json()['count'], 1)
        self.assertEqual(self.client.get('/api/products/?discounted=false').json()['results'][0]['id'], regular.pk)
        self.assertEqual(self.client.get('/api/products/?discounted=yes').status_code, 400)

    def test_cart_checkout_recalculate_discount_and_snapshot(self):
        self.client.post('/api/cart/', {'variant_id': self.variant.pk, 'quantity': 2}, content_type='application/json')
        self.assertEqual(self.client.get('/api/cart/').json()['total'], '150.76')
        self.product.discount_percent = 50
        self.product.save(update_fields=['discount_percent'])
        payload = {'name': 'Demo', 'checkout_token': str(uuid.uuid4()), 'privacy_consent': True, 'privacy_policy_version': PRIVACY_POLICY_VERSION}
        response = self.client.post('/api/orders/', payload, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal('100.50'))
        self.assertEqual(order.items.get().unit_price, Decimal('50.25'))
        self.product.discount_percent = 0
        self.product.save(update_fields=['discount_percent'])
        self.assertEqual(order.items.get().unit_price, Decimal('50.25'))

    def test_discount_limits_model_and_database(self):
        for value in [-1, 100]:
            self.product.discount_percent = value
            with self.assertRaises(ValidationError):
                self.product.full_clean()
            with self.assertRaises(IntegrityError), transaction.atomic():
                Product.objects.filter(pk=self.product.pk).update(discount_percent=value)

    def test_favorites_id_filter_validation(self):
        self.assertEqual(self.client.get('/api/products/', {'ids': str(self.product.pk)}).json()['count'], 1)
        self.assertEqual(self.client.get('/api/products/?ids=999999').json()['count'], 0)
        for value in ['', '0', '-1', 'x', ',1', '1,' , '1,' * 200 + '1']:
            with self.subTest(value=value):
                self.assertEqual(self.client.get('/api/products/', {'ids': value}).status_code, 400)
