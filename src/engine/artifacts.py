"""Writing engine output files.

Artifacts are written under ``JobRequest.output_dir`` and referenced *relative* to it,
so the Platform can relocate the directory without rewriting references.
"""

import hashlib
from pathlib import Path

from engine.contract import ArtifactRef

_CHUNK = 1024 * 1024


def sha256_file(path: str | Path) -> str:
    """Streaming SHA-256 of a file. Never loads the whole file into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """SHA-256 of an in-memory payload, for content already held as bytes."""
    return hashlib.sha256(data).hexdigest()


def write_artifact(
    output_dir: str | Path,
    name: str,
    content: str | bytes,
    *,
    kind: str,
    media_type: str,
    candidate_ref: str | None = None,
) -> ArtifactRef:
    """Write one artifact and return its reference.

    ``name`` may contain forward slashes to nest files; parent directories are created.
    Content is written with an explicit UTF-8 encoding and ``\\n`` newlines so that the
    checksum is stable across platforms.
    """
    payload = content.encode("utf-8") if isinstance(content, str) else content

    destination = Path(output_dir) / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)

    return ArtifactRef(
        kind=kind,
        path=name,
        media_type=media_type,
        checksum_sha256=sha256_bytes(payload),
        candidate_ref=candidate_ref,
    )
