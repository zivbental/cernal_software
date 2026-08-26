# 0004 — django-ninja rather than Django REST Framework

**Status:** Accepted · 2026-08-25

## Context

The API surface is roughly two dozen endpoints (docs/architecture.md §7). The maps
call for a "Central Typed API Client" in the frontend, generated from a published
schema.

## Decision

Use **django-ninja**.

## Consequences

**Gained.** Request and response shapes are Pydantic models — declarative, and close in
spirit to the engine's frozen dataclasses, so the two contracts read alike. OpenAPI is
generated automatically at `/api/openapi.json`, which gives the frontend a typed client
for free rather than as a maintained artifact. Substantially less machinery than
serializers, viewsets, routers and permission classes for endpoints that are mostly
straightforward reads.

**Given up.** DRF's browsable API, its large ecosystem of third-party packages, and its
much larger pool of existing examples and Stack Overflow answers — a real cost for a
team of rotating students.

**Reversal.** Endpoints are thin; business logic lives in `services.py` modules, not in
the API layer. Rewriting the routers against DRF would not touch application logic.

**Revisit when** a needed integration exists only for DRF.
