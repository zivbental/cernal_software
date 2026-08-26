# Development guide

Architecture lives in [`architecture.md`](architecture.md) and future work in
[`ROADMAP.md`](ROADMAP.md). This document covers running the project day to day.

## First-time setup (WSL)

Two environment issues matter here, both explained in
[architecture.md §15](architecture.md).

**1. Use Python 3.13, not 3.14.** Scientific wheels — ViennaRNA especially — lag new
CPython releases by months. The project pins 3.13 in `pyproject.toml` and
`.python-version`; `uv` honours both automatically.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"     # add to ~/.bashrc
uv python install 3.13
```

**2. Keep the repository on the Linux filesystem.** Under `/home/...`, never under
`/mnt/c/`. Performance and file-watching both degrade badly across the WSL boundary.

Then:

```bash
./do install
./do migrate
./do superuser
./do dev          # http://localhost:8000
```

`.env` is optional — every setting has a working development default. Copy
`.env.example` to `.env` when you need to change one.

## Everyday commands

| Command | What it does |
|---|---|
| `./do dev` | Development server on :8000 |
| `./do worker` | Background task worker — **required for analysis runs** (Step 3+) |
| `./do test` | Run the test suite; extra args pass through to pytest |
| `./do lint` | Check formatting and lint rules |
| `./do format` | Auto-fix formatting and lint rules |
| `./do migrate` | Apply migrations |
| `./do makemigrations` | Generate migrations after model changes |
| `./do make-admin <user>` | Promote an existing account to administrator |
| `./do pending` | List accounts waiting for approval |
| `./do approve <user>` | Approve a pending account |
| `./do manage <cmd>` | Any `manage.py` command, e.g. `./do manage shell` |
| `./do check` | Django system checks |
| `./do reset-db` | Wipe `var/` and rebuild — destructive, asks first |

There is no `Makefile`: `make` is not installed on a default WSL Ubuntu image, and a
plain shell script avoids adding a dependency to run the project at all.

## Running the full stack

Analysis runs execute in the worker, not the web process. Two terminals:

```bash
./do dev        # terminal 1
./do worker     # terminal 2
```

Without the worker, submitted runs sit in `QUEUED` forever. Queued and failed tasks are
visible in Django admin under **Django Q**.

## Frontend

The React app lives in `frontend/` and is built into `src/static/app/`, which Django
serves same-origin (ADR 0003, ADR 0005).

```bash
./do install-frontend    # once
./do build-frontend      # production build, served by ./do dev
./do frontend            # Vite dev server on :5173 with hot reload
```

For day-to-day frontend work run three terminals: `./do dev`, `./do worker`, and
`./do frontend`, then use **http://localhost:5173**. Vite proxies `/api`, `/media` and
`/admin` to Django, so the browser still sees one origin and session cookies behave
exactly as they will in production.

`./do dev` alone serves the last build at :8000 — enough for backend work, and it does
not need Node.

### Browser smoke test

`./do smoke` drives the real app through login, the wizard and the results screen, and
fails on any console or page error. It needs Chromium's system libraries, which are a
one-time root install:

```bash
sudo npx playwright install-deps chromium
# or: sudo apt install libnspr4 libnss3 libasound2t64
```

Then, with `./do dev` and `./do worker` running:

```bash
./do smoke                       # screenshots into frontend/e2e/shots/
RUN_ID=<completed-run-id> ./do smoke
```

## Testing

```bash
./do test                          # everything
./do test tests/engine             # one directory
./do test -k boundary              # one pattern
./do test -x -vv                   # stop at first failure, verbose
```

`tests/test_boundary.py` enforces the engine boundary
([architecture.md §3](architecture.md)). If it fails, do not add an exception to it — the
failure means Platform code has leaked into `src/engine/`, and that is the one thing this
architecture is protecting.

Testing *scientific* code is a different problem — golden tests, property tests,
determinism tests. See [engine.md §8](engine.md).

## Continuous integration

`.gitlab-ci.yml` runs the same things you run locally — `ruff check`, `ruff format --check`,
`manage.py check` and `pytest` for the backend, and `npm run check` plus `npm run build` for
the frontend — on every push. It uses `MockEngine`, so it needs no scientific dependencies
and no secrets.

**If `./do lint && ./do test` passes locally, CI passes.** That is deliberate: a pipeline
that checks something different from the local command is a pipeline people learn to ignore.

## Conventions

Full list at [architecture.md §14](architecture.md). The ones that come up most:

- Business logic lives in `services.py`, not in views, tasks, models or admin.
- Run state transitions happen only in `apps/analyses/services.py`.
- Tasks take primitive arguments (a UUID string) and re-fetch; never model instances.
- Every object endpoint checks ownership. No exceptions.
- All runtime state goes under `var/`. `rm -rf var/ && ./do migrate` must give a clean
  system.
- Adding a service (Redis, Postgres, Docker, S3) requires an ADR in `docs/decisions/`
  first.
- Future work is recorded in [`ROADMAP.md`](ROADMAP.md), not in a new planning document.

## Troubleshooting

**`uv: command not found`** — `export PATH="$HOME/.local/bin:$PATH"`, and add it to
`~/.bashrc`.

**`That port is already in use`** — `pkill -f "manage.py runserver"`, or
`./do dev 8001`.

**`database is locked`** — something holds a write transaction. WAL and a 10s busy
timeout are configured (`apps/common/db.py`); if this recurs under normal use it is the
signal to move to Postgres (ADR 0002).

**Submitted runs never leave `QUEUED`** — the worker is not running. `./do worker`.

**`403` on every API write** — the request is missing the `X-CSRFToken` header. Call
`GET /api/auth/csrf` first, then send the `csrftoken` cookie's value in that header. See
[api.md](api.md).

**Migrations conflict after a rebase** — never edit an applied migration. Roll back,
delete the conflicting file, regenerate.
