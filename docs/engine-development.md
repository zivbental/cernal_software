# Engine development regime

> **Planning document. Nothing here is implemented yet.**
> [`gcp-deployment.md`](gcp-deployment.md) covers where the engine runs.
> This covers **how it gets written**: which repository, which dependencies, what a day
> of scientific development looks like, and what changes in this repo.

---

## 1. One repo or two?

The design maps specify two repositories, `cernal-platform` and `cernal-engine`
(map 19). [ADR 0001](decisions/0001-single-repo-in-process-engine.md) deferred that. Now
that the engine deploys as a separate container, does the deferral end?

**No. Stay in one repository, and build two deployable artifacts from it.**

**Deployment separation is not repository separation.** The engine is *already* a separate
Python package with an enforced boundary; the container simply builds a subset of the
repo. Splitting the repo would buy independent release cadence and cost you the four
things that currently keep this architecture honest:

| What a split would break | Why it matters |
|---|---|
| `tests/test_boundary.py` | It can only check imports it can see. Across repos the boundary becomes a convention again |
| The shared contract | `engine/contract.py` would have to become a versioned, published package that both repos depend on — with its own release process |
| Contract equivalence tests ([§5](#5-the-central-discipline-equivalence-tests)) | Running the same job through `LocalEngine` *and* the container and comparing needs both in one place |
| Atomic contract changes | Adding a field currently touches one PR. Across repos it is a three-PR dance with a version bump in the middle |

For a rotating student team, those costs land immediately and the benefit does not.

### When to actually split

Not on a date — on a symptom:

- The scientific team is large enough to want its own review queue and release schedule.
- The contract has stopped changing, so publishing it as a package is cheap.
- Someone outside the team needs the engine without the product.

The seam is built. Splitting later means moving `src/engine/` into a new repo and
publishing `contract.py` — a day's work, not a redesign. **Do it when it hurts not to.**

---

## 2. What the repo looks like

Additions marked ★. Everything else is untouched.

```
cernal/
├── pyproject.toml              ★ dependencies split into groups (§3)
├── do                          ★ engine-build · engine-run · deploy-engine
├── deploy/
│   ├── Dockerfile.engine       ★ the container — and a proof of §3 (§3)
│   ├── deploy-engine.sh        ★ build, push, update the Cloud Run Job
│   └── deploy-web.sh           ★ the VM, as in deployment.md
├── src/
│   ├── config/  apps/  api/    unchanged — Platform only
│   └── engine/
│       ├── contract.py         unchanged
│       ├── client.py           ★ + CloudRunEngineClient
│       ├── pipeline/           ★ the science (Step 5) — filesystem-based, no cloud
│       ├── gates/  scoring/    ★ toehold implementation
│       ├── tools/              ★ rna.py — the only ViennaRNA caller
│       └── runner/
│           └── gcs_entry.py    ★ container entrypoint: stage down, run, stage up
└── tests/
    ├── engine/                 ★ scientific tests — fast, no cloud, no Django
    └── contract/               ★ equivalence: LocalEngine vs container (§5)
```

**Two artifacts, one source:**

| Artifact | Built from | Runs on | Contains |
|---|---|---|---|
| Web + worker | the whole repo | Compute Engine VM | Django, apps, api, engine *client* |
| Engine container | `src/engine/` **only** | Cloud Run Job | pipeline, gates, scoring, ViennaRNA |

---

## 3. Dependencies, and the Dockerfile as a proof

Today `engine/` imports **only the standard library** — no third-party packages at all.
Step 5 changes that, and this is the moment to stop the two halves' dependencies from
mixing.

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

```dockerfile
# deploy/Dockerfile.engine
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --extra engine --no-dev --frozen

# Only the engine. Not apps/, not config/, not api/.
COPY src/engine/ ./engine/

ENTRYPOINT ["uv", "run", "python", "-m", "engine.runner.gcs_entry"]
```

> **This Dockerfile is an executable proof of [§3](software-design.md).** Django is not
> installed and the Platform source is not copied, so if `engine/` ever grows a Django
> import, the container fails to start. `tests/test_boundary.py` says the boundary holds;
> the container makes it impossible to violate.

---

## 4. Writing the science: a day in the life

The regime that matters most, because this is what the scientific team does daily.

**Nothing about their work involves Google Cloud, Django, or containers.**

```bash
./do test tests/engine          # < 1 s, no database, no cloud
./do test tests/engine -k toehold
```

### The loop

1. **Pick a stage** from `engine/pipeline/stages.py`. Each has a signature and a docstring
   describing what it owes its successor.
2. **Write it as a pure function** over plain Python and dataclasses. No I/O beyond the
   paths it is handed.
3. **Test it in isolation** with a small fixture — twenty genes, not a real dataset.
4. **Run the whole pipeline locally** once the stage lands:
   ```bash
   ./do engine-run --input tests/fixtures/de_small.csv --out /tmp/out
   ```
   That calls `LocalEngine` directly. No worker, no web server, no cloud.
5. **Check it in the product** when it looks right: set
   `CERNAL_ENGINE=engine.client.LocalEngine`, then `./do dev` + `./do worker` and submit
   through the UI.

### Rules for engine code

These keep the container, the tests and the boundary all working:

| Rule | Why |
|---|---|
| **No Django. Ever.** | The container has no Django installed; it would not start |
| **Filesystem paths only** | `gcs_entry.py` stages files. The pipeline must not know where they came from |
| **All ViennaRNA calls go through `engine/tools/rna.py`** | One place to swap the tool, one place to record its version |
| **Stages are pure functions** | Testable without a pipeline around them |
| **Call `on_progress` between stages** | It is the progress bar *and* the cancellation check |
| **Never mutate a `JobRequest`** | It is frozen, and it is the reproducibility record |
| **Rejections carry reasons** | Rule 8, and the database enforces it on import |
| **Bump `ENGINE_VERSION` when output changes** | See [§6](#6-versioning-and-reproducibility) |

---

## 5. The central discipline: equivalence tests

The one thing that stops "works on my laptop" and "works on Cloud Run" from drifting
apart.

```python
# tests/contract/test_equivalence.py
@pytest.mark.container
def test_local_and_container_engines_agree(job_request, tmp_path):
    """The same request through both engines must produce the same science.

    MockEngine is deterministic and so is a seeded pipeline, so this is an equality
    assertion, not a tolerance check. If it ever needs a tolerance, something
    non-deterministic has crept in and that is the actual bug.
    """
    local = LocalEngine().run(job_request, noop_progress)
    containered = run_in_container(job_request)     # docker run, local paths

    assert [c.ref for c in local.candidates] == [c.ref for c in containered.candidates]
    assert [c.overall_score for c in local.accepted] == [
        c.overall_score for c in containered.accepted
    ]
    assert local.engine_version == containered.engine_version
```

Marked so it can be skipped where Docker is unavailable, and run before every engine
deploy. Three failures it catches that nothing else does:

- A dependency present on a developer's machine but missing from the image.
- Non-determinism — an unseeded RNG, or dictionary ordering leaking into output.
- A staging bug in `gcs_entry.py` that corrupts input or loses artifacts.

**`gcs_entry.py` must accept local paths as well as `gs://`.** Check the scheme; if it is
not `gs://`, use the path as-is. That is what makes this test possible without a storage
emulator, and it is also how a failed production run gets reproduced on a laptop.

---

## 6. Versioning and reproducibility

A researcher will eventually ask *"why did this run give a different answer from last
month's?"*. The pieces to answer that already exist; they need connecting.

| Recorded | Where | By |
|---|---|---|
| `engine_version` | `AnalysisRun.engine_version` | Already written on every run |
| Scientific parameters | `AnalysisRun.params_snapshot` | Already frozen at submission |
| Input checksum | `Dataset.checksum_sha256` | Already verified by the engine |
| Tool versions | `JobResult.warnings` or a new artifact | **Step 5** — `rna.py` should record ViennaRNA's version |
| Container image | tagged with `ENGINE_VERSION` | **Step 5** |

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

## 7. Changes to this repository, itemised

| # | Change | Where | Size |
|---|---|---|---|
| 1 | Split dependencies into `platform` / `engine` groups | `pyproject.toml` | S |
| 2 | `./do install` installs `--extra platform --extra dev` | `do` | S |
| 3 | `engine/tools/rna.py` — ViennaRNA wrapper, records version | new | M |
| 4 | Implement the thirteen stages and `ToeholdGate` | `engine/pipeline/`, `engine/gates/` | **L** |
| 5 | `engine/runner/gcs_entry.py` — staging entrypoint, `gs://` **and** local paths | new | M |
| 6 | `CloudRunEngineClient` | `engine/client.py` | M |
| 7 | Upload dataset to the bucket at submit time | `apps/analyses/services.py` | S |
| 8 | `deploy/Dockerfile.engine` | new | S |
| 9 | `deploy/deploy-engine.sh`, `deploy-web.sh` | new | M |
| 10 | `./do engine-run`, `engine-build`, `deploy-engine` | `do` | S |
| 11 | Equivalence tests | `tests/contract/` | M |
| 12 | GCP settings and `.env.example` entries | `config/settings/prod.py` | S |
| 13 | CI: lint + test on push, build image on tag | `.github/workflows/` | M |

**Item 7 is the only change to Platform code**, and it is a handful of lines in one
service. Everything else is either new files or inside `engine/`. That is the boundary
paying out.

**Item 1 is independent of everything else** and can be done today — it costs nothing and
makes the eventual container trivial.

---

## 8. New `./do` commands

```
engine-run        Run the pipeline locally on a file, no worker or cloud
                    ./do engine-run --input tests/fixtures/de_small.csv --out /tmp/out
engine-build      Build the engine container
engine-test       Run the container against local paths (the equivalence test's engine)
deploy-engine     Build, push and update the Cloud Run Job:  ./do deploy-engine 0.4.0
deploy-web        Deploy the Django app to the VM
```

`engine-run` is the one that matters day to day: it is the scientific team's inner loop,
and it must never require Docker, a database, or a network.

---

## 9. Continuous integration

There is none today, and once two artifacts ship from one repo it starts to earn its keep.

```yaml
# .github/workflows/ci.yml — sketch
on: [push, pull_request]
jobs:
  test:      # ./do lint && ./do test   — MockEngine, no cloud, no secrets
  container: # docker build, then the equivalence tests   (main only)
```

Keep `MockEngine` as CI's engine. It is deterministic, needs no scientific dependencies,
and it is what makes the test suite fast enough that people run it.

Deployment can stay manual — `./do deploy-engine 0.4.0` from a laptop is honest and
auditable at this team size. Automate it when someone forgets a step, not before.

---

## 10. Order of work

| # | Phase | Depends on |
|---|---|---|
| **E0** | Split dependency groups (item 1–2) | nothing — **do it now** |
| **E1** | `tools/rna.py` + the science ([step-5](step-5-engine-plan.md) 5a–5f) | E0 |
| **E2** | Measure a real run | E1 |
| **E3** | `gcs_entry.py` + Dockerfile, **local paths only** | E1 |
| **E4** | Equivalence tests | E3 |
| **E5** | GCP resources: bucket, service accounts, job ([gcp §8](gcp-deployment.md)) | E2 sizes the job |
| **E6** | `CloudRunEngineClient` + dataset upload | E5 |
| **E7** | Failure drills ([gcp §10](gcp-deployment.md) G5) | E6 |

**E1 is the long pole and the only one that needs scientific input.** E0, E3 and E4 are
software work that can proceed alongside it, and E4 is what makes E5 onwards safe.

The eight questions in [step-5 §10](step-5-engine-plan.md) still gate E1 — particularly
where trigger sequences come from, which no amount of infrastructure planning answers.
