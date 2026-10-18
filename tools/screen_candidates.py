"""Screen a candidate panel's switches for motifs that make a construct not worth ordering.

    uv run python tools/screen_candidates.py <results>/panel_k1_x508_xs283.csv

Reads the per-background CSV that ``candidates.py`` writes and runs the engine's own
``MotifScreener`` over every ``switch`` in it, against **both** iGEM assembly standards at
once -- RFC10 as the site set, RFC1000 as extra motifs -- so the standard can be chosen
after seeing what each would cost rather than before. The homopolymer cap is the design
guide's 4, not the engine default of 5.

**Why this is not inside the notebook.** ``MotifScreener`` lives in ``engine/stages/`` and
``engine/gates/notebooks/`` may not import upward; ``tests/engine/test_house_rules.py``
enforces that with an AST scan. Reimplementing the screener in the notebook to dodge the
rule is the merge defect the rule exists to prevent -- two screeners, two answers, one
report. This file sits outside ``src/engine/`` where importing the real one is legal.

A hard filter, never a score: a switch carrying a forbidden site is not a worse candidate,
it is not a candidate.

Not screened here, and named as gaps rather than quietly skipped:

* **RNase E** -- no reliable consensus motif exists. Structure and AU-richness are the
  honest proxies and both are already computed by the panel.
Now screened, since ``MotifScreener`` gained regex motifs and a reading frame:

* **In-frame stop codons**, from the AUG through the end of the linker. The frame is derived
  the documented way (``aug = len(switch) - 75 + 42``) rather than by finding the first AUG,
  which in several switches is upstream of the real start.
* **G-quadruplex** (``G>=3 N1-7`` x4). Previously impossible because motifs were literal.
* **CsrA and Hfq motifs**, the two E. coli RBPs with usable consensus sequences.
* **U runs of 4**, tighter than the other bases, because a U tract is the Rho-independent
  terminator signal. Note this is right for a switch and WRONG for an assembled plasmid,
  whose terminator legitimately is one -- hence opt-in, and opted into here.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine import sequences as sq
from engine.stages.motifs import RFC1000_SITES, MotifScreener


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv_path", help="a per-background CSV written by candidates.py")
    parser.add_argument("--picks-only", action="store_true", help="only rows the panel chose")
    args = parser.parse_args(argv)

    path = Path(args.csv_path)
    if not path.exists():
        print(f"no such file: {path}")
        return 1

    screener = MotifScreener(
        extra_motifs=RFC1000_SITES,
        max_homopolymer=4,
        rbp_motifs=True,
        quadruplex=True,
        per_base_homopolymer=True,
    )
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if args.picks_only:
        rows = [r for r in rows if r.get("panel_role")]

    print(f"  {len(rows):,} switches from {path.name}")
    print("  RFC10 (EcoRI/XbaI/SpeI/PstI/NotI) + RFC1000 (BsaI/SapI), homopolymer cap 4\n")

    clean, flagged = 0, []
    for row in rows:
        switch = row.get("switch", "")
        if not switch:
            continue
        # The screener works in DNA: a U left in the string matches nothing and every
        # sequence comes back falsely clean, which is the quiet failure to avoid here.
        # The AUG is a fixed offset in this architecture, so the reading frame is derived
        # rather than searched: the first AUG in the string is upstream of the real start in
        # several switches, and scanning from it would report stops that are not in frame.
        aug = len(switch) - 75 + 42
        frame = aug if switch[aug : aug + 3].upper() in ("AUG", "ATG") else None
        found = screener.violations(sq.to_dna(switch), reading_frame=frame)
        if not found:
            clean += 1
            continue
        label = row.get("panel_role") or f"{row.get('closure', '?')}/{row.get('stem_index', '?')}"
        flagged.append((label, ", ".join(f"{v.name}@{v.start}" for v in found)))

    print(f"  clean: {clean:,} of {len(rows):,}")
    if flagged:
        print(f"  flagged: {len(flagged):,}\n")
        width = max(len(name) for name, _ in flagged)
        for name, hits in flagged[:40]:
            print(f"    {name:<{width}}  {hits}")
        if len(flagged) > 40:
            print(f"    ... and {len(flagged) - 40:,} more")
    else:
        print("  nothing flagged -- no forbidden site, no in-frame stop, no quadruplex,")
        print("  no CsrA/Hfq motif, and no homopolymer run of 4 or more.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
