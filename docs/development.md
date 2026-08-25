# Development guide

Architecture and build order live in [`software-design.md`](software-design.md).
This document covers running the project day to day.

## First-time setup (WSL)

Two environment issues matter here, both explained in
[software-design.md §15](software-design.md).

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

## Testing

```bash
./do test                          # everything
./do test tests/engine             # one directory
./do test -k boundary              # one pattern
./do test -x -vv                   # stop at first failure, verbose
```

`tests/test_boundary.py` enforces the engine boundary
([§3](software-design.md)). If it fails, do not add an exception to it — the failure
means Platform code has leaked into `src/engine/`, and that is the one thing this
architecture is protecting.

## Conventions

Full list at [software-design.md §14](software-design.md). The ones that come up most:

- Business logic lives in `services.py`, not in views, tasks, models or admin.
- Run state transitions happen only in `apps/analyses/services.py`.
- Tasks take primitive arguments (a UUID string) and re-fetch; never model instances.
- Every object endpoint checks ownership. No exceptions.
- All runtime state goes under `var/`. `rm -rf var/ && ./do migrate` must give a clean
  system.
- Adding a service (Redis, Postgres, Docker, S3) requires an ADR in `docs/decisions/`
  first.

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
