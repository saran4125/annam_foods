"""One-time importer only; never used for the running app or test suite."""
import os
from pathlib import Path
from .dev import *  # noqa: F401,F403

DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": Path(os.environ["SEERKITCHEN_LEGACY_DB"]),
}}
