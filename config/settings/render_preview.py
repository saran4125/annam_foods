"""Isolated SQLite catalog initializer for the PHP preview; never serves HTTP."""
import os
from pathlib import Path
from .local import *  # noqa: F401,F403
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": str(Path(os.environ.get("PREVIEW_DATA_ROOT", "/tmp/annam-php-preview")) / "reference.sqlite"),
}}
MEDIA_ROOT = str(Path(os.environ.get("PREVIEW_DATA_ROOT", "/tmp/annam-php-preview")) / "media")
