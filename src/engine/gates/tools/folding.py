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
from functools import cache
from itertools import permutations

import RNA

from engine.domain import FoldResult, StructureMatch

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

    @cache  # noqa: B019 — one instance per run; see the class docstring
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
        """
        return {"ViennaRNA": RNA.__version__, "temperature_c": str(self.temperature)}


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
