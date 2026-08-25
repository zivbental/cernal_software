"""The Platform-facing engine interface.

This module and ``engine.contract`` are the *only* things Platform code may import from
the engine (docs/software-design.md §3).

Failure convention
------------------
An expected scientific failure is **data**: the engine returns a ``JobResult`` with
``status="failed"`` and a safe ``error`` message. A programming error is an
**exception** and propagates, so the Platform logs a traceback and the bug is visible.
Cancellation returns ``status="cancelled"``.
"""

import importlib
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

from engine.artifacts import sha256_file, write_artifact
from engine.contract import (
    CANCELLED,
    FAILED,
    SCHEMA_VERSION,
    SUCCEEDED,
    ArtifactRef,
    CandidateResult,
    EngineCapabilities,
    JobRequest,
    JobResult,
)
from engine.errors import ChecksumMismatchError, EngineError, InputValidationError, JobCancelled
from engine.scoring.normalize import build_metrics, failed_filter, rank_candidates, weighted_score
from engine.scoring.profiles import get_profile

#: ``on_progress(percent, stage) -> keep_going``. Returning ``False`` cancels the run.
ProgressFn = Callable[[int, str], bool]


@runtime_checkable
class EngineClient(Protocol):
    """What the Platform depends on. Implementations must be safe to call from a worker."""

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        """Execute one job to completion, reporting progress as it goes."""
        ...

    def capabilities(self) -> EngineCapabilities:
        """What this engine supports. Cheap enough to call on every request."""
        ...


def load_engine(dotted_path: str) -> EngineClient:
    """Instantiate an engine client from a dotted path, e.g. ``engine.client.MockEngine``.

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


def _installed_capabilities(engine_version: str) -> EngineCapabilities:
    """Read the registries. Engine-internal, so importing them here is fine."""
    from engine.gates.registry import available_families
    from engine.scoring.profiles import available_profiles

    return EngineCapabilities(
        engine_version=engine_version,
        schema_version=SCHEMA_VERSION,
        gate_families=available_families(),
        scoring_profiles=available_profiles(),
    )


class LocalEngine:
    """Runs the real scientific pipeline in-process. Step 5."""

    ENGINE_VERSION = "local-0.1.0-stub"

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        from engine.pipeline import run_pipeline

        return run_pipeline(request, on_progress)

    def capabilities(self) -> EngineCapabilities:
        return _installed_capabilities(self.ENGINE_VERSION)


# --- Mock engine ------------------------------------------------------------------

_STAGES: list[tuple[int, str]] = [
    (5, "Validating scientific inputs"),
    (15, "Loading and preprocessing dataset"),
    (30, "Discovering candidate features"),
    (45, "Generating trigger combinations"),
    (60, "Generating gate designs"),
    (78, "Evaluating gate designs"),
    (90, "Scoring and ranking candidates"),
    (97, "Writing artifacts"),
]

#: A fixed pool so generated candidates look plausible and stay stable across runs.
_FEATURE_POOL = [
    "aceB",
    "araC",
    "cheY",
    "dnaK",
    "fliC",
    "gadA",
    "hns",
    "ifcA",
    "katG",
    "lacZ",
    "malE",
    "narG",
    "ompF",
    "phoA",
    "rpoS",
    "soxS",
    "tnaA",
    "uspA",
    "wrbA",
    "ybgS",
    "zwf",
]

_BASES = "ACGU"


class MockEngine:
    """Deterministic fake science.

    Seeded from ``idempotency_key`` (and ``seed`` when supplied), so the same submission
    always produces byte-identical candidates and artifacts. It exercises the real
    scoring code, writes real files, honours cancellation, and can be told to fail — so
    the Platform's success *and* failure paths are both testable before any scientific
    code exists.

    Options, under ``JobRequest.params["mock"]``:

    ``candidate_count``  how many candidates to generate (default 12)
    ``step_delay``       seconds to pause per stage, to make progress observable (0.0)
    ``fail``             raise a scientific failure, producing a ``failed`` result
    ``fail_message``     the ``error`` text for that failure
    ``fail_at_stage``    zero-based stage index to fail at (default: the last one)
    """

    ENGINE_VERSION = "mock-1.0.0"

    def capabilities(self) -> EngineCapabilities:
        return _installed_capabilities(self.ENGINE_VERSION)

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        try:
            return self._execute(request, on_progress)
        except JobCancelled:
            return self._terminal(request, CANCELLED, error=None)
        except EngineError as exc:
            return self._terminal(request, FAILED, error=str(exc))

    # -- internals --

    def _terminal(self, request: JobRequest, status: str, error: str | None) -> JobResult:
        return JobResult(
            schema_version=SCHEMA_VERSION,
            engine_version=self.ENGINE_VERSION,
            status=status,
            error=error,
            input_checksum=request.input_checksum,
            params=request.params,
        )

    def _execute(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        options = request.mock_options()
        delay = float(options.get("step_delay", 0.0))
        fail_at = options.get("fail_at_stage", len(_STAGES) - 1)

        profile = get_profile(request.scoring_profile)
        rng = self._rng(request)

        for index, (percent, label) in enumerate(_STAGES):
            if not on_progress(percent, label):
                raise JobCancelled(label)
            if delay:
                time.sleep(delay)
            if index == 0:
                self._verify_input(request)
            if options.get("fail") and index == fail_at:
                raise InputValidationError(
                    options.get("fail_message", "Simulated engine failure (MockEngine).")
                )

        candidates = self._build_candidates(request, profile, rng, options)
        artifacts = self._write_artifacts(request, candidates)

        return JobResult(
            schema_version=SCHEMA_VERSION,
            engine_version=self.ENGINE_VERSION,
            status=SUCCEEDED,
            candidates=candidates,
            artifacts=artifacts,
            warnings=[
                "Results produced by MockEngine — these are not real scientific predictions."
            ],
            error=None,
            input_checksum=request.input_checksum,
            params=request.params,
        )

    @staticmethod
    def _rng(request: JobRequest) -> random.Random:
        """Deterministic per submission. Same key and seed → same stream."""
        return random.Random(f"{request.idempotency_key}:{request.seed}")

    @staticmethod
    def _verify_input(request: JobRequest) -> None:
        """Exercise the same checksum path a real engine would."""
        path = Path(request.input_path)
        if not path.is_file():
            raise InputValidationError("The submitted dataset could not be read.")
        if request.input_checksum and sha256_file(path) != request.input_checksum:
            raise ChecksumMismatchError(
                "The dataset does not match the checksum recorded at submission."
            )

    def _build_candidates(self, request, profile, rng, options) -> list[CandidateResult]:
        count = int(options.get("candidate_count", 12))
        families = request.gate_families or ["toehold"]
        max_triggers = int(request.params.get("max_triggers", 2))

        drafts: list[tuple[CandidateResult, dict]] = []

        for index in range(count):
            ref = f"cand-{index + 1:03d}"
            arity = rng.choice([1] * 3 + [2] * 2) if max_triggers > 1 else 1
            features = rng.sample(_FEATURE_POOL, arity)
            family = rng.choice(families)

            triggers = {
                "features": [
                    {
                        "feature_id": name,
                        "base_expression": round(rng.uniform(0.1, 3.0), 3),
                        "target_expression": round(rng.uniform(2.0, 9.0), 3),
                        "sequence": self._sequence(rng, 36),
                    }
                    for name in features
                ]
            }
            design = {
                "switch_sequence": self._sequence(rng, 92),
                "structure": self._structure(rng, 92),
                "toehold_length": rng.randint(12, 18),
                "logic_graph": {
                    "inputs": features,
                    "operator": "AND" if arity > 1 else "IDENTITY",
                    "output": "GFP",
                },
            }

            raw = {
                "state_separation": round(rng.uniform(0.0, 9.5), 3),
                "trigger_accessibility": round(rng.uniform(0.15, 0.98), 3),
                "gate_folding_energy": round(rng.uniform(-52.0, -8.0), 2),
                "predicted_leakage": round(rng.uniform(0.02, 0.95), 3),
                "orthogonality": round(rng.uniform(0.3, 0.99), 3),
                "circuit_complexity": float(arity * 2 + rng.randint(0, 3)),
            }

            logic_type = {1: "single-input", 2: "AND"}.get(arity, f"AND{arity}")
            metrics = build_metrics(raw, profile)
            breach = failed_filter(raw, profile)

            drafts.append(
                (
                    CandidateResult(
                        ref=ref,
                        rank=None,
                        overall_score=None if breach else weighted_score(metrics, profile),
                        gate_family=family,
                        logic_type=logic_type,
                        triggers=triggers,
                        design=design,
                        summary=f"{logic_type} {family} gate on {', '.join(features)}",
                        metrics=metrics,
                        warnings=(
                            ["Low orthogonality may cause cross-talk."]
                            if raw["orthogonality"] < 0.45
                            else []
                        ),
                        is_rejected=breach is not None,
                        rejection_reason=breach.reason if breach else "",
                    ),
                    raw,
                )
            )

        ranks = rank_candidates([(c.ref, c.overall_score) for c, _ in drafts if not c.is_rejected])

        from dataclasses import replace

        return [replace(c, rank=ranks.get(c.ref)) for c, _ in drafts]

    def _write_artifacts(
        self, request: JobRequest, candidates: list[CandidateResult]
    ) -> list[ArtifactRef]:
        output_dir = request.output_dir
        artifacts: list[ArtifactRef] = []

        header = "ref,rank,gate_family,logic_type,overall_score,rejected,rejection_reason"
        rows = [header]
        for candidate in sorted(candidates, key=lambda c: c.ref):
            score = "" if candidate.overall_score is None else f"{candidate.overall_score:.4f}"
            rows.append(
                ",".join(
                    [
                        candidate.ref,
                        "" if candidate.rank is None else str(candidate.rank),
                        candidate.gate_family,
                        candidate.logic_type,
                        score,
                        "yes" if candidate.is_rejected else "no",
                        f'"{candidate.rejection_reason}"',
                    ]
                )
            )
        artifacts.append(
            write_artifact(
                output_dir,
                "candidates.csv",
                "\n".join(rows) + "\n",
                kind="design_table",
                media_type="text/csv",
            )
        )

        for candidate in sorted((c for c in candidates if not c.is_rejected), key=lambda c: c.ref):
            fasta = (
                f">{candidate.ref} {candidate.gate_family} {candidate.logic_type} "
                f"rank={candidate.rank}\n{candidate.design['switch_sequence']}\n"
            )
            artifacts.append(
                write_artifact(
                    output_dir,
                    f"sequences/{candidate.ref}.fasta",
                    fasta,
                    kind="sequence_fasta",
                    media_type="text/x-fasta",
                    candidate_ref=candidate.ref,
                )
            )

        return artifacts

    @staticmethod
    def _sequence(rng: random.Random, length: int) -> str:
        return "".join(rng.choice(_BASES) for _ in range(length))

    @staticmethod
    def _structure(rng: random.Random, length: int) -> str:
        stem = min(length // 4, 20)
        loop = length - 2 * stem
        return "(" * stem + "." * loop + ")" * stem
