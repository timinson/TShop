"""Copy a quiescent SQLite snapshot into an empty, migrated MySQL database."""
import hashlib
import json
from pathlib import Path

from django.apps import apps
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.db.migrations.executor import MigrationExecutor


LABELS = (
    'contenttypes.ContentType', 'auth.Permission', 'auth.Group', 'auth.User',
    'catalog.Category', 'catalog.Product', 'catalog.ProductVariant',
    'orders.Order', 'orders.OrderItem', 'orders.OrderNotification',
    'sessions.Session', 'admin.LogEntry',
)
GENERATED = {'contenttypes.ContentType', 'auth.Permission'}


def records(model, alias):
    # Natural references remap permissions/content types without changing order/user IDs.
    return json.loads(serializers.serialize(
        'json', model._default_manager.using(alias).order_by(model._meta.pk.name),
        use_natural_foreign_keys=True,
        use_natural_primary_keys=model._meta.label in GENERATED,
    ))


def fingerprint(rows):
    encoded = sorted(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows)
    return hashlib.sha256('\n'.join(encoded).encode()).hexdigest()


def compare(models, source, target):
    for model in models:
        source_rows = records(model, source)
        target_rows = records(model, target)
        if model._meta.label in GENERATED:
            # migrate may have generated extra permissions for a newer application version.
            source_keys = {json.dumps(row['fields'], sort_keys=True) for row in source_rows}
            target_rows = [row for row in target_rows if json.dumps(row['fields'], sort_keys=True) in source_keys]
        if fingerprint(source_rows) != fingerprint(target_rows):
            raise CommandError(f'Data mismatch: {model._meta.label}; transfer not verified.')


class Command(BaseCommand):
    help = 'Inspect, copy or verify a private SQLite snapshot. Default is read-only inspection.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default='mysql_target', help='MySQL target alias; default mysql_target leaves the live SQLite database unchanged.')
        parser.add_argument('--source', required=True, help='Absolute path to a stopped/read-only SQLite snapshot.')
        action = parser.add_mutually_exclusive_group()
        action.add_argument('--apply', action='store_true', help='Copy into empty MySQL target database.')
        action.add_argument('--verify', '--verify-only', action='store_true', help='Compare existing target with snapshot; no writes.')

    def handle(self, *args, **options):
        target_alias = options['database']
        if target_alias not in connections:
            raise CommandError('Enable MYSQL_MIGRATION_ENABLED=1 to configure mysql_target.')
        target = connections[target_alias]
        if target.vendor != 'mysql':
            raise CommandError('Target database must be MySQL. SQLite application database is never a transfer target.')
        path = Path(options['source']).expanduser()
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise CommandError('Source must be an existing absolute, non-symlink SQLite snapshot path.')
        alias = 'sqlite_transfer_source'
        if alias in connections:
            raise CommandError('Reserved source alias is already configured.')
        config = {
            'ENGINE': 'django.db.backends.sqlite3', 'NAME': path.resolve().as_uri() + '?mode=ro',
            'OPTIONS': {'uri': True}, 'TIME_ZONE': None, 'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': False, 'AUTOCOMMIT': True, 'ATOMIC_REQUESTS': False,
        }
        connections.databases[alias] = config
        try:
            self.transfer(alias, target_alias, options)
        finally:
            connections[alias].close()
            del connections[alias]
            del connections.databases[alias]

    def transfer(self, source, target, options):
        models = [apps.get_model(label) for label in LABELS]
        for alias in (source, target):
            executor = MigrationExecutor(connections[alias])
            if executor.migration_plan(executor.loader.graph.leaf_nodes()):
                raise CommandError(f'Pending migrations on {alias}; migrate a private source copy/target first.')
        with connections[target].cursor() as cursor:
            cursor.execute("SELECT CONVERT_TZ('2026-01-01 00:00:00', 'UTC', 'Asia/Yekaterinburg'), @@SESSION.sql_mode")
            converted, mode = cursor.fetchone()
            if converted is None:
                raise CommandError('MySQL timezone tables are missing. Ask hosting support to load timezone tables for UTC and Asia/Yekaterinburg; analytics requires them.')
            if not {'STRICT_TRANS_TABLES', 'STRICT_ALL_TABLES'}.intersection(mode.split(',')):
                raise CommandError('MySQL strict SQL mode is required.')
        # All target tables must be transactional, including auth/session/admin tables.
        with connections[target].cursor() as cursor:
            cursor.execute('SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = %s', ['BASE TABLE'])
            if any(engine != 'InnoDB' for _, engine in cursor.fetchall()):
                raise CommandError('All target tables must use InnoDB.')
        for model in models:
            self.stdout.write(f'{model._meta.label}: source={model.objects.using(source).count()}, target={model.objects.using(target).count()}')
        if options['verify']:
            compare(models, source, target)
            self.stdout.write(self.style.SUCCESS('VERIFY OK: all transferred fields and relationships match.'))
            return
        for model in models:
            if model._meta.label not in GENERATED and model.objects.using(target).exists():
                raise CommandError(f'Target is not empty: {model._meta.label}. Nothing copied.')
        if not options['apply']:
            self.stdout.write(self.style.SUCCESS('CHECK OK: target empty; no data copied. Stop web writes and notification cron before --apply.'))
            return
        with transaction.atomic(using=target):
            for model in models:
                data = json.dumps(records(model, source), ensure_ascii=False)
                for obj in serializers.deserialize('json', data, using=target):
                    obj.save(using=target)
            compare(models, source, target)
        self.stdout.write(self.style.SUCCESS('TRANSFER OK: data and relationships verified; keep source snapshot for recovery.'))
