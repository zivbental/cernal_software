"""MockEngine behaviour.

MockEngine is what lets the whole product be built and demoed before any scientific
code exists, so its guarantees — determinism, cancellation, failure — are load-bearing
and tested as such.
"""

from pathlib import Path

import pytest

from engine.artifacts import sha256_file
from engine.client import EngineClient, LocalEngine, MockEngine, load_engine
from engine.contract import CANCELLED, FAILED, SUCCEEDED


@pytest.fixture
def engine():
    return MockEngine()


# --- Success path -----------------------------------------------------------------


def test_successful_run_returns_a_populated_result(engine, make_request, progress):
    result = engine.run(make_request(), progress)

    assert result.status == SUCCEEDED
    assert result.error is None
    assert result.engine_version == MockEngine.ENGINE_VERSION
    assert result.candidates
    assert result.artifacts


def test_result_echoes_back_what_was_submitted(engine, make_request, progress):
    """The Platform verifies the engine computed against what it actually sent (§10)."""
    request = make_request(params={"max_triggers": 2, "note": "hello"})
    result = engine.run(request, progress)

    assert result.input_checksum == request.input_checksum
    assert result.params == request.params


def test_mock_results_are_labelled_as_not_real_science(engine, make_request, progress):
    result = engine.run(make_request(), progress)
    assert any("MockEngine" in warning for warning in result.warnings)


def test_progress_is_reported_monotonically(engine, make_request, progress):
    engine.run(make_request(), progress)

    percentages = [percent for percent, _stage in progress.calls]
    assert percentages == sorted(percentages)
    assert percentages[0] <= 10
    assert percentages[-1] >= 90
    assert all(stage for _percent, stage in progress.calls), "every stage needs a label"


# --- Determinism ------------------------------------------------------------------


def test_same_idempotency_key_gives_identical_candidates(engine, make_request, progress):
    """The core guarantee: a retried submission must not produce different science."""
    first = engine.run(make_request(idempotency_key="key-repeat"), progress)
    second = engine.run(make_request(idempotency_key="key-repeat"), progress)

    assert first.candidates == second.candidates


def test_same_idempotency_key_gives_byte_identical_artifacts(engine, make_request, progress):
    first = engine.run(make_request(idempotency_key="key-bytes"), progress)
    second = engine.run(make_request(idempotency_key="key-bytes"), progress)

    assert [a.checksum_sha256 for a in first.artifacts] == [
        a.checksum_sha256 for a in second.artifacts
    ]


def test_different_idempotency_keys_give_different_candidates(engine, make_request, progress):
    first = engine.run(make_request(idempotency_key="key-a"), progress)
    second = engine.run(make_request(idempotency_key="key-b"), progress)

    assert first.candidates != second.candidates


def test_seed_participates_in_determinism(engine, make_request, progress):
    first = engine.run(make_request(idempotency_key="key-seed", seed=1), progress)
    second = engine.run(make_request(idempotency_key="key-seed", seed=2), progress)

    assert first.candidates != second.candidates


# --- Candidates and ranking -------------------------------------------------------


def test_rejected_candidates_are_kept_with_a_reason(engine, make_request, progress):
    """Rule 8: never silently drop a candidate."""
    result = engine.run(make_request(params={"mock": {"candidate_count": 40}}), progress)

    rejected = result.rejected
    assert rejected, "40 candidates should trip at least one hard filter"
    for candidate in rejected:
        assert candidate.rejection_reason, f"{candidate.ref} was rejected without a reason"
        assert candidate.rank is None
        assert candidate.overall_score is None


def test_accepted_candidates_are_contiguously_ranked(engine, make_request, progress):
    result = engine.run(make_request(params={"mock": {"candidate_count": 30}}), progress)

    ranks = sorted(c.rank for c in result.accepted)
    assert ranks == list(range(1, len(ranks) + 1))


def test_accepted_candidates_are_ordered_best_first(engine, make_request, progress):
    result = engine.run(make_request(params={"mock": {"candidate_count": 30}}), progress)

    scores = [c.overall_score for c in result.accepted]
    assert scores == sorted(scores, reverse=True)


def test_every_candidate_carries_the_full_metric_decomposition(engine, make_request, progress):
    """Design map 12: report the decomposition, not a single opaque score."""
    result = engine.run(make_request(), progress)

    for candidate in result.candidates:
        names = [m.name for m in candidate.metrics]
        assert "state_separation" in names
        assert "predicted_leakage" in names
        assert len(names) == len(set(names))
        for metric in candidate.metrics:
            assert metric.direction in ("HIGHER_BETTER", "LOWER_BETTER")


def test_candidate_count_is_honoured(engine, make_request, progress):
    result = engine.run(make_request(params={"mock": {"candidate_count": 5}}), progress)
    assert len(result.candidates) == 5


# --- Artifacts --------------------------------------------------------------------


def test_artifacts_exist_on_disk_with_matching_checksums(engine, make_request, progress):
    request = make_request()
    result = engine.run(request, progress)

    for artifact in result.artifacts:
        path = Path(request.output_dir) / artifact.path
        assert path.is_file(), f"{artifact.path} was referenced but not written"
        assert sha256_file(path) == artifact.checksum_sha256


def test_artifact_paths_are_relative_to_the_output_dir(engine, make_request, progress):
    result = engine.run(make_request(), progress)

    for artifact in result.artifacts:
        assert not Path(artifact.path).is_absolute()


def test_a_design_table_and_per_candidate_sequences_are_produced(engine, make_request, progress):
    result = engine.run(make_request(), progress)

    kinds = {a.kind for a in result.artifacts}
    assert "design_table" in kinds
    assert "sequence_fasta" in kinds

    for artifact in result.artifacts:
        if artifact.kind == "sequence_fasta":
            assert artifact.candidate_ref is not None


# --- Cancellation -----------------------------------------------------------------


def test_cancellation_is_honoured_and_is_not_a_failure(engine, make_request):
    """Cooperative cancellation: the callback says stop, the engine stops (§6.2)."""
    calls: list[int] = []

    def stop_after_two(percent: int, stage: str) -> bool:
        calls.append(percent)
        return len(calls) < 3

    result = engine.run(make_request(), stop_after_two)

    assert result.status == CANCELLED
    assert result.error is None
    assert result.candidates == []
    assert len(calls) == 3, "the engine must stop asking once told to stop"


def test_cancelling_immediately_produces_no_work(engine, make_request):
    request = make_request()
    result = engine.run(request, lambda percent, stage: False)

    assert result.status == CANCELLED
    assert not Path(request.output_dir).exists() or not any(Path(request.output_dir).iterdir())


# --- Failure ----------------------------------------------------------------------


def test_injected_failure_returns_a_failed_result_not_an_exception(engine, make_request, progress):
    result = engine.run(
        make_request(params={"mock": {"fail": True, "fail_message": "Unsupported organism."}}),
        progress,
    )

    assert result.status == FAILED
    assert result.error == "Unsupported organism."
    assert result.candidates == []


def test_missing_input_file_fails_safely(engine, make_request, progress, tmp_path):
    result = engine.run(make_request(input_path=str(tmp_path / "nope.csv")), progress)

    assert result.status == FAILED
    assert "could not be read" in result.error
    assert str(tmp_path) not in result.error, "error text must not leak filesystem paths (§6.2)"


def test_checksum_mismatch_is_detected(engine, make_request, progress):
    result = engine.run(make_request(input_checksum="0" * 64), progress)

    assert result.status == FAILED
    assert "checksum" in result.error.lower()


def test_unknown_scoring_profile_fails_cleanly(engine, make_request, progress):
    result = engine.run(make_request(scoring_profile="does-not-exist"), progress)

    assert result.status == FAILED
    assert "does-not-exist" in result.error


# --- Client resolution ------------------------------------------------------------


def test_load_engine_resolves_a_dotted_path():
    assert isinstance(load_engine("engine.client.MockEngine"), MockEngine)


def test_load_engine_rejects_a_missing_module():
    with pytest.raises(ValueError, match="Cannot import engine module"):
        load_engine("engine.nonexistent.Thing")


def test_load_engine_rejects_a_missing_class():
    with pytest.raises(ValueError, match="has no attribute"):
        load_engine("engine.client.NoSuchEngine")


def test_load_engine_rejects_something_that_is_not_an_engine():
    with pytest.raises(TypeError, match="does not implement"):
        load_engine("engine.contract.SCHEMA_VERSION")


def test_mock_and_local_engines_both_satisfy_the_protocol():
    assert isinstance(MockEngine(), EngineClient)
    assert isinstance(LocalEngine(), EngineClient)


def test_local_engine_is_not_implemented_until_step_5(make_request, progress):
    with pytest.raises(NotImplementedError, match="Step 5"):
        LocalEngine().run(make_request(), progress)


# --- Capabilities -----------------------------------------------------------------


def test_capabilities_advertise_what_the_engine_supports(engine):
    """The Platform validates submissions against this instead of importing the
    registries directly, which §3 forbids."""
    caps = engine.capabilities()

    assert caps.engine_version == MockEngine.ENGINE_VERSION
    assert "toehold" in caps.available_families
    assert "default" in caps.scoring_profiles

    by_name = {family.name: family for family in caps.gate_families}
    assert by_name["toehold"].available
    assert by_name["toehold"].label == "Toehold Riboswitch"
    # Planned families are advertised but not selectable, so the UI can show them
    # greyed out instead of hardcoding a "coming soon" list.
    assert not by_name["crispr"].available
    assert by_name["crispr"].description


def test_local_engine_reports_the_same_installed_families():
    assert (
        LocalEngine().capabilities().available_families
        == MockEngine().capabilities().available_families
    )


def test_capabilities_do_not_require_a_job(engine):
    """Cheap enough to call on every request."""
    assert engine.capabilities().schema_version
