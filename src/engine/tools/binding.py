"""S3 — trigger/switch hybridisation energy.

The single number that says whether a trigger will actually open its switch. A toehold
switch is a kinetic trap: the OFF hairpin is stable, and the trigger has to be *more*
stable bound to the switch than the switch is folded on itself, or nothing happens.

The formula is already fixed by the toehold spec, and it is implemented once here so
every gate family reports the same quantity on the same scale. Two families computing
"binding energy" slightly differently produce numbers that ``engine.scoring`` will
normalise onto one axis as though they were comparable.
"""

from engine.tools.folding import FoldEngine


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
        1. ``G_complex`` — fold the two strands together. In ViennaRNA this is
           ``RNA.cofold(switch + "&" + trigger)``, which returns the energy of the
           dimer.
        2. ``G_switch`` — ``folder.mfe(switch).energy``.
        3. ``G_trigger`` — ``folder.mfe(trigger).energy``.
        4. Subtract.

    Gotchas:
        * The ``&`` separator is ViennaRNA's dimer convention. Concatenating without it
          silently folds one long single strand and gives a meaningless answer that looks
          plausible.
        * ``cofold`` energies include a duplex initiation term. That is correct here, but
          it means the value is not comparable with a hand-computed base-pairing sum.
        * Order matters for the string but not for the energy. Keep ``switch`` first so
          any structure returned alongside it is indexed the way callers expect.

    Note:
        This is the *thermodynamic* question. Whether binding is fast enough in vivo is
        kinetic and outside what folding predicts — one reason the scoring profile
        carries ``predicted_success_rate`` as a separate, model-based metric rather than
        deriving everything from energy.
    """
    raise NotImplementedError("Step 5 — cofold the complex, subtract the parts")
