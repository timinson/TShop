"""Basic over-use limits shared by Passenger workers via the private cache."""
from hashlib import sha256

from django.core.cache import caches
from rest_framework.throttling import SimpleRateThrottle


class OrderTrackingIPThrottle(SimpleRateThrottle):
    rate = '30/min'
    scope = 'order_tracking_ip'

    @property
    def cache(self):
        return caches['order_tracking']

    def get_cache_key(self, request, view):
        # Forwarded headers supplied by callers are not trusted. Passenger must
        # expose the real client in REMOTE_ADDR; otherwise clients share a limit.
        address = request.META.get('REMOTE_ADDR') or 'unknown'
        identity = sha256(address.encode()).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': identity}


class OrderTrackingTokenThrottle(OrderTrackingIPThrottle):
    rate = '6/min'
    scope = 'order_tracking_token'

    def get_cache_key(self, request, view):
        return super().get_cache_key(request, view) + ':' + str(view.kwargs['tracking_token'])
