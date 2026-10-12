# Sequence screening frontend handoff

This branch adds an optional, proposed frontend contract on `GET /api/candidates/{id}`:
`sequence_screening?: SequenceScreening | null`. It does not change Django schemas,
run the screening engine, provision databases, or change release policy. Current backends
omit the field and the results panel displays **Not screened**. Candidate lists, ranking,
annotations and historical API clients retain their existing behavior.

## Liran's adapter boundary

Implement the backend integration with the official [IBBIS Common Mechanism](https://github.com/ibbis-bio/common-mechanism).
Map the engine's outcome on the server into `frontend/src/api/screening.ts`; do not send
raw Common Mechanism output to the browser. This is CERNAL's proposed API envelope,
not a claim about the native Common Mechanism JSON schema. The browser runtime validates
the envelope with Zod and does not infer a verdict from motifs, scores, warnings or an
empty array of matches.

1. Add the optional field to the candidate detail schema/serializer with ownership checks
   matching the existing endpoint. Persist evidence atomically against the immutable
   candidate/run and exact submitted sequence. Missing, disabled or historical data must
   stay omitted/null or explicitly `not_screened`/`unavailable`.
2. Supply `schema_version: 1`, one of `not_screened`, `unavailable`, `pending`, `error`,
   `flagged`, `clear`, and `subject` with `run_id`, `candidate_id`, `scope: switch_sequence`,
   lowercase 64-character SHA-256, nucleotide `length`, and `normalization: uppercase-rna-v1`.
   Hash UTF-8 bytes of the complete saved `design.switch_sequence` uppercased, containing
   only A/C/G/U. No trimming, FASTA parsing, T/U conversion, or concatenation takes place
   in the frontend. Record engine input conversion separately in backend provenance;
   bind this envelope to the original saved RNA. The hash is identity evidence, not proof
   of a trustworthy screening operation.
3. For completed outcomes supply timezone-qualified ISO `screened_at` and `valid_until`
   plus `provenance: { tool, tool_version, database, database_version, policy_version }`.
   Each provenance value is nonempty, max 200 characters. These are actual operational
   versions, never placeholders. Other statuses may use null timestamps/provenance.
   Backend policy owns the validity window and invalidation when databases/policy change;
   the frontend must not invent a lifetime. Future, expired or inconsistent timestamps
   are conservative stale results. Completed outcomes without provenance are unavailable.
4. Supply `findings` as at most three approved codes: `review_required`, `restricted_match`,
   `incomplete_coverage`. Empty findings alone never means clear. Only explicitly completed,
   adequately covered screening may map to `clear`; a clear result with findings is rejected.
   Do not send raw hits, hazardous sequence details, alignment coordinates, operational
   error traces or advice for circumventing screening. A failed attempt is `error`.
5. Pending candidate detail is polled every five seconds while visible. Refreshing the
   page or query on focus also retrieves current evidence. The UI verifies the hash locally,
   rejects mismatched identities and rechecks validity every second. It hides an old
   verdict immediately when the candidate object changes, while checking new evidence.
6. Preserve the separate existing `src/engine/safety.py` release boundary. Neither a clear
   switch result, a completed run nor a ranking/annotation decision authorizes export.
   Review-only or unavailable operational screening must remain subject to server policy.

## Deliberate limits

V1 covers only the one saved switch sequence. It does **not** cover a plasmid, cassette,
payload, backbone, every gate of a multi-gate design, input triggers, or artifact bytes.
Unknown scopes are unavailable. Full construct support needs an agreed identity-bearing
API (or artifact binding) and tests before the frontend can represent it as screened.
It must not reuse a switch hash to label an entire run or download as clear.

The panel appears within normal selected-candidate results, with a keyboard-operable
details disclosure, textual live status, complete identity, time and provenance. It says
“No concerns detected by this screening”, with explicit scope and limits. Screening has
no effect on candidate ranking or existing download links.

The download panel explains that screening is not embedded in current artifacts and does
not establish file or full-construct clearance. Server-generated CSV, JSON, ZIP, FASTA,
GenBank and reports are unchanged. Backend export integration must attach the relevant
evidence and artifact/sequence identity and apply release policy; that remains unavailable.

## Validation

`npm run test:screening` checks absent, null, every status, malformed/unsupported data,
contradictory evidence, missing provenance, identity/hash/length/scope mismatch, expired
and future evidence, normalization and missing browser crypto. `npm run test:screening:browser`
exercises the built results page with synthetic fixtures only; no real sequence screening
or external service is invoked. Both are included in existing check/browser CI scripts.
Fixtures live exclusively under `frontend/e2e`, outside the application bundle.

Work PC verification on 2026-10-12: `npm run check` and `npm run build` passed;
31 screening contracts, 15 screening browser checks, existing browser contracts and
29 RNA-viewer browser checks passed. The RNA fixture asset-path guard now uses the
platform separator so it can run on Windows as well as Linux. Screenshots are synthetic:
[desktop clear](evidence/screening-clear-desktop.png),
[mobile flagged](evidence/screening-flagged-mobile.png).

Integration acceptance still requires backend tests for persistence, ownership, conversion
identity, all operational failure states, version invalidation and release/export binding,
plus an end-to-end run against the provisioned service. Frontend tests do not establish
screening capability or biological safety.
