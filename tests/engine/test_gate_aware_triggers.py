"""Gate-aware RNAplfold trigger selection."""

import builtins
import math

import pytest

from engine.domain import AssemblyStandard, Constraints, FoldingConfig, Regulation, SelectedGene
from engine.gates.tools.folding import FoldEngine
from engine.stages import folding as folding_module
from engine.stages.folding import FoldProfiler
from engine.stages.motifs import MotifScreener
from engine.stages.triggers import TriggerScorer


class FakeRNA:
    __version__ = "2.7.2-test"
    OPTION_WINDOW = 16
    OPTION_PF = 2
    PROBS_WINDOW_UP = 8192
    ANY_LOOP = 15

    def __init__(self, monkeypatch, error=None, status=1, incomplete=False):
        self.calls = []
        self.compounds = []
        self.error = error
        self.status = status
        self.incomplete = incomplete
        monkeypatch.setattr(folding_module, "configured_compound", self.compound)
        monkeypatch.setattr(
            folding_module,
            "folding_provenance",
            lambda config, **kwargs: {"temperature_celsius": config.temperature_celsius, **kwargs},
        )

    def compound(self, sequence, config, *, window_size, max_bp_span, options):
        self.compounds.append((sequence, config, window_size, max_bp_span, options))
        rna = self

        class Compound:
            def probs_window(self, unpaired, options, callback):
                rna.calls.append((sequence, unpaired, window_size, max_bp_span))
                assert options == rna.PROBS_WINDOW_UP
                if rna.error:
                    raise rna.error
                for end in range(1, len(sequence) + 1 - int(rna.incomplete)):
                    size = min(end, unpaired)
                    row = [None] + [end * 100 + length for length in range(1, size + 1)]
                    row.extend([None] * (unpaired - size))
                    callback(row, size, end, unpaired, rna.PROBS_WINDOW_UP | rna.ANY_LOOP, None)
                return rna.status

        return Compound()


def test_rnaplfold_table_is_read_by_interval_end_and_length(monkeypatch):
    rna = FakeRNA(monkeypatch)
    profiler = FoldProfiler(rna_module=rna)

    assert profiler.profile("A" * 25)[0] == 101
    assert profiler.joint_probability("A" * 25, 2, 10) == 1008


def test_benchmark_parameters_are_clamped_per_sequence_and_recorded(monkeypatch):
    rna = FakeRNA(monkeypatch)
    profiler = FoldProfiler(rna_module=rna)

    profiler.profile("A" * 12)

    assert rna.calls == [("A" * 12, 12, 12, 12)]
    assert profiler.provenance("A" * 12) == {
        "tool": "RNAplfold",
        "viennarna_version": "2.7.2-test",
        "window": 12,
        "max_span": 12,
        "unpaired": 12,
        "temperature_celsius": 37.0,
        "folding_model": {
            "temperature_celsius": 37.0,
            "window_size": 12,
            "max_bp_span": 12,
        },
    }


def test_real_rnaplfold_computation_errors_fail_closed(monkeypatch):
    profiler = FoldProfiler(rna_module=FakeRNA(monkeypatch, RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        profiler.profile("A" * 30)


@pytest.mark.parametrize("failure", [{"status": 0}, {"incomplete": True}])
def test_rnaplfold_missing_probability_data_fails_closed(monkeypatch, failure):
    profiler = FoldProfiler(rna_module=FakeRNA(monkeypatch, **failure))
    with pytest.raises(RuntimeError, match="RNAplfold"):
        profiler.profile("A" * 30)


def test_rnaplfold_passes_immutable_model_to_compound(monkeypatch):
    rna = FakeRNA(monkeypatch)
    config = FoldingConfig(temperature_celsius=25.0, no_gu=True)
    profiler = FoldProfiler(config=config, rna_module=rna)
    profiler.profile("A" * 30)
    profiler.profile("A" * 30)

    assert profiler.config is config
    assert profiler.temperature_celsius == 25.0
    assert rna.compounds == [("A" * 30, config, 30, 30, rna.OPTION_WINDOW | rna.OPTION_PF)]
    assert profiler.provenance("A" * 30)["temperature_celsius"] == 25.0
    with pytest.raises(AttributeError):
        profiler.config = FoldingConfig()


def test_only_missing_viennarna_is_marked_unavailable():
    profiler = FoldProfiler(rna_module=None)
    assert profiler.available is False
    with pytest.raises(RuntimeError, match="ViennaRNA"):
        profiler.profile("A" * 30)


def test_rna_loader_marks_only_the_exact_missing_rna_module_unavailable(monkeypatch):
    error = ModuleNotFoundError("No module named 'RNA'", name="RNA")

    real_import = builtins.__import__

    def missing_rna(name, *args, **kwargs):
        if name == "RNA":
            raise error
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_rna)
    assert folding_module._load_rna() is None


@pytest.mark.parametrize(
    "error",
    [
        ModuleNotFoundError("No module named 'numpy'", name="numpy"),
        ImportError("libRNA.so: cannot open shared object file"),
    ],
    ids=["nested-dependency", "broken-extension"],
)
def test_rna_loader_reraises_non_absence_import_failures(monkeypatch, error):
    real_import = builtins.__import__

    def broken_rna(name, *args, **kwargs):
        if name == "RNA":
            raise error
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_rna)
    with pytest.raises(type(error), match=str(error)):
        folding_module._load_rna()


class GateAwareProfiler:
    available = True

    def __init__(self, joint=None, marginal=0.4):
        self.joint = joint or {}
        self.marginal = marginal
        self.calls = []

    def profile(self, sequence):
        return [self.marginal] * len(sequence)

    def joint_probability(self, sequence, start, end):
        self.calls.append((start, end))
        return self.joint.get((start, end), 0.2)

    def provenance(self, sequence):
        return {
            "tool": "RNAplfold",
            "viennarna_version": "2.7.2-test",
            "window": min(len(sequence), 200),
            "max_span": min(len(sequence), 150),
            "unpaired": min(len(sequence), 20),
            "temperature_celsius": 37.0,
        }


def gene():
    return SelectedGene(
        gene_id="g", symbol="g", regulation=Regulation.UP, log2_fold_change=2.0, score=1.0
    )


def score_one(length, profiler, start_offset=0):
    transcript = "ACGU" * 30
    scorer = TriggerScorer(profiler, MotifScreener(AssemblyStandard.RFC10), FoldEngine())
    candidates = list(
        scorer.score(
            [gene()],
            {"g": transcript[start_offset : start_offset + length]},
            Constraints(trigger_lengths=(length,)),
        )
    )
    assert len(candidates) == 1
    return candidates[0]


@pytest.mark.parametrize(
    ("footprint", "toehold", "seed_count", "window_start", "toehold_start"),
    [(30, 12, 5, 10, 18), (33, 15, 8, 13, 18), (36, 18, 11, 16, 18)],
)
def test_exact_footprints_anchor_terminal_20_and_enumerate_contactable_seeds(
    footprint, toehold, seed_count, window_start, toehold_start
):
    profiler = GateAwareProfiler()
    candidate = score_one(footprint, profiler)

    assert candidate.gate_toehold_length == toehold
    assert (candidate.hypothesis_start, candidate.hypothesis_end) == (window_start, footprint)
    assert len(candidate.seed_trials) == seed_count
    assert [(trial.start, trial.end) for trial in candidate.seed_trials] == [
        (start, start + 8) for start in range(toehold_start, footprint - 7)
    ]
    assert all(len(trial.sequence) == 8 for trial in candidate.seed_trials)


def test_seed_selection_uses_joint_p8_and_earliest_start_tie_break():
    joint = {(18, 26): 0.8, (19, 27): 0.9, (20, 28): 0.9, (22, 30): 0.95}
    candidate = score_one(30, GateAwareProfiler(joint=joint))

    assert candidate.selected_seed_probability == pytest.approx(0.95)
    assert (candidate.selected_seed_start, candidate.selected_seed_end) == (22, 30)
    tie = score_one(30, GateAwareProfiler(joint={(18, 26): 0.9, (19, 27): 0.9}))
    assert tie.selected_seed_start == 18
    assert [trial.probability for trial in tie.seed_trials[:2]] == [0.9, 0.9]


def test_joint_metrics_are_not_products_of_marginals_and_delta_g_uses_floor():
    p20 = 1e-30
    profiler = GateAwareProfiler(joint={(10, 30): p20, (18, 26): 0.7}, marginal=0.5)
    candidate = score_one(30, profiler)

    expected = (
        -TriggerScorer.GAS_CONSTANT_KCAL_PER_MOL_K
        * TriggerScorer.TEMPERATURE_K
        * math.log(TriggerScorer.PU_FLOOR)
        / 20
    )
    assert candidate.joint_open_probability_20 == p20
    assert candidate.mean_marginal_openness_20 == pytest.approx(0.5)
    assert candidate.selected_seed_probability == pytest.approx(0.7)
    assert candidate.selected_seed_probability != pytest.approx(0.5**8)
    assert candidate.delta_g_open_kcal_per_mol_per_nt == pytest.approx(expected)


def test_top_k_round_robin_preserves_every_footprint_bucket(monkeypatch):
    monkeypatch.setattr(TriggerScorer, "TOP_K_PER_GENE", 3)
    transcript = "ACGU" * 20
    scorer = TriggerScorer(GateAwareProfiler(), MotifScreener(), FoldEngine())

    candidates = list(
        scorer.score([gene()], {"g": transcript}, Constraints(trigger_lengths=(30, 33, 36)))
    )

    assert [candidate.length for candidate in candidates] == [30, 33, 36]


def test_default_trigger_lengths_cover_every_exact_toehold_footprint():
    assert Constraints().trigger_lengths == (30, 33, 36)


def test_coordinates_remain_absolute_for_nonzero_candidate_start():
    transcript = "ACGU" * 10
    scorer = TriggerScorer(GateAwareProfiler(), MotifScreener(), FoldEngine())
    candidates = list(scorer.score([gene()], {"g": transcript}, Constraints(trigger_lengths=(30,))))
    candidate = next(item for item in candidates if item.start_index == 7)
    assert (candidate.hypothesis_start, candidate.hypothesis_end) == (17, 37)
    assert [(trial.start, trial.end, trial.relative_start) for trial in candidate.seed_trials] == [
        (start, start + 8, start - 25) for start in range(25, 30)
    ]


def test_primary_joint_p8_orders_candidates_within_one_bucket():
    transcript = "ACGU" * 8
    profiler = GateAwareProfiler(joint={(18, 26): 0.9, (23, 31): 0.8})
    scorer = TriggerScorer(profiler, MotifScreener(), FoldEngine())
    candidates = list(scorer.score([gene()], {"g": transcript}, Constraints(trigger_lengths=(30,))))
    assert candidates[0].start_index == 0
    assert candidates[0].selected_seed_probability == pytest.approx(0.9)


def test_marginal_only_profiler_uses_documented_legacy_fallback():
    class MarginalOnly:
        def profile(self, sequence):
            return [0.25] * len(sequence)

    candidate = score_one(30, MarginalOnly())
    assert candidate.gate_toehold_length is None
    assert candidate.score == candidate.openness == pytest.approx(0.25)


@pytest.mark.parametrize("lengths", [(31,), (30, 31, 33)])
def test_joint_capable_scorer_rejects_non_exact_footprints(lengths):
    scorer = TriggerScorer(GateAwareProfiler(), MotifScreener(), FoldEngine())
    with pytest.raises(ValueError, match=r"30, 33, and 36"):
        list(scorer.score([gene()], {"g": "ACGU" * 20}, Constraints(trigger_lengths=lengths)))


def test_marginal_only_scorer_retains_arbitrary_length_compatibility():
    class MarginalOnly:
        def profile(self, sequence):
            return [0.25] * len(sequence)

    candidate = score_one(31, MarginalOnly())
    assert candidate.length == 31
    assert candidate.gate_toehold_length is None


def test_joint_probability_errors_are_not_downgraded_to_legacy_ranking():
    class ExplodingJoint(GateAwareProfiler):
        def joint_probability(self, sequence, start, end):
            raise RuntimeError("joint calculation failed")

    with pytest.raises(RuntimeError, match="joint calculation failed"):
        score_one(30, ExplodingJoint())


def test_max_span_is_also_clamped_to_the_effective_window(monkeypatch):
    rna = FakeRNA(monkeypatch)
    FoldProfiler(window=10, max_span=15, unpaired=8, rna_module=rna).profile("A" * 30)
    assert rna.calls == [("A" * 30, 8, 10, 10)]
