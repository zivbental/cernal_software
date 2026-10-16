"""Stem opening of toehold hairpins by Boltzmann sampling, and the construction and screens of the
two-input fused AND (the science behind ``eu_and_v3`` and the eukaryotic AND gate).

One implementation, two callers: the ``eu_and_v3`` notebook and its workers
(``src/engine/gates/notebooks/toehold_and``) re-export these names, and
:class:`engine.gates.toehold.EukaryoticToeholdAndGate` calls them. CLAUDE.md sec 1: two
implementations of one measurement produce two numbers and only one reaches the report.

Definitions (spec: ``notebooks/toehold_and/eu_and_v3_spec.md``). A hairpin has ``stem_up`` (its 5'
side) and ``stem_down`` (its 3' side). In a structure, a ``stem_up`` nucleotide is *open* when it is
not paired to a ``stem_down`` nucleotide of the same hairpin; ``k`` is the number of open
nucleotides and ``r`` the longest run of consecutive open ones. For a fused AND switch with
hairpins A (5') and B (3'), the joint opening of a state is

    Open = E[ min(r_A / L_A, r_B / L_B) ]

estimated as the mean over structures drawn from the Boltzmann ensemble
(``FoldEngine.sample_structures``), with each hairpin normalised by its own stem length.

Nothing here constructs a ``FoldEngine`` or imports ``RNA``: every function that folds takes the
shared engine as an argument (CLAUDE.md sec 5). Coordinates are 0-indexed, start inclusive, end
exclusive. A measurement that cannot be made is ``None``, never ``0.0`` (CLAUDE.md sec 3).
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence

from engine.sequences import find_augs, gc_content, reverse_complement

#: The notebook's own order of the four sampled states of a candidate.
AND_STATES: tuple[str, ...] = ("alone", "+A", "+B", "+A+B")


# ----------------------------------------------------------------------------------------------
# Counting open nucleotides in one structure
# ----------------------------------------------------------------------------------------------
def open_counts(
    structure: str, stem_up: tuple[int, int], stem_down: tuple[int, int]
) -> tuple[int, int]:
    """``(k, r)`` of a dot-bracket (``&`` removed): the number of open ``stem_up`` nt, and the
    longest stretch of consecutive open ones. Open = not paired to a ``stem_down`` nt."""
    stack: list[int] = []
    partner: dict[int, int] = {}
    for i, char in enumerate(structure):
        if char == "(":
            stack.append(i)
        elif char == ")":
            j = stack.pop()
            partner[i], partner[j] = j, i
    open_count = longest = run = 0
    for i in range(*stem_up):
        if stem_down[0] <= partner.get(i, -1) < stem_down[1]:
            run = 0
        else:
            open_count += 1
            run += 1
            longest = max(longest, run)
    return open_count, longest


# ----------------------------------------------------------------------------------------------
# Sampling one state
# ----------------------------------------------------------------------------------------------
def single_state(
    engine,
    strands: str,
    *,
    stem_up: tuple[int, int],
    stem_down: tuple[int, int],
    n_samples: int,
    seed: int | None,
    first_strand: int | None = None,
) -> dict:
    """E[r] and E[k] of one single-hairpin state, sampled, plus E[k] from the exact matrix.

    Means divide by the number of draws actually returned (ViennaRNA can return fewer than
    ``n_samples``); they are ``None`` when there were none -- never 0.
    """
    drawn = engine.sample_structures(strands, n_samples, seed=seed, first_strand=first_strand)
    counts = [open_counts(structure, stem_up, stem_down) for structure in drawn]
    bpp = engine.base_pair_probabilities(strands)
    closed = sum(bpp[i][j] for i in range(*stem_up) for j in range(*stem_down))
    n = len(counts)
    mean_k = sum(k for k, _ in counts) / n if n else None
    sd_k = (sum((k - mean_k) ** 2 for k, _ in counts) / n) ** 0.5 if n else None
    return {
        "open_nt_sd": sd_k,
        "run_nt_sampled": sum(r for _, r in counts) / n if n else None,
        "open_nt_sampled": mean_k,
        "open_nt_matrix": (stem_up[1] - stem_up[0]) - closed,
        "n_drawn": len(drawn),
    }


def both_triggers_extra(trigger_a: str, trigger_b: str) -> tuple[str, str]:
    """The ONE place the strand order of a two-real-trigger AND state is decided.

    Returns ``(trigger_b, trigger_a)``: B is appended FIRST, A LAST. ViennaRNA's multi-strand
    folding only represents structures that are NESTED along the written strand order. The fused
    switch is written 5'->3' as hairpin A (footprint A) ... hairpin B (footprint B), then the
    appended strands. A written ``fused & tA & tB`` makes footprint A <-> tA and footprint B <-> tB
    CROSS (a pseudoknot: A < B < tA < tB), which the model cannot represent -- measured, tA bound
    0.99 but tB bound 0.00, so the joint ON state was ~0 for every pair. ``fused & tB & tA`` nests
    (A < B < tB < tA: the LATER strand binds the EARLIER footprint) and both bind (0.98/0.99).
    Physically the molecules are separate, so the order is irrelevant; this is purely a
    model-representation requirement. Every state containing both real triggers must take its
    strands from here.
    """
    return (trigger_b, trigger_a)


def and_state_strands(
    fused: str, trigger_a: str, trigger_b: str
) -> dict[str, tuple[str, int | None]]:
    """``{state: (strands, first_strand)}`` for the four states of one AND candidate.

    ``first_strand`` is the strand ``FoldEngine.sample_structures`` writes first: ViennaRNA's
    sampler is sensitive to it, and the order that matched the exact matrix puts a trigger on the
    side of the switch nearest its target hairpin (trigger A before the fused strand for +A, the
    fused strand first for +B, and trigger A first -- ``tA, fused, tB`` -- for +A+B).
    """
    both = "&".join((fused, *both_triggers_extra(trigger_a, trigger_b)))
    return {
        "alone": (fused, None),
        "+A": (f"{fused}&{trigger_a}", 1),  # trigger A first: A is the 5' hairpin
        "+B": (f"{fused}&{trigger_b}", 0),  # fused first: B is the 3' hairpin
        "+A+B": (both, 2),  # fused & tB & tA written as tA, fused, tB
    }


def matrix_open_nt(bpp, stem_up: tuple[int, int], stem_down: tuple[int, int]) -> float:
    """Exact E[k] of one hairpin from the base-pair-probability matrix."""
    closed = sum(bpp[i][j] for i in range(*stem_up) for j in range(*stem_down))
    return (stem_up[1] - stem_up[0]) - closed


def and_state(
    engine,
    strands: str,
    first_strand: int | None,
    *,
    stem_up_a: tuple[int, int],
    stem_down_a: tuple[int, int],
    stem_up_b: tuple[int, int],
    stem_down_b: tuple[int, int],
    n_samples: int,
    seed: int | None,
) -> dict:
    """Open and E[k] of one AND state, sampled, plus each hairpin's E[k] from the exact matrix."""
    drawn = engine.sample_structures(strands, n_samples, seed=seed, first_strand=first_strand)
    sq = {"k_a": 0, "k_b": 0}
    sums = {"run_min": 0, "run_frac_min": 0.0, "k_min": 0, "k_a": 0, "k_b": 0, "r_a": 0, "r_b": 0}
    l_a = stem_up_a[1] - stem_up_a[0]
    l_b = stem_up_b[1] - stem_up_b[0]
    for structure in drawn:
        k_a, r_a = open_counts(structure, stem_up_a, stem_down_a)
        k_b, r_b = open_counts(structure, stem_up_b, stem_down_b)
        sums["run_min"] += min(r_a, r_b)
        sums["run_frac_min"] += min(r_a / l_a, r_b / l_b)
        sums["k_min"] += min(k_a, k_b)
        sums["k_a"] += k_a
        sq["k_a"] += k_a * k_a
        sq["k_b"] += k_b * k_b
        sums["k_b"] += k_b
        sums["r_a"] += r_a
        sums["r_b"] += r_b
    n = len(drawn)
    bpp = engine.base_pair_probabilities(strands)

    def sd(key):
        return max(sq[key] / n - (sums[key] / n) ** 2, 0.0) ** 0.5 if n else None

    return {
        "k_a_sd": sd("k_a"),
        "k_b_sd": sd("k_b"),
        "open_sampled": sums["run_min"] / n if n else None,
        "open_frac_sampled": sums["run_frac_min"] / n if n else None,
        "k_min_sampled": sums["k_min"] / n if n else None,
        "k_a_sampled": sums["k_a"] / n if n else None,
        "k_b_sampled": sums["k_b"] / n if n else None,
        "run_a_sampled": sums["r_a"] / n if n else None,
        "run_b_sampled": sums["r_b"] / n if n else None,
        "k_a_matrix": matrix_open_nt(bpp, stem_up_a, stem_down_a),
        "k_b_matrix": matrix_open_nt(bpp, stem_up_b, stem_down_b),
        "n_drawn": n,
    }


# ----------------------------------------------------------------------------------------------
# Verification of a sampled state against the exact matrix
# ----------------------------------------------------------------------------------------------
def sd_or_default(sd: float | None, default: float) -> float:
    """``sd`` when it was measured (including a valid 0.0), ``default`` when it is missing."""
    if sd is None or (isinstance(sd, float) and math.isnan(sd)):
        return default
    return sd


def verification_tolerance(
    sd: float | None, n_drawn: int, *, default_sd: float, sigma: float, floor_nt: float
) -> float:
    """tau = sigma * sd / sqrt(N) + floor; ``default_sd`` (<= L/2) only if ``sd`` is missing."""
    return sigma * sd_or_default(sd, default_sd) / math.sqrt(n_drawn) + floor_nt


def state_ok(state: dict, stem_len: int, *, sigma: float, floor_nt: float) -> bool:
    """Single-switch state verified: sampled mean k and sampled Open agree with the exact matrix."""
    run, k, m = state["run_nt_sampled"], state["open_nt_sampled"], state["open_nt_matrix"]
    if run is None or k is None:
        return False
    tol = verification_tolerance(
        state.get("open_nt_sd"),
        state["n_drawn"],
        default_sd=stem_len / 2.0,
        sigma=sigma,
        floor_nt=floor_nt,
    )
    return abs(k - m) <= tol and run <= m + tol


def open_value(state: dict, name: str) -> float | None:
    """Open of an AND state in nt, as the sampler check needs it: E[r_A] + E[r_B] for +A+B (bounded
    by E[k_A] + E[k_B]), E[min(r_A, r_B)] for the others. The ranking uses ``open_frac_sampled``."""
    if state["open_sampled"] is None:
        return None
    if name == "+A+B":
        return state["run_a_sampled"] + state["run_b_sampled"]
    return state["open_sampled"]


def state_ok_and(
    state: dict, name: str, l_a: int, l_b: int, *, sigma: float, floor_nt: float
) -> bool:
    """AND state verified: each hairpin's sampled E[k] agrees with its matrix value within its
    own tolerance, and the sampled Open does not exceed the matrix bound."""
    if state["open_sampled"] is None or state["k_a_sampled"] is None:
        return False
    n = state["n_drawn"]
    tol_a = verification_tolerance(
        state.get("k_a_sd"), n, default_sd=l_a / 2.0, sigma=sigma, floor_nt=floor_nt
    )
    tol_b = verification_tolerance(
        state.get("k_b_sd"), n, default_sd=l_b / 2.0, sigma=sigma, floor_nt=floor_nt
    )
    if name == "+A+B":  # r_A + r_B <= k_A + k_B, and the matrix gives E[k_A] + E[k_B] exactly
        bound = state["k_a_matrix"] + state["k_b_matrix"] + tol_a + tol_b
    else:  # min(r_A, r_B) <= min(k_A, k_B) <= min(E[k_A], E[k_B]) in expectation
        bound = min(state["k_a_matrix"], state["k_b_matrix"]) + max(tol_a, tol_b)
    return (
        abs(state["k_a_sampled"] - state["k_a_matrix"]) <= tol_a
        and abs(state["k_b_sampled"] - state["k_b_matrix"]) <= tol_b
        and open_value(state, name) <= bound
    )


# ----------------------------------------------------------------------------------------------
# Sequence-similarity screens
# ----------------------------------------------------------------------------------------------
def _is_complementary(x: str, y: str, *, allow_wobble: bool) -> tuple[bool, bool]:
    """``(is_match, is_wobble)`` for one antiparallel base pair -- Watson-Crick always matches;
    G*U/U*G matches only when ``allow_wobble``."""
    wc = {("A", "U"), ("U", "A"), ("G", "C"), ("C", "G")}
    if (x, y) in wc:
        return True, False
    if allow_wobble and (x, y) in {("G", "U"), ("U", "G")}:
        return True, True
    return False, False


def longest_complementary_run_wobble(a: str, b: str, wobble_max_fraction: float) -> tuple[int, int]:
    """Longest antiparallel-complementary run between ``a`` and ``b`` whose share of G*U/U*G
    wobble pairs is at most ``wobble_max_fraction`` -- the wobble-tolerant counterpart of
    :func:`longest_complementary_run` (a real, ViennaRNA-confirmed 12 bp helix scored as only
    4 nt under exact-complement-only matching because four of its positions were wobbles).

    Antiparallel: ``a[i]`` pairs with ``b`` read backwards, so every alignment is a diagonal of
    ``a`` against ``b[::-1]`` and the pair test (Watson-Crick, or wobble) supplies the
    complement. On each diagonal every maximal stretch of consecutive pairing positions is
    examined for its longest **sub-run** that meets the cap: a wobble-heavy prefix or suffix
    must not hide an acceptable stretch behind it (``GAUAUAUUUAC`` against ``GUGGGUGUGUU`` has a
    10-position suffix with 5 wobble pairs, which meets a cap of 0.5, while the whole stretch
    does not).

    Returns ``(run_length, n_wobble_positions_in_that_run)``; among runs of the longest length the
    one with the fewest wobble pairs (then the first found) is reported.
    """
    b_rev = b[::-1]
    n, m = len(a), len(b_rev)
    best_len, best_wobble = 0, 0

    def best_subrun(flags: list[int]) -> tuple[int, int]:
        prefix = [0]
        for w in flags:
            prefix.append(prefix[-1] + w)
        for length in range(len(flags), 0, -1):
            fewest = None
            for start in range(len(flags) - length + 1):
                wobbles = prefix[start + length] - prefix[start]
                if wobbles <= wobble_max_fraction * length + 1e-9 and (
                    fewest is None or wobbles < fewest
                ):
                    fewest = wobbles
            if fewest is not None:
                return length, fewest
        return 0, 0

    for shift in range(-(n - 1), m):  # a[i] is aligned with b_rev[i + shift]
        first, last = max(0, -shift), min(n, m - shift)
        flags: list[int] = []
        for i in range(first, last + 1):  # one past the end closes the final stretch
            pairs = False
            if i < last:
                pairs, wobble = _is_complementary(a[i], b_rev[i + shift], allow_wobble=True)
            if pairs:
                flags.append(1 if wobble else 0)
                continue
            if len(flags) >= max(best_len, 1):
                length, wobbles = best_subrun(flags)
                if length > best_len or (length == best_len and wobbles < best_wobble):
                    best_len, best_wobble = length, wobbles
            flags = []
    return best_len, best_wobble


def longest_identity_run(a: str, b: str) -> int:
    """Longest SAME-DIRECTION identical substring shared by ``a`` and ``b`` -- literal sequence
    identity, not antiparallel complementarity (ordinary longest-common-substring DP).

    WHY it exists beside the complementarity checks: two triggers drawn from the same or
    overlapping transcript region are near-identical substrings of each other, which predicts
    near-identical BINDING TARGETS (cross-talk) but is structurally invisible to a
    complementarity check -- identical sequences are generally not self-complementary. No wobble
    tolerance: identity is binary per position.
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


def longest_complementary_run(a: str, b: str) -> int:
    """Longest stretch that could base-pair between ``a`` and ``b`` in an antiparallel duplex --
    the longest common substring between ``a`` and ``reverse_complement(b)``. Pure string
    matching, no folding: a fast pre-screen for "would this even have a chance to hybridize"."""
    return longest_identity_run(a, reverse_complement(b))


def trigger_pair_too_similar(
    trigger_a: str, trigger_b: str, *, max_overlap_nt: int, wobble_max_fraction: float
) -> bool:
    """True when an AND pair's own two REAL triggers are too similar to each other by EITHER of two
    independent checks, each compared against ``max_overlap_nt``: a complementary run (wobble
    included -- would they hybridize to each other) or a same-direction identity run (are they
    (nearly) the same sequence, i.e. drawn from the same transcript region).

    Called before any fold for the pair, so no compute is spent on a rejected pair.
    """
    comp_run, _wobble = longest_complementary_run_wobble(trigger_a, trigger_b, wobble_max_fraction)
    identity_run = longest_identity_run(trigger_a, trigger_b)
    return comp_run > max_overlap_nt or identity_run > max_overlap_nt


# ----------------------------------------------------------------------------------------------
# The spacer between the two hairpins
# ----------------------------------------------------------------------------------------------
def generate_spacer_candidates(
    n: int, min_length: int = 15, max_length: int = 20, seed: int = 1
) -> list[str]:
    """A fixed, reproducible pool of low-GC candidate spacer sequences -- lengths cycle over
    ``min_length..max_length`` so the whole requested range is covered, and every base is drawn
    A/U-biased (A-U pairs are weaker than G-C, hence a low-GC spacer). Seeded by the caller, never
    wall-clock or module-level ``random.`` state (CLAUDE.md sec 6): the SAME pool for the same seed.
    """
    rng = random.Random(seed)
    bases = ("A", "U", "G", "C")
    weights = (0.35, 0.35, 0.15, 0.15)
    span = max_length - min_length + 1
    return [
        "".join(rng.choices(bases, weights=weights, k=min_length + (i % span))) for i in range(n)
    ]


def pick_optimized_spacer(design_5p, design_3p, candidates: Sequence[str]) -> tuple[str, int]:
    """Picks the candidate spacer with the smallest worst-case complementary run against either
    design's toehold OR trigger ("minimal interaction" estimated as no hybridization with
    triggers or toeholds). Ties broken by lower GC, then by pool order (deterministic,
    first-found wins). Returns ``(spacer, worst_run)`` so the caller can see how good the best
    available candidate actually was.

    ``design_5p``/``design_3p`` carry ``switch``, ``domains`` (with ``toehold``) and ``trigger``.
    """
    t5 = design_5p["switch"][slice(*design_5p["domains"]["toehold"])]
    t3 = design_3p["switch"][slice(*design_3p["domains"]["toehold"])]
    targets = (t5, t3, design_5p["trigger"], design_3p["trigger"])

    best_spacer, best_worst, best_gc = None, None, None
    for candidate in candidates:
        worst = max(longest_complementary_run(candidate, t) for t in targets)
        cand_gc = gc_content(candidate)
        if best_worst is None or worst < best_worst or (worst == best_worst and cand_gc < best_gc):
            best_spacer, best_worst, best_gc = candidate, worst, cand_gc
    return best_spacer, best_worst


# ----------------------------------------------------------------------------------------------
# Fusing two single switches into one AND construct
# ----------------------------------------------------------------------------------------------
def fuse(design_5p, design_3p, cut_before, keep_after, spacer):
    """One AND candidate: every domain from both halves, relocated into the fused frame.

    ``design_*`` are dicts with ``switch`` (the RNA), ``domains`` (name -> ``(start, end)``) and
    ``line_no`` (a label used in messages). Returns ``(built, problem)``. ``built["domains_5p"]``/
    ``["domains_3p"]`` carry every surviving domain's fused-frame span, not just the toehold.
    ``problem`` is non-None when either design lacks the domain its cut is defined by, lacks
    ``stem_up`` (the ascending arm a trigger's footprint needs), or when a relocated span does not
    hold the sequence it started as -- slicing a guessed offset instead would still return a
    sequence, and it would fold into a plausible-looking wrong answer nothing downstream could
    catch (CLAUDE.md sec 6: every coordinate translation is an off-by-one until it is checked).

    The 5' half is kept up to the start of its ``cut_before`` domain; the 3' half from the end of
    its ``keep_after`` domain. ``spacer`` sits between the two bodies: unshifted-domain-wise for the
    5' half and folded into the 3' half's shift -- a physical separator between the two hairpins,
    not part of either design's own domain set.
    """
    for label, design, domain in (("5'", design_5p, cut_before), ("3'", design_3p, keep_after)):
        if domain not in design["domains"]:
            return None, f"{label} line {design['line_no']}: no {domain!r} domain"

    cut_5p = design_5p["domains"][cut_before][0]
    keep_3p = design_3p["domains"][keep_after][1]
    body_5p = design_5p["switch"][:cut_5p]
    body_3p = design_3p["switch"][keep_3p:]
    fused = body_5p + spacer + body_3p
    shift = len(body_5p) + len(spacer) - keep_3p

    # Every 5' domain that ends at or before the cut survives unshifted; every 3' domain
    # that starts at or after the keep point survives, shifted by how far it moved.
    domains_5p = {name: span for name, span in design_5p["domains"].items() if span[1] <= cut_5p}
    domains_3p = {
        name: (start + shift, end + shift)
        for name, (start, end) in design_3p["domains"].items()
        if start >= keep_3p
    }

    for label, domains, design, base_shift in (
        ("5'", domains_5p, design_5p, 0),
        ("3'", domains_3p, design_3p, shift),
    ):
        for name, (start, end) in domains.items():
            original_start, original_end = start - base_shift, end - base_shift
            if fused[start:end] != design["switch"][original_start:original_end]:
                return None, f"{label} line {design['line_no']}: {name} does not survive relocation"

    for label, domains, design in (("5'", domains_5p, design_5p), ("3'", domains_3p, design_3p)):
        missing = [name for name in ("toehold", "stem_up") if name not in domains]
        if missing:
            return (
                None,
                f"{label} line {design['line_no']}: missing {', '.join(missing)} after the cut",
            )

    return (
        {
            "fused": fused,
            "domains_5p": domains_5p,
            "domains_3p": domains_3p,
            "toehold_5p": domains_5p["toehold"],
            "toehold_3p": domains_3p["toehold"],
            # The footprint is toehold + the ascending arm -- exactly the region the trigger
            # reverse-complements against.
            "footprint_5p": (domains_5p["toehold"][0], domains_5p["stem_up"][1]),
            "footprint_3p": (domains_3p["toehold"][0], domains_3p["stem_up"][1]),
            "spacer_span": (len(body_5p), len(body_5p) + len(spacer)),
        },
        None,
    )


def upstream_augs(built) -> tuple[int, ...]:
    """Start positions (0-based, in the fused RNA) of every AUG that begins before the second
    hairpin's ``stem_down``.

    The intended start codon of an AND construct is the payload's, after the second hairpin (and
    its Kozak); an AUG anywhere upstream of that hairpin -- in the first hairpin, the spacer, or
    the second hairpin's toehold, stem or loop -- is a competing start codon. An AUG that begins at
    or after the start of the second ``stem_down`` is not counted. Uses
    ``engine.sequences.find_augs`` (CLAUDE.md sec 1: one AUG finder).
    """
    limit = built["domains_3p"]["stem_down"][0]
    return tuple(i for i in find_augs(built["fused"]) if i < limit)


def percentile_95(values: Iterable[float | None]) -> float | None:
    """The 95th percentile of the absolute values (nearest rank below); ``None`` if there are none.

    The seed-to-seed noise band of ``ON - OFF`` that defines the tied group of an AND ranking.
    """
    kept = sorted(abs(v) for v in values if v is not None)
    if not kept:
        return None
    return kept[int(0.95 * (len(kept) - 1))]
