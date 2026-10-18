"""Bacterial AND application contracts; synthetic observables are explicitly test-only."""

import csv
import hashlib
import json
import math
from types import SimpleNamespace

import pytest

from engine import pipeline
from engine.client import LocalEngine, validate_job_configuration
from engine.contract import INPUT_DE, INPUT_DIRECT
from engine.domain import (
    Compatibility,
    Constraints,
    GateDesign,
    GateKind,
    Host,
    ProkaryoticAndSettings,
    TriggerCandidate,
    TriggerSet,
    ValidationResult,
)
from engine.errors import JobCancelled
from engine.gates.toehold import ProkaryoticToeholdAndGate, ToeholdAndGate
from engine.stages.switches import SwitchDesigner
from engine.stages.triggers import TriggerScorer


def params(**overrides):
    return {
        "constraints": {"max_triggers": 2, "max_circuit_gates": 1},
        "and_inputs": {"gene_a": "b3447", "gene_b": "b3846"},
        "prokaryotic_and": {
            "max_pairs": 2,
            "stems_per_pair": 1,
            "max_stem_assignments": 81,
            "max_attempts": 40,
        },
        "budget": {"max_designs": 2},
        **overrides,
    }


@pytest.mark.parametrize(
    "raw",
    [
        {"max_pairs": 0},
        {"max_stem_assignments": True},
        {"max_attempts": 10001},
        {"accessibility_percentile": float("nan")},
        {"on_ceiling": float("inf")},
        {"pair_selection": "random_without_seed"},
        {"kinetic_barrier": True},
    ],
)
def test_search_settings_reject_unbounded_or_unrecognised_work(raw):
    with pytest.raises(ValueError, match="prokaryotic_and"):
        ProkaryoticAndSettings.from_mapping(raw)


def test_bacterial_and_configuration_is_normalised_without_changing_eukaryotic_settings():
    config = validate_job_configuration(
        params(), ["prokaryotic_toehold_and"], "default", INPUT_DE, organism="ecoli"
    )
    assert config["prokaryotic_and"]["max_stem_assignments"] == 81
    assert config["prokaryotic_and"]["on_ceiling"] == 7.2
    assert "and_gate" not in config


@pytest.mark.parametrize("host", ["human", "yeast", "c_acnes"])
def test_bacterial_and_refuses_an_unreviewed_host(host):
    with pytest.raises(ValueError):
        validate_job_configuration(
            params(), ["prokaryotic_toehold_and"], "default", INPUT_DE, organism=host
        )


def test_bacterial_and_refuses_a_single_pasted_sequence():
    with pytest.raises(ValueError, match=r"differential|two input|input_mode"):
        validate_job_configuration(
            params(),
            ["prokaryotic_toehold_and"],
            "default",
            INPUT_DIRECT,
            trigger_sequence="ACGU" * 30,
            organism="ecoli",
        )


@pytest.fixture
def bacterial_request(make_request, tmp_path):
    content = (
        b"gene_id,base_expression,target_expression,log2fc,padj\n"
        b"b3447,1.0,8.0,3.0,0.001\n"
        b"b3846,1.0,6.0,2.585,0.002\n"
    )
    path = tmp_path / "bacterial-and.csv"
    path.write_bytes(content)

    def build(**overrides):
        return make_request(
            input_path=str(path),
            input_checksum=hashlib.sha256(content).hexdigest(),
            organism="ecoli",
            gate_families=["prokaryotic_toehold_and"],
            params=params(**overrides),
        )

    return build


@pytest.fixture
def synthetic_equilibrium(monkeypatch):
    """Fake expensive folds only; preserve real pairing, construction and all 22 checks."""
    seen = []
    mode = {"missing": False}

    def measure(self, design, **kwargs):
        seen.append((design, kwargs))
        raw = {
            name: threshold + 0.1 if comparison == ">" else threshold - 0.1
            for name, comparison, threshold in self.THRESHOLDS
        }
        for state, energy in (("00", 6.0), ("01", 5.0), ("10", 4.0), ("11", 1.0)):
            raw[f"dG_open_{state}"] = energy
            raw[f"P_open_{state}"] = math.exp(-energy / self.folder.rt)
        raw.update(gc_content=50.0, separation=3.0, barrier=None)
        if mode["missing"]:
            raw.pop("xstar_engA_10")
        if mode.get("full_failure") and design.architecture.get(
            "evaluation_context", ""
        ).startswith("full_"):
            raw["A_M_11"] = 0.1
        return raw

    monkeypatch.setattr(ToeholdAndGate, "measure_design", measure)
    monkeypatch.setattr(
        "engine.gates.tools.folding.FoldEngine.saddle",
        lambda *_: pytest.fail("An equilibrium application run must never request a barrier"),
    )
    # Reporting graphics are irrelevant to this application-contract test.
    monkeypatch.setattr(
        "engine.stages.reporting.ReportBuilder.build_result", lambda *args, **kwargs: None
    )
    return seen, mode


def test_two_gene_run_delivers_four_state_diagnostics_and_candidate_csv(
    bacterial_request, synthetic_equilibrium
):
    seen, _ = synthetic_equilibrium
    request = bacterial_request()
    result = LocalEngine().run(request, lambda *_: True)

    assert result.status == "succeeded", result.error
    assert result.candidates
    assert len(result.candidates) <= 2
    assert len(seen) == len(result.candidates)
    for candidate in result.candidates:
        assert candidate.logic_type == "AND"
        assert candidate.gate_family == "prokaryotic_toehold_and"
        assert {feature["gene_id"] for feature in candidate.triggers["features"]} == {
            "b3447",
            "b3846",
        }
        diagnostics = candidate.design["and_gate"]
        assert diagnostics["method"] == "prokaryotic_equilibrium"
        assert set(diagnostics["states"]) == {"00", "01", "10", "11"}
        assert diagnostics["worst_off_state"] == "10"
        assert diagnostics["feasibility"] == {"passed": 22, "total": 22, "violations": []}
        assert len(diagnostics["checks"]) == 22
        assert all(check["passed"] and check["measured"] for check in diagnostics["checks"])
        assert diagnostics["ranking_measures"]["denominator_floor"] is None
        assert diagnostics["ranking_profile"]["version"] == "v3-computational-proxies"
        assert diagnostics["barrier_computed"] is False
        assert candidate.rank is not None
    for design, kwargs in seen:
        assert kwargs.get("compute_barrier") is False
        assert design.architecture["evaluation_sequence"] == design.sequence
        assert design.architecture["evaluation_context"] == "switch_through_linker_excluding_output"
    with open(f"{request.output_dir}/candidates.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(result.candidates)
    with open(f"{request.output_dir}/and-candidates.json") as handle:
        exported = json.load(handle)
    assert exported["schema_version"] == "and-candidate-audit-v1"
    assert len(exported["candidates"]) == len(result.candidates)
    for row in exported["candidates"]:
        # Output is rank ordered; compare by ref rather than assuming result order.
        matched = next(c for c in result.candidates if c.ref == row["ref"])
        assert row["rank"] == matched.rank
        assert row["equilibrium"]["checks"] == matched.design["and_gate"]["checks"]
        assert row["metrics"][0]["raw_value"] == matched.metrics[0].raw_value
        assert matched.design["switch_sequence"] not in json.dumps(row)
        assert [feature["role"] for feature in row["inputs"]] == ["A", "B"]
        assert all(feature["length"] > 0 for feature in row["inputs"])
    assert "metric_state_separation" in rows[0]


def test_missing_structural_measurement_is_retained_as_rejected_without_rank(
    bacterial_request, synthetic_equilibrium
):
    _seen, mode = synthetic_equilibrium
    mode["missing"] = True
    result = LocalEngine().run(bacterial_request(), lambda *_: True)

    assert result.status == "succeeded", result.error
    assert result.candidates
    assert all(candidate.is_rejected and candidate.rank is None for candidate in result.candidates)
    assert all("xstar_engA_10" in candidate.rejection_reason for candidate in result.candidates)
    for candidate in result.candidates:
        check = next(
            c for c in candidate.design["and_gate"]["checks"] if c["observable"] == "xstar_engA_10"
        )
        assert check["value"] is None and not check["measured"] and not check["passed"]


def test_output_length_does_not_change_the_declared_switch_folding_boundary(
    bacterial_request, synthetic_equilibrium
):
    seen, mode = synthetic_equilibrium
    mode["full_failure"] = True  # The retired full-CDS stage must never be called.
    result = LocalEngine().run(
        bacterial_request(payload={"outputs": ["gfp", "mcherry"]}), lambda *_: True
    )
    assert result.status == "succeeded", result.error
    assert result.candidates
    assert all(c.rank is not None for c in result.candidates)
    assert all(d.architecture["evaluation_sequence"] == d.sequence for d, _ in seen)
    assert "full_context" not in result.scientific_provenance["and_gate"]


def test_automatic_gene_pool_does_not_require_two_manually_picked_genes(
    bacterial_request, synthetic_equilibrium
):
    import dataclasses

    request = bacterial_request()
    request = dataclasses.replace(
        request, params={k: v for k, v in request.params.items() if k != "and_inputs"}
    )
    result = LocalEngine().run(request, lambda *_: True)
    assert result.status == "succeeded", result.error
    assert result.candidates
    assert result.scientific_provenance["and_gate"]["search"]["input_genes"] == 2


def test_time_budget_returns_a_reported_partial_search_instead_of_cancelling(
    bacterial_request, synthetic_equilibrium, monkeypatch
):
    ticks = iter((0.0, 2.0))
    monkeypatch.setattr(pipeline, "monotonic", lambda: next(ticks, 2.0))
    result = LocalEngine().run(
        bacterial_request(
            budget={"max_designs": 2, "max_runtime_seconds": 1, "on_exceed": "return_partial"}
        ),
        lambda *_: True,
    )
    assert result.status == "succeeded", result.error
    search = result.scientific_provenance["and_gate"]["search"]
    assert search["runtime_limit_reached"] is True
    assert search["accepted_candidates"] == 0
    assert any("time budget reached" in warning for warning in result.warnings)


def test_completed_candidates_survive_the_time_limit(
    bacterial_request, synthetic_equilibrium, monkeypatch
):
    seen, _mode = synthetic_equilibrium
    monkeypatch.setattr(pipeline, "monotonic", lambda: 2.0 if seen else 0.0)
    result = LocalEngine().run(
        bacterial_request(budget={"max_designs": 2, "max_runtime_seconds": 1}), lambda *_: True
    )
    assert result.status == "succeeded", result.error
    assert len(result.candidates) == 1
    assert result.candidates[0].rank == 1
    assert result.scientific_provenance["and_gate"]["search"]["runtime_limit_reached"] is True


def test_build_tools_uses_shared_folder_and_requested_reduced_search(
    bacterial_request,
):
    from engine.domain import Host

    tools = pipeline.build_tools(bacterial_request(), Host.ECOLI)
    family = next(f for f in tools["families"] if isinstance(f, ProkaryoticToeholdAndGate))
    assert family.folder is tools["folder"]
    assert family.compute_barrier is False
    assert family.upper3_levels == ("WWW_AUA",)
    assert family.strengthen_lower3_only is True
    assert len(list(family._axis_grid("chosen"))) == 10
    assert tools["constraints"].stem_order == "strong_lock_row"
    assert ProkaryoticAndSettings().stems_per_pair == 3


def pair_scorer_fixture():
    """Two compatible pairs whose window means and window minima order differently."""
    sequences = {"a": "ACGUACGU", "b": "UGCAUGCA"}
    profiles = {
        sequences["a"]: [0.9, 0.9, 0.1, 0.9, 0.9, 0.9, 0.2, 0.2],
        sequences["b"]: [0.4, 0.4, 0.8, 0.8, 0.8, 0.8, 0.2, 0.2],
    }
    profiler = SimpleNamespace(
        profile=lambda sequence: profiles[sequence],
        provenance=lambda _sequence: {"viennarna_version": "test-only"},
        window=200,
        max_span=150,
        unpaired=20,
        temperature_celsius=37.0,
    )
    pairs = [
        SimpleNamespace(
            gene_a="a", gene_b="b", len_x=4, window_a=lambda: (0, 2), window_b=lambda: (0, 2)
        ),
        SimpleNamespace(
            gene_a="a", gene_b="b", len_x=5, window_a=lambda: (2, 6), window_b=lambda: (2, 6)
        ),
    ]
    family = SimpleNamespace(
        geometry_name="test",
        SECONDARY_INVASION_LEN=2,
        TOEHOLD_B_LEN=2,
        find_cross_gene_pairs=lambda *_args, **_kwargs: iter(pairs),
        last_pair_search={"seed_matches_considered": 2, "discovery_truncated": False},
    )
    genes = [
        TriggerCandidate(gene, gene, gene.upper(), sequence, 0, 0.5, 0.1, -1.0, 50.0)
        for gene, sequence in sequences.items()
    ]
    scorer = TriggerScorer(
        profiler,
        SimpleNamespace(violations=lambda _sequence: ()),
        SimpleNamespace(mfe=lambda _sequence: SimpleNamespace(energy=-1.0)),
    )
    return scorer, genes, sequences, family


def test_pair_selection_uses_whole_compatible_pairs_and_preserves_distinct_minimum():
    scorer, genes, sequences, family = pair_scorer_fixture()
    plan, summary = scorer.compatible_pairs(
        genes, sequences, [family], ProkaryoticAndSettings(max_pairs=1), Constraints(), seed=7
    )
    assert summary["discovered_pairs"] == 2
    assert summary["selected_pairs"] == 1
    a, b = plan[0][1].activators
    assert (a.start_index, b.start_index) == (2, 2)
    assert a.openness == pytest.approx(0.7)
    assert a.accessibility == pytest.approx(0.1)
    # Independently taking A's most open window would have chosen position 0,
    # which is not the A window of this best compatible pair.
    assert min(a.openness, b.openness) == pytest.approx(0.7)


def test_seeded_pair_policy_is_reproducible_and_retains_the_declared_pool():
    scorer, genes, sequences, family = pair_scorer_fixture()
    settings = ProkaryoticAndSettings(
        max_pairs=1, pair_selection="percentile_sample", accessibility_percentile=0
    )
    first = scorer.compatible_pairs(genes, sequences, [family], settings, Constraints(), seed=17)
    second = scorer.compatible_pairs(genes, sequences, [family], settings, Constraints(), seed=17)
    assert first == second
    assert first[1]["eligible_pairs"] == 2
    assert first[1]["percentile_cutoff"] == pytest.approx(0.4)


def test_no_compatible_pairs_are_an_explicit_empty_search_outcome():
    scorer, genes, sequences, family = pair_scorer_fixture()
    family.find_cross_gene_pairs = lambda *_args, **_kwargs: iter(())
    plan, summary = scorer.compatible_pairs(
        genes, sequences, [family], ProkaryoticAndSettings(), Constraints(), seed=7
    )
    assert plan == []
    assert summary["discovered_pairs"] == summary["selected_pairs"] == 0
    assert summary["discovery_truncated"] is False


def test_overlap_at_an_upstream_region_edge_gets_complete_rescored_footprints():
    from engine import sequences as sq

    transcripts = {
        "a": "A" * 18 + "GCGC" + "A" * 14,
        "b": "U" * 14 + "GCGC" + "C" * 32,
    }
    # Each supplied region is just the four-base overlap, too short to be either
    # complete AND trigger. Both complete footprints extend outside those regions.
    windows = [
        TriggerCandidate(g, g, g, "GCGC", start, 0.99, 0.99, -1, 100, score=0.99)
        for g, start in (("a", 18), ("b", 14))
    ]
    probabilities = []

    def joint(_sequence, start, end):
        probabilities.append((start, end))
        return 0.6 if end - start == 8 else 0.2

    profiler = SimpleNamespace(
        profile=lambda sequence: [0.4] * len(sequence),
        joint_probability=joint,
        provenance=lambda _: {
            "temperature_celsius": 37.0,
            "viennarna_version": "test",
            "window": 200,
            "max_span": 150,
            "unpaired": 20,
        },
    )
    scorer = TriggerScorer(
        profiler,
        SimpleNamespace(violations=lambda _: ()),
        SimpleNamespace(mfe=lambda _: SimpleNamespace(energy=-1)),
    )
    family = object.__new__(ProkaryoticToeholdAndGate)
    family.should_stop = None
    plan, summary = scorer.compatible_pairs(
        windows, transcripts, [family], ProkaryoticAndSettings(), Constraints(), seed=7
    )
    assert len(plan) == 1
    a, b = plan[0][1].activators
    assert (a.sequence, b.sequence) == (transcripts["a"], transcripts["b"])
    assert (a.length, b.length) == (36, 50)
    assert a.openness == b.openness == pytest.approx(0.4)
    assert a.score == b.score == 0.6
    assert (a.gate_toehold_length, b.gate_toehold_length) == (18, 32)
    assert a.sequence[18:22] == sq.reverse_complement(b.sequence[14:18])
    assert probabilities and summary["rescored_footprints"] == 2
    # A complementary run elsewhere in the transcripts must not broaden discovery.
    unavailable = [
        TriggerCandidate(g, g, g, seq[:4], 0, 0.99, 0.99, -1, 50) for g, seq in transcripts.items()
    ]
    empty, _ = scorer.compatible_pairs(
        unavailable, transcripts, [family], ProkaryoticAndSettings(), Constraints(), seed=7
    )
    assert empty == []


def test_pair_planner_never_pairs_regions_from_one_gene():
    scorer, windows, transcripts, family = pair_scorer_fixture()
    plan, summary = scorer.compatible_pairs(
        windows[:1], transcripts, [family], ProkaryoticAndSettings(), Constraints(), seed=0
    )
    assert plan == []
    assert summary["input_genes"] == 1


def test_overlap_constraint_filters_before_top_pair_budget():
    scorer, genes, sequences, family = pair_scorer_fixture()
    plan, summary = scorer.compatible_pairs(
        genes,
        sequences,
        [family],
        ProkaryoticAndSettings(max_pairs=1),
        Constraints(overlap_range=(4, 4)),
        seed=7,
    )
    assert summary["screened_pairs"] == 1
    assert [candidate.start_index for candidate in plan[0][1].activators] == [0, 0]


def bounded_designer_fixture():
    triggers = [TriggerCandidate(str(i), "a", "A", "ACGU", i, 0.5, 0.5, -1.0, 50.0) for i in (0, 1)]
    plan = [("test", TriggerSet((trigger, trigger))) for trigger in triggers]

    def generate(group, _constraints, **_kwargs):
        for index in range(1000):
            yield GateDesign(
                f"{group.activators[0].trigger_id}:{index}",
                GateKind.TOEHOLD_AND,
                Host.ECOLI,
                group,
                "ACGU",
            )

    family = SimpleNamespace(
        geometry_name="test",
        is_compatible=lambda *_: Compatibility.yes(),
        generate_designs=generate,
    )
    validator = SimpleNamespace(validate=lambda _design: ValidationResult.failed("test invalid"))
    return SwitchDesigner([family], validator, Host.ECOLI), plan


def test_attempt_budget_bounds_invalid_designs_and_interleaves_pairs():
    designer, plan = bounded_designer_fixture()
    attempts = []
    result = list(
        designer.design_pairs(
            plan,
            Constraints(max_triggers=2),
            max_attempts=4,
            on_progress=lambda *_: True,
            on_attempt=lambda design, _validation: attempts.append(design.design_id),
            on_incompatible=lambda reason: pytest.fail(reason),
        )
    )
    assert result == []
    assert attempts == ["0:0", "1:0", "0:1", "1:1"]


def test_pair_generation_can_cancel_while_every_design_is_invalid():
    designer, plan = bounded_designer_fixture()
    attempts = []
    with pytest.raises(JobCancelled):
        list(
            designer.design_pairs(
                plan,
                Constraints(max_triggers=2),
                max_attempts=4,
                on_progress=lambda index, _total: index == 0,
                on_attempt=lambda design, _validation: attempts.append(design.design_id),
                on_incompatible=lambda reason: pytest.fail(reason),
            )
        )
    assert attempts == ["0:0"]


def test_real_historical_switch_only_example_passes_all_structural_checks(
    bacterial_request,
    monkeypatch,
):
    """A selected positive control verifies real folding, not general-policy yield."""
    import dataclasses

    from tools.pair_budget_on_pfas import historical_positive

    from engine.transcriptome import load_transcriptome

    tools = pipeline.build_tools(bacterial_request(), Host.ECOLI)
    family = next(f for f in tools["families"] if isinstance(f, ProkaryoticToeholdAndGate))
    book = load_transcriptome(Host.ECOLI)
    sources = {"ggt": book["b3447"], "astC": book["b1748"]}
    profiles = {name: tools["profiler"].profile(sequence) for name, sequence in sources.items()}
    design, _seconds = historical_positive(family, sources, profiles)
    evaluated = dataclasses.replace(
        design,
        architecture={
            **design.architecture,
            "evaluation_sequence": design.sequence,
        },
    )
    monkeypatch.setattr(tools["folder"], "saddle", lambda *_: pytest.fail("unexpected barrier"))
    raw = family.measure_design(evaluated, on_ceiling=7.2, compute_barrier=False)
    assert len(family.THRESHOLDS) == 22
    assert family.gate_violations(raw) == ()
    assert raw["barrier"] is None
    assert raw["P_open_11"] > max(raw[f"P_open_{state}"] for state in ("00", "01", "10"))
