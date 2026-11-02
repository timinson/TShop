from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import ProductVariant
from .models import Order


def validate_transition(order, status):
    if status not in Order.Status.values:
        raise ValidationError('Неизвестный статус заказа.')
    if status == order.status:
        return
    if order.status in (Order.Status.CANCELLED, Order.Status.COMPLETED):
        raise ValidationError('Завершённый или отменённый заказ нельзя перевести в другой статус.')
    if status == Order.Status.NEW:
        raise ValidationError('Заказ в обработке нельзя вернуть в статус «Новый».')
    if status == Order.Status.CANCELLED and order.items.filter(variant__isnull=True).exists():
        raise ValidationError('Нельзя отменить заказ: вариант товара удалён или не определён для старой позиции. Сначала восстановите связь с товаром.')


@transaction.atomic
def transition_order_status(order_id, status):
    order = Order.objects.get(pk=order_id)
    validate_transition(order, status)
    if order.status == status:
        return order
    # The conditional UPDATE claims the transition even on SQLite, where
    # select_for_update does not provide row locks. Stock changes roll back
    # together with this claim if any line cannot be returned.
    updates = {'status': status}
    if status == Order.Status.COMPLETED:
        updates['completed_at'] = timezone.now()
    if not Order.objects.filter(pk=order.pk, status=order.status).update(**updates):
        raise ValidationError('Статус заказа уже изменился. Обновите страницу и повторите действие.')
    if status == Order.Status.CANCELLED:
        for item in order.items.all():
            if not item.variant_id or not ProductVariant.objects.filter(pk=item.variant_id).update(stock=F('stock') + item.quantity):
                raise ValidationError('Не удалось вернуть товар на склад: вариант удалён. Изменения отменены.')
    order.status = status
    if status == Order.Status.COMPLETED:
        order.completed_at = updates['completed_at']
    return order
