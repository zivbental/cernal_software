"""Split a sweep output that holds rows from two different column sets under one header.

    uv run python tools/split_mixed_schema.py --out axes_c8

**What happened, and it was avoidable.** `characterise_axes.py` appends to
`results/<out>_<shard>.csv` and writes the header only when the file does not yet exist, which is
what makes `--resume` work. `FIELDS` grew three times during one day -- 47 columns to 162 -- while
a resumable run existed on disk. Every row written after each change carried the new, wider schema
and was appended under the ORIGINAL 47-column header. Nothing was corrupted at the byte level and
no row was lost, but the file cannot be read as one table: a reader using the stored header maps
the first 47 values of a 162-field row onto the wrong names, which is why `skipped` came back
holding `True` and `False` -- position 23 of the new order is `lower3_forced`, a boolean.

Measured on the run: 431,916 rows, of which **346,528 carry 47 fields** and **85,388 carry 162**.
Both sets are intact and separable by row width alone, so this recovers two clean tables rather
than discarding either.

The guard that stops it happening again is in `characterise_axes.py`: it now compares the stored
header against its own `FIELDS` before appending and refuses rather than writing a row the header
cannot describe.

Written out as `<out>_v1_<shard>.csv` (47 columns) and `<out>_v2_<shard>.csv` (162 columns), with
the right header on each. Rows of any other width are reported and kept in `<out>_odd_<shard>.csv`
rather than dropped -- an unexpected width is a finding, not a nuisance.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "src" / "engine" / "gates" / "notebooks" / "toehold_and" / "results"


#: The 47-column set the run started with, in order. Reconstructed from the files' own stored
#: header rather than from git history, so it is what the rows actually are.
def stored_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def current_fields() -> tuple[str, ...]:
    """`FIELDS` as `characterise_axes.py` defines it now, imported rather than copied."""
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "src" / "engine" / "gates" / "notebooks" / "toehold_and"))
    spec = importlib.util.spec_from_file_location("_ca", ROOT / "tools" / "characterise_axes.py")
    module = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, ["split_mixed_schema"]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved
    return module.FIELDS


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="axes_c8")
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument(
        "--apply", action="store_true", help="write the split files; without it, only report"
    )
    args = parser.parse_args(argv)

    wide = current_fields()
    print(f"\n  current FIELDS: {len(wide)} columns")

    grand: Counter = Counter()
    for index in range(args.shards):
        source = RESULTS / f"{args.out}_{index}.csv"
        if not source.exists():
            continue
        header = stored_header(source)
        widths: Counter = Counter()
        with source.open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            next(reader)
            for row in reader:
                widths[len(row)] += 1
        grand.update(widths)
        print(
            f"  {source.name}: header {len(header)} columns, rows "
            + ", ".join(f"{w}x{c:,}" for w, c in sorted(widths.items()))
        )
        if not args.apply:
            continue

        narrow_path = RESULTS / f"{args.out}_v1_{index}.csv"
        wide_path = RESULTS / f"{args.out}_v2_{index}.csv"
        odd_path = RESULTS / f"{args.out}_odd_{index}.csv"
        with (
            source.open(encoding="utf-8", newline="") as handle,
            narrow_path.open("w", encoding="utf-8", newline="") as nh,
            wide_path.open("w", encoding="utf-8", newline="") as wh,
            odd_path.open("w", encoding="utf-8", newline="") as oh,
        ):
            reader = csv.reader(handle)
            next(reader)
            nw, ww, ow = csv.writer(nh), csv.writer(wh), csv.writer(oh)
            nw.writerow(header)
            ww.writerow(wide)
            ow.writerow(["n_fields", *(f"c{i}" for i in range(max(len(wide), len(header))))])
            counts = Counter()
            for row in reader:
                if len(row) == len(header):
                    nw.writerow(row)
                    counts["v1"] += 1
                elif len(row) == len(wide):
                    ww.writerow(row)
                    counts["v2"] += 1
                else:
                    ow.writerow([len(row), *row])
                    counts["odd"] += 1
        print(f"    -> v1 {counts['v1']:,}  v2 {counts['v2']:,}  odd {counts['odd']:,}")
        if not counts["odd"]:
            odd_path.unlink()

    print("\n  all shards: " + ", ".join(f"{w} fields x {c:,}" for w, c in sorted(grand.items())))
    if not args.apply:
        print("  report only. Pass --apply to write the split files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
