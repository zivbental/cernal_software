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

        Shifted by the minimum before exponentiating: a 160-nt complex sits near
        -80 kcal/mol, and ``exp(80 / 0.616)`` overflows a float long before the sum does.
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
            Summed over all ``(n-1)!`` strand orderings, numerator and denominator alike.
            The spread between orderings is **not** negligible and does not cancel in the
            ratio: measured on a 160+36+50 nt triple it is 2.75 kcal/mol in ``dG_open``
            — above the folding model's own ~1.5 kcal/mol error — because the
            unconstrained ensembles differ far more between orderings (3.29 kcal/mol)
            than the constrained ones do (0.54). Use ``p_open_by_order`` to see it.
            This is not NUPACK's exact treatment, which restricts each complex to
            connected structures and applies a symmetry correction; ViennaRNA counts
            disconnected states too, so a structure representable in several orderings is
            counted several times. Summing both sides over the same orderings is what
            makes that cancel to first order.
        """
        by_order = self.p_open_by_order(strands, window)
        if by_order is None:
            return None
        constrained, unconstrained = by_order[1], by_order[2]
        return math.exp(-(self._combine(constrained) - self._combine(unconstrained)) / self.rt)

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
