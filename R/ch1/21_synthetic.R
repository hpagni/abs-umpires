#!/usr/bin/env Rscript
# R/ch1/21_synthetic.R - SOP step W3.12, synthetic machinery: the D-60 power curve,
# simulation-based calibration of the heterogeneity model, and injected-effect recovery.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/21_synthetic.R --power      (c) the D-60 umpire power curve. Writes
#                                             out/tables/ch1_power_curve.csv and the raw
#                                             per-seed output under out/dev/ch1_synth/power/
#   Rscript R/ch1/21_synthetic.R --sbc        (b) SBC of the stage B2 model, 200 replicates,
#                                             raw ranks under out/dev/ch1_synth/sbc/
#   Rscript R/ch1/21_synthetic.R --recovery [n_inject n_null]
#                                             (a) injected-effect recovery on 2024 pitches,
#                                             raw replicates under out/dev/ch1_synth/recovery/
#   Rscript R/ch1/21_synthetic.R --check      verify. Rebuilds the curve CSV from the raw
#                                             per-seed draws, re-derives the CH1-A6 thresholds,
#                                             compares them with docs/prereg/ch1.md (and
#                                             PREREGISTRATION.md when it exists), re-runs one
#                                             power seed end to end and compares it with the
#                                             stored draws, re-scores the SBC ranks and reports
#                                             the recovery replicates. Writes nothing under
#                                             the repository. Exit 1 on any FAIL.
#   Rscript R/ch1/21_synthetic.R --worker <kind> ...
#                                             one job, started by the modes above.
#
# PART (c), THE D-60 POWER CURVE. The chapter's heterogeneity estimator is SOP W3.18:
#   B1  per umpire-season-edge offset delta, by maximising the binomial likelihood of
#       y_i ~ g_e(d_i - delta) over delta in [-4, 4] in 0.01 in steps, profile SE;
#   B2  brm(delta | se(se_delta, sigma = TRUE) ~ 0 + edge + edge:regime
#           + (1 + regime | umpire_hp_id), SOP priors, 4 chains x 2000, seed 20260922);
#   B3  split-half reliability, each umpire-season's plate games split odd/even by game
#       index, Spearman-Brown corrected, for the level and the response.
# Regime enters B2 as two step contrasts, buf_step = 1 in 2025 and 2026, abs_step = 1 in
# 2026. That is the SOP's edge:regime and (1 + regime | umpire) re-coded so that the
# abs_step slope is the umpire's 2025 -> 2026 response and its SD is tau. The fixed
# effects span the same nine edge x regime means.
#
# The simulation keeps every real shadow-band pitch of 2022-2026 (|d| <= 3.0 in, SOP
# W3.5): its umpire, season, game, edge and d. Only the call is simulated. The script
# reads no call from 2025 or 2026: the design read selects no cs column at all. The link
# g_e and the nuisance variance components are calibrated on 2022-2024 only:
#   g_e      glm(cs ~ ns(d, 6), binomial) per edge on 2022-2024 pitches with |d| <= 8 in
#   nuisance B1 on real 2022-2024 shadow-band pitches, then a brms variance-components
#            fit: umpire level, umpire x edge, umpire x season, residual
# The generating offset of umpire u, season s, edge e is
#   delta = a_u + h_ue + w_us + e_use + b_u 1[s >= 2025] + c_u 1[s = 2026],
# with c_u ~ N(0, tau) the ABS response and b_u ~ N(0, tau) the buffer response. The
# umpire x edge and umpire x season terms are not in B2, so the curve measures the
# estimator as specified against a world that has them.
#
# For tau in {0.10, 0.20, 0.30} in and five seeds each, the whole estimator runs on each
# simulated league. The curve reports the firing rate of P(tau >= 0.20 in) >= 0.90 and
# the simulated split-half reliability of the response. derive_thresholds() turns the
# curve into the CH1-A6 thresholds by a rule written here before any seed ran.
#
# PART (b), SBC. Parameters are drawn from the B2 prior, delta-hat is drawn from the B2
# likelihood at the real design (umpires, seasons, edges, and each cell's analytic SE at
# its real pitch locations), and B2 is refitted. The rank of the true value among 199
# thinned draws is binned into 10 bins and tested with a chi-square at alpha = 0.05 for
# tau (the abs_step SD) and the regime mean (the mean of the three edge abs_step means).
#
# WHAT IT WRITES. out/tables/ch1_power_curve.csv, and everything else under
# out/dev/ch1_synth/, which carries its own .gitignore. No fitted model object is saved:
# GD-01 fails on an .rds under out/ without provenance.json, and GD-12 fails on any
# provenance.json before prereg-v1. Draws and tables are saved as csv, json and parquet.
# The compiled Stan programs live in the R user cache, outside the repository.

args_all <- commandArgs(trailingOnly = FALSE)
args <- commandArgs(trailingOnly = TRUE)
file_arg <- grep("^--file=", args_all, value = TRUE)
SELF <- if (length(file_arg) == 1L) normalizePath(sub("^--file=", "", file_arg)) else
  normalizePath("R/ch1/21_synthetic.R")
ROOT <- Sys.getenv("ABSUMP_ROOT", unset = "")
if (!nzchar(ROOT)) ROOT <- normalizePath(file.path(dirname(SELF), "..", ".."))
setwd(ROOT)

MODE <- if (length(args) == 0L) "--power" else args[1]
if (!MODE %in% c("--power", "--sbc", "--recovery", "--check", "--worker", "--curve")) {
  cat("usage: Rscript R/ch1/21_synthetic.R --power | --sbc | --recovery [n_inject n_null] |",
      "--check | --curve\n")
  quit(status = 2)
}

suppressPackageStartupMessages({
  library(arrow)
  library(dplyr)
  library(jsonlite)
  library(splines)
})

## --- constants, fixed before any seed ran -------------------------------------------------

SEASONS_ALL   <- 2022:2026
DEV_SEASONS   <- 2022:2024                  # calibration window; never 2025 or 2026 outcomes
DEV_LAST_DATE <- as.Date("2024-12-31")
REGIME_OF     <- c("2022" = "pre_buffer", "2023" = "pre_buffer", "2024" = "pre_buffer",
                   "2025" = "buffer_2025", "2026" = "abs_2026")
EDGE_LEVELS   <- c("side", "top", "bot")
BAND_SHADOW   <- 3.0                        # SOP W3.5 shadow band, the B1 window
BAND_SURF     <- 8.0                        # SOP W3.5 surface band, the link-fit window
LINK_DF       <- 6L
U_MIN <- -8; U_MAX <- 8; U_STEP <- 0.001    # link lookup grid, inches
DELTA_MIN <- -4; DELTA_MAX <- 4; DELTA_STEP <- 0.01   # SOP W3.18 search grid
COARSE_STEP   <- 0.1
FINE_HALF     <- 1.0
N_MIN_CELL    <- 30L                        # B2 keeps umpire-season-edge cells with >= 30 pitches
N_MIN_HALF    <- 15L                        # B3 keeps half-cells with >= 15 pitches

TAUS          <- c(0.10, 0.20, 0.30)        # SOP W3.12(c), D-60
N_SEEDS       <- 5L                         # SOP W3.12(c), D-60
RULE_TAU      <- 0.20                       # CH1-A6 as written: P(tau >= 0.20 in) >= 0.90
RULE_PROB     <- 0.90
C_LADDER      <- c(0.20, 0.25, 0.30)        # candidate materiality thresholds, same draws
FALSE_FIRE_MAX <- 1L                        # of 5 seeds at tau = 0.10
POWER_MIN     <- 4L                         # of 5 seeds at tau = 0.30
REL_FLOOR     <- 0.50                       # the reliability gate D-60 names
STAN_SEED     <- 20260922L                  # SOP W3.18
DATA_SEED     <- 31200L
SBC_L         <- 200L                       # SOP W3.12(b)
SBC_DRAWS     <- 199L                       # ranks 0..199
SBC_BINS      <- 10L
SBC_ALPHA     <- 0.05
SBC_SEED      <- 31300L
MAX_PAR       <- 2L                         # concurrent brms workers, 4 chains each

OUT_DIR    <- file.path(ROOT, "out", "dev", "ch1_synth")
POWER_DIR  <- file.path(OUT_DIR, "power")
SBC_DIR    <- file.path(OUT_DIR, "sbc")
REC_DIR    <- file.path(OUT_DIR, "recovery")
CURVE_CSV  <- file.path(ROOT, "out", "tables", "ch1_power_curve.csv")
PREREG_MD  <- file.path(ROOT, "docs", "prereg", "ch1.md")
PREREG_ROOT <- file.path(ROOT, "PREREGISTRATION.md")
STAN_DIR   <- file.path(tools::R_user_dir("absump", "cache"), "ch1_synth_stan")
FIT_SUFFIXES <- c("rds", "npz", "stanfit", "qs", "pkl")

B2_FORMULA_TEXT <- paste("delta | se(se_delta, sigma = TRUE) ~ 0 + edge + edge:buf_step +",
                         "edge:abs_step + (1 + buf_step + abs_step | umpire_hp_id)")
B2_UE_US_TEXT <- paste(B2_FORMULA_TEXT, "+ (1 | umpire_hp_id:edge) + (1 | umpire_hp_id:season)")
# The estimators the curve measures. "sop" is SOP W3.18's B2 as written. "ue_us" adds the
# two nuisance intercepts the 2022-2024 calibration finds: a persistent umpire x edge
# tendency and an umpire x season shift common to the three edges.
ESTIMATORS <- c(sop = "sop", ue_us = "ue_us")
EST_FORMULA <- c(sop = B2_FORMULA_TEXT, ue_us = B2_UE_US_TEXT)
EST_LABEL <- c(sop = "SOP W3.18 B2 as written",
               ue_us = "B2 plus (1 | umpire x edge) and (1 | umpire x season)")
# Which estimator sets CH1-A6. Written after the sop curve's first four seeds showed tau
# under-estimated at 0.10 in, before any ue_us seed ran. An estimator is admissible when its
# 95% interval for tau covers the true tau in at least 13 of its 15 seeds (P(<= 12 of 15)
# is 0.036 at 95% coverage). The primary is sop when sop is admissible, else ue_us when
# ue_us is admissible, else none: then no threshold is set and no tau claim is made.
COVER_MIN <- 13L
CAL_FORMULA_TEXT <- paste("delta | se(se_delta, sigma = TRUE) ~ 0 + edge:season +",
                          "(1 | umpire_hp_id) + (1 | umpire_hp_id:edge) + (1 | umpire_hp_id:season)")

## --- the harness ----------------------------------------------------------------------------

t_start <- Sys.time()
n_pass <- 0L
failures <- character(0)
pending <- character(0)
check <- function(label, ok, detail) {
  if (isTRUE(ok)) {
    n_pass <<- n_pass + 1L
    cat(sprintf("PASS    %-50s %s\n", label, detail))
  } else {
    failures <<- c(failures, sprintf("%s -- %s", label, detail))
    cat(sprintf("FAIL    %-50s %s\n", label, detail))
  }
}
pend <- function(label, detail) {
  pending <<- c(pending, label)
  cat(sprintf("PENDING %-50s %s\n", label, detail))
}
record <- function(label, detail) cat(sprintf("RECORD  %-50s %s\n", label, detail))
comma <- function(x) formatC(as.numeric(x), format = "d", big.mark = ",")
f2 <- function(x) sprintf("%.2f", x)
f3 <- function(x) sprintf("%.3f", x)
finish <- function() {
  el <- as.numeric(difftime(Sys.time(), t_start, units = "secs"))
  cat(sprintf("\nW3.12 %s: %d PASS, %d FAIL, %d PENDING, %.0f s\n", MODE, n_pass,
              length(failures), length(pending), el))
  if (length(failures) > 0L) {
    cat("failures:\n", paste0("  ", failures, "\n"), sep = "")
    quit(status = 1)
  }
  # A PENDING clause is unscored acceptance, not a pass. Exit 3 so a verify run on a
  # partial SBC or recovery set cannot write a PASS receipt (the 2026-09-25 W3.12 gate read
  # "3 of 100 injected" off a run that had been paused for SBC and was still going).
  if (length(pending) > 0L) {
    cat("pending, not a pass:\n", paste0("  ", pending, "\n"), sep = "")
    quit(status = 3)
  }
  quit(status = 0)
}
ensure_dir <- function(p) dir.create(p, recursive = TRUE, showWarnings = FALSE)
write_json_file <- function(x, path) writeLines(toJSON(x, auto_unbox = TRUE, digits = NA, pretty = TRUE), path)

## --- layout from absump.paths ----------------------------------------------------------------

mart_path <- function() {
  out <- suppressWarnings(system2(
    "uv", c("run", "--locked", "python", "-c",
            shQuote("from absump.paths import mart; print(mart('ch1_called'))")),
    stdout = TRUE, stderr = TRUE))
  status <- attr(out, "status")
  if (is.null(status)) status <- 0L
  if (status != 0L || length(out) == 0L) {
    stop("could not read the mart path from absump.paths (exit ", status, "): ",
         paste(out, collapse = " "), call. = FALSE)
  }
  trimws(out[length(out)])
}

## --- the two reads ---------------------------------------------------------------------------
# load_outcome_dev(): calls, 2022-2024 only, |d| <= 8 in. The arrow filter drops 2025 and
# 2026 in the scanner, and the guard asserts what arrived.
# load_design(): every shadow-band pitch of 2022-2026, WITHOUT the call. The select names
# no cs column, and the guard asserts that no outcome column arrived.

load_outcome_dev <- function(mp) {
  cols <- c("pitch_uid", "season", "regime", "analysis_set", "official_date",
            "umpire_hp_id", "game_pk", "edge", "d", "cs")
  df <- arrow::open_dataset(mp) |>
    filter(season %in% !!DEV_SEASONS, abs(d) <= !!BAND_SURF) |>
    select(all_of(cols)) |> collect() |> as.data.frame()
  bad <- c(
    if (!all(df$season %in% DEV_SEASONS)) "a season outside 2022-2024",
    if (max(df$official_date) > DEV_LAST_DATE) "an official date after 2024",
    if (!identical(sort(unique(as.character(df$regime))), "pre_buffer")) "a regime other than pre_buffer",
    if (!identical(sort(unique(as.character(df$analysis_set))), "open")) "an analysis set other than open")
  if (length(bad) > 0L) stop("the outcome guard refused the sample: ", paste(bad, collapse = "; "),
                             call. = FALSE)
  df <- df[order(df$pitch_uid), , drop = FALSE]
  rownames(df) <- NULL
  df
}

load_design <- function(mp) {
  cols <- c("pitch_uid", "season", "regime", "analysis_set", "official_date",
            "umpire_hp_id", "game_pk", "edge", "d")
  df <- arrow::open_dataset(mp) |>
    filter(abs(d) <= !!BAND_SHADOW) |>
    select(all_of(cols)) |> collect() |> as.data.frame()
  bad <- c(
    if (any(c("cs", "challenged", "is_overturned") %in% names(df))) "an outcome column arrived",
    if (!all(df$season %in% SEASONS_ALL)) "a season outside 2022-2026",
    if (!all(as.character(df$regime) == REGIME_OF[as.character(df$season)])) "a regime that does not match its season",
    if (!identical(sort(unique(as.character(df$analysis_set))), "open")) "an analysis set other than open")
  if (length(bad) > 0L) stop("the design guard refused the sample: ", paste(bad, collapse = "; "),
                             call. = FALSE)
  df <- df[order(df$pitch_uid), , drop = FALSE]
  rownames(df) <- NULL
  # B3: each umpire-season's plate games in date order, odd and even by game index.
  g <- unique(df[, c("umpire_hp_id", "season", "official_date", "game_pk")])
  g <- g[order(g$umpire_hp_id, g$season, g$official_date, g$game_pk), ]
  g$game_index <- stats::ave(seq_len(nrow(g)), g$umpire_hp_id, g$season, FUN = seq_along)
  df$game_index <- g$game_index[match(paste(df$umpire_hp_id, df$season, df$game_pk),
                                      paste(g$umpire_hp_id, g$season, g$game_pk))]
  df$half <- ifelse(df$game_index %% 2L == 1L, "odd", "even")
  df$edge <- as.character(df$edge)
  data.frame(umpire_hp_id = as.integer(df$umpire_hp_id), season = as.integer(df$season),
             game_pk = as.integer(df$game_pk), game_index = as.integer(df$game_index),
             half = df$half, edge = df$edge, d = df$d, stringsAsFactors = FALSE)
}

## --- the link g_e(d) and its lookup table -----------------------------------------------------

fit_links <- function(dev) {
  u <- seq(U_MIN, U_MAX, by = U_STEP)
  lp <- matrix(NA_real_, length(u), length(EDGE_LEVELS), dimnames = list(NULL, EDGE_LEVELS))
  info <- list()
  for (e in EDGE_LEVELS) {
    s <- dev[as.character(dev$edge) == e, ]
    m <- glm(cs ~ ns(d, df = LINK_DF), family = binomial(), data = s)
    lp[, e] <- predict(m, data.frame(d = u))
    s3 <- s[abs(s$d) <= BAND_SHADOW, ]
    m1 <- glm(cs ~ d, family = binomial(), data = s3)
    iu <- which(abs(u) <= 7 + 1e-9)
    d50 <- u[which.min(abs(lp[, e]))]
    j50 <- which.min(abs(u - d50))
    slope50 <- -(lp[j50 + 10L, e] - lp[j50 - 10L, e]) / (20 * U_STEP)
    info[[e]] <- list(n_fit = nrow(s), n_shadow = nrow(s3),
                      d50_in = d50, slope_at_d50_logit_per_in = slope50,
                      glm_linear_slope_shadow = -unname(coef(m1)[2]),
                      monotone_on_pm7 = all(diff(lp[iu, e]) < 0))
  }
  list(u = u, lp = lp, info = info)
}

make_lut <- function(lp) {
  list(lg = as.vector(plogis(lp, log.p = TRUE)),
       l1g = as.vector(plogis(lp, lower.tail = FALSE, log.p = TRUE)),
       lp = as.vector(lp), nu = nrow(lp))
}
# 1-based index into one edge's column of the lookup for u = d - delta
lut_base <- function(edge_int, d, lut) (edge_int - 1L) * lut$nu + as.integer(round((d - U_MIN) / U_STEP)) + 1L
to_steps <- function(delta) as.integer(round(delta / U_STEP))

## --- B1: per-cell offsets by grid search, profile SE ------------------------------------------

b1_estimate <- function(grp, base, y, lut) {
  G <- max(grp)
  stopifnot(identical(sort(unique(grp)), seq_len(G)))
  ll_sum <- function(steps) {
    idx <- base - steps
    v <- lut$l1g[idx]
    k <- y == 1L
    v[k] <- lut$lg[idx[k]]
    as.vector(rowsum(v, grp, reorder = TRUE))
  }
  coarse <- seq(DELTA_MIN, DELTA_MAX, by = COARSE_STEP)
  LLc <- vapply(to_steps(coarse), function(s) ll_sum(rep.int(s, length(y))), numeric(G))
  centre <- coarse[max.col(LLc, ties.method = "first")]
  offs <- seq(-FINE_HALF, FINE_HALF, by = DELTA_STEP)
  fine <- round(pmin(pmax(outer(centre, offs, "+"), DELTA_MIN), DELTA_MAX), 2)
  fsteps <- matrix(to_steps(fine), nrow = G)
  LLf <- vapply(seq_along(offs), function(k) ll_sum(fsteps[grp, k]), numeric(G))
  if (G == 1L) LLf <- matrix(LLf, nrow = 1L)
  jm <- max.col(LLf, ties.method = "first")
  mle <- fine[cbind(seq_len(G), jm)]
  lmax <- LLf[cbind(seq_len(G), jm)]
  se <- vapply(seq_len(G), function(g) {
    l <- LLf[g, ]; x <- fine[g, ]; j <- jm[g]; tg <- lmax[g] - 0.5
    lo <- NA_real_; hi <- NA_real_
    if (j > 1L) {
      k <- which(l[seq_len(j - 1L)] < tg)
      if (length(k) > 0L) {
        k <- max(k)
        if (x[k + 1L] > x[k]) lo <- x[k] + (x[k + 1L] - x[k]) * (tg - l[k]) / (l[k + 1L] - l[k])
      }
    }
    if (j < length(l)) {
      k <- which(l[(j + 1L):length(l)] < tg)
      if (length(k) > 0L) {
        k <- j + min(k)
        if (x[k] > x[k - 1L]) hi <- x[k - 1L] + (x[k] - x[k - 1L]) * (l[k - 1L] - tg) / (l[k - 1L] - l[k])
      }
    }
    hw <- c(mle[g] - lo, hi - mle[g])
    if (all(is.na(hw))) NA_real_ else mean(hw, na.rm = TRUE)
  }, 0)
  data.frame(grp = seq_len(G), n = tabulate(grp, G), delta = mle, se_delta = se,
             at_bound = abs(mle) >= DELTA_MAX - 1e-9)
}

# Run B1 over cells defined by `keys` (a data frame, one row per pitch).
b1_cells <- function(keys, base, y, lut) {
  key <- do.call(paste, c(keys, sep = "|"))
  lev <- sort(unique(key))
  grp <- match(key, lev)
  est <- b1_estimate(grp, base, y, lut)
  first <- match(seq_along(lev), grp)
  cbind(keys[first, , drop = FALSE], est[, c("n", "delta", "se_delta", "at_bound")])
}

b2_rows <- function(b1) {
  k <- b1$n >= N_MIN_CELL & !b1$at_bound & is.finite(b1$se_delta)
  out <- b1[k, c("umpire_hp_id", "season", "edge", "n", "delta", "se_delta")]
  out$edge <- factor(out$edge, levels = EDGE_LEVELS)
  out$buf_step <- as.numeric(out$season >= 2025)
  out$abs_step <- as.numeric(out$season == 2026)
  out$umpire_hp_id <- factor(out$umpire_hp_id)
  out$season <- factor(out$season)
  rownames(out) <- NULL
  out
}

## --- B3: split-half reliability ------------------------------------------------------------------

sb <- function(r) 2 * r / (1 + r)

pool_edges <- function(v, w, grp) {
  # precision-weighted mean of v within grp
  num <- rowsum(v * w, grp); den <- rowsum(w, grp)
  setNames(as.vector(num / den), rownames(num))
}

split_half <- function(b1h) {
  ok <- b1h$n >= N_MIN_HALF & !b1h$at_bound & is.finite(b1h$se_delta)
  h <- b1h[ok, ]
  # response: 2026 minus 2025 per umpire, edge, half; centred per edge and half; pooled over edges
  resp <- list()
  for (hh in c("odd", "even")) {
    a <- h[h$half == hh & h$season == 2025, ]
    b <- h[h$half == hh & h$season == 2026, ]
    m <- merge(a, b, by = c("umpire_hp_id", "edge"), suffixes = c("_25", "_26"))
    m$r <- m$delta_26 - m$delta_25
    m$w <- 1 / (m$se_delta_25^2 + m$se_delta_26^2)
    ce <- pool_edges(m$r, m$w, m$edge)
    m$rc <- m$r - ce[m$edge]
    resp[[hh]] <- pool_edges(m$rc, m$w, m$umpire_hp_id)
  }
  u <- intersect(names(resp$odd), names(resp$even))
  r_resp <- stats::cor(resp$odd[u], resp$even[u])
  # level: per umpire-season, centred per season, edge and half; pooled over edges
  lev <- list()
  for (hh in c("odd", "even")) {
    a <- h[h$half == hh, ]
    a$w <- 1 / a$se_delta^2
    key_se <- paste(a$season, a$edge)
    ce <- pool_edges(a$delta, a$w, key_se)
    a$dc <- a$delta - ce[key_se]
    lev[[hh]] <- pool_edges(a$dc, a$w, paste(a$umpire_hp_id, a$season))
  }
  v <- intersect(names(lev$odd), names(lev$even))
  r_lev <- stats::cor(lev$odd[v], lev$even[v])
  list(n_umpires = length(u), r_response = r_resp, sb_response = sb(r_resp),
       n_umpire_seasons = length(v), r_level = r_lev, sb_level = sb(r_lev))
}

## --- brms: the B2 model and the calibration model -------------------------------------------------

load_brms <- function() {
  suppressPackageStartupMessages({
    library(brms)
    library(cmdstanr)
    library(posterior)
  })
  ensure_dir(STAN_DIR)
  options(cmdstanr_write_stan_file_dir = STAN_DIR, brms.backend = "cmdstanr",
          mc.cores = 4L)
}

b2_priors <- function() {
  c(brms::prior(normal(0, 1), class = "b"),
    brms::prior(exponential(2), class = "sd"),
    brms::prior(exponential(2), class = "sigma"),
    brms::prior(lkj(2), class = "cor"))
}
cal_priors <- function() {
  c(brms::prior(normal(0, 1), class = "b"),
    brms::prior(exponential(2), class = "sd"),
    brms::prior(exponential(2), class = "sigma"))
}

fit_brms <- function(formula_text, data, priors) {
  warn <- character(0)
  pt0 <- proc.time()
  fit <- withCallingHandlers(
    brms::brm(brms::bf(as.formula(formula_text)), data = data, family = gaussian(),
              prior = priors, chains = 4, iter = 2000, cores = 4, backend = "cmdstanr",
              seed = STAN_SEED, refresh = 0, silent = 2),
    warning = function(w) {
      warn <<- c(warn, conditionMessage(w))
      invokeRestart("muffleWarning")
    },
    message = function(m) invokeRestart("muffleMessage"))
  pt <- proc.time() - pt0
  list(fit = fit, warn = warn, elapsed = unname(pt[["elapsed"]]))
}

diagnostics <- function(fit, pars) {
  np <- brms::nuts_params(fit)
  div <- sum(np$Value[np$Parameter == "divergent__"])
  td <- sum(np$Value[np$Parameter == "treedepth__"] >= 10)
  en <- np[np$Parameter == "energy__", ]
  ebfmi <- vapply(split(en$Value, en$Chain), function(e) sum(diff(e)^2) / length(e) / stats::var(e), 0)
  dr <- posterior::subset_draws(posterior::as_draws_array(fit), variable = pars)
  sm <- posterior::summarise_draws(dr, "rhat", "ess_bulk", "ess_tail")
  list(divergent = div, treedepth_hits = td, ebfmi_min = min(ebfmi),
       rhat_max = max(sm$rhat), ess_bulk_min = min(sm$ess_bulk), ess_tail_min = min(sm$ess_tail))
}

## --- the scheduler --------------------------------------------------------------------------------

run_workers <- function(jobs, logdir, max_par = MAX_PAR) {
  ensure_dir(logdir)
  running <- list()
  status <- list()
  queue <- jobs
  while (length(queue) > 0L || length(running) > 0L) {
    while (length(running) < max_par && length(queue) > 0L) {
      j <- queue[[1]]
      queue <- queue[-1]
      running[[j$tag]] <- processx::process$new(
        "Rscript", c(SELF, "--worker", j$args),
        stdout = file.path(logdir, paste0(j$tag, ".log")), stderr = "2>&1",
        env = c("current", ABSUMP_ROOT = ROOT), cleanup = TRUE)
    }
    Sys.sleep(2)
    for (tag in names(running)) {
      p <- running[[tag]]
      if (!p$is_alive()) {
        st <- p$get_exit_status()
        status[[tag]] <- st
        cat(sprintf("  worker %-28s exit %s\n", tag, st))
        running[[tag]] <- NULL
      }
    }
  }
  status
}

## --- part (c): one power seed -----------------------------------------------------------------------

seed_tag <- function(tau, seed) sprintf("tau%.2f_seed%d", tau, seed)
data_seed <- function(tau, seed) DATA_SEED + 100L * match(round(tau, 2), round(TAUS, 2)) + seed

simulate_league <- function(des, lut, cal, tau, seed) {
  set.seed(data_seed(tau, seed))
  umps <- sort(unique(des$umpire_hp_id))
  nu <- length(umps)
  a <- setNames(stats::rnorm(nu, 0, cal$sd_level), umps)
  bb <- setNames(stats::rnorm(nu, 0, tau), umps)           # buffer response, SD tau
  cc <- setNames(stats::rnorm(nu, 0, tau), umps)           # ABS response, SD tau
  ue <- unique(des[, c("umpire_hp_id", "edge")])
  ue <- ue[order(ue$umpire_hp_id, ue$edge), ]
  h <- setNames(stats::rnorm(nrow(ue), 0, cal$sd_ump_edge), paste(ue$umpire_hp_id, ue$edge))
  us <- unique(des[, c("umpire_hp_id", "season")])
  us <- us[order(us$umpire_hp_id, us$season), ]
  w <- setNames(stats::rnorm(nrow(us), 0, cal$sd_ump_season), paste(us$umpire_hp_id, us$season))
  cells <- unique(des[, c("umpire_hp_id", "season", "edge")])
  cells <- cells[order(cells$umpire_hp_id, cells$season, cells$edge), ]
  e <- stats::rnorm(nrow(cells), 0, cal$sigma_resid)
  uk <- as.character(cells$umpire_hp_id)
  cells$delta_true <- a[uk] + h[paste(uk, cells$edge)] + w[paste(uk, cells$season)] + e +
    bb[uk] * (cells$season >= 2025) + cc[uk] * (cells$season == 2026)
  ci <- match(paste(des$umpire_hp_id, des$season, des$edge),
              paste(cells$umpire_hp_id, cells$season, cells$edge))
  idx <- des$base - to_steps(cells$delta_true[ci])
  p <- exp(lut$lg[idx])
  y <- as.integer(stats::runif(nrow(des)) < p)
  list(y = y, cells = cells,
       truth = data.frame(umpire_hp_id = umps, buf_true = unname(bb), abs_true = unname(cc)))
}

run_power_seed <- function(tau, seed, est, outdir) {
  load_brms()
  des <- as.data.frame(arrow::read_parquet(file.path(OUT_DIR, "design.parquet")))
  lk <- as.data.frame(arrow::read_parquet(file.path(OUT_DIR, "link.parquet")))
  lut <- make_lut(as.matrix(lk[, EDGE_LEVELS]))
  cal <- fromJSON(file.path(OUT_DIR, "calibration.json"))$dgp
  des$base <- lut_base(match(des$edge, EDGE_LEVELS), des$d, lut)
  sim <- simulate_league(des, lut, cal, tau, seed)
  pt0 <- proc.time()
  b1 <- b1_cells(des[, c("umpire_hp_id", "season", "edge")], des$base, sim$y, lut)
  b1h <- b1_cells(des[, c("umpire_hp_id", "season", "edge", "half")], des$base, sim$y, lut)
  t_b1 <- unname((proc.time() - pt0)[["elapsed"]])
  dd <- b2_rows(b1)
  ft <- fit_brms(EST_FORMULA[[est]], dd, b2_priors())
  fit <- ft$fit
  dr <- posterior::as_draws_df(fit)
  tau_d <- dr[["sd_umpire_hp_id__abs_step"]]
  buf_d <- dr[["sd_umpire_hp_id__buf_step"]]
  if (is.null(tau_d) || is.null(buf_d)) stop("B2 draws lack the abs_step or buf_step SD", call. = FALSE)
  rn <- grep("^r_umpire_hp_id\\[.*,abs_step\\]$", names(dr), value = TRUE)
  rid <- sub("^r_umpire_hp_id\\[(.*),abs_step\\]$", "\\1", rn)
  rm <- as.matrix(as.data.frame(dr)[, rn])
  post_mean <- colMeans(rm)
  post_var <- apply(rm, 2, stats::var)
  truth <- sim$truth[match(as.integer(rid), sim$truth$umpire_hp_id), ]
  sh <- split_half(b1h)
  pars <- c(grep("^b_", names(dr), value = TRUE), grep("^sd_", names(dr), value = TRUE),
            grep("^cor_", names(dr), value = TRUE), "sigma")
  dg <- diagnostics(fit, pars)
  ensure_dir(outdir)
  data.table::fwrite(data.frame(draw = seq_along(tau_d), tau_abs = tau_d, tau_buf = buf_d,
                                sigma = dr[["sigma"]]),
                     file.path(outdir, "tau_draws.csv.gz"))
  data.table::fwrite(b1, file.path(outdir, "b1_full.csv.gz"))
  data.table::fwrite(b1h, file.path(outdir, "b1_halves.csv.gz"))
  data.table::fwrite(data.frame(umpire_hp_id = as.integer(rid), abs_post_mean = post_mean,
                                abs_post_var = post_var, abs_true = truth$abs_true,
                                buf_true = truth$buf_true),
                     file.path(outdir, "umpires.csv.gz"))
  q <- stats::quantile(tau_d, c(0.025, 0.5, 0.95, 0.975), names = FALSE)
  res <- list(
    estimator = est, formula = EST_FORMULA[[est]],
    tau_true = tau, seed = seed, data_seed = data_seed(tau, seed), stan_seed = STAN_SEED,
    n_pitches = nrow(des), n_called_strikes = sum(sim$y), n_cells = nrow(b1),
    n_cells_b2 = nrow(dd), n_umpires_b2 = nlevels(dd$umpire_hp_id),
    p_tau_ge = setNames(as.list(vapply(C_LADDER, function(c) mean(tau_d >= c), 0)),
                        sprintf("%.2f", C_LADDER)),
    fired = mean(tau_d >= RULE_TAU) >= RULE_PROB,
    tau_median = q[2], tau_lo95 = q[1], tau_hi95 = q[4], tau_upper95 = q[3],
    covers_truth = q[1] <= tau && tau <= q[4],
    tau_buf_median = stats::median(buf_d),
    reliability_vc_response = 1 - mean(post_var) / mean(tau_d^2),
    cor2_shrunken_truth = stats::cor(post_mean, truth$abs_true)^2,
    split_half = sh, diagnostics = dg, b1_seconds = t_b1, b2_seconds = ft$elapsed,
    brms_warnings = unique(ft$warn))
  write_json_file(res, file.path(outdir, "summary.json"))
  invisible(res)
}

## --- the curve and the CH1-A6 derivation -------------------------------------------------------------
# Written before any seed ran. F_c(t) is the share of the five seeds at true tau = t in
# which P(tau >= c | data) >= 0.90; S(t) is the five-seed mean simulated split-half of the
# response.
#   1. c* is the smallest c in {0.20, 0.25, 0.30} in with F_c(0.10) <= 1/5: at half the
#      SOP threshold the rule fires in at most one seed of five. No such c: none.
#   2. powered: c* exists and F_c*(0.30) >= 4/5.
#   3. The reliability gate. REVISED after the sop curve and before any ue_us seed or any
#      real-data heterogeneity fit. The first version gated on the split-half S(t) alone:
#      R* = S(0.20) rounded down to 0.01. The sop curve showed S(0.10) = 0.69, already
#      above the 0.50 floor at half the materiality threshold, because split-half counts
#      season-specific umpire variation as signal. MT-07 makes the variance-components
#      value the gating estimator, so the gate is now:
#        V(t) = five-seed mean variance-components reliability of the per-umpire response,
#               1 - mean posterior variance of the umpire's abs_step / E[tau^2];
#        the gate is attainable when V(t) >= 0.50 at some grid tau t where the rule is
#        powered (F_c*(t) >= 4/5); t_att is the smallest such t;
#        attainable: publish the per-umpire table only if the rule fires, the observed V
#        is >= 0.50, and the observed split-half is >= S(t_att) rounded down to 0.01;
#        not attainable: no per-umpire table. tau is reported with its interval.
#   4. Not powered: the bounded null is the pre-registered reportable result, as D-42
#      does for Chapter 3.

wilson <- function(k, n, z = 1.959964) {
  p <- k / n
  den <- 1 + z^2 / n
  ctr <- (p + z^2 / (2 * n)) / den
  hw <- z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2)) / den
  c(ctr - hw, ctr + hw)
}

read_seed_raw <- function(tau, seed, est) {
  d <- file.path(POWER_DIR, est, seed_tag(tau, seed))
  sj <- file.path(d, "summary.json")
  td <- file.path(d, "tau_draws.csv.gz")
  if (!file.exists(sj) || !file.exists(td)) return(NULL)
  list(summary = fromJSON(sj), draws = utils::read.csv(td))
}

curve_rows <- function(est) {
  rows <- list()
  per_seed <- list()
  for (t in TAUS) {
    ss <- lapply(seq_len(N_SEEDS), function(s) read_seed_raw(t, s, est))
    if (any(vapply(ss, is.null, TRUE))) return(NULL)
    pge <- vapply(ss, function(x) mean(x$draws$tau_abs >= RULE_TAU), 0)
    fired <- as.integer(pge >= RULE_PROB)
    fc <- vapply(C_LADDER, function(c)
      mean(vapply(ss, function(x) mean(x$draws$tau_abs >= c) >= RULE_PROB, TRUE)), 0)
    med <- vapply(ss, function(x) stats::median(x$draws$tau_abs), 0)
    up <- vapply(ss, function(x) stats::quantile(x$draws$tau_abs, 0.95, names = FALSE), 0)
    cov <- vapply(ss, function(x) {
      q <- stats::quantile(x$draws$tau_abs, c(0.025, 0.975), names = FALSE)
      q[1] <= t && t <= q[2]
    }, TRUE)
    upc <- up >= t
    c2 <- vapply(ss, function(x) x$summary$cor2_shrunken_truth, 0)
    shr <- vapply(ss, function(x) x$summary$split_half$sb_response, 0)
    shl <- vapply(ss, function(x) x$summary$split_half$sb_level, 0)
    rvc <- vapply(ss, function(x) x$summary$reliability_vc_response, 0)
    nu <- vapply(ss, function(x) x$summary$split_half$n_umpires, 0)
    div <- vapply(ss, function(x) x$summary$diagnostics$divergent, 0)
    rh <- vapply(ss, function(x) x$summary$diagnostics$rhat_max, 0)
    eb <- vapply(ss, function(x) x$summary$diagnostics$ess_bulk_min, 0)
    et <- vapply(ss, function(x) x$summary$diagnostics$ess_tail_min, 0)
    wl <- wilson(sum(fired), N_SEEDS)
    for (s in seq_len(N_SEEDS)) {
      per_seed[[length(per_seed) + 1L]] <- data.frame(
        estimator = est, tau_true_in = t, seed = s, p_tau_ge_020 = pge[s], fired = fired[s],
        tau_post_median_in = med[s], tau_upper95_in = up[s], ci95_covers_truth = cov[s],
        upper95_covers_truth = upc[s], cor2_shrunken_truth = c2[s],
        split_half_response = shr[s], split_half_level = shl[s],
        reliability_vc_response = rvc[s], n_umpires_split_half = nu[s],
        divergent = div[s], rhat_max = rh[s], ess_bulk_min = eb[s], ess_tail_min = et[s],
        stringsAsFactors = FALSE)
    }
    rows[[length(rows) + 1L]] <- data.frame(
      estimator = est, formula = EST_FORMULA[[est]],
      tau_true_in = sprintf("%.2f", t), tau_buf_true_in = sprintf("%.2f", t),
      n_seeds = N_SEEDS, rule = "P(tau >= 0.20 in) >= 0.90",
      n_fired = sum(fired), firing_rate = sprintf("%.2f", mean(fired)),
      firing_rate_wilson95_lo = sprintf("%.3f", wl[1]), firing_rate_wilson95_hi = sprintf("%.3f", wl[2]),
      fired_by_seed = paste(fired, collapse = ";"),
      p_tau_ge_020_by_seed = paste(sprintf("%.4f", pge), collapse = ";"),
      firing_rate_c025 = sprintf("%.2f", fc[2]), firing_rate_c030 = sprintf("%.2f", fc[3]),
      tau_post_median_mean_in = sprintf("%.3f", mean(med)),
      tau_upper95_mean_in = sprintf("%.3f", mean(up)),
      ci95_covers_truth = sprintf("%d/%d", sum(cov), N_SEEDS),
      upper95_covers_truth = sprintf("%d/%d", sum(upc), N_SEEDS),
      split_half_response_mean = sprintf("%.3f", mean(shr)),
      split_half_response_min = sprintf("%.3f", min(shr)),
      split_half_response_max = sprintf("%.3f", max(shr)),
      split_half_response_by_seed = paste(sprintf("%.3f", shr), collapse = ";"),
      split_half_level_mean = sprintf("%.3f", mean(shl)),
      reliability_vc_response_mean = sprintf("%.3f", mean(rvc)),
      reliability_vc_response_by_seed = paste(sprintf("%.3f", rvc), collapse = ";"),
      cor2_shrunken_truth_mean = sprintf("%.3f", mean(c2)),
      n_umpires_split_half_mean = sprintf("%.1f", mean(nu)),
      divergent_total = sum(div), rhat_max = sprintf("%.4f", max(rh)),
      ess_bulk_min = sprintf("%.0f", min(eb)), ess_tail_min = sprintf("%.0f", min(et)),
      stringsAsFactors = FALSE)
  }
  list(curve = do.call(rbind, rows), per_seed = do.call(rbind, per_seed))
}

build_curve <- function() {
  parts <- lapply(ESTIMATORS, curve_rows)
  if (any(vapply(parts, is.null, TRUE))) return(NULL)
  per_seed <- do.call(rbind, lapply(parts, `[[`, "per_seed"))
  cover <- vapply(ESTIMATORS, function(e) sum(per_seed$ci95_covers_truth[per_seed$estimator == e]), 0)
  primary <- if (cover[["sop"]] >= COVER_MIN) "sop" else if (cover[["ue_us"]] >= COVER_MIN) "ue_us" else "none"
  curve <- do.call(rbind, lapply(parts, `[[`, "curve"))
  curve$sets_ch1_a6 <- ifelse(curve$estimator == primary, "yes", "no")
  rownames(curve) <- NULL
  rownames(per_seed) <- NULL
  list(curve = curve, per_seed = per_seed, primary = primary, cover = as.list(cover))
}

derive_thresholds <- function(ps, est) {
  ps <- ps[ps$estimator == est, ]
  fire_c <- function(c, t) {
    sub <- ps[abs(ps$tau_true_in - t) < 1e-9, ]
    sum(vapply(seq_len(nrow(sub)), function(i) {
      x <- read_seed_raw(t, sub$seed[i], est)
      mean(x$draws$tau_abs >= c) >= RULE_PROB
    }, TRUE))
  }
  S <- vapply(TAUS, function(t) mean(ps$split_half_response[abs(ps$tau_true_in - t) < 1e-9]), 0)
  names(S) <- sprintf("%.2f", TAUS)
  V <- vapply(TAUS, function(t) mean(ps$reliability_vc_response[abs(ps$tau_true_in - t) < 1e-9]), 0)
  names(V) <- sprintf("%.2f", TAUS)
  cstar <- NA_real_
  ff <- list()
  for (c in C_LADDER) {
    ff[[sprintf("%.2f", c)]] <- vapply(TAUS, function(t) fire_c(c, t), 0)
    if (is.na(cstar) && ff[[sprintf("%.2f", c)]][1] <= FALSE_FIRE_MAX) cstar <- c
  }
  powered <- !is.na(cstar) && ff[[sprintf("%.2f", cstar)]][3] >= POWER_MIN
  fpow <- if (is.na(cstar)) rep(0, length(TAUS)) else ff[[sprintf("%.2f", cstar)]]
  att <- which(fpow >= POWER_MIN & V >= REL_FLOOR)
  if (length(att) > 0L) {
    t_att <- TAUS[min(att)]
    rstar_vc <- REL_FLOOR
    rstar_sh <- floor(S[[sprintf("%.2f", t_att)]] * 100 + 1e-9) / 100
    table_rule <- sprintf("publish the per-umpire table only if the materiality rule fires, the variance-components reliability of the response is at least %.2f and its split-half is at least %.2f", rstar_vc, rstar_sh)
    attainable <- TRUE
  } else {
    t_att <- NA_real_
    rstar_vc <- NA_real_
    rstar_sh <- NA_real_
    table_rule <- "no per-umpire table: the curve does not reach a variance-components reliability of 0.50 at any \u03c4 where the rule is powered"
    attainable <- FALSE
  }
  rstar <- rstar_vc
  up <- vapply(TAUS, function(t) mean(ps$tau_upper95_in[abs(ps$tau_true_in - t) < 1e-9]), 0)
  # 5. The bound. When the primary's one-sided 95% upper bound fell below the true tau in
  #    any seed, the bounded null uses the larger of the two estimators' bounds.
  upc <- vapply(TAUS, function(t) sum(ps$upper95_covers_truth[abs(ps$tau_true_in - t) < 1e-9]), 0)
  bound <- if (min(upc) < N_SEEDS) {
    sprintf("bounded null: the posterior median of %s and the larger of the one-sided 95%% upper bounds from `sop` and `ue_us`, because the `%s` bound fell below the true %s in %d of %d seeds",
            "τ", est, "τ", sum(N_SEEDS - upc), N_SEEDS * length(TAUS))
  } else {
    sprintf("bounded null: the posterior median of %s and its one-sided 95%% upper bound from `%s`", "τ", est)
  }
  list(estimator = est, formula = EST_FORMULA[[est]], c_star_in = cstar, prob = RULE_PROB,
       powered = powered, fired_of_5 = ff, split_half_mean = as.list(round(S, 3)),
       reliability_vc_mean = as.list(round(V, 3)), r_star = rstar, r_star_vc = rstar_vc,
       r_star_split_half = rstar_sh, tau_attainable = t_att,
       reliability_gate_attainable = attainable, table_rule = table_rule,
       reportable_if_not_fired = bound, upper95_covers_of_5 = as.list(setNames(upc, sprintf("%.2f", TAUS))),
       bounded_null_primary = !powered,
       expected_upper95_in = setNames(as.list(round(up, 3)), sprintf("%.2f", TAUS)))
}

write_curve <- function() {
  bc <- build_curve()
  if (is.null(bc)) stop("the power curve is incomplete: a seed has no raw output", call. = FALSE)
  ensure_dir(dirname(CURVE_CSV))
  utils::write.csv(bc$curve, CURVE_CSV, row.names = FALSE, quote = TRUE)
  utils::write.csv(bc$per_seed, file.path(POWER_DIR, "seeds.csv"), row.names = FALSE)
  th <- if (bc$primary == "none") list(estimator = "none", c_star_in = NA, r_star = NA, powered = FALSE,
                                       note = "no estimator covered the true tau in 13 of 15 seeds") else
    derive_thresholds(bc$per_seed, bc$primary)
  th$coverage_of_15 <- bc$cover
  write_json_file(th, file.path(POWER_DIR, "thresholds.json"))
  list(curve = bc$curve, per_seed = bc$per_seed, thresholds = th, primary = bc$primary)
}

## --- part (b): SBC ---------------------------------------------------------------------------------

rlkjcorr <- function(K, eta) {
  alpha <- eta + (K - 2) / 2
  r12 <- 2 * stats::rbeta(1, alpha, alpha) - 1
  R <- matrix(0, K, K)
  R[1, 1] <- 1
  R[1, 2] <- r12
  R[2, 2] <- sqrt(1 - r12^2)
  if (K > 2) for (m in 2:(K - 1)) {
    alpha <- alpha - 0.5
    y <- stats::rbeta(1, m / 2, alpha)
    z <- stats::rnorm(m)
    z <- z / sqrt(sum(z^2))
    R[1:m, m + 1] <- sqrt(y) * z
    R[m + 1, m + 1] <- sqrt(1 - y)
  }
  crossprod(R)
}

sbc_design <- function(des, lut) {
  # each cell's analytic SE at delta = 0: 1 / sqrt(sum g(1-g) eta'(u)^2)
  eta <- lut$lp[des$base]
  deta <- (lut$lp[des$base + 1L] - lut$lp[des$base - 1L]) / (2 * U_STEP)
  p <- plogis(eta)
  info <- p * (1 - p) * deta^2
  key <- paste(des$umpire_hp_id, des$season, des$edge)
  agg <- data.frame(key = names(tapply(info, key, sum)), info = as.vector(tapply(info, key, sum)),
                    n = as.vector(table(key)[names(tapply(info, key, sum))]))
  parts <- do.call(rbind, strsplit(agg$key, " "))
  out <- data.frame(umpire_hp_id = as.integer(parts[, 1]), season = as.integer(parts[, 2]),
                    edge = parts[, 3], n = agg$n, se_delta = 1 / sqrt(agg$info),
                    stringsAsFactors = FALSE)
  out <- out[out$n >= N_MIN_CELL, ]
  out[order(out$umpire_hp_id, out$season, match(out$edge, EDGE_LEVELS)), ]
}

SBC_QUANTITIES <- c("tau_abs", "tau_buf", "sd_intercept", "sigma", "cor_buf_abs",
                    "b_side_abs", "b_top_abs", "b_bot_abs", "regime_mean_abs", "regime_mean_buf")

run_sbc_reps <- function(est, from, to) {
  load_brms()
  sdir <- file.path(SBC_DIR, est)
  ensure_dir(sdir)
  base <- utils::read.csv(file.path(SBC_DIR, "sbc_design.csv"), stringsAsFactors = FALSE)
  base$edge <- factor(base$edge, levels = EDGE_LEVELS)
  base$buf_step <- as.numeric(base$season >= 2025)
  base$abs_step <- as.numeric(base$season == 2026)
  X <- stats::model.matrix(~ 0 + edge + edge:buf_step + edge:abs_step, base)
  Z <- cbind(1, base$buf_step, base$abs_step)
  umps <- sort(unique(base$umpire_hp_id))
  ui <- match(base$umpire_hp_id, umps)
  ue_key <- paste(base$umpire_hp_id, base$edge)
  us_key <- paste(base$umpire_hp_id, base$season)
  ue_lev <- sort(unique(ue_key)); us_lev <- sort(unique(us_key))
  for (l in from:to) {
    out <- file.path(sdir, sprintf("rep%03d.json", l))
    if (file.exists(out)) next
    set.seed(SBC_SEED + l)
    b <- stats::rnorm(ncol(X), 0, 1)
    sdv <- stats::rexp(3, 2)
    R <- rlkjcorr(3, 2)
    sigma <- stats::rexp(1, 2)
    S <- diag(sdv) %*% R %*% diag(sdv)
    r <- matrix(stats::rnorm(length(umps) * 3), ncol = 3) %*% chol(S)
    mu <- as.vector(X %*% b) + rowSums(Z * r[ui, ])
    sd_ue <- NA_real_; sd_us <- NA_real_
    if (est == "ue_us") {
      sd_ue <- stats::rexp(1, 2)
      sd_us <- stats::rexp(1, 2)
      mu <- mu + stats::rnorm(length(ue_lev), 0, sd_ue)[match(ue_key, ue_lev)] +
        stats::rnorm(length(us_lev), 0, sd_us)[match(us_key, us_lev)]
    }
    d <- base
    d$delta <- mu + stats::rnorm(nrow(d), 0, sqrt(sigma^2 + d$se_delta^2))
    d$umpire_hp_id <- factor(d$umpire_hp_id)
    d$season <- factor(d$season)
    truth <- c(tau_abs = sdv[3], tau_buf = sdv[2], sd_intercept = sdv[1], sigma = sigma,
               cor_buf_abs = R[2, 3], b_side_abs = b[7], b_top_abs = b[8], b_bot_abs = b[9],
               regime_mean_abs = mean(b[7:9]), regime_mean_buf = mean(b[4:6]))
    ft <- fit_brms(EST_FORMULA[[est]], d, b2_priors())
    dr <- posterior::as_draws_df(ft$fit)
    nm <- names(dr)
    stopifnot(identical(colnames(X)[7:9], c("edgeside:abs_step", "edgetop:abs_step", "edgebot:abs_step")))
    post <- cbind(
      tau_abs = dr[["sd_umpire_hp_id__abs_step"]],
      tau_buf = dr[["sd_umpire_hp_id__buf_step"]],
      sd_intercept = dr[["sd_umpire_hp_id__Intercept"]],
      sigma = dr[["sigma"]],
      cor_buf_abs = dr[["cor_umpire_hp_id__buf_step__abs_step"]],
      b_side_abs = dr[["b_edgeside:abs_step"]],
      b_top_abs = dr[["b_edgetop:abs_step"]],
      b_bot_abs = dr[["b_edgebot:abs_step"]])
    post <- cbind(post,
                  regime_mean_abs = rowMeans(post[, c("b_side_abs", "b_top_abs", "b_bot_abs")]),
                  regime_mean_buf = rowMeans(cbind(dr[["b_edgeside:buf_step"]], dr[["b_edgetop:buf_step"]],
                                                   dr[["b_edgebot:buf_step"]])))
    keep <- round(seq(1, nrow(post), length.out = SBC_DRAWS))
    ranks <- vapply(SBC_QUANTITIES, function(q) sum(post[keep, q] < truth[[q]]), 0)
    dg <- diagnostics(ft$fit, c(grep("^b_", nm, value = TRUE), grep("^sd_", nm, value = TRUE),
                                grep("^cor_", nm, value = TRUE), "sigma"))
    write_json_file(list(rep = l, estimator = est, seed = SBC_SEED + l, truth = as.list(truth),
                         sd_ue = sd_ue, sd_us = sd_us, ranks = as.list(ranks),
                         n_draws = SBC_DRAWS, diagnostics = dg, seconds = ft$elapsed),
                    out)
    cat(sprintf("sbc rep %d done in %.1f s\n", l, ft$elapsed))
  }
}

# Simultaneous 95% ECDF band for ranks, by Monte Carlo (the method of Sailynoja,
# Buerkner and Vehtari, 2022): the pointwise binomial level gamma is chosen so that 95%
# of uniform rank samples stay inside the band at every evaluation point.
ecdf_band_gamma <- function(n, L, K = 20L, nsim = 4000L, seed = 31399L) {
  set.seed(seed)
  z <- seq_len(K - 1L) / K
  mins <- vapply(seq_len(nsim), function(i) {
    u <- (sample.int(L + 1L, n, replace = TRUE) - 0.5) / (L + 1)
    cnt <- vapply(z, function(zz) sum(u <= zz), 0)
    p <- pmin(stats::pbinom(cnt, n, z), 1 - stats::pbinom(cnt - 1, n, z))
    min(2 * p)
  }, 0)
  unname(stats::quantile(mins, 0.05))
}
ecdf_inside <- function(ranks, L, gamma, K = 20L) {
  n <- length(ranks)
  z <- seq_len(K - 1L) / K
  u <- (ranks + 0.5) / (L + 1)
  cnt <- vapply(z, function(zz) sum(u <= zz), 0)
  lo <- stats::qbinom(gamma / 2, n, z)
  hi <- stats::qbinom(1 - gamma / 2, n, z)
  all(cnt >= lo & cnt <= hi)
}

score_sbc <- function(est) {
  f <- sort(list.files(file.path(SBC_DIR, est), pattern = "^rep\\d{3}\\.json$", full.names = TRUE))
  if (length(f) == 0L) return(NULL)
  reps <- lapply(f, fromJSON)
  rk <- do.call(rbind, lapply(reps, function(r) unlist(r$ranks)[SBC_QUANTITIES]))
  n <- nrow(rk)
  width <- (SBC_DRAWS + 1L) / SBC_BINS
  chi <- vapply(SBC_QUANTITIES, function(q) {
    bins <- factor(floor(rk[, q] / width), levels = 0:(SBC_BINS - 1L))
    suppressWarnings(stats::chisq.test(table(bins), p = rep(1 / SBC_BINS, SBC_BINS))$p.value)
  }, 0)
  gamma <- ecdf_band_gamma(n, SBC_DRAWS)
  inside <- vapply(SBC_QUANTITIES, function(q) ecdf_inside(rk[, q], SBC_DRAWS, gamma), TRUE)
  dg <- do.call(rbind, lapply(reps, function(r) as.data.frame(r$diagnostics)))
  list(n = n, p_chisq = chi, p_bh = stats::p.adjust(chi, "BH"), ecdf_inside = inside, gamma = gamma,
       divergent_reps = sum(dg$divergent > 0), divergent_total = sum(dg$divergent),
       rhat_max = max(dg$rhat_max), seconds_mean = mean(vapply(reps, function(r) r$seconds, 0)),
       ranks = rk)
}

## --- part (a): injected-effect recovery ------------------------------------------------------------
# The 2024 called pitches with |d| <= 8 in are used twice: once labelled 2024 and once
# labelled synthetic 2026. A generating surface is fitted once on the real 2024 calls: the
# frozen W3.11 specification without its season terms and without s(umpire_season), which
# equals s(umpire_hp_id) inside one season. Both copies then get new calls: the 2024 copy
# from the generating surface as fitted, the 2026 copy from the same surface with the
# zone deformed: top down 0.60 in, bottom up 0.30 in, half-width in 0.10 in, for a 72 in
# batter. The deformation is a piecewise-linear warp of (x_mid, zn) that moves the
# generating contour by exactly those amounts at the reference points of the SOP W3.14
# estimands. The truth is read off the generating surfaces with the same estimand code.
# A null replicate draws both copies from the undeformed surface. Each replicate fits the
# frozen specification with season in {2024, 2026}, extracts top_in, bot_in and
# half_width_in on the standardised surfaces, and takes 95% intervals from 1,000 draws of
# the coefficients from N(beta, Vp). Nothing fitted is saved. CH1-A7 asks for the
# zero-effect criterion as an equivalence test in CH1-A3's form, so each replicate also
# records whether its 90% interval for the error lies inside +/-0.10 in; the null set
# passes when that holds in at least 93% of replicates for every shift, beside the SOP's
# false-positive rate of at most 7%.

REC_N_INJECT <- 100L                        # SOP W3.12(a)
REC_N_NULL   <- 50L                         # MT-04: 50 null replicates
INJ_IN       <- c(top_in = -0.60, bot_in = 0.30, half_width_in = -0.10)   # SOP W3.12(a)
REC_TOL_IN   <- 0.10
REC_COVER_MIN_SHARE <- 0.93                 # 93 of 100
REC_FPR_MAX  <- 0.07
REC_DRAWS    <- 1000L
REC_SEED     <- 31500L
REC_MAX_PAR  <- 4L
REC_SEASONS  <- c("2024", "2026")
CC_LEVELS    <- c("0-strike", "1-strike", "2-strike")
STAND_LEVELS <- c("L", "R")
PG_LEVELS    <- c("FF", "SI/FC", "BRK", "OFFSP")
REF_HEIGHT_IN <- 72
ZN_MID       <- 0.4025
CENTRE_X_FT  <- 0.25
XG <- round(seq(-1.5, 1.5, by = 0.01), 2)
ZG <- round(seq(0.15, 0.70, by = 0.002), 3)
NQ <- 51L
J_MID_LO <- max(which(ZG <= ZN_MID))
J_MID_HI <- J_MID_LO + 1L
I_CENTRE <- which(abs(XG) <= CENTRE_X_FT + 1e-9)
I_ZERO   <- which(XG == 0)
WIN_ZN   <- 0.03                            # draw window around each point-estimate crossing, zn units
WIN_X    <- 0.10                            # ft

frozen_k <- function() {
  fz <- fromJSON(file.path(ROOT, "out", "dev", "ch1_spec", "frozen_spec.json"))
  stopifnot(identical(fz$coding, "ordered"))
  unlist(fz$k)
}
te_txt <- function(k, by = NULL) sprintf('te(x_mid, zn, bs = c("cr","cr"), k = c(%d,%d)%s)', k, k,
                                         if (is.null(by)) "" else paste0(", by = ", by))
gen_formula <- function(k) paste0("cs ~ count_class + stand + pitch_group + ", te_txt(k[["main"]]),
                                  " + ", te_txt(k[["ccst"]], "count_class_o"), " + ", te_txt(k[["ccst"]], "stand_o"),
                                  " + s(velo, k = ", k[["velo"]], ') + s(umpire_hp_id, bs = "re")')
rec_formula <- function(k) paste0("cs ~ season + count_class + stand + pitch_group + ", te_txt(k[["main"]]),
                                  " + ", te_txt(k[["season"]], "season_o"), " + ", te_txt(k[["ccst"]], "count_class_o"),
                                  " + ", te_txt(k[["ccst"]], "stand_o"), " + s(velo, k = ", k[["velo"]],
                                  ') + s(umpire_hp_id, bs = "re") + s(umpire_season, bs = "re")')

load_rec_rows <- function(mp) {
  cols <- c("pitch_uid", "season", "regime", "analysis_set", "official_date", "umpire_hp_id",
            "stand", "count_class", "pitch_group", "velo", "x_mid", "zn", "d", "cs")
  df <- arrow::open_dataset(mp) |> filter(season == 2024L, abs(d) <= !!BAND_SURF) |>
    select(all_of(cols)) |> collect() |> as.data.frame()
  bad <- c(if (!all(df$season == 2024L)) "a season other than 2024",
           if (max(df$official_date) > DEV_LAST_DATE) "an official date after 2024",
           if (!identical(sort(unique(as.character(df$analysis_set))), "open")) "an analysis set other than open")
  if (length(bad) > 0L) stop("the recovery guard refused the sample: ", paste(bad, collapse = "; "), call. = FALSE)
  df <- df[order(df$pitch_uid), , drop = FALSE]
  rownames(df) <- NULL
  df
}

rec_factors <- function(df, season = NULL) {
  df$count_class <- factor(as.character(df$count_class), levels = CC_LEVELS)
  df$stand <- factor(as.character(df$stand), levels = STAND_LEVELS)
  df$pitch_group <- factor(as.character(df$pitch_group), levels = PG_LEVELS)
  df$count_class_o <- factor(df$count_class, levels = CC_LEVELS, ordered = TRUE)
  df$stand_o <- factor(df$stand, levels = STAND_LEVELS, ordered = TRUE)
  if (!is.null(season)) {
    df$season <- factor(season, levels = REC_SEASONS)
    df$season_o <- factor(season, levels = REC_SEASONS, ordered = TRUE)
  }
  df
}

fit_bam <- function(txt, df) {
  suppressPackageStartupMessages(library(mgcv))
  pt0 <- proc.time()
  m <- suppressWarnings(bam(as.formula(txt), data = df, family = binomial(), discrete = TRUE, method = "fREML"))
  list(m = m, elapsed = unname((proc.time() - pt0)[["elapsed"]]))
}

# The 2024 reference mix: six (count class, handedness) cells, each with NQ quantiles of the
# pitch-group-and-velocity shift on the logit scale, random effects set to zero.
rec_mix <- function(m, ref, season, re_terms, dummies) {
  velo_ref <- stats::median(ref$velo)
  base <- data.frame(x_mid = 0, zn = ZN_MID, pitch_group = ref$pitch_group, velo = ref$velo,
                     count_class = ref$count_class, stand = ref$stand)
  base <- rec_factors(cbind(base, dummies), season)
  base0 <- base
  base0$pitch_group <- factor(PG_LEVELS[1], levels = PG_LEVELS)
  base0$velo <- velo_ref
  delta <- predict(m, base, exclude = re_terms) - predict(m, base0, exclude = re_terms)
  cell <- paste(ref$count_class, ref$stand, sep = "|")
  probs <- (seq_len(NQ) - 0.5) / NQ
  cells <- lapply(split(seq_along(cell), cell), function(i) {
    list(cc = as.character(ref$count_class[i[1]]), st = as.character(ref$stand[i[1]]),
         w = length(i) / nrow(ref), q = unname(stats::quantile(delta[i], probs, type = 7)))
  })
  list(cells = cells, velo_ref = velo_ref)
}

cell_frame <- function(pts, mix, cl, season, dummies) {
  nd <- data.frame(x_mid = pts$x_mid, zn = pts$zn, pitch_group = PG_LEVELS[1], velo = mix$velo_ref,
                   count_class = cl$cc, stand = cl$st)
  rec_factors(cbind(nd, dummies[rep(1L, nrow(nd)), , drop = FALSE]), season)
}

rec_surface <- function(m, mix, season, re_terms, dummies, warp = NULL) {
  pts <- rbind(expand.grid(x_mid = XG, zn = ZG), data.frame(x_mid = XG, zn = ZN_MID))
  ev <- if (is.null(warp)) pts else warp(pts)
  p <- numeric(nrow(pts))
  for (cl in mix$cells) {
    eta <- predict(m, cell_frame(ev, mix, cl, season, dummies), exclude = re_terms)
    p <- p + cl$w * rowMeans(plogis(outer(eta, cl$q, "+")))
  }
  ng <- length(XG) * length(ZG)
  list(grid = matrix(p[seq_len(ng)], nrow = length(XG)), line = p[ng + seq_along(XG)])
}

crossing <- function(v, s, j0, step) {
  if (is.na(v[j0]) || v[j0] <= 0) return(NA_real_)
  idx <- if (step > 0) seq.int(j0 + 1L, length(v)) else seq.int(j0 - 1L, 1L)
  k <- which(v[idx] <= 0)[1]
  if (is.na(k)) return(NA_real_)
  j_out <- idx[k]
  j_in <- j_out - step
  s[j_in] + (s[j_out] - s[j_in]) * v[j_in] / (v[j_in] - v[j_out])
}
edge_metrics <- function(s) {
  lp <- unname(qlogis(s$grid))
  ll <- unname(qlogis(s$line))
  tops <- vapply(I_CENTRE, function(i) crossing(lp[i, ], ZG, J_MID_HI, +1L), 0)
  bots <- vapply(I_CENTRE, function(i) crossing(lp[i, ], ZG, J_MID_LO, -1L), 0)
  xr <- crossing(ll, XG, I_ZERO, +1L)
  xl <- crossing(ll, XG, I_ZERO, -1L)
  c(top_in = mean(tops) * REF_HEIGHT_IN, bot_in = mean(bots) * REF_HEIGHT_IN,
    half_width_in = (xr - xl) / 2 * 12)
}

make_warp <- function(ref_met) {
  top0 <- ref_met[["top_in"]] / REF_HEIGHT_IN
  bot0 <- ref_met[["bot_in"]] / REF_HEIGHT_IN
  hw0  <- ref_met[["half_width_in"]] / 12
  top1 <- top0 + INJ_IN[["top_in"]] / REF_HEIGHT_IN
  bot1 <- bot0 + INJ_IN[["bot_in"]] / REF_HEIGHT_IN
  hw1  <- hw0 + INJ_IN[["half_width_in"]] / 12
  # a point (x, zn) of the deformed season is scored where the generating surface sits at (x', zn')
  function(pts) {
    z <- pts$zn
    zp <- ifelse(z >= top1, z - top1 + top0, ifelse(z <= bot1, z - bot1 + bot0,
                                                    bot0 + (z - bot1) * (top0 - bot0) / (top1 - bot1)))
    ax <- abs(pts$x_mid)
    axp <- ifelse(ax >= hw1, ax - hw1 + hw0, ax * hw0 / hw1)
    data.frame(x_mid = sign(pts$x_mid) * axp, zn = zp)
  }
}

rec_prepare <- function() {
  ensure_dir(REC_DIR)
  mp <- mart_path()
  rows <- load_rec_rows(mp)
  k <- frozen_k()
  g <- rec_factors(rows)
  g$umpire_hp_id <- factor(g$umpire_hp_id)
  gf <- fit_bam(gen_formula(k), g)
  dummies <- data.frame(umpire_hp_id = factor(levels(g$umpire_hp_id)[1], levels = levels(g$umpire_hp_id)))
  mix <- rec_mix(gf$m, g, NULL, "s(umpire_hp_id)", dummies)
  s0 <- rec_surface(gf$m, mix, NULL, "s(umpire_hp_id)", dummies)
  met0 <- edge_metrics(s0)
  warp <- make_warp(met0)
  s1 <- rec_surface(gf$m, mix, NULL, "s(umpire_hp_id)", dummies, warp)
  met1 <- edge_metrics(s1)
  eta0 <- as.vector(predict(gf$m, g))
  gw <- g
  wp <- warp(data.frame(x_mid = g$x_mid, zn = g$zn))
  gw$x_mid <- wp$x_mid
  gw$zn <- wp$zn
  eta1 <- as.vector(predict(gf$m, gw))
  out <- data.frame(pitch_uid = rows$pitch_uid, umpire_hp_id = as.integer(rows$umpire_hp_id),
                    stand = as.character(rows$stand), count_class = as.character(rows$count_class),
                    pitch_group = as.character(rows$pitch_group), velo = rows$velo,
                    x_mid = rows$x_mid, zn = rows$zn, eta_gen = eta0, eta_gen_deformed = eta1,
                    stringsAsFactors = FALSE)
  arrow::write_parquet(out, file.path(REC_DIR, "rows.parquet"))
  truth <- list(generating_formula = gen_formula(k), analysis_formula = rec_formula(k),
                n_rows = nrow(rows), generating_fit_seconds = gf$elapsed,
                generating_2024 = as.list(met0), generating_deformed = as.list(met1),
                injected = as.list(INJ_IN), truth = as.list(met1 - met0),
                mean_p_gen = mean(plogis(eta0)), mean_p_deformed = mean(plogis(eta1)),
                real_cs_rate = mean(rows$cs))
  write_json_file(truth, file.path(REC_DIR, "truth.json"))
  truth
}

# the per-draw edge positions, on narrow windows around the point-estimate crossings
draw_edges <- function(m, mix, season, dummies, met, B) {
  zt <- met[["top_in"]] / REF_HEIGHT_IN; zb <- met[["bot_in"]] / REF_HEIGHT_IN; hw <- met[["half_width_in"]] / 12
  zwt <- ZG[abs(ZG - zt) <= WIN_ZN + 1e-9]
  zwb <- rev(ZG[abs(ZG - zb) <= WIN_ZN + 1e-9])
  xr <- XG[abs(XG - hw) <= WIN_X + 1e-9]
  xl <- rev(XG[abs(XG + hw) <= WIN_X + 1e-9])
  xc <- XG[I_CENTRE]
  pts <- rbind(expand.grid(zn = zwt, x_mid = xc)[, c("x_mid", "zn")],
               expand.grid(zn = zwb, x_mid = xc)[, c("x_mid", "zn")],
               data.frame(x_mid = xr, zn = ZN_MID), data.frame(x_mid = xl, zn = ZN_MID))
  re <- c("s(umpire_hp_id)", "s(umpire_season)")
  P <- matrix(0, nrow(pts), nrow(B))
  for (cl in mix$cells) {
    X <- predict(m, cell_frame(pts, mix, cl, season, dummies), type = "lpmatrix", exclude = re)
    E <- X %*% t(B)
    acc <- matrix(0, nrow(E), ncol(E))
    for (q in cl$q) acc <- acc + plogis(E + q)
    P <- P + cl$w * acc / length(cl$q)
  }
  L <- qlogis(P)
  first_cross <- function(v, s) {
    if (v[1] <= 0) return(NA_real_)
    k <- which(v <= 0)[1]
    if (is.na(k)) return(NA_real_)
    s[k - 1L] + (s[k] - s[k - 1L]) * v[k - 1L] / (v[k - 1L] - v[k])
  }
  nt <- length(zwt); nb <- length(zwb); nc <- length(xc)
  o_t <- 0L; o_b <- nt * nc; o_r <- o_b + nb * nc; o_l <- o_r + length(xr)
  res <- t(vapply(seq_len(ncol(L)), function(j) {
    v <- L[, j]
    tops <- vapply(seq_len(nc), function(i) first_cross(v[o_t + (i - 1L) * nt + seq_len(nt)], zwt), 0)
    bots <- vapply(seq_len(nc), function(i) first_cross(v[o_b + (i - 1L) * nb + seq_len(nb)], zwb), 0)
    r <- first_cross(v[o_r + seq_along(xr)][order(xr)], sort(xr))
    l <- first_cross(v[o_l + seq_along(xl)], xl)
    c(top_in = mean(tops) * REF_HEIGHT_IN, bot_in = mean(bots) * REF_HEIGHT_IN, half_width_in = (r - l) / 2 * 12)
  }, numeric(3)))
  res
}

run_recovery_rep <- function(kind, l) {
  stopifnot(kind %in% c("inject", "null"))
  ensure_dir(file.path(REC_DIR, kind))
  out <- file.path(REC_DIR, kind, sprintf("rep%03d.json", l))
  if (file.exists(out)) return(invisible(NULL))
  suppressPackageStartupMessages(library(mgcv))
  rows <- as.data.frame(arrow::read_parquet(file.path(REC_DIR, "rows.parquet")))
  truth <- fromJSON(file.path(REC_DIR, "truth.json"))
  k <- frozen_k()
  seed <- REC_SEED + (if (kind == "null") 1000L else 0L) + l
  set.seed(seed)
  n <- nrow(rows)
  cs24 <- as.integer(stats::runif(n) < plogis(rows$eta_gen))
  cs26 <- as.integer(stats::runif(n) < plogis(if (kind == "inject") rows$eta_gen_deformed else rows$eta_gen))
  df <- rbind(cbind(rows, cs = cs24, season = "2024"), cbind(rows, cs = cs26, season = "2026"))
  df$umpire_season <- factor(paste(df$umpire_hp_id, df$season, sep = "_"))
  df$umpire_hp_id <- factor(df$umpire_hp_id)
  df <- rec_factors(df, df$season)
  ft <- fit_bam(rec_formula(k), df)
  m <- ft$m
  pt0 <- proc.time()
  dummies <- data.frame(umpire_hp_id = factor(levels(df$umpire_hp_id)[1], levels = levels(df$umpire_hp_id)),
                        umpire_season = factor(levels(df$umpire_season)[1], levels = levels(df$umpire_season)))
  re <- c("s(umpire_hp_id)", "s(umpire_season)")
  ref <- df[df$season == "2024", ]
  mix <- rec_mix(m, ref, "2024", re, dummies)
  met <- lapply(REC_SEASONS, function(se) edge_metrics(rec_surface(m, mix, se, re, dummies)))
  names(met) <- REC_SEASONS
  est <- met[["2026"]] - met[["2024"]]
  set.seed(seed + 7L)
  B <- MASS::mvrnorm(REC_DRAWS, stats::coef(m), m$Vp)
  d24 <- draw_edges(m, mix, "2024", dummies, met[["2024"]], B)
  d26 <- draw_edges(m, mix, "2026", dummies, met[["2026"]], B)
  dd <- d26 - d24
  ok <- stats::complete.cases(dd)
  ci <- apply(dd[ok, , drop = FALSE], 2, stats::quantile, c(0.025, 0.975), names = FALSE)
  ci90 <- apply(dd[ok, , drop = FALSE], 2, stats::quantile, c(0.05, 0.95), names = FALSE)
  tr <- if (kind == "inject") unlist(truth$truth)[names(INJ_IN)] else setNames(c(0, 0, 0), names(INJ_IN))
  res <- list(kind = kind, rep = l, seed = seed, n_rows = nrow(df), fit_seconds = ft$elapsed,
              interval_seconds = unname((proc.time() - pt0)[["elapsed"]]), n_draws = REC_DRAWS,
              n_draws_complete = sum(ok),
              truth = as.list(tr), estimate = as.list(est[names(INJ_IN)]),
              lo95 = as.list(setNames(ci[1, ], names(INJ_IN))), hi95 = as.list(setNames(ci[2, ], names(INJ_IN))),
              covers = as.list(setNames(ci[1, ] <= tr & tr <= ci[2, ], names(INJ_IN))),
              lo90 = as.list(setNames(ci90[1, ], names(INJ_IN))), hi90 = as.list(setNames(ci90[2, ], names(INJ_IN))),
              equivalent = as.list(setNames(ci90[1, ] - tr >= -REC_TOL_IN & ci90[2, ] - tr <= REC_TOL_IN, names(INJ_IN))),
              within_tol = as.list(abs(est[names(INJ_IN)] - tr) <= REC_TOL_IN),
              level_2024 = as.list(met[["2024"]]), level_2026 = as.list(met[["2026"]]))
  write_json_file(res, out)
  cat(sprintf("recovery %s %d: est %s, fit %.0f s, intervals %.0f s\n", kind, l,
              paste(sprintf("%.3f", est), collapse = " "), ft$elapsed, res$interval_seconds))
}

score_recovery <- function() {
  rd <- function(kind) {
    f <- sort(list.files(file.path(REC_DIR, kind), pattern = "^rep\\d{3}\\.json$", full.names = TRUE))
    lapply(f, fromJSON)
  }
  inj <- rd("inject"); nul <- rd("null")
  q <- names(INJ_IN)
  summ <- function(reps) {
    if (length(reps) == 0L) return(NULL)
    est <- do.call(rbind, lapply(reps, function(r) unlist(r$estimate)[q]))
    tr <- do.call(rbind, lapply(reps, function(r) unlist(r$truth)[q]))
    cov <- do.call(rbind, lapply(reps, function(r) unlist(r$covers)[q]))
    wt <- do.call(rbind, lapply(reps, function(r) unlist(r$within_tol)[q]))
    eqv <- do.call(rbind, lapply(reps, function(r) unlist(r$equivalent)[q]))
    lo <- do.call(rbind, lapply(reps, function(r) unlist(r$lo95)[q]))
    hi <- do.call(rbind, lapply(reps, function(r) unlist(r$hi95)[q]))
    # excludes_zero is the 95% interval against zero: power on the injected arm, the false
    # positive on the null arm. It was colSums(!cov), the miss count, which equals it only
    # where the truth is zero and read as "9 of 100 detected" on the injected arm.
    list(n = length(reps), bias = colMeans(est - tr), mean_abs_err = colMeans(abs(est - tr)),
         covers = colSums(cov), misses = colSums(!cov), within_tol = colSums(wt),
         excludes_zero = colSums(lo > 0 | hi < 0), equivalent = colSums(eqv),
         fit_seconds = mean(vapply(reps, function(r) r$fit_seconds, 0)))
  }
  list(inject = summ(inj), null = summ(nul))
}

## --- the CH1-A6 table that docs/prereg/ch1.md carries ------------------------------------------------
# --check regenerates these lines from the raw draws and requires each one, byte for byte,
# in docs/prereg/ch1.md.

TAU_CH <- "τ"
GE <- "≥"
prereg_table_lines <- function(th, bc) {
  est <- th$estimator
  cv <- bc$curve[bc$curve$estimator == est, ]
  cv <- cv[order(as.numeric(cv$tau_true_in)), ]
  grid <- paste(cv$tau_true_in, collapse = " / ")
  fr <- paste(sprintf("%d/5", cv$n_fired), collapse = ", ")
  fc <- th$fired_of_5[[sprintf("%.2f", th$c_star_in)]]
  lines <- c(
    "| CH1-A6 item | pre-registered value |",
    "|---|---|",
    sprintf("| estimator that sets the thresholds | `%s`: %s |", est, EST_LABEL[[est]]),
    sprintf("| materiality rule | material only if P(%s %s %.2f in) %s %.2f |", TAU_CH, GE, th$c_star_in, GE, th$prob),
    sprintf("| firing rate of the rule at %s = %s in | %s |", TAU_CH, grid, fr),
    sprintf("| 95%% interval for %s covers the true %s, at %s = %s in | %s |", TAU_CH, TAU_CH, TAU_CH, grid,
            paste(cv$ci95_covers_truth, collapse = ", ")),
    sprintf("| one-sided 95%% upper bound at or above the true %s, at %s = %s in | %s |", TAU_CH, TAU_CH, grid,
            paste(cv$upper95_covers_truth, collapse = ", ")),
    sprintf("| powered for the materiality claim | %s: %d of 5 seeds fire at %s = 0.30 in, %d of 5 at %s = 0.10 in |",
            if (isTRUE(th$powered)) "yes" else "no", fc[3], TAU_CH, fc[1], TAU_CH),
    sprintf("| variance-components reliability of the response at %s = %s in | %s |", TAU_CH, grid,
            paste(cv$reliability_vc_response_mean, collapse = " / ")),
    sprintf("| split-half reliability of the response at %s = %s in | %s |", TAU_CH, grid,
            paste(cv$split_half_response_mean, collapse = " / ")),
    sprintf("| reliability gate attainable | %s |", if (isTRUE(th$reliability_gate_attainable))
      sprintf("yes, at %s = %.2f in", TAU_CH, th$tau_attainable) else "no"),
    sprintf("| per-umpire table | %s |", th$table_rule),
    sprintf("| reportable result when the rule does not fire | %s; the curve's mean 95%% upper bound is %s in at %s = %s in |",
            th$reportable_if_not_fired, paste(sprintf("%.3f", unlist(th$expected_upper95_in)), collapse = " / "),
            TAU_CH, grid),
    sprintf("| bounded null is the primary reportable result | %s |", if (isTRUE(th$bounded_null_primary)) "yes" else "no"))
  lines
}

## --- worker dispatch --------------------------------------------------------------------------------

if (MODE == "--worker") {
  kind <- args[2]
  if (kind == "power") {
    tau <- as.numeric(args[3]); seed <- as.integer(args[4]); est <- args[5]
    stopifnot(est %in% ESTIMATORS)
    res <- run_power_seed(tau, seed, est, file.path(POWER_DIR, est, seed_tag(tau, seed)))
    cat(sprintf("power %s %s: P(tau >= 0.20) = %.4f, split-half %.3f, %.0f s B2\n", est, seed_tag(tau, seed),
                res$p_tau_ge[["0.20"]], res$split_half$sb_response, res$b2_seconds))
    quit(status = 0)
  }
  if (kind == "sbc") {
    run_sbc_reps(args[5], as.integer(args[3]), as.integer(args[4]))
    quit(status = 0)
  }
  if (kind == "recovery") {
    run_recovery_rep(args[3], as.integer(args[4]))
    quit(status = 0)
  }
  stop("unknown worker kind: ", kind, call. = FALSE)
}

## --- build: part (c) -------------------------------------------------------------------------------

prepare_inputs <- function() {
  ensure_dir(OUT_DIR)
  writeLines(c("# Pre-tag development output of SOP W3.12. Never committed. See R/ch1/21_synthetic.R.", "*"),
             file.path(OUT_DIR, ".gitignore"))
  mp <- mart_path()
  dev <- load_outcome_dev(mp)
  record("outcome read, 2022-2024, |d| <= 8 in", sprintf("%s pitches, seasons %s, last date %s",
         comma(nrow(dev)), paste(sort(unique(dev$season)), collapse = " "), max(dev$official_date)))
  lk <- fit_links(dev)
  for (e in EDGE_LEVELS) {
    i <- lk$info[[e]]
    record(sprintf("link %s", e), sprintf("50%% point at d = %.3f in, slope %.3f logit/in there, linear-glm slope on |d| <= 3 in %.3f, monotone on [-7, 7] %s",
                                          i$d50_in, i$slope_at_d50_logit_per_in, i$glm_linear_slope_shadow, i$monotone_on_pm7))
  }
  arrow::write_parquet(data.frame(u = lk$u, lk$lp), file.path(OUT_DIR, "link.parquet"))
  lut <- make_lut(lk$lp)
  des <- load_design(mp)
  record("design read, 2022-2026, |d| <= 3 in, no call", sprintf("%s pitches, %d umpires, %s games",
         comma(nrow(des)), length(unique(des$umpire_hp_id)), comma(length(unique(des$game_pk)))))
  arrow::write_parquet(des, file.path(OUT_DIR, "design.parquet"))
  # calibration: B1 on real 2022-2024 shadow-band calls, then the variance components
  s3 <- dev[abs(dev$d) <= BAND_SHADOW, ]
  base <- lut_base(match(as.character(s3$edge), EDGE_LEVELS), s3$d, lut)
  kk <- data.frame(umpire_hp_id = as.integer(s3$umpire_hp_id), season = as.integer(s3$season),
                   edge = as.character(s3$edge), stringsAsFactors = FALSE)
  b1r <- b1_cells(kk, base, as.integer(s3$cs), lut)
  data.table::fwrite(b1r, file.path(OUT_DIR, "calibration_b1_2022_2024.csv"))
  cd <- b1r[b1r$n >= N_MIN_CELL & !b1r$at_bound & is.finite(b1r$se_delta), ]
  cd$edge <- factor(cd$edge, levels = EDGE_LEVELS)
  cd$season <- factor(cd$season)
  cd$umpire_hp_id <- factor(cd$umpire_hp_id)
  record("calibration B1 cells", sprintf("%d of %d umpire-season-edge cells kept (n >= %d, not at the grid bound), median se %.3f in",
                                         nrow(cd), nrow(b1r), N_MIN_CELL, stats::median(cd$se_delta)))
  load_brms()
  ft <- fit_brms(CAL_FORMULA_TEXT, cd, cal_priors())
  dr <- posterior::as_draws_df(ft$fit)
  qs <- function(v) as.list(setNames(stats::quantile(v, c(0.05, 0.5, 0.95), names = FALSE), c("q05", "median", "q95")))
  comp <- list(sd_level = qs(dr[["sd_umpire_hp_id__Intercept"]]),
               sd_ump_edge = qs(dr[["sd_umpire_hp_id:edge__Intercept"]]),
               sd_ump_season = qs(dr[["sd_umpire_hp_id:season__Intercept"]]),
               sigma_resid = qs(dr[["sigma"]]))
  nm <- names(dr)
  dg <- diagnostics(ft$fit, c(grep("^b_", nm, value = TRUE), grep("^sd_", nm, value = TRUE), "sigma"))
  dgp <- lapply(comp, function(x) round(x$median, 4))
  cal <- list(window = "2022-2024 regular season, shadow band |d| <= 3.0 in, calls read",
              formula = CAL_FORMULA_TEXT, n_cells = nrow(cd), components = comp, diagnostics = dg,
              dgp = dgp, links = lk$info, seconds = ft$elapsed)
  write_json_file(cal, file.path(OUT_DIR, "calibration.json"))
  for (k in names(comp)) record(sprintf("calibration %s", k), sprintf("median %.3f in, 90%% interval %.3f to %.3f",
                                                                      comp[[k]]$median, comp[[k]]$q05, comp[[k]]$q95))
  record("calibration diagnostics", sprintf("divergent %d, rhat max %.4f, ess bulk min %.0f",
                                            dg$divergent, dg$rhat_max, dg$ess_bulk_min))
  # SBC design: the real B2 layout with each cell's analytic SE
  des$base <- lut_base(match(des$edge, EDGE_LEVELS), des$d, lut)
  ensure_dir(SBC_DIR)
  sd <- sbc_design(des, lut)
  utils::write.csv(sd, file.path(SBC_DIR, "sbc_design.csv"), row.names = FALSE)
  record("SBC design", sprintf("%d cells, %d umpires, median analytic se %.3f in", nrow(sd),
                               length(unique(sd$umpire_hp_id)), stats::median(sd$se_delta)))
  invisible(cal)
}

compile_models <- function() {
  load_brms()
  # One small fit per model compiles it into STAN_DIR, so workers never compile at once.
  sd <- utils::read.csv(file.path(SBC_DIR, "sbc_design.csv"), stringsAsFactors = FALSE)
  sd$delta <- 0
  sd$edge <- factor(sd$edge, levels = EDGE_LEVELS)
  sd$buf_step <- as.numeric(sd$season >= 2025)
  sd$abs_step <- as.numeric(sd$season == 2026)
  sd$umpire_hp_id <- factor(sd$umpire_hp_id)
  sd$season <- factor(sd$season)
  for (est in ESTIMATORS) suppressMessages(suppressWarnings(
    brms::brm(brms::bf(as.formula(EST_FORMULA[[est]])), data = sd, family = gaussian(),
              prior = b2_priors(), chains = 1, iter = 20, warmup = 10, backend = "cmdstanr",
              seed = STAN_SEED, refresh = 0, silent = 2)))
  invisible(TRUE)
}

if (MODE == "--power") {
  cat("W3.12 part (c): the D-60 power curve\n")
  if (!file.exists(file.path(OUT_DIR, "calibration.json")) || "--fresh" %in% args) invisible(prepare_inputs())
  compile_models()
  jobs <- list()
  for (est in ESTIMATORS) for (t in TAUS) for (s in seq_len(N_SEEDS)) {
    if (file.exists(file.path(POWER_DIR, est, seed_tag(t, s), "summary.json"))) next
    jobs[[length(jobs) + 1L]] <- list(tag = paste(est, seed_tag(t, s), sep = "_"),
                                      args = c("power", sprintf("%.2f", t), s, est))
  }
  st <- run_workers(jobs, file.path(POWER_DIR, "logs"))
  wc <- write_curve()
  print(wc$curve[, c("estimator", "tau_true_in", "n_fired", "firing_rate", "ci95_covers_truth",
                     "split_half_response_mean", "reliability_vc_response_mean",
                     "tau_post_median_mean_in", "tau_upper95_mean_in", "sets_ch1_a6")])
  cat(toJSON(wc$thresholds, auto_unbox = TRUE, pretty = TRUE), "\n")
  quit(status = 0)
}

if (MODE == "--curve") {
  wc <- write_curve()
  print(wc$curve)
  cat(toJSON(wc$thresholds, auto_unbox = TRUE, pretty = TRUE), "\n")
  if (wc$primary %in% ESTIMATORS) {
    tl <- prereg_table_lines(wc$thresholds, build_curve())
    writeLines(tl, file.path(POWER_DIR, "ch1_a6_table.md"), useBytes = TRUE)
    cat("\nCH1-A6 table for docs/prereg/ch1.md:\n", paste(tl, collapse = "\n"), "\n", sep = "")
  }
  quit(status = 0)
}

if (MODE == "--sbc") {
  cat("W3.12 part (b): simulation-based calibration of the B2 model\n")
  if (!file.exists(file.path(SBC_DIR, "sbc_design.csv"))) invisible(prepare_inputs())
  est <- if (length(args) >= 2L) args[2] else "sop"
  npar <- if (length(args) >= 3L) as.integer(args[3]) else MAX_PAR
  stopifnot(est %in% ESTIMATORS)
  compile_models()
  per <- ceiling(SBC_L / npar)
  jobs <- lapply(seq_len(npar), function(i) {
    a <- (i - 1L) * per + 1L
    b <- min(i * per, SBC_L)
    list(tag = sprintf("sbc_%s_%03d_%03d", est, a, b), args = c("sbc", a, b, est))
  })
  run_workers(jobs, file.path(SBC_DIR, "logs"), max_par = npar)
  sc <- score_sbc(est)
  for (q in SBC_QUANTITIES) record(sprintf("SBC %s %s", est, q), sprintf("chi-square p %.4f, BH p %.4f, ECDF inside band %s",
                                                                  sc$p_chisq[[q]], sc$p_bh[[q]], sc$ecdf_inside[[q]]))
  quit(status = 0)
}

if (MODE == "--recovery") {
  cat("W3.12 part (a): injected-effect recovery\n")
  n_inj <- if (length(args) >= 2L) as.integer(args[2]) else REC_N_INJECT
  n_nul <- if (length(args) >= 3L) as.integer(args[3]) else REC_N_NULL
  npar <- if (length(args) >= 4L) as.integer(args[4]) else REC_MAX_PAR
  if (!file.exists(file.path(REC_DIR, "truth.json"))) {
    tr <- rec_prepare()
    record("recovery generating fit", sprintf("%s rows, %.0f s", comma(tr$n_rows), tr$generating_fit_seconds))
  }
  tr <- fromJSON(file.path(REC_DIR, "truth.json"))
  for (q in names(INJ_IN)) record(sprintf("recovery truth %s", q), sprintf("%.4f in (injected %.2f)", tr$truth[[q]], INJ_IN[[q]]))
  jobs <- c(lapply(seq_len(n_inj), function(l) list(tag = sprintf("inject_%03d", l), args = c("recovery", "inject", l))),
            lapply(seq_len(n_nul), function(l) list(tag = sprintf("null_%03d", l), args = c("recovery", "null", l))))
  jobs <- Filter(function(j) !file.exists(file.path(REC_DIR, j$args[2], sprintf("rep%03d.json", as.integer(j$args[3])))), jobs)
  run_workers(jobs, file.path(REC_DIR, "logs"), max_par = npar)
  sc <- score_recovery()
  print(sc)
  quit(status = 0)
}

if (MODE == "--check") {
  cat("W3.12 check: the D-60 power curve, the CH1-A6 thresholds, SBC and recovery\n")
  # 1. the raw per-seed output: five seeds per cell, 4,000 draws each
  for (est in ESTIMATORS) {
    got <- 0L; nd <- integer(0)
    for (t in TAUS) for (s in seq_len(N_SEEDS)) {
      x <- read_seed_raw(t, s, est)
      if (!is.null(x)) { got <- got + 1L; nd <- c(nd, nrow(x$draws)) }
    }
    check(sprintf("five seeds per cell, %s", est), got == length(TAUS) * N_SEEDS && all(nd == 4000L),
          sprintf("%d of %d seed directories, draws per seed %s", got, length(TAUS) * N_SEEDS,
                  paste(unique(nd), collapse = " ")))
  }
  check("ch1_power_curve.csv present", file.exists(CURVE_CSV), CURVE_CSV)
  if (length(failures) > 0L) finish()
  # 2. the CSV equals a rebuild from the raw draws
  bc <- build_curve()
  disk <- utils::read.csv(CURVE_CSV, colClasses = "character", check.names = FALSE)
  reb <- bc$curve
  reb[] <- lapply(reb, as.character)
  same <- identical(dim(disk), dim(reb)) && identical(names(disk), names(reb)) &&
    all(as.matrix(disk) == as.matrix(reb))
  check("ch1_power_curve.csv equals the rebuild from raw draws", same,
        sprintf("%d rows x %d columns", nrow(reb), ncol(reb)))
  for (i in seq_len(nrow(reb))) {
    r <- reb[i, ]
    record(sprintf("curve %s tau %s", r$estimator, r$tau_true_in),
           sprintf("fired %s (%s), P(tau>=0.20) %s, 95%% CI covers %s, split-half %s, VC %s",
                   r$n_fired, r$fired_by_seed, r$p_tau_ge_020_by_seed, r$ci95_covers_truth,
                   r$split_half_response_mean, r$reliability_vc_response_mean))
  }
  cov <- unlist(bc$cover)
  record("estimator coverage of 15", paste(sprintf("%s %d", names(cov), cov), collapse = ", "))
  check("an admissible estimator sets CH1-A6", bc$primary %in% ESTIMATORS,
        sprintf("primary %s (admissible at >= %d of 15)", bc$primary, COVER_MIN))
  if (length(failures) > 0L) finish()
  # 3. the thresholds re-derived from the draws equal thresholds.json
  th <- derive_thresholds(bc$per_seed, bc$primary)
  thj <- fromJSON(file.path(POWER_DIR, "thresholds.json"))
  keys <- c("estimator", "c_star_in", "prob", "powered", "r_star_vc", "r_star_split_half",
            "reliability_gate_attainable", "table_rule", "reportable_if_not_fired", "bounded_null_primary")
  norm <- function(x) if (is.null(x) || length(x) == 0L || (length(x) == 1L && (is.na(x) || identical(x, "NA")))) "NA" else as.character(x)
  eq <- vapply(keys, function(k) identical(norm(th[[k]]), norm(thj[[k]])), TRUE)
  check("thresholds.json equals the re-derivation", all(eq),
        if (all(eq)) sprintf("c* %.2f in, powered %s, gate attainable %s", th$c_star_in, th$powered,
                             th$reliability_gate_attainable) else paste(keys[!eq], collapse = ", "))
  check("the materiality threshold is one the curve supports",
        !is.na(th$c_star_in) && th$fired_of_5[[sprintf("%.2f", th$c_star_in)]][1] <= FALSE_FIRE_MAX,
        sprintf("P(tau >= %.2f in) >= 0.90 fires in %d of 5 seeds at tau = 0.10 in", th$c_star_in,
                th$fired_of_5[[sprintf("%.2f", th$c_star_in)]][1]))
  # 4. docs/prereg/ch1.md carries the table, line for line
  md <- if (file.exists(PREREG_MD)) readLines(PREREG_MD, warn = FALSE, encoding = "UTF-8") else character(0)
  tl <- prereg_table_lines(th, bc)
  miss <- tl[!tl %in% md]
  check("docs/prereg/ch1.md carries the CH1-A6 table", length(miss) == 0L,
        if (length(miss) == 0L) sprintf("%d table lines present", length(tl)) else paste("missing:", miss[1]))
  # 5. PREREGISTRATION.md, once W7.6 writes it
  if (!file.exists(PREREG_ROOT)) {
    pend("PREREGISTRATION.md carries CH1-A6", "PREREGISTRATION.md does not exist yet; W7.6 writes it")
  } else {
    txt <- readLines(PREREG_ROOT, warn = FALSE, encoding = "UTF-8")
    a6 <- grep("CH1-A6", txt, value = TRUE)
    rule <- sprintf("P(%s %s %.2f in) %s %.2f", TAU_CH, GE, th$c_star_in, GE, th$prob)
    ok <- length(a6) > 0L && all(grepl("docs/prereg/ch1.md", a6, fixed = TRUE) | grepl(rule, a6, fixed = TRUE))
    check("PREREGISTRATION.md carries CH1-A6 as the curve implies", ok,
          sprintf("%d CH1-A6 lines, each cites docs/prereg/ch1.md or states %s", length(a6), rule))
  }
  # 6. the design read carries no call, and the cached design equals a fresh read
  mp <- mart_path()
  des <- load_design(mp)
  cached <- as.data.frame(arrow::read_parquet(file.path(OUT_DIR, "design.parquet")))
  check("design read selects no outcome column", !any(c("cs", "challenged", "is_overturned") %in% names(des)),
        paste(names(des), collapse = " "))
  check("cached design equals a fresh read", isTRUE(all.equal(des, cached, check.attributes = FALSE)),
        sprintf("%s pitches, seasons %s", comma(nrow(des)), paste(sort(unique(des$season)), collapse = " ")))
  cb <- utils::read.csv(file.path(OUT_DIR, "calibration_b1_2022_2024.csv"))
  check("calibration cells are 2022-2024 only", all(cb$season %in% DEV_SEASONS),
        sprintf("%d cells, seasons %s", nrow(cb), paste(sort(unique(cb$season)), collapse = " ")))
  # 7. one seed, end to end, reproduces the stored draws
  tmp <- tempfile("w312_check_")
  invisible(run_power_seed(0.20, 2L, bc$primary, tmp))
  a <- utils::read.csv(file.path(tmp, "tau_draws.csv.gz"))
  b <- read_seed_raw(0.20, 2L, bc$primary)$draws
  b1a <- utils::read.csv(file.path(tmp, "b1_full.csv.gz"))
  b1b <- utils::read.csv(file.path(POWER_DIR, bc$primary, seed_tag(0.20, 2L), "b1_full.csv.gz"))
  check(sprintf("re-run of %s tau 0.20 seed 2 reproduces B1", bc$primary),
        isTRUE(all.equal(b1a, b1b, tolerance = 1e-12)), sprintf("%d cells", nrow(b1a)))
  check(sprintf("re-run of %s tau 0.20 seed 2 reproduces the draws", bc$primary),
        nrow(a) == nrow(b) && max(abs(a$tau_abs - b$tau_abs)) < 1e-9,
        sprintf("max abs difference in tau draws %.3g, P(tau >= 0.20) %.4f", max(abs(a$tau_abs - b$tau_abs)),
                mean(a$tau_abs >= RULE_TAU)))
  unlink(tmp, recursive = TRUE)
  # 8. nothing fitted is saved, and no provenance.json exists, under out/dev/ch1_synth
  ff <- list.files(OUT_DIR, recursive = TRUE, all.files = TRUE)
  bad <- ff[tolower(tools::file_ext(ff)) %in% FIT_SUFFIXES | basename(ff) == "provenance.json"]
  check("no fit object or provenance.json under out/dev/ch1_synth", length(bad) == 0L,
        if (length(bad) == 0L) sprintf("%d files scanned", length(ff)) else paste(bad, collapse = " "))
  # 9. SBC, part (b)
  sc <- score_sbc(bc$primary)
  if (is.null(sc) || sc$n < SBC_L) {
    pend("SBC, 200 replicates", sprintf("%d of %d replicates on disk", if (is.null(sc)) 0L else sc$n, SBC_L))
  } else {
    for (q in c("tau_abs", "regime_mean_abs")) {
      check(sprintf("SBC chi-square uniform at 0.05: %s", q), sc$p_chisq[[q]] > SBC_ALPHA,
            sprintf("p = %.4f over %d replicates, %d bins", sc$p_chisq[[q]], sc$n, SBC_BINS))
    }
    check("SBC worst BH-adjusted p > 0.01 (MT-02)", min(sc$p_bh) > 0.01,
          sprintf("worst %.4f (%s)", min(sc$p_bh), names(which.min(sc$p_bh))))
    check("SBC ECDF inside the 95% simultaneous band (MT-02)", all(sc$ecdf_inside),
          if (all(sc$ecdf_inside)) sprintf("%d quantities", length(sc$ecdf_inside)) else
            paste(names(sc$ecdf_inside)[!sc$ecdf_inside], collapse = " "))
    record("SBC divergences", sprintf("%d of %d replicates with any, %d in total", sc$divergent_reps, sc$n,
                                      sc$divergent_total))
  }
  # 10. recovery, part (a)
  rc <- score_recovery()
  ni <- if (is.null(rc$inject)) 0L else rc$inject$n
  nn <- if (is.null(rc$null)) 0L else rc$null$n
  if (ni > 0L) record("recovery injected so far", sprintf("n %d, bias %s, covers %s", ni,
                                                          paste(sprintf("%.3f", rc$inject$bias), collapse = " / "),
                                                          paste(rc$inject$covers, collapse = " / ")))
  if (nn > 0L) record("recovery null so far", sprintf("n %d, interval excludes 0 %s", nn,
                                                      paste(rc$null$excludes_zero, collapse = " / ")))
  if (ni < REC_N_INJECT || nn < REC_N_NULL) {
    pend("recovery, 100 injected and 50 null replicates", sprintf("%d injected and %d null on disk", ni, nn))
  } else {
    record("recovery injected, 95% interval excludes zero", sprintf("%s of %d (power; the misses are %s)",
                                                                    paste(rc$inject$excludes_zero, collapse = " / "), ni,
                                                                    paste(rc$inject$misses, collapse = " / ")))
    nul <- lapply(sort(list.files(file.path(REC_DIR, "null"), pattern = "^rep\\d{3}\\.json$", full.names = TRUE)), fromJSON)
    c90 <- vapply(names(INJ_IN), function(q) sum(vapply(nul, function(r) r$lo90[[q]] <= 0 && 0 <= r$hi90[[q]], TRUE)), 0L)
    record("recovery null, 90% interval covers zero (MT-04)", sprintf("%s of %d", paste(c90, collapse = " / "), nn))
    for (q in names(INJ_IN)) {
      check(sprintf("recovery bias within 0.10 in: %s", q), abs(rc$inject$bias[[q]]) <= REC_TOL_IN,
            sprintf("mean bias %.3f in", rc$inject$bias[[q]]))
      check(sprintf("recovery 95%% coverage >= 93/100: %s", q),
            rc$inject$covers[[q]] >= ceiling(REC_COVER_MIN_SHARE * rc$inject$n),
            sprintf("%d of %d", rc$inject$covers[[q]], rc$inject$n))
      check(sprintf("null false-positive rate <= 7%%: %s", q),
            rc$null$excludes_zero[[q]] / rc$null$n <= REC_FPR_MAX,
            sprintf("%d of %d", rc$null$excludes_zero[[q]], rc$null$n))
      check(sprintf("null 90%% interval inside +/-0.10 in (CH1-A7): %s", q),
            rc$null$equivalent[[q]] >= ceiling(REC_COVER_MIN_SHARE * rc$null$n),
            sprintf("%d of %d", rc$null$equivalent[[q]], rc$null$n))
    }
  }
  finish()
}
