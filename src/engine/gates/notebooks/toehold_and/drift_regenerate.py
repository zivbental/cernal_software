"""Regenerate the drift-affected designs a patch cannot fix, from their axis columns.

    uv run python src/engine/gates/notebooks/toehold_and/drift_regenerate.py --dry-run
    uv run python src/engine/gates/notebooks/toehold_and/drift_regenerate.py --out drift_regen
    uv run python src/engine/gates/notebooks/toehold_and/drift_regenerate.py --status

``drift_repair.py`` handles the designs whose correction lands in trigger B's window, where the
switch is the plain reverse complement and one base maps to one base. It refuses the 788 whose
correction lands in trigger **A**'s window, and the refusal is right: that region is where scheme C
assigns each conflict position to serve A, to serve B, or to hold the lock, so a corrected base can
change which assignment is best. Patching one base there would keep a build that is no longer the
build the enumeration would have chosen.

So those are **regenerated** rather than patched. Every design carries the axis columns it was built
from -- ``closure``, ``upper3``, ``lower3``, ``island`` and ``stem_index`` -- and
``full_sweep`` rebuilds a switch from exactly those. Re-running the enumeration against the
corrected triggers and rebuilding at the same axis point gives the design the generator would have
produced had the reference been right.

**``stem_index`` is deliberately not trusted.** It indexes into the Pareto front, and the front is
recomputed from the corrected triggers -- it can change length, and position *i* can be a different
stem. Carrying the old index across would silently rebuild the wrong design, which is exactly the
class of error the whole drift exercise is about. Instead every stem on the new front is rebuilt at
the row's axis point and the one closest to the original by sequence identity is kept, with the
identity reported so a poor match is visible rather than assumed away.

Cost is dominated by the enumeration, which is per PAIR and memoised: 2.1 s per pair over 57 pairs,
then one assembly and four tubes per design.
"""

import argparse
import csv
import glob
import sys
from collections import Counter
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402
from drift_fold import FIELDS as FOLD_FIELDS  # noqa: E402
from drift_fold import observables  # noqa: E402
from full_sweep import CLOSURES, ISLAND, LOWER3, UPPER3, build, read_fasta  # noqa: E402

from engine.domain import Host  # noqa: E402
from engine.gates.toehold import (  # noqa: E402
    KimSecondaryArmToeholdAndGate,
    ProkaryoticToeholdAndGate,
)
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

OBJ_FIELDS = (
    "switch",
    "a_start",
    "a_end",
    "b_start",
    "b_end",
    "len_x",
    "open_00",
    "open_01",
    "open_10",
    "open_11",
    "andness",
    "barrier",
    "access_a",
    "access_b",
)

EXTRA = (
    "switch_before",
    "identity",
    "stem_index_before",
    "stem_index_after",
    "front_size",
    "outcome",
)


def axis_columns(results: Path) -> dict[str, dict]:
    """``switch -> {closure, upper3, lower3, island, stem_index}`` off the folded shards.

    ``objective_panel.load`` carries four of the five but not ``island`` or ``stem_index``, and a
    rebuild needs all of them, so this reads the shards directly rather than widening ``load`` for
    one caller.
    """
    want = ("closure", "upper3", "lower3", "island", "stem_index")
    out: dict[str, dict] = {}
    for path in sorted(glob.glob(str(results / "*_folded_*.csv"))):
        with open(path, encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "stem_index" not in reader.fieldnames:
                continue
            for row in reader:
                switch = row.get("switch")
                if switch and switch not in out:
                    out[switch] = {key: row.get(key) for key in want}
    return out


def identity(left: str, right: str) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    return sum(1 for a, b in zip(left, right, strict=True) if a == b) / len(left)


def write_one(writer, handle, obj_rows: dict, made: tuple, transcript: str, folder) -> None:
    """Fold, score and write ONE design, flushing as it goes.

    Separated out so the loop has nothing to accumulate: a run killed at any point keeps every
    design it had finished, and `--status` can see how far it got.
    """
    row, fields = made
    trig_a = transcript[int(row["a_start"]) : int(row["a_end"])]
    trig_b = transcript[int(row["b_start"]) : int(row["b_end"])]
    switch = fields["switch"]
    fields.update(observables(folder, switch, trig_a, trig_b, int(fields["len_x"])))
    writer.writerow(fields)
    handle.flush()
    scored = oe.score_design(folder, switch, trig_a, trig_b, on_ceiling=None)
    entry = {
        "switch": switch,
        "a_start": row["a_start"],
        "a_end": row["a_end"],
        "b_start": row["b_start"],
        "b_end": row["b_end"],
        "len_x": fields["len_x"],
        "access_a": row.get("access_a"),
        "access_b": row.get("access_b"),
    }
    for field in ("open_00", "open_01", "open_10", "open_11", "andness", "barrier"):
        entry[field] = scored.get(field)
    obj_rows[switch] = entry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="drift_regen")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--min-identity",
        type=float,
        default=0.90,
        help="reject a rebuild that resembles the original less than this; a low match means the "
        "corrected triggers moved the front, which is a finding and not something to paper over",
    )
    args = parser.parse_args(argv)

    results = NB / "results"
    transcript = read_fasta(NB / "mCherry_original.txt")
    folder = FoldEngine(37.0)
    # ONE GATE PER GEOMETRY, and this is not a detail. `secondary_stems` slices trigger A at
    # `self.ARM_LEN` and derives `len_k2` from `self.SECONDARY_INVASION_LEN`, both ClassVars, so a
    # gate is tied to one geometry. Running the 165-nt designs through the 18-nt family slices one
    # base off and `fixed_alignment_energy` then refuses with "needs equal lengths, got 14 and 13"
    # -- which is what 50 of the 788 were failing on, and the other 451 inherited through an empty
    # memo for the same pair. The window lengths in the data are all self-consistent (161 nt pairs
    # A=36 with B=50, 165 nt pairs A=35 with B=49); it was the family that was wrong.
    gates = {
        161: ProkaryoticToeholdAndGate(
            Host.ECOLI, folder, CodonOptimizer(Host.ECOLI), TranslationScorer(Host.ECOLI)
        ),
        165: KimSecondaryArmToeholdAndGate(
            Host.ECOLI, folder, CodonOptimizer(Host.ECOLI), TranslationScorer(Host.ECOLI)
        ),
    }

    def gate_for(switch: str):
        family = gates.get(len(switch))
        if family is None:
            raise KeyError(f"no gate family for a {len(switch)} nt switch")
        return family

    rows = op.load(results)
    op.add_accessibility(rows, results)
    op.add_completions(rows, results)
    op.add_offtarget(rows, results)

    def fails_other(row: dict) -> bool:
        if row["open_11f"] is None or row["open_11f"] > op.ON_CEILING:
            return True
        if row["scheme"] in op.DEAD_SCHEMES:
            return True
        for key, floor, strict_lower in (
            ("aug_11", op.AUG_FLOOR, False),
            ("lock", op.LOCK_FLOOR, True),
            ("lock01", op.LOCK01_FLOOR, True),
            ("hairpin_worst", op.HAIRPIN_FLOOR, True),
            ("engaged_arm_11", op.ARM_FLOOR, True),
        ):
            value = row.get(key)
            if value is None:
                continue
            if (value < floor) if strict_lower else (value <= floor):
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

    axes_of = axis_columns(results)
    targets = []
    for row in rows:
        positions = op.covers_drift(row)
        if not positions or fails_other(row):
            continue
        a_start, a_end = int(row["a_start"]), int(row["a_end"])
        if not any(a_start <= p < a_end for p in positions):
            continue  # drift_repair handles these
        if row["switch"] in axes_of:
            targets.append(row)
    print(f"  {len(targets):,} drift-affected designs with trigger A involved and axis columns")

    if args.status:
        path = results / f"{args.out}_folded_0.csv"
        done = 0
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                done = sum(1 for r in csv.DictReader(handle) if r.get("A_M_11") not in (None, ""))
        print(f"  regenerated so far: {done:,}")
        print(f"  still to do:        {max(len(targets) - done, 0):,}")
        if done < len(targets):
            print("\n  continue with:")
            print(
                "    uv run python src/engine/gates/notebooks/toehold_and/"
                f"drift_regenerate.py --out {args.out}"
            )
        else:
            print("\n  complete. Rebuild the panel and these compete for slots.")
        return 0

    if args.limit:
        targets = targets[: args.limit]

    axis_lookup = {
        "closure": dict(CLOSURES),
        "upper3": dict(UPPER3),
        "lower3": dict(LOWER3),
        "island": dict(ISLAND),
    }
    fold_path = results / f"{args.out}_folded_0.csv"
    obj_path = results / f"obj_{args.out}.csv"
    done: set[str] = set()
    if fold_path.exists():
        with fold_path.open(encoding="utf-8") as handle:
            done = {r["switch_before"] for r in csv.DictReader(handle) if r.get("switch_before")}
        print(f"  resuming: {len(done):,} already regenerated")

    stem_cache: dict[tuple[str, str, int, int], list] = {}
    reasons: Counter = Counter()
    # STREAMED, not accumulated. The first version built the whole list in memory and wrote after
    # the loop; it then crashed in the write stage with 788 designs computed and lost every one of
    # them. Long runs here stream and resume, and this is why.
    produced: list[tuple[dict, dict]] = []
    fields = (*FOLD_FIELDS, *EXTRA)
    fold_mode = "a" if done else "w"
    obj_rows: dict[str, dict] = {}
    if obj_path.exists():
        with obj_path.open(encoding="utf-8") as handle:
            obj_rows = {r["switch"]: r for r in csv.DictReader(handle) if r.get("switch")}
    fold_handle = fold_path.open(fold_mode, encoding="utf-8", newline="")
    fold_writer = csv.DictWriter(fold_handle, fieldnames=list(fields), extrasaction="ignore")
    if fold_mode == "w":
        fold_writer.writeheader()
    for number, row in enumerate(targets):
        if row["switch"] in done:
            continue
        a_start, a_end = int(row["a_start"]), int(row["a_end"])
        b_start, b_end = int(row["b_start"]), int(row["b_end"])
        trig_a = transcript[a_start:a_end]
        trig_b = transcript[b_start:b_end]
        len_x = int(row["len_x"])
        # Keyed on the switch LENGTH too: the same trigger pair enumerates differently under the
        # two families, so a shared key would hand one geometry the other's front.
        try:
            gate = gate_for(row["switch"])
        except KeyError as error:
            reasons[str(error)] += 1
            continue
        key = (trig_a, trig_b, len_x, len(row["switch"]))
        if key not in stem_cache:
            try:
                stem_cache[key] = sorted(
                    (
                        s
                        for s in gate.secondary_stems(trig_a, trig_b, len_x)
                        if s.lock_energy <= 0.0
                    ),
                    key=lambda s: s.lock_energy,
                )
            except Exception as error:
                reasons[f"enumeration failed: {type(error).__name__}: {error}"] += 1
                stem_cache[key] = []
        front = stem_cache[key]
        if not front:
            reasons["no stem on the corrected front"] += 1
            continue
        axes = axes_of[row["switch"]]
        try:
            point = {name: axis_lookup[name][axes[name]] for name in axis_lookup}
        except KeyError as error:
            reasons[f"unknown axis level {error}"] += 1
            continue
        best = None
        for index, stem in enumerate(front):
            try:
                rebuilt = build(gate.assemble(trig_a, trig_b, len_x, stem), point)
            except Exception:
                continue
            score = identity(rebuilt.sequence, row["switch"])
            if best is None or score > best[0]:
                best = (score, index, rebuilt)
        if best is None:
            reasons["every rebuild raised"] += 1
            continue
        score, index, rebuilt = best
        if score < args.min_identity:
            reasons[f"identity below {args.min_identity:g}"] += 1
            continue
        # An identical rebuild is the strongest possible result, not a rejection. It says the
        # generator, run against the CORRECTED triggers, produces exactly the sequence already
        # stored -- so the corrected base never reached this design's build at this axis point and
        # the design was never wrong. Discarding those would throw away 153 designs for passing.
        #
        # They still need the flag, because `covers_drift` tests the windows and would go on
        # rejecting them; and they still get folded here, because their A_M columns were computed
        # before the correction and nothing has re-derived them since.
        unchanged = rebuilt.sequence == row["switch"]
        reasons["verified unchanged -- was never wrong" if unchanged else "regenerated"] += 1
        made = (
            row,
            {
                "switch": rebuilt.sequence,
                "switch_before": row["switch"],
                "identity": round(score, 4),
                "stem_index_before": axes["stem_index"],
                "stem_index_after": index,
                "front_size": len(front),
                "outcome": "unchanged" if unchanged else "regenerated",
                "len_x": len_x,
                "scheme": row.get("scheme"),
                "closure": axes["closure"],
                "upper3": axes["upper3"],
                "lower3": axes["lower3"],
                "drift_repaired": 1,
            },
        )
        produced.append(made)
        if not args.dry_run:
            write_one(fold_writer, fold_handle, obj_rows, made, transcript, folder)
        if number % 20 == 0:
            print(
                f"    {number + 1}/{len(targets)}  regenerated {reasons['regenerated']:,}",
                flush=True,
            )

    print("\n  outcome:")
    for why, count in reasons.most_common():
        print(f"    {count:6,d}  {why}")
    if args.dry_run:
        print("\n  --dry-run: nothing written.")
        return 0
    if not produced:
        print("\n  nothing to write.")
        return 0

    fold_handle.close()
    with obj_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OBJ_FIELDS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(obj_rows.values())
    print(f"\n  wrote {len(produced):,} designs to {fold_path.name}")
    print(f"  and {len(obj_rows):,} energy rows to {obj_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
