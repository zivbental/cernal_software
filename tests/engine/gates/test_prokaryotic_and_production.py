"""Production contracts of the bacterial AND family, using a real mCherry pair."""

import math
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine import sequences as sq
from engine.domain import Constraints, Host, TriggerCandidate, TriggerSet
from engine.errors import JobCancelled
from engine.gates import toehold
from engine.gates.toehold import KimSecondaryArmToeholdAndGate, ProkaryoticToeholdAndGate
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.scoring.profiles import DEFAULT_V1

# The engine's finder locates these at [34:70] and [250:300] in the mCherry fixture.
TRIGGER_A = "UCAUCAAGGAGUUCAUGCGCUUCAAGGUGCACAUGG"
TRIGGER_B = "UCCCCGACUACUUGAAGCUGUCCUUCCCCGAGGGCUUCAAGUGGGAGCGC"
FAMILIES = (ProkaryoticToeholdAndGate, KimSecondaryArmToeholdAndGate)


def _trigger(name, sequence, start):
    return TriggerCandidate(
        trigger_id=name,
        gene_id="mcherry",
        symbol="mcherry",
        sequence=sequence,
        start_index=start,
        openness=0.5,
        accessibility=0.5,
        mfe=-10.0,
        gc_content=50.0,
    )


@pytest.fixture(scope="module", params=FAMILIES, ids=lambda family: family.__name__)
def production(request):
    # A non-default temperature detects a conversion that silently assumes 37 C.
    folder = FoldEngine(30.0)
    gate = request.param(
        Host.ECOLI,
        folder,
        TranslationScorer(Host.ECOLI),
        CodonOptimizer(Host.ECOLI),
        compute_barrier=False,
        upper3_levels=("trigger_derived", "WWW_AUA"),
        max_secondary_assignments=1000,
        seed=7,
    )
    # Reverse the supplied tuple: the successful construction must reorder the record
    # into its actual roles, rather than only write the right names in architecture.
    length_a, length_b = gate.role_footprints()
    triggers = TriggerSet(
        activators=(
            _trigger("trig-b", TRIGGER_B[-length_b:], 300 - length_b),
            _trigger("trig-a", TRIGGER_A[:length_a], 34),
        )
    )
    design = next(
        gate.generate_designs(triggers, Constraints(stems_per_pair=1, closure_set="chosen"))
    )
    return gate, design


@pytest.fixture(scope="module")
def measured(production):
    gate, design = production
    context = design.sequence + "GCU" * 5 + "UAA"
    contextual = replace(
        design, architecture={**design.architecture, "evaluation_sequence": context}
    )
    with (
        patch.object(gate.folder, "saddle", side_effect=AssertionError("equilibrium only")),
        patch.object(gate.folder, "ensemble_defect", wraps=gate.folder.ensemble_defect) as defect,
        patch.object(
            gate.folder, "pooled_pair_probabilities", wraps=gate.folder.pooled_pair_probabilities
        ) as matrices,
    ):
        raw = gate.measure_design(contextual)
    return contextual, raw, defect.call_args_list, matrices.call_args_list


def test_generated_record_and_named_states_use_the_constructed_trigger_roles(production):
    gate, design = production
    a, b = design.trigger_set.activators
    assert a.trigger_id == design.architecture["trigger_a_id"] == "trig-a"
    assert b.trigger_id == design.architecture["trigger_b_id"] == "trig-b"
    length_a, length_b = gate.role_footprints()
    assert a.sequence == TRIGGER_A[:length_a]
    assert b.sequence == TRIGGER_B[-length_b:]


def test_a_anchored_label_does_not_reject_an_otherwise_constructible_stem(production, monkeypatch):
    gate, design = production
    a, b = design.trigger_set.activators
    stems = gate.secondary_stems(a.sequence, b.sequence, design.architecture["len_x"])
    stem = next(stem for stem in stems if stem.lock_energy <= 0)
    # Change only the classification label's assignments, retaining a constructible
    # stem's sequence/energies. Eligibility must depend on checks, never this label.
    labelled = replace(stem, states=("lockA",))
    monkeypatch.setattr(gate, "secondary_stems", lambda *_: [labelled])
    candidates = list(
        gate.generate_designs(
            design.trigger_set, Constraints(stems_per_pair=1, closure_set="chosen")
        )
    )
    assert candidates
    assert all(candidate.architecture["scheme"] == "A-anchored" for candidate in candidates)


def test_context_preserves_domain_coordinates_and_extends_the_target(production, measured):
    gate, original = production
    contextual, _raw, defects, matrices = measured
    switch = gate._switch_from_design(contextual)
    assert switch.domains == original.architecture["domain_map"]
    assert switch.dot_bracket == original.dot_bracket + "." * 18
    assert len(switch.sequence) == len(switch.dot_bracket)
    assert any(call.args == (switch.sequence, switch.dot_bracket) for call in defects)
    folded_states = {call.args[0] for call in matrices}
    a, b = original.trigger_set.activators
    assert {
        switch.sequence,
        f"{switch.sequence}&{a.sequence}",
        f"{switch.sequence}&{b.sequence}",
        f"{switch.sequence}&{a.sequence}&{b.sequence}",
    } <= folded_states


def test_changed_switch_prefix_cannot_be_reported_as_the_original_construct(production):
    gate, design = production
    altered = replace(design, architecture={**design.architecture, "evaluation_sequence": "A"})
    with pytest.raises(ValueError, match="unchanged switch"):
        gate._switch_from_design(altered)


def test_equilibrium_measurement_does_not_run_a_barrier_and_uses_the_configured_rt(
    production, measured
):
    gate, _design = production
    _contextual, raw, _defects, _matrices = measured
    assert raw["barrier"] is None
    for state in ("00", "01", "10", "11"):
        assert raw[f"P_open_{state}"] is not None
        assert raw[f"P_open_{state}"] == pytest.approx(
            math.exp(-raw[f"dG_open_{state}"] / gate.folder.rt)
        )


def test_existing_pass_supplies_metrics_and_diagnostics_without_remeasurement(
    production, measured, monkeypatch
):
    gate, _design = production
    contextual, raw, _defects, _matrices = measured

    def forbid_remeasurement(*args, **kwargs):
        raise AssertionError("the equilibrium pass must be reused")

    monkeypatch.setattr(gate, "measure_design", forbid_remeasurement)
    metrics = gate.metrics_from_measurement(contextual, raw)
    info = gate.diagnostics_from_measurement(contextual, raw)
    assert set(metrics) == {metric.name for metric in DEFAULT_V1.metrics}
    assert metrics["state_separation"] == pytest.approx(
        raw["separation"] / (gate.folder.rt * math.log(2.0))
    )
    assert info["method"] == "prokaryotic_equilibrium"
    assert info["observables"] == raw
    assert info["feasibility"]["total"] == len(gate.THRESHOLDS) == 22
    assert info["feasibility"]["violations"] == list(gate.gate_violations(raw))
    assert info["barrier_computed"] is False
    assert info["evaluation_context"] == "full_switch_plus_payload_cds_no_promoter_or_terminator"
    assert info["worst_off_state"] == max(
        ("00", "01", "10"), key=lambda state: raw[f"P_open_{state}"]
    )
    assert info["on_pct"] == pytest.approx(raw["P_open_11"] * 100)


def test_explicit_barrier_request_still_works_for_research(production, measured):
    gate, _design = production
    contextual, _raw, _defects, _matrices = measured
    with patch.object(gate.folder, "saddle", return_value=9.5) as saddle:
        raw = gate.measure_design(contextual, compute_barrier=True)
    assert saddle.call_count == 1
    assert raw["barrier"] == 9.5


def test_on_ceiling_keeps_measured_on_probability_and_a_only_probes(production, measured):
    gate, _design = production
    contextual, _raw, _defects, _matrices = measured
    with patch.object(gate, "four_tube_observables", side_effect=AssertionError("past ceiling")):
        raw = gate.measure_design(contextual, on_ceiling=-1e9)
    info = gate.diagnostics_from_measurement(contextual, raw)
    assert raw["skipped"] == "on_ceiling"
    assert raw["P_open_11"] is not None
    assert raw["xstar_engA_10"] is not None
    assert raw["mainpre_engA_10"] is not None
    assert "dG_open_00" not in raw
    assert info["on_pct"] == pytest.approx(raw["P_open_11"] * 100)
    assert info["off_pct"] is None


def test_reduced_grid_is_explicit_and_search_scope_is_recorded(production):
    gate, design = production
    grid = list(gate._axis_grid("chosen"))
    assert len(grid) == 5 * 2 * 2
    assert {upper[0] for _closure, upper, _lower in grid} == {"trigger_derived", "WWW_AUA"}
    scope = design.architecture["secondary_search"]
    assert scope["assignments_considered"] == min(1000, scope["assignments_total"])
    assert scope["exhaustive"] is (scope["assignments_total"] <= 1000)
    assert scope["seed"] == 7


def test_arm_assignment_cap_is_applied_before_energy_work_and_is_reproducible(production):
    gate, design = production
    built = toehold._build_arms
    a, b = design.trigger_set.activators

    def considered(seed):
        with patch.object(toehold, "_build_arms", wraps=built) as arms:
            gate.secondary_stems(
                a.sequence, b.sequence, design.architecture["len_x"], max_assignments=7, seed=seed
            )
        return [call.args[2] for call in arms.call_args_list]

    first = considered(11)
    assert len(first) == 7
    assert first == considered(11)
    assert first != considered(12)


def test_research_defaults_keep_full_grid_and_barrier(production):
    production_gate, _design = production
    research = type(production_gate)(
        Host.ECOLI,
        production_gate.folder,
        production_gate.translation,
        production_gate.codons,
    )
    assert research.compute_barrier is True
    assert research.max_secondary_assignments is None
    assert len(list(research._axis_grid())) == 16 * 3 * 2


@pytest.mark.parametrize("cross_gene", [False, True])
def test_pair_scan_cap_bounds_matching_seed_work_before_pair_emission(production, cross_gene):
    gate, _design = production
    repetitive = "ACGU" * 500
    if cross_gene:
        pairs = gate.find_cross_gene_pairs("a", repetitive, "b", repetitive, max_matches=17)
    else:
        pairs = gate.find_trigger_pairs(repetitive, max_matches=17)
    list(pairs)
    scope = gate.last_pair_search
    assert scope["seed_matches_considered"] == 17
    assert scope["unique_overlaps"] <= 17
    assert scope["discovery_truncated"] is True
    assert scope["exhaustive"] is False
    assert scope["selection"] == "deterministic_seed_scan_prefix"


def test_pair_scan_can_cancel_during_seed_matching(production):
    gate, _design = production
    progress = []

    def checkpoint(done, total):
        progress.append((done, total))
        return done < 128

    with pytest.raises(JobCancelled):
        list(
            gate.find_cross_gene_pairs(
                "a",
                "ACGU" * 500,
                "b",
                "ACGU" * 500,
                max_matches=1000,
                on_progress=checkpoint,
            )
        )
    assert progress[-1] == (128, 1000)


def test_exhaustive_pair_budget_preserves_uncapped_research_pair_order(production):
    gate, _design = production
    transcript = TRIGGER_A + "AAC" * 40 + TRIGGER_B
    uncapped = list(gate.find_trigger_pairs(transcript))
    assert uncapped
    bounded = list(gate.find_trigger_pairs(transcript, max_matches=1000000))
    assert bounded == uncapped
    assert gate.last_pair_search["exhaustive"] is True
    assert gate.last_pair_search["pairs_emitted"] == len(bounded)


def test_pair_compatibility_reports_requested_overlap_range(production):
    gate, design = production
    minimum = design.architecture["len_x"] + 1
    result = gate.is_compatible(design.trigger_set, Constraints(overlap_range=(minimum, 18)))
    assert result.ok is False
    assert f"overlap_range {minimum}-18" in result.reason


def test_payload_prefix_context_marker_and_actual_length_are_preserved(production, measured):
    gate, _design = production
    contextual, raw, _defects, _matrices = measured
    explicit = replace(
        contextual,
        architecture={
            **contextual.architecture,
            "evaluation_context": "switch_plus_payload_prefix",
        },
    )
    info = gate.diagnostics_from_measurement(explicit, raw)
    assert info["evaluation_context"] == "switch_plus_payload_prefix"
    assert info["payload_head_nt"] == 18
    assert info["evaluated_nt"] == len(explicit.sequence) + 18


def _balanced_family(gate):
    return type(gate)(
        Host.ECOLI,
        gate.folder,
        gate.translation,
        gate.codons,
        compute_barrier=False,
        balanced_grid=True,
        upper3_levels=gate.upper3_levels,
        max_secondary_assignments=gate.max_secondary_assignments,
        seed=gate.seed,
    )


@pytest.mark.parametrize("closures", ["chosen", "full"])
def test_balanced_grid_retains_every_axis_combination_once(production, closures):
    gate, _design = production
    balanced = _balanced_family(gate)
    original_grid = list(gate._axis_grid(closures))
    balanced_grid = list(balanced._axis_grid(closures))
    assert len(balanced_grid) == len(original_grid)
    assert len(set(balanced_grid)) == len(balanced_grid)
    assert set(balanced_grid) == set(original_grid)
    # The first cycle varies closures and both auxiliary decisions, rather than
    # spending the entire initial prefix on the trigger-derived closure.
    prefix = balanced_grid[: len(balanced.CLOSURES_CHOSEN)]
    assert len({closure for closure, _upper, _lower in prefix}) == len(prefix)
    assert len({upper for _closure, upper, _lower in prefix}) == 2
    assert len({lower for _closure, _upper, lower in prefix}) == 2


def test_balanced_generation_interleaves_stems_without_changing_the_design_set(production):
    gate, design = production
    balanced = _balanced_family(gate)
    constraints = Constraints(stems_per_pair=4, stem_order="front", closure_set="chosen")
    original_designs = list(gate.generate_designs(design.trigger_set, constraints))
    balanced_designs = list(balanced.generate_designs(design.trigger_set, constraints))
    original_by_id = {item.design_id: item for item in original_designs}
    balanced_by_id = {item.design_id: item for item in balanced_designs}
    assert len(original_by_id) == len(original_designs)
    assert len(balanced_by_id) == len(balanced_designs)
    assert balanced_by_id == original_by_id
    prefix = balanced_designs[:8]
    assert len({item.architecture["stem_index"] for item in prefix}) >= 2
    assert len({item.architecture["closure"] for item in prefix}) >= 2


def test_pair_offsets_keep_the_complete_design_set_and_spread_a_short_global_budget(production):
    gate, design = production
    balanced = _balanced_family(gate)
    constraints = Constraints(stems_per_pair=2, stem_order="front", closure_set="chosen")
    original = list(balanced.generate_designs(design.trigger_set, constraints))
    original_by_id = {item.design_id: item for item in original}
    grid_size = len(tuple(balanced._axis_grid("chosen")))
    early = []
    for offset in range(8):
        rotated = list(
            balanced.generate_designs(design.trigger_set, constraints, grid_offset=offset)
        )
        assert len(rotated) == len(original)
        assert {item.design_id: item for item in rotated} == original_by_id
        early.extend(rotated[:2])
    assert len({item.architecture["closure"] for item in early}) == 5
    assert len({item.architecture["upper3"] for item in early}) == 2
    assert len({item.architecture["lower3"] for item in early}) == 2
    assert (
        list(balanced.generate_designs(design.trigger_set, constraints, grid_offset=grid_size))
        == original
    )


def test_grid_offset_does_not_change_historical_generation_order(production):
    gate, design = production
    constraints = Constraints(stems_per_pair=2, stem_order="front", closure_set="chosen")
    assert list(gate.generate_designs(design.trigger_set, constraints, grid_offset=7)) == list(
        gate.generate_designs(design.trigger_set, constraints)
    )


def test_strong_lock_selection_returns_the_three_cells_of_the_first_row():
    # Each weaker-lock point has better B energy, so it is a genuine trade-off.
    front = [
        toehold._SecondaryStem("A", "U", (), 0, -30 + i, -30 + 10 * (i % 3), -i) for i in range(9)
    ]
    selected = toehold._select_stems(front, 3, "strong_lock_row")
    assert [(s.lock_energy, s.a_site_energy) for s in selected] == [
        (-30, -30),
        (-29, -20),
        (-28, -10),
    ]
    assert toehold._select_stems(front, 12, "strong_lock_row") == selected
    assert toehold._select_stems(list(reversed(front)), 3, "strong_lock_row") == selected


def test_reduced_generation_records_the_selected_row_and_never_emits_noop_wobble(production):
    gate, design = production
    reduced = type(gate)(
        Host.ECOLI,
        gate.folder,
        gate.translation,
        gate.codons,
        upper3_levels=("WWW_AUA",),
        strengthen_lower3_only=True,
        max_secondary_assignments=1000,
        seed=7,
    )
    constraints = Constraints(stems_per_pair=3, stem_order="strong_lock_row", closure_set="chosen")
    candidates = list(reduced.generate_designs(design.trigger_set, constraints))
    assert candidates
    for candidate in candidates:
        architecture = candidate.architecture
        assert architecture["upper3"] == "WWW_AUA"
        selection = architecture["secondary_selection"]
        assert selection["policy"] == "strong_lock_row"
        assert selection["requested"] == 3
        assert 1 <= selection["selected"] <= 3
        if architecture["lower3"] == "wobble_GU":
            assert architecture["wobble_applied"] > 0
            assert architecture["lower3_energy_after"] < architecture["lower3_energy_before"]
        assert "secondary_selection" in reduced.PRODUCTION_GENERATION_KEYS


def test_strong_lock_selection_does_not_fill_empty_cells_from_weaker_rows():
    front = [toehold._SecondaryStem("A", "U", (), 0, -30 + i, -30 + i, -i) for i in range(9)]
    selected = toehold._select_stems(front, 3, "strong_lock_row")
    assert len(selected) == 1
    assert selected[0].lock_energy == -29  # centre of the only occupied top-row cell
    assert toehold._select_stems([], 3, "strong_lock_row") == []
    assert toehold._select_stems(front[:2], 3, "strong_lock_row") == front[:1]


@pytest.mark.parametrize("star", ["AAAGCGCGC", "AAGGCGCGC"])
def test_reduced_wobble_requires_actual_lower_arm_strengthening(production, star):
    gate, _ = production
    reduced = type(gate)(
        Host.ECOLI, gate.folder, gate.translation, gate.codons, strengthen_lower3_only=True
    )
    base = SimpleNamespace(domains={"main_pre_star": (0, 9), "main_pre": (9, 18)})
    sequence = list(star + sq.reverse_complement(star))
    original = list(sequence)
    result = reduced._apply_lower3(sequence, base, reduced.LOWER3_WOBBLE)
    assert result["wobble_applied"] > 0
    assert result["lower3_energy_after"] < result["lower3_energy_before"]
    assert sum(b in "GC" for b in sequence[:3]) > sum(b in "GC" for b in original[:3])
    assert all(
        a == b or (a, b) == ("A", "G") for a, b in zip(original[:9], sequence[:9], strict=True)
    )


@pytest.mark.parametrize("star", ["CCCGCGCGC", "ACGGCGCGC", "UUUGCGCGC"])
def test_reduced_wobble_never_weakens_or_duplicates_an_inapplicable_change(production, star):
    gate, _ = production
    reduced = type(gate)(
        Host.ECOLI, gate.folder, gate.translation, gate.codons, strengthen_lower3_only=True
    )
    base = SimpleNamespace(domains={"main_pre_star": (0, 9), "main_pre": (9, 18)})
    sequence = list(star + sq.reverse_complement(star))
    original = list(sequence)
    result = reduced._apply_lower3(sequence, base, reduced.LOWER3_WOBBLE)
    assert result["wobble_applied"] == 0
    assert sequence == original


def test_reduced_wobble_does_not_claim_strengthening_when_energy_is_missing(
    production, monkeypatch
):
    gate, _ = production
    reduced = type(gate)(
        Host.ECOLI, gate.folder, gate.translation, gate.codons, strengthen_lower3_only=True
    )
    base = SimpleNamespace(domains={"main_pre_star": (0, 9), "main_pre": (9, 18)})
    sequence = list("AAAGCGCGC" + sq.reverse_complement("AAAGCGCGC"))
    original = list(sequence)
    monkeypatch.setattr(toehold, "fixed_alignment_energy", lambda *_: None)
    assert reduced._apply_lower3(sequence, base, reduced.LOWER3_WOBBLE)["wobble_applied"] == 0
    assert sequence == original
