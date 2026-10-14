# Run the Django storefront on this machine: SQLite, no Docker, no Postgres.
#   powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
# Then open http://annam.localhost:8000/  (*.localhost resolves to this PC in Chrome/Edge)
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv-win\Scripts\python.exe"

if (-not (Test-Path $py)) {
    python -m venv .venv-win
    & $py -m pip install -q "django>=5.0,<6.0" cryptography markdown pillow python-dotenv `
        "psycopg[binary]>=3.2,<4" "huey>=2.5,<3" "redis>=5,<7" "pyyaml>=6,<7" pytest pytest-django
}

$env:DJANGO_SETTINGS_MODULE = "config.settings.local"
& $py manage.py migrate --noinput
if (-not (Test-Path "local.sqlite3") -or (Get-Item "local.sqlite3").Length -lt 100000) { & $py scripts\seed_local.py }
& $py manage.py runserver 127.0.0.1:8000
