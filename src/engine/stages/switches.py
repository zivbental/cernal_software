"""Stage 3 — switch design and validation.

Where triggers become actual constructs. For each combination of triggers, and each gate
chemistry that supports the host, a generator builds candidate switches; a validator then
checks each one folds as intended and obeys the hard sequence rules.

The split matters. **Generation is chemistry-specific** and lives in the gate families —
a toehold and a CRISPR gate share nothing about how they are built. **Validation is
common** and lives here, so every chemistry is held to the same standard and a rule is
fixed in one place rather than three.
"""

from collections.abc import Callable, Iterable, Iterator
from itertools import combinations

from engine import sequences as sq
from engine.domain import (
    Constraints,
    GateDesign,
    Host,
    TriggerCandidate,
    TriggerSet,
    ValidationResult,
)
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.stages.motifs import MotifScreener
from engine.stages.off_target import OffTargetScanner


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
            ``engine.client.MockEngine._build_candidates`` already uses.
        """
        for trigger_set in self.build_trigger_sets(triggers, constraints):
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
                        yield design
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
            yield TriggerSet(activators=(trigger,))

        if constraints.max_triggers < 2:
            return

        for first, second in combinations(pool, 2):
            if first.gene_id == second.gene_id and _windows_overlap(first, second):
                continue
            yield TriggerSet(activators=(first, second))


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
        off_target: Shared ``OffTargetScanner``, for direction (a) on the binding site.
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
        off_target: OffTargetScanner,
        screener: MotifScreener,
        translation: TranslationScorer,
        constraints: Constraints,
    ) -> None:
        self.folder = folder
        self.off_target = off_target
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
            * **Three initiation rules**, each exactly as the architecture specifies it
              and no wider, taking the coordinates the generating family declares:

              1. **No out-of-frame AUG downstream of the RBS**, for a family that
                 declares ``architecture["rbs_span"]``. That span says where the ribosome
                 loads, and every AUG from there to the 3' end must be in frame with
                 ``architecture["aug_index"]``. In frame is legal -- that is a Met codon.
                 A family that declares no ``rbs_span`` keeps the stricter **exactly one
                 AUG in the switch**: without an RBS position there is nothing to say
                 which AUGs are reachable, and the frame-aware rule is strictly looser,
                 so applying it unasked relaxes a family it was not written for.
                 Upstream of the RBS is not scanned, because prokaryotic initiation needs
                 a Shine-Dalgarno sequence and a triplet 60-100 nt 5' of one is not a
                 start codon; measured, a two-input design carries one or two such
                 triplets in its trigger-derived 5' domains, which are a reverse
                 complement of the gene being sensed and not ours to edit.
              2. **No second ribosome binding site outside the loop.**
                 ``architecture["rbs_core_motif"]`` names the sequence, and it may occur
                 only within ``rbs_span``.
              3. **No in-frame stop codon after the planned start.** The switch ends at
                 its linker and the reporter follows it, so an in-frame stop truncates the
                 protein before the reporter is reached.

              A family carrying no ``aug_index`` is a chemistry with no embedded start
              codon of its own -- an antisense design silences post-transcriptionally
              rather than being translated -- and rules 1 and 3 are skipped for it rather
              than guessed. A family carrying no ``rbs_core_motif`` skips rule 2 the same
              way. **This is the same deferral the paragraph below makes** for geometry the
              validator must not learn: the offsets and the motif belong to the family,
              the rules belong here.

        Deliberately not implemented here (docs/smoke-run.md §3, S4):
            * **"Structure matches intent"** needs ``FoldEngine.ensemble_defect``, which
              is itself a stub, and the only two modules allowed to fold
              (``gates/tools/folding.py``, ``stages/folding.py``) both live under
              ``engine/gates/`` or are this file's sibling — this branch does not touch
              ``gates/`` at all, so this rule waits for whoever does.
            * **"RBS in the loop only"** needs the loop's exact offset within
              ``design.sequence`` — geometry only the generating family knows (toehold's
              ``architecture`` and antisense's share no keys for this). Hardcoding one
              family's layout into the shared validator would be exactly the kind of
              silent, chemistry-specific assumption this stage exists to avoid; it
              belongs in the family that has the geometry, not here.

        Order the checks cheapest first:
            Sequence rules are string operations; folding is milliseconds. A design
            failing on a stop codon should never be folded — moot today since nothing
            implemented here folds at all, but the ordering stays correct for when the
            deferred structural rule lands.
        """
        violations: list[str] = []

        if len(design.sequence) > self.constraints.max_switch_length:
            violations.append(
                f"switch is {len(design.sequence)} nt, over the "
                f"{self.constraints.max_switch_length} nt limit"
            )

        violations.extend(str(site) for site in self.screener.violations(design.sequence))

        aug_index = design.architecture.get("aug_index")
        rbs_span = design.architecture.get("rbs_span")
        if aug_index is not None:
            # RULE 1. No out-of-frame AUG downstream of the ribosome binding site.
            #
            # Downstream of the RBS and *all the way to the 3' end*, not merely up to the
            # planned start: measured, 192 of 2,176 two-input designs (8.8%) carry one
            # inside `main_pre`, after the real AUG, and a window that stopped at the AUG
            # missed every one of them. And **in frame is not a violation** -- an in-frame
            # AUG is a plain Met codon and makes the intended protein, so counting AUGs
            # instead of checking their frame rejects correct designs.
            #
            # Upstream of the RBS is not scanned at all. Prokaryotic initiation needs a
            # Shine-Dalgarno sequence, and a triplet 60-100 nt 5' of one is not a start
            # codon. The family declares where its RBS is, because that offset is geometry
            # only it knows -- the same deferral rule 2 below makes.
            if rbs_span is None:
                # **No declaration of where the ribosome loads, so the conservative rule
                # stands.** Without an RBS position there is no way to say which AUGs are
                # reachable, and the frame-aware rule below would be strictly looser: it
                # permits every in-frame AUG, which for a family whose 5' UTR is short and
                # synthetic is a relaxation bought for nothing. Measured when the
                # frame-aware rule was briefly applied to everything: a one-input run whose
                # paste was `"AUG" * 9` -- all those AUGs being in frame with one another --
                # went from 0 candidates to 19.
                augs = sq.find_augs(design.sequence)
                if len(augs) != 1:
                    violations.append(
                        f"expected exactly one AUG, found {len(augs)} at {list(augs)}"
                    )
            else:
                out_of_frame = [
                    index
                    for index in sq.find_augs(design.sequence)
                    if index >= rbs_span[0] and (index - aug_index) % 3 != 0
                ]
                if out_of_frame:
                    violations.append(
                        f"out-of-frame AUG(s) downstream of the RBS at {out_of_frame} "
                        f"(the planned start is at {aug_index})"
                    )

            # RULE 3. No in-frame stop codon after the planned start. The switch ends at
            # its linker and the reporter follows it, so an in-frame stop anywhere here
            # truncates the protein before the reporter is reached.
            stops = sq.find_stops(design.sequence, frame=aug_index)
            if stops:
                violations.append(f"in-frame stop codon(s) at {list(stops)}")

        # RULE 2. The ribosome binding site appears ONLY inside the main loop.
        #
        # This method's notes below deferred this rule for want of the loop's offset,
        # which is geometry only the generating family knows. The family now declares both
        # the loop span and the motif, so the rule lands here without the validator
        # learning any one chemistry's layout: a eukaryotic family would declare a Kozak
        # and the same code would screen for that instead.
        motif = design.architecture.get("rbs_core_motif")
        if motif and rbs_span:
            low, high = rbs_span
            stray = [
                index
                for index in range(len(design.sequence) - len(motif) + 1)
                if design.sequence[index : index + len(motif)] == motif
                and not (low <= index and index + len(motif) <= high)
            ]
            if stray:
                violations.append(
                    f"ribosome binding site {motif!r} occurs outside the loop "
                    f"[{low}, {high}) at {stray}"
                )

        return ValidationResult.failed(*violations) if violations else ValidationResult.passed()
