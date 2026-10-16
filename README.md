# CERNAL

Computational design platform for RNA logic candidates, built by the iGEM 2026 Tel Aviv
University team. Start with an RNA target sequence, a named reference gene, or a differential-expression
table; inspect ranked single-input toehold candidates, model limitations and traceable artifacts.

**The default is `CERNAL_ENGINE=engine.client.LocalEngine`.** ViennaRNA is an active
folding backend. Generated candidates are computational predictions; generation does not establish
experimental validation. Specific comparisons with measured structure data are retained in the
[evidence guide](docs/evidence/README.md).

## Choose your starting point

- **New researcher:** [overview and reading paths](docs/README.md), then the [tutorial](docs/tutorial.md).
- **Run locally:** [installation and development](docs/development.md).
- **Understand the science:** [methods](docs/engine.md), [metric interpretation](docs/scientific-interpretation.md), [evidence](docs/evidence/README.md).
- **Integrate or operate:** [HTTP API](docs/public-api.md), [configuration](docs/configuration.md), [deployment](docs/deployment.md), [security](docs/security.md).
- **Review or contribute:** [pinned feature status](docs/status.md), [limitations and next work](docs/ROADMAP.md), [contributing](CONTRIBUTING.md).

## What this revision supports

Documentation baseline: main [`c1bb92cc085a6bad272298b81bda28c22b1d57f5`](https://github.com/zivbental/cernal_software/commit/c1bb92cc085a6bad272298b81bda28c22b1d57f5), checked 16 October 2026.
`GET /api/version` is the running build's capability contract. A notebook or registry entry
is not sufficient evidence that a workflow is available in the application.

- RNA target, named-gene and DE input for E. coli, yeast, Human and C. acnes.
  Direct input also accepts the DNA alphabet and normalizes T to U for RNA computation;
  this is not a separate DNA-circuit design workflow.
- One input and one gate per production submission; supported single-input toehold families,
  GFP and custom coding-sequence outputs. DE tables accept CSV, TSV, TXT and XLSX; raw-count inference is absent.
- Configuration, warnings, rejection reasons, scores and artifact provenance retained with runs.
- Sequence release is a separate fail-closed decision: an unconfigured screening adapter holds exports.

Selectable AND work, stem-opening research and the IBBIS adapter are **branch-only** at
this baseline. [Status](docs/status.md) pins their commits and explains integration boundaries.
There is no established transcriptome-wide off-target validation, calibrated efficacy claim,
general wet-lab validation of generated circuits, or integrated ordering service.
Bacterial leakage is AUG-only marginal accessibility; dynamic range is a floored accessibility
ratio, and predicted success is an uncalibrated binding heuristic. Read the
[interpretation guide](docs/scientific-interpretation.md) before comparing scores.

## NucSyn research inputs and credit

[NucSyn Platform](https://github.com/YehudaLandau/NucSyn-Platform), released by Yehuda Landau
and credited to Landau and colleagues, supplies externally generated switch designs used by
a CSV-consuming research notebook. See [NucSyn provenance, citation and scope](docs/nucsyn.md)
for the input contract, independent CERNAL evaluation and licensing boundary. This is distinct
from the production LocalEngine/ViennaRNA path; the v0.1.2 release is not evidence of a runtime integration.

## Reproducible local quickstart

Use Python **3.13**, uv, Node **22+**, npm, Git and Bash. Run the application server and
Django Q2 worker on Linux or Linux inside WSL2; native Windows computational tests do not
establish native Windows queued-worker support. See the [Windows/WSL guide](docs/windows-worker.md).

```bash
git clone https://github.com/zivbental/cernal_software.git
cd cernal_software
git rev-parse HEAD
uv sync --locked --extra dev
(cd frontend && npm ci && npm run build)
uv run python manage.py migrate
uv run python manage.py check
uv run python manage.py createsuperuser
./do dev 8000
```

Use a fresh development checkout. Mutable database, uploads and outputs live under gitignored
`var/`; do not aim experiments at production storage. Sign in at http://localhost:8000 and
follow the [tutorial](docs/tutorial.md). Zero candidates is a possible valid outcome.
The standard clean-build fix ([PR 70](https://github.com/zivbental/cernal_software/pull/70))
and Windows/WSL guidance were merged through PR 80; they are not pending prerequisites.

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python tools/gen_api_surface.py --check
uv run pytest -q
(cd frontend && npm run check && npm run build)
```

See [testing](docs/testing.md) for scope and [this documentation verification](docs/evidence/documentation-reorganization-2026-10-16.md)
for checks actually executed. Software tests do not establish biological performance.

## Project boundaries and provenance

The framework-free engine lives in `src/engine/`; platform code uses `engine.contract` and
`engine.client`. Django apps/API, React UI and managed workers provide the application.
[Architecture](docs/architecture.md) explains the boundaries.

Historical experiments, data and audit evidence are preserved and indexed in the
[evidence guide](docs/evidence/README.md) and [archive](docs/archive/README.md). Superseded
instructions are outside the primary reading path. [The preservation inventory](docs/evidence/documentation-inventory.md)
maps every original documentation source.

Apache 2.0: [LICENSE](LICENSE), [NOTICE](NOTICE), [citation](CITATION.cff).
[Attribution](docs/attribution.md) records contributors, AI-tool disclosure, external code,
and dependency licensing qualifications. The dedicated iGEM GitLab software project and
matching pipeline have not been verified; a config file or separate wiki does not prove hosting.
