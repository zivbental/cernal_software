"""The full design sweep, staged so the expensive half only ever sees survivors.

    # stage 1 -- no folding of switches at all, millions of rows are fine
    uv run python src/engine/gates/notebooks/toehold_and/full_sweep.py \\
        --fasta "path/to/mCherry original.txt" --stage cheap --pairs 0 --out sweep

    # stage 2, block A -- resolve the axes: 10 pair-stems x all 360 axis points
    uv run python src/engine/gates/notebooks/toehold_and/full_sweep.py \\
        --fasta "path/to/mCherry original.txt" --stage fold --out sweep \\
        --block A --pair-stems 10

    # stage 2, block B -- breadth: one pair-stem per pair, axes fixed at A's answer
    uv run python src/engine/gates/notebooks/toehold_and/full_sweep.py \\
        --fasta "path/to/mCherry original.txt" --stage fold --out sweep \\
        --block B --ref-axes closure=closed_UAU,island=WWW

**Why it is staged, with the costs measured rather than guessed.** An earlier version of
this docstring claimed a four-tube evaluation costs ~25 s and that the sweep would otherwise
take weeks. **Both were wrong.** Measured on a 161-nt switch with its two triggers:

| operation | cost | scales with |
|---|---|---|
| four-tube evaluation, all observables | **1.2 s** | one design |
| secondary-stem enumeration (3ⁿ, n = 7 to 10 conflicts) | **2.1 s** | one trigger **pair** |
| the axis grid itself | free | — |

So the bottleneck is **stem enumeration per pair**, not folding per design, and it is paid
once per pair however many designs are built on it. The practical consequences:

* stage 1 over all 1036 pairs is **~36 minutes**, almost all of it stem enumeration;
* stage 2 folding 5,000 designs is **~1.7 hours**;
* folding the *entire* grid — 1036 pairs x 4 stems x 360 combinations, 1.5 M designs — is
  about **21 days**, which is the only case the "weeks" claim ever applied to and is not
  something anyone would run.

Staging is still right, but for a much less dramatic reason than first stated: it turns a
21-day job into a 2-hour one, and it lets the cheap metrics choose *which* designs are worth
the 1.2 s.

**How stage 2 chooses is deliberately not a top-N.** The space factorises into the
**pair-stem** (4,144 of them, setting ``lock_energy``, ``a_site_energy`` and ``scheme``) and
the **axes** (360, setting ``stem_dG`` and the grip energies), and the two are orthogonal —
the axes do not move ``lock_energy`` at all. Ranking on any single metric therefore collapses
one dimension entirely. Measured on the real sweep: "strongest locks per closure arm" at
``--fold 400`` folded **2 trigger pairs of 1,036**, because ``lock_energy`` takes only 195
distinct values and its median is shared by 6,840 rows. See ``SWEEP_FINDINGS.md`` §1. Hence
two deliberate blocks — ``--block A`` and ``--block B``, described on ``_select_block_a`` and
``_select_block_b``.

**Output is tidy, one row per design, and re-analysable.** Every axis value is its own
column beside every metric, and the switch sequence is written out, so any row can be rebuilt
and any pair of columns can be plotted against each other afterwards without re-running
anything. That is deliberate: the interesting relationships in this project have all turned
out to be ones nobody thought to tabulate in advance, and a table of a few hand-picked
examples cannot show a biological signal that only appears across hundreds of designs.

**The axes.**

1. ``toehold_trim`` — trigger B's toehold ``r2*``, full length or trimmed. Reported with the
   pairing probability of its **3' end**, the part adjacent to the inhibitory hairpin, since
   that is where structure blocks the transition from binding into invasion.
2. ``secondary_arm`` — 18, 19 or 20 nt. **Not yet implemented**: it changes ``ARM_LEN`` and
   therefore ``assemble``'s domain map, which is a change to the gate rather than a patch to a
   built switch. Flagged here so it is not silently dropped.
3. ``scheme`` — the scheme C front, as built, now including its fourth per-position option as
   a reported variant.
4. ``lower3`` — the 3 bp at the stem base: 2 strong + 1 weak, and the alternatives, because
   Green found 2 of 3 G·C optimal and that is a target rather than a maximum.
5. ``upper3`` — the 3 bp nearest the loop: 3 weak, or 2 weak + 1 strong.
6. ``closure`` — AUG sequestration, by depth **and** identity, since ``UAU`` and ``CAU`` close
   to the same depth and do not perform the same.
7. ``rbs_loop`` — 15 or 18 nt.

**Three of those seven are not in the grid yet** — ``toehold_trim``, ``rbs_loop`` and
``secondary_arm`` each change a domain *length*, so they need a change to ``assemble``'s
layout rather than a patch to a built switch. They are recorded at their current fixed value
and named in ``PENDING_LENGTH_AXES``, rather than being emitted as columns that vary in the
output but not in the molecule — which would let every downstream analysis treat them as
tested.

**And one axis the review list omitted:** the **3-nt island**. ``k1*`` is 6 nt and the upper-3
modification changes only its top half, so ``k1*[0:3]`` — between the changed top and the
bulge — stays trigger-derived. Combine upper-3 with an AUG closure and trigger A is left
holding a 3-nt island flanked by mismatches on both sides. It is swept here as ``island``,
because leaving it trigger-derived is a choice and not a default.
"""

import argparse
import csv
import itertools
import math
import sys
from pathlib import Path

import duckdb

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from narrate import Progress, banner, conclude, interim  # noqa: E402

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import (  # noqa: E402
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
    _mean_unpaired,
)
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

#: Closure of the AUG bulge: (label, bulge* sequence). Depth is how many of the start
#: codon's three bases pair; identity is the G+C count at that depth. Both matter -- UAU and
#: CAU close to the same depth and score differently -- so they are separate axis values.
CLOSURES: tuple[tuple[str, str], ...] = (
    ("open_3x3", None),  # leave bulge* trigger-derived, whatever the window gave
    ("closed_UAU", "UAU"),  # depth 3, zero G+C
    ("closed_CAU", "CAU"),  # depth 3, one G+C
    ("closed_CGU", "CGU"),  # depth 3, two G+C
    ("pair2_CCU", "CCU"),  # depth 2, designed 1x1
    ("pair1_CCC", "CCC"),  # depth 1, designed 2x2
    # --- the uncovered (depth, G+C) cells -------------------------------------------------
    #
    # The five above were chosen by hand and leave the axis lopsided: **depth 3 is complete**
    # (G+C 0/1/2, and no 3-mer reaches depth 3 at G+C 3), while depth 2 was tested at ONE
    # identity, depth 1 at one, and depth 0 not at all. Since UAU and CAU close to the same
    # depth and score differently -- the reason identity is an axis value at all -- a single
    # identity per depth cannot separate "this depth is wrong" from "this base content is".
    #
    # One representative per missing cell, the alphabetically first 3-mer in it, so the table is
    # reproducible rather than a set of 3-mers somebody liked. Enumerated and verified against the
    # pairing rule b[i] ~ AUG[2-i] with G-U counted as pairing, not asserted from memory.
    #
    # Depth 0 is NOT the same thing as ``open_3x3``: that level leaves bulge* trigger-derived, and
    # measured over 1,089 gating designs its aug_11 runs 0.2315 to 0.9927 with a median of 0.7207 --
    # below the median of every "closed" level at its low end. open_3x3 is an outcome of the
    # trigger; these are settings.
    ("d2_gc3_CGC", "CGC"),  # depth 2, G+C 3
    ("d2_gc1_AGU", "AGU"),  # depth 2, G+C 1
    ("d2_gc0_AAU", "AAU"),  # depth 2, G+C 0
    ("d1_gc2_AGC", "AGC"),  # depth 1, G+C 2
    ("d1_gc1_AAC", "AAC"),  # depth 1, G+C 1
    ("d1_gc0_AAA", "AAA"),  # depth 1, G+C 0
    ("d0_gc3_GCC", "GCC"),  # depth 0, G+C 3
    ("d0_gc2_ACC", "ACC"),  # depth 0, G+C 2
    ("d0_gc1_ACA", "ACA"),  # depth 0, G+C 1
    ("d0_gc0_AUA", "AUA"),  # depth 0, G+C 0
)

#: Top 3 bp of the main stem. "W" is a weak A-U pair, "S" a strong G-C.
UPPER3: tuple[tuple[str, str], ...] = (
    ("trigger_derived", None),
    ("WWW_AUA", "AUA"),
    ("WWW_UAU", "UAU"),
    ("WWS_AUG", "AUG"),
    ("WSW_AGA", "AGA"),
)

#: Sentinel for the wobble level: its sequence is not fixed, it is computed per design from
#: the trigger. See `build`.
WOBBLE = "<wobble>"

#: Bottom 3 bp. Green: 2 of 3 G-C is best, so 2S1W leads and the neighbours bracket it.
LOWER3: tuple[tuple[str, str], ...] = (
    ("trigger_derived", None),
    ("SSW", "GGA"),
    ("SWS", "GAG"),
    ("WSS", "AGG"),
    ("SSS", "GGG"),
    ("SWW", "GAA"),
    # Offer's proposal, and a different question from the five above. Those REPLACE the
    # three bases, which keeps the stem paired but breaks trigger A's match there -- so
    # every one of them trades stem G+C against trigger-A grip and we measure only the sum.
    # This one converts C-G stem pairs to U-A while leaving trigger A a G-U wobble, so the
    # stem weakens and trigger A stays paired. Not free -- G-U is weaker than G-C -- but a
    # far smaller cost than a mismatch, and it isolates the stem-strength effect.
    ("wobble_GU", WOBBLE),
    # WSS is NOT rescued here, and the reason is a standing constraint rather than an oversight.
    #
    # The level installs AGG at the third codon after the AUG -- a rare E. coli arginine -- so 100%
    # of its designs are dropped by the rare-codon screen and the weak-strong-strong arrangement has
    # never been tested. AGC (serine) would restore the arrangement with a common codon.
    #
    # But WSS_AGC would be a SIXTH fixed replacement of the lower 3, and that whole class is the one
    # measured to lose: against trigger A, SSW carries a real mismatch in 483 of 514 gating designs,
    # SWS in 446 of 484, SSS in 133 of 133. Only `trigger_derived` (344/344 exact) and `wobble_GU`
    # (184 exact, 184 with a G-U, **0 mismatches**) leave trigger A's grip intact. Adding a level
    # that breaks the grip to recover an arrangement is spending the trigger to test the stem.
    #
    # If the arrangement is wanted, the reachable route is a wobble that happens to land on W-S-S,
    # not a fixed substitution -- which is what `wobble_GU` already does where the bases allow it.
)

#: The 3 nt of k1* between the modified top and the bulge.
ISLAND: tuple[tuple[str, str], ...] = (("trigger_derived", None), ("WWW", "AUA"))

#: Axes that change a DOMAIN LENGTH rather than a domain's sequence, and so need a change to
#: `assemble`'s layout rather than a patch to a built switch. They are deliberately NOT in
#: the grid below: an axis recorded in the output but never applied to the sequence is worse
#: than a missing one, because every downstream analysis would treat it as tested.
#:
#:   toehold_trim   -- trigger B's r2* toehold, trimmed from the 5' end (0 / 4 / 8 nt)
#:   rbs_loop_len   -- 18 (ours) or 15 (Green forward-engineered, and Kim)
#:   secondary_arm  -- 18 / 19 / 20 nt, Kim's verified geometry
#:
#: All three are real axes and all three are pending the same piece of work.
PENDING_LENGTH_AXES = ("toehold_trim", "rbs_loop_len", "secondary_arm")


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def gc_fraction(sequence: str) -> float:
    return sum(1 for base in sequence if base in "GC") / len(sequence) if sequence else 0.0


def cheap_metrics(gate, trigger_a: str, trigger_b: str, pair) -> dict:
    """Everything about a trigger PAIR that needs no switch folding.

    Constant across every design built on that pair, so computed once and joined on, rather
    than recomputed per row -- which is where a sweep of this size would otherwise spend
    most of its time.
    """
    arm = gate.ARM_LEN
    main_pre = trigger_a[9:arm]
    bottom3 = main_pre[-3:]
    top3 = trigger_a[:3]
    return {
        "gc_bottom3": gc_fraction(bottom3),
        "gc_top3": gc_fraction(top3),
        "gc_gradient": gc_fraction(bottom3) - gc_fraction(top3),
        "gc_balance": abs(gc_fraction(trigger_a[:6]) - 0.5),
        "trigger_a_gc": gc_fraction(trigger_a),
        "trigger_b_gc": gc_fraction(trigger_b),
        "len_x": pair.len_x,
        "gap": pair.gap(),
    }


def build(base, axes: dict):
    """Apply one point of the axis grid to an assembled switch.

    Patches whole domains by name and never changes a length, so the domain map stays valid
    and the sequence can be rebuilt from the row's axis columns alone.
    """
    from dataclasses import replace

    sequence = list(base.sequence)

    def put(domain: str, piece: str, at_end: bool = False) -> None:
        start, end = base.domains[domain]
        offset = end - len(piece) if at_end else start
        sequence[offset : offset + len(piece)] = list(piece)

    if axes["closure"] is not None:
        put("bulge_star", axes["closure"])
    if axes["upper3"] is not None:
        put("k1_star", axes["upper3"], at_end=True)
        put("main_z", sq.reverse_complement(axes["upper3"]))
    if axes["island"] is not None:
        put("k1_star", axes["island"])
        put("main_z", sq.reverse_complement(axes["island"]), at_end=True)
    if axes["lower3"] == WOBBLE:
        # A G-U wobble lets the stem's strength move WITHOUT trigger A losing the position,
        # and it moves in both directions depending on what the trigger has there:
        #
        #   trigger U -> star is normally A, stem pair A-U (weak). Put G: trigger keeps a
        #                G-U wobble and the stem pair becomes G-C. STRONGER.
        #   trigger G -> star is normally C, stem pair C-G (strong). Put U: trigger keeps a
        #                G-U wobble and the stem pair becomes U-A. WEAKER.
        #
        # So this is not one modification but a target, and the target is Green's 2 strong +
        # 1 weak. A trigger-derived base too weak is strengthened, an all-strong one is
        # weakened by exactly one. The earlier version only weakened, which made it a no-op
        # on the majority of designs whose stem base is already A/U rich.
        # Reaches two-of-three WITHOUT dictating which position is weak. An earlier version
        # forced SSW -- strong at the bottom -- on the reading that Green's optimum is
        # positional. The preview does not support it: over 12 pair-stems WSS opened 59
        # times against SSW's 28 at the same leak, so forcing SSW converts away from the
        # arrangement that opens most. The three fixed levels test the arrangements head on;
        # this level's job is the STRENGTH, reached through wobbles trigger A still pairs
        # through, and the arrangement is left to the data.
        #
        # Only two bases have a wobble available: star A (trigger U) can become G, and star
        # C (trigger G) can become U. star G and star U have no G-U to reach for and are
        # left alone rather than forced into a mismatch.
        star_start = base.domains["main_pre_star"][0]
        pre_end = base.domains["main_pre"][1]
        strong = sum(1 for i in range(3) if sequence[star_start + i] in "GC")
        for offset in range(3):
            if strong == 2:
                break
            here = sequence[star_start + offset]
            if strong < 2 and here == "A":
                sequence[star_start + offset] = "G"
                sequence[pre_end - 1 - offset] = "C"
                strong += 1
            elif strong > 2 and here == "C":
                sequence[star_start + offset] = "U"
                sequence[pre_end - 1 - offset] = "A"
                strong -= 1
    elif axes["lower3"] is not None:
        put("main_pre_star", sq.reverse_complement(axes["lower3"]))
        put("main_pre", axes["lower3"], at_end=True)
    return replace(base, sequence="".join(sequence))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--stage", choices=("cheap", "fold"), required=True)
    parser.add_argument("--pairs", type=int, default=20, help="trigger pairs, 0 for all")
    parser.add_argument("--stems", type=int, default=4, help="stems per pair from the front")
    parser.add_argument(
        "--stems-by",
        choices=("lock_energy", "a_site_energy"),
        default="lock_energy",
        help="which objective picks the --stems kept per pair. lock_energy is what every "
        "run so far used, and it excluded the A-anchored corner entirely: those builds "
        "spend lock strength on trigger A's site (median lock -5.8 against B-anchored's "
        "-12.2), so none of 240 survivors ever reached the top 4 -- while having the best "
        "a_site of any scheme, -38.5 against -23.4. See BLOCK_C_FINDINGS.md section 5",
    )
    parser.add_argument(
        "--kim-arm",
        action="store_true",
        help="build with Kim 2019's secondary geometry: 20-nt arm, 17-nt invasion, AUA cap",
    )
    parser.add_argument(
        "--block",
        choices=("A", "B", "C"),
        default="A",
        help="stage 2 selection: A resolves the axes on a few pair-stems, B fixes the axes "
        "and varies triggers, C crosses every pair-stem with a restricted grid",
    )
    parser.add_argument(
        "--scheme", default="", help="block C: restrict to one scheme, e.g. B-anchored"
    )
    parser.add_argument(
        "--eligible-only",
        action="store_true",
        help="block C: keep only pair-stems with at least one design inside the grip window",
    )
    for axis in ("closures", "upper3", "lower3", "island"):
        parser.add_argument(
            f"--{axis}",
            default="",
            help=f"comma-separated {axis} levels to keep; empty means all of them",
        )
    parser.add_argument(
        "--pair-stems",
        type=int,
        default=10,
        help="block A: pair-stems to cross with all 360 axes (10 -> 3600 folds, ~1.6 h)",
    )
    parser.add_argument(
        "--ref-axes",
        default="",
        help="block B: axes to hold fixed, e.g. closure=closed_UAU,island=WWW",
    )
    parser.add_argument("--out", default="sweep")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="carry on from what the output file holds: stage 1 by pair, stage 2 by design",
    )
    parser.add_argument(
        "--shard",
        default="",
        metavar="i/n",
        help="stage 2: fold only shard i of n, writing {out}_folded_i.csv. Run n of these "
        "at once, one per physical core; ViennaRNA is safe to fork here because the "
        "temperature travels on an explicit RNA.md() and never on RNA.cvar",
    )
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    family = KimSecondaryArmToeholdAndGate if args.kim_arm else ProkaryoticToeholdAndGate
    gate = family(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    if args.kim_arm:
        print(
            f"  geometry: secondary arm {gate.SECONDARY_ARM_LEN}, invasion "
            f"{gate.SECONDARY_INVASION_LEN}, cap {gate.SECONDARY_CAP!r} -- NOT comparable "
            f"row-for-row with a default-geometry sweep; the switch is a different length "
            f"and the trigger-pair set differs."
        )
    transcript = read_fasta(args.fasta)

    if args.stage == "cheap":
        return _cheap(gate, transcript, args, output_dir)
    return _fold(gate, transcript, args, output_dir)


#: The columns that together identify one trigger pair. **``x_start`` alone does not.**
#: The 1036 kept pairs carry only 373 distinct ``x_start`` values -- ``x@448`` appears
#: twelve times with a different ``xstar_start`` each time -- so keying on it merges
#: distinct pairs into one group and, on resume, skips every pair that shares an
#: ``x_start`` with a finished one. Verified unique across all 1036; ``(x_start,
#: xstar_start)`` alone is not (1035 of 1036).
PAIR_KEY_COLUMNS = ("x_start", "xstar_start", "a_start", "a_end", "b_start", "b_end")


def pair_key(pair) -> tuple[int, ...]:
    """The identity of a trigger pair, matching ``PAIR_KEY_COLUMNS`` order."""
    return (pair.x_start, pair.xstar_start, *pair.window_a(), *pair.window_b())


def _rewind_to_last_complete_pair(path: Path) -> tuple[set[tuple[int, ...]], int, list[float]]:
    """Trim the final trigger pair off a partial stage-1 CSV and say what is left.

    Stage 1 writes each pair's rows contiguously, so if a run dies the only group that can
    be half-written is the last one -- and there is no way to tell a half-written pair from
    a complete one, because the number of stems a pair yields varies. So the last group is
    always dropped and recomputed, whether or not it was finished. One pair of rework is
    the price of not silently keeping a truncated one.

    Streams, holding at most one pair's rows (about 1440) in memory, then replaces the file
    only once the rewritten copy is complete -- a crash here must not destroy the very data
    it is trying to save.

    Collects the lock energies on the way past, because it is already reading every row and
    the closing summary should describe the whole file, not only the rows this session added.

    Returns:
        ``(pair keys kept, rows kept, their lock energies)``, keys as in
        ``PAIR_KEY_COLUMNS``. All three describe the file as it stands after the trim.
    """
    csv.field_size_limit(10**7)
    trimmed = path.with_suffix(".trimmed")
    done: set[tuple[int, ...]] = set()
    locks: list[float] = []
    kept_rows = 0
    with path.open(newline="") as src, trimmed.open("w", newline="") as dst:
        reader = csv.reader(src)
        header = next(reader, None)
        if header is None:
            trimmed.unlink(missing_ok=True)
            return set(), 0, []
        key_cols = [header.index(name) for name in PAIR_KEY_COLUMNS]
        lock_col = header.index("lock_energy")
        writer = csv.writer(dst)
        writer.writerow(header)
        group: list[list[str]] = []
        current = None
        for fields in reader:
            # A killed run leaves a half-written final line, and csv is happy to hand it
            # back as a short row. Read through `csv.DictReader` that fragment becomes a
            # row whose x_start is a piece of some other column -- which reads as the start
            # of a *new* pair and so marks the genuinely incomplete one as finished. The
            # width check is what makes a torn line look like the end of the file, which is
            # what it is.
            if len(fields) != len(header):
                break
            key = tuple(int(fields[col]) for col in key_cols)
            if key != current:
                if group:  # the previous group ended before this one began, so it is whole
                    writer.writerows(group)
                    kept_rows += len(group)
                    locks.extend(float(row[lock_col]) for row in group)
                    done.add(current)
                group, current = [], key
            group.append(fields)
        # `group` is the final pair and is deliberately discarded.
    path.unlink()
    trimmed.rename(path)
    return done, kept_rows, locks


def _cheap(gate, transcript, args, output_dir) -> int:
    kept = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        kept.append(pair)
    kept.sort(key=lambda p: (-p.len_x, -p.gap(), p.x_start))
    if args.pairs:
        kept = kept[: args.pairs]
    grid = list(itertools.product(CLOSURES, UPPER3, LOWER3, ISLAND))

    # Streamed, not accumulated. The full grid is 1036 pairs x 4 stems x 360 axis points =
    # 1.49 M rows, and holding those as dicts is several GB -- the run would die at the very
    # end, after all the work. Rows go straight to the file; the only things kept in memory
    # are one float per row for the lock distribution and the set of pairs that produced
    # anything, which is what the closing summary needs.
    # Stage 1 shards by trigger pair too. Stem enumeration is 3^n per pair and dominates
    # the cost, so splitting the pair list across cores is near-linear -- and with the
    # secondary geometry and the stem objective now both variable, stage 1 is re-run per
    # variant rather than once ever.
    shard_suffix = ""
    if args.shard:
        index_text, _, count_text = args.shard.partition("/")
        shard, shards = int(index_text), int(count_text or 0)
        if not 0 <= shard < shards:
            print(f"--shard {args.shard} is not of the form i/n with 0 <= i < n")
            return 1
        kept = [p for position, p in enumerate(kept) if position % shards == shard]
        shard_suffix = f"_{shard}"
        if not kept:
            print(f"  shard {shard} of {shards} has no pairs -- nothing to do")
            return 0

    path = output_dir / f"{args.out}_cheap{shard_suffix}.csv"
    locks: list[float] = []
    usable_pairs: set[tuple[int, ...]] = set()
    written = 0
    writer = None

    already: set[tuple[int, ...]] = set()
    if args.resume and path.exists():
        print(f"  resuming: reading {path.name} and dropping its last, possibly partial pair")
        already, written, locks = _rewind_to_last_complete_pair(path)
        usable_pairs |= already
        print(f"  {written:,} rows across {len(already)} pairs kept\n")
    elif args.resume:
        print(f"  --resume given but {path.name} does not exist; starting from the beginning\n")

    todo = [p for p in kept if pair_key(p) not in already]
    banner(
        "STAGE 1 - enumerate and score, folding no switches",
        [
            f"{len(todo)} trigger pairs x up to {args.stems} stems x {len(grid)} axis points",
            f"= up to {len(todo) * args.stems * len(grid):,} designs"
            + (f", on top of {written:,} rows resumed" if already else ""),
            "cost is dominated by stem enumeration (3^n per pair), not by the grid",
            f"pending axes, needing an assemble change: {', '.join(PENDING_LENGTH_AXES)}",
        ],
        estimate=len(todo) * 5.2,
    )
    bar = Progress(len(todo), "pairs")

    # Append on resume, and reuse the existing header rather than writing a second one.
    mode = "a" if already else "w"
    if already:
        with path.open(newline="") as handle:
            header = next(csv.reader(handle))
    with path.open(mode, newline="") as handle:
        if already:
            writer = csv.DictWriter(handle, fieldnames=header)
        for index, pair in enumerate(todo):
            trigger_a = transcript[slice(*pair.window_a())]
            trigger_b = transcript[slice(*pair.window_b())]
            stems = gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
            stems = [s for s in stems if s.lock_energy <= 0.0]  # a positive lock is not a lock
            if not stems:
                bar.step(f"x@{pair.x_start}  no stem with a negative lock")
                continue
            # Ordered by whichever objective --stems-by names. lock_energy is the historic
            # choice and it silently removed every A-anchored build; a_site_energy is the
            # complement, and the two selections are meant to be compared, not merged.
            stems = sorted(stems, key=lambda s: getattr(s, args.stems_by))[: args.stems]
            shared = cheap_metrics(gate, trigger_a, trigger_b, pair)
            # main_stem_energies depends only on (trigger_a, len_x, main_z), and the 360
            # grid points yield just 10 distinct main_z -- the closure and island axes do
            # not touch that slice. So 97.2% of the calls were repeats, paid for out of
            # FoldEngine's cache. Memoised here, keyed on main_z and dropped at the end of
            # the pair, so the saving does not come out of a cache someone else needs.
            stem_dg_by_main_z: dict[str, tuple] = {}
            for stem_index, stem in enumerate(stems):
                base = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
                for closure, upper3, lower3, island in grid:
                    axes = {
                        "closure": closure[1],
                        "upper3": upper3[1],
                        "lower3": lower3[1],
                        "island": island[1],
                    }
                    switch = build(base, axes)
                    main_z = switch.sequence[slice(*switch.domains["main_z"])]
                    if main_z not in stem_dg_by_main_z:
                        stem_dg_by_main_z[main_z] = gate.main_stem_energies(
                            trigger_a, pair.len_x, main_z
                        )
                    stem_dg = stem_dg_by_main_z[main_z]
                    row = {
                        **shared,
                        "x_start": pair.x_start,
                        "xstar_start": pair.xstar_start,
                        "a_start": pair.window_a()[0],
                        "a_end": pair.window_a()[1],
                        "b_start": pair.window_b()[0],
                        "b_end": pair.window_b()[1],
                        "stem_index": stem_index,
                        "scheme": stem.scheme,
                        "lock_energy": stem.lock_energy,
                        "a_site_energy": stem.a_site_energy,
                        "b_site_energy": stem.b_site_energy,
                        "ddg_pref": stem.ddg_pref,
                        "lock_minus_a_site": stem.lock_energy - stem.a_site_energy,
                        "closure": closure[0],
                        "upper3": upper3[0],
                        "lower3": lower3[0],
                        "island": island[0],
                        "toehold_trim": 0,
                        "rbs_loop_len": len(gate.RBS_FLANK) + len(gate.RBS_PROKARYOTIC),
                        "secondary_arm": gate.ARM_LEN,
                        "stem_dG": stem_dg[0],
                        "grip_alone": stem_dg[1],
                        "grip_with_x": stem_dg[2],
                        "switch": switch.sequence,
                    }
                    if writer is None:
                        writer = csv.DictWriter(handle, fieldnames=list(row))
                        writer.writeheader()
                    writer.writerow(row)
                    written += 1
                    locks.append(stem.lock_energy)
            # The pair's full key, not its x_start: the summary below counts these, and
            # x_start would collapse the 1036 pairs onto 373 values (see PAIR_KEY_COLUMNS).
            usable_pairs.add(pair_key(pair))
            bar.step(f"x@{pair.x_start}  {len(stems)} stems  {written:,} rows")
            if index and index % 25 == 0:
                handle.flush()  # a run that is killed should leave usable data behind
                interim(
                    f"after {index + 1} pairs",
                    [
                        ("designs written", f"{written:,}"),
                        (
                            "lock energy best / median",
                            f"{min(locks):.1f} / {sorted(locks)[len(locks) // 2]:.1f} kcal/mol",
                        ),
                        (
                            "pairs with no usable stem",
                            str(index + 1 - (len(usable_pairs) - len(already))),
                        ),
                    ],
                )

    bar.finish()
    if not written:
        print("  no designs produced -- no pair had a stem with a negative lock energy")
        return 1
    locks.sort()
    usable = len(usable_pairs)
    conclude(
        [
            f"{written:,} designs enumerated across {usable} trigger pairs, none folded yet.",
            f"Lock energy spans {locks[0]:.1f} to {locks[-1]:.1f} kcal/mol, median "
            f"{locks[len(locks) // 2]:.1f}. It is the strongest single predictor we have "
            f"(rho -0.938 against locked(10)), so it is what stage 2 selects on.",
            f"{len(kept) - usable} of {len(kept)} pairs were dropped for having no stem "
            f"with a negative lock energy: a positive lock is not a lock.",
            "One row per design, every axis its own column, sequence included - so any two "
            "columns can be plotted against each other later without re-running this.",
        ],
        wrote=[str(path)],
    )
    return 0


#: The pair-stem, as SQL. One trigger pair can hold several stems, and `lock_energy`,
#: `a_site_energy` and `scheme` are constant across a pair-stem's 360 axis rows.
_STEM_COLS = "x_start, xstar_start, a_start, a_end, b_start, b_end, stem_index"

#: A total order on pair-stems, so every selection is reproducible. `lock_energy` alone is
#: not: it takes 195 distinct values across 1.49 M rows and its median value is shared by
#: 6,840 of them, so ties decide most of the outcome and must not be left to scan order.
_STEM_ORDER = f"lock_energy, {_STEM_COLS}"

#: A design is *eligible* when trigger A loses to the stem alone and wins once B has freed
#: sw_xs. Of the window's two halves only this conjunction discriminates: `grip_with_x <
#: stem_dG` alone passes 99.8% of the sweep and carries no information, while `grip_alone >
#: stem_dG` passes 29.1%. Necessary and measured to be insufficient -- screen, never rank.
_ELIGIBLE = "grip_with_x < stem_dG AND stem_dG < grip_alone"


def _select_block_a(con, csv_sql: str, n: int) -> str:
    """Block A -- resolve the axes. ``n`` pair-stems crossed with **all 360 axis points**.

    ``closure`` and ``lower3`` are invisible to every stage-1 metric: all six levels of each
    return identical medians for ``lock_energy``, ``stem_dG``, ``grip_alone`` and
    ``grip_with_x``, and identical grip-window membership, because neither reaches
    ``main_z``. **Folding is the only instrument that can separate them**, and the best
    result measured so far is a closure effect (``closed_UAU``, separation 6.90). So this
    block holds the pair-stem roughly fixed and spends its budget on the axes.

    The ``n`` pair-stems are stratified: ``n/2`` per scheme, drawn from ``ntile`` buckets
    over the ``lock_energy`` range, taking each bucket's **median** member rather than its
    extreme -- the tails are single outliers and an axis effect measured only there would
    not generalise. Both schemes are carried explicitly because they differ by 5.2 kcal/mol
    at the A-site while their locks match, and counting alone would let ``B-anchored``
    (61.6% of rows) dominate.

    Restricted to pair-stems with at least one eligible design, which is 3,180 of 4,144, so
    the restriction costs little breadth.
    """
    per_scheme = max(1, n // 2)
    return f"""
    WITH per_stem AS (
      SELECT {_STEM_COLS}, any_value(scheme) AS scheme, any_value(lock_energy) AS lock_energy,
             sum(CASE WHEN {_ELIGIBLE} THEN 1 ELSE 0 END) AS eligible_rows
      FROM {csv_sql} GROUP BY {_STEM_COLS}),
    eligible AS (SELECT * FROM per_stem WHERE eligible_rows > 0),
    bucketed AS (SELECT *, ntile({per_scheme}) OVER
                 (PARTITION BY scheme ORDER BY {_STEM_ORDER}) AS bucket FROM eligible),
    numbered AS (SELECT *, row_number() OVER
                   (PARTITION BY scheme, bucket ORDER BY {_STEM_ORDER}) AS rn,
                   count(*) OVER (PARTITION BY scheme, bucket) AS cnt FROM bucketed)
    SELECT {_STEM_COLS} FROM numbered WHERE rn = (cnt + 1) // 2"""


def _levels(requested: str, axis: tuple[tuple[str, str], ...]) -> set[str]:
    """The axis levels to keep. Empty means all; an unknown name is an error, not a silent
    empty set -- a typo that quietly folds nothing is worse than one that stops the run."""
    names = {label for label, _ in axis}
    if not requested:
        return names
    asked = {part.strip() for part in requested.split(",") if part.strip()}
    unknown = asked - names
    if unknown:
        raise SystemExit(f"unknown axis level(s) {sorted(unknown)}; known: {sorted(names)}")
    return asked


def _select_block_c(con, csv_sql: str, scheme: str, eligible_only: bool) -> str:
    """Block C -- breadth: **every** pair-stem of one scheme, crossed with a restricted grid.

    Block A resolves the axes on a handful of pair-stems and cannot say which *triggers*
    work; block B fixes the axes and varies the triggers one pair-stem at a time. C is the
    version for when the axis grid has already been narrowed enough that the full cross is
    affordable: every pair-stem, every surviving axis point.

    It takes no top-N and applies no ranking. The axis restriction is the whole economy, and
    it is declared on the command line so the output records exactly which grid produced it.
    """
    where = ["1 = 1"]
    if scheme:
        where.append(f"any_value(scheme) = '{scheme}'")
    having = " AND ".join(w for w in where if w != "1 = 1") or "1 = 1"
    eligible = f"HAVING {having} AND sum(CASE WHEN {_ELIGIBLE} THEN 1 ELSE 0 END) > 0"
    return f"""
    SELECT {_STEM_COLS} FROM {csv_sql} GROUP BY {_STEM_COLS}
    {eligible if eligible_only else f"HAVING {having}"}"""


def _select_block_b(con, csv_sql: str, axes: dict[str, str]) -> str:
    """Block B -- test breadth. One pair-stem per trigger pair, at fixed axis settings.

    The complement of Block A: hold the axes fixed at the settings Block A found and vary
    the triggers, which is the only way to learn whether an axis result generalises past the
    handful of pair-stems it was measured on. Takes each pair's strongest eligible lock.
    """
    where = " AND ".join(f"{k} = '{v}'" for k, v in axes.items())
    return f"""
    WITH rows_at_axes AS (SELECT * FROM {csv_sql} WHERE {where} AND {_ELIGIBLE}),
    ranked AS (SELECT *, row_number() OVER
                 (PARTITION BY x_start, xstar_start, a_start, a_end, b_start, b_end
                  ORDER BY {_STEM_ORDER}) AS rn FROM rows_at_axes)
    SELECT {_STEM_COLS} FROM ranked WHERE rn = 1"""


#: What identifies one folded design: its pair-stem plus its four axis settings. Stage 2
#: writes one row per design and the rows are independent, so unlike stage 1 there is no
#: grouping to respect -- a design is either finished or it is not.
DESIGN_KEY_COLUMNS = (*PAIR_KEY_COLUMNS, "stem_index", "closure", "upper3", "lower3", "island")


def _rewind_partial_folds(path: Path) -> tuple[set[tuple[str, ...]], list[str], int]:
    """Trim a torn final row off a partial stage-2 file and return the designs already done.

    A killed run leaves a half-written last line, and ``csv`` hands it back as a short row.
    Requiring the full column count makes a torn line look like the end of the file, which is
    what it is -- the same check stage 1's rewind needs, and the same bug it caught: read
    through ``DictReader`` a fragment becomes a row with real-looking values in the columns
    that survived, and gets recorded as finished work.

    Rewrites to a sibling file and renames only once the copy is complete, so a crash here
    cannot destroy the data it is protecting.

    Returns:
        ``(design keys done, header, rows kept)``.
    """
    csv.field_size_limit(10**7)
    trimmed = path.with_suffix(".trimmed")
    done: set[tuple[str, ...]] = set()
    kept = 0
    with path.open(newline="") as src, trimmed.open("w", newline="") as dst:
        reader = csv.reader(src)
        header = next(reader, None)
        if header is None:
            trimmed.unlink(missing_ok=True)
            return set(), [], 0
        key_cols = [header.index(name) for name in DESIGN_KEY_COLUMNS]
        writer = csv.writer(dst)
        writer.writerow(header)
        for fields in reader:
            if len(fields) != len(header):
                break
            writer.writerow(fields)
            done.add(tuple(fields[col] for col in key_cols))
            kept += 1
    path.unlink()
    trimmed.rename(path)
    return done, header, kept


def _design_key(row: dict) -> tuple[str, ...]:
    """A selected stage-1 row's design key, as strings, to match what the CSV holds."""
    return tuple(str(row[name]) for name in DESIGN_KEY_COLUMNS)


def _append_folds(path: Path, batch: list[dict], header: list[str]) -> list[str]:
    """Append a batch of folded designs, writing the header if the file is new.

    Batched rather than per-row so the file is opened once per batch, and batched *small*
    so an interrupted run loses seconds rather than an hour. ``extrasaction="raise"`` is
    deliberate: on resume the header comes from the existing file, and a new row carrying
    different columns means the two halves are not the same experiment. That must fail
    loudly, not write a file whose rows quietly disagree about what their columns mean.
    """
    if not batch:
        return header
    fresh = not path.exists() or path.stat().st_size == 0
    if fresh:
        header = sorted(batch[0])
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="raise")
        if fresh:
            writer.writeheader()
        writer.writerows(batch)
    return header


def _conclude_fold(path: Path, args) -> int:
    """Close out stage 2 by reading the finished file, so resumed rows are included.

    Reading the file back rather than summarising the rows this session produced is what
    makes ``--resume`` honest: a run that folded 200 designs on top of 3,400 resumed ones
    would otherwise report the best of 200 and call it the best of the block.
    """
    con = duckdb.connect()
    folded = f"read_csv_auto('{path.as_posix()}')"
    total = con.execute(f"SELECT count(*) FROM {folded}").fetchone()[0]

    def best(key: str):
        return con.execute(
            f"SELECT {key}, separation, A_M_gain, mean_separation, log10_rate_advantage, "
            f"x_start, closure, upper3, island FROM {folded} "
            f"WHERE {key} IS NOT NULL ORDER BY {key} DESC LIMIT 1"
        ).fetchone()

    e, k = best("mean_separation"), best("log10_rate_advantage")
    gated = con.execute(
        f"SELECT count(*) FROM {folded} WHERE mean_separation > 0 AND A_M_11 > 0.3"
    ).fetchone()[0]
    measured = con.execute(
        f"SELECT count(mean_separation), count(separation), count(A_M_gain) FROM {folded}"
    ).fetchone()

    findings = [f"{total:,} designs folded in all four tubes."]
    if e is None:
        findings.append("Arm E could not be ranked: mean_separation was never measurable.")
    else:
        findings.append(
            f"Arm E, equilibrium, ranked on mean_separation per SELECTION_SPEC section 1: "
            f"best {e[0]:.3f} at x@{e[5]}, closure {e[6]}, upper3 {e[7]}, island {e[8]}. That "
            f"same design scores separation {_num(e[1], 1, 2).strip()} and A_M_gain "
            f"{_num(e[2], 1, 3).strip()} -- all three side by side, because they rank "
            f"differently and only the bench can say which was right."
        )
    if k is not None:
        findings.append(
            f"Arm K, kinetic: best nucleation advantage 10^{k[0]:.1f} at x@{k[5]}, whose "
            f"mean_separation is {_num(k[3], 1, 3).strip()}. The two arms need not agree, and "
            f"where they disagree is the informative part."
        )
    findings += [
        f"{gated} designs have BOTH mean_separation > 0 and A_M(11) > 0.3 - they turn off "
        f"without failing to turn on. Neither alone is sufficient: the rows with the largest "
        f"separation are usually the ones that never open at all.",
        f"Measurable rows: mean_separation {measured[0]:,}, separation {measured[1]:,}, "
        f"A_M_gain {measured[2]:,}, of {total:,}. A metric that could not be computed is "
        f"empty, never zero.",
        "No threshold filtered anything here. Every tau gate is reported in the CSV and none "
        "of them removed a row.",
    ]
    conclude(findings, wrote=[str(path)])
    return 0


def _num(value, width: int, places: int) -> str:
    """Format a metric, or ``n/a`` when it could not be measured.

    A metric we failed to compute is ``None``, never 0.0 -- a zero here would read as a
    perfect OFF state and outrank every design that was actually measured.
    """
    return f"{value:>{width}.{places}f}" if value is not None else "n/a".rjust(width)


def _best_of(rows: list[dict], key: str, places: int) -> str:
    """``best (n measured of N)`` for one metric, so an unmeasured majority is visible."""
    values = [r[key] for r in rows if r.get(key) is not None]
    if not values:
        return f"n/a (0 measured of {len(rows)})"
    return f"{max(values):.{places}f}   ({len(values)} measured of {len(rows)})"


def _fold(gate, transcript, args, output_dir) -> int:
    # One file when stage 1 ran in a single process, one per shard when it ran across
    # cores. Both spellings must work here, for the same reason fold_analysis had to learn
    # them: a sharded stage 1 whose output stage 2 cannot see fails as "not found" after
    # the expensive half is already done.
    shards_in = sorted(output_dir.glob(f"{args.out}_cheap_*.csv"))
    single = output_dir / f"{args.out}_cheap.csv"
    sources_in = shards_in or ([single] if single.exists() else [])
    if not sources_in:
        print(f"no {args.out}_cheap*.csv in {output_dir} -- run --stage cheap first")
        return 1

    # duckdb reads the CSV in place, so the 690 MB file is never loaded and the selection
    # costs about 1.7 s. It also keeps stage 2 on ONE input: the Parquet copy that
    # sweep_analysis.py derives drops the `switch` column, which stage 2 needs.
    con = duckdb.connect()
    csv_sql = (
        "read_csv_auto(["
        + ", ".join(f"'{p.as_posix()}'" for p in sources_in)
        + "], union_by_name=true)"
    )
    scanned = con.execute(f"SELECT count(*) FROM {csv_sql}").fetchone()[0]

    # The axis grid, restricted by whatever the command line named. Applied to `chosen`
    # below rather than to the constants, so the full grid is still what stage 1 wrote and
    # the restriction is visible in this run's banner instead of hidden in a constant.
    keep = {
        "closure": _levels(args.closures, CLOSURES),
        "upper3": _levels(args.upper3, UPPER3),
        "lower3": _levels(args.lower3, LOWER3),
        "island": _levels(args.island, ISLAND),
    }
    axis_points = (
        len(keep["closure"]) * len(keep["upper3"]) * len(keep["lower3"]) * len(keep["island"])
    )
    if args.block == "A":
        picked = _select_block_a(con, csv_sql, args.pair_stems)
        what = f"Block A -- {args.pair_stems} pair-stems x all {axis_points} axis points"
        detail = [
            f"{args.pair_stems // 2} pair-stems per scheme, spanning the lock_energy range",
            "closure and lower3 are invisible to every stage-1 metric; folding is the only",
            "instrument that can separate them, which is what this block is for",
        ]
    elif args.block == "C":
        picked = _select_block_c(con, csv_sql, args.scheme, args.eligible_only)
        what = f"Block C -- every pair-stem x {axis_points} axis points"
        detail = [
            f"scheme {args.scheme or 'any'}"
            + (", grip-window eligible only" if args.eligible_only else ", all pair-stems"),
            "no top-N and no ranking: the axis restriction is the whole economy",
        ]
    else:
        axes = dict(pair.split("=", 1) for pair in args.ref_axes.split(",") if pair)
        if not axes:
            print("--block B needs --ref-axes, e.g. --ref-axes closure=closed_UAU,island=WWW")
            return 1
        picked, what = _select_block_b(con, csv_sql, axes), "Block B -- breadth across triggers"
        detail = [
            f"axes held at {', '.join(f'{k}={v}' for k, v in axes.items())}",
            "one pair-stem per trigger pair, its strongest eligible lock",
        ]

    result = con.execute(f"SELECT c.* FROM {csv_sql} c SEMI JOIN ({picked}) p USING ({_STEM_COLS})")
    columns = [d[0] for d in result.description]
    chosen = [dict(zip(columns, values, strict=True)) for values in result.fetchall()]
    if not chosen:
        print("  the selection matched no rows -- check --ref-axes against the axis names")
        return 1
    before = len(chosen)
    # Axis levels are baked into stage 1's output: a level added to the constants AFTER a
    # sweep ran simply is not in its rows, and the filter below would drop it in silence.
    # That cost a preview run its entire wobble_GU arm without any error. A level asked for
    # and absent is a stale stage-1 file, not an empty selection.
    for name, levels in keep.items():
        present = {r[name] for r in chosen}
        missing = levels - present
        if missing:
            print(f"  ** {name} level(s) {sorted(missing)} are absent from {args.out}_cheap*.csv.")
            print(f"  ** Stage 1 wrote {sorted(present)}.")
            print("  ** A level added to the constants after that sweep ran is not in")
            print("  ** its rows. Re-run --stage cheap WITHOUT --resume, or drop the")
            print("  ** level from this command.")
            return 1
    chosen = [r for r in chosen if all(r[name] in levels for name, levels in keep.items())]
    if not chosen:
        named = {k: sorted(v) for k, v in keep.items()}
        print(f"  the axis restriction removed all {before:,} rows. Levels asked for: {named}")
        return 1
    # Sharded by trigger PAIR, never by row. secondary_stems enumerates 3^n builds and costs
    # ~2.1 s, memoised per pair; scattering one pair's designs across shards would make every
    # shard pay that again. Measured at this scale that is 1,014 pairs x 2.1 s x 6 shards =
    # about 3.5 hours of pure waste.
    shard_suffix = ""
    if args.shard:
        index_text, _, count_text = args.shard.partition("/")
        shard, shards = int(index_text), int(count_text or 0)
        if not 0 <= shard < shards:
            print(f"--shard {args.shard} is not of the form i/n with 0 <= i < n")
            return 1
        order = sorted({tuple(r[c] for c in PAIR_KEY_COLUMNS) for r in chosen})
        mine = {key for position, key in enumerate(order) if position % shards == shard}
        chosen = [r for r in chosen if tuple(r[c] for c in PAIR_KEY_COLUMNS) in mine]
        shard_suffix = f"_{shard}"
        if not chosen:
            print(f"  shard {shard} of {shards} has no pairs -- nothing to do")
            return 0

    stems_chosen = len({tuple(r[c] for c in _STEM_COLS.split(", ")) for r in chosen})
    pairs_chosen = len({tuple(r[c] for c in PAIR_KEY_COLUMNS) for r in chosen})
    eligible = sum(1 for r in chosen if r["grip_with_x"] < r["stem_dG"] < r["grip_alone"])

    # Folding streams to the file and can be resumed, because an hour of folding is too much
    # to lose to one interruption. Each row is one design and the rows are independent, so
    # resuming is just "skip the designs already there".
    path = output_dir / f"{args.out}_folded{shard_suffix}.csv"
    header: list[str] = []
    already = 0
    done_keys: set[tuple[str, ...]] = set()
    if args.resume and path.exists():
        print(f"  resuming: reading {path.name} and dropping any torn final row")
        done_keys, header, already = _rewind_partial_folds(path)
        print(f"  {already:,} designs already folded, keeping them\n")
    elif args.resume:
        print(f"  --resume given but {path.name} does not exist; starting from the top\n")
    todo = [r for r in chosen if _design_key(r) not in done_keys]

    banner(
        f"STAGE 2 - {what}",
        [
            (f"shard {shard} of {shards}, by trigger pair.  " if args.shard else "")
            + f"{scanned:,} designs from stage 1, folding {len(todo):,}"
            + (f" (plus {already:,} resumed)" if already else ""),
            *detail,
            f"covering {pairs_chosen} trigger pairs and {stems_chosen} pair-stems; "
            f"{eligible:,} of {len(chosen):,} ({100 * eligible / len(chosen):.0f}%) are eligible",
            "each design: four tubes, every observable, 1.2 to 1.6 s",
        ],
        estimate=len(todo) * 1.6,
    )
    if not todo:
        print("  every selected design is already folded -- nothing to do\n")
        return _conclude_fold(path, args)
    bar = Progress(len(todo), "designs")

    rows: list[dict] = []
    batch: list[dict] = []
    stem_cache: dict[tuple[str, str, int], list] = {}
    axis_lookup = {
        "closure": dict(CLOSURES),
        "upper3": dict(UPPER3),
        "lower3": dict(LOWER3),
        "island": dict(ISLAND),
    }
    for index, row in enumerate(todo):
        # Rebuilt from the axis columns, not from the stored sequence, so stage 2 has the
        # full domain map and any disagreement between the two surfaces as an assertion
        # rather than as a silently wrong span.
        trigger_a = transcript[int(row["a_start"]) : int(row["a_end"])]
        trigger_b = transcript[int(row["b_start"]) : int(row["b_end"])]
        len_x = int(row["len_x"])
        # Memoised per PAIR, not per design. secondary_stems enumerates 3^n builds and costs
        # ~2.1 s; the selection puts many designs on the same pair, so re-running it per row
        # was costing more than the folding it was feeding. Measured: 3.2 s/design before,
        # 1.2 s after.
        key = (trigger_a, trigger_b, len_x)
        if key not in stem_cache:
            # MUST order exactly as stage 1 did, or stem_index means something different
            # here than it did there and every rebuilt switch is the wrong one. The
            # assertion below is what would catch it.
            stem_cache[key] = sorted(
                (s for s in gate.secondary_stems(*key) if s.lock_energy <= 0.0),
                key=lambda s: getattr(s, args.stems_by),
            )
        stems = stem_cache[key]
        stem = stems[int(row["stem_index"])]
        base = gate.assemble(trigger_a, trigger_b, len_x, stem)
        switch = build(base, {name: axis_lookup[name][row[name]] for name in axis_lookup})
        if switch.sequence != row["switch"]:
            raise AssertionError(f"rebuild disagrees with stage 1 at row {index}")

        observed = gate.four_tube_observables(switch, trigger_a, trigger_b)
        rank = switch.span(-17, 13)
        out = dict(row)
        for state in ("00", "01", "10", "11"):
            strands = {
                "00": switch.sequence,
                "01": f"{switch.sequence}&{trigger_b}",
                "10": f"{switch.sequence}&{trigger_a}",
                "11": f"{switch.sequence}&{trigger_a}&{trigger_b}",
            }[state]
            matrix = gate.folder.pooled_pair_probabilities(strands)
            out[f"dG_open_{state}"] = observed[f"dG_open_{state}"]
            out[f"P_open_{state}"] = gate.folder.p_open(strands, rank)
            out[f"A_M_{state}"] = observed[f"A_M_{state}"]
            out[f"meanW_{state}"] = _mean_unpaired(matrix, *rank)
            out[f"aug_{state}"] = _mean_unpaired(matrix, *switch.domains["aug"])
            out[f"free_xstar_{state}"] = _mean_unpaired(matrix, *switch.domains["sw_xs"])
            # VISTA's Ideal Ensemble Defect over the RBS-through-linker stretch. Its
            # specified structure for a region that must be free is "completely unpaired",
            # so over such a region the IED collapses to the MEAN BASE-PAIRING probability
            # -- which is why this needs no NUPACK and no invented target structure.
            #
            # Calibrated against Green's 168 measured switches it is the strongest
            # correctly-signed predictor available to us (rho -0.356), ahead of Green's own
            # dG_RBS-linker (+0.334) over the identical span and of A_M_gain (+0.320), which
            # is what we rank on. LOWER is better. Flat on the toehold (+0.03), so it is the
            # region carrying the prediction rather than the statistic.
            out[f"ied_rbs_linker_{state}"] = 1.0 - _mean_unpaired(
                matrix, switch.domains["rbs_loop"][0], switch.domains["linker"][1]
            )
            # The x* three-way decomposition (SELECTION_SPEC 4.4). `free_xstar` above is an
            # unpaired probability and so cannot tell the lock HOLDING from the lock torn
            # OPEN -- both leave x* paired. Asking *what* x* is paired to does: to its own
            # sw_x arm (locked), or to a trigger (engaged). Measured on the panel, state 01
            # reads locked 0.000 / free 0.925 while state 00 reads locked 0.926, which is
            # the unlocking event, and no column here could previously show it.
            # Free from the matrix already folded above, so this adds no folds at all.
            lo, hi = switch.domains["sw_xs"]
            width = hi - lo
            out[f"xstar_locked_{state}"] = (
                sum(matrix[i][j] for i in range(lo, hi) for j in range(*switch.domains["sw_x"]))
                / width
            )
            # The matrix is symmetric, so ONE term per pair: summing m[i][j] + m[j][i]
            # double-counts and pushes a probability above 1.0. In a multi-strand complex it
            # is indexed over the concatenation with the "&" removed, strands in the order
            # written, so each trigger's block is found by offset.
            base = len(switch.sequence)
            blocks = {
                "00": {},
                "01": {"B": (base, base + len(trigger_b))},
                "10": {"A": (base, base + len(trigger_a))},
                "11": {
                    "A": (base, base + len(trigger_a)),
                    "B": (base + len(trigger_a), base + len(trigger_a) + len(trigger_b)),
                },
            }[state]
            for name in ("A", "B"):
                span = blocks.get(name)
                # None, never 0.0, when that trigger is not in the tube: there is nothing to
                # measure, and a 0.0 would read as "measured, and it does not bind".
                out[f"xstar_eng{name}_{state}"] = (
                    sum(matrix[i][j] for i in range(lo, hi) for j in range(*span)) / width
                    if span
                    else None
                )
        # The x* mechanism as one number, from columns this loop has already filled -- no
        # extra folding at all. The geometric mean of the four things the lock must do, all
        # probabilities in [0,1] where higher is right, so ONE failure pulls the score down
        # instead of being averaged away.
        #
        # It is the check a Pareto front cannot express. A switch whose lock trigger A tears
        # open by itself is non-dominated on (ratio, kinetics, A_M(11)) -- it opens, and it
        # opens fast -- while its ON/OFF ratio is 1.0 and it does not gate at all. Measured
        # on the candidate panel the two groups separate cleanly: 0.02 to 0.29 for a torn
        # lock against 0.78 to 0.87 for an intact one.
        mech = [
            out["xstar_locked_00"],  # the lock holds with no trigger
            out["xstar_locked_10"],  # and still holds with trigger A alone
            out["free_xstar_01"],  # trigger B alone frees x*
            out["xstar_engA_11"],  # trigger A then takes the freed site
        ]
        # None, never 0.0, when any term is missing: a zero would read as a measured failure
        # and rank the design as the worst available rather than as unmeasured.
        out["x_mech"] = (
            None
            if any(v is None for v in mech)
            else math.exp(sum(math.log(max(v, 1e-6)) for v in mech) / 4)
        )
        out["separation"] = observed["separation"]
        out["ddG_AND"] = observed["ddG_AND"]
        out["dG_bind_B"] = observed["dG_bind_B"]
        # Both were computed by `four_tube_observables` on every run so far and then dropped
        # on the floor here, because this dict is hand-picked rather than copied wholesale.
        out["dG_bind_A_given_B"] = observed["dG_bind_A_given_B"]
        out["A_r2_star_00"] = observed["A_r2_star_00"]
        out["d_off"] = observed["d_off"]
        # Every "gain" here is state 11 against the WORST of the three OFF states, not
        # against 10 alone. An AND that leaks in any one of 00/01/10 is broken, so the worst
        # is the honest comparator, and using the same shape for both keeps them comparable.
        means = [out[f"meanW_{st}"] for st in ("00", "01", "10", "11")]
        out["mean_separation"] = (
            means[3] - max(means[:3]) if all(m is not None for m in means) else None
        )
        a_m = [out[f"A_M_{st}"] for st in ("00", "01", "10", "11")]
        out["A_M_gain"] = a_m[3] - max(a_m[:3]) if all(v is not None for v in a_m) else None
        # The kinetic arm: what trigger A finds on arrival, before it binds, on each path.
        out["log10_rate_advantage"] = min(6.0, len_x * out["free_xstar_01"]) - min(
            6.0, len_x * out["free_xstar_00"]
        )
        rows.append(out)
        batch.append(out)
        if len(batch) >= 25:  # ~40 s of folding, the most an interruption can cost
            header = _append_folds(path, batch, header)
            batch.clear()
        # SELECTION_SPEC.md section 1 makes `mean_separation` the equilibrium arm, so it
        # leads here. The joint `separation` is shown beside it -- section 4.4 asks for both
        # forms always -- but it is NOT what Arm E ranks on: against Green's 168 measured
        # switches it scored rho -0.107, while A_M_gain scored +0.320.
        bar.step(
            f"{row['closure']:<11} msep {_num(out['mean_separation'], 5, 2)}"
            f"  sep {_num(out['separation'], 5, 2)}"
            f"  A_Mg {_num(out['A_M_gain'], 6, 3)}"
        )
        if index and index % 200 == 0:
            interim(
                f"after {index + 1} designs",
                [
                    ("ranking arm E: best mean_separation", _best_of(rows, "mean_separation", 3)),
                    ("  reported beside it: separation", _best_of(rows, "separation", 2)),
                    ("  reported beside it: A_M_gain", _best_of(rows, "A_M_gain", 3)),
                    (
                        "ranking arm K: best log10_rate_adv",
                        _best_of(rows, "log10_rate_advantage", 1),
                    ),
                ],
            )

    bar.finish()
    _append_folds(path, batch, header)  # whatever the last partial batch held
    return _conclude_fold(path, args)


if __name__ == "__main__":
    raise SystemExit(main())
