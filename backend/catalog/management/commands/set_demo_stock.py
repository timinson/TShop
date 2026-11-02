from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Product


class Command(BaseCommand):
    help = 'Перезаписать остатки вариантов для локальной проверки: часть 0, остальные 1–10.'

    @transaction.atomic
    def handle(self, *args, **options):
        unavailable = {'iphone-duo', 'iphone-16-pro', 'iphone-17-pro', 'apple-watch-ultra-2', 'airpods-pro-2'}
        products = Product.objects.order_by('slug').prefetch_related('variants')
        available_count = unavailable_count = variant_count = 0
        for index, product in enumerate(products):
            variants = list(product.variants.all())
            for offset, variant in enumerate(variants):
                variant.stock = 0 if product.slug in unavailable else (index + offset) % 10 + 1
                # Leave a few unavailable configurations inside available products.
                if offset > 0 and index % 3 == 0:
                    variant.stock = 0
                variant.save(update_fields=['stock'])
                variant_count += 1
            if any(variant.stock > 0 for variant in variants):
                available_count += 1
            else:
                unavailable_count += 1
        self.stdout.write(self.style.SUCCESS(
            f'Остатки обновлены: {variant_count} вариантов, '
            f'{available_count} товаров в наличии, {unavailable_count} без наличия.'
        ))
