"""Retry a retained scientific result into a new immutable run."""

from django.core.management.base import BaseCommand, CommandError

from apps.analyses.models import AnalysisRun
from apps.analyses.services import RunError, retry_result_import


class Command(BaseCommand):
    help = "Import retained output from a failed run into a new run without recalculating science."

    def add_arguments(self, parser):
        parser.add_argument("run_id")

    def handle(self, *args, **options):
        try:
            source = AnalysisRun.objects.get(pk=options["run_id"])
            run = retry_result_import(source)
        except (AnalysisRun.DoesNotExist, RunError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Created completed import attempt {run.pk} from {source.pk}")
