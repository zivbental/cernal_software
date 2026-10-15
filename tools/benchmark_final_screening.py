"""Measure synthetic JSON/policy overhead, never biological screening performance.

Run from the repository root with PYTHONPATH=src uv run python followed by this file.
No screening executable is started and no database is installed or read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine.common_mechanism import (
    DATABASES,
    JSON_VERSION,
    POLICY_VERSION,
    TOOL_VERSION,
    CommonMechanismAdapter,
    read_json,
)
from engine.safety import LocalScreeningManifest, SafetyGate, SequenceSubmission

LENGTHS = (41, 100, 1000, 10_000, 100_000)
BATCHES = (1, 8, 64)
STATUSES = {"Pass": "PASS", "Flag": "BLOCK", "Error": "HOLD_SYSTEM", "Unknown": "HOLD_SYSTEM"}
ROOT = Path(__file__).resolve().parents[1]


def new_adapter(now: datetime) -> CommonMechanismAdapter:
    """Parser-only object: deliberately nonexistent executable/database locations."""
    return CommonMechanismAdapter(
        manifest=LocalScreeningManifest(
            adapter_name="ibbis-common-mechanism",
            adapter_version=TOOL_VERSION,
            database_id="SYNTHETIC-NOT-A-VALIDATED-DATABASE",
            database_sha256="0" * 64,
            validated_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=1),
            policy_version=POLICY_VERSION,
            software_sha256="0" * 64,
        ),
        executable=Path("/nonexistent/synthetic-no-executable"),
        database=Path("/nonexistent/synthetic-no-database"),
        files={},
        revisions=dict.fromkeys(sorted(DATABASES), "1.0"),
        software_files={},
    )


def synthetic_case(length: int, batch: int, status: str):
    """Repetitive toy bytes, no biological source or functional design intent."""
    sequence = ("ACGT" * math.ceil(length / 4))[:length]
    submissions = tuple(
        SequenceSubmission(f"synthetic-{i}", sequence, "plasmid", "synthetic benchmark only")
        for i in range(batch)
    )
    data = {
        "commec_info": {"commec_version": TOOL_VERSION, "json_output_version": JSON_VERSION},
        "database_info": {"revisions": dict.fromkeys(sorted(DATABASES), "1.0")},
        "query_info": {"number_of_queries": batch, "total_query_length": length * batch},
        "queries": {
            f"q{i:06d}": {
                "query": f"q{i:06d}",
                "length": length,
                "hits": [],
                "status": {
                    "screen_status": status,
                    "biorisk": "Pass",
                    "protein_taxonomy": "Pass",
                    "nucleotide_taxonomy": "Pass",
                    "low_concern": "Pass",
                },
            }
            for i in range(batch)
        },
    }
    return submissions, data


def measure(path, submissions, status, mode, repeats, now):
    adapter = new_adapter(now)
    gate = SafetyGate()

    def operation():
        parser = new_adapter(now) if mode == "fresh_adapter" else adapter
        evidence = parser.parse_result(read_json(path), submissions)
        results = tuple(
            gate.evaluate(s, e, now=now) for s, e in zip(submissions, evidence, strict=True)
        )
        if len(results) != len(submissions) or any(
            result.decision.value != STATUSES[status] for result in results
        ):
            raise AssertionError("synthetic fixture no longer exercises its expected policy branch")
        return results

    # Both modes deliberately warm Python imports and file-system pages. Fresh does
    # not mean an OS/database cold cache; it adds only adapter construction.
    operation()
    samples = []
    start_load = time.perf_counter()
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - start)
    load_elapsed = time.perf_counter() - start_load
    # Measure allocation separately so tracing does not inflate timing samples.
    tracemalloc.start()
    operation()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "label": "synthetic software-path exercise; not biological ground truth",
        "length_bp": len(submissions[0].sequence),
        "batch_size": len(submissions),
        "total_bp": sum(len(s.sequence) for s in submissions),
        "synthetic_aggregate_status": status,
        "expected_policy_decision": STATUSES[status],
        "mode": mode,
        "json_bytes": path.stat().st_size,
        "repeats": repeats,
        "elapsed_seconds_samples": samples,
        "median_seconds": statistics.median(samples),
        "p95_seconds_nearest_rank": sorted(samples)[math.ceil(0.95 * repeats) - 1],
        "sustained_load_elapsed_seconds": load_elapsed,
        "sustained_batches_per_second": repeats / load_elapsed,
        "sustained_sequences_per_second": repeats * len(submissions) / load_elapsed,
        "sustained_bp_per_second": repeats
        * sum(len(s.sequence) for s in submissions)
        / load_elapsed,
        "separate_memory_pass_tracemalloc_current_bytes": current,
        "separate_memory_pass_tracemalloc_peak_bytes": peak,
        "process_lifetime_peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/ibbis-overhead.json"))
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("--repeats must be at least 2")
    now = datetime.now(UTC)
    records = []
    skipped = []
    with tempfile.TemporaryDirectory(prefix="synthetic-parser-benchmark-") as temporary:
        path = Path(temporary) / "synthetic.json"
        for length in LENGTHS:
            for batch in BATCHES:
                if length * batch > 1_000_000:
                    skipped.append(
                        {"length_bp": length, "batch_size": batch, "reason": "batch cap"}
                    )
                    continue
                for status in STATUSES:
                    submissions, data = synthetic_case(length, batch, status)
                    path.write_text(json.dumps(data), encoding="utf-8")
                    for mode in ("fresh_adapter", "reused_adapter"):
                        records.append(measure(path, submissions, status, mode, args.repeats, now))
    disk = shutil.disk_usage(ROOT)
    source_paths = (
        "tools/benchmark_final_screening.py",
        "src/engine/common_mechanism.py",
        "src/engine/safety.py",
    )
    report = {
        "schema": "cernal-synthetic-screening-overhead-v1",
        "created_at": now.isoformat(),
        "scope": "Actual JSON decoder, CommonMechanismAdapter.parse_result and SafetyGate.evaluate",
        "not_measured": [
            "real Common Mechanism runtime or database load",
            "executable startup or file inventory hashing",
            "biological sensitivity, specificity, or accuracy",
            "parallel load or contention",
            "OS cold-cache behavior",
        ],
        "coverage": "Four synthetic paths only; no branch coverage percentage claimed",
        "no_screening_result_cache": True,
        "fresh_mode_definition": "New adapter per call; imports/filesystem pages warm",
        "memory_definition": "Separate traced call; RSS is process-lifetime high-water mark",
        "input_definition": "ACGT toy strings; invented statuses; not screened sequences",
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "disk_total_bytes": disk.total,
            "disk_free_bytes": disk.free,
            "commec_on_path": shutil.which("commec"),
            "git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in source_paths
            },
        },
        "skipped_cases": skipped,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} synthetic overhead measurements to {args.output}")


if __name__ == "__main__":
    main()
