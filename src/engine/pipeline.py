"""The real scientific pipeline.

**Composition only.** This module constructs the tools once, hands them to the stages,
and runs them in order. It contains no science — if it grows past ~150 lines, logic has
leaked into it from a stage.

**Scope of this build (docs/smoke-run.md): the `direct` input path only.** A researcher
pastes a trigger mRNA and gets ranked toehold designs back. The `de` path — upload a
differential-expression table, discover triggers from it — stays a documented
``InputValidationError`` here: it needs stage 1 (`GeneSelector`), the two stubbed tools
stage 2 calls (`FoldProfiler` is now real; `OffTargetScanner` is not), a CSV parser with
no home yet, and a resolved Q1 (where do trigger sequences come from). None of that is
built by this branch. Stages 4 (circuits), 5 (plasmids) and 6 (rendered artifacts) are
likewise out of scope — see docs/smoke-run.md §4 for exactly what that costs the UI.

This branch does not modify anything under ``engine/gates/`` — every gate family and
gate tool it calls (``ToeholdGate`` and its host-specific subclasses, ``FoldEngine``)
was already built. ``FoldEngine.ensemble_defect`` and the RBS-placement rule stay
deferred in ``stages/switches.py`` for the same reason: implementing either means
editing something under ``gates/``.
"""

import dataclasses
from collections.abc import Callable

from engine import sequences as sq
from engine.artifacts import write_artifact
from engine.contract import (
    SCHEMA_VERSION,
    SUCCEEDED,
    ArtifactRef,
    CandidateResult,
    JobRequest,
    JobResult,
    MetricValue,
)
from engine.domain import AssemblyStandard, Constraints, GateDesign, Host, TriggerCandidate
from engine.errors import InputValidationError, JobCancelled
from engine.gates.base import GateFamily
from engine.gates.registry import get_family
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.scoring.normalize import build_metrics, failed_filter, rank_candidates, weighted_score
from engine.scoring.profiles import HardFilter, resolve_profile
from engine.stages.folding import FoldProfiler
from engine.stages.motifs import MotifScreener
from engine.stages.off_target import OffTargetScanner
from engine.stages.switches import SwitchDesigner, SwitchValidator
from engine.store import CandidateStore

ProgressFn = Callable[[int, str], bool]

#: How much of the run each stage is expected to cost. Progress is weighted by this
#: rather than by stage index, or the bar sits at 60% for ten minutes.
STAGE_WEIGHTS: dict[str, int] = {
    "Validating inputs": 2,
    "Selecting genes": 5,
    "Scoring triggers": 25,
    "Designing switches": 45,
    "Designing circuits": 15,
    "Constructing plasmids": 5,
    "Writing report": 3,
}

#: Families skipped even when requested, with why — never silently, always into
#: JobResult.warnings so a researcher who asked for one learns why it is absent.
_UNBUILDABLE_FAMILIES: dict[str, str] = {
    "antisense": (
        "no payload sequence library exists yet (docs/ROADMAP.md Q11) — "
        "AntisenseNotGate cannot be constructed without one. Request a toehold "
        "family instead."
    ),
}


def build_tools(request: JobRequest, host: Host) -> dict[str, object]:
    """Construct every tool **once** per run, and hand them back for wiring.

    Args:
        request: The immutable submission. Supplies the parameters each tool is
            configured from, so that configuration is recorded rather than hardcoded.
        host: The organism. Selects the codon table and the translation mechanism.

    Returns:
        The constructed tools, keyed by name, ready to pass into stages and gate
        families. ``"families"`` holds instantiated, ready-to-use gate families for
        every requested name this build can actually support; ``"warnings"`` names
        every requested family it could not build, and why.

    Why this is a function and not a per-class concern:
        ``FoldEngine``'s cache lives on the instance. Four instances means four cold
        caches — and, worse, four chances for someone to construct one at a different
        temperature. Two designs folded at different temperatures produce numbers that
        ``engine.scoring`` will normalise onto the same axis as though they were
        comparable, and the resulting ranking is wrong in a way nothing detects.

        Constructing them here also means the whole configuration of a run is visible in
        one place, which is what makes it recordable.

    Note:
        The transcriptome that ``OffTargetScanner`` indexes **must be the same build**
        the trigger sequences came from. This build never has one — the `direct` path
        has no transcriptome at all — so it is constructed empty and never called; see
        ``run_pipeline``.
    """
    folder = FoldEngine()
    constraints = _build_constraints(request.params)

    tools: dict[str, object] = {
        "folder": folder,
        "profiler": FoldProfiler(),
        "off_target": OffTargetScanner({}),
        "screener": MotifScreener(constraints.standard),
        "codons": CodonOptimizer(host),
        "translation": TranslationScorer(host),
        "constraints": constraints,
    }

    families: list = []
    warnings: list[str] = []
    for name in request.gate_families or ["toehold"]:
        reason = _UNBUILDABLE_FAMILIES.get(name)
        if reason is not None:
            warnings.append(f"Skipped gate family '{name}': {reason}")
            continue

        family_class = get_family(name)
        if not (family_class.available and host in family_class.supported_hosts):
            warnings.append(f"Skipped gate family '{name}': not available for {host.value}.")
            continue

        families.append(family_class(host, folder, tools["translation"], tools["codons"]))

    tools["families"] = families
    tools["warnings"] = warnings
    return tools


def run_pipeline(request: JobRequest, on_progress: ProgressFn) -> JobResult:
    """Execute the pipeline for one `direct`-mode job.

    Args:
        request: The immutable submission.
        on_progress: Called between stages **and between batches** within the expensive
            one (switch design). A ``False`` return raises ``JobCancelled``.

    Raises:
        InputValidationError: For a ``de`` submission (not built by this branch), an
            organism this engine does not recognise, an unusable trigger sequence, or
            constraints that do not parse. All are ``EngineError`` — **data**, per
            ``EngineClient``'s contract — and ``LocalEngine.run`` converts them into a
            terminal ``JobResult`` rather than letting them propagate as a crash.
        JobCancelled: When ``on_progress`` returns ``False``. Also converted by
            ``LocalEngine.run``.
    """
    if not on_progress(*_pct("Validating inputs")):
        raise JobCancelled("Validating inputs")

    if request.input_mode != "direct":
        raise InputValidationError(
            "Only direct-trigger submissions are supported today — differential-"
            "expression input needs gene selection, off-target scanning and a "
            "transcriptome source none of which this build implements. See "
            "docs/smoke-run.md."
        )

    host = _resolve_host(request)
    tools = build_tools(request, host)
    constraints: Constraints = tools["constraints"]
    families: list = tools["families"]
    warnings: list[str] = list(tools["warnings"])

    if not families:
        raise InputValidationError(
            "None of the requested gate families could be built for this host: "
            + "; ".join(warnings)
        )

    profile = resolve_profile(request.scoring_profile, request.params.get("scoring"))
    store = CandidateStore(request.output_dir, request.run_id)

    if not on_progress(*_pct("Scoring triggers")):
        raise JobCancelled("Scoring triggers")
    trigger = _direct_trigger(request, store, tools["profiler"], tools["folder"])

    validator = SwitchValidator(
        tools["folder"],
        tools["off_target"],
        tools["screener"],
        tools["translation"],
        constraints,
    )
    designer = SwitchDesigner(families, validator, host)
    families_by_kind = {family.kind: family for family in families}

    if not on_progress(*_pct("Designing switches")):
        raise JobCancelled("Designing switches")

    scored: list[tuple[CandidateResult, float | None]] = []
    for index, design in enumerate(designer.design([trigger], constraints)):
        if index % 5 == 0 and not on_progress(*_pct("Designing switches")):
            raise JobCancelled("Designing switches")

        family = families_by_kind[design.gate_kind]
        raw = family.evaluate_design(design)
        metrics = build_metrics(raw, profile)
        breach = failed_filter(raw, profile)

        scored.append(
            (
                _candidate_result(store, design, family, trigger, metrics, breach),
                None if breach else weighted_score(metrics, profile),
            )
        )

    ranks = rank_candidates([(c.ref, s) for c, s in scored if not c.is_rejected])
    candidates = [
        dataclasses.replace(c, rank=ranks.get(c.ref), overall_score=score) for c, score in scored
    ]

    if not on_progress(*_pct("Writing report")):
        raise JobCancelled("Writing report")
    artifacts = _write_artifacts(request.output_dir, candidates)

    if not candidates:
        warnings.append(
            "No candidate designs passed validation for this trigger — see "
            "docs/smoke-run.md §5 for why a validated design is not guaranteed."
        )

    on_progress(100, "Writing report")

    return JobResult(
        schema_version=SCHEMA_VERSION,
        # LocalEngine.run() overwrites this with its own ENGINE_VERSION — the single
        # source of truth for that string, since a bare function has no natural home
        # for a version constant a *client class* is what actually has one.
        engine_version="",
        status=SUCCEEDED,
        candidates=candidates,
        artifacts=artifacts,
        warnings=warnings,
        error=None,
        input_checksum=request.input_checksum,
        params=request.params,
    )


def _pct(stage: str) -> tuple[int, str]:
    """The cumulative percentage through ``STAGE_WEIGHTS`` at the start of ``stage`` —
    reusing the same weight table the full (`de`-capable) pipeline will use, so a
    progress bar does not need to change meaning once stages 1, 4, 5 and 6 land."""
    order = list(STAGE_WEIGHTS)
    total = sum(STAGE_WEIGHTS.values())
    done = sum(STAGE_WEIGHTS[name] for name in order[: order.index(stage)])
    return round(100 * done / total), stage


def _resolve_host(request: JobRequest) -> Host:
    """docs/ROADMAP.md P1: ``request.organism`` (from ``Project.organism``) is free
    text ("E. coli"), not a ``Host`` value. The wizard separately writes a
    ``Host``-compatible string into ``params["organism"]``; prefer that, falling back
    to the top-level field for a caller that passes one directly (``POST /api/design``
    does, since it never populates ``params["organism"]``). Neither being valid is an
    input problem, not a bug, so it is reported as one rather than crashing raw."""
    raw = request.params.get("organism", request.organism)
    try:
        return Host(raw)
    except ValueError:
        raise InputValidationError(
            f"organism {raw!r} is not a recognised host "
            f"({', '.join(h.value for h in Host)}). See docs/ROADMAP.md P1."
        ) from None


def _build_constraints(params: dict) -> Constraints:
    """``Constraints(**params.get("constraints", {}))``, per this module's own sketch —
    with the type coercion a JSON-sourced dict needs and a stub construction never did:
    tuple fields arrive as lists, and ``standard`` arrives as a plain string."""
    raw = dict(params.get("constraints") or {})

    known = {field.name for field in dataclasses.fields(Constraints)}
    unknown = set(raw) - known
    if unknown:
        raise InputValidationError(f"Unknown constraint field(s): {', '.join(sorted(unknown))}.")

    if "trigger_lengths" in raw:
        raw["trigger_lengths"] = tuple(raw["trigger_lengths"])
    if "forbidden_motifs" in raw:
        raw["forbidden_motifs"] = tuple(raw["forbidden_motifs"])
    if "standard" in raw:
        try:
            raw["standard"] = AssemblyStandard(raw["standard"])
        except ValueError:
            raise InputValidationError(f"Unknown assembly standard {raw['standard']!r}.") from None

    try:
        return Constraints(**raw)
    except TypeError as exc:
        raise InputValidationError(f"Invalid constraints: {exc}") from None


def _direct_trigger(
    request: JobRequest, store: CandidateStore, profiler: FoldProfiler, folder: FoldEngine
) -> TriggerCandidate:
    """The whole of stages 1-2 for a `direct` submission: the pasted sequence *is* the
    one trigger, at full length, offset 0 — modalities.md §A2's "the pipeline picks up
    at SwitchDesigner", made concrete.

    Re-validates length and alphabet defensively, mirroring
    ``MockEngine._verify_input`` — the Platform already checked this
    (``apps/analyses/services.py::_clean_trigger``), but the engine must not trust a
    caller that skipped the Platform (``LocalEngine`` used directly, as this module's
    own tests do).

    ``openness``/``accessibility`` follow ``TriggerScorer.score``'s already-decided
    convention exactly (mean, then minimum, of the same profile slice) rather than
    inventing a second one — profiling the pasted sequence *as* the transcript, since a
    `direct` submission has no larger context to profile.
    """
    sequence = sq.to_rna(request.trigger_sequence)
    if len(sequence) < 20:
        raise InputValidationError(
            "The trigger sequence is too short to design a switch against "
            "(at least 20 nucleotides are needed)."
        )
    if not sq.is_valid_rna(sequence):
        raise InputValidationError(
            "The trigger sequence contains characters other than A, C, G and U."
        )

    window = profiler.profile(sequence)

    return TriggerCandidate(
        trigger_id=store.mint_id("trig"),
        gene_id="direct",
        symbol="direct-trigger",
        sequence=sequence,
        start_index=0,
        openness=sum(window) / len(window),
        accessibility=min(window),
        mfe=folder.mfe(sequence).energy,
        # No transcriptome exists for a direct submission (build_tools constructs
        # OffTargetScanner empty and it is never called), so there is nothing to scan
        # against. 0.0/1.0 read as "clean" rather than "not measured" because
        # TriggerCandidate.off_target_penalty is a plain float with no None state to
        # express the difference — and neither built gate family's evaluate_design
        # reads either field today, so this has no effect on any current output.
        off_target_penalty=0.0,
        segment_specificity=1.0,
        gc_content=sq.gc_content(sequence),
        aug_indexes=sq.find_augs(sequence),
        stop_indexes=sq.find_stops(sequence),
    )


def _candidate_result(
    store: CandidateStore,
    design: GateDesign,
    family: GateFamily,
    trigger: TriggerCandidate,
    metrics: list[MetricValue],
    breach: HardFilter | None,
) -> CandidateResult:
    """One validated ``GateDesign`` plus its measured metrics, shaped as a
    ``CandidateResult`` the Platform can import. Stages 4-5 do not exist in this build,
    so ``logic_graph``/``plasmid_segments`` are honest about it — one gene, no chosen
    payload, no plasmid — rather than fabricated (docs/smoke-run.md §4): every frontend
    field the two render components actually index unconditionally
    (``LogicCircuit.tsx``'s ``genes[0]``, ``PlasmidRing.tsx``'s length fallback) is
    still present and valid, just empty where there is nothing real to show yet.
    """
    logic_graph = {
        "genes": [{"name": "A", "role": trigger.symbol, "state": "ON", "direction": "up"}],
        "mid_gate": "AND",
        "outer_gate": "AND",
        "invert": False,
        "output": "",
        "caption": f"IF {trigger.symbol} -> [no payload selected — stage 5 not built]",
    }

    return CandidateResult(
        ref=store.mint_id("cand"),
        rank=None,
        overall_score=None,
        gate_family=family.name,
        logic_type=design.trigger_set.logic_type,
        triggers={
            "features": [
                {
                    "feature_id": trigger.symbol,
                    "sequence": trigger.sequence,
                    "openness": trigger.openness,
                    "accessibility": trigger.accessibility,
                }
            ]
        },
        design={
            "switch_sequence": design.sequence,
            "structure": design.dot_bracket,
            "toehold_length": design.architecture.get("toehold_length", 0),
            "sequence_length_bp": len(design.sequence),
            "plasmid_segments": [],
            "logic_graph": logic_graph,
        },
        summary=f"{design.trigger_set.logic_type} {family.name} gate on {trigger.symbol}",
        metrics=metrics,
        warnings=[],
        is_rejected=breach is not None,
        rejection_reason=breach.reason if breach else "",
    )


def _write_artifacts(output_dir: str, candidates: list[CandidateResult]) -> list[ArtifactRef]:
    """A design table plus a FASTA per accepted candidate — the same shape
    ``MockEngine._write_artifacts`` produces, so the Platform's artifact import and
    download path is exercised identically regardless of which engine ran."""
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

    artifacts = [
        write_artifact(
            output_dir,
            "candidates.csv",
            "\n".join(rows) + "\n",
            kind="design_table",
            media_type="text/csv",
        )
    ]

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
