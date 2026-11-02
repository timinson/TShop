from datetime import date
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from .models import Category, Product


class ReleaseDateTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='iPhone', slug='iphone')

    def product(self, name, release=None):
        return Product.objects.create(category=self.category, name=name,
            slug=f'phone-{Product.objects.count()}', release_date=release)

    def test_default_sort_latest_first_and_unknown_last(self):
        unknown = self.product('Unknown')
        older = self.product('Older', date(2024, 9, 20))
        newest = self.product('Newest', date(2026, 9, 18))
        same_date = self.product('Same date', date(2026, 9, 18))
        result = self.client.get('/api/products/').json()['results']
        self.assertEqual([row['id'] for row in result], [same_date.pk, newest.pk, older.pk, unknown.pk])

    def test_date_backfill_only_existing_known_names_without_overwriting(self):
        first = self.product('iPhone 16')
        changed = self.product('iPhone 17', date(2025, 9, 26))
        unknown = self.product('Custom product')
        count = Product.objects.count()
        migration = import_module('catalog.migrations.0005_product_release_date')
        migration.fill_release_dates(apps, SimpleNamespace(connection=connection))
        first.refresh_from_db()
        changed.refresh_from_db()
        unknown.refresh_from_db()
        self.assertEqual(first.release_date, date(2024, 9, 20))
        self.assertEqual(changed.release_date, date(2025, 9, 26))
        self.assertIsNone(unknown.release_date)
        self.assertEqual(Product.objects.count(), count)
