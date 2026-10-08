"""Conservative retention tooling for known terminal execution staging directories."""

import json
import shutil
import time
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.analyses.models import AnalysisRun, RunStatus


class Command(BaseCommand):
    help = "Report terminal result staging older than 30 days; --apply explicitly removes it."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--include-failed", action="store_true")
        parser.add_argument("--older-than-days", type=float, default=30)

    def handle(self, *args, **options):
        days = options["older_than_days"]
        if not 1 <= days <= 3650:
            raise CommandError("Staging retention grace must be between 1 and 3650 days.")
        root = Path(settings.RUN_STAGING_ROOT)
        if root.is_symlink():
            raise CommandError("The staging root must not be a symlink.")
        root = root.resolve()
        threshold = time.time() - days * 86400
        statuses = [RunStatus.COMPLETED, RunStatus.CANCELLED]
        if options["include_failed"]:
            statuses.append(RunStatus.FAILED)
        selected = []
        if root.exists():
            for directory in root.iterdir():
                if directory.is_symlink() or not directory.is_dir():
                    continue
                try:
                    run_id = UUID(directory.name)
                except ValueError:
                    continue
                run = AnalysisRun.objects.filter(pk=run_id, status__in=statuses).first()
                if run is None or not getattr(run, "execution_token", None):
                    continue
                lease = directory / str(run.execution_token)
                if lease.is_symlink() or not lease.is_dir():
                    continue
                contents = [lease, *lease.rglob("*")]
                if any(path.is_symlink() for path in contents):
                    continue
                latest = max(path.stat().st_mtime for path in contents)
                if latest >= threshold:
                    continue
                if options["apply"]:
                    if not AnalysisRun.objects.filter(
                        pk=run.pk, execution_token=run.execution_token, status__in=statuses
                    ).exists():
                        continue
                    shutil.rmtree(lease)
                selected.append(lease.relative_to(root).as_posix())
        self.stdout.write(
            json.dumps(
                {
                    "applied": options["apply"],
                    "include_failed": options["include_failed"],
                    "staging_directories": sorted(selected),
                },
                indent=2,
            )
        )
