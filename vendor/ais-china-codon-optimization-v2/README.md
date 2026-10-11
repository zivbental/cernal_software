# Codon Optimization Tool V2

A synonymous codon optimization tool for *Cutibacterium acnes* ATCC 6919 and KPA171202. Enter a coding sequence, choose a host and optimization preferences, and get **one complete DNA sequence per selected preference**, ready to copy or download. Every output preserves the protein sequence and satisfies the selected hard constraints.

**Version 2.0.1** uses the frozen reference package `2026-09-06.v1`. V2 is independent of V1. Both the local application and the Vercel deployment use bundled reference data without querying external databases during optimization. Its interface, documentation and example reports are in English.

**[Open the online tool](https://c-acnes-codon-optimization-version2.vercel.app)** · [GitHub source](https://github.com/LTYyy17/c-acnes-codon-optimization-version2) · [Download releases](https://github.com/LTYyy17/c-acnes-codon-optimization-version2/releases)

## Quick start

Download or clone the repository, then open a terminal in its root directory. Use **Python 3.12**.

On Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv\Scripts\python.exe app.py
```

On macOS/Linux, the equivalent virtual-environment commands are:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
.venv/bin/python app.py
```

Open **http://127.0.0.1:8765** and click **Load example**, then **Optimize sequence**. The example is a real KPA171202 ribosomal protein CDS, optimized for ATCC 6919 with all five preferences selected. See [its provenance](examples/provenance.json).

Windows is the verified platform for this release; macOS/Linux commands describe the standard environment setup and have not yet been validated here. Keep `config/` and `data/hosts/` with the application. RNA calculations require ViennaRNA and energy parameters matching the frozen configuration. An incompatible engine makes RNA unavailable while other valid strategies can still run.

For another port, run `python -m codon_v2 serve --port 8770` using your virtual-environment interpreter. In an IDE, select that interpreter and run [app.py](app.py).

## Online deployment

The Vercel application uses the same Python optimizer, ViennaRNA version and frozen references as the local application. A request returns the complete run and download data directly; no background job or result database is required.

Online runs support **Quick** and **Standard** budgets, up to 40 seconds per preference. A cooperative 240-second limit covers the complete request; completed valid results are retained if that limit is reached. Larger budgets and interactive cancellation are available in the local application. A busy worker returns a retry message.

In online mode, submitted sequences are sent to the deployment server over HTTPS for calculation. The application does not persist sequences or log request bodies. Results and download data remain in the current browser page, so download them before leaving or refreshing. Local mode computes on your computer.

To deploy your own copy, import this repository in Vercel. The committed [configuration](vercel.json), [Python entry point](wsgi.py) and [runtime requirements](requirements.txt) select Python 3.12 and Flask. No application API keys or database are required. Enable Fluid compute and allow a 300-second function duration. The deployment excludes source snapshots and development evidence; the Git repository retains them for reproducibility.

To test the hosting adapter locally:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app wsgi:app run --port 8767
```

Open `http://127.0.0.1:8767`. The regular `app.py` launcher continues to provide the local queued-job interface.

## Use the tool

On opening the tool, **5′ RNA accessibility** is the only optimization preference selected by default. Users can switch to host frequency sampling, CAI priority, tAI priority or codon harmonization, or select multiple preferences to compare independent results.

1. **Select the host and enter one CDS.** Paste DNA/FASTA or import a file.
2. **Choose one or more preferences.** Harmonization requires a source-host reference. For RNA analysis, provide the actual transcribed upstream sequence if available.
3. **Set shared constraints.** Choose motif, global/local GC, repeat and fixed-position rules.
4. **Optimize and take the sequence.** The page moves to the complete output. Use **Copy sequence** or **Download FASTA** without selecting table rows.
5. **Switch or compare when needed.** Preference cards switch the main output. Expand **Metrics & comparison** to inspect metrics, changes and structures or export selected results in bulk.

Each preference produces one sequence or an explicit reason why no valid sequence was found. Selecting three preferences gives at most three sequences. Identical DNA found by different strategies retains every strategy label and is exported once. Multiple selection runs independent searches; it does not create a weighted score or sequentially rewrite one result.

The first selected preference is shown initially. If it has no valid result, the page identifies the fallback. Display order does not rank expected expression. An identical-to-input output is labeled **Unchanged**; a failed search never substitutes the original as a successful result. Starting a new run clears the previous output.

The interface reuses V1's cream-and-sage visual design, animated hero, typography and sequence editor. Use **Optimizer** in the navigation to go directly to the form. Motion can be paused and follows the system's reduced-motion preference. V2 retains its own five optimization preferences and sequence-first results; the presentation change does not change the optimization algorithms.

Inspecting details or selecting comparison rows leaves the main output unchanged. To change the sequence ready to copy, switch preferences or use the explicit **Use this** / **Use this sequence** action.

Keep `public/assets/` alongside `web/` when running locally. Vercel serves these files as static assets. The asset sources and retained licenses are listed in [presentation notices](public/assets/NOTICE.txt).

![Complete output sequence with optional analysis](reports/browser/desktop-results.png)

## Optimization preferences

| Preference | Objective | Method |
|---|---|---|
| 5′ RNA accessibility | Reduce the energy required to keep the entire target region unpaired simultaneously | ViennaRNA partition functions and bounded candidate search; mutable codons 2–30 by default |
| Host frequency sampling | Sample codons from the host's synonymous-family frequencies | Reproducible sampling and constraint filtering |
| CAI priority | Maximize strain-specific ribosomal-reference CAI | Dynamic programming on log weights, with explicitly marked approximation under resource limits |
| tAI priority | Maximize the selected tRNA decoding-model score | Dynamic programming; classic bacterial model by default, exploratory stAI available |
| Codon harmonization | Preserve the original codons' relative usage ranks in their source host | Position-wise rank matching with built-in or custom source counts |

All final candidates are translated again and checked against hard constraints. If the original already satisfies those constraints, non-sampling strategies do not return a worse primary objective. Sampling does not promise to improve any score. The original remains a separate baseline even when it fails the requested constraints.

## Inputs and defaults

| Item | Default behavior |
|---|---|
| CDS | One sequence, up to 9,000 nt; whitespace removed, uppercased, U converted to T |
| Translation | NCBI table 11; valid alternative starts are translated as initial Met |
| Fixed sequence | First codon, existing terminal stop and user-locked codon positions |
| Missing/nonstandard start or stop | Explicit status; a missing stop is not added; RNA start optimization requires a recognized start |
| Upstream | Optional actual transcribed sequence, up to 300 nt; fixed |
| Motif | ATCC: none / AGCAGY / custom literal ACGT motif of 2–32 nt; KPA: server-enforced AGCAGY |
| Global GC | Host-derived P5–P95 hard interval; terminal stop excluded |
| Local GC | 60 nt window, 3 nt step, report only; optional hard bounds |
| RNA | 37°C; upstream + first 150 CDS nt; opening target CDS nt 1–15 |
| Repeats | Warn by default; optional bounded repair or strict exclusion |
| Repeat thresholds | Homopolymer ≥8 nt; tandem unit 2–6 nt, ≥3 copies and ≥12 nt total; direct repeat ≥20 nt |
| Coordinates | Reports use 1-based inclusive coordinates |
| Output count | Fixed at one per selected preference |

Windows, thresholds and budgets are engineering settings. Full definitions, reference conventions and solver guarantees are in the documentation below. Missing metrics are reported with reasons, not substituted with zero or another strain's values.

## Documentation

| Document | Purpose |
|---|---|
| [README](README.md) | Installation, workflow and project overview |
| [Algorithm implementation](docs/ALGORITHM_DESIGN.md) | Formulas, scoring masks, constraints, search, selection and limitations |
| [Reference data and field dictionary](docs/DATA_DICTIONARY.md) | Sources, model assumptions, table fields and parameter provenance |
| [API and configuration](docs/API.md) | Python/HTTP interfaces, request fields and report schema |
| [Validation](docs/VALIDATION.md) | Numerical checks, browser evidence and how to reproduce checks |
| [Expert trial guide](docs/EXPERT_TRIAL.md) | A short trial and suggested usability/method feedback |

The repository contains the current implementation documents. Reference tables, source snapshots, manifests and machine-readable validation evidence remain available for reproducibility.

## Reference data

| Item | ATCC 6919 | KPA171202 |
|---|---:|---:|
| Assembly | GCF_008728435.1 | GCF_000008345.1 |
| QC-passing CDS records | 2,312 | 2,345 |
| Ribosomal CAI reference genes | 61 | 61 |
| tRNA loci | 45 | 45 |
| Positive tAI weights | 61 / 61 | 61 / 61 |
| Coding GC P5–P95 | 54.49%–64.99% | 54.69%–64.99% |

Download the [ATCC master table](data/hosts/atcc6919_GCF_008728435.1/2026-09-06.v1/codon_parameters.csv) or [KPA master table](data/hosts/kpa171202_GCF_000008345.1/2026-09-06.v1/codon_parameters.csv). Loading checks reference hashes, codon coverage, ranges and normalization. Model choices and fitting diagnostics are documented in the [data reference](docs/DATA_DICTIONARY.md).

## Command line and exports

Run a saved request using the virtual-environment interpreter:

```powershell
.\.venv\Scripts\python.exe -m codon_v2 run --request examples\request.json --output results\example
```

The directory receives `results.fasta`, `results.csv` and `results.json`. FASTA contains unique candidates; CSV also includes the original. JSON retains input, normalized settings, strategy memberships, changes, model/reference/code hashes, seeds, budgets and stopping reasons. Partial exports identify their selected subset while preserving full-run strategy status.

A seed makes sampling reproducible under the same reference, software and effective evaluation budget. Wall-clock stopping can vary with hardware load. A budget-limited result can still contain valid outputs; it does not establish global optimality. See [the API](docs/API.md) for rerunning an exported configuration and adjusting budgets.

## Development and reproducibility

Install [requirements-lock.txt](requirements-lock.txt) for the complete parameter-building and numerical-test environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts\run_all.py --offline
```

The last command rebuilds references from `data/raw/` without network access. Browser tests additionally require Node.js and Playwright; complete commands and evidence are in [Validation](docs/VALIDATION.md).

To prepare a source archive, run `python dev/package_release.py --output codon-optimization-v2-2.0.1.zip` with the virtual-environment interpreter. The archive includes code, frozen data, build scripts, these six documents and validation evidence, excluding virtual environments, IDE settings, caches and user results.

```text
app.py                       Local application entry point
wsgi.py                      Stateless online application entry point
vercel.json                  Vercel hosting configuration
requirements.txt             Online runtime dependencies
codon_v2/                    Validation, metrics, search, reporting and local server
web/                         English web interface; no frontend build step
config/                      Frozen models and defaults
data/hosts/                  Separate strain reference packages
data/raw/                    Frozen sources for offline rebuilds
scripts/                     Parameter-building pipeline
examples/                    Real example and custom source-reference format
tests/                       Parameter, optimizer and API checks
dev/                         Browser checks, example and release utilities
docs/                        Current algorithm, data, API, validation and trial documentation
reports/                     Machine-readable evidence and screenshots
```

## Scope

CAI, tAI and RNA scores describe computational models, not measured protein expression or expression fold changes. tRNA copy number is a supply proxy; the ribosomal CAI set is a high-expression proxy; RNA without actual upstream sequence is explicitly CDS-only. Expert trial feedback concerns usability and method assumptions, not experimental endorsement.

The local server binds to `127.0.0.1`, uses one computation worker and permits four queued/running jobs. It retains up to 16 in-memory jobs, clearing completed jobs older than two hours on new submissions. Restarting clears results, so download reports to keep them.

This release does not implement expression prediction, weighted joint objectives, ChimeraMap, multicodon block optimization or approximate/inverted repeats. Public hosting uses the separate stateless adapter in `codon_v2/online.py`; the local queued server remains bound to your computer.
