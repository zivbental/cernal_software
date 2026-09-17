"""Does our ranking observable rank switches that were actually measured?

    uv run --with openpyxl python \\
        src/engine/gates/notebooks/toehold_and/green_calibration.py --out green

**The question, and why it has to be answered before any redesign.** Every architectural
choice we are weighing — shortening the trigger's invasion by 3 nt, a 1x1 bulge instead of
3x3, unequal stem lengths — would be evaluated with ``dG_open`` over ``W_rank``. If that
observable has no rank-order relationship with real performance, then comparing variants
with it is measuring nothing, and the redesign question cannot be answered computationally
at all. So this is the prior question.

**The test.** Green 2014 Table S1 gives 168 first-generation toehold switches with full
switch and trigger RNA sequences and a measured ON/OFF ratio each, spanning roughly 1 to
265. They are single-input switches, so they cannot validate an AND gate — but our OFF/ON
contrast is exactly the quantity a single-input switch is built to maximise, so the
comparison is fair on its own terms:

* ``dG_open_off`` — the switch alone, over ``W_rank``;
* ``dG_open_on``  — the switch with its cognate trigger, over the same window;
* ``separation``  — the difference, which is what we rank our own designs on.

Then Spearman rank correlation against the measured ON/OFF. Spearman rather than Pearson
because the claim under test is ordering ("would our score have picked the good ones?"),
not linearity, and because the measured ratios span two orders of magnitude.

**Why ``W_rank`` is applied unchanged.** Green's layout puts the RBS at the 3' end of the
loop and the start codon 6 nt later, the same spacing we use, so offsets -17..+13 around
their ``AUG`` select the analogous region: the tail of the loop, the 6 nt before the start
codon, the codon itself and the first four codons of the reporter. Applying our own window
definition is the point — we are testing our observable, not reimplementing theirs.

**What the outcome means, decided in advance so the result cannot be rationalised after
the fact.**

* A strong positive correlation says ``dG_open`` is a valid ranking axis and the
  architecture questions can be settled computationally.
* A correlation near zero says our window is measuring something real performance does not
  depend on. That would corroborate the reading of VISTA's specified ON-state structure,
  which keeps the 6-bp upper stem **paired** and frees only the start codon — i.e. a working
  switch never opens all 30 nt of ``W_rank``, and demanding that it does asks the wrong
  question.
* A *negative* correlation would say the window is actively misleading.

No weight is fitted and no threshold is tuned here. This is a correlation check on an
existing observable, which is a different thing from fitting a model to data and is
permitted where fitting is not.
"""

import argparse
import csv
import math
import re
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.gates.toehold import _mean_unpaired  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402

TABLE_S1 = (
    "C:/Users/Dell/OneDrive - mail.tau.ac.il/IGEM/Toehold/Prokaryotic And Gate/"
    "Prokaryotic-And-Gate/Docs/Green 2014/Table S1. Sequence and Performance Information "
    "for First-Generation Toehold Switches, Related Systems, and PCR Primers, Related to "
    "Figures 1 and S1.xlsx"
)
RBS = "AGAGGAGA"
#: Green holds the RBS-to-start spacing at 6 nt, the same as ours, so the start codon is a
#: fixed offset from the end of the Shine-Dalgarno sequence rather than something to search
#: for -- searching would find the first AUG, which in several switches is upstream.
RBS_TO_AUG = 6


def load_switches(path: str) -> list[dict]:
    """Every row of Table S1 sections A and B that carries a sequence pair and a ratio."""
    import openpyxl

    sheet = openpyxl.load_workbook(path, data_only=True)["Table S1"]
    rows = []
    for index in range(1, sheet.max_row + 1):
        number, ratio, switch, trigger = (sheet.cell(index, c).value for c in range(1, 5))
        if not (isinstance(switch, str) and isinstance(trigger, str)):
            continue
        if not sq.is_valid_rna(switch.strip()) or not sq.is_valid_rna(trigger.strip()):
            continue
        measured = None
        if isinstance(ratio, int | float):
            measured = float(ratio)
        elif isinstance(ratio, str):
            match = re.match(r"\s*([0-9.]+)", ratio)
            measured = float(match.group(1)) if match else None
        if measured is None:
            continue
        rows.append(
            {
                "switch_number": number,
                "on_off": measured,
                "switch": switch.strip(),
                "trigger": trigger.strip(),
            }
        )
    return rows


def spearman(pairs: list[tuple[float, float]]) -> tuple[float, int]:
    """Rank correlation, average ranks for ties. Returns ``(rho, n)``."""

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        position = 0
        while position < len(order):
            stop = position
            while stop + 1 < len(order) and values[order[stop + 1]] == values[order[position]]:
                stop += 1
            shared = (position + stop) / 2 + 1
            for index in range(position, stop + 1):
                out[order[index]] = shared
            position = stop + 1
        return out

    xs = ranks([p[0] for p in pairs])
    ys = ranks([p[1] for p in pairs])
    n = len(pairs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    sx = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    sy = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    return (cov / (sx * sy) if sx and sy else math.nan), n


def score(folder: FoldEngine, row: dict) -> dict | None:
    """Our four-tube observables, reduced to the two tubes a one-input switch has."""
    switch, trigger = row["switch"], row["trigger"]
    rbs = switch.find(RBS)
    if rbs < 0:
        return None
    aug = rbs + len(RBS) + RBS_TO_AUG
    if switch[aug : aug + 3] != "AUG":
        return None
    start, end = aug - 17, aug + 13 + 1
    if start < 0 or end > len(switch):
        return None

    off = folder.p_open(switch, (start, end))
    on = folder.p_open(f"{switch}&{trigger}", (start, end))
    if off is None or on is None:
        return None
    rt = folder.rt
    dg_off, dg_on = -rt * math.log(off), -rt * math.log(on)

    # A_M over the descending arm, the analogue of our main_z+AUG+main_pre span.
    arm = (aug - 6, aug + 3 + 9)
    off_matrix = folder.pooled_pair_probabilities(switch)
    on_matrix = folder.pooled_pair_probabilities(f"{switch}&{trigger}")
    a_m_off = _mean_unpaired(off_matrix, *arm)
    a_m_on = _mean_unpaired(on_matrix, *arm)

    # The discriminating question: is the fault the WINDOW or the STATISTIC? Take the mean
    # over the very same W_rank the joint p_open uses, and take the joint over a span as
    # narrow as the start codon. If the mean works on W_rank, the window is fine and the
    # joint probability is the problem; if only the narrow joint works, it is the window.
    mean_wrank_off = _mean_unpaired(off_matrix, start, end)
    mean_wrank_on = _mean_unpaired(on_matrix, start, end)
    aug_off = _mean_unpaired(off_matrix, aug, aug + 3)
    aug_on = _mean_unpaired(on_matrix, aug, aug + 3)
    narrow_off = folder.p_open(switch, (aug - 6, aug + 3))
    narrow_on = folder.p_open(f"{switch}&{trigger}", (aug - 6, aug + 3))
    return {
        **{k: row[k] for k in ("switch_number", "on_off")},
        "aug_index": aug,
        "p_open_off": off,
        "p_open_on": on,
        "dG_open_off": dg_off,
        "dG_open_on": dg_on,
        "separation": dg_off - dg_on,
        "A_M_off": a_m_off,
        "A_M_on": a_m_on,
        "A_M_gain": None if a_m_on is None or a_m_off is None else a_m_on - a_m_off,
        "mean_wrank_off": mean_wrank_off,
        "mean_wrank_on": mean_wrank_on,
        "mean_wrank_gain": None
        if mean_wrank_on is None or mean_wrank_off is None
        else mean_wrank_on - mean_wrank_off,
        "aug_off": aug_off,
        "aug_on": aug_on,
        "aug_gain": None if aug_on is None or aug_off is None else aug_on - aug_off,
        "narrow_sep": None
        if not narrow_off or not narrow_on
        else -rt * math.log(narrow_off) + rt * math.log(narrow_on),
        "switch_len": len(switch),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", default=TABLE_S1)
    parser.add_argument("--limit", type=int, default=0, help="score only the first N")
    parser.add_argument("--out", default="green_calibration")
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    folder = FoldEngine(37.0)

    switches = load_switches(args.table)
    print(f"{len(switches)} switches with a sequence pair and a measured ON/OFF")
    if args.limit:
        switches = switches[: args.limit]

    rows, skipped = [], 0
    for index, row in enumerate(switches):
        scored = score(folder, row)
        if scored is None:
            skipped += 1
            continue
        rows.append(scored)
        if index % 20 == 0:
            print(f"  {index + 1}/{len(switches)}", flush=True)
    print(f"scored {len(rows)}, skipped {skipped} (no RBS, or no AUG 6 nt after it)")

    path = output_dir / f"{args.out}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"-> {path}\n")

    print("Spearman rank correlation against measured ON/OFF:")
    for name in (
        "separation",
        "narrow_sep",
        "dG_open_off",
        "dG_open_on",
        "A_M_on",
        "A_M_gain",
        "A_M_off",
        "mean_wrank_on",
        "mean_wrank_gain",
        "aug_on",
        "aug_gain",
    ):
        pairs = [(r[name], r["on_off"]) for r in rows if r.get(name) is not None]
        rho, n = spearman(pairs)
        # Two-sided significance, normal approximation; fine at n ~ 170.
        z = abs(rho) * math.sqrt(n - 1)
        print(f"  {name:<14} rho {rho:+.3f}   n {n:>4}   |z| {z:5.2f}")

    ordered = sorted(rows, key=lambda r: -r["separation"])
    print("\n  our top 10 by separation, with what they actually measured:")
    for r in ordered[:10]:
        print(
            f"    switch {r['switch_number']!s:>4}  separation {r['separation']:6.2f}"
            f"   measured ON/OFF {r['on_off']:7.1f}"
        )
    best = sorted(rows, key=lambda r: -r["on_off"])[:10]
    print("\n  the 10 that actually performed best, and where we ranked them:")
    rank_by_sep = {id(r): i + 1 for i, r in enumerate(ordered)}
    for r in best:
        print(
            f"    switch {r['switch_number']!s:>4}  measured {r['on_off']:7.1f}"
            f"   our rank {rank_by_sep[id(r)]:>4} of {len(rows)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
