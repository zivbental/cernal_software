"""``TriggerScorer`` — stage 2, ranking candidate trigger windows within a transcript.

``FoldProfiler`` and ``OffTargetScanner`` are still stubs (``NotImplementedError``) —
see ``docs/ROADMAP.md`` E1 — so this file drives ``TriggerScorer`` against small, explicit
fakes for those two tools instead, in the spirit of ``gates/tools/folding.py``'s own "one
stub point for tests" note. ``MotifScreener`` and ``FoldEngine`` are real: both are
already implemented, and the whole point of a golden test is to pin real numbers.
"""

import pytest

from engine.domain import (
    AssemblyStandard,
    Constraints,
    Hit,
    OffTargetReport,
    Regulation,
    SelectedGene,
)
from engine.gates.tools.folding import FoldEngine
from engine.stages.motifs import MotifScreener
from engine.stages.triggers import TriggerScorer

# 60 nt, deterministic, with an AUG at 10 and an in-frame-with-nothing-in-particular
# stop a bit later — enough to exercise aug/stop index recording without relying on
# random generation.
TRANSCRIPT = "ACGUACGUAC" + "AUGGCUAGCU" + "ACGUACGUAC" + "UAAACGUACG" + "UACGUACGUA" + "CGUACGUACG"


class FakeFoldProfiler:
    """A deterministic stand-in for ``FoldProfiler``: alternating open/paired blocks of
    4 nt, so a window's mean and minimum unpaired probability are easy to hand-check."""

    def profile(self, sequence: str) -> list[float]:
        return [0.9 if (i // 4) % 2 == 0 else 0.1 for i in range(len(sequence))]


class FakeOffTargetScanner:
    """A stand-in for ``OffTargetScanner`` returning a fixed, non-zero penalty — enough
    to prove ``TriggerScorer`` reads it rather than inventing its own number."""

    def __init__(self, penalty: float = 0.2) -> None:
        self.penalty = penalty
        self.calls: list[str] = []

    def scan_trigger(self, trigger: str) -> OffTargetReport:
        self.calls.append(trigger)
        hits = (Hit(gene_id="other", start=0, mismatches=1, identity=0.9),) if self.penalty else ()
        return OffTargetReport(hits=hits, penalty=self.penalty)


def make_gene(**overrides) -> SelectedGene:
    defaults = {
        "gene_id": "b0002",
        "symbol": "thrA",
        "regulation": Regulation.UP,
        "log2_fold_change": 2.0,
        "p_adj": 0.01,
        "control_percentile": 10.0,
        "condition_percentile": 90.0,
        "condition_specificity": 0.8,
        "score": 0.9,
    }
    defaults.update(overrides)
    return SelectedGene(**defaults)


@pytest.fixture
def scorer() -> TriggerScorer:
    return TriggerScorer(
        FakeFoldProfiler(),
        FakeOffTargetScanner(),
        MotifScreener(AssemblyStandard.RFC10),
        FoldEngine(),
    )


@pytest.fixture
def genes() -> list[SelectedGene]:
    return [make_gene()]


@pytest.fixture
def sequences() -> dict[str, str]:
    return {"b0002": TRANSCRIPT}


# --- windowing and pruning ----------------------------------------------------------


def test_scans_every_window_of_every_configured_length(scorer, genes, sequences):
    constraints = Constraints(trigger_lengths=(30,))
    candidates = list(scorer.score(genes, sequences, constraints))
    # A dense (step=1) scan of a 60 nt transcript with a 30 nt window has 31 positions;
    # nothing here should be screened out (no restriction sites, no long homopolymers).
    assert len(candidates) == 31
    assert sorted(c.start_index for c in candidates) == list(range(31))


def test_multiple_trigger_lengths_are_all_scanned(scorer, genes, sequences):
    constraints = Constraints(trigger_lengths=(20, 30))
    candidates = list(scorer.score(genes, sequences, constraints))
    lengths = {len(c.sequence) for c in candidates}
    assert lengths == {20, 30}


def test_top_k_per_gene_caps_the_yield(scorer, genes, sequences, monkeypatch):
    monkeypatch.setattr(TriggerScorer, "TOP_K_PER_GENE", 5)
    constraints = Constraints(trigger_lengths=(30,))
    candidates = list(scorer.score(genes, sequences, constraints))
    assert len(candidates) == 5


def test_each_gene_is_pruned_independently(sequences, monkeypatch):
    """A second, more open gene must not starve the first one's budget — the docstring's
    whole reason for pruning per gene rather than by one global threshold."""
    scorer = TriggerScorer(
        FakeFoldProfiler(),
        FakeOffTargetScanner(),
        MotifScreener(AssemblyStandard.RFC10),
        FoldEngine(),
    )
    monkeypatch.setattr(TriggerScorer, "TOP_K_PER_GENE", 5)
    genes = [make_gene(gene_id="b0002", symbol="thrA"), make_gene(gene_id="b0114", symbol="aceE")]
    seqs = {"b0002": TRANSCRIPT, "b0114": TRANSCRIPT}
    constraints = Constraints(trigger_lengths=(30,))
    candidates = list(scorer.score(genes, seqs, constraints))
    assert sum(c.gene_id == "b0002" for c in candidates) == 5
    assert sum(c.gene_id == "b0114" for c in candidates) == 5


# --- cheap filtering before expensive work -------------------------------------------


def test_windows_carrying_a_restriction_site_are_screened_out(scorer, genes):
    # EcoRI (GAAUUC) embedded in an otherwise clean transcript.
    transcript = "ACGU" * 5 + "GAAUUC" + "ACGU" * 5  # 46 nt
    constraints = Constraints(trigger_lengths=(10,))
    candidates = list(scorer.score(genes, {"b0002": transcript}, constraints))
    assert all("GAAUUC" not in c.sequence for c in candidates)
    total_possible = len(transcript) - 10 + 1
    assert len(candidates) < total_possible


def test_off_target_and_folding_are_never_called_for_a_screened_out_window():
    off_target = FakeOffTargetScanner()
    scorer = TriggerScorer(
        FakeFoldProfiler(), off_target, MotifScreener(AssemblyStandard.RFC10), FoldEngine()
    )
    transcript = "ACGU" * 5 + "GAAUUC" + "ACGU" * 5
    list(scorer.score([make_gene()], {"b0002": transcript}, Constraints(trigger_lengths=(10,))))
    assert not any("GAAUUC" in call for call in off_target.calls)


def test_the_transcript_is_profiled_once_per_gene_not_once_per_window():
    calls = []

    class CountingProfiler(FakeFoldProfiler):
        def profile(self, sequence):
            calls.append(sequence)
            return super().profile(sequence)

    scorer = TriggerScorer(
        CountingProfiler(),
        FakeOffTargetScanner(),
        MotifScreener(AssemblyStandard.RFC10),
        FoldEngine(),
    )
    constraints = Constraints(trigger_lengths=(20, 30))
    list(scorer.score([make_gene()], {"b0002": TRANSCRIPT}, constraints))
    # Once per gene, not once per (gene, length) or once per window.
    assert calls == [TRANSCRIPT]


# --- per-window measurements ----------------------------------------------------------


def test_openness_is_the_mean_and_accessibility_is_the_minimum_over_the_window(
    scorer, genes, sequences
):
    constraints = Constraints(trigger_lengths=(8,))
    candidates = {c.start_index: c for c in scorer.score(genes, sequences, constraints)}
    # FakeFoldProfiler: positions 0-3 open (0.9), 4-7 paired (0.1). A window starting at
    # 0 covers both blocks evenly: mean 0.5, minimum 0.1 (the worst position, not
    # averaged away).
    candidate = candidates[0]
    assert candidate.openness == pytest.approx(0.5)
    assert candidate.accessibility == pytest.approx(0.1)


def test_off_target_penalty_is_read_from_the_scanner_not_invented(genes, sequences):
    off_target = FakeOffTargetScanner(penalty=0.37)
    scorer = TriggerScorer(
        FakeFoldProfiler(), off_target, MotifScreener(AssemblyStandard.RFC10), FoldEngine()
    )
    constraints = Constraints(trigger_lengths=(30,))
    candidates = list(scorer.score(genes, sequences, constraints))
    assert all(c.off_target_penalty == pytest.approx(0.37) for c in candidates)


def test_aug_and_stop_indexes_are_recorded(scorer, genes, sequences):
    constraints = Constraints(trigger_lengths=(30,))
    candidates = {c.start_index: c for c in scorer.score(genes, sequences, constraints)}
    # TRANSCRIPT[10:20] == "AUGGCUAGCU": a window starting at 10 sees an AUG at its own
    # position 0.
    assert 0 in candidates[10].aug_indexes
    # TRANSCRIPT[30:40] == "UAAACGUACG": a window starting at 30 sees an in-frame stop
    # at its own position 0.
    assert 0 in candidates[30].stop_indexes


def test_mfe_is_the_windows_own_folding_energy_not_a_sentinel(scorer, genes, sequences):
    """`mfe` is a required, non-optional field — a failure here cannot fall back to a
    sentinel like 0.0 (CLAUDE.md §3), and the real FoldEngine never fails on valid RNA,
    so every candidate must carry a genuine, non-zero energy."""
    constraints = Constraints(trigger_lengths=(30,))
    candidates = list(scorer.score(genes, sequences, constraints))
    assert all(c.mfe < 0.0 for c in candidates)


def test_score_ranks_the_more_accessible_less_off_target_window_first(sequences):
    """Not a golden pin on the exact formula (flagged as an open question in the PR) —
    just the ordering property any reasonable combination must have."""
    scorer = TriggerScorer(
        FakeFoldProfiler(),
        FakeOffTargetScanner(penalty=0.0),
        MotifScreener(AssemblyStandard.RFC10),
        FoldEngine(),
    )
    # 4 nt windows line up exactly with FakeFoldProfiler's 4 nt blocks, so a window
    # is either fully open (min 0.9) or fully paired (min 0.1) — a clean contrast.
    constraints = Constraints(trigger_lengths=(4,))
    candidates = list(scorer.score([make_gene()], sequences, constraints))
    assert candidates == sorted(candidates, key=lambda c: c.score, reverse=True)
    fully_open = next(c for c in candidates if c.start_index == 0)
    fully_paired = next(c for c in candidates if c.start_index == 4)
    assert fully_open.accessibility == pytest.approx(0.9)
    assert fully_paired.accessibility == pytest.approx(0.1)
    assert fully_open.score > fully_paired.score


# --- golden: fixed input, committed output (docs/engine.md §8) -------------------------


def test_golden_first_candidate_for_a_known_transcript(scorer, genes, sequences):
    """Pins the exact first-ranked candidate for a known gene/transcript pair.

    A refactor that changes these numbers must be a deliberate, reviewed change.
    """
    constraints = Constraints(trigger_lengths=(30,))
    candidates = list(scorer.score(genes, sequences, constraints))
    best = candidates[0]

    assert best.trigger_id == "trig-b0002-0-30"
    assert best.gene_id == "b0002"
    assert best.start_index == 0
    assert best.sequence == TRANSCRIPT[0:30]
    assert best.openness == pytest.approx(0.5266666666666667)
    assert best.accessibility == pytest.approx(0.1)
    assert best.off_target_penalty == pytest.approx(0.2)
    assert best.segment_specificity == pytest.approx(0.8)
    assert best.score == pytest.approx(0.08)
