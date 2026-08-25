# 0002 — SQLite and an ORM-backed task queue

**Status:** Accepted · 2026-08-25

## Context

The maps specify PostgreSQL plus Redis and Celery. That is four services to install,
configure, monitor and back up, for a workload of roughly five analyses per day.

## Decision

**SQLite** in WAL mode, and **django-q2** on its ORM broker.

- `DATABASE_URL` defaults to `sqlite:///var/cernal.db`. All code stays DB-agnostic.
- WAL, `synchronous=NORMAL`, a 10s busy timeout and foreign key enforcement are applied
  via a `connection_created` receiver in `apps/common/db.py`.
- The task queue is a table in the same database. One worker (`./do worker`).
- `max_attempts = 1` — an expensive scientific computation must never be silently
  re-run. `retry` is set above `timeout` so django-q2 does not re-queue a task that is
  still running.

## Consequences

**Gained.** Zero services beyond the two Python processes. Backup is copying one file.
Task successes and failures are browsable in Django admin, which matters for a team
with rotating members and no on-call rotation.

**Given up.** One writer at a time; no concurrent analyses; no multi-machine workers.
Postgres-specific features are unavailable.

**Reversal.** Postgres is a one-line `DATABASE_URL` change plus running migrations. A
Redis broker is a `Q_CLUSTER` change.

**Revisit when** write contention appears in the logs, or more than one analysis needs
to run at a time.
