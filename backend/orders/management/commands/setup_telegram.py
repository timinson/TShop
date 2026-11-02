"""Configure a bot without exposing its token in shell arguments/history."""
import getpass
import json
import os
import tempfile
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def call_api(token, method):
    request = urllib.request.Request(
        f'https://api.telegram.org/bot{token}/{method}',
        data=b'{"timeout":0,"limit":100}',
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read(1024 * 1024))
        if not data.get('ok'):
            raise ValueError('API rejected request')
        return data['result']
    except Exception:
        # urllib exceptions contain the URL, including the secret token.
        raise CommandError('Telegram не ответил или отклонил запрос. Проверьте токен и отсутствие webhook.') from None


class Command(BaseCommand):
    help = 'Безопасно записать токен бота и личный chat_id в приватный .env.'

    def handle(self, *args, **options):
        env = Path(settings.BASE_DIR) / '.env'
        if not env.is_file() or env.is_symlink():
            raise CommandError('Ожидается существующий приватный файл backend/.env.')
        token = getpass.getpass('New bot token (hidden): ').strip()
        if not token or ':' not in token or any(character.isspace() for character in token):
            raise CommandError('Некорректный формат токена.')
        bot = call_api(token, 'getMe')
        chats = {}
        for update in call_api(token, 'getUpdates'):
            message = update.get('message', {})
            chat = message.get('chat', {})
            if chat.get('type') == 'private' and message.get('text') == '/start':
                chats[str(chat['id'])] = chat
        if not chats:
            raise CommandError('Напишите боту /start ещё раз и повторите команду. Настройки не изменены.')
        if len(chats) == 1:
            chat_id = next(iter(chats))
        else:
            self.stdout.write('Private chats with /start: ' + ', '.join(chats))
            chat_id = input('Your chat ID from the list: ').strip()
            if chat_id not in chats:
                raise CommandError('Чат не найден в списке.')
        replacements = {'TELEGRAM_BOT_TOKEN': token, 'TELEGRAM_CHAT_ID': chat_id}
        lines = env.read_text(encoding='utf-8').splitlines()
        lines = [line for line in lines if line.split('=', 1)[0].strip() not in replacements]
        lines.extend(f'{key}={value}' for key, value in replacements.items())
        descriptor, temporary = tempfile.mkstemp(dir=env.parent, prefix='.telegram-')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write('\n'.join(lines) + '\n')
            Path(temporary).chmod(0o600)
            os.replace(temporary, env)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
        self.stdout.write(self.style.SUCCESS(
            f'Настроен @{bot.get("username", "bot")}, личный чат {chat_id}. Токен сохранён без вывода.'
        ))
