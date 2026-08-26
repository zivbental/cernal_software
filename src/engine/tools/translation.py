"""S9 — translation initiation strength.

The point of a toehold switch is to control whether a ribosome starts translating. This
module estimates how strongly it would, given the sequence around the start codon.

**This is where the prokaryotic/eukaryotic split genuinely bites**, and it is the reason
``Host.track`` exists:

* **Prokaryotic.** A ribosome finds the start codon via the Shine-Dalgarno sequence, a
  purine-rich stretch a few nucleotides upstream that pairs with 16S rRNA. Strength
  depends on how well it complements, and on the spacing to the AUG. This is why a
  prokaryotic toehold puts the RBS in the loop: the loop is single-stranded in the OFF
  state, but the *start codon* stays sequestered in the stem, so no initiation occurs.
* **Eukaryotic.** No Shine-Dalgarno. The small subunit loads at the 5' cap and *scans*
  until it meets a start codon in good context — the Kozak consensus. So a eukaryotic
  design must worry about anything upstream that could capture the scanning ribosome
  first, which is why upstream AUGs are disqualifying rather than merely untidy.

Bodies land in Step 5.
"""

from engine.domain import Host, Track


class TranslationScorer:
    """Initiation strength for one host, dispatching on its track.

    Args:
        host: The organism. ``host.track`` selects the mechanism, and callers should use
            ``score`` rather than the track-specific methods so the dispatch happens in
            one place.
    """

    def __init__(self, host: Host) -> None:
        self.host = host
        self.track: Track = host.track

    def score(self, sequence: str, start_index: int) -> float:
        """Translation initiation rate for the start codon at ``start_index``.

        The method callers should use. Dispatches on ``self.track``.

        Args:
            sequence: The switch or construct, RNA, uppercase. Must include enough
                context — at least ~20 nt upstream of ``start_index`` for prokaryotic
                scoring, ~10 for Kozak.
            start_index: 0-indexed position of the ``A`` of the AUG being scored.

        Returns:
            A relative strength in 0.0 to 1.0. Compared *between designs*, not treated as
            an absolute rate — these models are rough, and the wet lab is the arbiter.

        Raises:
            ValueError: if ``sequence[start_index:start_index+3] != "AUG"``, which always
                means the caller computed the index wrongly.
        """
        raise NotImplementedError("Step 5 — dispatch on self.track")

    def rbs_strength(self, sequence: str, start_index: int) -> float:
        """Prokaryotic: Shine-Dalgarno complementarity and spacing.

        Args:
            sequence: Must include at least 20 nt upstream of the start codon.
            start_index: Position of the AUG.

        Returns:
            Relative strength, 0.0 to 1.0.

        Implementation (Step 5):
            Two contributions, both needed:

            * **Complementarity.** How well the upstream region pairs with the 16S rRNA
              3' end (anti-SD, ``CCUCCU`` in *E. coli*). Use ``FoldEngine`` to compute
              the hybridisation energy rather than counting matches — pairing strength is
              not linear in match count.
            * **Spacing.** The gap between the SD and the AUG has an optimum around 5 to 9
              nt, and falls off sharply either side. Model it as a penalty curve, not a
              hard window.

            The Salis RBS Calculator is the reference model if you want more fidelity;
            a two-term approximation is defensible for ranking, which is all this is used
            for.
        """
        raise NotImplementedError("Step 5")

    def kozak_match(self, sequence: str, start_index: int) -> float:
        """Eukaryotic: agreement with the Kozak consensus.

        Args:
            sequence: Must include at least 6 nt upstream and 4 downstream of the AUG.
            start_index: Position of the AUG.

        Returns:
            Match quality, 0.0 to 1.0.

        Implementation (Step 5):
            The consensus is ``gccRccAUGG``, and the two positions that dominate are the
            purine at -3 and the G at +4. Weight those heavily rather than scoring all
            positions equally — a sequence matching everywhere except -3 is a weak start
            site, and a naive position-count will call it strong.
        """
        raise NotImplementedError("Step 5")

    def ramp_is_unstructured(self, sequence: str, start_index: int) -> bool:
        """Whether the region just downstream of the AUG is open enough to translate.

        A strong initiation signal is wasted if the first few codons fold into a hairpin
        the ribosome has to melt. This check catches designs where the switch's own stem
        or the payload's opening codons obstruct the ramp.

        Args:
            sequence: The switch or construct.
            start_index: Position of the AUG.

        Returns:
            True when the downstream window is sufficiently unstructured.

        Implementation (Step 5):
            Take roughly the first 30 to 45 nt downstream, compute mean unpaired
            probability with ``FoldProfiler``, and compare against a threshold the
            scientific team sets. When this fails, ``CodonOptimizer.variants`` with a
            target of "less paired" is the natural repair — which is exactly why these
            two tools exist alongside each other.
        """
        raise NotImplementedError("Step 5")
