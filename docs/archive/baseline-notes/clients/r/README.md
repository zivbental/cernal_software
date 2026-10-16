# cernal (R client)

```r
remotes::install_github("zivbental/cernal_software", subdir = "clients/r")
```

```r
library(cernal)

cl  <- cernal_client(Sys.getenv("CERNAL_API_KEY"), base_url = "https://your-cernal-host")
job <- cernal_design(cl, trigger_sequence = "AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA", organism = "ecoli")
df  <- cernal_results(cernal_wait(job))
head(df)
```

Constrained, and the compelling demo — DESeq2 output straight to plasmid design:

```r
deseq_table <- as.data.frame(DESeq2::results(dds))

job <- cernal_design(
  cl,
  dge_csv       = readr::read_file("deseq2.csv"),
  organism      = "ecoli",
  gate_families = "toehold",
  constraints   = list(max_triggers = 1L, min_separation = 1.0, max_p_adj = 0.01),
  scoring       = list(weights = list(predicted_leakage = 4.0)),
  seed          = 42L
)
df <- cernal_results(cernal_wait(job))
```

`httr2` + `tibble`, no Bioconductor dependency. `cernal_results()` returns one row per
candidate, metric decomposition as columns, so it drops straight into `dplyr` and
`ggplot2`. Errors carry an S3 class per docs/public-api.md §10's codes —
`cernal_auth_error`, `cernal_validation_error` (with `$detail$did_you_mean`),
`cernal_rate_limited` (with `$retry_after`), `cernal_run_failed` (with
`$error_summary`) — so `tryCatch(..., cernal_validation_error = function(e) ...)` works.

The raw/table and live HTTP conformance suite passed in hosted Ubuntu R CI on
8 October 2026. The live suite uses a real LocalEngine-computed, precompleted
fixture; it does not exercise R polling through a live worker queue.

## Verification and result contracts (8 October 2026)

No package publication is claimed. Install from this repository's source; public
registry releases require separate maintainer authorization. Python HTTP conformance
and transport/ranking regressions execute against a local API. The R raw/table and
live HTTP conformance suite passed in [hosted Ubuntu CI](https://github.com/zivbental/cernal_software/actions/runs/37802426550/job/113397823314).
MATLAB runtime conformance remains unexecuted; its source changes are experimental.

Submission result options (`top_n`, `include_rejected`, `include_metrics`,
`include_artifacts`) remain on the job handle across queued completion. Persist them
when reconstructing a resumed handle; explicit results calls can override them.
Server-side `wait` is bounded to 0–300 seconds and submission transport timeout is
at least `wait + 10` seconds. Best-candidate helpers choose the lowest accepted rank
and return no result when all candidates are rejected or unranked.

Raw candidate JSON retains nested design, triggers, warnings and metrics. Flattened
tables are a separate convenience contract and are not compared to raw JSON column
sets. R exposes `cernal_candidates(job)` and MATLAB `job.rawCandidates()`.
