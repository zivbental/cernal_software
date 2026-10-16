# Deployment

Source baseline: `main` at `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

## Supported deployment

Use the [single-Linux-VM runbook](operations.md). The repository supplies
[Caddy](../deploy/Caddyfile), [web](../deploy/cernal-web.service),
[worker](../deploy/cernal-worker.service), [reconciler](../deploy/cernal-reconciler.service)
and [environment](../deploy/cernal.env.example) templates. Gunicorn binds loopback;
Caddy terminates HTTPS. One Django Q2 worker executes LocalEngine and a separate
reconciler handles queue/recovery deadlines. Persistent local storage holds SQLite,
media, staging and heartbeat state.

These are deployable templates, not evidence that a production environment has passed
acceptance. Provision DNS/TLS, restricted service identity, persistent disk, monitoring,
protected backups and incident ownership before making the service public.

## Preflight and acceptance

1. Choose a reviewed source revision and locked dependencies; retain the revision in
   the deployment record. Build the frontend and collect static assets.
2. Configure production secrets, allowed hosts and HTTPS CSRF origins using
   [configuration](configuration.md). Disable reviewer login for real user data.
3. Review the reverse-proxy boundary and [security checklist](security.md).
4. Follow [installation and recovery](operations.md), including a maintenance-window
   backup before migration or upgrade.
5. Verify health and readiness, an actual queued design, owner-only downloads,
   release restrictions, worker failure/reconciliation, reboot, backup restoration,
   alert delivery, and TLS renewal. Record results rather than treating a passing
   unit suite as production certification.

Native Windows is suitable for supported engine-only work, not the locked fork-based
queue. Use [WSL2](windows-worker.md) for the full application on Windows.

## Proposed cloud topology (not implemented)

The old [Cloud Run/VM deployment proposal](archive/operator-design/deployment.md)
preserves the original latency/cost reasoning, proposed object-storage protocol,
identity design, equivalence tests and commands. Its split dependency groups,
Dockerfile, cloud engine adapter and cloud task-runner commands are proposals, not
files or supported commands in this baseline. Do not run them as an installation
recipe. A future remote engine must preserve the platform/engine boundary and provide
new deployment, security, cancellation, reproducibility and acceptance evidence.
