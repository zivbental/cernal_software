"""Shared sequence constraints; motif matching includes overlaps and both strands."""
from collections import defaultdict
import math

from .sequence import AA, SYNONYMS, split_codons, translate


def reverse_complement(s):
    return s.translate(str.maketrans("ACGT", "TGCA"))[::-1]


class MotifAutomaton:
    def __init__(self, policy):
        forward = [] if policy["mode"] == "none" else (["AGCAGC", "AGCAGT"] if policy["mode"] == "AGCAGY" else [policy["custom"]])
        self.forward = tuple(forward)
        self.patterns = tuple(sorted(set(forward + [reverse_complement(m) for m in forward])))
        prefixes = {""} | {m[:i] for m in self.patterns for i in range(1, len(m))}
        states = sorted(prefixes, key=lambda x: (len(x), x))
        lookup = {s: i for i, s in enumerate(states)}
        self.transitions = {}
        for i, prefix in enumerate(states):
            for base in "ACGT":
                text = prefix + base
                matches = tuple(m for m in self.patterns if text.endswith(m))
                suffix = max((p for p in states if text.endswith(p)), key=len)
                self.transitions[i, base] = (lookup[suffix], matches)
        self.codon_transitions = {}
        for state in range(len(states)):
            for codon in list(AA) + ["TAA", "TAG", "TGA"]:
                q, hit = state, False
                for b in codon:
                    q, matches = self.transitions[q, b]
                    hit |= bool(matches)
                self.codon_transitions[state, codon] = (q, hit)

    def scan(self, sequence):
        matches, state = [], 0
        for i, base in enumerate(sequence):
            state, hits = self.transitions[state, base]
            for motif in hits:
                strands = (["+"] if motif in self.forward else []) + (["-"] if reverse_complement(motif) in self.forward else [])
                matches.append({"start_nt": i - len(motif) + 2, "end_nt": i + 1, "motif": motif, "strands": strands})
        return matches


def local_gc(sequence, window=60, step=3):
    n = len(sequence)
    starts = list(range(0, max(1, n - window + 1), step))
    if n >= window and starts[-1] != n - window:
        starts.append(n - window)
    prefix = [0]
    for b in sequence:
        prefix.append(prefix[-1] + (b in "GC"))
    return [{"start_nt": s + 1, "end_nt": min(n, s + window),
             "gc_fraction": (prefix[min(n, s + window)] - prefix[s]) / (min(n, s + window) - s)} for s in starts]


def detect_repeats(sequence, policy, pair_limit=30000, hit_limit=500):
    """Exact repeats, maximal extension and explicit bounds on pathological inputs."""
    n, hits = len(sequence), []
    i = 0
    while i < n:
        j = i + 1
        while j < n and sequence[j] == sequence[i]:
            j += 1
        if j - i >= policy["homopolymer_min_nt"]:
            hits.append({"type": "homopolymer", "start_nt": i + 1, "end_nt": j, "unit": sequence[i], "copies": j - i})
        i = j
    for size in range(policy["tandem_unit_min_nt"], policy["tandem_unit_max_nt"] + 1):
        i = 0
        while i + size * policy["tandem_min_copies"] <= n:
            unit = sequence[i:i + size]
            # A nonprimitive unit describes a smaller repeat already enumerated.
            if any(size % k == 0 and unit == unit[:k] * (size // k) for k in range(1, size)):
                i += 1
                continue
            end = i + size
            while end + size <= n and sequence[end:end + size] == unit:
                end += size
            copies = (end - i) // size
            if copies >= policy["tandem_min_copies"] and end - i >= policy["tandem_min_total_nt"]:
                hits.append({"type": "tandem", "start_nt": i + 1, "end_nt": end, "unit": unit, "copies": copies})
                i = end - size + 1
            else:
                i += 1
    seed = policy["direct_repeat_min_nt"]
    index, groups, comparisons, complete = defaultdict(list), {}, 0, True
    for j in range(n - seed + 1):
        token = sequence[j:j + seed]
        for i in index[token]:
            comparisons += 1
            if comparisons > pair_limit or len(groups) + len(hits) >= hit_limit:
                complete = False
                break
            if j - i < seed or (i > 0 and sequence[i - 1] == sequence[j - 1]):
                continue
            length = seed
            # Do not count overlapping copies as dispersed direct repeats.
            while length < j - i and j + length < n and sequence[i + length] == sequence[j + length]:
                length += 1
            repeated = sequence[i:i + length]
            groups.setdefault(repeated, set()).update([i, j])
        if not complete:
            break
        index[token].append(j)
    direct = sorted(groups.items(), key=lambda item: (-len(item[0]), sorted(item[1])))
    retained = []
    for text, positions in direct:
        if any(all(any(a <= p and p + len(text) <= a + len(t) for a in ps) for p in positions) for t, ps in retained):
            continue
        retained.append((text, positions))
        starts = sorted(positions)
        hits.append({"type": "direct", "start_nt": starts[0] + 1, "end_nt": starts[0] + len(text),
                     "length_nt": len(text), "positions": [{"start_nt": p + 1, "end_nt": p + len(text)} for p in starts]})
    if len(hits) > hit_limit:
        hits, complete = hits[:hit_limit], False
    return {"count": len(hits), "hits": hits, "scan_complete": complete,
            "reason": None if complete else "repeat_scan_budget_exhausted", "definition": "exact_homopolymer_tandem_nonoverlapping_direct"}


class Rules:
    def __init__(self, cds, request, strategy=None):
        self.cds, self.request = cds, request
        self.motif = MotifAutomaton(request["motif_policy"])
        locked = {p - 1 for p in request["locked_codon_positions"]}
        if strategy == "rna_start":
            rc = request["rna_config"]
            locked.update(i for i in range(len(cds.codons)) if not rc["mutable_start_codon"] - 1 <= i < rc["mutable_end_codon"])
        self.locked = locked
        self.options = [tuple([c]) if i in locked else SYNONYMS[AA[c]] for i, c in enumerate(cds.codons)]
        self.mutable = [i for i, opts in enumerate(self.options) if len(opts) > 1]
        bounds = request["gc_policy"]["bounds"] if request["gc_policy"]["mode"] == "hard" else [0, 1]
        self.gc_min = math.ceil(bounds[0] * cds.sense_nt - 1e-9)
        self.gc_max = math.floor(bounds[1] * cds.sense_nt + 1e-9)

    def check(self, sequence, repeats=True, include_details=True):
        cs = split_codons(sequence)
        violations = []
        if len(sequence) != len(self.cds.sequence) or translate(sequence) != self.cds.protein:
            violations.append("protein_or_length_changed")
        if any(i >= len(cs) or cs[i] != self.cds.codons[i] for i in self.locked):
            violations.append("locked_codon_changed")
        matches = self.motif.scan(sequence)
        if matches:
            violations.append("forbidden_motif")
        sense = sequence[:self.cds.sense_nt]
        gc_count = sense.count("G") + sense.count("C")
        if not self.gc_min <= gc_count <= self.gc_max:
            violations.append("coding_gc_out_of_bounds")
        gc = self.request["gc_policy"]
        windows = local_gc(sense, gc["local_window_nt"], gc["local_step_nt"]) if include_details or gc["local_mode"] == "hard" else []
        if gc["local_mode"] == "hard" and any(not gc["local_bounds"][0] - 1e-12 <= w["gc_fraction"] <= gc["local_bounds"][1] + 1e-12 for w in windows):
            violations.append("local_gc_out_of_bounds")
        repeat = detect_repeats(sequence, self.request["repeat_policy"]) if repeats else None
        if repeats and self.request["repeat_policy"]["mode"] == "strict" and (repeat["count"] or not repeat["scan_complete"]):
            violations.append("strict_repeat_constraint")
        return {"passed": not violations, "violations": violations, "protein_unchanged": translate(sequence) == self.cds.protein,
                "locked_positions_unchanged": "locked_codon_changed" not in violations, "motif_matches": matches,
                "coding_gc_fraction": gc_count / self.cds.sense_nt, "coding_gc_nt": self.cds.sense_nt,
                "local_gc": windows, "repeats": repeat}

    def quick(self, sequence):
        return self.check(sequence, repeats=False, include_details=False)["passed"]
