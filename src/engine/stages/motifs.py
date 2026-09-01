"""S7 — prohibited motif screening.

Implemented: this is pattern matching, not science. The **motif sets** are the part the
scientific team owns, and they live in the tables below so they can be edited without
touching the logic.
"""

import re
from dataclasses import dataclass

from engine.domain import AssemblyStandard

#: Restriction sites the iGEM assembly standards forbid inside a part.
#: Written as DNA; sequences are converted before matching.
RFC10_SITES: dict[str, str] = {
    "EcoRI": "GAATTC",
    "XbaI": "TCTAGA",
    "SpeI": "ACTAGT",
    "PstI": "CTGCAG",
    "NotI": "GCGGCCGC",
}

RFC1000_SITES: dict[str, str] = {
    "BsaI": "GGTCTC",
    "BsaI_rc": "GAGACC",
    "SapI": "GCTCTTC",
    "SapI_rc": "GAAGAGC",
}

#: Provisional. Owned by the scientific team.
RNASE_SITES: dict[str, str] = {}
RBP_MOTIFS: dict[str, str] = {}

MAX_HOMOPOLYMER = 5


@dataclass(frozen=True, slots=True)
class Violation:
    """One prohibited motif found, and where."""

    motif: str
    name: str
    start: int
    kind: str

    def __str__(self) -> str:
        return f"{self.kind} '{self.name}' ({self.motif}) at position {self.start}"


class MotifScreener:
    """Rejects or penalises sequences carrying prohibited motifs.

    Holds the motif sets, so a stage constructs one and reuses it. Screening the same
    sequence against three separately configured screeners is how inconsistent rules
    creep in.
    """

    def __init__(
        self,
        standard: AssemblyStandard = AssemblyStandard.RFC10,
        *,
        extra_motifs: dict[str, str] | None = None,
        max_homopolymer: int = MAX_HOMOPOLYMER,
    ) -> None:
        self.standard = standard
        self.max_homopolymer = max_homopolymer
        self.sites = dict(RFC10_SITES if standard is AssemblyStandard.RFC10 else RFC1000_SITES)
        self.extra = dict(extra_motifs or {})

    def violations(self, sequence: str) -> tuple[Violation, ...]:
        """Every prohibited motif in this sequence. Empty means compliant."""
        dna = sequence.strip().upper().replace("U", "T")
        found: list[Violation] = []

        for name, motif in self.sites.items():
            found.extend(
                Violation(motif, name, m.start(), "restriction site")
                for m in re.finditer(f"(?={re.escape(motif)})", dna)
            )

        for name, motif in self.extra.items():
            found.extend(
                Violation(motif, name, m.start(), "forbidden motif")
                for m in re.finditer(f"(?={re.escape(motif)})", dna)
            )

        run = "|".join(f"{base}{{{self.max_homopolymer + 1},}}" for base in "ACGT")
        found.extend(
            Violation(m.group(), f"{m.group()[0]}x{len(m.group())}", m.start(), "homopolymer")
            for m in re.finditer(run, dna)
        )

        return tuple(sorted(found, key=lambda v: v.start))

    def is_compliant(self, sequence: str) -> bool:
        """True when nothing prohibited is present. A yes/no wrapper over ``violations``."""
        return not self.violations(sequence)
