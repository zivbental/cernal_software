"""Silence an out-of-frame AUG by editing ``main_z``, which is a free design choice.

    uv run python src/engine/gates/notebooks/toehold_and/aug_rescue.py
    uv run python src/engine/gates/notebooks/toehold_and/aug_rescue.py --min-ratio 100 --apply out

The out-of-frame AUG filter removes 20% of the population, including the sweep's second-best A_M
ratio design at 315.6. Measured on the 13 designs with an A_M ratio above 100 that carry one, the
spurious AUG is at switch position **123 in every single case** -- five nucleotides before the real
start, inside ``main_z``.

That matters because of which domain it is. ``main_z`` is one of the three domains the generator
CHOOSES rather than derives: it is 6 nt picked to satisfy ``ddG_pref >= 0`` against ``k1_star``, and
it is not the reverse complement of any trigger. So a base there can be changed without touching
either trigger window, which is exactly the thing a patch is normally not allowed to do.

The replacement still has to earn its place, so every candidate edit is re-scored in all four tubes
rather than assumed harmless: a change inside ``main_z`` sits in the middle of the A_M window and
directly in the ribosome's path.
"""

import argparse
import csv
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

FIELDS = (
    "switch",
    "switch_before",
    "edit",
    "pair",
    "geom",
    "closure",
    "len_x",
    "a_start",
    "a_end",
    "b_start",
    "b_end",
    "oof_augs_before",
    "oof_augs_after",
    "f2_before",
    "f2_after",
    "open_11_before",
    "open_11_after",
    "andness_before",
    "andness_after",
    "barrier_after",
)


def a_m_per_tube(folder: FoldEngine, switch: str, trig_a: str, trig_b: str) -> dict[str, float]:
    dom = oe.domains(switch)
    lo, hi = dom["main_z"][0], dom["main_pre"][1]
    out = {}
    for state, strands in (
        ("00", switch),
        ("01", f"{switch}&{trig_b}"),
        ("10", f"{switch}&{trig_a}"),
        ("11", f"{switch}&{trig_a}&{trig_b}"),
    ):
        matrix = folder.pooled_pair_probabilities(strands)
        out[state] = sum(1.0 - sum(matrix[i]) for i in range(lo, hi)) / (hi - lo)
    return out


def ratio(values: dict[str, float]) -> float | None:
    worst = max(values[s] for s in ("00", "01", "10"))
    return None if worst <= 0 else values["11"] / worst


def candidate_edits(switch: str) -> list[tuple[int, str, str]]:
    """Single-base edits inside ``main_z`` that remove every out-of-frame AUG.

    Only ``main_z`` is touched. The AUG is reported at position 123 in every case measured, which
    is inside it, but the span is read from the layout rather than hard-coded -- a 161-nt and a
    165-nt switch put ``main_z`` in different places.
    """
    dom = oe.domains(switch)
    lo, hi = dom["main_z"]
    out = []
    for index in range(lo, hi):
        for base in "ACGU":
            if base == switch[index]:
                continue
            trial = switch[:index] + base + switch[index + 1 :]
            if op.out_of_frame_augs(trial):
                continue
            # The real start must survive, and no new in-frame stop may appear.
            aug = dom["aug"]
            if trial[aug[0] : aug[1]] != "AUG":
                continue
            coding = trial[aug[0] :]
            if any(
                coding[i : i + 3] in ("UAA", "UAG", "UGA") for i in range(0, len(coding) - 2, 3)
            ):
                continue
            out.append((index, switch[index], base))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-ratio", type=float, default=100.0)
    parser.add_argument("--apply", default="", help="write to results/<name>.csv")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help="include designs whose window covers a corrected base; they need "
        "drift_repair.py as well, so the rescue alone does not make them orderable",
    )
    args = parser.parse_args(argv)

    folder = FoldEngine(37.0)
    transcript = read_fasta(NB / "mCherry_original.txt")
    rows = op.load(NB / "results")
    targets = [
        r
        for r in rows
        if r.get("f2")
        and r["f2"] >= args.min_ratio
        and op.out_of_frame_augs(r["switch"])
        and (args.allow_drift or not op.covers_drift(r))
    ]
    targets.sort(key=lambda r: -r["f2"])
    if args.limit:
        targets = targets[: args.limit]
    print(
        f"  {len(targets)} design(s) with A_M ratio >= {args.min_ratio:g}, an out-of-frame AUG,"
        f" and a clean transcript\n"
    )

    written = []
    for row in targets:
        switch = row["switch"]
        trig_a = transcript[int(row["a_start"]) : int(row["a_end"])]
        trig_b = transcript[int(row["b_start"]) : int(row["b_end"])]
        edits = candidate_edits(switch)
        print(
            f"  {row['pair_label']:20s} {row['geom'][:6]:7s} A_M ratio {row['f2']:8.1f}"
            f"  closure {row['closure']}"
        )
        if not edits:
            print("      no single-base edit inside main_z silences it")
            continue
        before = a_m_per_tube(folder, switch, trig_a, trig_b)
        base_ratio = ratio(before)
        print(
            f"      {len(edits)} candidate edit(s) in main_z; A_M ratio recomputed here"
            f" = {base_ratio:.1f}"
        )
        best = None
        for index, was, now in edits:
            trial = switch[:index] + now + switch[index + 1 :]
            after = a_m_per_tube(folder, trial, trig_a, trig_b)
            new_ratio = ratio(after)
            scored = oe.score_design(folder, trial, trig_a, trig_b, on_ceiling=None)
            keep = (
                new_ratio is not None
                and scored.get("open_11") is not None
                and scored["open_11"] <= op.ON_CEILING
                and scored.get("andness") is not None
                and scored["andness"] <= op.GATING
            )
            flag = "ok " if keep else "   "
            print(
                f"      {flag}{was}{index}{now}:  A_M ratio {new_ratio:8.1f}"
                f"  open_11 {scored.get('open_11', float('nan')):6.2f}"
                f"  SEP {scored.get('andness', float('nan')):7.2f}"
                f"  barrier {scored.get('barrier', float('nan')):6.2f}"
            )
            if keep and (best is None or new_ratio > best[1]):
                best = ((index, was, now), new_ratio, scored, trial)
        if best is None:
            print("      every edit breaks a threshold")
            continue
        (index, was, now), new_ratio, scored, trial = best
        print(f"      BEST: {was}{index}{now} keeps A_M ratio {new_ratio:.1f} and passes")
        written.append(
            {
                "switch": trial,
                "switch_before": switch,
                "edit": f"{was}{index}{now}",
                "pair": row["pair"],
                "geom": row["geom"],
                "closure": row["closure"],
                "len_x": row["len_x"],
                "a_start": row["a_start"],
                "a_end": row["a_end"],
                "b_start": row["b_start"],
                "b_end": row["b_end"],
                "oof_augs_before": op.out_of_frame_augs(switch),
                "oof_augs_after": op.out_of_frame_augs(trial),
                "f2_before": round(base_ratio, 3) if base_ratio else None,
                "f2_after": round(new_ratio, 3),
                "open_11_before": row["open_11f"],
                "open_11_after": scored.get("open_11"),
                "andness_before": row["f1"],
                "andness_after": scored.get("andness"),
                "barrier_after": scored.get("barrier"),
            }
        )

    if args.apply and written:
        path = NB / "results" / f"{args.apply}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(FIELDS), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(written)
        print(f"\n  wrote {len(written)} rescued design(s) to {path.name}")
        print("  These are NEW switch sequences and are not joined into the panel automatically.")
    elif args.apply:
        print("\n  nothing rescued, nothing written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
