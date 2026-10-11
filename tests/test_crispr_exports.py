"""Research CLI sequence-release boundary, including nested diagnostic exports."""

import copy
import csv
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from tools import run_crispr

from engine.domain import CrisprObservables
from engine.gates.crispr import CrisprGate
from engine.pipeline import run_crispr_workbench
from engine.safety import Decision, fail_closed_release

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def research_result(monkeypatch):
    config = json.loads((ROOT / "examples/crispr/demo.json").read_text())
    monkeypatch.setattr(
        CrisprGate,
        "measurement_stages",
        lambda *args: iter([asdict(CrisprObservables(0.01, 0.8, 0.01, 0.01, -10))]),
    )
    return run_crispr_workbench(config)


def test_real_release_boundary_holds_all_nested_guides_without_changing_science(research_result):
    before = copy.deepcopy(research_result)
    exported = run_crispr.prepare_research_export(research_result)
    assert research_result == before
    assert exported["status"] == "ranked"
    assert exported["summary"] == before["summary"]
    assert exported["objective_parameters"] == before["objective_parameters"]
    serialized = json.dumps(exported)
    assert before["input"]["target_dna"] not in serialized
    assert before["input"]["scaffold"] not in serialized
    assert before["input"]["transcripts"]["toy"] not in serialized
    for group in ("top_candidates", "pairs", "guide_audit"):
        for source, row in zip(before[group], exported[group], strict=True):
            assert source["guide"] not in serialized
            assert row["guide"] is None
            assert row["sequence_release"]["decision"] == "HOLD_SYSTEM"
            assert row["sequence_release"]["release_allowed"] is False
            assert row["observables"] == source["observables"]
            assert "blocker" not in row["architecture"]
            assert "sequence" not in row.get("spacer", {})
            assert "pam" not in row.get("spacer", {})
            assert "sequence" not in row.get("trigger", {})
    assert exported["sequence_export"]["approved_unique_guides"] == 0


def test_approval_is_per_sequence_and_reused_for_repeated_rows(research_result, monkeypatch):
    approved = research_result["top_candidates"][0]["guide"]
    calls = []

    def screen(identifier, guide, *, host_context):
        calls.append((guide, host_context))
        result = fail_closed_release(identifier, guide, host_context=host_context)
        # Only this controlled fixture represents a provisioned approving adapter.
        return (
            replace(result, decision=Decision.PASS, release_allowed=True)
            if guide == approved
            else result
        )

    monkeypatch.setattr(run_crispr, "fail_closed_release", screen)
    result = run_crispr.prepare_research_export(research_result)
    unique = {row["guide"] for group in ("pairs", "guide_audit") for row in research_result[group]}
    assert len(calls) == len(unique)
    assert {host for _, host in calls} == {"human"}
    assert result["sequence_export"]["approved_unique_guides"] == 1
    for group in ("top_candidates", "pairs", "guide_audit"):
        for source, row in zip(research_result[group], result[group], strict=True):
            assert row["guide"] == (approved if source["guide"] == approved else None)


def test_empty_search_and_unknown_input_fields_do_not_release_sequences(research_result):
    secret = "GGGCUAACGUACGGUACGUA"
    research_result["input"]["extra"] = {"unrecognized_sequence": secret}
    research_result["new_output_field"] = secret
    for group in ("top_candidates", "pairs", "guide_audit"):
        research_result[group] = []
    result = run_crispr.prepare_research_export(research_result)
    assert secret not in json.dumps(result)
    assert result["sequence_export"]["screened_unique_guides"] == 0


def test_cli_overwrites_prior_sequence_exports_and_keeps_ranking(
    research_result, tmp_path, monkeypatch
):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(research_result["input"]))
    output = tmp_path / "export"
    output.mkdir()
    for name in ("result.json", "ranked.csv"):
        (output / name).write_text(research_result["top_candidates"][0]["guide"])
    monkeypatch.setattr(run_crispr, "run_crispr_workbench", lambda *args: research_result)
    monkeypatch.setattr("sys.argv", ["run_crispr", str(source), "--output", str(output)])
    run_crispr.main()
    result = json.loads((output / "result.json").read_text())
    with (output / "ranked.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(research_result["top_candidates"])
    assert all(row["guide"] == "" for row in rows)
    assert [float(row["phi"]) for row in rows] == [row["phi"] for row in result["top_candidates"]]
    assert result["input_sha256"] == run_crispr.sha256_bytes(source.read_bytes())
    for name in ("result.json", "ranked.csv"):
        assert research_result["top_candidates"][0]["guide"] not in (output / name).read_text()


def test_screening_failure_never_writes_unscreened_artifacts(
    research_result, tmp_path, monkeypatch
):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(research_result["input"]))
    output = tmp_path / "export"
    monkeypatch.setattr(run_crispr, "run_crispr_workbench", lambda *args: research_result)
    monkeypatch.setattr("sys.argv", ["run_crispr", str(source), "--output", str(output)])

    def failed(*args, **kwargs):
        raise RuntimeError("screening unavailable")

    monkeypatch.setattr(run_crispr, "fail_closed_release", failed)
    with pytest.raises(RuntimeError, match="screening unavailable"):
        run_crispr.main()
    assert not output.exists()
