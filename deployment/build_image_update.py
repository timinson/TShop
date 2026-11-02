"""Export only current product image mappings and their files, never database fixtures."""
import hashlib
from io import BytesIO
import json
import os
import re
from pathlib import Path
import sys
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def build():
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    from catalog.models import Product
    from PIL import Image

    media = Path(settings.MEDIA_ROOT).resolve()
    products = []
    images = {}
    for product in Product.objects.order_by('pk'):
        if not product.image:
            continue
        path = media / product.image.name
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError(f'Symlink image rejected: {product.slug}')
        path = path.resolve()
        if not path.is_relative_to(media) or not path.is_file():
            raise ValueError(f'Missing or unsafe image: {product.slug}')
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError(f'Image exceeds 5 MB: {product.slug}')
        data = path.read_bytes()
        with Image.open(BytesIO(data)) as picture:
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(picture.format)
            picture.verify()
        if not extension:
            raise ValueError(f'Unsupported image: {product.slug}')
        digest = hashlib.sha256(data).hexdigest()
        name = f'images/{digest}.{extension}'
        images[name] = data
        label = re.sub(r'[^A-Za-z0-9_-]+', '_', product.name).strip('_')
        if not label:
            label = product.slug.replace('-', '_')
        today = datetime.now(ZoneInfo('Asia/Yekaterinburg')).strftime('%Y-%m-%d')
        products.append({'slug': product.slug, 'image': name, 'sha256': digest,
                         'filename': f'{label}_{today}.{extension}'})
    if not products:
        raise ValueError('No product images to export')
    if len(images) + 1 > 200 or sum(map(len, images.values())) > 99 * 1024 * 1024:
        raise ValueError('Image package exceeds importer limits')
    release = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    output = ROOT / 'deployment' / f'shop-images-{release}.zip'
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps({'format': 1, 'products': products}, ensure_ascii=False))
        for name, data in images.items():
            archive.writestr(name, data)
    print(f'Archive: {output}\nProducts: {len(products)}; unique images: {len(images)}')
    return output


if __name__ == '__main__':
    build()
