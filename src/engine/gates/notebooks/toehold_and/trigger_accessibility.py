"""Stage 1b — accessibility scores for every trigger pair, in Green's and VISTA's terms.

    uv run python src/engine/gates/notebooks/toehold_and/trigger_accessibility.py \\
        --fasta "path/to/mCherry original.txt" --pairs 40 --out accessibility

**What this is.** Stage 1 finds pairs of windows sharing a reverse-complementary overlap of
at least ``MIN_OVERLAP`` (4 nt). That is pure geometry: it says the two windows *can* couple,
not that a switch could ever reach them. This scores how reachable each window actually is
inside its own transcript, using the descriptors the two published design tools use, so our
candidates can be judged on the same axes as work that has bench data behind it.

**Three corrections to the brief, all sourced, because two of them change what gets built.**

1. **SED and NED are Green 2026 (VISTA) terms, not Green 2014.** The string "SED" does not
   appear in Green 2014 at all. VISTA defines them (VISTA.pdf p.3-4): *"SED is the average
   number of incorrectly paired nucleotides at equilibrium relative to a specified predefined
   secondary structure, whereas NED is the average number of incorrectly paired nucleotides
   at equilibrium relative to the native MFE structure... Both SED and NED are normalized by
   the number of nucleotides and thus adopt values between 0 and 1."*
2. **VISTA does not use RNAplfold.** It never calls ``RNAplfold``, ``RNAup`` or ``RNAduplex``,
   and passes no ``-W``/``-L``/``-u`` anywhere. Its "±10/25/50/100 nt windows" are literal
   *slices* of the transcript — site plus L nt each side — folded **globally**. Both are
   What is computed here is therefore VISTA's own form — ``sed_wL``/``ned_wL``/``mfe_wL``,
   a literal slice folded globally — and **not** RNAplfold. True local folding does exist in
   this repo, as ``FoldProfiler`` in ``engine/stages/folding.py``, but it is a **stage-2**
   tool: the architecture's position is that a gate family is handed a trigger already
   judged accessible, and the house rules enforce that a file under ``gates/`` may not call
   it. Wiring RNAplfold into trigger selection is the proper stage-1b task and belongs in
   ``stages/triggers.py`` (`TriggerScorer.score`, still a stub). Flagged rather than
   smuggled in, because re-measuring accessibility a second way at a second layer is how
   two numbers for one quantity end up in one ranking.
3. **Because VISTA's specified structure for a target window is "completely unpaired", its
   SED collapses to the mean base-pairing probability over the window** — so it needs only a
   pair-probability matrix and no NUPACK at all. That identity is what makes this file
   possible on Windows, where NUPACK has no build.

**Green 2014's own score, for reference.** Document S1 §S14.3 Eq. 4 defines local
single-strandedness ``l = (Σ_i P_ii) / b`` — the mean *unpaired* probability over a window,
i.e. exactly ``1 - SED``. ``l_green`` reports it. Eq. 5 then *combines* the terms as
``φ = 5·l_mRNA + 4·l_toehold + 3·n_sensor``, and that combination is deliberately **not**
computed here: its two other terms are properties of a designed sensor rather than of a
transcript window, and the paper as written says the scores were "sorted from lowest to
highest" to pick the best, which cannot be right when high ``l`` is good and low ``n`` is
good. The raw terms are reported separately so nobody has to trust a combination whose
direction the source contradicts.

**Codon usage as a ribosome-occupancy proxy** follows VISTA p.9: *"the ribosome footprint
typically spans ~9-10 codons"*, so rare codons just downstream of a binding site park a
ribosome over it. Reported as the mean relative synonymous codon **fraction** (not CAI, not
tAI) over the n codons before and after the window, n = 4..10. Their strongest single
correlate was the following-8-codons mean (Pearson r = 0.30).

**Nothing here is thresholded, weighted or combined into a score that ranks.** These are raw
descriptors written to CSV. Per this project's standing instruction no weight is fitted to
data, and per its house rules an unmeasurable value is ``None`` and never ``0.0`` — which is
worth stating because VISTA's own shipped code returns ``0.0`` for an unknown codon and for
an empty window, and normalises features against whatever else happened to be in the batch.
"""

import argparse
import csv
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.domain import Host  # noqa: E402
from engine.gates.toehold import ProkaryoticToeholdAndGate  # noqa: E402
from engine.gates.tools.codons import CodonOptimizer  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402
from engine.gates.tools.translation import TranslationScorer  # noqa: E402

#: VISTA's flank sizes, in nucleotides on each side of the binding site.
VISTA_FLANKS = (0, 10, 25, 50, 100)
#: Codon counts for the ribosome-occupancy proxy.
FOOTPRINTS = (4, 5, 6, 7, 8, 9, 10)


def read_fasta(path: str) -> str:
    lines = Path(path).read_text().splitlines()
    return sq.to_rna("".join(line.strip() for line in lines if not line.startswith(">")))


def load_codon_fractions(path: str) -> dict[str, float]:
    """Relative synonymous codon fraction per codon, keyed on RNA codons.

    Raises rather than defaulting a missing codon to zero. VISTA's own code writes
    ``codon_usage_dict.get(codon, 0)``, which silently scores an unrecognised codon as the
    rarest possible one; this project's house rules forbid exactly that substitution.
    """
    table: dict[str, float] = {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            table[sq.to_rna(row["Codon"])] = float(row["Fraction"])
    if len(table) != 64:
        raise ValueError(f"{path} holds {len(table)} codons, expected 64")
    return table


def paired_profile(folder: FoldEngine, sequence: str) -> list[float]:
    """``P(paired)`` per position, from a global fold of exactly this sequence."""
    matrix = folder.base_pair_probabilities(sequence)
    return [min(1.0, sum(row)) for row in matrix]


def vista_window_features(folder: FoldEngine, transcript: str, start: int, end: int) -> dict:
    """VISTA's MFE / SED / NED at each flank size, by global folding of a literal slice."""
    out: dict[str, float | None] = {}
    for flank in VISTA_FLANKS:
        lo = max(0, start - flank)
        hi = min(len(transcript), end + flank)
        window = transcript[lo:hi]
        folded = folder.mfe(window)
        out[f"mfe_w{flank}"] = folded.energy
        # SED against the all-unpaired reference collapses to mean P(paired).
        profile = paired_profile(folder, window)
        out[f"sed_w{flank}"] = sum(profile) / len(profile)
        # NED: normalised ensemble defect against the window's own MFE structure.
        out[f"ned_w{flank}"] = folder.ensemble_defect(window, folded.structure) / len(window)
    return out


def subwindow_pairedness(profile: list[float], start: int, end: int) -> dict:
    """Mean ``P(paired)`` over VISTA's seven sub-windows of the binding site.

    The 5' sub-windows are the ones VISTA says *"are designed to initiate hairpin opening
    in the toehold switch"*; the 3' ones *"theoretically nucleate target-sensor binding"*.
    Read from the **whole transcript's** matrix, which is the context that matters.
    """
    out: dict[str, float | None] = {}
    for width in (3, 6, 18):
        head = profile[start : min(end, start + width)]
        tail = profile[max(start, end - width) : end]
        out[f"paired_5p{width}"] = sum(head) / len(head) if head else None
        out[f"paired_3p{width}"] = sum(tail) / len(tail) if tail else None
    whole = profile[start:end]
    out["paired_site"] = sum(whole) / len(whole) if whole else None
    return out


def codon_features(transcript: str, start: int, end: int, fractions: dict[str, float]) -> dict:
    """Codon usage in and around the window, as a ribosome-occupancy proxy.

    The transcript is assumed to be a CDS beginning in frame at index 0, which is true of
    the mCherry file this validation uses. The window is snapped back to the codon that
    contains its first base, the same convention VISTA's code uses.
    """
    codons = [transcript[i : i + 3] for i in range(0, len(transcript) - 2, 3)]
    values = [fractions[c] for c in codons if len(c) == 3 and c in fractions]
    first_codon = start // 3
    last_codon = min(len(values), (end + 2) // 3)

    out: dict[str, float | None] = {}
    inside = values[first_codon:last_codon]
    out["codon_first"] = values[first_codon] if first_codon < len(values) else None
    out["codon_second"] = values[first_codon + 1] if first_codon + 1 < len(values) else None
    out["codon_site_mean"] = sum(inside) / len(inside) if inside else None
    for n in FOOTPRINTS:
        before = values[max(0, first_codon - n) : first_codon]
        after = values[last_codon : last_codon + n]
        out[f"codon_before{n}"] = sum(before) / len(before) if before else None
        out[f"codon_after{n}"] = sum(after) / len(after) if after else None
    return out


def score_window(
    folder: FoldEngine,
    transcript: str,
    global_paired: list[float],
    start: int,
    end: int,
    fractions: dict[str, float],
) -> dict:
    row: dict[str, float | None] = {"start": start, "end": end, "length": end - start}
    row.update(vista_window_features(folder, transcript, start, end))
    row.update(subwindow_pairedness(global_paired, start, end))
    row.update(codon_features(transcript, start, end, fractions))
    # Green 2014 Eq. 4: local single-strandedness is 1 - mean pairedness.
    row["l_green"] = 1.0 - row["sed_w0"] if row["sed_w0"] is not None else None
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--pairs", type=int, default=40, help="pairs to score, 0 for all")
    parser.add_argument(
        "--codon-table",
        default="C:/Users/Dell/OneDrive - mail.tau.ac.il/IGEM/Toehold/Prokaryotic And Gate/"
        "vista/toehold-VISTA/ecoli_codon_usage_table.csv",
        help="CSV with Codon and Fraction columns; VISTA ships one for E. coli",
    )
    parser.add_argument("--out", default="accessibility", help="CSV prefix, into results/")
    args = parser.parse_args(argv)

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    folder = FoldEngine(37.0)
    gate = ProkaryoticToeholdAndGate(
        Host.ECOLI, folder, TranslationScorer(Host.ECOLI), CodonOptimizer(Host.ECOLI)
    )
    fractions = load_codon_fractions(args.codon_table)
    transcript = read_fasta(args.fasta)
    print(f"transcript {len(transcript)} nt · codon table {len(fractions)} codons")

    # One global fold of the whole transcript, reused for every window's sub-window features.
    global_paired = paired_profile(folder, transcript)
    mean_paired = sum(global_paired) / len(global_paired)
    print(f"global fold done; mean P(paired) over the transcript {mean_paired:.3f}")

    pairs = list(gate.find_trigger_pairs(transcript))
    print(f"{len(pairs)} pairs with a reverse-complementary overlap >= {gate.MIN_OVERLAP} nt")
    if args.pairs:
        pairs = pairs[: args.pairs]

    rows = []
    for index, pair in enumerate(pairs):
        for role, (start, end) in (("A", pair.window_a()), ("B", pair.window_b())):
            row = score_window(folder, transcript, global_paired, start, end, fractions)
            row.update(
                {
                    "pair_index": index,
                    "role": role,
                    "x_start": pair.x_start,
                    "xstar_start": pair.xstar_start,
                    "len_x": pair.len_x,
                }
            )
            rows.append(row)
        if index % 10 == 0:
            print(f"  scored {index + 1}/{len(pairs)} pairs", flush=True)

    path = output_dir / f"{args.out}.csv"
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} windows ({len(pairs)} pairs x 2) -> {path}")

    for name in ("sed_w0", "sed_w25", "sed_w100", "ned_w25", "codon_after8", "l_green"):
        values = [r[name] for r in rows if r.get(name) is not None]
        if values:
            ordered = sorted(values)
            print(
                f"  {name:<14} min {ordered[0]:7.3f}  median {ordered[len(ordered) // 2]:7.3f}"
                f"  max {ordered[-1]:7.3f}"
            )
    print(
        "\nLower SED means a more reachable window; higher l_green means the same thing\n"
        "from the other side (l_green = 1 - sed_w0). Compare designs within a column,\n"
        "never across: each flank size asks a different question about the same site.\n"
        "RNAplfold local accessibility is deliberately absent -- see the module docstring."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
