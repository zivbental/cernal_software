"""Local development settings. Never used on the VPS."""

from pathlib import Path

from .base import *  # noqa: F403
from .base import MEDIA_ROOT, STATIC_ROOT, VAR_DIR, env

DEBUG = True

SECRET_KEY = env.str(
    "SECRET_KEY",
    default="dev-only-insecure-key-do-not-use-in-production",
)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Create the runtime directories so a fresh clone works without manual setup.
for _path in (
    VAR_DIR,
    VAR_DIR / "logs",
    STATIC_ROOT,
    MEDIA_ROOT,
    Path(MEDIA_ROOT) / "datasets",
    Path(MEDIA_ROOT) / "artifacts",
):
    Path(_path).mkdir(parents=True, exist_ok=True)
