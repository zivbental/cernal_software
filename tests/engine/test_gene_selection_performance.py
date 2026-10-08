"""Exact window screening parity and bounded work for stage-one gene selection."""

import random
from pathlib import Path

import pytest

from engine import sequences as sq
from engine.domain import AssemblyStandard, Constraints, Host
from engine.inputs import parse_dge_table
from engine.stages.genes import GeneSelector
from engine.stages.motifs import MotifScreener
from engine.transcriptome import load_transcriptome, resolve_gene_id


def reference_yield(selector, transcript):
    """Independent original rule: screen each complete window directly."""
    low, high = selector.constraints.trigger_gc_range
    scanned = surviving = 0
    for length in selector.constraints.trigger_lengths:
        for _, window in sq.windows(transcript, length):
            scanned += 1
            if selector.screener.violations(window):
                continue
            starts = len(sq.find_augs(window)) + len(sq.find_augs(sq.reverse_complement(window)))
            if starts:
                continue
            if low <= sq.gc_content(window) <= high:
                surviving += 1
    return (surviving / scanned, surviving) if scanned else (None, None)


class ReferenceSelector(GeneSelector):
    def _trigger_yield(self, transcript):
        return reference_yield(self, transcript)


@pytest.mark.parametrize("standard", list(AssemblyStandard))
@pytest.mark.parametrize("homopolymer", [1, 5, 9])
@pytest.mark.parametrize("gc_range", [(0, 100), (20, 80), (50, 50)])
def test_prefix_screen_matches_independent_window_rules(standard, homopolymer, gc_range):
    rng = random.Random(711)
    sequences = [
        "",
        "A",
        "A" * 90,
        "G" * 90,
        "ACGU" * 40,
        "AAUGCAUAAA",
        "ACGUGAAUUCACGUUCUGAGAACGUACUAGUACGUCUGCAGACGUGCGGCCGCACGU",
        "ACGUACGU" + "A" * 80 + "ACGUACGU",
        *["".join(rng.choices("ACGU", k=size)) for size in (2, 6, 29, 30, 31, 63, 200)],
    ]
    selector = GeneSelector(
        Constraints(trigger_lengths=(1, 2, 3, 5, 30, 33, 36), trigger_gc_range=gc_range),
        MotifScreener(standard, max_homopolymer=homopolymer, extra_motifs={"overlap": "ACAC"}),
    )
    for transcript in sequences:
        assert selector._trigger_yield(transcript) == reference_yield(selector, transcript)


def test_transcript_is_screened_once_instead_of_once_per_window(monkeypatch):
    screener = MotifScreener()
    selector = GeneSelector(Constraints(trigger_lengths=(30, 33, 36)), screener)
    calls = []
    original = screener.violations

    def count(sequence, **kwargs):
        calls.append(len(sequence))
        return original(sequence, **kwargs)

    monkeypatch.setattr(screener, "violations", count)
    transcript = "ACGU" * 1000
    actual = selector._trigger_yield(transcript)
    assert calls == [len(transcript)]
    assert actual == (1.0, sum(len(transcript) - length + 1 for length in (30, 33, 36)))


def test_custom_screener_retains_per_window_behavior():
    class CustomScreener(MotifScreener):
        def violations(self, sequence, **kwargs):
            return ("custom window rule",) if sequence.startswith("AC") else ()

    selector = GeneSelector(Constraints(trigger_lengths=(5,)), CustomScreener())
    transcript = "ACGU" * 20
    assert selector._trigger_yield(transcript) == reference_yield(selector, transcript)


def test_real_catalog_subset_preserves_selected_ranks_scores_and_yields():
    from dataclasses import replace

    catalog = Path(__file__).parents[2] / "src/apps/expression/catalog/ecoli/92117__44313016.csv"
    table = parse_dge_table(catalog.read_bytes(), catalog.name)
    rows = tuple(
        replace(row, gene_id=resolve_gene_id(Host.ECOLI, row.gene_id)) for row in table.rows[:40]
    )
    table = replace(table, rows=rows)
    transcriptome = load_transcriptome(Host.ECOLI)
    constraints = Constraints(max_genes=3)
    original_warnings = []
    actual_warnings = []
    original = ReferenceSelector(constraints, MotifScreener()).select(
        table, sequences=transcriptome, on_warning=original_warnings.append
    )
    actual = GeneSelector(constraints, MotifScreener()).select(
        table, sequences=transcriptome, on_warning=actual_warnings.append
    )
    assert actual == original
    assert actual_warnings == original_warnings
    assert original, "The reference catalog subset must exercise real selected genes."
