test_that("raw JSON and flattened metrics have distinct contracts", {
  candidate <- list(id = "one", engine_ref = "cand-1", rank = 2L, overall_score = .7,
                    gate_family = "toehold", logic_type = "SINGLE", is_rejected = FALSE,
                    rejection_reason = "", output = "GFP", design = list(sequence = "ACGU"),
                    triggers = list(), warnings = list("held"), metrics = list(list(name = "gc_content", raw_value = NULL)))
  second <- candidate; second$id <- "two"; second$rank <- 1L; second$metrics <- list()
  rejected <- candidate; rejected$is_rejected <- TRUE; rejected$rank <- NULL
  job <- list(response = list(job_id = "run", status = "COMPLETED", candidates = list(rejected, candidate, second)))
  expect_identical(cernal_candidates(job)[[2]]$design, candidate$design)
  results <- cernal_results(job)
  expect_equal(nrow(results), 3L)
  expect_true(all(is.na(results$gc_content)))
  expect_identical(cernal_best(job)$id, "two")
  job$response$candidates <- list(rejected)
  expect_null(cernal_best(job))
  job$response$candidates <- list()
  expect_null(cernal_best(job))
})


test_that("dry run and failed inline candidates are not completion", {
  expect_error(cernal_wait(list(response = list(job_id = NULL, candidates = list()))), "never submitted")
  expect_error(cernal_wait(list(response = list(job_id = "run", status = "FAILED", candidates = list()))), "ended FAILED")
})
