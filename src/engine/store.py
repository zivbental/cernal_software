"""S11, S13 — provenance and pruning.

`CandidateStore` is a **recorder, not a bus**. Stages pass typed records to each other
directly; the store writes an inspectable snapshot of what passed through, so a run stays
auditable and re-runnable without forcing every stage to serialise
(docs/engine-classes.md §6).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from engine.contract import ArtifactRef


class CandidateStore:
    """Stable IDs, provenance, and a CSV snapshot per stage."""

    def __init__(self, output_dir: str, run_id: str) -> None:
        self.output_dir = output_dir
        self.run_id = run_id
        self._counters: dict[str, int] = {}

    def mint_id(self, kind: str) -> str:
        """Allocate a stable, readable identifier.

        Args:
            kind: A short prefix naming the record type — ``gene``, ``trig``, ``sw``,
                ``circ``, ``plasmid``.

        Returns:
            ``f"{kind}-{n:06d}"``, e.g. ``trig-000123``.

        Why sequential rather than a UUID:
            * **Snapshots sort meaningfully.** Opening stage 2's CSV in a spreadsheet and
              seeing ``trig-000001`` first is worth a great deal when debugging.
            * **A re-run with the same input produces the same IDs**, so two runs can be
              diffed. UUIDs would differ every time and make that impossible.
            * They are readable aloud, which matters when a wet-lab colleague is asking
              about a specific candidate.

        Not thread-safe, deliberately: the pipeline mints IDs on the parent process and
        parallelises only the evaluation step, which does not mint.
        """
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return f"{kind}-{self._counters[kind]:06d}"

    def snapshot(self, stage: str, records: Sequence[Any]) -> ArtifactRef:
        """Write what a stage produced, as an inspectable CSV.

        This is the store's real job. The scientific team can open stage 2's output in
        Excel and see exactly which windows scored well and why — which is worth far more
        during development than any log line.

        Args:
            stage: The stage's name. Becomes the filename, so keep it stable across runs.
            records: The frozen dataclasses that stage produced.

        Returns:
            ``ArtifactRef`` for the written file, so the Platform can offer it as a
            download and verify its checksum on import.

        Implementation (Step 5):
            Derive the columns from ``dataclasses.fields(type(records[0]))`` rather than
            maintaining a schema per record type. A new field then appears in the
            snapshot automatically, and nobody has to remember to update a writer.

            Flatten nested dataclasses one level with a dotted prefix
            (``trigger_set.arity``) and serialise dicts as JSON in a single cell. Deeper
            nesting than that is a sign the record wants splitting.

            Write **incrementally** where the caller is streaming: taking a ``Sequence``
            forces materialisation, which is the one thing the streaming design exists to
            avoid. Consider an ``open_snapshot(stage)`` context manager returning a writer
            when this becomes a problem at scale.

        Note:
            Empty ``records`` should still write a header-only file, not skip. A missing
            file reads as "this stage did not run"; an empty one reads as "this stage
            produced nothing", and those are very different diagnoses.
        """
        raise NotImplementedError("Step 5")

    def load_snapshot(self, stage: str) -> list[dict]:
        """Read a snapshot back, to re-run one stage without re-running the pipeline.

        The development loop this enables: run once, then iterate on stage 4 against
        stage 3's saved output instead of re-folding thousands of switches every time.
        On a ten-minute pipeline that is the difference between a usable feedback cycle
        and an unusable one.

        Args:
            stage: The stage whose output to load.

        Returns:
            Rows as dicts of strings. **Not reconstructed dataclasses** — CSV has no
            types, and silently guessing them is how a float becomes a string three
            stages later. The caller converts, deliberately.

        Raises:
            FileNotFoundError: if that stage has no snapshot, which usually means it was
                never run rather than that it produced nothing.
        """
        raise NotImplementedError("Step 5")


@dataclass(frozen=True, slots=True)
class Objective:
    """One axis of a Pareto comparison."""

    field: str
    maximize: bool = True


class ParetoFilter:
    """S13 — keep only the non-dominated candidates.

    A circuit scoring 0.9 with twelve components does not dominate one scoring 0.85 with
    four: neither is better on both axes, and the researcher should see both. Ranking on
    a single blended score hides that trade-off, which is why this is separate from
    `engine.scoring`.
    """

    def __init__(self, objectives: Sequence[Objective]) -> None:
        self.objectives = tuple(objectives)

    def frontier(self, records: Sequence[Any]) -> list[Any]:
        """Keep only the candidates nothing else beats on every axis.

        Args:
            records: Candidates to filter. Each must expose every field named in
                ``self.objectives``.

        Returns:
            The non-dominated set, in the input's order. Typically a small fraction of
            the input, and it is the set worth showing a researcher: every member is the
            best available at some trade-off, and no member is simply worse than another.

        Implementation (Step 5):
            A record **dominates** another when it is at least as good on every objective
            and strictly better on one. Keep every record that nothing dominates.

            The naive comparison is quadratic, which is fine here — this runs on hundreds
            of circuits, not hundreds of thousands. Do the simple thing.

        Example:
            Score 0.90 with 12 components and score 0.85 with 4: **neither dominates**.
            One is more accurate, the other far easier to build, and the researcher should
            see both. A single blended score would hide that, which is precisely why this
            is separate from ``engine.scoring``.
        """
        raise NotImplementedError("Step 5")

    def top_k(self, records: Sequence[Any], k: int, key: str = "score") -> list[Any]:
        """Cap how much passes from one stage to the next.

        The blunt instrument that keeps the pipeline's cost bounded. Stage 2 can produce
        tens of thousands of trigger candidates and stage 3 will fold every one it is
        given, so the budget has to be enforced somewhere — here, explicitly, rather than
        by hoping a threshold happens to cut the right amount.

        Args:
            records: Candidates, in any order.
            k: How many to keep.
            key: The attribute to sort by, descending.

        Returns:
            The best ``k``, or all of them when there are fewer.

        Why top-K rather than a threshold:
            A threshold lets one unusually good gene flood the pool and starve the rest of
            the budget. Applying top-K **per group** — per gene at stage 2, per trigger
            set at stage 3 — keeps the search broad rather than deep, which is usually the
            better science as well as the more predictable runtime.

        Note:
            Break ties on a stable secondary key, not on input order. Otherwise a re-run
            can return a different set for identical input, and the determinism the
            contract promises quietly stops holding.
        """
        raise NotImplementedError("Step 5")
