import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

from PIL import Image
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Category, Product, ProductVariant


class ImageUpdateTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.settings_override = self.settings(BASE_DIR=self.root / 'backend', MEDIA_ROOT=self.root / 'media')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        category = Category.objects.create(name='Phone', slug='phone')
        self.product = Product.objects.create(category=category, slug='phone', name='Phone', image='products/old.jpg', image_url='https://example.com/image.jpg')
        self.variant = ProductVariant.objects.create(product=self.product, color='Black', price='100', stock=7)
        stream = io.BytesIO()
        Image.new('RGB', (2, 2)).save(stream, format='PNG')
        self.data = stream.getvalue()
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.name = f'images/{self.digest}.png'

    def package(self, slug='phone', extra=None, data=None, filename=None):
        path = self.root / 'update.zip'
        row = {'slug': slug, 'image': self.name, 'sha256': self.digest}
        if filename is not None:
            row['filename'] = filename
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('manifest.json', json.dumps({'format': 1, 'products': [row]}))
            archive.writestr(self.name, self.data if data is None else data)
            if extra:
                archive.writestr(extra, 'bad')
        return path

    def run_command(self, path, **kwargs):
        call_command('apply_product_images', str(path), stdout=io.StringIO(), **kwargs)

    def test_updates_only_image_preserves_stock_and_other_fields_and_backs_up(self):
        from orders.models import Order
        order_count = Order.objects.count()
        self.run_command(self.package())
        self.product.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(self.product.image.name, f'products/deploy-{self.digest}.png')
        self.assertEqual(self.product.image_url, 'https://example.com/image.jpg')
        self.assertEqual(self.variant.stock, 7)
        self.assertEqual(Order.objects.count(), order_count)
        self.assertEqual(Product.objects.count(), 1)
        backup = json.loads(next((self.root / 'image-backups').glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(backup['products'][0]['image'], 'products/old.jpg')
        self.assertEqual((self.root / 'media' / self.product.image.name).read_bytes(), self.data)

    def test_check_only_has_no_filesystem_or_database_changes(self):
        self.run_command(self.package(), check_only=True)
        self.product.refresh_from_db()
        self.assertEqual(self.product.image.name, 'products/old.jpg')
        self.assertFalse((self.root / 'media').exists())
        self.assertFalse((self.root / 'image-backups').exists())

    def test_missing_slug_never_creates_product(self):
        with self.assertRaises(CommandError):
            self.run_command(self.package(slug='missing'))
        self.assertEqual(Product.objects.count(), 1)
        self.assertFalse((self.root / 'image-backups').exists())

    def test_rejects_extra_paths_bad_hash_and_non_image(self):
        for extra, data in [('../escape', None), ('unexpected.txt', None), (None, b'bad')]:
            with self.subTest(extra=extra, data=data), self.assertRaises(CommandError):
                self.run_command(self.package(extra=extra, data=data))
        self.data = b'not an image'
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.name = f'images/{self.digest}.png'
        with self.assertRaises(CommandError):
            self.run_command(self.package())
        self.product.refresh_from_db()
        self.assertEqual(self.product.image.name, 'products/old.jpg')

    def test_existing_different_media_never_overwritten(self):
        target = self.root / 'media' / f'products/deploy-{self.digest}.png'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing')
        with self.assertRaises(CommandError):
            self.run_command(self.package())
        self.assertEqual(target.read_bytes(), b'existing')

    def test_product_date_filename_and_collision_keep_old_file(self):
        filename = 'iPhone_16_2026-10-23.png'
        target = self.root / 'media' / 'products' / filename
        target.parent.mkdir(parents=True)
        target.write_bytes(b'old photo')
        self.run_command(self.package(filename=filename))
        self.product.refresh_from_db()
        self.assertEqual(self.product.image.name, 'products/iPhone_16_2026-10-23_2.png')
        self.assertEqual(target.read_bytes(), b'old photo')
        self.assertEqual((target.parent / 'iPhone_16_2026-10-23_2.png').read_bytes(), self.data)
        # Repeating the update reuses matching content rather than adding copies.
        self.run_command(self.package(filename=filename))
        self.assertEqual(len(list(target.parent.iterdir())), 2)

    def test_product_filename_without_collision(self):
        self.run_command(self.package(filename='iPhone_16_2026-10-23.png'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.image.name, 'products/iPhone_16_2026-10-23.png')

    def test_invalid_filename_and_extension_rejected(self):
        for filename in ('../iPhone_2026-10-23.png', 'iPhone_2026-10-23.jpg', '/iPhone_2026-10-23.png', 'iPhone.png'):
            with self.subTest(filename=filename), self.assertRaises(CommandError):
                self.run_command(self.package(filename=filename))
        self.assertFalse((self.root / 'media').exists())
