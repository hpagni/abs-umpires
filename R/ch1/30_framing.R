#!/usr/bin/env Rscript
# R/ch1/30_framing.R - SOP W3.19, catcher framing by regime, and CH1-A11.
#
#   Rscript R/ch1/30_framing.R                                    the real table into out/
#   Rscript R/ch1/30_framing.R --table <parquet> --out <root> [--draws N] [--force] [--no-arms]
#
# THE STEP, SOP W3.19 verbatim: "Expected strike probability from the **catcher-free** regime
# surface; observed minus expected per catcher-season, converted to runs by the **count-specific**
# run value of a strike-versus-ball built from `delta_run_exp` (Tango's 0-0 figures, +0.034 ball
# and -0.042 strike, are the sanity check), with a flat 0.125 runs/strike version as the
# Savant-comparable robustness. Report per regime the SD across catchers, the top-30 mean per 100
# innings (Doolittle's exact comparable: 0.704 -> 0.565, about -20%), the same
# `Delta_buffer`/`Delta_ABS` decomposition, catcher-level split-half reliability per regime, and
# the new question nobody has asked: did the reliability of framing itself fall under ABS. Two
# 2026 conventions, both pre-registered: all pitches at the original call (primary, because the
# original call is what the catcher influenced), and challenged pitches excluded (the SIS
# convention, robustness). External validity test: 2022-2024 per-catcher values correlate >=0.85
# with Savant's published `catcher-framing` `rv_tot`; below that the framing result is demoted to
# secondary." (The SOP's question mark is dropped here only because the prose linter reads it.)
#
# WHAT IT DOES, in order.
#   1. P0 (D-61): every open called pitch of 2022-2026 through the last open day, the four games
#      without ABS hardware removed, on the primary height rule (D-R0-02, D-P4-04), through the
#      shared loader and apply_heights() of R/lib/ch1_fits.R. No |d| band: D-61 names P0 as the
#      framing surface's sample.
#   2. The framing surface, out/ch1/model/surface_framing.rds, which R/ch1/20_surfaces.R leaves to
#      this step: the frozen specification of annex section 2 (FROZEN_FORMULA_TEXT, unchanged) by
#      mgcv::bam on P0, with 1,000 draws from N(beta, Vc), seed 20260922. Its terms are season,
#      count class, handedness, pitch group, velocity, the location surface by season, count class
#      and handedness, and the umpire and umpire-season random effects. It has no catcher term,
#      and check_catcher_free() refuses to run if the formula ever names one. The fit is cached
#      on sha256(input frame) + seed + draw count + sha256(model code).
#   3. Expected strike probability of every P0 pitch from the exact lpmatrix (predict.gam, the
#      umpire effects included) at beta and at each draw. Observed minus expected is summed per
#      catcher-game, in strikes and in runs, for each draw. That cache is keyed on the fit's key,
#      the run-value table, the catcher-game map and this file.
#   4. Runs. rv(c) = mean(delta_run_exp | ball, count c) - mean(delta_run_exp | strike, count c)
#      over the 2022-2024 called pitches, the twelve counts separately: the runs one extra strike
#      saves the fielding team in that count. Tango's first-pitch figures (+0.034 ball, -0.042
#      strike) are checked against the table's 0-0 row to +/-0.010 runs and never enter it. The
#      flat 0.125 runs per strike is the second value type. A season-specific table is written
#      beside the pooled one and scored as a point-only column.
#   5. Innings caught, from outs recorded while each catcher was behind the plate, from the
#      warehouse's open pitch view (main_marts.v_pitch_open, analysis_set 'open', game_type R,
#      through the last open day). Per 100 innings is runs / innings x 100.
#   6. Intervals, joint: replicate b pairs coefficient draw b of the surface with catcher-bootstrap
#      replicate b. The bootstrap resamples catchers with replacement, one multinomial draw over every
#      qualified catcher of 2022-2026 (seed 20260922), and a catcher keeps his multiplicity in every
#      season, so a regime contrast is paired within catcher. Every statistic here is taken across
#      catchers, so the catcher is the resampling unit. 1,000 replicates.
#
# READINGS THE SOP LEAVES OPEN, fixed in this file before the first real run:
#   a. Qualified catcher-season: innings >= 25% of that season's mean team innings (the season's
#      total innings / 30). The set is fixed at the point estimate and held across replicates.
#   b. SD across catchers: the SD of runs per 100 innings over qualified catcher-seasons (raw), and
#      the signal SD, sqrt(max(0, raw variance - mean binomial noise variance)), the noise of a
#      catcher's rate being sum(rv^2 p (1 - p)) / (innings / 100)^2.
#   c. Top-30: the 30 qualified catcher-seasons with the highest runs per 100 innings, their mean.
#      Doolittle's 2026 figure covers games through 2026-05-18 (his article is dated 2026-05-19),
#      so that window is scored too, beside the full open 2026 season.
#   d. Split-half: each catcher-season's games in date order, odd against even game index; runs
#      per 1,000 called pitches in each half; Pearson over qualified catcher-seasons, then
#      Spearman-Brown 2r / (1 + r). Within one season only. A regime's value is its season's, and
#      2022-2024's is the mean of its three seasons.
#   e. The decomposition is R/lib/ch1_decomp.R's decompose_estimand() on the five season values,
#      unchanged. Whether reliability fell under ABS is read from its delta_abs component, with the
#      plain 2026-minus-2025 difference beside it. Every regime value of 2022-2024 (SD, top-30 mean,
#      reliability) is the mean of that statistic over its three seasons, replicate by replicate.
#      The components are read descriptively when W3.21's T5_placebos.csv says "descriptive" (P1
#      failed, CH1-A3): the prose then names no cause, exactly as the headline does.
#   f. SIS convention: a challenged pitch leaves the catcher's observed sum, expected sum and pitch
#      count. The surface is the same fit, which models the original call.
#   g. CH1-A11: Pearson r over 2022-2024 catcher-seasons on Savant's qualified list, matched by
#      MLBAM id, of this step's count-specific season runs (all pitches; no challenge exists before
#      2026) against rv_tot. The gate is r >= 0.85 on that pooled statistic. Per-season, Spearman
#      and flat-value correlations are reported beside it and do not gate. Savant's files are read
#      from the raw cache only (data/raw, through data/raw/_manifest.csv, the seasonStart form of
#      contracts/savant_framing.yml) and checked against that contract's sha256 pins. Nothing here
#      opens a network connection to any MLB or Savant host.
#   h. Robustness arms, point estimates: the framing surface on the |d| <= 8 in band only; W3.14's
#      main surface on the same band; the framing surface on P1's band; W3.14's ABS-measured
#      surface (H_abs heights) on the same P1 rows. The last pair is the height-source check.
#   i. Centring, fixed after the first real run of 2026-09-30 (docs/DEVIATIONS.md, W3.19): runs are
#      relative to the league-average catcher of the season, per called pitch, in every replicate. At
#      beta the uncentred league-average catcher earned about +0.4 runs per 100 innings in every season:
#      observed minus expected sums to zero within each strike class (the count_class term), but rises
#      with balls inside it, where the run value is largest. Across the draws that level moved with SD
#      0.16 to 0.38, the same for every catcher. Doolittle's and Savant's figures are relative to
#      average. See variant_cs(). The uncentred values are kept.
#
# THE GUARD. GD-12 as ch1_fits.R's start_run() applies it: the fit must descend from the pushed
# prereg-v1, and the code that runs must be committed so the receipt's git_sha names it. start_run()
# checks every file under R/ch1, R/lib and tools/comms; this script checks the files it executes,
# R/ch1/30_framing.R and FIT_CODE, because in the shared tree other lanes' uncommitted files there
# would refuse a run whose own code is committed. A synthetic table runs anywhere outside the repo.
#
# WHAT IT WRITES, under --out (out/ for the real run), every number in a CSV before any prose:
#   ch1/model/surface_framing.rds, draws_vc_framing.rds, framing_cache.rds, framing_arms_cache.rds
#   models/surface_framing/provenance.json (and the union ch1/model/provenance.json), models/ch1_W3_19/
#   ch1/tab/framing_{sample,sanity,run_values,catcher_seasons,by_season,decomposition,reliability_change,
#     doolittle,validity,validity_pairs,arms,replicate_completeness,prose_numbers}.csv
#   tables/ch1_framing_{by_regime,decomposition,reliability,doolittle,validity}.csv, the publication tables
#   ch1/prose/framing.md, whose every number is listed in ch1/tab/framing_prose_numbers.csv.
# Every catcher-season value sits in framing_catcher_seasons.csv (window "season", and window
# "2026_through_05-18" for Doolittle's comparable), each with its through_date, none after the last open
# day. tests/testthat/test-ch1-framing.R re-derives the tables from it.
#   --force refits and recomputes past every cache; --no-arms skips the point-estimate arms.
# Exit 0 when every check passes, 1 when one fails, 4 when a guard refuses.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))
suppressPackageStartupMessages(library(Matrix))

STEP   <- "W3.19"
SCRIPT <- "R/ch1/30_framing.R"
EXTRA_COLS <- c("catcher", "challenged", "is_overturned", "delta_run_exp")
HASH_VARS  <- c("pitch_uid", "cs", "season", "count_class", "stand", "pitch_group", "x_mid", "zn", "velo",
                "umpire_hp_id", "umpire_season")

RV_SEASONS  <- 2022:2024            # the count table's seasons: no challenge rewrites a call there
FLAT_RUNS   <- 0.125                # SOP W3.19: the Savant-comparable flat value per strike
TANGO_00    <- c(ball = 0.034, strike = -0.042)   # SOP W3.19: the sanity check, never an input
TANGO_TOL   <- 0.010
N_TEAMS     <- 30L
QUAL_SHARE  <- 0.25
TOP_N       <- 30L
PER_INN     <- 100
PER_PITCHES <- 1000
A11_R       <- 0.85                 # CH1-A11
A11_SEASONS <- 2022:2024
DOOLITTLE   <- c(y2025 = 0.704, y2026 = 0.565, change_pct = -20)
DOOLITTLE_THROUGH <- as.Date("2026-05-18")
CHUNK       <- 20000L
SYN_CALLED_PER_INNING <- 8.5        # a synthetic table has no outs; its innings are called / 8.5
VALUE_TYPES <- c("cnt", "flat")
CONVENTIONS <- c("original", "sis")
VALUE_LABEL <- c(cnt = "count-specific run value from delta_run_exp (2022-2024 table)",
                 flat = "flat 0.125 runs per strike (Savant-comparable)")
CONV_LABEL  <- c(original = "every pitch at its original call (primary)",
                 sis = "challenged pitches excluded (SIS convention)")
METRICS <- c("sd_raw_per100", "sd_signal_per100", "top30_mean_per100", "mean_per100", "split_half_r",
             "reliability_sb")
DECOMP_METRICS <- c("sd_signal_per100", "sd_raw_per100", "top30_mean_per100", "reliability_sb")
METRIC_UNITS <- c(sd_raw_per100 = "runs per 100 innings", sd_signal_per100 = "runs per 100 innings",
                  top30_mean_per100 = "runs per 100 innings", mean_per100 = "runs per 100 innings",
                  split_half_r = "correlation", reliability_sb = "reliability")

## --- the guard ---------------------------------------------------------------------------------

framing_start <- function(opt) {
  table <- opt_get(opt, "table", mart_table())
  out <- opt_get(opt, "out", file.path(ROOT, "out"))
  if (!file.exists(table)) die(STEP, ": no analysis table at ", table)
  syn <- table_is_synthetic(table)
  code <- unique(c(SCRIPT, FIT_CODE))
  if (syn) {
    if (inside(out, ROOT)) {
      refuse(STEP, sprintf("a synthetic run writes outside the repository; %s is inside %s", out, ROOT))
    }
    record("mode", sprintf("SYNTHETIC table %s; GD-12 not required", table))
    gd <- list(ok = NA, detail = "synthetic table, GD-12 not applied")
  } else {
    if (!is.null(opt[["draws"]])) refuse(STEP, "--draws is a dry-run setting; real data runs the pre-registered value")
    gd <- gd12_ancestry()
    if (!isTRUE(gd$ok)) refuse(STEP, sprintf("real data, and GD-12 failed (%s)", gd$detail))
    tr <- git_out(c("ls-files", "--error-unmatch", "--", code))
    dirty <- git_out(c("status", "--porcelain", "--", code))$out
    if (tr$status != 0L || length(dirty) > 0L) {
      refuse(STEP, sprintf("real data, and the code this run executes is not committed, so git_sha would not name it: %s",
                           paste(c(if (tr$status != 0L) tr$out, dirty), collapse = "; ")))
    }
    record("mode", sprintf("REAL table %s; GD-12 %s; committed and clean: %s", table, gd$detail,
                           paste(code, collapse = ", ")))
  }
  ctx <- list(step = STEP, table = normalizePath(table), out = out, paths = out_paths(out), synthetic = syn,
              gd12 = gd, last_open = last_open_date(), script = SCRIPT, code_shas = code_hashes(SCRIPT),
              n_draws = if (syn) opt_int(opt, "draws", N_DRAWS) else N_DRAWS)
  ctx$paths$prose <- file.path(out, "ch1", "prose")
  record("last open day", format(ctx$last_open))
  record("replicates", sprintf("%d, each one draw from N(beta, %s) paired with one catcher-bootstrap replicate",
                               ctx$n_draws, INTERVAL_COV))
  ctx
}

# SOP W3.19 and build note 1: the expected surface is catcher-free. The formula is the frozen text;
# this refuses if a catcher, fielder or pitcher-catcher term ever enters it.
check_catcher_free <- function(formula_text) {
  hit <- grepl("catcher|fielder|framing", formula_text, ignore.case = TRUE)
  check("framing surface is catcher-free", !hit && identical(formula_text, FROZEN_FORMULA_TEXT),
        "the frozen formula of annex section 2, no catcher term, no by-catcher smooth, no catcher random effect")
  if (hit) die("the expected-strike surface names a catcher term; W3.19 stops rather than refit")
}

## --- P0 ------------------------------------------------------------------------------------------

load_p0 <- function(ctx, opt) {
  d <- load_table(ctx, extra = EXTRA_COLS)
  miss <- setdiff(EXTRA_COLS, names(d))
  if (length(miss) > 0L) die("the analysis table lacks ", paste(miss, collapse = ", "))
  d$catcher <- as.integer(d$catcher)
  d$challenged <- as.logical(d$challenged)
  d$is_overturned <- as.logical(d$is_overturned)
  d$balls <- as.integer(d$balls)
  d$strikes <- as.integer(d$strikes)
  check("every P0 pitch names its catcher", !anyNA(d$catcher), sprintf("%s rows", comma(nrow(d))))
  check("challenge flags are complete, and 2026-only", !anyNA(d$challenged) && !any(d$challenged & d$season < 2026L),
        sprintf("%s challenged pitches in 2026", comma(sum(d$challenged, na.rm = TRUE))))
  check("counts lie in 0-3 balls, 0-2 strikes", all(d$balls %in% 0:3) && all(d$strikes %in% 0:2), "")
  cal <- read_calibration(ctx, opt)
  p0 <- apply_heights(d, primary_height_rule(opt), cal, ctx)
  rm(d)
  list(rows = p0, cal = cal)
}

## --- run values --------------------------------------------------------------------------------

rv_one <- function(r, label) {
  r <- r[is.finite(r$delta_run_exp) & !r$challenged, c("balls", "strikes", "cs", "delta_run_exp")]
  cnt <- expand.grid(strikes = 0:2, balls = 0:3)[, c("balls", "strikes")]
  do.call(rbind, lapply(seq_len(nrow(cnt)), function(k) {
    i <- r$balls == cnt$balls[k] & r$strikes == cnt$strikes[k]
    yb <- r$delta_run_exp[i & r$cs == 0L]
    ys <- r$delta_run_exp[i & r$cs == 1L]
    data.frame(table = label, balls = cnt$balls[k], strikes = cnt$strikes[k],
               count = paste0(cnt$balls[k], "-", cnt$strikes[k]), n_ball = length(yb), n_strike = length(ys),
               mean_dre_ball = mean(yb), mean_dre_strike = mean(ys), rv_strike_vs_ball = mean(yb) - mean(ys),
               stringsAsFactors = FALSE)
  }))
}

run_value_tables <- function(rows) {
  pooled <- rv_one(rows[rows$season %in% RV_SEASONS, , drop = FALSE], "pooled_2022_2024")
  per <- do.call(rbind, lapply(SEASONS, function(s) rv_one(rows[rows$season == s, , drop = FALSE], paste0("season_", s))))
  tab <- rbind(pooled, per)
  ok <- all(tab$n_ball > 0 & tab$n_strike > 0) && all(is.finite(tab$rv_strike_vs_ball)) && nrow(pooled) == 12L
  check("run values: twelve counts, every cell observed", ok,
        sprintf("pooled table %d counts, %s pitches", nrow(pooled), comma(sum(pooled$n_ball + pooled$n_strike))))
  check("run values: a strike is worth more to the defence than a ball in every count",
        all(pooled$rv_strike_vs_ball > 0),
        sprintf("rv from %.3f (%s) to %.3f (%s)", min(pooled$rv_strike_vs_ball),
                pooled$count[which.min(pooled$rv_strike_vs_ball)], max(pooled$rv_strike_vs_ball),
                pooled$count[which.max(pooled$rv_strike_vs_ball)]))
  tab
}

# Tango's 0-0 figures, checked against the pooled table. They are never used as an input.
tango_check <- function(rvt) {
  z <- rvt[rvt$table == "pooled_2022_2024" & rvt$count == "0-0", ]
  gb <- z$mean_dre_ball - TANGO_00[["ball"]]
  gs <- z$mean_dre_strike - TANGO_00[["strike"]]
  check("Tango sanity check: 0-0 ball value", abs(gb) <= TANGO_TOL,
        sprintf("%+.4f against Tango's %+.3f (tolerance %.3f)", z$mean_dre_ball, TANGO_00[["ball"]], TANGO_TOL))
  check("Tango sanity check: 0-0 strike value", abs(gs) <= TANGO_TOL,
        sprintf("%+.4f against Tango's %+.3f (tolerance %.3f)", z$mean_dre_strike, TANGO_00[["strike"]], TANGO_TOL))
  data.frame(check = c("tango_00_ball", "tango_00_strike"), value = c(z$mean_dre_ball, z$mean_dre_strike),
             reference = unname(TANGO_00[c("ball", "strike")]), tolerance = TANGO_TOL,
             pass = c(abs(gb) <= TANGO_TOL, abs(gs) <= TANGO_TOL),
             note = "the pooled 2022-2024 table's 0-0 row; a sanity check, not an input", stringsAsFactors = FALSE)
}

rv_lookup <- function(rvt, label, balls, strikes) {
  z <- rvt[rvt$table == label, ]
  z$rv_strike_vs_ball[match(paste(balls, strikes), paste(z$balls, z$strikes))]
}

## --- the warehouse: innings caught --------------------------------------------------------------

duckdb_file <- function() {
  code <- "from absump.paths import DUCKDB_PATH; print(DUCKDB_PATH)"
  out <- suppressWarnings(system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python", "-c", shQuote(code)),
                                  stdout = TRUE, stderr = TRUE))
  trimws(out[length(out)])
}

# A read-only attach, retried for up to 15 minutes while a dbt build holds the write lock.
wh_query <- function(ctx, sql) {
  con <- suppressMessages(DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:"))
  on.exit(try(DBI::dbDisconnect(con, shutdown = TRUE), silent = TRUE), add = TRUE)
  db <- duckdb_file()
  ok <- FALSE
  for (attempt in 1:60) {
    ok <- tryCatch({
      DBI::dbExecute(con, sprintf("ATTACH %s AS abs (READ_ONLY)", DBI::dbQuoteString(con, db)))
      TRUE
    }, error = function(e) {
      if (attempt %% 10L == 1L) record("warehouse attach", sprintf("attempt %d: %s", attempt, conditionMessage(e)))
      FALSE
    })
    if (ok) break
    Sys.sleep(15)
  }
  if (!ok) die("could not attach the warehouse read-only at ", db)
  DBI::dbGetQuery(con, sql, params = list(format(ctx$last_open)))
}

# Outs recorded in each plate appearance, credited to the catcher on its last pitch: the next plate
# appearance's outs minus this one's inside a half-inning, 3 minus this one's at the end of a
# half-inning, and 0 on a game-ending bottom half the batting side wins.
INNINGS_SQL <- "
WITH p AS (
  SELECT v.game_pk, v.season, v.inning, v.inning_topbot, v.at_bat_number, v.pitch_number, v.outs_when_up,
         v.fielder_2, v.bat_score_diff, v.bat_score, v.post_bat_score
  FROM abs.main_marts.v_pitch_open AS v
  WHERE v.level = 'mlb' AND v.game_type = 'R' AND v.analysis_set = 'open'
    AND v.official_date <= CAST(? AS DATE)),
pa AS (
  SELECT game_pk, season, inning, inning_topbot, at_bat_number,
         arg_max(fielder_2, pitch_number) AS catcher, min(outs_when_up) AS outs0,
         arg_max(bat_score_diff + post_bat_score - bat_score, pitch_number) AS lead_after
  FROM p GROUP BY game_pk, season, inning, inning_topbot, at_bat_number),
sq AS (
  SELECT *, lead(outs0) OVER (PARTITION BY game_pk, inning, inning_topbot ORDER BY at_bat_number) AS next_outs,
         max(inning * 2 + CAST(inning_topbot = 'Bot' AS INTEGER)) OVER (PARTITION BY game_pk) AS last_half
  FROM pa),
o AS (
  SELECT game_pk, season, catcher,
         CASE WHEN next_outs IS NOT NULL THEN greatest(next_outs - outs0, 0)
              WHEN inning * 2 + CAST(inning_topbot = 'Bot' AS INTEGER) = last_half AND inning_topbot = 'Bot'
                   AND lead_after > 0 THEN 0
              ELSE greatest(3 - outs0, 0) END AS outs
  FROM sq)
SELECT CAST(game_pk AS INTEGER) AS game_pk, CAST(season AS INTEGER) AS season, CAST(catcher AS INTEGER) AS catcher,
       CAST(sum(outs) AS DOUBLE) AS outs
FROM o GROUP BY game_pk, season, catcher"

innings_caught <- function(ctx, rows) {
  if (ctx$synthetic) {
    k <- paste(rows$season, rows$game_pk, rows$catcher)
    u <- !duplicated(k)
    n <- tabulate(match(k, k[u]), sum(u))
    inn <- data.frame(game_pk = rows$game_pk[u], season = rows$season[u], catcher = rows$catcher[u],
                      outs = 3 * n / SYN_CALLED_PER_INNING)
    record("innings", sprintf("SYNTHETIC: called pitches / %.1f per catcher-game", SYN_CALLED_PER_INNING))
    return(inn)
  }
  inn <- wh_query(ctx, INNINGS_SQL)
  inn <- inn[inn$game_pk %in% rows$game_pk & !is.na(inn$catcher), , drop = FALSE]
  g <- unique(rows$game_pk)
  per_game <- tapply(inn$outs, inn$game_pk, sum) / 3 / 2
  check("innings: every P0 game has innings caught", all(g %in% inn$game_pk),
        sprintf("%s of %s games; %.3f innings per team-game", comma(sum(g %in% inn$game_pk)), comma(length(g)),
                mean(per_game)))
  check("innings: team-game innings are plausible", mean(per_game) > 8.5 && mean(per_game) < 9.2,
        sprintf("mean %.3f, the league plays about 8.9", mean(per_game)))
  inn
}

## --- Savant's catcher-framing files, from the raw cache only ---------------------------------------

# The seasonStart form of contracts/savant_framing.yml (its year= form is ignored by the endpoint),
# the latest status-200 manifest row for that URL, the zstd body decompressed by the project's own
# Python environment, and its sha256 checked against the contract's pin for that finished season.
savant_contract <- function() {
  y <- yaml::read_yaml(file.path(ROOT, "contracts", "savant_framing.yml"))
  list(template = gsub("\\s+", "", y$url_template), pins = y$static_baselines)
}

savant_season <- function(season, con, manifest) {
  url <- sub("{min_param}", "q", gsub("{season}", season, con$template, fixed = TRUE), fixed = TRUE)
  m <- manifest[manifest$url == url & manifest$http_status == "200", , drop = FALSE]
  if (nrow(m) == 0L) return(list(ok = FALSE, detail = sprintf("%d: no cached status-200 body for %s", season, url)))
  m <- m[order(m$fetched_at_utc), , drop = FALSE][nrow(m), ]
  src <- m$dest_path
  if (!startsWith(src, "/")) src <- file.path(ROOT, src)
  if (!file.exists(src)) return(list(ok = FALSE, detail = sprintf("%d: cached body missing at %s", season, src)))
  tmp <- tempfile(fileext = ".csv")
  on.exit(unlink(tmp), add = TRUE)
  py <- paste("import sys, zstandard",
              "raw = zstandard.ZstdDecompressor().stream_reader(open(sys.argv[1], 'rb')).read()",
              "open(sys.argv[2], 'wb').write(raw)", sep = "; ")
  st <- suppressWarnings(system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python", "-c", shQuote(py),
                                         shQuote(src), shQuote(tmp)), stdout = TRUE, stderr = TRUE))
  if (!file.exists(tmp) || file.size(tmp) == 0L) return(list(ok = FALSE, detail = paste(season, st, collapse = " ")))
  sha <- sha256_file(tmp)
  pin <- con$pins[[as.character(season)]]
  pinned <- !is.null(pin) && identical(sha, pin$sha256) && identical(sha, m$sha256)
  txt <- readLines(tmp, encoding = "UTF-8", warn = FALSE)
  txt[1] <- sub("^﻿", "", txt[1])
  df <- utils::read.csv(text = paste(txt, collapse = "\n"), stringsAsFactors = FALSE, check.names = FALSE)
  list(ok = pinned && nrow(df) > 0L, rows = df, url = url, sha256 = sha, fetched = m$fetched_at_utc,
       detail = sprintf("%d: %d catchers, sha256 %s %s the contract pin, fetched %s", season, nrow(df),
                        substr(sha, 1, 12), if (pinned) "matches" else "DOES NOT match", m$fetched_at_utc))
}

savant_table <- function(ctx) {
  if (ctx$synthetic) return(NULL)
  con <- savant_contract()
  manifest <- utils::read.csv(file.path(ROOT, "data", "raw", "_manifest.csv"), stringsAsFactors = FALSE,
                              colClasses = "character")
  out <- lapply(A11_SEASONS, function(s) {
    r <- savant_season(s, con, manifest)
    check(sprintf("Savant catcher-framing %d read from the raw cache", s), isTRUE(r$ok), r$detail)
    if (!isTRUE(r$ok)) return(NULL)
    data.frame(season = s, id = as.integer(r$rows$id), name = r$rows$name, savant_pitches = as.numeric(r$rows$pitches),
               savant_rv_tot = as.numeric(r$rows$rv_tot), source_sha256 = r$sha256, fetched_utc = r$fetched,
               stringsAsFactors = FALSE)
  })
  do.call(rbind, out)
}

## --- catcher-games and catcher-seasons ------------------------------------------------------------

build_cg <- function(rows, inn) {
  key_r <- paste(rows$season, rows$game_pk, rows$catcher, sep = ":")
  gd <- unique(rows[, c("game_pk", "official_date")])
  if (anyDuplicated(gd$game_pk)) die("a game carries two official dates")
  inn <- inn[inn$game_pk %in% gd$game_pk, , drop = FALSE]
  key_i <- paste(inn$season, inn$game_pk, inn$catcher, sep = ":")
  if (anyDuplicated(key_i)) die("the innings query returned a catcher-game twice")
  keys <- sort(unique(c(key_r, key_i)))
  parts <- do.call(rbind, strsplit(keys, ":", fixed = TRUE))
  cg <- data.frame(key = keys, season = as.integer(parts[, 1]), game_pk = as.integer(parts[, 2]),
                   catcher = as.integer(parts[, 3]), stringsAsFactors = FALSE)
  cg$official_date <- gd$official_date[match(cg$game_pk, gd$game_pk)]
  cg$outs <- 0
  cg$outs[match(key_i, keys)] <- inn$outs
  cg$innings <- cg$outs / 3
  ir <- match(key_r, keys)
  cg$n <- tabulate(ir, nrow(cg))
  cg$n_ch <- tabulate(ir[rows$challenged], nrow(cg))
  cg$cs_key <- paste(cg$season, cg$catcher, sep = ":")
  o <- order(cg$cs_key, cg$official_date, cg$game_pk)
  gi <- integer(nrow(cg))
  gi[o] <- stats::ave(seq_along(o), cg$cs_key[o], FUN = seq_along)
  cg$game_index <- gi
  cg$half <- ifelse(gi %% 2L == 1L, "odd", "even")
  cg$dw <- cg$season == 2026L & cg$official_date <= DOOLITTLE_THROUGH
  list(cg = cg, row_cg = ir)
}

build_cs <- function(cg, keep = rep(TRUE, nrow(cg))) {
  sub <- cg[keep, , drop = FALSE]
  keys <- sort(unique(sub$cs_key))
  cs <- data.frame(cs_key = keys, season = as.integer(sub("[:].*$", "", keys)),
                   catcher = as.integer(sub("^.*[:]", "", keys)), stringsAsFactors = FALSE)
  j <- match(sub$cs_key, keys)
  cs$games <- tabulate(j, nrow(cs))
  cs$innings <- as.vector(rowsum(sub$innings, j, reorder = TRUE))
  cs$called_pitches <- as.vector(rowsum(sub$n, j, reorder = TRUE))
  cs$challenged_pitches <- as.vector(rowsum(sub$n_ch, j, reorder = TRUE))
  cs$first_date <- as.Date(tapply(sub$official_date, j, min), origin = "1970-01-01")
  cs$through_date <- as.Date(tapply(sub$official_date, j, max), origin = "1970-01-01")
  team_inn <- tapply(cs$innings, cs$season, sum) / N_TEAMS
  cs$qual_innings <- QUAL_SHARE * as.vector(team_inn[as.character(cs$season)])
  cs$qualified <- cs$innings >= cs$qual_innings
  # The aggregation maps: catcher-season x catcher-game, all games and each half.
  jj <- match(cg$cs_key, keys)
  jj[!keep] <- NA
  mk <- function(sel) {
    w <- which(sel & !is.na(jj))
    Matrix::sparseMatrix(i = jj[w], j = w, x = 1, dims = c(nrow(cs), nrow(cg)))
  }
  list(cs = cs, A = mk(rep(TRUE, nrow(cg))), A_odd = mk(cg$half == "odd"), A_even = mk(cg$half == "even"))
}

## --- the framing surface -----------------------------------------------------------------------

frame_sha <- function(ff) hex(openssl::sha256(serialize(ff[, HASH_VARS], NULL)))
model_code_sha <- function() {
  sha256_text(paste(c(FROZEN_FORMULA_TEXT, deparse(fit_surface), deparse(coef_draws), deparse(fit_frame),
                      deparse(code_covariates), deparse(code_period), deparse(make_spec),
                      as.character(utils::packageVersion("mgcv")), R.version.string), collapse = "\n"))
}

framing_fit <- function(ctx, p0, ff, force) {
  spec <- make_spec("main")
  check_catcher_free(spec$formula)
  parts <- list(input_frame_sha256 = frame_sha(ff), seed = DRAW_SEED, n_draws = ctx$n_draws,
                model_code_sha256 = model_code_sha())
  key <- sha256_text(paste(unlist(parts), collapse = "|"))
  f_fit <- file.path(ctx$paths$model, "surface_framing.rds")
  f_dr <- file.path(ctx$paths$model, "draws_vc_framing.rds")
  if (!force && file.exists(f_fit) && file.exists(f_dr)) {
    o <- readRDS(f_fit)
    if (identical(o$cache_key, key)) {
      record("framing surface: cache hit", sprintf("key %s; fitted in %.0f s on %s rows", substr(key, 1, 16),
                                                   o$seconds, comma(o$n_rows)))
      return(list(m = o$m, spec = o$spec, draws = readRDS(f_dr), key = key, parts = parts, cached = TRUE,
                  seconds = o$seconds))
    }
    record("framing surface: cache stale", sprintf("stored key %s, this run's %s", substr(format(o$cache_key), 1, 16),
                                                   substr(key, 1, 16)))
    rm(o)
    invisible(gc())
  }
  record("framing surface: fitting", sprintf("%s rows, the frozen formula, P0 without a band", comma(nrow(ff))))
  ft <- fit_surface(ff, spec)
  check("framing surface: bam converged", ft$converged,
        sprintf("%s rows, %s coefficients, edf %.1f, largest fREML gradient %.1e, %.0f s", comma(nrow(ff)),
                comma(ft$n_coef), ft$edf, ft$grad_max, ft$seconds))
  if (length(ft$warnings) > 0L) record("framing surface: bam warnings", paste(ft$warnings, collapse = " | "))
  cd <- coef_draws(ft$m, ctx$n_draws, DRAW_SEED)
  check(sprintf("framing surface: %d draws from N(beta, %s)", ctx$n_draws, INTERVAL_COV),
        identical(dim(cd), c(ctx$n_draws, ft$n_coef)) && all(is.finite(cd)), "")
  ensure_dir(ctx$paths$model)
  saveRDS(list(m = ft$m, spec = ft$spec, fit = "framing", arm = "W3.19 framing surface (P0, catcher-free)",
               height_rule = attr(p0, "height_rule"), height_rule_key = attr(p0, "height_rule_key"),
               cache_key = key, cache_parts = parts, n_rows = nrow(ff), seconds = ft$seconds,
               warnings = ft$warnings), f_fit)
  saveRDS(cd, f_dr)
  prov <- provenance(ctx, "surface_framing", p0, DRAW_SEED, ctx$paths$model,
                     extra = list(formula = spec$formula, family = "binomial", method = "fREML", discrete = TRUE,
                                  n_coef = ft$n_coef, edf = ft$edf, fit_seconds = ft$seconds,
                                  converged = ft$converged, freml_grad_max = ft$grad_max,
                                  arm = "W3.19 framing surface (P0, catcher-free)",
                                  height_rule = attr(p0, "height_rule"), height_rule_key = attr(p0, "height_rule_key"),
                                  n_draws = ctx$n_draws, interval_cov = INTERVAL_COV, draw_seed = DRAW_SEED,
                                  cache_sha256 = key, cache_parts = parts,
                                  files = list(basename(f_fit), basename(f_dr)),
                                  n_umpires = length(unique(p0$umpire_hp_id)),
                                  rows_by_season = as.list(table(p0$season))))
  write_receipt(ctx, prov, ctx$paths$model)
  record("framing surface: written", sprintf("%s (%.0f MB), %s", f_fit, file.size(f_fit) / 1e6, f_dr))
  list(m = ft$m, spec = ft$spec, draws = cd, key = key, parts = parts, cached = FALSE, seconds = ft$seconds)
}

## --- expected strikes, observed minus expected, per catcher-game and per draw ----------------------

add_rows <- function(M, rs) {
  idx <- as.integer(rownames(rs))
  M[idx, ] <- M[idx, ] + rs
  M
}
add_vec <- function(v, g, x) {
  rs <- rowsum(x, g)
  idx <- as.integer(rownames(rs))
  v[idx] <- v[idx] + as.vector(rs)
  v
}

# For every chunk of P0: the exact lpmatrix, eta at beta and at each draw, p = plogis(eta). Sums per
# catcher-game: S = sum(cs - p), R = sum(rv (cs - p)); for the challenged pitches separately (the SIS
# convention subtracts them); and at beta only the noise terms sum(p (1 - p)), sum(rv^2 p (1 - p)),
# the season-table runs, and p itself for the arms.
propagate <- function(m, ff, rows, row_cg, ncg, rv, rv_season, draws) {
  beta <- stats::coef(m)
  if (!identical(colnames(draws), names(beta))) die("the draws' columns are not the fit's coefficients")
  Bm <- cbind(beta, t(draws))
  nb <- ncol(Bm)
  ch <- rows$challenged
  chcg <- sort(unique(row_cg[ch]))
  S <- matrix(0, ncg, nb); R <- matrix(0, ncg, nb)
  Sch <- matrix(0, length(chcg), nb); Rch <- matrix(0, length(chcg), nb)
  U0 <- V0 <- Rs0 <- U0ch <- V0ch <- Rs0ch <- numeric(ncg)
  p0 <- numeric(nrow(ff))
  n <- nrow(ff)
  starts <- seq(1L, n, by = CHUNK)
  t0 <- Sys.time()
  for (k in seq_along(starts)) {
    i <- starts[k]:min(n, starts[k] + CHUNK - 1L)
    X <- mgcv::predict.gam(m, ff[i, , drop = FALSE], type = "lpmatrix")
    P <- stats::plogis(X %*% Bm)
    rm(X)
    g <- row_cg[i]
    E <- rows$cs[i] - P
    S <- add_rows(S, rowsum(E, g))
    ER <- E * rv[i]
    R <- add_rows(R, rowsum(ER, g))
    p0[i] <- P[, 1]
    q <- P[, 1] * (1 - P[, 1])
    U0 <- add_vec(U0, g, q)
    V0 <- add_vec(V0, g, q * rv[i]^2)
    Rs0 <- add_vec(Rs0, g, E[, 1] * rv_season[i])
    c_i <- which(ch[i])
    if (length(c_i) > 0L) {
      gc_ <- match(g[c_i], chcg)
      rs <- rowsum(E[c_i, , drop = FALSE], gc_); Sch[as.integer(rownames(rs)), ] <- Sch[as.integer(rownames(rs)), ] + rs
      rs <- rowsum(ER[c_i, , drop = FALSE], gc_); Rch[as.integer(rownames(rs)), ] <- Rch[as.integer(rownames(rs)), ] + rs
      U0ch <- add_vec(U0ch, g[c_i], q[c_i])
      V0ch <- add_vec(V0ch, g[c_i], q[c_i] * rv[i][c_i]^2)
      Rs0ch <- add_vec(Rs0ch, g[c_i], E[c_i, 1] * rv_season[i][c_i])
    }
    rm(P, E, ER)
    if (k %% 10L == 0L || k == length(starts)) {
      record("propagation", sprintf("%d of %d chunks, %.0f s", k, length(starts),
                                    as.numeric(difftime(Sys.time(), t0, units = "secs"))))
    }
  }
  list(S = S, R = R, Sch = Sch, Rch = Rch, chcg = chcg, U0 = U0, V0 = V0, Rs0 = Rs0, U0ch = U0ch, V0ch = V0ch,
       Rs0ch = Rs0ch, p0 = p0, n_rep = nb - 1L)
}

framing_sums <- function(ctx, fit, ff, rows, cgm, rv, rv_season, rvt, force) {
  f <- file.path(ctx$paths$model, "framing_cache.rds")
  key <- sha256_text(paste(c(fit$key, sha256_text(paste(format(rvt$rv_strike_vs_ball, digits = 17), collapse = ";")),
                             sha256_text(paste(cgm$cg$key, collapse = ";")),
                             sha256_text(paste(cgm$row_cg, collapse = ";")),
                             sha256_text(paste(which(rows$challenged), collapse = ";")),
                             sha256_text(paste(c(deparse(propagate), deparse(add_rows), deparse(add_vec)), collapse = "\n")),
                             CHUNK), collapse = "|"))
  if (!force && file.exists(f)) {
    o <- readRDS(f)
    if (identical(o$key, key)) {
      record("expected strikes: cache hit", sprintf("key %s", substr(key, 1, 16)))
      return(o$sums)
    }
    record("expected strikes: cache stale", "recomputing")
    rm(o)
  }
  sums <- propagate(fit$m, ff, rows, cgm$row_cg, nrow(cgm$cg), rv, rv_season, fit$draws)
  saveRDS(list(key = key, sums = sums), f, compress = FALSE)
  sums
}

## --- robustness arms: point estimates on the band and on P1 -----------------------------------------

arm_predict <- function(file, rows_arm, label) {
  if (!file.exists(file)) {
    record(sprintf("arm %s", label), sprintf("not run: %s is absent", file))
    return(NULL)
  }
  o <- readRDS(file)
  m <- o$m
  rm(o)
  nd <- m$model
  ok <- nrow(nd) == nrow(rows_arm)
  if (ok) {
    ok <- max(abs(nd$x_mid - rows_arm$x_mid)) < 1e-12 && max(abs(nd$zn - rows_arm$zn)) < 1e-9 &&
      all(as.integer(nd$cs) == rows_arm$cs)
  }
  check(sprintf("arm %s: the fit's rows are this arm's rows, in order", label), ok,
        sprintf("%s fit rows, %s arm rows", comma(nrow(nd)), comma(nrow(rows_arm))))
  if (!ok) return(NULL)
  eta <- numeric(nrow(nd))
  for (s in seq(1L, nrow(nd), by = CHUNK)) {
    i <- s:min(nrow(nd), s + CHUNK - 1L)
    eta[i] <- as.vector(mgcv::predict.gam(m, nd[i, , drop = FALSE], type = "link"))
  }
  rm(m, nd)
  invisible(gc())
  stats::plogis(eta)
}

arm_cg <- function(idx, p, rows, row_cg, ncg, rv) {
  g <- row_cg[idx]
  e <- rows$cs[idx] - p
  q <- p * (1 - p)
  list(R = add_vec(numeric(ncg), g, e * rv[idx]), V = add_vec(numeric(ncg), g, q * rv[idx]^2),
       n = tabulate(g, ncg), n_rows = length(idx))
}

framing_arms <- function(ctx, opt, rows, cal, cgm, rv, sums, fit_key, force) {
  ncg <- nrow(cgm$cg)
  ib <- which(abs(rows$d) <= BAND_SURF)
  ip1 <- which(!is.na(rows$H_abs))
  p1 <- apply_heights(rows[ip1, , drop = FALSE], "abs_cohort", cal, ctx)
  keep <- abs(p1$d) <= BAND_SURF
  ia <- ip1[keep]
  f_main <- file.path(ctx$paths$model, "surface_main.rds")
  f_abs <- file.path(ctx$paths$model, "surface_abs_cohort.rds")
  shas <- vapply(c(f_main, f_abs), function(f) if (file.exists(f)) sha256_file(f) else "absent", "")
  key <- sha256_text(paste(c(fit_key, shas, sha256_text(paste(ib, collapse = ";")), sha256_text(paste(ia, collapse = ";")),
                             sha256_text(paste(c(deparse(arm_predict), deparse(arm_cg)), collapse = "\n"))),
                           collapse = "|"))
  f <- file.path(ctx$paths$model, "framing_arms_cache.rds")
  if (!force && file.exists(f)) {
    o <- readRDS(f)
    if (identical(o$key, key)) {
      record("robustness arms: cache hit", sprintf("key %s", substr(key, 1, 16)))
      return(o$arms)
    }
  }
  arms <- list()
  arms$band_framing_surface <- c(arm_cg(ib, sums$p0[ib], rows, cgm$row_cg, ncg, rv),
                                 list(label = "framing surface, |d| <= 8 in band rows only", compare = "primary"))
  pm <- arm_predict(f_main, surface_rows(rows), "band_surface_main")
  if (!is.null(pm)) {
    arms$band_surface_main <- c(arm_cg(ib, pm, rows, cgm$row_cg, ncg, rv),
                                list(label = "W3.14 main surface (band fit), band rows", compare = "band_framing_surface"))
  }
  rm(pm)
  arms$p1_framing_surface <- c(arm_cg(ia, sums$p0[ia], rows, cgm$row_cg, ncg, rv),
                               list(label = "framing surface, P1 band rows (primary heights)", compare = "primary"))
  pa <- arm_predict(f_abs, p1[keep, , drop = FALSE], "p1_surface_abs_cohort")
  if (!is.null(pa)) {
    arms$p1_surface_abs_cohort <- c(arm_cg(ia, pa, rows, cgm$row_cg, ncg, rv),
                                    list(label = "W3.14 ABS-measured surface (H_abs heights), P1 band rows",
                                         compare = "p1_framing_surface"))
  }
  saveRDS(list(key = key, arms = arms), f)
  arms
}

## --- statistics per season, per replicate ------------------------------------------------------------

to_cs <- function(A, x) if (is.null(dim(x))) as.vector(A %*% x) else as.matrix(A %*% x)

variant_cg <- function(sums, cg, v, cv) {
  runs <- if (v == "cnt") sums$R else FLAT_RUNS * sums$S
  noise <- if (v == "cnt") sums$V0 else FLAT_RUNS^2 * sums$U0
  n <- cg$n
  if (cv == "sis" && length(sums$chcg) > 0L) {
    sub <- if (v == "cnt") sums$Rch else FLAT_RUNS * sums$Sch
    runs[sums$chcg, ] <- runs[sums$chcg, , drop = FALSE] - sub
    noise <- noise - (if (v == "cnt") sums$V0ch else FLAT_RUNS^2 * sums$U0ch)
    n <- n - cg$n_ch
  }
  list(runs = runs, noise = noise, n = n)
}

# One statistic set on the catcher-season rows idx (repeats allowed: a resampled catcher enters as
# often as he was drawn), column j of the runs matrices.
stat_one <- function(idx, j, V) {
  rate <- V$runs[idx, j] / V$inn[idx] * PER_INN
  nv <- V$noise[idx] / (V$inn[idx] / PER_INN)^2
  sd_raw <- stats::sd(rate)
  top <- sort(rate, decreasing = TRUE)
  out <- c(sd_raw_per100 = sd_raw, sd_signal_per100 = sqrt(max(0, sd_raw^2 - mean(nv))),
           top30_mean_per100 = mean(top[seq_len(min(TOP_N, length(top)))]), mean_per100 = mean(rate),
           split_half_r = NA_real_, reliability_sb = NA_real_)
  if (!is.null(V$ro)) {
    a <- V$ro[idx, j] / V$no[idx] * PER_PITCHES
    b <- V$re[idx, j] / V$ne[idx] * PER_PITCHES
    ok <- is.finite(a) & is.finite(b)
    if (sum(ok) >= 3L) {
      r <- stats::cor(a[ok], b[ok])
      out[["split_half_r"]] <- r
      out[["reliability_sb"]] <- 2 * r / (1 + r)
    }
  }
  out
}

# Every season's statistics at the point (column 1: beta, every qualified catcher once) and in each
# replicate b (draw b, catchers resampled by the multiplicities M[, b]).
season_series <- function(V, cs, groups, M) {
  nrep <- ncol(V$runs) - 1L
  out <- list()
  for (gname in names(groups)) {
    q <- groups[[gname]]
    mm <- M[as.character(cs$catcher[q]), , drop = FALSE]
    res <- matrix(NA_real_, nrep + 1L, length(METRICS), dimnames = list(NULL, METRICS))
    res[1, ] <- stat_one(q, 1L, V)
    for (b in seq_len(nrep)) res[b + 1L, ] <- stat_one(rep(q, mm[, b]), b + 1L, V)
    out[[gname]] <- res
  }
  out
}

catcher_multiplicities <- function(ids, B) {
  set.seed(DRAW_SEED)
  M <- stats::rmultinom(B, length(ids), rep(1, length(ids)))
  rownames(M) <- as.character(ids)
  M
}

## --- CH1-A11 ----------------------------------------------------------------------------------------

fisher_ci <- function(r, n) {
  if (!is.finite(r) || n < 4L) return(c(NA_real_, NA_real_))
  z <- atanh(r)
  se <- 1 / sqrt(n - 3)
  tanh(z + c(-1, 1) * stats::qnorm(0.975) * se)
}

a11_validity <- function(sav, csout) {
  if (is.null(sav)) {
    return(list(pairs = NULL, table = data.frame(scope = "pooled_2022_2024", value_type = "cnt", n = NA_integer_,
                                                 pearson_r = NA_real_, lo95 = NA_real_, hi95 = NA_real_,
                                                 spearman_rho = NA_real_, threshold = A11_R, gates = TRUE,
                                                 pass = NA, verdict = "not run: synthetic table, no Savant file",
                                                 stringsAsFactors = FALSE)))
  }
  our <- csout[csout$season %in% A11_SEASONS, c("season", "catcher", "runs_cnt", "runs_flat", "runs_cnt_uncentred",
                                                "called_pitches", "innings", "qualified")]
  pr <- merge(sav, our, by.x = c("season", "id"), by.y = c("season", "catcher"), all.x = TRUE, sort = TRUE)
  names(pr)[names(pr) == "id"] <- "catcher"
  found <- is.finite(pr$runs_cnt)
  check("CH1-A11: every Savant catcher-season is in P0", all(found),
        sprintf("%d of %d matched by MLBAM id", sum(found), nrow(pr)))
  rows <- list()
  for (sc in c("pooled_2022_2024", as.character(A11_SEASONS))) {
    sel <- found & (sc == "pooled_2022_2024" | pr$season == suppressWarnings(as.integer(sc)))
    for (v in c(VALUE_TYPES, "cnt_uncentred")) {
      y <- pr[[paste0("runs_", v)]][sel]
      x <- pr$savant_rv_tot[sel]
      r <- stats::cor(x, y)
      ci <- fisher_ci(r, sum(sel))
      gates <- sc == "pooled_2022_2024" && v == "cnt"
      rows[[length(rows) + 1L]] <- data.frame(scope = sc, value_type = v, n = sum(sel), pearson_r = r, lo95 = ci[1],
                                              hi95 = ci[2], spearman_rho = stats::cor(x, y, method = "spearman"),
                                              threshold = A11_R, gates = gates, pass = r >= A11_R,
                                              verdict = "", stringsAsFactors = FALSE)
    }
  }
  tab <- do.call(rbind, rows)
  g <- tab[tab$gates, ]
  verdict <- if (isTRUE(g$pass)) "framing primary" else "framing demoted to secondary"
  tab$verdict <- ifelse(tab$gates, verdict, "reported, does not gate")
  list(pairs = pr, table = tab)
}

## --- assembling the tables ------------------------------------------------------------------------

regime_of_period <- function(p) {
  ifelse(p %in% names(REGIME_OF), unname(REGIME_OF[p]), ifelse(p %in% REGIMES, p, "abs_2026"))
}

# Long table rows for one variant's series: seasons, the three regimes, and any extra group.
series_rows <- function(ser, v, cv, nq) {
  pre <- (ser[["2022"]] + ser[["2023"]] + ser[["2024"]]) / 3
  all <- c(ser[SEASON_LEVELS], list(pre_buffer = pre, buffer_2025 = ser[["2025"]], abs_2026 = ser[["2026"]]),
           ser[setdiff(names(ser), SEASON_LEVELS)])
  out <- list()
  for (p in names(all)) {
    X <- all[[p]]
    for (mt in METRICS) {
      if (all(is.na(X[, mt]))) next
      i95 <- if (nrow(X) > 1L) qint(X[-1, mt], 0.95) else c(NA_real_, NA_real_)
      out[[length(out) + 1L]] <- data.frame(period = p, regime = regime_of_period(p), metric = mt, value_type = v,
                                            convention = cv, point = X[1, mt], lo95 = i95[1], hi95 = i95[2],
                                            units = METRIC_UNITS[[mt]], n_qualified = nq[[p]],
                                            n_reps = nrow(X) - 1L, stringsAsFactors = FALSE)
    }
  }
  do.call(rbind, out)
}

decomp_rows <- function(ser, v, cv) {
  out <- list()
  for (mt in DECOMP_METRICS) {
    pt <- vapply(SEASON_LEVELS, function(s) ser[[s]][1, mt], 0)
    dr <- sapply(SEASON_LEVELS, function(s) ser[[s]][-1, mt])
    d <- decompose_estimand(pt, dr, mt, METRIC_UNITS[[mt]])
    tab <- d$table
    tab$value_type <- v
    tab$convention <- cv
    out[[mt]] <- tab
  }
  do.call(rbind, out)
}

contrast_rows <- function(ser, dec, v, cv) {
  rel <- function(p) if (p == "pre_buffer") (ser[["2022"]][, "reliability_sb"] + ser[["2023"]][, "reliability_sb"] +
                                               ser[["2024"]][, "reliability_sb"]) / 3 else ser[[p]][, "reliability_sb"]
  cons <- list(c("2026_minus_2025", "2026", "2025"), c("2026_minus_pre_buffer", "2026", "pre_buffer"),
               c("2025_minus_pre_buffer", "2025", "pre_buffer"))
  out <- lapply(cons, function(k) {
    x <- rel(k[2]) - rel(k[3])
    i95 <- qint(x[-1], 0.95)
    data.frame(contrast = k[1], point = x[1], lo95 = i95[1], hi95 = i95[2], p_below_zero = mean(x[-1] < 0),
               source = "difference of split-half reliabilities, replicate by replicate", stringsAsFactors = FALSE)
  })
  dd <- dec[dec$estimand == "reliability_sb" & dec$component %in% c("delta_buffer", "delta_abs", "g"), ]
  out <- c(out, lapply(seq_len(nrow(dd)), function(i) {
    data.frame(contrast = dd$component[i], point = dd$point[i], lo95 = dd$lo95[i], hi95 = dd$hi95[i],
               p_below_zero = NA_real_, source = "decompose_estimand() of R/lib/ch1_decomp.R on the five seasons",
               stringsAsFactors = FALSE)
  }))
  tab <- do.call(rbind, out)
  tab$reading <- ifelse(tab$hi95 < 0, "fell", ifelse(tab$lo95 > 0, "rose", "no change distinguishable from zero"))
  tab$value_type <- v
  tab$convention <- cv
  tab
}

# The catcher-season sidecar: every catcher-season value the tables summarise, point estimates,
# with the surface-draw interval and the binomial noise SE of the primary rate.
catcher_rows <- function(csl, Vs, window) {
  cs <- csl$cs
  out <- data.frame(window = window, season = cs$season, regime = unname(REGIME_OF[as.character(cs$season)]),
                    catcher = cs$catcher, games = cs$games, innings = cs$innings, called_pitches = cs$called_pitches,
                    challenged_pitches = cs$challenged_pitches, qual_innings = cs$qual_innings,
                    qualified = cs$qualified, first_date = format(cs$first_date),
                    through_date = format(cs$through_date), stringsAsFactors = FALSE)
  for (nm in names(Vs)) {
    V <- Vs[[nm]]
    sfx <- sub("_original$", "", nm)
    out[[paste0("runs_", sfx)]] <- V$runs[, 1]
    out[[paste0("runs_", sfx, "_uncentred")]] <- V$runs_raw
    out[[paste0("runs_", sfx, "_per100")]] <- V$runs[, 1] / V$inn * PER_INN
    out[[paste0("se_noise_", sfx, "_per100")]] <- sqrt(V$noise) / (V$inn / PER_INN)
    if (!is.null(V$ro)) {
      out[[paste0("odd_", sfx, "_per1000")]] <- V$ro[, 1] / V$no * PER_PITCHES
      out[[paste0("even_", sfx, "_per1000")]] <- V$re[, 1] / V$ne * PER_PITCHES
    }
    if (ncol(V$runs) > 1L && nm == "cnt_original") {
      q <- apply(V$runs[, -1, drop = FALSE] / V$inn * PER_INN, 1, qint, lev = 0.95)
      out$runs_cnt_per100_draw_lo95 <- q[1, ]
      out$runs_cnt_per100_draw_hi95 <- q[2, ]
    }
  }
  out
}

arm_rows <- function(arms, CS, inn_cs, groups, prim_rate) {
  if (is.null(arms)) return(NULL)
  cs <- CS$cs
  rate_of <- list(primary = prim_rate)
  out <- list()
  for (nm in names(arms)) {
    a <- arms[[nm]]
    R <- to_cs(CS$A, a$R); n <- to_cs(CS$A, a$n)
    ro <- to_cs(CS$A_odd, a$R); no <- to_cs(CS$A_odd, a$n)
    re <- to_cs(CS$A_even, a$R); ne <- to_cs(CS$A_even, a$n)
    for (se in unique(cs$season)) {           # centred as variant_cs() centres, over the arm's own pitches
      i <- cs$season == se
      ms <- sum(R[i]) / sum(n[i])
      R[i] <- R[i] - n[i] * ms; ro[i] <- ro[i] - no[i] * ms; re[i] <- re[i] - ne[i] * ms
    }
    V <- list(runs = matrix(R), noise = to_cs(CS$A, a$V), inn = inn_cs, ro = matrix(ro), no = no, re = matrix(re), ne = ne)
    rate <- V$runs[, 1] / inn_cs * PER_INN
    rate_of[[nm]] <- rate
    cmp <- rate_of[[a$compare]]
    for (s in c(names(groups), "pooled")) {
      q <- if (s == "pooled") sort(unlist(groups, use.names = FALSE)) else groups[[s]]
      st <- if (s == "pooled") rep(NA_real_, length(METRICS)) else stat_one(q, 1L, V)
      names(st) <- METRICS
      out[[length(out) + 1L]] <- data.frame(arm = nm, label = a$label, compared_with = a$compare, period = s,
                                            n_pitches = a$n_rows, n_qualified = length(q),
                                            sd_raw_per100 = st[["sd_raw_per100"]],
                                            sd_signal_per100 = st[["sd_signal_per100"]],
                                            top30_mean_per100 = st[["top30_mean_per100"]],
                                            reliability_sb = st[["reliability_sb"]],
                                            cor_with_compared = stats::cor(rate[q], cmp[q]), stringsAsFactors = FALSE)
    }
  }
  out <- do.call(rbind, out)
  out$id <- paste(out$arm, out$period, sep = ":")
  out[, c("id", setdiff(names(out), "id"))]
}

doolittle_rows <- function(series) {
  out <- list()
  for (v in VALUE_TYPES) {
    ser <- series[[paste(v, "original")]]
    get <- function(p) ser[[p]][, "top30_mean_per100"]
    for (p in c("2025", "2026", "2026_through_05-18")) {
      x <- get(p)
      i95 <- qint(x[-1], 0.95)
      out[[length(out) + 1L]] <- data.frame(row = paste0("top30_", p), value_type = v, point = x[1], lo95 = i95[1],
                                            hi95 = i95[2], doolittle = switch(p, "2025" = DOOLITTLE[["y2025"]],
                                                                              "2026_through_05-18" = DOOLITTLE[["y2026"]],
                                                                              NA_real_),
                                            units = "runs per 100 innings", stringsAsFactors = FALSE)
    }
    for (p in c("2026_through_05-18", "2026")) {
      x <- (get(p) / get("2025") - 1) * 100
      i95 <- qint(x[-1], 0.95)
      out[[length(out) + 1L]] <- data.frame(row = paste0("change_pct_", p, "_vs_2025"), value_type = v, point = x[1],
                                            lo95 = i95[1], hi95 = i95[2],
                                            doolittle = if (p == "2026_through_05-18")
                                              (DOOLITTLE[["y2026"]] / DOOLITTLE[["y2025"]] - 1) * 100 else NA_real_,
                                            units = "percent", stringsAsFactors = FALSE)
    }
  }
  do.call(rbind, out)
}

## --- one variant per catcher-season -----------------------------------------------------------------

# A variant's catcher-season matrices: runs (column 1 at beta, then one column per draw), the noise
# variance at beta, innings, and the odd and even game halves with their pitch counts.
#
# Centring (reading i). Runs are relative to the league-average catcher of the season: in each season
# and in each replicate column, the league's runs per called pitch (over every catcher-season of the
# aggregation, qualified or not) times the catcher's called pitches is subtracted, from the season
# total and from each half alike. The league total is then zero in every season and every replicate.
# A per-season constant per pitch leaves the per-1,000-pitch split-half correlation unchanged, and
# moves a catcher's rate per 100 innings by a near-constant, so the SDs barely move; the level
# statistics (the mean and the top-30 mean) are what it changes. The uncentred point values are kept
# as runs_raw and published beside the centred ones.
variant_cs <- function(sums, cg, CS, v, cv) {
  W <- variant_cg(sums, cg, v, cv)
  runs <- to_cs(CS$A, W$runs); n <- to_cs(CS$A, W$n)
  ro <- to_cs(CS$A_odd, W$runs); no <- to_cs(CS$A_odd, W$n)
  re <- to_cs(CS$A_even, W$runs); ne <- to_cs(CS$A_even, W$n)
  runs_raw <- runs[, 1]
  season <- CS$cs$season
  league <- matrix(NA_real_, length(unique(season)), ncol(runs), dimnames = list(sort(unique(season)), NULL))
  for (se in sort(unique(season))) {
    i <- which(season == se)
    ms <- colSums(runs[i, , drop = FALSE]) / sum(n[i])
    league[as.character(se), ] <- ms
    runs[i, ] <- runs[i, , drop = FALSE] - outer(n[i], ms)
    ro[i, ] <- ro[i, , drop = FALSE] - outer(no[i], ms)
    re[i, ] <- re[i, , drop = FALSE] - outer(ne[i], ms)
  }
  list(runs = runs, noise = to_cs(CS$A, W$noise), inn = CS$cs$innings, n = n, ro = ro, no = no, re = re, ne = ne,
       runs_raw = runs_raw, league = league)
}

# The centring constants: the league's runs per called pitch and per 100 innings, at beta and over the
# replicate draws, per season and variant. This is the level the centring removes.
centring_rows <- function(V, CS, nm, window) {
  do.call(rbind, lapply(rownames(V$league), function(se) {
    i <- CS$cs$season == as.integer(se)
    per100 <- V$league[se, ] * sum(V$n[i]) / sum(V$inn[i]) * PER_INN
    q <- qint(per100[-1], 0.95)
    data.frame(window = window, season = as.integer(se), variant = nm, league_runs_per_pitch = V$league[se, 1],
               league_runs_per100 = per100[1], draws_sd_per100 = if (length(per100) > 1L) stats::sd(per100[-1]) else NA_real_,
               draws_lo95_per100 = q[1], draws_hi95_per100 = q[2], stringsAsFactors = FALSE)
  }))
}

season_groups <- function(cs) {
  g <- lapply(SEASON_LEVELS, function(s) which(cs$season == as.integer(s) & cs$qualified))
  stats::setNames(g, SEASON_LEVELS)
}

DW_PERIOD <- "2026_through_05-18"
VARIANTS <- expand.grid(v = VALUE_TYPES, cv = CONVENTIONS, stringsAsFactors = FALSE)
variant_name <- function(v, cv) paste(v, cv, sep = "_")
role_of <- function(v, cv) {
  ifelse(v == "cnt" & cv == "original", "primary",
         ifelse(v == "cnt", "robustness: SIS convention", ifelse(cv == "original", "robustness: flat 0.125",
                                                               "robustness: flat 0.125, SIS convention")))
}

# Share of replicates whose statistic is finite, per period and metric: a period needs 99%.
complete_share <- function(ser) {
  do.call(rbind, lapply(names(ser), function(p) {
    X <- ser[[p]][-1, , drop = FALSE]
    data.frame(period = p, metric = colnames(X), share = colMeans(is.finite(X)), stringsAsFactors = FALSE)
  }))
}

## --- the sample table ---------------------------------------------------------------------------------

sample_rows <- function(rows, CS, cgm, sums) {
  cs <- CS$cs
  cg <- cgm$cg
  per <- do.call(rbind, lapply(SEASONS, function(s) {
    i <- rows$season == s
    q <- cs$season == s
    e <- rows$cs[i] - sums$p0[i]
    data.frame(season = s, regime = unname(REGIME_OF[as.character(s)]), called_pitches = sum(i),
               games = length(unique(rows$game_pk[i])), first_date = format(min(rows$official_date[i])),
               last_date = format(max(rows$official_date[i])), challenged_pitches = sum(rows$challenged[i]),
               catcher_seasons = sum(q), qualified_catcher_seasons = sum(q & cs$qualified),
               qual_innings = cs$qual_innings[q][1], team_innings_mean = sum(cs$innings[q]) / N_TEAMS,
               innings_per_team_game = sum(cg$innings[cg$season == s]) / (2 * length(unique(cg$game_pk[cg$season == s]))),
               observed_strike_rate = mean(rows$cs[i]), expected_strike_rate = mean(sums$p0[i]),
               mean_obs_minus_exp = mean(e), stringsAsFactors = FALSE)
  }))
  tot <- data.frame(season = "all", regime = "all", called_pitches = nrow(rows), games = length(unique(rows$game_pk)),
                    first_date = format(min(rows$official_date)), last_date = format(max(rows$official_date)),
                    challenged_pitches = sum(rows$challenged), catcher_seasons = nrow(cs),
                    qualified_catcher_seasons = sum(cs$qualified), qual_innings = NA_real_,
                    team_innings_mean = NA_real_, innings_per_team_game = sum(cg$innings) / (2 * length(unique(cg$game_pk))),
                    observed_strike_rate = mean(rows$cs), expected_strike_rate = mean(sums$p0),
                    mean_obs_minus_exp = mean(rows$cs - sums$p0), stringsAsFactors = FALSE)
  per$season <- as.character(per$season)
  rbind(per, tot)
}

## --- the publication tables --------------------------------------------------------------------------

REGIME_PERIODS <- c("pre_buffer", "buffer_2025", "abs_2026", DW_PERIOD)

pub_by_regime <- function(br) {
  x <- br[br$period %in% REGIME_PERIODS, c("period", "regime", "metric", "value_type", "convention", "point", "lo95",
                                            "hi95", "units", "n_qualified", "n_reps")]
  x$role <- role_of(x$value_type, x$convention)
  x$id <- paste("framing", x$period, x$metric, x$value_type, x$convention, sep = ":")
  x[, c("id", setdiff(names(x), "id"))]
}

## --- the prose numbers ----------------------------------------------------------------------------------

# Every number the prose prints is registered first: the text as printed, its value, and the CSV row it
# comes from (source, the key column, the key, the column). tests/testthat/test-ch1-framing.R re-reads
# each source and re-derives the text. Constants of the SOP carry source "SOP W3.19".
.pn <- new.env()
.pn$rows <- list()
pn <- function(value, digits, source, key_col = "", key = "", column = "", suffix = "") {
  txt <- paste0(formatC(value, format = "f", digits = digits, big.mark = if (digits == 0L) "," else ""), suffix)
  .pn$rows[[length(.pn$rows) + 1L]] <- data.frame(text = txt, value = value, digits = digits, suffix = suffix,
                                                  source = source, key_col = key_col, key = key, column = column,
                                                  stringsAsFactors = FALSE)
  txt
}
# A value from a CSV the step wrote, looked up by one key column, printed and registered.
pv <- function(df, src, key_col, key, column, digits, suffix = "") {
  i <- which(df[[key_col]] == key)
  if (length(i) != 1L) die(sprintf("prose lookup: %d rows of %s where %s == %s", length(i), src, key_col, key))
  pn(df[[column]][i], digits, src, key_col, key, column, suffix)
}
ci95 <- function(df, src, key_col, key, digits, suffix = "") {
  sprintf("95%% CI %s to %s", pv(df, src, key_col, key, "lo95", digits, suffix),
          pv(df, src, key_col, key, "hi95", digits, suffix))
}

## --- the prose -------------------------------------------------------------------------------------------

# out/ch1/prose/framing.md. T: the tables as written, each list(df, path). Short sentences, no
# question mark, no cause named unless W3.21 licenses it; every number through pn()/pv().
write_prose <- function(ctx, T, reading, has_arms) {
  .pn$rows <- list()
  rel <- function(k) out_rel(ctx, T[[k]]$path)
  br <- T$by_regime$df; sbr <- rel("by_regime")
  dc <- T$decomp$df; sdc <- rel("decomp")
  rl <- T$reliability$df; srl <- rel("reliability")
  va <- T$validity$df; sva <- rel("validity")
  dl <- T$doolittle$df; sdl <- rel("doolittle")
  sm <- T$sample$df; ssm <- rel("sample")
  sn <- T$sanity$df; ssn <- rel("sanity")
  k_br <- function(p, m, v = "cnt", cv = "original") paste("framing", p, m, v, cv, sep = ":")
  X <- function(p, m, d, v = "cnt", cv = "original") pv(br, sbr, "id", k_br(p, m, v, cv), "point", d)
  XC <- function(p, m, d, v = "cnt", cv = "original") ci95(br, sbr, "id", k_br(p, m, v, cv), d)
  XN <- function(p, m = "sd_signal_per100", v = "cnt", cv = "original") pv(br, sbr, "id", k_br(p, m, v, cv), "n_qualified", 0)
  k_dc <- function(m, comp) paste("framing_decomp", m, comp, "cnt", "original", sep = ":")
  D <- function(m, comp, d) pv(dc, sdc, "id", k_dc(m, comp), "point", d)
  DC <- function(m, comp, d) ci95(dc, sdc, "id", k_dc(m, comp), d)
  k_rl <- function(con) paste("framing_rel", con, "cnt", "original", sep = ":")
  C100 <- pn(PER_INN, 0, "SOP W3.19")
  a11 <- va[va$scope == "pooled_2022_2024" & va$value_type == "cnt", ]
  a11_key <- "framing_a11:pooled_2022_2024:cnt"
  demoted <- !isTRUE(a11$pass)
  L <- c("# Catcher framing by regime", "",
         paste0("SOP W3.19. ", if (demoted) "**Secondary result.**" else "**Primary result.**",
                " Every number here is a row of `out/ch1/tab/framing_*.csv` or `out/tables/ch1_framing_*.csv`,",
                " listed with its source in `out/ch1/tab/framing_prose_numbers.csv`."), "")
  if (is.finite(a11$pearson_r)) {
    L <- c(L, paste0("**External validity, CH1-A11.** Across ", pv(va, sva, "id", a11_key, "n", 0),
                     " Savant-qualified catcher-seasons of 2022 to 2024, this step's count-specific framing runs",
                     " correlate with Savant's `rv_tot` at r = ", pv(va, sva, "id", a11_key, "pearson_r", 3), " (",
                     ci95(va, sva, "id", a11_key, 3), "). The pre-registered threshold is ",
                     pn(A11_R, 2, "SOP W3.19"), ". ",
                     if (demoted) paste("The correlation falls below it, so the framing result is demoted to secondary,",
                                        "as SOP W3.19 pre-registers. The estimator was not tuned toward the threshold.")
                     else "The correlation clears it, so framing is reported as a primary result."), "")
  } else {
    L <- c(L, paste("**External validity, CH1-A11.** Not measured in this run: no Savant file was read,",
                    "so the framing result stands as secondary."), "")
  }
  z <- sn[sn$check == "tango_00_ball", ]; zs <- sn[sn$check == "tango_00_strike", ]
  L <- c(L, paste0("**Method.** Each pitch's expected strike probability comes from a catcher-free surface.",
                   " It is the frozen formula of the chapter's primary surface, fitted by `bam` to P0 with no catcher term.",
                   " P0 holds ", pv(sm, ssm, "season", "all", "called_pitches", 0),
                   " called pitches of 2022 through ", format(ctx$last_open), ".",
                   " Observed minus expected strikes are summed per catcher-season.",
                   " Runs are centred on the league-average catcher of each season, per called pitch, in every replicate.",
                   " Uncentred, that catcher earns ", pv(T$centring$df, rel("centring"), "id", "season:2026:cnt_original",
                                                         "league_runs_per100", 3),
                   " runs per ", C100, " innings in 2026.",
                   " The surface's count term is the strike count, and umpires call more strikes than it expects in",
                   " counts with more balls.",
                   " Each pitch is priced by the count-specific run value of a strike against a ball, from",
                   " `delta_run_exp` over 2022 to 2024.",
                   " In the first-pitch count that table gives a ball ", pv(sn, ssn, "check", "tango_00_ball", "value", 3),
                   " runs and a strike ", pv(sn, ssn, "check", "tango_00_strike", "value", 3), ".",
                   " Tango's figures, ", pn(TANGO_00[["ball"]], 3, "SOP W3.19"), " and ",
                   pn(TANGO_00[["strike"]], 3, "SOP W3.19"), ", are the sanity check, within ",
                   pn(TANGO_TOL, 3, "R/ch1/30_framing.R TANGO_TOL"), " runs.",
                   " A flat ", pn(FLAT_RUNS, 3, "SOP W3.19"), " runs per strike is the Savant-comparable robustness column.",
                   " Each interval is a 95% interval from ", pn(ctx$n_draws, 0, "R/lib/ch1_fits.R N_DRAWS"),
                   " replicates that pair a surface draw with a catcher bootstrap.",
                   " A catcher-season qualifies with a quarter of its season's mean team innings."), "")
  L <- c(L, paste0("**Spread across catchers.** Net of binomial noise, the SD of framing runs per ", C100,
                   " innings across qualified catchers is ", X("pre_buffer", "sd_signal_per100", 3), " (",
                   XC("pre_buffer", "sd_signal_per100", 3), ") in 2022 to 2024.",
                   " It is ", X("buffer_2025", "sd_signal_per100", 3), " (", XC("buffer_2025", "sd_signal_per100", 3),
                   ") in 2025 and ", X("abs_2026", "sd_signal_per100", 3), " (", XC("abs_2026", "sd_signal_per100", 3),
                   ") in 2026.",
                   " The raw SDs, noise included, are ", X("pre_buffer", "sd_raw_per100", 3), ", ",
                   X("buffer_2025", "sd_raw_per100", 3), " and ", X("abs_2026", "sd_raw_per100", 3), ".",
                   " They cover ", XN("pre_buffer"), ", ", XN("buffer_2025"), " and ", XN("abs_2026"),
                   " qualified catcher-seasons."), "")
  k25 <- "framing_doolittle:top30_2025:cnt"; kdw <- paste0("framing_doolittle:top30_", DW_PERIOD, ":cnt")
  k26 <- "framing_doolittle:top30_2026:cnt"; kch <- paste0("framing_doolittle:change_pct_", DW_PERIOD, "_vs_2025:cnt")
  L <- c(L, paste0("**Doolittle's comparable.** The top-30 mean is ", pv(dl, sdl, "id", k25, "point", 3), " runs per ",
                   C100, " innings (", ci95(dl, sdl, "id", k25, 3), ") in 2025.",
                   " Through 2026-05-18 it is ", pv(dl, sdl, "id", kdw, "point", 3), " (", ci95(dl, sdl, "id", kdw, 3),
                   "), a change of ", pv(dl, sdl, "id", kch, "point", 1, "%"), " (", ci95(dl, sdl, "id", kch, 1, "%"), ").",
                   " Doolittle reported ", pv(dl, sdl, "id", k25, "doolittle", 3), " and ",
                   pv(dl, sdl, "id", kdw, "doolittle", 3), " for the same windows, a change of ",
                   pv(dl, sdl, "id", kch, "doolittle", 1, "%"), ".",
                   " Over the whole open 2026 season the top-30 mean is ", pv(dl, sdl, "id", k26, "point", 3), " (",
                   ci95(dl, sdl, "id", k26, 3), ")."), "")
  r_dd <- rl[rl$id == k_rl("2026_minus_2025"), ]
  r_da <- rl[rl$id == k_rl("delta_abs"), ]
  rd <- if (r_dd$reading == "fell" && r_da$reading == "fell") {
    "Both intervals lie below zero, so the reliability of framing fell in 2026."
  } else if (r_dd$reading == r_da$reading) {
    sprintf("Both readings agree: %s.", r_dd$reading)
  } else {
    sprintf("The two readings differ: the plain difference reads %s, the trend-adjusted component %s.",
            r_dd$reading, r_da$reading)
  }
  L <- c(L, paste0("**Reliability.** Split-half reliability compares odd and even games within a catcher-season,",
                   " Spearman-Brown corrected.",
                   " It is ", X("pre_buffer", "reliability_sb", 2), " (", XC("pre_buffer", "reliability_sb", 2),
                   ") in 2022 to 2024, ", X("buffer_2025", "reliability_sb", 2), " (", XC("buffer_2025", "reliability_sb", 2),
                   ") in 2025 and ", X("abs_2026", "reliability_sb", 2), " (", XC("abs_2026", "reliability_sb", 2), ") in 2026.",
                   " The step then asks whether the reliability of framing itself fell under ABS.",
                   " The 2026 minus 2025 difference is ", pv(rl, srl, "id", k_rl("2026_minus_2025"), "point", 2), " (",
                   ci95(rl, srl, "id", k_rl("2026_minus_2025"), 2), ").",
                   " The trend-adjusted `Delta_ABS` component is ", pv(rl, srl, "id", k_rl("delta_abs"), "point", 2), " (",
                   ci95(rl, srl, "id", k_rl("delta_abs"), 2), "). ", rd), "")
  desc <- !identical(reading, "as pre-registered")
  L <- c(L, paste0("**Decomposition.** On the signal SD, `Delta_buffer` is ", D("sd_signal_per100", "delta_buffer", 3), " (",
                   DC("sd_signal_per100", "delta_buffer", 3), ") runs per ", C100, " innings.",
                   " `Delta_ABS` is ", D("sd_signal_per100", "delta_abs", 3), " (", DC("sd_signal_per100", "delta_abs", 3), ").",
                   " On the top-30 mean the two are ", D("top30_mean_per100", "delta_buffer", 3), " (",
                   DC("top30_mean_per100", "delta_buffer", 3), ") and ", D("top30_mean_per100", "delta_abs", 3), " (",
                   DC("top30_mean_per100", "delta_abs", 3), ").",
                   if (startsWith(reading, "descriptive (no T5")) paste(" No placebo verdict is in this output tree, so",
                                                                      "the components are read descriptively and name no cause.")
                   else if (desc) paste(" W3.21's placebo P1 failed (CH1-A3), so these components are descriptive departures",
                                        "from the 2022 to 2024 trend and name no cause.")
                   else " W3.21's placebos pass, so the components are read as PREREGISTRATION.md section 8 sets out."), "")
  L <- c(L, paste0("**The two 2026 conventions.** The primary keeps every pitch at its original call, the call the catcher",
                   " influenced.",
                   " Excluding challenged pitches, the SIS convention, the 2026 signal SD is ",
                   X("abs_2026", "sd_signal_per100", 3, "cnt", "sis"), " (", XC("abs_2026", "sd_signal_per100", 3, "cnt", "sis"),
                   ") and the 2026 reliability ", X("abs_2026", "reliability_sb", 2, "cnt", "sis"), " (",
                   XC("abs_2026", "reliability_sb", 2, "cnt", "sis"), ").",
                   " At the flat value the 2026 signal SD is ", X("abs_2026", "sd_signal_per100", 3, "flat", "original"), " (",
                   XC("abs_2026", "sd_signal_per100", 3, "flat", "original"), ")."), "")
  if (has_arms) {
    ar <- T$arms$df; sar <- rel("arms")
    L <- c(L, paste0("**Surface checks.** On band rows, catcher-season rates from the framing surface and from W3.14's",
                     " band surface correlate at r = ", pv(ar, sar, "id", "band_surface_main:pooled", "cor_with_compared", 3),
                     " over ", pv(ar, sar, "id", "band_surface_main:pooled", "n_qualified", 0), " qualified catcher-seasons.",
                     " On P1's band rows the framing surface and W3.14's ABS-measured surface correlate at r = ",
                     pv(ar, sar, "id", "p1_surface_abs_cohort:pooled", "cor_with_compared", 3), "."), "")
  }
  f <- file.path(ctx$paths$prose, "framing.md")
  ensure_dir(dirname(f))
  while (length(L) > 0L && L[length(L)] == "") L <- L[-length(L)]   # one final newline, as the repo's hooks keep it
  writeLines(L, f)
  pnum <- do.call(rbind, .pn$rows)
  pnum <- pnum[!duplicated(paste(pnum$text, pnum$source, pnum$key, pnum$column)), , drop = FALSE]
  list(path = f, numbers = pnum, demoted = demoted)
}

## --- main ------------------------------------------------------------------------------------------------

# W3.21's reading of the decomposition: "as pre-registered" or "descriptive". A tree without T5 reads
# descriptive, the cautious side.
t5_reading <- function(ctx) {
  f <- file.path(ctx$paths$tab, "T5_placebos.csv")
  if (!file.exists(f)) return("descriptive (no T5_placebos.csv in this output tree)")
  r <- unique(read_csv_plain(f)$decomposition_reading)
  if (length(r) != 1L) die("T5_placebos.csv carries more than one decomposition_reading")
  r
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE), flags = c("force", "no-arms"))
  force <- isTRUE(opt[["force"]])
  ctx <- framing_start(opt)
  p <- ctx$paths
  reading <- t5_reading(ctx)
  record("decomposition reading (W3.21, T5)", reading)
  P0 <- load_p0(ctx, opt)
  rows <- P0$rows
  st <- table(rows$season)
  record("P0", sprintf("%s called pitches, %s games; %s", comma(nrow(rows)), comma(length(unique(rows$game_pk))),
                       paste(sprintf("%s %s", names(st), comma(st)), collapse = ", ")))

  # Run values: the pooled count table prices every pitch; the season tables are a point-only column.
  rvt <- run_value_tables(rows)
  tango <- tango_check(rvt)
  rv <- rv_lookup(rvt, "pooled_2022_2024", rows$balls, rows$strikes)
  rv_season <- numeric(nrow(rows))
  for (s in SEASONS) {
    i <- rows$season == s
    rv_season[i] <- rv_lookup(rvt, paste0("season_", s), rows$balls[i], rows$strikes[i])
  }
  check("run values: every P0 pitch is priced", all(is.finite(rv)) && all(is.finite(rv_season)), "")

  inn <- innings_caught(ctx, rows)
  cgm <- build_cg(rows, inn)
  cg <- cgm$cg
  check("catcher-games: every P0 pitch maps to one", !anyNA(cgm$row_cg) && sum(cg$n) == nrow(rows),
        sprintf("%s catcher-games", comma(nrow(cg))))

  # The catcher-free surface and the draws.
  spec <- make_spec("main")
  ff <- fit_frame(rows, spec)
  fit <- framing_fit(ctx, rows, ff, force)
  lab <- c(names(stats::coef(fit$m)), vapply(fit$m$smooth, function(s) s$label, ""))
  check("framing surface: no catcher term among the fitted terms", !any(grepl("catcher|fielder", lab, ignore.case = TRUE)),
        sprintf("%d coefficients; smooths %s", length(stats::coef(fit$m)),
                paste(vapply(fit$m$smooth, function(s) s$label, ""), collapse = ", ")))
  sums <- framing_sums(ctx, fit, ff, rows, cgm, rv, rv_season, rvt, force)
  fit_key <- fit$key
  fit_meta <- list(cached = fit$cached, seconds = fit$seconds, cache_parts = fit$parts)
  rm(ff, fit)
  invisible(gc())
  e_s <- tapply(rows$cs - sums$p0, rows$season, mean)
  check("observed minus expected averages to about zero in each season at beta", all(abs(e_s) < 2e-3),
        paste(sprintf("%s %+.5f", names(e_s), e_s), collapse = "; "))

  # Catcher-seasons: the full season, and 2026 through Doolittle's date.
  CS <- build_cs(cg)
  CSdw <- build_cs(cg, keep = cg$dw)
  groups <- season_groups(CS$cs)
  gdw <- stats::setNames(list(which(CSdw$cs$qualified)), DW_PERIOD)
  ng <- lengths(c(groups, gdw))
  check("qualified catchers: at least 30 in every season and in Doolittle's window", all(ng >= TOP_N),
        paste(sprintf("%s %d", names(ng), ng), collapse = "; "))
  ids <- sort(unique(c(CS$cs$catcher[unlist(groups)], CSdw$cs$catcher[gdw[[1]]])))
  M <- catcher_multiplicities(ids, ctx$n_draws)
  record("catcher bootstrap", sprintf("%d qualified catchers, %d replicates, seed %d", length(ids), ncol(M), DRAW_SEED))
  nq <- c(as.list(lengths(groups)), list(pre_buffer = sum(lengths(groups[PRE_SEASONS])),
                                         buffer_2025 = length(groups[["2025"]]), abs_2026 = length(groups[["2026"]])),
          stats::setNames(list(length(gdw[[1]])), DW_PERIOD))

  series <- list(); Vs <- list(); Vdws <- list(); br <- list(); dec <- list(); con <- list(); csh <- list(); ctr <- list()
  for (k in seq_len(nrow(VARIANTS))) {
    v <- VARIANTS$v[k]; cv <- VARIANTS$cv[k]; nm <- variant_name(v, cv)
    V <- variant_cs(sums, cg, CS, v, cv)
    Vdw <- variant_cs(sums, cg, CSdw, v, cv)
    ser <- c(season_series(V, CS$cs, groups, M), season_series(Vdw, CSdw$cs, gdw, M))
    series[[paste(v, cv)]] <- ser
    Vs[[nm]] <- V
    Vdws[[nm]] <- Vdw
    br[[nm]] <- series_rows(ser, v, cv, nq)
    dec[[nm]] <- decomp_rows(ser, v, cv)
    con[[nm]] <- contrast_rows(ser, dec[[nm]], v, cv)
    csh[[nm]] <- cbind(variant = nm, complete_share(ser), stringsAsFactors = FALSE)
    ctr[[nm]] <- rbind(centring_rows(V, CS, nm, "season"), centring_rows(Vdw, CSdw, nm, DW_PERIOD))
    record(sprintf("variant %s", nm), sprintf("%s; 2026 signal SD %.3f, reliability %.3f", role_of(v, cv),
                                              ser[["2026"]][1, "sd_signal_per100"], ser[["2026"]][1, "reliability_sb"]))
  }
  byreg <- do.call(rbind, br)
  byreg$id <- paste("framing", byreg$period, byreg$metric, byreg$value_type, byreg$convention, sep = ":")
  byreg$role <- role_of(byreg$value_type, byreg$convention)
  decomp <- do.call(rbind, dec)
  decomp$id <- paste("framing_decomp", decomp$estimand, decomp$component, decomp$value_type, decomp$convention, sep = ":")
  decomp$role <- role_of(decomp$value_type, decomp$convention)
  decomp$decomposition_reading <- reading
  relc <- do.call(rbind, con)
  relc$id <- paste("framing_rel", relc$contrast, relc$value_type, relc$convention, sep = ":")
  relc$role <- role_of(relc$value_type, relc$convention)
  csh <- do.call(rbind, csh)
  ctr <- do.call(rbind, ctr)
  ctr$id <- paste(ctr$window, ctr$season, ctr$variant, sep = ":")
  ctr <- ctr[, c("id", setdiff(names(ctr), "id"))]
  z <- ctr[ctr$window == "season" & ctr$variant == "cnt_original", ]
  record("centring: league runs per 100 innings removed", paste(sprintf("%d %+.3f (draws SD %.3f)", z$season,
                                                                         z$league_runs_per100, z$draws_sd_per100), collapse = "; "))
  dool <- doolittle_rows(series)
  dool$id <- paste("framing_doolittle", dool$row, dool$value_type, sep = ":")
  for (d in list(byreg, decomp, relc, dool)) if (anyDuplicated(d$id)) die("a table id repeats")
  resid <- max(decomp$identity_residual)
  check("decomposition identity: Delta_buffer + Delta_ABS + 2g == Delta_total", resid < IDENTITY_TOL,
        sprintf("max residual %.2e, %d estimands x %d variants", resid, length(DECOMP_METRICS), nrow(VARIANTS)))
  lo <- csh[which.min(csh$share), ]
  check("replicates: every statistic complete in at least 99% of replicates", all(csh$share >= MIN_COMPLETE_SHARE),
        sprintf("lowest %.4f (%s, %s, %s)", lo$share, lo$variant, lo$period, lo$metric))

  # The season-specific run-value table, a point-only column (original convention).
  cr_s <- catcher_rows(CS, Vs, "season")
  cr_s$runs_cnt_season_table <- to_cs(CS$A, sums$Rs0)
  cr_d <- catcher_rows(CSdw, Vdws, DW_PERIOD)
  cr_d$runs_cnt_season_table <- to_cs(CSdw$A, sums$Rs0)
  cat_rows <- rbind(cr_s, cr_d)
  a11 <- a11_validity(savant_table(ctx), cat_rows[cat_rows$window == "season", ])
  va <- a11$table
  va$id <- paste("framing_a11", va$scope, va$value_type, sep = ":")
  g <- va[va$gates, ]
  record("CH1-A11", sprintf("r %.4f (95%% CI %.4f to %.4f, n %s) against %.2f: %s", g$pearson_r, g$lo95, g$hi95,
                            format(g$n), A11_R, g$verdict))
  arms <- if (isTRUE(opt[["no-arms"]])) NULL else framing_arms(ctx, opt, rows, P0$cal, cgm, rv, sums, fit_key, force)
  armt <- arm_rows(arms, CS, CS$cs$innings, groups, Vs$cnt_original$runs[, 1] / CS$cs$innings * PER_INN)
  smp <- sample_rows(rows, CS, cgm, sums)

  tabf <- function(n) file.path(p$tab, paste0("framing_", n, ".csv"))
  pubf <- function(n) file.path(p$tables, paste0("ch1_framing_", n, ".csv"))
  T <- list(sample = list(df = smp, path = tabf("sample")), sanity = list(df = tango, path = tabf("sanity")),
            run_values = list(df = rvt, path = tabf("run_values")),
            catcher_seasons = list(df = cat_rows, path = tabf("catcher_seasons")),
            by_season = list(df = byreg, path = tabf("by_season")),
            decomp_all = list(df = decomp, path = tabf("decomposition")),
            reliability_all = list(df = relc, path = tabf("reliability_change")),
            doolittle_all = list(df = dool, path = tabf("doolittle")),
            validity_all = list(df = va, path = tabf("validity")),
            completeness = list(df = csh, path = tabf("replicate_completeness")),
            centring = list(df = ctr, path = tabf("centring")),
            by_regime = list(df = pub_by_regime(byreg), path = pubf("by_regime")),
            decomp = list(df = decomp, path = pubf("decomposition")),
            reliability = list(df = relc, path = pubf("reliability")),
            doolittle = list(df = dool, path = pubf("doolittle")),
            validity = list(df = va, path = pubf("validity")))
  if (!is.null(a11$pairs)) T$pairs <- list(df = a11$pairs, path = tabf("validity_pairs"))
  if (!is.null(armt)) T$arms <- list(df = armt, path = tabf("arms"))
  for (t in T) write_csv_plain(t$df, t$path)
  has_arms <- !is.null(armt) && all(c("band_surface_main:pooled", "p1_surface_abs_cohort:pooled") %in% armt$id)
  pr <- write_prose(ctx, T, reading, has_arms)
  write_csv_plain(pr$numbers, tabf("prose_numbers"))
  record("prose", sprintf("%s, %d registered numbers", out_rel(ctx, pr$path), nrow(pr$numbers)))
  if (pr$demoted && is.finite(g$pearson_r)) {
    cat(paste("CONSEQUENCE  CH1-A11 is below 0.85. Pre-registered (SOP W3.19): the framing result is demoted to",
              "secondary in the prose. Record it in docs/DEVIATIONS.md with a Madrid stamp; never tune the estimator.\n"))
  } else if (pr$demoted) {
    cat("CONSEQUENCE  CH1-A11 was not measured in this run, so the prose states the framing result as secondary.\n")
  }
  outs <- c(vapply(T, function(t) t$path, ""), tabf("prose_numbers"), pr$path)
  step_receipt(ctx, rows = rows, inputs = c(ctx$table, file.path(p$tab, "T5_placebos.csv")), outputs = outs,
               seed = DRAW_SEED,
               extra = list(fit_cache_sha256 = fit_key, fit_cached = fit_meta$cached, fit_seconds = fit_meta$seconds,
                            fit_cache_parts = fit_meta$cache_parts, decomposition_reading = reading,
                            ch1_a11 = list(pearson_r = g$pearson_r, lo95 = g$lo95, hi95 = g$hi95, n = g$n,
                                           threshold = A11_R, verdict = g$verdict),
                            conventions = as.list(CONV_LABEL), value_types = as.list(VALUE_LABEL)))
  finish(STEP)
}

if (identical(environment(), globalenv()) && !interactive()) main()
