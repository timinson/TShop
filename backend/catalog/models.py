from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.db import models
from .validators import validate_image_size


def product_image_path(instance, filename):
    return f'products/{uuid4().hex}{Path(filename).suffix.lower()}'


class Category(models.Model):
    name = models.CharField('Название', max_length=100)
    slug = models.SlugField('Адрес', unique=True)

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, verbose_name='Категория', on_delete=models.PROTECT, related_name='products')
    name = models.CharField('Название', max_length=200)
    release_date = models.DateField('Дата старта продаж', null=True, blank=True, help_text='Дата начала продаж модели. Используется для сортировки: сначала новые; без даты — в конце.')
    slug = models.SlugField('Адрес', unique=True)
    description = models.TextField('Описание')
    specifications = models.JSONField('Характеристики', default=dict, blank=True, help_text='JSON-объект: название характеристики и её текстовое значение.')
    image_url = models.URLField('Ссылка на изображение', blank=True)
    image = models.ImageField('Изображение', upload_to=product_image_path, blank=True,
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']), validate_image_size],
                              help_text='JPEG, PNG или WebP, до 5 МБ. Имеет приоритет над ссылкой.')
    is_active = models.BooleanField('Опубликован', default=True)
    discount_percent = models.PositiveSmallIntegerField('Скидка, %', default=0, validators=[MaxValueValidator(99)], help_text='От 0 до 99. Применяется ко всем вариантам товара.')

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['id']
        constraints = [models.CheckConstraint(condition=models.Q(discount_percent__lte=99), name='product_discount_max_99')]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not isinstance(self.specifications, dict) or any(
            not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip()
            for key, value in self.specifications.items()
        ):
            raise ValidationError({'specifications': 'Укажите объект с непустыми текстовыми названиями и значениями.'})


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, verbose_name='Товар', on_delete=models.CASCADE, related_name='variants')
    color = models.CharField('Цвет', max_length=80)
    memory = models.CharField('Память', max_length=80, blank=True)
    price = models.DecimalField('Цена, ₽', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    stock = models.PositiveIntegerField('Остаток', default=0)

    @property
    def sale_price(self):
        return (self.price * (100 - self.product.discount_percent) / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    class Meta:
        verbose_name = 'Вариант товара'
        verbose_name_plural = 'Варианты товара'
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['product', 'color', 'memory'], name='unique_product_color_memory'),
            models.CheckConstraint(condition=models.Q(price__gt=0), name='variant_price_positive'),
        ]

    def __str__(self):
        return ' / '.join(filter(None, [self.product.name, self.color, self.memory]))
