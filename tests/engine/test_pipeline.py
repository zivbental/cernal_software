"""``run_pipeline`` / ``build_tools`` / ``LocalEngine`` — the `direct` smoke path.

docs/smoke-run.md is the design document this implements: exactly the `direct` input
mode, exactly the toehold family, nothing under ``engine/gates/`` touched to build it.
These tests exercise the real thing end to end — real ViennaRNA folding, the real
``ToeholdGate``, the real scoring layer — the same way tests/engine/gates/test_toehold.py
and tests/engine/test_mock_engine.py do; nothing here is mocked.
"""

import os

import pytest

from engine.client import LocalEngine
from engine.contract import CANCELLED, INPUT_DE, INPUT_DIRECT, SCHEMA_VERSION
from engine.domain import Host
from engine.pipeline import build_tools, run_pipeline

# Chosen empirically (docs/smoke-run.md §5): a hand-repeated test sequence echoes extra
# AUGs into the switch through the toehold's reverse-complement construction and every
# design is correctly rejected. This one is not repetitive and reliably validates.
CLEAN_TRIGGER = "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA"


@pytest.fixture
def direct_request(make_request):
    def _make(**overrides):
        defaults = {
            "input_mode": INPUT_DIRECT,
            "trigger_sequence": CLEAN_TRIGGER,
            "organism": "ecoli",
            "gate_families": ["toehold"],
        }
        defaults.update(overrides)
        return make_request(**defaults)

    return _make


@pytest.fixture
def always_continue():
    return lambda pct, stage: True


# --- The happy path -----------------------------------------------------------------


def test_a_direct_run_completes_with_real_candidates(direct_request, always_continue):
    result = LocalEngine().run(direct_request(), always_continue)

    assert result.status == "succeeded"
    assert result.error is None
    assert result.candidates
    assert all(c.gate_family == "toehold" for c in result.candidates)


def test_engine_version_names_the_partial_scope():
    assert "direct" in LocalEngine.ENGINE_VERSION


def test_accepted_candidates_carry_the_real_metric_names(direct_request, always_continue):
    result = LocalEngine().run(direct_request(), always_continue)

    accepted = [c for c in result.candidates if not c.is_rejected]
    assert accepted
    for candidate in accepted:
        names = {m.name for m in candidate.metrics}
        assert names <= {
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
        assert "gate_folding_energy" in names  # ToeholdGate.evaluate_design always emits this


def test_accepted_candidates_are_ranked_contiguously(direct_request, always_continue):
    result = LocalEngine().run(direct_request(), always_continue)
    ranks = sorted(c.rank for c in result.candidates if not c.is_rejected)
    assert ranks == list(range(1, len(ranks) + 1))


def test_rejected_candidates_carry_no_rank_and_a_reason(direct_request, always_continue):
    result = LocalEngine().run(direct_request(), always_continue)
    for candidate in result.candidates:
        if candidate.is_rejected:
            assert candidate.rank is None
            assert candidate.overall_score is None
            assert candidate.rejection_reason


def test_artifacts_are_real_files_with_matching_checksums(direct_request, always_continue):
    from engine.artifacts import sha256_file

    request = direct_request()
    result = LocalEngine().run(request, always_continue)

    assert result.artifacts
    for artifact in result.artifacts:
        path = os.path.join(request.output_dir, artifact.path)
        assert os.path.isfile(path)
        assert sha256_file(path) == artifact.checksum_sha256


def test_the_design_table_has_one_row_per_candidate(direct_request, always_continue):
    request = direct_request()
    result = LocalEngine().run(request, always_continue)

    with open(os.path.join(request.output_dir, "candidates.csv")) as handle:
        rows = handle.read().strip().splitlines()
    assert len(rows) - 1 == len(result.candidates)  # header + one row each


def test_fasta_is_written_only_for_accepted_candidates(direct_request, always_continue):
    request = direct_request()
    result = LocalEngine().run(request, always_continue)

    fasta_refs = {a.candidate_ref for a in result.artifacts if a.kind == "sequence_fasta"}
    accepted_refs = {c.ref for c in result.candidates if not c.is_rejected}
    rejected_refs = {c.ref for c in result.candidates if c.is_rejected}

    assert fasta_refs == accepted_refs
    assert not (fasta_refs & rejected_refs)


# --- Determinism ----------------------------------------------------------------------


def test_same_request_produces_byte_identical_candidates(direct_request, always_continue):
    first = LocalEngine().run(direct_request(idempotency_key="det-1"), always_continue)
    second = LocalEngine().run(direct_request(idempotency_key="det-2"), always_continue)

    def key(c):
        return (c.ref, c.rank, c.overall_score, c.design["switch_sequence"])

    assert [key(c) for c in first.candidates] == [key(c) for c in second.candidates]


# --- Presentation gaps are honest, not broken (docs/smoke-run.md §4) ------------------


def test_logic_graph_has_at_least_one_gene_so_the_frontend_does_not_index_past_the_end(
    direct_request, always_continue
):
    """LogicCircuit.tsx indexes logic.genes[0] unconditionally on one code path — an
    empty genes list is a frontend crash, not just a blank diagram."""
    result = LocalEngine().run(direct_request(), always_continue)
    for candidate in result.candidates:
        assert len(candidate.design["logic_graph"]["genes"]) >= 1


def test_plasmid_segments_are_present_but_empty(direct_request, always_continue):
    """Stage 5 is not built — PlasmidRing.tsx handles an empty list safely
    (``candidate.design.plasmid_segments ?? []``); this pins that it stays empty
    rather than silently gaining fabricated segments."""
    result = LocalEngine().run(direct_request(), always_continue)
    for candidate in result.candidates:
        assert candidate.design["plasmid_segments"] == []


# --- Failure paths, all as data (EngineClient's own contract) -------------------------


def test_de_mode_fails_cleanly(direct_request, always_continue):
    request = direct_request(input_mode=INPUT_DE, trigger_sequence="")
    result = LocalEngine().run(request, always_continue)
    assert result.status == "failed"
    assert "direct" in result.error.lower()


def test_an_organism_the_engine_does_not_recognise_fails_cleanly(direct_request, always_continue):
    """docs/ROADMAP.md P1: Project.organism is free text ('E. coli'); this must not
    crash raw when it reaches the engine as-is."""
    result = LocalEngine().run(direct_request(organism="E. coli"), always_continue)
    assert result.status == "failed"
    assert "organism" in result.error.lower()


def test_a_trigger_sequence_that_is_too_short_fails_cleanly(direct_request, always_continue):
    result = LocalEngine().run(direct_request(trigger_sequence="AUGGCU"), always_continue)
    assert result.status == "failed"
    assert "short" in result.error.lower()


def test_a_trigger_sequence_with_invalid_characters_fails_cleanly(direct_request, always_continue):
    result = LocalEngine().run(
        direct_request(trigger_sequence="AUGXCUAAGCUUAACGGAUCCAUGGCUAAGCU"), always_continue
    )
    assert result.status == "failed"


def test_an_unknown_gate_family_name_fails_cleanly(direct_request, always_continue):
    result = LocalEngine().run(direct_request(gate_families=["not-a-real-family"]), always_continue)
    assert result.status == "failed"


def test_requesting_only_antisense_fails_cleanly_naming_q11(direct_request, always_continue):
    """AntisenseNotGate.__init__ requires a real payload CDS, and none exists yet
    (docs/ROADMAP.md Q11) — this must fail as data, not raise ValueError from deep
    inside a gate constructor."""
    result = LocalEngine().run(direct_request(gate_families=["antisense"]), always_continue)
    assert result.status == "failed"
    assert "antisense" in result.error.lower() or "payload" in result.error.lower()


def test_cancellation_before_the_run_starts(direct_request):
    result = LocalEngine().run(direct_request(), lambda pct, stage: False)
    assert result.status == CANCELLED


def test_cancellation_mid_switch_design(direct_request):
    """on_progress must be checked between batches within the dominant stage, not only
    when it begins — this simulates cancelling on a later call."""
    calls = {"n": 0}

    def on_progress(pct, stage):
        calls["n"] += 1
        return calls["n"] < 3

    result = LocalEngine().run(direct_request(), on_progress)
    assert result.status == CANCELLED


# --- build_tools ------------------------------------------------------------------


def test_build_tools_returns_every_documented_key(direct_request):
    tools = build_tools(direct_request(), Host.ECOLI)
    assert set(tools) == {
        "folder",
        "profiler",
        "off_target",
        "screener",
        "codons",
        "translation",
        "constraints",
        "families",
        "warnings",
    }


def test_build_tools_skips_antisense_with_a_warning(direct_request):
    tools = build_tools(direct_request(gate_families=["toehold", "antisense"]), Host.ECOLI)

    family_names = {f.name for f in tools["families"]}
    assert "antisense" not in family_names
    assert "toehold" in family_names
    assert any("antisense" in w.lower() for w in tools["warnings"])


def test_build_tools_constructs_no_gate_family_more_than_once_per_run():
    """FoldEngine's cache lives on the instance — two families must share one folder,
    not each get a cold cache (this module's own docstring)."""
    from engine.contract import JobRequest as _JR  # local alias, avoids shadowing above

    request = _JR(
        schema_version=SCHEMA_VERSION,
        run_id="r",
        idempotency_key="k",
        input_mode=INPUT_DIRECT,
        input_path="",
        input_checksum="",
        trigger_sequence=CLEAN_TRIGGER,
        organism="ecoli",
        params={},
        gate_families=["toehold"],
        scoring_profile="default",
        seed=None,
        output_dir="/tmp",
    )
    tools = build_tools(request, Host.ECOLI)
    assert tools["families"][0].folder is tools["folder"]


# --- Custom scoring flows through unchanged (X7, already built) ---------------------


def test_a_custom_scoring_override_actually_changes_the_result(direct_request, always_continue):
    baseline = LocalEngine().run(direct_request(idempotency_key="score-a"), always_continue)
    # Zero every metric ToeholdGate emits except gc_content — cand-000003 wins on
    # leakage/folding/dynamic-range under the default weights (verified), so isolating
    # gc_content (where it is not the best of the three) reliably flips first place,
    # unlike a partial reweight that leaves cand-000003 still dominant elsewhere.
    reweighted = LocalEngine().run(
        direct_request(
            idempotency_key="score-b",
            params={
                "scoring": {
                    "weights": {
                        "predicted_leakage": 0.0,
                        "gate_folding_energy": 0.0,
                        "dynamic_range": 0.0,
                        "trigger_accessibility": 0.0,
                        "gc_content": 10.0,
                    }
                }
            },
        ),
        always_continue,
    )

    def ranked_refs(result):
        accepted = sorted((c for c in result.candidates if not c.is_rejected), key=lambda c: c.rank)
        return [c.ref for c in accepted]

    assert {c.ref for c in baseline.candidates} == {c.ref for c in reweighted.candidates}
    assert ranked_refs(baseline) != ranked_refs(reweighted)


# --- run_pipeline called directly (bypassing LocalEngine's catch-and-convert) --------


def test_run_pipeline_raises_rather_than_returning_a_result_on_failure(
    direct_request, always_continue
):
    """LocalEngine.run is what converts EngineError to data — run_pipeline itself
    still raises, matching MockEngine._execute's half of the same split."""
    from engine.errors import InputValidationError

    with pytest.raises(InputValidationError):
        run_pipeline(direct_request(input_mode=INPUT_DE, trigger_sequence=""), always_continue)
