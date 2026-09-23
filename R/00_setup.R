#!/usr/bin/env Rscript
# R/00_setup.R - R stack smoke test. SOP W1.5. Run by `make r-smoke`.
#
# Loads the analysis stack, prints versions, asserts that DYLD_LIBRARY_PATH is
# empty, compiles the two-line Stan model, samples 2 chains x 200 draws and
# asserts rhat < 1.01. Exits non-zero on the first failure.
#
# Budget recorded in SOP W1.5: stack load 4.0 s, full CmdStan path 38 s. The
# compiled model is cached outside the repository, so reruns skip compilation.
#
# Run from the repository root so that .Rprofile activates renv.

t0 <- Sys.time()

fail <- function(...) stop(..., call. = FALSE)

## 1. Preconditions -----------------------------------------------------------

dyld <- Sys.getenv("DYLD_LIBRARY_PATH")
if (nzchar(dyld)) {
  fail("DYLD_LIBRARY_PATH is non-empty: '", dyld, "'. CmdStan does not link ",
       "correctly with it set. Unset it and run again.")
}
cat("DYLD_LIBRARY_PATH: empty\n")

lib <- .libPaths()[1]
if (!grepl("renv/library", lib, fixed = TRUE)) {
  fail("renv is not active. First library path is '", lib, "'. ",
       "Run this script from the repository root.")
}
cat("library:           ", lib, "\n", sep = "")

cmdstan_dir <- path.expand("~/.cmdstan/cmdstan-2.40.0")
if (!dir.exists(cmdstan_dir)) fail("CmdStan not found at ", cmdstan_dir)

## 2. Stack -------------------------------------------------------------------

t_load <- Sys.time()
suppressPackageStartupMessages({
  library(brms)
  library(mgcv)
  library(arrow)
  library(duckdb)
  library(data.table)
  library(baseballr)
  library(cmdstanr)
})
load_secs <- as.numeric(difftime(Sys.time(), t_load, units = "secs"))

cmdstanr::set_cmdstan_path(cmdstan_dir)

cat("\nversions\n")
cat(sprintf("  %-12s %s\n", "R", as.character(getRversion())))
for (p in c("brms", "mgcv", "arrow", "duckdb", "data.table", "baseballr",
            "cmdstanr", "renv")) {
  cat(sprintf("  %-12s %s\n", p, as.character(packageVersion(p))))
}
cat(sprintf("  %-12s %s\n", "cmdstan", cmdstanr::cmdstan_version()))
cat(sprintf("  %-12s %s\n", "cmdstan_path", cmdstanr::cmdstan_path()))
cat(sprintf("stack load: %.1f s\n", load_secs))

## 3. Two-line Stan model -----------------------------------------------------

# Cached outside the repository: a compiled binary is not a repository artifact.
# The CmdStan version is in the directory name so an upgrade cannot reuse a
# stale executable.
cache_dir <- path.expand("~/.cache/absump/stan-2.40.0")
dir.create(cache_dir, recursive = TRUE, showWarnings = FALSE)
stan_file <- file.path(cache_dir, "smoke.stan")

stan_code <- c(
  "parameters { real mu; }",
  "model { mu ~ std_normal(); }"
)
if (!file.exists(stan_file) ||
    !identical(readLines(stan_file, warn = FALSE), stan_code)) {
  writeLines(stan_code, stan_file)
}

t_stan <- Sys.time()
mod <- cmdstanr::cmdstan_model(stan_file, quiet = TRUE)

# Seeded, per RP-06: no stochastic call in this repository is unseeded.
set.seed(20260923)
fit <- mod$sample(
  chains = 2,
  parallel_chains = 2,
  iter_warmup = 200,
  iter_sampling = 200,
  seed = 20260923,
  refresh = 0,
  show_messages = FALSE
)
stan_secs <- as.numeric(difftime(Sys.time(), t_stan, units = "secs"))

s <- fit$summary("mu")
rhat <- s$rhat[1]
draws <- posterior::ndraws(fit$draws("mu"))

cat(sprintf("\nstan: 2 chains x 200 draws = %d draws, rhat = %.5f, %.1f s\n",
            draws, rhat, stan_secs))

if (!identical(draws, 400L) && draws != 400) {
  fail("expected 400 post-warmup draws, got ", draws)
}
if (!is.finite(rhat)) fail("rhat is not finite")
if (rhat >= 1.01) fail("rhat ", format(rhat), " is not below 1.01")

total <- as.numeric(difftime(Sys.time(), t0, units = "secs"))
cat(sprintf("\nR SMOKE OK (%.1f s)\n", total))
