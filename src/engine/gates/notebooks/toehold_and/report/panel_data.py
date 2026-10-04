"""Build the report JSON for the panel, from ``results/panel_three.csv``.

    uv run python src/engine/gates/notebooks/toehold_and/report/panel_data.py

This lived in a session scratchpad, which meant the report could only be rebuilt while that
session was alive. It is notebook code and belongs in the notebook.

Every number comes through ``FoldEngine``, **including the drawing coordinates**. The house rule
that keeps ``import RNA`` behind the adapter applies to ``gates/notebooks/`` as well -- the
workbench is exempt from the shared-tool rule and from nothing else -- so this calls
``FoldEngine.layout_coordinates``, which also trims the trailing padding point that the raw
ViennaRNA vector carries and that a private call would rediscover as a stray point at the origin.
"""

import csv
import glob
import json
import math
import statistics as st
import sys
from pathlib import Path

# Derived from this file, never hard-coded: the scratchpad copy carried an absolute path to
# one machine's checkout, which is not a thing a committed script may depend on.
NB = Path(__file__).resolve().parent.parent
REPO = NB.parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(NB))

import objective_energy as oe  # noqa: E402
import objective_panel as op  # noqa: E402
from full_sweep import read_fasta  # noqa: E402

from engine.gates.tools.folding import FoldEngine  # noqa: E402

#: Green 2014 Table S4 endogenous mCherry sensors and the sequence a colleague has already run,
#: located by exact substring against this transcript rather than by trusting a paper's
#: coordinate. A panel row that overlaps one of these is a row with prior bench evidence.
REFERENCES = (
    ("Green sensor A", 378, 408),
    ("Green sensor B", 531, 567),
    ("Green sensor C", 592, 628),
    ("colleague probe", 591, 624),
)

#: The secondary hairpin, 5'-anchored, with ``k2* = (sws_end - 50 - 2*len_x) / 2``:
#: cap(3) r2*(32) sw_x(len_x) k2*(k2) sec_loop(15) sec_z(k2) x*(len_x). Verified to close on
#: sws_end for every len_x in the panel.
SEC_FIXED = (("cap", 3), ("r2*", 32))


def secondary_domains(switch: str, len_x: int) -> list[dict]:
    sws_end = len(switch) - 75
    k2 = (sws_end - 50 - 2 * len_x) // 2
    spans, at = [], 0
    for name, width in (*SEC_FIXED, ("sw_x", len_x), ("k2*", k2), ("sec_loop", 15), ("sec_z", k2)):
        spans.append({"name": name, "s": at, "e": at + width})
        at += width
    spans.append({"name": "x*", "s": at, "e": at + len_x})
    assert at + len_x == sws_end, f"secondary layout misses sws_end by {sws_end - at - len_x}"
    return spans


def unpaired(folder: FoldEngine, strands: str) -> list[float]:
    """Per-base probability of being unpaired.

    The matrix is **symmetric with a zero diagonal**, so the paired probability at ``i`` is the
    sum of row ``i`` alone. An earlier version added ``m[i][j] + m[j][i]`` and reported an
    impossible "max delta +2.000"; that is the bug this comment exists to prevent recurring.
    """
    matrix = folder.pooled_pair_probabilities(strands)
    return [round(max(0.0, min(1.0, 1.0 - sum(row))), 3) for row in matrix]


def engaged_by_a(
    folder: FoldEngine,
    strands: str,
    xstar: tuple[int, int],
    arm: tuple[int, int],
    block: tuple[int, int],
) -> dict[str, float]:
    """Does trigger A take the freed x* **and** open the main stem? Both shares, and their min.

    ``x*`` alone is actively misleading. Measured on the panel, three designs score 0.846, 0.970
    and 0.884 on x*-by-A -- which reads as success -- while their ``main_pre_star``-by-A is 0.020,
    0.047 and 0.043. A has taken the lock and left the main stem shut, so the gate does not open
    and the x* term says it did.

    All four of the panel's Barrier picks sit at or below 0.047 on the arm. That follows: the
    Barrier arm minimises the activation energy, and a design whose main stem A never opens has
    little to activate. It is the same failure the hairpin floor catches from the other side,
    reached by a different route.

    Returns ``{"xstar", "arm", "min"}``. ``min`` is the verdict and was for a while the only
    thing returned, but it cannot say which half failed, and the two halves fail for opposite
    reasons: a low ``xstar`` with a high ``arm`` is A opening the stem without taking the lock,
    while a high ``xstar`` with a low ``arm`` is A taking the lock and leaving the stem shut.
    Only the second is the mode the Barrier arm keeps producing, so the card shows both.
    """
    matrix = folder.pooled_pair_probabilities(strands)
    xstar_share, arm_share = (
        sum(matrix[i][j] for i in range(lo, hi) for j in range(*block)) / (hi - lo)
        for lo, hi in (xstar, arm)
    )
    # Both, not only the minimum. The minimum is the verdict, but it hides WHICH half failed, and
    # the two failures mean opposite things: a low x* share with a high arm share is A opening the
    # stem without taking the lock, a high x* with a low arm is A taking the lock and leaving the
    # stem shut. Only the second is the failure mode the Barrier arm keeps producing.
    return {
        "xstar": round(xstar_share, 3),
        "arm": round(arm_share, 3),
        "min": round(min(xstar_share, arm_share), 3),
    }


def lock_term(
    folder: FoldEngine, strands: str, xstar: tuple[int, int], block: tuple[int, int] | None
) -> float:
    """What x* must be doing in this tube, as the term ``candidates.py`` scores.

    Four different quantities, one per state, because the lock's job changes state to state:

        00  x* paired with sw_x        the lock holds with no trigger
        10  x* paired with sw_x        the lock still holds with trigger A alone
        01  x* unpaired               trigger B alone frees it
        11  x* paired with trigger A   A then takes the freed site

    All four read higher-is-right. An earlier version of this file showed
    ``FoldEngine.p_open`` of the x* window in all four states instead -- one quantity four
    times, and the strictest available: the *joint* probability that all len_x bases are
    simultaneously unpaired, which over 4 to 7 nt is near zero whatever the lock is doing. So
    the card reported 0.00 to 0.01 in every state and said "x* open" four times, which is
    both uninformative and mislabelled for the three states where being open is wrong.

    The matrix is symmetric with a zero diagonal, so a position's paired probability is the
    sum of its row -- one term per pair, never two.
    """
    matrix = folder.pooled_pair_probabilities(strands)
    lo, hi = xstar
    if block is None:
        return round(sum(max(0.0, 1.0 - sum(matrix[i])) for i in range(lo, hi)) / (hi - lo), 3)
    return round(sum(matrix[i][j] for i in range(lo, hi) for j in range(*block)) / (hi - lo), 3)


#: The Shine-Dalgarno itself, inside ``rbs_loop``: the loop is ``RBS_FLANK`` (7 nt) followed by
#: ``RBS_PROKARYOTIC`` (11 nt), and only the second half is the ribosome's binding site.
RBS_FLANK_LEN = 7


def rbs_span(switch: str) -> tuple[int, int]:
    loop = oe.domains(switch)["rbs_loop"]
    return (loop[0] + RBS_FLANK_LEN, loop[1])


def xstar_partners(
    folder: FoldEngine, strands: str, xstar: tuple[int, int], spans: dict[str, tuple[int, int]]
) -> dict[str, float]:
    """What x* is paired to in this tube, by domain -- only partners above 1%.

    This exists because "x* freed by B alone" is the weakest term in the lock, 0.29 to 0.51 on
    the panel, and the obvious reading -- that B fails to open the lock -- is **wrong**.
    Measured, B releases the secondary stem *completely*: the x*-to-sw_x term is **0.000**, and
    the x*-to-B term is 0.000 too. The missing 0.5 to 0.7 goes to a **different partner**, and
    on the panel it is mostly the **linker** (0.27 to 0.61) with some of ``sec_z`` (0.09 to
    0.42). x* is freed and then immediately re-paired, so it is not available for trigger A.

    That is an actionable finding rather than a score: the linker is a constant we choose.
    """
    matrix = folder.pooled_pair_probabilities(strands)
    width = xstar[1] - xstar[0]
    out = {}
    for name, (lo, hi) in spans.items():
        if name == "x*":
            continue
        share = (
            sum(matrix[i][j] for i in range(*xstar) for j in range(lo, min(hi, len(matrix))))
            / width
        )
        if share > 0.01:
            out[name] = round(share, 3)
    return out


def boltzmann_share(folder: FoldEngine, strands: str, structure: str) -> float | None:
    """What share of the ensemble sits in exactly this structure: ``exp(-(E - G) / RT)``.

    ``E`` is the structure's own free energy and ``G`` the ensemble free energy over all
    structures, pooled across strand orderings for a complex. The quotient of their Boltzmann
    weights is by definition that structure's equilibrium probability.

    **Expect very small numbers and read them as a comparison, not as a verdict.** This is one
    structure out of a number that grows exponentially with length, so for a 250-nt complex even a
    dominant fold holds a tiny absolute share -- that is a property of counting microstates, not a
    sign the prediction is bad. What the number is good for is the ratio between the MFE and the
    centroid, and orders of magnitude between designs: a design whose MFE holds 1e-4 of the
    ensemble has a far more committed fold than one whose MFE holds 1e-12, and only the second
    makes a single drawing misleading.
    """
    energy = folder.structure_energy(strands, structure)
    if energy is None:
        return None
    ensemble = folder.pooled_partition(strands)
    return math.exp(-(energy - ensemble) / folder.rt)


def _drawing(folder: FoldEngine, structure: str) -> dict:
    """One structure as the viewer needs it: pair list plus naview coordinates."""
    stack: list[int] = []
    pairs: list[list[int]] = []
    for index, char in enumerate(structure):
        if char == "(":
            stack.append(index)
        elif char == ")":
            pairs.append([stack.pop(), index])
    return {
        "xy": [[round(x, 1), round(y, 1)] for x, y in folder.layout_coordinates(structure)],
        "bp": pairs,
    }


def state_block(folder: FoldEngine, strands: str, xstar: tuple[int, int]) -> dict:
    """One tube: the ensemble strip, and the TWO structures worth drawing.

    The MFE is one structure and can carry a small share of the Boltzmann weight, in which
    case drawing it alone presents a fold the molecule mostly is not in. The centroid keeps
    only the pairs the ensemble broadly agrees on, so where the two drawings disagree the
    disagreement is the information -- a helix in the MFE and not the centroid is a helix
    the ensemble is split on.

    Neither is ranked above the other and no measurement reads either of them: every number
    on the card comes from the partition function. These are the picture.
    """
    flat = strands.replace("&", "")
    mfe = folder.mfe(strands)
    centroid = folder.centroid(strands)
    cuts, at = [], 0
    for strand in strands.split("&")[:-1]:
        at += len(strand)
        cuts.append(at)
    return {
        "open": unpaired(folder, strands),
        "cuts": cuts,
        "seq": flat,
        "dG": round(mfe.energy, 1),
        "dG_centroid": round(centroid.energy, 1),
        "p_mfe": boltzmann_share(folder, strands, mfe.structure),
        "p_centroid": boltzmann_share(folder, strands, centroid.structure),
        **_drawing(folder, mfe.structure.replace("&", "")),
        "centroid": _drawing(folder, centroid.structure.replace("&", "")),
    }


def mechanism(folder: FoldEngine, switch: str, trig_a: str, trig_b: str) -> dict:
    """Binding energies, where trigger A actually binds, and why ``coop`` is not cooperativity.

    ``coop = dG_bind(A|B) - dG_bind(A)`` was presented as the ordering cost the AND gate pays.
    **It is not**, and the reason is that the two terms are not the same binding. Measured on all
    seven panel designs, the Jaccard overlap between A's switch contacts with and without B is
    **0.00 in every one**:

        without B   A binds the SECONDARY region only
        with B      A binds secondary + main_pre_star + bulge_star + k1_star -- the main stem

    So ``dG_bind(A)`` prices A stuck to the wrong site and ``dG_bind(A|B)`` prices A engaging the
    intended one. Their difference compares two different events, which is why ``coop`` comes out
    **positive** for some designs -- A's off-site binding can be the stronger of the two, and that
    means nothing mechanistically.

    ``dG_bind(A)`` and ``dG_bind(B)`` are not comparable to each other either: B is 49 nt against
    the 32-nt r2* arm and lands near -60 kcal/mol, A is 35 nt against a short arm and lands near
    -10. Neither a difference nor a ratio between them carries a mechanism.

    So this returns the contact sites and an ``interpretable`` flag beside the energies. What the
    gate actually needs to know -- did A engage the main stem -- is ``engages_stem``, the share of
    A's contacts landing in the main stem's ascending arm.
    """

    def energy(strands: str) -> float | None:
        result = folder.mfe(strands)
        return None if result is None else result.energy

    e_sw, e_a, e_b = energy(switch), energy(trig_a), energy(trig_b)
    e_swa, e_swb = energy(f"{switch}&{trig_a}"), energy(f"{switch}&{trig_b}")
    e_all = energy(f"{switch}&{trig_a}&{trig_b}")
    if None in (e_sw, e_a, e_b, e_swa, e_swb, e_all):
        return {}
    bind_a = e_swa - e_sw - e_a
    bind_b = e_swb - e_sw - e_b
    bind_a_given_b = e_all - e_swb - e_a
    bind_b_given_a = e_all - e_swa - e_b
    assert abs((bind_a_given_b - bind_a) - (bind_b_given_a - bind_b)) < 1e-9, (
        "cooperativity is symmetric by construction; a difference here means one of the "
        "six energies is not the quantity it is named after"
    )

    # One implementation of "where does A touch the switch", in `objective_energy`, because the
    # sweep now filters on the same question and two copies would be two answers to it.
    alone = oe.a_contacts(folder, f"{switch}&{trig_a}", len(switch), len(trig_a))
    with_b = oe.a_contacts(folder, f"{switch}&{trig_a}&{trig_b}", len(switch), len(trig_a))
    union = alone | with_b
    overlap = len(alone & with_b) / len(union) if union else 1.0
    arm = oe.ascending_arm(switch)
    return {
        "dG_bind_A": round(bind_a, 1),
        "dG_bind_B": round(bind_b, 1),
        "dG_bind_A_given_B": round(bind_a_given_b, 1),
        "dG_bind_B_given_A": round(bind_b_given_a, 1),
        "coop": round(bind_a_given_b - bind_a, 1),
        # "What does B gain from A" is THE SAME NUMBER, and not approximately:
        #     coop   = (e_all - e_swb - e_a) - (e_swa - e_sw - e_a)
        #     coop_b = (e_all - e_swa - e_b) - (e_swb - e_sw - e_b)
        # both reduce to `e_all - e_swa - e_swb + e_sw`; the single-strand terms cancel.
        # Measured over all 23 panel designs, max |coop - coop_b| = 0.0. So this quantity
        # is a symmetric coupling between the two bindings and carries no direction at
        # all -- it cannot answer which trigger helps which. Asserted rather than
        # commented, because shipping it twice under two labels would read as two
        # independent measurements agreeing.
        "coop_symmetric": True,
        # Below the threshold the two energies price different bindings, so their difference is
        # not a cooperativity. 0.3 is a declared line, not a measured one: every panel design
        # sits at 0.00, so nothing here depends on where in (0, 1) it is drawn.
        "coop_ok": overlap >= 0.3,
        "site_overlap": round(overlap, 2),
        "engages_stem_alone": round(len(alone & arm) / max(len(alone), 1), 2),
        "engages_stem_with_B": round(len(with_b & arm) / max(len(with_b), 1), 2),
    }


def reference_overlap(
    label: str, start: int, stop: int, a_span: tuple[int, int], b_span: tuple[int, int]
) -> dict | None:
    """How many nt of a published sensor land on each trigger window, and on which.

    ``None`` when neither window touches it, so the caller filters on the return value
    instead of recomputing the same two intersections in a comprehension guard.
    """
    nt = {
        name: max(0, min(span[1], stop) - max(span[0], start))
        for name, span in (("A", a_span), ("B", b_span))
    }
    hit = [name for name, count in nt.items() if count > 0]
    if not hit:
        return None
    return {
        "name": label,
        "nt": sum(nt.values()),
        "which": " and ".join(f"{name} ({nt[name]} nt)" for name in hit)
        if len(hit) > 1
        else f"window {hit[0]}",
    }


def describe(values: list[float]) -> dict:
    """Mean, sd and max beside the median -- a median alone has argued both sides before."""
    # Coerced here rather than at every call site. Only some columns are parsed to float by
    # `objective_panel.load`; the rest arrive as CSV strings, and the moment a new key was added
    # to the statistics list this raised "must be real number, not str" -- which failed the whole
    # build, so the page silently kept the previous JSON and the new tiles read empty.
    clean = []
    for value in values:
        if value is None or value == "":
            continue
        try:
            clean.append(float(value))
        except (TypeError, ValueError):
            continue
    if not clean:
        return {}
    return {
        "min": min(clean),
        "max": max(clean),
        "mean": round(st.fmean(clean), 3),
        "sd": round(st.pstdev(clean), 3) if len(clean) > 1 else 0.0,
        "median": round(st.median(clean), 3),
    }


#: Tile key on the card -> the column that key is computed from on a population row. The cards
#: use short names and the population rows use the CSV ones, and a mismatch makes
#: return {} so the bar vanishes rather than erroring.
#: Tile key -> the population column it is measured from, where the two differ.
#:
#: ``rngBar`` looks up ``STATS[key]`` and renders **nothing** when the key is missing, with no error
#: -- it has silently blanked bars twice now, three op-state bars once and the B-toehold tile since
#: the day it was added. So every tile key must appear in the statistics list below, and any key
#: whose name differs from its column must be mapped here.
#:
#: ``f2_worst`` has no column at all: it is ``A_M(11) - f2_gain``, an identity, so it is computed
#: into the population here rather than stored twice.
STAT_SOURCE = {
    "ied11": "ied_rbs_linker_11",
    "dgarm11": "dG_arm_11",
    "am11": "A_M_11",
}


def main(argv=None) -> int:
    # Two panels, not one. A row FILTER hides designs from a panel whose pairs and geometries were
    # already chosen without the constraint, so the structure still reflects the unconstrained
    # population -- the pairs, the geometries, which cells split which way. A panel BUILT under the
    # constraint is a different object, and comparing them is the point. Both are carried, tagged
    # with `panelset`, and a view button switches.
    argv = list(argv or sys.argv[1:])
    # Every panel named on the command line, in order; the first is the page's default. They were
    # three fixed slots -- `name`, `alt`, `third` -- which is why a fourth panel could not be shown
    # at all and the comparison the bench needs had to be read out of a terminal.
    names = argv or ["panel_three"]
    panel: list[dict] = []
    by_switch: dict[str, dict] = {}
    recipes: dict[str, str] = {}
    for position, panel_name in enumerate(names):
        path = NB / "results" / f"{panel_name}.csv"
        if not path.exists():
            print(f"  {panel_name}.csv not built -- its view will be empty")
            continue
        with path.open(encoding="utf-8") as handle:
            rows_here = [
                {
                    **r,
                    # The first panel is "default" so every existing view keeps working; the rest
                    # are identified by their own file name.
                    "panelset": "default" if position == 0 else panel_name,
                    "panelname": panel_name,
                    # Per PANEL, because a design shared between a swapped panel and an
                    # unswapped one has different states in each and one row cannot hold both.
                    # The merge keeps the first panel's row, so without this the swapped panel's
                    # states were simply discarded -- which is why three of six cards read the
                    # same state off every transcript.
                    "swap_by_panel": {panel_name: (r.get("swap_states") or "")},
                }
                for r in csv.DictReader(handle)
            ]
        added = 0
        for row in rows_here:
            existing = by_switch.get(row["switch"])
            if existing is None:
                panel.append(row)
                by_switch[row["switch"]] = row
                added += 1
                continue
            # A design chosen by more than one panel is ONE row carrying every panel's name, not
            # one row per panel: duplicating it would double it in every count and in the
            # comparison table. The arm names accumulate too, because a shared design is usually
            # shared by DIFFERENT arms -- and showing only the first panel's arm was read as
            # "sep3 chose dG arm (ON)" when sep3 has no such arm.
            if panel_name not in existing["panelname"]:
                existing["panelname"] = f"{existing['panelname']} + {panel_name}"
            existing.setdefault("swap_by_panel", {})[panel_name] = row.get("swap_states") or ""
            if row["arm"] not in existing["arm"]:
                existing["arm"] = f"{existing['arm']} + {row['arm']}"
        # One recipe per panel file. Taken from the rows rather than restated here, so the page
        # can only ever show what the panel actually recorded about itself.
        said = {r.get("recipe") for r in rows_here if r.get("recipe")}
        recipes[panel_name] = sorted(said)[0] if said else ""
        if len(said) > 1:
            print(f"    {panel_name}.csv carries {len(said)} different recipes -- rebuild it")
        print(f"  {len(rows_here)} rows from {panel_name}.csv, {added} new")
        if recipes[panel_name]:
            print(f"    {recipes[panel_name]}")
    if not panel:
        print("  no panel rows at all -- run objective_panel.py --six first")
        return 1

    # The folding engine and the transcript, built once. One instance, because its cache lives on
    # the instance and a second one would be a cold cache folding at the same temperature twice.
    folder = FoldEngine(37.0)
    transcript = read_fasta(NB / "mCherry_original.txt")

    # The reference population for every statistics bar and every "best in sweep" row. This
    # used to be `op.feasible(op.load(...))` with a comment claiming it matched the panel's own
    # set; it did not, because `feasible` reads columns that only the side-table joins supply and
    # a missing column filters nothing. 14,823 against the panel's 7,568. `op.population` is now
    # the single definition and `objective_panel.main` calls the same function.
    population = op.population(NB / "results")
    print(f"  {len(population):,} feasible designs as the reference population")

    # ---- the unconstrained best, one per (len_x, objective) -----------------------------
    # The panel's rows answer "which objective is right, with everything else held fixed", which
    # costs quality: a controlled cell is rarely the best cell. These rows answer the other
    # question -- what is the best this sweep can do at each overlap length, ignoring every
    # control requirement. They are NOT a comparison and are marked so; ordering one tells you
    # nothing about why it won.
    gating = op.gating(population)
    extra = []
    chosen_switches = {r["switch"] for r in panel}
    for length in sorted({int(r["len_x"]) for r in gating}):
        subset = [r for r in gating if int(r["len_x"]) == length]
        for arm, key in op.RANKING_ARMS.items():
            # `combined` is an epsilon-constraint and needs the cell to find its A_M ceiling, so
            # it is a factory rather than a key. Here the "cell" is every gating design at this
            # len_x, which is the right scope for "the best the sweep can do at this overlap".
            resolved = key(subset) if arm in op.CELL_RELATIVE else key
            best = min(subset, key=resolved)
            if best["switch"] in chosen_switches:
                continue
            chosen_switches.add(best["switch"])
            extra.append(
                {
                    **best,
                    "arm": arm,
                    "role": f"best {arm}, len_x {length}",
                    "control": "nothing - best in the sweep",
                    "multiplicity": 1,
                    "duplicate": "False",
                }
            )
    print(f"  + {len(extra)} unconstrained best-in-sweep rows")
    panel = list(panel) + extra

    # ---- completions, when complete_panel.py has been run -------------------------------
    # Merged PER COLUMN across every completion file, not first-file-wins.
    #
    # **The third appearance of the same failure, and the one that hid longest.** There are 30-odd
    # `completions*.csv` files, written by different `--metrics` runs, and each carries only the
    # columns its run asked for. `setdefault(switch, row)` kept the FIRST file's row whole, so a
    # switch present in an early run reached the page with that run's columns and nothing else --
    # `land_run_g0/g1/g2` and `land_site_nt` read as absent on every card while
    # `objective_panel.population` had them at 100% from the same files. Measured: 2,268 of 2,268
    # on the population, 0 of 37 on the cards.
    #
    # `objective_panel.add_completions` has always merged field by field; this is the same loop,
    # which is why the two disagreed. An empty cell never overwrites a value, so a run that did
    # not compute a column cannot erase it.
    completions: dict[str, dict] = {}
    for path in sorted(glob.glob(str(NB / "results" / "completions*.csv"))):
        with open(path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                switch = row.get("switch")
                if not switch:
                    continue
                into = completions.setdefault(switch, {})
                for field, value in row.items():
                    if value not in (None, ""):
                        into[field] = value
    if completions:
        filled = {}
        for found in completions.values():
            for field in found:
                filled[field] = filled.get(field, 0) + 1
        print(f"  joined completions for {len(completions):,} switches, {len(filled)} columns")
        # Coverage is reported against the designs the page USES, not against every switch any
        # completion file mentions: the later runs targeted the feasible set, so measuring them
        # over all 16,140 makes a complete column look half-finished. A column missing from the
        # panel's own rows is the one worth naming.
        panel_switches = {r["switch"] for r in panel}
        thin = sorted(
            field
            for field in filled
            if sum(
                1
                for switch in panel_switches
                if (completions.get(switch) or {}).get(field) not in (None, "")
            )
            < len(panel_switches)
        )
        if thin:
            print(f"    not on every panel row: {', '.join(thin)}")
    else:
        print("  no completions*.csv yet -- run complete_panel.py for off-target and l_green")

    cands = []
    for index, row in enumerate(panel):
        switch = row["switch"]
        len_x = int(row["len_x"])
        a_start, a_end = int(row["a_start"]), int(row["a_end"])
        b_start, b_end = int(row["b_start"]), int(row["b_end"])
        trig_a = transcript[a_start:a_end].upper().replace("T", "U")
        trig_b = transcript[b_start:b_end].upper().replace("T", "U")
        main_d = [{"name": n, "s": s, "e": e} for n, (s, e) in oe.domains(switch).items()]
        sec_d = secondary_domains(switch, len_x)
        all_d = sec_d + main_d
        xstar = next((d["s"], d["e"]) for d in sec_d if d["name"] == "x*")
        sw_x = next((d["s"], d["e"]) for d in sec_d if d["name"] == "sw_x")
        codons = op.early_codons(switch)
        # `x` is the stretch of TRIGGER A that the secondary hairpin holds -- the switch's `sw_x`
        # domain is that stretch and `x*` is its reverse complement.
        #
        # **It is not a motif the two triggers share, and an earlier version of this said it was.**
        # Measured on the panel: `sw_x` sits at trigger A offset 18 on both pairs, and in trigger B
        # it is absent on one pair and present at offset 41 on the other -- a coincidence, not a
        # structure. That is scheme C working as designed: where trigger A's x and trigger B's own
        # overlap region disagree, each position is assigned to serve A, to serve B, or to hold the
        # lock shut, so the switch's copy matches ONE of them by construction. Requiring it in both
        # would have failed a correct design.
        #
        # The span is found rather than derived, because the offset is not the one the domain
        # layout implies (18 measured against 15 derived) and an ordering sheet is the wrong place
        # to carry an assumed constant. The sheet checks the span the way that catches a wrong one:
        # the trigger, cut at these coordinates, must equal this sequence.
        xseq = switch[sw_x[0] : sw_x[1]]
        x_at = trig_a.find(xseq)
        x_span = [a_start + x_at, a_start + x_at + len(xseq)] if x_at >= 0 else None

        def number(key: str, row: dict = row) -> float | None:
            raw = row.get(key)
            return float(raw) if raw not in (None, "") else None

        cand = {
            "role": row["role"],
            "control": row["control"],
            "panelset": row.get("panelset") or "default",
            # The role swap, which the exporter needs and which had not reached here -- the SIXTH
            # computed column to stop at a layer boundary. Without it every design read the same
            # state off the same transcript, which is exactly what a swapped panel does not do,
            # and the realisation matrix flagged the second pair as not realising its state.
            "swap_states": row.get("swap_states") or "",
            "swap_by_panel": row.get("swap_by_panel") or {},
            "swap_recipe": row.get("swap_recipe") or "",
            "swap_used": str(row.get("swap_used") or "").lower() == "true",
            # Which panel FILE this row came from, so the page can offer one view per panel
            # instead of a fixed pair of names. `panelset` is the view; this is the provenance.
            "panelname": row.get("panelname") or "",
            "mult": int(row["multiplicity"]),
            "arm": row["arm"],
            "geom": row["geom"],
            "pair": row["pair_label"],
            "dup": row["duplicate"] == "True",
            "scheme": row["scheme"],
            "closure": row["closure"],
            "upper3": row["upper3"],
            "lower3": row["lower3"],
            "len_x": len_x,
            "nt": len(switch),
            "seq": switch,
            "trigA": trig_a,
            "trigB": trig_b,
            "wa": [a_start, a_end],
            "wb": [b_start, b_end],
            "f1": number("f1"),
            "f2": number("f2"),
            "barrier": number("barrier"),
            "access": number("access"),
            "f4": number("f4"),
            "f5": number("f5"),
            "f2_gain": number("f2_gain"),
            # worst(A_M), the OFF state the gain is measured against and the ratio's denominator.
            # DERIVED from the two stored columns rather than refolded: worst = A_M(11) - gain is an
            # identity, so recomputing it would be a second number for one quantity, and the four
            # tubes are the expensive part. Shown because the gain alone cannot see it -- measured
            # over 2,052 gating designs, rho(gain, worst A_M) = -0.019, while rho(gain, A_M(11)) =
            # +0.940. The gain IS the ON state; this column is the half it is blind to.
            "f2_worst": (
                None
                if number("A_M_11") is None or number("f2_gain") is None
                else round(number("A_M_11") - number("f2_gain"), 4)
            ),
            "am11": number("A_M_11"),
            "ied11": number("ied_rbs_linker_11"),
            # The arm itself, beside the ON half it is computed from. Stored on the
            # population by `objective_panel.add_ied_gain`, so this reads it rather
            # than subtracting a second time.
            "ied_gain": number("ied_gain"),
            "dgarm11": number("dG_arm_11"),
            "engarm11": number("engaged_arm_11"),
            "pct": {k: number(f"pct_{k}") for k in ("f1", "f2", "f2_gain", "barrier", "access")},
            "op": {s: number(f"open_{s}") for s in ("00", "01", "10", "11")},
            "domains": main_d,
            "sec": sec_d,
            "alld": sec_d + main_d,
            "stem": [list(span) for span in oe.main_stem_arms(switch)],
            "codons": codons,
            "rare": [c for c in codons if c in op.RARE_CODONS],
            "refs": [
                ref
                for label, start, stop in REFERENCES
                if (
                    ref := reference_overlap(label, start, stop, (a_start, a_end), (b_start, b_end))
                )
            ],
            "mech": mechanism(folder, switch, trig_a, trig_b),
            # Empty until complete_panel.py has run. Kept as a dict rather than flattened so a
            # missing run is visibly absent instead of silently defaulting.
            "extras": {
                k: v
                for k, v in (completions.get(switch) or {}).items()
                if k != "switch" and v not in (None, "")
            },
            # RBS(11), in the form the AUG check is NOT in: the joint probability that the whole
            # Shine-Dalgarno is open at once, reported as the energy it costs to force it open.
            # `A_M` and `aug_*` are MEANS of per-base unpaired probabilities, because over 18 nt
            # a joint probability is ~1e-22 and would put every design below every threshold.
            # The SD is 11 nt and the energy form does not underflow, so the strict question is
            # answerable here: the ribosome needs the whole site open together, not on average.
            #
            # Only state 11 is interesting -- in the other three the RBS sits open in its loop by
            # design, which is the whole point of the architecture.
            "rbs11": folder.open_penalty(f"{switch}&{trig_a}&{trig_b}", (rbs_span(switch),)),
            "rbs11_p": folder.p_open(f"{switch}&{trig_a}&{trig_b}", rbs_span(switch)),
            "rbs_span": list(rbs_span(switch)),
            # Both were measured for every design in the sweep and neither reached the page.
            "r2_star_00": number("r2_star_00"),
            # Both windows, not their sum. `access` is `access_a + access_b`, which cannot say
            # which of the two is the unreachable one -- and on this panel that is the open
            # question. `l_local` is the per-window floor's own quantity, on RNAplfold.
            "access_a": number("access_a"),
            "access_b": number("access_b"),
            "l_local": number("l_local"),
            "l_green": number("l_green"),
            "xseq": xseq,
            "wx": x_span,
            # Informational, and False on a correct design: see the note above.
            "x_in_b": trig_b.find(xseq) >= 0,
            "d_off": number("d_off"),
            "xstar_partners_01": xstar_partners(
                folder, f"{switch}&{trig_b}", xstar, {d["name"]: (d["s"], d["e"]) for d in all_d}
            ),
            "states": {
                "00": state_block(folder, switch, xstar),
                "01": state_block(folder, f"{switch}&{trig_b}", xstar),
                "10": state_block(folder, f"{switch}&{trig_a}", xstar),
                "11": state_block(folder, f"{switch}&{trig_a}&{trig_b}", xstar),
            },
            # sw_x is where the secondary stem holds x*; trigger A's block starts after the
            # switch in the 11 tube, which is why the span is expressed from len(switch).
            "lock4": {
                "00": lock_term(folder, switch, xstar, sw_x),
                "01": lock_term(folder, f"{switch}&{trig_b}", xstar, None),
                "10": lock_term(folder, f"{switch}&{trig_a}", xstar, sw_x),
                # x* AND the main stem's ascending arm, as the weaker of the two.
                "11": engaged_by_a(
                    folder,
                    f"{switch}&{trig_a}&{trig_b}",
                    xstar,
                    oe.domains(switch)["main_pre_star"],
                    (len(switch), len(switch) + len(trig_a)),
                ),
            },
        }
        cands.append(cand)
        print(f"    {index + 1}/{len(panel)}  {cand['pair']:17s}{cand['arm']:18s}ok", flush=True)

    # How far each candidate is from the NEAREST other one, in bases.
    #
    # **Because several rows differ by a base or two and that is a wasted bench slot.** Two designs
    # one substitution apart are one experiment, not two, whatever arm chose each -- and nothing on
    # the page said so: the cards show the sequence but nobody diffs 165 nt by eye. `sequences`
    # already has `hamming`; this calls it rather than counting again.
    #
    # Only equal-length switches are compared, which is every pair within a geometry -- 161 nt
    # naive against 165 nt Kim is not a substitution distance and is reported as None rather than
    # as a large number that would read as "very different".
    from engine.sequences import hamming

    for cand in cands:
        best, who = None, ""
        for other in cands:
            if other is cand or len(other["seq"]) != len(cand["seq"]):
                continue
            distance = hamming(cand["seq"], other["seq"])
            if best is None or distance < best:
                best, who = distance, other["arm"]
        cand["nearest_nt"] = best
        cand["nearest_arm"] = who

    # The identity, added to the population so `describe` can reach it like any column.
    for row in population:
        one, two = row.get("A_M_11"), row.get("f2_gain")
        row["f2_worst"] = None if one is None or two is None else one - two

    stats = {
        key: describe([r.get(STAT_SOURCE.get(key, key)) for r in population])
        # The statistics bars need every key the cards show a tile for, or rngBar silently
        # renders nothing -- which has happened before, to three bars at once.
        for key in (
            "f1",
            "f2",
            "f2_gain",
            "f2_worst",
            "am11",
            "ied11",
            "ied_gain",
            "dgarm11",
            "barrier",
            "access",
            "access_a",
            "access_b",
            "l_local",
            "nearest_nt",
            "r2_star_00",
            "f4",
            "f5",
        )
    }

    # Only `open_11` is parsed to a float by objective_panel.load (as `open_11f`); the other
    # three arrive as STRINGS off the CSV. An earlier version read `open_00f`/`open_01f`/
    # `open_10f`, got None for every row, and `describe` returned {} -- so `rngBar` bailed out
    # and three of the six statistics bars on every card silently rendered nothing.
    def column(key: str) -> list[float | None]:
        out = []
        for row in population:
            value = row.get(f"{key}f", row.get(key))
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                out.append(None)
        return out

    for state in ("00", "01", "10", "11"):
        stats[f"op{state}"] = describe(column(f"open_{state}"))

    # The variants, keyed by trigger pair so the ordering section can show every window beside the
    # sequence it replaces. Absent until codon_variants.py has run against THIS panel -- which
    # refresh_panel.ps1 guarantees by running them in order.
    # ONE VARIANT SET PER PANEL, and the merge is what makes that necessary.
    #
    # The four mCherry transcripts are shared across a panel, so a panel's pairs must have
    # mutually non-overlapping windows -- `pick` enforces that between its two slots. Carrying a
    # second panel puts FOUR pairs on the page, and nothing checked disjointness ACROSS the two.
    # Measured on the merged set: trigger A of pair 423/658 (423-459) overlaps trigger B of pair
    # 270/433 (384-433) by 11 nt, so the A-recoded transcript changed 2 to 10 bases inside a B
    # window it was supposed to leave intact, and the B-recoded one did the same in reverse.
    #
    # The two panels are ALTERNATIVE experiments, not one experiment with four pairs, so each gets
    # its own four transcripts and they are never mixed. A candidate is matched to the variants of
    # the panel it came from.
    # Each variant file is checked against ITS OWN panel CSV, which is the only count it can be
    # wrong against.
    #
    # Two earlier versions of this check were both wrong for the same reason -- they compared one
    # file's rows to a number derived from the MERGED panel. Inside the loop that warned twice
    # ("56 rows, expected 180" when 56 was exactly right); outside it, once the lower3 panel chose
    # the same six as the default, the merge added 0 rows while two files still contributed 24
    # each, so a correct pair of files reported "48 rows, expected 24". A per-file check cannot
    # drift with how the panels happen to overlap.
    variants = []
    for source, panel_name, tag in (
        (f"variants_{panel_name}", panel_name, "default" if i == 0 else panel_name)
        for i, panel_name in enumerate(names)
    ):
        vpath = NB / "results" / f"{source}.csv"
        if not vpath.exists():
            print(f"  {source}.csv absent -- {tag} rows will show no variant table")
            continue
        rows_here = [
            {**row, "panelset": tag} for row in csv.DictReader(vpath.open(encoding="utf-8"))
        ]
        variants.extend(rows_here)
        # Four transcripts per row of that panel. The best-in-sweep extras are not in the panel
        # CSV at all, so this count needs no filtering.
        ppath = NB / "results" / f"{panel_name}.csv"
        want = (
            4 * sum(1 for _ in csv.DictReader(ppath.open(encoding="utf-8")))
            if ppath.exists()
            else None
        )
        verdict = ""
        if want is not None and len(rows_here) != want:
            verdict = (
                f"  WARNING: expected {want} (4 x the panel's rows) -- rerun codon_variants.py"
            )
        print(f"  {len(rows_here)} variant rows from {source}.csv ({tag}){verdict}")
    # The four full transcripts, which the ordering sheet needs whole. `variants` carries only
    # each design's two trigger windows cut out of them, so a sheet built from that cannot show
    # the 711 nt anyone will actually order.
    transcripts = []
    for source, tag in (
        (f"variants_{panel_name}", "default" if i == 0 else panel_name)
        for i, panel_name in enumerate(names)
    ):
        tpath = NB / "results" / f"{source}_transcripts.csv"
        if not tpath.exists():
            print(f"  {source}_transcripts.csv absent -- no full transcripts for {tag}")
            continue
        rows_here = [
            {**row, "panelset": tag} for row in csv.DictReader(tpath.open(encoding="utf-8"))
        ]
        transcripts.extend(rows_here)
        sizes = sorted({len(r["seq"]) for r in rows_here})
        print(f"  {len(rows_here)} transcripts from {source}_transcripts.csv ({tag}), {sizes} nt")

    out = {
        "cands": cands,
        "stats": stats,
        "n_population": len(population),
        # The gating count too, so the funnel on the page reads both from the data instead of
        # carrying them as prose that goes stale whenever a filter moves.
        "n_gating": len(op.gating(population)),
        # The joined population before any filter, for the subtitle. It grew from 58,876 to 60,337
        # when the sweep was extended, and the subtitle went on saying 58,876.
        "n_joined": len(op.load(NB / "results")),
        # panel name -> the one line that panel recorded about how it was built. The page shows it
        # under the view button, because five panels side by side with no description is five
        # unlabelled things.
        "recipes": recipes,
        "panels": names,
        "variants": variants,
        "transcripts": transcripts,
    }
    path = OUT / "panel_data.json"
    json.dump(out, path.open("w"), separators=(",", ":"))
    print(
        f"\n  wrote {path.name}: {len(cands)} candidates, "
        f"{path.stat().st_size // 1024} KB, population {len(population):,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
