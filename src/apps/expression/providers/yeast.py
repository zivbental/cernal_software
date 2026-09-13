"""S. cerevisiae differential-expression data (docs §7 of the brief).

yStreX (the intended source) was unreachable at every domain tried this session
(``ystrex.riken.jp``, ``www.ystrex.org`` — DNS resolution failure, not a timeout or a
403). Per the brief's own fallback instruction, this wraps
``ExpressionAtlasProvider`` scoped to *S. cerevisiae* instead: Expression Atlas has 13
real RNA-seq differential experiments for yeast, verified live.

Nothing outside this module is supposed to know that — ``services.py`` and the sync
command import ``YeastExpressionProvider``, never ``ExpressionAtlasProvider``, for
anything yeast-related. If a working yStreX endpoint appears later, only this file
changes.
"""

from apps.expression.providers.expression_atlas import ExpressionAtlasProvider
from apps.expression.providers.normalize import NormalizedComparison, NormalizedDeRow

SPECIES = "Saccharomyces cerevisiae"


class YeastExpressionProvider:
    name = "yeast_expression"

    def __init__(self) -> None:
        self._atlas = ExpressionAtlasProvider()

    def list_experiments(self) -> list[dict]:
        return self._atlas.list_experiments(SPECIES)

    def list_comparisons(self, accession: str) -> list[NormalizedComparison]:
        return self._atlas.list_comparisons(accession)

    def get_differential_expression(
        self, accession: str, contrast_id: str
    ) -> list[NormalizedDeRow]:
        return self._atlas.get_differential_expression(accession, contrast_id)
