"""End-to-end run of ``eu_and_v3.ipynb`` on a small portable input (no browser, no local paths)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parents[3]
NOTEBOOK_DIR = REPO / "src/engine/gates/notebooks/toehold_and"
FIXTURE = REPO / "tests/fixtures/eu_and_v3_small.csv"


def _run_notebook(output_dir: Path, overrides: dict[str, str]) -> dict:
    """Execute every code cell in one namespace, with the parameter cell overridden."""
    notebook = json.loads((NOTEBOOK_DIR / "eu_and_v3.ipynb").read_text(encoding="utf-8"))
    namespace: dict = {"__name__": "__main__"}
    previous_cwd, previous_path = Path.cwd(), list(sys.path)
    os.chdir(NOTEBOOK_DIR)
    try:
        import matplotlib

        matplotlib.use("Agg")
        for cell in notebook["cells"]:
            if cell["cell_type"] != "code":
                continue
            code = "".join(cell["source"])
            if code.lstrip().startswith("# ---- data source"):
                values = {
                    "CSV_PATH": repr(str(FIXTURE)),
                    "OUTPUT_DIR": repr(str(output_dir)),
                    "MAKE_PDF": "False",
                    "N_DESIGNS": "8",
                    "AND_TOP_N": "3",
                    "N_SAMPLES": "300",
                    "MAX_WORKERS": "2",
                    "ARTIFACT_DETAIL_N": "4",
                    **overrides,
                }
                code = re.sub(  # a multi-line assignment in the notebook
                    r"(?s)CSV_PATH = \(.*?\n\)\n", f"CSV_PATH = {values.pop('CSV_PATH')}\n", code
                )
                for name, value in values.items():
                    code, hits = re.subn(rf"(?m)^{name} = .*$", f"{name} = {value}", code, count=1)
                    assert hits, f"parameter {name} not found in the notebook"
            exec(compile(code, "eu_and_v3.ipynb", "exec"), namespace)
    finally:
        os.chdir(previous_cwd)
        sys.path[:] = previous_path
    return namespace


def _reports(output_dir: Path) -> tuple[str, str]:
    single = next(output_dir.glob("eu_and_v3_report_*.html")).read_text(encoding="utf-8")
    both = next(output_dir.glob("eu_and_v3_and_report_*.html")).read_text(encoding="utf-8")
    return single, both


@pytest.mark.parametrize("controls", [2, 0])
def test_both_reports_render_with_and_without_control_triggers(tmp_path, controls):
    namespace = _run_notebook(tmp_path, {"N_CONTROLS": str(controls)})
    single, both = _reports(tmp_path)
    assert "@@" not in single and "@@" not in both  # every template field was filled
    assert namespace["scored"] and namespace["scored_and"]
    if controls == 0:
        # no control exists: the statistics are unavailable, not 0, and no row claims a control
        assert all(r["n_controls"] == 0 and r["ctrl_pct"] is None for r in namespace["scored"])
        assert all(r["n_controls"] == 0 and r["ctrl_pct"] is None for r in namespace["scored_and"])
        assert "median control" in single and "n/a" in single and "n/a" in both
    else:
        assert any(r["n_controls"] > 0 for r in namespace["scored"])
    csvs = list(tmp_path.glob("eu_and_v3_*all*.csv"))
    assert len(csvs) == 2
    assert all("n_controls" in path.read_text(encoding="utf-8").splitlines()[0] for path in csvs)
