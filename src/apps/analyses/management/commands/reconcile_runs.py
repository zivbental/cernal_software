"""Reconcile durable submissions and interrupted worker leases."""

import time

from django.core.management.base import BaseCommand, CommandError

from apps.analyses.services import reconcile_runs


class Command(BaseCommand):
    help = "Retry unpublished runs and fail stale execution leases (never recompute science)."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=float, default=10)

    def handle(self, *args, **options):
        if options["interval"] < 1:
            raise CommandError("The reconciliation interval must be at least one second.")
        try:
            while True:
                self.stdout.write(str(reconcile_runs()))
                if not options["watch"]:
                    return
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            return
