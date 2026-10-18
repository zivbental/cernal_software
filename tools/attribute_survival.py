"""WHICH filter eliminates each axis level — attributed, not lumped.

    uv run python tools/attribute_survival.py

`feasible()` applies **ten** tests, not one: the ON ceiling, the dead schemes, and floors on
`aug_11`, `lock`, `lock01`, `hairpin_worst`, `engages_stem_mfe`, `engaged_arm_11`, accessibility,
plus a categorical off-target disqualification. Reporting that a level "survives at 2.7%" says
nothing about which of the ten did it, and naming one of them without separating them is a claim
with no measurement behind it. This separates them.

Two numbers per (level, filter):

* **first-loss** — the filter that rejects the design, applying them in `feasible()`'s own order.
  This is the honest attribution of the funnel as it actually runs, and it is order-dependent by
  construction: a design failing three tests is charged to the first.
* **marginal** — designs this filter rejects that NO OTHER filter would have. Order-free, and the
  number that answers "what would switching this filter off buy", which first-loss cannot.

Both are reported because they disagree whenever filters overlap, and the disagreement is the
interesting part: a filter with a large first-loss and a small marginal is mostly redundant.

A level's survival is not automatically an artifact. `WWW_AUA` is an all-weak override, so an ON
state that opens more cheaply is the lever doing what Green intended, not a bias — which is why
this prints the loss per filter and leaves the reading to whoever knows the chemistry.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "src/engine/gates/notebooks/toehold_and"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(NB))

# ruff: noqa: E402 - the notebook imports must follow the sys.path.insert above.
import objective_panel as op

#: One predicate per `feasible()` test, in `feasible()`'s own order, each True when the row is
#: REJECTED. Copied from `feasible()` rather than imported because `feasible()` returns survivors
#: and cannot say why; if it changes, this list has to change with it and the count below will
#: disagree with `feasible()`, which is the alarm.
FILTERS: tuple[tuple[str, object], ...] = (
    ("on_ceiling", lambda r: r["open_11f"] is None or r["open_11f"] > op.ON_CEILING),
    ("dead_scheme", lambda r: r["scheme"] in op.DEAD_SCHEMES),
    ("aug_11", lambda r: r.get("aug_11") is not None and r["aug_11"] <= op.AUG_FLOOR),
    ("lock", lambda r: r.get("lock") is not None and r["lock"] < op.LOCK_FLOOR),
    ("lock01", lambda r: r.get("lock01") is not None and r["lock01"] < op.LOCK01_FLOOR),
    ("offtarget_fires", lambda r: bool(r.get("offtarget_fires"))),
    (
        "hairpin_worst",
        lambda r: r.get("hairpin_worst") is not None and r["hairpin_worst"] < op.HAIRPIN_FLOOR,
    ),
    (
        "engages_stem_mfe",
        lambda r: (
            r.get("engages_stem_mfe") is not None and r["engages_stem_mfe"] <= op.STEM_MFE_FLOOR
        ),
    ),
    (
        "engaged_arm_11",
        lambda r: r.get("engaged_arm_11") is not None and r["engaged_arm_11"] < op.ARM_FLOOR,
    ),
    (
        "l_local",
        lambda r: r.get("l_local") is not None and r["l_local"] <= op.L_LOCAL_FLOOR,
    ),
    ("out_of_frame_aug", lambda r: bool(op.out_of_frame_augs(r.get("switch") or ""))),
    ("covers_drift", lambda r: bool(op.covers_drift(r))),
    (
        "lower3_keep",
        lambda r: bool(op.LOWER3_KEEP) and (r.get("lower3") or "") not in op.LOWER3_KEEP,
    ),
    (
        "closure_drop",
        lambda r: bool(op.CLOSURE_DROP) and (r.get("closure") or "") in op.CLOSURE_DROP,
    ),
    ("lower3_grip", lambda r: not op.lower3_ok(r)),
    # `.get` because `feasible` reads `codons` LAST, so only rows that passed everything else
    # reach it there; the marginal pass below applies every test to every row.
    ("rare_codon", lambda r: any(c in op.RARE_CODONS for c in (r.get("codons") or ()))),
)


def main() -> int:
    # `enriched`, not `load`: every join applied and `feasible` NOT applied. On bare rows a
    # column no join supplied reads as "nothing to filter on", which under-counts every rejection
    # -- measured at 17,666 survivors against the real 7,298.
    rows = op.enriched(NB / "results")
    print(f"  {len(rows):,} scored rows, every join applied")
    survivors = op.feasible(rows)
    print(f"  {len(survivors):,} survive feasible()")

    # The alarm: if this list has drifted from `feasible()`, the two counts disagree.
    mine = [r for r in rows if not any(test(r) for _name, test in FILTERS)]
    print(f"  {len(mine):,} survive the predicates copied here", end="")
    if len(mine) != len(survivors):
        print(f"  **MISMATCH of {abs(len(mine) - len(survivors)):,} -- FILTERS has drifted**")
    else:
        print("  (matches, so the attribution below is of the real funnel)")

    for axis in ("upper3", "lower3", "closure", "scheme", "geom"):
        levels = sorted({str(r.get(axis)) for r in rows if r.get(axis) is not None})
        print(f"\n{'=' * 104}\n{axis}")
        header = f"  {'level':17s}{'rows':>8s}{'kept':>7s}{'%':>7s}"
        names = [name for name, _ in FILTERS]
        print(header + "".join(f"{n[:11]:>12s}" for n in names))
        for level in levels:
            here = [r for r in rows if str(r.get(axis)) == level]
            if not here:
                continue
            kept = sum(1 for r in here if not any(t(r) for _n, t in FILTERS))
            first: dict[str, int] = {}
            for row in here:
                for name, test in FILTERS:
                    if test(row):
                        first[name] = first.get(name, 0) + 1
                        break
            cells = "".join(f"{(100.0 * first.get(n, 0) / len(here)):>11.1f}%" for n in names)
            print(
                f"  {level:17s}{len(here):>8,}{kept:>7,}{100.0 * kept / len(here):>6.1f}%" + cells
            )

        # Marginal: what each filter rejects that nothing else would. Order-free.
        print(f"  {'(marginal: only this filter rejects it)':17s}", end="")
        marg = []
        for name, test in FILTERS:
            others = [t for n, t in FILTERS if n != name]
            only = sum(1 for r in rows if test(r) and not any(t(r) for t in others))
            marg.append(only)
        print("".join(f"{v:>12,}" for v in marg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
