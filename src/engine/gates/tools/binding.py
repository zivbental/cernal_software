"""S3 — trigger/switch hybridisation energy.

The single number that says whether a trigger will actually open its switch. A toehold
switch is a kinetic trap: the OFF hairpin is stable, and the trigger has to be *more*
stable bound to the switch than the switch is folded on itself, or nothing happens.

The formula is already fixed by the toehold spec, and it is implemented once here so
every gate family reports the same quantity on the same scale. Two families computing
"binding energy" slightly differently produce numbers that ``engine.scoring`` will
normalise onto one axis as though they were comparable.
"""

import math
from collections.abc import Sequence

from engine.gates.tools.folding import FoldEngine

#: Every pairing the design may rely on. **G:U wobbles count** — a duplex scored on
#: Watson-Crick pairs alone reads as broken while still holding perfectly well, which on
#: this project produced a "knockout" retaining a fully wobble-paired 8-nt run.
_PAIRABLE = frozenset({("A", "U"), ("U", "A"), ("G", "C"), ("C", "G"), ("G", "U"), ("U", "G")})


def can_pair(first: str, second: str) -> bool:
    """Whether two bases can hydrogen-bond, **G:U wobbles included**.

    See ``_PAIRABLE``: excluding wobbles makes a duplex read as broken while it still
    holds, which is how a negative control stops being one.
    """
    return (first, second) in _PAIRABLE


def alignment_pairs(first: str, second: str) -> list[bool]:
    """Which positions can pair when the two strands are held antiparallel.

    ``first[i]`` faces ``second[n-1-i]``, the 5'→3'/3'→5' convention both strands are
    written in. Returns one flag per position of ``first``.

    Raises:
        ValueError: if the strands are different lengths. A fixed alignment between
            unequal strands is undefined, and silently truncating would score a shorter
            duplex than the design describes.
    """
    if len(first) != len(second):
        raise ValueError(f"fixed alignment needs equal lengths, got {len(first)} and {len(second)}")
    n = len(first)
    return [can_pair(first[i], second[n - 1 - i]) for i in range(n)]


def longest_complementary_run(first: str, second: str) -> int:
    """Longest unbroken stretch the two strands can pair over, in this alignment.

    The question behind "can this trigger still nucleate?" — nucleation needs a few
    contiguous pairs, and scattered ones do not substitute. It is also what decides
    whether a negative control is really disabled.

    **G:U wobbles count**, via ``can_pair``. Scored on Watson-Crick pairs alone, a
    synonymous-substitution knockout on this project read as disabled while retaining a
    fully wobble-paired 8-nt run — a negative control that was not one, and one that
    could not be recognised as such from the experimental result.

    Shorter strand wins: the alignment is taken over ``min(len(first), len(second))``
    positions, so this tolerates the unequal lengths ``alignment_pairs`` rejects.
    """
    n = min(len(first), len(second))
    best = run = 0
    for i in range(n):
        run = run + 1 if can_pair(first[i], second[n - 1 - i]) else 0
        best = max(best, run)
    return best


def fixed_alignment_energy(first: str, second: str, folder: FoldEngine) -> float | None:
    """Free energy of two strands held in the alignment the **design** imposes.

    Distinct from ``hybridization_energy`` above, and the distinction matters. That one
    folds the strands freely and lets ViennaRNA choose the best structure — the right
    question for "will this trigger open this switch?". This one forces ``first[i]``
    against ``second[n-1-i]`` and leaves mismatched positions unpaired, priced as internal
    loops — the right question for "how strong is the stem I am building here?", where the
    register is fixed by the architecture and the mismatches are the design decision.

    Args:
        first: RNA, uppercase, 5'→3'.
        second: RNA, uppercase, 5'→3', same length as ``first``. It is reversed here, so
            pass both as they read on the molecule rather than pre-reversing one.
        folder: The run's shared ``FoldEngine`` — injected, so this shares its cache and
            its temperature rather than quietly folding at a different one.

    Returns:
        Free energy in kcal/mol, **more negative meaning a stronger duplex**; ``0.0`` when
        the alignment permits no pair at all, which is a real answer rather than a failure;
        or ``None`` if the model cannot evaluate the forced structure.

    Note:
        ``None`` rather than a sentinel is the whole point. ViennaRNA reports an
        unevaluable structure by *returning* ``1e5``, and two such values subtracted give
        ``0.00`` — which passes a ``>= 0`` gate. That is not hypothetical: it is why every
        stem energy in the upstream A0 scripts reads as a pass.
    """
    paired = alignment_pairs(first, second)
    if not any(paired):
        return 0.0
    n = len(first)
    left = ["."] * n
    right = ["."] * n
    for i, is_paired in enumerate(paired):
        if is_paired:
            left[i] = "("
            right[n - 1 - i] = ")"
    return folder.structure_energy(f"{first}&{second}", "".join(left + right))


def hybridization_energy(switch: str, trigger: str, folder: FoldEngine) -> float:
    """Free energy released when a trigger binds its switch.

    dG_bind = G_complex - (G_switch + G_trigger)

    Read it as: how much better off the two strands are together than apart. The switch
    and trigger each pay a cost to unfold their own structure, and gain from the new
    duplex; this is the net.

    Args:
        switch: The full switch sequence, RNA, uppercase.
        trigger: The trigger sequence it was designed against.
        folder: The run's shared ``FoldEngine``. Passed in rather than constructed so
            the cache is shared and the temperature is consistent.

    Returns:
        Free energy in kcal/mol. **More negative means stronger binding**, so a usable
        design is well below zero. A value near zero means the trigger will not reliably
        displace the stem, and the switch stays dark.

    Implementation (Step 5):
        1. ``G_complex`` — fold the two strands together as a dimer, through the shared
           engine: ``folder.mfe(f"{switch}&{trigger}").energy``. Going through
           ``folder`` rather than calling ``RNA.cofold`` directly is what gives this the
           shared cache and consistent temperature ``folder`` was passed in for.
        2. ``G_switch`` — ``folder.mfe(switch).energy``.
        3. ``G_trigger`` — ``folder.mfe(trigger).energy``.
        4. Subtract.

    Gotchas:
        * The ``&`` separator is ViennaRNA's dimer convention. Concatenating without it
          silently folds one long single strand and gives a meaningless answer that looks
          plausible.
        * The dimer energy includes a duplex initiation term. That is correct here, but
          it means the value is not comparable with a hand-computed base-pairing sum.
        * Order matters for the string but not for the energy. Keep ``switch`` first so
          any structure returned alongside it is indexed the way callers expect.

    Note:
        This is the *thermodynamic* question. Whether binding is fast enough in vivo is
        kinetic and outside what folding predicts — one reason the scoring profile
        carries ``predicted_success_rate`` as a separate, model-based metric rather than
        deriving everything from energy.
    """
    g_complex = folder.mfe(f"{switch}&{trigger}").energy
    g_switch = folder.mfe(switch).energy
    g_trigger = folder.mfe(trigger).energy
    return g_complex - (g_switch + g_trigger)


#: Reference point for ``binding_energy_factor``: the ΔG_bind at which a design is
#: judged an even bet. Literature-reasonable for an RNA-RNA duplex of the lengths these
#: chemistries build, and fixed rather than calibrated against the run's own candidate
#: pool on purpose — a pool-relative reference makes a design's score depend on which
#: other designs happened to be in its batch (CLAUDE.md §3).
DG_REFERENCE_KCAL = -15.0

#: How sharply confidence changes around ``DG_REFERENCE_KCAL``, in kcal/mol. Larger is
#: a gentler slope.
DG_STEEPNESS = 2.0


def binding_energy_factor(
    binding_dg: float,
    *,
    reference_kcal: float = DG_REFERENCE_KCAL,
    steepness: float = DG_STEEPNESS,
) -> float:
    """Map ΔG_bind (kcal/mol, more negative is stronger) onto a 0-1 confidence.

    This is ``predicted_success_rate``'s model: a logistic curve through
    ``reference_kcal``, where a duplex exactly that stable scores 0.5, a much stronger
    one approaches 1.0 and a much weaker one approaches 0.0.

    It lives here rather than on one family because every chemistry that reports
    ``predicted_success_rate`` must report it on the *same* scale. Two families each
    with their own sigmoid produce numbers ``engine.scoring`` normalises onto one axis
    as though they were comparable — the same failure this module's own docstring
    describes for binding energy itself.

    Args:
        binding_dg: From ``hybridization_energy``. kcal/mol, negative for a duplex that
            forms.
        reference_kcal: The 0.5 point. A family with a well-founded reason to sit
            elsewhere passes its own, and says why.
        steepness: kcal/mol per unit of logit.

    Returns:
        A confidence on 0-1, higher better — the direction ``predicted_success_rate``
        declares in ``engine.scoring.profiles``.
    """
    x = (binding_dg - reference_kcal) / steepness
    x = max(-50.0, min(50.0, x))  # clamp: math.exp overflows well before this
    return 1.0 / (1.0 + math.exp(x))


def weakest_binding_confidence(
    switch: str, triggers: Sequence[str], folder: FoldEngine
) -> float | None:
    """``predicted_success_rate`` over every input a design needs.

    Runs ``hybridization_energy`` for each trigger against the switch and returns the
    *lowest* confidence ``binding_energy_factor`` gives any of them. The weakest input
    governs: an AND gate whose second trigger barely binds does not work because the
    first one binds beautifully.

    Args:
        switch: The full switch sequence, RNA, uppercase.
        triggers: Each trigger sequence the design is designed against. A single-input
            family passes one.
        folder: The run's shared ``FoldEngine`` — one instance, so every energy here is
            computed at one temperature and served from one cache.

    Returns:
        A confidence on 0-1, or ``None`` when there are no triggers to bind, which is
        not a design scoring zero but a design there is nothing to say about.
    """
    if not triggers:
        return None
    return min(binding_energy_factor(hybridization_energy(switch, t, folder)) for t in triggers)
