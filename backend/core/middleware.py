from django.conf import settings
from django.http import HttpResponse, JsonResponse


class MaintenanceMiddleware:
    """Stop application requests while a release is being installed."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        marker = settings.BASE_DIR.parent / 'maintenance.flag'
        if request.path != '/api/health/' and marker.is_file():
            if request.path.startswith('/api/'):
                response = JsonResponse({'detail': 'Сайт обновляется. Пожалуйста, попробуйте через несколько минут.'}, status=503)
            else:
                response = HttpResponse('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Обновление shop</title><h1>Сайт обновляется</h1><p>Пожалуйста, зайдите через несколько минут.</p></html>', status=503)
            response['Retry-After'] = '60'
            response['Cache-Control'] = 'no-store'
            return response
        return self.get_response(request)
