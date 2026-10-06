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

import math
from collections.abc import Sequence
from functools import cache

import RNA

from engine.domain import FoldResult, StructureMatch


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
        cache_size: Maximum cached folds. Each entry holds a sequence and its structure,
            so 100k entries is roughly tens of MB. Raise it before raising the machine
            size.

    Example:
        >>> folder = FoldEngine(temperature=37.0)
        >>> result = folder.mfe("GGGAAACCC")
        >>> result.structure, result.energy
        ('(((...)))', -1.2)
    """

    def __init__(self, temperature: float = 37.0, cache_size: int = 100_000) -> None:
        self.temperature = temperature
        self._cache_size = cache_size

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
        model = RNA.md()
        model.temperature = self.temperature
        return RNA.fold_compound(strands, model)

    @cache  # noqa: B019 — one instance per run; see the class docstring
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

    @cache  # noqa: B019 — one instance per run; see the class docstring
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
        raise NotImplementedError("Step 5 — wrap RNA.ensemble_defect")

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

    @cache  # noqa: B019 — one instance per run; see the class docstring
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

    def sample_structures(
        self,
        strands: str,
        n_samples: int,
        forced_pairs: Sequence[tuple[int, int]] = (),
    ) -> list[str]:
        """Structures drawn from the real Boltzmann ensemble, not just the best one.

        Why it matters: :meth:`mfe` returns the *single* most stable structure, and a
        design can have a perfectly good MFE while spending most of its time in other
        conformations. Sampling is also the only way to ask a **joint** question — are
        two regions open in the *same* structure — which no pair of per-region marginals
        can answer, however they are combined: two regions can each be open in 90% of
        structures and never be open together in one.

        Args:
            strands: RNA, uppercase. One sequence, or several joined with ``&`` to fold
                as a complex — the same syntax and the same resulting indexing as
                :meth:`base_pair_probabilities`: positions run over the concatenation
                with the ``&`` removed, first strand first.
            n_samples: How many structures to draw.
            forced_pairs: ``(i, j)`` positions, **0-indexed into the same concatenated
                frame**, that every returned structure must contain. Use this to ask
                conditional questions: force a trigger's duplex to exist and see what
                the rest of the molecule then does. Converted to ViennaRNA's 1-indexed
                ``hc_add_bp`` with ``CONSTRAINT_CONTEXT_ENFORCE`` here, so no caller has
                to rediscover either convention. An empty sequence (the default) folds
                unconstrained.

        Returns:
            Dot-bracket strings, one per drawn structure. **May be shorter than
            ``n_samples``**: ViennaRNA's stochastic backtracking can fail on
            numerically awkward multiloops (it prints ``backtracking failed for qm2``
            and drops that draw), so callers must normalise by ``len(samples)`` and
            never by ``n_samples`` — dividing by the number *requested* silently
            understates every fraction when draws are lost.

        Not cached, unlike every other method here: these draws are stochastic, so
        handing a second caller the first caller's samples would make two measurements
        that are supposed to be independent silently identical.

        ``uniq_ML`` is required for stochastic backtracking and is set on a compound
        built here rather than in :meth:`_compound`, deliberately: turning it on for
        every caller would change the model behind :meth:`mfe`, :meth:`partition` and
        :meth:`base_pair_probabilities`, and every number already stored from them.
        """
        model = RNA.md()
        model.temperature = self.temperature
        model.uniq_ML = 1  # precondition for pbacktrack; scoped to sampling only
        fold_compound = RNA.fold_compound(strands, model)
        if forced_pairs:
            option = RNA.CONSTRAINT_CONTEXT_ALL_LOOPS | RNA.CONSTRAINT_CONTEXT_ENFORCE
            for i, j in forced_pairs:
                fold_compound.hc_add_bp(i + 1, j + 1, option)
        fold_compound.pf()
        return list(fold_compound.pbacktrack(n_samples))

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
        ``RT = R * T`` with ``R = 0.0019872`` kcal/mol/K and ``T = temperature + 273.15``.
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

    @cache  # noqa: B019 — one instance per run; see the class docstring
    def _constrained_probability_cached(
        self, strands: str, forced_pairs: tuple[tuple[int, int], ...]
    ) -> float | None:
        gas_constant = 0.0019872  # kcal/mol/K
        rt = gas_constant * (self.temperature + 273.15)

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
        probability = math.exp(-(free_forced - free_all) / rt)
        if not 0.0 < probability <= 1.0 + 1e-9:
            return None
        return min(probability, 1.0)

    def suboptimal(self, sequence: str, delta: float = 2.0) -> list[FoldResult]:
        """Every structure within an energy window of the MFE.

        Why it matters: if a switch has an alternative fold only 0.5 kcal/mol above its
        intended one, it will spend meaningful time in that state. Populating this early
        catches designs that look fine by MFE and misbehave in vitro.

        Args:
            sequence: RNA, uppercase.
            delta: Energy window in kcal/mol above the MFE. 2.0 is a reasonable default;
                widening it grows the result set very quickly.

        Returns:
            ``FoldResult`` list, sorted by energy ascending, with the MFE structure
            first.

        Implementation (Step 5):
            ``self._compound(sequence).subopt(int(delta * 100))`` — ViennaRNA takes the
            window in dekacal/mol, not kcal/mol. Getting that conversion wrong returns
            either one structure or millions.
        """
        raise NotImplementedError("Step 5 — wrap RNA.subopt")

    def layout_coordinates(self, structure: str) -> list[tuple[float, float]]:
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
        """
        points = RNA.naview_xy_coordinates(structure)
        return [(points[i].X, points[i].Y) for i in range(len(structure))]

    def versions(self) -> dict[str, str]:
        """The tool versions this run was computed with.

        Written into ``JobResult`` so that a result remains interpretable after an
        upgrade. Without it, "why does this run disagree with last month's?" is
        unanswerable.

        Returns:
            e.g. ``{"ViennaRNA": "2.7.2", "temperature_c": "37.0"}``. Include anything
            that changes the numbers, not only the library version.

        ``sampling_uniq_ml`` records that :meth:`sample_structures` folds with
        ``uniq_ML=1`` while every other method here does not — the two see slightly
        different models, and a stored result should say so rather than leave someone
        to discover it from a disagreement later.
        """
        return {
            "ViennaRNA": RNA.__version__,
            "temperature_c": str(self.temperature),
            "sampling_uniq_ml": "1",
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
    raise NotImplementedError("Step 5")
