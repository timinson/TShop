from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from .models import Order, OrderItem, OrderNotification
from .services import transition_order_status, validate_transition


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['status']

    def clean_status(self):
        status = self.cleaned_data['status']
        if self.instance.pk:
            validate_transition(Order.objects.get(pk=self.instance.pk), status)
        return status


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ['product_name', 'color', 'memory', 'unit_price', 'quantity']
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = ['id', 'created_at', 'name', 'items_summary', 'total', 'status_badge']
    list_display_links = ['id']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'phone', 'email']
    fieldsets = [
        ('Состояние заказа', {'fields': ['status', 'total', 'created_at', 'tracking_link']}),
        ('Данные заказа', {'fields': ['name', 'phone', 'email', 'address', 'comment']}),
        ('Согласие на обработку данных', {'fields': ['privacy_consent_at', 'privacy_policy_version']}),
    ]
    readonly_fields = ['name', 'phone', 'email', 'address', 'comment', 'total', 'created_at', 'privacy_consent_at', 'privacy_policy_version', 'tracking_link']
    inlines = [OrderItemInline]

    class Media:
        css = {'all': ['shop_admin/orders-list.css']}
        js = ['shop_admin/orders-list.js']

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')

    @admin.display(description='Состав заказа')
    def items_summary(self, obj):
        items = list(obj.items.all())
        if not items:
            return '—'
        summary = ', '.join(f'{item.product_name} × {item.quantity}' for item in items[:2])
        if len(items) > 2:
            summary += f' и ещё {len(items) - 2}'
        return summary

    @admin.display(description='Статус', ordering='status')
    def status_badge(self, obj):
        return format_html('<span class="order-status order-status--{}">{}</span>', obj.status, obj.get_status_display())

    @admin.display(description='Страница заказа')
    def tracking_link(self, obj):
        return format_html('<a href="/orders/{}">Открыть статус заказа</a>', obj.ensure_tracking_token())

    def save_model(self, request, obj, form, change):
        transition_order_status(obj.pk, obj.status)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as error:
            # A concurrent transition can invalidate an already validated form.
            self.message_user(request, ' '.join(error.messages), level=messages.ERROR)
            return HttpResponseRedirect(request.path)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderNotification)
class OrderNotificationAdmin(admin.ModelAdmin):
    list_display = ['order', 'attempts', 'sent_at', 'last_error', 'next_attempt_at']
    list_filter = ['sent_at']
    readonly_fields = ['order', 'attempts', 'sent_at', 'message_id', 'last_error', 'next_attempt_at', 'locked_until', 'claim_token']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
