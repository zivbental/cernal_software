#!/usr/bin/env python
"""Django management entry point.

Lives at the repo root rather than in src/ so that pytest, ruff and editors all root
naturally, while the Python packages keep a clean src layout.
See docs/software-design.md §4.1.
"""

import os
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
