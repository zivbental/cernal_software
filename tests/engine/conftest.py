"""Fixtures for engine tests.

These tests never touch Django — they exercise ``src/engine/`` as the standalone,
framework-free package it is meant to be.
"""

import hashlib

import pytest

from engine.contract import SCHEMA_VERSION, JobRequest

DATASET_CONTENT = (
    "gene_id,base_expression,target_expression,log2fc,padj\n"
    "lacZ,0.8,6.4,3.0,0.001\n"
    "rpoS,2.1,0.4,-2.4,0.004\n"
    "katG,1.2,5.9,2.3,0.002\n"
)


@pytest.fixture
def dataset(tmp_path):
    """A real file on disk, so the engine's checksum path is genuinely exercised."""
    path = tmp_path / "expression.csv"
    path.write_text(DATASET_CONTENT, encoding="utf-8")
    return path


@pytest.fixture
def make_request(tmp_path, dataset):
    """Factory for JobRequests. Every keyword overrides a default."""

    def _make(**overrides) -> JobRequest:
        output_dir = overrides.pop("output_dir", None)
        if output_dir is None:
            output_dir = tmp_path / f"out-{overrides.get('idempotency_key', 'default')}"
        output_dir = str(output_dir)

        defaults = {
            "schema_version": SCHEMA_VERSION,
            "run_id": "11111111-1111-1111-1111-111111111111",
            "idempotency_key": "key-alpha",
            "input_path": str(dataset),
            "input_checksum": hashlib.sha256(DATASET_CONTENT.encode()).hexdigest(),
            "organism": "E. coli",
            "params": {},
            "gate_families": ["toehold"],
            "scoring_profile": "default",
            "seed": 7,
            "output_dir": output_dir,
        }
        defaults.update(overrides)
        return JobRequest(**defaults)

    return _make


@pytest.fixture
def progress():
    """Records every progress callback. Always allows the run to continue."""

    class Recorder:
        def __init__(self) -> None:
            self.calls: list[tuple[int, str]] = []

        def __call__(self, percent: int, stage: str) -> bool:
            self.calls.append((percent, stage))
            return True

    return Recorder()
