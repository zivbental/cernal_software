# Operating CERNAL on one Linux VM

Status: executable service templates and locally tested recovery code; **not a
production deployment certification**. Use the combined QA remediation branch. These
instructions assume Python 3.13, uv, Node 22, Caddy, systemd, a local persistent disk,
and a dedicated `cernal` service account. The operator chooses and provisions the VM,
DNS, TLS, backup destination and alert receiver. No cloud credentials are included.

## Supported topology

`deploy/` runs Gunicorn, one django-q2 scientific worker and a separate reconciler.
Caddy is the only public listener; Gunicorn binds loopback. SQLite, uploads, artifacts,
result staging and worker heartbeats share `/opt/cernal/var`. Keep this directory on
local persistent storage. This is a single-machine topology: the file cache cannot
coordinate workers on different hosts. Multiple scientific workers or network-mounted
SQLite need a separate load/concurrency review.

The web process handles authentication and downloads. Do not add a Caddy `/media/`
file-server rule: that bypasses owner and API-scope checks. Static files are served by
WhiteNoise after the frontend build and `collectstatic`.

## First installation

1. Create the unprivileged `cernal` account, install a reviewed source revision at
   `/opt/cernal`, and create `/opt/cernal/var/{logs,media,result-staging,worker-status}`
   owned by that account. Source and virtual environment may remain operator-owned;
   the service only needs write access to `var/`.
2. In `/opt/cernal`, run `uv sync --locked --extra dev`, then in `frontend/` run
   `npm ci`, `npm run build:fast`, `npm run check`, and `npm run build`.
3. Copy `deploy/cernal.env.example` to `/etc/cernal/cernal.env`, permissions 0640,
   owner root, group cernal. Replace the secret, hostname and CSRF origin. Generate the
   secret with `uv run python -c 'import secrets; print(secrets.token_urlsafe(64))'`.
   Keep reviewer login disabled for real user data. Do not place secrets in Git.
4. Load these trusted shell-compatible settings into the operator's environment
   (`set -a; . /etc/cernal/cernal.env; set +a`). Run as the service account with the same
   environment: `.venv/bin/python manage.py migrate --noinput`,
   `.venv/bin/python manage.py collectstatic --noinput`,
   `.venv/bin/python manage.py check --deploy`, and
   `.venv/bin/python manage.py createsuperuser`.
5. Install the three `deploy/cernal-*.service` files under `/etc/systemd/system/`.
   Review the fixed `/opt/cernal` paths. Install `deploy/Caddyfile`, replacing its
   hostname, and validate it with `caddy validate --config /etc/caddy/Caddyfile`.
6. Run `systemctl daemon-reload`, then `systemctl enable --now cernal-web
   cernal-worker cernal-reconciler`. Start/reload Caddy after DNS and firewall setup.
7. Through HTTPS, verify `/api/health` is 200, `/api/ready` is 200, login works, a real
   direct design advances from QUEUED to COMPLETED, and its authorized artifact is
   downloadable. Verify a different account cannot download it. Record the revision,
   duration and result before opening service to users.

Do not run `manage.py runserver` or the development supervisor under these units. The
systemd units own their subprocesses and restart failed services. The worker's stop
timeout is 130 seconds: a long native computation can be killed during maintenance,
so first stop accepting submissions and wait for active runs to finish when possible.

## Monitoring and the 0% failure

`/api/health` checks the web process. `/api/ready` checks a database read and a current
worker heartbeat, returning only `ready` or `unavailable` (503). Use readiness for
operator alerts; making web availability depend on it would also hide old results
when the worker is down. It does not certify reference files, disk capacity, scientific
correctness or the reconciler. Monitor all three systemd services, available disk,
backup age, failed runs and queue age separately.

Inspect `journalctl -u cernal-web -u cernal-worker -u cernal-reconciler` and
`var/logs/cernal.log`. The reconciler prints counts of published, failed and cancelled
runs every interval. Alert on repeated reconciliation failures and queued runs older
than the normal workload allows. Protect logs: exception tracebacks may contain local
paths and input metadata.

Submission now saves the run before dispatch. If publishing to the broker fails, the
run stays QUEUED with a retry stage and the reconciler republishes it. A worker claims
the run through an atomic execution token. Duplicate delivery cannot acquire a live
claim. Heartbeats are written independently of the result-import database transaction.
After heartbeat expiry or the execution deadline, reconciliation makes the abandoned
run terminal; it does **not** silently repeat the scientific computation. A stale
worker's later progress/result cannot overwrite the new terminal state.

Defaults: heartbeat every 10 seconds, expiry at 120 seconds, execution deadline 3630
seconds, queue republish after 3660 seconds. django-q2 has a 3600-second task timeout
and 3660-second delivery retry. Keep heartbeat expiry comfortably above scheduling
delays. Changing the timeout settings independently of Q_CLUSTER requires review.
Reconciliation fences a stale worker; it is not itself a process killer. The queue
supervisor enforces its task timeout. These measures bound known failure modes;
they do not guarantee that no future infrastructure or scientific job can fail.

Manual recovery: `.venv/bin/python manage.py reconcile_runs`. If a run failed during
result import after the engine completed, its manifest and artifacts remain under
`var/result-staging/<run-id>/<execution-token>/`. Fix the importer/storage problem,
then run `.venv/bin/python manage.py reimport_run_results <run-id>`. This validates the
retained manifest and creates a **new** completed run with the original run recorded
in its warnings. It preserves the original failed record and does not rerun folding.
Malformed/incomplete manifests are rejected. Failed staging is retained for diagnosis;
set an operator retention policy and remove it only after recovery is no longer needed.

## Backup and restore

The `backup_instance` and `restore_instance` commands are part of the storage PR in
the same remediation stack. They target SQLite and local media. Test them on the
combined branch before relying on them operationally.

1. Start a maintenance window, stop new writes, and stop all three CERNAL services.
   Keeping a web process online for uploads/reviews violates the media consistency
   assumption even though SQLite's own snapshot is consistent.
2. With the production environment loaded, run
   `.venv/bin/python manage.py backup_instance /protected/cernal-backup.tar.gz --maintenance-window`.
   The archive includes a SQLite snapshot, referenced media and result staging with
   checksums. It excludes environment secrets; preserve those in your separate secret
   manager. The switch acknowledges the window; it does not enforce it.
3. Copy the archive to separately protected storage, record its checksum and retention
   date, then restart services. The archive contains private uploaded/result data and
   account records and must have restricted access.
4. Restore a drill copy into **new** paths using
   `.venv/bin/python manage.py restore_instance /protected/cernal-backup.tar.gz --database /restore/cernal.db --media /restore/media --staging /restore/result-staging`.
   Existing database files or nonempty media/staging directories are rejected. The
   command validates archive paths, sizes, checksums and database file references.
5. To activate a restore, keep services stopped and copy the verified drill outputs to
   the configured production paths. `RUN_STAGING_ROOT` and heartbeat cache currently
   live under the repository's `var/`; `--staging` chooses the extraction destination,
   not a runtime configuration override. Start using the restored database/media and
   preserved production secret. Reconcile old active runs, then perform the HTTPS and
   owned-download acceptance checks again. Do not run a drill against production paths.

Use `.venv/bin/python manage.py cleanup_media` to inspect orphan files. It defaults to
a dry run and a 24-hour grace period; inspect the listing before `--apply`. Use a
maintenance window for destructive cleanup. Referenced media is retained. Failed
result staging follows its separate diagnostic retention policy.

## Upgrade and rollback

Record the current Git revision and take a verified maintenance-window backup before
applying migrations. Build the new frontend and environment, stop services, migrate,
collect static files, restart, and repeat the acceptance run. For an application-only
failure with a compatible schema, switch to the previous reviewed source revision.
For incompatible migrations, restore the matching database **and media** backup;
do not guess a reverse migration against live results. Restoration can lose writes
since the snapshot, so keep service closed until the rollback decision is made.

## Verification still required before production approval

Local tests cover readiness responses, worker death/reconciliation, retained-import
recovery, backup round trips and archive corruption/path rejection. Unit templates
receive syntax checking. A real VM reboot, public TLS renewal, disk-full behavior,
external alerts, scheduled protected backups, a full production-size restore, and a
human-owned incident drill remain deployment acceptance work. Native Windows receives
portable supervisor code and a manual CI lane, but is not certified by Linux mocks.
