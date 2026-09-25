#!/usr/bin/env Rscript
# R/ch1/10_build_analysis_table.R - SOP step W3.7, the analysis table.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/10_build_analysis_table.R           build data/marts/ch1_called.parquet
#   Rscript R/ch1/10_build_analysis_table.R --check   rebuild in memory, compare with the file,
#                                                      write nothing
#
# WHAT IT WRITES. One row per pitch of P0, the sample SOP W3.5 defines once:
# every called pitch (called_strike, ball, blocked_ball) with game_type R in the
# open view, official date up to the last open day, non-null mid-plate
# coordinates, less the pitches thrown by position players, a position player
# being a pitcher who held a position other than P or TWP in the season he threw
# the pitch (pitcher_season_roles() below). P1, the
# ABS-measured-height cohort, is the subset with a non-null H_abs. The key is
# pitch_uid. Rows are sorted by season, game_pk, at_bat_number, pitch_number.
#
# THE COLUMNS. The 19 names SOP W3.7 lists, then identifiers and the arm columns.
#
#   x_mid, z_mid   plate_x_mid and plate_z_mid from the open view, in feet, on the
#                  mid-plate plane y = 8.5/12 ft. W2.14 re-projected 2022-2025 from
#                  the front plane; 2026 is published at the middle. This script
#                  re-projects both ways with R/lib/zone.R and asserts that it
#                  reproduces the warehouse pair. It does not re-derive the pair.
#   H              batter height in inches: roster height plus the one
#                  calibration offset o. DECISIONS.md D-R0-02, the owner's answer
#                  to D-13, makes roster plus offset the primary cohort in every
#                  season. o is read from dim_batter_season as W3.4 reads it.
#   top_ft, bot_ft abs_top_ft(H) and abs_bot_ft(H): 53.5% and 27% of H, in feet.
#   zn             z_norm(z_mid, H) = z_mid * 12 / H.
#   d              signed_edge_in(x_mid, z_mid, top_ft, bot_ft): the distance of
#                  the ball centre from the zone edge, in inches, negative inside,
#                  Euclidean at the corners, no ball radius taken off. This is
#                  W3.5's d. The ABS predicate is d - BALL_R_IN < 0.
#   edge           nearest_edge(x_mid, z_mid, top_ft, bot_ft): side, top or bot.
#   cs             1 when the umpire's original call is a strike, else 0. It comes
#                  from W3.6's call_original, not from the published call. On an
#                  overturned 2026 pitch the two differ.
#   count_class    0-strike, 1-strike or 2-strike, from the strikes before the
#                  pitch. balls and strikes are kept, so the 12-level count needs
#                  no other column.
#   pitch_group    FF (FF, FA); SI/FC (SI, FC); BRK (SL, ST, SV, CU, KC, CS);
#                  OFFSP (CH, FS, FO, SC, KN, EP, UN). A code outside these 17
#                  fails the build rather than falling into a group.
#   velo           release_speed, mph.
#   stand, umpire_hp_id, umpire_season, season, regime, analysis_set
#                  from the open view. catcher is fielder_2.
#
#   Also kept: pitch_uid, game_pk, official_date, batter, pitcher, p_throws,
#   balls, strikes, pitch_type; H_abs and d_abs, the same height and distance
#   for the ABS-measured arm, NA outside P1; challenged and is_overturned from
#   W3.6; delta_run_exp for the W3.19 run values.
#
# WHERE THE BINS COME FROM. SOP W3.7 names count_class and pitch_group and gives
# no bins; the warehouse left both to this step (quality/warehouse_contract.yml,
# deferred block). The three count classes and the four pitch groups are the
# ones the W3 design draft wrote for this step. The draft named the groups and
# no codes. The code-to-group map above is this script's, and the
# pre-registration states it.
#
# OUTCOMES. The script prints no called-strike rate and fits no model. The
# prereg-v1 tag does not exist yet, and a 2025 or 2026 rate is an outcome.
#
# READS. abs.main_marts.v_called_pitch_open and dim_batter_season, restricted to
# analysis_set = 'open' in the same statement, on a read-only attach;
# data/interim/ch1/original_call.parquet (W3.6); out/ch1/tab/T1_sample.csv
# (W3.5), to compare counts; data/interim/dim_batter_season/calibration.json;
# and the Stats API people endpoint through R/lib/http.R, with the same batch
# URLs W3.5 uses, so every request is a raw-cache hit.
#
# WRITES. data/marts/ch1_called.parquet, and only when the rebuilt table differs
# from the file on disk, so a second run leaves the file as the first run left
# it. The path comes from absump.paths.mart(). Check mode writes nothing.
#
# Exit 0 when every check passes, 1 when any fails, 2 on a usage error.

options(warn = 1, digits = 12)
t_start <- Sys.time()

args_all <- commandArgs(trailingOnly = FALSE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1 || (length(args) == 1 && !identical(args, "--check"))) {
  cat("usage: Rscript R/ch1/10_build_analysis_table.R [--check]\n", file = stderr())
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
  library(DBI)
  library(duckdb)
  library(arrow)
  library(jsonlite)
})

source("R/lib/zone.R")
source("R/lib/http.R")
source("R/lib/endpoints.R")

## --- the harness -------------------------------------------------------------

n_pass <- 0L
failures <- character(0)
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
comma <- function(x) formatC(as.numeric(x), format = "d", big.mark = ",")
finish <- function() {
  cat(sprintf("W3.7 %s: %d PASS, %d FAIL, %.1f s\n",
              if (CHECK_ONLY) "check" else "build", n_pass, length(failures),
              as.numeric(difftime(Sys.time(), t_start, units = "secs"))))
  if (length(failures) > 0) {
    cat("FAILED CLAUSES:\n", paste0("  ", failures, "\n"), sep = "")
    quit(status = 1)
  }
  quit(status = 0)
}

## --- constants -----------------------------------------------------------------

SEASONS     <- 2022:2026
REGIMES     <- c("pre_buffer", "buffer_2025", "abs_2026")
REGIME_OF   <- c(`2022` = "pre_buffer", `2023` = "pre_buffer", `2024` = "pre_buffer",
                 `2025` = "buffer_2025", `2026` = "abs_2026")
PITCHER_POS <- c("P", "TWP")
# PEOPLE_URL is in R/lib/endpoints.R.

# POSITION PLAYERS, BY THE ROLE HELD WHEN HE PITCHED. A pitch is a position
# player's pitch when its pitcher held a position other than P (pitcher) or TWP
# (two-way player) in the season he threw it. Today's primary position is not
# the test: Brett Phillips (621433) pitched in 2022 and 2023 as an outfielder
# and is listed P today, so today's position kept his 36 lobs in P0. The role
# comes from three sources, in this order:
#   2022-2025  the position the club's fullSeason roster gives him that season,
#              from every MLB club's roster. P on one roster and a field
#              position on another in the same season fails the build rather
#              than guess;
#   2022-2025  when he is on no roster that season (the endpoint omits 9
#              pitcher-seasons, all of whom pitched), his fielding record for
#              the season: a position player when his games at other positions,
#              DH included, outnumber his games at P;
#   2026       the people endpoint's primary position. 2026 is the season now
#              under way, so that is the role he holds in the season he
#              pitched, and a 2026 roster read would carry moves dated after
#              the last open day.
# Every request goes through R/lib/http.R and is cached, so a re-run sends none.
ROLE_ROSTER_SEASONS <- 2022:2025
# ROLE_TEAMS_URL, ROLE_ROSTER_URL and ROLE_FIELDING_URL are in R/lib/endpoints.R.

role_json <- function(url) {
  res <- absump_http_get(url)
  if (!identical(as.integer(res$status_code), 200L)) stop("HTTP ", res$status_code, " from ", url)
  jsonlite::fromJSON(rawToChar(res$content), simplifyVector = FALSE)
}

# ps: one row per (season, pitcher) in the sample. today: data.frame(pitcher,
# position) from the people endpoint. Returns ps with role, role_source and
# position_player, one row per (season, pitcher).
pitcher_season_roles <- function(ps, today) {
  ps <- unique(ps[, c("season", "pitcher")])
  ps$role <- NA_character_
  ps$role_source <- NA_character_
  for (s in sort(unique(ps$season))) {
    i <- which(ps$season == s)
    if (!(s %in% ROLE_ROSTER_SEASONS)) {
      ps$role[i] <- today$position[match(ps$pitcher[i], today$pitcher)]
      ps$role_source[i] <- "people endpoint, current season"
      next
    }
    teams <- vapply(role_json(sprintf(ROLE_TEAMS_URL, s))$teams, function(x) as.numeric(x$id), 0)
    ro <- list()
    for (tid in sort(teams)) for (e in role_json(sprintf(ROLE_ROSTER_URL, tid, s))$roster)
      ro[[length(ro) + 1L]] <- data.frame(pitcher = as.numeric(e$person$id),
                                          pos = e$position$abbreviation, stringsAsFactors = FALSE)
    ro <- unique(do.call(rbind, ro))
    ro <- ro[ro$pitcher %in% ps$pitcher[i], ]
    kinds <- tapply(ro$pos %in% PITCHER_POS, ro$pitcher, function(v) length(unique(v)))
    if (any(kinds > 1L)) stop(sprintf("season %d: P and a field position on two rosters for %s", s,
                                      paste(names(kinds)[kinds > 1L], collapse = ", ")))
    hit <- match(ps$pitcher[i], ro$pitcher)
    ps$role[i] <- ro$pos[hit]
    ps$role_source[i[!is.na(hit)]] <- "fullSeason roster"
    miss <- ps$pitcher[i[is.na(hit)]]
    for (b in split(miss, ceiling(seq_along(miss) / 100))) {
      if (!length(b)) next
      url <- sprintf(ROLE_FIELDING_URL, paste(format(b, scientific = FALSE, trim = TRUE), collapse = ","), s, s)
      for (p in role_json(url)$people) {
        g <- list()
        for (st in p$stats) for (sp in st$splits) {
          if (!is.null(sp$sport$id) && sp$sport$id != 1L) next
          a <- sp$stat$position$abbreviation
          if (is.null(a) || is.null(sp$stat$games)) next
          k <- paste(if (is.null(sp$team$id)) "all" else sp$team$id, a)
          g[[k]] <- max(c(g[[k]], sp$stat$games))
        }
        gv <- unlist(g)
        team_of <- sub(" .*$", "", names(gv))
        pos_of <- sub("^\\S+ ", "", names(gv))
        # a traded player has a total row per position as well as a row per club
        per_pos <- vapply(unique(pos_of), function(a) {
          w <- pos_of == a
          if (any(w & team_of == "all")) max(gv[w & team_of == "all"]) else sum(gv[w])
        }, 0)
        g_p <- sum(per_pos[names(per_pos) %in% PITCHER_POS], 0)
        g_other <- sum(per_pos[!(names(per_pos) %in% PITCHER_POS)], 0)
        j <- i[ps$pitcher[i] == as.numeric(p$id)]
        ps$role[j] <- if (g_other > g_p) "field" else "P"
        ps$role_source[j] <- sprintf("fielding record (%g games at P, %g elsewhere)", g_p, g_other)
      }
    }
  }
  ps$position_player <- !(ps$role %in% PITCHER_POS)
  ps
}
COUNT_LEVELS <- c("0-strike", "1-strike", "2-strike")
PITCH_GROUP <- c(
  FF = "FF", FA = "FF",
  SI = "SI/FC", FC = "SI/FC",
  SL = "BRK", ST = "BRK", SV = "BRK", CU = "BRK", KC = "BRK", CS = "BRK",
  CH = "OFFSP", FS = "OFFSP", FO = "OFFSP", SC = "OFFSP", KN = "OFFSP", EP = "OFFSP",
  UN = "OFFSP"
)
GROUP_LEVELS <- c("FF", "SI/FC", "BRK", "OFFSP")
EDGE_LEVELS  <- c("side", "top", "bot")
REPROJ_TOL_FT <- 1e-9     # re-projection against the warehouse pair
ZONE_TOL_FT   <- 1e-12    # W3.5's bar for the zone against sz_top_h and sz_bot_h
DT17_MIN_NONNULL <- 0.995 # SOP DT-17: >=99.5% non-null each
BAND_SURF   <- 8.0
BAND_SHADOW <- 3.0
# LICENCE is in R/lib/endpoints.R.

ORIG_CALL_FILE <- file.path(ROOT, "data", "interim", "ch1", "original_call.parquet")
T1_FILE        <- file.path(ROOT, "out", "ch1", "tab", "T1_sample.csv")
CALIB_FILE     <- file.path(ROOT, "data", "interim", "dim_batter_season", "calibration.json")

## --- paths from absump.paths -----------------------------------------------------

paths_from_python <- function() {
  code <- paste(
    "from absump.paths import DUCKDB_PATH, LAST_OPEN_DATE, mart",
    "print(DUCKDB_PATH)", "print(LAST_OPEN_DATE)", "print(mart('ch1_called'))", sep = "; "
  )
  out <- suppressWarnings(system2(
    "uv", c("run", "--locked", "python", "-c", shQuote(code)),
    stdout = TRUE, stderr = TRUE
  ))
  status <- attr(out, "status")
  if (is.null(status)) status <- 0L
  if (status != 0L || length(out) < 3L) {
    stop("could not read the layout from absump.paths (exit ", status, "): ",
         paste(out, collapse = " "), call. = FALSE)
  }
  n <- length(out)
  list(duckdb = trimws(out[n - 2L]), last_open = as.Date(trimws(out[n - 1L])),
       out_file = trimws(out[n]))
}
lay <- paths_from_python()
OUT_FILE <- lay$out_file
OUT_DIR  <- dirname(OUT_FILE)
record("layout", sprintf("warehouse %s; last open day %s; output %s",
                         lay$duckdb, format(lay$last_open), OUT_FILE))

for (f in c(ORIG_CALL_FILE, T1_FILE, CALIB_FILE, lay$duckdb)) {
  check("input present", file.exists(f), f)
}
if (length(failures) > 0) finish()

## --- 1. the warehouse, open views only -------------------------------------------

con <- suppressMessages(DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:"))
attached <- FALSE
for (attempt in 1:30) {
  attached <- tryCatch({
    DBI::dbExecute(con, sprintf("ATTACH %s AS abs (READ_ONLY)",
                                DBI::dbQuoteString(con, lay$duckdb)))
    TRUE
  }, error = function(e) {
    cat(sprintf("RECORD warehouse attach attempt %d failed: %s\n", attempt, conditionMessage(e)))
    FALSE
  })
  if (attached) break
  Sys.sleep(2)
}
check("warehouse attached read-only", attached, lay$duckdb)
if (!attached) finish()
q <- function(sql, ...) DBI::dbGetQuery(con, sql, ...)

cp <- q(sprintf("
  SELECT c.pitch_uid,
         CAST(c.game_pk AS INTEGER)       AS game_pk,
         c.at_bat_number, c.pitch_number,
         c.official_date, c.season, c.level, c.game_type, c.regime, c.analysis_set,
         c.umpire_hp_id, c.umpire_season,
         CAST(c.fielder_2 AS INTEGER)     AS catcher,
         CAST(c.batter AS INTEGER)        AS batter,
         CAST(c.pitcher AS INTEGER)       AS pitcher,
         c.stand, c.p_throws, c.balls, c.strikes, c.pitch_type,
         c.release_speed                  AS velo,
         c.plate_x_mid, c.plate_z_mid, c.plate_x_front, c.plate_z_front, c.plane_source,
         c.vx0, c.vy0, c.vz0, c.ax, c.ay, c.az,
         c.description,
         c.call_original                  AS w216_call_original,
         c.challenged                     AS w216_challenged,
         c.is_overturned                  AS w216_is_overturned,
         c.height_source, c.batter_height_in, c.sz_top_h, c.sz_bot_h,
         c.delta_run_exp,
         b.h_roster_in, b.h_abs_in,
         o.call_original, o.call_final   AS w36_call_final,
         o.is_overturned, o.challenged
  FROM abs.main_marts.v_called_pitch_open AS c
  LEFT JOIN abs.main_marts.dim_batter_season AS b
    ON b.batter = c.batter AND b.season = c.season
   AND b.level = 'mlb' AND b.analysis_set = 'open'
  LEFT JOIN read_parquet(%s) AS o
    ON o.pitch_uid = c.pitch_uid
  WHERE c.level = 'mlb' AND c.game_type = 'R' AND c.analysis_set = 'open'
    AND c.plate_x_mid IS NOT NULL AND c.plate_z_mid IS NOT NULL
  ORDER BY c.season, c.game_pk, c.at_bat_number, c.pitch_number",
  DBI::dbQuoteString(con, ORIG_CALL_FILE)))
cp$official_date <- as.Date(cp$official_date)
record("called pitches with coordinates", sprintf("%s rows read from the open view", comma(nrow(cp))))

off <- q("
  SELECT min(height_in - h_roster_in) FILTER (WHERE height_source = 'people_offset') AS o_min,
         max(height_in - h_roster_in) FILTER (WHERE height_source = 'people_offset') AS o_max,
         avg(h_abs_in - h_roster_in)  FILTER (WHERE season = 2026 AND h_abs_in IS NOT NULL) AS o_2026,
         count(*) FILTER (WHERE height_source = 'people_offset') AS n_people_offset
  FROM abs.main_marts.dim_batter_season
  WHERE level = 'mlb' AND analysis_set = 'open'")
try(DBI::dbDisconnect(con, shutdown = TRUE), silent = TRUE)

## --- 2. position players, as W3.5 finds them ---------------------------------------

ids <- sort(unique(as.numeric(cp$pitcher)))
batches <- split(ids, ceiling(seq_along(ids) / 100))
pos_rows <- list()
n_cache <- 0L
n_sent <- 0L
for (b in batches) {
  url <- sprintf(PEOPLE_URL, paste(format(b, scientific = FALSE, trim = TRUE), collapse = ","))
  res <- absump_http_get(url)
  if (!identical(as.integer(res$status_code), 200L)) {
    check("people endpoint", FALSE, sprintf("HTTP %s for a batch of %d ids", res$status_code, length(b)))
    finish()
  }
  if (isTRUE(res$from_cache)) n_cache <- n_cache + 1L else n_sent <- n_sent + 1L
  people <- jsonlite::fromJSON(rawToChar(res$content), simplifyVector = FALSE)$people
  for (p in people) {
    abbr <- if (is.null(p$primaryPosition$abbreviation)) NA_character_ else p$primaryPosition$abbreviation
    pos_rows[[length(pos_rows) + 1L]] <- data.frame(pitcher = as.numeric(p$id), position = abbr,
                                                    stringsAsFactors = FALSE)
  }
}
pos <- do.call(rbind, pos_rows)
unresolved <- setdiff(ids, pos$pitcher)
check("pitcher positions resolved", length(unresolved) == 0L && !anyNA(pos$position),
      sprintf("%d pitchers in %d requests (%d from the raw cache, %d sent), %d unresolved",
              length(ids), length(batches), n_cache, n_sent, length(unresolved)))
roles <- tryCatch(pitcher_season_roles(data.frame(season = cp$season, pitcher = as.numeric(cp$pitcher)), pos),
                  error = function(e) { check("pitcher roles by season", FALSE, conditionMessage(e)); finish() })
src <- table(sub(" \\(.*$", "", roles$role_source))
check("pitcher roles by season", !anyNA(roles$role),
      sprintf("%d pitcher-seasons, each by the role held that season: %s", nrow(roles),
              paste(sprintf("%d from the %s", as.vector(src), names(src)), collapse = "; ")))
if (anyNA(roles$role)) finish()
is_pp <- roles$position_player[match(paste(cp$season, as.numeric(cp$pitcher)), paste(roles$season, roles$pitcher))]
moved <- roles[roles$position_player != !(pos$position[match(roles$pitcher, pos$pitcher)] %in% PITCHER_POS), ]
record("role then differs from today's position", if (nrow(moved)) paste(sprintf("%d %d, %s then, %s today",
       moved$pitcher, moved$season, moved$role, pos$position[match(moved$pitcher, pos$pitcher)]), collapse = "; ") else "none")
record("position players removed", sprintf("%d pitchers, %s called pitches",
                                           length(unique(cp$pitcher[is_pp])), comma(sum(is_pp))))
t <- cp[!is_pp, ]
rm(cp)
rownames(t) <- NULL
n <- nrow(t)

## --- 3. P0 against W3.5's T1 ------------------------------------------------------

t1 <- utils::read.csv(T1_FILE, stringsAsFactors = FALSE, check.names = FALSE)
t1_row <- function(id) {
  r <- t1[t1$row_id == id, paste0("y", SEASONS)]
  if (nrow(r) != 1L) return(rep(NA_real_, length(SEASONS)))
  as.numeric(unlist(r))
}
by_season <- function(flag) as.numeric(tabulate(match(t$season[flag], SEASONS), length(SEASONS)))
p0_n <- by_season(rep(TRUE, n))
p1_n <- by_season(!is.na(t$h_abs_in))
fmt_s <- function(v) paste(sprintf("%d %s", SEASONS, comma(v)), collapse = ", ")
check("P0 equals W3.5 T1 row P0, per season", identical(p0_n, t1_row("P0")),
      sprintf("%s rows: %s", comma(n), fmt_s(p0_n)))
check("P1 equals W3.5 T1 row P1, per season", identical(p1_n, t1_row("P1")),
      sprintf("%s rows: %s", comma(sum(p1_n)), fmt_s(p1_n)))

## --- 4. keys, joins and the population --------------------------------------------

key_dup <- anyDuplicated(t[, c("game_pk", "at_bat_number", "pitch_number")]) > 0
check("DT-18 keys unique", !anyDuplicated(t$pitch_uid) && !key_dup,
      sprintf("pitch_uid and (game_pk, at_bat_number, pitch_number) unique over %s rows", comma(n)))
check("population", all(t$level == "mlb") && all(t$game_type == "R") &&
        all(t$analysis_set == "open") && all(t$description %in% c("called_strike", "ball", "blocked_ball")) &&
        max(t$official_date) <= lay$last_open && all(t$season %in% SEASONS),
      sprintf("MLB, game_type R, analysis_set open, called descriptions only, %s to %s",
              format(min(t$official_date)), format(max(t$official_date))))
check("regime map", identical(unname(REGIME_OF[as.character(t$season)]), t$regime),
      "pre_buffer 2022-2024, buffer_2025, abs_2026 on every row")
check("every row joins dim_batter_season", !anyNA(t$h_roster_in),
      sprintf("%d rows without a roster height", sum(is.na(t$h_roster_in))))
check("every row joins W3.6 original_call", !anyNA(t$call_original) && !anyNA(t$is_overturned) &&
        !anyNA(t$challenged),
      sprintf("%d rows without a W3.6 row", sum(is.na(t$call_original))))
check("P1 flag agrees with height_source",
      identical(!is.na(t$h_abs_in), !is.na(t$height_source) & t$height_source == "abs_measured"),
      "H_abs is non-null on exactly the rows the warehouse marks abs_measured")

## --- 5. coordinates against the warehouse ----------------------------------------

ps_ok <- all(t$plane_source[t$season <= 2025] == "front") && all(t$plane_source[t$season == 2026] == "mid")
check("plane_source by season", ps_ok, "front 2022-2025, mid 2026")
fr <- t$plane_source == "front"
md <- t$plane_source == "mid"
rp_f <- reproject(t$plate_x_front[fr], t$plate_z_front[fr], t$vx0[fr], t$vy0[fr], t$vz0[fr],
                  t$ax[fr], t$ay[fr], t$az[fr], Y_FRONT_FT, Y_MID_FT)
rp_m <- reproject(t$plate_x_mid[md], t$plate_z_mid[md], t$vx0[md], t$vy0[md], t$vz0[md],
                  t$ax[md], t$ay[md], t$az[md], Y_MID_FT, Y_FRONT_FT)
err_f <- max(abs(rp_f$x - t$plate_x_mid[fr]), abs(rp_f$z - t$plate_z_mid[fr]))
err_m <- max(abs(rp_m$x - t$plate_x_front[md]), abs(rp_m$z - t$plate_z_front[md]))
check("x_mid, z_mid reproduce under zone.R", err_f < REPROJ_TOL_FT && err_m < REPROJ_TOL_FT,
      sprintf("front->mid on %s rows max %.2e ft; mid->front on %s rows max %.2e ft; bar %.0e ft",
              comma(sum(fr)), err_f, comma(sum(md)), err_m, REPROJ_TOL_FT))

## --- 6. heights and the zone -------------------------------------------------------

o <- off$o_min
calib <- jsonlite::fromJSON(CALIB_FILE)
check("roster offset o", abs(off$o_max - off$o_min) < 1e-12 && abs(off$o_2026 - o) < 1e-12 &&
        abs(calib$offset_in - o) < 1e-12,
      sprintf("o = %.12f in: one value over %s people_offset rows, the 2026 overlap mean, calibration.json",
              o, comma(off$n_people_offset)))
H <- t$h_roster_in + o
H_abs <- t$h_abs_in
nonp1 <- is.na(H_abs)
check("H is the warehouse height outside P1",
      max(abs(H[nonp1] - t$batter_height_in[nonp1])) < 1e-12,
      sprintf("roster plus o equals batter_height_in on the %s rows outside P1", comma(sum(nonp1))))
check("H_abs is the warehouse height inside P1",
      identical(H_abs[!nonp1], t$batter_height_in[!nonp1]),
      sprintf("h_abs_in equals batter_height_in on the %s rows of P1", comma(sum(!nonp1))))
dev_top <- max(abs(abs_top_ft(t$batter_height_in) - t$sz_top_h))
dev_bot <- max(abs(abs_bot_ft(t$batter_height_in) - t$sz_bot_h))
check("zone.R reproduces sz_top_h and sz_bot_h", dev_top < ZONE_TOL_FT && dev_bot < ZONE_TOL_FT,
      sprintf("max %.1e ft and %.1e ft", dev_top, dev_bot))
dh <- H - ifelse(nonp1, H, H_abs)
record("H minus H_abs on P1", sprintf("mean %.4f in, sd %.4f in, max |.| %.4f in, over %s rows",
                                      mean(dh[!nonp1]), stats::sd(dh[!nonp1]),
                                      max(abs(dh[!nonp1])), comma(sum(!nonp1))))

x_mid  <- t$plate_x_mid
z_mid  <- t$plate_z_mid
top_ft <- abs_top_ft(H)
bot_ft <- abs_bot_ft(H)
zn     <- z_norm(z_mid, H)
d      <- signed_edge_in(x_mid, z_mid, top_ft, bot_ft)
edge   <- nearest_edge(x_mid, z_mid, top_ft, bot_ft)
d_abs  <- signed_edge_in(x_mid, z_mid, abs_top_ft(H_abs), abs_bot_ft(H_abs))

# W3.5 measured its bands with the warehouse height. The same geometry on that
# height must give T1's counts exactly; this ties the table to W3.5's d.
d_wh <- signed_edge_in(x_mid, z_mid, abs_top_ft(t$batter_height_in), abs_bot_ft(t$batter_height_in))
b8 <- by_season(abs(d_wh) <= BAND_SURF)
b3 <- by_season(abs(d_wh) <= BAND_SHADOW)
check("W3.5 bands reproduce on the warehouse height",
      identical(b8, t1_row("B_d8_P0")) && identical(b3, t1_row("B_d3_P0")),
      sprintf("|d| <= 8 in: %s; |d| <= 3 in: %s", fmt_s(b8), fmt_s(b3)))
record("bands on H (roster plus o)", sprintf("|d| <= 8 in: %s; |d| <= 3 in: %s",
                                             fmt_s(by_season(abs(d) <= BAND_SURF)),
                                             fmt_s(by_season(abs(d) <= BAND_SHADOW))))
check("d_abs is W3.5's d on P1 and NA outside it",
      identical(d_abs[!nonp1], d_wh[!nonp1]) && all(is.na(d_abs[nonp1])),
      sprintf("%s P1 rows equal, %s rows outside P1 NA", comma(sum(!nonp1)), comma(sum(nonp1))))

## --- 7. the call ------------------------------------------------------------------

cs <- as.integer(t$call_original == "strike")
cs_pub <- as.integer(t$description == "called_strike")
moved <- cs != cs_pub
check("cs is the original call",
      identical(moved, t$is_overturned) && identical(t$call_original, t$w216_call_original) &&
        identical(t$w36_call_final == "strike", cs_pub == 1L),
      sprintf("cs differs from the published call on %s rows, exactly the overturned ones; call_original equals the W2.16 column on every row",
              comma(sum(moved))))
# The warehouse leaves is_overturned NULL on an unchallenged pitch; W3.6 writes FALSE.
w216_ovt <- !is.na(t$w216_is_overturned) & t$w216_is_overturned
check("challenges only in 2026",
      !any(t$challenged[t$season < 2026]) && !any(t$is_overturned[t$season < 2026]) &&
        identical(t$challenged, t$w216_challenged) && identical(t$is_overturned, w216_ovt) &&
        all(is.na(t$w216_is_overturned) == !t$challenged),
      sprintf("2026: %s challenged, %s overturned; 0 before 2026; both flags equal the W2.16 columns, whose is_overturned is NULL on exactly the %s unchallenged rows",
              comma(sum(t$challenged)), comma(sum(t$is_overturned)), comma(sum(!t$challenged))))

## --- 8. count, pitch group, identifiers --------------------------------------------

check("count in range", all(t$balls %in% 0:3) && all(t$strikes %in% 0:2),
      "balls 0-3 and strikes 0-2 on every row")
count_class <- factor(COUNT_LEVELS[t$strikes + 1L], levels = COUNT_LEVELS)
unknown <- setdiff(unique(t$pitch_type), names(PITCH_GROUP))
check("every pitch_type has a group", length(unknown) == 0L && !anyNA(t$pitch_type),
      if (length(unknown)) paste("unmapped:", paste(unknown, collapse = ", ")) else
        sprintf("%d codes in P0, all in the 17-code map", length(unique(t$pitch_type))))
pitch_group <- factor(unname(PITCH_GROUP[t$pitch_type]), levels = GROUP_LEVELS)
tab_code <- table(t$pitch_type)
for (g in GROUP_LEVELS) {
  codes <- names(PITCH_GROUP)[PITCH_GROUP == g]
  codes <- codes[codes %in% names(tab_code)]
  record(paste("pitch_group", g), paste(sprintf("%s %s", codes, comma(tab_code[codes])), collapse = ", "))
}
check("umpire_season is umpire_hp_id:season",
      identical(t$umpire_season, paste0(t$umpire_hp_id, ":", t$season)),
      sprintf("%d umpire-seasons, %d umpires", length(unique(t$umpire_season)),
              length(unique(t$umpire_hp_id))))

## --- 9. the table -------------------------------------------------------------------

radix_levels <- function(x) sort(unique(x), method = "radix")
out <- data.frame(
  pitch_uid     = t$pitch_uid,
  game_pk       = t$game_pk,
  official_date = t$official_date,
  season        = as.integer(t$season),
  regime        = factor(t$regime, levels = REGIMES),
  analysis_set  = factor(t$analysis_set, levels = "open"),
  umpire_hp_id  = as.integer(t$umpire_hp_id),
  umpire_season = factor(t$umpire_season, levels = radix_levels(t$umpire_season)),
  catcher       = t$catcher,
  batter        = t$batter,
  pitcher       = t$pitcher,
  stand         = factor(t$stand, levels = c("L", "R")),
  p_throws      = factor(t$p_throws, levels = c("L", "R")),
  balls         = as.integer(t$balls),
  strikes       = as.integer(t$strikes),
  count_class   = count_class,
  pitch_type    = t$pitch_type,
  pitch_group   = pitch_group,
  velo          = t$velo,
  x_mid         = x_mid,
  z_mid         = z_mid,
  H             = H,
  top_ft        = top_ft,
  bot_ft        = bot_ft,
  zn            = zn,
  d             = d,
  edge          = factor(edge, levels = EDGE_LEVELS),
  cs            = cs,
  H_abs         = H_abs,
  d_abs         = d_abs,
  challenged    = t$challenged,
  is_overturned = t$is_overturned,
  delta_run_exp = t$delta_run_exp,
  stringsAsFactors = FALSE
)
rm(t)

SOP_COLS <- c("x_mid", "z_mid", "H", "top_ft", "bot_ft", "zn", "d", "edge", "cs", "count_class",
              "pitch_group", "velo", "stand", "umpire_hp_id", "umpire_season", "catcher",
              "season", "regime", "analysis_set")
nulls <- vapply(out, function(v) sum(is.na(v)), 0)
check("the 19 SOP W3.7 columns present and non-null",
      all(SOP_COLS %in% names(out)) && all(nulls[SOP_COLS] == 0),
      sprintf("%d of 19 present; %d nulls across them", sum(SOP_COLS %in% names(out)),
              sum(nulls[intersect(SOP_COLS, names(out))])))
dt17 <- c("x_mid", "z_mid", "catcher", "delta_run_exp", "balls", "strikes", "stand", "p_throws")
nn <- 1 - nulls[dt17] / n
check("DT-17 null rates", all(nn >= DT17_MIN_NONNULL),
      sprintf(">=99.5%% non-null each: %s", paste(sprintf("%s %.4f%%", dt17, 100 * nn), collapse = ", ")))
record("null counts", paste(sprintf("%s %d", names(nulls)[nulls > 0], nulls[nulls > 0]), collapse = "; "))
inside <- abs(x_mid) <= PLATE_HALF_W_FT & z_mid >= bot_ft & z_mid <= top_ft
check("d <= 0 exactly on the pitches inside the zone", identical(inside, d <= 0),
      sprintf("%s rows inside the H zone by direct comparison, %s with d <= 0",
              comma(sum(inside)), comma(sum(d <= 0))))

meta <- list(
  w37_step    = "W3.7 the analysis table",
  w37_grain   = "one row per P0 pitch (SOP W3.5); key pitch_uid",
  w37_sample  = "called_strike, ball, blocked_ball; game_type R; analysis_set open; non-null plate_x_mid and plate_z_mid; position players removed; P1 = non-null H_abs",
  w37_height  = sprintf("H = h_roster_in + o, o = %.12f in (DECISIONS.md D-R0-02); H_abs = h_abs_in", o),
  w37_d       = "d = signed_edge_in(x_mid, z_mid, 0.535 H/12, 0.27 H/12), ball centre, inches, negative inside; ABS predicate d - 1.45 < 0",
  w37_cs      = "cs = 1 when W3.6 call_original is strike",
  w37_count_class = "0-strike, 1-strike, 2-strike from strikes before the pitch",
  w37_pitch_group = paste(sprintf("%s=%s", names(PITCH_GROUP), PITCH_GROUP), collapse = ","),
  w37_sources = paste("warehouse/abs.duckdb open views v_called_pitch_open and dim_batter_season;",
                      "data/interim/ch1/original_call.parquet (W3.6);",
                      "Stats API club fullSeason rosters 2022-2025, fielding records and the people endpoint for the role each pitcher held in the season he pitched"),
  w37_licence = LICENCE,
  w37_counts  = sprintf("rows %d; P1 %d; columns %d", nrow(out), sum(!is.na(out$H_abs)), ncol(out))
)
build_table <- function(df) {
  tb <- arrow::arrow_table(df)
  for (k in names(meta)) tb$metadata[[k]] <- meta[[k]]
  tb
}
same_as_disk <- function(path) {
  old_tb <- arrow::read_parquet(path, as_data_frame = FALSE)
  old <- as.data.frame(old_tb)
  class(old) <- "data.frame"
  shape <- identical(names(old), names(out)) && nrow(old) == nrow(out)
  types <- shape && identical(lapply(old, class), lapply(out, class)) &&
    identical(lapply(Filter(is.factor, old), levels), lapply(Filter(is.factor, out), levels))
  vals <- types && isTRUE(all.equal(old, out, tolerance = 0, check.attributes = FALSE))
  md <- identical(unname(unlist(old_tb$metadata[names(meta)])), unname(unlist(meta)))
  list(rows = nrow(old), cols = ncol(old), shape = shape, types = types, vals = vals, meta = md)
}

## --- 10. write, or compare --------------------------------------------------------------

record("table", sprintf("%s rows x %d columns", comma(nrow(out)), ncol(out)))
if (CHECK_ONLY) {
  on_disk <- file.exists(OUT_FILE)
  check("artifact on disk", on_disk, OUT_FILE)
  if (on_disk) {
    s <- same_as_disk(OUT_FILE)
    check("artifact equals a rebuild from sources", s$vals && s$meta,
          sprintf("%s rows x %d columns on disk; rebuilt %s x %d; names %s, types %s, values %s, w37 metadata %s",
                  comma(s$rows), s$cols, comma(nrow(out)), ncol(out),
                  if (s$shape) "same" else "differ", if (s$types) "same" else "differ",
                  if (s$vals) "identical" else "differ", if (s$meta) "same" else "differ"))
    record("artifact", sprintf("%s bytes, md5 %s", comma(file.size(OUT_FILE)),
                               unname(tools::md5sum(OUT_FILE))))
  }
} else if (length(failures) > 0) {
  record("write skipped", sprintf("%d check(s) failed; %s left as it was", length(failures), OUT_FILE))
} else {
  unchanged <- file.exists(OUT_FILE) && with(same_as_disk(OUT_FILE), vals && meta)
  if (unchanged) {
    record("artifact unchanged, not rewritten", sprintf("%s, %s bytes, md5 %s", OUT_FILE,
           comma(file.size(OUT_FILE)), unname(tools::md5sum(OUT_FILE))))
  } else {
    dir.create(OUT_DIR, recursive = TRUE, showWarnings = FALSE)
    tmp <- file.path(OUT_DIR, sprintf(".ch1_called.parquet.tmp-%d", Sys.getpid()))
    arrow::write_parquet(build_table(out), tmp)
    ok <- file.rename(tmp, OUT_FILE)
    if (!ok) unlink(tmp)
    check("artifact written", ok && file.exists(OUT_FILE),
          sprintf("%s, %s rows x %d columns, %s bytes, md5 %s", OUT_FILE, comma(nrow(out)), ncol(out),
                  comma(file.size(OUT_FILE)), unname(tools::md5sum(OUT_FILE))))
  }
}
finish()
