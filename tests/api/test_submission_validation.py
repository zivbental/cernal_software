"""Synchronous validation parity for runs, design and dry-run requests."""

import pytest

from apps.analyses.models import AnalysisRun, RunStatus
from apps.datasets.models import Dataset
from apps.results.models import Candidate, CandidateMetric

SEQUENCE = "ACGU" * 12


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize(
    "overrides",
    [
        {"trigger_sequence": "not RNA"},
        {"trigger_sequence": "ACGN" * 10},
        {"trigger_sequence": ">first\nACGU\n>second\nACGU"},
        {"organism": "unknown"},
        {"gene_id": "missing-gene", "trigger_sequence": ""},
        {"budget": {"max_designs": 0}},
        {"budget": {"max_runtime_seconds": 0}},
        {"constraints": {"max_triggers": 0}},
        {"constraints": {"max_p_adj": 2}},
        {"scoring": {"weights": {"predicted_leakage": "bad"}}},
        {"scoring": {"weights": []}},
        {"scoring": {"hard_filters": ["bad"]}},
        {"gate_families": []},
        {"payload": {"outputs": ["apoptosis"]}},
    ],
)
def test_design_invalid_requests_fail_before_queue_or_dry_estimate(auth_client, dry_run, overrides):
    body = {"trigger_sequence": SEQUENCE, "organism": "ecoli", **overrides}
    response = auth_client.post(
        f"/api/design?dry_run={'true' if dry_run else 'false'}",
        data=body,
        content_type="application/json",
    )
    assert response.status_code == 422, response.content
    assert not AnalysisRun.objects.exists()
    assert not Dataset.objects.exists()


@pytest.mark.parametrize(
    "params",
    [
        {"constraints": []},
        {"scoring": []},
        {"backbone": []},
        {"scoring": {"weights": {"gc_content": "not numeric"}}},
        {"constraints": {"trigger_lengths": "30"}},
        {"constraints": {"max_p_adj": 2}},
        {"budget": {"max_designs": 0}},
        {"host": "human"},
        {"organism": "human"},
        {"payload": {"outputs": ["apoptosis"]}},
    ],
)
def test_runs_invalid_nested_configuration_is_422(auth_client, params):
    response = auth_client.post(
        "/api/runs",
        data={
            "input_mode": "direct",
            "trigger_sequence": SEQUENCE,
            "organism": "ecoli",
            "params": params,
        },
        content_type="application/json",
    )
    assert response.status_code == 422, response.content
    assert not AnalysisRun.objects.exists()


def test_fasta_normalization_and_effective_defaults_match_dry_and_real_submission(auth_client):
    body = {
        "trigger_sequence": ">one record\n" + "acgt " * 12,
        "organism": "ecoli",
        "gate_families": ["toehold"],
    }
    dry = auth_client.post("/api/design?dry_run=true", data=body, content_type="application/json")
    assert dry.status_code == 200, dry.content
    assert not AnalysisRun.objects.exists()
    submitted = auth_client.post("/api/design", data=body, content_type="application/json")
    assert submitted.status_code == 202, submitted.content
    assert dry.json()["resolved"] == submitted.json()["resolved"]
    run = AnalysisRun.objects.get()
    assert run.trigger_sequence == "ACGU" * 12
    assert run.params_snapshot["constraints"] == dry.json()["resolved"]["constraints"]


def test_invalid_inline_dge_is_not_a_successful_dry_run(auth_client):
    response = auth_client.post(
        "/api/design?dry_run=true",
        data={"dge_csv": "gene_id,log2fc\ngene,not-number\n"},
        content_type="application/json",
    )
    assert response.status_code == 422
    assert not Dataset.objects.exists()


def test_inline_and_async_results_omit_metrics_when_requested(auth_client):
    body = {
        "trigger_sequence": SEQUENCE,
        "gate_families": ["toehold"],
        "idempotency_key": "result-options",
        "include_metrics": False,
    }
    submission = auth_client.post("/api/design", data=body, content_type="application/json")
    assert submission.status_code == 202, submission.content
    run = AnalysisRun.objects.get()
    candidate = Candidate.objects.create(
        run=run,
        engine_ref="one",
        rank=1,
        overall_score=0.5,
        gate_family="toehold",
        logic_type="single",
    )
    CandidateMetric.objects.create(
        candidate=candidate,
        name="zero",
        raw_value=0,
        normalized_value=0,
        weight=1,
        direction="HIGHER_BETTER",
    )
    run.status = RunStatus.COMPLETED
    run.save(update_fields=["status"])
    inline = auth_client.post("/api/design?wait=1", data=body, content_type="application/json")
    asynchronous = auth_client.get(f"/api/design/{run.id}/results?include_metrics=false")
    assert inline.status_code == asynchronous.status_code == 200
    assert "metrics" not in inline.json()["candidates"][0]
    assert "metrics" not in asynchronous.json()["candidates"][0]
    default = auth_client.get(f"/api/design/{run.id}/results")
    assert default.json()["candidates"][0]["metrics"][0]["raw_value"] == 0


def test_version_exposes_authoritative_host_family_output_limits(client):
    response = client.get("/api/version")
    assert response.status_code == 200
    document = response.json()
    assert document["supported_hosts"] == ["ecoli", "yeast", "human", "c_acnes"]
    assert set(document["supported_outputs"]) == {"gfp", "other"}
    assert "ecoli" in document["family_hosts"]["toehold"]
    assert document["limits"]["max_de_rows"] == 200000
    assert document["constraints"]["trigger_lengths"]


def test_canonical_wizard_organism_is_accepted_and_real_conflict_rejected(auth_client):
    body = {
        "input_mode": "direct",
        "trigger_sequence": SEQUENCE,
        "organism": "ecoli",
        "params": {"organism": "ecoli", "constraints": {"max_circuit_gates": 1}},
    }
    response = auth_client.post("/api/runs", data=body, content_type="application/json")
    assert response.status_code == 202, response.content
    body["params"]["organism"] = "human"
    response = auth_client.post("/api/runs", data=body, content_type="application/json")
    assert response.status_code == 422
    assert "agree" in response.json()["error"]["message"]


def test_inline_retry_reuses_run_without_leaving_an_extra_dataset(auth_client, media_root):
    body = {"dge_csv": "gene_id,log2fc,padj\nb0005,2,0.01\n", "idempotency_key": "inline-retry"}
    first = auth_client.post("/api/design", data=body, content_type="application/json")
    second = auth_client.post("/api/design", data=body, content_type="application/json")
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert Dataset.objects.count() == AnalysisRun.objects.count() == 1
    assert AnalysisRun.objects.get().dataset.file.storage.exists(
        AnalysisRun.objects.get().dataset.file.name
    )


def test_inline_conflict_removes_unreferenced_new_input(auth_client, media_root):
    body = {"dge_csv": "gene_id,log2fc,padj\nb0005,2,0.01\n", "idempotency_key": "inline-conflict"}
    first = auth_client.post("/api/design", data=body, content_type="application/json")
    assert first.status_code == 202
    body["dge_csv"] = "gene_id,log2fc,padj\nb0005,3,0.01\n"
    rejected = auth_client.post("/api/design", data=body, content_type="application/json")
    assert rejected.status_code == 409
    assert Dataset.objects.count() == AnalysisRun.objects.count() == 1


def test_inline_quota_rejection_removes_unreferenced_input(auth_client, media_root, settings):
    settings.MAX_ACTIVE_RUNS_PER_ACCOUNT = 1
    first = auth_client.post(
        "/api/design", data={"trigger_sequence": SEQUENCE}, content_type="application/json"
    )
    assert first.status_code == 202
    rejected = auth_client.post(
        "/api/design",
        data={"dge_csv": "gene_id,log2fc\nb0005,2\n"},
        content_type="application/json",
    )
    assert rejected.status_code == 429
    assert not Dataset.objects.exists()
    assert AnalysisRun.objects.count() == 1


def test_inline_invalid_real_submission_never_stores_input(auth_client, media_root):
    rejected = auth_client.post(
        "/api/design",
        data={"dge_csv": "gene_id,log2fc\nb0005,invalid\n"},
        content_type="application/json",
    )
    assert rejected.status_code == 422
    assert not Dataset.objects.exists()
    assert not AnalysisRun.objects.exists()
