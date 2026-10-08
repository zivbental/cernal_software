"""Table-11 validation and public 1-based coordinates."""
from dataclasses import dataclass
import hashlib
import re

from Bio.Data import CodonTable

TABLE = CodonTable.unambiguous_dna_by_id[11]
AA = dict(TABLE.forward_table)
STARTS = frozenset(TABLE.start_codons)
STOPS = frozenset(TABLE.stop_codons)
SYNONYMS = {a: tuple(sorted(c for c in AA if AA[c] == a)) for a in set(AA.values())}


class InputError(ValueError):
    def __init__(self, message, field="cds"):
        super().__init__(message)
        self.field = field


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(text, field="cds", allow_empty=False, limit=9000):
    if not isinstance(text, str):
        raise InputError("Provide a sequence as text.", field)
    lines = text.strip().splitlines()
    headers = [i for i, line in enumerate(lines) if line.lstrip().startswith(">")]
    name = "input"
    if headers:
        if len(headers) != 1 or headers[0] != 0:
            raise InputError("Provide one FASTA record with its header on the first line.", field)
        name = lines.pop(0).strip()[1:][:200] or name
    raw = "".join(lines)
    seq = re.sub(r"\s+", "", raw).upper().replace("U", "T")
    if not seq and not allow_empty:
        raise InputError("The sequence cannot be empty.", field)
    if len(seq) > limit:
        raise InputError(f"The sequence exceeds the {limit:,} nt limit. Select the intended region and submit again.", field)
    invalid = next((i for i, base in enumerate(seq) if base not in "ACGT"), None)
    if invalid is not None:
        raise InputError(f"Invalid character at nt {invalid + 1}. Only A/C/G/T are accepted; U is converted to T.", field)
    changes = []
    if any(c.islower() for c in raw):
        changes.append("uppercase")
    if "U" in raw.upper():
        changes.append("U_to_T")
    if re.search(r"\s", raw) or len(lines) > 1:
        changes.append("whitespace_removed")
    return seq, name, changes


def split_codons(sequence):
    return tuple(sequence[i:i + 3] for i in range(0, len(sequence), 3))


def translate(sequence):
    cs = split_codons(sequence)
    return "".join("M" if i == 0 and c in STARTS else AA.get(c, "*") for i, c in enumerate(cs) if not (i == len(cs) - 1 and c in STOPS))


@dataclass(frozen=True)
class CDS:
    sequence: str
    codons: tuple
    protein: str
    name: str
    normalization: tuple
    warnings: tuple
    standard_start: bool
    terminal_stop: bool

    @classmethod
    def parse(cls, text):
        seq, name, normalization = normalize(text)
        if len(seq) < 3 or len(seq) % 3:
            raise InputError("CDS length must be a multiple of 3 and include at least one sense codon.")
        cs = split_codons(seq)
        for i, c in enumerate(cs[:-1]):
            if c in STOPS:
                raise InputError(f"Codon {i + 1} is an internal stop codon ({c}).")
        if cs[0] in STOPS:
            raise InputError("The input has no valid coding sequence.")
        warnings = []
        if cs[0] not in STARTS:
            warnings.append("nonstandard_start")
        if cs[-1] not in STOPS:
            warnings.append("missing_terminal_stop")
        return cls(seq, cs, translate(seq), name, tuple(normalization), tuple(warnings), cs[0] in STARTS, cs[-1] in STOPS)

    @property
    def sense_nt(self):
        return len(self.sequence) - (3 if self.terminal_stop else 0)


def edits(original, candidate):
    return [{"codon_position": i + 1, "nt_start": 3 * i + 1, "nt_end": 3 * i + 3,
             "before": a, "after": b, "amino_acid": "M" if i == 0 and a in STARTS else AA[a]}
            for i, (a, b) in enumerate(zip(split_codons(original), split_codons(candidate))) if a != b]
