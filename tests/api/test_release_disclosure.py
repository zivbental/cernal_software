"""A held design must not escape via another authenticated presentation/export."""

import copy
import hashlib
import json

import pytest
from django.core.files.base import ContentFile
from django.test import Client

from apps.results.models import Artifact, Candidate

SEQUENCE = "GGGAAACCC"


def release_design(decision="PASS", allowed=True):
    digest = hashlib.sha256(SEQUENCE.encode()).hexdigest()
    audit = {"decision": decision, "release_allowed": allowed, "sequence_sha256": digest}
    return {
        "switch_sequence": SEQUENCE,
        "structure": "(((...)))",
        "structure_kind": "intended_target",
        "construct_sha256": digest,
        "sequence_release": {"switch": copy.deepcopy(audit), "plasmid": copy.deepcopy(audit)},
        "architecture": {"stem": SEQUENCE},
        "component_switches": [{"switch_sequence": SEQUENCE}],
        "payload_source": {"sequence": SEQUENCE},
        "unknown_future_field": {"bases": SEQUENCE},
        "family_version": "test-version",
    }


@pytest.fixture
def held_candidate(run):
    return Candidate.objects.create(
        run=run,
        engine_ref="held",
        gate_family="toehold",
        logic_type="YES",
        rank=1,
        design=release_design("HOLD_SYSTEM", False),
        triggers={
            "features": [
                {"gene_id": "test", "sequence": SEQUENCE, "seed_trials": [{"sequence": SEQUENCE}]}
            ]
        },
    )


@pytest.mark.parametrize(
    "state",
    [
        "HOLD_SYSTEM",
        "BLOCK",
        "REVIEW",
        "ERROR",
        "missing",
        "truthy",
        "contradictory",
        "wrong_switch",
        "wrong_plasmid",
    ],
)
def test_held_detail_and_design_results_have_no_sequence(auth_client, held_candidate, state):
    candidate = held_candidate
    if state == "missing":
        candidate.design.pop("sequence_release")
    elif state in {"wrong_switch", "wrong_plasmid"}:
        candidate.design = release_design()
        kind = state.removeprefix("wrong_")
        candidate.design["sequence_release"][kind]["sequence_sha256"] = "0" * 64
    else:
        candidate.design = release_design(
            "PASS" if state == "truthy" else "HOLD_SYSTEM" if state == "contradictory" else state,
            "true" if state == "truthy" else state == "contradictory",
        )
    candidate.save()
    before = copy.deepcopy(candidate.design)
    for url in (f"/api/candidates/{candidate.id}", f"/api/design/{candidate.run_id}/results"):
        response = auth_client.get(url)
        assert response.status_code == 200
        assert SEQUENCE not in response.content.decode()
        body = response.json()
        detail = body["candidates"][0] if "candidates" in body else body
        assert detail["design"]["family_version"] == "test-version"
        assert detail["design"]["sequence_release"]["release_allowed"] is False
        assert detail["triggers"]["features"][0]["gene_id"] == "test"
    response = auth_client.get(f"/api/candidates/{candidate.id}/structure")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["sequence"] == ""
    assert response.json()["bases"] == []
    candidate.refresh_from_db()
    assert candidate.design == before


@pytest.mark.parametrize("decision", ["PASS", "REVIEW"])
def test_explicit_release_preserves_detail_and_geometry(auth_client, held_candidate, decision):
    held_candidate.design = release_design(decision)
    held_candidate.save()
    detail = auth_client.get(f"/api/candidates/{held_candidate.id}").json()
    assert detail["design"]["switch_sequence"] == SEQUENCE
    assert detail["design"]["sequence_release"]["release_allowed"] is True
    structure = auth_client.get(f"/api/candidates/{held_candidate.id}/structure").json()
    assert structure["status"] == "available"
    assert structure["sequence"] == SEQUENCE


@pytest.mark.parametrize(
    "kind",
    [
        "sequence_fasta",
        "genbank",
        "sbol",
        "structure_plot",
        "run_manifest",
        "stage_snapshot",
        "report",
        "future_format",
    ],
)
def test_old_or_unscreened_artifact_cannot_bypass_hold(
    auth_client, other_client, client, held_candidate, media_root, kind
):
    artifact = Artifact.objects.create(
        run=held_candidate.run,
        candidate=held_candidate,
        kind=kind,
        file=ContentFile(SEQUENCE.encode(), name="legacy.txt"),
        media_type="text/plain",
        checksum_sha256=hashlib.sha256(SEQUENCE.encode()).hexdigest(),
    )
    url = f"/api/artifacts/{artifact.id}/download"
    assert auth_client.get(url).status_code == 409
    assert other_client.get(url).status_code == 404
    assert Client().get(url).status_code == 401
    for suffix in ("", f"?ids={artifact.id}", f"?category={artifact.category}"):
        response = auth_client.get(f"/api/runs/{artifact.run_id}/artifacts/download{suffix}")
        assert response.status_code == 409
        assert str(artifact.id) in response.json()["error"]["detail"]["withheld_artifact_ids"]
    items = auth_client.get(f"/api/runs/{artifact.run_id}/artifacts").json()
    assert next(a for a in items if a["id"] == str(artifact.id))["download_available"] is False


def test_sequence_free_evidence_stays_available(auth_client, held_candidate, media_root):
    artifact = Artifact.objects.create(
        run=held_candidate.run,
        kind="report",
        sequence_free=True,
        file=ContentFile(b"Computational report; sequence withheld", name="report.html"),
        media_type="text/html",
        checksum_sha256="0" * 64,
    )
    assert auth_client.get(f"/api/artifacts/{artifact.id}/download").status_code == 200
    assert (
        auth_client.get(
            f"/api/runs/{artifact.run_id}/artifacts/download?ids={artifact.id}"
        ).status_code
        == 200
    )


def test_release_does_not_bypass_ownership(client, other_client, held_candidate):
    held_candidate.design = release_design()
    held_candidate.save()
    for suffix in ("", "/structure"):
        url = f"/api/candidates/{held_candidate.id}{suffix}"
        assert client.get(url).status_code == 401
        assert other_client.get(url).status_code == 404


def test_nested_fragments_and_malformed_optional_data_fail_closed(auth_client, held_candidate):
    held_candidate.design.update(
        coding_regions=[{"start": 0, "end": 9, "protein": SEQUENCE}],
        logic_graph={"genes": [{"name": "A", "sequence": SEQUENCE}], "output": "GFP"},
        folding_model={"configuration": {"temperature_celsius": 37, "unknown": SEQUENCE}},
        plasmid_segments=None,
    )
    held_candidate.triggers = {"features": None}
    held_candidate.save()
    response = auth_client.get(f"/api/candidates/{held_candidate.id}")
    assert response.status_code == 200
    assert SEQUENCE not in response.content.decode()
    assert response.json()["design"]["coding_regions"] == [{"start": 0, "end": 9}]
    assert response.json()["design"]["logic_graph"]["genes"] == [{"name": "A"}]


@pytest.mark.parametrize("kind", ["sequence_fasta", "genbank", "sbol"])
def test_approved_sequence_artifact_downloads_unchanged(
    auth_client, held_candidate, media_root, kind
):
    held_candidate.design = release_design()
    held_candidate.save()
    artifact = Artifact.objects.create(
        run=held_candidate.run,
        candidate=held_candidate,
        kind=kind,
        file=ContentFile(SEQUENCE.encode(), name="approved.txt"),
        media_type="text/plain",
        checksum_sha256=hashlib.sha256(SEQUENCE.encode()).hexdigest(),
    )
    response = auth_client.get(f"/api/artifacts/{artifact.id}/download")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == SEQUENCE.encode()
    response = auth_client.get(f"/api/runs/{artifact.run_id}/artifacts/download?ids={artifact.id}")
    assert response.status_code == 200


def test_partial_approval_still_withholds(auth_client, held_candidate):
    held_candidate.design = release_design()
    held_candidate.design["sequence_release"]["plasmid"]["release_allowed"] = False
    held_candidate.save()
    assert SEQUENCE not in auth_client.get(f"/api/candidates/{held_candidate.id}").content.decode()


@pytest.mark.parametrize("audit_kind", ["switch", "plasmid"])
@pytest.mark.parametrize("decision", [[], {}])
@pytest.mark.parametrize("endpoint", ["detail", "results", "structure", "download", "zip"])
def test_malformed_decision_is_a_graceful_hold(
    auth_client, held_candidate, media_root, audit_kind, decision, endpoint
):
    held_candidate.design = release_design()
    held_candidate.design["sequence_release"][audit_kind]["decision"] = decision
    held_candidate.save()
    artifact = Artifact.objects.create(
        run=held_candidate.run,
        candidate=held_candidate,
        kind="sequence_fasta",
        file=ContentFile(SEQUENCE.encode(), name="held.fasta"),
        media_type="text/plain",
        checksum_sha256=hashlib.sha256(SEQUENCE.encode()).hexdigest(),
    )
    urls = {
        "detail": f"/api/candidates/{held_candidate.id}",
        "results": f"/api/design/{held_candidate.run_id}/results",
        "structure": f"/api/candidates/{held_candidate.id}/structure",
        "download": f"/api/artifacts/{artifact.id}/download",
        "zip": f"/api/runs/{held_candidate.run_id}/artifacts/download?ids={artifact.id}",
    }
    response = auth_client.get(urls[endpoint])
    assert response.status_code == (409 if endpoint in {"download", "zip"} else 200)
    assert SEQUENCE not in response.content.decode()


def test_real_hold_result_retains_audits_without_exporting_sequences(run, auth_client, media_root):
    from apps.analyses.services import execute_run

    execute_run(str(run.id))
    candidate = run.candidates.filter(is_rejected=False).first()
    assert candidate is not None
    sequence = candidate.design["switch_sequence"]
    body = auth_client.get(f"/api/candidates/{candidate.id}").json()
    assert body["design"]["sequence_release"]["switch"]["decision"] == "HOLD_SYSTEM"
    assert sequence not in json.dumps(body)
    assert not run.artifacts.filter(kind__in=["sequence_fasta", "genbank", "sbol"]).exists()
    for artifact in run.artifacts.all():
        response = auth_client.get(f"/api/artifacts/{artifact.id}/download")
        if artifact.kind == "run_manifest":
            assert response.status_code == 409
        else:
            assert response.status_code == 200
            assert sequence.encode() not in b"".join(response.streaming_content)
