from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from .models import Category, Product, ProductVariant


class IPadMigrationTests(TestCase):
    def apply(self):
        import_module('catalog.migrations.0006_add_ipads').add_ipads(apps, SimpleNamespace(connection=connection))

    def test_existing_catalog_gets_two_ipads_without_images_and_repeat_is_safe(self):
        category = Category.objects.create(name='Other', slug='other')
        other = Product.objects.create(category=category, name='Keep', slug='keep')
        self.apply()
        self.apply()
        self.assertEqual(Product.objects.count(), 3)
        self.assertEqual(ProductVariant.objects.count(), 4)
        for product in Product.objects.filter(category__slug='ipad'):
            self.assertFalse(product.image)
            self.assertFalse(product.image_url)
            self.assertTrue(product.release_date)
            self.assertTrue(product.specifications)
            self.assertEqual(product.variants.count(), 2)
        other.refresh_from_db()
        self.assertEqual(other.name, 'Keep')

    def test_existing_admin_values_and_variants_are_preserved(self):
        category = Category.objects.create(name='Custom', slug='ipad')
        existing = Product.objects.create(category=category, name='Custom Air', slug='ipad-air-11-m4', discount_percent=7)
        variant = ProductVariant.objects.create(product=existing, color='Custom', memory='Custom', price='1', stock=9)
        self.apply()
        existing.refresh_from_db()
        variant.refresh_from_db()
        self.assertEqual(existing.name, 'Custom Air')
        self.assertEqual(existing.discount_percent, 7)
        self.assertEqual(existing.variants.count(), 1)
        self.assertEqual(variant.stock, 9)
        category.refresh_from_db()
        self.assertEqual(category.name, 'Custom')

    def test_empty_installation_is_not_seeded(self):
        self.apply()
        self.assertFalse(Product.objects.exists())
