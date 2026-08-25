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


def test_mock_options_defaults_to_empty(make_request):
    assert make_request(params={}).mock_options() == {}
    assert make_request(params={"mock": "not-a-dict"}).mock_options() == {}
    assert make_request(params={"mock": {"fail": True}}).mock_options() == {"fail": True}


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
