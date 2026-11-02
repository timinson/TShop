import uuid
import time
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.cache import caches
from django.test import TestCase, override_settings

from orders.models import Order, OrderItem


@override_settings(CACHES={
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'tracking-protection-default'},
    'order_tracking': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                       'LOCATION': 'tracking-protection-tests'},
})
class TrackingProtectionTests(TestCase):
    def setUp(self):
        self.cache = caches['order_tracking']
        self.cache.clear()
        self.addCleanup(self.cache.clear)
        self.order = Order.objects.create(
            name='PRIVATE_NICK', phone='PRIVATE_PHONE', email='private@example.org',
            address='PRIVATE_ADDRESS', comment='PRIVATE_COMMENT',
            total='201.00', checkout_token=uuid.uuid4(), session_key='PRIVATE_SESSION',
        )
        OrderItem.objects.create(
            order=self.order, product_name='Phone', color='Black', memory='128 GB',
            unit_price='100.50', quantity=2,
        )
        self.url = f'/api/orders/{self.order.tracking_token}/'

    def test_warm_order_cache_avoids_database_queries_and_keeps_private_headers(self):
        first = self.client.get(self.url)
        self.assertEqual(first.status_code, 200)
        with self.assertNumQueries(0):
            second = self.client.get(self.url)
        self.assertEqual(second.json(), first.json())
        self.assertIn('no-store', second['Cache-Control'])
        self.assertNotIn('PRIVATE_', second.content.decode())
        self.assertNotIn('private@example.org', second.content.decode())

    def test_same_ip_and_order_seventh_request_is_throttled_before_database(self):
        for _ in range(6):
            self.assertEqual(self.client.get(self.url).status_code, 200)
        with self.assertNumQueries(0):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response['Retry-After']), 0)
        self.assertIn('no-store', response['Cache-Control'])

    def test_ip_limits_are_independent(self):
        for _ in range(6):
            self.assertEqual(self.client.get(self.url, REMOTE_ADDR='192.0.2.1').status_code, 200)
        self.assertEqual(self.client.get(self.url, REMOTE_ADDR='192.0.2.1').status_code, 429)
        self.assertEqual(self.client.get(self.url, REMOTE_ADDR='192.0.2.2').status_code, 200)

    def test_rotating_tokens_cannot_bypass_total_ip_limit(self):
        for _ in range(30):
            self.assertEqual(self.client.get(f'/api/orders/{uuid.uuid4()}/').status_code, 404)
        with self.assertNumQueries(0):
            response = self.client.get(f'/api/orders/{uuid.uuid4()}/')
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response['Retry-After']), 0)

    def test_spoofed_forwarded_header_cannot_reset_client_limit(self):
        for number in range(6):
            response = self.client.get(self.url, HTTP_X_FORWARDED_FOR=f'198.51.100.{number}')
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(self.url, HTTP_X_FORWARDED_FOR='203.0.113.5').status_code, 429)

    def test_missing_order_is_negatively_cached(self):
        url = f'/api/orders/{uuid.uuid4()}/'
        self.assertEqual(self.client.get(url).status_code, 404)
        with self.assertNumQueries(0):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_order_snapshot_refreshes_after_cache_entry_expires(self):
        now = time.time()
        with patch('time.time', return_value=now):
            self.assertEqual(self.client.get(self.url).json()['status'], 'new')
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PROCESSING)
        with patch('time.time', return_value=now + 29):
            with self.assertNumQueries(0):
                self.assertEqual(self.client.get(self.url).json()['status'], 'new')
        with patch('time.time', return_value=now + 31):
            self.assertEqual(self.client.get(self.url).json()['status'], 'processing')

    def test_file_cache_shares_responses_and_limits_between_backend_instances(self):
        with TemporaryDirectory() as directory:
            cache_settings = {
                'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
                'order_tracking': {
                    'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
                    'LOCATION': directory,
                },
            }
            with override_settings(CACHES=cache_settings):
                first_cache = caches['order_tracking']
                for _ in range(6):
                    self.assertEqual(self.client.get(self.url).status_code, 200)
            with override_settings(CACHES=cache_settings):
                self.assertIsNot(caches['order_tracking'], first_cache)
                with self.assertNumQueries(0):
                    response = self.client.get(self.url)
                self.assertEqual(response.status_code, 429)
                # A second client can reuse the shared snapshot without SQL.
                with self.assertNumQueries(0):
                    response = self.client.get(self.url, REMOTE_ADDR='192.0.2.2')
                self.assertEqual(response.status_code, 200)

    def test_options_requests_also_count_towards_limit(self):
        for _ in range(6):
            self.assertEqual(self.client.options(self.url).status_code, 200)
        response = self.client.options(self.url)
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response['Retry-After']), 0)
