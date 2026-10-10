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
        {"constraints": {"max_triggers": 2}},
        {"constraints": {"max_circuit_gates": 2}},
        {"constraints": {"max_p_adj": 2}},
        {"scoring": {"weights": {"predicted_leakage": "bad"}}},
        {"scoring": {"weights": []}},
        {"scoring": {"hard_filters": ["bad"]}},
        {"gate_families": []},
        {"payload": {"outputs": ["apoptosis"]}},
        {"payload": {"optimize_codons": "yes"}},
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
        {"constraints": {"max_triggers": 2}},
        {"constraints": {"max_circuit_gates": 2}},
        {"budget": {"max_designs": 0}},
        {"host": "human"},
        {"organism": "human"},
        {"payload": {"outputs": ["apoptosis"]}},
        {"payload": {"optimize_codons": "yes"}},
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
    assert {"gfp", "other", "mcherry", "luciferase", "ampr", "kanr"} <= set(
        document["supported_outputs"]
    )
    assert "ecoli" in document["family_hosts"]["toehold"]
    assert document["limits"]["max_de_rows"] == 200000
    assert document["constraints"]["trigger_lengths"]
    # Host matrices are passed through from the selected engine, including custom
    # engine implementations that predate these additive fields.
    from django.conf import settings

    from engine.client import load_engine

    capabilities = load_engine(settings.CERNAL_ENGINE).capabilities()
    assert document["output_hosts"] == getattr(capabilities, "output_hosts", {})
    assert document["backbone_hosts"] == getattr(capabilities, "backbone_hosts", {})
    assert document["output_hosts"]["ampr"] == ["ecoli"]
    assert document["output_hosts"]["kanr"] == ["ecoli"]
    assert document["backbone_hosts"]["psb1a3"] == ["ecoli"]


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


@pytest.mark.parametrize("endpoint", ["design", "runs"])
@pytest.mark.parametrize("insertion", [True, "1", -1, 10**9])
def test_backbone_insertion_coordinate_is_validated_before_storage(
    auth_client, endpoint, insertion
):
    backbone = {"catalog_key": "psb1a3", "insertion_index": insertion}
    body = {"trigger_sequence": SEQUENCE, "organism": "ecoli"}
    if endpoint == "design":
        body["backbone"] = backbone
    else:
        body.update(input_mode="direct", params={"backbone": backbone})
    response = auth_client.post(f"/api/{endpoint}", data=body, content_type="application/json")
    assert response.status_code == 422, response.content
    assert "insertion_index" in response.json()["error"]["message"]
    assert not AnalysisRun.objects.exists()
    assert not Dataset.objects.exists()


@pytest.mark.parametrize("endpoint", ["design?dry_run=true", "design", "runs"])
def test_explicit_backbone_insertion_coordinate_is_preserved(auth_client, endpoint):
    backbone = {"catalog_key": "psb1a3", "insertion_index": 1}
    body = {"trigger_sequence": SEQUENCE, "organism": "ecoli"}
    if endpoint == "runs":
        body.update(input_mode="direct", params={"backbone": backbone})
    else:
        body["backbone"] = backbone
    response = auth_client.post(f"/api/{endpoint}", data=body, content_type="application/json")
    assert response.status_code in (200, 202), response.content
    if endpoint.endswith("true"):
        assert response.json()["resolved"]["backbone"] == backbone
        assert not AnalysisRun.objects.exists()
    else:
        assert AnalysisRun.objects.get().params_snapshot["backbone"] == backbone


@pytest.mark.parametrize("endpoint", ["design?dry_run=true", "design", "runs"])
@pytest.mark.parametrize("insertion", [0, 1, 15])
def test_custom_backbone_functional_feature_is_protected_before_queue(
    auth_client, endpoint, insertion
):
    import io

    from Bio import SeqIO
    from Bio.Seq import Seq
    from Bio.SeqFeature import SeqFeature, SimpleLocation
    from Bio.SeqRecord import SeqRecord

    record = SeqRecord(Seq("ATGGCTGCTGCTTAA"), id="vector", name="vector")
    record.annotations = {"molecule_type": "DNA", "topology": "circular"}
    record.features = [SeqFeature(SimpleLocation(0, 15), type="CDS")]
    stream = io.StringIO()
    SeqIO.write(record, stream, "genbank")
    backbone = {"custom_genbank": stream.getvalue(), "insertion_index": insertion}
    body = {"trigger_sequence": SEQUENCE, "organism": "ecoli"}
    if endpoint == "runs":
        body.update(input_mode="direct", params={"backbone": backbone})
    else:
        body["backbone"] = backbone
    response = auth_client.post(f"/api/{endpoint}", data=body, content_type="application/json")
    if insertion == 1:
        assert response.status_code == 422, response.content
        assert "disrupts backbone CDS" in response.json()["error"]["message"]
        assert not AnalysisRun.objects.exists()
    else:
        assert response.status_code in (200, 202), response.content
        if endpoint.endswith("true"):
            assert response.json()["resolved"]["backbone"] == backbone
            assert not AnalysisRun.objects.exists()
        else:
            assert AnalysisRun.objects.get().params_snapshot["backbone"] == backbone
    assert not Dataset.objects.exists()


@pytest.mark.parametrize("endpoint", ["design?dry_run=true", "design", "runs"])
@pytest.mark.parametrize("organism", ["ecoli", "yeast", "human", "c_acnes"])
@pytest.mark.parametrize("configuration", ["ampr", "kanr", "psb1a3"])
def test_ecoli_marker_and_vector_scope_matches_public_capabilities(
    auth_client, endpoint, organism, configuration
):
    block = (
        {"backbone": {"catalog_key": configuration}}
        if configuration == "psb1a3"
        else {"payload": {"outputs": [configuration]}}
    )
    body = {"trigger_sequence": SEQUENCE, "organism": organism, "gate_families": ["toehold"]}
    if endpoint == "runs":
        body.update(input_mode="direct", params=block)
    else:
        body.update(block)
    response = auth_client.post(f"/api/{endpoint}", data=body, content_type="application/json")
    if organism == "ecoli":
        assert response.status_code in (200, 202), response.content
        if endpoint.endswith("true"):
            assert not AnalysisRun.objects.exists()
        else:
            stored = AnalysisRun.objects.get().params_snapshot
            if configuration == "psb1a3":
                assert stored["backbone"] == {"catalog_key": configuration, "insertion_index": 0}
            else:
                assert stored["payload"]["outputs"] == [configuration]
    else:
        assert response.status_code == 422, response.content
        assert "E. coli" in response.json()["error"]["message"]
        assert not AnalysisRun.objects.exists()
    assert not Dataset.objects.exists()


@pytest.mark.parametrize("endpoint", ["design?dry_run=true", "design", "runs"])
@pytest.mark.parametrize(
    "folding",
    [
        None,
        [],
        {"temperature": 25},
        {"temperature_celsius": -1},
        {"temperature_celsius": 101},
        {"temperature_celsius": "25"},
        {"temperature_celsius": True},
        {"dangles": 1},
        {"dangles": 3},
        {"dangles": 2.0},
        {"special_hairpins": "false"},
        {"no_lonely_pairs": 1},
        {"no_gu": 0},
        {"no_gu_closure": None},
        {"energy_parameters": "unsupported"},
    ],
)
def test_invalid_folding_configuration_fails_before_queue(auth_client, endpoint, folding):
    body = {"trigger_sequence": SEQUENCE}
    if endpoint == "runs":
        body.update(input_mode="direct", params={"folding": folding})
    else:
        body.update(folding=folding, strict=False)
    response = auth_client.post(f"/api/{endpoint}", data=body, content_type="application/json")
    assert response.status_code == 422, response.content
    assert not AnalysisRun.objects.exists()
    assert not Dataset.objects.exists()


@pytest.mark.parametrize("endpoint", ["design?dry_run=true", "design", "runs"])
@pytest.mark.parametrize(
    "folding",
    [
        {},
        {"temperature_celsius": 25, "energy_parameters": "turner1999"},
        {
            "temperature_celsius": 42.5,
            "dangles": 0,
            "special_hairpins": False,
            "no_lonely_pairs": True,
            "no_gu": True,
            "no_gu_closure": True,
            "energy_parameters": "andronescu2007",
        },
    ],
)
def test_folding_configuration_is_normalized_and_preserved(auth_client, endpoint, folding):
    defaults = {
        "temperature_celsius": 37.0,
        "dangles": 2,
        "special_hairpins": True,
        "no_lonely_pairs": False,
        "no_gu": False,
        "no_gu_closure": False,
        "energy_parameters": "turner2004",
    }
    expected = {**defaults, **folding}
    body = {"trigger_sequence": SEQUENCE}
    if endpoint == "runs":
        body.update(input_mode="direct", params={"folding": folding})
    else:
        body["folding"] = folding
    response = auth_client.post(f"/api/{endpoint}", data=body, content_type="application/json")
    assert response.status_code in (200, 202), response.content
    if endpoint != "runs":
        assert response.json()["resolved"]["folding"] == expected
    if endpoint.endswith("true"):
        assert not AnalysisRun.objects.exists()
    else:
        run = AnalysisRun.objects.get()
        assert run.params_snapshot["folding"] == expected
        result = auth_client.get(f"/api/design/{run.id}/results")
        assert result.status_code == 200, result.content
        assert result.json()["resolved"]["folding"] == expected


def test_folding_defaults_have_the_same_idempotency_identity(auth_client):
    body = {"trigger_sequence": SEQUENCE, "idempotency_key": "folding-defaults"}
    first = auth_client.post("/api/design", data=body, content_type="application/json")
    assert first.status_code == 202, first.content
    body["folding"] = first.json()["resolved"]["folding"]
    body["folding"]["temperature_celsius"] = 37
    repeated = auth_client.post("/api/design", data=body, content_type="application/json")
    assert repeated.status_code == 202, repeated.content
    assert repeated.json()["job_id"] == first.json()["job_id"]
    assert AnalysisRun.objects.count() == 1
    body["folding"]["temperature_celsius"] = 25
    conflicting = auth_client.post("/api/design", data=body, content_type="application/json")
    assert conflicting.status_code == 409, conflicting.content
    assert AnalysisRun.objects.count() == 1


def test_historical_run_does_not_claim_unrecorded_folding_defaults(auth_client, run):
    assert "folding" not in run.params_snapshot
    response = auth_client.get(f"/api/design/{run.id}/results")
    assert response.status_code == 200, response.content
    assert response.json()["resolved"]["folding"] == {}
