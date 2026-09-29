#!/usr/bin/env Rscript
# R/ch2/03_prior_predictive.R - SOP step W4.7, prior predictive checks for M1. Gate MT-01,
# Chapter 2 half.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch2/03_prior_predictive.R            sample, write out/ch2/log/prior_predictive.json
#   Rscript R/ch2/03_prior_predictive.R --check    sample again, compare with the file, write nothing
#   Rscript R/ch2/03_prior_predictive.R --derive   derive INTERCEPT_SD, write out/ch2/log/intercept_scale.json
#
# THE SOP TEXT, VERBATIM (W4.7):
#   **W4.7 Prior predictive.** 1,000 draws, `sample_prior = "only"`. Gates: the league
#   overturn rate has a 95% interval covering [0.10, 0.90] with median in [0.35, 0.65];
#   the between-challenger SD of player overturn rates has a 90th percentile below 0.30
#   on the probability scale (`exponential(4)` on `sd` implies a prior mean of 0.25
#   probit, about 10 pp at p = 0.5, and a 90th percentile of 0.576 probit, about 23 pp).
# THE GATE, VERBATIM (section 6, MT-01):
#   MT-01 prior predictive (Ch1: implied shadow-zone called-strike rate in [0.10, 0.90]
#   for >=95% of draws, implied between-umpire SD of the top-edge shift < 3.0 in for
#   >=99%; Ch2: the two gates in W4.7, on the probit scale).
# This script owns the Chapter 2 half of MT-01 only. The Chapter 1 half is not here.
#
# THE MODEL. M1 exactly as SOP W4.10 writes it: the formula, the three priors, the
# seed 20260922. The response is the one change, and it is described under THE OUTCOME.
#
#   overturned ~ 1 + role + balls + strikes + inning_band + leverage_tercile +
#     tokens_own + tokens_opp +
#     (1 | challenger_id) + (1 | opponent_id) + (1 | pitcher_id) +
#     (1 | ump_id) + (1 | team_id)
#   prior(normal(0, 1.5), class = "Intercept"), prior(normal(0, 1), class = "b"),
#   prior(exponential(4), class = "sd")
# The Intercept prior is the one departure: normal(0, INTERCEPT_SD), see THE RULE below.
#
# TWO LINKS, BOTH GATED. The SOP disagrees with itself on the link. W4.10, D-30, D-55 and
# CH2-H2a put M1 on the logit link (D-55 moves M2 to probit and keeps M1 on logit). W4.7's
# parenthetical and MT-01 say "on the probit scale". So the script samples the prior on both
# links, with everything else identical, and both arms' two gates set the verdict:
#   arm "probit"  the scale MT-01 names;
#   arm "logit"   the link W4.10 will fit.
# THE RULE, AND ITS HISTORY. The rule written before any draw required both gates in both arms.
# The first run, 2026-09-25, gave the logit arm a gate 1 interval of [0.1204, 0.8757] under the
# SOP's normal(0, 1.5) Intercept prior, short of [0.10, 0.90] at both tails. That day the verdict
# was narrowed to the probit arm after the draws were seen (D-P4-15). The narrowing is undone:
# both arms gate again, and M1's Intercept prior is widened to INTERCEPT_SD below, derived by
# `--derive` before the gated run. The SOP prior is sampled as the sensitivity arm
# SENS-M1-INTERCEPT-SOP and reported, not gated (logs/decisions-pending/stats.md).
#
# THE TWO GATED QUANTITIES, DEFINED BEFORE ANY DRAW. Per prior draw d:
#   league overturn rate   L_d = mean over the N challenges of y_rep[d, i], where y_rep
#                          is the prior predictive outcome (brms::posterior_predict on
#                          the prior-only fit). The mean of the expected probability,
#                          posterior_epred, is reported beside it and not gated.
#   between-challenger SD  S_d = SD over the challengers j of inv_link(Intercept_d +
#                          r_challenger[d, j]): each player's overturn rate on the
#                          probability scale at the league-average linear predictor,
#                          every other term at its mean. This is the quantity the SOP's
#                          parenthetical describes (the challenger sd prior, read on the
#                          probability scale at p = 0.5). Intercept is brms's centred
#                          intercept, the linear predictor at the covariate means.
#   Gate 1  quantile(L, 0.025) <= 0.10, quantile(L, 0.975) >= 0.90 (the central 95%
#           interval covers [0.10, 0.90]) and quantile(L, 0.5) in [0.35, 0.65].
#   Gate 2  quantile(S, 0.90) < 0.30.
# Quantiles are R's default, type 7. Two wider readings of S are reported and not gated:
#   S_full   SD over challengers of each challenger's mean expected probability over
#            their own challenges, every term included (role, count, tokens, the other
#            four group effects);
#   S_raw20  SD of the raw prior-predictive rate over challengers with >= 20 challenges,
#            binomial noise included.
#
# THE DESIGN. One row per MLB 2026 open-set challenge from data/interim/ch2/challenges.parquet
# (W4.5), N = 10,167. The columns M1 names come from:
#   role, balls, strikes, challenger_id, opponent_id, pitcher_id   the W4.5 frame
#   team_id           challenger_team_id from the W4.5 frame
#   inning_band       from inning: 1-3, 4-6, 7-8, 9+, the competitor's card bands
#                     (fixtures/prior_art/uiloi/tier1_card_2026.csv, inn_band)
#   tokens_own, tokens_opp
#                     the warehouse view v_opportunity_open, open rows only, joined on
#                     (game_pk, at_bat_number, pitch_number) and the challenger's side
#   ump_id            hp_umpire_id in the warehouse view v_umpire_game_open (D-P4-45),
#                     open rows only
#   leverage_tercile  NOT BUILT YET. The tercile needs W5's win-probability surface. The
#                     design carries a placeholder: balanced thirds (low, mid, high) by a
#                     permutation seeded at 20260922. The prior predictive depends on this
#                     column only through its marginal distribution in the design, since
#                     every b has the same independent prior. A tercile is balanced by
#                     definition over its reference population; among challenges the real
#                     split will lean to the high tercile. Recorded in the output.
# balls, strikes, tokens_own and tokens_opp enter as numbers, as the SOP formula writes
# them; role, inning_band and leverage_tercile are factors with treatment contrasts.
#
# THE OUTCOME IS NEVER READ. The frame is read with an explicit column list that holds no
# column in the file's w45_m1_excluded metadata and not overturned, and the script asserts
# it. brms requires a response column, so the design carries overturned = 0 on every row
# as a placeholder. With sample_prior = "only" brms drops the likelihood, so the draws are
# the prior and the placeholder cannot move them. No fit of any kind is made: there is no
# likelihood, no provenance.json and no model cache. The Stan CSV files and the compiled
# model go to a temporary directory that is deleted at exit.
#
# SAMPLING. brms 2.23.0 on cmdstanr, 4 chains x 500 iterations with 250 warmup = 1,000
# prior draws, seed 20260922. posterior_predict runs after set.seed(20260922).
#
# CROSS-CHECK. The same priors are also drawn by direct Monte Carlo in R, 4,000 i.i.d.
# draws on the same design matrix brms builds (make_standata, centred), and the league
# rate and S quantiles of the two routes are compared. --check fails if any compared
# quantile differs by more than 0.04. This catches a coding error in either route.
#
# WHAT IT WRITES. out/ch2/log/prior_predictive.json, a list of one record (the W2.21 export
# gate reads a json file under out/ only as a list of records): the SOP text, the rule and its
# history, the design summary, the gated arms, per arm the quantiles, the gates, the sampler
# diagnostics, the cross-check, the sensitivity arms and finding SENS-M1-INTERCEPT-SOP, the
# Intercept derivation, and the per-draw values of the two gated quantities (so a verifier can
# recompute every quantile without R). --derive writes out/ch2/log/intercept_scale.json, a
# list of records, one per link and candidate scale. --check writes nothing under the repository.
#
# Exit 0 when every check passes and both gates pass in both arms, 1 when any of those fails,
# 2 on a usage error. The sensitivity arm's gates never change the exit code.

options(warn = 1, digits = 12)
t_start <- Sys.time()

args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1 || (length(args) == 1 && !args %in% c("--check", "--derive"))) {
  cat("usage: Rscript R/ch2/03_prior_predictive.R [--check | --derive]\n", file = stderr())
  quit(status = 2)
}
CHECK_ONLY <- identical(args, "--check")
DERIVE     <- identical(args, "--derive")

args_all <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args_all, value = TRUE)
SCRIPT <- if (length(file_arg) == 1) normalizePath(sub("^--file=", "", file_arg)) else
  normalizePath("R/ch2/03_prior_predictive.R")

suppressPackageStartupMessages({
  library(brms)
  library(cmdstanr)
  library(posterior)
  library(Matrix)
})

FRAME    <- "data/interim/ch2/challenges.parquet"
# The warehouse path is minted once, in src/absump/paths.py, and read from there
# relative to the repository root this script runs from.
duckdb_from_python <- function() {
  code <- "import os; from absump.paths import DUCKDB_PATH; print(os.path.relpath(DUCKDB_PATH))"
  out <- suppressWarnings(system2("uv", c("run", "--locked", "python", "-c", shQuote(code)),
                                  stdout = TRUE, stderr = TRUE))
  status <- attr(out, "status")
  if (is.null(status)) status <- 0L
  if (status != 0L || length(out) == 0L) {
    stop("could not read the warehouse path from absump.paths (exit ", status, "): ",
         paste(out, collapse = " "), call. = FALSE)
  }
  trimws(out[length(out)])
}
DUCKDB   <- duckdb_from_python()
OUT_JSON <- "out/ch2/log/prior_predictive.json"
SEED     <- 20260922L
N_EXPECT <- 10167L
CHAINS   <- 4L
ITER     <- 500L
WARMUP   <- 250L
N_MC     <- 4000L
MC_TOL   <- 0.04
LINKS    <- c("probit", "logit")
GATED    <- LINKS                # both arms gate: the scale MT-01 names and the link W4.10 fits
# M1's Intercept prior. SOP W4.10 writes normal(0, 1.5) on the centred Intercept. On the logit
# link, the one W4.10 fits M1 on, that prior's league-rate 95% interval was [0.1204, 0.8757] on
# 2026-09-25, short of [0.10, 0.90] at both tails. INTERCEPT_SD is the smallest multiple of 0.05
# at which a DERIVE_DRAWS-draw direct Monte Carlo of M1's prior clears both W4.7 gates on both
# links, each gated quantile inside its bound by two Monte Carlo standard errors of the gate's own
# 1,000-draw quantile, so that the 1,000-draw gate reads the prior and not Monte Carlo noise.
# `--derive` computes it and writes out/ch2/log/intercept_scale.json. The SOP's normal(0, 1.5) is
# the pre-registered sensitivity arm SENS-M1-INTERCEPT-SOP: sampled and reported, never gated.
INTERCEPT_SD     <- 1.9
INTERCEPT_SD_SOP <- 1.5
SENS_ID  <- "SENS-M1-INTERCEPT-SOP"
DERIVE_JSON  <- "out/ch2/log/intercept_scale.json"
DERIVE_DRAWS <- 40000L
DERIVE_BOOT  <- 2000L
DERIVE_GRID  <- round(seq(1.50, 2.20, by = 0.05), 2)
DIGITS   <- 6L

failures <- character(0)
check <- function(label, ok, detail = "") {
  ok <- isTRUE(ok)
  cat(sprintf("%s %s%s\n", if (ok) "PASS" else "FAIL", label,
              if (nzchar(detail)) paste0(" -- ", detail) else ""))
  if (!ok) failures <<- c(failures, label)
  invisible(ok)
}
record <- function(label, value) cat(sprintf("RECORD %s: %s\n", label, value))
fmt <- function(x, d = 4) formatC(x, format = "f", digits = d)
finish <- function() {
  cat(sprintf("W4.7 %s: %d FAIL, wall %.1f s\n", if (CHECK_ONLY) "check" else "build",
              length(failures), as.numeric(difftime(Sys.time(), t_start, units = "secs"))))
  if (length(failures)) {
    cat("FAILED:", paste(failures, collapse = " | "), "\n")
    quit(status = 1)
  }
  quit(status = 0)
}

check("run from the repository root", file.exists("R/ch2/03_prior_predictive.R"), getwd())
for (f in c(FRAME, DUCKDB)) check("input present", file.exists(f), f)
if (length(failures)) finish()

tmp <- file.path(tempdir(), "w47_prior_only")
dir.create(tmp, showWarnings = FALSE, recursive = TRUE)
options(cmdstanr_write_stan_file_dir = tmp)
on.exit(unlink(tmp, recursive = TRUE), add = TRUE)

## --- 1. the design, ex-ante columns only -------------------------------------------------

meta <- arrow::read_parquet(FRAME, as_data_frame = FALSE)$metadata
excluded <- trimws(strsplit(meta$w45_m1_excluded, ",")[[1]])
check("frame carries the w45_m1_excluded list", length(excluded) >= 10,
      paste(excluded, collapse = ","))
READ_COLS <- c("level", "season", "game_pk", "at_bat_number", "pitch_number",
               "challenger_id", "role", "challenger_team_id", "opponent_id", "pitcher_id",
               "inning", "balls", "strikes")
check("the read holds no excluded column and not the outcome",
      !any(READ_COLS %in% c(excluded, "overturned")),
      paste(intersect(READ_COLS, c(excluded, "overturned")), collapse = ","))
fr <- as.data.frame(arrow::read_parquet(FRAME, col_select = dplyr::all_of(READ_COLS)))
fr <- fr[fr$level == "mlb" & fr$season == 2026L, , drop = FALSE]
check("MLB 2026 open challenges", nrow(fr) == N_EXPECT, sprintf("%d rows", nrow(fr)))
fr$side <- ifelse(fr$role == "batter", "bat", "fld")

con <- suppressMessages(DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:"))
attached <- FALSE
for (attempt in 1:30) {
  attached <- tryCatch({
    DBI::dbExecute(con, sprintf("ATTACH %s AS abs (READ_ONLY)", DBI::dbQuoteString(con, DUCKDB)))
    TRUE
  }, error = function(e) {
    cat(sprintf("RECORD warehouse attach attempt %d failed: %s\n", attempt, conditionMessage(e)))
    FALSE
  })
  if (attached) break
  Sys.sleep(2)
}
check("warehouse attached read-only", attached, DUCKDB)
if (!attached) finish()
duckdb::duckdb_register(con, "fr", fr[, c("game_pk", "at_bat_number", "pitch_number", "side")])
tok <- DBI::dbGetQuery(con, "
  SELECT f.game_pk, f.at_bat_number, f.pitch_number, f.side,
         o.tokens_own, o.tokens_opp, u.hp_umpire_id
  FROM fr AS f
  LEFT JOIN (SELECT game_pk, at_bat_number, pitch_number, acting_side, tokens_own, tokens_opp
             FROM abs.main_marts.v_opportunity_open WHERE analysis_set = 'open') AS o
    ON o.game_pk = f.game_pk AND o.at_bat_number = f.at_bat_number
   AND o.pitch_number = f.pitch_number AND o.acting_side = f.side
  LEFT JOIN (SELECT game_pk, hp_umpire_id FROM abs.main_marts.v_umpire_game_open
             WHERE analysis_set = 'open' AND level = 'mlb') AS u
    ON u.game_pk = f.game_pk")
DBI::dbDisconnect(con, shutdown = TRUE)
check("token and umpire join is one row per challenge", nrow(tok) == nrow(fr),
      sprintf("%d rows", nrow(tok)))
key_f <- paste(fr$game_pk, fr$at_bat_number, fr$pitch_number, fr$side)
key_t <- paste(tok$game_pk, tok$at_bat_number, tok$pitch_number, tok$side)
tok <- tok[match(key_f, key_t), ]
check("tokens found for every challenge", !anyNA(tok$tokens_own) && !anyNA(tok$tokens_opp),
      sprintf("%d missing", sum(is.na(tok$tokens_own) | is.na(tok$tokens_opp))))
check("plate umpire found for every challenge", !anyNA(tok$hp_umpire_id),
      sprintf("%d missing", sum(is.na(tok$hp_umpire_id))))

set.seed(SEED)
lev_placeholder <- sample(rep(c("low", "mid", "high"), length.out = nrow(fr)))
d <- data.frame(
  overturned       = 0L,
  role             = factor(fr$role, levels = c("batter", "catcher", "pitcher")),
  balls            = as.integer(fr$balls),
  strikes          = as.integer(fr$strikes),
  inning_band      = factor(cut(fr$inning, c(0, 3, 6, 8, Inf), labels = c("1-3", "4-6", "7-8", "9+"))),
  leverage_tercile = factor(lev_placeholder, levels = c("low", "mid", "high")),
  tokens_own       = as.integer(tok$tokens_own),
  tokens_opp       = as.integer(tok$tokens_opp),
  challenger_id    = factor(fr$challenger_id),
  opponent_id      = factor(fr$opponent_id),
  pitcher_id       = factor(fr$pitcher_id),
  ump_id           = factor(tok$hp_umpire_id),
  team_id          = factor(fr$challenger_team_id)
)
check("no missing value in the design", !anyNA(d), "")
n_levels <- sapply(d[, c("challenger_id", "opponent_id", "pitcher_id", "ump_id", "team_id")], nlevels)
record("design", sprintf("N %d; levels %s", nrow(d),
                         paste(names(n_levels), n_levels, sep = " ", collapse = ", ")))
n_ch <- table(d$challenger_id)
record("challengers with >= 20 challenges", sum(n_ch >= 20))

f1 <- brms::bf(
  overturned ~ 1 + role + balls + strikes + inning_band + leverage_tercile +
    tokens_own + tokens_opp +
    (1 | challenger_id) + (1 | opponent_id) + (1 | pitcher_id) +
    (1 | ump_id) + (1 | team_id)
)
prior_of <- function(isd) c(brms::set_prior(sprintf("normal(0, %s)", format(isd)), class = "Intercept"),
                            prior(normal(0, 1),   class = "b"),
                            prior(exponential(4), class = "sd"))
pr <- prior_of(INTERCEPT_SD)

q_of <- function(x, p) unname(stats::quantile(x, p, type = 7))
summ <- function(x) {
  list(mean = round(mean(x), DIGITS), q025 = round(q_of(x, 0.025), DIGITS),
       q05 = round(q_of(x, 0.05), DIGITS), q10 = round(q_of(x, 0.10), DIGITS),
       q50 = round(q_of(x, 0.50), DIGITS), q90 = round(q_of(x, 0.90), DIGITS),
       q95 = round(q_of(x, 0.95), DIGITS), q975 = round(q_of(x, 0.975), DIGITS))
}
gates_of <- function(L, S) {
  lo <- q_of(L, 0.025); hi <- q_of(L, 0.975); md <- q_of(L, 0.5); s90 <- q_of(S, 0.90)
  g1 <- lo <= 0.10 && hi >= 0.90 && md >= 0.35 && md <= 0.65
  g2 <- s90 < 0.30
  list(gate1_league_rate = list(
         rule = "quantile(L, 0.025) <= 0.10 and quantile(L, 0.975) >= 0.90 and 0.35 <= quantile(L, 0.5) <= 0.65",
         interval95 = round(c(lo, hi), DIGITS), median = round(md, DIGITS),
         pass = g1),
       gate2_between_challenger_sd = list(
         rule = "quantile(S, 0.90) < 0.30 on the probability scale",
         q90 = round(s90, DIGITS), pass = g2))
}

## --- the Intercept scale, derived (--derive) ------------------------------------------------
# For each candidate scale on DERIVE_GRID and each link: DERIVE_DRAWS i.i.d. draws of M1's prior
# on the centred design brms builds (the route the cross-check below uses), the W4.7 quantiles of
# L and S, and each quantile's Monte Carlo standard error at the gate's own 1,000 draws, from
# DERIVE_BOOT bootstrap samples of 1,000. The Intercept draw is scaled per candidate, so every
# candidate reads the same b, sd and group draws. A scale clears when, on both links,
# q025(L) + 2 se <= 0.10, q975(L) - 2 se >= 0.90, the median sits 2 se inside [0.35, 0.65] and
# q90(S) + 2 se < 0.30. INTERCEPT_SD is the smallest scale that clears.
derive_intercept_sd <- function() {
  t0 <- Sys.time()
  gvars <- c("challenger_id", "opponent_id", "pitcher_id", "ump_id", "team_id")
  gidx <- lapply(gvars, function(g) as.integer(d[[g]]))
  glev <- sapply(gvars, function(g) nlevels(d[[g]]))
  rows <- list()
  for (link in LINKS) {
    inv <- if (link == "probit") stats::pnorm else stats::plogis
    sdat <- brms::make_standata(f1, data = d, family = brms::bernoulli(link = link),
                                prior = prior_of(INTERCEPT_SD_SOP), sample_prior = "only")
    X <- sdat$X[, colnames(sdat$X) != "Intercept", drop = FALSE]
    Xc <- sweep(X, 2, colMeans(X))
    set.seed(SEED)
    L <- matrix(NA_real_, DERIVE_DRAWS, length(DERIVE_GRID)); S <- L
    for (s in seq_len(DERIVE_DRAWS)) {
      za <- stats::rnorm(1)
      b  <- stats::rnorm(ncol(Xc), 0, 1)
      sg <- stats::rexp(length(gvars), 4)
      eta0 <- as.vector(Xc %*% b)
      r_ch <- NULL
      for (k in seq_along(gvars)) {
        r <- stats::rnorm(glev[k], 0, sg[k])
        if (k == 1) r_ch <- r
        eta0 <- eta0 + r[gidx[[k]]]
      }
      u <- stats::runif(length(eta0))
      for (j in seq_along(DERIVE_GRID)) {
        a <- DERIVE_GRID[j] * za
        L[s, j] <- mean(u < inv(a + eta0))
        S[s, j] <- stats::sd(inv(a + r_ch))
      }
    }
    set.seed(SEED + 1L)
    bi <- matrix(sample.int(DERIVE_DRAWS, DERIVE_BOOT * CHAINS * (ITER - WARMUP), replace = TRUE),
                 nrow = CHAINS * (ITER - WARMUP))
    for (j in seq_along(DERIVE_GRID)) {
      qs <- function(ix) c(q_of(L[ix, j], 0.025), q_of(L[ix, j], 0.5), q_of(L[ix, j], 0.975), q_of(S[ix, j], 0.9))
      q <- qs(seq_len(DERIVE_DRAWS))
      se <- apply(apply(bi, 2, qs), 1, stats::sd)
      raw <- q[1] <= 0.10 && q[3] >= 0.90 && q[2] >= 0.35 && q[2] <= 0.65 && q[4] < 0.30
      ok <- q[1] + 2 * se[1] <= 0.10 && q[3] - 2 * se[3] >= 0.90 && q[2] - 2 * se[2] >= 0.35 &&
        q[2] + 2 * se[2] <= 0.65 && q[4] + 2 * se[4] < 0.30
      rows[[length(rows) + 1L]] <- list(
        link = link, intercept_sd = DERIVE_GRID[j], draws = DERIVE_DRAWS,
        league_rate_q025 = round(q[1], DIGITS), league_rate_q50 = round(q[2], DIGITS),
        league_rate_q975 = round(q[3], DIGITS), between_sd_q90 = round(q[4], DIGITS),
        se1000_q025 = round(se[1], DIGITS), se1000_q50 = round(se[2], DIGITS),
        se1000_q975 = round(se[3], DIGITS), se1000_between_sd_q90 = round(se[4], DIGITS),
        gates_hold = raw, gates_hold_by_two_se = ok)
      cat(sprintf("DERIVE %-6s Intercept normal(0, %.2f): L q025 %.4f (se %.4f) q975 %.4f (se %.4f) median %.4f, S q90 %.4f; gates %s, by 2 se %s\n",
                  link, DERIVE_GRID[j], q[1], se[1], q[3], se[3], q[2], q[4], raw, ok))
    }
  }
  clears <- vapply(DERIVE_GRID, function(g) all(vapply(rows, function(r)
    r$intercept_sd != g || isTRUE(r$gates_hold_by_two_se), TRUE)), TRUE)
  chosen <- if (any(clears)) min(DERIVE_GRID[clears]) else NA_real_
  rows <- lapply(rows, function(r) c(r, list(chosen = isTRUE(all.equal(r$intercept_sd, chosen)),
                                              seed = SEED, rule = paste(
    "smallest multiple of 0.05 at which both links clear both W4.7 gates with each gated",
    "quantile inside its bound by two Monte Carlo standard errors of a 1,000-draw quantile"))))
  dir.create(dirname(DERIVE_JSON), showWarnings = FALSE, recursive = TRUE)
  jsonlite::write_json(rows, DERIVE_JSON, auto_unbox = TRUE, digits = NA, pretty = TRUE)
  record("derived Intercept scale", sprintf("normal(0, %s); INTERCEPT_SD in this script is %s; %s, %.0f s",
         format(chosen), format(INTERCEPT_SD), DERIVE_JSON, as.numeric(difftime(Sys.time(), t0, units = "secs"))))
  check("INTERCEPT_SD equals the derivation", isTRUE(all.equal(chosen, INTERCEPT_SD)),
        sprintf("derived %s, script %s", format(chosen), format(INTERCEPT_SD)))
  finish()
}

## --- 2. the prior, sampled by brms, per link and per Intercept prior ----------------------

# One arm: M1's prior with Intercept ~ normal(0, isd), sampled on one link. A gated arm's two
# gates are checks; an ungated arm (the sensitivity arm) records them.
sample_arm <- function(link, isd, gated) {
  lab <- if (gated) link else sprintf("%s, Intercept normal(0, %s)", link, format(isd))
  pr_arm <- prior_of(isd)
  t0 <- Sys.time()
  inv <- if (link == "probit") stats::pnorm else stats::plogis
  fam <- brms::bernoulli(link = link)
  fit <- suppressMessages(brms::brm(
    f1, data = d, family = fam, prior = pr_arm, sample_prior = "only",
    chains = CHAINS, iter = ITER, warmup = WARMUP, cores = CHAINS, seed = SEED,
    backend = "cmdstanr", output_dir = tmp, refresh = 0, silent = 2
  ))
  t_fit <- as.numeric(difftime(Sys.time(), t0, units = "secs"))
  dr <- posterior::as_draws_df(fit)
  n_draws <- nrow(dr)
  check(sprintf("[%s] 1,000 prior draws", lab), n_draws == 1000L, sprintf("%d", n_draws))

  set.seed(SEED)
  yrep <- brms::posterior_predict(fit)
  ep   <- brms::posterior_epred(fit)
  L      <- rowMeans(yrep)
  L_epr  <- rowMeans(ep)

  rch <- as.matrix(posterior::subset_draws(posterior::as_draws_matrix(fit),
                                           variable = "^r_challenger_id\\[", regex = TRUE))
  check(sprintf("[%s] one challenger effect per level", lab),
        ncol(rch) == nlevels(d$challenger_id), sprintf("%d columns", ncol(rch)))
  icpt <- dr$Intercept
  S <- apply(inv(sweep(rch, 1, icpt, "+")), 1, stats::sd)

  W <- Matrix::sparseMatrix(i = seq_len(nrow(d)), j = as.integer(d$challenger_id),
                            x = 1 / as.numeric(n_ch[as.integer(d$challenger_id)]),
                            dims = c(nrow(d), nlevels(d$challenger_id)))
  S_full <- apply(as.matrix(ep %*% W), 1, stats::sd)
  keep20 <- which(as.numeric(n_ch) >= 20)
  S_raw20 <- apply(as.matrix(yrep %*% W)[, keep20, drop = FALSE], 1, stats::sd)

  sdv <- grep("^sd_", names(dr), value = TRUE)
  diag_vars <- c("Intercept", grep("^b_", names(dr), value = TRUE), sdv)
  sm <- posterior::summarise_draws(posterior::subset_draws(posterior::as_draws_array(fit),
                                                           variable = diag_vars),
                                   "rhat", "ess_bulk", "ess_tail")
  np <- brms::nuts_params(fit)
  n_div <- sum(np$Value[np$Parameter == "divergent__"])
  n_td  <- sum(np$Value[np$Parameter == "treedepth__"] >= 10)

  ## --- direct Monte Carlo on the same centred design -------------------------------------
  sdat <- brms::make_standata(f1, data = d, family = fam, prior = pr_arm, sample_prior = "only")
  X <- sdat$X[, colnames(sdat$X) != "Intercept", drop = FALSE]
  Xc <- sweep(X, 2, colMeans(X))
  set.seed(SEED)
  mc_L <- numeric(N_MC); mc_S <- numeric(N_MC)
  gvars <- c("challenger_id", "opponent_id", "pitcher_id", "ump_id", "team_id")
  gidx <- lapply(gvars, function(g) as.integer(d[[g]]))
  glev <- sapply(gvars, function(g) nlevels(d[[g]]))
  for (s in seq_len(N_MC)) {
    a  <- stats::rnorm(1, 0, isd)
    b  <- stats::rnorm(ncol(Xc), 0, 1)
    sg <- stats::rexp(length(gvars), 4)
    eta <- a + as.vector(Xc %*% b)
    r_ch <- NULL
    for (k in seq_along(gvars)) {
      r <- stats::rnorm(glev[k], 0, sg[k])
      if (k == 1) r_ch <- r
      eta <- eta + r[gidx[[k]]]
    }
    mc_L[s] <- mean(inv(eta))
    mc_S[s] <- stats::sd(inv(a + r_ch))
  }
  cmp <- list(
    league_rate_expected_q025 = c(brms = q_of(L_epr, 0.025), mc = q_of(mc_L, 0.025)),
    league_rate_expected_q50  = c(brms = q_of(L_epr, 0.5),   mc = q_of(mc_L, 0.5)),
    league_rate_expected_q975 = c(brms = q_of(L_epr, 0.975), mc = q_of(mc_L, 0.975)),
    between_challenger_sd_q50 = c(brms = q_of(S, 0.5),       mc = q_of(mc_S, 0.5)),
    between_challenger_sd_q90 = c(brms = q_of(S, 0.9),       mc = q_of(mc_S, 0.9))
  )
  cmp_out <- lapply(cmp, function(v) list(brms = round(v[["brms"]], DIGITS), mc = round(v[["mc"]], DIGITS),
                                          abs_diff = round(abs(v[["brms"]] - v[["mc"]]), DIGITS)))
  max_diff <- max(sapply(cmp, function(v) abs(v[["brms"]] - v[["mc"]])))
  check(sprintf("[%s] brms and direct Monte Carlo agree within %.2f", lab, MC_TOL),
        max_diff <= MC_TOL, sprintf("largest difference %s", fmt(max_diff)))

  sd_ch <- dr[["sd_challenger_id__Intercept"]]
  g <- gates_of(L, S)
  arm <- list(
    link = link,
    intercept_prior = sprintf("normal(0, %s)", format(isd)),
    gated = gated,
    draws = n_draws,
    league_rate = summ(L),
    league_rate_expected = summ(L_epr),
    between_challenger_sd = summ(S),
    between_challenger_sd_full = summ(S_full),
    between_challenger_sd_raw20 = summ(S_raw20),
    sd_challenger_link_scale = summ(sd_ch),
    gates = g,
    pass = g$gate1_league_rate$pass && g$gate2_between_challenger_sd$pass,
    descriptive_not_gated = list(
      between_challenger_sd_full_q90_below_0.30 = q_of(S_full, 0.9) < 0.30,
      between_challenger_sd_raw20_q90_below_0.30 = q_of(S_raw20, 0.9) < 0.30),
    sampler = list(
      chains = CHAINS, iter = ITER, warmup = WARMUP, seed = SEED,
      divergent = as.integer(n_div), max_treedepth_hits = as.integer(n_td),
      max_rhat = round(max(sm$rhat, na.rm = TRUE), DIGITS),
      min_ess_bulk = round(min(sm$ess_bulk, na.rm = TRUE), 1),
      min_ess_tail = round(min(sm$ess_tail, na.rm = TRUE), 1),
      variables = length(diag_vars)),
    cross_check_direct_mc = c(list(draws = N_MC, tolerance = MC_TOL), cmp_out),
    per_draw = list(
      n_overturned = as.integer(rowSums(yrep)),
      between_challenger_sd = round(S, DIGITS),
      sd_challenger = round(sd_ch, DIGITS))
  )
  record(sprintf("[%s] league overturn rate", lab),
         sprintf("median %s, 95%% interval [%s, %s]", fmt(q_of(L, .5)), fmt(q_of(L, .025)), fmt(q_of(L, .975))))
  record(sprintf("[%s] between-challenger SD", lab),
         sprintf("median %s, q90 %s (full q90 %s, raw20 q90 %s)", fmt(q_of(S, .5)), fmt(q_of(S, .9)),
                 fmt(q_of(S_full, .9)), fmt(q_of(S_raw20, .9))))
  record(sprintf("[%s] sd_challenger prior draws", lab),
         sprintf("mean %s, q90 %s", fmt(mean(sd_ch)), fmt(q_of(sd_ch, .9))))
  record(sprintf("[%s] sampler", lab),
         sprintf("%d divergent, %d treedepth hits, max R-hat %s, min ess_bulk %.0f, min ess_tail %.0f, %.1f s",
                 n_div, n_td, fmt(max(sm$rhat, na.rm = TRUE)), min(sm$ess_bulk, na.rm = TRUE),
                 min(sm$ess_tail, na.rm = TRUE), t_fit))
  g1_detail <- sprintf("95%% interval [%s, %s] must cover [0.10, 0.90]; median %s must be in [0.35, 0.65]",
                       fmt(q_of(L, .025)), fmt(q_of(L, .975)), fmt(q_of(L, .5)))
  g2_detail <- sprintf("q90 %s must be below 0.30", fmt(q_of(S, .9)))
  if (gated) {
    check(sprintf("[%s] gate 1, league overturn rate", lab), g$gate1_league_rate$pass, g1_detail)
    check(sprintf("[%s] gate 2, between-challenger SD", lab), g$gate2_between_challenger_sd$pass, g2_detail)
  } else {
    record(sprintf("%s [%s] gate 1, not gated", SENS_ID, lab),
           sprintf("%s -- %s", if (g$gate1_league_rate$pass) "holds" else "does not hold", g1_detail))
    record(sprintf("%s [%s] gate 2, not gated", SENS_ID, lab),
           sprintf("%s -- %s", if (g$gate2_between_challenger_sd$pass) "holds" else "does not hold", g2_detail))
  }
  check(sprintf("[%s] sampler, 0 divergent transitions", lab), n_div == 0, sprintf("%d", n_div))
  rm(fit, yrep, ep); gc(verbose = FALSE)
  arm
}

if (DERIVE) derive_intercept_sd()
arms <- list()
for (link in LINKS) arms[[link]] <- sample_arm(link, INTERCEPT_SD, TRUE)
sens_arms <- list()
for (link in LINKS) sens_arms[[link]] <- sample_arm(link, INTERCEPT_SD_SOP, FALSE)

## --- 3. the record -------------------------------------------------------------------------

analytic <- list(
  sd_prior = "exponential(4)",
  mean = 0.25, q90 = round(log(10) / 4, DIGITS),
  probit_pp_at_p05 = list(mean = round(0.25 * stats::dnorm(0), DIGITS),
                          q90 = round(log(10) / 4 * stats::dnorm(0), DIGITS)),
  logit_pp_at_p05 = list(mean = round(0.25 * 0.25, DIGITS), q90 = round(log(10) / 4 * 0.25, DIGITS)),
  note = "Delta-method slope of the inverse link at p = 0.5: dnorm(0) = 0.3989 for probit, 0.25 for logit."
)
verdict <- all(vapply(arms[GATED], function(a) isTRUE(a$pass), TRUE))
sensitivity <- lapply(LINKS, function(link) {
  a <- sens_arms[[link]]
  g1 <- a$gates$gate1_league_rate
  g2 <- a$gates$gate2_between_challenger_sd
  list(
    id = SENS_ID,
    arm = link,
    intercept_prior = a$intercept_prior,
    what = paste("M1's prior with the SOP W4.10 Intercept prior, read through the same two W4.7",
                 "gates on this link. The pre-registered sensitivity arm: reported, not gated."),
    gate1_interval95 = g1$interval95,
    gate1_median = g1$median,
    gate1_holds = g1$pass,
    gate1_shortfall_lower = round(max(0, g1$interval95[1] - 0.10), DIGITS),
    gate1_shortfall_upper = round(max(0, 0.90 - g1$interval95[2]), DIGITS),
    gate2_q90 = g2$q90,
    gate2_holds = g2$pass,
    deviation = "logs/decisions-pending/stats.md")
})
for (f in sensitivity) record(sprintf("%s %s gate 1 interval", SENS_ID, f$arm),
  sprintf("[%s, %s], short of [0.10, 0.90] by %s at the lower tail and %s at the upper tail",
          fmt(f$gate1_interval95[1]), fmt(f$gate1_interval95[2]),
          fmt(f$gate1_shortfall_lower), fmt(f$gate1_shortfall_upper)))
derivation <- if (file.exists(DERIVE_JSON)) {
  dj <- jsonlite::fromJSON(DERIVE_JSON, simplifyVector = FALSE)
  list(source = DERIVE_JSON, rule = dj[[1]]$rule, draws = dj[[1]]$draws,
       chosen = unique(vapply(Filter(function(r) isTRUE(r$chosen), dj), function(r) r$intercept_sd, 0)),
       rows = lapply(dj, function(r) r[setdiff(names(r), c("rule", "seed", "draws"))]))
} else list(source = DERIVE_JSON, note = "absent: run --derive")
check("INTERCEPT_SD is the derived scale", identical(derivation$chosen, INTERCEPT_SD),
      sprintf("%s in %s, %s here", paste(derivation$chosen, collapse = " "), DERIVE_JSON, format(INTERCEPT_SD)))
n_b_columns <- sum(colnames(brms::make_standata(f1, data = d, family = brms::bernoulli("logit"), prior = pr,
                                                 sample_prior = "only")$X) != "Intercept")
res <- list(
  step = "W4.7",
  gate = "MT-01, Chapter 2 half",
  sop_text = paste("**W4.7 Prior predictive.** 1,000 draws, `sample_prior = \"only\"`. Gates: the league",
                   "overturn rate has a 95% interval covering [0.10, 0.90] with median in [0.35, 0.65];",
                   "the between-challenger SD of player overturn rates has a 90th percentile below 0.30",
                   "on the probability scale (`exponential(4)` on `sd` implies a prior mean of 0.25",
                   "probit, about 10 pp at p = 0.5, and a 90th percentile of 0.576 probit, about 23 pp)."),
  mt01_text = paste("MT-01 prior predictive (Ch1: implied shadow-zone called-strike rate in [0.10, 0.90]",
                    "for >=95% of draws, implied between-umpire SD of the top-edge shift < 3.0 in for",
                    ">=99%; Ch2: the two gates in W4.7, on the probit scale)."),
  rule = paste("Both gates in both arms set the verdict: the probit arm, the scale MT-01 names, and the",
               "logit arm, the link SOP W4.10 fits, each under M1's pre-registered Intercept prior",
               sprintf("normal(0, %s).", format(INTERCEPT_SD)), "The SOP's normal(0, 1.5) is the sensitivity arm",
               "SENS-M1-INTERCEPT-SOP, reported and not gated. L = mean of the prior predictive outcome",
               "over the N challenges; S = SD over challengers of inv_link(Intercept + r_challenger)."),
  rule_before_draws = paste("Both gates in both arms. Arm probit is the scale MT-01 names; arm logit is the",
                            "link SOP W4.10 fits. Written before any draw."),
  rule_history = c(
    "Before any draw: both gates in both arms, SOP priors.",
    paste("After the first draws (D-P4-15): the verdict narrowed to the probit arm, the logit",
          "arm reported as SENS-W4.7-LOGIT with gate 1 at [0.1204, 0.8757]."),
    paste("Stats lane, before the tag: both arms gate again; M1's Intercept prior widened to",
          sprintf("normal(0, %s)", format(INTERCEPT_SD)), "by the --derive rule; the SOP prior is the",
          "sensitivity arm SENS-M1-INTERCEPT-SOP. logs/decisions-pending/stats.md.")),
  gated_arm = GATED,
  model = list(
    formula = paste("overturned ~ 1 + role + balls + strikes + inning_band + leverage_tercile +",
                    "tokens_own + tokens_opp + (1 | challenger_id) + (1 | opponent_id) +",
                    "(1 | pitcher_id) + (1 | ump_id) + (1 | team_id)"),
    priors = c(sprintf("normal(0, %s) on Intercept (centred)", format(INTERCEPT_SD)), "normal(0, 1) on b",
               "exponential(4) on sd"),
    priors_sensitivity_arm = c(sprintf("normal(0, %s) on Intercept (centred)", format(INTERCEPT_SD_SOP)),
                               "normal(0, 1) on b", "exponential(4) on sd"),
    intercept_derivation = derivation,
    sample_prior = "only", backend = "cmdstanr",
    brms = as.character(utils::packageVersion("brms")),
    cmdstanr = as.character(utils::packageVersion("cmdstanr")),
    cmdstan = cmdstanr::cmdstan_version()),
  design = list(
    source = paste(FRAME, "(W4.5), MLB 2026 open rows; tokens from warehouse view",
                   "v_opportunity_open and plate umpire from v_umpire_game_open, open rows only"),
    n = nrow(d),
    levels = as.list(n_levels),
    n_b_columns = n_b_columns,
    challengers_with_20_or_more = sum(n_ch >= 20),
    role = as.list(table(d$role)),
    inning_band = as.list(table(d$inning_band)),
    tokens_own = as.list(table(d$tokens_own)),
    tokens_opp = as.list(table(d$tokens_opp)),
    outcome_read = FALSE,
    response_placeholder = "overturned = 0 on every row; the likelihood is dropped by sample_prior = \"only\"",
    leverage_tercile_placeholder = paste("Not built until W5's win-probability surface exists. Balanced",
                                         "thirds (low, mid, high) by a permutation seeded at 20260922.")),
  analytic_sd_prior = analytic,
  arms = arms,
  sensitivity_arms = sens_arms,
  sensitivity_findings = sensitivity,
  verdict = if (verdict) "PASS" else "FAIL",
  frame_sha256 = digest::digest(file = FRAME, algo = "sha256"),
  code_sha256 = digest::digest(file = SCRIPT, algo = "sha256"),
  written_madrid = system("TZ=Europe/Madrid date -Iseconds", intern = TRUE),
  wall_s = round(as.numeric(difftime(Sys.time(), t_start, units = "secs")), 1)
)

## --- 4. write, or compare with the file ----------------------------------------------------

strip_volatile <- function(x) {
  x[c("written_madrid", "wall_s")] <- NULL
  x
}
if (CHECK_ONLY) {
  check("prior_predictive.json present", file.exists(OUT_JSON), OUT_JSON)
  if (file.exists(OUT_JSON)) {
    raw <- jsonlite::fromJSON(OUT_JSON, simplifyVector = FALSE)
    one <- is.list(raw) && is.null(names(raw)) && length(raw) == 1L && !is.null(names(raw[[1]]))
    check("the file is a list of one record, as the W2.21 export gate reads json", one,
          sprintf("%s of length %d", if (is.null(names(raw))) "array" else "object", length(raw)))
    old <- if (one) raw[[1]] else raw
    new <- jsonlite::fromJSON(jsonlite::toJSON(res, auto_unbox = TRUE, digits = NA, null = "null"),
                              simplifyVector = FALSE)
    # Flattened field by field, in order. A list of records flattens to repeated names
    # (one per record), so the two sides are compared by position once their names match
    # in order.
    fo <- unlist(strip_volatile(old)); fn <- unlist(strip_volatile(new))
    same_keys <- identical(names(fo), names(fn))
    check("the file and the rerun hold the same fields", same_keys,
          sprintf("%d vs %d", length(fo), length(fn)))
    if (same_keys) {
      num <- suppressWarnings(!is.na(as.numeric(fo)) & !is.na(as.numeric(fn)))
      dn <- abs(as.numeric(fo[num]) - as.numeric(fn[num]))
      bad_num <- names(fo)[num][dn > 1e-6]
      bad_txt <- names(fo)[!num][fo[!num] != fn[!num]]
      check("every number in the file equals the rerun to 1e-6", length(bad_num) == 0,
            paste(utils::head(bad_num, 5), collapse = ", "))
      check("every string in the file equals the rerun", length(bad_txt) == 0,
            paste(utils::head(bad_txt, 5), collapse = ", "))
    }
    check("the file's verdict is PASS", identical(old$verdict, "PASS"), as.character(old$verdict))
  }
} else {
  dir.create(dirname(OUT_JSON), showWarnings = FALSE, recursive = TRUE)
  # a list of one record: tests/unit/test_exports.py reads a .json under out/ only as records
  jsonlite::write_json(list(res), OUT_JSON, auto_unbox = TRUE, digits = NA, pretty = TRUE, null = "null")
  record("wrote", sprintf("%s, %d bytes", OUT_JSON, file.size(OUT_JSON)))
}
check("no provenance.json under out/ch2", length(list.files("out/ch2", "^provenance\\.json$",
                                                            recursive = TRUE)) == 0, "")
record("MT-01 Chapter 2 verdict", res$verdict)
finish()
