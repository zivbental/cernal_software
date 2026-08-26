"""Stage 3 — switch design and validation.

Where triggers become actual constructs. For each combination of triggers, and each gate
chemistry that supports the host, a generator builds candidate switches; a validator then
checks each one folds as intended and obeys the hard sequence rules.

The split matters. **Generation is chemistry-specific** and lives in the gate families —
a toehold and a CRISPR gate share nothing about how they are built. **Validation is
common** and lives here, so every chemistry is held to the same standard and a rule is
fixed in one place rather than three.
"""

from collections.abc import Iterable, Iterator

from engine.domain import (
    Constraints,
    GateDesign,
    Host,
    TriggerCandidate,
    TriggerSet,
    ValidationResult,
)
from engine.tools.folding import FoldEngine
from engine.tools.motifs import MotifScreener
from engine.tools.off_target import OffTargetScanner
from engine.tools.translation import TranslationScorer


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
        self, triggers: Iterable[TriggerCandidate], constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Yield validated switch designs.

        Args:
            triggers: Stage 2's ranked candidates, already pruned.
            constraints: ``max_triggers`` bounds the arity; ``max_switch_length`` and
                ``standard`` are enforced by the validator.

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
        """
        raise NotImplementedError("Step 5")

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

        Rules (Step 5):
            * **Two triggers may come from the same gene.** The pipeline map is explicit:
              "2 inputs can be of the same gene or trigger". Two accessible windows on
              one transcript are a legitimate AND design, so this must not deduplicate by
              ``gene_id``. It is an easy and invisible mistake.
            * **Do not pair overlapping windows** from the same transcript — they cannot
              be bound simultaneously.
            * Activators come from UP-regulated genes, repressors from DOWN-regulated
              ones, but stage 4 decides the final logic. This stage only proposes.

        Cost:
            Pairs grow as the square of the input. 50 triggers gives 1,225 pairs; 200
            gives 19,900, and each is multiplied by the number of designs per family.
            This is exactly why stage 2 prunes hard — see docs/ROADMAP.md §3.
        """
        raise NotImplementedError("Step 5")


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
    """

    def __init__(
        self,
        folder: FoldEngine,
        off_target: OffTargetScanner,
        screener: MotifScreener,
        translation: TranslationScorer,
    ) -> None:
        self.folder = folder
        self.off_target = off_target
        self.screener = screener
        self.translation = translation

    def validate(self, design: GateDesign) -> ValidationResult:
        """Check one design against every hard rule.

        Args:
            design: A freshly generated switch.

        Returns:
            ``ValidationResult(ok, violations)``. **Collect every violation**, do not
            return on the first — a generator being tuned is far easier to fix when it
            reports all four problems at once.

        The rules, from the pipeline map (Step 5):
            * **Exactly one AUG.** ``sequences.find_augs``. An extra start codon means an
              extra protein, and in a eukaryotic host an upstream one captures the
              scanning ribosome and the payload is never reached.
            * **Zero in-frame STOP codons** before the payload. ``sequences.find_stops``
              in the switch's reading frame. One truncates the protein.
            * **RBS in the loop only** (prokaryotic). The whole mechanism depends on the
              RBS being sequestered in the OFF state. Check it lies within the
              single-stranded loop of the predicted structure, not the stem.
            * **No prohibited motifs.** ``screener.violations``. Restriction sites for the
              chosen standard, and homopolymers over the limit.
            * **Structure matches intent.** ``folder.ensemble_defect`` against the
              generator's target structure, below a threshold. A switch that does not
              fold into a hairpin is not a switch.
            * **Length.** Within ``constraints.max_switch_length``.

        Order the checks cheapest first:
            Sequence rules are string operations; folding is milliseconds. A design
            failing on a stop codon should never be folded.
        """
        raise NotImplementedError("Step 5")
