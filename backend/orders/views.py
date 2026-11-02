from decimal import Decimal

from django.core.cache import caches
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from cart.views import GuestAPIView, quantity
from catalog.models import ProductVariant
from .models import Order, OrderItem, OrderNotification
from .privacy import PRIVACY_POLICY_VERSION
from .demo import DEMO_PHONE, DEMO_EMAIL, DEMO_ADDRESS, DEMO_COMMENT
from .tracking import OrderTrackingIPThrottle, OrderTrackingTokenThrottle


class PrivacyConsentField(serializers.Field):
    def to_internal_value(self, value):
        if value is not True:
            raise serializers.ValidationError('Для оформления заказа необходимо согласие на обработку персональных данных.')
        return True


class CheckoutSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.RegexField(r'^\+?[\d\s()\-]{7,30}$', max_length=30, error_messages={'invalid': 'Укажите корректный телефон.'})
    email = serializers.EmailField()
    address = serializers.CharField(max_length=2000)
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')
    checkout_token = serializers.UUIDField()
    privacy_consent = PrivacyConsentField(required=True)
    privacy_policy_version = serializers.CharField(max_length=32)

    def to_internal_value(self, data):
        # Do not trust read-only browser fields: replace contacts before validation.
        if isinstance(data, dict):
            data = data.copy()
            data.update(phone=DEMO_PHONE, email=DEMO_EMAIL,
                        address=DEMO_ADDRESS, comment=DEMO_COMMENT)
        return super().to_internal_value(data)

    def validate_privacy_policy_version(self, value):
        if value != PRIVACY_POLICY_VERSION:
            raise serializers.ValidationError('Политика обновилась. Обновите страницу и подтвердите согласие повторно.')
        return value

    def validate_phone(self, value):
        if not 7 <= sum(character.isdigit() for character in value) <= 15:
            raise serializers.ValidationError('Телефон должен содержать от 7 до 15 цифр.')
        return value


def result(order):
    return {'id': order.pk, 'number': order.pk, 'total': f'{order.total:.2f}', 'status': order.status,
            'tracking_token': str(order.ensure_tracking_token())}


@method_decorator(never_cache, name='dispatch')
class OrderDetailView(GuestAPIView):
    throttle_classes = [OrderTrackingIPThrottle, OrderTrackingTokenThrottle]

    def get(self, request, tracking_token):
        cache = caches['order_tracking']
        key = f'order-detail:{tracking_token}'
        data = cache.get(key)
        if data is not None:
            return Response(data, status=404 if data.get('not_found') else 200)
        order = Order.objects.prefetch_related('items').filter(tracking_token=tracking_token).first()
        if order is None:
            data = {'detail': 'Заказ не найден.', 'not_found': True}
            cache.set(key, data, 30)
            return Response(data, status=404)
        data = {
            'id': order.pk,
            'number': order.pk,
            'total': f'{order.total:.2f}',
            'status': order.status,
            'status_label': order.get_status_display(),
            'created_at': order.created_at.isoformat(),
            'items': [{
                'product_name': item.product_name,
                'color': item.color,
                'memory': item.memory,
                'unit_price': f'{item.unit_price:.2f}',
                'quantity': item.quantity,
                'line_total': f'{item.unit_price * item.quantity:.2f}',
            } for item in order.items.all()],
        }
        cache.set(key, data, 30)
        return Response(data)


@method_decorator(never_cache, name='dispatch')
class OrderView(GuestAPIView):
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        data.pop('privacy_consent')
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        existing = Order.objects.filter(checkout_token=data['checkout_token']).first()
        if existing:
            return self.repeat(existing, session_key)
        cart = request.session.get('cart', {})
        if not cart:
            raise ValidationError({'detail': 'Корзина пуста.'})
        try:
            with transaction.atomic():
                variants = {str(v.pk): v for v in ProductVariant.objects.select_for_update().select_related('product').filter(pk__in=cart)}
                total, snapshots = Decimal('0'), []
                for key, qty in cart.items():
                    quantity(qty)
                    variant = variants.get(key)
                    if not variant or not variant.product.is_active:
                        raise ValidationError({'detail': 'В корзине есть недоступный товар. Удалите его.'})
                    changed = ProductVariant.objects.filter(pk=variant.pk, stock__gte=qty, product__is_active=True).update(stock=F('stock') - qty)
                    if not changed:
                        raise ValidationError({'detail': f'Недостаточно товара «{variant.product.name}» в наличии.'})
                    price = variant.sale_price
                    total += price * qty
                    snapshots.append(OrderItem(variant=variant, product_name=variant.product.name, color=variant.color, memory=variant.memory, unit_price=price, quantity=qty))
                order = Order.objects.create(**data, session_key=session_key, total=total, privacy_consent_at=timezone.now())
                for item in snapshots:
                    item.order = order
                OrderItem.objects.bulk_create(snapshots)
                OrderNotification.objects.create(order=order)
        except IntegrityError:
            existing = Order.objects.filter(checkout_token=data['checkout_token']).first()
            if existing:
                return self.repeat(existing, session_key)
            raise
        request.session['cart'] = {}
        return Response(result(order), status=201)

    def repeat(self, order, session_key):
        if order.session_key != session_key:
            raise ValidationError({'detail': 'Ключ оформления уже использован. Обновите страницу.'})
        return Response(result(order))
