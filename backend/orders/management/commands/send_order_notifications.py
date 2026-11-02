import uuid
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q
from django.utils import timezone

from orders.models import OrderNotification
from orders.telegram import DeliveryError, send_order


class Command(BaseCommand):
    help = 'Send pending order Telegram notifications (suitable for CRON).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10)

    def handle(self, *args, **options):
        if (settings.BASE_DIR.parent / 'maintenance.flag').exists():
            self.stdout.write('Telegram: maintenance active; skipped')
            return
        if not getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or not getattr(settings, 'TELEGRAM_CHAT_ID', ''):
            raise CommandError('Telegram is not configured; no notifications claimed.')
        limit = options['limit']
        if not 1 <= limit <= 50:
            raise CommandError('Limit must be between 1 and 50.')
        now = timezone.now()
        available = Q(locked_until__isnull=True) | Q(locked_until__lte=now)
        ids = list(OrderNotification.objects.filter(available, sent_at__isnull=True,
            next_attempt_at__lte=now).order_by('pk').values_list('pk', flat=True)[:limit])
        sent = failed = 0
        for pk in ids:
            now = timezone.now()
            claim = uuid.uuid4()
            claimed = OrderNotification.objects.filter(
                Q(locked_until__isnull=True) | Q(locked_until__lte=now),
                pk=pk, sent_at__isnull=True, next_attempt_at__lte=now,
            ).update(claim_token=claim, locked_until=now + timedelta(minutes=2), attempts=F('attempts') + 1)
            if not claimed:
                continue
            notification = OrderNotification.objects.select_related('order').get(pk=pk)
            owned = OrderNotification.objects.filter(pk=pk, claim_token=claim, sent_at__isnull=True)
            try:
                message_id = send_order(notification.order)
            except DeliveryError as error:
                delay = max(min(3600, 60 * 2 ** min(notification.attempts - 1, 6)), error.retry_after)
                owned.update(last_error=error.code, next_attempt_at=timezone.now() + timedelta(seconds=delay),
                             locked_until=None, claim_token=None)
                failed += 1
            else:
                owned.update(sent_at=timezone.now(), message_id=message_id, last_error='',
                             locked_until=None, claim_token=None)
                sent += 1
        self.stdout.write(f'Telegram: sent={sent}, deferred={failed}')
