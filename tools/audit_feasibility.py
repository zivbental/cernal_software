"""Order in the feasibility set: every metric, its measurement type, its role, and a real value.

    uv run python tools/audit_feasibility.py

The set of things measured per design has grown by accretion across four layers, and nobody can
currently say for a given metric whether it FILTERS, RANKS, is a THRESHOLD, or is only reported --
nor whether two of them are the same quantity under different names. This prints that, keyed to the
five requirements the gate actually has, with the worked example's numbers beside each row so a
duplicate is visible as two equal numbers rather than as an argument.

The five requirements, in the order the mechanism runs:

  A. state 00  trigger B's toehold reachable, BOTH hairpins shut
  B. state 01  A's effective toehold reachable (B did that), main hairpin still shut
  C. state 10  main hairpin still shut -- the dangerous leak
  D. state 11  the initiation window reachable by the ribosome, RBS through AUG
  E. gene      both trigger windows accessible in their transcript, no off-target FIRES

Three ways exist to ask "open or shut", and they are not interchangeable:

  mean unpaired    mean of per-base unpaired probabilities. Robust, but partner-blind: it cannot
                   tell "open" from "bound to the right thing".
  mean paired-to   mean probability of pairing to a NAMED partner. The only form that can express
                   "x* is held by its own arm" versus "x* is taken by trigger A".
  joint            probability the whole window is open at once. Underflows past ~18 nt (1e-22),
                   so it is unusable on a 36 or 50 nt footprint and is not offered there.
  energy           kcal/mol to force the window open. Never underflows, and energies add, which is
                   why the opening terms are energies and the accessibility terms are probabilities.

The example is ggt x fadB, len_x 13, open_3x3, naive geometry, 161 nt -- the design where
`A_S_11 = 0.003` fails tau6 while `xstar_engA_11 = 0.997` shows it doing exactly the right thing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "src/engine/gates/notebooks/toehold_and"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(NB))

# ruff: noqa: E402 - the engine and notebook imports must follow the sys.path inserts.
from engine import sequences as sq
from engine.domain import Constraints, Host, TriggerCandidate, TriggerSet
from engine.gates.toehold import ProkaryoticToeholdAndGate
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer
from engine.transcriptome import load_transcriptome

#: requirement -> rows of (metric, measurement type, role, note)
#:
#: ROLE is the thing nobody could state before this file existed:
#:   FILTER     rejects a design inside `objective_panel.feasible`
#:   THRESHOLD  listed in `THRESHOLDS` (tau1..tau11). Declared, and `gate_violations` reports
#:              it, but `feasible` does NOT read most of them
#:   RANK       one of `ARMS`, so it orders designs
#:   REPORT     computed and carried, nothing reads it
MAP: tuple[tuple[str, tuple[tuple[str, str, str, str], ...]], ...] = (
    (
        "A. state 00 -- B's toehold reachable, both hairpins shut",
        (
            (
                "A_r2_star_00",
                "mean unpaired",
                "THRESHOLD tau8",
                "B's toehold available to begin with",
            ),
            (
                "xstar_locked_00",
                "mean paired-to",
                "REPORT (new)",
                "x* held by its OWN arm -- the only form that says so",
            ),
            ("A_S_00", "mean unpaired", "THRESHOLD tau1", "secondary shut; partner-blind"),
            ("A_M_00", "mean unpaired", "THRESHOLD tau2", "main shut; spans main_z-aug-main_pre"),
            ("aug_00", "mean unpaired", "REPORT (new)", "the AUG alone, separated from the arms"),
            (
                "open_00",
                "energy",
                "REPORT",
                "cost to open the main stem's two arms, bulge excluded",
            ),
            (
                "d_off",
                "ensemble defect",
                "THRESHOLD tau9 + FILTER",
                "the OFF state is the structure we drew",
            ),
            ("hairpin_worst", "energy", "FILTER", "worst hairpin -- see the note at the end"),
        ),
    ),
    (
        "B. state 01 -- A's effective toehold reachable, main hairpin shut",
        (
            ("A_S_01", "mean unpaired", "THRESHOLD tau5", "B freed x*; this is `free_xstar_01`"),
            (
                "xstar_locked_01",
                "mean paired-to",
                "REPORT (new)",
                "and it is no longer held by its own arm",
            ),
            (
                "A_S_full_01",
                "mean unpaired",
                "REPORT",
                "the whole descending arm -- how far B unzipped, NOT A's toehold",
            ),
            ("A_M_01", "mean unpaired", "THRESHOLD tau4b", "main still shut -- the harder test"),
            ("open_01", "energy", "REPORT", ""),
            ("dG_bind_B", "energy", "REPORT", "why it happened: B's own binding"),
        ),
    ),
    (
        "C. state 10 -- the main hairpin must stay shut. The dangerous leak",
        (
            (
                "A_M_10",
                "mean unpaired",
                "THRESHOLD tau4a",
                "leakiest OFF state in 400 of 400 designs",
            ),
            (
                "A_S_10",
                "mean unpaired",
                "THRESHOLD tau3",
                "A alone must not open the secondary -- PARTNER-BLIND, see below",
            ),
            (
                "xstar_engA_10",
                "mean paired-to",
                "REPORT (new)",
                "A alone taking x*: the leak tau3 cannot see",
            ),
            ("open_10", "energy", "REPORT", ""),
            (
                "engages_stem_mfe",
                "MFE contact share",
                "FILTER",
                "A on the ascending arm in the single most likely structure",
            ),
        ),
    ),
    (
        "D. state 11 -- the initiation window reachable, RBS through AUG",
        (
            (
                "A_M_11",
                "mean unpaired",
                "THRESHOLD tau7",
                "A opened the main hairpin, but only with B",
            ),
            (
                "xstar_engA_11",
                "mean paired-to",
                "REPORT (new)",
                "x* taken BY A -- what tau6 meant to ask",
            ),
            ("aug_11", "mean unpaired", "REPORT (new)", "the start codon itself"),
            (
                "dG_open_11",
                "energy",
                "RANK (opening SEP via f1)",
                "over span(-17,13), the ribosome footprint",
            ),
            (
                "open_11",
                "energy",
                "FILTER (ON ceiling 4.0)",
                "the only externally calibrated number we have",
            ),
            ("ied_rbs_linker_11", "energy", "RANK (IED gain)", "RBS-to-linker interference"),
            ("dG_bind_A_given_B", "energy", "REPORT", "why it happened: A conditioned on B"),
        ),
    ),
    (
        "E. gene level -- windows accessible in the transcript, no off-target",
        (
            (
                "l_local",
                "mean unpaired (RNAplfold)",
                "FILTER",
                "CERNAL's measure: sliding local window, capped span",
            ),
            (
                "l_green",
                "mean unpaired (isolated slice)",
                "REPORT",
                "Green 2014's form; disagrees with l_local on 272 of 941 windows",
            ),
            (
                "l_full_w25",
                "mean unpaired (whole transcript)",
                "REPORT",
                "a third form, retired as the filter",
            ),
            (
                "access / access_a / access_b",
                "energy",
                "REPORT",
                "open_penalty summed; CONSTANT within a cell, so it never reorders a design",
            ),
            (
                "offtarget_fires",
                "categorical",
                "FILTER",
                "a gate that opens on a decoy is wrong whatever it scores",
            ),
        ),
    ),
)

#: Quantities that are the same measurement reached twice, or that look like a pair and are not.
DUPLICATES: tuple[tuple[str, str], ...] = (
    (
        "A_S_01 and free_xstar_01",
        "the same number. `free_xstar` is the notebook's name for `A_S` in state 01.",
    ),
    (
        "open_11 and dG_open_11",
        "DIFFERENT regions, similar names: `open_*` is the main stem's two arms with the bulge "
        "excluded, `dG_open_*` is span(-17,13), the ribosome footprint. The ON ceiling and the "
        "separation arm ride on different ones.",
    ),
    (
        "A_M_* and open_*",
        "both 'the main stem', different spans AND different measurement types: `A_M` is one "
        "contiguous probability over main_z-aug-main_pre, `open_*` is an energy over two spans "
        "with the AUG left out.",
    ),
    (
        "f1_opening_sep and ied_gain",
        "within-cell Spearman +0.919 over 249 cells. Close to one arm, not two.",
    ),
    (
        "a_site_energy and lock_energy",
        "NOT a pair: `a_site` is A's binding to secondary_z + x*, `lock` is k2_star against "
        "secondary_z plus the cap. Different regions; the difference is not a margin.",
    ),
    (
        "l_local, l_green, l_full_w25",
        "three forms of one question. Only `l_local` filters; the other two are carried so a "
        "reader can see they disagree.",
    ),
)


def main() -> int:
    folder = FoldEngine()
    gate = ProkaryoticToeholdAndGate(
        host=Host.ECOLI,
        folder=folder,
        translation=TranslationScorer(Host.ECOLI),
        codons=CodonOptimizer(Host.ECOLI),
    )
    book = load_transcriptome(Host.ECOLI)
    ta, tb = sq.to_rna(book["b3447"]), sq.to_rna(book["b3846"])
    src = {"ggt": ta, "fadB": tb}
    pairs = list(gate.find_cross_gene_pairs("ggt", ta, "fadB", tb))
    pair = sorted(pairs, key=lambda q: (-q.len_x, q.x_start))[0]
    a0, _ = pair.window_a()
    _, b1 = pair.window_b()
    fa, fb = gate.role_footprints()
    wa = src[pair.gene_a][a0 : a0 + fa]
    wb = src[pair.gene_b][b1 - fb : b1]

    def cand(name: str, gene: str, seq: str, start: int) -> TriggerCandidate:
        return TriggerCandidate(
            trigger_id=name,
            gene_id=gene,
            symbol=gene,
            sequence=seq,
            start_index=start,
            openness=0.4,
            accessibility=0.4,
            mfe=0.0,
            off_target_penalty=0.0,
            segment_specificity=0.0,
            gc_content=sq.gc_content(seq),
        )

    trigger_set = TriggerSet(
        activators=(cand("A", pair.gene_a, wa, a0), cand("B", pair.gene_b, wb, b1 - fb))
    )
    design = next(
        iter(gate.generate_designs(trigger_set, Constraints(stems_per_pair=1, stem_order="front")))
    )
    measured = gate.measure_design(design, on_ceiling=None)

    print(
        f"  worked example: {pair.gene_a} x {pair.gene_b}, len_x {pair.len_x}, "
        f"{design.architecture.get('closure')}, {len(design.sequence)} nt, {gate.geometry_name}"
    )
    print(f"  {len(measured)} measurements returned by one `measure_design` pass\n")

    for heading, rows in MAP:
        print(f"{'=' * 118}\n{heading}")
        print(f"  {'metric':24s}{'value':>10s}  {'measurement type':26s}{'role':28s}note")
        for name, kind, role, note in rows:
            value = measured.get(name)
            shown = f"{value:.4f}" if isinstance(value, (int, float)) else "--"
            print(f"  {name:24s}{shown:>10s}  {kind:26s}{role:28s}{note}")

    print(f"\n{'=' * 118}\nDUPLICATES AND NEAR-MISSES")
    for pairname, why in DUPLICATES:
        print(f"  {pairname}")
        print(f"      {why}")

    print(f"\n{'=' * 118}\nWHAT THE EXAMPLE SETTLES")
    a_s_11 = measured.get("A_S_11")
    eng_11 = measured.get("xstar_engA_11")
    a_s_10 = measured.get("A_S_10")
    eng_10 = measured.get("xstar_engA_10")
    print(f"  tau6 asks  A_S_11 > 0.5   and gets {a_s_11:.4f}  -> REJECTS this design")
    print(f"  the mechanism asks x* be taken by A, and xstar_engA_11 = {eng_11:.4f}")
    print(f"  tau3 asks  A_S_10 < 0.2   and gets {a_s_10:.4f}  -> PASSES")
    print(f"  while trigger A alone already holds xstar_engA_10 = {eng_10:.4f} of the site")
    print("\n  So both gates on the secondary hairpin are partner-blind in the direction that")
    print("  matters, and the replacement is the paired-to form, with thresholds set from a")
    print("  measured distribution rather than carried over from the unpaired ones.")

    print(f"\n{'=' * 118}\nNOTES THAT DO NOT FIT A ROW")
    print("  hairpin_worst: I claimed it conflates states. WRONG -- `hairpin_fidelity(folder,")
    print("  switch, len_x)` takes the switch ALONE, so it is a state-00 measure applied as a")
    print("  state-00 requirement, and there is no per-state conflict. It is also already")
    print("  decomposed: hairpin_main_pre, hairpin_k1, hairpin_lock, hairpin_sec are all carried")
    print("  and `worst` is their min. The four intended duplexes are main_pre*<->main_pre (9 bp),")
    print("  k1*<->main_z (6 bp), sw_x<->x* (len_x), k2*<->sec_z (k2).")
    print()
    print("  aug_00: I called 0.6765 a leak the thresholds miss. WRONG -- `intended_duplexes`")
    print('  excludes the AUG bulge on purpose: "It is deliberately not a stem -- the AUG sits')
    print('  open in the OFF state -- and the closure axis varies it on purpose." So aug_00 is the')
    print("  intended design, and the AUG is only informative in state 11.")
    print("  mean vs joint vs energy was chosen by what reads intuitively, not by evidence that")
    print("  one discriminates better. Joint is unusable past ~18 nt (1e-22 on a 36-nt window), so")
    print("  the real choice is mean-unpaired against energy, and it is untested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
