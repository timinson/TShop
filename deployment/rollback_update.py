"""Restore code from an apply_update backup; preserve the current database and media.

Use only for a release whose database changes remain compatible with the old code.
Dependencies must be unchanged. Applied migration files are retained deliberately.
"""
import argparse
import json
from pathlib import Path
import re
import time

from apply_update import atomic_write, allowed, execute, safe_path, verify_health, verify_maintenance


def rollback(backup, home, check_only=False, run_command=None, health_check=None,
             maintenance_check=None, sleep=time.sleep):
    home = safe_path(home)
    updates = safe_path(home / 'shop-updates')
    backup = safe_path(backup)
    if backup.parent.resolve() != updates.resolve() or not backup.is_dir():
        raise ValueError('Backup must be a direct directory inside home/shop-updates')
    app = safe_path(home / 'shop/backend')
    public = safe_path(home / 'www/shop.example.com')
    htaccess = safe_path(public / '.htaccess')
    maintenance = safe_path(home / 'shop/maintenance.flag')
    python = safe_path(home / 'shop-venv/bin') / 'python'
    # Reject links before inspecting backup bytes or writing destinations.
    files = {}
    for directory in ['backend', 'public']:
        root = safe_path(backup / directory)
        for path in root.rglob('*'):
            safe_path(path)
            name = path.relative_to(backup).as_posix()
            if path.is_file() and allowed(name):
                target = safe_path((app if directory == 'backend' else public) / path.relative_to(root))
                files[name] = (target, path.read_bytes())
    for name in ['backend/manage.py', 'backend/release.json', 'backend/requirements-hosting.txt', 'public/index.html', 'public/passenger_wsgi.py']:
        if name not in files:
            raise ValueError(f'Incomplete backup: {name}')
    release = json.loads(files['backend/release.json'][1]).get('release', '')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', release):
        raise ValueError('Invalid old release marker')
    for name, (target, data) in files.items():
        if re.fullmatch(r'backend/requirements(?:-[a-z]+)?\.txt', name):
            if not target.is_file() or target.read_bytes() != data:
                raise ValueError('Dependencies differ; environment recovery must be planned separately')
    for path in app.glob('requirements*.txt'):
        safe_path(path)
        if re.fullmatch(r'requirements(?:-[a-z]+)?\.txt', path.name) and 'backend/' + path.name not in files:
            raise ValueError('Current dependency file is absent from backup')
    original = safe_path(backup / 'original.htaccess').read_bytes()
    if not python.is_file() or not htaccess.is_file():
        raise ValueError('Existing interpreter and .htaccess are required')
    marker = b'# SHOP UPDATE MAINTENANCE\n'
    gate = (marker + b'RewriteEngine On\nRewriteCond %{REQUEST_URI} !^/api/health/$\n'
            b'RewriteRule ^ - [R=503,L]\n'
            b'ErrorDocument 503 "Store update in progress. Please try again shortly."\n' + original)
    current = htaccess.read_bytes()
    if current not in [original, gate]:
        raise ValueError('.htaccess differs from this backup; inspect changes before rollback')
    if maintenance.exists() and current != gate:
        raise ValueError('Existing maintenance state does not match this backup')
    if maintenance.exists():
        active_release = maintenance.read_text(encoding='utf-8')
        backup_match = re.fullmatch(r'(.+)-\d{8}-\d{6}', backup.name)
        update_release = backup_match.group(1) if backup_match else None
        if active_release not in [release, update_release]:
            raise ValueError('Maintenance belongs to a different update backup')
    if check_only:
        print(f'ROLLBACK CHECK OK: {release}, {len(files)} files; database and media preserved')
        return
    lock = safe_path(updates / '.lock')
    lock.mkdir(mode=0o700)
    try:
        with safe_path(backup / 'rollback.log').open('a', encoding='utf-8') as log:
            atomic_write(htaccess, gate)
            atomic_write(maintenance, release.encode(), 0o600)
            sleep(2)
            if not (maintenance_check or verify_maintenance)():
                raise RuntimeError('Maintenance gate is not blocking API requests')
            for target, data in files.values():
                atomic_write(target, data)
            run = run_command or execute
            for arguments in [['check'], ['collectstatic', '--noinput']]:
                run([str(python), str(app / 'manage.py'), *arguments], app, log)
            run([str(python), '-c', 'import runpy; runpy.run_path(' + repr(str(public / 'passenger_wsgi.py')) + ')'], app, log)
            safe_path(public / '.restart-app').touch()
            health = health_check or verify_health
            for attempt in range(20):
                try:
                    healthy = health(release)
                except Exception as error:
                    log.write(f'HEALTH {attempt + 1}: {type(error).__name__}\n')
                    healthy = False
                if healthy:
                    break
                sleep(3)
            else:
                raise RuntimeError('Old release health failed; maintenance remains active')
            if htaccess.read_bytes() != gate:
                raise RuntimeError('.htaccess changed during rollback')
            atomic_write(htaccess, original)
            maintenance.unlink()
            log.write('SUCCESS ' + release + '\n')
        print(f'ROLLBACK OK: {release}; database and media preserved')
    except Exception:
        print(f'ROLLBACK FAILED: inspect {backup / "rollback.log"}; maintenance remains active if installed')
        raise
    finally:
        lock.rmdir()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--home', type=Path, default=Path('/var/www/hosting_user/data'))
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    rollback(args.backup, args.home, args.check_only)
