import uuid

from django.db import migrations, models


def populate_tracking_tokens(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    orders = Order.objects.using(schema_editor.connection.alias)
    for order in orders.filter(tracking_token__isnull=True).iterator():
        orders.filter(pk=order.pk, tracking_token__isnull=True).update(tracking_token=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [('orders', '0005_ordernotification')]

    operations = [
        migrations.AddField(
            model_name='order', name='tracking_token',
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(populate_tracking_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='order', name='tracking_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
    ]
