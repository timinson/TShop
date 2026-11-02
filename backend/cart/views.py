from decimal import Decimal

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ProductVariant


def quantity(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 99:
        raise ValidationError({'quantity': 'Количество должно быть целым числом от 1 до 99.'})
    return value


def cart_data(session):
    cart = session.get('cart', {})
    variants = {str(v.pk): v for v in ProductVariant.objects.select_related('product').filter(pk__in=cart)}
    items, total = [], Decimal('0')
    for key, qty in cart.items():
        variant = variants.get(key)
        price = variant.sale_price if variant else Decimal('0')
        subtotal = price * qty
        total += subtotal
        items.append({
            'variant_id': int(key), 'product_name': variant.product.name if variant else 'Товар удалён',
            'product_slug': variant.product.slug if variant else '',
            'image_url': (variant.product.image.url if variant.product.image else variant.product.image_url) if variant else '',
            'color': variant.color if variant else '', 'memory': variant.memory if variant else '',
            'price': f'{price:.2f}', 'quantity': qty, 'line_total': f'{subtotal:.2f}',
            'original_price': f'{variant.price:.2f}' if variant and variant.product.discount_percent else None,
            'discount_percent': variant.product.discount_percent if variant else 0,
            'stock': variant.stock if variant else 0,
            'is_available': bool(variant and variant.product.is_active and variant.stock >= qty),
        })
    return {'items': items, 'total': f'{total:.2f}', 'count': sum(cart.values())}


@method_decorator(csrf_protect, name='dispatch')
class GuestAPIView(APIView):
    pass


class CartView(GuestAPIView):
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response(cart_data(request.session))

    def post(self, request):
        variant_id = request.data.get('variant_id')
        if isinstance(variant_id, bool) or not isinstance(variant_id, int):
            raise ValidationError({'variant_id': 'Выберите вариант товара.'})
        cart = request.session.get('cart', {}).copy()
        qty = quantity(cart.get(str(variant_id), 0) + quantity(request.data.get('quantity', 1)))
        validate_variant(variant_id, qty)
        cart[str(variant_id)] = qty
        request.session['cart'] = cart
        return Response(cart_data(request.session))


def validate_variant(variant_id, qty):
    variant = ProductVariant.objects.filter(pk=variant_id, product__is_active=True).first()
    if not variant:
        raise ValidationError({'detail': 'Товар недоступен.'})
    if variant.stock < qty:
        raise ValidationError({'detail': 'Недостаточно товара в наличии.'})


class CartItemView(GuestAPIView):
    def patch(self, request, variant_id):
        cart = request.session.get('cart', {}).copy()
        if str(variant_id) not in cart:
            raise ValidationError({'detail': 'Товара нет в корзине.'})
        qty = quantity(request.data.get('quantity'))
        validate_variant(variant_id, qty)
        cart[str(variant_id)] = qty
        request.session['cart'] = cart
        return Response(cart_data(request.session))

    def delete(self, request, variant_id):
        cart = request.session.get('cart', {}).copy()
        cart.pop(str(variant_id), None)
        request.session['cart'] = cart
        return Response(cart_data(request.session))
