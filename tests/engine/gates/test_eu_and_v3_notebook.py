"""End-to-end run of ``eu_and_v3.ipynb`` on a small portable input (no browser, no local paths)."""

from __future__ import annotations

import hashlib
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
                    "AND_TOP_N": "5",
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
    single = next(output_dir.rglob("eu_and_v3_report_*.html")).read_text(encoding="utf-8")
    both = next(output_dir.rglob("eu_and_v3_and_report_*.html")).read_text(encoding="utf-8")
    return single, both


def test_saved_results_reject_mismatches_and_preserve_provenance(tmp_path):
    # Test the persistence boundary independently of expensive sampling/rendering.
    sys.path.insert(0, str(NOTEBOOK_DIR))
    try:
        from _report_stats import load_results, save_results
    finally:
        sys.path.pop(0)
    identity = {
        "csv_sha256": "input-a",
        "folding_model": {"salt": 0.1},
        "settings": {"seed": 7, "samples": 300},
        "part": "single",
    }
    original = {
        "code_revision": "original",
        "input_file": "original.csv",
        "folding_model": "original model",
    }
    payload = {"results": {"1": {"on": 12}}, "check": {}}
    path = tmp_path / "saved.json"
    save_results(path, identity, original, payload)
    assert load_results(path, identity) == (payload, original)
    for changed in (
        {**identity, "csv_sha256": "input-b"},
        {**identity, "folding_model": {"salt": 1.021}},
        {**identity, "settings": {"seed": 8, "samples": 300}},
        {**identity, "settings": {"seed": 7, "samples": 301}},
        {**identity, "part": "and"},
    ):
        with pytest.raises(ValueError, match="identity mismatch"):
            load_results(path, changed)
    saved = json.loads(path.read_text())
    saved["payload"]["results"]["1"]["on"] = 99
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="integrity"):
        load_results(path, identity)
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="lack validated provenance"):
        load_results(path, identity)


@pytest.mark.parametrize("controls", [2, 0])
def test_both_reports_render_with_and_without_control_triggers(tmp_path, controls):
    namespace = _run_notebook(tmp_path, {"N_CONTROLS": str(controls)})
    single, both = _reports(tmp_path)
    assert "@@" not in single and "@@" not in both  # every template field was filled
    for report in (single, both):  # provenance: code revision, input checksum, folding model
        assert "code_revision" in report and "folding_model" in report and "ViennaRNA" in report
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() in report
    # the sampler check lives in Appendix A only: listed there, no colour anywhere
    assert (
        "Appendix A&ensp;Sampler check" in single and "States not verified (design rank" in single
    )
    assert "Appendix A&ensp;Expected number of open nucleotides and sampler check" in both
    for report in (single, both):
        text = re.sub(
            r"base64,[A-Za-z0-9+/=]+", "", report
        )  # random image bytes can contain any letters
        assert "badk" not in text and "okk" not in text and "shaded" not in text
        assert "states not verified" not in report.split("Appendix A")[0].lower()
    assert "one mismatched trigger per design" not in single
    assert "one pair of mismatched triggers" not in both
    assert namespace["scored"] and namespace["scored_and"]
    if controls == 0:
        # no control exists: the statistics are unavailable, not 0, and no row claims a control
        assert all(r["n_controls"] == 0 and r["ctrl_pct"] is None for r in namespace["scored"])
        assert all(r["n_controls"] == 0 and r["ctrl_pct"] is None for r in namespace["scored_and"])
        assert "median Control" in single and "n/a" in single and "n/a" in both
    else:
        assert any(r["n_controls"] > 0 for r in namespace["scored"])
    # the AND ranking is the joint ON_min - OFF: its best candidate is in the tied group, and the
    # sum-based difference is only indicative
    ranked = [r for r in namespace["scored_and"] if r["diff_min_pp"] is not None]
    best = max(ranked, key=lambda r: r["diff_min_pp"])
    assert best["tied"]
    assert all(r["diff_min_pp"] <= best["diff_min_pp"] for r in ranked if r["tied"])
    assert (
        "ONmin_pct"
        in next(tmp_path.rglob("eu_and_v3_and_all_candidates_*.csv")).read_text().splitlines()[0]
    )
    # no listed construct has an AUG before the second hairpin's stem_down
    for candidate in namespace["candidates"].values():
        assert not namespace["upstream_augs"](candidate["built"]), candidate["spacer_label"]
    csvs = list(tmp_path.rglob("eu_and_v3_*all*.csv"))
    assert len(csvs) == 2
    assert all("n_controls" in path.read_text(encoding="utf-8").splitlines()[0] for path in csvs)


def test_every_pair_filtered_out_reports_no_eligible_candidates(tmp_path):
    """All candidates excluded is a valid outcome: a clean report, no ranking, no crash."""
    namespace = _run_notebook(tmp_path, {"FAKE_MAX_SEQ_OVERLAP_NT": "-1", "N_CONTROLS": "2"})
    _, both = _reports(tmp_path)
    assert namespace["scored_and"] == []
    assert "No eligible AND candidates" in both
    assert "@@" not in both
    assert namespace["rank_agreement"] is None
    assert namespace["noise_p95_and"] is None
    assert not list(tmp_path.rglob("eu_and_v3_and_trigger_positions_*.png"))
    csv_path = next(tmp_path.rglob("eu_and_v3_and_all_candidates_*.csv"))
    assert len(csv_path.read_text(encoding="utf-8").splitlines()) == 1  # the header only
    assert json.loads(next(tmp_path.rglob("eu_and_v3_and_artifact_*/rows.json")).read_text()) == []


def test_a_single_candidate_has_no_rank_correlation(tmp_path):
    namespace = _run_notebook(tmp_path, {"AND_MAX_CANDIDATES": "1", "N_CONTROLS": "2"})
    _, both = _reports(tmp_path)
    assert len(namespace["scored_and"]) == 1
    assert namespace["rank_agreement"] is None  # a correlation needs two candidates
    assert namespace["scored_and"][0]["tied"]
    assert "@@" not in both
    assert "NaN" not in re.sub(r"base64,[A-Za-z0-9+/=]+", "", both)  # no NaN printed as a value
    assert "Spearman rank correlation n/a" in both
    assert list(tmp_path.rglob("eu_and_v3_and_trigger_positions_*.png"))
    replay = _run_notebook(
        tmp_path / "replay",
        {
            "AND_MAX_CANDIDATES": "1",
            "N_CONTROLS": "2",
            "RESULTS_TO_LOAD": repr(str(namespace["_results_path"])),
            "RESULTS_TO_LOAD_AND": repr(str(namespace["_results_path_and"])),
        },
    )
    assert replay["RUN_INFO"] == namespace["RUN_INFO"]
    assert replay["AND_RUN_INFO"] == namespace["AND_RUN_INFO"]
    assert [d["control_ranks"] for d in replay["designs"]] == [
        d["control_ranks"] for d in namespace["designs"]
    ]
    assert replay["AND_IDENTITY"] == namespace["AND_IDENTITY"]
    changed = json.loads(json.dumps(replay["AND_IDENTITY"]))
    changed["and_jobs"][0]["fused"] += "A"
    with pytest.raises(ValueError, match="identity mismatch"):
        replay["load_results"](namespace["_results_path_and"], changed)
