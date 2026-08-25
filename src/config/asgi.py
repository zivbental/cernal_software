"""ASGI entry point. Unused in v1; present so the option exists without restructuring."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

from django.core.asgi import get_asgi_application

application = get_asgi_application()
