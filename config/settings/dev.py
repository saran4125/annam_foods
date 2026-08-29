import os
from pathlib import Path

from .base import *  # noqa: F401,F403

DEBUG = True
SECRET_KEY = "dev-only-not-a-secret-change-in-production"
ALLOWED_HOSTS = ["*"]

# The dev database deliberately lives OUTSIDE the project directory.
# The project folder is a synced/mounted volume and SQLite's file locking is
# unreliable there -- you get "disk I/O error" on the first write. Postgres
# replaces this before Phase 3 anyway, where real row locking matters for
# invoice numbering.
DB_PATH = Path(
    os.environ.get("SEERKITCHEN_DB", Path.home() / ".seerkitchen" / "dev.sqlite3")
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_PATH,
    }
}
