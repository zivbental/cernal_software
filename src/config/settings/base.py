"""Settings shared by every environment.

Rule (docs/architecture.md §12): no `if DEBUG:` branching in this file.
Environment-specific behaviour belongs in dev.py / prod.py.
"""

from pathlib import Path

import environ

# BASE_DIR is the repo root: src/config/settings/base.py -> up 4.
BASE_DIR = Path(__file__).resolve().parents[3]
VAR_DIR = BASE_DIR / "var"

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# --- Applications ---------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "django_q",
]

# Dotted paths, per docs/architecture.md §4.1.
LOCAL_APPS = [
    "apps.accounts",
    "apps.common",
    "apps.projects",
    "apps.datasets",
    "apps.analyses",
    "apps.results",
    "apps.web",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "src" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Identity -------------------------------------------------------------------

# Set before the first migration. Swapping this later is a well-known Django trap.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Database -------------------------------------------------------------------

DATABASES = {
    "default": env.db_url("DATABASE_URL", default=f"sqlite:///{VAR_DIR / 'cernal.db'}"),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Internationalization -------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static & media -------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = VAR_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "src" / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = env.path("MEDIA_ROOT", default=VAR_DIR / "media")

# Artifacts are served through an authorized view, never by a static handler (§7.2).

# --- Uploads --------------------------------------------------------------------

MAX_DATASET_MB = env.int("MAX_DATASET_MB", default=100)
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_DATASET_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- Background work (docs/architecture.md §9) --------------------------------

Q_CLUSTER = {
    "name": "cernal",
    "orm": "default",  # ORM broker: the queue is a table, no Redis to run or back up.
    "workers": 1,  # Concurrency of 1 removes a class of SQLite write contention.
    "timeout": 60 * 60,  # An analysis is long-running and rare.
    "retry": 60 * 60 + 60,  # Must exceed timeout, or django-q2 re-queues running tasks.
    "max_attempts": 1,  # Never silently re-run an expensive computation.
    "save_limit": 500,
    "catch_up": False,
}

# --- Engine (docs/architecture.md §3, §10) ------------------------------------

# Dotted path to an engine.client.EngineClient implementation.
CERNAL_ENGINE = env.str("CERNAL_ENGINE", default="engine.client.MockEngine")

# --- Logging --------------------------------------------------------------------

LOG_LEVEL = env.str("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "propagate": False},
    },
}
