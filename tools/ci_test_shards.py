"""Run complete, deterministic GitLab pytest shards and audit their coverage.

Durations are scheduling hints, never a test allowlist: every collected node is
assigned, including new tests. Module fixtures stay together; only explicitly
profiled function-scoped modules may be divided between workers.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMINGS = ROOT / "tools" / "ci_test_durations.json"


def fingerprint(nodeids):
    return hashlib.sha256("\n".join(sorted(nodeids)).encode()).hexdigest()


def partition(nodeids, total, timings):
    """Longest estimated group first, with stable tie-breaking and no exclusions."""
    if total < 1 or len(set(nodeids)) != len(nodeids):
        raise ValueError("Shard count must be positive and collection must be unique")
    split = set(timings["split_modules"])
    groups = defaultdict(list)
    for nodeid in sorted(nodeids):
        module = nodeid.split("::", 1)[0]
        groups[nodeid if module in split else module].append(nodeid)
    weights = timings["seconds"]
    ordered = sorted(
        groups,
        key=lambda key: (-max(float(weights.get(key, len(groups[key]))), 0.01), key),
    )
    shards = [[] for _ in range(total)]
    loads = [0.0] * total
    for key in ordered:
        index = min(range(total), key=lambda i: (loads[i], i))
        shards[index].extend(groups[key])
        loads[index] += max(float(weights.get(key, len(groups[key]))), 0.01)
    flattened = [node for shard in shards for node in shard]
    if sorted(flattened) != sorted(nodeids) or len(set(flattened)) != len(nodeids):
        raise ValueError("Shard assignment omitted or duplicated collected tests")
    return [sorted(shard) for shard in shards], loads


def verify_reports(paths):
    reports = [json.loads(Path(path).read_text()) for path in paths]
    if not reports:
        raise ValueError("No shard coverage reports")
    first = reports[0]
    total = first["total"]
    if sorted(r["index"] for r in reports) != list(range(1, total + 1)):
        raise ValueError("Missing or duplicate shard reports")
    combined = []
    for report in reports:
        for key in ("total", "collection_count", "collection_sha256"):
            if report[key] != first[key]:
                raise ValueError("Shards did not use the same complete collection")
        if report["exitstatus"] != 0 or report["selected"] != report["executed"]:
            raise ValueError("A shard did not successfully execute its complete assignment")
        combined.extend(report["selected"])
    if len(combined) != len(set(combined)) or len(combined) != first["collection_count"]:
        raise ValueError("Combined shards omitted or duplicated tests")
    if fingerprint(combined) != first["collection_sha256"]:
        raise ValueError("Combined shards differ from the full collected suite")
    return len(combined)


def run_shard(index, total, report_dir, collect_only=False):
    import pytest

    if not 1 <= index <= total:
        raise ValueError("Shard index must be between 1 and total inclusive")
    timings = json.loads(TIMINGS.read_text())
    report_dir.mkdir(parents=True, exist_ok=True)

    class Shard:
        selected = []
        executed = set()
        collection = []

        @pytest.hookimpl(trylast=True)
        def pytest_collection_modifyitems(self, config, items):
            self.collection = [item.nodeid for item in items]
            # A future shared fixture in a split module must not silently multiply
            # expensive setup. Re-profile and regroup it explicitly instead.
            for item in items:
                if item.nodeid.split("::", 1)[0] in timings["split_modules"]:
                    definitions = item._fixtureinfo.name2fixturedefs.values()
                    if any(
                        f.scope in {"module", "class"}
                        and not (
                            f.argname == "_django_setup_unittest"
                            and f.func.__module__ == "pytest_django.plugin"
                            and item.cls is None
                        )
                        for fs in definitions
                        for f in fs
                    ):
                        raise pytest.UsageError(
                            f"Shared fixture in split module: {item.nodeid}; "
                            "re-profile shard groups"
                        )
            assignments, loads = partition(self.collection, total, timings)
            self.selected = assignments[index - 1]
            selected = set(self.selected)
            deselected = [item for item in items if item.nodeid not in selected]
            items[:] = [item for item in items if item.nodeid in selected]
            config.hook.pytest_deselected(items=deselected)
            print(
                f"Shard {index}/{total}: {len(items)}/{len(self.collection)} tests; "
                f"profile estimate {loads[index - 1]:.1f}s (runner speed may differ)"
            )

        def pytest_runtest_logstart(self, nodeid, location):
            self.executed.add(nodeid)

        def pytest_sessionfinish(self, session, exitstatus):
            payload = {
                "index": index,
                "total": total,
                "collection_count": len(self.collection),
                "collection_sha256": fingerprint(self.collection),
                "selected": self.selected,
                "executed": sorted(self.executed),
                "exitstatus": int(exitstatus),
            }
            (report_dir / f"shard-{index}.json").write_text(json.dumps(payload, indent=2) + "\n")

    args = ["-q", "--durations=20", f"--junitxml={report_dir}/junit-{index}.xml"]
    if collect_only:
        args.append("--collect-only")
    return int(pytest.main(args, plugins=[Shard()]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--index", type=int, required=True)
    run.add_argument("--total", type=int, required=True)
    run.add_argument("--report-dir", type=Path, default=ROOT / "test-results" / "backend")
    run.add_argument("--collect-only", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("reports", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "verify":
        print(f"Verified complete, disjoint execution of {verify_reports(args.reports)} tests.")
        return 0
    return run_shard(args.index, args.total, args.report_dir, args.collect_only)


if __name__ == "__main__":
    raise SystemExit(main())
