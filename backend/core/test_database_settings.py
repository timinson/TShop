import os
from pathlib import Path
import runpy
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    def settings_for(self, **values):
        with patch.dict(os.environ, {'SECRET_KEY': 'settings-test-only', **values}, clear=True), patch('dotenv.load_dotenv'):
            return runpy.run_path(str(Path(__file__).resolve().parents[1] / 'config/settings.py'))

    def test_sqlite_remains_default(self):
        settings = self.settings_for(DATABASE_PATH='local.sqlite3')
        self.assertEqual(settings['DATABASES']['default']['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(settings['DATABASES']['default']['NAME'], Path('local.sqlite3'))

    def test_mysql_uses_private_environment_and_strict_mode(self):
        settings = self.settings_for(DB_ENGINE='mysql', MYSQL_DATABASE='test_shop', MYSQL_USER='test_user', MYSQL_PASSWORD='dummy')
        database = settings['DATABASES']['default']
        self.assertEqual(database['ENGINE'], 'django.db.backends.mysql')
        self.assertEqual(database['NAME'], 'test_shop')
        self.assertEqual(database['HOST'], '127.0.0.1')
        self.assertEqual(database['PORT'], 3306)
        self.assertEqual(database['OPTIONS']['charset'], 'utf8mb4')
        self.assertIn('STRICT_TRANS_TABLES', database['OPTIONS']['init_command'])
        self.assertEqual(database['OPTIONS']['isolation_level'], 'read committed')

    def test_mysql_requires_credentials_and_valid_port(self):
        with self.assertRaises(ImproperlyConfigured):
            self.settings_for(DB_ENGINE='mysql')
        for port in ['invalid', '0', '65536']:
            with self.subTest(port=port), self.assertRaises(ImproperlyConfigured):
                self.settings_for(DB_ENGINE='mysql', MYSQL_DATABASE='test_shop', MYSQL_USER='test_user', MYSQL_PASSWORD='dummy', MYSQL_PORT=port)

    def test_unknown_engine_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            self.settings_for(DB_ENGINE='unknown')

    def test_mysql_rehearsal_alias_keeps_sqlite_default(self):
        settings = self.settings_for(MYSQL_MIGRATION_ENABLED='1', MYSQL_DATABASE='test_shop', MYSQL_USER='test_user', MYSQL_PASSWORD='dummy')
        self.assertEqual(settings['DATABASES']['default']['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(settings['DATABASES']['mysql_target']['ENGINE'], 'django.db.backends.mysql')
        self.assertNotIn('mysql_target', self.settings_for()['DATABASES'])
