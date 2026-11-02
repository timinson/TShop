
"""Conservative, standalone REG.RU update installer (Python standard library only)."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import zipfile

MAX_SIZE = 200 * 1024 * 1024
MAX_FILES = 1000


def mysql_config(values, python, app):
    """Use the project's dotenv parser, so quoted passwords retain their meaning."""
    result = subprocess.run(
        [str(python), '-c', 'import json; from dotenv import dotenv_values; '
         'print(json.dumps(dict(dotenv_values(".env", interpolate=True))))'],
        cwd=app, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
    )
    if result.returncode:
        raise ValueError('Cannot read MySQL configuration with the project dotenv parser')
    try:
        parsed = json.loads(result.stdout)
        parsed.update({key: value for key, value in os.environ.items() if key.startswith('MYSQL_')})
        config = {key: parsed.get(key, '') for key in
                  ['MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE']}
        config['MYSQL_HOST'] = config['MYSQL_HOST'] or '127.0.0.1'
        config['MYSQL_PORT'] = str(int(config['MYSQL_PORT'] or '3306'))
        if not 0 < int(config['MYSQL_PORT']) < 65536:
            raise ValueError
        if not all(config[key] for key in ['MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE']):
            raise ValueError
        if any('\x00' in value or '\n' in value or '\r' in value for value in config.values()):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid or incomplete MYSQL_* configuration') from None
    if not shutil.which('mysqldump'):
        raise ValueError('mysqldump is required for MySQL backups before updates')
    return config


def backup_mysql(config, backup, log):
    """Keep credentials out of argv, environment and logs; fail before installing code."""
    def quote(value):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'

    descriptor, filename = tempfile.mkstemp(prefix='.mysql-', suffix='.cnf', dir=backup)
    temporary = Path(filename)
    partial = backup / 'database.sql.incomplete'
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as options:
            options.write('[client]\n')
            for option, key in [('host', 'MYSQL_HOST'), ('port', 'MYSQL_PORT'),
                                ('user', 'MYSQL_USER'), ('password', 'MYSQL_PASSWORD')]:
                options.write(option + '=' + quote(config[key]) + '\n')
        command = [shutil.which('mysqldump'), '--defaults-extra-file=' + str(temporary),
                   '--single-transaction', '--quick', '--no-tablespaces', '--set-gtid-purged=OFF',
                   '--default-character-set=utf8mb4', '--databases', config['MYSQL_DATABASE']]
        log.write('RUN MySQL consistent backup (credentials suppressed)\n')
        log.flush()
        with partial.open('xb') as output:
            partial.chmod(0o600)
            result = subprocess.run(command, stdout=output, stderr=subprocess.DEVNULL, timeout=600)
        if result.returncode or not partial.stat().st_size:
            raise RuntimeError('MySQL backup failed; no release files installed')
        partial.rename(backup / 'database.sql')
    finally:
        temporary.unlink(missing_ok=True)


def safe_path(path):
    """Reject symlinks in every existing component, including the target."""
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise ValueError(f'Symlink is not allowed: {part}')
    return path


def allowed(name):
    parts = PurePosixPath(name).parts
    if any(part.lower() == 'agents.md' for part in parts):
        return False
    # Only the dedicated admin presentation directories may contain non-Python backend files.
    if re.fullmatch(r'backend/(?:templates/admin/(?:[a-z0-9_-]+/)*[a-z0-9_-]+\.html|core/static/shop_admin/[a-z0-9_-]+\.(?:css|js))', name):
        return True
    if any(p.startswith('.') or p.lower() in {'media', 'static', 'node_modules', '__pycache__', 'docs', 'tests', 'fixtures'} for p in parts):
        return False
    if parts[0] == 'backend':
        if name == 'backend/release.json':
            return True
        return (name.endswith('.py') and not any(p.startswith('test') for p in parts)
                or len(parts) == 2 and re.fullmatch(r'requirements(?:-[a-z]+)?\.txt', parts[-1]))
    if parts[0] == 'public':
        return (name in {'public/index.html', 'public/passenger_wsgi.py', 'public/favicon.ico', 'public/favicon.svg', 'public/icons.svg', 'public/vite.svg'}
                or len(parts) > 2 and parts[1] in {'assets', 'icons'}
                and PurePosixPath(name).suffix.lower() in {'.js', '.css', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico', '.woff', '.woff2'})
    return False


def read_package(archive):
    payload = {}
    with zipfile.ZipFile(archive) as package:
        infos = package.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_SIZE:
            raise ValueError('Archive exceeds size/file limit')
        seen = set()
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name).parts
            if (name in seen or '\\' in name or not parts or name.startswith('/')
                    or any(p in {'.', '..'} for p in name.split('/')) or ':' in name
                    or info.is_dir() or info.flag_bits & 1
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError(f'Unsafe archive member: {name}')
            seen.add(name)
            if name != 'manifest.json' and not allowed(name):
                raise ValueError(f'Unexpected archive member: {name}')
            payload[name] = package.read(info)
    manifest = json.loads(payload.pop('manifest.json'))
    if manifest.get('format') != 1 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', manifest.get('release', '')):
        raise ValueError('Invalid manifest format/release')
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    if manifest.get('files') != hashes:
        raise ValueError('Manifest files or hashes differ from archive')
    for required in ['backend/manage.py', 'backend/requirements-hosting.txt', 'backend/release.json', 'public/index.html', 'public/passenger_wsgi.py']:
        if required not in payload:
            raise ValueError(f'Missing required file: {required}')
    if json.loads(payload['backend/release.json']).get('release') != manifest['release']:
        raise ValueError('Release marker differs from manifest')
    return manifest, payload


def atomic_write(path, data, mode=0o644):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.update-tmp')
    safe_path(temporary)
    with temporary.open('xb') as stream:
        stream.write(data)
    temporary.chmod(mode)
    os.replace(temporary, path)


def execute(command, cwd, log):
    # Commands never contain credentials. Suppress tool output that could expose env values.
    log.write('RUN ' + ' '.join(map(str, command)) + '\n')
    log.flush()
    result = subprocess.run(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {command[1:3]}; run manually for diagnostics')


def verify_health(release):
    url = 'https://shop.example.com/api/health/?release=' + release
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=5) as response:
        data = json.load(response)
    if data.get('status') != 'ok' or data.get('service') != 'marketplace-api':
        raise RuntimeError('Health endpoint returned an unexpected service/status')
    if data.get('release') != release:
        raise RuntimeError(f'Worker release is {data.get("release")!r}; expected {release!r}')
    return True


def verify_maintenance():
    request = urllib.request.Request(
        'https://shop.example.com/api/cart/?maintenance=' + str(time.time_ns()),
        headers={'Cache-Control': 'no-cache'},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 503
    except urllib.error.HTTPError as error:
        return error.code == 503


def install(archive, home, check_only=False, run_command=None, health_check=None, sleep=time.sleep, maintenance_check=None):
    home = safe_path(home)
    app = safe_path(home / 'shop/backend')
    public = safe_path(home / 'www/shop.example.com')
    # venv deliberately uses a symlink to the provider's interpreter on Linux.
    python = safe_path(home / 'shop-venv/bin') / 'python'
    database = safe_path(home / 'shop/data/db.sqlite3')
    env = safe_path(app / '.env')
    htaccess = safe_path(public / '.htaccess')
    maintenance = safe_path(home / 'shop/maintenance.flag')
    if maintenance.exists():
        raise ValueError('Maintenance flag already exists; inspect the previous update before recovery')
    manifest, payload = read_package(archive)
    # Simple literal dotenv paths only; reject interpolation rather than guess its meaning.
    values = {}
    for line in env.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('\"\'')
    engine = os.getenv('DB_ENGINE', values.get('DB_ENGINE', 'sqlite')).lower()
    if engine not in {'sqlite', 'mysql'}:
        raise ValueError('DB_ENGINE must be sqlite or mysql')
    paths = {'STATIC_ROOT': public / 'static', 'MEDIA_ROOT': public / 'media'}
    if engine == 'sqlite':
        paths['DATABASE_PATH'] = database
    for key, expected in paths.items():
        if values.get(key) != str(expected):
            raise ValueError(f'{key} must point to the expected server path')
        safe_path(expected)
    if (engine == 'sqlite' and not database.is_file()) or not python.is_file() or not htaccess.is_file():
        raise ValueError('Existing database, virtual environment and .htaccess are required')
    mysql = mysql_config(values, python, app) if engine == 'mysql' else None
    destinations = {name: safe_path((app if name.startswith('backend/') else public) / name.split('/', 1)[1]) for name in payload}
    # Inspect whole backup trees as well; shutil must never follow a hidden symlink.
    for root in [app, public]:
        for current, directories, files in os.walk(root, followlinks=False):
            for name in directories + files:
                safe_path(Path(current) / name)
    if check_only:
        print(f'CHECK OK: {manifest["release"]}, {len(payload)} files; no changes made')
        return None
    updates = safe_path(home / 'shop-updates')
    updates.mkdir(mode=0o700, exist_ok=True)
    lock = safe_path(updates / '.lock')
    lock.mkdir(mode=0o700)  # Deliberately no automatic stale-lock removal.
    backup = updates / (manifest['release'] + '-' + time.strftime('%Y%m%d-%H%M%S'))
    gate = None
    original = htaccess.read_bytes()
    try:
        backup.mkdir(mode=0o700)
        with (backup / 'update.log').open('x', encoding='utf-8') as log:
            shutil.copytree(app, backup / 'backend')
            # public contains uploaded media: backup only application-managed files, never replace media.
            for name, target in destinations.items():
                if name.startswith('public/') and target.is_file():
                    saved = backup / name
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
            (backup / 'original.htaccess').write_bytes(original)
            (backup / 'RECOVERY.txt').write_text(
                'Update backup. Maintenance remains active on failure. Do not restore the database automatically.\n'
                'Inspect update.log; fix the failed command, verify WSGI and matching release health first.\n'
                'To resume traffic after verification, restore original.htaccess to the site .htaccess\n'
                'and remove shop/maintenance.flag. Never resume until the new release is healthy.\n'
                'Database migrations and installed dependencies may require a separate recovery plan.\n', encoding='utf-8')
            gate = (b'# SHOP UPDATE MAINTENANCE\nRewriteEngine On\n'
                    b'RewriteCond %{REQUEST_URI} !^/api/health/$\n'
                    b'RewriteRule ^ - [R=503,L]\n'
                    b'ErrorDocument 503 "Store update in progress. Please try again shortly."\n' + original)
            atomic_write(htaccess, gate)
            atomic_write(maintenance, manifest['release'].encode(), 0o600)
            sleep(2)  # Best effort only: Apache rules cannot drain requests already running.
            if not (maintenance_check or verify_maintenance)():
                raise RuntimeError('Maintenance gate is not blocking API requests. No release files installed; inspect hosting routing.')
            if mysql is not None:
                backup_mysql(mysql, backup, log)
            else:
                try:
                    import pysqlite3 as sqlite
                except ImportError:
                    import sqlite3 as sqlite
                with closing(sqlite.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
                    with closing(sqlite.connect(backup / 'db.sqlite3')) as destination:
                        source.backup(destination)
                (backup / 'db.sqlite3').chmod(0o600)
            requirements_changed = any(
                not destinations[name].is_file() or destinations[name].read_bytes() != data
                for name, data in payload.items()
                if re.fullmatch(r'backend/requirements(?:-[a-z]+)?\.txt', name)
            )
            for name, target in destinations.items():
                atomic_write(target, payload[name])
            run = run_command or execute
            if requirements_changed:
                run([str(python), '-m', 'pip', 'install', '-r', str(app / 'requirements-hosting.txt')], app, log)
            for arguments in [['check'], ['migrate', '--noinput'], ['collectstatic', '--noinput']]:
                run([str(python), str(app / 'manage.py'), *arguments], app, log)
            run([str(python), '-c', 'import runpy; runpy.run_path(' + repr(str(public / 'passenger_wsgi.py')) + ')'], app, log)
            safe_path(public / '.restart-app').touch()
            health = health_check or verify_health
            healthy = False
            for attempt in range(20):
                try:
                    healthy = health(manifest['release'])
                except Exception as error:
                    log.write(f'HEALTH attempt {attempt + 1}: {type(error).__name__}: {error}\n')
                    log.flush()
                    healthy = False
                if healthy:
                    break
                sleep(3)
            if not healthy:
                raise RuntimeError('New release health check failed; maintenance left active')
            if htaccess.read_bytes() != gate:
                raise RuntimeError('.htaccess changed during update; refusing to overwrite it')
            atomic_write(htaccess, original)
            maintenance.unlink()
            log.write('SUCCESS ' + manifest['release'] + '\n')
        print(f'UPDATE OK: {manifest["release"]}; backup: {backup}')
        return backup
    except Exception as error:
        if backup.is_dir():
            with (backup / 'update.log').open('a', encoding='utf-8') as log:
                log.write('FAILED: ' + type(error).__name__ + ': ' + str(error) + '\n')
        print(f'UPDATE FAILED. Backup/log: {backup}. Maintenance remains active if installed. No database rollback performed.')
        raise
    finally:
        lock.rmdir()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--home', type=Path, default=Path('/var/www/hosting_user/data'))
    parser.add_argument('--check-only', action='store_true')
    options = parser.parse_args()
    install(options.archive, options.home, options.check_only)
