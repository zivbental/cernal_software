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

``DesignJob.controls`` are mismatched triggers. By default their states are not sampled: ViennaRNA's
sampler was found to disagree strongly with its own matrix on such states (the draws leave the stem
open), so they get the exact matrix E[k], an upper bound of their Open, from ``matrix_open_nt``.
With ``sample_controls`` they are sampled like the other states and carry the same matrix check;
that is for engines whose sampler is sound on them (the separate ``nupack_report`` notebook).

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

from engine.gates.tools.stem_opening import matrix_open_nt as _matrix_open_nt
from engine.gates.tools.stem_opening import open_counts as open_counts
from engine.gates.tools.stem_opening import single_state


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
    sample_controls: bool = False  # True: sample the controls too; False: exact matrix E[k] only


def stem_open_state(engine, strands: str, job: DesignJob) -> dict:
    """E[r] and E[k] of one state, sampled, plus E[k] from the exact matrix (the engine tool's
    :func:`single_state`, with this job's stem spans, sample count and seed)."""
    return single_state(
        engine,
        strands,
        stem_up=job.stem_up,
        stem_down=job.stem_down,
        n_samples=job.n_samples,
        seed=job.seed,
    )


def matrix_open_nt(engine, strands: str, job: DesignJob) -> float:
    """Exact E[k] of one state from the base-pair-probability matrix (no sampling)."""
    return _matrix_open_nt(engine.base_pair_probabilities(strands), job.stem_up, job.stem_down)


def _design_worker(job: DesignJob) -> dict:
    engine = _engine(job.temperature)
    out = {
        "key": job.key,
        "on": stem_open_state(engine, f"{job.switch}&{job.trigger}", job),
        "alone": stem_open_state(engine, job.switch, job),
    }
    if job.sample_controls:
        out["controls"] = [
            stem_open_state(engine, f"{job.switch}&{trigger}", job) for trigger in job.controls
        ]
    else:
        # exact matrix only: E[k] with a mismatched trigger is an upper bound of its Open, and
        # ViennaRNA's sampler is unreliable for such states
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
