# Deployment

> **Planning document for Step 6. Nothing here is implemented yet.** The task list is
> [ROADMAP.md §6](ROADMAP.md); this is the design and the reasoning behind it.
>
> The engine's internals are in [engine.md](engine.md); the boundary this depends on is
> [architecture.md §3](architecture.md#3-the-boundary-rule).

**The shape:** a small always-on VM runs the product; a container runs the science on
demand and stops. Idle compute cost is zero.

```
┌─ Compute Engine · e2-small · always on ────────────────────┐
│   Caddy → gunicorn → Django                                │
│   django-q2 worker                                         │
│   Persistent disk:  var/cernal.db  +  var/media/           │
└───────────┬────────────────────────────────────────────────┘
            │ 1. upload dataset          ┌────────────────────┐
            ├───────────────────────────▶│  Cloud Storage     │
            │                            │   datasets/        │
            │ 2. jobs.run(overrides)     │   runs/<id>/       │
            ▼                            │     progress.json  │
┌─ Cloud Run Job · 4–8 vCPU ─────────┐   │     result.json    │
│   cernal-engine container          │◀──┤     artifacts/     │
│   · starts on submit               │──▶│                    │
│   · stages input down              │   └────────────────────┘
│   · runs LocalEngine               │             ▲
│   · stages artifacts up            │             │
│   · exits · ZERO idle cost         │  3. poll progress, read result
└────────────────────────────────────┘
```

| Piece | Service | Why |
|---|---|---|
| Web + worker | **Compute Engine** VM | It is a VPS. `var/` is a directory, backups are a file copy, and everything [ADR 0002](decisions/0002-sqlite-and-orm-task-queue.md) assumes still holds |
| Engine | **Cloud Run Jobs** | Run a container to completion, then stop. No compute environment or queue to configure |
| Transfer | **Cloud Storage** | Datasets in; artifacts and progress out |
| Identity | **Service accounts** | No passwords or keys anywhere ([§5](#5-identity-no-keys-anywhere)) |
| Image | **Artifact Registry** | Where the engine container lives |

---

## 1. Why this shape

### 1.1 The number it hinges on

| | |
|---|---|
| Analyses per day | ~5 |
| Minutes per analysis | ~10 ([ROADMAP.md §3](ROADMAP.md)) |
| Compute needed per day | ~50 minutes |
| **Duty cycle** | **~3.5%** |

An on-demand compute host is idle **96% of the time**. That is the saving, and it is
provider-independent: whatever the machine costs per hour, you pay roughly a
twenty-ninth of the monthly figure.

**When this is clearly worth it:** the machine is expensive — many cores, lots of RAM, or a
GPU. A 16-core / 32 GB box billed at 3.5% is transformative.

**When it is not:** the machine is a €20/month VPS. Then on-demand saves ~€19/month and
costs you a network boundary, a second deployment, credentials, cold starts and a new class
of failure. **Buying one slightly larger always-on VPS is the better trade at that size.**

So the deciding input is *what does the heavy machine actually need?* — which comes from a
measured run, and is why that measurement is the first thing Step 5 should produce
([ROADMAP.md](ROADMAP.md) E6/C0).

### 1.2 Three shapes of on-demand compute

All three keep the engine behind `EngineClient`, so the Platform is unchanged in each.

| Shape | How it works | Cost of it |
|---|---|---|
| **A · Auto-waking HTTP service** | The provider starts the container on an incoming request and stops it after an idle period (Fly Machines, and equivalents on Cloud Run / Container Apps) | **No lifecycle code at all** — the smallest possible diff. But only available where the platform provides it, and cold start on a large image is real |
| **B · Explicitly orchestrated VM** | The Platform calls a provider API to boot a VM, waits for health, submits, polls, and stops it | Works with any provider and any machine type. **You own the lifecycle** — boot orchestration, health polling, an idle watchdog, and a reaper for machines nobody is using, because a crashed worker that never issues the stop call bills you until someone notices |
| **C · Batch job, no service at all** ⭐ | The Platform submits a **job**. A container starts, reads its input, computes, writes its result, and exits. Nothing listens; nothing idles | **Our contract is already job-shaped** — `JobRequest` in, `JobResult` out, poll for status. Idle cost is structurally zero. The cost is that progress and error reporting must be re-earned ([§6](#6-progress-cancellation-idempotency)) |

**Choosing:**

| If… | Shape |
|---|---|
| You are on a major cloud (GCP, AWS, Azure) | **C** — batch jobs are what these platforms are best at, and IAM removes the shared secret entirely |
| You want the least new code and can freely pick the host | **A** |
| You must use a specific provider, or need an exact machine type | **B** |
| Runs are short (< 2 min) | **none** — cold start dominates; stay in-process |

> **A trap worth knowing about Shape A:** on most platforms, *idle* is measured in
> **requests, not CPU**. A scale-to-zero service that is being polled never scales to zero.
> Our client already stops polling on a terminal status, so this happens to be fine — but
> it is the kind of thing that silently costs money.

### 1.3 Why Google Cloud, and one simplification it buys

**Cloud Run Jobs** is Shape C with the least configuration — no compute environment, no
queue, no scheduler to set up.

**Not Cloud Run *services* for the web app.** Cloud Run has no persistent disk, and SQLite
over a network filesystem is a bad idea. A plain VM keeps the product deployment boring,
which is the whole point of ADR 0002.

**No presigned URLs.** Presigned URLs exist to hand access to something *outside* your trust
boundary. Here the engine is inside it: same project, its own service account. So the
Platform passes plain `gs://` paths and the job's service account reads and writes them
directly.

```python
JobRequest.input_path = "gs://cernal-data/datasets/<uuid>/expression.csv"
JobRequest.output_dir = "gs://cernal-data/runs/<run-id>/artifacts"
```

No signing, no expiry to tune, no `signBlob` permission, no clock skew. `input_path` and
`output_dir` are already opaque strings in the contract, so **nothing in
`engine/contract.py` changes.**

An S3 equivalent would be the same design with presigned URLs added back, and the entrypoint
in [§3](#3-keeping-cloud-code-out-of-engine) is the only file that would differ.

---

## 2. One repository, two artifacts

### 2.1 Deployment separation is not repository separation

The design maps specify two repositories. [ADR 0001](decisions/0001-single-repo-in-process-engine.md)
deferred that. Now that the engine deploys as a separate container, does the deferral end?

**No. Stay in one repository, and build two deployable artifacts from it.**

The engine is *already* a separate Python package with an enforced boundary; the container
simply builds a subset of the repo. Splitting the repo would buy independent release cadence
and cost four things that currently keep this architecture honest:

| What a split would break | Why it matters |
|---|---|
| `tests/test_boundary.py` | It can only check imports it can see. Across repos the boundary becomes a convention again |
| The shared contract | `engine/contract.py` would have to become a versioned, published package that both repos depend on — with its own release process |
| Equivalence tests ([§8](#8-the-equivalence-discipline)) | Running the same job through both engines and comparing needs both in one place |
| Atomic contract changes | Adding a field currently touches one PR. Across repos it is a three-PR dance with a version bump in the middle |

**When to actually split** — not on a date, on a symptom: the scientific team is large
enough to want its own review queue; the contract has stopped changing, so publishing it as
a package is cheap; or someone outside the team needs the engine without the product. The
seam is built, so splitting later is a day's work. **Do it when it hurts not to.**

| Artifact | Built from | Runs on | Contains |
|---|---|---|---|
| Web + worker | the whole repo | Compute Engine VM | Django, apps, api, engine *client* |
| Engine container | `src/engine/` **only** | Cloud Run Job | domain, stages, gates, tools, scoring, ViennaRNA |

### 2.2 Dependency groups

Today `engine/` imports **only the standard library**. Step 5 changes that, and this is the
moment to stop the two halves' dependencies from mixing. This is task **E0** and it is
independent of everything else — it can be done today.

```toml
[project]
dependencies = []          # nothing shared

[project.optional-dependencies]
platform = [
    "django>=5.2,<6.0", "django-ninja>=1.3", "django-q2>=1.7",
    "django-environ>=0.11", "openpyxl>=3.1", "whitenoise>=6.7", "gunicorn>=23.0",
    "google-cloud-run>=0.10", "google-cloud-storage>=2.18",   # to submit jobs
]
engine = [
    "viennarna>=2.7", "numpy>=2.0", "pandas>=2.2",
    "google-cloud-storage>=2.18",                              # to stage files
]
dev = ["pytest>=8.3", "pytest-django>=4.9", "ruff>=0.8"]
```

The VM installs `platform`; the container installs `engine`. Neither installs the other.

### 2.3 The Dockerfile is a proof of the boundary

```dockerfile
# deploy/Dockerfile.engine
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --extra engine --no-dev --frozen

# Only the engine. Not apps/, not config/, not api/.
COPY src/engine/ ./engine/

ENTRYPOINT ["uv", "run", "python", "-m", "engine.runner.entry"]
```

> Django is not installed and the Platform source is not copied, so **if `engine/` ever
> grows a Django import, the container fails to start.** `tests/test_boundary.py` says the
> boundary holds; the container makes it impossible to violate.

---

## 3. Keeping cloud code out of `engine/`

The engine must not learn about Google Cloud. If a stage starts calling a storage client,
the boundary that makes it testable and portable is gone.

**A thin entrypoint stages files; the engine stays filesystem-based.**

```python
# src/engine/runner/entry.py — the ONLY file that knows about object storage
def main() -> None:
    request = JobRequest(**json.loads(os.environ["CERNAL_JOB_REQUEST"]))

    with tempfile.TemporaryDirectory() as work:
        local_input = stage_down(request.input_path, work)  # gs:// -> /tmp, or a no-op
        local_out = Path(work) / "out"

        result = LocalEngine().run(
            replace(request, input_path=local_input, output_dir=str(local_out)),
            on_progress=publish_progress(request),  # writes progress.json
        )

        stage_up(local_out, request.output_dir)  # /tmp -> gs://
        write_json(f"{request.output_dir}/../result.json", asdict(result))
```

Three consequences worth having:

1. **`LocalEngine` and every stage are unchanged** — they still take local paths, so they
   remain runnable and testable with no cloud at all.
2. **The same container runs locally.** Point `input_path` at a real file and it works on a
   laptop, which is how a failing production run gets debugged.
3. **Moving clouds later touches one file.**

**`entry.py` must accept local paths as well as `gs://`.** Check the scheme; if it is not
`gs://`, use the path as-is. That is what makes [§8](#8-the-equivalence-discipline) possible
without a storage emulator.

---

## 4. The Platform side

One more implementation of the existing `EngineClient` protocol.

```python
# src/engine/client.py
class CloudRunEngineClient:
    """Runs each job as a Cloud Run Job execution.

    Reads configuration from the environment, not Django settings, so the boundary
    still holds: engine/ may read os.environ, it may not import django.conf.
    """

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        execution = self._start(request)  # jobs.run with env overrides
        while True:
            state = self._poll(execution)  # executions.get
            progress = self._read_progress(request)  # progress.json from the bucket
            if progress and not on_progress(progress.pct, progress.stage):
                self._request_cancel(request)  # cooperative, see §6
            if state.finished:
                break
        return self._read_result(request)  # result.json from the bucket
```

Then `CERNAL_ENGINE=engine.client.CloudRunEngineClient`. **No Platform code changes** —
`tests/test_boundary.py` already forbids `apps/` and `api/` from importing anything but
`engine.contract` and `engine.client`, so this is checkable rather than hoped for.

### The one change to Platform code

`apps/datasets/services.py` writes to a `FileField` on local disk. The engine can no longer
read `dataset.file.path`. Two options:

- **Keep local disk, upload at submit time.** `submit_run` copies the dataset to
  `gs://…/datasets/<id>/` before starting the job. Smallest change; the product keeps
  working with no bucket for local development.
- **Switch `DEFAULT_FILE_STORAGE` to `django-storages[google]`.** Cleaner long-term, but
  local development then needs a bucket or an emulator.

**Recommendation: the first, for now.** Keeping `./do dev` working with nothing but a
directory matters more than elegance while the team is still building. That is task **C5**,
and it is a handful of lines in one service — **the only Platform change in the whole
phase.** That is the boundary paying out.

---

## 5. Identity: no keys anywhere

This is the part that is genuinely nicer than a shared token, and it is worth setting up
properly rather than falling back to a JSON key file.

| Identity | Attached to | Permissions |
|---|---|---|
| `cernal-web@` | The Compute Engine VM | `run.jobs.run` on the engine job · read/write on `gs://cernal-data` |
| `cernal-engine@` | The Cloud Run Job | read/write on `gs://cernal-data` **only** |

Both are **attached identities**: the VM and the job obtain short-lived tokens from the
metadata server automatically. **No key file is ever created**, so none can leak, be
committed, or need rotating.

> **Do not download a service account key.** It is the default answer in most tutorials and
> it is the one thing that turns this design back into a secret you have to manage. If
> something cannot authenticate, the fix is an IAM binding, not a key.

Grant the narrowest role that works — object admin scoped **to the bucket**, not the
project — and give the engine no `run.*` permissions at all. It has no business starting
jobs.

---

## 6. Progress, cancellation, idempotency

The three things a remote engine has to re-earn.

**Progress.** Cloud Run reports execution states, not the stage labels the progress screen
shows. The engine writes after each stage:

```jsonc
// gs://cernal-data/runs/<run-id>/progress.json
{"pct": 60, "stage": "Designing switches", "at": "2026-08-26T10:31:04Z"}
```

The Platform reads it while polling. **Data flows one way** — the engine never calls back
into the Platform, so there is no inbound endpoint and no credential for the engine to hold.

**Cancellation** stays cooperative, exactly as it is today:

1. `cancel_run` writes `gs://cernal-data/runs/<run-id>/cancel`.
2. The entrypoint's `on_progress` checks for that object between stages and returns `False`,
   which raises `JobCancelled` inside the engine — **unchanged code**.
3. `executions.cancel` is the hard stop if it does not respond.

The cooperative model built in Step 3 transfers to the cloud without modification, which is
the return on having built it that way.

**Idempotency.** Cloud Run execution names must be unique within a job, so derive the name
from the key:

```python
execution_name = f"run-{request.idempotency_key[:40]}"
```

A duplicate submission collides, the client detects the existing execution and attaches to
it rather than starting a second one. That is the guarantee `JobRequest.idempotency_key` was
carrying all along, now enforced by the platform itself.

---

## 7. Local development must not need the cloud

Non-negotiable: a new team member should be able to clone, `./do install`, and work.

| `CERNAL_ENGINE` | What runs | Needs the cloud |
|---|---|---|
| `engine.client.MockEngine` | Deterministic fake science | **No** — the default |
| `engine.client.LocalEngine` | Real pipeline, in-process, local paths | **No** |
| `engine.client.CloudRunEngineClient` | Cloud Run Job | Yes — production only |

The container is also runnable locally with local paths, so a failed production run can be
reproduced on a laptop. **Keep `MockEngine` as the default in `dev.py` and in CI**, exactly
as it is now: it is deterministic, needs no scientific dependencies, and it is what makes
the test suite fast enough that people run it.

### A day in the life of writing the science

Nothing about it involves Google Cloud, Django, or containers:

```bash
./do test tests/engine          # < 1 s, no database, no cloud
./do engine-run --input tests/fixtures/de_small.csv --out /tmp/out
```

1. **Pick a stage.** Each has a signature and a docstring describing what it owes its
   successor.
2. **Write it as a pure function** over plain Python and dataclasses. No I/O beyond the
   paths it is handed.
3. **Test it in isolation** with a small fixture — twenty genes, not a real dataset.
4. **Run the whole pipeline locally** once the stage lands (`./do engine-run`). No worker,
   no web server, no cloud.
5. **Check it in the product** when it looks right: `CERNAL_ENGINE=engine.client.LocalEngine`,
   then `./do dev` + `./do worker` and submit through the UI.

**Rules for engine code**, which keep the container, the tests and the boundary all working:

| Rule | Why |
|---|---|
| **No Django. Ever.** | The container has no Django installed; it would not start |
| **Filesystem paths only** | The entrypoint stages files. The pipeline must not know where they came from |
| **All ViennaRNA calls go through `tools/folding.py`** | One place to swap the tool, one place to record its version |
| **Stages are pure over their inputs** | Testable without a pipeline around them |
| **Call `on_progress` between batches** | It is the progress bar *and* the cancellation check |
| **Never mutate a `JobRequest`** | It is frozen, and it is the reproducibility record |
| **Rejections carry reasons** | Rule 8, and the database enforces it on import |
| **Bump `ENGINE_VERSION` when output changes** | See [§9](#9-versioning-and-reproducibility) |

---

## 8. The equivalence discipline

The one thing that stops "works on my laptop" and "works on Cloud Run" from drifting apart.

```python
# tests/contract/test_equivalence.py
@pytest.mark.container
def test_local_and_container_engines_agree(job_request, tmp_path):
    """The same request through both engines must produce the same science.

    A seeded pipeline is deterministic, so this is an equality assertion, not a
    tolerance check. If it ever needs a tolerance, something non-deterministic has
    crept in and that is the actual bug.
    """
    local = LocalEngine().run(job_request, noop_progress)
    containered = run_in_container(job_request)  # docker run, local paths

    assert [c.ref for c in local.candidates] == [c.ref for c in containered.candidates]
    assert [c.overall_score for c in local.accepted] == [
        c.overall_score for c in containered.accepted
    ]
    assert local.engine_version == containered.engine_version
```

Marked so it can be skipped where Docker is unavailable, and **run before every engine
deploy**. Three failures it catches that nothing else does:

- A dependency present on a developer's machine but missing from the image.
- Non-determinism — an unseeded RNG, or dictionary ordering leaking into output.
- A staging bug in the entrypoint that corrupts input or loses artifacts.

---

## 9. Versioning and reproducibility

A researcher will eventually ask *"why did this run give a different answer from last
month's?"*. The pieces to answer that already exist; they need connecting.

| Recorded | Where | By |
|---|---|---|
| `engine_version` | `AnalysisRun.engine_version` | Already written on every run |
| Scientific parameters | `AnalysisRun.params_snapshot` | Already frozen at submission |
| Input checksum | `Dataset.checksum_sha256` | Already verified by the engine |
| Tool versions | a run-level artifact | **Step 5** — `FoldEngine.versions()` |
| Container image | tagged with `ENGINE_VERSION` | **Step 6** |

**Tag the image with the engine version, never `latest`.** Then `engine_version` on a run
identifies the exact image that produced it, and a result from six months ago can be
reproduced by running that tag.

```bash
./do deploy-engine 0.4.0     # builds engine:0.4.0, deploys it, never moves a tag
```

Bump `ENGINE_VERSION` whenever output could change — a new metric, a changed threshold, a
ViennaRNA upgrade. It costs nothing and it is the only thing making old results
interpretable.

---

## 10. Deploying it

Worth turning into a script in `deploy/` rather than a wiki page nobody finds.

```bash
# One-off setup
gcloud services enable run.googleapis.com storage.googleapis.com \
                       artifactregistry.googleapis.com
gcloud storage buckets create gs://cernal-data --location=me-west1
gcloud artifacts repositories create cernal --repository-format=docker --location=me-west1

# Service accounts, no keys
gcloud iam service-accounts create cernal-web
gcloud iam service-accounts create cernal-engine
# + the bindings from §5

# Engine: build and deploy the job
gcloud builds submit --tag me-west1-docker.pkg.dev/$PROJECT/cernal/engine:$VERSION
gcloud run jobs deploy cernal-engine \
    --image me-west1-docker.pkg.dev/$PROJECT/cernal/engine:$VERSION \
    --region me-west1 --cpu 8 --memory 16Gi \
    --task-timeout 3600 --max-retries 0 \
    --service-account cernal-engine@$PROJECT.iam.gserviceaccount.com

# Web: an ordinary VM
gcloud compute instances create cernal-web --machine-type e2-small \
    --service-account cernal-web@$PROJECT.iam.gserviceaccount.com \
    --scopes cloud-platform
```

Pick a region close to your users — `me-west1` (Tel Aviv) is the obvious one — and use the
**same region** for the bucket, the job and the VM, so transfers stay free and fast.

`--max-retries 0` matters: an expensive scientific computation must never be silently
retried, which is the same reasoning as `Q_CLUSTER["max_attempts"] = 1`.

### New `./do` commands

```
engine-run     Run the pipeline locally on a file — no worker, no database, no cloud
engine-build   Build the engine container
engine-test    Run the container against local paths (the equivalence test's engine)
deploy-engine  Build, push and update the Cloud Run Job:  ./do deploy-engine 0.4.0
deploy-web     Deploy the Django app to the VM
```

Deployment can stay **manual**. `./do deploy-engine 0.4.0` from a laptop is honest and
auditable at this team size. Automate it when someone forgets a step, not before.

---

## 11. The VPS runbook

> **Stub — written in Step 6.** Provision → deploy → migrate → restart →
> restore-from-backup, for the always-on VM.

What it will contain:

- `deploy/Caddyfile` — automatic TLS.
- `deploy/cernal-web.service` — gunicorn under systemd.
- `deploy/cernal-worker.service` — `qcluster` under systemd.
- `deploy/backup.sh` — `sqlite3 .backup` plus a `var/media/` archive, on a nightly cron.
- `config/settings/prod.py` — `DEBUG=False`, real `ALLOWED_HOSTS`, `SECURE_*` headers,
  HSTS, file logging with rotation.
- Optionally at this point: `DATABASE_URL` → Postgres. One variable.

**Done when** the app is live over HTTPS, both services restart on boot, a nightly backup
exists, **and a restore has been tested at least once.**

**This is independent of everything else in this document** and can happen first. The
mock-engine version could ship this week and let people use it, then switch `CERNAL_ENGINE`
when the science lands — no downtime, no user-visible change.

---

## 12. Cost

| Item | Shape |
|---|---|
| Compute Engine e2-small | ~$13/month, always on |
| Cloud Run Jobs | Per vCPU-second and GiB-second. A 10-minute 8-vCPU run is cents |
| Cloud Storage | Negligible at this volume |
| Artifact Registry | Negligible |
| Egress | Free within a region — hence keeping everything in one |

**A small fixed monthly cost plus a few cents per analysis.** Check current pricing, and
check Google's research and student credit programmes first — a year of credit changes the
arithmetic entirely.

---

## 13. Gotchas

| Gotcha | Why it bites |
|---|---|
| **Downloading a service account key** | The default tutorial answer, and it recreates the secret this design avoids. Use attached identities |
| **Cloud Run Job CPU/memory ceilings** | There are per-task limits. Check them against a measured run before designing around 16 vCPU |
| **Task timeout** | The default is far below an hour. Set `--task-timeout` deliberately, and keep it above the engine's own budget |
| **Cold start** | Pulling a large image costs seconds. Keep the container lean; ViennaRNA is small, a full conda stack is not |
| **Cross-region transfer** | Costs money and time. One region for bucket, job and VM |
| **`--max-retries`** | Defaults to retrying. An expensive computation must not silently run twice |
| **Bucket lifecycle** | Artifacts accumulate forever. Add a lifecycle rule before it matters, not after |
| **VM scopes** | `--scopes cloud-platform` plus narrow IAM is the modern pattern; legacy narrow scopes cause confusing denials |
| **Nobody watching it** | A second deployment needs someone who will notice when it breaks. Unlike the web VPS, nobody notices the engine is down until somebody submits a run |

---

## 14. What does not change

Worth stating, because it is the return on the boundary work:

- Every model, endpoint and screen from Steps 2–4.
- `MockEngine`, which remains what CI and frontend development use.
- The scoring layer, the `GateFamily` interface, `default-v1`.
- `tests/test_boundary.py`, which is what makes this claim checkable rather than hopeful.
- The six run states, and every product-facing status the researcher sees.

**The user-visible difference should be a slightly longer wait on the first run of the day,
and nothing else.**
