#!/usr/bin/env python3
"""Run from repo root: uv run python tools/run_crispr.py INPUT.json --output var/crispr."""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.artifacts import sha256_bytes, write_artifact
from engine.pipeline import run_crispr_workbench
from engine.safety import fail_closed_release


def prepare_research_export(result: dict) -> dict:
    """Project non-sequence diagnostics and screen each exported complete guide.

    Raw inputs, sequence fragments and arbitrary extra fields are never copied.
    Only a complete guide explicitly approved by the shared release boundary may
    leave the process. Ranking/feasibility and release authorization are separate.
    This projection does not mutate the scientific result used within the engine.
    """
    exported = {
        key: result[key]
        for key in (
            "status",
            "measurement_complete",
            "model",
            "gate_version",
            "limitations",
            "objective_parameters",
            "lambda_calculation",
            "versions",
            "summary",
            "guide_rejection_counts",
            "measurement_failure_counts",
            "input_sha256",
        )
        if key in result
    }
    exported["input"] = {"omitted_from_export": True, "reason": "raw input contains sequences"}
    screens = {}
    host = result["input"].get("host", "human")

    def project_row(row):
        projected = {
            key: row[key]
            for key in (
                "pair_id",
                "design_id",
                "rank",
                "j_best",
                "phi",
                "observables",
                "feasible",
                "selectable",
                "rejections",
                "evaluation_status",
                "measurement_error",
                "measurement_errors",
                "measurement_failures",
                "evaluated_guides",
                "inner_feasible_guides",
                "j",
                "j_accessibility",
                "j_energy",
                "q_spacer",
                "q_trigger",
                "q_pair",
                "j_positive",
            )
            if key in row
        }
        # Preserve coordinates and structural geometry, not fragments that could
        # reconstruct an unapproved guide or disclose its input sequences.
        for name, fields in (
            ("spacer", ("id", "start", "end", "strand")),
            ("trigger", ("id", "transcript_id", "start", "length")),
            (
                "architecture",
                (
                    "blocker_candidate_index",
                    "blocker_candidate_count",
                    "blocker_variable_positions",
                    "blocker_search",
                    "regions",
                    "intended_trigger_regions",
                    "order_5_to_3",
                    "gate_version",
                    "model",
                ),
            ),
        ):
            if name in row:
                projected[name] = {key: row[name][key] for key in fields if key in row[name]}
        guide = row.get("guide")
        projected["guide"] = None
        if guide is not None:
            if not isinstance(guide, str) or not guide:
                raise ValueError("Export requires a nonempty guide string or null")
            if guide not in screens:
                digest = sha256_bytes(guide.encode("ascii"))
                screens[guide] = fail_closed_release(
                    f"crispr:guide:{digest}", guide, host_context=host
                )
            screening = screens[guide]
            projected["sequence_release"] = screening.audit_manifest()
            if screening.release_allowed is True:
                projected["guide"] = guide
        return projected

    for key in ("top_candidates", "pairs", "guide_audit"):
        exported[key] = [project_row(row) for row in result[key]]
    approved = sum(screen.release_allowed is True for screen in screens.values())
    exported["sequence_export"] = {
        "policy": "project-fail-closed-release-v1",
        "screened_unique_guides": len(screens),
        "approved_unique_guides": approved,
        "held_unique_guides": len(screens) - approved,
        "sequence_fragments_omitted": True,
    }
    return exported


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
        result["input_sha256"] = sha256_bytes(raw)
        result = prepare_research_export(result)
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
    print(
        json.dumps(
            {
                "status": result["status"],
                **result["summary"],
                "sequence_export": result["sequence_export"],
            },
            indent=2,
        )
    )
    print(f"Results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
