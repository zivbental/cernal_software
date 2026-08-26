"""S5 — off-target scanning, in both directions.

A switch that works perfectly against its intended trigger is still useless if some
other transcript in the cell opens it. This module answers *"what else in the
transcriptome looks like this sequence?"*, and it answers it **once**, so every caller
uses the same definition of "similar" and the same penalty scale.

Two biologically distinct failures, both found by the same search
(docs/engine.md §3.4):

* **Direction (a) — cross-activation.** Some non-cognate RNA resembles the trigger
  closely enough to open the switch. Consequence: the circuit fires when it should not.
  A **false positive**, and the more dangerous of the two, because a kill-switch that
  fires in the wrong cell is a safety problem rather than an inconvenience.
* **Direction (b) — sponging.** The trigger's sequence occurs elsewhere, so free trigger
  is mopped up by other transcripts and less is available to open the switch.
  Consequence: weak ON. A **false negative**.

Three callers, three questions, one index — see the class docstring.
"""

from engine.domain import Hit, OffTargetReport


class OffTargetScanner:
    """Finds near-matches of a sequence in the host transcriptome.

    Holds the index and the mismatch model. Constructing three of these with different
    settings is the failure mode this class exists to prevent: three penalty scales that
    ``engine.scoring`` then normalises onto one axis as though they were comparable,
    producing a ranking that is quietly wrong rather than obviously broken.

    Args:
        transcriptome: Gene ID to transcript sequence for the host organism. This is the
            same reference the trigger sequences came from — scanning against a different
            build than the triggers were taken from produces nonsense.
        max_mismatch: How many mismatched positions still count as a hit. RNA duplexes
            tolerate mismatches, so 0 is far too strict; 2 to 3 over a 30-mer is a
            reasonable starting point and is the scientific team's to settle.

    Who calls what:
        * ``TriggerScorer`` calls ``scan_trigger`` — is this segment sponged?
        * ``SwitchValidator`` calls ``scan_switch`` on the **binding site**, not the whole
          switch — can the wrong RNA open this?
        * ``ConfusionEvaluator`` uses neither. The per-trigger and per-switch penalties
          are already computed and stored upstream; re-scanning would be slow and would
          disagree with the numbers already recorded. It calls ``find_similar`` only for
          cross-talk between a circuit's own components.
    """

    def __init__(self, transcriptome: dict[str, str], max_mismatch: int = 2) -> None:
        self.transcriptome = transcriptome
        self.max_mismatch = max_mismatch

    def build_index(self) -> None:
        """Prepare the search structure. Call once, before any scanning.

        Why it is separate: indexing a transcriptome is seconds of work and megabytes of
        memory. Doing it lazily inside ``find_similar`` means the first call is
        mysteriously slow and the cost is invisible in a profile.

        Implementation (Step 5):
            A k-mer index is the pragmatic choice: hash every k-mer (k around 12) to the
            positions it occurs at, then for a query, look up its k-mers, gather candidate
            positions, and verify each with a full mismatch count. That is a seed-and-extend
            search, and it is what makes this tractable — comparing every query against
            every position is quadratic and far too slow at transcriptome scale.

            An off-the-shelf aligner (bowtie, BLAST) is also legitimate and probably more
            accurate. If you go that way, keep the interface below unchanged so nothing
            else has to know.
        """
        raise NotImplementedError("Step 5")

    def find_similar(self, sequence: str) -> tuple[Hit, ...]:
        """The primitive. Every method below is interpretation of these hits.

        Args:
            sequence: The query, RNA, uppercase.

        Returns:
            Every near-match found, as ``Hit(gene_id, start, mismatches, identity)``.
            ``identity`` is the fraction of matching positions, so 1.0 is exact.
            **Includes the query's own source gene** — the caller decides whether that
            self-hit counts, because it means different things in each direction.

        Implementation (Step 5):
            Seed with k-mers, verify candidates with ``sequences.hamming``, keep hits
            within ``max_mismatch``. Sort by identity descending so callers can stop early.
        """
        raise NotImplementedError("Step 5")

    def scan_trigger(self, trigger: str) -> OffTargetReport:
        """Direction (b) — is this trigger sponged by other transcripts?

        Args:
            trigger: The candidate trigger segment.

        Returns:
            ``OffTargetReport(hits, penalty)``. ``penalty`` is 0.0 for a clean trigger and
            rises with the number and quality of competing hits.

        Implementation (Step 5):
            Call ``find_similar``, **drop the self-hit** — a trigger matching its own gene
            is the intended behaviour, not an off-target — and weight the remainder. A hit
            in an abundantly expressed transcript sponges far more than one in a rare
            transcript, so weight by expression if the count matrix is available.

        Note:
            The penalty scale is arbitrary but must be *consistent*: it is normalised by
            ``engine.scoring`` against ``MetricSpec.valid_range``, so decide the range
            once, write it into the profile, and do not change one without the other.
        """
        raise NotImplementedError("Step 5")

    def scan_switch(self, binding_site: str) -> OffTargetReport:
        """Direction (a) — can non-cognate RNA cross-activate this switch?

        Args:
            binding_site: The switch's **toehold and stem region** — the part a trigger
                actually pairs with. Passing the whole switch is a common and expensive
                mistake: the payload CDS is long, shared across every design, and its
                matches tell you nothing about specificity.

        Returns:
            ``OffTargetReport(hits, penalty)``. Feeds ``SwitchDesign.binding_site_off_target``
            and, through it, the leakage estimate.

        Implementation (Step 5):
            Search for transcripts complementary to the binding site — that is, search
            with ``sequences.reverse_complement(binding_site)``, since a transcript that
            *binds* the site is complementary to it rather than identical. Getting this
            backwards is the single easiest error in this module, and it fails silently:
            you get plausible-looking hits that mean nothing.
        """
        raise NotImplementedError("Step 5")
