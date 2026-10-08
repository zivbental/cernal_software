# CERNAL

Design platform for RNA logic circuits — trigger discovery, gate design, scoring and
ranking from transcriptomic differential-expression data. Built for iGEM.

> **New here?** Start at [`docs/`](docs/README.md).
> [`docs/architecture.md`](docs/architecture.md) is the authoritative reference for how
> the system is built; [`docs/ROADMAP.md`](docs/ROADMAP.md) is what is left to do. This
> README only covers getting the thing running.

Signed-in users can choose a supported workflow at `/use-cases`, follow the practical
guide at `/guide`, and troubleshoot at `/faq`. These authenticated React pages live in
`frontend/src/routes/`; [the maintainer map](docs/user-help.md) ties their claims to source.

## Requirements

- Python **3.13** — not 3.14; scientific wheels lag new CPython releases by months
- [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node 22+** — only to build the frontend. On WSL, install it *inside* WSL via
  [`nvm`](https://github.com/nvm-sh/nvm), not on `/mnt/c`

## Quickstart

```bash
./do install      # create the venv and install dependencies
./do migrate      # build the database at var/cernal.db
./do superuser    # create an admin login
./do dev          # serve on http://localhost:8000
```

`./do dev` starts the web server and background worker together, restarts a failed
worker, and stops both when you exit. Local `manage.py runserver` uses the same
supervision. `./do worker` remains available for a separately managed worker.
The run screen reports when the worker is offline.

Run `./do help` for every available command.
[`docs/development.md`](docs/development.md) covers day-to-day work.

### Trigger/nucleation analysis utility

Reusable offline ranking for marginal trigger/nucleation accessibility lives in
[`tools/trigger_nucleation_ranking.py`](tools/trigger_nucleation_ranking.py). The preserved
default is lexicographic nucleation-first ranking; balanced geometric-mean ranking is an
explicit separate sensitivity mode. See
[`docs/trigger-nucleation-ranking.md`](docs/trigger-nucleation-ranking.md) for semantics,
provenance and usage.

### Building the frontend

`./do dev` builds the React app once if it is missing. To rebuild it explicitly, or to
work on it with hot reload:

```bash
./do build-frontend   # production build into src/static/app/
./do frontend         # Vite dev server on :5173, proxying /api to :8000
```

### Verifying the build

```bash
./do lint         # ruff, TypeScript, ESLint, and a server-render regression test
./do test         # the full pytest suite
```

GitHub CI runs for pull requests and pushes to `main`; it does not run for every
feature-branch push. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Current state

`CERNAL_ENGINE` defaults to `MockEngine`, which produces deterministic simulated results.
`LocalEngine` implements scoped direct-transcript and E. coli/yeast DE paths, but several
scientific stages remain partial. Capability availability is not evidence that a complete
pipeline exists; consult current source, run warnings, and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Layout

```
docs/     Design documentation — start with docs/README.md
src/      Python source
  config/   Django project (settings, urls, wsgi)
  apps/     Django apps: accounts, common, projects, datasets, analyses, results, web
  api/      The only HTTP surface (django-ninja)
  engine/   Scientific engine — framework-free, never imports Django
frontend/ React application (Lovable origin)
tests/    Test suite
var/      All mutable state: database, uploads, artifacts, logs (gitignored)
deploy/   Deployment configuration
```

## The one rule

`src/engine/` must never import Django, and Platform code must never import the engine's
internals — only `engine.contract` and `engine.client`. This is what keeps the engine
extractable into its own service later. It is enforced by `tests/test_boundary.py`. See
[`docs/architecture.md` §3](docs/architecture.md).

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

Copyright 2026 iGEM TAU 2026 Team, Tel Aviv University.

One dependency is worth flagging: the scientific engine's planned RNA folding backend,
**ViennaRNA**, is *not* under an OSI-approved license. CERNAL does not redistribute it —
it is installed by the user — but any claim that a distributed bundle is wholly open
source has to account for it. [`docs/attribution.md`](docs/attribution.md) explains the
constraint.

## Attribution

CERNAL was built by the iGEM 2026 Tel Aviv University team. Third-party components,
outside contributions and the disclosure of AI-assisted work required by iGEM's
[AI policy](https://igem.org/legal?tab=ai-policy-teams) are recorded in
[`docs/attribution.md`](docs/attribution.md).

The React frontend originates from a [Lovable](https://lovable.dev) design; the original
export is preserved in [`docs/design-reference/`](docs/design-reference/) and
[ADR 0005](docs/decisions/0005-static-spa-not-tanstack-start.md) records what was
stripped and rewritten by hand.

## A note on results

With the default `CERNAL_ENGINE=engine.client.MockEngine`, every number the product
displays is **deterministic fake output**. The interface says so in its footer. Do not
publish a MockEngine screenshot as a scientific result.

## Citing

See [`CITATION.cff`](CITATION.cff).

The local engine supports all four organisms (E. coli, yeast, Human, C. acnes) with
differential-expression tables, direct RNA/DNA sequences, and named reference genes.
CSV, TSV, TXT, and XLSX uploads work through the engine. Human gene discovery uses
pinned Ensembl release 116 mature cDNA/noncoding transcripts; gene symbols and stable
IDs resolve offline. Human constructs use CMV/hGH parts and an uploaded mammalian
backbone, or a bare expression cassette. Local development supervises the worker and
keeps its heartbeat separate from SQLite result imports.
