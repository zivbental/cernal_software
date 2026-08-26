"""The Step 3 milestone (docs/architecture.md §13).

One researcher completes the whole workflow through the HTTP API alone: log in, create a
project, upload a dataset, submit a run, watch it progress, read back ranked candidates
with their metrics, download an artifact, annotate, and export.

The worker is executed inline rather than by a real qcluster, so the test is
deterministic. `./do worker` running the same task is verified separately.
"""

import csv
import io
import json

import pytest

from apps.analyses.models import RunStatus
from apps.analyses.tasks import run_analysis

DATASET = (
    "gene_id,base_expression,target_expression,log2fc,padj\n"
    "lacZ,0.82,6.41,2.97,0.0007\n"
    "rpoS,2.11,0.44,-2.26,0.0041\n"
    "katG,1.24,5.93,2.26,0.0019\n"
    "soxS,0.31,4.77,3.94,0.0002\n"
)


@pytest.fixture
def researcher(db):
    from django.contrib.auth import get_user_model

    get_user_model().objects.create_user(username="rosalind", password="franklin-1952")
    return "rosalind", "franklin-1952"


def test_a_researcher_completes_the_whole_workflow(
    client, researcher, media_root, django_capture_on_commit_callbacks, csv_upload
):
    username, password = researcher

    # 1. Log in.
    login = client.post(
        "/api/auth/login",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
    )
    assert login.status_code == 200

    # 2. Discover what the engine supports.
    capabilities = client.get("/api/version").json()
    available = [f["name"] for f in capabilities["gate_families"] if f["available"]]
    assert "toehold" in available

    # 3. Create a project.
    project = client.post(
        "/api/projects",
        data=json.dumps(
            {
                "name": "Lactose to oxidative stress",
                "organism": "E. coli",
                "biological_objective": "Express GFP when both signals are present.",
            }
        ),
        content_type="application/json",
    ).json()

    # 4. Upload a dataset — validated synchronously.
    dataset = client.post(
        f"/api/projects/{project['id']}/datasets",
        data={"file": csv_upload(DATASET, "expression.csv")},
    ).json()
    assert dataset["validation_status"] == "VALID"
    assert dataset["validation_report"]["rows"] == 4

    # 5. Submit a run. Accepted, not completed.
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        submit = client.post(
            f"/api/projects/{project['id']}/runs",
            data=json.dumps(
                {
                    "dataset_id": dataset["id"],
                    "gate_families": available[:1],
                    "scoring_profile": capabilities["scoring_profiles"][0],
                    "seed": 42,
                    "params": {"max_triggers": 2, "mock": {"candidate_count": 24}},
                    "idempotency_key": "e2e-run-001",
                }
            ),
            content_type="application/json",
        )
    run = submit.json()
    assert submit.status_code == 202
    assert run["status"] == RunStatus.QUEUED
    assert callbacks, "submission must enqueue exactly one worker task"

    # 6. Poll while queued.
    queued = client.get(f"/api/runs/{run['id']}").json()
    assert queued["status"] == RunStatus.QUEUED
    assert queued["counts"]["candidates"] == 0

    # 7. The worker picks it up.
    run_analysis(run["id"])

    # 8. Poll again — done.
    finished = client.get(f"/api/runs/{run['id']}").json()
    assert finished["status"] == RunStatus.COMPLETED
    assert finished["progress_pct"] == 100
    assert finished["counts"]["candidates"] == 24
    assert finished["counts"]["artifacts"] > 0
    assert finished["finished_at"] is not None

    # 9. Read back ranked candidates.
    candidates = client.get(f"/api/runs/{run['id']}/candidates?limit=100").json()
    assert candidates["count"] > 0
    ranks = [c["rank"] for c in candidates["items"]]
    assert ranks == list(range(1, len(ranks) + 1))

    # 10. Inspect the top candidate's full score decomposition.
    top = client.get(f"/api/candidates/{candidates['items'][0]['id']}").json()
    assert top["rank"] == 1
    assert top["design"]["switch_sequence"]
    assert {m["name"] for m in top["metrics"]} >= {"state_separation", "predicted_leakage"}

    # 11. Rejected candidates are available with their reasons.
    everything = client.get(
        f"/api/runs/{run['id']}/candidates?limit=100&include_rejected=true"
    ).json()
    rejected = [c for c in everything["items"] if c["is_rejected"]]
    assert rejected, "24 candidates should trip at least one hard filter"
    assert all(c["rejection_reason"] for c in rejected)

    # 12. Download an artifact.
    artifacts = client.get(f"/api/runs/{run['id']}/artifacts").json()
    fasta = next(a for a in artifacts if a["kind"] == "sequence_fasta")
    download = client.get(fasta["download_url"])
    body = b"".join(download.streaming_content)
    assert download.status_code == 200
    assert body.startswith(b">")

    # 13. Annotate a candidate.
    annotation = client.post(
        f"/api/candidates/{top['id']}/annotations",
        data=json.dumps({"text": "Take this to synthesis.", "decision_tag": "SYNTHESIZE"}),
        content_type="application/json",
    )
    assert annotation.status_code == 201

    # 14. Export.
    export = client.get(f"/api/runs/{run['id']}/export.csv")
    rows = list(csv.DictReader(io.StringIO(export.content.decode())))
    assert len(rows) == 24
    assert rows[0]["state_separation_raw"]

    # 15. Resubmitting with the same idempotency key returns the same run.
    with django_capture_on_commit_callbacks(execute=False):
        again = client.post(
            f"/api/projects/{project['id']}/runs",
            data=json.dumps({"dataset_id": dataset["id"], "idempotency_key": "e2e-run-001"}),
            content_type="application/json",
        ).json()
    assert again["id"] == run["id"]


def test_a_failed_run_is_reported_to_the_researcher(
    client, researcher, media_root, django_capture_on_commit_callbacks, csv_upload
):
    """The failure path is as much a product feature as the success path."""
    username, password = researcher
    client.post(
        "/api/auth/login",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
    )

    project = client.post(
        "/api/projects",
        data=json.dumps({"name": "Failure path", "organism": "E. coli"}),
        content_type="application/json",
    ).json()
    dataset = client.post(
        f"/api/projects/{project['id']}/datasets", data={"file": csv_upload(DATASET)}
    ).json()

    with django_capture_on_commit_callbacks(execute=False):
        run = client.post(
            f"/api/projects/{project['id']}/runs",
            data=json.dumps(
                {
                    "dataset_id": dataset["id"],
                    "params": {"mock": {"fail": True, "fail_message": "Organism unsupported."}},
                }
            ),
            content_type="application/json",
        ).json()

    run_analysis(run["id"])

    status = client.get(f"/api/runs/{run['id']}").json()
    assert status["status"] == RunStatus.FAILED
    assert status["error_summary"] == "Organism unsupported."
    assert status["counts"]["candidates"] == 0
