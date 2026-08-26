"""The Platform ⇄ Engine contract.

These dataclasses are the *only* types that cross the boundary described in
docs/architecture.md §3. Their fields deliberately mirror the payloads the design
maps specify for ``POST /v1/jobs`` and the result manifest, so that promoting the engine
to a standalone HTTP service later is a serialisation exercise and nothing more.

Nothing in this module may import Django, Pydantic, or anything from ``apps``/``api``.
See docs/engine.md §1 for the field-for-field HTTP mapping.
"""

from dataclasses import dataclass, field

#: Bumped only for breaking changes to the shapes below.
SCHEMA_VERSION = "1"

#: Metric direction — which way is better.
HIGHER_BETTER = "HIGHER_BETTER"
LOWER_BETTER = "LOWER_BETTER"

#: How the researcher supplied the trigger.
INPUT_DE = "de"  # differential-expression table
INPUT_DIRECT = "direct"  # an mRNA sequence pasted straight in

#: Terminal job outcomes.
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class JobRequest:
    """An immutable request for one scientific computation.

    Carries *references and values only* — never a Django model, a file handle or an
    open connection. ``input_path`` is an absolute path the engine may read; the engine
    re-verifies ``input_checksum`` before using it.
    """

    schema_version: str
    run_id: str
    idempotency_key: str
    input_mode: str
    input_path: str
    input_checksum: str
    trigger_sequence: str
    organism: str
    params: dict
    gate_families: list[str]
    scoring_profile: str
    seed: int | None
    output_dir: str

    @property
    def is_direct_trigger(self) -> bool:
        """True when the researcher pasted a sequence instead of uploading a table."""
        return self.input_mode == INPUT_DIRECT

    def mock_options(self) -> dict:
        """Options consumed by MockEngine. Ignored by every real implementation."""
        options = self.params.get("mock", {})
        return options if isinstance(options, dict) else {}


@dataclass(frozen=True, slots=True)
class GateFamilyInfo:
    """One selectable switch mechanism, as the engine describes itself.

    ``available`` is what the UI greys out. Keeping it here rather than in React means
    Step 5 can enable CRISPR by flipping one class attribute, with no frontend change.
    """

    name: str
    label: str
    description: str
    available: bool


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """What this engine build can do.

    The Platform needs to validate a submission's gate families and scoring profile, but
    §3 forbids it importing ``engine.gates`` or ``engine.scoring``. So the engine
    advertises its capabilities instead — the in-process form of the ``GET /version``
    capability document in design map 08.
    """

    engine_version: str
    schema_version: str
    gate_families: list[GateFamilyInfo]
    scoring_profiles: list[str]

    @property
    def available_families(self) -> list[str]:
        """Names the Platform will accept on a submission."""
        return [family.name for family in self.gate_families if family.available]


@dataclass(frozen=True, slots=True)
class MetricValue:
    """One measured property of a candidate, with its scoring metadata preserved.

    Both ``raw_value`` and ``normalized_value`` are kept: the decomposition is reported
    to the researcher, never just an opaque final score (design map 12).
    """

    name: str
    raw_value: float | None
    normalized_value: float | None
    weight: float
    direction: str


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """A file the engine produced, addressed relative to ``JobRequest.output_dir``."""

    kind: str
    path: str
    media_type: str
    checksum_sha256: str
    candidate_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateResult:
    """One proposed circuit.

    Rejected candidates are returned too, with ``rejection_reason`` populated. They are
    never silently dropped — a researcher needs to see what was considered and why it
    lost (design map 11, rule 8).
    """

    ref: str
    rank: int | None
    overall_score: float | None
    gate_family: str
    logic_type: str
    triggers: dict
    design: dict
    summary: str
    metrics: list[MetricValue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_rejected: bool = False
    rejection_reason: str = ""


@dataclass(frozen=True, slots=True)
class JobResult:
    """The versioned result manifest.

    ``input_checksum`` and ``params`` are echoed back so the Platform can verify that the
    engine computed against what was actually submitted.
    """

    schema_version: str
    engine_version: str
    status: str
    candidates: list[CandidateResult] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    input_checksum: str = ""
    params: dict = field(default_factory=dict)

    @property
    def accepted(self) -> list[CandidateResult]:
        """Non-rejected candidates, in rank order."""
        return sorted(
            (c for c in self.candidates if not c.is_rejected),
            key=lambda c: (c.rank is None, c.rank),
        )

    @property
    def rejected(self) -> list[CandidateResult]:
        """Excluded candidates, each carrying its reason. Never silently dropped."""
        return [c for c in self.candidates if c.is_rejected]
