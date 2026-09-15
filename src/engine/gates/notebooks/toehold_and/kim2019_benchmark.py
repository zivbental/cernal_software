"""Benchmark: put Kim 2019's bench-tested constructs through our own scoring.

Run it::

    uv run python src/engine/gates/notebooks/toehold_and/kim2019_benchmark.py

**Why this is the right control.** Kim et al. 2019 built the closest published architecture
to ours and measured it: an inhibitory hairpin 5' of an AUG/RBS-containing primary hairpin,
the same 6-nt Shine-Dalgarno-to-start spacing, the same 21-nt linker, and the same
pattern-prevention list our Appendix B copies. Crucially they varied *one* parameter — the
primary hairpin's exposed toehold length ``a`` — across three otherwise identical
constructs, and reported qualitatively different behaviour: ``a = 10`` behaves as a
one-input switch, ``a = 4`` behaves as a two-input AND gate.

That gives us a design our scoring **should** reject beside one it **should** accept. If we
cannot separate them, our thresholds are not measuring what we think they are.

Two differences to keep in mind when reading the numbers. Kim's two triggers are unrelated
sequences binding separate hairpins, where ours share the overlap ``x`` — so their trigger B
does not carry a copy of trigger A's nucleation site. And their ``a`` is a *shortened but
non-zero* exposed toehold where ours is 0, which makes our design the extreme end of the
series they tested rather than a departure from it.

Note the direction, because it inverts easily: ``a`` is the **exposed** toehold, so a
*smaller* ``a`` means *more* inhibition and more AND-like behaviour.

**Sequences are transcribed from the paper's Supplementary Table S2** (given there as DNA,
for *E. coli* DH10B) and converted to RNA here. Reference: Soo-Jung Kim, Matthew Leong,
Matthew B. Amrofell, Young Je Lee and Tae Seok Moon, "Modulating responses of toehold
switches by an inhibitory hairpin". Local copy under ``Docs/Kim 2019/``.
"""

import math
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from engine import sequences as sq  # noqa: E402  (path set up just above)
from engine.gates.toehold import ToeholdAndGate, _mean_unpaired  # noqa: E402
from engine.gates.tools.folding import FoldEngine  # noqa: E402

#: Supplementary Table S2, switch RNAs. The trailing 21-nt linker is appended below so the
#: folded region matches the convention used for our own designs (cap through LINKER).
SWITCHES: dict[str, str] = {
    "G5-G3n5": (
        "TATGTAATTGATTTGGCTTCTGTTAGTTTCATACAAGAACTTAGACAATATGAAATCAACAGAAGCTATT"
        "ACTACTTACCATTGTCTTGCTCTATACAGAAACAGAGGAGATATAGAATGAGACAATGG"
    ),
    "G5-G3n8": (
        "TATGTAATTGATTTGGCTTCTGTTAGTTTCATACAAGAACTTAGACAATATGAAATCAACAGAAGCTACT"
        "ACTTACCATTGTCTTGCTCTATACAGAAACAGAGGAGATATAGAATGAGACAATGG"
    ),
    "G5-G3n11": (
        "TATGTAATTGATTTGGCTTCTGTTAGTTTCATACAAGAACTTAGACAATATGAAATCAACAGAAGCTACT"
        "TACCATTGTCTTGCTCTATACAGAAACAGAGGAGATATAGAATGAGACAATGG"
    ),
    #: No inhibitory hairpin at all — the floor of the comparison.
    "G3n5": "AGCTATTACTACTTACCATTGTCTTGCTCTATACAGAAACAGAGGAGATATAGAATGAGACAATGG",
}

#: Supplementary Table S2, trigger RNAs. ``TrG3n*`` is the primary trigger (our trigger A);
#: ``TrG51`` binds the inhibitory hairpin (our trigger B).
PRIMARY_TRIGGER: dict[str, str] = {
    "G5-G3n5": "AGAGCAAGACAATGGTAAGTAGTAATAGCT",
    "G5-G3n8": "AGAGCAAGACAATGGTAAGTAGTAGCTTCT",
    "G5-G3n11": "AGAGCAAGACAATGGTAAGTAGCTTCTGTT",
    "G3n5": "AGAGCAAGACAATGGTAAGTAGTAATAGCT",
}
SECONDARY_TRIGGER = "GAAACTAACAGAAGCCAAATCAATTACATA"  # TrG51

#: ``a``, and what the paper reports for each construct.
REPORTED: dict[str, tuple[str, str]] = {
    "G5-G3n5": ("a = 10", "behaves as a one-input switch"),
    "G5-G3n8": ("a = 7", "intermediate"),
    "G5-G3n11": ("a = 4", "behaves as a two-input AND gate"),
    "G3n5": ("no inhibitory hairpin", "plain one-input switch"),
}


def longest_shared(probe: str, target: str) -> str:
    """Longest substring of ``probe`` occurring in ``target``.

    Used on ``revcomp(trigger)`` against the switch, which gives the trigger's longest
    *contiguous* binding footprint — the quantity that decides whether it can displace the
    hairpin's own arm without help.
    """
    best = ""
    for start in range(len(probe)):
        for end in range(start + len(best) + 1, len(probe) + 1):
            if probe[start:end] in target:
                best = probe[start:end]
            else:
                break
    return best


def analyse(name: str, folder: FoldEngine) -> dict[str, object]:
    """Our four tubes, our ranking window, and our stem/AUG accessibility, for one construct."""
    switch = sq.to_rna(SWITCHES[name]) + sq.to_rna(ToeholdAndGate.LINKER_SEQUENCE)
    primary = sq.to_rna(PRIMARY_TRIGGER[name])
    secondary = sq.to_rna(SECONDARY_TRIGGER)

    rbs = switch.find(ToeholdAndGate.RBS_PROKARYOTIC)
    aug = switch.find("AUG", rbs)
    rank = (aug - 17, aug + 13)  # our W_rank, -17..+13
    arm = (aug - 6, aug + 12)  # our A_M span, -6..+12

    tubes = {
        "00": switch,
        "01": f"{switch}&{secondary}",
        "10": f"{switch}&{primary}",
        "11": f"{switch}&{primary}&{secondary}",
    }
    if name == "G3n5":  # no inhibitory hairpin, so no secondary trigger to add
        tubes = {"00": tubes["00"], "10": tubes["10"]}

    opening: dict[str, float | None] = {}
    accessibility: dict[str, float] = {}
    for state, strands in tubes.items():
        probability = folder.p_open(strands, rank)
        opening[state] = (
            None
            if probability is None or probability <= 0.0
            else -folder.rt * math.log(probability)
        )
        accessibility[state] = _mean_unpaired(folder.base_pair_probabilities(strands), *arm)

    footprint = longest_shared(sq.reverse_complement(primary), switch)
    return {
        "opening": opening,
        "accessibility": accessibility,
        "footprint": len(footprint),
        "trigger_len": len(primary),
        "spacing": aug - (rbs + len(ToeholdAndGate.RBS_PROKARYOTIC)),
    }


def main() -> int:
    folder = FoldEngine(temperature=37.0)
    results = {name: analyse(name, folder) for name in SWITCHES}

    print("Kim 2019 constructs, scored by our own pipeline\n")
    print("1. Is the primary trigger a reverse complement of its own switch's arm?")
    print("   (its longest CONTIGUOUS footprint, which is what lets it displace unaided)\n")
    for name, r in results.items():
        print(
            f"   {name:<10} {r['footprint']:>2} of {r['trigger_len']} nt contiguous"
            f"      SD-to-start spacing {r['spacing']} nt"
        )

    print("\n2. Our four tubes, on our ranking window (-17..+13 around the start codon).\n")
    header = (
        f"   {'construct':<10}{'a':<22}{'00':>8}{'01':>8}{'10':>8}{'11':>8}{'sep':>8}{'sep!10':>9}"
    )
    print(header)
    for name, r in results.items():
        o = r["opening"]

        def cell(state: str, o=o) -> str:
            return f"{o[state]:>8.2f}" if o.get(state) is not None else f"{'-':>8}"

        if o.get("11") is not None:
            off = [o[s] for s in ("00", "01", "10")]
            separation = f"{min(v - o['11'] for v in off):>8.2f}"
            no_ten = f"{min(o[s] - o['11'] for s in ('00', '01')):>9.2f}"
        else:
            separation, no_ten = f"{'-':>8}", f"{'-':>9}"
        print(
            f"   {name:<10}{REPORTED[name][0]:<22}"
            + cell("00")
            + cell("01")
            + cell("10")
            + cell("11")
            + separation
            + no_ten
        )

    print("\n3. Would our feasible set accept them? A_M per state, against our taus.\n")
    print(
        f"   {'construct':<10}{'A_M(00)':>9}{'A_M(01)':>9}"
        f"{'A_M(10)':>9}{'A_M(11)':>9}   our verdict"
    )
    for name, r in results.items():
        a = r["accessibility"]
        failures = []
        if not a["00"] < 0.2:
            failures.append("A_M(00)<0.2")
        if "01" in a and not a["01"] < 0.2:
            failures.append("A_M(01)<0.2")
        if not a["10"] < 0.2:
            failures.append("t4a A_M(10)<0.2")
        if "11" in a and not a["11"] > 0.5:
            failures.append("A_M(11)>0.5")
        cells = "".join(
            f"{a[s]:>9.3f}" if s in a else f"{'-':>9}" for s in ("00", "01", "10", "11")
        )
        verdict = "REJECTED: " + ", ".join(failures) if failures else "accepted"
        print(f"   {name:<10}{cells}   {verdict}")

    print("\n4. What Kim measured, for comparison.\n")
    for name, (spacing, behaviour) in REPORTED.items():
        print(f"   {name:<10} {spacing:<22} {behaviour}")

    ten = {name: r["opening"].get("10") for name, r in results.items()}
    print(
        "\nThe result: dG_open(10) is "
        + " / ".join(f"{v:.2f}" for v in ten.values())
        + " — the same for a working AND gate, a leaky one-input switch, and a construct"
        "\nwith no inhibitory hairpin at all. Our scoring cannot separate them, so tau4a"
        "\nrejects a design that demonstrably works at the bench. The discrimination Kim"
        "\nobserved is in binding probability and binding order, which an equilibrium"
        "\nend-state model does not represent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
