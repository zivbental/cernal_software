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
