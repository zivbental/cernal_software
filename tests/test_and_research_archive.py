"""AND evidence recovery preserves exact bytes and refuses destructive replacements."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "and_research_archive", Path(__file__).resolve().parents[1] / "tools/and_research_archive.py"
)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


@pytest.fixture
def git_evidence(tmp_path):
    """Create a tiny local Git archive containing bytes unsafe for text redirection."""
    repo = tmp_path / "repo"
    repo.mkdir()
    name = archive.PREFIX + "example.csv"
    content = b"column,value\r\nexact,\x00\xff\r\n"
    source = repo / name
    source.parent.mkdir(parents=True)
    source.write_bytes(content)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)

    git("init", "-q")
    git("add", name)
    git(
        "-c",
        "user.name=Archive test",
        "-c",
        "user.email=archive@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "Pin test evidence",
    )
    revision = git("rev-parse", "HEAD").decode().strip()
    record = {"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    return repo, revision, record, content


def test_binary_recovery_repeat_and_check(tmp_path, git_evidence, monkeypatch):
    repo, revision, record, content = git_evidence
    output = tmp_path / "recovered"
    assert archive.recover(record, revision, output, repo=repo) == "recovered"
    assert (output / record["path"]).read_bytes() == content
    assert archive.recover(record, revision, output, repo=repo) == "verified existing"
    monkeypatch.setattr(archive, "load_archive", lambda *args: (revision, [record]))
    assert archive.main(["--check", "--output-dir", str(output)]) == 0


def test_different_local_file_is_never_replaced(tmp_path, git_evidence):
    repo, revision, record, _ = git_evidence
    output = tmp_path / "recovered"
    target = output / record["path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(b"local research result")
    with pytest.raises(ValueError, match="left unchanged"):
        archive.recover(record, revision, output, repo=repo)
    assert target.read_bytes() == b"local research result"


@pytest.mark.parametrize("field,value", [("sha256", "0" * 64), ("size", 1)])
def test_archive_mismatch_creates_no_output(tmp_path, git_evidence, field, value):
    repo, revision, record, _ = git_evidence
    record = {**record, field: value}
    output = tmp_path / "recovered"
    with pytest.raises(ValueError, match="fails byte count/SHA-256"):
        archive.recover(record, revision, output, repo=repo)
    assert not output.exists()


def test_invalid_archive_path_and_unknown_selection_fail_without_writes(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    bad = {"path": archive.PREFIX + "../other.csv", "size": 0, "sha256": "0" * 64}
    manifest.write_text(json.dumps({"source_commit": "a" * 40, "files": [bad]}))
    with pytest.raises(ValueError, match="Invalid or duplicate"):
        archive.load_archive(manifest)
    monkeypatch.setattr(archive, "load_archive", lambda *args: ("a" * 40, []))
    output = tmp_path / "recovered"
    assert archive.main(["--restore", "--path", "unrecorded.csv", "--output-dir", str(output)]) == 1
    assert not output.exists()
