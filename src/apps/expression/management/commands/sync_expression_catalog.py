"""Fetch, normalize and bundle the curated public-dataset catalog.

Run this offline, ahead of time — the running application never calls a provider (see
``apps/expression/providers/__init__.py``). Re-run it to refresh an entry or add a new
one to ``CURATED_EXPERIMENTS`` below; nothing else in the app needs to change.

    uv run python manage.py sync_expression_catalog
    uv run python manage.py sync_expression_catalog --only human

Every accession/bioset id below was fetched and verified live against the real provider
during development — see docs/public-datasets.md for the full verification log and the
limitations discovered along the way (Expression Atlas: no adjusted-p-value column, and
only RNA-seq experiments are fetchable this way — microarray analytics files use a
platform-suffixed filename this provider deliberately doesn't chase; BV-BRC: p-value is
not present on every bioset).
"""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.expression.providers.bvbrc import BVBRCProvider
from apps.expression.providers.expression_atlas import ExpressionAtlasProvider
from apps.expression.providers.normalize import CSV_FIELDNAMES

CATALOG_DIR = Path(__file__).resolve().parents[3] / "expression" / "catalog"

#: Keep the catalog small and curated (task brief §8) — a handful of real, representative
#: experiments per organism, not an import of everything the provider has. Every entry
#: here traces to a real accession, verified live, never fabricated.
CURATED_EXPERIMENTS = [
    # --- human (EMBL-EBI Expression Atlas) ---
    {
        "organism": "human",
        "provider": "expression_atlas",
        "accession": "E-CURD-149",
        "category": "inflammatory response",
    },
    {
        "organism": "human",
        "provider": "expression_atlas",
        "accession": "E-CURD-45",
        "category": "cancer vs normal",
    },
    {
        "organism": "human",
        "provider": "expression_atlas",
        "accession": "E-GEOD-103501",
        "category": "immune activation",
    },
    {
        "organism": "human",
        "provider": "expression_atlas",
        "accession": "E-GEOD-54112",
        "category": "differentiation",
    },
    {
        "organism": "human",
        "provider": "expression_atlas",
        "accession": "E-MTAB-2580",
        "category": "hypoxia",
    },
    # --- yeast (EMBL-EBI Expression Atlas — yStreX was unreachable, see providers/yeast.py) ---
    {
        "organism": "yeast",
        "provider": "yeast_expression",
        "accession": "E-MTAB-5313",
        "category": "osmotic stress",
    },
    {
        "organism": "yeast",
        "provider": "yeast_expression",
        "accession": "E-MTAB-10511",
        "category": "ER stress / unfolded protein response",
    },
    {
        "organism": "yeast",
        "provider": "yeast_expression",
        "accession": "E-MTAB-7657",
        "category": "nutrient depletion / growth phase",
    },
    {
        "organism": "yeast",
        "provider": "yeast_expression",
        "accession": "E-MTAB-4651",
        "category": "nitrogen source / nutrient response",
    },
    {
        "organism": "yeast",
        "provider": "yeast_expression",
        "accession": "E-GEOD-59814",
        "category": "metabolic engineering",
    },
    # --- E. coli (BV-BRC) --- bioset_id doubles as the comparison; exp_id as the experiment.
    {
        "organism": "ecoli",
        "provider": "bvbrc",
        "bioset_id": "67644164",
        "exp_id": "138294",
        "category": "heat shock",
    },
    {
        "organism": "ecoli",
        "provider": "bvbrc",
        "bioset_id": "44313016",
        "exp_id": "92117",
        "category": "oxidative stress",
    },
    {
        "organism": "ecoli",
        "provider": "bvbrc",
        "bioset_id": "42635036",
        "exp_id": "88048",
        "category": "antibiotic treatment",
    },
    {
        "organism": "ecoli",
        "provider": "bvbrc",
        "bioset_id": "68952326",
        "exp_id": "85809",
        "category": "nutrient limitation",
    },
    {
        "organism": "ecoli",
        "provider": "bvbrc",
        "bioset_id": "44541816",
        "exp_id": "105638",
        "category": "growth-condition change",
    },
]

#: A comparison can hold a whole genome/transcriptome (E. coli: ~4,300 genes; human:
#: ~58,000 measured transcripts). The API preview endpoint already caps what it renders
#: at 2,000 rows sorted by |log2FC| — storing more than a little past that cap buys
#: nothing and works against "keep the catalog intentionally small" (task brief §8).
MAX_ROWS_PER_COMPARISON = 3000


class Command(BaseCommand):
    help = "Fetch and normalize the curated public expression-dataset catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=["human", "yeast", "ecoli"],
            default=None,
            help="Sync a single organism, e.g. while iterating on one provider.",
        )

    def handle(self, *args, **options):
        only = options["only"]
        atlas = ExpressionAtlasProvider()
        bvbrc = BVBRCProvider()
        synced_at = datetime.now(UTC).isoformat()

        manifest: dict[str, dict] = {}
        for entry in CURATED_EXPERIMENTS:
            if only and entry["organism"] != only:
                continue
            try:
                if entry["provider"] == "bvbrc":
                    self._sync_bvbrc_entry(bvbrc, entry, synced_at, manifest)
                else:
                    self._sync_atlas_entry(atlas, entry, synced_at, manifest)
            except Exception as exc:
                self.stderr.write(self.style.WARNING(f"Skipped {entry}: {exc!r}"))

        if only:
            manifest_path = CATALOG_DIR / "manifest.json"
            existing = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
            existing.update(manifest)
            manifest = existing
        (CATALOG_DIR).mkdir(parents=True, exist_ok=True)
        (CATALOG_DIR / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {len(manifest)} comparison(s) to {CATALOG_DIR}")
        )

    # --- Expression Atlas (human + yeast, the latter via YeastExpressionProvider's identity) --

    def _sync_atlas_entry(self, atlas, entry, synced_at, manifest):
        accession = entry["accession"]
        comparisons = atlas.list_comparisons(accession)
        if not comparisons:
            self.stderr.write(self.style.WARNING(f"{accession}: no comparisons found"))
            return

        # One representative comparison per curated experiment keeps the catalog small
        # and each entry's story simple — the first (a) is enumeration order, not
        # significance, and is documented as such in docs/public-datasets.md.
        comparison = comparisons[0]
        rows = atlas.get_differential_expression(accession, comparison.comparison_id)
        title = self._atlas_title(accession)

        key = f"{entry['organism']}__{accession}__{comparison.comparison_id}"
        self._write_comparison(
            key=key,
            organism=entry["organism"],
            provider=entry["provider"],
            accession=accession,
            title=title or entry["category"],
            comparison_id=comparison.comparison_id,
            comparison_label=comparison.label,
            experimental_condition=comparison.experimental_condition,
            reference_condition=comparison.reference_condition,
            source_url=f"https://www.ebi.ac.uk/gxa/experiments/{accession}/Results",
            synced_at=synced_at,
            rows=rows,
            manifest=manifest,
        )

    def _atlas_title(self, accession: str) -> str:
        """Best-effort: the JSON experiment list already has the description; a second
        network round trip per accession isn't worth it here since list_experiments()
        already fetches the whole catalog once per call — cheap to just re-derive."""
        for species in ("Homo sapiens", "Saccharomyces cerevisiae"):
            for exp in ExpressionAtlasProvider().list_experiments(species):
                if exp["accession"] == accession:
                    return exp["title"]
        return ""

    # --- BV-BRC (E. coli) -----------------------------------------------------------

    def _sync_bvbrc_entry(self, bvbrc, entry, synced_at, manifest):
        bioset_id = entry["bioset_id"]
        rows = bvbrc.get_differential_expression(bioset_id)
        if not rows:
            self.stderr.write(self.style.WARNING(f"bioset {bioset_id}: no rows"))
            return

        meta = self._bvbrc_bioset_meta(bioset_id)
        # bioset_name, not treatment_name, is the real "X / Y" comparison label —
        # verified live: treatment_name is often a single word ("Ampicillin", "pH")
        # with no direction at all; bioset_name is consistently "condition A / condition B".
        bioset_name = meta.get("bioset_name", "")
        experimental, sep, reference = bioset_name.partition(" / ")
        label = bioset_name if sep else meta.get("treatment_name", bioset_id)

        key = f"ecoli__{entry['exp_id']}__{bioset_id}"
        self._write_comparison(
            key=key,
            organism="ecoli",
            provider="bvbrc",
            accession=entry["exp_id"],
            title=meta.get("exp_title") or meta.get("study_title") or entry["category"],
            comparison_id=bioset_id,
            comparison_label=label,
            experimental_condition=experimental.strip(),
            reference_condition=reference.strip(),
            source_url=f"https://www.bv-brc.org/view/Bioset/{bioset_id}",
            synced_at=synced_at,
            rows=rows,
            manifest=manifest,
            extra={"bioset_id": bioset_id, "strain": meta.get("strain", "")},
        )

    def _bvbrc_bioset_meta(self, bioset_id: str) -> dict:
        import requests

        response = requests.get(
            f"https://www.bv-brc.org/api/bioset/?eq(bioset_id,{bioset_id})",
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else {}

    # --- shared -----------------------------------------------------------------------

    def _write_comparison(
        self,
        *,
        key,
        organism,
        provider,
        accession,
        title,
        comparison_id,
        comparison_label,
        experimental_condition,
        reference_condition,
        source_url,
        synced_at,
        rows,
        manifest,
        extra=None,
    ):
        # Drop untested genes, then keep the most differentially expressed ones — see
        # MAX_ROWS_PER_COMPARISON's docstring for why capping storage is deliberate.
        ranked = sorted(rows, key=lambda r: abs(r.log2_fold_change), reverse=True)
        kept = ranked[:MAX_ROWS_PER_COMPARISON]

        organism_dir = CATALOG_DIR / organism
        organism_dir.mkdir(parents=True, exist_ok=True)
        csv_path = organism_dir / f"{key.split('__', 1)[1].replace('/', '_')}.csv"
        # lineterminator="\n": csv.writer defaults to "\r\n" regardless of platform,
        # which git then flags for CRLF->LF normalisation on every future re-sync.
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES, lineterminator="\n")
            writer.writeheader()
            for row in kept:
                writer.writerow(row.as_row())

        with_pvalue = sum(1 for r in kept if r.p_value is not None)
        with_padj = sum(1 for r in kept if r.adjusted_p_value is not None)

        manifest[key] = {
            "provider": provider,
            "organism": organism,
            "experiment_accession": accession,
            "experiment_title": title,
            "comparison_id": comparison_id,
            "comparison_label": comparison_label,
            "experimental_condition": experimental_condition,
            "reference_condition": reference_condition,
            "source_url": source_url,
            "retrieved_at": synced_at,
            "gene_count": len(kept),
            "genes_with_p_value": with_pvalue,
            "genes_with_adjusted_p_value": with_padj,
            "csv_path": str(csv_path.relative_to(CATALOG_DIR)),
            "provider_metadata": extra or {},
        }
        self.stdout.write(f"  {key}: {len(kept)} genes (of {len(rows)} total)")
