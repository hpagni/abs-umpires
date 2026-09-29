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
#      all_roster       every batter, roster height plus the one D-R0-02 offset.
#                       D-P4-04 (item 3) later gave batters outside the cohort
#                       their own offset. The selection effect holds one height
#                       rule fixed across its two arms, so it keeps the single
#                       offset, which is SENS-HEIGHT-SINGLE's rule.
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
# 3. The non-cohort offset, DECISIONS.md D-P4-04. Inside the ABS-measured cohort
#    roster height is round(measured height), so D-R0-02's offset (0.0022 in, the
#    2026 overlap mean) measures rounding and cannot see a listing error outside
#    the cohort. The evidence is pre-ABS Hawk-Eye sz_top, the W3.4 stat
#    verifier's method (logs/evidence/W3.4.verify-stat.log, section G). For each
#    season 2022, 2023 and 2024, every batter-season with at least 200 pitches
#    carrying sz_top gives its median sz_top in inches, and one OLS is fitted:
#
#      sz_top_in ~ h + nc     h = measured height in the cohort, roster height
#                             outside it; nc = 1 outside the cohort
#
#    Listed minus true height outside the cohort is -coef(nc) / coef(h), and its
#    SE is se(coef(nc)) / coef(h), conditional on the slope, as the verifier
#    reported it. The three seasons are pooled by inverse variance into one value,
#    and the offset is its negative, so that
#
#      H = h_roster_in + offset_in             inside the cohort (D-R0-02)
#      H = h_roster_in + offset_noncohort_in   outside it, in every season
#
#    The same fit with batter age (Statcast age_bat, the batter-season mean) as a
#    third covariate is reported beside it, not used. The value is written to
#    data/interim/dim_batter_season/calibration.json under the keys
#    absump.heights.NONCOHORT_KEYS; every existing key is kept. This step fits
#    no surface and reads no call: the evidence read selects batter, season,
#    sz_top, age_bat and game_date, from the 2022-2024 day files only. The
#    analysis table keeps H with the one D-R0-02 offset; the Chapter 1 fit code
#    moves the non-cohort rows at fit time, so no mart is rebuilt.
#
# WHAT IT READS. main_marts.v_called_pitch_open, main_marts.v_pitch_open (counts
# only) and main_marts.dim_batter_season in the DuckDB warehouse, read-only; the
# 2022-2024 interim Statcast day files for item 3; data/interim/dim_batter_season/
# calibration.json; docs/prereg/ch1.md, which must carry item 3's values; and
# DECISIONS.md. It fits nothing on 2025 or 2026: the fit seasons are asserted to
# be the pre-buffer regime before any fit runs. It reaches no host.
#
# WHAT IT WRITES. out/tables/height_coverage.csv, and D-P4-04's keys in
# calibration.json, each only when the content changed, so two runs in a row
# leave the tree as the first run left it. The check mode writes nothing.

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
source(file.path(ROOT, "R", "lib", "zone.R"))   # ABS_TOP_FRAC and ABS_BOT_FRAC, D-14

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

# D-P4-04, item 3
NC_SEASONS     <- 2022:2024         # the pre-2026 sz_top evidence; never 2025 or 2026
NC_LAST_DATE   <- as.Date("2024-12-31")
NC_MIN_PITCHES <- 200L              # the verifier's floor on a batter-season (section G)
NC_TOL_IN      <- 1e-9              # calibration.json against the recomputation
D_R0_02_OFFSET <- "0.0022"          # D-R0-02's cohort offset as the owner's answer states it
CAL_REL        <- "data/interim/dim_batter_season/calibration.json"
ANNEX_REL      <- "docs/prereg/ch1.md"
NC_CONVENTION  <- paste(
  "H = h_roster_in + offset_in for a batter inside the ABS-measured cohort (h_abs_in not null),",
  "and H = h_roster_in + offset_noncohort_in for a batter outside it, one value in every season",
  "2022-2026. Both offsets are added to roster height, in inches. offset_noncohort_in is negative",
  "because roster listings outside the cohort run tall. offset_in is D-R0-02's; offset_noncohort_in",
  "is D-P4-04's, pooled over 2022-2024 by R/ch1/03_heights.R (W3.4). The age-adjusted value is",
  "reported, not used.")

stopifnot(length(XG) == 301L, length(ZG) == 276L,
          all(FIT_SEASONS %in% 2022:2024), all(NC_SEASONS %in% 2022:2024))

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

# ---- D-P4-04: the non-cohort offset, from 2022-2024 sz_top, no call read
interim_statcast_dirs <- function(seasons) {
  code <- sprintf(paste0(
    'from absump import paths; ',
    'print(chr(10).join(str(paths.interim("statcast_pitch", "mlb", s, "%%d-06-01" %% s).parents[1]) ',
    'for s in (%s)))'), paste(seasons, collapse = ", "))
  out <- suppressWarnings(system2("uv", c("run", "--locked", "python", "-c", shQuote(code)),
                                  stdout = TRUE, stderr = TRUE))
  status <- attr(out, "status")
  if (!is.null(status) && status != 0L) {
    stop("could not read the interim Statcast layout from absump.paths: ",
         paste(out, collapse = " "), call. = FALSE)
  }
  out <- trimws(utils::tail(out, length(seasons)))
  if (length(out) != length(seasons) || !all(dir.exists(out))) {
    stop("interim Statcast season directories missing: ", paste(out, collapse = " "), call. = FALSE)
  }
  if (!all(basename(out) == paste0("season=", seasons))) {
    stop("interim directories are not the seasons asked for: ", paste(out, collapse = " "), call. = FALSE)
  }
  out
}
nc_dirs <- interim_statcast_dirs(NC_SEASONS)
nc_src <- sprintf("read_parquet([%s], union_by_name = true)",
                  paste(sprintf("'%s'", file.path(nc_dirs, "*", "*.parquet")), collapse = ", "))
# The two reads of item 3. They name five columns and no call column.
nc_guard_sql <- sprintf("
SELECT season, count(*) AS n_pitches, count(sz_top) AS n_sz_top,
       min(game_date) AS first_date, max(game_date) AS last_date
FROM %s
GROUP BY season ORDER BY season", nc_src)
nc_agg_sql <- sprintf("
SELECT season, batter, count(*) AS n_pitches, median(sz_top) * 12 AS sz_top_in,
       avg(age_bat) AS age_bat, count(age_bat) AS n_age
FROM %s
WHERE sz_top IS NOT NULL
GROUP BY season, batter
HAVING count(*) >= %d", nc_src, NC_MIN_PITCHES)
nc_wh_sql <- sprintf("
SELECT season, count(*) AS n_pitches, count(sz_top) AS n_sz_top
FROM main_marts.v_pitch_open
WHERE level = 'mlb' AND season BETWEEN %d AND %d
GROUP BY season ORDER BY season", min(NC_SEASONS), max(NC_SEASONS))
nc_dim_sql <- sprintf("
SELECT season, batter, h_abs_in, h_roster_in
FROM main_marts.dim_batter_season
WHERE level = 'mlb' AND season BETWEEN %d AND %d", min(NC_SEASONS), max(NC_SEASONS))

nc_guard <- DBI::dbGetQuery(con, nc_guard_sql)
nc_wh <- DBI::dbGetQuery(con, nc_wh_sql)
nc_agg <- DBI::dbGetQuery(con, nc_agg_sql)
nc_dim <- DBI::dbGetQuery(con, nc_dim_sql)
for (nm in c("n_pitches", "n_sz_top")) {
  nc_guard[[nm]] <- as.numeric(nc_guard[[nm]]); nc_wh[[nm]] <- as.numeric(nc_wh[[nm]])
}

clause("D-P4-04 evidence reads 2022-2024 only, and no call", {
  cols_named <- unique(unlist(regmatches(c(nc_guard_sql, nc_agg_sql),
                                         gregexpr("\\b(description|call_[a-z]+|events|type|cs)\\b",
                                                  c(nc_guard_sql, nc_agg_sql)))))
  if (identical(as.integer(nc_guard$season), NC_SEASONS) &&
      max(as.Date(nc_guard$last_date)) <= NC_LAST_DATE && length(cols_named) == 0L) {
    pass(sprintf("sz_top evidence: seasons %s only, last date %s, no call column named",
                 paste(nc_guard$season, collapse = " "), format(max(as.Date(nc_guard$last_date)))))
  } else {
    fail("the D-P4-04 evidence read reached outside 2022-2024 or names a call column: seasons ",
         paste(nc_guard$season, collapse = " "), ", last date ", format(max(as.Date(nc_guard$last_date))),
         ", call columns ", paste(cols_named, collapse = " "))
  }
})
clause("D-P4-04 evidence is the warehouse's pitch set", {
  if (identical(nc_guard$n_pitches, nc_wh$n_pitches) && identical(nc_guard$n_sz_top, nc_wh$n_sz_top)) {
    pass("interim day files and main_marts.v_pitch_open agree on pitches and sz_top counts: ",
         paste(sprintf("%d %s / %s", as.integer(nc_wh$season), comma(nc_wh$n_pitches), comma(nc_wh$n_sz_top)),
               collapse = "; "))
  } else {
    fail("interim day files and v_pitch_open disagree: ",
         paste(nc_guard$season, nc_guard$n_pitches, nc_wh$n_pitches, nc_guard$n_sz_top, nc_wh$n_sz_top,
               collapse = "; "))
  }
})

nc_ev <- merge(nc_agg, nc_dim, by = c("season", "batter"), all.x = TRUE, sort = TRUE)
nc_ev$season <- as.integer(nc_ev$season)
nc_ev$nc <- as.numeric(is.na(nc_ev$h_abs_in))
nc_ev$h <- ifelse(is.na(nc_ev$h_abs_in), nc_ev$h_roster_in, nc_ev$h_abs_in)
clause("D-P4-04 evidence rows carry a height and an age", {
  if (!anyNA(nc_ev$h) && !anyNA(nc_ev$age_bat)) {
    pass(sprintf("%s batter-seasons with >= %d sz_top pitches, each with a height and a batter age",
                 comma(nrow(nc_ev)), NC_MIN_PITCHES))
  } else {
    fail(sprintf("%d batter-seasons without a height, %d without an age", sum(is.na(nc_ev$h)),
                 sum(is.na(nc_ev$age_bat))))
  }
})

nc_fit <- function(x, age) {
  m <- stats::lm(if (age) sz_top_in ~ h + nc + age_bat else sz_top_in ~ h + nc, data = x)
  b <- stats::coef(m)
  V <- stats::vcov(m)
  g <- setNames(rep(0, length(b)), names(b))
  g[["h"]] <- b[["nc"]] / b[["h"]]^2
  g[["nc"]] <- -1 / b[["h"]]
  list(delta = -b[["nc"]] / b[["h"]], se = sqrt(V["nc", "nc"]) / b[["h"]],
       se_delta_method = sqrt(drop(t(g) %*% V %*% g)), slope = b[["h"]],
       age_coef = if (age) b[["age_bat"]] else NA_real_,
       n_noncohort = sum(x$nc == 1), n_cohort = sum(x$nc == 0))
}
nc_by <- do.call(rbind, lapply(NC_SEASONS, function(s) {
  x <- nc_ev[nc_ev$season == s, ]
  u <- nc_fit(x, FALSE)
  a <- nc_fit(x, TRUE)
  data.frame(season = s, n_batters_noncohort = u$n_noncohort, n_batters_cohort = u$n_cohort,
             slope_in_per_in = u$slope, listed_minus_true_in = u$delta, se_in = u$se,
             se_delta_method_in = u$se_delta_method,
             age_adjusted_listed_minus_true_in = a$delta, age_adjusted_se_in = a$se,
             age_coef_in_per_year = a$age_coef)
}))
ivw <- function(est, se) { w <- 1 / se^2; c(est = sum(w * est) / sum(w), se = 1 / sqrt(sum(w))) }
nc_pool <- ivw(nc_by$listed_minus_true_in, nc_by$se_in)
nc_pool_age <- ivw(nc_by$age_adjusted_listed_minus_true_in, nc_by$age_adjusted_se_in)
o_nc <- -nc_pool[["est"]]
o_nc_age <- -nc_pool_age[["est"]]
nc_batters <- unique(nc_ev$batter[nc_ev$nc == 1])

nc_payload <- list(
  convention = NC_CONVENTION,
  offset_noncohort_in = o_nc,
  offset_noncohort_se_in = nc_pool[["se"]],
  offset_noncohort_age_adjusted_in = o_nc_age,
  offset_noncohort_age_adjusted_se_in = nc_pool_age[["se"]],
  noncohort_evidence = list(
    decision = "DECISIONS.md D-P4-04; logs/evidence/W3.4.verify-stat.log, section G",
    method = paste(
      "Per season, batter-seasons with at least min_pitches pitches carrying sz_top; median sz_top",
      "in inches regressed by OLS on h (measured height inside the cohort, roster height outside",
      "it) and nc (1 outside the cohort). listed_minus_true_in = -coef(nc) / coef(h), se_in =",
      "se(coef(nc)) / coef(h). Seasons pooled by inverse variance; offset_noncohort_in is minus",
      "the pooled value. The age-adjusted fit adds the batter-season mean of Statcast age_bat."),
    seasons = NC_SEASONS,
    min_pitches = NC_MIN_PITCHES,
    by_season = nc_by,
    pooled_listed_minus_true_in = nc_pool[["est"]],
    pooled_se_in = nc_pool[["se"]],
    age_adjusted_pooled_listed_minus_true_in = nc_pool_age[["est"]],
    age_adjusted_pooled_se_in = nc_pool_age[["se"]],
    n_batter_seasons_noncohort = sum(nc_ev$nc == 1),
    n_batters_noncohort = length(nc_batters)))

for (i in seq_len(nrow(nc_by))) {
  r <- nc_by[i, ]
  record(sprintf(paste0("D-P4-04 %d: %d outside the cohort, %d inside, slope %.3f; listed minus true %+.3f in ",
                        "(SE %.3f, delta method %.3f); age-adjusted %+.3f in (SE %.3f), age %+.4f in a year"),
                 r$season, r$n_batters_noncohort, r$n_batters_cohort, r$slope_in_per_in,
                 r$listed_minus_true_in, r$se_in, r$se_delta_method_in,
                 r$age_adjusted_listed_minus_true_in, r$age_adjusted_se_in, r$age_coef_in_per_year))
}
record(sprintf(paste0("D-P4-04 pooled 2022-2024: listed minus true %+.4f in, SE %.4f in (%.1f SE); ",
                      "offset_noncohort_in %+.4f in. Age-adjusted, reported only: %+.4f in, SE %.4f in"),
               nc_pool[["est"]], nc_pool[["se"]], nc_pool[["est"]] / nc_pool[["se"]], o_nc,
               o_nc_age, nc_pool_age[["se"]]))
record(sprintf(paste0("D-P4-04 the three seasons share batters: %s non-cohort batter-seasons are %s distinct ",
                      "batters, so the pooled SE, which treats the seasons as independent, is a lower bound"),
               comma(sum(nc_ev$nc == 1)), comma(length(nc_batters))))

# What the rule moves (the annex table): the non-cohort share of called pitches,
# and the zone top and bottom of those batters, 53.5% and 27% of the height change.
d_h <- o_nc - o
shift_top <- ABS_TOP_FRAC * d_h
shift_bot <- ABS_BOT_FRAC * d_h
nc_move <- data.frame(season = as.integer(cov$season), n_called = cov$n_called,
                      n_noncohort = cov$n_called - cov$n_called_abs_measured)
nc_move$share <- nc_move$n_noncohort / nc_move$n_called
nc_move <- nc_move[nc_move$season %in% 2022:2025, ]
annex_row <- function(r) sprintf("| %d | %s | %s | %.4f | %.3f | %.3f |", r$season,
                                 comma(r$n_called), comma(r$n_noncohort), r$share, shift_top, shift_bot)
annex_rows <- vapply(seq_len(nrow(nc_move)), function(i) annex_row(nc_move[i, ]), "")
record(sprintf("D-P4-04 height change outside the cohort %+.4f in (offset_noncohort_in - offset_in): zone top %+.3f in, bottom %+.3f in",
               d_h, shift_top, shift_bot))
for (ln in annex_rows) record("D-P4-04 annex row ", ln)

cal_path <- file.path(ROOT, CAL_REL)
if (MODE == "build") {
  tmp <- tempfile(fileext = ".json")
  writeLines(jsonlite::toJSON(nc_payload, auto_unbox = TRUE, digits = NA, pretty = TRUE), tmp)
  out <- suppressWarnings(system2("uv", c("run", "--locked", "python", "-m", "absump.heights",
                                          "--merge-noncohort", shQuote(tmp)),
                                  stdout = TRUE, stderr = TRUE))
  unlink(tmp)
  status <- attr(out, "status")
  if (!is.null(status) && status != 0L) {
    stop("the calibration merge failed: ", paste(out, collapse = " "), call. = FALSE)
  }
  record(utils::tail(out, 1L))
}

clause("D-P4-04 calibration.json", {
  if (!file.exists(cal_path)) stop(CAL_REL, " is absent")
  cal <- jsonlite::fromJSON(cal_path, simplifyVector = TRUE)
  miss <- setdiff(names(nc_payload), names(cal))
  if (length(miss)) stop(CAL_REL, " lacks ", paste(miss, collapse = ", "))
  if (!identical(cal$convention, NC_CONVENTION)) stop("the convention string differs")
  if (!(is.numeric(cal$offset_noncohort_in) && length(cal$offset_noncohort_in) == 1L)) {
    stop("offset_noncohort_in is not one number")
  }
  got <- c(cal$offset_noncohort_in, cal$offset_noncohort_se_in, cal$offset_noncohort_age_adjusted_in,
           cal$offset_noncohort_age_adjusted_se_in,
           unlist(cal$noncohort_evidence$by_season[, setdiff(names(nc_by), "season")]))
  want <- c(o_nc, nc_pool[["se"]], o_nc_age, nc_pool_age[["se"]],
            unlist(nc_by[, setdiff(names(nc_by), "season")]))
  dev <- max(abs(got - want))
  if (length(got) != length(want) || !is.finite(dev) || dev > NC_TOL_IN) {
    stop(sprintf("the file does not reproduce from the inputs: max |file - recomputed| %.3g", dev))
  }
  pass(sprintf("%s carries D-P4-04: offset_noncohort_in %+.6f in, SE %.6f in, one value for every season; it reproduces within %.0e",
               CAL_REL, cal$offset_noncohort_in, cal$offset_noncohort_se_in, NC_TOL_IN))
})

clause("D-P4-04 leaves the cohort offset as D-R0-02 set it", {
  cal <- jsonlite::fromJSON(cal_path, simplifyVector = TRUE)
  if (abs(cal$offset_in - o) < 1e-12 && sprintf("%.4f", cal$offset_in) == D_R0_02_OFFSET) {
    pass(sprintf("offset_in %.12f in: the dimension's offset and D-R0-02's %s in", cal$offset_in, D_R0_02_OFFSET))
  } else {
    fail(sprintf("offset_in %.12f in is not the dimension's %.12f or D-R0-02's %s", cal$offset_in, o, D_R0_02_OFFSET))
  }
})

clause("D-P4-04 in the annex", {
  annex <- readLines(file.path(ROOT, ANNEX_REL), warn = FALSE)
  txt <- paste(annex, collapse = "\n")
  need <- c(sprintf("%.3f in", abs(o_nc)), sprintf("SE %.3f in", nc_pool[["se"]]),
            sprintf("%.3f in", abs(o_nc_age)), annex_rows)
  miss <- need[!vapply(need, function(s) grepl(s, txt, fixed = TRUE), TRUE)]
  if (length(miss) == 0L) {
    pass(ANNEX_REL, " states the pooled offset, its SE, the age-adjusted value and all ",
         length(annex_rows), " rows of the what-it-moves table")
  } else {
    fail(ANNEX_REL, " lacks: ", paste(miss, collapse = " || "))
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
