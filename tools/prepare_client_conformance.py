"""Create a productive client fixture in an explicitly isolated QA database/media."""

import argparse
import json
import os
import tempfile
from pathlib import Path

import django


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-output", required=True, type=Path)
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL") or not os.environ.get("MEDIA_ROOT"):
        parser.error("Set explicit DATABASE_URL and MEDIA_ROOT for isolated QA storage.")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()
    from django.contrib.auth import get_user_model

    from apps.accounts.services import issue_api_key
    from apps.analyses.models import AnalysisRun
    from apps.results.services import import_job_result
    from engine.client import LocalEngine, validate_job_configuration
    from engine.contract import INPUT_DIRECT, SCHEMA_VERSION, SUCCEEDED, JobRequest

    fixture = json.loads(
        (Path(__file__).resolve().parents[1] / "clients/fixtures/design_request.json").read_text()
    )
    params = {
        name: fixture.get(name, {})
        for name in ("constraints", "scoring", "budget", "payload", "backbone")
    }
    params.update(top_n=fixture.get("top_n", 25), notes=fixture.get("notes", ""))
    params = validate_job_configuration(
        params,
        fixture["gate_families"],
        "default",
        INPUT_DIRECT,
        fixture["trigger_sequence"],
        fixture["organism"],
    )
    params = json.loads(json.dumps(params))
    user = get_user_model().objects.create_user(username="isolated-client-fixture", is_active=True)
    _, secret = issue_api_key(owner=user, label="isolated-client-fixture")
    run = AnalysisRun.objects.create(
        created_by=user,
        organism=fixture["organism"],
        input_mode=INPUT_DIRECT,
        trigger_sequence=fixture["trigger_sequence"],
        params_snapshot=params,
        seed=fixture["seed"],
        gate_families=fixture["gate_families"],
        scoring_profile="default",
        idempotency_key=fixture["idempotency_key"],
        status="QUEUED",
    )
    with tempfile.TemporaryDirectory() as output_dir:
        request = JobRequest(
            schema_version=SCHEMA_VERSION,
            run_id=str(run.id),
            idempotency_key=run.idempotency_key,
            input_mode=INPUT_DIRECT,
            trigger_sequence=run.trigger_sequence,
            input_path="",
            input_checksum="",
            organism=run.organism,
            params=params,
            seed=run.seed,
            gate_families=run.gate_families,
            scoring_profile=run.scoring_profile,
            output_dir=output_dir,
        )
        result = LocalEngine().run(request, lambda pct, stage: True)
        if result.status != SUCCEEDED or not result.accepted:
            raise RuntimeError(
                f"Conformance fixture is not productive: {result.error}; {result.warnings}"
            )
        import_job_result(run, result, output_dir)
    run.status = "COMPLETED"
    run.engine_version = result.engine_version
    run.progress_pct = 100
    run.save()
    args.key_output.write_text(secret)
    args.key_output.chmod(0o600)


if __name__ == "__main__":
    main()
