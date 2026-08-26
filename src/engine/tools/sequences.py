"""S6 — sequence facts. Pure functions, no state, no dependencies.

Implemented rather than stubbed: none of this needs a scientific decision, and every
stage below depends on it.
"""

import re

RNA_BASES = frozenset("ACGU")
DNA_BASES = frozenset("ACGT")

_COMPLEMENT = str.maketrans("ACGUTacgut", "UGCAAugcaa")
_DNA_COMPLEMENT = str.maketrans("ACGTacgt", "TGCAtgca")

START_CODON = "AUG"
STOP_CODONS = frozenset({"UAA", "UAG", "UGA"})

#: Standard genetic code, RNA. '*' marks a stop.
CODON_TABLE: dict[str, str] = {
    "UUU": "F",
    "UUC": "F",
    "UUA": "L",
    "UUG": "L",
    "CUU": "L",
    "CUC": "L",
    "CUA": "L",
    "CUG": "L",
    "AUU": "I",
    "AUC": "I",
    "AUA": "I",
    "AUG": "M",
    "GUU": "V",
    "GUC": "V",
    "GUA": "V",
    "GUG": "V",
    "UCU": "S",
    "UCC": "S",
    "UCA": "S",
    "UCG": "S",
    "CCU": "P",
    "CCC": "P",
    "CCA": "P",
    "CCG": "P",
    "ACU": "T",
    "ACC": "T",
    "ACA": "T",
    "ACG": "T",
    "GCU": "A",
    "GCC": "A",
    "GCA": "A",
    "GCG": "A",
    "UAU": "Y",
    "UAC": "Y",
    "UAA": "*",
    "UAG": "*",
    "CAU": "H",
    "CAC": "H",
    "CAA": "Q",
    "CAG": "Q",
    "AAU": "N",
    "AAC": "N",
    "AAA": "K",
    "AAG": "K",
    "GAU": "D",
    "GAC": "D",
    "GAA": "E",
    "GAG": "E",
    "UGU": "C",
    "UGC": "C",
    "UGA": "*",
    "UGG": "W",
    "CGU": "R",
    "CGC": "R",
    "CGA": "R",
    "CGG": "R",
    "AGU": "S",
    "AGC": "S",
    "AGA": "R",
    "AGG": "R",
    "GGU": "G",
    "GGC": "G",
    "GGA": "G",
    "GGG": "G",
}


def to_rna(sequence: str) -> str:
    """Uppercase and convert T to U. Researchers paste DNA as often as RNA."""
    return sequence.strip().upper().replace("T", "U")


def to_dna(sequence: str) -> str:
    return sequence.strip().upper().replace("U", "T")


def is_valid_rna(sequence: str) -> bool:
    return bool(sequence) and set(sequence.upper()) <= RNA_BASES


def reverse_complement(sequence: str, *, dna: bool = False) -> str:
    """Reverse complement. A switch's binding site is the trigger's reverse complement."""
    table = _DNA_COMPLEMENT if dna else _COMPLEMENT
    return sequence.upper().translate(table)[::-1]


def gc_content(sequence: str) -> float:
    """Percent G+C. Extremes hurt synthesis and folding alike."""
    if not sequence:
        return 0.0
    upper = sequence.upper()
    return 100.0 * sum(base in "GC" for base in upper) / len(upper)


def codons(sequence: str, frame: int = 0) -> list[str]:
    """Split into codons from a reading frame, dropping any trailing partial codon."""
    rna = to_rna(sequence)[frame:]
    return [rna[i : i + 3] for i in range(0, len(rna) - len(rna) % 3, 3)]


def translate(sequence: str, frame: int = 0, *, stop_at_stop: bool = True) -> str:
    """Translate to single-letter amino acids. Unknown codons become 'X'."""
    protein: list[str] = []
    for codon in codons(sequence, frame):
        residue = CODON_TABLE.get(codon, "X")
        if residue == "*" and stop_at_stop:
            break
        protein.append(residue)
    return "".join(protein)


def find_augs(sequence: str, frame: int | None = None) -> tuple[int, ...]:
    """Every AUG position.

    A switch must present exactly one start codon; an alternative AUG upstream of the
    intended one produces a different protein.
    """
    rna = to_rna(sequence)
    found = [m.start() for m in re.finditer("(?=AUG)", rna)]
    if frame is None:
        return tuple(found)
    return tuple(i for i in found if (i - frame) % 3 == 0)


def find_stops(sequence: str, frame: int = 0) -> tuple[int, ...]:
    """In-frame stop codon positions. A switch's coding region must contain none."""
    rna = to_rna(sequence)
    return tuple(i for i in range(frame, len(rna) - 2, 3) if rna[i : i + 3] in STOP_CODONS)


def longest_homopolymer(sequence: str) -> tuple[str, int]:
    """The longest single-base run, as ``(base, length)``.

    Runs above about five nucleotides cause synthesis and sequencing trouble.
    """
    if not sequence:
        return "", 0
    upper = sequence.upper()
    best_base, best_run = upper[0], 1
    base, run = upper[0], 1
    for character in upper[1:]:
        run = run + 1 if character == base else 1
        base = character
        if run > best_run:
            best_base, best_run = base, run
    return best_base, best_run


def hamming(a: str, b: str) -> int:
    """Mismatches between two equal-length sequences."""
    if len(a) != len(b):
        raise ValueError("Sequences must be the same length.")
    return sum(x != y for x, y in zip(a.upper(), b.upper(), strict=True))


def windows(sequence: str, length: int, step: int = 1) -> list[tuple[int, str]]:
    """Sliding windows as ``(start, subsequence)`` — the basis of trigger scanning."""
    if length <= 0 or length > len(sequence):
        return []
    return [(i, sequence[i : i + length]) for i in range(0, len(sequence) - length + 1, step)]
