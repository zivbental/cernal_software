"""Statistics behind the ``eu_and_v3`` reports that must be testable on their own.

Three things live here because a silent mistake in any of them changes what the report says:

* the per-state verification tolerance (:func:`verification_tolerance`, :func:`state_ok`,
  :func:`state_ok_and`) -- a *measured* standard deviation of 0 is a real value (a state that
  never varies), only a missing one (``None``/NaN) falls back to the conservative L/2;
* the medians of report columns (:func:`median_or_none`, :func:`median_text`) -- an empty
  column (for example no control triggers were available) is "n/a", never 0 and never an error.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable


def sd_or_default(sd: float | None, default: float) -> float:
    """``sd`` when it was measured (including a valid 0.0), ``default`` when it is missing."""
    if sd is None or (isinstance(sd, float) and math.isnan(sd)):
        return default
    return sd


def verification_tolerance(
    sd: float | None, n_drawn: int, *, default_sd: float, sigma: float, floor_nt: float
) -> float:
    """tau = sigma * sd / sqrt(N) + floor; ``default_sd`` (<= L/2) is used only if ``sd`` is missing."""
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
    """Open of an AND state: E[r_A] + E[r_B] for +A+B (ON), E[min(r_A, r_B)] for the others."""
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


def median_or_none(values: Iterable[float | None]) -> float | None:
    """Median of the non-missing values, ``None`` when there are none."""
    kept = [v for v in values if v is not None]
    return statistics.median(kept) if kept else None


def median_text(values: Iterable[float | None], *, unit: str = "", digits: int = 1) -> str:
    """The median as text with its unit, or ``n/a`` when no value is available."""
    m = median_or_none(values)
    return "n/a" if m is None else f"{m:.{digits}f}{unit}"


def pct_text(value: float | None, *, digits: int = 1) -> str:
    """A percentage as text, ``n/a`` for a missing value."""
    return "n/a" if value is None else f"{value:.{digits}f}%"
