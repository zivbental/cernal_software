"""Real ViennaRNA regression tests for the run-wide, immutable folding model."""

import dataclasses
import hashlib
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import RNA

from engine.domain import AssemblyStandard, Constraints, FoldingConfig, Regulation, SelectedGene
from engine.gates.tools import folding
from engine.gates.tools.folding import FoldEngine
from engine.stages.folding import FoldProfiler
from engine.stages.motifs import MotifScreener
from engine.stages.triggers import TriggerScorer

SEQUENCE = "GGGCGAAAGCCCAUAUAUGGGCUUUCCC"
LOCAL_SEQUENCE = "ACGU" * 60
SRC = str(Path(__file__).resolve().parents[2] / "src")

# The reference never imports CERNAL's adapter. Each subprocess starts with clean
# native caches, loads exactly one table, and folds with an explicit native model.
_REFERENCE = r"""
import json, sys, RNA
config = json.loads(sys.argv[1])
assert RNA.params_load_from_string(getattr(RNA, "parameter_set_rna_" + config["energy_parameters"]))
md = RNA.md(temperature=config["temperature_celsius"], dangles=config["dangles"],
    special_hp=int(config["special_hairpins"]), noLP=int(config["no_lonely_pairs"]),
    noGU=int(config["no_gu"]), noGUclosure=int(config["no_gu_closure"]))
values = []
for sequence in json.loads(sys.argv[2]):
    fc = RNA.fold_compound(sequence, md)
    structure, energy = fc.mfe()
    target_energy = fc.eval_structure(structure)
    _, ensemble = fc.pf()
    values.append([structure, energy, target_energy, ensemble])
print(json.dumps(values))
"""


def reference(config, sequences):
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _REFERENCE,
            json.dumps(dataclasses.asdict(config)),
            json.dumps(sequences),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


@pytest.fixture(autouse=True)
def restore_global_tables():
    yield
    RNA.params_load_RNA_Turner2004()
    folding._fresh_parameters(RNA.md())


@pytest.mark.parametrize(
    "config",
    [
        FoldingConfig(),
        FoldingConfig(temperature_celsius=15),
        FoldingConfig(temperature_celsius=65),
        FoldingConfig(dangles=0),
        FoldingConfig(special_hairpins=False),
        FoldingConfig(no_lonely_pairs=True),
        FoldingConfig(no_gu=True),
        FoldingConfig(no_gu_closure=True),
        FoldingConfig(energy_parameters="turner1999"),
        FoldingConfig(energy_parameters="andronescu2007"),
        FoldingConfig(
            temperature_celsius=28,
            dangles=0,
            special_hairpins=False,
            no_gu=True,
            no_gu_closure=True,
            no_lonely_pairs=True,
            energy_parameters="andronescu2007",
        ),
    ],
)
def test_all_models_match_independent_native_reference(config):
    sequences = ["GGGAAACCC", SEQUENCE, "GGG&CCC", "AAAAAAA"]
    expected = reference(config, sequences)
    folder = FoldEngine(config=config)
    for sequence, (structure, mfe, evaluated, ensemble) in zip(sequences, expected, strict=True):
        assert folder.mfe(sequence).structure == structure
        assert folder.mfe(sequence).energy == mfe
        assert folder.structure_energy(sequence, structure) == evaluated
        assert folder.partition(sequence) == pytest.approx(ensemble, abs=1e-6)
        compound = folder._compound(sequence)
        before = compound.exp_params.param_file
        compound.pf()
        assert compound.exp_params.param_file == before  # PF must never reload globals.


def test_energy_snapshot_cache_switches_tables_in_the_same_process():
    expected = {
        "turner2004": (-1.2000000476837158, -1.6191964149475098),
        "turner1999": (-3.9000000953674316, -3.9124648571014404),
        "andronescu2007": (-1.75, -1.9235178232192993),
    }
    for name in ["turner2004", "turner1999", "andronescu2007", "turner2004"]:
        folder = FoldEngine(config=FoldingConfig(energy_parameters=name))
        assert (folder.mfe("GGGAAACCC").energy, folder.partition("GGGAAACCC")) == expected[name]


def test_default_model_ignores_mutated_native_defaults_and_external_energy_loads(monkeypatch):
    expected = FoldEngine().mfe(SEQUENCE)
    expected_ensemble = FoldEngine().partition(SEQUENCE)
    # No adapter cache can hide a global state leak in a newly constructed engine.
    RNA.params_load_RNA_Andronescu2007()
    for name, value in [("temperature", 15.0), ("dangles", 0), ("noGU", 1), ("noLonelyPairs", 1)]:
        monkeypatch.setattr(RNA.cvar, name, value)
    folder = FoldEngine()
    assert folder.mfe(SEQUENCE) == expected
    assert folder.partition(SEQUENCE) == expected_ensemble
    assert folder.provenance()["model_details"]["noGU"] == 0
    assert RNA.last_parameter_file() == "RNA - Andronescu 2007"


def test_snapshot_loading_restores_global_tables_and_identity(tmp_path):
    RNA.params_load_RNA_Turner1999()
    before = tmp_path / "before.par"
    after = tmp_path / "after.par"
    assert RNA.params_save(str(before))
    previous_name = RNA.last_parameter_file()
    FoldEngine(config=FoldingConfig(temperature_celsius=23.456, energy_parameters="andronescu2007"))
    assert RNA.params_save(str(after))
    assert before.read_bytes() == after.read_bytes()
    assert RNA.last_parameter_file() == previous_name
    native = RNA.fold_compound("GGGAAACCC")
    assert native.mfe()[1] == pytest.approx(-3.9)
    assert native.pf()[1] == pytest.approx(-3.912464857)


def test_snapshot_failure_restores_global_state(monkeypatch):
    RNA.params_load_RNA_Turner1999()
    actual_load = RNA.params_load_from_string

    def fail_selected(text, name):
        return 0 if name.startswith("cernal:") else actual_load(text, name)

    monkeypatch.setattr(RNA, "params_load_from_string", fail_selected)
    with pytest.raises(RuntimeError, match="Could not load"):
        FoldEngine(config=FoldingConfig(temperature_celsius=23.457))
    assert RNA.last_parameter_file() == "RNA - Turner 1999"
    assert RNA.fold_compound("GGGAAACCC").mfe()[1] == pytest.approx(-3.9)


def test_concurrent_runs_and_instance_caches_are_isolated():
    configs = [
        FoldingConfig(temperature_celsius=10 + index, energy_parameters=name)
        for index in range(4)
        for name in ("turner2004", "turner1999", "andronescu2007")
    ]
    expected = {config: reference(config, [SEQUENCE])[0][1::2] for config in configs}

    def run(config):
        folder = FoldEngine(config=config)
        values = [folder.mfe(SEQUENCE).energy, folder.partition(SEQUENCE)]
        assert values == pytest.approx(expected[config], abs=1e-6)
        assert folder.mfe(SEQUENCE).energy == values[0]
        assert folder.mfe.cache_info().hits == 1
        return folder.provenance()["configuration"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(run, configs * 2)) == [dataclasses.asdict(c) for c in configs * 2]


def test_model_and_provenance_cannot_mutate_cached_results():
    folder = FoldEngine()
    original = folder.partition(SEQUENCE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        folder.config.dangles = 0
    with pytest.raises(AttributeError):
        folder.temperature = 10
    with pytest.raises(AttributeError):
        folder.config = FoldingConfig(dangles=0)
    report = folder.provenance()
    report["configuration"]["dangles"] = 0
    assert folder.provenance()["configuration"]["dangles"] == 2
    assert folder.partition(SEQUENCE) == original
    report = json.loads(json.dumps(folder.provenance(), allow_nan=False))
    table = report["energy_parameters"]
    assert table["sha256"] == hashlib.sha256(RNA.parameter_set_rna_turner2004.encode()).hexdigest()
    assert table["loaded_identity"] == folder._compound(SEQUENCE).params.param_file
    assert json.loads(folder.versions()["folding_model"]) == report


def test_suboptimal_worker_receives_full_configuration():
    config = FoldingConfig(
        temperature_celsius=22,
        dangles=0,
        special_hairpins=False,
        no_gu=True,
        energy_parameters="turner1999",
    )
    folder = FoldEngine(config=config)
    structures = folder.suboptimal("GGGAAACCC", delta=1)
    assert structures[0] == folder.mfe("GGGAAACCC")
    assert all(
        folder.structure_energy("GGGAAACCC", result.structure) == result.energy
        for result in structures
    )
    assert folder.provenance()["suboptimal_model_override"] == {"uniq_ML": 1}


def test_rnaplfold_defaults_preserve_old_native_path():
    profiler = FoldProfiler()
    for sequence in ["A", "GGGAAACCC", LOCAL_SEQUENCE]:
        window, span, unpaired = profiler._parameters(sequence)
        expected = RNA.pfl_fold_up(sequence, unpaired, window, span)
        actual = profiler._matrix(sequence)
        assert actual == tuple(tuple(row) for row in expected)


def test_local_model_changes_probabilities_and_trigger_energy_uses_its_temperature():
    config = FoldingConfig(temperature_celsius=20, energy_parameters="andronescu2007")
    profiler = FoldProfiler(config=config)
    assert profiler.profile(LOCAL_SEQUENCE) != FoldProfiler().profile(LOCAL_SEQUENCE)
    scorer = TriggerScorer(
        profiler, MotifScreener(AssemblyStandard.NONE), FoldEngine(config=config)
    )
    gene = SelectedGene(
        gene_id="g", symbol="g", regulation=Regulation.UP, log2_fold_change=2, score=1
    )
    candidates = list(
        scorer.score(
            [gene],
            {"g": LOCAL_SEQUENCE},
            Constraints(trigger_lengths=(30,), standard=AssemblyStandard.NONE),
        )
    )
    assert candidates
    for candidate in candidates:
        expected = -(
            scorer.GAS_CONSTANT_KCAL_PER_MOL_K
            * 293.15
            * math.log(max(candidate.joint_open_probability_20, scorer.PU_FLOOR))
            / 20
        )
        assert candidate.delta_g_open_kcal_per_mol_per_nt == expected
        assert candidate.rnaplfold_temperature_celsius == 20
        model = json.loads(candidate.rnaplfold_model)
        assert model["configuration"] == dataclasses.asdict(config)
        assert model["model_details"]["window_size"] == 200
        assert model["model_details"]["max_bp_span"] == 150


def test_profiler_missing_runtime_is_still_reported_without_importing_the_adapter():
    script = r"""
import builtins, json, sys
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def without_rna(name, *args, **kwargs):
    if name == "RNA":
        raise ModuleNotFoundError("No module named RNA", name="RNA")
    return original(name, *args, **kwargs)
builtins.__import__ = without_rna
from engine.stages.folding import FoldProfiler
profiler = FoldProfiler()
assert not profiler.available
assert profiler.provenance("AAAA")["folding_model"] is None
"""
    subprocess.run([sys.executable, "-I", "-c", script, SRC], check=True, capture_output=True)


def test_profiler_window_parameters_cannot_make_cached_provenance_stale():
    profiler = FoldProfiler()
    profiler.profile(SEQUENCE)
    for name in ("window", "max_span", "unpaired", "config"):
        with pytest.raises(AttributeError):
            setattr(profiler, name, 5)
    for name in ("window", "max_span", "unpaired"):
        for invalid in (0, -1, True, 2.0):
            with pytest.raises(ValueError, match="positive integer"):
                FoldProfiler(**{name: invalid})
