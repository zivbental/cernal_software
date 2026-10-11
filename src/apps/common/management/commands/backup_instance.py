"""Create a verified backup while platform and worker writes are stopped."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.common.backups import BackupError, create_backup


class Command(BaseCommand):
    help = "Back up SQLite, referenced media and durable result staging to a new archive."

    def add_arguments(self, parser):
        parser.add_argument("output")
        parser.add_argument("--maintenance-window", action="store_true")

    def handle(self, *args, **options):
        if not options["maintenance_window"]:
            raise CommandError("Stop web/worker writers first and pass --maintenance-window.")
        try:
            manifest = create_backup(
                connection,
                settings.MEDIA_ROOT,
                options["output"],
                staging_root=getattr(settings, "RUN_STAGING_ROOT", None),
            )
        except (BackupError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Verified backup written: {len(manifest['files'])} files.")
