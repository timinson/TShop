import json
from io import StringIO

from django.contrib.auth.models import Group, Permission, User
from django.core import serializers
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from catalog.models import Category, Product
from core.management.commands.transfer_sqlite import fingerprint, records


class TransferTests(TestCase):
    def test_sqlite_target_is_rejected_without_writes(self):
        with self.assertRaisesMessage(CommandError, 'must be MySQL'):
            call_command('transfer_sqlite', database='default', source='/not-read.sqlite3', stdout=StringIO())

    def test_fingerprint_ignores_order_but_detects_changes(self):
        a, b = {'pk': 1, 'fields': {'stock': 2}}, {'pk': 2, 'fields': {'stock': 3}}
        self.assertEqual(fingerprint([a, b]), fingerprint([b, a]))
        self.assertNotEqual(fingerprint([a]), fingerprint([b]))

    def test_business_serialization_preserves_primary_keys_json_and_media_paths(self):
        category = Category.objects.create(pk=91, name='Apple', slug='apple')
        product = Product.objects.create(pk=42, category=category, name='Phone', slug='phone',
                                         specifications={'Экран': 'OLED'}, image='products/phone.webp')
        saved = records(Product, 'default')
        product.delete()
        for obj in serializers.deserialize('json', json.dumps(saved), using='default'):
            obj.save(using='default')
        restored = Product.objects.get(pk=42)
        self.assertEqual(restored.category_id, 91)
        self.assertEqual(restored.specifications, {'Экран': 'OLED'})
        self.assertEqual(restored.image.name, 'products/phone.webp')
        self.assertEqual(fingerprint(saved), fingerprint(records(Product, 'default')))

    def test_user_password_ids_and_natural_permission_relations_survive_roundtrip(self):
        permission = Permission.objects.get(codename='view_order')
        group = Group.objects.create(pk=27, name='Managers')
        group.permissions.add(permission)
        user = User.objects.create_user(pk=35, username='manager', password='test-only-password', is_staff=True)
        user.groups.add(group)
        user.user_permissions.add(permission)
        rows = records(User, 'default')
        user.delete()
        for obj in serializers.deserialize('json', json.dumps(rows), using='default'):
            obj.save(using='default')
        restored = User.objects.get(pk=35)
        self.assertTrue(restored.check_password('test-only-password'))
        self.assertEqual(list(restored.groups.values_list('pk', flat=True)), [27])
        self.assertTrue(restored.has_perm('orders.view_order'))
        self.assertEqual(fingerprint(rows), fingerprint(records(User, 'default')))
