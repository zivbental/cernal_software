"""Populate the database with a browsable demo run.

Drives ``MockEngine`` through the real import path, so what lands in the database is
exactly what Step 3's run lifecycle will produce — not hand-written fixtures that drift
away from reality.

    ./do manage seed_demo
    ./do manage seed_demo --reset --candidates 30
"""

import tempfile
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.analyses.models import AnalysisRun, RunStatus
from apps.common.checksums import sha256_bytes
from apps.datasets.models import Dataset, ValidationStatus
from apps.projects.models import Project
from apps.results.models import Annotation, DecisionTag
from apps.results.services import import_job_result
from engine.client import load_engine
from engine.contract import SCHEMA_VERSION, JobRequest

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-password-123"

DATASET_CSV = """gene_id,base_expression,target_expression,log2fc,padj
lacZ,0.82,6.41,2.97,0.0007
rpoS,2.11,0.44,-2.26,0.0041
katG,1.24,5.93,2.26,0.0019
soxS,0.31,4.77,3.94,0.0002
gadA,3.02,7.85,1.38,0.0113
fliC,5.60,1.02,-2.46,0.0033
ompF,1.95,4.10,1.07,0.0208
zwf,0.74,3.88,2.39,0.0016
"""


class Command(BaseCommand):
    help = "Create a demo user, project, dataset and completed analysis run."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data before seeding.",
        )
        parser.add_argument(
            "--candidates",
            type=int,
            default=18,
            help="How many candidates the mock engine should generate (default 18).",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        user = self._user()

        if options["reset"]:
            self.stdout.write(f"Removed {self._reset(user)} existing demo objects.")

        project = Project.objects.create(
            owner=user,
            name=f"Lactose-to-oxidative-stress switch ({uuid.uuid4().hex[:6]})",
            organism="E. coli",
            biological_objective=(
                "Detect the transition from lactose metabolism to oxidative stress response "
                "and drive GFP expression when both signals are present."
            ),
        )

        dataset = self._dataset(project, user)
        run = self._run(project, dataset, user, options["candidates"])

        self.stdout.write(self.style.SUCCESS("\nDemo data created.\n"))
        self.stdout.write(f"  User      {DEMO_USERNAME} / {DEMO_PASSWORD}")
        self.stdout.write(f"  Project   {project.name}")
        self.stdout.write(f"  Dataset   {dataset.name} ({dataset.size_bytes} B)")
        self.stdout.write(f"  Run       {run.id}  [{run.get_status_display()}]")
        self.stdout.write(
            f"  Results   {run.candidates.count()} candidates "
            f"({run.candidates.filter(is_rejected=True).count()} rejected), "
            f"{run.artifacts.count()} artifacts"
        )
        self.stdout.write("\n  Browse at http://localhost:8000/admin/\n")

    # -- helpers --

    @staticmethod
    def _reset(user) -> int:
        """Delete in dependency order.

        AnalysisRun holds PROTECT references to both its project and its dataset, so
        deleting projects first raises ProtectedError.
        """
        removed = 0
        for queryset in (
            AnalysisRun.objects.filter(project__owner=user),
            Dataset.objects.filter(project__owner=user),
            Project.objects.filter(owner=user),
        ):
            count, _ = queryset.delete()
            removed += count
        return removed

    def _user(self):
        model = get_user_model()
        user, created = model.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={"email": "demo@example.org", "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
        return user

    def _dataset(self, project, user) -> Dataset:
        payload = DATASET_CSV.encode("utf-8")
        dataset = Dataset(
            project=project,
            name="expression_lactose_vs_oxidative.csv",
            checksum_sha256=sha256_bytes(payload),
            size_bytes=len(payload),
            schema_version="1",
            validation_status=ValidationStatus.VALID,
            validation_report={
                "rows": len(DATASET_CSV.strip().splitlines()) - 1,
                "columns": ["gene_id", "base_expression", "target_expression", "log2fc", "padj"],
                "errors": [],
                "warnings": [],
            },
            uploaded_by=user,
        )
        dataset.file.save(dataset.name, ContentFile(payload), save=False)
        dataset.save()
        return dataset

    def _run(self, project, dataset, user, candidate_count: int) -> AnalysisRun:
        now = timezone.now()
        run = AnalysisRun.objects.create(
            project=project,
            dataset=dataset,
            created_by=user,
            idempotency_key=f"seed-demo-{uuid.uuid4().hex}",
            params_snapshot={"max_triggers": 2, "mock": {"candidate_count": candidate_count}},
            gate_families=["toehold"],
            scoring_profile="default",
            seed=42,
            status=RunStatus.RUNNING,
            stage="Scoring and ranking candidates",
            progress_pct=90,
            submitted_at=now,
            started_at=now,
        )

        # A temporary output dir: import_job_result copies artifact bytes into the
        # Artifact FileField, so the engine's scratch space is not needed afterwards.
        with tempfile.TemporaryDirectory() as output_dir:
            request = JobRequest(
                schema_version=SCHEMA_VERSION,
                run_id=str(run.id),
                idempotency_key=run.idempotency_key,
                input_path=dataset.file.path,
                input_checksum=dataset.checksum_sha256,
                organism=project.organism,
                params=run.params_snapshot,
                gate_families=run.gate_families,
                scoring_profile=run.scoring_profile,
                seed=run.seed,
                output_dir=output_dir,
            )
            engine = load_engine("engine.client.MockEngine")
            result = engine.run(request, lambda pct, stage: True)
            import_job_result(run, result, output_dir)

        run.status = RunStatus.COMPLETED
        run.stage = "Completed"
        run.progress_pct = 100
        run.engine_version = result.engine_version
        run.warnings = result.warnings
        run.finished_at = timezone.now()
        run.save()

        self._annotate(run, user)
        return run

    def _annotate(self, run, user) -> None:
        """A couple of researcher decisions, so the annotation UI has something to show."""
        top = list(run.candidates.filter(is_rejected=False).order_by("rank")[:2])
        if top:
            Annotation.objects.create(
                candidate=top[0],
                author=user,
                text="Strong separation and low predicted leakage. Shortlist for synthesis.",
                decision_tag=DecisionTag.SYNTHESIZE,
            )
        if len(top) > 1:
            Annotation.objects.create(
                candidate=top[1],
                author=user,
                text="Good score but accessibility looks marginal — worth a second look.",
                decision_tag=DecisionTag.PINNED,
            )
