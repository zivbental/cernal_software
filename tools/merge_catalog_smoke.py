"""Merge independently saved catalog smoke shards, preserving per-record provenance."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reports = [json.loads(path.read_text()) for path in args.reports]
    merged = dict(reports[0])
    records = {}
    commits = set()
    for report in reports:
        for invariant in ("schema", "params", "seed", "catalog_manifest_sha256"):
            if report[invariant] != merged[invariant]:
                parser.error(f"Reports disagree on {invariant}.")
        commits.add(report["engine_commit"])
        for source in report["comparisons"]:
            key = source["catalog_key"]
            if key in records:
                parser.error(f"Duplicate comparison: {key}.")
            records[key] = {
                **source,
                "engine_commit": report["engine_commit"],
                "engine_version": report["engine_version"],
                "recorded_at": report["recorded_at"],
            }
    merged["engine_commit"] = None  # See exact per-comparison engine_commit.
    merged["engine_commits"] = sorted(commits)
    merged["expected_comparisons"] = 15
    merged["complete"] = len(records) == 15
    merged["comparisons"] = [records[key] for key in sorted(records)]
    merged["outcome_counts"] = {
        outcome: sum(record["outcome"] == outcome for record in records.values())
        for outcome in ("productive", "valid_empty", "engine_error")
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    print(f"{len(records)}/15 comparisons; complete={merged['complete']}")
    print(merged["outcome_counts"])


if __name__ == "__main__":
    main()
