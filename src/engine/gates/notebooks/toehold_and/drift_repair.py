"""Repair designs built against a transcript base that has since been corrected.

    # what it would do, nothing written
    uv run python src/engine/gates/notebooks/toehold_and/drift_repair.py --dry-run

    # patch and rescore, resumable, shardable like every other long run here
    uv run python src/engine/gates/notebooks/toehold_and/drift_repair.py --out drift_fixed
    uv run python src/engine/gates/notebooks/toehold_and/drift_repair.py \
        --out drift_fixed --shard 0/4

**What this can and cannot do, measured rather than assumed.** The claim that a corrected
transcript base maps to one determined switch position is only true where the switch is the plain
reverse complement of the window. Checked on clean designs of both geometries:

    trigger B's window   the FULL 49-nt reverse complement sits at switch[3]   -> patchable
    trigger A's window   the longest plain revcomp block is 8 nt of 35         -> NOT patchable

Trigger A's region is where scheme C assigns each conflict base to serve A, to serve B, or to hold
the lock, so it is not a complement and a correction there can change which assignment is best.
Those designs need the generator, and this script **refuses** them rather than patching something
it cannot justify.

Of the designs that pass every filter except the drift one, that split is about 871 trigger-B-only
against 788 involving trigger A. So this recovers roughly half, and names the other half.

The patch itself is verified before it is applied: the script locates the window's reverse
complement inside the switch, asserts the base at the mapped position is the complement of the
**old** transcript base, and only then writes the complement of the new one. A design whose
mapping cannot be established that way is skipped and counted, never guessed at.
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402
from objective_panel import DRIFTED_POSITIONS as DRIFTED  # noqa: E402
from transcript_drift import previous  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

#: Shortest reverse-complement block accepted as a unique anchor, in nt.
MIN_BLOCK = 12

FIELDS = (
    "switch",
    "switch_before",
    "patched_positions",
    "a_start",
    "a_end",
    "b_start",
    "b_end",
    "len_x",
    "scheme",
    "closure",
    "upper3",
    "lower3",
    "pair",
    "open_00",
    "open_01",
    "open_10",
    "open_11",
    "andness",
    "barrier",
    "verdict",
)


def map_position(switch: str, window: str, start: int, position: int) -> int | None:
    """Switch index pairing with transcript ``position``, or ``None`` if not determined.

    Found by locating the window's reverse complement inside the switch, so the layout is read
    off the actual sequence rather than assumed from the domain table. The reverse complement
    runs antiparallel: window offset ``k`` maps to revcomp offset ``len - 1 - k``.
    """
    from engine import sequences as sq

    offset = position - start
    if not 0 <= offset < len(window):
        return None
    # The whole window's reverse complement is often NOT in the switch: the secondary hairpin
    # carries only part of trigger B, and how much depends on len_x and the k2* geometry.
    # Measured, insisting on the whole window found 353 of 1,659 designs; most of the rest are
    # trigger-B-only with a partial block.
    #
    # So search for the longest block of the reverse complement that CONTAINS this position and
    # appears EXACTLY ONCE in the switch. Uniqueness is the safety condition -- a short block can
    # match in several places and then the mapping is a guess, which is the one thing this must
    # not do. MIN_BLOCK is 12 nt: long enough that a chance match in a 165-nt switch is unlikely,
    # and every accepted mapping is then re-verified against the OLD base by the caller.
    rc = sq.reverse_complement(window)
    rc_index = len(window) - 1 - offset
    best: int | None = None
    for length in range(len(rc), MIN_BLOCK - 1, -1):
        for lo in range(max(0, rc_index - length + 1), min(rc_index, len(rc) - length) + 1):
            block = rc[lo : lo + length]
            first = switch.find(block)
            if first < 0 or switch.find(block, first + 1) >= 0:
                continue
            best = first + (rc_index - lo)
            break
        if best is not None:
            break
    return best


def repair(switch: str, row: dict, before: str, after: str) -> tuple[str | None, list[int], str]:
    """The patched switch, the switch positions touched, and why if it could not be done."""
    from engine import sequences as sq

    a_start, a_end = int(row["a_start"]), int(row["a_end"])
    b_start, b_end = int(row["b_start"]), int(row["b_end"])
    positions = op.covers_drift(row)
    if any(a_start <= p < a_end for p in positions):
        return None, [], "trigger A involved -- needs the generator, not a patch"

    window_before = before[b_start:b_end]
    out = list(switch)
    touched: list[int] = []
    for position in positions:
        index = map_position(switch, window_before, b_start, position)
        if index is None:
            return None, [], "window's reverse complement not found in the switch"
        expected = sq.reverse_complement(before[position])
        if out[index] != expected:
            return (
                None,
                [],
                (
                    f"switch[{index}] is {out[index]}, expected {expected} "
                    f"as the complement of the OLD base {before[position]}"
                ),
            )
        out[index] = sq.reverse_complement(after[position])
        touched.append(index)
    return "".join(out), touched, ""


def status(results: Path, out: str, targets: list[dict], before: str, after: str) -> int:
    """How far the repair has got, against what it can actually reach.

    Progress is reported against the **patchable** set, not the whole scope. Most of the scope is
    refused by design -- trigger A involved -- and printing "788 left" would read as a stalled run
    rather than a declared refusal.
    """
    path = results / f"{out}.csv"
    reach: Counter = Counter()
    for row in targets:
        patched, _touched, why = repair(row["switch"], row, before, after)
        reach["patchable" if patched is not None else why] += 1

    print(f"  designs in scope (pass every filter but the drift one): {len(targets):6,d}")
    for why, count in reach.most_common():
        print(f"    {count:6,d}  {why}")

    if not path.exists():
        print(f"\n  {path.name} does not exist yet -- nothing repaired.")
        print(f"  {reach['patchable']:,} designs are waiting.")
        print("\n  start it with:")
        print(
            f"    uv run python src/engine/gates/notebooks/toehold_and/drift_repair.py --out {out}"
        )
        return 0

    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    done = {r["switch_before"] for r in rows if r.get("switch_before")}
    in_scope = done & {r["switch"] for r in targets}
    todo = max(reach["patchable"] - len(in_scope), 0)

    print(f"\n  {path.name}: {len(rows):,} rows written")
    print(f"  patched and still in scope:                             {len(in_scope):6,d}")
    print(f"  patchable and still to do:                              {todo:6,d}")
    if reach["patchable"]:
        print(
            f"  progress against the patchable set:                      "
            f"{100.0 * len(in_scope) / reach['patchable']:5.1f}%"
        )
    stale = len(done) - len(in_scope)
    if stale:
        print(
            f"  rows for designs no longer in scope:                    {stale:6,d}"
            "  (kept, not deleted)"
        )
    if todo:
        print("\n  rerun the same command to continue; it skips what is already written:")
        print(
            f"    uv run python src/engine/gates/notebooks/toehold_and/drift_repair.py --out {out}"
        )
    else:
        print("\n  the patchable set is complete.")
    return 0


def verify(results: Path, out: str, before: str, after: str) -> int:
    """Check each written row against the two transcripts, without trusting this module's mapping.

    **The map is ANTIPARALLEL, and that is the trap.** A reverse complement runs backwards, so a
    LARGER transcript position maps to a SMALLER switch position. A first version of this check
    paired ``sorted(drifted_positions)`` with ``sorted(patched_positions)`` and reported 87 of 773
    rows as broken -- every row carrying two corrections, because their pairing was inverted. The
    data was correct and the check was not.

    So no ordering is assumed: for each corrected transcript position this looks for ANY patched
    switch position that holds the complement of the old base before and of the new base after, and
    requires a one-to-one assignment covering every edit. A row with an edit nothing explains fails.
    """
    from engine import sequences as sq

    path = results / f"{out}.csv"
    if not path.exists():
        print(f"  {path.name} does not exist.")
        return 1
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    ok = 0
    failures: list[tuple[dict, str]] = []
    for row in rows:
        old, new = row["switch_before"], row["switch"]
        claimed = (
            sorted(int(v) for v in row["patched_positions"].split())
            if row["patched_positions"]
            else []
        )
        actual = sorted(i for i, (x, y) in enumerate(zip(old, new, strict=True)) if x != y)
        if actual != claimed:
            failures.append((row, "patched_positions disagrees with the diff"))
            continue
        b_start, b_end = int(row["b_start"]), int(row["b_end"])
        corrected = [p for p in sorted(DRIFTED) if b_start <= p < b_end]
        free = list(claimed)
        for position in corrected:
            match = [
                index
                for index in free
                if old[index] == sq.reverse_complement(before[position])
                and new[index] == sq.reverse_complement(after[position])
            ]
            if not match:
                failures.append((row, f"no switch position explains the correction at {position}"))
                break
            free.remove(match[0])
        else:
            if free:
                failures.append((row, f"{len(free)} edit(s) nothing explains"))
            else:
                ok += 1

    scored = sum(
        1
        for row in rows
        for keys in [("open_00", "open_01", "open_10", "open_11", "andness", "barrier")]
        if all(row.get(k) not in (None, "") for k in keys)
    )
    print(f"  {len(rows):,} rows in {path.name}")
    print(f"  patches verified against both transcripts: {ok:,}")
    print(f"  rows failing verification:                 {len(failures):,}")
    for row, why in failures[:8]:
        print(f"    pair {row['pair']}, positions {row['patched_positions']}: {why}")
    print(f"  rescored in all four tubes:                {scored:,}")
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="drift_fixed", help="results/<name>.csv")
    parser.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    parser.add_argument("--shard", default="", help="i/n")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="re-derive every written patch from the two transcripts and report mismatches",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="how far the repair has got and what is left; reads the output, runs nothing",
    )
    args = parser.parse_args(argv)

    results = NB / "results"
    after = read_fasta(NB / "mCherry_original.txt")
    before = previous(NB / "mCherry_original.txt")
    if len(before) != len(after):
        print("  transcript length changed; coordinates do not carry over. Rebuild the sweep.")
        return 1

    rows = op.load(results)
    op.add_accessibility(rows, results)
    op.add_completions(rows, results)
    op.add_offtarget(rows, results)

    def fails_other(row: dict) -> bool:
        if row["open_11f"] is None or row["open_11f"] > op.ON_CEILING:
            return True
        if row["scheme"] in op.DEAD_SCHEMES:
            return True
        for key, floor, lower in (
            ("aug_11", op.AUG_FLOOR, False),
            ("lock", op.LOCK_FLOOR, True),
            ("lock01", op.LOCK01_FLOOR, True),
            ("hairpin_worst", op.HAIRPIN_FLOOR, True),
            ("engaged_arm_11", op.ARM_FLOOR, True),
        ):
            value = row.get(key)
            if value is None:
                continue
            if (value < floor) if lower else (value <= floor):
                return True
        if row.get("offtarget_fires"):
            return True
        if row.get("l_green") is not None and row["l_green"] <= op.L_GREEN_FLOOR:
            return True
        if op.out_of_frame_augs(row["switch"]):
            return True
        if any(c in oe.RARE_CODONS for c in oe.early_codons(row["switch"])):
            return True
        return row["f1"] is None or row["f1"] > op.GATING

    targets = [r for r in rows if op.covers_drift(r) and not fails_other(r)]
    print(f"  {len(targets):,} designs pass every filter except the drift one")

    if args.shard:
        index, total = (int(v) for v in args.shard.split("/"))
        targets = [r for i, r in enumerate(targets) if i % total == index]
        print(f"  shard {index} of {total}: {len(targets):,} designs")
    if args.limit:
        targets = targets[: args.limit]

    if args.verify:
        return verify(results, args.out, before, after)
    if args.status:
        return status(results, args.out, targets, before, after)

    reasons = Counter()
    patched = []
    for row in targets:
        switch, touched, why = repair(row["switch"], row, before, after)
        if switch is None:
            reasons[why] += 1
            continue
        reasons["patched"] += 1
        patched.append((row, switch, touched))

    print("\n  what the patch could do:")
    for why, count in reasons.most_common():
        print(f"    {count:6,d}  {why}")

    if args.dry_run:
        print("\n  --dry-run: nothing written.")
        return 0
    if not patched:
        print("\n  nothing to write.")
        return 0

    path = results / f"{args.out}.csv"
    done: set[str] = set()
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            done = {r["switch_before"] for r in csv.DictReader(handle) if r.get("switch_before")}
        print(f"\n  resuming: {len(done):,} already rescored in {path.name}")
    mode = "a" if done else "w"

    folder = FoldEngine(37.0)
    transcript = after
    written = 0
    with path.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), extrasaction="ignore")
        if mode == "w":
            writer.writeheader()
        for number, (row, switch, touched) in enumerate(patched):
            if row["switch"] in done:
                continue
            trig_a = transcript[int(row["a_start"]) : int(row["a_end"])]
            trig_b = transcript[int(row["b_start"]) : int(row["b_end"])]
            scored = oe.score_design(folder, switch, trig_a, trig_b, on_ceiling=None)
            out = {
                "switch": switch,
                "switch_before": row["switch"],
                "patched_positions": " ".join(str(i) for i in touched),
                "verdict": "patched and rescored",
            }
            for key in (
                "a_start",
                "a_end",
                "b_start",
                "b_end",
                "len_x",
                "scheme",
                "closure",
                "upper3",
                "lower3",
                "pair",
            ):
                out[key] = row.get(key)
            for key in ("open_00", "open_01", "open_10", "open_11", "andness", "barrier"):
                out[key] = scored.get(key)
            writer.writerow(out)
            handle.flush()
            written += 1
            if number % 25 == 0:
                print(f"    {number + 1}/{len(patched)}  written {written:,}", flush=True)
    print(f"\n  wrote {written:,} rescored designs to {path.name}")
    print("  These are NOT joined into the panel automatically: they are new switch sequences,")
    print("  so they belong in a sweep output that objective_energy and complete_panel then see.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
