"""Stored-structure drawing is geometry only, behind the existing folding adapter."""

import math
from types import SimpleNamespace

import pytest

from engine.client import layout_stored_structure
from engine.errors import EngineError, StructureLayoutUnavailable
from engine.gates.tools import folding
from engine.gates.tools.folding import FoldEngine
from engine.gates.tools.rnaviz.layout import build_bases_and_links


@pytest.fixture(autouse=True)
def forbid_scientific_computation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Displaying a stored structure must never fold or build a FoldEngine")

    monkeypatch.setattr(FoldEngine, "__init__", forbidden)
    for name in ("fold_compound", "fold", "cofold"):
        monkeypatch.setattr(folding.RNA, name, forbidden)


@pytest.mark.parametrize("structure", [".", "..", "." * 29, "(((...)))", "((..((...))..))"])
def test_layout_preserves_sequence_structure_and_finite_coordinates(structure):
    sequence = ("ACGU" * len(structure))[: len(structure)]
    result = layout_stored_structure(sequence, structure, structure_kind="intended_target")

    assert result["status"] == "available"
    assert result["reason"] is None
    assert result["sequence"] == sequence
    assert result["structure"] == structure
    assert result["structure_kind"] == "intended_target"
    assert [base["index"] for base in result["bases"]] == list(range(len(sequence)))
    assert "".join(base["char"] for base in result["bases"]) == sequence
    assert all(math.isfinite(base[axis]) for base in result["bases"] for axis in ("x", "y"))
    assert result["renderer"] == "cernal-rnaviz"
    assert result["renderer_version"] == "aa112e17a76941233987bb4287c2c66511c40d13"


def test_exact_pair_indexes_are_emitted_once_and_backbone_is_not_a_pair():
    result = layout_stored_structure("A" * 15, "((..((...))..))")
    assert result["links"] == [
        {"source": 0, "target": 14},
        {"source": 1, "target": 13},
        {"source": 4, "target": 10},
        {"source": 5, "target": 9},
    ]


def test_source_helper_retains_global_offsets():
    points = {i: SimpleNamespace(X=float(i), Y=-float(i)) for i in range(4)}
    bases, links = build_bases_and_links("ACGU", points, [4, 4, 0, 0, 1], start_offset=12)
    assert [base.index for base in bases] == [12, 13, 14, 15]
    assert [link.to_dict() for link in links] == [{"source": 12, "target": 15}]


@pytest.mark.parametrize("structure", ["..", "." * 12, "(((...)))", "(.(..).)"])
def test_coordinates_match_upstream_default_without_reading_global_plot_type(
    structure, monkeypatch
):
    # Tal's original helper uses get_xy_coordinates with ViennaRNA's NAVIEW default.
    monkeypatch.setattr(folding.RNA.cvar, "rna_plot_type", folding.RNA.PLOT_TYPE_NAVIEW)
    expected = folding.RNA.get_xy_coordinates(structure)
    expected_xy = [(expected.get(i).X, expected.get(i).Y) for i in range(len(structure))]
    monkeypatch.setattr(folding.RNA.cvar, "rna_plot_type", folding.RNA.PLOT_TYPE_CIRCULAR)
    bases, _ = FoldEngine.structure_layout("A" * len(structure), structure)
    assert [(base.x, base.y) for base in bases] == expected_xy
    assert folding.RNA.cvar.rna_plot_type == folding.RNA.PLOT_TYPE_CIRCULAR


def test_single_base_has_a_finite_origin_and_no_pairs():
    result = layout_stored_structure("G", ".")
    assert result["bases"] == [{"index": 0, "char": "G", "x": 0.0, "y": 0.0}]
    assert result["links"] == []


@pytest.mark.parametrize(
    "structure", ["()", "(())", "()()", "(()())", "(.)", "(..)", "((.))", "()" * 1000]
)
def test_balanced_minimal_pairs_are_drawable_without_claiming_scientific_validity(structure):
    result = layout_stored_structure("A" * len(structure), structure)
    assert result["status"] == "available"
    assert len(result["bases"]) == len(structure)
    assert len(result["links"]) == structure.count("(")
    assert all(math.isfinite(base[axis]) for base in result["bases"] for axis in ("x", "y"))


def test_structure_layout_reuses_existing_coordinates_adapter(monkeypatch):
    calls = []

    def coordinates(structure):
        calls.append(structure)
        return [(3.0, 4.0), (5.0, 6.0)]

    monkeypatch.setattr(FoldEngine, "layout_coordinates", coordinates)
    result = layout_stored_structure("AU", "()")
    assert calls == ["()"]
    assert [(base["x"], base["y"]) for base in result["bases"]] == [(3.0, 4.0), (5.0, 6.0)]


@pytest.mark.parametrize("kind", [None, "", "legacy_custom_label", "intended_target"])
def test_provenance_is_never_inferred(kind):
    assert layout_stored_structure("A", ".", structure_kind=kind)["structure_kind"] == kind


@pytest.mark.parametrize("sequence,structure", [(None, None), ("", ""), ("A", None), (None, ".")])
def test_missing_historical_data_is_unavailable(sequence, structure):
    result = layout_stored_structure(sequence, structure)
    assert result["status"] == "unavailable"
    assert result["bases"] == result["links"] == []
    assert result["reason"]


@pytest.mark.parametrize(
    "sequence,structure",
    [
        (["A"], "."),
        ("A", ["."]),
        (4, "."),
        (False, "."),
        ("AT", ".."),
        ("AN", ".."),
        ("au", ".."),
        ("A&U", ".&."),
        ("A\n", ".."),
        ("A\x00", ".."),
        ("AA", "."),
        ("AA", "(("),
        ("AA", ")("),
        ("AA", "[ ]"),
        ("AA", "xx"),
    ],
)
def test_invalid_data_never_reaches_native_layout(sequence, structure, monkeypatch):
    def forbidden(*args):
        pytest.fail("Malformed stored data reached native code")

    monkeypatch.setattr(folding.RNA, "naview_xy_coordinates", forbidden)
    monkeypatch.setattr(folding.RNA, "ptable", forbidden)
    result = layout_stored_structure(sequence, structure)
    assert result["status"] == "invalid"
    assert result["reason"]
    assert result["bases"] == result["links"] == []


def test_exact_viewer_limit_works_and_larger_valid_structures_are_unavailable(monkeypatch):
    result = layout_stored_structure("A" * 2000, "." * 2000)
    assert result["status"] == "available"
    assert len(result["bases"]) == 2000
    assert all(math.isfinite(base[axis]) for base in result["bases"] for axis in ("x", "y"))

    def forbidden(*args):
        pytest.fail("Oversized stored data reached native code")

    monkeypatch.setattr(folding.RNA, "naview_xy_coordinates", forbidden)
    result = layout_stored_structure("A" * 2001, "." * 2001)
    assert result["status"] == "unavailable"
    assert "2,000 nt viewer limit" in result["reason"]
    with pytest.raises(StructureLayoutUnavailable):
        FoldEngine.structure_layout("A" * 2001, "." * 2001)


@pytest.mark.parametrize("exception", [RuntimeError, SystemError, ValueError, OverflowError])
def test_known_native_failure_is_safe_and_not_a_scientific_result(monkeypatch, exception):
    def failed(*args):
        raise exception("private/native/path and internal details")

    monkeypatch.setattr(folding.RNA, "naview_xy_coordinates", failed)
    result = layout_stored_structure("AA", "..")
    assert result["status"] == "error"
    assert result["reason"] == "Stored structure layout could not be generated."
    assert result["bases"] == result["links"] == []


@pytest.mark.parametrize("points", [None, [], [SimpleNamespace(X=float("nan"), Y=0.0)] * 2])
def test_bad_native_coordinates_are_rejected(monkeypatch, points):
    monkeypatch.setattr(folding.RNA, "naview_xy_coordinates", lambda structure: points)
    result = layout_stored_structure("AA", "..")
    assert result["status"] == "error"
    assert result["bases"] == result["links"] == []
    with pytest.raises(EngineError):
        FoldEngine.structure_layout("AA", "..")


def test_programming_errors_are_not_disguised_as_missing_data(monkeypatch):
    def bug(*args):
        raise AttributeError("Unexpected programming error")

    monkeypatch.setattr(FoldEngine, "structure_layout", bug)
    with pytest.raises(AttributeError):
        layout_stored_structure("AA", "..")
