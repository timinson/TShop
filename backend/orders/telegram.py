"""Telegram delivery. Exception text/URLs are deliberately never persisted."""
import json
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

CLIENT_LINK_TEXT = 'Ссылка для клиента'


class DeliveryError(Exception):
    def __init__(self, code, retry_after=0):
        super().__init__(code)
        self.code = code
        self.retry_after = min(86400, max(0, retry_after))


def message_for(order):
    header = f'Новый заказ №{order.pk}\n{timezone.localtime(order.created_at):%d.%m.%Y %H:%M}\n\n'
    footer = f'\nИтого: {order.total:.2f} ₽\n\n{CLIENT_LINK_TEXT}'
    # Count UTF-16 units conservatively: Telegram's limit must also fit emoji.
    budget = 3900 - len((header + footer).encode('utf-16-le')) // 2
    rows = []
    for item in order.items.all():
        row = f'{item.product_name} / {item.color}'
        if item.memory:
            row += f' / {item.memory}'
        row += f' × {item.quantity} — {item.unit_price:.2f} ₽\n'
        size = len(row.encode('utf-16-le')) // 2
        if size > budget:
            rows.append('… остальные позиции — в админке\n')
            break
        rows.append(row)
        budget -= size
    return header + ''.join(rows) + footer


def send_order(order):
    token = settings.TELEGRAM_BOT_TOKEN
    payload = {'chat_id': settings.TELEGRAM_CHAT_ID, 'text': message_for(order)}
    site = settings.SITE_URL.rstrip('/')
    # Explicit entities keep product names literal, including HTML and emoji.
    prefix = payload['text'][:-len(CLIENT_LINK_TEXT)]
    payload['entities'] = [{
        'type': 'text_link',
        'offset': len(prefix.encode('utf-16-le')) // 2,
        'length': len(CLIENT_LINK_TEXT.encode('utf-16-le')) // 2,
        'url': f'{site}/orders/{order.ensure_tracking_token()}',
    }]
    payload['link_preview_options'] = {'is_disabled': True}
    payload['reply_markup'] = {'inline_keyboard': [[{
        'text': 'Открыть заказ', 'url': f'{site}/admin/orders/order/{order.pk}/change/'
    }]]}
    request = urllib.request.Request(
        f'https://api.telegram.org/bot{token}/sendMessage',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read(65537)
    except urllib.error.HTTPError as error:
        retry = 0
        if error.code == 429:
            try:
                data = json.loads(error.read(65537))
                value = data.get('parameters', {}).get('retry_after', 0)
                if isinstance(value, int):
                    retry = value
            except Exception:
                pass
        raise DeliveryError(f'http_{error.code}', retry) from None
    except Exception:
        raise DeliveryError('network_error') from None
    try:
        if len(raw) > 65536:
            raise ValueError
        data = json.loads(raw)
        result = data.get('result')
        if data.get('ok') is not True or not isinstance(result, dict):
            raise ValueError
        message_id = result.get('message_id')
        if type(message_id) is not int:
            raise ValueError
        return message_id
    except (ValueError, TypeError, AttributeError):
        raise DeliveryError('invalid_response') from None
