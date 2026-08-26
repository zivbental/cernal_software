#!/usr/bin/env bash
# CERNAL task runner. Zero dependencies — see docs/development.md
set -euo pipefail
cd "$(dirname "$0")"

# uv installs to ~/.local/bin, which is not always on PATH in a fresh shell.
export PATH="$HOME/.local/bin:$PATH"

# nvm is not loaded in non-interactive shells; source it so node/npm resolve to the
# Linux install rather than the Windows one on /mnt/c (docs/software-design.md §15).
if [ -s "$HOME/.nvm/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed. Run:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

require_node() {
  command -v npm >/dev/null 2>&1 || {
    echo "error: npm not found. Install Node inside WSL:" >&2
    echo "  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash" >&2
    echo "  nvm install --lts" >&2
    exit 1
  }
  [ -d frontend/node_modules ] || (cd frontend && npm install)
}

case "${1:-help}" in

  install)        # Create the venv and install all dependencies
    uv sync --extra dev
    ;;

  dev)            # Run the development server on :8000
    [ -f src/static/app/index.html ] || {
      echo "Frontend not built yet — building it once..."
      (cd frontend && npm run build:fast)
    }
    uv run python manage.py runserver "${2:-8000}"
    ;;

  build-frontend) # Build the React app into src/static/app/
    require_node
    (cd frontend && npm run build)
    ;;

  frontend)       # Run the Vite dev server on :5173 (proxies /api to :8000)
    require_node
    (cd frontend && npm run dev)
    ;;

  install-frontend) # Install frontend dependencies
    require_node
    (cd frontend && npm install)
    ;;

  smoke)          # Browser smoke test (needs ./do dev + ./do worker running)
    require_node
    if [ -z "${RUN_ID:-}" ]; then
      echo "note: set RUN_ID=<a completed run id> to also check the results screen" >&2
    fi
    (cd frontend && node e2e/smoke.mjs "${2:-e2e/shots}")
    ;;

  worker)         # Run the background task worker (needed for analysis runs)
    uv run python manage.py qcluster
    ;;

  test)           # Run the test suite
    shift || true
    uv run pytest "$@"
    ;;

  lint)           # Check formatting and lint rules
    uv run ruff check .
    uv run ruff format --check .
    if [ -d frontend/node_modules ]; then
      (cd frontend && npm run typecheck && npm run lint)
    else
      echo "note: frontend deps not installed; skipping TS checks (./do install-frontend)"
    fi
    ;;

  format)         # Auto-fix formatting and lint rules
    uv run ruff format .
    uv run ruff check --fix .
    ;;

  migrate)        # Apply database migrations
    uv run python manage.py migrate
    ;;

  makemigrations) # Generate migrations for model changes
    shift || true
    uv run python manage.py makemigrations "$@"
    ;;

  superuser)      # Create an admin user
    uv run python manage.py createsuperuser
    ;;

  pending)        # List accounts waiting for approval
    uv run python manage.py pending_accounts
    ;;

  approve)        # Approve an account: ./do approve <username>
    shift || true
    uv run python manage.py pending_accounts --approve "$@"
    ;;

  check)          # Run Django's system checks
    uv run python manage.py check
    ;;

  manage)         # Run any manage.py command: ./do manage shell
    shift || true
    uv run python manage.py "$@"
    ;;

  reset-db)       # Delete all local state and rebuild from scratch (DESTRUCTIVE)
    read -rp "Delete var/cernal.db, var/media and var/logs? [y/N] " reply
    [[ "$reply" == "y" || "$reply" == "Y" ]] || { echo "aborted"; exit 1; }
    rm -rf var/cernal.db var/media var/logs
    mkdir -p var/media/datasets var/media/artifacts var/logs
    uv run python manage.py migrate
    ;;

  help|--help|-h)
    cat <<'USAGE'
CERNAL task runner

Usage: ./do <command>

  install          Create the venv and install all dependencies
  dev [port]       Run the development server (default :8000)
  frontend         Vite dev server on :5173, proxying /api to :8000
  build-frontend   Build the React app into src/static/app/
  install-frontend Install frontend dependencies
  smoke            Browser smoke test against a running dev server
  worker           Run the background task worker (needed for analysis runs)
  test [args...]   Run the test suite
  lint             Check formatting and lint rules
  format           Auto-fix formatting and lint rules
  migrate          Apply database migrations
  makemigrations   Generate migrations for model changes
  superuser        Create an admin user
  pending          List accounts waiting for approval
  approve <user>   Approve a pending account
  check            Run Django's system checks
  manage <cmd>     Run any manage.py command, e.g. ./do manage shell
  reset-db         Delete all local state and rebuild (DESTRUCTIVE)
USAGE
    ;;

  *)
    echo "error: unknown command '${1}'. Try: ./do help" >&2
    exit 1
    ;;
esac
