"""Evaluate the ordering sheet's sanity checks in Python, on the data the sheet is built from.

    uv run python src/engine/gates/notebooks/toehold_and/report/check_order_sheet.py

**Why this exists.** ``export_xlsx.html`` writes every sanity check as an Excel FORMULA, so that a
wrong cell fails in the reader's own Excel rather than being blessed by whatever wrote the file.
That is the right design and it has one gap: nothing here can run Excel, so the formulas go out
unevaluated. This script closes half the gap -- it evaluates the same PREDICATES over the same
``panel_data.json``, so a check that is wrong about the biology fails here, before anyone orders
anything. What it cannot check is the Excel SYNTAX of the formulas; that needs one click.

**It also tests the checks themselves.** A check that passes on good data proves nothing until it
is shown to fail on bad data, so each one is re-run against a deliberately corrupted copy -- a
shifted coordinate, a swapped base, a recoded window left intact. A check that still passes there
is a check that cannot catch the bug it is named for, and that is reported as a failure of the
check rather than a pass of the data.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPLEMENT = {"A": "U", "U": "A", "G": "C", "C": "G"}


def revcomp(seq: str) -> str:
    return "".join(COMPLEMENT.get(base, base) for base in reversed(seq))


def part(cand: dict, name: str) -> str:
    domain = next((d for d in cand.get("alld", []) if d["name"] == name), None)
    return cand["seq"][domain["s"] : domain["e"]] if domain else ""


def halves(cand: dict, name: str) -> tuple[str, str]:
    domain = next((d for d in cand.get("alld", []) if d["name"] == name), None)
    if not domain:
        return "", ""
    mid = domain["s"] + (domain["e"] - domain["s"]) // 2
    return cand["seq"][domain["s"] : mid], cand["seq"][mid : domain["e"]]


def rbs_split(cand: dict) -> tuple[str, str]:
    domain = next((d for d in cand.get("alld", []) if d["name"] == "rbs_loop"), None)
    if not domain:
        return "", ""
    return cand["seq"][domain["s"] : domain["s"] + 7], cand["seq"][domain["s"] + 7 : domain["e"]]


#: One entry per sanity check in the sheet, in the same order and with the same label.
#:
#: Each is ``(label, predicate)`` where the predicate takes the rows and the four transcripts and
#: returns True when the sheet should read OK. ``corrupt`` below pairs each with a way to break it.
def build_checks() -> list[tuple[str, Callable[[list[dict], dict], bool]]]:
    def in_original(rows, tr, which):
        original = tr["original"]["seq"]
        key = "trigA" if which == "A" else "trigB"
        return all(c[key] in original for c in rows)

    def overlap_small(rows, _tr):
        worst = 0
        for one in rows:
            for two in rows:
                if one is two:
                    continue
                shared = min(one["wa"][1], two["wb"][1]) - max(one["wa"][0], two["wb"][0])
                worst = max(worst, shared)
        return worst <= 2

    def constants(rows, _tr):
        return (
            all(part(c, "cap") == "GGG" for c in rows)
            and all(part(c, "aug") == "AUG" for c in rows)
            and len({part(c, "sec_loop") for c in rows}) == 1
            and len({rbs_split(c)[0] for c in rows}) == 1
            and len({rbs_split(c)[1] for c in rows}) == 1
            and len({part(c, "linker") for c in rows}) == 1
            and len(part(rows[0], "sec_loop")) == 15
            and len(rbs_split(rows[0])[0]) == 7
            and len(rbs_split(rows[0])[1]) == 11
            and len(part(rows[0], "linker")) == 21
        )

    def alphabet(rows, _tr):
        for c in rows:
            for seq in (c["seq"], c["trigA"], c["trigB"], c["xseq"]):
                if set(seq) - set("ACGU"):
                    return False
        return True

    def window_lengths(rows, _tr):
        return all(
            len(c["trigA"]) == c["wa"][1] - c["wa"][0]
            and len(c["trigB"]) == c["wb"][1] - c["wb"][0]
            for c in rows
        )

    def windows_match_transcript(rows, tr):
        original = tr["original"]["seq"]
        return all(
            original[c["wa"][0] : c["wa"][1]] == c["trigA"]
            and original[c["wb"][0] : c["wb"][1]] == c["trigB"]
            for c in rows
        )

    def switch_length(rows, _tr):
        return all(len(c["seq"]) in (161, 165) for c in rows)

    def parts_rebuild(rows, _tr):
        names = [
            "cap",
            "r2*",
            "sw_x",
            "k2*",
            "sec_loop",
            "sec_z",
            "x*",
            "main_pre_star",
            "bulge_star",
        ]
        for c in rows:
            built = "".join(part(c, n) for n in names)
            built += halves(c, "k1_star")[0] + halves(c, "k1_star")[1]
            built += rbs_split(c)[0] + rbs_split(c)[1]
            built += halves(c, "main_z")[0] + halves(c, "main_z")[1]
            built += part(c, "aug") + part(c, "main_pre") + part(c, "linker")
            if built != c["seq"]:
                return False
        return True

    def x_is_real(rows, _tr):
        return all(
            c["xseq"]
            and c["wx"]
            and c["trigA"][c["wx"][0] - c["wa"][0] : c["wx"][1] - c["wa"][0]] == c["xseq"]
            and part(c, "sw_x") == c["xseq"]
            for c in rows
        )

    def revcomp_checks(rows, _tr):
        return all(
            part(c, "sw_x") == revcomp(part(c, "x*")) and c["xseq"] == revcomp(part(c, "x*"))
            for c in rows
        )

    def recode_changes(rows, tr, variant, role, must_change):
        if variant not in tr:
            return True
        seq, original = tr[variant]["seq"], tr["original"]["seq"]
        key = "wa" if role == "A" else "wb"
        for c in rows:
            lo, hi = c[key]
            changed = seq[lo:hi] != original[lo:hi]
            if changed is not must_change:
                return False
        return True

    def realises_states(rows, tr):
        """Each transcript changes exactly the windows its state says are gone, per DESIGN.

        **The general form of four role-named checks this replaces.** Those asked whether
        "A-recoded" changes every A window, which is not a question that exists on a panel using
        the role swap: there the transcripts are T0..T3 and the same one removes trigger A for one
        pair and trigger B for the other. The state is a property of the (transcript, pair) cell,
        so the check has to be too.
        """
        original = tr["original"]["seq"] if "original" in tr else None
        if original is None:
            original = next((t["seq"] for t in tr.values() if int(t["changed_nt"] or 0) == 0), None)
        if original is None:
            return False
        for cand in rows:
            states = dict(
                part.split("=", 1)
                for part in str(cand.get("swap_states") or "").split()
                if "=" in part
            )
            for name, entry in tr.items():
                state = states.get(name) or entry.get("states") or ""
                if len(state) != 2:
                    return False
                for role, gone in (("A", state[0] == "0"), ("B", state[1] == "0")):
                    lo, hi = cand["wa" if role == "A" else "wb"]
                    changed = entry["seq"][lo:hi] != original[lo:hi]
                    if changed is not gone:
                        return False
        return True

    def same_length(_rows, tr):
        return len({len(t["seq"]) for t in tr.values()}) == 1

    return [
        ("Trigger A sequence is in original mCherry", lambda r, t: in_original(r, t, "A")),
        ("Trigger B sequence is in original mCherry", lambda r, t: in_original(r, t, "B")),
        ("no more than 2 overlaps between triggers", overlap_small),
        ("all constant subsequences are constant", constants),
        ("every sequence is A/C/G/U only", alphabet),
        ("window length matches start and end", window_lengths),
        ("trigger sequences are the transcript at those coordinates", windows_match_transcript),
        ("switch length is 161 or 165", switch_length),
        ("the parts rebuild the full switch", parts_rebuild),
        ("overlap is real: x is in trigger A and sw_x is x", x_is_real),
        ("sw_x and x are revcomp(x*)", revcomp_checks),
        ("every transcript realises the state it is labelled with", realises_states),
        ("the four transcripts are all the same length", same_length),
    ]


#: How to break each check, so a check that cannot fail is reported rather than trusted.
#:
#: Each returns a corrupted ``(rows, transcripts)`` pair. They are deliberately small: one base,
#: one coordinate, one window left intact -- the size of mistake a sheet actually makes.
def corruptions() -> dict[str, Callable[[list[dict], dict], tuple[list[dict], dict]]]:
    def deep(rows, tr):
        return json.loads(json.dumps(rows)), json.loads(json.dumps(tr))

    def shift_coordinate(rows, tr):
        rows, tr = deep(rows, tr)
        rows[0]["wa"] = [rows[0]["wa"][0] + 1, rows[0]["wa"][1] + 1]
        return rows, tr

    def break_base(rows, tr):
        rows, tr = deep(rows, tr)
        rows[0]["trigA"] = "X" + rows[0]["trigA"][1:]
        return rows, tr

    def shorten(rows, tr):
        rows, tr = deep(rows, tr)
        rows[0]["trigA"] = rows[0]["trigA"][:-1]
        return rows, tr

    def break_constant(rows, tr):
        rows, tr = deep(rows, tr)
        # The AUG, by editing the switch under it rather than the column, which is what a real
        # filling bug looks like: the parts come off the sequence.
        aug = next(d for d in rows[0]["alld"] if d["name"] == "aug")
        seq = rows[0]["seq"]
        rows[0]["seq"] = seq[: aug["s"]] + "AUA" + seq[aug["e"] :]
        return rows, tr

    def unrecode(variant, role):
        """Put the ORIGINAL bases back into one window of one variant: a recode that did nothing."""

        def breaker(rows, tr):
            rows, tr = deep(rows, tr)
            lo, hi = rows[0]["wa" if role == "A" else "wb"]
            seq = tr[variant]["seq"]
            tr[variant]["seq"] = seq[:lo] + tr["original"]["seq"][lo:hi] + seq[hi:]
            return rows, tr

        return breaker

    def over_recode(variant, role):
        """Recode a window the variant was supposed to leave alone: a recode that went too far."""

        def breaker(rows, tr):
            rows, tr = deep(rows, tr)
            lo, hi = rows[0]["wa" if role == "A" else "wb"]
            seq = tr[variant]["seq"]
            tr[variant]["seq"] = seq[:lo] + tr["AB-recoded"]["seq"][lo:hi] + seq[hi:]
            return rows, tr

        return breaker

    def truncate_transcript(rows, tr):
        rows, tr = deep(rows, tr)
        tr["B-recoded"]["seq"] = tr["B-recoded"]["seq"][:-3]
        return rows, tr

    def break_switch_length(rows, tr):
        rows, tr = deep(rows, tr)
        rows[0]["seq"] = rows[0]["seq"] + "A"
        return rows, tr

    def break_xstar(rows, tr):
        rows, tr = deep(rows, tr)
        star = next(d for d in rows[0]["alld"] if d["name"] == "x*")
        seq = rows[0]["seq"]
        flipped = "A" if seq[star["s"]] != "A" else "C"
        rows[0]["seq"] = seq[: star["s"]] + flipped + seq[star["s"] + 1 :]
        return rows, tr

    def move_x(rows, tr):
        rows, tr = deep(rows, tr)
        rows[0]["wx"] = [rows[0]["wx"][0] + 1, rows[0]["wx"][1] + 1]
        return rows, tr

    def overlap_windows(rows, tr):
        rows, tr = deep(rows, tr)
        # Make the second candidate's B window run into the first's A window by 5 nt.
        rows[-1]["wb"] = [rows[0]["wa"][0] - 5, rows[0]["wa"][0] + 5]
        return rows, tr

    def break_base_b(rows, tr):
        rows, tr = deep(rows, tr)
        rows[0]["trigB"] = "X" + rows[0]["trigB"][1:]
        return rows, tr

    # Each check is paired with a breaker that targets ITS OWN column and variant. Five of these
    # were wrong in the first version -- the B checks were handed a breaker that edited trigger A,
    # and all three "B-recoded"/"AB-recoded" checks one that edited the A-recoded transcript -- so
    # they reported BLIND. The checks were right; the test of the checks was not.
    return {
        "Trigger A sequence is in original mCherry": break_base,
        "Trigger B sequence is in original mCherry": break_base_b,
        "no more than 2 overlaps between triggers": overlap_windows,
        "all constant subsequences are constant": break_constant,
        "every sequence is A/C/G/U only": break_base,
        "window length matches start and end": shorten,
        "trigger sequences are the transcript at those coordinates": shift_coordinate,
        "switch length is 161 or 165": break_switch_length,
        "the parts rebuild the full switch": break_switch_length,
        "overlap is real: x is in trigger A and sw_x is x": move_x,
        "sw_x and x are revcomp(x*)": break_xstar,
        # Putting the original bases back into one window of one transcript is the failure this
        # check exists for -- it is exactly what the under-recoding bug in `role_swap` produced.
        "every transcript realises the state it is labelled with": unrecode(
            next(iter(("A-recoded", "T1"))), "A"
        ),
        "the four transcripts are all the same length": truncate_transcript,
    }


def main(argv=None) -> int:
    argv = list(argv or sys.argv[1:])
    view = argv[0] if argv else "the six to build"
    data = json.loads((HERE / "panel_data.json").read_text(encoding="utf-8"))
    rows = [
        c
        for c in data["cands"]
        if (c.get("panelset") or "default") in ("default", "both", "both4")
        and not str(c.get("control", "")).startswith("nothing")
        and not str(c.get("control", "")).startswith("arm 4")
    ]
    transcripts = {
        t["variant"]: t
        for t in data.get("transcripts", [])
        if (t.get("panelset") or "default") == "default"
    }
    print(f"  view {view!r}: {len(rows)} rows, {len(transcripts)} transcripts")
    if not rows or not transcripts:
        print("  nothing to check -- run panel_data.py first")
        return 1

    checks = build_checks()
    breakers = corruptions()
    print(f"\n  {'check':58s}{'on the data':>13s}{'when broken':>13s}")
    bad = 0
    for label, predicate in checks:
        try:
            good = predicate(rows, transcripts)
        except Exception as error:
            print(f"  {label:58s}{'ERROR':>13s}   {type(error).__name__}: {error}")
            bad += 1
            continue
        breaker = breakers.get(label)
        if breaker is None:
            caught = None
        else:
            corrupt_rows, corrupt_tr = breaker(rows, transcripts)
            try:
                caught = not predicate(corrupt_rows, corrupt_tr)
            except Exception:
                # A predicate that raises on corrupt input has still noticed the corruption.
                caught = True
        verdict = "OK" if good else "FAILS"
        catch = "no breaker" if caught is None else ("catches it" if caught else "BLIND")
        if not good or caught is False:
            bad += 1
        print(f"  {label:58s}{verdict:>13s}{catch:>13s}")

    print()
    if bad:
        print(f"  {bad} check(s) either failed on the data or cannot catch the bug they name.")
    else:
        print(
            f"  all {len(checks)} checks pass on the data, and each one fails on a deliberately\n"
            "  corrupted copy -- so a pass here is evidence rather than a tautology.\n"
            "  What this does NOT verify is the Excel syntax of the same checks in the workbook;\n"
            "  that needs the button pressed once."
        )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
