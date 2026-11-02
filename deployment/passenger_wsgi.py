"""REG.RU entry point; keep application and secrets outside the public folder."""
import os
import sys
from pathlib import Path

home = Path('/var/www/hosting_user/data')
sys.path.insert(0, str(home / 'shop-venv/lib/python3.14/site-packages'))
sys.path.insert(0, str(home / 'shop/backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
