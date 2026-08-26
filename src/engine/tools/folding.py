"""S1, S2, S4 — RNA folding.

**The only module that imports ViennaRNA.** Everything else asks these classes, which
buys a shared cache on the hottest operation, one place recording the tool version for
reproducibility, one place to swap the library, and a single stub point for tests.

Bodies land in Step 5 (docs/step-5-engine-plan.md 5a).
"""

from functools import cache

from engine.domain import FoldResult, StructureMatch


class FoldEngine:
    """S2 — MFE, partition function, ensemble defect, base-pair probabilities.

    Construct **once per run** and pass it down: the cache is the single biggest
    performance win available, and it only works if everyone shares one instance.
    """

    def __init__(self, temperature: float = 37.0, cache_size: int = 100_000) -> None:
        self.temperature = temperature
        self._cache_size = cache_size

    @cache  # noqa: B019 — one instance per run; see the docstring
    def mfe(self, sequence: str) -> FoldResult:
        """Minimum free energy structure. `RNA.fold`."""
        raise NotImplementedError("Step 5 — wrap RNA.fold")

    def partition(self, sequence: str) -> float:
        """Ensemble free energy. `RNA.pf`."""
        raise NotImplementedError("Step 5 — wrap RNA.pf")

    def ensemble_defect(self, sequence: str, target: str) -> float:
        """Expected number of incorrectly paired bases against a target structure."""
        raise NotImplementedError("Step 5 — wrap RNA.ensemble_defect")

    def base_pair_probabilities(self, sequence: str) -> list[list[float]]:
        """Base-pair probability matrix, for accessibility and diagnostics."""
        raise NotImplementedError("Step 5 — wrap RNA.pfl_fold / bppm")

    def suboptimal(self, sequence: str, delta: float = 2.0) -> list[FoldResult]:
        """Structures within `delta` kcal/mol of the MFE."""
        raise NotImplementedError("Step 5 — wrap RNA.subopt")

    def versions(self) -> dict[str, str]:
        """Recorded on every run. Without it, an old result is uninterpretable after
        a ViennaRNA upgrade."""
        raise NotImplementedError("Step 5 — return {'ViennaRNA': RNA.__version__}")


class FoldProfiler:
    """S1 — per-position unpaired probability in local context. `RNAplfold -W -L -u`.

    The primitive behind trigger selection: an accessible segment is one a trigger can
    actually reach.
    """

    def __init__(self, window: int = 80, max_span: int = 40, unpaired: int = 10) -> None:
        self.window = window
        self.max_span = max_span
        self.unpaired = unpaired

    def profile(self, sequence: str) -> list[float]:
        """Unpaired probability at every position."""
        raise NotImplementedError("Step 5 — wrap RNAplfold")

    def openness(self, sequence: str, start: int, end: int) -> float:
        """Mean unpaired probability across a segment — the map's `openness`."""
        raise NotImplementedError("Step 5 — mean of profile()[start:end]")


def structure_match(dot_bracket: str, target_structure: str) -> StructureMatch:
    """S4 — how far a predicted fold is from the intended one."""
    raise NotImplementedError("Step 5")
