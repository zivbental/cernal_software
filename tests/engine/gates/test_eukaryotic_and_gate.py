"""The eukaryotic two-input AND gate family, its settings and the tool it shares with the notebook.

These tests fold with the real ViennaRNA model (one shared ``FoldEngine``, as in production) at a
small sampling budget. They pin behaviour that fails *silently* when wrong: a coordinate that is
off by one still folds and still scores, a failed measurement turned into ``0.0`` outranks every
real one, and a threshold hard-coded in a family is an invisible filter.
"""

import dataclasses

import pytest

from engine import sequences as sq
from engine.domain import (
    AndGateSettings,
    AssemblyStandard,
    Constraints,
    Host,
    TriggerCandidate,
    TriggerSet,
)
from engine.gates.toehold import EukaryoticToeholdAndGate, ToeholdAndGate
from engine.gates.tools import stem_opening as so
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.scoring.profiles import DEFAULT_V1
from engine.stages.motifs import MotifScreener
from engine.stages.switches import SwitchValidator

# Two 36 nt windows of one reporter transcript, 200 nt apart, with no AUG and no CAU in either (the
# reverse complement of CAU is AUG, which the hairpin is built from): every design on them is valid.
WINDOW_A = "UGGAGGGCUCCGUGAACGGCCACGAGUUCGAGAUCG"
WINDOW_B = "UGUCCUUCCCCGAGGGCUUCAAGUGGGAGCGCGUGA"

#: Cheap but real: the sampler check needs enough draws to be meaningful, not many.
FAST = AndGateSettings(n_samples=300, screen_samples=100, n_controls=3, singles_per_trigger=2)


def _trigger(trigger_id: str, sequence: str, start: int, gene: str = "REP") -> TriggerCandidate:
    return TriggerCandidate(
        trigger_id=trigger_id,
        gene_id=gene,
        symbol=gene,
        sequence=sequence,
        start_index=start,
        openness=0.6,
        accessibility=0.5,
        mfe=-4.0,
        gc_content=sq.gc_content(sequence),
    )


@pytest.fixture(scope="module")
def folder():
    return FoldEngine()


@pytest.fixture(scope="module")
def pool():
    """Unrelated 60 nt windows (what the pipeline draws from the host transcriptome)."""
    import random

    rng = random.Random(3)
    return tuple("".join(rng.choice("ACGU") for _ in range(60)) for _ in range(16))


@pytest.fixture(scope="module")
def triggers():
    return _trigger("trig-1", WINDOW_A, 67), _trigger("trig-2", WINDOW_B, 268)


@pytest.fixture(scope="module")
def constraints():
    return Constraints(max_triggers=2, standard=AssemblyStandard.NONE, max_switch_length=300)


@pytest.fixture(scope="module")
def gate(folder, pool):
    host = Host.HUMAN
    return EukaryoticToeholdAndGate(
        host,
        folder,
        TranslationScorer(host),
        CodonOptimizer(host, folder=folder, seed=1),
        settings=FAST,
        control_pool=pool,
        seed=1,
    )


@pytest.fixture(scope="module")
def designs(gate, triggers, constraints):
    return list(gate.generate_designs(TriggerSet(activators=triggers), constraints))


# --- The family declares itself honestly --------------------------------------------------------


def test_the_family_redeclares_what_a_stub_parent_would_have_inherited(gate):
    """``ToeholdAndGate`` carries ``version='0.1.0-stub'``; a built family must not."""
    assert "stub" not in gate.version
    assert gate.version != ToeholdAndGate.version
    assert gate.available is True
    assert gate.max_inputs == 2
    assert gate.supported_hosts == frozenset({Host.HUMAN, Host.YEAST})


def test_only_the_trailing_kozak_layout_is_built(gate):
    """The fused construct drops the first hairpin's Kozak, which only this layout can do."""
    assert gate.kozak_layouts == ("trailing",)


# --- Compatibility is cheap, specific and shown to the researcher -------------------------------


def test_one_trigger_is_not_an_and(gate, triggers, constraints):
    result = gate.is_compatible(TriggerSet(activators=triggers[:1]), constraints)

    assert not result.ok
    assert "exactly 2 activating input" in result.reason


def test_two_near_identical_triggers_are_refused_with_the_reason(gate, triggers, constraints):
    twin = dataclasses.replace(triggers[0], trigger_id="trig-3", start_index=70)

    result = gate.is_compatible(TriggerSet(activators=(triggers[0], twin)), constraints)

    assert not result.ok
    assert "cross-talk" in result.reason and "trig-3" in result.reason


def test_a_pair_outside_the_chosen_genes_is_refused(folder, pool, triggers, constraints):
    host = Host.HUMAN
    gate = EukaryoticToeholdAndGate(
        host,
        folder,
        TranslationScorer(host),
        CodonOptimizer(host, folder=folder, seed=1),
        settings=FAST,
        control_pool=pool,
        gene_pair=("GENE_A", "GENE_B"),
        seed=1,
    )

    stranger = (_trigger("t1", WINDOW_A, 1, "GENE_A"), _trigger("t2", WINDOW_B, 300, "GENE_C"))
    chosen = (_trigger("t1", WINDOW_A, 1, "GENE_A"), _trigger("t2", WINDOW_B, 300, "GENE_B"))

    assert not gate.is_compatible(TriggerSet(activators=stranger), constraints).ok
    assert gate.is_compatible(TriggerSet(activators=chosen), constraints).ok


# --- Generation: every coordinate is checked, nothing is silently dropped -----------------------


def test_every_design_is_a_valid_fused_switch(designs, folder, constraints):
    validator = SwitchValidator(
        folder, MotifScreener(AssemblyStandard.NONE), TranslationScorer(Host.HUMAN), constraints
    )

    assert len(designs) == 2 * FAST.singles_per_trigger**2 * 2  # both orders x both spacer variants
    assert {d.architecture["and"]["spacer"]["variant"] for d in designs} == {"no_spacer", "spacer"}
    for design in designs:
        assert validator.validate(design).ok, design.design_id
        assert design.sequence.count("AUG") == 1  # the payload's start codon only
        assert len(design.dot_bracket) == len(design.sequence)


def test_each_hairpin_sits_where_its_domains_say_it_does(designs):
    """The off-by-one that still folds: slice the fused RNA by the recorded domains and check the
    toehold and ascending stem really are the reverse complement of that hairpin's own trigger."""
    for design in designs:
        first, second = design.trigger_set.activators
        domains = design.architecture["and"]
        for hairpin, trigger in (("hairpin_a", first), ("hairpin_b", second)):
            spans = domains[hairpin]["domains"]
            footprint = design.sequence[spans["toehold"][0] : spans["stem_up"][1]]
            assert footprint == sq.reverse_complement(trigger.sequence)[: len(footprint)]
            stem_up = design.sequence[spans["stem_up"][0] : spans["stem_up"][1]]
            stem_down = design.sequence[spans["stem_down"][0] : spans["stem_down"][1]]
            assert stem_down == sq.reverse_complement(stem_up)
        spacer = domains["spacer"]
        assert design.sequence[spacer["span"][0] : spacer["span"][1]] == spacer["sequence"]


def test_the_start_codon_the_plasmid_builder_reads_is_the_second_hairpins(designs):
    for design in designs:
        aug = design.architecture["aug_index"]
        assert design.sequence[aug : aug + 3] == "AUG"
        assert aug == len(design.sequence) - 3 - design.architecture["payload_head_length"]


def test_designs_come_best_first_so_a_budget_keeps_the_most_promising(designs):
    screens = [
        (d.architecture["and"]["hairpin_a"]["screen_score_pct"] or 0)
        + (d.architecture["and"]["hairpin_b"]["screen_score_pct"] or 0)
        for d in designs
    ]
    assert screens == sorted(screens, reverse=True)


def test_generation_is_deterministic(gate, triggers, constraints, designs):
    again = list(gate.generate_designs(TriggerSet(activators=triggers), constraints))

    assert [d.design_id for d in again] == [d.design_id for d in designs]
    assert [d.sequence for d in again] == [d.sequence for d in designs]


# --- Evaluation: raw metrics under the profile's own names --------------------------------------


@pytest.fixture(scope="module")
def evaluated(gate, designs):
    design = designs[0]
    return design, gate.evaluate_design(design), gate.diagnostics(design)


def test_only_the_profiles_metric_names_are_emitted_in_their_units(evaluated):
    _design, metrics, _diag = evaluated

    assert set(metrics) <= {m.name for m in DEFAULT_V1.metrics}
    assert 0.0 <= metrics["predicted_leakage"] <= 1.0  # a fraction, not a percent
    assert 0.0 <= metrics["gc_content"] <= 100.0  # a percent, not a fraction
    assert metrics["dynamic_range"] >= 1.0  # a linear fold, floored by the OFF floor
    # kcal/mol, the raw MFE. Two stable hairpins lie below the profile's -60 floor (about -80),
    # where the normalised score saturates at its best for every AND candidate: it does not
    # discriminate between them. Reported honestly rather than rescaled (a profile decision).
    assert metrics["gate_folding_energy"] < -60.0
    assert metrics["circuit_complexity"] == 3.0  # two inputs and the gate
    assert "orthogonality" not in metrics  # not measurable for a single gate: absent, never 0.0


def test_the_metrics_follow_from_the_diagnostics(evaluated):
    """One measurement, one number: the metrics are read off the diagnostics, not recomputed."""
    _design, metrics, diag = evaluated

    assert metrics["predicted_leakage"] == pytest.approx(diag["off_pct"] / 100)
    floor = FAST.off_floor_pct
    assert metrics["dynamic_range"] == pytest.approx(diag["on_pct"] / max(diag["off_pct"], floor))
    assert diag["on_minus_off_pp"] == pytest.approx(diag["on_pct"] - diag["off_pct"])


def test_off_is_the_worst_of_the_states_that_should_stay_shut(evaluated):
    _design, _metrics, diag = evaluated

    assert diag["off_pct"] == pytest.approx(max(diag["off_terms_pct"].values()))
    assert diag["off_source"] in diag["off_terms_pct"]
    assert set(diag["off_terms_pct"]) <= {"alone", "+A", "+B", "control"}


def test_every_state_reports_its_sampler_check(evaluated):
    _design, _metrics, diag = evaluated

    assert set(diag["states"]) == {"alone", "+A", "+B", "+A+B"}
    for state in diag["states"].values():
        assert isinstance(state["verified"], bool)
        assert state["draws"] == FAST.n_samples
    assert diag["evaluated_nt"] <= len(evaluated[0].sequence) + diag["payload_head_nt"]


def test_controls_are_matrix_upper_bounds_unless_sampling_them_is_asked_for(evaluated):
    _design, _metrics, diag = evaluated

    assert diag["controls"]["mode"] == "exact_matrix_upper_bound"
    assert diag["controls"]["found"] == FAST.n_controls


def test_the_same_design_evaluates_to_the_same_numbers(gate, designs, evaluated):
    _design, metrics, diag = evaluated

    assert gate.evaluate_design(designs[0]) == metrics
    assert gate.diagnostics(designs[0])["on_pct"] == diag["on_pct"]


def test_a_measurement_that_could_not_be_made_is_none_never_zero(
    folder, pool, designs, monkeypatch
):
    """No structures drawn for a required state: ON and OFF are unmeasured, and so is everything
    derived from them. A 0.0 here would normalise to a *perfect* leakage and outrank real ones."""
    host = Host.HUMAN
    gate = EukaryoticToeholdAndGate(
        host,
        folder,
        TranslationScorer(host),
        CodonOptimizer(host, folder=folder, seed=1),
        settings=FAST,
        control_pool=pool,
        seed=1,
    )
    monkeypatch.setattr(folder, "sample_structures", lambda *args, **kwargs: [])

    metrics = gate.evaluate_design(designs[0])
    diag = gate.diagnostics(designs[0])

    assert metrics["predicted_leakage"] is None
    assert metrics["dynamic_range"] is None
    assert metrics["state_separation"] is None
    assert diag["on_pct"] is None and diag["off_pct"] is None
    assert any("could not be measured" in w for w in diag["warnings"])
    assert all(state["verified"] is False for state in diag["states"].values())


def test_controls_never_resemble_the_real_triggers_and_are_never_padded(gate, triggers):
    pairs = gate._control_pairs(*triggers)

    assert 0 < len(pairs) <= FAST.n_controls
    for control_a, control_b in pairs:
        assert len(control_a) == len(triggers[0].sequence)
        for control in (control_a, control_b):
            for real in triggers:
                assert so.longest_identity_run(control, real.sequence) <= FAST.max_overlap_nt
    assert gate._control_pairs(*triggers) == pairs  # deterministic in the seed

    empty = EukaryoticToeholdAndGate(
        Host.HUMAN, gate.folder, gate.translation, gate.codons, settings=FAST, seed=1
    )
    assert empty._control_pairs(*triggers) == []  # no pool: none found, not invented


# --- The settings: every tunable is declared and validated --------------------------------------


def test_defaults_are_the_notebooks():
    settings = AndGateSettings()

    assert (settings.n_samples, settings.n_controls) == (2000, 5)
    assert (settings.max_overlap_nt, settings.wobble_max_fraction) == (8, 0.5)
    assert (settings.spacer_min_length, settings.spacer_max_length) == (15, 20)
    assert settings.verify_sigma == 4.0 and settings.verify_floor_nt == 0.02
    assert settings.controls_sampled is False and settings.noise_check is True


@pytest.mark.parametrize(
    "mapping, field",
    [
        ({"n_samples": 5}, "n_samples"),
        ({"n_samples": True}, "n_samples"),
        ({"n_controls": -1}, "n_controls"),
        ({"wobble_max_fraction": 2}, "wobble_max_fraction"),
        ({"controls_sampled": "yes"}, "controls_sampled"),
        ({"spacer_variants": ["no_spacer", "no_spacer"]}, "spacer_variants"),
        ({"spacer_variants": ["both"]}, "spacer_variants"),
        ({"spacer_min_length": 30, "spacer_max_length": 20}, "spacer_max_length"),
        ({"n_samples": 500, "screen_samples": 900}, "screen_samples"),
        ({"windows_per_gene": 0}, "windows_per_gene"),
        ({"colour": "red"}, "colour"),
    ],
)
def test_invalid_settings_are_rejected_naming_the_field(mapping, field):
    with pytest.raises(ValueError, match=field):
        AndGateSettings.from_mapping(mapping)


def test_settings_round_trip_through_json_types():
    settings = AndGateSettings.from_mapping({"n_samples": 400, "spacer_variants": ["spacer"]})

    assert AndGateSettings.from_mapping(settings.to_dict()) == settings


# --- The shared tool ----------------------------------------------------------------------------


def test_open_counts_reads_the_stem_from_the_structure():
    """stem_up is positions 0-3 and stem_down 8-11; open means not paired to stem_down."""
    closed = "((((....))))"
    one_open = "(.((.....)))"  # position 1 unpaired, stem_down position 8 unpaired
    paired_elsewhere = ".....((..))."  # stem_up pairs with nothing in stem_down
    assert so.open_counts(closed, (0, 4), (8, 12)) == (0, 0)
    assert so.open_counts(one_open, (0, 4), (8, 12)) == (1, 1)
    assert so.open_counts(paired_elsewhere, (0, 4), (8, 12)) == (4, 4)
    # A run is consecutive: two separate open nucleotides are two runs of one, not a run of two.
    two_runs = "(.(.....)..)"  # positions 1 and 3 open, separated by the paired position 2
    assert so.open_counts(two_runs, (0, 4), (8, 12)) == (2, 1)


def test_a_measured_zero_spread_is_a_real_value_not_a_missing_one():
    """Treating sd = 0 as missing widened the tolerance from 0.02 nt to over 0.5 nt."""
    measured = so.verification_tolerance(0.0, 100, default_sd=9.0, sigma=4.0, floor_nt=0.02)
    missing = so.verification_tolerance(None, 100, default_sd=9.0, sigma=4.0, floor_nt=0.02)

    assert measured == pytest.approx(0.02)
    assert missing == pytest.approx(4.0 * 9.0 / 10 + 0.02)


def test_fuse_refuses_a_design_that_lacks_the_domain_its_cut_needs():
    a = {"switch": "AAAA", "domains": {"prefix": (0, 2), "toehold": (2, 4)}, "line_no": "a"}
    built, problem = so.fuse(a, a, "kozak", "prefix", "")

    assert built is None and "no 'kozak' domain" in problem


def test_the_pair_screen_catches_identity_and_complementarity():
    a = "GAGGCUACGUUCAGCUAGCAUGCAUCGGAC"
    assert so.trigger_pair_too_similar(a, a, max_overlap_nt=8, wobble_max_fraction=0.5)  # same
    assert so.trigger_pair_too_similar(
        a, sq.reverse_complement(a), max_overlap_nt=8, wobble_max_fraction=0.5
    )  # pairs with itself
    assert not so.trigger_pair_too_similar(
        WINDOW_A, WINDOW_B, max_overlap_nt=8, wobble_max_fraction=0.5
    )


def test_the_seed_noise_percentile_ignores_unmeasured_changes():
    assert so.percentile_95([]) is None
    assert so.percentile_95([None, None]) is None
    assert so.percentile_95([0.1, -0.2, None, 0.05]) == pytest.approx(0.1)
