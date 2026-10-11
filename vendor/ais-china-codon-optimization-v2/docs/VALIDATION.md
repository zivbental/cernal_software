# Computational and Interface Validation

Release: **2.0.1**. Evidence recorded on **September 6–7, 2026**. The machine-readable files below identify the runs used in this report.

## Observed checks

- **67 Python checks passed**, with zero failures and errors, in 8.01 seconds. This includes the original 18 parameter checks, optimizer/local API checks and stateless online API checks.
- Real browser end-to-end checks passed in browser version `153.0.4234.32`, with no page-script or console errors.
- Layout checks covered 900 px light mode and 736/360 px light and dark modes, with no page-level horizontal overflow.
- English checks covered HTML language, app-owned form validation, interface/detail text, accessibility labels and the built-in example report. The final browser run used locale `zh-CN`.

Machine-readable evidence: [pytest XML](../reports/pytest-v2-results.xml), [browser JSON](../reports/browser/browser-check.json), [complete real example](../reports/example_run.json).

## Coverage

Numerical/API coverage includes scoring masks, missing stops, table 11 alternative starts, invalid FASTA, unknown configuration fields, CAI/tAI weights and source hashes, global tAI normalization, two-strand overlapping motifs and terminal-stop junctions, final GC windows, exact-repeat scanning/repair, locked positions and hard filtering.

CAI/tAI/harmonization DP is compared against independent exhaustive search in small synonymous spaces. Approximate/interrupted searches are not labeled exact. RNA checks cover constraint coordinates, simultaneous whole-target opening and joint probability. Other checks cover independent samples for single/multiple selections, memberships for identical DNA, missing modules, isolated strategy errors, cancellation, HTTP validation, polling and real exports.

The browser submits an actual five-strategy job and checks exactly one output per successful preference, with no output-count setting or numbered alternatives. Complete DNA appears first with automatic scrolling and collapsed analysis. Clipboard contents match the computed sequence exactly, and single FASTA download needs no row selection. Every preference's sequence and label are verified. Inspecting the original or another result leaves the output unchanged until an explicit use-result action.

The browser also checks retained output/comparison selections after collapsing analysis, cross-strategy comparison, details, structures and batch FASTA containing the selected unique sequences. A real run places a forbidden motif in the fixed start, confirming that no valid result clears old DNA and cannot copy/download the original as a successful output. A real nonstandard-start input makes RNA unavailable and verifies the explicit CAI fallback. A separately labeled protocol fixture checks that terminal job failure stops polling after one read; it is not numerical evidence.

The one-output contract is checked in Python/API tests: omitted count defaults to one and explicit larger counts are rejected. The recorded evidence comes from the complete Python suite and real browser workflow.

The reference build also passed 18 parameter checks and a complete offline rebuild. Six core tables had matching SHA-256 hashes before and after rebuilding: the master table, per-gene metrics and RNA background for each strain. See [parameter checks](../reports/pytest-results.xml) and [the reproducibility record](../reports/reproducibility_check.json). Audit timestamps and runtimes are not required to be byte-identical.

## Local example

Input: KPA171202 PPA_RS04215, 50S ribosomal protein L21, 309 nt. Target: ATCC 6919. No transcribed upstream sequence was supplied, so RNA is CDS-only. The web example uses its quick budget and returns at most one result per preference.

| Strategy | Status | Solver | Returned memberships |
|---|---|---|---:|
| `rna_start` | budget_exhausted | rna_pool_search | 1 |
| `host_sampling` | completed | host_frequency_rejection_sampling | 1 |
| `cai_max` | completed | dp_exact | 1 |
| `tai_max` | completed | dp_exact | 1 |
| `harmonize` | completed | dp_exact | 1 |

After deduplication, the run contains **5 distinct sequences** and took **2.28 seconds** in the backend. This is one observed input on this computer, not a performance guarantee. RNA can reach its evaluation budget and still return a completed valid representative. Missing valid outputs have explicit reasons.

Screenshots: [input](../reports/browser/desktop-input.png), [main sequence output](../reports/browser/desktop-results.png), [expanded analysis](../reports/browser/desktop-analysis.png), [mobile with system dark preference](../reports/browser/results-dark-360.png).

## Reproduce the checks

Use Python 3.12 from the project root. The following Windows commands use the virtual environment described in the [README](../README.md); on macOS/Linux its interpreter path is `.venv/bin/python`.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pytest tests -q --junitxml=reports/pytest-v2-results.xml
```

For an offline parameter rebuild, run `python scripts/run_all.py --offline` with the same interpreter and keep `data/raw/`.

Start a browser-test server in one terminal:

```powershell
.\.venv\Scripts\python.exe -m codon_v2 serve --port 8766
```

In another terminal, install and run Playwright:

```powershell
cd dev
npm install
npx playwright install chromium
npm test
```

The browser check tries Playwright Chromium and falls back to installed Microsoft Edge. `CODON_TEST_URL` overrides the test address; `CODON_PLAYWRIGHT_MODULE` points to an existing module. The default browser locale is `zh-CN` to check English behavior in a Chinese browser; `CODON_TEST_LOCALE` overrides it.

The script writes screenshots and browser evidence to `reports/browser/`, and its real five-strategy report to `reports/example_run.json`. After successful checks, run `python dev/finalize_docs.py` from the root to regenerate this document and check the six public documents' links. The generator reads existing evidence; it does not run tests. `dev/prepare_example.py` separately extracts the example from the frozen KPA reference without network access.

## Scope

The numerical environment is Windows / Python 3.12.14 / ViennaRNA 2.7.2. Local macOS/Linux installation and expression experiments have not been validated. Hosting verification is recorded separately below when deployment evidence is available. Parameter fitting and expert trial feedback are not expression evidence.

These checks address calculation definitions, constraints, provenance and interface behavior. Hardware load can affect candidates when time limits trigger. Harmonization implements the declared position-wise rank method; repeat checks cover only the documented exact-repeat types.

## V1 presentation adaptation — 2026-09-19

The interface now reuses the V1 hero video, poster, background artwork, Manrope font, cream/sage palette, split sequence editor and host/motif radio lists. V2's independent preferences, request fields, numerical algorithms and sequence-first output contract are retained. The same palette is used with either system color preference.

The real local and WSGI browser workflows passed with the new interface, including all five preferences, exact clipboard DNA, FASTA/CSV/JSON export, forced KPA motif behavior, example loading, comparison and explicit output switching, unavailable/no-result handling and mobile layouts. This is local verification of the hosting adapter, not publication of the new design to the live site.

Ten HTTP/hosting tests passed, including the existing optimization and transport tests plus public-media byte ranges and rejection of private/traversal paths. Additional presentation checks covered decoded video, pause/play, reduced motion, navigation, a usable form with unavailable video, and header/form bounds at 320, 360, 736, 900 and 1440 px. See [presentation evidence](../reports/browser/presentation-check.json), [adapter browser evidence](../reports/browser/online-browser-check.json), and [HTTP test results](../reports/presentation-api-tests.xml).

Run `npm run test:presentation` in `dev/` against the local test server, using the same optional environment variables as the main browser check. Screenshots include the [hero](../reports/browser/desktop-hero.png), [workspace](../reports/browser/desktop-workspace.png) and [mobile input](../reports/browser/mobile-workspace.png). Source and font licenses are retained in [public/assets](../public/assets/NOTICE.txt). The release packager includes this directory.

## Online hosting verification

The live deployment at https://c-acnes-codon-optimization-version2.vercel.app was checked on 2026-09-06T16:27:09.175143+00:00. The deployed runtime reports Python 3.12.13 and ViennaRNA 2.7.2. An anonymous request loaded both host references and ran all five preferences using the real example. All final outputs passed their protein and hard-constraint checks. Server-generated FASTA and CSV exports matched the report.

The browser workflow also passed against the stateless adapter: exact clipboard DNA, one-sequence FASTA, all five output labels, selected CSV without repeated headers/baselines, full JSON, responsive layouts, a no-result rerun and visible handling of an incomplete server response. See [online evidence](../reports/online-validation.json).
