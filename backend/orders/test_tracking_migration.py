import uuid

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TrackingMigrationTests(TransactionTestCase):
    def test_existing_orders_get_distinct_tokens_and_preserve_data(self):
        previous = [('orders', '0005_ordernotification')]
        current = [('orders', '0008_order_completed_at')]
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        try:
            LegacyOrder = executor.loader.project_state(previous).apps.get_model('orders', 'Order')
            ids = [LegacyOrder.objects.create(
                name=f'Legacy {index}', phone='123456789', email='demo@example.com',
                address='Demo', total='123.45', status='processing',
                checkout_token=uuid.uuid4(), session_key='legacy-session',
            ).pk for index in range(2)]
            executor = MigrationExecutor(connection)
            executor.migrate(current)
            Order = executor.loader.project_state(current).apps.get_model('orders', 'Order')
            orders = list(Order.objects.filter(pk__in=ids).order_by('pk'))
            self.assertEqual(len(orders), 2)
            self.assertEqual(len({order.tracking_token for order in orders}), 2)
            for index, order in enumerate(orders):
                self.assertIsInstance(order.tracking_token, uuid.UUID)
                self.assertEqual(order.name, f'Legacy {index}')
                self.assertEqual(str(order.total), '123.45')
                self.assertEqual(order.status, 'processing')
            # The old ORM INSERT omits tracking_token entirely after code rollback.
            legacy = LegacyOrder.objects.create(
                name='Rollback', phone='123456789', email='demo@example.com',
                address='Demo', total='123.45', checkout_token=uuid.uuid4(),
                session_key='legacy-session',
            )
            from orders.models import Order as LiveOrder
            restored = LiveOrder.objects.get(pk=legacy.pk)
            self.assertIsNone(restored.tracking_token)
            self.assertIsInstance(restored.ensure_tracking_token(), uuid.UUID)
            restored.refresh_from_db()
            self.assertIsNotNone(restored.tracking_token)
        finally:
            MigrationExecutor(connection).migrate(current)
