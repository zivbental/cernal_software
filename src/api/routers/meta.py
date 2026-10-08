"""Operational endpoints.

``/version`` doubles as the capability document the frontend reads to populate gate
family and scoring profile choices — the in-process form of design map 08's
``GET /version``. It exposes no secrets or infrastructure details.
"""

from dataclasses import asdict

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from ninja import Router

from api.schemas import BackboneInfoOut, GateFamilyOut, HardFilterOut, MetricInfoOut, VersionOut
from apps.analyses.worker import worker_available
from engine.client import load_engine

router = Router()

APP_VERSION = "0.1.0"
API_SCHEMA_VERSION = "1"


@router.get("/health", auth=None, url_name="health")
def health(request):
    return {"status": "ok"}


@router.get("/ready", auth=None, url_name="ready")
def ready(request):
    """Operational readiness for alerts; the web liveness probe remains separate."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        available = worker_available()
    except (DatabaseError, OSError):
        available = False
    return JsonResponse(
        {"status": "ready" if available else "unavailable"},
        status=200 if available else 503,
    )


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
        metrics=[MetricInfoOut(**asdict(m)) for m in capabilities.metrics],
        hard_filters=[HardFilterOut(**hf) for hf in capabilities.hard_filters],
        available_backbones=[
            BackboneInfoOut(**asdict(b)) for b in capabilities.available_backbones
        ],
        reviewer_login_enabled=settings.REVIEWER_LOGIN_ENABLED,
        supported_hosts=capabilities.supported_hosts,
        family_hosts=capabilities.family_hosts,
        supported_outputs=capabilities.supported_outputs,
        output_hosts=getattr(capabilities, "output_hosts", {}),
        backbone_hosts=getattr(capabilities, "backbone_hosts", {}),
        input_modes=capabilities.input_modes,
        limits=capabilities.limits,
        constraints=capabilities.constraints,
    )
