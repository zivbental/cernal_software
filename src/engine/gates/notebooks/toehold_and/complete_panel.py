"""The three measurements the panel is still missing, in one resumable pass.

    uv run python src/engine/gates/notebooks/toehold_and/complete_panel.py

Writes ``results/completions.csv``, one row per switch, which ``objective_panel.load`` joins when
it exists. Streams and resumes: killed halfway, rerun and it continues.

**1. Off-target, joined at last.** ``offtarget_folded.csv`` already holds a verdict for **all
1,239 trigger pairs** -- the cheap sequence screen covered every pair, 840 carried no mimic worth
folding, and the 399 that did were folded four strands at a time:

    FIRES    23   a decoy fires the gate with no real trigger  -> DISQUALIFIED
    BLOCKS  104   a decoy occupies a nucleation site           -> flagged, ranked below
    inert   272   binds, but moves A_M by nothing
    (none)  840   no mimic long enough to be worth folding

``FIRES`` is a categorical failure: a gate that opens on the wrong transcript is wrong whatever
else it scores, and no ordering of a continuous score expresses "disqualified". ``BLOCKS`` is
graded -- it costs ON signal rather than inventing one -- so it is carried as a flag.

**2. Accessibility that both geometries share.** ``access`` was keyed on the exact window, so the
naive build's 36/50-nt windows and the Kim build's 35/49-nt ones looked like different windows and
only 352 of 747 joined to ``trigger_accessibility.py``'s ``l_green``. That split is an artefact:
the 18th nucleotide is physically present in the Kim construct's context either way, and the
endogenous mCherry context being probed is a far wider window than the 1-nt difference. Two
designs built from the same trigger-window overlap, with the same A and B roles, are reaching the
same place in the same transcript, so they get the same number.

So accessibility is keyed on the **window start and role**, which both geometries share, and comes
from ``trigger_accessibility.py``'s ``l_green`` -- Green 2014 Document S1 Eq. 4, the mean unpaired
probability over the window. That is the published descriptor with bench pedigree; the
``open_penalty`` energy stays beside it as a second, stricter view.

**3. RBS(11) over the whole population**, not just the panel's rows: the joint cost of opening all
11 nt of the Shine-Dalgarno in the ON state. ``A_M`` is a per-base mean over 18 nt and the RBS loop
is a different domain, so this is a real addition rather than a restatement.

**What this deliberately does NOT do: fit a weight.** The standing rule forbids it and there are
too few constructs. Accessibility arrives as its own reported axis, and the balance between
switch quality and endogenous reachability stays an explicit choice made when reading the panel.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))

import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402

from engine.gates.toehold import _mean_unpaired  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402

#: Length of ``RBS_FLANK`` inside ``rbs_loop``; the Shine-Dalgarno is what follows it.
RBS_FLANK_LEN = 7

#: Verdicts that disqualify rather than penalise.
DISQUALIFYING = ("FIRES",)

#: What each measurement is worth, measured on 55 designs -- which corrected a 12-design sample
#: that had said something quite different:
#:
#:   ``rbs11_open``   **the only thing genuinely missing.** The joint cost of opening all 11 nt of
#:                    the Shine-Dalgarno at once, kcal/mol, lower better. No column carries it and
#:                    the RBS loop is not inside ``A_M`` (which spans main_z + AUG + main_pre).
#:   ``aug11_mean``   **already on disk.** Recomputing it reproduces the stored ``aug_11`` column
#:                    at rho +1.000, worst absolute difference 0.0000. Pure waste, so it is not in
#:                    the default set.
#:   ``aug11_open``   adds little: rho **-0.941** against the mean form we already have. Kept as an
#:                    option, not a default.
#:   ``rbs11_mean``   rho **-0.944** against ``rbs11_open``. Second-tier for the same reason.
#:
#: **A correction worth keeping.** An earlier version of this comment claimed the AUG's two forms
#: were "genuinely different quantities" at rho +0.077 and that keeping both earned its place.
#: That was 12 designs. At 55 it is -0.941, exactly what a 3-nt window should give, and the +0.077
#: was noise in a restricted range. The redundancy claim for the RBS survived (-0.993 then, -0.944
#: now); the AUG claim did not.
#:
#: So the default is ``rbs_open`` alone: one ``open_penalty`` call, about 0.2 s per design against
#: 0.87 s for everything, which is the difference between a panel this week and a panel next week.
#: ``hairpin_worst`` is the weakest of the four duplexes the two hairpins are meant to form, in
#: the OFF state. It answers a question ``d_off`` cannot: ``d_off`` is an ensemble defect over the
#: WHOLE switch, so it counts the linker's and the cap/r2-star region's internal structure as
#: deviation when that structure is the intent, and it scores the AUG bulge that the closure axis
#: varies on purpose. Measured on the panel, two designs have a main stem that does not form at
#: all -- 0.000 and 0.003 -- while their d_off is 0.50 against a median of 0.19, high but only
#: 2.5x and not obviously broken.
#:
#: One strand, so one pair-probability matrix and no multi-strand pooling: about 0.08 s per design
#: against 0.2 s for rbs11_open.
#: ``ied_rbs_linker_11`` is the strongest single metric on BOTH Green libraries -- +0.356 on the
#: 168 and +0.390 on the 13, against the Barrier's +0.179 / +0.280 -- and Green's own Extended
#: Experimental Procedures S13 reaches the same conclusion independently: "the RBS/mRNA secondary
#: structure terms constitute the category of parameters with the strongest overall correlation",
#: with dG_RBS-linker the best of them. It is **not** in our objective stack and until this metric
#: set existed it was not computed on our designs at all, so it could not be considered.
#:
#: VISTA's Ideal Ensemble Defect collapses to the mean base-pairing probability over a region whose
#: specified structure is "completely unpaired", which is what makes it computable here with no
#: NUPACK and no invented target. Taken over rbs_loop[0]..linker[1]. LOWER is better.
#:
#: ``dG_arm_11``/``dG_arm_00`` are the opening energy over the **18-nt A_M window** rather than the
#: 31-nt W_rank every other dG here uses -- asked for directly, and the one way to tell whether
#: A_M's edge over dG_open is the window or the statistic, since they would then share a window.
#: ``rbs_aug_open_11`` -- the joint cost of opening the Shine-Dalgarno, ``main_z`` and the AUG
#: **all at once**, in the ON tube. kcal/mol, lower better.
#:
#: **Why this span.** Nothing covered it. ``A_M`` is ``main_z + aug + main_pre`` and deliberately
#: excludes the RBS; ``rbs11_open`` is the 11-nt Shine-Dalgarno alone. The ribosome needs the SD and
#: the start codon reachable *together*, and that question had no column.
#:
#: **Why JOINT and not a mean, and this is the whole point.** Measured over 40 gating designs, the
#: SD is **already open in the OFF state** -- mean 0.962 unpaired in tube 00 -- and going to tube 11
#: it **closes** by 0.163 on average. So a MEAN over the 20 nt is dominated by a term that is
#: constant and then moves the wrong way: on real designs the mean runs 0.594 (OFF) to 0.935 (ON), a
#: swing of 0.34, where ``A_M`` over its own 18 nt runs 0.071 to 0.891, a swing of 0.82. Averaging
#: the SD in makes the window a worse discriminator than the one it was meant to improve on.
#:
#: A joint opening does not have that problem. A region that is already open contributes almost
#: nothing to the cost of opening the whole stretch, while a closed ``main_z`` dominates it -- which
#: is what "the ribosome needs all of it at once" actually means.
#:
#: **And it corrects an earlier recommendation.** ``rbs11_open`` was proposed here as the energetic
#: ON-state arm to replace ``dG_rbs_linker``. It is energetic, it is in tube 11, and it is nearly
#: independent of the OFF-state form (rho +0.039). But the quantity moves the wrong way: rho with
#: ``A_M_11`` is **-0.182**, so minimising it weakly selects against the designs whose main stem
#: opens most. That is the 0.163 drop showing up in the ranking. This span does not have that
#: defect, because the SD is no longer the term that carries it.
#:
#: ``eff_toehold_a`` / ``eff_run_a_g0,g1,g2`` -- how many of trigger A's bases are actually paired
#: to the switch in the ON tube, and the longest **duplex** run at each gap size, with
#: ``eff_run_lo``/``eff_run_hi`` giving the switch positions the gap=1 run spans.
#:
#: **``len_x`` is not the effective toehold, and it is not even monotone in it.** Measured on the
#: A_M-gain winners per overlap length, trigger A makes **21 to 32 contacts** in tube 11 while
#: ``len_x`` runs 4 to 7, and the ordering inverts: ``len_x`` 4 gave 31 and 32 contacts where
#: ``len_x`` 7 gave 21 and 27. So a requirement written in ``len_x`` -- "the panel needs a pair with
#: overlap 6 or more" -- is a requirement on a label rather than on A's grip.
#:
#: The run is reported with **one skip allowed**, because the skip is what the measurement is about:
#: on the same designs the longest unbroken run is 13 to 30, and allowing a single gap takes it to
#: 21 to 32. A one-nucleotide interruption halves an unbroken run while costing one contact out of
#: thirty, so a gap-free run measures where the interruptions fall rather than how long the grip is.
#: Two skips add almost nothing beyond one (21 -> 21, 24 -> 26), so one is where the knee is.
#: Every column ``effective_toehold`` returns. Named once, so the ON-tube guard, the metric set, the
#: FIELDS list and the call site cannot drift apart. They already did: a name present in the metric
#: set but missing from the guard is requested, announced as "taken" in the banner, and written as
#: an empty cell -- and it only showed up because ``--metrics all`` happens to satisfy the guard on
#: OTHER names, so the narrow set ``--metrics toehold_a`` was the broken case.
#: The window that is comparable BETWEEN STATES, measured in all four tubes.
#:
#: ``main_z`` (6 nt) is the stretch between the Shine-Dalgarno and the AUG, and ``aug`` is the start
#: codon: 9 contiguous nucleotides, joint opening, kcal/mol, lower better.
#:
#: **Why this window and not a wider one.** Every other window here fails one of two tests. ``A_M``
#: and ``f1`` span ``main_z + main_pre`` and ``f1`` deliberately EXCLUDES the AUG -- the thing the
#: ribosome has to reach. ``rbs_aug_open_*`` adds the Shine-Dalgarno, and measured over 40 gating
#: designs the SD is already 0.962 unpaired in tube 00 and **closes** by 0.163 going to tube 11: in
#: the OFF tubes it contributes a constant and in the ON tube it contributes the wrong sign. That
#: shows up as ``rbs_aug_open_00`` correlating **+0.785 with the barrier** and only -0.190 with
#: ``A_M_11`` -- in tube 00 that window measures stem stability, not state.
#:
#: So the widest window that means the same thing in all four tubes stops before the RBS. These 9 nt
#: are closed in OFF and open in ON by design, which is what makes a difference across tubes a
#: measurement rather than an artefact of the architecture.
#:
#: **All four tubes, because an AND gate has three OFF states.** 00, 01 and 10, and a gate that
#: leaks in any one of them is broken, so the comparator is the WORST of the three -- the same rule
#: the sweep uses for ``A_M_gain``. Only ``open_*`` had all four before this, and its window is the
#: one that excludes the AUG.
#:
#: **Energies, not probabilities, and the two are the same quantity.** ``-RT ln P`` is monotone in
#: P, so within one tube they rank identically; combining tubes, a probability RATIO is an energy
#: DIFFERENCE. The choice is about the tail: a ratio explodes when its denominator collapses, which
#: is exactly how the A_M ratio reached 383 on a denominator that turned out to be a closure label.
#: Over 9 nt a joint probability runs 1e-3 to 1e-6, so a ratio there is all tail. A difference in
#: kcal/mol is bounded and reads directly.
#:
#: **Not yet an arm.** It is computed and reported, and nothing ranks on it, until it has been
#: scored against Green's 168 measured switches. The arm it would replace, ``f1``, scores **-0.107**
#: there, and this window has the same SHAPE as that failed separation -- a difference of openings
#: between tubes -- so resemblance to our own metrics is not evidence. Only the external set
#: decides.
AUG_Z_COLUMNS = frozenset(
    {f"aug_z_open_{state}" for state in ("00", "01", "10", "11")} | {"aug_z_sep"}
)


def secondary_arm_domains(switch: str) -> dict[str, tuple[int, int]]:
    """``sec_z`` and ``x*`` -- the stretch trigger B's binding frees for trigger A to land on.

    The secondary hairpin is 5'-anchored as ``cap(3) r2*(32) sw_x(len_x) k2*(k2) sec_loop(15)
    sec_z(k2) x*(len_x)`` and ends where the main region begins, at ``len(switch) - 75``. ``len_x``
    is recovered by solving that layout rather than read from a column, so this works on a bare
    switch string and cannot disagree with the sequence it was handed.

    **The site is 20 nt for every design, and that is an identity, not a coincidence.**
    ``k2 = (base - 50 - 2*len_x) / 2 = 20 - len_x`` for a 90-nt secondary region, so
    ``sec_z + x* = (20 - len_x) + len_x = 20``. What ``len_x`` changes is how the 20 are SPLIT
    between the two domains, not how many there are -- which is why ``len_x`` says nothing about
    how much of the site trigger A actually covers.

    Empty dict when the layout does not solve, which happens for a switch of unexpected length.
    """
    base = len(switch) - 75
    for len_x in range(4, 9):
        k2 = (base - 50 - 2 * len_x) // 2
        if 3 + 32 + len_x + k2 + 15 + k2 + len_x != base:
            continue
        sw_x_end = 35 + len_x
        k2_star_end = sw_x_end + k2
        loop_end = k2_star_end + 15
        sec_z = (loop_end, loop_end + k2)
        return {"sec_z": sec_z, "x*": (sec_z[1], base)}
    return {}


#: Columns for the run on trigger A's exposed landing site, one per gap size, plus the site's width.
#:
#: **Why these are separate from ``eff_run_a_g*``.** Those take the longest duplex ANYWHERE in the
#: switch, and on the panel's own designs that number is mostly the INVASION: on 150/705/5 a run of
#: 28 is 11 nt on the landing site plus 17 nt on ``main_pre_star``/``bulge_star``/``k1_star``. Two
#: different events -- the stretch B's binding frees for A to land on, and the arm A then invades --
#: and neither is recoverable from their sum.
#:
#: Measured across all 28 eligible pairs at gap 1, the landing run is **4 to 12 of 20 available**,
#: median 7, where ``anywhere`` runs 13 to 23. And the two orderings disagree: the pairs with the
#: best A_M gain are among the WORST on landing -- 507/120/4 at gain 0.8201 lands 7, while 99/705/4
#: at 0.6310 lands 12. Over the 28 pairs, rho(landing, best gain) is **-0.117** at the max and
#: **-0.243** at the median.
#:
#: So this is reported and is never a floor: a floor on it would select against the arm the panel
#: ranks on, and nothing in our data says which of the two events the cell cares about.
LANDING_COLUMNS = frozenset({"land_site_nt"} | {f"land_run_g{gap}" for gap in (0, 1, 2)})


TOEHOLD_COLUMNS = frozenset(
    {"eff_toehold_a", "eff_run_lo", "eff_run_hi"} | {f"eff_run_a_g{gap}" for gap in (0, 1, 2)}
)


METRIC_SETS = {
    "rbs_open": ("rbs11_open",),
    "rbs_aug": ("rbs_aug_open_11", "rbs_aug_open_00"),
    "aug_z": tuple(sorted(AUG_Z_COLUMNS)),
    "toehold_a": tuple(sorted(TOEHOLD_COLUMNS | LANDING_COLUMNS)),
    "landing_a": tuple(sorted(LANDING_COLUMNS)),
    # Everything still missing from the population, and nothing else. All of it reads the
    # SAME 11-tube fold plus the three OFF tubes for aug_z, so the four folds are shared and
    # the set costs barely more than aug_z alone -- where --metrics all would recompute a
    # dozen columns that are already at 100%, including aug11_mean, which reproduces the
    # stored aug_11 at rho +1.000.
    "window_and_toehold": tuple(sorted(AUG_Z_COLUMNS | TOEHOLD_COLUMNS | LANDING_COLUMNS)),
    "hairpin": ("hairpin_worst",),
    "core": ("rbs11_open", "hairpin_worst"),
    "ied": ("ied_rbs_linker_11", "ied_rbs_linker_00"),
    # The two OFF tubes `ied` never measured, so `ied_gain` can be taken against the worst OFF
    # state instead of against the switch alone. Two extra partition functions per design.
    "ied_off": ("ied_rbs_linker_01", "ied_rbs_linker_10"),
    "green_dg": ("dG_rbs_linker",),
    "stem": ("engaged_arm_11",),
    "toehold_b": ("r2_star_00",),
    "arm_energy": ("dG_arm_11", "dG_arm_00"),
    "green": (
        "dG_rbs_linker",
        "ied_rbs_linker_11",
        "ied_rbs_linker_00",
        "dG_arm_11",
        "dG_arm_00",
        "engaged_arm_11",
        "r2_star_00",
    ),
    "all": (
        "rbs11_open",
        "rbs_aug_open_11",
        "rbs_aug_open_00",
        *sorted(AUG_Z_COLUMNS),
        "eff_toehold_a",
        "eff_run_a_g0",
        "eff_run_a_g1",
        "eff_run_a_g2",
        "eff_run_lo",
        "eff_run_hi",
        "land_site_nt",
        "land_run_g0",
        "land_run_g1",
        "land_run_g2",
        "hairpin_worst",
        "aug11_open",
        "rbs11_mean",
        "aug11_mean",
        "ied_rbs_linker_11",
        "ied_rbs_linker_00",
        "dG_arm_11",
        "dG_arm_00",
        "engaged_arm_11",
        "r2_star_00",
        "dG_rbs_linker",
    ),
    "none": (),
}

FIELDS = (
    "switch",
    "rbs_aug_open_11",
    "rbs_aug_open_00",
    "aug_z_open_00",
    "aug_z_open_01",
    "aug_z_open_10",
    "aug_z_open_11",
    "aug_z_sep",
    "eff_toehold_a",
    "eff_run_a_g0",
    "eff_run_a_g1",
    "eff_run_a_g2",
    "eff_run_lo",
    "eff_run_hi",
    "land_site_nt",
    "land_run_g0",
    "land_run_g1",
    "land_run_g2",
    "rbs11_open",
    "rbs11_p",
    "hairpin_worst",
    "hairpin_main_pre",
    "hairpin_k1",
    "hairpin_lock",
    "hairpin_sec",
    "aug11_open",
    "rbs11_mean",
    "aug11_mean",
    "dG_rbs_linker",
    "ied_rbs_linker_11",
    "ied_rbs_linker_00",
    # The two OFF tubes. A column computed and not named HERE is written as an empty cell -- the
    # failure this module's own docstring warns about, and the fifth time it has happened: the run
    # printed "folded measurements taken: ied_rbs_linker_01, ied_rbs_linker_10" while writing
    # neither.
    "ied_rbs_linker_01",
    "ied_rbs_linker_10",
    "dG_arm_11",
    "dG_arm_00",
    "engaged_arm_11",
    "r2_star_00",
    "l_green_a",
    "l_green_b",
    "l_green_worst",
    "offtarget",
    "offtarget_fires",
    "offtarget_blocks",
)


def rbs_span(switch: str) -> tuple[int, int]:
    """The Shine-Dalgarno itself: ``rbs_loop`` is ``RBS_FLANK`` (7 nt) then the 11-nt site."""
    loop = oe.domains(switch)["rbs_loop"]
    return (loop[0] + RBS_FLANK_LEN, loop[1])


def load_offtarget(path: Path) -> dict[tuple[int, int, int], dict]:
    """(a_start, b_start, len_x) -> verdict. Keyed on STARTS, so both geometries match.

    ``b_end`` is identical between the two builds and ``b_start`` differs by 1 nt only because
    trigger B's window is 50 nt in the naive build and 49 in Kim's -- the same location, a
    different length. Keying on the ends would split one pair into two.
    """
    out: dict[tuple[int, int, int], dict] = {}
    if not path.exists():
        return out
    for row in csv.DictReader(path.open(encoding="utf-8")):
        try:
            key = (int(row["a_start"]), int(row["b_end"]), int(row["len_x"]))
        except (KeyError, ValueError):
            continue
        out[key] = {
            "offtarget": row.get("verdict") or "not notable",
            "offtarget_fires": row.get("fires") == "True",
            "offtarget_blocks": row.get("blocks") == "True",
        }
    return out


def load_l_green(path: Path) -> dict[tuple[int, str], float]:
    """(window start, role) -> l_green, shared by both geometries.

    Green 2014 Document S1 Eq. 4: the mean unpaired probability over the window. Keyed on the
    START and the role rather than on (start, end), because the two builds' windows differ by one
    nucleotide at the 3' end and that difference is not a different place in the transcript.
    """
    out: dict[tuple[int, str], float] = {}
    if not path.exists():
        return out
    for row in csv.DictReader(path.open(encoding="utf-8")):
        try:
            out[(int(row["start"]), (row.get("role") or "").strip())] = float(row["l_green"])
        except (KeyError, ValueError, TypeError):
            continue
    return out


#: A trigger base counts as contacting the switch above this total pairing probability.
#:
#: Declared, not fitted: it is the same 0.5 the rest of this notebook calls "paired", and the
#: measurement is a count of bases, so a threshold is unavoidable. Read from the pooled
#: pair-probability matrix rather than an MFE structure, because one structure can miss a contact
#: the ensemble holds at 0.4 -- and the count is the quantity, so a missed contact is a wrong count.
CONTACT_P = 0.5


#: Gap sizes reported, in skipped nucleotides. All three, because the choice is the finding: on the
#: A_M-gain winners per overlap length the gap-free run is 13 to 30 and one gap takes it to 21 to
#: 32, while two gaps add almost nothing (21 -> 21, 24 -> 26). A single interruption halves a
#: gap-free run while costing one contact in thirty, so a gap-free run measures where the
#: interruptions fall rather than how long the grip is -- and a reader should be able to see all
#: three and judge.
RUN_GAPS = (0, 1, 2)


def effective_toehold(
    folder: FoldEngine,
    strands: str,
    switch_len: int,
    trig_a_len: int,
    switch: str | None = None,
) -> dict[str, int | None]:
    """How long a duplex trigger A actually forms with the switch in the ON tube.

    Returns ``eff_toehold_a`` (contacts anywhere) and ``eff_run_a_g0/g1/g2`` (the longest run), plus
    ``eff_run_lo``/``eff_run_hi``, the switch positions the best run spans.

    **A run is contiguous on BOTH strands, and the first version was not.** It counted a run in
    trigger A's own index space, so a stretch of consecutive trigger bases paired to *scattered*
    places in the switch -- the top of the secondary stem among them -- counted as one long toehold.
    That is not a duplex, and it inflates exactly the designs whose trigger is doing several
    unrelated things at once.

    The fix is to key on the **antiparallel diagonal**. In a real duplex, trigger base ``i`` pairs
    with switch base ``j`` and the next pair is ``(i+1, j-1)``, so ``i + j`` is constant along the
    whole helix. Contacts are grouped by that sum and the longest run is taken within a single
    diagonal, which makes a far-away contact a *different* diagonal and therefore a different run,
    not an extension of this one. A skipped nucleotide stays a skip inside one diagonal -- a
    symmetric 1x1 bulge -- rather than licensing a jump across the molecule.

    ``eff_run_lo``/``eff_run_hi`` say where the winning run sits, so "the toehold is 21 nt" can be
    read against the domain map instead of taken on trust: a run in the secondary region and a run
    on the main stem are different events and the number alone does not distinguish them.
    """
    matrix = folder.pooled_pair_probabilities(strands)
    out: dict[str, int | None] = {"eff_toehold_a": None, "eff_run_lo": None, "eff_run_hi": None}
    for gap in RUN_GAPS:
        out[f"eff_run_a_g{gap}"] = None
    for column in LANDING_COLUMNS:
        out[column] = None
    if matrix is None:
        return out

    # The dominant switch partner of each trigger base, and None where the base does not contact
    # the switch at all. The matrix is upper-triangular, so each cell is read from both halves;
    # summing one half silently halves every contact.
    partner: list[int | None] = []
    for index in range(trig_a_len):
        here = switch_len + index
        total, best_p, best_j = 0.0, 0.0, None
        for j in range(switch_len):
            p = matrix[j][here] + matrix[here][j]
            total += p
            if p > best_p:
                best_p, best_j = p, j
        partner.append(best_j if total > CONTACT_P else None)
    out["eff_toehold_a"] = sum(1 for p in partner if p is not None)

    # One bucket per antiparallel diagonal i + j.
    diagonals: dict[int, list[int]] = {}
    for index, j in enumerate(partner):
        if j is not None:
            diagonals.setdefault(index + j, []).append(index)

    for gap in RUN_GAPS:
        best_len, best_span = 0, None
        for total, members in diagonals.items():
            present = set(members)
            start = None
            run = skipped = 0
            for index in range(min(members), max(members) + 1):
                if index in present:
                    if start is None:
                        start = index
                    run += 1
                    if run > best_len:
                        best_len = run
                        best_span = (total - index, total - start)
                elif run > 0 and skipped < gap:
                    skipped += 1
                else:
                    start, run, skipped = None, 0, 0
        out[f"eff_run_a_g{gap}"] = best_len
        if gap == 1 and best_span is not None:
            # Reported for the gap=1 run, the one the metric is read with.
            out["eff_run_lo"], out["eff_run_hi"] = best_span

    # The same diagonals, restricted to the exposed landing site. `switch` is optional only so the
    # two-argument callers keep working; without it the landing columns stay None rather than being
    # filled with a number measured over the wrong region.
    if switch is None:
        return out
    site = secondary_arm_domains(switch)
    if not site:
        return out
    allowed = set(range(*site["sec_z"])) | set(range(*site["x*"]))
    out["land_site_nt"] = len(allowed)
    for gap in RUN_GAPS:
        best = 0
        for total, members in diagonals.items():
            here = {index for index in members if (total - index) in allowed}
            if not here:
                continue
            run = skipped = 0
            for index in range(min(here), max(here) + 1):
                if index in here:
                    run += 1
                    best = max(best, run)
                elif run > 0 and skipped < gap:
                    skipped += 1
                else:
                    run = skipped = 0
        out[f"land_run_g{gap}"] = best
    return out


def status(results: Path, out: str) -> int:
    """How far the shards have got, against the feasible set they are completing."""
    target = len(op.feasible(op.load(results)))
    shards = sorted(results.glob(f"{out}*.csv"))
    if not shards:
        print(f"  nothing written yet -- no results/{out}*.csv")
        print(f"  target: {target:,} feasible designs")
        return 0
    total = 0
    newest = 0.0
    print(f"  {'shard':28s}{'rows':>10s}{'last written':>16s}")
    for path in shards:
        with path.open(encoding="utf-8") as handle:
            rows = max(0, sum(1 for _ in handle) - 1)
        stamp = path.stat().st_mtime
        newest = max(newest, stamp)
        total += rows
        age = time.time() - stamp
        print(f"  {path.name:28s}{rows:>10,}{_ago(age):>16s}")
    share = 100.0 * total / max(target, 1)
    print("")
    print(f"  {total:,} rows written; the feasible set is {target:,} today  ({share:.1f}%)")
    if total > target:
        # Not an error and not over-counting: completions are computed for everything feasible
        # BEFORE the panel's later filters, so that tightening a filter never forces a re-run.
        # A surplus means filters were added since the rows were written, which is the intent.
        print(f"    {total - target:,} rows are for designs a filter has since excluded --")
        print("    expected: completions run before the panel's filters, so a tighter filter")
        print("    costs nothing. It does NOT mean the run overshot.")
    idle = time.time() - newest
    if idle > 300:
        print(f"  nothing written for {_ago(idle)} -- the shards have most likely finished or died")
    else:
        # A rate needs two observations, and one call is one observation. Report what is knowable
        # from a single look rather than inventing a rate from the file's whole lifetime, which
        # would average over every pause and resume.
        print(f"  last write {_ago(idle)} ago, so it is still running. Call again in a minute for")
        print("  a rate: the difference between two calls is the only honest measure of one.")
    return 0


def _ago(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="completions", help="results/<name>.csv")
    parser.add_argument(
        "--rejoin",
        action="store_true",
        help="recompute the cheap joins for rows that already exist, keeping their folded "
        "measurements. Needed after accessibility.csv changes: a plain rerun skips anything "
        "already written, so the stale join would survive",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="print how far the run has got and stop. Safe to call while shards are writing",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="only the first N feasible designs, for a smoke run"
    )
    parser.add_argument(
        "--metrics",
        default="rbs_open",
        choices=sorted(METRIC_SETS),
        help="which folded measurements to take. Default rbs_open: the one quantity no column "
        "carries, ~0.2 s per design. 'all' adds three that are each rho -0.94 or better against "
        "something we already have, at ~0.87 s per design. 'none' does the joins only",
    )
    parser.add_argument(
        "--shard",
        default="",
        metavar="i/n",
        help="complete only shard i of n, writing {out}_{i}.csv. Run n at once, one per core -- "
        "each design needs two open_penalty calls and one pair-probability matrix, so the folding "
        "half is ~1.2 s per design and 16,284 designs is hours on one core. Safe to fork: nothing "
        "here touches RNA.cvar, and the temperature travels on an explicit RNA.md() inside "
        "FoldEngine",
    )
    args = parser.parse_args(argv)

    wanted = set(METRIC_SETS[args.metrics])
    results = HERE / "results"

    if args.status:
        return status(results, args.out)
    every = op.load(results)
    if not every:
        print("  nothing scored yet")
        return 1
    live = op.feasible(every)
    print(f"  {len(every):,} scored -> {len(live):,} feasible designs to complete")

    # RBS(11) needs the two triggers, which are slices of the endogenous transcript.
    transcript = None
    fasta = HERE / "mCherry_original.txt"
    if fasta.exists():
        raw = fasta.read_text()
        transcript = (
            "".join(line.strip() for line in raw.splitlines() if not line.startswith(">"))
            .upper()
            .replace("T", "U")
        )
        print(f"  transcript {len(transcript):,} nt from {fasta.name}")
    elif wanted:
        print(f"  no {fasta.name}: the folded measurements will be None for every row")

    off = load_offtarget(results / "offtarget_folded.csv")
    lg = load_l_green(results / "accessibility.csv")
    print(f"  off-target verdicts for {len(off):,} trigger pairs")
    print(f"  l_green for {len(lg):,} (window start, role) keys")
    shard_index = shard_total = None
    if args.shard:
        shard_index, shard_total = (int(v) for v in args.shard.split("/"))
        if not 0 <= shard_index < shard_total:
            print(f"bad --shard {args.shard}: need 0 <= i < n")
            return 1
        live = [r for i, r in enumerate(live) if i % shard_total == shard_index]
        print(f"  shard {shard_index} of {shard_total}: {len(live):,} designs")
    if args.limit:
        live = live[: args.limit]

    name = args.out if shard_total is None else f"{args.out}_{shard_index}"
    path = results / f"{name}.csv"
    done: set[str] = set()
    # Read EVERY shard's file, not just this shard's. The shard a design lands in is its index in
    # the feasible list, so the boundaries move whenever a filter changes the list's length -- and
    # then a design whose row sits in shard 0's file is looked up by shard 3, found missing, and
    # its earlier measurements are silently dropped. That is exactly what happened when
    # hairpin_worst was added: the feasible set had shrunk 16,284 -> 14,823, every boundary
    # shifted, and rbs11_open survived on only 2,182 rows of 14,823.
    existing: dict[str, dict] = {}
    for source in sorted(results.glob(f"{args.out}*.csv")):
        with source.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("switch"):
                    existing.setdefault(row["switch"], row)
    if path.exists():
        if args.rejoin:
            # Keep the folded numbers and redo the joins: the folds are the expensive half and
            # nothing about them changed.
            print(f"  --rejoin: refreshing the joins on {len(existing):,} rows already written")
            wanted = set()
            live = [r for r in live if r["switch"] in existing]
        else:
            # A row counts as done only if it already carries every metric THIS run wants. Adding
            # a metric therefore re-scores just that metric's gap rather than forcing the whole
            # file to be thrown away, and the fields it is not recomputing are carried forward
            # below -- so a second pass never loses the first pass's work.
            done = {
                switch
                for switch, row in existing.items()
                if all(row.get(field) not in (None, "") for field in wanted)
            }
            print(
                f"  resuming: {len(done):,} of {len(existing):,} written rows already carry "
                f"{', '.join(sorted(wanted)) if wanted else 'nothing to recompute'}"
            )

    folder = FoldEngine(37.0)
    hits = {"offtarget": 0, "l_green": 0, "fires": 0, "blocks": 0}
    written = 0
    # Rewrite whenever an existing file is being extended: appending would leave the old rows
    # without the new columns, and a CSV with two shapes is not a CSV.
    # Rewrite whenever existing rows need new columns -- appending would leave the old rows short
    # and a CSV with two shapes is not a CSV.
    mode = "a" if (done and len(done) == len(existing)) else "w"
    if mode == "w" and existing and args.limit:
        # --limit plus a rewrite would truncate the file to N rows and silently destroy the rest.
        print(f"  REFUSING: --limit {args.limit} would rewrite {path.name} with {args.limit} rows")
        print(f"  and discard {len(existing):,}.")
        print("  Use --out <other name> for a sample, or drop --limit to extend this file.")
        return 1
    with path.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), extrasaction="ignore")
        if mode == "w":
            writer.writeheader()
        # Every existing row is carried through a rewrite, INCLUDING designs no longer in `live`.
        #
        # This file's scope is `feasible()`, and `feasible()` now filters on columns computed
        # HERE -- `hairpin_worst`, `engaged_arm_11`. That is circular, and it made each run's
        # scope narrower than the last: a design measured in an earlier pass but excluded by a
        # filter added since was simply not iterated, so the rewrite dropped it. Measured damage
        # from one such run: a shard file went from 2,470 rows holding four metrics to 965 rows
        # holding one, and the four were gone.
        #
        # Measuring is not the same job as filtering, so a measurement is never deleted because
        # today's filters reject its design. If a filter is later loosened the number is still
        # there instead of needing another 35-minute pass.
        if mode == "w":
            in_live = {r["switch"] for r in live}
            orphans = [kept for sw, kept in existing.items() if sw not in in_live]
            for kept in orphans:
                writer.writerow(kept)
                written += 1
            if orphans:
                print(
                    f"  carried {len(orphans):,} measured row(s) whose design a filter now "
                    f"excludes -- kept rather than deleted"
                )
        for index, row in enumerate(live):
            switch = row["switch"]
            keep = existing.get(switch)
            if switch in done:
                # Already carries everything this run wants. When APPENDING that means skip it;
                # when REWRITING the file it must still be written, or skipping it deletes it --
                # which is how a finished run came out at 85.3% coverage instead of 100%.
                if mode == "w" and keep:
                    writer.writerow(keep)
                    written += 1
                continue
            a_start, b_end = int(row["a_start"]), int(row["b_end"])
            len_x = int(row["len_x"])
            out: dict[str, object] = {"switch": switch}

            verdict = off.get((a_start, b_end, len_x))
            if verdict:
                out.update(verdict)
                hits["offtarget"] += 1
                hits["fires"] += bool(verdict["offtarget_fires"])
                hits["blocks"] += bool(verdict["offtarget_blocks"])

            la = lg.get((a_start, "A"))
            lb = lg.get((int(row["b_start"]), "B"))
            if la is not None:
                out["l_green_a"] = round(la, 4)
            if lb is not None:
                out["l_green_b"] = round(lb, 4)
            if la is not None and lb is not None:
                out["l_green_worst"] = round(min(la, lb), 4)
                hits["l_green"] += 1

            # None when it could not be measured, never 0.0: zero is what a perfectly open site
            # costs, so a failed measurement written as 0.0 would become the best design here.
            if "hairpin_worst" in wanted:
                fidelity = oe.hairpin_fidelity(folder, switch, int(row["len_x"]))
                out["hairpin_worst"] = fidelity["worst"]
                for part in ("main_pre", "k1", "lock", "sec"):
                    out[f"hairpin_{part}"] = fidelity[part]
            # The OFF-state pair, which needs no transcript: the switch folds alone in tube 00.
            if "rbs_aug_open_00" in wanted:
                # The OFF comparator for the SD-through-AUG span. Needs no transcript -- tube 00
                # is the switch alone -- so it sits here rather than in the ON-tube block, whose
                # guard requires one. Kept beside the ON form because the span's value is only
                # readable as a change: the Shine-Dalgarno is ~0.96 unpaired in tube 00 on every
                # design, so a single number is mostly a constant.
                out["rbs_aug_open_00"] = folder.open_penalty(
                    switch, ((rbs_span(switch)[0], oe.domains(switch)["aug"][1]),)
                )
            if "dG_rbs_linker" in wanted:
                # GREEN'S OWN best predictor, and a different statistic from the IED over the
                # same span: he folds the RBS-loop-through-linker stretch BY ITSELF and reports
                # its MFE, where the IED is the mean pairing probability of that region inside
                # the whole molecule. Green 2014 S13 found this the strongest single parameter in
                # the strongest category; measured against his 168 it is +0.334 to the IED's
                # +0.356, so the two are close and neither subsumes the other.
                #
                # Folded as a SUBSEQUENCE, exactly as he did it -- not as a window inside the
                # switch. Those are different numbers and using the second while citing the
                # first would be comparing our value to his under a shared name.
                dom = oe.domains(switch)
                piece = switch[dom["rbs_loop"][0] : dom["linker"][1]]
                folded = folder.mfe(piece)
                out["dG_rbs_linker"] = None if folded is None else round(folded.energy, 3)
            if {"ied_rbs_linker_00", "dG_arm_00", "r2_star_00"} & wanted:
                dom = oe.domains(switch)
                arm_span = (dom["main_z"][0], dom["main_pre"][1])
                if {"ied_rbs_linker_00", "r2_star_00"} & wanted:
                    # One 00-tube matrix serves both, so r2* costs nothing beside the IED.
                    matrix = folder.pooled_pair_probabilities(switch)
                    if "ied_rbs_linker_00" in wanted:
                        out["ied_rbs_linker_00"] = round(
                            1.0 - _mean_unpaired(matrix, dom["rbs_loop"][0], dom["linker"][1]), 4
                        )
                    if "r2_star_00" in wanted:
                        # Trigger B nucleates on r2*, a 32-nt arm, and this says how reachable
                        # it is before anything binds. `four_tube_observables` has computed it
                        # as `A_r2_star_00` since the start, but only two of the sweep's runs
                        # carried the column and the panel's designs are not in them -- so
                        # "is trigger B's toehold accessible" had no answer for any row shown.
                        # r2* is fixed at (3, 35) for every len_x: the secondary hairpin is
                        # 5'-anchored as cap(3) r2*(32) sw_x(len_x) ..., so only the domains
                        # AFTER r2* move with the overlap length.
                        out["r2_star_00"] = round(_mean_unpaired(matrix, 3, 35), 4)
                if "dG_arm_00" in wanted:
                    out["dG_arm_00"] = folder.open_penalty(switch, (arm_span,))
            if wanted & {
                "rbs11_open",
                "aug11_open",
                "rbs11_mean",
                "aug11_mean",
                "ied_rbs_linker_11",
                "dG_arm_11",
                "engaged_arm_11",
                # Every metric computed inside this block must be named here. A name missing from
                # the guard is requested, reported as "taken", and silently written as an empty
                # cell -- and `--metrics all` hides it, because the guard passes on other names.
                "rbs_aug_open_11",
                *TOEHOLD_COLUMNS,
                *LANDING_COLUMNS,
                *AUG_Z_COLUMNS,
            } and (transcript is not None):
                trig_a = transcript[a_start : int(row["a_end"])]
                trig_b = transcript[int(row["b_start"]) : b_end]
                tube = f"{switch}&{trig_a}&{trig_b}"
                aug, rbs = oe.domains(switch)["aug"], rbs_span(switch)
                if "rbs11_open" in wanted:
                    out["rbs11_open"] = folder.open_penalty(tube, (rbs,))
                if "aug11_open" in wanted:
                    out["aug11_open"] = folder.open_penalty(tube, (aug,))
                if "rbs_aug_open_11" in wanted:
                    # One span, Shine-Dalgarno through the AUG inclusive. `rbs` already starts at
                    # the SD (the 7-nt flank is excluded by RBS_FLANK_LEN), and rbs_loop, main_z
                    # and aug are contiguous, so the span is (rbs start, aug end).
                    out["rbs_aug_open_11"] = folder.open_penalty(tube, ((rbs[0], aug[1]),))
                if wanted & AUG_Z_COLUMNS:
                    # One span, four tubes. `main_z` and `aug` are contiguous, so the window is
                    # (main_z start, aug end) -- 9 nt, ending at the last base of the start codon.
                    window = (oe.domains(switch)["main_z"][0], aug[1])
                    tubes = {
                        "00": switch,
                        "01": f"{switch}&{trig_b}",
                        "10": f"{switch}&{trig_a}",
                        "11": tube,
                    }
                    for state, strands in tubes.items():
                        out[f"aug_z_open_{state}"] = folder.open_penalty(strands, (window,))
                    # The separation: the WORST OFF tube's opening cost minus the ON tube's.
                    # Positive means the ON state opens more cheaply than the best-opening OFF
                    # state, which is the gate working. None when any term is missing -- never 0.0,
                    # which would read as a measured tie and rank a failed measurement above a real
                    # one.
                    # NOT `off`: that name holds the off-target table for the whole loop, and
                    # shadowing it made the next iteration call .get on a list.
                    off_costs = [out[f"aug_z_open_{s}"] for s in ("00", "01", "10")]
                    on_cost = out["aug_z_open_11"]
                    out["aug_z_sep"] = (
                        None
                        if on_cost is None or any(v is None for v in off_costs)
                        else round(min(off_costs) - on_cost, 4)
                    )
                if wanted & (TOEHOLD_COLUMNS | LANDING_COLUMNS):
                    # One call, both families: the fold and the partner scan are the whole cost
                    # and they are shared, so computing the landing run separately would pay for
                    # them twice and let the two answers drift apart.
                    out.update(
                        effective_toehold(folder, tube, len(switch), len(trig_a), switch=switch)
                    )
                if "dG_arm_11" in wanted:
                    dom = oe.domains(switch)
                    out["dG_arm_11"] = folder.open_penalty(
                        tube, ((dom["main_z"][0], dom["main_pre"][1]),)
                    )
                if {"rbs11_mean", "aug11_mean", "ied_rbs_linker_11", "engaged_arm_11"} & wanted:
                    # One matrix serves both means, and the FoldEngine cache makes a second call
                    # on the same tube free -- measured 0.454 s cold against 0.0072 s warm.
                    matrix = folder.pooled_pair_probabilities(tube)
                    if "rbs11_mean" in wanted:
                        out["rbs11_mean"] = round(_mean_unpaired(matrix, *rbs), 4)
                    if "aug11_mean" in wanted:
                        out["aug11_mean"] = round(_mean_unpaired(matrix, *aug), 4)
                    if "engaged_arm_11" in wanted:
                        # Share of main_pre* paired with trigger A in the ON tube: did A open
                        # the main stem, as opposed to merely taking the freed x* lock. These
                        # are different events and a design can do the second without the
                        # first -- measured on the panel, designs scoring 0.85-0.97 on x* sat
                        # at 0.006-0.047 here, so the gate never opens and the lock term says
                        # it did.
                        lo, hi = oe.domains(switch)["main_pre_star"]
                        block = (len(switch), len(switch) + len(trig_a))
                        out["engaged_arm_11"] = round(
                            sum(matrix[i][j] for i in range(lo, hi) for j in range(*block))
                            / (hi - lo),
                            4,
                        )
                    if "ied_rbs_linker_11" in wanted:
                        dom = oe.domains(switch)
                        out["ied_rbs_linker_11"] = round(
                            1.0 - _mean_unpaired(matrix, dom["rbs_loop"][0], dom["linker"][1]),
                            4,
                        )
            # The two OFF tubes the IED never had.
            #
            # **The gain was `ied(00) - ied(11)` and the rule is the worst OFF.** 00 is the switch
            # alone; the other two OFF states have a trigger bound, and a trigger that opens part
            # of the molecule without opening the gate shows up in them and not in 00. So
            # `ied_gain` was comparing the ON state against the *easiest* OFF state, which is the
            # one comparison that cannot catch a leak. With these three columns present,
            # `ied_gain_worst` is the same subtraction against `max(00, 01, 10)` -- max, because
            # the IED is a PAIRED fraction and more paired is the shut state.
            if {"ied_rbs_linker_01", "ied_rbs_linker_10"} & wanted and transcript is not None:
                dom = oe.domains(switch)
                # Bound here rather than borrowed from the block above: that block's trigger
                # variables only exist when one of ITS columns was asked for, so reading them
                # from here raised UnboundLocalError on a run that asked for these two alone.
                a_only = transcript[a_start : int(row["a_end"])]
                b_only = transcript[int(row["b_start"]) : b_end]
                for state, strands in (
                    ("01", f"{switch}&{b_only}"),
                    ("10", f"{switch}&{a_only}"),
                ):
                    if f"ied_rbs_linker_{state}" not in wanted:
                        continue
                    matrix = folder.pooled_pair_probabilities(strands)
                    out[f"ied_rbs_linker_{state}"] = (
                        None
                        if matrix is None
                        else round(
                            1.0 - _mean_unpaired(matrix, dom["rbs_loop"][0], dom["linker"][1]), 4
                        )
                    )
            if keep:
                # Carry forward anything this run did not recompute, so metrics accumulate across
                # passes instead of replacing each other.
                for field in FIELDS:
                    if field == "switch" or field in out:
                        continue
                    if keep.get(field) not in (None, ""):
                        out[field] = keep[field]
            # Derived, never measured: open_penalty IS -RT.ln(P), so P is exp(-dG/RT) on a number
            # already in hand. Done here rather than inside the fold block so that a row whose
            # energy was measured by an EARLIER run -- before this column existed -- gains the
            # probability on a --rejoin pass, with no refolding.
            energy = out.get("rbs11_open")
            if energy is not None:
                out["rbs11_p"] = f"{math.exp(-float(energy) / folder.rt):.3g}"
            writer.writerow(out)
            handle.flush()
            written += 1
            if index % 500 == 0:
                print(f"  {index + 1}/{len(live)}  written {written:,}", flush=True)

    print(f"\n  wrote {written:,} rows to {path.name}")
    print(
        f"    off-target verdict joined: {hits['offtarget']:,}"
        f"   FIRES {hits['fires']:,}   BLOCKS {hits['blocks']:,}"
    )
    print(f"    l_green joined (both roles): {hits['l_green']:,}")
    if hits["l_green"] < written:
        # accessibility.csv covers only the windows an earlier stage-1b run scored. The gap is
        # missing DATA, not a key mismatch -- keying on (start, role) already merged the two
        # geometries, which the (start, end) key had split.
        missing = written - hits["l_green"]
        print(f"    {missing:,} rows have no l_green: those windows were never scored by")
        print("    trigger_accessibility.py. To fill the gap, run it over EVERY window:")
        print(
            "      uv run python src/engine/gates/notebooks/toehold_and/trigger_accessibility.py \\"
        )
        print("        --fasta src/engine/gates/notebooks/toehold_and/mCherry_original.txt \\")
        # --pairs 0 is NOT optional: it defaults to 40, and a run without it overwrites
        # accessibility.csv with 80 windows. That happened once and destroyed 921 of them. An
        # earlier version of this very message omitted the flag, which is how.
        print("        --pairs 0 --out accessibility     # --pairs 0, or it writes only 40 pairs")
        print("    then rerun THIS script with --rejoin. A plain rerun skips every switch that")
        print("    already has a row, so the stale join would survive.")
    print(f"    folded measurements taken: {', '.join(wanted) if wanted else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
