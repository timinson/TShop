"""Use a supported SQLite driver on hosts with an older system SQLite."""
import sqlite3
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

if os.getenv('DB_ENGINE', 'sqlite').strip().lower() == 'sqlite' and sqlite3.sqlite_version_info < (3, 31, 0):
    try:
        import pysqlite3
    except ImportError as exc:
        raise RuntimeError(
            'System SQLite is too old. Install requirements-hosting.txt '
            'in the server virtual environment.'
        ) from exc
    if pysqlite3.sqlite_version_info < (3, 31, 0):
        raise RuntimeError('The bundled SQLite driver must provide SQLite 3.31 or newer.')
    sys.modules['sqlite3'] = pysqlite3
    sys.modules['sqlite3.dbapi2'] = pysqlite3.dbapi2
