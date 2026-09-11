"""The one-call fast path (docs/public-api.md §8-§9).

Three thin wrappers over services that already exist — submit_run, the same status
read get_run_status builds, and the same candidate query list_candidates builds. No new
science, no new status transitions (architecture.md §6.2: those stay in
apps/analyses/services.py).

The design target: a scientist with a sequence gets ranked designs in four lines of R,
having read nothing.
"""

import difflib
import math
import time
from uuid import UUID

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import F
from ninja import Router, Status

from api.auth import get_owned
from api.errors import ApiError, ValidationFailed
from api.schemas import (
    DesignAcceptedOut,
    DesignIn,
    DesignResponseOut,
    RunCounts,
    RunStatusOut,
)
from api.security import enforce_concurrency_ceiling, require_scope
from apps.accounts.models import ApiKeyScope
from apps.analyses.models import AnalysisRun, InputMode, RunStatus
from apps.analyses.services import RunError, submit_run
from apps.datasets.models import Dataset
from apps.datasets.services import DatasetValidationError, create_dataset, validate_expression_file
from apps.results.models import Artifact, Candidate
from engine.client import label_for_custom_scoring, load_engine

router = Router()

#: A client blocking past this reads as the connection stalling, not the run failing —
#: keep it below any reverse-proxy write timeout (docs/public-api.md §8).
WAIT_HARD_CEILING = 300.0

#: ROADMAP.md §3, measured on ViennaRNA 2.7.2, one core: a fold + a cofold + a
#: partition function per design, ~15ms. Never presented as a guarantee.
_SECONDS_PER_DESIGN = 0.015
#: ROADMAP.md §3's own worked example: 1,225 trigger sets (top-50 genes, pairs) -> a
#: measured ~12,250 designs. Used only to keep dry_run's arithmetic consistent with the
#: one real data point this repo has.
_DESIGNS_PER_TRIGGER_SET = 10

_CONSTRAINT_KEYS = {
    "max_triggers",
    "min_separation",
    "max_p_adj",
    "trigger_lengths",
    "max_switch_length",
    "forbidden_motifs",
    "standard",
}
_SCORING_KEYS = {"base", "weights", "hard_filters", "tie_breakers"}
_BUDGET_KEYS = {"max_designs", "max_runtime_seconds", "on_exceed"}
_PAYLOAD_KEYS = {"outputs", "custom_sequence"}


class UnknownParameter(ApiError):
    status = 422
    code = "unknown_parameter"


def _check_known_keys(block: dict, allowed: set[str], name: str) -> None:
    """strict mode (§9.2): a typo becomes a 422 naming the mistake, instead of the
    silent CLAUDE.md §2 failure — an unknown key is simply never read."""
    unknown = sorted(set(block) - allowed)
    if not unknown:
        return
    bad = unknown[0]
    suggestion = difflib.get_close_matches(bad, allowed, n=1)
    raise UnknownParameter(
        f"Unknown {name} '{bad}'.",
        detail={"did_you_mean": suggestion[0] if suggestion else None, "allowed": sorted(allowed)},
    )


def _input_mode(body: DesignIn) -> str:
    provided = [
        name
        for name, value in (
            ("trigger_sequence", body.trigger_sequence),
            ("dataset_id", body.dataset_id),
            ("dge_csv", body.dge_csv),
        )
        if value
    ]
    if len(provided) != 1:
        raise ValidationFailed(
            "Provide exactly one of trigger_sequence, dataset_id or dge_csv.",
            detail={"provided": provided},
        )
    return InputMode.DIRECT if provided[0] == "trigger_sequence" else InputMode.DE


def _resolve_gate_families(body: DesignIn, capabilities) -> list[str]:
    available = capabilities.available_families

    if body.gate_families is not None:
        unknown = sorted(set(body.gate_families) - set(available))
        if unknown:
            raise ValidationFailed(
                f"Unavailable gate family/families: {', '.join(unknown)}.",
                detail={"available": available},
            )
        return list(body.gate_families)

    families = [name for name in available if name not in set(body.exclude_gate_families)]
    if not families:
        raise ValidationFailed("No gate family remains after applying exclude_gate_families.")
    return families


def _resolve_scoring(body: DesignIn, capabilities) -> dict:
    scoring = body.scoring
    if body.strict:
        _check_known_keys(scoring, _SCORING_KEYS, "scoring field")

    known = {metric.name for metric in capabilities.metrics}
    unknown = set(scoring.get("weights", {})) | set(scoring.get("tie_breakers", []))
    unknown |= {hf.get("metric") for hf in scoring.get("hard_filters", [])}
    unknown -= known
    unknown.discard(None)
    if unknown:
        raise ValidationFailed(
            f"Unknown metric name(s) in 'scoring': {', '.join(sorted(unknown))}.",
            detail={"allowed": sorted(known)},
        )

    weights = scoring.get("weights")
    if weights:
        # Cheap arithmetic on data the API already has (capabilities.metrics), not a
        # ScoringProfile construction — that stays engine-side (§3). Catches the case
        # engine.scoring.profiles.ScoringProfile.validate() would otherwise only find
        # once the run is already executing, turning it into a submission-time 422
        # instead of an async FAILED run.
        total = sum(weights.get(metric.name, metric.weight) for metric in capabilities.metrics)
        if total <= 0:
            raise ValidationFailed("'scoring.weights' leaves the total weight non-positive.")

    return scoring


def _estimate(
    input_mode: str, rows: int | None, constraints: dict, gate_families: list[str]
) -> dict:
    """Rough, and labelled as such (docs/public-api.md §9.3). ``de`` mode can only be
    bounded from the dataset's row count — gene selection (stage 1) doesn't exist yet,
    so how many genes actually survive filtering is unknown until it does."""
    n_families = max(1, len(gate_families))

    if input_mode == InputMode.DIRECT:
        n_lengths = max(1, len(constraints.get("trigger_lengths", (30, 36))))
        designs = n_lengths * n_families
        confidence = "very rough"
    else:
        max_triggers = int(constraints.get("max_triggers", 2))
        genes = min(rows, 200) if rows else 50
        trigger_sets = math.comb(genes, max_triggers) if genes >= max_triggers else genes
        designs = trigger_sets * _DESIGNS_PER_TRIGGER_SET * n_families
        confidence = "rough"

    return {
        "designs": designs,
        "seconds": round(designs * _SECONDS_PER_DESIGN, 1),
        "confidence": confidence,
    }


def _resolved(run: AnalysisRun) -> dict:
    return {
        "input_mode": run.input_mode,
        "gate_families": run.gate_families,
        # The label the engine actually scored under (X7) — not just the base name —
        # when a custom scoring block was submitted; otherwise identical to the base.
        "scoring_profile": label_for_custom_scoring(
            run.scoring_profile, run.params_snapshot.get("scoring")
        ),
        "seed": run.seed,
        "constraints": run.params_snapshot.get("constraints", {}),
    }


def _row_count_for_dry_run(request, body: DesignIn, input_mode: str) -> int | None:
    """Never persists — a dry run creates nothing (§9.3)."""
    if input_mode == InputMode.DIRECT:
        return None
    if body.dataset_id:
        dataset = get_owned(Dataset, body.dataset_id, request.user)
        return (dataset.validation_report or {}).get("rows")

    upload = SimpleUploadedFile("dge.csv", body.dge_csv.encode(), content_type="text/csv")
    try:
        report = validate_expression_file(upload)
    except DatasetValidationError as exc:
        raise ValidationFailed(str(exc)) from None
    return report.get("rows")


@router.post("/design", response={202: DesignAcceptedOut, 200: DesignResponseOut})
def create_design(request, body: DesignIn, wait: float = 0, dry_run: bool = False):
    """Submit, or estimate without submitting (``?dry_run=true``), or block for a
    finished result (``?wait=<seconds>``, ceiling 300s — see ``WAIT_HARD_CEILING``)."""
    require_scope(request, ApiKeyScope.DESIGN)

    capabilities = load_engine(settings.CERNAL_ENGINE).capabilities()
    input_mode = _input_mode(body)
    gate_families = _resolve_gate_families(body, capabilities)
    scoring = _resolve_scoring(body, capabilities)

    if body.strict:
        _check_known_keys(body.constraints, _CONSTRAINT_KEYS, "constraint")
        _check_known_keys(body.budget, _BUDGET_KEYS, "budget field")
        _check_known_keys(body.payload, _PAYLOAD_KEYS, "payload field")

    if dry_run:
        rows = _row_count_for_dry_run(request, body, input_mode)
        estimate = _estimate(input_mode, rows, body.constraints, gate_families)
        return Status(
            200,
            {
                "resolved": {
                    "input_mode": input_mode,
                    "gate_families": gate_families,
                    "scoring_profile": label_for_custom_scoring(
                        scoring.get("base", "default"), scoring
                    ),
                    "seed": body.seed,
                    "constraints": body.constraints,
                },
                "estimate": estimate,
                # No budget enforcement yet — engine-side work, blocked on the real
                # pipeline (docs/public-api.md §9.3, §14 X6). True until it lands.
                "budget_ok": True,
            },
        )

    enforce_concurrency_ceiling(request)

    dataset = None
    if body.dataset_id:
        dataset = get_owned(Dataset, body.dataset_id, request.user)
    elif body.dge_csv:
        try:
            dataset = create_dataset(
                uploaded_file=SimpleUploadedFile(
                    "dge.csv", body.dge_csv.encode(), content_type="text/csv"
                ),
                user=request.user,
                name="dge.csv (inline)",
            )
        except DatasetValidationError as exc:
            raise ValidationFailed(str(exc)) from None

    params = {
        "constraints": body.constraints,
        "scoring": scoring,
        "budget": body.budget,
        "payload": body.payload,
        "top_n": body.top_n,
        "notes": body.notes,
    }

    try:
        run, _created = submit_run(
            user=request.user,
            dataset=dataset,
            input_mode=input_mode,
            trigger_sequence=body.trigger_sequence,
            organism=body.organism,
            params=params,
            gate_families=gate_families,
            scoring_profile=scoring.get("base", "default"),
            seed=body.seed,
            idempotency_key=body.idempotency_key,
        )
    except RunError as exc:
        raise ValidationFailed(str(exc)) from None

    rows = (dataset.validation_report or {}).get("rows") if dataset else None
    estimate = _estimate(input_mode, rows, body.constraints, gate_families)

    wait = max(0.0, min(wait, WAIT_HARD_CEILING))
    if wait > 0:
        deadline = time.monotonic() + wait
        while True:
            run.refresh_from_db()
            if run.is_terminal:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.5, remaining))

        if run.status == RunStatus.COMPLETED:
            results = _results_payload(
                run,
                top_n=body.top_n,
                include_rejected=body.include_rejected,
                include_artifacts=body.include_artifacts,
            )
            return Status(200, {**results, "resolved": _resolved(run)})

    return Status(
        202,
        {
            "job_id": run.id,
            "status": run.status,
            "progress_pct": run.progress_pct,
            "poll_url": f"/api/design/{run.id}",
            "results_url": f"/api/design/{run.id}/results",
            "web_url": f"/runs/{run.id}",
            "estimate": estimate,
            "resolved": _resolved(run),
        },
    )


@router.get("/design/{run_id}", response=RunStatusOut)
def get_design_status(request, run_id: UUID):
    """Thin alias of ``GET /api/runs/{id}`` (§8) — the same cheap polling read."""
    run = get_owned(AnalysisRun, run_id, request.user)
    return RunStatusOut(
        id=run.id,
        status=run.status,
        stage=run.stage,
        progress_pct=run.progress_pct,
        error_summary=run.error_summary or None,
        warnings=run.warnings or [],
        submitted_at=run.submitted_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        counts=RunCounts(candidates=run.candidates.count(), artifacts=run.artifacts.count()),
    )


def _results_payload(
    run: AnalysisRun, *, top_n: int, include_rejected: bool, include_artifacts: list[str]
) -> dict:
    queryset = Candidate.objects.filter(run=run).prefetch_related("metrics")
    if not include_rejected:
        queryset = queryset.filter(is_rejected=False)
    queryset = queryset.order_by(F("rank").asc(nulls_last=True), "engine_ref")
    candidates = list(queryset[: max(1, top_n)])

    artifacts = []
    if include_artifacts:
        artifacts = list(Artifact.objects.filter(run=run, kind__in=include_artifacts))

    return {
        "job_id": run.id,
        "status": run.status,
        "candidates": candidates,
        "artifacts": artifacts,
    }


@router.get("/design/{run_id}/results", response=DesignResponseOut)
def get_design_results(
    request,
    run_id: UUID,
    format: str = "json",
    top_n: int = 25,
    include_rejected: bool = False,
    include_artifacts: str = "",
):
    """Ranked candidates with metric decomposition. ``?format=csv`` delegates to the
    same export the SPA and the old endpoint use — one code path (§8).
    ``include_artifacts`` is a comma-separated list of artifact kinds, e.g.
    ``fasta,structure_svg``."""
    run = get_owned(AnalysisRun, run_id, request.user)

    if format == "csv":
        from api.routers.results import export_candidates_csv

        return export_candidates_csv(request, run_id)

    kinds = [kind.strip() for kind in include_artifacts.split(",") if kind.strip()]
    results = _results_payload(
        run, top_n=top_n, include_rejected=include_rejected, include_artifacts=kinds
    )
    return {**results, "resolved": _resolved(run)}
