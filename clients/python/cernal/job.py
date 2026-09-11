"""A submitted design — a handle to wait on, read results from, download artifacts
from (docs/public-api.md §8)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from cernal.errors import RunFailed

if TYPE_CHECKING:
    from cernal.client import Client

_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


class Job:
    """Returned by :meth:`Client.design`.

    Already resolved if the server answered inline — a ``wait=`` that finished before
    its deadline, or an idempotent resubmission of an already-completed run — in which
    case :meth:`wait` is a no-op.
    """

    def __init__(self, client: Client, response: dict) -> None:
        self._client = client
        self._response = response
        self.job_id: str | None = response.get("job_id")
        self.estimate: dict = response.get("estimate") or {}
        self.resolved: dict = response.get("resolved") or {}
        self._results: dict | None = response if "candidates" in response else None

    def __repr__(self) -> str:
        return f"Job(job_id={self.job_id!r}, status={self.status!r})"

    @property
    def status(self) -> str | None:
        return self._response.get("status")

    def wait(self, *, timeout: float = 300.0, poll: float = 2.0, max_poll: float = 15.0) -> Job:
        """Poll with backoff until the run reaches a terminal state.

        Raises :class:`~cernal.errors.RunFailed` for a ``FAILED``/``CANCELLED`` run,
        and :class:`TimeoutError` if ``timeout`` elapses first — poll again by calling
        :meth:`wait` a second time; it will not resubmit.
        """
        if self._results is not None:
            return self

        if self.job_id is None:
            raise RunFailed("This job was never submitted (dry_run=True has no id to wait on).")

        deadline = time.monotonic() + timeout
        delay = poll
        status = self.status
        while status not in _TERMINAL:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Job {self.job_id} did not finish within {timeout}s.")
            time.sleep(min(delay, remaining))
            self._response = self._client.status(self.job_id)
            status = self._response["status"]
            delay = min(delay * 1.5, max_poll)

        if status != "COMPLETED":
            raise RunFailed(
                f"Run {self.job_id} ended {status}.",
                status=status,
                error_summary=self._response.get("error_summary", ""),
            )

        self._results = self._client.results(self.job_id)
        return self

    # --- results -----------------------------------------------------------------

    def candidates(self) -> list[dict]:
        if self._results is None:
            raise RunFailed("Call wait() before reading results.")
        return self._results.get("candidates", [])

    def best(self) -> dict | None:
        """The highest-ranked candidate, or ``None`` if every candidate was rejected."""
        candidates = self.candidates()
        return candidates[0] if candidates else None

    def to_dicts(self) -> list[dict]:
        return self.candidates()

    def to_dataframe(self) -> Any:
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                "to_dataframe() needs pandas. `pip install cernal[pandas]`, "
                "or use to_dicts() instead."
            ) from exc
        return pd.DataFrame(self.candidates())

    def artifact(self, kind: str) -> _Artifact:
        """The first artifact of ``kind`` (e.g. ``\"fasta\"``, ``\"structure_svg\"``)
        on this run — fetched fresh, so a prior ``include_artifacts`` at submission
        time is not required."""
        if self.job_id is None:
            raise RunFailed("This job was never submitted.")
        results = self._client.results(self.job_id, include_artifacts=kind)
        matches = [a for a in results.get("artifacts", []) if a["kind"] == kind]
        if not matches:
            raise KeyError(f"No artifact of kind '{kind}' on job {self.job_id}.")
        return _Artifact(self._client, matches[0])


class _Artifact:
    """Returned by :meth:`Job.artifact`. Downloads only when :meth:`save` is called."""

    def __init__(self, client: Client, meta: dict) -> None:
        self._client = client
        self.meta = meta

    def save(self, path: str) -> None:
        content = self._client.artifact(self.meta["id"])
        with open(path, "wb") as handle:
            handle.write(content)
