#!/usr/bin/env Rscript
# R/ch1/03_heights.R - SOP W3.4, height harmonisation, DT-30 and the D-13 fork.
#
#   Rscript R/ch1/03_heights.R            build: compute, write the table, report
#   Rscript R/ch1/03_heights.R --check    verify: recompute everything and compare
#                                         it with the table on disk; exit 1 on any
#                                         FAIL. This is the registered verify command.
#
# WHAT IT COMPUTES
#
# 1. DT-30 and CH1-A12. For each MLB season 2022-2026, the called pitches in the
#    open view and the share of them thrown to a batter who carries an
#    ABS-measured height (dim_batter_season.h_abs_in not null). Measured height
#    exists only from 2026, so W2.7 back-links it from a batter's 2026
#    appearance, and for 2022-2025 the cohort is the batters still active in
#    2026. That is Clemens's both-seasons restriction and it is a survivorship
#    restriction. The table also carries the roster+offset share, the batter
#    counts, and the share of called pitches with a recorded sz_top whose own
#    sz_top carries the 0.5 mm ABS signature, which shows that no season before
#    2026 holds a measured height of its own. The 60% trigger is SOP D-13's
#    number.
#
# 2. The selection effect SOP W3.4 asks for "as its own number". For 2022, 2023
#    and 2024 only, the called-strike surface is fitted three times and the 50%
#    contour is read for a 72-inch batter:
#
#      all_roster       every batter, roster height plus the offset. This is the
#                       primary cohort under the owner answer D-R0-02.
#      cohort_roster    only the ABS-measured cohort, with the same roster height.
#      cohort_measured  the same cohort with its ABS-measured height. This is the
#                       pre-registered robustness arm.
#
#    cohort_roster minus all_roster holds the height rule fixed, so it isolates
#    the surviving-batter restriction. Its 2024 value is the SOP's number and
#    bounds the selection effect. cohort_measured minus cohort_roster is the
#    height-measurement effect on the same batters.
#
# THE SURFACE. mgcv::bam, binomial, discrete = TRUE, method = "fREML", one tensor
# product of cr marginals over (plate_x_mid, zn), zn = plate_z_mid * 12 / height,
# which is SOP W3.11's family and basis type. It is pooled over count and
# handedness and not standardised to a pitch mix: it measures how the sample
# restriction moves the contour, and it is not the chapter's headline estimand.
# The grid is SOP W3.14's: x_mid in [-1.5, 1.5] ft by 0.01 (301 points), zn in
# [0.15, 0.70] by 0.002 (276 points). The metrics are SOP W3.14's, for a 72-inch
# batter: top_in and bot_in are the contour height averaged over |x| <= 0.25 ft,
# half_width_in is the contour |x| at zn = 0.4025, and area_sqin is the area
# inside the closed 50% contour from marching squares (grDevices::contourLines).
#
# THE INTERVALS. 1,000 coefficient draws per fit from the Bayesian covariance Vp
# by MASS::mvrnorm, seeded, never a refit. The draws of the two fits in a
# difference are independent. The cohort is a subset of the full sample, so the
# two estimates are positively correlated and the true interval on the
# difference is narrower than the one reported. The reported interval is
# conservative.
#
# WHAT IT READS. main_marts.v_called_pitch_open and main_marts.dim_batter_season
# in the DuckDB warehouse, read-only, and DECISIONS.md. It fits nothing on 2025
# or 2026: the fit seasons are asserted to be the pre-buffer regime before any
# fit runs. It reaches no host.
#
# WHAT IT WRITES. out/tables/height_coverage.csv, and only when the content
# changed, so two runs in a row leave the tree as the first run left it. The
# check mode writes nothing.

suppressPackageStartupMessages({
  library(DBI)
  library(duckdb)
  library(mgcv)
})

t0 <- Sys.time()

args <- commandArgs(trailingOnly = TRUE)
MODE <- if ("--check" %in% args) "check" else "build"
if (length(setdiff(args, "--check")) > 0L) {
  stop("usage: Rscript R/ch1/03_heights.R [--check]", call. = FALSE)
}

script_path <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
ROOT <- normalizePath(file.path(dirname(script_path[1]), "..", ".."))
OUT_REL <- "out/tables/height_coverage.csv"
OUT <- file.path(ROOT, OUT_REL)

# ---------------------------------------------------------------- constants
SEASONS       <- 2022:2026
FIT_SEASONS   <- 2022:2024          # the development window; never 2025 or 2026
FIT_REGIME    <- "pre_buffer"
TRIGGER       <- 0.60               # SOP D-13
REF_HEIGHT_IN <- 72                 # SOP W3.14 reference batter
ZN_MID        <- 0.4025             # SOP W3.14, midway between 0.27 and 0.535
CENTRE_X_FT   <- 0.25               # SOP W3.14, |x| band for top_in and bot_in
XG <- round(seq(-1.5, 1.5, by = 0.01), 2)      # 301 points
ZG <- round(seq(0.15, 0.70, by = 0.002), 3)    # 276 points
TE_K          <- c(16L, 16L)
N_DRAWS       <- 1000L
DRAW_CHUNK    <- 100L
SEED_BASE     <- 3040L              # RP-06: every stochastic call is seeded
# The 0.5 mm signature: sz_top * 12 * 25.4 / 0.535 within this many mm of the
# half-millimetre grid. W2.7 B-3 measured true ABS rows within 3e-7 mm; at 1e-6
# mm a chance hit on a continuous value has probability 4e-6.
SIG_TOL_MM    <- 1e-6
CELL_TOL      <- 2e-4               # contour cells are written to 4 decimals
MAX_NA_DRAWS  <- 0.01

ARMS <- c("all_roster", "cohort_roster", "cohort_measured")

stopifnot(length(XG) == 301L, length(ZG) == 276L,
          all(FIT_SEASONS %in% 2022:2024))

# ---------------------------------------------------------------- reporting
n_pass <- 0L
n_fail <- 0L
pass <- function(...) { n_pass <<- n_pass + 1L; cat("PASS    ", ..., "\n", sep = "") }
fail <- function(...) { n_fail <<- n_fail + 1L; cat("FAIL    ", ..., "\n", sep = "") }
record <- function(...) cat("record  ", ..., "\n", sep = "")
clause <- function(label, expr) {
  tryCatch(expr, error = function(e) fail(label, ": ", conditionMessage(e)))
}
f6 <- function(x) ifelse(is.na(x), "", sprintf("%.6f", x))
f4 <- function(x) ifelse(is.na(x), "", sprintf("%.4f", x))
fint <- function(x) ifelse(is.na(x), "", sprintf("%.0f", x))
comma <- function(x) formatC(x, format = "d", big.mark = ",")

# ---------------------------------------------------------------- warehouse
# tests/unit/test_paths.py holds every layout string to one copy, in
# src/absump/paths.py, so the path comes from that module, as in 00_preflight.R.
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

# A read-only connection. Another process may hold the file for a write, so the
# open is retried for up to a minute before it fails.
open_warehouse <- function(path) {
  for (i in 1:30) {
    con <- tryCatch(
      suppressMessages(DBI::dbConnect(duckdb::duckdb(), dbdir = path, read_only = TRUE)),
      error = function(e) e
    )
    if (!inherits(con, "error")) return(con)
    Sys.sleep(2)
  }
  stop("could not open the warehouse read-only: ", conditionMessage(con), call. = FALSE)
}

# ---------------------------------------------------------------- DT-30
coverage_sql <- sprintf("
SELECT p.season,
       p.level,
       min(p.regime)                                                   AS regime,
       count(DISTINCT p.regime)                                        AS n_regimes,
       min(p.official_date)                                            AS first_date,
       max(p.official_date)                                            AS last_date,
       count(*)                                                        AS n_called,
       count(*) FILTER (WHERE b.h_abs_in IS NOT NULL)                  AS n_called_abs_measured,
       count(*) FILTER (WHERE b.h_roster_in IS NOT NULL)               AS n_called_roster_offset,
       count(*) FILTER (WHERE b.batter IS NULL)                        AS n_called_no_dim,
       count(*) FILTER (WHERE p.height_source = 'abs_measured')        AS n_called_src_abs,
       count(DISTINCT p.batter)                                        AS n_batters,
       count(DISTINCT p.batter) FILTER (WHERE b.h_abs_in IS NOT NULL)  AS n_batters_abs_measured,
       count(p.sz_top)                                                 AS n_sz_top,
       count(*) FILTER (WHERE abs(p.sz_top * 12 * 25.4 / 0.535 * 2
                                  - round(p.sz_top * 12 * 25.4 / 0.535 * 2)) <= %.10f)
                                                                       AS n_signature
FROM main_marts.v_called_pitch_open AS p
LEFT JOIN main_marts.dim_batter_season AS b
       ON b.batter = p.batter AND b.season = p.season AND b.level = p.level
WHERE p.level = 'mlb'
GROUP BY p.season, p.level
ORDER BY p.season", 2 * SIG_TOL_MM)

dim_sql <- "
SELECT season,
       count(*)                                   AS n_batter_seasons,
       count(h_abs_in)                            AS n_batter_seasons_abs
FROM main_marts.dim_batter_season
WHERE level = 'mlb'
GROUP BY season
ORDER BY season"

offset_sql <- "
SELECT min(height_in - h_roster_in) FILTER (WHERE height_source = 'people_offset') AS o_min,
       max(height_in - h_roster_in) FILTER (WHERE height_source = 'people_offset') AS o_max,
       avg(h_abs_in - h_roster_in)  FILTER (WHERE season = 2026 AND h_abs_in IS NOT NULL) AS o_2026,
       count(*) FILTER (WHERE height_source = 'people_offset') AS n_people_offset
FROM main_marts.dim_batter_season
WHERE level = 'mlb'"

# ---------------------------------------------------------------- the surface
fit_sql <- "
SELECT p.cs, p.plate_x_mid AS x, p.plate_z_mid AS z, b.h_roster_in, b.h_abs_in
FROM main_marts.v_called_pitch_open AS p
JOIN main_marts.dim_batter_season AS b
  ON b.batter = p.batter AND b.season = p.season AND b.level = p.level
WHERE p.level = 'mlb' AND p.season = ? AND p.regime = ?
  AND p.plate_x_mid IS NOT NULL AND p.plate_z_mid IS NOT NULL
ORDER BY p.pitch_uid"

arm_frame <- function(d, arm, o) {
  if (arm == "all_roster") {
    data.frame(cs = d$cs, x = d$x, zn = d$z * 12 / (d$h_roster_in + o))
  } else {
    k <- !is.na(d$h_abs_in)
    h <- if (arm == "cohort_roster") d$h_roster_in[k] + o else d$h_abs_in[k]
    data.frame(cs = d$cs[k], x = d$x[k], zn = d$z[k] * 12 / h)
  }
}

# bam warns once per fit that some fitted probabilities are 0 or 1. Pitches far
# outside the zone are balls with certainty, so the warning is expected; it is
# counted and reported, never hidden, and any other warning passes through.
N_SEPARATION_WARNINGS <- 0L
fit_surface <- function(df) {
  withCallingHandlers(
    bam(cs ~ te(x, zn, bs = "cr", k = TE_K), family = binomial, data = df,
        discrete = TRUE, method = "fREML"),
    warning = function(w) {
      if (grepl("fitted probabilities numerically 0 or 1", conditionMessage(w))) {
        N_SEPARATION_WARNINGS <<- N_SEPARATION_WARNINGS + 1L
        invokeRestart("muffleWarning")
      }
    }
  )
}

# First crossing of the linear predictor through 0, walking from index j0 in
# direction step, linearly interpolated. NA when j0 is not inside the zone or no
# crossing is reached inside the grid.
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
  hit <- ((y > py) != (y[j] > py)) &
    (px < (x[j] - x) * (py - y) / (y[j] - y) + x)
  sum(hit, na.rm = TRUE) %% 2L == 1L
}

J_MID_LO <- max(which(ZG <= ZN_MID))
J_MID_HI <- J_MID_LO + 1L
I_CENTRE <- which(abs(XG) <= CENTRE_X_FT + 1e-9)
I_ZERO   <- which(XG == 0)

contour_metrics <- function(lp_grid, lp_line) {
  # lp_grid: 301 x 276, rows x, columns zn. lp_line: 301 values at zn = ZN_MID.
  lp_line <- as.numeric(lp_line)   # drop the lpmatrix row names so c() keeps ours
  tops <- vapply(I_CENTRE, function(i) crossing(lp_grid[i, ], ZG, J_MID_HI, +1L), 0)
  bots <- vapply(I_CENTRE, function(i) crossing(lp_grid[i, ], ZG, J_MID_LO, -1L), 0)
  xr <- crossing(lp_line, XG, I_ZERO, +1L)
  xl <- crossing(lp_line, XG, I_ZERO, -1L)
  area <- NA_real_
  lines <- grDevices::contourLines(XG, ZG, lp_grid, levels = 0)
  for (ln in lines) {
    n <- length(ln$x)
    closed <- n > 3L && abs(ln$x[1] - ln$x[n]) < 1e-12 && abs(ln$y[1] - ln$y[n]) < 1e-12
    if (!closed || !point_in_polygon(0, ZN_MID, ln$x, ln$y)) next
    xi <- ln$x * 12
    zi <- ln$y * REF_HEIGHT_IN
    a <- abs(sum(xi * c(zi[-1], zi[1]) - c(xi[-1], xi[1]) * zi)) / 2
    area <- max(area, a, na.rm = TRUE)
  }
  c(area_sqin = area,
    top_in = mean(tops) * REF_HEIGHT_IN,
    bot_in = mean(bots) * REF_HEIGHT_IN,
    half_width_in = (xr - xl) / 2 * 12)
}

GRID <- expand.grid(x = XG, zn = ZG)          # x varies fastest: rows of the matrix
LINE <- data.frame(x = XG, zn = ZN_MID)

surface_draws <- function(m, seed) {
  Xg <- predict(m, newdata = GRID, type = "lpmatrix")
  Xl <- predict(m, newdata = LINE, type = "lpmatrix")
  beta <- coef(m)
  point <- contour_metrics(matrix(drop(Xg %*% beta), nrow = length(XG)), drop(Xl %*% beta))
  set.seed(seed)
  B <- MASS::mvrnorm(N_DRAWS, beta, m$Vp)
  draws <- matrix(NA_real_, N_DRAWS, 4L, dimnames = list(NULL, names(point)))
  for (start in seq.int(1L, N_DRAWS, by = DRAW_CHUNK)) {
    rows <- start:min(N_DRAWS, start + DRAW_CHUNK - 1L)
    LG <- Xg %*% t(B[rows, , drop = FALSE])
    LL <- Xl %*% t(B[rows, , drop = FALSE])
    for (r in seq_along(rows)) {
      draws[rows[r], ] <- contour_metrics(matrix(LG[, r], nrow = length(XG)), LL[, r])
    }
  }
  kc <- k.check(m)
  list(point = point, draws = draws, n = nrow(m$model), edf = sum(m$edf),
       k_index = unname(kc[1, "k-index"]), k_prime = unname(kc[1, "k'"]))
}

# ---------------------------------------------------------------- main
wh <- warehouse_path()
con <- open_warehouse(wh)
cat("W3.4 height harmonisation, DT-30 and the D-13 fork (mode: ", MODE, ")\n", sep = "")
cat("warehouse ", wh, ", read-only\n", sep = "")

cov <- DBI::dbGetQuery(con, coverage_sql)
dimc <- DBI::dbGetQuery(con, dim_sql)
off <- DBI::dbGetQuery(con, offset_sql)
for (nm in setdiff(names(cov), c("level", "regime", "first_date", "last_date"))) {
  cov[[nm]] <- as.numeric(cov[[nm]])
}

clause("seasons", {
  if (identical(as.integer(cov$season), SEASONS) && all(cov$n_regimes == 1)) {
    pass("seasons ", paste(cov$season, collapse = " "), ", one regime each: ",
         paste(cov$regime, collapse = " "))
  } else {
    fail("seasons or regimes: ", paste(cov$season, cov$regime, cov$n_regimes, collapse = "; "))
  }
})

clause("every called pitch has a height row", {
  if (all(cov$n_called_no_dim == 0)) {
    pass("every called pitch joins dim_batter_season (0 unmatched in each season)")
  } else {
    fail("called pitches with no dim_batter_season row: ",
         paste(cov$season, cov$n_called_no_dim, collapse = "; "))
  }
})

clause("height_source agrees with h_abs_in", {
  if (all(cov$n_called_src_abs == cov$n_called_abs_measured)) {
    pass("fct height_source = abs_measured on exactly the pitches whose batter has h_abs_in")
  } else {
    fail("height_source and h_abs_in disagree: ",
         paste(cov$season, cov$n_called_src_abs, cov$n_called_abs_measured, collapse = "; "))
  }
})

o <- off$o_min
clause("roster offset", {
  if (abs(off$o_max - off$o_min) < 1e-12 && abs(off$o_2026 - o) < 1e-12) {
    pass(sprintf("roster offset o = %.6f in, one value over %d people_offset rows, equal to the 2026 overlap mean",
                 o, as.integer(off$n_people_offset)))
  } else {
    fail(sprintf("roster offset is not one value: min %.9f max %.9f 2026 mean %.9f",
                 off$o_min, off$o_max, off$o_2026))
  }
})

cov$abs_measured_share <- cov$n_called_abs_measured / cov$n_called
cov$roster_offset_share <- cov$n_called_roster_offset / cov$n_called
cov$abs_measured_batter_share <- cov$n_batters_abs_measured / cov$n_batters
cov$in_season_signature_share <- cov$n_signature / cov$n_sz_top
cov$abs_below_trigger <- cov$abs_measured_share < TRIGGER

clause("roster+offset coverage", {
  if (all(cov$n_called_roster_offset == cov$n_called)) {
    pass("roster+offset height covers 100% of called pitches in every season")
  } else {
    fail("roster+offset coverage below 100%: ",
         paste(cov$season, f6(cov$roster_offset_share), collapse = "; "))
  }
})

# ---- the contour fits, 2022-2024 only
fits <- list()
for (si in seq_along(FIT_SEASONS)) {
  s <- FIT_SEASONS[si]
  reg <- cov$regime[cov$season == s]
  if (!identical(reg, FIT_REGIME)) {
    stop("refusing to fit season ", s, ": regime ", reg, " is not ", FIT_REGIME, call. = FALSE)
  }
  d <- DBI::dbGetQuery(con, fit_sql, params = list(s, FIT_REGIME))
  for (ai in seq_along(ARMS)) {
    arm <- ARMS[ai]
    df <- arm_frame(d, arm, o)
    m <- fit_surface(df)
    fits[[paste(s, arm)]] <- surface_draws(m, SEED_BASE + 10L * si + ai)
    rm(m)
  }
  rm(d)
  invisible(gc(verbose = FALSE))
}

DBI::dbDisconnect(con, shutdown = TRUE)

clause("fit seasons", {
  pass("contours fitted on ", paste(FIT_SEASONS, collapse = ", "), " only, regime ", FIT_REGIME,
       "; nothing fitted on 2025 or 2026")
})

sel <- list()
for (s in FIT_SEASONS) {
  a <- fits[[paste(s, "all_roster")]]
  c_ <- fits[[paste(s, "cohort_roster")]]
  mm <- fits[[paste(s, "cohort_measured")]]
  dd <- c_$draws - a$draws
  ok <- stats::complete.cases(dd)
  q <- apply(dd[ok, , drop = FALSE], 2, stats::quantile, probs = c(0.025, 0.975), names = FALSE)
  sel[[as.character(s)]] <- list(
    area_all = a$point[["area_sqin"]], area_cohort = c_$point[["area_sqin"]],
    d = c_$point - a$point, lo = q[1, ], hi = q[2, ], meas = mm$point - c_$point,
    na_draws = sum(!ok)
  )
}

clause("contours closed", {
  pts <- unlist(lapply(fits, function(f) f$point))
  na_share <- max(vapply(fits, function(f) mean(!stats::complete.cases(f$draws)), 0))
  if (!anyNA(pts) && na_share <= MAX_NA_DRAWS) {
    pass(sprintf("all %d point contours closed and all four metrics defined; worst draw failure share %.4f (limit %.2f)",
                 length(fits), na_share, MAX_NA_DRAWS))
  } else {
    fail(sprintf("undefined contour metrics: %d NA point values, worst draw failure share %.4f",
                 sum(is.na(pts)), na_share))
  }
})

for (nm in names(fits)) {
  f <- fits[[nm]]
  record(sprintf("fit %-20s n %s, edf %.1f, k' %d, k-index %.3f, area %.2f sq in, top %.2f in, bot %.2f in, half-width %.2f in",
                 nm, comma(f$n), f$edf, as.integer(f$k_prime), f$k_index, f$point[["area_sqin"]],
                 f$point[["top_in"]], f$point[["bot_in"]], f$point[["half_width_in"]]))
}
record("bam separation warnings, expected and counted: ", N_SEPARATION_WARNINGS, " over ", length(fits), " fits")

# ---- the table
tab <- data.frame(
  season = as.character(as.integer(cov$season)), level = cov$level, regime = cov$regime,
  first_date = as.character(cov$first_date), last_date = as.character(cov$last_date),
  n_called = fint(cov$n_called),
  n_called_abs_measured = fint(cov$n_called_abs_measured),
  abs_measured_share = f6(cov$abs_measured_share),
  n_called_roster_offset = fint(cov$n_called_roster_offset),
  roster_offset_share = f6(cov$roster_offset_share),
  n_batters = fint(cov$n_batters),
  n_batters_abs_measured = fint(cov$n_batters_abs_measured),
  abs_measured_batter_share = f6(cov$abs_measured_batter_share),
  in_season_signature_share = f6(cov$in_season_signature_share),
  trigger_share = sprintf("%.2f", TRIGGER),
  abs_below_trigger = ifelse(cov$abs_below_trigger, "true", "false"),
  abs_height_link = ifelse(cov$season == 2026, "measured_in_season", "backlinked_from_2026"),
  contour_fit = ifelse(cov$season %in% FIT_SEASONS, "fitted", "not_fitted_before_prereg"),
  stringsAsFactors = FALSE
)
metric_cols <- c("area_sqin", "top_in", "bot_in", "half_width_in")
pick <- function(s, fn) {
  if (!as.character(s) %in% names(sel)) return(rep(NA_real_, 1))
  fn(sel[[as.character(s)]])
}
tab$area_all_sqin <- f4(vapply(cov$season, pick, 0, fn = function(x) x$area_all))
tab$area_cohort_sqin <- f4(vapply(cov$season, pick, 0, fn = function(x) x$area_cohort))
for (mc in metric_cols) {
  stem <- sub("_sqin$|_in$", "", mc)
  unit <- if (mc == "area_sqin") "_sqin" else "_in"
  tab[[paste0("sel_d_", stem, unit)]] <- f4(vapply(cov$season, pick, 0, fn = function(x) x$d[[mc]]))
  tab[[paste0("sel_d_", stem, "_lo95")]] <- f4(vapply(cov$season, pick, 0, fn = function(x) x$lo[match(mc, metric_cols)]))
  tab[[paste0("sel_d_", stem, "_hi95")]] <- f4(vapply(cov$season, pick, 0, fn = function(x) x$hi[match(mc, metric_cols)]))
}
for (mc in metric_cols) {
  stem <- sub("_sqin$|_in$", "", mc)
  unit <- if (mc == "area_sqin") "_sqin" else "_in"
  tab[[paste0("meas_d_", stem, unit)]] <- f4(vapply(cov$season, pick, 0, fn = function(x) x$meas[[mc]]))
}

render <- function(tab) {
  body <- apply(tab, 1, function(r) paste(trimws(r), collapse = ","))
  paste0(paste(c(paste(names(tab), collapse = ","), body), collapse = "\n"), "\n")
}
text <- render(tab)

if (MODE == "build") {
  dir.create(dirname(OUT), recursive = TRUE, showWarnings = FALSE)
  old <- if (file.exists(OUT)) paste(readLines(OUT, warn = FALSE), collapse = "\n") else NULL
  if (!identical(old, sub("\n$", "", text))) {
    tmp <- tempfile(tmpdir = dirname(OUT))
    writeLines(sub("\n$", "", text), tmp)
    file.rename(tmp, OUT)
    record("wrote ", OUT_REL, ", ", nrow(tab), " seasons, ", ncol(tab), " columns")
  } else {
    record(OUT_REL, " unchanged, not rewritten")
  }
}

# ---- DT-30: the table on disk equals the recomputation, cell for cell
clause("DT-30 table on disk", {
  if (!file.exists(OUT)) stop(OUT_REL, " is absent")
  disk <- utils::read.csv(OUT, colClasses = "character", na.strings = character(0),
                          check.names = FALSE)
  if (!identical(names(disk), names(tab)) || nrow(disk) != nrow(tab)) {
    stop("shape differs: disk ", nrow(disk), " x ", ncol(disk), ", recomputed ",
         nrow(tab), " x ", ncol(tab))
  }
  numeric_cols <- c("area_all_sqin", "area_cohort_sqin", grep("^(sel|meas)_d_", names(tab), value = TRUE))
  bad <- character(0)
  for (nm in names(tab)) {
    a <- trimws(disk[[nm]]); b <- trimws(as.character(tab[[nm]]))
    if (nm %in% numeric_cols) {
      both_blank <- a == "" & b == ""
      diff <- abs(suppressWarnings(as.numeric(a)) - suppressWarnings(as.numeric(b)))
      ok <- both_blank | (!is.na(diff) & diff <= CELL_TOL)
    } else {
      ok <- a == b
    }
    if (!all(ok)) bad <- c(bad, paste0(nm, " (seasons ", paste(tab$season[!ok], collapse = " "), ")"))
  }
  if (length(bad) == 0L) {
    pass("DT-30 ", OUT_REL, " matches the recomputation in all ", nrow(tab) * ncol(tab),
         " cells (counts and shares exact, contour cells within ", CELL_TOL, ")")
  } else {
    fail("DT-30 ", OUT_REL, " differs from the recomputation: ", paste(bad, collapse = "; "))
  }
})

# ---- the printed table and the two numbers the step exists for
cat("\nDT-30, ABS-height coverage per season, as a share of called pitches (open view, level mlb)\n")
cat(sprintf("%-6s %-12s %9s %9s %8s %8s %7s %7s %8s\n", "season", "regime", "called",
            "abs", "abs_sh", "ros_sh", "batters", "bat_abs", "sig_sh"))
for (i in seq_len(nrow(cov))) {
  cat(sprintf("%-6d %-12s %9s %9s %8.4f %8.4f %7d %7d %8.4f\n", as.integer(cov$season[i]),
              cov$regime[i], comma(cov$n_called[i]), comma(cov$n_called_abs_measured[i]),
              cov$abs_measured_share[i], cov$roster_offset_share[i], as.integer(cov$n_batters[i]),
              as.integer(cov$n_batters_abs_measured[i]), cov$in_season_signature_share[i]))
}
for (i in seq_len(nrow(dimc))) {
  record(sprintf("batter-seasons in dim_batter_season, %d: %d of %d ABS-measured, %.1f%%",
                 as.integer(dimc$season[i]), as.integer(dimc$n_batter_seasons_abs[i]),
                 as.integer(dimc$n_batter_seasons[i]),
                 100 * dimc$n_batter_seasons_abs[i] / dimc$n_batter_seasons[i]))
}

r22 <- cov[cov$season == 2022, ]
cat(sprintf("\nDT-30 2022: ABS-measured coverage is %.4f of %s called pitches (%s pitches), %s the %.2f trigger by %.4f.\n",
            r22$abs_measured_share, comma(r22$n_called), comma(r22$n_called_abs_measured),
            if (r22$abs_measured_share < TRIGGER) "below" else "at or above",
            TRIGGER, abs(TRIGGER - r22$abs_measured_share)))
below <- cov$season[cov$abs_below_trigger]
cat(sprintf("Seasons below the %.2f trigger: %s.\n", TRIGGER,
            if (length(below)) paste(below, collapse = ", ") else "none"))

s24 <- sel[["2024"]]
cat(sprintf(paste0(
  "\nSelection effect, 2024 (SOP W3.4, its own number): restricting to batters still active in 2026,\n",
  "with the roster+offset height held fixed, changes the 2024 50%% contour for a 72-inch batter by\n",
  "  area       %+.2f sq in (95%% interval %+.2f to %+.2f, conservative), of %.2f sq in\n",
  "  top        %+.3f in (%+.3f to %+.3f)\n",
  "  bottom     %+.3f in (%+.3f to %+.3f)\n",
  "  half-width %+.3f in (%+.3f to %+.3f)\n"),
  s24$d[["area_sqin"]], s24$lo[1], s24$hi[1], s24$area_all,
  s24$d[["top_in"]], s24$lo[2], s24$hi[2],
  s24$d[["bot_in"]], s24$lo[3], s24$hi[3],
  s24$d[["half_width_in"]], s24$lo[4], s24$hi[4]))
for (s in FIT_SEASONS) {
  x <- sel[[as.character(s)]]
  record(sprintf("%d selection (cohort_roster - all_roster): area %+.2f sq in [%+.2f, %+.2f], top %+.3f in, bot %+.3f in, half-width %+.3f in",
                 s, x$d[["area_sqin"]], x$lo[1], x$hi[1], x$d[["top_in"]], x$d[["bot_in"]], x$d[["half_width_in"]]))
  record(sprintf("%d measurement (cohort_measured - cohort_roster): area %+.2f sq in, top %+.3f in, bot %+.3f in, half-width %+.3f in",
                 s, x$meas[["area_sqin"]], x$meas[["top_in"]], x$meas[["bot_in"]], x$meas[["half_width_in"]]))
}

# ---- D-13: the fork is decided from this table before prereg-v1
clause("D-13 fork and prereg-v1 ordering", {
  dec <- readLines(file.path(ROOT, "DECISIONS.md"), warn = FALSE)
  ans <- grep("OWNER ANSWER, D-13", dec, value = TRUE, fixed = TRUE)
  Sys.setenv(GIT_TERMINAL_PROMPT = "0")
  tag <- suppressWarnings(system2("git", c("-C", ROOT, "tag", "-l", "prereg-v1"),
                                  stdout = TRUE, stderr = FALSE))
  tagged <- length(tag) > 0L && any(trimws(tag) == "prereg-v1")
  if (length(ans)) record("D-13 owner answer on file: ", sub("^#+\\s*", "", ans[1]))
  else record("D-13 owner answer: none on file in DECISIONS.md")
  if (!tagged) {
    pass("prereg-v1 is not tagged yet; the DT-30 table is on disk ahead of the tag")
  } else {
    at_tag <- suppressWarnings(system2("git", c("-C", ROOT, "show", paste0("prereg-v1:", OUT_REL)),
                                       stdout = TRUE, stderr = FALSE))
    same <- is.null(attr(at_tag, "status")) &&
      identical(sub("\n$", "", paste(at_tag, collapse = "\n")),
                paste(readLines(OUT, warn = FALSE), collapse = "\n"))
    if (length(ans) && same) {
      pass("prereg-v1 carries ", OUT_REL, " byte for byte, and D-13 has an owner answer")
    } else {
      fail("prereg-v1 is tagged but ", if (!same) paste0(OUT_REL, " differs from the tagged copy or is absent from it") else "D-13 has no owner answer")
    }
  }
})

cat(sprintf("\nW3.4 %s: %d PASS, %d FAIL, elapsed %.1f s\n", MODE, n_pass, n_fail,
            as.numeric(difftime(Sys.time(), t0, units = "secs"))))
quit(save = "no", status = if (n_fail > 0L) 1L else 0L)
