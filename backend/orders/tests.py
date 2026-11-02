import uuid
import importlib
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase
from django.apps import apps
from django.db import connection

from catalog.models import Category, Product, ProductVariant
from orders.admin import OrderAdmin, OrderAdminForm
from orders.models import Order, OrderItem
from orders.services import transition_order_status
from orders.privacy import PRIVACY_POLICY_VERSION


class ShoppingTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Phones', slug='phones')
        self.product = Product.objects.create(category=category, name='Phone', slug='phone', description='Phone')
        self.variant = ProductVariant.objects.create(product=self.product, color='Black', memory='128 GB', price='100.50', stock=5)
        self.client = Client(enforce_csrf_checks=True)
        self.client.get('/api/cart/')
        self.headers = {'HTTP_X_CSRFTOKEN': self.client.cookies['csrftoken'].value}

    def add(self, qty=1):
        return self.client.post('/api/cart/', {'variant_id': self.variant.pk, 'quantity': qty}, content_type='application/json', **self.headers)

    def checkout(self, token=None, **overrides):
        payload = {
            'name': 'Покупатель', 'phone': '+79991234567', 'email': 'buyer@example.com',
            'address': 'Улица 1', 'checkout_token': str(token or uuid.uuid4()),
            'privacy_consent': True, 'privacy_policy_version': PRIVACY_POLICY_VERSION,
        }
        payload.update(overrides)
        return self.client.post('/api/orders/', payload, content_type='application/json', **self.headers)

    def test_consent_must_be_actual_true_and_preserves_cart_and_stock(self):
        self.add(2)
        for consent in [False, None, 'true', '1', 1, 0, [], {}]:
            with self.subTest(consent=consent):
                response = self.checkout(privacy_consent=consent)
                self.assertEqual(response.status_code, 400)
                self.assertIn('privacy_consent', response.json())
        payload = {'name': 'Test', 'phone': '123456789', 'email': 'test@example.com', 'address': 'Address', 'checkout_token': str(uuid.uuid4()), 'privacy_policy_version': PRIVACY_POLICY_VERSION}
        response = self.client.post('/api/orders/', payload, content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('privacy_consent', response.json())
        self.assertEqual(Order.objects.count(), 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)
        self.assertEqual(self.client.get('/api/cart/').json()['count'], 2)

    def test_consent_stamps_server_time_and_current_version(self):
        from django.utils import timezone
        self.add()
        before = timezone.now()
        self.assertEqual(self.checkout(privacy_consent_at='2000-01-01T00:00:00Z').status_code, 201)
        order = Order.objects.get()
        self.assertGreaterEqual(order.privacy_consent_at, before)
        self.assertLessEqual(order.privacy_consent_at, timezone.now())
        self.assertEqual(order.privacy_policy_version, PRIVACY_POLICY_VERSION)

    def test_old_or_missing_policy_version_blocks_checkout_and_retry(self):
        self.add()
        token = uuid.uuid4()
        self.assertEqual(self.checkout(token, privacy_policy_version='old').status_code, 400)
        self.assertEqual(self.checkout(token, privacy_policy_version=None).status_code, 400)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.checkout(token).status_code, 201)
        self.assertEqual(self.checkout(token, privacy_consent=False).status_code, 400)
        self.assertEqual(self.checkout(token, privacy_policy_version='old').status_code, 400)

    def test_anonymous_mutations_require_csrf(self):
        self.assertEqual(self.client.post('/api/cart/', {'variant_id': self.variant.pk}, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post('/api/orders/', {}, content_type='application/json').status_code, 403)
        self.assertEqual(self.add().status_code, 200)

    def test_cart_totals_and_session_isolation(self):
        self.assertEqual(self.add(2).json()['total'], '201.00')
        self.assertEqual(Client().get('/api/cart/').json()['count'], 0)
        for qty in [0, -1, 100, True, '1']:
            self.assertEqual(self.add(qty).status_code, 400)
        response = self.client.patch(f'/api/cart/items/{self.variant.pk}/', {'quantity': 3}, content_type='application/json', **self.headers)
        self.assertEqual(response.json()['total'], '301.50')

    def test_order_uses_current_price_and_keeps_snapshots(self):
        self.add(2)
        self.variant.price = Decimal('120.00')
        self.variant.save()
        token = uuid.uuid4()
        response = self.checkout(token)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['total'], '240.00')
        self.assertEqual(self.client.get('/api/cart/').json()['count'], 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)
        self.product.name = 'Renamed'
        self.product.save()
        self.assertEqual(Order.objects.get().items.get().product_name, 'Phone')
        self.assertEqual(Order.objects.get().items.get().variant_id, self.variant.pk)
        self.assertEqual(self.checkout(token).status_code, 200)
        self.assertEqual(Order.objects.count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)

    def test_out_of_stock_rolls_back_all_lines(self):
        second = ProductVariant.objects.create(product=self.product, color='White', price='200', stock=2)
        self.add(2)
        self.client.post('/api/cart/', {'variant_id': second.pk, 'quantity': 2}, content_type='application/json', **self.headers)
        second.stock = 1
        second.save()
        self.assertEqual(self.checkout().status_code, 400)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.get('/api/cart/').json()['count'], 4)

    def test_checkout_applies_current_discount_and_saves_discounted_snapshot(self):
        self.add(2)
        self.product.discount_percent = 15
        self.product.save()
        response = self.checkout()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['total'], '170.86')
        order = Order.objects.get()
        self.assertEqual(order.items.get().unit_price, Decimal('85.43'))
        self.product.discount_percent = 0
        self.product.save()
        self.assertEqual(order.items.get().unit_price, Decimal('85.43'))

    def test_removed_or_hidden_lines_block_checkout(self):
        self.add()
        self.product.is_active = False
        self.product.save()
        self.assertFalse(self.client.get('/api/cart/').json()['items'][0]['is_available'])
        self.assertEqual(self.checkout().status_code, 400)
        variant_id = self.variant.pk
        self.variant.delete()
        self.assertEqual(self.client.get('/api/cart/').json()['count'], 1)
        self.assertEqual(self.checkout().status_code, 400)
        self.assertEqual(self.client.delete(f'/api/cart/items/{variant_id}/', **self.headers).json()['count'], 0)

    def test_checkout_token_does_not_expose_another_session_order(self):
        self.add()
        token = uuid.uuid4()
        self.checkout(token)
        other = Client(enforce_csrf_checks=True)
        other.get('/api/cart/')
        response = other.post('/api/orders/', {'name': 'Other', 'phone': '123456789', 'email': 'other@example.com', 'address': 'Other', 'checkout_token': str(token), 'privacy_consent': True, 'privacy_policy_version': PRIVACY_POLICY_VERSION}, content_type='application/json', HTTP_X_CSRFTOKEN=other.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/orders/').status_code, 405)

    def test_tracking_link_is_independent_and_repeat_checkout_returns_same_link(self):
        self.add(2)
        checkout_token = uuid.uuid4()
        supplied_token = uuid.uuid4()
        response = self.checkout(checkout_token, tracking_token=str(supplied_token))
        self.assertEqual(response.status_code, 201)
        token = response.json()['tracking_token']
        self.assertNotIn(token, [str(checkout_token), str(supplied_token)])
        self.assertEqual(token, str(Order.objects.get().tracking_token))
        self.assertEqual(self.checkout(checkout_token).json()['tracking_token'], token)
        self.assertIn('no-store', response['Cache-Control'])

    def test_tracking_link_shows_snapshots_without_private_fields(self):
        order = self.make_order()
        self.product.name = 'New name'
        self.product.save()
        self.variant.price = Decimal('999.00')
        self.variant.save()
        response = Client().get(f'/api/orders/{order.tracking_token}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        data = response.json()
        self.assertEqual(set(data), {'id', 'number', 'total', 'status', 'status_label', 'created_at', 'items'})
        self.assertEqual(data['total'], '201.00')
        self.assertEqual(data['status_label'], 'Новый')
        self.assertEqual(data['items'], [{
            'product_name': 'Phone', 'color': 'Black', 'memory': '128 GB',
            'unit_price': '100.50', 'quantity': 2, 'line_total': '201.00',
        }])

    def test_repeat_checkout_restores_link_for_order_created_during_rollback(self):
        self.add()
        checkout_token = uuid.uuid4()
        self.checkout(checkout_token)
        order = Order.objects.get()
        Order.objects.filter(pk=order.pk).update(tracking_token=None)
        response = self.checkout(checkout_token)
        self.assertEqual(response.status_code, 200)
        token = response.json()['tracking_token']
        self.assertIsInstance(uuid.UUID(token), uuid.UUID)
        self.assertEqual(self.checkout(checkout_token).json()['tracking_token'], token)
        self.assertEqual(Client().get(f'/api/orders/{token}/').status_code, 200)
        self.assertEqual(Order.objects.count(), 1)

    def test_admin_restores_missing_token_without_replacing_concurrently_assigned_link(self):
        order = self.make_order()
        Order.objects.filter(pk=order.pk).update(tracking_token=None)
        first = Order.objects.get(pk=order.pk)
        stale = Order.objects.get(pk=order.pk)
        link = OrderAdmin(Order, AdminSite()).tracking_link(first)
        self.assertIsNotNone(first.tracking_token)
        self.assertIn(str(first.tracking_token), link)
        self.assertEqual(stale.ensure_tracking_token(), first.tracking_token)

    def test_tracking_rejects_number_checkout_token_and_unknown_token(self):
        order = self.make_order()
        for token in [order.pk, order.checkout_token, uuid.uuid4(), 'invalid']:
            with self.subTest(token=token):
                self.assertEqual(Client().get(f'/api/orders/{token}/').status_code, 404)
        self.assertEqual(Client().post(f'/api/orders/{order.tracking_token}/', {}).status_code, 405)

    def test_tracking_reflects_admin_status_change_and_is_read_only(self):
        order = self.make_order()
        model_admin = OrderAdmin(Order, AdminSite())
        order.status = Order.Status.PROCESSING
        model_admin.save_model(RequestFactory().post('/'), order, None, True)
        url = f'/api/orders/{order.tracking_token}/'
        response = Client().get(url)
        self.assertEqual(response.json()['status'], 'processing')
        self.assertEqual(response.json()['status_label'], 'В обработке')
        for method in ['post', 'patch', 'delete']:
            self.assertEqual(getattr(Client(), method)(url, {}, content_type='application/json').status_code, 405)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)

    def test_empty_order_and_invalid_contact(self):
        self.assertEqual(self.checkout().status_code, 400)
        self.add()
        self.assertEqual(self.client.post('/api/orders/', {'name': 'Test'}, content_type='application/json', **self.headers).status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_submitted_contacts_and_comment_are_replaced_before_validation(self):
        from orders.demo import DEMO_PHONE, DEMO_EMAIL, DEMO_ADDRESS, DEMO_COMMENT
        self.add()
        response = self.checkout(phone={'unexpected': 'contact'}, email='invalid',
                                 address='Real address', comment='Private message')
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.phone, DEMO_PHONE)
        self.assertEqual(order.email, DEMO_EMAIL)
        self.assertEqual(order.address, DEMO_ADDRESS)
        self.assertEqual(order.comment, DEMO_COMMENT)

    def test_demo_contacts_can_be_omitted(self):
        from orders.demo import DEMO_PHONE, DEMO_EMAIL, DEMO_ADDRESS, DEMO_COMMENT
        self.add()
        payload = {'name': 'nickname', 'checkout_token': str(uuid.uuid4()),
                   'privacy_consent': True, 'privacy_policy_version': PRIVACY_POLICY_VERSION}
        response = self.client.post('/api/orders/', payload, content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.name, 'nickname')
        self.assertEqual((order.phone, order.email, order.address),
                         (DEMO_PHONE, DEMO_EMAIL, DEMO_ADDRESS))
        self.assertEqual(order.comment, DEMO_COMMENT)

    def test_admin_preserves_order_snapshots(self):
        model_admin = OrderAdmin(Order, AdminSite())
        request = RequestFactory().get('/')
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertEqual(set(model_admin.get_fields(request)) - set(model_admin.readonly_fields), {'status'})

    def make_order(self):
        self.add(2)
        self.assertEqual(self.checkout().status_code, 201)
        return Order.objects.get()

    def test_cancellation_returns_stock_once_and_preserves_snapshots(self):
        order = self.make_order()
        transition_order_status(order.pk, Order.Status.PROCESSING)
        transition_order_status(order.pk, Order.Status.CANCELLED)
        transition_order_status(order.pk, Order.Status.CANCELLED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)
        self.assertEqual(order.items.get().unit_price, Decimal('100.50'))
        with self.assertRaises(ValidationError):
            transition_order_status(order.pk, Order.Status.PROCESSING)

    def test_cancellation_returns_each_variant_once(self):
        second = ProductVariant.objects.create(product=self.product, color='White', price='200', stock=4)
        self.add(2)
        self.client.post('/api/cart/', {'variant_id': second.pk, 'quantity': 3}, content_type='application/json', **self.headers)
        self.assertEqual(self.checkout().status_code, 201)
        order = Order.objects.get()
        self.variant.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((self.variant.stock, second.stock), (3, 1))
        transition_order_status(order.pk, Order.Status.CANCELLED)
        transition_order_status(order.pk, Order.Status.CANCELLED)
        self.variant.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((self.variant.stock, second.stock), (5, 4))

    def test_missing_variant_blocks_entire_cancellation(self):
        order = self.make_order()
        OrderItem.objects.create(order=order, product_name='Deleted', color='Black', unit_price=1, quantity=1)
        with self.assertRaises(ValidationError):
            transition_order_status(order.pk, Order.Status.CANCELLED)
        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)
        self.assertEqual(self.variant.stock, 3)

    def test_deleted_variant_keeps_snapshot_and_blocks_cancellation(self):
        order = self.make_order()
        self.variant.delete()
        self.assertIsNone(order.items.get().variant_id)
        self.assertEqual(order.items.get().product_name, 'Phone')
        form = OrderAdminForm(data={'status': Order.Status.CANCELLED}, instance=order)
        self.assertFalse(form.is_valid())
        self.assertIn('status', form.errors)

    def test_completed_order_is_terminal(self):
        order = self.make_order()
        completed = transition_order_status(order.pk, Order.Status.COMPLETED)
        self.assertIsNotNone(completed.completed_at)
        original_completed_at = completed.completed_at
        transition_order_status(order.pk, Order.Status.COMPLETED)
        order.refresh_from_db()
        self.assertEqual(order.completed_at, original_completed_at)
        with self.assertRaises(ValidationError):
            transition_order_status(order.pk, Order.Status.CANCELLED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)

    def test_existing_completed_order_without_date_is_not_backfilled_on_save(self):
        order = self.make_order()
        Order.objects.filter(pk=order.pk).update(status=Order.Status.COMPLETED)
        transition_order_status(order.pk, Order.Status.COMPLETED)
        order.refresh_from_db()
        self.assertIsNone(order.completed_at)

    def test_legacy_backfill_only_maps_unique_exact_snapshots(self):
        order = self.make_order()
        item = order.items.get()
        item.variant = None
        item.save()
        backfill = importlib.import_module('orders.migrations.0002_orderitem_variant').backfill_variants
        backfill(apps, connection.schema_editor())
        item.refresh_from_db()
        self.assertEqual(item.variant_id, self.variant.pk)
        duplicate = Product.objects.create(category=self.product.category, name=self.product.name, slug='duplicate', description='Duplicate')
        ProductVariant.objects.create(product=duplicate, color=self.variant.color, memory=self.variant.memory, price='1', stock=0)
        item.variant = None
        item.save()
        backfill(apps, connection.schema_editor())
        item.refresh_from_db()
        self.assertIsNone(item.variant_id)

    def test_admin_manager_can_change_status_but_not_order_data(self):
        order = self.make_order()
        manager = User.objects.create_user('manager', password='test-password', is_staff=True)
        manager.user_permissions.add(*Permission.objects.filter(content_type__app_label='orders', codename__in=['view_order', 'change_order', 'view_orderitem']))
        client = Client()
        client.force_login(manager)
        url = f'/admin/orders/order/{order.pk}/change/'
        response = client.post(url, {'status': 'cancelled', 'name': 'Changed', 'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '1', 'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000', 'items-0-id': str(order.items.get().pk), 'items-0-order': str(order.pk), '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.name, 'Покупатель')
        self.assertEqual(Client().get(f'/api/orders/{order.tracking_token}/').json()['status'], 'cancelled')
        self.assertIn(f'/orders/{order.tracking_token}', OrderAdmin(Order, AdminSite()).tracking_link(order))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)
        response = client.post(url, {'status': 'processing'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'нельзя перевести')
