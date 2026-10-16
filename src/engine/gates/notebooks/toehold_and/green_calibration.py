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

    # The sheet name was hard-coded to "Table S1", which quietly limited every calibration
    # to Green's 168 FIRST-GENERATION switches. Table S3's forward-engineered set carries
    # the same four columns and is a different architecture generation, so it is a genuine
    # second test rather than more of the same. Any "Table S…" sheet is accepted.
    book = openpyxl.load_workbook(path, data_only=True)
    names = [n for n in book.sheetnames if n.strip().lower().startswith("table s")]
    sheet = book[names[0] if names else book.sheetnames[0]]
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


def load_vista_csv(path: str) -> list[dict]:
    """Robson/Green 2026 Supplementary Table 4 -- the ~190-switch VISTA library.

    A different file shape from Table S1, so a separate reader rather than a flag inside
    ``load_switches``: this one is a CSV with named columns and it carries TWO measured
    ratios per switch, for the truncated and the full-length reporter mRNA.

    **The T7 promoter is stripped here.** Every ``Switch Sequence`` in this table is the
    DNA template including ``…TAATACGACTCACTATA`` upstream of the +1, so the transcript
    begins at the ``GGG`` that follows it. Scoring the template as if it were the RNA would
    fold 22 nt of promoter into the OFF state and shift every window by 22, which folds and
    scores and reports a plausible number -- exactly the class of error that does not raise.
    After stripping, all 189 rows are 119 nt, which is the check that the offset is right.

    ``on_off`` is the FULL-length ratio, because that is the construct the paper treats as
    the real one; the truncated ratio travels beside it as ``on_off_trunc`` so neither has
    to be re-derived later.
    """
    promoter = "TAATACGACTCACTATA"
    rows = []
    with open(path, encoding="utf-8-sig") as handle:
        for record in csv.DictReader(handle):
            raw = (record.get("Switch Sequence") or "").strip().upper()
            trigger = (record.get("Target Sequence") or "").strip().upper()
            if not raw or not trigger:
                continue
            cut = raw.find(promoter)
            if cut < 0:
                continue
            switch = sq.to_rna(raw[cut + len(promoter) :])
            trigger = sq.to_rna(trigger)
            if not sq.is_valid_rna(switch) or not sq.is_valid_rna(trigger):
                continue

            def number(key: str, source: dict = record) -> float | None:
                value = (source.get(key) or "").strip()
                try:
                    return float(value)
                except ValueError:
                    return None

            full, trunc = number("ON OFF Full"), number("ON OFF Truncated")
            if full is None:
                continue
            rows.append(
                {
                    "switch_number": record.get("Index"),
                    "on_off": full,
                    "on_off_trunc": trunc,
                    "switch": switch,
                    "trigger": trigger,
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

    # Green's own best predictor, for a like-for-like comparison. Table S3 defines
    # "dG RBS-Linker" as the free energy of the sequence from the FIRST BASE OF THE LOOP to
    # the LAST BASE OF THE 21-NT LINKER. It is a single-state folding energy of a
    # subsequence -- how structured that region is -- and NOT a difference between two
    # states, which is what makes it a different quantity from our dG_open rather than a
    # rewording of it. The loop begins where the ascending stem ends and the linker ends
    # 21 nt after the descending stem; both are fixed offsets in this architecture.
    loop_start = rbs - 3  # the pre-RBS bases that open the 11-nt loop
    linker_end = min(len(switch), aug + 3 + 9 + 21)
    rbs_linker = None
    if 0 <= loop_start < linker_end <= len(switch):
        rbs_linker = folder.mfe(switch[loop_start:linker_end]).energy

    # A_M over the descending arm, the analogue of our main_z+AUG+main_pre span.
    arm = (aug - 6, aug + 3 + 9)
    off_matrix = folder.pooled_pair_probabilities(switch)
    on_matrix = folder.pooled_pair_probabilities(f"{switch}&{trigger}")

    # The same IED identity applied to the TOEHOLD -- the switch's own single-stranded 5'
    # end, which is what A(r2*|00) measures on our gate. Green's first generation used a
    # 12-nt toehold and tsgen2 15, and this table mixes both, so three lengths are reported
    # rather than one guess being made load-bearing.
    ied_toe = {}
    for L in (12, 15, 18):
        if L <= len(switch):
            ied_toe[f"ied_toehold{L}_off"] = 1.0 - _mean_unpaired(off_matrix, 0, L)
            # ``k_analogue`` -- and it IS an analogue, not the same quantity. On our
            # two-input gate K is CONDITIONAL: free(x*|01) - free(x*|00), how much the
            # OTHER trigger liberates the site trigger A needs to nucleate on. A
            # single-input switch has no other trigger, so nothing conditions it; the
            # nearest quantity is the UNCONDITIONAL one, how open the switch's own
            # toehold is in the OFF state. Same physical question -- is the nucleation
            # foothold available when the trigger arrives -- with the conditioning
            # dropped, which is exactly what makes it an analogue rather than a
            # measurement of K.
            #
            # Measured, it predicts nothing. Against ON/OFF: Spearman +0.023 / -0.032 /
            # -0.037 for L = 12 / 15 / 18 on the 168-switch table, leave-one-out stable
            # to +/-0.02, so that null is solid rather than underpowered. On the 13
            # forward-engineered switches it is -0.15 to -0.30, the wrong sign and not
            # stable under leave-one-out. This is not a no-variance artefact: the
            # analogue spans 0.39 to 0.97 with sd 0.09-0.13.
            #
            # So it is reported, not ranked on -- and any objective built on K inherits
            # that null, since this is the only set where K's analogue can be tested.
            ied_toe[f"k_analogue{L}"] = _mean_unpaired(off_matrix, 0, L)

    # VISTA ranks on Ideal Ensemble Defect, and its specified structure for a region that
    # must be free is "completely unpaired" -- so over such a region the IED collapses to
    # the MEAN BASE-PAIRING probability, 1 - mean_unpaired. That identity is what makes
    # this testable here without NUPACK and without inventing a target structure.
    #
    # VISTA takes it over the toehold-linker; Green's own predictor folds the same stretch
    # and reports its MFE. Both are computed over the identical span, so the comparison is
    # between the two STATISTICS rather than between two regions.
    ied_off = ied_on = None
    if rbs_linker is not None:
        ied_off = 1.0 - _mean_unpaired(off_matrix, loop_start, linker_end)
        ied_on = 1.0 - _mean_unpaired(on_matrix, loop_start, linker_end)
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
    # --- the OFF cluster ---------------------------------------------------------------
    # dG_OFF: the closed switch's own folding energy, one value per switch and NOT a
    # per-state quantity -- there is only one OFF structure to have an energy.
    folded = folder.mfe(switch)
    dg_off_mfe = folded.energy
    # d_OFF: the ensemble defect of the OFF state. Green's switches come with no INTENDED
    # dot-bracket, so there is no target to measure against the way our own generator has
    # one. Scored against the switch's OWN MFE structure instead, which makes it "how
    # concentrated is the ensemble on its single most likely fold" rather than "did we build
    # what we meant to". Different question, so it is named apart from structure_deviation,
    # and it is NORMALISED by length -- the raw defect is a length bias, and this table
    # mixes 119-nt and 145-nt switches.
    d_off_norm = None
    if folded.structure and len(folded.structure) == len(switch):
        raw = folder.ensemble_defect(switch, folded.structure)
        d_off_norm = None if raw is None else raw / len(switch)

    narrow_off = folder.p_open(switch, (aug - 6, aug + 3))
    narrow_on = folder.p_open(f"{switch}&{trigger}", (aug - 6, aug + 3))
    return {
        **{k: row[k] for k in ("switch_number", "on_off", "on_off_trunc") if k in row},
        "aug_index": aug,
        "p_open_off": off,
        "p_open_on": on,
        "dG_open_off": dg_off,
        "dG_open_on": dg_on,
        "separation": dg_off - dg_on,
        "A_M_off": a_m_off,
        "A_M_on": a_m_on,
        "A_M_gain": None if a_m_on is None or a_m_off is None else a_m_on - a_m_off,
        # The ratio beside the difference, because the objectives rank on the ratio and it
        # was never a column here -- every comparison of the two forms so far was done by
        # hand on the CSV afterwards, and only ever for Table S1.
        "A_M_ratio": None if a_m_on is None or not a_m_off else a_m_on / a_m_off,
        **ied_toe,
        "dG_rbs_linker": rbs_linker,
        "ied_rbs_linker_off": ied_off,
        "ied_rbs_linker_on": ied_on,
        "ied_rbs_linker_gain": None if ied_on is None or ied_off is None else ied_off - ied_on,
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
        "dG_OFF": dg_off_mfe,
        "d_OFF": d_off_norm,
        "switch_len": len(switch),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", default=TABLE_S1)
    parser.add_argument(
        "--csv",
        default="",
        help="score Robson/Green 2026 Supplementary Table 4 instead of an xlsx Table S "
        "sheet -- the VISTA library, read by load_vista_csv (which strips the T7 promoter)",
    )
    parser.add_argument("--limit", type=int, default=0, help="score only the first N")
    parser.add_argument("--out", default="green_calibration")
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    folder = FoldEngine(37.0)

    switches = load_vista_csv(args.csv) if args.csv else load_switches(args.table)
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
        "dG_rbs_linker",
        "separation",
        "narrow_sep",
        "dG_open_off",
        "dG_open_on",
        "A_M_on",
        "A_M_gain",
        "A_M_ratio",
        "A_M_off",
        "ied_toehold12_off",
        "ied_toehold15_off",
        "ied_toehold18_off",
        "k_analogue12",
        "k_analogue15",
        "k_analogue18",
        "ied_rbs_linker_off",
        "ied_rbs_linker_on",
        "ied_rbs_linker_gain",
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
