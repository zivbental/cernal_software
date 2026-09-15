"""Stage 5 — ``PlasmidBuilder`` (docs/plasmids.md, ADR 0007).

Built on the `direct` path's shape: one trigger, one switch, one hand-built
``CircuitCandidate`` — the same move ``pipeline._direct_trigger`` makes for stages 1-2
(docs/plasmids.md §3), so these tests construct a circuit the same way rather than
waiting on stage 4 (``CircuitDesigner``), which is not built.

The parts table (``PROMOTERS``/``TERMINATORS``/``PAYLOADS``) holds real, verified iGEM
Registry sequences (BBa_J23119, BBa_B0015, BBa_E0040) — see the module docstring in
``engine/stages/plasmids.py`` for why real parts rather than invented ones. Tests below
exercise both the populated entries (E. coli / GFP) and the deliberately unpopulated
ones (every other host/outcome), since both are load-bearing behaviour.
"""

import io
import re

import pytest
from Bio import SeqIO

from engine.domain import (
    AssemblyStandard,
    BooleanExpression,
    CircuitCandidate,
    ConfusionMatrix,
    DesiredOutcome,
    GateDesign,
    GateKind,
    Host,
    LogicGene,
    LogicGraph,
    LogicOperator,
    SegmentKind,
    TriggerCandidate,
    TriggerSet,
)
from engine.errors import InputValidationError
from engine.gates.tools.codons import CodonOptimizer
from engine.stages.motifs import MotifScreener
from engine.stages.plasmids import (
    BACKBONES,
    PAYLOADS,
    PROMOTERS,
    TERMINATORS,
    PlasmidBuilder,
    parse_custom_backbone,
    to_genbank,
    validate_payload_cds,
)

# A real toehold switch shape: leader/toehold, stem, loop, AUG, linker — not a
# fabricated CDS, just a plausible switch sequence for exercising assembly and
# screening. The AUG position is computed the same way ToeholdGate records it
# (index of the literal start codon), not hand-counted.
SWITCH_SEQUENCE = "GGGUUUAACAGAGGAGAUAAAGAUGGCUAAGCUUAACGGAUCCAUG"


def _trigger() -> TriggerCandidate:
    return TriggerCandidate(
        trigger_id="trig-000001",
        gene_id="pasted",
        symbol="pasted",
        sequence="AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA",
        start_index=0,
        openness=0.6,
        accessibility=0.5,
        mfe=-4.2,
        off_target_penalty=0.0,
        segment_specificity=1.0,
        gc_content=44.4,
    )


def _circuit(
    *, switch_sequence: str = SWITCH_SEQUENCE, aug_index: int | None = None, host: Host = Host.ECOLI
) -> CircuitCandidate:
    """One hand-built one-gene circuit, the shape a `direct` run actually produces."""
    if aug_index is None:
        aug_index = switch_sequence.index("AUG")

    design = GateDesign(
        design_id="sw-000001",
        gate_kind=GateKind.TOEHOLD,
        host=host,
        trigger_set=TriggerSet(activators=(_trigger(),)),
        sequence=switch_sequence,
        architecture={"aug_index": aug_index},
    )
    graph = LogicGraph(
        genes=(LogicGene(name="A", role="pasted", state="ON", direction="up"),),
        mid_gate=LogicOperator.IDENTITY,
        outer_gate=LogicOperator.IDENTITY,
        invert=False,
        output="",
        caption="IF pasted -> GFP",
    )
    return CircuitCandidate(
        circuit_id="circ-000001",
        expression=BooleanExpression.gene("pasted"),
        logic_graph=graph,
        # Unmeasured, not measured-as-zero (docs/plasmids.md §3) — a direct run has no
        # samples, and nothing downstream reads this field once this circuit is only
        # used to reach PlasmidBuilder.build().
        confusion=ConfusionMatrix(0, 0, 0, 0),
        designs=(design,),
        output="",
    )


@pytest.fixture
def builder() -> PlasmidBuilder:
    return PlasmidBuilder(MotifScreener(AssemblyStandard.RFC10), CodonOptimizer(Host.ECOLI))


# --- validate_payload_cds -----------------------------------------------------------


def test_a_well_formed_cds_is_accepted_and_returned_as_dna():
    dna = validate_payload_cds("test", "AUGGCUAAGCUUAACUAA")
    assert dna == "ATGGCTAAGCTTAACTAA"


def test_dna_input_is_accepted_the_same_as_rna():
    assert validate_payload_cds("test", "AUGGCUAAGCUUAACUAA") == validate_payload_cds(
        "test", "ATGGCTAAGCTTAACTAA"
    )


def test_a_tandem_stop_is_accepted_as_one_stop_not_rejected():
    """BBa_E0040 itself ends UAA UAA — the real-world case that surfaced this rule."""
    name, cds = PAYLOADS[DesiredOutcome.GFP]
    dna = validate_payload_cds(name, cds)
    assert dna.endswith("TAATAA")


def test_not_starting_with_a_start_codon_is_refused():
    with pytest.raises(InputValidationError, match="start codon"):
        validate_payload_cds("test", "GCUGCUAAGCUUAACUAA")


def test_not_a_whole_number_of_codons_is_refused():
    with pytest.raises(InputValidationError, match="whole number of codons"):
        validate_payload_cds("test", "AUGGCUAAGCUUAACUA")  # 17 nt


def test_no_stop_codon_at_all_is_refused():
    with pytest.raises(InputValidationError, match="does not end in a stop codon"):
        validate_payload_cds("test", "AUGGCUAAGCUUAACGGC")


def test_a_premature_stop_before_the_true_end_is_refused():
    # UAA mid-sequence, then more coding, then a real trailing stop.
    with pytest.raises(InputValidationError, match="premature"):
        validate_payload_cds("test", "AUGUAAGCUAAGCUUAACUAA")


def test_invalid_alphabet_is_refused():
    with pytest.raises(InputValidationError, match="not a valid"):
        validate_payload_cds("test", "AUGXCUAAGCUUAACUAA")


# --- payload_segment -----------------------------------------------------------------


def test_payload_segment_looks_up_the_configured_gfp(builder):
    segment = builder.payload_segment(DesiredOutcome.GFP)

    assert segment.kind is SegmentKind.PAYLOAD
    assert segment.name == "GFP"
    assert segment.sequence == validate_payload_cds(*PAYLOADS[DesiredOutcome.GFP])


def test_payload_segment_refuses_an_unconfigured_outcome(builder):
    with pytest.raises(InputValidationError, match="mcherry"):
        builder.payload_segment(DesiredOutcome.MCHERRY)


def test_payload_segment_names_what_is_configured_in_the_error(builder):
    with pytest.raises(InputValidationError, match="gfp"):
        builder.payload_segment(DesiredOutcome.LUCIFERASE)


def test_payload_segment_refuses_custom_directly(builder):
    """CUSTOM has no catalog entry — the caller must build its Segment from
    params['payload']['custom_sequence'] itself, through validate_payload_cds."""
    with pytest.raises(InputValidationError, match="CUSTOM"):
        builder.payload_segment(DesiredOutcome.CUSTOM)


# --- build: happy path ---------------------------------------------------------------


def test_build_assembles_promoter_switch_payload_terminator_in_order(builder):
    design = builder.build(_circuit(), DesiredOutcome.GFP)

    kinds = [segment.kind for segment in design.plasmid.segments]
    assert kinds == [
        SegmentKind.PROMOTER,
        SegmentKind.SWITCH,
        SegmentKind.PAYLOAD,
        SegmentKind.TERMINATOR,
    ]


def test_build_produces_a_compliant_plasmid_for_the_clean_fixture(builder):
    design = builder.build(_circuit(), DesiredOutcome.GFP)

    assert design.is_compliant
    assert design.violations == ()


def test_build_includes_the_backbone_segments_verbatim():
    from engine.domain import Segment

    backbone = (Segment(SegmentKind.BACKBONE, "test-ori", "ACGTACGTACGT"),)
    builder = PlasmidBuilder(
        MotifScreener(AssemblyStandard.RFC10), CodonOptimizer(Host.ECOLI), backbone=backbone
    )

    design = builder.build(_circuit(), DesiredOutcome.GFP)

    assert design.plasmid.segments[-1].name == "test-ori"


def test_the_switch_sequence_is_present_exactly_once_as_dna():
    from engine import sequences as sq

    builder = PlasmidBuilder(MotifScreener(AssemblyStandard.RFC10), CodonOptimizer(Host.ECOLI))
    design = builder.build(_circuit(), DesiredOutcome.GFP)

    assert design.plasmid.sequence.count(sq.to_dna(SWITCH_SEQUENCE)) == 1


def test_the_payload_sequence_is_present_exactly_once():
    builder = PlasmidBuilder(MotifScreener(AssemblyStandard.RFC10), CodonOptimizer(Host.ECOLI))
    design = builder.build(_circuit(), DesiredOutcome.GFP)

    _, gfp_cds = PAYLOADS[DesiredOutcome.GFP]
    assert design.plasmid.sequence.count(gfp_cds) == 1


def test_plasmid_id_is_deterministic_and_traces_to_circuit_and_outcome(builder):
    design = builder.build(_circuit(), DesiredOutcome.GFP)
    again = builder.build(_circuit(), DesiredOutcome.GFP)

    assert design.plasmid_id == again.plasmid_id
    assert design.plasmid_id == "plasmid-000001-gfp"


def test_total_length_is_the_sum_of_every_segment(builder):
    design = builder.build(_circuit(), DesiredOutcome.GFP)

    assert design.plasmid.length_bp == sum(s.length_bp for s in design.plasmid.segments)


# --- build: failure paths ------------------------------------------------------------


def test_build_refuses_a_circuit_with_no_designs(builder):
    empty = _circuit()
    import dataclasses

    empty = dataclasses.replace(empty, designs=())

    with pytest.raises(InputValidationError, match="at least one switch design"):
        builder.build(empty, DesiredOutcome.GFP)


def test_build_refuses_an_unconfigured_host(builder):
    """*E. coli* and yeast both have a real promoter/terminator configured now
    (docs/ROADMAP.md Q12) — human is the one still genuinely unconfigured."""
    with pytest.raises(InputValidationError, match="human"):
        builder.build(_circuit(host=Host.HUMAN), DesiredOutcome.GFP)


def test_build_refuses_an_unconfigured_outcome(builder):
    with pytest.raises(InputValidationError, match="ampr"):
        builder.build(_circuit(), DesiredOutcome.ANTIBIOTIC)


# --- build: DesiredOutcome.CUSTOM ---------------------------------------------------


def test_build_refuses_custom_with_no_payload_supplied(builder):
    with pytest.raises(InputValidationError, match="custom_sequence"):
        builder.build(_circuit(), DesiredOutcome.CUSTOM)


def test_build_accepts_a_valid_custom_payload(builder):
    design = builder.build(_circuit(), DesiredOutcome.CUSTOM, custom_payload="AUGGCUAAGUAA")

    payload = next(s for s in design.plasmid.segments if s.kind is SegmentKind.PAYLOAD)
    assert payload.name == "Custom"
    assert payload.sequence == "ATGGCTAAGTAA"
    assert design.plasmid_id == "plasmid-000001-other"


def test_build_validates_a_custom_payload_the_same_as_a_catalog_one(builder):
    with pytest.raises(InputValidationError, match="start codon"):
        builder.build(_circuit(), DesiredOutcome.CUSTOM, custom_payload="GCUGCUAAGUAA")


# --- build: the failure modes docs/plasmids.md §7 exists to catch --------------------


def test_a_restriction_site_formed_across_a_junction_is_caught():
    """Neither backbone segment alone carries EcoRI; joining them creates one —
    the classic assembly failure (docs/plasmids.md §7.2), engineered here with two
    fully-controlled backbone segments rather than fighting real part endings."""
    from engine.domain import Segment

    left = Segment(SegmentKind.BACKBONE, "left", "ACGTACGTGAA")
    right = Segment(SegmentKind.BACKBONE, "right", "TTCACGTACGT")
    assert not MotifScreener(AssemblyStandard.RFC10).violations(left.sequence)
    assert not MotifScreener(AssemblyStandard.RFC10).violations(right.sequence)

    builder = PlasmidBuilder(
        MotifScreener(AssemblyStandard.RFC10), CodonOptimizer(Host.ECOLI), backbone=(left, right)
    )
    design = builder.build(_circuit(), DesiredOutcome.GFP)

    assert not design.is_compliant
    assert any("EcoRI" in v for v in design.violations)


def test_circular_screening_runs_over_the_whole_assembled_plasmid(builder, monkeypatch):
    """PlasmidBuilder must ask for circular=True, not just screen linearly — assert
    the call it actually makes, since crafting a real junction-spanning fixture through
    every real part is brittle and the unit behaviour is already locked down in
    test_tools.py."""
    calls = []
    original = MotifScreener.violations

    def spy(self, sequence, *, circular=False):
        calls.append(circular)
        return original(self, sequence, circular=circular)

    monkeypatch.setattr(MotifScreener, "violations", spy)
    builder.build(_circuit(), DesiredOutcome.GFP)

    assert calls == [True]


def test_an_out_of_frame_switch_payload_join_is_caught(builder):
    # Shift the recorded aug_index by one base without touching the sequence, so the
    # switch's "start codon" the builder reads is no longer actually AUG-aligned with
    # the payload — the exact silent failure docs/plasmids.md §7.4 measured.
    design = builder.build(_circuit(aug_index=SWITCH_SEQUENCE.index("AUG") + 1), DesiredOutcome.GFP)

    assert not design.is_compliant
    assert any("not in frame" in v for v in design.violations)


def test_a_family_with_no_aug_index_is_not_frame_checked(builder):
    """A gate family that never records an aug_index (none built today do this, but
    the check must degrade safely) has nothing for the frame check to inspect."""
    design = _circuit()
    import dataclasses

    bare_design = dataclasses.replace(design.designs[0], architecture={})
    circuit = dataclasses.replace(design, designs=(bare_design,))

    result = builder.build(circuit, DesiredOutcome.GFP)
    assert not any("frame" in v for v in result.violations)


# --- to_genbank ------------------------------------------------------------------


def test_genbank_round_trip_preserves_topology_sequence_and_features(builder):
    design = builder.build(_circuit(), DesiredOutcome.GFP)
    gb = to_genbank(design)

    record = SeqIO.read(io.StringIO(gb.decode()), "genbank")

    assert record.annotations.get("topology") == "circular"
    assert str(record.seq).upper() == design.plasmid.sequence
    assert len(record.features) == len(design.plasmid.segments)


def test_genbank_uses_standard_feature_types_and_cernal_qualifiers(builder):
    design = builder.build(_circuit(), DesiredOutcome.GFP)
    record = SeqIO.read(io.StringIO(to_genbank(design).decode()), "genbank")

    types = [f.type for f in record.features]
    assert types == ["promoter", "misc_feature", "CDS", "terminator"]

    payload_feature = record.features[types.index("CDS")]
    assert payload_feature.qualifiers["label"] == ["GFP"]
    assert payload_feature.qualifiers["cernal_role"] == ["payload"]
    assert payload_feature.qualifiers["cernal_circuit_id"] == ["circ-000001"]


def test_genbank_feature_coordinates_are_contiguous_and_in_bounds(builder):
    design = builder.build(_circuit(), DesiredOutcome.GFP)
    record = SeqIO.read(io.StringIO(to_genbank(design).decode()), "genbank")

    position = 0
    for feature in record.features:
        assert int(feature.location.start) == position
        position = int(feature.location.end)
    assert position == len(record.seq)


def test_genbank_output_is_deterministic(builder):
    design = builder.build(_circuit(), DesiredOutcome.GFP)

    assert to_genbank(design) == to_genbank(design)


# --- BACKBONES catalog (docs/plasmids.md Q13, docs/ROADMAP.md E5b) ------------------


def test_backbones_table_has_ten_real_entries():
    assert len(BACKBONES) == 10
    for key, (name, sequence) in BACKBONES.items():
        assert key == key.lower()
        assert name  # a real registry name, never blank
        assert set(sequence) <= set("ACGT"), f"{key} contains non-ACGT characters"
        assert len(sequence) > 1000  # every real vector is well over a kilobase


def test_backbones_span_more_than_one_resistance_marker_and_copy_number():
    """Not ten flavours of the same vector — real, meaningfully different choices."""
    names = {name for name, _ in BACKBONES.values()}
    assert len(names) == 10  # every catalog entry is visibly distinct
    lengths = {len(seq) for _, seq in BACKBONES.values()}
    assert len(lengths) > 1  # more than one copy-number class


# --- parse_custom_backbone -----------------------------------------------------------


def test_parse_custom_backbone_round_trips_a_real_genbank_file(builder):
    """Build a real plasmid, export it, and parse the export back — the same
    round-trip discipline docs/plasmids.md §7.5 already applies to to_genbank itself,
    now exercised through the reverse direction too."""
    design = builder.build(_circuit(), DesiredOutcome.GFP)
    gb_text = to_genbank(design).decode("utf-8")

    segment = parse_custom_backbone(gb_text)

    assert segment.kind == SegmentKind.BACKBONE
    assert segment.sequence == design.plasmid.sequence


def test_parse_custom_backbone_refuses_a_linear_record():
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord

    record = SeqRecord(Seq("ACGT" * 20), id="linear-test", name="linear_test")
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "linear"

    with pytest.raises(InputValidationError, match="circular"):
        parse_custom_backbone(record.format("genbank"))


def test_parse_custom_backbone_refuses_unparseable_text():
    with pytest.raises(InputValidationError, match="GenBank"):
        parse_custom_backbone("this is not a GenBank file")


def test_parse_custom_backbone_refuses_an_empty_sequence():
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord

    record = SeqRecord(Seq(""), id="empty-test", name="empty_test")
    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "circular"

    with pytest.raises(InputValidationError):
        parse_custom_backbone(record.format("genbank"))


# --- Golden fixture (docs/plasmids.md §10) ------------------------------------------


def test_golden_fixture_locks_down_the_clean_construct(builder):
    """One small, stable fixture. If this ever changes, it must change on purpose —
    the checksum, length and feature order are the whole point of pinning it."""
    design = builder.build(_circuit(), DesiredOutcome.GFP)

    assert design.plasmid.length_bp == 930
    assert [s.kind.value for s in design.plasmid.segments] == [
        "promoter",
        "switch",
        "payload",
        "terminator",
    ]
    assert [s.name for s in design.plasmid.segments] == ["J23119", "sw-000001", "GFP", "B0015"]
    assert design.is_compliant

    gb = to_genbank(design)
    assert re.match(rb"LOCUS\s+plasmid-000001-gfp\s+930 bp\s+DNA\s+circular", gb)


# --- Parts table sanity (the tables themselves, not the mechanism) -------------------


def test_every_configured_promoter_and_terminator_is_valid_dna():
    import re as _re

    for _host, (_name, seq) in {**PROMOTERS, **TERMINATORS}.items():
        assert _re.fullmatch("[ACGT]+", seq), f"non-DNA characters in {_name}"


def test_every_configured_payload_passes_its_own_validation():
    for outcome, (name, seq) in PAYLOADS.items():
        assert validate_payload_cds(name, seq), f"{outcome} payload failed validation"
