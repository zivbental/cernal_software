# Development and installation

Source baseline: `main` at `c1bb92cc085a6bad272298b81bda28c22b1d57f5` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

## Requirements and checkout

Use Python 3.13 and uv ([pyproject](../pyproject.toml), [lock](../uv.lock)). The complete
web/worker application requires Linux or [WSL2](windows-worker.md); native Windows
engine tests do not prove queue support. Node 22 is the CI frontend baseline.
Keep clones outside OneDrive/Dropbox/Google Drive; use the Linux filesystem in WSL.

Install uv from [its official instructions](https://docs.astral.sh/uv/getting-started/installation/)
and review installer commands under your local policy. From a fresh checkout:

```bash
git clone https://github.com/zivbental/cernal_software.git
cd cernal_software
uv sync --locked --extra dev
uv run python manage.py migrate
uv run python manage.py check
npm --prefix frontend ci
npm --prefix frontend run build
uv run python manage.py createsuperuser
./do dev
```

Run commands at the repository root unless stated otherwise. `migrate` and account creation change this local installation. `./do dev` serves
http://localhost:8000 and supervises the development worker. Do not start an extra
worker alongside it. Ctrl+C stops its managed processes. `manage.py runserver` also
uses this supervisor in development. Production instead uses [systemd](operations.md).

The frontend build is required on a clean checkout: `./do dev` attempts `build:fast`
if no built index exists, but does not install Node dependencies. An existing built
frontend permits backend-only work without Node. For hot reload, keep `./do dev`
running and start `./do frontend` in another terminal, then visit localhost:5173.
Vite proxies API/admin/media requests to Django.

An empty `.env` works for local development. See [configuration](configuration.md)
for defaults and production requirements. Local reviewer login is enabled by default;
use only disposable data. Registered accounts otherwise require staff approval.

## Daily workflow

```bash
git switch -c your-name/short-description
uv run pytest tests/engine -q
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
```

Read [CLAUDE.md](../CLAUDE.md) first. Reuse existing shared tools, keep platform imports
within the engine boundary, and make service-layer lifecycle changes rather than
writing state directly. [Testing](testing.md) describes wider gates and their scope.
Open a reviewed PR; do not push directly to main. Hebrew contributor guidance is in
[onboarding](onboarding.he.md).

The [do wrapper](../do) provides `test`, `lint`, `format`, `migrate`, `makemigrations`,
`worker`, `manage`, `superuser`, `pending`, `approve`, `make-admin`, `key`, `keys`,
`build-frontend`, `frontend` and `smoke`. Read `./do help` for argument forms.
`format` edits files; `reset-db` deletes selected local database/media/log paths after
confirmation and is not a complete reset of all runtime state. Never use it on data
you need. Approval, administrator promotion and API-key creation are privileged actions.

## First run and troubleshooting

Follow [the tutorial](tutorial.md) after installation. For a disposable demo,
`uv run python manage.py seed_demo` executes the configured engine/import path and
creates a known-password demo account; do not run it on a real-user deployment.

- uv missing: add `$HOME/.local/bin` to PATH and reopen the shell.
- Occupied port: choose `./do dev 8001`; stop only a process you own and identify.
- QUEUED at 0%: inspect worker availability and terminal logs; see [operations](operations.md).
- `database is locked`: check long transactions and competing processes; SQLite has
  WAL and a busy timeout, but sustained contention requires a reviewed topology change.
- API write 403: fetch `/api/auth/csrf` and send its cookie value as `X-CSRFToken`.
- Migration conflict: inspect both histories and coordinate a merge migration; do not
  delete or rewrite migrations already applied to shared databases.

Historical environment notes are preserved in the [old guide](archive/operator-design/development.md).
