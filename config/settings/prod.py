"""Production refuses to start without explicit database and secret settings."""
import os
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F401,F403

required = ["SECRET_KEY", "SECRETS_KEY", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "ALLOWED_HOSTS"]
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
PLATFORM_HOST = os.environ.get("PLATFORM_HOST", PLATFORM_HOST).strip().lower()
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "NAME": os.environ["POSTGRES_DB"],
    "USER": os.environ["POSTGRES_USER"], "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    "HOST": os.environ["POSTGRES_HOST"], "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    "CONN_MAX_AGE": int(os.environ.get('DB_CONN_MAX_AGE','60')),
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {"connect_timeout":5,"sslmode":os.environ.get('POSTGRES_SSLMODE','require'),
                "options":'-c statement_timeout='+os.environ.get('DB_STATEMENT_TIMEOUT_MS','15000')+' -c lock_timeout=5000'},
}}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]   # the platform's health probe is plain HTTP

# WhiteNoise serves the collected static files straight from the app, so no
# separate web server or CDN is needed for CSS, JS and icons.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
ADMINS = [(x.rsplit("@", 1)[0], x) for x in os.environ.get("ADMIN_EMAILS", "").split(",") if "@" in x]
EMAIL_SUBJECT_PREFIX = "[Annam Foods] "
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"private": {"()": "apps.operations.security.PrivateLogFormatter"}},
    "handlers": {
        "stderr": {"class": "logging.StreamHandler", "formatter":"private"},
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR"},
    },
    "root": {"handlers": ["stderr", "mail_admins"], "level": "WARNING"},
    "loggers": {
        "django.request": {"handlers": ["stderr", "mail_admins"], "level": "ERROR", "propagate": False},
    },
}

MEDIA_ROOT = os.environ.get("PUBLIC_MEDIA_ROOT", str(BASE_DIR / "media"))
# Absolute on purpose: STORAGES below is built from this raw value (not from the
# script-prefixed settings.MEDIA_URL), and a relative "media/" resolves against
# the current page, so /menu/ would look for /menu/media/... and 404.
MEDIA_URL = "/media/"
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

# Never expose historical/demo kitchens from the production service.
STORE_SLUG = os.environ.get("STORE_SLUG", "annam").strip().lower() or "annam"

# Explicit proxy trust: only enable for a gateway that overwrites/appends client IPs.
TRUSTED_PROXY_HOPS = int(os.environ.get('TRUSTED_PROXY_HOPS','0'))
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8*60*60
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
DEFAULT_EXCEPTION_REPORTER_FILTER = 'apps.operations.security.PrivateExceptionReporterFilter'
READINESS_CHECK_STORAGE = os.environ.get('READINESS_CHECK_STORAGE','1')=='1'
REQUIRE_WORKER_HEARTBEAT = os.environ.get('REQUIRE_WORKER_HEARTBEAT','0')=='1'
STORAGE_PERSISTENT = os.environ.get('STORAGE_PERSISTENT','0')=='1'
if os.environ.get('REQUIRE_DURABLE_STORAGE','0')=='1':
    from pathlib import Path
    if not STORAGE_PERSISTENT or any(Path(root).resolve().is_relative_to('/tmp') for root in (MEDIA_ROOT,PRIVATE_BILLS_ROOT)):
        raise ImproperlyConfigured('Durable public media and private bill storage must be configured.')

ENABLE_TRANSACTIONAL_MESSAGES = os.environ.get('ENABLE_TRANSACTIONAL_MESSAGES','0')=='1'

DEFAULT_EXCEPTION_REPORTER = 'apps.operations.security.PrivateExceptionReporter'
