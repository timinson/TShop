from io import StringIO

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Category, Product, ProductVariant


class CatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='iPhone', slug='iphone')
        cls.product = Product.objects.create(category=cls.category, name='iPhone 16', slug='iphone-16', description='Phone')
        ProductVariant.objects.create(product=cls.product, color='Белый', memory='128 ГБ', price='100.00', stock=0)
        ProductVariant.objects.create(product=cls.product, color='Чёрный', memory='256 ГБ', price='200.00', stock=2)
        cls.hidden = Product.objects.create(category=cls.category, name='Hidden', slug='hidden', is_active=False)

    def test_list_contract_and_detail(self):
        response = self.client.get('/api/products/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['min_price'], '100.00')
        self.assertTrue(data['results'][0]['in_stock'])
        self.assertEqual(len(data['results'][0]['variants']), 2)
        self.assertEqual(data['results'][0]['specifications'], {})
        self.assertEqual(self.client.get('/api/products/iphone-16/').json(), data['results'][0])
        self.assertEqual(self.client.post('/api/products/', {}).status_code, 405)

    def test_hidden_detail_is_not_public(self):
        self.assertEqual(self.client.get('/api/products/hidden/').status_code, 404)

    def test_availability_includes_last_item_and_reacts_to_zero_stock(self):
        ProductVariant.objects.filter(product=self.product).update(stock=0)
        self.assertFalse(self.client.get('/api/products/iphone-16/').json()['in_stock'])
        self.assertEqual(self.client.get('/api/products/?in_stock=true').json()['count'], 0)
        variant = self.product.variants.first()
        variant.stock = 1
        variant.save(update_fields=['stock'])
        self.assertTrue(self.client.get('/api/products/').json()['results'][0]['in_stock'])
        self.assertEqual(self.client.get('/api/products/?in_stock=true').json()['count'], 1)

    def test_sorting_by_price_and_model(self):
        cheaper = Product.objects.create(category=self.category, name='A Phone', slug='a-phone')
        ProductVariant.objects.create(product=cheaper, color='Black', price='50', stock=1)
        for ordering, expected in [('price', [cheaper.pk, self.product.pk]), ('-price', [self.product.pk, cheaper.pk]), ('name', [cheaper.pk, self.product.pk]), ('-name', [self.product.pk, cheaper.pk])]:
            with self.subTest(ordering=ordering):
                data = self.client.get('/api/products/', {'ordering': ordering}).json()
                self.assertEqual([item['id'] for item in data['results']], expected)
        self.assertEqual(self.client.get('/api/products/?ordering=invalid').status_code, 400)

    def test_sorting_happens_before_pagination_and_null_prices_are_last(self):
        Product.objects.create(category=self.category, name='No price', slug='no-price')
        for number in range(13):
            product = Product.objects.create(category=self.category, name=f'Phone {number}', slug=f'sorted-{number}')
            ProductVariant.objects.create(product=product, color='Black', price=200 - number, stock=1)
        first = self.client.get('/api/products/?ordering=-price').json()
        second = self.client.get('/api/products/?ordering=-price&page=2').json()
        self.assertEqual(first['results'][0]['min_price'], '200.00')
        self.assertIsNone(second['results'][-1]['min_price'])
        self.assertEqual(len(first['results']), 12)

    def test_price_and_stock_apply_to_same_variant(self):
        self.assertEqual(self.client.get('/api/products/?max_price=150&in_stock=true').json()['count'], 0)
        self.assertEqual(self.client.get('/api/products/?min_price=150&in_stock=true').json()['count'], 1)
        self.assertEqual(self.client.get('/api/products/?min_price=120&max_price=180').json()['count'], 0)

    def test_color_memory_price_stock_require_one_matching_variant(self):
        queries = [
            ({'color': 'Белый', 'memory': '256 ГБ'}, 0),
            ({'color': 'Белый', 'in_stock': 'true'}, 0),
            ({'memory': '128 ГБ', 'min_price': 150}, 0),
            ({'color': 'Чёрный', 'max_price': 150}, 0),
            ({'color': 'Чёрный', 'memory': '256 ГБ', 'in_stock': 'true', 'min_price': 150}, 1),
            ({'color': 'Белый', 'memory': '128 ГБ', 'max_price': 150}, 1),
        ]
        for params, count in queries:
            with self.subTest(params=params):
                response = self.client.get('/api/products/', params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['count'], count)

    def test_catalog_options_include_only_published_products_and_selected_category(self):
        ProductVariant.objects.create(product=self.hidden, color='Hidden color', memory='Hidden memory', price=1)
        other_category = Category.objects.create(name='MacBook', slug='macbook')
        other = Product.objects.create(category=other_category, name='Mac', slug='mac')
        ProductVariant.objects.create(product=other, color='Серый', memory='', price=1)
        ProductVariant.objects.create(product=other, color='Серый', memory='512 ГБ', price=2)
        self.assertEqual(self.client.get('/api/catalog-options/', {'category': 'iphone'}).json(), {
            'colors': ['Белый', 'Чёрный'], 'memories': ['128 ГБ', '256 ГБ'],
        })
        self.assertEqual(self.client.get('/api/catalog-options/').json(), {
            'colors': ['Белый', 'Серый', 'Чёрный'], 'memories': ['128 ГБ', '256 ГБ', '512 ГБ'],
        })
        self.assertEqual(self.client.get('/api/catalog-options/', {'category': 'missing'}).json(), {
            'colors': [], 'memories': [],
        })

    def test_search_category_and_availability(self):
        self.assertEqual(self.client.get('/api/products/?q=IPHONE&category=iphone').json()['count'], 1)
        self.assertEqual(self.client.get('/api/products/?category=macbook').json()['count'], 0)
        ProductVariant.objects.filter(product=self.product).update(stock=0)
        self.assertEqual(self.client.get('/api/products/?in_stock=true').json()['count'], 0)

    def test_invalid_parameters(self):
        for query in ['min_price=oops', 'max_price=NaN', 'max_price=Infinity', 'min_price=-1', 'min_price=20&max_price=10', 'in_stock=yes']:
            with self.subTest(query=query):
                self.assertEqual(self.client.get('/api/products/?' + query).status_code, 400)

    def test_pagination(self):
        for number in range(13):
            Product.objects.create(category=self.category, name=f'Phone {number}', slug=f'phone-{number}')
        data = self.client.get('/api/products/').json()
        self.assertEqual(data['count'], 14)
        self.assertEqual(len(data['results']), 12)
        self.assertIsNotNone(data['next'])
        self.assertEqual(len(self.client.get('/api/products/?page=2').json()['results']), 2)

    def test_categories_are_plain_array(self):
        self.assertEqual(self.client.get('/api/categories/').json(), [{'id': self.category.id, 'name': 'iPhone', 'slug': 'iphone'}])

    def test_database_constraints(self):
        for values in [dict(color='Белый', memory='128 ГБ', price='20.00', stock=1), dict(color='Other', price='0.00', stock=1), dict(color='Other', price='20.00', stock=-1)]:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                ProductVariant.objects.create(product=self.product, **values)


class SeedCatalogTests(TestCase):
    def test_command_is_idempotent_and_preserves_edits(self):
        call_command('seed_catalog', stdout=StringIO())
        self.assertEqual(Category.objects.count(), 4)
        self.assertEqual(Product.objects.count(), 19)
        self.assertFalse(Product.objects.filter(specifications={}).exists())
        product = Product.objects.first()
        product.specifications = {'Особенность': 'Заполнено менеджером'}
        product.save()
        original_count = ProductVariant.objects.count()
        variant = ProductVariant.objects.first()
        variant.price = '1.00'
        variant.save()
        call_command('seed_catalog', stdout=StringIO())
        self.assertEqual(Product.objects.count(), 19)
        product.refresh_from_db()
        self.assertEqual(product.specifications, {'Особенность': 'Заполнено менеджером'})
        self.assertEqual(ProductVariant.objects.count(), original_count)
        variant.refresh_from_db()
        self.assertEqual(str(variant.price), '1.00')

    def test_specifications_are_text_mapping(self):
        category = Category.objects.create(name='Test', slug='test')
        product = Product(category=category, name='Test', slug='test')
        for value in [[], {'Экран': 6.3}, {'': 'Значение'}, {'Экран': ''}]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                product.specifications = value
                product.full_clean()
