"""Pick an orderable panel, and say what each row is there to find out.

    uv run python src/engine/gates/notebooks/toehold_and/candidates.py --from p1,p2,p3

**The panel is an experiment, not a shortlist.** Ordering the ten highest-scoring designs
tests almost nothing: if they work, the model is confirmed on the cases it was already
confident about, and if they fail we learn only that it is wrong somewhere. So the panel is
built the way Offer proposed -- a small number of **trigger-pair backgrounds**, each carrying
several design variants -- which holds constant the thing we cannot predict (which pair of
windows the transcript happens to offer) and varies the thing the model claims to know.

Each row carries a **role**, and the roles are chosen so that every outcome is readable:

``arm-E``      best ``mean_separation``: what the equilibrium arm believes.
``arm-K``      best ``log10_rate_advantage``: what the kinetic arm believes. These two have
               disagreed on nearly every comparison so far, and only a bench result can say
               which to keep. A panel without both cannot settle it.
``old-stat``   best joint ``separation`` *while barely opening*. The statistic the pipeline
               used to rank on, which we measured at r = -0.063 against ``A_M(11)``. If these
               work, that retraction was wrong; if they fail, it is confirmed on real data.
``closure``    the same background at a different AUG closure, so the one axis stage 1 is
               blind to is varied within a fixed context.
``null``       predicted to fail: opens poorly and separates poorly. **Without these a null
               result is uninterpretable** -- if every ordered construct works, the panel
               cannot distinguish a good model from an easy target.

Backgrounds are chosen for **toehold accessibility** as well as score: ``r2_open_3p3`` is how
unpaired the 3 nt of trigger B's toehold nearest the hairpin are, where structure blocks
binding from becoming invasion. A background that scores well but cannot be reached is not a
test of anything.
"""

import argparse
import csv
import glob
import math
import re
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from engine import sequences as sq
from engine.domain import Host
from engine.gates.toehold import ProkaryoticToeholdAndGate, _mean_unpaired
from engine.gates.tools.codons import CodonOptimizer
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.translation import TranslationScorer

RESULTS = Path(__file__).resolve().parent / "results"

#: Backgrounds pinned by `--pin`, so the report can say which were not ranked in.
PINNED: dict[tuple[int, int], str] = {}
SECONDARY_LOOP = "CAAGAACUUAGACAA"


def _longest_rc(loop: str, trigger: str) -> int:
    """Longest stretch of `loop` reverse-complementary to somewhere in `trigger`.

    A substring scan, not a fold: it answers "could these pair at all", which is the cheap
    screen. Folding answers "would they", and is the follow-up for whatever this flags.
    """
    best = 0
    for start in range(len(loop)):
        for end in range(start + best + 1, len(loop) + 1):
            if sq.reverse_complement(loop[start:end]) in trigger:
                best = end - start
    return best


PAIR = "x_start, xstar_start, a_start, a_end, b_start, b_end"
DESIGN = "closure, upper3, lower3, island, scheme, stem_index"


def _view(con, name: str, pattern: str) -> int:
    files = [f.replace("\\", "/") for f in sorted(glob.glob(str(RESULTS / pattern)))]
    if not files:
        return 0
    listed = ", ".join(repr(f) for f in files)
    con.execute(
        f"CREATE VIEW {name} AS SELECT * FROM read_csv_auto([{listed}], union_by_name=true)"
    )
    return len(files)


_SINKS: list = []


def _tee_to(handle) -> None:
    """Send everything `print` writes here to `handle` as well as to the terminal."""
    _SINKS.append(handle)


_builtin_print = print


def print(*args, **kwargs):  # deliberate shadow, so every table lands in the file too
    _builtin_print(*args, **kwargs)
    for sink in _SINKS:
        _builtin_print(*args, **{**kwargs, "file": sink})


def _table(rows, headers) -> None:
    if not rows:
        print("  (none)")
        return
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    print("  " + "  ".join(str(h).ljust(w) for h, w in zip(headers, widths, strict=True)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(str(v).ljust(w) for v, w in zip(r, widths, strict=True)))


def _recover(gate, transcript, picks, bgrow) -> list[tuple]:
    """The metrics stage 2 never recorded, for the panel's own picks only.

    Specified and missing from every folded run: the `x*` three-way decomposition
    (SELECTION_SPEC 4.4 -- locked to `sw_x`, engaged to a trigger, free; the only way to tell
    the lock HOLDING from the lock torn OPEN), `A(r2*|00)`, `dG_bind_A` on its own (`ddG_AND`
    records a difference but not which side moved), and `dG_rbs_linker` (Green's own best
    predictor, rho +0.29 to +0.33 against measured ON/OFF and near zero against our
    `A_M(11)`, so it carries information ours does not).

    Recomputed, not re-folded: every row stores its `switch` and trigger coordinates, so the
    tubes rebuild from the CSV. Over 197,784 designs that is ~13 h sharded; over a panel's
    picks it is seconds, which is why it belongs here.
    """
    a = transcript[bgrow[2] : bgrow[3]]
    b = transcript[bgrow[4] : bgrow[5]]
    out = []
    for p in picks:
        switch = p[15]
        # `sw_xs` ends where `main_pre_star` begins, and everything from there to the 3' end
        # is fixed at 75 nt: main_pre_star 9 + bulge_star 3 + k1_star 6 + rbs_loop 18 +
        # main_z 6 + aug 3 + main_pre 9 + linker 21. So the offset follows from the length
        # and holds for BOTH geometries -- 161 - 75 = 86 for the default arm, 165 - 75 = 90
        # for Kim's. It was hard-coded to 86, which made every recovered metric read "n/a"
        # on a Kim run without any error.
        sws_end = len(switch) - 75
        # len_x comes from the row, not from matching the sequence against itself: that
        # match succeeded at EVERY length from 3 to 11 on a real switch, so it would have
        # silently picked 3.
        lx = int(p[16])
        swx, sws = (35, 35 + lx), (sws_end - lx, sws_end)
        n = len(switch)
        lo, hi = sws
        span = hi - lo
        # All four logic states, named with trigger A as the left digit, in the strand order
        # `four_tube_observables` uses. x* is read in every one of them: the lock HOLDING and
        # the lock torn OPEN are the same unpaired probability, and only asking *what* x* is
        # paired to separates them.
        tubes = {
            "00": (switch, {}),
            "01": (f"{switch}&{b}", {"B": (n, n + len(b))}),
            "10": (f"{switch}&{a}", {"A": (n, n + len(a))}),
            "11": (
                f"{switch}&{a}&{b}",
                {"A": (n, n + len(a)), "B": (n + len(a), n + len(a) + len(b))},
            ),
        }
        share = {}
        for state, (strands, blocks) in tubes.items():
            # The matrix is symmetric (verified on both an intra-strand fold and a dimer's
            # cross-strand block), so ONE term per pair. Summing m[i][j] + m[j][i] counts
            # every pair twice and read x*locked as 1.85, which is not a probability.
            m = gate.folder.pooled_pair_probabilities(strands)
            row = {"locked": sum(m[i][j] for i in range(lo, hi) for j in range(*swx)) / span}
            for name, (blo, bhi) in blocks.items():
                row[name] = sum(m[i][j] for i in range(lo, hi) for j in range(blo, bhi)) / span
            # Free is MEASURED as the unpaired probability, not inferred as the residual:
            # x* can pair with something that is neither its lock nor a trigger, so a
            # residual is a bin of leftovers and clamps to 0.0 the moment rounding pushes
            # the other terms past 1.0. The four terms summing to 1.0 is then a CHECK.
            row["free"] = _mean_unpaired(m, lo, hi)
            # The gate's own span, not absolute coordinates. `_mean_unpaired(m, 111, 141)`
            # stood here and was a SECOND definition of a measurement `toehold.py` already
            # makes -- and a length-dependent one: over 111-141 a 161-nt switch gets
            # rbs_loop[11/18] + main_z + aug + main_pre + 1 nt of linker while a 165-nt switch
            # gets rbs_loop[15/18] + main_z + aug + main_pre[6/9]. Different domains per
            # architecture, in a script that compares architectures.
            #
            # The stored `A_M_*` columns were never affected: `four_tube_observables` uses
            # `(main_z[0], main_pre[1])` -- 18 nt, identical in both lengths -- and a recompute
            # reproduces the shard values to 0.000000. Only this line disagreed with it.
            # main_z starts 36 nt after sws_end and main_pre ends 54 after it, per the
            # assembly order: rbs_loop(18) main_z(6) aug(3) main_pre(9).
            row["A_M"] = _mean_unpaired(m, sws_end + 36, sws_end + 54)
            share[state] = row
        # dG_bind on the ensemble, not the MFE: SELECTION_SPEC 7.13 asks every scored
        # observable to be an ensemble quantity. Pooled over strand orderings, because the
        # two orderings of this very tube measured 12.66 kcal/mol apart -- unpooled, the
        # three-strand term and the two-strand term it is subtracted from are folded under
        # different constraints and the difference is meaningless.
        z_a = gate.folder.pooled_partition(a)
        z_s = gate.folder.pooled_partition(switch)
        z_sa = gate.folder.pooled_partition(f"{switch}&{a}")
        z_sb = gate.folder.pooled_partition(f"{switch}&{b}")
        z_sab = gate.folder.pooled_partition(f"{switch}&{a}&{b}")
        out.append(
            (
                p[0],
                round(_mean_unpaired(gate.folder.pooled_pair_probabilities(switch), 3, 35), 3),
                round(share["00"]["locked"], 3),
                round(share["10"]["locked"], 3),
                round(share["01"]["free"], 3),
                round(share["11"]["A"], 3),
                round(z_sa - z_s - z_a, 2),
                round(z_sab - z_sb - z_a, 2),
                round((z_sab - z_sb - z_a) - (z_sa - z_s - z_a), 2),
                round(z_sb - z_s - gate.folder.pooled_partition(b), 2),
                round(gate.folder.mfe(switch[sws_end + 18 :]).energy, 2),
            )
        )
    return out


def _cols(role: str) -> str:
    """The one column list every role selects, so all picks are the same tuple shape."""
    return (
        f"'{role}', closure, upper3, lower3, scheme, stem_index, "
        "round(mean_separation, 4), round(A_M_11, 3), round(A_M_gain, 3), "
        "round(separation, 2), round(log10_rate_advantage, 2), "
        "round(A_M_11 / nullif(greatest(A_M_00, A_M_01, A_M_10), 0), 2), "
        # Already folded, never surfaced: how free the start codon is in the ON state, and
        # how x* frees up when trigger B binds -- the kinetic proxy's own two inputs.
        "round(aug_11, 3), round(free_xstar_00, 3), round(free_xstar_01, 3), switch, "
        # Appended AFTER `switch` on purpose: p[15] is the switch and is indexed by name
        # nowhere, so inserting earlier would silently shift every reader of it.
        "len_x, round(d_off, 4), round(A_M_10, 3)"
    )


#: Green 2014 / VISTA 2026 / Kim 2019 thresholds that apply to OUR architecture, as written
#: in the team's design guide. Deliberately NOT folded into the ranking: two of the guide's
#: rules (3-WWW top, 2S1W bottom) come from `tsgen2`, where the trigger unwinds 15 bp of a
#: fully synthetic stem. Ours is the RNA-refolding architecture, where `sw_x`/`sw_xs` is
#: Green's own `a*x*` domain and the stem base is SHARED with trigger A -- and Green's table
#: lists the refolding switches' top stem as "based on switch #1", not 3-WWW. Our sweep
#: agrees: forcing 2S1W collapses the ON/OFF ratio to ~1.0 against 4.86 for the trigger's
#: own bases. So those two are reported for the record and never scored.
#: E. coli codons below ~0.5% usage / known stalling sites, from the team's scoring
#: pipeline, transcribed to RNA. `lower3` writes codon 3 of the reporter CDS directly, and
#: the level labelled WSS installs AGG -- a rare arginine -- in 100% of its designs.
RARE_CODONS = frozenset({"AGG", "AGA", "CGA", "CGG", "CUA", "AUA", "CCC", "UCG"})

#: Nothing may truncate the reporter in its first three codons.
STOP_CODONS = frozenset({"UAA", "UAG", "UGA"})

#: Shine-Dalgarno-like cores. One outside `rbs_loop` is a second start site.
SD_LIKE = ("AGGAGG", "GGAGG", "AGGAG")

_RULES = {
    "IED rbs-linker (ON)": "VISTA's statistic over Green's own span; rho -0.356 against "
    "168 measured switches, the best correctly-signed predictor we have. Lower is better",
    "codons 1-3 clean": "VISTA: a rare codon stalls the ribosome right after the start",
    "no in-frame stop": "a stop in the first codons truncates the reporter outright",
    "no poly-U >= 4": "the U-tract half of a Rho-independent terminator",
    "no internal AGGAGG": "a second RBS initiates translation in the wrong frame",
    "no restriction site": "RFC10 and RFC1000 both, so the standard can be chosen later",
    "dG_rbs_linker > -15": "guide checklist; a stiffer refolded stem blocks the ribosome",
    "dG_OFF <= -30": "VISTA: hermetic OFF, no stem breathing",
    "homopolymer <= 5": "guide says 4, but the required GGG cap and the fixed linker's "
    "CAAAAG both make 4 unavoidable, so the engine default of 5 is the honest bar",
    "mid-stem GC 33-50%": "switch #1's 33% was the best gen-1 switch; guide says 40-50%",
    "dG_crosstalk > -5": "guide Sortho: trigger A must not bind the other hairpin",
}


def _liabilities(picks) -> list[tuple]:
    """Things that would make a construct not worth ordering, whatever it scores.

    A hard filter, never a weight: a stop codon in the reporter's first three codons is
    not a worse candidate, it is not a candidate.

    Restriction sites and homopolymer runs are deliberately NOT here. `MotifScreener` owns
    them, it lives in `stages/`, and `gates/notebooks/` may not import upward -- the house
    rules check that, and reimplementing the screener to dodge the rule is exactly the
    merge defect the rules exist to stop. `tools/screen_candidates.py` runs it over this
    panel's CSV export instead, outside the engine tree where the import is legal.

    Also not screened, named in the report as gaps rather than quietly skipped: RNase E
    (no reliable consensus motif -- structure and AU-richness are the honest proxies) and
    G-quadruplexes (0 hits in mCherry and 0 in every panel switch, so nothing today).
    """
    out = []
    for p in picks:
        switch = p[15]
        poly_u = max((len(m) for m in re.findall(r"U+", switch)), default=0)
        # An SD-like core outside the real RBS would start translation somewhere else. The
        # intended one lives in `rbs_loop`, so occurrences are counted and one is expected.
        sd = sum(switch.count(m) for m in SD_LIKE[:1])
        out.append(
            (
                p[0],
                f"{poly_u} {'FAIL' if poly_u >= 4 else 'OK'}",
                f"{sd} {'CHECK' if sd > 1 else 'OK'}",
                "ORDER" if poly_u < 4 and sd <= 1 else "HOLD",
            )
        )
    return out


def _green_rules(gate, transcript, picks, bgrow) -> list[tuple]:
    """The design guide's numeric thresholds, checked per candidate and REPORTED.

    Every value here is already computed elsewhere in this run, so this costs nothing but
    the arithmetic. It is a checklist, not a score: `SELECTION_SPEC` forbids fitting weights
    to data, and two of the guide's eight AND-gate terms are contradicted by our own sweep.
    """
    a = transcript[bgrow[2] : bgrow[3]]
    b = transcript[bgrow[4] : bgrow[5]]
    out = []
    for p in picks:
        switch = p[15]
        sws_end = next(
            (
                86 + d
                for d in (0, 4)
                if switch[35 : 35 + 3] == sq.reverse_complement(switch[83 + d : 86 + d])
            ),
            None,
        )
        arm = switch[sws_end : sws_end + gate.ARM_LEN] if sws_end else ""
        mid = arm[3:-3]
        rbs_linker = gate.folder.mfe(switch[sws_end + 18 :]).energy
        # VISTA's Ideal Ensemble Defect over the same stretch. Its target structure for a
        # region that must be free is "completely unpaired", so the IED collapses to the
        # mean base-pairing probability. Calibrated against Green's 168 measured switches it
        # is the strongest correctly-signed predictor we have -- rho -0.356 against ON/OFF,
        # ahead of Green's own MFE form (+0.334) over the identical span. LOWER is better.
        ied = 1.0 - _mean_unpaired(
            gate.folder.pooled_pair_probabilities(f"{switch}&{a}&{b}"),
            sws_end + 18,
            len(switch),
        )
        dg_off = gate.folder.pooled_partition(switch)
        # In state 10 trigger A reaches nothing but the other hairpin's toehold, so its whole
        # binding energy IS the guide's crosstalk term.
        crosstalk = (
            gate.folder.pooled_partition(f"{switch}&{a}") - dg_off - gate.folder.pooled_partition(a)
        )
        # returns (base, run length) -- the run is what the guide caps at 4
        # The mandatory GGG T7 prefix sits at index 0 and makes a GGGG the moment r2* starts
        # with a G. Failing a design for a leader the guide itself requires is noise, so the
        # run is measured from after the cap. The threshold is the engine default of 5, not
        # the guide's 4 -- the constant LINKER ends in CAAAAG, an unavoidable A-run of 4 that
        # would otherwise fail every design ever built, which is what it did.
        homo_base, homo = sq.longest_homopolymer(switch[3:])
        # AUG sits 42 nt after main_pre_star begins -- main_pre_star 9 + bulge_star 3 +
        # k1_star 6 + rbs_loop 18 + main_z 6 -- so codon 3 of the CDS is +51 from there.
        # Derived from sws_end rather than hard-coded, because the Kim geometry shifts
        # every index by 4 and an index borrowed from the default gate reads the wrong bases.
        # Codons 1-3 of the CDS: `main_pre`, which is trigger-derived and therefore the only
        # part that varies. Codons 4-10 are the constant LINKER -- AAC CUG GCG GCA GCG CAA
        # AAG -- checked once and clean, so they can never differ between designs.
        cds = switch[sws_end + 45 : sws_end + 54]
        codons = [cds[i : i + 3] for i in range(0, len(cds), 3)]
        rare = [c for c in codons if c in RARE_CODONS]
        stops = [c for c in codons if c in STOP_CODONS]
        # A stop is fatal and outranks rarity, so it is what the cell reports.
        verdict = (
            "STOP:" + ",".join(stops) if stops else ("RARE:" + ",".join(rare) if rare else "OK")
        )
        gc = sq.gc_content(mid) if mid else None
        out.append(
            (
                p[0],
                f"{'/'.join(codons)} {verdict}" if codons else "n/a",
                f"{ied:.3f}",
                f"{rbs_linker:.1f} {'OK' if rbs_linker > -15 else 'FAIL'}",
                f"{dg_off:.0f} {'OK' if dg_off <= -30 else 'FAIL'}",
                f"{homo_base}x{homo} {'OK' if homo <= 5 else 'FAIL'}",
                f"{gc:.0f}% {'OK' if 33 <= gc <= 50 else 'high'}" if gc is not None else "n/a",
                f"{crosstalk:.1f} {'OK' if crosstalk > -5 else 'FAIL'}",
            )
        )
    return out


#: The three aggregations from the objective-function discussion, as SELECTION methods over
#: the same measurements. They are not extra metrics: every one reads `ratio`, `kinetic` and
#: `A_M(11)` off the same folded rows and differs only in how it combines them.
#:
#:   A  rank on the ON/OFF ratio alone -- one axis, no aggregation
#:   B  the Pareto front over (ratio, kinetic, A_M(11)) -- refuses to aggregate at all
#:   C  a product in log space: ln(ratio) + ln(10) * kinetic -- energies and log-rates add,
#:      which IS multiplying the probabilities, so an axis at zero kills the score
#:
#: Measured on the panel's own backgrounds, they agree on the best designs (the unanimous
#: picks sit at the 94th percentile or above in all three, several at 100) and diverge on
#: the tail, mostly over Pareto domination: 8 of 12 two-method picks are not on B's front at
#: all while ranking in A's and C's top 15%. That divergence is why the method-unique picks
#: are worth benching -- they are the only rows that can tell us which aggregation to trust.
OBJECTIVE_ROLES = ("consensus", "onoff-only", "pareto-only", "product-only")

#: switch -> the objective ROLE it earns, independent of any metric role that also claimed
#: it. One construct can serve both arms: it is ordered once and answers both questions.
OBJECTIVE_ROLE_OF: dict[str, str] = {}

#: switch -> the objective methods that put it in their top N, filled by `_objective_take`.
#: A design a metric role already claimed is NOT taken again -- ordering one construct twice
#: tests nothing -- but which methods also wanted it is real information, so it is recorded
#: here and exported beside the row rather than lost to whoever claimed it first.
OBJECTIVE_PICKS: dict[str, list[str]] = {}


#: Floors every objective method applies before ranking. Reported, not silent.
#:
#:   A_M(11)      the opening bar, passed in by the caller as `extra`
#:   AUG(11)      a start codon buried in the ON state is a dead switch whatever it scores.
#:                Measured, this is NEARLY REDUNDANT -- among designs already clearing
#:                A_M(11) > 0.3 it removes 1.6%, because the AUG sits inside the A_M window.
#:                Kept as a cheap guard, not as a discriminator.
#:
#: NOT thresholded, and why: `d_off` has no literature bar and a narrow spread here
#: (p10 0.181, median 0.215, p90 0.257), so any cut would be invented. `dG_OFF` has the
#: guide's bar of -30 kcal/mol but every design in this sweep sits at -71 to -77, so it
#: passes trivially and is reported on the panel rather than filtered on.
AUG_FLOOR = 0.2


#: A design whose lock survives trigger A alone scores near 0.8 here; one whose lock A tears
#: open scores near 0.02. Measured on the panel the two groups are separated by a gap from
#: 0.29 to 0.78, so any cut in that range gives the same answer -- 0.3 is the conservative
#: end of it. Deliberately not tuned finer than the data supports.
LOCK_FLOOR = 0.3

#: switch -> its x* mechanism score, so a design considered by several roles folds once.
_LOCK_CACHE: dict[str, float] = {}


def _x_mechanism(gate, switch: str, a: str, b: str, len_x: int) -> float:
    """The four things the lock must do, multiplied.

    ``lock(00)`` and ``lock(10)`` must hold, ``free(01)`` says trigger B unlocked it, and
    ``engA(11)`` says trigger A then took the freed site. All four are probabilities where
    higher is right, so a geometric mean is their AND: one failure pulls the score down
    instead of being averaged away.

    This is the check that catches a design the Pareto front cannot reject. A switch whose
    lock trigger A tears open on its own is non-dominated on (ratio, kinetics, A_M(11)) --
    it opens, and it opens fast -- while its ON/OFF ratio is 1.0 and it does not gate at
    all. Ranking cannot express "must actually gate"; this does.
    """
    if switch in _LOCK_CACHE:
        return _LOCK_CACHE[switch]
    n = len(switch)
    sws_end = n - 75
    xs0, xs1 = sws_end - len_x, sws_end
    swx = (35, 35 + len_x)

    def _share(tube: str, block: tuple[int, int] | None) -> float:
        m = gate.folder.pooled_pair_probabilities(tube)
        if block is None:
            return _mean_unpaired(m, xs0, xs1)
        # The matrix is symmetric, so ONE term per pair; summing both triangles would
        # double-count and push a probability above 1.
        return sum(m[i][j] for i in range(xs0, xs1) for j in range(*block)) / len_x

    terms = [
        _share(switch, swx),  # lock holds, no trigger
        _share(f"{switch}&{a}", swx),  # lock still holds with A
        _share(f"{switch}&{b}", None),  # B alone frees x*
        _share(f"{switch}&{a}&{b}", (n, n + len(a))),  # A then takes it
    ]
    score = math.exp(sum(math.log(max(v, 1e-6)) for v in terms) / 4)
    _LOCK_CACHE[switch] = score
    return score


def _by_crowding(front: list, axes) -> list:
    """The Pareto front ordered so that taking the first N spans it.

    NSGA-II's crowding distance: each member scores the summed, normalised gap between its
    neighbours along every axis, and the extreme member on each axis scores infinity. High
    score means isolated, so the head of this list is the corners first and then whatever
    sits in the emptiest stretch between them.
    """
    if len(front) <= 2:
        return list(front)
    dist = dict.fromkeys(range(len(front)), 0.0)
    for axis in axes:
        order = sorted(range(len(front)), key=lambda i: axis(front[i]))
        lo, hi = axis(front[order[0]]), axis(front[order[-1]])
        span = (hi - lo) or 1.0
        dist[order[0]] = dist[order[-1]] = float("inf")
        for k in range(1, len(order) - 1):
            i = order[k]
            if dist[i] != float("inf"):
                dist[i] += (axis(front[order[k + 1]]) - axis(front[order[k - 1]])) / span
    return [front[i] for i in sorted(dist, key=lambda i: -dist[i])]


#: switch -> its 1-based rank inside each method's own ordering, exported beside the row so
#: a card can say "onoff #2, pareto #1, product #4" rather than only that a method chose it.
OBJECTIVE_RANKS: dict[str, dict[str, int]] = {}


def _objective_take(
    con, where, picks: list, seen: set, extra: str, top: int = 6, lock=None
) -> None:
    """Add the designs the three aggregations agree on, and the ones only one of them wants.

    Ranked on PERCENTILE within a shared eligible pool, not on raw position: B's front can
    be a handful of rows where A and C rank ninety, so "rank 2" means something different in
    each and comparing them directly overstates B's agreement.
    """
    rows = con.execute(f"""
        SELECT {_cols("?")} FROM f WHERE {where} {extra}
        AND A_M_11 IS NOT NULL AND log10_rate_advantage IS NOT NULL
          AND aug_11 > {AUG_FLOOR}
          AND A_M_11 / nullif(greatest(A_M_00, A_M_01, A_M_10), 0) IS NOT NULL""").fetchall()
    if lock is not None:
        # Applied to the shared pool, so all three methods see the same eligible set and
        # none of them can pick a design that does not gate.
        rows = [r for r in rows if lock(r)]
    if len(rows) < 4:
        return
    ratio, kin, am = (lambda r: r[11]), (lambda r: r[10]), (lambda r: r[7])
    front = [
        r
        for r in rows
        if not any(
            o is not r
            and ratio(o) >= ratio(r)
            and kin(o) >= kin(r)
            and am(o) >= am(r)
            and (ratio(o) > ratio(r) or kin(o) > kin(r) or am(o) > am(r))
            for o in rows
        )
    ]
    order = {
        "onoff": sorted(rows, key=lambda r: -ratio(r)),
        # Ranked by CROWDING DISTANCE, not by ratio x kin. Sorting a Pareto front by a
        # product of its own axes reintroduces exactly the aggregation the front exists to
        # refuse, and picks a cluster from one corner. Crowding distance -- NSGA-II's
        # measure -- keeps the extremes and then the most isolated members, so N picks
        # SPAN the front instead of repeating one trade-off.
        "pareto": _by_crowding(front, (ratio, kin, am)),
        # ln(ratio) + ln(10)*log10(rate): both terms are logs, so adding them multiplies the
        # quantities they came from. A ratio at zero sends it to -inf, which is the "one bad
        # axis kills the gate" behaviour a weighted sum of normalised scores cannot express.
        "product": sorted(rows, key=lambda r: -(math.log(max(ratio(r), 1e-9)) + 2.302585 * kin(r))),
    }
    # Deduplicated by SEQUENCE before the top-N cut. Two stem indices can build the identical
    # molecule, and counting it twice inside one method's list makes a single-method pick
    # read as a two-method consensus -- the exact thing this role exists to detect.
    chosen: dict[str, list[str]] = {}
    for key, ordered in order.items():
        names: list[str] = []
        for row in ordered:
            if row[15] not in names:
                names.append(row[15])
            if len(names) == top:
                break
        chosen[key] = names
    methods: dict[str, set[str]] = {}
    for key, names in chosen.items():
        for sw in names:
            methods.setdefault(sw, set()).add(key)
    for key, ordered in order.items():
        seen_sw: list[str] = []
        for row in ordered:
            if row[15] not in seen_sw:
                seen_sw.append(row[15])
        # Rank AND pool size: "#2 of 120" says something "#2" alone does not, and the
        # pools differ by an order of magnitude between methods -- the Pareto front can hold
        # four rows where ranking on the ratio has ninety.
        for pos, sw in enumerate(seen_sw, start=1):
            OBJECTIVE_RANKS.setdefault(sw, {})[key] = (pos, len(seen_sw))
    counts = {sw: len(ms) for sw, ms in methods.items()}
    for sw, ms in methods.items():
        OBJECTIVE_PICKS[sw] = sorted(ms)
    by_switch = {r[15]: r for r in rows}

    def _add(sw: str, role: str) -> None:
        # The objective arm assigns its role whether or not a metric role got there first.
        # Skipping a claimed design left the arm with two picks out of four and no consensus
        # row at all, which is not the experiment -- the construct is ordered once and
        # carries both labels.
        OBJECTIVE_ROLE_OF[sw] = role
        if sw in seen:
            return
        seen.add(sw)
        picks.append((role, *by_switch[sw][1:]))

    for sw in chosen["onoff"]:
        if counts[sw] == 3:
            _add(sw, "consensus")
    for key, role in (
        ("onoff", "onoff-only"),
        ("pareto", "pareto-only"),
        ("product", "product-only"),
    ):
        for sw in chosen[key]:
            if counts[sw] == 1:
                _add(sw, role)
                break


def _take_rbs(
    con, gate, where: str, picks: list, seen: set, extra: str, cap: int = 600, lock=None
) -> None:
    """The design Green's own best predictor likes, which our ranking never consults.

    `dG_rbs_linker` -- the MFE of the RBS-through-linker segment on its own -- correlates
    rho +0.29 to +0.33 with measured ON/OFF in Green 2014 and near zero with our `A_M(11)`,
    so it carries information ours does not. **Less negative** is less structure over the
    RBS and linker, the direction Green's model rewards, so that is the direction taken
    here. A role exists to test a hypothesis the ranking does not use; if this one wins in
    the wet lab, the ranking is missing a term.

    Not an SQL `ORDER BY`, because the value is not in the folded CSV -- it is one 57-nt
    MFE per candidate, computed here. `cap` bounds that work and is REPORTED, never
    silent: a truncation nobody prints reads as "scanned everything".
    """
    rows = con.execute(f"""
        SELECT {_cols("green-rbs")} FROM f WHERE {where} {extra}
        ORDER BY A_M_11 DESC LIMIT {cap}""").fetchall()
    if not rows:
        return
    scored = sorted(((gate.folder.mfe(r[15][104:]).energy, r) for r in rows), key=lambda x: -x[0])
    # Walked in order, so only the rows this role would actually take get folded for the
    # lock check. Without it green-rbs happily picked a switch trigger A opens on its own.
    if lock is not None:
        scored = [(e, r) for e, r in scored if lock(r)]
    if not scored:
        return
    print(
        f"  green-rbs scanned {len(rows)} of this background's designs"
        f"{' (capped)' if len(rows) == cap else ''}; dG_rbs_linker spans "
        f"{scored[-1][0]:.1f} to {scored[0][0]:.1f} kcal/mol"
    )
    for _, row in scored:
        if row[15] not in seen:
            seen.add(row[15])
            picks.append(row)
            return


def _take(
    con,
    where: str,
    picks: list,
    seen: set,
    role: str,
    order: str,
    extra: str,
    tie: float = 0.05,
    lock=None,
) -> None:
    """Add the single best row for one role, unless that exact switch is already in.

    A background often has one design that is simultaneously the best on two criteria. Taking
    it twice would fill a panel slot without adding a test, so the switch sequence is the
    identity here -- two rows differing only in a stem index that produced the same molecule
    are the same construct to order.
    """
    cols = _cols(role)
    # Two candidates for the role: the outright best, and the best from a scheme not already
    # in the panel. Where they agree to within `tie`, take the second -- a panel whose slots
    # all come from one scheme tests one molecule several times, and which anchoring wins is
    # itself an open question. The metric still decides; this only breaks near-ties.
    taken = {p[4] for p in picks}
    rows = con.execute(f"""
        SELECT {cols} FROM f WHERE {where} {extra} ORDER BY {order} LIMIT 40""").fetchall()
    # Folded only for the rows this role would otherwise take, walking down the order until
    # one survives -- typically a handful, never the whole pool.
    if lock is not None:
        rows = [r for r in rows if lock(r)]
    # Pinning the closure keeps role from being confounded with it, but a pinned closure may
    # have no candidate for a role at all -- open_3x3 rarely shuts, so old-stat and null come
    # up empty there. An empty slot loses the test, so the pin is dropped and the role marked
    # with * to say the comparison is no longer closure-controlled.
    if not rows and "AND closure = " in extra:
        head = extra.partition("AND closure = ")[0]
        rows = con.execute(f"""
            SELECT {cols} FROM f WHERE {where} {head} ORDER BY {order} LIMIT 40""").fetchall()
        if lock is not None:
            rows = [r for r in rows if lock(r)]
        rows = [(r[0] + "*", *r[1:]) for r in rows]
    row = rows[0] if rows else None
    if row is not None and taken:
        lead = row[6] if row[6] is not None else 0.0
        for other in rows[1:]:
            if other[4] in taken or other[6] is None:
                continue
            if lead <= 0 or (lead - other[6]) / abs(lead) <= tie:
                row = other
            break
    if row and row[15] not in seen:
        seen.add(row[15])
        picks.append(row)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="sources", default="p1,p2,p3")
    parser.add_argument("--pairs", type=int, default=2, help="trigger-pair backgrounds")
    parser.add_argument(
        "--opens-pct",
        type=float,
        default=0.0,
        help="percentile of A_M(11) counting as open, e.g. 90 for the top 10%%. Overrides "
        "--opens, and adapts to whatever population is loaded instead of fixing a cut that "
        "was chosen for a different one",
    )
    parser.add_argument("--opens", type=float, default=0.3, help="absolute A_M(11) fallback")
    parser.add_argument(
        "--out",
        default="",
        help="write the panel to results/<name>.txt as well as printing it; a run never "
        "overwrites an earlier one, so an --out already present gets a numeric suffix",
    )
    parser.add_argument(
        "--pin",
        default="",
        help="x_start:xstar_start[=why] pairs to keep as backgrounds whatever their rank, "
        "comma separated -- for a pair kept for a reason the ranking does not carry, such as "
        "the literature using that region or the pair being the sweep's extreme on some "
        "axis. The reason is printed in the panel header, so state the real one",
    )
    parser.add_argument("--fasta", default="", help="transcript, enables the loop scan")
    parser.add_argument(
        "--acc-span",
        type=int,
        choices=(3, 6),
        default=6,
        help="how many nucleotides at the toehold's 3' end count as the nucleation site. "
        "6 is Zhang & Winfree's saturation length; 3 is where most of the rate sits",
    )
    args = parser.parse_args(argv)

    transcript, gate = "", None
    if args.fasta:
        from full_sweep import read_fasta

        transcript = read_fasta(args.fasta)
        gate = ProkaryoticToeholdAndGate(
            Host.ECOLI,
            FoldEngine(37.0),
            TranslationScorer(Host.ECOLI),
            CodonOptimizer(Host.ECOLI),
        )

    tee = None
    if args.out:
        # A panel is a record of a decision, so a later run must not erase an earlier one.
        # The first free numeric suffix rather than a timestamp, so the ordering is obvious.
        target = RESULTS / f"{args.out}.txt"
        seq = 2
        while target.exists():
            target = RESULTS / f"{args.out}_{seq}.txt"
            seq += 1
        tee = target.open("w", encoding="utf-8")
        _tee_to(tee)
        print(f"  writing this panel to {target.name}")

    con = duckdb.connect()
    parts = []
    for prefix in args.sources.split(","):
        prefix = prefix.strip()
        if prefix and _view(con, f"src_{prefix}", f"{prefix}_folded*.csv"):
            parts.append(f"SELECT * FROM src_{prefix}")
    if not parts:
        sys.exit(f"no folded output for {args.sources}")
    # Deduplicated: p3 re-folds designs p1 and p2 already did, and they are identical --
    # verified, 5,400 shared rows with zero discrepancy -- but counting them twice would
    # weight those backgrounds double.
    con.execute(f"""CREATE VIEW f AS SELECT * EXCLUDE (rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY {PAIR}, {DESIGN} ORDER BY 1) rn
        FROM ({" UNION ALL BY NAME ".join(parts)})) WHERE rn = 1""")
    has_toehold = _view(con, "toe", "toehold.csv")
    # In-vivo reachability, from trigger_accessibility.py: VISTA's global transcript slices.
    # This is a DIFFERENT question from toehold.csv, which folds the switch's own toehold in
    # isolation -- a switch can have a perfectly open toehold and sit on a trigger window
    # that is buried in the mRNA. One row per window per pair, so role A and role B are
    # pivoted back together here. sed_w25 because VISTA found only the +/-10 and +/-25
    # windows significant ("proximal occlusion ... rather than global folding").
    has_acc = _view(con, "acc_raw", "accessibility.csv")
    if has_acc:
        con.execute("""CREATE VIEW acc AS
            SELECT x_start, xstar_start,
                   max(CASE WHEN role = 'A' THEN sed_w25 END) AS sed_a,
                   max(CASE WHEN role = 'B' THEN sed_w25 END) AS sed_b,
                   max(CASE WHEN role = 'A' THEN paired_site END) AS paired_a,
                   max(CASE WHEN role = 'B' THEN paired_site END) AS paired_b,
                   max(CASE WHEN role = 'A' THEN codon_after8 END) AS cod_a,
                   max(CASE WHEN role = 'B' THEN codon_after8 END) AS cod_b
            FROM acc_raw GROUP BY x_start, xstar_start""")

    n, pairs = con.execute(f"SELECT count(*), count(DISTINCT ({PAIR})) FROM f").fetchone()
    print(f"\n  {n:,} distinct designs over {pairs:,} trigger pairs")

    # --- backgrounds: must open, must separate, and must be reachable -------------------
    # Joined on (x_start, xstar_start) only, which is what the per-background line below
    # uses. On all six pair-key columns the join silently missed every Kim-arm row -- the
    # column printed "n/a" in this table while the line below printed a real number for the
    # same background, from the same file. Two lookups of one quantity disagreeing is the
    # defect; the pair is identified by x_start AND xstar_start together (x_start alone
    # names up to five different pairs), so the shorter key is still exact.
    acc = "LEFT JOIN toe t USING (x_start, xstar_start)" if has_toehold else ""
    # r2* is the SWITCH's toehold and the strand that must be free for trigger B to bind.
    # r2_open_3p3 folds r2 -- trigger B's own domain -- which is a different molecule with a
    # different self-structure; its median 3' openness reads 0.839 against r2*'s 0.69. Older
    # toehold.csv files predate the r2star columns, hence the fallback.
    acc_name = f"r2_open_3p{args.acc_span}"
    if has_toehold:
        cols = {r[0] for r in con.execute("DESCRIBE SELECT * FROM toe").fetchall()}
        if f"r2star_open_3p{args.acc_span}" in cols:
            acc_name = f"r2star_open_3p{args.acc_span}"
        else:
            print("  ** toehold.csv predates the r2star columns; falling back to r2 **")
    acc_col = f"round(any_value(t.{acc_name}), 3)" if has_toehold else "NULL"
    # Qualified with `f.`: the two-column join leaves a_start/a_end/b_start/b_end present
    # in BOTH f and t, and an unqualified name is then ambiguous rather than wrong -- duckdb
    # refuses it outright, which is the good failure.
    pair_q = ", ".join(f"f.{c}" for c in PAIR.split(", "))
    backgrounds = con.execute(f"""
        SELECT {pair_q}, round(max(f.mean_separation), 4) AS best_msep,
               count(*) FILTER (WHERE f.A_M_11 > {args.opens}) AS opening,
               {acc_col} AS toehold_3p,
               {
        "round(any_value(v.sed_a),3), round(any_value(v.sed_b),3), "
        "round(any_value(v.cod_a),3), round(any_value(v.cod_b),3)"
        if has_acc
        else "NULL, NULL, NULL, NULL"
    }
        FROM f {acc}
        {"LEFT JOIN acc v USING (x_start, xstar_start)" if has_acc else ""}
        GROUP BY {pair_q}
        HAVING count(*) FILTER (WHERE f.A_M_11 > {args.opens}) >= 10
        ORDER BY best_msep DESC
        LIMIT 400""").fetchall()
    # A pinned pair is looked up on its own, NOT filtered out of the 400 above: the whole
    # point of pinning is that the pair did not rank, so searching the ranked list for it
    # finds nothing and reports a pair that is present in the data as missing.
    # ``x:x*`` or ``x:x*=why``. The reason is carried through to the panel header because a
    # pinned background is the one row a reader cannot account for from the ranking, so the
    # panel has to say what put it there. Naming no reason is allowed and prints a neutral
    # one -- what is not allowed is the panel asserting a reason that is not the real one.
    want: dict[tuple[int, int], str] = {}
    for token in args.pin.split(","):
        if not token.strip():
            continue
        coords, _, why = token.partition("=")
        want[tuple(int(v) for v in coords.split(":"))] = why.strip()
    if want:
        clause = " OR ".join(f"(f.x_start = {x} AND f.xstar_start = {xs})" for x, xs in want)
        extra = con.execute(f"""
            SELECT {pair_q}, round(max(f.mean_separation), 4) AS best_msep,
                   count(*) FILTER (WHERE f.A_M_11 > {args.opens}) AS opening,
                   {acc_col} AS toehold_3p,
                   {
            "round(any_value(v.sed_a),3), round(any_value(v.sed_b),3), "
            "round(any_value(v.cod_a),3), round(any_value(v.cod_b),3)"
            if has_acc
            else "NULL, NULL"
        }
            FROM f {acc}
            {"LEFT JOIN acc v USING (x_start, xstar_start)" if has_acc else ""}
            WHERE {clause}
            GROUP BY {pair_q}""").fetchall()
        found = {(r[0], r[1]) for r in extra}
        if set(want) - found:
            print(f"  ** pinned pair(s) {sorted(set(want) - found)} are not in the folded data **")
        PINNED.update({k: want[k] for k in found})
        seen_keys = {(r[0], r[1]) for r in extra}
        backgrounds = extra + [r for r in backgrounds if (r[0], r[1]) not in seen_keys]

    # Among strong backgrounds, prefer the reachable ones -- a background that scores well
    # and cannot be bound is not a test of the design, only of the transcript.
    # PAIR is 6 columns, so best_msep/opening/toehold_3p are 6, 7, 8 and sed_a/sed_b 9, 10.
    #
    # The in-vivo SEDs were previously PRINTED and never ranked on, so a background could
    # lead this table while sitting in a region of mCherry no trigger can reach. SED is the
    # mean base-pairing probability over the +/-25 nt window (Green's l = 1 - SED), so LOWER
    # is more accessible, and the binding constraint is the WORSE of the two triggers --
    # both have to be bound for an AND gate to fire, so the max is what gates it.
    # One reachability score, in the same log-probability space objective C uses, so the
    # background ranking and the design ranking speak one language:
    #
    #   S_bg = ln(l_A) + ln(l_B) + ln(codon_after8_A) + ln(codon_after8_B)
    #
    # l = 1 - SED is Green's local single-strandedness (Doc S1 S14.3 Eq. 4); codon_after8 is
    # VISTA's ribosome-occlusion proxy and its strongest single feature at r = 0.30. All
    # four are fractions in (0, 1] where higher is better, so adding logs multiplies them: a
    # background with EITHER trigger unreachable, or either site parked under a ribosome, is
    # killed rather than averaged back up.
    #
    # These are exactly the acc_A and acc_B terms objective C carries and cannot use inside
    # one background, where they are constant. This is where they do their work.
    #
    # It was max(sed_a, sed_b) alone, which ignored occlusion entirely.
    def _bg_score(row):
        terms = []
        for sed, cod in ((row[9], row[11]), (row[10], row[12])):
            if sed is None or cod is None:
                return float("-inf")
            terms += [max(1.0 - sed, 1e-6), max(cod, 1e-6)]
        return sum(math.log(v) for v in terms)

    # Pinned first, then the score. Sorting them in with everything else would drop a
    # pinned pair straight back out of the panel, which is the opposite of pinning it.
    backgrounds.sort(key=lambda r: ((r[0], r[1]) not in PINNED, -_bg_score(r), -r[6]))
    # Backgrounds must not share an x*: two pairs overlapping on the same x* region are the
    # same piece of transcript seen twice, so a design that works on both has demonstrated
    # one success, not two. Independence is the whole point of having more than one.
    chosen, used_xstar = [], set()
    for row in backgrounds:
        if row[1] in used_xstar:
            continue
        used_xstar.add(row[1])
        chosen.append(row)
        if len(chosen) >= args.pairs:
            break

    print(f"\n  BACKGROUNDS ({len(chosen)} of {len(backgrounds)} qualifying)")
    _table(
        [
            (
                f"x@{r[0]}",
                r[1],
                r[6],
                r[7],
                r[8] if r[8] is not None else "n/a",
                r[9] if len(r) > 9 and r[9] is not None else "n/a",
                r[10] if len(r) > 10 and r[10] is not None else "n/a",
                r[11] if len(r) > 11 and r[11] is not None else "n/a",
                r[12] if len(r) > 12 and r[12] is not None else "n/a",
                round(_bg_score(r), 2) if _bg_score(r) != float("-inf") else "n/a",
            )
            for r in chosen
        ],
        [
            "pair",
            "x*_start",
            "best mean_sep",
            "opening",
            f"3' open ({args.acc_span}nt)",
            "SED A",
            "SED B",
            "codon A",
            "codon B",
            "reach score",
        ],
    )

    for bg in chosen:
        where = " AND ".join(f"{c} = {v}" for c, v in zip(PAIR.split(", "), bg[:6], strict=True))
        print()
        print("=" * 78)
        tag = (
            f"  [PINNED -- {PINNED[bg[0], bg[1]] or 'kept by hand'}, not by the ranking]"
            if (bg[0], bg[1]) in PINNED
            else ""
        )
        print(f"  BACKGROUND x@{bg[0]}  (x* at {bg[1]}){tag}")
        print("=" * 78)
        # Accessibility is a property of the background, not the row -- every role here
        # shares the trigger pair -- so it is stated once rather than as a constant column.
        acc = (
            con.execute(
                f"SELECT round(r2star_open_3p3,3), round(r2star_open_3p6,3), "
                f"round(p5_binds_p3,2), trim_indicated FROM toe "
                f"WHERE x_start = {bg[0]} AND xstar_start = {bg[1]} LIMIT 1"
            ).fetchone()
            if has_toehold
            else None
        )
        if acc:
            print(
                f"  accessibility: 3' open 3nt {acc[0]}, 6nt {acc[1]};  "
                f"5'-binds-3' {acc[2]};  trim indicated {acc[3]}"
            )
        picks: list[tuple] = []
        seen: set[tuple] = set()

        # `shut` is gone: both roles that used it -- old-stat and leaky-10 -- were selecting
        # designs too dead to be informative, and now require `opens` like every other role.
        opens = args.opens
        # A design whose lock trigger A tears open on its own does not gate, whatever it
        # scores. Every role rejects one EXCEPT leaky-10, whose whole job is to find that
        # failure and put it on the bench. Evaluated lazily and cached by switch, so only
        # the rows a role actually considers are folded.
        trig_a, trig_b = transcript[bg[2] : bg[3]], transcript[bg[4] : bg[5]]

        def _lock_ok(row, _a=trig_a, _b=trig_b):
            if gate is None:
                return True
            return _x_mechanism(gate, row[15], _a, _b, int(row[16])) >= LOCK_FLOOR

        # Role must not be confounded with closure. old-stat and null both favour the closed
        # variants (best separation 16.86 at closed_CGU against 15.57 at open_3x3), so roles
        # picked freely would differ by closure as much as by criterion and the panel could
        # not tell the two apart. Every role below is therefore pinned to ONE closure -- the
        # one that wins arm E on this background -- and the `closure` role is the only row
        # that varies it, deliberately and on its own.
        ref = con.execute(f"""
            SELECT closure FROM f WHERE {where} AND A_M_11 > {opens}
            ORDER BY mean_separation DESC LIMIT 1""").fetchone()
        pin = f"AND closure = '{ref[0]}'" if ref else ""
        ratio = "A_M_11 / nullif(greatest(A_M_00, A_M_01, A_M_10), 0)"
        _take(
            con,
            where,
            picks,
            seen,
            "arm-E",
            "mean_separation DESC",
            f"AND A_M_11 > {opens} {pin}",
            lock=_lock_ok,
        )
        # The difference and the ratio are different statistics: they correlate 0.365 and
        # share only 10 of their top 20. meanW is a probability, not an energy, so a
        # difference is not a log-ratio the way the dG_open separation is -- and fold change
        # is what a bench measures. Both arms are carried; neither is assumed.
        _take(
            con,
            where,
            picks,
            seen,
            "arm-E-ratio",
            f"{ratio} DESC",
            f"AND A_M_11 > {opens} {pin}",
            lock=_lock_ok,
        )
        _take(
            con,
            where,
            picks,
            seen,
            "arm-K",
            "log10_rate_advantage DESC",
            f"AND A_M_11 > {opens} {pin}",
            lock=_lock_ok,
        )
        # `A_M_11 > opens`, not `< shut`. The point of this role is to test whether the
        # retracted `separation` statistic picks winners; ranked among SHUT designs it
        # returned A_M(11) = 0.046 and AUG(11) = 0.003 -- a dead switch, whose failure at the
        # bench would say nothing about the statistic. Among designs that open, it is a real
        # head-to-head against `mean_separation`.
        _take(con, where, picks, seen, "old-stat", "separation DESC", f"AND A_M_11 > {opens} {pin}")
        # A null must be null on EVERY reported metric. Chosen on mean_separation alone it
        # could still hold the highest separation and the highest kinetic advantage in the
        # whole table -- 15.37 and 5.96 were both available to that slot -- which is not a
        # negative control, it is a third positive dressed as one.
        _take(
            # A design that LEAKS: state 10 opens at least as much as state 11, so trigger A
            # alone is enough. More informative than one that is merely shut -- a shut switch
            # failing says nothing, while a leaky one failing confirms A_M(10) is the quantity
            # to suppress, and a leaky one WORKING would say the model reads state 10 wrongly.
            # This is the state-10 leak chased since block A, made orderable.
            con,
            where,
            picks,
            seen,
            "leaky-10",
            "A_M_10 DESC",
            # `A_M_10 >= A_M_11` was the wrong constraint: it forces the ON state to be no
            # better than the leak, which selects a broken switch (A_M(11) = 0.119, ratio
            # 1.0) rather than a working one that leaks. What we want to bench is a design
            # that DOES turn on and also leaks in state 10, because that is the informative
            # failure: if it works, A_M(10) is not what limits us.
            f"AND A_M_11 > {opens} {pin}",
        )
        if ref:
            _take(
                con,
                where,
                picks,
                seen,
                "closure",
                # Ranked on the ON/OFF ratio, not mean_separation. open_3x3 leaves bulge*
                # trigger-derived and opens 99.3% of designs while separating nothing
                # (median mean_sep 0.0); the closed bulges are mostly dead but their upper
                # tail discriminates twice as well (p90 ratio 8.26 against 4.51). A panel
                # selects the tail, so the tail is what this role must rank on.
                "A_M_11 / nullif(greatest(A_M_00, A_M_01, A_M_10), 0) DESC NULLS LAST",
                f"AND A_M_11 > {opens} AND closure <> '{ref[0]}'",
                lock=_lock_ok,
            )
        # Last, so it fills a slot only with a design no other role already claimed: this
        # one is here to probe an axis, not to win the panel.
        if gate is not None:
            _take_rbs(con, gate, where, picks, seen, f"AND A_M_11 > {opens} {pin}", lock=_lock_ok)
        # The objective-function arm. It answers a different question from the roles above:
        # those ask WHICH MEASUREMENT matters, these ask HOW TO COMBINE them.
        _objective_take(con, where, picks, seen, f"AND A_M_11 > {opens}", lock=_lock_ok)
        # green-rbs ranks on this, so it belongs beside the numbers the other roles rank on
        # rather than only in the guide-threshold block below.
        rbsl = (
            {p[15]: round(gate.folder.mfe(p[15][len(p[15]) - 57 :]).energy, 1) for p in picks}
            if gate is not None
            else {}
        )
        _table(
            [
                (
                    *p[:6],
                    # 161 nt is the default geometry, 165 the Kim 20/17/AUA arm. Printing
                    # the length is the only way to tell them apart from the panel alone.
                    len(p[15]),
                    p[6],
                    p[7],
                    p[18],
                    p[11],
                    p[8],
                    p[9],
                    p[10],
                    p[17],
                    p[12],
                    p[13],
                    p[14],
                    rbsl.get(p[15], "n/a"),
                )
                for p in picks
            ],
            [
                "role",
                "closure",
                "upper3",
                "lower3",
                "scheme",
                "stem",
                "nt",
                "mean_sep",
                "A_M(11)",
                "A_M(10)",
                "A_M ratio",
                "A_M_gain",
                "sep",
                "log10 kin",
                "d_off",
                "AUG(11)",
                "freeX(00)",
                "freeX(01)",
                "dG_rbs_link",
            ],
        )
        if gate is not None:
            print()
            print("  recovered metrics -- specified but absent from every folded run")
            print("  (x* decomposition tells the lock HOLDING from the lock torn OPEN)")
            _table(
                _recover(gate, transcript, picks, bg),
                [
                    "role",
                    "A(r2*|00)",
                    "x*lock 00",
                    "x*lock 10",
                    "x*free 01",
                    "x*engA 11",
                    "dG_bind_A",
                    "dG_bind(A|B)",
                    "coop",
                    "dG_bind_B",
                    "dG_rbs_linker",
                ],
            )
            print()
            print("  DESIGN-GUIDE THRESHOLDS (Green 2014 / VISTA 2026 / Kim 2019)")
            print("  reported, never scored -- see _RULES for why two of the guide's rules")
            print("  belong to tsgen2's architecture and not to this refolding one")
            _table(
                _green_rules(gate, transcript, picks, bg),
                [
                    "role",
                    "codon3",
                    "IED rbs-link (ON)",
                    "dG_rbs_linker",
                    "dG_OFF",
                    "homopolymer (max 5, after cap)",
                    "mid-stem GC",
                    "dG_crosstalk",
                ],
            )
            print()
            print("  ORDERABLE? -- hard filters, not weights.")
            print("  Restriction sites and homopolymers: run tools/screen_candidates.py on")
            print("  the CSV export; MotifScreener lives in stages/ and cannot be imported here.")
            _table(
                _liabilities(picks),
                ["role", "poly-U", "AGGAGG copies", "verdict"],
            )
            # Every design for this background, not just the picks -- the panel takes one
            # row per role, which hides the runners-up. Opens in Excel; `panel_role` marks
            # what the panel chose so the picks can be found among the alternatives.
            chosen_sw = {p[15]: p[0] for p in picks}
            allrows = con.execute(f"SELECT * FROM f WHERE {where}").fetchall()
            cols = [d[0] for d in con.description]
            csv_path = RESULTS / f"{args.out}_x{bg[0]}_xs{bg[1]}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                w = csv.writer(handle)
                w.writerow(
                    [*cols, "panel_role", "objective_methods", "objective_role", "objective_ranks"]
                )
                sw_at = cols.index("switch")
                for row in allrows:
                    w.writerow(
                        [
                            *row,
                            chosen_sw.get(row[sw_at], ""),
                            "|".join(OBJECTIVE_PICKS.get(row[sw_at], [])),
                            OBJECTIVE_ROLE_OF.get(row[sw_at], ""),
                            ";".join(
                                f"{k}:{v[0]}/{v[1]}"
                                for k, v in sorted(OBJECTIVE_RANKS.get(row[sw_at], {}).items())
                            ),
                        ]
                    )
            print()
            print(f"  every option for this background, for Excel: {csv_path.name}")
            print(
                f"  ({len(allrows):,} designs, {len(cols) + 1} columns, panel_role marks the picks)"
            )
        print()
        print("  sequences (cap through linker):")
        for p in picks:
            print(f"    {p[0]:<11} {p[15]}")
        # The switches above are useless to order without the two RNAs that drive them, and
        # they were missing from every panel so far. One trigger pair per background, shared
        # by every row above, so they print once here rather than on each line.
        ta, tb = transcript[bg[2] : bg[3]], transcript[bg[4] : bg[5]]
        # Coordinates are 0-indexed, inclusive start, exclusive end, into the mCherry
        # transcript -- asserted rather than trusted, because every external-tool wrapper in
        # this repo has been an off-by-one at least once.
        assert transcript[bg[2] : bg[2] + len(ta)] == ta
        assert transcript[bg[4] : bg[4] + len(tb)] == tb
        print()
        print(f"  triggers -- the same pair for every row above (x@{bg[0]}, x* at {bg[1]}):")
        print(f"    trigger A   transcript[{bg[2]}:{bg[3]}]  {len(ta):>2} nt   {ta}")
        print(f"    trigger B   transcript[{bg[4]}:{bg[5]}]  {len(tb):>2} nt   {tb}")
        print("    (RNA, 5'->3'. x_start alone names FIVE different pairs in this run, so")
        print("     the x* coordinate above is part of the identity, not decoration.)")

    print()
    print("=" * 78)
    print("  SECONDARY LOOP vs THE TRIGGERS -- can either bind the loop we never vary?")
    print("=" * 78)
    print("  SECONDARY_LOOP is a fixed 15-mer and nothing has checked whether a trigger can")
    print("  pair with it. A trigger that binds the loop competes with its own intended")
    print("  site, which would read as a weak design rather than as an off-target.")
    print("  Longest reverse-complementary run; 6 nt is worth a look, 8+ should not be")
    print("  ordered without folding the pair properly.")
    print()
    if transcript:
        rows = []
        for bg in chosen:
            a, b = transcript[bg[2] : bg[3]], transcript[bg[4] : bg[5]]
            la, lb = _longest_rc(SECONDARY_LOOP, a), _longest_rc(SECONDARY_LOOP, b)
            rows.append((f"x@{bg[0]}", la, lb, "CHECK" if max(la, lb) >= 6 else "ok"))
        _table(rows, ["background", "loop vs trigger A", "loop vs trigger B", "verdict"])
    else:
        print("  pass --fasta to run this scan")

    print(f"\n{'=' * 78}\n  HOW TO READ A RESULT\n{'=' * 78}")
    for line in (
        "arm-E works and arm-K does not  -> rank on mean_separation, drop the kinetic proxy.",
        "arm-K works and arm-E does not  -> the equilibrium picture is not what limits us.",
        "old-stat works                  -> the separation retraction was wrong; revisit it.",
        "null also works                 -> the target is easy and the panel discriminates",
        "                                   nothing. Widen the design space before trusting",
        "                                   any ranking.",
        "nothing works                   -> the model is wrong at a level no reranking fixes.",
    ):
        print(f"  {line}")
    print()
    if tee is not None:
        tee.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
