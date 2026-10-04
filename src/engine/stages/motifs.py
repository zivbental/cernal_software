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

#: E. coli RNA-binding proteins whose recognition sequences can sequester a synthetic
#: transcript. **Regular expressions over DNA**, not literals, because every one of these
#: consensus sites is degenerate -- which is why ``extra_motifs`` (matched literally) was
#: the wrong home for them.
#:
#: Owned by the scientific team: these are the published consensus cores, deliberately the
#: permissive form, so the list errs towards flagging. Each entry cites what it is.
RBP_MOTIFS: dict[str, str] = {
    # CsrA/RsmA. The core recognition element is GGA presented in a HAIRPIN LOOP; the
    # extended consensus is RUACARGGAUGU. Sequence-only screening cannot see the loop, so
    # this matches the conserved ANGGA core and over-reports: measured at **25% of the A0
    # panel's 192 switches**. Treat a hit as "check the structure here", not as a reject.
    "CsrA_core": "A.GGA",
    # Hfq, U-rich face. A U tract is also the Rho-independent terminator signal, so
    # `HOMOPOLYMER_LIMITS` catches it too; kept here because the reason differs.
    # Measured at 0% of the A0 panel.
    "Hfq_Urich": "T{4,}",
}

#: Hfq's A-rich face is **deliberately absent**. Its consensus is an ARN triplet repeat,
#: which as a sequence pattern matched `AAGAACAGA` — the invariant spacer immediately 5' of
#: the Shine-Dalgarno — in **192 of 192** A0 panel switches. A screen that flags a required,
#: constant part of the architecture in every design cannot discriminate between designs, and
#: tightening the repeat count does not fix it: the region is constant, so any threshold
#: rejects all or none. Like RNase E, the real determinant is an A-rich patch in a
#: single-stranded context next to a hairpin, which needs structure and does not belong in a
#: sequence screener. Left out rather than left in as a filter that always fires.

#: Canonical G-quadruplex: **four** G-runs of three or more, separated by short loops. Two
#: runs is a G-rich patch, not a quadruplex, and screening for two would reject most GC-rich
#: designs for no reason.
G_QUADRUPLEX = "(?:G{3,}\w{1,7}){3,}G{3,}"

#: Stop codons, DNA. Scanned in frame only -- out-of-frame occurrences are harmless.
STOP_CODONS: tuple[str, ...] = ("TAA", "TAG", "TGA")

MAX_HOMOPOLYMER = 5

#: Per-base homopolymer ceilings, applied only when a caller asks for them. **T/U is lower
#: on purpose**: a U tract is the Rho-independent terminator signal in E. coli, so four is
#: already a risk in a transcribed switch where four A's are not.
#:
#: Opt-in, and the reason is instructive: a terminator *is* a poly-U tract. Applying this to
#: a plasmid flags the very element that is supposed to be there — measured, on the clean
#: golden fixture, as three TTTT hits in the backbone. So it is right for a switch or a
#: trigger and wrong for an assembled construct, which makes it the caller's call.
#: Bases absent here fall back to ``max_homopolymer``.
HOMOPOLYMER_LIMITS: dict[str, int] = {"T": 3}


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
        rbp_motifs: bool = False,
        quadruplex: bool = False,
        per_base_homopolymer: bool = False,
    ) -> None:
        self.standard = standard
        self.max_homopolymer = max_homopolymer
        self.sites = dict(RFC10_SITES if standard is AssemblyStandard.RFC10 else RFC1000_SITES)
        self.extra = dict(extra_motifs or {})
        # Both default OFF. Turning them on changes which designs pass, so it is a declared
        # choice per call site rather than a silent tightening of every existing caller.
        self.rbp_motifs = rbp_motifs
        self.quadruplex = quadruplex
        self.per_base_homopolymer = per_base_homopolymer

    def violations(
        self, sequence: str, *, circular: bool = False, reading_frame: int | None = None
    ) -> tuple[Violation, ...]:
        """Every prohibited motif in this sequence. Empty means compliant.

        Args:
            circular: When true, also catch a motif formed across the sequence's own
                end-to-start join — invisible to a linear scan, and the classic way an
                assembled plasmid hides a restriction site (or a homopolymer run)
                neither individual part carried (docs/plasmids.md §7.3). Meaningless
                for a linear molecule (a trigger, a switch) and defaults off.
            reading_frame: Index of the first base of the start codon, 0-based. Given it,
                every in-frame stop between there and the end is reported. **A stop codon
                is only a fault in frame** — the same three letters one base over are
                ordinary sequence, so without a frame this check cannot run and is skipped
                rather than guessed. Passing the index of something that is not a start
                codon is a caller bug; the scan still runs from wherever it is told.
        """
        dna = sequence.strip().upper().replace("U", "T")
        found = self._scan(dna)
        if reading_frame is not None:
            found.extend(self._stops(dna, reading_frame))

        if circular and dna:
            longest = max(
                (
                    *(len(motif) for motif in self.sites.values()),
                    *(len(motif) for motif in self.extra.values()),
                    self.max_homopolymer + 1,
                ),
                default=0,
            )
            pad = longest - 1
            if pad > 0:
                seen = {(v.start, v.motif) for v in found}
                found.extend(
                    v for v in self._scan(dna + dna[:pad]) if (v.start, v.motif) not in seen
                )

        return tuple(sorted(found, key=lambda v: v.start))

    def _scan(self, dna: str) -> list[Violation]:
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

        if self.rbp_motifs:
            for name, pattern in RBP_MOTIFS.items():
                found.extend(
                    Violation(m.group(), name, m.start(), "RBP motif")
                    for m in re.finditer(pattern, dna)
                )

        if self.quadruplex:
            found.extend(
                Violation(m.group(), "G-quadruplex", m.start(), "quadruplex")
                for m in re.finditer(G_QUADRUPLEX, dna)
            )

        # Per base, so that T can be held tighter than the rest. `HOMOPOLYMER_LIMITS` gives
        # the longest RUN THAT IS STILL ALLOWED, so the pattern looks for one more.
        limits = HOMOPOLYMER_LIMITS if self.per_base_homopolymer else {}
        run = "|".join(
            f"{base}{{{limits.get(base, self.max_homopolymer) + 1},}}" for base in "ACGT"
        )
        found.extend(
            Violation(m.group(), f"{m.group()[0]}x{len(m.group())}", m.start(), "homopolymer")
            for m in re.finditer(run, dna)
        )

        return found

    @staticmethod
    def _stops(dna: str, frame: int) -> list[Violation]:
        """In-frame stop codons from ``frame`` onward, excluding a stop at the very end."""
        found: list[Violation] = []
        if frame < 0:
            return found
        last = len(dna) - (len(dna) - frame) % 3
        for start in range(frame, last, 3):
            codon = dna[start : start + 3]
            if codon in STOP_CODONS and start + 3 < len(dna):
                found.append(Violation(codon, f"stop@{start}", start, "in-frame stop"))
        return found

    def is_compliant(self, sequence: str) -> bool:
        """True when nothing prohibited is present. A yes/no wrapper over ``violations``."""
        return not self.violations(sequence)
