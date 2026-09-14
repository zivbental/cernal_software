"""Stage 1 for the A0 two-input AND gate: find usable trigger pairs in one transcript.

Run it::

    uv run python src/engine/gates/notebooks/toehold_and/find_candidates.py \\
        --fasta "path/to/mCherry original.txt" --csv candidates.csv

**Why this lives in the notebook workbench.** The geometry — finding every perfect
reverse-complementary overlap and checking both footprints fit, do not collide and lie far
enough apart — is in ``ToeholdAndGate.find_trigger_pairs`` where it belongs, and is
imported here rather than repeated. The three filters below are *not* here because they
belong here; they are here because a gate family may not reach for them:

* **Motif screening.** ``MotifScreener`` escapes its ``extra_motifs`` as literals, so it
  cannot express the patterns this architecture forbids — ``[AG]AUGA`` for RNase E, the
  G-quadruplex pattern, ``U{5,}``, the internal Shine-Dalgarno alternatives. Teaching it
  regexes is a change to a shared stage that every family is screened by, so it needs
  coordinating rather than doing here. Until then these regexes are duplicated, and that
  duplication is a known debt, not a design.
* **Knockout feasibility.** ``CodonOptimizer.variants`` is still a stub, so the synonymous
  codon table is rebuilt here from ``sequences.CODON_TABLE``. It should move into that
  tool.

Both filters are *selection* criteria rather than diagnostics. Knockout feasibility in
particular has to run inside the scan: 169 of the 1,036 otherwise-valid mCherry pairs
cannot have either trigger disabled by any synonymous substitution, and finding that out
after choosing a pair wastes a design cycle.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]


def bootstrap() -> Path:
    """Put ``<repo>/src`` on ``sys.path``, the same way the notebooks beside this do.

    The package is not installed into the environment — ``pythonpath = ["src"]`` in
    ``pyproject.toml`` is a pytest setting and does nothing for a plain script run — so
    without this the script is only runnable through the test harness. It has to work
    from a VS Code Run button too.
    """
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    return _SRC


bootstrap()

from engine import sequences as sq  # noqa: E402  (path set up just above)
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.binding import can_pair, longest_complementary_run  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

#: Patterns forbidden anywhere in trigger A's window. RNase E cleavage would shorten the
#: transcript; a G-quadruplex or a poly-U run would sequester or terminate it; an internal
#: Shine-Dalgarno would give the ribosome a second place to start.
MOTIFS: dict[str, re.Pattern[str]] = {
    "RNase_E": re.compile(r"[AG]AUGA"),
    "G_quadruplex": re.compile(r"G{3,}[ACGU]{1,7}G{3,}[ACGU]{1,7}G{3,}[ACGU]{1,7}G{3,}"),
    "poly_U": re.compile(r"U{5,}"),
    "internal_SD": re.compile(r"AGGAGG|AAGGAG|GGAGGA"),
}

#: E. coli rare codons. A knockout may not introduce one — the control has to differ from
#: the real construct only in whether the trigger works, not in how well it translates.
RARE = frozenset({"AGG", "AGA", "CGA", "AUA", "CUA"})

SYNONYMS: dict[str, list[str]] = {}
for _codon, _residue in sq.CODON_TABLE.items():
    SYNONYMS.setdefault(_residue, []).append(_codon)


def synonymous(codon: str) -> list[str]:
    """Other codons for the same residue, excluding rare ones and the codon itself."""
    residue = sq.CODON_TABLE.get(codon)
    if residue is None:
        return []
    return [c for c in SYNONYMS[residue] if c != codon and c not in RARE]


def breakable_positions(transcript: str, start: int, length: int) -> set[int]:
    """Positions inside a region that some synonymous codon can actually change.

    A position whose codon has no usable alternative is immovable: ``AUG`` and ``UGG`` have
    no synonym at all, and for others every alternative may be a rare codon.
    """
    movable: set[int] = set()
    for codon_index in range(start // 3, (start + length - 1) // 3 + 1):
        codon = transcript[codon_index * 3 : codon_index * 3 + 3]
        for alternative in synonymous(codon):
            for offset in range(3):
                position = codon_index * 3 + offset
                if codon[offset] != alternative[offset] and start <= position < start + length:
                    movable.add(position)
    return movable


def knockout_possible(transcript: str, start: int, length: int, partner: str) -> bool:
    """Could synonymous substitution alone leave this trigger unable to nucleate?

    Computed exactly and cheaply rather than by search: break *every* position any
    synonymous codon can break, then ask whether a pairable run of four still survives. If
    one does, no combination of synonymous edits can disable this trigger, and the pair is
    unusable — not because the gate would fail, but because its negative control cannot be
    built.

    Wobbles count, through ``longest_complementary_run``. They are why this is not rare: a
    position can only be broken by a base pairing with *neither* partner option.
    """
    broken = list(transcript[start : start + length])
    for position in breakable_positions(transcript, start, length):
        codon_index, offset = divmod(position, 3)
        codon = transcript[codon_index * 3 : codon_index * 3 + 3]
        partner_base = partner[length - 1 - (position - start)]
        for alternative in synonymous(codon):
            if not can_pair(alternative[offset], partner_base):
                broken[position - start] = alternative[offset]
                break
    return longest_complementary_run("".join(broken), partner) < 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True, help="the transcript both triggers come from")
    parser.add_argument("--min-gap", type=int, default=None, help="default: the gate's own 50")
    parser.add_argument("--csv", help="write every surviving candidate here")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)

    lines = Path(args.fasta).read_text().splitlines()
    transcript = sq.to_rna("".join(line for line in lines if not line.startswith(">")))

    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI,
        FoldEngine(temperature=37.0),
        TranslationScorer(Host.ECOLI),
        CodonOptimizer(Host.ECOLI),
    )
    print(f"transcript: {len(transcript)} nt, {len(transcript) // 3} codons")

    geometric = list(gate.find_trigger_pairs(transcript, min_window_gap=0))
    kept = args.min_gap if args.min_gap is not None else gate.MIN_WINDOW_GAP

    rows = []
    for pair in geometric:
        a_start, a_end = pair.window_a()
        b_start, b_end = pair.window_b()
        window_a = transcript[a_start:a_end]
        main_pre = transcript[pair.x_start - 9 : pair.x_start]
        hits = [name for name, pattern in MOTIFS.items() if pattern.search(window_a)]
        # main_pre lands at +4..+12 in the switch, so its frame is set by the switch's own
        # AUG, not by the frame it happens to occupy in this transcript.
        if any(main_pre[i : i + 3] in sq.STOP_CODONS for i in (0, 3, 6)):
            hits.append("in_frame_stop")

        x = transcript[pair.x_start : pair.x_start + pair.len_x]
        x_star = transcript[pair.xstar_start : pair.xstar_start + pair.len_x]
        k1 = transcript[a_start : a_start + 6]
        k2_start = pair.xstar_start - pair.len_k2
        ko_a = knockout_possible(transcript, pair.x_start, pair.len_x, x_star) or (
            knockout_possible(transcript, a_start, 6, sq.reverse_complement(k1))
        )
        ko_b = knockout_possible(transcript, pair.xstar_start, pair.len_x, x) or (
            pair.len_k2 > 0
            and k2_start >= 0
            and knockout_possible(
                transcript,
                k2_start,
                pair.len_k2,
                sq.reverse_complement(transcript[k2_start : pair.xstar_start]),
            )
        )
        rows.append(
            {
                "len_x": pair.len_x,
                "x": x,
                "x_start": pair.x_start,
                "xstar_start": pair.xstar_start,
                "window_a": f"{a_start}..{a_end - 1}",
                "window_b": f"{b_start}..{b_end - 1}",
                "gap": pair.gap(),
                "motif_fail": ";".join(hits) or "-",
                "ko_A": ko_a,
                "ko_B": ko_b,
            }
        )

    passes = [r for r in rows if r["motif_fail"] == "-" and r["gap"] >= kept]
    clean = [r for r in passes if r["ko_A"] and r["ko_B"]]

    print(f"windows fit and are disjoint ................. {len(rows)}")
    print(f"  motif-clean and gap >= {kept} ................. {len(passes)}")
    print(
        f"  and both negative controls constructible ... {len(clean)}"
        f"   ({len(passes) - len(clean)} dropped: no synonymous knockout)"
    )

    clean.sort(key=lambda r: (-r["len_x"], -r["gap"]))
    print(f"\n  {'len_x':>5} {'x':<10} {'x@':>5} {'x*@':>5} {'gap':>5}  window_A       window_B")
    for row in clean[: args.top]:
        print(
            f"  {row['len_x']:>5} {row['x']:<10} {row['x_start']:>5} "
            f"{row['xstar_start']:>5} {row['gap']:>5}  {row['window_a']:<14} {row['window_b']}"
        )
    if len(clean) > args.top:
        print(f"  ... {len(clean) - args.top} more")

    if args.csv and clean:
        with open(args.csv, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(clean[0]))
            writer.writeheader()
            writer.writerows(clean)
        print(f"\n{len(clean)} candidates written to {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
