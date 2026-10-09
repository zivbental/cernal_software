"""The document's inner J and outer Phi, separate from DEFAULT_V1 ranking."""

import math
from collections.abc import Iterable
from dataclasses import asdict
from itertools import batched

from engine.domain import CrisprObjective, CrisprObservables


def validate_objective(p: CrisprObjective) -> None:
    for name, value in asdict(p).items():
        if name == "scale_lambda" and value is None:
            continue
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
    for name in ("tau_off", "tau_on", "epsilon", "off_target_max"):
        if getattr(p, name) > 1:
            raise ValueError(f"{name} must be in [0,1]")
    if not p.tau_off < p.tau_on or p.epsilon == 0:
        raise ValueError("Require tau_off < tau_on and epsilon > 0")
    for a, b in ((p.w_energy, p.w_accessibility), (p.v_on, p.v_off), (p.w_spacer, p.w_trigger)):
        if not math.isclose(a + b, 1.0, abs_tol=1e-9):
            raise ValueError("Energy/accessibility, spacer and outer weight pairs must sum to 1")


def measurement_rejections(measured: dict[str, float], p: CrisprObjective) -> list[str]:
    """Validate available measurements and apply their existing hard gates."""
    for name, value in measured.items():
        if name == "dg_bind":
            if not math.isfinite(value):
                raise ValueError("Missing or invalid binding free energy")
        elif name in ("a_off", "a_on", "d_off", "d_on"):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Invalid probability {name}")
        else:
            raise ValueError(f"Unknown CRISPR measurement {name}")
    failures = []
    if "a_off" in measured and measured["a_off"] > p.tau_off:
        failures.append("a_off > tau_off")
    if "a_on" in measured and measured["a_on"] < p.tau_on:
        failures.append("a_on < tau_on")
    if "d_off" in measured and measured["d_off"] >= p.epsilon:
        failures.append("d_off >= epsilon")
    if "d_on" in measured and measured["d_on"] >= p.epsilon:
        failures.append("d_on >= epsilon")
    return failures


def inner_objective(o: CrisprObservables, p: CrisprObjective) -> dict:
    """Hard gates precede J. None serializes mathematical -infinity honestly."""
    validate_objective(p)
    failures = measurement_rejections(asdict(o), p)
    ja = p.w_on * o.a_on - p.w_off * o.a_off
    je = -o.dg_bind
    if not failures and p.scale_lambda is None:
        raise ValueError("Compute lambda from the ranking batch before scoring")
    j = None if failures else p.w_energy * je + p.w_accessibility * p.scale_lambda * ja
    return {
        "feasible": not failures,
        "rejections": failures,
        "j_accessibility": ja,
        "j_energy": je,
        "j": j if not failures else None,
    }


def outer_objective(
    j: float, eta_on: float, eta_off: float, q_trigger: float, p: CrisprObjective
) -> dict:
    validate_objective(p)
    if not math.isfinite(j):
        raise ValueError("J must be finite")
    for value in (eta_on, eta_off, q_trigger):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("External spacer/trigger metrics must lie in [0,1]")
    qs = p.v_on * eta_on + p.v_off * (1 - eta_off)
    q_pair = p.w_spacer * qs + p.w_trigger * q_trigger
    failures = []
    if eta_off > p.off_target_max:
        failures.append("eta_off > off_target_max")
    j_positive = max(0.0, j)
    return {
        "q_spacer": qs,
        "q_trigger": q_trigger,
        "q_pair": q_pair,
        "j_positive": j_positive,
        "phi": None if failures else q_pair * j_positive,
        "selectable": not failures and j > 0,
        "rejections": failures,
    }


def calibrate_scale(observations: Iterable[CrisprObservables], w_on: float, w_off: float) -> float:
    """Compute mean |JE| / mean |JA| over one ranking batch, in bounded memory.

    Both means use the same candidates, so the ratio equals the ratio of sums.
    Zero mean energy gives lambda=0; zero mean accessibility is undefined.
    """
    if any(not math.isfinite(w) or w < 0 for w in (w_on, w_off)):
        raise ValueError("Need nonnegative finite weights")
    energy, accessibility, count = 0.0, 0.0, 0
    for batch in batched(observations, 1024, strict=False):
        for o in batch:
            if not math.isfinite(o.dg_bind) or any(
                not math.isfinite(v) or not 0 <= v <= 1 for v in (o.a_on, o.a_off)
            ):
                raise ValueError("Invalid batch observation")
        energy = math.fsum((energy, math.fsum(abs(o.dg_bind) for o in batch)))
        accessibility = math.fsum(
            (accessibility, math.fsum(abs(w_on * o.a_on - w_off * o.a_off) for o in batch))
        )
        count += len(batch)
    if count == 0 or accessibility == 0:
        raise ValueError("Cannot compute lambda: empty batch or zero mean |JA|")
    result = energy / accessibility
    if not math.isfinite(result):
        raise ValueError("Computed lambda is not finite")
    return result
