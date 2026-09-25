#!/usr/bin/env Rscript
# R/ch1/01_sample.R - SOP step W3.5, regimes, sample and exclusions.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/01_sample.R
#
# It writes out/ch1/tab/T1_sample.csv, the Chapter 1 sample table, and prints
# one PASS or FAIL line per assertion. Every assertion runs. The script exits 1
# if any failed. It fits no model.
#
# WHAT T1 HOLDS. One row per rule, one column per season, 2022 to 2026, and a
# total. The `unit` column says what a cell is: pitches, percent, games,
# umpires, date or label. The blocks, in order:
#
#   regime   season boundaries fetched from the Stats API seasons endpoint,
#            sportId=1 for 2022-2026 and sportId=11 for AAA 2023-2025, and the
#            regime label each season carries in the warehouse
#   sample   the exclusion waterfall, in the SOP's order, ending in P0 and P1.
#            An exclusion row holds the rows it removed. A sample row holds the
#            rows left. blocked_ball is a retain row: counted, not removed
#   band     the |d| <= 8.0 in surface-fit band and the |d| <= 3.0 in shadow
#            band. Neither filters P0 or P1
#   size     games and called pitches per game, against the SOP's 152.1
#   cohort   P0 coverage by the two batter-height cohorts
#   panel    the balanced umpire panel for CH1-A14
#
# THE TWO NAMES. P0 and P1 are the SOP's, defined once in W3.5:
#   P0 = every called pitch with game_type == "R", official date 2022-01-01 to
#        the last open day, and non-null re-projected coordinates, less the
#        pitches thrown by position players (the exclusion list names them).
#   P1 = P0 restricted to the ABS-measured-height cohort,
#        height_source == "abs_measured".
# DECISIONS.md D-R0-02, the owner's own R0 answer, makes roster height
# plus offset the primary cohort and the ABS-measured cohort a robustness arm.
# The SOP text still calls P1 the primary sample. This script counts both row
# sets exactly as W3.5 defines them and reports roster coverage of P0 beside
# them. It does not choose which one <<N_CALLED>> reports.
#
# THE FILTER. game_type == "R", never a date (SOP W3.5). The season boundaries
# are fetched and published, and one assertion checks that every open
# regular-season pitch falls inside its season's fetched regular-season window.
# No date bounds a query here.
#
# d. The signed distance from the harmonised zone in inches, from R/lib/zone.R:
# signed_edge_in(plate_x_mid, plate_z_mid, abs_top_ft(H), abs_bot_ft(H)), with
# H the warehouse batter_height_in. It is the ball-centre distance on the
# mid-plate plane, with no ball radius taken off. The script checks that
# abs_top_ft(H) and abs_bot_ft(H) reproduce the warehouse sz_top_h and sz_bot_h.
#
# 2025 AND 2026 OUTCOMES. The shadow-band called-strike rate is computed for
# 2022-2024 only. It is the raw form of the pre-registered shadow_rate, and the
# plan is not frozen yet, so the 2025 and 2026 cells are left empty until the
# prereg-v1 tag exists. Counts and shares of pitches are not outcomes and are
# reported for every season.
#
# POSITION PLAYERS. A pitch is excluded when its pitcher held a position other
# than P (pitcher) or TWP (two-way player) in the season he threw it; the block
# above pitcher_season_roles() below gives the sources. Ids are sorted and cut
# into batches of 100 so that each batch URL is stable and R/lib/http.R serves
# it from the raw cache on a re-run.
#
# READS. Only the open views v_pitch_open and v_called_pitch_open, and three
# dimensions, each restricted to analysis_set = 'open' in the same statement.
# The connection is read-only. The warehouse path and the last open day come
# from src/absump/paths.py, which holds every layout string once.
#
# REQUESTS. Through R/lib/http.R only, under config/throttle.yml: 8 seasons URLs
# and one people URL per 100 pitchers, 25 in all on the first run at 4 s each.
# A re-run costs zero requests.
#
# SIDE EFFECTS. One file, out/ch1/tab/T1_sample.csv, written only when its bytes
# change, so a second run leaves the tree as the first run left it. The raw
# cache and its manifest grow on the first run only.

suppressPackageStartupMessages({
  library(DBI)
  library(duckdb)
  library(jsonlite)
  library(yaml)
})

source("R/lib/zone.R")
source("R/lib/http.R")
source("R/lib/endpoints.R")

SEASONS     <- 2022:2026
AAA_SEASONS <- 2023:2025
OUT_CSV     <- "out/ch1/tab/T1_sample.csv"
CALLED      <- c("called_strike", "ball", "blocked_ball")
POSTSEASON  <- c("F", "D", "L", "W")
PITCHER_POS <- c("P", "TWP")
BAND_SURF   <- 8.0
BAND_SHADOW <- 3.0
PANEL_GAMES <- 15L
DEV_SEASONS <- 2022:2024
# SEASONS_URL and PEOPLE_URL are in R/lib/endpoints.R.

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

# The SOP W3.5 table, month-day as the SOP prints it. The three 2026 cells that
# fall after the last open day are NA here: GD-04 rule 5 keeps a held-out day
# out of R/. The 2026 regular-season end is compared with config/seal.yml
# instead, and the 2026 postseason is published as fetched.
SOP_TABLE <- data.frame(
  season        = 2022:2026,
  spring_start  = c("02-27", "02-24", "02-22", "02-20", "02-20"),
  spring_end    = c("04-06", "03-28", "03-26", "03-25", "03-24"),
  regular_start = c("04-07", "03-30", "03-20", "03-18", "03-25"),
  regular_end   = c("10-05", "10-02", "09-30", "09-28", NA),
  asb_last      = c("07-17", "07-09", "07-14", "07-14", "07-14"),
  asb_first     = c("07-21", "07-14", "07-19", "07-18", "07-19"),
  post_start    = c("10-07", "10-03", "10-01", "09-30", NA),
  post_end      = c("11-05", "11-01", "10-30", "11-01", NA),
  stringsAsFactors = FALSE
)
SOP_AAA <- data.frame(
  season        = 2023:2025,
  regular_start = c("03-31", "03-29", "03-28"),
  regular_end   = c("09-24", "09-22", "09-21"),
  stringsAsFactors = FALSE
)

# Stats API field for each column of the SOP table.
API_FIELDS <- c(
  spring_start  = "springStartDate",
  spring_end    = "springEndDate",
  regular_start = "regularSeasonStartDate",
  regular_end   = "regularSeasonEndDate",
  asb_last      = "lastDate1stHalf",
  asb_first     = "firstDate2ndHalf",
  post_start    = "postSeasonStartDate",
  post_end      = "postSeasonEndDate"
)

n_pass <- 0L
n_fail <- 0L
pass <- function(...) {
  n_pass <<- n_pass + 1L
  cat("PASS    ", ..., "\n", sep = "")
}
fail <- function(...) {
  n_fail <<- n_fail + 1L
  cat("FAIL    ", ..., "\n", sep = "")
}
record <- function(...) cat("record  ", ..., "\n", sep = "")
check <- function(ok, label, detail = "") {
  if (isTRUE(ok)) pass(label, detail) else fail(label, detail)
}
clause <- function(label, expr) {
  tryCatch(expr, error = function(e) fail(label, ": ", conditionMessage(e)))
}
fmt_n <- function(x) formatC(x, format = "d", big.mark = ",")

# ---------------------------------------------------------------- paths
paths_from_python <- function() {
  code <- paste(
    "from absump.paths import DUCKDB_PATH, LAST_OPEN_DATE",
    "print(DUCKDB_PATH)", "print(LAST_OPEN_DATE)", sep = "; "
  )
  out <- suppressWarnings(system2(
    "uv", c("run", "--locked", "python", "-c", shQuote(code)),
    stdout = TRUE, stderr = TRUE
  ))
  status <- attr(out, "status")
  if (is.null(status)) status <- 0L
  if (status != 0L || length(out) < 2L) {
    stop("could not read the layout from absump.paths (exit ", status, "): ",
         paste(out, collapse = " "), call. = FALSE)
  }
  n <- length(out)
  list(duckdb = trimws(out[n - 1L]), last_open = as.Date(trimws(out[n])))
}

lay <- paths_from_python()
if (!file.exists(lay$duckdb)) {
  cat("FAIL    warehouse not found at ", lay$duckdb, "\n", sep = "")
  quit(status = 1L)
}
con <- dbConnect(duckdb::duckdb(), dbdir = lay$duckdb, read_only = TRUE)
finish <- function(status) {
  try(dbDisconnect(con, shutdown = TRUE), silent = TRUE)
  quit(status = status)
}
q <- function(sql) dbGetQuery(con, sql)

# ---------------------------------------------------------------- the rows
T1 <- list()
add_row <- function(block, row_id, rule, unit, values, total = NA,
                    expected = "", note = "") {
  v <- setNames(rep(NA_character_, length(SEASONS)), paste0("y", SEASONS))
  if (!is.null(values)) {
    for (s in names(values)) v[[paste0("y", s)]] <- as.character(values[[s]])
  }
  T1[[length(T1) + 1L]] <<- c(
    block = block, row_id = row_id, rule = rule, unit = unit, v,
    total = if (is.na(total)) NA_character_ else as.character(total),
    expected = expected, note = note
  )
}
by_season <- function(df, col = "n") {
  out <- setNames(as.list(rep(0, length(SEASONS))), SEASONS)
  for (i in seq_len(nrow(df))) out[[as.character(df$season[i])]] <- df[[col]][i]
  out
}
counts_row <- function(block, row_id, rule, df, expected = "", note = "") {
  v <- by_season(df)
  add_row(block, row_id, rule, "pitches", lapply(v, fmt_plain),
          fmt_plain(sum(unlist(v))), expected, note)
  invisible(v)
}
fmt_plain <- function(x) format(as.numeric(x), scientific = FALSE, trim = TRUE)
pct <- function(num, den) sprintf("%.2f", 100 * num / den)

# ============================================================ 1. regimes
cat("W3.5 regimes, sample and exclusions\n")
cat("warehouse: open views only; last open day ", format(lay$last_open), "\n", sep = "")

fetch_season <- function(sport, season) {
  res <- absump_http_get(sprintf(SEASONS_URL, sport, season))
  if (!identical(as.integer(res$status_code), 200L)) {
    stop(sprintf("seasons sportId=%d season=%d returned HTTP %s",
                 sport, season, res$status_code))
  }
  payload <- jsonlite::fromJSON(rawToChar(res$content), simplifyVector = FALSE)
  rows <- Filter(function(x) identical(as.character(x$seasonId), as.character(season)),
                 payload$seasons)
  if (length(rows) != 1L) {
    stop(sprintf("seasons sportId=%d season=%d: %d season rows", sport, season,
                 length(rows)))
  }
  rows[[1L]]
}

boundaries <- NULL
aaa <- NULL
clause("season boundaries fetched", {
  got <- lapply(SEASONS, function(s) fetch_season(1L, s))
  boundaries <<- do.call(rbind, lapply(seq_along(SEASONS), function(i) {
    f <- got[[i]]
    missing <- setdiff(API_FIELDS, names(f))
    if (length(missing)) {
      stop(sprintf("season %d lacks %s", SEASONS[i], paste(missing, collapse = ", ")))
    }
    data.frame(season = SEASONS[i],
               as.list(setNames(vapply(API_FIELDS, function(k) f[[k]], ""),
                                names(API_FIELDS))),
               stringsAsFactors = FALSE)
  }))
  got_aaa <- lapply(AAA_SEASONS, function(s) fetch_season(11L, s))
  aaa <<- data.frame(
    season = AAA_SEASONS,
    regular_start = vapply(got_aaa, function(f) f$regularSeasonStartDate, ""),
    regular_end   = vapply(got_aaa, function(f) f$regularSeasonEndDate, ""),
    stringsAsFactors = FALSE
  )
  pass("season boundaries fetched: sportId=1 for ", length(SEASONS),
       " seasons, sportId=11 for ", length(AAA_SEASONS), ", every field present")
})

if (!is.null(boundaries)) {
  labels <- c(
    spring_start  = "spring training start (sportId=1)",
    spring_end    = "spring training end (sportId=1)",
    regular_start = "regular season start (sportId=1)",
    regular_end   = "regular season end (sportId=1)",
    asb_last      = "All-Star break: last day of the first half",
    asb_first     = "All-Star break: first day of the second half",
    post_start    = "postseason start (sportId=1)",
    post_end      = "postseason end (sportId=1)"
  )
  seal <- yaml::read_yaml("config/seal.yml")
  n_diff <- 0L
  for (k in names(API_FIELDS)) {
    fetched <- setNames(as.list(boundaries[[k]]), boundaries$season)
    sop <- SOP_TABLE[[k]]
    diffs <- character(0)
    for (i in seq_along(SEASONS)) {
      s <- SEASONS[i]
      got_md <- format(as.Date(boundaries[[k]][i]), "%m-%d")
      got_yr <- format(as.Date(boundaries[[k]][i]), "%Y")
      if (is.na(sop[i])) next
      if (!identical(got_md, sop[i]) || !identical(got_yr, as.character(s))) {
        diffs <- c(diffs, sprintf("%d fetched %s, SOP table %s", s,
                                  boundaries[[k]][i], sop[i]))
      }
    }
    exp_txt <- paste(ifelse(is.na(sop), "not written under R/", sop), collapse = " | ")
    note <- if (length(diffs)) {
      paste0("fetched value is authoritative; differs from the SOP table: ",
             paste(diffs, collapse = "; "))
    } else if (anyNA(sop)) {
      paste0("matches the SOP table 2022-2025; the 2026 cell is ",
             if (k == "regular_end") "compared with config/seal.yml" else "published as fetched")
    } else {
      "matches the SOP table in every season"
    }
    add_row("regime", paste0("R_", k), labels[[k]], "date", fetched,
            expected = paste0("SOP table: ", exp_txt), note = note)
    if (length(diffs)) {
      n_diff <- n_diff + length(diffs)
      for (d in diffs) record("season boundary differs from the SOP table: ", k, " ", d)
    }
  }
  if (n_diff == 0L) {
    pass("season boundaries: every compared cell matches the SOP W3.5 table")
  } else {
    record(n_diff, " season-boundary cells differ from the SOP table; ",
           "the fetched values are published (the SOP names the endpoint authoritative)")
  }
  end26 <- boundaries$regular_end[boundaries$season == 2026]
  check(identical(end26, as.character(seal$regular_season_end)),
        "2026 regular-season end matches config/seal.yml regular_season_end",
        paste0(" (", end26, ")"))
  ord_ok <- with(boundaries,
    as.Date(regular_start) < as.Date(asb_last) &
    as.Date(asb_last) < as.Date(asb_first) &
    as.Date(asb_first) <= as.Date(regular_end) &
    as.Date(regular_end) < as.Date(post_start) &
    as.Date(post_start) <= as.Date(post_end))
  check(all(ord_ok), "season boundaries ordered: regular start < break < regular end < postseason")

  aaa_diffs <- character(0)
  for (k in c("regular_start", "regular_end")) {
    for (i in seq_len(nrow(aaa))) {
      if (!identical(format(as.Date(aaa[[k]][i]), "%m-%d"), SOP_AAA[[k]][i])) {
        aaa_diffs <- c(aaa_diffs, sprintf("%s %d fetched %s, SOP %s", k,
                                          aaa$season[i], aaa[[k]][i], SOP_AAA[[k]][i]))
      }
    }
    add_row("regime", paste0("R_aaa_", k),
            sprintf("AAA regular season %s (sportId=11)",
                    if (k == "regular_start") "start" else "end"),
            "date", setNames(as.list(aaa[[k]]), aaa$season),
            expected = paste0("SOP: ", paste(sprintf("%d %s", SOP_AAA$season, SOP_AAA[[k]]),
                                             collapse = " | ")),
            note = "AAA is not in P0 or P1; fetched for the W3.9 AAA arm")
  }
  if (length(aaa_diffs)) {
    for (d in aaa_diffs) record("AAA boundary differs from the SOP: ", d)
  } else {
    pass("AAA boundaries 2023-2025 match the SOP W3.5 line")
  }
}

# The regime each season carries, from the open view.
regimes <- q("
  SELECT season, string_agg(DISTINCT regime, '+' ORDER BY regime) AS regime,
         count(DISTINCT regime) AS n_regime,
         min(official_date) AS first_day, max(official_date) AS last_day
  FROM main_marts.v_pitch_open
  WHERE level = 'mlb' AND game_type = 'R'
  GROUP BY season ORDER BY season")
add_row("regime", "R_label", "regime label in the warehouse (five-level season factor, three regimes)",
        "label", setNames(as.list(regimes$regime), regimes$season),
        expected = "pre_buffer 2022-2024 | buffer_2025 | abs_2026",
        note = "season enters the model as a five-level factor; regime contrasts are linear combinations of its levels")
add_row("regime", "R_first_day", "first official date with a regular-season pitch in the open lake",
        "date", setNames(as.list(format(regimes$first_day)), regimes$season))
add_row("regime", "R_last_day", "last official date with a regular-season pitch in the open lake",
        "date", setNames(as.list(format(regimes$last_day)), regimes$season),
        note = "2026 stops at the last open day; later days are held out")
check(all(regimes$n_regime == 1L) &&
        identical(regimes$regime, c("pre_buffer", "pre_buffer", "pre_buffer",
                                    "buffer_2025", "abs_2026")),
      "regime map: one label per season, pre_buffer 2022-2024, buffer_2025, abs_2026")
check(as.integer(format(min(regimes$first_day), "%Y")) >= 2022L &&
        max(regimes$last_day) <= lay$last_open,
      "open regular-season pitches run from season 2022 to the last open day",
      paste0(" (", format(min(regimes$first_day)), " to ", format(max(regimes$last_day)), ")"))
if (!is.null(boundaries)) {
  inside <- merge(regimes, boundaries[, c("season", "regular_start", "regular_end")], by = "season")
  ok <- inside$first_day >= as.Date(inside$regular_start) &
        inside$last_day <= as.Date(inside$regular_end)
  check(all(ok), "every open game_type R pitch lies inside its season's fetched regular-season window")
}

# ============================================================ 2. the waterfall
cat("-- sample\n")
per <- function(where, from = "main_marts.v_pitch_open") {
  q(sprintf("SELECT season, count(*) AS n FROM %s WHERE level = 'mlb' AND (%s)
             GROUP BY season ORDER BY season", from, where))
}
start <- counts_row("sample", "S_all", "every Statcast pitch in the open lake, MLB",
                    per("TRUE"), note = "main_marts.v_pitch_open")
x_gt <- counts_row("sample", "X_game_type", "excluded: game_type != \"R\"",
                   per("game_type <> 'R' AND game_type NOT IN ('F','D','L','W')"),
                   note = "the filter is on game_type, never on date; the schedule is pulled with gameType=R, so the lake holds no other game type")
x_post <- counts_row("sample", "X_postseason", "excluded: postseason held out of the primary",
                     per("game_type IN ('F','D','L','W')"),
                     note = "separate pre-registered secondary; 2022-2025 postseason pitches are not in the lake and the 2026 postseason is held out")
REG <- "game_type = 'R'"
x_ab <- counts_row("sample", "X_automatic_ball", "excluded: automatic_ball",
                   per(paste(REG, "AND description = 'automatic_ball'")))
x_po <- counts_row("sample", "X_pitchout", "excluded: pitchout",
                   per(paste(REG, "AND description = 'pitchout'")))
x_hbp <- counts_row("sample", "X_hit_by_pitch", "excluded: hit_by_pitch",
                    per(paste(REG, "AND description = 'hit_by_pitch'")))
x_as <- counts_row("sample", "X_automatic_strike", "excluded: automatic_strike",
                   per(paste(REG, "AND description = 'automatic_strike'")),
                   note = "not named in SOP W3.5; a pitch-clock strike is not a called pitch")
x_sw <- counts_row("sample", "X_not_taken", "excluded: swung at, bunted or put in play",
                   per(paste(REG, "AND description NOT IN ('called_strike','ball','blocked_ball',",
                             "'automatic_ball','pitchout','hit_by_pitch','automatic_strike')")),
                   note = "not a called pitch; P0 is called pitches only")
called <- counts_row("sample", "C_called", "called pitches: called_strike, ball, blocked_ball",
                     per(paste(REG, "AND description IN ('called_strike','ball','blocked_ball')")),
                     expected = "about 370k per season, about 1.85M in all")
x_blank <- counts_row("sample", "X_blank_coordinate",
                      "excluded: blank re-projected coordinate (plate_x_mid or plate_z_mid null)",
                      per(paste(REG, "AND description IN ('called_strike','ball','blocked_ball')",
                                "AND (plate_x_mid IS NULL OR plate_z_mid IS NULL)")))

# Called pitches with coordinates, pulled once into R for the rest.
cp <- q("
  SELECT c.season, c.game_pk, c.pitcher, c.batter, c.umpire_hp_id, c.description,
         c.cs, c.plate_x_mid, c.plate_z_mid, c.sz_top_h, c.sz_bot_h,
         c.batter_height_in, c.height_source, c.official_date,
         b.h_roster_in
  FROM main_marts.v_called_pitch_open c
  LEFT JOIN (SELECT batter, season, h_roster_in FROM main_marts.dim_batter_season
             WHERE level = 'mlb' AND analysis_set = 'open') b
    ON b.batter = c.batter AND b.season = c.season
  WHERE c.level = 'mlb' AND c.game_type = 'R'
    AND c.plate_x_mid IS NOT NULL AND c.plate_z_mid IS NOT NULL")
record("called pitches with coordinates read into R: ", fmt_n(nrow(cp)))

# Position players, from the people endpoint.
pos <- NULL
clause("pitcher positions fetched", {
  ids <- sort(unique(as.numeric(cp$pitcher)))
  batches <- split(ids, ceiling(seq_along(ids) / 100))
  rows <- list()
  for (b in batches) {
    url <- sprintf(PEOPLE_URL, paste(format(b, scientific = FALSE, trim = TRUE), collapse = ","))
    res <- absump_http_get(url)
    if (!identical(as.integer(res$status_code), 200L)) {
      stop("people endpoint returned HTTP ", res$status_code)
    }
    people <- jsonlite::fromJSON(rawToChar(res$content), simplifyVector = FALSE)$people
    for (p in people) {
      abbr <- if (is.null(p$primaryPosition$abbreviation)) NA_character_ else p$primaryPosition$abbreviation
      rows[[length(rows) + 1L]] <- data.frame(pitcher = as.numeric(p$id), position = abbr,
                                              name = p$fullName, stringsAsFactors = FALSE)
    }
  }
  pos <<- do.call(rbind, rows)
  unresolved <- setdiff(ids, pos$pitcher)
  check(length(unresolved) == 0L && !anyNA(pos$position),
        "pitcher positions: every pitcher id resolved by the people endpoint",
        sprintf(" (%d pitchers in %d requests, %d unresolved)", length(ids),
                length(batches), length(unresolved)))
})
if (is.null(pos)) {
  cat("FAIL    no pitcher positions; P0 cannot be built\n")
  finish(1L)
}
roles <- NULL
clause("pitcher roles by season", {
  roles <<- pitcher_season_roles(data.frame(season = cp$season, pitcher = as.numeric(cp$pitcher)), pos)
  src <- table(sub(" \\(.*$", "", roles$role_source))
  check(!anyNA(roles$role), "pitcher roles: every pitcher-season resolved to the role held that season",
        sprintf(" (%d pitcher-seasons: %s)", nrow(roles),
                paste(sprintf("%d from the %s", as.vector(src), names(src)), collapse = "; ")))
})
if (is.null(roles) || anyNA(roles$role)) {
  cat("FAIL    no pitcher role for every pitcher-season; P0 cannot be built\n")
  finish(1L)
}
role_key <- paste(roles$season, roles$pitcher)
cp$position_player <- roles$position_player[match(paste(cp$season, as.numeric(cp$pitcher)), role_key)]
today_pp <- !(pos$position[match(roles$pitcher, pos$pitcher)] %in% PITCHER_POS)
moved <- roles[roles$position_player != today_pp, ]
record(sprintf("pitcher-seasons whose role then differs from today's primary position: %d%s", nrow(moved),
               if (nrow(moved)) paste0(" (", paste(sprintf("%s %d, %s then, %s today, %s pitches",
                 pos$name[match(moved$pitcher, pos$pitcher)], moved$season, moved$role,
                 pos$position[match(moved$pitcher, pos$pitcher)],
                 fmt_n(vapply(seq_len(nrow(moved)), function(k) sum(cp$season == moved$season[k] &
                   as.numeric(cp$pitcher) == moved$pitcher[k]), 0L))), collapse = "; "), ")") else ""))
pp_keys <- role_key[roles$position_player]
x_pp_df <- aggregate(list(n = cp$position_player), list(season = cp$season), sum)
pp_rows <- cp[cp$position_player, ]
pp_speed <- q(sprintf("
  SELECT quantile_cont(release_speed, 0.5) AS med, quantile_cont(release_speed, 0.9) AS p90,
         count(*) FILTER (WHERE release_speed >= 85) AS n85, count(*) AS n
  FROM main_marts.v_called_pitch_open
  WHERE level = 'mlb' AND game_type = 'R' AND plate_x_mid IS NOT NULL
    AND (CAST(season AS VARCHAR) || ' ' || CAST(pitcher AS VARCHAR)) IN (%s)",
  if (length(pp_keys)) paste0("'", pp_keys, "'", collapse = ",") else "NULL"))
record(sprintf("position players: %d pitchers, %s called pitches, release speed median %.1f mph, p90 %.1f mph, %d at 85 mph or more",
               length(unique(pp_rows$pitcher)), fmt_n(nrow(pp_rows)),
               pp_speed$med, pp_speed$p90, pp_speed$n85))
x_pp <- counts_row("sample", "X_position_player",
                   "excluded: pitches thrown by position players",
                   x_pp_df,
                   note = sprintf("%d pitchers who held a position other than P or TWP in the season they pitched; release speed median %.1f mph; courtesy strikes on slow lobs, which TapToChallenge also excludes",
                                  length(unique(pp_rows$pitcher)), pp_speed$med))
twp <- pos[pos$position == "TWP", ]
if (nrow(twp)) record("two-way players kept as pitchers: ", paste(twp$name, collapse = ", "))

p0 <- cp[!cp$position_player, ]
blocked <- aggregate(list(n = p0$description == "blocked_ball"), list(season = p0$season), sum)
counts_row("sample", "K_blocked_ball", "retained: blocked_ball kept as a genuine ball call",
           blocked, note = "counted, not removed; it stays in P0 and P1 as a ball")
p0_df <- aggregate(list(n = rep(1L, nrow(p0))), list(season = p0$season), sum)
p0_v <- counts_row("sample", "P0",
                   "P0: called pitches, game_type R, official date 2022-01-01 to the last open day, non-null re-projected coordinates, position players removed",
                   p0_df, expected = "about 1.85M",
                   note = "the framing surface's sample")
x_h_df <- aggregate(list(n = p0$height_source != "abs_measured" | is.na(p0$height_source)),
                    list(season = p0$season), sum)
counts_row("sample", "X_not_abs_measured",
           "excluded from P1: batter height not ABS-measured",
           x_h_df, note = "height_source people_offset; roster height plus offset covers these rows")
p1 <- p0[!is.na(p0$height_source) & p0$height_source == "abs_measured", ]
p1_df <- aggregate(list(n = rep(1L, nrow(p1))), list(season = p1$season), sum)
p1_v <- counts_row("sample", "P1", "P1: P0 restricted to the ABS-measured-height cohort",
                   p1_df, expected = "about 1.20M",
                   note = "SOP W3.5 names P1 the primary sample and the <<N_CALLED>> count; DECISIONS.md D-R0-02 (owner answer) makes roster height plus offset primary and the ABS-measured cohort a robustness arm")

# Waterfall arithmetic, season by season.
removed <- list(x_gt, x_post, x_ab, x_po, x_hbp, x_as, x_sw)
for (s in as.character(SEASONS)) {
  called_s <- start[[s]] - sum(vapply(removed, function(v) v[[s]], 0))
  check(called_s == called[[s]],
        sprintf("waterfall %s: all pitches less the non-called rows equals the called count", s),
        sprintf(" (%s)", fmt_n(called[[s]])))
  p0_s <- called[[s]] - x_blank[[s]] - x_pp[[s]]
  check(p0_s == p0_v[[s]],
        sprintf("waterfall %s: called less blank coordinates less position players equals P0", s),
        sprintf(" (%s)", fmt_n(p0_v[[s]])))
}

# P0 and P1 by an independent route, in SQL.
indep <- q(sprintf("
  SELECT count(*) AS p0,
         count(*) FILTER (WHERE height_source = 'abs_measured') AS p1,
         count(*) FILTER (WHERE description NOT IN ('called_strike','ball','blocked_ball')) AS not_called
  FROM main_marts.v_called_pitch_open
  WHERE level = 'mlb' AND game_type = 'R'
    AND plate_x_mid IS NOT NULL AND plate_z_mid IS NOT NULL
    AND (CAST(season AS VARCHAR) || ' ' || CAST(pitcher AS VARCHAR)) NOT IN (%s)",
  if (length(pp_keys)) paste0("'", pp_keys, "'", collapse = ",") else "''"))
check(indep$p0 == nrow(p0), "P0 recounted in SQL matches the waterfall", sprintf(" (%s)", fmt_n(nrow(p0))))
check(indep$p1 == nrow(p1), "P1 recounted in SQL matches the waterfall", sprintf(" (%s)", fmt_n(nrow(p1))))
check(indep$not_called == 0L && all(p0$description %in% CALLED),
      "P0 holds only called_strike, ball and blocked_ball")
check(!anyNA(p0$plate_x_mid) && !anyNA(p0$plate_z_mid), "P0 has no blank re-projected coordinate")
check(all(p1$height_source == "abs_measured") &&
        nrow(p1) + sum(unlist(by_season(x_h_df))) == nrow(p0),
      "P1 is P0 less the rows without an ABS-measured height",
      sprintf(" (%s + %s = %s)", fmt_n(nrow(p1)), fmt_n(sum(unlist(by_season(x_h_df)))), fmt_n(nrow(p0))))
check(max(p0$official_date) <= lay$last_open, "P0 ends on or before the last open day",
      sprintf(" (%s)", format(max(p0$official_date))))

# ============================================================ 3. bands
cat("-- bands\n")
top_ft <- abs_top_ft(p0$batter_height_in)
bot_ft <- abs_bot_ft(p0$batter_height_in)
dev_top <- max(abs(top_ft - p0$sz_top_h))
dev_bot <- max(abs(bot_ft - p0$sz_bot_h))
check(dev_top < 1e-12 && dev_bot < 1e-12,
      "harmonised zone: abs_top_ft(H) and abs_bot_ft(H) reproduce sz_top_h and sz_bot_h",
      sprintf(" (max %.1e ft, %.1e ft)", dev_top, dev_bot))
p0$d <- signed_edge_in(p0$plate_x_mid, p0$plate_z_mid, top_ft, bot_ft)
p0$in8 <- abs(p0$d) <= BAND_SURF
p0$in3 <- abs(p0$d) <= BAND_SHADOW
p0$p1 <- !is.na(p0$height_source) & p0$height_source == "abs_measured"

agg <- function(x, g = p0$season) {
  a <- aggregate(list(n = x), list(season = g), sum)
  by_season(a)
}
in8 <- agg(p0$in8)
in3 <- agg(p0$in3)
in8_p1 <- agg(p0$in8 & p0$p1)
add_row("band", "B_d8_P0", "P0 rows with |d| <= 8.0 in on the harmonised zone (surface fit)",
        "pitches", lapply(in8, fmt_plain), fmt_plain(sum(unlist(in8))),
        expected = "about 240k per season, about 1.2M in all",
        note = "a surface-fit restriction; the framing model uses the unrestricted sample")
add_row("band", "B_d8_P0_pct", "share of P0 with |d| <= 8.0 in",
        "percent", setNames(lapply(SEASONS, function(s) pct(in8[[as.character(s)]], p0_v[[as.character(s)]])), SEASONS),
        pct(sum(unlist(in8)), nrow(p0)),
        expected = "65.9 (2024) | 66.9 (2025) | 64.8 (2026)",
        note = "d is the ball-centre distance from R/lib/zone.R signed_edge_in on the mid-plate plane, no radius")
add_row("band", "B_d8_P1", "P1 rows with |d| <= 8.0 in",
        "pitches", lapply(in8_p1, fmt_plain), fmt_plain(sum(unlist(in8_p1))))
add_row("band", "B_d3_P0", "P0 rows with |d| <= 3.0 in (shadow band)",
        "pitches", lapply(in3, fmt_plain), fmt_plain(sum(unlist(in3))),
        expected = "about 103k per season",
        note = "a reporting region and a sensitivity factor, not a filter on P0 or P1")
add_row("band", "B_d3_P0_pct", "share of P0 with |d| <= 3.0 in",
        "percent", setNames(lapply(SEASONS, function(s) pct(in3[[as.character(s)]], p0_v[[as.character(s)]])), SEASONS),
        pct(sum(unlist(in3)), nrow(p0)),
        expected = "27.7 to 28.7")
dev <- p0[p0$in3 & p0$season %in% DEV_SEASONS, ]
cs_dev <- aggregate(list(cs = dev$cs), list(season = dev$season), mean)
cs_vals <- setNames(as.list(rep(NA, length(SEASONS))), SEASONS)
for (i in seq_len(nrow(cs_dev))) cs_vals[[as.character(cs_dev$season[i])]] <- sprintf("%.2f", 100 * cs_dev$cs[i])
add_row("band", "B_d3_cs_rate", "called-strike rate inside |d| <= 3.0 in, P0",
        "percent", cs_vals, NA,
        expected = "66 to 72",
        note = "2022-2024 only; the 2025 and 2026 cells stay empty until the prereg-v1 tag, because this is the raw form of the pre-registered shadow_rate")
for (s in as.character(SEASONS)) {
  record(sprintf("band %s: |d|<=8 %s of P0 (%s%%), |d|<=3 %s (%s%%)", s,
                 fmt_n(in8[[s]]), pct(in8[[s]], p0_v[[s]]), fmt_n(in3[[s]]), pct(in3[[s]], p0_v[[s]])))
}
record("shadow-band called-strike rate, development seasons only: ",
       paste(sprintf("%d %.2f%%", cs_dev$season, 100 * cs_dev$cs), collapse = ", "))

# ============================================================ 4. sizes
games <- aggregate(list(n = p0$game_pk), list(season = p0$season), function(x) length(unique(x)))
g_v <- by_season(games)
add_row("size", "Z_games", "games with at least one P0 pitch", "games",
        lapply(g_v, fmt_plain), fmt_plain(length(unique(p0$game_pk))),
        expected = "about 2,430 per full season",
        note = "2026 runs to the last open day only")
add_row("size", "Z_per_game", "P0 called pitches per game", "pitches",
        setNames(lapply(SEASONS, function(s) sprintf("%.1f", p0_v[[as.character(s)]] / g_v[[as.character(s)]])), SEASONS),
        sprintf("%.1f", nrow(p0) / length(unique(p0$game_pk))),
        expected = "152.1")

# ============================================================ 5. cohorts
roster <- agg(!is.na(p0$h_roster_in))
add_row("cohort", "H_abs_measured", "P0 rows in the ABS-measured-height cohort (P1)", "percent",
        setNames(lapply(SEASONS, function(s) pct(p1_v[[as.character(s)]], p0_v[[as.character(s)]])), SEASONS),
        pct(nrow(p1), nrow(p0)))
add_row("cohort", "H_roster_offset", "P0 rows whose batter has a roster height (roster plus offset cohort)",
        "percent",
        setNames(lapply(SEASONS, function(s) pct(roster[[as.character(s)]], p0_v[[as.character(s)]])), SEASONS),
        pct(sum(unlist(roster)), nrow(p0)),
        note = "D-R0-02: this cohort is primary for every season")
check(sum(unlist(roster)) == nrow(p0), "roster height plus offset covers every P0 row",
      sprintf(" (%s of %s)", fmt_n(sum(unlist(roster))), fmt_n(nrow(p0))))

# ============================================================ 6. umpire panel
ug <- q("
  SELECT u.season, u.hp_umpire_id, count(*) AS games
  FROM main_marts.dim_umpire_game u
  JOIN main_marts.dim_game g ON g.game_pk = u.game_pk
  WHERE u.level = 'mlb' AND u.analysis_set = 'open'
    AND g.analysis_set = 'open' AND g.game_type = 'R'
  GROUP BY 1, 2")
wide <- tapply(ug$games, list(ug$hp_umpire_id, ug$season), sum)
wide[is.na(wide)] <- 0L
panel <- as.integer(rownames(wide)[apply(wide[, as.character(SEASONS), drop = FALSE] >= PANEL_GAMES, 1, all)])
ump_p0 <- aggregate(list(n = p0$umpire_hp_id), list(season = p0$season), function(x) length(unique(x)))
add_row("panel", "U_umpires", "home-plate umpires with a P0 pitch", "umpires",
        lapply(by_season(ump_p0), fmt_plain), fmt_plain(length(unique(p0$umpire_hp_id))))
add_row("panel", "U_panel", sprintf("balanced panel: umpires with >= %d home-plate games in every season 2022-2026", PANEL_GAMES),
        "umpires", setNames(as.list(rep(length(panel), length(SEASONS))), SEASONS), length(panel),
        note = "CH1-A14 robustness row; controls for crew turnover")
in_panel <- p0$umpire_hp_id %in% panel
pan_p0 <- agg(in_panel)
pan_p1 <- agg(in_panel & p0$p1)
add_row("panel", "U_panel_P0", "P0 rows called by balanced-panel umpires", "pitches",
        lapply(pan_p0, fmt_plain), fmt_plain(sum(unlist(pan_p0))))
add_row("panel", "U_panel_P1", "P1 rows called by balanced-panel umpires", "pitches",
        lapply(pan_p1, fmt_plain), fmt_plain(sum(unlist(pan_p1))))
check(length(panel) > 0L && sum(unlist(pan_p0)) < nrow(p0),
      "balanced umpire panel is non-empty and smaller than P0",
      sprintf(" (%d umpires, %s P0 rows)", length(panel), fmt_n(sum(unlist(pan_p0)))))

# ============================================================ write
tab <- as.data.frame(do.call(rbind, T1), stringsAsFactors = FALSE)
tab <- cbind(order = seq_len(nrow(tab)), tab)
check(!anyDuplicated(tab$row_id), "T1 row ids are unique", sprintf(" (%d rows)", nrow(tab)))
dir.create(dirname(OUT_CSV), recursive = TRUE, showWarnings = FALSE)
tmp <- tempfile(fileext = ".csv")
utils::write.table(tab, tmp, sep = ",", row.names = FALSE, col.names = TRUE,
                   qmethod = "double", na = "", fileEncoding = "UTF-8", eol = "\n")
new_bytes <- readBin(tmp, "raw", file.info(tmp)$size)
old_bytes <- if (file.exists(OUT_CSV)) readBin(OUT_CSV, "raw", file.info(OUT_CSV)$size) else raw(0)
if (!identical(new_bytes, old_bytes)) {
  file.copy(tmp, OUT_CSV, overwrite = TRUE)
  record("wrote ", OUT_CSV, " (", length(new_bytes), " bytes)")
} else {
  record(OUT_CSV, " unchanged (", length(new_bytes), " bytes)")
}
unlink(tmp)

record(sprintf("P0 %s rows, P1 %s rows (%s%% of P0)", fmt_n(nrow(p0)), fmt_n(nrow(p1)),
               pct(nrow(p1), nrow(p0))))
cat(sprintf("W3.5: %d PASS, %d FAIL\n", n_pass, n_fail))
finish(if (n_fail == 0L) 0L else 1L)
