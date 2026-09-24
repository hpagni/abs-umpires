#!/usr/bin/env Rscript
# ops/smoke_r.R - smoke check 5, the R stack. SOP step W1.15.
#
# Two SOP clauses, one R session. W1.15 names a 2-chain CmdStan fit with
# rhat < 1.01 and an mgcv::bam with s(plate_x, plate_z), binomial, on 50,000
# synthetic called pitches. Both run here. They share one session because the
# renv library load is the fixed cost on this machine and paying it twice buys
# nothing: the two assertions are independent of each other either way.
#
# It also refreshes RP-04: CmdStan is the pinned 2.40.0 and DYLD_LIBRARY_PATH is
# empty. .Rprofile refuses to start R with that variable set, so a non-empty
# value fails twice.
#
# The Stan model and its compiled binary are the ones R/00_setup.R caches under
# ~/.cache/absump/stan-2.40.0, outside the repository. A compiled binary is not a
# repository artifact, and the CmdStan version is in the directory name so an
# upgrade cannot reuse a stale executable. Warm runs skip compilation.
#
# The 50,000 called pitches are synthetic and carry no RNG draw. Every row is a
# fixed arithmetic function of its row index through a Weyl sequence, so two runs
# build identical data and the check is safe to re-run. The Stan fit is seeded
# with 20260923, the seed R/00_setup.R already uses for the same two-line model.
#
# No network. No lake read. Nothing here reads data/staging, data/raw or
# data/sealed.
#
# Run from the repository root so that .Rprofile activates renv.

t0 <- Sys.time()
fail <- function(...) stop(..., call. = FALSE)

## 1. RP-04 preconditions ------------------------------------------------------

dyld <- Sys.getenv("DYLD_LIBRARY_PATH")
if (nzchar(dyld)) {
  fail("DYLD_LIBRARY_PATH is non-empty: '", dyld, "'. CmdStan does not link ",
       "correctly with it set.")
}

lib <- .libPaths()[1]
if (!grepl("renv/library", lib, fixed = TRUE)) {
  fail("renv is not active. First library path is '", lib,
       "'. Run this from the repository root.")
}

cmdstan_dir <- path.expand("~/.cmdstan/cmdstan-2.40.0")
if (!dir.exists(cmdstan_dir)) fail("CmdStan not found at ", cmdstan_dir)

suppressPackageStartupMessages({
  library(mgcv)
  library(cmdstanr)
})
cmdstanr::set_cmdstan_path(cmdstan_dir)

cmdstan_ver <- cmdstanr::cmdstan_version()
if (!identical(cmdstan_ver, "2.40.0")) {
  fail("CmdStan is ", cmdstan_ver, ", not the pinned 2.40.0")
}

## 2. The 2-chain CmdStan fit, rhat < 1.01 -------------------------------------

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

if (draws != 400) fail("expected 400 post-warmup draws, got ", draws)
if (!is.finite(rhat)) fail("rhat is not finite")
if (rhat >= 1.01) fail("rhat ", format(rhat), " is not below 1.01")

cat(sprintf("smoke-r stan: 2 chains x 200 draws = %d, rhat = %.5f, %.1f s\n",
            draws, rhat, stan_secs))

## 3. mgcv::bam, s(plate_x, plate_z), binomial, 50,000 called pitches ----------

# Deterministic, no RNG. The Weyl sequence frac(i * phi) is equidistributed on
# (0, 1), so u1 and u2 fill the plate rectangle evenly and u3 decides the call
# against the true probability. Two runs produce identical data.
n <- 50000L
i <- seq_len(n)
phi1 <- 0.6180339887498949   # frac(sqrt(5) - 1)/2
phi2 <- 0.7548776662466927   # the 2D plastic-number companion
phi3 <- 0.5698402909980532   # its square, for the third coordinate

u1 <- (i * phi1) %% 1
u2 <- (i * phi2) %% 1
u3 <- (i * phi3) %% 1

# Feet. The rulebook plate half-width plus a ball is about 0.83 ft; the zone
# runs roughly 1.5 to 3.5 ft. The band below is wider than both on purpose, so
# the surface has called balls as well as called strikes to separate.
plate_x <- -2.0 + 4.0 * u1
plate_z <- 0.8 + 3.2 * u2

# A smooth true surface, highest in the middle of the zone. Not a model of any
# umpire: it exists so that s(plate_x, plate_z) has something to recover.
eta <- 3.0 - 2.6 * (abs(plate_x) - 0.83)^2 - 2.0 * (plate_z - 2.5)^2
p <- 1 / (1 + exp(-eta))
called_strike <- as.integer(u3 < p)

d <- data.frame(plate_x = plate_x, plate_z = plate_z,
                called_strike = called_strike)

if (nrow(d) != 50000L) fail("expected 50,000 synthetic called pitches, got ", nrow(d))
n_strike <- sum(d$called_strike)
if (n_strike < 5000L || n_strike > 45000L) {
  fail("synthetic calls are degenerate: ", n_strike, " strikes of ", nrow(d))
}

t_bam <- Sys.time()
m <- mgcv::bam(called_strike ~ s(plate_x, plate_z),
               family = binomial, data = d, discrete = TRUE)
bam_secs <- as.numeric(difftime(Sys.time(), t_bam, units = "secs"))

if (!isTRUE(m$converged)) fail("mgcv::bam did not converge")
if (!identical(nrow(m$model), 50000L)) {
  fail("mgcv::bam fitted ", nrow(m$model), " rows, expected 50,000")
}
edf <- sum(m$edf)
if (!is.finite(edf) || edf <= 3) fail("bam edf is ", edf, "; the smooth is degenerate")

fitted_p <- fitted(m)
if (any(!is.finite(fitted_p)) || min(fitted_p) <= 0 || max(fitted_p) >= 1) {
  fail("bam fitted probabilities left (0, 1)")
}
dev_expl <- summary(m)$dev.expl
if (!is.finite(dev_expl) || dev_expl <= 0.05) {
  fail("bam explained ", format(dev_expl), " of the deviance; the smooth recovered nothing")
}

cat(sprintf(paste0("smoke-r bam: 50000 called pitches, %d strikes, edf %.2f, ",
                   "deviance explained %.3f, %.1f s\n"),
            n_strike, edf, dev_expl, bam_secs))

total <- as.numeric(difftime(Sys.time(), t0, units = "secs"))
cat(sprintf("smoke-r OK: cmdstan %s, rhat %.5f < 1.01, bam converged (%.1f s)\n",
            cmdstan_ver, rhat, total))
