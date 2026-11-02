import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('catalog', '0003_product_image')]
    operations = [
        migrations.AddField(
            model_name='product', name='discount_percent',
            field=models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(99)], verbose_name='Скидка, %', help_text='От 0 до 99. Применяется ко всем вариантам товара.'),
        ),
        migrations.AddConstraint(model_name='product', constraint=models.CheckConstraint(condition=models.Q(discount_percent__lte=99), name='product_discount_max_99')),
    ]
