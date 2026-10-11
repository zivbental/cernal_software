"""Mammalian assembly settings, backbone handling, and sequence export integration."""

import io

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from engine.client import LocalEngine
from engine.domain import AssemblyStandard, Host
from engine.pipeline import build_tools

TRIGGER = "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA"


def test_human_default_does_not_apply_biobrick_restriction_rules(make_request):
    request = make_request(organism="human")
    tools = build_tools(request, Host.HUMAN)
    assert tools["constraints"].standard is AssemblyStandard.NONE
    assert not tools["screener"].sites
    assert "constraints" not in request.params
    explicit = make_request(organism="human", params={"constraints": {"standard": "RFC1000"}})
    assert build_tools(explicit, Host.HUMAN)["constraints"].standard is AssemblyStandard.RFC1000


def test_human_refuses_a_bacterial_catalog_backbone(make_request):
    request = make_request(organism="human", params={"backbone": {"catalog_key": "psb1c3"}})
    result = LocalEngine().run(request, lambda *_: True)
    assert result.status == "failed"
    assert "mammalian" in result.error


def test_human_custom_backbone_and_export_roundtrip(make_request, tmp_path, screening_released):
    # Synthetic fixture tests upload/assembly plumbing; it is not a functional vector.
    record = SeqRecord(Seq("ACGT" * 25), id="test-backbone", name="test-backbone")
    record.annotations = {"molecule_type": "DNA", "topology": "circular"}
    request = make_request(
        organism="human",
        input_mode="direct",
        trigger_sequence=TRIGGER,
        gate_families=["eukaryotic_toehold"],
        params={"backbone": {"custom_genbank": record.format("genbank")}},
    )
    result = LocalEngine().run(request, lambda *_: True)
    assert result.status == "succeeded", result.error
    assert result.accepted
    for candidate in result.accepted:
        segments = candidate.design["plasmid_segments"]
        assert segments[0]["name"] == "I712004"
        assert segments[-2]["name"] == "K404108"
        assert segments[-1]["length_bp"] == 100
    artifacts = {a.kind: a for a in result.artifacts if a.candidate_ref == result.accepted[0].ref}
    assert {"sequence_fasta", "genbank", "sbol"} <= artifacts.keys()
    gb = (tmp_path / "out-default" / artifacts["genbank"].path).read_text()
    exported = SeqIO.read(io.StringIO(gb), "genbank")
    assert exported.annotations["topology"] == "circular"
    assert str(exported.seq).endswith(str(record.seq))
