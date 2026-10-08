"""Bounded independent searches; exact claims apply only to the modeled DP problem."""
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import math
import random
import time

from .constraints import Rules, detect_repeats
from .metrics import comparable_positions
from .sequence import AA, split_codons, digest


def sub_seed(seed, name):
    return int.from_bytes(hashlib.sha256(f"codon-v2:{seed}:{name}".encode()).digest()[:8], "big")


class SearchStopped(Exception):
    pass


@dataclass
class Budget:
    config: dict
    cancelled: object = lambda: False
    started: float = field(default_factory=time.monotonic)
    counts: dict = field(default_factory=lambda: {"transitions": 0, "sampling_attempts": 0, "rna_evaluations": 0, "repair_evaluations": 0})
    reason: str = "search_completed"
    rna_contexts: set = field(default_factory=set)

    def check(self):
        if self.cancelled():
            self.reason = "cancelled"
            raise SearchStopped(self.reason)
        if time.monotonic() - self.started >= self.config["wall_seconds"]:
            self.reason = "wall_time_limit"
            raise SearchStopped(self.reason)

    def consume(self, key, amount=1):
        self.check()
        limit_key = "max_transitions" if key == "transitions" else key
        if self.counts[key] + amount > self.config[limit_key]:
            self.reason = key + "_limit"
            raise SearchStopped(self.reason)
        self.counts[key] += amount

    def report(self):
        return {**self.counts, "unique_rna_contexts": len(self.rna_contexts),
                "elapsed_seconds": round(time.monotonic() - self.started, 4), "termination_reason": self.reason}


def objective_terms(strategy, cds, host, request, source_ranks=None):
    key = "tai" if request["tai_model"] == "classic" else "stai"
    comparable = set(comparable_positions(cds))
    result = []
    for i, original in enumerate(cds.codons):
        scores = {}
        for c in AA:
            score = 0.
            if strategy == "cai_max" and not (i == 0 and cds.standard_start) and AA[c] not in {"M", "W"}:
                score = math.log(host.tables["cai"][c])
            elif strategy == "tai_max" and i > 0:
                score = math.log(host.tables[key][c])
            elif strategy == "harmonize" and i in comparable:
                score = -abs(host.tables["rank"][c] - source_ranks[original])
            scores[c] = score
        scores.update({c: 0. for c in ("TAA", "TAG", "TGA")})
        result.append(scores)
    return result


def additive_dp(rules, terms, budget, keep=5):
    """K-best paths per (GC count, motif state), bounded beam fallback.

    Local GC and exact-repeat predicates are final filters, not DP states. The
    caller never claims a full-problem optimum when those hard predicates apply.
    """
    options, n = rules.options, len(rules.options)
    min_remaining, max_remaining = [0] * (n + 1), [0] * (n + 1)
    gc_cost = [{c: c.count("G") + c.count("C") if i * 3 < rules.cds.sense_nt else 0 for c in opts} for i, opts in enumerate(options)]
    for i in range(n - 1, -1, -1):
        min_remaining[i] = min_remaining[i + 1] + min(gc_cost[i].values())
        max_remaining[i] = max_remaining[i + 1] + max(gc_cost[i].values())
    states = {(0, 0): [(0., 0, "")]}
    pruned, peak = False, 1
    order = lambda p: (-p[0], p[1], p[2])
    try:
        for i, opts in enumerate(options):
            next_states = defaultdict(list)
            for (gc, state), paths in sorted(states.items()):
                for c in opts:
                    q, hit = rules.motif.codon_transitions[state, c]
                    g = gc + gc_cost[i][c]
                    if hit or g + min_remaining[i + 1] > rules.gc_max or g + max_remaining[i + 1] < rules.gc_min:
                        continue
                    for score, changes, prefix in paths:
                        budget.consume("transitions")
                        path = (score + terms[i][c], changes + (c != rules.cds.codons[i]), prefix + c)
                        bucket = next_states[g, q]
                        bucket.append(path)
                        if len(bucket) > keep:
                            bucket.sort(key=order)
                            del bucket[keep:]
            peak = max(peak, sum(len(v) for v in next_states.values()))
            # Bound path count as well as state count.
            if sum(len(v) for v in next_states.values()) > budget.config["max_frontier"]:
                pruned = True
                best = sorted(((key, p) for key, paths in next_states.items() for p in paths), key=lambda item: order(item[1]))[:budget.config["beam_width"]]
                next_states = defaultdict(list)
                for key, p in best:
                    next_states[key].append(p)
            states = next_states
            if not states:
                return [], {"solver": "beam_approx" if pruned else "dp_exact", "complete": True, "peak_paths": peak, "empty": True}
    except SearchStopped:
        return [], {"solver": "beam_approx" if pruned else "dp_interrupted", "complete": False, "peak_paths": peak, "empty": False}
    final = sorted((p for paths in states.values() for p in paths), key=order)
    return [p[2] for p in final[:max(keep * 5, 20)]], {"solver": "beam_approx" if pruned else "dp_exact", "complete": True, "peak_paths": peak, "empty": not final}


def draw_sample(rules, probabilities, rng):
    return "".join(opts[0] if len(opts) == 1 else rng.choices(opts, weights=[probabilities[c] for c in opts], k=1)[0] for opts in rules.options)


def seed_pool(cds, request, host, cancelled):
    """Built identically regardless of the selected strategy set."""
    rng = random.Random(sub_seed(request["seed"], "shared_seeds"))
    common, local = Rules(cds, request), Rules(cds, request, "rna_start")
    seeds = {}
    if common.quick(cds.sequence):
        seeds[cds.sequence] = "original"
    started = time.monotonic()
    attempts = 0
    stop_reason, fallback = "attempt_limit", None
    if "sampling" in host.tables:
        for i in range(64):
            if cancelled() or time.monotonic() - started > 5:
                stop_reason = "cancelled" if cancelled() else "wall_time_limit"
                break
            for rules, label in [(common, "shared_host_sampling"), (local, "shared_start_sampling")]:
                s = draw_sample(rules, host.tables["sampling"], rng)
                attempts += 1
                if rules.quick(s):
                    seeds.setdefault(s, label)
            if len(seeds) >= 16:
                stop_reason = "seed_pool_full"
                break
    # A constrained DP fallback works even when rejection sampling finds no seed.
    if not seeds:
        b = Budget({**request["search_budget"], "max_transitions": min(60000, request["search_budget"]["max_transitions"]), "wall_seconds": 5}, cancelled)
        terms = [{c: 0. for c in list(AA) + ["TAA", "TAG", "TGA"]} for _ in cds.codons]
        paths, dp_status = additive_dp(common, terms, b, keep=1)
        fallback = {**dp_status, "budget": b.report()}
        for s in paths:
            if common.quick(s):
                seeds.setdefault(s, "shared_feasibility_dp")
    return [{"sequence": s, "sha256": digest(s), "source": source} for s, source in seeds.items()], {"attempts": attempts, "elapsed_seconds": round(time.monotonic() - started, 4), "seed": sub_seed(request["seed"], "shared_seeds"), "termination_reason": stop_reason, "feasibility_fallback": fallback}


def codon_distance(a, b, mutable):
    if not mutable:
        return 0.
    return sum(a[i * 3:i * 3 + 3] != b[i * 3:i * 3 + 3] for i in mutable) / len(mutable)


def select_diverse(sequences, score, rules, count, sampling=False):
    sequences = list(dict.fromkeys(sequences))
    if not sequences:
        return []
    ordered = sequences if sampling else sorted(sequences, key=lambda s: (-score(s), sum(a != b for a, b in zip(split_codons(s), rules.cds.codons)), s))
    remaining = ordered[:max(25, count * 5)] if not sampling else ordered
    selected = [remaining.pop(0)]
    while remaining and len(selected) < count:
        best = min(remaining, key=lambda s: (-min(codon_distance(s, chosen, rules.mutable) for chosen in selected), -score(s) if not sampling else 0, s))
        selected.append(best)
        remaining.remove(best)
    return selected


def repair_repeat(sequence, rules, score, rng, budget):
    before = detect_repeats(sequence, rules.request["repeat_policy"])
    record = {"mode": rules.request["repeat_policy"]["mode"], "before": before["count"], "after": before["count"], "changes": 0, "reason": None}
    if record["mode"] == "warn" or not before["count"]:
        return sequence, record
    def penalty(report):
        return (not report["scan_complete"], report["count"], sum(h["end_nt"] - h["start_nt"] + 1 for h in report["hits"]))
    original_score = score(sequence)
    current, current_report = sequence, before
    try:
        for _ in range(3):
            areas = [p for h in current_report["hits"] for p in h.get("positions", [h])]
            positions = [i for i in rules.mutable if any(3 * i < p["end_nt"] and 3 * i + 3 >= p["start_nt"] for p in areas)]
            if not positions:
                record["reason"] = "repeat_unresolved_locked_region"
                break
            proposals = []
            rng.shuffle(positions)
            for i in positions:
                for c in rules.options[i]:
                    if c != current[3 * i:3 * i + 3]:
                        proposals.append(current[:3 * i] + c + current[3 * i + 3:])
            # Reserve part of the budget for two-position changes when needed.
            for _ in range(min(8, len(positions))):
                if len(positions) < 2:
                    break
                cs = list(split_codons(current))
                for i in rng.sample(positions, 2):
                    cs[i] = rng.choice(rules.options[i])
                proposals.insert(0, "".join(cs))
            improvement = None
            for proposed in proposals:
                budget.consume("repair_evaluations")
                if not rules.quick(proposed) or score(proposed) + 1e-12 < original_score:
                    continue
                report = detect_repeats(proposed, rules.request["repeat_policy"])
                if penalty(report) < penalty(current_report):
                    improvement = proposed, report
                    break
            if not improvement:
                record["reason"] = "no_non_degrading_repair_found"
                break
            current, current_report = improvement
            if not current_report["count"]:
                break
    except SearchStopped:
        record["reason"] = "repair_budget_exhausted"
    record.update(after=current_report["count"], changes=sum(a != b for a, b in zip(split_codons(sequence), split_codons(current))))
    return current, record


def run_strategy(strategy, cds, host, request, engine, seeds, source_ranks, cancelled=lambda: False):
    rules = Rules(cds, request, strategy)
    rng = random.Random(sub_seed(request["seed"], strategy))
    budget = Budget(request["search_budget"], cancelled)
    initial = [s["sequence"] for s in seeds if rules.quick(s["sequence"])]
    candidates, scores, origins = [], {}, {s: digest(s) for s in initial}
    terms = objective_terms(strategy, cds, host, request, source_ranks)
    solver = {"solver": "host_frequency_rejection_sampling" if strategy == "host_sampling" else "rna_pool_search", "complete": False}

    def score(sequence):
        if sequence in scores:
            return scores[sequence]
        if strategy == "rna_start":
            rc = request["rna_config"]
            key = sequence[:rc["context_cds_nt"]]
            if key not in budget.rna_contexts:
                budget.consume("rna_evaluations")
                budget.rna_contexts.add(key)
            metric = engine.evaluate(sequence, request["upstream_transcribed_sequence"], rc)
            if metric["value"] is None:
                raise RuntimeError(metric["reason"])
            value = -metric["value"]
        else:
            value = math.fsum(terms[i][c] for i, c in enumerate(split_codons(sequence)))
        scores[sequence] = value
        return value

    try:
        if strategy == "host_sampling":
            candidates = [s["sequence"] for s in seeds if s["source"] == "shared_host_sampling"]
            for _ in range(budget.config["sampling_attempts"]):
                budget.consume("sampling_attempts")
                sequence = draw_sample(rules, host.tables["sampling"], rng)
                if rules.quick(sequence):
                    candidates.append(sequence)
            solver["complete"] = True
        elif strategy in {"cai_max", "tai_max", "harmonize"}:
            # Keep the existing internal search breadth even though only one result is delivered.
            candidates, solver = additive_dp(rules, terms, budget, keep=5)
            for sequence in candidates:
                origins[sequence] = None  # A positional DP path is not a mutation of a seed.
            candidates = [s for s in candidates if rules.quick(s)] + initial
        else:
            if not initial:
                # The RNA strategy must not modify distant codons to repair constraints.
                initial, seed_solver = additive_dp(rules, terms, budget, keep=1)
                solver["feasibility_solver"] = seed_solver
                solver["local_seed_sequences"] = [{"sequence": s, "sha256": digest(s)} for s in initial]
            pool = []
            for sequence in initial:
                if rules.quick(sequence):
                    score(sequence)
                    pool.append(sequence)
                    candidates.append(sequence)
                    origins[sequence] = digest(sequence)
            seen = set(pool)
            max_proposals = budget.config["rna_evaluations"] * 25
            for _ in range(max_proposals):
                budget.check()
                if not pool or not rules.mutable:
                    break
                parent = rng.choice(pool)
                cs = list(split_codons(parent))
                for i in rng.sample(rules.mutable, min(len(rules.mutable), rng.choice([1, 1, 1, 2, 3]))):
                    cs[i] = rng.choice(rules.options[i])
                sequence = "".join(cs)
                if sequence in seen:
                    continue
                seen.add(sequence)
                if not rules.quick(sequence):
                    continue
                score(sequence)
                candidates.append(sequence)
                origins[sequence] = origins.get(parent, digest(parent))
                pool.append(sequence)
                if len(pool) > 24:
                    ordered = sorted(pool, key=lambda s: (-scores[s], s))
                    pool = ordered[:20] + rng.sample(ordered[20:], min(4, len(ordered) - 20))
            solver["complete"] = True
    except SearchStopped:
        pass
    raw_count = len(set(candidates))
    # Diversity must not turn an optimization preference into a worse-than-baseline result.
    # If the original violates a hard constraint, that baseline floor does not apply.
    baseline_floor = None
    if strategy != "host_sampling" and rules.check(cds.sequence)["passed"]:
        baseline_floor = score(cds.sequence)
        candidates = [s for s in candidates if score(s) + 1e-12 >= baseline_floor]
    # Check/filter every proposed final result; a seed that violates strict repeats is not a candidate.
    shortlist = select_diverse(candidates, score, rules, 15, strategy == "host_sampling")
    repaired, repair_records = [], {}
    for sequence in shortlist:
        if cancelled():
            budget.reason = "cancelled"
            break
        variant, record = repair_repeat(sequence, rules, score, rng, budget)
        if rules.check(variant)["passed"]:
            repaired.append(variant)
            repair_records[variant] = record
            origins.setdefault(variant, origins.get(sequence))
    selected = select_diverse(repaired, score, rules, 1, strategy == "host_sampling")
    extra_hard = request["gc_policy"]["local_mode"] == "hard" or request["repeat_policy"]["mode"] == "strict"
    guarantee = "none"
    if solver["solver"] == "dp_exact" and solver["complete"] and not extra_hard:
        guarantee = "additive_objective_optimal_under_motif_global_gc_locks" if selected else "infeasible_under_motif_global_gc_locks"
    if budget.reason == "cancelled":
        status = "cancelled"
    elif selected:
        status = "budget_exhausted" if budget.reason != "search_completed" else "completed"
    elif solver.get("empty") and guarantee.startswith("infeasible"):
        status = "infeasible_proven"
    else:
        status = "no_feasible_candidate_found"
    return selected, {"strategy_id": strategy, "status": status, "seed": sub_seed(request["seed"], strategy),
                      **solver, "guarantee": guarantee, "found_count": raw_count, "returned_count": len(selected),
                      "baseline_objective_floor": baseline_floor,
                      "budget": budget.report(), "mutable_codon_positions": [i + 1 for i in rules.mutable],
                      "candidate_provenance": {digest(s): {"initial_sequence_sha256": origins.get(s), "repair": repair_records[s],
                                                           "template_sequence_sha256": digest(cds.sequence),
                                                           "initialization": "seed_pool" if origins.get(s) else "independent_frequency_draw" if strategy == "host_sampling" else "positional_dp",
                                                           "objective_value": score(s)} for s in selected}}
