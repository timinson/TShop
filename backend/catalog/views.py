from decimal import Decimal, InvalidOperation

from django.db.models import Exists, F, Min, OuterRef
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Product, ProductVariant
from .serializers import CategorySerializer, ProductSerializer
from .pricing import sale_price_expression


class CatalogPagination(PageNumberPagination):
    page_size = 12


def product_queryset():
    return Product.objects.filter(is_active=True).select_related('category').prefetch_related('variants').annotate(
        min_price=Min(sale_price_expression('variants__price', 'discount_percent')),
        base_min_price=Min('variants__price'),
        in_stock=Exists(ProductVariant.objects.filter(product=OuterRef('pk'), stock__gt=0)),
    ).order_by(F('release_date').desc(nulls_last=True), '-id')


class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    pagination_class = None


class CatalogOptionsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        variants = ProductVariant.objects.filter(product__is_active=True)
        if request.query_params.get('category'):
            variants = variants.filter(product__category__slug=request.query_params['category'])
        # Reset model ordering before DISTINCT so variant IDs do not create duplicates.
        colors = variants.exclude(color='').order_by('color').values_list('color', flat=True).distinct()
        memories = variants.exclude(memory='').order_by('memory').values_list('memory', flat=True).distinct()
        return Response({'colors': list(colors), 'memories': list(memories)})


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    pagination_class = CatalogPagination

    def get_queryset(self):
        params = self.request.query_params
        queryset = product_queryset()
        if 'ids' in params:
            ids = params['ids'].split(',')
            if len(ids) > 200 or any(not item.isascii() or not item.isdigit() or len(item) > 18 or int(item) < 1 for item in ids):
                raise ValidationError({'ids': 'Укажите до 200 ID товаров через запятую.'})
            queryset = queryset.filter(pk__in=[int(item) for item in ids])
        if params.get('q', '').strip():
            queryset = queryset.filter(name__icontains=params['q'].strip())
        if params.get('category'):
            queryset = queryset.filter(category__slug=params['category'])
        if 'discounted' in params:
            if params['discounted'] not in ['true', 'false']:
                raise ValidationError({'discounted': 'Допустимые значения: true или false.'})
            queryset = queryset.filter(discount_percent__gt=0) if params['discounted'] == 'true' else queryset.filter(discount_percent=0)
        variants = ProductVariant.objects.filter(product=OuterRef('pk')).annotate(sale_price_value=sale_price_expression())
        variant_filters = {key: params[key] for key in ('color', 'memory') if params.get(key)}
        variants = variants.filter(**variant_filters)
        prices = {}
        for key in ['min_price', 'max_price']:
            if key in params:
                try:
                    value = Decimal(params[key])
                    if not value.is_finite() or value < 0 or value > Decimal('9999999999.99'):
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    raise ValidationError({key: 'Укажите неотрицательную цену числом.'})
                prices[key] = value
                variants = variants.filter(**{'sale_price_value__gte' if key == 'min_price' else 'sale_price_value__lte': value})
        if len(prices) == 2 and prices['min_price'] > prices['max_price']:
            raise ValidationError({'max_price': 'Максимальная цена должна быть не меньше минимальной.'})
        if 'in_stock' in params:
            if params['in_stock'] not in ['true', 'false']:
                raise ValidationError({'in_stock': 'Допустимые значения: true или false.'})
            if params['in_stock'] == 'true':
                variants = variants.filter(stock__gt=0)
        if prices or variant_filters or params.get('in_stock') == 'true':
            queryset = queryset.filter(Exists(variants))
        ordering = params.get('ordering', '')
        choices = {
            '': [F('release_date').desc(nulls_last=True), '-id'],
            'price': [F('min_price').asc(nulls_last=True), 'id'],
            '-price': [F('min_price').desc(nulls_last=True), 'id'],
            'name': ['name', 'id'],
            '-name': ['-name', 'id'],
        }
        if ordering not in choices:
            raise ValidationError({'ordering': 'Неизвестный порядок сортировки.'})
        return queryset.order_by(*choices[ordering])


class ProductDetailView(generics.RetrieveAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return product_queryset()
