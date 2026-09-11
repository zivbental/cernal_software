"""cernal — a thin Python client for the CERNAL RNA logic circuit design API.

    from cernal import Client
    c = Client(api_key=os.environ["CERNAL_API_KEY"], base_url="https://your-cernal-host")
    df = c.design(trigger_sequence="AUGGCUAAGCUUAACGGAUCC", organism="ecoli").wait().to_dataframe()

Wraps five HTTP calls (docs/public-api.md §11): POST /api/design,
GET /api/design/{id}, GET /api/design/{id}/results,
GET /api/artifacts/{id}/download, GET /api/version. Anyone needing more talks to the
documented, self-describing REST API directly — that is the integration story, and it
is free (docs/public-api.md §12).
"""

from cernal.client import Client
from cernal.errors import (
    AuthError,
    CernalError,
    RateLimited,
    RunFailed,
    ValidationError,
)
from cernal.job import Job

__all__ = [
    "AuthError",
    "CernalError",
    "Client",
    "Job",
    "RateLimited",
    "RunFailed",
    "ValidationError",
]
__version__ = "0.1.0"
