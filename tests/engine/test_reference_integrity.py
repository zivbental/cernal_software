"""Offline integrity checks for installed references and maintainer downloads."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine import transcriptome
from engine.domain import Host
from engine.errors import InputValidationError


@pytest.fixture
def reference_files(monkeypatch, tmp_path):
    data_dir = tmp_path / "transcriptomes"
    data_dir.mkdir()
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(transcriptome, "_DATA_DIR", data_dir)
    monkeypatch.setattr(transcriptome, "_MANIFEST_PATH", manifest_path)
    transcriptome.load_transcriptome.cache_clear()
    transcriptome.reference_metadata.cache_clear()

    def write(files):
        entries = []
        for filename, content in files.items():
            (data_dir / filename).write_bytes(content)
            entries.append(
                {
                    "path": f"src/engine/data/transcriptomes/{filename}",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
            )
        manifest_path.write_text(json.dumps({"files": entries}), encoding="utf-8")
        return data_dir, manifest_path

    yield write
    transcriptome.load_transcriptome.cache_clear()
    transcriptome.reference_metadata.cache_clear()


@pytest.mark.parametrize("host", [Host.ECOLI, Host.HUMAN])
def test_verified_fasta_loads_with_overridden_data_directory(reference_files, host):
    content = b">gene1\nATGC\n"
    filename = transcriptome._FILES[host]
    if filename.endswith(".gz"):
        content = gzip.compress(content, mtime=0)
    reference_files({filename: content})

    first = transcriptome.load_transcriptome(host)
    assert first == {"gene1": "AUGC"}
    assert transcriptome.load_transcriptome(host) is first


def test_verified_metadata_loads_and_is_cached(reference_files):
    reference_files({"ecoli.json": b'{"aliases": {"thrA": "b0002"}}\n'})
    first = transcriptome.reference_metadata(Host.ECOLI)
    assert first == {"aliases": {"thrA": "b0002"}}
    assert transcriptome.reference_metadata(Host.ECOLI) is first


@pytest.mark.parametrize("filename", ["ecoli.fasta", "ecoli.json"])
@pytest.mark.parametrize("damage", ["missing", "truncated", "same_size"])
def test_missing_or_corrupt_files_fail_before_parsing(
    reference_files, monkeypatch, filename, damage
):
    original = b">gene1\nATGC\n" if filename.endswith(".fasta") else b'{"aliases": {}}\n'
    data_dir, _ = reference_files({filename: original})
    path = data_dir / filename
    if damage == "missing":
        path.unlink()
    elif damage == "truncated":
        path.write_bytes(original[:-1])
    else:
        path.write_bytes(b"x" * len(original))
    parser = MagicMock(side_effect=AssertionError("corrupt data reached the FASTA parser"))
    monkeypatch.setattr(transcriptome.SeqIO, "parse", parser)
    loader = (
        transcriptome.load_transcriptome
        if filename.endswith(".fasta")
        else transcriptome.reference_metadata
    )

    with pytest.raises(InputValidationError, match=r"python tools/install_data\.py"):
        loader(Host.ECOLI)
    parser.assert_not_called()


@pytest.mark.parametrize(
    "manifest_content",
    [None, b"broken json", b"[]", b'{"files": {}}', b'{"files": []}'],
)
def test_missing_or_invalid_manifest_has_setup_remediation(reference_files, manifest_content):
    _, manifest_path = reference_files({"ecoli.fasta": b">gene1\nATGC\n"})
    if manifest_content is None:
        manifest_path.unlink()
    else:
        manifest_path.write_bytes(manifest_content)

    with pytest.raises(InputValidationError, match=r"python tools/install_data\.py"):
        transcriptome.load_transcriptome(Host.ECOLI)


@pytest.mark.parametrize(
    ("field", "value"),
    [("sha256", "not a hash"), ("sha256", None), ("size", True), ("size", -1)],
)
def test_invalid_manifest_pin_fails_closed(reference_files, field, value):
    _, manifest_path = reference_files({"ecoli.fasta": b">gene1\nATGC\n"})
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][0][field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(InputValidationError, match="manifest is missing or invalid"):
        transcriptome.load_transcriptome(Host.ECOLI)


def test_duplicate_manifest_pin_fails_closed(reference_files):
    _, manifest_path = reference_files({"ecoli.fasta": b">gene1\nATGC\n"})
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] *= 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(InputValidationError, match="manifest is missing or invalid"):
        transcriptome.load_transcriptome(Host.ECOLI)


@pytest.mark.parametrize("content", [b"broken json", b"[]"])
def test_unreadable_metadata_is_an_input_error(reference_files, content):
    reference_files({"ecoli.json": content})
    with pytest.raises(InputValidationError, match=r"python tools/install_data\.py"):
        transcriptome.reference_metadata(Host.ECOLI)


def test_invalid_gzip_is_an_input_error(reference_files):
    reference_files({"human.fasta.gz": b"not gzip"})
    with pytest.raises(InputValidationError, match=r"python tools/install_data\.py"):
        transcriptome.load_transcriptome(Host.HUMAN)


@pytest.fixture
def human_sync(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[2] / "tools" / "sync_human_transcriptome.py"
    spec = importlib.util.spec_from_file_location("sync_human_transcriptome", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "CACHE", tmp_path)
    request = MagicMock(side_effect=AssertionError("unexpected network request"))
    monkeypatch.setattr(module.requests, "get", request)
    return module, request


def test_human_sync_checks_valid_cached_source_without_network(human_sync):
    module, request = human_sync
    content = b"verified source"
    target = module.CACHE / "source.fa.gz"
    target.write_bytes(content)

    assert (
        module.download("https://example.test/source.fa.gz", hashlib.sha256(content).hexdigest())
        == target
    )
    request.assert_not_called()


def test_human_sync_rejects_bad_cached_source(human_sync):
    module, request = human_sync
    target = module.CACHE / "source.fa.gz"
    target.write_bytes(b"corrupt cache")

    with pytest.raises(ValueError, match=r"Cached reference .* failed SHA-256"):
        module.download("https://example.test/source.fa.gz", "0" * 64)
    request.assert_not_called()


@pytest.mark.parametrize("valid", [True, False])
def test_human_sync_only_promotes_verified_download(human_sync, valid):
    module, request = human_sync
    content = b"verified source"
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [content[:4], b"", content[4:]]
    request.side_effect = None
    request.return_value = response
    target = module.CACHE / "source.fa.gz"
    expected = hashlib.sha256(content).hexdigest() if valid else "0" * 64

    if valid:
        assert module.download("https://example.test/source.fa.gz", expected) == target
        assert target.read_bytes() == content
    else:
        with pytest.raises(ValueError, match=r"Downloaded reference .* failed SHA-256"):
            module.download("https://example.test/source.fa.gz", expected)
        assert not target.exists()
    assert not list(module.CACHE.glob("*.partial"))


def test_human_sync_cleans_interrupted_download(human_sync):
    module, request = human_sync

    def interrupted_chunks(_chunk_size):
        yield b"partial download"
        raise module.requests.ConnectionError("connection interrupted")

    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.side_effect = interrupted_chunks
    request.side_effect = None
    request.return_value = response

    with pytest.raises(module.requests.ConnectionError, match="interrupted"):
        module.download("https://example.test/source.fa.gz", "0" * 64)
    assert not (module.CACHE / "source.fa.gz").exists()
    assert not list(module.CACHE.glob("*.partial"))


@pytest.mark.parametrize("valid", [True, False])
def test_human_sync_never_follows_predictable_partial_symlink(human_sync, valid):
    module, request = human_sync
    victim = module.CACHE / "unrelated-file"
    victim.write_bytes(b"preserve these bytes")
    legacy_partial = module.CACHE / "source.fa.partial"
    legacy_partial.symlink_to(victim)
    content = b"verified source"
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [content]
    request.side_effect = None
    request.return_value = response
    expected = hashlib.sha256(content).hexdigest() if valid else "0" * 64

    if valid:
        module.download("https://example.test/source.fa.gz", expected)
    else:
        with pytest.raises(ValueError, match="failed SHA-256"):
            module.download("https://example.test/source.fa.gz", expected)
    assert victim.read_bytes() == b"preserve these bytes"
    assert legacy_partial.is_symlink()
    assert list(module.CACHE.glob("*.partial")) == [legacy_partial]


@pytest.mark.parametrize("kind", ["symlink", "dangling_symlink", "directory"])
def test_human_sync_rejects_unsafe_cached_target(human_sync, kind):
    module, request = human_sync
    target = module.CACHE / "source.fa.gz"
    if kind == "directory":
        target.mkdir()
    else:
        destination = module.CACHE / "elsewhere"
        if kind == "symlink":
            destination.write_bytes(b"verified source")
        target.symlink_to(destination)

    with pytest.raises(ValueError, match="Unsafe cached reference"):
        module.download("https://example.test/source.fa.gz", "0" * 64)
    request.assert_not_called()


@pytest.mark.parametrize("kind", ["cache_symlink", "ancestor_symlink", "file"])
def test_human_sync_rejects_unsafe_cache_directory(human_sync, monkeypatch, kind):
    module, request = human_sync
    unsafe = module.CACHE / "unsafe"
    if kind == "file":
        unsafe.write_bytes(b"not a directory")
    else:
        destination = module.CACHE / "elsewhere"
        destination.mkdir()
        unsafe.symlink_to(destination, target_is_directory=True)
    cache = unsafe / "cache" if kind == "ancestor_symlink" else unsafe
    monkeypatch.setattr(module, "CACHE", cache)

    with pytest.raises(ValueError, match="Unsafe reference cache"):
        module.download("https://example.test/source.fa.gz", "0" * 64)
    request.assert_not_called()
