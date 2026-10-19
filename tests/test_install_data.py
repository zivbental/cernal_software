"""Data installation uses immutable bytes, atomic writes, and explicit offline failure."""

import hashlib
import importlib.util
import io
from pathlib import Path
from urllib.error import URLError

import pytest

SPEC = importlib.util.spec_from_file_location(
    "install_data", Path(__file__).resolve().parents[1] / "tools" / "install_data.py"
)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def asset(data=b"pinned reference\n"):
    return {
        "path": "data/example.bin",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "url": "https://example.org/data",
    }


class Response(io.BytesIO):
    def geturl(self):
        return "https://example.org/data"


def test_download_repeat_offline_and_repair(tmp_path, monkeypatch):
    content = b"pinned reference\n"
    item = asset(content)
    calls = []

    def download(*args, **kwargs):
        calls.append(args)
        return Response(content)

    monkeypatch.setattr(installer, "urlopen", download)
    root, cache = tmp_path / "root", tmp_path / "cache"
    assert installer.install_asset(item, root, cache) == "installed"
    assert installer.install_asset(item, root, cache, offline=True) == "verified"
    target = root / item["path"]
    target.write_bytes(b"damaged")
    assert installer.install_asset(item, root, cache, offline=True) == "installed"
    assert target.read_bytes() == content
    assert len(calls) == 1


@pytest.mark.parametrize("data", [b"wrong size", b"x" * len(b"pinned reference\n")])
def test_invalid_download_never_replaces_existing_file(tmp_path, monkeypatch, data):
    monkeypatch.setattr(installer, "urlopen", lambda *a, **k: Response(data))
    item = asset()
    target = tmp_path / "root" / item["path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")
    with pytest.raises(installer.DataInstallError, match=r"mismatch|Oversized"):
        installer.install_asset(item, tmp_path / "root", tmp_path / "cache")
    assert target.read_bytes() == b"old"
    assert list((tmp_path / "cache").iterdir()) == []


def test_network_failure_removes_partial(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr(installer, "urlopen", fail)
    with pytest.raises(installer.DataInstallError, match="Cannot download"):
        installer.install_asset(asset(), tmp_path / "root", tmp_path / "cache")
    assert list((tmp_path / "cache").iterdir()) == []
    assert not (tmp_path / "root").exists()


def test_offline_corrupt_cache_fails_without_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline mode attempted network")

    monkeypatch.setattr(installer, "urlopen", forbidden)
    item = asset()
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / item["sha256"]).write_bytes(b"wrong")
    with pytest.raises(installer.DataInstallError, match="offline"):
        installer.install_asset(item, tmp_path / "root", cache, offline=True)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "a/../../escape", r"a\..\escape"])
def test_path_traversal_rejected(tmp_path, path):
    with pytest.raises(installer.DataInstallError, match="Unsafe"):
        installer.destination(tmp_path, path)


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(installer.DataInstallError, match="Symlink"):
        installer.destination(root, "link/escape")


def test_published_manifest_has_exact_assets_and_profiles():
    runtime = installer.load_manifest(installer.MANIFEST, "runtime")
    tests = installer.load_manifest(installer.MANIFEST, "test")
    assert runtime == tests
    assert len(runtime) == 81
    assert sum(a["size"] for a in runtime) == 82601858
    assert {a["group"] for a in runtime} == {
        "transcriptomes",
        "ais-reference",
        "expression-catalog",
    }


def test_check_missing_data_changes_nothing(tmp_path):
    assert installer.main(["--check", "--root", str(tmp_path)]) == 1
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("parent_link", [False, True])
def test_internal_symlink_rejected(tmp_path, parent_link):
    root = tmp_path / "root"
    root.mkdir()
    if parent_link:
        (root / "real").mkdir()
        (root / "link").symlink_to(root / "real", target_is_directory=True)
        relative = "link/data.bin"
    else:
        (root / "real").write_bytes(b"keep")
        (root / "link").symlink_to(root / "real")
        relative = "link"
    with pytest.raises(installer.DataInstallError, match="Symlink"):
        installer.destination(root, relative)
