"""Desired scientific behavior for the October 2026 audit regressions."""

import gc
import io
import weakref

import pytest
from openpyxl import Workbook

from engine.client import (
    LocalEngine,
    inspect_expression_input,
    normalize_trigger_sequence,
    validate_job_configuration,
)
from engine.domain import Constraints, DgeRow, DgeTable
from engine.errors import InputValidationError
from engine.gates.tools.folding import FoldEngine
from engine.inputs import parse_dge_table
from engine.pipeline import _build_constraints
from engine.scoring.normalize import failed_filter, normalize_value
from engine.scoring.profiles import DEFAULT_V1
from engine.stages.folding import FoldProfiler
from engine.stages.genes import GeneSelector
from engine.stages.motifs import MotifScreener


@pytest.mark.parametrize("suffix", ["csv", "tsv", "txt", "xlsx"])
@pytest.mark.parametrize("bad", ["inf", "-Infinity", "1e999", "not-a-number", "-0.1", "1.01"])
def test_invalid_probability_rejected_across_input_formats(suffix, bad):
    if suffix == "xlsx":
        book = Workbook()
        book.active.append(["gene_id", "log2fc", "pvalue"])
        book.active.append(["g1", 2.0, bad])
        stream = io.BytesIO()
        book.save(stream)
        raw = stream.getvalue()
    else:
        delimiter = "," if suffix == "csv" else "\t"
        raw = (
            delimiter.join(["gene_id", "log2fc", "pvalue"])
            + "\n"
            + delimiter.join(["g1", "2", bad])
            + "\n"
        ).encode()
    with pytest.raises(InputValidationError):
        parse_dge_table(raw, f"input.{suffix}")


@pytest.mark.parametrize("headers", ["gene_id,log2fc, log2 Fold Change", "gene_id,,log2fc"])
def test_normalized_header_collisions_rejected(headers):
    with pytest.raises(InputValidationError, match="headers"):
        parse_dge_table(f"{headers}\ng1,2,2\n".encode())


def test_preview_and_engine_use_first_xlsx_sheet(tmp_path):
    book = Workbook()
    book.active.append(["gene_id", "log2 Fold Change"])
    book.active.append(["first", 2])
    other = book.create_sheet("active-but-not-first")
    other.append(["gene_id", "log2fc"])
    other.append(["other", 9])
    book.active = 1
    path = tmp_path / "input.xlsx"
    book.save(path)
    report = inspect_expression_input(str(path))
    assert report["valid"]
    assert report["selected_sheet"] == 0
    assert report["preview"] == [{"gene_id": "first", "log2fc": 2.0}]
    assert parse_dge_table(path.read_bytes(), path.name).rows[0].gene_id == "first"


def test_raw_pvalues_need_complete_hypothesis_declaration():
    rows = tuple(DgeRow(f"g{i}", 2.0, p_value=p) for i, p in enumerate([0.01, 0.04, 0.9]))
    selector = GeneSelector(Constraints(direction_balance=False), MotifScreener())
    warnings = []
    subset = selector.select(
        DgeTable(rows, hypothesis_universe_complete=False), on_warning=warnings.append
    )
    assert len(subset) == 2
    assert all(g.p_adj is None for g in subset)
    assert any("not an FDR-controlled" in warning for warning in warnings)
    complete = selector.select(DgeTable(rows, hypothesis_universe_complete=True))
    assert len(complete) == 1
    assert complete[0].p_adj == pytest.approx(0.03)


def test_instance_fold_cache_is_bounded_and_collectible():
    folder = FoldEngine(cache_size=1)
    folder.mfe("GGGAAACCC")
    expected = folder.mfe("GGGAAACCC")
    folder.mfe("GGGAAAACCC")
    assert folder.mfe.cache_info().currsize == 1
    assert folder.mfe.cache_info().maxsize == 1
    assert folder.mfe("GGGAAACCC") == expected
    reference = weakref.ref(folder)
    del folder
    gc.collect()
    assert reference() is None


def test_instance_rnaplfold_cache_is_bounded_and_collectible():
    profiler = FoldProfiler()
    for sequence in ("GGGAAACCC", "GGGAAAACCC", "GGGAAAAACCC"):
        profiler.profile(sequence)
    assert profiler._matrix.cache_info().currsize == 2
    reference = weakref.ref(profiler)
    del profiler
    gc.collect()
    assert reference() is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_metrics_cannot_score_or_pass_filter(bad):
    with pytest.raises(ValueError, match="finite"):
        normalize_value(bad, DEFAULT_V1.spec("predicted_leakage"))
    assert failed_filter({"predicted_leakage": bad}, DEFAULT_V1) is not None


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_genes", True),
        ("max_triggers", 0),
        ("max_p_adj", 2),
        ("min_separation", float("nan")),
        ("trigger_gc_range", [70, 30]),
        ("forbidden_motifs", [""]),
        ("forbidden_motifs", "ATG"),
        ("direction_balance", "false"),
    ],
)
def test_invalid_constraints_fail_before_computation(field, value):
    with pytest.raises(InputValidationError):
        _build_constraints({"constraints": {field: value}})


def test_forbidden_motifs_normalize_dna_case():
    assert _build_constraints({"constraints": {"forbidden_motifs": ["augc"]}}).forbidden_motifs == (
        "ATGC",
    )


@pytest.mark.parametrize("sequence", ["AUN", ">a\nAU\n>b\nGC", ">\nAUG", "AUG!"])
def test_trigger_normalization_never_discards_invalid_symbols(sequence):
    with pytest.raises(ValueError):
        normalize_trigger_sequence(sequence)


def test_single_fasta_record_normalizes_without_changing_coordinates():
    assert normalize_trigger_sequence(">one record\nat gc\nTT") == "AUGCUU"


def test_capabilities_advertise_only_runnable_host_family_pairs():
    capabilities = LocalEngine().capabilities()
    assert "antisense" not in capabilities.available_families
    assert all("and" not in name for name in capabilities.available_families)
    assert set(capabilities.family_hosts) == set(capabilities.available_families)
    for name, hosts in capabilities.family_hosts.items():
        for host in hosts:
            assert (
                validate_job_configuration({}, [name], "default", "direct", "AUGC", host)["host"]
                == host
            )
    with pytest.raises(ValueError, match="production supported"):
        validate_job_configuration(
            {}, ["prokaryotic_toehold"], "default", "direct", "AUGC", "human"
        )


def test_validated_structure_and_physical_construct():
    from Bio import SeqIO

    from engine.domain import (
        BooleanExpression,
        CircuitCandidate,
        ConfusionMatrix,
        DesiredOutcome,
        Host,
        LogicGraph,
        LogicOperator,
        TriggerCandidate,
        TriggerSet,
    )
    from engine.gates.toehold import ToeholdGate
    from engine.gates.tools.codons import CodonOptimizer
    from engine.gates.tools.translation import TranslationScorer
    from engine.stages.plasmids import PlasmidBuilder, to_genbank
    from engine.stages.switches import SwitchValidator

    host = Host.ECOLI
    folder = FoldEngine()
    translation = TranslationScorer(host)
    codons = CodonOptimizer(host)
    screener = MotifScreener()
    family = ToeholdGate(host, folder, translation, codons)
    trigger = TriggerCandidate(
        "t1", "g1", "G1", "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA", 0, 0.8, 0.8, -1, 50
    )
    design = next(family.generate_designs(TriggerSet((trigger,)), Constraints()))
    validation = SwitchValidator(folder, screener, translation, Constraints()).validate(design)
    assert validation.ok
    assert 0 <= validation.structure_deviation <= 1
    graph = LogicGraph((), LogicOperator.IDENTITY, LogicOperator.IDENTITY, False, "other", "")
    circuit = CircuitCandidate(
        "c1", BooleanExpression.gene("g1"), graph, (design,), ConfusionMatrix(0, 0, 0, 0), "other"
    )
    builder = PlasmidBuilder(screener, codons, Constraints().standard)
    compiled = builder.build(circuit, DesiredOutcome.CUSTOM, custom_payload="ATGGCTGCTTAA")
    assert compiled.coding_regions
    record = SeqIO.read(io.StringIO(to_genbank(compiled).decode()), "genbank")
    assert record.annotations["topology"] == "linear"
    coding = [f for f in record.features if f.type == "CDS"]
    assert len(coding) == 1
    assert (
        str(coding[0].extract(record.seq).translate()).rstrip("*")
        == coding[0].qualifiers["translation"][0]
    )
    import dataclasses

    for operator in (LogicOperator.AND, LogicOperator.OR, LogicOperator.NOT):
        expression = BooleanExpression(operator, (BooleanExpression.gene("g1"),))
        with pytest.raises(InputValidationError, match="Unsupported physical circuit"):
            builder.build(dataclasses.replace(circuit, expression=expression), DesiredOutcome.GFP)
    with pytest.raises(InputValidationError, match="does not identify"):
        builder.build(
            dataclasses.replace(circuit, expression=BooleanExpression.gene("wrong")),
            DesiredOutcome.GFP,
        )
    for structure in ("bad" * len(design.sequence), "(" + "." * (len(design.sequence) - 1)):
        result = SwitchValidator(folder, screener, translation, Constraints()).validate(
            dataclasses.replace(design, dot_bracket=structure)
        )
        assert not result.ok


def test_exact_structure_comparison_does_not_invent_fold_probability():
    from engine.gates.tools.folding import structure_match

    assert structure_match("((..))", "((..))").deviation == 0
    assert structure_match("((..))", ".(..).").deviation == pytest.approx(2 / 6)
    assert structure_match("((..))", "((..))").p_target_fold is None


def test_count_threshold_classifier_has_independent_truth_table():
    from engine.domain import BooleanExpression, CountMatrix, SampleMetadata
    from engine.stages.circuits import ConfusionEvaluator
    from engine.stages.quality import InputQualityCheck

    matrix = CountMatrix(
        ("g1",),
        ("c0", "c1", "t0", "t1"),
        ((0, 2, 2, 0),),
        SampleMetadata(("c0", "c1"), ("t0", "t1")),
    )
    qc = InputQualityCheck().check(matrix, matrix.metadata)
    assert not qc.ok  # two zero-library samples cannot support expression QC
    confusion = ConfusionEvaluator().evaluate(BooleanExpression.gene("g1"), matrix, 1)
    assert (
        confusion.true_positive,
        confusion.false_positive,
        confusion.false_negative,
        confusion.true_negative,
    ) == (1, 1, 1, 1)
    assert confusion.separation_margin == 0
    with pytest.raises(InputValidationError, match="absent"):
        ConfusionEvaluator().evaluate(BooleanExpression.gene("absent"), matrix, 1)


def test_configured_rank_ties_follow_metric_directions():
    from engine.scoring.normalize import rank_candidates

    scores = [("a", 0.5), ("b", 0.5)]
    raw = {
        "a": {"state_separation": 1, "predicted_leakage": 0.2},
        "b": {"state_separation": 2, "predicted_leakage": 0.3},
    }
    assert rank_candidates(scores, raw_values=raw, profile=DEFAULT_V1) == {"b": 1, "a": 2}
    raw["a"]["state_separation"] = 2
    assert rank_candidates(scores, raw_values=raw, profile=DEFAULT_V1) == {"a": 1, "b": 2}


def test_snapshots_preserve_zero_and_missing_without_releasing_sequences(tmp_path):
    from engine.store import CandidateStore

    store = CandidateStore(str(tmp_path), "run")
    artifact = store.snapshot("input", [{"sequence": "AUGC", "zero": 0, "missing": None}])
    content = (tmp_path / artifact.path).read_text()
    assert "AUGC" not in content
    assert "sequence_sha256" in content
    rows = store.load_snapshot("input")
    assert rows[0]["zero"] == "0"
    assert rows[0]["missing"] == ""
    with pytest.raises(ValueError):
        store.load_snapshot("../input")


def test_full_preview_preserves_missing_statistic_headers(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("gene_id,log2fc,padj\ng1,2,NA\ng2,1,NA\n")
    report = inspect_expression_input(str(path), limit=None)
    assert report["columns"] == ["gene_id", "log2fc", "padj"]
    assert len(report["preview"]) == 2
    assert report["preview"][0]["padj"] is None


@pytest.mark.parametrize(
    "budget", [{"max_seconds": 1}, {"max_designs": True}, {"max_designs": 1001}]
)
def test_invalid_compute_budget_is_rejected(budget):
    with pytest.raises(ValueError, match="budget"):
        validate_job_configuration(
            {"budget": budget}, ["toehold"], "default", "direct", "AUGC", "ecoli"
        )


def test_suboptimal_matches_viennarna_energy_window_and_count_limit():
    import RNA

    folder = FoldEngine()
    actual = folder.suboptimal("GGGAAACCC", 0.5)
    model = RNA.md()
    model.temperature = 37
    model.uniq_ML = 1
    expected = RNA.fold_compound("GGGAAACCC", model).subopt(50)
    assert [(fold.structure, fold.energy) for fold in actual] == sorted(
        [(fold.structure, fold.energy) for fold in expected], key=lambda fold: (fold[1], fold[0])
    )
    with pytest.raises(ValueError, match="count limit"):
        folder.suboptimal("GGGAAACCC", 0.5, max_structures=1)
    with pytest.raises(ValueError, match=r"1\.\.150"):
        folder.suboptimal("A" * 151)


def test_suboptimal_timeout_returns_no_partial_ensemble(monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(TimeoutError, match="time limit"):
        FoldEngine().suboptimal("GGGAAACCC")
