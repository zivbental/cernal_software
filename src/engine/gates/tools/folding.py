"""S2, S4 — RNA secondary structure prediction for gate designs.

**The only place a gate family folds anything.** Every chemistry here folds: a toehold's
hairpin, an antisense duplex and a blocked sgRNA are all structural predictions, and all
three must be made the same way or their numbers are not comparable. That is what makes
this a shared gate tool rather than something each family carries.

Stage-side accessibility profiling (S1, ``RNAplfold``) is a different entry point with
its own window parameters and no shared cache, and lives in ``engine.stages.folding``.

Everything else asks these classes rather than ViennaRNA directly. That gives four
things:

1. **A shared cache.** The same subsequence is folded hundreds of times across a run —
   every toehold length variant re-folds most of the same stem. Caching is the single
   largest speed win available (see docs/ROADMAP.md §3: folding is ~15 ms per
   design, and it dominates total runtime).
2. **One recorded version.** A result computed under ViennaRNA 2.7 is not comparable
   with one from 2.6. ``FoldEngine.versions()`` is written into every ``JobResult``.
3. **One place to swap the library.** NUPACK, or a lab-specific solver, replaces this
   module and nothing else.
4. **One stub point for tests.** Faking this module fakes all design-side folding, so
   the gate families can be tested without ViennaRNA installed at all.

Background: a toehold switch works because its OFF state is a hairpin that sequesters
the ribosome binding site, and the trigger opens it by strand displacement. Everything
this module computes is in service of predicting whether that actually happens.

Bodies land in Step 5 (docs/ROADMAP.md E1).
"""

import json
import math
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict
from functools import lru_cache
from hashlib import sha256
from itertools import permutations
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from types import SimpleNamespace

import RNA

from engine import sequences
from engine.domain import FoldingConfig, FoldResult, StructureMatch
from engine.errors import EngineError, StructureLayoutUnavailable
from engine.gates.tools import VIENNA_PARAMETER_LOCK
from engine.gates.tools.rnaviz.layout import build_bases_and_links
from engine.gates.tools.rnaviz.models import Base, Link

# ViennaRNA's ``pf()`` returns a C ``float``, so every ensemble free energy this module
# handles lands exactly on the single-precision grid — verified by round-tripping real
# outputs through ``struct.pack("<f", ...)``. At the magnitudes an AND-gate tube reaches
# (|G| of 40 to 210 kcal/mol) one step is 3.8e-06 to 1.5e-05 kcal/mol, so a *difference*
# of two such energies -- which is what every opening cost and every ``separation`` is --
# carries about 3e-05 kcal/mol of quantisation.
#
# **Two numbers closer than this are not equal, they are unresolved.** Nothing here can
# distinguish them, and no threshold should be set inside that band. Quoted as the
# coarsest case so it is a bound rather than an estimate.
_FLOAT32_ENERGY_ULP = 3.1e-05

# Presentation limit only: bounds native layout work, never filters scientific designs.
_MAX_STRUCTURE_LAYOUT_NT = 2_000


# All CERNAL snapshot creation and compound construction shares this lock. Native folds
# use copied parameters after leaving it. Never load an energy file for every fold.
_PARAMETER_LOCK = VIENNA_PARAMETER_LOCK
# ViennaRNA's random generator is process-global: held while seeding and drawing.
_SAMPLING_LOCK = Lock()
_ENERGY_TABLES = {
    "turner2004": RNA.parameter_set_rna_turner2004,
    "turner1999": RNA.parameter_set_rna_turner1999,
    "andronescu2007": RNA.parameter_set_rna_andronescu2007,
}


def _model(config: FoldingConfig, window_size: int, max_bp_span: int, uniq_ml: int):
    """Explicit scalar defaults: RNA.md()/reset() otherwise inherit mutable globals."""
    return RNA.md(
        temperature=config.temperature_celsius,
        dangles=config.dangles,
        special_hp=int(config.special_hairpins),
        noLP=int(config.no_lonely_pairs),
        noGU=int(config.no_gu),
        noGUclosure=int(config.no_gu_closure),
        betaScale=1.0,
        pf_smooth=1,
        logML=0,
        circ=0,
        circ_penalty=1,
        gquad=0,
        uniq_ML=uniq_ml,
        energy_set=0,
        backtrack=1,
        backtrack_type="F",
        compute_bpp=1,
        max_bp_span=max_bp_span,
        min_loop_size=3,
        window_size=window_size,
        oldAliEn=0,
        ribo=0,
        cv_fact=1.0,
        nc_fact=1.0,
        sfact=1.07,
        salt=config.salt_molar,
        saltMLLower=6,
        saltMLUpper=24,
        saltDPXInit=99999,
        saltDPXInitFact=-45.324,
        helical_rise=2.8,
        backbone_length=6.0,
    )


def _fresh_parameters(model):
    # ViennaRNA 2.7.2 caches RNA.param/exp_param by model details only: loading a
    # different energy table does NOT invalidate these caches. First request a model
    # that differs from the wanted one, then the wanted one, for BOTH parameter types.
    other = RNA.md()
    other.temperature = model.temperature + 1.0
    RNA.param(other)
    parameters = RNA.param(model)
    RNA.exp_param(other)
    exp_parameters = RNA.exp_param(model)
    return parameters, exp_parameters


@lru_cache(maxsize=32)
def _parameter_snapshot(config: FoldingConfig, window_size: int, max_bp_span: int, uniq_ml: int):
    """Snapshot bundled tables once, restoring the previous global tables even on error.

    Caller holds _PARAMETER_LOCK. Only native objects copied into compounds are used
    for calculations. The cache key includes every configurable model field and each
    algorithm override; no snapshot or global energy setting is a run's mutable state.
    """
    model = _model(config, window_size, max_bp_span, uniq_ml)
    text = _ENERGY_TABLES[config.energy_parameters]
    digest = sha256(text.encode("utf-8")).hexdigest()
    label = f"cernal:{config.energy_parameters}:{digest}"
    previous_name = RNA.last_parameter_file() or ""
    with TemporaryDirectory(prefix="cernal-parameters-") as directory:
        previous_path = Path(directory) / "previous.par"
        if not RNA.params_save(str(previous_path)):
            raise RuntimeError("Could not snapshot ViennaRNA energy parameters.")
        previous = previous_path.read_text(encoding="utf-8")
        try:
            if not RNA.params_load_from_string(text, label):
                raise RuntimeError(f"Could not load ViennaRNA energy parameters: {label}")
            parameters, exp_parameters = _fresh_parameters(model)
            if parameters.param_file != label or exp_parameters.param_file != label:
                raise RuntimeError("ViennaRNA did not apply the requested energy parameter set.")
        finally:
            if not RNA.params_load_from_string(previous, previous_name):
                raise RuntimeError("Could not restore ViennaRNA energy parameters.")
            # Also restore parameter caches, not merely the raw global tables.
            _fresh_parameters(RNA.md())
    details = parameters.model_details
    effective = {
        name: getattr(details, name)
        for name in dir(details)
        if not name.startswith("_")
        and name not in ("this", "thisown", "alias", "pair", "rtype", "nonstandards")
        and not callable(getattr(details, name))
    }
    provenance = {
        "schema": "cernal-folding-model-v1",
        "viennarna_version": RNA.__version__,
        "configuration": asdict(config),
        "model_details": effective,
        "sequence_length_normalization": {
            "window_size": "clamped to nucleotide count; -1 means full length",
            "max_bp_span": "clamped to window size; -1 means full window",
        },
        "energy_parameters": {
            "name": config.energy_parameters,
            "source": f"ViennaRNA.parameter_set_rna_{config.energy_parameters}",
            "sha256": digest,
            "hash_basis": "UTF-8 bytes of the bundled parameter string loaded",
            "loaded_identity": parameters.param_file,
        },
        "ensemble_caveats": (
            [
                "ViennaRNA noLP excludes pairs that cannot stack; "
                "lonely pairs may remain in ensembles."
            ]
            if config.no_lonely_pairs
            else []
        ),
        "suboptimal_model_override": {"uniq_ML": 1},
        "sampling_model_override": {"uniq_ML": 1},
    }
    return parameters, exp_parameters, json.dumps(provenance, sort_keys=True, allow_nan=False)


def folding_provenance(
    config: FoldingConfig, *, window_size: int = -1, max_bp_span: int = -1, uniq_ml: int = 0
) -> dict:
    """Return detached JSON-compatible evidence of the actual parameter snapshots."""
    with _PARAMETER_LOCK:
        _, _, encoded = _parameter_snapshot(config, window_size, max_bp_span, uniq_ml)
        return json.loads(encoded)


def configured_compound(
    strands: str,
    config: FoldingConfig,
    *,
    window_size: int = -1,
    max_bp_span: int = -1,
    uniq_ml: int = 0,
    options: int = 0,
):
    """The shared model/energy authority for design, RNAplfold and suboptimal folds."""
    with _PARAMETER_LOCK:
        parameters, exp_parameters, _ = _parameter_snapshot(
            config, window_size, max_bp_span, uniq_ml
        )
        compound = RNA.fold_compound(
            strands, _model(config, window_size, max_bp_span, uniq_ml), options
        )
        compound.params_subst(parameters)
        compound.exp_params_subst(exp_parameters)
        # pf() sanitizes these fields and reloads GLOBAL tables if MFE/PF model
        # details differ afterward. Normalize both snapshots before that check,
        # including sequences whose MFE is zero (mfe/rescale is not a sufficient fix).
        length = len(strands) - strands.count("&")
        effective_window = min(window_size, length) if window_size > 0 else length
        effective_span = min(max_bp_span, effective_window) if max_bp_span > 0 else effective_window
        for parameters_copy in (compound.params, compound.exp_params):
            parameters_copy.model_details.window_size = effective_window
            parameters_copy.model_details.max_bp_span = effective_span
        compound.exp_params_rescale()
    return compound


def _contains_pairs(structure: str, pairs: Sequence[tuple[int, int]]) -> bool:
    """Whether a dot-bracket string (``&`` ignored) pairs every ``(i, j)`` in ``pairs``."""
    stack: list[int] = []
    partner: dict[int, int] = {}
    for position, char in enumerate(structure.replace("&", "")):
        if char == "(":
            stack.append(position)
        elif char == ")":
            opener = stack.pop()
            partner[opener] = position
            partner[position] = opener
    return all(partner.get(i) == j for i, j in pairs)


class FoldEngine:
    """S2 — minimum free energy, ensemble properties and suboptimal structures.

    **Construct exactly once per run and pass it down.** The cache lives on the
    instance, so four instances means four cold caches, and — worse — four opportunities
    for someone to construct one with a different temperature. Two designs folded at
    different temperatures produce numbers that ``engine.scoring`` will happily normalise
    onto the same axis as though they were comparable.

    Args:
        temperature: Folding temperature in degrees Celsius. 37 is the ViennaRNA default
            and matches mammalian culture; *E. coli* work is often done at 37 too, but a
            wet-lab protocol at 30 should be reflected here. **Recorded on the run** —
            it changes every energy this module returns.
        config: Immutable run-wide model. Use ``FoldingConfig`` for energy table,
            dangling ends, special hairpins, lonely pairs and GU options. Its validated
            defaults are explicit; global ViennaRNA settings never configure a run.
        cache_size: Maximum cached folds. Each entry holds a sequence and its structure,
            so 100k entries is roughly tens of MB. Raise it before raising the machine
            size.

    Example:
        >>> folder = FoldEngine(temperature=37.0)
        >>> result = folder.mfe("GGGAAACCC")
        >>> result.structure, result.energy
        ('(((...)))', -1.2)
    """

    def __init__(
        self,
        temperature: float = 37.0,
        cache_size: int = 1_024,
        *,
        config: FoldingConfig | None = None,
    ) -> None:
        if config is not None and temperature != 37.0:
            raise ValueError("Pass either config or a nondefault temperature, not both.")
        self._config = (
            config if config is not None else FoldingConfig(temperature_celsius=temperature)
        )
        if not isinstance(self._config, FoldingConfig):
            raise ValueError("config must be a FoldingConfig.")
        self._provenance = json.dumps(folding_provenance(self._config), sort_keys=True)
        if isinstance(cache_size, bool) or not isinstance(cache_size, int) or cache_size < 0:
            raise ValueError("cache_size must be a nonnegative integer")
        self._cache_size = cache_size
        self.constrained_free_energy = lru_cache(maxsize=min(cache_size, 4096))(
            self.constrained_free_energy
        )
        # Instance-owned wrappers retain no tools through a class-level cache. Cycles
        # between an instance and its bound wrappers are reclaimed by Python's GC.
        for name in (
            "mfe",
            "structure_energy",
            "partition",
            "_partition_with_unpaired",
            "_constrained_probability_cached",
        ):
            setattr(self, name, lru_cache(maxsize=cache_size)(getattr(self, name)))
        self._base_pair_probabilities_cached = lru_cache(maxsize=min(cache_size, 2))(
            self._base_pair_probabilities_cached
        )

    @property
    def config(self) -> FoldingConfig:
        return self._config

    @property
    def temperature(self) -> float:
        return self.config.temperature_celsius

    def provenance(self) -> dict:
        return json.loads(self._provenance)

    def _compound(self, strands: str) -> RNA.fold_compound:
        """Build a ``fold_compound`` at this engine's temperature.

        Shared by every method on this class that needs one, so the model — and
        therefore the temperature — is built exactly one way here. Duplicating this in
        each method risks one of them reading the global ``RNA.cvar.temperature``
        instead, which is exactly the split-brain the class docstring warns about.

        Args:
            strands: RNA, uppercase. A single sequence to fold alone, or multiple
                sequences joined with ``&`` to fold as a complex — ViennaRNA's
                dimer/multi-strand syntax. A toehold's ON state (switch + trigger) must
                be folded this way, as a true dimer, not as one concatenated strand —
                concatenating covalently joins two molecules that are not covalently
                joined, which is a different, wrong physical system.

        An explicit ``RNA.md()`` model carries the temperature rather than mutating
        ``RNA.cvar.temperature``, which is process-global and unsafe once folding moves
        to a process pool (see docs/ROADMAP.md §3).
        """
        return configured_compound(strands, self.config)

    def mfe(self, strands: str) -> FoldResult:
        """Fold a sequence — or a multi-strand complex — and return its most stable
        predicted structure.

        The workhorse. Called for the switch alone (OFF state), the trigger alone, and
        the switch-plus-trigger complex (ON state).

        Args:
            strands: RNA, uppercase, A/C/G/U only. Pass DNA and ViennaRNA will
                misinterpret T — convert with ``sequences.to_rna`` first. For a
                complex, join the strands with ``&`` (e.g. ``f"{switch}&{trigger}"``)
                rather than passing a list — see ``_compound`` for why a concatenated
                strand is wrong, and the class docstring for why this stays a plain
                ``str``: it is what keeps this method's cache key hashable, the same
                reason trigger sets elsewhere in the engine are tuples, not lists.

        Returns:
            ``FoldResult(structure, energy)`` where ``structure`` is dot-bracket
            notation (``.`` unpaired, ``(``/``)`` paired) over the combined strands —
            same total length as ``strands`` with the ``&`` removed — and ``energy`` is
            the minimum free energy in kcal/mol. **More negative means more stable**,
            so a switch's OFF state should be strongly negative and the difference
            between OFF and ON is what drives the design.

        Gotchas:
            * Results are cached on ``strands`` only. If you ever make the model
              configurable per call, the cache key must include it.
            * ViennaRNA returns energies in kcal/mol; NUPACK also uses kcal/mol but
              different parameter sets. Do not mix them within a run.
        """
        fc = self._compound(strands)
        structure, energy = fc.mfe()
        return FoldResult(structure=structure, energy=energy)

    def structure_energy(self, strands: str, structure: str) -> float | None:
        """Energy of one **given** structure, rather than the best one.

        ``mfe`` asks "what will this fold into?"; this asks "what would it cost to hold it
        like *this*?" — the question a designed duplex needs, where the alignment is
        imposed by the design and not up for negotiation.

        Args:
            strands: RNA, uppercase, ``&``-joined for a complex, as everywhere else here.
            structure: Dot-bracket over the strands **with the ``&`` removed**, same
                length as ``strands`` minus its separators.

        Returns:
            Free energy in kcal/mol, or ``None`` if the structure is not evaluable under
            the model.

        Gotchas:
            * ViennaRNA wants the separator-free structure here even though the compound
              was built with ``&``; passing it back in returns the sentinel below instead
              of raising, and the wrong number then flows onward looking plausible.
            * It signals "impossible" by **returning** ``1e5``-ish rather than raising, so
              a ``try``/``except`` around this call catches nothing. That is checked for
              here, once, so no caller has to remember it.
        """
        if len(structure) != len(strands) - strands.count("&"):
            raise ValueError(
                f"structure is {len(structure)} long but {strands.count('&') + 1} strands "
                f"hold {len(strands) - strands.count('&')} nucleotides"
            )
        energy = float(self._compound(strands).eval_structure(structure))
        return energy if abs(energy) < 1e4 else None

    def partition(self, sequence: str) -> float:
        """Ensemble free energy over all structures, not just the most stable one.

        Why it matters: MFE reports a single structure, but RNA in solution occupies a
        distribution. A switch whose MFE looks perfect but whose ensemble is dominated
        by other conformations will leak. The gap between the MFE and the ensemble free
        energy is a rough measure of how committed a sequence is to one fold.

        Args:
            sequence: RNA, uppercase.

        Returns:
            Ensemble free energy in kcal/mol. Always less than or equal to the MFE.

        Implementation (Step 5):
            ``fc = self._compound(sequence); _, energy = fc.pf()``. Note that ``pf()``
            must be called after ``mfe()`` on the same compound if you want both, or the
            compound rescales internally.
        """
        fold_compound = self._compound(sequence)
        _, energy = fold_compound.pf()
        return energy

    @property
    def rt(self) -> float:
        """``RT`` in kcal/mol at this engine's temperature.

        Taken from ViennaRNA's own constants rather than a literal, so it cannot drift
        from the model the energies were computed under.
        """
        return (RNA.GASCONST / 1000.0) * (self.temperature + RNA.K0)

    @staticmethod
    def _strand_orders(strands: str) -> list[str]:
        """One representative per distinct circular ordering of the strands.

        ViennaRNA's multi-strand partition function only counts structures that are
        non-crossing when the strands are laid out in the given order, so the answer
        depends on that order. It is invariant under *rotation* — measured here as
        exactly 0.0000 kcal/mol across the three rotations of a class — but not under
        reordering, so there are ``(n-1)!`` genuinely different answers. Fixing the first
        strand and permuting the rest enumerates exactly one representative of each, and
        keeps strand 0 at offset 0 so a window into it never needs remapping.
        """
        head, *rest = strands.split("&")
        return ["&".join((head, *tail)) for tail in permutations(rest)]

    def _partition_with_unpaired(self, strands: str, unpaired: tuple[int, ...]) -> float:
        """Ensemble free energy with every 1-based position in ``unpaired`` forced open."""
        fold_compound = self._compound(strands)
        for position in unpaired:
            fold_compound.hc_add_up(position)
        _, energy = fold_compound.pf()
        return energy

    def _combine(self, energies: list[float]) -> float:
        """Free energy of the union of several ensembles, summed in Boltzmann space.

        Shifted by the minimum before exponentiating, because ``exp(-G / RT)`` overflows a
        float64 once ``|G|`` passes about **437 kcal/mol** — reached by a complex of a few
        hundred nucleotides, and by the constrained ensembles here sooner than by the free
        ones. (An earlier version of this docstring justified the shift with
        ``exp(80 / 0.616)``, which does not overflow at all: it is 2.4e+56.) The shift is
        algebraically exact — ``floor`` is added back — and cancels in any ratio of two
        combined ensembles; checked against a 60-digit unshifted reference to 3.2e-15
        kcal/mol, including cases where the two sides have different minima.
        """
        floor = min(energies)
        total = math.fsum(math.exp(-(energy - floor) / self.rt) for energy in energies)
        return floor - self.rt * math.log(total)

    def p_open(self, strands: str, window: tuple[int, int]) -> float | None:
        """Joint probability that **every** base in ``window`` is unpaired at once.

        Not the average of per-base unpaired probabilities, and much smaller than it: if
        every base of a 30-nt window is 90% open the average reads 0.90 while the joint
        probability is far lower, because the bases are correlated — a closed stem shuts a
        whole block at once. This is the quantity a ribosome footprint needs, since the
        30S entry channel holds only single-stranded RNA and the whole threaded window
        must be open simultaneously in the assembled complex.

        Args:
            strands: RNA, uppercase, ``&``-joined for a complex — the same convention and
                the same reason (a hashable cache key) as ``mfe``.
            window: ``(start, end)`` into **the first strand**, 0-based, inclusive start,
                exclusive end — the engine's convention everywhere. Converted to
                ViennaRNA's 1-based indexing here so that no caller has to.

        Returns:
            A probability in [0, 1], or ``None`` if the ensemble came back non-finite.
            ``None`` rather than ``0.0`` because a hard filter reads 0.0 as a perfectly
            closed window instead of as a measurement that failed.

        Raises:
            ValueError: if the window is empty, reversed, or runs off the first strand.
                That is always a bug upstream, not a bad design, and an off-by-one here
                still folds and still scores.

        Note:
            Pooled over all ``(n-1)!`` strand orderings, numerator and denominator alike,
            each weighted by its own population — so this is a Boltzmann average, not a
            mean over orderings. That distinction is not cosmetic: on a real 161+36+50 nt
            AND-gate tube the two orderings differ by **46.8 kcal/mol**, so the pooled
            answer is the dominant ordering's to every bit, while an unweighted mean would
            have reported ``dG_open`` 8.02 instead of 7.59. An earlier version of this note
            claimed the spread was 2.75 kcal/mol and cancelled between the two sides;
            measured across ten real designs it is 10.9 to 22.1 kcal/mol and does not
            cancel — the pooling simply lets the populated ordering win. Use
            ``p_open_by_order`` to see the spread.

            Why the orderings differ so much: ViennaRNA counts only structures that are
            non-crossing in the written order, and ``switch&B&A`` makes trigger A's arcs
            cross trigger B's, forbidding the both-bound state. That ordering therefore
            describes a *different* physical situation, and is correctly given a weight of
            ``1.1e-33`` rather than half the answer.

            This is not NUPACK's exact treatment, which restricts each complex to connected
            structures and applies a symmetry correction; ViennaRNA counts disconnected
            states too, so a structure representable in several orderings is counted
            several times. Pooling both sides over the same orderings is what makes that
            cancel to first order.

        Warning:
            The result is resolved to about ``4.9e-05`` *relatively*, because it is built
            from two single-precision energies — see ``_FLOAT32_ENERGY_ULP``. Two tubes
            whose probabilities agree to the last bit have been measured as equal to
            within the instrument, not proven identical.
        """
        by_order = self.p_open_by_order(strands, window)
        if by_order is None:
            return None
        constrained, unconstrained = by_order[1], by_order[2]
        cost = self._combine(constrained) - self._combine(unconstrained)
        probability = math.exp(-cost / self.rt)
        if probability == 0.0:
            # exp underflows once the cost passes ~459 kcal/mol, and 0.0 is the one value
            # this must never return: a hard filter reads it as a perfectly closed window
            # instead of as a window too closed to measure. Real 30-nt footprints top out
            # near 22 kcal/mol, so this is headroom, not a live path.
            return None
        # The constrained ensemble is a subset of the unconstrained one, so the cost is
        # non-negative in exact arithmetic. ViennaRNA returns single-precision energies,
        # so a window with nothing left to pair can measure one ulp the wrong way and
        # produce a probability just above 1 -- exactly the regime a working ON state
        # reaches. Clamp inside that noise band; anything larger is a real inconsistency.
        if probability > 1.0:
            return 1.0 if cost > -_FLOAT32_ENERGY_ULP else None
        return probability

    def p_open_by_order(
        self, strands: str, window: tuple[int, int]
    ) -> tuple[list[float], list[float], list[float]] | None:
        """``p_open`` resolved per strand ordering, for auditing the spread above.

        Returns:
            ``(probabilities, constrained_energies, unconstrained_energies)``, one entry
            each per ordering from ``_strand_orders``, or ``None`` if any came back
            non-finite. For one or two strands there is a single ordering and the spread
            is necessarily zero — the degeneracy only appears from three strands up.
        """
        start, end = window
        first = strands.split("&")[0]
        if not 0 <= start < end <= len(first):
            raise ValueError(
                f"window {window} is not a non-empty range inside the first strand "
                f"(length {len(first)})"
            )
        positions = tuple(range(start + 1, end + 1))

        constrained: list[float] = []
        unconstrained: list[float] = []
        for order in self._strand_orders(strands):
            constrained.append(self._partition_with_unpaired(order, positions))
            unconstrained.append(self.partition(order))
        if not all(math.isfinite(e) for e in (*constrained, *unconstrained)):
            return None
        probabilities = [
            math.exp(-(c - u) / self.rt) for c, u in zip(constrained, unconstrained, strict=True)
        ]
        return probabilities, constrained, unconstrained

    @staticmethod
    def validate_target(sequence: str, target: str) -> None:
        """Reject malformed single-strand dot-bracket structures before native calls."""
        if not target or len(target) != len(sequence):
            raise ValueError("Target structure must be nonempty and match the sequence length.")
        depth = 0
        for symbol in target:
            if symbol not in ".()":
                raise ValueError("Target structure contains invalid dot-bracket symbols.")
            depth += (symbol == "(") - (symbol == ")")
            if depth < 0:
                raise ValueError("Target structure has unbalanced parentheses.")
        if depth:
            raise ValueError("Target structure has unbalanced parentheses.")

    @staticmethod
    def structure_layout(sequence: str, structure: str) -> tuple[list[Base], list[Link]]:
        """Lay out an existing single-strand structure without folding or scoring it.

        Coordinates reproduce cernal-rnaviz's default NAVIEW geometry. Selecting the
        algorithm explicitly avoids reading or mutating ``RNA.cvar.rna_plot_type``.
        The 2,000 nt cap is a viewer limit, not a scientific validity rule. No fold
        compound, thermodynamic model, cache, file or network service is involved.
        """
        if not isinstance(sequence, str) or not isinstance(structure, str):
            raise ValueError("Stored sequence and structure must be text.")
        if sequence != sequence.upper() or not sequences.is_valid_rna(sequence):
            raise ValueError("Stored sequence must contain only uppercase RNA bases A/C/G/U.")
        FoldEngine.validate_target(sequence, structure)
        if len(sequence) > _MAX_STRUCTURE_LAYOUT_NT:
            raise StructureLayoutUnavailable(
                f"Stored structure exceeds the {_MAX_STRUCTURE_LAYOUT_NT:,} nt viewer limit."
            )

        try:
            coordinates = {
                index: SimpleNamespace(X=x, Y=y)
                for index, (x, y) in enumerate(FoldEngine.layout_coordinates(structure))
            }
            bases, links = build_bases_and_links(sequence, coordinates, RNA.ptable(structure))
        except (RuntimeError, SystemError, ValueError, OverflowError) as exc:
            raise EngineError("Stored structure layout could not be generated.") from exc
        return bases, links

    def ensemble_defect(self, sequence: str, target: str) -> float:
        """How far the predicted ensemble sits from an intended structure.

        This is the metric that answers *"did the generator actually build the hairpin it
        meant to build?"*. A toehold generator produces a sequence intended to fold into
        a specific stem-loop; this measures the expected number of nucleotides in the
        wrong pairing state.

        Args:
            sequence: RNA, uppercase.
            target: Dot-bracket notation, same length as ``sequence``, describing the
                structure the generator intended.

        Returns:
            Expected number of incorrectly paired bases, from 0 (the ensemble is exactly
            the target) upward. Divide by sequence length for a comparable fraction —
            ``SwitchDesign.structure_deviation`` stores the **normalised** value so that
            designs of different lengths can be compared.

        Implementation (Step 5):
            ``fc = self._compound(sequence); fc.pf(); fc.ensemble_defect(target)``.

        Gotchas:
            * ``target`` must be balanced and the same length as ``sequence``, or
              ViennaRNA raises. Validate before calling.
            * A low defect does not mean the switch works — only that it folds as
              designed. Leakage and trigger binding are separate questions.
        """
        if len(target) != len(sequence):
            raise ValueError(
                f"target is {len(target)} long but sequence is {len(sequence)}; "
                "a length mismatch is always a bug upstream"
            )
        self.validate_target(sequence, target)
        fold_compound = self._compound(sequence)
        fold_compound.pf()
        # ViennaRNA's ensemble_defect is already divided by length, despite the name;
        # this method's contract is the raw count, which the caller then normalises.
        return fold_compound.ensemble_defect(target) * len(sequence)

    def base_pair_probabilities(self, sequence: str) -> list[list[float]]:
        """Probability that each pair of positions is bonded, over the whole ensemble.

        Used for diagnostics and for accessibility calculations that need more detail
        than ``FoldProfiler`` gives. The results view can render this as a heat map.

        Args:
            sequence: RNA, uppercase. May be a ViennaRNA cofold pair written as
                ``"switch&trigger"`` — ``fold_compound`` folds that as one two-strand
                ensemble, and the returned matrix is indexed over the concatenation with
                the ``&`` removed, switch positions first. Antisense leakage needs exactly
                this: how open the switch's initiation region is *with the trigger bound*,
                not in isolation.

        Returns:
            An n-by-n matrix where entry [i][j] is the probability that position i pairs
            with position j. Symmetric, and the diagonal is zero. **Memory grows with the
            square of length** — do not call this for a whole plasmid.

        Implementation (Step 5):
            ``fc = self._compound(sequence); fc.pf(); fc.bpp()``. ViennaRNA's matrix is
            1-indexed and upper-triangular; convert to 0-indexed and symmetric here so
            callers do not each rediscover that.
        """
        # Cached as an immutable tuple-of-tuples, then copied out as a fresh
        # list-of-lists per call — @cache on this method directly would hand every
        # caller the *same* mutable matrix, and one caller mutating it would corrupt
        # every other caller's view for the rest of the run.
        return [list(row) for row in self._base_pair_probabilities_cached(sequence)]

    def pooled_pair_probabilities(self, strands: str) -> list[list[float]]:
        """``base_pair_probabilities`` Boltzmann-averaged over all strand orderings.

        **Use this, not ``base_pair_probabilities``, whenever there are three or more
        strands.** ViennaRNA counts only structures that are non-crossing in the order the
        strands are written, and from three strands up the orderings are not
        interchangeable: one of them can make two binders' arcs cross and so forbid the
        both-bound structure entirely. Measured on a 161+36+50 nt AND-gate tube, the two
        orderings of the same three molecules give per-base unpaired probabilities
        differing by up to **0.997**, because ``switch&B&A`` crosses trigger A out of the
        complex while ``switch&A&B`` nests it. A caller that simply writes the strands in
        some order gets one of those two answers with nothing to say which.

        Each ordering is weighted by its own ensemble population, exactly as ``p_open``
        weights its numerator and denominator, so a geometrically forbidden ordering
        contributes in proportion to how populated it actually is — on that same tube,
        ``1.1e-33``, which is why the existing numbers do not move.

        Args:
            strands: RNA, uppercase, ``&``-joined. One or two strands have a single
                ordering, so this returns the same matrix as ``base_pair_probabilities``.

        Returns:
            An n-by-n matrix indexed over the concatenation **in the order given**, the
            same convention as ``base_pair_probabilities``. Every ordering's matrix is
            mapped back onto those positions before averaging, so a caller's indices never
            depend on which ordering happened to dominate.
        """
        orders = self._strand_orders(strands)
        if len(orders) == 1:
            return self.base_pair_probabilities(strands)

        canonical = strands.split("&")
        energies = [self.partition(order) for order in orders]
        floor = min(energies)
        weights = [math.exp(-(energy - floor) / self.rt) for energy in energies]
        total = math.fsum(weights)

        width = sum(len(strand) for strand in canonical)
        pooled = [[0.0] * width for _ in range(width)]
        for order, weight in zip(orders, weights, strict=True):
            if weight / total == 0.0:  # underflowed; contributes nothing to any entry
                continue
            index = self._position_map(order.split("&"), canonical)
            matrix = self.base_pair_probabilities(order)
            share = weight / total
            for i, row in enumerate(matrix):
                target = pooled[index[i]]
                for j, probability in enumerate(row):
                    if probability:
                        target[index[j]] += share * probability
        return pooled

    @staticmethod
    def _position_map(order: list[str], canonical: list[str]) -> list[int]:
        """Index in the canonical concatenation for each index in ``order``'s.

        The orderings permute the strands, so position *k* means a different nucleotide in
        each one. Built by matching strands left to right and consuming each canonical
        strand once, so repeated identical strands map to distinct copies rather than all
        collapsing onto the first.
        """
        starts, cursor = [], 0
        for strand in canonical:
            starts.append(cursor)
            cursor += len(strand)

        taken = [False] * len(canonical)
        mapping: list[int] = []
        for strand in order:
            for position, candidate in enumerate(canonical):
                if not taken[position] and candidate == strand:
                    taken[position] = True
                    mapping.extend(range(starts[position], starts[position] + len(strand)))
                    break
            else:  # pragma: no cover — _strand_orders only ever permutes
                raise ValueError(f"{strand!r} is not an unused strand of the original")
        return mapping

    def _base_pair_probabilities_cached(self, sequence: str) -> tuple[tuple[float, ...], ...]:
        fold_compound = self._compound(sequence)
        fold_compound.pf()
        raw = fold_compound.bpp()  # 1-indexed, upper-triangular, row 0 unused
        n = len(raw) - 1
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(1, n + 1):
            row = raw[i]
            for j in range(i + 1, n + 1):
                probability = row[j]
                if probability:
                    matrix[i - 1][j - 1] = probability
                    matrix[j - 1][i - 1] = probability
        return tuple(tuple(row) for row in matrix)

    def constrained_probability(
        self, strands: str, forced_pairs: Sequence[tuple[int, int]]
    ) -> float | None:
        """Exact probability that **all** of ``forced_pairs`` are present at once.

        Why it exists: a joint event such as "both designed duplexes are formed in the
        same structure" cannot be read off the pair-probability matrix, whose entries
        are marginals — the product of marginals is only a bound under independence.
        The partition-function ratio answers it exactly, with no sampling noise (on
        multi-strand complexes :meth:`sample_structures` was measured to disagree badly
        with the exact probabilities, and more draws do not fix it)::

            P(all forced pairs) = Z(forced) / Z = exp(-(G_forced - G) / RT)

        where ``Z(forced)`` is the partition function restricted to structures that
        contain every forced pair, ``G`` the unconstrained ensemble free energy, and
        ``RT`` is :attr:`rt` (ViennaRNA's own gas constant at this engine's temperature).
        For a single forced pair this equals the matching
        :meth:`base_pair_probabilities` entry exactly.

        Args:
            strands: RNA, uppercase; one sequence or several joined with ``&`` — the
                same syntax and indexing as :meth:`sample_structures`.
            forced_pairs: ``(i, j)`` positions, **0-indexed over the concatenation with
                the** ``&`` **removed**, that must all be paired. Converted here to
                ViennaRNA's 1-indexed ``hc_add_bp`` with all-loop-context enforcement.

        Returns:
            A probability in ``(0, 1]``, or ``None`` — never ``0.0`` — when
            ``forced_pairs`` is empty (nothing to ask), the constraints cannot all hold
            (an impossible pair, or pairs that conflict), or ViennaRNA fails.

        Numerics: both compounds run ``mfe()`` and ``exp_params_rescale(mfe)`` before
        ``pf()`` so the Boltzmann factors are scaled to the same energy scale and long
        complexes do not overflow. Cached on ``(strands, forced_pairs)``.
        """
        pairs = tuple((int(i), int(j)) for i, j in forced_pairs)
        if not pairs:
            return None
        return self._constrained_probability_cached(strands, pairs)

    def _constrained_probability_cached(
        self, strands: str, forced_pairs: tuple[tuple[int, int], ...]
    ) -> float | None:
        rt = self.rt

        def free_energy(pairs: tuple[tuple[int, int], ...]) -> float | None:
            fold_compound = self._compound(strands)
            if pairs:
                option = RNA.CONSTRAINT_CONTEXT_ALL_LOOPS | RNA.CONSTRAINT_CONTEXT_ENFORCE
                for i, j in pairs:
                    fold_compound.hc_add_bp(i + 1, j + 1, option)
            structure, mfe_energy = fold_compound.mfe()
            if pairs and not _contains_pairs(structure, pairs):
                # ViennaRNA silently drops a forced pair it cannot place (and an
                # enforced set that conflicts), which would read back as P = 1.0.
                return None
            fold_compound.exp_params_rescale(mfe_energy)
            _, energy = fold_compound.pf()
            return energy

        try:
            free_forced = free_energy(forced_pairs)
            free_all = free_energy(())
        except Exception:  # ViennaRNA raises bare RuntimeError/ValueError
            return None
        # An infeasible constraint set yields a non-finite or absurdly high energy.
        if free_forced is None or free_all is None:
            return None
        if not (free_forced == free_forced and free_all == free_all):
            return None
        if free_forced - free_all > 100.0:
            return None
        cost = free_forced - free_all
        probability = math.exp(-cost / rt)
        if probability == 0.0:
            return None
        # Same clamp as ``p_open``: the constrained ensemble is a subset of the free one,
        # so ``cost`` is non-negative in exact arithmetic; single-precision energies can put
        # a near-certain event one ulp the wrong way (probability just above 1).
        if probability > 1.0:
            return 1.0 if cost > -_FLOAT32_ENERGY_ULP else None
        return probability

    def sample_structures(
        self,
        strands: str,
        n_samples: int,
        seed: int | None = None,
        first_strand: int | None = None,
    ) -> list[str]:
        """Structures drawn from the Boltzmann ensemble, not just the best one.

        :meth:`mfe` returns the single most stable structure; sampling shows what the
        molecule does the rest of the time, and is the only way to ask a joint question
        ("is region X open *in the same structure* as region Y?").

        Args:
            strands: RNA, uppercase. One sequence, or several joined with ``&``; same
                indexing as :meth:`base_pair_probabilities` (positions over the
                concatenation with the ``&`` removed, first strand first). The strand order
                must already be one ViennaRNA can represent without a pseudoknot.
            n_samples: How many structures to draw.
            seed: If given, seeds ViennaRNA's random generator before drawing. That
                generator is process-global, so seeding and drawing run under a lock and
                concurrent seeded calls in one process are serialized (each reproducible);
                an unseeded call still advances the shared generator.
            first_strand: Index (in ``strands``) of the strand to write first when drawing;
                the others follow in their cyclic order, so the structure stays nested.
                ``None`` writes the last strand first (the validated choice for a switch
                with its trigger: the trigger first). See the strand-order gotcha below.

        Returns:
            Dot-bracket strings (``&`` removed, in the caller's strand order). **May be
            shorter than ``n_samples``**: ViennaRNA's stochastic backtracking can drop a
            draw on a numerically awkward multiloop, so normalise by ``len(result)``,
            never by ``n_samples``.

        Not cached: draws are stochastic, so a second caller must not receive the first
        caller's samples.

        Gotchas:
            * ``uniq_ML`` is required for stochastic backtracking. The compound comes from
              :func:`configured_compound` (so ``no_gu``, dangles, energy tables and the
              parameter lock match :meth:`mfe`, :meth:`partition` and
              :meth:`base_pair_probabilities`) with ``uniq_ml=1`` as the only override,
              recorded in :meth:`provenance` as ``sampling_model_override``.
            * **Strand order matters.** ViennaRNA's ``pbacktrack`` can draw from the wrong
              ensemble depending on which strand is written first: for real ~120-nt
              switches plus their trigger, ``switch&trigger`` never drew the MFE and
              returned structures with Boltzmann weight ~1e-11 as 70-75% of draws, while
              ``trigger&switch`` matched exp(-(E-G)/RT) and the exact stem marginals. In a
              switch with two hairpins and one trigger, the order that matched was the
              one with the trigger on the side of the switch nearest its target hairpin
              (trigger first for the 5' hairpin, last for the 3' one); the other order
              drew the untargeted hairpin open. Not exact either (on a 57-nt construct the
              top structure came out 4 points under its Boltzmann probability). Check
              marginals built from samples against :meth:`base_pair_probabilities`.
        """
        parts = strands.split("&")
        count = len(parts)
        first = (count - 1) if first_strand is None else first_strand
        if not 0 <= first < count:
            raise ValueError(f"first_strand {first_strand} is outside the {count} strands")
        order = [(first + k) % count for k in range(count)]  # a cyclic rotation: stays nested
        drawn_order = "&".join(parts[i] for i in order)
        # Same model, energy tables and parameter lock as every other fold; only uniq_ML
        # differs, which stochastic backtracking requires (see the provenance record).
        fold_compound = configured_compound(drawn_order, self.config, uniq_ml=1)
        fold_compound.pf()
        # ViennaRNA's generator is process-global: seeding and drawing must not interleave
        # with another seeded draw in this process, or neither is reproducible.
        with _SAMPLING_LOCK:
            if seed is not None:
                RNA.init_rand(seed)
            drawn = list(fold_compound.pbacktrack(n_samples))
        if count == 1 or order == list(range(count)):
            return drawn
        # Map each position of the drawn frame back to the caller's strand order.
        original_start = [sum(len(parts[j]) for j in range(i)) for i in range(count)]
        to_original: list[int] = []
        for i in order:
            to_original.extend(original_start[i] + k for k in range(len(parts[i])))
        total = len(to_original)
        mapped = []
        for structure in drawn:
            out = ["."] * total
            stack: list[int] = []
            for i, char in enumerate(structure):
                if char == "(":
                    stack.append(i)
                elif char == ")":
                    a, b = sorted((to_original[stack.pop()], to_original[i]))
                    out[a], out[b] = "(", ")"
            mapped.append("".join(out))
        return mapped

    def suboptimal(
        self,
        sequence: str,
        delta: float = 2.0,
        *,
        max_structures: int = 1000,
        timeout_seconds: float = 2.0,
    ) -> list[FoldResult]:
        """Enumerate exact structures within ``delta`` kcal/mol of MFE.

        Supports one uppercase RNA strand of at most 150 nt, delta 0..5,
        max_structures 1..10000 and timeout_seconds (0,30]. An isolated native
        process enforces time/count limits; exceeding either raises an error and
        never returns a truncated ensemble. Results sort by energy and structure.
        The set is thermodynamic and supplies no calibrated cellular kinetics.
        """
        return self._bounded_suboptimal(
            sequence, delta, max_structures=max_structures, timeout_seconds=timeout_seconds
        )

    def _bounded_suboptimal(
        self,
        sequence: str,
        delta: float,
        *,
        max_structures: int = 1000,
        timeout_seconds: float = 2.0,
    ) -> list[FoldResult]:
        """Exact enumeration in an isolated native process with count/time bounds."""
        if not sequence or len(sequence) > 150 or any(base not in "ACGU" for base in sequence):
            raise ValueError(
                "Suboptimal enumeration requires one uppercase RNA strand of 1..150 nt."
            )
        if (
            isinstance(delta, bool)
            or not isinstance(delta, (int, float))
            or not math.isfinite(delta)
            or not 0 <= delta <= 5
        ):
            raise ValueError("Suboptimal delta must be finite and between 0 and 5 kcal/mol.")
        if (
            isinstance(max_structures, bool)
            or not isinstance(max_structures, int)
            or not 1 <= max_structures <= 10000
        ):
            raise ValueError("max_structures must be an integer between 1 and 10000.")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 30
        ):
            raise ValueError("timeout_seconds must be between 0 and 30 seconds.")
        payload = json.dumps(
            {
                "sequence": sequence,
                "folding": asdict(self.config),
                "delta": delta,
                "max_structures": max_structures,
            },
            allow_nan=False,
        )
        # Pytest/source-checkout callers can import through sys.path without exporting
        # PYTHONPATH. Bootstrap the same package tree explicitly; its parent is src
        # in a checkout and site-packages for an installed package. Keep caller cwd
        # and environment untouched while loading this exact engine implementation.
        package_root = str(Path(__file__).resolve().parents[3])
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys\n"
                    f"sys.path.insert(0, {package_root!r})\n"
                    "from engine.gates.tools.folding import _suboptimal_worker\n"
                    "_suboptimal_worker()",
                ],
                input=payload,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                "Suboptimal enumeration exceeded its native-process time limit."
            ) from exc
        response = json.loads(completed.stdout)
        if response.get("error"):
            raise ValueError(response["error"])
        return [FoldResult(structure, energy) for structure, energy in response["results"]]

    def mfe_with_window_open(self, strands: str, window: tuple[int, int]) -> tuple[str, float]:
        """The most stable structure that leaves ``window`` single-stranded.

        The endpoint a refolding path has to reach for a trigger to nucleate. Constrained
        with the same ``hc_add_up`` mechanism ``p_open`` uses, so "open" means the same
        thing in both, and the window is 0-based half-open into the first strand as it is
        everywhere else in this engine.

        Returns:
            ``(structure, energy)`` with the structure carrying an ``&`` for each strand
            junction, matching ``mfe``.
        """
        start, end = window
        first = strands.split("&")[0]
        if not 0 <= start < end <= len(first):
            raise ValueError(f"window {window} is not inside the first strand")
        fold_compound = self._compound(strands)
        for position in range(start + 1, end + 1):
            fold_compound.hc_add_up(position)
        structure, energy = fold_compound.mfe()
        return structure, energy

    def refolding_saddle(
        self, strands: str, start: str, target: str, *, width: int = 20
    ) -> float | None:
        """Highest energy on a direct refolding path from ``start`` to ``target``.

        ViennaRNA's ``findpath``: a breadth-limited search over direct paths, which gives
        the barrier height a rate depends on without enumerating a landscape. It is a
        heuristic, so it can only **over**-estimate the true saddle, never under-estimate
        it — the result is a conservative bound, and a wider search can only lower it.

        Args:
            strands: RNA, uppercase, ``&``-joined as elsewhere.
            start: Dot-bracket for the starting structure, same ``&`` convention.
            target: Dot-bracket for the structure being refolded into.
            width: findpath's search width. Higher is tighter and costs linearly.

        Returns:
            The saddle energy in **kcal/mol**, or ``None`` if the search failed.

        Gotchas:
            * ``path_findpath_saddle`` returns an integer in **dekacal/mol** — 320 means
              3.20 kcal/mol. Converted here so no caller rediscovers it, the same trap
              ``subopt``'s integer window sets.
            * Both structures must be over the same sequence and balanced, or ViennaRNA
              returns a meaningless answer rather than raising.
        """
        if len(start) != len(target):
            raise ValueError(f"structures differ in length: {len(start)} vs {len(target)}")
        saddle = self._compound(strands).path_findpath_saddle(start, target, width)
        if saddle is None:
            return None
        return float(saddle) / 100.0

    @staticmethod
    def layout_coordinates(structure: str) -> list[tuple[float, float]]:
        """Where each nucleotide sits when a structure is drawn, one point per base.

        ViennaRNA's naview layout — the same algorithm behind ``RNAplot`` and the familiar
        forna-style pictures — solved here rather than by a caller, because this module is
        the only one permitted to reach for the folding library at all.

        Args:
            structure: Dot-bracket, balanced. Multi-strand structures must already have
                their ``&`` removed, since the layout is over a single coordinate space.

        Returns:
            ``(x, y)`` per position, in the layout's own arbitrary units and **y-up**
            orientation. A caller drawing SVG has to flip y and scale to its own box; no
            normalisation is done here because the sensible scale depends on the target.

        Gotchas:
            * The underlying vector comes back one entry longer than the structure — the
              trailing point is padding, not a base — and is trimmed here so no caller
              rediscovers it as a stray point at the origin.
            * A one-nucleotide NAVIEW layout is nonfinite in ViennaRNA 2.7.2; its sole
              point is placed at the origin. All returned coordinates must be finite.
        """
        if not isinstance(structure, str):
            raise ValueError("Stored structure must be text.")
        FoldEngine.validate_target("A" * len(structure), structure)
        if len(structure) == 1:
            return [(0.0, 0.0)]
        try:
            points = RNA.naview_xy_coordinates(structure)
            if not points or len(points) < len(structure):
                raise EngineError("Stored structure layout returned incomplete coordinates.")
            coordinates = [(points[i].X, points[i].Y) for i in range(len(structure))]
        except (RuntimeError, SystemError, ValueError, OverflowError) as exc:
            raise EngineError("Stored structure layout could not be generated.") from exc
        if not all(math.isfinite(x) and math.isfinite(y) for x, y in coordinates):
            raise EngineError("Stored structure layout returned nonfinite coordinates.")
        return coordinates

    def constrained_free_energy(self, strands: str, constraint: str = "") -> float:
        """Partition free energy, using FcAB (connected states) for a heterodimer.

        Constraints use ViennaRNA notation: x is forced unpaired, parentheses
        force a specific pair, and . is unconstrained. Indices exclude '&'.
        A 999 FcAB means no connected ensemble; it is represented internally by
        +inf, never exposed as a successful measurement or an arbitrary score.
        Impossible target pairs also give +inf (zero constrained partition).
        Malformed constraints raise ValueError; they are not empty physical events.
        Numerical PF failures raise; callers distinguish errors from threshold rejections.
        """
        parts = strands.split("&")
        if len(parts) not in (1, 2) or any(not p or set(p) - set("ACGU") for p in parts):
            raise ValueError("Expected one or two non-empty uppercase RNA strands")
        if not math.isfinite(self.temperature) or self.temperature <= -273.15:
            raise ValueError("Invalid folding temperature")
        n = sum(map(len, parts))
        if constraint and (len(constraint) != n or set(constraint) - set(".x()")):
            raise ValueError("Invalid constraint length or alphabet")
        if constraint:
            self.validate_target("".join(parts), constraint.replace("x", "."))
        fc = self._compound(strands)
        if constraint:
            # ENFORCE_BP can introduce noncanonical pairs or silently drop pairs
            # with too short a hairpin. Neither is a subset of the original ensemble.
            # Check against this compound's model before calling the native parser.
            model = fc.params.model_details
            encoded = fc.sequence_encoding
            cut = len(parts[0])
            stack = []
            for j, char in enumerate(constraint):
                if char == "(":
                    stack.append(j)
                elif char == ")":
                    i = stack.pop()
                    same_strand = (i < cut) == (j < cut)
                    pair_type = model.pair[encoded[i + 1]][encoded[j + 1]]
                    if (
                        not pair_type
                        or (model.noGU and pair_type in (3, 4))
                        or (same_strand and j - i <= model.min_loop_size)
                        or (model.max_bp_span > 0 and j - i > model.max_bp_span)
                    ):
                        return math.inf  # A validly specified, empty event.
            if not fc.hc_add_from_db(
                constraint, RNA.CONSTRAINT_DB_DEFAULT | RNA.CONSTRAINT_DB_ENFORCE_BP
            ):
                raise ArithmeticError("Native constraint parser failed")
        if len(parts) == 2:
            # Python 2.7 bindings: structure, FA, FB, FcAB, FAB.
            # A forced interstrand pair makes isolated FA/FB infinite by design.
            # Only the connected ensemble and its containing total are relevant here.
            _, _, _, energy, fab = fc.pf_dimer()
            if energy == 999.0:
                return math.inf
            if not math.isfinite(fab) or abs(fab) >= 1e4:
                raise ArithmeticError("Dimer partition calculation failed")
        else:
            _, energy = fc.pf()
        if not math.isfinite(energy) or abs(energy) >= 1e4:
            raise ArithmeticError("Partition calculation failed")
        return float(energy)

    def constraint_probability(self, strands: str, constraint: str) -> float:
        """Joint event Z_constrained / Z; never multiply marginal probabilities."""
        reference = self.constrained_free_energy(strands)
        if not math.isfinite(reference):
            raise ValueError("No connected two-strand ensemble")
        constrained = self.constrained_free_energy(strands, constraint)
        if constrained == math.inf:
            return 0.0  # A measured empty subset, not a failed measurement.
        rt = self.rt
        log_p = (reference - constrained) / rt
        if log_p > 2e-5:
            raise ArithmeticError("Constrained partition function exceeds total")
        return math.exp(min(0.0, log_p))

    def region_accessibility(self, strands: str, start: int, end: int) -> float:
        """Probability every nucleotide in [start, end) is simultaneously unpaired."""
        n = len(strands.replace("&", ""))
        if not 0 <= start < end <= n:
            raise ValueError("Invalid accessibility interval")
        return self.constraint_probability(
            strands, "." * start + "x" * (end - start) + "." * (n - end)
        )

    def region_defect(self, strands: str, reference: str, start: int = 0) -> float:
        """Normalized expected incorrect bases in a region of the first strand.

        start is a zero-based offset; reference describes only the region.

        Constrained PF ratios work for connected dimers as well as monomers;
        this avoids confusing cofold's null-model BPP with conditional gT BPP.
        Every target pair is counted twice, once for each nucleotide.
        """
        n = len(strands.replace("&", ""))
        if (
            not reference
            or type(start) is not int
            or start < 0
            or start + len(reference) > len(strands.split("&")[0])
        ):
            raise ValueError("Invalid reference region")
        stack, partners = [], {}
        for i, char in enumerate(reference):
            if char == "(":
                stack.append(i)
            elif char == ")" and stack:
                j = stack.pop()
                partners[i], partners[j] = j, i
            elif char != ".":
                raise ValueError("Scaffold reference must be balanced dot-bracket")
        if stack:
            raise ValueError("Unbalanced scaffold reference")
        correct = 0.0
        for i, char in enumerate(reference):
            if char == ")":
                continue
            constraint = ["."] * n
            if char == ".":
                constraint[start + i] = "x"
                count = 1
            else:
                constraint[start + i], constraint[start + partners[i]] = "(", ")"
                count = 2
            correct += count * self.constraint_probability(strands, "".join(constraint))
        return max(0.0, min(1.0, 1.0 - correct / len(reference)))

    def binding_free_energy(self, strand_a: str, strand_b: str) -> float:
        """Standard binding free energy from connected AB and free A/B ensembles.

        Concentrations are not needed for this quantity. It does not predict
        the fraction of strands bound in a solution.
        """
        if "&" in strand_a or "&" in strand_b:
            raise ValueError("Supply two individual strands")
        dg = (
            self.constrained_free_energy(strand_a + "&" + strand_b)
            - self.constrained_free_energy(strand_a)
            - self.constrained_free_energy(strand_b)
        )
        if not math.isfinite(dg):
            raise ValueError("No connected strand_a-strand_b ensemble")
        return dg

    def heterodimer_equilibrium(
        self,
        strand_a: str,
        strand_b: str,
        a_molar: float,
        b_molar: float,
    ) -> tuple[float, float]:
        """Return (binding free energy, fraction of A bound) for {A, B, AB}.

        Total concentrations are in M. This restricted model excludes homodimers
        and larger complexes. It has no assumptions about biological regions or
        strand lengths. Callers decide which observables to mix by bound fraction.
        """
        if not (math.isfinite(a_molar) and math.isfinite(b_molar) and a_molar > 0 and b_molar > 0):
            raise ValueError("Require finite positive strand concentrations")
        dg = self.binding_free_energy(strand_a, strand_b)
        rt = self.rt
        # Solve x = K (g0-x)(t0-x), in logs, with K relative to 1 M standard state.
        # Bisection avoids quadratic cancellation and overflowing exp(-dG/RT).
        lo, hi = 0.0, min(a_molar, b_molar)
        for _ in range(100):
            x = (lo + hi) / 2
            if x == lo or x == hi:
                break
            log_ratio = math.log(x) - math.log(a_molar - x) - math.log(b_molar - x)
            if log_ratio < -dg / rt:
                lo = x
            else:
                hi = x
        fraction = ((lo + hi) / 2) / a_molar
        return dg, fraction

    def versions(self) -> dict[str, str]:
        """The tool versions this run was computed with.

        Written into ``JobResult`` so that a result remains interpretable after an
        upgrade. Without it, "why does this run disagree with last month's?" is
        unanswerable.

        Returns:
            The legacy version/temperature strings plus canonical JSON ``folding_model``
            with effective model fields and loaded energy-table identity and SHA-256.
            ``provenance()`` exposes the same evidence as a structured dictionary.
        """
        provenance = self.provenance()
        return {
            "ViennaRNA": RNA.__version__,
            "temperature_c": str(self.temperature),
            "folding_model": json.dumps(provenance, sort_keys=True, separators=(",", ":")),
        }


def structure_match(dot_bracket: str, target_structure: str) -> StructureMatch:
    """S4 — compare a predicted structure against the one a generator intended.

    Cheaper than ``FoldEngine.ensemble_defect`` and answers a slightly different
    question: this compares two specific structures, where ensemble defect compares a
    structure against the whole distribution. Use this for a fast reject, and ensemble
    defect for the number that goes into scoring.

    Args:
        dot_bracket: The predicted structure, from ``FoldEngine.mfe``.
        target_structure: What the generator intended, same length.

    Returns:
        ``StructureMatch(deviation, p_target_fold)`` where ``deviation`` is the fraction
        of positions in the wrong state (0.0 is a perfect match) and ``p_target_fold`` is
        the Boltzmann probability of the target structure.

    Implementation (Step 5):
        Deviation is a position-wise comparison — count positions where paired/unpaired
        state differs, divide by length. ``p_target_fold`` needs the partition function:
        ``exp(-(E_target - E_ensemble) / RT)``.

    Raises:
        ValueError: if the two structures are different lengths, which always means a
            bug upstream rather than a bad design.
    """
    FoldEngine.validate_target("A" * len(dot_bracket), dot_bracket)
    FoldEngine.validate_target("A" * len(dot_bracket), target_structure)

    def partners(structure: str) -> list[int | None]:
        result: list[int | None] = [None] * len(structure)
        stack: list[int] = []
        for index, symbol in enumerate(structure):
            if symbol == "(":
                stack.append(index)
            elif symbol == ")":
                other = stack.pop()
                result[index] = other
                result[other] = index
        return result

    predicted, intended = partners(dot_bracket), partners(target_structure)
    deviation = sum(a != b for a, b in zip(predicted, intended, strict=True)) / len(predicted)
    # Structures alone carry no molecule or model energy: a Boltzmann probability
    # cannot be inferred from this signature and remains explicitly unavailable.
    return StructureMatch(deviation=deviation, p_target_fold=None)


def _suboptimal_worker() -> None:
    """Private subprocess entry: do not execute native enumeration in a long-lived worker."""
    request = json.loads(sys.stdin.read())
    config = FoldingConfig.from_mapping(request["folding"])
    compound = configured_compound(request["sequence"], config, uniq_ml=1)
    results: dict[str, float] = {}

    def collect(structure, energy, _data):
        if structure is None:
            return
        results[structure] = float(energy)
        if len(results) > request["max_structures"]:
            print(
                json.dumps(
                    {"error": "Suboptimal count limit reached; complete ensemble unavailable."}
                ),
                flush=True,
            )
            # This is the isolated native-enumeration child, not a job worker. A hard
            # exit stops the C callback/recursion immediately without retaining state.
            os._exit(0)

    compound.subopt_cb(round(request["delta"] * 100), collect)
    ordered = sorted(results.items(), key=lambda item: (item[1], item[0]))
    print(json.dumps({"results": ordered}, allow_nan=False), flush=True)
