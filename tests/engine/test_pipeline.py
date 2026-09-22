"""``run_pipeline`` / ``build_tools`` / ``LocalEngine`` — the `direct` and `de` smoke
paths.

docs/smoke-run.md is the design document the `direct` path implements; docs/genes.md is
the one the `de` path implements — both exactly the toehold family, both nothing under
``engine/gates/`` touched to build. These tests exercise the real thing end to end —
real ViennaRNA folding, real ``GeneSelector``/``TriggerScorer``, the real ``ToeholdGate``,
the real scoring layer — the same way tests/engine/gates/test_toehold.py and
tests/engine/test_mock_engine.py do; nothing here is mocked.
"""

import hashlib
import os

import pytest

from engine.client import LocalEngine
from engine.contract import CANCELLED, INPUT_DE, INPUT_DIRECT, SCHEMA_VERSION
from engine.domain import AssemblyStandard, Host
from engine.errors import InputValidationError
from engine.pipeline import build_tools, run_pipeline

# Chosen empirically (docs/smoke-run.md §5): a hand-repeated test sequence echoes extra
# AUGs into the switch through the toehold's reverse-complement construction and every
# design is correctly rejected. This one is not repetitive and reliably validates.
CLEAN_TRIGGER = "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA"

# Real genes from the bundled reference transcriptomes (docs/genes.md, docs/ROADMAP.md
# Q1), keyed by their real NCBI locus tag / SGD systematic name — verified empirically
# to produce real, accepted toehold candidates through the full pipeline, the same
# "chosen empirically" discipline CLEAN_TRIGGER above documents for the `direct` path.
REAL_DE_DATASET = "gene_id,gene_symbol,log2fc,padj\nb3908,sodA,3.2,0.001\nb0033,carA,-2.8,0.002\n"
REAL_YEAST_DATASET = "gene_id,log2fc,padj\nYDR281C,1.2,0.001\nYER085C,-1.4,0.002\n"


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


def _de_request_factory(make_request, tmp_path, filename: str, content: str, organism: str):
    """Shared by ``de_request`` and ``yeast_de_request``: a real `de` submission
    against real dataset ``content``, rather than the shared ``dataset`` fixture's
    symbol-keyed rows that don't join against any bundled transcriptome."""
    dataset_path = tmp_path / filename
    dataset_path.write_text(content, encoding="utf-8", newline="")
    checksum = hashlib.sha256(content.encode()).hexdigest()

    def _make(**overrides):
        defaults = {
            "input_mode": INPUT_DE,
            "input_path": str(dataset_path),
            "input_checksum": checksum,
            "organism": organism,
            "gate_families": ["toehold"],
        }
        defaults.update(overrides)
        return make_request(**defaults)

    return _make


@pytest.fixture
def de_request(make_request, tmp_path):
    return _de_request_factory(
        make_request, tmp_path, "real_de_dataset.csv", REAL_DE_DATASET, "ecoli"
    )


@pytest.fixture
def yeast_de_request(make_request, tmp_path):
    return _de_request_factory(
        make_request, tmp_path, "real_yeast_dataset.csv", REAL_YEAST_DATASET, "yeast"
    )


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


def test_exact_direct_trigger_exposes_raw_selection_provenance(direct_request, always_continue):
    result = LocalEngine().run(direct_request(), always_continue)

    assert result.candidates
    for candidate in result.candidates:
        feature = candidate.triggers["features"][0]
        assert feature["selection_method"] == "rnaplfold_mean_base_unpaired_v1"
        assert feature["selection_metric"] == "mean_base_unpaired_probability"
        assert feature["selection_score"] == feature["openness"]


def test_a_de_run_against_real_genes_completes_with_real_candidates(de_request, always_continue):
    """The MVP scope confirmed in docs/genes.md: GeneSelector picks the best real
    gene(s), their real transcripts are scanned by the same TriggerScorer the `direct`
    path uses, and the result is real, accepted toehold candidates — not a
    NotImplementedError, not an empty warning-only result."""
    result = LocalEngine().run(de_request(), always_continue)

    assert result.status == "succeeded"
    assert result.error is None
    assert result.candidates
    assert all(c.gate_family == "toehold" for c in result.candidates)
    # Both real genes' symbols should be traceable somewhere in the result — either a
    # design built against one of them, or the summary warning naming the best one.
    assert any("sodA" in c.summary or "carA" in c.summary for c in result.candidates)
    assert any("sodA" in w or "carA" in w for w in result.warnings)


def test_a_de_run_is_not_available_for_human(de_request, always_continue):
    """docs/ROADMAP.md Q1: *E. coli* and yeast both have a bundled reference
    transcriptome now; human does not (a genomic CDS extraction is the wrong tool for
    a heavily-spliced genome — ``tools/sync_transcriptome.py``). A human `de`
    submission fails cleanly rather than silently returning zero candidates or
    crashing on a missing lookup — today it fails even earlier than ``_de_trigger``'s
    own transcriptome guard, on Q12's still-open "no human promoter/terminator"
    limitation (``_resolve_outputs``, ahead of trigger scoring in ``run_pipeline``'s
    own order) — a real, equally honest reason to stop, and a reminder that
    ``_de_trigger``'s host guard is defence in depth for the day Q12 is answered for
    another host, not dead code today."""
    result = LocalEngine().run(de_request(organism="human"), always_continue)

    assert result.status == "failed"
    assert "human" in result.error.lower()


def test_a_de_run_against_real_yeast_genes_completes_with_real_candidates(
    yeast_de_request, always_continue
):
    """The same MVP shape as the *E. coli* happy path above, now for the second bundled
    host — real genes (docs/genes.md, ``tools/sync_transcriptome.py`` yeast) through
    the same ``GeneSelector``/``TriggerScorer``/``ToeholdGate`` path, no second
    implementation anywhere. ``ToeholdGate.supported_hosts`` already listed
    ``Host.YEAST`` before this session — only the transcriptome and the
    promoter/terminator were missing."""
    result = LocalEngine().run(yeast_de_request(), always_continue)

    assert result.status == "succeeded"
    assert result.error is None
    assert result.candidates
    assert any("YDR281C" in w or "YER085C" in w for w in result.warnings)


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


# --- Plasmid construction (stage 5, docs/plasmids.md E5a) ---------------------------


def test_a_direct_run_populates_real_plasmid_segments(direct_request, always_continue):
    """The default output (GFP) is fully configured (docs/ROADMAP.md Q11/Q12), so a
    plain direct run — no payload requested explicitly — gets a real plasmid, not the
    ``[]`` PlasmidRing.tsx used to be handed while stage 5 was a stub."""
    result = LocalEngine().run(direct_request(), always_continue)

    assert result.candidates
    for candidate in result.candidates:
        segments = candidate.design["plasmid_segments"]
        assert [s["kind"] for s in segments] == ["promoter", "switch", "payload", "terminator"]
        assert all(s["length_bp"] > 0 for s in segments)
        assert candidate.design["logic_graph"]["output"] == "GFP"


def test_a_genbank_artifact_is_written_per_accepted_candidate(direct_request, always_continue):
    result = LocalEngine().run(direct_request(), always_continue)

    accepted = [c for c in result.candidates if not c.is_rejected]
    genbank_refs = {a.candidate_ref for a in result.artifacts if a.kind == "genbank"}
    assert genbank_refs == {c.ref for c in accepted}


def test_the_genbank_artifact_parses_back_as_a_circular_plasmid(direct_request, always_continue):
    from Bio import SeqIO

    request = direct_request(idempotency_key="genbank-parse-back")
    result = LocalEngine().run(request, always_continue)
    genbank = next(a for a in result.artifacts if a.kind == "genbank")

    with open(os.path.join(request.output_dir, genbank.path)) as handle:
        record = SeqIO.read(handle, "genbank")

    assert record.annotations.get("topology") == "circular"
    assert len(record.features) == 4


def test_an_unconfigured_output_fails_the_whole_run_cleanly(direct_request, always_continue):
    """mCherry has no catalog entry yet (docs/ROADMAP.md Q11) — the same "none of the
    requested X could be built" pattern already used for gate families."""
    request = direct_request(params={"payload": {"outputs": ["mcherry"]}})
    result = LocalEngine().run(request, always_continue)

    assert result.status == "failed"
    assert "mcherry" in result.error.lower() or "Q11" in result.error


def test_an_unknown_output_string_is_a_clean_failure(direct_request, always_continue):
    request = direct_request(params={"payload": {"outputs": ["not-a-real-output"]}})
    result = LocalEngine().run(request, always_continue)

    assert result.status == "failed"
    assert "not-a-real-output" in result.error


def test_a_custom_payload_builds_through_the_full_pipeline(direct_request, always_continue):
    request = direct_request(
        params={"payload": {"outputs": ["other"], "custom_sequence": "AUGGCUAAGCUUAACUAA"}}
    )
    result = LocalEngine().run(request, always_continue)

    assert result.status == "succeeded"
    for candidate in result.candidates:
        payload = next(s for s in candidate.design["plasmid_segments"] if s["kind"] == "payload")
        assert payload["name"] == "Custom"


def test_mixed_outputs_use_only_the_buildable_ones_and_warn_about_the_rest(
    direct_request, always_continue
):
    request = direct_request(params={"payload": {"outputs": ["gfp", "mcherry"]}, "mock": {}})
    result = LocalEngine().run(request, always_continue)

    assert result.status == "succeeded"
    assert any("mcherry" in w for w in result.warnings)
    assert all(c.design["logic_graph"]["output"] == "GFP" for c in result.candidates)


def test_run_pipeline_asks_for_circular_screening_when_building_a_plasmid(
    direct_request, always_continue, monkeypatch
):
    """PlasmidBuilder.build() is responsible for circular screening
    (tests/engine/test_plasmids.py already locks in the unit itself); this is the
    integration guarantee that run_pipeline actually reaches that code path. The same
    shared ``screener`` is also used linearly by stage 3's switch validation, so both
    ``True`` and ``False`` calls are expected — only the presence of a ``True`` one is
    this test's concern."""
    from engine.stages.motifs import MotifScreener

    calls = []
    original = MotifScreener.violations

    def spy(self, sequence, *, circular=False):
        calls.append(circular)
        return original(self, sequence, circular=circular)

    monkeypatch.setattr(MotifScreener, "violations", spy)
    result = LocalEngine().run(direct_request(), always_continue)

    assert result.candidates
    assert True in calls


# --- Backbone selection (docs/plasmids.md Q13, docs/ROADMAP.md E5b) -----------------


def test_no_backbone_param_is_unchanged_behaviour(direct_request, always_continue):
    """Omitting params.backbone entirely must stay byte-for-byte what every direct run
    produced before this feature existed — four segments, no origin, no marker."""
    result = LocalEngine().run(direct_request(), always_continue)

    assert result.status == "succeeded"
    for candidate in result.candidates:
        kinds = [s["kind"] for s in candidate.design["plasmid_segments"]]
        assert kinds == ["promoter", "switch", "payload", "terminator"]


def test_a_catalog_backbone_is_assembled_into_the_plasmid(direct_request, always_continue):
    request = direct_request(params={"backbone": {"catalog_key": "psb1a3"}})
    result = LocalEngine().run(request, always_continue)

    assert result.status == "succeeded"
    for candidate in result.candidates:
        segments = candidate.design["plasmid_segments"]
        assert [s["kind"] for s in segments] == [
            "promoter",
            "switch",
            "payload",
            "terminator",
            "backbone",
        ]
        backbone = segments[-1]
        assert backbone["name"] == "pSB1A3"
        assert backbone["length_bp"] == 2155
        # sequence_length_bp must agree with the segments actually drawn (this session's
        # earlier PlasmidRing bug: a switch-only value here makes the ring's arcs
        # overflow past 360 degrees).
        assert candidate.design["sequence_length_bp"] == sum(s["length_bp"] for s in segments)


def test_an_unknown_catalog_key_fails_the_whole_run_cleanly(direct_request, always_continue):
    request = direct_request(params={"backbone": {"catalog_key": "not-a-real-backbone"}})
    result = LocalEngine().run(request, always_continue)

    assert result.status == "failed"
    assert "not-a-real-backbone" in result.error


def test_a_custom_genbank_backbone_is_assembled_into_the_plasmid(direct_request, always_continue):
    """A real backbone built and exported once, then handed back in as if a researcher
    uploaded it — the same round-trip discipline test_plasmids.py applies directly to
    parse_custom_backbone, exercised here through the whole pipeline instead."""
    source_request = direct_request(
        params={"backbone": {"catalog_key": "psb1c3"}}, idempotency_key="custom-backbone-src"
    )
    baseline = LocalEngine().run(source_request, always_continue)
    genbank_artifact = next(a for a in baseline.artifacts if a.kind == "genbank")
    with open(os.path.join(source_request.output_dir, genbank_artifact.path)) as handle:
        gb_text = handle.read()

    custom_request = direct_request(
        params={"backbone": {"custom_genbank": gb_text}}, idempotency_key="custom-backbone-use"
    )
    result = LocalEngine().run(custom_request, always_continue)

    assert result.status == "succeeded"
    for candidate in result.candidates:
        kinds = [s["kind"] for s in candidate.design["plasmid_segments"]]
        assert kinds[-1] == "backbone"


def test_providing_both_catalog_key_and_custom_genbank_fails_cleanly(
    direct_request, always_continue
):
    request = direct_request(
        params={"backbone": {"catalog_key": "psb1a3", "custom_genbank": "ignored"}}
    )
    result = LocalEngine().run(request, always_continue)

    assert result.status == "failed"
    assert "both" in result.error.lower()


# --- Failure paths, all as data (EngineClient's own contract) -------------------------


def test_de_mode_fails_cleanly_on_an_identifier_namespace_mismatch(direct_request, always_continue):
    """`de` mode is real now (see the success path above/below), but the shared
    ``dataset`` fixture (tests/engine/conftest.py) keys its rows by gene *symbol*
    (``lacZ``, ``rpoS``, ``katG``), while the bundled reference transcriptome is keyed
    by NCBI locus tag (``engine.transcriptome`` — docs/genes.md §3 G-d's exact
    namespace-mismatch scenario). That must fail as data, not crash."""
    request = direct_request(input_mode=INPUT_DE, trigger_sequence="")
    result = LocalEngine().run(request, always_continue)
    assert result.status == "failed"
    assert "identifier namespace" in result.error.lower()


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


def test_requesting_only_toehold_and_fails_cleanly_not_a_crash(direct_request, always_continue):
    """ToeholdAndGate.available is inherited True, but generate_designs is an
    unconditional NotImplementedError. Dormant with one trigger (arity always rejects
    first); a scanned paste (docs/triggers.md E2b) can produce real 2-input trigger
    sets that would otherwise reach it. Must fail as data, never propagate raw
    (docs/triggers.md, blocking bug found during review)."""
    result = LocalEngine().run(direct_request(gate_families=["toehold_and"]), always_continue)
    assert result.status == "failed"
    assert "toehold_and" in result.error.lower() or "and" in result.error.lower()


def test_a_long_paste_never_reaches_the_broken_and_family_uncaught(direct_request, always_continue):
    """The actual crash scenario: mixing a working family with the broken AND one,
    against a paste long enough to scan into multiple, non-overlapping trigger
    candidates — build_trigger_sets will genuinely pair some of them."""
    long_trigger = (
        "AUGGUGAGCAAGGGCGAGGAGGAUAACAUGGCCAUCAUCAAGGAGUUCAUGCGCUUCAAGGUGCAC"
        "AUGGAGGGCUCCGUGAACGGCCACGAGUUCGAGAUCGAGGGCGAGGGCGAGGGCCGCCCCUACGAG"
        "GGCACCCAGACC"
    )
    result = LocalEngine().run(
        direct_request(trigger_sequence=long_trigger, gate_families=["toehold", "toehold_and"]),
        always_continue,
    )
    assert result.status == "succeeded"
    assert result.candidates
    assert all(c.gate_family == "toehold" for c in result.candidates)
    assert any("toehold_and" in w for w in result.warnings)


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


# --- Trigger selection (stage 2, docs/triggers.md E2b) ------------------------------
#
# A real fragment of mCherry's CDS (144 nt) — the exact case that motivated this
# feature: pasted whole, only its silently-unscanned tail used to be tried, and that
# tail happened to fail (extra AUGs). Longer than one trigger window
# (max(trigger_lengths) = 36), so it is scanned rather than used whole.
LONG_PASTE = (
    "AUGGUGAGCAAGGGCGAGGAGGAUAACAUGGCCAUCAUCAAGGAGUUCAUGCGCUUCAAGGUGCAC"
    "AUGGAGGGCUCCGUGAACGGCCACGAGUUCGAGAUCGAGGGCGAGGGCGAGGGCCGCCCCUACGAG"
    "GGCACCCAGACC"
)


@pytest.mark.parametrize("trigger_lengths", [[31], [30, 31, 33]])
def test_long_direct_scan_rejects_non_exact_footprints(
    trigger_lengths, direct_request, always_continue
):
    request = direct_request(
        trigger_sequence=LONG_PASTE,
        params={"constraints": {"trigger_lengths": trigger_lengths}},
    )

    result = LocalEngine().run(request, always_continue)

    assert result.status == "failed"
    assert result.error is not None
    assert "trigger_lengths" in result.error
    assert "30, 33, and 36" in result.error


@pytest.mark.parametrize("trigger_lengths", [[31], [30, 31, 33]])
def test_de_scan_rejects_non_exact_footprints(trigger_lengths, de_request, always_continue):
    request = de_request(params={"constraints": {"trigger_lengths": trigger_lengths}})

    result = LocalEngine().run(request, always_continue)

    assert result.status == "failed"
    assert result.error is not None
    assert "trigger_lengths" in result.error
    assert "30, 33, and 36" in result.error


def test_manual_direct_trigger_retains_legacy_fitting_variant_sweep(
    direct_request, always_continue
):
    request = direct_request(params={"constraints": {"trigger_lengths": [31, 40]}})

    result = LocalEngine().run(request, always_continue)

    assert result.status == "succeeded"
    assert len(result.candidates) == 3
    assert {
        candidate.triggers["features"][0]["selection_method"] for candidate in result.candidates
    } == {"rnaplfold_mean_base_unpaired_v1"}


def test_a_paste_longer_than_one_window_is_scanned_not_silently_truncated(
    direct_request, always_continue
):
    result = LocalEngine().run(direct_request(trigger_sequence=LONG_PASTE), always_continue)

    assert result.status == "succeeded"
    assert result.candidates
    assert not all(c.is_rejected for c in result.candidates)
    # More than one distinct window actually got used — this is the whole point, not
    # an accident of one lucky offset.
    starts = {c.design.get("trigger_start_index") for c in result.candidates}
    assert len(starts) > 1
    assert any("scanned" in w and "144 nt" in w for w in result.warnings)


def test_scanned_direct_and_de_report_gate_aware_rnaplfold_provenance(
    direct_request, de_request, always_continue
):
    direct_result = LocalEngine().run(direct_request(trigger_sequence=LONG_PASTE), always_continue)
    de_result = LocalEngine().run(de_request(), always_continue)
    expected = "joint P8"

    assert any(expected in warning for warning in direct_result.warnings)
    assert any(expected in warning for warning in de_result.warnings)
    for result in (direct_result, de_result):
        assert result.candidates
        for candidate in result.candidates:
            feature = candidate.triggers["features"][0]
            assert feature["selection_method"] == "rnaplfold_gate_aware_joint_opening_v2"
            assert feature["selection_metric"] == "selected_joint_p8"
            assert feature["selection_score"] == feature["selected_seed_probability"]
            assert feature["mean_marginal_openness_20"] is not None
            assert feature["joint_open_probability_20"] is not None
            assert feature["delta_g_open_kcal_per_mol_per_nt"] is not None
            assert feature["seed_trials"]
            assert feature["rnaplfold"]["temperature_celsius"] == 37.0
            assert feature["orientation"] == "transcript_forward"


def test_every_candidate_records_which_window_it_came_from(direct_request, always_continue):
    result = LocalEngine().run(direct_request(trigger_sequence=LONG_PASTE), always_continue)
    for candidate in result.candidates:
        start = candidate.design.get("trigger_start_index")
        assert isinstance(start, int)
        assert start >= 0
        assert candidate.triggers["features"][0]["start_index"] == start


def test_a_long_paste_with_nothing_usable_reports_why_not_a_generic_message(
    direct_request, always_continue
):
    """A homopolymer run: every window of either configured length trivially contains
    one, so nothing survives TriggerScorer's own screen before switch design is even
    attempted — a different, earlier failure than a design-validation rejection."""
    result = LocalEngine().run(direct_request(trigger_sequence="G" * 50), always_continue)

    assert result.status == "succeeded"
    assert result.candidates == []
    assert any("50 nt" in w and "possible trigger window" in w for w in result.warnings)
    # The old, generic message must not also appear — one clear reason, not two.
    assert not any("docs/smoke-run.md §5" in w for w in result.warnings)


def test_a_paste_at_or_under_one_window_is_unaffected_byte_for_byte(
    direct_request, always_continue
):
    """The threshold decision's whole point (docs/triggers.md T2): CLEAN_TRIGGER is
    exactly max(trigger_lengths) = 36 nt, and must still produce exactly the 3 designs
    (one per swept toehold length) it always has — not the 7 that scanning its own
    sub-windows would add. A regression guard on the threshold itself, not just a new
    feature test."""
    result = LocalEngine().run(direct_request(), always_continue)

    assert result.status == "succeeded"
    assert len(result.candidates) == 3
    assert {c.design.get("trigger_start_index") for c in result.candidates} == {0}
    assert not any("scanned" in w for w in result.warnings)


def test_rejections_are_summarized_with_reasons_when_scanning_finds_candidates_but_none_build(
    direct_request, always_continue
):
    """Unlike the all-homopolymer case above, this paste's windows pass the cheap
    screen and reach switch design/validation — a later, different failure point.
    Empirically verified deterministic: every window built from this repeating
    trinucleotide pattern embeds either a second AUG or an in-frame stop once
    reverse-complemented into a switch, so nothing here ever builds."""
    paste = "AUG" * 9 + "ACG" * 9  # 54 nt, real RNA, longer than one window
    result = LocalEngine().run(direct_request(trigger_sequence=paste), always_continue)

    assert result.status == "succeeded"
    assert result.candidates == []
    assert any("generated design(s) rejected:" in w for w in result.warnings)
    assert any("AUG" in w or "stop codon" in w for w in result.warnings)


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
        "plasmid_builder",
        "constraints",
        "families",
        "warnings",
    }


def test_plasmid_builder_shares_the_same_screener_and_codons_instances(direct_request):
    """A second, independently configured MotifScreener/CodonOptimizer would mean the
    plasmid compliance check and everything else agreeing by coincidence rather than by
    construction (this module's own docstring on why tools are built once)."""
    tools = build_tools(direct_request(), Host.ECOLI)

    assert tools["plasmid_builder"].screener is tools["screener"]
    assert tools["plasmid_builder"].codons is tools["codons"]


# --- _build_constraints (via build_tools) -----------------------------------------
#
# The API layer (api/params.py) now rejects an unknown constraint field before a run
# is even queued, but this is the engine's own defense — the check the API's absence
# would otherwise leave as the only one — so it stays covered here independently of
# whatever the API does.


def test_a_default_constraints_block_builds_with_no_overrides(direct_request):
    tools = build_tools(direct_request(), Host.ECOLI)
    assert tools["constraints"].max_triggers == 2
    assert tools["constraints"].standard == AssemblyStandard.RFC10


def test_an_unknown_constraint_field_is_rejected(direct_request):
    request = direct_request(params={"constraints": {"max_leakage": 0.08}})
    with pytest.raises(InputValidationError, match="max_leakage"):
        build_tools(request, Host.ECOLI)


def test_trigger_lengths_coerces_from_a_json_list_to_a_tuple(direct_request):
    """A JSON-sourced dict carries a list; Constraints.trigger_lengths is a tuple
    (CLAUDE.md §6: hashable arguments for FoldEngine.mfe's lru_cache)."""
    request = direct_request(params={"constraints": {"trigger_lengths": [30, 45]}})
    tools = build_tools(request, Host.ECOLI)
    assert tools["constraints"].trigger_lengths == (30, 45)


@pytest.mark.parametrize(
    "trigger_lengths",
    [[], [30, 30], [0], [-1]],
    ids=["empty", "duplicate", "zero", "negative"],
)
@pytest.mark.parametrize("input_mode", [INPUT_DIRECT, INPUT_DE])
def test_invalid_trigger_lengths_fail_cleanly(
    trigger_lengths, input_mode, direct_request, de_request, always_continue
):
    request_factory = direct_request if input_mode == INPUT_DIRECT else de_request
    request = request_factory(params={"constraints": {"trigger_lengths": trigger_lengths}})

    result = LocalEngine().run(request, always_continue)

    assert result.status == "failed"
    assert result.error is not None
    assert "trigger_lengths" in result.error


def test_an_unknown_assembly_standard_is_rejected(direct_request):
    request = direct_request(params={"constraints": {"standard": "rfc-nonexistent"}})
    with pytest.raises(InputValidationError, match="rfc-nonexistent"):
        build_tools(request, Host.ECOLI)


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


def test_gate_aware_trigger_ranking_bumps_engine_version():
    assert LocalEngine.ENGINE_VERSION == "local-0.5.0-direct-and-de-ecoli-yeast"
