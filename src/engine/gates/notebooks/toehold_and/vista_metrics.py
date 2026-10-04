"""The VISTA-style metrics, computed on finished folds and joined back by design key.

    uv run python src/engine/gates/notebooks/toehold_and/vista_metrics.py --out p1 --shard 0/6

Green 2026 (VISTA) reports its strongest correlations against measured fluorescence for
quantities this sweep never computed. Its three best (Pearson r > 0.45, all in the OFF
state) are **single-state MFEs of the molecule and of two sub-regions** — how stable the
thing is as folded. Our ``dG_open`` is a different quantity: the cost of forcing one window
unpaired. Having the second does not give you the first.

One of the gaps is our own: ``SELECTION_SPEC.md`` §4.2 calls ``dG_RBS-Linker`` "the best
cheap predictor", rho +0.334 on Green's 168 measured switches — the highest of anything we
have tested — and it costs one MFE of ~57 nt. It was implemented in ``green_calibration.py``
and never wired into the sweep.

Nothing here folds a tube or re-derives a design. Every column is a function of the
``switch`` sequence already stored on each folded row, so this runs **after** a fold and
joins on the design key. It is ranking information, not selection: a run that picked its
leaders on ``mean_separation`` picked them before these existed, and whether these would
have chosen differently is a question to ask once both are on the table.

**Two honest limits.**

``sed_*`` is *not* VISTA's SED. True structural ensemble diversity is the mean base-pair
distance across the ensemble, which our ``FoldEngine`` does not expose; adding it would mean
a new ViennaRNA call in the one module allowed to make them, during a live run. What is
computed instead is the **ensemble defect against the region's own MFE structure**,
normalised by length: the expected fraction of nucleotides paired differently from the best
single structure. It answers the same question — how spread out is the ensemble — by a
different route, and the two are not interchangeable in a published comparison.

"The 6 nt at the base of the descending stem" is ambiguous in our layout: ``main_z``
[122,128) sits against the loop, while [134,140) is where the arm meets the linker. **Both
are computed**, named ``_loopside`` and ``_linkerside``, rather than choosing one quietly.
"""

import argparse
import csv
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from full_sweep import DESIGN_KEY_COLUMNS, read_fasta  # noqa: E402
from narrate import Progress, banner, conclude  # noqa: E402

from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

#: The sub-regions this module measures, each named by the DOMAINS that bound it rather
#: than by an index. The offsets themselves are read off a real assembly at startup -- a
#: table of numbers was correct only for the 161-nt default geometry and would have put
#: every column on the wrong nucleotides the moment the secondary arm changed length.
SPAN_BOUNDS = {
    # (start domain, which end, end domain, which end)
    "whole": None,  # the entire switch
    "rbs_linker": ("rbs_loop", 0, "linker", 1),  # as green_calibration defines it
    "rbs_stem": ("main_pre_star", 0, "main_pre", 1),  # the main hairpin, arms and loop
    "toehold_linker": ("cap", 1, "linker", 1),  # everything past the GGG cap
    "cds9": ("aug", 1, "main_pre", 1),  # the three codons after the start codon
    "codon3": ("main_pre", 1, "main_pre", 1),  # placeholder; resolved as the last 3 of cds9
}

#: The 6 nt at the base of the descending stem, in both readings -- `main_z` sits against
#: the loop and the end of `main_pre` meets the linker. Both are computed; see the module
#: docstring on why neither is chosen quietly.
BASE6 = {"loopside": ("main_z", 0, +6), "linkerside": ("main_pre", 1, -6)}


def _fraction(sequence: str, bases: str) -> float:
    return sum(1 for b in sequence if b in bases) / len(sequence) if sequence else 0.0


def _derive_spans(gate, transcript) -> tuple[dict[str, tuple[int, int]], int]:
    """Read every span off real assemblies, and refuse if they are not the same for all len_x.

    Rebuilding each design would cost 2.1 s of stem enumeration per pair, so the loop needs
    fixed offsets. They are *derived* here rather than listed: the domains after the
    secondary hairpin sit at constant indices only because that hairpin's four domains move
    against each other, and that stops being true the moment its arm length changes. A
    listed table would still have returned plausible energies from the wrong nucleotides.
    """
    kept = []
    for pair in gate.find_trigger_pairs(transcript):
        start, end = pair.window_a()
        if gate.screen_trigger_window(transcript[start:end], transcript[pair.x_start - 9 :][:9]):
            continue
        kept.append(pair)

    spans: dict[str, tuple[int, int]] = {}
    switch_len = None
    seen: set[int] = set()
    for pair in kept:
        if pair.len_x in seen:
            continue
        trigger_a = transcript[slice(*pair.window_a())]
        trigger_b = transcript[slice(*pair.window_b())]
        stems = [
            s
            for s in gate.secondary_stems(trigger_a, trigger_b, pair.len_x)
            if s.lock_energy <= 0.0
        ]
        if not stems:
            continue
        seen.add(pair.len_x)
        stem = sorted(stems, key=lambda s: s.lock_energy)[0]
        switch = gate.assemble(trigger_a, trigger_b, pair.len_x, stem)
        d, n = switch.domains, len(switch.sequence)
        here = {"whole": (0, n)}
        for name, bound in SPAN_BOUNDS.items():
            if bound is None:
                continue
            a_dom, a_end, b_dom, b_end = bound
            here[name] = (d[a_dom][a_end], d[b_dom][b_end])
        for side, (dom, which, delta) in BASE6.items():
            anchor = d[dom][which]
            here[f"base6_{side}"] = (
                (anchor, anchor + delta)
                if delta > 0
                else (
                    anchor + delta,
                    anchor,
                )
            )
        if switch_len is None:
            spans, switch_len = here, n
        elif here != spans or n != switch_len:
            raise SystemExit(
                f"len_x {pair.len_x} lays out differently ({n} nt, {here}) from the first "
                f"({switch_len} nt, {spans}). These offsets are only usable because the "
                f"layout is constant across len_x; it is not, so nothing here is safe."
            )
    if switch_len is None:
        raise SystemExit("no assemblable trigger pair -- cannot derive the spans")
    print(f"  spans derived from real assemblies, len_x {sorted(seen)}, switch {switch_len} nt")
    for name in ("rbs_linker", "rbs_stem", "base6_loopside", "base6_linkerside"):
        print(f"    {name:<18} {spans[name]}")
    return spans, switch_len


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--out", default="p1", help="the folded prefix to read")
    parser.add_argument("--shard", default="", metavar="i/n")
    args = parser.parse_args(argv)

    sources = sorted(RESULTS.glob(f"{args.out}_folded*.csv"))
    if not sources:
        sys.exit(f"no {args.out}_folded*.csv -- fold something first")

    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, FoldEngine(37.0), TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    SPANS, SWITCH_LEN = _derive_spans(gate, read_fasta(args.fasta))

    csv.field_size_limit(10**7)
    shard, shards, suffix = 0, 1, ""
    if args.shard:
        index_text, _, count_text = args.shard.partition("/")
        shard, shards = int(index_text), int(count_text or 1)
        if not 0 <= shard < shards:
            sys.exit(f"--shard {args.shard} is not of the form i/n with 0 <= i < n")
        suffix = f"_{shard}"

    # Counted by streaming, not by loading. A folded phase is 91,908 rows carrying a 161-nt
    # switch each; holding them all is ~200 MB per process, and several processes alongside
    # a live fold is how the machine runs out of memory. The count is only for the bar.
    total = 0
    for source in sources:
        with source.open(newline="") as handle:
            total += max(0, sum(1 for _ in handle) - 1)
    mine = len(range(shard, total, shards))

    banner(
        "VISTA-STYLE METRICS, joined onto finished folds",
        [
            f"{total:,} designs across {len(sources)} folded file(s); this shard takes {mine:,}",
            "3 MFEs and 1 partition function per design; no tube is folded",
            "dG_rbs_linker is SELECTION_SPEC 4.2's best cheap predictor, rho +0.334,",
            "and had never been wired into the sweep",
        ],
        estimate=mine * 0.14,
    )
    bar = Progress(mine, "designs")

    path = RESULTS / f"{args.out}_vista{suffix}.csv"
    # Only the three energy columns are kept, as plain floats, for the closing summary.
    # Everything else goes straight to the file.
    seen: dict[str, list[float]] = {"dG_switch_off": [], "dG_rbs_linker": [], "dG_rbs_stem": []}
    written = index = 0
    batch: list[dict] = []
    fieldnames: list[str] = []
    with path.open("w", newline="") as out:
        writer = None
        for source in sources:
            with source.open(newline="") as handle:
                for row in csv.DictReader(handle):
                    take = index % shards == shard
                    index += 1
                    if not take:
                        continue
                    switch = row["switch"]
                    extra = {name: row[name] for name in DESIGN_KEY_COLUMNS}
                    if len(switch) != SWITCH_LEN:
                        # Never zero for an unmeasurable design: 0.0 kcal/mol reads as a
                        # perfectly unstructured region and would top every ranking that
                        # maximises these.
                        for key in (
                            "dG_switch_off",
                            "dG_rbs_linker",
                            "dG_rbs_stem",
                            "sed_toehold_linker",
                        ):
                            extra[key] = None
                        for side in ("loopside", "linkerside"):
                            for key in ("gc6", "gcau_balance6", "a_content6"):
                                extra[f"{key}_{side}"] = None
                    else:
                        for key, span in (
                            ("dG_switch_off", "whole"),
                            ("dG_rbs_linker", "rbs_linker"),
                            ("dG_rbs_stem", "rbs_stem"),
                        ):
                            value = gate.folder.mfe(switch[slice(*SPANS[span])]).energy
                            extra[key] = value
                            seen[key].append(value)
                        region = switch[slice(*SPANS["toehold_linker"])]
                        # Defect against the region's own MFE -- see the module docstring on
                        # why this is not VISTA's SED and must not be reported as though.
                        extra["sed_toehold_linker"] = gate.folder.ensemble_defect(
                            region, gate.folder.mfe(region).structure
                        ) / len(region)
                        for side in ("loopside", "linkerside"):
                            six = switch[slice(*SPANS[f"base6_{side}"])]
                            gc = _fraction(six, "GC")
                            extra[f"gc6_{side}"] = gc
                            extra[f"gcau_balance6_{side}"] = abs(gc - 0.5)
                            extra[f"a_content6_{side}"] = _fraction(six, "A")
                    if writer is None:
                        fieldnames = list(extra)
                        writer = csv.DictWriter(out, fieldnames=fieldnames)
                        writer.writeheader()
                    batch.append(extra)
                    written += 1
                    if len(batch) >= 200:
                        writer.writerows(batch)
                        out.flush()
                        batch.clear()
                    bar.step(f"dG_off {extra['dG_switch_off']}")
        if writer is not None and batch:
            writer.writerows(batch)
    bar.finish()

    findings = [
        f"{written:,} designs measured, {len(seen['dG_switch_off']):,} with a usable switch."
    ]
    if seen["dG_switch_off"]:
        for key, label in (
            ("dG_switch_off", "whole switch MFE"),
            ("dG_rbs_linker", "RBS-linker MFE"),
            ("dG_rbs_stem", "main hairpin MFE"),
        ):
            values = sorted(seen[key])
            findings.append(
                f"{label} spans {values[0]:.2f} to {values[-1]:.2f} kcal/mol, median "
                f"{values[len(values) // 2]:.2f}."
            )
        findings += [
            "DIRECTION IS CONTESTED, and it is not a sign convention -- an MFE is a "
            "single-state energy, so there is no subtraction whose order could flip. "
            "Re-measured on Green's 168 switches with their own RBS locator: dG_RBS-Linker "
            "rho +0.293 and whole-switch MFE rho +0.277 against measured ON/OFF, both "
            "positive, so on that data LESS structure gives a better ratio and these are "
            "MAXIMISED. VISTA reports the opposite for fold change on its 189 designs. The "
            "architectures differ -- our A0 shares Green's first-generation rule of full "
            "invasion, while VISTA invades 6 nt into a frozen cassette -- which makes "
            "Green's direction the better prior here, but it is a prior and not a result.",
            f"Join on {', '.join(DESIGN_KEY_COLUMNS[:3])}... plus stem_index and the four "
            f"axis columns -- the same design key the folded rows carry.",
        ]
    conclude(findings, wrote=[str(path)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
