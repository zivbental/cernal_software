"""Stage 3 — switch design and validation."""

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
    """For each (trigger set x gate family), run the family's generator.

    Dispatches; owns no chemistry itself. Adding a family changes nothing here.
    """

    def __init__(self, families: list, validator: "SwitchValidator", host: Host) -> None:
        self.families = families
        self.validator = validator
        self.host = host

    def design(
        self, triggers: Iterable[TriggerCandidate], constraints: Constraints
    ) -> Iterator[GateDesign]:
        """Yield validated switch designs.

        Step 5: build trigger sets up to `constraints.max_triggers`; for each family
        supporting this host, ask `is_compatible`, then `generate_designs`; validate
        each; yield those that pass, with their measured metrics attached.
        """
        raise NotImplementedError("Step 5")

    def build_trigger_sets(
        self, triggers: Iterable[TriggerCandidate], constraints: Constraints
    ) -> Iterator[TriggerSet]:
        """Combinations up to the configured arity.

        Two triggers may come from the same gene — the pipeline map says so explicitly —
        so this must not deduplicate by gene_id.
        """
        raise NotImplementedError("Step 5")


class SwitchValidator:
    """The hard rules a switch must pass, whatever family produced it.

    Kept out of the families so every chemistry is held to the same standard, and so a
    rule is fixed in one place.
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
        """Structure and sequence rules together.

        Step 5, per the pipeline map: exactly one AUG, zero in-frame STOPs, RBS in the
        loop only (prokaryotic), no restriction sites for the chosen standard, and the
        predicted fold close enough to the intended one.
        """
        raise NotImplementedError("Step 5")
