"""Fail-closed output sequence safety policy tests using harmless synthetic fixtures."""

from datetime import UTC, datetime, timedelta

from engine.safety import (
    AdapterStatus,
    Decision,
    DeclaredSelectableMarker,
    Finding,
    FindingKind,
    LocalScreeningManifest,
    ReviewTokenSigner,
    SafetyGate,
    ScreeningEvidence,
    SequenceSubmission,
)

NOW = datetime(2026, 9, 22, tzinfo=UTC)
MANIFEST = LocalScreeningManifest(
    adapter_name="manifest-stub",
    adapter_version="0",
    database_id="unprovisioned",
    database_sha256="0" * 64,
    validated_at=NOW,
    expires_at=NOW + timedelta(days=1),
)
MARKER = DeclaredSelectableMarker(
    gene_identity="declared-marker-001",
    role="selectable_marker",
    host_context="laboratory E. coli cloning host",
    plasmid_context="delivery backbone",
    justification="selection during plasmid propagation",
    approval_reference="IBC-TEST-001",
)
SUBMISSION = SequenceSubmission(
    sequence_id="construct-001",
    sequence="ACGT" * 24,
    delivery_method="plasmid",
    host_context="laboratory E. coli cloning host",
    declared_markers=(MARKER,),
)


def evidence(status=AdapterStatus.COMPLETE, findings=()):
    return ScreeningEvidence(manifest=MANIFEST, adapter_status=status, findings=findings)


def test_declared_selectable_marker_requires_review_and_is_audited():
    result = SafetyGate().evaluate(
        SUBMISSION,
        evidence(
            findings=(
                Finding(
                    kind=FindingKind.AMR,
                    identity="declared-marker-001",
                    confidence="confirmed",
                    evidence_reference="local:synthetic-fixture",
                ),
            )
        ),
        now=NOW,
    )

    assert result.decision is Decision.REVIEW
    assert result.declared_marker_findings[0].identity == "declared-marker-001"
    assert result.release_allowed is False


def test_unexpected_resistance_finding_blocks_even_with_declared_marker():
    result = SafetyGate().evaluate(
        SUBMISSION,
        evidence(
            findings=(
                Finding(FindingKind.AMR, "declared-marker-001", "confirmed", "local:fixture"),
                Finding(FindingKind.AMR, "additional-marker-002", "confirmed", "local:fixture"),
            )
        ),
        now=NOW,
    )

    assert result.decision is Decision.BLOCK
    assert [finding.identity for finding in result.unexpected_marker_findings] == [
        "additional-marker-002"
    ]


def test_missing_marker_declaration_fails_closed():
    undeclared = SequenceSubmission(
        sequence_id="construct-002",
        sequence="ACGT" * 24,
        delivery_method="plasmid",
        host_context="laboratory E. coli cloning host",
    )

    result = SafetyGate().evaluate(
        undeclared,
        evidence(
            findings=(Finding(FindingKind.AMR, "marker-unknown", "confirmed", "local:fixture"),)
        ),
        now=NOW,
    )

    assert result.decision is Decision.BLOCK


def test_malformed_sequence_holds_system():
    malformed = SequenceSubmission(
        sequence_id="construct-003",
        sequence="ACGT-NOT-A-SEQUENCE",
        delivery_method="plasmid",
        host_context="laboratory E. coli cloning host",
        declared_markers=(MARKER,),
    )

    assert SafetyGate().evaluate(malformed, evidence(), now=NOW).decision is Decision.HOLD_SYSTEM


def test_unavailable_or_ambiguous_evidence_holds_system():
    unavailable = SafetyGate().evaluate(
        SUBMISSION, evidence(status=AdapterStatus.UNAVAILABLE), now=NOW
    )
    ambiguous = SafetyGate().evaluate(
        SUBMISSION,
        evidence(
            findings=(
                Finding(FindingKind.OTHER_HAZARD, "ambiguous-hit", "ambiguous", "local:fixture"),
            )
        ),
        now=NOW,
    )

    assert unavailable.decision is Decision.HOLD_SYSTEM
    assert ambiguous.decision is Decision.HOLD_SYSTEM


def test_approved_review_token_releases_only_review_decisions():
    gate = SafetyGate()
    review = gate.evaluate(
        SUBMISSION,
        evidence(
            findings=(Finding(FindingKind.AMR, MARKER.gene_identity, "confirmed", "local:fixture"),)
        ),
        now=NOW,
    )
    signer = ReviewTokenSigner(b"test-only-signing-key")
    token = signer.issue(review, approver="reviewer-001", expires_at=NOW + timedelta(hours=1))

    released = gate.evaluate(
        SUBMISSION, evidence(findings=review.findings), now=NOW, review_token=token, signer=signer
    )
    assert released.decision is Decision.REVIEW
    assert released.release_allowed is True


def test_intended_marker_cannot_suppress_an_unrelated_hazard():
    result = SafetyGate().evaluate(
        SUBMISSION,
        evidence(
            findings=(
                Finding(FindingKind.AMR, MARKER.gene_identity, "confirmed", "local:fixture"),
                Finding(
                    FindingKind.OTHER_HAZARD, "redacted-unrelated-hit", "confirmed", "local:fixture"
                ),
            )
        ),
        now=NOW,
    )

    assert result.decision is Decision.BLOCK


def test_review_token_tampering_and_expiry_do_not_release_sequences():
    gate = SafetyGate()
    review = gate.evaluate(
        SUBMISSION,
        evidence(
            findings=(Finding(FindingKind.AMR, MARKER.gene_identity, "confirmed", "local:fixture"),)
        ),
        now=NOW,
    )
    signer = ReviewTokenSigner(b"test-only-signing-key")
    valid = signer.issue(review, approver="reviewer-001", expires_at=NOW + timedelta(minutes=1))

    tampered = valid[:-1] + ("A" if valid[-1] != "A" else "B")
    assert not signer.authorizes(tampered, review, now=NOW)
    assert not signer.authorizes(valid, review, now=NOW + timedelta(minutes=2))


def release_design(result):
    return {
        "switch_sequence": SUBMISSION.sequence,
        "construct_sha256": SUBMISSION.sequence_sha256,
        "sequence_release": {
            "switch": result.release_record(),
            "plasmid": result.release_record(),
        },
    }


def test_stored_pass_requires_current_evidence_for_both_exact_molecules():
    from engine.safety import stored_release_allowed

    result = SafetyGate().evaluate(SUBMISSION, evidence(), now=NOW)
    design = release_design(result)
    assert stored_release_allowed(design, now=NOW)
    assert not stored_release_allowed(design, now=MANIFEST.expires_at)
    assert not stored_release_allowed(design, now=NOW - timedelta(seconds=1))
    assert not stored_release_allowed(design, now=NOW.replace(tzinfo=None))
    design["switch_sequence"] += "A"
    assert not stored_release_allowed(design, now=NOW)


def test_stored_evidence_rejects_legacy_malformed_and_contradictory_records():
    import copy

    from engine.safety import stored_release_allowed

    result = SafetyGate().evaluate(SUBMISSION, evidence(), now=NOW)
    pristine = release_design(result)
    changes = (
        ("schema", None),
        ("release_allowed", 1),
        ("decision", []),
        ("decision", "HOLD_SYSTEM"),
        ("sequence_sha256", "f" * 64),
        ("result_sha256", "z" * 64),
        ("result_sha256", None),
        ("adapter_status", "FAILED"),
        ("screening_status", "unavailable"),
    )
    for kind in ("switch", "plasmid"):
        for key, value in changes:
            design = copy.deepcopy(pristine)
            design["sequence_release"][kind][key] = value
            assert not stored_release_allowed(design, now=NOW), (kind, key, value)
        for key, value in (
            ("validated_at", None),
            ("validated_at", (NOW + timedelta(seconds=1)).isoformat()),
            ("expires_at", "not-a-date"),
            ("expires_at", NOW.isoformat()),
            ("expires_at", NOW.replace(tzinfo=None).isoformat()),
            ("expires_at", []),
            ("name", None),
            ("database_sha256", "z" * 64),
        ):
            design = copy.deepcopy(pristine)
            design["sequence_release"][kind]["adapter"][key] = value
            assert not stored_release_allowed(design, now=NOW), (kind, key, value)
        design = copy.deepcopy(pristine)
        del design["sequence_release"][kind]["adapter"]["expires_at"]
        assert not stored_release_allowed(design, now=NOW)


def test_stored_review_cannot_outlive_approval_or_screening():
    from engine.safety import stored_release_allowed

    gate = SafetyGate()
    screened = evidence(
        findings=(Finding(FindingKind.AMR, MARKER.gene_identity, "confirmed", "local:fixture"),)
    )
    review = gate.evaluate(SUBMISSION, screened, now=NOW)
    signer = ReviewTokenSigner(b"test-only-signing-key")
    expiry = NOW + timedelta(minutes=1)
    token = signer.issue(review, approver="reviewer-001", expires_at=expiry)
    approved = gate.evaluate(SUBMISSION, screened, now=NOW, review_token=token, signer=signer)
    design = release_design(approved)
    assert approved.approval_expires_at == expiry
    assert stored_release_allowed(design, now=NOW)
    assert not stored_release_allowed(design, now=expiry)
    assert not stored_release_allowed(design, now=MANIFEST.expires_at)
    design["sequence_release"]["switch"].pop("approval_expires_at")
    assert not stored_release_allowed(design, now=NOW)
    design["sequence_release"]["switch"]["approval_expires_at"] = "malformed"
    assert not stored_release_allowed(design, now=NOW)


def test_unprovisioned_release_records_remain_deterministic_and_held():
    from engine.safety import fail_closed_release, stored_release_allowed

    first = fail_closed_release("test", SUBMISSION.sequence, host_context="test")
    second = fail_closed_release("test", SUBMISSION.sequence, host_context="test")
    assert first.release_record() == second.release_record()
    assert first.release_record()["screening_status"] == "unavailable"
    assert first.release_record()["adapter_status"] == "UNAVAILABLE"
    assert not stored_release_allowed(release_design(first), now=NOW)


def test_status_records_do_not_turn_incomplete_screening_into_a_pass():
    for status, display in (
        (AdapterStatus.UNAVAILABLE, "unavailable"),
        (AdapterStatus.INCONCLUSIVE, "inconclusive"),
        (AdapterStatus.STALE, "inconclusive"),
        (AdapterStatus.FAILED, "error"),
        (AdapterStatus.TIMEOUT, "error"),
    ):
        result = SafetyGate().evaluate(SUBMISSION, evidence(status=status), now=NOW)
        assert result.decision is Decision.HOLD_SYSTEM
        assert not result.release_allowed
        assert result.release_record()["adapter_status"] == status.value
        assert result.release_record()["screening_status"] == display


def test_common_mechanism_flags_hold_release_without_claiming_confirmed_hazard():
    result = SafetyGate().evaluate(
        SUBMISSION,
        evidence(
            findings=(Finding(FindingKind.SCREENING_FLAG, "flag", "confirmed", "local:fixture"),)
        ),
        now=NOW,
    )
    assert result.decision is Decision.BLOCK
    assert result.screening_status == "flagged"
    assert result.reasons == ("screening flag requires review",)
    assert not result.release_allowed


def test_review_approval_is_bound_to_exact_screening_and_sequence():
    from dataclasses import replace

    gate = SafetyGate()
    screened = evidence(
        findings=(Finding(FindingKind.AMR, MARKER.gene_identity, "confirmed", "local:fixture"),)
    )
    review = gate.evaluate(SUBMISSION, screened, now=NOW)
    signer = ReviewTokenSigner(b"test-only-signing-key")
    token = signer.issue(review, approver="reviewer-001", expires_at=NOW + timedelta(hours=1))
    changed_sequence = replace(SUBMISSION, sequence=SUBMISSION.sequence + "A")
    changed_manifest = replace(screened, manifest=replace(MANIFEST, database_sha256="a" * 64))
    assert not gate.evaluate(
        changed_sequence, screened, now=NOW, review_token=token, signer=signer
    ).release_allowed
    assert not gate.evaluate(
        SUBMISSION, changed_manifest, now=NOW, review_token=token, signer=signer
    ).release_allowed


def test_authenticated_malformed_review_payload_fails_closed():
    import base64
    import hashlib
    import hmac
    import json

    review = SafetyGate().evaluate(
        SUBMISSION,
        evidence(
            findings=(Finding(FindingKind.AMR, MARKER.gene_identity, "confirmed", "local:fixture"),)
        ),
        now=NOW,
    )
    signer = ReviewTokenSigner(b"test-only-signing-key")
    for payload in ([], None, {"approver": []}, {"approver": "reviewer", "expires_at": []}):
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = (
            base64.urlsafe_b64encode(
                hmac.new(signer.secret, encoded.encode(), hashlib.sha256).digest()
            )
            .decode()
            .rstrip("=")
        )
        assert not signer.authorizes(f"{encoded}.{signature}", review, now=NOW)


def test_commec_requires_pinned_policy_and_software_provenance(monkeypatch, tmp_path):
    import json
    from dataclasses import asdict, replace

    from engine.safety import stored_release_allowed

    manifest = replace(MANIFEST, adapter_name="ibbis-common-mechanism", adapter_version="2.1.0")
    assert not manifest.is_valid_at(NOW)
    manifest = replace(
        manifest, policy_version="commec-resolved-findings-v2", software_sha256="a" * 64
    )
    result = SafetyGate().evaluate(
        SUBMISSION, ScreeningEvidence(manifest, AdapterStatus.COMPLETE), now=NOW
    )
    config = tmp_path / "active.json"
    config.write_text(json.dumps({"manifest": asdict(manifest)}, default=lambda d: d.isoformat()))
    monkeypatch.setenv("CERNAL_COMMEC_MANIFEST", str(config))
    design = release_design(result)
    assert stored_release_allowed(design, now=NOW)
    assert result.release_record()["adapter"]["policy_version"] == "commec-resolved-findings-v2"
    assert result.release_record()["adapter"]["software_sha256"] == "a" * 64
    design["sequence_release"]["switch"]["adapter"]["policy_version"] = "unknown-policy"
    assert not stored_release_allowed(design, now=NOW)
    design = release_design(result)
    design["sequence_release"]["plasmid"]["adapter"]["software_sha256"] = ""
    assert not stored_release_allowed(design, now=NOW)
    changed = replace(result, manifest=replace(manifest, software_sha256="b" * 64))
    assert result.result_sha256 != changed.result_sha256
