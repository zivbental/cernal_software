"""FASTA, CSV and JSON share canonical sequence IDs and all strategy memberships."""
import csv
from io import StringIO
import json


def subset(report, ids=None):
    if ids is None:
        return report
    valid = {c["candidate_id"] for c in report["candidates"]}
    if not set(ids) <= valid:
        raise ValueError("Unknown candidate ID")
    selected = [c for c in report["candidates"] if c["candidate_id"] in set(ids)]
    return {**report, "candidates": selected, "export": {"selected_ids": [c["candidate_id"] for c in selected], "deduplicated": True,
                                                         "note": "Strategy status counts describe the complete run; candidates contains this selection."}}


def export(report, format, ids=None):
    result = subset(report, ids)
    if format == "json":
        return json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", "application/json; charset=utf-8"
    if format == "fasta":
        lines = []
        for c in result["candidates"]:
            tags = ",".join(m["strategy_id"] for m in c["strategy_memberships"])
            lines.append(f">{c['candidate_id']} host={report['run']['config']['host_id']} strategies={tags} sha256={c['sequence_sha256']}")
            lines.extend(c["sequence"][i:i + 80] for i in range(0, len(c["sequence"]), 80))
        return "\n".join(lines) + ("\n" if lines else ""), "text/plain; charset=utf-8"
    if format == "csv":
        stream = StringIO(newline="")
        fields = ["candidate_id", "strategies", "sequence_sha256", "length_nt", "changed_codons", "protein_unchanged", "constraints_passed",
                  "cai", "cai_reason", "tai", "tai_reason", "rna_opening_kcal_mol", "rna_reason", "rna_context_mode", "coding_gc_percent",
                  "harmonization_error", "repeat_count", "repeat_scan_complete", "motif_matches", "cai_delta", "tai_delta", "rna_delta", "reference_version", "seed"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for c in [result["original_result"]] + result["candidates"]:
            m, constraints = c["metrics"], c["constraints"]
            row = {"candidate_id": c["candidate_id"], "strategies": ";".join(x["strategy_id"] for x in c["strategy_memberships"]) or "original_input",
                   "sequence_sha256": c["sequence_sha256"], "length_nt": len(c["sequence"]), "changed_codons": len(c["changes"]),
                   "protein_unchanged": constraints["protein_unchanged"], "constraints_passed": constraints["passed"],
                   "cai": m["cai"]["value"], "cai_reason": m["cai"].get("reason"), "tai": m["tai"]["value"], "tai_reason": m["tai"].get("reason"),
                   "rna_opening_kcal_mol": m["rna"]["value"], "rna_reason": m["rna"].get("reason"), "rna_context_mode": m["rna"].get("context_mode"),
                   "coding_gc_percent": m["gc"]["value"], "harmonization_error": m["harmonization"]["value"],
                   "repeat_count": constraints["repeats"]["count"], "repeat_scan_complete": constraints["repeats"]["scan_complete"],
                   "motif_matches": len(constraints["motif_matches"]), "reference_version": report["run"]["reference_version"], "seed": report["run"]["config"]["seed"]}
            for key in ("cai", "tai", "rna"):
                before, after = result["original_result"]["metrics"][key]["value"], m[key]["value"]
                row[key + "_delta"] = after - before if before is not None and after is not None else None
            writer.writerow(row)
        return "\ufeff" + stream.getvalue(), "text/csv; charset=utf-8"
    raise ValueError("Export format must be fasta, csv or json")
