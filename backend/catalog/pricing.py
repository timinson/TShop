from django.db.models import DecimalField, ExpressionWrapper, F, Value
from django.db.models.functions import Round


def sale_price_expression(price='price', discount='product__discount_percent'):
    # Floating divisor prevents SQLite's integer division for whole-ruble prices.
    return Round(ExpressionWrapper(
        F(price) * (Value(100) - F(discount)) / Value(100.0),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    ), precision=2)
