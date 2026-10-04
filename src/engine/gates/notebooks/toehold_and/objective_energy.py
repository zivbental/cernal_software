"""The energy-sum objective function for the A0 two-input toehold AND gate.

    uv run python src/engine/gates/notebooks/toehold_and/objective_energy.py \
        --from wob --out objective_energy

Every term is a free energy in kcal/mol, taken as a difference of ensemble energies, and
**every weight is 1**. That is not a convention chosen for lack of data -- it is what free
energies do. A sum of free energies is a free energy, so the terms compose without anyone
deciding how much each is worth. The probability-based score this replaces could not say
that: a ratio of accessibilities and a log-rate have no common unit, so combining them
always meant inventing a weight, and the project's standing rule forbids fitting one.

**Why energies rather than the probabilities we started from.** They are the same numbers --
``G_constrained - G_ensemble = -RT ln(Q_constrained / Q)`` -- but across the four tubes of
one real design the probabilities span ``1.9e-15`` to ``3.4e-04`` while the energies span
4.93 to 20.89 kcal/mol. The probability underflows in exactly the states where the answer
matters, and a score that has to return ``None`` there cannot rank. See
``FoldEngine.open_penalty``.

**Why the constraint is on the stem rather than on the RBS/AUG window.** A window constraint
asks "is this region unpaired", which a design can satisfy by refolding the region onto
something else. Measured on the VISTA library, 57 of 60 switches re-pair the RBS-to-AUG
window in the ON state while leaving the RBS and the start codon themselves free -- benign
refolding that a window score reports as failure. Our own unfiltered sweep is worse still
(the whole window re-paired in the median design). Constraining the stem's own arms cannot
be faked that way. The bulge between the arms is deliberately left unconstrained: the AUG
sits there and is already open in the OFF state, which is the architecture's own design
(``ToeholdAndGate`` intended-structure docstring), so forcing it open would price something
that is never shut.

**Why one constraint direction throughout.** Forcing a stem *closed* measures 0.00 +/- 0.00
kcal/mol in every state of every design tested -- the stem is already paired in the
ensemble, so the constraint is pre-satisfied and the term is identically zero. Only forcing
it *open* separates the states. So all four tubes are scored with the same open constraint
and the gate's quality is their contrast.

The score, minimised:

    open(s)  = open_penalty(tube s, the main stem's descending arms)

    Score =   open(11) - min[ open(00), open(01), open(10) ]   <- AND-ness
            + barrier(00 -> 11)                               <- activation, find_saddle
            + access(A) + access(B)                           <- accessibility, as energy
            + offtarget

Line 1 is the whole gate in one number. ``min`` over the three OFF states is the honest AND
condition, because any one of them leaking breaks the gate -- and it is what caught the
failure the ratio hid: on a design whose ``A_M`` ratio read 10.99, this line reads **-0.03
kcal/mol**, because trigger A alone opens the stem as well as A and B together. A gate whose
state 10 held would score about -16.

Accessibility is a **term, not a filter**. Opening trigger A's own site inside the 711-nt
transcript costs about +17 kcal/mol while the duplex it then forms is worth far more, so a
hard accessibility cut discards designs that would have paid for themselves -- and it was
also what kept long-overlap trigger pairs out of the panel. As a penalty on the same axis as
everything else it competes honestly. Only physically disqualifying facts stay filters: an
in-frame stop, a restriction site, a forbidden motif.

The slope is not a separate term. ``open(11) - open(00)`` *is* the thermodynamic slope, so
line 1 already contains it; adding it again would double-weight the same contrast. The
barrier is the independent kinetic quantity, and it is an **upper bound** -- findpath walks a
heuristic direct path, not the minimum-barrier path.
"""

import argparse
import csv
import glob
import math
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402

#: Offsets of every domain from ``sws_end = len(switch) - 75``, taken from the assembly order
#: in ``ToeholdAndGate``: main_pre_star(9) bulge_star(3) k1_star(6) rbs_loop(18) main_z(6)
#: aug(3) main_pre(9) linker(21). Derived rather than searched, because the first AUG in the
#: string is upstream of the real start in some switches.
_OFFSETS: dict[str, tuple[int, int]] = {
    "main_pre_star": (0, 9),
    "bulge_star": (9, 12),
    "k1_star": (12, 18),
    "rbs_loop": (18, 36),
    "main_z": (36, 42),
    "aug": (42, 45),
    "main_pre": (45, 54),
    "linker": (54, 75),
}


#: Rare E. coli codons. One in the first few codons after the AUG can stall the ribosome as
#: translation starts, so such a construct fails for a reason unrelated to its gate and the
#: result is uninterpretable. They are **excluded, not flagged**, because they are enriched among
#: the designs the model likes -- AGG and CGG are G-rich, so they strengthen pairing and the
#: folding score rewards what the cell punishes.
#:
#: The screen lives in the scorer rather than only in the panel because it is **free**: it reads
#: three codons off a string. Measured on 43,378 scored designs, 46.1% carry one, and 41.6% carry
#: one without also being excluded by scheme -- designs that were being fully folded for nothing.
RARE_CODONS = frozenset({"AGG", "AGA", "CGA", "CGG", "CUA", "AUA", "CCC", "UCG"})

#: How many codons after the AUG to screen. Codons 4-10 are the fixed linker and always clean.
CODONS_SCREENED = 3

#: Ceiling on ``open_11`` in kcal/mol: the ON state has to actually open. ``open`` is a *cost*,
#: so lower is better here.
#:
#: **Calibrated against Green's measured switches rather than our own population.** An earlier
#: version used our median, 8.0, which is a joint opening probability of 2.3e-06 and admitted a
#: "best" candidate whose stem was **97% paired in the ON state** -- its AND-ness of -16.46 was
#: a ratio between two numbers both effectively zero. Green's 168 built-and-measured switches
#: have a median ON cost of 3.64, and the 77 above 20-fold ON/OFF have a median of **3.07**. So
#: 4.0 admits designs whose ON state costs no more than a switch known to work. It keeps 19.2%
#: of designs. (VISTA's median is 9.25 -- the refolding problem again; Green is the reference.)
ON_CEILING = 4.0


def early_codons(switch: str) -> list[str]:
    """The first ``CODONS_SCREENED`` codons after the AUG.

    The AUG is at ``len(switch) - 33``, derived rather than searched: every domain from ``main_z``
    onward is anchored to the 3' end (aug 3 + main_pre 9 + linker 21 = 33), and the first AUG in
    the string is upstream of the real start in some switches.
    """
    aug = len(switch) - 33
    return [switch[aug + 3 + 3 * i : aug + 6 + 3 * i] for i in range(CODONS_SCREENED)]


def domains(switch: str) -> dict[str, tuple[int, int]]:
    """Absolute ``(start, end)`` of each domain in this switch, 0-based, end exclusive."""
    base = len(switch) - 75
    return {name: (base + lo, base + hi) for name, (lo, hi) in _OFFSETS.items()}


def mfe_partners(folder, strands: str) -> dict[int, int]:
    """Position -> its partner in this tube's MFE structure, with the ``&`` removed.

    The separator is dropped before indexing, so positions are offsets into the concatenated
    strands -- the switch first, then each trigger in the order written.
    """
    folded = folder.mfe(strands)
    if folded is None:
        return {}
    structure = folded.structure.replace("&", "")
    stack: list[int] = []
    partner: dict[int, int] = {}
    for index, char in enumerate(structure):
        if char == "(":
            stack.append(index)
        elif char == ")":
            if not stack:
                return {}
            opened = stack.pop()
            partner[index] = opened
            partner[opened] = index
    return partner


def a_contacts(folder, strands: str, switch_len: int, trig_a_len: int) -> set[int]:
    """Which SWITCH positions trigger A is paired to, in the MFE of this tube.

    Trigger A occupies ``[switch_len, switch_len + trig_a_len)`` of the concatenation, so the
    caller writes the strands with A immediately after the switch.
    """
    partner = mfe_partners(folder, strands)
    return {
        partner[i]
        for i in range(switch_len, switch_len + trig_a_len)
        if i in partner and partner[i] < switch_len
    }


def ascending_arm(switch: str) -> set[int]:
    """The main stem's ascending arm: ``main_pre* + bulge* + k1*``, as switch positions."""
    spans = domains(switch)
    return (
        set(range(*spans["main_pre_star"]))
        | set(range(*spans["bulge_star"]))
        | set(range(*spans["k1_star"]))
    )


def engages_stem_mfe(folder, switch: str, trig_a: str, trig_b: str | None = None) -> float | None:
    """Share of trigger A's MFE contacts that land on the ascending arm. ``None`` if it has none.

    **The MFE question, deliberately, beside the ensemble one.** ``engaged_arm_11`` sums pair
    probabilities over the whole ensemble and answers "how much of main_pre* is paired to A on
    average". This answers "in the single most probable structure, is A on the stem at all" --
    and that is the structure the report DRAWS, so a design reading 0 here is a design whose
    picture shows a shut main hairpin in the ON tube.
    """
    strands = f"{switch}&{trig_a}" if trig_b is None else f"{switch}&{trig_a}&{trig_b}"
    contacts = a_contacts(folder, strands, len(switch), len(trig_a))
    if not contacts:
        return None
    return len(contacts & ascending_arm(switch)) / len(contacts)


def main_stem_arms(switch: str) -> tuple[tuple[int, int], ...]:
    """The descending arms of the main stem: ``main_z`` and ``main_pre``.

    The ``aug`` bulge between them is excluded on purpose -- see the module docstring. These
    two spans are what every tube is scored against, so that the four numbers are
    comparable.
    """
    d = domains(switch)
    return (d["main_z"], d["main_pre"])


def intended_duplexes(switch: str, len_x: int) -> dict[str, tuple[range, range]]:
    r"""The four duplexes the two hairpins are supposed to form, as index ranges to be zipped.

    Each entry is ``(five_prime, three_prime_reversed)``: position ``a[k]`` is meant to pair with
    ``b[k]``, so a caller zips them.

        main stem     main_pre_star <-> main_pre      9 bp
                      k1_star       <-> main_z        6 bp
        secondary     sw_x          <-> x*          len_x bp
                      k2*           <-> sec_z          k2 bp

    **What is deliberately NOT here, and why each omission matters.**

    * The **linker** and the **cap/r2-star** stretch. Both carry internal structure by design, so a
      whole-molecule ensemble defect counts their folding as deviation when it is the intent. That
      is the flaw in reading ``d_off`` as "do the two hairpins form".
    * The **AUG bulge** (``bulge_star`` against ``aug``). It is deliberately not a stem -- the AUG
      sits open in the OFF state -- and the ``closure`` axis varies it on purpose, so scoring it as
      deviation would penalise the very thing the sweep is exploring.
    * The **loops** (``rbs_loop``, ``sec_loop``). Unpaired by intent.

    The secondary arm length is derived per switch rather than assumed, so the two geometries are
    each measured against their own intended shape -- 161 nt and 165 nt give different ``k2``.
    """
    d = domains(switch)
    sws_end = len(switch) - 75
    k2 = (sws_end - 50 - 2 * len_x) // 2
    sw_x = (35, 35 + len_x)
    k2_star = (35 + len_x, 35 + len_x + k2)
    sec_z = (50 + len_x + k2, 50 + len_x + 2 * k2)
    x_star = (50 + len_x + 2 * k2, sws_end)
    return {
        "main_pre": (
            range(*d["main_pre_star"]),
            range(d["main_pre"][1] - 1, d["main_pre"][0] - 1, -1),
        ),
        "k1": (range(*d["k1_star"]), range(d["main_z"][1] - 1, d["main_z"][0] - 1, -1)),
        "lock": (range(*sw_x), range(x_star[1] - 1, x_star[0] - 1, -1)),
        "sec": (range(*k2_star), range(sec_z[1] - 1, sec_z[0] - 1, -1)),
    }


def hairpin_fidelity(folder: FoldEngine, switch: str, len_x: int) -> dict[str, float | None]:
    """How much of each intended duplex actually forms in the OFF state, 0 to 1.

    The matrix is symmetric with a zero diagonal, so one term per pair and never two -- summing
    both triangles reads a probability above 1, which has been a real bug in this repo.
    """
    matrix = folder.pooled_pair_probabilities(switch)
    out: dict[str, float | None] = {}
    for name, (left, right) in intended_duplexes(switch, len_x).items():
        pairs = [(i, j) for i, j in zip(left, right, strict=False) if i < j < len(matrix)]
        out[name] = round(sum(matrix[i][j] for i, j in pairs) / len(pairs), 3) if pairs else None
    formed = [v for v in out.values() if v is not None]
    # The weakest duplex, not the mean: a hairpin with one arm fully formed and the other absent
    # is not half a hairpin, it is a different structure.
    out["worst"] = round(min(formed), 3) if formed else None
    return out


def accessibility_table(
    folder: FoldEngine, transcript: str, windows: set[tuple[int, int]], path: Path
) -> dict[tuple[int, int], float | None]:
    """Cost of opening each trigger window on the transcript, computed once and cached.

    **Why this exists.** The two accessibility terms fold the whole 711-nt transcript, which
    at O(n^3) costs about 2.3 s per window against 1.1 s for all four switch tubes together
    — measured at **80% of the per-design time**. And they are properties of the trigger
    *pair*, identical for every design on it: the sweep has 748 distinct A windows and 869
    distinct B windows against 390,814 designs, so each fold was being repeated about 522
    times. Precomputing them turns a 466-hour run into a feasible one.

    The table is a CSV so that parallel shards share it instead of each rebuilding it. Missing
    windows are computed and appended; an existing file is read and trusted.
    """
    table: dict[tuple[int, int], float | None] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                value = row.get("penalty")
                table[(int(row["start"]), int(row["end"]))] = (
                    None if value in (None, "", "None") else float(value)
                )
        print(f"  accessibility cache: {len(table):,} windows from {path.name}")
    missing = sorted(windows - set(table))
    if missing:
        print(f"  computing {len(missing):,} new transcript windows (~2.3 s each)")
        with path.open("a" if path.exists() else "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("start", "end", "penalty"))
            if not table:
                writer.writeheader()
            for index, (start, end) in enumerate(missing):
                value = folder.open_penalty(transcript, ((start, end),))
                table[(start, end)] = value
                writer.writerow({"start": start, "end": end, "penalty": value})
                handle.flush()
                if index % 25 == 0:
                    print(f"    {index + 1}/{len(missing)}", flush=True)
    return table


def score_design(
    folder: FoldEngine,
    switch: str,
    trigger_a: str,
    trigger_b: str,
    *,
    transcript: str | None = None,
    site_a: tuple[int, int] | None = None,
    site_b: tuple[int, int] | None = None,
    access: dict[tuple[int, int], float | None] | None = None,
    on_ceiling: float | None = None,
) -> dict[str, float | None]:
    """Every term of the objective for one design, plus the total.

    A term that could not be measured is ``None`` and the total is ``None`` with it. Never
    0.0: zero is what a perfectly accessible stem costs, so substituting it for a failed
    measurement would turn an unmeasurable design into the best one in the sweep.

    **Measured cheapest-first, because the components differ by 13x.** Cold-cache cost per
    design, on 14 real designs:

        barrier   1.055 s   52.1%
        tube 11   0.547 s   27.0%
        tube 01   0.187 s    9.2%
        tube 10   0.155 s    7.7%
        tube 00   0.082 s    4.0%

    The barrier is over half the cost and used to run on every design, although only **6.3%** of
    designs survive the filters that decide whether a design is worth ranking at all. So the ON
    tube goes first -- it alone decides the ``on_ceiling``, which rejects 88% -- and the barrier
    goes last. With the free rare-codon screen in the caller, that is a measured **5.7x** on the
    remaining sweep: 33 h wall becomes 5.8 h on five shards.

    Args:
        transcript, site_a, site_b: the endogenous context. Given all three, the two
            accessibility terms are priced; otherwise they are ``None`` and so is the total,
            because a score missing a term it claims to contain is worse than no score.
        on_ceiling: stop after the ON tube when its opening cost exceeds this, and set
            ``skipped`` to say so. **A ``None`` beside a ``skipped`` reason means "not
            attempted", not "measurement failed"** -- the two are different and the column
            exists so they cannot be confused. Leave it unset to measure everything.
    """
    arms = main_stem_arms(switch)
    if switch[domains(switch)["aug"][0] :][:3] != "AUG":
        return {"error_no_aug": 1.0}

    out: dict[str, float | None] = {}

    # The ON tube first: it is the only one the ceiling needs, and the ceiling rejects 88%.
    out["open_11"] = folder.open_penalty(f"{switch}&{trigger_a}&{trigger_b}", arms)
    if on_ceiling is not None and (out["open_11"] is None or out["open_11"] > on_ceiling):
        out["skipped"] = "on_ceiling"
        return out

    for state, strands in (
        ("00", switch),
        ("01", f"{switch}&{trigger_b}"),
        ("10", f"{switch}&{trigger_a}"),
    ):
        out[f"open_{state}"] = folder.open_penalty(strands, arms)

    off_states = [out["open_00"], out["open_01"], out["open_10"]]
    on_state = out["open_11"]
    out["andness"] = (
        None
        if on_state is None or any(v is None for v in off_states)
        else on_state - min(v for v in off_states if v is not None)
    )

    # The barrier, on the switch alone: OFF structure -> the same structure with the main
    # stem's arms released. findpath takes one strand, so this is the switch's own
    # refolding cost and not the trigger-bound path; it is the wall the molecule must clear
    # once the trigger has committed, and it is an upper bound.
    folded = folder.mfe(switch)
    target = list(folded.structure)
    partner: dict[int, int] = {}
    stack: list[int] = []
    for index, char in enumerate(folded.structure):
        if char == "(":
            stack.append(index)
        elif char == ")":
            opened = stack.pop()
            partner[index] = opened
            partner[opened] = index
    for lo, hi in arms:
        for index in range(lo, min(hi, len(target))):
            if index in partner:
                target[partner[index]] = "."
            target[index] = "."
    out["barrier"] = folder.saddle(switch, folded.structure, "".join(target))

    if access is not None and site_a is not None and site_b is not None:
        out["access_a"] = access.get(site_a)
        out["access_b"] = access.get(site_b)
    elif transcript is not None and site_a is not None and site_b is not None:
        out["access_a"] = folder.open_penalty(transcript, (site_a,))
        out["access_b"] = folder.open_penalty(transcript, (site_b,))
    else:
        out["access_a"] = out["access_b"] = None

    parts = [out["andness"], out["barrier"], out["access_a"], out["access_b"]]
    out["score"] = None if any(v is None for v in parts) else sum(v for v in parts if v is not None)
    return out


_FIELDS = (
    "switch",
    "a_start",
    "a_end",
    "b_start",
    "b_end",
    "open_00",
    "open_01",
    "open_10",
    "open_11",
    "andness",
    "barrier",
    "access_a",
    "access_b",
    "score",
    "skipped",
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="prefix", default="wob", help="folded shard prefix")
    parser.add_argument("--out", default="objective_energy")
    parser.add_argument("--limit", type=int, default=0, help="score only the first N designs")
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="score N designs spread EVENLY across the shard instead of the first N. The "
        "shards are ordered by trigger pair, so --limit samples a handful of pairs deeply "
        "and tells you nothing about the rest; an even stride spans the pairs. Deterministic "
        "by construction, so no seed is involved",
    )
    parser.add_argument(
        "--skip-scheme",
        default="A-anchored,unlocked",
        help="schemes to leave unscored. Both defaults gate in 0 of 4,330 and 0 of 384 "
        "designs measured, and the mechanism is known -- A-anchored spends lock strength on "
        "trigger A's own site, so A alone opens the stem. Only 1.3%% of the sweep, so this "
        "buys cleanliness rather than time. Pass an empty string to score everything",
    )
    parser.add_argument(
        "--keep-rare",
        action="store_true",
        help="score designs carrying a rare E. coli codon in the first 3 codons after the AUG. "
        "Off by default: the panel excludes them anyway, so folding them is pure waste, and it "
        "is 46.1%% of the sweep measured on 43,378 scored designs. The screen reads three codons "
        "off a string, so it costs nothing and runs before any folding",
    )
    parser.add_argument(
        "--on-ceiling",
        type=float,
        default=ON_CEILING,
        help="stop after the ON tube when its opening cost exceeds this, in kcal/mol. The ON "
        "tube is 27%% of a design's cost and the ceiling rejects 88%%, so this skips the three "
        "OFF tubes and the barrier -- together 73%% -- for the designs that were never going to "
        "rank. Pass a large number to measure everything",
    )
    parser.add_argument(
        "--closure",
        default="",
        help="comma-separated closure levels to keep; empty means all. Used to put the "
        "informative designs first: open_3x3 is 17%% of the sweep and gates in 14.3%% against "
        "~55%% for every closed level, so scoring the closed ones first surfaces candidates "
        "sooner. Deprioritised rather than excluded, because that evidence replicates but is "
        "not as firm as the scheme result",
    )
    parser.add_argument(
        "--access-only",
        action="store_true",
        help="build the accessibility table for this family and stop. Run this ONCE before "
        "launching shards: they all append to the same CSV, and concurrent appends corrupt "
        "it. With the table already complete the shards only read it",
    )
    parser.add_argument(
        "--access-table",
        default="accessibility_penalty",
        help="CSV under results/ holding the per-window transcript opening cost. Shared by "
        "every run and every shard, so the expensive transcript folds happen once",
    )
    parser.add_argument(
        "--shard",
        default="",
        metavar="i/n",
        help="score only shard i of n, writing {out}_{i}.csv. Run n of these at once, one "
        "per core. Safe to fork: this module never touches RNA.cvar, and the temperature "
        "travels on an explicit RNA.md() inside FoldEngine. Shards are cut by position in "
        "the design list, which is ordered by trigger pair, so each shard spans pairs",
    )
    parser.add_argument(
        "--fasta",
        default="mCherry_original.txt",
        help="transcript for the accessibility terms; without it those terms are None",
    )
    args = parser.parse_args(argv)

    here = Path(__file__).resolve().parent
    results = here / "results"
    shards = sorted(glob.glob(str(results / f"{args.prefix}_folded_*.csv")))
    if not shards:
        print(f"no shards matching {args.prefix}_folded_*.csv in {results}")
        return 1

    transcript = None
    fasta = here / args.fasta
    if fasta.exists():
        raw = fasta.read_text()
        transcript = sq.to_rna(
            "".join(line.strip() for line in raw.splitlines() if not line.startswith(">")).upper()
        )
        print(f"  transcript {len(transcript)} nt from {fasta.name}")

    skip = {v.strip() for v in args.skip_scheme.split(",") if v.strip()}
    keep_closure = {v.strip() for v in args.closure.split(",") if v.strip()}
    rows: list[dict] = []
    dropped = {"scheme": 0, "closure": 0, "rare codon": 0}
    for shard in shards:
        with open(shard, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if not (row.get("switch") and row.get("a_start")):
                    continue
                if skip and (row.get("scheme") or "") in skip:
                    dropped["scheme"] += 1
                    continue
                if keep_closure and (row.get("closure") or "") not in keep_closure:
                    dropped["closure"] += 1
                    continue
                # Free, and before any folding: three codons off a string against a set.
                if not args.keep_rare and any(
                    codon in RARE_CODONS for codon in early_codons(row["switch"])
                ):
                    dropped["rare codon"] += 1
                    continue
                rows.append(row)
    for reason, count in dropped.items():
        if count:
            print(f"  skipped {count:,} designs by {reason}")
    shard_index = shard_total = None
    if args.shard:
        shard_index, shard_total = (int(v) for v in args.shard.split("/"))
        if not 0 <= shard_index < shard_total:
            print(f"bad --shard {args.shard}: need 0 <= i < n")
            return 1

    if args.access_only:
        pass
    elif args.sample and args.sample < len(rows):
        stride = len(rows) / args.sample
        rows = [rows[int(i * stride)] for i in range(args.sample)]
    elif args.limit:
        rows = rows[: args.limit]
    if args.access_only:
        print("  --access-only: ignoring --sample/--limit/--shard so every window is covered")
    elif shard_total is not None:
        rows = [row for index, row in enumerate(rows) if index % shard_total == shard_index]
        print(f"  shard {shard_index} of {shard_total}")
    print(f"  {len(rows):,} designs from {len(shards)} shard(s)")

    # Streaming and resume are a standing requirement here, not an optimisation: a long run
    # that dies having written nothing has cost its whole runtime.
    name = args.out if shard_total is None else f"{args.out}_{shard_index}"
    path = results / f"{name}.csv"
    done: set[str] = set()
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            done = {r["switch"] for r in csv.DictReader(handle) if r.get("switch")}
        print(f"  resuming: {len(done):,} already scored")

    folder = FoldEngine(37.0)

    access = None
    if transcript is not None:
        windows: set[tuple[int, int]] = set()
        for row in rows:
            windows.add((int(row["a_start"]), int(row["a_end"])))
            windows.add((int(row["b_start"]), int(row["b_end"])))
        access = accessibility_table(
            folder, transcript, windows, results / f"{args.access_table}.csv"
        )
        if args.access_only:
            print(f"  accessibility table complete: {len(access):,} windows")
            return 0

    written = short = 0
    with path.open("a" if done else "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS, extrasaction="ignore")
        if not done:
            writer.writeheader()
        for index, row in enumerate(rows):
            switch = row["switch"]
            if switch in done:
                continue
            site_a = (int(row["a_start"]), int(row["a_end"]))
            site_b = (int(row["b_start"]), int(row["b_end"]))
            scored = score_design(
                folder,
                switch,
                transcript[site_a[0] : site_a[1]] if transcript else "",
                transcript[site_b[0] : site_b[1]] if transcript else "",
                transcript=transcript,
                site_a=site_a,
                site_b=site_b,
                access=access,
                on_ceiling=args.on_ceiling,
            )
            if "error_no_aug" in scored:
                continue
            writer.writerow({"switch": switch, **{k: row.get(k) for k in _FIELDS[1:5]}, **scored})
            handle.flush()
            written += 1
            if scored.get("skipped"):
                short += 1
            if index % 50 == 0:
                print(
                    f"  {index + 1}/{len(rows)}  scored {written:,}  "
                    f"({short:,} stopped at the ON ceiling)",
                    flush=True,
                )

    # A row that stopped at the ceiling is still WRITTEN, so --resume never scores it twice, and
    # it carries `skipped` so its empty cells read as "not attempted" and not "measurement
    # failed". `load()` in objective_panel drops it for having no `andness`, which is correct:
    # it is infeasible by construction and belongs in no population.
    print(
        f"  wrote {written:,} new rows to {path.name} "
        f"({short:,} stopped at the ON ceiling, {written - short:,} measured in full)"
    )
    scores = [
        float(r["score"])
        for r in csv.DictReader(path.open(encoding="utf-8", newline=""))
        if r.get("score") not in (None, "")
    ]
    if scores:
        scores.sort()
        mid = scores[len(scores) // 2]
        mean = sum(scores) / len(scores)
        sd = math.sqrt(sum((x - mean) ** 2 for x in scores) / len(scores))
        print(
            f"  score over {len(scores):,}: median {mid:.2f}  mean {mean:.2f}  sd {sd:.2f}  "
            f"best {scores[0]:.2f}  worst {scores[-1]:.2f}  (lower is better)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
