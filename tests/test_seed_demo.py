"""The seed_demo command (docs/software-design.md §13 Step 2, "Done when").

It drives MockEngine through the real import path, so it doubles as an end-to-end check
that the model layer can hold a complete engine result.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.analyses.models import AnalysisRun, RunStatus
from apps.datasets.models import Dataset, ValidationStatus
from apps.projects.models import Project
from apps.results.models import Annotation, Artifact, Candidate, CandidateMetric
from engine.scoring.profiles import DEFAULT_V1


@pytest.fixture
def seeded(db, media_root):
    out = StringIO()
    call_command("seed_demo", "--candidates", "12", stdout=out)
    return out.getvalue()


def test_seed_demo_creates_a_browsable_run(seeded):
    run = AnalysisRun.objects.get()

    assert run.status == RunStatus.COMPLETED
    assert run.progress_pct == 100
    assert run.finished_at is not None
    assert run.engine_version.startswith("mock")


def test_seed_demo_creates_the_whole_object_graph(seeded):
    assert Project.objects.count() == 1
    assert Dataset.objects.get().validation_status == ValidationStatus.VALID
    assert Candidate.objects.count() == 12
    # One row per metric the scoring profile declares.
    assert CandidateMetric.objects.count() == 12 * len(DEFAULT_V1.metrics)
    assert Artifact.objects.exists()
    assert Annotation.objects.exists()


def test_seeded_candidates_are_ranked_and_scored(seeded):
    accepted = Candidate.objects.filter(is_rejected=False).order_by("rank")

    assert accepted.exists()
    ranks = list(accepted.values_list("rank", flat=True))
    assert ranks == list(range(1, len(ranks) + 1))
    assert all(c.overall_score is not None for c in accepted)


def test_seeded_artifacts_are_readable(seeded):
    for artifact in Artifact.objects.all():
        assert artifact.file.storage.exists(artifact.file.name)
        assert artifact.size_bytes > 0


def test_seed_demo_reports_the_login_it_created(seeded):
    assert "demo" in seeded
    assert "Browse at" in seeded


def test_seed_demo_reset_clears_previous_data(db, media_root):
    call_command("seed_demo", "--candidates", "5", stdout=StringIO())
    call_command("seed_demo", "--candidates", "5", "--reset", stdout=StringIO())

    assert Project.objects.count() == 1
    assert AnalysisRun.objects.count() == 1
