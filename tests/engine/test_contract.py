"""The contract types themselves.

Immutability is the point: a JobRequest is a frozen snapshot of one submission, and a
JobResult is a manifest of what actually happened. Neither may be edited in flight.
"""

import dataclasses

import pytest

from engine.contract import (
    CANCELLED,
    FAILED,
    SCHEMA_VERSION,
    SUCCEEDED,
    ArtifactRef,
    CandidateResult,
    JobResult,
    MetricValue,
)
from engine.errors import EngineError, UnsupportedGateFamilyError
from engine.gates.registry import available_families, get_family


def _candidate(ref: str, rank: int | None, score: float | None, rejected: bool = False):
    return CandidateResult(
        ref=ref,
        rank=rank,
        overall_score=score,
        gate_family="toehold",
        logic_type="AND",
        triggers={},
        design={},
        summary="",
        is_rejected=rejected,
        rejection_reason="filtered" if rejected else "",
    )


def test_job_request_is_immutable(make_request):
    request = make_request()
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.organism = "S. cerevisiae"


def test_contract_types_are_frozen():
    for cls, kwargs in [
        (
            MetricValue,
            {
                "name": "m",
                "raw_value": 1.0,
                "normalized_value": 1.0,
                "weight": 1.0,
                "direction": "HIGHER_BETTER",
            },
        ),
        (
            ArtifactRef,
            {"kind": "k", "path": "p", "media_type": "text/plain", "checksum_sha256": "x"},
        ),
    ]:
        instance = cls(**kwargs)
        with pytest.raises(dataclasses.FrozenInstanceError):
            instance.kind = "mutated" if cls is ArtifactRef else None


def test_accepted_returns_rank_order():
    result = JobResult(
        schema_version=SCHEMA_VERSION,
        engine_version="test",
        status=SUCCEEDED,
        candidates=[
            _candidate("c", 2, 0.5),
            _candidate("a", 1, 0.9),
            _candidate("z", None, None, True),
        ],
    )
    assert [c.ref for c in result.accepted] == ["a", "c"]
    assert [c.ref for c in result.rejected] == ["z"]


def test_status_constants_are_distinct():
    assert len({SUCCEEDED, FAILED, CANCELLED}) == 3


def test_gate_registry_exposes_toehold():
    assert "toehold" in available_families()
    assert get_family("toehold").name == "toehold"


def test_unknown_gate_family_names_the_available_ones():
    with pytest.raises(UnsupportedGateFamilyError, match="Available families"):
        get_family("crispr-not-yet")


def test_every_engine_error_shares_one_base():
    """The Platform catches EngineError and nothing narrower (§6.2)."""
    assert issubclass(UnsupportedGateFamilyError, EngineError)


def test_capabilities_advertise_the_scoring_vocabulary():
    """docs/public-api.md §7: the API validates a custom scoring block against this,
    without importing engine.scoring (§3's boundary rule)."""
    from engine.client import LocalEngine

    capabilities = LocalEngine().capabilities()
    names = {metric.name for metric in capabilities.metrics}

    assert names == {
        "state_separation",
        "trigger_accessibility",
        "gate_folding_energy",
        "predicted_leakage",
        "orthogonality",
        "gc_content",
        "dynamic_range",
        "predicted_success_rate",
        "circuit_complexity",
    }
    assert all(metric.unit for metric in capabilities.metrics)
    assert {hf["metric"] for hf in capabilities.hard_filters} == {
        "predicted_leakage",
        "state_separation",
    }


@pytest.mark.parametrize("params", [{}, {"folding": {}}])
def test_job_configuration_snapshots_all_folding_defaults(params):
    from engine.client import validate_job_configuration

    normalized = validate_job_configuration(params, ["toehold"], "default", "direct", "ACGU")
    assert normalized["folding"] == {
        "temperature_celsius": 37.0,
        "dangles": 2,
        "special_hairpins": True,
        "no_lonely_pairs": False,
        "no_gu": False,
        "no_gu_closure": False,
        "energy_parameters": "turner2004",
    }
    assert params in ({}, {"folding": {}})


@pytest.mark.parametrize("temperature", [0, 25.5, 100])
@pytest.mark.parametrize("energy_parameters", ["turner2004", "turner1999", "andronescu2007"])
def test_job_configuration_preserves_custom_folding_settings(temperature, energy_parameters):
    from engine.client import validate_job_configuration

    folding = {
        "temperature_celsius": temperature,
        "dangles": 0,
        "special_hairpins": False,
        "no_lonely_pairs": True,
        "no_gu": True,
        "no_gu_closure": True,
        "energy_parameters": energy_parameters,
    }
    params = {"folding": folding}
    normalized = validate_job_configuration(params, ["toehold"], "default", "direct", "ACGU")
    assert normalized["folding"] == folding
    normalized["folding"]["dangles"] = 2
    assert params["folding"]["dangles"] == 0


@pytest.mark.parametrize(
    "folding",
    [
        None,
        False,
        "",
        [],
        {"temperature": 25},
        {"temperature_celsius": -0.1},
        {"temperature_celsius": 100.1},
        {"temperature_celsius": float("nan")},
        {"temperature_celsius": float("inf")},
        {"temperature_celsius": "25"},
        {"temperature_celsius": True},
        {"dangles": 1},
        {"dangles": 3},
        {"dangles": -1},
        {"dangles": 2.0},
        {"dangles": "2"},
        {"dangles": False},
        {"special_hairpins": "false"},
        {"no_lonely_pairs": 1},
        {"no_gu": 0},
        {"no_gu_closure": None},
        {"energy_parameters": "unknown"},
        {"energy_parameters": "/tmp/parameters.par"},
        {"energy_parameters": ["turner2004"]},
    ],
)
def test_job_configuration_rejects_invalid_folding_settings(folding):
    from engine.client import validate_job_configuration

    with pytest.raises(ValueError):
        validate_job_configuration({"folding": folding}, ["toehold"], "default", "direct", "ACGU")
