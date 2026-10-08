"""Report or remove old unreferenced upload/artifact files; default is dry-run."""

import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.datasets.models import Dataset
from apps.results.models import Artifact


class Command(BaseCommand):
    help = "Report media orphans older than a grace period; use --apply to delete them."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--older-than-hours", type=float, default=24)

    def handle(self, *args, **options):
        grace = options["older_than_hours"]
        if not 1 <= grace <= 24 * 3650:
            raise CommandError("Grace period must be between 1 hour and 10 years.")
        root = Path(settings.MEDIA_ROOT).resolve()
        referenced = set(Dataset.objects.values_list("file", flat=True))
        referenced.update(Artifact.objects.values_list("file", flat=True))
        threshold = time.time() - grace * 3600
        orphaned = []
        # Limit cleanup to managed file namespaces. Staged engine results and backups
        # have a separate recovery/retention policy and must not be removed here.
        for namespace in ("datasets", "artifacts"):
            directory = root / namespace
            if not directory.is_dir() or directory.is_symlink():
                continue
            for source in directory.rglob("*"):
                if source.is_symlink() or not source.is_file():
                    continue
                if not source.resolve().is_relative_to(root):
                    continue
                relative = source.relative_to(root).as_posix()
                if relative in referenced or source.stat().st_mtime >= threshold:
                    continue
                # Recheck against current database references immediately before removal.
                if options["apply"]:
                    if (
                        Dataset.objects.filter(file=relative).exists()
                        or Artifact.objects.filter(file=relative).exists()
                    ):
                        continue
                    source.unlink()
                orphaned.append(relative)
        missing = sorted(name for name in referenced if name and not (root / name).is_file())
        self.stdout.write(
            json.dumps(
                {
                    "applied": options["apply"],
                    "orphans": sorted(orphaned),
                    "missing_referenced_files": missing,
                },
                indent=2,
            )
        )
