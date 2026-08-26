# Engine deployment — on-demand compute

> **Planning document. Nothing here is implemented yet.**
> Companion to [`step-5-engine-plan.md`](step-5-engine-plan.md), which covers the science.
> This covers **where the engine runs** and how the Platform talks to it.

Goal: the heavy machine should exist only while it is computing, so you are not paying
for an idle server. The web VPS stays small and always on.

---

## 1. The number this hinges on

| | |
|---|---|
| Analyses per day | ~5 |
| Minutes per analysis | ~10 (measured basis in [step-5 §3](step-5-engine-plan.md)) |
| Compute needed per day | ~50 minutes |
| **Duty cycle** | **~3.5%** |

So an on-demand compute host is idle **96% of the time**. That is the saving, and it is
provider-independent: whatever the machine costs per hour, you pay roughly a
twenty-ninth of the monthly figure.

**When this is clearly worth it:** the machine is expensive — many cores, lots of RAM, or
a GPU. A 16-core / 32 GB box billed at 3.5% is transformative.

**When it is not:** the machine is a €20/month VPS. Then on-demand saves ~€19/month and
costs you a network boundary, a second deployment, credentials, cold starts and a new
class of failure. Buying one slightly larger always-on VPS and running everything on it
([step-5 §4 option A](step-5-engine-plan.md)) is the better trade at that size.

Worth settling before building: **what does the heavy machine actually need?** The answer
comes from a measured run ([step-5 §3](step-5-engine-plan.md)), which is the reason that
measurement is the first thing Step 5 should produce.

The rest of this document assumes the answer is "expensive enough to be worth it".

---

## 2. Three shapes of on-demand compute

All three keep the engine behind `EngineClient`, so the Platform is unchanged in each.

### Shape A — Auto-waking HTTP service ⭐ *recommended*

The engine is a container that the platform provider **starts on an incoming request and
stops after an idle period**. Fly.io Machines do this natively; Cloud Run and Container
Apps have equivalents.

```
Platform worker ──HTTPS──▶ [engine.fly.dev]
                            ├─ asleep  → provider boots it (~1–5 s), request proceeds
                            └─ idle 5 min → provider stops it, billing stops
```

**Why this one:** there is **no lifecycle code to write**. `HttpEngineClient` makes a
request; waking up is the provider's problem. No cloud API tokens in the Platform, no
boot polling, no idle watchdog, nothing to leak or get stuck. It is the smallest possible
diff from what exists.

**Watch for:** cold start on a large image (keep it lean); per-second billing granularity;
and making sure your polling does not keep it awake after a run ends — our client already
stops polling on a terminal status, so this is fine as written.

### Shape B — Explicitly orchestrated VM

The Platform calls a provider API to boot a VM, waits for health, submits, polls, and
stops it after an idle timeout.

```
Platform worker ──provider API──▶ boot VM  (30–120 s)
                ──HTTPS─────────▶ submit, poll, collect
                ──provider API──▶ stop VM
```

**Why you might:** works with any provider (Hetzner, DigitalOcean, AWS), and you can pick
exactly the machine type. Fits if TAU or the team already has cloud credits somewhere
specific.

**Cost:** you own the lifecycle. Boot orchestration, health polling, an idle watchdog, and
— the part people underestimate — **a reaper that stops machines nobody is using**, because
a crashed worker that never issues the stop call bills you until someone notices.

### Shape C — Batch job, no service at all

The Platform submits a **job**, not a request. A container starts, reads its input,
computes, writes its result, and exits. Nothing listens; nothing idles.

```
Platform ──▶ upload input to object storage
         ──▶ submit job (Cloud Run Jobs / AWS Batch / Hetzner cloud-init)
         ◀── poll job status
         ◀── download result manifest + artifacts
```

**Why it is appealing:** our contract is *already job-shaped* — `JobRequest` in,
`JobResult` out, poll for status. A batch service matches that better than a
long-running HTTP service does, and idle cost is structurally zero.

**Cost:** the progress callback becomes coarse (job states, not stage labels) unless the
job posts progress back, and error reporting is weaker — you get exit codes and logs
rather than a clean `error` string. Cancellation means killing a job rather than a
cooperative flag.

### Choosing

| If… | Shape |
|---|---|
| You want the least new code and can pick the host | **A** |
| You must use a specific provider, or need an exact machine type | **B** |
| Runs are long, infrequent, and coarse progress is acceptable | **C** |
| Runs are short (< 2 min) | none — cold start dominates; stay in-process |

**Recommendation: Shape A.** It achieves the goal with roughly a day of work, and it is
the only one that does not put infrastructure credentials or lifecycle state into the
Platform.

---

## 2a. "Can one instance launch a bigger sub-instance?"

A common and reasonable question, and the answer clears up which of the shapes above is
actually available to you.

**No — there is no parent/child relationship between compute instances.** You cannot nest
a machine with more resources inside a smaller one. Nested virtualisation exists on some
providers, but a guest is always bounded by its host: a 2 vCPU VPS can never contain an
8 vCPU anything. Resources come from the provider's hardware, not from your instance.

**But the thing you want works.** Your small always-on VPS can, through the provider's
API, create a **sibling** instance of any size — same account, same project, same private
network, one bill. That is Shape B, and "same private network" is what makes it *feel*
like it lives under the web server:

```
        ┌─ your cloud project ────────────────────────┐
        │                                             │
        │  web VPS (2 vCPU, always on)                │
        │      │  provider API: create / delete       │
        │      ▼                                      │
        │  engine host (16 vCPU, minutes per day)     │
        │                                             │
        │  ── private network, no public IP ──        │
        └─────────────────────────────────────────────┘
```

The engine host needs **no public address at all**: the web VPS reaches it on an internal
IP, which resolves most of [§7](#7-security) by construction rather than by firewall rules.

### The three mechanisms, concretely

| Mechanism | How it works | Idle cost | Verdict |
|---|---|---|---|
| **Create / destroy a sibling** | Web VPS calls the provider API to create an instance per run, then deletes it | **Zero** — the machine does not exist | Shape B. Most control, most code |
| **Stop / start a sibling** | The instance persists but is powered off between runs | Usually **disk only** — a few € a month | Shape B, simpler. Faster boot, no re-provisioning |
| **Resize one instance** | Scale a single machine up before a run, down after | Full price until you scale down | **Avoid** — see below |
| **Managed jobs / auto-wake** | No instance you own; the provider runs a container on demand | Zero | Shapes A and C. Least code |

### Why not just resize?

It looks like the simplest option and it is the worst fit here:

- **It needs a reboot.** If that is your web VPS, the app goes down during every run.
- **Scale-down is a step that can silently fail**, and you keep paying the large rate
  until somebody notices. Creating and destroying leaves no such trap.
- **It does not compose.** Two concurrent runs still contend on one machine, where
  siblings just means two of them.

Resizing is for load that grows and stays grown. Yours is spiky and short — the opposite.

### What to reach for

- **Auto-wake or managed jobs** (Shapes A / C) if your provider offers them. Nothing to
  create, nothing to remember to destroy.
- **Stop / start a sibling** (Shape B) if not. Keep a pre-provisioned engine host powered
  off; boot it on submit, power it down when idle. Faster than re-creating, and the disk
  cost is small enough to ignore.
- **Create / destroy** only if you want the machine type to vary per run, or you refuse
  to pay for an idle disk.

In all three the Platform is unchanged — `CERNAL_ENGINE` points at `HttpEngineClient` and
everything above the boundary carries on as it is.

## 2b. Where Shape A can actually run

Shape A is not something you install — **scale-to-zero is a property of the platform**.
On a plain VPS provider there is no auto-wake, and Shape A is simply unavailable; you
build Shape B instead. So the hosting choice and the shape choice are the same decision.

### What this workload demands of a platform

| Requirement | Why it rules things out |
|---|---|
| **~10 minute jobs** | Function platforms with short ceilings (AWS Lambda caps at 15 min) are marginal at best |
| **4–16 vCPU, several GB** | Folding is CPU-bound. Small function tiers will not do |
| **Scale to zero** | The entire point. "Minimum one instance" plans defeat it |
| **Per-second or per-minute billing** | Hourly granularity wastes most of a 10-minute run |
| **Background work stays alive** | See the trap below |

### The trap: idle is measured in *requests*, not CPU

Auto-wake platforms usually decide a machine is idle because **no requests have
arrived** — not because it is doing nothing. A background computation with no inbound
traffic can be stopped mid-run.

Our contract happens to sidestep this. The Platform polls `GET /v1/jobs/{id}` every ~3
seconds for the whole run, so the machine sees continuous traffic and stays up; when the
run reaches a terminal status the client stops polling, and the machine goes to sleep on
its own. The polling that exists for the progress bar doubles as the keep-alive.

> Verify this against whatever platform you pick, and set the idle timeout comfortably
> above the poll interval. If you ever move to a callback instead of polling, this
> protection disappears with it.

### Candidate platforms

Capabilities move quickly — treat this as where to look, and check current limits and
prices yourself.

| Platform | Scale to zero | Notes |
|---|---|---|
| **Fly.io Machines** | Yes, native start/stop | Per-second billing, private networking between your own apps. The closest fit |
| **Google Cloud Run** | Yes | Long request timeouts; **Cloud Run Jobs** suits Shape C even better |
| **Azure Container Apps** | Yes | Scale-to-zero supported; check per-job CPU ceilings |
| **AWS** | Not directly | Lambda's 15 min ceiling is tight. Fargate needs orchestration; **AWS Batch** is Shape C |
| **Hetzner / DigitalOcean** | **No** | No auto-wake. Excellent value for Shape B stop/start |

### The cross-provider consequence

**If the web VPS and the engine are on different providers, there is no private network
between them.** The engine then needs a public endpoint protected by a service token
([§7](#7-security)) rather than being unreachable by construction. That is workable, and
it is strictly more to get right.

### Four combinations that make sense

| # | Web app | Engine | Private net | Trade |
|---|---|---|---|---|
| 1 | Fly | Fly Machines | **Yes** | One platform, one bill, auto-wake, no lifecycle code. **Recommended if you are not already committed elsewhere** |
| 2 | Small VM on GCP/AWS | Cloud Run Jobs / AWS Batch | **Yes** | Shape C. Zero idle by construction, coarser progress |
| 3 | Hetzner VPS | Fly Machines | No | Cheapest web hosting, but a public engine endpoint and a token to manage |
| 4 | Hetzner VPS | Hetzner sibling, stopped when idle | **Yes** | No auto-wake, so you write the lifecycle. Simple, cheap, entirely in your control |

**Recommendation:** if nothing constrains you, **combination 1** — put both on Fly. The
Django app and worker run there perfectly well, the engine becomes a second app that
sleeps between runs, and they talk over private networking with no public engine endpoint
and no cloud credentials in the Platform.

**If you would rather keep the web app on a cheap VPS**, take **combination 4** and accept
Shape B. Stop/start of a pre-provisioned sibling is perhaps a hundred lines behind the
`EngineClient` interface, and it keeps everything on one provider with a private network.

Either way the Platform is untouched: `CERNAL_ENGINE` names the client, and the boundary
test keeps the rest honest.

---

## 3. What splitting actually forces you to build

This is the honest cost. Today the engine reads a local file and writes to a local
directory; neither is true across a network.

| # | Concern | Why it appears | Work |
|---|---|---|---|
| 1 | **Input transfer** | `dataset.file.path` does not exist on the other machine | **M** |
| 2 | **Artifact return** | Artifacts are written to `output_dir` on the compute host | **M** |
| 3 | **Authentication** | An open engine endpoint is free compute for the internet | **S** |
| 4 | **Cold-start handling** | The run sits waiting for a machine that does not exist yet | **S** |
| 5 | **Timeouts and retries** | Every call is now fallible | **S** |
| 6 | **Idempotency storage** | The key exists in `JobRequest`; the engine must now honour it | **S** |
| 7 | **Engine-side job state** | The engine must remember jobs across requests | **M** |
| 8 | **Two deployments** | Engine and Platform version independently | **M** |
| 9 | **Observability** | Failures now happen on a machine you are not looking at | **S** |

Items 1 and 2 are the substantive ones. Two options:

**Object storage (recommended).** The Platform uploads the dataset to S3-compatible
storage and passes a short-lived signed URL in `JobRequest.input_path`; the engine uploads
artifacts and returns signed URLs in `ArtifactRef.path`. This is exactly what design map
15 specifies, and it is the pattern that keeps working when the engine moves again.

**Inline transfer.** The Platform POSTs the dataset with the job and downloads artifacts
in the result call. No object storage to run, but it puts potentially large files through
request bodies, and a 100 MB dataset in a POST is unpleasant on both ends.

> Either way, `ArtifactRef` already carries `path`, `media_type` and `checksum_sha256`, so
> only the *resolution* of `path` changes. The Platform already verifies those checksums on
> import — which becomes far more valuable once bytes cross a network.

---

## 4. Contract changes

Smaller than you might expect, because the contract was designed for this.

`JobRequest` and `JobResult` need **no new fields**. `input_path` becomes a URL rather
than a filesystem path; `ArtifactRef.path` likewise. Both are already strings the engine
treats as opaque.

What is new:

```python
# src/engine/client.py — a third implementation of the existing Protocol
class HttpEngineClient:
    """Talks to an engine deployed elsewhere.

    Reads its configuration from the environment rather than Django settings, so §3
    still holds: engine/ may read os.environ, it may not import django.conf.
    """
    def __init__(self) -> None:
        self.base_url = os.environ["CERNAL_ENGINE_URL"]
        self.token = os.environ["CERNAL_ENGINE_TOKEN"]

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult: ...
    def capabilities(self) -> EngineCapabilities: ...
```

```python
# src/engine/service.py — new, the same code LocalEngine runs, behind HTTP
POST /v1/jobs              → 202 {engine_job_id}      (idempotent on the key)
GET  /v1/jobs/{id}         → technical status + progress
GET  /v1/jobs/{id}/result  → JobResult
POST /v1/jobs/{id}/cancel
GET  /version              → EngineCapabilities
```

Then `CERNAL_ENGINE=engine.client.HttpEngineClient`. **No Platform code changes** —
guaranteed by `tests/test_boundary.py`, which already forbids `apps/` and `api/` from
importing anything but `engine.contract` and `engine.client`.

`engine-contract.md` §4 maps every field onto these endpoints already, so the payload
design is done.

---

## 5. What the run state machine has to learn

A run can now be waiting for a *machine*, not just for compute. The six states in
[§6](software-design.md) stay — this is a `stage` change, not a status change, which is
exactly the mapping principle design map 07 sets out.

```
QUEUED   "Waiting for a compute machine"      ← new, can last 1–120 s
RUNNING  "Staging input"                      ← new, upload time
RUNNING  "Discovering candidate features"     ← as today
...
RUNNING  "Collecting results"                 ← new, download time
COMPLETED
```

Two things to get right:

**Say what is happening during a cold start.** A user watching "Queued" for two minutes
assumes it is broken. `stage` is already displayed verbatim by the progress screen, so
this costs nothing but the words.

**Do not let polling keep the machine awake.** Our client stops polling on a terminal
status, so a finished run costs nothing. Confirm this holds for `FAILED` and `CANCELLED`
too, not only `COMPLETED`.

---

## 6. Failure modes that only exist once it is remote

These are the ones that will actually bite, and none of them exist today:

| Failure | What must happen |
|---|---|
| **Machine never boots** | Fail the run with "Could not reach the compute service", not a stack trace. Cap the wait |
| **Machine dies mid-run** | The Platform must notice and mark the run `FAILED`, rather than polling a corpse forever. Give polling a deadline |
| **Machine dies after computing, before returning** | The expensive part succeeded and is lost. This is the argument for the engine persisting results before acknowledging |
| **Duplicate submission after a timeout** | Exactly what `idempotency_key` is for — but the engine must now *store* keys, which it does not today |
| **Orphaned machine** (Shape B) | Bills you until someone notices. Needs a reaper, and an alarm |
| **Version skew** | Platform expects `schema_version` 2, engine serves 1. `GET /version` exists; the Platform should check it and refuse clearly |
| **Artifact download fails** | Already handled: `import_job_result` is atomic and reports an import failure distinctly from a science failure, so a retry re-imports rather than recomputes |

The last row is worth noticing — the Step 3 work on atomic import and distinguishing
import failure from computation failure was built for exactly this, before it was needed.

---

## 7. Security

Once the engine is reachable over a network, it is a service that will execute expensive
work for anyone who can reach it.

- **Authenticate the Platform, not users.** A service token the Platform worker holds,
  verified by the engine. It is **never** sent to the browser — the browser has no idea
  the engine exists.
- **Do not expose the engine publicly** if the provider allows private networking. On
  Fly, that is internal `.flycast` addressing; on a VM, a firewall rule allowing only the
  web VPS.
- **Short-lived signed URLs** for input and artifacts, not long-lived credentials handed
  to the engine.
- **Cap the work.** Maximum designs, maximum runtime, maximum input size — enforced
  engine-side. Otherwise a malformed submission can run up a bill.
- **Rotate the token** via environment variable; no redeploy of the Platform needed.

Design map 16 covers this boundary; the summary above is what actually has to exist.

---

## 8. Implementation phases

Each leaves the system working. Nothing here starts before [step-5](step-5-engine-plan.md)
5a–5f have produced a real pipeline and a real timing.

| # | Phase | Outcome |
|---|---|---|
| **D0** | **Measure.** Real run on real data; record wall time, peak RAM, cores used | The numbers that size the machine — and confirm this is worth doing |
| **D1** | **Containerise the engine.** Dockerfile with ViennaRNA; `engine/service.py`; runs `LocalEngine` behind HTTP. Local only | `docker run` + `curl` produces a `JobResult` |
| **D2** | **`HttpEngineClient`.** Third implementation of the Protocol; contract tests run it against both `LocalEngine` and the container and assert identical results | The same run, two engines, same output |
| **D3** | **Object storage.** Signed input URL in, signed artifact URLs out. `MinIO` locally, S3-compatible in production | Input and artifacts cross a boundary |
| **D4** | **Auth + limits.** Service token, private networking, caps on runtime and size | Safe to expose |
| **D5** | **Deploy on-demand.** Shape A host; measure cold start; wire the new `stage` labels | Idle cost ≈ zero |
| **D6** | **Failure drills.** Kill the machine mid-run, submit twice with one key, break the token — confirm each lands in a terminal state with a readable message | §6 verified, not assumed |

**D6 is not optional.** Every failure in §6 is new, and the only way to know they are
handled is to cause them.

---

## 9. What does not change

Worth stating, because it is the return on the boundary work:

- Every model, endpoint and screen in Steps 2–4
- `MockEngine`, which remains what CI and frontend development use
- The scoring layer, the `GateFamily` interface, `default-v1`
- `tests/test_boundary.py`, which is what makes this claim checkable rather than hopeful
- The six run states, and every product-facing status the researcher sees

**The user-visible difference should be a slightly longer wait on the first run of the
day, and nothing else.**

---

## 10. Decision checklist

Before D1:

1. **What does the machine need?** From D0. Cores, RAM, wall time.
2. **Is on-demand worth it at that size?** Compare against one larger always-on VPS (§1).
3. **Which provider?** Determines Shape A vs B. Auto-start support is the deciding feature.
4. **Object storage or inline transfer?** (§3). Object storage if datasets approach the
   100 MB cap.
5. **Who operates it?** A second deployment needs someone who will notice when it breaks
   during the competition.

Question 5 is the one teams skip. A compute host nobody is watching fails silently at the
worst possible moment — and unlike the web VPS, nobody notices it is down until somebody
submits a run.
