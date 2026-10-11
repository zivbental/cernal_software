"""Shared helpers of the toehold notebooks (used by ``eu_and_v3.ipynb`` and its workers).

Lives in a real file, not a notebook cell, because Python multiprocessing workers must be able
to import their target functions from a module.

**All folding goes through the one shared ``FoldEngine``** (``CLAUDE.md`` sec 1/sec 5: it is the
only place a gate family may fold, and exactly one instance exists per run). This module does
not ``import RNA`` and does not construct an engine: the notebook publishes it with
:func:`use_fold_engine` before submitting any jobs, and the pools run under the "fork" start
method, so every worker inherits that *same* instance. One engine, one temperature, one recorded
ViennaRNA version, exactly as if the work had stayed in-process.

Contents: the engine hook (:func:`use_fold_engine`, :func:`_engine`); the one strand-order rule
of the two-trigger AND state (:func:`both_triggers_extra`); the sequence-similarity screens
(:func:`trigger_pair_too_similar`, :func:`pick_fake_trigger`, :func:`pick_fake_triggers`); and
the spacer pool and choice (:func:`generate_spacer_candidates`, :func:`pick_optimized_spacer`).
"""

from __future__ import annotations

import random

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
    :func:`_longest_complementary_run` (longest stretch of ``a`` whose bases pair with ``b``
    read backwards, i.e. against ``reverse_complement(b)``) but tolerating G*U/U*G wobble
    matches -- a trap
    recorded in the old ``and_eu_report_spec.md`` (git history): a real, ViennaRNA-confirmed
    12bp helix scored as only 4nt under exact-complement-only matching because four of its
    positions were wobbles.

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
    # Antiparallel: a[i] pairs with b read backwards. The pair test below supplies the
    # complement, so b is only reversed here; complementing it too would turn "A pairs
    # with U" into a test of "A equals A" (A*12 against U*12 then scores 0).
    b_rev = b[::-1]
    n, m = len(a), len(b_rev)
    prev = [(0, 0)] * (m + 1)
    best_len, best_wobble = 0, 0
    for i in range(1, n + 1):
        curr = [(0, 0)] * (m + 1)
        ai = a[i - 1]
        for j in range(1, m + 1):
            bj = b_rev[j - 1]
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
        "".join(rng.choices(bases, weights=weights, k=min_length + (i % span))) for i in range(n)
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
        if best_worst is None or worst < best_worst or (worst == best_worst and cand_gc < best_gc):
            best_spacer, best_worst, best_gc = candidate, worst, cand_gc
    return best_spacer, best_worst
