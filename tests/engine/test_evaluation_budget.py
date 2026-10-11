"""Evaluation budgets stop generation; presentation limits never prune engine results."""

import csv
from types import SimpleNamespace

import pytest

from engine import pipeline
from engine.contract import INPUT_DIRECT, CandidateResult
from engine.domain import Constraints, GateDesign, GateKind, Host, TriggerCandidate, TriggerSet


@pytest.fixture
def cheap_pipeline(monkeypatch, make_request):
    """Fake expensive measurements, preserving real scoring, filtering and ranking."""
    trigger = TriggerCandidate("trig-1", "gene-1", "gene", "ACGU" * 8, 0, 0.8, 0.8, -1.0, 50.0)
    evaluated = []
    raw_values = []

    def evaluate(design):
        evaluated.append(design.design_id)
        return raw_values[int(design.design_id)]

    family = SimpleNamespace(kind=GateKind.TOEHOLD, evaluate_design=evaluate)
    monkeypatch.setattr(
        pipeline,
        "build_tools",
        lambda *_: {
            "constraints": Constraints(),
            "families": [family],
            "warnings": [],
            "profiler": None,
            "folder": SimpleNamespace(versions=lambda: {}),
            "screener": None,
            "translation": None,
            "plasmid_builder": None,
        },
    )
    monkeypatch.setattr(pipeline, "_direct_trigger", lambda *_: ([trigger], []))

    def designs(*args, **kwargs):
        for index in range(len(raw_values)):
            yield GateDesign(
                str(index), GateKind.TOEHOLD, Host.ECOLI, TriggerSet((trigger,)), "ACGU"
            )

    monkeypatch.setattr(pipeline.SwitchDesigner, "design", designs)
    monkeypatch.setattr(
        pipeline,
        "_build_plasmid",
        lambda *_: SimpleNamespace(plasmid=SimpleNamespace(segments=[], sequence="ACGU")),
    )

    def candidate(store, design, family, trigger, metrics, breach, plasmid, outcome):
        return CandidateResult(
            ref=store.mint_id("cand"),
            rank=None,
            overall_score=None,
            gate_family="toehold",
            logic_type="single-input",
            triggers={},
            design={
                "switch_sequence": "ACGU",
                "design_index": int(design.design_id),
                "output": outcome.value,
            },
            summary="Budget test",
            metrics=metrics,
            is_rejected=breach is not None,
            rejection_reason="hard filter" if breach else "",
        )

    monkeypatch.setattr(pipeline, "_candidate_result", candidate)
    # Leave the real CSV/safety-audit writer in place; omit expensive visual reporting.
    from engine.stages.reporting import ReportBuilder

    monkeypatch.setattr(ReportBuilder, "build_result", lambda *args, **kwargs: None)

    def run(raws, *, budget=None, outputs=None, top_n=None):
        raw_values[:] = raws
        evaluated.clear()
        params = {"budget": {} if budget is None else {"max_designs": budget}}
        if outputs is not None:
            params["payload"] = {"outputs": outputs, "custom_sequence": "ATGGCTGCTTAA"}
        if top_n is not None:
            params["top_n"] = top_n
        request = make_request(
            input_mode=INPUT_DIRECT, trigger_sequence="ACGU" * 8, organism="ecoli", params=params
        )
        result = pipeline.run_pipeline(request, lambda *_: True)
        with open(f"{request.output_dir}/candidates.csv", newline="") as file:
            rows = list(csv.DictReader(file))
        return result, list(evaluated), rows

    return run


def test_later_best_candidate_is_evaluated_with_expanded_budget(cheap_pipeline):
    raws = [{"state_separation": 1.0, "predicted_leakage": 0.2}] * 24
    raws.append({"state_separation": 9.0, "predicted_leakage": 0.1})
    result, evaluated, rows = cheap_pipeline(raws, budget=25, top_n=1)
    assert len(evaluated) == len(result.candidates) == len(rows) == 25
    assert [candidate.design["design_index"] for candidate in result.candidates] == list(range(25))
    assert result.candidates[-1].rank == 1
    assert result.scientific_provenance["design_budget"]["evaluated_gate_designs"] == 25


def test_default_budget_keeps_first_twenty_without_result_pruning(cheap_pipeline):
    raws = [{"state_separation": 1.0, "predicted_leakage": 0.2}] * 25
    result, evaluated, rows = cheap_pipeline(raws)
    assert len(evaluated) == len(result.candidates) == len(rows) == 20
    assert [candidate.rank for candidate in result.candidates] == list(range(1, 21))
    assert result.scientific_provenance["design_budget"]["truncated"] is True


def test_outputs_count_individually_and_rejections_remain_in_csv(cheap_pipeline):
    raws = [{"state_separation": 0.1}, {"state_separation": 1.0}, {"state_separation": 9.0}]
    result, evaluated, rows = cheap_pipeline(raws, budget=3, outputs=["gfp", "other"], top_n=1)
    assert evaluated == ["0", "0", "1", "1", "2", "2"]
    assert len(result.candidates) == len(rows) == 6
    assert [c.design["output"] for c in result.candidates] == ["gfp", "other"] * 3
    assert [c.rank for c in result.candidates] == [None, None, 3, 4, 1, 2]
    assert [row["rejected"] for row in rows] == ["yes", "yes", "no", "no", "no", "no"]
    assert result.scientific_provenance["design_budget"]["evaluated_gate_designs"] == 3


def test_equal_scores_have_repeatable_ranks(cheap_pipeline):
    raws = [{"state_separation": 2.0, "predicted_leakage": 0.2}] * 4
    first, _, _ = cheap_pipeline(raws, budget=4)
    second, _, _ = cheap_pipeline(raws, budget=4, top_n=1)
    assert first.candidates == second.candidates
    assert [c.rank for c in first.candidates] == [1, 2, 3, 4]


@pytest.mark.parametrize("value", [0, -1, 1001, True, False, 1.5, "2", None])
def test_stored_top_n_configuration_requires_bounded_integer(value):
    from engine.client import validate_job_configuration

    with pytest.raises(ValueError, match="top_n"):
        validate_job_configuration(
            {"top_n": value},
            ["toehold"],
            "default",
            INPUT_DIRECT,
            trigger_sequence="ACGU" * 8,
            organism="ecoli",
        )


@pytest.mark.parametrize("value", [1, 25, 1000])
def test_stored_top_n_configuration_retains_budget_independently(value):
    from engine.client import validate_job_configuration

    params = validate_job_configuration(
        {"top_n": value, "budget": {"max_designs": 40}},
        ["toehold"],
        "default",
        INPUT_DIRECT,
        trigger_sequence="ACGU" * 8,
        organism="ecoli",
    )
    assert params["top_n"] == value
    assert params["budget"]["max_designs"] == 40
