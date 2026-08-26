"""S3 — trigger/switch hybridisation.

The formula is already specified in the toehold spec; implemented once, here, so every
gate family reports the same number.
"""

from engine.tools.folding import FoldEngine


def hybridization_energy(switch: str, trigger: str, folder: FoldEngine) -> float:
    """dG_bind = G_complex - (G_switch + G_trigger).

    More negative means the trigger binds the switch more readily.
    """
    raise NotImplementedError("Step 5 — RNA.cofold the complex, subtract the parts")
