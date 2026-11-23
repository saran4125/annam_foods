"""Create a disposable PHP SQLite seed from committed reference data only."""
import json
import os
from pathlib import Path
import runpy
import sqlite3
import sys
from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DIRECTORY = Path(os.environ.get('PREVIEW_DATA_ROOT', '/tmp/annam-php-preview'))
if str(DIRECTORY) not in ('/tmp/annam-php-preview', '/var/data/annam-php-preview'):
    raise RuntimeError('Unsupported preview data directory')
INITIALIZED = DIRECTORY / '.database-initialized'
DESTINATION = DIRECTORY / 'annam.sqlite'
if DESTINATION.exists():
    with sqlite3.connect(f'file:{DESTINATION}?mode=ro', uri=True) as existing:
        if existing.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise RuntimeError('Existing database failed integrity check; restore a backup, do not reseed')
    INITIALIZED.touch(exist_ok=True)
    print('Existing preview database preserved, including latest stock settings.')
    sys.exit(0)
if INITIALIZED.exists():
    raise RuntimeError('Previously initialized database is missing; restore a backup instead of seeding defaults')
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.render_preview'
import django
django.setup()
from django.core.management import call_command
call_command('migrate', interactive=False, verbosity=0)
try:
    runpy.run_path(str(ROOT / 'scripts/seed_local.py'), run_name='__main__')
except SystemExit as exc:
    if exc.code not in (None, 0):
        raise
source = sqlite3.connect(DIRECTORY / 'reference.sqlite')
source.row_factory = sqlite3.Row
pending = DIRECTORY / 'annam.pending.sqlite'
pending.unlink(missing_ok=True)
target = sqlite3.connect(pending)
target.executescript((ROOT / 'php-app/resources/sqlite-schema.sql').read_text())
target.execute('PRAGMA foreign_keys=OFF')
types = json.loads((ROOT / 'php-app/resources/sqlite-types.json').read_text())
tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
# Additive PHP fields absent from the older Django reference schema.
defaults = {
    'catalog_menuitem': {'admin_notes': '', 'in_stock': 1, 'weight': ''},
    'catalog_slot': {'order_days_before': 1, 'order_opens_at': '00:00:00'},
}
with target:
    for table, fields in types.items():
        if table not in tables:
            continue
        for row in source.execute(f'SELECT * FROM "{table}"'):
            extra = defaults.get(table, {})
            names = [name for name in fields if name in row.keys() or name in extra]
            values = []
            for name in names:
                value = row[name] if name in row.keys() else extra[name]
                if value is not None:
                    kind = fields[name]
                    if kind == 'DECIMAL_TEXT':
                        value = format(Decimal(str(value)).quantize(Decimal('0.01')), 'f')
                    elif kind == 'TIMESTAMP':
                        stamp = datetime.fromisoformat(value)
                        if stamp.tzinfo:
                            stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
                        value = stamp.strftime('%Y-%m-%d %H:%M:%S.%f')
                    elif kind.startswith('UUID'):
                        value = str(UUID(value))
                values.append(value)
            columns = ','.join('"'+name+'"' for name in names)
            target.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({",".join("?" for _ in names)})', values)
if target.execute('PRAGMA foreign_key_check').fetchone():
    raise RuntimeError('Preview seed relationships failed validation')
if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
    raise RuntimeError('Preview seed integrity failed validation')
target.close()
source.close()
pending.chmod(0o600)
pending.rename(DESTINATION)
INITIALIZED.touch(exist_ok=True)
(DIRECTORY / 'new-catalog').touch()
print('PHP SQLite preview initialized; no external database used.')
