from django.urls import path

from .views import CatalogOptionsView, CategoryListView, ProductDetailView, ProductListView

urlpatterns = [
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('catalog-options/', CatalogOptionsView.as_view(), name='catalog-options'),
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),
]
