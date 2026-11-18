"""Build reproducible code-only PHP source and split-hosting update ZIPs."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'php-app'
DEST = ROOT / 'docs/php-rebuild'
DIRECTORIES = ('src', 'views', 'resources', 'bin', 'deploy', 'tests', 'public/assets')
DOCS = ('README.md', 'ARCHITECTURE.md', 'PARITY.md', 'UI-PARITY.md', 'SQLITE-HOSTINGER.md',
        'storage/sessions/.gitkeep', 'storage/logs/.gitkeep', '.env.example', 'router.php', 'hosting-check.php', 'public/index.php', 'public/.htaccess')


def source_files():
    for directory in DIRECTORIES:
        for path in sorted((APP / directory).rglob('*')):
            if path.is_symlink() or not path.is_file() or '__pycache__' in path.parts:
                continue
            if path.suffix.lower() in ('.sqlite', '.sqlite3', '.db', '.log', '.pyc', '.zip'):
                raise ValueError(f'Unexpected generated/private file: {path}')
            yield path
    for name in DOCS:
        path = APP / name
        if path.is_file():
            yield path


def write_zip(filename, files, instruction):
    checksums = {}
    with zipfile.ZipFile(DEST / filename, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, target in sorted(files, key=lambda item: item[1]):
            data = path.read_bytes()
            info = zipfile.ZipInfo(target, (2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
            checksums[target] = hashlib.sha256(data).hexdigest()
        for name, data in [('CHECKSUMS.json', json.dumps(checksums, indent=2, sort_keys=True)),
                           ('UPDATE-EXISTING-SITE.txt', instruction)]:
            info = zipfile.ZipInfo(name, (2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(DEST / filename) as archive:
        assert archive.testzip() is None
        assert any(name.endswith('fonts/dejavusans.z') for name in archive.namelist())
        for name, digest in checksums.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest


if __name__ == '__main__':
    files = list(source_files())
    instruction = (DEST / 'PAYMENT-RECEIPT-UPDATE.md').read_text()
    write_zip('annam-foods-php-source.zip', [(p, 'php-app/' + p.relative_to(APP).as_posix()) for p in files], instruction)
    update = []
    for path in files:
        relative = path.relative_to(APP).as_posix()
        if relative.startswith('public/assets/'):
            update.append((path, 'public_html/' + relative.removeprefix('public/')))
        elif not relative.startswith('public/') and relative not in ('storage/sessions/.gitkeep', 'storage/logs/.gitkeep', '.env.example', 'router.php', 'hosting-check.php'):
            update.append((path, 'annam-private/' + relative))
    write_zip('annam-foods-php-ui-update.zip', update, instruction)
    names = ('annam-foods-php-source.zip', 'annam-foods-php-ui-update.zip', 'annam-foods-php-reviewed-database.zip')
    (DEST / 'PHP-ZIPS-SHA256.txt').write_text(''.join(f'{hashlib.sha256((DEST / name).read_bytes()).hexdigest()}  {name}\n' for name in names))
    print('Verified code ZIPs, member hashes, compressed fonts and archive integrity.')
