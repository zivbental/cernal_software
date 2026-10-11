"""Longest open run of BOTH hairpins of a fused AND switch, by sampling, in parallel (used by
part 2 of ``eu_and_v3.ipynb``).

An AND candidate has two hairpins, A (5' half) and B (3' half). For a structure s let r_A(s),
r_B(s) be the longest run of consecutive open ``stem_up`` nt of each hairpin (open = not paired to
a ``stem_down`` nt of the same hairpin), and k_A(s), k_B(s) the numbers of open nt. For a state

    Open = E[ min(r_A / L_A, r_B / L_B) ]   the expected longest run that is open in BOTH hairpins
                                            at once, each run as a fraction of its OWN stem (L_h)
    E[k] = E[ min(k_A, k_B) ]               the expected number of nt open in both hairpins (nt)

both estimated as the mean over structures drawn from the Boltzmann ensemble
(``FoldEngine.sample_structures``). The matrix gives E[k_A] and E[k_B] exactly, which checks the
sampler hairpin by hairpin, and bounds the joint quantities: min(r_A / L_A, r_B / L_B) <=
min(k_A / L_A, k_B / L_B), so Open <= E[min(k_A / L_A, k_B / L_B)] <= min(E[k_A] / L_A,
E[k_B] / L_B).

The report's ON (``ON_min``) and OFF use this per-hairpin Open (``open_frac_sampled``, a fraction
of 0-1): normalising each hairpin by its own stem keeps a long, half-open stem from being
hidden behind a short, fully open one, which min(r_A, r_B) / min(L_A, L_B) would do. The
information-only sum E[r_A + r_B] (``run_a_sampled`` + ``run_b_sampled``) is divided by
L_A + L_B in the notebook. ``open_sampled`` (E[min(r_A, r_B)], nt) stays for the sampler check.

Four states per candidate: alone, +A, +B, +A+B, sampled. Each ``AndJob.controls`` pair (two
mismatched triggers in the +A+B layout) gets the exact matrix E[k_A], E[k_B] only, with no
sampling: the sampler is unreliable for mismatched states, and min(E[k_A] / L_A, E[k_B] / L_B)
is an upper bound of the control's Open.

The strand order of +A+B is ``_joint_state_parallel.both_triggers_extra`` (fused & tB & tA,
nested). ViennaRNA's sampler is sensitive to which strand is written first, and the order that
matched the matrix puts a trigger on the side of the switch nearest its target hairpin: trigger A
before the fused strand, trigger B after it. No draw is filtered; the matrix check flags a bad
state.

Folding goes through the one shared ``FoldEngine`` published with
``_joint_state_parallel.use_fold_engine`` (CLAUDE.md sec 5); this module only schedules and counts.
"""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import NamedTuple

from _joint_state_parallel import _engine, both_triggers_extra
from _sampled_stem_parallel import open_counts


class AndJob(NamedTuple):
    """One AND candidate: the fused switch, the two real triggers and both hairpins' stems."""

    key: str
    fused: str
    trigger_a: str
    trigger_b: str
    stem_up_a: tuple[int, int]
    stem_down_a: tuple[int, int]
    stem_up_b: tuple[int, int]
    stem_down_b: tuple[int, int]
    temperature: float
    n_samples: int
    seed: int
    controls: tuple = ()  # pairs (trigger standing in for A, trigger standing in for B); () = none


def state_strands(job: AndJob) -> dict[str, tuple[str, int | None]]:
    """``{state: (strands, first_strand)}`` for the four states of a candidate."""
    both = "&".join((job.fused, *both_triggers_extra(job.trigger_a, job.trigger_b)))
    states = {
        "alone": (job.fused, None),
        "+A": (f"{job.fused}&{job.trigger_a}", 1),  # trigger A first: A is the 5' hairpin
        "+B": (f"{job.fused}&{job.trigger_b}", 0),  # fused first: B is the 3' hairpin
        "+A+B": (both, 2),  # fused & tB & tA written as tA, fused, tB
    }
    return states


def and_state(engine, strands: str, first_strand: int | None, job: AndJob) -> dict:
    """Open and E[k] of one state, sampled, plus each hairpin's E[k] from the exact matrix."""
    drawn = engine.sample_structures(
        strands, job.n_samples, seed=job.seed, first_strand=first_strand
    )
    sq = {"k_a": 0, "k_b": 0}
    sums = {"run_min": 0, "run_frac_min": 0.0, "k_min": 0, "k_a": 0, "k_b": 0, "r_a": 0, "r_b": 0}
    l_a = job.stem_up_a[1] - job.stem_up_a[0]
    l_b = job.stem_up_b[1] - job.stem_up_b[0]
    for structure in drawn:
        k_a, r_a = open_counts(structure, job.stem_up_a, job.stem_down_a)
        k_b, r_b = open_counts(structure, job.stem_up_b, job.stem_down_b)
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

    def matrix_open(stem_up, stem_down):
        closed = sum(bpp[i][j] for i in range(*stem_up) for j in range(*stem_down))
        return (stem_up[1] - stem_up[0]) - closed

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
        "k_a_matrix": matrix_open(job.stem_up_a, job.stem_down_a),
        "k_b_matrix": matrix_open(job.stem_up_b, job.stem_down_b),
        "n_drawn": n,
    }


def _matrix_open_nt(bpp, stem_up: tuple[int, int], stem_down: tuple[int, int]) -> float:
    """Exact E[k] of one hairpin from the base-pair-probability matrix."""
    closed = sum(bpp[i][j] for i in range(*stem_up) for j in range(*stem_down))
    return (stem_up[1] - stem_up[0]) - closed


def _and_worker(job: AndJob) -> dict:
    engine = _engine(job.temperature)
    out = {"key": job.key}
    for state, (strands, first_strand) in state_strands(job).items():
        out[state] = and_state(engine, strands, first_strand, job)
    # Controls (two mismatched triggers in the +A+B layout): exact matrix only. min(E[k_A] / L_A,
    # E[k_B] / L_B) is an upper bound of E[min(r_A / L_A, r_B / L_B)]; the sampler is unreliable
    # for mismatched states.
    out["controls"] = []
    for ctrl_a, ctrl_b in job.controls:
        strands = "&".join((job.fused, *both_triggers_extra(ctrl_a, ctrl_b)))
        bpp = engine.base_pair_probabilities(strands)

        out["controls"].append(
            {
                "k_a_matrix": _matrix_open_nt(bpp, job.stem_up_a, job.stem_down_a),
                "k_b_matrix": _matrix_open_nt(bpp, job.stem_up_b, job.stem_down_b),
            }
        )
    return out


def run_parallel_and(jobs: list[AndJob], max_workers: int = 6) -> dict[str, dict]:
    """One process-pool call for all candidates (fork, like every ``run_parallel*`` here)."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_and_worker, jobs, chunksize=2):
            results[outcome["key"]] = outcome
    return results
