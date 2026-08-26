"""S9 — translation initiation strength.

Prokaryotic and eukaryotic hosts initiate translation differently, so this is the tool
where the track distinction genuinely bites.
"""

from engine.domain import Host, Track


class TranslationScorer:
    """RBS strength (prokaryotic) or Kozak match (eukaryotic), plus the ramp check."""

    def __init__(self, host: Host) -> None:
        self.host = host
        self.track: Track = host.track

    def score(self, sequence: str, start_index: int) -> float:
        """Translation initiation rate for the AUG at `start_index`."""
        raise NotImplementedError("Step 5")

    def rbs_strength(self, sequence: str, start_index: int) -> float:
        """Prokaryotic: Shine-Dalgarno complementarity and spacing."""
        raise NotImplementedError("Step 5")

    def kozak_match(self, sequence: str, start_index: int) -> float:
        """Eukaryotic: agreement with the Kozak consensus."""
        raise NotImplementedError("Step 5")

    def ramp_is_unstructured(self, sequence: str, start_index: int) -> bool:
        """Whether the region downstream of the AUG is free enough for the ribosome."""
        raise NotImplementedError("Step 5")
