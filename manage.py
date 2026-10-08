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

    requested_settings = os.environ["DJANGO_SETTINGS_MODULE"]
    for index, argument in enumerate(sys.argv):
        if argument.startswith("--settings="):
            requested_settings = argument.partition("=")[2]
        elif argument == "--settings" and index + 1 < len(sys.argv):
            requested_settings = sys.argv[index + 1]

    # Local runserver must include the worker even when started without ./do dev.
    if (
        len(sys.argv) > 1
        and sys.argv[1] == "runserver"
        and requested_settings == "config.settings.dev"
        and os.environ.get("CERNAL_SUPERVISED_CHILD") != "1"
    ):
        sys.argv[1] = "devserver"

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
