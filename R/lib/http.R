# R/lib/http.R -- the one HTTP call site for the R half of abs-umpires.
#
# SOP section 2.3, step W1.7. Rule 0.5.2 forbids any other R file in this
# repository from issuing a request; ops/lint_http.sh fails CI on a second call
# site. The Python counterpart is src/absump/http.py.
#
# The two clients are one policy in two languages. They read the same
# config/throttle.yml, send the same User-Agent, hold the same per-host delay,
# spend the same per-host daily budget out of the same data/raw/_budget.json,
# write the same zstandard level 10 frames to the same cache paths, and append
# to the same data/raw/_manifest.csv. A file fetched by either half is a cache
# hit for the other.
#
# Public: absump_http_get(url, host_budget = TRUE) -> list
# Everything named with a leading dot is private and may change.
#
# Sourcing this file issues no request and creates no directory.

suppressPackageStartupMessages({
  library(httr2)
  library(yaml)
  library(jsonlite)
  library(openssl)
  library(arrow)
})

.absump_http <- new.env(parent = emptyenv())
.absump_http$config <- NULL
.absump_http$config_path <- NULL
.absump_http$cache_dir <- NULL
.absump_http$last_request_at <- list()

# Section 2.3, storage: zstandard level 10.
.ABSUMP_ZSTD_LEVEL <- 10L

# Section 2.3: exponential 2/4/8/16/32 on these, and 403 is FATAL.
.ABSUMP_RETRY_STATUS <- c(429L, 500L, 502L, 503L, 504L)
.ABSUMP_FATAL_STATUS <- c(403L)

.ABSUMP_STATSAPI_HOST <- "statsapi.mlb.com"
.ABSUMP_SAVANT_HOST <- "baseballsavant.mlb.com"
.ABSUMP_SAVANT_LEADERBOARD_PATH <- "/leaderboard/abs-challenges"

# Every Savant CSV carries a UTF-8 BOM (section 2.3; UT-14). Read one with
# readr::read_csv(locale = locale(encoding = ABSUMP_SAVANT_CSV_ENCODING)) or
# base read.csv(fileEncoding = ...), never with plain "UTF-8".
ABSUMP_SAVANT_CSV_ENCODING <- "UTF-8-BOM"

# The canonical Savant ABS leaderboard URL. The year= form 301-redirects and
# the csv=true export returns HTTP 500 (SOP W2.11). Both are refused below.
ABSUMP_SAVANT_ABS_LEADERBOARD_URL <- paste0(
  "https://baseballsavant.mlb.com/leaderboard/abs-challenges",
  "?level=%s&challengeType=%s&season%%5B%%5D=%s"
)

# Manifest columns, in order, exactly as section 2.3 states them.
.ABSUMP_MANIFEST_COLUMNS <- c(
  "fetched_at_utc", "host", "url", "http_status", "wire_bytes",
  "disk_bytes", "sha256", "attempt", "elapsed_s", "dest_path"
)

.absump_repo_root <- function() {
  this_file <- tryCatch(normalizePath(sys.frame(1)$ofile), error = function(e) NA_character_)
  if (is.na(this_file)) {
    return(normalizePath(getwd()))
  }
  normalizePath(file.path(dirname(this_file), "..", ".."))
}

.absump_root <- function() {
  root <- Sys.getenv("ABSUMP_REPO_ROOT", "")
  if (nzchar(root)) normalizePath(root) else .ABSUMP_ROOT
}

# Resolved once at source time, so a later setwd() cannot move the config.
.ABSUMP_ROOT <- .absump_repo_root()

.absump_config_path <- function() {
  if (!is.null(.absump_http$config_path)) {
    return(.absump_http$config_path)
  }
  file.path(.absump_root(), "config", "throttle.yml")
}

#' Read config/throttle.yml once per session. The only source of a delay, a
#' cap or the User-Agent anywhere in the R half.
.absump_config <- function() {
  if (!is.null(.absump_http$config)) {
    return(.absump_http$config)
  }
  path <- .absump_config_path()
  config <- yaml::read_yaml(path)
  required <- c(
    "user_agent", "timeout_seconds", "max_attempts", "backoff_base_seconds",
    "min_interval_seconds", "daily_request_budget", "cache_dir"
  )
  missing <- setdiff(required, names(config))
  if (length(missing) > 0L) {
    stop(sprintf("%s is missing %s", path, paste(missing, collapse = ", ")), call. = FALSE)
  }
  if (grepl("@", config$user_agent, fixed = TRUE)) {
    # Section 2.3: no email address is ever sent to any host.
    stop(sprintf("%s: user_agent contains '@'", path), call. = FALSE)
  }
  unbudgeted <- setdiff(names(config$min_interval_seconds), names(config$daily_request_budget))
  if (length(unbudgeted) > 0L) {
    stop(sprintf("%s: no daily cap for %s", path, paste(unbudgeted, collapse = ", ")),
      call. = FALSE
    )
  }
  .absump_http$config <- config
  config
}

.absump_min_interval <- function(host) {
  table <- .absump_config()$min_interval_seconds
  as.numeric(if (!is.null(table[[host]])) table[[host]] else table[["default"]])
}

.absump_daily_cap <- function(host) {
  table <- .absump_config()$daily_request_budget
  as.integer(if (!is.null(table[[host]])) table[[host]] else table[["default"]])
}

.absump_cache_dir <- function() {
  if (!is.null(.absump_http$cache_dir)) {
    return(.absump_http$cache_dir)
  }
  configured <- .absump_config()$cache_dir
  if (grepl("^(/|[A-Za-z]:)", configured)) configured else file.path(.absump_root(), configured)
}

.absump_host_of <- function(url) {
  host <- httr2::url_parse(url)$hostname
  if (is.null(host) || !nzchar(host)) {
    stop(sprintf("no host in URL: %s", url), call. = FALSE)
  }
  host
}

# ---------------------------------------------------------------------------
# Throttle: one gap per host, on a clock that cannot go backwards
# ---------------------------------------------------------------------------

.absump_monotonic <- function() {
  as.numeric(proc.time()[["elapsed"]])
}

.absump_sleep <- function(seconds) {
  Sys.sleep(seconds)
}

.absump_throttle <- function(host) {
  interval <- .absump_min_interval(host)
  last <- .absump_http$last_request_at[[host]]
  now <- .absump_monotonic()
  if (!is.null(last)) {
    wait <- interval - (now - last)
    if (wait > 0) {
      .absump_sleep(wait)
      now <- .absump_monotonic()
    }
  }
  .absump_http$last_request_at[[host]] <- now
  invisible(now)
}

# ---------------------------------------------------------------------------
# Daily budget: per host, per UTC day, in the same file the Python half uses
# ---------------------------------------------------------------------------

.absump_utc_day <- function() {
  format(as.POSIXlt(Sys.time(), tz = "UTC"), "%Y-%m-%d")
}

.absump_budget_path <- function() {
  file.path(.absump_cache_dir(), "_budget.json")
}

.absump_read_budget <- function() {
  path <- .absump_budget_path()
  today <- .absump_utc_day()
  empty <- list(utc_date = today, used = structure(list(), names = character(0)))
  if (!file.exists(path)) {
    return(empty)
  }
  state <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(state) || !identical(state$utc_date, today) || !is.list(state$used)) {
    return(empty)
  }
  list(utc_date = today, used = state$used)
}

.absump_write_budget <- function(state) {
  path <- .absump_budget_path()
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  tmp <- paste0(path, ".tmp")
  writeLines(jsonlite::toJSON(state, auto_unbox = TRUE, pretty = TRUE), tmp)
  file.rename(tmp, path)
  invisible(path)
}

.absump_budget_take <- function(host) {
  cap <- .absump_daily_cap(host)
  state <- .absump_read_budget()
  used <- if (is.null(state$used[[host]])) 0L else as.integer(state$used[[host]])
  if (used >= cap) {
    stop(sprintf(
      "BudgetExceeded: %s used %d/%d requests on %s UTC; config/throttle.yml is the only place this cap is set",
      host, used, cap, state$utc_date
    ), call. = FALSE)
  }
  state$used[[host]] <- used + 1L
  .absump_write_budget(state)
  invisible(cap - (used + 1L))
}

# ---------------------------------------------------------------------------
# Raw cache and manifest, shared byte for byte with the Python half
# ---------------------------------------------------------------------------

.absump_url_digest <- function(url) {
  paste(openssl::sha256(charToRaw(url)), collapse = "")
}

.absump_dest_path <- function(url) {
  digest <- .absump_url_digest(url)
  file.path(
    .absump_cache_dir(), .absump_host_of(url), substr(digest, 1L, 2L),
    paste0(digest, ".zst")
  )
}

.absump_manifest_path <- function() {
  file.path(.absump_cache_dir(), "_manifest.csv")
}

.absump_manifest_rows <- function() {
  path <- .absump_manifest_path()
  if (!file.exists(path)) {
    return(NULL)
  }
  utils::read.csv(path, colClasses = "character", check.names = FALSE)
}

.absump_manifest_row_for <- function(url) {
  rows <- .absump_manifest_rows()
  if (is.null(rows) || nrow(rows) == 0L) {
    return(NULL)
  }
  hit <- rows[rows$url == url, , drop = FALSE]
  if (nrow(hit) == 0L) {
    return(NULL)
  }
  as.list(hit[nrow(hit), , drop = FALSE])
}

.absump_manifest_append <- function(row) {
  path <- .absump_manifest_path()
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  frame <- as.data.frame(row[.ABSUMP_MANIFEST_COLUMNS], stringsAsFactors = FALSE)
  utils::write.table(
    frame, path,
    sep = ",", row.names = FALSE, col.names = !file.exists(path),
    append = file.exists(path), qmethod = "double", fileEncoding = "UTF-8"
  )
  invisible(path)
}

.absump_write_raw <- function(dest, body) {
  dir.create(dirname(dest), recursive = TRUE, showWarnings = FALSE)
  if (file.exists(dest)) {
    return(as.integer(file.info(dest)$size))
  }
  tmp <- paste0(dest, ".tmp")
  codec <- arrow::Codec$create("zstd", compression_level = .ABSUMP_ZSTD_LEVEL)
  stream <- arrow::CompressedOutputStream$create(tmp, codec = codec)
  stream$write(body)
  stream$close()
  file.rename(tmp, dest)
  as.integer(file.info(dest)$size)
}

.absump_read_raw <- function(dest) {
  stream <- arrow::CompressedInputStream$create(dest, codec = arrow::Codec$create("zstd"))
  chunks <- list()
  repeat {
    buffer <- stream$Read(1048576L)
    if (buffer$size == 0L) break
    chunks[[length(chunks) + 1L]] <- as.raw(buffer)
  }
  stream$close()
  if (length(chunks) == 0L) raw(0) else do.call(c, chunks)
}

# ---------------------------------------------------------------------------
# Endpoint contract (SOP section 2.3, W2.11, W4.2)
# ---------------------------------------------------------------------------

.absump_check_contract <- function(url, host) {
  if (!identical(host, .ABSUMP_SAVANT_HOST)) {
    return(invisible(NULL))
  }
  parsed <- httr2::url_parse(url)
  path <- if (is.null(parsed$path)) "" else parsed$path
  if (!startsWith(path, .ABSUMP_SAVANT_LEADERBOARD_PATH)) {
    return(invisible(NULL))
  }
  query <- parsed$query
  if (!is.null(query$csv) && tolower(as.character(query$csv)) == "true") {
    stop(paste(
      "Fatal: the Savant ABS leaderboard csv=true export returns HTTP 500 with a",
      "text/html body even with the page's own serverParams; parse the page's",
      "absData block instead (SOP W2.11)"
    ), call. = FALSE)
  }
  if (!is.null(query$year)) {
    stop(sprintf(
      "Fatal: the Savant ABS leaderboard year= form 301-redirects; use the canonical season[]= form: %s",
      ABSUMP_SAVANT_ABS_LEADERBOARD_URL
    ), call. = FALSE)
  }
  invisible(NULL)
}

# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------

.absump_headers <- function(host) {
  # One User-Agent, from config, set with req_user_agent. Nothing here can
  # identify a person: section 2.3 sends no email address to any host.
  list(
    # 6.3x less bandwidth off MLB's servers on the measured feed. Savant's CSV
    # endpoint does not compress, so its cost is fixed.
    "Accept-Encoding" = "gzip, deflate",
    # statsapi returns 406 without it.
    "Accept" = if (identical(host, .ABSUMP_STATSAPI_HOST)) "application/json" else "*/*"
  )
}

.absump_backoff <- function(attempt, base) {
  # Section 2.3: exponential 2/4/8/16/32, capped at backoff_base_seconds x 8.
  min(2^attempt, base * 8)
}

.absump_build_request <- function(url, host) {
  config <- .absump_config()
  req <- httr2::request(url)
  req <- httr2::req_user_agent(req, config$user_agent)
  req <- do.call(httr2::req_headers, c(list(req), .absump_headers(host)))
  req <- httr2::req_timeout(req, as.numeric(config$timeout_seconds))
  req <- httr2::req_options(req, followlocation = 0L)
  # Statuses are classified here, not by httr2: 403 is fatal, a 4xx is never
  # retried, a 5xx and a 429 go on the ladder.
  httr2::req_error(req, is_error = function(resp) FALSE)
}

.absump_perform <- function(url, host, host_budget) {
  config <- .absump_config()
  max_attempts <- as.integer(config$max_attempts)
  base <- as.numeric(config$backoff_base_seconds)
  req <- .absump_build_request(url, host)
  attempt <- 0L
  repeat {
    attempt <- attempt + 1L
    .absump_throttle(host)
    if (isTRUE(host_budget)) {
      .absump_budget_take(host)
    }
    started <- .absump_monotonic()
    resp <- tryCatch(httr2::req_perform(req), error = function(e) e)
    elapsed <- .absump_monotonic() - started

    if (inherits(resp, "error")) {
      if (attempt < max_attempts) {
        .absump_sleep(.absump_backoff(attempt, base))
        next
      }
      stop(sprintf(
        "Retryable: %s failed on attempt %d of %d: %s",
        host, attempt, max_attempts, conditionMessage(resp)
      ), call. = FALSE)
    }

    status <- as.integer(httr2::resp_status(resp))
    if (status %in% .ABSUMP_FATAL_STATUS) {
      stop(sprintf(
        "Fatal: %d from %s on attempt %d: the host has refused this client. Stop the pull. URL: %s",
        status, host, attempt, url
      ), call. = FALSE)
    }
    if (status %in% .ABSUMP_RETRY_STATUS || (status >= 500L && status < 600L)) {
      if (attempt < max_attempts) {
        .absump_sleep(.absump_backoff(attempt, base))
        next
      }
      stop(sprintf(
        "Retryable: %d from %s after %d attempts. URL: %s", status, host, attempt, url
      ), call. = FALSE)
    }
    if (status >= 400L && status < 500L) {
      stop(sprintf("Fatal: %d from %s: a 4xx is never retried. URL: %s", status, host, url),
        call. = FALSE
      )
    }
    if (status >= 300L && status < 400L) {
      stop(sprintf(
        "Fatal: %d from %s to %s: this URL is not canonical. Fetch the canonical form. URL: %s",
        status, host, httr2::resp_header(resp, "location"), url
      ), call. = FALSE)
    }
    return(list(response = resp, elapsed = elapsed, attempt = attempt))
  }
}

# ---------------------------------------------------------------------------
# The one public function
# ---------------------------------------------------------------------------

.absump_dry_run <- function() {
  value <- tolower(trimws(Sys.getenv("ABSUMP_DRY_RUN", "")))
  !(value %in% c("", "0", "false", "no"))
}

#' Fetch a URL under the project's throttle, budget and cache policy.
#'
#' Returns the cached copy without touching the network when the URL is
#' already in data/raw/_manifest.csv and its file is still on disk, so a re-run
#' of a completed pull costs zero requests. host_budget = FALSE skips the daily
#' cap for a single probe; it never skips the inter-request delay.
absump_http_get <- function(url, host_budget = TRUE) {
  stopifnot(is.character(url), length(url) == 1L, nzchar(url))
  host <- .absump_host_of(url)
  .absump_check_contract(url, host)
  dest <- .absump_dest_path(url)

  if (.absump_dry_run()) {
    message(sprintf(
      "DRY RUN: 1 URL, 0 sent.\n  fetch   %s\n          -> %s\n          est %.1f s at the configured interval",
      url, dest, .absump_min_interval(host)
    ))
    return(list(
      url = url, host = host, status_code = 0L, content = raw(0), dest_path = dest,
      sha256 = "", wire_bytes = 0L, disk_bytes = 0L, attempt = 0L, elapsed_s = 0,
      from_cache = FALSE, dry_run = TRUE
    ))
  }

  row <- .absump_manifest_row_for(url)
  if (!is.null(row) && file.exists(dest)) {
    body <- .absump_read_raw(dest)
    return(list(
      url = url, host = host, status_code = as.integer(row$http_status), content = body,
      dest_path = dest, sha256 = row$sha256, wire_bytes = as.integer(row$wire_bytes),
      disk_bytes = as.integer(file.info(dest)$size), attempt = 0L, elapsed_s = 0,
      from_cache = TRUE, dry_run = FALSE
    ))
  }

  outcome <- .absump_perform(url, host, host_budget)
  body <- httr2::resp_body_raw(outcome$response)
  # curl does not hand back the compressed transfer size here, so the manifest
  # records the Content-Length the host declared when it declared one, and the
  # decoded length otherwise. The Python half records the wire count directly.
  declared <- httr2::resp_header(outcome$response, "content-length")
  wire_bytes <- if (is.null(declared)) length(body) else as.integer(declared)
  disk_bytes <- .absump_write_raw(dest, body)
  digest <- paste(openssl::sha256(body), collapse = "")
  .absump_manifest_append(list(
    fetched_at_utc = format(as.POSIXlt(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ"),
    host = host,
    url = url,
    http_status = as.integer(httr2::resp_status(outcome$response)),
    wire_bytes = wire_bytes,
    disk_bytes = disk_bytes,
    sha256 = digest,
    attempt = outcome$attempt,
    elapsed_s = sprintf("%.3f", outcome$elapsed),
    dest_path = dest
  ))
  list(
    url = url, host = host,
    status_code = as.integer(httr2::resp_status(outcome$response)),
    content = body, dest_path = dest, sha256 = digest, wire_bytes = wire_bytes,
    disk_bytes = disk_bytes, attempt = outcome$attempt, elapsed_s = outcome$elapsed,
    from_cache = FALSE, dry_run = FALSE
  )
}

#' Drop cached session state. Tests only; the throttle clock and the daily
#' budget are deliberately session-wide.
.absump_reset_state <- function(config_path = NULL, cache_dir = NULL) {
  .absump_http$config <- NULL
  .absump_http$config_path <- config_path
  .absump_http$cache_dir <- cache_dir
  .absump_http$last_request_at <- list()
  invisible(NULL)
}
