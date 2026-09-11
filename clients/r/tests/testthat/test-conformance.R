# Submits the shared fixture (clients/fixtures/) against a live MockEngine server and
# checks the exact candidate column set — the mechanism meant to keep three language
# clients honest (docs/public-api.md §11.4).
#
# Inert unless CERNAL_TEST_BASE_URL and CERNAL_TEST_API_KEY are set: a CI job that
# starts a live Django server, pre-seeds the fixture's idempotency_key as an
# already-COMPLETED run (the same trick clients/python/tests/test_conformance.py
# uses — no worker process runs a background queue during this test), and points
# both at it. python -m json.tool clients/fixtures/design_request.json shows the
# exact request.

base_url <- Sys.getenv("CERNAL_TEST_BASE_URL")
api_key <- Sys.getenv("CERNAL_TEST_API_KEY")

test_that("the fixture request returns the expected candidate columns", {
  skip_if(base_url == "" || api_key == "", "CERNAL_TEST_BASE_URL/CERNAL_TEST_API_KEY not set")

  fixtures_dir <- normalizePath(file.path("..", "..", "..", "fixtures"))
  request <- jsonlite::fromJSON(file.path(fixtures_dir, "design_request.json"),
                                 simplifyVector = TRUE)
  expected <- jsonlite::fromJSON(file.path(fixtures_dir, "expected_columns.json"))

  client <- cernal_client(api_key = api_key, base_url = base_url)
  job <- do.call(cernal_design, c(list(client = client, wait = 5), as.list(request)))

  expect_equal(job$response$status, "COMPLETED")
  results <- cernal_results(job)
  expect_gt(nrow(results), 0)
  expect_lte(nrow(results), request$top_n)
  expect_setequal(names(results), expected$candidate_columns)
})

test_that("capabilities needs no key", {
  skip_if(base_url == "", "CERNAL_TEST_BASE_URL not set")

  client <- cernal_client(api_key = "unused", base_url = base_url)
  body <- cernal_capabilities(client)
  expect_true("toehold" %in% body$gate_families$name)
})

test_that("a bad key raises a cernal_auth_error", {
  skip_if(base_url == "", "CERNAL_TEST_BASE_URL not set")

  client <- cernal_client(api_key = "cern_live_definitely-not-real", base_url = base_url)
  expect_error(
    cernal_design(client, trigger_sequence = "AUGGCUAAGCUUAACGGAUCC", organism = "ecoli"),
    class = "cernal_auth_error"
  )
})

test_that("an unknown constraint raises a cernal_validation_error naming the typo", {
  skip_if(base_url == "" || api_key == "", "CERNAL_TEST_BASE_URL/CERNAL_TEST_API_KEY not set")

  client <- cernal_client(api_key = api_key, base_url = base_url)
  err <- tryCatch(
    cernal_design(
      client,
      trigger_sequence = "AUGGCUAAGCUUAACGGAUCC",
      organism = "ecoli",
      constraints = list(max_trigger = 2L)
    ),
    cernal_validation_error = function(e) e
  )
  expect_s3_class(err, "cernal_validation_error")
  expect_equal(err$detail$did_you_mean, "max_triggers")
})
