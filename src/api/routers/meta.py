"""Operational endpoints.

``/version`` doubles as the capability document the frontend reads to populate gate
family and scoring profile choices — the in-process form of design map 08's
``GET /version``. It exposes no secrets or infrastructure details.
"""

from dataclasses import asdict

from django.conf import settings
from ninja import Router

from api.schemas import GateFamilyOut, VersionOut
from engine.client import load_engine

router = Router()

APP_VERSION = "0.1.0"
API_SCHEMA_VERSION = "1"


@router.get("/health", auth=None, url_name="health")
def health(request):
    return {"status": "ok"}


@router.get("/version", response=VersionOut, auth=None)
def version(request):
    capabilities = load_engine(settings.CERNAL_ENGINE).capabilities()
    return VersionOut(
        app_version=APP_VERSION,
        api_schema_version=API_SCHEMA_VERSION,
        engine=settings.CERNAL_ENGINE.rsplit(".", 1)[-1],
        engine_version=capabilities.engine_version,
        engine_schema_version=capabilities.schema_version,
        gate_families=[GateFamilyOut(**asdict(f)) for f in capabilities.gate_families],
        scoring_profiles=capabilities.scoring_profiles,
    )
