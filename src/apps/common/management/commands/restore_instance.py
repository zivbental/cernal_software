"""Restore a verified backup into explicitly supplied empty targets."""

from django.core.management.base import BaseCommand, CommandError

from apps.common.backups import BackupError, restore_backup


class Command(BaseCommand):
    help = "Verify a backup and restore it to new SQLite/media/staging paths."

    def add_arguments(self, parser):
        parser.add_argument("archive")
        parser.add_argument("--database", required=True)
        parser.add_argument("--media", required=True)
        parser.add_argument("--staging")

    def handle(self, *args, **options):
        try:
            manifest = restore_backup(
                options["archive"],
                options["database"],
                options["media"],
                staging_target=options["staging"],
            )
        except (BackupError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Verified restore completed: {len(manifest['files'])} files.")
