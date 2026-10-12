"""Statistics behind the ``eu_and_v3`` reports that must be testable on their own.

Three things live here because a silent mistake in any of them changes what the report says or
how far it can be trusted:

* the per-state verification tolerance (:func:`verification_tolerance`, :func:`state_ok`,
  :func:`state_ok_and`) -- a *measured* standard deviation of 0 is a real value (a state that
  never varies), only a missing one (``None``/NaN) falls back to the conservative L/2;
* the medians of report columns (:func:`median_or_none`, :func:`median_text`) -- an empty
  column (for example no control triggers were available) is "n/a", never 0 and never an error;
* the run provenance (:func:`run_provenance`) printed in every report: code revision, input file
  checksum and folding-model settings.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import subprocess
from collections.abc import Iterable
from pathlib import Path


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


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation of two equally long rank/value lists, ``None`` when it is
    undefined: fewer than two items, or no variation in either list."""
    if len(x) != len(y):
        raise ValueError("spearman needs two lists of the same length")
    n = len(x)
    if n < 2:
        return None
    rx, ry = _average_ranks(x), _average_ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True)) / math.sqrt(vx * vy)


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def noise_summary(changes: Iterable[float | None]) -> tuple[float | None, float | None]:
    """``(median, 95th percentile)`` of the absolute seed-to-seed changes, ``(None, None)`` when
    there is none (no candidate, or none with both runs measured)."""
    values = sorted(abs(c) for c in changes if c is not None)
    if not values:
        return None, None
    return statistics.median(values), values[int(0.95 * (len(values) - 1))]


def num_text(value: float | None, digits: int = 2, unit: str = "") -> str:
    """A number as text, ``n/a`` when it is unavailable."""
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def _git(repo_dir: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def file_sha256(path: str | Path) -> str:
    """SHA-256 of a file, streamed."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def describe_folding_model(provenance: dict) -> str:
    """One line from ``FoldEngine.provenance()``: library version, energy table, settings."""
    cfg, energy = provenance["configuration"], provenance["energy_parameters"]
    on_off = lambda flag: "on" if flag else "off"  # noqa: E731
    return (
        f"ViennaRNA {provenance['viennarna_version']}; {energy['name']} energy parameters "
        f"(sha256 {energy['sha256'][:12]}); {cfg['temperature_celsius']:g} °C; dangles "
        f"{cfg['dangles']}; special hairpins {on_off(cfg['special_hairpins'])}; no lonely pairs "
        f"{on_off(cfg['no_lonely_pairs'])}; no G-U {on_off(cfg['no_gu'])}; no G-U closure "
        f"{on_off(cfg['no_gu_closure'])}; sampling adds uniq_ML = 1 only"
    )


def run_provenance(csv_path: str | Path, folding_provenance: dict, repo_dir: str | Path) -> dict:
    """What a reader needs to check a report: the code revision (and whether files were modified
    since that commit), the input file with its checksum, and the folding model."""
    revision = _git(Path(repo_dir), "rev-parse", "HEAD")
    if revision is None:
        code = "unavailable (not a git checkout)"
    else:
        changed = _git(Path(repo_dir), "status", "--porcelain", "--untracked-files=no")
        code = revision + (" (+ uncommitted changes)" if changed else "")
    path = Path(csv_path)
    return {
        "code_revision": code,
        "input_file": f"{path.name}, sha256 {file_sha256(path)}, {path.stat().st_size} bytes",
        "folding_model": describe_folding_model(folding_provenance),
    }
