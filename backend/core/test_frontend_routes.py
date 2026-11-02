from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings

from catalog.models import Category, Product


class StorefrontRouteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name='Phone', slug='phone')
        Product.objects.create(name='Visible', slug='visible', category=category, description='Phone')
        Product.objects.create(name='Hidden', slug='hidden', category=category, description='Phone', is_active=False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.index = Path(temporary.name) / 'index.html'
        self.index.write_text('<!doctype html><div id="root">storefront</div>', encoding='utf-8')
        setting = override_settings(FRONTEND_INDEX_PATH=self.index)
        setting.enable()
        self.addCleanup(setting.disable)

    def test_known_pages_and_product_deliver_shell_for_get_and_head(self):
        for path in ['/', '/catalog?category=phone', '/cart', '/checkout', '/favorites',
                     '/discounts', '/privacy', '/consent', '/products/visible']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="root"')
                self.assertEqual(response['Cache-Control'], 'no-cache')
                self.assertEqual(self.client.head(path).status_code, 200)

    def test_unknown_and_unpublished_product_return_shell_with_real_404(self):
        for path in ['/missing', '/products/missing', '/products/hidden', '/products/visible/extra']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, 'id="root"', status_code=404)

    def test_reserved_and_hidden_paths_never_deliver_shell(self):
        for path in ['/api/missing/', '/static/missing.js', '/assets/missing.js',
                     '/media/missing.jpg', '/.git/config', '/nested/.env', '/cgi-bin/test']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(b'id="root"', response.content)
        self.assertEqual(self.client.get('/api/missing/').json(), {'detail': 'Not found.'})
        self.assertNotIn(b'id="root"', self.client.get('/admin/missing/').content)

    def test_frontend_canonical_redirect_preserves_query_and_api_slash_handling(self):
        response = self.client.get('/catalog/?category=phone')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/catalog?category=phone')
        self.assertEqual(self.client.get('/products/visible/')['Location'], '/products/visible')
        self.assertEqual(self.client.get('/api/health/').status_code, 200)
        self.assertEqual(self.client.get('/api/health')['Location'], '/api/health/')
        self.assertEqual(self.client.get('/admin')['Location'], '/admin/')

    def test_unsafe_methods_are_not_accepted_as_pages(self):
        self.assertEqual(self.client.post('/catalog').status_code, 405)

    def test_order_tracking_page_is_private_shell_and_validates_path(self):
        path = '/orders/550e8400-e29b-41d4-a716-446655440000'
        response = self.client.get(path)
        self.assertContains(response, 'id="root"')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')
        self.assertEqual(self.client.get(path + '/')['Location'], path)
        self.assertEqual(self.client.get('/orders/123').status_code, 404)

    def test_missing_build_is_service_unavailable(self):
        self.index.unlink()
        self.assertEqual(self.client.get('/catalog').status_code, 503)
