"""``GeneSelector`` — stage 1, gene selection (docs/genes.md).

The headline regression (``test_the_naive_top_of_fold_change_is_not_what_gets_selected``)
uses the real first 8 rows of ``E-CURD-149__g3_g1.csv`` — the exact worked example
docs/genes.md §1 measured a naive ``|log2FC|`` sort failing on. Everything else exercises
one axis at a time against small, hand-computed fixtures, in the spirit of
``test_triggers.py``'s own real-numbers-not-mocks-all-the-way-down style.
"""

from collections.abc import Callable

import pytest

from engine.domain import (
    Constraints,
    CountMatrix,
    DgeRow,
    DgeTable,
    Regulation,
    SampleMetadata,
    SelectedGene,
)
from engine.errors import InputValidationError
from engine.inputs import parse_dge_table
from engine.stages.genes import GeneSelector
from engine.stages.motifs import MotifScreener

# Same real E-CURD-149 rows as tests/engine/test_inputs.py — the naive top-8-by-|log2FC|
# example from docs/genes.md §1 (three pseudogene/unlabelled artifacts above the first
# real, significant gene).
E_CURD_149_HEAD = b"""gene_id,gene_symbol,log2fc,pvalue,padj
ENSG00000263503,MAPK8IP1P2,-23.1,0.00613402959179577,
ENSG00000280683,LINC01242,-21.8,0.062828360921023,
ENSG00000198744,MTCO3P12,-20.9,,
ENSG00000118113,MMP8,10.0,8.38041931778982e-08,
ENSG00000137869,CYP19A1,9.3,0.000157405572268537,
ENSG00000102837,OLFM4,9.1,8.40026345156656e-06,
ENSG00000163710,PCOLCE2,9.0,0.000157405572268537,
ENSG00000227292,,8.2,0.0019745406015627,
"""

# A clean, motif-free 60 nt transcript (reused from tests/engine/test_triggers.py) —
# has exactly one natural AUG, so some but not all windows of a scanned length survive
# the trigger-yield screen.
CLEAN_TRANSCRIPT = (
    "ACGUACGUAC" + "AUGGCUAGCU" + "ACGUACGUAC" + "UAAACGUACG" + "UACGUACGUA" + "CGUACGUACG"
)


def make_row(**overrides) -> DgeRow:
    defaults: dict = {
        "gene_id": "b0002",
        "log2_fold_change": 2.0,
        "symbol": "thrA",
        "p_adj": 0.01,
    }
    defaults.update(overrides)
    return DgeRow(**defaults)


def make_selector(
    constraints: Constraints | None = None,
    atlas: dict[str, float] | None = None,
) -> GeneSelector:
    return GeneSelector(constraints or Constraints(), MotifScreener(), atlas)


def make_counts(profiles: dict[str, tuple[list[float], list[float]]]) -> CountMatrix:
    """``profiles``: gene_id -> (control_values, condition_values), equal length."""
    gene_ids = tuple(profiles)
    n_control = len(next(iter(profiles.values()))[0])
    n_condition = len(next(iter(profiles.values()))[1])
    control_samples = tuple(f"c{i}" for i in range(1, n_control + 1))
    condition_samples = tuple(f"t{i}" for i in range(1, n_condition + 1))
    counts = tuple(tuple(profiles[g][0] + profiles[g][1]) for g in gene_ids)
    return CountMatrix(
        gene_ids=gene_ids,
        samples=control_samples + condition_samples,
        counts=counts,
        metadata=SampleMetadata(
            control_samples=control_samples, condition_samples=condition_samples
        ),
    )


def collect_warnings() -> tuple[list[str], Callable[[str], None]]:
    warnings: list[str] = []
    return warnings, warnings.append


# ---------------------------------------------------------------------------
# The headline regression
# ---------------------------------------------------------------------------


def test_the_naive_top_of_fold_change_is_not_what_gets_selected():
    """docs/genes.md §1: a plain sort on |log2FC| puts a pseudogene at an 8.9-million-
    fold change, a non-significant lncRNA, and a gene with no p-value at all above the
    first real, significant gene (MMP8). Selection must not reproduce that."""
    table = parse_dge_table(E_CURD_149_HEAD, "E-CURD-149.csv")
    # docs/genes.md §4.1's own recommended ceiling — an implausible fold change is
    # evidence of a near-zero denominator, not strong regulation.
    constraints = Constraints(max_separation=12.0, direction_balance=False, max_genes=10)
    warnings, on_warning = collect_warnings()

    selected = make_selector(constraints).select(table, on_warning=on_warning)
    selected_ids = {gene.gene_id for gene in selected}

    # The three artifacts never make the shortlist at all.
    assert "ENSG00000263503" not in selected_ids  # MAPK8IP1P2, -23.1, dropped by the ceiling
    assert "ENSG00000280683" not in selected_ids  # LINC01242, p=0.063 > 0.05
    assert "ENSG00000198744" not in selected_ids  # MTCO3P12, no p-value at all

    # The first real gene ranks first.
    assert selected[0].gene_id == "ENSG00000118113"  # MMP8
    assert selected[0].symbol == "MMP8"

    # And the degraded significance path is reported, not silent (raw p-value coverage
    # here is 7/8 = 87.5%, below the 95% bar for a computed FDR).
    assert any("not an FDR-controlled selection" in message for message in warnings)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_empty_table_raises():
    with pytest.raises(InputValidationError, match="no usable rows"):
        make_selector().select(DgeTable(rows=()))


def test_all_genes_missing_from_sequences_raises():
    table = DgeTable(rows=(make_row(gene_id="g1"), make_row(gene_id="g2", log2_fold_change=3.0)))
    with pytest.raises(InputValidationError, match="identifier namespace"):
        make_selector().select(table, sequences={"some-other-id": CLEAN_TRANSCRIPT})


# ---------------------------------------------------------------------------
# Significance tiers (docs/genes.md §4.1)
# ---------------------------------------------------------------------------


def test_no_pvalue_of_any_kind_still_selects_and_warns():
    table = DgeTable(
        rows=(
            make_row(gene_id="g1", log2_fold_change=3.0, p_adj=None),
            make_row(gene_id="g2", log2_fold_change=0.6, p_adj=None),
        )
    )
    warnings, on_warning = collect_warnings()
    selected = make_selector().select(table, on_warning=on_warning)

    assert {gene.gene_id for gene in selected} == {"g1", "g2"}
    assert all(gene.p_adj is None for gene in selected)
    assert any("significance was not assessed" in message for message in warnings)


def test_high_pvalue_coverage_computes_bh_and_records_it_as_padj():
    # 20 rows, all with a raw p-value (100% coverage >= the 95% bar) and no p_adj —
    # the shape of a table BH can legitimately be computed from.
    rows = [
        make_row(gene_id=f"g{i}", log2_fold_change=2.0, p_adj=None, p_value=0.001 if i < 5 else 0.9)
        for i in range(20)
    ]
    table = DgeTable(rows=tuple(rows))
    warnings, on_warning = collect_warnings()
    selected = make_selector().select(table, on_warning=on_warning)

    assert any("Benjamini-Hochberg" in message for message in warnings)
    # The five low-raw-p genes should survive with a real, computed q-value attached —
    # never the raw p-value passed through unlabelled as if it were already adjusted.
    selected_ids = {gene.gene_id for gene in selected}
    assert {"g0", "g1", "g2", "g3", "g4"} <= selected_ids
    for gene in selected:
        if gene.gene_id in {"g0", "g1", "g2", "g3", "g4"}:
            assert gene.p_adj is not None
            assert gene.p_adj != pytest.approx(0.001)  # a genuine BH q-value, not raw p


def test_low_pvalue_coverage_falls_back_to_raw_uncorrected():
    # Coverage well under 95% — BH cannot be trusted, so this must fall back to raw p.
    rows = [make_row(gene_id="g1", log2_fold_change=2.0, p_adj=None, p_value=0.01)]
    rows += [make_row(gene_id=f"g{i}", log2_fold_change=2.0, p_adj=None) for i in range(2, 12)]
    table = DgeTable(rows=tuple(rows))
    warnings, on_warning = collect_warnings()
    selected = make_selector().select(table, on_warning=on_warning)

    assert any("too incomplete to compute a valid FDR" in message for message in warnings)
    assert [gene.gene_id for gene in selected] == ["g1"]
    assert selected[0].p_adj is None  # raw p is never stored as an adjusted value


# ---------------------------------------------------------------------------
# Effect size floor and ceiling
# ---------------------------------------------------------------------------


def test_below_min_separation_is_dropped():
    table = DgeTable(rows=(make_row(gene_id="g1", log2_fold_change=0.1),))
    assert make_selector(Constraints(min_separation=0.5)).select(table) == []


def test_above_max_separation_is_dropped():
    table = DgeTable(
        rows=(
            make_row(gene_id="implausible", log2_fold_change=23.1, p_adj=0.001),
            make_row(gene_id="real", log2_fold_change=3.0, p_adj=0.001),
        )
    )
    selected = make_selector(Constraints(max_separation=12.0)).select(table)
    assert {gene.gene_id for gene in selected} == {"real"}


# ---------------------------------------------------------------------------
# Missing axes are None, never a fabricated number
# ---------------------------------------------------------------------------


def test_bare_table_leaves_every_optional_axis_none():
    table = DgeTable(rows=(make_row(gene_id="g1", log2_fold_change=3.0, p_adj=0.001),))
    gene = make_selector().select(table)[0]
    assert isinstance(gene, SelectedGene)
    assert gene.control_percentile is None
    assert gene.condition_percentile is None
    assert gene.condition_specificity is None
    assert gene.trigger_yield is None
    assert gene.usable_windows is None
    assert gene.score is not None and gene.score != 0.0  # separation alone still scores


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_shuffled_input_produces_an_identical_shortlist():
    rows = [
        make_row(gene_id=f"g{i}", log2_fold_change=1.0 + i * 0.1, p_adj=0.001) for i in range(10)
    ]
    forward = DgeTable(rows=tuple(rows))
    backward = DgeTable(rows=tuple(reversed(rows)))

    first = [g.gene_id for g in make_selector(Constraints(max_genes=5)).select(forward)]
    second = [g.gene_id for g in make_selector(Constraints(max_genes=5)).select(backward)]
    assert first == second


def test_duplicate_gene_id_keeps_first_and_warns():
    table = DgeTable(
        rows=(
            make_row(gene_id="g1", log2_fold_change=2.0, p_adj=0.001, symbol="first"),
            make_row(gene_id="g1", log2_fold_change=5.0, p_adj=0.001, symbol="second"),
        )
    )
    warnings, on_warning = collect_warnings()
    selected = make_selector().select(table, on_warning=on_warning)
    assert len(selected) == 1
    assert selected[0].symbol == "first"
    assert any("duplicate gene_id" in message for message in warnings)


# ---------------------------------------------------------------------------
# Abundance window (docs/genes.md §4.1's directional ON/OFF check)
# ---------------------------------------------------------------------------


def test_low_on_state_expression_is_dropped():
    # UP gene: ON state is the condition group.
    table = DgeTable(
        rows=(make_row(gene_id="g1", log2_fold_change=2.0, p_adj=0.001, target_mean=2.0),)
    )
    constraints = Constraints(min_base_expression=10.0)
    assert make_selector(constraints).select(table) == []


def test_leaky_off_state_expression_is_dropped():
    # UP gene: OFF state is the control group.
    table = DgeTable(
        rows=(make_row(gene_id="g1", log2_fold_change=2.0, p_adj=0.001, control_mean=500.0),)
    )
    constraints = Constraints(max_base_expression=50.0)
    assert make_selector(constraints).select(table) == []


def test_expression_within_the_window_passes():
    table = DgeTable(
        rows=(
            make_row(
                gene_id="g1",
                log2_fold_change=2.0,
                p_adj=0.001,
                control_mean=5.0,
                target_mean=50.0,
            ),
        )
    )
    constraints = Constraints(min_base_expression=10.0, max_base_expression=20.0)
    selected = make_selector(constraints).select(table)
    assert {g.gene_id for g in selected} == {"g1"}


# ---------------------------------------------------------------------------
# Trigger yield (docs/genes.md §4.2)
# ---------------------------------------------------------------------------


def test_zero_yield_gene_is_dropped_but_others_survive():
    table = DgeTable(
        rows=(
            make_row(gene_id="all-homopolymer", log2_fold_change=2.0, p_adj=0.001),
            make_row(gene_id="clean", log2_fold_change=2.0, p_adj=0.001),
        )
    )
    sequences = {
        "all-homopolymer": "A" * 30,  # every 10 nt window is one long homopolymer run
        "clean": CLEAN_TRANSCRIPT,
    }
    constraints = Constraints(trigger_lengths=(10,))
    warnings, on_warning = collect_warnings()
    selected = make_selector(constraints).select(table, sequences=sequences, on_warning=on_warning)

    selected_ids = {gene.gene_id for gene in selected}
    assert "all-homopolymer" not in selected_ids
    assert "clean" in selected_ids
    assert any("zero usable trigger windows" in message for message in warnings)

    clean_gene = next(g for g in selected if g.gene_id == "clean")
    assert clean_gene.trigger_yield is not None
    assert 0.0 < clean_gene.trigger_yield <= 1.0
    assert clean_gene.usable_windows and clean_gene.usable_windows > 0


def test_missing_sequence_is_dropped_and_reported_not_crashed():
    table = DgeTable(
        rows=(
            make_row(gene_id="has-sequence", log2_fold_change=2.0, p_adj=0.001),
            make_row(gene_id="no-sequence", log2_fold_change=2.0, p_adj=0.001),
        )
    )
    warnings, on_warning = collect_warnings()
    selected = make_selector().select(
        table, sequences={"has-sequence": CLEAN_TRANSCRIPT}, on_warning=on_warning
    )
    assert {g.gene_id for g in selected} == {"has-sequence"}
    assert any("no matching transcript sequence" in message for message in warnings)


# ---------------------------------------------------------------------------
# Condition specificity (needs an atlas)
# ---------------------------------------------------------------------------


def test_condition_specificity_uses_the_atlas_when_available():
    table = DgeTable(
        rows=(make_row(gene_id="g1", log2_fold_change=2.0, p_adj=0.001, target_mean=45.0),)
    )
    gene = make_selector(atlas={"g1": 5.0}).select(table)[0]
    assert gene.condition_specificity == pytest.approx(0.9)


def test_condition_specificity_is_none_without_an_atlas_entry():
    table = DgeTable(
        rows=(make_row(gene_id="g1", log2_fold_change=2.0, p_adj=0.001, target_mean=45.0),)
    )
    gene = make_selector(atlas={"some-other-gene": 5.0}).select(table)[0]
    assert gene.condition_specificity is None


# ---------------------------------------------------------------------------
# Non-redundancy (docs/genes.md §4.3)
# ---------------------------------------------------------------------------


def test_a_perfectly_redundant_gene_loses_out_to_an_independent_one():
    """geneB is geneA scaled by exactly 2x (correlation 1.0 — pure redundancy). geneC is
    a weaker but genuinely independent signal. With room for only 2, the greedy pass
    should keep the independent gene over the redundant twin, even though geneB's own
    fold change and significance rank it above geneC on a naive sort."""
    table = DgeTable(
        rows=(
            make_row(gene_id="A", log2_fold_change=2.5, p_adj=0.001),
            make_row(gene_id="B", log2_fold_change=2.4, p_adj=0.001),
            make_row(gene_id="C", log2_fold_change=1.5, p_adj=0.001),
        )
    )
    counts = make_counts(
        {
            "A": ([10, 11, 9], [50, 52, 48]),
            "B": ([20, 22, 18], [100, 104, 96]),  # == 2x A, correlation 1.0
            "C": ([30, 5, 40], [5, 40, 20]),  # verified low correlation with A
        }
    )
    constraints = Constraints(max_separation=3.0, direction_balance=False, max_genes=2)
    selected = make_selector(constraints).select(table, counts=counts)

    assert {gene.gene_id for gene in selected} == {"A", "C"}


def test_no_counts_falls_back_to_a_plain_ranking():
    """With no count matrix, non-redundancy cannot be measured — the greedy pass must
    degrade to exactly the base-axis ranking, not silently default redundancy to a
    fabricated value."""
    table = DgeTable(
        rows=(
            make_row(gene_id="A", log2_fold_change=2.5, p_adj=0.001),
            make_row(gene_id="B", log2_fold_change=2.4, p_adj=0.001),
            make_row(gene_id="C", log2_fold_change=1.5, p_adj=0.001),
        )
    )
    constraints = Constraints(max_separation=3.0, direction_balance=False, max_genes=2)
    selected = make_selector(constraints).select(table)
    assert [gene.gene_id for gene in selected] == ["A", "B"]
    for gene in selected:
        assert gene.control_percentile is None  # nothing to measure without counts


# ---------------------------------------------------------------------------
# Direction balance (docs/genes.md §4.4)
# ---------------------------------------------------------------------------


def test_direction_balance_reserves_a_slot_for_the_minority_direction():
    table = DgeTable(
        rows=(
            make_row(gene_id="D1", log2_fold_change=-4.0, p_adj=0.001),
            make_row(gene_id="D2", log2_fold_change=-3.8, p_adj=0.001),
            make_row(gene_id="D3", log2_fold_change=-3.5, p_adj=0.001),
            make_row(gene_id="U1", log2_fold_change=1.0, p_adj=0.001),
        )
    )
    constraints = Constraints(max_genes=2, direction_balance=True)
    selected = make_selector(constraints).select(table)
    regulations = {gene.regulation for gene in selected}
    assert regulations == {Regulation.UP, Regulation.DOWN}
    assert "U1" in {gene.gene_id for gene in selected}


def test_direction_balance_disabled_takes_the_plain_top_k():
    table = DgeTable(
        rows=(
            make_row(gene_id="D1", log2_fold_change=-4.0, p_adj=0.001),
            make_row(gene_id="D2", log2_fold_change=-3.8, p_adj=0.001),
            make_row(gene_id="U1", log2_fold_change=1.0, p_adj=0.001),
        )
    )
    constraints = Constraints(max_genes=2, direction_balance=False)
    selected = make_selector(constraints).select(table)
    assert {gene.gene_id for gene in selected} == {"D1", "D2"}


def test_all_up_shortlist_warns_that_no_down_gene_survived():
    table = DgeTable(
        rows=(
            make_row(gene_id="U1", log2_fold_change=2.0, p_adj=0.001),
            make_row(gene_id="U2", log2_fold_change=1.8, p_adj=0.001),
        )
    )
    warnings, on_warning = collect_warnings()
    make_selector(Constraints(direction_balance=True)).select(table, on_warning=on_warning)
    assert any("No down-regulated gene" in message for message in warnings)


# ---------------------------------------------------------------------------
# max_genes
# ---------------------------------------------------------------------------


def test_max_genes_caps_the_shortlist():
    rows = [
        make_row(gene_id=f"g{i}", log2_fold_change=1.0 + i * 0.1, p_adj=0.001) for i in range(10)
    ]
    table = DgeTable(rows=tuple(rows))
    selected = make_selector(Constraints(max_genes=3, direction_balance=False)).select(table)
    assert len(selected) == 3
