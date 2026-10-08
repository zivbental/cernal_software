# Platform security remediation (8 October 2026)

Protected GET/HEAD/OPTIONS operations require a key with `read` or `design` scope.
Submission, cancellation, annotation writes, dataset upload, example copying and
public-comparison materialization require `design`. Public catalog, capability and
health reads remain public. Key lifecycle operations and dataset deletion require a
session; an API key alone cannot reach them. A legacy empty-scope key cannot read
protected resources, and issuance rejects new empty-scope keys.

Login, registration and reviewer login explicitly check Django CSRF before doing
password work or creating a session. The SPA obtains `/api/auth/csrf` and sends
`X-CSRFToken`. These entry points share a per-address, per-minute cache counter,
default 30 attempts (`AUTH_ATTEMPTS_PER_MINUTE`). Deployments must use a shared cache
for a shared counter across web processes. Client-supplied forwarding headers do not
change this address; a trusted proxy must configure the real remote address.

Reviewer login intentionally retains the existing shared demo history policy. The
username `reviewer` is reserved. The endpoint refuses any existing account with that
name which is privileged, inactive, password-bearing or lacks the dedicated demo
email. It never demotes or changes a colliding account. Disable reviewer mode when
shared demo history is unsuitable. Raw media URLs are not served in DEBUG; artifacts
must go through the authorized API.

Run idempotency keys are unique per owner. An identical request returns its existing
run before considering quota; changed immutable input/configuration returns 409.
Dataset content identity is its checksum, so byte-identical inline retries work even
if storage IDs differ. Account submissions are serialized while checking the active
run count and creating the run. `MAX_ACTIVE_RUNS_PER_ACCOUNT` defaults to 2 and applies
to sessions and keys; stricter credential limits also apply. This limits queued and
running work, independently of best-effort API rate throttling.

Regeneration rotates an unexpired secret and can reactivate a revoked key. It
refuses an expired key with an actionable error; create a new key with an explicit
new expiry instead. Expiry must be 1–3650 days if supplied. Prefix collisions retry
within database savepoints and never replace another credential.

Account recovery remains a manual team operation: verify the researcher identity
through an established contact, then have an authorized administrator use the
Django user change-password page to set a temporary password and ask the researcher
to replace it. Do not disclose passwords, API secrets or account-existence details
through public endpoints. Account approval and annotations remain mutable in admin;
source datasets, submitted runs, imported measurements and artifact provenance do
not.
