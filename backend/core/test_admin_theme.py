from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product


class AdminThemeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('theme-admin', password='test-only-password')
        category = Category.objects.create(name='iPhone', slug='iphone')
        cls.product = Product.objects.create(name='iPhone', slug='iphone', category=category)

    def setUp(self):
        self.client.force_login(self.user)

    def test_dashboard_keeps_sections_and_account_controls(self):
        response = self.client.get(reverse('admin:index'))
        for url in ['admin:catalog_product_changelist', 'admin:orders_order_changelist',
                    'admin:auth_user_changelist', 'admin:password_change', 'admin:logout']:
            self.assertContains(response, reverse(url))
        self.assertContains(response, 'shop_admin/admin.css')

    def test_product_form_keeps_all_save_and_related_controls(self):
        response = self.client.get(reverse('admin:catalog_product_change', args=[self.product.pk]))
        for control in ['name="_save"', 'name="_addanother"', 'name="_continue"',
                        'id="add_id_category"', 'id="variants-group"', 'class="deletelink"']:
            self.assertContains(response, control)
        self.assertContains(response, reverse('admin:catalog_product_history', args=[self.product.pk]))

    def test_login_uses_theme_and_retains_login_form(self):
        self.client.logout()
        response = self.client.get(reverse('admin:login'))
        self.assertContains(response, 'shop_admin/admin.css')
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
