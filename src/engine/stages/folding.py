"""S1 — local accessibility profiling, the primitive behind trigger selection.

Lives beside the stages rather than in ``engine/gates/tools/`` because no gate family
uses it: a gate is handed a trigger that has *already* been judged accessible. Only
stage 2 asks this question, and it asks it of whole transcripts rather than of designs.

**This is the second module in the engine that imports ViennaRNA**, the other being
``engine.gates.tools.folding``. That duplication is deliberate and the cost is small:
``RNAplfold`` is a separate entry point with its own window parameters, and it shares
neither cache nor temperature model with the MFE folding the gate families do.

E1 rung 4 (docs/ROADMAP.md §5): the windowed ``RNAplfold`` wrapper.
"""

from functools import cache

import RNA


class FoldProfiler:
    """S1 — per-position unpaired probability in *local* folding context.

    The primitive behind trigger selection, and the reason a trigger is more than "a
    30-nucleotide window". A trigger must be **accessible**: single-stranded enough in
    the context of its own transcript for the switch to reach it. A perfect sequence
    match buried inside a stable hairpin will never bind.

    "Local context" matters because a full mRNA can be thousands of nucleotides, and
    global folding of that is both slow and biologically dubious — RNA folds
    co-transcriptionally and locally. ``RNAplfold`` computes unpaired probabilities using
    only a sliding window, which is faster and closer to reality.

    Args:
        window: ``-W``. Span of the sliding window in nucleotides. Positions further
            apart than this are never considered paired. 80 is a common choice.
        max_span: ``-L``. Maximum base-pair span within the window. Must be less than or
            equal to ``window``.
        unpaired: ``-u``. Maximum length of unpaired stretch to compute probabilities
            for. Must be at least as long as the trigger lengths being screened, or the
            openness of a full-length trigger cannot be read off.

    Gotcha:
        ``unpaired`` shorter than the trigger length is the most common misconfiguration
        here, and it fails quietly by returning probabilities for stretches shorter than
        you asked about.
    """

    def __init__(self, window: int = 80, max_span: int = 40, unpaired: int = 10) -> None:
        self.window = window
        self.max_span = max_span
        self.unpaired = unpaired

    def profile(self, sequence: str) -> list[float]:
        """Unpaired probability at every position of a transcript.

        Args:
            sequence: The **whole transcript**, not the candidate segment. Context is
                the entire point — a segment folded alone gives a different, wrong answer.

        Returns:
            One probability per position, each in 0.0 to 1.0, where 1.0 means certainly
            single-stranded. Same length as ``sequence``.

        Cached per transcript (on ``sequence``, this instance's only varying input) —
        called once per gene and then read many times by ``openness``, so computing it
        per window would be quadratic. A fresh list is returned on every call, the same
        defensive copy ``gates/tools/folding.py``'s ``base_pair_probabilities`` makes: a
        cached list handed out by reference would let one caller's mutation corrupt
        every other caller's view for the rest of the run.
        """
        return list(self._profile_cached(sequence))

    @cache  # noqa: B019 — one instance per run; see FoldEngine's identical pattern
    def _profile_cached(self, sequence: str) -> tuple[float, ...]:
        # RNA.pfl_fold_up returns a 1-based matrix: row 0 and column 0 are unused
        # placeholders (verified against ViennaRNA 2.7.2), row i holds probabilities for
        # segments *starting* at position i, and column 1 is the length-1 (single
        # position) segment — exactly the per-position openness this method reports.
        matrix = RNA.pfl_fold_up(sequence, self.unpaired, self.window, self.max_span)
        return tuple(matrix[position][1] for position in range(1, len(sequence) + 1))

    def openness(self, sequence: str, start: int, end: int) -> float:
        """Mean unpaired probability across a segment. The map's ``Trigger Openness``.

        Args:
            sequence: The whole transcript.
            start: 0-indexed inclusive start of the candidate segment.
            end: 0-indexed exclusive end.

        Returns:
            Mean unpaired probability in 0.0 to 1.0. Higher is more accessible and
            therefore a better trigger. ``0.0`` for an empty segment (``end <= start``)
            — there is nothing to average, and CLAUDE.md §3 rules out inventing a
            number for what was not measured; a genuinely empty segment is not a
            "failed measurement" that should read ``None``, since the caller chose the
            empty window itself.

        Note:
            The mean can hide a problem: a segment that is wide open at both ends and
            firmly paired in the middle averages to something respectable. Consider also
            recording the minimum, and let the scientific team decide which matters.
        """
        segment = self.profile(sequence)[start:end]
        return sum(segment) / len(segment) if segment else 0.0
