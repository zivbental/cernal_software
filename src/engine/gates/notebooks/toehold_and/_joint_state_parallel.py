"""Parallel worker for ``joint_state()`` (see ``toehold_and_eu_test.ipynb``'s
"joint-state helpers" cell for the serial, documented original).

Lives in a real file, not a notebook cell, because Python multiprocessing on macOS uses
the "spawn" start method: a worker process re-imports the target function from its module,
which only works for a function defined in an actual importable file -- a function defined
by ``exec()`` inside a notebook cell has no module a spawned child can import it from.

Each job is fully self-contained (sequences, footprint spans as plain tuples/strings),
so a worker needs nothing from the notebook's namespace. Splitting the work across
processes changes nothing about what is computed, only how many candidates get checked
per second.

**All folding goes through the one shared ``FoldEngine``** (``CLAUDE.md`` sec 1/sec 5:
it is the only place a gate family may fold, and exactly one instance exists per run).
This module does not ``import RNA`` and does not construct an engine: the notebook
publishes the engine ``pipeline``-style with :func:`use_fold_engine` before submitting
any jobs, and the pools run under the "fork" start method, so every worker inherits
that *same* instance -- verified by object identity and temperature inside a worker,
not assumed. One engine, one temperature, one recorded ViennaRNA version, exactly as
if the work had stayed in-process.
"""

from __future__ import annotations

import math
import multiprocessing
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from typing import NamedTuple

from engine.sequences import gc_content, reverse_complement

# The one shared FoldEngine, published by the notebook (or a pipeline) before any pool
# is started. Deliberately not constructed here: CLAUDE.md sec 5 reserves building
# tools for pipeline.build_tools(), and a second instance would mean a second cold
# cache and a second chance to fold at a different temperature.
_FOLD_ENGINE = None


def use_fold_engine(engine) -> None:
    """Publish the single shared ``FoldEngine`` for the workers to fold through.

    Call once, from the process that owns the engine, BEFORE submitting any jobs: the
    pools fork, so a child inherits whatever was set at fork time. Setting it after a
    pool has started does not reach the already-forked workers.
    """
    global _FOLD_ENGINE
    _FOLD_ENGINE = engine


def _engine(temperature: float):
    """The shared engine, with the job's temperature checked against it.

    A job carrying a different temperature than the engine folds at is exactly the
    split-brain ``FoldEngine``'s own docstring warns about -- two designs folded at
    different temperatures whose energies then get normalised onto one axis as though
    comparable. Raising here makes that impossible to do by accident; silently
    preferring either value would not.
    """
    if _FOLD_ENGINE is None:
        raise RuntimeError(
            "No FoldEngine published: call use_fold_engine(folder) before running any "
            "parallel job (and before the pool forks)."
        )
    if abs(_FOLD_ENGINE.temperature - temperature) > 1e-9:
        raise ValueError(
            f"job temperature {temperature} != shared FoldEngine temperature "
            f"{_FOLD_ENGINE.temperature} -- one folding temperature per run"
        )
    return _FOLD_ENGINE


def _partner_table(structure: str) -> list[int | None]:
    """Base-pair partner index per position (``None`` where unpaired) for one
    dot-bracket structure -- the same stack walk this notebook's own mechanism cells
    already use, lifted here so every worker reads partners the same way instead of
    four near-copies drifting apart.
    """
    stack: list[int] = []
    partner: list[int | None] = [None] * len(structure)
    for i, ch in enumerate(structure):
        if ch == "(":
            stack.append(i)
        elif ch == ")":
            j = stack.pop()
            partner[i] = j
            partner[j] = i
    return partner


def _frac_paired_to_external(structure: str, start: int, end: int, n_self: int) -> float:
    """Fraction of ``structure[start:end]`` paired to a strand OTHER than the first
    ``n_self`` positions -- i.e. other than the switch/fused molecule itself.

    WHY NOT "paired to anything": in the fused AND construct the footprint is 80-90%
    paired with NO trigger present at all (roughly half to its own stem_down, the
    intended OFF hairpin, and half to the OTHER hairpin's toehold), so a plain "any
    non-dot character" count reads intramolecular misfolding as trigger activation.

    Requiring the partner to live on another strand makes "open" mean that the
    footprint was opened by something that arrived from outside the molecule. A real
    trigger and an off-target fake both count, deliberately: in a leak state a fake
    occupying the footprint is exactly the leak being measured. Folding with no second
    strand (``n_self == len(structure)``) yields 0.0 by construction.
    """
    partner = _partner_table(structure)
    external = sum(
        1 for i in range(start, end) if partner[i] is not None and partner[i] >= n_self
    )
    return external / (end - start)


def _mean_pair_prob(matrix: list[list[float]], span: tuple[int, int], target_ok) -> float | None:
    """Mean over positions of ``span`` of the TOTAL probability of pairing to any
    position ``j`` with ``target_ok(j)`` -- the one exact-marginal reader, shared by
    :func:`_exact_decomp_means`. ``None`` for an empty
    span (not measured is not zero -- CLAUDE.md sec 3)."""
    s0, s1 = span
    if s1 <= s0:
        return None
    n_total = len(matrix)
    total = 0.0
    for i in range(s0, s1):
        row = matrix[i]
        total += sum(row[j] for j in range(n_total) if target_ok(j))
    return total / (s1 - s0)


def _exact_decomp_means(
    matrix: list[list[float]],
    n_self: int,
    footprint: tuple[int, int],
    stem_up: tuple[int, int],
    stem_down: tuple[int, int],
) -> dict[str, float | None]:
    """EXACT ensemble means of the three decomposition metrics for one hairpin, read off
    the partition-function pair-probability matrix instead of Boltzmann samples.

    Same definitions as :func:`stem_closed_fraction` / :func:`misfolded_fraction` /
    :func:`_frac_paired_to_external`, with a position's single 0/1 partner replaced by
    the total probability of pairing into the same target set (a position pairs with at
    most one partner per structure, so these probabilities add; the per-position values
    are expected fractions, and their mean over the span is the expected fraction of the
    span's nt). ``matrix`` is ``FoldEngine.base_pair_probabilities`` for the SAME strand
    string the sampling used (0-indexed, ``&`` removed, fused molecule first, so every
    index below ``n_self`` is the fused construct and every index at/past it is an
    external strand).

    WHY: ``FoldEngine.sample_structures`` disagrees with this exact calculation on multi-strand
    complexes, so the report uses these exact means. A joint event (all designed duplexes at
    once) cannot be read from a marginal matrix; it comes from
    ``FoldEngine.constrained_probability`` (see :func:`designed_pairs`).

    ``None`` for a metric whose span is empty (not measured is not zero -- CLAUDE.md
    sec 3).
    """
    sd0, sd1 = stem_down
    return {
        "stem_closed": _mean_pair_prob(matrix, stem_up, lambda j: sd0 <= j < sd1),
        "misfolded": _mean_pair_prob(
            matrix, footprint, lambda j: j < n_self and not (sd0 <= j < sd1)
        ),
        "trigger_bound": _mean_pair_prob(matrix, footprint, lambda j: j >= n_self),
    }


def stem_closed_fraction(
    structure: str, stem_up_span: tuple[int, int], stem_down_span: tuple[int, int]
) -> float:
    """Fraction of ``stem_up_span`` paired SPECIFICALLY to ``stem_down_span`` in one
    sampled structure -- the intended OFF hairpin actually closing, not just "paired to
    something". One of three state-decomposition metrics (``and_eu_report_spec.md``
    Step 2); the other two are :func:`misfolded_fraction` below and
    ``_frac_paired_to_external`` above (``trigger_bound``).

    Built on :func:`_partner_table`, so a stem that closes with a bulge or an
    off-register shift is read the same way as every other partner-tracing check here.
    """
    partner = _partner_table(structure)
    su0, su1 = stem_up_span
    sd0, sd1 = stem_down_span
    n = su1 - su0
    if n == 0:
        return 0.0
    closed = sum(
        1 for i in range(su0, su1) if partner[i] is not None and sd0 <= partner[i] < sd1
    )
    return closed / n


def misfolded_fraction(
    structure: str, footprint_span: tuple[int, int], stem_down_span: tuple[int, int], n_self: int
) -> float:
    """Fraction of ``footprint_span`` paired INTRAMOLECULARLY but NOT to its own
    ``stem_down_span`` -- paired to something other than what either the OFF hairpin
    (``stem_closed_fraction``) or a real binding event (``_frac_paired_to_external``,
    ``trigger_bound``) would call correct, e.g. the footprint paired to the OTHER
    hairpin's toehold in the fused AND construct.

    Low everywhere is the goal; unlike ``trigger_bound``, there is no state in which a
    high value here is correct.

    ``n_self``: length of the fused/switch molecule alone -- a partner index at or past
    this is external (``_frac_paired_to_external``'s territory, not misfolding) and is
    excluded here so the three metrics partition the footprint's possible partners
    without double-counting any of them.
    """
    partner = _partner_table(structure)
    f0, f1 = footprint_span
    sd0, sd1 = stem_down_span
    n = f1 - f0
    if n == 0:
        return 0.0
    misfolded = 0
    for i in range(f0, f1):
        p = partner[i]
        if p is None or p >= n_self:  # unpaired, or paired externally -- not misfolding
            continue
        if sd0 <= p < sd1:  # paired to its own stem_down -- the intended OFF hairpin
            continue
        misfolded += 1
    return misfolded / n


def _sample_coverage(samples: list[str]) -> dict:
    """How much of the real Boltzmann ensemble a batch of ``pbacktrack`` draws
    actually represents -- not a raw count against the astronomical total structure
    space (~1.8^n, meaningless as a percentage for any real-size switch), but the
    empirical Shannon entropy of the DRAWN distribution turned into an "effective
    structure count" (2^H): the number of distinct structures that would carry this
    much probability mass if it were spread evenly. ``coverage`` = how many of the
    draws were unique, relative to that effective count, capped at 100% -- once the
    number of distinct structures actually seen reaches the effective count, more
    samples are very unlikely to turn up a structure that matters and was missed.
    Computed from the SAME samples every worker in this file already draws for its
    own bound/open fraction -- no extra folding call.
    """
    n = len(samples) or 1
    counts = Counter(samples)
    entropy_bits = -sum((c / n) * math.log2(c / n) for c in counts.values())
    effective_structures = 2**entropy_bits
    n_unique = len(counts)
    coverage = min(1.0, n_unique / effective_structures) if effective_structures > 0 else 1.0
    return {
        "n_unique_structures": n_unique,
        "effective_structures": effective_structures,
        "sample_coverage": coverage,
    }


class SingleStateJob(NamedTuple):
    """Single-input state job -- one switch, one trigger (or none),
    one footprint. There is no "both" state to speak of; the only question is whether
    the footprint reads as paired in a real sampled structure, not just on average.

    ``trigger=""`` folds the switch by itself, no second strand at all -- the "toehold
    alone" state. With nothing else present, the footprint's only possible pairing
    partner is its own stem_down, so a HIGH ``bound`` fraction here means the intended
    OFF-state hairpin (stem_up:stem_down closed) is what the ensemble actually sits in
    -- correct/expected for a well-behaved design, not a naming inversion: "bound"
    always means "the footprint is >=threshold paired to something", and what that
    something is is determined entirely by what strands the job includes.
    """

    key: str
    switch: str
    trigger: str
    footprint: tuple[int, int]
    temperature: float
    n_samples: int = 1200
    threshold: float = 0.80


def _single_worker(job: SingleStateJob) -> dict:
    """Runs in a separate process, folding through the inherited shared ``FoldEngine``."""
    strands = f"{job.switch}&{job.trigger}" if job.trigger else job.switch
    samples = _engine(job.temperature).sample_structures(strands, job.n_samples)

    # Two different, deliberate meanings, picked by whether a second strand exists:
    #
    #   trigger present -> "bound" means paired to THAT strand (external), not to
    #     anything: a footprint sequestered by its own stem_down, or by any other part
    #     of the switch, is not bound to the trigger and must not count as such (see
    #     _frac_paired_to_external for the measured reason this matters).
    #   trigger == ""   -> "bound" keeps its documented alone-state meaning, paired to
    #     ANYTHING, because the whole point of that state is to measure how much of the
    #     footprint sits in its own intended OFF hairpin with nothing else around. The
    #     caller reads it as `1 - bound` for the leak term, so flipping it to the
    #     external-strand rule (which is 0.0 by construction with no second strand)
    #     would silently turn that leak into a constant 100%.
    start, end = job.footprint
    if job.trigger:
        n_self = len(job.switch)
        bound = sum(
            1
            for structure in samples
            if _frac_paired_to_external(structure, start, end, n_self) >= job.threshold
        )
    else:
        bound = sum(
            1
            for structure in samples
            if sum(ch != "." for ch in structure[start:end]) / (end - start) >= job.threshold
        )
    n = len(samples) or 1
    return {
        "key": job.key, "bound": bound / n, "unbound": 1 - bound / n, "n_samples": n,
        **_sample_coverage(samples),
    }


def run_parallel_single(jobs: list[SingleStateJob], max_workers: int = 6) -> dict[str, dict]:
    """Single-input counterpart to ``run_parallel`` -- same fork-context reasoning."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_single_worker, jobs):
            results[outcome["key"]] = outcome
    return results


class FakeSweepJob(NamedTuple):
    """One AND pair, checked across ten states: the fused switch alone, with each of
    two off-target ("fake") triggers alone and together, with each real trigger alone,
    with both real triggers, and with each real trigger paired against a fake in the
    other slot -- the full leakage/specificity sweep, not just the "both real" state
    every other job type here checks. A "fake" trigger is a real design's own trigger
    from elsewhere in the pool, chosen by the caller to not overlap either real
    footprint -- this job only ever sees the four already-resolved sequences.
    """

    key: str
    fused: str
    trigger_a: str
    trigger_b: str
    fake_a: str
    fake_b: str
    footprint_5p: tuple[int, int]
    footprint_3p: tuple[int, int]
    temperature: float
    n_samples: int = 1200
    threshold: float = 0.80


def both_triggers_extra(trigger_a: str, trigger_b: str) -> tuple[str, str]:
    """The ONE place the strand order of a two-real-trigger AND state is decided.

    Returns ``(trigger_b, trigger_a)``: B is appended FIRST, A LAST. ViennaRNA's
    multi-strand folding only represents structures that are NESTED along the written
    strand order. The fused switch is written 5'->3' as hairpin A (footprint A, ~nt
    8-38) ... hairpin B (footprint B, ~nt 66-96), then the appended strands. A written
    ``fused & tA & tB`` makes footprint A <-> tA and footprint B <-> tB CROSS (a
    pseudoknot: A < B < tA < tB), which the model cannot represent -- measured on pair
    4+6 no_spacer, tA bound 0.99 but tB bound 0.00 (59% unpaired), so the joint ON
    state was ~0 for every pair. ``fused & tB & tA`` nests (A < B < tB < tA: the LATER
    strand binds the EARLIER footprint) and both bind (0.98/0.99). Physically the
    molecules are separate, so the order is irrelevant; this is purely a
    model-representation requirement. Every state containing both real triggers must
    take its strands from here, and its crosshair boundaries must follow this order.

    Single-real-trigger states with a fake (``+A+fakeA``, ``+B+fakeB``) are left as
    (real, fake): only one real footprint is in play, so the real duplex (one footprint
    against one strand) is nestable whichever position it sits in, and the fake is a
    non-binding decoy; that order is kept consistent for all of them.
    """
    return (trigger_b, trigger_a)


# (state name, which resolved sequences ride along with the fused switch) -- shared by
# the worker below and by any caller that wants to know the state list without running
# anything (e.g. to size a results table before the sweep finishes).
FAKE_SWEEP_STATES = (
    ("alone", ()),
    ("+fake1", ("fake_a",)),
    ("+fake2", ("fake_b",)),
    ("+fake1+fake2", ("fake_a", "fake_b")),
    ("+A", ("trigger_a",)),
    ("+B", ("trigger_b",)),
    ("+A+B", ("trigger_b", "trigger_a")),  # order: see both_triggers_extra
    ("+A+fake1", ("trigger_a", "fake_a")),
    ("+B+fake2", ("trigger_b", "fake_b")),
    ("+A+B+fake1+fake2", ("trigger_b", "trigger_a", "fake_a", "fake_b")),
)
# Only these three states get a base-pair-probability matrix (the marginal check) alongside
# the sampled joint answer; the fake-only states are leakage checks on the sampled
# open-fraction alone, since a full n^2 matrix for all ten states would multiply the cost.
FAKE_SWEEP_MATRIX_STATES = frozenset({"+A", "+B", "+A+B"})


def _fake_sweep_worker(job: FakeSweepJob) -> dict:
    """Runs in a separate process, folding through the inherited shared ``FoldEngine``.

    Accessibility comes from ``FoldEngine.base_pair_probabilities`` (0-indexed, symmetric,
    over the same ``&``-joined frame).
    """
    engine = _engine(job.temperature)

    sequences = {
        "trigger_a": job.trigger_a,
        "trigger_b": job.trigger_b,
        "fake_a": job.fake_a,
        "fake_b": job.fake_b,
    }

    def mean_unpaired(matrix, start, end):
        end = min(end, len(matrix))
        if end <= start:
            return 0.0
        vals = [max(0.0, 1.0 - sum(matrix[i])) for i in range(start, end)]
        return sum(vals) / len(vals)

    n = len(job.fused)
    fp5, fp3 = job.footprint_5p, job.footprint_3p
    out = {"key": job.key}
    for name, extra_keys in FAKE_SWEEP_STATES:
        extra = [sequences[k] for k in extra_keys]
        strands = "&".join([job.fused, *extra]) if extra else job.fused
        samples = engine.sample_structures(strands, job.n_samples)
        n_samples = len(samples) or 1
        # Per-structure classification, not two independent marginals: "sampled_both"
        # counts structures where BOTH footprints clear threshold in the SAME draw, the
        # only number that answers "does this molecule ever do both at once".
        a_open = b_open = both_open = 0
        for s in samples:
            # External-strand rule, not "paired to anything" (see
            # _frac_paired_to_external).
            is_a = _frac_paired_to_external(s, fp5[0], fp5[1], n) >= job.threshold
            is_b = _frac_paired_to_external(s, fp3[0], fp3[1], n) >= job.threshold
            a_open += is_a
            b_open += is_b
            both_open += is_a and is_b
        state_out = {
            "sampled_a_open": a_open / n_samples,
            "sampled_b_open": b_open / n_samples,
            "sampled_both": both_open / n_samples,
            **_sample_coverage(samples),
        }
        if name in FAKE_SWEEP_MATRIX_STATES:
            # Already 0-indexed and symmetric over the &-joined frame; mean_unpaired
            # clips to len(matrix), so the footprint spans (which index the fused
            # molecule, the first strand) stay valid for any number of extra strands.
            matrix = engine.base_pair_probabilities(strands)
            state_out["marginal_a_access"] = mean_unpaired(matrix, fp5[0], fp5[1])
            state_out["marginal_b_access"] = mean_unpaired(matrix, fp3[0], fp3[1])
        out[name] = state_out
    return out


def _is_complementary(x: str, y: str, *, allow_wobble: bool) -> tuple[bool, bool]:
    """``(is_match, is_wobble)`` for one antiparallel base pair -- Watson-Crick always
    matches; G*U/U*G matches only when ``allow_wobble``. Used by
    :func:`_longest_complementary_run_wobble`, the Trap-3 fix below.
    """
    wc = {("A", "U"), ("U", "A"), ("G", "C"), ("C", "G")}
    if (x, y) in wc:
        return True, False
    if allow_wobble and (x, y) in {("G", "U"), ("U", "G")}:
        return True, True
    return False, False


def _longest_complementary_run_wobble(
    a: str, b: str, wobble_max_fraction: float
) -> tuple[int, int]:
    """Longest antiparallel-complementary run between ``a`` and ``b``, same DP shape as
    :func:`_longest_complementary_run` (longest common substring of ``a`` against
    ``reverse_complement(b)``) but tolerating G*U/U*G wobble matches -- Trap 3 in
    ``and_eu_report_spec.md``: a real, ViennaRNA-confirmed 12bp helix scored as only 4nt
    under exact-complement-only matching because four of its positions were wobbles.

    Returns ``(run_length, n_wobble_positions_in_that_run)``.

    Every DP cell carries the full, uncapped ``(length, wobble_count)`` of the run
    ending there, so a run can keep growing through a locally wobble-heavy stretch (the
    fraction can still recover if later positions are plain Watson-Crick, since adding a
    non-wobble match grows the denominator without the numerator). The cap is applied
    when reading out the best answer: at every cell, a candidate only updates the global
    best if ITS OWN ``wobble_count / length`` is within ``wobble_max_fraction`` --
    so the reported run is always one that, taken as a whole, satisfies the cap, even
    though the DP underneath explored runs that temporarily did not.
    """
    b_rc = reverse_complement(b)
    n, m = len(a), len(b_rc)
    prev = [(0, 0)] * (m + 1)
    best_len, best_wobble = 0, 0
    for i in range(1, n + 1):
        curr = [(0, 0)] * (m + 1)
        ai = a[i - 1]
        for j in range(1, m + 1):
            bj = b_rc[j - 1]
            match, wobble = _is_complementary(ai, bj, allow_wobble=True)
            if match:
                prev_len, prev_wobble = prev[j - 1]
                length = prev_len + 1
                n_wobble = prev_wobble + (1 if wobble else 0)
                curr[j] = (length, n_wobble)
                if n_wobble / length <= wobble_max_fraction and length > best_len:
                    best_len, best_wobble = length, n_wobble
            # else curr[j] stays (0, 0): a mismatch always breaks the run, same as the
            # exact-match DP this generalises.
        prev = curr
    return best_len, best_wobble


def _longest_identity_run(a: str, b: str) -> int:
    """Longest SAME-DIRECTION identical substring shared by ``a`` and ``b`` -- literal
    sequence identity, not antiparallel complementarity. Ordinary longest-common-substring
    DP (:func:`_longest_complementary_run` without the ``reverse_complement`` step).

    WHY it exists beside the complementarity checks: two triggers drawn from the same or
    overlapping transcript region are near-identical substrings of each other, which
    predicts near-identical BINDING TARGETS (cross-talk) but is structurally invisible to
    a complementarity check -- identical sequences are generally not self-complementary.
    Real counterexample: trigger B (27 nt) a literal prefix of trigger A (30 nt) has a
    complementary run of only 6 nt. No wobble tolerance: identity is binary per position.
    """
    n, m = len(a), len(b)
    prev = [0] * (m + 1)
    best = 0
    for i in range(1, n + 1):
        curr = [0] * (m + 1)
        ai = a[i - 1]
        for j in range(1, m + 1):
            if ai == b[j - 1]:
                v = prev[j - 1] + 1
                curr[j] = v
                if v > best:
                    best = v
        prev = curr
    return best


def trigger_pair_too_similar(
    trigger_a: str, trigger_b: str, *, max_overlap_nt: int, wobble_max_fraction: float
) -> bool:
    """True when an AND pair's own two REAL triggers (trigger A, trigger B) are too
    similar to each other by EITHER of two independent checks, each compared against
    ``max_overlap_nt``: a complementary run (wobble included,
    :func:`_longest_complementary_run_wobble` -- would they hybridize to each other) or a
    same-direction identity run (:func:`_longest_identity_run` -- are they (nearly) the
    same sequence, i.e. drawn from the same transcript region).

    Reuses both run finders (CLAUDE.md sec 1: one overlap checker per concept). Called
    before any job for the pair is submitted, so no compute is spent on a rejected pair.
    """
    comp_run, _wobble = _longest_complementary_run_wobble(trigger_a, trigger_b, wobble_max_fraction)
    identity_run = _longest_identity_run(trigger_a, trigger_b)
    return comp_run > max_overlap_nt or identity_run > max_overlap_nt


def pick_fake_design(
    design_5p,
    design_3p,
    exclude_ranks,
    pool,
    start_offset=0,
    *,
    max_overlap_nt=None,
    wobble_max_fraction=None,
):
    """Pool design with no meaningful sequence complementarity to EITHER A's or B's own
    footprint (toehold+stem_up) -- a real off-target trigger picked by sequence
    dissimilarity, not by genomic position (two triggers from non-overlapping windows can
    still share real, accidental complementarity to a footprint).

    Used by ``toehold_and_eu_test.ipynb`` and ``toehold_context_report.ipynb``;
    ``and_eu_report.ipynb`` uses :func:`pick_fake_trigger` instead.

    ``max_overlap_nt``/``wobble_max_fraction`` (both ``None`` by default): optional extra
    screening -- a candidate also fails when its longest complementary run against either
    footprint exceeds ``max_overlap_nt`` (an absolute cap, not just "less than the real
    trigger"), and wobble matches count toward that run up to ``wobble_max_fraction`` of it
    (:func:`_longest_complementary_run_wobble`). Leaving both ``None`` keeps the plain
    exact-complement behaviour. When wobble screening is on, the returned dict carries an
    extra ``wobble_positions_used`` key (the larger of the two footprints' wobble counts in
    the accepted candidate's own best run) so a wobble-driven accept is visible.

    A candidate qualifies only when its longest exact complementary run
    (``_longest_complementary_run``) against EACH footprint is STRICTLY LESS than that
    footprint's own real trigger's longest complementary run against itself --
    self-calibrated per design rather than one arbitrary nt cutoff.

    Starts the scan at ``start_offset`` and wraps around, so different candidates rotate
    onto different fakes instead of one early-pool design dominating every result.
    """

    def _footprint(design):
        start, end = design["domains"]["toehold"][0], design["domains"]["stem_up"][1]
        return design["switch"][start:end]

    use_wobble = wobble_max_fraction is not None

    def _run(seq_a, seq_b):
        if use_wobble:
            return _longest_complementary_run_wobble(seq_a, seq_b, wobble_max_fraction)
        return _longest_complementary_run(seq_a, seq_b), 0

    footprint_5p, footprint_3p = _footprint(design_5p), _footprint(design_3p)
    real_run_5p, _ = _run(footprint_5p, design_5p["trigger"])
    real_run_3p, _ = _run(footprint_3p, design_3p["trigger"])

    n = len(pool)
    for step in range(n):
        candidate = pool[(start_offset + step) % n]
        if candidate["rank"] in exclude_ranks:
            continue
        run_5p, wobble_5p = _run(footprint_5p, candidate["trigger"])
        run_3p, wobble_3p = _run(footprint_3p, candidate["trigger"])
        if run_5p >= real_run_5p or run_3p >= real_run_3p:
            continue
        if max_overlap_nt is not None and (run_5p > max_overlap_nt or run_3p > max_overlap_nt):
            continue
        if not use_wobble:
            return candidate
        result = dict(candidate)
        result["wobble_positions_used"] = max(wobble_5p, wobble_3p)
        return result
    return None


def pick_fake_trigger(
    real_triggers,
    exclude_ranks,
    pool,
    start_offset=0,
    *,
    max_overlap_nt=8,
):
    """Next pool design whose TRIGGER shares at most ``max_overlap_nt`` nt of identical
    sequence with EVERY real trigger in ``real_triggers``.

    Similarity is the longest same-direction identical run
    (:func:`_longest_identity_run`, a plain longest-common-substring). Single switch:
    ``real_triggers=(trigger,)``. AND: ``(trigger_a, trigger_b)`` -- both real triggers sit
    in the AND construct, so a fake for either side must resemble neither.

    Identity only, no complementarity or wobble screen: :func:`pick_fake_design`'s
    footprint-complementarity bar (4-7 nt, self-calibrated) is not met by any pool
    candidate, which gave zero fakes.

    Scan starts at ``start_offset`` and wraps, so different candidates rotate onto
    different fakes. Deterministic. Returns the pool design dict, or ``None`` when no
    unexcluded candidate qualifies.
    """
    n = len(pool)
    for step in range(n):
        candidate = pool[(start_offset + step) % n]
        if candidate["rank"] in exclude_ranks:
            continue
        if all(
            _longest_identity_run(real, candidate["trigger"]) <= max_overlap_nt
            for real in real_triggers
        ):
            return candidate
    return None


def pick_fake_triggers(real_triggers, exclude_ranks, pool, n, start_offset=0, *, max_overlap_nt):
    """Up to ``n`` distinct fakes for one footprint set: :func:`pick_fake_trigger` called
    with ``start_offset``, ``start_offset + 1``, ... and each pick excluded from the next.
    Stops early when the pool runs out, so fewer than ``n`` may come back (never padded).
    ``exclude_ranks`` is not modified.
    """
    picked = set(exclude_ranks)
    fakes = []
    for k in range(n):
        fake = pick_fake_trigger(
            real_triggers,
            picked,
            pool,
            start_offset=start_offset + k,
            max_overlap_nt=max_overlap_nt,
        )
        if fake is None:
            break
        picked.add(fake["rank"])
        fakes.append(fake)
    return fakes


def _longest_complementary_run(a: str, b: str) -> int:
    """Longest stretch that could actually base-pair between ``a`` and ``b`` in an
    antiparallel duplex -- the longest common substring between ``a`` and
    ``reverse_complement(b)``, found by ordinary substring DP. Pure string matching, no
    folding: a fast pre-screen for "would this even have a chance to hybridize".
    """
    b_rc = reverse_complement(b)
    n, m = len(a), len(b_rc)
    prev = [0] * (m + 1)
    best = 0
    for i in range(1, n + 1):
        curr = [0] * (m + 1)
        ai = a[i - 1]
        for j in range(1, m + 1):
            if ai == b_rc[j - 1]:
                v = prev[j - 1] + 1
                curr[j] = v
                if v > best:
                    best = v
        prev = curr
    return best


def generate_spacer_candidates(
    n: int, min_length: int = 15, max_length: int = 20, seed: int = 1
) -> list[str]:
    """A fixed, reproducible pool of low-GC candidate spacer sequences -- lengths
    cycle 15..20 so the whole requested range is covered, and every base is drawn
    A/U-biased (A-U pairs are weaker than G-C, hence a low-GC spacer). Seeded with a
    literal constant, never wall-clock or module-level ``random.`` state (CLAUDE.md
    sec 6) -- the SAME pool every run.
    """
    rng = random.Random(seed)
    bases = ("A", "U", "G", "C")
    weights = (0.35, 0.35, 0.15, 0.15)
    span = max_length - min_length + 1
    return [
        "".join(rng.choices(bases, weights=weights, k=min_length + (i % span)))
        for i in range(n)
    ]


def pick_optimized_spacer(design_5p, design_3p, candidates: list[str]) -> tuple[str, int]:
    """Picks the candidate spacer with the smallest worst-case complementary run
    against either design's toehold OR trigger ("minimal interaction" estimated as no
    hybridization with triggers or toeholds). Ties broken by lower GC, then by pool order
    (deterministic, first-found wins -- CLAUDE.md sec 6). Returns ``(spacer, worst_run)``
    so the caller can see how good the best available candidate actually was -- a
    worst_run of e.g. 8 says the pool needs to be bigger or the pair is hard to spacer
    around, not that the search silently failed.
    """
    t5 = design_5p["switch"][slice(*design_5p["domains"]["toehold"])]
    t3 = design_3p["switch"][slice(*design_3p["domains"]["toehold"])]
    targets = (t5, t3, design_5p["trigger"], design_3p["trigger"])

    best_spacer, best_worst, best_gc = None, None, None
    for candidate in candidates:
        worst = max(_longest_complementary_run(candidate, t) for t in targets)
        cand_gc = gc_content(candidate)
        if (
            best_worst is None
            or worst < best_worst
            or (worst == best_worst and cand_gc < best_gc)
        ):
            best_spacer, best_worst, best_gc = candidate, worst, cand_gc
    return best_spacer, best_worst


def run_parallel_fake_sweep(jobs: list[FakeSweepJob], max_workers: int = 6) -> dict[str, dict]:
    """Same fork-context reasoning as every other ``run_parallel*`` in this module."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_fake_sweep_worker, jobs):
            results[outcome["key"]] = outcome
    return results


class ConstrainedBindJob(NamedTuple):
    """Real Boltzmann sampling of the fused AND molecule with ONE role's footprint
    HARD-CONSTRAINED to the exact base pairs it forms when bound to its own trigger
    in isolation (read off a real MFE fold, not an idealized/assumed alignment) --
    then asks whether the OTHER role's footprint still binds its own trigger for
    real, in the remainder of the structure, with that duplex locked in place.

    This is a CONDITIONAL check -- P(other role binds | this role is genuinely,
    fully bound) -- not the real unconstrained joint probability (``sampled_both``,
    computed elsewhere in this module) for the whole system folding freely. Forcing
    one duplex removes every competing conformation for that region from
    consideration, so this answers "CAN the other role still bind given this one is
    bound" rather than "does the real, unconstrained system actually settle there on
    its own" -- the two questions are different and this job answers only the first.
    See ``_constrained_bind_worker``'s own docstring for how the forced pairs are
    derived and enforced.

    ``fake`` is an extra off-target trigger strand, joined last -- "" means no fake
    present (the clean version of this check); a real sequence runs the same
    question with off-target noise also in the tube.
    """

    key: str
    fused: str
    trigger_bound: str  # the role being forced open (paired to this trigger)
    trigger_check: str  # the role being measured for real binding
    footprint_bound: tuple[int, int]
    footprint_check: tuple[int, int]
    fake: str  # "" = no fake present
    temperature: float
    n_samples: int = 1200
    threshold: float = 0.80


def _constrained_bind_worker(job: ConstrainedBindJob) -> dict:
    """Runs in a separate process, folding through the inherited shared ``FoldEngine``.

    Step 1: fold ``fused & trigger_bound`` ALONE (just those two strands) and read
    off the REAL base pairs the to-be-forced footprint actually forms with its
    trigger in this exact MFE structure -- whatever its real register/bulges turn
    out to be for this exact sequence, not a hand-derived idealized alignment.
    ``n_forced_pairs`` is returned alongside the result precisely so a degenerate
    case (this design's own real binding is weak or absent, so there is little or
    nothing to force) is visible as a number, never silently treated as if the
    footprint were fully, perfectly bound (CLAUDE.md sec 3).

    Step 2: build the full strand set (``fused & trigger_bound & trigger_check``,
    plus ``& fake`` when present) and force every one of those same base pairs with
    ``hc_add_bp(i, j, CONSTRAINT_CONTEXT_ALL_LOOPS | CONSTRAINT_CONTEXT_ENFORCE)`` --
    verified directly (not assumed) to both (a) actually force the pair into the
    MFE structure and (b) have real ``pbacktrack`` samples respect it with zero
    violations. ``FoldEngine.sample_structures`` takes those pairs 0-indexed and owns
    the conversion to ViennaRNA's 1-indexed ``hc_add_bp``, so no caller here repeats
    it.

    Step 3: real Boltzmann sampling of the resulting constrained ensemble, the same
    >=threshold-of-the-whole-footprint criterion as every other check in this
    module, to see how often ``footprint_check`` reads as bound to ``trigger_check``
    given the forced duplex.
    """
    engine = _engine(job.temperature)

    # ---- step 1: real base pairs of the forced duplex, from an actual fold ----
    bind_structure = engine.mfe(f"{job.fused}&{job.trigger_bound}").structure
    partner = _partner_table(bind_structure)
    fp_start, fp_end = job.footprint_bound
    forced_pairs = [
        (pos, partner[pos])
        for pos in range(fp_start, fp_end)
        if partner[pos] is not None and partner[pos] >= len(job.fused)
    ]

    # ---- step 2+3: constrained fold of the full strand set, real sampling ----
    strands = [job.fused, job.trigger_bound, job.trigger_check]
    if job.fake:
        strands.append(job.fake)
    samples = engine.sample_structures(
        "&".join(strands), job.n_samples, forced_pairs=forced_pairs
    )

    # External-strand rule (see _frac_paired_to_external): "the checked footprint got
    # opened by a strand from outside the molecule", not "is paired to anything" --
    # otherwise this check would score a footprint still shut in its own hairpin as
    # bound, which is the exact opposite of the question being asked.
    check_start, check_end = job.footprint_check
    n_fused = len(job.fused)
    bound = sum(
        1
        for s in samples
        if _frac_paired_to_external(s, check_start, check_end, n_fused) >= job.threshold
    )
    n = len(samples) or 1
    return {
        "key": job.key,
        "n_forced_pairs": len(forced_pairs),
        "footprint_bound_len": fp_end - fp_start,
        "check_bound_frac": bound / n,
        "n_samples": n,
        **_sample_coverage(samples),
    }


def run_parallel_constrained_bind(
    jobs: list[ConstrainedBindJob], max_workers: int = 6
) -> dict[str, dict]:
    """Same fork-context reasoning as every other ``run_parallel*`` in this module."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_constrained_bind_worker, jobs):
            results[outcome["key"]] = outcome
    return results


# ======================================================================================
# Sampled three-way state decomposition (stem_closed / misfolded / trigger_bound), used by
# ``toehold_context_report.ipynb`` (``and_eu_report.ipynb`` uses the exact workers at the
# end of this file). One job = one state (one fixed set of extra strands); the caller
# submits every state of every candidate as ONE list to ONE pool.map call per batch
# (CLAUDE.md sec 5), then averages whatever needs averaging itself.
# ======================================================================================


class SingleDecompJob(NamedTuple):
    """One state of one single-input switch: ``extra`` is the second strand (the real
    trigger, or a fake), or ``""`` for the switch alone. ``footprint`` is toehold+stem_up
    (what a trigger binds, and what
    ``_frac_paired_to_external``/``misfolded_fraction`` are asked about); ``stem_up`` is
    just the ascending arm (what ``stem_closed_fraction`` is asked about, paired against
    ``stem_down``).
    """

    key: str
    switch: str
    extra: str  # "" => switch alone
    footprint: tuple[int, int]
    stem_up: tuple[int, int]
    stem_down: tuple[int, int]
    temperature: float
    n_samples: int = 1200
    threshold: float = 0.70


def _single_decomp_worker(job: SingleDecompJob) -> dict:
    """Runs in a separate process, folding through the inherited shared ``FoldEngine``.

    Per sampled structure: ``trigger_bound`` (``_frac_paired_to_external`` over
    ``footprint``), ``stem_closed`` (``stem_closed_fraction`` over ``stem_up``/
    ``stem_down``), ``misfolded`` (``misfolded_fraction`` over ``footprint``/
    ``stem_down``) -- the same three metrics, the same partner-table stack walk,
    whichever state this job represents. "Open" means ``trigger_bound >= threshold``
    (Trap 1 -- never "paired to anything"); ``frac_open`` is the fraction of samples
    that clear it, which is what the ON/OFF ratio is built from (a frequency, so Trap
    4's floor at ``1/n_samples`` is meaningful on it, unlike a continuous mean).

    ``n_stem_closed``/``n_misfolded``: the same per-sample ``job.threshold`` crossing
    used for ``n_open``, applied to ``stem_closed``/``misfolded`` -- counts, so a report
    can show "k of N samples read as closed/misfolded" rather than a bare percentage.
    """
    engine = _engine(job.temperature)
    strands = f"{job.switch}&{job.extra}" if job.extra else job.switch
    samples = engine.sample_structures(strands, job.n_samples)
    n_self = len(job.switch)
    f0, f1 = job.footprint

    n_open = n_stem_closed = n_misfolded = 0
    sum_trigger_bound = sum_stem_closed = sum_misfolded = 0.0
    for structure in samples:
        trigger_bound = _frac_paired_to_external(structure, f0, f1, n_self)
        stem_closed = stem_closed_fraction(structure, job.stem_up, job.stem_down)
        misfolded = misfolded_fraction(structure, job.footprint, job.stem_down, n_self)
        sum_trigger_bound += trigger_bound
        sum_stem_closed += stem_closed
        sum_misfolded += misfolded
        if trigger_bound >= job.threshold:
            n_open += 1
        if stem_closed >= job.threshold:
            n_stem_closed += 1
        if misfolded >= job.threshold:
            n_misfolded += 1

    # Exact (partition-function) means, same strand string as the sampling above. Reports
    # show and score these *_bpp values, not the sampled mean_* fields, because sampled
    # structures disagree with the exact ensemble on multi-strand complexes.
    exact = _exact_decomp_means(
        engine.base_pair_probabilities(strands),
        n_self,
        job.footprint,
        job.stem_up,
        job.stem_down,
    )

    n = len(samples) or 1
    return {
        "key": job.key,
        "mean_stem_closed_bpp": exact["stem_closed"],
        "mean_misfolded_bpp": exact["misfolded"],
        "mean_trigger_bound_bpp": exact["trigger_bound"],
        "frac_open": n_open / n,
        "n_open": n_open,
        "n_stem_closed": n_stem_closed,
        "n_misfolded": n_misfolded,
        "mean_trigger_bound": sum_trigger_bound / n,
        "mean_stem_closed": sum_stem_closed / n,
        "mean_misfolded": sum_misfolded / n,
        "n_samples": n,
        **_sample_coverage(samples),
    }


def run_parallel_single_decomp(
    jobs: list[SingleDecompJob], max_workers: int = 6
) -> dict[str, dict]:
    """Same fork-context reasoning as every other ``run_parallel*`` in this module."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_single_decomp_worker, jobs):
            results[outcome["key"]] = outcome
    return results


# ======================================================================================
# EXACT-ONLY decomposition workers (``and_eu_report.ipynb``). Nothing below samples:
# sampled structures disagree with the exact partition function on these multi-strand
# complexes (measured on the top AND pairs: sampled "both open" 0.3-1% vs exact
# P(both designed duplexes) 32-69%), so the report is built from
# ``FoldEngine.base_pair_probabilities`` marginals plus ONE exact joint probability,
# ``FoldEngine.constrained_probability``, per state where the joint event is defined.
# ======================================================================================


def designed_pairs(
    engine,
    strands: str,
    footprints: tuple[tuple[int, int], ...],
    n_self: int,
) -> list[tuple[int, int]] | None:
    """The designed footprint-trigger duplex(es) of one state, as the MFE realises them.

    ``strands`` is the exact string the state is folded as (``&``-joined, fused molecule
    first, same strand order as every other call -- incl. ``both_triggers_extra``);
    ``n_self`` = ``len(fused)``, so an index ``>= n_self`` is a base of an external
    strand. The structure is ``engine.mfe(strands)`` (the one shared engine, cached; a
    ``&`` in the returned string is stripped so indices run over the concatenation).

    Returns every ``(i, j)`` with ``i`` inside one of ``footprints`` and ``j >= n_self``
    (0-indexed, ``i < j``) -- "the designed duplex as the MFE realises it". It is
    STRICT: ``constrained_probability`` of this list is the probability that every one
    of those pairs is present at once.

    ``None`` (never an empty list, never 1.0 downstream) when ANY footprint has no
    external pair in the MFE: that hairpin's duplex is then undefined, so the joint
    event is not defined for this state.
    """
    structure = engine.mfe(strands).structure.replace("&", "")
    partner = _partner_table(structure)
    pairs: list[tuple[int, int]] = []
    for start, end in footprints:
        found = [
            (i, partner[i])
            for i in range(start, end)
            if partner[i] is not None and partner[i] >= n_self
        ]
        if not found:
            return None
        pairs.extend(found)
    return pairs


class SingleExactJob(NamedTuple):
    """One state of one single-input switch, exact-only. ``extra`` is the second strand
    (the real trigger, or a fake), or ``""`` for the switch alone. ``footprint`` is
    toehold+stem_up; ``stem_up``/``stem_down`` the hairpin arms. ``with_joint`` asks
    for ``p_on`` (only meaningful for the switch + REAL trigger state)."""

    key: str
    switch: str
    extra: str  # "" => switch alone
    footprint: tuple[int, int]
    stem_up: tuple[int, int]
    stem_down: tuple[int, int]
    temperature: float
    with_joint: bool = False


def _single_exact_worker(job: SingleExactJob) -> dict:
    """Runs in a separate process, folding through the inherited shared ``FoldEngine``.
    Exact means of ``trigger_bound`` / ``stem_closed`` / ``misfolded`` from one
    ``base_pair_probabilities`` matrix, plus ``p_on`` -- the exact probability that the
    designed footprint-trigger duplex (:func:`designed_pairs`) is fully formed -- when
    ``with_joint``; ``p_on`` is ``None`` otherwise or when the duplex is undefined."""
    engine = _engine(job.temperature)
    strands = f"{job.switch}&{job.extra}" if job.extra else job.switch
    n_self = len(job.switch)
    exact = _exact_decomp_means(
        engine.base_pair_probabilities(strands), n_self, job.footprint, job.stem_up, job.stem_down
    )
    p_on = None
    if job.with_joint and job.extra:
        pairs = designed_pairs(engine, strands, (job.footprint,), n_self)
        if pairs is not None:
            p_on = engine.constrained_probability(strands, pairs)
    return {
        "key": job.key,
        "mean_stem_closed_bpp": exact["stem_closed"],
        "mean_misfolded_bpp": exact["misfolded"],
        "mean_trigger_bound_bpp": exact["trigger_bound"],
        "p_on": p_on,
    }


def run_parallel_single_exact(jobs: list[SingleExactJob], max_workers: int = 6) -> dict[str, dict]:
    """Same fork-context reasoning as every other ``run_parallel*`` in this module."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_single_exact_worker, jobs):
            results[outcome["key"]] = outcome
    return results


class AndDecompJob(NamedTuple):
    """One state of one AND pair, exact-only: ``extra`` lists whichever trigger/fake
    strands ride along with ``fused`` for this state (``()`` = alone). Both footprints
    get the three-way exact decomposition from ONE ``base_pair_probabilities`` matrix.
    ``with_joint`` asks for ``p_on`` (only meaningful for the +A+B state)."""

    key: str
    fused: str
    extra: tuple[str, ...]
    footprint_a: tuple[int, int]
    stem_up_a: tuple[int, int]
    stem_down_a: tuple[int, int]
    footprint_b: tuple[int, int]
    stem_up_b: tuple[int, int]
    stem_down_b: tuple[int, int]
    temperature: float
    with_joint: bool = False


def _and_decomp_worker(job: AndDecompJob) -> dict:
    """Runs in a separate process, folding through the inherited shared ``FoldEngine``.
    Same exact means as :func:`_single_exact_worker`, per side (A/B), plus ``p_on`` --
    the exact probability that BOTH designed duplexes (:func:`designed_pairs` over both
    footprints) are present in the same structure -- when ``with_joint``; ``None``
    otherwise or when either duplex is undefined in the MFE."""
    engine = _engine(job.temperature)
    strands = "&".join([job.fused, *job.extra]) if job.extra else job.fused
    n_self = len(job.fused)
    matrix = engine.base_pair_probabilities(strands)
    exact_a = _exact_decomp_means(matrix, n_self, job.footprint_a, job.stem_up_a, job.stem_down_a)
    exact_b = _exact_decomp_means(matrix, n_self, job.footprint_b, job.stem_up_b, job.stem_down_b)
    p_on = None
    if job.with_joint and job.extra:
        pairs = designed_pairs(engine, strands, (job.footprint_a, job.footprint_b), n_self)
        if pairs is not None:
            p_on = engine.constrained_probability(strands, pairs)
    return {
        "key": job.key,
        "mean_stem_closed_a_bpp": exact_a["stem_closed"],
        "mean_misfolded_a_bpp": exact_a["misfolded"],
        "mean_trigger_bound_a_bpp": exact_a["trigger_bound"],
        "mean_stem_closed_b_bpp": exact_b["stem_closed"],
        "mean_misfolded_b_bpp": exact_b["misfolded"],
        "mean_trigger_bound_b_bpp": exact_b["trigger_bound"],
        "p_on": p_on,
    }


def and_pair_jobs(
    built: dict,
    key_prefix: str,
    trigger_a: str,
    trigger_b: str,
    fakes_a: list[dict],
    fakes_b: list[dict],
    *,
    temperature: float,
) -> list[AndDecompJob]:
    """Every state job of one (pair, spacer): ``alone``, ``+A``, ``+B``, ``+A+B`` (the only
    one with ``with_joint``; strands via :func:`both_triggers_extra`), then per side each
    fake alone and with its own real trigger (``+fakeA{i}``/``+A+fakeA{i}``,
    ``+fakeB{i}``/``+B+fakeB{i}``). ``built`` is ``fuse()``'s output; ``fakes_a``/
    ``fakes_b`` are pool designs (only ``["trigger"]`` is read). Keys are
    ``f"{key_prefix}|{state}"``.
    """

    def job(state, extra, with_joint=False):
        return AndDecompJob(
            key=f"{key_prefix}|{state}",
            fused=built["fused"],
            extra=extra,
            footprint_a=built["footprint_5p"],
            stem_up_a=built["domains_5p"]["stem_up"],
            stem_down_a=built["domains_5p"]["stem_down"],
            footprint_b=built["footprint_3p"],
            stem_up_b=built["domains_3p"]["stem_up"],
            stem_down_b=built["domains_3p"]["stem_down"],
            temperature=temperature,
            with_joint=with_joint,
        )

    jobs = [
        job("alone", ()),
        job("+A", (trigger_a,)),
        job("+B", (trigger_b,)),
        job("+A+B", both_triggers_extra(trigger_a, trigger_b), with_joint=True),
    ]
    for i, fake in enumerate(fakes_a):
        jobs.append(job(f"+fakeA{i}", (fake["trigger"],)))
        jobs.append(job(f"+A+fakeA{i}", (trigger_a, fake["trigger"])))
    for i, fake in enumerate(fakes_b):
        jobs.append(job(f"+fakeB{i}", (fake["trigger"],)))
        jobs.append(job(f"+B+fakeB{i}", (trigger_b, fake["trigger"])))
    return jobs


def run_parallel_and_decomp(jobs: list[AndDecompJob], max_workers: int = 6) -> dict[str, dict]:
    """Same fork-context reasoning as every other ``run_parallel*`` in this module."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_and_decomp_worker, jobs):
            results[outcome["key"]] = outcome
    return results
