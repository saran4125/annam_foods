"""Settings shared by every environment."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "huey.contrib.djhuey",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.tenancy",
    "apps.catalog",
    "apps.delivery",
    "apps.content",
    "apps.storefront",
    "apps.messaging",
    "apps.orders",
    "apps.jobs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Resolves Host -> Tenant. Must sit after auth so admin/staff views
    # can still resolve a tenant from the session when on the admin host.
    "apps.tenancy.middleware.TenantMiddleware",
    # /admin/ only on the platform host (FIX-11).
    "apps.tenancy.middleware.PlatformAdminGuard",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.tenancy.context.tenant",
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django 6 will default URLField to https; opt in now so the behaviour
# doesn't change under us at upgrade time.
FORMS_URLFIELD_ASSUME_HTTPS = True

# Host that serves the SEER super-admin, not any tenant storefront.
PLATFORM_HOST = "admin.localhost"

HUEY = {
    "name": "seerkitchen",
    "huey_class": "huey.RedisHuey",
    "connection": {"url": os.environ.get("REDIS_URL", "redis://127.0.0.1:6389/0")},
    "consumer": {"workers": 2, "worker_type": "thread", "periodic": True},
    "immediate": False,
}
