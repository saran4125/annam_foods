"""Production refuses to start without explicit database and secret settings."""
import os
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F401,F403

required = ["SECRET_KEY", "SECRETS_KEY", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "ALLOWED_HOSTS", "PLATFORM_HOST"]
missing = [name for name in required if not os.environ.get(name)]
if missing:
    raise ImproperlyConfigured("Missing required production settings: " + ", ".join(missing))
DEBUG = False
SECRET_KEY = os.environ["SECRET_KEY"]
SECRETS_KEY = os.environ["SECRETS_KEY"]
# A Fernet key is 32 random bytes, base64-encoded. Platforms that can only
# generate random text (Render) are fine too: any long random value is hashed
# into a valid key, deterministically, so it stays stable across restarts.
try:
    from cryptography.fernet import Fernet

    Fernet(SECRETS_KEY.encode())
except Exception:
    import base64
    import hashlib

    if len(SECRETS_KEY) < 32:
        raise ImproperlyConfigured("SECRETS_KEY must be a Fernet key or a random string of 32+ characters.")
    SECRETS_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRETS_KEY.encode()).digest()).decode()
ALLOWED_HOSTS = [x.strip() for x in os.environ["ALLOWED_HOSTS"].split(",") if x.strip()]
PLATFORM_HOST = os.environ["PLATFORM_HOST"].strip().lower()
if "*" not in ALLOWED_HOSTS and PLATFORM_HOST not in ALLOWED_HOSTS:
    raise ImproperlyConfigured("PLATFORM_HOST must also appear in ALLOWED_HOSTS")
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "NAME": os.environ["POSTGRES_DB"],
    "USER": os.environ["POSTGRES_USER"], "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    "HOST": os.environ["POSTGRES_HOST"], "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    "CONN_MAX_AGE": 60,
}}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]   # the platform's health probe is plain HTTP

# WhiteNoise serves the collected static files straight from the app, so no
# separate web server or CDN is needed for CSS, JS and icons.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
ADMINS = [(x.rsplit("@", 1)[0], x) for x in os.environ.get("ADMIN_EMAILS", "").split(",") if "@" in x]
EMAIL_SUBJECT_PREFIX = "[SeerKitchen] "
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "stderr": {"class": "logging.StreamHandler"},
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR"},
    },
    "root": {"handlers": ["stderr", "mail_admins"], "level": "WARNING"},
    "loggers": {
        "django.request": {"handlers": ["stderr", "mail_admins"], "level": "ERROR", "propagate": False},
    },
}

MEDIA_ROOT = os.environ.get("PUBLIC_MEDIA_ROOT", str(BASE_DIR / "media"))
PRIVATE_BILLS_ROOT = os.environ.get("PRIVATE_BILLS_ROOT", str(BASE_DIR / "private-bills"))
STATIC_ROOT = os.environ.get("STATIC_ROOT", str(BASE_DIR / "staticfiles"))
STORAGES = {
    "default": {
        "BACKEND": os.environ.get("PUBLIC_MEDIA_BACKEND", "django.core.files.storage.FileSystemStorage"),
        "OPTIONS": {"location": MEDIA_ROOT, "base_url": MEDIA_URL},
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "private_bills": {
        "BACKEND": os.environ.get("PRIVATE_BILLS_BACKEND", "django.core.files.storage.FileSystemStorage"),
        "OPTIONS": {"location": PRIVATE_BILLS_ROOT},
    },
}

# Dish photos and owner uploads live on a persistent disk (PUBLIC_MEDIA_ROOT).
# Without object storage Django serves them itself; fine at this scale, and
# the files stay on the disk across deploys. Set SERVE_MEDIA=0 once a CDN or
# bucket serves /media/ instead.
SERVE_MEDIA = os.environ.get("SERVE_MEDIA", "1") == "1"
