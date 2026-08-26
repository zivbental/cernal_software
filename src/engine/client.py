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
    from engine.gates.registry import describe_families
    from engine.scoring.profiles import available_profiles

    return EngineCapabilities(
        engine_version=engine_version,
        schema_version=SCHEMA_VERSION,
        gate_families=describe_families(),
        scoring_profiles=available_profiles(),
    )


class LocalEngine:
    """Runs the real scientific pipeline in-process. Step 5."""

    ENGINE_VERSION = "local-0.1.0-stub"

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        """Delegate to the real pipeline.

        Imported lazily so that constructing a ``LocalEngine`` — which the Platform does
        just to read capabilities — does not import numpy, pandas and ViennaRNA.
        """
        from engine.pipeline import run_pipeline

        return run_pipeline(request, on_progress)

    def capabilities(self) -> EngineCapabilities:
        """The families and profiles actually installed in this build."""
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

#: Downstream outputs, all equivalent. A run produces candidates for each one selected.
_OUTPUT_NAMES = {
    "gfp": "GFP",
    "mcherry": "mCherry",
    "luciferase": "Luciferase",
    "ampr": "AmpR",
    "apoptosis": "Apoptosis inducer",
}


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
        """The same registries the real engine reports, so a mock run configures
        identically to a real one."""
        return _installed_capabilities(self.ENGINE_VERSION)

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        """Run a fake job, deterministically.

        Converts ``JobCancelled`` and ``EngineError`` into terminal results exactly as a
        real engine must — so the Platform's failure and cancellation paths are exercised
        long before any science exists.
        """
        try:
            return self._execute(request, on_progress)
        except JobCancelled:
            return self._terminal(request, CANCELLED, error=None)
        except EngineError as exc:
            return self._terminal(request, FAILED, error=str(exc))

    # -- internals --

    def _terminal(self, request: JobRequest, status: str, error: str | None) -> JobResult:
        """Build a result carrying no candidates: cancelled, or failed."""
        return JobResult(
            schema_version=SCHEMA_VERSION,
            engine_version=self.ENGINE_VERSION,
            status=status,
            error=error,
            input_checksum=request.input_checksum,
            params=request.params,
        )

    def _execute(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        """Walk the fake stages, honouring cancellation and injected failure.

        Verifies the input checksum on the first stage exactly as a real engine would, so
        the Platform's checksum handling is exercised too.
        """
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
        """Exercise the same input checks a real engine would."""
        if request.is_direct_trigger:
            sequence = request.trigger_sequence.strip().upper()
            if len(sequence) < 20:
                raise InputValidationError(
                    "The trigger sequence is too short to design a switch against "
                    "(at least 20 nucleotides are needed)."
                )
            if set(sequence) - set("ACGU"):
                raise InputValidationError(
                    "The trigger sequence contains characters other than A, C, G and U."
                )
            return

        path = Path(request.input_path)
        if not path.is_file():
            raise InputValidationError("The submitted dataset could not be read.")
        if request.input_checksum and sha256_file(path) != request.input_checksum:
            raise ChecksumMismatchError(
                "The dataset does not match the checksum recorded at submission."
            )

    def _build_candidates(self, request, profile, rng, options) -> list[CandidateResult]:
        """Generate candidates from the seeded RNG, scored through the **real** scoring
        layer.

        Using ``engine.scoring`` rather than inventing numbers is what makes the mock
        representative: the metric decomposition, hard filters and ranking are the same
        code a real run uses.
        """
        count = int(options.get("candidate_count", 12))
        families = request.gate_families or ["toehold"]
        outputs = self._requested_outputs(request)
        max_triggers = int(request.params.get("max_triggers", 2))

        drafts: list[tuple[CandidateResult, dict]] = []

        for index in range(count):
            ref = f"cand-{index + 1:03d}"
            arity = rng.choice([1] * 3 + [2] * 2) if max_triggers > 1 else 1
            pool = rng.sample(_FEATURE_POOL, arity + 1)
            features, repressor = pool[:arity], pool[arity]
            # Roughly half the circuits gate on a transcript that must be absent.
            if rng.random() < 0.5:
                repressor = None
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
            # Round-robin, so every selected output gets a comparable share of the
            # candidate budget rather than one output dominating by chance.
            payload_name = outputs[index % len(outputs)]
            segments = self._plasmid_segments(rng, payload_name)
            design = {
                "switch_sequence": self._sequence(rng, 92),
                "structure": self._structure(rng, 92),
                "toehold_length": rng.randint(12, 18),
                "sequence_length_bp": sum(seg["length_bp"] for seg in segments),
                "plasmid_segments": segments,
                "logic_graph": self._logic_graph(features, repressor, payload_name),
            }

            raw = {
                "state_separation": round(rng.uniform(0.0, 9.5), 3),
                "trigger_accessibility": round(rng.uniform(0.15, 0.98), 3),
                "gate_folding_energy": round(rng.uniform(-52.0, -8.0), 2),
                "predicted_leakage": round(rng.uniform(0.02, 0.95), 3),
                "orthogonality": round(rng.uniform(0.3, 0.99), 3),
                "gc_content": round(rng.uniform(38.0, 62.0), 1),
                "dynamic_range": round(rng.uniform(8.0, 460.0), 1),
                "predicted_success_rate": round(rng.uniform(0.45, 0.97), 3),
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
        """Write real files: a design table, and a FASTA per accepted candidate.

        Real files rather than stubs, so the Platform's artifact import, checksum
        verification and download paths are exercised end to end.
        """
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
    def _requested_outputs(request: JobRequest) -> list[str]:
        """Every downstream output the researcher selected, in display form.

        All outputs are equivalent: each one gets its own set of candidate plasmids,
        because a construct expressing GFP is a different construct from one expressing
        an antibiotic resistance marker.
        """
        payload = request.params.get("payload") or {}
        selected = payload.get("outputs") or []

        names = [_OUTPUT_NAMES.get(key, str(key)) for key in selected if key != "other"]
        if "other" in selected and payload.get("custom_sequence"):
            names.append("Custom")

        return names or ["GFP"]

    @staticmethod
    def _plasmid_segments(rng: random.Random, payload: str) -> list[dict]:
        """The construct laid out end to end. Drives the plasmid map.

        ``kind`` is a stable vocabulary; colours belong to the frontend, not here.
        """
        return [
            {"kind": "promoter", "name": "J23119", "length_bp": rng.randint(30, 60)},
            {"kind": "switch", "name": "toehold_switch", "length_bp": rng.randint(90, 160)},
            {"kind": "payload", "name": payload, "length_bp": rng.randint(600, 1800)},
            {"kind": "terminator", "name": "B0015", "length_bp": rng.randint(100, 160)},
            {"kind": "backbone", "name": "pUC ori", "length_bp": rng.randint(900, 1500)},
        ]

    @staticmethod
    def _logic_graph(features: list[str], repressor: str | None, payload: str) -> dict:
        """The Boolean circuit, as the researcher reads it.

        Letters (A, B, C...) label the genes in the caption so it stays readable
        regardless of how long the real feature names are.
        """
        letters = "ABCDEF"
        genes = [
            {
                "name": letters[index],
                "role": feature,
                "state": "ON",
                "direction": "up",
            }
            for index, feature in enumerate(features)
        ]
        if repressor is not None:
            genes.append(
                {
                    "name": letters[len(features)],
                    "role": repressor,
                    "state": "OFF",
                    "direction": "down",
                }
            )

        activators = [gene["name"] for gene in genes if gene["state"] == "ON"]
        mid_gate = "AND"
        outer_gate = "AND"
        expression = (
            activators[0] if len(activators) == 1 else f"({f' {mid_gate} '.join(activators)})"
        )
        if repressor is not None:
            expression = f"{expression} {outer_gate} NOT {genes[-1]['name']}"

        return {
            "genes": genes,
            "mid_gate": mid_gate,
            "outer_gate": outer_gate,
            "invert": repressor is not None,
            "output": payload,
            "caption": f"IF {expression} → EXPRESS {payload}",
        }

    @staticmethod
    def _sequence(rng: random.Random, length: int) -> str:
        """A plausible-looking RNA sequence. Deterministic for a given RNG state."""
        return "".join(rng.choice(_BASES) for _ in range(length))

    @staticmethod
    def _structure(rng: random.Random, length: int) -> str:
        """A hairpin in dot-bracket notation, so structure-rendering code has real input."""
        stem = min(length // 4, 20)
        loop = length - 2 * stem
        return "(" * stem + "." * loop + ")" * stem
