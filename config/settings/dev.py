import os
from dotenv import load_dotenv

from .base import *  # noqa: F401,F403
load_dotenv(BASE_DIR / ".env")
HUEY["connection"]["url"] = os.environ.get("REDIS_URL", "redis://127.0.0.1:6389/0")
PLATFORM_HOST = os.environ.get("PLATFORM_HOST", PLATFORM_HOST).strip().lower()

DEBUG = os.environ.get("DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-a-secret-change-in-production")
# The tenant middleware is the dev hostname allowlist: it returns 404 for
# unregistered domains. Django's Host validation would otherwise return 400
# before that tenant-specific, fail-closed response can run. Production uses
# explicit ALLOWED_HOSTS from the environment.
ALLOWED_HOSTS = ["*"]

# Encrypts TenantSecrets. This throwaway value is fine for development and for
# tests; production settings must require a real key from the environment and
# refuse to start without one.
SECRETS_KEY = os.environ.get(
    "SECRETS_KEY", "8ZQ1kCq0nTQ0Y1nZ5vX2wJ7bF3sD9gH6kL0pR4tU8yM="
)

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("POSTGRES_DB", "seerkitchen"),
    "USER": os.environ.get("POSTGRES_USER", "seerkitchen"),
    "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
    "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    "PORT": os.environ.get("POSTGRES_PORT", "5439"),
    "CONN_MAX_AGE": 60,
}}

TENANT_BASE_DOMAIN = os.environ.get("TENANT_BASE_DOMAIN", "localhost").strip().lower()
