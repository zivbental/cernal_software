"""How structured is trigger B's toehold, and especially its 3' end?

    uv run python src/engine/gates/notebooks/toehold_and/toehold_metric.py --out toehold

Trigger B binds through ``r2``, whose complement ``r2*`` is the switch's toehold. Binding is
only the first step: the duplex then has to migrate into the inhibitory stem. The nucleotides
that decide whether that transition happens are the ones **adjacent to the hairpin**, at the
toehold's 3' end — structure there blocks invasion even when the toehold as a whole is free,
which is why this reports the 3' end separately rather than one average over the whole domain.

One row per trigger pair, joinable to the sweep on the six pair-key columns. Nothing here
folds a switch, so it costs one partition function per pair and runs in minutes.

**This is a measurement, not an axis.** Trimming the toehold changes a domain *length* and so
needs a change to ``assemble``'s layout; that is ``toehold_trim`` in ``PENDING_LENGTH_AXES``
and is not implemented. Reporting openness and trimming the molecule are different claims,
and only the first is made here.
"""

import argparse
import csv
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from full_sweep import PAIR_KEY_COLUMNS, read_fasta  # noqa: E402
from narrate import Progress, banner, conclude  # noqa: E402

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate, _mean_unpaired  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

#: How much of the toehold's 5' end a trim would remove. Trimming only helps if THIS is
#: what is pairing with the 3' end -- see ``p5_binds_p3``.
TRIM_WINDOW = 8

#: How many nucleotides at the 3' end count as "adjacent to the hairpin". Three is the span
#: the literature treats as decisive for nucleation (Zhang & Winfree's per-nucleotide rate
#: saturates around 6, and the first few carry most of it); 6 is reported beside it so the
#: choice is visible rather than load-bearing.
THREE_PRIME_SPANS = (3, 6)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--out", default="toehold")
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    transcript = read_fasta(args.fasta)

    kept = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        kept.append(pair)

    banner(
        "TOEHOLD ACCESSIBILITY - trigger B's r2, and its 3' end",
        [
            f"{len(kept)} trigger pairs, one partition function each",
            "the 3' end is the part adjacent to the inhibitory hairpin, where structure",
            "blocks binding from turning into invasion",
            "a measurement only -- trimming the toehold is a pending length axis",
        ],
        estimate=len(kept) * 0.2,
    )
    bar = Progress(len(kept), "pairs")

    path = output_dir / f"{args.out}.csv"
    rows = []
    for pair in kept:
        trigger_b = transcript[slice(*pair.window_b())]
        # Mirrors `assemble`'s own slice, `rna_b[len_k2 + len_x:]` with
        # `len_k2 = ARM_LEN - len_x`, which reduces to this. Written the same way on purpose:
        # if ARM_LEN is ever split into separate main and secondary constants, both must move
        # together, and two different spellings of one slice is how they would not.
        r2 = trigger_b[gate.ARM_LEN :]
        row = dict(
            zip(
                PAIR_KEY_COLUMNS,
                (pair.x_start, pair.xstar_start, *pair.window_a(), *pair.window_b()),
                strict=True,
            )
        )
        row["len_x"] = pair.len_x
        row["r2_len"] = len(r2)
        if len(r2) < max(THREE_PRIME_SPANS):
            # Short domains are reported as unmeasured, never as zero: a zero here would
            # read as "perfectly paired" and rank the pair as the worst available.
            for span in THREE_PRIME_SPANS:
                row[f"r2_open_3p{span}"] = None
                row[f"r2star_open_3p{span}"] = None
            row["r2_open_all"] = None
            row["r2star_open_all"] = None
            row["p5_binds_p3"] = None
            row["trim_indicated"] = None
        else:
            matrix = gate.folder.pooled_pair_probabilities(r2)
            row["r2_open_all"] = _mean_unpaired(matrix, 0, len(r2))
            for span in THREE_PRIME_SPANS:
                row[f"r2_open_3p{span}"] = _mean_unpaired(matrix, len(r2) - span, len(r2))

            # The columns above fold **r2**, trigger B's own domain. What a trim removes is
            # the SWITCH's toehold, r2* = revcomp(r2) -- a different molecule with a
            # different self-structure, and the one that has to be free for B to bind. Both
            # are reported rather than the first being quietly replaced, because toehold.csv
            # already exists with the r2 columns in it.
            star = sq.reverse_complement(r2)
            star_matrix = gate.folder.pooled_pair_probabilities(star)
            row["r2star_open_all"] = _mean_unpaired(star_matrix, 0, len(star))
            for span in THREE_PRIME_SPANS:
                row[f"r2star_open_3p{span}"] = _mean_unpaired(
                    star_matrix, len(star) - span, len(star)
                )

            # Does the 5' end -- the part a trim would cut -- actually pair with the 3' end,
            # the part next to the hairpin that has to be free? Expected number of base pairs
            # between the two windows. Trimming is only worth doing where this is non-trivial:
            # if the 3' end is sequestered by something else, or by nothing, removing the 5'
            # end costs binding surface and buys no accessibility.
            five = range(0, min(TRIM_WINDOW, len(star)))
            three = range(max(0, len(star) - max(THREE_PRIME_SPANS)), len(star))
            row["p5_binds_p3"] = sum(
                star_matrix[i][j] + star_matrix[j][i] for i in five for j in three
            )
            row["trim_indicated"] = row["p5_binds_p3"] >= 0.5
        rows.append(row)
        bar.step(f"x@{pair.x_start}  3' open {row['r2_open_3p3']}")
    bar.finish()

    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    measured = [r["r2_open_3p3"] for r in rows if r["r2_open_3p3"] is not None]
    whole = [r["r2_open_all"] for r in rows if r["r2_open_all"] is not None]
    findings = [f"{len(rows):,} trigger pairs measured, {len(measured):,} with a usable r2."]
    if measured:
        measured.sort()
        whole.sort()
        findings += [
            f"Openness of the 3 nt nearest the hairpin spans {measured[0]:.3f} to "
            f"{measured[-1]:.3f}, median {measured[len(measured) // 2]:.3f}. Over the whole "
            f"toehold the median is {whole[len(whole) // 2]:.3f} -- the two differ, which is "
            f"the reason for reporting the end separately.",
            "Join on the six pair-key columns to rank designs by how free the nucleation site "
            "is before trigger B arrives. No threshold is applied here.",
        ]
    conclude(findings, wrote=[str(path)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
