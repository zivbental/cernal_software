"""Reject empty/incomplete Python audits of exported production requirements."""

import argparse
import json
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def summarize_coverage(report: dict, requirements: str) -> dict:
    expected = {}
    for line in requirements.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        versions = list(requirement.specifier)
        if len(versions) != 1 or versions[0].operator != "==" or "*" in versions[0].version:
            raise ValueError("Production requirements must contain exact version pins.")
        expected[canonicalize_name(requirement.name)] = versions[0].version
    dependencies = report["dependencies"]
    reported = {canonicalize_name(item["name"]): item for item in dependencies}
    missing = sorted(set(expected) - set(reported))
    skipped = [
        {"name": name, "required_version": version, "reason": reported[name]["skip_reason"]}
        for name, version in sorted(expected.items())
        if name in reported and "skip_reason" in reported[name]
    ]
    audited = [
        name for name in expected if name in reported and "skip_reason" not in reported[name]
    ]
    mismatched = [name for name in audited if str(reported[name].get("version")) != expected[name]]
    return {
        "expected_packages": len(expected),
        "audited_packages": len(audited),
        "skipped_packages": len(skipped),
        "skipped": skipped,
        "missing": missing,
        "mismatched_versions": mismatched,
        "vulnerabilities": sum(len(reported[name].get("vulns", [])) for name in audited),
        "valid": bool(expected and audited and not missing and not mismatched and not skipped),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summary = summarize_coverage(json.loads(args.report.read_text()), args.requirements.read_text())
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not summary["valid"]:
        raise SystemExit(
            "Python advisory coverage is empty, incomplete, or uses different versions."
        )


if __name__ == "__main__":
    main()
