"""Isolated SQLite catalog initializer for the free PHP preview; never serves HTTP."""
from .local import *  # noqa: F401,F403
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": "/tmp/annam-php-preview/reference.sqlite",
}}
MEDIA_ROOT = "/tmp/annam-php-preview/media"
