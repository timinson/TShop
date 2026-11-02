from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class TelegramSetupTests(SimpleTestCase):
    def test_setup_preserves_private_settings_without_printing_token(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            env = root / '.env'
            env.write_text('SECRET_KEY=existing-secret\nTELEGRAM_BOT_TOKEN=old\n')
            results = [{'username': 'shop_example_bot'}, [{'message': {'chat': {'id': 123, 'type': 'private'}, 'text': '/start'}}]]
            output = StringIO()
            with override_settings(BASE_DIR=root), patch('orders.management.commands.setup_telegram.getpass.getpass', return_value='123:fake-secret'), patch('orders.management.commands.setup_telegram.call_api', side_effect=results):
                call_command('setup_telegram', stdout=output)
            content = env.read_text()
            self.assertIn('SECRET_KEY=existing-secret', content)
            self.assertIn('TELEGRAM_BOT_TOKEN=123:fake-secret', content)
            self.assertIn('TELEGRAM_CHAT_ID=123', content)
            self.assertNotIn('fake-secret', output.getvalue())
            self.assertNotIn('existing-secret', output.getvalue())

    def test_no_start_does_not_change_env(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            env = root / '.env'
            env.write_text('SECRET_KEY=unchanged\n')
            with override_settings(BASE_DIR=root), patch('orders.management.commands.setup_telegram.getpass.getpass', return_value='123:fake'), patch('orders.management.commands.setup_telegram.call_api', side_effect=[{}, []]):
                with self.assertRaises(CommandError):
                    call_command('setup_telegram')
            self.assertEqual(env.read_text(), 'SECRET_KEY=unchanged\n')

    def test_api_exception_does_not_expose_token(self):
        from orders.management.commands.setup_telegram import call_api
        with patch('orders.management.commands.setup_telegram.urllib.request.urlopen', side_effect=RuntimeError('https://api.telegram.org/bot123:fake-secret/getMe')):
            with self.assertRaises(CommandError) as error:
                call_api('123:fake-secret', 'getMe')
        self.assertNotIn('fake-secret', str(error.exception))
