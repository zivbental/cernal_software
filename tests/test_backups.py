"""Backups retain ownership and checksums; restore rejects corrupted or unsafe archives."""

import io
import sqlite3
import tarfile

import pytest
from django.db import connection

from apps.common.backups import BackupError, create_backup, restore_backup
from apps.common.checksums import sha256_file


@pytest.fixture
def backup_archive(transactional_db, dataset, tmp_path, media_root):
    path = tmp_path / "snapshot.tar.gz"
    staging = tmp_path / "staging"
    result = staging / "run" / "lease" / "result.json"
    result.parent.mkdir(parents=True)
    result.write_text('{"schema_version":"1"}')
    create_backup(connection, media_root, path, staging_root=staging)
    return path


def test_backup_restore_preserves_ownership_media_and_pending_results(
    backup_archive, dataset, tmp_path
):
    destination = tmp_path / "restored"
    database, media, staging = (
        destination / "database.sqlite3",
        destination / "media",
        destination / "staging",
    )
    manifest = restore_backup(backup_archive, database, media, staging_target=staging)
    with sqlite3.connect(database) as restored:
        owner, digest, name = restored.execute(
            "SELECT uploaded_by_id, checksum_sha256, file FROM datasets_dataset WHERE id = ?",
            [dataset.id.hex],
        ).fetchone()
        username = restored.execute(
            "SELECT username FROM accounts_user WHERE id = ?", [owner]
        ).fetchone()[0]
    assert owner == dataset.uploaded_by_id
    assert username == dataset.uploaded_by.username
    assert digest == sha256_file(media / name) == dataset.checksum_sha256
    assert (staging / "run" / "lease" / "result.json").read_text() == '{"schema_version":"1"}'
    assert manifest["files"]["database.sqlite3"]["sha256"] == sha256_file(database)


def rewrite_archive(source, target, *, edit=None, extra=None):
    with tarfile.open(source, "r:gz") as before, tarfile.open(target, "w:gz") as after:
        for member in before.getmembers():
            payload = before.extractfile(member).read()
            if edit:
                payload = edit(member.name, payload)
            member.size = len(payload)
            after.addfile(member, io.BytesIO(payload))
        if extra:
            member = tarfile.TarInfo(extra)
            member.size = 1
            after.addfile(member, io.BytesIO(b"x"))


def test_restore_rejects_changed_bytes_before_touching_targets(backup_archive, tmp_path):
    corrupt = tmp_path / "corrupt.tar.gz"
    rewrite_archive(
        backup_archive,
        corrupt,
        edit=lambda name, data: data + b"x" if name.startswith("media/") else data,
    )
    destination = tmp_path / "destination"
    with pytest.raises(BackupError, match=r"size|checksum"):
        restore_backup(
            corrupt,
            destination / "db",
            destination / "media",
            staging_target=destination / "staging",
        )
    assert not destination.exists()


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/outside", "media/../../outside"])
def test_restore_rejects_traversal_before_touching_targets(backup_archive, tmp_path, name):
    unsafe = tmp_path / "unsafe.tar.gz"
    rewrite_archive(backup_archive, unsafe, extra=name)
    destination = tmp_path / "destination"
    with pytest.raises(BackupError, match="path"):
        restore_backup(
            unsafe,
            destination / "db",
            destination / "media",
            staging_target=destination / "staging",
        )
    assert not destination.exists()


def test_restore_refuses_existing_database(backup_archive, tmp_path):
    database = tmp_path / "existing.sqlite3"
    database.write_text("valuable data")
    with pytest.raises(BackupError, match="must not exist"):
        restore_backup(backup_archive, database, tmp_path / "media")
    assert database.read_text() == "valuable data"


def test_backup_refuses_missing_referenced_media(transactional_db, dataset, tmp_path, media_root):
    dataset.file.storage.delete(dataset.file.name)
    output = tmp_path / "backup.tar.gz"
    with pytest.raises(BackupError, match="missing"):
        create_backup(connection, media_root, output)
    assert not output.exists()


def test_restore_requires_pending_result_destination(backup_archive, tmp_path):
    with pytest.raises(BackupError, match="pending results"):
        restore_backup(backup_archive, tmp_path / "db", tmp_path / "restore-media")
    assert not (tmp_path / "db").exists()
