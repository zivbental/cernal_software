"""Explicit, local-only full-database acceptance run; never installs a deployment.

Requires the already validated laptop tool/database inventories. Uses the real
catalog, native folding and original configured final-output/export path. Output
includes private generated sequences and must not be committed wholesale.
"""

import argparse
import dataclasses
import hashlib
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine import common_mechanism as cm
from engine.client import LocalEngine, validate_job_configuration
from engine.contract import INPUT_DE, SCHEMA_VERSION, JobRequest
from engine.safety import stored_release_allowed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.installation.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    source = repo / "src/apps/expression/catalog/ecoli/138294__67644164.csv"
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == "452d25b413d6c3f3a6eec321da41adfe166578c95fc17492c2bc1fe5012f1cf0"
    (output / "source.csv").write_bytes(raw)
    files = json.loads((root / "database-inventory.json").read_text())["files"]
    software = {
        str(root / "env" / name): value
        for name, value in json.loads((root / "env-inventory.json").read_text())["files"].items()
    }
    now = datetime.now(UTC)
    config = {
        "manifest": {
            "adapter_name": "ibbis-common-mechanism",
            "adapter_version": cm.TOOL_VERSION,
            "database_id": "BENCHMARK-ONLY-CLEARED-V2-NOT-PRODUCTION",
            "database_sha256": cm.inventory_digest(files),
            "software_sha256": cm.inventory_digest(software),
            "policy_version": cm.POLICY_VERSION,
            "validated_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
        },
        "executable": str(root / "env/bin/commec"),
        "database": str(root / "database"),
        "files": files,
        "software_files": software,
        "revisions": {
            "biorisk": "1.2",
            "control_lists": "1.1",
            "best_match": "1.0",
            "low_concern": "1.1",
        },
        "timeout_seconds": 900,
        "threads": 2,
    }
    manifest = output / "benchmark-manifest.json"
    manifest.write_text(json.dumps(config))
    os.environ["CERNAL_COMMEC_MANIFEST"] = str(manifest)  # only this explicit benchmark child
    params = validate_job_configuration(
        {
            "constraints": {"max_genes": 3, "standard": "none"},
            "budget": {"max_designs": 1},
            "payload": {"outputs": ["mcherry"]},
            "backbone": {},
            "statistics": {"hypothesis_universe_complete": False},
        },
        ["toehold"],
        "default",
        INPUT_DE,
        "",
        "ecoli",
    )
    request = JobRequest(
        schema_version=SCHEMA_VERSION,
        run_id="ibbis-cleared-v2",
        idempotency_key="ibbis-cleared-v2",
        input_mode=INPUT_DE,
        input_path=str(output / "source.csv"),
        input_checksum=digest,
        trigger_sequence="",
        organism="ecoli",
        params=params,
        gate_families=["toehold"],
        scoring_profile="default",
        seed=42,
        output_dir=str(output / "artifacts"),
    )
    (output / "request.json").write_text(json.dumps(dataclasses.asdict(request), indent=2))
    phases = []
    original_verify = cm.CommonMechanismAdapter._verify_installation
    original_batch = cm.CommonMechanismAdapter._screen_one_batch

    def timed(method, label):
        def observe(self, *arguments):
            start = time.perf_counter()
            try:
                return method(self, *arguments)
            finally:
                phases.append({"phase": label, "seconds": time.perf_counter() - start})
                print(json.dumps(phases[-1]), flush=True)

        return observe

    cm.CommonMechanismAdapter._verify_installation = timed(original_verify, "integrity")
    cm.CommonMechanismAdapter._screen_one_batch = timed(original_batch, "screen_batch")
    start = time.perf_counter()
    try:
        result = LocalEngine().run(request, lambda pct, stage: True)
    finally:
        cm.CommonMechanismAdapter._verify_installation = original_verify
        cm.CommonMechanismAdapter._screen_one_batch = original_batch
    elapsed = time.perf_counter() - start
    (output / "private-result.json").write_text(json.dumps(dataclasses.asdict(result), indent=2))
    audit_paths = sorted((output / "artifacts/safety").glob("*.json"))
    audits = [json.loads(path.read_text()) for path in audit_paths]
    summary = {
        "started_at": now.isoformat(),
        "wall_seconds": elapsed,
        "status": result.status,
        "error": result.error,
        "accepted": len(result.accepted),
        "phases": phases,
        "dataset_sha256": digest,
        "manifest": config["manifest"],
        "audit_files": [str(path.relative_to(output)) for path in audit_paths],
        "audits": audits,
        "source_sha256": {
            name: hashlib.sha256((repo / name).read_bytes()).hexdigest()
            for name in (
                "src/engine/common_mechanism.py",
                "src/engine/safety.py",
                "src/engine/pipeline.py",
            )
        },
        "candidate_release_checks": [
            stored_release_allowed(c.design, now=datetime.now(UTC)) for c in result.accepted
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(
        json.dumps(
            {
                key: summary[key]
                for key in ("wall_seconds", "status", "accepted", "candidate_release_checks")
            }
        ),
        flush=True,
    )
    assert result.status == "succeeded" and len(audits) == 2
    assert all(audit["decision"] == "PASS" and audit["release_allowed"] for audit in audits)
    assert all(summary["candidate_release_checks"])


if __name__ == "__main__":
    main()
