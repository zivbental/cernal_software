"""apps.expression.services against the real, bundled catalog — no network, no mocks:
the catalog is checked into the repo, so exercising it here is exercising exactly what
ships (docs §26's "provider normalization" concern is covered in
tests/test_expression_providers.py; this file covers the materialize path)."""

import pytest

from apps.datasets.models import Dataset, ValidationStatus
from apps.datasets.services import DatasetValidationError
from apps.expression.models import DatasetProvenance, Provider
from apps.expression.services import (
    get_comparison_info,
    list_comparisons,
    list_experiments,
    list_organisms,
    materialize_public_dataset,
)

ECOLI_COMPARISON_KEY = "ecoli__88048__42635036"  # Ampicillin treatment — see catalog/manifest.json


def test_list_organisms_is_the_three_supported_hosts():
    keys = {o["key"] for o in list_organisms()}
    assert keys == {"human", "yeast", "ecoli"}


def test_list_experiments_returns_only_that_organisms_curated_entries():
    experiments = list_experiments("ecoli")

    assert len(experiments) == 5  # the curated set — see sync_expression_catalog.py
    assert all(e["organism"] == "ecoli" for e in experiments)
    assert all(e["title"] and e["accession"] for e in experiments)


def test_list_experiments_for_an_unknown_organism_is_empty_not_an_error():
    assert list_experiments("mouse") == []


def test_list_comparisons_reaches_the_curated_ampicillin_entry():
    comparisons = list_comparisons("ecoli__88048")

    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert comparison["comparison_key"] == ECOLI_COMPARISON_KEY
    assert "Ampicillin" in comparison["experimental_condition"]
    assert comparison["gene_count"] > 0


def test_comparison_info_carries_full_provenance_for_the_info_card():
    info = get_comparison_info(ECOLI_COMPARISON_KEY)

    assert info["organism"] == "ecoli"
    assert info["provider"] == "bvbrc"
    assert info["experiment_accession"] == "88048"
    assert info["source_url"].startswith("https://www.bv-brc.org/")
    assert info["gene_count"] > 0


def test_unknown_comparison_key_names_the_available_ones():
    with pytest.raises(DatasetValidationError, match=ECOLI_COMPARISON_KEY):
        get_comparison_info("does-not-exist")


def test_materializing_a_public_dataset_produces_a_real_valid_dataset(user, media_root):
    """Same standard an upload is held to — checksum, validation, real file in storage —
    plus a DatasetProvenance row recording exactly where it came from."""
    dataset = materialize_public_dataset(user=user, comparison_key=ECOLI_COMPARISON_KEY)

    assert isinstance(dataset, Dataset)
    assert dataset.validation_status == ValidationStatus.VALID
    assert dataset.uploaded_by_id == user.id
    assert len(dataset.checksum_sha256) == 64
    assert dataset.file.storage.exists(dataset.file.name)

    provenance = DatasetProvenance.objects.get(dataset=dataset)
    assert provenance.provider == Provider.BVBRC
    assert provenance.organism == "ecoli"
    assert provenance.experiment_accession == "88048"
    assert provenance.retrieved_at is not None


def test_materializing_an_unknown_comparison_raises_with_available_keys(user, media_root):
    with pytest.raises(DatasetValidationError, match="Unknown public dataset"):
        materialize_public_dataset(user=user, comparison_key="not-a-real-key")


def test_each_curated_organism_has_at_least_one_working_comparison():
    """A cheap end-to-end smoke test over the whole bundled catalog — every organism
    the wizard advertises must actually have something a researcher can load."""
    for organism in ("human", "yeast", "ecoli"):
        experiments = list_experiments(organism)
        assert experiments, f"{organism} has no curated experiments"
        comparisons = list_comparisons(experiments[0]["experiment_key"])
        assert comparisons, f"{organism}'s first experiment has no comparisons"
