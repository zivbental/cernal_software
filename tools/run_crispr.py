#!/usr/bin/env python3
"""Run from repo root: uv run python tools/run_crispr.py INPUT.json --output var/crispr."""

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.artifacts import write_artifact
from engine.pipeline import run_crispr_workbench


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("var/crispr"))
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        config = json.loads(raw)
        result = run_crispr_workbench(
            config,
            lambda done, total, pair: print(f"Pair {done + 1}/{total}: {pair}", file=sys.stderr),
        )
        result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        write_artifact(
            str(args.output),
            "result.json",
            json.dumps(result, indent=2, allow_nan=False),
            kind="crispr_research_result",
            media_type="application/json",
        )
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=["rank", "pair_id", "j_best", "phi", "guide"])
        writer.writeheader()
        for row in result["top_candidates"]:
            writer.writerow({k: row[k] for k in writer.fieldnames})
        write_artifact(
            str(args.output),
            "ranked.csv",
            stream.getvalue(),
            kind="crispr_research_ranking",
            media_type="text/csv",
        )
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"Input/run error: {exc}\n")
    print(json.dumps({"status": result["status"], **result["summary"]}, indent=2))
    print(f"Results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
