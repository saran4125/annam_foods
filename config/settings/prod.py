"""Production refuses to start without explicit database and secret settings."""
import os
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F401,F403

required = ["SECRET_KEY", "SECRETS_KEY", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "ALLOWED_HOSTS", "REDIS_URL"]
missing = [name for name in required if not os.environ.get(name)]
if missing:
    raise ImproperlyConfigured("Missing required production settings: " + ", ".join(missing))
DEBUG = False
SECRET_KEY = os.environ["SECRET_KEY"]
SECRETS_KEY = os.environ["SECRETS_KEY"]
ALLOWED_HOSTS = [x.strip() for x in os.environ["ALLOWED_HOSTS"].split(",") if x.strip()]
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "NAME": os.environ["POSTGRES_DB"],
    "USER": os.environ["POSTGRES_USER"], "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    "HOST": os.environ["POSTGRES_HOST"], "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    "CONN_MAX_AGE": 60,
}}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
