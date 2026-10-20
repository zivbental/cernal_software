# Operating CERNAL on one Linux VM

Status: executable service templates and locally tested recovery code; **not a
production deployment certification**. Use a reviewed, recorded source revision. These
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

The supplied Caddy configuration overwrites `X-Cernal-Client-IP`. Authentication
rate limits use it only when the immediate peer is in `AUTH_TRUSTED_PROXY_ADDRESSES`
(loopback in the supplied environment template). Without that explicit configuration,
the app uses the peer address; behind a proxy that would share one quota across all
users. Never trust this header from a directly exposed listener or a proxy that simply
passes through caller-supplied headers. Ordinary `X-Forwarded-For` is not trusted here.

## First installation

This is the authoritative production quickstart. `./do install` remains a development
dependency/data convenience command, not a production deployment. The commands below
prepare the current checkout; they never install/start system services, change firewall
rules, configure DNS/TLS, restore a backup, or provision IBBIS.

1. An operator separately provisions Linux, Python 3.13, uv, Node 22+, npm, Git,
   Caddy and the dedicated service account. Put the reviewed checkout at its final
   absolute path, for example `/opt/cernal`. Run preparation as an account allowed to
   write that checkout and its runtime directories; arrange ownership for the service
   account before service activation. Runtime directories are created before Django
   initializes logging, including on a fresh production settings import.
2. Render configuration and templates without creating credentials or a database:

   ```sh
   ./do production prepare --domain cernal.example.org --output /opt/cernal/var/deployment
   ```

   `--root`, `--user`, `--group`, and `--dataset-mib` parameterize all templates
   consistently. Root must contain `manage.py`; domain must be a DNS hostname.
   Deployment paths must be absolute POSIX paths without spaces, `..`, or shell/systemd
   metacharacters: unsupported paths fail explicitly rather than being misquoted.
   Generated files are mode 0600. Review them; existing files and secrets are preserved.
   A conflicting domain/path/upload limit or edited unit/Caddyfile stops preparation
   before files are written. Reconcile such changes manually or render to a new directory.
   Managed checkout, configuration, output and runtime paths must not contain symlinks,
   including dangling links or linked ancestors. Database and log destinations are
   checked before preparation or migration. If a system uses a linked path (for example
   an alias for a mounted disk), supply its literal canonical location instead; the
   tool deliberately refuses to guess the intended target. Keep these directories
   operator-controlled and do not change paths concurrently with preparation.
3. In `var/deployment/cernal.env`, replace `SECRET_KEY` with an operator-managed random
   secret of at least 50 characters, preserving it across upgrades/restores. No default
   admin account/password or real secret is generated. Reviewer login is enabled by
   default, including production: visitors can sign in without a password to the same
   unprivileged reviewer account, share its history, and create API keys. Set
   `REVIEWER_LOGIN_ENABLED=False` to disable new reviewer logins; existing configuration
   files are preserved, and an explicit False overrides inherited environment or `.env`
   values. Disabling login does not revoke existing sessions or API keys; revoke those
   separately when withdrawing access. Use False for deployments holding private data.
   Values are literal dotenv entries (quote values containing spaces); no shell code,
   command substitution or environment expansion is evaluated. Do not commit this file.
4. For a genuinely new database only:

   ```sh
   ./do production install --config var/deployment/cernal.env --initialize-database
   ```

   This installs locked Python dependencies, verifies/downloads pinned runtime data,
   runs `npm ci` and the standard typechecked build, migrates, collects static files,
   and runs deployment checks with warnings treated as failures. Each failed step
   stops the sequence. It does not delete data or reset configuration. Rerun without
   `--initialize-database` once the database exists. Optional `--create-admin` explicitly
   invokes interactive `createsuperuser`; noninteractive use is rejected. For a restore,
   use the separate procedure below, not fresh-database initialization.
5. Virtual environments are path-specific. After relocating a checkout, move its old
   `.venv` aside and let the install command create a new one normally through `uv sync`.
   Never rewrite shebangs or copy a venv between platforms. An unmanaged/relocated venv
   is rejected with an actionable message. A venv created manually for development
   must likewise be moved aside before using production installation.
6. **Separate privileged activation:** review/install the rendered units under
   `/etc/systemd/system/` and the rendered Caddyfile under `/etc/caddy/`. Ensure the
   configured environment file is readable by the service account (for example 0640,
   root:service-group) and runtime `var/` is writable by it. Source/venv can remain
   operator-owned. Validate units with `systemd-analyze verify` and the proxy with
   `caddy validate --config /etc/caddy/Caddyfile`, then separately approve service
   activation, DNS/TLS and firewall configuration. Do not install the raw `@@...@@`
   templates directly. The script never invokes service enable/start/restart.
7. After activation, run `./do production status --config var/deployment/cernal.env`.
   It reports data verification, migration/database availability, HTTPS web liveness,
   worker readiness, each service's activity and screening inventory independently;
   any unavailable required component gives a nonzero exit. A homepage is not evidence
   of production readiness. Screening inventory verification grants no sequence
   release authorization and does not run or bypass screening. Service activity is
   not proof that reconciliation is progressing: inspect its journal and perform a
   controlled acceptance run. Verify login, a real queued design, and owner isolation;
   sequence downloads must remain held until valid screening and required approvals
   permit release. Record revision, durations and results before admitting users.

### Upload limits

`MAX_DATASET_MB` is the application's per-file limit in **MiB**, despite its legacy
name. Default 100 means 104,857,600 bytes; exactly that size is accepted by the size
check, one byte above is rejected (content validation still applies). Caddy's generated
`request_body max_size` is **106,954,752 bytes**, leaving 2 MiB for multipart overhead
and metadata. Both derive from `--dataset-mib` (1–1024). Django's
`DATA_UPLOAD_MAX_MEMORY_SIZE` bounds non-file form data at the file-limit value;
`FILE_UPLOAD_MAX_MEMORY_SIZE=5 MiB` is a spool-to-disk threshold, not a rejection limit.
The proxy bounds the complete request, including chunked uploads. Large metadata can
consume the 2 MiB margin and receive HTTP 413; it does not increase the file allowance.
Keep proxy and application values together when reconfiguring. Validate the generated
request-body directive against the installed Caddy version before activating it;
see the [official Caddy request_body documentation](https://caddyserver.com/docs/caddyfile/directives/request_body).

The proxy regression test runs the official executable's `adapt --validate` command,
which provisions configuration for validation without starting listeners. It uses
temporary HOME/XDG directories and checks the parsed hostname, upstream and exact
request-body limit for the substituted template and generated configurations at
1, 100 and 1024 MiB, including alternate installation paths/domains. Run it with:

```sh
CADDY_BIN=/absolute/path/to/caddy uv run pytest tests/test_production_setup.py -k caddy -q
```

The test skips when Caddy is unavailable; providing `CADDY_BIN` makes a missing or
invalid binary fail. Caddy 2.11.7 passed these checks using the official Linux amd64
release archive (SHA256 `727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b`).
This verifies configuration loading, not TLS issuance or live HTTP upload behavior.

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
seconds, queue republish after 3660 seconds, and queue wait deadline 7200 seconds from
submission (`RUN_QUEUE_TIMEOUT`). A run never claimed by any worker becomes FAILED
with an explicit queue-wait error at reconciliation; broker retries do not reset this
deadline. Late delivery cannot restart it. Adjust this limit deliberately for expected
queue capacity: an overlong legitimate queue also expires. django-q2 has a 3600-second task timeout
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

The `backup_instance` and `restore_instance` commands target SQLite and local media.
They are separate from fresh installation. Test a protected restore drill with the
reviewed revision before relying on them operationally.

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

`manage.py cleanup_staging` previews removal of result directories older than 30 days
for COMPLETED/CANCELLED runs. `--apply` performs that reviewed removal. Failed-run
directories require the additional explicit `--include-failed` switch; use it only
after deciding recovery is no longer needed. Active runs, unknown directories,
unrecognized lease tokens and symlinks are preserved. This command is not scheduled
automatically.

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
human-owned incident drill remain deployment acceptance work. The native Windows
Server 2025 CI lane passed 48 supervision/lifecycle/recovery tests; launch/shutdown
adapters in that suite use mocks. Actual process-tree crash/restart drills remain open.
