"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, re_path
from django.conf import settings
from django.conf.urls.static import static
from core.frontend import storefront
from orders.analytics import analytics, analytics_orders

urlpatterns = [
    path('admin/analytics/', admin.site.admin_view(analytics), name='sales_analytics'),
    path('admin/analytics/orders/', admin.site.admin_view(analytics_orders), name='sales_analytics_orders'),
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    path('api/', include('catalog.urls')),
    path('api/', include('cart.urls')),
    path('api/', include('orders.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Must stay after API/admin/media routes so missing backend resources never get HTML.
urlpatterns += [re_path(r'^(?P<path>.*)$', storefront, name='storefront')]
