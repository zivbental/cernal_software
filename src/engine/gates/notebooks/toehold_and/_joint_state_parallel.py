"""Parallel worker for ``joint_state()`` (see ``toehold_and_eu_test.ipynb``'s
"joint-state helpers" cell for the serial, documented original).

Lives in a real file, not a notebook cell, because Python multiprocessing on macOS uses
the "spawn" start method: a worker process re-imports the target function from its module,
which only works for a function defined in an actual importable file -- a function defined
by ``exec()`` inside a notebook cell has no module a spawned child can import it from.

Each job is fully self-contained (sequences, temperature, footprint spans as plain
tuples/strings) so a worker never needs the shared ``FoldEngine`` instance or its cache --
consistent with ``joint_state()``'s own docstring: this check already builds its own
``fold_compound`` per call, so it was already independent of the shared cache before this
file existed. Splitting the work across processes changes nothing about what is computed,
only how many candidates get checked per second.
"""

from __future__ import annotations

import math
import multiprocessing
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from typing import NamedTuple

from engine.sequences import gc_content, reverse_complement


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

    WHY NOT "paired to anything", which every worker in this file used to count: in the
    fused AND construct the footprint reaches 80-90% paired with NO trigger present at
    all -- measured directly, roughly half of it to its own stem_down (the intended OFF
    hairpin) and half to the OTHER hairpin's toehold (real cross-hairpin talk). A plain
    "any non-dot character" count therefore cleared an 80%-of-footprint "open"
    threshold in up to 81% of alone-state samples, and that number fed the AND score's
    leak term -- so "open" was reporting intramolecular misfolding as trigger
    activation, and the AND ranking was built on it.

    Requiring the partner to live on another strand makes "open" mean what its name
    claims: this footprint was opened by something that arrived from outside the
    molecule. A real trigger and an off-target fake both count, deliberately -- in the
    legitimate states the only external strands present ARE the real triggers, and in
    a leak state a fake occupying the footprint is exactly the leak being measured.
    Folding with no second strand at all (``n_self == len(structure)``) therefore
    yields 0.0 by construction, which is correct: nothing external is present to open
    anything.
    """
    partner = _partner_table(structure)
    external = sum(
        1 for i in range(start, end) if partner[i] is not None and partner[i] >= n_self
    )
    return external / (end - start)


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


class JointStateJob(NamedTuple):
    key: str  # caller's own identifier for this candidate, echoed back in the result
    fused: str
    trigger_5p: str
    trigger_3p: str
    footprint_5p: tuple[int, int]
    footprint_3p: tuple[int, int]
    temperature: float
    n_samples: int = 1200
    threshold: float = 0.80


def _worker(job: JointStateJob) -> dict:
    """Runs in a separate process -- imports RNA locally, same precondition
    (``uniq_ML=1``) as the serial ``joint_state()`` this mirrors."""
    import RNA

    model = RNA.md()
    model.temperature = job.temperature
    model.uniq_ML = 1
    fold_compound = RNA.fold_compound(
        f"{job.fused}&{job.trigger_5p}&{job.trigger_3p}", model
    )
    fold_compound.pf()
    samples = fold_compound.pbacktrack(job.n_samples)

    # "Open" = paired to an EXTERNAL strand, not to anything -- see
    # _frac_paired_to_external's own docstring for the measured reason why.
    n_fused = len(job.fused)
    fp5, fp3 = job.footprint_5p, job.footprint_3p
    neither = a_only = b_only = both = 0
    for structure in samples:
        a_open = _frac_paired_to_external(structure, fp5[0], fp5[1], n_fused) >= job.threshold
        b_open = _frac_paired_to_external(structure, fp3[0], fp3[1], n_fused) >= job.threshold
        if a_open and b_open:
            both += 1
        elif a_open:
            a_only += 1
        elif b_open:
            b_only += 1
        else:
            neither += 1
    n = len(samples) or 1
    return {
        "key": job.key,
        "neither": neither / n,
        "a_only": a_only / n,
        "b_only": b_only / n,
        "both": both / n,
        "n_samples": n,
    }


class SingleStateJob(NamedTuple):
    """Single-input analog of ``JointStateJob`` -- one switch, one trigger (or none),
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
    """Runs in a separate process, same ``uniq_ML=1`` precondition as ``_worker``."""
    import RNA

    model = RNA.md()
    model.temperature = job.temperature
    model.uniq_ML = 1
    strands = f"{job.switch}&{job.trigger}" if job.trigger else job.switch
    fold_compound = RNA.fold_compound(strands, model)
    fold_compound.pf()
    samples = fold_compound.pbacktrack(job.n_samples)

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
    ("+A+B", ("trigger_a", "trigger_b")),
    ("+A+fake1", ("trigger_a", "fake_a")),
    ("+B+fake2", ("trigger_b", "fake_b")),
    ("+A+B+fake1+fake2", ("trigger_a", "trigger_b", "fake_a", "fake_b")),
)
# Only these three states get a real partition-function base-pair-probability matrix
# (the marginal check) alongside the Boltzmann-sampled joint answer -- the fake-only
# states are leakage checks on the SAMPLED open-fraction only, per the request that
# spawned this job type; computing a full n^2 matrix for every one of ten states per
# pair would multiply the already-heavy cost of this sweep for numbers nobody asked for.
FAKE_SWEEP_MATRIX_STATES = frozenset({"+A", "+B", "+A+B"})


def _fake_sweep_worker(job: FakeSweepJob) -> dict:
    """Runs in a separate process -- same ``uniq_ML=1`` precondition as ``_worker``.

    Recomputes accessibility from a raw ``fc.bpp()`` call rather than importing
    ``engine.gates.toehold._mean_unpaired`` / ``FoldEngine.base_pair_probabilities``:
    this worker is deliberately self-contained (see this module's own docstring on why
    -- a forked worker never touches the shared ``FoldEngine`` cache), so it mirrors the
    same 1-indexed-upper-triangular-to-0-indexed-symmetric conversion
    ``base_pair_probabilities`` documents, inline, the same way ``frac_paired`` already
    mirrors the sampling logic in every other worker in this file instead of importing
    it from the notebook's own helpers cell (which a forked child cannot import from).
    """
    import RNA

    model = RNA.md()
    model.temperature = job.temperature
    model.uniq_ML = 1

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
        fold_compound = RNA.fold_compound(strands, model)
        fold_compound.pf()
        samples = fold_compound.pbacktrack(job.n_samples)
        n_samples = len(samples) or 1
        # Per-structure classification, not two independent marginals -- min(a_open,
        # b_open) from separately-counted fractions would still be right even if A and
        # B were open in entirely DIFFERENT sampled structures, never simultaneously.
        # "sampled_both" is the count of structures where BOTH footprints clear
        # threshold in the SAME draw -- the only number that actually answers "does
        # this molecule ever really do both at once" (this exact marginal-vs-joint gap
        # is why joint_state()/JointStateJob exist elsewhere in this notebook; this
        # worker had been computing only the marginals until this was checked).
        a_open = b_open = both_open = 0
        for s in samples:
            # External-strand rule, not "paired to anything" -- this is the metric the
            # AND score's leak term is built from, and the alone state was previously
            # reporting 80%+ "both open" with no trigger present at all.
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
            raw = fold_compound.bpp()  # 1-indexed, upper-triangular
            matrix = [[0.0] * n for _ in range(n)]
            for i in range(1, n + 1):
                row = raw[i]
                for j in range(i + 1, min(len(row), n + 1)):
                    p = row[j]
                    if p:
                        matrix[i - 1][j - 1] = p
                        matrix[j - 1][i - 1] = p
            state_out["marginal_a_access"] = mean_unpaired(matrix, fp5[0], fp5[1])
            state_out["marginal_b_access"] = mean_unpaired(matrix, fp3[0], fp3[1])
        out[name] = state_out
    return out


def pick_fake_design(design_5p, design_3p, exclude_ranks, pool, start_offset=0):
    """Pool design with no meaningful sequence complementarity to EITHER A's or B's own
    footprint (toehold+stem_up) -- a real off-target trigger picked by actual sequence
    dissimilarity, not by genomic position.

    Previously this screened candidates by trigger *position* on the transcript (two
    windows counted as "the same region" if they overlapped by some nt threshold). That
    is the wrong criterion for "this fake shouldn't bind": two triggers from
    non-overlapping windows can still share real, accidental complementarity to a
    footprint (verified directly -- one positionally-"non-overlapping" candidate had an
    8nt exact complementary run against a footprint whose own REAL trigger's best run
    was only 6nt, i.e. a fake that could out-compete the true pair on this same metric).
    Conversely, if a candidate has NO meaningful sequence complementarity to the
    footprint, it cannot meaningfully bind it regardless of where it came from on the
    transcript -- position becomes irrelevant once sequence similarity is the actual
    thing being screened for.

    A candidate qualifies only when its longest exact complementary run
    (``_longest_complementary_run``) against EACH footprint is STRICTLY LESS than that
    footprint's own real trigger's longest complementary run against itself --
    self-calibrated per design rather than one arbitrary nt cutoff for every candidate:
    a fake is only accepted if it could not plausibly out-compete the real trigger even
    on this same crude metric.

    Starts the scan at ``start_offset`` and wraps around, rather than always scanning
    from the front of ``pool`` -- same reasoning as before: always starting from index 0
    would let one early-pool design's accidental complementarity profile dominate every
    pair's result instead of rotating across genuinely different fakes.

    Lives here (not a notebook cell) so every sweep that needs a fake trigger -- single-
    switch or AND -- imports the exact same selection rule instead of each cell keeping
    its own copy that can quietly drift apart.
    """

    def _footprint(design):
        start, end = design["domains"]["toehold"][0], design["domains"]["stem_up"][1]
        return design["switch"][start:end]

    footprint_5p, footprint_3p = _footprint(design_5p), _footprint(design_3p)
    real_run_5p = _longest_complementary_run(footprint_5p, design_5p["trigger"])
    real_run_3p = _longest_complementary_run(footprint_3p, design_3p["trigger"])

    n = len(pool)
    for step in range(n):
        candidate = pool[(start_offset + step) % n]
        if candidate["rank"] in exclude_ranks:
            continue
        run_5p = _longest_complementary_run(footprint_5p, candidate["trigger"])
        run_3p = _longest_complementary_run(footprint_3p, candidate["trigger"])
        if run_5p < real_run_5p and run_3p < real_run_3p:
            return candidate
    return None


def _longest_complementary_run(a: str, b: str) -> int:
    """Longest stretch that could actually base-pair between ``a`` and ``b`` in an
    antiparallel duplex -- the longest common substring between ``a`` and
    ``reverse_complement(b)``, found by ordinary substring DP. Pure string matching,
    no folding: a fast pre-screen for "would this even have a chance to hybridize",
    not a replacement for the real Boltzmann-sampled ON/OFF check every selected
    spacer still goes through afterwards.
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
    A/U-biased (A-U pairs are weaker than G-C, this notebook's own established
    low-GC-spacer rationale). Seeded with a literal constant, never wall-clock or
    module-level ``random.`` state (CLAUDE.md sec 6) -- the SAME pool every run, so a
    later run picking a different spacer for some pair means the pair's own scoring
    changed, never that the candidate pool silently changed under it.
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
    against either design's toehold OR trigger -- "minimal interaction" estimated as
    "no hybridization with triggers or toeholds", per this task's own instruction.
    Ties broken by lower GC (this notebook's low-GC spacer rationale), then by pool
    order (deterministic, first-found wins -- CLAUDE.md sec 6, no randomness in a
    tie-break either). Returns ``(spacer, worst_run)`` so the caller can see how good
    the best available candidate actually was, not just which one won -- a worst_run
    of e.g. 8 on a 20-candidate pool says the pool needs to be bigger or the pair is
    just hard to spacer around, not that the search silently failed.
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
    """Fake-sweep counterpart to ``run_parallel`` -- same fork-context reasoning."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_fake_sweep_worker, jobs):
            results[outcome["key"]] = outcome
    return results


def run_parallel(jobs: list[JointStateJob], max_workers: int = 6) -> dict[str, dict]:
    """Runs every job across a process pool and returns ``{key: joint_state_dict}``.

    ``max_workers`` defaults to 6, not the machine's full core count (8 on the dev
    machine this was written on) -- leaving headroom keeps the machine responsive while
    a batch runs, since this is meant to be launched interactively, not as a dedicated
    batch job.
    """
    # "fork" (not the platform default "spawn" on macOS) so a worker starts as a clone
    # of this process instead of re-importing whatever launched it -- "spawn" re-imports
    # the __main__ module in every worker, which breaks when the launcher is a Jupyter
    # kernel or a notebook-exec harness rather than a plain `if __name__ == "__main__":`
    # script (that re-import tries to re-run the launcher's own top-level code in the
    # child and the pool falls over). Each job is a plain, already-built NamedTuple of
    # strings and numbers, so fork's copy-on-write semantics cost nothing extra here.
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_worker, jobs):
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
    """Runs in a separate process -- imports RNA locally, same ``uniq_ML=1``
    precondition as every other real-sampling worker in this module.

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
    violations. ViennaRNA's C API is 1-indexed for this call; the conversion happens
    here so nothing else in this module needs to know that.

    Step 3: real Boltzmann sampling of the resulting constrained ensemble, the same
    >=threshold-of-the-whole-footprint criterion as every other check in this
    module, to see how often ``footprint_check`` reads as bound to ``trigger_check``
    given the forced duplex.
    """
    import RNA

    model = RNA.md()
    model.temperature = job.temperature
    model.uniq_ML = 1

    # ---- step 1: real base pairs of the forced duplex, from an actual fold ----
    bind_only_fc = RNA.fold_compound(f"{job.fused}&{job.trigger_bound}", model)
    bind_structure, _ = bind_only_fc.mfe()
    stack: list[int] = []
    partner: list[int | None] = [None] * len(bind_structure)
    for i, ch in enumerate(bind_structure):
        if ch == "(":
            stack.append(i)
        elif ch == ")":
            j = stack.pop()
            partner[i] = j
            partner[j] = i
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
    fold_compound = RNA.fold_compound("&".join(strands), model)
    option = RNA.CONSTRAINT_CONTEXT_ALL_LOOPS | RNA.CONSTRAINT_CONTEXT_ENFORCE
    for i, j in forced_pairs:
        fold_compound.hc_add_bp(i + 1, j + 1, option)  # 1-indexed per the C API
    fold_compound.pf()
    samples = fold_compound.pbacktrack(job.n_samples)

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
