"""Which designs were built against a transcript base that has since been corrected.

    uv run python src/engine/gates/notebooks/toehold_and/transcript_drift.py [old.txt]

The mCherry reference was corrected at six positions. Every switch in the sweep has its
trigger-derived domains built from the transcript **as it was**, so a design whose trigger window
covers a corrected base now encodes a sequence that does not match the real transcript -- its
``r2*``, ``sw_x``, ``x*``, ``main_pre_star`` or ``k1_star`` is the reverse complement of a base
that is not there. Its folding energies, its A_M values and its barrier were all computed on that
mismatch.

This is not recoverable by rescoring: the switch sequence itself has to be rebuilt. So the job here
is to say exactly which designs and which pairs are affected, and to flag them rather than let a
mismatched design be ordered.

Without an argument it reads the previous committed version out of git.
"""

import argparse
import subprocess
import sys
from pathlib import Path

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parents[4] / "src"))
sys.path.insert(0, str(NB))

import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

#: The commit holding the transcript as the sweep saw it.
BEFORE = "7748668"


def previous(path: Path) -> str:
    """The transcript as of ``BEFORE``, read out of git rather than kept as a second file."""
    rel = path.relative_to(NB.parents[4]).as_posix()
    raw = subprocess.run(
        ["git", "show", f"{BEFORE}:{rel}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=NB.parents[4],
    ).stdout
    return (
        "".join(line.strip() for line in raw.splitlines() if not line.startswith(">"))
        .upper()
        .replace("T", "U")
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old", nargs="?", default="", help="an explicit old FASTA, else git")
    args = parser.parse_args(argv)

    current = read_fasta(NB / "mCherry_original.txt")
    before = read_fasta(Path(args.old)) if args.old else previous(NB / "mCherry_original.txt")
    if len(before) != len(current):
        print(f"  LENGTH CHANGED {len(before)} -> {len(current)}: every coordinate shifts, and")
        print("  nothing below is meaningful. Rebuild the sweep.")
        return 1

    drift = [(i, a, b) for i, (a, b) in enumerate(zip(before, current, strict=True)) if a != b]
    print(f"  {len(drift)} corrected position(s) in a {len(current)} nt transcript:")
    for index, was, now in drift:
        print(f"    pos {index:3d}  {was} -> {now}   codon {index // 3}, base {index % 3 + 1}")
    wobble = sum(1 for index, _w, _n in drift if index % 3 == 2)
    print(
        f"  {wobble} of {len(drift)} are at codon base 3, so the protein is "
        f"{'unchanged' if wobble == len(drift) else 'CHANGED -- check the translation'}."
    )
    hit = {index for index, _w, _n in drift}

    rows = op.load(NB / "results")
    print(f"\n  {len(rows):,} scored designs. Checking each one's two trigger windows.\n")

    def covers(start: int, end: int) -> list[int]:
        return sorted(p for p in hit if start <= p < end)

    affected = []
    pairs: dict[str, dict] = {}
    for row in rows:
        a_start, a_end = int(row["a_start"]), int(row["a_end"])
        b_start, b_end = int(row["b_start"]), int(row["b_end"])
        in_a, in_b = covers(a_start, a_end), covers(b_start, b_end)
        if not in_a and not in_b:
            continue
        affected.append(row)
        entry = pairs.setdefault(
            row["pair"], {"A": in_a, "B": in_b, "n": 0, "label": row["pair_label"]}
        )
        entry["n"] += 1
    print(
        f"  designs whose trigger window covers a corrected base: "
        f"{len(affected):,} of {len(rows):,} ({100.0 * len(affected) / len(rows):.1f}%)"
    )
    print(f"  trigger pairs affected: {len(pairs)} of {len({r['pair'] for r in rows})}\n")
    for _pair, entry in sorted(pairs.items(), key=lambda kv: -kv[1]["n"]):
        where = []
        if entry["A"]:
            where.append(f"trigger A at {entry['A']}")
        if entry["B"]:
            where.append(f"trigger B at {entry['B']}")
        print(f"    {entry['label']:20s} {entry['n']:6,d} designs   {'; '.join(where)}")

    # The panel is the part that would actually be ordered, so it gets named explicitly.
    panel = NB / "results" / "panel_three.csv"
    if panel.exists():
        import csv

        print("\n  THE CURRENT PANEL:")
        seen = set()
        for row in csv.DictReader(panel.open(encoding="utf-8")):
            key = row["pair"]
            if key in seen:
                continue
            seen.add(key)
            in_a = covers(int(row["a_start"]), int(row["a_end"]))
            in_b = covers(int(row["b_start"]), int(row["b_end"]))
            # A REPAIRED design's windows still cover the corrected base -- a patch corrects the
            # switch, not the coordinates -- so the flag is the only thing that distinguishes it.
            # Without this the report contradicted , which does
            # honour the flag, and called six regenerated designs MISMATCH.
            repaired = str(row.get("drift_repaired") or "").strip() in ("1", "True", "true")
            verdict = (
                "REPAIRED"
                if repaired and (in_a or in_b)
                else "CLEAN"
                if not in_a and not in_b
                else "MISMATCH"
            )
            detail = ""
            if in_a:
                detail += f"  trigger A covers {in_a}"
            if in_b:
                detail += f"  trigger B covers {in_b}"
            print(f"    {row['pair_label']:20s} {verdict}{detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
