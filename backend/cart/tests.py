from django.test import TestCase

from catalog.models import Category, Product, ProductVariant
from .views import cart_data


class CartImageTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='iPhone', slug='iphone')
        self.product = Product.objects.create(category=category, name='Phone', slug='phone', image_url='https://example.com/phone.jpg')
        self.variant = ProductVariant.objects.create(product=self.product, color='Black', price='100', stock=2)

    def item(self):
        return cart_data({'cart': {str(self.variant.pk): 1}})['items'][0]

    def test_external_image_url_and_upload_priority(self):
        self.assertEqual(self.item()['image_url'], 'https://example.com/phone.jpg')
        self.product.image = 'products/phone.jpg'
        self.product.save()
        self.assertEqual(self.item()['image_url'], self.product.image.url)

    def test_missing_image_or_deleted_variant_has_empty_url(self):
        self.product.image_url = ''
        self.product.save()
        self.assertEqual(self.item()['image_url'], '')
        variant_id = self.variant.pk
        self.variant.delete()
        item = cart_data({'cart': {str(variant_id): 1}})['items'][0]
        self.assertEqual(item['image_url'], '')
        self.assertFalse(item['is_available'])
