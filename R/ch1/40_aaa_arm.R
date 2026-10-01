#!/usr/bin/env Rscript
# R/ch1/40_aaa_arm.R - SOP step W3.20, the AAA arm and the level difference-in-differences.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/40_aaa_arm.R           read the AAA feeds on disk, run the three uses, write
#                                        the five tables and the prose below
#   Rscript R/ch1/40_aaa_arm.R --check   rebuild everything in memory and compare it, byte for
#                                        byte, with the files on disk; write nothing
#
# THE THREE USES, in the SOP's descending order of strength, and reported in that order:
#
#   1. The machine-drift placebo (P3). Machine days are keyless full-ABS games. Their 50%
#      contour area, net of each season's published rule (D-P4-29), must not move between
#      seasons: two one-sided tests, 90% interval on the change inside +/-3 sq in.
#   2. The within-week alternation. The same plate umpire works a full-ABS game and a
#      challenge-format game in the same week. His called-strike rate on shadow-band pitches
#      is compared across the two formats against his own season mean (umpire-season fixed
#      effects), with week fixed effects. The frame holds only dates STRICTLY BEFORE the D-57
#      changeover date, read from the format_challenge_tue_thu row of the rule-version table
#      out/tables/aaa_format.csv. No date is written in this file. DT-29 asserts the frame.
#   3. The level difference-in-differences with AAA as the control series.
#      The DiD is a supporting arm, not the identification.
#      Parallel trends is stated explicitly, and it is strong: different umpire populations,
#      parks and Hawk-Eye installations, and a machine-set zone in AAA. Pre-trend: the
#      AAA-versus-MLB 2023 to 2024 coefficient must have a 95% interval containing 0, or the DiD
#      is reported as descriptive. The DiD is reported as an estimate with its own 95% interval.
#      In the changeover season the DiD series, like the within-week frame, keeps only dates
#      strictly before the changeover date (DT-29: the DiD frame holds no date on or after it).
#
# Placebo P1 failed (out/ch1/tab/T5_placebos.csv), so under the pre-registered consequence every
# contrast here is descriptive and names no cause.
#
# ESTIMATORS. The DiD reads both series with the annex section 5 binned logistic, the CH1-A5
# estimator: MLB from W3.15's cached draws (out/ch1/model/estimand_draws_binned.csv, no refit),
# AAA fitted here on challenge-format games with the umpire's original call. The MLB bam
# primary (estimand_draws_main.csv) is a robustness row. AAA intervals come from a bootstrap
# of games within season, 1,000 replicates, each paired with one MLB draw. AAA d is measured
# from each season's own published rule zone, so every AAA edge is net of the rule; the MLB
# rule did not change from 2023 to 2025. The AAA series is read on the calendar window every
# season covers with challenge-format games (primary) and on every such game on disk (robustness).
#
# READS. The AAA feeds in the raw lake (data/raw/statsapi/feed/sport=11), the staging cache for
# a game the lake does not hold, the AAA schedule in data/interim/schedule_game/level=aaa,
# out/tables/aaa_format.csv, out/ch1/tab/T5_placebos.csv, out/ch1/tab/T3_estimands.csv and
# out/ch1/model/estimand_draws_{binned,main}.csv. It makes no request of any host.
#
# THE SEAL. Only AAA 2023 to 2025 is read. Every game is dated before absump.paths.LAST_OPEN_DATE,
# asserted, and the run refuses to start unless the prereg tag is an ancestor of HEAD and the code
# it executes (this script and R/lib's fit code) is committed and clean, GD-12's code half. The
# tag's presence on origin is not queried: this phase makes no network request.
#
# WRITES, each only when its content changes:
#   out/tables/aaa_placebo.csv        use 1, P3
#   out/ch1/tab/aaa_withinweek.csv    use 2, with the frame's first and last date
#   out/ch1/tab/aaa_pretrend.csv      use 3, the pre-trend coefficient
#   out/ch1/tab/aaa_did.csv           use 3, the DiD estimate
#   out/ch1/prose/aaa.md              the three uses in prose, every number from the tables
#
# Exit 0 on success, 1 on a failed check or (with --check) a difference, 2 on a usage error.
#
# Environment: CH1_AAA_PAR, the number of forked feed readers (default 4; the readers are light).

options(warn = 1, digits = 12)
t_start <- Sys.time()

args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1 || (length(args) == 1 && !identical(args, "--check"))) {
  cat("usage: Rscript R/ch1/40_aaa_arm.R [--check]\n", file = stderr())
  quit(status = 2)
}
CHECK_ONLY <- identical(args, "--check")

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  if (length(f) == 1L) normalizePath(file.path(dirname(f), "..", "..")) else normalizePath(getwd())
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))   # zone.R, the annex constants, crossing(), qint()
suppressPackageStartupMessages({
  library(parallel)
  library(data.table)
})

## --- constants --------------------------------------------------------------------------------

STEP            <- "W3.20"
AAA_SEASONS     <- 2023:2025
AAA_LEVELS      <- as.character(AAA_SEASONS)
SPORT_ID        <- 11L
CALLED_CODES    <- c("B", "*B", "C")
RULE_TOP_FRACS  <- c(0.510, ABS_TOP_FRAC)   # 27/51 (AAA 2023), 27/53.5 (AAA 2024, 2025): W3.9
RULE_TOL        <- 0.002
CUT_FULL_ABS    <- 0.99                     # SOP W3.9's cut: a full-ABS game agrees >= 0.99
MIN_SCORED      <- 50L                      # SOP W3.9: fewer scored called pitches, unclassified
GRID_X          <- c(-16L, 16L)             # W3.9's S4 contour grid, 1-inch cells, 72-in batter
GRID_Z          <- c(10L, 48L)
MIN_SEASON_GAMES   <- 20L                   # W3.9: a season is evaluable with >= 20 machine days
MIN_SEASON_PITCHES <- 3000L                 # and >= 3,000 scored pitches
P3_MARGIN_SQIN  <- 3                        # PREREGISTRATION.md, P3 takes P1's area tolerance
P3_LEVEL        <- 0.90                     # two one-sided tests: the 90% interval
N_BOOT          <- N_DRAWS                  # 1,000, one AAA replicate per MLB draw
SEED            <- DRAW_SEED                # 20260922, the project seed
MIN_BOOT_SHARE  <- MIN_COMPLETE_SHARE       # 99% of replicates complete, as W3.15 requires
FORMAT_ROW      <- "format_challenge_tue_thu"   # the D-57 row of the rule-version table
ROLE            <- "The DiD is a supporting arm, not the identification."
PARALLEL_TRENDS <- paste(
  "Parallel trends, stated explicitly: had the 2025 grading-buffer cut not happened, MLB's called",
  "zone would have changed from 2024 to 2025 as AAA's challenge-format called zone did.",
  "This assumption is strong: different umpire populations, different parks, different Hawk-Eye",
  "installations, and a machine-set zone in AAA.")
PRETREND_RULE   <- paste("Pre-trend test (SOP W3.20): the AAA-versus-MLB 2023 to 2024 coefficient must",
                         "have a 95% interval containing 0, or the DiD is reported as descriptive.")
WEEKDAYS        <- c("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

FORMAT_FILE   <- file.path(ROOT, "out", "tables", "aaa_format.csv")
PLACEBO_T5    <- file.path(ROOT, "out", "ch1", "tab", "T5_placebos.csv")
T3_FILE       <- file.path(ROOT, "out", "ch1", "tab", "T3_estimands.csv")
MLB_DRAWS     <- c(binned = file.path(ROOT, "out", "ch1", "model", "estimand_draws_binned.csv"),
                   main   = file.path(ROOT, "out", "ch1", "model", "estimand_draws_main.csv"))
OUT_PLACEBO   <- file.path(ROOT, "out", "tables", "aaa_placebo.csv")
OUT_WEEK      <- file.path(ROOT, "out", "ch1", "tab", "aaa_withinweek.csv")
OUT_PRETREND  <- file.path(ROOT, "out", "ch1", "tab", "aaa_pretrend.csv")
OUT_DID       <- file.path(ROOT, "out", "ch1", "tab", "aaa_did.csv")
OUT_PROSE     <- file.path(ROOT, "out", "ch1", "prose", "aaa.md")

## --- the checks -------------------------------------------------------------------------------

n_pass <- 0L
failures <- character(0)
ok_line <- function(label, ok, detail) {
  if (isTRUE(ok)) {
    n_pass <<- n_pass + 1L
    cat(sprintf("PASS    %-46s %s\n", label, detail))
  } else {
    failures <<- c(failures, sprintf("%s -- %s", label, detail))
    cat(sprintf("FAIL    %-46s %s\n", label, detail))
  }
  invisible(isTRUE(ok))
}
note <- function(label, detail) cat(sprintf("RECORD  %-46s %s\n", label, detail))
stop_if_failed <- function() {
  if (length(failures) == 0) return(invisible(TRUE))
  cat("FAILED CLAUSES:\n", paste0("  ", failures, "\n"), sep = "")
  quit(status = 1)
}
f6 <- function(x) ifelse(is.finite(x), formatC(x, format = "f", digits = 6), "")
f2 <- function(x) formatC(x, format = "f", digits = 2)
f1 <- function(x) formatC(x, format = "f", digits = 1)
sgn2 <- function(x) sprintf("%+.2f", x)

## --- guards: the tag, the seal, the rule-version table -----------------------------------------

tag <- prereg_tag()
anc <- git_out(c("merge-base", "--is-ancestor", shQuote(tag), "HEAD"))
ok_line("prereg tag is an ancestor of HEAD", anc$status == 0L, sprintf("%s; AAA 2025 is read only after it", tag))
RUN_CODE <- unique(c("R/ch1/40_aaa_arm.R", FIT_CODE))
tracked <- git_out(c("ls-files", "--error-unmatch", "--", RUN_CODE))
dirty <- git_out(c("status", "--porcelain", "--", RUN_CODE))$out
ok_line("the code this run executes is committed and clean", tracked$status == 0L && length(dirty) == 0L,
        if (tracked$status == 0L && length(dirty) == 0L) sprintf("%d files at HEAD %s", length(RUN_CODE),
                                                                substr(git_head(), 1, 12))
        else paste(c(if (tracked$status != 0L) tracked$out, dirty), collapse = "; "))
LAST_OPEN <- last_open_date()
note("last open day", sprintf("absump.paths.LAST_OPEN_DATE %s; AAA %d to %d only", format(LAST_OPEN),
                              min(AAA_SEASONS), max(AAA_SEASONS)))
stop_if_failed()

fmt_rows <- utils::read.csv(FORMAT_FILE, colClasses = "character")
d57 <- fmt_rows[fmt_rows$level == "aaa" & fmt_rows$rule_version == FORMAT_ROW, ]
ok_line("D-57 row in the rule-version table", nrow(d57) == 1L,
        sprintf("%d row(s) with rule_version %s in %s", nrow(d57), FORMAT_ROW, "out/tables/aaa_format.csv"))
stop_if_failed()
CHANGEOVER <- as.Date(d57$changeover_date)
CHANGEOVER_SEASON <- as.integer(d57$season)
ok_line("changeover date is a date in its season", !is.na(CHANGEOVER) &&
          as.integer(format(CHANGEOVER, "%Y")) == CHANGEOVER_SEASON,
        sprintf("%s (season %d), source: %s", format(CHANGEOVER), CHANGEOVER_SEASON, substr(d57$source, 1, 60)))

p1 <- utils::read.csv(PLACEBO_T5, colClasses = "character")
p1 <- p1[p1$placebo == "P1", ]
P1_FAILED <- nrow(p1) > 0 && any(p1$placebo_verdict == "fail")
ok_line("P1 verdict read from T5", nrow(p1) > 0, sprintf("P1 %s: every contrast here is descriptive",
                                                         if (P1_FAILED) "failed" else "did not fail"))
# The notes and the prose below state that P1 failed. Should T5 ever read otherwise, the run stops
# rather than print a sentence the table no longer supports.
ok_line("P1 failed, as every note here states", P1_FAILED, "T5_placebos.csv, placebo P1, placebo_verdict")
stop_if_failed()

## --- the layout, the schedule and the feeds on disk ---------------------------------------------

data_root <- local({
  code <- "from absump.paths import data_root; print(data_root())"
  out <- suppressWarnings(system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python", "-c",
                                          shQuote(code)), stdout = TRUE, stderr = TRUE))
  st <- attr(out, "status")
  if (!is.null(st) && st != 0L) die("could not read absump.paths: ", paste(out, collapse = " "))
  trimws(out[length(out)])
})
LAKE_ROOT     <- file.path(data_root, "raw", "statsapi", "feed", sprintf("sport=%d", SPORT_ID))
STAGING_ROOT  <- file.path(data_root, "staging", "statsapi", "feeds", sprintf("sport%d", SPORT_ID))
SCHEDULE_ROOT <- file.path(data_root, "interim", "schedule_game", "level=aaa")
ok_line("AAA schedule present", dir.exists(SCHEDULE_ROOT), SCHEDULE_ROOT)
ok_line("AAA feed lake present", dir.exists(LAKE_ROOT), LAKE_ROOT)
stop_if_failed()

sched_files <- sort(list.files(SCHEDULE_ROOT, pattern = "\\.parquet$", recursive = TRUE, full.names = TRUE))
sched <- do.call(rbind, lapply(sched_files, function(f) as.data.frame(arrow::read_parquet(
  f, col_select = c("game_pk", "season", "game_type", "official_date", "status_coded")))))
sched$game_pk <- as.integer(sched$game_pk)
sched$season <- as.integer(sched$season)
sched$official_date <- as.Date(sched$official_date)
final_r <- sched[sched$game_type == "R" & sched$status_coded == "F" & sched$season %in% AAA_SEASONS &
                   sched$official_date < LAST_OPEN, ]
note("schedule, Final regular-season games", paste(sprintf("%d: %s", AAA_SEASONS,
     comma(table(factor(final_r$season, levels = AAA_SEASONS)))), collapse = "; "))

list_feeds <- function() {
  lake <- unlist(lapply(AAA_SEASONS, function(s) list.files(
    file.path(LAKE_ROOT, sprintf("season=%d", s)), pattern = "^gamepk=[0-9]+\\.json\\.zst$",
    recursive = TRUE, full.names = TRUE)))
  staged <- unlist(lapply(AAA_SEASONS, function(s) list.files(
    file.path(STAGING_ROOT, s), pattern = "^[0-9]+\\.json$", recursive = TRUE, full.names = TRUE)))
  a <- data.frame(game_pk = as.integer(sub("^gamepk=([0-9]+)\\.json\\.zst$", "\\1", basename(lake))),
                  path = lake, stringsAsFactors = FALSE)
  b <- data.frame(game_pk = as.integer(sub("\\.json$", "", basename(staged))), path = staged,
                  stringsAsFactors = FALSE)
  out <- rbind(a, b[!(b$game_pk %in% a$game_pk), , drop = FALSE])
  out <- out[out$game_pk %in% final_r$game_pk, , drop = FALSE]
  out[order(out$game_pk), , drop = FALSE]
}
feeds <- list_feeds()
note("feeds on disk, Final regular season", sprintf("%s of %s scheduled", comma(nrow(feeds)), comma(nrow(final_r))))

## --- reading a feed ------------------------------------------------------------------------------

read_feed_text <- function(path) {
  if (grepl("\\.zst$", path)) {
    s <- arrow::CompressedInputStream$create(path, codec = arrow::Codec$create("zstd"))
    on.exit(s$close())
    parts <- list()
    repeat {
      r <- as.raw(s$Read(16e6))
      if (length(r) == 0) break
      parts[[length(parts) + 1L]] <- r
    }
    rawToChar(do.call(c, parts))
  } else {
    rawToChar(readBin(path, "raw", file.size(path)))
  }
}
num <- function(x) if (is.null(x)) NA_real_ else as.numeric(x)
int_or_na <- function(x) if (is.null(x)) NA_integer_ else as.integer(x)
walk_reviews <- function(r) {
  if (!is.list(r) || is.null(names(r))) return(list())
  out <- list(r)
  for (x in r$additionalReviews) out <- c(out, walk_reviews(x))
  out
}

# One feed: the game's facts and one row per called pitch. The umpire's call is the published
# call flipped back where an MJ review overturned it, W3.9's rule: a review on
# playEvents[].reviewDetails belongs to that pitch, one on allPlays[].reviewDetails to the play's
# last pitch, and additionalReviews count with their parent. The plate umpire is the "Home
# Plate" official of liveData.boxscore.officials. The count before a pitch is the count after
# the event before it in the plate appearance, 0-0 for the first.
parse_game <- function(path) {
  feed <- jsonlite::parse_json(read_feed_text(path), simplifyVector = FALSE)
  gd <- feed$gameData
  hp <- NA_integer_
  for (o in feed$liveData$boxscore$officials) {
    if (identical(o$officialType, "Home Plate")) hp <- int_or_na(o$official$id)
  }
  cap <- 1200L
  code <- character(cap); flip <- logical(cap)
  batter <- pre_s <- rep(NA_integer_, cap); stand <- rep(NA_character_, cap)
  top <- bot <- px <- pz <- vx0 <- vy0 <- vz0 <- ax <- ay <- az <- rep(NA_real_, cap)
  k <- 0L; n_mj <- 0L
  for (play in feed$liveData$plays$allPlays) {
    bat <- int_or_na(play$matchup$batter$id)
    side <- play$matchup$batSide$code
    side <- if (is.null(side)) NA_character_ else as.character(side)
    evs <- play$playEvents
    if (length(evs) == 0) next
    is_p <- vapply(evs, function(e) isTRUE(e$isPitch), logical(1))
    fl <- logical(length(evs))
    last <- if (any(is_p)) max(which(is_p)) else NA_integer_
    for (r in walk_reviews(play$reviewDetails)) {
      if (identical(r$reviewType, "MJ")) {
        n_mj <- n_mj + 1L
        if (isTRUE(r$isOverturned) && !is.na(last)) fl[last] <- TRUE
      }
    }
    for (i in seq_along(evs)) {
      for (r in walk_reviews(evs[[i]]$reviewDetails)) {
        if (identical(r$reviewType, "MJ")) {
          n_mj <- n_mj + 1L
          if (isTRUE(r$isOverturned) && is_p[i]) fl[i] <- TRUE
        }
      }
    }
    for (i in which(is_p)) {
      ev <- evs[[i]]
      cd <- ev$details$call$code
      if (is.null(cd) || !(cd %in% CALLED_CODES)) next
      k <- k + 1L
      if (k > cap) stop(sprintf("%s has more than %d called pitches", path, cap))
      prev <- if (i > 1L) evs[[i - 1L]]$count else NULL
      pre_s[k] <- if (is.null(prev)) 0L else int_or_na(prev$strikes)
      pd <- ev$pitchData
      co <- pd$coordinates
      code[k] <- cd; flip[k] <- fl[i]; batter[k] <- bat; stand[k] <- side
      top[k] <- num(pd$strikeZoneTop); bot[k] <- num(pd$strikeZoneBottom)
      px[k] <- num(co$pX); pz[k] <- num(co$pZ)
      vx0[k] <- num(co$vX0); vy0[k] <- num(co$vY0); vz0[k] <- num(co$vZ0)
      ax[k] <- num(co$aX); ay[k] <- num(co$aY); az[k] <- num(co$aZ)
    }
  }
  s <- seq_len(k)
  game <- data.frame(
    game_pk = as.integer(gd$game$pk), season = as.integer(gd$game$season),
    game_type = as.character(gd$game$type), official_date = as.character(gd$datetime$officialDate),
    has_key = "absChallenges" %in% names(gd), venue_id = int_or_na(gd$venue$id),
    umpire_hp_id = hp, n_mj = n_mj, stringsAsFactors = FALSE)
  pitches <- data.frame(
    game_pk = rep(game$game_pk, k), code = code[s], flip = flip[s], batter = batter[s],
    stand = stand[s], pre_strikes = pre_s[s], top = top[s], bot = bot[s],
    px = px[s], pz = pz[s], vx0 = vx0[s], vy0 = vy0[s], vz0 = vz0[s], ax = ax[s], ay = ay[s],
    az = az[s], stringsAsFactors = FALSE)
  list(game = game, pitches = pitches)
}

n_par <- max(1L, as.integer(Sys.getenv("CH1_AAA_PAR", "4")))
t_read <- Sys.time()
parsed <- mclapply(feeds$path, function(f) tryCatch(parse_game(f), error = function(e) conditionMessage(e)),
                   mc.cores = n_par, mc.preschedule = TRUE)
bad <- which(vapply(parsed, is.character, logical(1)))
ok_line("every feed on disk parses", length(bad) == 0L,
        if (length(bad) == 0L) sprintf("%s feeds, %d readers, %.0f s", comma(nrow(feeds)), n_par,
                                       as.numeric(difftime(Sys.time(), t_read, units = "secs")))
        else paste(head(sprintf("%s (%s)", feeds$path[bad], unlist(parsed[bad])), 3), collapse = "; "))
stop_if_failed()
G <- do.call(rbind, lapply(parsed, `[[`, "game"))
P <- do.call(rbind, lapply(parsed, `[[`, "pitches"))
rm(parsed)
ok_line("each feed is the game its path names", identical(G$game_pk, feeds$game_pk),
        sprintf("%s games", comma(nrow(G))))
G$official_date <- as.Date(G$official_date)
G <- G[G$game_type == "R", , drop = FALSE]
ok_line("the seal: every game before the last open day, AAA 2023 to 2025",
        all(G$official_date < LAST_OPEN) && all(G$season %in% AAA_SEASONS),
        sprintf("latest game %s, seasons %s", format(max(G$official_date)), paste(sort(unique(G$season)), collapse = ", ")))
stop_if_failed()
P <- P[P$game_pk %in% G$game_pk, , drop = FALSE]
m <- match(P$game_pk, G$game_pk)
P$season <- G$season[m]
P$official_date <- as.character(G$official_date[m])

## --- the zone and the format, W3.9's rules ----------------------------------------------------------

rule_of <- function(top, bot) {
  frac <- ABS_BOT_FRAC * top / bot
  vapply(frac, function(f) {
    if (is.na(f)) return(NA_real_)
    d <- abs(RULE_TOP_FRACS - f)
    if (min(d) <= RULE_TOL) RULE_TOP_FRACS[which.min(d)] else NA_real_
  }, numeric(1))
}
modal <- function(x) {
  x <- x[!is.na(x)]
  if (length(x) == 0) return(NA_real_)
  tab <- table(x)
  as.numeric(names(tab)[which.max(tab)])
}

# Every called pitch against the machine rule zone in force: the zone the feed publishes where it
# is a rule zone (bottom 27%, top 51% or 53.5% of height), otherwise the batter's rule zone that
# season from his height on his published rule-zone pitches and the top fraction in force that
# day (W3.9's score_all in R/ch1/12_aaa_formats.R). d is the ball-centre signed distance to that
# zone at mid-plate, positive outside: the MLB analysis table's d, on the season's own rule zone.
score_pitches <- function(P) {
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
  h_med <- tapply(P$bot[has_pub] * 12 / ABS_BOT_FRAC, paste(P$season[has_pub], P$batter[has_pub]), stats::median)
  day_rule <- tapply(rule_pub[has_pub], P$official_date[has_pub], modal)
  season_rule <- tapply(rule_pub[has_pub], P$season[has_pub], modal)
  need <- kin & !has_pub & !is.na(P$batter)
  h <- rep(NA_real_, nrow(P))
  h[need] <- as.numeric(h_med[paste(P$season[need], P$batter[need])])
  r_fill <- as.numeric(day_rule[P$official_date])
  r_fill <- ifelse(is.na(r_fill), as.numeric(season_rule[as.character(P$season)]), r_fill)
  from_batter <- need & !is.na(h) & !is.na(r_fill)
  rule <- ifelse(has_pub, rule_pub, ifelse(from_batter, r_fill, NA_real_))
  top <- ifelse(has_pub, P$top, ifelse(from_batter, r_fill * h / 12, NA_real_))
  bot <- ifelse(has_pub, P$bot, ifelse(from_batter, ABS_BOT_FRAC * h / 12, NA_real_))
  ok <- kin & !is.na(rule)
  d <- xm <- zm <- rep(NA_real_, nrow(P)); edge <- rep(NA_character_, nrow(P))
  if (any(ok)) {
    mid <- reproject(P$px[ok], P$pz[ok], P$vx0[ok], P$vy0[ok], P$vz0[ok], P$ax[ok], P$ay[ok], P$az[ok],
                     y_from = Y_FRONT_FT, y_to = Y_MID_FT)
    xm[ok] <- mid$x; zm[ok] <- mid$z
    d[ok] <- signed_edge_in(mid$x, mid$z, top[ok], bot[ok])
    edge[ok] <- nearest_edge(mid$x, mid$z, top[ok], bot[ok])
  }
  cc <- ifelse(!is.na(P$pre_strikes) & P$pre_strikes %in% 0:2,
               CC_LEVELS[pmin(pmax(P$pre_strikes, 0L), 2L) + 1L], NA_character_)
  data.frame(game_pk = P$game_pk, season = P$season, cs = cs, scored = ok, rule = rule, d = d,
             edge = edge, count_class = cc, stand = P$stand, x_in = xm * 12,
             z_ref = zm * REF_HEIGHT_IN * ABS_BOT_FRAC / bot, stringsAsFactors = FALSE)
}
S <- score_pitches(P)
rm(P)

# The game's format. The key marks a challenge-format game (D-11 and D-57: a game's format is read
# from its key). A keyless game is full ABS when the umpire's call agrees with the machine rule
# zone on at least 99% of its scored called pitches (SOP W3.9's cut), and human-called without
# challenges otherwise; fewer than 50 scored called pitches, unclassified. W3.9's cut and minimum.
fg <- factor(S$game_pk, levels = G$game_pk)
G$n_scored <- as.integer(tabulate(as.integer(fg)[S$scored], nbins = nrow(G)))
hit <- S$scored & (S$cs == (S$d < BALL_R_IN))
G$agree <- ifelse(G$n_scored > 0, tabulate(as.integer(fg)[hit], nbins = nrow(G)) / G$n_scored, NA_real_)
G$format <- ifelse(G$n_scored < MIN_SCORED, "unclassified",
                   ifelse(G$has_key, "challenge", ifelse(G$agree >= CUT_FULL_ABS, "full_abs", "human_no_challenge")))
G$weekday <- WEEKDAYS[as.POSIXlt(G$official_date)$wday + 1L]
fmt_tab <- table(factor(G$season, levels = AAA_SEASONS), factor(G$format, levels = c(
  "full_abs", "challenge", "human_no_challenge", "unclassified")))
for (s in AAA_SEASONS) {
  note(sprintf("formats %d", s), paste(sprintf("%s %s", colnames(fmt_tab), comma(fmt_tab[as.character(s), ])),
                                       collapse = ", "))
}
S$format <- G$format[as.integer(fg)]
S$official_date <- G$official_date[as.integer(fg)]

# Feed coverage per season: the last date through which every Final game from opening day has
# its feed on disk. It bounds the DiD's calendar window and is printed in every table.
final_r$on_disk <- final_r$game_pk %in% G$game_pk
coverage <- do.call(rbind, lapply(AAA_SEASONS, function(s) {
  x <- final_r[final_r$season == s, ]
  per_day <- tapply(x$on_disk, x$official_date, all)
  days <- as.Date(names(per_day))
  full <- as.logical(per_day)
  end <- if (all(full)) length(full) else which(!full)[1] - 1L
  data.frame(season = s, first = min(days), last = max(days), complete_through =
               if (end > 0) days[end] else as.Date(NA), n_final = nrow(x), n_on_disk = sum(x$on_disk),
             stringsAsFactors = FALSE)
}))
cov_text <- function(s) {
  r <- coverage[coverage$season == s, ]
  if (r$n_on_disk == r$n_final) return(sprintf("%d: all %s Final games", s, comma(r$n_final)))
  sprintf("%d: %s of %s Final games, complete through %s", s, comma(r$n_on_disk), comma(r$n_final),
          format(r$complete_through))
}
COVERAGE <- paste(vapply(AAA_SEASONS, cov_text, character(1)), collapse = "; ")
note("feed coverage", COVERAGE)

## --- use 1: the machine-drift placebo, P3 ---------------------------------------------------------
# Machine days are keyless full-ABS games. The 50% contour area is W3.9's S4 estimator: 1-inch
# cells for a 72-inch batter over x in [-16, 16) and z in [10, 48), area = the sum of the cells'
# called-strike rates, an empty cell taking the rule's own verdict at its centre. Rule-net area is
# that area minus the area of the season's published zone for the same batter (D-P4-29). Pitches
# scored against a zone other than the season's modal rule are left out and counted. The interval
# is a bootstrap of machine-day games within season, 1,000 replicates.

rule_area <- function(top_frac) {
  H <- (top_frac - ABS_BOT_FRAC) * REF_HEIGHT_IN
  W <- 2 * PLATE_HALF_W_FT * 12
  (W + 2 * BALL_R_IN) * (H + 2 * BALL_R_IN) - (4 - pi) * BALL_R_IN^2
}
NX <- GRID_X[2] - GRID_X[1]; NZ <- GRID_Z[2] - GRID_Z[1]
cell_of <- function(x_in, z_ref) {
  ix <- floor(x_in) - GRID_X[1]; iz <- floor(z_ref) - GRID_Z[1]
  ifelse(ix >= 0 & ix < NX & iz >= 0 & iz < NZ, ix * NZ + iz + 1L, NA_integer_)
}
cell_rule_verdict <- function(top_frac) {
  cx <- (rep(seq_len(NX) - 1L, each = NZ) + GRID_X[1] + 0.5) / 12
  cz <- (rep(seq_len(NZ) - 1L, times = NX) + GRID_Z[1] + 0.5) / 12
  as.numeric(signed_edge_in(cx, cz, top_frac * REF_HEIGHT_IN / 12, ABS_BOT_FRAC * REF_HEIGHT_IN / 12) < BALL_R_IN)
}
area_from <- function(n, k, rv) sum(ifelse(n > 0, k / n, rv))

machine <- S[S$scored & S$format == "full_abs", ]
p3_season <- list()
p3_boot <- list()
set.seed(SEED)
for (s in AAA_SEASONS) {
  p <- machine[machine$season == s, ]
  games <- sort(unique(p$game_pk))
  fr <- modal(p$rule)
  base <- list(season = s, n_games = length(games), n_pitches = nrow(p), n_other_rule = 0L,
               first = if (nrow(p)) min(p$official_date) else as.Date(NA),
               last = if (nrow(p)) max(p$official_date) else as.Date(NA), top_frac = fr)
  if (nrow(p) > 0) {
    base$n_other_rule <- sum(p$rule != fr)
    p <- p[p$rule == fr, ]
  }
  if (length(games) < MIN_SEASON_GAMES || nrow(p) < MIN_SEASON_PITCHES) {
    p3_season[[as.character(s)]] <- c(base, list(evaluable = FALSE))
    next
  }
  cell <- cell_of(p$x_in, p$z_ref)
  inw <- !is.na(cell)
  gi <- match(p$game_pk, games)
  # games x cells counts; a replicate's counts are its game multiplicities times these
  Nm <- matrix(0, length(games), NX * NZ); Km <- Nm
  idx <- cbind(gi[inw], cell[inw])
  Nm <- as.matrix(Matrix::sparseMatrix(i = idx[, 1], j = idx[, 2], x = 1, dims = dim(Nm)))
  Km <- as.matrix(Matrix::sparseMatrix(i = idx[, 1], j = idx[, 2], x = as.numeric(p$cs[inw]), dims = dim(Nm)))
  rv <- cell_rule_verdict(fr)
  ra <- rule_area(fr)
  area <- area_from(colSums(Nm), colSums(Km), rv)
  reps <- vapply(seq_len(N_BOOT), function(b) {
    w <- tabulate(sample.int(length(games), length(games), replace = TRUE), nbins = length(games))
    area_from(as.vector(w %*% Nm), as.vector(w %*% Km), rv)
  }, numeric(1))
  p3_season[[as.character(s)]] <- c(base, list(evaluable = TRUE, area = area, rule_area = ra,
                                               rule_net = area - ra, n_outside_grid = sum(!inw)))
  p3_boot[[as.character(s)]] <- reps - ra
  note(sprintf("P3 machine days %d", s), sprintf(
    "%s games, %s pitches (%d on another rule left out); contour %s sq in, rule %s, rule-net %s",
    comma(length(games)), comma(nrow(p)), base$n_other_rule, f2(area), f2(ra), sgn2(area - ra)))
}

P3_NOTE <- paste("Use 1 of 3, the strongest: the machine-drift placebo. The level DiD, use 3, is a supporting",
                 "arm, not the identification. Placebo P1 failed, so every contrast is descriptive.")
p3_rows <- list()
for (s in AAA_SEASONS) {
  z <- p3_season[[as.character(s)]]
  i90 <- if (z$evaluable) qint(p3_boot[[as.character(s)]], 0.90) else c(NA, NA)
  i95 <- if (z$evaluable) qint(p3_boot[[as.character(s)]], 0.95) else c(NA, NA)
  p3_rows[[length(p3_rows) + 1L]] <- data.frame(
    placebo = "P3", row_type = "season", season_from = s, season_to = s,
    quantity = "rule-net machine-day contour area, 72-in batter", units = "sq in",
    estimate = if (z$evaluable) z$rule_net else NA_real_, lo90 = i90[1], hi90 = i90[2], lo95 = i95[1], hi95 = i95[2],
    margin_sqin = NA_real_, verdict = if (z$evaluable) "measured" else "not evaluable",
    contour_area = if (z$evaluable) z$area else NA_real_, rule_area = if (z$evaluable) z$rule_area else NA_real_,
    rule_top_frac = z$top_frac, n_games = z$n_games, n_pitches = z$n_pitches,
    first_date = if (is.na(z$first)) "" else format(z$first), last_date = if (is.na(z$last)) "" else format(z$last),
    n_boot = if (z$evaluable) N_BOOT else 0L,
    detail = if (z$evaluable) sprintf("%d pitches scored on another rule left out; %d outside the grid",
                                      z$n_other_rule, z$n_outside_grid)
             else sprintf("%d machine-day games and %s scored pitches, below %d and %s", z$n_games,
                          comma(z$n_pitches), MIN_SEASON_GAMES, comma(MIN_SEASON_PITCHES)),
    note = P3_NOTE, stringsAsFactors = FALSE)
}
for (i in seq_len(length(AAA_SEASONS) - 1L)) {
  a <- p3_season[[AAA_LEVELS[i]]]; b <- p3_season[[AAA_LEVELS[i + 1L]]]
  ev <- a$evaluable && b$evaluable
  if (ev) {
    dv <- p3_boot[[AAA_LEVELS[i + 1L]]] - p3_boot[[AAA_LEVELS[i]]]
    est <- b$rule_net - a$rule_net
    i90 <- qint(dv, P3_LEVEL); i95 <- qint(dv, 0.95)
    verdict <- if (i90[1] > -P3_MARGIN_SQIN && i90[2] < P3_MARGIN_SQIN) "pass" else "fail"
    detail <- sprintf("raw contour change %s sq in, published-rule change %s sq in", sgn2(b$area - a$area),
                      sgn2(b$rule_area - a$rule_area))
  } else {
    est <- NA_real_; i90 <- i95 <- c(NA_real_, NA_real_); verdict <- "not evaluable"
    miss <- AAA_LEVELS[c(i, i + 1L)][!c(a$evaluable, b$evaluable)]
    detail <- sprintf("%s has %s machine-day games on disk: no keyless full-ABS game",
                      paste(miss, collapse = " and "),
                      paste(vapply(miss, function(m) as.character(p3_season[[m]]$n_games), ""), collapse = " and "))
  }
  p3_rows[[length(p3_rows) + 1L]] <- data.frame(
    placebo = "P3", row_type = "change", season_from = AAA_SEASONS[i], season_to = AAA_SEASONS[i + 1L],
    quantity = sprintf("rule-net machine-day contour area, %d minus %d", AAA_SEASONS[i + 1L], AAA_SEASONS[i]),
    units = "sq in", estimate = est, lo90 = i90[1], hi90 = i90[2], lo95 = i95[1], hi95 = i95[2],
    margin_sqin = P3_MARGIN_SQIN, verdict = verdict, contour_area = NA_real_, rule_area = NA_real_,
    rule_top_frac = NA_real_, n_games = if (ev) a$n_games + b$n_games else NA_integer_,
    n_pitches = if (ev) a$n_pitches + b$n_pitches else NA_integer_, first_date = "", last_date = "",
    n_boot = if (ev) N_BOOT else 0L,
    detail = paste0("two one-sided tests: pass when the 90% interval lies inside +/-3 sq in (PREREGISTRATION.md, ",
                    "D-P4-29); ", detail),
    note = P3_NOTE, stringsAsFactors = FALSE)
}
p3 <- do.call(rbind, p3_rows)
for (i in which(p3$row_type == "change")) {
  note(sprintf("P3 %d to %d", p3$season_from[i], p3$season_to[i]), sprintf(
    "%s: %s sq in, 90%% interval %s to %s", p3$verdict[i], sgn2(p3$estimate[i]), sgn2(p3$lo90[i]), sgn2(p3$hi90[i])))
}

## --- use 2: the within-week alternation -------------------------------------------------------------
# The week is the AAA series week, Tuesday to the Monday after it, so a Tue-Sun series and a
# Monday game after it share a week. The frame keeps full-ABS and challenge-format plate games on
# dates STRICTLY BEFORE the changeover date from the rule-version table, and of those only the
# umpire-weeks in which one plate umpire worked at least one game of each format. On those
# games' scored shadow-band pitches, |d - 1.45| <= 3.0 in (D-P4-09), a linear probability model:
#
#   called strike ~ challenge + edge x 0.5-in d bin + count class x handedness
#                   + umpire x season (his own season mean) + week
#
# The coefficient on challenge, in percentage points, is his called-strike rate on the
# challenge-format day minus his rate on the full-ABS day at the same location, within his season
# and the league week. On a full-ABS day the call is the machine's, so it reads as his departure
# from the machine zone. Standard errors are cluster-robust by umpire (CR1), the interval uses
# t with one fewer degree of freedom than there are umpires.

week_of <- function(date) date - ((as.integer(format(date, "%u")) - 2L) %% 7L)
G$week <- week_of(G$official_date)
pre <- G[G$official_date < CHANGEOVER & G$format %in% c("full_abs", "challenge") & !is.na(G$umpire_hp_id), ]
uw <- aggregate(cbind(full = pre$format == "full_abs", chal = pre$format == "challenge") ~
                  umpire_hp_id + week, data = pre, FUN = sum)
alt <- uw[uw$full > 0 & uw$chal > 0, c("umpire_hp_id", "week")]
frame <- merge(pre, alt, by = c("umpire_hp_id", "week"))
frame <- frame[order(frame$official_date, frame$game_pk), ]
ok_line("DT-29: the within-week frame holds no date on or after the changeover",
        nrow(frame) > 0 && all(frame$official_date < CHANGEOVER),
        sprintf("%s games, %s to %s, changeover %s", comma(nrow(frame)), format(min(frame$official_date)),
                format(max(frame$official_date)), format(CHANGEOVER)))
stop_if_failed()
note("within-week frame", sprintf("%s umpire-weeks, %d umpires; %s full-ABS and %s challenge-format games",
                                  comma(nrow(alt)), length(unique(alt$umpire_hp_id)),
                                  comma(sum(frame$format == "full_abs")), comma(sum(frame$format == "challenge"))))

wk <- S[S$scored & S$game_pk %in% frame$game_pk & shadow_band(S$d) & !is.na(S$count_class) &
          S$stand %in% STAND_LEVELS, ]
fm <- match(wk$game_pk, frame$game_pk)
wk$umpire_hp_id <- frame$umpire_hp_id[fm]
wk$week <- frame$week[fm]
wk$challenge <- as.numeric(frame$format[fm] == "challenge")
wk$dbin <- floor((wk$d - (BALL_R_IN - BAND_SHADOW)) / BIN_W_IN)

# One coefficient by Frisch-Waugh: residualise y and the regressor on the fixed effects, then
# beta = sum(x y) / sum(x^2), CR1 by umpire.
fe_fit <- function(x) {
  X <- stats::model.matrix(~ factor(paste(edge, dbin)) + factor(paste(count_class, stand)) +
                             factor(paste(umpire_hp_id, season)) + factor(format(week)), data = x)
  q <- qr(X)
  xt <- qr.resid(q, x$challenge)
  yt <- qr.resid(q, as.numeric(x$cs))
  beta <- sum(xt * yt) / sum(xt^2)
  u <- yt - beta * xt
  cl <- x$umpire_hp_id
  sg <- tapply(xt * u, cl, sum)
  G_ <- length(sg); N_ <- nrow(x); K_ <- q$rank + 1L
  v <- sum(sg^2) / sum(xt^2)^2 * (G_ / (G_ - 1)) * ((N_ - 1) / (N_ - K_))
  se <- sqrt(v)
  tq <- stats::qt(0.975, df = G_ - 1)
  list(beta = 100 * beta, se = 100 * se, lo = 100 * (beta - tq * se), hi = 100 * (beta + tq * se),
       n = N_, clusters = G_, k = K_)
}
WEEK_NOTE <- paste("Use 2 of 3: the within-week alternation. The level DiD, use 3, is a supporting arm, not the",
                   "identification. Placebo P1 failed, so every contrast is descriptive.")
wk_rows <- list()
scopes <- list(c("pooled", "all"), c(AAA_LEVELS[1], "all"), c(AAA_LEVELS[2], "all"))
scopes <- c(scopes, lapply(EDGE_LEVELS, function(e) c("pooled", e)))
for (sc in scopes) {
  x <- wk
  if (sc[1] != "pooled") x <- x[x$season == as.integer(sc[1]), ]
  if (sc[2] != "all") x <- x[x$edge == sc[2], ]
  fr <- frame[frame$game_pk %in% x$game_pk, ]
  f <- if (nrow(x) > 0 && length(unique(x$challenge)) == 2L) fe_fit(x) else NULL
  wk_rows[[length(wk_rows) + 1L]] <- data.frame(
    use = "within-week alternation", season_scope = sc[1], edge_scope = sc[2],
    estimand = "challenge-format minus full-ABS called-strike rate, shadow band, same umpire-season and week",
    units = "pp", estimate = if (is.null(f)) NA_real_ else f$beta, se = if (is.null(f)) NA_real_ else f$se,
    lo95 = if (is.null(f)) NA_real_ else f$lo, hi95 = if (is.null(f)) NA_real_ else f$hi,
    rate_challenge = 100 * mean(x$cs[x$challenge == 1]), rate_full_abs = 100 * mean(x$cs[x$challenge == 0]),
    n_pitches = nrow(x), n_pitches_challenge = sum(x$challenge == 1), n_pitches_full_abs = sum(x$challenge == 0),
    n_games_challenge = sum(fr$format == "challenge"), n_games_full_abs = sum(fr$format == "full_abs"),
    n_umpire_weeks = nrow(unique(fr[, c("umpire_hp_id", "week")])), n_umpires = length(unique(fr$umpire_hp_id)),
    n_parameters = if (is.null(f)) NA_integer_ else f$k,
    frame_first_date = format(min(fr$official_date)), frame_last_date = format(max(fr$official_date)),
    changeover_date = format(CHANGEOVER), changeover_source = sprintf("out/tables/aaa_format.csv, rule_version %s",
                                                                     FORMAT_ROW),
    model = "LPM: challenge + edge x d bin + count class x stand + umpire x season + week; CR1 by umpire",
    note = WEEK_NOTE, stringsAsFactors = FALSE)
}
wkt <- do.call(rbind, wk_rows)
for (i in seq_len(nrow(wkt))) {
  note(sprintf("within-week %s, %s", wkt$season_scope[i], wkt$edge_scope[i]), sprintf(
    "%s pp (95%% CI %s to %s), %s pitches, %d umpires", sgn2(wkt$estimate[i]), sgn2(wkt$lo95[i]),
    sgn2(wkt$hi95[i]), comma(wkt$n_pitches[i]), wkt$n_umpires[i]))
}

## --- use 3: the level difference-in-differences -------------------------------------------------------
# The DiD is a supporting arm, not the identification. The AAA control series is the plate
# umpire's original call in challenge-format games, the format AAA played in every season on
# disk. It is read with the annex section 5 binned logistic (R/lib/ch1_decomp.R, W3.11's code):
# d in 0.5-in bins over [-8, +8], glm(cbind(strikes, balls) ~ 0 + bin + season + count_class +
# stand) per edge, each season's edge the 50% crossing standardised to the 2024 mix of count
# class and handedness, walking outward from the deepest inside bin. The edges are placed on the
# common reference zone of a 72-inch batter as the MLB binned estimands are: top = 0.535 x 72 +
# the top crossing, bottom = 0.27 x 72 - the bottom crossing, half-width = 8.5 + the side
# crossing, area = 2 x half-width x (top - bottom). The MLB series is W3.15's cached binned draws.
#
# The AAA window. Primary: the month-day window every AAA season covers with challenge-format
# games whose feeds are complete, from the latest season's first challenge-format game to the
# earliest complete-coverage end. Robustness: every challenge-format game on disk.

# In the changeover season only dates strictly before the changeover date enter (DT-29). The
# challenge-format games on disk after it are D-57's binary-search probes, not a season sample.
aaa_band <- S[S$scored & S$format == "challenge" & abs(S$d) <= BAND_SURF & !is.na(S$count_class) &
                S$stand %in% STAND_LEVELS & !is.na(S$edge) &
                !(S$season == CHANGEOVER_SEASON & S$official_date >= CHANGEOVER), ]
ok_line("DT-29: the DiD series holds no changeover-season date on or after the changeover",
        nrow(aaa_band) > 0 && !any(aaa_band$season == CHANGEOVER_SEASON & aaa_band$official_date >= CHANGEOVER),
        sprintf("latest %d date %s, changeover %s", CHANGEOVER_SEASON,
                format(max(aaa_band$official_date[aaa_band$season == CHANGEOVER_SEASON])), format(CHANGEOVER)))
md <- function(date) format(date, "%m-%d")
chal_first <- tapply(G$official_date[G$format == "challenge"], G$season[G$format == "challenge"], min)
chal_last <- tapply(G$official_date[G$format == "challenge"], G$season[G$format == "challenge"], max)
end_md <- vapply(AAA_SEASONS, function(s) {
  r <- coverage[coverage$season == s, ]
  min(md(r$complete_through), md(as.Date(chal_last[[as.character(s)]], origin = "1970-01-01")))
}, character(1))
WIN_LO <- max(md(as.Date(chal_first, origin = "1970-01-01")))
WIN_HI <- min(end_md)
ok_line("the DiD calendar window is not empty", WIN_LO <= WIN_HI, sprintf("%s to %s (month-day)", WIN_LO, WIN_HI))
stop_if_failed()
WINDOWS <- list(
  window = list(label = sprintf("challenge-format games %s to %s in every season (primary)", WIN_LO, WIN_HI),
                keep = function(x) md(x$official_date) >= WIN_LO & md(x$official_date) <= WIN_HI),
  all_on_disk = list(label = "every challenge-format game on disk (robustness)", keep = function(x) rep(TRUE, nrow(x))))

aaa_cells <- function(x) {
  x$bin <- as.integer(bin_index(x$d))
  dt <- data.table::as.data.table(x[, c("game_pk", "season", "edge", "bin", "count_class", "stand", "cs")])
  dt[, .(strikes = sum(cs), n = .N), by = .(game_pk, season, edge, bin, count_class, stand)]
}
aaa_fit <- function(agg) {
  fits <- list()
  for (e in EDGE_LEVELS) {
    a <- as.data.frame(agg[agg$edge == e, ])
    a$bin_f <- factor(a$bin, levels = sort(unique(a$bin)))
    a$season <- factor(as.character(a$season), levels = AAA_LEVELS)
    a$count_class <- factor(a$count_class, levels = CC_LEVELS)
    a$stand <- factor(a$stand, levels = STAND_LEVELS)
    fits[[e]] <- suppressWarnings(stats::glm(cbind(strikes, n - strikes) ~ 0 + bin_f + season + count_class + stand,
                                             family = stats::binomial(), data = a))
  }
  fits
}
aaa_estimands <- function(fits, w, season) {
  out <- list()
  for (e in EDGE_LEVELS) {
    f <- fits[[e]]
    bins <- as.integer(levels(f$model$bin_f))
    ctr <- bin_centre(bins)
    tt <- stats::delete.response(stats::terms(f))
    cf <- stats::coef(f); cf[is.na(cf)] <- 0
    prob <- Reduce(`+`, lapply(seq_len(nrow(w)), function(r) {
      nd <- data.frame(bin_f = factor(bins, levels = bins), season = factor(season, levels = AAA_LEVELS),
                       count_class = factor(w$count_class[r], levels = CC_LEVELS),
                       stand = factor(w$stand[r], levels = STAND_LEVELS))
      w$w[r] * stats::plogis(as.vector(stats::model.matrix(tt, nd, contrasts.arg = f$contrasts) %*% cf))
    }))
    v0 <- stats::qlogis(prob)
    j0 <- which(v0 > 0)[1]
    out[[e]] <- if (is.na(j0)) NA_real_ else crossing(v0, ctr, j0, +1L)
  }
  top <- ABS_TOP_FRAC * REF_HEIGHT_IN + out[["top"]]
  bot <- ABS_BOT_FRAC * REF_HEIGHT_IN - out[["bot"]]
  hw <- PLATE_HALF_W_FT * 12 + out[["side"]]
  c(top_in = top, bot_in = bot, half_width_in = hw, area_sqin = 2 * hw * (top - bot))
}
aaa_series <- function(x) {
  cells <- aaa_cells(x)
  agg <- cells[, .(strikes = sum(strikes), n = sum(n)), by = .(season, edge, bin, count_class, stand)]
  w <- binned_ref_weights(x[x$season == 2024L, ])
  fits <- aaa_fit(agg)
  point <- t(vapply(AAA_LEVELS, function(s) aaa_estimands(fits, w, s), numeric(4)))
  # the bootstrap: games resampled within season, each replicate refitted
  games <- unique(cells[, .(game_pk, season)])
  data.table::setorder(games, season, game_pk)
  cells[, gi := match(game_pk, games$game_pk)]
  set.seed(SEED)
  reps <- array(NA_real_, c(N_BOOT, length(AAA_LEVELS), 4L), dimnames = list(NULL, AAA_LEVELS, GEOM))
  by_season <- split(seq_len(nrow(games)), games$season)
  for (b in seq_len(N_BOOT)) {
    mult <- numeric(nrow(games))
    for (s in names(by_season)) {
      ix <- by_season[[s]]
      mult[ix] <- tabulate(sample.int(length(ix), length(ix), replace = TRUE), nbins = length(ix))
    }
    cells[, m := mult[gi]]
    ab <- cells[m > 0, .(strikes = sum(m * strikes), n = sum(m * n)), by = .(season, edge, bin, count_class, stand)]
    fb <- aaa_fit(ab)
    for (s in AAA_LEVELS) reps[b, s, ] <- aaa_estimands(fb, w, s)
  }
  list(point = point, reps = reps, n_games = table(factor(games$season, levels = AAA_SEASONS)),
       n_pitches = table(factor(x$season, levels = AAA_SEASONS)),
       dates = tapply(x$official_date, x$season, function(v) paste(format(min(v)), "to", format(max(v)))))
}
aaa <- list()
for (wn in names(WINDOWS)) {
  x <- aaa_band[WINDOWS[[wn]]$keep(aaa_band), ]
  t_b <- Sys.time()
  aaa[[wn]] <- aaa_series(x)
  share <- mean(stats::complete.cases(matrix(aaa[[wn]]$reps, N_BOOT)))
  ok_line(sprintf("AAA %s: >= 99%% of replicates complete", wn), share >= MIN_BOOT_SHARE,
          sprintf("%.1f%% of %d; %s; %.0f s", 100 * share, N_BOOT,
                  paste(sprintf("%s %s games", AAA_LEVELS, comma(aaa[[wn]]$n_games)), collapse = ", "),
                  as.numeric(difftime(Sys.time(), t_b, units = "secs"))))
  note(sprintf("AAA %s area", wn), paste(sprintf("%s %s", AAA_LEVELS, f2(aaa[[wn]]$point[, "area_sqin"])),
                                          collapse = ", "))
}
stop_if_failed()

# The MLB series, read and never refitted: W3.15's points (T3) and its 1,000 draws.
t3 <- utils::read.csv(T3_FILE, stringsAsFactors = FALSE)
MLB_ARMS <- list(
  binned = list(fit = "binned", label = "binned logistic, annex 5 (primary: the AAA series' own estimator)"),
  main = list(fit = "main", label = "bam, the chapter's frozen primary (robustness)"))
mlb <- list()
for (an in names(MLB_ARMS)) {
  dr <- utils::read.csv(MLB_DRAWS[[an]], check.names = FALSE)
  pt <- t3[t3$fit == MLB_ARMS[[an]]$fit & t3$estimand %in% GEOM, ]
  ok_line(sprintf("MLB %s: points and 1,000 draws for 2023 to 2025", an),
          nrow(dr) == N_BOOT && all(paste(rep(2023:2025, each = 4), GEOM, sep = "_") %in% names(dr)) &&
            all(vapply(2023:2025, function(s) all(GEOM %in% pt$estimand[pt$season == s]), logical(1))),
          sprintf("%s rows in %s; T3 fit %s", comma(nrow(dr)), basename(MLB_DRAWS[[an]]), MLB_ARMS[[an]]$fit))
  mlb[[an]] <- list(draws = dr, point = pt)
}
stop_if_failed()
mlb_point <- function(an, s, e) {
  p <- mlb[[an]]$point
  p$point[p$season == s & p$estimand == e]
}
mlb_draw <- function(an, s, e) mlb[[an]]$draws[[sprintf("%d_%s", s, e)]]

UNITS <- c(top_in = "in", bot_in = "in", half_width_in = "in", area_sqin = "sq in")
contrast_rows <- function(s0, s1) {
  out <- list()
  for (an in names(MLB_ARMS)) for (wn in names(WINDOWS)) for (e in GEOM) {
    a <- aaa[[wn]]
    m_pt <- mlb_point(an, s1, e) - mlb_point(an, s0, e)
    a_pt <- a$point[as.character(s1), e] - a$point[as.character(s0), e]
    m_dr <- mlb_draw(an, s1, e) - mlb_draw(an, s0, e)
    a_dr <- a$reps[, as.character(s1), e] - a$reps[, as.character(s0), e]
    d_dr <- m_dr - a_dr
    out[[length(out) + 1L]] <- data.frame(
      estimand = e, units = UNITS[[e]], mlb_estimator = an, aaa_window = wn,
      primary = an == "binned" && wn == "window" && e == "area_sqin",
      point = m_pt - a_pt, lo95 = qint(d_dr)[1], hi95 = qint(d_dr)[2],
      mlb_change = m_pt, mlb_change_lo95 = qint(m_dr)[1], mlb_change_hi95 = qint(m_dr)[2],
      aaa_change = a_pt, aaa_change_lo95 = qint(a_dr)[1], aaa_change_hi95 = qint(a_dr)[2],
      n_draws = sum(is.finite(d_dr)),
      aaa_games = sprintf("%d %d, %d %d", s0, a$n_games[[as.character(s0)]], s1, a$n_games[[as.character(s1)]]),
      aaa_dates = sprintf("%d %s; %d %s", s0, a$dates[[as.character(s0)]], s1, a$dates[[as.character(s1)]]),
      stringsAsFactors = FALSE)
  }
  do.call(rbind, out)
}

# The pre-trend: the AAA-versus-MLB 2023 to 2024 coefficient, (MLB 2024 - MLB 2023) - (AAA 2024 -
# AAA 2023). Its 95% interval must contain 0, or the DiD is reported as descriptive.
pt_rows <- contrast_rows(2023L, 2024L)
pt_rows$contains_zero <- pt_rows$lo95 <= 0 & pt_rows$hi95 >= 0
pt_rows$verdict <- ifelse(pt_rows$contains_zero, "pass", "fail")
pt_rows$consequence <- ifelse(pt_rows$contains_zero,
                              "interval contains 0: the pre-trend test passes",
                              "interval excludes 0: the DiD is reported as descriptive")
pretrend <- data.frame(
  test = "pre-trend", contrast = "2023_to_2024", pt_rows[, c("estimand", "units", "mlb_estimator", "aaa_window",
  "primary", "point", "lo95", "hi95", "contains_zero", "verdict", "consequence", "mlb_change", "mlb_change_lo95",
  "mlb_change_hi95", "aaa_change", "aaa_change_lo95", "aaa_change_hi95", "n_draws", "aaa_games", "aaa_dates")],
  rule = PRETREND_RULE, role = ROLE, parallel_trends = PARALLEL_TRENDS, stringsAsFactors = FALSE)
pp <- pretrend[pretrend$primary, ]
note("pre-trend, primary (area)", sprintf("%s sq in (95%% CI %s to %s): %s", sgn2(pp$point), sgn2(pp$lo95),
                                          sgn2(pp$hi95), pp$verdict))

# The DiD: the 2024 to 2025 step, the season MLB cut its grading buffer and AAA did not change
# format. The 2025 to 2026 step, the season MLB adopted the challenge system, needs AAA 2026,
# which the lake does not hold, and this phase makes no request.
dd <- contrast_rows(2024L, 2025L)
key <- paste(dd$estimand, dd$mlb_estimator, dd$aaa_window)
pk <- paste(pretrend$estimand, pretrend$mlb_estimator, pretrend$aaa_window)
dd$pretrend_point <- pretrend$point[match(key, pk)]
dd$pretrend_lo95 <- pretrend$lo95[match(key, pk)]
dd$pretrend_hi95 <- pretrend$hi95[match(key, pk)]
dd$pretrend_verdict <- pretrend$verdict[match(key, pk)]
reason <- function(v) {
  r <- c(if (P1_FAILED) "placebo P1 failed", if (v == "fail") "the pre-trend 95% interval excludes 0")
  if (length(r) == 0) "estimate: the pre-trend 95% interval contains 0" else paste0("descriptive: ", paste(r, collapse = "; "))
}
dd$reading <- vapply(dd$pretrend_verdict, reason, character(1))
dd$status <- "estimated"
na_rows <- data.frame(
  estimand = GEOM, units = unname(UNITS[GEOM]), mlb_estimator = "binned", aaa_window = "window", primary = FALSE,
  point = NA_real_, lo95 = NA_real_, hi95 = NA_real_, mlb_change = NA_real_, mlb_change_lo95 = NA_real_,
  mlb_change_hi95 = NA_real_, aaa_change = NA_real_, aaa_change_lo95 = NA_real_, aaa_change_hi95 = NA_real_,
  n_draws = 0L, aaa_games = "", aaa_dates = "", pretrend_point = NA_real_, pretrend_lo95 = NA_real_,
  pretrend_hi95 = NA_real_, pretrend_verdict = "", reading = "not estimated",
  status = "not estimated: no AAA 2026 feed is in the lake, and this phase makes no request", stringsAsFactors = FALSE)
did <- rbind(
  data.frame(contrast = "2024_to_2025", mlb_step = "2025 grading-buffer cut", dd, stringsAsFactors = FALSE),
  data.frame(contrast = "2025_to_2026", mlb_step = "2026 challenge system", na_rows, stringsAsFactors = FALSE))
did$role <- ROLE
did$parallel_trends <- PARALLEL_TRENDS
did$sign <- "MLB change minus AAA change; negative area: MLB's zone shrank more than AAA's"
dp <- did[did$primary, ]
note("DiD 2024 to 2025, primary (area)", sprintf("%s sq in (95%% CI %s to %s), %s", sgn2(dp$point), sgn2(dp$lo95),
                                                 sgn2(dp$hi95), dp$reading))

## --- the tables ---------------------------------------------------------------------------------------

csv_text <- function(df) {
  for (nm in names(df)) {
    v <- df[[nm]]
    if (is.double(v)) df[[nm]] <- f6(v)
    else if (is.logical(v)) df[[nm]] <- ifelse(is.na(v), "", ifelse(v, "TRUE", "FALSE"))
    else if (is.integer(v)) df[[nm]] <- ifelse(is.na(v), "", as.character(v))
  }
  con <- textConnection("txt", "w", local = TRUE)
  utils::write.table(df, con, sep = ",", row.names = FALSE, qmethod = "double", na = "")
  close(con)
  paste0(paste(txt, collapse = "\n"), "\n")
}
int_cols <- function(df, cols) { for (c in cols) df[[c]] <- as.integer(df[[c]]); df }
p3 <- int_cols(p3, c("season_from", "season_to", "n_games", "n_pitches", "n_boot"))
wkt <- int_cols(wkt, c("n_pitches", "n_pitches_challenge", "n_pitches_full_abs", "n_games_challenge",
                       "n_games_full_abs", "n_umpire_weeks", "n_umpires", "n_parameters"))
pretrend <- int_cols(pretrend, "n_draws")
did <- int_cols(did, "n_draws")
wkt$coverage <- COVERAGE
pretrend$coverage <- COVERAGE
did$coverage <- COVERAGE
p3$coverage <- COVERAGE

## --- the prose ----------------------------------------------------------------------------------------
# Every number below is read from the tables just built. One claim per sentence.

# "+4.23 pp (95% CI +3.52 to +4.94)": the unit sits before the bracket, so no sentence ends on "pp."
ci <- function(p, lo, hi, unit, d = 2) {
  s <- function(v) sprintf(paste0("%+.", d, "f"), v)
  sprintf("%s %s (95%% CI %s to %s)", s(p), unit, s(lo), s(hi))
}
EST_WORD <- c(binned = "binned", main = "bam")
WIN_WORD <- c(window = "the primary window", all_on_disk = "every AAA challenge-format game on disk")
EDGE_WORD <- c(side = "side edge", top = "top edge", bot = "bottom edge")
p3c <- p3[p3$row_type == "change", ]
p3s <- p3[p3$row_type == "season" & p3$verdict == "measured", ]
p3_first <- p3c[p3c$verdict != "not evaluable", ][1, ]
p3_na <- p3c[p3c$verdict == "not evaluable", ]
w_all <- wkt[wkt$season_scope == "pooled" & wkt$edge_scope == "all", ]
w_edge <- wkt[wkt$season_scope == "pooled" & wkt$edge_scope != "all", ]
w_season <- wkt[wkt$season_scope != "pooled", ]
pt_p <- pretrend[pretrend$primary, ]
pt_other <- pretrend[pretrend$mlb_estimator == "binned" & pretrend$aaa_window == "window" & !pretrend$primary, ]
did_p <- did[did$primary, ]
did_rb <- did[did$contrast == "2024_to_2025" & did$estimand == "area_sqin" & !did$primary, ]
pt_rb <- pretrend[pretrend$estimand == "area_sqin" & !pretrend$primary, ]
ed_word <- c(top_in = "top edge", bot_in = "bottom edge", half_width_in = "half-width")

prose <- c(
  "# The AAA arm",
  "",
  paste0("SOP W3.20. The tables are `out/tables/aaa_placebo.csv`, `out/ch1/tab/aaa_withinweek.csv`, ",
         "`out/ch1/tab/aaa_pretrend.csv` and `out/ch1/tab/aaa_did.csv`, written by `R/ch1/40_aaa_arm.R`."),
  "",
  paste0("The arm has three uses, reported in descending strength. First comes the machine-drift placebo. ",
         "Second comes the within-week alternation. Third comes the level difference-in-differences with AAA ",
         "as the control series."),
  "",
  paste0("Placebo P1 failed (T5). Every contrast here is therefore descriptive and names no cause."),
  "",
  paste0("**Coverage.** The lake holds these AAA feeds: ", COVERAGE, ". ",
         "The 2024 pull is still open in phase 07, so 2024 is read only as far as its feeds are complete."),
  "",
  "## 1. The machine-drift placebo (P3)",
  "",
  paste0("Machine days are keyless full-ABS games, where the machine makes every call. ",
         "Rule-net area is the area inside the machine-day 0.5 contour minus the published zone's area, for a 72-inch batter."),
  "",
  paste0(paste(sprintf("In %d the rule-net area is %s sq in over %s games.", p3s$season_from,
                       sprintf("%+.2f", p3s$estimate), comma(p3s$n_games)), collapse = " ")),
  "",
  if (nrow(p3_first) == 1 && !is.na(p3_first$estimate)) paste0(
    sprintf("From %d to %d it changes by %s sq in (90%% CI %s to %s). ", p3_first$season_from, p3_first$season_to,
            sprintf("%+.2f", p3_first$estimate), sprintf("%+.2f", p3_first$lo90), sprintf("%+.2f", p3_first$hi90)),
    sprintf("P3 %s its two one-sided tests at +/-3 sq in.", if (p3_first$verdict == "pass") "passes" else "fails")),
  "",
  if (nrow(p3_na) > 0) paste(sprintf("The %d to %d change is not evaluable, since %d has no keyless full-ABS game on disk.",
                                     p3_na$season_from, p3_na$season_to, p3_na$season_to), collapse = " "),
  "",
  "## 2. The within-week alternation",
  "",
  paste0(sprintf("The frame holds only dates strictly before the changeover date, %s. ", format(CHANGEOVER)),
         sprintf("That date is read from the `%s` row of `out/tables/aaa_format.csv`.", FORMAT_ROW)),
  "",
  paste0(sprintf("It keeps %s umpire-weeks in which one plate umpire worked both formats. ", comma(w_all$n_umpire_weeks)),
         sprintf("They cover %d umpires, %s full-ABS games and %s challenge-format games, from %s to %s.",
                 w_all$n_umpires, comma(w_all$n_games_full_abs), comma(w_all$n_games_challenge),
                 w_all$frame_first_date, w_all$frame_last_date)),
  "",
  paste0(sprintf("The frame has %s shadow-band pitches. ", comma(w_all$n_pitches)),
         sprintf("Their challenge-format called-strike rate minus the full-ABS rate is %s.",
                 ci(w_all$estimate, w_all$lo95, w_all$hi95, "pp"))),
  "",
  paste0("The comparison is within the umpire's own season, with week fixed effects. ",
         "It also holds location, count and handedness fixed."),
  "",
  paste0("On a full-ABS day the call is the machine's. ",
         "The contrast therefore reads as the umpire's departure from the machine zone at the same location."),
  "",
  paste(sprintf("In %d alone it is %s.", as.integer(w_season$season_scope),
                ci(w_season$estimate, w_season$lo95, w_season$hi95, "pp")), collapse = " "),
  "",
  paste(sprintf("On the %s it is %s.", EDGE_WORD[w_edge$edge_scope],
                ci(w_edge$estimate, w_edge$lo95, w_edge$hi95, "pp")), collapse = " "),
  "",
  "## 3. The level difference-in-differences",
  "",
  paste0("**", ROLE, "** The chapter's design is the three-regime MLB comparison. ",
         "AAA gives a second, weaker reading of the same seasons."),
  "",
  paste0("**Parallel trends.** Had the 2025 grading-buffer cut not happened, MLB's called zone would have changed ",
         "from 2024 to 2025 as AAA's challenge-format called zone did. This assumption is strong. ",
         "The two series differ in umpire populations, parks and Hawk-Eye installations, and AAA's zone is machine-set."),
  "",
  paste0("Both series use the annex section 5 binned logistic. MLB comes from W3.15's cached draws, and AAA from a ",
         "bootstrap of games within season. AAA's edges are net of its published rule, which changed from 2023 to 2024."),
  "",
  paste0(sprintf("The primary AAA window is %s to %s of each season, the span every season covers. ", WIN_LO, WIN_HI),
         "Every challenge-format game on disk is a robustness row."),
  "",
  paste0(sprintf("In %d both AAA series keep only dates strictly before the changeover date, %s. ",
                 CHANGEOVER_SEASON, format(CHANGEOVER)),
         "The challenge-format games on disk after it are binary-search probes, not a season sample."),
  "",
  paste0("**Pre-trend.** ", PRETREND_RULE),
  "",
  paste0(sprintf("On area the AAA-versus-MLB 2023 to 2024 coefficient is %s. ",
                 ci(pt_p$point, pt_p$lo95, pt_p$hi95, "sq in")),
         if (pt_p$contains_zero) "The interval contains 0, so the pre-trend test passes."
         else "The interval excludes 0, so the DiD is reported as descriptive."),
  "",
  paste(sprintf("On the %s the coefficient is %s, and the test %s.", ed_word[pt_other$estimand],
                ci(pt_other$point, pt_other$lo95, pt_other$hi95, "in"), ifelse(pt_other$contains_zero, "passes", "fails")),
        collapse = " "),
  "",
  paste(sprintf("With MLB's %s series and %s, the area coefficient is %s.", EST_WORD[pt_rb$mlb_estimator],
                WIN_WORD[pt_rb$aaa_window], ci(pt_rb$point, pt_rb$lo95, pt_rb$hi95, "sq in")), collapse = " "),
  "",
  paste0(sprintf("**Estimate.** From 2024 to 2025, MLB's area changes by %s sq in and AAA's by %s sq in. ",
                 sprintf("%+.2f", did_p$mlb_change), sprintf("%+.2f", did_p$aaa_change)),
         sprintf("The DiD, MLB's change minus AAA's, is %s.", ci(did_p$point, did_p$lo95, did_p$hi95, "sq in"))),
  "",
  paste0(if (grepl("^descriptive", did_p$reading)) "It is reported as descriptive. "
         else "It is reported as a supporting estimate. ",
         sprintf("Its reading in `aaa_did.csv` is \"%s\".", did_p$reading)),
  "",
  paste(sprintf("With MLB's %s series and %s, the DiD is %s.", EST_WORD[did_rb$mlb_estimator],
                WIN_WORD[did_rb$aaa_window], ci(did_rb$point, did_rb$lo95, did_rb$hi95, "sq in")), collapse = " "),
  "",
  paste0("The 2025 to 2026 step is not estimated. No AAA 2026 feed is in the lake, and this phase makes no request."),
  ""
)
prose <- prose[!vapply(prose, is.null, logical(1))]
prose_text <- paste0(paste(unlist(prose), collapse = "\n"), "\n")
prose_text <- gsub("\n{3,}", "\n\n", prose_text)

## --- write or compare -----------------------------------------------------------------------------------

outputs <- list(
  list(path = OUT_PLACEBO, text = csv_text(p3)),
  list(path = OUT_WEEK, text = csv_text(wkt)),
  list(path = OUT_PRETREND, text = csv_text(pretrend)),
  list(path = OUT_DID, text = csv_text(did)),
  list(path = OUT_PROSE, text = prose_text))
read_text <- function(path) if (file.exists(path)) paste(readLines(path, warn = FALSE), collapse = "\n") else NA_character_
for (o in outputs) {
  rel <- sub(paste0("^", ROOT, "/"), "", o$path)
  same <- identical(read_text(o$path), sub("\n$", "", o$text))
  if (CHECK_ONLY) {
    ok_line(sprintf("rebuild matches %s", basename(o$path)), same, rel)
  } else if (same) {
    note("unchanged, not rewritten", rel)
  } else {
    dir.create(dirname(o$path), recursive = TRUE, showWarnings = FALSE)
    tmp <- paste0(o$path, ".tmp-", Sys.getpid())
    writeLines(sub("\n$", "", o$text), tmp)
    ok_line(sprintf("written %s", basename(o$path)), file.rename(tmp, o$path), rel)
  }
}
cat(sprintf("%s %s: %d PASS, %d FAIL, %.0f s\n", STEP, if (CHECK_ONLY) "check" else "build", n_pass, length(failures),
            as.numeric(difftime(Sys.time(), t_start, units = "secs"))))
stop_if_failed()
quit(status = 0)
