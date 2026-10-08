"""Joint opening energy from two independent ensemble partition functions."""
import hashlib
import math
import threading

from .references import read_json

_LOCK = threading.Lock()


class RNAEngine:
    def __init__(self, root, disabled=False):
        self.cache = {}
        self.reason = None
        self.config = {}
        try:
            if disabled:
                raise ImportError("rna_engine_disabled")
            import RNA
            self.RNA = RNA
            self.config = read_json(root / "config/rna_model.json")
            self.parameter_file = root / self.config["energy_parameter_file"]
            actual = hashlib.sha256(self.parameter_file.read_bytes()).hexdigest()
            if actual != self.config["energy_parameter_sha256"]:
                raise ValueError("rna_parameter_checksum_mismatch")
            if RNA.__version__ != self.config["viennarna_version"]:
                raise ValueError(f"rna_version_mismatch: expected {self.config['viennarna_version']}, found {RNA.__version__}")
        except (ImportError, OSError, ValueError, KeyError) as exc:
            self.reason = str(exc)

    def evaluate(self, cds, upstream, config):
        if self.reason:
            return {"value": None, "status": "unavailable", "reason": self.reason, "unit": "kcal/mol"}
        prefix = cds[:config["context_cds_nt"]]
        context = (upstream + prefix).replace("T", "U")
        start = len(upstream) + config["target_start_nt"] - 1
        end = len(upstream) + min(config["target_end_nt"], len(prefix))
        key = (context, start, end, config["temperature_c"], self.config["energy_parameter_sha256"], self.config["viennarna_version"])
        if key in self.cache:
            return self.cache[key]
        try:
            if not 0 <= start < end <= len(context):
                raise ValueError("rna_target_outside_context")
            with _LOCK:
                if not self.RNA.params_load(str(self.parameter_file)):
                    raise RuntimeError("rna_parameter_load_failed")
                g_all, mfe, structure = self.ensemble(context, [], config["temperature_c"])
                g_open, _, open_structure = self.ensemble(context, range(start, end), config["temperature_c"])
            delta = g_open - g_all
            if delta < -self.config["energy_difference_tolerance_kcal_mol"]:
                raise ArithmeticError("negative_opening_energy")
            value = max(0., delta)
            log_p = -value / (self.config["R_kcal_mol_K"] * (config["temperature_c"] + 273.15))
            result = {"value": value, "status": "ok", "reason": None, "unit": "kcal/mol",
                      "p_open": math.exp(log_p), "log_p_open": log_p, "ensemble_all": g_all, "ensemble_open": g_open,
                      "mfe": mfe, "mfe_structure": structure, "constrained_mfe_structure": open_structure,
                      "context_rna": context, "context_mode": "upstream_and_cds" if upstream else "cds_only",
                      "upstream_nt": len(upstream), "actual_cds_context_nt": len(prefix),
                      "target_context_nt": [start + 1, end], "target_cds_nt": [config["target_start_nt"], end - len(upstream)],
                      "temperature_c": config["temperature_c"], "model": self.config["model_id"],
                      "engine_version": self.config["viennarna_version"], "parameter_sha256": self.config["energy_parameter_sha256"],
                      "roundoff_clamped": delta < 0}
        except Exception as exc:
            result = {"value": None, "status": "failed", "reason": f"rna_calculation_failed: {exc}", "unit": "kcal/mol"}
        # Request-local, bounded by the server's evaluation limits.
        self.cache[key] = result
        return result

    def ensemble(self, context, positions, temperature):
        RNA = self.RNA
        md = RNA.md()
        md.temperature, md.dangles, md.compute_bpp = temperature, 2, 0
        md.betaScale, md.salt = 1., self.config["salt_molar"]
        md.noLP = md.noGU = md.noGUclosure = md.gquad = md.circ = 0
        md.max_bp_span = -1
        fc = RNA.fold_compound(context, md)
        positions = list(positions)
        if positions:
            constraint = ["."] * len(context)
            for pos in positions:
                constraint[pos] = "x"
            if not fc.hc_add_from_db("".join(constraint), RNA.CONSTRAINT_DB_DEFAULT):
                raise RuntimeError("rna_constraint_rejected")
        structure, mfe = fc.mfe()
        fc.exp_params_rescale(mfe)
        _, ensemble = fc.pf()
        if not math.isfinite(ensemble) or abs(ensemble) > 100000:
            raise ArithmeticError("invalid_ensemble_energy")
        return float(ensemble), float(mfe), structure
