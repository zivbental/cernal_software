"""S1 — RNAplfold local opening probabilities for trigger selection.

The default model follows the benchmark protocol used by
``zivbental/dna_rna_availability``: ViennaRNA 2.7.2-compatible RNAplfold defaults at
37 °C, W=min(n, 200), L=min(n, 150), and u=min(n, 20). An explicit immutable model
is shared with design-side folding. The returned pU table is indexed by the
1-based *interval end* and interval length despite the Python docstring describing the
row as an interval start; explicit coordinate tests protect this convention.
"""

from functools import lru_cache

from engine.domain import FoldingConfig


def _load_rna():
    """Load ViennaRNA, distinguishing true absence from a broken installation."""
    try:
        import RNA
    except ModuleNotFoundError as exc:
        if exc.name == "RNA":
            return None
        raise
    return RNA


_RNA = _load_rna()
if _RNA is not None:
    from engine.gates.tools.folding import configured_compound, folding_provenance

_DEFAULT_RNA = object()


class FoldProfiler:
    """Profile marginal and joint local opening probabilities in transcript context.

    ``profile`` returns one-base marginal pU values. ``joint_probability`` returns the
    RNAplfold joint probability that every nucleotide in one contiguous interval is
    unpaired; it is not a product or average of marginal probabilities.

    Passing ``rna_module=None`` represents a confirmed missing ViennaRNA runtime.
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
        config: FoldingConfig | None = None,
        rna_module=_DEFAULT_RNA,
    ) -> None:
        for name, value in (("window", window), ("max_span", max_span), ("unpaired", unpaired)):
            if type(value) is not int or value < 1:
                raise ValueError(f"RNAplfold {name} must be a positive integer.")
        self._window = window
        self._max_span = max_span
        self._unpaired = unpaired
        self._config = config if config is not None else FoldingConfig()
        if not isinstance(self._config, FoldingConfig):
            raise ValueError("config must be a FoldingConfig.")
        self._rna = _RNA if rna_module is _DEFAULT_RNA else rna_module
        self._matrix = lru_cache(maxsize=2)(self._matrix)

    @property
    def window(self) -> int:
        return self._window

    @property
    def max_span(self) -> int:
        return self._max_span

    @property
    def unpaired(self) -> int:
        return self._unpaired

    @property
    def config(self) -> FoldingConfig:
        """Immutable model used by every cached local probability calculation."""
        return self._config

    @property
    def temperature_celsius(self) -> float:
        """Temperature used for both local probabilities and their opening energies."""
        return self.config.temperature_celsius

    @property
    def available(self) -> bool:
        """Whether ViennaRNA can perform the requested calculation."""
        return self._rna is not None

    def _parameters(self, sequence: str) -> tuple[int, int, int]:
        n = len(sequence)
        window = min(n, self.window)
        return window, min(n, self.max_span, window), min(n, self.unpaired)

    def provenance(self, sequence: str) -> dict:
        """Exact RNAplfold implementation and clamped parameters for ``sequence``."""
        window, max_span, unpaired = self._parameters(sequence)
        return {
            "tool": "RNAplfold",
            "viennarna_version": getattr(self._rna, "__version__", None),
            "window": window,
            "max_span": max_span,
            "unpaired": unpaired,
            "temperature_celsius": self.temperature_celsius,
            "folding_model": folding_provenance(
                self.config, window_size=window, max_bp_span=max_span
            )
            if self.available
            else None,
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

    def _matrix(self, sequence: str):
        if not self.available:
            raise RuntimeError(
                "ViennaRNA is unavailable; RNAplfold probabilities were not computed."
            )
        if not sequence:
            return ((0.0,),)
        window, max_span, unpaired = self._parameters(sequence)
        compound = configured_compound(
            sequence,
            self.config,
            window_size=window,
            max_bp_span=max_span,
            options=self._rna.OPTION_WINDOW | self._rna.OPTION_PF,
        )
        rows = {}

        def collect(probabilities, size, end, _maximum, kind, _data):
            if (kind & self._rna.PROBS_WINDOW_UP) and (
                kind & self._rna.ANY_LOOP
            ) == self._rna.ANY_LOOP:
                # Copy the callback data before ViennaRNA releases its working arrays.
                # ``end`` is the 1-based inclusive interval end; slot zero is unused.
                rows[end] = tuple(probabilities[1 : size + 1])

        if not compound.probs_window(unpaired, self._rna.PROBS_WINDOW_UP, collect):
            raise RuntimeError("ViennaRNA failed to compute RNAplfold probabilities.")
        matrix = [[0.0] * (unpaired + 1) for _ in range(len(sequence) + 1)]
        for end in range(1, len(sequence) + 1):
            row = rows.get(end)
            expected = min(end, unpaired)
            if row is None or len(row) != expected or any(value is None for value in row):
                raise RuntimeError("ViennaRNA returned an incomplete RNAplfold probability table.")
            for length, value in enumerate(row, start=1):
                matrix[end][length] = float(value)
        return tuple(tuple(row) for row in matrix)
