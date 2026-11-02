import json
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


# Capture once when this worker imports the module: an old worker must never
# claim a new release merely because files on disk have already been replaced.
_release_file = settings.BASE_DIR / 'release.json'
_release_id = json.loads(_release_file.read_text(encoding='utf-8'))['release'] if _release_file.is_file() else None


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    data = {'status': 'ok', 'service': 'marketplace-api'}
    if _release_id:
        data['release'] = _release_id
    return Response(data)
