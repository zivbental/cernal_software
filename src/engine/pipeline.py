"""The real scientific pipeline.

**Composition only.** This module constructs the tools once, hands them to the stages,
and runs them in order. It contains no science — if it grows past ~150 lines, logic has
leaked into it from a stage.

**Scope of this build (docs/smoke-run.md): the `direct` input path only.** A researcher
pastes a trigger mRNA and gets ranked toehold designs back, each with a real,
annotated plasmid (docs/plasmids.md, E5a). The `de` path — upload a
differential-expression table, discover triggers from it — stays a documented
``InputValidationError`` here: it needs stage 1 (`GeneSelector`), the two stubbed tools
stage 2 calls (`FoldProfiler` is now real; `OffTargetScanner` is not), a CSV parser with
no home yet, and a resolved Q1 (where do trigger sequences come from). None of that is
built by this branch. Stage 4 (`CircuitDesigner`, real multi-switch circuits) and stage 6
(the PDF report, structure/circuit figures) are likewise out of scope — see
docs/smoke-run.md §4 and docs/plasmids.md §3 for exactly what that costs.

**Stage 5 does not wait for stage 4.** A `direct` submission has one trigger and one
switch, so ``_build_plasmid`` hand-builds a trivial one-gene ``CircuitCandidate`` the
same way ``_direct_trigger`` hand-builds the one ``TriggerCandidate`` for stages 1-2
(docs/plasmids.md §3) — ``PlasmidBuilder.build()`` never sees that this circuit was not
produced by a real ``CircuitDesigner``.

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
from engine.domain import (
    AssemblyStandard,
    BooleanExpression,
    CircuitCandidate,
    ConfusionMatrix,
    Constraints,
    DesiredOutcome,
    GateDesign,
    Host,
    LogicGraph,
    LogicOperator,
    PlasmidDesign,
    TriggerCandidate,
)
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
from engine.stages.plasmids import (
    PAYLOADS,
    PROMOTERS,
    TERMINATORS,
    PlasmidBuilder,
    to_genbank,
    validate_payload_cds,
)
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
    screener = MotifScreener(constraints.standard)
    codons = CodonOptimizer(host)

    tools: dict[str, object] = {
        "folder": folder,
        "profiler": FoldProfiler(),
        "off_target": OffTargetScanner({}),
        "screener": screener,
        "codons": codons,
        "translation": TranslationScorer(host),
        # Same screener/codons instances as above — a second PlasmidBuilder-only
        # MotifScreener would mean two independently configured screeners agreeing by
        # coincidence rather than by construction.
        "plasmid_builder": PlasmidBuilder(screener, codons, constraints.standard),
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

    outcomes, outcome_warnings = _resolve_outputs(request.params, host)
    warnings.extend(outcome_warnings)
    if not outcomes:
        raise InputValidationError(
            "None of the requested outputs could be built for this host: "
            + ("; ".join(outcome_warnings) if outcome_warnings else "no output was requested.")
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

    plasmid_builder: PlasmidBuilder = tools["plasmid_builder"]
    custom_sequence = (request.params.get("payload") or {}).get("custom_sequence")

    scored: list[tuple[CandidateResult, float | None]] = []
    plasmids: dict[str, PlasmidDesign] = {}
    for index, design in enumerate(designer.design([trigger], constraints)):
        if index % 5 == 0 and not on_progress(*_pct("Designing switches")):
            raise JobCancelled("Designing switches")

        family = families_by_kind[design.gate_kind]
        raw = family.evaluate_design(design)
        metrics = build_metrics(raw, profile)
        breach = failed_filter(raw, profile)

        # Round-robin, matching MockEngine._build_candidates: every requested output
        # gets a comparable share of the candidate budget rather than one dominating
        # by chance (both engines must agree on this, or a real run's distribution
        # looks like a bug next to the mock one it is meant to match).
        outcome = outcomes[index % len(outcomes)]
        plasmid = _build_plasmid(plasmid_builder, store, design, outcome, custom_sequence)

        candidate = _candidate_result(
            store, design, family, trigger, metrics, breach, plasmid, outcome
        )
        plasmids[candidate.ref] = plasmid

        scored.append((candidate, None if breach else weighted_score(metrics, profile)))

    ranks = rank_candidates([(c.ref, s) for c, s in scored if not c.is_rejected])
    candidates = [
        dataclasses.replace(c, rank=ranks.get(c.ref), overall_score=score) for c, score in scored
    ]

    if not on_progress(*_pct("Writing report")):
        raise JobCancelled("Writing report")
    artifacts = _write_artifacts(request.output_dir, candidates, plasmids)

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
    """docs/ROADMAP.md P1: ``request.organism`` (from ``AnalysisRun.organism``) is free
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


def _resolve_outputs(params: dict, host: Host) -> tuple[list[DesiredOutcome], list[str]]:
    """Which of ``params["payload"]["outputs"]`` can actually be built today, and why
    any cannot (docs/plasmids.md Q11/Q12/Q13) — the same "skip and say why" pattern
    ``_UNBUILDABLE_FAMILIES`` already uses for gate families, applied to payloads.

    An unrecognised output string is a caller mistake, not a capability gap, and is
    reported immediately rather than silently skipped — the same distinction
    ``_resolve_host`` draws for an unrecognised organism.
    """
    payload = params.get("payload") or {}
    requested = payload.get("outputs") or ["gfp"]
    custom_sequence = payload.get("custom_sequence")

    outcomes: list[DesiredOutcome] = []
    for raw in requested:
        try:
            outcomes.append(DesiredOutcome(raw))
        except ValueError:
            raise InputValidationError(
                f"Unknown output {raw!r}. Known outputs: "
                f"{', '.join(o.value for o in DesiredOutcome)}."
            ) from None

    if host not in PROMOTERS or host not in TERMINATORS:
        return [], [
            f"No plasmid can be built for host {host.value!r} yet: no promoter/"
            "terminator is configured (docs/ROADMAP.md Q12)."
        ]

    buildable: list[DesiredOutcome] = []
    warnings: list[str] = []
    for outcome in outcomes:
        if outcome is DesiredOutcome.CUSTOM:
            if not custom_sequence:
                warnings.append("Skipped output 'other': no custom_sequence was supplied.")
            else:
                try:
                    validate_payload_cds("Custom", custom_sequence)
                except InputValidationError as exc:
                    warnings.append(f"Skipped output 'other': {exc}")
                else:
                    buildable.append(outcome)
        elif outcome in PAYLOADS:
            buildable.append(outcome)
        else:
            warnings.append(
                f"Skipped output {outcome.value!r}: no payload sequence is configured "
                "yet (docs/ROADMAP.md Q11)."
            )

    return buildable, warnings


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


def _build_plasmid(
    builder: PlasmidBuilder,
    store: CandidateStore,
    design: GateDesign,
    outcome: DesiredOutcome,
    custom_sequence: str | None,
) -> PlasmidDesign:
    """Wrap one accepted switch design in a trivial one-gene ``CircuitCandidate`` —
    the same move ``_direct_trigger`` makes for stages 1-2, since a `direct` run's
    circuit *is* the one switch (docs/plasmids.md §3) — and build its plasmid.

    Never raises: ``run_pipeline`` only reaches this after ``_resolve_outputs`` has
    already confirmed ``outcome`` is buildable for this host.
    """
    circuit = CircuitCandidate(
        circuit_id=store.mint_id("circ"),
        # Placeholders below: PlasmidBuilder.build() reads only circuit.designs and
        # circuit.circuit_id (see its own source) — expression/logic_graph/confusion
        # exist only to satisfy CircuitCandidate's shape and are discarded the moment
        # this function returns. In particular ConfusionMatrix(0, 0, 0, 0) must never
        # be read as a measured separation of -1.0 (docs/plasmids.md §3) — it is not,
        # because nothing downstream of this call ever looks at it.
        expression=BooleanExpression.gene(design.trigger_set.activators[0].symbol),
        logic_graph=LogicGraph(
            genes=(),
            mid_gate=LogicOperator.IDENTITY,
            outer_gate=LogicOperator.IDENTITY,
            invert=False,
            output=outcome.value,
            caption="",
        ),
        designs=(design,),
        confusion=ConfusionMatrix(0, 0, 0, 0),
        output=outcome.value,
    )
    if outcome is DesiredOutcome.CUSTOM:
        return builder.build(circuit, outcome, custom_payload=custom_sequence)
    return builder.build(circuit, outcome)


def _candidate_result(
    store: CandidateStore,
    design: GateDesign,
    family: GateFamily,
    trigger: TriggerCandidate,
    metrics: list[MetricValue],
    breach: HardFilter | None,
    plasmid: PlasmidDesign,
    outcome: DesiredOutcome,
) -> CandidateResult:
    """One validated ``GateDesign`` plus its measured metrics and its plasmid
    (docs/plasmids.md, E5a), shaped as a ``CandidateResult`` the Platform can import.

    Stage 4 (real multi-gene circuits) does not exist in this build, so
    ``logic_graph`` still describes one gene rather than fabricating a circuit
    (docs/smoke-run.md §4) — but ``plasmid_segments`` is real, from the plasmid
    ``_build_plasmid`` just constructed. Any compliance violation is carried as a
    candidate warning, never silently dropped (docs/plasmids.md §9) — a violation is
    a fact about the construct, not a reason to reject the switch design itself.
    """
    logic_graph = {
        "genes": [{"name": "A", "role": trigger.symbol, "state": "ON", "direction": "up"}],
        "mid_gate": "AND",
        "outer_gate": "AND",
        "invert": False,
        "output": outcome.display_name,
        "caption": f"IF {trigger.symbol} -> {outcome.display_name}",
    }
    plasmid_segments = [
        {"kind": segment.kind.value, "name": segment.name, "length_bp": segment.length_bp}
        for segment in plasmid.plasmid.segments
    ]

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
            "plasmid_segments": plasmid_segments,
            "logic_graph": logic_graph,
        },
        summary=f"{design.trigger_set.logic_type} {family.name} gate on {trigger.symbol}",
        metrics=metrics,
        warnings=[f"Plasmid: {v}" for v in plasmid.violations],
        is_rejected=breach is not None,
        rejection_reason=breach.reason if breach else "",
    )


def _write_artifacts(
    output_dir: str, candidates: list[CandidateResult], plasmids: dict[str, PlasmidDesign]
) -> list[ArtifactRef]:
    """A design table, a FASTA and a GenBank per accepted candidate — the FASTA and
    table match the shape ``MockEngine._write_artifacts`` produces, so the Platform's
    artifact import and download path is exercised identically regardless of which
    engine ran; the GenBank is new (docs/plasmids.md, E5a) and has no mock equivalent
    yet.

    ``plasmids`` is keyed by candidate ref, from the same run that produced
    ``candidates`` — every accepted candidate has an entry (``_build_plasmid`` never
    raises once ``_resolve_outputs`` has confirmed the outcome is buildable).
    """
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

        artifacts.append(
            write_artifact(
                output_dir,
                f"plasmids/{candidate.ref}.gb",
                to_genbank(plasmids[candidate.ref]),
                kind="genbank",
                media_type="text/plain",
                candidate_ref=candidate.ref,
            )
        )

    return artifacts
