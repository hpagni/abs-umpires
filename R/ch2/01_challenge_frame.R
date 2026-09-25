#!/usr/bin/env Rscript
# R/ch2/01_challenge_frame.R - SOP step W4.5, the challenge frame.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch2/01_challenge_frame.R            build data/interim/ch2/challenges.parquet
#   Rscript R/ch2/01_challenge_frame.R --check    rebuild in memory, compare to the file, write nothing
#
# WHAT IT WRITES. One row per ABS challenge from the Savant per-team drawer (W4.2):
# MLB 2026 open rows and AAA 2025. Key play_id. The derived columns SOP W4.5 names:
#
#   role              batter, catcher or pitcher: challenging_player_id matched against
#                     player_at_bat, fielder_2 and pitcher. team_summary_mode is never
#                     read (contracts/savant_drawer.yml, forbidden_keys).
#   opponent_id       fielder_2 when role is batter, else player_at_bat (SOP W4.10).
#   m                 the signed evidence in inches:
#                       m = +edge_dist_calc  when original_isStrike_ump == 1
#                       m = -edge_dist_calc  when original_isStrike_ump == 0
#   overturned        is_challengeABS_overturned, 0 or 1.
#   count_class       2-strike, 3-ball or other, from the count before the pitch. The W4
#                     draft lists the three values and no rule for 3-2; this script
#                     applies them in the listed order, so 3-2 is 2-strike. balls and
#                     strikes are kept as columns, so a reader can re-cut it.
#   edge_side         side, top, bottom or corner: which term won the max or the hypot
#                     in the SOP section 2.5 edge rule, on the drawer's own plateX,
#                     plateZ, strikeZoneTop, strikeZoneBottom and widthinches.
#   runs_at_stake_z   sz_challenge_runs standardised within level and season (W4
#                     draft). Measured here: it is a realised value, not a stake. It
#                     is sz_challenge_overturned_runs on an overturn and minus
#                     sz_challenge_lost_runs otherwise, so its sign is the outcome.
#   challenger_season_index
#                     1, 2, ... n over one challenger's challenges in one level-season,
#                     in game order. MLB 2026: game_date, game_pk, then at_bat_number
#                     and pitch_number from the W3.6 bridge. AAA 2025 has no pitch key,
#                     so inside a game the order is event_inning, outs, balls plus
#                     strikes, then play_id. index_order_source names the rule per row.
#
# THE DESIGN FACT (SOP W4.5). overturned == 1{m > 0} on every row. M1 must not
# condition on m or on edge_dist_calc: a distance-adjusted accuracy model fits
# perfectly and every random effect collapses to zero. The file carries the list
# of columns M1 may not read in its metadata key w45_m1_excluded, so the W4.10
# formula test can read it from the artifact instead of restating it. The list
# holds m, every location measure and every column whose value follows from the
# outcome.
#
# THE SEAL. The drawer has no date parameter. MLB 2026 rows dated on or after
# config/seal.yml's seal_start_date are dropped as each file is parsed, before
# any other column is read. The boundary is read from that file and is not
# written here. AAA 2025 is outside the seal's scope (MLB 2026 only). The W3.6
# pitch key is read from data/interim/ch1/original_call.parquet, open rows only.
#
# THE COORDINATES. The drawer spells the plate pair twice, plateX/plateZ and
# plate_X/plate_Z. They agree on every row but 4: the two AAA 2025 plays that
# contracts/savant_drawer.yml names as known_exceptions, each carried in the for
# and the against drawer. On those two plays edge_dist_calc and the overturn
# follow plate_X/plate_Z exactly, and plateX/plateZ miss by the residuals the
# contract records. So the frame takes plate_X/plate_Z as plate_x/plate_z, and
# the check below shows the contract's two exceptions are this spelling split.
#
# CHECKS. The four W4.2 facts again, on the frame: edge_dist_calc re-derived by
# R/lib/zone.R to 1e-6 in on every row;
# overturned == 1{m > 0}; role resolved on every row, exactly one match; role is
# batter if and only if the original call was a strike. Plus DT-25's totals on
# the MLB open set, the for and against copies of each play agreeing, the index
# having no gaps, and no nulls in any derived column.
#
# Exit 0 when every check passes, 1 when any fails, 2 on a usage error.

options(warn = 1, digits = 12)
t_start <- Sys.time()

args_all <- commandArgs(trailingOnly = FALSE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1 || (length(args) == 1 && !identical(args, "--check"))) {
  cat("usage: Rscript R/ch2/01_challenge_frame.R [--check]\n", file = stderr())
  quit(status = 2)
}
CHECK_ONLY <- identical(args, "--check")

file_arg <- grep("^--file=", args_all, value = TRUE)
ROOT <- if (length(file_arg) == 1) {
  normalizePath(file.path(dirname(sub("^--file=", "", file_arg)), "..", ".."))
} else {
  normalizePath(getwd())
}
setwd(ROOT)

suppressPackageStartupMessages({
  library(arrow)
  library(jsonlite)
})
source(file.path(ROOT, "R", "lib", "zone.R"))

## --- check helpers -----------------------------------------------------------

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
comma <- function(x) formatC(x, format = "d", big.mark = ",")
finish <- function() {
  cat(sprintf("W4.5 %s: %d PASS, %d FAIL, %.1f s\n",
              if (CHECK_ONLY) "check" else "build", n_pass, length(failures),
              as.numeric(difftime(Sys.time(), t_start, units = "secs"))))
  if (length(failures) > 0) {
    cat("FAILED CLAUSES:\n", paste0("  ", failures, "\n"), sep = "")
    quit(status = 1)
  }
  quit(status = 0)
}

## --- paths, the seal boundary, the contract -----------------------------------

DRAWER_DIR <- file.path(ROOT, "data", "raw", "savant", "abs_drawer")
MANIFEST   <- file.path(ROOT, "data", "raw", "_manifest.csv")
ORIG_CALL  <- file.path(ROOT, "data", "interim", "ch1", "original_call.parquet")
CONTRACT   <- file.path(ROOT, "contracts", "savant_drawer.yml")
OUT_DIR    <- file.path(ROOT, "data", "interim", "ch2")
OUT_FILE   <- file.path(OUT_DIR, "challenges.parquet")
# The licence line and the endpoint are read from the files that own them,
# DATA_LICENSE.md and the drawer contract, so no address is written here.
LICENCE <- grep("^Copyright 2026 MLB Advanced Media", readLines(file.path(ROOT, "DATA_LICENSE.md"),
                                                                warn = FALSE), value = TRUE)
stopifnot(length(LICENCE) == 1)

seal_yml <- readLines(file.path(ROOT, "config", "seal.yml"), warn = FALSE)
seal_start <- as.Date(gsub('[" ]', "", sub("^seal_start_date:", "",
  grep("^seal_start_date:", seal_yml, value = TRUE)[1])))
stopifnot(!is.na(seal_start))

contract <- yaml::read_yaml(CONTRACT)
DRAWER_ENDPOINT <- contract$endpoint$url_template
stopifnot(is.character(DRAWER_ENDPOINT), length(DRAWER_ENDPOINT) == 1)
EDGE_TOL <- as.numeric(contract$facts$edge$tolerance_in)
KNOWN_EXC <- unlist(contract$facts$edge$known_exceptions)
DT25 <- contract$dt25
stopifnot(length(EDGE_TOL) == 1, EDGE_TOL > 0, length(KNOWN_EXC) >= 1)

LEVELS <- list(
  list(level = "mlb", season = 2026L, pattern = "^mlb_2026_[0-9]+\\.json$", sealed_scope = TRUE),
  list(level = "aaa", season = 2025L, pattern = "^aaa_2025_[0-9]+\\.json$", sealed_scope = FALSE)
)

## --- 1. the drawer, both copies of every play ---------------------------------

num <- function(v) if (is.null(v)) NA_real_ else as.numeric(v)
int <- function(v) if (is.null(v)) NA_integer_ else as.integer(v)

n_dropped_at_seal <- 0L
all_files <- character(0)
raw <- do.call(rbind, lapply(LEVELS, function(L) {
  files <- sort(list.files(DRAWER_DIR, pattern = L$pattern, full.names = TRUE))
  all_files <<- c(all_files, files)
  check(sprintf("%s %d drawer files", toupper(L$level), L$season), length(files) == 30,
        sprintf("%d team drawers, one per club, 30 expected", length(files)))
  do.call(rbind, lapply(files, function(f) {
    d <- jsonlite::fromJSON(f, simplifyVector = TRUE)$data
    played <- as.Date(substr(d$game_date, 1, 10))
    stopifnot(!anyNA(played))
    keep <- if (L$sealed_scope) played < seal_start else rep(TRUE, length(played))
    n_dropped_at_seal <<- n_dropped_at_seal + sum(!keep)
    d <- d[keep, , drop = FALSE]
    data.frame(
      file = basename(f),
      level = L$level,
      level_season = L$season,
      play_id = as.character(d$play_id),
      game_pk = int(d$game_pk),
      game_date = as.Date(substr(d$game_date, 1, 10)),
      year = int(d$year),
      against = as.logical(d$against),
      challenger_id = int(d$challenging_player_id),
      batter_id = int(d$player_at_bat),
      pitcher_id = int(d$pitcher),
      catcher_id = int(d$fielder_2),
      bat_team_id = int(d$bat_team_id),
      fld_team_id = int(d$fld_team_id),
      player_team = int(d$player_team),
      bat_side = as.character(d$bat_side),
      inning = int(d$event_inning),
      outs = int(d$outs),
      balls = int(d$pre_ball_count),
      strikes = int(d$pre_strike_count),
      bat_score = int(d$bat_score),
      fld_score = int(d$fld_score),
      original_is_strike = int(d$original_isStrike_ump),
      overturned = int(d$is_challengeABS_overturned),
      reasonable_attempt = int(d$is_challengeABS_reasonable_attempt),
      edge_dist_calc = num(d$edge_dist_calc),
      plate_x = num(d$plate_X),
      plate_z = num(d$plate_Z),
      plate_x_alt = num(d$plateX),
      plate_z_alt = num(d$plateZ),
      sz_top = num(d$strikeZoneTop),
      sz_bot = num(d$strikeZoneBottom),
      width_in = num(d$widthinches),
      sz_challenge_prob = num(d$sz_challenge_prob),
      sz_challenge_runs = num(d$sz_challenge_runs),
      sz_challenge_overturned_runs = num(d$sz_challenge_overturned_runs),
      sz_challenge_lost_runs = num(d$sz_challenge_lost_runs),
      stringsAsFactors = FALSE)
  }))
}))

record("drawer rows at the seal", sprintf(
  "%s rows read (both copies of each play); %s MLB 2026 rows on or after the boundary dropped at parse",
  comma(nrow(raw)), comma(n_dropped_at_seal)))
check("rows are in their level-season",
      all(raw$year == raw$level_season) &&
        all(raw$game_date[raw$level == "mlb"] < seal_start) &&
        all(format(raw$game_date, "%Y") == as.character(raw$level_season)),
      sprintf("MLB rows all 2026 and before seal_start; AAA rows all 2025; %s rows", comma(nrow(raw))))
split_rows <- raw$plate_x != raw$plate_x_alt | raw$plate_z != raw$plate_z_alt
check("plate_X and plateX split on the named plays only",
      !anyNA(split_rows) && setequal(unique(raw$play_id[split_rows]), names(KNOWN_EXC)),
      sprintf("the two spellings differ on %d rows, %d plays, all among the %d the contract names; equal on the other %s rows",
              sum(split_rows), length(unique(raw$play_id[split_rows])), length(KNOWN_EXC),
              comma(sum(!split_rows))))

own <- raw[!raw$against, ]
opp <- raw[raw$against, ]
pair_cols <- c("level", "play_id", "game_pk", "game_date", "challenger_id", "batter_id",
               "pitcher_id", "catcher_id", "bat_team_id", "fld_team_id", "inning", "outs",
               "balls", "strikes", "original_is_strike", "overturned", "edge_dist_calc",
               "plate_x", "plate_z", "sz_top", "sz_bot", "width_in", "sz_challenge_runs")
own_k <- own[order(own$level, own$play_id), pair_cols]
opp_k <- opp[order(opp$level, opp$play_id), pair_cols]
rownames(own_k) <- NULL; rownames(opp_k) <- NULL
pairs_ok <- !anyDuplicated(own[, c("level", "play_id")]) &&
  !anyDuplicated(opp[, c("level", "play_id")]) &&
  nrow(own_k) == nrow(opp_k) && isTRUE(all.equal(own_k, opp_k, tolerance = 0))
check("each play once as for and once as against",
      pairs_ok,
      sprintf("%s plays for, %s against; the two copies agree on %d fields",
              comma(nrow(own)), comma(nrow(opp)), length(pair_cols) - 1L))

## --- 2. derive ----------------------------------------------------------------

f <- own
rownames(f) <- NULL

hits <- (f$challenger_id == f$batter_id) + (f$challenger_id == f$catcher_id) +
  (f$challenger_id == f$pitcher_id)
f$role <- ifelse(f$challenger_id == f$batter_id, "batter",
          ifelse(f$challenger_id == f$catcher_id, "catcher",
          ifelse(f$challenger_id == f$pitcher_id, "pitcher", NA_character_)))
check("role resolves, one match per row",
      all(hits == 1) && !anyNA(f$role),
      sprintf("%s of %s rows match exactly one of player_at_bat, fielder_2, pitcher; %d unresolved, %d ambiguous",
              comma(sum(hits == 1)), comma(nrow(f)), sum(hits == 0), sum(hits > 1)))

f$opponent_id <- ifelse(f$role == "batter", f$catcher_id, f$batter_id)
f$challenger_team_id <- ifelse(f$role == "batter", f$bat_team_id, f$fld_team_id)
check("challenger team is the drawer's own team",
      identical(f$challenger_team_id, f$player_team),
      sprintf("bat_team_id for a batter, fld_team_id otherwise, equals player_team on %s of %s rows",
              comma(sum(f$challenger_team_id == f$player_team)), comma(nrow(f))))

is_bat <- f$role == "batter"
is_k <- f$original_is_strike == 1L
check("role batter iff called strike",
      all(is_bat == is_k),
      sprintf("%s batter rows, %s called strikes, %d rows disagree",
              comma(sum(is_bat)), comma(sum(is_k)), sum(is_bat != is_k)))

f$m <- ifelse(f$original_is_strike == 1L, f$edge_dist_calc, -f$edge_dist_calc)
check("design fact: overturned == 1{m > 0}",
      all(f$overturned == as.integer(f$m > 0)) && !anyNA(f$m),
      sprintf("%s of %s rows; %d rows with m == 0; min m among overturned %.6f in, max m among upheld %.6f in",
              comma(sum(f$overturned == as.integer(f$m > 0))), comma(nrow(f)), sum(f$m == 0),
              min(f$m[f$overturned == 1L]), max(f$m[f$overturned == 0L])))

hw_ft <- f$width_in / 24
f$edge_dist_rederived <- signed_edge_in(f$plate_x, f$plate_z, f$sz_top, f$sz_bot, hw_ft) - BALL_R_IN
resid <- f$edge_dist_rederived - f$edge_dist_calc
check("edge_dist_calc re-derived by zone.R",
      all(abs(resid) < EDGE_TOL),
      sprintf("max |diff| %.3e in on %s of %s rows from plate_X/plate_Z, bar %g in",
              max(abs(resid)), comma(sum(abs(resid) < EDGE_TOL)), comma(nrow(f)), EDGE_TOL))
named <- f$play_id %in% names(KNOWN_EXC)
alt_resid <- abs(signed_edge_in(f$plate_x_alt[named], f$plate_z_alt[named], f$sz_top[named],
                                f$sz_bot[named], hw_ft[named]) - BALL_R_IN - f$edge_dist_calc[named])
exc_want <- as.numeric(KNOWN_EXC[f$play_id[named]])
check("contract exceptions are the plateX spelling",
      sum(named) == length(KNOWN_EXC) && all(round(alt_resid, 6) == round(exc_want, 6)),
      sprintf("on the %d named plays plateX/plateZ miss edge_dist_calc by %s in; the contract records %s",
              sum(named), paste(sprintf("%.6f", alt_resid), collapse = " and "),
              paste(sprintf("%.6f", exc_want), collapse = " and ")))

dx_in <- (abs(f$plate_x) - hw_ft) * 12
dz_in <- pmax(f$sz_bot - f$plate_z, f$plate_z - f$sz_top) * 12
corner <- dx_in > 0 & dz_in > 0
ne <- nearest_edge(f$plate_x, f$plate_z, f$sz_top, f$sz_bot, hw_ft)
f$edge_side <- factor(ifelse(corner, "corner", c(side = "side", top = "top", bot = "bottom")[ne]),
                      levels = c("side", "top", "bottom", "corner"))

f$count_class <- factor(ifelse(f$strikes == 2L, "2-strike",
                         ifelse(f$balls == 3L, "3-ball", "other")),
                        levels = c("other", "2-strike", "3-ball"))
record("count_class on 3-2", sprintf("%s rows at 3-2 are 2-strike by the listed order (MLB %s, AAA %s)",
       comma(sum(f$balls == 3L & f$strikes == 2L)),
       comma(sum(f$balls == 3L & f$strikes == 2L & f$level == "mlb")),
       comma(sum(f$balls == 3L & f$strikes == 2L & f$level == "aaa"))))

grp <- paste(f$level, f$level_season)
mu <- ave(f$sz_challenge_runs, grp, FUN = mean)
sdv <- ave(f$sz_challenge_runs, grp, FUN = stats::sd)
f$runs_at_stake_z <- (f$sz_challenge_runs - mu) / sdv
z_mean <- tapply(f$runs_at_stake_z, grp, mean)
z_sd <- tapply(f$runs_at_stake_z, grp, stats::sd)
check("runs_at_stake_z standardised per level-season",
      all(abs(z_mean) < 1e-12) && all(abs(z_sd - 1) < 1e-12),
      paste(sprintf("%s: raw mean %.6f, sd %.6f", names(z_mean),
                    tapply(f$sz_challenge_runs, grp, mean), tapply(f$sz_challenge_runs, grp, stats::sd)),
            collapse = "; "))
realised <- all((f$sz_challenge_runs > 0) == (f$overturned == 1L)) &&
  all(f$sz_challenge_runs[f$overturned == 1L] == f$sz_challenge_overturned_runs[f$overturned == 1L]) &&
  all(f$sz_challenge_runs[f$overturned == 0L] == -f$sz_challenge_lost_runs[f$overturned == 0L])
check("runs_at_stake_z is realised, listed as excluded",
      realised,
      sprintf("sz_challenge_runs > 0 iff overturned on %s of %s rows; upheld rows take %s distinct value(s): %s",
              comma(sum((f$sz_challenge_runs > 0) == (f$overturned == 1L))), comma(nrow(f)),
              length(unique(f$sz_challenge_runs[f$overturned == 0L])),
              paste(sprintf("%.2f", sort(unique(f$sz_challenge_runs[f$overturned == 0L]))), collapse = ", ")))

## --- 3. DT-25 on the MLB open set --------------------------------------------

mlb <- f$level == "mlb"
n_bat <- sum(mlb & f$role == "batter")
n_fld <- sum(mlb & f$role != "batter")
check("DT-25 totals, MLB 2026 open set",
      sum(mlb) == DT25$expected_total && n_bat == DT25$expected_batter_side &&
        n_fld == DT25$expected_fielding_side,
      sprintf("%s challenges = %s batting + %s fielding; contract %s = %s + %s",
              comma(sum(mlb)), comma(n_bat), comma(n_fld), comma(DT25$expected_total),
              comma(DT25$expected_batter_side), comma(DT25$expected_fielding_side)))
record("roles", paste(sprintf("%s %s", names(table(paste(f$level, f$role))),
                              comma(as.integer(table(paste(f$level, f$role))))), collapse = "; "))

## --- 4. the W3.6 pitch key, and the chronological index -----------------------

oc <- as.data.frame(arrow::read_parquet(ORIG_CALL, col_select = c("drawer_play_id", "game_pk",
  "at_bat_number", "pitch_number", "analysis_set", "challenged")))
oc <- oc[!is.na(oc$drawer_play_id) & oc$analysis_set == "open" & oc$challenged, ]
mi <- match(f$play_id, oc$drawer_play_id)
check("MLB plays carry the W3.6 pitch key",
      !anyDuplicated(oc$drawer_play_id) && all(!is.na(mi[mlb])) && all(is.na(mi[!mlb])) &&
        all(oc$game_pk[mi[mlb]] == f$game_pk[mlb]),
      sprintf("%s of %s MLB plays map to one open challenged pitch on the same game_pk; %s AAA plays have none",
              comma(sum(!is.na(mi[mlb]))), comma(sum(mlb)), comma(sum(!mlb))))
f$at_bat_number <- oc$at_bat_number[mi]
f$pitch_number <- oc$pitch_number[mi]
f$index_order_source <- ifelse(mlb, "at_bat_pitch", "inning_outs_count")

f$count_total <- f$balls + f$strikes
ord <- order(f$level, f$level_season, f$game_date, f$game_pk,
             f$at_bat_number, f$pitch_number,
             f$inning, f$outs, f$count_total, f$play_id, na.last = TRUE)
f <- f[ord, ]
rownames(f) <- NULL
key <- paste(f$level, f$level_season, f$challenger_id)
f$challenger_season_index <- as.integer(ave(seq_len(nrow(f)), key, FUN = seq_along))

n_by <- tapply(f$challenger_season_index, key, max)
gapless <- all(tapply(f$challenger_season_index, key, function(v) identical(v, seq_along(v))))
monotone <- all(tapply(as.numeric(f$game_date), key, function(v) !is.unsorted(v)))
check("index is 1..n per challenger-season, in date order",
      gapless && monotone && all(n_by == as.integer(table(key)[names(n_by)])),
      sprintf("%s challenger-seasons; max index %d; no gaps; game_date non-decreasing in index",
              comma(length(n_by)), max(n_by)))

# The drawer-only rule, measured against the pitch key where both exist.
drawer_rank <- function(d) order(d$game_date, d$game_pk, d$inning, d$outs, d$count_total, d$play_id)
mm <- f[mlb[ord], ]
multi <- split(mm, paste(mm$challenger_id, mm$game_pk))
multi <- multi[vapply(multi, nrow, 1L) > 1L]
misordered <- sum(vapply(multi, function(d) !identical(drawer_rank(d), seq_len(nrow(d))), TRUE))
record("drawer-only order vs pitch order", sprintf(
  "MLB 2026: %d of %s challenger-games with 2 or more challenges would be misordered by inning, outs and count alone; AAA 2025 uses that rule",
  misordered, comma(length(multi))))
dh <- tapply(f$game_pk, paste(f$level, f$challenger_id, f$game_date), function(v) length(unique(v)))
record("same-day games", sprintf("%d challenger-days span 2 games; game_pk orders them", sum(dh > 1)))

## --- 5. the frame -------------------------------------------------------------

out <- data.frame(
  level = f$level,
  season = f$level_season,
  game_date = f$game_date,
  game_pk = f$game_pk,
  play_id = f$play_id,
  at_bat_number = f$at_bat_number,
  pitch_number = f$pitch_number,
  challenger_id = f$challenger_id,
  role = factor(f$role, levels = c("batter", "catcher", "pitcher")),
  challenger_team_id = f$challenger_team_id,
  opponent_id = f$opponent_id,
  batter_id = f$batter_id,
  pitcher_id = f$pitcher_id,
  catcher_id = f$catcher_id,
  bat_team_id = f$bat_team_id,
  fld_team_id = f$fld_team_id,
  bat_side = f$bat_side,
  inning = f$inning,
  outs = f$outs,
  balls = f$balls,
  strikes = f$strikes,
  count_class = f$count_class,
  bat_score = f$bat_score,
  fld_score = f$fld_score,
  original_is_strike = f$original_is_strike,
  overturned = f$overturned,
  m = f$m,
  edge_dist_calc = f$edge_dist_calc,
  edge_dist_rederived = f$edge_dist_rederived,
  edge_side = f$edge_side,
  plate_x = f$plate_x,
  plate_z = f$plate_z,
  sz_top = f$sz_top,
  sz_bot = f$sz_bot,
  width_in = f$width_in,
  reasonable_attempt = f$reasonable_attempt,
  sz_challenge_prob = f$sz_challenge_prob,
  sz_challenge_runs = f$sz_challenge_runs,
  runs_at_stake_z = f$runs_at_stake_z,
  challenger_season_index = f$challenger_season_index,
  index_order_source = f$index_order_source,
  stringsAsFactors = FALSE)

M1_EXCLUDED <- c("m", "edge_dist_calc", "edge_dist_rederived", "edge_side", "plate_x", "plate_z",
                 "sz_top", "sz_bot", "reasonable_attempt", "sz_challenge_prob", "sz_challenge_runs",
                 "runs_at_stake_z", "original_is_strike")
stopifnot(all(M1_EXCLUDED %in% names(out)))

may_be_null <- c("at_bat_number", "pitch_number")
nulls <- vapply(out, function(v) sum(is.na(v)), 0)
check("no nulls outside the AAA pitch key",
      all(nulls[setdiff(names(out), may_be_null)] == 0) &&
        all(nulls[may_be_null] == sum(out$level == "aaa")),
      sprintf("%d columns with 0 nulls; at_bat_number and pitch_number null on the %s AAA rows only",
              ncol(out) - length(may_be_null), comma(sum(out$level == "aaa"))))
check("play_id unique",
      !anyDuplicated(out$play_id),
      sprintf("%s rows, %s distinct play_id", comma(nrow(out)), comma(length(unique(out$play_id)))))

## --- 6. provenance ------------------------------------------------------------

man <- tryCatch(utils::read.csv(MANIFEST, stringsAsFactors = FALSE), error = function(e) NULL)
fetch_window <- function(lvl, yr) {
  if (is.null(man)) return("NA")
  hit <- man$fetched_at_utc[grepl("/leaderboard/services/abs/[0-9]+\\?", man$url) &
                              grepl(sprintf("year=%d&", yr), man$url, fixed = TRUE) &
                              grepl(sprintf("level=%s", lvl), man$url, fixed = TRUE)]
  if (length(hit) == 0) return("NA")
  sprintf("%d manifest rows, %s to %s UTC", length(hit), min(hit), max(hit))
}
pull_mlb <- fetch_window("mlb", 2026L)
pull_aaa <- fetch_window("aaa", 2025L)
record("drawer pull, MLB 2026", pull_mlb)
record("drawer pull, AAA 2025", pull_aaa)
drawer_md5 <- unname(tools::md5sum(all_files))
drawer_digest <- digest::digest(paste(basename(all_files), drawer_md5, collapse = "\n"),
                                algo = "sha256", serialize = FALSE)

meta <- list(
  w45_step = "W4.5 the challenge frame",
  w45_grain = "one row per ABS challenge in the Savant drawer; key play_id; MLB 2026 open rows and AAA 2025",
  w45_m_rule = "m = +edge_dist_calc if original_isStrike_ump == 1, else -edge_dist_calc; overturned == 1{m > 0}",
  w45_m1_excluded = paste(M1_EXCLUDED, collapse = ","),
  w45_m1_excluded_reason = paste("M1 does not condition on m or on edge_dist_calc (SOP W4.5, D-64).",
                                 "The list adds every location measure, Savant's location-based",
                                 "expectation, and sz_challenge_runs and runs_at_stake_z, whose sign",
                                 "is the outcome. original_is_strike is collinear with role."),
  w45_count_class = "2-strike if strikes == 2, else 3-ball if balls == 3, else other; 3-2 is 2-strike",
  w45_edge_side = "corner if both the side and the vertical term are positive, else the larger of side, top, bottom",
  w45_runs_at_stake_z = "sz_challenge_runs standardised within level and season (mean 0, sd 1)",
  w45_index = paste("challenger_season_index: 1..n per challenger, level and season, by game_date,",
                    "game_pk, then at_bat_number and pitch_number (MLB) or inning, outs,",
                    "balls + strikes and play_id (AAA)"),
  w45_sources = paste("Savant ABS drawer", DRAWER_ENDPOINT,
                      "(60 files, data/raw/savant/abs_drawer); W3.6 pitch key from",
                      "data/interim/ch1/original_call.parquet, open rows"),
  w45_drawer_fetched_utc = paste("MLB 2026:", pull_mlb, "| AAA 2025:", pull_aaa),
  w45_drawer_sha256 = drawer_digest,
  w45_seal_start_date = as.character(seal_start),
  w45_licence = LICENCE,
  w45_counts = sprintf("rows %d; mlb %d (batting %d, fielding %d, pitcher %d); aaa %d; overturned %d",
                       nrow(out), sum(out$level == "mlb"), n_bat, n_fld,
                       sum(out$level == "mlb" & out$role == "pitcher"), sum(out$level == "aaa"),
                       sum(out$overturned))
)

build_table <- function(df) {
  tb <- arrow::arrow_table(df)
  for (k in names(meta)) tb$metadata[[k]] <- meta[[k]]
  tb
}

## --- 7. write, or compare -----------------------------------------------------

if (CHECK_ONLY) {
  on_disk <- file.exists(OUT_FILE)
  check("artifact on disk", on_disk, OUT_FILE)
  if (on_disk) {
    old_tb <- arrow::read_parquet(OUT_FILE, as_data_frame = FALSE)
    old <- as.data.frame(old_tb)
    same_shape <- identical(names(old), names(out)) && nrow(old) == nrow(out)
    same_types <- same_shape && identical(vapply(old, function(v) class(v)[1], ""),
                                          vapply(out, function(v) class(v)[1], ""))
    same_rows <- same_types && isTRUE(all.equal(old, out, check.attributes = FALSE, tolerance = 0))
    check("artifact equals a rebuild from sources", same_rows,
          sprintf("%s rows x %d columns on disk; rebuilt %s x %d; names, types and values %s",
                  comma(nrow(old)), ncol(old), comma(nrow(out)), ncol(out),
                  if (same_rows) "identical" else "differ"))
    old_meta <- old_tb$metadata[names(meta)]
    same_meta <- identical(unname(unlist(old_meta)), unname(unlist(meta)))
    check("artifact provenance equals a rebuild", same_meta,
          sprintf("%d w45_* metadata keys", length(meta)))
    old_excl <- strsplit(old_tb$metadata[["w45_m1_excluded"]] %||% "", ",", fixed = TRUE)[[1]]
    check("artifact names the columns M1 may not read",
          all(c("m", "edge_dist_calc") %in% old_excl) && all(old_excl %in% names(old)),
          sprintf("w45_m1_excluded lists %d columns, m and edge_dist_calc among them", length(old_excl)))
    record("artifact md5", unname(tools::md5sum(OUT_FILE)))
  }
} else if (length(failures) > 0) {
  record("write skipped", sprintf("%d check(s) failed; %s left as it was", length(failures), OUT_FILE))
} else {
  dir.create(OUT_DIR, recursive = TRUE, showWarnings = FALSE)
  tmp <- file.path(OUT_DIR, sprintf(".challenges.parquet.tmp-%d", Sys.getpid()))
  arrow::write_parquet(build_table(out), tmp)
  ok <- file.rename(tmp, OUT_FILE)
  if (!ok) unlink(tmp)
  check("artifact written", ok && file.exists(OUT_FILE),
        sprintf("%s, %s rows x %d columns, %s bytes, md5 %s", OUT_FILE, comma(nrow(out)), ncol(out),
                comma(file.size(OUT_FILE)), unname(tools::md5sum(OUT_FILE))))
}

record("null counts", paste(sprintf("%s %s", names(nulls), comma(nulls)), collapse = "; "))
tab <- table(paste(out$level, out$season))
record("rows by level-season", paste(sprintf("%s %s (overturned %s, %.2f%%)", names(tab), comma(as.integer(tab)),
  comma(as.integer(tapply(out$overturned, paste(out$level, out$season), sum))),
  100 * tapply(out$overturned, paste(out$level, out$season), mean)), collapse = "; "))
es <- table(paste(out$level, out$edge_side))
record("edge_side", paste(sprintf("%s %s", names(es), comma(as.integer(es))), collapse = "; "))
cc <- table(paste(out$level, out$count_class))
record("count_class", paste(sprintf("%s %s", names(cc), comma(as.integer(cc))), collapse = "; "))
lv <- vapply(out[out$level == "mlb", c("challenger_id", "opponent_id", "pitcher_id", "challenger_team_id")],
             function(v) length(unique(v)), 0L)
record("MLB 2026 distinct levels", paste(sprintf("%s %d", names(lv), lv), collapse = "; "))

finish()
