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

# One implementation of every shared screen and of the spacer pool: the engine tool that the
# eukaryotic AND gate also calls (CLAUDE.md sec 1). The names stay importable from here because
# the notebook and its tests use them (explicit ``as`` aliases mark intentional re-exports).
from engine.gates.tools.stem_opening import (
    _is_complementary as _is_complementary,
)
from engine.gates.tools.stem_opening import (
    both_triggers_extra as both_triggers_extra,
)
from engine.gates.tools.stem_opening import (
    generate_spacer_candidates as generate_spacer_candidates,
)
from engine.gates.tools.stem_opening import (
    longest_complementary_run as _longest_complementary_run,  # noqa: F401
)
from engine.gates.tools.stem_opening import (
    longest_complementary_run_wobble as _longest_complementary_run_wobble,  # noqa: F401
)
from engine.gates.tools.stem_opening import (
    longest_identity_run as _longest_identity_run,
)
from engine.gates.tools.stem_opening import (
    pick_optimized_spacer as pick_optimized_spacer,
)
from engine.gates.tools.stem_opening import (
    trigger_pair_too_similar as trigger_pair_too_similar,
)

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
