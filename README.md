# CERNAL

Computational design platform for RNA logic candidates: trigger discovery, single-input
toehold design, scoring and ranking from direct sequences, named reference genes or
differential-expression tables. Built by the iGEM 2026 Tel Aviv University team.

**The default is `CERNAL_ENGINE=engine.client.LocalEngine`.** It uses real ViennaRNA
folding. The former `MockEngine` has been removed. Current results are computational
predictions, not simulated demo values and not experimentally validated circuits.

Start with [the documentation index](docs/README.md), [architecture](docs/architecture.md)
and [current limitations](docs/ROADMAP.md). Signed-in help lives at `/use-cases`, `/guide`
and `/faq`; [the maintainer map](docs/user-help.md) connects those pages to source.

For production preparation, configuration, preflight and recovery, use the
[authoritative operations runbook](docs/operations.md). `./do production --help`
lists the preparation commands; service activation is a separate operator step.

## Current application capabilities

`GET /api/version` is the installed build's capability contract. It exposes supported
hosts, input modes, gate families, payloads, constraints and scoring metrics. Inspect it
before assuming a registry entry or notebook is a supported application workflow.

- Direct RNA/DNA, named reference genes, and DE tables for E. coli, yeast, Human and
  C. acnes. DE uploads accept CSV, TSV, TXT and XLSX; raw-count inference is not provided.
- Production submissions support **one input and one gate**, using supported
  single-input toehold families, plus **one two-input AND gate per run**: bacterial
  equilibrium (`prokaryotic_toehold_and`, E. coli) or eukaryotic joint-stem sampling
  (`eukaryotic_toehold_and`, Human and yeast). Both take their two genes from a DE table
  ([docs/and-gate.md](docs/and-gate.md)). GFP and custom coding sequences are supported
  outputs. Bacterial searches evaluate a bounded design set through the switch's
  linker, excluding the output CDS, using the declared equilibrium model. Other
  AND chemistries, antisense and CRISPR workbenches are not production
  integrations.
- Human references use pinned Ensembl release 116 mature cDNA/noncoding transcripts.
  Human assembly uses CMV/hGH parts with an uploaded backbone or a bare expression cassette.
- Runs retain configuration, metrics, rejection reasons and artifacts. Sequence release
  is a separate fail-closed policy decision: an unconfigured screening adapter holds
  sequence exports. Software availability does not establish specificity or efficacy.

Read [scientific interpretation](docs/scientific-interpretation.md) before comparing
metrics: single-input bacterial leakage measures only AUG's three-base marginal accessibility;
dynamic range is a floored accessibility ratio; success is an uncalibrated binding
heuristic. No established transcriptome-wide off-target or wet-lab validation is claimed.
The bacterial AND family instead reports whole-window equilibrium opening across
four input states through the linker, excluding the output CDS, before final ranking.

## Installation and reproducible quickstart

Use Python **3.13** (`>=3.13,<3.14`), [uv](https://docs.astral.sh/uv/), Node **22+**, npm,
Git and Bash for `./do`. Locked Python dependencies include ViennaRNA: it is an active
folding backend, not a planned optional integration.

These commands target Linux or Linux inside WSL2. Install Node and uv inside that
environment and keep its checkout and dependencies there. Native Windows engine/tests
support does not imply application-worker support: the locked Django Q2 worker requires
`fork`. Run the application server and worker inside Linux/WSL2.
The [Windows/WSL worker guide](docs/windows-worker.md) provides operational
instructions and a real queued-worker acceptance test.

```bash
git clone https://github.com/zivbental/cernal_software.git
cd cernal_software
git rev-parse HEAD                 # record the exact revision being tested
uv sync --locked --extra dev
uv run --locked python tools/install_data.py
(cd frontend && npm ci && npm run build)
uv run python manage.py migrate    # fresh checkout: disposable var/cernal.db
uv run python manage.py check
uv run python manage.py createsuperuser
./do dev 8000                      # http://localhost:8000
```

The standard build generates the route tree before typechecking; no prior generated
files or `build:fast` bootstrap are required. Installing frontend
dependencies explicitly avoids relying on an existing `node_modules` folder.
`./do install` performs the locked Python sync and verified data installation;
`./do install-frontend` runs `npm ci`. See [data installation](docs/data-installation.md)
for downloaded sources, cache/offline use and `./do install-data --check` verification.
IBBIS screening software/databases and sequence-release authorization require separate
provisioning and are not enabled by this installation.
An empty `.env` uses development defaults; [`.env.example`](.env.example) documents them.
Use a fresh checkout for experiments: database, media, logs and generated artifacts live
under gitignored `var/`. Do not point a smoke run at a production database.

`./do dev` supervises the web server and background worker; `./do worker` is for a
separately managed worker. After logging in, choose a supported single-input workflow
at `/use-cases`, start with a small run and inspect warnings and rejected candidates.
Candidate counts can be zero and depend on input and constraints. A completed job is
not proof of a functional construct. Keep the input, run configuration, revision and
available manifest alongside any reported computational result.

For frontend hot reload, `./do frontend` starts Vite on :5173 and proxies `/api` to
:8000. See [development](docs/development.md) for additional commands.
`./do build-frontend` calls that same standard `npm run build`. If a build is missing,
`./do dev` installs missing frontend dependencies with `npm ci` and builds it first.

### Verify the checkout

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run pytest -q
(cd frontend && npm run check && npm run build)
```

These are computational/software checks, not biological validation. GitHub CI runs on
pull requests and pushes to `main`; manual/scheduled acceptance lanes are separate.
See [the workflow](.github/workflows/ci.yml) for the exact jobs.

## Research workbenches and historical records

Offline [trigger/nucleation ranking](docs/trigger-nucleation-ranking.md) preserves
nucleation-first ranking and offers an explicit geometric-mean sensitivity mode.
Notebook experiments under `src/engine/gates/notebooks/`, CRISPR workbenches, historical
design maps and dated audits describe research or past states. Their results and
metrics do not replace the current application's capability contract.

As checked on **2026-10-12** against main `2baa75a7f0dc89f9aafac58dad50da5982f3f56a`:

- [PR 68](https://github.com/zivbental/cernal_software/pull/68) is an **unmerged research
  workbench** for eukaryotic single/AND stem-opening reports (`eu_and_v3`), not an
  integrated application AND workflow.
- [PR 69](https://github.com/zivbental/cernal_software/pull/69) is an **unmerged draft
  frontend screening contract/UI**. It does not implement or invoke Common Mechanism
  or establish full-construct screening or release authorization.

GitHub source and [`.gitlab-ci.yml`](.gitlab-ci.yml) are present. As checked on
**2026-10-19 at 02:42 UTC**, the official
[CERNAL iGEM GitLab project](https://gitlab.igem.org/2026/software/tau-israel/cernal)
contained only the four-file starter template at main commit
`3fe39b407120b501421be3f82e44b73c6d741783`; the application had not yet been published
there. A matching software commit and pipeline evidence are still needed to verify
the mirror. The [F5 verification record](docs/evidence/audit-f5-documentation-2026-10-12.md)
describes the earlier audit state.

## Layout and boundaries

```text
docs/       Engineering documentation and dated evidence
src/config/ Django configuration
src/apps/   Platform data, jobs, accounts and results
src/api/    HTTP API (django-ninja)
src/engine/ Framework-free scientific engine
frontend/   React application
tests/      Software and computational regression tests
var/        Local mutable state (gitignored)
deploy/     Deployment configuration
```

`src/engine/` must never import Django. Platform code imports only `engine.contract`
and `engine.client` from the engine. [The boundary test](tests/test_boundary.py)
enforces this rule.

## License, attribution and citation

Apache License 2.0: [LICENSE](LICENSE), [NOTICE](NOTICE). Copyright 2026 iGEM TAU 2026
Team, Tel Aviv University. ViennaRNA has separate licensing constraints; consult
[attribution](docs/attribution.md) before describing a distributed bundle's licensing.
That document also records third-party contributions and AI-assisted work disclosures.
The original Lovable frontend export is preserved in [design-reference](docs/design-reference/);
[ADR 0005](docs/decisions/0005-static-spa-not-tanstack-start.md) records the rewrite.
See [CITATION.cff](CITATION.cff) for citation metadata.
