"""Validation for the ``params`` sub-blocks both submission endpoints accept.

``engine.domain.Constraints`` and ``engine.scoring.profiles`` are the source of truth
for these key sets; ``api/`` may not import ``engine.domain`` directly
(architecture.md §3), so the key sets are mirrored here — the same reason
``DesignIn``'s docstring gives for ``constraints``/``scoring`` being plain dicts
rather than nested schemas.

Shared by ``POST /api/design`` (``routers/design.py``, always strict) and
``POST /api/runs`` (``routers/runs.py``, which validates these two sub-blocks
unconditionally while leaving every other ``params`` key free-form) — one place to
keep both endpoints' idea of "a known constraint field" or "a known metric name" in
sync, rather than two copies drifting apart.
"""

import difflib

from api.errors import ApiError, ValidationFailed

CONSTRAINT_KEYS = {
    "max_triggers",
    "min_separation",
    "max_p_adj",
    "trigger_lengths",
    "max_switch_length",
    "forbidden_motifs",
    "standard",
}
SCORING_KEYS = {"base", "weights", "hard_filters", "tie_breakers"}
BUDGET_KEYS = {"max_designs", "max_runtime_seconds", "on_exceed"}
PAYLOAD_KEYS = {"outputs", "custom_sequence"}
BACKBONE_KEYS = {"catalog_key", "custom_genbank"}


class UnknownParameter(ApiError):
    status = 422
    code = "unknown_parameter"


def check_known_keys(block: dict, allowed: set[str], name: str) -> None:
    """A typo becomes a 422 naming the mistake, instead of the silent CLAUDE.md §2
    failure — an unknown key is simply never read."""
    unknown = sorted(set(block) - allowed)
    if not unknown:
        return
    bad = unknown[0]
    suggestion = difflib.get_close_matches(bad, allowed, n=1)
    raise UnknownParameter(
        f"Unknown {name} '{bad}'.",
        detail={"did_you_mean": suggestion[0] if suggestion else None, "allowed": sorted(allowed)},
    )


def check_scoring_block(scoring: dict, capabilities) -> None:
    """Every metric name referenced in ``weights``/``hard_filters``/``tie_breakers``
    must be one ``ScoringProfile`` actually knows, and the total weight must stay
    positive — the submission-time version of checks
    ``engine.scoring.profiles.ScoringProfile.validate()`` would otherwise only run once
    the run is already executing, turning a typo into an async FAILED run instead of an
    immediate 422 (CLAUDE.md §2)."""
    known = {metric.name for metric in capabilities.metrics}
    hard_filters = scoring.get("hard_filters", [])
    unknown = set(scoring.get("weights", {})) | set(scoring.get("tie_breakers", []))
    unknown |= {hf.get("metric") for hf in hard_filters}
    unknown -= known
    unknown.discard(None)
    if unknown:
        raise ValidationFailed(
            f"Unknown metric name(s) in 'scoring': {', '.join(sorted(unknown))}.",
            detail={"allowed": sorted(known)},
        )

    # engine.scoring.profiles.derive_profile defaults a missing "reason" to "" rather
    # than requiring one, and Candidate has a DB constraint that a rejected row must
    # carry a non-empty rejection_reason — so a caller-supplied hard filter with no
    # reason does not fail here or there, it fails as an IntegrityError the first time
    # the filter actually rejects a real candidate, deep inside the worker. Catching it
    # at submission is the only place a clean message is possible.
    reasonless = [hf["metric"] for hf in hard_filters if not hf.get("reason")]
    if reasonless:
        raise ValidationFailed(
            f"'scoring.hard_filters' entries for {', '.join(sorted(reasonless))} need a "
            "non-empty 'reason' — it becomes the rejected candidate's recorded reason."
        )

    weights = scoring.get("weights")
    if weights:
        total = sum(weights.get(metric.name, metric.weight) for metric in capabilities.metrics)
        if total <= 0:
            raise ValidationFailed("'scoring.weights' leaves the total weight non-positive.")


def check_backbone_block(backbone: dict, capabilities) -> None:
    """Exactly one of ``catalog_key`` / ``custom_genbank``, and ``catalog_key`` must be
    one the engine actually advertises — the submission-time version of the check
    ``engine.pipeline._resolve_backbone`` would otherwise only run once the run is
    already executing (CLAUDE.md §2, docs/plasmids.md Q13).

    ``custom_genbank`` is not validated here beyond presence — parsing it is real work
    (:func:`engine.stages.plasmids.parse_custom_backbone`) that stays engine-side, the
    same boundary ``_resolve_scoring`` already draws for ``ScoringProfile`` construction.
    """
    catalog_key = backbone.get("catalog_key")
    custom_genbank = backbone.get("custom_genbank")
    if catalog_key and custom_genbank:
        raise ValidationFailed(
            "Provide at most one of 'backbone.catalog_key' or 'backbone.custom_genbank', not both."
        )
    if catalog_key:
        known = {b.key for b in capabilities.available_backbones}
        if catalog_key not in known:
            raise ValidationFailed(
                f"Unknown backbone 'catalog_key' {catalog_key!r}.",
                detail={"allowed": sorted(known)},
            )
