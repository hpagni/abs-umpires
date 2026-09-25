#!/usr/bin/env Rscript
# R/ch1/02_original_call.R - SOP step W3.6, original-call reconstruction.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/02_original_call.R            build data/interim/ch1/original_call.parquet
#   Rscript R/ch1/02_original_call.R --check    rebuild in memory, compare to the file, write nothing
#
# WHAT IT WRITES. One row per called pitch in the open view v_called_pitch_open,
# every season, so the W3.7 analysis table joins it one to one on pitch_uid. The
# three W2.16 columns are kept apart: call_final is the call Statcast and the
# feed publish, which is the call after any ABS review; call_original is the
# umpire's call; is_overturned says whether a review moved it. No model may read
# call_final as the umpire's call.
#
#   call_original = call_final        when is_overturned is false
#   call_original = NOT call_final    when is_overturned is true
#
# WHERE is_overturned COMES FROM (SOP W3.6, D-62). The Savant ABS drawer carries
# the review outcome and the umpire's original call per challenge, keyed on
# play_id. The Statcast CSV has no play_id. The sprint route is the drawer
# coordinate key of DT-28: (game_pk, round(plate_X, 2), round(plate_Z, 2)),
# joined to Statcast. A drawer play whose key names exactly one Statcast pitch in
# its game is bridged by that key. A play whose key names more than one is
# ambiguous under DT-28, and the fallback D-62 names takes it: the feed's
# playEvents[].playId, which the warehouse carries as play_id on every open 2026
# pitch. The fallback pick must be one of the key's candidates. A challenge the
# feed holds and the drawer does not is taken from the feed's own W2.16
# reconstruction. A pitch with no challenge keeps its call.
#
# THE KEY IS ON THE RAW PAIR. Statcast reports plate_x and plate_z at the middle
# of the plate from 2026, which is the plane the drawer publishes. The open view
# carries that pair as plate_x_mid and plate_z_mid, with plane_source 'mid' on
# every 2026 row. The script asserts both before it builds a key.
#
# THE GATE, CH1-A2 (hard). The 2026 original call is recovered for 100% of the
# drawer's challenges, by the DT-28 bridge or by the feed fallback, with 0
# ambiguous matches. The script also fails on any of these:
#   - the bridge pick and the feed pick differ on a play both can resolve;
#   - a resolved pitch differs from the drawer on plate_X, plate_Z, the count,
#     the pitcher or the catcher;
#   - a resolved pitch is not a called, challenged pitch in the open view;
#   - the drawer's original_isStrike_ump differs from the reconstructed call;
#   - the reconstruction differs from the warehouse's W2.16 call_original;
#   - a challenged pitch in the open view is left without a source.
# DT-28 as the SOP writes it (100% unique on the rounded key) is measured and
# printed. When it is not met, the feed fallback carries the ambiguous plays, as
# D-62 directs, and the line says so.
#
# THE SEAL. The drawer has no date parameter, so each file's rows dated on or
# after config/seal.yml's seal_start_date are dropped as the file is parsed,
# before any other column is read. The boundary is read from that file and is
# not written here. The warehouse is read through the open views only.
#
# Exit 0 when every check passes, 1 when any fails, 2 on a usage error.

options(warn = 1, digits = 12)
t_start <- Sys.time()

args_all <- commandArgs(trailingOnly = FALSE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1 || (length(args) == 1 && !identical(args, "--check"))) {
  cat("usage: Rscript R/ch1/02_original_call.R [--check]\n", file = stderr())
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

## --- the harness -------------------------------------------------------------

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
  cat(sprintf("W3.6 %s: %d PASS, %d FAIL, %.1f s\n",
              if (CHECK_ONLY) "check" else "build", n_pass, length(failures),
              as.numeric(difftime(Sys.time(), t_start, units = "secs"))))
  if (length(failures) > 0) {
    cat("FAILED CLAUSES:\n", paste0("  ", failures, "\n"), sep = "")
    quit(status = 1)
  }
  quit(status = 0)
}

## --- paths and the seal boundary --------------------------------------------

WAREHOUSE  <- file.path(ROOT, "warehouse", "abs.duckdb")
DRAWER_DIR <- file.path(ROOT, "data", "raw", "savant", "abs_drawer")
MANIFEST   <- file.path(ROOT, "data", "raw", "_manifest.csv")
OUT_DIR    <- file.path(ROOT, "data", "interim", "ch1")
OUT_FILE   <- file.path(OUT_DIR, "original_call.parquet")
# LICENCE and DRAWER_ENDPOINT are in R/lib/endpoints.R.
source(file.path(ROOT, "R", "lib", "endpoints.R"))

seal_yml <- readLines(file.path(ROOT, "config", "seal.yml"), warn = FALSE)
seal_start <- as.Date(gsub('[" ]', "", sub("^seal_start_date:", "",
  grep("^seal_start_date:", seal_yml, value = TRUE)[1])))
stopifnot(!is.na(seal_start))

## --- 1. the drawer, one row per play -----------------------------------------

DRAWER_FILES <- sort(list.files(DRAWER_DIR, pattern = "^mlb_2026_[0-9]+\\.json$",
                                full.names = TRUE))
check("drawer files", length(DRAWER_FILES) == 30,
      sprintf("%d MLB 2026 team drawers, one per club, 30 expected", length(DRAWER_FILES)))
if (length(DRAWER_FILES) == 0) finish()

n_dropped_at_seal <- 0L
drw_rows <- do.call(rbind, lapply(DRAWER_FILES, function(f) {
  d <- jsonlite::fromJSON(f, simplifyVector = TRUE)$data
  played <- as.Date(substr(d$game_date, 1, 10))
  stopifnot(!anyNA(played))
  keep <- played < seal_start
  n_dropped_at_seal <<- n_dropped_at_seal + sum(!keep)
  d <- d[keep, , drop = FALSE]
  data.frame(
    file = basename(f),
    play_id = as.character(d$play_id),
    game_pk = as.integer(d$game_pk),
    game_date = as.Date(substr(d$game_date, 1, 10)),
    year = as.integer(d$year),
    plate_x = as.numeric(d$plate_X),
    plate_z = as.numeric(d$plate_Z),
    plate_x_alt = as.numeric(d$plateX),
    plate_z_alt = as.numeric(d$plateZ),
    original_is_strike = as.integer(d$original_isStrike_ump),
    overturned = as.integer(d$is_challengeABS_overturned),
    pre_balls = as.integer(d$pre_ball_count),
    pre_strikes = as.integer(d$pre_strike_count),
    pitcher = as.integer(d$pitcher),
    catcher = as.integer(d$fielder_2),
    stringsAsFactors = FALSE)
}))

record("drawer rows at the seal", sprintf(
  "%s rows read before the boundary, %s rows on or after it dropped at parse",
  comma(nrow(drw_rows)), comma(n_dropped_at_seal)))
check("drawer rows are 2026 and before the boundary",
      all(drw_rows$year == 2026) && all(drw_rows$game_date < seal_start),
      sprintf("%s rows, year 2026 on all, latest game date before seal_start",
              comma(nrow(drw_rows))))
check("drawer plateX equals plate_X",
      identical(drw_rows$plate_x, drw_rows$plate_x_alt) &&
        identical(drw_rows$plate_z, drw_rows$plate_z_alt),
      "the two coordinate spellings the drawer carries are the same numbers on every row")

key_cols <- c("play_id", "game_pk", "game_date", "plate_x", "plate_z", "original_is_strike",
              "overturned", "pre_balls", "pre_strikes", "pitcher", "catcher")
drawer <- unique(drw_rows[, key_cols])
per_play <- table(drw_rows$play_id)
check("each play twice, both copies identical",
      all(per_play == 2) && nrow(drawer) == length(per_play) && !anyNA(drawer),
      sprintf("%s plays in %s rows; every play in exactly 2 team drawers with the same %d fields; 0 nulls",
              comma(length(per_play)), comma(nrow(drw_rows)), length(key_cols) - 1L))
drawer <- drawer[order(drawer$game_pk, drawer$play_id), ]
rownames(drawer) <- NULL
N_DRAWER <- nrow(drawer)

## --- 2. the warehouse, open views only ---------------------------------------

con <- suppressMessages(DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:"))
attached <- FALSE
for (attempt in 1:30) {
  attached <- tryCatch({
    DBI::dbExecute(con, sprintf("ATTACH %s AS abs (READ_ONLY)",
                                DBI::dbQuoteString(con, WAREHOUSE)))
    TRUE
  }, error = function(e) {
    cat(sprintf("RECORD warehouse attach attempt %d failed: %s\n", attempt, conditionMessage(e)))
    FALSE
  })
  if (attached) break
  Sys.sleep(2)
}
check("warehouse attached read-only", attached, WAREHOUSE)
if (!attached) finish()

q <- function(sql, ...) DBI::dbGetQuery(con, sql, ...)
x <- function(sql) invisible(DBI::dbExecute(con, sql))

duckdb::duckdb_register(con, "drawer_play", drawer)

x("CREATE TEMP TABLE pitch26 AS
   SELECT pitch_uid,
          CAST(game_pk AS INTEGER)   AS game_pk,
          plate_x_mid                AS px,
          plate_z_mid                AS pz,
          plane_source,
          balls, strikes,
          CAST(pitcher AS INTEGER)   AS pitcher,
          CAST(fielder_2 AS INTEGER) AS catcher,
          CAST(play_id AS VARCHAR)   AS play_id
   FROM abs.main_marts.v_pitch_open
   WHERE level = 'mlb' AND season = 2026")

x("CREATE TEMP TABLE called AS
   SELECT pitch_uid,
          CAST(game_pk AS INTEGER)   AS game_pk,
          at_bat_number, pitch_number, level, season, official_date, analysis_set,
          call_final,
          call_original              AS w216_call_original,
          challenged,
          is_overturned              AS w216_is_overturned,
          d_signed_in
   FROM abs.main_marts.v_called_pitch_open")

pv <- q("SELECT count(*) AS n,
                count(*) FILTER (WHERE px IS NOT NULL AND pz IS NOT NULL) AS n_xy,
                count(*) FILTER (WHERE px IS NOT NULL AND plane_source = 'mid') AS n_mid,
                count(DISTINCT pitch_uid) AS n_uid,
                count(play_id) AS n_play,
                count(DISTINCT play_id) AS n_play_distinct
         FROM pitch26")
check("2026 raw pair is the mid-plane pair",
      pv$n_xy > 0 && pv$n_mid == pv$n_xy,
      sprintf("%s open MLB 2026 pitches, %s with coordinates, plane_source 'mid' on %s",
              comma(pv$n), comma(pv$n_xy), comma(pv$n_mid)))
check("feed play_id is a key on 2026 pitches",
      pv$n_uid == pv$n && pv$n_play == pv$n_play_distinct && pv$n_play > 0,
      sprintf("%s pitches carry a feed play_id, %s distinct", comma(pv$n_play),
              comma(pv$n_play_distinct)))

cv <- q("SELECT count(*) AS n, count(DISTINCT pitch_uid) AS n_uid,
                count(*) FILTER (WHERE analysis_set = 'open') AS n_open,
                count(*) FILTER (WHERE season = 2026) AS n26,
                count(*) FILTER (WHERE challenged) AS n_chal,
                count(*) FILTER (WHERE official_date < CAST(? AS DATE)) AS n_before
         FROM called", params = list(as.character(seal_start)))
check("called-pitch population", cv$n > 0 && cv$n_uid == cv$n && cv$n_open == cv$n &&
        cv$n_before == cv$n,
      sprintf("%s called pitches in the open view, pitch_uid unique, all open, all before the boundary; %s in 2026, %s challenged",
              comma(cv$n), comma(cv$n26), comma(cv$n_chal)))

## --- 3. DT-28, the drawer coordinate bridge ----------------------------------

x("CREATE TEMP TABLE cand AS
   SELECT d.play_id, p.pitch_uid, (c.pitch_uid IS NOT NULL) AS is_called
   FROM drawer_play AS d
   JOIN pitch26 AS p
     ON p.game_pk = d.game_pk
    AND round(p.px, 2) = round(d.plate_x, 2)
    AND round(p.pz, 2) = round(d.plate_z, 2)
   LEFT JOIN called AS c ON c.pitch_uid = p.pitch_uid")

x("CREATE TEMP TABLE resolved AS
   WITH k AS (
     SELECT play_id,
            count(*) AS n_all,
            count(*) FILTER (WHERE is_called) AS n_called,
            CASE WHEN count(*) = 1 THEN min(pitch_uid) END AS bridge_uid
     FROM cand GROUP BY play_id
   ),
   f AS (
     SELECT play_id, min(pitch_uid) AS feed_uid, count(*) AS n_feed
     FROM pitch26 WHERE play_id IS NOT NULL GROUP BY play_id
   ),
   j AS (
     SELECT d.*,
            coalesce(k.n_all, 0)    AS dt28_candidates,
            coalesce(k.n_called, 0) AS dt28_candidates_called,
            k.bridge_uid,
            f.feed_uid,
            coalesce(f.n_feed, 0)   AS n_feed,
            EXISTS (SELECT 1 FROM cand AS c2
                    WHERE c2.play_id = d.play_id AND c2.pitch_uid = f.feed_uid) AS feed_in_cand
     FROM drawer_play AS d
     LEFT JOIN k ON k.play_id = d.play_id
     LEFT JOIN f ON f.play_id = d.play_id
   )
   SELECT j.*,
          CASE WHEN dt28_candidates = 1 THEN 'drawer_dt28_bridge'
               WHEN n_feed = 1 AND (dt28_candidates = 0 OR feed_in_cand) THEN 'drawer_feed_fallback'
          END AS route,
          CASE WHEN dt28_candidates = 1 THEN bridge_uid
               WHEN n_feed = 1 AND (dt28_candidates = 0 OR feed_in_cand) THEN feed_uid
          END AS pitch_uid
   FROM j")

dt <- q("SELECT count(*) AS n,
                count(*) FILTER (WHERE dt28_candidates >= 1) AS matched,
                count(*) FILTER (WHERE dt28_candidates = 1) AS uniq,
                count(*) FILTER (WHERE dt28_candidates > 1) AS amb,
                count(*) FILTER (WHERE dt28_candidates = 0) AS unmatched,
                count(*) FILTER (WHERE dt28_candidates_called > 1) AS amb_called,
                count(*) FILTER (WHERE dt28_candidates > 1 AND dt28_candidates_called = 1) AS amb_noncalled_twin,
                count(*) FILTER (WHERE route = 'drawer_dt28_bridge') AS by_bridge,
                count(*) FILTER (WHERE route = 'drawer_feed_fallback') AS by_fallback,
                count(*) FILTER (WHERE route IS NULL) AS unrecovered,
                count(*) FILTER (WHERE route IS NULL AND (dt28_candidates > 1 OR n_feed > 1)) AS amb_final,
                count(*) FILTER (WHERE bridge_uid IS NOT NULL AND feed_uid IS NOT NULL) AS both,
                count(*) FILTER (WHERE bridge_uid IS NOT NULL AND feed_uid = bridge_uid) AS both_agree,
                count(*) FILTER (WHERE dt28_candidates > 1 AND feed_in_cand) AS fb_in_cand,
                count(DISTINCT pitch_uid) AS distinct_pitch
         FROM resolved")

dt28_met <- dt$uniq == dt$n && dt$amb == 0 && dt$unmatched == 0
record("DT-28 as written, round(.,2) key", sprintf(
  "%s of %s drawer challenges matched, %s unique, %s ambiguous (%s with two called pitches on the key, %s with one called pitch and one other Statcast row), %s unmatched; bar 100%%, 0 ambiguous, 0 unmatched: %s",
  comma(dt$matched), comma(dt$n), comma(dt$uniq), comma(dt$amb), comma(dt$amb_called),
  comma(dt$amb_noncalled_twin), comma(dt$unmatched),
  if (dt28_met) "met" else "NOT MET, the D-62 feed fallback takes the ambiguous plays"))

ex <- q("SELECT n, count(*) AS plays FROM (
           SELECT d.play_id, count(p.pitch_uid) AS n
           FROM drawer_play AS d
           LEFT JOIN pitch26 AS p
             ON p.game_pk = d.game_pk AND p.px = d.plate_x AND p.pz = d.plate_z
           GROUP BY d.play_id) GROUP BY n ORDER BY n")
record("same key at exact coordinates", paste(sprintf("%s plays with %d candidate(s)",
  comma(ex$plays), ex$n), collapse = "; "))

check("bridge and feed agree where both resolve", dt$both == dt$uniq && dt$both_agree == dt$both,
      sprintf("%s of %s DT-28-unique plays pick the same pitch as the feed play_id",
              comma(dt$both_agree), comma(dt$both)))
check("feed fallback pick is a DT-28 candidate", dt$fb_in_cand == dt$amb,
      sprintf("%s of %s ambiguous plays: the play_id pitch is one of the key's candidates",
              comma(dt$fb_in_cand), comma(dt$amb)))

## --- 4. the resolved pitch against the drawer --------------------------------

rv <- q("SELECT count(*) AS n,
                count(*) FILTER (WHERE p.px = r.plate_x AND p.pz = r.plate_z) AS same_xy,
                count(*) FILTER (WHERE p.balls = r.pre_balls AND p.strikes = r.pre_strikes) AS same_count,
                count(*) FILTER (WHERE p.pitcher = r.pitcher AND p.catcher = r.catcher) AS same_battery,
                count(*) FILTER (WHERE c.pitch_uid IS NOT NULL) AS is_called,
                count(*) FILTER (WHERE c.challenged) AS is_challenged,
                count(*) FILTER (WHERE c.game_pk = r.game_pk AND c.official_date = r.game_date) AS same_game_day
         FROM resolved AS r
         JOIN pitch26 AS p ON p.pitch_uid = r.pitch_uid
         LEFT JOIN called AS c ON c.pitch_uid = r.pitch_uid
         WHERE r.route IS NOT NULL")
check("resolved pitch matches the drawer row",
      rv$n == dt$n && rv$same_xy == rv$n && rv$same_count == rv$n && rv$same_battery == rv$n,
      sprintf("%s plays: plate_X and plate_Z bit-equal on %s, pre-pitch count on %s, pitcher and catcher on %s",
              comma(rv$n), comma(rv$same_xy), comma(rv$same_count), comma(rv$same_battery)))
check("resolved pitch is a called, challenged pitch",
      rv$is_called == rv$n && rv$is_challenged == rv$n && rv$same_game_day == rv$n &&
        dt$distinct_pitch == rv$n,
      sprintf("%s of %s in the open called-pitch view, %s flagged challenged, %s on the drawer's game and date, %s distinct pitches",
              comma(rv$is_called), comma(rv$n), comma(rv$is_challenged),
              comma(rv$same_game_day), comma(dt$distinct_pitch)))

## --- 5. the reconstruction ---------------------------------------------------

x("CREATE TEMP TABLE built AS
   WITH src AS (
     SELECT c.*,
            r.play_id                AS drawer_play_id,
            r.route                  AS route,
            r.overturned             AS drawer_overturned,
            r.original_is_strike     AS drawer_original_is_strike,
            r.dt28_candidates        AS dt28_candidates,
            r.dt28_candidates_called AS dt28_candidates_called
     FROM called AS c
     LEFT JOIN (SELECT * FROM resolved WHERE route IS NOT NULL) AS r
       ON r.pitch_uid = c.pitch_uid
   ),
   flag AS (
     SELECT src.*,
            CASE WHEN route IS NOT NULL THEN drawer_overturned = 1
                 WHEN challenged THEN w216_is_overturned
                 ELSE false
            END AS is_overturned_new,
            CASE WHEN route IS NOT NULL THEN route
                 WHEN challenged THEN 'feed_only'
                 ELSE 'not_challenged'
            END AS source_new
     FROM src
   )
   SELECT pitch_uid,
          game_pk,
          CAST(at_bat_number AS INTEGER) AS at_bat_number,
          CAST(pitch_number AS INTEGER)  AS pitch_number,
          level,
          CAST(season AS INTEGER)        AS season,
          official_date,
          analysis_set,
          call_final,
          CASE WHEN is_overturned_new THEN
                 CASE call_final WHEN 'strike' THEN 'ball' WHEN 'ball' THEN 'strike' END
               ELSE call_final
          END                            AS call_original,
          is_overturned_new              AS is_overturned,
          challenged,
          source_new                     AS original_call_source,
          drawer_play_id,
          CAST(dt28_candidates AS INTEGER)        AS dt28_candidates,
          CAST(dt28_candidates_called AS INTEGER) AS dt28_candidates_called,
          -- audit columns, dropped before the write
          drawer_original_is_strike      AS _drawer_original_is_strike,
          w216_call_original             AS _w216_call_original,
          d_signed_in                    AS _d_signed_in
   FROM flag
   ORDER BY season, game_pk, at_bat_number, pitch_number")

bv <- q("SELECT count(*) AS n,
          count(*) FILTER (WHERE call_final NOT IN ('ball', 'strike') OR call_final IS NULL) AS bad_final,
          count(*) FILTER (WHERE call_original NOT IN ('ball', 'strike') OR call_original IS NULL) AS bad_orig,
          count(*) FILTER (WHERE is_overturned AND call_original = call_final) AS ovt_same,
          count(*) FILTER (WHERE NOT is_overturned AND call_original <> call_final) AS kept_moved,
          count(*) FILTER (WHERE NOT challenged AND is_overturned) AS unchal_ovt,
          count(*) FILTER (WHERE is_overturned IS NULL OR challenged IS NULL OR original_call_source IS NULL) AS nulls,
          count(*) FILTER (WHERE original_call_source LIKE 'drawer%') AS n_drawer,
          count(*) FILTER (WHERE original_call_source = 'drawer_dt28_bridge') AS n_bridge,
          count(*) FILTER (WHERE original_call_source = 'drawer_feed_fallback') AS n_fallback,
          count(*) FILTER (WHERE original_call_source = 'feed_only') AS n_feed_only,
          count(*) FILTER (WHERE original_call_source = 'not_challenged') AS n_unchal,
          count(*) FILTER (WHERE challenged) AS n_chal,
          count(*) FILTER (WHERE original_call_source LIKE 'drawer%' AND
                                 (CASE _drawer_original_is_strike WHEN 1 THEN 'strike' WHEN 0 THEN 'ball' END)
                                   = call_original) AS drawer_orig_agree,
          count(*) FILTER (WHERE call_original = _w216_call_original) AS w216_agree,
          count(*) FILTER (WHERE season = 2026 AND is_overturned) AS ovt26,
          count(*) FILTER (WHERE season = 2026) AS n26,
          count(*) FILTER (WHERE season = 2026 AND abs(_d_signed_in) <= 3) AS n26_band,
          count(*) FILTER (WHERE season = 2026 AND abs(_d_signed_in) <= 3 AND is_overturned) AS ovt26_band,
          count(*) FILTER (WHERE season < 2026 AND (challenged OR is_overturned)) AS pre26_chal
        FROM built")

check("call vocabulary and the W2.16 rule",
      bv$bad_final == 0 && bv$bad_orig == 0 && bv$ovt_same == 0 && bv$kept_moved == 0 &&
        bv$unchal_ovt == 0 && bv$nulls == 0,
      sprintf("%s rows: calls outside ball/strike %d and %d; overturned but unchanged %d; kept but moved %d; unchallenged but overturned %d; nulls %d",
              comma(bv$n), bv$bad_final, bv$bad_orig, bv$ovt_same, bv$kept_moved,
              bv$unchal_ovt, bv$nulls))
check("DT-22 form: drawer original call", bv$drawer_orig_agree == bv$n_drawer && bv$n_drawer == N_DRAWER,
      sprintf("original_isStrike_ump equals the reconstructed call on %s of %s drawer challenges",
              comma(bv$drawer_orig_agree), comma(bv$n_drawer)))
check("agrees with the warehouse W2.16 call_original", bv$w216_agree == bv$n,
      sprintf("%s of %s called pitches", comma(bv$w216_agree), comma(bv$n)))
check("every challenged pitch has a source",
      bv$n == cv$n && bv$n_chal == bv$n_drawer + bv$n_feed_only &&
        bv$n_unchal == bv$n - bv$n_chal && bv$pre26_chal == 0,
      sprintf("%s rows for %s called pitches; %s challenged = %s drawer + %s feed only; %s not challenged; %d challenged before 2026",
              comma(bv$n), comma(cv$n), comma(bv$n_chal), comma(bv$n_drawer),
              comma(bv$n_feed_only), comma(bv$n_unchal), bv$pre26_chal))

feed_only <- q("SELECT pitch_uid, call_final, call_original, is_overturned FROM built
                WHERE original_call_source = 'feed_only' ORDER BY pitch_uid")
if (nrow(feed_only) > 0) {
  record("feed-only challenges", paste(sprintf("%s (%s, overturned %s)", feed_only$pitch_uid,
    feed_only$call_original, tolower(feed_only$is_overturned)), collapse = "; "))
}

## --- 6. CH1-A2, the hard gate -------------------------------------------------

ch1a2 <- dt$unrecovered == 0 && dt$amb_final == 0 && bv$n_drawer == N_DRAWER &&
  dt$by_bridge + dt$by_fallback == N_DRAWER && bv$n_chal == bv$n_drawer + bv$n_feed_only
check("CH1-A2 original call recovered", ch1a2,
      sprintf("%s of %s drawer challenges recovered (%s by the DT-28 bridge, %s by the feed fallback), %d ambiguous, %d unrecovered; %s feed-only challenge(s) from the W2.16 feed reconstruction; %s of %s challenged pitches carry an original call",
              comma(dt$by_bridge + dt$by_fallback), comma(N_DRAWER), comma(dt$by_bridge),
              comma(dt$by_fallback), dt$amb_final, dt$unrecovered, comma(bv$n_feed_only),
              comma(bv$n_drawer + bv$n_feed_only), comma(bv$n_chal)))

record("2026 overturns", sprintf(
  "%s overturned of %s called pitches (%.2f%%); SOP estimate about 4,716 on about 356k",
  comma(bv$ovt26), comma(bv$n26), 100 * bv$ovt26 / bv$n26))
record("2026 overturns in |d| <= 3 in", sprintf(
  "%s of %s called pitches in the shadow band (%.2f%%); SOP estimate 6-7%%",
  comma(bv$ovt26_band), comma(bv$n26_band), 100 * bv$ovt26_band / bv$n26_band))

## --- 7. provenance -------------------------------------------------------------

man <- tryCatch(utils::read.csv(MANIFEST, stringsAsFactors = FALSE), error = function(e) NULL)
fetched <- if (is.null(man)) character(0) else
  man$fetched_at_utc[grepl("/leaderboard/services/abs/[0-9]+\\?year=2026&challengeType=team-summary",
                           man$url) & grepl("level=mlb", man$url, fixed = TRUE)]
record("drawer pull", sprintf("%d manifest rows for the MLB 2026 drawer endpoint, fetched %s to %s UTC",
                              length(fetched), if (length(fetched)) min(fetched) else "NA",
                              if (length(fetched)) max(fetched) else "NA"))
drawer_md5 <- unname(tools::md5sum(DRAWER_FILES))
drawer_digest <- digest::digest(paste(basename(DRAWER_FILES), drawer_md5, collapse = "\n"),
                                algo = "sha256", serialize = FALSE)

out <- q("SELECT * EXCLUDE (_drawer_original_is_strike, _w216_call_original, _d_signed_in)
          FROM built ORDER BY season, game_pk, at_bat_number, pitch_number")
meta <- list(
  w36_step = "W3.6 original-call reconstruction",
  w36_grain = "one row per called pitch in v_called_pitch_open; key pitch_uid",
  w36_rule = "call_original = call_final unless is_overturned, then the other call",
  w36_sources = paste("Statcast via warehouse/abs.duckdb open views v_called_pitch_open and v_pitch_open;",
                      "Savant ABS drawer", DRAWER_ENDPOINT, "(30 files, data/raw/savant/abs_drawer);",
                      "MLB Stats API feed play_id via v_pitch_open"),
  w36_drawer_fetched_utc = if (length(fetched)) paste(min(fetched), "to", max(fetched)) else "NA",
  w36_drawer_sha256 = drawer_digest,
  w36_seal_start_date = as.character(seal_start),
  w36_licence = LICENCE,
  w36_counts = sprintf(paste("rows %d; challenged %d; drawer %d (dt28 bridge %d, feed fallback %d);",
                             "feed_only %d; dt28 ambiguous %d; unrecovered %d; ambiguous after fallback %d"),
                       nrow(out), bv$n_chal, bv$n_drawer, bv$n_bridge, bv$n_fallback,
                       bv$n_feed_only, dt$amb, dt$unrecovered, dt$amb_final)
)

build_table <- function(df) {
  tb <- arrow::arrow_table(df)
  for (k in names(meta)) tb$metadata[[k]] <- meta[[k]]
  tb
}

## --- 8. write, or compare -----------------------------------------------------

if (CHECK_ONLY) {
  on_disk <- file.exists(OUT_FILE)
  check("artifact on disk", on_disk, OUT_FILE)
  if (on_disk) {
    old_tb <- arrow::read_parquet(OUT_FILE, as_data_frame = FALSE)
    old <- as.data.frame(old_tb)
    same_shape <- identical(names(old), names(out)) && nrow(old) == nrow(out)
    same_types <- same_shape && identical(vapply(old, function(v) class(v)[1], ""),
                                          vapply(out, function(v) class(v)[1], ""))
    same_rows <- same_types && isTRUE(all.equal(old, out, check.attributes = FALSE))
    check("artifact equals a rebuild from sources", same_rows,
          sprintf("%s rows x %d columns on disk; rebuilt %s x %d; names, types and values %s",
                  comma(nrow(old)), ncol(old), comma(nrow(out)), ncol(out),
                  if (same_rows) "identical" else "differ"))
    old_meta <- old_tb$metadata[names(meta)]
    same_meta <- identical(unname(unlist(old_meta)), unname(unlist(meta)))
    check("artifact provenance equals a rebuild", same_meta,
          sprintf("%d w36_* metadata keys", length(meta)))
    record("artifact md5", unname(tools::md5sum(OUT_FILE)))
  }
} else if (length(failures) > 0) {
  record("write skipped", sprintf("%d check(s) failed; %s left as it was", length(failures), OUT_FILE))
} else {
  dir.create(OUT_DIR, recursive = TRUE, showWarnings = FALSE)
  tmp <- file.path(OUT_DIR, sprintf(".original_call.parquet.tmp-%d", Sys.getpid()))
  arrow::write_parquet(build_table(out), tmp)
  ok <- file.rename(tmp, OUT_FILE)
  if (!ok) unlink(tmp)
  check("artifact written", ok && file.exists(OUT_FILE),
        sprintf("%s, %s rows x %d columns, %s bytes, md5 %s", OUT_FILE, comma(nrow(out)), ncol(out),
                comma(file.size(OUT_FILE)), unname(tools::md5sum(OUT_FILE))))
}

nulls <- vapply(out, function(v) sum(is.na(v)), 0)
record("null counts", paste(sprintf("%s %s", names(nulls), comma(nulls)), collapse = "; "))
by_season <- q("SELECT season, count(*) AS n, count(*) FILTER (WHERE challenged) AS chal,
                       count(*) FILTER (WHERE is_overturned) AS ovt
                FROM built GROUP BY season ORDER BY season")
record("rows by season", paste(sprintf("%d %s (challenged %s, overturned %s)", by_season$season,
  comma(by_season$n), comma(by_season$chal), comma(by_season$ovt)), collapse = "; "))

DBI::dbDisconnect(con, shutdown = TRUE)
finish()
