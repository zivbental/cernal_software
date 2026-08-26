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
        """A stable, readable identifier: ``trig-000123``.

        Sequential rather than random so that snapshots sort meaningfully and a
        re-run with the same input produces the same IDs.
        """
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return f"{kind}-{self._counters[kind]:06d}"

    def snapshot(self, stage: str, records: Sequence[Any]) -> ArtifactRef:
        """Write what a stage produced, as CSV, for inspection and provenance.

        Step 5: derive columns from the record's dataclass fields, so a new field
        appears in the snapshot without anyone maintaining a schema.
        """
        raise NotImplementedError("Step 5")

    def load_snapshot(self, stage: str) -> list[dict]:
        """Read a snapshot back, so one stage can be re-run while it is being developed."""
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
        """The non-dominated set."""
        raise NotImplementedError("Step 5")

    def top_k(self, records: Sequence[Any], k: int, key: str = "score") -> list[Any]:
        """Stage budget enforcement — cap what passes to the next stage."""
        raise NotImplementedError("Step 5")
