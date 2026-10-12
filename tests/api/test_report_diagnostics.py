"""Final diagnostics must agree across the engine, polling API and stored report."""

from html import escape

import pytest

from apps.analyses.services import execute_run
from engine.client import LocalEngine


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
