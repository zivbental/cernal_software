# Running the application on Windows through WSL2

Source baseline: `main` at `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

The locked Django Q2 1.11.0 worker explicitly selects `multiprocessing.get_context("fork")`
in both cluster and worker startup. Native Windows has no `fork` context. Native
engine tests or direct engine calls do **not** establish working queued application
execution. Use Linux, including WSL2, for the web application and its worker together.
Native Windows queued execution remains unsupported; `qcluster` and the development
supervisor report this limitation before launching a broken worker/restart loop.

Upstream context: [Django Q2 multiprocessing discussion](https://github.com/django-q2/django-q2/issues/199).
This workflow does not modify the dependency, enable synchronous queue execution, or
change screening/release settings.

## Set up WSL2 once

From an administrator PowerShell terminal, if WSL is not installed:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart if Windows requests it, open Ubuntu, and finish its Linux user setup. Check
`wsl --list --verbose` in PowerShell; the Ubuntu distribution should use version 2.
Inside Ubuntu, install Git and curl if needed, then install uv using its official
installer. Review the installer before executing it according to your local policy.

```bash
sudo apt-get update
sudo apt-get install -y git curl
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/install-uv.sh
sh /tmp/install-uv.sh
export PATH="$HOME/.local/bin:$PATH"
mkdir -p ~/src
cd ~/src
git clone https://github.com/zivbental/cernal_software.git
cd cernal_software
uv sync --locked --extra dev
```

Keep the checkout, Linux virtual environment, SQLite database, media and staging in
the Linux filesystem. Do not share a Windows `.venv` or a live SQLite file between
Windows Python and WSL. For private repository access, authenticate Git in WSL through
your normal credential workflow; do not paste credentials into these commands.

## Verify the real worker before using the application

Run inside Ubuntu at the repository root:

```bash
uv run pytest tests/test_queued_worker_acceptance.py -q -s
```

The acceptance test creates disposable settings, a new migrated SQLite database,
media, staging and worker-status cache. It submits through `submit_run`, asserts a
durable queued task exists before starting a separate `manage.py qcluster` process,
waits for LocalEngine completion and the queue's successful task record, and verifies
stored artifact checksums. It stops only its own process group. It opens no network
port and never reads or restores user backups. A failure or timeout fails the test.
Computational completion is not biological validation or sequence release approval.

## Start the development application

Follow [the development guide](development.md) for frontend setup in this same Linux checkout (use Linux Node/npm),
then run:

```bash
uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:8000
```

The development entry point starts the web server and supervised qcluster together.
Open `http://localhost:8000` in your Windows browser. If port 8000 is occupied, use
another free local port. Keep the terminal open; Ctrl+C stops the supervised processes.
For an independently managed worker, `uv run python manage.py qcluster` works inside
WSL; do not start an extra worker unnecessarily alongside the supervisor.

This is a local development workflow, not a production deployment recipe. Existing
Linux qcluster behavior and deployment settings are unchanged.
