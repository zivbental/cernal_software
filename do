#!/usr/bin/env bash
# CERNAL task runner. Zero dependencies — see docs/development.md
set -euo pipefail
cd "$(dirname "$0")"

# uv installs to ~/.local/bin, which is not always on PATH in a fresh shell.
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed. Run:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

case "${1:-help}" in

  install)        # Create the venv and install all dependencies
    uv sync --extra dev
    ;;

  dev)            # Run the development server on :8000
    uv run python manage.py runserver "${2:-8000}"
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
  worker           Run the background task worker (needed for analysis runs)
  test [args...]   Run the test suite
  lint             Check formatting and lint rules
  format           Auto-fix formatting and lint rules
  migrate          Apply database migrations
  makemigrations   Generate migrations for model changes
  superuser        Create an admin user
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
