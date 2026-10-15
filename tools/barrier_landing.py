"""The kinetic barrier to trigger A landing on x*, with and without trigger B.

The architecture's central claim is a kinetic one that nothing on the page measures
kinetically: trigger A cannot reach x* until trigger B has freed it. Every observable we
report is an equilibrium property, and the one barrier we had is the switch strand folding
alone -- which does not involve a trigger at all.

**The question, stated so it is cheap to ask.** Not "what does the whole transition cost"
-- that path runs past five minutes per design, because findpath explores every
intermediate between two structures that differ almost everywhere. The nucleation step is
what the claim is about, so the path is:

    start   the OFF structure, triggers present but unpaired
    end     the same structure with the lock opened and x* paired to trigger A instead

A few dozen base pairs apart, not a few hundred. And it is the sharper question: a barrier
to the global minimum mixes in the inhibitory hairpin's own opening.

**Two tubes, one target.** `switch&A` is state 10, the leak. `switch&A&B` is the ON path.
The target structure is identical in both, so the only difference is whether trigger B is
in the tube. The architecture predicts `b_10` well above `b_11`; a design where the two are
close is leaking by a route no equilibrium observable here can see.

**Two defects in the previous attempts, recorded so they are not repeated.** Structures for
a multi-strand fold compound carry no `&` -- pass one and findpath silently returns its
ceiling sentinel, which reads as a number rather than a failure. And a target that leaves
the triggers unpaired measures the switch folding alone three times over with inert strands
beside it: all three tubes returned identical values, which is how that was caught.

Run (six shards, each resumable, safe to kill and restart)::

    uv run python <this> --out bn.csv --shard 0/6
"""

import argparse
import csv
import pathlib
import sys
import time

REPO = pathlib.Path("C:/Users/Dell/source/repos/cernal_software")
sys.path.insert(0, str(REPO / "src"))

import RNA  # noqa: E402

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import (  # noqa: E402
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
)
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.transcriptome import load_transcriptome  # noqa: E402

GENE_PAIRS = (
    ("ggt", "b3447", "fadB", "b3846"),
    ("ggt", "b3447", "astC", "b1748"),
    ("ggt", "b3447", "aldA", "b1415"),
)
GEOMETRIES = (("naive", ProkaryoticToeholdAndGate), ("kim", KimSecondaryArmToeholdAndGate))
CEILING = 20_000  # dekacal/mol; findpath returns this when it gives up
STEMS_PER_PAIR = 1


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


def landing_target(
    off: str, lock: tuple[int, int], xstar: tuple[int, int], a_x_start: int, len_x: int
) -> str:
    """`off` with the lock released and x* paired to trigger A's own copy of x instead.

    Pairing is antiparallel, so the 5'-most base of x* meets the 3'-most base of trigger
    A's x. x* lies inside the switch and trigger A after it, so x* always takes the opening
    bracket. Removing the lock first is what keeps the result crossing-free: a pair from
    sw_x to sw_xs would cross every new pair.
    """
    bonds = partners(off)
    out = list(off)
    for lo, hi in (lock, xstar):
        for i in range(lo, hi):
            j = bonds.get(i)
            if j is not None:
                out[i] = out[j] = "."
    lo_xs, hi_xs = xstar
    assert hi_xs - lo_xs == len_x, "x* is not len_x long"
    for k in range(len_x):
        out[lo_xs + k] = "("
    out += ["."] * 0
    return "".join(out), [a_x_start + len_x - 1 - k for k in range(len_x)]


def barrier(strands: str, start: str, end: str) -> tuple[float | None, float]:
    compound = RNA.fold_compound(strands)
    began = time.time()
    raw = compound.path_findpath_saddle(start, end, CEILING)
    elapsed = time.time() - began
    if raw is None or raw >= CEILING:
        return None, elapsed
    return raw / 100.0 - compound.eval_structure(start), elapsed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Barrier to trigger A landing on x*.")
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--shard", default="0/1", help="i/n, as ONE argument")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    index, total = (int(p) for p in args.shard.split("/"))

    done: set[str] = set()
    if args.out.exists():
        with args.out.open(newline="", encoding="utf-8") as fh:
            done = {row["key"] for row in csv.DictReader(fh)}
        print(f"  resuming: {len(done):,} rows already present", flush=True)

    fields = [
        "key",
        "geom",
        "gene_a",
        "gene_b",
        "x_start",
        "xstar_start",
        "len_x",
        "stem_index",
        "switch_len",
        "b_10",
        "s_10",
    ]
    fresh = not args.out.exists()
    handle = args.out.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(handle, fieldnames=fields)
    if fresh:
        writer.writeheader()
        handle.flush()

    folder = FoldEngine(37.0)
    book = load_transcriptome(Host.ECOLI)
    seen = written = 0
    began = time.time()

    for geom_name, cls in GEOMETRIES:
        gate = cls(Host.ECOLI, folder, None, None)
        foot_a, foot_b = gate.role_footprints()
        for sym_a, id_a, sym_b, id_b in GENE_PAIRS:
            ta, tb = sq.to_rna(book[id_a]), sq.to_rna(book[id_b])
            for pair in gate.find_cross_gene_pairs(sym_a, ta, sym_b, tb):
                if pair.gene_a != sym_a:
                    continue
                a0, a1 = pair.window_a()
                b0, b1 = pair.window_b()
                wa, wb = ta[a0:a1], tb[b0:b1]
                if len(wa) != foot_a or len(wb) != foot_b:
                    continue
                stems = list(gate.secondary_stems(wa, wb, pair.len_x))
                if not stems:
                    continue
                for stem_index in range(min(STEMS_PER_PAIR, len(stems))):
                    seen += 1
                    if seen % total != index:
                        continue
                    # Every coordinate that distinguishes a pair, because x_start alone
                    # does not: it names many pairs with different partners and lengths.
                    key = (
                        f"{geom_name}:{sym_a}:{sym_b}:{pair.x_start}:"
                        f"{pair.xstar_start}:{pair.len_x}:{stem_index}"
                    )
                    if key in done:
                        continue
                    built = gate.assemble(wa, wb, pair.len_x, stems[stem_index])
                    switch, off = built.sequence, built.dot_bracket
                    a_at = len(switch)
                    target_switch, a_positions = landing_target(
                        off,
                        built.domains["sw_x"],
                        built.domains["sw_xs"],
                        a_at + gate.ARM_LEN,
                        pair.len_x,
                    )
                    row = {
                        "key": key,
                        "geom": geom_name,
                        "gene_a": sym_a,
                        "gene_b": sym_b,
                        "x_start": pair.x_start,
                        "xstar_start": pair.xstar_start,
                        "len_x": pair.len_x,
                        "stem_index": stem_index,
                        "switch_len": len(switch),
                    }
                    # State 10 ONLY. The 11 tube is not a matched comparison: there B
                    # binds FIRST and that is what frees x*, so A's landing barrier would
                    # have to start from a B-bound state, not from OFF. Measuring it from
                    # OFF put trigger B in the tube unpaired at both ends of the path, so
                    # it never participated and both tubes returned the identical number.
                    # Recorded rather than shipped wrong.
                    for tag, strands, tail_len in (("10", f"{switch}&{wa}", len(wa)),):
                        start = off + "." * tail_len
                        end = list(target_switch + "." * tail_len)
                        for position in a_positions:
                            end[position] = ")"
                        value, secs = barrier(strands, start, "".join(end))
                        row[f"b_{tag}"] = "" if value is None else f"{value:.3f}"
                        row[f"s_{tag}"] = f"{secs:.3f}"
                    writer.writerow(row)
                    handle.flush()
                    written += 1
                    rate = (time.time() - began) / written
                    print(
                        f"  {written:>6,}  b_10 {row['b_10'] or '-':>9}  "
                        f"{rate:5.2f} s/design  {key}",
                        flush=True,
                    )
                    if args.limit and written >= args.limit:
                        handle.close()
                        print(f"\n  limit reached: {written:,} designs, {rate:.2f} s each")
                        return 0
    handle.close()
    print(f"\n  done: {written:,} designs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
