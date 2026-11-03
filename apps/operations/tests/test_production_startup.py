"""Production logging must initialize before Django's app registry is populated."""
import os
import subprocess
import sys
from pathlib import Path


def test_production_logging_does_not_import_database_models_during_setup():
    root = Path(__file__).resolve().parents[3]
    env = {
        **os.environ,
        'DJANGO_SETTINGS_MODULE': 'config.settings.prod',
        'SECRET_KEY': 'isolated-production-startup-test-not-a-real-secret',
        'SECRETS_KEY': 'isolated-production-startup-test-not-a-real-secret',
        'POSTGRES_DB': 'startup_check',
        'POSTGRES_USER': 'startup_check',
        'POSTGRES_PASSWORD': 'startup_check',
        'POSTGRES_HOST': '127.0.0.1',
        'ALLOWED_HOSTS': 'startup.invalid',
        'STORE_SLUG': 'annam',
    }
    result = subprocess.run(
        [sys.executable, '-c', 'import django; django.setup(); print("production startup OK")'],
        cwd=root, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert 'production startup OK' in result.stdout
