#!/bin/bash
set -eu
umask 077
BASE=/var/www/hosting_user/data
APP="$BASE/shop/backend"
PY="$BASE/shop-venv/bin/python"
mkdir -p "$BASE/shop/data"
"$PY" -m pip install -r "$APP/requirements-hosting.txt"
if [ ! -f "$APP/.env" ]; then
  "$PY" - <<'PY'
from pathlib import Path
from secrets import token_urlsafe
base = Path('/var/www/hosting_user/data')
env = base / 'shop/backend/.env'
with env.open('x') as stream:
    stream.write('\n'.join([
        'DEBUG=False',
        'SECRET_KEY=' + token_urlsafe(64),
        'ALLOWED_HOSTS=shop.example.com,www.shop.example.com',
        'CSRF_TRUSTED_ORIGINS=https://shop.example.com,https://www.shop.example.com',
        f'DATABASE_PATH={base}/shop/data/db.sqlite3',
        f'STATIC_ROOT={base}/www/shop.example.com/static',
        f'MEDIA_ROOT={base}/www/shop.example.com/media',
        '',
    ]))
env.chmod(0o600)
PY
fi
FIRST_INSTALL=0
if [ ! -f "$BASE/shop/data/db.sqlite3" ]; then FIRST_INSTALL=1; fi
"$PY" "$APP/manage.py" migrate --noinput
if [ "$FIRST_INSTALL" = 1 ]; then
  "$PY" "$APP/manage.py" loaddata "$BASE/shop/catalog.json"
fi
"$PY" "$APP/manage.py" collectstatic --noinput
"$PY" "$APP/manage.py" check
echo 'Application installed. Create a new administrator before activation.'
