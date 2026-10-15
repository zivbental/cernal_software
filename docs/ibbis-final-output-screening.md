# Local final-output screening: draft deployment contract

## Status and release boundary

This is an implemented, fail-closed integration with synthetic software validation,
not a validated biological screening deployment. **No real Common Mechanism database
or executable has been provisioned here, and production activation is not approved.**
The user/operator must select and approve the policy, validate the full deployment,
and obtain adequate hardware before enabling it. Leave `CERNAL_COMMEC_MANIFEST`
unset until those steps are complete. An unset, missing, invalid, stale or unavailable
deployment holds sequence release; it does not substitute a permissive fallback.

The pipeline supplies both the final switch and fully assembled plasmid sequences,
after assembly/optimization. Each complete molecule is supplied as linear FASTA; no selected window
stands in for it. Circular-origin-spanning detection, biological sensitivity/specificity
and context-dependent biological function are not established by this integration. One `configured_final_screens` call covers the run. Internally,
subprocess batches contain at most 64 records and one million bases. Inputs must be
uppercase, unmixed DNA/RNA alphabet, 41–100,000 bases per molecule. Unsupported or
malformed inputs hold release. RNA is normalized to DNA only for local CLI input;
policy evidence remains bound to the original submitted sequence digest.

Both switch and plasmid must have valid matching release records before sequence
artifacts are emitted. Persisted release metadata is revalidated at disclosure:
sequence digests, policy/software/database provenance and validity periods must match.
For Common Mechanism records, every disclosure also compares the saved manifest
identity with the currently configured `CERNAL_COMMEC_MANIFEST`. Changed or removed
active manifests invalidate old grants. This checks active deployment identity, not
a fresh hash of all installed database/software bytes; the immutable environment
requirement still applies. ISO timestamp `Z` and `+00:00` UTC representations are
normalized for this identity comparison. A report's existence is never approval
to disclose sequences.

## Pinned contract and draft policy

- Common Mechanism: `2.1.0`, upstream commit
  `24fe0390978eb66d13db4f91c18f122d051b1a65`.
- Native JSON output version: `0.6`.
- Local restrictive policy identifier: `commec-exact-pass-v1`.
- Required database revision keys: `biorisk`, `best_match`, `low_concern`,
  `control_lists`, matching the native output exactly.

The candidate policy accepts only aggregate `Pass`, with `Pass` biorisk and protein
taxonomy, all hit recommendations `Pass`, and nucleotide-taxonomy/low-concern status
`Pass` or the native tool's conditional `Skip`. This is **not** permission to disable
searches: the effective configuration must explicitly show
`skip_taxonomy_search`, `skip_nt_search`, `auto_update_databases` and `resume` all false.
The native tool's per-query conditional status and an operator-skipped search are
separate concepts. The policy remains subject to user review and validation against
the pinned tool's actual output semantics.

`Flag`, `Warning`, `Flag (Cleared)` and `Warning (Cleared)` all withhold release:
they create a screening-flag finding mapped to `BLOCK` by `SafetyGate`. They do not
become an automatically approvable `REVIEW`. Error, missing/inconsistent evidence,
unknown status, invalid schema, unavailable tool, timeout or changed installation
hold release. Generic selectable-marker review elsewhere in `safety.py` does not
create an exemption for Common Mechanism flags. Empty hits alone never prove success.
No fast mode, skipped taxonomy search, database reduction or reusable successful-
verdict cache is supported.

## Operator manifest schema

`CERNAL_COMMEC_MANIFEST` names an **operator-owned local JSON file**. It is not a job
parameter and must not be writable by ordinary users, jobs or the screening process.
Its paths determine the executable and database used by the worker. Treat the worker
environment, filesystem permissions, dependency search paths and this manifest as
security-sensitive deployment configuration, not uploaded user data.

Illustrative structure below is intentionally **not a usable deployment**: bracketed
values are placeholders, revisions are illustrative, and the inventories are abbreviated.
Do not replace unknown checksums with zeros or treat this example as validated evidence.

```json
{
  "executable": "/opt/commec/2.1.0/bin/commec",
  "database": "/srv/commec-db/validated-version",
  "files": {
    "config.yaml": "<actual SHA-256 of this file>",
    "biorisk/<relative-file-name>": "<actual SHA-256 of this file>"
  },
  "software_files": {
    "/opt/commec/2.1.0/bin/commec": "<actual SHA-256 of this file>",
    "/opt/commec/2.1.0/bin/python": "<actual SHA-256 of this file>",
    "/opt/commec/2.1.0/bin/blastn": "<actual SHA-256 of this file>",
    "/opt/commec/2.1.0/lib/<package-or-library-file>": "<actual SHA-256>"
  },
  "revisions": {
    "biorisk": "1.0",
    "best_match": "1.0",
    "low_concern": "1.0",
    "control_lists": "1.0"
  },
  "timeout_seconds": 300,
  "threads": 4,
  "manifest": {
    "adapter_name": "ibbis-common-mechanism",
    "adapter_version": "2.1.0",
    "database_id": "<operator's validated immutable deployment identifier>",
    "database_sha256": "<canonical files inventory SHA-256>",
    "software_sha256": "<canonical software_files inventory SHA-256>",
    "policy_version": "commec-exact-pass-v1",
    "validated_at": "<actual timezone-aware validation timestamp>",
    "expires_at": "<approved timezone-aware expiry timestamp>"
  }
}
```

Requirements:

1. `executable` and `database` must be absolute existing paths. The database
   directory must be immutable/read-only throughout a run. Database symlinks are
   rejected. Use a versioned directory; never update the active directory in place.
2. `files` must enumerate **every regular file** below the database directory, using
   relative POSIX paths and actual lowercase SHA-256 content digests. Include
   configuration and revision files. Added, removed or modified files invalidate the
   inventory. The manifest database digest covers this whole canonical inventory.
3. `software_files` maps absolute paths to actual content SHA-256 digests and must
   include the selected executable. Inventory the complete trusted runtime: package
   source/modules, interpreter, relevant libraries, command-line dependencies and
   resolution configuration. **Hashing only the launcher is not sufficient.**
4. Software inventory completeness is an operator trust requirement. The adapter
   verifies listed software files but cannot discover every dynamically loaded module,
   system library or executable dependency. A sealed image/read-only installation,
   controlled PATH/PYTHONPATH and validated dependency closure are required to make
   the inventory meaningful. Prevent unlisted code injection and mutable symlink
   targets. Pre/post hashing alone does not prevent an adversary from modifying
   bytes temporarily and restoring them; immutable deployment is essential.
5. The revision map must use exactly the four required keys and the actual revisions
   emitted by the pinned tool. Accepted revision strings currently match
   `1.<integer>` or `1.<integer>.<integer>`. Unknown formats hold; do not rewrite a
   tool's revision to force it through validation.
6. Inventory digests are computed by the existing `inventory_digest` function:
   SHA-256 of UTF-8 JSON with sorted keys and separators `(',', ':')`. Individual file
   hashes use `engine.artifacts.sha256_file`. A database archive checksum is not a
   substitute for the canonical extracted-file inventory digest.
7. `validated_at` and `expires_at` must be timezone-aware ISO timestamps and satisfy
   `validated_at <= now < expires_at`. They represent an actual operator validation
   window, not arbitrary future dates chosen to make a check pass.
8. Timeout must be an integer 1–3,600 seconds (default 300); thread count must be an
   integer 1–32 (default four). Pin resource limits as part of deployment acceptance.

The complete database and listed software are verified once before all internal
batches and again after the entire run. No result is returned as releasable until
the closing inventory verification succeeds. Any installation mismatch holds all
results. This amortizes integrity checks across batches without caching verdicts
or weakening the requirement that every complete final molecule is screened.

## Local execution and operations

The adapter launches the pinned executable without a shell, with a private temporary
FASTA, full-region screening and the configured thread count. CLI stdout/stderr are
suppressed; the native JSON and effective configuration are validated instead. The
input FASTA path and its digest are checked before trusting results. Native JSON is
bounded at 16 MiB and duplicate keys are rejected. Temporary working data is removed
when the subprocess step ends; it is not an audit archive. Use approved deployment
observability for failures without exposing raw sequence data.

POSIX process groups support termination of the CLI and its children on timeout;
native Windows is not enabled by this adapter. A failed process or malformed output never counts as a clean screen. Missing CLI
report/configuration files after invocation are `FAILED` evidence (error), while an
absent/unavailable deployment is `UNAVAILABLE`; both withhold release. Worker progress/cancellation is checked between
subprocess batches. The integration performs no database download. For a genuinely
local-only deployment, operators must enforce network isolation and disable upstream
auto-updates; a subprocess wrapper alone is not a network sandbox.

## Provisioning and acceptance checklist (not performed here)

- Review [upstream v2.1.0](https://github.com/ibbis-bio/common-mechanism/tree/v2.1.0)
  at the pinned commit and the [official installation requirements](https://github.com/ibbis-bio/common-mechanism/wiki/Install).
- Approve the release policy and responsibility for review/escalation before activation.
- Provision and validate the full pinned tool/dependency/database environment on a
  sufficiently sized isolated host. Preserve hashes and actual revision information.
- Verify database licensing independently. Upstream **code** is MIT-licensed; the
  current v2 database licence has not been verified for this work. Do not infer database
  redistribution rights from the code licence or redistribute database material.
- Validate effective configuration, native output paths/schema and end-to-end holds
  against the actual pinned tool. Synthetic tests cannot establish these operational
  or biological properties on their own.
- Run the separate full-tool protocol in
  [the benchmark guide](ibbis-final-screening-benchmarks.md), preserving complete/held/
  failed counts. Measure the full inventory cost, external processes and peak memory.
- Require actual biological validation under appropriate governance before making
  sensitivity/specificity or safety claims. Passing a policy parser is not such validation.
- Only after acceptance, arrange authorized deployment of the operator-owned manifest
  and worker environment. This document does not authorize activating it.

This workspace has roughly 31.45 GiB total / 28.80 GiB free storage and no `commec`
on PATH. Official documentation describes approximately 40 GB extracted databases
and recommends at least 50 GB free SSD, 16 GB RAM and 16 CPU threads. The database
cannot fit here. Full inventory checks alone imply roughly 80 GB of logical file
reads per full run at that database size, plus software verification and searches;
physical reads depend on caching. Actual runtime, capacity and biological performance
remain unmeasured. See [synthetic overhead evidence](evidence/ibbis-overhead-2026-10-15.json)
for the narrower JSON/parser/policy measurements and their pinned source hashes.
