"""Submits the shared fixture (clients/fixtures/) against a real, running MockEngine
server and checks the exact candidate column set — the mechanism that is meant to keep
three language clients honest (docs/public-api.md §11.4).

No worker process runs a background queue during this test, so the fixture's
idempotency_key is pre-seeded as an already-COMPLETED run: submit_run's idempotent
resubmission then returns it immediately, over real HTTP, with no queue involved. That
is exactly the ``wait=`` code path a real deployment's worker would resolve into on its
own — this only replaces "wait for a worker" with "it was already done".
"""

import json
import tempfile
from pathlib import Path

import pytest
from cernal import Client

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
DESIGN_REQUEST = json.loads((FIXTURES / "design_request.json").read_text())
EXPECTED_COLUMNS = json.loads((FIXTURES / "expected_columns.json").read_text())


@pytest.fixture
def api_key(transactional_db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")

    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.accounts.services import issue_api_key
    from apps.analyses.models import AnalysisRun, InputMode, RunStatus
    from apps.projects.models import Project
    from apps.results.services import import_job_result
    from engine.client import MockEngine
    from engine.contract import INPUT_DIRECT, SCHEMA_VERSION, JobRequest

    user = get_user_model().objects.create_user(
        username="conformance-python", password="x", is_active=True
    )
    _key, secret = issue_api_key(owner=user, label="conformance")
    project, _created = Project.objects.get_or_create(
        owner=user, name="API · conformance", defaults={"organism": "ecoli"}
    )

    run = AnalysisRun.objects.create(
        project=project,
        input_mode=InputMode.DIRECT,
        trigger_sequence=DESIGN_REQUEST["trigger_sequence"],
        created_by=user,
        idempotency_key=DESIGN_REQUEST["idempotency_key"],
        params_snapshot={},
        gate_families=["toehold"],
        scoring_profile="default",
        seed=DESIGN_REQUEST["seed"],
        status=RunStatus.QUEUED,
        submitted_at=timezone.now(),
    )

    with tempfile.TemporaryDirectory() as output_dir:
        request = JobRequest(
            schema_version=SCHEMA_VERSION,
            run_id=str(run.id),
            idempotency_key=run.idempotency_key,
            input_mode=INPUT_DIRECT,
            trigger_sequence=run.trigger_sequence,
            input_path="",
            input_checksum="",
            organism="ecoli",
            params={},
            gate_families=["toehold"],
            scoring_profile="default",
            seed=run.seed,
            output_dir=output_dir,
        )
        result = MockEngine().run(request, lambda pct, stage: True)
        import_job_result(run, result, output_dir)

    run.status = RunStatus.COMPLETED
    run.progress_pct = 100
    run.stage = "Completed"
    run.engine_version = result.engine_version
    run.save()

    return secret


def test_conformance(live_server, api_key):
    client = Client(api_key=api_key, base_url=live_server.url)

    job = client.design(**DESIGN_REQUEST, wait=5)

    assert job.status == "COMPLETED"
    candidates = job.to_dicts()
    assert candidates, "the fixture request must produce at least one candidate"
    assert len(candidates) <= DESIGN_REQUEST["top_n"]

    for candidate in candidates:
        assert sorted(candidate.keys()) == EXPECTED_COLUMNS["candidate_columns"]


def test_capabilities_needs_no_key(live_server):
    client = Client(api_key="cern_live_unused", base_url=live_server.url)
    body = client.capabilities()
    assert "toehold" in [f["name"] for f in body["gate_families"]]


def test_a_bad_key_raises_auth_error(live_server):
    from cernal import AuthError

    client = Client(api_key="cern_live_definitely-not-real", base_url=live_server.url)
    with pytest.raises(AuthError):
        client.design(**DESIGN_REQUEST)


def test_an_unknown_constraint_raises_validation_error_with_did_you_mean(live_server, api_key):
    from cernal import ValidationError

    client = Client(api_key=api_key, base_url=live_server.url)
    with pytest.raises(ValidationError) as excinfo:
        client.design(
            trigger_sequence=DESIGN_REQUEST["trigger_sequence"],
            organism="ecoli",
            constraints={"max_trigger": 2},
        )
    assert excinfo.value.did_you_mean == "max_triggers"
