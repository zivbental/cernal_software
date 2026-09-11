# cernal (R client)

```r
remotes::install_github("zivbental/cernal_software", subdir = "clients/r")
```

```r
library(cernal)

cl  <- cernal_client(Sys.getenv("CERNAL_API_KEY"), base_url = "https://your-cernal-host")
job <- cernal_design(cl, trigger_sequence = "AUGGCUAAGCUUAACGGAUCC", organism = "ecoli")
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
  constraints   = list(max_triggers = 2L, min_separation = 1.0, max_p_adj = 0.01),
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

**Not independently verified against a live server** — built directly from
docs/public-api.md §11.2's spec and this repo's actual API responses, but no R
interpreter was available to run it. `tests/testthat/test-conformance.R` is written
and ready; it needs `CERNAL_TEST_BASE_URL`/`CERNAL_TEST_API_KEY` pointed at a running
MockEngine deployment (see `.gitlab-ci.yml`'s `client-r` job) and a human with R to
confirm it passes before this ships.
