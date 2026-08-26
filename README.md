# CERNAL

Design platform for RNA logic circuits — trigger discovery, gate design, scoring and
ranking from transcriptomic differential-expression data. Built for iGEM.

> **New here?** Start at [`docs/`](docs/README.md).
> [`docs/architecture.md`](docs/architecture.md) is the authoritative reference for how
> the system is built; [`docs/ROADMAP.md`](docs/ROADMAP.md) is what is left to do. This
> README only covers getting the thing running.

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

In a second terminal:

```bash
./do worker       # background task worker — without it, runs sit in QUEUED forever
```

Run `./do help` for every available command.
[`docs/development.md`](docs/development.md) covers day-to-day work.

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

Both run in CI on every push — see [`.gitlab-ci.yml`](.gitlab-ci.yml).

## Current state

**Steps 0–4 are complete.** The full product works end to end in the browser: register,
log in, create a project, upload a dataset (or paste a trigger), configure a run, watch it
progress, and explore ranked candidates with metric decompositions and downloadable
artifacts. 415 tests pass.

**The science is not written.** `CERNAL_ENGINE` defaults to `MockEngine`, which produces
deterministic fake results in exactly the shape the real engine will. The engine's classes,
methods and signatures all exist as documented stubs — see
[`docs/ROADMAP.md`](docs/ROADMAP.md).

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
