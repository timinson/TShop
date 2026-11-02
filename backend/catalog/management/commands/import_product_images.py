"""Import only photographs for products already present in the database."""
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import urlopen

from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from catalog.models import Product


class Command(BaseCommand):
    help = 'Заполнить пустые изображения существующих товаров по проверенному списку aw-store.ru.'

    def handle(self, *args, **options):
        manifest_path = settings.BASE_DIR.parent / 'docs' / 'aw-store-images.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        before = list(Product.objects.order_by('pk').values())
        report = []
        for entry in manifest:
            product = Product.objects.filter(slug=entry['slug']).first()
            if not product or product.image:
                report.append({'slug': entry['slug'], 'status': 'preserved' if product else 'not_found'})
                continue
            if entry.get('copy_from'):
                source = Product.objects.get(slug=entry['copy_from'])
                if not source.image:
                    raise CommandError(f'Нет исходного изображения: {source.slug}')
                product.image = source.image.name
                product.save(update_fields=['image'])
            else:
                parts = urlsplit(entry['image_url'])
                if parts.scheme != 'https' or parts.netloc != 'aw-store.ru':
                    raise CommandError('Разрешены только HTTPS-изображения aw-store.ru.')
                url = urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe='/%'), parts.query, ''))
                with urlopen(url, timeout=25) as response:
                    if urlsplit(response.url).netloc != 'aw-store.ru':
                        raise CommandError('Источник перенаправил изображение на другой сайт.')
                    data = response.read(5 * 1024 * 1024 + 1)
                if len(data) > 5 * 1024 * 1024:
                    raise CommandError(f'Файл больше 5 МБ: {product.slug}')
                with Image.open(BytesIO(data)) as image:
                    extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(image.format)
                    image.verify()
                if not extension:
                    raise CommandError(f'Неподдерживаемое изображение: {product.slug}')
                product.image.save(f'{product.slug}.{extension}', ContentFile(data), save=False)
                product.save(update_fields=['image'])
            report.append({'slug': product.slug, 'status': 'added', 'image': product.image.name, 'note': entry.get('note', '')})
            self.stdout.write(f'Добавлено: {product.name}')
        after = list(Product.objects.order_by('pk').values())
        strip_image = lambda rows: [{key: value for key, value in row.items() if key != 'image'} for row in rows]
        if strip_image(before) != strip_image(after):
            raise CommandError('Обнаружено изменение данных помимо изображений.')
        output = settings.BASE_DIR.parent / 'docs' / 'aw-store-image-report.json'
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Готово. Товаров: {len(after)}. Другие поля сохранены.'))
