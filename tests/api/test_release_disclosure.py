"""A held design must not escape via another authenticated presentation/export."""

import copy
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from django.core.files.base import ContentFile
from django.test import Client

from apps.results.models import Artifact, Candidate
from engine.safety import (
    AdapterStatus,
    DeclaredSelectableMarker,
    Finding,
    FindingKind,
    LocalScreeningManifest,
    ReviewTokenSigner,
    SafetyGate,
    ScreeningEvidence,
    SequenceSubmission,
)

SEQUENCE = "GGGAAACCC"


def release_design(decision="PASS", allowed=True, *, now=None):
    now = now or datetime.now(UTC)
    manifest = LocalScreeningManifest(
        "mock-local-screen",
        "test",
        "mock-database",
        "a" * 64,
        now - timedelta(hours=1),
        now + timedelta(hours=1),
    )
    marker = DeclaredSelectableMarker(
        "mock-marker",
        "selectable_marker",
        "test-host",
        "test-plasmid",
        "mock fixture only",
        "test-approval",
    )
    findings = (Finding(FindingKind.AMR, "mock-marker", "confirmed", "mock"),)
    evidence = ScreeningEvidence(
        manifest,
        AdapterStatus.COMPLETE,
        findings if decision == "REVIEW" else (),
    )
    audits = {}
    for kind, sequence in (("switch", SEQUENCE), ("plasmid", SEQUENCE + "AAA")):
        submission = SequenceSubmission(
            kind,
            sequence,
            "plasmid",
            "test-host",
            (marker,) if decision == "REVIEW" else (),
        )
        gate = SafetyGate()
        result = gate.evaluate(submission, evidence, now=now)
        if decision == "REVIEW" and allowed is True:
            signer = ReviewTokenSigner(b"test-only-review-secret")
            token = signer.issue(
                result, approver="test-reviewer", expires_at=now + timedelta(minutes=30)
            )
            result = gate.evaluate(submission, evidence, now=now, signer=signer, review_token=token)
        audit = result.release_record()
        # Invalid-state tests deliberately corrupt genuine current screening records.
        audit.update(decision=decision, release_allowed=allowed)
        audits[kind] = audit
    return {
        "switch_sequence": SEQUENCE,
        "structure": "(((...)))",
        "structure_kind": "intended_target",
        "construct_sha256": hashlib.sha256((SEQUENCE + "AAA").encode()).hexdigest(),
        "sequence_release": audits,
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
        checksum_sha256=hashlib.sha256(b"Computational report; sequence withheld").hexdigest(),
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


@pytest.mark.parametrize(
    "kind", ["sequence_fasta", "genbank", "sbol", "structure_plot", "run_manifest"]
)
@pytest.mark.parametrize("decision", ["PASS", "REVIEW"])
def test_approved_sequence_artifact_downloads_unchanged(
    auth_client, held_candidate, media_root, kind, decision
):
    held_candidate.design = release_design(decision)
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
@pytest.mark.parametrize("decision", [[], {}, [SEQUENCE], {"unexpected": SEQUENCE}])
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


def test_real_hold_result_retains_audits_and_downloadable_sequence_exports(
    run, auth_client, media_root
):
    from apps.analyses.services import execute_run

    execute_run(str(run.id))
    candidate = run.candidates.filter(is_rejected=False).first()
    assert candidate is not None
    sequence = candidate.design["switch_sequence"]
    body = auth_client.get(f"/api/candidates/{candidate.id}").json()
    assert body["design"]["sequence_release"]["switch"]["decision"] == "HOLD_SYSTEM"
    assert sequence not in json.dumps(body)
    assert {
        "sequence_fasta",
        "plasmid_fasta",
        "genbank",
        "sbol",
    } <= set(run.artifacts.values_list("kind", flat=True))
    for artifact in run.artifacts.all():
        response = auth_client.get(f"/api/artifacts/{artifact.id}/download")
        if artifact.kind == "run_manifest":
            assert response.status_code == 409
        else:
            assert response.status_code == 200
    switch_fasta = run.artifacts.filter(kind="sequence_fasta").first()
    response = auth_client.get(f"/api/artifacts/{switch_fasta.id}/download")
    assert sequence.encode() in b"".join(response.streaming_content)


@pytest.mark.parametrize("audit_kind", ["switch", "plasmid"])
@pytest.mark.parametrize(
    "invalidity",
    [
        "expired_manifest",
        "expired_review",
        "legacy",
        "missing_window",
        "naive_expiry",
        "malformed_expiry",
        "future_validation",
        "missing_result_digest",
        "malformed_result_digest",
        "wrong_sequence",
        "swapped_records",
        "missing_review_expiry",
    ],
)
def test_invalid_evidence_withholds_every_delivery_route(
    auth_client, held_candidate, media_root, audit_kind, invalidity
):
    now = datetime.now(UTC)
    decision = "REVIEW" if "review" in invalidity else "PASS"
    issued_at = now - timedelta(hours=2) if invalidity == "expired_manifest" else now
    if invalidity == "expired_review":
        issued_at = now - timedelta(minutes=45)
    design = release_design(decision, now=now)
    if invalidity in {"expired_manifest", "expired_review"}:
        design["sequence_release"][audit_kind] = release_design(decision, now=issued_at)[
            "sequence_release"
        ][audit_kind]
    record = design["sequence_release"][audit_kind]
    if invalidity == "legacy":
        record["schema"] = "sequence-release-v1"
    elif invalidity == "missing_window":
        record["adapter"].pop("expires_at")
    elif invalidity == "naive_expiry":
        record["adapter"]["expires_at"] = (
            (now + timedelta(hours=1)).replace(tzinfo=None).isoformat()
        )
    elif invalidity == "malformed_expiry":
        record["adapter"]["expires_at"] = {"invalid": True}
    elif invalidity == "future_validation":
        record["adapter"]["validated_at"] = (now + timedelta(minutes=1)).isoformat()
    elif invalidity == "missing_result_digest":
        record.pop("result_sha256")
    elif invalidity == "malformed_result_digest":
        record["result_sha256"] = "not-a-digest"
    elif invalidity == "wrong_sequence":
        record["sequence_sha256"] = "0" * 64
    elif invalidity == "swapped_records":
        design["sequence_release"][audit_kind] = copy.deepcopy(
            design["sequence_release"]["plasmid" if audit_kind == "switch" else "switch"]
        )
    elif invalidity == "missing_review_expiry":
        record.pop("approval_expires_at")
    held_candidate.design = design
    held_candidate.save()
    artifacts = [
        Artifact.objects.create(
            run=held_candidate.run,
            candidate=None if kind == "run_manifest" else held_candidate,
            kind=kind,
            file=ContentFile(SEQUENCE.encode(), name=f"{kind}.txt"),
            checksum_sha256=hashlib.sha256(SEQUENCE.encode()).hexdigest(),
        )
        for kind in ("sequence_fasta", "genbank", "sbol", "structure_plot", "run_manifest")
    ]
    for url in (
        f"/api/candidates/{held_candidate.id}",
        f"/api/candidates/{held_candidate.id}/structure",
        f"/api/design/{held_candidate.run_id}/results",
        f"/api/runs/{held_candidate.run_id}/candidates",
        f"/api/runs/{held_candidate.run_id}/export.csv",
    ):
        response = auth_client.get(url)
        assert response.status_code == 200
        assert SEQUENCE not in response.content.decode()
    listed = auth_client.get(f"/api/runs/{held_candidate.run_id}/artifacts").json()
    assert all(not item["download_available"] for item in listed)
    for artifact in artifacts:
        assert auth_client.get(f"/api/artifacts/{artifact.id}/download").status_code == 409
        for suffix in (f"?ids={artifact.id}", f"?category={artifact.category}", ""):
            response = auth_client.get(f"/api/runs/{artifact.run_id}/artifacts/download{suffix}")
            assert response.status_code == 409
            assert SEQUENCE not in response.content.decode()


@pytest.mark.parametrize("endpoint", ["download", "zip"])
def test_changed_artifact_bytes_are_withheld(auth_client, held_candidate, media_root, endpoint):
    held_candidate.design = release_design()
    held_candidate.save()
    artifact = Artifact.objects.create(
        run=held_candidate.run,
        candidate=held_candidate,
        kind="sequence_fasta",
        file=ContentFile(b"replaced after screening", name="changed.txt"),
        checksum_sha256=hashlib.sha256(SEQUENCE.encode()).hexdigest(),
    )
    url = (
        f"/api/artifacts/{artifact.id}/download"
        if endpoint == "download"
        else f"/api/runs/{artifact.run_id}/artifacts/download?ids={artifact.id}"
    )
    response = auth_client.get(url)
    assert response.status_code == 409
    assert b"replaced after screening" not in response.content


@pytest.mark.parametrize("endpoint", ["download", "zip"])
def test_release_expiring_during_snapshot_is_withheld(
    auth_client, held_candidate, media_root, monkeypatch, endpoint
):
    import engine.safety as safety
    from api.routers import results

    now = datetime.now(UTC)
    held_candidate.design = release_design(now=now)
    held_candidate.save()
    artifact = Artifact.objects.create(
        run=held_candidate.run,
        candidate=held_candidate,
        kind="sequence_fasta",
        file=ContentFile(SEQUENCE.encode(), name="expiry.txt"),
        checksum_sha256=hashlib.sha256(SEQUENCE.encode()).hexdigest(),
    )
    original_snapshot = results._verified_artifact_snapshot

    class LaterDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp((now + timedelta(hours=2)).timestamp(), tz)

    def snapshot_then_expire(item):
        snapshot = original_snapshot(item)
        monkeypatch.setattr(safety, "datetime", LaterDatetime)
        return snapshot

    monkeypatch.setattr(results, "_verified_artifact_snapshot", snapshot_then_expire)
    url = (
        f"/api/artifacts/{artifact.id}/download"
        if endpoint == "download"
        else f"/api/runs/{artifact.run_id}/artifacts/download?ids={artifact.id}"
    )
    assert auth_client.get(url).status_code == 409


@pytest.mark.parametrize("endpoint", ["download", "zip"])
def test_storage_replacement_after_check_cannot_change_verified_delivery(
    auth_client, held_candidate, media_root, monkeypatch, endpoint
):
    from api.routers import results

    held_candidate.design = release_design()
    held_candidate.save()
    artifact = Artifact.objects.create(
        run=held_candidate.run,
        candidate=held_candidate,
        kind="sequence_fasta",
        file=ContentFile(SEQUENCE.encode(), name="snapshot.txt"),
        checksum_sha256=hashlib.sha256(SEQUENCE.encode()).hexdigest(),
    )
    original_checksum = results.sha256_upload

    def verify_then_replace(snapshot):
        digest = original_checksum(snapshot)
        with open(artifact.file.path, "wb") as stored:
            stored.write(b"replacement after checksum")
        return digest

    monkeypatch.setattr(results, "sha256_upload", verify_then_replace)
    url = (
        f"/api/artifacts/{artifact.id}/download"
        if endpoint == "download"
        else f"/api/runs/{artifact.run_id}/artifacts/download?ids={artifact.id}"
    )
    response = auth_client.get(url)
    assert response.status_code == 200
    delivered = b"".join(response.streaming_content)
    if endpoint == "zip":
        with zipfile.ZipFile(io.BytesIO(delivered)) as archive:
            assert len(archive.namelist()) == 1
            delivered = archive.read(archive.namelist()[0])
    assert delivered == SEQUENCE.encode()
