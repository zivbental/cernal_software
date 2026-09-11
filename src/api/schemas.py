"""Request and response shapes.

Field names match the domain model, so the generated OpenAPI document reads the same as
docs/domain-model.md. Nothing here exposes storage paths or internal identifiers.
"""

from datetime import datetime
from uuid import UUID

from ninja import Field, ModelSchema, Schema

from apps.accounts.models import ApiKey
from apps.analyses.models import AnalysisRun
from apps.datasets.models import Dataset
from apps.projects.models import Project
from apps.results.models import Annotation, Artifact, Candidate

# --- Auth -------------------------------------------------------------------------


class LoginIn(Schema):
    username: str
    password: str


class RegisterIn(Schema):
    # Length and strength rules live in apps.accounts.services, not here: Django's
    # password validators and the service produce messages an applicant can act on,
    # where a schema violation only yields a generic "request body is invalid".
    username: str = Field(max_length=150)
    email: str = Field(max_length=254)
    password: str
    full_name: str = ""


class RegistrationOut(Schema):
    """Deliberately not a session — the account is not usable yet."""

    username: str
    email: str
    pending_approval: bool
    message: str


class UserOut(Schema):
    id: int
    username: str
    email: str
    is_staff: bool


# --- API keys (ADR 0006) -----------------------------------------------------------


class ApiKeyCreateIn(Schema):
    label: str = Field(max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["read", "design"])
    expires_in_days: int | None = Field(default=None, description="Never expires if omitted.")


class ApiKeyOut(ModelSchema):
    """Never the secret — only its prefix (ADR 0006)."""

    class Meta:
        model = ApiKey
        fields = [
            "id",
            "label",
            "prefix",
            "scopes",
            "max_concurrent_runs",
            "rate_per_minute",
            "expires_at",
            "revoked_at",
            "last_used_at",
            "created_at",
        ]


class ApiKeyCreatedOut(ApiKeyOut):
    """The only response that ever carries the secret — shown once, at creation."""

    secret: str


class WhoAmIOut(Schema):
    """What ``GET /api/auth/whoami`` confirms: the key works, and what it can do."""

    username: str
    scopes: list[str]
    max_concurrent_runs: int
    rate_per_minute: int
    expires_at: datetime | None
    key_label: str
    key_prefix: str


# --- Projects ---------------------------------------------------------------------


class ProjectIn(Schema):
    name: str = Field(max_length=200)
    organism: str = Field(max_length=100)
    biological_objective: str = ""


class ProjectPatch(Schema):
    name: str | None = Field(default=None, max_length=200)
    organism: str | None = Field(default=None, max_length=100)
    biological_objective: str | None = None


class ProjectOut(ModelSchema):
    dataset_count: int = 0
    run_count: int = 0

    class Meta:
        model = Project
        fields = ["id", "name", "organism", "biological_objective", "created_at", "updated_at"]


# --- Datasets ---------------------------------------------------------------------


class ExampleDatasetOut(Schema):
    """A bundled dataset a researcher can try the product with."""

    key: str
    label: str
    description: str


class UseExampleIn(Schema):
    key: str = "ecoli-oxidative-stress"


class DatasetOut(ModelSchema):
    project_id: UUID
    filename: str

    class Meta:
        model = Dataset
        fields = [
            "id",
            "name",
            "checksum_sha256",
            "size_bytes",
            "schema_version",
            "validation_status",
            "validation_report",
            "created_at",
        ]

    @staticmethod
    def resolve_filename(obj) -> str:
        """The original name only — never the storage path (§7.2)."""
        return obj.name


# --- Runs -------------------------------------------------------------------------


class RunIn(Schema):
    input_mode: str = Field(
        default="de", description="de = upload a table · direct = paste a trigger mRNA"
    )
    dataset_id: UUID | None = Field(default=None, description="Required when input_mode is de.")
    trigger_sequence: str = Field(default="", description="Required when input_mode is direct.")
    params: dict = Field(default_factory=dict)
    gate_families: list[str] = Field(default_factory=lambda: ["toehold"])
    scoring_profile: str = "default"
    seed: int | None = None
    idempotency_key: str | None = Field(
        default=None,
        max_length=64,
        description="Resubmitting with the same key returns the existing run.",
    )


class RunCounts(Schema):
    candidates: int
    artifacts: int


class RunStatusOut(Schema):
    """The polling response (docs/architecture.md §7.1). Deliberately cheap."""

    id: UUID
    status: str
    stage: str
    progress_pct: int
    error_summary: str | None
    warnings: list[str]
    submitted_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    counts: RunCounts


class RunOut(ModelSchema):
    project_id: UUID
    dataset_id: UUID | None

    class Meta:
        model = AnalysisRun
        fields = [
            "id",
            "status",
            "stage",
            "progress_pct",
            "input_mode",
            "trigger_sequence",
            "gate_families",
            "scoring_profile",
            "seed",
            "params_snapshot",
            "engine_version",
            "error_summary",
            "warnings",
            "cancel_requested",
            "submitted_at",
            "started_at",
            "finished_at",
            "created_at",
        ]


class CancelOut(Schema):
    id: UUID
    status: str
    outcome: str = Field(
        description="cancelled · cancellation_requested · already_terminal",
    )


# --- Results ----------------------------------------------------------------------


class MetricOut(Schema):
    name: str
    raw_value: float | None
    normalized_value: float | None
    weight: float
    direction: str


class CandidateOut(ModelSchema):
    run_id: UUID
    output: str | None

    @staticmethod
    def resolve_output(obj) -> str | None:
        """What this candidate expresses.

        A run can target several equivalent outputs, each compiled into its own
        plasmids, so the list view needs to distinguish them without fetching every
        candidate's full design.
        """
        graph = (obj.design or {}).get("logic_graph") or {}
        return graph.get("output")

    class Meta:
        model = Candidate
        fields = [
            "id",
            "engine_ref",
            "rank",
            "overall_score",
            "gate_family",
            "logic_type",
            "summary",
            "warnings",
            "is_rejected",
            "rejection_reason",
        ]


class CandidateDetailOut(CandidateOut):
    triggers: dict
    design: dict
    metrics: list[MetricOut]

    @staticmethod
    def resolve_metrics(obj) -> list:
        return list(obj.metrics.all())


class ArtifactOut(ModelSchema):
    run_id: UUID
    candidate_id: UUID | None
    download_url: str

    class Meta:
        model = Artifact
        fields = ["id", "kind", "media_type", "checksum_sha256", "size_bytes", "created_at"]

    @staticmethod
    def resolve_download_url(obj) -> str:
        """An API path, never a storage location (§7.2)."""
        return f"/api/artifacts/{obj.id}/download"


class AnnotationIn(Schema):
    text: str = ""
    decision_tag: str = "NONE"


class AnnotationOut(ModelSchema):
    candidate_id: UUID
    author: str

    class Meta:
        model = Annotation
        fields = ["id", "text", "decision_tag", "created_at"]

    @staticmethod
    def resolve_author(obj) -> str:
        return obj.author.get_username()


# --- Design (docs/public-api.md §8-§9): the one-call fast path --------------------


class DesignIn(Schema):
    """Everything ``POST /api/design`` accepts. ``constraints``, ``scoring``,
    ``budget`` and ``payload`` are free-form dicts, not nested schemas — the same
    reason ``RunIn.params`` is a dict: their real shape is ``engine.domain.Constraints``
    / a scoring profile / etc, which ``api/`` may not import (architecture.md §3).
    ``strict`` (default ``True``, unlike the legacy run endpoint) is what catches a
    misspelled key here instead of ``engine.scoring`` silently discarding it
    (CLAUDE.md §2).
    """

    # --- input (exactly one) ---
    trigger_sequence: str = ""
    dataset_id: UUID | None = None
    dge_csv: str = ""
    project: str = Field(default="", description="Name or UUID; created if absent.")

    # --- biology ---
    organism: str = Field(default="", description="Only used when creating a project.")
    payload: dict = Field(
        default_factory=dict, description='{"outputs": [...], "custom_sequence": ...}'
    )

    # --- which chemistries may be used ---
    gate_families: list[str] | None = None
    exclude_gate_families: list[str] = Field(default_factory=list)

    # --- search constraints: engine.domain.Constraints, field for field ---
    constraints: dict = Field(default_factory=dict)

    # --- how candidates are compared (§9.1) ---
    scoring: dict = Field(default_factory=dict)

    # --- cost ceiling (§9.3) ---
    budget: dict = Field(default_factory=dict)

    # --- output shaping ---
    top_n: int = 25
    include_rejected: bool = False
    include_metrics: bool = True
    include_artifacts: list[str] = Field(default_factory=list)

    # --- reproducibility & control ---
    seed: int | None = None
    idempotency_key: str | None = None
    strict: bool = True
    notes: str = ""


class DesignEstimateOut(Schema):
    designs: int
    seconds: float
    confidence: str = Field(description='"rough" or "very rough" — never a guarantee.')


class DesignResolvedOut(Schema):
    """Every default the server chose, echoed back — so a run is reproducible from its
    response alone (docs/public-api.md §8). ``constraints`` here is exactly what the
    caller supplied, not padded with engine-side defaults: computing those would mean
    duplicating engine.domain.Constraints' defaults in api/, which the boundary rule
    (architecture.md §3) forbids importing and CLAUDE.md §3 forbids re-deriving."""

    input_mode: str
    gate_families: list[str]
    scoring_profile: str
    seed: int | None
    constraints: dict


class DesignAcceptedOut(Schema):
    job_id: UUID
    status: str
    progress_pct: int
    poll_url: str
    results_url: str
    web_url: str
    estimate: DesignEstimateOut
    resolved: DesignResolvedOut


class DesignResponseOut(Schema):
    """The 200 shape — serves two different callers with one schema, both additive
    (docs/public-api.md §10): a resolved ``wait=`` result (job_id/status/candidates)
    and a ``dry_run=true`` estimate (estimate/budget_ok). Each caller ignores the
    fields meant for the other, exactly as the compatibility promise expects."""

    resolved: DesignResolvedOut
    # populated when wait= resolved before the deadline
    job_id: UUID | None = None
    status: str | None = None
    candidates: list[CandidateDetailOut] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)
    # populated for dry_run=true
    estimate: DesignEstimateOut | None = None
    budget_ok: bool | None = None


# --- Meta -------------------------------------------------------------------------


class GateFamilyOut(Schema):
    """A selectable switch mechanism, described by the engine.

    ``available`` is what the UI greys out — the frontend must not keep its own list of
    which mechanisms are ready (docs/architecture.md §3).
    """

    name: str
    label: str
    description: str
    available: bool


class MetricInfoOut(Schema):
    """One scoring metric, as advertised by the engine (engine.contract.MetricInfo).

    What lets a caller validate a custom ``scoring.weights`` block against the real
    vocabulary instead of discovering a typo as a silently-worst-scored candidate
    (CLAUDE.md §2, docs/public-api.md §7/§9.1).
    """

    name: str
    direction: str
    weight: float
    valid_range: tuple[float, float]
    unit: str = ""
    description: str = ""


class HardFilterOut(Schema):
    metric: str
    minimum: float | None = None
    maximum: float | None = None
    reason: str = ""


class VersionOut(Schema):
    app_version: str
    api_schema_version: str
    engine: str
    engine_version: str
    engine_schema_version: str
    gate_families: list[GateFamilyOut]
    scoring_profiles: list[str]
    metrics: list[MetricInfoOut] = Field(default_factory=list)
    hard_filters: list[HardFilterOut] = Field(default_factory=list)
