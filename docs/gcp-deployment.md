# CERNAL on Google Cloud

> **Planning document. Nothing here is implemented yet.**
> [`engine-deployment.md`](engine-deployment.md) argues *why* the engine runs elsewhere.
> This is *how*, on Google Cloud specifically.
> [`engine-development.md`](engine-development.md) covers how the engine gets written.

The shape: a small always-on VM runs the product; a container runs the science on demand
and stops. Idle compute cost is zero.

---

## 1. At a glance

```
┌─ Compute Engine · e2-small · always on ────────────────────┐
│   Caddy → gunicorn → Django          (docs/deployment.md)  │
│   django-q2 worker                                         │
│   Persistent disk:  var/cernal.db                          │
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
| Engine | **Cloud Run Jobs** | Run a container to completion, then stop. No compute environment or queue to configure, unlike AWS Batch |
| Transfer | **Cloud Storage** | Datasets in, artifacts and progress out |
| Identity | **Service accounts** | No passwords or keys anywhere. See [§5](#5-identity-no-keys-anywhere) |
| Image | **Artifact Registry** | Where the engine container lives |

**Not Cloud Run *services* for the web app.** Cloud Run has no persistent disk, and SQLite
over a network filesystem is a bad idea. A plain VM keeps the product deployment boring,
which is the whole point of ADR 0002.

---

## 2. The simplification worth noticing

The AWS sketch in [engine-deployment.md §2d](engine-deployment.md) used presigned URLs.
**On Google Cloud you do not need them**, and skipping them removes a whole class of
mistake.

Presigned URLs exist to hand access to something *outside* your trust boundary. Here the
engine is inside it: same project, its own service account. So the Platform passes plain
`gs://` paths, and the job's service account reads and writes them directly.

```python
JobRequest.input_path  = "gs://cernal-data/datasets/<uuid>/expression.csv"
JobRequest.output_dir  = "gs://cernal-data/runs/<run-id>/artifacts"
```

No signing, no expiry to tune, no `signBlob` permission, no clock skew. `input_path` and
`output_dir` are already opaque strings in the contract, so **nothing in
`engine/contract.py` changes**.

---

## 3. Keeping cloud code out of `engine/`

The engine must not learn about Google Cloud. If `engine/pipeline/` starts calling a
storage client, the boundary that makes it testable and portable is gone.

**A thin entrypoint stages files; the engine stays filesystem-based.**

```
src/engine/
├── contract.py          unchanged
├── client.py            unchanged + CloudRunEngineClient
├── pipeline/            unchanged — reads and writes local paths, always
├── gates/  scoring/     unchanged
└── runner/
    └── gcs_entry.py     NEW — the container's entrypoint
```

```python
# src/engine/runner/gcs_entry.py — the only file that knows about Cloud Storage
def main() -> None:
    request = JobRequest(**json.loads(os.environ["CERNAL_JOB_REQUEST"]))

    with tempfile.TemporaryDirectory() as work:
        local_input = download(request.input_path, work)      # gs:// -> /tmp
        local_out = Path(work) / "out"

        result = LocalEngine().run(
            replace(request, input_path=local_input, output_dir=str(local_out)),
            on_progress=publish_progress(request),            # writes progress.json
        )

        upload_tree(local_out, request.output_dir)            # /tmp -> gs://
        write_json(f"{request.output_dir}/../result.json", asdict(result))
```

Three consequences worth having:

1. **`LocalEngine` and the whole pipeline are unchanged** — they still take local paths, so
   they remain runnable and testable with no cloud at all.
2. **The same container runs locally.** Point `input_path` at a real file and it works on
   your laptop, which is how you debug a failing run.
3. **Moving clouds later touches one file.** An `s3_entry.py` would be the same shape.

---

## 4. The Platform side

One more implementation of the existing `EngineClient` protocol.

```python
# src/engine/client.py
class CloudRunEngineClient:
    """Runs each job as a Cloud Run Job execution.

    Reads configuration from the environment, not Django settings, so §3 still holds:
    engine/ may read os.environ, it may not import django.conf.
    """

    def __init__(self) -> None:
        self.project = os.environ["GOOGLE_CLOUD_PROJECT"]
        self.region = os.environ["CERNAL_ENGINE_REGION"]
        self.job = os.environ["CERNAL_ENGINE_JOB"]
        self.bucket = os.environ["CERNAL_BUCKET"]

    def run(self, request: JobRequest, on_progress: ProgressFn) -> JobResult:
        execution = self._start(request)          # jobs.run with env overrides
        while True:
            state = self._poll(execution)          # executions.get
            progress = self._read_progress(request)  # progress.json from GCS
            if progress and not on_progress(progress.pct, progress.stage):
                self._request_cancel(request)      # cooperative, see §6
            if state.finished:
                break
        return self._read_result(request)          # result.json from GCS

    def capabilities(self) -> EngineCapabilities: ...
```

Then `CERNAL_ENGINE=engine.client.CloudRunEngineClient`. **No Platform code changes** —
`tests/test_boundary.py` already forbids `apps/` and `api/` from importing anything but
`engine.contract` and `engine.client`, so this is checkable rather than hoped for.

### Uploading the dataset

`apps/datasets/services.py` currently writes to a `FileField` on local disk. Two options:

- **Keep local disk, upload at submit time.** `submit_run` copies the dataset to
  `gs://…/datasets/<id>/` before starting the job. Smallest change; the product keeps
  working with no bucket for local development.
- **Switch `DEFAULT_FILE_STORAGE` to `django-storages[google]`.** Uploads go straight to
  Cloud Storage. Cleaner long-term, but now local development needs a bucket or an
  emulator.

**Recommendation: the first, for now.** It keeps `./do dev` working with nothing but a
directory, which matters more than elegance while the team is still building.

---

## 5. Identity: no keys anywhere

This is the part that is genuinely nicer than a shared token, and it is worth setting up
properly rather than falling back to a JSON key file.

| Identity | Attached to | Permissions |
|---|---|---|
| `cernal-web@` | The Compute Engine VM | `run.jobs.run` on the engine job · read/write on `gs://cernal-data` |
| `cernal-engine@` | The Cloud Run Job | read/write on `gs://cernal-data` only |

Both are **attached identities**: the VM and the job obtain short-lived tokens from the
metadata server automatically. **No key file is ever created**, so none can leak, be
committed, or need rotating.

> **Do not download a service account key.** It is the default answer in most tutorials
> and it is the one thing that turns this design back into a secret you have to manage.
> If something cannot authenticate, the fix is an IAM binding, not a key.

Grant the narrowest role that works — `roles/storage.objectAdmin` scoped **to the bucket**,
not the project — and give the engine no `run.*` permissions at all. It has no business
starting jobs.

---

## 6. Progress, cancellation, idempotency

The three things a remote engine has to re-earn.

### Progress

Cloud Run reports execution states, not the stage labels the progress screen shows. The
engine writes after each stage:

```jsonc
// gs://cernal-data/runs/<run-id>/progress.json
{"pct": 60, "stage": "Generating gate designs", "at": "2026-08-26T10:31:04Z"}
```

The Platform reads it while polling. **Data flows one way** — the engine never calls back
into the Platform, so there is no inbound endpoint and no credential for the engine to
hold.

### Cancellation

Stays cooperative, exactly as it is today:

1. `cancel_run` writes `gs://cernal-data/runs/<run-id>/cancel`.
2. The entrypoint's `on_progress` checks for that object between stages and returns
   `False`, which raises `JobCancelled` inside the engine — **unchanged code**.
3. `executions.cancel` is the hard stop if it does not respond.

The cooperative model built in Step 3 transfers to the cloud without modification, which
is the return on having built it that way.

### Idempotency

Cloud Run execution names must be unique within a job. Derive the name from
`idempotency_key`:

```python
execution_name = f"run-{request.idempotency_key[:40]}"
```

A duplicate submission collides, the client detects the existing execution and attaches to
it rather than starting a second one. That is the guarantee `JobRequest.idempotency_key`
was carrying all along, now enforced by the platform itself.

---

## 7. Local development must not need Google Cloud

Non-negotiable: a new team member should be able to clone, `./do install`, and work.

| Setting | What runs | Needs GCP |
|---|---|---|
| `engine.client.MockEngine` | Deterministic fake science | **No** — the default |
| `engine.client.LocalEngine` | Real pipeline, in-process, local paths | **No** |
| `engine.client.CloudRunEngineClient` | Cloud Run Job | Yes — production only |

The container is also runnable locally with local paths, so a failing production run can
be reproduced on a laptop. Keep `MockEngine` as the default in `dev.py` and CI, exactly as
it is now.

---

## 8. Deploying it

Roughly, and worth turning into a script in `deploy/` rather than a wiki page nobody
finds:

```bash
# One-off setup
gcloud services enable run.googleapis.com storage.googleapis.com \
                       artifactregistry.googleapis.com
gcloud storage buckets create gs://cernal-data --location=me-west1
gcloud artifacts repositories create cernal --repository-format=docker --location=me-west1

# Service accounts, no keys
gcloud iam service-accounts create cernal-web
gcloud iam service-accounts create cernal-engine
# + bindings from §5

# Engine: build and deploy the job
gcloud builds submit --tag me-west1-docker.pkg.dev/$PROJECT/cernal/engine:$VERSION
gcloud run jobs deploy cernal-engine \
    --image me-west1-docker.pkg.dev/$PROJECT/cernal/engine:$VERSION \
    --region me-west1 --cpu 8 --memory 16Gi \
    --task-timeout 3600 --max-retries 0 \
    --service-account cernal-engine@$PROJECT.iam.gserviceaccount.com

# Web: an ordinary VM, deployed as in docs/deployment.md
gcloud compute instances create cernal-web --machine-type e2-small \
    --service-account cernal-web@$PROJECT.iam.gserviceaccount.com \
    --scopes cloud-platform
```

Pick a region close to your users — `me-west1` (Tel Aviv) is the obvious one — and use the
same region for the bucket, the job and the VM, so transfers stay free and fast.

`--max-retries 0` matters: an expensive scientific computation must never be silently
retried, which is the same reasoning as `Q_CLUSTER["max_attempts"] = 1`.

---

## 9. Cost

| Item | Shape |
|---|---|
| Compute Engine e2-small | ~$13/month, always on |
| Cloud Run Jobs | Per vCPU-second and GiB-second. A 10-minute 8-vCPU run is cents |
| Cloud Storage | Negligible at this volume |
| Artifact Registry | Negligible |
| Egress | Free within a region — hence keeping everything in one |

**A small fixed monthly cost plus a few cents per analysis.** Check current pricing; and
check Google's research and student credit programmes first, because a year of credit
changes the arithmetic entirely.

---

## 10. Build order

Nothing here starts before [step-5](step-5-engine-plan.md) 5a–5f produce a real pipeline
and a measured run. Sizing the Cloud Run Job is guesswork until then.

| # | Phase | Done when |
|---|---|---|
| **G0** | Measure a real run: wall time, peak RAM, cores | You know what `--cpu` and `--memory` to ask for |
| **G1** | Containerise. Dockerfile with ViennaRNA; `gcs_entry.py`; runs against **local paths** | `docker run` on a laptop produces a `JobResult` |
| **G2** | Bucket, service accounts, IAM. No keys | The VM can start a job; the job can reach only its bucket |
| **G3** | `CloudRunEngineClient` + contract tests asserting `LocalEngine` and Cloud Run give **identical results** for the same request | The same run, two engines, same output |
| **G4** | Progress, cancellation, idempotency (§6) | The progress bar moves; cancel stops it; a double submit runs once |
| **G5** | Failure drills — kill the execution mid-run, break IAM, submit twice, corrupt an artifact | Each lands in a terminal state with a readable message |

**G5 is not optional.** Every one of those failures is new, and the only way to know they
are handled is to cause them.

---

## 11. Gotchas

| Gotcha | Why it bites |
|---|---|
| **Downloading a service account key** | The default tutorial answer, and it recreates the secret this design avoids. Use attached identities |
| **Cloud Run Job CPU/memory ceilings** | There are per-task limits. Check them against G0 before designing around 16 vCPU |
| **Task timeout** | Default is far below an hour. Set `--task-timeout` deliberately, and keep it above the engine's own budget |
| **Cold start** | Pulling a large image costs seconds. Keep the container lean; ViennaRNA is small, a full conda stack is not |
| **Cross-region transfer** | Costs money and time. One region for bucket, job and VM |
| **`--max-retries`** | Defaults to retrying. An expensive computation must not silently run twice |
| **Bucket lifecycle** | Artifacts accumulate forever. Add a lifecycle rule before it matters, not after |
| **VM scopes** | `--scopes cloud-platform` plus narrow IAM is the modern pattern; legacy narrow scopes cause confusing denials |
