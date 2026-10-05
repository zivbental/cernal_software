"""The Platform-facing engine interface.

This module and ``engine.contract`` are the *only* things Platform code may import from
the engine (docs/architecture.md §3).

Failure convention
------------------
An expected scientific failure is **data**: the engine returns a ``JobResult`` with
``status="failed"`` and a safe ``error`` message. A programming error is an
**exception** and propagates, so the Platform logs a traceback and the bug is visible.
Cancellation returns ``status="cancelled"``.
"""

import dataclasses
import importlib
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from engine.contract import (
    CANCELLED,
    FAILED,
    SCHEMA_VERSION,
    BackboneInfo,
    EngineCapabilities,
    JobRequest,
    JobResult,
    MetricInfo,
)
from engine.errors import EngineError, JobCancelled

#: ``on_progress(percent, stage) -> keep_going``. Returning ``False`` cancels the run.
ProgressFn = Callable[[int, str], bool]


@runtime_checkable
class EngineClient(Protocol):
    """What the Platform depends on. Implementations must be safe to call from a worker."""

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        """Execute one job to completion, reporting progress as it goes.

        Args:
            request: The immutable submission.
            on_progress: Called between stages with ``(percent, stage_label)``. Returning
                ``False`` cancels — cooperatively, never by killing anything.

        Returns:
            A ``JobResult``. An expected scientific failure is **data**, returned with
            ``status="failed"``; a programming error is an **exception** and propagates,
            so the Platform logs a traceback and the bug is visible.
        """
        ...

    def capabilities(self) -> EngineCapabilities:
        """What this engine supports.

        Called on every ``GET /api/version``, so it must not fold anything or read a
        transcriptome — it reads the registries and returns.
        """
        ...


def load_engine(dotted_path: str) -> EngineClient:
    """Instantiate an engine client from a dotted path, e.g. ``engine.client.LocalEngine``.

    Takes the path as an argument rather than reading ``settings.CERNAL_ENGINE`` itself:
    this module must not import Django (§3). The Platform passes the setting in.
    """
    module_name, _, class_name = dotted_path.rpartition(".")
    if not module_name:
        raise ValueError(f"CERNAL_ENGINE must be a dotted path, got {dotted_path!r}.")

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError(f"Cannot import engine module '{module_name}': {exc}") from exc

    try:
        engine_class = getattr(module, class_name)
    except AttributeError:
        raise ValueError(f"Module '{module_name}' has no attribute '{class_name}'.") from None

    # Checked before instantiating: a misconfigured CERNAL_ENGINE should produce a clear
    # message, not a side effect and an obscure TypeError.
    if not isinstance(engine_class, type) or not all(
        callable(getattr(engine_class, name, None)) for name in ("run", "capabilities")
    ):
        raise TypeError(f"{dotted_path} does not implement EngineClient.")

    instance = engine_class()
    if not isinstance(instance, EngineClient):
        raise TypeError(f"{dotted_path} does not implement EngineClient.run().")
    return instance


def label_for_custom_scoring(base_name: str, overrides: dict | None) -> str:
    """The label the engine will actually score under (docs/public-api.md §9.1) —
    computable from the request alone, before the engine ever runs, so the Platform can
    echo it in a submission's ``resolved`` field without building a ``ScoringProfile``
    itself (§3's boundary: that stays in ``engine.scoring``, imported only here).
    """
    from engine.scoring.profiles import custom_scoring_label

    if not overrides:
        return base_name

    weights = overrides.get("weights") or {}
    hard_filters = overrides.get("hard_filters") or []
    tie_breakers = overrides.get("tie_breakers") or []
    if not (weights or hard_filters or tie_breakers):
        return base_name

    return f"custom-{custom_scoring_label(base_name, weights, hard_filters, tie_breakers)}"


def _installed_capabilities(engine_version: str) -> EngineCapabilities:
    """Read the registries. Engine-internal, so importing them here is fine."""
    from engine.gates.registry import describe_families
    from engine.scoring.profiles import DEFAULT_V1, available_profiles
    from engine.stages.plasmids import BACKBONES

    return EngineCapabilities(
        engine_version=engine_version,
        schema_version=SCHEMA_VERSION,
        gate_families=describe_families(),
        scoring_profiles=available_profiles(),
        # The vocabulary a caller may name in a custom `scoring` block (docs/public-api.md
        # §7, §9.1) — what makes an unknown or misspelled metric name a 422 instead of a
        # silently-worst-scored candidate (CLAUDE.md §2).
        metrics=[
            MetricInfo(
                name=spec.name,
                direction=spec.direction,
                weight=spec.weight,
                valid_range=spec.valid_range,
                unit=spec.unit,
                description=spec.description,
            )
            for spec in DEFAULT_V1.metrics
        ],
        hard_filters=[
            {
                "metric": hard_filter.metric,
                "minimum": hard_filter.minimum,
                "maximum": hard_filter.maximum,
                "reason": hard_filter.reason,
            }
            for hard_filter in DEFAULT_V1.hard_filters
        ],
        # Real backbone vectors PlasmidBuilder can assemble onto (docs/plasmids.md
        # Q13, docs/ROADMAP.md E5b) — what lets the wizard render real names and the
        # API reject an unknown catalog_key at submit time, the same reason
        # gate_families/metrics are advertised rather than hardcoded twice.
        available_backbones=[
            BackboneInfo(key=key, name=name, length_bp=len(sequence))
            for key, (name, sequence) in sorted(BACKBONES.items())
        ],
    )


class LocalEngine:
    """Runs the real scientific pipeline in-process.

    **Partial, honestly.** The ``direct`` input path is real end to end — a pasted
    trigger sequence through toehold design, evaluation and scoring, with real
    ViennaRNA folding throughout. ``de`` submissions now run too, for *E. coli* and
    yeast — the two hosts with a bundled reference transcriptome
    (``engine.transcriptome.available_hosts()``, docs/ROADMAP.md Q1) — and only as
    single-gene circuits: ``GeneSelector`` real, real transcripts scanned by the same
    ``TriggerScorer`` the `direct` path uses, but no ``CircuitDesigner`` (no multi-gene
    Boolean circuits yet), no real off-target scanning, no ``InputQualityCheck`` (there
    is no count matrix in this product to check), no bundled yeast plasmid backbone
    (a lab's own upload, or no backbone at all). Human has no bundled transcriptome
    and no promoter/terminator either. See docs/genes.md and this module's own
    ``pipeline.py`` docstring for exactly what that does and does not cover.
    ``ENGINE_VERSION`` says so directly rather than claiming more than this build does.
    """

    ENGINE_VERSION = "local-0.5.0-direct-and-de-ecoli-yeast"

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        """Delegate to the real pipeline.

        Imported lazily so that constructing a ``LocalEngine`` — which the Platform does
        just to read capabilities — does not import numpy, pandas and ViennaRNA.

        Converts ``JobCancelled``/``EngineError`` into a terminal ``JobResult`` exactly
        — an expected scientific failure is data, not a
        crash (this module's own docstring) — and stamps ``ENGINE_VERSION`` onto
        whatever ``run_pipeline`` returns, so that string has exactly one source of
        truth rather than being duplicated into ``engine/pipeline.py`` as well.
        """
        from engine.pipeline import run_pipeline

        try:
            result = run_pipeline(request, on_progress)
        except JobCancelled:
            return self._terminal(request, CANCELLED, error=None)
        except EngineError as exc:
            return self._terminal(request, FAILED, error=str(exc))

        return dataclasses.replace(result, engine_version=self.ENGINE_VERSION)

    def _terminal(self, request: JobRequest, status: str, error: str | None) -> JobResult:
        return JobResult(
            schema_version=SCHEMA_VERSION,
            engine_version=self.ENGINE_VERSION,
            status=status,
            error=error,
            input_checksum=request.input_checksum,
            params=request.params,
        )

    def capabilities(self) -> EngineCapabilities:
        """The families and profiles actually installed in this build."""
        return _installed_capabilities(self.ENGINE_VERSION)
