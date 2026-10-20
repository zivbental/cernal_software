"""Keep the CI partition exhaustive, deterministic, and fail-closed."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ci_test_shards", ROOT / "tools/ci_test_shards.py")
shards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shards)


def test_partition_retains_every_test_once_and_is_order_independent():
    nodes = [f"tests/test_{i // 7}.py::test_{i}" for i in range(100)]
    timings = {"split_modules": ["tests/test_0.py"], "seconds": {nodes[0]: 50}}
    plan, _ = shards.partition(nodes, 16, timings)
    assert plan == shards.partition(list(reversed(nodes)), 16, timings)[0]
    assert sorted(n for group in plan for n in group) == sorted(nodes)
    for module in {n.split("::")[0] for n in nodes} - {"tests/test_0.py"}:
        assert sum(any(n.startswith(module + "::") for n in group) for group in plan) == 1


def test_new_tests_are_scheduled_without_being_in_timing_hints():
    plan, _ = shards.partition(["new.py::test_new"], 2, {"split_modules": [], "seconds": {}})
    assert [node for group in plan for node in group] == ["new.py::test_new"]


@pytest.mark.parametrize("total,nodes", [(0, ["a"]), (2, ["a", "a"])])
def test_invalid_partition_input_fails(total, nodes):
    with pytest.raises(ValueError):
        shards.partition(nodes, total, {"split_modules": [], "seconds": {}})


def reports(tmp_path):
    paths = []
    for index, selected in enumerate((["a", "b"], ["c"]), 1):
        path = tmp_path / f"{index}.json"
        path.write_text(
            json.dumps(
                {
                    "index": index,
                    "total": 2,
                    "collection_count": 3,
                    "collection_sha256": shards.fingerprint(["a", "b", "c"]),
                    "selected": selected,
                    "executed": selected,
                    "exitstatus": 0,
                }
            )
        )
        paths.append(path)
    return paths


def test_complete_reports_pass(tmp_path):
    assert shards.verify_reports(reports(tmp_path)) == 3


@pytest.mark.parametrize(
    "corruption", ["missing", "duplicate", "unexecuted", "failed", "different"]
)
def test_incomplete_or_inconsistent_reports_fail(tmp_path, corruption):
    paths = reports(tmp_path)
    if corruption == "missing":
        paths.pop()
    elif corruption == "duplicate":
        paths.append(paths[0])
    else:
        data = json.loads(paths[1].read_text())
        if corruption == "unexecuted":
            data["executed"] = []
        elif corruption == "failed":
            data["exitstatus"] = 1
        else:
            data["collection_sha256"] = "different"
        paths[1].write_text(json.dumps(data))
    with pytest.raises(ValueError):
        shards.verify_reports(paths)


@pytest.mark.parametrize("replacement", [["a", "b"], ["d"]])
def test_combined_coverage_rejects_overlap_or_substitution(tmp_path, replacement):
    paths = reports(tmp_path)
    data = json.loads(paths[1].read_text())
    data["selected"] = data["executed"] = replacement
    paths[1].write_text(json.dumps(data))
    with pytest.raises(ValueError):
        shards.verify_reports(paths)


def test_real_pytest_shards_execute_pass_and_skip_without_nested_leakage(tmp_path):
    import os
    import shutil
    import subprocess
    import sys

    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copy(ROOT / "tools/ci_test_shards.py", tools / "ci_test_shards.py")
    (tools / "ci_test_durations.json").write_text(json.dumps({"split_modules": [], "seconds": {}}))
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_one.py").write_text(
        "import pytest\n"
        "def test_pass(): assert True\n"
        "@pytest.mark.skip(reason='intentional platform skip')\n"
        "def test_skip(): assert False\n"
    )
    (tests / "test_two.py").write_text("def test_other(): assert True\n")
    env = dict(os.environ)
    env.pop("DJANGO_SETTINGS_MODULE", None)
    env.pop("PYTEST_ADDOPTS", None)
    for index in (1, 2):
        result = subprocess.run(
            [
                sys.executable,
                str(tools / "ci_test_shards.py"),
                "run",
                "--index",
                str(index),
                "--total",
                "2",
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    assert (
        shards.verify_reports(sorted((tmp_path / "test-results/backend").glob("shard-*.json"))) == 3
    )
