# Submitting and polling (docs/public-api.md §8-§9).

#' Submit a design request
#'
#' Every named argument in `...` is a docs/public-api.md §9 field passed straight
#' through as the JSON body: `trigger_sequence` / `dataset_id` / `dge_csv` / `gene_id` (exactly
#' one), `organism`, `gate_families`, `exclude_gate_families`,
#' `constraints` (a `list`), `scoring` (a `list`), `budget` (a `list`), `payload`,
#' `seed`, `top_n`, `include_rejected`, `include_artifacts`, `idempotency_key`,
#' `strict`, `notes`. This client does not duplicate the server's validation.
#'
#' @param client A `cernal_client`, from [cernal_client()].
#' @param ... Design fields, e.g. `trigger_sequence = "..."`,
#'   `constraints = list(max_triggers = 2L, min_separation = 1.0)`.
#' @param wait Seconds to block server-side for a finished result (ceiling 300).
#' @param dry_run Estimate without submitting.
#' @return A `cernal_job`.
#' @export
cernal_design <- function(client, ..., wait = NULL, dry_run = FALSE) {
  fields <- list(...)
  query <- list()
  if (isTRUE(dry_run)) query$dry_run <- "true"
  if (!is.null(wait)) query$wait <- wait

  if (!is.null(wait) && (length(wait) != 1 || !is.numeric(wait) || !is.finite(wait) || wait < 0 || wait > 300)) {
    stop("wait must be finite and between 0 and 300 seconds.", call. = FALSE)
  }
  for (name in intersect(names(fields), c("gate_families", "exclude_gate_families", "include_artifacts"))) {
    fields[[name]] <- as.list(fields[[name]])
  }
  options <- fields[intersect(names(fields), c("top_n", "include_rejected", "include_metrics", "include_artifacts"))]
  if (!is.null(options$include_artifacts)) options$include_artifacts <- paste(unlist(options$include_artifacts), collapse = ",")
  resp <- .cernal_request(client, "POST", "/api/design", body = fields, query = query,
                         timeout = if (is.null(wait)) client$timeout else max(client$timeout, wait + 10))
  body <- httr2::resp_body_json(resp, simplifyVector = FALSE)
  structure(list(client = client, response = body, result_options = options), class = "cernal_job")
}

#' Poll a job until it reaches a terminal state
#'
#' Polls with backoff (2s, growing to `max_poll`, up to `timeout` overall). Already
#' resolved if the server answered inline — a `wait=` that finished before its
#' deadline, or an idempotent resubmission of an already-completed run — in which case
#' this returns immediately.
#'
#' @param job A `cernal_job`, from [cernal_design()].
#' @param timeout Overall seconds to wait before raising.
#' @return `job`, with results attached.
#' @export
cernal_wait <- function(job, timeout = 300, poll = 2, max_poll = 15) {
  if (!is.null(job$response$candidates)) {
    return(job)
  }
  job_id <- job$response$job_id
  if (is.null(job_id)) {
    stop("This job was never submitted (dry_run=TRUE has no id to wait on).", call. = FALSE)
  }

  deadline <- Sys.time() + timeout
  delay <- poll
  status <- job$response$status
  while (!(status %in% c("COMPLETED", "FAILED", "CANCELLED"))) {
    remaining <- as.numeric(difftime(deadline, Sys.time(), units = "secs"))
    if (remaining <= 0) {
      stop(sprintf("Job %s did not finish within %ds.", job_id, timeout), call. = FALSE)
    }
    Sys.sleep(min(delay, remaining))
    resp <- .cernal_request(job$client, "GET", paste0("/api/design/", job_id))
    job$response <- httr2::resp_body_json(resp, simplifyVector = FALSE)
    status <- job$response$status
    delay <- min(delay * 1.5, max_poll)
  }

  if (status != "COMPLETED") {
    stop(structure(
      class = c("cernal_run_failed", "cernal_error", "error", "condition"),
      list(
        message = sprintf("Run %s ended %s.", job_id, status),
        call = NULL,
        status = status,
        error_summary = job$response$error_summary %||% ""
      )
    ))
  }

  resp <- .cernal_request(job$client, "GET", paste0("/api/design/", job_id, "/results"),
                          query = job$result_options %||% list())
  job$response <- httr2::resp_body_json(resp, simplifyVector = FALSE)
  job
}

#' The status of a job, without waiting
#'
#' @param client A `cernal_client`.
#' @param job_id A job id, from `job$response$job_id`.
#' @export
cernal_status <- function(client, job_id) {
  resp <- .cernal_request(client, "GET", paste0("/api/design/", job_id))
  httr2::resp_body_json(resp, simplifyVector = TRUE)
}

#' Gate families, scoring metrics and their units
#'
#' Needs no key — `GET /api/version` is public.
#'
#' @param client A `cernal_client`.
#' @export
cernal_capabilities <- function(client) {
  resp <- .cernal_request(client, "GET", "/api/version", auth = FALSE)
  httr2::resp_body_json(resp, simplifyVector = TRUE)
}
