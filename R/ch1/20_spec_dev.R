#!/usr/bin/env Rscript
# R/ch1/20_spec_dev.R - SOP step W3.11, specification development on 2022-2024 only.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/20_spec_dev.R            build: run the development wave, write the
#                                          diagnostics under out/dev/ch1_spec/, report
#   Rscript R/ch1/20_spec_dev.R --check    verify: reload the 2022-2024 sample, refit the
#                                          frozen specification and the rung above it,
#                                          and compare both with docs/prereg/ch1.md and
#                                          out/dev/ch1_spec/. Writes nothing under the
#                                          repository. Exit 1 on any FAIL. This is the
#                                          registered verify command.
#   Rscript R/ch1/20_spec_dev.R --fit <variant> --outdir <dir>
#   Rscript R/ch1/20_spec_dev.R --bench-sop <rows> --outdir <dir>
#                                          workers. The build and check modes start them,
#                                          each under /usr/bin/time -l, so that wall time,
#                                          CPU time and peak resident memory are measured
#                                          by the operating system, not estimated.
#
# THE SPECIFICATION. SOP W3.11:
#
#   cs ~ season + count_class + stand + pitch_group
#      + te(x_mid, zn, bs = c("cr","cr"), k = c(24,24))
#      + te(x_mid, zn, bs = c("cr","cr"), k = c(18,18), by = season)
#      + te(x_mid, zn, bs = c("cr","cr"), k = c(12,12), by = count_class)
#      + te(x_mid, zn, bs = c("cr","cr"), k = c(12,12), by = stand)
#      + s(velo, k = 10) + s(umpire_hp_id, bs = "re") + s(umpire_season, bs = "re")
#
# fitted with mgcv::bam, family binomial, discrete = TRUE, method "fREML".
#
# WHAT THIS STEP SETTLES, and nothing else.
#
# 1. The by-factor coding. Written literally, each by-smooth has one level smooth
#    per factor level beside a main te() over the same covariates. The level
#    smooths then sum to a copy of the main smooth, which is not identifiable. The
#    build fits both codings: the literal one, and ordered copies of the three
#    by-factors (season_o, count_class_o, stand_o), which give one difference smooth
#    per non-reference level. The parametric terms keep the unordered factors and
#    treatment contrasts. The frozen coding is the one this script records in
#    out/dev/ch1_spec/frozen_spec.json, with the reason.
#
# 2. The basis dimension k, by gam.check() and k.check(). The ladder and the rule
#    are fixed here, before any fit:
#      main te       24, 32, 40, 48
#      by season     18, 24, 30, 36
#      by count, by stand (one group, both 12 in the SOP)  12, 16, 20, 24
#      s(velo)       10, 20, 30, 40
#    A group is stable at rung j when every one of its terms changes its k-index by
#    less than KI_STABLE between rung j and rung j + 1, the other groups held at
#    their SOP k. k.check() runs on a seeded sub-sample of KC_SUBSAMPLE rows with
#    KC_REP permutations, so two fits are compared on the same rows.
#
# 3. The re-benchmark. Wall time, user and system CPU time, and peak resident
#    memory for every fit, and a re-run of the SOP's 14.1 s benchmark formula on
#    synthetic data. CPU over wall near 1.0 means one core did the work. bam()
#    is also called with nthreads = 2, once, to record its OpenMP warning.
#
# 4. The secondary estimator. A binned logistic: d in 0.5 in bins over [-8, +8],
#    aggregated to cbind(strikes, balls) per bin x season x count_class x stand x
#    edge, and one binomial glm per edge with the bin as a factor and season,
#    count_class and stand as shifts on the logit. That is one glm with every term
#    interacted with edge. The edge position is the d at which the probability,
#    standardised to the 2024 count and handedness mix, crosses 0.5.
#
# 5. A dry run of the CH1-A5 point clause on a contrast that no acceptance
#    criterion uses: 2023 minus 2022. CH1-A3's placebo is 2023 to 2024, so no 2024
#    surface is evaluated here, and no 2023-to-2024 difference is computed.
#
# 6. A baseline table, on a game-level holdout inside 2022-2024: the league base
#    rate, the ABS rulebook zone as a two-rate classifier, the pooled surface of
#    W3.4, the binned logistic, and the specification.
#
# WHAT IT READS. data/marts/ch1_called.parquet (W3.7) through one arrow scan whose
# filter keeps seasons 2022, 2023 and 2024. No 2025 or 2026 row reaches R. The
# loader asserts the seasons, the last official date, the regime and the analysis
# set before any fit runs. It also reads out/ch1/tab/T1_sample.csv for one count,
# the five-season surface-sample size used by the scale benchmark.
#
# WHAT IT WRITES. Only under out/dev/ch1_spec/, which carries its own .gitignore:
# JSON, CSV, text, PNG and logs. No fitted model object is saved anywhere. GD-01
# fails on any .rds under out/ without a provenance.json beside it, and GD-12
# fails on any provenance.json before prereg-v1 is pushed, so a development fit
# cannot be cached under out/ without breaking one of the two. No
# provenance.json, nothing under out/models/ or out/ch1/log/. Check mode writes
# only to a temporary directory.
#
# Exit 0 when every check passes, 1 when any fails, 2 on a usage error.

options(warn = 1, digits = 12)
t_start <- Sys.time()

args_all <- commandArgs(trailingOnly = FALSE)
args <- commandArgs(trailingOnly = TRUE)

usage <- function() {
  cat("usage: Rscript R/ch1/20_spec_dev.R [--check]\n",
      "       Rscript R/ch1/20_spec_dev.R --fit <variant> --outdir <dir>\n",
      "       Rscript R/ch1/20_spec_dev.R --bench-sop <rows> --outdir <dir>\n",
      file = stderr(), sep = "")
  quit(status = 2)
}
arg_value <- function(flag) {
  i <- match(flag, args)
  if (is.na(i) || i == length(args)) usage()
  args[i + 1L]
}
MODE <- if (length(args) == 0L) {
  "build"
} else if (identical(args, "--check")) {
  "check"
} else if ("--fit" %in% args && "--outdir" %in% args && length(args) == 4L) {
  "fit"
} else if ("--bench-sop" %in% args && "--outdir" %in% args && length(args) == 4L) {
  "bench"
} else {
  usage()
}

file_arg <- grep("^--file=", args_all, value = TRUE)
SELF <- if (length(file_arg) == 1L) normalizePath(sub("^--file=", "", file_arg)) else
  normalizePath("R/ch1/20_spec_dev.R")
ROOT <- normalizePath(file.path(dirname(SELF), "..", ".."))
setwd(ROOT)

suppressPackageStartupMessages({
  library(arrow)
  library(dplyr)
  library(mgcv)
  library(jsonlite)
})
source("R/lib/zone.R")

## --- constants, fixed before any fit ---------------------------------------------

DEV_SEASONS    <- 2022:2024                 # the development window; never 2025 or 2026
DEV_LAST_DATE  <- as.Date("2024-12-31")
DEV_REGIME     <- "pre_buffer"
SEASON_LEVELS  <- as.character(DEV_SEASONS)
REF_SEASON     <- "2024"                    # SOP W3.14: the 2024 pitch mix is the reference
DRY_SEASONS    <- c("2022", "2023")         # the CH1-A5 dry-run contrast, 2023 minus 2022
CC_LEVELS      <- c("0-strike", "1-strike", "2-strike")
STAND_LEVELS   <- c("L", "R")
PG_LEVELS      <- c("FF", "SI/FC", "BRK", "OFFSP")
EDGE_LEVELS    <- c("side", "top", "bot")
D_BAND_IN      <- 8.0                       # SOP W3.5: |d| <= 8.0 in for the surface fit
BIN_W_IN       <- 0.5                       # SOP W3.11: 0.5 in bins over [-8, +8]
N_BINS         <- as.integer(2 * D_BAND_IN / BIN_W_IN)
TOL_EDGE_IN    <- 0.15                      # SOP W3.11 and CH1-A5
TOL_AREA_SQIN  <- 3                         # SOP W3.11 and CH1-A5

SOP_K   <- c(main = 24L, season = 18L, ccst = 12L, velo = 10L)
LADDER  <- list(main = c(24L, 32L, 40L, 48L), season = c(18L, 24L, 30L, 36L),
                ccst = c(12L, 16L, 20L, 24L), velo = c(10L, 20L, 30L, 40L))
GROUPS  <- names(SOP_K)
KI_STABLE    <- 0.01
KC_SUBSAMPLE <- 20000L
KC_REP       <- 400L
KC_SEED      <- 311L
RE_TERMS     <- c("s(umpire_hp_id)", "s(umpire_season)")

REF_HEIGHT_IN <- 72                         # SOP W3.14 reference batter
ZN_MID        <- 0.4025                     # SOP W3.14
CENTRE_X_FT   <- 0.25                       # SOP W3.14
XG <- round(seq(-1.5, 1.5, by = 0.01), 2)   # 301 points
ZG <- round(seq(0.15, 0.70, by = 0.002), 3) # 276 points
NQ <- 51L                                   # quantiles of the pitch-group and velocity shift per cell

HOLDOUT_SHARE <- 0.2
HOLDOUT_SEED  <- 3112L
SCALE_SEED    <- 3113L
BENCH_SEED    <- 3114L
BENCH_ROWS    <- c(300000L, 1200000L)       # the SOP's two benchmark sizes
MAX_PAR       <- 4L                         # concurrent worker processes
FIT_SUFFIXES  <- c("rds", "npz", "stanfit", "qs", "pkl")

OUT_DIR   <- file.path(ROOT, "out", "dev", "ch1_spec")
PREREG_MD <- file.path(ROOT, "docs", "prereg", "ch1.md")
T1_FILE   <- file.path(ROOT, "out", "ch1", "tab", "T1_sample.csv")

stopifnot(length(XG) == 301L, length(ZG) == 276L, N_BINS == 32L,
          all(DEV_SEASONS %in% 2022:2024))

## --- the harness -------------------------------------------------------------------

n_pass <- 0L
failures <- character(0)
check <- function(label, ok, detail) {
  if (isTRUE(ok)) {
    n_pass <<- n_pass + 1L
    cat(sprintf("PASS   %-44s %s\n", label, detail))
  } else {
    failures <<- c(failures, sprintf("%s -- %s", label, detail))
    cat(sprintf("FAIL   %-44s %s\n", label, detail))
  }
}
record <- function(label, detail) cat(sprintf("RECORD %-44s %s\n", label, detail))
comma <- function(x) formatC(as.numeric(x), format = "d", big.mark = ",")
finish <- function() {
  el <- as.numeric(difftime(Sys.time(), t_start, units = "secs"))
  cat(sprintf("\nW3.11 %s: %d PASS, %d FAIL, %.0f s\n", MODE, n_pass, length(failures), el))
  if (length(failures) > 0L) {
    cat("failures:\n", paste0("  ", failures, "\n"), sep = "")
    quit(status = 1)
  }
  quit(status = 0)
}

## --- layout from absump.paths ----------------------------------------------------

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

## --- the one read ------------------------------------------------------------------
# Every row this script fits comes through load_dev(). The arrow filter keeps
# 2022-2024 and the band; 2025 and 2026 rows are dropped by the scanner and never
# reach R. The guard then asserts what arrived before anything is fitted.

load_dev <- function(sample = c("d8", "p1_d8")) {
  sample <- match.arg(sample)
  cols <- c("pitch_uid", "game_pk", "official_date", "season", "regime", "analysis_set",
            "umpire_hp_id", "umpire_season", "stand", "count_class", "pitch_group",
            "velo", "x_mid", "z_mid", "H", "zn", "d", "edge", "cs", "H_abs", "d_abs")
  ds <- arrow::open_dataset(mart_path())
  q <- ds |> filter(season %in% !!DEV_SEASONS)
  q <- if (sample == "d8") {
    q |> filter(abs(d) <= !!D_BAND_IN)
  } else {
    q |> filter(!is.na(H_abs), abs(d_abs) <= !!D_BAND_IN)
  }
  df <- q |> select(all_of(cols)) |> collect() |> as.data.frame()
  df <- df[order(df$pitch_uid), , drop = FALSE]
  rownames(df) <- NULL
  guard <- list(
    seasons = sort(unique(as.integer(df$season))),
    max_date = max(df$official_date),
    regimes = sort(unique(as.character(df$regime))),
    sets = sort(unique(as.character(df$analysis_set))))
  bad <- c(
    if (!all(guard$seasons %in% DEV_SEASONS)) "a season outside 2022-2024",
    if (guard$max_date > DEV_LAST_DATE) "an official date after 2024",
    if (!identical(guard$regimes, DEV_REGIME)) "a regime other than pre_buffer",
    if (!identical(guard$sets, "open")) "an analysis set other than open")
  if (length(bad) > 0L) stop("the development guard refused the sample: ",
                             paste(bad, collapse = "; "), call. = FALSE)
  if (sample == "p1_d8") {
    # The robustness arm: the same pitches, ABS-measured height (DECISIONS.md D-R0-02).
    df$zn <- z_norm(df$z_mid, df$H_abs)
    df$d <- df$d_abs
  }
  df$regime <- NULL
  df$analysis_set <- NULL
  list(df = prepare(df), guard = guard)
}

prepare <- function(df) {
  fx <- function(x, lv, what) {
    x <- as.character(x)
    if (!all(x %in% lv)) stop(what, " carries a level outside ", paste(lv, collapse = " "),
                             call. = FALSE)
    factor(x, levels = lv)
  }
  df$season <- fx(df$season, SEASON_LEVELS, "season")
  df$count_class <- fx(df$count_class, CC_LEVELS, "count_class")
  df$stand <- fx(df$stand, STAND_LEVELS, "stand")
  df$pitch_group <- fx(df$pitch_group, PG_LEVELS, "pitch_group")
  df$edge <- fx(df$edge, EDGE_LEVELS, "edge")
  df$season_o <- factor(df$season, levels = SEASON_LEVELS, ordered = TRUE)
  df$count_class_o <- factor(df$count_class, levels = CC_LEVELS, ordered = TRUE)
  df$stand_o <- factor(df$stand, levels = STAND_LEVELS, ordered = TRUE)
  df$umpire_hp_id <- factor(as.character(df$umpire_hp_id))
  df$umpire_season <- factor(as.character(df$umpire_season))
  if (anyNA(df[, c("cs", "x_mid", "zn", "velo", "d", "umpire_hp_id", "umpire_season")])) {
    stop("a fitted column carries NA", call. = FALSE)
  }
  df
}

## --- the specification -------------------------------------------------------------

spec_text <- function(k, coding) {
  by <- if (coding == "ordered") c("season_o", "count_class_o", "stand_o") else
    c("season", "count_class", "stand")
  te <- function(kk, b) sprintf('te(x_mid, zn, bs = c("cr","cr"), k = c(%d,%d)%s)', kk, kk,
                                if (is.null(b)) "" else paste0(", by = ", b))
  paste0("cs ~ season + count_class + stand + pitch_group",
         " + ", te(k[["main"]], NULL),
         " + ", te(k[["season"]], by[1]),
         " + ", te(k[["ccst"]], by[2]),
         " + ", te(k[["ccst"]], by[3]),
         " + s(velo, k = ", k[["velo"]], ")",
         ' + s(umpire_hp_id, bs = "re") + s(umpire_season, bs = "re")')
}

vname <- function(k, coding = "ordered", sample = "d8") {
  sprintf("k%d-%d-%d-%d_%s_%s", k[["main"]], k[["season"]], k[["ccst"]], k[["velo"]],
          substr(coding, 1L, 3L), sample)
}
parse_vname <- function(name) {
  m <- regmatches(name, regexec("^k(\\d+)-(\\d+)-(\\d+)-(\\d+)_(ord|uno)_(d8|p1_d8|train80|scale5)$", name))[[1]]
  if (length(m) != 7L) stop("not a variant name: ", name, call. = FALSE)
  list(k = setNames(as.integer(m[2:5]), GROUPS),
       coding = if (m[6] == "ord") "ordered" else "unordered", sample = m[7])
}
term_group <- function(term) {
  ifelse(term == "te(x_mid,zn)", "main",
  ifelse(grepl("^te\\(x_mid,zn\\):season", term), "season",
  ifelse(grepl("^te\\(x_mid,zn\\):(count_class|stand)", term), "ccst",
  ifelse(term == "s(velo)", "velo", "re"))))
}
rung_up <- function(g, k) {
  lad <- LADDER[[g]]
  i <- match(k, lad)
  if (is.na(i) || i == length(lad)) NA_integer_ else lad[i + 1L]
}

fit_spec <- function(df, k, coding) {
  txt <- spec_text(k, coding)
  warn <- character(0)
  pt0 <- proc.time()
  m <- withCallingHandlers(
    bam(as.formula(txt), data = df, family = binomial(), discrete = TRUE, method = "fREML"),
    warning = function(w) {
      warn <<- c(warn, conditionMessage(w))
      invokeRestart("muffleWarning")
    })
  pt <- proc.time() - pt0
  list(m = m, text = txt, warn = warn,
       elapsed = unname(pt[["elapsed"]]),
       cpu = unname(pt[["user.self"]] + pt[["sys.self"]]))
}

kcheck_table <- function(m) {
  set.seed(KC_SEED)
  kc <- k.check(m, subsample = KC_SUBSAMPLE, n.rep = KC_REP)
  data.frame(term = rownames(kc), k_prime = kc[, "k'"], edf = kc[, "edf"],
             k_index = kc[, "k-index"], p_value = kc[, "p-value"],
             group = term_group(rownames(kc)), row.names = NULL, stringsAsFactors = FALSE)
}

## --- standardised surfaces and contour metrics (SOP W3.14's definitions) ----------

by_columns <- function(nd, season, cc, st) {
  nd$season <- factor(season, levels = SEASON_LEVELS)
  nd$season_o <- factor(season, levels = SEASON_LEVELS, ordered = TRUE)
  nd$count_class <- factor(cc, levels = CC_LEVELS)
  nd$count_class_o <- factor(cc, levels = CC_LEVELS, ordered = TRUE)
  nd$stand <- factor(st, levels = STAND_LEVELS)
  nd$stand_o <- factor(st, levels = STAND_LEVELS, ordered = TRUE)
  nd
}

# The 2024 reference mix of count class, handedness, pitch group and velocity,
# reduced to six (count class, handedness) cells, each with NQ quantiles of the
# pitch-group-and-velocity shift on the logit scale. Random effects set to zero.
reference_mix <- function(m, df) {
  ref <- df[df$season == REF_SEASON, c("count_class", "stand", "pitch_group", "velo")]
  velo_ref <- stats::median(ref$velo)
  base <- data.frame(x_mid = 0, zn = ZN_MID, pitch_group = ref$pitch_group, velo = ref$velo,
                     umpire_hp_id = factor(levels(df$umpire_hp_id)[1], levels = levels(df$umpire_hp_id)),
                     umpire_season = factor(levels(df$umpire_season)[1], levels = levels(df$umpire_season)))
  base <- by_columns(base, SEASON_LEVELS[1], as.character(ref$count_class), as.character(ref$stand))
  base0 <- base
  base0$pitch_group <- factor(PG_LEVELS[1], levels = PG_LEVELS)
  base0$velo <- velo_ref
  delta <- predict(m, base, exclude = RE_TERMS) - predict(m, base0, exclude = RE_TERMS)
  cell <- paste(ref$count_class, ref$stand, sep = "|")
  probs <- (seq_len(NQ) - 0.5) / NQ
  cells <- lapply(split(seq_along(cell), cell), function(i) {
    list(cc = as.character(ref$count_class[i[1]]), st = as.character(ref$stand[i[1]]),
         w = length(i) / nrow(ref), q = unname(stats::quantile(delta[i], probs, type = 7)))
  })
  list(cells = cells, velo_ref = velo_ref)
}

std_surface <- function(m, df, mix, season) {
  pts <- rbind(expand.grid(x_mid = XG, zn = ZG), data.frame(x_mid = XG, zn = ZN_MID))
  pts$pitch_group <- factor(PG_LEVELS[1], levels = PG_LEVELS)
  pts$velo <- mix$velo_ref
  pts$umpire_hp_id <- factor(levels(df$umpire_hp_id)[1], levels = levels(df$umpire_hp_id))
  pts$umpire_season <- factor(levels(df$umpire_season)[1], levels = levels(df$umpire_season))
  p <- numeric(nrow(pts))
  for (cl in mix$cells) {
    nd <- by_columns(pts, season, cl$cc, cl$st)
    eta <- predict(m, nd, exclude = RE_TERMS)
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
point_in_polygon <- function(px, py, x, y) {
  n <- length(x)
  j <- c(n, seq_len(n - 1L))
  hit <- ((y > py) != (y[j] > py)) & (px < (x[j] - x) * (py - y) / (y[j] - y) + x)
  sum(hit, na.rm = TRUE) %% 2L == 1L
}
J_MID_LO <- max(which(ZG <= ZN_MID))
J_MID_HI <- J_MID_LO + 1L
I_CENTRE <- which(abs(XG) <= CENTRE_X_FT + 1e-9)
I_ZERO   <- which(XG == 0)

contour_metrics <- function(s) {
  lp <- unname(qlogis(s$grid))
  ll <- unname(qlogis(s$line))
  tops <- vapply(I_CENTRE, function(i) crossing(lp[i, ], ZG, J_MID_HI, +1L), 0)
  bots <- vapply(I_CENTRE, function(i) crossing(lp[i, ], ZG, J_MID_LO, -1L), 0)
  xr <- crossing(ll, XG, I_ZERO, +1L)
  xl <- crossing(ll, XG, I_ZERO, -1L)
  area <- NA_real_
  for (ln in grDevices::contourLines(XG, ZG, lp, levels = 0)) {
    n <- length(ln$x)
    closed <- n > 3L && abs(ln$x[1] - ln$x[n]) < 1e-12 && abs(ln$y[1] - ln$y[n]) < 1e-12
    if (!closed || !point_in_polygon(0, ZN_MID, ln$x, ln$y)) next
    xi <- ln$x * 12
    zi <- ln$y * REF_HEIGHT_IN
    area <- max(area, abs(sum(xi * c(zi[-1], zi[1]) - c(xi[-1], xi[1]) * zi)) / 2, na.rm = TRUE)
  }
  c(top_in = mean(tops) * REF_HEIGHT_IN, bot_in = mean(bots) * REF_HEIGHT_IN,
    half_width_in = (xr - xl) / 2 * 12, area_sqin = area)
}

## --- the binned logistic (SOP W3.11 secondary) -------------------------------------

bin_index <- function(d) pmin(pmax(floor((d + D_BAND_IN) / BIN_W_IN), 0), N_BINS - 1L)
bin_centre <- function(j) -D_BAND_IN + BIN_W_IN * (j + 0.5)

aggregate_bins <- function(df) {
  df$bin <- as.integer(bin_index(df$d))
  df |>
    group_by(edge, bin, season, count_class, stand) |>
    summarise(strikes = sum(cs), balls = n() - sum(cs), .groups = "drop") |>
    as.data.frame()
}
fit_binned <- function(agg) {
  fits <- list()
  for (e in EDGE_LEVELS) {
    a <- agg[agg$edge == e, ]
    a$bin_f <- factor(a$bin, levels = sort(unique(a$bin)))
    fits[[e]] <- glm(cbind(strikes, balls) ~ 0 + bin_f + season + count_class + stand,
                     family = binomial(), data = a)
  }
  fits
}
predict_binned <- function(fits, newd) {
  p <- rep(NA_real_, nrow(newd))
  for (e in EDGE_LEVELS) {
    i <- which(newd$edge == e)
    if (length(i) == 0L) next
    nd <- newd[i, c("bin", "season", "count_class", "stand")]
    nd$bin_f <- factor(nd$bin, levels = levels(fits[[e]]$model$bin_f))
    p[i] <- predict(fits[[e]], nd, type = "response")
  }
  p
}
# The d at which the probability, standardised to the 2024 (count, stand) mix,
# crosses 0.5, walking outward from the deepest inside bin.
binned_edges <- function(fits, df, season) {
  ref <- df[df$season == REF_SEASON, c("count_class", "stand")]
  w <- as.data.frame(table(ref$count_class, ref$stand), stringsAsFactors = FALSE)
  names(w) <- c("count_class", "stand", "n")
  w$w <- w$n / sum(w$n)
  out <- c()
  for (e in EDGE_LEVELS) {
    bins <- as.integer(levels(fits[[e]]$model$bin_f))
    p <- numeric(length(bins))
    for (r in seq_len(nrow(w))) {
      nd <- data.frame(bin = bins, season = factor(season, levels = SEASON_LEVELS),
                       count_class = factor(w$count_class[r], levels = CC_LEVELS),
                       stand = factor(w$stand[r], levels = STAND_LEVELS), edge = e)
      p <- p + w$w[r] * predict_binned(fits, nd)
    }
    v <- qlogis(p)
    j0 <- which(v > 0)[1]
    out[e] <- if (is.na(j0)) NA_real_ else crossing(v, bin_centre(bins), j0, +1L)
  }
  top <- ABS_TOP_FRAC * REF_HEIGHT_IN + out[["top"]]
  bot <- ABS_BOT_FRAC * REF_HEIGHT_IN - out[["bot"]]
  hw <- PLATE_HALF_W_FT * 12 + out[["side"]]
  c(top_in = top, bot_in = bot, half_width_in = hw, area_sqin = 2 * hw * (top - bot))
}

## --- holdout metrics ---------------------------------------------------------------

score <- function(y, p) {
  p <- pmin(pmax(p, 1e-12), 1 - 1e-12)
  o <- order(p)
  bins <- cut(seq_along(o), breaks = 10, labels = FALSE)
  ece <- 0
  for (b in 1:10) {
    i <- o[bins == b]
    ece <- ece + length(i) / length(p) * abs(mean(y[i]) - mean(p[i]))
  }
  c(log_loss = -mean(y * log(p) + (1 - y) * log(1 - p)), brier = mean((y - p)^2), ece = ece)
}

## --- worker: one fit -----------------------------------------------------------------

run_fit <- function(name, outdir) {
  v <- parse_vname(name)
  dir.create(file.path(outdir, "fits"), recursive = TRUE, showWarnings = FALSE)
  src <- load_dev(if (v$sample == "p1_d8") "p1_d8" else "d8")
  df <- src$df
  res <- list(name = name, k = as.list(v$k), coding = v$coding, sample = v$sample,
              guard = list(seasons = src$guard$seasons, max_official_date = format(src$guard$max_date),
                           regimes = src$guard$regimes, analysis_sets = src$guard$sets),
              rows_loaded = nrow(df))
  fitdf <- df
  if (v$sample == "train80") {
    set.seed(HOLDOUT_SEED)
    games <- sort(unique(df$game_pk))
    test_games <- sample(games, round(HOLDOUT_SHARE * length(games)))
    is_test <- df$game_pk %in% test_games
    fitdf <- df[!is_test, ]
    test <- df[is_test, ]
    keep <- test$umpire_season %in% unique(fitdf$umpire_season)
    res$holdout <- list(games = length(games), test_games = length(test_games),
                        n_train = nrow(fitdf), n_test = nrow(test),
                        n_test_dropped_unseen_umpire_season = sum(!keep))
    test <- test[keep, ]
  }
  if (v$sample == "scale5") {
    # A cost benchmark only. Real 2022-2024 rows resampled to the five-season
    # surface-sample size, with synthetic labels s1..s5 in place of the season.
    t1 <- read.csv(T1_FILE, stringsAsFactors = FALSE)
    n_scale <- as.integer(t1$total[t1$row_id == "B_d8_P0"])
    set.seed(SCALE_SEED)
    idx <- sample.int(nrow(df), n_scale, replace = TRUE)
    fitdf <- df[idx, ]
    lab <- paste0("s", sample.int(5L, n_scale, replace = TRUE))
    fitdf$season <- factor(lab, levels = paste0("s", 1:5))
    fitdf$season_o <- factor(lab, levels = paste0("s", 1:5), ordered = TRUE)
    fitdf$umpire_season <- factor(paste(fitdf$umpire_hp_id, lab, sep = "_"))
    res$scale <- list(rows = n_scale, source = "B_d8_P0 total in out/ch1/tab/T1_sample.csv",
                      synthetic_season_levels = 5L,
                      umpire_season_levels = nlevels(fitdf$umpire_season))
  }
  res$n_fit <- nrow(fitdf)
  res$seasons_in_fit <- sort(unique(as.character(fitdf$season)))
  f <- fit_spec(fitdf, v$k, v$coding)
  m <- f$m
  res$formula <- f$text
  res$fit <- list(elapsed_s = f$elapsed, cpu_s = f$cpu, cpu_over_wall = f$cpu / f$elapsed,
                  n_coef = length(coef(m)), edf_total = sum(m$edf), freml = unname(m$gcv.ubre),
                  aic = AIC(m), dev_expl = summary(m)$dev.expl, converged = isTRUE(m$converged),
                  warnings = as.list(table(f$warn)))
  kt <- kcheck_table(m)
  res$kcheck <- kt
  if (v$sample %in% c("d8", "p1_d8")) {
    mix <- reference_mix(m, df)
    dir.create(file.path(outdir, "grids"), showWarnings = FALSE)
    met <- list()
    grids <- list()
    for (s in DRY_SEASONS) {
      sf <- std_surface(m, df, mix, s)
      met[[s]] <- as.list(contour_metrics(sf))
      grids[[s]] <- as.vector(sf$grid)
    }
    res$dry_run <- list(metrics = met,
                        delta = as.list(unlist(met[[DRY_SEASONS[2]]]) - unlist(met[[DRY_SEASONS[1]]])),
                        velo_ref = mix$velo_ref)
    g <- data.frame(x_mid = rep(XG, times = length(ZG)), zn = rep(ZG, each = length(XG)))
    for (s in DRY_SEASONS) g[[paste0("p_", s)]] <- sprintf("%.6f", grids[[s]])
    gz <- gzfile(file.path(outdir, "grids", paste0(name, ".csv.gz")), "w")
    write.csv(g, gz, row.names = FALSE, quote = FALSE)
    close(gz)
    if (name == vname(SOP_K) && MODE == "fit" && identical(normalizePath(outdir), normalizePath(OUT_DIR, mustWork = FALSE))) {
      grDevices::png(file.path(outdir, paste0("gam_check_", name, ".png")), width = 1400, height = 1000)
      set.seed(KC_SEED)
      txt <- utils::capture.output(gam.check(m, k.sample = KC_SUBSAMPLE, k.rep = KC_REP))
      grDevices::dev.off()
      writeLines(txt, file.path(outdir, paste0("gam_check_", name, ".txt")))
    }
  }
  if (v$sample == "train80") {
    y <- test$cs
    rows <- list()
    rows$base_rate <- score(y, rep(mean(fitdf$cs), nrow(test)))
    inside <- fitdf$d - BALL_R_IN < 0
    r_in <- mean(fitdf$cs[inside])
    r_out <- mean(fitdf$cs[!inside])
    rows$abs_rulebook_zone <- score(y, ifelse(test$d - BALL_R_IN < 0, r_in, r_out))
    pooled <- bam(cs ~ te(x_mid, zn, bs = "cr", k = c(16L, 16L)), data = fitdf,
                  family = binomial(), discrete = TRUE, method = "fREML")
    rows$pooled_surface_w34 <- score(y, as.numeric(predict(pooled, test, type = "response")))
    agg <- aggregate_bins(fitdf)
    bf <- fit_binned(agg)
    test$bin <- as.integer(bin_index(test$d))
    pb <- predict_binned(bf, test)
    res$holdout$binned_rows_in_unseen_cells <- sum(is.na(pb))
    pb[is.na(pb)] <- mean(fitdf$cs)
    rows$binned_logistic <- score(y, pb)
    rows$specification <- score(y, as.numeric(predict(m, test, type = "response")))
    res$baselines <- lapply(rows, as.list)
    res$baseline_rates <- list(abs_rulebook_in = r_in, abs_rulebook_out = r_out)
  }
  writeLines(toJSON(res, auto_unbox = TRUE, digits = NA, pretty = TRUE),
             file.path(outdir, "fits", paste0(name, ".json")))
  cat("worker done ", name, "\n", sep = "")
}

## --- worker: the SOP's 14.1 s benchmark formula, on synthetic data -----------------

run_bench <- function(rows, outdir) {
  dir.create(file.path(outdir, "fits"), recursive = TRUE, showWarnings = FALSE)
  set.seed(BENCH_SEED)
  n <- as.integer(rows)
  x <- runif(n, -1.5, 1.5)
  z <- runif(n, 0.15, 0.70)
  season <- factor(sample(paste0("s", 1:5), n, replace = TRUE))
  ump <- factor(sample(sprintf("u%03d", 1:100), n, replace = TRUE))
  ue <- rnorm(100, 0, 0.2)
  eta <- 4 * (1 - (abs(x) / 0.75)^4 - (abs(z - 0.42) / 0.15)^4) + ue[as.integer(ump)] +
    0.1 * (as.integer(season) - 3)
  eta <- pmax(pmin(eta, 12), -12)
  y <- rbinom(n, 1L, plogis(eta))
  d <- data.frame(y, x, z, season, ump)
  pt0 <- proc.time()
  m <- bam(y ~ s(x, z, by = season, k = 120) + season + s(ump, bs = "re"),
           family = binomial(), data = d, discrete = TRUE)
  pt <- proc.time() - pt0
  omp <- character(0)
  withCallingHandlers(
    bam(y ~ s(x, z, k = 20), family = binomial(), data = d[1:5000, ], discrete = TRUE, nthreads = 2),
    warning = function(w) { omp <<- c(omp, conditionMessage(w)); invokeRestart("muffleWarning") })
  res <- list(rows = n, formula = 'y ~ s(x, z, by = season, k = 120) + season + s(ump, bs = "re")',
              data = "synthetic: x, z uniform on the grid box, 5-level season, 100-level umpire",
              elapsed_s = unname(pt[["elapsed"]]),
              cpu_s = unname(pt[["user.self"]] + pt[["sys.self"]]),
              n_coef = length(coef(m)), edf_total = sum(m$edf),
              veclib_maximum_threads = Sys.getenv("VECLIB_MAXIMUM_THREADS", unset = ""),
              nthreads2_warnings = unique(omp),
              openmp_capability = unname(capabilities("OpenMP")))
  tag <- paste0("bench_sop_", n, if (nzchar(res$veclib_maximum_threads)) "_veclib1" else "")
  writeLines(toJSON(res, auto_unbox = TRUE, digits = NA, pretty = TRUE),
             file.path(outdir, "fits", paste0(tag, ".json")))
  cat("worker done ", tag, "\n", sep = "")
}

if (MODE == "fit") {
  run_fit(arg_value("--fit"), arg_value("--outdir"))
  quit(status = 0)
}
if (MODE == "bench") {
  run_bench(arg_value("--bench-sop"), arg_value("--outdir"))
  quit(status = 0)
}

## --- the scheduler: workers under /usr/bin/time -l -----------------------------------

parse_time_log <- function(path) {
  txt <- if (file.exists(path)) readLines(path, warn = FALSE) else character(0)
  tl <- grep("^\\s*[0-9.]+ real\\s+[0-9.]+ user\\s+[0-9.]+ sys", txt, value = TRUE)
  rss <- grep("maximum resident set size", txt, value = TRUE)
  if (length(tl) == 0L || length(rss) == 0L) return(NULL)
  num <- as.numeric(regmatches(tl[1], gregexpr("[0-9.]+", tl[1]))[[1]])
  list(real_s = num[1], user_s = num[2], sys_s = num[3],
       peak_rss_bytes = as.numeric(sub("^\\s*([0-9]+).*", "\\1", rss[1])))
}

run_jobs <- function(jobs, outdir) {
  # jobs: list of list(tag, args, env)
  dir.create(file.path(outdir, "logs"), recursive = TRUE, showWarnings = FALSE)
  queue <- jobs
  running <- list()
  done <- list()
  while (length(queue) > 0L || length(running) > 0L) {
    while (length(queue) > 0L && length(running) < MAX_PAR) {
      j <- queue[[1]]
      queue <- queue[-1]
      log <- file.path(outdir, "logs", paste0(j$tag, ".log"))
      unlink(log)
      system2("/usr/bin/time", c("-l", "Rscript", shQuote(SELF), j$args, "--outdir", shQuote(outdir)),
              stdout = log, stderr = log, wait = FALSE, env = j$env)
      cat(sprintf("start  %-34s %s\n", j$tag, format(Sys.time(), "%H:%M:%S")))
      running[[j$tag]] <- log
    }
    Sys.sleep(5)
    for (tag in names(running)) {
      t <- parse_time_log(running[[tag]])
      if (!is.null(t)) {
        cat(sprintf("done   %-34s %s  %.1f s wall, %.2f GB peak\n", tag, format(Sys.time(), "%H:%M:%S"),
                    t$real_s, t$peak_rss_bytes / 1e9))
        done[[tag]] <- t
        running[[tag]] <- NULL
      }
    }
  }
  done
}
fit_job <- function(name) list(tag = name, args = c("--fit", name), env = character(0))
read_fit <- function(outdir, tag) {
  p <- file.path(outdir, "fits", paste0(tag, ".json"))
  if (!file.exists(p)) return(NULL)
  fromJSON(p, simplifyVector = TRUE)
}
ki_by_term <- function(res) setNames(res$kcheck$k_index, res$kcheck$term)
max_group_change <- function(a, b, g) {
  ka <- ki_by_term(a); kb <- ki_by_term(b)
  terms <- a$kcheck$term[a$kcheck$group == g]
  max(abs(kb[terms] - ka[terms]))
}

## --- shared: load the development sample in the parent -------------------------------

MART <- mart_path()
record("layout", sprintf("analysis table %s", MART))
check("input present", file.exists(MART), MART)
check("T1 present", file.exists(T1_FILE), T1_FILE)
if (length(failures) > 0L) finish()

src <- load_dev("d8")
dev <- src$df
check("development guard: seasons", identical(src$guard$seasons, DEV_SEASONS),
      paste(src$guard$seasons, collapse = " "))
check("development guard: last official date", src$guard$max_date <= DEV_LAST_DATE,
      format(src$guard$max_date))
check("development guard: regime and set",
      identical(src$guard$regimes, DEV_REGIME) && identical(src$guard$sets, "open"),
      paste(src$guard$regimes, src$guard$sets))
n_by_season <- as.list(table(dev$season))
record("development sample", sprintf("%s rows, |d| <= %.1f in: %s", comma(nrow(dev)), D_BAND_IN,
                                     paste(names(n_by_season), comma(unlist(n_by_season)), collapse = ", ")))

# The self-scan: one arrow read in this file, and it is load_dev's.
self_src <- readLines(SELF, warn = FALSE)
n_reads <- sum(grepl("open_dataset\\(", self_src) & !grepl("^\\s*#", self_src))
check("one read path", n_reads == 1L, sprintf("%d open_dataset call outside comments", n_reads))

## --- build -------------------------------------------------------------------------------

if (MODE == "build") {
  dir.create(OUT_DIR, recursive = TRUE, showWarnings = FALSE)
  writeLines(c("# Pre-tag development output of SOP W3.11. Never committed. See R/ch1/20_spec_dev.R.", "*"),
             file.path(OUT_DIR, ".gitignore"))
  sop <- vname(SOP_K)
  up1 <- function(g, k = SOP_K) { k[[g]] <- rung_up(g, k[[g]]); k }
  all_up <- SOP_K
  for (g in GROUPS) all_up[[g]] <- rung_up(g, SOP_K[[g]])
  wave <- list(
    fit_job(vname(SOP_K, "unordered")),
    fit_job(vname(SOP_K, sample = "scale5")),
    fit_job(sop),
    fit_job(vname(SOP_K, sample = "train80")),
    fit_job(vname(up1("main"))), fit_job(vname(up1("season"))),
    fit_job(vname(up1("ccst"))), fit_job(vname(up1("velo"))),
    fit_job(vname(all_up)),
    fit_job(vname(SOP_K, sample = "p1_d8")),
    list(tag = "bench_sop_300000", args = c("--bench-sop", "300000"), env = character(0)),
    list(tag = "bench_sop_1200000", args = c("--bench-sop", "1200000"), env = character(0)),
    list(tag = "bench_sop_1200000_veclib1", args = c("--bench-sop", "1200000"),
         env = "VECLIB_MAXIMUM_THREADS=1"))
  times <- run_jobs(wave, OUT_DIR)

  # The ladder. For each group, compare rung j with rung j + 1 until stable.
  settled <- SOP_K
  sweep_rows <- list()
  for (g in GROUPS) {
    k_lo <- SOP_K
    repeat {
      k_hi <- k_lo
      k_hi[[g]] <- rung_up(g, k_lo[[g]])
      if (is.na(k_hi[[g]])) { settled[[g]] <- k_lo[[g]]; break }
      need <- setdiff(c(vname(k_lo), vname(k_hi)), names(times))
      if (length(need) > 0L) times <- c(times, run_jobs(lapply(need, fit_job), OUT_DIR))
      a <- read_fit(OUT_DIR, vname(k_lo)); b <- read_fit(OUT_DIR, vname(k_hi))
      ch <- max_group_change(a, b, g)
      sweep_rows[[length(sweep_rows) + 1L]] <- data.frame(
        group = g, k_from = k_lo[[g]], k_to = k_hi[[g]], max_abs_k_index_change = ch,
        stable = ch < KI_STABLE)
      if (ch < KI_STABLE) { settled[[g]] <- k_lo[[g]]; break }
      k_lo <- k_hi
    }
  }
  sweep <- do.call(rbind, sweep_rows)
  final_up <- settled
  for (g in GROUPS) final_up[[g]] <- rung_up(g, settled[[g]])
  need <- setdiff(c(vname(settled), vname(final_up)), names(times))
  if (length(need) > 0L) times <- c(times, run_jobs(lapply(need, fit_job), OUT_DIR))

  # The by-factor coding.
  lit <- read_fit(OUT_DIR, vname(SOP_K, "unordered"))
  ord <- read_fit(OUT_DIR, sop)

  # k_sweep.csv: every fit, every term.
  fit_tags <- grep("^k", names(times), value = TRUE)
  ks <- do.call(rbind, lapply(fit_tags, function(tag) {
    r <- read_fit(OUT_DIR, tag)
    data.frame(variant = tag, k_main = r$k$main, k_season = r$k$season, k_ccst = r$k$ccst,
               k_velo = r$k$velo, coding = r$coding, sample = r$sample, r$kcheck)
  }))
  write.csv(ks, file.path(OUT_DIR, "k_sweep.csv"), row.names = FALSE)
  write.csv(sweep, file.path(OUT_DIR, "k_ladder.csv"), row.names = FALSE)

  # sensitivity.csv: one row per fit.
  final_name <- vname(settled)
  read_grid <- function(tag) {
    p <- file.path(OUT_DIR, "grids", paste0(tag, ".csv.gz"))
    if (file.exists(p)) read.csv(p) else NULL
  }
  g_final <- read_grid(final_name)
  sens <- do.call(rbind, lapply(fit_tags, function(tag) {
    r <- read_fit(OUT_DIR, tag)
    t <- times[[tag]]
    gd <- read_grid(tag)
    dp <- if (is.null(gd)) NA_real_ else max(abs(gd$p_2022 - g_final$p_2022), abs(gd$p_2023 - g_final$p_2023))
    dl <- r$dry_run$delta
    data.frame(variant = tag, coding = r$coding, sample = r$sample, n_fit = r$n_fit,
               n_coef = r$fit$n_coef, edf_total = r$fit$edf_total, freml = r$fit$freml,
               dev_expl = r$fit$dev_expl, min_k_index = min(r$kcheck$k_index, na.rm = TRUE),
               fit_wall_s = r$fit$elapsed_s, fit_cpu_s = r$fit$cpu_s,
               cpu_over_wall = r$fit$cpu_over_wall, process_peak_rss_gb = t$peak_rss_bytes / 1e9,
               max_abs_dp_vs_frozen = dp,
               d_top_in_2023_minus_2022 = if (is.null(dl)) NA else dl$top_in,
               d_bot_in_2023_minus_2022 = if (is.null(dl)) NA else dl$bot_in,
               d_half_width_in_2023_minus_2022 = if (is.null(dl)) NA else dl$half_width_in,
               d_area_sqin_2023_minus_2022 = if (is.null(dl)) NA else dl$area_sqin)
  }))
  write.csv(sens, file.path(OUT_DIR, "sensitivity.csv"), row.names = FALSE)

  # benchmark.csv
  bench_tags <- grep("^bench_sop_", names(times), value = TRUE)
  bench <- do.call(rbind, c(
    lapply(bench_tags, function(tag) {
      r <- read_fit(OUT_DIR, tag); t <- times[[tag]]
      data.frame(run = tag, formula = r$formula, rows = r$rows, n_coef = r$n_coef,
                 fit_wall_s = r$elapsed_s, fit_cpu_s = r$cpu_s, cpu_over_wall = r$cpu_s / r$elapsed_s,
                 process_wall_s = t$real_s, process_cpu_s = t$user_s + t$sys_s,
                 process_peak_rss_gb = t$peak_rss_bytes / 1e9,
                 veclib_maximum_threads = r$veclib_maximum_threads,
                 nthreads2_warning = paste(r$nthreads2_warnings, collapse = " | "))
    }),
    lapply(fit_tags, function(tag) {
      r <- read_fit(OUT_DIR, tag); t <- times[[tag]]
      data.frame(run = tag, formula = r$formula, rows = r$n_fit, n_coef = r$fit$n_coef,
                 fit_wall_s = r$fit$elapsed_s, fit_cpu_s = r$fit$cpu_s,
                 cpu_over_wall = r$fit$cpu_over_wall,
                 process_wall_s = t$real_s, process_cpu_s = t$user_s + t$sys_s,
                 process_peak_rss_gb = t$peak_rss_bytes / 1e9,
                 veclib_maximum_threads = "", nthreads2_warning = "")
    })))
  write.csv(bench, file.path(OUT_DIR, "benchmark.csv"), row.names = FALSE)

  # baselines.csv
  ho <- read_fit(OUT_DIR, vname(SOP_K, sample = "train80"))
  bl <- do.call(rbind, lapply(names(ho$baselines), function(nm) {
    data.frame(model = nm, n_train = ho$holdout$n_train, n_test = ho$holdout$n_test -
                 ho$holdout$n_test_dropped_unseen_umpire_season,
               log_loss = ho$baselines[[nm]]$log_loss, brier = ho$baselines[[nm]]$brier,
               ece = ho$baselines[[nm]]$ece)
  }))
  write.csv(bl, file.path(OUT_DIR, "baselines.csv"), row.names = FALSE)

  # The binned logistic on the whole development sample, and the CH1-A5 dry run.
  agg <- aggregate_bins(dev)
  bf <- fit_binned(agg)
  bm <- lapply(DRY_SEASONS, function(s) binned_edges(bf, dev, s))
  names(bm) <- DRY_SEASONS
  fin <- read_fit(OUT_DIR, final_name)
  metrics <- c("top_in", "bot_in", "half_width_in", "area_sqin")
  dry <- data.frame(
    metric = metrics,
    bam_2022 = unlist(fin$dry_run$metrics[["2022"]])[metrics],
    bam_2023 = unlist(fin$dry_run$metrics[["2023"]])[metrics],
    binned_2022 = bm[["2022"]][metrics], binned_2023 = bm[["2023"]][metrics])
  dry$bam_delta <- dry$bam_2023 - dry$bam_2022
  dry$binned_delta <- dry$binned_2023 - dry$binned_2022
  dry$abs_diff <- abs(dry$binned_delta - dry$bam_delta)
  dry$tolerance <- ifelse(dry$metric == "area_sqin", TOL_AREA_SQIN, TOL_EDGE_IN)
  dry$within <- dry$abs_diff <= dry$tolerance
  write.csv(dry, file.path(OUT_DIR, "binned_vs_bam_dryrun.csv"), row.names = FALSE)
  write.csv(agg, file.path(OUT_DIR, "binned_cells.csv"), row.names = FALSE)

  frozen <- list(
    step = "W3.11", coding = "ordered", k = as.list(settled), k_up = as.list(final_up),
    formula = spec_text(settled, "ordered"),
    reference_levels = list(season = SEASON_LEVELS[1], count_class = CC_LEVELS[1], stand = STAND_LEVELS[1]),
    ladder = LADDER, ki_stable = KI_STABLE, kc_subsample = KC_SUBSAMPLE, kc_rep = KC_REP, kc_seed = KC_SEED,
    dev_rows = nrow(dev), dev_rows_by_season = n_by_season,
    literal_coding = list(fit_wall_s = lit$fit$elapsed_s, n_coef = lit$fit$n_coef, edf = lit$fit$edf_total),
    ordered_coding = list(fit_wall_s = ord$fit$elapsed_s, n_coef = ord$fit$n_coef, edf = ord$fit$edf_total),
    final_variant = final_name, final_up_variant = vname(final_up))
  writeLines(toJSON(frozen, auto_unbox = TRUE, digits = NA, pretty = TRUE),
             file.path(OUT_DIR, "frozen_spec.json"))

  cat("\n")
  print(sweep, row.names = FALSE)
  cat("\n")
  print(ks[ks$variant == final_name, c("term", "k_prime", "edf", "k_index", "p_value")], row.names = FALSE)
  cat("\n")
  print(sens[, c("variant", "n_fit", "n_coef", "edf_total", "min_k_index", "fit_wall_s",
                 "cpu_over_wall", "process_peak_rss_gb", "max_abs_dp_vs_frozen")], row.names = FALSE)
  cat("\n")
  print(bench[, c("run", "rows", "n_coef", "fit_wall_s", "cpu_over_wall", "process_peak_rss_gb",
                  "veclib_maximum_threads")], row.names = FALSE)
  cat("\n")
  print(bl, row.names = FALSE)
  cat("\n")
  print(dry, row.names = FALSE)
  cat("\n")
  for (tag in fit_tags) {
    r <- read_fit(OUT_DIR, tag)
    check(sprintf("no 2025 or 2026 row: %s", tag),
          all(r$guard$seasons %in% DEV_SEASONS) && as.Date(r$guard$max_official_date) <= DEV_LAST_DATE,
          sprintf("seasons %s, last date %s, %s rows fitted", paste(r$guard$seasons, collapse = " "),
                  r$guard$max_official_date, comma(r$n_fit)))
    check(sprintf("converged: %s", tag), isTRUE(r$fit$converged), "bam reports convergence")
  }
  check("every group stable within the ladder", all(sweep$stable[!duplicated(sweep$group, fromLast = TRUE)]),
        paste(sprintf("%s %d", names(settled), settled), collapse = ", "))
  check("no fit object under out/dev", length(list.files(OUT_DIR, recursive = TRUE,
        pattern = paste0("\\.(", paste(FIT_SUFFIXES, collapse = "|"), ")$"))) == 0L, OUT_DIR)
  finish()
}

## --- check ---------------------------------------------------------------------------------

frozen_file <- file.path(OUT_DIR, "frozen_spec.json")
check("frozen_spec.json present", file.exists(frozen_file), frozen_file)
check("docs/prereg/ch1.md present", file.exists(PREREG_MD), PREREG_MD)
if (length(failures) > 0L) finish()
frozen <- fromJSON(frozen_file, simplifyVector = TRUE)
k_frozen <- unlist(frozen$k)[GROUPS]
k_up <- unlist(frozen$k_up)[GROUPS]
check("development rows equal the build",
      identical(as.integer(unlist(n_by_season)), as.integer(unlist(frozen$dev_rows_by_season))),
      paste(comma(unlist(n_by_season)), collapse = " / "))

md <- readLines(PREREG_MD, warn = FALSE)
mdt <- paste(md, collapse = "\n")
# The formula block in ch1.md carries the frozen k. Its four te() k values and the
# s(velo) k, read in order, must equal frozen_spec.json.
fb <- regmatches(mdt, regexpr("```r\\s*\\ncs ~[^`]*```", mdt))
check("formula block in ch1.md", length(fb) == 1L, "one fenced r block that starts with cs ~")
if (length(fb) == 1L) {
  kte <- as.integer(sub("k = c\\((\\d+),\\s*\\d+\\)", "\\1",
                        regmatches(fb, gregexpr("k = c\\(\\d+,\\s*\\d+\\)", fb))[[1]]))
  kv <- as.integer(sub(".*k = (\\d+).*", "\\1", regmatches(fb, regexpr("s\\(velo, k = \\d+\\)", fb))))
  md_k <- c(main = kte[1], season = kte[2], ccst = kte[3], velo = kv)
  check("ch1.md k values equal the frozen k",
        length(kte) == 4L && kte[3] == kte[4] && identical(unname(md_k), unname(k_frozen)),
        paste(sprintf("%s %s", GROUPS, md_k), collapse = ", "))
  check("ch1.md formula uses the ordered by-factors",
        grepl("by = season_o", fb) && grepl("by = count_class_o", fb) && grepl("by = stand_o", fb),
        "season_o, count_class_o, stand_o")
}
must_say <- c(
  "2022-2024 disclosure" = "no row from 2025 or 2026",
  "edge tolerance" = "0.15 in",
  "area tolerance" = "3 sq in",
  "single-thread record" = "single-threaded",
  "no-OpenMP warning" = "openMP not available")
for (nm in names(must_say)) check(sprintf("ch1.md states: %s", nm),
                                  grepl(tolower(must_say[[nm]]), tolower(mdt), fixed = TRUE),
                                  sprintf("\"%s\"", must_say[[nm]]))

# Refit the frozen specification and the rung above it, in a temporary directory.
tmp <- tempfile("w311_check_")
dir.create(tmp)
times <- run_jobs(list(fit_job(vname(k_frozen)), fit_job(vname(k_up))), tmp)
a <- read_fit(tmp, vname(k_frozen))
b <- read_fit(tmp, vname(k_up))
check("refits completed", !is.null(a) && !is.null(b), paste(vname(k_frozen), vname(k_up)))
if (is.null(a) || is.null(b)) finish()
for (r in list(a, b)) {
  check(sprintf("no 2025 or 2026 row: %s", r$name),
        all(r$guard$seasons %in% DEV_SEASONS) && as.Date(r$guard$max_official_date) <= DEV_LAST_DATE &&
          all(r$seasons_in_fit %in% SEASON_LEVELS),
        sprintf("seasons %s, last date %s, %s rows fitted", paste(r$guard$seasons, collapse = " "),
                r$guard$max_official_date, comma(r$n_fit)))
}
ks <- read.csv(file.path(OUT_DIR, "k_sweep.csv"), stringsAsFactors = FALSE)
for (r in list(a, b)) {
  rec <- ks[ks$variant == r$name, ]
  kt <- r$kcheck
  mt <- match(kt$term, rec$term)
  dki <- max(abs(kt$k_index - rec$k_index[mt]), na.rm = TRUE)
  dedf <- max(abs(kt$edf - rec$edf[mt]))
  check(sprintf("refit reproduces the build: %s", r$name),
        !anyNA(mt) && dki < 1e-6 && dedf < 1e-4,
        sprintf("max |k-index change| %.2e, max |edf change| %.2e", dki, dedf))
}
for (g in GROUPS) {
  ch <- max_group_change(a, b, g)
  check(sprintf("k stable at the frozen rung: %s", g), ch < KI_STABLE,
        sprintf("k %d -> %d, max |k-index change| %.4f < %.2f", k_frozen[[g]], k_up[[g]], ch, KI_STABLE))
}
# The k.check table in ch1.md, to 3 decimals.
for (i in seq_len(nrow(a$kcheck))) {
  tr <- a$kcheck$term[i]
  if (is.na(a$kcheck$k_index[i])) next
  # The W3.11 k.check table is the earliest table in ch1.md that names the term.
  row <- grep(paste0("| `", tr, "` |"), md, fixed = TRUE, value = TRUE)
  ok <- FALSE
  if (length(row) >= 1L) {
    cells <- trimws(strsplit(row[1], "|", fixed = TRUE)[[1]])
    ok <- any(cells == sprintf("%.3f", a$kcheck$k_index[i]))
  }
  check(sprintf("ch1.md k-index: %s", tr), ok, sprintf("%.3f", a$kcheck$k_index[i]))
}
bad <- list.files(OUT_DIR, recursive = TRUE, all.files = TRUE,
                  pattern = paste0("(\\.(", paste(FIT_SUFFIXES, collapse = "|"), ")|provenance\\.json)$"))
check("no fit object or provenance.json under out/dev", length(bad) == 0L,
      if (length(bad) == 0L) OUT_DIR else paste(bad, collapse = " "))
record("check refit cost", sprintf("%s %.0f s wall, %.2f GB peak; %s %.0f s wall, %.2f GB peak",
                                   a$name, times[[a$name]]$real_s, times[[a$name]]$peak_rss_bytes / 1e9,
                                   b$name, times[[b$name]]$real_s, times[[b$name]]$peak_rss_bytes / 1e9))
unlink(tmp, recursive = TRUE)
finish()
