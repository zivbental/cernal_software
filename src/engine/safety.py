"""Offline-first, fail-closed release control for output sequences.

This module is a policy boundary, not a sequence-design or external screening service.
Adapters are local-only by contract. Until a validated local database/tool manifest is
provided, ``UnavailableLocalAdapter`` returns ``HOLD_SYSTEM`` evidence and no sequence may
be released.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class Decision(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
    HOLD_SYSTEM = "HOLD_SYSTEM"


class AdapterStatus(StrEnum):
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class FindingKind(StrEnum):
    AMR = "AMR"
    OTHER_HAZARD = "OTHER_HAZARD"


_VALID_BASES = frozenset("ACGTU")
_HEX = frozenset("0123456789abcdef")


@dataclass(frozen=True, slots=True)
class DeclaredSelectableMarker:
    """A specific intended selectable marker; never a general AMR bypass."""

    gene_identity: str
    role: str
    host_context: str
    plasmid_context: str
    justification: str
    approval_reference: str

    def is_complete(self) -> bool:
        return self.role == "selectable_marker" and all(
            value.strip()
            for value in (
                self.gene_identity,
                self.host_context,
                self.plasmid_context,
                self.justification,
                self.approval_reference,
            )
        )


@dataclass(frozen=True, slots=True)
class SequenceSubmission:
    sequence_id: str
    sequence: str
    delivery_method: str
    host_context: str
    declared_markers: tuple[DeclaredSelectableMarker, ...] = ()

    @property
    def sequence_sha256(self) -> str:
        return hashlib.sha256(self.sequence.encode("ascii", errors="ignore")).hexdigest()

    def validation_errors(self) -> tuple[str, ...]:
        sequence = self.sequence.strip().upper()
        errors: list[str] = []
        if not self.sequence_id.strip():
            errors.append("missing sequence identity")
        if self.delivery_method != "plasmid":
            errors.append("delivery method must be declared as plasmid")
        if not self.host_context.strip():
            errors.append("missing host context")
        if not sequence or set(sequence) - _VALID_BASES or ("T" in sequence and "U" in sequence):
            errors.append("malformed sequence")
        if len({marker.gene_identity for marker in self.declared_markers}) != len(
            self.declared_markers
        ):
            errors.append("duplicate declared marker identity")
        if any(not marker.is_complete() for marker in self.declared_markers):
            errors.append("incomplete selectable marker declaration")
        return tuple(errors)


@dataclass(frozen=True, slots=True)
class LocalScreeningManifest:
    """Immutable identity and validation window for a local screening deployment."""

    adapter_name: str
    adapter_version: str
    database_id: str
    database_sha256: str
    validated_at: datetime
    expires_at: datetime

    def is_valid_at(self, now: datetime) -> bool:
        digest = self.database_sha256.lower()
        return (
            bool(self.adapter_name.strip())
            and bool(self.adapter_version.strip())
            and bool(self.database_id.strip())
            and len(digest) == 64
            and set(digest) <= _HEX
            and self.validated_at.tzinfo is not None
            and self.expires_at.tzinfo is not None
            and self.validated_at <= now < self.expires_at
        )


@dataclass(frozen=True, slots=True)
class Finding:
    kind: FindingKind
    identity: str
    confidence: str
    evidence_reference: str

    @property
    def is_ambiguous(self) -> bool:
        return self.confidence != "confirmed"


@dataclass(frozen=True, slots=True)
class ScreeningEvidence:
    manifest: LocalScreeningManifest
    adapter_status: AdapterStatus
    findings: tuple[Finding, ...] = ()


class LocalScreeningAdapter(Protocol):
    """Local-only adapter contract. Implementations must not transmit the sequence."""

    def screen(self, submission: SequenceSubmission) -> ScreeningEvidence: ...


@dataclass(frozen=True, slots=True)
class UnavailableLocalAdapter:
    """Safe default when a validated local tool/database has not been provisioned."""

    manifest: LocalScreeningManifest

    def screen(self, submission: SequenceSubmission) -> ScreeningEvidence:
        del submission
        return ScreeningEvidence(manifest=self.manifest, adapter_status=AdapterStatus.UNAVAILABLE)


@dataclass(frozen=True, slots=True)
class ReviewTokenSigner:
    """Signs review-only release tokens bound to one exact screening result."""

    secret: bytes

    def issue(self, result: SafetyScreenResult, *, approver: str, expires_at: datetime) -> str:
        if result.decision is not Decision.REVIEW:
            raise ValueError("review tokens may only authorize REVIEW decisions")
        if not approver.strip() or expires_at.tzinfo is None:
            raise ValueError("approver and timezone-aware expiry are required")
        payload = {
            "approver": approver,
            "decision": result.decision.value,
            "expires_at": expires_at.astimezone(UTC).isoformat(),
            "result_sha256": result.result_sha256,
            "sequence_sha256": result.sequence_sha256,
        }
        encoded = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        signature = _b64(hmac.new(self.secret, encoded.encode(), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def authorizes(self, token: str | None, result: SafetyScreenResult, *, now: datetime) -> bool:
        if not token or result.decision is not Decision.REVIEW or now.tzinfo is None:
            return False
        try:
            encoded, signature = token.split(".", 1)
            expected = _b64(hmac.new(self.secret, encoded.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                return False
            payload = json.loads(_unb64(encoded))
            expiry = datetime.fromisoformat(payload["expires_at"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return (
            expiry.tzinfo is not None
            and now < expiry
            and payload.get("decision") == Decision.REVIEW.value
            and payload.get("sequence_sha256") == result.sequence_sha256
            and payload.get("result_sha256") == result.result_sha256
            and bool(payload.get("approver", "").strip())
        )


@dataclass(frozen=True, slots=True)
class SafetyScreenResult:
    decision: Decision
    sequence_sha256: str
    manifest: LocalScreeningManifest
    findings: tuple[Finding, ...]
    declared_marker_findings: tuple[Finding, ...]
    unexpected_marker_findings: tuple[Finding, ...]
    reasons: tuple[str, ...]
    release_allowed: bool = False
    result_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "decision": self.decision.value,
            "findings": [
                (
                    finding.kind.value,
                    finding.identity,
                    finding.confidence,
                    finding.evidence_reference,
                )
                for finding in self.findings
            ],
            "manifest": (
                self.manifest.adapter_name,
                self.manifest.adapter_version,
                self.manifest.database_id,
                self.manifest.database_sha256,
                self.manifest.validated_at.isoformat(),
                self.manifest.expires_at.isoformat(),
            ),
            "reasons": self.reasons,
            "sequence_sha256": self.sequence_sha256,
        }
        object.__setattr__(
            self,
            "result_sha256",
            hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )

    def audit_manifest(self) -> dict:
        return {
            "decision": self.decision.value,
            "release_allowed": self.release_allowed,
            "sequence_sha256": self.sequence_sha256,
            "result_sha256": self.result_sha256,
            "adapter": {
                "name": self.manifest.adapter_name,
                "version": self.manifest.adapter_version,
                "database_id": self.manifest.database_id,
                "database_sha256": self.manifest.database_sha256,
                "validated_at": self.manifest.validated_at.isoformat(),
                "expires_at": self.manifest.expires_at.isoformat(),
            },
            "reasons": list(self.reasons),
            "declared_marker_findings": [
                finding.identity for finding in self.declared_marker_findings
            ],
            "unexpected_marker_findings": [
                finding.identity for finding in self.unexpected_marker_findings
            ],
        }


class SafetyGate:
    """Deterministic policy evaluator: no evidence gap can become a release."""

    def evaluate(
        self,
        submission: SequenceSubmission,
        evidence: ScreeningEvidence,
        *,
        now: datetime,
        review_token: str | None = None,
        signer: ReviewTokenSigner | None = None,
    ) -> SafetyScreenResult:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        errors = list(submission.validation_errors())
        if errors:
            return self._result(Decision.HOLD_SYSTEM, submission, evidence, (), (), tuple(errors))
        if evidence.adapter_status is not AdapterStatus.COMPLETE:
            return self._result(
                Decision.HOLD_SYSTEM,
                submission,
                evidence,
                (),
                (),
                (f"local screening adapter status is {evidence.adapter_status.value}",),
            )
        if not evidence.manifest.is_valid_at(now):
            return self._result(
                Decision.HOLD_SYSTEM,
                submission,
                evidence,
                (),
                (),
                ("local screening manifest is stale or invalid",),
            )
        if any(finding.is_ambiguous for finding in evidence.findings):
            return self._result(
                Decision.HOLD_SYSTEM,
                submission,
                evidence,
                (),
                (),
                ("ambiguous screening evidence",),
            )

        declared_ids = {marker.gene_identity for marker in submission.declared_markers}
        declared = tuple(
            finding
            for finding in evidence.findings
            if finding.kind is FindingKind.AMR and finding.identity in declared_ids
        )
        unexpected = tuple(
            finding
            for finding in evidence.findings
            if finding.kind is FindingKind.AMR and finding.identity not in declared_ids
        )
        hazards = tuple(
            finding for finding in evidence.findings if finding.kind is FindingKind.OTHER_HAZARD
        )
        if unexpected or hazards:
            reasons = tuple(
                ["unexpected resistance determinant" for _ in unexpected]
                + ["confirmed non-marker hazard" for _ in hazards]
            )
            return self._result(Decision.BLOCK, submission, evidence, declared, unexpected, reasons)
        if declared:
            result = self._result(
                Decision.REVIEW,
                submission,
                evidence,
                declared,
                (),
                ("declared selectable marker requires documented human approval",),
            )
            allowed = signer.authorizes(review_token, result, now=now) if signer else False
            return SafetyScreenResult(
                decision=result.decision,
                sequence_sha256=result.sequence_sha256,
                manifest=result.manifest,
                findings=result.findings,
                declared_marker_findings=result.declared_marker_findings,
                unexpected_marker_findings=result.unexpected_marker_findings,
                reasons=result.reasons,
                release_allowed=allowed,
            )
        return self._result(
            Decision.PASS,
            submission,
            evidence,
            (),
            (),
            ("no reportable findings",),
            release_allowed=True,
        )

    @staticmethod
    def _result(
        decision: Decision,
        submission: SequenceSubmission,
        evidence: ScreeningEvidence,
        declared: tuple[Finding, ...],
        unexpected: tuple[Finding, ...],
        reasons: tuple[str, ...],
        *,
        release_allowed: bool = False,
    ) -> SafetyScreenResult:
        return SafetyScreenResult(
            decision=decision,
            sequence_sha256=submission.sequence_sha256,
            manifest=evidence.manifest,
            findings=evidence.findings,
            declared_marker_findings=declared,
            unexpected_marker_findings=unexpected,
            reasons=reasons,
            release_allowed=release_allowed,
        )


def fail_closed_release(
    sequence_id: str, sequence: str, *, host_context: str
) -> SafetyScreenResult:
    """Return auditable HOLD_SYSTEM evidence when no local screening stack is provisioned.

    This is the production-safe default used at the artifact boundary. A future local
    adapter must replace this call with complete, validated evidence; it must never make
    an unavailable tool look like a clean screen.
    """
    now = datetime.now(UTC)
    manifest = LocalScreeningManifest(
        adapter_name="unprovisioned-local-screening",
        adapter_version="0",
        database_id="unavailable",
        database_sha256="0" * 64,
        validated_at=now,
        expires_at=now,
    )
    submission = SequenceSubmission(
        sequence_id=sequence_id,
        sequence=sequence,
        delivery_method="plasmid",
        host_context=host_context,
    )
    return SafetyGate().evaluate(
        submission,
        UnavailableLocalAdapter(manifest).screen(submission),
        now=now,
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode()
