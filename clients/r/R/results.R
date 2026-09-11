# Reading results (docs/public-api.md §8, §11.2).

#' Ranked candidates as a tibble
#'
#' One row per candidate, metrics decomposed into columns — what makes this worth
#' writing at all: the output drops straight into dplyr and ggplot2. The natural next
#' step is `DESeq2::results() |> as.data.frame() |> cernal_design(...)`: DESeq2 output
#' to plasmid design in one script.
#'
#' @param job A `cernal_job` that has been through [cernal_wait()].
#' @return A tibble, one row per candidate.
#' @export
cernal_results <- function(job) {
  candidates <- job$response$candidates
  if (is.null(candidates)) {
    stop("Call cernal_wait() before cernal_results().", call. = FALSE)
  }
  if (length(candidates) == 0) {
    return(tibble::tibble())
  }

  rows <- lapply(candidates, function(candidate) {
    metric_cols <- stats::setNames(
      lapply(candidate$metrics, function(m) m$raw_value %||% NA_real_),
      vapply(candidate$metrics, function(m) m$name, character(1))
    )
    c(
      list(
        id = candidate$id,
        engine_ref = candidate$engine_ref,
        rank = candidate$rank %||% NA_integer_,
        overall_score = candidate$overall_score %||% NA_real_,
        gate_family = candidate$gate_family,
        logic_type = candidate$logic_type,
        is_rejected = candidate$is_rejected,
        rejection_reason = candidate$rejection_reason,
        output = candidate$output %||% NA_character_
      ),
      metric_cols
    )
  })

  tibble::as_tibble(do.call(
    rbind.data.frame,
    lapply(rows, as.data.frame, stringsAsFactors = FALSE)
  ))
}

#' The highest-ranked candidate
#'
#' @param job A `cernal_job` that has been through [cernal_wait()].
#' @return A one-row tibble, or `NULL` if every candidate was rejected.
#' @export
cernal_best <- function(job) {
  results <- cernal_results(job)
  if (nrow(results) == 0) return(NULL)
  results[1, ]
}

#' Download an artifact
#'
#' Fetched fresh — a prior `include_artifacts` at submission time is not required.
#'
#' @param job A `cernal_job` that has been through [cernal_wait()].
#' @param kind e.g. `"fasta"`, `"structure_svg"`.
#' @param path Where to save it.
#' @export
cernal_artifact <- function(job, kind, path) {
  job_id <- job$response$job_id
  resp <- .cernal_request(
    job$client, "GET", paste0("/api/design/", job_id, "/results"),
    query = list(include_artifacts = kind)
  )
  body <- httr2::resp_body_json(resp, simplifyVector = FALSE)
  matches <- Filter(function(a) identical(a$kind, kind), body$artifacts)
  if (length(matches) == 0) {
    stop(sprintf("No artifact of kind '%s' on job %s.", kind, job_id), call. = FALSE)
  }

  artifact_resp <- .cernal_request(
    job$client, "GET", paste0("/api/artifacts/", matches[[1]]$id, "/download")
  )
  writeBin(httr2::resp_body_raw(artifact_resp), path)
  invisible(path)
}
