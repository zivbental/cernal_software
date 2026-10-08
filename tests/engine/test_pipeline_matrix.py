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
#: Families that run AND produce candidates on these fixtures.
BUILDABLE = {
    "ecoli": {"toehold", "prokaryotic_toehold"},
    "yeast": {"toehold", "eukaryotic_toehold"},
    "c_acnes": {"toehold", "prokaryotic_toehold"},
    "human": {"toehold", "eukaryotic_toehold"},
}

#: Families that RUN without failing but may produce nothing on a given input -- a third outcome
#: the binary map above cannot express. The two-input AND family is reachable on every host (its
#: `generate_designs` has a body on this branch) and yields nothing on these one-gene fixtures,
#: because `build_trigger_sets` has no second candidate to pair. On the eukaryotic hosts it also
#: emits no AND candidates at all, which is `is_compatible` refusing the track: the loop hardcodes
#: the prokaryotic Shine-Dalgarno, so a eukaryotic design would carry no Kozak.
REACHABLE = {
    host: families | {"toehold_and", "prokaryotic_toehold_and"}
    for host, families in BUILDABLE.items()
}


@pytest.mark.parametrize("host", [h.value for h in Host])
@pytest.mark.parametrize("input_mode", ["direct", "de", "gene"])
@pytest.mark.parametrize("family", [f.name for f in describe_families()])
def test_real_pipeline_combination(host, input_mode, family, make_request, tmp_path):
    table = TABLES.get(host, TABLES["ecoli"])
    path = tmp_path / "matrix.csv"
    # The bytes written must be the bytes hashed. `write_text` translates newlines to
    # the platform ending, so on Windows the file gets CRLF while `input_checksum`
    # below is taken over the LF string -- and the engine then rejects every `de`
    # request with "The dataset does not match the checksum recorded at submission".
    # Writing the encoded bytes removes the translation step instead of compensating
    # for it.
    path.write_bytes(table.encode())
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
    reachable = family in REACHABLE.get(host, set())
    if not supported and reachable:
        # Runs, and this input gives it nothing to build. Asserting candidates here would assert
        # designs that honestly do not exist; asserting a failure would assert one that no longer
        # happens.
        assert result.status in ("succeeded", "failed")
        assert not [c for c in (result.candidates or ()) if "and" in c.gate_family]
        return
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
