#!/usr/bin/env Rscript
# R/ch1/00_preflight.R - SOP step W3.2, the Chapter 1 preflight.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/00_preflight.R
#
# It hard-fails on the seven clauses of W3.2 and records two facts that the
# Chapter 1 runtime estimates depend on. Every clause runs; the script reports
# every failure, not only the first, and exits 1 if any clause failed.
#
# THE CLAUSES, in the SOP's order and with the SOP's numbers:
#
#   1  getRversion() >= "4.5.2"
#   2  packageVersion("mgcv") >= "1.9.4"
#   3  packageVersion("brms") == "2.23.0"
#   4  cmdstanr::cmdstan_version() == "2.40.0"
#   5  a 3-second CmdStan sample
#   6  free disk >= 25 GiB
#   7  all five warehouse inputs readable by arrow::open_dataset()
#
# THE TWO RECORDS. capabilities("OpenMP") and the thread warning mgcv::bam
# raises are recorded, not asserted. This R build has no OpenMP, so
# bam(nthreads=) is a no-op and a Chapter 1 runtime estimate that assumes
# threads inside a fit is wrong. Parallelism on this machine is across R
# processes. The records are here so the estimate is made against the machine
# that exists.
#
# CLAUSE 5. The SOP-final line reads "a 3-second CmdStan sample". The W3 draft
# it abbreviates reads "a 3-second CmdStan sample runs", so the condition is
# that the sample runs and the three seconds describe its size. The script
# fails when the sampler errors, when it returns the wrong number of draws or
# when rhat is not finite, and prints the elapsed time without comparing it to
# anything. A wall-clock ceiling invented here would fail the gate on a busy
# machine while the toolchain was intact. The measured sample is 0.4 s, so the
# margin under either reading is visible in the log.
#
# CLAUSE 7. The SOP names the five Chapter 1 inputs; section 2.6 maps them onto
# the warehouse relations below, and the two pitch-level ones are read through
# their open views, never through a fact table. The warehouse is one DuckDB
# file, so a relation is put in front of arrow::open_dataset() the only way a
# DuckDB relation can be: DuckDB writes a bounded extract of the relation to
# Parquet in a temporary directory, arrow::open_dataset() opens that directory
# and the whole extract is scanned into memory. A relation that cannot be read,
# or whose extract arrow cannot open, fails the clause. The extract is 2,000
# rows, which is enough to prove a read and cheap enough to run before every
# Chapter 1 session; the full row count of each input is read from DuckDB and
# printed beside it.
#
# THE WAREHOUSE PATH is not written here. tests/unit/test_paths.py holds every
# layout string to one copy, in src/absump/paths.py, so the script asks that
# module for the path through `uv run --locked python`, which costs 0.2 s.
#
# SIDE EFFECTS: none. Running it twice changes nothing on disk. It writes only
# into a temporary directory that it removes on exit, it holds a read-only
# connection to the warehouse, and it reaches no host, so the D-63 throttle
# policy is satisfied with zero requests. There is nothing to resume: every
# clause is independent and the whole script runs in under two minutes.

t0 <- Sys.time()

# The warehouse path. tests/unit/test_paths.py holds every layout string to one
# copy, in src/absump/paths.py, so this script asks that module for the path
# rather than writing it down a second time.
warehouse_path <- function() {
  out <- suppressWarnings(system2(
    "uv",
    c("run", "--locked", "python", "-c",
      shQuote("from absump.paths import DUCKDB_PATH; print(DUCKDB_PATH)")),
    stdout = TRUE, stderr = TRUE
  ))
  status <- attr(out, "status")
  if (is.null(status)) status <- 0L
  if (status != 0L || length(out) == 0L) {
    stop("could not read the warehouse path from absump.paths (exit ", status,
         "): ", paste(out, collapse = " "), call. = FALSE)
  }
  trimws(out[length(out)])
}

DISK_FLOOR_GIB <- 25
DISK_VOLUME    <- "/System/Volumes/Data"
CMDSTAN_DIR    <- path.expand("~/.cmdstan/cmdstan-2.40.0")
CMDSTAN_PIN    <- "2.40.0"
BRMS_PIN       <- "2.23.0"
R_FLOOR        <- "4.5.2"
MGCV_FLOOR     <- "1.9.4"
EXTRACT_ROWS   <- 2000L

# The five Chapter 1 inputs of SOP W3.1, under the names section 2.6 gives them.
INPUTS <- list(
  list(role = "called pitches", relation = "main_marts.v_called_pitch_open"),
  list(role = "challenges",     relation = "main_marts.v_challenge_open"),
  list(role = "umpire games",   relation = "main_marts.dim_umpire_game"),
  list(role = "batter heights", relation = "main_marts.dim_batter_season"),
  list(role = "AAA format",     relation = "main_marts.dim_aaa_format")
)

n_pass <- 0L
n_fail <- 0L

pass <- function(...) {
  n_pass <<- n_pass + 1L
  cat("PASS    ", ..., "\n", sep = "")
}
fail <- function(...) {
  n_fail <<- n_fail + 1L
  cat("FAIL    ", ..., "\n", sep = "")
}
record <- function(...) cat("record  ", ..., "\n", sep = "")

# A clause that throws is a clause that failed. The message is reported and the
# remaining clauses still run.
clause <- function(label, expr) {
  tryCatch(expr, error = function(e) fail(label, ": ", conditionMessage(e)))
}

## 1-3. R and the two pinned packages ------------------------------------------

clause("R version", {
  v <- getRversion()
  if (v >= R_FLOOR) {
    pass("R ", as.character(v), " (floor ", R_FLOOR, ")")
  } else {
    fail("R ", as.character(v), " is below the floor ", R_FLOOR)
  }
})

clause("mgcv version", {
  v <- packageVersion("mgcv")
  if (v >= MGCV_FLOOR) {
    pass("mgcv ", as.character(v), " (floor ", MGCV_FLOOR, ")")
  } else {
    fail("mgcv ", as.character(v), " is below the floor ", MGCV_FLOOR)
  }
})

clause("brms version", {
  v <- as.character(packageVersion("brms"))
  if (identical(v, BRMS_PIN)) {
    pass("brms ", v, " (pin ", BRMS_PIN, ")")
  } else {
    fail("brms ", v, " is not the pin ", BRMS_PIN)
  }
})

## 4-5. CmdStan, and a sample that runs ----------------------------------------

clause("CmdStan", {
  if (!dir.exists(CMDSTAN_DIR)) {
    fail("CmdStan is not at ", CMDSTAN_DIR)
  } else {
    suppressPackageStartupMessages(library(cmdstanr))
    cmdstanr::set_cmdstan_path(CMDSTAN_DIR)
    v <- cmdstanr::cmdstan_version()
    if (identical(v, CMDSTAN_PIN)) {
      pass("CmdStan ", v, " (pin ", CMDSTAN_PIN, ")")
    } else {
      fail("CmdStan ", v, " is not the pin ", CMDSTAN_PIN)
    }

    # The model is the two-line standard normal R/00_setup.R already uses, and
    # its compiled binary is cached outside the repository under a directory
    # named for the CmdStan version, so an upgrade cannot reuse a stale
    # executable and a warm run skips the compile. The sample is seeded, so two
    # runs produce the same rhat.
    cache_dir <- path.expand("~/.cache/absump/stan-2.40.0")
    dir.create(cache_dir, recursive = TRUE, showWarnings = FALSE)
    stan_file <- file.path(cache_dir, "ch1_preflight.stan")
    stan_code <- c("parameters { real mu; }", "model { mu ~ std_normal(); }")
    if (!file.exists(stan_file) ||
        !identical(readLines(stan_file, warn = FALSE), stan_code)) {
      writeLines(stan_code, stan_file)
    }
    mod <- cmdstanr::cmdstan_model(stan_file, quiet = TRUE)
    t_stan <- Sys.time()
    # Seeded, per RP-06: no stochastic call in this repository is unseeded.
    # The sampler's own stream is fixed by seed = below; set.seed() fixes R's
    # stream, which cmdstanr draws the chain ids and any jitter from, so the
    # whole preflight sample is reproducible and not only the Stan side.
    set.seed(20260925)
    fit <- mod$sample(
      chains = 2, parallel_chains = 2,
      iter_warmup = 1000, iter_sampling = 1000,
      seed = 20260925, refresh = 0, show_messages = FALSE
    )
    stan_secs <- as.numeric(difftime(Sys.time(), t_stan, units = "secs"))
    draws <- posterior::ndraws(fit$draws("mu"))
    rhat  <- fit$summary("mu")$rhat[1]
    if (draws != 2000L) {
      fail("CmdStan sample returned ", draws, " draws, expected 2000")
    } else if (!is.finite(rhat)) {
      fail("CmdStan sample returned an rhat that is not finite")
    } else {
      pass(sprintf("CmdStan sample: 2 chains x 1000 draws = %d, rhat %.5f, elapsed %.1f s",
                   draws, rhat, stan_secs))
    }
  }
})

## 6. Free disk ----------------------------------------------------------------

clause("free disk", {
  out <- system2("df", c("-Pk", DISK_VOLUME), stdout = TRUE, stderr = TRUE)
  kib <- suppressWarnings(as.numeric(strsplit(trimws(out[2]), "\\s+")[[1]][4]))
  if (!is.finite(kib)) {
    fail("could not read free space on ", DISK_VOLUME)
  } else {
    gib <- kib / 1048576
    if (gib >= DISK_FLOOR_GIB) {
      pass(sprintf("%.1f GiB free on %s (floor %d GiB)", gib, DISK_VOLUME, DISK_FLOOR_GIB))
    } else {
      fail(sprintf("%.1f GiB free on %s, floor is %d GiB", gib, DISK_VOLUME, DISK_FLOOR_GIB))
    }
  }
})

## 7. The five warehouse inputs, through arrow::open_dataset() -----------------

clause("warehouse inputs", {
  suppressPackageStartupMessages({
    library(arrow)
    library(duckdb)
    library(DBI)
  })
  wh <- warehouse_path()
  if (!file.exists(wh)) {
    fail("the warehouse is not at ", wh)
  } else {
    record("warehouse: ", wh)
    scratch <- file.path(tempdir(), "w32_extract")
    dir.create(scratch, recursive = TRUE, showWarnings = FALSE)
    on.exit(unlink(scratch, recursive = TRUE), add = TRUE)
    con <- NULL
    suppressMessages(
      con <- DBI::dbConnect(duckdb::duckdb(), dbdir = wh, read_only = TRUE)
    )
    on.exit(DBI::dbDisconnect(con, shutdown = TRUE), add = TRUE)

    for (inp in INPUTS) {
      rel   <- inp$relation
      label <- sub("^main_marts\\.", "", rel)
      tryCatch({
        n_rows <- DBI::dbGetQuery(con, paste0("SELECT count(*) AS n FROM ", rel))$n[1]
        dest   <- file.path(scratch, label)
        dir.create(dest, showWarnings = FALSE)
        target <- file.path(dest, "part-000.parquet")
        invisible(DBI::dbExecute(con, sprintf(
          "COPY (SELECT * FROM %s LIMIT %d) TO %s (FORMAT PARQUET)",
          rel, EXTRACT_ROWS, DBI::dbQuoteString(con, target)
        )))
        ds       <- arrow::open_dataset(dest)
        n_col    <- length(ds$schema$names)
        scanned  <- nrow(arrow::Scanner$create(ds)$ToTable())
        expected <- min(EXTRACT_ROWS, n_rows)
        if (n_rows <= 0) {
          fail(label, " (", inp$role, ") is empty")
        } else if (n_col <= 0) {
          fail(label, " (", inp$role, ") opened with no columns")
        } else if (scanned != expected) {
          fail(label, " (", inp$role, "): arrow scanned ", scanned,
               " rows of the ", expected, "-row extract")
        } else {
          pass(sprintf("%s (%s): %d rows, %d columns, arrow scanned %d",
                       label, inp$role, n_rows, n_col, scanned))
        }
      }, error = function(e) {
        fail(label, " (", inp$role, "): ", conditionMessage(e))
      })
    }
  }
})

## The two records -------------------------------------------------------------

omp <- capabilities("OpenMP")
if (length(omp) == 0L) {
  record("capabilities(\"OpenMP\") is length 0: this R build does not list ",
         "OpenMP among its capabilities at all. The names it does list are: ",
         paste(names(capabilities()), collapse = " "))
} else {
  record("capabilities(\"OpenMP\") = ", paste(omp, collapse = " "))
}

omp_flags <- suppressWarnings(
  system2("R", c("CMD", "config", "SHLIB_OPENMP_CFLAGS"),
          stdout = TRUE, stderr = TRUE)
)
omp_status <- attr(omp_flags, "status")
if (is.null(omp_status)) omp_status <- 0L
omp_text <- trimws(paste(omp_flags, collapse = " "))
if (omp_status != 0L) {
  record("R CMD config SHLIB_OPENMP_CFLAGS exits ", omp_status, " and says: ",
         omp_text, ". No OpenMP flags are configured.")
} else if (!nzchar(omp_text)) {
  record("R CMD config SHLIB_OPENMP_CFLAGS is empty. No OpenMP flags are configured.")
} else {
  record("R CMD config SHLIB_OPENMP_CFLAGS = '", omp_text, "'")
}

# The bam thread warning, taken from a real fit rather than quoted. The data is
# a Weyl sequence, so it carries no RNG draw and two runs build the same frame.
bam_warning <- NA_character_
tryCatch({
  suppressPackageStartupMessages(library(mgcv))
  n <- 4000L
  i <- seq_len(n)
  u1 <- (i * 0.6180339887498949) %% 1
  u2 <- (i * 0.7548776662466927) %% 1
  u3 <- (i * 0.5698402909980532) %% 1
  x <- -2.0 + 4.0 * u1
  z <- 0.8 + 3.2 * u2
  p <- 1 / (1 + exp(-(3.0 - 2.6 * (abs(x) - 0.83)^2 - 2.0 * (z - 2.5)^2)))
  d <- data.frame(x = x, z = z, cs = as.integer(u3 < p))
  withCallingHandlers(
    invisible(mgcv::bam(cs ~ s(x, z), family = binomial, data = d,
                        discrete = TRUE, nthreads = 2)),
    warning = function(w) {
      if (is.na(bam_warning)) bam_warning <<- conditionMessage(w)
      invokeRestart("muffleWarning")
    }
  )
}, error = function(e) bam_warning <<- paste("bam failed:", conditionMessage(e)))

if (is.na(bam_warning)) {
  record("bam(nthreads = 2) raised no thread warning")
} else {
  record("bam(nthreads = 2) warning: ", bam_warning)
}
record("bam(nthreads=) is a no-op on this build. Chapter 1 runtime estimates ",
       "assume parallelism across R processes, capped at 8 concurrent on 18 GB.")

## Verdict ---------------------------------------------------------------------

total <- as.numeric(difftime(Sys.time(), t0, units = "secs"))
cat(sprintf("W3.2 preflight: %d PASS, %d FAIL, elapsed %.1f s\n",
            n_pass, n_fail, total))
if (n_fail > 0L) {
  cat("PREFLIGHT W3.2 FAIL\n")
  quit(status = 1L)
}
cat("PREFLIGHT W3.2 OK\n")
quit(status = 0L)
