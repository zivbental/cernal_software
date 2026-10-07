"""The real scientific pipeline.

**Composition only.** This module constructs the tools once, hands them to the stages,
and runs them in order. It contains no science — if it grows past ~150 lines, logic has
leaked into it from a stage.

**Scope of this build (docs/smoke-run.md, docs/genes.md): `direct` and a first, scoped
`de` path.** A researcher pastes a trigger mRNA — or a longer transcript to find one in,
docs/triggers.md E2b — and gets ranked toehold designs back, each with a real, annotated
plasmid (docs/plasmids.md, E5a). A researcher who instead uploads a differential-
expression table gets the *same* thing, sourced differently: ``GeneSelector`` (real,
docs/genes.md) ranks the genes, the best ones' real transcripts (``engine.transcriptome``
— *E. coli* and yeast today, docs/ROADMAP.md Q1's first two answers) are scanned for
triggers by the same ``TriggerScorer`` the `direct` path already uses, and everything
after that — switch design, plasmid construction — is one shared code path for both
modes and both hosts.

**What the `de` path still does not do, deliberately.** No ``InputQualityCheck`` — there
is no count matrix to check; the product only ever collects a differential-expression
table (docs/genes.md §3 G-a), so the stage that validates one has nothing to run on
yet. No off-target scanning at all — the scanner and the two trigger fields it fed
were removed rather than left as placeholders that read as measurements. No
real confusion matrix — ``CircuitDesigner`` now builds circuits that combine up to
``Constraints.max_circuit_gates`` genes (``A AND NOT B``), but with no per-sample count
matrix there is nothing to evaluate their *behaviour* against, so a circuit is scored on
complexity and on its weakest member rather than on a measured separation. No human — no bundled reference
transcriptome (a genomic CDS extraction is the wrong tool for a heavily-spliced genome,
``tools/sync_transcriptome.py``), and no promoter/terminator either (Q12). No bundled
yeast plasmid backbone either, deliberately — yeast's real BioBrick-family assembly
grammar (the "Lim standard") could not be fully verified from public sources in the
time this took, so a yeast run relies on ``params["backbone"]["custom_genbank"]``
(a lab's own real vector) rather than a first-party default built on a half-verified
restriction-site table (CLAUDE.md §1: an almost-right part is worse than a missing
one) — omitting backbone entirely is also a fully legal choice (``_resolve_backbone``'s
own docstring). Stage 6 (the PDF report, structure/circuit figures) is out of scope for
every mode and host — see docs/smoke-run.md §4 and docs/plasmids.md §3 for exactly what
that costs.

**Stage 5 does not wait for stage 4.** Each accepted switch design gets its own
trivial one-gene ``CircuitCandidate`` from ``_build_plasmid``, the same way
``_direct_trigger``/``_de_trigger`` hand-build ``TriggerCandidate``(s) for stages 1-2
(docs/plasmids.md §3) — ``PlasmidBuilder.build()`` never sees that this circuit was not
produced by a real ``CircuitDesigner``.

This branch does not modify anything under ``engine/gates/`` — every gate family and
gate tool it calls (``ToeholdGate`` and its host-specific subclasses, ``FoldEngine``)
was already built. ``FoldEngine.ensemble_defect`` and the RBS-placement rule stay
deferred in ``stages/switches.py`` for the same reason: implementing either means
editing something under ``gates/``.
"""

import dataclasses
import json
import re
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

from engine import sequences as sq
from engine.artifacts import sha256_bytes, write_artifact
from engine.contract import (
    HIGHER_BETTER,
    INPUT_DE,
    INPUT_DIRECT,
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
    CountMatrix,
    DesiredOutcome,
    GateDesign,
    Host,
    LogicGraph,
    LogicOperator,
    PlasmidDesign,
    Regulation,
    SampleMetadata,
    Segment,
    SegmentKind,
    SelectedGene,
    TriggerCandidate,
)
from engine.errors import ChecksumMismatchError, InputValidationError, JobCancelled
from engine.gates.base import GateFamily
from engine.gates.registry import get_family
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.inputs import parse_dge_table
from engine.safety import fail_closed_release
from engine.scoring.normalize import build_metrics, failed_filter, rank_candidates, weighted_score
from engine.scoring.profiles import HardFilter, ScoringProfile, resolve_profile
from engine.stages.circuits import CircuitDesigner, ConfusionEvaluator
from engine.stages.folding import FoldProfiler
from engine.stages.genes import GeneSelector
from engine.stages.motifs import MotifScreener
from engine.stages.plasmids import (
    BACKBONES,
    PAYLOADS,
    PROMOTERS,
    TERMINATORS,
    PlasmidBuilder,
    parse_custom_backbone,
    to_genbank,
    to_sbol3,
    validate_payload_cds,
)
from engine.stages.switches import SwitchDesigner, SwitchValidator
from engine.stages.triggers import TriggerScorer
from engine.store import CandidateStore
from engine.transcriptome import available_hosts, load_transcriptome

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

#: Upper bound on a pasted `direct` sequence (docs/triggers.md T2). Generous for any real
#: transcript including UTRs — measured, screening+folding a transcript this long costs
#: well under two seconds — and a guard against a sequence with no realistic trigger
#: reading (a whole plasmid or genome pasted by mistake) hanging a single, uninterruptible
#: call with no cancellation checkpoint inside it.
MAX_TRIGGER_LENGTH = 10_000

#: Families skipped even when requested, with why — never silently, always into
#: JobResult.warnings so a researcher who asked for one learns why it is absent.
_UNBUILDABLE_FAMILIES: dict[str, str] = {
    "antisense": (
        "no payload sequence library exists yet (docs/ROADMAP.md Q11) — "
        "AntisenseNotGate cannot be constructed without one. Request a toehold "
        "family instead."
    ),
    # available=True is inherited from ToeholdGate, but generate_designs is an
    # unconditional NotImplementedError (docs/triggers.md E2b) — dormant while a
    # direct run only ever supplies one trigger (is_compatible's arity check rejects
    # every attempt first), but trigger scanning (E2b) can now produce real 2-input
    # trigger sets, which would reach generate_designs and crash the run uncaught.
    "toehold_and": "the two-input AND construction is not yet implemented for this chemistry.",
    "prokaryotic_toehold_and": (
        "the two-input AND construction is not yet implemented for this chemistry."
    ),
    "eukaryotic_toehold_and": (
        "the two-input AND construction is not yet implemented for this chemistry."
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
        The transcriptome **must be the same build**
        the trigger sequences came from. This build never has one — the `direct` path
        has no transcriptome at all — so it is constructed empty
        (docs/triggers.md T1: an empty transcriptome gives a defined, honest
        "nothing to compare against" answer rather than raising). Off-target
        specificity is consequently never *measured* on this path, only defaulted —
        the warning below says so, so a 0.0 penalty is never mistaken for a clean scan.
    """
    folder = FoldEngine()
    constraints = _build_constraints(request.params)
    screener = MotifScreener(constraints.standard)
    codons = CodonOptimizer(host)
    backbone = _resolve_backbone(request.params)

    tools: dict[str, object] = {
        "folder": folder,
        "profiler": FoldProfiler(),
        "screener": screener,
        "codons": codons,
        "translation": TranslationScorer(host),
        # Same screener/codons instances as above — a second PlasmidBuilder-only
        # MotifScreener would mean two independently configured screeners agreeing by
        # coincidence rather than by construction.
        "plasmid_builder": PlasmidBuilder(screener, codons, constraints.standard, backbone),
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
    """Execute the pipeline for one `direct`- or `de`-mode job.

    Args:
        request: The immutable submission.
        on_progress: Called between stages **and between batches** within the expensive
            one (switch design). A ``False`` return raises ``JobCancelled``.

    Raises:
        InputValidationError: An unrecognised ``input_mode``, a ``de`` submission for a
            host with no bundled reference transcriptome (*E. coli* and yeast today,
            not human — ``engine.transcriptome.available_hosts()``, docs/ROADMAP.md
            Q1), an organism this engine does not recognise, an unusable dataset or
            trigger sequence, or constraints that do not parse. All are
            ``EngineError`` — **data**, per ``EngineClient``'s contract — and
            ``LocalEngine.run`` converts them into a terminal ``JobResult`` rather than
            letting them propagate as a crash.
        ChecksumMismatchError: A ``de`` submission's dataset file does not match the
            checksum recorded at submission time.
        JobCancelled: When ``on_progress`` returns ``False``. Also converted by
            ``LocalEngine.run``.
    """
    if not on_progress(*_pct("Validating inputs")):
        raise JobCancelled("Validating inputs")

    if request.input_mode not in (INPUT_DIRECT, INPUT_DE):
        raise InputValidationError(f"Unrecognised input mode {request.input_mode!r}.")

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

    if request.input_mode == INPUT_DE:
        if not on_progress(*_pct("Selecting genes")):
            raise JobCancelled("Selecting genes")
        if not on_progress(*_pct("Scoring triggers")):
            raise JobCancelled("Scoring triggers")
        trigger_candidates, trigger_warnings = _de_trigger(
            request,
            store,
            tools["profiler"],
            tools["folder"],
            tools["screener"],
            constraints,
            host,
        )
    else:
        if not on_progress(*_pct("Scoring triggers")):
            raise JobCancelled("Scoring triggers")
        trigger_candidates, trigger_warnings = _direct_trigger(
            request,
            store,
            tools["profiler"],
            tools["folder"],
            tools["screener"],
            constraints,
        )
    warnings.extend(trigger_warnings)

    validator = SwitchValidator(
        tools["folder"],
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

    # Two independent tallies (docs/triggers.md T3) — counted in different units
    # (trigger sets vs. generated designs), so kept separate rather than summed into
    # one misleading total. One real example message is kept per bucket for display;
    # the report never shows the generalized template itself.
    incompatible_counts: Counter[str] = Counter()
    incompatible_examples: dict[str, str] = {}
    invalid_counts: Counter[str] = Counter()
    invalid_examples: dict[str, str] = {}

    def _on_incompatible(reason: str) -> None:
        key = _rejection_bucket(reason)
        incompatible_counts[key] += 1
        incompatible_examples.setdefault(key, reason)

    def _on_invalid(reason: str) -> None:
        key = _rejection_bucket(reason)
        invalid_counts[key] += 1
        invalid_examples.setdefault(key, reason)

    scored: list[tuple[CandidateResult, float | None]] = []
    plasmids: dict[str, PlasmidDesign] = {}
    #: Accepted one-gate designs with their raw metrics and score, for stage 4 to
    #: combine. Rejected designs are excluded: a circuit built on a switch that
    #: already breached a hard filter is not a circuit worth proposing.
    single_gate: list[tuple[GateDesign, dict[str, float | None], float]] = []
    designs = designer.design(
        trigger_candidates, constraints, on_incompatible=_on_incompatible, on_invalid=_on_invalid
    )
    for index, design in enumerate(designs):
        if index % 5 == 0 and not on_progress(*_pct("Designing switches")):
            raise JobCancelled("Designing switches")

        family = families_by_kind[design.gate_kind]
        raw = family.evaluate_design(design)
        metrics = build_metrics(raw, profile)
        breach = failed_filter(raw, profile)

        # Round-robin: every requested output
        # gets a comparable share of the candidate budget rather than one dominating
        # by chance (both engines must agree on this, or a real run's distribution
        # looks like a bug next to the mock one it is meant to match).
        outcome = outcomes[index % len(outcomes)]
        plasmid = _build_plasmid(plasmid_builder, store, design, outcome, custom_sequence)

        # The specific trigger that produced *this* design — scanning (docs/triggers.md
        # T2) can feed multiple candidates from different windows into one run, so this
        # is no longer necessarily the same trigger for every design.
        trigger = design.trigger_set.activators[0]
        candidate = _candidate_result(
            store, design, family, trigger, metrics, breach, plasmid, outcome
        )
        plasmids[candidate.ref] = plasmid

        score = None if breach else weighted_score(metrics, profile)
        scored.append((candidate, score))
        if not breach:
            single_gate.append((design, raw, score or 0.0))

    # Stage 4: circuits longer than one gate, when the researcher allows them.
    for candidate, plasmid, score in _multi_gate_candidates(
        single_gate,
        trigger_candidates,
        constraints,
        profile,
        plasmid_builder,
        store,
        outcomes,
        custom_sequence,
        families_by_kind,
    ):
        plasmids[candidate.ref] = plasmid
        scored.append((candidate, score))

    ranks = rank_candidates([(c.ref, s) for c, s in scored if not c.is_rejected])
    candidates = [
        dataclasses.replace(c, rank=ranks.get(c.ref), overall_score=score) for c, score in scored
    ]

    if not on_progress(*_pct("Writing report")):
        raise JobCancelled("Writing report")
    artifacts = _write_artifacts(request.output_dir, candidates, plasmids)

    if not candidates and trigger_candidates:
        # trigger_candidates was non-empty, so the loop above genuinely tried and
        # failed — report why, rather than the old one-size-fits-all message. When
        # trigger_candidates is already empty, _direct_trigger's own warning (above)
        # already explains it; adding this too would double-report the same failure.
        summary = _summarize_rejections(incompatible_counts, incompatible_examples, "trigger set")
        summary += _summarize_rejections(invalid_counts, invalid_examples, "generated design")
        if summary:
            warnings.append("No candidate designs passed validation." + summary)
        else:
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


def _rejection_bucket(reason: str) -> str:
    """Collapse a specific rejection message to its general shape, so many
    near-identical messages (differing only in a position, a count, or an ID) tally
    into one reported bucket instead of one each (docs/triggers.md T3).

    Position lists first, so ``"found 2 at [50, 58]"`` and ``"found 3 at [22, 53, 59]"``
    both become ``"found N at [...]"`` rather than differing only in list length; then
    every remaining run of digits becomes ``N``. A specific enzyme name or homopolymer
    letter is deliberately left alone — a PstI site and an XbaI site are genuinely
    different problems, and should not be merged.
    """
    generalized = re.sub(r"\[[\d,\s]*\]", "[...]", reason)
    return re.sub(r"\d+", "N", generalized)


def _summarize_rejections(counts: "Counter[str]", examples: dict[str, str], unit: str) -> str:
    """The top few rejection buckets as one reportable clause, or ``""`` if nothing was
    tallied. ``examples`` supplies one real, unmodified message per bucket — the
    generalized template from ``_rejection_bucket`` is for grouping only, never shown."""
    if not counts:
        return ""
    total = sum(counts.values())
    detail = "; ".join(f"{n}x {examples[key]}" for key, n in counts.most_common(3))
    return f" {total} {unit}(s) rejected: {detail}."


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
        trigger_lengths = raw["trigger_lengths"]
        if isinstance(trigger_lengths, (str, bytes)) or not isinstance(trigger_lengths, Sequence):
            raise InputValidationError(
                "trigger_lengths must be a non-empty sequence of unique positive integers."
            )
        trigger_lengths = tuple(trigger_lengths)
        if not trigger_lengths:
            raise InputValidationError("trigger_lengths must not be empty.")
        if any(
            isinstance(length, bool) or not isinstance(length, int) for length in trigger_lengths
        ):
            raise InputValidationError("trigger_lengths values must be positive integers.")
        if any(length <= 0 for length in trigger_lengths):
            raise InputValidationError("trigger_lengths values must be positive integers.")
        if len(set(trigger_lengths)) != len(trigger_lengths):
            raise InputValidationError("trigger_lengths values must be unique.")
        raw["trigger_lengths"] = trigger_lengths
    if "forbidden_motifs" in raw:
        raw["forbidden_motifs"] = tuple(raw["forbidden_motifs"])
    if "trigger_gc_range" in raw:
        raw["trigger_gc_range"] = tuple(raw["trigger_gc_range"])
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


def _resolve_backbone(params: dict) -> tuple[Segment, ...]:
    """The backbone segment(s) for this run, from ``params["backbone"]``
    (docs/plasmids.md Q13, docs/ROADMAP.md E5b).

    Unlike ``_resolve_outputs``, there is no "skip and warn" case here — a backbone is
    one choice, not a list of alternatives, so a bad one is a hard
    ``InputValidationError`` rather than something to silently drop. Omitting
    ``params["backbone"]`` entirely is itself a fully legal choice: the plasmid is then
    promoter+switch+payload+terminator only, exactly as every `direct` run built before
    this feature existed — never a silent default a caller did not ask for.

    Raises:
        InputValidationError: both ``catalog_key`` and ``custom_genbank`` are given
            (ambiguous — same "exactly one of" shape as the input-mode check on
            ``POST /api/design``), ``catalog_key`` names no configured backbone, or
            ``custom_genbank`` fails to parse (:func:`parse_custom_backbone`).
    """
    backbone = params.get("backbone") or {}
    catalog_key = backbone.get("catalog_key")
    custom_genbank = backbone.get("custom_genbank")

    if catalog_key and custom_genbank:
        raise InputValidationError(
            "Provide at most one of backbone.catalog_key or backbone.custom_genbank, not both."
        )
    if custom_genbank:
        return (parse_custom_backbone(custom_genbank),)
    if catalog_key:
        try:
            name, sequence = BACKBONES[catalog_key]
        except KeyError:
            raise InputValidationError(
                f"No backbone {catalog_key!r} is configured. Configured: "
                f"{', '.join(sorted(BACKBONES))}."
            ) from None
        return (Segment(SegmentKind.BACKBONE, name, sequence),)
    return ()


def _validate_scanned_trigger_lengths(constraints: Constraints) -> None:
    "Require an exact gate mapping before scanning transcript windows."
    unsupported = sorted(set(constraints.trigger_lengths) - TriggerScorer.ALLOWED_SCANNED_LENGTHS)
    if unsupported:
        raise InputValidationError(
            "trigger_lengths for transcript scanning may contain only the exact supported "
            "footprints 30, 33, and 36 nt; unsupported: " + ", ".join(map(str, unsupported)) + "."
        )


def _direct_trigger(
    request: JobRequest,
    store: CandidateStore,
    profiler: FoldProfiler,
    folder: FoldEngine,
    screener: MotifScreener,
    constraints: Constraints,
) -> tuple[list[TriggerCandidate], list[str]]:
    """Resolve the trigger(s) for a `direct` submission (docs/triggers.md, E2b).

    A pasted sequence can mean two different things: *"this is my trigger"* (a
    ~30-36 nt window, sized to a chemistry's footprint) or *"this is my target
    transcript — find a trigger in it"* (anything longer, e.g. a full mRNA). Today's
    rule: if the paste already fits within one window
    (``max(constraints.trigger_lengths)``), it **is** the one trigger, full length,
    offset 0 — modalities.md §A2's "the pipeline picks up at SwitchDesigner", made
    concrete, and unchanged from before this function scanned anything. Longer than
    that, it is scanned like a transcript, using the already-built, already-tested
    ``TriggerScorer.score`` rather than a second implementation of window-scanning.

    This is a deliberate, measured divergence from treating every paste identically
    regardless of length: scanning even an exact, already-correctly-sized paste would
    take the reference `direct` scenario from 3 candidate designs to 12 (measured,
    against ``constraints.trigger_lengths = (30, 33, 36)``), which contradicts
    docs/smoke-run.md §5's explicit "three designs... is exactly what a smoke run
    wants, do not widen for more results." The threshold is not a magic constant — it
    is derived from ``constraints`` itself, so it moves if the configured window
    lengths ever do.

    Re-validates length and alphabet defensively, mirroring
    the Platform already checked this
    (``apps/analyses/services.py::_clean_trigger``), but the engine must not trust a
    caller that skipped the Platform (``LocalEngine`` used directly, as this module's
    own tests do).

    Returns:
        The candidate trigger(s), ranked best first, and any warnings about how they
        were chosen (how many windows were considered, how many survived — or, if
        none did, why). Empty candidates with a non-empty warning is a valid, reported
        outcome, not a raised error — mirroring the existing "candidates is empty"
        convention at the end of ``run_pipeline`` rather than introducing a second one.
    """
    sequence = sq.to_rna(request.trigger_sequence)
    if len(sequence) < 20:
        raise InputValidationError(
            "The trigger sequence is too short to design a switch against "
            "(at least 20 nucleotides are needed)."
        )
    if len(sequence) > MAX_TRIGGER_LENGTH:
        raise InputValidationError(
            f"The trigger sequence is {len(sequence)} nt, over the "
            f"{MAX_TRIGGER_LENGTH} nt limit for a direct submission."
        )
    if not sq.is_valid_rna(sequence):
        raise InputValidationError(
            "The trigger sequence contains characters other than A, C, G and U."
        )

    max_window = max(constraints.trigger_lengths)
    if len(sequence) <= max_window:
        # Preserve today's selection behaviour: the whole paste is the one
        # trigger. openness/accessibility follow TriggerScorer.score's already-decided
        # convention (mean, then minimum, of the same profile slice) rather than
        # inventing a second one — profiling the pasted sequence *as* the transcript,
        # since a `direct` submission this short has no larger context to profile.
        window = profiler.profile(sequence)
        openness = sum(window) / len(window)
        trigger = TriggerCandidate(
            trigger_id=store.mint_id("trig"),
            gene_id="direct",
            symbol="direct-trigger",
            sequence=sequence,
            start_index=0,
            openness=openness,
            accessibility=min(window),
            mfe=folder.mfe(sequence).energy,
            gc_content=sq.gc_content(sequence),
            aug_indexes=sq.find_augs(sequence),
            stop_indexes=sq.find_stops(sequence),
            score=openness,
        )
        return [trigger], []

    # Longer than one window: genuinely ambiguous which sub-window is "the" trigger.
    _validate_scanned_trigger_lengths(constraints)
    # Reuse TriggerScorer.score rather than reimplementing scanning — it already
    # screens motifs, profiles once, folds survivors and ranks (stages/triggers.py).
    gene = SelectedGene(
        gene_id="direct",
        symbol="direct-trigger",
        regulation=Regulation.UP,
        # This describes a differential-expression comparison this submission never
        # made, so every field below is None or inert rather than a fabricated
        # measurement (domain.py's "None means not measured" rule, docs/genes.md §3 G1).
        # log2_fold_change is None specifically: it now travels onto every
        # TriggerCandidate and is read as `state_separation`, and a 0.0 there would
        # breach that metric's own hard filter on a quantity this mode cannot have.
        log2_fold_change=None,
        score=0.0,
    )
    scorer = TriggerScorer(profiler, screener, folder)
    scored = list(scorer.score([gene], {"direct": sequence}, constraints))
    # Re-mint through CandidateStore: TriggerCandidate.trigger_id's own contract
    # (domain.py) says "minted by CandidateStore", but TriggerScorer builds its own
    # f"trig-{gene_id}-{start}-{length}" string directly. Harmless while nothing
    # outside its own tests constructed one; fixed here, at the point this is first
    # exposed in a real run, rather than by touching triggers.py's tested code.
    # Window provenance (offset) is recorded on the candidate result instead of the ID.
    candidates = [dataclasses.replace(c, trigger_id=store.mint_id("trig")) for c in scored]

    windows_considered = sum(
        len(sequence) - length + 1
        for length in constraints.trigger_lengths
        if length <= len(sequence)
    )
    if not candidates:
        return [], [
            f"The pasted sequence is {len(sequence)} nt; none of its "
            f"{windows_considered} possible trigger window(s) survived screening "
            "(restriction sites, homopolymers, or extreme GC content). See "
            "docs/triggers.md."
        ]
    return candidates, [
        f"The pasted sequence is {len(sequence)} nt, longer than one trigger window "
        f"(up to {max_window} nt) — scanned {windows_considered} window(s) and kept "
        f"{len(candidates)} candidate(s) after screening. Exact 30/33/36-nt footprints "
        "were ranked within footprint buckets by selected joint P8, then RNAplfold "
        "terminal-20 opening energy and mean marginal openness; buckets were unioned "
        "round-robin."
    ]


def _de_trigger(
    request: JobRequest,
    store: CandidateStore,
    profiler: FoldProfiler,
    folder: FoldEngine,
    screener: MotifScreener,
    constraints: Constraints,
    host: Host,
) -> tuple[list[TriggerCandidate], list[str]]:
    """Resolve trigger candidates for a `de` submission (docs/genes.md, docs/ROADMAP.md
    Q1's first answer) — a scoped first cut, not the full `de` pipeline docs/ROADMAP.md
    E2 describes. Reuses everything already built for `direct` mode rather than adding a
    second implementation of anything: this module's own ``TriggerScorer.score`` call is
    identical in shape to ``_direct_trigger``'s scanned-paste branch, just fed real genes
    instead of one synthetic one.

    What this does, in order:
        1. Re-verify the dataset's checksum and parse it (``engine.inputs.parse_dge_table``)
           — the engine trusts nothing the Platform already checked, the same discipline
           ``_direct_trigger`` applies to a pasted sequence.
        2. Load the bundled reference transcriptome for ``host`` (``engine.transcriptome``
           — *E. coli* and yeast today, not human; anything unbundled raises before any
           work happens, rather than silently producing an empty shortlist).
        3. ``GeneSelector.select`` the shortlist, degrading gracefully on every axis it
           cannot measure — there is no count matrix here (docs/genes.md §3 G-a), so
           percentiles, the abundance window and non-redundancy are all unmeasured on
           every run through this path today; only separation and trigger yield apply.
        4. ``TriggerScorer.score`` across every selected gene's real transcript — the
           same call ``_direct_trigger`` already makes for one synthetic gene, extended
           to however many ``GeneSelector`` kept. Each design that comes out of this
           still becomes its own one-gene circuit downstream (this module's own
           docstring) — selecting several genes here is not a multi-gene Boolean
           circuit, just several independent single-input switches to choose from.

    Returns:
        The candidate trigger(s), ranked best first, and warnings describing how they
        were chosen — mirroring ``_direct_trigger``'s "empty candidates with a
        non-empty warning is a valid, reported outcome" convention rather than raising.

    Raises:
        InputValidationError: ``host`` has no bundled reference transcriptome, the
            dataset file cannot be read or parsed, or ``GeneSelector`` finds the input
            unusable outright (an empty table, or every candidate gene missing from the
            transcriptome — docs/genes.md §3 G-d).
        ChecksumMismatchError: the dataset file does not match the checksum recorded at
            submission time.
    """
    _validate_scanned_trigger_lengths(constraints)
    if host not in available_hosts():
        raise InputValidationError(
            f"Differential-expression input is only supported for "
            f"{', '.join(sorted(h.value for h in available_hosts()))} today — no "
            f"reference transcriptome is bundled for {host.value}. See "
            "docs/ROADMAP.md Q1."
        )

    path = Path(request.input_path)
    if not path.is_file():
        raise InputValidationError("The submitted dataset could not be read.")
    raw = path.read_bytes()
    if request.input_checksum and sha256_bytes(raw) != request.input_checksum:
        raise ChecksumMismatchError(
            "The dataset does not match the checksum recorded at submission."
        )

    dge = parse_dge_table(raw, path.name)
    transcriptome = load_transcriptome(host)

    warnings: list[str] = []
    selector = GeneSelector(constraints, screener)
    genes = selector.select(dge, sequences=transcriptome, on_warning=warnings.append)
    if not genes:
        return [], [
            *warnings,
            "No gene passed stage 1's filters — nothing to design a switch against.",
        ]

    # Every gene GeneSelector kept is guaranteed present in `transcriptome` (it drops,
    # and warns about, any gene missing from `sequences` itself) — safe to reuse the
    # same dict rather than building a second, smaller one.
    scorer = TriggerScorer(profiler, screener, folder)
    scored = list(scorer.score(genes, transcriptome, constraints))
    # Re-mint through CandidateStore, matching _direct_trigger's own note: trigger_id
    # is "minted by CandidateStore" per domain.py's contract, but TriggerScorer builds
    # its own id string directly.
    candidates = [dataclasses.replace(c, trigger_id=store.mint_id("trig")) for c in scored]

    if not candidates:
        return [], [
            *warnings,
            f"{len(genes)} gene(s) passed selection, but none of their scanned "
            "trigger windows survived screening (restriction sites, homopolymers, or "
            "extreme GC content). See docs/triggers.md.",
        ]

    best = genes[0]
    # Always present on this path — GeneSelector reads it off the DGE table and filters
    # on it — but the field is Optional for `direct`'s sake, so this does not assume.
    best_effect = "n/a" if best.log2_fold_change is None else f"{best.log2_fold_change:.2f}"
    return candidates, [
        *warnings,
        f"Selected {len(genes)} gene(s) from the differential-expression table (best: "
        f"{best.symbol or best.gene_id}, log2FC={best_effect}); scanned "
        f"their real transcripts and kept {len(candidates)} candidate trigger "
        "window(s) after screening. Exact footprints were ranked within footprint "
        "buckets by selected joint P8, terminal-20 opening energy and mean marginal "
        "openness, then unioned round-robin.",
    ]


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


def _multi_gate_candidates(
    single_gate: list[tuple[GateDesign, dict[str, float | None], float]],
    trigger_candidates: list[TriggerCandidate],
    constraints: Constraints,
    profile: ScoringProfile,
    plasmid_builder: PlasmidBuilder,
    store: CandidateStore,
    outcomes: list[DesiredOutcome],
    custom_sequence: str | None,
    families_by_kind: dict,
) -> Iterator[tuple[CandidateResult, PlasmidDesign, float | None]]:
    """Stage 4 — circuits that combine more than one gene, and their plasmids.

    Additive on purpose. Every one-gene candidate the loop above produced is still
    yielded unchanged; this adds the longer circuits alongside them, so raising
    ``max_circuit_gates`` widens the menu rather than replacing it. A researcher who
    sets it to 1 gets exactly what this engine produced before stage 4 existed.

    Why a circuit's metrics are its *worst* member's:
        A circuit is only as good as the weakest switch in it. Taking each metric's
        worst value across the member designs — worst by that metric's own declared
        direction, not by magnitude — means a two-gate circuit can never score better
        than either gate alone on any axis, which is the honest answer: adding a
        component cannot improve the thermodynamics of the one already there.

        ``circuit_complexity`` is the exception, and the one that makes a longer circuit
        actually cost something: it comes from the circuit's own
        ``BooleanExpression.complexity()`` rather than from any member, so it rises with
        every gate and every ``NOT``.
    """
    if constraints.max_circuit_gates <= 1 or len(single_gate) < 2:
        return

    genes = _genes_for_circuits(trigger_candidates)
    if len(genes) < 2:
        return

    designer = CircuitDesigner(ConfusionEvaluator(), max_terms=constraints.max_circuit_gates)
    # Best-first, so CircuitDesigner.design's "first design per gene" rule picks each
    # gene's strongest switch (its own docstring explains why the choice is the
    # caller's to make through ordering).
    ordered = [design for design, _raw, _score in sorted(single_gate, key=_by_score_desc)]
    raw_by_design = {design.design_id: raw for design, raw, _score in single_gate}

    # No per-sample counts exist in this product (docs/genes.md §3 G-a), so the
    # confusion matrix stays unmeasured — CircuitDesigner.design's own docstring says
    # what that means and what fills it once a count matrix does exist.
    empty_counts = CountMatrix(
        gene_ids=(),
        samples=(),
        counts=(),
        metadata=SampleMetadata(control_samples=(), condition_samples=()),
    )
    for index, circuit in enumerate(designer.design(genes, ordered, empty_counts)):
        if len(circuit.expression.gene_ids()) < 2:
            # The one-gene forms were already produced, and scored, above.
            continue

        outcome = outcomes[index % len(outcomes)]
        raws = [raw_by_design[design.design_id] for design in circuit.designs]
        raw = _worst_metrics(raws, profile)
        raw["circuit_complexity"] = float(circuit.complexity)

        metrics = build_metrics(raw, profile)
        breach = failed_filter(raw, profile)

        built = dataclasses.replace(circuit, circuit_id=store.mint_id("circ"), output=outcome.value)
        plasmid = (
            plasmid_builder.build(built, outcome, custom_payload=custom_sequence)
            if outcome is DesiredOutcome.CUSTOM
            else plasmid_builder.build(built, outcome)
        )
        family = families_by_kind[circuit.designs[0].gate_kind]
        candidate = _circuit_candidate_result(
            store, built, family, metrics, breach, plasmid, outcome
        )
        yield candidate, plasmid, None if breach else weighted_score(metrics, profile)


def _by_score_desc(entry: tuple[GateDesign, dict[str, float | None], float]):
    """Highest score first, ties broken by design id so the order is total."""
    design, _raw, score = entry
    return (-score, design.design_id)


def _genes_for_circuits(trigger_candidates: list[TriggerCandidate]) -> list[SelectedGene]:
    """The genes behind these triggers, as stage 4 needs them.

    Rebuilt from the trigger candidates rather than threaded down from stage 1, because
    a ``TriggerCandidate`` already carries everything a circuit needs to know about its
    gene — the id, the symbol and the effect size — and the direction follows from the
    sign of that effect size (``DgeRow.regulation`` derives it the same way).

    One entry per gene, not per trigger: scanning can yield many windows from one
    transcript, and they are all the same circuit input.
    """
    genes: dict[str, SelectedGene] = {}
    for trigger in trigger_candidates:
        if trigger.gene_id in genes or trigger.log2_fold_change is None:
            # No effect size means no direction, and a `direct` submission has none —
            # there is nothing to orient a NOT gate by, so it cannot join a circuit.
            continue
        genes[trigger.gene_id] = SelectedGene(
            gene_id=trigger.gene_id,
            symbol=trigger.symbol,
            regulation=(Regulation.UP if trigger.log2_fold_change >= 0 else Regulation.DOWN),
            log2_fold_change=trigger.log2_fold_change,
            score=trigger.score,
        )
    return list(genes.values())


def _worst_metrics(
    raws: list[dict[str, float | None]], profile: ScoringProfile
) -> dict[str, float | None]:
    """Each metric's worst value across a circuit's member designs.

    "Worst" is by the metric's own declared direction: the lowest value for a
    higher-is-better metric, the highest for a lower-is-better one. A metric any member
    could not measure stays ``None`` for the circuit too — one unmeasured switch makes
    the circuit's figure unmeasured, not the best of what is left.
    """
    worst: dict[str, float | None] = {}
    for name in {key for raw in raws for key in raw}:
        values = [raw.get(name) for raw in raws]
        if any(value is None for value in values):
            worst[name] = None
            continue
        spec = profile.spec(name)
        if spec is None:
            # Stored, not scored (CLAUDE.md §2) — no direction to pick a worst by, so
            # report the first member's rather than inventing an ordering.
            worst[name] = values[0]
            continue
        worst[name] = min(values) if spec.direction == HIGHER_BETTER else max(values)
    return worst


def _circuit_candidate_result(
    store: CandidateStore,
    circuit: CircuitCandidate,
    family: GateFamily,
    metrics: list[MetricValue],
    breach: HardFilter | None,
    plasmid: PlasmidDesign,
    outcome: DesiredOutcome,
) -> CandidateResult:
    """A multi-gene circuit shaped as a ``CandidateResult`` the Platform can import.

    The same record a one-gene candidate uses, with the parts that are genuinely plural
    carrying every member rather than only the first:

    * ``triggers["features"]`` — one entry per member gene. The field was always a list;
      a one-gene circuit simply only ever put one thing in it.
    * ``plasmid_segments`` — the real construct, which ``PlasmidBuilder`` already lays
      out as a promoter/switch pair per switch plus one shared payload and terminator.
    * ``logic_graph`` — the real Boolean structure from ``CircuitDesigner``, not the
      one-gene placeholder.

    ``design["switch_sequence"]`` stays the *primary* switch, because the field is
    singular in the contract and a concatenation of several switches would read as one
    molecule that nobody is building. ``component_switches`` carries all of them, so a
    consumer that wants every sequence has it without the singular field lying.
    """
    logic_graph = {
        "genes": [
            {
                "name": gene.name,
                "role": gene.role,
                "state": gene.state.value,
                "direction": gene.direction.value,
            }
            for gene in circuit.logic_graph.genes
        ],
        "mid_gate": circuit.logic_graph.mid_gate.value,
        "outer_gate": circuit.logic_graph.outer_gate.value,
        "invert": circuit.logic_graph.invert,
        "output": outcome.display_name,
        "caption": f"{circuit.logic_graph.caption} -> {outcome.display_name}",
    }
    triggers = [
        trigger
        for design in circuit.designs
        for trigger in (design.trigger_set.activators + design.trigger_set.repressors)
    ]
    primary = circuit.designs[0]
    return CandidateResult(
        ref=store.mint_id("cand"),
        rank=None,
        overall_score=None,
        gate_family=family.name,
        logic_type=circuit.expression.render(),
        triggers={"features": [_trigger_feature(trigger) for trigger in triggers]},
        design={
            "switch_sequence": primary.sequence,
            "structure": primary.dot_bracket,
            "toehold_length": primary.architecture.get("toehold_length", 0),
            "sequence_length_bp": plasmid.plasmid.length_bp,
            "plasmid_segments": [
                {"kind": segment.kind.value, "name": segment.name, "length_bp": segment.length_bp}
                for segment in plasmid.plasmid.segments
            ],
            "logic_graph": logic_graph,
            "trigger_start_index": triggers[0].start_index if triggers else 0,
            "component_switches": [
                {"design_id": design.design_id, "switch_sequence": design.sequence}
                for design in circuit.designs
            ],
        },
        summary=(
            f"{len(circuit.designs)}-gate circuit: {circuit.expression.render()} "
            f"-> {outcome.display_name}"
        ),
        metrics=metrics,
        warnings=tuple(f"Assembly standard: {v}" for v in plasmid.violations),
        is_rejected=breach is not None,
        rejection_reason=breach.reason if breach else "",
    )


def _trigger_feature(trigger: TriggerCandidate) -> dict:
    """One trigger as the Platform's ``triggers["features"]`` entry.

    Extracted so the single-gene and multi-gene circuit paths describe a trigger
    identically — a circuit's features list is this, once per member gene.
    """
    return {
        "feature_id": trigger.symbol,
        "sequence": trigger.sequence,
        "openness": trigger.openness,
        "accessibility": trigger.accessibility,
        "selection_method": (
            TriggerScorer.SELECTION_METHOD
            if trigger.gate_toehold_length is not None
            else TriggerScorer.LEGACY_SELECTION_METHOD
        ),
        "selection_metric": (
            "selected_joint_p8"
            if trigger.gate_toehold_length is not None
            else "mean_base_unpaired_probability"
        ),
        "selection_score": trigger.score,
        "orientation": "transcript_forward",
        "gate_toehold_length": trigger.gate_toehold_length,
        "hypothesis_start": trigger.hypothesis_start,
        "hypothesis_end": trigger.hypothesis_end,
        "joint_open_probability_20": trigger.joint_open_probability_20,
        "mean_marginal_openness_20": trigger.mean_marginal_openness_20,
        "delta_g_open_kcal_per_mol_per_nt": (trigger.delta_g_open_kcal_per_mol_per_nt),
        "selected_seed_start": trigger.selected_seed_start,
        "selected_seed_end": trigger.selected_seed_end,
        "selected_seed_probability": trigger.selected_seed_probability,
        "seed_trials": [
            {
                "start": trial.start,
                "end": trial.end,
                "relative_start": trial.relative_start,
                "sequence": trial.sequence,
                "joint_probability": trial.probability,
            }
            for trial in trigger.seed_trials
        ],
        "rnaplfold": {
            "viennarna_version": trigger.rnaplfold_version,
            "window": trigger.rnaplfold_window,
            "max_span": trigger.rnaplfold_max_span,
            "unpaired": trigger.rnaplfold_unpaired,
            "temperature_celsius": trigger.rnaplfold_temperature_celsius,
        },
        # Which window this candidate came from (docs/triggers.md T2) —
        # 0 for the single-trigger fast path, a real scanned offset
        # otherwise. Makes a chosen window inspectable rather than a
        # black box when more than one was considered.
        "start_index": trigger.start_index,
    }


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
        triggers={"features": [_trigger_feature(trigger)]},
        design={
            "switch_sequence": design.sequence,
            "structure": design.dot_bracket,
            "toehold_length": design.architecture.get("toehold_length", 0),
            # The whole construct, not the switch alone - matches
            # convention (client.py) and Plasmid.length_bp's own definition. The
            # frontend's PlasmidRing draws arcs proportional to this against
            # plasmid_segments, so a switch-only value here makes every arc but the
            # switch's own overflow past 360 degrees.
            "sequence_length_bp": plasmid.plasmid.length_bp,
            "plasmid_segments": plasmid_segments,
            "logic_graph": logic_graph,
            "trigger_start_index": trigger.start_index,
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
    """A design table, and — only once the safety gate releases — a FASTA, a GenBank
    and an SBOL document per accepted candidate (docs/plasmids.md, E5a; ADR 0008).

    The sequence-bearing exports sit below the release check deliberately: with no
    local screening adapter provisioned, ``fail_closed_release`` holds every sequence
    and this writes the design table and the audit manifests alone.

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
        plasmid = plasmids[candidate.ref]
        switch_screen = fail_closed_release(
            f"{candidate.ref}:switch",
            candidate.design["switch_sequence"],
            host_context="unconfigured",
        )
        plasmid_screen = fail_closed_release(
            f"{candidate.ref}:plasmid", plasmid.plasmid.sequence, host_context="unconfigured"
        )
        artifacts.extend(
            [
                write_artifact(
                    output_dir,
                    f"safety/{candidate.ref}-switch.json",
                    json.dumps(switch_screen.audit_manifest(), indent=2, sort_keys=True) + "\n",
                    kind="safety_audit",
                    media_type="application/json",
                    candidate_ref=candidate.ref,
                ),
                write_artifact(
                    output_dir,
                    f"safety/{candidate.ref}-plasmid.json",
                    json.dumps(plasmid_screen.audit_manifest(), indent=2, sort_keys=True) + "\n",
                    kind="safety_audit",
                    media_type="application/json",
                    candidate_ref=candidate.ref,
                ),
            ]
        )
        if not (switch_screen.release_allowed and plasmid_screen.release_allowed):
            continue
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
                to_genbank(plasmid),
                kind="genbank",
                media_type="text/plain",
                candidate_ref=candidate.ref,
            )
        )
        # SBOL 3 alongside GenBank (ADR 0008). Deliberately inside this block, below the
        # release check above: an SBOL document carries the full construct sequence, so
        # emitting it before the gate would hand out exactly what the gate withholds.
        artifacts.append(
            write_artifact(
                output_dir,
                f"sbol/{candidate.ref}.nt",
                to_sbol3(plasmid),
                kind="sbol",
                media_type="application/n-triples",
                candidate_ref=candidate.ref,
            )
        )

    return artifacts
