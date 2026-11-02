"""Rollback checks against isolated fake hosting files; no external requests."""
import json
from pathlib import Path
import tempfile
import unittest

from rollback_update import rollback


class RollbackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.backup = self.home / 'shop-updates/new-release-20261027-123456'
        self.app = self.home / 'shop/backend'
        self.public = self.home / 'www/shop.example.com'
        for root, files in [
            (self.backup, {'backend/manage.py': '# old', 'backend/release.json': json.dumps({'release': 'old-release'}),
                           'backend/requirements-hosting.txt': 'Django==5.2', 'backend/.env': 'old secret',
                           'public/index.html': 'old page', 'public/passenger_wsgi.py': '# old wsgi',
                           'original.htaccess': '# original'}),
            (self.home, {'shop/backend/manage.py': '# new', 'shop/backend/.env': 'current secret',
                         'shop/backend/requirements-hosting.txt': 'Django==5.2',
                         'shop/backend/orders/migrations/0006_order_tracking_token.py': '# keep migration',
                         'shop/data/db.sqlite3': 'current orders', 'shop-venv/bin/python': '# interpreter',
                         'www/shop.example.com/.htaccess': '# original', 'www/shop.example.com/index.html': 'new page',
                         'www/shop.example.com/media/photo.jpg': 'current photo'})]:
            for name, value in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding='utf-8')
        self.commands = []

    def run_rollback(self, **options):
        parameters = dict(run_command=lambda command, cwd, log: self.commands.append(command),
                          maintenance_check=lambda: True, health_check=lambda release: release == 'old-release',
                          sleep=lambda seconds: None)
        parameters.update(options)
        return rollback(self.backup, self.home, **parameters)

    def test_restores_code_preserves_data_environment_and_migrations(self):
        self.run_rollback()
        self.assertEqual((self.app / 'manage.py').read_text(), '# old')
        self.assertEqual((self.public / 'index.html').read_text(), 'old page')
        self.assertEqual((self.app / '.env').read_text(), 'current secret')
        self.assertEqual((self.home / 'shop/data/db.sqlite3').read_text(), 'current orders')
        self.assertEqual((self.public / 'media/photo.jpg').read_text(), 'current photo')
        self.assertTrue((self.app / 'orders/migrations/0006_order_tracking_token.py').exists())
        self.assertFalse((self.home / 'shop/maintenance.flag').exists())
        self.assertFalse(any('migrate' in command for command in self.commands))

    def test_check_only_has_no_side_effects(self):
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.run_rollback(check_only=True)
        self.assertEqual(before, {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()})
        self.assertEqual(self.commands, [])

    def test_health_failure_keeps_maintenance(self):
        with self.assertRaises(RuntimeError):
            self.run_rollback(health_check=lambda release: False)
        self.assertTrue((self.home / 'shop/maintenance.flag').exists())
        self.assertTrue((self.public / '.htaccess').read_bytes().startswith(b'# SHOP UPDATE MAINTENANCE'))
        self.assertFalse((self.home / 'shop-updates/.lock').exists())

    def test_dependency_difference_is_rejected_before_writes(self):
        (self.app / 'requirements-hosting.txt').write_text('different')
        with self.assertRaisesRegex(ValueError, 'Dependencies'):
            self.run_rollback()
        self.assertEqual((self.public / '.htaccess').read_text(), '# original')

    def test_backup_outside_updates_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'direct directory'):
            rollback(self.home, self.home)

    def test_new_dependency_file_is_rejected(self):
        (self.app / 'requirements-extra.txt').write_text('new package')
        with self.assertRaisesRegex(ValueError, 'absent from backup'):
            self.run_rollback()

    def test_missing_hosting_requirements_is_rejected(self):
        (self.backup / 'backend/requirements-hosting.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'Incomplete backup'):
            self.run_rollback()

    def test_foreign_maintenance_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.run_rollback(health_check=lambda release: False)
        (self.home / 'shop/maintenance.flag').write_text('unrelated')
        with self.assertRaisesRegex(ValueError, 'different update'):
            self.run_rollback()

    def test_matching_failed_update_can_be_rolled_back(self):
        with self.assertRaises(RuntimeError):
            self.run_rollback(health_check=lambda release: False)
        (self.home / 'shop/maintenance.flag').write_text('new-release')
        self.run_rollback()
        self.assertFalse((self.home / 'shop/maintenance.flag').exists())


if __name__ == '__main__':
    unittest.main()
