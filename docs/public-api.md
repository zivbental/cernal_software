# External clients and API integration

Source baseline: `main` at `66a6d265577810e8943709f3e5bb21bffdab212c` (16 October 2026).
See [status and remaining work](status.md) for verification and release limits.

There is one HTTP API for the browser and scripts. Use an `X-API-Key` credential,
read capabilities from `/api/version`, submit `/api/design`, poll the returned URL,
and retrieve results/artifacts. The [HTTP reference](api.md) is the contract; this page
covers client installation and interpretation. [Tutorial](tutorial.md) provides a full
local request workflow.

## Install from reviewed source

No public package-registry publication is claimed. Install clients from the same
reviewed repository revision as your integration, rather than assuming `pip install
cernal` identifies this software.

| Client | Installation | Reference |
|---|---|---|
| Python | `uv pip install ./clients/python` in an activated uv environment; add `[pandas]` for tables | [Python README](../clients/python/README.md) |
| R | `R CMD INSTALL clients/r` after installing httr2, tibble and jsonlite | [R README](../clients/r/README.md) |
| MATLAB | Add the repository `clients/matlab` directory to the MATLAB path | [MATLAB README](../clients/matlab/README.md) |

Python example after installation (use a host and key you control):

```python
import os
from cernal import Client

client = Client(
    api_key=os.environ["CERNAL_API_KEY"],
    base_url=os.environ["CERNAL_BASE_URL"],
)
job = client.design(
    trigger_sequence="AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA",
    organism="ecoli",
    gate_families=["toehold"],
    seed=42,
    top_n=5,
)
rows = job.wait().to_dicts()
```

The example is a computational demonstration, not a validated biological design or
permission to release/synthesize sequences. Results can legitimately be rejected or
have no available sequence download. Review warnings and the manifest.

## Result and transport contract

- `top_n` limits returned ranked rows; `budget.max_designs` limits evaluation.
- Preserve result options (`top_n`, rejected/metric/artifact inclusion) on resumed job
  handles; explicit results calls can override them.
- A raw candidate retains nested design, triggers, warnings and metrics. Flattened
  tables are convenience views, not identical JSON column contracts.
- Best-candidate helpers select the lowest accepted rank and return no result when
  all candidates are rejected/unranked. Inspect that case explicitly.
- Server wait is bounded to 300 seconds. Submission transport timeout must exceed
  wait (clients use at least wait + 10 seconds); otherwise poll the accepted run.
- Reuse idempotency keys after ambiguous transport failures, honor 429 Retry-After,
  and stop polling at COMPLETED/FAILED/CANCELLED. Do not automatically resubmit failures.
- Protect keys and use only returned authenticated artifact routes; never storage paths.

## Verification scope

Python HTTP conformance/transport/ranking tests are present and run in CI. R raw/table
and live HTTP conformance have recorded hosted evidence; the live suite uses a
LocalEngine-computed precompleted fixture and is not live-worker polling acceptance.
MATLAB runtime conformance remains unexecuted and experimental. See [status](status.md)
for dated evidence and [testing](testing.md) for commands. Runtime support should be
stated separately from source implementation and package publication.

## Original API design proposal

The [original public-API proposal](archive/operator-design/public-api.md) retains design
rationale, scope/quota discussion, client plans, optional webhook ideas and historical
implementation tasks. It is not a second current specification. API keys and the design
route are implemented; optional proposal features and old “stub-first” statements do
not establish what is available now. ADRs retain decisions; source and tests establish
behavior.

## Merged AND and screening-status scope

The [eukaryotic AND guide](and-gate.md) specifies Human/yeast DE requests with
`and_inputs`, optional `and_gate`, two trigger inputs and exactly one gate. `/runs`
places these in `params`; `/design` exposes them directly. `/api/version` publishes
family input counts/modes and `limits.max_gate_inputs`. The ordinary single-input
default remains unchanged. `folding.salt_molar` is finite and lies in 0.01–6.0 mol/L;
the ordinary reference default is 1.021 M, while AND defaults are documented in its guide.

Engine-only `closure_set`, `stem_order` and `stems_per_pair` are not public constraints.
`constraints.closure_set` is rejected with 422, including `strict=false` requests.
The merged [screening-status UI contract](sequence-screening.md) remains optional:
the main backend does not supply operational Common Mechanism evidence, so the UI
shows Not screened. UI evidence never overrides artifact availability or release policy.
