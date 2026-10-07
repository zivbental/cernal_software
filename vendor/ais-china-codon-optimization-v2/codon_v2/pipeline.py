"""Selected strategies run independently. A failure preserves other results."""
from datetime import datetime, timezone
import hashlib
import json
import platform
import time

from . import __version__
from .config import STRATEGIES, validate_request
from .constraints import Rules
from .metrics import evaluate, comparable_positions
from .references import ReferenceStore
from .rna import RNAEngine
from .search import run_strategy, seed_pool
from .sequence import AA, digest, edits


def availability(strategy, cds, host, request, engine, source):
    key = {"host_sampling": "sampling", "cai_max": "cai", "tai_max": "tai" if request["tai_model"] == "classic" else "stai", "harmonize": "rank"}.get(strategy)
    if key and key not in host.tables:
        return host.reasons.get(key, key + "_reference_unavailable")
    if strategy == "rna_start":
        if not cds.standard_start:
            return "nonstandard_start"
        if engine.reason:
            return engine.reason
    if strategy == "cai_max" and not any(c in AA and AA[c] not in {"M", "W"} and not (i == 0 and cds.standard_start) for i, c in enumerate(cds.codons)):
        return "no_scored_codons"
    if strategy == "tai_max" and not any(c in AA for c in cds.codons[1:]):
        return "no_scored_codons"
    if strategy == "harmonize" and (source is None or not comparable_positions(cds)):
        return "source_reference_or_comparable_positions_missing"
    return None


def optimize(raw, refs=None, progress=None, cancelled=lambda: False, disable_rna=False):
    refs = refs or ReferenceStore()
    request, cds, host, source_ranks, source_metadata = validate_request(raw, refs)
    started = time.monotonic()
    engine = RNAEngine(refs.root, disabled=disable_rna)
    common_rules = Rules(cds, request)
    warnings = list(cds.warnings)
    if not request["upstream_transcribed_sequence"]:
        warnings.append("missing_upstream_cds_only_rna")
    if request["tai_model"] == "stai":
        warnings.append("stai_exploratory_dcbs_fit_not_expression_validation")
    original_metrics, original_constraints = evaluate(cds.sequence, cds, host, request, engine, common_rules, source_ranks)
    original = {"candidate_id": "ORIGINAL", "sequence": cds.sequence, "sequence_sha256": digest(cds.sequence), "protein": cds.protein,
                "metrics": original_metrics, "constraints": original_constraints, "changes": [], "strategy_memberships": []}
    statuses = [{"strategy_id": s, "status": "queued"} for s in request["strategies"]]
    report = {"schema_version": "2.0", "run": {"code_version": __version__, "python_version": platform.python_version(),
              "implementation_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((refs.root / "codon_v2").glob("*.py"))},
              "created_utc": datetime.now(timezone.utc).isoformat(), "config": request,
              "request_sha256": digest(json.dumps(request, sort_keys=True, separators=(",", ":"))),
              "coordinate_system": "1-based inclusive", "reference_version": host.manifest["reference_version"]},
              "status": "running", "reference_manifest": host.metadata(), "source_reference": source_metadata,
              "input": {"name": cds.name, "sequence": cds.sequence, "protein": cds.protein, "normalization": list(cds.normalization),
                        "standard_start": cds.standard_start, "terminal_stop": cds.terminal_stop},
              "original_result": original, "candidates": [], "strategy_status": statuses, "warnings": warnings}
    def publish():
        if progress:
            # JSON copy prevents a polling thread from seeing a half-mutated result.
            progress(json.loads(json.dumps(report, allow_nan=False)))
    publish()
    seeds, seed_stats = seed_pool(cds, request, host, cancelled)
    report["run"]["shared_seed_pool"] = seeds
    report["run"]["shared_seed_budget"] = seed_stats
    by_sequence = {}
    for i, strategy in enumerate(request["strategies"]):
        if cancelled():
            statuses[i] = {"strategy_id": strategy, "status": "cancelled", "reason": "user_cancelled"}
            continue
        reason = availability(strategy, cds, host, request, engine, source_ranks)
        if reason:
            statuses[i] = {"strategy_id": strategy, "status": "unavailable", "reason": reason, "returned_count": 0}
            publish()
            continue
        statuses[i] = {"strategy_id": strategy, "status": "running"}
        publish()
        try:
            sequences, status = run_strategy(strategy, cds, host, request, engine, seeds, source_ranks, cancelled)
            for rank, sequence in enumerate(sequences, 1):
                sha = digest(sequence)
                membership = {"strategy_id": strategy, "label": STRATEGIES[strategy], "candidate_number": rank,
                              "representative": "first_valid_frequency_sample" if strategy == "host_sampling" else "first_by_objective",
                              **status["candidate_provenance"][sha]}
                if sequence not in by_sequence:
                    metrics, constraints = evaluate(sequence, cds, host, request, engine, common_rules, source_ranks)
                    by_sequence[sequence] = {"candidate_id": "SEQ-" + sha[:12].upper(), "sequence": sequence, "sequence_sha256": sha,
                                             "protein": cds.protein, "metrics": metrics, "constraints": constraints,
                                             "changes": edits(cds.sequence, sequence), "strategy_memberships": []}
                    report["candidates"].append(by_sequence[sequence])
                by_sequence[sequence]["strategy_memberships"].append(membership)
            statuses[i] = status
        except Exception as exc:
            statuses[i] = {"strategy_id": strategy, "status": "failed", "reason": f"{type(exc).__name__}: {exc}", "returned_count": 0}
        publish()
    successful = {"completed", "budget_exhausted"}
    report["status"] = "cancelled" if cancelled() else ("completed" if all(s["status"] in successful for s in statuses) else "partial_results" if report["candidates"] else "no_results")
    report["run"]["elapsed_seconds"] = round(time.monotonic() - started, 4)
    report["run"]["unique_rna_contexts_including_reporting"] = len(engine.cache)
    report["run"]["reproducibility"] = "Stable SHA-256 sub-seeds and canonical order; wall-time interrupted runs can vary across hardware."
    for c in report["candidates"]:
        if c["constraints"]["repeats"]["count"]:
            report["warnings"].append(c["candidate_id"] + ": exact_repeats_present")
        if not c["constraints"]["repeats"]["scan_complete"]:
            report["warnings"].append(c["candidate_id"] + ": repeat_scan_incomplete")
    publish()
    return report
