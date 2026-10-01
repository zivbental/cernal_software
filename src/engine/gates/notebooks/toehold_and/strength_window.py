"""Generate the experiment that asks whether a thermodynamic AND is reachable at all.

    uv run python src/engine/gates/notebooks/toehold_and/strength_window.py \\
        --fasta "path/to/mCherry original.txt" --pairs 3 --fold 8 --out window

**The question.** As designed, trigger A is the exact reverse complement of all 18 nt of
the main hairpin's ascending arm, so it beats that arm's own descending copy by a measured
6.6 kcal/mol and opens the hairpin whether or not trigger B has acted. That is the state-10
leak, and it is why ``separation`` is 0.00 on every candidate and why Kim 2019's
bench-validated gate fails the same gate with the same numbers.

``mainZ`` is the only free sequence in that arm — ``k1*`` is its reverse complement — so
choosing it is the one lever on the balance. The hypothesis is that a window exists:

    ``grip_with_x  <  stem  <  grip_alone``

trigger A loses to the stem on the 18-nt arm alone, and wins once trigger B frees ``sw_xs``
and hands it ``len_x`` more base pairs in the same helix.

**The answer, from this script: the window is empty.** Forty variants, ten trigger pairs,
spacers spread from 0.1 to 10.7 kcal/mol inside the proxy window — every one returns
``separation`` 0.00 with ``dG_open(10) == dG_open(11)``. Meanwhile ``dG_open(00)`` and
``dG_open(01)`` do differ, so the four tubes are responding to strand composition; it is
specifically trigger B that stops mattering once trigger A is present.

**Why the proxy promised what folding will not deliver.** Trigger A never has to beat the
*whole* stem. It only has to displace the sub-helix over ``main_pre*``, where its own
``main_pre`` is the switch's identical sequence *plus* the 3-nt ``bulge`` that the
descending ``AUG`` cannot pair. R7 grants trigger A those three base pairs by design, and
``mainZ`` sits on the far side of the bulge, so no choice of it can take them back. What
``mainZ`` does control — the 6 bp of ``k1*:mainZ`` nearest the start codon — is 6 of the 30
nt of ``W_rank``, not enough to hold the window shut once ``main_pre`` has been peeled.

**A retraction.** An earlier throwaway script reported this substitution reaching
``separation +2.97`` with ``A_M(10)`` 0.060 against ``A_M(11)`` 0.404, and that number was
carried into the notes as evidence the idea worked. It was a **state-labelling error**: its
"state 10" was the switch-alone tube. Re-measured through ``four_tube_observables`` on the
same pair and the same spacer (x@52, ``len_x`` 8, ``mainZ`` ``GCCGAC``), the result is
``separation`` -0.00 with ``A_M(10) = A_M(11) = 0.405``, and its "``A_M(10)`` 0.060" is
this pipeline's ``A_M(00)``. Decoupling ``k1*`` does lower ``A_M(10)`` from 0.522 to 0.405,
but it never separates state 10 from state 11.

**What this run produces, and why it is still worth running.** Spacers are **stratified
across the margin range** rather than ranked, so the output is a curve — separation against
margin — and not a top-k list. That is what makes an empty window a *result*: separation
does not respond to the margin anywhere along a 10 kcal/mol sweep, which is a far stronger
statement than any single design failing. Both halves of the open question fall out of it:
how wide the window is, counted in spacers whose folded ``separation`` clears 1.5 kcal/mol
rather than in spacers the proxy liked, and whether a design inside it still turns **ON**,
which is what ``A_M(11)`` and ``dG_open_11`` say. Every pair's control row
(``mainZ = k1``, the design as it stands) is folded beside its variants. Re-run it against
any *other* lever — a longer stem, a bulge moved off the ``AUG``, a shortened trigger arm —
and it will answer the same question about that lever.

**This is a hypothesis being tested, not a metric being satisfied.** τ4a has been shown
unable to discriminate, so nothing here tunes designs to pass it. The claim was physical —
shorten trigger A's grip and the AND becomes thermodynamic — and it failed on the computer,
which is the cheapest place for it to fail.
"""

import argparse
import csv
import sys
from dataclasses import replace
from itertools import product
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

STATES = ("00", "01", "10", "11")


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def sweep_spacers(gate, trigger_a: str, len_x: int, rbs_loop: str) -> list[dict]:
    """Every 6-nt spacer, scored on the three energies. No folding.

    Rejects a spacer that puts an ``AUG`` in the 5' UTR — ``rbs_loop`` ends in A, so a
    spacer beginning ``UG`` makes one across the join — because that is a second start
    codon out of frame with the real one, and it is cheaper to exclude here than to
    discover after folding.
    """
    rows = []
    for letters in product("ACGU", repeat=gate.STEM_POST_BULGE_LEN):
        main_z = "".join(letters)
        if "AUG" in rbs_loop + main_z:
            continue
        stem, alone, with_x = gate.main_stem_energies(trigger_a, len_x, main_z)
        if None in (stem, alone, with_x):
            continue
        rows.append(
            {
                "main_z": main_z,
                "stem": stem,
                "grip_alone": alone,
                "grip_with_x": with_x,
                # positive: trigger A cannot win on the arm alone
                "margin_alone": alone - stem,
                # positive: trigger A wins once sw_xs is free
                "margin_with_x": stem - with_x,
            }
        )
    return rows


def in_window(row) -> bool:
    return row["margin_alone"] > 0.0 and row["margin_with_x"] > 0.0


def stratify(rows: list[dict], wanted: int) -> list[dict]:
    """``wanted`` spacers spread evenly across the window's margin range.

    Ranking by margin and folding the top few answers a different question — it finds the
    best spacer the proxy can name, and the proxy has already been shown not to predict
    ``separation``. Spreading the sample across the range instead measures whether
    ``separation`` depends on the margin at all, which is what "how wide is the window"
    asks. Deterministic: sorted by margin, then evenly spaced by index.
    """
    ordered = sorted(rows, key=lambda r: min(r["margin_alone"], r["margin_with_x"]))
    if wanted >= len(ordered):
        return ordered
    step = (len(ordered) - 1) / (wanted - 1) if wanted > 1 else 0
    return [ordered[round(i * step)] for i in range(wanted)]


def with_spacer(gate, switch, main_z: str):
    """The same switch with ``mainZ`` and ``k1*`` replaced, lengths unchanged.

    Rebuilt by substitution rather than by re-running ``assemble``, because ``assemble``
    derives ``mainZ`` from trigger A by design; this is the one place that choice is
    deliberately overridden, and the point of the experiment is to override it.
    """
    k_start, k_end = switch.domains["k1_star"]
    z_start, z_end = switch.domains["main_z"]
    if k_end - k_start != len(main_z) or z_end - z_start != len(main_z):
        raise ValueError(
            f"spacer is {len(main_z)} nt, domains are {k_end - k_start}/{z_end - z_start}"
        )
    sequence = list(switch.sequence)
    for offset, base in enumerate(sq.reverse_complement(main_z)):
        sequence[k_start + offset] = base
    for offset, base in enumerate(main_z):
        sequence[z_start + offset] = base
    return replace(switch, sequence="".join(sequence))


def fold_row(gate, switch, trigger_a: str, trigger_b: str, row: dict) -> dict:
    """Four tubes on one patched switch, flattened into the row."""
    o = gate.four_tube_observables(switch, trigger_a, trigger_b)
    row.update({f"dG_open_{s}": o[f"dG_open_{s}"] for s in STATES})
    row.update({f"A_M_{s}": o[f"A_M_{s}"] for s in STATES})
    row["separation"] = o["separation"]
    row["dG_bind_B"] = o["dG_bind_B"]
    row["switch"] = switch.sequence
    return row


def _fmt(value, width=7, places=2) -> str:
    return f"{value:>{width}.{places}f}" if value is not None else " " * (width - 1) + "-"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pairs", type=int, default=3, help="trigger pairs to sweep")
    parser.add_argument(
        "--fold",
        type=int,
        default=8,
        help="in-window spacers to fold per pair, spread across the margin range",
    )
    parser.add_argument("--out", default="window", help="CSV prefix, written beside this file")
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    transcript = read_fasta(args.fasta)
    rbs_loop = gate.RBS_FLANK + gate.RBS_PROKARYOTIC

    pairs = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        pairs.append(pair)
    pairs.sort(key=lambda p: (-p.len_x, -p.gap()))
    pairs = pairs[: args.pairs]
    print(
        f"transcript {len(transcript)} nt · {len(pairs)} pairs · 4096 spacers swept each, "
        f"{args.fold} folded"
    )

    rows: list[dict] = []
    for pair in pairs:
        trigger_a = transcript[slice(*pair.window_a())]
        trigger_b = transcript[slice(*pair.window_b())]
        stem = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)[0]
        base = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)

        swept = sweep_spacers(gate, trigger_a, pair.len_x, rbs_loop)
        window = [r for r in swept if in_window(r)]
        widths = [min(r["margin_alone"], r["margin_with_x"]) for r in window]

        print(f"\n=== pair x@{pair.x_start} len_x={pair.len_x} {stem.scheme} ===")
        print(f"  spacers evaluated {len(swept)}   inside the proxy window {len(window)}")
        if widths:
            print(f"  proxy margin: narrowest {min(widths):.2f}, widest {max(widths):.2f} kcal/mol")
        print(
            f"\n  {'mainZ':<8}{'margin':>8}{'stem':>8}{'alone':>8}{'withx':>8}"
            + "".join(f"{'dG' + s:>8}" for s in STATES)
            + f"{'sep':>7}{'A_M10':>7}{'A_M11':>7}"
        )

        control = {
            "main_z": base.sequence[slice(*base.domains["main_z"])],
            "role": "control",
            "stem": None,
            "grip_alone": None,
            "grip_with_x": None,
            "margin_alone": None,
            "margin_with_x": None,
        }
        candidates = [(control, base)]
        for row in stratify(window, args.fold):
            row["role"] = "variant"
            candidates.append((row, with_spacer(gate, base, row["main_z"])))

        for row, switch in candidates:
            row.update(x_start=pair.x_start, xstar_start=pair.xstar_start, len_x=pair.len_x)
            row["scheme"] = stem.scheme
            fold_row(gate, switch, trigger_a, trigger_b, row)
            rows.append(row)
            margin = (
                min(row["margin_alone"], row["margin_with_x"])
                if row["margin_alone"] is not None
                else None
            )
            print(
                f"  {row['main_z']:<8}{_fmt(margin, 8)}{_fmt(row['stem'], 8)}"
                f"{_fmt(row['grip_alone'], 8)}{_fmt(row['grip_with_x'], 8)}"
                + "".join(_fmt(row[f"dG_open_{s}"], 8) for s in STATES)
                + f"{_fmt(row['separation'], 7)}{_fmt(row['A_M_10'], 7, 3)}"
                f"{_fmt(row['A_M_11'], 7, 3)}"
                + ("   <- control" if row["role"] == "control" else "")
            )

    if not rows:
        print("\nNo pair produced a candidate. Nothing to order.")
        return 0

    path = output_dir / f"{args.out}_candidates.csv"
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows written to {path}")

    passing = [
        r
        for r in rows
        if r["role"] == "variant"
        and r["separation"] is not None
        and r["separation"] > 1.5
        and r["A_M_10"] is not None
        and r["A_M_10"] < 0.2
    ]
    variants = [r for r in rows if r["role"] == "variant"]
    print(
        f"{len(passing)} of {len(variants)} folded variants reach separation > 1.5 with "
        f"A_M(10) < 0.2 — state 10 included, no gate dropped."
    )
    if passing:
        best = max(passing, key=lambda r: r["separation"])
        print(
            f"widest so far: x@{best['x_start']} mainZ={best['main_z']} "
            f"separation {best['separation']:.2f}, A_M(10) {best['A_M_10']:.3f}, "
            f"A_M(11) {best['A_M_11']:.3f}, dG_open(11) {best['dG_open_11']:.2f}"
        )
        print(
            "Read A_M(11) and dG_open_11 as the second half of the question: a design "
            "inside the window is only worth building if it still turns ON."
        )
    else:
        print(
            "The window is empty on these pairs. That is a real result and not a failure "
            "of the run: it says the proxy's margin does not buy separation here, and the "
            "pairs themselves have to be varied, not just the spacer."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
