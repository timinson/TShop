"""Build a deployment archive without local secrets, orders or personal notes."""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from apply_update import allowed

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.core import serializers
from catalog.models import Category, Product, ProductVariant
from django.conf import settings

subprocess.run(['npm.cmd' if os.name == 'nt' else 'npm', 'run', 'build'], cwd=ROOT / 'frontend', check=True)
output = ROOT / 'deployment/shop-timinson.zip'
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in (ROOT / 'backend').rglob('*'):
        relative = path.relative_to(ROOT / 'backend')
        if not path.is_file() or path.is_symlink() or '__pycache__' in relative.parts:
            continue
        if not allowed('backend/' + relative.as_posix()):
            continue
        if path.name in ('tests.py', 'test_images.py', 'import_product_images.py'):
            continue
        archive.write(path, 'shop/backend/' + relative.as_posix())
    objects = [*Category.objects.all(), *Product.objects.all(), *ProductVariant.objects.all()]
    archive.writestr('shop/catalog.json', serializers.serialize('json', objects, ensure_ascii=False))
    for path in (ROOT / 'frontend/dist').rglob('*'):
        if path.is_file():
            archive.write(path, 'public/' + path.relative_to(ROOT / 'frontend/dist').as_posix())
    images = set(Product.objects.exclude(image='').values_list('image', flat=True))
    for name in images:
        path = (Path(settings.MEDIA_ROOT) / name).resolve()
        if not path.is_relative_to(Path(settings.MEDIA_ROOT).resolve()) or not path.is_file():
            raise RuntimeError(f'Invalid or missing image: {name}')
        archive.write(path, 'public/media/' + name)
    archive.write(ROOT / 'deployment/passenger_wsgi.py', 'public/passenger_wsgi.py')
    archive.write(ROOT / 'deployment/public.htaccess', 'public/.htaccess')
    archive.write(ROOT / 'deployment/install.sh', 'shop/install.sh')
with zipfile.ZipFile(output) as archive:
    names = archive.namelist()
    assert not any(name.endswith(('.md', '.sqlite3', '.env')) or '/docs/' in name for name in names)
    fixture = json.loads(archive.read('shop/catalog.json'))
    assert {item['model'] for item in fixture} <= {'catalog.category', 'catalog.product', 'catalog.productvariant'}
    print(f'Package: {output}; files: {len(names)}; products: {Product.objects.count()}')
