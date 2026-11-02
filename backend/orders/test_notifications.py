import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock
from urllib.error import URLError

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from orders.models import Order, OrderItem, OrderNotification
from orders.telegram import DeliveryError, message_for, send_order
from orders import tests as shopping


class NotificationCheckoutTests(TestCase):
    setUp = shopping.ShoppingTests.setUp
    add = shopping.ShoppingTests.add
    checkout = shopping.ShoppingTests.checkout

    def test_checkout_enqueues_once_and_failure_does_not_enqueue(self):
        self.add()
        token = uuid.uuid4()
        self.assertEqual(self.checkout(token).status_code, 201)
        self.assertEqual(self.checkout(token).status_code, 200)
        self.assertEqual(OrderNotification.objects.count(), 1)
        self.add(1)
        self.variant.stock = 0
        self.variant.save()
        self.assertEqual(self.checkout().status_code, 400)
        self.assertEqual(OrderNotification.objects.count(), 1)


@override_settings(TELEGRAM_BOT_TOKEN='secret-test-token', TELEGRAM_CHAT_ID='123', SITE_URL='https://shop.example.com')
class NotificationTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(name='PRIVATE_NICK', phone='PRIVATE_PHONE',
            email='private@example.org', address='PRIVATE_ADDRESS', comment='PRIVATE_COMMENT',
            total='201', checkout_token=uuid.uuid4(), session_key='session')
        OrderItem.objects.create(order=self.order, product_name='iPhone', color='Black',
            memory='128 GB', unit_price='100.50', quantity=2)
        self.notification = OrderNotification.objects.create(order=self.order)
        self.order.refresh_from_db()

    def run_command(self):
        call_command('send_order_notifications', stdout=io.StringIO())

    def test_message_uses_only_snapshot_and_no_contacts(self):
        message = message_for(self.order)
        self.assertIn('iPhone / Black / 128 GB × 2', message)
        self.assertIn('201.00', message)
        for private in ['PRIVATE_', 'private@example.org', 'session']:
            self.assertNotIn(private, message)
        for _ in range(70):
            OrderItem.objects.create(order=self.order, product_name='😀' * 200,
                color='White', unit_price=1, quantity=1)
        self.assertLessEqual(len(message_for(self.order).encode('utf-16-le')) // 2, 4096)

    @patch('orders.management.commands.send_order_notifications.send_order', return_value=42)
    def test_success_and_repeated_command(self, send):
        self.run_command()
        self.run_command()
        self.notification.refresh_from_db()
        self.assertIsNotNone(self.notification.sent_at)
        self.assertEqual(self.notification.attempts, 1)
        self.assertEqual(self.notification.message_id, 42)
        send.assert_called_once()

    @patch('orders.management.commands.send_order_notifications.send_order', side_effect=DeliveryError('http_429', 300))
    def test_retry_is_delayed_and_same_row(self, send):
        before = timezone.now()
        self.run_command()
        self.run_command()
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.sent_at)
        self.assertEqual(self.notification.attempts, 1)
        self.assertEqual(self.notification.last_error, 'http_429')
        self.assertGreaterEqual(self.notification.next_attempt_at, before + timedelta(seconds=300))
        self.assertEqual(OrderNotification.objects.count(), 1)
        send.assert_called_once()

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_unconfigured_does_not_claim(self):
        with self.assertRaises(CommandError):
            self.run_command()
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.attempts, 0)

    @patch('orders.telegram.urllib.request.urlopen', side_effect=URLError('secret-test-token'))
    def test_error_does_not_leak_token(self, send):
        with self.assertRaises(DeliveryError) as error:
            send_order(self.order)
        self.assertEqual(str(error.exception), 'network_error')

    @patch('orders.telegram.urllib.request.urlopen')
    def test_transport_plain_text_no_pii(self, send):
        response = MagicMock()
        response.read.return_value = b'{"ok":true,"result":{"message_id":123}}'
        send.return_value.__enter__.return_value = response
        self.assertEqual(send_order(self.order), 123)
        request = send.call_args.args[0]
        data = json.loads(request.data)
        self.assertNotIn('parse_mode', data)
        entity = data['entities'][0]
        self.assertEqual(entity['type'], 'text_link')
        self.assertEqual(entity['url'], f'https://shop.example.com/orders/{self.order.tracking_token}')
        encoded = data['text'].encode('utf-16-le')
        self.assertEqual(encoded[entity['offset'] * 2:(entity['offset'] + entity['length']) * 2].decode('utf-16-le'), 'Ссылка для клиента')
        self.assertEqual(data['link_preview_options'], {'is_disabled': True})
        self.assertEqual(data['reply_markup']['inline_keyboard'][0][0]['url'], f'https://shop.example.com/admin/orders/order/{self.order.pk}/change/')
        self.assertNotIn('PRIVATE_', request.data.decode())
        self.assertEqual(send.call_args.kwargs['timeout'], 5)

    @patch('orders.telegram.urllib.request.urlopen')
    def test_client_link_with_emoji_and_legacy_order(self, send):
        self.order.items.update(product_name='📱 <iPhone> & Apple')
        Order.objects.filter(pk=self.order.pk).update(tracking_token=None)
        self.order.refresh_from_db()
        response = MagicMock()
        response.read.return_value = b'{"ok":true,"result":{"message_id":123}}'
        send.return_value.__enter__.return_value = response
        send_order(self.order)
        data = json.loads(send.call_args.args[0].data)
        entity = data['entities'][0]
        encoded = data['text'].encode('utf-16-le')
        self.assertEqual(encoded[entity['offset'] * 2:(entity['offset'] + entity['length']) * 2].decode('utf-16-le'), 'Ссылка для клиента')
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.tracking_token)
        self.assertEqual(entity['url'], f'https://shop.example.com/orders/{self.order.tracking_token}')
        self.assertIn('📱 <iPhone> & Apple', data['text'])

    @patch('orders.management.commands.send_order_notifications.send_order')
    def test_active_claim_not_sent(self, send):
        self.notification.locked_until = timezone.now() + timedelta(minutes=2)
        self.notification.save()
        self.run_command()
        send.assert_not_called()

    @patch('orders.management.commands.send_order_notifications.send_order')
    def test_expired_worker_cannot_overwrite_new_owner(self, send):
        new_owner = uuid.uuid4()

        def lose_lease(order):
            OrderNotification.objects.filter(pk=self.notification.pk).update(claim_token=new_owner)
            return 42

        send.side_effect = lose_lease
        self.run_command()
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.sent_at)
        self.assertEqual(self.notification.claim_token, new_owner)

    @patch('orders.management.commands.send_order_notifications.send_order')
    def test_maintenance_skips_without_claiming(self, send):
        with patch('pathlib.Path.exists', return_value=True):
            self.run_command()
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.attempts, 0)
        send.assert_not_called()
