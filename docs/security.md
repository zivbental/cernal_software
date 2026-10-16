# Security and data handling

Source baseline: `main` at `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

## Deployment checklist

- Use production settings and a strong unique secret; restrict the environment file.
- Keep reviewer login disabled for real data. `seed_demo` creates a known-password
  account and belongs only in disposable environments.
- Terminate HTTPS at the reviewed proxy and bind Gunicorn to loopback. The proxy must
  overwrite client-address headers; configure only trusted immediate peer addresses.
- Never expose `/media/` with a static file server. Downloads require ownership,
  key scope and scientific release checks.
- Restrict database, media, staging, logs and backup access. Backups contain account
  records and private inputs/results; separately protect secrets excluded from them.
- Test recovery, disk capacity, dependency advisories, alerting and account revocation.
  Assign incident ownership before accepting users. See [operations](operations.md).

## Authentication and authorization

[Security code](../src/api/security.py) supports session + CSRF and `X-API-Key`.
An explicitly invalid nonempty key is rejected rather than silently using a session.
Key management is session-only; secrets are returned only on creation/regeneration,
and only digests are stored. Use an environment variable/secret manager in clients,
never committed examples, URLs or logs. Scope `design` implies `read`; key quotas and
rate limits do not replace capacity planning. Authentication entry points use CSRF and
per-address throttling through the shared cache.

[Ownership helpers](../src/api/auth.py) grant staff access and otherwise restrict by
owner; missing and inaccessible objects both return 404. UUIDs are not access control.
Public metadata/catalog endpoints intentionally require no login. Registration creates
an inactive account requiring approval; password recovery is staff-administered, not
an email reset flow. Revoke leaked keys and inspect related activity.

## Scientific release and input safety

Computational completion does not authorize sequence export or synthesis. Read
[release decisions](release-decisions.md), [release disclosure](audit-f2-release-disclosure.md)
and [interpretation](scientific-interpretation.md). Download routes reject withheld
sequence-bearing artifacts; lists expose availability. An archive containing withheld
or missing files fails explicitly. Do not bypass this by sharing storage paths.

Uploads are bounded and validated. Result import validates files/checksums, and restore
checks archive paths and manifests. These defenses still require least privilege,
retention policies and recovery drills. Never treat file extension or a successful
HTTP response as proof of trustworthy scientific content.

## Verification and reporting

Run the relevant [test gates](testing.md), review the current advisory report, and
retain evidence with the revision. A past dependency scan is not a continuing guarantee.
For suspected exposure, restrict access, preserve relevant logs without redistributing
private sequences/credentials, notify the deployment owner privately, and agree on a secure reporting channel.
This baseline has no dedicated SECURITY.md reporting policy. Avoid posting secrets
or private datasets in public issues.
