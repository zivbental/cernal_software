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

from html import escape

from engine.artifacts import write_artifact
from engine.contract import ArtifactRef, CandidateResult
from engine.domain import CircuitCandidate, GateDesign, PlasmidDesign
from engine.gates.tools.folding import FoldEngine


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
        FoldEngine.validate_target(design.sequence, design.dot_bracket)
        width = max(300, 8 * len(design.dot_bracket) + 40)
        stack = []
        paths = []
        for index, symbol in enumerate(design.dot_bracket):
            if symbol == "(":
                stack.append(index)
            elif symbol == ")":
                start = stack.pop()
                x1, x2 = 20 + 8 * start, 20 + 8 * index
                paths.append(
                    f"<path d='M{x1},160 Q{(x1 + x2) / 2},20 {x2},160' "
                    "fill='none' stroke='#245c88'/>"
                )
        content = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='220' "
            f"viewBox='0 0 {width} 220'><title>Intended target pairing: "
            f"{escape(design.design_id)}</title><text x='20' y='195'>"
            "Intended target pairing, not a predicted or experimentally measured fold"
            "</text>" + "".join(paths) + "</svg>"
        )
        return write_artifact(
            output_dir,
            f"structures/{design.design_id}.svg",
            content,
            kind="structure_plot",
            media_type="image/svg+xml",
        )

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
        expression = escape(circuit.expression.render())
        content = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='900' height='120'>"
            "<title>Logical specification</title><text x='20' y='40'>"
            + expression
            + "</text><text x='20' y='80'>Logical specification; "
            "physical compiler and functional evidence required</text></svg>"
        )
        return write_artifact(
            output_dir,
            f"logic/{circuit.circuit_id}.svg",
            content,
            kind="logic_graph",
            media_type="image/svg+xml",
        )


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
            * **Which engine and version produced this.** From ``JobResult.engine_version``,
              so a stored result can always be traced back to the build that made it.
            * **Tool versions and parameters.** From ``FoldEngine.versions()``. Without
              them the result is not reproducible.
            * **The caveats.** Small sample counts, circuits that fit the data suspiciously
              well, low-confidence metrics. The temptation is to lead with the best score;
              the useful report leads with what would make you doubt it.
        """
        rows = []
        for circuit in circuits:
            state = "rejected" if circuit.is_rejected else "logical specification"
            measured = (
                sum(
                    (
                        circuit.confusion.true_positive,
                        circuit.confusion.false_positive,
                        circuit.confusion.false_negative,
                        circuit.confusion.true_negative,
                    )
                )
                > 0
            )
            rows.append(
                f"<li>{escape(circuit.expression.render())}: {state}; "
                f"sample confusion {'available' if measured else 'unmeasured'}</li>"
            )
        content = (
            "<!doctype html><meta charset='utf-8'><title>CERNAL logical specification</title>"
            "<h1>Computational logical specification</h1>"
            "<p>Logical expressions do not establish a physically compiled circuit. "
            "No experimental validation or sequence-release approval is inferred.</p><ul>"
            + "".join(rows)
            + "</ul>"
        )
        return [
            write_artifact(
                output_dir, "report.html", content, kind="report", media_type="text/html"
            )
        ]

    def build_result(
        self,
        candidates: list[CandidateResult],
        warnings: list[str],
        output_dir: str,
        *,
        engine_version: str,
        profile_version: str,
    ) -> ArtifactRef:
        """Write a sequence-free computational report while release remains held."""
        parts = [
            "<!doctype html><html lang='en'><meta charset='utf-8'>",
            "<title>CERNAL computational design report</title>",
            "<h1>CERNAL computational design report</h1>",
            f"<p>Engine {escape(engine_version)}; scoring profile {escape(profile_version)}.</p>",
            "<p>Computation is complete. Experimental efficacy, functional success calibration "
            "and transcriptome off-target screening are unavailable. Sequence export remains "
            "held until release policy approval; see safety audit artifacts.</p>",
            "<p>These are independent single-input constructs. Scores are computational proxies: "
            "dynamic range is an initiation-accessibility ratio with denominator floored at 0.001; "
            "predicted success rate is an uncalibrated binding-energy sigmoid, not a probability "
            "of cellular success. Ensemble defect is normalized once and has no calibrated "
            "functional acceptance threshold. PDF and structure figures are not produced.</p>",
            "<h2>Run caveats</h2><ul>",
            *(f"<li>{escape(warning)}</li>" for warning in warnings),
            "</ul><h2>Candidates</h2>",
        ]
        for candidate in candidates:
            parts.append(f"<h3>{escape(candidate.ref)}: {escape(candidate.summary)}</h3>")
            status = (
                "Rejected"
                if candidate.is_rejected
                else "Computationally eligible, experimentally unvalidated"
            )
            rank = candidate.rank if candidate.rank is not None else "unranked"
            parts.append(f"<p>{status}; rank {rank}.</p>")
            if candidate.rejection_reason:
                parts.append(f"<p>{escape(candidate.rejection_reason)}</p>")
            parts.append("<table><tr><th>Metric</th><th>Raw</th><th>Normalized</th></tr>")
            for metric in candidate.metrics:
                raw = "unmeasured" if metric.raw_value is None else str(metric.raw_value)
                normalized = (
                    "unmeasured"
                    if metric.normalized_value is None
                    else str(metric.normalized_value)
                )
                parts.append(
                    f"<tr><td>{escape(metric.name)}</td><td>{escape(raw)}</td>"
                    f"<td>{escape(normalized)}</td></tr>"
                )
            parts.append("</table>")
        parts.append("</html>")
        return write_artifact(
            output_dir, "report.html", "\n".join(parts), kind="report", media_type="text/html"
        )
