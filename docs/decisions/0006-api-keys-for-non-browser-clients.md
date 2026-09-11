# 0006 — API keys for non-browser clients

**Status:** Accepted
**Extends:** ADR 0003 (same-origin SPA, session cookies)

## Context

ADR 0003 chose session cookies and closed with: "Revisit when a client that is not a
browser on this origin needs to authenticate." That client now exists — Python, R and
MATLAB scripts run by researchers, and the iGEM integration requirement asks for exactly
this.

A session cookie cannot be held by a script: it requires a login round trip, a cookie
jar, and a CSRF token read from a second cookie and echoed in a header. Every scientific
HTTP client makes that awkward and MATLAB's `webwrite` makes it near-impossible.

## Decision

Add **long-lived API keys**, presented in an `X-API-Key` request header, as a *second*
credential on the *same* `/api/` surface. Session auth is unchanged and remains the
SPA's only mechanism.

A key belongs to exactly one user. Authenticating with it sets `request.user` to that
user, so all existing ownership checks apply without modification.

Keys are stored as SHA-256 digests. The secret is displayed once, at creation.

## Consequences

**Gained.** Scripts authenticate in one header. No CORS is needed, because these clients
are not browsers. No CSRF work is needed, because django-ninja attaches CSRF to
`APIKeyCookie`, not to `APIKeyHeader`. The SPA is untouched. Work submitted by a script
appears in the web UI, owned by the same account.

**Given up.** A second credential to revoke, expire and audit. A bearer secret that,
unlike an HttpOnly cookie, can be pasted into a notebook and committed to a repository —
mitigated by a `cern_live_` prefix that secret scanners recognise, single-display,
per-key revocation and expiry.

**Not chosen.** OAuth 2 / JWT: no third-party application needs delegated access, and
refresh-token handling in R and MATLAB would be the largest single piece of client code.
Reconsider only if a client must act *on behalf of* a user who is not its owner.

**Revisit when** a third party needs delegated access, or a browser-based tool on another
origin needs to call the API (that one needs CORS, not a new credential).
