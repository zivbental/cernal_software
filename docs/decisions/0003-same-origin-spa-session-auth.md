# 0003 — Serve the SPA same-origin, authenticate with sessions

**Status:** Accepted · 2026-08-25

## Context

A React application (Lovable origin) already exists and is being kept. The usual
arrangement — SPA on one origin, API on another — forces a choice about cross-origin
authentication, and the common answer is JWTs held in browser storage.

## Decision

Build the SPA with Vite into `src/static/app/` and serve it from Django (Whitenoise),
on the **same origin** as `/api/`. Authenticate with **Django's session cookies**.

`config/urls.py` claims `/admin/`, `/api/` and `/static/`, then falls through to a
catch-all returning `index.html` so client-side routing works.

## Consequences

**Gained.** No CORS configuration, no preflight requests, no origin allowlist, no
`SameSite` puzzles. No JWT issuing, refreshing, revoking or storing. No access token in
`localStorage` — the session cookie is `HttpOnly`, so a cross-site scripting bug cannot
exfiltrate it. One deployment unit, one TLS certificate, one origin.

**Given up.** The frontend cannot be deployed to a CDN separately from the backend.
A future native mobile client would need token auth added.

**Notes.** Write endpoints require CSRF; the SPA reads the `csrftoken` cookie, which
works without configuration because it is same-origin. The frontend build is a
deployment step, not a separate release.

**Revisit when** a client that is not a browser on this origin needs to authenticate.
