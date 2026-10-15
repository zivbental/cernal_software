"""What the negative barrier values are, measured on the designs that produce them.

A review raised it as a contradiction: an activation barrier is the highest point of a
path *above* its starting state, so it cannot be negative, and 10 to 12% of our values
are. The question is answerable by rebuilding the designs that produce them and printing
the saddle and the starting energy separately, which this does.

Run::

    uv run python tools/barrier_sign.py --rows docs/assets/barrier/designs_0.csv -n 6
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys

import RNA

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import barrier_designs as bd

from engine import sequences as sq
from engine.domain import Host
from engine.gates.toehold import _CrossGenePair
from engine.gates.tools.folding import FoldEngine
from engine.transcriptome import load_transcriptome


def rebuild(row, gates, transcripts):
    """The switch, trigger A, and the two structures the path runs between."""
    geom = bd.GEOM.get(row["geom_label"], row["geom_label"])
    gate = gates[geom]
    foot_a, foot_b = gate.role_footprints()
    len_x = int(float(row["len_x"]))
    pair = _CrossGenePair(
        gene_a=row["gene_a"],
        gene_b=row["gene_b"],
        x_start=int(float(row["x_start"])),
        xstar_start=int(float(row["xstar_start"])),
        len_x=len_x,
        arm_len=gate.ARM_LEN,
        invasion_len=gate.SECONDARY_INVASION_LEN,
        toehold_b_len=gate.TOEHOLD_B_LEN,
    )
    a0, a1 = pair.window_a()
    b0, b1 = pair.window_b()
    wa, wb = transcripts[row["gene_a"]][a0:a1], transcripts[row["gene_b"]][b0:b1]
    if len(wa) != foot_a or len(wb) != foot_b:
        return None
    stems = list(gate.secondary_stems(wa, wb, len_x))
    index = int(float(row["stem_index"]))
    if index >= len(stems):
        return None
    base = gate.assemble(wa, wb, len_x, stems[index])
    closure = next((c for c in gate.CLOSURES if c[0] == row["closure"]), None)
    upper3 = next((u for u in gate.UPPER3 if u[0] == row["upper3"]), None)
    lower3 = next((low for low in gate.LOWER3 if low[0] == row["lower3"]), None)
    if None in (closure, upper3, lower3):
        return None
    patched = gate._apply_axes(base, closure, upper3, lower3)
    if patched is None:
        return None
    built = patched[0] if isinstance(patched, tuple) else patched
    switch, off = built.sequence, built.dot_bracket
    target, positions = bd.landing_target(
        off, built.domains["sw_x"], built.domains["sw_xs"], len(switch) + gate.ARM_LEN, len_x
    )
    end = list(target + "." * len(wa))
    for position in positions:
        end[position] = ")"
    return f"{switch}&{wa}", off + "." * len(wa), "".join(end)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose the barrier's sign.")
    parser.add_argument("--rows", type=pathlib.Path, required=True)
    parser.add_argument("-n", type=int, default=6)
    args = parser.parse_args(argv)

    rows = list(csv.DictReader(args.rows.open(newline="", encoding="utf-8")))
    negative = [r for r in rows if r["b_10"] not in ("", "None") and float(r["b_10"]) < 0]
    positive = [r for r in rows if r["b_10"] not in ("", "None") and float(r["b_10"]) > 2]
    print(f"  {args.rows.name}: {len(rows)} rows, {len(negative)} negative, showing up to {args.n}")

    folder = FoldEngine(37.0)
    book = load_transcriptome(Host.ECOLI)
    gates = {name: cls(Host.ECOLI, folder, None, None) for name, cls in bd.CLASSES.items()}
    transcripts = {sym: sq.to_rna(book[gid]) for sym, gid, _, _ in bd.GENE_PAIRS}
    transcripts |= {sym: sq.to_rna(book[gid]) for _, _, sym, gid in bd.GENE_PAIRS}

    print(
        f"\n  {'row':>4}  {'stored':>8}  {'saddle':>8}  "
        f"{'E(start)':>9}  {'E(end)':>8}  {'E(mfe)':>8}"
    )
    for label, sample in (("negative", negative[: args.n]), ("positive", positive[:2])):
        print(f"  -- {label} --")
        for row in sample:
            built = rebuild(row, gates, transcripts)
            if built is None:
                continue
            strands, start, end = built
            compound = RNA.fold_compound(strands)
            raw = compound.path_findpath_saddle(start, end, bd.CEILING)
            saddle = raw / 100.0
            e_start = compound.eval_structure(start)
            e_end = compound.eval_structure(end)
            _mfe_structure, e_mfe = compound.mfe()
            print(
                f"  {row['key'][:4]:>4}  {float(row['b_10']):8.2f}  {saddle:8.2f}  "
                f"{e_start:9.2f}  {e_end:8.2f}  {e_mfe:8.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
