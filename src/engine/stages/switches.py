"""Stage 3 — switch design and validation.

Where triggers become actual constructs. For each combination of triggers, and each gate
chemistry that supports the host, a generator builds candidate switches; a validator then
checks each one folds as intended and obeys the hard sequence rules.

The split matters. **Generation is chemistry-specific** and lives in the gate families —
a toehold and a CRISPR gate share nothing about how they are built. **Validation is
common** and lives here, so every chemistry is held to the same standard and a rule is
fixed in one place rather than three.
"""

import dataclasses
import math
from collections.abc import Callable, Iterable, Iterator
from itertools import combinations
from math import comb

from engine import sequences as sq
from engine.domain import (
    Constraints,
    GateDesign,
    Host,
    TriggerCandidate,
    TriggerSet,
    ValidationResult,
)
from engine.errors import JobCancelled
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.stages.motifs import MotifScreener


class SwitchDesigner:
    """Dispatches trigger sets to the gate families that can realise them.

    Owns no chemistry. Adding a family changes nothing in this class — that is the point
    of the ``GateFamily`` interface.

    Args:
        families: Instantiated gate families, already given their tools. Only those
            supporting ``host`` will be used; filter with ``family.supports(host)``
            rather than assuming the caller did.
        validator: The shared validator every design passes through.
        host: The organism. Decides which families apply — CRISPR is eukaryotic only.
    """

    def __init__(self, families: list, validator: "SwitchValidator", host: Host) -> None:
        self.families = families
        self.validator = validator
        self.host = host

    def design(
        self,
        triggers: Iterable[TriggerCandidate],
        constraints: Constraints,
        *,
        on_incompatible: Callable[[str], None] | None = None,
        on_invalid: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int], bool] | None = None,
    ) -> Iterator[GateDesign]:
        """Yield validated switch designs.

        Args:
            triggers: Stage 2's ranked candidates, already pruned.
            constraints: ``max_triggers`` bounds the arity; ``max_switch_length`` and
                ``standard`` are enforced by the validator.
            on_incompatible: Optional. Called with ``Compatibility.reason`` every time a
                trigger set is skipped for a family, instead of the reason being silently
                dropped (docs/triggers.md T3). One call per skipped ``(trigger_set,
                family)`` pair — a different unit than ``on_invalid`` below, so callers
                that aggregate should keep the two counts separate rather than summing
                them into one total.
            on_invalid: Optional. Called once per string in a failing design's
                ``ValidationResult.violations``, instead of the violations being silently
                dropped. One call per violation *of a generated design* — many designs
                can come from one trigger set (one per swept toehold length), so this is
                a finer-grained count than ``on_incompatible``'s.

        Yields:
            ``GateDesign`` for every candidate that passes validation, with its measured
            values attached. Rejected designs are **not** yielded here — a design that
            fails a hard structural rule is not a candidate, it is a construction error.
            (Contrast with stage 4, where a *circuit* that fails a scoring filter is kept
            with its reason, because the researcher may want to see it.)

        The loop (Step 5):
            for each trigger set from ``build_trigger_sets``:
                for each family where ``family.supports(self.host)``:
                    ask ``family.is_compatible(trigger_set, constraints)`` — cheap
                    checks, skip the family if it says no and record why;
                    for each design from ``family.generate_designs(...)``:
                        ``validator.validate(design)``; if it passes, measure it with
                        ``family.evaluate_design(design)`` and yield.

        Order matters for cost:
            ``is_compatible`` is cheap and ``generate_designs`` is not; validation folds
            and is the expensive part. Reject as early as the information allows.

        Cancellation:
            This stage dominates runtime. The caller's ``on_progress`` must be checked
            **between batches** here, not only when the stage begins, or a cancelled run
            keeps computing for minutes.

        Note on "measure it" above:
            ``evaluate_design`` is deliberately **not** called from here. ``GateDesign``
            has no field to carry a full raw-metric dict (CLAUDE.md §3's own nine-metric
            vocabulary lives one layer up, in ``engine.scoring``), so folding every
            design here and discarding the numbers just to fold it again for real
            scoring would be pure waste with no compensating benefit. The caller —
            ``run_pipeline`` today, ``CircuitDesigner`` once stage 4 exists — calls
            ``evaluate_design`` exactly once per surviving design, the same pattern
            the scoring layer already uses.
        """
        pool = list(triggers)
        arities = {family.max_inputs for family in self.families if family.supports(self.host)}
        total = sum(comb(len(pool), arity) for arity in arities if arity <= len(pool))
        completed = 0
        effective = dataclasses.replace(
            constraints, max_triggers=min(constraints.max_triggers, max(arities, default=1))
        )
        for index, trigger_set in enumerate(self.build_trigger_sets(pool, effective)):
            active = trigger_set.arity in arities
            if on_progress is not None and (active or index % 100 == 0):
                if not on_progress(completed, total):
                    raise JobCancelled("Designing switches")
            if active:
                completed += 1
            for family in self.families:
                if not family.supports(self.host):
                    continue

                compatibility = family.is_compatible(trigger_set, constraints)
                if not compatibility.ok:
                    if on_incompatible:
                        on_incompatible(compatibility.reason)
                    continue

                for design in family.generate_designs(trigger_set, constraints):
                    result = self.validator.validate(design)
                    if result.ok:
                        yield dataclasses.replace(
                            design, structure_deviation=result.structure_deviation
                        )
                    elif on_invalid:
                        for violation in result.violations:
                            on_invalid(violation)

    def build_trigger_sets(
        self, triggers: Iterable[TriggerCandidate], constraints: Constraints
    ) -> Iterator[TriggerSet]:
        """Combine individual triggers into the input sets a circuit can use.

        Args:
            triggers: Ranked candidates.
            constraints: ``max_triggers`` caps the arity. 2 is the practical ceiling —
                see the note on cost below.

        Yields:
            ``TriggerSet``, singletons first, then pairs, and so on.

        Rules:
            * **Two triggers may come from the same gene.** The pipeline map is explicit:
              "2 inputs can be of the same gene or trigger". Two accessible windows on
              one transcript are a legitimate AND design, so this must not deduplicate by
              ``gene_id``. It is an easy and invisible mistake.
            * **Do not pair overlapping windows** from the same transcript — they cannot
              be bound simultaneously.
            * Activators come from UP-regulated genes, repressors from DOWN-regulated
              ones, but stage 4 decides the final logic. This stage only proposes —
              ``TriggerCandidate`` itself carries no up/down field (that lives on
              ``SelectedGene``, stage 1's output, which this stage does not receive), so
              every trigger handed in is treated as a potential activator. Repressor
              sets are stage 4's to build once it exists.

        Cost:
            Pairs grow as the square of the input. 50 triggers gives 1,225 pairs; 200
            gives 19,900, and each is multiplied by the number of designs per family.
            This is exactly why stage 2 prunes hard — see docs/ROADMAP.md §3. Triples are
            not generated even when ``constraints.max_triggers`` allows them — Q3
            (docs/ROADMAP.md §2) has not set a ceiling above 2, and 2 is documented
            elsewhere as the practical limit before the search space becomes
            intractable without a cluster.
        """
        pool = list(triggers)

        for trigger in pool:
            down = trigger.log2_fold_change is not None and trigger.log2_fold_change < 0
            yield (
                TriggerSet(activators=(), repressors=(trigger,))
                if down
                else TriggerSet(activators=(trigger,))
            )

        if constraints.max_triggers < 2:
            return

        for first, second in combinations(pool, 2):
            if first.gene_id == second.gene_id and _windows_overlap(first, second):
                continue
            members = (first, second)
            yield TriggerSet(
                activators=tuple(
                    t for t in members if t.log2_fold_change is None or t.log2_fold_change >= 0
                ),
                repressors=tuple(
                    t for t in members if t.log2_fold_change is not None and t.log2_fold_change < 0
                ),
            )


def _windows_overlap(a: TriggerCandidate, b: TriggerCandidate) -> bool:
    """True when two same-transcript windows share any position — they cannot be bound
    simultaneously, so they cannot be paired into one trigger set."""
    a_end = a.start_index + a.length
    b_end = b.start_index + b.length
    return a.start_index < b_end and b.start_index < a_end


class SwitchValidator:
    """The hard rules a switch must obey, whichever family produced it.

    Deliberately outside the gate families. Three chemistries each implementing "no
    in-frame stop codons" is three chances to implement it slightly differently, and a
    rule fixed in one of them stays broken in the other two.

    These are **pass/fail rules**, not scored metrics. A switch with a premature stop
    codon does not score badly — it does not work at all, and there is nothing to
    compare it against.

    Args:
        folder: Shared ``FoldEngine``, for structural checks.
        screener: Shared ``MotifScreener``, for assembly-standard compliance.
        translation: Shared ``TranslationScorer``, for the initiation checks.
        constraints: The run's limits. ``max_switch_length`` comes from here, never a
            module-level literal — CLAUDE.md §3 is explicit that an undeclared numeric
            cutoff is an invisible per-family filter that makes candidate pools
            incomparable across runs.
    """

    def __init__(
        self,
        folder: FoldEngine,
        screener: MotifScreener,
        translation: TranslationScorer,
        constraints: Constraints,
    ) -> None:
        self.folder = folder
        self.screener = screener
        self.translation = translation
        self.constraints = constraints

    def validate(self, design: GateDesign) -> ValidationResult:
        """Check one design against every hard rule this stage can currently apply.

        Args:
            design: A freshly generated switch.

        Returns:
            ``ValidationResult(ok, violations)``. **Collects every violation**, does not
            return on the first — a generator being tuned is far easier to fix when it
            reports all its problems at once.

        Implemented, cheapest first — all four are string operations, no folding:
            * **Length.** Within ``self.constraints.max_switch_length``.
            * **No prohibited motifs.** ``screener.violations`` — restriction sites for
              the chosen standard, and homopolymers over the limit.
            * **Exactly one AUG**, and **zero in-frame STOP codons** downstream of it —
              ``sequences.find_augs``/``find_stops``, in the frame ``design.architecture``
              declares via ``"aug_index"``. A family whose ``architecture`` carries no
              ``aug_index`` is a chemistry with no embedded start codon of its own (an
              antisense design silences post-transcriptionally rather than being
              translated itself — its ``architecture`` has no ``aug_index`` key at all),
              and both rules are skipped for it rather than guessed.

        Target syntax and length are required. Ensemble defect is measured as a
        length-normalized fraction after cheap sequence checks pass; no biological
        threshold is asserted because switching efficacy has not been calibrated.
        """
        violations: list[str] = []

        if len(design.sequence) > self.constraints.max_switch_length:
            violations.append(
                f"switch is {len(design.sequence)} nt, over the "
                f"{self.constraints.max_switch_length} nt limit"
            )

        try:
            self.folder.validate_target(design.sequence, design.dot_bracket)
        except ValueError as exc:
            violations.append(str(exc))

        violations.extend(str(site) for site in self.screener.violations(design.sequence))

        aug_index = design.architecture.get("aug_index")
        if aug_index is not None:
            augs = sq.find_augs(design.sequence)
            if len(augs) != 1:
                violations.append(f"expected exactly one AUG, found {len(augs)} at {list(augs)}")

            stops = sq.find_stops(design.sequence, frame=aug_index)
            if stops:
                violations.append(f"in-frame stop codon(s) at {list(stops)}")

        if violations:
            return ValidationResult.failed(*violations)
        defect = self.folder.ensemble_defect(design.sequence, design.dot_bracket) / len(
            design.sequence
        )
        if not math.isfinite(defect) or not 0 <= defect <= 1:
            return ValidationResult.failed(
                "Normalized ensemble defect is nonfinite or outside [0, 1]."
            )
        return ValidationResult(ok=True, structure_deviation=defect)


def run_endogenous_crispr(config: dict, folder: FoldEngine, on_progress=None) -> dict:
    """Run the explicit-input research workbench independently of the application pipeline.

    External scores are required, keyed by genomic/transcript coordinates. Missing
    or invalid scores are input errors detected before folding begins.
    """
    import json
    import math
    from dataclasses import asdict, fields, replace
    from tempfile import TemporaryFile

    from engine import sequences as sq
    from engine.domain import CrisprObjective, CrisprObservables, CrisprTemplate
    from engine.gates.crispr import CrisprGate, scan_spacers
    from engine.scoring.crispr import (
        calibrate_scale,
        inner_objective,
        measurement_rejections,
        outer_objective,
        validate_objective,
    )

    if not isinstance(config, dict):
        raise ValueError("CRISPR input must be a JSON object")
    required = (
        "scaffold",
        "scaffold_reference",
        "target_dna",
        "activation_window",
        "transcripts",
        "templates",
        "objective",
        "spacer_metrics",
        "trigger_metrics",
        "score_source",
        "calibration_source",
    )
    missing = [key for key in required if config.get(key) is None]
    if missing:
        raise ValueError("Missing required inputs: " + ", ".join(missing))
    for key in ("objective", "transcripts", "spacer_metrics", "trigger_metrics"):
        if not isinstance(config[key], dict):
            raise ValueError(f"{key} must be an object")
    for key in ("target_dna", "scaffold", "scaffold_reference"):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"{key} must be a non-empty string")
    window = config["activation_window"]
    if (
        not isinstance(window, (list, tuple))
        or len(window) != 2
        or any(type(value) is not int for value in window)
    ):
        raise ValueError("activation_window must contain two integer coordinates [start, end)")
    temperature = folder.temperature
    if (
        type(temperature) not in (int, float)
        or not math.isfinite(temperature)
        or temperature <= -273.15
    ):
        raise ValueError("temperature_c must be finite and above absolute zero")
    if not isinstance(config["templates"], (list, tuple)) or any(
        not isinstance(t, dict) for t in config["templates"]
    ):
        raise ValueError("templates must be an array of objects")
    for identifier, sequence in config["transcripts"].items():
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("transcripts must have non-empty string identifiers")
        if not isinstance(sequence, str):
            raise ValueError(f"transcripts[{identifier}] must be a sequence string")
    for key in ("score_source", "calibration_source"):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"{key} must describe the source; use synthetic for a toy demo")
    if "scale_lambda" in config["objective"]:
        raise ValueError("Remove scale_lambda: it is computed from the ranking batch")
    if "spacer_score_mode" in config["objective"]:
        raise ValueError("Remove spacer_score_mode: Q_S now uses the specificity formula only")
    try:
        objective = CrisprObjective(**config["objective"])
    except TypeError as exc:
        raise ValueError(f"Invalid objective fields: {exc}") from exc
    validate_objective(objective)
    if any("loop" in t for t in config["templates"]):
        raise ValueError("Remove template.loop: loop sequence is derived from the trigger")
    try:
        templates = tuple(CrisprTemplate(**t) for t in config["templates"])
    except TypeError as exc:
        raise ValueError(f"Invalid template fields: {exc}") from exc
    if not templates or not config["scaffold_reference"]:
        raise ValueError("Non-empty templates and scaffold reference required")
    stride, top_k = config.get("trigger_stride", 1), config.get("top_k", 10)
    max_pairs = config.get("max_pairs", 1000)
    max_length = config.get("max_switch_length", 200)
    audit_limit = config.get("guide_audit_limit", 1000)
    if type(audit_limit) is not int or audit_limit < 0:
        raise ValueError("guide_audit_limit must be a nonnegative integer")
    for name, value in (
        ("trigger_stride", stride),
        ("top_k", top_k),
        ("max_pairs", max_pairs),
        ("max_switch_length", max_length),
    ):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if "guide_molar" in config or "trigger_molar" in config:
        raise ValueError(
            "Remove guide_molar/trigger_molar: ON now uses the connected gT ensemble, "
            "not a concentration-weighted tube"
        )
    if config.get("host", "human") not in ("human", "yeast"):
        raise ValueError("host must be human or yeast")
    host = Host.HUMAN if config.get("host", "human") == "human" else Host.YEAST
    constraints = Constraints(max_switch_length=max_length)
    gate_kwargs = {
        "scaffold": config["scaffold"],
        "scaffold_reference": config["scaffold_reference"],
        "templates": templates,
    }
    # Validate architecture even when target scan finds no spacers.
    CrisprGate(host, folder, **gate_kwargs)
    spacers = scan_spacers(config["target_dna"], tuple(config["activation_window"]))
    windows = []
    if not isinstance(config["transcripts"], dict) or not config["transcripts"]:
        raise ValueError("transcripts must map identifiers to RNA sequences")
    for transcript_id, sequence in sorted(config["transcripts"].items()):
        rna = sq.to_rna(sequence)
        if not sq.is_valid_rna(rna):
            raise ValueError(f"Invalid transcript {transcript_id}")
        for length in sorted({t.trigger_length for t in templates}):
            for start, window in sq.windows(rna, length, stride):
                windows.append(
                    {
                        "id": f"{transcript_id}:{start}:{length}",
                        "transcript_id": transcript_id,
                        "start": start,
                        "length": length,
                        "sequence": window,
                    }
                )
    if len(spacers) * len(windows) > max_pairs:
        raise ValueError(
            "Search exceeds max_pairs; narrow the input or explicitly raise the budget"
        )
    # Validate every supplied score and coverage before starting any candidate fold.
    for name, metrics, keys in (
        ("spacer_metrics", config["spacer_metrics"], ("eta_on", "eta_off")),
        ("trigger_metrics", config["trigger_metrics"], ("q_trigger",)),
    ):
        for identifier, values in metrics.items():
            if not isinstance(identifier, str) or not identifier or not isinstance(values, dict):
                raise ValueError(f"{name} must map non-empty identifiers to score objects")
            for key in keys:
                value = values.get(key)
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not 0 <= value <= 1
                ):
                    raise ValueError(f"{name}[{identifier}].{key} must be a finite number in [0,1]")
            if name == "trigger_metrics" and values.get("accessibility") is not None:
                value = values["accessibility"]
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not 0 <= value <= 1
                ):
                    raise ValueError(
                        f"trigger_metrics[{identifier}].accessibility must be in [0,1]"
                    )
    if spacers and windows:
        for name, candidates in (("spacer_metrics", spacers), ("trigger_metrics", windows)):
            missing_ids = [item["id"] for item in candidates if item["id"] not in config[name]]
            if missing_ids:
                preview = ", ".join(missing_ids[:5])
                raise ValueError(f"Missing {name} for {len(missing_ids)} candidates: {preview}")
    pairs, audit = [], []
    evaluated_guides = 0
    rejection_counts = {}
    measurement_failure_counts = {}
    measurement_failures = 0
    threshold_rejected_guides = 0
    total = len(spacers) * len(windows)
    batch_count = 0
    with TemporaryFile(mode="w+t", encoding="utf-8") as spool:
        for spacer in spacers:
            for window in windows:
                pair_id = spacer["id"] + "|" + window["id"]
                if on_progress:
                    on_progress(len(pairs), total, pair_id)
                row = {
                    "pair_id": pair_id,
                    "spacer": spacer,
                    "trigger": window,
                    "rejections": [],
                    "j_best": None,
                    "phi": None,
                    "guide": None,
                    "measurement_failures": 0,
                    "measurement_errors": {},
                }
                pairs.append(row)
                sm = config["spacer_metrics"][spacer["id"]]
                tm = config["trigger_metrics"][window["id"]]
                precheck = outer_objective(
                    0.0, sm["eta_on"], sm["eta_off"], tm["q_trigger"], objective
                )
                if precheck["rejections"]:
                    row["rejections"].extend(precheck["rejections"])
                    continue
                gate = CrisprGate(host, folder, spacer=spacer["sequence"], **gate_kwargs)
                # Only accessibility is consumed from this adapter record. Other stage-2
                # measurements are unavailable, deliberately None, never fabricated zeros.
                trigger = TriggerCandidate(
                    trigger_id=window["id"],
                    gene_id=window["transcript_id"],
                    symbol=window["transcript_id"],
                    sequence=window["sequence"],
                    start_index=window["start"],
                    openness=None,
                    accessibility=tm.get("accessibility"),
                    mfe=None,
                    gc_content=sq.gc_content(window["sequence"]),
                )
                trigger_set = TriggerSet(activators=(trigger,))
                compatible = gate.is_compatible(trigger_set, constraints)
                if not compatible.ok:
                    row["rejections"].append(compatible.reason)
                    continue
                feasible_in_pair = 0
                row["evaluated_guides"] = 0
                for design in gate.generate_designs(trigger_set, constraints):
                    item = {
                        "pair_id": pair_id,
                        "design_id": design.design_id,
                        "guide": design.sequence,
                        "architecture": design.architecture,
                    }
                    measured = {field.name: None for field in fields(CrisprObservables)}
                    item.update(
                        observables=measured,
                        feasible=False,
                        j=None,
                        j_accessibility=None,
                        j_energy=None,
                        rejections=[],
                        evaluation_status="rejected",
                        measurement_error=None,
                    )
                    try:
                        for batch in gate.measurement_stages(design):
                            failures = measurement_rejections(batch, objective)
                            measured.update(batch)
                            if failures:
                                item["rejections"] = failures
                                break
                        else:
                            item["feasible"] = True
                            item["evaluation_status"] = "feasible"
                    except (ArithmeticError, ValueError) as exc:
                        reason = f"{type(exc).__name__}: {exc}"
                        item.update(
                            feasible=None,
                            j=None,
                            rejections=[],
                            evaluation_status="measurement_failed",
                            measurement_error=reason,
                        )
                        measurement_failures += 1
                        row["measurement_failures"] += 1
                        row["measurement_errors"][reason] = (
                            row["measurement_errors"].get(reason, 0) + 1
                        )
                        measurement_failure_counts[reason] = (
                            measurement_failure_counts.get(reason, 0) + 1
                        )
                    evaluated_guides += 1
                    row["evaluated_guides"] += 1
                    if item["feasible"] is False:
                        threshold_rejected_guides += 1
                    for reason in item["rejections"]:
                        rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    # Limit diagnostic retention only; EVERY candidate is still evaluated.
                    if len(audit) < audit_limit:
                        audit.append(item)
                    if item["feasible"]:
                        feasible_in_pair += 1
                        batch_count += 1
                        spool.write(json.dumps(item, allow_nan=False) + "\n")
                row["inner_feasible_guides"] = feasible_in_pair
                if feasible_in_pair == 0 and row["measurement_failures"] == 0:
                    row["rejections"].append(
                        "No feasible guide in the exhaustive binary-complement search"
                    )
        # A missing observation can change the global lambda and every winner.
        # Preserve diagnostic measurements, but never rank an incomplete batch.
        if batch_count and not measurement_failures:
            spool.seek(0)
            objective = replace(
                objective,
                scale_lambda=calibrate_scale(
                    (CrisprObservables(**json.loads(line)["observables"]) for line in spool),
                    objective.w_on,
                    objective.w_off,
                ),
            )
            # Score stored measurements only after the global batch scale is known.
            # Temporary storage avoids retaining all feasible guides in RAM or refolding.
            spool.seek(0)
            pair_rows = {row["pair_id"]: row for row in pairs}
            for line in spool:
                item = json.loads(line)
                scored = inner_objective(CrisprObservables(**item["observables"]), objective)
                row = pair_rows[item["pair_id"]]
                if row["j_best"] is None or scored["j"] > row["j_best"]:
                    row.update(
                        j_best=scored["j"],
                        guide=item["guide"],
                        architecture=item["architecture"],
                        observables=item["observables"],
                    )
            for item in audit:
                if item["feasible"]:
                    item.update(
                        **inner_objective(CrisprObservables(**item["observables"]), objective)
                    )
            for row in pairs:
                if row["j_best"] is not None:
                    sm = config["spacer_metrics"][row["spacer"]["id"]]
                    tm = config["trigger_metrics"][row["trigger"]["id"]]
                    row.update(
                        outer_objective(
                            row["j_best"], sm["eta_on"], sm["eta_off"], tm["q_trigger"], objective
                        )
                    )
    ranked = sorted(
        (r for r in pairs if not r["rejections"] and r["phi"] is not None),
        key=lambda r: (-r["phi"], not r["selectable"], r["pair_id"]),
    )
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
    selectable = [row for row in ranked if row["selectable"]]
    return {
        "status": (
            "measurement_incomplete"
            if measurement_failures
            else "ranked"
            if selectable
            else "no_positive_switch_candidates"
            if ranked
            else "no_feasible_candidates"
        ),
        "measurement_complete": measurement_failures == 0,
        "model": CrisprGate.ensemble_model,
        "gate_version": CrisprGate.version,
        "limitations": [
            "OFF is free g; ON is conditioned on connected gT structures",
            "No strand concentrations or prediction of the fraction bound in solution",
            "ON includes alternative connected folds; spacer opening is not imposed",
            "Homodimers/oligomers omitted",
            "Naked-RNA equilibrium; no dCas9, DNA binding, kinetics or cell environment",
            "Isolated trigger window; transcript-context suitability supplied externally",
            "Exhaustive over binary spacer/trigger-complement choices; "
            "not all four bases per position",
            "User-confirmed 5-prime order: BT, B, E-prime, loop, E, S, C",
            "J and Phi are composite ranking scores, not physical free energies",
            "Scores have no demonstrated cross-gate comparability without joint calibration",
        ],
        "input": config,
        "objective_parameters": asdict(objective),
        "lambda_calculation": {
            "method": "mean-absolute-energy/mean-absolute-accessibility",
            "scope": "all-inner-feasible-guides-across-prechecked-pairs",
            "candidate_count": batch_count,
            "value": objective.scale_lambda,
            "status": (
                "measurement_incomplete"
                if measurement_failures
                else "computed"
                if batch_count
                else "empty_batch"
            ),
        },
        "versions": folder.versions(),
        "summary": {
            "spacers": len(spacers),
            "trigger_windows": len(windows),
            "pairs": len(pairs),
            "evaluated_guides": evaluated_guides,
            "measurement_failed_guides": measurement_failures,
            "threshold_rejected_guides": threshold_rejected_guides,
            "inner_feasible_guides": batch_count,
            "retained_guide_audits": len(audit),
            "omitted_guide_audits": evaluated_guides - len(audit),
            "feasible_pairs": len(ranked),
            "selectable_pairs": len(selectable),
        },
        "top_candidates": selectable[:top_k],
        "pairs": pairs,
        "guide_audit": audit,
        "guide_rejection_counts": rejection_counts,
        "measurement_failure_counts": measurement_failure_counts,
    }
