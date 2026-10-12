"""Keep the supported Linux worker and explain the Windows dependency limitation."""

import sys

from django.core.management.base import CommandError
from django_q.management.commands.qcluster import Command as QClusterCommand


class Command(QClusterCommand):
    def handle(self, *args, **options):
        if sys.platform == "win32":
            raise CommandError(
                "The locked Django Q2 worker requires fork, unavailable on native Windows. "
                "Run the application and worker together in WSL2; see docs/windows-worker.md."
            )
        return super().handle(*args, **options)
