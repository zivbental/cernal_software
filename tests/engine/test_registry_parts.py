"""The parts table really is the iGEM Registry parts it claims to be.

``stages/plasmids.py``'s table comment says its defaults are "verified against the iGEM
Registry API rather than typed from memory". That was true when a human did it by hand
and nothing kept it true afterwards. These tests make it a standing claim: every entry
names a Registry part, and the bundled catalog's digest still matches the sequence the
engine actually builds with.

**Offline.** Nothing here touches the network — ``tools/sync_registry_parts.py`` does
that, ahead of time, and checks in the result. CI must never depend on a live community
service (``apps/expression/providers/__init__.py`` makes the same argument for the
expression catalog).
"""

import hashlib

import pytest

from engine.stages.plasmids import (
    BACKBONES,
    PAYLOADS,
    PROMOTERS,
    REGISTRY_PARTS,
    TERMINATORS,
    load_registry_catalog,
)


def _local_parts() -> dict[str, str]:
    """Every part the engine builds with, keyed by its local name."""
    local: dict[str, str] = {}
    for table in (PROMOTERS, TERMINATORS, PAYLOADS, BACKBONES):
        for name, sequence in table.values():
            local[name] = sequence
    return local


def test_the_catalog_was_synced_at_all():
    """A missing catalog is a setup mistake, not a reason to skip the checks below."""
    assert load_registry_catalog(), (
        "src/engine/data/registry/parts.json is missing or empty — "
        "run: uv run python tools/sync_registry_parts.py"
    )


def test_every_part_in_the_tables_declares_a_registry_part():
    missing = sorted(set(_local_parts()) - set(REGISTRY_PARTS))
    assert not missing, (
        f"{missing} appear in a parts table but not in REGISTRY_PARTS, so nothing checks "
        "them against the Registry. Add the mapping and re-run the sync tool."
    )


def test_registry_parts_names_only_parts_that_exist_in_a_table():
    """The reverse direction: a stale mapping entry means the sync tool fetches a part
    nothing uses, and the drift check below silently covers one part fewer."""
    orphans = sorted(set(REGISTRY_PARTS) - set(_local_parts()))
    assert not orphans, f"{orphans} are mapped to Registry parts but are in no parts table"


@pytest.mark.parametrize("local_name", sorted(_local_parts()))
def test_the_table_sequence_still_matches_the_registry_part(local_name):
    """The drift check.

    Compares against the digest recorded from the Registry, not against a second copy of
    the sequence — the table stays the one place a part's bases live (CLAUDE.md §1). A
    failure here means the table and the Registry disagree, which is a scientific
    decision for a human (docs/plasmids.md §4), not something to auto-fix.
    """
    catalog = load_registry_catalog()
    entry = catalog.get(local_name)
    assert entry, f"{local_name} has no catalog entry — re-run tools/sync_registry_parts.py"

    sequence = _local_parts()[local_name].strip().upper()
    assert len(sequence) == entry["length_bp"], (
        f"{local_name} ({entry['registry_name']}): table has {len(sequence)} nt, "
        f"Registry had {entry['length_bp']} nt when last synced"
    )
    assert hashlib.sha256(sequence.encode()).hexdigest() == entry["sequence_sha256"], (
        f"{local_name} ({entry['registry_name']}): same length as the Registry part but "
        f"different bases — see {entry['url']}"
    )


def test_every_catalog_entry_carries_the_provenance_sbol_export_needs():
    """``to_sbol3`` reads these fields; an entry missing one degrades the SBOL output
    silently rather than failing, so assert them here instead."""
    for local_name, entry in sorted(load_registry_catalog().items()):
        for field in ("registry_name", "uuid", "url", "role_accession"):
            assert entry.get(field), f"{local_name} has no {field} in the bundled catalog"
