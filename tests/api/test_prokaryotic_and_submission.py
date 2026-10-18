"""The bacterial AND configuration crosses both API paths without eukaryotic semantics."""

import csv
import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from apps.analyses.models import AnalysisRun, RunStatus
from apps.results.services import AND_CSV_COLUMNS, _and_csv_cells

TABLE = "gene_id,log2fc,padj\nb3447,3.4,0.0001\nb3846,2.6,0.0004\n"
FAMILY = "prokaryotic_toehold_and"


def test_and_search_budget_uses_deployed_limits_without_changing_other_families(settings):
    from apps.analyses.services import queued_and_budget

    settings.Q_CLUSTER = {"timeout": 120}
    settings.RUN_EXECUTION_TIMEOUT = 150
    assert queued_and_budget({}, [FAMILY])["budget"] == {
        "max_runtime_seconds": 108,
        "on_exceed": "return_partial",
    }
    assert (
        queued_and_budget({"budget": {"max_runtime_seconds": 20}}, [FAMILY])["budget"][
            "max_runtime_seconds"
        ]
        == 20
    )
    with pytest.raises(ValueError, match="at most 108 seconds"):
        queued_and_budget({"budget": {"max_runtime_seconds": 121}}, [FAMILY])
    assert queued_and_budget({}, ["eukaryotic_toehold_and"]) == {}


@pytest.mark.parametrize("endpoint", ["runs", "design"])
def test_misspelled_bacterial_setting_is_rejected_by_name(
    auth_client, csv_upload, media_root, endpoint
):
    settings = {"max_pairz": 2}
    if endpoint == "runs":
        upload = auth_client.post("/api/datasets", data={"file": csv_upload(TABLE)})
        assert upload.status_code == 201
        body = {
            "dataset_id": upload.json()["id"],
            "organism": "ecoli",
            "gate_families": [FAMILY],
            "params": {
                "constraints": {"max_triggers": 2},
                "and_inputs": {"gene_a": "b3447", "gene_b": "b3846"},
                "prokaryotic_and": settings,
            },
        }
    else:
        body = {
            "dge_csv": TABLE,
            "organism": "ecoli",
            "gate_families": [FAMILY],
            "constraints": {"max_triggers": 2},
            "and_inputs": {"gene_a": "b3447", "gene_b": "b3846"},
            "prokaryotic_and": settings,
        }
    response = auth_client.post(
        f"/api/{endpoint}", data=json.dumps(body), content_type="application/json"
    )
    assert response.status_code == 422, response.content
    assert "max_pairz" in response.content.decode()
    assert AnalysisRun.objects.count() == 0


def test_bacterial_dry_run_echoes_effective_search_without_creating_a_run(auth_client):
    response = auth_client.post(
        "/api/design?dry_run=true",
        data=json.dumps(
            {
                "dge_csv": TABLE,
                "organism": "ecoli",
                "gate_families": [FAMILY],
                "constraints": {"max_triggers": 2},
                "and_inputs": {"gene_a": "b3447", "gene_b": "b3846"},
                "prokaryotic_and": {
                    "max_pairs": 2,
                    "pair_selection": "percentile_sample",
                },
                "seed": 11,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    resolved = response.json()["resolved"]
    assert resolved["and_inputs"] == {"gene_a": "b3447", "gene_b": "b3846"}
    assert resolved["prokaryotic_and"]["max_pairs"] == 2
    assert resolved["prokaryotic_and"]["pair_selection"] == "percentile_sample"
    assert "full_context_finalists" not in resolved["prokaryotic_and"]
    assert resolved["budget"]["max_runtime_seconds"] > 0
    assert resolved["budget"]["on_exceed"] == "return_partial"
    assert "n_samples" not in resolved["prokaryotic_and"]
    assert AnalysisRun.objects.count() == 0


def test_equilibrium_export_preserves_missing_states_without_claiming_sampler_checks():
    candidate = SimpleNamespace(
        design={
            "and_gate": {
                "method": "prokaryotic_equilibrium",
                "full_context_status": "screen_failed",
                "on_pct": 40.0,
                "off_pct": None,
                "worst_off_state": None,
                "payload_head_nt": 9,
                "evaluated_nt": 170,
                "states": {
                    "00": {"open_probability": None, "opening_energy_kcal_per_mol": None},
                    "11": {"open_probability": 0.4, "opening_energy_kcal_per_mol": 0.6},
                },
                "feasibility": {"passed": 21, "total": 22, "violations": ["ON screen failed"]},
            }
        }
    )
    exported = dict(zip(AND_CSV_COLUMNS, _and_csv_cells(candidate), strict=True))
    assert exported["and_method"] == "prokaryotic_equilibrium"
    assert exported["and_full_context_status"] == "screen_failed"
    assert exported["and_p_open_11"] == 0.4
    assert exported["and_p_open_00"] == ""
    assert exported["and_off_pct"] == ""
    assert exported["and_payload_head_nt"] == 9
    assert exported["and_evaluated_nt"] == 170
    assert exported["and_equilibrium_feasible"] == "no"
    assert exported["and_feasibility_violations"] == "ON screen failed"
    assert exported["and_sampler_checks_failed"] == ""
    assert exported["and_controls_found"] == ""


def test_eukaryotic_export_retains_sampler_fields_without_equilibrium_claims():
    candidate = SimpleNamespace(
        design={
            "and_gate": {
                "on_pct": 90.0,
                "off_pct": 5.0,
                "off_source": "+A",
                "states": {"+A": {"open_pct": 5.0, "verified": False}},
                "controls": {"found": 2},
            }
        }
    )
    exported = dict(zip(AND_CSV_COLUMNS, _and_csv_cells(candidate), strict=True))
    assert exported["and_method"] == "eukaryotic_stem_sampling"
    assert exported["and_sampler_checks_failed"] == 1
    assert exported["and_controls_found"] == 2
    assert exported["and_equilibrium_feasible"] == ""
    assert exported["and_p_open_11"] == ""


def test_bacterial_task_persists_the_actual_bounded_search_and_exports(
    auth_client, csv_upload, media_root, django_capture_on_commit_callbacks
):
    """A small real fold verifies the complete platform path, without promising a survivor."""
    from apps.analyses.tasks import run_analysis

    upload = auth_client.post("/api/datasets", data={"file": csv_upload(TABLE)})
    assert upload.status_code == 201
    with django_capture_on_commit_callbacks():
        submission = auth_client.post(
            "/api/runs",
            data=json.dumps(
                {
                    "input_mode": "de",
                    "dataset_id": upload.json()["id"],
                    "organism": "ecoli",
                    "gate_families": [FAMILY],
                    "seed": 11,
                    "params": {
                        "constraints": {"max_triggers": 2, "max_circuit_gates": 1},
                        "and_inputs": {"gene_a": "b3447", "gene_b": "b3846"},
                        "prokaryotic_and": {
                            "max_pairs": 1,
                            "stems_per_pair": 1,
                            "max_stem_assignments": 243,
                            "max_attempts": 20,
                        },
                        "budget": {"max_designs": 1},
                        "payload": {"outputs": ["other"], "custom_sequence": "ATGGCTGCTTAA"},
                    },
                }
            ),
            content_type="application/json",
        )
    assert submission.status_code == 202, submission.content
    run_id = submission.json()["id"]
    run_analysis(run_id)

    status = auth_client.get(f"/api/runs/{run_id}").json()
    assert status["status"] == RunStatus.COMPLETED, status
    run = AnalysisRun.objects.get(pk=run_id)
    assert run.params_snapshot["and_inputs"] == {"gene_a": "b3447", "gene_b": "b3846"}
    assert run.params_snapshot["prokaryotic_and"]["max_pairs"] == 1
    assert run.params_snapshot["prokaryotic_and"]["max_attempts"] == 20
    assert run.params_snapshot["budget"]["max_designs"] == 1

    # Inspect the stored manifest directly: its HTTP disclosure remains subject to release checks.
    manifest_artifact = run.artifacts.get(kind="run_manifest")
    with manifest_artifact.file.open("rb") as stream:
        manifest_bytes = stream.read()
    assert hashlib.sha256(manifest_bytes).hexdigest() == manifest_artifact.checksum_sha256
    manifest = json.loads(manifest_bytes)
    assert manifest["input_checksum"] == run.dataset.checksum_sha256
    assert manifest["seed"] == 11
    evidence = manifest["scientific_provenance"]["and_gate"]
    assert evidence["method"] == "prokaryotic_equilibrium"
    assert evidence["barrier_computed"] is False
    assert evidence["settings"] == run.params_snapshot["prokaryotic_and"]
    assert evidence["search"]["evaluated_gate_designs"] <= 1
    assert evidence["search"]["attempted_designs"] <= 20
    assert evidence["folding_context"] == "switch_through_linker_excluding_output"
    assert (
        evidence["search"]["runtime_limit_seconds"]
        == run.params_snapshot["budget"]["max_runtime_seconds"]
    )

    search_artifact = run.artifacts.get(kind="search_provenance")
    with search_artifact.file.open("rb") as stream:
        search_bytes = stream.read()
    assert hashlib.sha256(search_bytes).hexdigest() == search_artifact.checksum_sha256
    assert json.loads(search_bytes)["summary"] == evidence
    assert not run.artifacts.filter(kind__in=["sequence_fasta", "genbank"]).exists()

    report = run.artifacts.get(kind="report")
    report_download = auth_client.get(f"/api/artifacts/{report.id}/download")
    assert report_download.status_code == 200
    report_html = b"".join(report_download.streaming_content).decode()
    assert "Sampler check" not in report_html and "Mismatched-trigger controls" not in report_html

    listing = auth_client.get(f"/api/runs/{run_id}/candidates?include_rejected=true").json()
    assert listing["count"] == evidence["search"]["evaluated_gate_designs"]
    export = auth_client.get(f"/api/runs/{run_id}/export.csv")
    assert export.status_code == 200
    csv_rows = list(csv.DictReader(io.StringIO(export.content.decode())))
    assert len(csv_rows) == listing["count"]
    if not listing["items"]:
        assert evidence["search"]["accepted_candidates"] == 0
        assert any("No switch passed" in warning for warning in status["warnings"])
    else:
        assert "declared initiation window" in report_html
        assert "prokaryotic_equilibrium" in report_html
    for saved in listing["items"]:
        assert saved["gate_family"] == FAMILY
        if saved["is_rejected"]:
            assert saved["rank"] is None and saved["rejection_reason"]
        detail = auth_client.get(f"/api/candidates/{saved['id']}").json()
        assert detail == auth_client.get(f"/api/candidates/{saved['id']}").json()
        info = detail["design"]["and_gate"]
        assert info["method"] == "prokaryotic_equilibrium"
        assert info["barrier_computed"] is False
        assert info["evaluation_context"] == "switch_through_linker_excluding_output"
        assert info["payload_head_nt"] == 0
        assert info["evaluated_nt"] >= 161
        if saved["rank"] is not None:
            assert info["feasibility"]["passed"] == info["feasibility"]["total"]
        assert set(info["states"]) == {"00", "10", "01", "11"}
        assert detail["design"]["switch_sequence"] == ""
        assert detail["design"]["sequence_release"]["release_allowed"] is False
        row = next(row for row in csv_rows if row["candidate"] == saved["engine_ref"])
        assert row["and_method"] == info["method"]
        assert row["and_full_context_status"] == ""
        assert row["and_evaluation_context"] == info["evaluation_context"]
        assert int(row["and_evaluated_nt"]) == info["evaluated_nt"]
        assert row["and_sampler_checks_failed"] == ""
        assert row["and_controls_found"] == ""
        for state, value in info["states"].items():
            actual = row[f"and_p_open_{state}"]
            if value["open_probability"] is None:
                assert actual == ""
            else:
                assert float(actual) == pytest.approx(value["open_probability"])
