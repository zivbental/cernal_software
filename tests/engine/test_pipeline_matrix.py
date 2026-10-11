"""Run every host/input/family combination through the real installed engine.

Unsupported combinations must return a useful terminal failure, never raise or hang.
This deliberately includes registered families whose advertised availability is broader
than the pipeline's current ability to construct them.
"""

import hashlib

import pytest

from engine.artifacts import sha256_file
from engine.client import LocalEngine
from engine.domain import Host
from engine.gates.registry import describe_families

TRIGGER = "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA"
TABLES = {
    "ecoli": "gene_id,log2fc,padj\nb3908,3.2,0.001\nb0033,-2.8,0.002\n",
    "human": "gene_id,log2fc,padj\nENSG00000201966,3.2,0.001\nENSG00000205361,-2.8,0.002\n",
    "c_acnes": "gene_id,log2fc,padj\nF6X01_RS12590,3.2,0.001\nF6X01_RS07220,-2.8,0.002\n",
    "yeast": "gene_id,log2fc,padj\nYDR281C,1.2,0.001\nYER085C,-1.4,0.002\n",
}
BUILDABLE = {
    "ecoli": {"toehold", "prokaryotic_toehold"},
    "yeast": {"toehold", "eukaryotic_toehold"},
    "c_acnes": {"toehold", "prokaryotic_toehold"},
    "human": {"toehold", "eukaryotic_toehold"},
}


@pytest.mark.parametrize("host", [h.value for h in Host])
@pytest.mark.parametrize("input_mode", ["direct", "de", "gene"])
@pytest.mark.parametrize("family", [f.name for f in describe_families()])
def test_real_pipeline_combination(host, input_mode, family, make_request, tmp_path):
    table = TABLES.get(host, TABLES["ecoli"])
    path = tmp_path / "matrix.csv"
    path.write_text(table)
    request = make_request(
        organism=host,
        params={"target_gene": {"gene_id": TABLES[host].splitlines()[1].split(",")[0]}},
        input_mode=input_mode,
        gate_families=[family],
        trigger_sequence=TRIGGER if input_mode == "direct" else "",
        input_path=str(path) if input_mode == "de" else "",
        input_checksum=hashlib.sha256(table.encode()).hexdigest() if input_mode == "de" else "",
    )
    progress = []

    def report(percent, stage):
        progress.append((percent, stage))
        return True

    result = LocalEngine().run(request, report)

    assert progress
    supported = family in BUILDABLE.get(host, set())
    if supported:
        assert result.status == "succeeded", result.error
        assert result.error is None
        assert result.candidates
        assert result.artifacts
        assert progress[-1][0] == 100
        assert [p for p, _ in progress] == sorted(p for p, _ in progress)
        for artifact in result.artifacts:
            assert sha256_file(tmp_path / "out-default" / artifact.path) == artifact.checksum_sha256
    else:
        assert result.status == "failed"
        assert result.error
        assert not result.candidates
