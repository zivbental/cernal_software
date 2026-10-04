"""Pick an orderable panel: four objective functions, two geometries, one trigger pair each.

    uv run python src/engine/gates/notebooks/toehold_and/objective_panel.py --out panel_energy

**The design.** Every row differs from another in exactly one of three things: which objective
chose it, which secondary-arm geometry it uses, or which trigger pair it sits on. Nothing else
varies, so a bench result points at one cause.

    2 trigger pairs  x  2 geometries  x  4 objectives  =  16 rows

**The trigger pair is held constant across geometries**, which took two attempts to establish.
Keying a pair on ``(a_start, b_start)`` finds **0 of 2,078** pairs shared between the 161-nt
and 165-nt builds, and that was reported here as a structural impossibility. It is not:
``b_end`` is *identical* in both, and ``b_start`` differs by 1 nt only because trigger B's
window is 50 nt in the naive build and 49 in the Kim build. Same location, different length.
x* does not move either -- 416 x* positions are shared. Keyed on
``(a_start, b_end, len_x)``, **1,020 of 1,042** pairs are shared and **112** carry at least two
feasible designs in both geometries. A column that is nearly the identity is not the identity.

**The two geometries** are the comparison the panel exists to make:

    161 nt   the naive 18-nt secondary arm      (k2* = 18 - len_x)
    165 nt   Kim 2019: 20-nt arm, 17-nt invasion, AUA cap  (k2* = 20 - len_x)

**The four objectives**, all ranking inside the same feasible set so the comparison is of the
functions and not of their floors:

    f1        AND-ness, kcal/mol: open(11) - min[open(00), open(01), open(10)]
    f2        A_M ratio: A_M(11) / max[A_M(00), A_M(01), A_M(10)]
    Barrier   the activation energy alone, from find_saddle
    f4        percentile aggregate of f1, Barrier and access

``Barrier`` stands alone rather than as ``f1 + Barrier`` because that sum *is* the barrier:
measured, it correlates **+0.867** with the barrier and only **+0.185** with f1. Calling it a
correction to f1 would have been a fiction.

``f4`` aggregates by **percentile inside the feasible set**, not by adding kcal/mol. Adding
fails for a measurable reason: ``f1 + Barrier + access`` correlates **+0.886** with access
alone, because sd(access) = 7.00 and sd(Barrier) = 4.40 against sd(f1) = 2.86, so the two large
terms decide everything. Percentiles give each term the same range by construction rather than
by a weight fitted to outcomes, which the standing rule forbids. The cost is that the score
depends on the reference population, so the population size is printed with the panel.

**Not included.** Off-target is a hard filter's job, not a ranking term -- of 399 flagged
trigger pairs, 23 fire the gate alone and 113 block the real triggers, and no ordering of a
continuous score expresses "this one is disqualified". It is also not yet joined to the scorer.
"""

import argparse
import csv
import glob
from pathlib import Path

# The screens are defined in the scorer, which is the lower layer and the place they are
# applied first. Importing them keeps exactly one definition of each: two copies of a
# threshold is how the panel and the sweep end up disagreeing about what is feasible.
from objective_energy import ON_CEILING, RARE_CODONS, domains, early_codons
from objective_energy import domains as _oe_domains

from engine.sequences import reverse_complement as _revcomp

#: Secondary-arm geometry, inferred from switch length: 161 nt is the documented default
#: assembly (cap through linker) and 165 is 4 nt longer, which is what ``--kim-arm`` adds. The
#: folded shards do not record which flag produced them, so this is an inference, not a fact
#: read off the data.
GEOMETRY = {161: "naive 18nt", 165: "Kim 20/17/AUA"}

#: Floor on ``aug_11``: a start codon buried in the ON state is a dead switch whatever else it
#: scores. Same column and same threshold as ``candidates.py``, so the two agree by construction.
#:
#: It is a **cheap guard rather than a discriminator** -- among gating designs it rejects 7.1%
#: (88 of 1,241 measured), and all seven designs in the current panel clear it by a wide margin
#: (0.714 to 0.975). It is restored because it is free and because 7.1% would have bitten
#: eventually, not because it is doing heavy lifting today.
AUG_FLOOR = 0.2

#: The x* lock, all four terms, from columns the folded run already wrote: the lock holds with no
#: trigger and with A alone, trigger B alone frees it, and A then takes the freed site. Geometric
#: mean, so one failure pulls the score down instead of being averaged away.
#:
#: **The fourth term does not need a fold after all.** An earlier version of this comment said it
#: did -- that ``candidates.py``'s "A takes the freed site" needs a
#: ``pooled_pair_probabilities`` call against A's own block, which no column carries -- and
#: refused to filter on a three-term proxy for that reason. Measured against the true four-term
#: score on 18 designs with the folds actually done:
#:
#:     Spearman(true 4-term, 3-term proxy)              +0.874
#:     Spearman(true 4-term, this 4-term proxy)         +0.994
#:     Spearman(engA(11) term, 1 - free_xstar_11)       +0.998   medians 0.991 vs 0.995
#:
#: ``1 - free_xstar_11`` is formally only an upper bound on "x* is paired **with A**" -- x* could
#: be paired with something else -- but in state 11 there is nothing else free to take it, so the
#: bound is tight. At rho 0.994 against the real thing this is the same quantity, and
#: ``LOCK_FLOOR`` transfers to it legitimately.
LOCK_FLOOR = 0.3

#: Measured for scale over 1,241 gating designs: median 0.741, p10 0.577, and only **0.6%** fall
#: below the floor -- the ON ceiling and the gating floor already remove the broken locks. So this
#: is a guard, like AUG(11), and not a discriminator. The panel's seven sit at 0.663 to 0.791.

#: Floor on ``l_green``, the worse of the two trigger windows. Green 2014 Document S1 Eq. 4: the
#: mean unpaired probability over the window, on the endogenous transcript.
#:
#: **Set at the MEDIAN of the ranked population, 0.483, and that is a declared choice rather than
#: a calibration.** Nothing published fixes a threshold here, so any number is arguable; the median
#: at least splits the population we have instead of importing a figure from a different library.
#: It keeps 3,560 of the 7,348 ranked designs whose windows carry an l_green (48.4%).
#:
#: **Why it is a filter and not a ranking term.** Accessibility does not predict gate quality --
#: measured, |rho| <= 0.13 on both definitions -- and the reason is structural: the objectives are
#: calibrated on Green's TRUNCATED-trigger data, which never tested endogenous reachability. The two
#: axes are orthogonal by construction, so mixing them into one score would trade a real quantity
#: against a blind one. Filter on reachability, then rank the survivors on switch quality.
#:
#: The cost, measured: best A_M ratio unchanged at 383.6, best Barrier 11.2 -> 13.0, best combined
#: 95.4 -> 93.0.
L_GREEN_FLOOR = 0.483

#: Floor on ``l_full_w25`` -- **the accessibility filter the panel actually applies.**
#:
#: Same quantity, two definitions, and they are nearly independent: ``l_green`` folds the binding
#: window as an isolated slice, ``l_full_w25`` averages per-base unpaired probability over that
#: window plus 25 nt each side from one fold of the whole 711-nt transcript, and over 5,357 designs
#: that carry both, **rho(l_green, l_full_w25) = +0.195**. So this is a change of which designs are
#: rejected, not a cosmetic relabel.
#:
#: **Why the flanked full-transcript form wins.** It is the one with external support: +0.317
#: against VISTA's 189 measured switches, where the isolated-slice ``mfe_w25`` managed +0.011. A
#: window folded on its own cannot know what the rest of the transcript does to it, and reachability
#: is exactly a question about the rest of the transcript.
#:
#: **0.3482 is the median of the ranked population**, the same declared rule ``L_GREEN_FLOOR`` was
#: set by, re-derived on this column rather than inherited -- the two distributions do not overlap
#: (l_green median 0.4930, this one 0.3482), so reusing 0.483 would reject everything.
#:
#: Measured with the floor switched OFF first, which matters: with it on, ``l_green``'s minimum
#: comes back at 0.4838, a hair above its own 0.483 floor, because the filter has already run -- and
#: a "median of the population" taken there is the median of the half the floor kept, which ratchets
#: the floor upward every time anyone re-derives it.
#:
#: **It also reaches every design, which the old filter could not.** ``l_full_w25`` comes from one
#: fold of the whole transcript, so any window is a mean over a slice of a profile already in
#: memory, and ``accessibility_s1.py`` scores every window the designs actually use: **100%
#: coverage**, 941 (start, role) keys. ``l_green`` reaches **85.6%** -- it is folded per window, so
#: a window nobody ran has no value -- which means 14% of designs passed its floor unchecked. A
#: floor only rejects a value it has, and "never measured" is deliberately not "failed", so that 14%
#: was never a rejection it declined to make; it was a rejection it could not see.
#:
#: What it costs, measured on the same 6,129 ranked designs with each floor at its own median:
#: ``l_full_w25`` leaves 2,048 gating designs and 37 eligible pairs, ``l_green`` 2,132 and 36. So it
#: rejects ~80 more designs and still buys a pair, because what it rejects is what the old filter
#: was blind to. For scale, no accessibility floor at all leaves 3,555 gating designs and 74
#: eligible pairs, so this is the single most expensive filter the panel applies.
L_FULL_W25_FLOOR = 0.3482

#: Floor on ``l_local`` -- **the accessibility filter the panel applies**, replacing the one above.
#:
#: ``l_local`` is ``FoldProfiler.openness``: RNAplfold's unpaired probability in a *sliding local
#: window* with a capped pair span, averaged over the trigger window itself. The other two assume a
#: 711-nt transcript reaches global equilibrium, which it does not -- it folds co-transcriptionally
#: from the 5' end and local structure persists. RNAplfold exists for that reason and is the
#: established method for target-site accessibility.
#:
#: **The measure it replaces had no external support.** ``l_full_w25`` was introduced here as
#: "VISTA's form" and is not: VISTA folds a SLICE of site +- L globally, while ``l_full_w25`` folds
#: the WHOLE transcript and averages over site +- 25. Two differences at once, so the +0.317 that
#: justified it belongs to VISTA's measure. ``l_full_w25`` also averages in 50 nt the trigger never
#: touches, which is a smoothing choice with no mechanism behind it.
#:
#: **This is a per-TRIGGER filter and nothing else.** The column is joined as ``min(l_local_A,
#: l_local_B)``, and ``min(A, B) > floor`` is exactly ``A > floor and B > floor`` -- so it asks of
#: each window independently whether it is reachable, and never ranks designs. (It can still vary
#: between a pair's designs, because a pair is keyed on ``b_end`` and the two geometries give the
#: same ``b_end`` a different ``b_start``: 50 nt against 49.)
#:
#: **0.3369 is the median of the ranked population**, the same declared rule the two floors before
#: it came from, measured with every accessibility floor switched OFF so the median is not the
#: median of the half a floor already kept.
#:
#: Not the median over WINDOWS, which is 0.4065 -- and that distinction is the whole threshold.
#: The column is a minimum of two draws, so its design-level median sits below the window-level one.
#: A window median rejects half of all windows, and a pair needs BOTH of its windows to pass, so it
#: leaves about a quarter of the pairs: measured, **32 pairs against 93**, with the best A_M gain
#: falling 0.8222 to 0.8180. The design-level median keeps the "half the population" rule in the
#: terms the filter is actually applied in.
#:
#: What it costs against the floor it replaces, on the same 4,780 ranked designs: gating 1,669 ->
#: 1,423, and **eligible pairs 68 -> 93** with the best A_M gain rising 0.8201 -> 0.8222. It rejects
#: more designs and admits more pairs, because the two floors disagree about **272 of 941 windows**
#: (71% agreement) and ``l_local``'s half is the better-founded one.
L_LOCAL_FLOOR = 0.3369

#: Floor on the x* lock's **01 term alone**: does trigger B, acting by itself, actually free x*?
#:
#: **Deliberately lenient, and that is a measurement rather than timidity.** The 4-term lock mean
#: cannot screen this at all -- with the other three terms near 1.0 it only crosses ``LOCK_FLOOR``
#: when the 01 term drops below **0.0081**, and the worst observed is 0.185, twenty-three times
#: higher. So the dilution is total and a separate floor is the only way to express it.
#:
#: But a strict floor would delete good gates. Measured on the panel's own cards, designs with a
#: weak 01 still engage in state 11:
#:
#:     01 0.295 -> 11 engaged 0.999   andness -3.88
#:     01 0.294 -> 11 engaged 0.999   andness -3.50
#:     01 0.241 -> 11 engaged 1.000   andness -9.44   <- among the best in the panel
#:     01 0.225 -> 11 engaged 0.997   andness -6.28
#:     01 0.185 -> 11 engaged 0.750   andness -4.47   <- the only one that propagates
#:
#: Trigger A evidently captures x* from whatever it re-paired with, not only from a free x*, so
#: **the 01 term is not on the critical path**. 0.20 removes the single design whose weakness
#: reaches state 11 and keeps the four where it does not. A floor at 0.30 would have cost five.
LOCK01_FLOOR = 0.20

#: AND-ness below this counts as gating, kcal/mol.
GATING = -2.0

#: Floor on ``andness_variant``, in kcal/mol, or ``None`` to leave it off.
#:
#: **The honest gating floor, and off by default only because switching it on is your call.**
#: ``GATING`` is applied to ``f1``, the AND-ness of four tubes built by omitting strands. The
#: experiment cannot omit a strand: it realises state 10 with a transcript whose B window is
#: recoded, and that strand is still in the tube. Measured over all 1,317 designs that pass
#: ``GATING``:
#:
#:     median AND-ness, sweep        -4.94
#:     median AND-ness, transcripts  -2.74     a loss of 2.2 kcal/mol
#:     no gate left at all (>= -0.01)  105     8.0%
#:     effectively none  (>= -0.5)     328    24.9%
#:     rho between the two          +0.374
#:
#: So ranking on the sweep's AND-ness orders designs by a quantity that explains about an eighth
#: of the variance in what will be observed. The leak is almost entirely ``leak_10``: in nearly
#: every row the whole loss equals the 10 tube's, which is the same conclusion the sweep reached
#: from the other side -- state 10 is the only leak.
#:
#: At ``-2.0`` it keeps **764 of 1,317** designs, 77 of 92 trigger pairs and 62 of 94 cells with
#: three or more designs -- enough to build a panel. ``--bench-floor -2.0``.
VARIANT_GATING: float | None = None
#: Schemes that cannot gate: 0 of 4,330 and 0 of 384 designs respectively, with a known
#: mechanism -- A-anchored spends lock strength on trigger A's own site, so A alone opens the
#: stem and ``open_10`` equals ``open_11``.
DEAD_SCHEMES = ("A-anchored", "unlocked")


def _num(row: dict, key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load(results: Path) -> list[dict]:
    """Energy scores joined to design axes, one row per switch.

    A switch can be scored under more than one family -- 3,077 such rows exist -- so one is
    kept. Those duplicates are not an inconsistency: ``andness`` agrees to six decimal places
    in every case, which is the check that the scoring is deterministic.
    """
    axes: dict[str, dict] = {}
    for path in sorted(glob.glob(str(results / "*_folded_*.csv"))):
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                switch = row.get("switch")
                if not switch or switch in axes:
                    continue
                a_m = [_num(row, f"A_M_{s}") for s in ("00", "01", "10", "11")]
                worst_off = max((v for v in a_m[:3] if v is not None), default=None)
                states = ("00", "01", "10", "11")
                free_x = [_num(row, f"free_xstar_{k}") for k in states]
                axes[switch] = {
                    # AUG(11) and the x* lock: already computed for all 390,814 designs by the
                    # folded run, and a rebuild of this panel around the energy objective
                    # silently stopped reading them. They cost nothing to read.
                    "aug_11": _num(row, "aug_11"),
                    # The 01 term on its own, because the 4-term mean dilutes it away.
                    "lock01": free_x[1],
                    # How far the OFF state's real fold sits from the intended two-hairpin shape,
                    # normalised by length. Reported, NOT thresholded: candidates.py measured the
                    # spread here as p10 0.181, median 0.215, p90 0.257, and with no literature bar
                    # any cut would be invented. It is on the card so a design whose 00 state does
                    # not look like two hairpins is visible rather than silently ranked.
                    "d_off": _num(row, "d_off"),
                    # Trigger B's own binding arm, r2*, in the OFF tube: how reachable B's
                    # landing site is before anything binds. `four_tube_observables` has
                    # computed this for every folded design all along and nothing read it, so
                    # "is trigger B's toehold accessible" had no answer on the page. Trigger A's
                    # counterpart is `l_green_a`/`access`, which do reach the card -- B's did
                    # not, and the two are not interchangeable: A nucleates on the freed x*
                    # while B nucleates on r2*, a 32-nt arm.
                    "r2_star_00": _num(row, "A_r2_star_00"),
                    "lock": (
                        None
                        if any(v is None for v in free_x)
                        else (
                            max(1 - free_x[0], 1e-6)  # lock holds, no trigger
                            * max(1 - free_x[2], 1e-6)  # lock still holds with A alone
                            * max(free_x[1], 1e-6)  # B alone frees x*
                            * max(1 - free_x[3], 1e-6)  # and A then takes the freed site
                        )
                        ** 0.25
                    ),
                    # Carried from the folded side so `feasible` can see it. Without this the
                    # flag exists in the CSV and never reaches the filter.
                    "drift_repaired": row.get("drift_repaired") or "",
                    "scheme": row.get("scheme") or "",
                    "closure": row.get("closure") or "",
                    "upper3": row.get("upper3") or "",
                    "lower3": row.get("lower3") or "",
                    "len_x": row.get("len_x") or "",
                    "xstar_start": row.get("xstar_start") or "",
                    "f2": None if a_m[3] is None or not worst_off else a_m[3] / worst_off,
                    # The DIFFERENCE beside the ratio, same 18-nt window. Measured against
                    # Green's 168 it is the better of the two (+0.320 against +0.306), it needs
                    # no denominator -- the ratio spans 0.45 to 383.6 here against -0.17 to 0.82
                    # -- and it is architecture-neutral where the ratio is not: designs with a
                    # deliberately shut AUG bulge are 4.7% of the gating population and 89 of the
                    # top 100 by ratio, but only 5 of the top 100 by gain, with a median gain of
                    # 0.444 against everything else's 0.432.
                    "f2_gain": None if a_m[3] is None or worst_off is None else a_m[3] - worst_off,
                    "A_M_11": a_m[3],
                }

    rows: dict[str, dict] = {}
    for path in sorted(glob.glob(str(results / "obj*.csv"))):
        source = Path(path).stem
        if "smoke" in source or "panel" in source:
            continue
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                switch = row.get("switch")
                if not switch or switch in rows:
                    continue
                f1 = _num(row, "andness")
                extra = axes.get(switch)
                if f1 is None or extra is None:
                    continue
                access_a, access_b = _num(row, "access_a"), _num(row, "access_b")
                rows[switch] = {
                    **row,
                    **extra,
                    "source": source,
                    "f1": f1,
                    "barrier": _num(row, "barrier"),
                    "open_11f": _num(row, "open_11"),
                    "access": None if access_a is None or access_b is None else access_a + access_b,
                    "geom": GEOMETRY.get(len(switch), f"{len(switch)}nt"),
                    # (a_start, b_end, len_x) and NOT b_start -- see the module docstring.
                    "pair": f"{row.get('a_start')}/{row.get('b_end')}/{extra['len_x']}",
                    "pair_label": f"A@{row.get('a_start')} B->{row.get('b_end')} x{extra['len_x']}",
                }
    return list(rows.values())


def add_offtarget(rows: list[dict], results: Path) -> dict[str, int]:
    """Attach the off-target verdict, keyed on ``(a_start, b_end, len_x)`` so both geometries match.

    ``offtarget_scan.py`` screened **all 1,239 trigger pairs** and folded the 399 that carried a
    mimic worth folding: 23 FIRES, 104 BLOCKS, 272 inert, 840 not notable. One row per PAIR, since
    ``r2*``, ``x*`` and the A-binding site are all fixed once the pair is chosen.

    Wired in here so nobody has to remember to check it by hand. It was checked by hand once, on a
    panel whose long-overlap pair turned out to be a BLOCKS pair -- that is exactly the kind of
    thing a filter should catch and a person should not have to.
    """
    table: dict[tuple[int, int, int], dict] = {}
    path = results / "offtarget_folded.csv"
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    key = (int(row["a_start"]), int(row["b_end"]), int(row["len_x"]))
                except (KeyError, ValueError):
                    continue
                table[key] = {
                    "offtarget": row.get("verdict") or "not notable",
                    "offtarget_fires": row.get("fires") == "True",
                    "offtarget_blocks": row.get("blocks") == "True",
                }
    counts = {"joined": 0, "fires": 0, "blocks": 0}
    for row in rows:
        try:
            found = table.get((int(row["a_start"]), int(row["b_end"]), int(row["len_x"])))
        except (KeyError, ValueError):
            found = None
        # An unscreened pair is unknown, not clean -- but it is also not evidence of a problem,
        # so it is left None and `feasible` does not reject on it.
        row["offtarget"] = found["offtarget"] if found else None
        row["offtarget_fires"] = found["offtarget_fires"] if found else None
        row["offtarget_blocks"] = found["offtarget_blocks"] if found else None
        if found:
            counts["joined"] += 1
            counts["fires"] += bool(found["offtarget_fires"])
            counts["blocks"] += bool(found["offtarget_blocks"])
    return counts


#: Floor on ``hairpin_worst``: the weakest of the four duplexes the two hairpins are meant to
#: form in the OFF state must actually form.
#:
#: **0.3 is where the data has a gap, not a preference.** Over the 14,823 feasible designs the
#: distribution runs min 0.000, p10 0.767, median 0.908 -- so a floor at 0.3 removes **469
#: designs (3.2%)** whose intended stem is effectively absent, and touches nothing else. It is
#: the same discipline applied to ``d_off``: cut where the data shows a break, not at a round
#: number chosen for its own sake.
#:
#: It catches what ``d_off`` cannot. Two designs sat in the panel with ``main_pre`` and ``k1`` at
#: 0.000 and 0.003 -- no main stem at all -- while their ``d_off`` read 0.50 against a median of
#: 0.19, high but only 2.5x and not obviously broken. Both were Barrier picks, which follows: a
#: switch with no main stem has no barrier to cross.
HAIRPIN_FLOOR = 0.3


#: Columns `add_completions` lifts off completions*.csv onto each row.
#: Every column ``add_completions`` lifts out of ``completions*.csv``.
#:
#: **A column absent here is measured, written to disk, and invisible.** That is the third time this
#: shape of mistake has cost a run in this notebook: a name missing from ``complete_panel``'s
#: ON-tube guard is written as an empty cell, and a name missing from THIS tuple is written
#: correctly and then never joined. Both are silent. After the first full run of the two metrics
#: below, the files held 1,207 non-empty values per shard and the population reported **0.0%**
#: coverage.
#:
#: So: adding a metric to ``complete_panel`` is not finished until its name is in this tuple.
COMPLETION_COLUMNS = (
    "rbs11_open",
    "dG_rbs_linker",
    "r2_star_00",
    "hairpin_worst",
    "engaged_arm_11",
    "ied_rbs_linker_11",
    "ied_rbs_linker_00",
    "ied_rbs_linker_01",
    "ied_rbs_linker_10",
    "dG_arm_11",
    "dG_arm_00",
    # The joint cost of opening the Shine-Dalgarno, main_z and the AUG as one contiguous 20-nt
    # stretch -- the span the ribosome needs, which neither A_M (no RBS) nor rbs11_open (RBS only)
    # covered. Measured 10.4 to 11.3 kcal/mol in tube 00 against 1.5 to 3.9 in tube 11.
    "rbs_aug_open_11",
    "rbs_aug_open_00",
    # The duplex trigger A actually forms, keyed on the antiparallel diagonal so a contact in the
    # upper secondary stem is a different run rather than an extension of this one. len_x is not
    # this number and is not monotone in it.
    "eff_toehold_a",
    "eff_run_a_g0",
    "eff_run_a_g1",
    "eff_run_a_g2",
    "eff_run_lo",
    "eff_run_hi",
    # Not defaults in any metric set, and joined anyway so that a run which does ask for them is
    # not thrown away. `aug11_mean` earns its place as an INTEGRITY CHECK rather than as a metric:
    # it recomputes the stored `aug_11` from scratch and matched it at rho +1.000 with a worst
    # absolute difference of 0.0000, so a disagreement here means the stored column and the live
    # folder have drifted apart. `aug11_open` is the joint form of the same window (rho -0.941
    # against the mean) and `rbs11_mean` the mean form of `rbs11_open`.
    "aug11_mean",
    "aug11_open",
    "rbs11_mean",
    # main_z + aug, joint opening, all four tubes, plus worst-OFF minus ON. Reported only: it has
    # the same shape as `f1`, which scores -0.107 against Green's 168, so it ranks nothing until it
    # has been measured against that set.
    "aug_z_open_00",
    "aug_z_open_01",
    "aug_z_open_10",
    "aug_z_open_11",
    "aug_z_sep",
    # The run on trigger A's exposed landing site -- sec_z + x*, the 20 nt trigger B's binding
    # frees -- at each gap size, beside the site's own width. Reported, never a floor: over the 28
    # eligible pairs rho(landing, best A_M gain) is -0.117, so a floor would select against the
    # arm the panel ranks on.
    "land_site_nt",
    "land_run_g0",
    "land_run_g1",
    "land_run_g2",
)


def add_ied_gain(rows: list[dict]) -> int:
    """``ied_rbs_linker_00 - ied_rbs_linker_11``: IED's own ON/OFF separation.

    **Derived, never folded.** Both halves are completion columns at 100% coverage, and their
    difference is an identity -- computing it again would be a second number for one quantity.

    **Why the separation and not either half.** Measured across all three libraries, the two halves
    point in OPPOSITE directions: ``ied_off`` is +0.073 / +0.225 / +0.186 against the measured
    ON/OFF (a closed OFF state helps) and ``ied_on`` is -0.356 / -0.390 / +0.096 (an open ON state
    helps). That is what a gain needs, and it is why ``ied_gain`` is the **only** metric we hold
    that keeps a positive sign on all three libraries: **+0.345 / +0.495 / +0.116**. Every other
    candidate flips somewhere -- ``A_M_gain`` at -0.026 on VISTA, ``aug_z_gain`` at -0.107 on the
    168, ``separation`` negative everywhere.

    **Its within-cell spread is small and that is not a defect.** Median 0.0294, range 0.0787,
    against ``A_M_ratio``'s 4.15 -- because the window is a MEAN over 57 nt of which 39 are the
    fixed ``rbs_loop`` and ``linker`` domains, and those contribute almost no variance (median
    within-cell sd 0.0509 and 0.0166, against ~0.19 for each of ``main_z``, ``aug`` and
    ``main_pre``). Narrowing the window to the varying 18 nt would widen the spread and **destroy
    the arm**: ``1 - mean_unpaired`` over ``main_z + aug + main_pre`` is exactly ``1 - A_M``, so it
    would collapse into the arm it is meant to complement. The independence comes from the 39
    nucleotides that are fixed in SEQUENCE but not in STRUCTURE. Spearman is scale-free, so a
    narrow range ranks as validly as a wide one.
    """
    joined = 0
    for row in rows:
        off, on = row.get("ied_rbs_linker_00"), row.get("ied_rbs_linker_11")
        row["ied_gain"] = None if off is None or on is None else off - on
        joined += row["ied_gain"] is not None
        # The same subtraction against the WORST of the three OFF tubes, which is the rule
        # everywhere else here and the one `ied_gain` does not follow. `max`, because the IED is a
        # paired fraction: the most-paired OFF state is the shut one, so it is the easiest to beat
        # and therefore the honest baseline. `None` until `complete_panel --metrics ied_off` has
        # run; the command is in that module's docstring.
        tubes = [row.get(f"ied_rbs_linker_{state}") for state in ("00", "01", "10")]
        present = [v for v in tubes if v is not None]
        row["ied_gain_worst"] = None if on is None or len(present) < 3 else max(present) - on
    return joined


def add_completions(rows: list[dict], results: Path) -> int:
    """Attach ``rbs11_open`` from ``complete_panel.py``, if it has been run.

    Reported, not thresholded, for the same reason ``d_off`` is: nothing published fixes a bar on
    how open a Shine-Dalgarno must be, and the observed range is 0.03 to 4.84 kcal/mol with a
    median of 0.45 -- a cut anywhere in that would be a number I made up. It sits on the card so a
    design whose RBS is occluded in the ON state can be seen and rejected by eye.
    """
    table: dict[str, dict[str, float]] = {}
    for path in sorted(results.glob("completions*.csv")):
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                switch = row.get("switch")
                if not switch:
                    continue
                for field in COMPLETION_COLUMNS:
                    value = row.get(field)
                    if value not in (None, ""):
                        try:
                            table.setdefault(switch, {})[field] = float(value)
                        except ValueError:
                            continue
    for row in rows:
        # Every completion column, not a hand-maintained pair of them: a column computed by
        # complete_panel and not lifted here is silently absent from `feasible`, which is how
        # `engaged_arm_11` could be measured on the panel's own cards and still never filter.
        found = table.get(row["switch"], {})
        for field in COMPLETION_COLUMNS:
            # setdefault, not assignment: `r2_star_00` also arrives from `load` for the two runs
            # whose folded CSVs carry `A_r2_star_00`, and a plain assignment would overwrite a
            # real measurement with None wherever the completion pass has not reached yet.
            value = found.get(field)
            if value is not None or field not in row:
                row[field] = value
    return sum(1 for r in rows if r.get("hairpin_worst") is not None)


#: Accessibility columns joined onto every design, each keyed on (window start, role).
#:
#: ``l_green`` is ``1 - sed_w0`` over the exact binding window, folded as an **isolated slice**.
#: ``l_full_w25`` is the mean per-base unpaired probability over that window **plus 25 nt of flank
#: each side**, read from one fold of the **whole 711-nt transcript** -- the form that measured
#: +0.317 against VISTA's 189 switches, where the isolated-slice ``mfe_w25`` managed +0.011.
#:
#: Those are two differences at once, the context and the flank, and over the same 2,478 windows the
#: two forms of the *same* window agree at only **rho +0.47**. So both are joined rather than one
#: replacing the other: the choice of which gates a pair is then made with both numbers on the row.
ACCESS_COLUMNS = (
    "l_green",
    "l_full_w0",
    "l_full_w10",
    "l_full_w25",
    "l_full_w50",
    # RNAplfold, through the engine's own FoldProfiler. The established measure for
    # target-site accessibility and the only one of the three with a mechanism behind its
    # window: a sliding local window with a capped pair span, which is how a long mRNA
    # actually folds -- co-transcriptionally, 5' to 3', with local structure persisting. The
    # other two assume the molecule reaches equilibrium over all 711 nt.
    "l_local",
)


#: Pairs that hold a duplex. The G-U wobble is included on the trigger side on purpose: it is
#: weaker than G-C but it is a pair, and the whole point of the wobble level is that trigger A keeps
#: the position.
_HOLDS = frozenset({("A", "U"), ("U", "A"), ("G", "C"), ("C", "G"), ("G", "U"), ("U", "G")})

#: How many of the stem's bottom 3 a forced ``lower3`` level may cost trigger A and still be used.
#:
#: **Set to 1 because the binary reading was wrong.** "Does this level break the grip" was measured
#: as a yes/no and reported as ``SSW`` breaking it in 483 of 514 designs, which made the whole class
#: of forced levels look unusable. Counted properly, the cost is almost always **one nucleotide**:
#:
#:     lower3            n   0 broken   1 broken   2 broken   3 broken
#:     SSW             514         31        352        129          2
#:     SWS             484         38        264        146         36
#:     SWW             209         65        113         31          0
#:     SSS             133          0         95         38          0
#:     wobble_GU       368        368          0          0          0
#:     trigger_derived 344        344          0          0          0
#:
#: SSW costs exactly one base in 68% of its designs and nothing in 31 of them; 2 of 514 lose all
#: three. Against an effective toehold of 15 to 20 contiguous base pairs, one lost pair is a small
#: price, and these designs measured well on the objectives -- which is why excluding the class
#: wholesale was throwing away real candidates for a number that was never counted.
#:
#: 2 and 3 stay out: two is a 2-nt lesion in a 9-nt arm, and the levels that reach it are the ones
#: that replace the stem wholesale rather than meet the trigger.
GRIP_BREAK_MAX = 1


def grip_broken(switch: str, trigger_a: str) -> int | None:
    """How many of the stem's bottom 3 base pairs trigger A cannot form on this design.

    Aligned by the best 9-nt match to ``main_pre_star``'s reverse complement rather than a fixed
    offset, because the ``lower3`` levels break the exact match on purpose -- an exact search finds
    nothing on most designs. ``None`` when the design is too short to have the domains.
    """
    try:
        star = _oe_domains(switch)["main_pre_star"][0]
    except (KeyError, IndexError, ValueError):
        return None
    star9 = switch[star : star + 9]
    if len(star9) < 9 or len(trigger_a) < 9:
        return None
    probe = _revcomp(star9)
    best, offset = 99, 0
    for start in range(len(trigger_a) - 9 + 1):
        window = trigger_a[start : start + 9]
        count = sum(1 for x, y in zip(probe, window, strict=False) if x != y)
        if count < best:
            best, offset = count, start
    segment = trigger_a[offset : offset + 9]
    return sum(1 for i in range(3) if (star9[i], segment[8 - i]) not in _HOLDS)


def add_grip(rows: list[dict], transcript: str) -> int:
    """Attach ``lower3_broken`` to every row. Pure string work -- no folding, no side table."""
    joined = 0
    for row in rows:
        try:
            trigger_a = transcript[int(row["a_start"]) : int(row["a_end"])]
        except (KeyError, TypeError, ValueError):
            row["lower3_broken"] = None
            continue
        row["lower3_broken"] = grip_broken(row["switch"], trigger_a)
        joined += row["lower3_broken"] is not None
    return joined


def lower3_ok(row: dict) -> bool:
    """Is this design's lower3 acceptable?

    ``wobble_GU`` and ``trigger_derived`` always pass -- measured, they break **nothing**, 0 of 712.
    A forced level passes when it costs trigger A at most ``GRIP_BREAK_MAX`` of the bottom 3.
    An unmeasured design passes: unmeasured is not failed, as everywhere else here.
    """
    level = row.get("lower3") or ""
    if level in ("wobble_GU", "trigger_derived"):
        return True
    broken = row.get("lower3_broken")
    return broken is None or broken <= GRIP_BREAK_MAX


def add_accessibility(rows: list[dict], results: Path) -> int:
    """Attach ``l_green`` from ``trigger_accessibility.py``, keyed so both geometries share it.

    Keyed on (window start, role): the naive build's windows are 36/50 nt and Kim's 35/49, but the
    18th nucleotide is present in the Kim context either way and the endogenous window being probed
    is far wider than 1 nt. Two designs from the same trigger-window overlap with the same A/B
    roles are reaching the same place in the same transcript, so they get the same number.
    """
    table: dict[tuple[int, str], dict[str, float]] = {}
    # Two files: ``trigger_accessibility.py``'s table and ``accessibility_s1.py``'s full-transcript
    # forms. A later file FILLS columns an earlier one lacks instead of replacing the whole row, so
    # adding a partial second file adds information rather than deleting the first one's.
    for name in ("accessibility.csv", "accessibility_s1.csv", "accessibility_local.csv"):
        path = results / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                start, role = row.get("start"), (row.get("role") or "").strip()
                if not start or role not in ("A", "B"):
                    continue
                try:
                    entry = table.setdefault((int(start), role), {})
                except (ValueError, TypeError):
                    continue
                for column in ACCESS_COLUMNS:
                    try:
                        entry[column] = float(row[column])
                    except (KeyError, ValueError, TypeError):
                        continue
    joined = 0
    for row in rows:
        try:
            a_entry = table.get((int(row["a_start"]), "A")) or {}
            b_entry = table.get((int(row["b_start"]), "B")) or {}
        except (KeyError, ValueError):
            a_entry = b_entry = {}
        # Every column reduced the same way: the MINIMUM over the pair's two windows, because a pair
        # is only as reachable as its harder window. A product would read "both moderately hard"
        # (0.5 x 0.5) as worse than "one impossible" (0.3 x 1.0), and the second is the blocked one.
        # None means "never measured", not "inaccessible" -- `feasible` must not reject on it.
        for column in ACCESS_COLUMNS:
            one, two = a_entry.get(column), b_entry.get(column)
            row[column] = None if one is None or two is None else min(one, two)
        joined += row["l_green"] is not None
    return joined


#: When non-empty, only these ``lower3`` levels are feasible. Empty by default.
#:
#: **A trade, and it is the panel's shape that pays.** Measured over the 1,367 gating designs,
#: keeping only ``wobble_GU`` and ``trigger_derived`` leaves 482 (35%), lifts the median
#: ``engaged_arm_11`` from 0.777 to 0.949, and loses nothing at the top -- best A_M ratio 383.567,
#: best A_M gain 0.822, best opening SEP -14.460 all survive. What it costs is choice: eligible
#: trigger pairs fall from **25 to 6**, which is most of the room the pair requirements (both
#: geometries, three per cell, disjoint windows, a long overlap) need.
#:
#: So it is a run-time option rather than a standing filter, set by ``--lower3``. A panel built
#: under it is smaller by construction, and that is informative rather than a failure: a few
#: designs whose lower three bases are all trigger-derived or wobble is exactly the set the bench
#: can use to ask whether the forced levels were ever worth having.
LOWER3_KEEP: frozenset[str] = frozenset()

#: Transcript positions corrected after the sweep had already folded against them.
#:
#: All six are at codon base 3, so the protein is unchanged -- but a switch's trigger-derived
#: domains (``r2*``, ``sw_x``, ``x*``, ``main_pre_star``, ``k1_star``) are the reverse complement
#: of the window as it was, so a design covering one of these encodes a base that is not in the
#: transcript. Its folding energies, A_M values and barrier were all computed on that mismatch,
#: and no rescoring fixes it: the switch sequence itself would have to be rebuilt.
#:
#: **53.9% of the sweep is affected** -- 31,735 of 58,876 designs across 633 of 1,043 trigger
#: pairs -- which is why this is a filter and not a footnote. ``transcript_drift.py`` recomputes
#: the list from git rather than trusting this constant, and prints which designs and pairs are
#: hit; this is the operative copy so that scoring needs no git call.
DRIFTED_POSITIONS = frozenset({62, 356, 434, 482, 578, 590})


def covers_drift(row: dict) -> list[int]:
    """Corrected positions inside either trigger window of this design, 0-based.

    **Empty for a repaired design, and the flag is the only way to say so.** A patch corrects the
    SWITCH; it does not move the trigger windows, so a repaired design's windows still cover the
    corrected position and this would reject it forever. ``drift_fold.py`` writes
    ``drift_repaired=1`` beside a freshly computed fold of a sequence ``drift_repair.py`` produced,
    and ``drift_repair.py --verify`` re-derives every patch from both transcripts, so the flag is
    not settable by hand on an unchecked sequence.
    """
    if str(row.get("drift_repaired") or "").strip() in ("1", "True", "true"):
        return []
    spans = (
        (int(row["a_start"]), int(row["a_end"])),
        (int(row["b_start"]), int(row["b_end"])),
    )
    return sorted(p for p in DRIFTED_POSITIONS for lo, hi in spans if lo <= p < hi)


def out_of_frame_augs(switch: str) -> int:
    """AUGs between the RBS loop and the real start that are NOT in the real start's frame.

    Green 2014 S6.3 screened his designs for in-frame stops; this is the matching hazard on the
    other side. An AUG the ribosome reaches before the real one gives it a second place to
    initiate, and out of frame with the real start what it then translates is not the reporter.
    An *in*-frame upstream AUG only extends the protein by a few residues, so only the
    out-of-frame ones are rejected.

    Measured before it became a filter: it rejects **519 of 3,741** gating designs (13.9%), while
    in-frame stops reject 0 -- those were already clean. The rest of Green's S6.2 list (``AAAA``
    through ``YYYYYY``) is NOT applied, and that is a measurement rather than an omission: his
    constraints bound sequences NUPACK was free to generate, while our secondary hairpin is the
    reverse complement of an mCherry window. ``SSSSSS`` alone appears in 79.6% of our designs
    there and cannot be edited without changing which trigger we detect, so it is a fact about
    the trigger pair, not a design fault. ``sequence_screen.py`` reports all ten.
    """
    dom = domains(switch)
    start, aug = dom["rbs_loop"][0], dom["aug"][0]
    return sum(
        1
        for index in range(start, aug - 2)
        if switch[index : index + 3] == "AUG" and (aug - index) % 3
    )


def feasible(rows: list[dict]) -> list[dict]:
    """The one filter set every objective ranks inside, so the arms differ only in ranking."""
    keep = []
    for row in rows:
        if row["open_11f"] is None or row["open_11f"] > ON_CEILING:
            continue
        if row["scheme"] in DEAD_SCHEMES:
            continue
        if row.get("aug_11") is not None and row["aug_11"] <= AUG_FLOOR:
            continue
        if row.get("lock") is not None and row["lock"] < LOCK_FLOOR:
            continue
        if row.get("lock01") is not None and row["lock01"] < LOCK01_FLOOR:
            continue
        # FIRES is a categorical disqualification: a gate that opens on a decoy with no real
        # trigger is wrong whatever else it scores, and no ordering of a continuous score can say
        # "disqualified". BLOCKS costs ON signal rather than inventing it, so it is carried as a
        # flag on the row and left to the reader.
        if row.get("offtarget_fires"):
            continue
        # A design whose stem was never measured keeps None and is NOT rejected: unmeasured is
        # not failed, and complete_panel.py has not necessarily been run.
        if row.get("hairpin_worst") is not None and row["hairpin_worst"] < HAIRPIN_FLOOR:
            continue
        # Strictly greater than the floor, because the floor IS zero: the rejected population
        # is the one sitting exactly at 0.000, and `>= 0.0` would reject nothing.
        if row.get("engages_stem_mfe") is not None and row["engages_stem_mfe"] <= STEM_MFE_FLOOR:
            continue
        if row.get("engaged_arm_11") is not None and row["engaged_arm_11"] < ARM_FLOOR:
            continue
        # An unmeasured window is not a failed one: rejecting on None would quietly delete every
        # design whose windows accessibility_s1.py has not reached.
        #
        # `l_green` is still joined and still shown -- it is just no longer what gates a design.
        # Both numbers on the row is the point: the two disagree (rho +0.195), so a reader can see
        # which definition a rejection came from instead of taking the filter's word for it.
        if row.get("l_local") is not None and row["l_local"] <= L_LOCAL_FLOOR:
            continue
        if out_of_frame_augs(row["switch"]):
            continue
        if covers_drift(row):
            continue
        # Two gates, and they answer different questions. LOWER3_KEEP is a blunt name filter a
        # caller asks for; `lower3_ok` is the measured one -- a forced level is kept when it costs
        # trigger A at most one of the bottom 3, which is what SSW does in 68% of its designs.
        if LOWER3_KEEP and (row.get("lower3") or "") not in LOWER3_KEEP:
            continue
        if not lower3_ok(row):
            continue
        row["codons"] = early_codons(row["switch"])
        row["rare"] = [c for c in row["codons"] if c in RARE_CODONS]
        if row["rare"]:
            continue
        keep.append(row)
    return keep


#: Weight on the FIRST term of the two-term aggregates, the Barrier taking the remainder.
#:
#: **0.50 does not mean equal influence, and that is measured.** Percentiles equalise a term's
#: RANGE but not its spread: over the ranked population sd(pct_A_M) is 20.4 against
#: sd(pct_Barrier) 29.0, because the A_M ratio is heavy-tailed and its percentiles bunch while the
#: barrier's spread out. At 0.50 the aggregate correlates **+0.275** with the A_M ratio and
#: **+0.765** with the barrier -- so "equal weights" was silently a 0.28/0.77 split that nobody
#: chose, and ``combined`` was the barrier under another name.
#:
#: Swept over the whole population, the balance point is **0.60**, giving +0.545 against +0.536.
#:
#: **This is not a weight fitted to data in the forbidden sense.** No bench number enters it: it is
#: derived from the spread of the design population, exactly like the percentile transform it sits
#: on top of. The standing rule forbids fitting to measured ON/OFF, of which there is too little.
#: The cost is that it moves with the population, so the population size is printed with the panel.
COMBINED_WEIGHT = 0.60


def add_variant_leak(rows: list[dict], results: Path) -> int:
    """Join ``andness_variant`` and the three leaks from ``variant_leak.csv``.

    **This is the AND-ness the bench will measure, and it is not the one the sweep ranks on.**
    The sweep scores state 10 by *omitting* trigger B; the experiment realises it with a transcript
    whose B window is synonymously recoded, so a full-length mRNA is still in the tube. Measured
    over all 1,317 gating designs, that costs **2.2 kcal/mol of AND-ness at the median** (-4.94 in
    the sweep against -2.74 on the transcripts), **8.0% of them have no gate left at all**, and the
    two quantities agree at only **rho +0.374** -- so the sweep's AND-ness explains about an eighth
    of the variance in the thing that will actually be observed.

    Produced by ``variant_leak.py``: four folds per design, 39 minutes over the gating set.
    Unmeasured designs keep ``None`` and are not rejected.
    """
    path = results / "variant_leak.csv"
    if not path.exists():
        return 0
    table: dict[str, dict[str, float | None]] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            entry: dict[str, float | None] = {}
            for field in ("andness_variant", "leak_10", "leak_01", "leak_00"):
                raw = row.get(field)
                entry[field] = None if raw in (None, "") else float(raw)
            table[row["switch"]] = entry
    joined = 0
    for row in rows:
        found = table.get(row["switch"], {})
        for field in ("andness_variant", "leak_10", "leak_01", "leak_00"):
            row[field] = found.get(field)
        joined += row.get("andness_variant") is not None
    return joined


def add_stem_mfe(rows: list[dict], results: Path) -> int:
    """Join ``engages_stem_mfe`` from ``stem_opens_mfe.csv``, keyed on the switch sequence.

    Produced by ``stem_opens_mfe.py``, which costs one cofold of the 11 tube per design -- 2.3
    minutes over the whole feasible set, measured. Kept as a side table rather than folded here
    because ``population`` is called by every tool on every run.

    A design the table does not mention keeps ``None`` and is **not** rejected: unmeasured is not
    failed, and the table is only as current as the last run of that script.
    """
    path = results / "stem_opens_mfe.csv"
    if not path.exists():
        return 0
    table: dict[str, float | None] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            raw = row.get("engages_stem_mfe")
            table[row["switch"]] = None if raw in (None, "") else float(raw)
    joined = 0
    for row in rows:
        value = table.get(row["switch"], None)
        row["engages_stem_mfe"] = value
        joined += value is not None
    return joined


def population(results: Path, *, quiet: bool = True) -> list[dict]:
    """Load, join every side table, filter to feasible and add percentiles. The one definition.

    **There were two, and they disagreed by a factor of two.** ``main`` joined accessibility,
    completions and off-target *before* ``feasible``, so the three filters that read those
    columns -- ``l_green``, ``hairpin_worst`` and an off-target FIRES pair -- could fire, and it
    got **7,568**. The report's data builder called ``feasible(load(results))`` with no joins, so
    those three filters were structurally unable to fire, and it got **14,823** while its own
    comment claimed the two sets were identical.

    What that cost: every statistics bar on every card was drawn against a population twice the
    size of the one the percentile chips beside it came from, and the "best in sweep" rows were
    chosen from a set that still contained designs the panel itself rejects -- so a row presented
    as the best available could be one excluded for failing a filter.

    A join is not optional here. ``feasible`` reads columns that only a join supplies, and a
    missing column reads as "nothing to filter on" rather than as an error, which is exactly the
    silent-pass failure the house rules are about.
    """
    rows = load(results)
    if not rows:
        return []
    joined = add_accessibility(rows, results)
    got = add_completions(rows, results)
    off = add_offtarget(rows, results)
    gained = add_ied_gain(rows)
    stem_mfe = add_stem_mfe(rows, results)
    bench = add_variant_leak(rows, results)
    # Before `feasible`, because `lower3_ok` reads the column it writes. Needs the transcript and no
    # folding, so it costs a file read and some string work on 60k rows.
    grip = 0
    fasta = Path(__file__).resolve().parent / "mCherry_original.txt"
    if fasta.exists():
        from full_sweep import read_fasta

        grip = add_grip(rows, read_fasta(fasta))
    if not quiet:
        print(f"  l_green joined for {joined:,} of {len(rows):,} scored designs")
        print(f"  lower3 grip counted for {grip:,} designs (forced levels kept at <= 1 broken)")
        print(f"  completions joined for {got:,} designs: RBS(11) reported, hairpin filtered")
        print(f"  ied_gain derived for {gained:,} designs (ied_00 - ied_11)")
        print(
            f"  engages_stem_mfe joined for {stem_mfe:,} designs "
            f"(main hairpin open in the MFE of tube 11)"
        )
        print(f"  andness_variant joined for {bench:,} designs (the AND-ness the bench will see)")
        print(
            f"  off-target joined for {off['joined']:,}: {off['fires']:,} on a FIRES pair "
            f"(excluded), {off['blocks']:,} on a BLOCKS pair (flagged)"
        )
    live = feasible(rows)
    add_percentiles(live)
    return live


def add_percentiles(rows: list[dict]) -> None:
    """Percentile of each term inside this feasible set, 100 = best; f4 and f5 are their means.

    **``access`` is measured and reported but is NOT a term in any objective**, and that is a
    measurement rather than a preference. ``access`` is the cost of opening the two trigger
    windows on the endogenous transcript -- a property of the **trigger pair**, not of the
    design. Measured on this sweep it is *exactly* constant inside all **324** (pair, geometry)
    cells, spread 0.000000 kcal/mol, so as a term in a percentile mean it is a constant offset:
    ``(pct_f2 + pct_barrier + pct_access) / 3`` and ``(pct_f2 + pct_barrier) / 2`` rank the
    designs in a cell **identically**. Checked directly: of the 14 cells where the two picks
    differ, **0** are a genuine reordering and all 14 are ties broken differently.

    So the term could never do what it looked like it was doing. What it *did* do was decide
    which trigger **pairs** scored well, silently, inside a score presented as design quality --
    and only f5 carried it, so the three objectives were not comparable. It now selects pairs
    explicitly in ``pick``, which is where a pair-level quantity belongs.

    The empirical cost is small and the two libraries disagree about its sign. Percentile
    aggregates against Green's measured ON/OFF:

                                  Green 168    Green 13
        f2 alone                     +0.306      +0.698
        Barrier alone                +0.179      +0.280
        f2 + Barrier   (f5 now)      +0.345      +0.644
        f2 + Barrier + access        +0.366      +0.591

    On the 168 the third term is worth +0.021; on the 13 it **costs** 0.053, where f2 alone beats
    every aggregate. And Green's third term is not even the same quantity: there ``access`` is
    proxied by ``dG_open(ON)``, a **design** property, so his data never validated a pair-level
    accessibility term in the first place.
    """
    for key, lower_is_better in (
        ("f1", True),
        ("barrier", True),
        ("access", True),
        ("f2", False),
        ("f2_gain", False),
    ):
        values = sorted(v for r in rows if (v := r.get(key)) is not None)
        n = len(values)
        for row in rows:
            value = row.get(key)
            if value is None or not n:
                row[f"pct_{key}"] = None
                continue
            below = 100.0 * sum(1 for v in values if v < value) / n
            row[f"pct_{key}"] = round(100.0 - below if lower_is_better else below, 1)
    for row in rows:
        for name, first in (("f4", "f1"), ("f5", "f2")):
            parts = [row.get(f"pct_{k}") for k in (first, "barrier")]
            row[name] = (
                None
                if any(p is None for p in parts)
                else round(COMBINED_WEIGHT * parts[0] + (1.0 - COMBINED_WEIGHT) * parts[1], 1)
            )


#: All four objectives, and the duplicates they produce are **data rather than waste**. A panel
#: row is not a construct: only distinct designs get synthesised, so 24 rows are 14 constructs
#: and the repeats cost nothing at the bench while recording which objectives agreed.
#:
#: How often each pair picks the same design, over **470 cells** with at least 4 feasible
#: designs each:
#:
#:     f1      == f2        78.7%
#:     f1      == f4        66.6%
#:     f2      == f4        57.7%
#:     Barrier == f4        43.0%
#:     f1      == Barrier   22.6%
#:     f2      == Barrier   20.6%
#:
#: So they form a **gradient of similarity**, not disjoint groups: the barrier is the most
#: distinct objective, f1 and f2 the most alike, and f4 sits between f1 and the barrier while
#: leaning towards f1. That is what percentile aggregation is supposed to produce, and it
#: confirms the aggregation works: within cells, ``Spearman(f4, f1) = -0.811`` against
#: ``Spearman(f4, barrier) = -0.602``, and ``pct_f1`` spreads more inside a cell (sd 12.8) than
#: ``pct_barrier`` (9.5).
#:
#: **An earlier version of this comment claimed "two families that never meet", with
#: f1 == Barrier at 0%.** That was measured on **6** cells and was noise: the real figure is
#: 22.6%. Read every agreement figure here against its cell count, and note that the 11 cells
#: with >=15 designs give Barrier == f4 at 72.7% -- noise in the other direction.
#:
#: Each key returns a value where SMALLER is better, so every arm is a ``min``.
#: **f1 is kept in the panel although it scores worst against Green.** Measured on his 168
#: switches, Spearman against the measured ON/OFF, signed so positive means the objective is
#: right:
#:
#:     f5   pct(f2, Barrier, access)   +0.366    leave-one-out [+0.355, +0.384]
#:     f2   A_M ratio                  +0.306                 [+0.294, +0.323]
#:     f4   pct(f1, Barrier, access)   +0.213                 [+0.200, +0.231]
#:     Barrier                         +0.179                 [+0.165, +0.195]
#:     f1   energy difference          -0.107                 [-0.125, -0.093]
#:
#: Reproduce with ``objective_vs_green.py``, which is where these numbers come from.
#:
#: The leave-one-out ranges never straddle zero, so the ordering is not one outlier. f1's sign
#: is **wrong**: on Green's data a larger open-energy difference goes with a *worse* measured
#: ON/OFF. f4, the aggregate that leans on f1 (63.8% agreement), sits below f2 -- not at zero,
#: but below the single term it was built to improve on -- while f5 with f2 in f1's place is the
#: best of the five.
#:
#: Two caveats keep f1 as a row rather than deleting it:
#:
#: 1. Green's switches are **single-input**, so "AND-ness" does not exist there. f1 was
#:    evaluated as its two-state analogue ``dG_open(ON) - dG_open(OFF)``, which is the same
#:    quantity one trigger short. That is a fair analogue, not the same function.
#: 2. f1 is the quantity the design theory recommends. A wrong sign on an analogue is a reason
#:    to **test** it at the bench, which is what a panel row is for, not to assume it.
#: The names are the ones a reader can act on, not the working labels the investigation used.
#: ``f2`` is the A_M ratio and ``f5`` is the combination of the other two, so they say that. The
#: underlying columns keep their short keys (``r["f2"]``, ``r["f5"]``) because the scorer writes
#: them and renaming a stored column would break every shard already on disk.
#: How much of a cell's best A_M ratio a design must keep to stay in ``combined``'s pool.
#:
#: **Measured against the weighted percentile mean it replaces.** Over all 292 cells, picking by
#: the weighted mean gave up more than half the achievable A_M ratio -- mean 15.8 down to 7.3, 85%
#: of each cell's ceiling -- to buy 1.6 kcal/mol of barrier. At 0.80 the constraint keeps a mean of
#: 15.2, which is 95% of the ceiling and 96% of what the A_M arm itself achieves, and still gains
#: 0.38 kcal/mol on average (max 12.2) while reordering 154 of the 292 cells.
#:
#: The cause is the heavy tail: a percentile mean reads an A_M ratio of 300 and one of 10 as seven
#: percentile points apart, while in ratio space they are 30x apart. The constraint works in the
#: space the quantity lives in.
#:
#: 0.80 rather than 0.90 for pool size: at 0.80 a cell keeps a median of 3 designs to order by
#: barrier and only 58 of 292 are left with a single option, against 90 of 292 at 0.90. A rule that
#: cannot choose is not a ranking arm. Not fitted to any bench number -- it is a declared tolerance
#: on a quantity the design population defines, like the percentile transform it replaces.
EPSILON = 0.80


def epsilon_combined(cell: list[dict]) -> object:
    """``combined``: lowest barrier among designs holding EPSILON of the cell's best A_M ratio.

    A *cell-relative* arm, so unlike the other two it cannot be written as a key on one row --
    it needs the cell to know the ceiling. ``cell_picks`` therefore passes the cell to every
    arm and the row-wise arms ignore it.
    """
    usable = [r for r in cell if r.get("f2") is not None and r.get("barrier") is not None]
    if not usable:
        return lambda r: float("inf")
    ceiling = max(r["f2"] for r in usable)
    kept = {id(r) for r in usable if r["f2"] >= EPSILON * ceiling}
    # Outside the pool, order by how far short of the tolerance the design falls, so the arm
    # still returns something sane if a cell's whole pool is unmeasurable.
    return lambda r: (
        r["barrier"] if id(r) in kept else float("inf") if r.get("f2") is None else 1e6 - r["f2"]
    )


ARMS: dict[str, object] = {
    "opening SEP": lambda r: r["f1"],
    "A_M ratio": lambda r: -r["f2"] if r["f2"] is not None else float("inf"),
    "A_M gain": lambda r: -r["f2_gain"] if r.get("f2_gain") is not None else float("inf"),
    # Green's own strongest category, in VISTA's statistic. LOWER is better.
    "IED rbs-linker": lambda r: (
        r["ied_rbs_linker_11"] if r.get("ied_rbs_linker_11") is not None else float("inf")
    ),
    # The opening energy over the 18-nt A_M window rather than the 31-nt W_rank, so an energy
    # and an accessibility finally share a span. LOWER is better.
    "dG arm (ON)": lambda r: r["dG_arm_11"] if r.get("dG_arm_11") is not None else float("inf"),
    # Green's own predictor, with HIS sign: less negative is better. A strongly negative
    # dG_RBS-linker is a stiff refolded stem in front of the ribosome, which he reports
    # correlating with LOWER dynamic range -- so the arm maximises it.
    "dG rbs-linker": lambda r: (
        -r["dG_rbs_linker"] if r.get("dG_rbs_linker") is not None else float("inf")
    ),
    # IED's ON/OFF separation. HIGHER is better: the OFF state more paired than the ON state.
    # The only metric we hold with a positive sign on all three measured libraries.
    "IED gain": lambda r: -r["ied_gain"] if r.get("ied_gain") is not None else float("inf"),
    # The same against the WORST of the three OFF tubes. Unusable until
    # `complete_panel --metrics ied_off` has run -- it returns inf for every row until then, so an
    # arm selecting on it would find nothing rather than silently selecting on a partial column.
    "IED gain (worst OFF)": lambda r: (
        -r["ied_gain_worst"] if r.get("ied_gain_worst") is not None else float("inf")
    ),
    "Barrier": lambda r: r["barrier"] if r["barrier"] is not None else float("inf"),
    "combined (SEP)": lambda r: -r["f4"] if r["f4"] is not None else float("inf"),
    # Built per cell, not per row -- see `epsilon_combined`.
    "combined": epsilon_combined,
}

#: The arms that need the whole cell to build their key, rather than reading one row.
CELL_RELATIVE = frozenset({"combined"})

#: **The three that rank: the A_M ratio, the Barrier, and their combination.** ``f1`` is not here
#: and neither is ``combined (f1)``, and both omissions are the same measurement -- f1 scores
#: **-0.107** against Green's 168 and the aggregate that leans on it lands at **+0.213**, below
#: the A_M ratio's own +0.306.
#:
#: f1 is not deleted, it is **demoted to the floor**. The measurement says f1 is a poor ranker
#: *among designs that already gate*; it does not say AND-ness is meaningless. ``GATING`` is
#: exactly that floor, so f1 keeps the job it survives -- "is this a gate at all" -- and the
#: ordering above the floor goes to the three objectives that point the right way.
#:
#: ``combined`` replaces ``combined (f1)`` outright: same percentile construction, the A_M ratio
#: where f1 stood. Keeping both would be keeping a known-worse copy of the same thing, so the
#: f1 version is shown on cards and ranks nothing.
#: ``A_M gain`` is on the panel so the ratio-versus-difference choice can be made by eye rather
#: than from the two correlation numbers, which are 0.014 apart on Green's 168 and disagree on his
#: 13. Where the two arms pick the SAME design the choice does not matter; where they diverge, the
#: divergence is the thing to look at. It is a ranking arm, not a replacement: nothing has been
#: removed, so every earlier row on the page still means what it meant.
#: Every arm the panel shows a row for. Six now, because the choice between them is yours to make
#: by eye and an arm that is not on the page cannot be compared.
#:
#: **The cross-correlations say which ones are redundant**, measured over the 1,367 gating designs:
#:
#:     IED vs A_M gain      -0.750   they agree strongly (IED is lower-better)
#:     IED vs Barrier       +0.161   nearly independent
#:     Barrier vs A_M gain  -0.113   nearly independent
#:     dG arm vs Barrier    +0.342
#:     IED vs dG arm        +0.522
#:
#: So **IED cannot replace the Barrier as a third arm**: it duplicates A_M gain at 0.75 while the
#: Barrier is almost orthogonal to it at 0.11, and swapping them would collapse the panel to two
#: arms that agree. IED is nonetheless the better single predictor on both Green libraries (+0.356
#: and +0.390 against the Barrier's +0.179 and +0.280). Those two facts point opposite ways and
#: only the bench can settle it, which is why both are on the page.
RANKING_ARMS: dict[str, object] = {
    name: ARMS[name]
    for name in (
        "A_M ratio",
        "A_M gain",
        "IED rbs-linker",
        "dG rbs-linker",
        "dG arm (ON)",
        "Barrier",
        "combined",
    )
}


#: The arms the six-construct panel builds from: two trigger pairs x these three = six rows.
#:
#: **Chosen for how little they overlap, measured on our own designs.** Over the 86 cells with four
#: or more designs, the share of cells where two arms pick the SAME design:
#:
#:     A_M ratio  <-> dG arm (ON)   35%
#:     IED gain   <-> A_M ratio     37%
#:     IED gain   <-> dG arm (ON)   51%
#:     IED gain   <-> A_M gain      62%   <- rejected for this
#:     A_M gain   <-> A_M ratio     62%
#:
#: ``A_M gain`` is out despite being well-supported externally, because ``ied_gain`` ranks it at
#: **rho +0.929 within a cell** -- the two would spend four of six constructs on one question.
#: ``dG rbs-linker`` is out for a measured reason as well: it is an OFF-state MFE of an isolated
#: subsequence, and two designs in one cell with an identical -7.20 differ 2.4x in how far the stem
#: opens in tube 11, so it is blind to the only difference between them.
#:
#: ``dG arm (ON)`` is the ON-state opening energy. Note that it is ``rho +1.0000`` with ``open_11``,
#: the ON ceiling -- the same quantity over 18 nt instead of 15. That is **not** a reason to drop
#: the ceiling: a ceiling is a calibrated bound that removes designs whose AND-ness is a ratio
#: between two near-zeros, and an arm only orders the survivors. Dropping it readmitted designs at
#: open_11 up to 32 when we measured the rescued set.
#:
#: The cost of the ceiling is visible, though: it leaves ``dG arm (ON)`` a median within-cell range
#: of 0.87 kcal/mol out of 0.398 to 3.992 overall. It still separates -- no cell is flat.
PANEL_ARMS = ("IED gain", "A_M ratio", "dG arm (ON)")


#: Require each chosen pair's three arms to pick three DIFFERENT designs.
#:
#: **Off by default, and the trade is measured.** Ranking on the three arms, the two best pairs are
#: ``645/251/4`` (worst percentile 11.7) and ``414/361/4`` (13.3), and on both of them ``IED gain``
#: and ``dG arm (ON)`` land on the same design -- so six bench slots buy **four** designs. Of the
#: 60 candidate pairs in the Kim geometry, the three arms pick three distinct designs on only
#: **11**; 35 pairs give two and 14 give one.
#:
#: Switching this on costs about three deciles of pair quality: the best distinct-arm pairs are
#: ``53/605/5`` at rank 7 (worst percentile 35.0) and ``306/710/4`` at rank 9 (48.3).
#:
#: And it does not buy six independent measurements on both. On ``53/605/5`` the ``A_M ratio`` and
#: ``dG arm (ON)`` designs are different rows carrying the SAME arm values -- ied_gain 0.2138,
#: A_M ratio 9.6, dG arm 0.94 on each -- differing only in opening SEP (-8.38 against -6.63), so
#: the third design is a tie broken by something no arm is reading. ``306/710/4`` separates for
#: real: dG arm 3.58 / 2.50 / 2.29 and A_M ratio 4.5 / 9.1 / 5.2 across its three rows.
#:
#: So this is a declared trade, not a fix: it is six distinct tubes against the two best pairs, and
#: on one of the two pairs the sixth tube repeats a measurement under a different label anyway.
#: ``--distinct-arms``.
DISTINCT_ARMS = False

#: A fourth arm, taken on MORE pairs than the three base arms, and how many pairs it gets.
#:
#: **Why a fourth arm is not simply a fourth column.** Two pairs x four arms is eight rows, and the
#: bench budget is six. What this builds instead is the six to build, unchanged, plus the fourth
#: arm's own picks on the best ``ARM4_PAIRS`` pairs -- so the question "what would this arm have
#: chosen" is answerable by eye without the six moving to accommodate it. At the default of 3 that
#: is 6 + 3 = 9 rows.
#:
#: The fourth arm's rows are tagged ``arm 4`` in ``control`` so a view can show or hide them, and
#: they are NOT part of the ranking: the pairs are still chosen on the three base arms, because
#: letting a fourth arm move the pairs would change the six this panel exists to compare.
#:
#: ``opening SEP`` is the arm this was built for. It is ``open_11`` minus the cheapest OFF tube --
#: measured, ``f1`` -- and it is the panel's GATING FLOOR rather than one of its arms, because
#: against Green's 168 it scores **-0.107**: designs it prefers did worse on the bench. A floor it
#: can be, since every design must clear some AND-ness; an order it cannot. This exists so that
#: verdict can be looked at rather than taken on the number.
ARM4 = ""

#: Which arms each pair is CHOSEN for, one group per pair. Empty means every pair is judged on
#: every arm, which is the maximise-the-worst rule.
#:
#: **Maximise-the-worst is one rule and not an obvious one.** With an empty assignment a pair is
#: ranked on the WORST of the three arms' percentiles, so a pair that is excellent on two arms and
#: weak on one loses to a pair that is middling on all three. Measured on this build: the pair
#: holding the best A_M ratio anywhere, **96.0**, splits three ways and still ranks **30**, because
#: its opening SEP runs -3.63 to -4.96 against the leader's -9.83. The panel then shows A_M ratios
#: of 12.7 and 9.6 while 96.0 was available.
#:
#: An assignment says instead: *this* pair is here to serve these arms. Every arm is still emitted
#: on every pair -- the panel is still two pairs x PANEL_ARMS -- but the pair is selected for the
#: arms it is meant to answer, so a pair strong on one question is not rejected for being ordinary
#: on another.
#:
#: Given as ``--pair-arms "IED gain|A_M ratio"`` (one arm each) or
#: ``--pair-arms "IED gain,A_M ratio|opening SEP,Barrier"`` (two each). The groups are matched to
#: pairs greedily in order: the first group picks its best pair, the second picks its best from
#: what is left, which is why the stronger claim should come first.
PAIR_ARMS: tuple[tuple[str, ...], ...] = ()

#: The pairs forced with ``--pin``, kept only so ``recipe`` can say so. A pinned panel is not a
#: ranked one and a reader comparing views has to be able to tell.
PINNED_FOR_RECIPE: tuple[str, ...] = ()

#: How many pairs the fourth arm picks on, best-ranked first. Independent of the two the six use.
ARM4_PAIRS = 3

#: How close two arm rows have to be, as a fraction of the CELL'S OWN RANGE on each arm column,
#: before they count as one measurement rather than two.
#:
#: **Counting distinct switch strings is not enough, and that was measured.** On ``53/605/5`` the
#: ``A_M ratio`` and ``dG arm (ON)`` arms picked two different switches carrying ied_gain 0.2138,
#: A_M ratio 9.6 and dG arm 0.94 *each* -- identical to three significant figures on every arm the
#: panel reads, differing only in opening SEP, which is the floor and not an arm. Two tubes, one
#: measurement, and a ``distinct designs: 6 of 6`` banner that says otherwise.
#:
#: A fraction of the cell's range rather than an absolute tolerance, because the three arms are a
#: probability difference, a ratio and kcal/mol, and the cell is the only scale they share.
ARM_TIE = 0.02

#: Fewest bases two panel designs may differ by and still count as two measurements.
#:
#: **Because arm VALUES can differ while the sequences do not.** ``ARM_TIE`` compares the arms'
#: numbers, and on ``414/361/4`` the ``A_M ratio`` pick and the ``opening SEP`` pick score 96.0 and
#: 94.9 -- a real difference by that test -- while being **one nucleotide apart**. One substitution
#: is one experiment whichever arm chose each end of it, and a panel reporting six distinct
#: measurements there is reporting a difference in the score and not in the construct.
#:
#: 3 is a declared line, not a measured one: nothing says where "the same design" ends. It is set
#: where a single codon's worth of change still counts as the same, since that is the unit the
#: generator varies.
MIN_NT_APART = 3

#: Let each pair bring its own geometry, instead of forcing one on the whole panel.
#:
#: **Forcing one is a real cost and it was never measured until now.** The builder picks the
#: geometry carrying more eligible pairs -- Kim 20/17/AUA with 38 against naive 18nt's 24 -- and
#: everything in the other one is then unreachable. Measured over the designs that survive every
#: filter: the best A_M ratio in Kim is **96.0** and in naive it is **383.6**, while the best
#: opening SEP is -14.27 in Kim against -13.30 in naive. So the geometry choice alone is what put
#: every A_M ratio above 100 out of reach.
#:
#: **What forcing one buys** is the thing the panel was built for: two pairs in one geometry differ
#: in the pair and nothing else, so a bench difference points at the trigger pair. Let each pair
#: bring its own and a difference between the two halves of the panel has two possible causes at
#: once. The three arms WITHIN a pair are still a clean comparison either way -- the geometry is
#: fixed inside a cell -- so what is lost is only the comparison ACROSS the two pairs, which no
#: arm reads.
#:
#: Off by default because that is a deliberate trade, not an improvement. ``--any-geometry``.
ANY_GEOMETRY = False

#: The columns ``ARM_TIE`` compares, one per entry of ``PANEL_ARMS``, in the same order.
ARM_COLUMNS = {
    "IED gain": "ied_gain",
    # Missing, and the omission silently disabled the whole test: an arm with no column here makes
    # `real_measurements` fall back to counting switch STRINGS, so a 1-nt pair counted as two.
    # Every arm in ARMS belongs in this map.
    "opening SEP": "f1",
    "IED gain (worst OFF)": "ied_gain_worst",
    "IED rbs-linker": "ied_rbs_linker_11",
    "dG rbs-linker": "dG_rbs_linker",
    "combined (SEP)": "f4",
    "A_M ratio": "f2",
    "dG arm (ON)": "dG_arm_11",
    "Barrier": "barrier",
    "A_M gain": "f2_gain",
    "combined": "f5",
}


def real_measurements(cell: list[dict], arm_rows: dict[str, dict]) -> int:
    """How many of the arm rows are measurements the others do not already carry.

    Two rows are one measurement when they agree within ``ARM_TIE`` of the cell's range on EVERY
    arm column. Falls back to counting switches for an arm with no column mapped, which is the
    conservative direction: it over-counts rather than silently merging two rows.
    """
    columns = [ARM_COLUMNS.get(arm) for arm in arm_rows]
    if any(c is None for c in columns):
        return len({r["switch"] for r in arm_rows.values()})
    spans = {}
    for column in columns:
        values = [r[column] for r in cell if r.get(column) is not None]
        spans[column] = (max(values) - min(values)) if len(values) > 1 else 0.0
    groups: list[dict] = []
    for row in arm_rows.values():
        for first in groups:
            # Either test merges them: the arms cannot tell them apart, OR the sequences are too
            # close to be two constructs. The second is the one that catches a 1-nt pair whose
            # arm values happen to differ.
            close = (
                len(row["switch"]) == len(first["switch"])
                and sum(1 for x, y in zip(row["switch"], first["switch"], strict=True) if x != y)
                < MIN_NT_APART
            )
            tied = all(
                abs(row[c] - first[c]) <= ARM_TIE * spans[c] or spans[c] == 0.0 for c in columns
            )
            if tied or close:
                break
        else:
            groups.append(row)
    return len(groups)


#: Require a pair to carry designs in BOTH geometries.
#:
#: **Obsolete, and switched off.** It existed because the panel was once 3 pairs x 2 geometries x 3
#: objectives: every row had a partner in the other geometry so that a difference between the two
#: was the GEOMETRY and not the transcript. That was a real control and the requirement was right
#: for it.
#:
#: The six-construct panel has no architecture arm -- all six rows are one geometry -- so the
#: requirement now buys nothing and costs candidates that are fully measured and fully feasible.
#: Measured at the moment it was switched off: 601/54/5 (24 feasible, 12 gating), 625/124/6 (31,
#: 15), 645/425/4 (17, 9), 554/123/4 (11, 11), 598/414/6 (24, 14) and 645/560/4 (13, 4) were all
#: excluded by this line alone, with nothing else wrong with them.
#:
#: Set True to restore it, which is what a panel that compares geometries again would need.
REQUIRE_BOTH_GEOMETRIES = False


def controlled_pairs(rows: list[dict], per_cell: int) -> list[str]:
    """Pairs carrying at least ``per_cell`` feasible designs in BOTH geometries, best first."""
    by_pair: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        by_pair.setdefault(row["pair"], {}).setdefault(row["geom"], []).append(row)
    usable = [
        (min(r["f1"] for cells in geoms.values() for r in cells), pair)
        for pair, geoms in by_pair.items()
        # ``per_cell`` applies to the geometries the pair actually has. With the requirement off
        # and one geometry present, that is "this cell holds per_cell designs"; with two, it is
        # "the THINNER of the two does" -- `all(...)`, not the total, because a slot in the panel
        # draws from one cell and a fat cell cannot cover for an empty one.
        if (len(geoms) >= 2 or not REQUIRE_BOTH_GEOMETRIES)
        and all(len(v) >= per_cell for v in geoms.values())
    ]
    usable.sort()
    return [pair for _, pair in usable]


def gating(rows: list[dict]) -> list[dict]:
    """The floor f1 is kept for: a design has to separate the ON tube from the best OFF tube.

    With ``VARIANT_GATING`` set, the same floor is also required of ``andness_variant`` -- the
    AND-ness of the four TRANSCRIPTS rather than of four tubes built by omitting strands. A design
    with no measurement keeps ``None`` and is kept: unmeasured is not failed, and `variant_leak.py`
    has not necessarily been run.
    """
    kept = [r for r in rows if r["f1"] is not None and r["f1"] <= GATING]
    if VARIANT_GATING is None:
        return kept
    return [
        r
        for r in kept
        if r.get("andness_variant") is None or r["andness_variant"] <= VARIANT_GATING
    ]


def cell_picks(cell: list[dict], arms: dict | None = None) -> dict[str, list[str]]:
    """switch -> the objectives that chose it, for one (pair, geometry) cell.

    An arm in ``CELL_RELATIVE`` is a factory taking the cell and returning the key, because an
    epsilon-constraint cannot be evaluated on a row alone -- it needs the cell's ceiling.
    """
    out: dict[str, list[str]] = {}
    for arm, key in (arms or ARMS).items():
        resolved = key(cell) if arm in CELL_RELATIVE else key
        out.setdefault(min(cell, key=resolved)["switch"], []).append(arm)
    return out


def by_cell(rows: list[dict], per_cell: int) -> dict[tuple[str, str], list[dict]]:
    return {key: group for key, group in _group(rows).items() if len(group) >= per_cell}


def _group(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    cells: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        cells.setdefault((row["pair"], row["geom"]), []).append(row)
    return cells


#: Minimum share of a window's substitutions that must actually break a pair, per window.
#:
#: **A wet-lab constraint, not a score.** The four mCherry transcripts realise the 01 and 10 states
#: by recoding a trigger window; a window whose recoding leaves the duplex intact cannot produce
#: those states, so the pair cannot be used however well its switches score. Synthesising it spends
#: bench budget on a construct designed to fail.
#:
#: Measured over the 53 eligible pairs, **52 clear 50% on both windows and exactly one does not**:
#: ``625/124/6``, whose A window breaks 5 of 11 substitutions. That pair had been pinned onto the
#: panel, and ``order_check`` was reporting its four failures after the panel was already
#: published -- which is the wrong end of the process to find it.
#:
#: 0.5 matches the bar ``order_check`` already applies, so the panel cannot select a pair that the
#: pre-order check will then reject. ``recode_quality.py`` prints the per-pair numbers.
RECODE_FLOOR = 0.5

#: Minimum share of ``main_pre*`` that trigger A must pair with in the ON tube.
#:
#: **A physical disqualification, and the third route to the same failure.** A gate whose main stem
#: trigger A never opens does not open, whatever it scores: the ribosome's window stays shut. It is
#: not the same question as the x* lock -- measured on the panel, designs scoring 0.85, 0.93 and
#: 0.97 on "x* taken by A" sat at 0.006, 0.009 and 0.047 here. A took the lock and left the stem
#: closed, and the lock term reported success.
#:
#: Measured on the long-overlap pairs, which is where this was found: of the six eligible, two had
#: an arm minimum of 0.006 and 0.043 across their arms while four ran 0.515 to 0.932. The panel had
#: selected one of the two bad ones twice -- once at len_x 7 and once, before that, at len_x 6 --
#: because this was reported on the card and never filtered on.
#:
#: 0.3 is declared, not measured: the population is bimodal with nothing near it (at or below 0.05,
#: or at or above 0.19), so the value inside that gap does not matter. Needs
#: ``complete_panel.py --metrics stem`` to have run; until then the column is None and NOTHING is
#: rejected, which is the standing convention -- unmeasured is not failed.
ARM_FLOOR = 0.3

#: Smallest share of trigger A's MFE contacts that must land on the ascending arm, in tube 11.
#:
#: **The same disqualification as ``ARM_FLOOR``, asked of the structure the report DRAWS.**
#: ``engaged_arm_11`` sums pair probabilities over the whole ensemble; this reads the single most
#: probable structure. A design can pass the first and fail this one, and then its own figure of
#: the ON tube shows a shut main hairpin -- which is how this was noticed, by looking at the
#: pictures rather than at a column.
#:
#: **The line is drawn by the histogram, not chosen.** Over the 2,446 feasible designs the
#: distribution is in two pieces: **178 sit at exactly 0.000**, then a gap -- only 5 designs in
#: the whole interval (0, 0.2) -- and then the mass, median 0.556, sd 0.096, up to 1.000. So
#: ``> 0`` separates two populations rather than cutting a tail. Raising it to 0.2 would cost 5
#: more designs and 0.4 would cost 165, which is a different and much stronger claim; this floor
#: makes the weak one.
#:
#: **What it costs**, measured on the gating set: 1,317 of 1,480 kept (89.0%), 92 of 96 trigger
#: pairs survive, 94 of 100 cells still hold three or more designs, and the best value of every
#: arm is unchanged -- A_M ratio 383.567, A_M gain 0.822, Barrier 19.360, IED gain 0.304, dG arm
#: 0.403 -- except ``opening SEP``, which gives up 0.19 kcal/mol (-14.460 to -14.274).
STEM_MFE_FLOOR = 0.0

#: Overlap lengths counted as "long". ``len_x 6`` qualifies but cannot currently fill the slot:
#: it has 7 gating designs across 5 pairs and **none with both geometries**, so the long slot
#: falls to ``len_x 7``. That is a fact about where the sweep has reached, not about len_x 6 --
#: 4,034 of its designs are scored against 24,279 at len_x 4.
LONG_LENX = (6, 7)


def swap_solves(by_pair: dict, pair: str, taken: list[str]) -> list[dict] | None:
    """The four transcripts that address both pairs despite their clash, or ``None``.

    Delegates to ``role_swap.solve``, which names each transcript by the SET of windows it recodes
    rather than by a role, and lets the logic state it realises differ per pair. The overlap then
    stops being damage and becomes the mechanism -- the transcript that removes pair 1's A removes
    pair 2's B as collateral, which is one pair at 01 and the other at 10 in the same tube.

    ``solve`` enumerates all 16 window subsets and every 4-subset combination, 1,820 cases, so a
    ``None`` is a proof that no four transcripts suffice and not a search that gave up.

    **Conservative on failure.** An import or data error returns ``None``, which keeps the old
    rejection. Elsewhere in this module an unmeasured quantity is treated as "not rejected", and
    that is right for a filter that would otherwise delete designs nobody checked; it is wrong
    here, where being permissive would put a pair on the panel whose 01 and 10 transcripts cannot
    be built.
    """
    if len(taken) != 1:
        # ``solve`` is written for two pairs, four windows. Three pairs is a larger problem that has
        # not been measured, so the clash stands rather than being waved through.
        return None
    try:
        import codon_variants as cv
        from full_sweep import read_fasta
        from role_swap import changed_positions, solve

        here = Path(__file__).resolve().parent
        amino, fraction = cv.load_codon_table(here / "data" / "ecoli_codon_usage_table.csv")
        groups = cv.synonyms(amino)
        transcript = read_fasta(here / "mCherry_original.txt")
    except Exception as error:
        print(f"  role swap unavailable ({type(error).__name__}), clash stands")
        return None

    windows, changes = {}, {}
    for index, name in ((1, pair), (2, taken[0])):
        spans = windows_of(by_pair, name)
        for role in ("A", "B"):
            lo, hi = spans[role]
            windows[f"{index}{role}"] = (lo, hi)
            # Asked of the recoder's own per-codon rule rather than assumed to be the whole window:
            # it substitutes roughly a quarter of a window, so an overlap containing none of its
            # substitutions is not collateral damage at all.
            changes[f"{index}{role}"] = changed_positions(
                transcript, lo, hi, amino, fraction, groups
            )
    return solve(windows, changes)


def recodes_ok(by_pair: dict, pair: str) -> bool:
    """Can BOTH of this pair's windows be recoded into a knockout?

    Lifted out of ``pick`` so ``pick_six`` uses the same test rather than a second copy. The first
    version of ``pick_six`` had no copy at all and selected ``625/124/6`` -- the one pair of 53 that
    ``RECODE_FLOOR`` rejects -- which is exactly the failure the floor exists to prevent.

    Imported lazily and permissively: the panel must stay buildable without the codon table, and a
    missing table means every pair passes, which is the status quo rather than a silent rejection.
    """
    try:
        import codon_variants as cv
        from full_sweep import read_fasta
        from recode_quality import recode_window

        here = Path(__file__).resolve().parent
        amino, fraction = cv.load_codon_table(here / "data" / "ecoli_codon_usage_table.csv")
        groups = cv.synonyms(amino)
        transcript = read_fasta(here / "mCherry_original.txt")
    except Exception:
        return True
    flat = [r for cells in by_pair[pair].values() for r in cells]
    for lo_key, hi_key in (("a_start", "a_end"), ("b_start", "b_end")):
        lo = min(int(r[lo_key]) for r in flat)
        hi = max(int(r[hi_key]) for r in flat)
        subs, breaks = recode_window(transcript, lo, hi, amino, fraction, groups)
        if not subs or breaks / subs < RECODE_FLOOR:
            return False
    return True


def windows_of(by_pair: dict, pair: str) -> dict[str, tuple[int, int]]:
    """This pair's two trigger windows, widest form, as spans on the transcript."""
    flat = [r for cells in by_pair[pair].values() for r in cells]
    return {
        "A": (min(int(r["a_start"]) for r in flat), max(int(r["a_end"]) for r in flat)),
        "B": (min(int(r["b_start"]) for r in flat), max(int(r["b_end"]) for r in flat)),
    }


# The panel used to be two base arms plus a third arm SPLIT between the pairs, each half an
# epsilon-constrained "same quality on the base arm, better barrier" pick. Four constants served it
# -- `ARM3_FALLBACKS`, `ARM3_MUST_GAIN`, `ARM3_MIN_GAIN`, `SIX_EPS` -- and all four are gone with
# it, because the structure is now three equal arms on two pairs.
#
# **Why the split went.** Its measured lift over its own base arm was +0.0388 against Green's 168,
# inside that library's 0.08 sampling noise, so two of six constructs tested a claim the data
# cannot carry. The epsilon machinery is recoverable from git if an arm ever needs it again; the
# numbers behind the decision are in the commit that removed it.


#: Require the panel's two pairs to use two different trigger-A windows.
#:
#: **Caught on a rebuild, and it is not the same thing as "two different pairs".** After the
#: accessibility and hairpin filters reached full coverage, ``pick_six`` chose 645/425/4 and
#: 645/560/4 -- two distinct pairs that share trigger A at position 645. ``cross_role_clash``
#: deliberately permits A against A (both are recoded in the same transcript and removed together),
#: so nothing objected. The result would have been **all six constructs depending on one trigger
#: A**: if that window is unreachable in the cell, the whole experiment returns nothing, where two
#: distinct A windows leave half the panel informative.
#:
#: It costs almost nothing. Over the 37 eligible pairs, of 666 two-pair combinations **466 already
#: use two distinct A windows and only 14 share one** -- and with the role swap wired, the 186 that
#: clash cross-role are usable too. So this rejects 2% of the choice to remove a single point of
#: failure.
#:
#: Set False to allow a shared trigger A, which is a deliberate declaration and not a default.
DISTINCT_TRIGGER_A = True


def shares_trigger(by_pair: dict, pair: str, other: str) -> bool:
    """Do these two pairs reach the transcript through the same trigger-A window?

    Compared on the window START, not on the pair label: two pairs with the same A and different B
    have different labels and the same single point of failure. The ends differ between geometries
    (36 nt naive against 35 Kim) while the start does not, so the start is the stable identity.
    """
    return windows_of(by_pair, pair)["A"][0] == windows_of(by_pair, other)["A"][0]


def cross_role_clash(by_pair: dict, pair: str, other: str) -> int:
    """Overlapping nucleotides between one pair's A and the other's B, either direction.

    CROSS-ROLE only: A against A is harmless because both are recoded in the same transcript and
    removed together, which is what that transcript is for. A against B is the breaking case --
    recoding one pair's B changes bases inside the other's A, so the transcript meant to leave A
    intact destroys it.
    """
    mine, theirs = windows_of(by_pair, pair), windows_of(by_pair, other)
    worst = 0
    for mine_role, theirs_role in (("A", "B"), ("B", "A")):
        lo, hi = mine[mine_role]
        start, stop = theirs[theirs_role]
        worst = max(worst, min(hi, stop) - max(lo, start))
    return max(worst, 0)


def recipe() -> str:
    """One line saying how this panel was built, carried on every row of it.

    **Why it travels with the data.** Five panels now exist side by side as views on one page, and
    nothing on that page said what any of them was -- the difference between them is the arm set
    and the pair rule, neither of which is visible in a row. Asked what the views meant, the only
    answer was the shell history that produced them. A panel that cannot say how it was built is
    not comparable with the one beside it.
    """
    parts = [f"arms={', '.join(PANEL_ARMS)}"]
    if ARM4:
        parts.append(f"arm4={ARM4} on {ARM4_PAIRS} pair(s)")
    if PAIR_ARMS:
        groups = "".join("(" + ", ".join(group) + ")" for group in PAIR_ARMS)
        parts.append(f"pairs=assigned {groups}")
    else:
        parts.append("pairs=the worst arm's percentile, maximised")
    if ANY_GEOMETRY:
        parts.append("geometry=per pair")
    if VARIANT_GATING is not None:
        parts.append(f"bench floor: andness_variant <= {VARIANT_GATING}")
    if PINNED_FOR_RECIPE:
        parts.append(f"pinned by hand: {', '.join(PINNED_FOR_RECIPE)}")
    if DISTINCT_ARMS:
        parts.append("pairs must give three distinct measurements")
    if LOWER3_KEEP:
        parts.append(f"lower3 in {{{', '.join(sorted(LOWER3_KEEP))}}}")
    return " | ".join(parts)


def pick_six(rows: list[dict], geometry: str = "", pin: tuple[str, ...] = ()) -> list[dict]:
    """Six constructs: two base arms on two trigger pairs, and arm 3 split between them.

    The layout, which is a budget decision rather than a scoring one -- the bench can build six:

        pair A, arm 1   A_M gain                        pair B, arm 1   A_M gain
        pair A, arm 2   dG_rbs_linker                   pair B, arm 2   dG_rbs_linker
        one of the two  eps(A_M gain) + barrier         the other       eps(dG_rbs_linker) + barrier

    **One geometry, not two.** Six slots do not hold two geometries as well as two pairs and three
    arms, and the geometry is the axis that divided least: the two families' best opening SEP came
    out -14.32 and -14.46, and the A_M arm took its cell's maximum under both. Pair is where the
    spread is -- best A_M ratio runs 3.7 to 383.6 across pairs -- so pair earns the axis.

    **Why arm 3 is assigned by measurement.** The epsilon-constraint only yields a design DIFFERENT
    from its base arm where the cell holds something with a comparable base value and a better
    barrier. Measured over 50 eligible cells, only 26 reorder on both arms, so assigning the halves
    arbitrarily would spend a construct on a duplicate of arm 1 or arm 2. Each half therefore
    goes to the pair where it gains the most barrier, and the halves are put on different pairs
    when that costs nothing.

    The three arms are near-independent on our population -- agreement +0.221 (A_M gain against
    dG_rbs_linker), +0.282 (dG_rbs_linker against barrier), -0.050 (A_M gain against barrier) --
    which is what makes six constructs worth more than one aggregate: an aggregate hides exactly the
    disagreement the bench is being asked to settle.
    """
    by_pair: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        by_pair.setdefault(row["pair"], {}).setdefault(row["geom"], []).append(row)

    def best_of(cell: list[dict], column: str, lower: bool = False) -> dict | None:
        usable = [r for r in cell if r.get(column) is not None]
        if not usable:
            return None
        return (
            min(usable, key=lambda r: r[column]) if lower else max(usable, key=lambda r: r[column])
        )

    # --- the geometry -------------------------------------------------------------------------
    geometries = sorted({g for geoms in by_pair.values() for g in geoms})
    if geometry and geometry in geometries:
        chosen_geometry = geometry
    else:
        # Whichever carries more eligible pairs, so the pair choice is least constrained.
        counts = {
            g: sum(1 for geoms in by_pair.values() if len(geoms.get(g, [])) >= 3)
            for g in geometries
        }
        chosen_geometry = max(counts, key=lambda g: counts[g]) if counts else ""
        print(f"  geometry chosen by eligible-pair count: {chosen_geometry}  {counts}")

    # --- the two pairs -----------------------------------------------------------------------
    # A pair is a candidate when the cell can serve EVERY arm the panel emits, and is ranked on
    # the WORST of those arms -- so a pair has to serve all three rather than being carried by one.
    #
    # **This used to rank on `f2_gain` and `dG_rbs_linker`**, which is the bug this replaces: the
    # emission had already moved to PANEL_ARMS, so the pairs were chosen for two arms that no row
    # on the page is built from -- one of them the arm rejected for being blind to the ON state.
    # Choosing on arm X and then reporting arm Y is how a panel ends up with nothing to compare.
    #
    # Percentile, not the raw value, because the three arms are in different units -- a probability
    # ratio, a mean-unpaired difference and kcal/mol. Every ARMS key is already oriented so LOWER
    # is better, so the percentile is of values below this one and a low percentile is a good pair.
    candidates = []
    rejected: dict[str, int] = {}
    # One entry per (pair, geometry) when ANY_GEOMETRY, else only the chosen geometry's cell. A
    # pair appearing in both geometries competes as two candidates and at most one can be taken,
    # because the clash test below rejects a pair against itself by trigger A.
    cells = (
        [(pair, geom, cell) for pair, geoms in by_pair.items() for geom, cell in geoms.items()]
        if ANY_GEOMETRY
        else [
            (pair, chosen_geometry, geoms.get(chosen_geometry, []))
            for pair, geoms in by_pair.items()
        ]
    )
    for pair, _geom, cell in cells:
        if len(cell) < len(PANEL_ARMS):
            continue
        arm_rows = {}
        for arm in PANEL_ARMS:
            key = ARMS[arm](cell) if arm in CELL_RELATIVE else ARMS[arm]
            usable = [r for r in cell if key(r) != float("inf")]
            if usable:
                arm_rows[arm] = min(usable, key=key)
        if len(arm_rows) < len(PANEL_ARMS):
            missing = [a for a in PANEL_ARMS if a not in arm_rows]
            reason = f"no design carries {', '.join(missing)}"
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        # The same recoding test `pick` applies. A pair whose window cannot be knocked out cannot
        # produce its 01 or 10 transcript, so it is not a candidate however well it scores.
        if not recodes_ok(by_pair, pair):
            rejected["recodes below the floor"] = rejected.get("recodes below the floor", 0) + 1
            continue
        if DISTINCT_ARMS and real_measurements(cell, arm_rows) < len(PANEL_ARMS):
            rejected["two arms measure the same thing"] = (
                rejected.get("two arms measure the same thing", 0) + 1
            )
            continue
        candidates.append((pair, cell, arm_rows))
    for reason, count in rejected.items():
        print(f"  {count} pair(s) dropped: {reason}")
    if len(candidates) < 2:
        print(f"  fewer than two pairs usable in {chosen_geometry} -- cannot build six")
        return []

    def arm_value(row: dict, arm: str, cell: list[dict]) -> float:
        key = ARMS[arm](cell) if arm in CELL_RELATIVE else ARMS[arm]
        return key(row)

    per_arm = {
        arm: sorted(arm_value(rows[arm], arm, cell) for _p, cell, rows in candidates)
        for arm in PANEL_ARMS
    }

    def rank_in(values: list[float], value: float) -> float:
        """Percentile of `value` in `values`, where LOWER is better, so 0 is the best pair."""
        return 100.0 * sum(1 for v in values if v < value) / len(values)

    def score_on(cell: list[dict], arm_rows: dict, arms: tuple[str, ...]) -> float:
        """The worst percentile among `arms` -- the whole set, or just the ones assigned."""
        return max(rank_in(per_arm[arm], arm_value(arm_rows[arm], arm, cell)) for arm in arms)

    scored = []
    for pair, cell, arm_rows in candidates:
        scored.append((score_on(cell, arm_rows, PANEL_ARMS), pair, cell, arm_rows))
    scored.sort()
    if PAIR_ARMS:
        # One group per pair, matched greedily in group order: the first group takes its best pair,
        # the second its best of what is left. `scored` is rebuilt so that everything downstream --
        # the clash test, the role swap, the emission -- sees the pairs in the order this rule
        # chose them, and the maximise-the-worst scores stay on the entries for reporting.
        print(f"  --pair-arms: each pair chosen for its own arms, {len(PAIR_ARMS)} group(s)")
        remaining = list(scored)
        ordered = []
        for group in PAIR_ARMS:
            missing = [arm for arm in group if arm not in PANEL_ARMS]
            if missing:
                print(f"    {', '.join(missing)} is not one of the panel's arms -- group skipped")
                continue
            ranked = sorted(remaining, key=lambda entry: score_on(entry[2], entry[3], tuple(group)))
            if not ranked:
                break
            best = ranked[0]
            print(
                f"    {', '.join(group):28s} -> {best[1]:16s}"
                f"(its own worst percentile {score_on(best[2], best[3], tuple(group)):5.1f}, "
                f"on all three {best[0]:5.1f})"
            )
            ordered.append(best)
            remaining = [entry for entry in remaining if entry[1] != best[1]]
        # Anything the groups did not claim keeps the all-arms order behind them, so a group that
        # could not be filled still leaves a usable panel rather than an empty one.
        scored = ordered + remaining

    taken: list[tuple] = []
    #: The four-transcript assignment, when the two chosen pairs clash and the role swap resolved
    #: it. Empty when the pairs are cross-role disjoint -- the ordinary case, which needs no plan.
    swap_plan: list[dict] = []
    for pinned in pin:
        # `pair` or `pair@geometry`. The geometry half matters only with --any-geometry, where one
        # pair is two candidates: pinning `507/260/4` alone took whichever came first in the
        # ranking, which was the Kim cell at A_M 12.6 while the naive cell of the same pair is at
        # 383.6. A pin that cannot say which cell it means is not a pin.
        want, _, want_geom = pinned.partition("@")
        hit = next(
            (
                s
                for s in scored
                if s[1] == want and (not want_geom or s[2][0]["geom"].startswith(want_geom))
            ),
            None,
        )
        if hit is None:
            where = f" in {want_geom}" if want_geom else ""
            print(f"  --pin {pinned}: no usable cell{where}, skipped")
            continue
        # Everything below keys on the bare pair -- `by_pair`, the clash test, the swap -- so the
        # geometry half is dropped once it has selected the cell.
        pinned = want
        # A pin overrides the RANKING, not the physics. This loop used to append straight into
        # `taken`, so pinning two pairs skipped the cross-role test entirely -- and a panel built
        # that way carried a 13 nt clash with no swap plan attached, which cannot be ordered: the
        # four transcripts do not exist. Measured on --pin 423/658/7,645/425/4.
        clash = max((cross_role_clash(by_pair, pinned, t[1]) for t in taken), default=0)
        if clash > 0:
            swap = swap_solves(by_pair, pinned, [t[1] for t in taken])
            if swap is None:
                print(
                    f"  --pin {pinned}: {clash} nt cross-role overlap with "
                    f"{', '.join(t[1] for t in taken)} and the role swap cannot resolve it. "
                    f"PINNED ANYWAY -- the four transcripts for this panel do not exist"
                )
            else:
                print(f"  --pin {pinned}: {clash} nt cross-role overlap, RESOLVED by role swap")
                for index, step in enumerate(swap):
                    names = " ".join(step["recoded"]) or "(nothing recoded)"
                    print(
                        f"    T{index}: {names:26s}{pinned} -> {step['pair1_state']}"
                        f"   {taken[0][1]} -> {step['pair2_state']}"
                    )
                swap_plan.extend(
                    {
                        "transcript": f"T{index}",
                        "recoded": " ".join(step["recoded"]) or "(none)",
                        "pair_1": pinned,
                        "state_1": step["pair1_state"],
                        "pair_2": taken[0][1],
                        "state_2": step["pair2_state"],
                        "clash_nt": clash,
                    }
                    for index, step in enumerate(swap)
                )
        taken.append(hit)
    for entry in scored:
        if len(taken) >= 2:
            break
        if entry[1] in {t[1] for t in taken}:
            continue
        # Cross-role disjointness against everything already taken: the four transcripts are
        # shared, so one pair's A overlapping the other's B means the A-recoded transcript damages
        # a B window it must leave intact. Measured once at 11 nt on a live panel, which produced
        # untouched runs of 41 nt where the recoder had barely acted.
        if DISTINCT_TRIGGER_A and any(shares_trigger(by_pair, entry[1], t[1]) for t in taken):
            print(
                f"  {entry[1]} skipped: shares trigger A with "
                f"{', '.join(t[1] for t in taken if shares_trigger(by_pair, entry[1], t[1]))}"
            )
            continue
        clash = max((cross_role_clash(by_pair, entry[1], t[1]) for t in taken), default=0)
        swap = swap_solves(by_pair, entry[1], [t[1] for t in taken]) if clash > 0 else None
        if clash > 0 and swap is None:
            print(
                f"  {entry[1]} skipped: {clash} nt cross-role overlap with "
                f"{', '.join(t[1] for t in taken)}, and the role swap cannot resolve it"
            )
            continue
        if swap is not None:
            # Kept, with the assignment recorded on the entry rather than left implicit. The wet lab
            # builds from this: "A-recoded" is no longer a meaningful transcript name here, so the
            # four transcripts have to travel with the panel or they cannot be ordered.
            print(
                f"  {entry[1]}: {clash} nt cross-role overlap with "
                f"{', '.join(t[1] for t in taken)}, RESOLVED by role swap"
            )
            for index, step in enumerate(swap):
                names = " ".join(step["recoded"]) or "(nothing recoded)"
                print(
                    f"    T{index}: {names:26s}{entry[1]} -> {step['pair1_state']}"
                    f"   {taken[0][1]} -> {step['pair2_state']}"
                )
            swap_plan.extend(
                {
                    "transcript": f"T{index}",
                    "recoded": " ".join(step["recoded"]) or "(none)",
                    "pair_1": entry[1],
                    "state_1": step["pair1_state"],
                    "pair_2": taken[0][1],
                    "state_2": step["pair2_state"],
                    "clash_nt": clash,
                }
                for index, step in enumerate(swap)
            )
        taken.append(entry)
    if len(taken) < 2:
        return []

    chosen: list[dict] = []
    seen: set[str] = set()

    # Which transcript realises which state, for THIS pair, when the role swap was used. Without it
    # a row says "01" and the bench cannot tell which of the four tubes that is, because the
    # transcripts are no longer named by a role -- the same transcript is 01 for one pair and 10 for
    # the other. Empty when the pairs were disjoint and the ordinary role naming still holds.
    swap_by_pair: dict[str, dict[str, str]] = {}
    for step in swap_plan:
        for index, role in (("1", "state_1"), ("2", "state_2")):
            name = step[f"pair_{index}"]
            swap_by_pair.setdefault(name, {})[step["transcript"]] = step[role]

    # The WHOLE plan as one string, carried on every row, because the recoder cannot reconstruct
    # it: when the swap is used the four transcripts are not "original / A / B / AB" any more --
    # T1 recodes pair 1's A window ALONE, not every A window -- and nothing but this says so.
    #
    # **This is the fourth time a computed column never reached the file.** `swap_states` and
    # `swap_used` were built here and left out of the field list, so `codon_variants` had no way
    # to know a swap was needed and built the ordinary four transcripts for a panel that cannot
    # use them. The variants for `panel_assign` were wrong for exactly that reason.
    #
    #     pairs=<pair 1>;<pair 2>|T0=|T1=1A|T2=1B,2A|T3=1A,1B,2A
    #
    # `1A` means pair 1's trigger-A window; an empty right-hand side is the untouched transcript.
    swap_recipe = ""
    if swap_plan:
        pairs = f"pairs={swap_plan[0]['pair_1']};{swap_plan[0]['pair_2']}"
        steps = "|".join(
            f"{step['transcript']}=" + ",".join(w for w in step["recoded"].split() if w != "(none)")
            for step in swap_plan
        )
        swap_recipe = f"{pairs}|{steps}"
        print(f"  swap recipe: {swap_recipe}")

    def take(row: dict, arm: str, control: str) -> None:
        plan = swap_by_pair.get(row["pair"]) or {}
        chosen.append(
            {
                **row,
                "arm": arm,
                "role": arm,
                "control": control,
                "multiplicity": 1,
                "duplicate": row["switch"] in seen,
                # A string rather than a nested object: these rows are written to CSV and read back
                # by the report, and a nested value would come back as a repr nobody parses.
                "swap_states": (" ".join(f"{t}={plan[t]}" for t in sorted(plan)) if plan else ""),
                "swap_used": bool(plan),
                "swap_recipe": swap_recipe,
            }
        )
        seen.add(row["switch"])

    # Two pairs x PANEL_ARMS = six rows. Each arm picks the best design in that pair's cell with
    # `cell_picks`, which is the same selector every other table on the page ranks with, so a row
    # here is a row a reader can reproduce.
    #
    # **Replaces a two-base-arms-plus-epsilon-split structure**, for two measured reasons. The old
    # base pair was `A_M gain` and `dG rbs-linker`: the second is an OFF-state MFE of an isolated
    # subsequence and is blind to the ON state -- two designs in one cell with an identical -7.20
    # differ 2.4x in how far the stem opens in tube 11. And the epsilon rows claimed a barrier
    # improvement whose lift over its base arm measured **+0.0388** against Green's 168, well inside
    # the 0.08 sampling noise, so they were two of six constructs spent on an unsupported claim.
    #
    # A duplicate is kept and FLAGGED rather than replaced: if two arms land on one design that is
    # a finding about the arms, and substituting something else would hide it. `distinct designs`
    # in the banner is the number to read.
    # The rows come from the ranking's own `arm_rows`, not from a second `cell_picks` call: a pair
    # was ranked on these exact designs, so emitting a different one would mean the panel shows
    # rows the pair was not chosen for.
    for _score, pair, _cell, arm_rows in taken:
        for arm in PANEL_ARMS:
            row = arm_rows.get(arm)
            if row is None:
                print(f"  {arm} on {pair}: no design in the cell carries it")
                continue
            mark = "  (already taken by another arm)" if row["switch"] in seen else ""
            print(f"  {pair:16s}{arm:14s}{row['switch'][:12]}...{mark}")
            # Each cell's OWN geometry, which is the chosen one unless ANY_GEOMETRY let the two
            # pairs differ. Taken from the row rather than from the panel, so the control string
            # cannot claim a geometry the design is not in.
            take(row, arm, f"six | pair {pair} | {row['geom']}")

    # The fourth arm, on its own pairs, after the six are fixed. `scored` is the ranking the six
    # came from, so "best pairs" means the same thing here as it does there.
    if ARM4:
        key_for = ARMS[ARM4]
        print(f"\n  arm 4 -- {ARM4} on the best {ARM4_PAIRS} pair(s), beside the six:")
        shown = 0
        for _worst, pair, cell, _rows in scored:
            if shown >= ARM4_PAIRS:
                break
            key = key_for(cell) if ARM4 in CELL_RELATIVE else key_for
            usable = [r for r in cell if key(r) != float("inf")]
            if not usable:
                print(f"  {pair:16s}{ARM4:14s}no design in the cell carries it")
                continue
            row = min(usable, key=key)
            mark = "  (already in the six)" if row["switch"] in seen else ""
            print(f"  {pair:16s}{ARM4:14s}{row['switch'][:12]}...{mark}")
            take(row, ARM4, f"arm 4 | pair {pair} | {row['geom']}")
            shown += 1
    return chosen


def pick(rows: list[dict], pairs: int, per_cell: int, pin: tuple[str, ...] = ()) -> list[dict]:
    """Two trigger pairs x two geometries x three objectives, pairs chosen by **quality**.

    **Accessibility no longer selects the pairs, and that is a measurement.** It used to: among
    pairs carrying enough gating designs in both geometries, the most accessible won its slot.
    On the finished sweep, over 179 controlled pairs, a pair's accessibility does not predict the
    quality of its best design at all -- signed so positive would mean "more accessible pairs
    carry better designs":

        definition                        combined   A_M ratio   opening SEP
        l_green (Green 2014 Eq. 4)          -0.102      +0.132        +0.005
        open_penalty energy (ours)          +0.064      -0.038        +0.056

    Both are noise, the two definitions agree with each other only at rho -0.200, and the cost of
    selecting on either was concrete: the most accessible pair carries a best ``combined`` of
    **62.7** while the best pair carries **95.4**, and that best pair ranks **96 of 179** on
    accessibility. Selecting on accessibility was discarding good gates for a property that does
    not predict them.

    So pairs are ranked by **best ``combined``** -- the objective with the best support against
    Green's measured switches -- and accessibility is reported per row instead. Nothing here is a
    threshold: a genuinely unreachable window would need a hard filter, and none is invented.

    **A single pair now shows every objective in both geometries**, which it could not do
    mid-run. Of the 460 gating cells the three objectives split three ways in 173, and **36
    pairs** have *both* geometries splitting all three ways -- a complete 6-row panel on one
    transcript site, the layout that was 0 of 26 when only 13% of the sweep was scored. The
    second slot is a long overlap, so the trigger-overlap length is still represented.

    Each row still names what its own comparison holds fixed:

    * **objective** -- controlled on the pair *and* the geometry, wherever a cell splits.
    * **geometry** -- controlled on the trigger pair.
    * **len_x** -- not controlled between the two slots; a trigger pair has one overlap length.
    """
    chosen: list[dict] = []
    seen: set[str] = set()

    def take(row: dict, arms: list[str], control: str) -> None:
        chosen.append(
            {
                **row,
                "arm": " + ".join(arms),
                "role": arms[0] if len(arms) == 1 else "agreed",
                "control": control,
                "multiplicity": len(arms),
                "duplicate": row["switch"] in seen,
            }
        )
        seen.add(row["switch"])

    by_pair: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        by_pair.setdefault(row["pair"], {}).setdefault(row["geom"], []).append(row)

    def quality(geoms: dict[str, list[dict]]) -> float | None:
        """A pair's quality is the best `combined` design in it, under the arm actually used.

        This read `f5` -- the weighted percentile mean -- while the arm had become an
        epsilon-constraint, so pairs were ranked by a rule no row was picked by. The constraint
        returns a BARRIER (lower better), so the pair score is its negation to keep "higher is
        better" for the caller, and a pair whose cells hold nothing usable stays None.
        """
        best = None
        for cells in geoms.values():
            usable = [r for r in cells if r.get("f2") is not None and r.get("barrier") is not None]
            if not usable:
                continue
            key = epsilon_combined(cells)
            value = -min(key(r) for r in usable)
            best = value if best is None else max(best, value)
        return best

    def splits(geoms: dict[str, list[dict]]) -> int:
        """How many of the two geometries split all three ways -- 2 is the ideal."""
        return sum(
            1 for cell in geoms.values() if len(cell_picks(cell, RANKING_ARMS)) == len(RANKING_ARMS)
        )

    def recodes(pair: str) -> bool:
        """Can BOTH of this pair's windows be recoded into a knockout?

        Asked here rather than left to `order_check`, so a pair that cannot produce its 01 and 10
        transcripts is never selected in the first place. Imported lazily and permissively: the
        panel must stay buildable without the codon table, and a missing table means every pair
        passes -- which is the status quo, not a silent new rejection.
        """
        try:
            import codon_variants as cv
            from full_sweep import read_fasta
            from recode_quality import recode_window

            here = Path(__file__).resolve().parent
            amino, fraction = cv.load_codon_table(here / "data" / "ecoli_codon_usage_table.csv")
            groups = cv.synonyms(amino)
            transcript = read_fasta(here / "mCherry_original.txt")
        except Exception:
            return True
        flat = [r for cells in by_pair[pair].values() for r in cells]
        for lo_key, hi_key in (("a_start", "a_end"), ("b_start", "b_end")):
            lo = min(int(r[lo_key]) for r in flat)
            hi = max(int(r[hi_key]) for r in flat)
            subs, breaks = recode_window(transcript, lo, hi, amino, fraction, groups)
            if not subs or breaks / subs < RECODE_FLOOR:
                return False
        return True

    eligible = []
    skipped_recode = []
    for pair, geoms in by_pair.items():
        # Same two tests as `controlled_pairs`, and `min(...) < per_cell` is the same statement as
        # `not all(... >= per_cell)`: it rejects a pair whose THINNEST geometry cell is too small.
        if REQUIRE_BOTH_GEOMETRIES and len(geoms) < 2:
            continue
        if min(len(v) for v in geoms.values()) < per_cell:
            continue
        if not recodes(pair):
            skipped_recode.append(pair)
            continue
        score = quality(geoms)
        if score is None:
            continue
        length = int(next(r["len_x"] for cells in geoms.values() for r in cells))
        # A pair whose cells both split three ways is preferred over a marginally better one
        # that does not: a cell that cannot split shows an agreement, not a comparison.
        eligible.append(((-splits(geoms), -score), pair, length))
    if skipped_recode:
        print(
            f"  {len(skipped_recode)} pair(s) dropped: a window recodes below "
            f"{RECODE_FLOOR:.0%} and cannot make its knockout transcript "
            f"-- {', '.join(sorted(skipped_recode))}"
        )
    eligible.sort()

    def recoded_bases(role: str, pair: str) -> set[int]:
        """Transcript positions the recoder would actually substitute in this pair's window.

        Imported lazily and tolerantly: ``codon_variants`` owns the recoding rules and this
        module must not become a second copy of them, but the panel has to be buildable without
        the codon table present. If it cannot be loaded, every base in the window is treated as
        changeable, which makes the disjointness test strictly more conservative rather than
        silently permissive.
        """
        index = 0 if role == "A" else 1
        lo, hi = windows(pair)[index]
        try:
            import codon_variants as cv
            from full_sweep import read_fasta

            here = Path(__file__).resolve().parent
            amino, fraction = cv.load_codon_table(here / "data" / "ecoli_codon_usage_table.csv")
            groups = cv.synonyms(amino)
            transcript = read_fasta(here / "mCherry_original.txt")
        except Exception:
            return set(range(lo, hi))
        changed: set[int] = set()
        for start in cv.codon_starts(lo, hi):
            codon = transcript[start : start + 3]
            acid = amino.get(codon)
            options = [c for c in groups.get(acid, ()) if c != codon] if acid else []
            if not options:
                continue
            best = min(
                options,
                key=lambda o: (
                    abs(fraction.get(o, 0.0) - fraction.get(codon, 0.0)),
                    abs(sum(1 for c in o if c in "GC") - sum(1 for c in codon if c in "GC")),
                ),
            )
            changed.update(
                start + offset
                for offset in range(3)
                if best[offset] != codon[offset] and lo <= start + offset < hi
            )
        return changed

    def windows(pair: str) -> list[tuple[int, int]]:
        """Both trigger windows of a pair, widest form, as spans on the transcript."""
        rows_here = [r for cells in by_pair[pair].values() for r in cells]
        a_start = min(int(r["a_start"]) for r in rows_here)
        a_end = max(int(r["a_end"]) for r in rows_here)
        b_start = min(int(r["b_start"]) for r in rows_here)
        b_end = max(int(r["b_end"]) for r in rows_here)
        return [(a_start, a_end), (b_start, b_end)]

    def disjoint(pair: str, taken: list[str]) -> bool:
        """Do this pair's windows avoid every window already on the panel?

        **A hard requirement, not a preference, and it is about the bench rather than the
        score.** The wet lab builds exactly four mCherry transcripts -- original, A-recoded,
        B-recoded, AB-recoded -- shared across the whole panel. If pair 1's trigger B window
        overlaps pair 2's trigger A window, then recoding B for pair 1 also destroys A for
        pair 2, and the transcript meant to realise one pair's 10 state silently realises
        something else for the other. The states stop being independently addressable and no
        amount of scoring detects it.

        Measured on the panel this was found in: ``522/439/4``'s trigger B spans 389-439 and
        ``423/658/7``'s trigger A spans 423-459, a **16 nt** overlap. Both pairs had been
        selected and the variants built, so three of the eight transcript/state combinations
        were wrong.
        """
        mine = dict(zip(("A", "B"), windows(pair), strict=True))
        for other in taken:
            theirs = dict(zip(("A", "B"), windows(other), strict=True))
            # CROSS-ROLE only. A overlapping A is harmless: both are recoded in the SAME
            # transcript (the A-recoded one), so they are removed together, which is what that
            # transcript is for. Same for B against B. The breaking case is A against B --
            # recoding one pair's B changes bases inside the other pair's A, so the transcript
            # meant to leave A intact destroys it.
            for mine_role, theirs_role in (("A", "B"), ("B", "A")):
                lo, hi = mine[mine_role]
                start, stop = theirs[theirs_role]
                if min(hi, stop) - max(lo, start) <= 0:
                    continue
                # And an overlap only breaks anything where a base actually CHANGES. The
                # recoding touches roughly a quarter of a window -- 12 of 49 bases in one
                # measured case -- so an overlap that happens to contain no substituted base
                # costs nothing. Only the codons the recoder would rewrite matter, and a codon
                # is only rewritable where a synonym exists, so this asks the recoder.
                if recoded_bases(theirs_role, other) & set(range(max(lo, start), min(hi, stop))):
                    return False
        return True

    slots: list[tuple[str, str]] = []
    # Pinned pairs take their slots first, in the order given. A pin is a judgement the ranking
    # cannot make -- "this pair carries the single best design even though its cell average is
    # not the best" -- and it still has to pass eligibility and disjointness, so a pin cannot
    # put a mismatched or overlapping pair on the panel.
    for pair in pin:
        if pair not in by_pair:
            print(f"  --pin {pair}: no gating designs, skipped")
            continue
        if not any(p == pair for _r, p, _length in eligible):
            print(f"  --pin {pair}: not eligible (needs both geometries, >= per-cell each)")
            continue
        if not disjoint(pair, [p for p, _ in slots]):
            print(f"  --pin {pair}: windows clash with an already-chosen pair, skipped")
            continue
        slots.append((pair, "pair + geometry | pinned"))
    for label, wanted in (("balanced", False), ("long overlap", True)):
        if len(slots) >= 2:
            break
        for rank, pair, length in eligible:
            if (length in LONG_LENX) is not wanted or pair in {p for p, _ in slots}:
                continue
            if not disjoint(pair, [p for p, _ in slots]):
                continue
            full = rank[0] == -2
            slots.append(
                (pair, f"pair + geometry | {label}" + ("" if full else " (partial split)"))
            )
            break

    for pair, control in slots:
        for geom in sorted(by_pair[pair]):
            cell = by_pair[pair][geom]
            picks = cell_picks(cell, RANKING_ARMS)
            index = {r["switch"]: r for r in cell}
            for switch, arms in sorted(picks.items(), key=lambda kv: -len(kv[1])):
                take(index[switch], arms, control)
    return chosen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pairs", type=int, default=3, help="cells per fully controlled comparison"
    )
    parser.add_argument("--per-cell", type=int, default=4, help="min feasible designs per cell")
    parser.add_argument("--out", default="", help="write to results/<name>.csv")
    parser.add_argument(
        "--lower3",
        default="",
        help="comma-separated lower3 levels to keep, e.g. wobble_GU,trigger_derived; "
        "empty keeps all. Shrinks the eligible pair pool sharply -- see LOWER3_KEEP",
    )
    parser.add_argument(
        "--any-geometry",
        action="store_true",
        help="let each pair bring its own geometry instead of forcing one on the panel. Opens the "
        "naive 18nt designs, where the best A_M ratio is 383.6 against Kim's 96.0, and gives up "
        "the comparison ACROSS the two pairs -- see ANY_GEOMETRY",
    )
    parser.add_argument(
        "--bench-floor",
        type=float,
        default=None,
        help="also require andness_variant <= this, in kcal/mol: the AND-ness of the four "
        "TRANSCRIPTS rather than of four tubes built by omitting a strand. -2.0 keeps 764 of "
        "1,317. Needs variant_leak.py to have run",
    )
    parser.add_argument(
        "--pair-arms",
        default="",
        help='which arms each pair is CHOSEN for, pipe-separated, e.g. "IED gain|A_M ratio" or '
        '"IED gain,A_M ratio|opening SEP,Barrier". Every arm is still emitted on every pair; this '
        "changes only which pairs are picked. Empty keeps maximise-the-worst",
    )
    parser.add_argument(
        "--arm4",
        default="",
        help="add a fourth arm's own picks beside the six, on --arm4-pairs pairs. The six do not "
        "move: the pairs are still ranked on the three base arms",
    )
    parser.add_argument(
        "--arm4-pairs",
        type=int,
        default=3,
        help="how many pairs the fourth arm picks on (default 3, so the panel is 6 + 3 = 9 rows)",
    )
    parser.add_argument(
        "--arm3",
        default="",
        help="replace the panel's third arm with this one, e.g. --arm3 Barrier. The first two "
        "are the ones with external support and do not move; the third is the open question",
    )
    parser.add_argument(
        "--distinct-arms",
        action="store_true",
        help="only choose pairs where the three arms pick three DIFFERENT designs, so the panel "
        "is six designs rather than four. Costs pair quality -- see DISTINCT_ARMS, measured",
    )
    parser.add_argument(
        "--six",
        action="store_true",
        help="the six-construct layout: two base arms on two pairs, arm 3 split between them",
    )
    parser.add_argument(
        "--share-trigger-a",
        action="store_true",
        help="allow the two panel pairs to use the same trigger-A window. Off by default: "
        "sharing it makes all six constructs depend on one window, and avoiding it "
        "costs 2% of the pair combinations",
    )
    parser.add_argument("--geometry", default="", help="fix the geometry for --six")
    parser.add_argument(
        "--pin",
        default="",
        help="comma-separated trigger pairs to place first, e.g. 625/124/6",
    )
    args = parser.parse_args(argv)

    results = Path(__file__).resolve().parent / "results"
    if args.any_geometry:
        global ANY_GEOMETRY
        ANY_GEOMETRY = True
        print("  --any-geometry: each pair brings its own")
    if args.bench_floor is not None:
        global VARIANT_GATING
        VARIANT_GATING = args.bench_floor
        print(f"  --bench-floor: also requiring andness_variant <= {VARIANT_GATING}")
    if args.pair_arms:
        global PAIR_ARMS
        PAIR_ARMS = tuple(
            tuple(arm.strip() for arm in group.split(",") if arm.strip())
            for group in args.pair_arms.split("|")
            if group.strip()
        )
    if args.arm4:
        if args.arm4 not in ARMS:
            print(f"  --arm4 {args.arm4}: no such arm. Known: {', '.join(ARMS)}")
            return 1
        global ARM4, ARM4_PAIRS
        ARM4 = args.arm4
        ARM4_PAIRS = args.arm4_pairs
        print(f"  --arm4: {ARM4} on the best {ARM4_PAIRS} pair(s), beside the six")
    if args.arm3:
        if args.arm3 not in ARMS:
            print(f"  --arm3 {args.arm3}: no such arm. Known: {', '.join(ARMS)}")
            return 1
        global PANEL_ARMS
        PANEL_ARMS = (*PANEL_ARMS[:2], args.arm3)
        print(f"  --arm3: the panel's arms are {', '.join(PANEL_ARMS)}")
    if args.distinct_arms:
        global DISTINCT_ARMS
        DISTINCT_ARMS = True
    if args.share_trigger_a:
        global DISTINCT_TRIGGER_A
        DISTINCT_TRIGGER_A = False
        print("  --share-trigger-a: the two pairs may use the same trigger-A window")
    if args.lower3:
        global LOWER3_KEEP
        LOWER3_KEEP = frozenset(v.strip() for v in args.lower3.split(",") if v.strip())
        print(f"  --lower3: keeping only {sorted(LOWER3_KEEP)}")
    every = load(results)
    if not every:
        print("  nothing scored yet -- run objective_energy.py first")
        return 1
    live = population(results, quiet=False)
    if not live:
        print(
            f"  nothing feasible -- no design has an ON state opening for <= {ON_CEILING} kcal/mol"
        )
        return 1

    # Percentiles are computed on the FEASIBLE set, before the gating floor, so f4 and f5 mean
    # the same thing here as in every earlier run and the floor does not silently rescale them.
    pool_rows = gating(live)
    print(
        f"\n  {len(every):,} scored -> {len(live):,} feasible "
        f"(open_11 <= {ON_CEILING}, scheme usable) -> {len(pool_rows):,} gating at f1 <= {GATING}"
    )
    for geom in sorted({r["geom"] for r in live}):
        sub = [r for r in live if r["geom"] == geom]
        gat = [r for r in pool_rows if r["geom"] == geom]
        print(
            f"    {geom:16s} {len(sub):6,} feasible  {len(gat):6,} gating   "
            f"best f1 {min(r['f1'] for r in sub):7.2f}"
        )
    feasible_rows = live
    live = pool_rows
    if not live:
        print(f"    nothing gates at f1 <= {GATING}")
        return 1

    pool = controlled_pairs(live, args.per_cell)
    print(
        f"\n  trigger pairs with >={args.per_cell} feasible designs in BOTH geometries: "
        f"{len(pool):,}"
    )
    if not pool:
        print("    none -- cannot control the pair across geometries on this data yet")
        return 1

    pinned = tuple(v.strip() for v in args.pin.split(",") if v.strip())
    global PINNED_FOR_RECIPE
    PINNED_FOR_RECIPE = pinned
    if args.six:
        panel = pick_six(gating(live), args.geometry, pinned)
    else:
        panel = pick(live, args.pairs, args.per_cell, pinned)
    # The two paths build different objects, so one banner cannot describe both. `--six` is the
    # bench panel: one geometry, two pairs, the three arms in PANEL_ARMS. `pick` is the survey.
    if args.six:
        extra = f" + {ARM4} on {ARM4_PAIRS} pair(s)" if ARM4 else ""
        print(
            f"\n  PANEL -- 2 pairs x 1 geometry x {len(PANEL_ARMS)} arms "
            f"({', '.join(PANEL_ARMS)}){extra} = {len(panel)} rows"
        )
    else:
        print(
            f"\n  PANEL -- {min(args.pairs, len(pool))} pairs x 2 geometries "
            f"x {len(RANKING_ARMS)} ranking objectives ({', '.join(RANKING_ARMS)}) "
            f"= {len(panel)} rows"
        )
    print(
        f"  opening SEP is the floor, not an arm: every row satisfies SEP <= {GATING} kcal/mol.\n"
    )
    print(
        f"  {'pair':17s}{'geometry':15s}{'chosen by':32s}"
        f"{'SEP':>8s}{'A_M':>8s}{'Bar':>7s}{'comb':>6s}{'ON':>6s}  closure / lower3"
    )
    last = None
    for row in panel:
        if last and row["pair"] != last:
            print()
        last = row["pair"]
        mark = "  *repeat*" if row["duplicate"] else ""
        print(
            f"  {row['pair_label']:17s}{row['geom']:15s}{row['arm']:32s}"
            f"{row['f1']:>8.2f}{(row['f2'] or 0):>8.1f}{(row['barrier'] or 0):>7.1f}"
            f"{(row['f5'] or 0):>6.1f}{row['open_11f']:>6.2f}  "
            f"{row['closure']} / {row['lower3']}{mark}"
        )
    # Distinct SWITCH STRINGS and distinct MEASUREMENTS, because they are not the same number and
    # the second is the one the bench budget is spent on. Measured: a panel reporting 6 of 6 held
    # two rows agreeing on every arm to three significant figures -- see `real_measurements`.
    distinct = len({r["switch"] for r in panel})
    real = 0
    for pair in dict.fromkeys(r["pair"] for r in panel):
        rows = {r["arm"]: r for r in panel if r["pair"] == pair}
        cell = [r for r in panel if r["pair"] == pair]
        real += real_measurements(cell, rows)
    print(f"\n  distinct designs: {distinct} of {len(panel)}")
    if args.six:
        # The cell here is the panel's own rows rather than the full cell, so the range this
        # tolerance is a fraction of is narrower than the one the FILTER used -- it reads as a
        # lower bound on how much the panel measures, which is the cautious direction.
        print(f"  distinct measurements: {real} of {len(panel)}  (arms agreeing within ARM_TIE)")
    # Over the whole feasible population, not over the panel's own rows: a rate computed on a
    # handful of cells is noise, and an earlier version of this reported 0 of 6 as structure
    # when the real figure over 470 cells was 22.6%.
    every_cell = by_cell(feasible_rows, args.per_cell)
    picks = [cell_picks(c) for c in every_cell.values()]
    names = list(ARMS)
    print(f"\n  how often two objectives pick the same design, over {len(picks)} cells:")
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            same = sum(
                1 for p in picks for sw, arms in p.items() if first in arms and second in arms
            )
            print(
                f"    {first:8s} == {second:8s}  {same:4d} of {len(picks):4d}  "
                f"({100.0 * same / max(len(picks), 1):5.1f}%)"
            )
    spread = {}
    for p in picks:
        spread[len(p)] = spread.get(len(p), 0) + 1
    print(f"\n  how the {len(ARMS)} split inside a cell:")
    for n_distinct in sorted(spread, reverse=True):
        label = {
            5: "five ways, one design each",
            4: "four ways",
            3: "three ways",
            2: "two ways",
            1: "unanimous",
        }.get(n_distinct, "")
        print(f"    {n_distinct} distinct picks: {spread[n_distinct]:4d} cells   {label}")
    print("\n  Each row shares its trigger pair with the row in the other geometry, so a")
    print("  geometry difference is the geometry rather than the transcript. Percentiles in")
    print("  f4 and f5 are relative to the feasible set, computed before the gating floor.")
    print("\n  Against Green's 168 measured switches (Spearman, positive = the objective is")
    print("  right): f5 +0.366, f2 +0.306, f4 +0.213, Barrier +0.179, f1 -0.107. That is why")
    print("  f1 ranks nothing here and f5 replaced f4. Reproduce: objective_vs_green.py")

    if args.out:
        path = results / f"{args.out}.csv"
        fields = [
            "role",
            "control",
            "multiplicity",
            "arm",
            "geom",
            "pair_label",
            "pair",
            "f1",
            "f2",
            "barrier",
            "access",
            "f4",
            "f5",
            "f2_gain",
            "ied_rbs_linker_11",
            "ied_rbs_linker_00",
            # The arm the panel ranks on. It was missing here, so every consumer read it back as
            # an empty cell -- `panel_data` reported ied_gain None on all six rows while the
            # selection that produced them had used it. The same failure COMPLETION_COLUMNS
            # documents, one layer further out.
            "ied_gain",
            "ied_gain_worst",
            # Per-window accessibility, both of them. `access` is their SUM, which cannot say
            # which of the two windows is the unreachable one -- and that was the only thing
            # anyone wanted to know from it.
            "access_a",
            "access_b",
            "l_local",
            "l_green",
            "dG_rbs_linker",
            "dG_arm_11",
            "engaged_arm_11",
            # The MFE counterpart of the column above it, which is the one the report's figures
            # agree with: a row passing engaged_arm_11 and failing this drew a shut main hairpin.
            "engages_stem_mfe",
            # How this panel was built, on every row, so a page showing several panels can say
            # what each one is instead of leaving the reader to guess from the rows.
            "recipe",
            # The role swap, which was computed and then dropped on the floor. Without these the
            # recoder builds the wrong four transcripts and the bench cannot tell which tube it
            # is looking at.
            "swap_used",
            "swap_states",
            "swap_recipe",
            # Carried so DOWNSTREAM readers can tell a repaired design from a drifted one.
            # order_check calls covers_drift on a panel row, and without this column it reported
            # six regenerated designs as covering a corrected base -- an alarm that would have
            # blocked an order, and indistinguishable from a real one.
            "drift_repaired",
            "pct_f1",
            "pct_f2",
            "pct_f2_gain",
            "pct_barrier",
            "pct_access",
            "aug_11",
            # A_M(11) itself, so the report can show the ON state and derive worst(A_M) as
            # A_M(11) - f2_gain. Without the column the derived tile has a statistics bar and no
            # value, and `rngBar` then renders nothing at all -- the same silent blank that has
            # already cost three op-state bars and the B-toehold tile.
            "A_M_11",
            "lock",
            "lock01",
            "d_off",
            "r2_star_00",
            "rbs11_open",
            "hairpin_worst",
            "offtarget",
            "offtarget_blocks",
            "open_11",
            "open_00",
            "open_01",
            "open_10",
            "scheme",
            "closure",
            "upper3",
            "lower3",
            "len_x",
            "xstar_start",
            "a_start",
            "a_end",
            "b_start",
            "b_end",
            "duplicate",
            "source",
            "switch",
        ]
        # Stamped at write time rather than inside `pick_six`, so there is one string per file and
        # rows of the same panel cannot disagree about how that panel was built.
        line = recipe()
        for row in panel:
            row["recipe"] = line
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(panel)
        print(f"\n  written: {path.name}")
        print(f"  recipe: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
