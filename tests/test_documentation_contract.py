"""Entry-point claims must agree with the shipped engine and metric contract."""

import ast
import tomllib
from pathlib import Path

from engine.client import LocalEngine

ROOT = Path(__file__).resolve().parents[1]


def test_readme_documents_the_configured_engine_and_installed_folding_backend():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    settings = ast.parse((ROOT / "src/config/settings/base.py").read_text(encoding="utf-8"))
    engine_assignment = next(
        node
        for node in settings.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CERNAL_ENGINE" for target in node.targets
        )
    )
    configured_default = next(
        keyword.value.value
        for keyword in engine_assignment.value.keywords
        if keyword.arg == "default"
    )
    assert f"The default is `CERNAL_ENGINE={configured_default}`" in readme
    assert "deterministic fake output" not in readme
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert any(dependency.startswith("viennarna") for dependency in project["dependencies"])
    assert "active\nfolding backend" in readme
    # The standard build and data bootstrap are merged setup requirements.
    assert "npm ci && npm run build)" in readme
    assert "npm ci && npm run build:fast" not in readme
    assert "uv run --locked python tools/install_data.py" in readme
    assert "merge it before F5" not in readme
    assert "separately proposed" not in readme
    assert "uv sync --locked --extra dev" in readme


def test_published_metric_help_distinguishes_single_input_and_bacterial_and_windows():
    capabilities = LocalEngine().capabilities()
    metrics = {metric.name: metric for metric in capabilities.metrics}
    leakage = metrics["predicted_leakage"].description
    assert "AUG-only (three bases)" in leakage
    assert "Single-input toehold" in leakage
    assert "Bacterial AND" in leakage and "30-nt window" in leakage
    assert "joint opening probability" in leakage
    assert "0.001" in metrics["dynamic_range"].description
    assert "Not a success probability" in metrics["predicted_success_rate"].description


def test_documented_application_scope_matches_capabilities():
    capabilities = LocalEngine().capabilities()
    assert capabilities.input_modes == ["direct", "de", "gene"]
    assert set(capabilities.supported_hosts) == {"ecoli", "yeast", "human", "c_acnes"}
    assert capabilities.limits["max_circuit_gates"] == 1
    assert capabilities.limits["max_triggers"] == 1  # the single-input default
    # Each documented two-input chemistry has its own host and measurement contract.
    assert [name for name in capabilities.family_hosts if "and" in name] == [
        "eukaryotic_toehold_and",
        "prokaryotic_toehold_and",
    ]
    assert capabilities.family_inputs["eukaryotic_toehold_and"] == 2
    assert capabilities.family_inputs["prokaryotic_toehold_and"] == 2
    assert capabilities.family_hosts["prokaryotic_toehold_and"] == ["ecoli"]
    assert capabilities.limits["max_gate_inputs"] == 2
