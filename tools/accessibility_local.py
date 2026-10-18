"""Trigger-window accessibility by TRUE local folding -- RNAplfold, via the engine's own profiler.

    uv run python tools/accessibility_local.py --from-ref origin/main
    uv run python tools/accessibility_local.py

**Why a third accessibility column.** Two exist and they barely agree. ``l_green`` folds the binding
window as an isolated slice; ``l_full_w25`` folds the whole 711-nt transcript once and averages over
the window plus 25 nt of flank. Over 832 windows they agree at **rho +0.345**, the lowest pair in
the table -- so the choice between them is not cosmetic, and neither is the established method.

``FoldProfiler`` is. It wraps ``RNAplfold``, which computes unpaired probability in a *sliding local
window* and caps base-pair span, and that is the right physics for a long mRNA: a 711-nt transcript
does not reach global equilibrium in a cell, it folds co-transcriptionally from the 5' end and local
structure persists. RNAplfold exists because of exactly that, and it is the standard tool for
target-site accessibility. ``l_full_w25`` assumes equilibrium over the whole molecule and then
averages in 50 nt the trigger never touches.

**And one correction this file exists to record.** ``l_full_w25`` was introduced here as "VISTA's
form". It is not. VISTA folds a **slice** of site +- L globally; ``l_full_w25`` folds the **whole
transcript** and averages over site +- 25 -- two differences at once, what is folded and what is
averaged. The +0.317 that justified it belongs to VISTA's measure, so ``l_full_w25`` has no external
validation at all.

**Why this lives in ``tools/`` and not in the notebook.** ``FoldProfiler`` is a **stage-2** tool,
and ``tests/engine/test_house_rules.py`` forbids any file under ``gates/`` from even referencing it.
The rule is right and its message is the argument: by the time a gate family sees a trigger, its
accessibility has already been measured and stored, and re-measuring inside the family "produces a
second number for the same physical quantity ... and only one of the two reaches the report, with
nothing indicating which". The notebook's exemption covers the shared-tool rule, not this one.

So the split is: this generator runs outside the engine and writes
``results/accessibility_local.csv``; ``objective_panel`` joins that file like any other side table,
reading a CSV and never touching the profiler. The architecture's own position is that wiring
RNAplfold into trigger selection belongs in ``stages/triggers.py`` (``TriggerScorer.score``, still a
stub) -- this is the measurement, not that wiring.

**No second copy of the tool.** ``FoldProfiler`` is imported, never reimplemented, and
``--from-ref`` loads it from a git ref without checking anything out -- ``git show <ref>:<path>``
into a temporary file, then ``importlib``. That matters because the branch and ``main`` hold
different versions: the branch's uses W=80/L=40/u=10 and returns a mean of marginals, while main's
uses W=200/L=150/u=20 and adds ``joint_probability``. Measured on the same 832 windows they agree at
rho +0.733 -- close, not identical -- so which one produced a column has to be recorded, and the
output carries it.

``joint_probability`` is deliberately not used. Over a 35 to 50 nt trigger window it is **0.000000**
with a maximum of 6.9e-05 -- the same vanishing that makes any joint probability over 18 nt
meaningless -- and main's u=20 default refuses a window that long outright, which is a correct guard
rather than a limitation to work around.
"""

import argparse
import csv
import importlib.util
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NB = REPO / "src" / "engine" / "gates" / "notebooks" / "toehold_and"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(NB))

#: Where ``FoldProfiler`` lives, for ``--from-ref``.
PROFILER_PATH = "src/engine/stages/folding.py"


def load_profiler(ref: str):
    """``FoldProfiler`` from a git ref, or from the working tree when ``ref`` is empty.

    ``git show`` writes the file's content without touching the index, the working tree or HEAD, so
    this reads another branch's version with no merge and nothing to undo. The module is loaded
    standalone, which works because ``stages/folding.py`` imports only ``functools.cache`` and
    ``RNA`` -- it has no engine dependencies to resolve.
    """
    if not ref:
        from engine.stages.folding import FoldProfiler

        return FoldProfiler, "working tree"
    blob = subprocess.run(
        ["git", "show", f"{ref}:{PROFILER_PATH}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    handle = tempfile.NamedTemporaryFile("w", suffix="_folding.py", delete=False, encoding="utf-8")
    with handle:
        handle.write(blob)
    spec = importlib.util.spec_from_file_location("folding_from_ref", handle.name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FoldProfiler, ref


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from-ref",
        default="",
        help="load FoldProfiler from this git ref instead of the working tree, e.g. origin/main. "
        "Nothing is checked out and no file in the repo changes",
    )
    parser.add_argument("--fasta", default="mCherry_original.txt")
    parser.add_argument("--out", default="accessibility_local")
    parser.add_argument(
        "--source",
        default="accessibility_s1",
        help="the table whose (start, role) keys to score, so the join key matches",
    )
    args = parser.parse_args(argv)

    from full_sweep import read_fasta

    results = NB / "results"
    source = results / f"{args.source}.csv"
    if not source.exists():
        print(f"  no {source.name} -- run accessibility_s1.py first")
        return 1

    try:
        profiler_class, origin = load_profiler(args.from_ref)
    except subprocess.CalledProcessError as error:
        print(f"  git show {args.from_ref}:{PROFILER_PATH} failed: {error.stderr.strip()}")
        return 1
    profiler = profiler_class()
    window = getattr(profiler, "window", None)
    span = getattr(profiler, "max_span", None)
    unpaired = getattr(profiler, "unpaired", None)
    print(f"  FoldProfiler from {origin}: W={window} L={span} u={unpaired}")
    if hasattr(profiler, "available") and not profiler.available:
        print("  ViennaRNA is unavailable to this profiler; nothing can be measured")
        return 1

    transcript = read_fasta(NB / args.fasta)
    print(f"  transcript {len(transcript):,} nt\n")

    # The same (start, role) keys the other accessibility tables use, so `add_accessibility` joins
    # all three on one key and a reader can compare them row by row.
    keys: dict[tuple[int, str], tuple[int, int]] = {}
    with source.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            start, end, role = row.get("start"), row.get("end"), (row.get("role") or "").strip()
            if not start or not end or role not in ("A", "B"):
                continue
            keys[(int(start), role)] = (int(start), int(end))
    print(f"  {len(keys):,} (start, role) keys to score")

    rows = []
    for (start, role), (lo, hi) in sorted(keys.items()):
        rows.append(
            {
                "start": start,
                "end": hi,
                "role": role,
                "l_local": round(profiler.openness(transcript, lo, hi), 6),
                "profiler": origin,
                "window": window,
                "max_span": span,
            }
        )
    values = [r["l_local"] for r in rows]
    print(
        f"\n  l_local: min {min(values):.4f}  median {st.median(values):.4f}"
        f"  mean {st.fmean(values):.4f}  sd {st.stdev(values):.4f}  max {max(values):.4f}"
    )

    path = results / f"{args.out}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["start", "end", "role", "l_local", "profiler", "window", "max_span"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n  wrote {len(rows):,} rows to {path.name}")
    print("  the `profiler` column records which FoldProfiler produced them -- the branch's and")
    print("  main's agree at rho +0.733, so the provenance is part of the measurement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
