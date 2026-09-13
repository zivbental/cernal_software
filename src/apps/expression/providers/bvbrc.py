"""BV-BRC — bacterial differential-expression biosets (docs §6 of the brief).

``https://www.bv-brc.org/api/bioset/`` and ``.../bioset_result/`` are real,
unauthenticated JSON REST endpoints (verified live) — no FTP mirror exists here the way
Expression Atlas has one, so this provider talks to the API directly, at sync time only.

**Discovered limitations, not assumed:**
- The documented example query (``eq(bioset_type,differential_expression)``) uses a
  value that does not exist in the real data — the actual field values observed are
  ``"Differential"`` and ``"RNA-seq Differential Expression"``. Filtering here matches
  on real observed values, not the doc's example.
- ``bioset_result`` rows do **not** all carry a p-value — some biosets report only
  ``log2_fc`` and a ``z_score``. A row with no p-value is kept with
  ``p_value=None``, never fabricated.
- The API caps how much a single request returns before truncating mid-response
  (observed: a ``limit(10000,0)`` request came back with invalid, cut-off JSON) — so
  paging uses a conservative page size and stops using the ``Content-Range`` header's
  total count.
"""

from __future__ import annotations

import logging

import requests

from apps.expression.providers.normalize import NormalizedDeRow

logger = logging.getLogger(__name__)

BASE = "https://www.bv-brc.org/api"
TIMEOUT = 30
PAGE_SIZE = 500

#: Real observed values — see module docstring. Not the documentation's example value.
DIFFERENTIAL_BIOSET_TYPES = ("Differential", "RNA-seq Differential Expression")


class BVBRCProvider:
    """``list_experiments`` / ``get_differential_expression`` for *E. coli*."""

    name = "bvbrc"

    def list_experiments(self, keyword: str = "Escherichia coli", limit: int = 500) -> list[dict]:
        """Public RNA-seq differential-expression biosets, filtered client-side to real
        observed ``bioset_type`` values and to organisms that are actually *E. coli*
        (BV-BRC's ``keyword()`` search is loose — e.g. it can surface a bioset about a
        completely different organism that merely mentions *E. coli* in its title)."""
        # BV-BRC's RQL syntax needs literal, unencoded parentheses — requests' own
        # params= dict percent-encodes them ("(" -> "%28"), which the API rejects with a
        # 400. Verified live: the query string must be built and passed as-is.
        response = requests.get(
            f"{BASE}/bioset/?keyword({keyword})&limit({limit})",
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        biosets = response.json()

        seen: set[str] = set()
        experiments = []
        for row in biosets:
            organism = row.get("organism", "")
            bioset_type = row.get("bioset_type", "")
            bioset_id = row.get("bioset_id")
            if (
                not organism.startswith("Escherichia coli")
                or bioset_type not in DIFFERENTIAL_BIOSET_TYPES
            ):
                continue
            if bioset_id in seen:
                continue
            seen.add(bioset_id)
            experiments.append(
                {
                    "bioset_id": bioset_id,
                    "exp_id": row.get("exp_id"),
                    "title": row.get("exp_title") or row.get("bioset_name") or bioset_id,
                    "bioset_name": row.get("bioset_name", ""),
                    "treatment_name": row.get("treatment_name", ""),
                    "strain": row.get("strain", ""),
                    "study_title": row.get("study_title", ""),
                    "entity_count": row.get("entity_count"),
                }
            )
        return experiments

    def get_differential_expression(self, bioset_id: str) -> list[NormalizedDeRow]:
        """Page through ``bioset_result`` for one bioset. A bioset can hold thousands of
        genes (a whole-genome comparison); this returns all of it — the sync command
        decides how much of that to keep in the curated catalog, not this adapter."""
        rows: list[NormalizedDeRow] = []
        offset = 0
        total: int | None = None

        while total is None or offset < total:
            response = requests.get(
                f"{BASE}/bioset_result/?eq(bioset_id,{bioset_id})&limit({PAGE_SIZE},{offset})",
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            page = response.json()
            if not page:
                break

            for record in page:
                gene_id = (
                    record.get("locus_tag") or record.get("gene_id") or record.get("patric_id")
                )
                log2fc = record.get("log2_fc")
                if not gene_id or log2fc is None:
                    continue
                rows.append(
                    NormalizedDeRow(
                        gene_id=str(gene_id),
                        gene_symbol=(record.get("gene") or "").strip() or None,
                        log2_fold_change=float(log2fc),
                        p_value=_as_float(record.get("p_value")),
                        adjusted_p_value=_as_float(record.get("q_value") or record.get("padj")),
                    )
                )

            content_range = response.headers.get("Content-Range", "")
            if total is None and "/" in content_range:
                try:
                    total = int(content_range.rsplit("/", 1)[1])
                except ValueError:
                    total = len(page)  # header missing/malformed — this page is all we get
            offset += len(page)
            if len(page) < PAGE_SIZE:
                break

        return rows


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
