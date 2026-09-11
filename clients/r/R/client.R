# The cernal HTTP client (docs/public-api.md §11.2). httr2 + tibble, no Bioconductor
# dependency.

`%||%` <- function(a, b) if (is.null(a)) b else a

#' Create a CERNAL client
#'
#' Holds a key and a base URL. Nothing else here is stateful.
#'
#' @param api_key An `X-API-Key` secret (`cern_live_...`). Defaults to the
#'   `CERNAL_API_KEY` environment variable.
#' @param base_url The deployment to talk to — no default, since there is no public
#'   CERNAL host to assume.
#' @param timeout Seconds per HTTP request (not the run itself — see [cernal_wait()]).
#' @return A `cernal_client` object.
#' @export
cernal_client <- function(api_key = Sys.getenv("CERNAL_API_KEY"), base_url, timeout = 30) {
  if (!nzchar(api_key)) {
    stop("No API key. Pass api_key=, or set CERNAL_API_KEY.", call. = FALSE)
  }
  structure(
    list(api_key = api_key, base_url = sub("/$", "", base_url), timeout = timeout),
    class = "cernal_client"
  )
}

#' @keywords internal
.cernal_request <- function(client, method, path, body = NULL, query = list(), auth = TRUE) {
  req <- httr2::request(paste0(client$base_url, path))
  req <- httr2::req_method(req, method)
  req <- httr2::req_timeout(req, client$timeout)
  if (auth) {
    req <- httr2::req_headers(req, `X-API-Key` = client$api_key)
  }
  if (length(query) > 0) {
    req <- httr2::req_url_query(req, !!!query)
  }
  if (!is.null(body)) {
    # req_body_json()'s default is auto_unbox = TRUE: a length-1 R vector becomes a
    # JSON scalar, not a single-element array. This is the one real trap every
    # hand-written R client ships with — max_triggers = 2 silently becoming [2] on
    # the wire (docs/public-api.md §11.2) — and it is why this must not be overridden.
    req <- httr2::req_body_json(req, body)
  }
  # Handled explicitly below, so a 4xx/5xx does not raise httr2's own generic error
  # before .cernal_check_response can read the envelope and map it to a typed one.
  req <- httr2::req_error(req, is_error = function(resp) FALSE)
  resp <- httr2::req_perform(req)
  .cernal_check_response(resp)
  resp
}

#' @keywords internal
.cernal_check_response <- function(resp) {
  status <- httr2::resp_status(resp)
  if (status < 400) {
    return(invisible(NULL))
  }

  body <- tryCatch(httr2::resp_body_json(resp), error = function(e) list())
  err <- body$error %||% list()
  message <- err$message %||% tryCatch(httr2::resp_body_string(resp), error = function(e) "")
  code <- err$code %||% ""
  detail <- err$detail %||% list()

  # One class hierarchy per docs/public-api.md §10's error codes, so a caller can
  # tryCatch(..., cernal_validation_error = function(e) ...) instead of parsing codes.
  if (status == 401) {
    stop(structure(
      class = c("cernal_auth_error", "cernal_error", "error", "condition"),
      list(message = message, call = NULL)
    ))
  }
  if (status == 422) {
    did_you_mean <- detail$did_you_mean
    hint <- if (!is.null(did_you_mean)) paste0(" Did you mean '", did_you_mean, "'?") else ""
    stop(structure(
      class = c("cernal_validation_error", "cernal_error", "error", "condition"),
      list(message = paste0(message, hint), call = NULL, code = code, detail = detail)
    ))
  }
  if (status == 429) {
    retry_after <- httr2::resp_header(resp, "Retry-After")
    suffix <- if (!is.null(retry_after)) paste0(" (retry after ", retry_after, "s)") else ""
    stop(structure(
      class = c("cernal_rate_limited", "cernal_error", "error", "condition"),
      list(message = paste0(message, suffix), call = NULL, retry_after = retry_after)
    ))
  }
  stop(structure(
    class = c("cernal_error", "error", "condition"),
    list(message = paste0(code, ": ", message), call = NULL)
  ))
}
