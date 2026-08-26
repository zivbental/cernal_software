"""Stage 6 — the compiler's output.

S14. The pipeline map puts it well: this stage assembles "the evidence a user needs in
order to decide whether to order a plasmid".

That framing is the design brief. The output is not a score — it is an argument, with the
uncertainty left in. A researcher about to spend money and weeks on synthesis needs to
see the confusion table, the separation margin, the flags and the caveats, not a
confident number.

Everything here reads; nothing computes science. If a figure needs a value that was not
already recorded, the value belongs upstream.
"""

from engine.contract import ArtifactRef
from engine.domain import CircuitCandidate, GateDesign, PlasmidDesign


class StructureRenderer:
    """Figures for structures and circuits.

    Separate from ``ReportBuilder`` because these are also useful on their own — the
    results screen may want a structure image, and a lab notebook may want one without
    the surrounding report.
    """

    def render_structure(self, design: GateDesign, output_dir: str) -> ArtifactRef:
        """Draw a switch's predicted secondary structure.

        Args:
            design: The switch, carrying its ``dot_bracket``.
            output_dir: Where to write. The returned path is **relative** to it, so the
                Platform can relocate the directory without rewriting references.

        Returns:
            ``ArtifactRef`` with ``kind="structure_plot"``, its media type and checksum.

        Implementation (Step 5):
            ViennaRNA ships ``RNA.svg_rna_plot``, which is the least effort and produces
            a conventional-looking diagram. Colour the toehold, stem and loop distinctly
            — an undifferentiated hairpin tells a reader very little. SVG rather than
            PNG: it scales into the PDF and stays small.
        """
        raise NotImplementedError("Step 5")

    def render_circuit(self, circuit: CircuitCandidate, output_dir: str) -> ArtifactRef:
        """Draw a circuit's logic diagram.

        Args:
            circuit: Carrying its ``logic_graph``.
            output_dir: Destination directory.

        Returns:
            ``ArtifactRef`` with ``kind="logic_graph"``.

        Note:
            The frontend already draws its own logic diagram from ``logic_graph``. This
            exists for the **PDF**, which has no JavaScript. Draw from the same
            ``LogicGraph`` so the two agree — a report that disagrees with the screen is
            worse than no report.
        """
        raise NotImplementedError("Step 5")


class ReportBuilder:
    """Assembles every artefact a run produces, including the PDF.

    Args:
        renderer: Produces the figures the report embeds.
    """

    def __init__(self, renderer: StructureRenderer) -> None:
        self.renderer = renderer

    def build(
        self,
        circuits: list[CircuitCandidate],
        plasmids: list[PlasmidDesign],
        output_dir: str,
    ) -> list[ArtifactRef]:
        """Write every artefact and return references to them.

        Args:
            circuits: Ranked circuits, including rejected ones with their reasons.
            plasmids: The constructs built from the top circuits.
            output_dir: Where to write. Paths returned are relative to it.

        Returns:
            ``ArtifactRef`` list. The Platform verifies each checksum on import and
            serves the files through an authorised view, so ``kind`` and ``media_type``
            must be accurate — they drive how the results screen labels each download.

        What to produce (Step 5):
            * **FASTA** per plasmid — ``kind="sequence_fasta"``. The minimum a synthesis
              order needs.
            * **GenBank** per plasmid — ``kind="genbank"``. FASTA plus feature
              annotations, so the researcher can open it in SnapGene or Benchling and see
              the promoter, switch and payload marked. This is what people actually want.
            * **Candidate table** as CSV — ``kind="design_table"``. Every circuit with its
              scores and metrics, including rejected ones and why.
            * **Structure and circuit figures** — one per top candidate, not per
              candidate. Two hundred SVGs help nobody.
            * **The PDF report** — ``kind="report"``.

        The PDF, per the pipeline map:
            * A read-me explaining what CERNAL did and what the numbers mean.
            * An abstract of the designed circuits, for someone deciding what to order:
              the top few, their sequences, their confusion tables, their flags.
            * Diagrams.
            * Legal and safety notes.

        What the report must say plainly:
            * **Which engine produced this.** If ``MockEngine``, say so loudly — simulated
              results must never be mistaken for predictions.
            * **Tool versions and parameters.** From ``FoldEngine.versions()``. Without
              them the result is not reproducible.
            * **The caveats.** Small sample counts, circuits that fit the data suspiciously
              well, low-confidence metrics. The temptation is to lead with the best score;
              the useful report leads with what would make you doubt it.
        """
        raise NotImplementedError("Step 5")
