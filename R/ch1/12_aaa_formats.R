#!/usr/bin/env Rscript
# R/ch1/12_aaa_formats.R - SOP step W3.9, AAA format classification.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/12_aaa_formats.R           scan every AAA feed on disk, classify each game,
#                                            write the four tables below, run the SOP tests
#   Rscript R/ch1/12_aaa_formats.R --check   recompute on exactly the games T5 lists, compare
#                                            with the files on disk, run the SOP tests, write
#                                            nothing
#
# WHAT IT MEASURES. For every AAA regular-season game whose GUMBO feed is on disk:
#
#   has_abs_challenges  presence of the absChallenges key in gameData, and nothing else
#   agree               mean(called_strike == zone_pred) over the game's called pitches
#
# A called pitch is a pitch event whose call code is B, *B or C. called_strike is the
# umpire's call: the published call, flipped back where an MJ review overturned it. An
# MJ review on playEvents[].reviewDetails belongs to that pitch; one on
# allPlays[].reviewDetails belongs to the play's last pitch (W2.16's rule); reviews
# nested under additionalReviews count with their parent. On a full-ABS day there are
# no reviews, so the umpire's call is the machine's call.
#
# THE ZONE. zone_pred is D-14's rule from R/lib/zone.R: the pitch re-projected from the
# front plane (the Stats API pX, pZ) to the mid-plate plane, then any part of the ball,
# r = 1.45 in, inside the published zone, Euclidean at the corners. The zone is the one
# the feed publishes on the pitch, pitchData.strikeZoneTop and strikeZoneBottom. It is
# used only where it is a machine rule zone: bottom 27% of height and top 51% or 53.5%
# of height, read from the ratio bottom/top to within 0.002 of the top fraction. The
# feed publishes 27/51 on AAA 2023 pitches and 27/53.5 on AAA 2024 pitches, so the
# machine zone changed between the two seasons. Where the feed publishes some other zone
# on a pitch (on an ABS-down day the umpire works the older rulebook zone and the feed
# says so), the pitch is scored against the machine zone that batter carries that season:
# his height from his published rule-zone pitches, and the top fraction in force that day.
# A pitch without the full kinematics, or without such a height, is counted, not scored.
#
# THE CLASS. The cut is the SOP's own number and is not tuned to these data:
#
#   unclassified   fewer than 50 scored called pitches
#   full_abs       agree >= 0.99 (SOP: a full-ABS game has agree of about 0.99 or more)
#   human_called   agree < 0.99
#
# The weekday is written as a descriptive column and read by nothing. signal_conflict
# marks a game with the absChallenges key and agree >= 0.99.
#
# THE SOP TESTS, each a PASS, FAIL or PENDING line. PENDING is a clause the corpus on
# disk cannot evaluate yet; it is not a pass and it is not a failure.
#
#   S1  the agree histogram is bimodal with a gap >= 0.04: both classes present, and the
#       widest empty interval between consecutive agree values that lies between the
#       two class medians is at least 0.04 wide
#   S2  every game classified full_abs has has_abs_challenges == FALSE
#   S3  the classification matches the six AAA data-contract games (722770, 723056,
#       752975, 752300, 753191, 780583): the key and both MJ counts as the contract
#       states them, and a game with the key is not classed full_abs
#   S4  the machine-day 50% contour area is stable across 2023, 2024 and 2025 to within
#       2 sq in. Machine days are full_abs games without the key. The area is for a
#       6-ft batter: x in inches, z as a share of height times 72 in, 1-inch cells over
#       x in [-16, 16) and z in [10, 48), area = sum over cells of the cell's called
#       strike rate. That sum is the area of the 50% contour when the edge is sharp, and
#       nothing is fitted. A season is evaluable with at least 20 machine-day games and
#       3,000 scored pitches. 2025 is not read for S4 until the prereg-v1 tag exists,
#       because this phase fits nothing on 2025 before the tag.
#
# D-11 AND D-57. out/tables/aaa_changeover.csv carries one row each. D-11 counts the
# 2023 games carrying the absChallenges key; it is settled when every Final 2023 game
# has been scanned. D-57 is the first Tue/Wed/Thu 2024 game carrying the key; it is
# settled when such a game is found and every Final Tue/Wed/Thu game before it has been
# scanned. Until then the row states the lower bound the scan supports.
#
# READS. The AAA feeds in the raw lake (data/raw/statsapi/feed/sport=11/...), and the
# staging cache (data/staging/statsapi/feeds/sport11/...) for any game the lake does not
# hold yet. The AAA schedule in data/interim/schedule_game/level=aaa. Nothing else.
#
# WRITES, each only when its content changes, so a second run leaves the tree as the
# first run left it:
#
#   out/ch1/tab/T5_aaa_formats.csv   one row per Final regular-season game on disk: the
#                                    counts, agree on the umpire's call, agree_final on
#                                    the published call, and the class
#   out/tables/aaa_regime_scan.csv   one row per game: the SOP W2.8 scan columns
#   out/tables/aaa_changeover.csv    the D-11 and D-57 results
#   out/tables/aaa_format.csv        the rule-version table. This script appends or
#                                    replaces only rows whose source begins "W3.9"; a
#                                    row any other step wrote is kept byte for byte
#
# Exit 0 when every comparison holds and every evaluable SOP test passes, 1 otherwise,
# 2 on a usage error.

options(warn = 1, digits = 12)
t_start <- Sys.time()

args_all <- commandArgs(trailingOnly = FALSE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1 || (length(args) == 1 && !identical(args, "--check"))) {
  cat("usage: Rscript R/ch1/12_aaa_formats.R [--check]\n", file = stderr())
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

source("R/lib/zone.R")

## --- the checks -----------------------------------------------------------------

n_pass <- 0L
n_pending <- 0L
failures <- character(0)
check <- function(label, ok, detail) {
  if (isTRUE(ok)) {
    n_pass <<- n_pass + 1L
    cat(sprintf("PASS    %-44s %s\n", label, detail))
  } else {
    failures <<- c(failures, sprintf("%s -- %s", label, detail))
    cat(sprintf("FAIL    %-44s %s\n", label, detail))
  }
}
pending <- function(label, detail) {
  n_pending <<- n_pending + 1L
  cat(sprintf("PENDING %-44s %s\n", label, detail))
}
record <- function(label, detail) cat(sprintf("RECORD  %-44s %s\n", label, detail))
comma <- function(x) formatC(as.numeric(x), format = "d", big.mark = ",")
f4 <- function(x) sprintf("%.4f", x)
finish <- function() {
  cat(sprintf("W3.9 %s: %d PASS, %d FAIL, %d PENDING, %.1f s\n",
              if (CHECK_ONLY) "check" else "build", n_pass, length(failures), n_pending,
              as.numeric(difftime(Sys.time(), t_start, units = "secs"))))
  if (length(failures) > 0) {
    cat("FAILED CLAUSES:\n", paste0("  ", failures, "\n"), sep = "")
    quit(status = 1)
  }
  quit(status = 0)
}

## --- constants --------------------------------------------------------------------

CUT_FULL_ABS    <- 0.99     # SOP W3.9: a full-ABS game has agree of about 0.99 or more
GAP_MIN         <- 0.04     # SOP W3.9: bimodal with a gap >= 0.04
AREA_TOL_SQIN   <- 2        # SOP W3.9: contour area stable to within 2 sq in
MIN_SCORED      <- 50L      # fewer scored called pitches than this: unclassified
BOT_FRAC        <- ABS_BOT_FRAC                 # 0.27, from R/lib/zone.R
RULE_TOP_FRACS  <- c(0.510, ABS_TOP_FRAC)       # 27/51 (AAA 2023), 27/53.5 (AAA 2024)
RULE_TOL        <- 0.002
CALLED_CODES    <- c("B", "*B", "C")
REF_HEIGHT_IN   <- 72       # contour areas are for a 6-ft batter (SOP section 11)
GRID_X          <- c(-16L, 16L)
GRID_Z          <- c(10L, 48L)
MIN_SEASON_GAMES   <- 20L
MIN_SEASON_PITCHES <- 3000L
BAND_IN         <- 0.5
FAR_IN          <- 2
SPORT_ID        <- 11L
TUE_THU         <- c("Tuesday", "Wednesday", "Thursday")
WEEKDAYS        <- c("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                     "Saturday")
# The AAA rows of the data contract, research/sop-ground-data-contract.md section 6.
CONTRACT <- data.frame(
  game_pk            = c(722770L, 723056L, 752975L, 752300L, 753191L, 780583L),
  has_abs_challenges = c(FALSE, FALSE, TRUE, TRUE, TRUE, TRUE),
  n_mj_event         = c(0L, 0L, 1L, 4L, 3L, 2L),
  n_mj_play          = c(0L, 0L, 2L, 2L, 2L, 2L)
)
SOURCE_TAG <- "W3.9"

T5_FILE       <- file.path(ROOT, "out", "ch1", "tab", "T5_aaa_formats.csv")
SCAN_FILE     <- file.path(ROOT, "out", "tables", "aaa_regime_scan.csv")
CHANGE_FILE   <- file.path(ROOT, "out", "tables", "aaa_changeover.csv")
FORMAT_FILE   <- file.path(ROOT, "out", "tables", "aaa_format.csv")
T5_REL        <- "out/ch1/tab/T5_aaa_formats.csv"
SCAN_REL      <- "out/tables/aaa_regime_scan.csv"

## --- layout from absump.paths ---------------------------------------------------------

paths_from_python <- function() {
  code <- "from absump.paths import data_root; print(data_root())"
  out <- suppressWarnings(system2(
    "uv", c("run", "--locked", "python", "-c", shQuote(code)),
    stdout = TRUE, stderr = TRUE
  ))
  status <- attr(out, "status")
  if (is.null(status)) status <- 0L
  if (status != 0L || length(out) < 1L) {
    stop("could not read the layout from absump.paths (exit ", status, "): ",
         paste(out, collapse = " "), call. = FALSE)
  }
  trimws(out[length(out)])
}
DATA <- paths_from_python()
LAKE_ROOT     <- file.path(DATA, "raw", "statsapi", "feed", sprintf("sport=%d", SPORT_ID))
STAGING_ROOT  <- file.path(DATA, "staging", "statsapi", "feeds", sprintf("sport%d", SPORT_ID))
SCHEDULE_ROOT <- file.path(DATA, "interim", "schedule_game", "level=aaa")
record("layout", sprintf("lake %s; staging %s", LAKE_ROOT, STAGING_ROOT))
check("AAA schedule present", dir.exists(SCHEDULE_ROOT), SCHEDULE_ROOT)
if (CHECK_ONLY) {
  for (f in c(T5_FILE, SCAN_FILE, CHANGE_FILE, FORMAT_FILE)) {
    check("file present for comparison", file.exists(f), f)
  }
}
if (length(failures) > 0) finish()

prereg_tagged <- local({
  st <- suppressWarnings(system2("git", c("-C", shQuote(ROOT), "rev-parse", "-q", "--verify",
                                          "refs/tags/prereg-v1"), stdout = FALSE, stderr = FALSE))
  identical(as.integer(st), 0L)
})
record("prereg-v1 tag", if (prereg_tagged) "present" else "absent: 2025 is not read for S4")

## --- 1. the schedule -------------------------------------------------------------------

sched_files <- sort(list.files(SCHEDULE_ROOT, pattern = "\\.parquet$", recursive = TRUE,
                               full.names = TRUE))
sched <- do.call(rbind, lapply(sched_files, function(f) as.data.frame(arrow::read_parquet(
  f, col_select = c("game_pk", "season", "game_type", "official_date", "status_coded")))))
sched$game_pk <- as.integer(sched$game_pk)
sched$season <- as.integer(sched$season)
sched$official_date <- as.Date(sched$official_date)
final_r <- sched[sched$game_type == "R" & sched$status_coded == "F", ]
record("schedule, Final regular-season games",
       paste(sprintf("%d: %s", sort(unique(final_r$season)),
                     comma(table(final_r$season)[as.character(sort(unique(final_r$season)))])),
             collapse = "; "))

## --- 2. the feeds on disk ----------------------------------------------------------------

list_feeds <- function() {
  lake <- list.files(LAKE_ROOT, pattern = "^gamepk=[0-9]+\\.json\\.zst$", recursive = TRUE,
                     full.names = TRUE)
  staged <- list.files(STAGING_ROOT, pattern = "^[0-9]+\\.json$", recursive = TRUE,
                       full.names = TRUE)
  a <- data.frame(
    game_pk = as.integer(sub("^gamepk=([0-9]+)\\.json\\.zst$", "\\1", basename(lake))),
    path = lake, source = rep("lake", length(lake)), stringsAsFactors = FALSE
  )
  b <- data.frame(
    game_pk = as.integer(sub("\\.json$", "", basename(staged))),
    path = staged, source = rep("staging", length(staged)), stringsAsFactors = FALSE
  )
  b <- b[!(b$game_pk %in% a$game_pk), ]
  out <- rbind(a, b)
  out[order(out$game_pk), ]
}
feeds <- list_feeds()
record("feeds on disk", sprintf("%s in the lake, %s in staging only",
                                comma(sum(feeds$source == "lake")),
                                comma(sum(feeds$source == "staging"))))

if (CHECK_ONLY) {
  t5_disk <- utils::read.csv(T5_FILE, colClasses = "character")
  want <- as.integer(t5_disk$game_pk)
  missing_feed <- setdiff(want, feeds$game_pk)
  check("every T5 game has a feed on disk", length(missing_feed) == 0,
        sprintf("%s games in T5, %d without a feed", comma(length(want)), length(missing_feed)))
  if (length(missing_feed) > 0) finish()
  extra <- setdiff(feeds$game_pk, want)
  record("feeds on disk that T5 does not list", sprintf(
    "%s (the corpus grew since the build; a build run takes them in)", comma(length(extra))))
  feeds <- feeds[feeds$game_pk %in% want, ]
}

read_feed <- function(path) {
  if (grepl("\\.zst$", path)) {
    s <- arrow::CompressedInputStream$create(path, codec = arrow::Codec$create("zstd"))
    on.exit(s$close())
    parts <- list()
    repeat {
      r <- as.raw(s$Read(16e6))
      if (length(r) == 0) break
      parts[[length(parts) + 1L]] <- r
    }
    txt <- rawToChar(do.call(c, parts))
  } else {
    txt <- rawToChar(readBin(path, "raw", file.size(path)))
  }
  jsonlite::parse_json(txt, simplifyVector = FALSE)
}

num <- function(x) if (is.null(x)) NA_real_ else as.numeric(x)
int_or_na <- function(x) if (is.null(x)) NA_integer_ else as.integer(x)

walk_reviews <- function(r) {
  if (!is.list(r) || is.null(names(r))) return(list())
  out <- list(r)
  for (x in r$additionalReviews) out <- c(out, walk_reviews(x))
  out
}

rule_of <- function(top, bot) {
  frac <- BOT_FRAC * top / bot
  k <- vapply(frac, function(f) {
    if (is.na(f)) return(NA_real_)
    d <- abs(RULE_TOP_FRACS - f)
    if (min(d) <= RULE_TOL) RULE_TOP_FRACS[which.min(d)] else NA_real_
  }, numeric(1))
  k
}

scan_game <- function(feed) {
  gd <- feed$gameData
  game_pk <- as.integer(gd$game$pk)
  season <- as.integer(gd$game$season)
  game_type <- as.character(gd$game$type)
  official_date <- as.character(gd$datetime$officialDate)
  has_key <- "absChallenges" %in% names(gd)
  block <- gd$absChallenges

  n_ev <- 0L; n_pl <- 0L; n_ov <- 0L; n_ov_unplaced <- 0L
  snap <- list(away = integer(0), home = integer(0))
  take_snapshot <- function(r) {
    rc <- r$remainingChallenges
    if (is.list(rc)) for (side in c("away", "home")) {
      v <- int_or_na(rc[[side]])
      if (!is.na(v)) snap[[side]] <<- c(snap[[side]], v)
    }
  }

  cap <- 1200L
  code <- character(cap); flip <- logical(cap); batter <- rep(NA_integer_, cap)
  top <- bot <- px <- pz <- vx0 <- vy0 <- vz0 <- ax <- ay <- az <- rep(NA_real_, cap)
  k <- 0L

  for (play in feed$liveData$plays$allPlays) {
    bat <- int_or_na(play$matchup$batter$id)
    evs <- play$playEvents
    if (length(evs) == 0) evs <- list()
    is_p <- vapply(evs, function(e) isTRUE(e$isPitch), logical(1))
    fl <- logical(length(evs))
    last <- if (any(is_p)) max(which(is_p)) else NA_integer_
    for (r in walk_reviews(play$reviewDetails)) {
      take_snapshot(r)
      if (identical(r$reviewType, "MJ")) {
        n_pl <- n_pl + 1L
        if (isTRUE(r$isOverturned)) {
          n_ov <- n_ov + 1L
          if (is.na(last)) n_ov_unplaced <- n_ov_unplaced + 1L else fl[last] <- TRUE
        }
      }
    }
    for (i in seq_along(evs)) {
      for (r in walk_reviews(evs[[i]]$reviewDetails)) {
        take_snapshot(r)
        if (identical(r$reviewType, "MJ")) {
          n_ev <- n_ev + 1L
          if (isTRUE(r$isOverturned)) {
            n_ov <- n_ov + 1L
            if (is_p[i]) fl[i] <- TRUE else n_ov_unplaced <- n_ov_unplaced + 1L
          }
        }
      }
    }
    for (i in which(is_p)) {
      ev <- evs[[i]]
      cd <- ev$details$call$code
      if (is.null(cd) || !(cd %in% CALLED_CODES)) next
      k <- k + 1L
      if (k > cap) stop(sprintf("game %d has more than %d called pitches", game_pk, cap))
      pd <- ev$pitchData
      co <- pd$coordinates
      code[k] <- cd; flip[k] <- fl[i]; batter[k] <- bat
      top[k] <- num(pd$strikeZoneTop); bot[k] <- num(pd$strikeZoneBottom)
      px[k] <- num(co$pX); pz[k] <- num(co$pZ)
      vx0[k] <- num(co$vX0); vy0[k] <- num(co$vY0); vz0[k] <- num(co$vZ0)
      ax[k] <- num(co$aX); ay[k] <- num(co$aY); az[k] <- num(co$aZ)
    }
  }
  s <- seq_len(k)
  p <- data.frame(code = code[s], flip = flip[s], batter = batter[s], top = top[s],
                  bot = bot[s], px = px[s],
                  pz = pz[s], vx0 = vx0[s], vy0 = vy0[s], vz0 = vz0[s], ax = ax[s],
                  ay = ay[s], az = az[s], stringsAsFactors = FALSE)

  # the starting allotment per side (D-12): play-by-play maximum, else the end block
  max_remaining <- NA_integer_
  if (is.list(block)) {
    per_side <- vapply(c("away", "home"), function(side) {
      if (length(snap[[side]]) > 0) return(as.integer(max(snap[[side]])))
      e <- block[[side]]
      uf <- int_or_na(e$usedFailed); rm <- int_or_na(e$remaining)
      if (is.na(uf) || is.na(rm)) NA_integer_ else uf + rm
    }, integer(1))
    if (any(!is.na(per_side))) max_remaining <- max(per_side, na.rm = TRUE)
  }

  list(game_pk = game_pk, season = season, game_type = game_type,
       official_date = official_date, has_key = has_key, n_mj_event = n_ev,
       n_mj_play = n_pl, n_mj_overturned = n_ov, n_overturn_unplaced = n_ov_unplaced,
       max_remaining = max_remaining, pitches = p)
}

modal <- function(x) {
  x <- x[!is.na(x)]
  if (length(x) == 0) return(NA_real_)
  tab <- table(x)
  as.numeric(names(tab)[which.max(tab)])
}

# Score every called pitch at once. The zone is the published one where it is a rule
# zone. Where the feed publishes some other zone (an ABS-down game, when the umpire calls
# the game on the older rulebook zone), the pitch is scored against the machine zone the
# batter carries in that season: his height from his published rule-zone pitches, bottom
# 27%, and the top fraction in force that day, else that season. A pitch with no such
# batter height is counted and not scored.
score_all <- function(P) {
  cs_final <- P$code == "C"
  cs <- xor(cs_final, P$flip)
  kin <- !is.na(P$px) & !is.na(P$pz) & !is.na(P$vx0) & !is.na(P$vy0) & !is.na(P$vz0) &
    !is.na(P$ax) & !is.na(P$ay) & !is.na(P$az)
  kin <- kin & ifelse(kin, P$vy0 < 0 & P$ay > 0, FALSE)
  pub <- kin & !is.na(P$top) & !is.na(P$bot)
  pub <- pub & ifelse(pub, P$top > P$bot & P$bot > 0, FALSE)
  rule_pub <- rep(NA_real_, nrow(P))
  rule_pub[pub] <- rule_of(P$top[pub], P$bot[pub])
  has_pub <- !is.na(rule_pub)

  h_pub <- P$bot[has_pub] * 12 / BOT_FRAC
  key_pub <- paste(P$season[has_pub], P$batter[has_pub])
  h_med <- tapply(h_pub, key_pub, stats::median)
  day_rule <- tapply(rule_pub[has_pub], P$official_date[has_pub], modal)
  season_rule <- tapply(rule_pub[has_pub], P$season[has_pub], modal)

  need <- kin & !has_pub & !is.na(P$batter)
  h <- rep(NA_real_, nrow(P))
  h[need] <- as.numeric(h_med[paste(P$season[need], P$batter[need])])
  r_day <- as.numeric(day_rule[P$official_date])
  r_sea <- as.numeric(season_rule[as.character(P$season)])
  r_fill <- ifelse(is.na(r_day), r_sea, r_day)
  from_batter <- need & !is.na(h) & !is.na(r_fill)

  rule <- ifelse(has_pub, rule_pub, ifelse(from_batter, r_fill, NA_real_))
  top <- ifelse(has_pub, P$top, ifelse(from_batter, r_fill * h / 12, NA_real_))
  bot <- ifelse(has_pub, P$bot, ifelse(from_batter, BOT_FRAC * h / 12, NA_real_))
  ok <- kin & !is.na(rule)
  e <- rep(NA_real_, nrow(P)); xm <- zm <- rep(NA_real_, nrow(P))
  if (any(ok)) {
    mid <- reproject(P$px[ok], P$pz[ok], P$vx0[ok], P$vy0[ok], P$vz0[ok], P$ax[ok], P$ay[ok],
                     P$az[ok], y_from = Y_FRONT_FT, y_to = Y_MID_FT)
    xm[ok] <- mid$x; zm[ok] <- mid$z
    e[ok] <- signed_edge_in(mid$x, mid$z, top[ok], bot[ok]) - BALL_R_IN
  }
  data.frame(game_pk = P$game_pk, season = P$season, cs = cs, cs_final = cs_final,
             tracked = kin, published_rule = has_pub, from_batter = from_batter & ok,
             rule = rule, scored = ok, e = e, x_in = xm * 12,
             z_ref = zm * REF_HEIGHT_IN * BOT_FRAC / bot, stringsAsFactors = FALSE)
}

## --- 3. scan and classify -------------------------------------------------------------------

metas <- vector("list", nrow(feeds))
plist <- vector("list", nrow(feeds))
unreadable <- character(0)
for (j in seq_len(nrow(feeds))) {
  g <- tryCatch(scan_game(read_feed(feeds$path[j])), error = function(e) {
    unreadable <<- c(unreadable, sprintf("%s (%s)", feeds$path[j], conditionMessage(e)))
    NULL
  })
  if (is.null(g)) next
  if (!identical(g$game_pk, feeds$game_pk[j])) {
    unreadable <- c(unreadable, sprintf("%s (feed says game %s)", feeds$path[j], g$game_pk))
    next
  }
  metas[[j]] <- data.frame(
    game_pk = g$game_pk, season = g$season, game_type = g$game_type,
    official_date = g$official_date,
    weekday = WEEKDAYS[as.POSIXlt(as.Date(g$official_date))$wday + 1L],
    has_abs_challenges = g$has_key, n_mj_event = g$n_mj_event, n_mj_play = g$n_mj_play,
    n_mj_overturned = g$n_mj_overturned, n_overturn_unplaced = g$n_overturn_unplaced,
    max_remaining = g$max_remaining, stringsAsFactors = FALSE
  )
  if (nrow(g$pitches) > 0) {
    plist[[j]] <- cbind(data.frame(game_pk = g$game_pk, season = g$season,
                                   official_date = g$official_date, stringsAsFactors = FALSE),
                        g$pitches)
  }
}
check("every feed on disk parses", length(unreadable) == 0,
      if (length(unreadable) == 0) sprintf("%s feeds", comma(nrow(feeds)))
      else paste(head(unreadable, 5), collapse = "; "))
gm <- do.call(rbind, metas[!vapply(metas, is.null, logical(1))])

# Only games the schedule records as Final regular-season games are AAA games here. A
# postponed or cancelled game can still have a feed, with no pitches, and sometimes with
# the absChallenges key; it is left out and counted.
not_final <- gm[!(gm$game_type == "R" & gm$game_pk %in% final_r$game_pk), ]
record("feeds left out, not Final regular season", sprintf(
  "%d (%s)", nrow(not_final), if (nrow(not_final) == 0) "none" else
    paste(sprintf("%d %s", not_final$game_pk, not_final$official_date), collapse = ", ")))
gm <- gm[gm$game_type == "R" & gm$game_pk %in% final_r$game_pk, ]
P <- do.call(rbind, plist[!vapply(plist, is.null, logical(1))])
P <- P[P$game_pk %in% gm$game_pk, ]
sc <- score_all(P)

per_game <- function(x) {
  v <- tapply(x, factor(sc$game_pk, levels = gm$game_pk), sum)
  as.integer(ifelse(is.na(v), 0L, v))
}
hit <- sc$scored & (sc$cs == (sc$e < 0))
hit_final <- sc$scored & (sc$cs_final == (sc$e < 0))
gm$n_called <- per_game(rep(1L, nrow(sc)))
gm$n_tracked <- per_game(sc$tracked)
gm$n_scored <- per_game(sc$scored)
gm$n_zone_from_batter <- per_game(sc$from_batter)
gm$n_agree <- per_game(hit)
gm$agree <- ifelse(gm$n_scored > 0, gm$n_agree / gm$n_scored, NA_real_)
gm$agree_final <- ifelse(gm$n_scored > 0, per_game(hit_final) / gm$n_scored, NA_real_)
tf_rule <- tapply(sc$rule[sc$scored], factor(sc$game_pk[sc$scored], levels = gm$game_pk), modal)
gm$zone_top_frac <- as.numeric(tf_rule)
px_all <- sc[sc$scored, c("game_pk", "season", "cs", "e", "x_in", "z_ref", "rule",
                          "published_rule")]

gm$format_class <- ifelse(gm$n_scored < MIN_SCORED, "unclassified",
                          ifelse(gm$agree >= CUT_FULL_ABS, "full_abs", "human_called"))
gm$signal_conflict <- gm$format_class == "full_abs" & gm$has_abs_challenges
gm <- gm[order(gm$season, gm$official_date, gm$game_pk), ]
rownames(gm) <- NULL

seasons_on_disk <- sort(unique(gm$season))
for (s in sort(unique(final_r$season))) {
  n_f <- sum(final_r$season == s)
  n_d <- sum(gm$season == s)
  span <- if (n_d > 0) sprintf(", %s to %s", min(gm$official_date[gm$season == s]),
                               max(gm$official_date[gm$season == s])) else ""
  record(sprintf("coverage %d", s), sprintf("%s of %s Final games on disk%s", comma(n_d),
                                            comma(n_f), span))
}
record("overturned MJ reviews with no pitch to flip",
       sprintf("%d", sum(gm$n_overturn_unplaced)))

## --- 4. the tables --------------------------------------------------------------------------

fmt6 <- function(x) ifelse(is.na(x), NA_character_, sprintf("%.6f", x))
fmt3 <- function(x) ifelse(is.na(x), NA_character_, sprintf("%.3f", x))
tf <- function(x) ifelse(x, "TRUE", "FALSE")

t5 <- data.frame(
  game_pk = gm$game_pk, season = gm$season, official_date = gm$official_date,
  weekday = gm$weekday, has_abs_challenges = tf(gm$has_abs_challenges),
  n_mj_event = gm$n_mj_event, n_mj_play = gm$n_mj_play, n_mj_overturned = gm$n_mj_overturned,
  n_called = gm$n_called, n_tracked = gm$n_tracked, n_scored = gm$n_scored,
  n_zone_from_batter = gm$n_zone_from_batter, zone_top_frac = fmt3(gm$zone_top_frac), n_agree = gm$n_agree, agree = fmt6(gm$agree),
  agree_final = fmt6(gm$agree_final), format_class = gm$format_class,
  signal_conflict = tf(gm$signal_conflict), stringsAsFactors = FALSE
)

scan <- data.frame(
  game_pk = gm$game_pk, season = gm$season, official_date = gm$official_date,
  weekday = gm$weekday, has_abs_challenges = tf(gm$has_abs_challenges),
  n_mj_event = gm$n_mj_event, n_mj_play = gm$n_mj_play, max_remaining = gm$max_remaining,
  stringsAsFactors = FALSE
)

# D-11: the 2023 challenge records. D-57: the first Tue/Wed/Thu 2024 game with the key.
d11 <- local({
  s <- 2023L
  sch <- final_r[final_r$season == s, ]
  g <- gm[gm$season == s, ]
  n_key <- sum(g$has_abs_challenges)
  settled <- nrow(g) > 0 && all(sch$game_pk %in% g$game_pk)
  first_key <- if (n_key > 0) min(g$official_date[g$has_abs_challenges]) else NA_character_
  last_no <- if (any(!g$has_abs_challenges)) max(g$official_date[!g$has_abs_challenges]) else
    NA_character_
  result <- if (settled) {
    if (n_key == 0) sprintf(paste0("absChallenges key on 0 of %s Final 2023 games: the ",
                                   "challenge arm is 2024-2025 only"), comma(nrow(sch)))
    else sprintf("absChallenges key on %s of %s Final 2023 games", comma(n_key),
                 comma(nrow(sch)))
  } else {
    sprintf(paste0("absChallenges key on %s of %s games scanned; %s Final 2023 games are ",
                   "not on disk yet, so the season count is open"), comma(n_key),
            comma(nrow(g)), comma(sum(!(sch$game_pk %in% g$game_pk))))
  }
  data.frame(decision = "D-11", level = "aaa", season = s,
             status = if (settled) "settled" else "open",
             n_final_scheduled = nrow(sch), n_scanned = nrow(g), n_with_key = n_key,
             first_key_date = first_key, last_no_key_date = last_no, result = result,
             evidence_path = SCAN_REL, stringsAsFactors = FALSE)
})
d57 <- local({
  s <- 2024L
  sch <- final_r[final_r$season == s, ]
  sch$weekday <- WEEKDAYS[as.POSIXlt(sch$official_date)$wday + 1L]
  sch <- sch[sch$weekday %in% TUE_THU, ]
  g <- gm[gm$season == s & gm$weekday %in% TUE_THU, ]
  n_key <- sum(g$has_abs_challenges)
  first_key <- if (n_key > 0) min(g$official_date[g$has_abs_challenges]) else NA_character_
  last_no <- if (any(!g$has_abs_challenges)) max(g$official_date[!g$has_abs_challenges]) else
    NA_character_
  # the last Tue/Wed/Thu date through which every scheduled Tue/Wed/Thu game is scanned
  dates <- sort(unique(sch$official_date))
  covered <- vapply(seq_along(dates), function(i) {
    all(sch$game_pk[sch$official_date == dates[i]] %in% g$game_pk)
  }, logical(1))
  run <- if (length(covered) > 0 && covered[1]) {
    dates[if (all(covered)) length(dates) else which(!covered)[1] - 1L]
  } else as.Date(NA)
  settled <- !is.na(first_key) &&
    all(sch$game_pk[sch$official_date < as.Date(first_key)] %in% g$game_pk)
  result <- if (settled) {
    sprintf(paste0("first Tue/Wed/Thu game with the absChallenges key is on %s; every ",
                   "earlier Final Tue/Wed/Thu game was scanned"), first_key)
  } else if (n_key == 0 && is.na(run)) {
    sprintf(paste0("absChallenges key on 0 of %s Tue/Wed/Thu games scanned; the opening ",
                   "Tue/Wed/Thu date is not fully on disk, so no bound is set"), comma(nrow(g)))
  } else if (n_key == 0) {
    sprintf(paste0("absChallenges key on 0 of %s Tue/Wed/Thu games scanned (%s to %s); ",
                   "every Final Tue/Wed/Thu game through %s is scanned, so the changeover ",
                   "is later than %s; the search of the rest of 2024 is open"),
            comma(nrow(g)), min(g$official_date), max(g$official_date), format(run),
            format(run))
  } else {
    sprintf(paste0("absChallenges key on %s of %s Tue/Wed/Thu games scanned, first on %s; ",
                   "earlier Tue/Wed/Thu games are not all on disk, so the date is an upper ",
                   "bound"), comma(n_key), comma(nrow(g)), first_key)
  }
  data.frame(decision = "D-57", level = "aaa", season = s,
             status = if (settled) "settled" else "open",
             n_final_scheduled = nrow(sch), n_scanned = nrow(g), n_with_key = n_key,
             first_key_date = first_key, last_no_key_date = last_no, result = result,
             evidence_path = SCAN_REL, stringsAsFactors = FALSE)
})
changeover <- rbind(d11, d57)

# The rule-version rows this scan settles. A zone rule is written for a season when the
# feed publishes it on the season's opening day; the 2024 weekly format is written when
# the opening week shows it. Nothing is written for a rule the scan has not settled.
fmt_rows <- list()
for (s in seasons_on_disk) {
  opening <- min(sched$official_date[sched$season == s & sched$game_type == "R" &
                                       sched$status_coded == "F"])
  g_open <- gm[gm$season == s & as.Date(gm$official_date) == opening, ]
  p_s <- px_all[px_all$season == s & px_all$published_rule, ]
  for (fr in RULE_TOP_FRACS) {
    on_open <- sum(p_s$rule[p_s$game_pk %in% g_open$game_pk] == fr)
    if (on_open == 0) next
    n_rule <- sum(p_s$rule == fr)
    days <- sort(unique(gm$official_date[gm$game_pk %in% unique(p_s$game_pk[p_s$rule == fr])]))
    fmt_rows[[length(fmt_rows) + 1L]] <- data.frame(
      level = "aaa", season = s,
      rule_version = sprintf("zone_top_%.3f_bot_%.3f", fr, BOT_FRAC),
      changeover_date = format(opening),
      source = sprintf(paste0("%s scan: statsapi feed pitchData.strikeZoneBottom/",
                              "strikeZoneTop gives top %.1f%% and bottom %.1f%% of height on ",
                              "%s of %s scored called pitches, opening day included, ",
                              "%s to %s"), SOURCE_TAG, 100 * fr, 100 * BOT_FRAC,
                       comma(n_rule), comma(nrow(p_s)), days[1], days[length(days)]),
      evidence_path = T5_REL, stringsAsFactors = FALSE)
  }
}
fmt_week <- local({
  s <- 2024L
  g <- gm[gm$season == s, ]
  if (nrow(g) == 0) return(NULL)
  opening <- min(final_r$official_date[final_r$season == s])
  wk <- g[as.Date(g$official_date) < opening + 7, ]
  mid <- wk$weekday %in% TUE_THU
  end <- wk$weekday %in% c("Friday", "Saturday", "Sunday")
  if (!any(mid) || !any(end)) return(NULL)
  if (any(wk$has_abs_challenges[mid]) || !all(wk$has_abs_challenges[end])) return(NULL)
  tt <- g[g$weekday %in% TUE_THU, ]
  fs <- g[g$weekday %in% c("Friday", "Saturday", "Sunday"), ]
  data.frame(
    level = "aaa", season = s,
    rule_version = "format_full_abs_tue_thu_challenge_fri_sun",
    changeover_date = format(opening),
    source = sprintf(paste0("%s scan: absChallenges key on 0 of %s Tue-Thu and %s of %s ",
                            "Fri-Sun games in the opening week; over %s to %s, key on %s of %s ",
                            "Tue-Thu and %s of %s Fri-Sun games; the end of this format is ",
                            "D-57, see out/tables/aaa_changeover.csv"), SOURCE_TAG,
                     sum(mid), sum(wk$has_abs_challenges[end]), sum(end),
                     min(g$official_date), max(g$official_date),
                     comma(sum(tt$has_abs_challenges)), comma(nrow(tt)),
                     comma(sum(fs$has_abs_challenges)), comma(nrow(fs))),
    evidence_path = SCAN_REL, stringsAsFactors = FALSE)
})
if (!is.null(fmt_week)) fmt_rows[[length(fmt_rows) + 1L]] <- fmt_week
mine <- if (length(fmt_rows) > 0) do.call(rbind, fmt_rows) else
  data.frame(level = character(0), season = integer(0), rule_version = character(0),
             changeover_date = character(0), source = character(0),
             evidence_path = character(0))
FORMAT_COLS <- c("level", "season", "rule_version", "changeover_date", "source",
                 "evidence_path")

csv_text <- function(df) {
  tc <- textConnection("out_lines", "w", local = TRUE)
  utils::write.csv(df, tc, row.names = FALSE, na = "")
  close(tc)
  paste0(paste(out_lines, collapse = "\n"), "\n")
}
read_text <- function(path) {
  if (!file.exists(path)) return(NA_character_)
  rawToChar(readBin(path, "raw", file.size(path)))
}

# aaa_format.csv: every row whose source does not begin with the W3.9 tag is kept byte for
# byte and in its place. This scan's rows follow them. The comparison in check mode is on
# this scan's rows alone, so a row another step appends later does not fail it.
mine_lines <- strsplit(sub("\n$", "", csv_text(mine[, FORMAT_COLS])), "\n", fixed = TRUE)[[1]]
format_header <- mine_lines[1]
mine_lines <- mine_lines[-1]
split_format <- function() {
  old <- read_text(FORMAT_FILE)
  if (is.na(old)) return(list(others = character(0), ours = character(0), exists = FALSE))
  lines <- strsplit(sub("\n$", "", old), "\n", fixed = TRUE)[[1]]
  if (!identical(gsub('"', "", lines[1]), paste(FORMAT_COLS, collapse = ","))) {
    stop("aaa_format.csv has a header this script does not write: ", lines[1], call. = FALSE)
  }
  body <- lines[-1]
  if (length(body) == 0) return(list(others = character(0), ours = character(0), exists = TRUE))
  parsed <- utils::read.csv(text = paste(lines, collapse = "\n"), colClasses = "character")
  stopifnot(nrow(parsed) == length(body))
  is_ours <- startsWith(parsed$source, paste0(SOURCE_TAG, " "))
  list(others = body[!is_ours], ours = body[is_ours], exists = TRUE, header = lines[1])
}
fmt_disk <- split_format()
format_text <- paste0(paste(c(if (fmt_disk$exists) fmt_disk$header else format_header,
                              fmt_disk$others, mine_lines), collapse = "\n"), "\n")

outputs <- list(
  list(path = T5_FILE, text = csv_text(t5), label = "T5_aaa_formats.csv"),
  list(path = SCAN_FILE, text = csv_text(scan), label = "aaa_regime_scan.csv"),
  list(path = CHANGE_FILE, text = csv_text(changeover), label = "aaa_changeover.csv"),
  list(path = FORMAT_FILE, text = format_text, label = "aaa_format.csv")
)
for (o in outputs) {
  disk <- read_text(o$path)
  same <- if (identical(o$path, FORMAT_FILE)) {
    fmt_disk$exists && identical(fmt_disk$ours, mine_lines)
  } else {
    !is.na(disk) && identical(disk, o$text)
  }
  if (CHECK_ONLY) {
    check(sprintf("%s matches a rebuild", o$label), same,
          sprintf("%s bytes on disk", if (is.na(disk)) "no file," else comma(nchar(disk, "bytes"))))
  } else if (same) {
    record(sprintf("%s", o$label), "unchanged")
  } else {
    dir.create(dirname(o$path), recursive = TRUE, showWarnings = FALSE)
    tmp <- paste0(o$path, ".tmp")
    writeBin(charToRaw(o$text), tmp)
    file.rename(tmp, o$path)
    record(sprintf("%s", o$label), sprintf("written, %s bytes", comma(nchar(o$text, "bytes"))))
  }
}

## --- 5. what the scan found -------------------------------------------------------------------

for (s in seasons_on_disk) {
  g <- gm[gm$season == s, ]
  cls <- table(factor(g$format_class, levels = c("full_abs", "human_called", "unclassified")),
               factor(g$has_abs_challenges, levels = c(FALSE, TRUE)))
  record(sprintf("classes %d (no key / key)", s), sprintf(
    "full_abs %d / %d; human_called %d / %d; unclassified %d / %d",
    cls["full_abs", "FALSE"], cls["full_abs", "TRUE"], cls["human_called", "FALSE"],
    cls["human_called", "TRUE"], cls["unclassified", "FALSE"], cls["unclassified", "TRUE"]))
  for (cl in c("full_abs", "human_called")) {
    a <- g$agree[g$format_class == cl]
    if (length(a) > 0) record(sprintf("agree %d %s", s, cl), sprintf(
      "median %s, 5th pct %s, 95th pct %s, range %s to %s, %d games", f4(stats::median(a)),
      f4(stats::quantile(a, 0.05, type = 7)), f4(stats::quantile(a, 0.95, type = 7)),
      f4(min(a)), f4(max(a)), length(a)))
  }
  record(sprintf("pitches %d", s), sprintf(paste0(
    "%s called, %s with full kinematics, %s scored (%s of them on the batter's machine ",
    "zone because the feed zone is not a rule zone), %s tracked and not scored"),
    comma(sum(g$n_called)), comma(sum(g$n_tracked)), comma(sum(g$n_scored)),
    comma(sum(g$n_zone_from_batter)), comma(sum(g$n_tracked - g$n_scored))))
}
hist_breaks <- seq(0.80, 1.00, by = 0.01)
cl_games <- gm[gm$format_class != "unclassified", ]
h <- table(cut(pmin(cl_games$agree, 0.999999), hist_breaks, right = FALSE))
record("agree histogram, 0.01 bins from 0.80",
       paste(sprintf("%s:%d", sprintf("%.2f", head(hist_breaks, -1)), as.integer(h)),
             collapse = " "))
below <- sum(cl_games$agree < 0.80)
if (below > 0) record("agree below 0.80", sprintf("%d games", below))

## --- 6. the SOP tests -------------------------------------------------------------------------

# S1: bimodal with a gap >= 0.04
full <- cl_games$agree[cl_games$format_class == "full_abs"]
human <- cl_games$agree[cl_games$format_class == "human_called"]
if (length(full) == 0 || length(human) == 0) {
  check("S1 agree histogram bimodal", FALSE, sprintf("full_abs %d games, human_called %d games",
                                                      length(full), length(human)))
} else {
  m_h <- stats::median(human); m_f <- stats::median(full)
  v <- sort(unique(cl_games$agree[cl_games$agree >= m_h & cl_games$agree <= m_f]))
  if (length(v) < 2) v <- c(m_h, m_f)
  gaps <- diff(v)
  w <- which.max(gaps)
  gap <- gaps[w]
  between <- cl_games[cl_games$agree >= m_h + GAP_MIN & cl_games$agree < CUT_FULL_ABS, ]
  record("S1 class medians", sprintf("human_called %s, full_abs %s, separation %s",
                                     f4(m_h), f4(m_f), f4(m_f - m_h)))
  record("S1 games between human median + 0.04 and 0.99", sprintf(
    "%d (%d with the key, %d without)", nrow(between), sum(between$has_abs_challenges),
    sum(!between$has_abs_challenges)))
  check("S1 widest empty gap between the modes >= 0.04", gap >= GAP_MIN,
        sprintf("widest gap %s, from %s to %s, over %s games", f4(gap), f4(v[w]), f4(v[w + 1]),
                comma(nrow(cl_games))))
}

# S2: every full_abs game has no key
conf <- gm[gm$signal_conflict, ]
check("S2 no full_abs game carries the key", nrow(conf) == 0,
      if (nrow(conf) == 0) sprintf("%s full_abs games", comma(sum(gm$format_class == "full_abs")))
      else sprintf("%d of %s full_abs games carry it: %s", nrow(conf),
                   comma(sum(gm$format_class == "full_abs")),
                   paste(sprintf("%d (%s, agree %s, %d MJ, %d overturned)", conf$game_pk,
                                 conf$official_date, f4(conf$agree),
                                 conf$n_mj_event + conf$n_mj_play, conf$n_mj_overturned),
                         collapse = "; ")))

# S3: the six data-contract games
for (i in seq_len(nrow(CONTRACT))) {
  cg <- CONTRACT[i, ]
  row <- gm[gm$game_pk == cg$game_pk, ]
  label <- sprintf("S3 contract game %d", cg$game_pk)
  if (nrow(row) == 0) {
    pending(label, "feed not on disk")
    next
  }
  ok <- row$has_abs_challenges == cg$has_abs_challenges && row$n_mj_event == cg$n_mj_event &&
    row$n_mj_play == cg$n_mj_play && !(row$has_abs_challenges && row$format_class == "full_abs")
  check(label, ok, sprintf(
    "key %s (contract %s), MJ %d/%d (contract %d/%d), class %s, agree %s, %d scored, %s",
    row$has_abs_challenges, cg$has_abs_challenges, row$n_mj_event, row$n_mj_play,
    cg$n_mj_event, cg$n_mj_play, row$format_class, f4(row$agree), row$n_scored, row$weekday))
}

# S4: the machine-day contour area by season, and the edge rule on machine-day verdicts
machine <- gm$game_pk[gm$format_class == "full_abs" & !gm$has_abs_challenges]
mp <- px_all[px_all$game_pk %in% machine, ]
rule_area <- function(top_frac) {
  H <- (top_frac - BOT_FRAC) * REF_HEIGHT_IN
  W <- 2 * PLATE_HALF_W_FT * 12
  (W + 2 * BALL_R_IN) * (H + 2 * BALL_R_IN) - (4 - pi) * BALL_R_IN^2
}
contour_area <- function(p, top_frac) {
  nx <- GRID_X[2] - GRID_X[1]; nz <- GRID_Z[2] - GRID_Z[1]
  ix <- floor(p$x_in) - GRID_X[1]; iz <- floor(p$z_ref) - GRID_Z[1]
  inw <- ix >= 0 & ix < nx & iz >= 0 & iz < nz
  cell <- ix[inw] * nz + iz[inw]
  n <- tabulate(cell + 1L, nbins = nx * nz)
  k <- tabulate(cell[p$cs[inw]] + 1L, nbins = nx * nz)
  cx <- (rep(seq_len(nx) - 1L, each = nz) + GRID_X[1] + 0.5) / 12
  cz <- (rep(seq_len(nz) - 1L, times = nx) + GRID_Z[1] + 0.5) / 12
  top <- top_frac * REF_HEIGHT_IN / 12; bot <- BOT_FRAC * REF_HEIGHT_IN / 12
  e_c <- signed_edge_in(cx, cz, top, bot) - BALL_R_IN
  rate <- ifelse(n > 0, k / n, as.numeric(e_c < 0))
  list(area = sum(rate), empty_near = sum(n == 0 & abs(e_c) < 2),
       strikes_outside = sum(p$cs[!inw]), n_in = sum(inw))
}
areas <- list()
for (s in seasons_on_disk) {
  label <- sprintf("S4 contour %d", s)
  if (s >= 2025L && !prereg_tagged) {
    pending(label, "not read before the prereg-v1 tag")
    next
  }
  p <- mp[mp$season == s, ]
  n_g <- length(unique(p$game_pk))
  if (n_g < MIN_SEASON_GAMES || nrow(p) < MIN_SEASON_PITCHES) {
    pending(label, sprintf("%d machine-day games and %s scored pitches on disk, below %d and %s",
                           n_g, comma(nrow(p)), MIN_SEASON_GAMES, comma(MIN_SEASON_PITCHES)))
    next
  }
  tab <- table(p$rule)
  fr <- as.numeric(names(tab)[which.max(tab)])
  ca <- contour_area(p, fr)
  ra <- rule_area(fr)
  areas[[as.character(s)]] <- c(area = ca$area, rule = ra, top = fr)
  agree_all <- mean(p$cs == (p$e < 0))
  out_band <- abs(p$e) > BAND_IN
  record(label, sprintf(paste0("%s sq in for a 6-ft batter over %d games and %s pitches; the ",
                               "published rule (top %.1f%%) gives %s sq in, residual %s; ",
                               "%d empty cells within 2 in of the rule edge, %d strikes ",
                               "outside the grid"),
                        sprintf("%.2f", ca$area), n_g, comma(nrow(p)), 100 * fr,
                        sprintf("%.2f", ra), sprintf("%+.2f", ca$area - ra), ca$empty_near,
                        ca$strikes_outside))
  record(sprintf("edge rule on machine-day verdicts %d", s), sprintf(
    paste0("%s of %s agree (%s%%); outside the +/-0.5 in band %s of %s (%s%%); ",
           "%d disagreements more than 2 in from the edge"),
    comma(sum(p$cs == (p$e < 0))), comma(nrow(p)), sprintf("%.4f", 100 * agree_all),
    comma(sum(p$cs[out_band] == (p$e[out_band] < 0))), comma(sum(out_band)),
    sprintf("%.4f", 100 * mean(p$cs[out_band] == (p$e[out_band] < 0))),
    sum(p$cs != (p$e < 0) & abs(p$e) > FAR_IN)))
}
if (length(areas) >= 2) {
  a <- vapply(areas, function(z) z[["area"]], numeric(1))
  r <- vapply(areas, function(z) z[["area"]] - z[["rule"]], numeric(1))
  spread <- max(a) - min(a)
  record("S4 residual against the published rule", sprintf(
    "spread %s sq in across %s", sprintf("%.2f", max(r) - min(r)),
    paste(names(areas), collapse = ", ")))
  check("S4 machine-day contour area stable to 2 sq in", spread <= AREA_TOL_SQIN,
        sprintf("%s; spread %s sq in across %s",
                paste(sprintf("%s %s", names(a), sprintf("%.2f", a)), collapse = ", "),
                sprintf("%.2f", spread), paste(names(areas), collapse = ", ")))
  if (length(areas) < 3) pending("S4 contour, all three seasons",
                                 sprintf("%d of 3 seasons evaluable", length(areas)))
} else {
  pending("S4 machine-day contour area stable to 2 sq in",
          sprintf("%d of 3 seasons evaluable", length(areas)))
}

## --- 7. D-11 and D-57 ------------------------------------------------------------------------

for (i in seq_len(nrow(changeover))) {
  r <- changeover[i, ]
  record(sprintf("%s %s", r$decision, r$status), r$result)
}

finish()
