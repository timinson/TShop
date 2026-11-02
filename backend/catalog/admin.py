from django.contrib import admin

from .models import Category, Product, ProductVariant


admin.site.site_header = 'shop — управление магазином'
admin.site.site_title = 'shop'
admin.site.index_title = 'Управление магазином'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'release_date', 'discount_percent', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductVariantInline]
    fieldsets = [
        ('Основное', {'fields': ['name', 'slug', 'category', 'release_date', 'is_active']}),
        ('Описание и характеристики', {'fields': ['description', 'specifications']}),
        ('Изображение', {'fields': ['image', 'image_url']}),
        ('Цена и скидка', {'fields': ['discount_percent']}),
    ]
