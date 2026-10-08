import dataclasses
import hashlib
import json
import platform
import runpy
import time
from pathlib import Path

from engine.domain import Constraints, Host
from engine.errors import InputValidationError
from engine.inputs import parse_dge_table
from engine.stages.genes import GeneSelector
from engine.stages.motifs import MotifScreener
from engine.transcriptome import load_transcriptome, resolve_gene_id

reference = runpy.run_path("tests/engine/test_gene_selection_performance.py")["reference_yield"]
source = Path("src/apps/expression/catalog/ecoli/92117__44313016.csv")
payload = source.read_bytes()
table = parse_dge_table(payload, source.name)
rows = []
for row in table.rows:
    try:
        identifier = resolve_gene_id(Host.ECOLI, row.gene_id)
    except InputValidationError:
        identifier = row.gene_id
    rows.append(dataclasses.replace(row, gene_id=identifier))
table = dataclasses.replace(table, rows=tuple(rows))
transcripts = load_transcriptome(Host.ECOLI)
constraints = Constraints(max_genes=3)


class MeasuredSelector(GeneSelector):
    calls = 0
    bases = 0
    legacy = False

    def _trigger_yield(self, transcript):
        self.calls += 1
        self.bases += len(transcript)
        return reference(self, transcript) if self.legacy else super()._trigger_yield(transcript)


measurements = {}
outputs = {}
warnings = {}
for name, legacy in (("original", True), ("optimized", False)):
    selector = MeasuredSelector(constraints, MotifScreener())
    selector.legacy = legacy
    messages = []
    start = time.perf_counter()
    result = selector.select(table, sequences=transcripts, on_warning=messages.append)
    elapsed = time.perf_counter() - start
    measurements[name] = {
        "seconds": elapsed,
        "transcripts_screened": selector.calls,
        "transcript_bases": selector.bases,
        "selected_genes": len(result),
    }
    outputs[name] = result
    warnings[name] = messages
    print(name, json.dumps(measurements[name]), flush=True)
assert outputs["original"] == outputs["optimized"]
assert warnings["original"] == warnings["optimized"]
report = {
    "catalog": str(source),
    "catalog_sha256": hashlib.sha256(payload).hexdigest(),
    "python": platform.python_version(),
    "input_rows": len(table.rows),
    "constraints": dataclasses.asdict(constraints),
    "measurements": measurements,
    "speedup": measurements["original"]["seconds"] / measurements["optimized"]["seconds"],
    "selected": [dataclasses.asdict(gene) for gene in outputs["optimized"]],
    "selection_and_warnings_identical": True,
    "budget_pruned_genes": 0,
    "policy": "Every eligible transcript is screened; no changed ranking or pre-pruning.",
}
Path("docs/qa/2026-10-08-gene-selection-performance.json").write_text(
    json.dumps(report, indent=2, default=str) + "\n"
)
print("speedup", report["speedup"], flush=True)
