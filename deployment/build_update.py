"""Build a code-only release; never read the development database or .env."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from uuid import uuid4
import zipfile

from apply_update import allowed


ROOT = Path(__file__).resolve().parent.parent


def payload(root):
    files = {}
    backend = root / 'backend'
    for path in sorted(backend.rglob('*')):
        relative = path.relative_to(backend)
        if not path.is_file() or path.is_symlink() or '__pycache__' in relative.parts:
            continue
        if path.name in ('tests.py', 'test_images.py', 'import_product_images.py') or path.name.startswith('test_'):
            continue
        name = 'backend/' + relative.as_posix()
        if not allowed(name):
            continue
        if any(part.startswith('.') for part in relative.parts):
            continue
        files[name] = path.read_bytes()
    dist = root / 'frontend/dist'
    for path in sorted(dist.rglob('*')):
        relative = path.relative_to(dist)
        name = 'public/' + relative.as_posix()
        if path.is_file() and not path.is_symlink() and allowed(name) and not any(part.startswith('.') for part in relative.parts):
            files[name] = path.read_bytes()
    files['public/passenger_wsgi.py'] = (root / 'deployment/passenger_wsgi.py').read_bytes()
    required = ['backend/manage.py', 'backend/config/settings.py', 'backend/requirements-hosting.txt', 'public/index.html', 'public/passenger_wsgi.py']
    for name in required:
        if name not in files:
            raise ValueError(f'Missing release file: {name}')
    return files


def build(root=ROOT, output=None, compile_frontend=True):
    root = Path(root).resolve()
    if compile_frontend:
        subprocess.run(['npm.cmd' if os.name == 'nt' else 'npm', 'run', 'lint'], cwd=root / 'frontend', check=True)
        subprocess.run(['npm.cmd' if os.name == 'nt' else 'npm', 'run', 'build'], cwd=root / 'frontend', check=True)
    release = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    files = payload(root)
    files['backend/release.json'] = (json.dumps({'release': release}) + '\n').encode()
    manifest = {'format': 1, 'release': release, 'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    output = Path(output) if output else root / 'deployment' / f'shop-update-{release}.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidentally overwriting an earlier release.
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, indent=2))
        for name, data in files.items():
            archive.writestr(name, data)
    from apply_update import read_package
    read_package(output)
    print(f'Release: {release}\nArchive: {output}\nPayload files: {len(files)}')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    options = parser.parse_args()
    build(output=options.output)
