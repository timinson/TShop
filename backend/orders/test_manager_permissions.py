import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from orders.models import Order, OrderItem


class ReadOnlyManagerTests(TestCase):
    def setUp(self):
        manager = get_user_model().objects.create_user('readonly-manager', is_staff=True)
        manager.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='orders', codename__in=['view_order', 'view_orderitem'],
        ))
        manager.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='catalog', codename__in=['view_product', 'view_productvariant'],
        ))
        self.client.force_login(manager)
        category = Category.objects.create(name='Телефоны', slug='phones')
        self.product = Product.objects.create(category=category, name='Телефон', slug='phone', description='Описание')
        self.order = Order.objects.create(
            name='Тест', phone='8000000000', email='test@test.ru', address='Тестовый адрес',
            total='100.00', checkout_token=uuid.uuid4(), session_key='test-session',
        )

    def test_can_view_orders_and_products(self):
        for name, args in [
            ('admin:orders_order_changelist', []),
            ('admin:orders_order_change', [self.order.pk]),
            ('admin:catalog_product_changelist', []),
            ('admin:catalog_product_change', [self.product.pk]),
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_order_list_contains_link_summary_and_sortable_status(self):
        OrderItem.objects.create(order=self.order, product_name='Телефон', color='Чёрный', unit_price='100.00', quantity=2)
        response = self.client.get(reverse('admin:orders_order_changelist'))
        self.assertContains(response, reverse('admin:orders_order_change', args=[self.order.pk]))
        self.assertContains(response, 'Телефон × 2')
        self.assertContains(response, 'order-status--new')
        self.assertContains(response, 'shop_admin/orders-list.js')
        self.assertTrue(response.context['cl'].get_ordering_field('status_badge'))

    def test_order_summaries_do_not_query_per_order(self):
        from django.contrib import admin
        from django.test import RequestFactory

        order_admin = admin.site._registry[Order]
        request = RequestFactory().get('/')
        with self.assertNumQueries(2):
            orders = list(order_admin.get_queryset(request))
            for order in orders:
                order_admin.items_summary(order)

    def test_cannot_change_or_delete_orders_and_products(self):
        for name, args, data in [
            ('admin:orders_order_change', [self.order.pk], {'status': Order.Status.CANCELLED}),
            ('admin:orders_order_delete', [self.order.pk], {'post': 'yes'}),
            ('admin:catalog_product_change', [self.product.pk], {'name': 'Изменённый товар'}),
            ('admin:catalog_product_delete', [self.product.pk], {'post': 'yes'}),
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.post(reverse(name, args=args), data).status_code, 403)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.NEW)
        self.assertEqual(self.product.name, 'Телефон')

    def test_cannot_access_user_or_notification_management(self):
        for name in ['admin:auth_user_changelist', 'admin:orders_ordernotification_changelist']:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
