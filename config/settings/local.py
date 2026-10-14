"""Run the storefront on a laptop with nothing but Python.

SQLite instead of PostgreSQL, tasks run inline instead of through Redis. For
looking at the UI and clicking around only -- tests and production stay on
PostgreSQL (`dev.py` / `prod.py`).

    python manage.py migrate --settings=config.settings.local
    python manage.py runserver --settings=config.settings.local
"""
from .dev import *  # noqa: F401,F403

DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": BASE_DIR / "local.sqlite3",
}}
HUEY = {**HUEY, "immediate": True}
