"""Refresh the bundled iGEM Registry metadata for CERNAL's parts table.

Run this offline, ahead of time, the same way ``tools/sync_transcriptome.py`` and
``tools/gen_api_surface.py`` are — the running application never calls the Registry
itself (``apps/expression/providers/__init__.py`` states the same principle for the
expression catalog):

    uv run python tools/sync_registry_parts.py

Fetches every part named in ``engine.stages.plasmids.REGISTRY_PARTS`` from the iGEM
Registry's REST API (new in August 2025; read-only access needs no credentials) and
writes ``src/engine/data/registry/parts.json`` — the catalog
``tests/engine/test_registry_parts.py`` checks the parts table against, and
``to_sbol3`` reads Sequence Ontology roles from.

**What is stored, and what deliberately is not.** The catalog holds identity and
provenance — registry UUID, the SO role accession, topology, license, URL — plus the
sequence's *length and SHA-256*. It never stores the sequences themselves. The tables
in ``engine/stages/plasmids.py`` remain the single source of truth for what CERNAL
builds; a second copy of a promoter's bases is exactly the duplication CLAUDE.md §1 is
about, and a digest catches drift just as well while being impossible to accidentally
build from.

**Drift is reported, never silently written.** If a Registry sequence no longer matches
the table, this script says so and exits non-zero without touching the catalog — the
table is a scientific decision and a human resolves the disagreement, as
docs/plasmids.md §4 has it.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.stages.plasmids import (  # noqa: E402  — needs sys.path above
    BACKBONES,
    PAYLOADS,
    PROMOTERS,
    REGISTRY_PARTS,
    TERMINATORS,
)

#: The Registry's REST API. Read-only part lookup is unauthenticated; this script never
#: writes, so it never needs a token (plan: registry integration is read-only on purpose).
API_BASE = "https://api.registry.igem.org/v1"

#: Where the human-readable part page lives, recorded per entry so a reader of the
#: catalog — or of an SBOL file CERNAL emits — can go look the part up.
PART_URL = "https://registry.igem.org/parts/{slug}"

OUTPUT = ROOT / "src" / "engine" / "data" / "registry" / "parts.json"

TIMEOUT = 30

#: The Registry rate-limits well below what 15 parts at 2 requests each needs if issued back
#: to back — measured: HTTP 429 from the sixth part onward. This is a courtesy pause
#: between requests, not a tuning knob; a sync of the whole table takes under a minute
#: either way, and the alternative is hammering a free community service.
PAUSE_SECONDS = 1.5

#: Retries for a 429 specifically. Anything else is a real error and is not retried.
MAX_RETRIES = 4


def _get(path: str) -> Any:
    """One GET against the Registry API, returning parsed JSON.

    Backs off and retries on HTTP 429 only — a 404 means the part is genuinely not
    there and retrying it just prolongs the rate limiting for the parts that follow.
    """
    request = urllib.request.Request(
        API_BASE + path,
        headers={"Accept": "application/json", "User-Agent": "CERNAL-sync-registry-parts"},
    )
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == MAX_RETRIES - 1:
                raise
            backoff = PAUSE_SECONDS * (2**attempt)
            print(f"        rate limited, waiting {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError("unreachable")  # pragma: no cover


def _fetch_part(registry_name: str) -> dict[str, Any]:
    """The Registry's full record for one part, matched on its exact name.

    ``?name=`` is an exact filter; the ``?search=`` parameter is full-text and returns
    composite parts that merely mention the name in their title, which is how you end up
    recording BBa_K5299203's metadata under BBa_J23119.
    """
    found = _get("/parts?name=" + urllib.parse.quote(registry_name))
    rows = [row for row in found.get("data", []) if row.get("name") == registry_name]
    if not rows:
        raise LookupError(f"{registry_name}: no part with that exact name in the Registry")
    return _get(f"/parts/{rows[0]['uuid']}")


def _local_sequences() -> dict[str, str]:
    """Every part CERNAL actually builds with, keyed by its local name."""
    local: dict[str, str] = {}
    for table in (PROMOTERS, TERMINATORS, PAYLOADS, BACKBONES):
        for name, sequence in table.values():
            local[name] = sequence
    return local


def main() -> int:
    local = _local_sequences()
    catalog: dict[str, Any] = {}
    drift: list[str] = []
    missing: list[str] = []

    for local_name, registry_name in sorted(REGISTRY_PARTS.items()):
        if local_name not in local:
            missing.append(f"{local_name}: named in REGISTRY_PARTS but in no parts table")
            continue
        try:
            time.sleep(PAUSE_SECONDS)
            part = _fetch_part(registry_name)
        except (LookupError, urllib.error.URLError, TimeoutError) as exc:
            missing.append(f"{local_name} ({registry_name}): {exc}")
            continue

        registry_sequence = (part.get("sequence") or "").strip().upper()
        table_sequence = local[local_name].strip().upper()
        if registry_sequence != table_sequence:
            drift.append(
                f"{local_name} ({registry_name}): table has {len(table_sequence)} nt, "
                f"Registry has {len(registry_sequence)} nt"
            )
            continue

        role = part.get("role") or {}
        topology = part.get("topology") or {}
        catalog[local_name] = {
            "registry_name": registry_name,
            "uuid": part["uuid"],
            "url": PART_URL.format(slug=part.get("slug", "")),
            "title": part.get("title") or "",
            "source_revision": (part.get("audit") or {}).get("updated") or "",
            "source_origin": part.get("source") or "",
            "role_accession": role.get("accession") or "",
            "role_label": role.get("label") or "",
            "topology_accession": topology.get("accession") or "",
            "topology_label": topology.get("label") or "",
            "license_uuid": part.get("licenseUUID") or "",
            "length_bp": len(registry_sequence),
            "sequence_sha256": hashlib.sha256(registry_sequence.encode()).hexdigest(),
        }
        print(
            f"  ok    {local_name:<12} {registry_name:<14} {len(registry_sequence):>5} nt  "
            f"{role.get('accession') or '—'}"
        )

    for problem in missing:
        print(f"  MISS  {problem}", file=sys.stderr)
    for problem in drift:
        print(f"  DRIFT {problem}", file=sys.stderr)

    if drift or missing:
        print(
            f"\nRefusing to write {OUTPUT.relative_to(ROOT)}: "
            f"{len(drift)} drifted, {len(missing)} unresolved. "
            "The parts table is a scientific decision (docs/plasmids.md §4) — a human "
            "decides whether the table or the Registry is right here.",
            file=sys.stderr,
        )
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {OUTPUT.relative_to(ROOT)} — {len(catalog)} parts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
