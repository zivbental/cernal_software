"""Media removal observes database commits and a conservative orphan grace period."""

import io
import json
import os
import time
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import transaction

from apps.datasets.services import delete_dataset


def test_unused_dataset_file_is_removed_only_after_commit(
    dataset, django_capture_on_commit_callbacks
):
    path = Path(dataset.file.path)
    with django_capture_on_commit_callbacks(execute=True):
        delete_dataset(dataset)
        assert path.exists()
    assert not path.exists()


def test_rolled_back_dataset_delete_preserves_bytes_and_record(
    dataset, django_capture_on_commit_callbacks
):
    path = Path(dataset.file.path)
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError), transaction.atomic():
            delete_dataset(dataset)
            raise RuntimeError("rollback")
    assert path.exists()
    assert type(dataset).objects.filter(file=dataset.file.name).exists()


def test_orphan_cleanup_is_dry_by_default_and_preserves_references_and_young_files(
    dataset, media_root
):
    root = Path(media_root)
    old = root / "artifacts" / "old" / "orphan.txt"
    old.parent.mkdir(parents=True)
    old.write_text("orphan")
    young = old.with_name("young.txt")
    young.write_text("pending transaction")
    threshold = time.time() - 48 * 3600
    os.utime(old, (threshold, threshold))
    os.utime(dataset.file.path, (threshold, threshold))
    output = io.StringIO()
    call_command("cleanup_media", stdout=output)
    assert json.loads(output.getvalue())["orphans"] == ["artifacts/old/orphan.txt"]
    assert old.exists()
    output = io.StringIO()
    call_command("cleanup_media", apply=True, stdout=output)
    assert not old.exists()
    assert young.exists()
    assert Path(dataset.file.path).exists()
