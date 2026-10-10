"""The energy-model guard for the AIS-China submodule — read this before bumping it.

**What this file prevents.** CLAUDE.md §5: ``FoldEngine`` is the single folding authority,
and "two designs folded under different model settings produce free energies that
``engine.scoring`` will normalise onto the same axis as though they were comparable".
The AIS-China library (``vendor/ais-china-codon-optimization-v2``, used unmodified) does
``import RNA`` in ``codon_v2/rna.py`` and calls ``RNA.params_load(<their .par file>)``.
That call changes global energy tables. CERNAL now snapshots its explicitly selected
model independently, so external parameter loads cannot silently change its cached or
uncached design folds. The deliberately altered-table control below verifies this.

Vendor equivalence remains worth checking: its diagnostic metrics use its own model.
Its ``config/rna_turner2004.par`` is numerically identical to ViennaRNA 2.7.2's bundled
Turner 2004 defaults (all 8,059 lines; only line endings differ). That is a fact about
one version of one file. A vendor bump can change it without any import-layer rule
noticing, because the third-party source lives outside ``src/engine/``.

**If one of these tests fails after a bump, do not edit the test.** Either the bump
changed the energy model — in which case it must not be merged as-is, because a second
energy model would be running inside the process — or their ``rna_model.json`` and
parameter file disagree with each other, in which case their own pipeline refuses to run
``rna_start`` and the pin is bad. Re-verify equivalence (the tests below are that
verification), and only then move ``PINNED_COMMIT``.

The pristine reference is computed in a **fresh interpreter** that has never loaded any
parameter file, so the comparison cannot be made vacuous by test ordering (an earlier test
that ran their ``optimize()`` leaves their parameters loaded in this process).
"""

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import RNA

from engine.gates.tools.ais_china import DEFAULT_ROOT, AisChinaCodons
from engine.gates.tools.folding import FoldEngine

SRC = Path(__file__).resolve().parents[2] / "src"

#: Single strand, a long strand (their window is up to 300 nt), a tiny hairpin, and a dimer
#: — the ``&`` path exercises the duplex-initiation terms of the parameter file, which
#: single-strand folds never read.
REFERENCE_STRANDS = (
    "AUGUCCAAGGGCGAGGAGCUGUUCACCGGCGUCGUCCCGAUCCUGGUCGAGCUGGACGGCGACGUCAACGGCCACAAGUUCUCCGUC"
    "UCCGGCGAGGGCGAGGGCGACGCCACCUACGGCAAGCUGACCCUGAAGUUCAUCUGCACCACC",
    "GGGAAACCC",
    "GGGCGAAAGCCCAUAUAUGGGCUUUCCC",
    "GGGCGAAAGCCC&GGGCUUUCCC",
)

_PRISTINE_SCRIPT = """
import json, sys
sys.path.insert(0, sys.argv[1])
from engine.gates.tools.folding import FoldEngine
strands = json.loads(sys.argv[2])
out = []
for s in strands:
    folder = FoldEngine()
    result = folder.mfe(s)
    # partition() takes a single strand; a dimer has none in this comparison.
    partition = None if "&" in s else folder.partition(s)
    out.append([result.structure, result.energy, partition])
print(json.dumps(out))
"""


def _folds(strands) -> list[list]:
    """Fold with a *fresh* FoldEngine per strand, so no cache can hide a change."""
    out = []
    for s in strands:
        folder = FoldEngine()
        result = folder.mfe(s)
        partition = None if "&" in s else folder.partition(s)
        out.append([result.structure, result.energy, partition])
    return out


@pytest.fixture(scope="module")
def pristine() -> list[list]:
    """FoldEngine's numbers in a process that has never loaded a parameter file."""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _PRISTINE_SCRIPT, str(SRC), json.dumps(REFERENCE_STRANDS)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


@pytest.fixture(autouse=True)
def _restore_builtin_parameters():
    """Never leak a parameter set out of this file, whatever a test did to it."""
    yield
    RNA.params_load_RNA_Turner2004()


@pytest.fixture(scope="module")
def model() -> dict:
    """Their ``config/rna_model.json``. Read with ``utf-8-sig``: their text files may
    carry a BOM, and ``json.loads`` of a BOM-prefixed string raises."""
    return json.loads((DEFAULT_ROOT / "config/rna_model.json").read_text(encoding="utf-8-sig"))


@pytest.fixture(scope="module")
def parameter_file(model) -> Path:
    return DEFAULT_ROOT / model["energy_parameter_file"]


def test_parameter_file_hashes_to_the_hash_their_own_model_records(model, parameter_file):
    """Their ``.par`` file is byte-for-byte the one their ``rna_model.json`` vouches for.

    Their ``RNAEngine`` makes the same check at run time and quietly disables the
    ``rna_start`` strategy when it fails, so a mismatch would not crash a run — it would
    just remove a strategy. Here it fails loudly instead.
    """
    actual = hashlib.sha256(parameter_file.read_bytes()).hexdigest()
    assert actual == model["energy_parameter_sha256"], (
        f"{parameter_file} hashes to {actual} but config/rna_model.json records "
        f"{model['energy_parameter_sha256']}. The submodule's energy parameters changed "
        "under it. Do not merge this bump until the fold-equivalence tests below pass "
        "against the new file (CLAUDE.md §5: one energy model per process)."
    )


def test_installed_viennarna_is_the_version_their_model_was_verified_against(model):
    """Equivalence was verified against one ViennaRNA release; a different one is a new question.

    "Their file equals the built-in defaults" is a statement about a specific ViennaRNA
    version's defaults. If ``uv.lock`` moves ViennaRNA, the built-in set could move with it
    while their frozen file does not, and this test is where that surfaces. (Their own
    pipeline also refuses to run ``rna_start`` on a version mismatch.)
    """
    assert RNA.__version__ == model["viennarna_version"], (
        f"ViennaRNA {RNA.__version__} is installed but their model declares "
        f"{model['viennarna_version']}. Re-verify that their parameter file still equals "
        "the built-in defaults of the installed release."
    )


def test_loading_their_parameter_file_leaves_foldengine_bit_identical(pristine, parameter_file):
    """The core guarantee: ``RNA.params_load(their .par)`` changes no ``FoldEngine`` number.

    Compared exactly (``==`` on structure strings and float energies), not to a tolerance:
    a parameter file that differs in a single stacking term would move some of these by a
    visible amount, and one that matches must reproduce them to the last bit.
    """
    assert _folds(REFERENCE_STRANDS) == pristine, "baseline in this process differs from fresh"
    assert RNA.params_load(str(parameter_file)), "ViennaRNA rejected their parameter file"
    assert _folds(REFERENCE_STRANDS) == pristine, (
        "Loading the AIS-China parameter file changed a FoldEngine fold. A second energy "
        "model is now active in this process (CLAUDE.md §5)."
    )


def test_a_full_optimize_run_leaves_foldengine_bit_identical(pristine):
    """Same guarantee, through the real code path rather than a hand-made ``params_load``.

    Running their ``optimize()`` is what actually calls ``RNA.params_load`` in production,
    inside their lock, as a side effect no caller asked for.
    """
    codons = AisChinaCodons()
    cds = (
        "AUGAGUAAAGGAGAAGAACUUUUCACUGGAGUUGUCCCAAUUCUUGUUGAAUUAGAUGGUGAUGUUAAUGGGCACAAAUUUUCUGUC"
        "AGUGGAGAGGGUGAAGGUGAUGCAACAUACGGAAAACUUACCCUUAAAUUUAUUUGCACUACUGGAAAAUAA"
    )
    run = codons.optimize(cds, seed=7, strategies=["cai_max", "rna_start"])
    assert run.original.metric("rna").status == "ok", "the RNA engine never ran; test is vacuous"
    assert _folds(REFERENCE_STRANDS) == pristine, (
        "Their optimize() run left a different energy model loaded in this process (CLAUDE.md §5)."
    )


def test_their_ensemble_calculation_agrees_exactly_with_foldengine(pristine, parameter_file):
    """Their numbers sit on FoldEngine's energy axis: MFE and ensemble free energy match.

    Calls their own ``RNAEngine.ensemble`` — the function behind every ``rna`` metric they
    report — and compares it with ``FoldEngine.mfe`` / ``FoldEngine.partition`` for the
    same sequence. Their model object sets temperature 37 °C, ``dangles=2`` and a salt of
    1.021 M explicitly; FoldEngine relies on ViennaRNA's defaults. That these coincide is
    the second half of the equivalence, and ``rna_model.json`` is what states it.
    """
    AisChinaCodons()  # registers codon_v2 from the pinned submodule
    codon_rna = importlib.import_module("codon_v2.rna")
    engine = codon_rna.RNAEngine(DEFAULT_ROOT)
    assert engine.reason is None, f"their RNA engine is disabled: {engine.reason}"
    assert RNA.params_load(str(engine.parameter_file))

    for strand, (_, mfe, partition) in zip(REFERENCE_STRANDS, pristine, strict=True):
        if "&" in strand:
            continue
        ensemble, their_mfe, _ = engine.ensemble(strand, [], 37.0)
        assert their_mfe == mfe, f"MFE differs for {strand[:20]}…: {their_mfe} vs {mfe}"
        assert ensemble == partition, (
            f"ensemble free energy differs for {strand[:20]}…: {ensemble} vs {partition}"
        )


def test_the_guard_has_teeth(pristine, parameter_file, tmp_path):
    """A parameter file that really is different *does* move the folds this file compares.

    Without this, the identical-fold assertions above could be passing for the wrong
    reason (an unused ``params_load``, a cache, an energy that does not depend on stacking).
    One CG/CG stacking term is weakened by 1 kcal/mol in a copy of their file; the same
    raw-library comparison must now fail, while CERNAL stays on its explicit model.
    """
    text = parameter_file.read_bytes().decode("ascii")
    assert "  -240  -330" in text, "their file no longer has the line this control edits"
    altered = tmp_path / "altered.par"
    altered.write_bytes(text.replace("  -240  -330", "  -140  -330", 1).encode("ascii"))
    assert RNA.params_load(str(altered))
    # The raw library changes, proving this is a real different energy axis. The
    # shared adapter must now stay on its explicitly selected bundled model.
    raw = [RNA.fold_compound(strand).mfe()[1] for strand in REFERENCE_STRANDS]
    assert raw != [fold[1] for fold in pristine]
    assert _folds(REFERENCE_STRANDS) == pristine


def test_vendor_optimization_shares_the_folding_parameter_lock(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from engine.gates.tools import VIENNA_PARAMETER_LOCK

    adapter = AisChinaCodons()

    def attempt_lock():
        acquired = VIENNA_PARAMETER_LOCK.acquire(blocking=False)
        if acquired:
            VIENNA_PARAMETER_LOCK.release()
        return acquired

    def check_vendor_call(*args, **kwargs):
        # A second thread must fail immediately while the wrapper calls the vendor.
        # No sleeps or scheduling assumptions: future.result waits for the attempt.
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(attempt_lock).result() is False
        raise RuntimeError("checked shared lock")

    monkeypatch.setattr(adapter._pipeline, "optimize", check_vendor_call)
    with pytest.raises(RuntimeError, match="checked shared lock"):
        adapter.optimize("AUGGCUUAA", seed=7)
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(attempt_lock).result() is True  # Error paths release the lock too.
