"""S1 — RNAplfold local opening probabilities for trigger selection.

The wrapper follows the benchmark protocol used by ``zivbental/dna_rna_availability``:
ViennaRNA 2.7.2-compatible RNAplfold defaults at 37 °C, W=min(n, 200),
L=min(n, 150), and u=min(n, 20).  The returned pU table is indexed by the
1-based *interval end* and interval length despite the Python docstring describing the
row as an interval start; explicit coordinate tests protect this convention.
"""

from functools import cache

try:
    import RNA as _RNA
except ImportError:  # pragma: no cover - exercised through explicit dependency injection
    _RNA = None

_DEFAULT_RNA = object()


class FoldProfiler:
    """Profile marginal and joint local opening probabilities in transcript context.

    ``profile`` returns one-base marginal pU values. ``joint_probability`` returns the
    RNAplfold joint probability that every nucleotide in one contiguous interval is
    unpaired; it is not a product or average of marginal probabilities.

    Passing ``rna_module=None`` represents an unavailable optional ViennaRNA runtime.
    That state is distinguishable through ``available``. Any error from an available
    ViennaRNA implementation propagates unchanged (fail closed).
    """

    DEFAULT_WINDOW = 200
    DEFAULT_MAX_SPAN = 150
    DEFAULT_UNPAIRED = 20
    TEMPERATURE_CELSIUS = 37.0

    def __init__(
        self,
        window: int = DEFAULT_WINDOW,
        max_span: int = DEFAULT_MAX_SPAN,
        unpaired: int = DEFAULT_UNPAIRED,
        *,
        rna_module=_DEFAULT_RNA,
    ) -> None:
        self.window = window
        self.max_span = max_span
        self.unpaired = unpaired
        self._rna = _RNA if rna_module is _DEFAULT_RNA else rna_module

    @property
    def available(self) -> bool:
        """Whether ViennaRNA can perform the requested calculation."""
        return self._rna is not None

    def _parameters(self, sequence: str) -> tuple[int, int, int]:
        n = len(sequence)
        window = min(n, self.window)
        return window, min(n, self.max_span, window), min(n, self.unpaired)

    def provenance(self, sequence: str) -> dict[str, str | int | float | None]:
        """Exact RNAplfold implementation and clamped parameters for ``sequence``."""
        window, max_span, unpaired = self._parameters(sequence)
        return {
            "tool": "RNAplfold",
            "viennarna_version": getattr(self._rna, "__version__", None),
            "window": window,
            "max_span": max_span,
            "unpaired": unpaired,
            "temperature_celsius": self.TEMPERATURE_CELSIUS,
        }

    def profile(self, sequence: str) -> list[float]:
        """Return one marginal unpaired probability per transcript position."""
        matrix = self._matrix(sequence)
        return [matrix[end][1] for end in range(1, len(sequence) + 1)]

    def joint_probability(self, sequence: str, start: int, end: int) -> float:
        """Return joint pU for ``sequence[start:end]`` using 0-based half-open coordinates."""
        if not 0 <= start < end <= len(sequence):
            raise ValueError("RNAplfold interval must satisfy 0 <= start < end <= sequence length")
        length = end - start
        _, _, unpaired = self._parameters(sequence)
        if length > unpaired:
            raise ValueError(
                f"RNAplfold interval length {length} exceeds configured/clamped u={unpaired}."
            )
        # ViennaRNA's matrix has placeholder row/column zero. Row ``end`` is the
        # 1-based inclusive interval end corresponding to our 0-based exclusive end.
        return float(self._matrix(sequence)[end][length])

    def openness(self, sequence: str, start: int, end: int) -> float:
        """Mean one-base marginal pU over a 0-based half-open interval."""
        segment = self.profile(sequence)[start:end]
        return sum(segment) / len(segment) if segment else 0.0

    @cache  # noqa: B019 - one profiler instance per run, matching FoldEngine
    def _matrix(self, sequence: str):
        if not self.available:
            raise RuntimeError(
                "ViennaRNA is unavailable; RNAplfold probabilities were not computed."
            )
        if not sequence:
            return ((0.0,),)
        current_temperature = float(self._rna.cvar.temperature)
        if current_temperature != self.TEMPERATURE_CELSIUS:
            raise RuntimeError(
                "RNAplfold requires ViennaRNA's default 37 °C model; global temperature is "
                f"{current_temperature:g} °C."
            )
        window, max_span, unpaired = self._parameters(sequence)
        return self._rna.pfl_fold_up(sequence, unpaired, window, max_span)
