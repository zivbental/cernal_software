"""Load only local frozen references. Never borrow another strain's weights."""
import csv
import hashlib
import json
import math
from pathlib import Path

from .sequence import AA, SYNONYMS, InputError, digest

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class HostReference:
    def __init__(self, root, host_id, config):
        self.host_id = host_id
        self.config = config
        folder = root / config["reference_directory"]
        self.manifest = read_json(folder / "manifest.json")
        if self.manifest["host_id"] != host_id or self.manifest["translation_table"] != 11:
            raise ValueError("Reference host / genetic code mismatch")
        self.tables = {}
        self.reasons = {}
        self.file_hashes = {}
        # Read separate frozen files: one missing metric must not disable the others.
        sources = {
            "sampling": ("host_codon_counts.csv", "codon", "sampling_probability_v1"),
            "host_preference": ("host_codon_counts.csv", "codon", "host_preference_v1"),
            "rank": ("codon_parameters.csv", "codon_dna", "harmonization_midrank_v1"),
            "cai": ("cai_weights.csv", "codon", "cai_weight"),
            "tai": ("tai_classic_weights.csv", "codon", "relative_w"),
            "stai": ("stai_weights.csv", "codon", "relative_w"),
        }
        for metric, (name, codon_key, value_key) in sources.items():
            try:
                raw = (folder / name).read_bytes()
                actual = hashlib.sha256(raw).hexdigest()
                if actual != self.manifest["output_sha256"].get(name):
                    raise ValueError("reference_checksum_mismatch")
                self.file_hashes[name] = actual
                rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
                # Frozen builders use codon_dna in some tables; accept only these known schemas.
                if codon_key not in rows[0]:
                    codon_key = "codon_dna"
                weights = {r[codon_key]: float(r[value_key]) for r in rows}
                if len(rows) != 61 or set(weights) != set(AA):
                    raise ValueError("incomplete_codon_coverage")
                if any(not math.isfinite(v) or v <= 0 or v > 1 for v in weights.values()):
                    raise ValueError("invalid_reference_weight")
                if metric == "sampling" and any(abs(sum(weights[c] for c in family) - 1) > 1e-9 for family in SYNONYMS.values()):
                    raise ValueError("sampling_probabilities_not_normalized")
                if metric in {"tai", "stai"} and abs(max(weights.values()) - 1) > 1e-9:
                    raise ValueError("tai_global_normalization_failed")
                self.tables[metric] = weights
            except (OSError, ValueError, KeyError, IndexError) as exc:
                self.reasons[metric] = f"{metric}_reference_unavailable: {exc}"

    def metadata(self):
        return {"host_id": self.host_id, "display_name": self.manifest["display_name"],
                "assembly": self.manifest["assembly"], "accession": self.manifest["accession"],
                "reference_version": self.manifest["reference_version"], "sources": self.manifest["sources"],
                "scoring_policies": self.manifest["scoring_policies"], "consumed_file_sha256": self.file_hashes,
                "capabilities": {key: {"available": key in self.tables, "reason": self.reasons.get(key)}
                                 for key in ["sampling", "host_preference", "rank", "cai", "tai", "stai"]},
                "motif_policy": self.config["motif_policy"], "gc_bounds": self.config["coding_gc_fraction_bounds"]}


class ReferenceStore:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.defaults = read_json(self.root / "config/defaults.json")
        self.hosts = {}
        for host_id, config in self.defaults["hosts"].items():
            self.hosts[host_id] = HostReference(self.root, host_id, config)

    def get(self, host_id):
        if not isinstance(host_id, str) or host_id not in self.hosts:
            raise InputError("Select an installed target host reference.", "host_id")
        return self.hosts[host_id]

    def source(self, request):
        source_id = request.get("source_host_id")
        custom = request.get("source_reference")
        if source_id and custom:
            raise InputError("Use either a built-in source host or a custom source reference, not both.", "source_reference")
        if source_id:
            ref = self.get(source_id)
            return ref.tables.get("rank"), ref.metadata()
        if custom:
            if not isinstance(custom, dict) or set(custom) - {"name", "counts"}:
                raise InputError("The source reference must contain a name and counts for 61 sense codons.", "source_reference")
            counts = custom.get("counts", {})
            if not isinstance(counts, dict) or set(counts) != set(AA):
                raise InputError("Custom source counts must cover all 61 sense codons using uppercase DNA letters.", "source_reference")
            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in counts.values()):
                raise InputError("Source counts must be finite, nonnegative numbers.", "source_reference")
            if any(sum(counts[c] for c in family) == 0 for family in SYNONYMS.values()):
                raise InputError("Every synonymous family must have a positive total source count.", "source_reference")
            ranks = {c: (sum(counts[d] < counts[c] for d in SYNONYMS[a]) + .5 * sum(counts[d] == counts[c] for d in SYNONYMS[a])) / len(SYNONYMS[a]) for c, a in AA.items()}
            canonical = json.dumps(counts, sort_keys=True, separators=(",", ":"))
            return ranks, {"name": str(custom.get("name", "custom_source"))[:200], "counts": counts,
                           "sha256": digest(canonical), "method": "whole_CDS_synonymous_family_midrank", "source": "user_supplied"}
        return None, None
