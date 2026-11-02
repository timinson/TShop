from datetime import date

from django.db import migrations, models


# First availability dates (not announcement/pre-order dates), Apple Newsroom.
# https://www.apple.com/newsroom/2024/09/apple-introduces-iphone-16-and-iphone-16-plus/
# https://www.apple.com/newsroom/2024/09/apple-debuts-iphone-16-pro-and-iphone-16-pro-max/
# https://www.apple.com/newsroom/2025/02/upgrade-to-iphone-16e-a-powerful-new-member-of-the-iphone-16-family/
# https://www.apple.com/newsroom/2025/09/apple-debuts-iphone-17/
# https://www.apple.com/newsroom/2025/09/apple-unveils-iphone-17-pro-and-iphone-17-pro-max/
# https://www.apple.com/newsroom/2025/09/introducing-iphone-air-a-powerful-new-iphone-with-a-breakthrough-design/
# https://www.apple.com/newsroom/2026/03/apple-introduces-iphone-17e/
# https://www.apple.com/newsroom/2026/09/apple-debuts-iphone-18-pro-and-iphone-18-pro-max/
# https://www.apple.com/newsroom/2026/09/apple-unveils-iphone-duo/
# https://www.apple.com/newsroom/2025/03/apple-introduces-the-new-macbook-air-with-the-m4-chip-and-a-sky-blue-color/
# https://www.apple.com/newsroom/2024/10/new-macbook-pro-features-m4-family-of-chips-and-apple-intelligence/
# https://www.apple.com/newsroom/2024/09/introducing-apple-watch-series-10/
# https://www.apple.com/newsroom/2023/09/apple-unveils-apple-watch-ultra-2/
# https://www.apple.com/newsroom/2024/09/apple-introduces-airpods-4-and-a-hearing-health-experience-with-airpods-pro-2/
# https://www.apple.com/newsroom/2023/09/apple-upgrades-airpods-pro-2nd-generation-with-usb-c-charging/
RELEASE_DATES = {
    'iPhone 16': '2024-09-20',
    'iPhone 16 Plus': '2024-09-20',
    'iPhone 16 Pro': '2024-09-20',
    'iPhone 16 Pro Max': '2024-09-20',
    'iPhone 16e': '2025-02-28',
    'iPhone 17': '2025-09-19',
    'iPhone 17 Pro': '2025-09-19',
    'iPhone 17 Pro Max': '2025-09-19',
    'iPhone Air': '2025-09-19',
    'iPhone 17e': '2026-03-11',
    'iPhone 18 Pro': '2026-09-18',
    'iPhone 18 Pro Max': '2026-09-18',
    'iPhone Duo': '2026-10-23',
    'MacBook Air 13': '2025-03-12',  # Existing catalog: M4.
    'MacBook Pro 14': '2024-11-08',  # Existing catalog: M4.
    'Apple Watch Series 10': '2024-09-20',
    'Apple Watch Ultra 2': '2023-09-22',
    'AirPods 4': '2024-09-20',
    'AirPods Pro 2': '2023-09-22',  # Existing catalog: USB-C case.
}


def fill_release_dates(apps, schema_editor):
    Product = apps.get_model('catalog', 'Product')
    for name, value in RELEASE_DATES.items():
        Product.objects.using(schema_editor.connection.alias).filter(
            name=name, release_date__isnull=True,
        ).update(release_date=date.fromisoformat(value))


class Migration(migrations.Migration):
    dependencies = [('catalog', '0004_product_discount_percent')]

    operations = [
        migrations.AddField(
            model_name='product', name='release_date',
            field=models.DateField('Дата старта продаж', null=True, blank=True,
                help_text='Дата начала продаж модели. Используется для сортировки: сначала новые; без даты — в конце.'),
        ),
        migrations.RunPython(fill_release_dates, migrations.RunPython.noop),
    ]
