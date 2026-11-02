from django.test import SimpleTestCase
from django.test import override_settings
from django.urls import reverse
from pathlib import Path
from tempfile import TemporaryDirectory


class HealthTests(SimpleTestCase):
    def test_health_contract(self):
        response = self.client.get(reverse('health'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'service': 'marketplace-api'})

    def test_health_rejects_post(self):
        self.assertEqual(self.client.post(reverse('health')).status_code, 405)

    def test_maintenance_blocks_writes_but_health_stays_accessible(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'maintenance.flag').write_text('release-test')
            with override_settings(BASE_DIR=root / 'backend'):
                response = self.client.post('/api/orders/', {})
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response['Retry-After'], '60')
                self.assertEqual(self.client.get('/admin/').status_code, 503)
                self.assertEqual(self.client.get(reverse('health')).status_code, 200)
            (root / 'maintenance.flag').unlink()
