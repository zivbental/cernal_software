"""Recheck the Wiki revision against local historical rows, without folding again.

Run with ``uv run python tools/and_revision_audit.py --out var/and-revision/audit.json``.
Large axes_c8 shards are local research inputs, not supplied by a fresh clone. Their
digests are recorded. This analysis neither establishes their original provenance nor
turns old designs into current-compiler candidates. Reuses the existing correlation,
cell-identity, threshold and barrier-join implementations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import experiment_contrasts as barrier_analysis
from analyse_axes import cells_of, spearman
from experiment_contrasts import contrasts, measured

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from engine.gates.toehold import ToeholdAndGate  # noqa: E402

RESULTS = ROOT / "src/engine/gates/notebooks/toehold_and/results"
IDENTITY = ("gene_a", "gene_b", "x_start", "xstar_start", "len_x", "geom", "stem_index", "closure")
OUTCOMES = ("xstar_engA_10", "mainpre_engA_10", "dG_open_11", "P_open_11")
NUMBERS = (
    set(OUTCOMES)
    | {
        "a_site_energy",
        "lock_energy",
        "open_11",
        "ied_gain",
        "ied_gain_worst",
        "ied_rbs_linker_00",
        "ied_rbs_linker_01",
        "ied_rbs_linker_10",
        "ied_rbs_linker_11",
    }
    | {f"dG_open_{s}" for s in ("00", "01", "10", "11")}
    | {name for name, _, _ in ToeholdAndGate.THRESHOLDS}
)


def summary(values):
    return {
        "n": len(values),
        "median": st.median(values) if values else None,
        "mean": st.fmean(values) if values else None,
    }


def posthoc_checks(row):
    """Use the engine's exact checks; this is NOT a refold at the current producer."""
    return not ToeholdAndGate.gate_violations(ToeholdAndGate, row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(RESULTS.glob("axes_c8_[0-5].csv"))
    if len(paths) != 6:
        raise SystemExit("Expected all six local axes_c8 shards; no partial-cohort analysis.")
    records, full_count, feasible = 0, 0, 0
    source = []
    rhos = defaultdict(list)
    correlation_rows = defaultdict(int)
    factorial = defaultdict(list)
    rates = defaultdict(lambda: [0, 0])
    for path in paths:
        with path.open("rb") as handle:
            source.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": hashlib.file_digest(handle, "sha256").hexdigest(),
                }
            )
        rows = []
        with path.open(encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                row = {key: raw.get(key) for key in (*IDENTITY, "upper3", "lower3", "skipped")}
                row.update(
                    {
                        key: float(raw[key]) if raw.get(key) not in (None, "", "None") else None
                        for key in NUMBERS
                    }
                )
                row["posthoc_22_pass"] = posthoc_checks(row)
                rows.append(row)
        records += len(rows)
        full_count += sum(not row["skipped"] for row in rows)
        feasible += sum(row["posthoc_22_pass"] for row in rows)
        for group in cells_of(rows).values():
            for x, y in (
                ("a_site_energy", "xstar_engA_10"),
                ("a_site_energy", "mainpre_engA_10"),
                ("a_site_energy", "dG_open_11"),
                ("lock_energy", "xstar_engA_10"),
            ):
                usable = [r for r in group if r.get(x) is not None and r.get(y) is not None]
                rho = (
                    spearman([r[x] for r in usable], [r[y] for r in usable])
                    if len(usable) >= 5
                    else None
                )
                if rho is not None:
                    rhos[f"{x} vs {y}"].append(rho)
            # Trace the ambiguous historical OFF-reference statement against opening
            # separation, with BOTH gains oriented as larger-is-better.
            for ref, off_states in (
                ("00", ("00",)),
                ("single", ("01", "10")),
                ("all", ("00", "01", "10")),
            ):
                xs, ys = [], []
                for row in group:
                    values = [row.get(f"ied_rbs_linker_{s}") for s in off_states]
                    opening = [row.get(f"dG_open_{s}") for s in ("00", "01", "10")]
                    if any(
                        v is None
                        for v in (
                            *values,
                            *opening,
                            row.get("ied_rbs_linker_11"),
                            row.get("dG_open_11"),
                        )
                    ):
                        continue
                    xs.append(min(opening) - row["dG_open_11"])
                    ys.append(min(values) - row["ied_rbs_linker_11"])
                rho = spearman(xs, ys) if len(xs) >= 5 else None
                if rho is not None:
                    rhos[f"opening_gain vs IED_gain_OFF_{ref}"].append(rho)
                    correlation_rows[ref] += len(xs)
        by_design = defaultdict(dict)
        for row in rows:
            key = tuple(row[k] for k in IDENTITY)
            level = (row["upper3"], row["lower3"])
            if level in by_design[key]:
                raise ValueError(f"Duplicate factorial row: {key} {level}")
            by_design[key][level] = row
        baseline = ("trigger_derived", "trigger_derived")
        aua = ("WWW_AUA", "trigger_derived")
        wobble = ("trigger_derived", "wobble_GU")
        both = ("WWW_AUA", "wobble_GU")
        for levels in by_design.values():
            if not all(k in levels for k in (baseline, aua, wobble, both)):
                continue
            for label, level in (
                ("baseline", baseline),
                ("AUA", aua),
                ("wobble", wobble),
                ("both", both),
            ):
                rates[label][0] += 1
                rates[label][1] += levels[level]["posthoc_22_pass"]
            for outcome in OUTCOMES:
                vals = [levels[k].get(outcome) for k in (baseline, aua, wobble, both)]
                if any(v is None for v in vals):
                    continue
                control, a, w, aw = vals
                factorial[f"both_minus_baseline:{outcome}"].append(aw - control)
                factorial[
                    f"interaction_both_minus_AUA_minus_wobble_plus_baseline:{outcome}"
                ].append(aw - a - w + control)
        print(f"Read {path.name}: {len(rows)} rows", flush=True)
    # Force the tracked ON join rather than the helper's optional, ignored full grid.
    barrier_analysis.GRID = barrier_analysis.JOIN
    barrier_rows = measured()
    within = [
        pair for pair in contrasts(barrier_rows, 8.0, 0.5, 10000) if pair[2] == "same trigger pair"
    ]
    report = {
        "analysis_version": "and-revision-audit-v1",
        "producer_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "shared_code_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "tools/analyse_axes.py",
                "tools/experiment_contrasts.py",
                "src/engine/gates/toehold.py",
                "uv.lock",
            )
        },
        "thresholds": ToeholdAndGate.THRESHOLDS,
        "barrier_inputs": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in sorted(barrier_analysis.BARRIERS.glob("*.csv"))
        ],
        "status": (
            "Historical post-hoc analysis; not a current-compiler yield or wet-lab validation"
        ),
        "sources": source,
        "rows": records,
        "four_state_rows": full_count,
        "posthoc_current_22_pass": feasible,
        "within_cell_rho": {
            k: summary(v)
            | {"positive_cells": sum(x > 0 for x in v), "negative_cells": sum(x < 0 for x in v)}
            for k, v in rhos.items()
        },
        "off_reference_correlations": {
            "x": "min(dG_open_00,01,10)-dG_open_11",
            "y": "min(IED_OFF_reference)-IED_11",
            "directions": "both gains higher-is-better",
            "summary": (
                "median Spearman within gene/window/lenx/geometry cell; "
                ">=5 complete rows, constants omitted"
            ),
            "usable_rows_by_reference": dict(correlation_rows),
        },
        "matched_AUA_x_wobble": {
            "controls": "same genes/windows/lenx/geometry/secondary stem/closure",
            "rates": {k: {"n": n, "posthoc_22_pass": passed} for k, (n, passed) in rates.items()},
            "deltas": {k: summary(v) for k, v in factorial.items()},
            "interpretation": (
                "Not a test of longer effective A toeholds or independent bulge x "
                "stem-energy compensation. No p-values or causal claim."
            ),
        },
        "barrier_contrasts": {
            "rows_with_ON": len(barrier_rows),
            "within_pair_contrasts_gap_at_least_8_ON_tolerance_0_5": len(within),
            "examples": contrasts(barrier_rows, 8.0, 0.5, 3),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
