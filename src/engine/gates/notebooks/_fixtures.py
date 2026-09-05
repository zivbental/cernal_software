"""Shared setup for the per-gate notebooks under this folder.

Each gate family has its own sub-folder (``toehold/``, ``antisense/`` …) holding one or
more notebooks; every one of them imports this module. A notebook drives **one** gate
family at a time — instantiate it, feed it a trigger set, call each method, look at what
comes back — without starting Django, the task worker or the pipeline. Every notebook's
first code cell walks up from its own folder to find this file, then::

    import _fixtures as fx
    fx.bootstrap()

and everything below is what that gives you.

Nothing in here is science:

* the sample triggers are made up, with plausible-looking numbers;
* :class:`StubFoldEngine` returns shaped-but-fake structures and energies so the
  sequence-construction parts of a gate can run on a machine with no ViennaRNA.

Swap in the real folder with ``fx.<gate>(host, real_fold=True)`` (or
``fx.fold_engine(real=True)``) once you want genuine structure predictions.

Every scientific method on a gate currently raises ``NotImplementedError("Step 5")``.
That is expected — :func:`attempt` catches it and prints ``pending Step 5`` rather than
a traceback, so a notebook still reads top to bottom today and becomes a live manual
test harness the moment the Step 5 bodies land.
"""

from __future__ import annotations

import itertools
import pathlib
import random
import sys

# --- make ``import engine...`` work from a notebook ------------------------------
# This file is  src/engine/gates/notebooks/_fixtures.py ; the package root is  src/ .
_SRC = pathlib.Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def bootstrap() -> pathlib.Path:
    """Put ``<repo>/src`` on ``sys.path`` and say where it pointed.

    Importing this module already did it; calling it explicitly keeps a notebook
    readable top to bottom and prints the path so you can confirm which checkout you
    are driving.
    """
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    print(f"engine package root: {_SRC}")
    return _SRC


from engine import sequences as sq  # noqa: E402  (path set up just above)
from engine.domain import (  # noqa: E402
    Compatibility,
    Constraints,
    FoldResult,
    GateDesign,
    GateKind,
    Host,
    ToolRequirement,
    TriggerCandidate,
    TriggerSet,
)
from engine.gates.antisense import AntisenseNotGate  # noqa: E402
from engine.gates.base import GateFamily  # noqa: E402
from engine.gates.crispr import CrisprGate  # noqa: E402
from engine.gates.toehold import ToeholdAndGate, ToeholdGate  # noqa: E402
from engine.gates.tools import binding  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

# Everything a notebook needs is reached through ``fx.`` — the domain types re-exported
# just above (so a notebook rarely writes its own ``from engine...`` import), the fake
# tools and sample-input builders below, and the gate builders and display helpers at
# the end. ``__all__`` is the public surface; the README repeats it in prose.
__all__ = [
    "Compatibility",
    "Constraints",
    "FoldResult",
    "GateDesign",
    "GateKind",
    "Host",
    "StubFoldEngine",
    "ToolRequirement",
    "TriggerCandidate",
    "TriggerSet",
    "antisense",
    "attempt",
    "binding",
    "bootstrap",
    "crispr",
    "describe_gate",
    "fold_engine",
    "sample_constraints",
    "sample_design",
    "sample_trigger",
    "sample_trigger_set",
    "sq",
    "toehold",
    "toehold_and",
]


# --- a fake FoldEngine ----------------------------------------------------------


class StubFoldEngine:
    """A stand-in for :class:`~engine.gates.tools.folding.FoldEngine`.

    Same method names, deterministic output, no ViennaRNA. Every sequence is reported
    as a simple hairpin — outer thirds paired, middle third open — with a negative
    energy proportional to the stem length. The shape is right; the numbers are not
    predictions. Use it to exercise a gate's construction logic before Step 5 wires
    the real folder in, or on any machine where ``import RNA`` fails.
    """

    temperature = 37.0

    @staticmethod
    def _stem(n: int) -> int:
        return max(0, n // 3)

    def mfe(self, sequence: str) -> FoldResult:
        n = len(sequence)
        stem = self._stem(n)
        structure = "(" * stem + "." * (n - 2 * stem) + ")" * stem
        energy = round(-0.53 * stem - 0.1 * (n % 7), 2)
        return FoldResult(structure=structure, energy=energy)

    def partition(self, sequence: str) -> float:
        return round(self.mfe(sequence).energy - 1.5, 2)

    def ensemble_defect(self, sequence: str, target: str) -> float:
        if len(sequence) != len(target):
            raise ValueError("target must be the same length as sequence")
        predicted = self.mfe(sequence).structure
        return float(sum(a != b for a, b in zip(predicted, target, strict=True)))

    def base_pair_probabilities(self, sequence: str) -> list[list[float]]:
        n = len(sequence)
        matrix = [[0.0] * n for _ in range(n)]
        stack: list[int] = []
        for i, char in enumerate(self.mfe(sequence).structure):
            if char == "(":
                stack.append(i)
            elif char == ")" and stack:
                j = stack.pop()
                matrix[i][j] = matrix[j][i] = 0.95
        return matrix

    def suboptimal(self, sequence: str, delta: float = 2.0) -> list[FoldResult]:
        best = self.mfe(sequence)
        unfolded = FoldResult(structure="." * len(sequence), energy=round(best.energy + delta, 2))
        return [best, unfolded]

    def versions(self) -> dict[str, str]:
        return {"StubFoldEngine": "fake-no-science", "temperature_c": "37.0"}


def fold_engine(real: bool = False, temperature: float = 37.0) -> object:
    """The folder to hand a gate.

    ``real=False`` (default) → :class:`StubFoldEngine`.
    ``real=True`` → the real :class:`FoldEngine`. With no ViennaRNA installed it still
    returns the real object; it raises the moment a method is called, which is the
    honest failure.
    """
    return FoldEngine(temperature=temperature) if real else StubFoldEngine()


# --- sample inputs ------------------------------------------------------------


def _rna(length: int, rng: random.Random) -> str:
    return "".join(rng.choice("ACGU") for _ in range(length))


def sample_trigger(
    *,
    trigger_id: str = "trig-000001",
    gene_id: str = "b0002",
    symbol: str = "thrA",
    sequence: str | None = None,
    length: int = 36,
    start_index: int = 120,
    seed: int = 2026,
) -> TriggerCandidate:
    """One made-up :class:`~engine.domain.TriggerCandidate` with plausible values.

    ``sequence`` defaults to a deterministic pseudo-random RNA ``length`` nt long.
    Any field can be overridden by keyword.
    """
    seq = (sequence or _rna(length, random.Random(seed))).upper()
    return TriggerCandidate(
        trigger_id=trigger_id,
        gene_id=gene_id,
        symbol=symbol,
        sequence=seq,
        start_index=start_index,
        openness=0.72,
        accessibility=0.61,
        mfe=-4.3,
        off_target_penalty=0.0,
        segment_specificity=0.88,
        gc_content=sq.gc_content(seq),
        aug_indexes=sq.find_augs(seq),
        stop_indexes=(),
        score=0.79,
    )


def sample_trigger_set(n_activators: int = 1, n_repressors: int = 0) -> TriggerSet:
    """A :class:`~engine.domain.TriggerSet` of made-up triggers.

    ``n_activators=2`` for the AND toehold; ``n_repressors=1`` (and
    ``n_activators=0``) for a NOT.
    """
    genes = [("b0002", "thrA"), ("b0114", "aceE"), ("b3236", "mdh")]

    def _trig(index: int, base_seed: int, prefix: int) -> TriggerCandidate:
        gene_id, symbol = genes[index % len(genes)]
        return sample_trigger(
            trigger_id=f"trig-{prefix + index:06d}",
            gene_id=gene_id,
            symbol=symbol,
            seed=base_seed + index,
        )

    activators = tuple(_trig(i, 2026, 1) for i in range(n_activators))
    repressors = tuple(_trig(i, 5000, 900) for i in range(n_repressors))
    return TriggerSet(activators=activators, repressors=repressors)


def sample_constraints(**overrides) -> Constraints:
    """A :class:`~engine.domain.Constraints` with library defaults; each keyword
    overrides one field (e.g. ``max_switch_length=160``)."""
    return Constraints(**overrides)


def sample_design(
    gate: GateFamily,
    trigger_set: TriggerSet | None = None,
    *,
    sequence: str | None = None,
) -> GateDesign:
    """A hand-built :class:`~engine.domain.GateDesign` for the output helpers.

    ``emit_sequence`` and ``describe`` are implemented today, but ``generate_designs``
    is not — so this lets you call them without waiting for Step 5. The sequence is a
    trivial ``AUG`` + Ala repeat unless you pass your own.
    """
    triggers = trigger_set or sample_trigger_set(n_activators=max(1, gate.max_inputs))
    return GateDesign(
        design_id="demo-000001",
        gate_kind=gate.kind,
        host=getattr(gate, "host", Host.ECOLI),
        trigger_set=triggers,
        sequence=(sequence or "AUG" + "GCU" * 20).upper(),
        architecture={"note": "hand-built by fx.sample_design"},
    )


# --- gate builders ----------------------------------------------------------


def toehold(host: Host = Host.ECOLI, *, real_fold: bool = False) -> ToeholdGate:
    """A wired :class:`~engine.gates.toehold.ToeholdGate`. Hosts: ECOLI, YEAST, HUMAN."""
    return ToeholdGate(host, fold_engine(real_fold), TranslationScorer(host), CodonOptimizer(host))


def toehold_and(host: Host = Host.ECOLI, *, real_fold: bool = False) -> ToeholdAndGate:
    """A wired :class:`~engine.gates.toehold.ToeholdAndGate` (two-input AND)."""
    return ToeholdAndGate(
        host, fold_engine(real_fold), TranslationScorer(host), CodonOptimizer(host)
    )


def antisense(
    host: Host = Host.ECOLI, *, payload: str, real_fold: bool = False
) -> AntisenseNotGate:
    """A wired :class:`~engine.gates.antisense.AntisenseNotGate`.

    ``payload`` is the gene this switch controls — a full CDS starting with a start
    codon, e.g. a GFP or mCherry sequence — and is required: the gate is generic over
    the payload gene, so there is no built-in default to fall back to. Pass whatever
    gene the scenario you're building calls for.
    """
    return AntisenseNotGate(host, fold_engine(real_fold), CodonOptimizer(host), payload)


def crispr(host: Host = Host.HUMAN, *, real_fold: bool = False) -> CrisprGate:
    """A wired :class:`~engine.gates.crispr.CrisprGate`. Eukaryotic only — hosts YEAST
    and HUMAN; ECOLI is rejected by ``is_compatible`` with a host-specific message."""
    return CrisprGate(host, fold_engine(real_fold))


# --- display helpers ------------------------------------------------------


def describe_gate(gate: GateFamily) -> None:
    """Print a gate's class-level declarations — the contract it advertises before you
    call anything on it."""
    cls = type(gate)
    print(f"{cls.__name__}   {gate!r}")
    print(f"  name             {cls.name}")
    print(f"  version          {cls.version}")
    print(f"  kind             {cls.kind}")
    print(f"  label            {cls.label}")
    print(f"  description      {cls.description}")
    print(f"  max_inputs       {cls.max_inputs}")
    print(f"  available        {cls.available}")
    print(f"  supported_hosts  {sorted(h.value for h in cls.supported_hosts)}")
    host = getattr(gate, "host", None)
    if host is not None:
        print(f"  instance host    {host.value}   supports(host)={gate.supports(host)}")


def _show(value: object, limit: int = 6) -> None:
    if hasattr(value, "__next__"):  # a generator / iterator — materialise a few
        head = list(itertools.islice(value, limit))
        print(f"  <iterator>  first {len(head)}:")
        for item in head:
            print(f"    {item!r}")
        return
    if isinstance(value, (list, tuple)) and len(value) > limit:
        print(f"  {type(value).__name__} of {len(value)}, first {limit}:")
        for item in value[:limit]:
            print(f"    {item!r}")
        return
    print(f"  {value!r}")


def attempt(label: str, call) -> object | None:
    """Run ``call()`` and display the result.

    A ``NotImplementedError`` is reported as ``pending Step 5`` instead of raising —
    every scientific gate method raises it until the bodies land, and that is the
    expected state here. Any other exception is printed with its type and message so
    the notebook keeps going; call the method directly if you want the full traceback.
    """
    try:
        value = call()
    except NotImplementedError as exc:
        print(f"pending Step 5 :: {label}  ->  {exc}")
        return None
    except Exception as exc:  # a manual harness wants the message, not a stack trace
        print(f"error :: {label}  ->  {type(exc).__name__}: {exc}")
        return None
    print(f"ok :: {label}")
    _show(value)
    return value
