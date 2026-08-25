"""Checksum helpers for Platform-side files.

Deliberately duplicates ``engine.artifacts.sha256_file``. Platform code may import only
``engine.contract`` and ``engine.client`` (docs/software-design.md §3), so reaching into
``engine.artifacts`` to save six lines would break the boundary that lets the engine be
extracted into its own service later. ``tests/test_boundary.py`` enforces this — if you
are here to remove the duplication, read §3 first.
"""

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


def sha256_file(path: str | Path) -> str:
    """Streaming SHA-256 of a file on disk."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_upload(uploaded_file) -> str:
    """Streaming SHA-256 of a Django ``UploadedFile``, leaving it rewound for saving."""
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks(_CHUNK):
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
