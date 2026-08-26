"""S8 — codon usage and synonymous rewriting.

Two jobs, both about the fact that a switch is fused to a protein-coding sequence and
the fusion has to work as both RNA structure and protein.

**Rewriting.** The genetic code is redundant: most amino acids have several codons. That
redundancy is design freedom — a linker or the start of a CDS can be rewritten to change
its folding without changing the protein at all. A toehold whose stem is disrupted by the
payload's first few codons can often be fixed this way rather than by redesigning the
switch.

**Scoring.** Not all synonymous codons are equal in a given host. A CDS full of codons
*E. coli* rarely uses translates slowly and expresses poorly, however good the switch is.

Bodies land in Step 5.
"""

from engine.domain import Host


class CodonOptimizer:
    """Synonymous-codon search and translation scoring for one host.

    Holds the host's usage table, so every caller scores against the same organism.
    Constructing one per call site invites two stages disagreeing about what "good codon
    usage" means.

    Args:
        host: The organism. Determines which usage table applies — *E. coli*, yeast and
            human have substantially different preferences.
        usage_table: Codon to relative frequency, normally 0.0 to 1.0 within each amino
            acid's synonymous family. When omitted, Step 5 should load the bundled table
            for ``host`` (map input 5, "Organisms' codon-usage table").

    Note:
        Frequencies are **within a synonymous family**, not across all 64 codons. A codon
        at 0.9 is used 90% of the time for *its amino acid*, not 90% of the time overall.
        Mixing those two conventions produces a scoring function that looks reasonable
        and ranks nonsense highly.
    """

    def __init__(self, host: Host, usage_table: dict[str, float] | None = None) -> None:
        self.host = host
        self.usage_table = usage_table or {}

    def variants(self, cds: str, target_pairing: str | None = None) -> list[str]:
        """Synonymous rewrites of a coding sequence: same protein, different bases.

        Args:
            cds: The coding sequence to rewrite. Must be a whole number of codons and
                in frame — this rewrites codon by codon and a frame error silently
                produces a different protein.
            target_pairing: Optional dot-bracket structure the rewrite should move
                *towards*. Supplied when the caller is trying to make a region pair (to
                extend a stem) or stop pairing (to free an RBS).

        Returns:
            Candidate sequences, all translating to the same protein as ``cds``, best
            first. Includes the input unchanged when it is already good.

        Implementation (Step 5):
            The full space is the product of every position's synonymous options and is
            astronomically large — a 100-codon CDS has more variants than there are
            atoms nearby. Do not enumerate it. Options, in increasing effort:

            * Rewrite only the first N codons, which is where the switch's structure
              actually reaches. Usually enough.
            * Greedy: change one codon at a time, keep changes that improve the objective.
            * Simulated annealing over the same move set when greedy plateaus.

            Score each candidate with ``FoldEngine`` when ``target_pairing`` is given,
            and by ``translation_score`` otherwise. Cap the returned list — the caller
            will fold every one of them, and folding is the expensive part.

        Gotcha:
            Rewriting can introduce a restriction site or a long homopolymer that was not
            there before. Every variant must be screened with ``MotifScreener`` before it
            is offered, or the plasmid stage rejects it much later at much greater cost.
        """
        raise NotImplementedError("Step 5")

    def translation_score(self, cds: str) -> float:
        """How well a sequence's codons suit the host.

        Args:
            cds: The coding sequence. In frame, whole codons.

        Returns:
            A score in 0.0 to 1.0 where higher means better adapted. Stored as
            ``SwitchDesign.translation_score`` and fed into the final switch score.

        Implementation (Step 5):
            The Codon Adaptation Index is the standard choice: the geometric mean of each
            codon's relative adaptiveness — its frequency divided by the most frequent
            codon for the same amino acid. Geometric rather than arithmetic, so a single
            catastrophic codon drags the whole score down rather than being averaged away.

            Skip stop codons, and decide explicitly what to do about Met and Trp, which
            have exactly one codon each and therefore no meaningful adaptiveness. The
            usual answer is to exclude them.

        Note:
            CAI predicts expression *level*, not whether the switch works. A design can
            score 0.95 here and still be dark because its stem never opens — which is
            why this is one weighted metric among nine rather than a gate.
        """
        raise NotImplementedError("Step 5 — codon adaptation index or equivalent")
