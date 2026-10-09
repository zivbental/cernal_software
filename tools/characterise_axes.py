"""Characterise which DESIGN DECISIONS move the objectives — the overnight run.

Run one shard per core, six windows, changing only the shard number::

    uv run python tools/characterise_axes.py --out axes_pfas --shard 0/6 --resume
    uv run python tools/characterise_axes.py --out axes_pfas --shard 1/6 --resume
    ...

and check on it from anywhere, without touching a running shard::

    uv run python tools/characterise_axes.py --out axes_pfas --shard 0/6 --status

This is a **characterisation** run, not a selection run. It does not pick six constructs; it
writes one row per design so that "which decision matters, and in combination with what" can be
answered by measurement afterwards. Four things it does differently from every sweep before it,
each because of something that sweep got wrong.

**1. It records the designs that FAIL, with the reason.** Measured on the mCherry sweep, survival
through ``feasible()`` differs between axis levels by up to 37x: ``open_3x3`` keeps 7.5% of its
designs and ``closed_CAU`` keeps 0.2%; ``WSS`` lower3 keeps **0 of 7,208**. Every lift and win-rate
computed so far was therefore conditioned on surviving, which is selection on the dependent
variable -- it can say "among designs that already open, which closure wins" and nothing more. A
run that keeps only survivors can never answer the question, so this one keeps the rest with a
``skipped`` reason beside them. The ON tube is measured for EVERY design before the ceiling
decides, so ``open_11`` is present on every row.

**2. It samples the secondary stems ACROSS the Pareto front** by passing
``Constraints(stem_order="front")``, which is a declared engine setting rather than something this
script reimplements. ``secondary_stems`` returns the non-dominated set over ``(lock_energy,
a_site_energy, b_site_energy)`` -- a median of 82 usable stems per real PFAS pair, mean 89.4, max
268 -- and the historic ``"lock"`` rule takes two points from one edge of it, discarding the
``a_site_energy`` axis. That axis is trigger A's binding to the secondary arm: the quantity the
architecture's central claim rests on, carried on every design, and never ranked on.

**3. It sweeps all 16 closures.** Only 6 ever reached the scored population; the 10 absent ones are
the systematic ladder (``d2_*``/``d1_*``/``d0_*``, mismatch count x GC count) where a non-monotonic
optimum would live if there is one. The full 16 x 3 x 2 grid runs per (pair, stem, geometry), so
interactions between decisions are estimable and not only single-axis effects.

**4. It goes through ``generate_designs``**, the production path, so every row is a real
``GateDesign`` measured by ``measure_design`` -- one measurement pass, the same one the pipeline
uses. Nothing here re-derives a metric the engine already computes.

**Costs are measured, not inherited.** The ON tube's ceiling rejects ~88% of mCherry designs before
the three OFF tubes are folded, which is what makes any of this affordable: ~0.3 s per enumerated
design against ~2 s for a full four-tube measurement. That figure is mCherry's; this script times
itself and prints the rate and an ETA from its own observations.

Memory is bounded: one design at a time, never a list, and ``--cache`` caps the ``FoldEngine``
entries per method (its default of 100,000 pair-probability matrices for a 165-nt switch is not
small). Output is flushed and fsynced every ``--flush-every`` rows, so a killed shard loses at
most that many and ``--resume`` picks up from the keys already on disk.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ruff: noqa: E402 - the engine imports must follow the sys.path.insert above, which is how every
# script in tools/ reaches `src/engine` without the package being installed.
from engine import sequences as sq
from engine.domain import Constraints, Host, TriggerCandidate, TriggerSet
from engine.gates.toehold import (
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
)
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.stages.folding import FoldProfiler
from engine.transcriptome import load_transcriptome

RESULTS = ROOT / "src/engine/gates/notebooks/toehold_and/results"
NOTEBOOK = ROOT / "src/engine/gates/notebooks/toehold_and"

#: The PFAS gene pairs as b-numbers. ``ggt`` (b3447) is one half of each; see the model page for
#: why these three, and note that E. coli and PFAS are the USE CASE here, not the platform.
GENE_PAIRS: tuple[tuple[str, str, str, str], ...] = (
    ("ggt", "b3447", "fadB", "b3846"),
    ("ggt", "b3447", "astC", "b1748"),
    ("ggt", "b3447", "aldA", "b1415"),
)

#: Per-design columns. Identity first so ``--resume`` can read one column; then the stem's three
#: Pareto objectives, because they are the axis nothing has ranked on; then survival, because a
#: row with a reason is still a measurement; then the metrics themselves.
IDENTITY = (
    "key",
    "gene_a",
    "gene_b",
    "x_start",
    "xstar_start",
    "len_x",
    "geom",
    "scheme",
    "stem_index",
    "closure",
    "upper3",
    "lower3",
)
STEM = ("lock_energy", "a_site_energy", "b_site_energy", "ddg_pref", "lock_minus_a_site")
#: What each design-decision lever FOUND and whether it changed anything -- taken from the engine's
#: declaration, never listed here. Without these a lever's effect is not estimable: comparing an
#: override against the control across all designs mixes the designs it never touched, where the
#: natural sequence already was the override, with the ones it did. Measured: `wobble_GU` against
#: `trigger_derived` came out 17.7% against 16.4%, which is that dilution and not a null result.
_LEVER_NAMES = (
    "closure_natural",
    "closure_changed",
    "upper3_natural",
    "upper3_changed",
    "lower3_strong_before",
    "lower3_forced",
    "wobble_applied",
    "main_z_repaired",
    "rare_codons_after_aug",
    "codons_after_aug",
)
# Tied to the engine's declaration rather than being a parallel list: a name the engine stops
# putting on `architecture` fails here at import, instead of silently becoming an empty column.
assert set(_LEVER_NAMES) <= set(ProkaryoticToeholdAndGate.GENERATION_KEYS), sorted(
    set(_LEVER_NAMES) - set(ProkaryoticToeholdAndGate.GENERATION_KEYS)
)
LEVERS = (
    *_LEVER_NAMES,
    # Produced by `_apply_lower3` only when the wobble lever actually converted something, so
    # they are empty on every other row rather than zero -- an unapplied lever made no codon.
    "wobble_codon",
    "wobble_made_stop",
    "wobble_made_rare",
    "wobble_rescued",
)
PAIR = ("l_local_a", "l_local_b", "l_local_min")
SURVIVAL = ("skipped", "assembly_violations", "n_switch", "stems_selected")
#: The settings this shard was launched with, repeated on every row.
#:
#: **Because a row has to say how it was built.** None of these was on a row before. Launch at
#: `--stems 6` tonight, resume at `--stems 9` tomorrow, and it is the same file with nothing to
#: tell the two halves apart -- and every analysis here is WITHIN a (pair, geometry) cell, so a
#: cell whose halves came from different samples of the Pareto front cannot be compared inside
#: itself and nothing would say so. The same applies to a shard accidentally launched at
#: `--stem-order lock`, or to concatenating two nights' files.
RUN = (
    "stem_order",
    "stems_per_pair",
    "overlap_low",
    "overlap_high",
    "on_ceiling",
    "pair_order",
    "min_access",
    "min_len_x",
)
#: Every name ``measure_design`` returns, taken from the ENGINE's declaration rather than listed
#: here. This used to be a hand-picked tuple of 24 against the 90 the pass actually computes, so 66
#: folded numbers were discarded on every row of a 346,528-design run -- the entire x* breakdown,
#: every hairpin fidelity, all four ``A_S``/``A_S_full`` states, all four ``P_open``. Any question
#: needing one of them meant re-running the sweep for values that had already been computed.
#:
#: It also carried ``free_xstar_01``, which names no observable the engine has ever returned: 0
#: values out of 346,528, with nothing to say so. ``tests/engine/gates/test_toehold_and_inventory``
#: now asserts this declaration equals ``measure_design``'s result in BOTH directions, so a name
#: that does not exist and a measurement nobody carries are each a test failure.
#:
#: Anything not returned stays empty rather than becoming 0.0 -- on every lower-is-better quantity
#: here a zero reads as perfect and clears every threshold.
MEASURED = ProkaryoticToeholdAndGate.MEASURED_KEYS

FIELDS = IDENTITY + STEM + LEVERS + PAIR + SURVIVAL + RUN + MEASURED


def build_gates(folder: FoldEngine) -> dict[str, object]:
    """One gate per geometry, tools injected once, as ``pipeline.build_tools`` does it."""
    gates: dict[str, object] = {}
    for cls in (ProkaryoticToeholdAndGate, KimSecondaryArmToeholdAndGate):
        gate = cls(
            host=Host.ECOLI,
            folder=folder,
            translation=TranslationScorer(Host.ECOLI),
            codons=CodonOptimizer(Host.ECOLI),
        )
        gates[gate.geometry_name] = gate
    return gates


def as_candidate(
    name: str, gene: str, sequence: str, start: int, openness: float
) -> TriggerCandidate:
    """A ``TriggerCandidate`` carrying what this run measures and ``None`` for what it does not.

    ``openness`` is the real RNAplfold value for the window. The fields this run has no
    measurement for are left at whatever the record requires rather than filled with zeros: a 0.0
    accessibility would read downstream as a measured failure.
    """
    return TriggerCandidate(
        trigger_id=name,
        gene_id=gene,
        symbol=gene,
        sequence=sequence,
        start_index=start,
        openness=openness,
        accessibility=openness,
        mfe=0.0,
        gc_content=sq.gc_content(sequence),
    )


def status(out: str, shards: int) -> int:
    """What every shard has written. Read-only: safe while shards are running."""
    print(f"  {'shard':>6s}{'rows':>12s}{'MB':>8s}{'last write':>21s}")
    total = 0
    for i in range(shards):
        path = RESULTS / f"{out}_{i}.csv"
        if not path.exists():
            print(f"  {i:>6d}{'--':>12s}{'--':>8s}{'not started':>21s}")
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            rows = max(sum(1 for _ in handle) - 1, 0)
        stat = path.stat()
        when = time.strftime("%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
        age = (time.time() - stat.st_mtime) / 60.0
        mark = "" if age < 5 else f"  (idle {age:.0f} min)"
        total += rows
        print(f"  {i:>6d}{rows:>12,}{stat.st_size / 1e6:>8.1f}{when:>21s}{mark}")
    print(f"\n  {total:,} rows in all")
    if not total:
        return 0
    measured = 0
    reasons: dict[str, int] = {}
    for i in range(shards):
        path = RESULTS / f"{out}_{i}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                reason = (row.get("skipped") or "").strip()
                if reason:
                    reasons[reason] = reasons.get(reason, 0) + 1
                else:
                    measured += 1
    print(f"  measured in full: {measured:,}  ({100.0 * measured / total:.1f}%)")
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    stopped at {reason:24s}{n:>10,}  ({100.0 * n / total:.1f}%)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="axes_pfas", help="writes results/<out>_<shard>.csv")
    parser.add_argument(
        "--shard",
        default="0/1",
        help="THIS shard as i/n, ONE argument. Written as two flags argparse rejects it and the "
        "run produces nothing, which has happened on this project before",
    )
    parser.add_argument(
        "--access",
        action="store_true",
        help=(
            "also price access_a/access_b from the transcript. Requires --control, because "
            "measure_design takes ONE transcript and prices both windows on it -- correct for a "
            "validation design from one gene, wrong for a PFAS pair whose windows sit on two "
            "different mRNAs. OFF by default on cost too, measured not assumed: 10-34 s per "
            "window on the real PFAS transcripts against 0.25-0.54 s for a whole enumerated "
            "design, since these fold the 1.4-2.2 kb transcript and not the switch. They are "
            "properties of the trigger PAIR, so they can be filled afterwards over the few "
            "hundred distinct windows without re-folding one design, and this run already "
            "records a pair-level accessibility in l_local_a/b/min from RNAplfold."
        ),
    )
    parser.add_argument("--resume", action="store_true", help="skip keys already on disk")
    parser.add_argument("--status", action="store_true", help="report progress and exit")
    parser.add_argument(
        "--pairs", type=int, default=240, help="trigger pairs per gene pair (default 240)"
    )
    parser.add_argument(
        "--pair-order",
        choices=("spread", "access", "len_x"),
        default="spread",
        help="'spread' takes every Nth of the accessibility-sorted list, which spans the range "
        "instead of one end, and is the default for a characterisation run; 'access' takes the "
        "most accessible; 'len_x' the longest overlaps",
    )
    parser.add_argument(
        "--stems", type=int, default=6, help="stems per pair (Constraints.stems_per_pair)"
    )
    parser.add_argument(
        "--stem-order",
        choices=("front_tops", "front", "lock"),
        default="front_tops",
        help="'front_tops' (default): one stem per non-empty square of the 3x3 "
        "(lock_energy x a_site_energy) board, plus the strongest stem on each of the three "
        "Pareto axes -- so b_site_energy, which the board cannot see, is represented. An empty "
        "square gives up its slot and there is NO quota: the count follows the data, measured 8 "
        "to 10 per cell, and lands in the stems_selected column. 'front' is the same board with "
        "a quota, filling any leftover slot from the lock edge. 'lock' is the historic one-edge "
        "rule, kept for comparison. --stems applies to the latter two only.",
    )
    parser.add_argument("--min-access", type=float, default=None, help="require l_local_min > this")
    parser.add_argument("--min-len-x", type=int, default=None, help="require len_x >= this")
    parser.add_argument(
        "--on-ceiling",
        type=float,
        default=4.0,
        help="open_11 ceiling in kcal/mol. The ON tube is measured and RECORDED for every design; "
        "this only decides whether the three OFF tubes are folded too",
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="run the mCherry control instead -- both windows from one transcript, comparable with "
        "every sweep before this one",
    )
    parser.add_argument(
        "--cache", type=int, default=20_000, help="FoldEngine entries per cached method"
    )
    parser.add_argument("--flush-every", type=int, default=100, help="rows between flush+fsync")
    parser.add_argument("--limit", type=int, default=0, help="stop after N rows (smoke test)")
    parser.add_argument(
        "--grid-stride",
        type=int,
        default=1,
        help="take every Nth CLOSURE BLOCK and all six (upper3 x lower3) points inside it. "
        "Blocks and not points, because a design and its control differ in one axis and so sit "
        "at ADJACENT grid positions -- lower3 has period 2, so a pair is i and i+1, and no "
        "point stride can take both. Measured: a coprime point stride covered every level of "
        "every axis and left the conditional analysis with zero matched pairs. The offset "
        "rotates per shard, so with six shards at --grid-stride 2 the even and odd closures are "
        "split between them and all 16 are covered, each shard internally complete. Use this "
        "and NOT --limit, which stops in generator order and reaches 4 of 16 closures while "
        "survival between closures differs by a factor of 8.8.",
    )
    args = parser.parse_args(argv)

    try:
        index, shards = (int(part) for part in args.shard.split("/"))
    except ValueError:
        parser.error("--shard takes i/n as ONE argument, e.g. --shard 0/6")
    if not 0 <= index < shards:
        parser.error(f"--shard {args.shard}: i must be in [0, n)")

    if args.status:
        return status(args.out, shards)

    RESULTS.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS / f"{args.out}_{index}.csv"
    done: set[str] = set()
    if args.resume and out_path.exists():
        with out_path.open(encoding="utf-8", newline="") as handle:
            done = {row["key"] for row in csv.DictReader(handle) if row.get("key")}
        print(f"  --resume: {len(done):,} keys already in {out_path.name}")

    folder = FoldEngine(cache_size=args.cache)
    profiler = FoldProfiler()
    gates = build_gates(folder)
    constraints = Constraints(stems_per_pair=args.stems, stem_order=args.stem_order)

    first = next(iter(gates.values()))
    grid = len(first.CLOSURES) * len(first.UPPER3) * len(first.LOWER3)
    print(f"  shard {index} of {shards}   on_ceiling {args.on_ceiling} kcal/mol")
    print(f"  geometries: {', '.join(gates)}")
    print(
        f"  grid per (pair, stem, geometry): {len(first.CLOSURES)} closures x "
        f"{len(first.UPPER3)} upper3 x {len(first.LOWER3)} lower3 = {grid}"
    )
    if args.stem_order == "front_tops":
        print(
            f"  stems per pair: NO QUOTA (stem_order='front_tops') -- one per non-empty 3x3 "
            f"square plus each axis's extreme; --stems {args.stems} is ignored. The count per "
            f"cell lands in stems_selected."
        )
    else:
        print(f"  stems per pair: {args.stems}, chosen by stem_order={args.stem_order!r}")
    if args.grid_stride > 1:
        # Coprimality is the whole correctness condition. `i, i+N, i+2N, ...` mod `grid` covers
        # every residue iff gcd(N, grid) == 1; otherwise it covers only grid/gcd of them and the
        # axes whose period shares that factor are silently pinned to one level.
        block = len(first.UPPER3) * len(first.LOWER3)
        blocks = grid // block
        if args.grid_stride > blocks:
            print(
                f"\n  --grid-stride {args.grid_stride} exceeds the {blocks} closure blocks in "
                f"the grid, so some shards would sample nothing."
            )
            return 2
        print(
            f"  grid stride {args.grid_stride}: every {args.grid_stride}th closure BLOCK, all "
            f"{block} (upper3 x lower3) points inside it -- so every design keeps its control "
            f"and the conditional comparison has pairs to pair"
        )
        print(
            f"    about {blocks // args.grid_stride} of {blocks} closures per shard, offset by "
            f"shard index, so the {shards} shards cover all {blocks} between them"
        )
    print(f"  {len(MEASURED)} measurement columns, from ToeholdAndGate.MEASURED_KEYS")
    print(f"  {len(RUN)} run-setting columns repeated on every row, so a row says how it was built")
    print(
        f"  {len(LEVERS)} lever columns (what each decision found, and whether it changed "
        f"anything) -- the conditional comparison needs these"
    )
    if args.access and not args.control:
        print(
            "\n  --access needs --control. `measure_design` takes ONE transcript and prices both\n"
            "  windows on it. That is right for a validation design from one gene, and wrong\n"
            "  for a PFAS pair whose windows sit on two different mRNAs: access_b would be\n"
            "  trigger B's window priced against trigger A's transcript -- a plausible\n"
            "  number that means nothing.\n"
            "  Filling it for cross-gene pairs needs a transcript_b on the engine's signature."
        )
        return 2
    if not args.access:
        print(
            "  access_a/access_b are NOT measured (no --access): 10-34 s per window on these\n"
            "  transcripts against 0.25-0.54 s per design, and they are pair-level, so\n"
            "  l_local_a/b/min carries accessibility here and these can be filled afterwards\n"
            "  over the distinct windows without re-folding a design."
        )

    # ---- the transcripts, and the trigger pairs on them ---------------------------------
    if args.control:
        sys.path.insert(0, str(NOTEBOOK))
        from full_sweep import read_fasta

        transcript = sq.to_rna(read_fasta(NOTEBOOK / "mCherry_original.txt"))
        sources = {"mCherry": transcript}
        scans = [("mCherry", "mCherry")]
    else:
        book = load_transcriptome(Host.ECOLI)
        sources = {}
        scans = []
        for a_sym, a_id, b_sym, b_id in GENE_PAIRS:
            sources[a_sym] = sq.to_rna(book[a_id])
            sources[b_sym] = sq.to_rna(book[b_id])
            scans.append((a_sym, b_sym))

    jobs = []
    for a_sym, b_sym in scans:
        ta, tb = sources[a_sym], sources[b_sym]
        if args.control:
            found = list(first.find_trigger_pairs(ta))
        else:
            found = list(first.find_cross_gene_pairs(a_sym, ta, b_sym, tb))
        scored = []
        for pair in found:
            if args.min_len_x is not None and pair.len_x < args.min_len_x:
                continue
            a0, a1 = pair.window_a()
            b0, b1 = pair.window_b()
            src_a = sources.get(getattr(pair, "gene_a", a_sym), ta)
            src_b = sources.get(getattr(pair, "gene_b", b_sym), tb)
            la = profiler.openness(src_a, a0, a1)
            lb = profiler.openness(src_b, b0, b1)
            worse = min(la, lb)
            if args.min_access is not None and worse <= args.min_access:
                continue
            scored.append((pair, la, lb, worse))
        scored.sort(key=lambda t: (-t[3], t[0].x_start, t[0].xstar_start))
        if args.pair_order == "len_x":
            scored.sort(key=lambda t: (-t[0].len_x, -t[3], t[0].x_start))
            taken = scored[: args.pairs]
        elif args.pair_order == "access":
            taken = scored[: args.pairs]
        else:
            step = max(1, len(scored) // max(args.pairs, 1))
            taken = scored[::step][: args.pairs]
        print(
            f"  {a_sym} x {b_sym}: {len(found):,} pairs -> {len(scored):,} past the floors "
            f"-> {len(taken):,} taken ({args.pair_order})"
        )
        for pair, la, lb, worse in taken:
            jobs.append((a_sym, b_sym, pair, la, lb, worse))

    mine = jobs[index::shards]
    print(f"\n  {len(jobs):,} trigger pairs; shard {index} takes {len(mine):,}")
    expected = len(mine) * len(gates) * args.stems * grid
    print(f"  at most {expected:,} rows from this shard (fewer where a pair offers fewer stems)")

    # ---- the run ------------------------------------------------------------------------
    fresh = not out_path.exists()
    handle = out_path.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
    if fresh:
        writer.writeheader()
        handle.flush()

    # Resolved once: constant for the shard, written on every row. `overlap_range` is
    # split into two columns rather than stored as the repr of a tuple, so a reader gets
    # numbers instead of a string to parse back.
    run_settings = {
        "stem_order": constraints.stem_order,
        "stems_per_pair": constraints.stems_per_pair,
        "overlap_low": constraints.overlap_range[0],
        "overlap_high": constraints.overlap_range[1],
        "on_ceiling": args.on_ceiling,
        "pair_order": args.pair_order,
        # `None` stays empty, never 0.0: a floor that was not applied is not a floor of zero.
        "min_access": "" if args.min_access is None else args.min_access,
        "min_len_x": "" if args.min_len_x is None else args.min_len_x,
    }

    started = time.time()
    written = resumed = 0
    for job_i, (a_sym, b_sym, pair, la, lb, worse) in enumerate(mine):
        a0, a1 = pair.window_a()
        b0, b1 = pair.window_b()
        gene_a = getattr(pair, "gene_a", a_sym)
        gene_b = getattr(pair, "gene_b", b_sym)
        src_a = sources.get(gene_a, sources[a_sym])
        src_b = sources.get(gene_b, sources[b_sym])
        for geom, gate in gates.items():
            window_a = src_a[a0 : a0 + gate.role_footprints()[0]]
            window_b = src_b[b1 - gate.role_footprints()[1] : b1]
            if len(window_a) != gate.role_footprints()[0]:
                continue
            if len(window_b) != gate.role_footprints()[1]:
                continue
            trigger_set = TriggerSet(
                activators=(
                    as_candidate(f"A@{a0}", gene_a, window_a, a0, la),
                    as_candidate(f"B@{b0}", gene_b, window_b, b0, lb),
                )
            )
            try:
                designs = list(gate.generate_designs(trigger_set, constraints))
            except Exception as error:
                print(f"    {gene_a}/{gene_b} {geom}: generate_designs {type(error).__name__}")
                continue
            # How many stems the rule actually returned for this cell. `front_tops` has no
            # quota, so this varies between pairs and the row has to carry it. Recovered from
            # the designs rather than by calling `_select_stems` again: one source of truth,
            # and re-selecting could disagree with what was built.
            stems_here = len({design.architecture.get("stem_index") for design in designs})
            # One closure block is `len(UPPER3) * len(LOWER3)` consecutive grid points, and a
            # design's control sits inside the same block, so blocks are kept whole and the
            # stride skips blocks. The shard index is the offset, so the six shards between
            # them cover every closure.
            block = len(gate.UPPER3) * len(gate.LOWER3)
            for position, design in enumerate(designs):
                if args.grid_stride > 1:
                    if (position // block - index) % args.grid_stride:
                        continue
                arch = design.architecture
                key = (
                    f"{gene_a}>{gene_b}|{pair.x_start}|{pair.xstar_start}|{pair.len_x}|{geom}"
                    f"|{arch.get('stem_index')}|{arch.get('closure')}"
                    f"|{arch.get('upper3')}|{arch.get('lower3')}"
                )
                if key in done:
                    resumed += 1
                    continue
                lock = arch.get("lock_energy")
                a_site = arch.get("a_site_energy")
                row = {
                    "key": key,
                    "gene_a": gene_a,
                    "gene_b": gene_b,
                    "x_start": pair.x_start,
                    "xstar_start": pair.xstar_start,
                    "len_x": pair.len_x,
                    "geom": geom,
                    "scheme": arch.get("scheme"),
                    "stem_index": arch.get("stem_index"),
                    "closure": arch.get("closure"),
                    "upper3": arch.get("upper3"),
                    "lower3": arch.get("lower3"),
                    "lock_energy": lock,
                    "a_site_energy": a_site,
                    "b_site_energy": arch.get("b_site_energy"),
                    "ddg_pref": arch.get("ddg_pref"),
                    "lock_minus_a_site": (
                        None if lock is None or a_site is None else lock - a_site
                    ),
                    # Straight off `architecture`, by the engine's own names. A missing key
                    # stays empty rather than becoming 0 -- `wobble_codon` absent means the
                    # lever never ran, which is a different fact from a codon of zero.
                    **{
                        name: (
                            "|".join(arch[name])
                            if isinstance(arch.get(name), tuple)
                            else arch.get(name, "")
                        )
                        for name in LEVERS
                    },
                    **run_settings,
                    "stems_selected": stems_here,
                    "l_local_a": round(la, 6),
                    "l_local_b": round(lb, 6),
                    "l_local_min": round(worse, 6),
                    "assembly_violations": "|".join(arch.get("assembly_violations") or ()),
                    "n_switch": len(design.sequence),
                }
                try:
                    measured = gate.measure_design(
                        design,
                        on_ceiling=args.on_ceiling,
                        # Given all three, the accessibility terms are priced from the
                        # transcript; without them they are None -- never 0.0, since these are
                        # costs and zero reads as free. `--access` is gated on `--control`
                        # above, so `src_a` really is the transcript both windows came from.
                        transcript=src_a if args.access else None,
                        site_a=(a0, a1) if args.access else None,
                        site_b=(b0, b1) if args.access else None,
                    )
                except Exception as error:
                    row["skipped"] = f"measure_error:{type(error).__name__}"
                else:
                    row["skipped"] = measured.get("skipped") or ""
                    for name in MEASURED:
                        value = measured.get(name)
                        if value is not None:
                            row[name] = value
                writer.writerow(row)
                written += 1
                if written % args.flush_every == 0:
                    handle.flush()
                    os.fsync(handle.fileno())
                    per = (time.time() - started) / written
                    remaining = (len(mine) - job_i - 1) * len(gates) * args.stems * grid
                    print(
                        f"  pair {job_i + 1}/{len(mine)}  {written:,} rows  {per:.3f} s each  "
                        f"~{remaining * per / 3600:.1f} h left",
                        flush=True,
                    )
                if args.limit and written >= args.limit:
                    handle.flush()
                    handle.close()
                    print(f"\n  --limit {args.limit}: wrote {written:,} rows")
                    return 0

    handle.flush()
    os.fsync(handle.fileno())
    handle.close()
    elapsed = time.time() - started
    print(f"\n  wrote {written:,} rows to {out_path.name} in {elapsed / 3600:.2f} h")
    if args.resume:
        print(f"  skipped {resumed:,} already present")
    if written:
        print(f"  {elapsed / written:.3f} s per design")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
