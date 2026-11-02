"""Serve the built storefront without routing API or private paths into React."""
import re
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.urls import resolve
from django.views.decorators.http import require_safe

from catalog.models import Product


PAGE_PATHS = {'/', '/catalog', '/discounts', '/favorites', '/cart', '/checkout', '/privacy', '/consent'}
RESERVED_PREFIXES = {'api', 'admin', 'static', 'media', 'assets', 'icons', 'cgi-bin'}


@require_safe
def storefront(request, path=''):
    # Only a fixed file is read; no URL segment is ever used as a filesystem path.
    segments = path.split('/')
    if segments[0] in {'api', 'admin'} and settings.APPEND_SLASH and not request.path.endswith('/'):
        match = resolve(request.path + '/')
        if match.func is not storefront:
            query = request.META.get('QUERY_STRING', '')
            return HttpResponsePermanentRedirect(request.path + '/' + ('?' + query if query else ''))
    if segments[0] == 'api':
        return JsonResponse({'detail': 'Not found.'}, status=404)
    if segments[0] in RESERVED_PREFIXES or any(segment.startswith('.') for segment in segments):
        return HttpResponse('Not found.', status=404, content_type='text/plain; charset=utf-8')

    canonical = request.path.rstrip('/') or '/'
    found = canonical in PAGE_PATHS
    if re.fullmatch(r'/orders/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', canonical):
        found = True
    product = re.fullmatch(r'/products/([-a-zA-Z0-9_]+)', canonical)
    if product:
        found = Product.objects.filter(slug=product.group(1), is_active=True).exists()

    if found and request.path != canonical:
        query = request.META.get('QUERY_STRING', '')
        return HttpResponsePermanentRedirect(canonical + ('?' + query if query else ''))

    try:
        document = Path(settings.FRONTEND_INDEX_PATH).read_bytes()
    except OSError:
        return HttpResponse('Storefront is temporarily unavailable.', status=503,
                            content_type='text/plain; charset=utf-8')
    response = HttpResponse(document, status=200 if found else 404, content_type='text/html; charset=utf-8')
    # Refresh the entry point after releases; immutable caching belongs to hashed assets.
    response['Cache-Control'] = 'no-store' if canonical.startswith('/orders/') else 'no-cache'
    if canonical.startswith('/orders/'):
        response['Referrer-Policy'] = 'no-referrer'
        response['X-Robots-Tag'] = 'noindex, nofollow'
    return response
