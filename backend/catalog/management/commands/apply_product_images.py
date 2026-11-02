"""Apply a bounded, hash-verified image-only release to existing products."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from uuid import uuid4
import zipfile

from PIL import Image
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import Product


IMAGE_NAME = re.compile(r'images/([a-f0-9]{64})\.(jpg|png|webp)\Z')
DISPLAY_NAME = re.compile(r'[A-Za-z0-9_-]+_\d{4}-\d{2}-\d{2}(?:_\d+)?\.(jpg|png|webp)\Z')
MAX_IMAGE = 5 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024


def read_package(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(infos) > 200 or len(set(names)) != len(names):
            raise ValueError('Invalid archive member count or duplicate members')
        if sum(item.file_size for item in infos) > MAX_TOTAL:
            raise ValueError('Archive exceeds size limit')
        for item in infos:
            parts = PurePosixPath(item.filename).parts
            if (item.is_dir() or '\\' in item.filename or item.filename.startswith('/')
                    or any(part in ('.', '..') for part in parts)
                    or stat.S_ISLNK(item.external_attr >> 16)
                    or (item.filename != 'manifest.json' and not IMAGE_NAME.fullmatch(item.filename))):
                raise ValueError('Unsafe or unexpected archive member')
            if item.file_size > MAX_IMAGE:
                raise ValueError('Archive member exceeds size limit')
        manifest = json.loads(archive.read('manifest.json'))
        if not isinstance(manifest, dict) or manifest.get('format') != 1:
            raise ValueError('Unsupported manifest')
        products = manifest.get('products')
        if not isinstance(products, list) or not products or len(products) > 199:
            raise ValueError('Invalid product list')
        slugs, expected, payload = set(), {'manifest.json'}, {}
        for row in products:
            if not isinstance(row, dict) or set(row) not in ({'slug', 'image', 'sha256'}, {'slug', 'image', 'sha256', 'filename'}):
                raise ValueError('Invalid product entry')
            slug, name, digest = row['slug'], row['image'], row['sha256']
            if not isinstance(slug, str) or not slug or slug in slugs:
                raise ValueError('Missing or duplicate product slug')
            match = IMAGE_NAME.fullmatch(name) if isinstance(name, str) else None
            if not match or digest != match[1]:
                raise ValueError('Invalid image name or digest')
            if 'filename' in row:
                filename = row['filename']
                display_match = DISPLAY_NAME.fullmatch(filename) if isinstance(filename, str) else None
                if not display_match or display_match[1] != match[2]:
                    raise ValueError('Invalid display filename')
            slugs.add(slug)
            expected.add(name)
            if name not in payload:
                data = archive.read(name)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError('Image digest mismatch')
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != {'jpg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP'}[match[2]]:
                        raise ValueError('Image format mismatch')
                    image.verify()
                payload[name] = data
        if set(names) != expected:
            raise ValueError('Unexpected or missing archive members')
        return products, payload


class Command(BaseCommand):
    help = 'Replace images of existing products from a verified image-only ZIP.'

    def add_arguments(self, parser):
        parser.add_argument('archive')
        parser.add_argument('--check-only', action='store_true')

    def handle(self, *args, **options):
        try:
            self.apply(options['archive'], options['check_only'])
        except (ValueError, KeyError, OSError, zipfile.BadZipFile, Image.DecompressionBombError) as exc:
            raise CommandError('Image update rejected: invalid archive, image, or filesystem state.') from exc

    def apply(self, archive, check_only):
        rows, payload = read_package(archive)
        with transaction.atomic():
            products = {p.slug: p for p in Product.objects.select_for_update().filter(slug__in=[r['slug'] for r in rows])}
            if set(products) != {r['slug'] for r in rows}:
                raise CommandError('Image update rejected: some product slugs do not exist; no products created.')
            root = Path(settings.MEDIA_ROOT).resolve()
            targets = {}
            reserved = {}
            for row in rows:
                filename = row.get('filename', 'deploy-' + row['image'].split('/')[-1])
                original = Path(filename)
                suffix = 1
                while True:
                    name = 'products/' + filename
                    target = root / name
                    if not target.resolve().is_relative_to(root) or target.is_symlink():
                        raise ValueError('Unsafe media target')
                    occupied = reserved.get(name)
                    if occupied is None and target.exists():
                        occupied = hashlib.sha256(target.read_bytes()).hexdigest()
                    if occupied is None or occupied == row['sha256']:
                        break
                    if 'filename' not in row:
                        raise ValueError('Existing media differs')
                    suffix += 1
                    filename = f'{original.stem}_{suffix}{original.suffix}'
                reserved[name] = row['sha256']
                targets[row['slug']] = (name, target)
            if check_only:
                self.stdout.write(f'CHECK OK: {len(rows)} existing products; no changes made')
                return
            backup_dir = Path(settings.BASE_DIR).parent / 'image-backups'
            backup_dir.mkdir(mode=0o700, exist_ok=True)
            if backup_dir.is_symlink():
                raise ValueError('Unsafe backup directory')
            backup = backup_dir / (timezone.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex + '.json')
            with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
                json.dump({'products': [{'slug': p.slug, 'image': p.image.name, 'image_url': p.image_url} for p in products.values()]}, stream, ensure_ascii=False, indent=2)
            for row in rows:
                name, target = targets[row['slug']]
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    with target.open('xb') as stream:
                        stream.write(payload[row['image']])
                Product.objects.filter(pk=products[row['slug']].pk).update(image=name)
        self.stdout.write(f'IMAGES UPDATED: {len(rows)} existing products; old images retained; backup: {backup}')
