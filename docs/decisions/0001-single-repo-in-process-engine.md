# 0001 — Single repository, in-process engine

**Status:** Accepted · 2026-08-25

## Context

The `Design Maps/` vault specifies two independently deployed systems — the CERNAL
Platform and the CERNAL Engine — communicating over a versioned, asynchronous REST
contract with published OpenAPI, contract tests, service-to-service authentication and
signed storage references.

Expected load is a few dozen users and roughly five analyses per day. The scientific
pipeline is not written yet. The team is an iGEM team with rotating student members and
no dedicated ops owner.

## Decision

One repository. One web process, one worker process. The engine is a **Python package**
(`src/engine/`) rather than a network service.

The boundary is preserved in full, as a module boundary:

- `src/engine/` must never import Django or Platform code.
- Platform code may import only `engine.contract` and `engine.client`.
- Communication is via frozen dataclasses whose fields deliberately match the payloads
  the maps specify for `POST /v1/jobs` and the result manifest.
- The rule is enforced by `tests/test_boundary.py`, not by convention.

## Consequences

**Gained.** No second deployment, no network contract to version and test, no
service-to-service authentication, no serialisation layer, no cross-repo release
coordination. The whole product can be built and demoed before any scientific code
exists.

**Given up.** The engine cannot scale independently and cannot run on HPC-adjacent
hosting. A long analysis occupies the single worker.

**Reversal.** Add `engine/service.py` exposing the contract over HTTP, add
`HttpEngineClient` implementing the same `Protocol`, change `CERNAL_ENGINE`. Because
the dataclasses already carry the right fields, this is a serialisation exercise. No
Platform code changes.

**Revisit when** the engine outgrows the VPS, Slurm access is granted, or two teams are
genuinely blocking each other.
