"""The landing barrier for designs that EXIST in the grid, so the join is per design.

The first run measured one design per cell: the first stem the Pareto front happened to
return, with no lever applied. That design is in no grid row at all -- `closure` differs
from `closure_natural` on all 301,440 of them, and so does `upper3` -- so its barrier
could only be set against a cell median taken over hundreds of other designs. Comparing
one arbitrary molecule with the average of a thousand others is not a comparison.

Here each row of the grid names a design -- its cell, its stem index, and its three lever
settings -- and that design is rebuilt and measured. The barrier then sits beside the
equilibrium leak **of the same molecule**.

**Which designs, and why not the first N.** A sweep that walks the grid in order would
spend a day inside a handful of cells and answer nothing about whether the barrier
follows the design or the trigger pair. The selection instead covers the axes that could
plausibly move it: every lever level appears, every stem index that exists appears, and
the leak itself is sampled across its range rather than from one end. `--per-cell` then
caps how many designs any one cell contributes, so no cell can dominate.

Resumable by design key, so it is safe to kill and restart, and safe to run for a day.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import RNA  # noqa: E402

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import (  # noqa: E402
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
    _CrossGenePair,
)
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.transcriptome import load_transcriptome  # noqa: E402

GENE_PAIRS = (
    ("ggt", "b3447", "fadB", "b3846"),
    ("ggt", "b3447", "astC", "b1748"),
    ("ggt", "b3447", "aldA", "b1415"),
)
GEOM = {"arm18/inv18/capnone": "naive", "arm20/inv17/capAUA": "kim"}
CLASSES = {"naive": ProkaryoticToeholdAndGate, "kim": KimSecondaryArmToeholdAndGate}
CEILING = 20_000
FIELDS = (
    "key geom_label gene_a gene_b x_start xstar_start len_x stem_index "
    "closure upper3 lower3 switch_len leak b_10 s_10"
).split()


def partners(structure: str) -> dict[int, int]:
    stack: list[int] = []
    out: dict[int, int] = {}
    for i, symbol in enumerate(structure):
        if symbol == "(":
            stack.append(i)
        elif symbol == ")":
            j = stack.pop()
            out[i], out[j] = j, i
    return out


def landing_target(off, lock, xstar, a_x_start, len_x):
    """`off` with the lock released and x* paired to trigger A's own copy of x."""
    bonds = partners(off)
    out = list(off)
    for lo, hi in (lock, xstar):
        for i in range(lo, hi):
            j = bonds.get(i)
            if j is not None:
                out[i] = out[j] = "."
    lo_xs, _ = xstar
    for k in range(len_x):
        out[lo_xs + k] = "("
    return "".join(out), [a_x_start + len_x - 1 - k for k in range(len_x)]


def barrier(strands: str, start: str, end: str) -> tuple[float | None, float]:
    compound = RNA.fold_compound(strands)
    began = time.time()
    raw = compound.path_findpath_saddle(start, end, CEILING)
    elapsed = time.time() - began
    if raw is None or raw >= CEILING:
        return None, elapsed
    return raw / 100.0 - compound.eval_structure(start), elapsed


def choose(grid: pathlib.Path, per_cell: int) -> list[dict]:
    """Designs spread over the axes that could move the barrier, not the first N.

    Sorted inside each cell by the equilibrium leak and then taken at an even stride, so
    the sample spans the leak's range rather than its top. The first items of a sorted
    list are not representative, and the question here is precisely whether the barrier
    tracks the leak.
    """
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    cells: dict[tuple, list[dict]] = collections.defaultdict(list)
    with grid.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["skipped"] or not row["xstar_engA_10"]:
                continue
            key = (
                row["geom"],
                row["gene_a"],
                row["gene_b"],
                int(float(row["x_start"])),
                int(float(row["xstar_start"])),
                int(float(row["len_x"])),
            )
            cells[key].append(row)
    chosen: list[dict] = []
    for rows in cells.values():
        rows.sort(key=lambda r: float(r["xstar_engA_10"]))
        take = min(per_cell, len(rows))
        if take:
            stride = max(1, len(rows) // take)
            chosen.extend(rows[::stride][:take])
    return chosen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Landing barrier, per grid design.")
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--grid", type=pathlib.Path, default=REPO / "docs/assets/axes_c8/rows.csv")
    parser.add_argument("--per-cell", type=int, default=8)
    parser.add_argument("--shard", default="0/1", help="i/n, as ONE argument")
    args = parser.parse_args(argv)
    index, total = (int(p) for p in args.shard.split("/"))

    done: set[str] = set()
    if args.out.exists():
        with args.out.open(newline="", encoding="utf-8") as handle:
            done = {row["key"] for row in csv.DictReader(handle)}
        print(f"  resuming: {len(done):,} rows already present", flush=True)

    fresh = not args.out.exists()
    handle = args.out.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    if fresh:
        writer.writeheader()
        handle.flush()

    designs = choose(args.grid, args.per_cell)
    mine = [d for i, d in enumerate(designs) if i % total == index]
    print(f"  {len(designs):,} designs selected, {len(mine):,} in this shard", flush=True)

    folder = FoldEngine(37.0)
    book = load_transcriptome(Host.ECOLI)
    gates = {name: cls(Host.ECOLI, folder, None, None) for name, cls in CLASSES.items()}
    transcripts = {sym: sq.to_rna(book[gid]) for sym, gid, _, _ in GENE_PAIRS}
    transcripts |= {sym: sq.to_rna(book[gid]) for _, _, sym, gid in GENE_PAIRS}
    written = 0
    began = time.time()

    for row in mine:
        geom = GEOM[row["geom"]]
        stem_index = int(float(row["stem_index"]))
        key = (
            f"{geom}:{row['gene_a']}:{row['gene_b']}:{int(float(row['x_start']))}:"
            f"{int(float(row['xstar_start']))}:{int(float(row['len_x']))}:{stem_index}:"
            f"{row['closure']}:{row['upper3']}:{row['lower3']}"
        )
        if key in done:
            continue
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
        wa = transcripts[row["gene_a"]][a0:a1]
        wb = transcripts[row["gene_b"]][b0:b1]
        if len(wa) != foot_a or len(wb) != foot_b:
            continue
        stems = list(gate.secondary_stems(wa, wb, len_x))
        if stem_index >= len(stems):
            continue
        base = gate.assemble(wa, wb, len_x, stems[stem_index])
        # The levers this row was built with, found by name in the gate's own axis lists
        # rather than re-derived, so the molecule measured is the molecule scored.
        closure = next((c for c in gate.CLOSURES if c[0] == row["closure"]), None)
        upper3 = next((u for u in gate.UPPER3 if u[0] == row["upper3"]), None)
        lower3 = next((low for low in gate.LOWER3 if low[0] == row["lower3"]), None)
        if None in (closure, upper3, lower3):
            continue
        patched = gate._apply_axes(base, closure, upper3, lower3)
        if patched is None:
            continue
        built = patched[0] if isinstance(patched, tuple) else patched
        switch, off = built.sequence, built.dot_bracket
        target, a_positions = landing_target(
            off, built.domains["sw_x"], built.domains["sw_xs"], len(switch) + gate.ARM_LEN, len_x
        )
        start = off + "." * len(wa)
        end = list(target + "." * len(wa))
        for position in a_positions:
            end[position] = ")"
        value, secs = barrier(f"{switch}&{wa}", start, "".join(end))
        writer.writerow(
            {
                "key": key,
                "geom_label": row["geom"],
                "gene_a": row["gene_a"],
                "gene_b": row["gene_b"],
                "x_start": int(float(row["x_start"])),
                "xstar_start": int(float(row["xstar_start"])),
                "len_x": len_x,
                "stem_index": stem_index,
                "closure": row["closure"],
                "upper3": row["upper3"],
                "lower3": row["lower3"],
                "switch_len": len(switch),
                "leak": row["xstar_engA_10"],
                "b_10": "" if value is None else f"{value:.3f}",
                "s_10": f"{secs:.3f}",
            }
        )
        handle.flush()
        written += 1
        rate = (time.time() - began) / written
        print(
            f"  {written:>5,}/{len(mine):<5,}  leak {float(row['xstar_engA_10']):.3f}  "
            f"b_10 {value if value is None else f'{value:+.2f}':>7}  {rate:5.1f} s  {key[:58]}",
            flush=True,
        )
    handle.close()
    print(f"\n  done: {written:,} designs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
