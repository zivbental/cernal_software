"""Read the bundled catalog; materialize a chosen comparison into a real Dataset.

Mirrors ``apps.datasets.services.create_example_dataset`` exactly, generalized from one
bundled key to a curated organism -> experiment -> comparison hierarchy. The catalog
itself (``apps/expression/catalog/``) is read-only at request time — see
``apps/expression/providers/__init__.py`` for why nothing here ever calls a provider.
"""

import json
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.dateparse import parse_datetime

from apps.datasets.models import Dataset
from apps.datasets.services import DatasetValidationError, create_dataset
from apps.expression.models import DatasetProvenance

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"

#: Host-aligned (engine.domain.Host) — the only three organisms this catalog supports
#: (task brief §3). Display names are for the UI; keys are what's stored everywhere else.
ORGANISMS = [
    {"key": "human", "name": "Homo sapiens"},
    {"key": "yeast", "name": "Saccharomyces cerevisiae"},
    {"key": "ecoli", "name": "Escherichia coli"},
]


def _load_manifest() -> dict[str, dict]:
    """Not cached across requests — the file is a few KB and dev/test runs regenerate
    it via the sync command, so a stale in-process cache would be a worse trade than a
    disk read this small."""
    manifest_path = CATALOG_DIR / "manifest.json"
    if not manifest_path.is_file():
        return {}
    return json.loads(manifest_path.read_text())


def list_organisms() -> list[dict]:
    return ORGANISMS


def list_experiments(organism: str) -> list[dict]:
    """One row per distinct (organism, accession) — an accession can hold more than one
    curated comparison, but the wizard picks the experiment first, the comparison second
    (task brief §2's hierarchy)."""
    manifest = _load_manifest()
    seen: dict[str, dict] = {}
    for key, entry in manifest.items():
        if entry["organism"] != organism:
            continue
        experiment_key = _experiment_key(key)
        if experiment_key not in seen:
            seen[experiment_key] = {
                "experiment_key": experiment_key,
                "organism": entry["organism"],
                "provider": entry["provider"],
                "accession": entry["experiment_accession"],
                "title": entry["experiment_title"],
                "source_url": entry["source_url"],
            }
    return sorted(seen.values(), key=lambda e: e["title"])


def list_comparisons(experiment_key: str) -> list[dict]:
    manifest = _load_manifest()
    return [
        {
            "comparison_key": key,
            "comparison_id": entry["comparison_id"],
            "label": entry["comparison_label"],
            "experimental_condition": entry["experimental_condition"],
            "reference_condition": entry["reference_condition"],
            "gene_count": entry["gene_count"],
        }
        for key, entry in manifest.items()
        if _experiment_key(key) == experiment_key
    ]


def get_comparison_info(comparison_key: str) -> dict:
    """The info-card data (task brief §12) — every field the UI shows before a
    researcher commits to loading it."""
    entry = _manifest_entry(comparison_key)
    return {"comparison_key": comparison_key, **entry}


def materialize_public_dataset(*, user, comparison_key: str) -> Dataset:
    """Copy one curated comparison's bundled CSV into a Dataset the user owns.

    Goes through exactly the same checksum/validation path as an upload
    (``create_dataset``, unchanged) — a public dataset is indistinguishable from an
    upload downstream, which is the whole point (docs/architecture.md §5).
    """
    entry = _manifest_entry(comparison_key)
    csv_path = CATALOG_DIR / entry["csv_path"]
    if not csv_path.is_file():
        raise DatasetValidationError(
            f"'{comparison_key}' is in the catalog but its data file is missing from this install."
        )

    name = f"{entry['experiment_title']} — {entry['comparison_label']}"[:200]
    dataset = create_dataset(
        uploaded_file=SimpleUploadedFile(
            f"{comparison_key}.csv", csv_path.read_bytes(), content_type="text/csv"
        ),
        user=user,
        name=name,
    )
    DatasetProvenance.objects.create(
        dataset=dataset,
        provider=entry["provider"],
        organism=entry["organism"],
        experiment_accession=entry["experiment_accession"],
        experiment_title=entry["experiment_title"],
        comparison_id=entry["comparison_id"],
        comparison_label=entry["comparison_label"],
        experimental_condition=entry["experimental_condition"],
        reference_condition=entry["reference_condition"],
        source_url=entry["source_url"],
        retrieved_at=parse_datetime(entry["retrieved_at"]),
        analysis_method=entry.get("analysis_method", ""),
        publication_doi=entry.get("publication_doi", ""),
        provider_metadata=entry.get("provider_metadata", {}),
    )
    return dataset


def _manifest_entry(comparison_key: str) -> dict:
    manifest = _load_manifest()
    try:
        return manifest[comparison_key]
    except KeyError:
        known = ", ".join(sorted(manifest)) or "none"
        raise DatasetValidationError(
            f"Unknown public dataset '{comparison_key}'. Available: {known}."
        ) from None


def _experiment_key(comparison_key: str) -> str:
    """``"human__E-CURD-149__g3_g1"`` -> ``"human__E-CURD-149"``."""
    organism, accession, _comparison_id = comparison_key.split("__", 2)
    return f"{organism}__{accession}"
