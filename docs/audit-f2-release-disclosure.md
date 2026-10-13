# F2: consistent generated-sequence disclosure

The release boundary follows ADR 0008 and the authorized CRISPR export policy in
`crispr-pr65-review-fixes.md`: computational eligibility is not sequence-release
approval. Ownership checks remain necessary and unchanged; the audit finding was an
owner-visible disclosure inconsistency, not an authentication bypass.

## Enforcement

- The pipeline saves stable switch and plasmid decision records with each accepted
  candidate. Both must explicitly permit release, have PASS or authorized REVIEW
  decisions, and match the saved switch/construct digests. HOLD, BLOCK, error, missing,
  contradictory, partial and mismatched evidence withhold disclosure.
  Full timestamped evidence and its audit digest remain in the safety audit files;
  candidate records omit those clock-dependent fields to preserve reproducibility.
- The common candidate projection covers candidate detail and synchronous/asynchronous
  design results. Held designs expose known non-sequence metadata, metrics and audit
  status. Architecture, component sequences, payload catalog sequences and unknown
  nested fields cannot become alternate sequence channels. Stored scientific data is
  not rewritten. Rejected candidates without approval remain withheld too.
- Structure reads retain ownership checks and return an unavailable, empty drawing
  while release is withheld. No screening or folding is invented by a read request.
- Individual, category, selected and whole-run ZIP downloads check release. A mixed
  archive fails explicitly with withheld artifact IDs; it is never silently incomplete.
- Trusted artifact writers explicitly mark sequence-free bytes. The pipeline report,
  design table, hashed trigger snapshot and safety audits retain their checksums and
  remain downloadable. The platform summary table is sequence-free. Raw configuration
  manifests contain submitted input sequences and require approval of every candidate.
  A newly written zero-candidate manifest has no generated switch/plasmid sequence;
  its owned input/provenance-only bytes remain downloadable, including in complete ZIPs.
  CSV summaries and researcher-authored notes contain no generated design sequences.
  Here `sequence_free` means free of complete generated switch/plasmid sequences,
  not the absence of every common motif substring in diagnostic text. Restriction-site
  and homopolymer diagnostics can still name the relevant short motifs.
- The UI shows withheld states for sequences, RNA drawings and downloads. Positive
  approval preserves sequence detail, geometry, FASTA, GenBank and SBOL downloads.

Original user-submitted input and reference-catalog lookup APIs are not generated design
exports. Their existing owned-input/reference behavior remains intact. No public file
handler, production configuration, permissions, screening adapter or review-token
policy is changed.

## Compatibility and evidence

Migration `results.0004` defaults `sequence_free` to false. Historical candidate data
without saved approval is withheld; historical unclassified artifacts (including
reports) are withheld rather than guessed safe. Historical safety audit JSON remains
readable. There is no automatic approval or reclassification of old files. The
repository does not currently provision a screening adapter, so normal new runs
truthfully remain HOLD_SYSTEM.

Release lifetime is a separate unresolved policy question. Reads use the saved,
sequence-bound decision; they do not freshly revalidate screening, adapter validity,
or review tokens on every download. A genuine historical PASS/authorized REVIEW can
therefore remain usable after adapter or token expiry. Current evidence does not
retain review-token expiry or approver identity. Expiry/revocation semantics and their
regression tests must be defined before a real adapter is provisioned. This change
does not invent an expiry-on-read policy or silently revoke a genuine saved approval.

Baseline: `2baa75a7f0dc89f9aafac58dad50da5982f3f56a`. Copy the new
`tests/api/test_release_disclosure.py` into an isolated baseline checkout and run:

```text
uv run pytest tests/api/test_release_disclosure.py -k 'held_detail or old_or' -q
```

All 17 selected cases fail on baseline: raw held sequences are returned or files
download with HTTP 200. The same tests on the fix require redacted detail/structure
and HTTP 409 for held file/ZIP requests, while anonymous/other-owner requests retain
401/404. Tests also exercise a real pipeline HOLD, approved exports, immutable stored
data, partial approval, unknown nested fragments and optional malformed metadata.
Browser fixtures exercise withheld sequence text and drawings and recovery to an
approved candidate. These are computational and access-control tests, not biological
validation. F6 is an independent branch moving final report diagnostics; neither fix
depends on the other.
