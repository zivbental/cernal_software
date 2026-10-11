"""Security acceptance must audit the locked project, not an empty tool overlay."""

import runpy
from pathlib import Path

import pytest

summarize_coverage = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "tools/check_advisory_coverage.py")
)["summarize_coverage"]


def test_hosted_empty_audit_is_rejected():
    summary = summarize_coverage({"dependencies": [], "fixes": []}, "Django==5.2.17\n")
    assert not summary["valid"]
    assert summary["audited_packages"] == 0
    assert summary["missing"] == ["django"]


def test_incomplete_or_wrong_version_audit_is_rejected():
    report = {"dependencies": [{"name": "django", "version": "5.2.16", "vulns": []}]}
    summary = summarize_coverage(report, "django==5.2.17\nrequests==2.34.2\n")
    assert not summary["valid"]
    assert summary["missing"] == ["requests"]
    assert summary["mismatched_versions"] == ["django"]


def test_partly_skipped_coverage_is_explicit_and_incomplete():
    report = {
        "dependencies": [
            {"name": "django", "version": "5.2.17", "vulns": []},
            {"name": "special-package", "skip_reason": "Advisory service cannot audit package"},
        ]
    }
    summary = summarize_coverage(report, "Django==5.2.17\nspecial_package==1.0\n")
    assert not summary["valid"]
    assert summary["expected_packages"] == 2
    assert summary["audited_packages"] == summary["skipped_packages"] == 1
    assert summary["skipped"][0]["required_version"] == "1.0"


def test_all_skipped_cannot_be_reported_as_success():
    summary = summarize_coverage(
        {"dependencies": [{"name": "django", "skip_reason": "Unavailable"}]}, "django==5.2.17"
    )
    assert not summary["valid"]
    assert summary["skipped_packages"] == 1


def test_inapplicable_markers_are_excluded_and_vulnerabilities_counted():
    summary = summarize_coverage(
        {"dependencies": [{"name": "django", "version": "5.2.17", "vulns": [{"id": "example"}]}]},
        'django==5.2.17\nother==1.0; python_version < "2.0"\n',
    )
    assert summary["valid"]
    assert summary["expected_packages"] == 1
    assert summary["vulnerabilities"] == 1


@pytest.mark.parametrize("requirement", ["django>=5", "django==5.*", "django"])
def test_unpinned_exports_are_rejected(requirement):
    with pytest.raises(ValueError, match="exact version pins"):
        summarize_coverage({"dependencies": []}, requirement)
