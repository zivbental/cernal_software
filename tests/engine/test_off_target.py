"""``OffTargetScanner`` — S5. Only the empty-transcriptome case is built today
(docs/triggers.md T1); everything else stays a documented stub until Q1 supplies a real
transcriptome to index.
"""

import pytest

from engine.stages.off_target import OffTargetScanner


@pytest.fixture
def empty_scanner() -> OffTargetScanner:
    return OffTargetScanner({})


def test_scan_trigger_on_an_empty_transcriptome_is_clean_not_a_crash(empty_scanner):
    report = empty_scanner.scan_trigger("ACGUACGUACGUACGUACGUACGUACGUACGU")
    assert report.hits == ()
    assert report.penalty == 0.0


def test_scan_switch_on_an_empty_transcriptome_is_clean_not_a_crash(empty_scanner):
    report = empty_scanner.scan_switch("ACGUACGUACGUACGUACGUACGUACGUACGU")
    assert report.hits == ()
    assert report.penalty == 0.0


def test_a_real_transcriptome_still_raises_for_the_unbuilt_methods():
    """The guard is specific to "nothing to scan against" — a non-empty transcriptome
    is real work this stage still does not do (Q1)."""
    scanner = OffTargetScanner({"geneA": "ACGUACGUACGUACGUACGUACGUACGUACGU"})
    with pytest.raises(NotImplementedError):
        scanner.scan_trigger("ACGUACGUACGUACGUACGUACGUACGUACGU")
    with pytest.raises(NotImplementedError):
        scanner.scan_switch("ACGUACGUACGUACGUACGUACGUACGUACGU")


def test_build_index_and_find_similar_are_still_unbuilt(empty_scanner):
    with pytest.raises(NotImplementedError):
        empty_scanner.build_index()
    with pytest.raises(NotImplementedError):
        empty_scanner.find_similar("ACGUACGUACGUACGUACGUACGUACGUACGU")
