"""Inventory real catalog DE computations without database or media mutations.

Run with uv and PYTHONPATH pointing at the engine checkout under review. All fifteen
bundled comparisons use the same default scientific filters, max_genes=3,
max_designs=1, one short custom CDS and no vector. This is source-path smoke evidence,
not therapeutic validation or a replacement for a full compute-budget run.
"""

import argparse
import dataclasses
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from engine import client
from engine.client import LocalEngine, validate_job_configuration
from engine.contract import INPUT_DE, SCHEMA_VERSION, SUCCEEDED, JobRequest
from engine.domain import Host
from engine.errors import InputValidationError
from engine.inputs import parse_dge_table
from engine.pipeline import build_tools
from engine.stages.genes import GeneSelector
from engine.transcriptome import load_transcriptome, resolve_gene_id

PARAMS = {
    "constraints": {"max_genes": 3},
    "budget": {"max_designs": 1},
    "payload": {"outputs": ["other"], "custom_sequence": "ATGGCTGCTGCTGCTGCTTAA"},
    "backbone": {},
    "statistics": {"hypothesis_universe_complete": False},
}


def selection_inventory(request, raw, host):
    """Repeat the exact cheap stage-1 setup and preserve its pre-inversion shortlist."""
    dge = parse_dge_table(raw, Path(request.input_path).name, hypothesis_universe_complete=False)
    sequences = load_transcriptome(host)
    resolved = []
    unresolved = []
    for row in dge.rows:
        try:
            gene_id = resolve_gene_id(host, row.gene_id)
        except InputValidationError:
            gene_id = row.gene_id
        if gene_id not in sequences:
            unresolved.append(row.gene_id)
        resolved.append(dataclasses.replace(row, gene_id=gene_id))
    tools = build_tools(request, host)
    warnings = []
    inventory = {
        "rows": len(dge.rows),
        "rows_with_p_value": sum(row.p_value is not None for row in dge.rows),
        "rows_with_adjusted_p_value": sum(row.p_adj is not None for row in dge.rows),
        "unmapped_rows": len(unresolved),
        "unmapped_identifiers_sample": unresolved[:10],
        "selected_genes": [],
        "selection_warnings": warnings,
        "selection_error": None,
        "effective_constraints": dataclasses.asdict(tools["constraints"]),
    }
    try:
        genes = GeneSelector(tools["constraints"], tools["screener"]).select(
            dataclasses.replace(dge, rows=tuple(resolved)),
            sequences=sequences,
            on_warning=warnings.append,
        )
        inventory["selected_genes"] = [
            {
                "gene_id": gene.gene_id,
                "symbol": gene.symbol,
                "log2_fold_change": gene.log2_fold_change,
                "regulation": gene.regulation.value,
            }
            for gene in genes
        ]
    except InputValidationError as exc:
        inventory["selection_error"] = str(exc)
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--catalog-key", action="append", help="Limit to exact catalog keys; repeatable."
    )
    args = parser.parse_args()
    source_root = Path(client.__file__).resolve().parents[2]
    catalog_root = source_root / "src/apps/expression/catalog"
    manifest = json.loads((catalog_root / "manifest.json").read_text())
    unknown = set(args.catalog_key or []) - manifest.keys()
    if unknown:
        parser.error(f"Unknown catalog key(s): {sorted(unknown)}")
    report = {
        "schema": "cernal-catalog-smoke-v1",
        "recorded_at": datetime.now(UTC).isoformat(),
        "engine_version": LocalEngine.ENGINE_VERSION,
        "engine_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source_root, text=True
        ).strip(),
        "catalog_manifest_sha256": hashlib.sha256(
            (catalog_root / "manifest.json").read_bytes()
        ).hexdigest(),
        "params": PARAMS,
        "default_hard_filters": LocalEngine().capabilities().hard_filters,
        "seed": 42,
        "interpretation": (
            "Bounded local DE source-path smoke; selected_genes is the pre-inversion stage-1 "
            "shortlist. Down signatures cannot activate a production toehold without an "
            "unimplemented physical inverter. Unknown source hypothesis-universe completeness "
            "is declared false. Zero candidates on succeeded computations is a valid empty "
            "outcome. Neither candidate counts nor study titles establish disease selectivity "
            "or wet-lab efficacy. No C. acnes public comparison is bundled."
        ),
        "expected_comparisons": len(args.catalog_key or manifest),
        "complete": False,
        "comparisons": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for key, metadata in sorted(manifest.items()):
        if args.catalog_key and key not in args.catalog_key:
            continue
        start = time.monotonic()
        path = catalog_root / metadata["csv_path"]
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        host = Host(metadata["organism"])
        families = ["eukaryotic_toehold" if host in (Host.HUMAN, Host.YEAST) else "toehold"]
        params = validate_job_configuration(PARAMS, families, "default", INPUT_DE, "", host.value)
        record = {
            "catalog_key": key,
            "organism": host.value,
            "source_url": metadata["source_url"],
            "comparison_label": metadata["comparison_label"],
            "provider_metadata": metadata.get("provider_metadata", {}),
            "source_checksum": checksum,
            "checksum_matches_catalog": checksum
            == metadata.get("provider_metadata", {}).get("csv_sha256"),
        }
        with tempfile.TemporaryDirectory(prefix="cernal-catalog-smoke-") as output_dir:
            request = JobRequest(
                schema_version=SCHEMA_VERSION,
                run_id=key,
                idempotency_key="catalog-smoke-" + key,
                input_mode=INPUT_DE,
                input_path=str(path),
                input_checksum=checksum,
                trigger_sequence="",
                organism=host.value,
                params=params,
                gate_families=families,
                scoring_profile="default",
                seed=42,
                output_dir=output_dir,
            )
            selection_started = time.monotonic()
            record["selection"] = selection_inventory(request, raw, host)
            record["selection_elapsed_seconds"] = round(time.monotonic() - selection_started, 3)
            stage_times = []

            def progress(pct, stage, stage_times=stage_times, start=start, key=key):
                if not stage_times or stage_times[-1]["stage"] != stage:
                    stage_times.append(
                        {"stage": stage, "elapsed_seconds": round(time.monotonic() - start, 3)}
                    )
                    print(f"{key}: {stage}", flush=True)
                return True

            result = LocalEngine().run(request, progress)
            record["stage_progress"] = stage_times
            record.update(
                terminal_status=result.status,
                error=result.error,
                outcome=("productive" if result.accepted else "valid_empty")
                if result.status == SUCCEEDED
                else "engine_error",
                candidates=len(result.candidates),
                accepted=len(result.accepted),
                rejected=len(result.rejected),
                warnings=result.warnings,
                scientific_provenance=result.scientific_provenance,
                effective_params=result.params,
                candidate_details=[
                    {
                        "ref": candidate.ref,
                        "is_rejected": candidate.is_rejected,
                        "rejection_reason": candidate.rejection_reason,
                        "warnings": candidate.warnings,
                        "metrics": {metric.name: metric.raw_value for metric in candidate.metrics},
                        "construct_sha256": candidate.design.get("construct_sha256"),
                    }
                    for candidate in result.candidates
                ],
                artifact_count=len(result.artifacts),
                elapsed_seconds=round(time.monotonic() - start, 3),
            )
        report["comparisons"].append(record)
        report["complete"] = len(report["comparisons"]) == report["expected_comparisons"]
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(
            f"{key}: {record['terminal_status']} / {record['outcome']} "
            f"{record['accepted']} accepted, {record['elapsed_seconds']}s",
            flush=True,
        )
    if any(not item["checksum_matches_catalog"] for item in report["comparisons"]):
        raise SystemExit("Catalog checksum mismatch; see report.")


if __name__ == "__main__":
    main()
