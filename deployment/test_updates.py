"""Isolated release and installer checks; no host connection or live data."""
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from types import SimpleNamespace

import apply_update
import build_update


class UpdateTests(unittest.TestCase):
    def test_mysql_update_requires_successful_backup_before_installing(self):
        self.write(self.app / '.env', '\n'.join([
            'DB_ENGINE=mysql', 'MYSQL_DATABASE=demo', 'MYSQL_USER=manager', 'MYSQL_PASSWORD=test-secret',
            f'STATIC_ROOT={self.public / "static"}', f'MEDIA_ROOT={self.public / "media"}',
        ]))
        self.db.unlink()
        config = {'MYSQL_HOST': '127.0.0.1', 'MYSQL_PORT': '3306', 'MYSQL_DATABASE': 'demo',
                  'MYSQL_USER': 'manager', 'MYSQL_PASSWORD': 'test-secret'}
        with patch.object(apply_update, 'mysql_config', return_value=config), \
                patch.object(apply_update, 'backup_mysql', side_effect=RuntimeError('Backup unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'Backup unavailable'):
                self.install()
        self.assertEqual((self.app / 'manage.py').read_text(), '# old')
        self.assertTrue((self.home / 'shop/maintenance.flag').exists())

    def test_mysql_backup_uses_private_options_and_removes_them(self):
        config = {'MYSQL_HOST': '127.0.0.1', 'MYSQL_PORT': '3306', 'MYSQL_DATABASE': 'demo',
                  'MYSQL_USER': 'manager', 'MYSQL_PASSWORD': 'test-secret"\\x'}
        backup = self.root / 'mysql-backup'
        backup.mkdir()
        seen = []
        def dump(command, **kwargs):
            self.assertNotIn(config['MYSQL_PASSWORD'], ' '.join(command))
            options = Path(command[1].split('=', 1)[1])
            self.assertTrue(options.is_file())
            seen.append(options)
            kwargs['stdout'].write(b'CREATE TABLE demo(id int);')
            return SimpleNamespace(returncode=0)
        log = io.StringIO()
        with patch.object(apply_update.shutil, 'which', return_value='/usr/bin/mysqldump'), \
                patch.object(apply_update.subprocess, 'run', side_effect=dump):
            apply_update.backup_mysql(config, backup, log)
        self.assertFalse(seen[0].exists())
        self.assertTrue((backup / 'database.sql').is_file())
        self.assertNotIn(config['MYSQL_PASSWORD'], log.getvalue())

    def test_mysql_backup_failure_cleans_credentials_and_has_no_complete_dump(self):
        config = {'MYSQL_HOST': '127.0.0.1', 'MYSQL_PORT': '3306', 'MYSQL_DATABASE': 'demo',
                  'MYSQL_USER': 'manager', 'MYSQL_PASSWORD': 'test-secret'}
        backup = self.root / 'mysql-backup'
        backup.mkdir()
        with patch.object(apply_update.shutil, 'which', return_value='/usr/bin/mysqldump'), \
                patch.object(apply_update.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, 'MySQL backup failed'):
                apply_update.backup_mysql(config, backup, io.StringIO())
        self.assertEqual(list(backup.glob('*.cnf')), [])
        self.assertFalse((backup / 'database.sql').exists())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.home = self.root / 'home'
        self.app = self.home / 'shop/backend'
        self.public = self.home / 'www/shop.example.com'
        self.db = self.home / 'shop/data/db.sqlite3'
        for base, files in [
            (self.source, {'backend/manage.py': '# new', 'backend/config/settings.py': '# settings',
                           'backend/requirements-hosting.txt': 'Django==5.2',
                           'backend/templates/admin/base_site.html': '{% extends "admin/base.html" %}',
                           'backend/core/static/shop_admin/theme.css': ':root { --primary: green; }',
                           'backend/core/static/shop_admin/analytics-graph.js': '// chart',
                           'backend/templates/admin/orders/analytics.html': '<main>Analytics</main>',
                           'backend/templates/private.html': 'PRIVATE',
                           'backend/core/static/other/secret.css': 'PRIVATE',
                           'frontend/dist/index.html': 'new html', 'frontend/dist/assets/app.js': 'new js',
                           'AGENTS.md': 'PRIVATE', 'backend/AGENTS.md': 'PRIVATE',
                           'frontend/dist/assets/AGENTS.md': 'PRIVATE', 'backend/docs/note.py': 'PRIVATE',
                           'deployment/passenger_wsgi.py': '# wsgi',
                           'backend/.env': 'PRIVATE', 'backend/db.sqlite3': 'PRIVATE',
                           'backend/media/photo.jpg': 'PRIVATE', 'docs/note.md': 'PRIVATE'}),
            (self.home, {'shop/backend/manage.py': '# old',
                         'shop/backend/requirements-hosting.txt': 'Django==5.2',
                         'shop-venv/bin/python': '# fake interpreter',
                         'www/shop.example.com/.htaccess': '# original',
                         'www/shop.example.com/index.html': 'old html',
                         'www/shop.example.com/media/photo.jpg': 'uploaded photo'})]:
            for name, value in files.items():
                self.write(base / name, value)
        self.write(self.app / '.env', '\n'.join(f'{key}={value}' for key, value in {
            'DATABASE_PATH': self.db, 'STATIC_ROOT': self.public / 'static',
            'MEDIA_ROOT': self.public / 'media'}.items()))
        self.db.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('create table durable (value text)')
            connection.execute("insert into durable values ('order preserved')")
        self.archive = build_update.build(self.source, self.root / 'update.zip', compile_frontend=False)
        self.commands = []

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')

    def command(self, command, cwd, log):
        self.commands.append(command)

    def install(self, **options):
        return apply_update.install(self.archive, self.home, run_command=self.command,
                                    health_check=lambda release: True, maintenance_check=lambda: True,
                                    sleep=lambda seconds: None, **options)

    def snapshot(self):
        return {p.relative_to(self.home).as_posix(): p.read_bytes()
                for p in self.home.rglob('*') if p.is_file()}

    def rewrite_archive(self, change):
        with zipfile.ZipFile(self.archive) as source:
            entries = {i.filename: (i, source.read(i)) for i in source.infolist()}
        change(entries)
        with zipfile.ZipFile(self.archive, 'w') as target:
            for info, data in entries.values():
                target.writestr(info, data)

    def test_builder_excludes_private_data_and_notes(self):
        with zipfile.ZipFile(self.archive) as package:
            names = package.namelist()
            self.assertIn('public/assets/app.js', names)
            self.assertIn('backend/config/settings.py', names)
            self.assertIn('backend/core/static/shop_admin/analytics-graph.js', names)
            self.assertIn('backend/templates/admin/orders/analytics.html', names)
            self.assertFalse(any('PRIVATE' in package.read(name).decode() for name in names))
        manifest, payload = apply_update.read_package(self.archive)
        self.assertEqual(json.loads(payload['backend/release.json'])['release'], manifest['release'])
        for name in ['AGENTS.md', 'backend/AGENTS.md', 'public/assets/AGENTS.md', 'backend/docs/note.py',
                     'backend/.env', 'backend/db.sqlite3', 'backend/media/photo.jpg']:
            with self.subTest(name=name):
                self.assertNotIn(name, payload)
                self.assertFalse(apply_update.allowed(name))

    def test_check_only_makes_no_changes(self):
        before = self.snapshot()
        self.install(check_only=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.commands, [])

    def test_admin_assets_are_packaged_and_installed_without_widening_static_access(self):
        _, payload = apply_update.read_package(self.archive)
        expected = ['backend/templates/admin/base_site.html', 'backend/core/static/shop_admin/theme.css',
                    'backend/templates/admin/orders/analytics.html', 'backend/core/static/shop_admin/analytics-graph.js']
        for name in expected:
            self.assertIn(name, payload)
        self.install()
        for name in expected:
            self.assertEqual((self.home / 'shop' / name).read_bytes(), payload[name])
        self.assertTrue(any('collectstatic' in command for command in self.commands))
        for name in ['backend/templates/private.html', 'backend/core/static/other/secret.css',
                     'backend/templates/admin/.hidden.html',
                     'backend/core/static/shop_admin/nested/theme.css', 'backend/core/static/shop_admin/script.txt']:
            with self.subTest(name=name):
                self.assertNotIn(name, payload)
                self.assertFalse(apply_update.allowed(name))

    def test_base_requirements_change_installs_dependencies(self):
        self.write(self.app / 'requirements.txt', 'old dependency')
        self.write(self.source / 'backend/requirements.txt', 'new dependency')
        self.archive = build_update.build(self.source, self.root / 'deps.zip', compile_frontend=False)
        self.install()
        self.assertTrue(any('pip' in command for command in self.commands))

    def test_unconfirmed_maintenance_never_writes_application(self):
        with self.assertRaises(RuntimeError):
            apply_update.install(self.archive, self.home, run_command=self.command,
                                 maintenance_check=lambda: False, sleep=lambda _: None)
        self.assertEqual((self.app / 'manage.py').read_text(), '# old')
        self.assertEqual(self.commands, [])

    def test_success_preserves_data_and_creates_consistent_backup(self):
        env = (self.app / '.env').read_bytes()
        backup = self.install()
        self.assertEqual((self.app / 'manage.py').read_text(), '# new')
        self.assertEqual((self.app / '.env').read_bytes(), env)
        self.assertEqual((self.public / 'media/photo.jpg').read_text(), 'uploaded photo')
        self.assertEqual((self.public / '.htaccess').read_text(), '# original')
        self.assertFalse((self.home / 'shop/maintenance.flag').exists())
        self.assertFalse((self.home / 'shop-updates/.lock').exists())
        for database in [self.db, backup / 'db.sqlite3']:
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('select value from durable').fetchone()[0], 'order preserved')
        self.assertEqual((backup / 'backend/manage.py').read_text(), '# old')
        self.assertTrue(any('migrate' in c for c in self.commands))
        self.assertFalse(any('pip' in c for c in self.commands))

    def test_unsafe_packages_rejected_without_mutation(self):
        original = self.archive.read_bytes()
        cases = ['../escaped.py', 'backend/.env', 'public/assets/link.js', 'bad_hash']
        for case in cases:
            with self.subTest(case=case):
                self.archive.write_bytes(original)
                def modify(entries):
                    if case == 'bad_hash':
                        info, data = entries['backend/manage.py']
                        entries['backend/manage.py'] = (info, b'tampered')
                    else:
                        info = zipfile.ZipInfo(case)
                        if case.endswith('link.js'):
                            info.create_system = 3
                            info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        entries[case] = (info, b'bad')
                self.rewrite_archive(modify)
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.install()
                self.assertEqual(before, self.snapshot())

    def test_migration_failure_keeps_maintenance_and_does_not_revert_database(self):
        def fail(command, cwd, log):
            if 'migrate' in command:
                with closing(sqlite3.connect(self.db)) as connection, connection:
                    connection.execute("insert into durable values ('migration marker')")
                raise RuntimeError('simulated migration failure')
        with self.assertRaisesRegex(RuntimeError, 'migration failure'):
            apply_update.install(self.archive, self.home, run_command=fail,
                                 maintenance_check=lambda: True, sleep=lambda _: None)
        self.assertTrue((self.home / 'shop/maintenance.flag').exists())
        self.assertIn('SHOP UPDATE MAINTENANCE', (self.public / '.htaccess').read_text())
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('select count(*) from durable').fetchone()[0], 2)
        backup = next((self.home / 'shop-updates').glob('*/db.sqlite3'))
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute('select count(*) from durable').fetchone()[0], 1)

    def test_existing_lock_or_maintenance_is_not_removed(self):
        for path in [self.home / 'shop-updates/.lock', self.home / 'shop/maintenance.flag']:
            with self.subTest(path=path.name):
                if path.name == '.lock':
                    path.mkdir(parents=True)
                else:
                    self.write(path, 'previous update')
                before = self.snapshot()
                with self.assertRaises((ValueError, FileExistsError)):
                    self.install()
                self.assertTrue(path.exists())
                self.assertEqual(before, self.snapshot())
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()

    def test_health_requires_current_release(self):
        response = io.BytesIO(json.dumps({'status': 'ok', 'service': 'marketplace-api', 'release': 'old'}).encode())
        with patch.object(apply_update.urllib.request, 'urlopen', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'Worker release'):
                apply_update.verify_health('new')
        response = io.BytesIO(json.dumps({'status': 'ok', 'service': 'marketplace-api', 'release': 'new'}).encode())
        with patch.object(apply_update.urllib.request, 'urlopen', return_value=response):
            self.assertTrue(apply_update.verify_health('new'))

    def test_failed_health_keeps_maintenance(self):
        releases = []
        def unhealthy(release):
            releases.append(release)
            return False
        with self.assertRaisesRegex(RuntimeError, 'health check failed'):
            apply_update.install(self.archive, self.home, run_command=self.command,
                                 health_check=unhealthy, maintenance_check=lambda: True, sleep=lambda _: None)
        self.assertEqual(len(releases), 20)
        self.assertEqual(len(set(releases)), 1)
        self.assertTrue((self.home / 'shop/maintenance.flag').exists())


if __name__ == '__main__':
    unittest.main()
