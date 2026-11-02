from django.urls import path
from .views import CartItemView, CartView

urlpatterns = [
    path('cart/', CartView.as_view()),
    path('cart/items/<int:variant_id>/', CartItemView.as_view()),
]
