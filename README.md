# CERNAL

Design platform for RNA logic circuits — trigger discovery, gate design, scoring and
ranking from transcriptomic differential-expression data. Built for iGEM.

> **New here? Read [`docs/software-design.md`](docs/software-design.md) first.**
> It is the authoritative reference for the architecture, the domain model and the
> build order. This README only covers getting the thing running.

## Requirements

- Python **3.13** (see [§15](docs/software-design.md) — do not use 3.14 yet)
- [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Quickstart

```bash
./do install      # create the venv and install dependencies
./do migrate      # build the database at var/cernal.db
./do superuser    # create an admin login
./do dev          # serve on http://localhost:8000
```

In a second terminal, once analysis runs exist (Step 3):

```bash
./do worker       # background task worker
```

Run `./do help` for every available command.

## Current state

Step 0 (scaffold) is complete. The application boots, the database migrates and the
admin is reachable at `/admin/`. There is no product functionality yet — see the
status table at the top of [`docs/software-design.md`](docs/software-design.md).

## Layout

```
docs/     Design documentation and decision records — start with software-design.md
src/      Python source
  config/   Django project (settings, urls, wsgi)
  apps/     Django apps: accounts, common, projects, datasets, analyses, results
  api/      The only HTTP surface (django-ninja)
  engine/   Scientific engine — framework-free, never imports Django
frontend/ React application (Lovable origin)
tests/    Test suite
var/      All mutable state: database, uploads, artifacts, logs (gitignored)
deploy/   VPS deployment configuration
```

## The one rule

`src/engine/` must never import Django, and Platform code must never import the
engine's internals — only `engine.contract` and `engine.client`. This is what keeps
the engine extractable into its own service later. It is enforced by
`tests/test_boundary.py`. See [§3](docs/software-design.md).
