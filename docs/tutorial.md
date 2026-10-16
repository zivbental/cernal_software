# Tutorial: one local design, from request to review

Source baseline: `main` at `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

## Before starting

Complete [development setup](development.md) on Linux/WSL2 and keep `./do dev`
running. Use a disposable local database and synthetic example sequence. This tutorial
executes real computation; completion does not establish experimental efficacy or
permission to synthesize/export withheld sequences.

For the browser path, sign in at http://localhost:8000 using your approved account,
open New Circuit, select direct input and a compatible host/family advertised by the
app, paste the example sequence below, review configuration and submit. Follow the
queued/run view, then inspect accepted and rejected candidates, warnings, metrics,
RNA structure and artifact availability. `/guide` provides in-app instructions.

Direct target input is normalized to RNA: DNA-alphabet T is accepted and converted to U
by `normalize_trigger_sequence`; it does not select a DNA circuit-design workflow.

## Script path: authenticate and inspect capabilities

Create a local API key for your existing account (the command prints its secret once):

```bash
./do key YOUR_USERNAME tutorial
export CERNAL_BASE_URL=http://127.0.0.1:8000
read -rs -p 'API key: ' CERNAL_API_KEY; echo
export CERNAL_API_KEY
curl --fail-with-body "$CERNAL_BASE_URL/api/auth/whoami" \
  -H "X-API-Key: $CERNAL_API_KEY"
curl --fail-with-body "$CERNAL_BASE_URL/api/version"
```

The shell key variable is only for this session; do not paste the secret into a file,
commit or chat. Creation requires administrator/host access; on a hosted service use
its session-authenticated key management instead. `whoami` confirms the key, scopes
and quotas. `/version` confirms available hosts/families/limits before submission.

## Validate and submit

Create `tutorial-request.json` in your working directory:

```json
{
  "trigger_sequence": "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA",
  "organism": "ecoli",
  "gate_families": ["toehold"],
  "seed": 42,
  "top_n": 5,
  "idempotency_key": "local-tutorial-001"
}
```

Validate without saving a run, then submit the identical request:

```bash
curl --fail-with-body "$CERNAL_BASE_URL/api/design?dry_run=true" \
  -H "X-API-Key: $CERNAL_API_KEY" -H 'Content-Type: application/json' \
  --data-binary @tutorial-request.json
curl --fail-with-body "$CERNAL_BASE_URL/api/design" \
  -H "X-API-Key: $CERNAL_API_KEY" -H 'Content-Type: application/json' \
  --data-binary @tutorial-request.json
```

Dry run returns resolved defaults and an uncalibrated estimate, not a runtime guarantee.
Submission returns 202 with `job_id`, `poll_url` and `results_url`. Reusing this key
with the same request returns the existing run. Change the key for a new intentional
run; do not change it merely because a network response was lost.

## Poll and inspect

Copy the returned job ID; poll every few seconds and stop on a terminal state:

```bash
JOB_ID=REPLACE_WITH_RETURNED_JOB_ID
curl --fail-with-body "$CERNAL_BASE_URL/api/design/$JOB_ID" \
  -H "X-API-Key: $CERNAL_API_KEY"
curl --fail-with-body "$CERNAL_BASE_URL/api/design/$JOB_ID/results?top_n=5&include_rejected=true&include_metrics=true" \
  -H "X-API-Key: $CERNAL_API_KEY"
curl --fail-with-body "$CERNAL_BASE_URL/api/runs/$JOB_ID/artifacts" \
  -H "X-API-Key: $CERNAL_API_KEY"
```

On FAILED/CANCELLED, read the error/warnings rather than assuming results are complete.
On QUEUED with `worker_available=false`, inspect the development terminal and
[worker guidance](operations.md). Do not use synchronous execution to hide a queue
failure. COMPLETED can include rejected candidates, withheld downloads and scientific
limitations; review [interpretation](scientific-interpretation.md).

Only fetch an artifact's returned `download_url` when `download_available` is true.
Use the authenticated route with the same key. An unavailable/409 download needs the
applicable release decision, not a filesystem workaround.

## Next inputs

For reference-gene input replace `trigger_sequence` with `gene_id`; do not send both.
For DE input upload a validated table and use its `dataset_id`, or use `dge_csv` with
`/design`. See [API](api.md), [modalities](modalities.md) and [public datasets](public-datasets.md).
Keep input/reference provenance, normalized settings, seed, tool versions and manifest
when comparing runs. Revoke the tutorial key when finished, and remove only disposable
local data after review.

## Optional eukaryotic AND workflow

The direct-input example above stays single-input. For Human or yeast, use a DE
dataset, select Eukaryotic AND Toehold in the wizard, and choose two up-regulated
inputs. Follow the [AND tutorial and API example](and-gate.md#using-it-in-the-application)
for `and_inputs`, `max_triggers=2` and one gate. Canonical aliases such as SELE and
ENSG00000007908 still request two windows when they identify the same gene.
Inspect the AND evidence panel and its limitations. The screening-status panel is
merged UI groundwork; Not screened is expected without backend evidence and does
not authorize downloads. Artifact release remains a separate decision.
