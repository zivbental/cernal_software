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

import copy
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


def lookup_reference_gene(organism: str, identifier: str) -> dict:
    """Resolve a public reference gene without exposing engine internals to the API."""
    from engine.domain import Host
    from engine.errors import EngineError
    from engine.transcriptome import gene_reference

    try:
        host = Host(organism)
        return gene_reference(host, identifier)
    except (ValueError, EngineError) as exc:
        raise ValueError(str(exc)) from exc


def layout_stored_structure(
    sequence: object, structure: object, *, structure_kind: object = None
) -> dict:
    """Return drawing data for a stored primary switch, never a new scientific result.

    Unknown provenance stays unknown. Missing historical data is unavailable; malformed
    stored data is invalid. Known layout failures are safe data, while programming
    errors still propagate. No engine/tool instance or scientific computation is created.
    """
    from engine.errors import StructureLayoutUnavailable

    result = {
        "status": "unavailable",
        "reason": None,
        "sequence": sequence if isinstance(sequence, str) else "",
        "structure": structure if isinstance(structure, str) else "",
        "structure_kind": structure_kind if isinstance(structure_kind, str) else None,
        "bases": [],
        "links": [],
        "renderer": "cernal-rnaviz",
        "renderer_version": "aa112e17a76941233987bb4287c2c66511c40d13",
    }
    if any(value is not None and not isinstance(value, str) for value in (sequence, structure)):
        result.update(status="invalid", reason="Stored sequence and structure must be text.")
        return result
    if not sequence or not structure:
        result["reason"] = "This candidate has no stored sequence and structure to display."
        return result
    from engine.gates.tools.folding import FoldEngine

    try:
        bases, links = FoldEngine.structure_layout(sequence, structure)
    except StructureLayoutUnavailable as exc:
        result["reason"] = str(exc)
    except ValueError as exc:
        result.update(status="invalid", reason=str(exc))
    except EngineError as exc:
        result.update(status="error", reason=str(exc))
    else:
        result.update(
            status="available",
            bases=[base.to_dict() for base in bases],
            links=[link.to_dict() for link in links],
        )
    return result


def normalize_trigger_sequence(sequence: str) -> str:
    """Normalize one RNA/DNA sequence or one FASTA record without changing symbols."""
    from engine import sequences

    if not isinstance(sequence, str):
        raise ValueError("Trigger sequence must be text.")
    lines = sequence.strip().splitlines()
    headers = [index for index, line in enumerate(lines) if line.lstrip().startswith(">")]
    if headers:
        if headers != [0] or not lines[0].lstrip()[1:].strip():
            raise ValueError("Provide one FASTA record with one nonempty header.")
        lines = lines[1:]
    normalized = sequences.to_rna("".join("".join(lines).split()))
    if not normalized or not sequences.is_valid_rna(normalized):
        raise ValueError(
            "Trigger sequence must contain only A/C/G/T/U; ambiguous symbols are unsupported."
        )
    return normalized


def inspect_expression_input(path: str, limit: int | None = 100) -> dict:
    """Shared upload and preview interpretation, exposed through the engine boundary."""
    from pathlib import Path

    from engine.inputs import parse_dge_table

    source = Path(path)
    try:
        table = parse_dge_table(source.read_bytes(), source.name)
    except (OSError, EngineError) as exc:
        return {
            "valid": False,
            "errors": [str(exc)],
            "warnings": [],
            "columns": [],
            "row_count": 0,
            "preview": [],
            "selected_sheet": 0 if source.suffix.lower() == ".xlsx" else None,
        }

    fields = {
        "gene_symbol": "symbol",
        "log2fc": "log2_fold_change",
        "padj": "p_adj",
        "pvalue": "p_value",
        "base_expression": "control_mean",
        "target_expression": "target_mean",
    }
    columns = (
        [key for key in table.columns if key in dataclasses.asdict(table.rows[0]) or key in fields]
        if table.rows
        else list(table.columns)
    )
    return {
        "valid": bool(table.rows),
        "errors": [] if table.rows else ["No usable effect-size rows were found."],
        "warnings": [
            "Tested hypothesis universe is unspecified; raw p-values do not establish FDR control."
        ],
        "columns": columns,
        "detected_columns": dict(table.detected_columns),
        "row_count": table.source_row_count,
        "preview": [
            {key: getattr(row, fields.get(key, key)) for key in columns}
            for row in table.rows[:limit]
        ],
        "selected_sheet": 0 if source.suffix.lower() == ".xlsx" else None,
    }


def validate_job_configuration(
    params: dict,
    gate_families: list[str],
    scoring_profile: str,
    input_mode: str,
    trigger_sequence: str = "",
    organism: str = "",
) -> dict:
    """Validate a runnable configuration before queueing; return normalized parameters."""
    from engine.domain import Host
    from engine.gates.registry import get_family
    from engine.pipeline import (
        _UNBUILDABLE_FAMILIES,
        _build_constraints,
        _resolve_backbone,
        _resolve_outputs,
    )
    from engine.scoring.profiles import resolve_profile
    from engine.stages.plasmids import validate_backbone_insertion

    if not isinstance(params, dict):
        raise ValueError("params must be an object.")
    if "scientific_provenance" in params:
        raise ValueError("scientific_provenance is engine-generated metadata, not a parameter.")
    if input_mode not in ("direct", "de", "gene"):
        raise ValueError("input_mode must be direct, de, or gene.")
    for block in ("constraints", "payload", "backbone", "scoring", "statistics", "target_gene"):
        if block in params and not isinstance(params[block], dict):
            raise ValueError(f"params.{block} must be an object.")
    budget = params.get("budget", {})
    if not isinstance(budget, dict) or set(budget) - {"max_designs"}:
        raise ValueError("budget supports only max_designs (integer 1..1000).")
    max_designs = budget.get("max_designs", 20)
    if (
        isinstance(max_designs, bool)
        or not isinstance(max_designs, int)
        or not 1 <= max_designs <= 1000
    ):
        raise ValueError("budget.max_designs must be an integer between 1 and 1000.")
    selections = [organism, *(params[key] for key in ("host", "organism") if key in params)]
    if any(not isinstance(value, str) for value in selections):
        raise ValueError("organism/host selections must be strings.")
    if not isinstance(gate_families, list) or any(
        not isinstance(name, str) for name in gate_families
    ):
        raise ValueError("gate_families must be a list of family names.")
    host_values = [value for value in selections if value]
    if len(set(host_values)) > 1:
        raise ValueError("Conflicting organism/host selections are not allowed.")
    payload = params.get("payload") or {}
    if "outputs" in payload and (
        not isinstance(payload["outputs"], list)
        or not payload["outputs"]
        or any(not isinstance(item, str) for item in payload["outputs"])
        or len(set(payload["outputs"])) != len(payload["outputs"])
    ):
        raise ValueError("payload.outputs must be a nonempty list of unique output identifiers.")
    if "optimize_codons" in payload and not isinstance(payload["optimize_codons"], bool):
        raise ValueError("payload.optimize_codons must be a boolean.")
    statistics = params.get("statistics") or {}
    if "hypothesis_universe_complete" in statistics and not isinstance(
        statistics["hypothesis_universe_complete"], bool
    ):
        raise ValueError("statistics.hypothesis_universe_complete must be a boolean.")
    try:
        try:
            host = Host(next(iter(host_values), "ecoli"))
        except ValueError as exc:
            raise ValueError(f"Unknown organism: {next(iter(host_values), 'ecoli')!r}.") from exc
        effective = params
        if host is Host.HUMAN and "standard" not in (params.get("constraints") or {}):
            effective = {
                **params,
                "constraints": {**(params.get("constraints") or {}), "standard": "none"},
            }
        constraints = _build_constraints(effective)
        if constraints.max_circuit_gates > 1 or constraints.max_triggers > 1:
            raise ValueError(
                "Unsupported physical circuit: production supports one input and one gate."
            )
        resolve_profile(scoring_profile, params.get("scoring"))
        families = gate_families or ["toehold"]
        for name in families:
            family = get_family(name)
            if (
                name in _UNBUILDABLE_FAMILIES
                or not family.available
                or host not in family.supported_hosts
            ):
                raise ValueError(
                    f"Gate family {name!r} is not production supported for {host.value}."
                )
        outputs, warnings = _resolve_outputs(params, host)
        if warnings or not outputs:
            raise ValueError("; ".join(warnings) or "No supported output requested.")
        backbone_segments = _resolve_backbone(params)
        insertion = (params.get("backbone") or {}).get("insertion_index", 0)
        if (
            isinstance(insertion, bool)
            or not isinstance(insertion, int)
            or not 0 <= insertion <= sum(segment.length_bp for segment in backbone_segments)
        ):
            raise ValueError(
                "backbone.insertion_index must be a 0-based boundary within the vector."
            )
        validate_backbone_insertion(backbone_segments, insertion)
        if host is not Host.ECOLI and (params.get("backbone") or {}).get("catalog_key"):
            raise ValueError(
                "Catalog vectors are currently supported only for E. coli; provide an explicit "
                "custom vector/cassette for mammalian, yeast or C. acnes context."
            )
        if input_mode == "direct":
            normalized = normalize_trigger_sequence(trigger_sequence)
            if len(normalized) > 10_000:
                raise ValueError("Trigger sequence exceeds the 10,000-nucleotide compute limit.")
    except (EngineError, TypeError, KeyError) as exc:
        raise ValueError(str(exc)) from exc
    normalized = {
        **params,
        "host": host.value,
        "payload": {
            **payload,
            "outputs": [outcome.value for outcome in outputs],
            "optimize_codons": payload.get("optimize_codons", False),
        },
        **(
            {"backbone": {**params["backbone"], "insertion_index": insertion}}
            if backbone_segments
            else {}
        ),
        "constraints": dataclasses.asdict(constraints),
        "budget": {"max_designs": max_designs},
    }
    return copy.deepcopy(normalized)


def _installed_capabilities(engine_version: str) -> EngineCapabilities:
    """Read the registries. Engine-internal, so importing them here is fine."""
    from engine.domain import Constraints, Host
    from engine.gates.registry import describe_families, get_family
    from engine.pipeline import _UNBUILDABLE_FAMILIES, MAX_TRIGGER_LENGTH
    from engine.scoring.profiles import DEFAULT_V1, available_profiles
    from engine.stages.plasmids import BACKBONES, PAYLOAD_HOSTS

    return EngineCapabilities(
        engine_version=engine_version,
        schema_version=SCHEMA_VERSION,
        gate_families=[
            dataclasses.replace(f, available=f.available and f.name not in _UNBUILDABLE_FAMILIES)
            for f in describe_families()
        ],
        supported_hosts=[host.value for host in Host],
        family_hosts={
            f.name: sorted(host.value for host in get_family(f.name).supported_hosts)
            for f in describe_families()
            if f.available and f.name not in _UNBUILDABLE_FAMILIES
        },
        supported_outputs=[outcome.value for outcome in PAYLOAD_HOSTS],
        output_hosts={
            outcome.value: [host.value for host in hosts]
            for outcome, hosts in PAYLOAD_HOSTS.items()
        },
        backbone_hosts={key: ["ecoli"] for key in BACKBONES},
        input_modes=["direct", "de", "gene"],
        limits={
            "max_trigger_length": MAX_TRIGGER_LENGTH,
            "max_de_rows": 200_000,
            "max_payload_length": 2000,
            "max_designs_default": 20,
            "max_designs_limit": 1000,
            "max_circuit_gates": 1,
            "max_triggers": 1,
        },
        constraints=dataclasses.asdict(Constraints()),
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
    ViennaRNA folding throughout. Direct, differential-expression, and named-gene
    inputs work for E. coli, yeast, C. acnes, and Human. Human uses pinned mature
    transcripts, CMV/hGH expression parts, and a custom mammalian backbone or cassette.
    Computational support does not establish wet-lab performance.
    ``ENGINE_VERSION`` says so directly rather than claiming more than this build does.
    """

    ENGINE_VERSION = "local-0.11.0-scientific-qa"

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
