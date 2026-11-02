import uuid

from django.db import models
from django.utils import timezone


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новый'
        PROCESSING = 'processing', 'В обработке'
        COMPLETED = 'completed', 'Завершён'
        CANCELLED = 'cancelled', 'Отменён'

    name = models.CharField('Никнейм', max_length=150)
    phone = models.CharField('Телефон', max_length=30)
    email = models.EmailField('Email')
    address = models.TextField('Адрес')
    comment = models.TextField('Комментарий', blank=True)
    total = models.DecimalField('Итого', max_digits=14, decimal_places=2)
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.NEW)
    checkout_token = models.UUIDField(unique=True, editable=False)
    # Nullable for inserts made by the previous application version after rollback.
    tracking_token = models.UUIDField(default=uuid.uuid4, unique=True, null=True, editable=False)
    session_key = models.CharField(max_length=40, editable=False)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    completed_at = models.DateTimeField('Завершён', null=True, blank=True, editable=False)
    privacy_consent_at = models.DateTimeField('Согласие на обработку ПД', null=True, blank=True, editable=False)
    privacy_policy_version = models.CharField('Версия политики ПД', max_length=32, blank=True, editable=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    def __str__(self):
        return f'Заказ №{self.pk}'

    def ensure_tracking_token(self):
        if self.tracking_token is None:
            type(self).objects.using(self._state.db).filter(
                pk=self.pk, tracking_token__isnull=True,
            ).update(tracking_token=uuid.uuid4())
            # A competing request may have assigned the token first.
            self.refresh_from_db(fields=['tracking_token'])
        return self.tracking_token


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    variant = models.ForeignKey('catalog.ProductVariant', verbose_name='Вариант товара', null=True, blank=True, on_delete=models.SET_NULL, related_name='order_items')
    product_name = models.CharField('Товар', max_length=200)
    color = models.CharField('Цвет', max_length=80)
    memory = models.CharField('Память', max_length=80, blank=True)
    unit_price = models.DecimalField('Цена', max_digits=12, decimal_places=2)
    quantity = models.PositiveSmallIntegerField('Количество')

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'

    def __str__(self):
        return f'{self.product_name} × {self.quantity}'


class OrderNotification(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='notification')
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=40, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    message_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = 'Уведомление Telegram'
        verbose_name_plural = 'Уведомления Telegram'

    def __str__(self):
        return f'Заказ №{self.order_id}'
