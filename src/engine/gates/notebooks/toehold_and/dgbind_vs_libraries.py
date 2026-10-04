"""Is ``dG_bind`` -- how hard the trigger grips the switch -- predictive on measured switches?

    uv run python src/engine/gates/notebooks/toehold_and/dgbind_vs_libraries.py

**Why this is the one term from the proposal worth testing.** The proposed objective's two largest
terms are OFF-state energies, and both are measured wrong-signed on Green's data: ``dG_OFF`` at
-0.284 and ``dG_open_off`` at -0.362. ``dG_bind(A|B)`` is the one term that is neither measured nor
measurable here, because every library we hold is **single-input** and there is no second trigger
to condition on.

But its single-input analogue IS defined there, and that is the proxy Offer proposed: the binding
energy of the one trigger to the one switch,

    dG_bind = e(switch & trigger) - e(switch) - e(trigger)

computed through the same ``FoldEngine`` as everything else. If that is flat on Green's measured
ON/OFF, then the binding half of the proposal has no support either and only the ON-state opening
terms survive. If it is positive, ``dG_bind(A|B)`` becomes a real candidate for a fourth arm.

**Signed so positive means the metric points the right way.** Binding is favourable when ``dG`` is
negative, so a *more negative* dG_bind should go with a *better* measured ratio -- which is a
NEGATIVE Spearman against ON/OFF, reported here as ``-rho`` like every other cost in this repo.

Reported beside it, over the same switches and the same folds: ``dG_open_on`` as the known-good
reference (+0.315 on the 168) and ``dG_OFF`` as the known-bad one (-0.284), so a reader can see
the new number against two whose sign is already established rather than in isolation.
"""

from __future__ import annotations

import csv
import statistics as st
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import green_calibration as gc  # noqa: E402
from augz_vs_libraries import LIBRARIES, noise_for  # noqa: E402
from metric_correlations import spearman  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402


def dg_bind(folder: FoldEngine, switch: str, trigger: str) -> float | None:
    """``e(switch&trigger) - e(switch) - e(trigger)``, the grip of one trigger on one switch.

    The three MFEs come from one cached engine, so the two single-strand terms are folded once per
    sequence however many times they appear. ``None`` if any fold fails -- never 0.0, which would
    read as "binds not at all" rather than as "not measured".
    """
    parts = [folder.mfe(s) for s in (f"{switch}&{trigger}", switch, trigger)]
    if any(p is None for p in parts):
        return None
    together, alone_s, alone_t = (p.energy for p in parts)
    return together - alone_s - alone_t


def main(argv=None) -> int:
    results = NB / "results"
    folder = FoldEngine(37.0)
    everything: list[dict] = []

    for label, table, source, kind in LIBRARIES:
        path = results / table
        if not path.exists():
            print(f"  no {table}, skipping {label}")
            continue
        measured = {}
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    measured[str(row["switch_number"])] = float(row["on_off"])
                except (KeyError, TypeError, ValueError):
                    continue
        try:
            records = gc.load_switches(source) if kind == "xlsx" else gc.load_vista_csv(source)
        except Exception as error:
            print(f"  {label}: could not load sequences ({type(error).__name__}: {error})")
            continue
        sequences = {str(r.get("switch_number")): (r["switch"], r["trigger"]) for r in records}

        rows = []
        for number, on_off in sorted(measured.items()):
            pair = sequences.get(number)
            if not pair or on_off <= 0:
                continue
            switch, trigger = pair
            value = dg_bind(folder, switch, trigger)
            if value is None:
                continue
            rows.append(
                {
                    "library": label,
                    "switch_number": number,
                    "on_off": on_off,
                    "dG_bind": round(value, 3),
                    "nt_trigger": len(trigger),
                }
            )
        if not rows:
            print(f"  {label}: nothing scored")
            continue
        everything.extend(rows)
        noise = noise_for(len(rows))
        on_off = [r["on_off"] for r in rows]
        values = [r["dG_bind"] for r in rows]
        rho = spearman(values, on_off)
        # A cost: more negative is better, so the signed correlation is the negation.
        signed = None if rho is None else -rho
        flag = "  (inside the sampling noise)" if signed is not None and abs(signed) < noise else ""
        print(f"\n  {label}: {len(rows)} switches, sampling noise ~{noise:.2f}")
        print(
            f"    dG_bind  min {min(values):8.1f}  median {st.median(values):8.1f}  "
            f"mean {st.fmean(values):8.1f}  sd {st.pstdev(values):6.1f}  max {max(values):8.1f}"
        )
        print(f"    signed rho against measured ON/OFF: {signed:+.4f}{flag}")
        # Trigger length is the obvious confound: a longer trigger binds harder for no biological
        # merit, which is exactly the point the proposal's own section 2 makes about normalising.
        lengths = sorted({r["nt_trigger"] for r in rows})
        if len(lengths) > 1:
            by_len = spearman([r["nt_trigger"] for r in rows], values)
            print(f"    trigger lengths {lengths}, rho(length, dG_bind) = {by_len:+.3f}")
        else:
            print(f"    every trigger is {lengths[0]} nt, so length is not a confound here")

    if not everything:
        return 1
    out = results / "dgbind_libraries.csv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(everything[0]))
        writer.writeheader()
        writer.writerows(everything)
    print(f"\n  wrote {len(everything):,} rows to {out.name}")

    print(f"\n{'=' * 74}\n  does dG_bind hold its sign across the libraries?\n{'=' * 74}\n")
    labels = [label for label, *_ in LIBRARIES if any(r["library"] == label for r in everything)]
    cells, got = "", []
    for label in labels:
        pool = [r for r in everything if r["library"] == label]
        rho = spearman([r["dG_bind"] for r in pool], [r["on_off"] for r in pool])
        value = None if rho is None else -rho
        got.append(value)
        cells += f"{value:>+10.3f}" if value is not None else f"{'n/a':>10s}"
    real = [v for v in got if v is not None]
    verdict = (
        "positive everywhere"
        if real and all(v > 0 for v in real)
        else "negative everywhere"
        if real and all(v < 0 for v in real)
        else "FLIPS SIGN"
    )
    print(f"    {'dG_bind':16s}" + "".join(f"{label:>10s}" for label in labels) + "   verdict")
    print(f"    {'':16s}{cells}   {verdict}")
    print("\n  for reference, measured the same way: dG_open_on +0.315 / +0.478 / -0.074,")
    print("  dG_OFF -0.284 / -0.253 / n/a, ied_gain +0.345 / +0.495 / +0.116.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
