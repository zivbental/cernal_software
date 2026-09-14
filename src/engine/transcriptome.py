"""Reference transcript sequences, by organism — Q1's first real answer.

``docs/ROADMAP.md`` Q1 asks where trigger sequences come from, and calls it "the single
largest unanswered question in the whole engine". This module is the first answer for
one host: a real reference genome, fetched once by ``tools/sync_transcriptome.py`` and
bundled under ``engine/data/transcriptomes/`` — the same "fetch offline, check in,
never call a provider from the running application" shape already used for the plasmid
backbone catalog (``stages/plasmids.py``) and the public dataset catalog
(``docs/public-datasets.md``).

**This is the "supporting-database module... no home yet" CLAUDE.md and
docs/integration.md GAP-1/Q1 describe.** It has a home now: this file for the loader,
``engine/data/transcriptomes/`` for the data, ``tools/sync_transcriptome.py`` for how the
data got there.

Unranked in the engine's layer graph, the same as ``store.py``/``artifacts.py`` — a data
accessor with no science in it, importable from ``pipeline.py`` and from a stage alike.
"""

from functools import cache
from pathlib import Path

from Bio import SeqIO

from engine import sequences as sq
from engine.domain import Host
from engine.errors import InputValidationError

_DATA_DIR = Path(__file__).resolve().parent / "data" / "transcriptomes"

#: Host -> bundled FASTA filename. Extend this, and re-run
#: ``tools/sync_transcriptome.py``, to add another organism — nothing else changes.
_FILES: dict[Host, str] = {
    Host.ECOLI: "ecoli.fasta",
}


@cache
def load_transcriptome(host: Host) -> dict[str, str]:
    """Every bundled transcript for ``host``, as RNA, keyed by gene id.

    Loaded once per process and cached — this is a ~4 MB file for *E. coli* alone, and
    nothing about it changes between requests within one process (``cache`` needs a
    hashable argument, which is why this takes a ``Host`` enum member rather than a
    string).

    Args:
        host: The organism. Only ``Host.ECOLI`` is bundled today.

    Returns:
        Gene id (NCBI locus tag, e.g. ``"b0002"``) to its CDS sequence, uppercase RNA.
        **CDS only, not a full transcript with UTRs** — see this module's sibling,
        ``tools/sync_transcriptome.py``, for why that is today's honest limitation
        rather than a hidden one.

    Raises:
        InputValidationError: no reference transcriptome is bundled for ``host``.
    """
    filename = _FILES.get(host)
    if filename is None:
        raise InputValidationError(
            f"No reference transcriptome is bundled for {host.value}. Only "
            f"{', '.join(sorted(h.value for h in _FILES))} today (docs/ROADMAP.md Q1)."
        )
    path = _DATA_DIR / filename
    return {record.id: sq.to_rna(str(record.seq)) for record in SeqIO.parse(path, "fasta")}


def available_hosts() -> tuple[Host, ...]:
    """Which hosts have a bundled reference transcriptome today."""
    return tuple(_FILES)
