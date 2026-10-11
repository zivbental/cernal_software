"""Distinct masks and provenance for each numerical metric."""
import math

from .sequence import AA, SYNONYMS, split_codons


def geometric(codons, weights, reference, reason=None):
    if weights is None:
        return {"value": None, "status": "unavailable", "reason": reason or "reference_unavailable", "reference": reference}
    if not codons:
        return {"value": None, "status": "unavailable", "reason": "no_scored_codons", "scored_codons": 0, "reference": reference}
    return {"value": math.exp(math.fsum(math.log(weights[c]) for c in codons) / len(codons)), "status": "ok", "reason": None,
            "scored_codons": len(codons), "reference": reference, "unit": "index"}


def comparable_positions(cds):
    return [i for i, c in enumerate(cds.codons) if i > 0 and c in AA and len(SYNONYMS[AA[c]]) > 1]


def evaluate(sequence, cds, host, request, engine, rules, source_ranks=None):
    cs = split_codons(sequence)
    # CAI excludes only a recognized start, stop and Met/Trp. tAI always excludes the fixed first position.
    cai_codons = [c for i, c in enumerate(cs) if c in AA and not (i == 0 and cds.standard_start) and AA[c] not in {"M", "W"}]
    sense_internal = [c for i, c in enumerate(cs) if i > 0 and c in AA]
    tai_key = "tai" if request["tai_model"] == "classic" else "stai"
    ref_id = host.host_id + "/" + host.manifest["reference_version"]
    metrics = {"cai": geometric(cai_codons, host.tables.get("cai"), ref_id + "/ribosomal", host.reasons.get("cai")),
               "tai": geometric(sense_internal, host.tables.get(tai_key), ref_id + "/" + tai_key, host.reasons.get(tai_key)),
               "host_preference": geometric(sense_internal, host.tables.get("host_preference"), ref_id + "/frozen_whole_CDS", host.reasons.get("host_preference")),
               "rna": engine.evaluate(sequence, request["upstream_transcribed_sequence"], request["rna_config"])}
    positions = comparable_positions(cds)
    if source_ranks is not None and "rank" in host.tables and positions:
        profile = [{"codon_position": i + 1, "source_rank": source_ranks[cds.codons[i]], "target_rank": host.tables["rank"][cs[i]]} for i in positions]
        metrics["harmonization"] = {"value": math.fsum(abs(p["target_rank"] - p["source_rank"]) for p in profile) / len(profile),
                                   "status": "ok", "scored_codons": len(profile), "method": "harmonize_rank_v1", "profile": profile}
    else:
        metrics["harmonization"] = {"value": None, "status": "unavailable", "reason": "source_reference_or_comparable_positions_missing"}
    constraints = rules.check(sequence)
    metrics["gc"] = {"value": constraints["coding_gc_fraction"] * 100, "unit": "%", "status": "ok", "nt_count": cds.sense_nt, "terminal_stop_excluded": True}
    return metrics, constraints
