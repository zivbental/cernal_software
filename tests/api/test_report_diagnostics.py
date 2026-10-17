"""Final diagnostics must agree across the engine, polling API and stored report."""

from html import escape

import pytest

from apps.analyses.services import execute_run
from engine.client import LocalEngine
from engine.stages.reporting import ReportBuilder


@pytest.mark.parametrize("case", ["accepted", "validation_empty", "trigger_empty"])
def test_final_warning_parity(run, auth_client, media_root, monkeypatch, case):
    run.dataset = None
    run.input_mode = "direct"
    run.trigger_sequence = (
        "A" * 100 if case == "trigger_empty" else "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA"
    )
    if case == "validation_empty":
        run.params_snapshot["constraints"] = {"max_switch_length": 1}
    run.save()
    results = []
    original = LocalEngine.run

    def capture(self, request, on_progress):
        result = original(self, request, on_progress)
        results.append(result)
        return result

    monkeypatch.setattr(LocalEngine, "run", capture)
    execute_run(str(run.id))
    run.refresh_from_db()
    assert run.status == "COMPLETED"
    result = results[0]
    assert bool(result.candidates) == (case == "accepted")
    if case == "validation_empty":
        assert any("No candidate designs passed validation" in w for w in result.warnings)
    if case == "trigger_empty":
        assert result.warnings
        assert not any("No candidate designs passed validation" in w for w in result.warnings)

    report = run.artifacts.get(kind="report")
    response = auth_client.get(f"/api/artifacts/{report.id}/download")
    assert response.status_code == 200
    html = b"".join(response.streaming_content).decode()
    for endpoint in (f"/api/runs/{run.id}", f"/api/design/{run.id}"):
        response = auth_client.get(endpoint)
        assert response.status_code == 200
        assert response.json()["warnings"] == result.warnings == run.warnings
    for warning in result.warnings:
        assert f"<li>{escape(warning)}</li>" in html


def test_bacterial_report_uses_equilibrium_values_and_retains_failed_checks():
    html = "".join(
        ReportBuilder._and_gate_section(
            {
                "method": "prokaryotic_equilibrium",
                "on_pct": 40,
                "off_pct": None,
                "states": {
                    "11": {"open_probability": 0.4, "opening_energy_kcal_per_mol": 0.6},
                    "10": {"open_probability": None, "opening_energy_kcal_per_mol": None},
                },
                "feasibility": {"passed": 21, "total": 22, "violations": ["A-only <limit> failed"]},
            }
        )
    )
    assert "prokaryotic_equilibrium" in html
    assert "40.00%" in html and "unmeasured" in html
    assert "Feasibility: failed; 21/22" in html
    assert "A-only &lt;limit&gt; failed" in html
    assert "Sampler" not in html and "Draws" not in html and "Mismatched" not in html
    assert "tied with the best" not in html


def test_eukaryotic_report_keeps_its_sampler_and_control_evidence():
    html = "".join(
        ReportBuilder._and_gate_section(
            {
                "on_pct": 90,
                "off_pct": 5,
                "off_source": "+A",
                "states": {"+A": {"open_pct": 5, "draws": 200, "verified": False}},
                "controls": {"found": 2, "requested": 2},
            }
        )
    )
    assert "Sampler check" in html and "FAILED" in html
    assert "Mismatched-trigger controls: 2 of 2" in html
    assert "prokaryotic_equilibrium" not in html
