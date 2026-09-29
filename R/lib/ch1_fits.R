# R/lib/ch1_fits.R - shared code for the Chapter 1 sprint fits: SOP W3.14 to W3.18, W3.21,
# W6.7 and W6.8.
#
# Sourced by R/ch1/20_surfaces.R (W3.14), 22_estimands.R (W3.15), 23_decomposition.R (W3.16),
# 24_plane.R (W3.17), 25_heterogeneity.R (W3.18), 26_placebos.R (W3.21), 27_abstract_ch1.R
# (W6.7), 28_umpire_summary.R (W6.8) and 29_synthetic_table.R, the dry-run generator. It
# sources R/lib/zone.R, ch1_estimands.R, ch1_decomp.R and ch1_hetero.R in turn.
#
# Every constant here is a pre-registered value, and the source is named beside it:
# docs/prereg/ch1.md (the annex), PREREGISTRATION.md, DECISIONS.md or SOP W3.14 to W3.21.
#
# THE GUARDS. Every entry point calls start_run() before it reads a row.
#   1. The seal. The loader filters official_date to the last open day inside the arrow
#      scan, so no later row reaches R, and asserts it afterwards. The day comes from
#      absump.paths.LAST_OPEN_DATE. No held-out date is written in this file (GD-04).
#   2. GD-12. A run on real data refuses to start unless
#      `git merge-base --is-ancestor <prereg tag> HEAD` succeeds and the fit code is
#      committed, so every receipt names a commit that descends from the tag. The tag name
#      comes from config/seal.yml.
#   3. The synthetic marker. A synthetic table carries the column is_synthetic, TRUE on every
#      row. Only such a table runs before the tag, and a synthetic run may not write inside
#      the repository, where GD-01, GD-12 and the number gate read.
#
# THE HEIGHT RULE (DECISIONS.md D-R0-02 and D-P4-04). The primary cohort is every P0 pitch
# with batter height = roster height + an offset that depends on the cohort: the D-R0-02
# offset inside the ABS-measured cohort (rows with a measured height H_abs) and the pooled
# 2022-2024 offset of D-P4-04 outside it. The analysis table stores H with the one D-R0-02
# offset, so the loader moves the non-cohort rows by (noncohort - cohort) and recomputes zn,
# d and edge with R/lib/zone.R. The robustness arm is the ABS-measured cohort, P1, on H_abs
# (D-R0-02), and D-P4-04 requires it to agree in sign with the primary on the buffer and ABS
# components.

suppressPackageStartupMessages({
  library(arrow)
  library(dplyr)
  library(jsonlite)
})

## --- pre-registered constants ------------------------------------------------------------

SEASONS       <- 2022:2026
SEASON_LEVELS <- as.character(SEASONS)
PRE_SEASONS   <- c("2022", "2023", "2024")          # the pre-trend window, SOP W3.14-W3.17
REGIMES       <- c("pre_buffer", "buffer_2025", "abs_2026")
REGIME_OF     <- c("2022" = "pre_buffer", "2023" = "pre_buffer", "2024" = "pre_buffer",
                   "2025" = "buffer_2025", "2026" = "abs_2026")
CC_LEVELS     <- c("0-strike", "1-strike", "2-strike")   # annex section 2; reference 0-strike
STAND_LEVELS  <- c("L", "R")                             # reference L
PG_LEVELS     <- c("FF", "SI/FC", "BRK", "OFFSP")        # SOP W3.7's four groups
EDGE_LEVELS   <- c("side", "top", "bot")
BAND_SURF     <- 8.0      # SOP W3.5 and annex section 1: the surface fit uses |d| <= 8.0 in
BAND_SHADOW   <- 3.0      # SOP W3.5: the shadow band is 3.0 in wide on each side, a reporting region
REF_SEASON    <- "2024"   # SOP W3.14: the 2024 reference pitch mix
REF_HEIGHT_IN <- 72       # SOP W3.14: estimands for a 72-inch batter
ZN_MID        <- 0.4025   # SOP W3.14: half_width_in is read at zn = 0.4025
CENTRE_X_FT   <- 0.25     # SOP W3.14: top_in and bot_in over |x| <= 0.25 ft
XG <- round(seq(-1.5, 1.5, by = 0.01), 2)      # 301 points, SOP W3.14
ZG <- round(seq(0.15, 0.70, by = 0.002), 3)    # 276 points, SOP W3.14
NQ     <- 51L             # quantiles of the pitch-group-and-velocity shift per cell (W3.12 harness)
WIN_ZN <- 0.03            # per-draw window around a point crossing, zn units (W3.12 harness)
WIN_X  <- 0.10            # the same, ft (W3.12 harness)
L_BAND <- 2.5             # per-draw area: grid points with |logit| <= 2.5 are re-evaluated
L_RIM  <- 2.0             # a draw whose sign flips at |logit| >= 2.0 is re-evaluated on the full grid
J_MID_LO <- max(which(ZG <= ZN_MID))
J_MID_HI <- J_MID_LO + 1L
I_CENTRE <- which(abs(XG) <= CENTRE_X_FT + 1e-9)
I_ZERO   <- which(XG == 0)
N_DRAWS    <- 1000L       # SOP W3.14: 1,000 posterior coefficient draws
DRAW_SEED  <- 20260922L   # the project seed, SOP W3.18
INTERVAL_COV <- "Vc"      # annex 8.7, PREREGISTRATION.md section 8, DEV-60: Vc, not Vp
MIN_COMPLETE_SHARE <- 0.99   # a season's estimand needs 99% of its draws complete
PANEL_MIN_GAMES <- 15L    # CH1-A14 and DEV-51: >= 15 home-plate games in every season
PANEL_PREREG_N  <- 62L    # PREREGISTRATION.md section 7, at the freeze
# PREREGISTRATION.md section 7 and D-P2-01: four neutral-site games with no ABS hardware.
# They join no regime, and every Chapter 1 estimate excludes them.
NO_ABS_HARDWARE_GAMES <- c(823669L, 823745L, 825093L, 825094L)
# SOP W3.5's season table, as R/ch1/01_sample.R checks it against the Stats API: the last
# day of the first half and the first day of the second half. P2 splits each season here.
ASB <- data.frame(season = SEASONS,
                  asb_last  = c("07-17", "07-09", "07-14", "07-14", "07-14"),
                  asb_first = c("07-21", "07-14", "07-19", "07-18", "07-19"),
                  stringsAsFactors = FALSE)
# The frozen specification, annex section 2, verbatim. tests/ch1/test_ch1_sprint.R compares
# it with the annex's code block.
FROZEN_FORMULA_TEXT <- paste(
  "cs ~ season + count_class + stand + pitch_group",
  '+ te(x_mid, zn, bs = c("cr","cr"), k = c(24,24))',
  '+ te(x_mid, zn, bs = c("cr","cr"), k = c(18,18), by = season_o)',
  '+ te(x_mid, zn, bs = c("cr","cr"), k = c(12,12), by = count_class_o)',
  '+ te(x_mid, zn, bs = c("cr","cr"), k = c(12,12), by = stand_o)',
  "+ s(velo, k = 10)",
  '+ s(umpire_hp_id, bs = "re")',
  '+ s(umpire_season, bs = "re")')
# SENS-B1-UNDERSMOOTH, pre-registered in annex 8.7 (D-R0-04): W3.14 refits the surfaces with the
# season by-term at k = 24, the next rung of annex section 3's season ladder, and every other k
# as frozen. W3.15 reads the top edge off it and W3.16 reports it beside the primary, never in
# its place.
UNDERSMOOTH_SEASON_K <- 24L
UNDERSMOOTH_ESTIMANDS <- "top_in"

## --- the run harness ---------------------------------------------------------------------

.ch1 <- new.env()
.ch1$n_pass <- 0L
.ch1$failures <- character(0)
.ch1$t0 <- Sys.time()
check <- function(label, ok, detail = "") {
  if (isTRUE(ok)) {
    .ch1$n_pass <- .ch1$n_pass + 1L
    cat(sprintf("PASS    %-50s %s\n", label, detail))
  } else {
    .ch1$failures <- c(.ch1$failures, sprintf("%s -- %s", label, detail))
    cat(sprintf("FAIL    %-50s %s\n", label, detail))
  }
  invisible(isTRUE(ok))
}
record <- function(label, detail = "") cat(sprintf("RECORD  %-50s %s\n", label, detail))
elapsed_s <- function() as.numeric(difftime(Sys.time(), .ch1$t0, units = "secs"))
finish <- function(step) {
  cat(sprintf("\n%s: %d PASS, %d FAIL, %.0f s\n", step, .ch1$n_pass, length(.ch1$failures), elapsed_s()))
  if (length(.ch1$failures) > 0L) {
    cat("failures:\n", paste0("  ", .ch1$failures, "\n"), sep = "")
    quit(status = 1)
  }
  quit(status = 0)
}
die <- function(...) stop(paste0(...), call. = FALSE)
refuse <- function(step, why) {
  cat(sprintf("REFUSED %s: %s\n", step, why))
  quit(status = 4)
}
madrid_now <- function() format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z", tz = "Europe/Madrid")
ensure_dir <- function(p) dir.create(p, recursive = TRUE, showWarnings = FALSE)
write_json_file <- function(x, path) {
  ensure_dir(dirname(path))
  writeLines(toJSON(x, auto_unbox = TRUE, digits = NA, pretty = TRUE, null = "null", na = "null"), path)
}
hex <- function(h) paste(sprintf("%02x", as.integer(unclass(h))), collapse = "")
sha256_file <- function(path) hex(openssl::sha256(file(path)))
sha256_text <- function(txt) hex(openssl::sha256(charToRaw(enc2utf8(txt))))
write_csv_plain <- function(df, path) {
  ensure_dir(dirname(path))
  utils::write.csv(df, path, row.names = FALSE, na = "")
}
read_csv_plain <- function(path) utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
fmt <- function(x, d) formatC(x, format = "f", digits = d)
comma <- function(x) formatC(as.numeric(x), format = "d", big.mark = ",")

## --- command line ------------------------------------------------------------------------

# parse_cli(args, flags): "--name value" pairs, plus bare switches named in flags.
parse_cli <- function(args, flags = character(0)) {
  out <- list()
  i <- 1L
  while (i <= length(args)) {
    a <- args[i]
    if (!startsWith(a, "--")) die("unexpected argument ", a)
    key <- sub("^--", "", a)
    if (key %in% flags) {
      out[[key]] <- TRUE
      i <- i + 1L
    } else {
      if (i == length(args)) die("missing value for ", a)
      out[[key]] <- args[i + 1L]
      i <- i + 2L
    }
  }
  out
}
opt_get <- function(opt, key, default = NULL) if (is.null(opt[[key]])) default else opt[[key]]
opt_int <- function(opt, key, default) as.integer(opt_get(opt, key, default))

## --- paths and layout --------------------------------------------------------------------

ch1_root <- function() {
  r <- Sys.getenv("ABSUMP_ROOT", unset = "")
  if (nzchar(r)) return(normalizePath(r))
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  if (length(f) == 1L) return(normalizePath(file.path(dirname(f), "..", "..")))
  normalizePath(getwd())
}
if (!exists("ROOT")) ROOT <- ch1_root()

# The last open day, from absump.paths, the one place it is written (D-P3-03).
last_open_date <- function() {
  code <- "from absump.paths import LAST_OPEN_DATE; print(LAST_OPEN_DATE)"
  out <- suppressWarnings(system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python", "-c",
                                          shQuote(code)), stdout = TRUE, stderr = TRUE))
  st <- attr(out, "status")
  if (!is.null(st) && st != 0L) die("could not read absump.paths: ", paste(out, collapse = " "))
  d <- as.Date(trimws(out[length(out)]))
  if (is.na(d)) die("absump.paths printed no date: ", paste(out, collapse = " "))
  d
}

# The output tree under --out mirrors out/: ch1/{model,tab,log,fig}, tables/, models/<fit>/.
out_paths <- function(out) {
  list(root = out, model = file.path(out, "ch1", "model"), tab = file.path(out, "ch1", "tab"),
       log = file.path(out, "ch1", "log"), fig = file.path(out, "ch1", "fig"),
       tables = file.path(out, "tables"), models = file.path(out, "models"))
}

## --- GD-12, the synthetic marker, and the start of every run --------------------------------

prereg_tag <- function() {
  l <- grep("^prereg_tag:", readLines(file.path(ROOT, "config", "seal.yml")), value = TRUE)
  if (length(l) != 1L) die("config/seal.yml names no prereg_tag")
  gsub('[" ]', "", sub("#.*$", "", sub("^prereg_tag:", "", l)))
}
git_out <- function(args) {
  out <- suppressWarnings(system2("git", c("-C", shQuote(ROOT), args), stdout = TRUE, stderr = TRUE))
  st <- attr(out, "status")
  list(status = if (is.null(st)) 0L else as.integer(st), out = out)
}
git_head <- function() {
  h <- git_out(c("rev-parse", "HEAD"))
  if (h$status != 0L) NA_character_ else h$out[1]
}

# GD-12: `git merge-base --is-ancestor <tag> HEAD` must exit 0.
gd12_ancestry <- function() {
  tag <- prereg_tag()
  a <- git_out(c("merge-base", "--is-ancestor", tag, "HEAD"))
  list(ok = a$status == 0L, tag = tag, head = git_head(),
       detail = sprintf("git merge-base --is-ancestor %s HEAD exited %d at HEAD %s", tag, a$status,
                        substr(git_head(), 1, 12)))
}

table_is_synthetic <- function(path) {
  ds <- arrow::open_dataset(path)
  if (!"is_synthetic" %in% names(ds$schema)) return(FALSE)
  v <- ds |> distinct(is_synthetic) |> collect()
  if (!identical(sort(unique(v$is_synthetic)), TRUE)) die("is_synthetic is not TRUE on every row of ", path)
  TRUE
}

inside <- function(path, dir) {
  p <- normalizePath(path, mustWork = FALSE)
  d <- normalizePath(dir, mustWork = FALSE)
  identical(p, d) || startsWith(paste0(p, "/"), paste0(d, "/"))
}

FIT_CODE <- c("R/lib/ch1_fits.R", "R/lib/ch1_estimands.R", "R/lib/ch1_decomp.R", "R/lib/ch1_hetero.R",
              "R/lib/zone.R")

# The analysis table W3.7 writes, from absump.paths.mart(), the one place its path is written.
mart_table <- function() {
  code <- "from absump.paths import mart; print(mart('ch1_called'))"
  out <- suppressWarnings(system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python", "-c",
                                          shQuote(code)), stdout = TRUE, stderr = TRUE))
  trimws(out[length(out)])
}

# Called by every entry point before it reads a row. Returns the run context. With no --table and
# no --out a script runs on the real analysis table into the repository's out/, as the fleet's
# commands call it; the GD-12 guard below then decides whether it may.
start_run <- function(step, opt, script) {
  table <- opt_get(opt, "table", mart_table())
  out <- opt_get(opt, "out", file.path(ROOT, "out"))
  if (!file.exists(table)) die(step, ": no analysis table at ", table)
  syn <- table_is_synthetic(table)
  if (syn) {
    if (inside(out, ROOT)) {
      refuse(step, sprintf("a synthetic run writes outside the repository; %s is inside %s", out, ROOT))
    }
    record("mode", sprintf("SYNTHETIC table %s; GD-12 not required", table))
    gd <- list(ok = NA, detail = "synthetic table, GD-12 not applied")
  } else {
    for (k in c("draws", "stan-chains", "stan-warmup", "stan-sampling", "b2-fits")) {
      if (!is.null(opt[[k]])) refuse(step, sprintf("--%s is a dry-run setting; real data runs the pre-registered value", k))
    }
    gd <- gd12_ancestry()
    if (!isTRUE(gd$ok)) refuse(step, sprintf("real data, and GD-12 ancestry failed (%s)", gd$detail))
    dirty <- git_out(c("status", "--porcelain", "--", "R/ch1", "R/lib", "tools/comms"))$out
    if (length(dirty) > 0L) {
      refuse(step, sprintf("real data, and the fit code is not committed, so git_sha would not name it: %s",
                           paste(dirty, collapse = "; ")))
    }
    record("mode", sprintf("REAL table %s; GD-12 %s", table, gd$detail))
  }
  ctx <- list(step = step, table = normalizePath(table), out = out, paths = out_paths(out),
              synthetic = syn, gd12 = gd, last_open = last_open_date(), script = script,
              code_shas = code_hashes(script),
              n_draws = if (syn) opt_int(opt, "draws", N_DRAWS) else N_DRAWS)
  record("last open day", format(ctx$last_open))
  record("draws", sprintf("%d from N(beta, %s)", ctx$n_draws, INTERVAL_COV))
  ctx
}

## --- the one loader ---------------------------------------------------------------------------

TABLE_COLS <- c("pitch_uid", "game_pk", "official_date", "season", "regime", "analysis_set",
                "umpire_hp_id", "umpire_season", "stand", "balls", "strikes", "count_class",
                "pitch_group", "pitch_type", "velo", "x_mid", "z_mid", "H", "zn", "d", "edge", "cs",
                "H_abs", "d_abs")

# The open rows of the analysis table, on or before the last open day, filtered inside the
# arrow scan so that no later row reaches R. The four games without ABS hardware are dropped.
load_table <- function(ctx, seasons = SEASONS, extra = character(0)) {
  ds <- arrow::open_dataset(ctx$table)
  have <- names(ds$schema)
  want <- unique(c(TABLE_COLS, intersect(extra, have), if ("is_synthetic" %in% have) "is_synthetic"))
  miss <- setdiff(TABLE_COLS, have)
  if (length(miss) > 0L) die("the analysis table lacks ", paste(miss, collapse = ", "))
  lo <- ctx$last_open
  seas <- as.integer(seasons)
  df <- ds |>
    filter(official_date <= !!lo, analysis_set == "open", season %in% !!seas) |>
    select(all_of(want)) |> collect() |> as.data.frame()
  bad <- c(
    if (nrow(df) == 0L) "no rows",
    if (nrow(df) > 0L && max(df$official_date) > lo) "a row after the last open day",
    if (!all(as.character(df$analysis_set) == "open")) "an analysis set other than open",
    if (!all(df$season %in% seas)) "a season outside the request",
    if (!all(as.character(df$regime) == REGIME_OF[as.character(df$season)])) "a regime that does not match its season")
  if (length(bad) > 0L) die("the loader refused the table: ", paste(bad, collapse = "; "))
  drop <- df$game_pk %in% NO_ABS_HARDWARE_GAMES
  record("no-ABS-hardware games dropped", sprintf("%d rows from %d games (PREREGISTRATION.md section 7)",
                                                  sum(drop), length(unique(df$game_pk[drop]))))
  df <- df[!drop, , drop = FALSE]
  df <- df[order(df$pitch_uid), , drop = FALSE]
  rownames(df) <- NULL
  for (v in c("stand", "count_class", "pitch_group", "edge", "regime", "analysis_set", "umpire_season")) {
    df[[v]] <- as.character(df[[v]])
  }
  df$season <- as.integer(df$season)
  df$umpire_hp_id <- as.integer(df$umpire_hp_id)
  record("rows loaded", sprintf("%s rows, %s games, seasons %s, last day %s", comma(nrow(df)),
                                comma(length(unique(df$game_pk))), paste(sort(unique(df$season)), collapse = " "),
                                format(max(df$official_date))))
  df
}

## --- the height rule --------------------------------------------------------------------------

# The table's one offset o, from its W3.7 metadata: "H = h_roster_in + o, o = <o> in".
table_offset <- function(path) {
  md <- arrow::open_dataset(path)$schema$metadata
  s <- md[["w37_height"]]
  if (is.null(s)) return(NA_real_)
  m <- regmatches(s, regexec("o = ([-+0-9.eE]+) in", s))[[1]]
  if (length(m) < 2L) NA_real_ else as.numeric(m[2])
}

# The offsets file. D-R0-02's offset_in is the cohort offset; D-P4-04's offset_noncohort_in
# is written by W3.4's lane (R/ch1/03_heights.R). Default: data/interim/dim_batter_season/
# calibration.json for a real table, <table stem>.calibration.json for a synthetic one.
read_calibration <- function(ctx, opt) {
  p <- opt_get(opt, "calibration")
  if (is.null(p)) {
    p <- if (ctx$synthetic) sub("\\.parquet$", ".calibration.json", ctx$table)
         else file.path(ROOT, "data", "interim", "dim_batter_season", "calibration.json")
  }
  if (!file.exists(p)) die("no height calibration at ", p)
  cal <- fromJSON(p)
  cal$path <- normalizePath(p)
  cal
}

# rule "primary": roster + cohort-specific offset on every P0 row (D-R0-02, D-P4-04).
# rule "abs":     the ABS-measured cohort P1 on H_abs (the D-R0-02 robustness arm).
# allow_single:   the owner's override of D-P4-04 (--height-rule single-offset); recorded.
apply_heights <- function(df, rule, cal, ctx, allow_single = FALSE) {
  o_tab <- table_offset(ctx$table)
  in_cohort <- !is.na(df$H_abs)
  if (rule == "abs") {
    df <- df[in_cohort, , drop = FALSE]
    H1 <- df$H_abs
    d1 <- signed_edge_in(df$x_mid, df$z_mid, abs_top_ft(H1), abs_bot_ft(H1))
    check("P1 d_abs reproduced from H_abs", max(abs(d1 - df$d_abs)) < 1e-9,
          sprintf("max |d - d_abs| %.2e in over %s rows", max(abs(d1 - df$d_abs)), comma(nrow(df))))
    rule_text <- "ABS-measured cohort P1, H = H_abs (D-R0-02 robustness arm)"
  } else {
    if (!is.finite(o_tab) || abs(o_tab - cal$offset_in) > 1e-9) {
      die(sprintf("the table's offset (%s) is not the calibration's cohort offset %.12f", format(o_tab), cal$offset_in))
    }
    H1 <- df$H
    o_nc <- cal$offset_noncohort_in
    if (!is.null(o_nc) && is.finite(o_nc)) {
      H1[!in_cohort] <- df$H[!in_cohort] - cal$offset_in + o_nc
      rule_text <- sprintf("roster + offset: %.4f in inside the ABS-measured cohort, %.4f in outside it (D-R0-02, D-P4-04)",
                           cal$offset_in, o_nc)
    } else if (allow_single) {
      rule_text <- sprintf("roster + the one D-R0-02 offset %.4f in; D-P4-04 NOT applied (owner override, DEV-48)",
                           cal$offset_in)
    } else {
      die("D-P4-04's non-cohort offset (offset_noncohort_in) is not in ", cal$path,
          ". W3.4's lane writes it. Pass --height-rule single-offset only on the owner's override of D-P4-04.")
    }
    d1 <- signed_edge_in(df$x_mid, df$z_mid, abs_top_ft(H1), abs_bot_ft(H1))
    dev_c <- if (any(in_cohort)) max(abs(d1[in_cohort] - df$d[in_cohort])) else 0
    check("cohort rows reproduce the table's d", dev_c < 1e-9, sprintf("max |d - table d| %.2e in", dev_c))
  }
  df$H <- H1
  df$zn <- z_norm(df$z_mid, H1)
  df$d <- d1
  df$edge <- nearest_edge(df$x_mid, df$z_mid, abs_top_ft(H1), abs_bot_ft(H1))
  attr(df, "height_rule") <- rule_text
  record(sprintf("height rule %s", rule), sprintf("%s; %s rows, %s in the cohort", rule_text,
                                                 comma(nrow(df)), comma(sum(!is.na(df$H_abs)))))
  df
}

## --- samples ------------------------------------------------------------------------------------

# The surface sample: |d| <= 8.0 in on the rule's own ball-centre d (annex section 1). D-P4-09
# keeps the 8 in filter on the ball-centre d.
surface_rows <- function(df) df[abs(df$d) <= BAND_SURF, , drop = FALSE]

# Two shadow bands, each where the pre-registration puts it.
#   shadow_band()  the W3.15 shadow_rate estimand, and so P1: |d - 1.45| <= 3.0 in, the signed
#                  edge distance with the ball radius taken off, on the harmonised zone. D-P4-09
#                  (DEV-49) moved the band there and named it the band of the pre-registered
#                  shadow rate.
#   b1_band()      W3.18 B1: |d| <= 3.0 in on the ball-centre d. Annex 8.1 builds the D-60 design
#                  on it, and annex 8.2 applies CH1-A6's thresholds to that estimator.
shadow_band <- function(d) abs(d - BALL_R_IN) <= BAND_SHADOW
b1_band <- function(d) abs(d) <= BAND_SHADOW

# CH1-A14's balanced panel: umpires with >= 15 home-plate games in every season 2022-2026,
# counted as distinct games among the loaded P0 rows (DEV-51, D-P4-12).
panel_umpires <- function(df) {
  g <- unique(df[, c("umpire_hp_id", "season", "game_pk")])
  n <- table(factor(g$umpire_hp_id), factor(g$season, levels = SEASONS))
  sort(as.integer(rownames(n)[apply(n >= PANEL_MIN_GAMES, 1, all)]))
}

# Game index within umpire-season, in date order, for the B3 odd/even split (SOP W3.18).
game_halves <- function(df) {
  g <- unique(df[, c("umpire_hp_id", "season", "official_date", "game_pk")])
  g <- g[order(g$umpire_hp_id, g$season, g$official_date, g$game_pk), ]
  g$game_index <- stats::ave(seq_len(nrow(g)), g$umpire_hp_id, g$season, FUN = seq_along)
  k <- match(paste(df$umpire_hp_id, df$season, df$game_pk), paste(g$umpire_hp_id, g$season, g$game_pk))
  ifelse(g$game_index[k] %% 2L == 1L, "odd", "even")
}

# The half-season of each row for P2: first half on or before the All-Star break's last day.
season_half <- function(df) {
  last <- as.Date(paste0(df$season, "-", ASB$asb_last[match(df$season, ASB$season)]))
  first <- as.Date(paste0(df$season, "-", ASB$asb_first[match(df$season, ASB$season)]))
  h <- ifelse(df$official_date <= last, "first", ifelse(df$official_date >= first, "second", NA_character_))
  h
}

## --- provenance, the SOP section 1.4 contract --------------------------------------------------

code_hashes <- function(script) {
  files <- unique(c(script, FIT_CODE))
  vapply(files, function(f) sha256_file(file.path(ROOT, f)), "")
}

provenance <- function(ctx, name, rows, seed, model_dir, extra = list()) {
  shas <- ctx$code_shas
  c(list(step = ctx$step, fit = name, model_dir = normalizePath(model_dir, mustWork = FALSE),
         n_games = length(unique(rows$game_pk)), n_rows = nrow(rows),
         min_official_date = format(min(rows$official_date)),
         max_official_date = format(max(rows$official_date)),
         game_pk_sha256 = sha256_text(paste(sort(unique(rows$game_pk)), collapse = "\n")),
         analysis_sets_touched = as.list(sort(unique(as.character(rows$analysis_set)))),
         seed = seed,
         code_sha256 = sha256_text(paste(shas, collapse = "\n")),
         code_files = as.list(shas),
         git_sha = git_head(),
         prereg_tag = prereg_tag(),
         gd12 = ctx$gd12$detail,
         synthetic = ctx$synthetic,
         table = ctx$table,
         table_sha256 = sha256_file(ctx$table),
         r_version = R.version.string,
         mgcv = as.character(utils::packageVersion("mgcv")),
         written_madrid = madrid_now()),
    extra)
}

# A directory lock for the files several processes rewrite: the receipt union and T3.
with_lock <- function(dir, expr) {
  ensure_dir(dir)
  lock <- file.path(dir, ".ch1.lock")
  got <- FALSE
  for (i in 1:1200) if (dir.create(lock, showWarnings = FALSE)) { got <- TRUE; break } else Sys.sleep(0.5)
  if (!got) die("could not take the lock ", lock, " in 10 minutes")
  on.exit(unlink(lock, recursive = TRUE), add = TRUE)
  force(expr)
}

# ops/check_seal_order.sh (GD-12) reads one git_sha per receipt and needs a commit. The union's
# git_sha is the earliest of its fits' commits: every other one descends from it, so it descends
# from prereg-v1 exactly when they all do. Fits on diverged commits are refused.
earliest_sha <- function(shas) {
  shas <- unique(shas)
  if (length(shas) == 1L) return(shas)
  for (s in shas) {
    later <- setdiff(shas, s)
    if (all(vapply(later, function(o) git_out(c("merge-base", "--is-ancestor", s, o))$status == 0L, TRUE))) return(s)
  }
  die("the fits of one model directory ran on diverged commits: ", paste(shas, collapse = ", "))
}

# One receipt per fit under models/<fit>/, and the union of every fit receipt of that model
# directory beside the fitted objects (GD-01 reads p.parent / provenance.json). The union is
# rewritten under a lock, so W3.14's fits may run as separate processes.
write_receipt <- function(ctx, prov, model_dir) {
  write_json_file(prov, file.path(ctx$paths$models, prov$fit, "provenance.json"))
  with_lock(model_dir, {
    fits <- list.files(ctx$paths$models, pattern = "^provenance\\.json$", recursive = TRUE, full.names = TRUE)
    recs <- lapply(fits, fromJSON, simplifyVector = FALSE)
    recs <- Filter(function(r) identical(r$model_dir, prov$model_dir), recs)
    recs <- recs[order(vapply(recs, function(r) r$fit, ""))]
    keyf <- function(k) unique(unlist(lapply(recs, function(r) r[[k]])))
    shas <- vapply(recs, function(r) r$git_sha, "")
    # Every fit here uses a subset of the P0 rows, so the largest fit's games are the union's
    # games. The union's hash is the hash of the fits' own hashes, in fit order.
    union <- list(what = paste("union of the fit receipts of this directory; one receipt per fit under",
                               "models/<fit>/; n_games is the largest fit's count, game_pk_sha256 hashes",
                               "the fits' own hashes in fit order; git_sha is the earliest fit commit"),
                  n_games = max(vapply(recs, function(r) r$n_games, 0)),
                  n_rows = sum(vapply(recs, function(r) r$n_rows, 0)),
                  min_official_date = min(keyf("min_official_date")), max_official_date = max(keyf("max_official_date")),
                  game_pk_sha256 = sha256_text(paste(vapply(recs, function(r) r$game_pk_sha256, ""), collapse = "\n")),
                  analysis_sets_touched = as.list(sort(keyf("analysis_sets_touched"))),
                  seed = paste(unique(vapply(recs, function(r) if (is.null(r$seed)) "none" else as.character(r$seed), "")),
                               collapse = ";"),
                  code_sha256 = paste(unique(vapply(recs, function(r) r$code_sha256, "")), collapse = ";"),
                  git_sha = earliest_sha(shas), git_shas = as.list(unique(shas)),
                  synthetic = all(vapply(recs, function(r) isTRUE(r$synthetic), TRUE)),
                  fits = recs)
    write_json_file(union, file.path(model_dir, "provenance.json"))
    invisible(union)
  })
}

# The run receipt every entry point writes, models/ch1_<step>/provenance.json: the SOP section
# 1.4 keys over the rows the step read (none for a step that reads only CSVs), the files it read
# and wrote with their sha256, and the git_sha GD-12 checks.
out_rel <- function(ctx, f) {
  f <- normalizePath(f, mustWork = FALSE)
  o <- normalizePath(ctx$out, mustWork = FALSE)
  r <- normalizePath(ROOT)
  if (startsWith(f, paste0(o, "/"))) return(paste0("out/", substring(f, nchar(o) + 2L)))
  if (startsWith(f, paste0(r, "/"))) return(substring(f, nchar(r) + 2L))
  f
}
step_receipt <- function(ctx, rows = NULL, inputs = character(0), outputs = character(0), seed = NA, extra = list(),
                         suffix = "") {
  name <- paste0("ch1_", gsub(".", "_", ctx$step, fixed = TRUE), if (nzchar(suffix)) paste0("_", suffix) else "")
  files <- function(v) {
    v <- v[file.exists(v)]
    stats::setNames(as.list(vapply(v, sha256_file, "")), vapply(v, function(f) out_rel(ctx, f), ""))
  }
  base <- if (is.null(rows) || nrow(rows) == 0L) {
    list(n_games = 0L, n_rows = 0L, min_official_date = NA, max_official_date = NA,
         game_pk_sha256 = sha256_text(""), analysis_sets_touched = list())
  } else {
    list(n_games = length(unique(rows$game_pk)), n_rows = nrow(rows),
         min_official_date = format(min(rows$official_date)), max_official_date = format(max(rows$official_date)),
         game_pk_sha256 = sha256_text(paste(sort(unique(rows$game_pk)), collapse = "\n")),
         analysis_sets_touched = as.list(sort(unique(as.character(rows$analysis_set)))))
  }
  rec <- c(list(step = ctx$step, what = "run receipt of one Chapter 1 entry point"), base,
           list(seed = seed, code_sha256 = sha256_text(paste(ctx$code_shas, collapse = "\n")),
                code_files = as.list(ctx$code_shas), git_sha = git_head(), prereg_tag = prereg_tag(),
                gd12 = ctx$gd12$detail, synthetic = ctx$synthetic, table = ctx$table,
                inputs = files(inputs), outputs = files(outputs), r_version = R.version.string,
                written_madrid = madrid_now()), extra)
  f <- file.path(ctx$paths$models, name, "provenance.json")
  write_json_file(rec, f)
  record("run receipt", out_rel(ctx, f))
  invisible(rec)
}

## --- small statistics ------------------------------------------------------------------------------

qint <- function(v, lev = 0.95) {
  v <- v[is.finite(v)]
  if (length(v) == 0L) return(c(NA_real_, NA_real_))
  a <- (1 - lev) / 2
  unname(stats::quantile(v, c(a, 1 - a), names = FALSE, type = 7))
}

## --- the rest of the library -----------------------------------------------------------------------
source(file.path(ROOT, "R", "lib", "zone.R"))
source(file.path(ROOT, "R", "lib", "ch1_estimands.R"))
source(file.path(ROOT, "R", "lib", "ch1_decomp.R"))
source(file.path(ROOT, "R", "lib", "ch1_hetero.R"))
