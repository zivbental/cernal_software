"""Transport and queued result contract, independent of biological fixture selection."""

from types import SimpleNamespace

import pytest
from cernal import Client
from cernal.job import Job


class Session:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return SimpleNamespace(ok=True, json=lambda: {"job_id": "run", "status": "QUEUED"})


def test_wait_timeout_and_queued_options():
    session = Session()
    client = Client("test", base_url="http://example", session=session)
    job = client.design(
        wait=120,
        top_n=100,
        include_rejected=True,
        include_metrics=False,
        include_artifacts=["fasta", "csv"],
    )
    assert session.calls[0][2]["timeout"] == 130
    calls = []
    client.status = lambda _: {"status": "COMPLETED"}
    client.results = lambda _, **query: calls.append(query) or {"candidates": []}
    job.wait(poll=0)
    assert calls == [
        {
            "top_n": 100,
            "include_rejected": True,
            "include_metrics": False,
            "include_artifacts": "fasta,csv",
        }
    ]
    job.wait(poll=0)
    assert len(calls) == 1


@pytest.mark.parametrize("wait", [-1, 301, float("nan"), float("inf"), True])
def test_invalid_wait_does_not_submit(wait):
    session = Session()
    client = Client("test", base_url="http://example", session=session)
    with pytest.raises(ValueError):
        client.design(wait=wait)
    assert not session.calls


@pytest.mark.parametrize(
    "candidates,rank",
    [
        ([], None),
        ([{"rank": 1, "is_rejected": True}], None),
        ([{"rank": 3}, {"rank": None}, {"rank": 2}, {"rank": 1, "is_rejected": True}], 2),
    ],
)
def test_best_uses_accepted_rank(candidates, rank):
    best = Job(None, {"candidates": candidates}).best()
    assert (best["rank"] if best else None) == rank


def test_resumed_job_retains_explicit_options():
    calls = []
    client = SimpleNamespace(results=lambda _, **query: calls.append(query) or {"candidates": []})
    Job(client, {"job_id": "run", "status": "COMPLETED"}, result_options={"top_n": 1}).wait()
    assert calls == [{"top_n": 1}]
