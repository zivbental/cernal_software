"""Validated request schema. Unknown fields fail rather than being ignored."""
from copy import deepcopy
import math

from .sequence import CDS, InputError, normalize

STRATEGIES = {"rna_start": "5′ RNA accessibility", "host_sampling": "Host frequency sampling", "cai_max": "CAI priority", "tai_max": "tAI priority", "harmonize": "Codon harmonization"}
DEFAULT_BUDGET = {"sampling_attempts": 256, "rna_evaluations": 128, "max_transitions": 600000,
                  "max_frontier": 1200, "beam_width": 160, "wall_seconds": 40, "repair_evaluations": 48}


def number(value, field, lower, upper, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper or (integer and not isinstance(value, int)):
        raise InputError(f"{field} must be {'an integer' if integer else 'a number'} between {lower} and {upper}.", field)
    return value


def object_config(request, key, defaults):
    value = request.get(key, {})
    if not isinstance(value, dict) or set(value) - set(defaults):
        raise InputError(f"{key} contains unknown fields or has an invalid format.", key)
    return {**deepcopy(defaults), **value}


def validate_request(raw, refs):
    if not isinstance(raw, dict):
        raise InputError("The request must be a JSON object.", "request")
    allowed = {"cds", "host_id", "strategies", "upstream_transcribed_sequence", "source_host_id", "source_reference",
               "locked_codon_positions", "motif_policy", "gc_policy", "repeat_policy", "rna_config", "tai_model", "seed", "search_budget", "candidates_per_strategy"}
    if set(raw) - allowed:
        raise InputError("Unknown request fields: " + ", ".join(sorted(set(raw) - allowed)), "request")
    cds = CDS.parse(raw.get("cds", ""))
    host = refs.get(raw.get("host_id"))
    strategies = raw.get("strategies", ["rna_start", "host_sampling", "cai_max", "tai_max"])
    if not isinstance(strategies, list) or not strategies or any(not isinstance(s, str) or s not in STRATEGIES for s in strategies):
        raise InputError("Select at least one valid optimization preference.", "strategies")
    # Canonical scheduling order, independent random streams.
    strategies = [s for s in STRATEGIES if s in strategies]
    upstream, _, _ = normalize(raw.get("upstream_transcribed_sequence", ""), "upstream_transcribed_sequence", allow_empty=True, limit=300)
    locked = raw.get("locked_codon_positions", [])
    if not isinstance(locked, list):
        raise InputError("Locked positions must be a list of 1-based codon positions.", "locked_codon_positions")
    for p in locked:
        number(p, "locked_codon_positions", 1, len(cds.codons), True)
    locked = sorted(set(locked) | {1} | ({len(cds.codons)} if cds.terminal_stop else set()))
    motif = object_config(raw, "motif_policy", {"mode": "none", "custom": ""})
    if motif["mode"] not in ("none", "AGCAGY", "custom"):
        raise InputError("Unknown motif mode.", "motif_policy")
    if host.config["motif_policy"] == "AGCAGY_mandatory":
        motif = {"mode": "AGCAGY", "custom": ""}
    if motif["mode"] == "custom":
        value = motif["custom"]
        if not isinstance(value, str) or not 2 <= len(value) <= 32 or set(value.upper()) - set("ACGT"):
            raise InputError("A custom motif must be one A/C/G/T sequence of 2–32 nt.", "motif_policy")
        motif["custom"] = value.upper()
    gc = object_config(raw, "gc_policy", {"mode": "hard", "bounds": host.config["coding_gc_fraction_bounds"], "local_mode": "report", "local_bounds": [.3, .8], "local_window_nt": 60, "local_step_nt": 3})
    for mode in ("mode", "local_mode"):
        if gc[mode] not in ("hard", "report"):
            raise InputError("GC mode must be hard or report.", "gc_policy")
    for key in ("bounds", "local_bounds"):
        values = gc[key]
        if not isinstance(values, list) or len(values) != 2:
            raise InputError("GC bounds must contain two numbers between 0 and 1.", "gc_policy")
        for x in values:
            number(x, "gc_policy", 0, 1)
        if values[0] > values[1]:
            raise InputError("The lower GC bound cannot exceed the upper bound.", "gc_policy")
    number(gc["local_window_nt"], "local_window_nt", 3, 300, True)
    number(gc["local_step_nt"], "local_step_nt", 1, gc["local_window_nt"], True)
    repeat = object_config(raw, "repeat_policy", {"mode": "warn", **refs.defaults["repeat_thresholds"]})
    if repeat["mode"] not in ("warn", "repair", "strict"):
        raise InputError("Repeat mode must be warn, repair or strict.", "repeat_policy")
    for key in repeat:
        if key != "mode":
            number(repeat[key], key, 2, 100, True)
    if repeat["tandem_unit_min_nt"] > repeat["tandem_unit_max_nt"] or repeat["tandem_unit_max_nt"] > 12:
        raise InputError("Invalid tandem repeat unit range; the maximum is 12 nt.", "repeat_policy")
    rna = object_config(raw, "rna_config", {"temperature_c": 37., "context_cds_nt": 150, "target_start_nt": 1, "target_end_nt": 15, "mutable_start_codon": 2, "mutable_end_codon": 30})
    number(rna["temperature_c"], "temperature_c", 0, 80)
    number(rna["context_cds_nt"], "context_cds_nt", 15, 300, True)
    for key in ("target_start_nt", "target_end_nt"):
        number(rna[key], key, 1, rna["context_cds_nt"], True)
    if rna["target_start_nt"] > min(rna["target_end_nt"], len(cds.sequence)):
        raise InputError("The RNA target must start within the CDS and at or before its end position.", "rna_config")
    for key in ("mutable_start_codon", "mutable_end_codon"):
        number(rna[key], key, 2, 100, True)
    if rna["mutable_start_codon"] > rna["mutable_end_codon"]:
        raise InputError("Invalid mutable codon range for RNA optimization.", "rna_config")
    budget = object_config(raw, "search_budget", DEFAULT_BUDGET)
    maxima = {"sampling_attempts": 5000, "rna_evaluations": 1000, "max_transitions": 5000000, "max_frontier": 4000, "beam_width": 1000, "wall_seconds": 120, "repair_evaluations": 256}
    for key, value in budget.items():
        number(value, key, 1, maxima[key], key != "wall_seconds")
    if budget["beam_width"] > budget["max_frontier"]:
        raise InputError("beam_width cannot exceed max_frontier.", "search_budget")
    tai_model = raw.get("tai_model", "classic")
    if tai_model not in ("classic", "stai"):
        raise InputError("The tAI model must be classic or stai.", "tai_model")
    number(raw.get("seed", 42), "seed", 0, 2**32 - 1, True)
    count = raw.get("candidates_per_strategy", 1)
    if type(count) is not int or count != 1:
        raise InputError("Each preference returns one sequence; candidates_per_strategy only supports 1.", "candidates_per_strategy")
    source_ranks, source_metadata = refs.source(raw)
    request = {"cds": cds.sequence, "host_id": host.host_id, "strategies": strategies,
               "upstream_transcribed_sequence": upstream, "source_host_id": raw.get("source_host_id"),
               "source_reference": raw.get("source_reference"), "locked_codon_positions": locked,
               "motif_policy": motif, "gc_policy": gc, "repeat_policy": repeat, "rna_config": rna,
               "tai_model": tai_model, "seed": raw.get("seed", 42), "search_budget": budget,
               "candidates_per_strategy": 1}
    return request, cds, host, source_ranks, source_metadata
