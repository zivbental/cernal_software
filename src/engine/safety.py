"""Offline-first, fail-closed release control for output sequences.

This module is a policy boundary, not a sequence-design or external screening service.
Adapters are local-only by contract. Until a validated local database/tool manifest is
provided, ``UnavailableLocalAdapter`` returns ``HOLD_SYSTEM`` evidence and no sequence may
be released.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
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
    INCONCLUSIVE = "INCONCLUSIVE"


class FindingKind(StrEnum):
    AMR = "AMR"
    OTHER_HAZARD = "OTHER_HAZARD"
    SCREENING_FLAG = "SCREENING_FLAG"


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
    policy_version: str = "safety-v2"
    software_sha256: str = ""

    def is_valid_at(self, now: datetime) -> bool:
        digest = self.database_sha256.lower()
        return (
            bool(self.adapter_name.strip())
            and bool(self.adapter_version.strip())
            and bool(self.database_id.strip())
            and bool(self.policy_version.strip())
            and (
                self.adapter_name != "ibbis-common-mechanism"
                or (
                    self.adapter_version == "2.1.0"
                    and self.policy_version == "commec-exact-pass-v1"
                    and _is_sha256(self.software_sha256)
                )
            )
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
            if not isinstance(payload, dict) or not isinstance(payload.get("approver"), str):
                return False
            expiry = datetime.fromisoformat(payload["expires_at"])
        except (KeyError, TypeError, ValueError, AttributeError, UnicodeError):
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
    approval_expires_at: datetime | None = None
    adapter_status: AdapterStatus = AdapterStatus.COMPLETE
    result_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "decision": self.decision.value,
            "adapter_status": self.adapter_status.value,
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
                self.manifest.policy_version,
                self.manifest.software_sha256,
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

    @property
    def screening_status(self) -> str:
        if self.adapter_status is AdapterStatus.UNAVAILABLE:
            return "unavailable"
        if self.adapter_status in (AdapterStatus.STALE, AdapterStatus.INCONCLUSIVE):
            return "inconclusive"
        if self.adapter_status in (AdapterStatus.FAILED, AdapterStatus.TIMEOUT):
            return "error"
        if self.decision in (Decision.REVIEW, Decision.BLOCK):
            return "flagged"
        if self.decision is Decision.PASS:
            return "screened"
        return "inconclusive"

    def audit_manifest(self) -> dict:
        return {
            "decision": self.decision.value,
            "adapter_status": self.adapter_status.value,
            "release_allowed": self.release_allowed,
            "screening_status": self.screening_status,
            "sequence_sha256": self.sequence_sha256,
            "result_sha256": self.result_sha256,
            "approval_expires_at": (
                self.approval_expires_at.isoformat() if self.approval_expires_at else None
            ),
            "adapter": {
                "name": self.manifest.adapter_name,
                "version": self.manifest.adapter_version,
                "database_id": self.manifest.database_id,
                "database_sha256": self.manifest.database_sha256,
                "policy_version": self.manifest.policy_version,
                "software_sha256": self.manifest.software_sha256,
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

    def release_record(self) -> dict:
        """Retain expiry for download-time checks of provisioned screening evidence.

        Only the unprovisioned, always-held default omits time-dependent fields so
        unavailable screening does not make otherwise deterministic output vary.
        Missing expiry can never authorize disclosure.
        """
        record = self.audit_manifest()
        record["schema"] = "sequence-release-v2"
        if (
            self.manifest.adapter_name == "unprovisioned-local-screening"
            and self.decision is Decision.HOLD_SYSTEM
            and not self.release_allowed
        ):
            record.pop("result_sha256")
            record["adapter"].pop("validated_at")
            record["adapter"].pop("expires_at")
        return record


def stored_release_allowed(design: object, *, now: datetime | None = None) -> bool:
    """Revalidate persisted release evidence at every disclosure boundary.

    Records are trusted server-side screening metadata, not user-supplied approval.
    Legacy records without validation windows fail closed. Approval of a REVIEW
    cannot outlive either the verified review token or the screening deployment.
    This check never reruns screening or interprets artifact presence as approval.
    """
    now = datetime.now(UTC) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return False
    if not isinstance(design, dict):
        return False
    release = design.get("sequence_release")
    sequence = design.get("switch_sequence")
    if not isinstance(release, dict) or not isinstance(sequence, str) or not sequence:
        return False
    expected = {
        "switch": hashlib.sha256(sequence.encode()).hexdigest(),
        "plasmid": design.get("construct_sha256"),
    }
    for kind, digest in expected.items():
        record = release.get(kind)
        if (
            not isinstance(record, dict)
            or record.get("schema") != "sequence-release-v2"
            or record.get("release_allowed") is not True
            or record.get("adapter_status") != "COMPLETE"
            or record.get("screening_status")
            != ("screened" if record.get("decision") == "PASS" else "flagged")
            or record.get("decision") not in ("PASS", "REVIEW")
            or not _is_sha256(digest)
            or record.get("sequence_sha256") != digest
            or not _is_sha256(record.get("result_sha256"))
        ):
            return False
        adapter = record.get("adapter")
        if not isinstance(adapter, dict):
            return False
        try:
            manifest = LocalScreeningManifest(
                adapter_name=adapter["name"],
                adapter_version=adapter["version"],
                database_id=adapter["database_id"],
                database_sha256=adapter["database_sha256"],
                policy_version=adapter["policy_version"],
                software_sha256=adapter["software_sha256"],
                validated_at=datetime.fromisoformat(adapter["validated_at"]),
                expires_at=datetime.fromisoformat(adapter["expires_at"]),
            )
            if not manifest.is_valid_at(now):
                return False
            if manifest.adapter_name == "ibbis-common-mechanism" and not _active_manifest_matches(
                manifest
            ):
                return False
            if record["decision"] == "REVIEW":
                approval_expiry = datetime.fromisoformat(record["approval_expires_at"])
                if approval_expiry.tzinfo is None or not now < approval_expiry:
                    return False
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return False
    return True


def _unique_json_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate screening configuration field")
        result[key] = value
    return result


def _active_manifest_matches(manifest: LocalScreeningManifest) -> bool:
    """Deployment rotation/revocation invalidates old grants without a 40 GB read.

    This checks the operator's active identity, not mutable database bytes. Runtime
    DB/software must be immutable, versioned and read-only; full inventory hashing
    is performed around screening before any grant is emitted.
    """
    try:
        path = Path(os.environ["CERNAL_COMMEC_MANIFEST"])
        if path.stat().st_size > 16 * 1024 * 1024:
            return False
        config = json.loads(path.read_text(), object_pairs_hook=_unique_json_fields)
        active = dict(config["manifest"])
        for key in ("validated_at", "expires_at"):
            active[key] = datetime.fromisoformat(active[key]).isoformat()
        return active == {
            "adapter_name": manifest.adapter_name,
            "adapter_version": manifest.adapter_version,
            "database_id": manifest.database_id,
            "database_sha256": manifest.database_sha256,
            "policy_version": manifest.policy_version,
            "software_sha256": manifest.software_sha256,
            "validated_at": manifest.validated_at.isoformat(),
            "expires_at": manifest.expires_at.isoformat(),
        }
    except (OSError, KeyError, TypeError, ValueError, AttributeError):
        return False


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def disclosed_candidate_data(design: object, triggers: object) -> tuple[dict, dict]:
    """Project held candidate data onto known non-sequence fields, without mutation."""
    design = design if isinstance(design, dict) else {}
    triggers = triggers if isinstance(triggers, dict) else {}
    allowed = stored_release_allowed(design)
    if allowed:
        disclosed = copy.deepcopy(design)
        disclosed["sequence_release"]["release_allowed"] = True
        return disclosed, copy.deepcopy(triggers)

    def pick(value, keys):
        if not isinstance(value, dict):
            return {}
        return {
            key: item
            for key, item in value.items()
            if key in keys and isinstance(item, (str, int, float, bool, type(None)))
        }

    def records(value):
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    # Unknown fields, architecture fragments and nested component switches must not
    # create an alternate route around the sequence release decision.
    safe_keys = {
        "toehold_length",
        "evaluation_context",
        "evaluation_sequence_sha256",
        "payload_sequence_sha256",
        "coding_junction",
        "family_version",
        "host",
        "structure_kind",
        "structure_deviation",
        "structural_rule_version",
        "maturity",
        "orthogonality_status",
        "assembly_method",
        "insertion_index",
        "payload_id",
        "construct_sha256",
        "topology",
        "sequence_length_bp",
        "trigger_start_index",
    }
    safe_design = {
        key: value
        for key, value in design.items()
        if key in safe_keys and isinstance(value, (str, int, float, bool, type(None)))
    }
    safe_design.update(switch_sequence="", structure="", architecture={})
    release = design.get("sequence_release")
    safe_design["sequence_release"] = {}
    if isinstance(release, dict):
        for kind in ("switch", "plasmid"):
            audit = release.get(kind)
            if isinstance(audit, dict):
                safe_design["sequence_release"][kind] = {
                    key: copy.deepcopy(audit[key])
                    for key in (
                        "schema",
                        "adapter_status",
                        "screening_status",
                        "decision",
                        "release_allowed",
                        "approval_expires_at",
                        "sequence_sha256",
                        "result_sha256",
                        "adapter",
                        "reasons",
                        "declared_marker_findings",
                        "unexpected_marker_findings",
                    )
                    if key in audit
                }
                safe_design["sequence_release"][kind]["adapter"] = pick(
                    audit.get("adapter"),
                    {
                        "name",
                        "version",
                        "database_id",
                        "database_sha256",
                        "policy_version",
                        "software_sha256",
                        "validated_at",
                        "expires_at",
                    },
                )
                decision = audit.get("decision")
                safe_design["sequence_release"][kind]["decision"] = (
                    decision
                    if isinstance(decision, str)
                    and decision in {"PASS", "REVIEW", "HOLD_SYSTEM", "BLOCK", "ERROR"}
                    else "INVALID"
                )
    safe_design["sequence_release"]["release_allowed"] = False
    safe_design["sequence_release"]["reason"] = (
        "Sequence disclosure is withheld: no matching release approval for both switch and plasmid."
    )
    safe_design["plasmid_segments"] = [
        pick(segment, {"kind", "name", "length_bp"})
        for segment in records(design.get("plasmid_segments"))
    ]
    graph = design.get("logic_graph")
    if isinstance(graph, dict):
        safe_design["logic_graph"] = pick(
            graph,
            {
                "mid_gate",
                "outer_gate",
                "invert",
                "output",
                "caption",
            },
        )

        safe_design["logic_graph"]["genes"] = [
            pick(gene, {"name", "role", "state", "direction"})
            for gene in records(graph.get("genes"))
        ]

    def folding_provenance(value):
        if not isinstance(value, dict):
            return {}
        result = pick(value, {"schema", "viennarna_version"})
        for key in ("configuration", "model_details"):
            block = value.get(key)
            if isinstance(block, dict):
                result[key] = {
                    name: item
                    for name, item in block.items()
                    if isinstance(item, (int, float, bool))
                }
                result[key].update(pick(block, {"energy_parameters", "model_version"}))
        result["energy_parameters"] = pick(
            value.get("energy_parameters"),
            {
                "name",
                "source",
                "sha256",
                "hash_basis",
            },
        )
        return result

    safe_design["coding_regions"] = [
        pick(region, {"start", "end", "name", "protein_sha256"})
        for region in records(design.get("coding_regions"))
    ]
    safe_design["tool_versions"] = pick(
        design.get("tool_versions"),
        {
            "viennarna",
            "ViennaRNA",
            "temperature_c",
        },
    )
    safe_design["folding_model"] = folding_provenance(design.get("folding_model"))
    feature_keys = {
        "feature_id",
        "gene_id",
        "gene_symbol",
        "transcript_id",
        "reference_accession",
        "reference_selection_method",
        "transcript_sequence_sha256",
        "log2_fold_change",
        "sequence_sha256",
        "openness",
        "accessibility",
        "selection_method",
        "selection_metric",
        "selection_score",
        "orientation",
        "gate_toehold_length",
        "hypothesis_start",
        "hypothesis_end",
        "joint_open_probability_20",
        "mean_marginal_openness_20",
        "delta_g_open_kcal_per_mol_per_nt",
        "selected_seed_start",
        "selected_seed_end",
        "selected_seed_probability",
        "start_index",
    }
    safe_triggers = {
        "features": [
            {
                key: value
                for key, value in feature.items()
                if key in feature_keys and isinstance(value, (str, int, float, bool, type(None)))
            }
            for feature in records(triggers.get("features"))
        ]
    }
    for source, feature in zip(
        records(triggers.get("features")), safe_triggers["features"], strict=True
    ):
        feature["seed_trials"] = [
            pick(trial, {"start", "end", "relative_start", "joint_probability"})
            for trial in records(source.get("seed_trials"))
        ]
        feature["rnaplfold"] = pick(
            source.get("rnaplfold"),
            {
                "viennarna_version",
                "window",
                "max_span",
                "unpaired",
                "temperature_celsius",
            },
        )
        rnaplfold = source.get("rnaplfold")
        if isinstance(rnaplfold, dict):
            feature["rnaplfold"]["folding_model"] = folding_provenance(
                rnaplfold.get("folding_model")
            )
    return safe_design, safe_triggers


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
        screening_flags = tuple(
            finding for finding in evidence.findings if finding.kind is FindingKind.SCREENING_FLAG
        )
        if unexpected or hazards or screening_flags:
            reasons = tuple(
                ["unexpected resistance determinant" for _ in unexpected]
                + ["confirmed non-marker hazard" for _ in hazards]
                + ["screening flag requires review" for _ in screening_flags]
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
                adapter_status=evidence.adapter_status,
                approval_expires_at=(
                    datetime.fromisoformat(
                        json.loads(_unb64(review_token.split(".", 1)[0]))["expires_at"]
                    )
                    if allowed and review_token
                    else None
                ),
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
            adapter_status=evidence.adapter_status,
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
