"""Shared AND-construct builder and single-switch loader/measurement.

Moved out of ``toehold_and_eu_test.ipynb``'s own cells so that notebook and
``and_eu_report.ipynb`` share one implementation of each, instead of two copies that can
drift apart (``CLAUDE.md`` §1 — "two implementations of one measurement produce two
numbers and only one reaches the report").

Three names that used to be notebook globals these functions closed over
(``COLUMNS``/``CARRY_METRICS`` for :func:`load_ranked_designs`, ``cut_before``/
``keep_after`` for :func:`fuse`) are **required parameters here**, not module-level
defaults — a second copy of a notebook's column map living in this module would be the
same drift problem one level down. Callers pass their own notebook's values explicitly.

``fx.sq.X`` calls (the notebook bootstrap's alias for ``engine.sequences``) are now plain
``engine.sequences`` imports — this module has no notebook bootstrap to inherit one from.
"""

import csv
import json
from pathlib import Path

from _joint_state_parallel import _partner_table

from engine.gates.toehold import _mean_unpaired  # same accessibility helper measure() uses
from engine.sequences import hamming, is_valid_rna, reverse_complement, to_rna, windows


def _maybe_float(value):
    """``float(value)``, or ``None`` when the cell is blank or not a number.

    Deliberately not ``float(value or 0)``: a blank cell is a measurement that is not
    there, and 0.0 is a real value that would go on to sort as though it had been
    measured (``CLAUDE.md`` §3).
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def motif_self_bind_score(sequence, motif_seq):
    """Best fractional match, sliding a window the length of ``motif_seq`` across
    ``sequence``, against the reverse complement of ``motif_seq`` -- built entirely from
    existing engine functions (``windows`` for the scan, ``reverse_complement`` for
    the target, ``hamming`` to score each window; matches = window length minus
    mismatches), not a hand-rolled loop over either.

    Generic over which fixed motif is being checked -- used below for both Kozak
    (``own_kozak_rc_score``, ``kozak_rc_5p``) and the prefix (``own_prefix_rc_score``,
    ``prefix_rc_3p``): the risk is the same shape either way, a fixed element that could
    fold back onto a toehold regardless of how far away it sits.

    Same sliding-window partial-match idea as the team's own ``complementarity_Kozak`` in
    ``CERNAL_FUNCTIONS.py`` — and the one ``engine.gates.toehold._kozak_rc_in_toehold``
    should arguably also use: an exact full-length substring check misses a real,
    ViennaRNA-confirmed partial match (a 5/9 toehold x Kozak+AUG pair found directly in a
    real MFE fold earlier this session, at a window score of 0.556 — see that function's
    own docstring for the caveat this generalises past). Score in [0, 1]; 1.0 is a perfect
    match over the whole window.
    """
    target = reverse_complement(motif_seq)
    window_len = len(target)
    if len(sequence) < window_len:
        return 0.0
    return max(
        1.0 - hamming(window, target) / window_len
        for _start, window in windows(sequence, window_len)
    )


def stem_closed_fraction(structure, stem_up_span, stem_down_span):
    """Fraction of ``stem_up_span`` paired SPECIFICALLY to ``stem_down_span`` in one
    sampled structure -- the intended OFF hairpin actually closing, not just "paired to
    something". One of three state-decomposition metrics (``and_eu_report_spec.md``
    Step 2); the other two are :func:`misfolded_fraction` below and
    ``_frac_paired_to_external`` (``_joint_state_parallel.py`` -- already written,
    already the fix for "open" meaning "paired to anything" rather than "paired to an
    external strand"; reused here as-is for ``trigger_bound``, not reimplemented).

    Built on the same :func:`_partner_table` stack-walk every other partner-tracing
    check in this project uses, so a stem that closes with a bulge or an off-register
    shift is read the same way everywhere, not approximated differently here.
    """
    partner = _partner_table(structure)
    su0, su1 = stem_up_span
    sd0, sd1 = stem_down_span
    n = su1 - su0
    if n == 0:
        return 0.0
    closed = sum(
        1 for i in range(su0, su1) if partner[i] is not None and sd0 <= partner[i] < sd1
    )
    return closed / n


def misfolded_fraction(structure, footprint_span, stem_down_span, n_self):
    """Fraction of ``footprint_span`` paired INTRAMOLECULARLY but NOT to its own
    ``stem_down_span`` -- paired to something other than what either the OFF hairpin
    (``stem_closed_fraction``) or a real binding event (``_frac_paired_to_external``,
    ``trigger_bound``) would call correct. This is the metric that would have caught the
    80-90% false "open" the AND construct read with zero triggers present: that was
    footprint paired to the OTHER hairpin's toehold, not to an external strand and not to
    its own stem_down -- exactly this category, previously invisible because nothing
    distinguished it from "open".

    Low everywhere is the goal; unlike ``trigger_bound``, there is no state in which a
    high value here is correct.

    ``n_self``: length of the fused/switch molecule alone -- a partner index at or past
    this is external (``_frac_paired_to_external``'s territory, not misfolding) and is
    excluded here so the three metrics partition the footprint's possible partners
    without double-counting any of them.
    """
    partner = _partner_table(structure)
    f0, f1 = footprint_span
    sd0, sd1 = stem_down_span
    n = f1 - f0
    if n == 0:
        return 0.0
    misfolded = 0
    for i in range(f0, f1):
        p = partner[i]
        if p is None or p >= n_self:  # unpaired, or paired externally -- not misfolding
            continue
        if sd0 <= p < sd1:  # paired to its own stem_down -- the intended OFF hairpin
            continue
        misfolded += 1
    return misfolded / n


def _toehold_self_fold(toehold_seq, folder):
    """Fraction of ``toehold_seq`` paired to itself when folded alone.

    A general self-structure tendency, independent of what it might specifically bind to
    (Kozak or otherwise) — read alongside ``kozak_self_bind_score``, not instead of it: a
    toehold can fold into a hairpin that has nothing to do with Kozak and still be
    unusable, and this is the only one of the two checks that would catch that.
    """
    matrix = folder.base_pair_probabilities(toehold_seq)
    return 1.0 - _mean_unpaired(matrix, 0, len(toehold_seq))


def load_ranked_designs(path, folder, columns, carry_metrics, limit=None):
    """Rows of a NucSyn ``results_ranked.csv``, kept in file order (already ranked).

    Returns ``(rows, problems)``. A row missing a column, carrying a non-RNA sequence, or
    whose domain breakdown does not tile its own switch exactly is collected in
    ``problems`` with its line number and reason — never dropped silently or patched to a
    default.

    Sequences are normalised with ``engine.sequences.to_rna`` here at the edge: a CSV is
    exactly where a DNA alphabet sneaks in, and ViennaRNA reads a T as an unknown base
    rather than failing (``CLAUDE.md`` §6).

    Three metrics are *computed* here rather than read from the CSV, per design as it
    stands before any fusion decision: ``own_kozak_rc_score`` and ``own_prefix_rc_score``
    (this design's own toehold against its own, still-present Kozak and prefix
    respectively) and ``toehold_self_fold`` (the toehold's general self-pairing tendency,
    folded alone). All three land in ``metrics`` alongside the CSV-carried ones.
    ``own_kozak_rc_score`` matters less for whichever half ends up 5' in a fused pair --
    its own Kozak gets cut away at fusion (see ``fuse()``) -- and symmetrically
    ``own_prefix_rc_score`` matters less for whichever half ends up 3' -- its own prefix
    is what gets cut. Both are computed for every row regardless, since which role a
    design plays is decided later, per pair, not at load time.

    ``columns``: the caller's own column-name map (this notebook's ``COLUMNS``). Required,
    not defaulted here -- see this module's own docstring.
    ``carry_metrics``: the caller's own ``CARRY_METRICS`` tuple -- which CSV columns get
    carried through into ``metrics`` unchanged, via ``_maybe_float``.
    """
    rows, problems = [], []
    with Path(path).open(newline="") as handle:
        for line_no, raw in enumerate(csv.DictReader(handle), start=2):  # 2 = first data line
            missing = [column for column in columns.values() if not (raw.get(column) or "").strip()]
            if missing:
                problems.append((line_no, f"missing or empty: {', '.join(missing)}"))
                continue

            switch = to_rna(raw[columns["switch"]])
            trigger = to_rna(raw[columns["trigger"]])
            not_rna = [
                name
                for name, value in (("switch", switch), ("trigger", trigger))
                if not is_valid_rna(value)
            ]
            if not_rna:
                problems.append((line_no, f"not RNA after to_rna(): {', '.join(not_rna)}"))
                continue

            # 0-indexed, start-inclusive/end-exclusive, same convention as the engine.
            domains = {
                domain["name"]: (domain["start"], domain["end"])
                for domain in json.loads(raw[columns["domains"]])
            }
            # The breakdown is the only thing locating the cut points, so a breakdown that
            # does not tile the switch exactly would put those cuts somewhere arbitrary.
            covered = sorted(domains.values())
            if not covered or covered[0][0] != 0 or covered[-1][1] != len(switch):
                problems.append((line_no, "domain breakdown does not span the switch"))
                continue

            toehold_seq = switch[domains["toehold"][0] : domains["toehold"][1]]
            own_kozak_span = domains.get("kozak")
            own_kozak_seq = (
                switch[own_kozak_span[0] : own_kozak_span[1]] if own_kozak_span else None
            )
            own_prefix_span = domains.get("prefix")
            own_prefix_seq = (
                switch[own_prefix_span[0] : own_prefix_span[1]] if own_prefix_span else None
            )
            metrics = {name: _maybe_float(raw.get(name)) for name in carry_metrics}
            metrics["own_kozak_rc_score"] = (
                motif_self_bind_score(toehold_seq, own_kozak_seq) if own_kozak_seq else None
            )
            metrics["own_prefix_rc_score"] = (
                motif_self_bind_score(toehold_seq, own_prefix_seq) if own_prefix_seq else None
            )
            metrics["toehold_self_fold"] = _toehold_self_fold(toehold_seq, folder)

            # Optional: only this notebook's COLUMNS declares trigger_start/trigger_end
            # (the single-input notebook's loader has neither, and doesn't need them --
            # this is purely for the trigger-position map at the end of this report).
            trigger_start = (
                int(raw[columns["trigger_start"]]) if "trigger_start" in columns else None
            )
            trigger_end = int(raw[columns["trigger_end"]]) if "trigger_end" in columns else None

            rows.append(
                {
                    "switch": switch,
                    "trigger": trigger,
                    "domains": domains,
                    "rank": raw[columns["rank"]],
                    "metrics": metrics,
                    "line_no": line_no,
                    "trigger_start": trigger_start,
                    "trigger_end": trigger_end,
                }
            )
            if limit is not None and len(rows) >= limit:
                break
    return rows, problems


def fuse(design_5p, design_3p, cut_before, keep_after, spacer):
    """One AND candidate: every domain from both halves, relocated into the fused frame.

    Returns ``(built, problem)``. ``built["domains_5p"]``/``["domains_3p"]`` carry every
    surviving domain's fused-frame span, not just the toehold — the layout bar and the
    register diagrams both need to know where every domain landed, and re-deriving those
    offsets in two more places would be two more chances to get the arithmetic wrong.
    ``problem`` is non-None when either design lacks the domain its cut is defined by,
    lacks ``stem_up`` (the ascending arm a trigger's footprint needs), or when a relocated
    span does not hold the sequence it started as — slicing a guessed offset instead would
    still return a sequence, and it would fold into a plausible-looking wrong answer
    nothing downstream could catch.

    Note for other topologies: cutting the 5' half at ``kozak`` leaves its ``pre_kozak``
    arm in place while dropping the ``post_kozak`` it was designed to pair with. Both are
    zero-length in ``euk_open_5p_kozak_after_stem``, so nothing is orphaned here; a
    topology that uses them needs this cut reconsidered, not just re-pointed.

    ``spacer`` sits between the two bodies unshifted-domain-wise for the 5' half and
    folded into the 3' half's shift -- a physical separator between the two hairpins,
    not part of either design's own domain set.

    ``cut_before``/``keep_after``/``spacer``: the caller's own ``CUT_5P_BEFORE``/
    ``KEEP_3P_AFTER``/``SPACER_SEQ``-equivalent values. Required, not defaulted here --
    see this module's own docstring.
    """
    for label, design, domain in (("5'", design_5p, cut_before), ("3'", design_3p, keep_after)):
        if domain not in design["domains"]:
            return None, f"{label} line {design['line_no']}: no {domain!r} domain"

    cut_5p = design_5p["domains"][cut_before][0]
    keep_3p = design_3p["domains"][keep_after][1]
    body_5p = design_5p["switch"][:cut_5p]
    body_3p = design_3p["switch"][keep_3p:]
    fused = body_5p + spacer + body_3p
    shift = len(body_5p) + len(spacer) - keep_3p

    # Every 5' domain that ends at or before the cut survives unshifted; every 3' domain
    # that starts at or after the keep point survives, shifted by how far it moved.
    domains_5p = {name: span for name, span in design_5p["domains"].items() if span[1] <= cut_5p}
    domains_3p = {
        name: (start + shift, end + shift)
        for name, (start, end) in design_3p["domains"].items()
        if start >= keep_3p
    }

    # CLAUDE.md §6: every coordinate translation is an off-by-one until it is checked.
    for label, domains, design, base_shift in (
        ("5'", domains_5p, design_5p, 0),
        ("3'", domains_3p, design_3p, shift),
    ):
        for name, (start, end) in domains.items():
            original_start, original_end = start - base_shift, end - base_shift
            if fused[start:end] != design["switch"][original_start:original_end]:
                return None, f"{label} line {design['line_no']}: {name} does not survive relocation"

    for label, domains, design in (("5'", domains_5p, design_5p), ("3'", domains_3p, design_3p)):
        missing = [name for name in ("toehold", "stem_up") if name not in domains]
        if missing:
            return (
                None,
                f"{label} line {design['line_no']}: missing {', '.join(missing)} after the cut",
            )

    return (
        {
            "fused": fused,
            "domains_5p": domains_5p,
            "domains_3p": domains_3p,
            "toehold_5p": domains_5p["toehold"],
            "toehold_3p": domains_3p["toehold"],
            # The footprint is toehold + the ascending arm -- exactly the region the
            # trigger reverse-complements against, same definition the single-input
            # report uses for its own "footprint" highlight.
            "footprint_5p": (domains_5p["toehold"][0], domains_5p["stem_up"][1]),
            "footprint_3p": (domains_3p["toehold"][0], domains_3p["stem_up"][1]),
            "spacer_span": (len(body_5p), len(body_5p) + len(spacer)),
        },
        None,
    )


def measure(built, trigger_5p, trigger_3p, folder, own_kozak_rc_3p, own_prefix_rc_5p):
    """Energies for the four states, both toehold accessibilities, and the Kozak/prefix
    self-binding risk of whichever toehold each fixed element could actually reach.

    ``FoldEngine`` caches per sequence, so the shared instance built in the run cell below
    is the only one that should ever fold here — a second instance means a cold cache and,
    worse, a second chance to fold at a different temperature.

    ``own_kozak_rc_3p``/``own_prefix_rc_5p`` are the 3'/5' design's own
    ``metrics["own_kozak_rc_score"]``/``["own_prefix_rc_score"]`` (``load_ranked_designs``),
    passed in rather than recomputed: fusion never changes the 3' half's own toehold+Kozak,
    or the 5' half's own toehold+prefix -- only their position in the fused frame -- and
    ``motif_self_bind_score`` depends only on sequence content, so recomputing either here
    was verified to return the exact same number the load-time pass already computed. Only
    the *other* toehold's score against each surviving element is genuinely
    fusion-dependent (5' toehold vs the surviving Kozak; 3' toehold vs the surviving
    prefix), since each depends on which design it ended up paired with — those two are
    still computed here, per pair.
    """
    fused = built["fused"]
    states = {
        "off": fused,  # no trigger: both hairpins closed
        "t5": f"{fused}&{trigger_5p}",  # '&' = a true multi-strand complex, not a fusion
        "t3": f"{fused}&{trigger_3p}",
        "both": f"{fused}&{trigger_5p}&{trigger_3p}",
    }

    out = {}
    for name, strands in states.items():
        out[f"mfe_{name}"] = folder.mfe(strands).energy
        out[f"ee_{name}"] = folder.partition(strands)

    # dG of a state = that state minus the trigger-free OFF state, so a negative number is
    # the stabilisation that adding trigger(s) bought.
    for name in ("t5", "t3", "both"):
        out[f"d_mfe_{name}"] = out[f"mfe_{name}"] - out["mfe_off"]
        out[f"d_ee_{name}"] = out[f"ee_{name}"] - out["ee_off"]

    # Reported, never ranked on: how much the second trigger buys beyond whichever single
    # trigger already did most of the work. Near zero means one trigger alone already
    # opens the construct -- an OR wearing an AND's shape, which is the specific failure
    # this architecture has to be checked for (see this notebook's mechanism section).
    out["and_margin_ee"] = min(out["d_ee_t5"], out["d_ee_t3"]) - out["d_ee_both"]

    # The ranking key. d_ee_both alone only asks "is ON more stable than OFF" -- it says
    # nothing about whether the ensemble would rather sit in some *other* not-fully-on
    # state instead, e.g. "+trigger B alone" being more stable than plain OFF. The real
    # competitor to the ON state is whichever of the three not-fully-activated states
    # (OFF, +A alone, +B alone) is thermodynamically most favourable -- the most negative
    # of the three, since a system settles toward lower free energy. worst_alt_ee is that
    # state's energy; d_ee_worst_alt is how far ON beats it. A design can look good on
    # d_ee_both alone yet have a mediocre d_ee_worst_alt, if one single trigger already
    # competes closely with full activation.
    worst_alt_ee = min(out["ee_off"], out["ee_t5"], out["ee_t3"])
    out["d_ee_worst_alt"] = out["ee_both"] - worst_alt_ee

    # Both toeholds have to be open in the OFF state for either trigger to nucleate, so
    # the limiting one is the one that decides whether this construct can start at all.
    off_matrix = folder.base_pair_probabilities(fused)
    out["access_5p"] = _mean_unpaired(off_matrix, *built["toehold_5p"])
    out["access_3p"] = _mean_unpaired(off_matrix, *built["toehold_3p"])
    out["access_min"] = min(out["access_5p"], out["access_3p"])

    # Whichever Kozak actually survives fusion (always the 3' half's -- the 5' half's own
    # copy was cut away in fuse()) is the one the 5' toehold could realistically
    # hybridise to in the finished molecule -- its own Kozak is gone, but nothing stops it
    # from reaching the surviving one instead: intramolecular pairing does not require
    # adjacency. A real ViennaRNA fold earlier this session found exactly this kind of
    # pairing spanning ~50 nt of intervening hairpin, so "less important" for the 5'
    # toehold is not "not checked".
    fused_kozak_span = built["domains_3p"].get("kozak")
    if fused_kozak_span is not None:
        kozak_seq = fused[fused_kozak_span[0] : fused_kozak_span[1]]
        toehold_5p_seq = fused[built["toehold_5p"][0] : built["toehold_5p"][1]]
        out["kozak_rc_5p"] = motif_self_bind_score(toehold_5p_seq, kozak_seq)
    else:
        out["kozak_rc_5p"] = None
    out["kozak_rc_3p"] = own_kozak_rc_3p

    # Mirror check, other direction: the prefix always survives fusion -- it belongs to
    # the 5' half, and fuse() never cuts it (only the 3' half's prefix is cut, in the
    # keep_after step). So it's the 3' toehold that could realistically reach back and
    # hybridise to it, same "distance is not protection" reasoning as the Kozak check
    # above, just pointed the other way down the molecule.
    fused_prefix_span = built["domains_5p"].get("prefix")
    if fused_prefix_span is not None:
        prefix_seq = fused[fused_prefix_span[0] : fused_prefix_span[1]]
        toehold_3p_seq = fused[built["toehold_3p"][0] : built["toehold_3p"][1]]
        out["prefix_rc_3p"] = motif_self_bind_score(toehold_3p_seq, prefix_seq)
    else:
        out["prefix_rc_3p"] = None
    out["prefix_rc_5p"] = own_prefix_rc_5p
    return out
