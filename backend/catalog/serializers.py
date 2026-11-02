from rest_framework import serializers

from .models import Category, Product, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class ProductVariantSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(source='sale_price', max_digits=12, decimal_places=2, read_only=True)
    original_price = serializers.SerializerMethodField()

    def get_original_price(self, variant):
        return f'{variant.price:.2f}' if variant.product.discount_percent else None

    class Meta:
        model = ProductVariant
        fields = ['id', 'color', 'memory', 'price', 'original_price', 'stock']


class ProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    min_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    min_original_price = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)

    def get_min_original_price(self, product):
        if not product.discount_percent or product.base_min_price is None:
            return None
        return f'{product.base_min_price:.2f}'

    def get_image_url(self, product):
        return product.image.url if product.image else product.image_url

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'release_date', 'specifications', 'image_url', 'category', 'variants', 'min_price', 'min_original_price', 'discount_percent', 'in_stock']
