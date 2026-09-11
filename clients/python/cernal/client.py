"""The cernal HTTP client (docs/public-api.md §11)."""

from __future__ import annotations

import os
from typing import Any

import requests

from cernal.errors import AuthError, CernalError, RateLimited, ValidationError
from cernal.job import Job


class Client:
    """Holds a key and a base URL. Nothing else here is stateful.

    Args:
        api_key: An ``X-API-Key`` secret (``cern_live_...``). Falls back to the
            ``CERNAL_API_KEY`` environment variable when omitted.
        base_url: The deployment to talk to — no default, since there is no public
            CERNAL host to assume.
        dry_run: When true, every :meth:`design` call estimates instead of submitting,
            unless overridden per call.
        timeout: Seconds per HTTP request (not the run itself — see ``Job.wait``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str,
        dry_run: bool = False,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("CERNAL_API_KEY", "")
        if not self.api_key:
            raise CernalError("No API key. Pass api_key=..., or set CERNAL_API_KEY.")
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self._session = session or requests.Session()

    # --- the five calls -----------------------------------------------------------

    def design(
        self, *, wait: float | None = None, dry_run: bool | None = None, **fields: Any
    ) -> Job:
        """Submit a design request.

        Every keyword is a docs/public-api.md §9 field: ``trigger_sequence`` /
        ``dataset_id`` / ``dge_csv`` (exactly one), ``organism``,
        ``gate_families``, ``exclude_gate_families``, ``constraints``, ``scoring``,
        ``budget``, ``payload``, ``seed``, ``top_n``, ``include_rejected``,
        ``include_metrics``, ``include_artifacts``, ``idempotency_key``, ``strict``,
        ``notes``. Passed straight through as the JSON body — this client does not
        duplicate the server's validation.

        ``wait=`` blocks server-side for a finished result (ceiling 300s).
        ``dry_run=True`` estimates without submitting; unset, it uses the client's own
        default from ``Client(dry_run=...)``.
        """
        query: dict[str, Any] = {}
        effective_dry_run = self.dry_run if dry_run is None else dry_run
        if effective_dry_run:
            query["dry_run"] = "true"
        if wait is not None:
            query["wait"] = wait

        body = self._request("POST", "/api/design", json=fields, params=query)
        return Job(self, body)

    def status(self, job_id: str) -> dict:
        return self._request("GET", f"/api/design/{job_id}")

    def results(self, job_id: str, **query: Any) -> dict:
        return self._request("GET", f"/api/design/{job_id}/results", params=query)

    def artifact(self, artifact_id: str) -> bytes:
        return self._request("GET", f"/api/artifacts/{artifact_id}/download", raw=True).content

    def capabilities(self) -> dict:
        """``GET /api/version`` — gate families, scoring metrics and their units.
        Needs no key."""
        return self._request("GET", "/api/version", auth=False)

    # --- internals ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        auth: bool = True,
        raw: bool = False,
    ):
        headers = {"X-API-Key": self.api_key} if auth else {}
        response = self._session.request(
            method,
            f"{self.base_url}{path}",
            json=json,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(response)
        return response if raw else response.json()

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        if response.ok:
            return

        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        message = error.get("message") or response.text or f"HTTP {response.status_code}"
        code = error.get("code", "")
        detail = error.get("detail", {})

        if response.status_code == 401:
            raise AuthError(message)
        if response.status_code == 422:
            raise ValidationError(message, code=code, detail=detail)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimited(message, retry_after=float(retry_after) if retry_after else None)
        raise CernalError(f"{code or response.status_code}: {message}")
