"""Stage 1 — gene selection.

Narrows a whole transcriptome to the handful of genes worth building a circuit around.

The criteria are all about **separation**: a useful gene is one whose expression tells
the two cell states apart cleanly. That is not the same as "most differentially
expressed" — a gene with a huge fold change between two barely-detectable values is
statistically impressive and biologically useless, because a switch cannot respond to
transcripts that are not there. A real check against a real public comparison
(docs/genes.md §1) put exactly this failure at the top of the naive ranking: a
pseudogene at an 8.9-million-fold change and an unlabelled row above the first gene a
synthetic biologist would actually recognise.

CERNAL does **not** run differential expression. The researcher supplies DESeq2-style
results; this stage filters and ranks them.

This is a **budget allocation**, not a sort (docs/genes.md §4): the shortlist decides
what the entire rest of the run is allowed to look at, and nothing downstream can
recover a gene stage 1 dropped. Five largely independent questions decide it — does the
gene separate the two states, is it expressed in a usable range, can a trigger even be
built from its transcript, does it say something the other selected genes don't, and is
either direction actually constructible today — and this stage answers as many of them
as the input happens to support, never fewer by silently defaulting a missing one to
"passing" or a missing number to zero. A run given only a bare DE table (no count
matrix, no transcript sequences, no reference atlas — the shape of every public dataset
this product ships today) still produces a ranked shortlist; it just cannot answer
questions 2 through 5, and says so through ``on_warning`` rather than pretending
otherwise.
"""

from bisect import bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from statistics import StatisticsError, correlation, mean

from engine import sequences as sq
from engine.domain import Constraints, CountMatrix, DgeRow, DgeTable, Regulation, SelectedGene
from engine.errors import InputValidationError
from engine.stages.motifs import MotifScreener

#: Fraction of rows needing a raw p-value before a Benjamini-Hochberg correction is
#: trusted (docs/genes.md §4.1). BH's own math needs the complete rank ordering of every
#: tested gene; a table with only partial coverage cannot support a valid FDR, and every
#: public dataset this product ships is pre-truncated to the top rows by fold change
#: (docs/public-datasets.md §3), which would make a computed FDR anti-conservative.
#: A data-quality gate on *which computation path runs* — not an undeclared scientific
#: filter on results, the same distinction ``TriggerScorer.TOP_K_PER_GENE`` draws for
#: its own class-constant budget knob.
_BH_COVERAGE_THRESHOLD = 0.95


@dataclass(slots=True)
class _Candidate:
    """Stage 1's own scratch record for one gene mid-selection.

    Not ``SelectedGene`` — this carries the per-axis intermediate values and the
    per-sample expression vector needed for the redundancy pass (docs/genes.md §4.3),
    none of which belong on the record a caller receives. Discarded once ``select``
    returns; never crosses a stage boundary, so it needs neither ``frozen`` nor the
    house rules that apply to ``domain.py``.
    """

    gene_id: str
    symbol: str
    regulation: Regulation
    log2_fold_change: float
    p_adj: float | None
    control_percentile: float | None
    condition_percentile: float | None
    condition_specificity: float | None
    trigger_yield: float | None
    usable_windows: int | None
    separation_score: float
    abundance_score: float | None
    vector: tuple[float, ...] | None
    base_score: float
    final_score: float = field(default=0.0)


class _Significance:
    """Which significance tier applies to this table, and the pass/fail rule for it.

    Exactly one of four shapes, chosen once for the whole table rather than row by row
    (docs/genes.md §4.1) — a table either has an adjusted p-value column, or it doesn't,
    for every row alike:

    * ``"padj"`` — the table has its own adjusted p-value. Used as-is.
    * ``"bh"`` — no adjusted p-value, but a raw p-value for (near) every row. A
      Benjamini-Hochberg correction is computed once and used as if it were the table's
      own ``p_adj``.
    * ``"raw"`` — a raw p-value, but too incomplete to support a valid FDR. Filtered on
      the raw, uncorrected value instead, at the same numeric threshold — never presented
      as an adjusted one.
    * ``"none"`` — no p-value of any kind (every curated *E. coli* comparison in the
      public catalog, docs/genes.md §2). No significance filter is applied; the other
      axes carry the whole ranking.
    """

    def __init__(
        self, mode: str, max_p_adj: float, qvalues: dict[str, float] | None = None
    ) -> None:
        self.mode = mode
        self.max_p_adj = max_p_adj
        self.qvalues = qvalues or {}

    def passes(self, row: DgeRow) -> bool:
        if self.mode == "padj":
            return row.p_adj is not None and row.p_adj <= self.max_p_adj
        if self.mode == "bh":
            q = self.qvalues.get(row.gene_id)
            return q is not None and q <= self.max_p_adj
        if self.mode == "raw":
            return row.p_value is not None and row.p_value <= self.max_p_adj
        return True

    def adjusted_p(self, row: DgeRow) -> float | None:
        """The value to record on ``SelectedGene.p_adj`` — never a raw p-value wearing
        an adjusted one's name (docs/public-datasets.md §2.1 draws the same line for the
        ingestion layer)."""
        if self.mode == "padj":
            return row.p_adj
        if self.mode == "bh":
            return self.qvalues.get(row.gene_id)
        return None


def _benjamini_hochberg(p_by_gene: dict[str, float]) -> dict[str, float]:
    """The standard BH step-up adjusted p-value (q-value) for every gene, by id.

    Sorted ascending by raw p-value; ``q_i = p_i * n / rank_i``, then corrected right to
    left so a q-value never exceeds any q-value at a larger rank (the step-up procedure's
    own monotonicity requirement — without it, "adjusted" p-values could decrease as the
    raw p-value increases, which is not a valid FDR).
    """
    ranked = sorted(p_by_gene.items(), key=lambda item: (item[1], item[0]))
    n = len(ranked)
    raw_q = [p_value * n / rank for rank, (_gene_id, p_value) in enumerate(ranked, start=1)]
    for i in range(n - 2, -1, -1):
        raw_q[i] = min(raw_q[i], raw_q[i + 1])
    return {gene_id: min(1.0, q) for (gene_id, _p), q in zip(ranked, raw_q, strict=True)}


def _directional_expression(
    row: DgeRow, regulation: Regulation
) -> tuple[float | None, float | None]:
    """``(on_state_expression, off_state_expression)`` for this gene's direction.

    An UP gene's ON state is the condition group; a DOWN gene's ON state is control — it
    is highly expressed there and drops in the condition (``Regulation``'s own
    docstring). Falls back to ``base_mean`` — DESeq2's overall mean, the common case for
    a real export — when no per-group mean is available; that fallback can only answer
    "is there enough signal at all", never which state would leak, since it does not
    distinguish the two groups.
    """
    if regulation is Regulation.UP:
        on_expr, off_expr = row.target_mean, row.control_mean
    else:
        on_expr, off_expr = row.control_mean, row.target_mean
    if on_expr is None and off_expr is None:
        return row.base_mean, None
    return on_expr, off_expr


def _abundance_score(
    on_expr: float | None, off_expr: float | None, constraints: Constraints
) -> float | None:
    """0-1: how comfortably this gene's expression sits inside the configured window.

    ``None`` when neither bound is configured (nothing to score against) or neither
    expression value is available (nothing to score). Worst of the two margins wins —
    "usable in both states" is an AND, not an average; a gene that clears the floor by a
    mile while leaking badly over the ceiling is not rescued by the floor margin.

    The margin shape (distance past the bound as a fraction of the bound itself,
    clipped to [0, 1]) is a simple, documented, explicitly provisional choice — the same
    status ``DEFAULT_V1``'s own weights carry (docs/ROADMAP.md Q6).
    """
    if constraints.min_base_expression is None and constraints.max_base_expression is None:
        return None

    margins: list[float] = []
    if constraints.min_base_expression is not None and on_expr is not None:
        floor = constraints.min_base_expression
        margin = 1.0 if floor <= 0 else (on_expr - floor) / floor
        margins.append(max(0.0, min(1.0, margin)))
    if constraints.max_base_expression is not None and off_expr is not None:
        ceiling = constraints.max_base_expression
        margin = 1.0 if ceiling <= 0 else (ceiling - off_expr) / ceiling
        margins.append(max(0.0, min(1.0, margin)))

    return min(margins) if margins else None


def _separation_score(
    effect: float, constraints: Constraints, percentile_gap: float | None
) -> float:
    """0-1 from the effect size, refined by the percentile gap when one is available.

    Two genes with an identical fold change can differ sharply in where they sit within
    their own group's distribution (the original stub's own step 4) — the percentile gap
    is folded in as a minority tiebreak (15%) rather than a separate top-level axis, so it
    sharpens a close call without letting a single noisy percentile swing the ranking on
    its own.
    """
    ceiling = (
        constraints.max_separation
        if constraints.max_separation is not None
        else (constraints.min_separation + 10.0)
    )
    span = max(ceiling - constraints.min_separation, 1e-9)
    fold_component = max(0.0, min(1.0, (effect - constraints.min_separation) / span))
    if percentile_gap is None:
        return fold_component
    gap_component = max(0.0, min(1.0, percentile_gap / 100.0))
    return 0.85 * fold_component + 0.15 * gap_component


def _forbidden_start_codons(window: str) -> int:
    """AUG count in this window, forward and reverse-complemented.

    The switch contains the trigger's reverse complement and, in the descending stem,
    segments reverse-complemented back — so an unwanted AUG in the finished switch comes
    from an AUG in the window *or* from a CAU in it (reverse-complementing "CAU" gives
    "AUG"). Reusing ``find_augs``/``reverse_complement`` on the window's own reverse
    complement is exactly that check, expressed with the two already-shared functions
    rather than a third hand-written motif scan (docs/triggers.md §4, docs/genes.md
    §4.2).
    """
    return len(sq.find_augs(window)) + len(sq.find_augs(sq.reverse_complement(window)))


def _combine(weighted: Iterable[tuple[float, float | None]]) -> float:
    """Weighted mean over the axes that were actually measured.

    ``score = sum(w * v) / sum(w)`` over axes where ``v is not None`` — substituting 0.0
    for a missing axis is the exact failure CLAUDE.md §3 describes for a design metric,
    one layer up: with no atlas, every gene's specificity would become a constant 0.0 and
    the weighting would silently stop meaning what it says. Renormalising says plainly
    that a run with three of five axes is a run with three of five axes.
    """
    present = [(weight, value) for weight, value in weighted if value is not None]
    if not present:
        return 0.0
    total_weight = sum(weight for weight, _ in present)
    return sum(weight * value for weight, value in present) / total_weight


def _percentile_rank(sorted_values: list[float], value: float) -> float:
    """0-100: the fraction of ``sorted_values`` at or below ``value``."""
    return 100.0 * bisect_right(sorted_values, value) / len(sorted_values)


class _CountsContext:
    """Precomputed, once per ``select`` call, from a ``CountMatrix``.

    Two things every candidate gene needs: where it ranks within its own group (for
    ``control_percentile``/``condition_percentile``) and its full per-sample expression
    vector (for the redundancy pass, docs/genes.md §4.3). Both are O(genes) to build
    once and O(1) or O(log genes) to look up — building either per-candidate would be
    the same quadratic mistake ``TriggerScorer``'s own docstring warns against for
    per-window profiling.
    """

    def __init__(self, counts: CountMatrix) -> None:
        self.gene_index = {gene_id: i for i, gene_id in enumerate(counts.gene_ids)}
        control_idx = [counts.samples.index(s) for s in counts.metadata.control_samples]
        condition_idx = [counts.samples.index(s) for s in counts.metadata.condition_samples]
        self._control_idx = control_idx
        self._condition_idx = condition_idx
        self._rows = counts.counts
        self._control_means_sorted = sorted(
            mean(row[i] for i in control_idx) for row in counts.counts
        )
        self._condition_means_sorted = sorted(
            mean(row[i] for i in condition_idx) for row in counts.counts
        )

    def vector(self, gene_id: str) -> tuple[float, ...] | None:
        index = self.gene_index.get(gene_id)
        return None if index is None else self._rows[index]

    def percentiles(self, gene_id: str) -> tuple[float | None, float | None]:
        index = self.gene_index.get(gene_id)
        if index is None:
            return None, None
        row = self._rows[index]
        control_mean = mean(row[i] for i in self._control_idx)
        condition_mean = mean(row[i] for i in self._condition_idx)
        return (
            _percentile_rank(self._control_means_sorted, control_mean),
            _percentile_rank(self._condition_means_sorted, condition_mean),
        )


class GeneSelector:
    """Keep the genes that actually separate the two cell states.

    Args:
        constraints: Thresholds the researcher configured — see ``Constraints``'
            docstring for every field this stage reads (``min_separation``,
            ``max_p_adj``, ``max_genes``, ``max_separation``, ``min_base_expression``,
            ``max_base_expression``, ``trigger_gc_range``, ``direction_balance``,
            ``trigger_lengths``).
        screener: The run's shared ``MotifScreener`` (injected, never constructed here —
            CLAUDE.md §5). Used only for the trigger-yield screen (docs/genes.md §4.2);
            never for a final pass/fail call on any single sequence, which stays stage
            2's job.
        atlas: Optional reference expression, e.g. Human Cell Atlas (map input 7). Used
            for **condition specificity**: a gene strongly expressed in the target state
            but also everywhere else in the body is a poor trigger for a therapeutic
            circuit, however clean the in-vitro separation looks. No producer exists for
            this anywhere in the repo today, so it defaults to ``None`` and the axis is
            reported as unmeasured on every run until one does.
    """

    #: Stage 1's own per-axis weights (docs/genes.md §4.5) — provisional, the same
    #: status ``DEFAULT_V1``'s weights carry (docs/ROADMAP.md Q6). **Not** one of the
    #: nine ``engine.scoring`` metrics: this ranks genes, not designs, so it never goes
    #: through ``engine.scoring`` and must never borrow one of those nine names
    #: (CLAUDE.md §2).
    WEIGHT_SEPARATION = 3.0
    WEIGHT_ABUNDANCE = 2.0
    WEIGHT_TRIGGER_YIELD = 2.0
    WEIGHT_NON_REDUNDANCY = 1.5
    WEIGHT_CONDITION_SPECIFICITY = 1.0

    def __init__(
        self,
        constraints: Constraints,
        screener: MotifScreener,
        atlas: dict[str, float] | None = None,
    ) -> None:
        self.constraints = constraints
        self.screener = screener
        self.atlas = atlas

    def select(
        self,
        dge: DgeTable,
        *,
        counts: CountMatrix | None = None,
        sequences: dict[str, str] | None = None,
        on_warning: Callable[[str], None] | None = None,
    ) -> list[SelectedGene]:
        """Filter, score and rank genes; return a shortlist with an up/down call.

        Args:
            dge: The researcher's differential-expression results. The only required
                input — a bare table with nothing else still produces a shortlist,
                ranked on effect size and significance alone (docs/genes.md §5 D1).
            counts: The count matrix, optional. Unlocks per-group percentiles, a
                directional abundance check and the non-redundancy pass (docs/genes.md
                §4.3) — without it those axes are ``None`` on every gene, not 0.0.
            sequences: Gene ID to full transcript sequence, optional (still blocked on
                Q1 in general, docs/ROADMAP.md). Unlocks the trigger-yield axis
                (docs/genes.md §4.2) and drops any gene with zero usable windows — a
                gene stage 2 could build nothing from is never worth stage 2's time,
                however clean its statistics.
            on_warning: Called with one human-readable message per notable event —
                duplicate gene IDs collapsed, a significance tier that had to degrade,
                genes dropped for a missing sequence, an entire direction absent from
                the shortlist. The same "yield a reason, never drop silently" pattern
                ``SwitchDesigner.design``'s own callbacks use (CLAUDE.md §3).

        Returns:
            ``SelectedGene`` list, best first, at most ``constraints.max_genes`` long.
            Empty is a valid, reported outcome (every gene failed a filter), not an
            error — ``on_warning`` names how many failed which filter.

        Raises:
            InputValidationError: the table has no rows at all, or ``sequences`` was
                supplied and not one candidate gene ID was found in it — the second
                case names a systematic identifier-namespace mismatch (docs/genes.md §3
                G-d) rather than letting stage 2 crash on the first missing key.
        """

        def warn(message: str) -> None:
            if on_warning is not None:
                on_warning(message)

        if not dge.rows:
            raise InputValidationError(
                "The differential-expression table has no usable rows — nothing to select from."
            )

        rows, duplicates = self._deduplicate(dge.rows)
        if duplicates:
            warn(
                f"{duplicates} duplicate gene_id row(s) in the input table; the first "
                "occurrence of each was kept."
            )

        significance = self._significance_plan(rows, warn)
        counts_context = _CountsContext(counts) if counts is not None else None

        candidates: list[_Candidate] = []
        dropped_effect = 0
        dropped_significance = 0
        dropped_abundance = 0
        dropped_zero_yield = 0
        missing_sequence = 0
        considered_for_sequence = 0

        for row in rows:
            effect = abs(row.log2_fold_change)
            if effect < self.constraints.min_separation:
                dropped_effect += 1
                continue
            if (
                self.constraints.max_separation is not None
                and effect > self.constraints.max_separation
            ):
                dropped_effect += 1
                continue
            if not significance.passes(row):
                dropped_significance += 1
                continue

            regulation = row.regulation
            on_expr, off_expr = _directional_expression(row, regulation)
            if (
                self.constraints.min_base_expression is not None
                and on_expr is not None
                and on_expr < self.constraints.min_base_expression
            ):
                dropped_abundance += 1
                continue
            if (
                self.constraints.max_base_expression is not None
                and off_expr is not None
                and off_expr > self.constraints.max_base_expression
            ):
                dropped_abundance += 1
                continue

            control_pct = condition_pct = None
            if counts_context is not None:
                control_pct, condition_pct = counts_context.percentiles(row.gene_id)
            percentile_gap = None
            if control_pct is not None and condition_pct is not None:
                percentile_gap = (
                    condition_pct - control_pct
                    if regulation is Regulation.UP
                    else control_pct - condition_pct
                )

            trigger_yield: float | None = None
            usable_windows: int | None = None
            if sequences is not None:
                considered_for_sequence += 1
                transcript = sequences.get(row.gene_id)
                if transcript is None:
                    missing_sequence += 1
                    continue
                trigger_yield, usable_windows = self._trigger_yield(sq.to_rna(transcript))
                if trigger_yield == 0.0:
                    dropped_zero_yield += 1
                    warn(
                        f"{row.gene_id} has zero usable trigger windows and was dropped "
                        "— stage 2 could build nothing from it however clean its "
                        "statistics are."
                    )
                    continue

            candidates.append(
                _Candidate(
                    gene_id=row.gene_id,
                    symbol=row.symbol,
                    regulation=regulation,
                    log2_fold_change=row.log2_fold_change,
                    p_adj=significance.adjusted_p(row),
                    control_percentile=control_pct,
                    condition_percentile=condition_pct,
                    condition_specificity=self._condition_specificity(row, regulation),
                    trigger_yield=trigger_yield,
                    usable_windows=usable_windows,
                    separation_score=_separation_score(effect, self.constraints, percentile_gap),
                    abundance_score=_abundance_score(on_expr, off_expr, self.constraints),
                    vector=counts_context.vector(row.gene_id)
                    if counts_context is not None
                    else None,
                    base_score=0.0,  # filled in below, once every axis above is known
                )
            )

        if (
            sequences is not None
            and considered_for_sequence
            and missing_sequence == considered_for_sequence
        ):
            raise InputValidationError(
                f"None of the {considered_for_sequence} candidate gene ID(s) that otherwise "
                "passed selection were found in the supplied transcript sequences. Check "
                "that both use the same identifier namespace (e.g. an Ensembl ID vs. a "
                "locus tag vs. a bare symbol)."
            )
        if missing_sequence:
            warn(
                f"{missing_sequence} candidate gene(s) had no matching transcript sequence "
                "and were dropped rather than passed on to fail stage 2."
            )

        for candidate in candidates:
            candidate.base_score = _combine(
                [
                    (self.WEIGHT_SEPARATION, candidate.separation_score),
                    (self.WEIGHT_ABUNDANCE, candidate.abundance_score),
                    (self.WEIGHT_TRIGGER_YIELD, candidate.trigger_yield),
                    (self.WEIGHT_CONDITION_SPECIFICITY, candidate.condition_specificity),
                ]
            )

        if not candidates:
            warn(
                "No gene passed stage 1's filters (dropped: "
                f"{dropped_effect} on effect size, {dropped_significance} on significance, "
                f"{dropped_abundance} on expression range, {dropped_zero_yield} with zero "
                "usable trigger windows)."
            )
            return []

        ordered = self._rank_by_redundancy(candidates, has_counts=counts is not None)

        if self.constraints.direction_balance:
            shortlist = self._balance_directions(ordered, self.constraints.max_genes)
            if not any(c.regulation is Regulation.DOWN for c in candidates):
                warn(
                    "No down-regulated gene survived stage 1's filters; the shortlist "
                    "contains only up-regulated (activator) candidates."
                )
            elif not any(c.regulation is Regulation.UP for c in candidates):
                warn(
                    "No up-regulated gene survived stage 1's filters; the shortlist "
                    "contains only down-regulated (repressor) candidates."
                )
        else:
            shortlist = ordered[: self.constraints.max_genes]

        return [self._finalize(candidate) for candidate in shortlist]

    # -- axis helpers --------------------------------------------------------------

    @staticmethod
    def _deduplicate(rows: tuple[DgeRow, ...]) -> tuple[list[DgeRow], int]:
        """First occurrence of each ``gene_id`` wins; a collision is counted, not
        silently swallowed (CLAUDE.md §3)."""
        seen: set[str] = set()
        kept: list[DgeRow] = []
        duplicates = 0
        for row in rows:
            if row.gene_id in seen:
                duplicates += 1
                continue
            seen.add(row.gene_id)
            kept.append(row)
        return kept, duplicates

    def _significance_plan(self, rows: list[DgeRow], warn: Callable[[str], None]) -> _Significance:
        """Choose one of the four tiers in ``_Significance``'s docstring, once for the
        whole table."""
        if any(row.p_adj is not None for row in rows):
            return _Significance("padj", self.constraints.max_p_adj)

        with_pvalue = {row.gene_id: row.p_value for row in rows if row.p_value is not None}
        if not with_pvalue:
            warn(
                "The input table has no adjusted or raw p-value column; significance "
                "was not assessed, and ranking relies on effect size and the other axes "
                "alone."
            )
            return _Significance("none", self.constraints.max_p_adj)

        coverage = len(with_pvalue) / len(rows)
        if coverage >= _BH_COVERAGE_THRESHOLD:
            warn(
                "The input table has no adjusted p-value column; a Benjamini-Hochberg "
                f"FDR was computed by CERNAL from raw p-values at alpha="
                f"{self.constraints.max_p_adj}."
            )
            return _Significance("bh", self.constraints.max_p_adj, _benjamini_hochberg(with_pvalue))

        warn(
            f"The input table has raw p-values for only {coverage:.0%} of rows — too "
            "incomplete to compute a valid FDR (docs/genes.md §4.1). Filtering on the "
            f"raw, uncorrected p-value at {self.constraints.max_p_adj} instead; this is "
            "not an FDR-controlled selection."
        )
        return _Significance("raw", self.constraints.max_p_adj)

    def _trigger_yield(self, transcript: str) -> tuple[float | None, int | None]:
        """Fraction of this transcript's windows usable with no folding at all
        (docs/genes.md §4.2): clear of forbidden motifs, no accidental start codon in
        either orientation, GC inside the configured band. ``None`` when no window
        length could even be scanned, never 0.0 for "not tested"."""
        if not self.constraints.trigger_lengths:
            return None, None

        low, high = self.constraints.trigger_gc_range
        scanned = 0
        surviving = 0
        for length in self.constraints.trigger_lengths:
            for _start, window in sq.windows(transcript, length):
                scanned += 1
                if self.screener.violations(window):
                    continue
                if _forbidden_start_codons(window) > 0:
                    continue
                if not (low <= sq.gc_content(window) <= high):
                    continue
                surviving += 1

        if scanned == 0:
            return None, None
        return surviving / scanned, surviving

    def _condition_specificity(self, row: DgeRow, regulation: Regulation) -> float | None:
        """A simple, explicitly provisional ratio against ``self.atlas`` — the same
        placeholder status ``TriggerScorer.score``'s own ranking formula carries until
        the scientific team reviews it. ``None`` with no atlas, no matching entry, or no
        own-expression value to compare it against."""
        if self.atlas is None:
            return None
        own_expr = row.target_mean if regulation is Regulation.UP else row.control_mean
        if own_expr is None:
            own_expr = row.base_mean
        if own_expr is None:
            return None
        baseline = self.atlas.get(row.gene_id)
        if baseline is None:
            return None
        denominator = own_expr + max(baseline, 0.0)
        if denominator <= 0:
            return None
        return max(0.0, min(1.0, own_expr / denominator))

    @staticmethod
    def _gene_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        """``abs(Pearson correlation)`` — a strong *negative* correlation is just as
        redundant as a strong positive one for separation purposes: knowing one gene
        still tells you the other, so neither adds independent information."""
        try:
            return abs(correlation(a, b))
        except StatisticsError:
            # A zero-variance gene (identical expression in every sample) cannot
            # correlate with anything by definition, which also means it cannot be "the
            # same signal" as another gene. This is a defined mathematical edge case,
            # not the "measurement blew up" pattern CLAUDE.md §3 bans — nothing was
            # left unmeasured here.
            return 0.0

    def _rank_by_redundancy(
        self, candidates: list[_Candidate], *, has_counts: bool
    ) -> list[_Candidate]:
        """The full greedy priority order (docs/genes.md §4.3): repeatedly take the
        highest-scoring remaining candidate, penalised by its similarity to what has
        already been taken.

        Every candidate's final score — including this pass's own non-redundancy axis —
        is written onto it here, so it is available for ``SelectedGene.score`` however
        far down the eventual shortlist the gene lands. Degrades correctly with no
        count matrix: every candidate's ``vector`` is ``None``, ``_combine`` renormalises
        the missing axis away, and ``final_score`` becomes exactly ``base_score`` for
        every gene — an O(n²) walk that produces the same order a plain sort would, kept
        as one code path rather than two that could quietly drift apart.
        """
        remaining = sorted(
            candidates, key=lambda c: (-c.base_score, -abs(c.log2_fold_change), c.gene_id)
        )
        ordered: list[_Candidate] = []

        while remaining:
            best_index = 0
            best_key: tuple[float, float, str] | None = None
            for index, candidate in enumerate(remaining):
                redundancy: float | None = None
                if has_counts and candidate.vector is not None:
                    chosen_vectors = [c.vector for c in ordered if c.vector is not None]
                    redundancy = (
                        1.0
                        if not chosen_vectors
                        else 1.0
                        - max(self._gene_similarity(candidate.vector, v) for v in chosen_vectors)
                    )
                adjusted_score = _combine(
                    [
                        (self.WEIGHT_SEPARATION, candidate.separation_score),
                        (self.WEIGHT_ABUNDANCE, candidate.abundance_score),
                        (self.WEIGHT_TRIGGER_YIELD, candidate.trigger_yield),
                        (self.WEIGHT_CONDITION_SPECIFICITY, candidate.condition_specificity),
                        (self.WEIGHT_NON_REDUNDANCY, redundancy),
                    ]
                )
                key = (adjusted_score, abs(candidate.log2_fold_change), candidate.gene_id)
                if best_key is None or _is_better_pick(key, best_key):
                    best_key = key
                    best_index = index

            chosen = remaining.pop(best_index)
            assert best_key is not None  # a loop iteration always sets it
            chosen.final_score = best_key[0]
            ordered.append(chosen)

        return ordered

    @staticmethod
    def _balance_directions(ordered: list[_Candidate], max_genes: int) -> list[_Candidate]:
        """Reserve up to half the shortlist for each direction, then fill any
        remaining slots from whichever candidates rank best overall (docs/genes.md
        §4.4) — a direction with only one surviving gene still keeps it rather than
        losing it to a strict 50/50 split, and a direction with none simply contributes
        nothing rather than forcing an empty reservation.
        """
        half = max_genes // 2
        up = [c for c in ordered if c.regulation is Regulation.UP][:half]
        down = [c for c in ordered if c.regulation is Regulation.DOWN][:half]
        chosen_ids = {c.gene_id for c in (*up, *down)}

        remaining_slots = max_genes - len(chosen_ids)
        if remaining_slots > 0:
            fill = [c for c in ordered if c.gene_id not in chosen_ids][:remaining_slots]
            chosen_ids.update(c.gene_id for c in fill)

        # Preserve the overall greedy priority order rather than the up-then-down-
        # then-fill construction order, so the shortlist's own order stays explicable.
        return [c for c in ordered if c.gene_id in chosen_ids]

    @staticmethod
    def _finalize(candidate: _Candidate) -> SelectedGene:
        return SelectedGene(
            gene_id=candidate.gene_id,
            symbol=candidate.symbol,
            regulation=candidate.regulation,
            log2_fold_change=candidate.log2_fold_change,
            score=candidate.final_score,
            p_adj=candidate.p_adj,
            control_percentile=candidate.control_percentile,
            condition_percentile=candidate.condition_percentile,
            condition_specificity=candidate.condition_specificity,
            trigger_yield=candidate.trigger_yield,
            usable_windows=candidate.usable_windows,
        )


def _is_better_pick(
    candidate: tuple[float, float, str], current_best: tuple[float, float, str]
) -> bool:
    """Higher adjusted score wins; ties broken by larger effect size, then by the
    lexicographically smaller gene id — a total order, so the same input always
    produces the same shortlist regardless of dict/set iteration order upstream
    (CLAUDE.md §6's determinism rule)."""
    if candidate[0] != current_best[0]:
        return candidate[0] > current_best[0]
    if candidate[1] != current_best[1]:
        return candidate[1] > current_best[1]
    return candidate[2] < current_best[2]
