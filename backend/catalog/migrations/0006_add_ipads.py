from datetime import date
from decimal import Decimal

from django.db import migrations


# Specifications and first availability: Apple Newsroom.
# https://www.apple.com/newsroom/2026/03/apple-introduces-the-new-ipad-air-powered-by-m4/
# https://www.apple.com/newsroom/2025/10/apple-introduces-the-powerful-new-ipad-pro-with-the-m5-chip/
# RUB prices and stock below are demonstration values, not live retail prices.
IPADS = [
    {
        'slug': 'ipad-air-11-m4', 'name': 'iPad Air 11 (M4)',
        'release_date': date(2026, 3, 11),
        'description': 'Лёгкий планшет с чипом M4 для учёбы, работы и творчества. Поддерживает Apple Pencil Pro и Magic Keyboard.',
        'specifications': {'Процессор': 'Apple M4, 8 ядер CPU / 9 ядер GPU', 'Экран': '11 дюймов', 'Оперативная память': '12 ГБ', 'Связь': 'Wi-Fi 7, Bluetooth 6', 'Аксессуары': 'Apple Pencil Pro, Magic Keyboard'},
        'variants': [('Голубой', '128 ГБ', '69990.00', 6), ('Серый космос', '256 ГБ', '79990.00', 3)],
    },
    {
        'slug': 'ipad-pro-11-m5', 'name': 'iPad Pro 11 (M5)',
        'release_date': date(2025, 10, 22),
        'description': 'Планшет с чипом M5 и OLED-дисплеем Ultra Retina XDR для графики, монтажа и многозадачности.',
        'specifications': {'Процессор': 'Apple M5', 'Экран': '11 дюймов, Ultra Retina XDR OLED, ProMotion', 'Связь': 'Wi-Fi 7, Bluetooth 6', 'Толщина': '5,3 мм', 'Аксессуары': 'Apple Pencil Pro, Magic Keyboard'},
        'variants': [('Чёрный космос', '256 ГБ', '109990.00', 4), ('Серебристый', '512 ГБ', '129990.00', 0)],
    },
]


def add_ipads(apps, schema_editor):
    alias = schema_editor.connection.alias
    Product = apps.get_model('catalog', 'Product')
    # This is a catalog update; avoid populating empty installations/test databases.
    if not Product.objects.using(alias).exists():
        return
    Category = apps.get_model('catalog', 'Category')
    Variant = apps.get_model('catalog', 'ProductVariant')
    category, _ = Category.objects.using(alias).get_or_create(slug='ipad', defaults={'name': 'iPad'})
    for item in IPADS:
        values = {key: value for key, value in item.items() if key != 'variants'}
        slug = values.pop('slug')
        product, created = Product.objects.using(alias).get_or_create(slug=slug, defaults={'category': category, **values})
        if created:
            for color, memory, price, stock in item['variants']:
                Variant.objects.using(alias).create(product=product, color=color, memory=memory, price=Decimal(price), stock=stock)


class Migration(migrations.Migration):
    dependencies = [('catalog', '0005_product_release_date')]
    operations = [migrations.RunPython(add_ipads, migrations.RunPython.noop)]
