"""S5 — off-target scanning, in both directions.

One transcriptome index, three callers. What differs between them is the question asked
and what the hits mean, and that lives in the stage
(docs/engine-classes.md §4a).
"""

from engine.domain import Hit, OffTargetReport


class OffTargetScanner:
    """Finds near-matches of a sequence in the transcriptome.

    Holds the index and the mismatch model, so every caller uses the same definition of
    "similar" and the same penalty scale. Three separately configured scanners produce
    numbers that scoring then normalises as though they were comparable.
    """

    def __init__(self, transcriptome: dict[str, str], max_mismatch: int = 2) -> None:
        self.transcriptome = transcriptome
        self.max_mismatch = max_mismatch

    def build_index(self) -> None:
        """Prepare the search structure. Called once, before any scanning."""
        raise NotImplementedError("Step 5")

    def find_similar(self, sequence: str) -> tuple[Hit, ...]:
        """The primitive. Everything below is interpretation of these hits."""
        raise NotImplementedError("Step 5")

    def scan_trigger(self, trigger: str) -> OffTargetReport:
        """Direction (b): is this trigger sponged by non-cognate RNA?

        Consequence: less trigger available, weak ON, false negative.
        """
        raise NotImplementedError("Step 5")

    def scan_switch(self, binding_site: str) -> OffTargetReport:
        """Direction (a): can non-cognate RNA cross-activate this switch?

        Consequence: leak, false positive.
        """
        raise NotImplementedError("Step 5")
