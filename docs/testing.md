# Testing and verification

Source baseline: `main` at `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

Run from the repository root after [installation](development.md). These commands are
verification recipes, not a claim that every lane passed on the documentation revision.
Record command, revision, environment, outcome and limitations in evidence.

## Backend gates

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python tools/gen_api_surface.py --check
uv run pytest tests/engine -q
uv run pytest -q
```

The generated [API surface](api-surface.md) inventories engine Python symbols, not HTTP
routes. Do not hand-edit it. Its generator uses only the standard library and can also
be checked with `python tools/gen_api_surface.py --check` without scientific packages.
`tests/test_boundary.py` and `tests/engine/test_house_rules.py` enforce architectural
and shared-science rules. Do not weaken them to make an implementation pass.

## Real queue acceptance

```bash
uv run pytest tests/test_queued_worker_acceptance.py -q -s
```

This Linux/WSL test starts an actual separate fork-based worker against disposable
SQLite/media/staging/cache state, executes LocalEngine and verifies imported artifact
checksums. A synchronous task test or native Windows supervision mock is not equivalent.
See [Windows guide](windows-worker.md). Failure/recovery tests include
`tests/test_run_lifecycle.py`, `tests/test_run_recovery.py` and
`tests/test_worker_supervision.py`; these do not replace production process-tree drills.

## Frontend and browser

```bash
npm --prefix frontend ci
npm --prefix frontend run test:clean-build
npm --prefix frontend run build
npm --prefix frontend run check
cd frontend
npx playwright install --with-deps chromium
npm run test:browser
```

Build before `check` on a clean checkout so Vite generates the route tree.
Browser installation can require OS packages/admin rights. `check` includes TypeScript,
ESLint, SSR result checks, help/link contracts and RNA adapters. Browser contracts use
fixtures; the separate `node frontend/e2e/queued.mjs` exercises the actual SQLite queue
and LocalEngine. Review its setup before running on a machine with other app processes.
`./do smoke` instead targets a running development server; set `RUN_ID` to an existing
completed disposable run to cover results. Screenshots are not scientific evidence.

## Clients and CI

```bash
uv run --with requests --with 'cernal @ ./clients/python'   pytest clients/python/tests -c clients/python/tests/pytest.ini -q
```

[GitHub CI](../.github/workflows/ci.yml) defines backend, frontend, Python/R conformance,
real queued-browser, and manual/scheduled Windows/dependency-review lanes.
[GitLab CI](../.gitlab-ci.yml) is a separate configuration; its presence is not evidence
of an executed hosted pipeline. See [client scope](public-api.md): MATLAB remains
runtime-unverified; R live HTTP fixtures do not prove live worker-queue polling.

Scientific metric regression, deterministic seeds and real ViennaRNA tests establish
software properties. They do not establish wet-lab efficacy, calibrated probabilities,
clinical suitability, public hosting, or synthesis-release approval. Track those limits
in [status](status.md) and [scientific interpretation](scientific-interpretation.md).
