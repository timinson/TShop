import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Order, OrderItem


class AnalyticsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('manager', is_staff=True)
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='orders', codename='view_order'))
        self.client.force_login(self.user)
        self.url = reverse('sales_analytics')

    def make_order(self, status, completed_at, price='10.25', quantity=2):
        order = Order.objects.create(name='Test', phone='1', email='a@example.com', address='x', total='99', status=status, completed_at=completed_at, checkout_token=uuid.uuid4(), session_key='x')
        OrderItem.objects.create(order=order, product_name='Старое название', color='x', unit_price=price, quantity=quantity)
        return order

    def test_sales_dates_snapshots_and_zeros(self):
        tz = ZoneInfo('Asia/Yekaterinburg')
        self.make_order(Order.Status.COMPLETED, datetime(2025, 1, 2, 1, tzinfo=tz))
        self.make_order(Order.Status.NEW, None)
        self.make_order(Order.Status.COMPLETED, None)
        response = self.client.get(self.url, {'period': 'custom', 'start': '2025-01-01', 'end': '2025-01-03', 'grouping': 'day'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current']['revenue'], Decimal('20.50'))
        self.assertEqual(response.context['current']['orders'], 1)
        self.assertEqual(response.context['current']['units'], 2)
        self.assertEqual(response.context['unknown_count'], 1)
        self.assertEqual([p['orders'] for p in response.context['series']], [0, 1, 0])
        self.assertNotContains(response, 'предыдущему периоду')
        self.assertNotContains(response, 'Сравнение:')
        self.assertLess(response.content.decode().index('03.01.2025</span>'), response.content.decode().index('02.01.2025</span>'))

    def test_invalid_dates_and_permission(self):
        response = self.client.get(self.url, {'period': 'custom', 'start': '2025-02-01', 'end': '2025-01-01', 'grouping': 'day'})
        self.assertContains(response, 'Начало периода')
        self.user.user_permissions.clear()
        self.client.force_login(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_previous_period_comparison_and_calendar_groups(self):
        tz = ZoneInfo('Asia/Yekaterinburg')
        self.make_order(Order.Status.COMPLETED, datetime(2025, 1, 31, 23, 59, tzinfo=tz), '0.10', 3)
        self.make_order(Order.Status.COMPLETED, datetime(2025, 2, 1, 0, 0, tzinfo=tz), '0.20', 3)
        self.make_order(Order.Status.COMPLETED, datetime(2025, 2, 7, 23, 59, tzinfo=tz), '0.30', 3)
        self.make_order(Order.Status.COMPLETED, datetime(2025, 2, 8, 0, 0, tzinfo=tz), '50.00', 1)
        params = {'period': 'custom', 'start': '2025-02-01', 'end': '2025-02-07', 'grouping': 'week'}
        response = self.client.get(self.url, params)
        self.assertEqual(response.context['current']['revenue'], Decimal('1.50'))
        self.assertEqual(response.context['current']['orders'], 2)
        self.assertEqual(response.context['current']['average'], Decimal('0.75'))
        self.assertEqual([point['orders'] for point in response.context['series']], [1, 0, 0, 0, 0, 0, 1])
        self.assertEqual(response.context['ranking'][0]['units'], 6)
        params.update(start='2025-01-08', end='2025-02-07')
        response = self.client.get(self.url, params)
        self.assertEqual(response.context['grouping'], 'week')
        self.assertEqual([point['orders'] for point in response.context['series']], [0, 0, 0, 2, 1])
        params.update(start='2025-01-01', end='2025-04-01', grouping='month')
        response = self.client.get(self.url, params)
        self.assertEqual([point['orders'] for point in response.context['series']], [1, 3, 0, 0])

    def test_automatic_grouping_boundaries_and_interval_limits(self):
        start = date(2025, 1, 1)
        for days, expected in [(1, 'day'), (30, 'day'), (31, 'week'), (90, 'week'), (91, 'month')]:
            with self.subTest(days=days):
                end = start + timedelta(days=days - 1)
                response = self.client.get(self.url, {'period': 'custom', 'start': start.isoformat(), 'end': end.isoformat(), 'grouping': 'day'})
                self.assertEqual(response.context['grouping'], expected)
                points = response.context['series']
                self.assertEqual(points[0]['range_start'], start)
                self.assertEqual(points[-1]['range_end'], end)
                for previous, following in zip(points, points[1:]):
                    self.assertEqual(previous['range_end'] + timedelta(days=1), following['range_start'])

    def test_time_zone_midnight_and_date_validation(self):
        from datetime import timezone
        self.make_order(Order.Status.COMPLETED, datetime(2025, 1, 1, 20, 30, tzinfo=timezone.utc))
        params = {'period': 'custom', 'start': '2025-01-02', 'end': '2025-01-02', 'grouping': 'day'}
        response = self.client.get(self.url, params)
        self.assertEqual(response.context['current']['orders'], 1)
        for start, end in [('1900-01-01', '1900-01-02'), ('2020-01-01', '2031-01-01'), ('2025-02-30', '2025-03-01')]:
            with self.subTest(start=start):
                response = self.client.get(self.url, {**params, 'start': start, 'end': end})
                self.assertTrue(response.context['form'].errors)
                self.assertNotIn('current', response.context)

    def test_login_and_staff_enforced(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        user = get_user_model().objects.create_user('not-staff')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='orders', codename='view_order'))
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_interval_order_details_use_snapshots_timezone_and_permissions(self):
        from datetime import timezone
        sale = self.make_order(Order.Status.COMPLETED, datetime(2025, 1, 1, 20, 30, tzinfo=timezone.utc), '0.10', 3)
        self.make_order(Order.Status.NEW, datetime(2025, 1, 1, 20, 30, tzinfo=timezone.utc))
        self.make_order(Order.Status.COMPLETED, None)
        url = reverse('sales_analytics_orders')
        params = {'start': '2025-01-02', 'end': '2025-01-02'}
        with self.assertNumQueries(7):
            response = self.client.get(url, params)
        self.assertEqual(response.json(), {'orders': [{'id': sale.pk, 'date': '2025-01-02', 'total': '0.30'}], 'page': 1, 'has_next': False})
        self.assertEqual(self.client.get(url, {**params, 'page': '0'}).status_code, 400)
        self.assertEqual(self.client.get(url, {**params, 'start': 'bad'}).status_code, 400)
        self.user.user_permissions.clear()
        self.client.force_login(get_user_model().objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(url, params).status_code, 403)

    def test_interval_details_are_paginated(self):
        tz = ZoneInfo('Asia/Yekaterinburg')
        for _ in range(21):
            self.make_order(Order.Status.COMPLETED, datetime(2025, 2, 1, 12, tzinfo=tz))
        url = reverse('sales_analytics_orders')
        params = {'start': '2025-02-01', 'end': '2025-02-01'}
        first = self.client.get(url, params).json()
        second = self.client.get(url, {**params, 'page': 2}).json()
        self.assertEqual((len(first['orders']), first['has_next']), (20, True))
        self.assertEqual((len(second['orders']), second['has_next']), (1, False))
        self.assertTrue({o['id'] for o in first['orders']}.isdisjoint(o['id'] for o in second['orders']))
