# Configuration reference

Source baseline: `main` at `c1bb92cc085a6bad272298b81bda28c22b1d57f5` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

Settings load the root `.env` through django-environ; explicit process environment
values take precedence. Sources: [base](../src/config/settings/base.py),
[development](../src/config/settings/dev.py), [production](../src/config/settings/prod.py),
[local example](../.env.example), [deployment example](../deploy/cernal.env.example).
Restart affected processes after changing configuration.

| Variable | Default / meaning |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` through manage.py; use `config.settings.prod` for deployment |
| `SECRET_KEY` | Insecure development key; production requires an explicit secret with no default |
| `ALLOWED_HOSTS` | Localhost addresses in dev; required explicitly in production |
| `CSRF_TRUSTED_ORIGINS` | Empty in production; set explicit HTTPS origins |
| `DATABASE_URL` | SQLite in repository `var/cernal.db`; production template uses an absolute URL |
| `MEDIA_ROOT` | `var/media`; use an absolute persistent production path |
| `CERNAL_ENGINE` | `engine.client.LocalEngine`, the supported engine |
| `MAX_DATASET_MB` | 100; request upload limit, with 5 MiB in-memory file threshold |
| `REVIEWER_LOGIN_ENABLED` | True in dev, False by default in prod; shared unauthenticated reviewer access |
| `AUTH_TRUSTED_PROXY_ADDRESSES` | Empty; exact immediate proxy addresses permitted to supply `X-Cernal-Client-IP` |
| `LOG_LEVEL` | INFO |
| `RUN_HEARTBEAT_SECONDS` | 10 |
| `RUN_HEARTBEAT_TIMEOUT` | 120 |
| `RUN_EXECUTION_TIMEOUT` | 3630 seconds |
| `RUN_QUEUE_REPUBLISH_SECONDS` | 3660 seconds |
| `RUN_QUEUE_TIMEOUT` | 7200 seconds from submission |

The ORM queue uses one worker, a 3600-second task timeout and 3660-second retry, with
one attempt. These `Q_CLUSTER` settings are Python configuration, not individual
supported environment overrides. Change timeout relationships together after review.
`RUN_STAGING_ROOT` is fixed to repository `var/result-staging`; worker cache is
`var/worker-status`. An arbitrary environment variable with that name does not override
it. Keep these paths writable and persistent. The database-backed authentication cache table is created by the accounts migration
when you run `manage.py migrate`; it needs no separate manual creation step.

PostgreSQL is not provisioned by these instructions: changing `DATABASE_URL` alone
does not install a database server/driver, migrate existing data or certify backups.
The shipped backup/restore commands target SQLite/local media.

## Production security behavior

Production disables DEBUG, requires secret/hosts, redirects HTTPS, marks session/CSRF
cookies secure and sets HSTS (including subdomains/preload), nosniff, frame denial and
same-origin referrer policy. TLS terminates at the trusted reverse proxy. Review the
scope of HSTS before deploying under a domain with other subdomains. Keep Gunicorn
private so callers cannot forge trusted proxy headers. Do not reuse `.env.example`'s
development secret or a literal replacement placeholder.

Production logs rotate under `var/logs`; create the directory before starting the app.
Use restrictive environment-file permissions. [Operations](operations.md) owns service,
backup and recovery procedures; [security](security.md) owns the checklist.

## Scientific run configuration is separate

Host, input mode, families, scoring, constraints, folding, payload and backbone belong
to a submitted run and its immutable snapshot, not deployment environment variables.
Discover capabilities at `/api/version` and see [HTTP API](api.md) and
[modalities](modalities.md). No infrastructure setting constitutes biological
validation or sequence-release approval.
