#!/usr/bin/env Rscript
# R/ch1/11_zone_gate.R - SOP step W3.8, the zone-truth gate. Hard go/no-go, DT-21.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/11_zone_gate.R           score the zone, write out/ch1/tab/T2_zone_gate.csv
#   Rscript R/ch1/11_zone_gate.R --check   score the zone again, compare with the file on disk,
#                                           write nothing
#
# WHAT IT TESTS. On a challenged pitch the final call is the ABS verdict. This
# script rebuilds that verdict from the zone and scores it against the call the
# review produced. The zone is D-14's primary zone truth (SOP section 2.5):
#
#   top, bot   53.5% and 27% of the batter's ABS-measured height, h_abs_in in
#              dim_batter_season, through abs_top_ft() and abs_bot_ft()
#   d          signed_edge_in(x_mid, z_mid, top, bot): ball-centre distance from
#              the zone edge, inches, negative inside, Euclidean at the corners
#   e          d - BALL_R_IN, with BALL_R_IN = 1.45 in: the any-part-of-ball
#              distance, which is Savant's edge_dist_calc
#   verdict    strike when e < 0, else ball
#
# Every function and constant comes from R/lib/zone.R. Nothing is fitted: r is
# fixed at 1.45 in and no parameter is estimated from these pitches.
#
# WHAT IT REPORTS, one row each in T2:
#
#   overall        every challenged pitch
#   outside_band   |e| > 0.5 in, outside the coin-flip band
#   inside_band    |e| <= 0.5 in
#   edge_side, edge_top, edge_bot
#                  by nearest_edge() of the ball centre on the same zone
#   arm_roster_offset_overall, arm_roster_offset_outside_band
#                  the same rule on Chapter 1's primary height, roster height
#                  plus the one calibration offset (D-R0-02), read as H from the
#                  W3.7 analysis table. Reported, not gated: ABS scores a pitch
#                  on the measured height, so this row prices the height choice,
#                  not the edge rule.
#
# THE GATE (DT-21, SOP section 6). Overall agreement >= 99.75% and agreement
# outside the band >= 99.95%. Both are compared in integers, n_agree * 10000
# against threshold_bp * n, so no rounding sits between a count and a verdict.
# If either fails the script still writes T2 and then exits 1. SOP W3.8: stop
# and re-fit r before any surface is fit.
#
# THE POPULATION. Every MLB 2026 review in v_challenge_open. The view carries
# only analysis_set = 'open', so the population ends on the last open day that
# absump.paths names. Pitches after that day are outside this read by design and
# join the gate when W3.23 runs on the held-out games.
#
# CROSS-CHECKS, each a PASS/FAIL line:
#   - the published sz_top/sz_bot equal the zone rebuilt from h_abs_in
#   - e equals the warehouse's edge_dist_calc, W2.14's Python twin
#   - e equals d_abs - 1.45 from data/marts/ch1_called.parquet (W3.7), on the
#     same set of challenged pitches, and the two tables agree on the calls
#   - call_final is call_original flipped exactly when is_overturned
#
# READS. abs.main_marts.v_challenge_open, v_called_pitch_open and
# dim_batter_season, each restricted to analysis_set = 'open' in its own
# statement, on a read-only attach; data/marts/ch1_called.parquet.
#
# WRITES. out/ch1/tab/T2_zone_gate.csv, and only when its content changes, so a
# second run leaves the file as the first run left it. Check mode writes nothing.
#
# Exit 0 when every check passes and the gate holds, 1 otherwise, 2 on a usage error.

options(warn = 1, digits = 12)
t_start <- Sys.time()

args_all <- commandArgs(trailingOnly = FALSE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1 || (length(args) == 1 && !identical(args, "--check"))) {
  cat("usage: Rscript R/ch1/11_zone_gate.R [--check]\n", file = stderr())
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
})

source("R/lib/zone.R")

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
  cat(sprintf("W3.8 %s: %d PASS, %d FAIL, %.1f s\n",
              if (CHECK_ONLY) "check" else "build", n_pass, length(failures),
              as.numeric(difftime(Sys.time(), t_start, units = "secs"))))
  if (length(failures) > 0) {
    cat("FAILED CLAUSES:\n", paste0("  ", failures, "\n"), sep = "")
    quit(status = 1)
  }
  quit(status = 0)
}

## --- constants -----------------------------------------------------------------

GATE_OVERALL_BP <- 9975L   # DT-21: >= 99.75% overall, in basis points
GATE_OUTSIDE_BP <- 9995L   # DT-21: >= 99.95% outside the band
BAND_IN         <- 0.5     # the coin-flip band, |e| <= 0.5 in
ZONE_TOL_FT     <- 1e-9    # published zone against the zone rebuilt from h_abs_in
EDGE_TOL_IN     <- 1e-9    # e against edge_dist_calc and against W3.7's d_abs
EDGE_LEVELS     <- c("side", "top", "bot")
# The public benchmark, SOP W3.8 and section 11: use-it-or-lose-it, 2026-09-22.
BENCH <- list(overall = c(99.75, 10155), outside_band = c(99.99, NA),
              edge_side = c(99.70, NA), edge_top = c(99.88, NA), edge_bot = c(99.77, NA))

T2_FILE <- file.path(ROOT, "out", "ch1", "tab", "T2_zone_gate.csv")

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
       mart = trimws(out[n]))
}
lay <- paths_from_python()
record("layout", sprintf("warehouse %s; last open day %s; analysis table %s",
                         lay$duckdb, format(lay$last_open), lay$mart))

for (f in c(lay$duckdb, lay$mart)) check("input present", file.exists(f), f)
if (CHECK_ONLY) check("T2 present for comparison", file.exists(T2_FILE), T2_FILE)
if (length(failures) > 0) finish()

## --- 1. the challenged pitches, open views only -----------------------------------

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
q <- function(sql) DBI::dbGetQuery(con, sql)

ch <- q("
  SELECT c.challenge_uid, c.pitch_uid,
         CAST(c.game_pk AS INTEGER) AS game_pk, c.at_bat_number, c.pitch_number,
         c.official_date, c.season, c.level, c.analysis_set,
         c.review_level, c.review_type, c.pitch_matched, c.in_progress,
         c.call_original, c.call_final, c.is_overturned,
         c.edge_dist_calc AS wh_edge_dist_calc,
         p.pitch_uid AS p_pitch_uid, p.game_type, p.description,
         p.plate_x_mid, p.plate_z_mid, p.sz_top, p.sz_bot,
         CAST(p.batter AS INTEGER) AS batter,
         b.h_abs_in
  FROM abs.main_marts.v_challenge_open AS c
  LEFT JOIN abs.main_marts.v_called_pitch_open AS p
    ON p.pitch_uid = c.pitch_uid AND p.analysis_set = 'open'
  LEFT JOIN abs.main_marts.dim_batter_season AS b
    ON b.batter = p.batter AND b.season = c.season
   AND b.level = 'mlb' AND b.analysis_set = 'open'
  WHERE c.level = 'mlb' AND c.season = 2026 AND c.analysis_set = 'open'
  ORDER BY c.game_pk, c.at_bat_number, c.pitch_number, c.review_level")
try(DBI::dbDisconnect(con, shutdown = TRUE), silent = TRUE)
ch$official_date <- as.Date(ch$official_date)
n <- nrow(ch)
record("challenges read", sprintf("%s MLB 2026 reviews from the open view, %s to %s",
                                  comma(n), format(min(ch$official_date)), format(max(ch$official_date))))

## --- 2. the population ----------------------------------------------------------

check("population", n > 0 && all(ch$level == "mlb") && all(ch$season == 2026L) &&
        all(ch$analysis_set == "open") && max(ch$official_date) <= lay$last_open,
      sprintf("MLB, season 2026, analysis_set open, last day %s <= last open day %s",
              format(max(ch$official_date)), format(lay$last_open)))
check("one review per challenged pitch", !anyDuplicated(ch$pitch_uid) && !anyNA(ch$pitch_uid),
      sprintf("%s reviews on %s distinct pitch_uid", comma(n), comma(length(unique(ch$pitch_uid)))))
check("every review matched to its pitch and closed",
      all(ch$pitch_matched %in% TRUE) && all(ch$in_progress %in% FALSE),
      sprintf("%d unmatched, %d in progress", sum(!(ch$pitch_matched %in% TRUE)),
              sum(!(ch$in_progress %in% FALSE))))
record("review levels", paste(sprintf("%s %s", names(table(ch$review_level)),
                                      comma(table(ch$review_level))), collapse = ", "))
record("review types", paste(sprintf("%s %s", names(table(ch$review_type)),
                                     comma(table(ch$review_type))), collapse = ", "))
check("every review joins a called pitch with mid-plate coordinates",
      !anyNA(ch$p_pitch_uid) && !anyNA(ch$plate_x_mid) && !anyNA(ch$plate_z_mid),
      sprintf("%d without a called pitch, %d without coordinates", sum(is.na(ch$p_pitch_uid)),
              sum(is.na(ch$plate_x_mid) | is.na(ch$plate_z_mid))))
check("regular season only", all(ch$game_type %in% "R"),
      paste(sprintf("game_type %s %s", names(table(ch$game_type, useNA = "ifany")),
                    comma(table(ch$game_type, useNA = "ifany"))), collapse = ", "))
check("every batter carries an ABS-measured height", !anyNA(ch$h_abs_in),
      sprintf("%d of %s pitches without h_abs_in", sum(is.na(ch$h_abs_in)), comma(n)))
if (length(failures) > 0) finish()

## --- 3. the observed outcome -----------------------------------------------------

flip <- c(strike = "ball", ball = "strike")
check("calls are strike or ball", all(ch$call_original %in% names(flip)) &&
        all(ch$call_final %in% names(flip)) && !anyNA(ch$is_overturned),
      sprintf("%d rows outside {strike, ball} or without is_overturned",
              sum(!(ch$call_original %in% names(flip)) | !(ch$call_final %in% names(flip)) |
                    is.na(ch$is_overturned))))
expect_final <- ifelse(ch$is_overturned, unname(flip[ch$call_original]), ch$call_original)
check("call_final is call_original flipped exactly when overturned",
      identical(expect_final, ch$call_final),
      sprintf("%d mismatches over %s reviews", sum(expect_final != ch$call_final), comma(n)))
pub_final <- ifelse(ch$description == "called_strike", "strike", "ball")
check("published description carries the final call", identical(pub_final, ch$call_final),
      sprintf("%d mismatches; called_strike %s, ball %s, blocked_ball %s",
              sum(pub_final != ch$call_final), comma(sum(ch$description == "called_strike")),
              comma(sum(ch$description == "ball")), comma(sum(ch$description == "blocked_ball"))))
record("outcomes", sprintf("%s overturned, %s upheld; final strike %s, final ball %s",
                           comma(sum(ch$is_overturned)), comma(sum(!ch$is_overturned)),
                           comma(sum(ch$call_final == "strike")), comma(sum(ch$call_final == "ball"))))

## --- 4. the zone and the verdict ---------------------------------------------------

top <- abs_top_ft(ch$h_abs_in)
bot <- abs_bot_ft(ch$h_abs_in)
dz_top <- max(abs(top - ch$sz_top)); dz_bot <- max(abs(bot - ch$sz_bot))
check("published zone is 53.5%/27% of h_abs_in", !anyNA(ch$sz_top) && !anyNA(ch$sz_bot) &&
        dz_top <= ZONE_TOL_FT && dz_bot <= ZONE_TOL_FT,
      sprintf("max |top - sz_top| %.3g ft, max |bot - sz_bot| %.3g ft, bar %.0e ft",
              dz_top, dz_bot, ZONE_TOL_FT))

d <- signed_edge_in(ch$plate_x_mid, ch$plate_z_mid, top, bot)
e <- d - BALL_R_IN
edge <- nearest_edge(ch$plate_x_mid, ch$plate_z_mid, top, bot)
pred <- ifelse(e < 0, "strike", "ball")
agree <- pred == ch$call_final
outside <- abs(e) > BAND_IN

# The warehouse's edge_dist_calc (W2.14, the Python twin) is taken on the
# published sz_top/sz_bot. Scored on that same zone, R and Python must agree to
# EDGE_TOL_IN. The gate's own zone differs from the published one by at most
# ZONE_TOL_FT, and the edge distance is 1-Lipschitz in top and bot, so e may sit
# up to 12 * ZONE_TOL_FT inches from the published-zone distance, and no verdict
# may change between the two.
e_pub <- signed_edge_in(ch$plate_x_mid, ch$plate_z_mid, ch$sz_top, ch$sz_bot) - BALL_R_IN
de_wh <- max(abs(e_pub - ch$wh_edge_dist_calc))
check("R edge distance equals the warehouse edge_dist_calc",
      !anyNA(ch$wh_edge_dist_calc) && de_wh <= EDGE_TOL_IN,
      sprintf("published zone: max |e_pub - edge_dist_calc| %.3g in over %s pitches, bar %.0e in",
              de_wh, comma(n), EDGE_TOL_IN))
de_pub <- max(abs(e - e_pub))
check("gate zone and published zone give the same verdicts",
      de_pub <= 12 * ZONE_TOL_FT && identical(e < 0, e_pub < 0),
      sprintf("max |e - e_pub| %.3g in, bar %.1e in; %d verdicts differ", de_pub, 12 * ZONE_TOL_FT,
              sum((e < 0) != (e_pub < 0))))

## --- 5. the analysis table, W3.7 --------------------------------------------------

mt <- as.data.frame(arrow::read_parquet(
  lay$mart, col_select = c("pitch_uid", "season", "challenged", "is_overturned", "cs",
                           "H", "H_abs", "d_abs")))
mt <- mt[mt$season == 2026L & mt$challenged %in% TRUE, ]
m_idx <- match(ch$pitch_uid, mt$pitch_uid)
in_mart <- !is.na(m_idx)
check("W3.7 carries the same challenged pitches",
      all(in_mart) && nrow(mt) == n,
      sprintf("%s challenged 2026 rows in the analysis table, %s reviews here, %d not found",
              comma(nrow(mt)), comma(n), sum(!in_mart)))
if (!all(in_mart)) finish()
mm <- mt[m_idx, ]
de_mart <- max(abs((mm$d_abs - BALL_R_IN) - e))
check("e equals W3.7 d_abs - 1.45", !anyNA(mm$d_abs) && de_mart <= EDGE_TOL_IN &&
        identical(mm$H_abs, ch$h_abs_in),
      sprintf("max |d_abs - 1.45 - e| %.3g in; H_abs equal to h_abs_in on %s rows", de_mart, comma(n)))
check("W3.7 agrees on the calls", identical(mm$is_overturned, ch$is_overturned) &&
        identical(mm$cs == 1L, ch$call_original == "strike"),
      sprintf("is_overturned and cs against call_original, %s rows", comma(n)))

# The roster-plus-offset arm: W3.7's primary H, the same rule, reported and not gated.
h_arm <- mm$H
e_arm <- signed_edge_in(ch$plate_x_mid, ch$plate_z_mid, abs_top_ft(h_arm), abs_bot_ft(h_arm)) - BALL_R_IN
agree_arm <- ifelse(e_arm < 0, "strike", "ball") == ch$call_final
outside_arm <- abs(e_arm) > BAND_IN
record("roster+offset arm height", sprintf("H - h_abs_in: mean %+.4f in, sd %.4f in, max |.| %.4f in",
                                           mean(h_arm - ch$h_abs_in), sd(h_arm - ch$h_abs_in),
                                           max(abs(h_arm - ch$h_abs_in))))

## --- 6. the table ---------------------------------------------------------------

pct <- function(a, b) if (b > 0) sprintf("%.4f", 100 * a / b) else ""
num <- function(x) if (is.na(x)) "" else format(x, scientific = FALSE, trim = TRUE)
row <- function(row_id, population, zone, sel, ag, gate_bp, note) {
  nn <- sum(sel); na <- sum(ag & sel)
  bench <- BENCH[[row_id]]
  verdict <- if (is.na(gate_bp)) "reported" else if (na * 10000 >= gate_bp * nn && nn > 0) "PASS" else "FAIL"
  data.frame(row_id = row_id, population = population, zone = zone,
             n = nn, n_agree = na, n_disagree = nn - na,
             agreement_pct = pct(na, nn),
             threshold_pct = if (is.na(gate_bp)) "" else sprintf("%.2f", gate_bp / 100),
             verdict = verdict,
             benchmark_pct = if (is.null(bench)) "" else sprintf("%.2f", bench[1]),
             benchmark_n = if (is.null(bench)) "" else num(bench[2]),
             note = note, stringsAsFactors = FALSE)
}
POP <- sprintf("MLB 2026 regular season, challenged pitches, %s to %s",
               format(min(ch$official_date)), format(max(ch$official_date)))
Z_ABS <- "ABS-measured height, 53.5%/27%, mid-plate, r = 1.45 in"
Z_ARM <- "roster height plus offset, 53.5%/27%, mid-plate, r = 1.45 in"
all_rows <- rep(TRUE, n)
t2 <- rbind(
  row("overall", POP, Z_ABS, all_rows, agree, GATE_OVERALL_BP, "DT-21 overall"),
  row("outside_band", POP, Z_ABS, outside, agree, GATE_OUTSIDE_BP,
      "DT-21 outside the band, |e| > 0.5 in"),
  row("inside_band", POP, Z_ABS, !outside, agree, NA, "|e| <= 0.5 in"),
  row("edge_side", POP, Z_ABS, edge == "side", agree, NA, "nearest edge of the ball centre"),
  row("edge_top", POP, Z_ABS, edge == "top", agree, NA, "nearest edge of the ball centre"),
  row("edge_bot", POP, Z_ABS, edge == "bot", agree, NA, "nearest edge of the ball centre"),
  row("arm_roster_offset_overall", POP, Z_ARM, all_rows, agree_arm, NA,
      "not gated: Chapter 1 primary height (D-R0-02), not the height ABS scores"),
  row("arm_roster_offset_outside_band", POP, Z_ARM, outside_arm, agree_arm, NA,
      "not gated: band on this arm's own e")
)
check("per-edge rows partition the population", sum(t2$n[t2$row_id %in% paste0("edge_", EDGE_LEVELS)]) == n &&
        all(edge %in% EDGE_LEVELS),
      sprintf("side %s + top %s + bot %s = %s", comma(sum(edge == "side")), comma(sum(edge == "top")),
              comma(sum(edge == "bot")), comma(n)))

for (i in seq_len(nrow(t2))) {
  record(sprintf("T2 %s", t2$row_id[i]),
         sprintf("%s/%s = %s%%%s", comma(t2$n_agree[i]), comma(t2$n[i]), t2$agreement_pct[i],
                 if (nzchar(t2$benchmark_pct[i])) sprintf(" (benchmark %s%%)", t2$benchmark_pct[i]) else ""))
}
miss <- which(!agree)
for (i in miss) {
  record("disagreement", sprintf("%s %s %s -> %s, rebuilt %s, e %+.4f in, edge %s, %s band",
                                 ch$pitch_uid[i], format(ch$official_date[i]), ch$call_original[i],
                                 ch$call_final[i], pred[i], e[i], edge[i],
                                 if (outside[i]) "outside the" else "inside the"))
}

## --- 7. write or compare ---------------------------------------------------------

tc <- textConnection("csv_lines", "w", local = TRUE)
utils::write.csv(t2, tc, row.names = FALSE, na = "")
close(tc)
csv_text <- paste0(paste(csv_lines, collapse = "\n"), "\n")

if (CHECK_ONLY) {
  on_disk <- paste0(paste(readLines(T2_FILE, warn = FALSE), collapse = "\n"), "\n")
  check("T2 on disk equals the rebuild", identical(on_disk, csv_text),
        sprintf("%s, %d rows", T2_FILE, nrow(t2)))
} else {
  dir.create(dirname(T2_FILE), recursive = TRUE, showWarnings = FALSE)
  old <- if (file.exists(T2_FILE)) paste0(paste(readLines(T2_FILE, warn = FALSE), collapse = "\n"), "\n") else NA
  if (!identical(old, csv_text)) {
    tmp <- paste0(T2_FILE, ".tmp")
    writeLines(csv_lines, tmp)
    file.rename(tmp, T2_FILE)
    record("T2 written", sprintf("%s, %d rows", T2_FILE, nrow(t2)))
  } else {
    record("T2 unchanged", sprintf("%s, %d rows, content identical", T2_FILE, nrow(t2)))
  }
}

## --- 8. the gate ---------------------------------------------------------------

g_all <- t2[t2$row_id == "overall", ]
g_out <- t2[t2$row_id == "outside_band", ]
check("DT-21 overall >= 99.75%", g_all$verdict == "PASS",
      sprintf("%s/%s = %s%%", comma(g_all$n_agree), comma(g_all$n), g_all$agreement_pct))
check("DT-21 outside the +/-0.5 in band >= 99.95%", g_out$verdict == "PASS",
      sprintf("%s/%s = %s%%", comma(g_out$n_agree), comma(g_out$n), g_out$agreement_pct))
if (g_all$verdict != "PASS" || g_out$verdict != "PASS") {
  cat("DT-21 NO-GO: stop, re-fit r (SOP W3.8) before any surface is fit.\n")
}

finish()
