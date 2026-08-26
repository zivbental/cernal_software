"""S8 — codon usage.

Needed by antisense CDS extension and toehold linker design: a linker must not translate
into something disruptive, and a payload should use codons the host prefers.
"""

from engine.domain import Host


class CodonOptimizer:
    """Synonymous-codon substitution search and translation scoring.

    Holds the host's usage table, so every caller scores against the same organism.
    """

    def __init__(self, host: Host, usage_table: dict[str, float] | None = None) -> None:
        self.host = host
        self.usage_table = usage_table or {}

    def variants(self, cds: str, target_pairing: str | None = None) -> list[str]:
        """Synonymous rewrites of a coding sequence — same protein, different bases."""
        raise NotImplementedError("Step 5")

    def translation_score(self, cds: str) -> float:
        """How well this sequence's codons suit the host. Higher is better."""
        raise NotImplementedError("Step 5 — codon adaptation index or equivalent")
