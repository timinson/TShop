from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Category, Product


class ProductImageTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        settings = override_settings(MEDIA_ROOT=self.directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        user = get_user_model().objects.create_superuser(username='image-manager', password='test-password')
        self.client.force_login(user)
        category = Category.objects.create(name='Phone', slug='phone')
        self.product = Product.objects.create(category=category, name='Phone', slug='phone', image_url='https://example.com/fallback.jpg')

    def upload(self, image):
        return self.client.post(f'/admin/catalog/product/{self.product.pk}/change/', {
            'category': self.product.category_id, 'name': 'Phone', 'slug': 'phone',
            'description': 'Phone description', 'specifications': '{}', 'is_active': 'on',
            'image_url': self.product.image_url, 'image': image,
            'discount_percent': '0',
            'variants-TOTAL_FORMS': '0', 'variants-INITIAL_FORMS': '0',
            'variants-MIN_NUM_FORMS': '0', 'variants-MAX_NUM_FORMS': '1000',
            '_save': 'Save',
        })

    def test_admin_upload_is_saved_and_used_by_api(self):
        content = BytesIO()
        Image.new('RGB', (4, 4), 'green').save(content, format='PNG')
        response = self.upload(SimpleUploadedFile('photo.png', content.getvalue(), content_type='image/png'))
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertTrue(Path(self.product.image.path).is_file())
        self.assertTrue(self.product.image.url.startswith('/media/products/'))
        data = self.client.get('/api/products/phone/').json()
        self.assertEqual(data['image_url'], self.product.image.url)

    def test_invalid_image_is_rejected(self):
        response = self.upload(SimpleUploadedFile('bad.png', b'not an image', content_type='image/png'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('image', response.context['adminform'].form.errors)
        self.product.refresh_from_db()
        self.assertFalse(self.product.image)

    def test_legacy_url_fallback_and_size_limit(self):
        from django.core.exceptions import ValidationError
        from .validators import validate_image_size
        self.assertEqual(self.client.get('/api/products/phone/').json()['image_url'], self.product.image_url)
        with self.assertRaises(ValidationError):
            validate_image_size(SimpleUploadedFile('large.png', b'0' * (5 * 1024 * 1024 + 1)))
