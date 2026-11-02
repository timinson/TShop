from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from .models import Order, OrderItem


class AnalyticsForm(forms.Form):
    period = forms.ChoiceField(choices=[('7', '7 дней'), ('30', '30 дней'), ('90', '90 дней'), ('365', 'Год'), ('custom', 'Свой период')], initial='30', label='Период')
    start = forms.DateField(required=False, label='С', widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(required=False, label='По', widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        data = super().clean()
        if data.get('period') == 'custom':
            start, end = data.get('start'), data.get('end')
            if not start or not end:
                raise forms.ValidationError('Укажите обе даты периода.')
            if start.year < 1901 or end.year > 9998:
                raise forms.ValidationError('Укажите даты между 1901 и 9998 годами.')
            if start > end:
                raise forms.ValidationError('Начало периода должно быть не позднее окончания.')
            if (end - start).days > 3659:
                raise forms.ValidationError('Период не может превышать 3660 дней.')
        elif data.get('period'):
            end = timezone.localdate()
            start = end - timedelta(days=int(data['period']) - 1)
            data.update(start=start, end=end)
        return data


def bucket(day, grouping):
    if grouping == 'week':
        return day - timedelta(days=day.weekday())
    if grouping == 'month':
        return day.replace(day=1)
    return day


def next_bucket(day, grouping):
    if grouping == 'month':
        return date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return day + timedelta(days=7 if grouping == 'week' else 1)


def grouping_for_period(start, end):
    days = (end - start).days + 1
    return 'day' if days <= 30 else 'week' if days <= 90 else 'month'


def analytics(request):
    if not request.user.has_perm('orders.view_order'):
        raise PermissionDenied
    defaults = {'period': '30'}
    form = AnalyticsForm(request.GET or defaults)
    context = {**admin.site.each_context(request), 'title': 'Аналитика', 'form': form}
    if form.is_valid():
        start, end = (form.cleaned_data[k] for k in ('start', 'end'))
        grouping = grouping_for_period(start, end)
        # Use local calendar boundaries as an indexed datetime range; truncation
        # below uses the same active timezone when assigning days.
        zone = timezone.get_current_timezone()
        range_start = timezone.make_aware(datetime.combine(start, time.min), zone)
        range_end = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), zone)
        orders = Order.objects.filter(status=Order.Status.COMPLETED, completed_at__gte=range_start, completed_at__lt=range_end)
        order_days = orders.annotate(day=TruncDate('completed_at')).values('day').annotate(count=Count('pk')).order_by()
        item_rows = OrderItem.objects.filter(order__in=orders).annotate(day=TruncDate('order__completed_at')).values('day', 'product_name', 'unit_price').annotate(units=Sum('quantity')).order_by()
        daily = defaultdict(lambda: {'revenue': Decimal('0'), 'units': 0, 'orders': 0})
        for row in order_days:
            daily[row['day']]['orders'] = row['count']
        ranking = defaultdict(lambda: {'units': 0, 'revenue': Decimal('0')})
        for row in item_rows:
            revenue = row['unit_price'] * row['units']
            day = row['day']
            daily[day]['revenue'] += revenue
            daily[day]['units'] += row['units']
            if start <= day <= end:
                ranking[row['product_name']]['units'] += row['units']
                ranking[row['product_name']]['revenue'] += revenue
        def totals(first, last):
            result = {'revenue': Decimal('0'), 'units': 0, 'orders': 0}
            for day, values in daily.items():
                if first <= day <= last:
                    for key in result:
                        result[key] += values[key]
            result['average'] = result['revenue'] / result['orders'] if result['orders'] else Decimal('0')
            return result
        current = totals(start, end)
        cards = [{'label': label, 'value': current[key], 'money': key in ('revenue', 'average')} for key, label in [('revenue', 'Выручка'), ('orders', 'Завершённые заказы'), ('units', 'Продано единиц'), ('average', 'Средний чек')]]
        grouped = defaultdict(lambda: {'revenue': Decimal('0'), 'orders': 0})
        for day, values in daily.items():
            if start <= day <= end:
                group = grouped[bucket(day, grouping)]
                group['revenue'] += values['revenue']
                group['orders'] += values['orders']
        series = []
        day = bucket(start, grouping)
        while day <= end:
            following = next_bucket(day, grouping)
            series.append({'day': day, 'range_start': max(day, start), 'range_end': min(following - timedelta(days=1), end), **grouped[day]})
            day = following
        max_revenue = max((item['revenue'] for item in series), default=Decimal('0'))
        max_orders = max((item['orders'] for item in series), default=0)
        for item in series:
            item['revenue_width'] = round(item['revenue'] * 100 / max_revenue, 2) if max_revenue else 0
            item['orders_width'] = round(item['orders'] * 100 / max_orders, 2) if max_orders else 0
        context.update(start=start, end=end, grouping=grouping, cards=cards, series=series, current=current, ranking=sorted(({'name': name, **data} for name, data in ranking.items()), key=lambda item: (-item['units'], item['name'])), unknown_count=Order.objects.filter(status=Order.Status.COMPLETED, completed_at__isnull=True).count())
    return render(request, 'admin/orders/analytics.html', context)


def analytics_orders(request):
    """Return a bounded page of sale details only when an interval is opened."""
    if not request.user.has_perm('orders.view_order'):
        raise PermissionDenied
    if request.method != 'GET':
        return JsonResponse({'error': 'Метод не поддерживается.'}, status=405)
    form = AnalyticsForm({'period': 'custom', 'start': request.GET.get('start'),
                          'end': request.GET.get('end')})
    try:
        page = int(request.GET.get('page', '1'))
        if page < 1 or page > 100000:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Некорректная страница.'}, status=400)
    if not form.is_valid():
        return JsonResponse({'error': 'Некорректный диапазон дат.'}, status=400)
    start, end = form.cleaned_data['start'], form.cleaned_data['end']
    zone = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(start, time.min), zone)
    range_end = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), zone)
    orders = Order.objects.filter(status=Order.Status.COMPLETED, completed_at__gte=range_start,
                                  completed_at__lt=range_end).order_by('-completed_at', '-pk')
    page_size = 20
    offset = (page - 1) * page_size
    # Fetch one extra id to detect another page without counting all orders.
    ids = list(orders.values_list('pk', flat=True)[offset:offset + page_size + 1])
    has_next = len(ids) > page_size
    page_orders = orders.filter(pk__in=ids[:page_size]).prefetch_related('items')
    result = []
    for order in page_orders:
        total = sum((item.unit_price * item.quantity for item in order.items.all()), Decimal('0'))
        result.append({'id': order.pk, 'date': timezone.localtime(order.completed_at, zone).date().isoformat(),
                       'total': f'{total:.2f}'})
    return JsonResponse({'orders': result, 'page': page, 'has_next': has_next})
