"""Expected longest open run of the stem, by sampling, in parallel (used by ``eu_and_v3.ipynb``).

For one state (a switch alone, or a switch with its real trigger) the main quantity is

    Open = E[r] = sum over structures s of P(s) * r(s)

where r(s) is the length of the longest stretch of consecutive ``stem_up`` nt that are not paired
to a ``stem_down`` nt in structure s. It is estimated as the mean of r over structures drawn from
the Boltzmann ensemble (``FoldEngine.sample_structures``).

The matrix cannot give E[r] (it does not know which positions are open together), but it gives
the expected *number* of open nt exactly, E[k] = sum over stem_up nt i of
(1 - sum over stem_down nt j of p_ij), and E[r] <= E[k] always. Each state therefore also returns
E[k] sampled and from the matrix: the sampler is checked on E[k], and E[r] against that bound.

``DesignJob.controls`` are mismatched triggers: their states are not sampled (the sampler is
unreliable for them) but get the exact matrix E[k], an upper bound of their Open, from
``matrix_open_nt``.

No draw is filtered: ViennaRNA's sampler returns wrong draws for some switch + trigger pairs, and
the comparison with the matrix is what flags a bad state.

Folding goes through the one shared ``FoldEngine`` published with
``_joint_state_parallel.use_fold_engine`` (CLAUDE.md sec 5); this module only schedules and counts.
"""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import NamedTuple

from _joint_state_parallel import _engine


class DesignJob(NamedTuple):
    """One design: the switch with its real trigger, and the switch alone."""

    key: str
    switch: str
    trigger: str
    stem_up: tuple[int, int]
    stem_down: tuple[int, int]
    temperature: float
    n_samples: int
    seed: int
    controls: tuple = ()  # mismatched triggers, not similar to ``trigger``; () = no controls


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


def stem_open_state(engine, strands: str, job: DesignJob) -> dict:
    """E[r] and E[k] of one state, sampled, plus E[k] from the exact matrix.

    Means divide by the number of draws actually returned (ViennaRNA can return fewer than
    ``job.n_samples``); they are ``None`` when there were none -- never 0.
    """
    drawn = engine.sample_structures(strands, job.n_samples, seed=job.seed)
    counts = [open_counts(structure, job.stem_up, job.stem_down) for structure in drawn]
    bpp = engine.base_pair_probabilities(strands)
    closed = sum(bpp[i][j] for i in range(*job.stem_up) for j in range(*job.stem_down))
    n = len(counts)
    mean_k = sum(k for k, _ in counts) / n if n else None
    sd_k = (sum((k - mean_k) ** 2 for k, _ in counts) / n) ** 0.5 if n else None
    return {
        "open_nt_sd": sd_k,
        "run_nt_sampled": sum(r for _, r in counts) / len(counts) if counts else None,
        "open_nt_sampled": sum(k for k, _ in counts) / len(counts) if counts else None,
        "open_nt_matrix": (job.stem_up[1] - job.stem_up[0]) - closed,
        "n_drawn": len(drawn),
    }


def matrix_open_nt(engine, strands: str, job: DesignJob) -> float:
    """Exact E[k] of one state from the base-pair-probability matrix (no sampling)."""
    bpp = engine.base_pair_probabilities(strands)
    closed = sum(bpp[i][j] for i in range(*job.stem_up) for j in range(*job.stem_down))
    return (job.stem_up[1] - job.stem_up[0]) - closed


def _design_worker(job: DesignJob) -> dict:
    engine = _engine(job.temperature)
    out = {
        "key": job.key,
        "on": stem_open_state(engine, f"{job.switch}&{job.trigger}", job),
        "alone": stem_open_state(engine, job.switch, job),
    }
    # Controls use the exact matrix only: E[k] of the switch with a mismatched trigger is an upper
    # bound of its Open, and the sampler is unreliable for such mismatched states.
    out["controls"] = [
        {"open_nt_matrix": matrix_open_nt(engine, f"{job.switch}&{trigger}", job)}
        for trigger in job.controls
    ]
    return out


def run_parallel_designs(jobs: list[DesignJob], max_workers: int = 6) -> dict[str, dict]:
    """One process-pool call for all designs (fork, like every ``run_parallel*`` here)."""
    results: dict[str, dict] = {}
    context = multiprocessing.get_context("fork")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        for outcome in pool.map(_design_worker, jobs, chunksize=4):
            results[outcome["key"]] = outcome
    return results
