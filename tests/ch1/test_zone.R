#!/usr/bin/env Rscript
# tests/ch1/test_zone.R -- the zone and kinematics acceptance test. SOP step W3.3.
#
# Owns UT-11 (the re-projection root), UT-12 (the release-column substitution
# guard) and UT-13 (the ABS height fractions), plus the edge, plane, golden-file
# and cross-language clauses of SOP section 3, W3.3.
#
# Run from the repository root:  Rscript tests/ch1/test_zone.R
#
# It prints one line per clause and exits 1 after reporting every clause that
# failed, not only the first. Three line kinds:
#
#   PASS   an assertion with a threshold, and the measured number
#   FAIL   the same, with the measured number that missed it
#   RECORD a measured number that nothing asserts, printed so a reader can see
#          what the data does rather than take the assertion's word for it
#   DEFER  a clause whose input is not on this machine, with the reason. A
#          DEFER never passes silently: it is printed, counted and listed again
#          in the summary.
#
# THE POPULATION OF UT-11's t-BAND. The clause "t in (0.30, 0.60) s at both
# planes" is asserted over pitches with release_speed >= 70 mph, and the SOP
# clause is written over that same population. The band is a sanity check on
# the kinematics, not a claim about baseball: a 50 mph lob really does take
# longer than 0.60 s. Pitches under 70 mph are counted, their slowest speed and
# largest t printed, and they remain under the two clauses that hold at any
# speed, t_mid > t_front and dz < 0. Nothing here asserts a band the SOP does
# not state, and nothing is dropped without being named. That population is
# DEV-42 in docs/DEVIATIONS.md, confirmed under DECISIONS.md D-P4-01 (the R0
# delegation: an applied default, not an owner answer). A RECORD line also
# prints the band read with no speed filter at all, so the literal clause's own
# count is on every run.
#
# THE POPULATION OF THE 0.0011 ft CLAUSE. "2026 CSV re-projected mid -> front
# matches API pX/pZ to < 0.0011 ft" is asserted over called pitches, the
# project's definition (called_strike, ball, blocked_ball, as in
# fct_called_pitch). The SOP set the bar on the 281 pitches of one game. Over
# every pitch on the five days two batted balls, both curveballs at 72 mph or
# more, sit above it by at most 2.7e-5 ft. A RECORD line names them on every
# run. This population is recorded in docs/DEVIATIONS.md DEV-43 and applied under
# DECISIONS.md D-P4-02 (the R0 delegation).
#
# WHAT IS ON THIS MACHINE. MLB Statcast CSV for 2022-2026. The Stats API side
# (x0/y0/z0) for all of MLB 2026 through feed_pitch and pitch_joined, and for
# one MLB 2025 game, 776311 on 2025-09-15, as a raw feed under data/raw. There
# is no AAA pitch-level CSV, so the AAA 2024 plane clause is deferred (DEV-25,
# DEV-27). Everything that needs only the CSV runs for every season.
#
# THE SEAL. Only 2026 dates before config/seal.yml's seal_start_date are read,
# and the boundary is read from that file rather than written here.

options(warn = 1, digits = 12)
t_start <- Sys.time()

## --- where we are ------------------------------------------------------------

args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
ROOT <- if (length(file_arg) == 1) {
  normalizePath(file.path(dirname(sub("^--file=", "", file_arg)), "..", ".."))
} else {
  normalizePath(getwd())
}
setwd(ROOT)

suppressPackageStartupMessages({
  library(duckdb)
  library(DBI)
  library(arrow)
})

source(file.path(ROOT, "R", "lib", "zone.R"))

## --- the little harness ------------------------------------------------------

n_pass <- 0L; failures <- character(0); defers <- character(0)

check <- function(label, ok, detail) {
  if (isTRUE(ok)) {
    n_pass <<- n_pass + 1L
    cat(sprintf("PASS   %-46s %s\n", label, detail))
  } else {
    failures <<- c(failures, sprintf("%s -- %s", label, detail))
    cat(sprintf("FAIL   %-46s %s\n", label, detail))
  }
}
record <- function(label, detail) cat(sprintf("RECORD %-46s %s\n", label, detail))
defer  <- function(label, reason) {
  defers <<- c(defers, sprintf("%s -- %s", label, reason))
  cat(sprintf("DEFER  %-46s %s\n", label, reason))
}

fmt <- function(x, d = 9) formatC(x, format = "f", digits = d)

## --- paths, the seal boundary and the sample -------------------------------

SC  <- function(season, day) sprintf(
  "%s/data/interim/statcast_pitch/level=mlb/season=%s/date=%s/part-000.parquet", ROOT, season, day)
PJ  <- function(day) sprintf(
  "%s/data/interim/pitch_joined/level=mlb/season=2026/date=%s/part-000.parquet", ROOT, day)
FP  <- function(day) sprintf(
  "%s/data/interim/feed_pitch/level=mlb/season=2026/date=%s/part-000.parquet", ROOT, day)

seal_yml <- readLines(file.path(ROOT, "config", "seal.yml"), warn = FALSE)
seal_start <- as.Date(gsub('[" ]', "", sub("^seal_start_date:", "",
  grep("^seal_start_date:", seal_yml, value = TRUE)[1])))

# Five 2026 days spread across the season, all before the seal, and one day per
# prior season. The 2026 days are fixed here so the test reads the same rows on
# every run; each is checked against the seal boundary before it is opened.
DAYS_2026 <- c("2026-04-11", "2026-05-18", "2026-06-23", "2026-07-29", "2026-09-01")
DAYS_PRIOR <- c("2022" = "2022-07-05", "2023" = "2023-06-29",
                "2024" = "2024-06-26", "2025" = "2025-06-25")
GOLDEN_DAY <- "2024-06-26"      # the golden file's source day
SLOW_MPH <- 70                  # the competitive-speed floor of the UT-11 t-band
                                # clause; see the comment above the check below

stopifnot(all(as.Date(DAYS_2026) < seal_start))

con <- dbConnect(duckdb::duckdb())

q <- function(sql) dbGetQuery(con, sql)

## ===========================================================================
## 1. UT-12, the release-column substitution guard
## ===========================================================================
#
# CSV release_pos_x/y/z are the release point and are not x0/y0/z0:
# release_pos_y == 54.18 against y0 == 50.0022, and substituting them breaks
# the projection by up to 1.04 ft. The Python twin refuses them with
# ValueError. The R module refuses the other half of the same trap, a pitch
# whose vy0 is not negative or whose ay is not positive, through stopifnot.

py <- file.path(ROOT, ".venv", "bin", "python")
if (!file.exists(py)) py <- Sys.which("python3")

py_run <- function(code) {
  out <- suppressWarnings(system2(py, c("-c", shQuote(code)),
                                  stdout = TRUE, stderr = TRUE, env = "PYTHONPATH=src"))
  list(status = attr(out, "status") %||% 0L, text = paste(out, collapse = " "))
}
`%||%` <- function(a, b) if (is.null(a)) b else a

PY_CALL <- paste0(
  "from absump.geometry import reproject;",
  "reproject(0.12,2.31,5.104,-136.346,-5.012,-9.147,28.540,-13.958,%s,%s)")

r_ok   <- py_run(sprintf(PY_CALL, "17/12", "8.5/12"))
r_from <- py_run(sprintf(PY_CALL, "54.18", "8.5/12"))
r_to   <- py_run(sprintf(PY_CALL, "17/12", "54.18"))
r_y0   <- py_run(sprintf(PY_CALL, "50.0022", "8.5/12"))

check("UT-12 twin accepts the two plate planes", r_ok$status == 0L,
      sprintf("exit %d on reproject(front -> mid)", r_ok$status))
check("UT-12 twin refuses release_pos_y as y_from",
      r_from$status != 0L && grepl("ValueError", r_from$text),
      sprintf("exit %d, %s", r_from$status,
              if (grepl("ValueError", r_from$text)) "ValueError raised" else "no ValueError"))
check("UT-12 twin refuses release_pos_y as y_to",
      r_to$status != 0L && grepl("ValueError", r_to$text),
      sprintf("exit %d, %s", r_to$status,
              if (grepl("ValueError", r_to$text)) "ValueError raised" else "no ValueError"))
check("UT-12 twin refuses the API reference plane y0",
      r_y0$status != 0L && grepl("ValueError", r_y0$text),
      sprintf("y0 = 50.0022 ft is not a plate plane, exit %d", r_y0$status))

# The other two release columns. A pandas Series carries its column name, so
# the twin refuses release_pos_x or release_pos_z handed over in place of
# plate_x or plate_z, and accepts the real plate columns in the same form.
PY_SERIES <- paste0(
  "import pandas as pd;",
  "from absump.geometry import reproject;",
  "d = pd.DataFrame(dict(plate_x=[0.12], plate_z=[2.31], release_pos_x=[-1.80],",
  "release_pos_z=[5.90], vx0=[5.104], vy0=[-136.346], vz0=[-5.012], ax=[-9.147],",
  "ay=[28.540], az=[-13.958]));",
  "reproject(d.%s, d.%s, d.vx0, d.vy0, d.vz0, d.ax, d.ay, d.az, 17/12, 8.5/12)")
s_ok <- py_run(sprintf(PY_SERIES, "plate_x", "plate_z"))
s_rx <- py_run(sprintf(PY_SERIES, "release_pos_x", "plate_z"))
s_rz <- py_run(sprintf(PY_SERIES, "plate_x", "release_pos_z"))
check("UT-12 twin accepts plate_x/plate_z columns", s_ok$status == 0L,
      sprintf("exit %d on pandas columns named plate_x and plate_z", s_ok$status))
check("UT-12 twin refuses release_pos_x as plate_x",
      s_rx$status != 0L && grepl("ValueError", s_rx$text),
      sprintf("exit %d, %s", s_rx$status,
              if (grepl("ValueError", s_rx$text)) "ValueError raised" else "no ValueError"))
check("UT-12 twin refuses release_pos_z as plate_z",
      s_rz$status != 0L && grepl("ValueError", s_rz$text),
      sprintf("exit %d, %s", s_rz$status,
              if (grepl("ValueError", s_rz$text)) "ValueError raised" else "no ValueError"))

# The size of the trap, measured rather than quoted: release_pos_y is 54.18 ft,
# so a caller who substitutes it projects from the wrong plane.
g24 <- q(sprintf("select plate_x, plate_z, vx0, vy0, vz0, ax, ay, az,
                         release_pos_x, release_pos_y, release_pos_z
                  from read_parquet('%s')
                  where plate_x is not null and vy0 is not null and ay is not null
                    and release_pos_y is not null", SC(2024, GOLDEN_DAY)))
# The SOP's own form of the trap: the release point read as if it were the
# reference state (x0, y0, z0) and integrated to the front plane.
ta <- (-g24$vy0 - sqrt(g24$vy0^2 - 2 * g24$ay * (g24$release_pos_y - Y_FRONT_FT))) / g24$ay
sub_x <- g24$release_pos_x + g24$vx0 * ta + 0.5 * g24$ax * ta^2
sub_z <- g24$release_pos_z + g24$vz0 * ta + 0.5 * g24$az * ta^2
record("UT-12 size of the substitution error",
       sprintf("release_pos_y %s .. %s ft against the reference plane 50.0: the release point read as (x0, y0, z0) misses the published crossing by up to %s ft over %d pitches, and says nothing while it does it",
               fmt(min(g24$release_pos_y), 2), fmt(max(g24$release_pos_y), 2),
               fmt(max(abs(sub_x - g24$plate_x), abs(sub_z - g24$plate_z)), 3), nrow(g24)))

check("UT-12 R module refuses vy0 >= 0",
      inherits(try(t_at_y(Y_FRONT_FT, 136.346, 28.540), silent = TRUE), "try-error"),
      "stopifnot(all(vy0 < 0)) fires")
check("UT-12 R module refuses ay <= 0",
      inherits(try(t_at_y(Y_FRONT_FT, -136.346, -28.540), silent = TRUE), "try-error"),
      "stopifnot(all(ay > 0)) fires")

## ===========================================================================
## 2. UT-11, the root
## ===========================================================================

# 2.1 the closed form against a brute-force smallest-positive-root solve.
# Bisection of f(t) = 0.5*ay*t^2 + vy0*t + (Y_REF - y), which shares the
# polynomial with the closed form and none of its algebra, on [0, -vy0/ay].
# f(0) = Y_REF - y > 0, and -vy0/ay is the vertex of the parabola, where f is at
# its minimum and negative for any pitch that reaches the plane: f(0) > 0 and
# f(vertex) < 0 are asserted, and the smaller root is the only root in that
# bracket, at any speed. The larger root lies beyond the vertex. The solve runs
# over every pitch of the nine days in 2.2, with no speed filter.
brute_root <- function(y, vy0, ay, iters = 200L) {
  f <- function(t) 0.5 * ay * t^2 + vy0 * t + (Y_REF_FT - y)
  lo <- rep(0, length(vy0)); hi <- -vy0 / ay
  stopifnot(all(f(lo) > 0), all(f(hi) < 0))
  for (i in seq_len(iters)) {
    mid <- 0.5 * (lo + hi)
    neg <- f(mid) < 0
    hi[neg] <- mid[neg]; lo[!neg] <- mid[!neg]
  }
  0.5 * (lo + hi)
}

# 2.2 t in (0.30, 0.60) s at both planes over pitches with release_speed >= 70
# mph, t_mid > t_front pitch by pitch and dz < 0 wherever the vertical velocity
# at the plate is negative over every pitch at any speed, all of it over five
# 2026 days and one day per prior season.
all_days <- c(DAYS_2026, unname(DAYS_PRIOR))
all_seasons <- c(rep(2026, length(DAYS_2026)), names(DAYS_PRIOR))
n_t <- 0L; n_slow <- 0L; t_lo <- Inf; t_hi <- -Inf; slow_hi <- -Inf; slow_mph <- -Inf
bad_range <- 0L; bad_order <- 0L; n_vzneg <- 0L; bad_dz <- 0L; dz_means <- numeric(0)
brute_max <- c(front = 0, mid = 0); far_min <- Inf; closed_max <- -Inf
lit_out <- 0L; lit_mph <- -Inf; lit_ep <- 0L
for (i in seq_along(all_days)) {
  d <- q(sprintf("select plate_x, plate_z, vx0, vy0, vz0, ax, ay, az, release_speed,
                         pitch_type
                  from read_parquet('%s')
                  where vy0 is not null and ay is not null and plate_x is not null",
                 SC(all_seasons[i], all_days[i])))
  tf <- t_at_y(Y_FRONT_FT, d$vy0, d$ay); tm <- t_at_y(Y_MID_FT, d$vy0, d$ay)
  brute_max["front"] <- max(brute_max["front"], abs(tf - brute_root(Y_FRONT_FT, d$vy0, d$ay)))
  brute_max["mid"]   <- max(brute_max["mid"],   abs(tm - brute_root(Y_MID_FT, d$vy0, d$ay)))
  far_min <- min(far_min, (-d$vy0 + sqrt(d$vy0^2 - 2 * d$ay * (Y_REF_FT - Y_FRONT_FT))) / d$ay)
  closed_max <- max(closed_max, tm)
  out <- tf <= 0.30 | tf >= 0.60 | tm <= 0.30 | tm >= 0.60
  lit_out <- lit_out + sum(out)
  if (any(out)) {
    lit_mph <- max(lit_mph, max(d$release_speed[out], na.rm = TRUE))
    lit_ep <- lit_ep + sum(d$pitch_type[out] %in% "EP")
  }
  fast <- !is.na(d$release_speed) & d$release_speed >= SLOW_MPH
  n_t <- n_t + sum(fast); n_slow <- n_slow + sum(!fast)
  t_lo <- min(t_lo, min(tf[fast])); t_hi <- max(t_hi, max(tm[fast]))
  if (any(!fast)) {
    slow_hi <- max(slow_hi, max(tm[!fast]))
    slow_mph <- max(slow_mph, max(d$release_speed[!fast], na.rm = TRUE))
  }
  bad_range <- bad_range + sum(tf[fast] <= 0.30 | tf[fast] >= 0.60 |
                               tm[fast] <= 0.30 | tm[fast] >= 0.60)
  bad_order <- bad_order + sum(!(tm > tf))
  r <- reproject(d$plate_x, d$plate_z, d$vx0, d$vy0, d$vz0, d$ax, d$ay, d$az,
                 Y_FRONT_FT, Y_MID_FT)
  dz <- (r$z - d$plate_z) * 12
  vz_plate <- d$vz0 + d$az * tf
  n_vzneg <- n_vzneg + sum(vz_plate < 0)
  bad_dz <- bad_dz + sum(dz[vz_plate < 0] >= 0)
  dz_means <- c(dz_means, mean(dz))
}
for (nm in c("front", "mid")) {
  check(sprintf("UT-11 closed form == brute force at %s", nm), brute_max[[nm]] < 1e-12,
        sprintf("max |delta| %.3e s < 1e-12, n = %d, every speed", brute_max[[nm]],
                n_t + n_slow))
}
record("UT-11 the root not taken",
       sprintf("larger root min %s s over %d pitches; the closed form returns max %s s",
               fmt(far_min, 4), n_t + n_slow, fmt(closed_max, 4)))
# THE POPULATION OF THE t-BAND CLAUSE. (0.30, 0.60) s is a sanity check on the
# kinematics, not a claim about baseball. A 50 mph lob genuinely takes longer
# than 0.60 s to reach the plate, so the band is true only of competitive-speed
# pitching. The clause is therefore stated, here and in the SOP, over one
# explicit population: release_speed >= SLOW_MPH mph. The pitches below that
# floor -- eephus and position players -- are not defects and are not dropped
# in silence: the two lines below count them, name the slowest and the largest
# t, and the next two clauses (t_mid > t_front and dz < 0) are asserted over
# every pitch with no speed filter at all, so the excluded population is still
# covered by the assertions that can be stated over it. The band is not widened
# to swallow them.
check(sprintf("UT-11 t in (0.30, 0.60) s, >= %d mph, 2 planes", SLOW_MPH), bad_range == 0L,
      sprintf("%d of %d pitches at or above %d mph outside, range %s .. %s s, %d days",
              bad_range, n_t, SLOW_MPH, fmt(t_lo, 4), fmt(t_hi, 4), length(all_days)))
record("UT-11 the population the band excludes",
       sprintf("%d of %d pitches (%.3f%%) are under %d mph and are outside the clause's population, asserted on by no band; slowest %s mph, largest t %s s, still far under the smaller of the two far roots",
               n_slow, n_t + n_slow, 100 * n_slow / (n_t + n_slow), SLOW_MPH,
               fmt(slow_mph, 1), fmt(slow_hi, 4)))
record("UT-11 the band read with no speed filter",
       sprintf("%d of %d pitches (%.3f%%) fall outside (0.30, 0.60) s at either plane; the fastest of them is %s mph and %d are eephus (EP)",
               lit_out, n_t + n_slow, 100 * lit_out / (n_t + n_slow), fmt(lit_mph, 1), lit_ep))
check("UT-11 t_mid > t_front pitch by pitch, every speed", bad_order == 0L,
      sprintf("%d of %d pitches violate it, no speed filter", bad_order, n_t + n_slow))
check("UT-11 dz < 0 where vz at the plate is negative", bad_dz == 0L,
      sprintf("%d of %d such pitches violate it, no speed filter", bad_dz, n_vzneg))

# 2.3 the round trip, front -> mid -> front.
gold_src <- q(sprintf("select plate_x, plate_z, vx0, vy0, vz0, ax, ay, az
                       from read_parquet('%s')
                       where plate_x is not null and vy0 is not null and ay is not null",
                      SC(2024, GOLDEN_DAY)))
m <- reproject(gold_src$plate_x, gold_src$plate_z, gold_src$vx0, gold_src$vy0, gold_src$vz0,
               gold_src$ax, gold_src$ay, gold_src$az, Y_FRONT_FT, Y_MID_FT)
b <- reproject(m$x, m$z, gold_src$vx0, gold_src$vy0, gold_src$vz0,
               gold_src$ax, gold_src$ay, gold_src$az, Y_MID_FT, Y_FRONT_FT)
rt <- max(abs(b$x - gold_src$plate_x), abs(b$z - gold_src$plate_z))
check("UT-11 round trip front -> mid -> front", rt < 1e-12,
      sprintf("max |delta| %.3e ft < 1e-12, n = %d", rt, nrow(gold_src)))

## ===========================================================================
## 3. The planes: 2026 CSV against the Stats API, and direct integration
## ===========================================================================

api_all_max <- 0; api_called_max <- 0; api_n <- 0L; api_called_n <- 0L; api_over <- 0L
api_over_rows <- character(0)
direct_mid <- 0; direct_front_api <- 0
for (day in DAYS_2026) {
  d <- q(sprintf("select c.game_pk, c.at_bat_number, c.pitch_number,
                         c.plate_x, c.plate_z, c.vx0, c.vy0, c.vz0, c.ax, c.ay, c.az,
                         c.description, j.p_x, j.p_z, f.x0, f.y0, f.z0
                  from read_parquet('%s') c
                  join read_parquet('%s') j
                    on c.game_pk = j.game_pk and c.at_bat_number = j.at_bat_number
                   and c.pitch_number = j.pitch_number
                  join read_parquet('%s') f
                    on j.game_pk = f.game_pk and j.at_bat_number = f.at_bat_number
                   and j.pitch_slot = f.pitch_slot
                  where c.plate_x is not null and j.p_x is not null and f.x0 is not null",
                 SC(2026, day), PJ(day), FP(day)))
  # the 2026 CSV is published at the middle plane; the API at the front
  r <- reproject(d$plate_x, d$plate_z, d$vx0, d$vy0, d$vz0, d$ax, d$ay, d$az,
                 Y_MID_FT, Y_FRONT_FT)
  e <- pmax(abs(r$x - d$p_x), abs(r$z - d$p_z))
  called <- d$description %in% c("called_strike", "ball", "blocked_ball")
  api_all_max <- max(api_all_max, max(e)); api_called_max <- max(api_called_max, max(e[called]))
  api_n <- api_n + length(e); api_called_n <- api_called_n + sum(called)
  api_over <- api_over + sum(e >= 0.0011)
  if (any(e >= 0.0011)) api_over_rows <- c(api_over_rows, sprintf("%d ab %d p %d %s %s ft",
    d$game_pk[e >= 0.0011], d$at_bat_number[e >= 0.0011], d$pitch_number[e >= 0.0011],
    d$description[e >= 0.0011], fmt(e[e >= 0.0011], 9)))
  # direct integration from the API's own release-plane state (x0, y0, z0),
  # which shares nothing with reproject's difference form
  for (nm in c("front", "mid")) {
    y <- if (nm == "front") Y_FRONT_FT else Y_MID_FT
    tt <- (-d$vy0 - sqrt(d$vy0^2 - 2 * d$ay * (d$y0 - y))) / d$ay
    xx <- d$x0 + d$vx0 * tt + 0.5 * d$ax * tt^2
    zz <- d$z0 + d$vz0 * tt + 0.5 * d$az * tt^2
    if (nm == "mid") direct_mid <- max(direct_mid, max(abs(xx - d$plate_x), abs(zz - d$plate_z)))
    else direct_front_api <- max(direct_front_api, max(abs(xx - d$p_x), abs(zz - d$p_z)))
  }
}
check("2026 CSV mid -> front matches API pX/pZ, called", api_called_max < 0.0011,
      sprintf("max %s ft < 0.0011 over %d called pitches (called_strike, ball, blocked_ball), %d days",
              fmt(api_called_max), api_called_n, length(DAYS_2026)))
record("2026 the same over every pitch",
       sprintf("max %s ft over %d pitches; %d at or above 0.0011 ft: %s", fmt(api_all_max),
               api_n, api_over, paste(api_over_rows, collapse = "; ")))
check("2026 CSV reproduces at y = 8.5/12 (direct integration)", direct_mid < 5e-7,
      sprintf("max abs err %s ft, prints as 0.000000, %d pitches", fmt(direct_mid), api_n))
record("2026 API pX/pZ at y = 17/12 (direct integration)",
       sprintf("max abs err %s ft: the API's own pX/pZ do not follow exactly from its x0/y0/z0 at this plane, and this residual is what the 0.0011 ft bar allows for",
               fmt(direct_front_api)))

# 2025. The clause needs the Stats API's own release-plane state (x0, y0, z0),
# which the CSV does not carry. data/interim/feed_pitch holds season=2026 only
# (DEV-25, DEV-27), and one MLB 2025 game is on disk as a raw feed, 776311 on
# 2025-09-15. The feed is joined to the CSV on the six kinematic columns, which
# the SOP measured equal between the two sources, so the join needs neither
# at_bat_number nor pitch_number and cannot fall into the join-key trap.
FEED_2025_DAY <- "2025-09-15"; FEED_2025_GAME <- 776311L
FEED_2025 <- sprintf("%s/data/raw/statsapi/feed/sport=1/season=2025/date=%s/gamepk=%d.json.zst",
                     ROOT, FEED_2025_DAY, FEED_2025_GAME)
read_feed <- function(path) {
  f <- arrow::ReadableFile$create(path)
  s <- arrow::CompressedInputStream$create(f, codec = arrow::Codec$create("zstd"))
  chunks <- list()
  repeat {
    b <- s$Read(1048576L)
    if (b$size == 0) break
    chunks[[length(chunks) + 1L]] <- as.raw(b)
  }
  s$close(); f$close()
  jsonlite::fromJSON(rawToChar(do.call(c, chunks)), simplifyVector = FALSE)
}
if (!file.exists(FEED_2025) || !file.exists(SC(2025, FEED_2025_DAY))) {
  defer("2025 CSV reproduces at y = 17/12",
        sprintf("the Stats API side for MLB 2025 is not on this machine: %s is absent, and data/interim/feed_pitch holds season=2026 only (DEV-25, DEV-27)",
                sub(paste0(ROOT, "/"), "", FEED_2025, fixed = TRUE)))
} else {
  num <- function(v) if (is.null(v)) NA_real_ else as.numeric(v)
  rows <- list()
  for (p in read_feed(FEED_2025)$liveData$plays$allPlays) {
    for (e in p$playEvents) {
      if (!isTRUE(e$isPitch)) next
      cc <- e$pitchData$coordinates
      rows[[length(rows) + 1L]] <- c(
        x0 = num(cc$x0), y0 = num(cc$y0), z0 = num(cc$z0),
        vx0 = num(cc$vX0), vy0 = num(cc$vY0), vz0 = num(cc$vZ0),
        ax = num(cc$aX), ay = num(cc$aY), az = num(cc$aZ))
    }
  }
  api25 <- as.data.frame(do.call(rbind, rows))
  api25 <- api25[stats::complete.cases(api25), ]
  csv25 <- q(sprintf("select plate_x, plate_z, vx0, vy0, vz0, ax, ay, az
                      from read_parquet('%s')
                      where game_pk = %d and plate_x is not null and vy0 is not null
                        and ay is not null", SC(2025, FEED_2025_DAY), FEED_2025_GAME))
  kin <- c("vx0", "vy0", "vz0", "ax", "ay", "az")
  key <- function(df) do.call(paste, c(lapply(df[kin], function(v) sprintf("%.6f", v)), sep = "|"))
  api25$k <- key(api25); csv25$k <- key(csv25)
  m25 <- merge(csv25, api25, by = "k", suffixes = c("", ".api"))
  kin_diff <- max(abs(as.matrix(m25[kin]) - as.matrix(m25[paste0(kin, ".api")])))
  one_to_one <- !anyDuplicated(api25$k) && !anyDuplicated(csv25$k)
  direct25 <- function(y) {
    tt <- (-m25$vy0 - sqrt(m25$vy0^2 - 2 * m25$ay * (m25$y0 - y))) / m25$ay
    max(abs(m25$x0 + m25$vx0 * tt + 0.5 * m25$ax * tt^2 - m25$plate_x),
        abs(m25$z0 + m25$vz0 * tt + 0.5 * m25$az * tt^2 - m25$plate_z))
  }
  e25_front <- direct25(Y_FRONT_FT); e25_mid <- direct25(Y_MID_FT)
  check("2025 CSV reproduces at y = 17/12 (direct integration)",
        one_to_one && nrow(m25) > 0 && kin_diff == 0 && e25_front < 5e-7,
        sprintf("max abs err %s ft, prints as %s, %d pitches of game %d on %s",
                fmt(e25_front), fmt(e25_front, 6), nrow(m25), FEED_2025_GAME, FEED_2025_DAY))
  record("2025 the join and the other plane",
         sprintf("%d of %d CSV pitches joined 1:1 on the six kinematic columns, max |delta| %s between the two sources; the same integration to y = 8.5/12 misses by %s ft, so the clause identifies the plane",
                 nrow(m25), nrow(csv25), fmt(kin_diff, 6), fmt(e25_mid, 4)))
}
defer("AAA 2024 CSV reproduces at y = 8.5/12",
      "there is no AAA pitch-level data on this machine: data/interim/statcast_pitch holds level=mlb only, and the AAA pull is a later step")

# What the CSV alone can prove for 2022-2025: an independent integrator, run
# from the release-plane state recovered at y = 50 ft, agrees with reproject's
# difference form. This checks the algebra, not which plane the CSV publishes.
for (season in names(DAYS_PRIOR)) {
  d <- q(sprintf("select plate_x, plate_z, vx0, vy0, vz0, ax, ay, az
                  from read_parquet('%s')
                  where plate_x is not null and vy0 is not null and ay is not null",
                 SC(season, DAYS_PRIOR[[season]])))
  ta <- t_at_y(Y_FRONT_FT, d$vy0, d$ay)
  x0 <- d$plate_x - d$vx0 * ta - 0.5 * d$ax * ta^2
  z0 <- d$plate_z - d$vz0 * ta - 0.5 * d$az * ta^2
  tb <- t_at_y(Y_MID_FT, d$vy0, d$ay)
  xi <- x0 + d$vx0 * tb + 0.5 * d$ax * tb^2
  zi <- z0 + d$vz0 * tb + 0.5 * d$az * tb^2
  r <- reproject(d$plate_x, d$plate_z, d$vx0, d$vy0, d$vz0, d$ax, d$ay, d$az,
                 Y_FRONT_FT, Y_MID_FT)
  e <- max(abs(xi - r$x), abs(zi - r$z))
  check(sprintf("%s integrator agrees with reproject", season), e < 1e-12,
        sprintf("max |delta| %.3e ft < 1e-12, n = %d", e, nrow(d)))
}

# mean dz on a 2022-2025 day, one day per season.
for (i in seq_along(DAYS_PRIOR)) {
  season <- names(DAYS_PRIOR)[i]
  mdz <- dz_means[length(DAYS_2026) + i]
  check(sprintf("%s mean dz in [-1.10, -0.90] in", season), mdz >= -1.10 && mdz <= -0.90,
        sprintf("%s in on %s", fmt(mdz, 4), DAYS_PRIOR[[season]]))
}

## ===========================================================================
## 4. UT-13, the ABS height fractions
## ===========================================================================

h26 <- q(sprintf("select sz_top, sz_bot from read_parquet('%s') where sz_top is not null",
                 SC(2026, DAYS_2026[3])))
dh <- abs(h26$sz_top * 12 / ABS_TOP_FRAC - h26$sz_bot * 12 / ABS_BOT_FRAC)
check("UT-13 sz_top*12/0.535 == sz_bot*12/0.27", max(dh) < 1e-6,
      sprintf("max %s in < 1e-6, n = %d on %s", fmt(max(dh), 12), nrow(h26), DAYS_2026[3]))
h25 <- q(sprintf("select sz_top, sz_bot from read_parquet('%s') where sz_top is not null",
                 SC(2025, DAYS_PRIOR[["2025"]])))
dh25 <- abs(h25$sz_top * 12 / ABS_TOP_FRAC - h25$sz_bot * 12 / ABS_BOT_FRAC)
record("UT-13 the pre-2026 contrast",
       sprintf("2025 max %s in, mean %s in: the published zone is operator-set before ABS, so the clause is a 2026 assertion and is not vacuous",
               fmt(max(dh25), 4), fmt(mean(dh25), 4)))
check("abs_top_ft and abs_bot_ft invert the fractions",
      max(abs(abs_top_ft(h26$sz_top * 12 / ABS_TOP_FRAC) - h26$sz_top)) < 1e-12 &&
        max(abs(abs_bot_ft(h26$sz_top * 12 / ABS_TOP_FRAC) - h26$sz_bot)) < 1e-6,
      "0.535*H/12 and 0.27*H/12 return the published sz_top and sz_bot")

## ===========================================================================
## 5. signed_edge_in against four hand-computed points (D-14)
## ===========================================================================
#
# Plate half-width 8.5/12 ft = 8.5 in. Take top = 3.5 ft = 42 in and
# bot = 1.5 ft = 18 in.
#   A  on the right-hand edge, mid-height: |x| - hw = 0, inside vertically, so
#      the signed distance is 0 exactly.
#   B  the centre of the zone, x = 0, z = 2.5 ft: dx = -8.5 in, dz = -12 in,
#      the larger (least negative) is -8.5 in.
#   C  a corner, 3 in outside in x and 4 in outside in z: both positive, so
#      Euclidean, sqrt(3^2 + 4^2) = 5 in exactly.
#   D  4 in below the bottom edge, inside in x: dz = 4 in, dx < 0, so 4 in.
top <- 3.5; bot <- 1.5; hw <- PLATE_HALF_W_FT
pts <- data.frame(
  label = c("A on the side edge", "B the centre", "C a corner", "D below the bottom"),
  x = c(hw, 0, hw + 3/12, 2/12),
  z = c(2.5, 2.5, top + 4/12, bot - 4/12),
  want = c(0, -8.5, 5, 4))
got <- signed_edge_in(pts$x, pts$z, top, bot)
for (i in seq_len(nrow(pts))) {
  check(sprintf("D-14 signed_edge_in, %s", pts$label[i]), abs(got[i] - pts$want[i]) < 1e-12,
        sprintf("%s in, hand-computed %s in", fmt(got[i], 10), fmt(pts$want[i], 1)))
}
check("D-14 the zone-truth predicate",
      signed_edge_in(hw + 1.44/12, 2.5, top, bot) - BALL_R_IN < 0 &&
        !(signed_edge_in(hw + 1.46/12, 2.5, top, bot) - BALL_R_IN < 0),
      "edge - 1.45 in < 0 flips between 1.44 in and 1.46 in outside the side edge")
check("nearest_edge names the edge that is nearest",
      identical(nearest_edge(c(hw + 1/12, 0, 0), c(2.5, top + 1/12, bot - 1/12),
                             top, bot), c("side", "top", "bot")),
      "side, top, bot on three points built one inch outside each edge")
check("z_norm rescales by height",
      abs(z_norm(3.0, 72) - 0.5) < 1e-12,
      "3.0 ft over a 72 in batter is 0.5")

## ===========================================================================
## 6. The golden file, 500 pitches to 1e-9
## ===========================================================================

g <- read.csv(file.path(ROOT, "tests", "golden", "reproject_golden.csv"),
              stringsAsFactors = FALSE)
check("golden file is 500 pitches", nrow(g) == 500L,
      sprintf("%d rows, %d columns", nrow(g), ncol(g)))
gm <- reproject(g$plate_x, g$plate_z, g$vx0, g$vy0, g$vz0, g$ax, g$ay, g$az,
                Y_FRONT_FT, Y_MID_FT)
gb <- reproject(gm$x, gm$z, g$vx0, g$vy0, g$vz0, g$ax, g$ay, g$az, Y_MID_FT, Y_FRONT_FT)
gold <- list(
  t_front      = t_at_y(Y_FRONT_FT, g$vy0, g$ay),
  t_mid        = t_at_y(Y_MID_FT, g$vy0, g$ay),
  x_mid        = gm$x, z_mid = gm$z,
  x_back_front = gb$x, z_back_front = gb$z,
  abs_top_ft   = abs_top_ft(g$h_in_from_sz_top),
  abs_bot_ft   = abs_bot_ft(g$h_in_from_sz_top),
  edge_in_front = signed_edge_in(g$plate_x, g$plate_z, g$sz_top, g$sz_bot),
  edge_in_mid   = signed_edge_in(gm$x, gm$z, g$sz_top, g$sz_bot),
  z_norm_mid    = z_norm(gm$z, g$h_in_from_sz_top))
worst <- 0; worst_col <- ""
for (nm in names(gold)) {
  e <- max(abs(gold[[nm]] - g[[nm]]))
  if (e > worst) { worst <- e; worst_col <- nm }
}
check("golden file, 11 numeric columns to 1e-9", worst < 1e-9,
      sprintf("max |delta| %.3e, worst column %s, %d rows", worst, worst_col, nrow(g)))
check("golden file, nearest_edge to the letter",
      identical(nearest_edge(gm$x, gm$z, g$sz_top, g$sz_bot), g$nearest_edge_mid),
      sprintf("%d of %d rows agree", sum(nearest_edge(gm$x, gm$z, g$sz_top, g$sz_bot) ==
                                           g$nearest_edge_mid), nrow(g)))

## ===========================================================================
## 7. The Python twin on 100,000 rows
## ===========================================================================

n_cross <- 100000L
x <- q(sprintf("select plate_x, plate_z, vx0, vy0, vz0, ax, ay, az
                from read_parquet('%s/data/interim/statcast_pitch/level=mlb/season=2024/date=2024-06-*/part-000.parquet')
                where plate_x is not null and plate_z is not null and vy0 is not null
                  and ay is not null
                order by game_pk, at_bat_number, pitch_number limit %d", ROOT, n_cross))
check("cross-check sample is 100,000 rows", nrow(x) == n_cross,
      sprintf("%d rows from MLB 2024-06", nrow(x)))
tmp <- file.path(tempdir(), "w33_cross")
dir.create(tmp, showWarnings = FALSE)
in_pq <- file.path(tmp, "in.parquet"); out_pq <- file.path(tmp, "out.parquet")
arrow::write_parquet(x, in_pq)
code <- sprintf(paste0(
  "import pyarrow.parquet as pq, pyarrow as pa;",
  "from absump.geometry import reproject, Y_FRONT_FT, Y_MID_FT;",
  "t = pq.read_table('%s');",
  "d = {k: t.column(k).to_numpy() for k in t.column_names};",
  "r = reproject(d['plate_x'], d['plate_z'], d['vx0'], d['vy0'], d['vz0'], d['ax'], d['ay'], d['az'], Y_FRONT_FT, Y_MID_FT);",
  "pq.write_table(pa.table({'x': r['x'], 'z': r['z']}), '%s')"), in_pq, out_pq)
cross <- py_run(code)
if (cross$status != 0L) {
  check("Python twin agrees on 100,000 rows", FALSE,
        sprintf("the twin exited %d: %s", cross$status, substr(cross$text, 1, 200)))
} else {
  pyout <- as.data.frame(arrow::read_parquet(out_pq))
  rr <- reproject(x$plate_x, x$plate_z, x$vx0, x$vy0, x$vz0, x$ax, x$ay, x$az,
                  Y_FRONT_FT, Y_MID_FT)
  e <- max(abs(rr$x - pyout$x), abs(rr$z - pyout$z))
  check("Python twin agrees on 100,000 rows", e < 1e-12,
        sprintf("max |delta| %.3e ft < 1e-12 over %d rows", e, nrow(x)))
}
unlink(tmp, recursive = TRUE)

## --- summary -----------------------------------------------------------------

elapsed <- as.numeric(difftime(Sys.time(), t_start, units = "secs"))
dbDisconnect(con, shutdown = TRUE)
cat(sprintf("\n%d PASS, %d FAIL, %d DEFER, %.1f s\n",
            n_pass, length(failures), length(defers), elapsed))
if (length(defers)) {
  cat("deferred, each with its reason:\n")
  for (d in defers) cat(" -", d, "\n")
}
if (length(failures)) {
  cat("failed:\n")
  for (f in failures) cat(" -", f, "\n")
  quit(status = 1L)
}
quit(status = 0L)
