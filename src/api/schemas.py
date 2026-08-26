"""Request and response shapes.

Field names match the domain model, so the generated OpenAPI document reads the same as
docs/domain-model.md. Nothing here exposes storage paths or internal identifiers.
"""

from datetime import datetime
from uuid import UUID

from ninja import Field, ModelSchema, Schema

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
    """The polling response (docs/software-design.md §7.1). Deliberately cheap."""

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


# --- Meta -------------------------------------------------------------------------


class GateFamilyOut(Schema):
    """A selectable switch mechanism, described by the engine.

    ``available`` is what the UI greys out — the frontend must not keep its own list of
    which mechanisms are ready (docs/software-design.md §3).
    """

    name: str
    label: str
    description: str
    available: bool


class VersionOut(Schema):
    app_version: str
    api_schema_version: str
    engine: str
    engine_version: str
    engine_schema_version: str
    gate_families: list[GateFamilyOut]
    scoring_profiles: list[str]
