"""Checksummed SQLite and file archives for an operator-controlled maintenance window."""

import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from apps.common.checksums import sha256_file


class BackupError(Exception):
    """Backup or restore could not guarantee a complete, verified snapshot."""


def safe_relative(name: str) -> Path:
    if not isinstance(name, str) or not name or "\\" in name:
        raise BackupError("Archive paths must be relative POSIX paths.")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or PureWindowsPath(name).drive:
        raise BackupError("Archive path escapes its root.")
    return Path(*path.parts)


def _referenced_files(database: Path) -> dict[str, str]:
    from apps.datasets.models import Dataset
    from apps.results.models import Artifact

    references = {}
    if not database.is_file():
        raise BackupError("The SQLite snapshot is missing.")
    with sqlite3.connect(database) as snapshot:
        if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("The SQLite snapshot failed its integrity check.")
        for model in (Dataset, Artifact):
            table = model._meta.db_table
            for name, digest in snapshot.execute(f'SELECT file, checksum_sha256 FROM "{table}"'):
                safe_relative(name)
                if name in references and references[name] != digest:
                    raise BackupError("One stored path has conflicting recorded checksums.")
                references[name] = digest
    return references


def create_backup(connection, media_root, output, *, staging_root=None):
    """Snapshot SQLite, verify every referenced file and write a checksummed archive."""
    output = Path(output)
    if output.exists():
        raise BackupError("The backup destination already exists.")
    if connection.vendor != "sqlite":
        raise BackupError("This backup command supports SQLite only.")
    if connection.in_atomic_block:
        raise BackupError("Backup must run outside an open database transaction.")
    media_root = Path(media_root).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cernal-backup-") as directory:
        temporary = Path(directory)
        database = temporary / "database.sqlite3"
        connection.ensure_connection()
        with sqlite3.connect(database) as snapshot:
            connection.connection.backup(snapshot)
        files = {"database.sqlite3": database}
        for name, digest in _referenced_files(database).items():
            source = (media_root / safe_relative(name)).resolve()
            if not source.is_relative_to(media_root) or not source.is_file():
                raise BackupError("Referenced media is missing or outside its storage root.")
            if not digest or sha256_file(source) != digest:
                raise BackupError("Referenced media does not match its recorded checksum.")
            files[f"media/{name}"] = source
        if staging_root is not None:
            root = Path(staging_root).resolve()
            if root.exists():
                for source in root.rglob("*"):
                    if source.is_symlink():
                        raise BackupError(
                            "Result staging contains a symlink; inspect it before backup."
                        )
                    if source.is_file():
                        files[f"staging/{source.relative_to(root).as_posix()}"] = source
        manifest = {
            "schema_version": "1",
            "database": "database.sqlite3",
            "files": {
                name: {"sha256": sha256_file(source), "size": source.stat().st_size}
                for name, source in files.items()
            },
        }
        manifest_path = temporary / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        archive_path = temporary / "backup.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(manifest_path, arcname="manifest.json", recursive=False)
            for name, source in files.items():
                archive.add(source, arcname=name, recursive=False)
        # A writer during the maintenance window invalidates the snapshot, rather
        # than silently producing an internally inconsistent backup.
        if any(
            sha256_file(source) != manifest["files"][name]["sha256"]
            for name, source in files.items()
        ):
            raise BackupError("Files changed during backup. Stop writers and retry.")
        created = False
        try:
            with (
                os.fdopen(
                    os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
                ) as handle,
                archive_path.open("rb") as source,
            ):
                created = True
                shutil.copyfileobj(source, handle, length=1024 * 1024)
        except Exception:
            if created:
                output.unlink(missing_ok=True)
            raise
    return manifest


def restore_backup(archive_path, database_target, media_target, *, staging_target=None):
    """Verify all archive bytes before populating new, empty target paths."""
    database_target, media_target = Path(database_target), Path(media_target)
    staging_target = Path(staging_target) if staging_target is not None else None
    if database_target.exists() or database_target.is_symlink():
        raise BackupError("The database restore target must not exist.")
    for target in (media_target, staging_target):
        if target is not None and (
            target.is_symlink()
            or (target.exists() and (not target.is_dir() or any(target.iterdir())))
        ):
            raise BackupError("File restore targets must be absent or empty directories.")
    with tempfile.TemporaryDirectory(prefix="cernal-restore-") as directory:
        temporary = Path(directory)
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                members = archive.getmembers()
                names = set()
                for member in members:
                    safe_relative(member.name)
                    if not member.isfile() or member.name in names:
                        raise BackupError("Archive entries must be unique regular files.")
                    names.add(member.name)
                manifest_member = archive.getmember("manifest.json")
                if manifest_member.size > 2 * 1024 * 1024:
                    raise BackupError("The backup manifest is too large.")
                manifest = json.load(archive.extractfile(manifest_member))
                if (
                    manifest.get("schema_version") != "1"
                    or manifest.get("database") != "database.sqlite3"
                ):
                    raise BackupError("Unsupported backup manifest.")
                files = manifest.get("files")
                if not isinstance(files, dict) or names != {"manifest.json", *files}:
                    raise BackupError("Archive contents do not match the manifest.")
                for name, metadata in files.items():
                    if (
                        not isinstance(metadata, dict)
                        or type(metadata.get("size")) is not int
                        or not 0 <= metadata["size"] <= 1024**4
                        or not isinstance(metadata.get("sha256"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"])
                    ):
                        raise BackupError("Invalid file metadata in the backup manifest.")
                    relative = safe_relative(name)
                    if name != "database.sqlite3" and not name.startswith(("media/", "staging/")):
                        raise BackupError("Archive contains an unsupported file namespace.")
                    member = archive.getmember(name)
                    if member.size != metadata["size"]:
                        raise BackupError("Archive file size does not match its manifest.")
                    target = temporary / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, target.open("wb") as handle:
                        shutil.copyfileobj(source, handle, length=1024 * 1024)
                    if sha256_file(target) != metadata["sha256"]:
                        raise BackupError("Archive file checksum does not match its manifest.")
        except (OSError, tarfile.TarError, KeyError, ValueError, TypeError) as exc:
            raise BackupError("The backup archive is malformed or incomplete.") from exc
        try:
            references = _referenced_files(temporary / "database.sqlite3")
        except sqlite3.DatabaseError as exc:
            raise BackupError("The archived SQLite database is invalid.") from exc
        for name, digest in references.items():
            entry = files.get(f"media/{name}")
            if not entry or entry["sha256"] != digest:
                raise BackupError("The database references media absent from the verified archive.")
        if any(name.startswith("staging/") for name in files) and staging_target is None:
            raise BackupError("This backup contains pending results; provide --staging.")
        # Everything is verified before any final target is touched.
        copied = []
        try:
            for name in files:
                if name == "database.sqlite3":
                    destination = database_target
                elif name.startswith("media/"):
                    destination = media_target / safe_relative(name.removeprefix("media/"))
                else:
                    destination = staging_target / safe_relative(name.removeprefix("staging/"))
                destination.parent.mkdir(parents=True, exist_ok=True)
                with (
                    destination.open("xb") as handle,
                    (temporary / safe_relative(name)).open("rb") as source,
                ):
                    copied.append(destination)
                    shutil.copyfileobj(source, handle, length=1024 * 1024)
        except Exception:
            for destination in copied:
                destination.unlink(missing_ok=True)
            raise
    return manifest
