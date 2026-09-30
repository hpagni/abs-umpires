#!/usr/bin/env Rscript
# R/ch1/50_sensitivity.R - SOP W3.22, the Chapter 1 sensitivity grid (the multiverse CH1-A9 reads).
#
#   Rscript R/ch1/50_sensitivity.R --list
#   Rscript R/ch1/50_sensitivity.R --cells <id[,id...]> --estimator binned|bam [--force]
#   Rscript R/ch1/50_sensitivity.R --select-bam
#   Rscript R/ch1/50_sensitivity.R --summarise
#   every mode takes --table <parquet> and --out <root> as the other Chapter 1 scripts do
#   (the real analysis table and the repository's out/ by default). ops/run_sensitivity_grid.sh
#   drives the whole grid, one cell per process.
#
# THE STEP, SOP W3.22 verbatim: "One factor at a time from the pre-registered primary, using the
# binned-logistic estimator for the full grid and re-fitting `bam` for the four configurations
# that move the headline most: `r` in {0, 1.0, 1.45, fitted}; height source in {ABS-measured
# cohort, roster+offset, per-batter ML offset}; shadow band in {2, 3, 4} in; band restriction in
# {6, 8, unrestricted} in; plane in {mid, front}; `blocked_ball` in/out; position-player pitchers
# in/out; postseason in/out; `k` at 0.75x and 1.5x; standardisation mix in {2024, 2025,
# unweighted}." Acceptance is CH1-A9 as D-59 revised it: the sign of Delta_ABS and the sign of
# Delta_buffer are each stable across the whole multiverse; share_ABS is reported only where the
# 95% interval on Delta_ABS + Delta_buffer excludes zero. The IQR criterion is withdrawn.
#
# THE PRIMARY. The pre-registered primary of every other Chapter 1 step: P0 (called_strike, ball
# and blocked_ball; game_type R; position players removed), the D-P4-04 height rule, the
# mid-plate pair, |d| <= 8.0 in, r = 1.45 in, the shadow-rate band |d - r| <= 3.0 in (D-P4-09),
# the frozen k, the 2024 reference mix, 1,000 draws, seed 20260922. Each cell changes one factor.
# A cell whose value is the primary's is the primary: it is computed once and written under its
# own id with same_as_primary TRUE, so every SOP cell has its row.
#
# WHAT EACH FACTOR CHANGES, and the reading this script gives the SOP's words.
#   r                    the ball radius of D-14's radius-adjusted edge distance d - r. In this
#                        chapter it enters only the shadow-rate band |d - r| <= w: the edges
#                        and the area are the 50% contour of the called zone and do not contain
#                        r. "fitted" is D-14's maximum-likelihood r on the 2026 challenges of
#                        the open window: a 0.01-in grid over [0, 2] in, the r under which the
#                        most challenges satisfy overturned == XOR(original strike, d_abs - r
#                        < 0), the midpoint of the widest maximal run, which is also reported.
#   height source        "roster+offset" is the primary rule (D-R0-02, D-P4-04). "ABS-measured
#                        cohort" is the ABS-measured arm, P1 on H_abs. "per-batter ML offset":
#                        the SOP defines no estimator, so this script fits one and says so (an
#                        owner item): each batter's height offset delta_b maximises the binomial
#                        likelihood of his 2022-2024 top- and bottom-edge calls (nearest edge top
#                        or bottom, |x_mid| <= 8.5 in, |d| <= 8 in) under a pooled 2022-2024 link
#                        per edge, glm(cs ~ ns(d, 6)), on a 0.05-in grid over [-4, 4] in; a batter
#                        with fewer than ML_MIN_N such pitches within |d| <= 3 in, or whose
#                        maximum sits on the grid's bound, keeps the primary rule. H = primary H
#                        + delta_b in every season. 2022-2024 only, so no offset absorbs a
#                        regime change.
#   shadow band          w in |d - r| <= w, the shadow-rate band of D-P4-09; it moves only
#                        shadow_rate.
#   band restriction     the rows the estimator is fitted on: |d| <= 6, |d| <= 8 (primary), or
#                        every P0 row. The binned logistic bins over [-B, B] for B = 6 and 8;
#                        unrestricted keeps [-8, 8] and its two end bins are open-ended, so no
#                        row is dropped and the crossings, read within 3 in of the edge, are read
#                        on the same bins as the primary.
#   plane                mid (primary) or front: d, zn and the nearest edge recomputed on the
#                        front-of-plate pair from the warehouse's open view (2022-2025 as
#                        published, 2026 re-projected by W2.x), on the primary height.
#   blocked_ball         in (primary, P0 carries it) or out: rows whose description is
#                        blocked_ball, from the open view, are dropped.
#   position-player      out (primary) or in: the open view's called pitches that P0 removed as
#     pitchers           position players' (W3.5, D-P4-08) are added back, each on the height
#                        P0 gives that batter in that season.
#   postseason           out (primary) or in: 2022-2025 postseason called pitches from the open
#                        view. When the open view holds none, the cell is written with status
#                        "deferred" and the reason, and it runs on the next pass that finds rows.
#   k                    0.75x and 1.5x. For bam every k of the frozen formula is scaled and
#                        rounded (24, 18, 12, 10 become 18, 14, 9, 8 and 36, 27, 18, 15). The
#                        binned logistic has no basis dimension; its resolution is its bin
#                        count, so k x f is f times the bins over the same band (bin width
#                        0.5 / f in).
#   standardisation mix  the reference sample of the g-computation: the 2024 pitches (primary),
#                        the 2025 pitches, or "unweighted", the six count-class x handedness
#                        cells weighted equally (bam keeps each cell's 2024 pitch-group-and-
#                        velocity quantiles). shadow_rate is averaged over the same cells.
#
# THE ESTIMATORS. binned: the annex section 5 binned logistic of R/lib/ch1_decomp.R, run through
# the library's own aggregate_bins(), fit_binned(), binned_estimands() and binned_draws() with the
# band and bin width set per cell, plus this script's shadow_rate on the same glm fits and draws.
# The binned primary must reproduce W3.16's CH1-A5 binned arm (T4_decomposition_arms.csv) to
# 1e-6 on every geometric component. bam: the frozen specification refitted on the cell's rows
# (R/lib/ch1_estimands.R), 1,000 draws from N(beta, Vc), seed 20260922, estimands by the W3.15
# code. The bam primary is W3.15's main fit, read from its draws, never refitted; a selected cell
# whose configuration W3.14 already fitted (the ABS-measured arm) is read from that fit's draws
# when its receipt names this table. The four bam cells are the four non-primary cells whose
# binned area components move furthest from the binned primary: max(|dDelta_buffer|,
# |dDelta_ABS|) in square inches, ties by grid order.
#
# THE GRID FILE, out/ch1/tab/sensitivity_grid.csv: one row per cell and estimator. The headline
# columns are area_sqin's decomposition (delta_buffer, delta_abs, delta_total, g, the sum, and
# share_abs where CH1-A9 licenses it); each of top_in, bot_in, half_width_in and shadow_rate has
# its delta_buffer and delta_abs with 95% intervals. Every row carries factor, value, estimator,
# n_rows, n_draws, seed, the table and code hashes. The primary is the row with cell_id "primary"
# (is_primary TRUE), one per estimator. --summarise adds the sign and interval comparisons with
# the primary, writes out/tables/T8_sensitivity_data.csv (long form, one row per cell, estimator,
# estimand and component) and prints the CH1-A9 verdict.
#
# GUARDS. start_run() before any row is read (GD-12, the seal, the synthetic marker). Rows come
# from the analysis table's open rows and from the warehouse's open view only, each query with
# analysis_set = 'open' and official_date on or before the last open day. No fitted object is
# written: the bam cells keep their fits in memory. Exit 0 done, 1 a check failed, 4 refused.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

STEP <- "W3.22"
SCRIPT <- "R/ch1/50_sensitivity.R"
HEADLINE <- "area_sqin"
GRID_ESTIMANDS <- c("top_in", "bot_in", "half_width_in", "area_sqin", "shadow_rate")
SIDE_ESTIMANDS <- setdiff(GRID_ESTIMANDS, HEADLINE)
N_BAM_REFITS <- 4L
BAM_HEAVY_ROWS <- 1.3      # a bam cell with more rows than 1.3 x the primary's runs alone
ML_MIN_N <- 150L           # per-batter ML offset: pitches within |d| <= 3 in on top and bottom
ML_MIN_N_SYNTHETIC <- 20L  # the tiny synthetic table of a dry run has about 130 pitches a batter
ML_GRID <- seq(-4, 4, by = 0.05)
ML_U <- seq(-12.5, 12.5, by = 0.01)
R_GRID <- seq(0, 2, by = 0.01)
POSTSEASON_TYPES <- c("F", "D", "L", "W")
PITCH_GROUP_MAP <- c(      # W3.7's 17-code map, R/ch1/10_build_analysis_table.R
  FF = "FF", FA = "FF",
  SI = "SI/FC", FC = "SI/FC",
  SL = "BRK", ST = "BRK", SV = "BRK", CU = "BRK", KC = "BRK", CS = "BRK",
  CH = "OFFSP", FS = "OFFSP", FO = "OFFSP", SC = "OFFSP", KN = "OFFSP", EP = "OFFSP",
  UN = "OFFSP")

## --- the cells ---------------------------------------------------------------------------------

PRIMARY_CFG <- list(height = "primary", r = BALL_R_IN, r_fitted = FALSE, shadow_w = BAND_SHADOW, band = BAND_SURF,
                    plane = "mid", blocked_ball = TRUE, pp = FALSE, postseason = FALSE, k_scale = 1, mix = "2024")

# factor, SOP value (verbatim), cell id, and the change to the primary configuration.
cell_table <- function() {
  L <- list(
    list("r", "0", "r_0", list(r = 0)),
    list("r", "1.0", "r_1.0", list(r = 1.0)),
    list("r", "1.45", "r_1.45", list()),
    list("r", "fitted", "r_fitted", list(r_fitted = TRUE)),
    list("height source", "ABS-measured cohort", "height_abs_cohort", list(height = "abs_cohort")),
    list("height source", "roster+offset", "height_roster_offset", list()),
    list("height source", "per-batter ML offset", "height_ml_offset", list(height = "ml_offset")),
    list("shadow band", "2", "shadow_2", list(shadow_w = 2)),
    list("shadow band", "3", "shadow_3", list()),
    list("shadow band", "4", "shadow_4", list(shadow_w = 4)),
    list("band restriction", "6", "band_6", list(band = 6)),
    list("band restriction", "8", "band_8", list()),
    list("band restriction", "unrestricted", "band_unrestricted", list(band = Inf)),
    list("plane", "mid", "plane_mid", list()),
    list("plane", "front", "plane_front", list(plane = "front")),
    list("blocked_ball", "in", "blocked_ball_in", list()),
    list("blocked_ball", "out", "blocked_ball_out", list(blocked_ball = FALSE)),
    list("position-player pitchers", "in", "pp_in", list(pp = TRUE)),
    list("position-player pitchers", "out", "pp_out", list()),
    list("postseason", "in", "postseason_in", list(postseason = TRUE)),
    list("postseason", "out", "postseason_out", list()),
    list("k", "0.75x", "k_0.75x", list(k_scale = 0.75)),
    list("k", "1.5x", "k_1.5x", list(k_scale = 1.5)),
    list("standardisation mix", "2024", "mix_2024", list()),
    list("standardisation mix", "2025", "mix_2025", list(mix = "2025")),
    list("standardisation mix", "unweighted", "mix_unweighted", list(mix = "unweighted")))
  data.frame(factor = vapply(L, `[[`, "", 1L), value = vapply(L, `[[`, "", 2L), cell_id = vapply(L, `[[`, "", 3L),
             same_as_primary = vapply(L, function(x) length(x[[4]]) == 0L, TRUE), stringsAsFactors = FALSE)
}
CELLS <- cell_table()
CELL_CHANGE <- local({
  L <- list(r_0 = list(r = 0), `r_1.0` = list(r = 1.0), r_fitted = list(r_fitted = TRUE),
            height_abs_cohort = list(height = "abs_cohort"), height_ml_offset = list(height = "ml_offset"),
            shadow_2 = list(shadow_w = 2), shadow_4 = list(shadow_w = 4), band_6 = list(band = 6),
            band_unrestricted = list(band = Inf), plane_front = list(plane = "front"),
            blocked_ball_out = list(blocked_ball = FALSE), pp_in = list(pp = TRUE), postseason_in = list(postseason = TRUE),
            `k_0.75x` = list(k_scale = 0.75), `k_1.5x` = list(k_scale = 1.5), mix_2025 = list(mix = "2025"),
            mix_unweighted = list(mix = "unweighted"))
  L
})
cell_cfg <- function(id) {
  cfg <- PRIMARY_CFG
  if (identical(id, "primary")) return(cfg)
  if (!id %in% CELLS$cell_id) die("unknown cell ", id)
  ch <- CELL_CHANGE[[id]]
  if (is.null(ch)) return(cfg)
  for (k in names(ch)) cfg[[k]] <- ch[[k]]
  cfg
}
cfg_text <- function(cfg) {
  paste(sprintf("height=%s; r=%s; shadow_w=%g; band=%s; plane=%s; blocked_ball=%s; pp=%s; postseason=%s; k=%gx; mix=%s",
                cfg$height, if (isTRUE(cfg$r_fitted)) "fitted" else format(cfg$r), cfg$shadow_w,
                if (is.finite(cfg$band)) format(cfg$band) else "unrestricted", cfg$plane,
                if (cfg$blocked_ball) "in" else "out", if (cfg$pp) "in" else "out", if (cfg$postseason) "in" else "out",
                cfg$k_scale, cfg$mix))
}
# Cells a process computes: the primary plus every cell whose configuration differs from it.
RUN_CELLS <- c("primary", CELLS$cell_id[!CELLS$same_as_primary])

## --- the warehouse's open view -----------------------------------------------------------------

duckdb_file <- function() {
  code <- "from absump.paths import DUCKDB_PATH; print(DUCKDB_PATH)"
  out <- suppressWarnings(system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python", "-c", shQuote(code)),
                                  stdout = TRUE, stderr = TRUE))
  trimws(out[length(out)])
}
# A read-only attach, retried for up to 15 minutes: a dbt build of fleet phase 07 holds the
# warehouse's write lock while it runs.
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

# Per-pitch columns of P0's rows from the open view: description and the front-plane pair.
view_columns <- function(ctx, rows) {
  if (ctx$synthetic) {
    if (!all(c("x_front", "z_front") %in% names(rows))) die("the synthetic table carries no front pair")
    return(data.frame(pitch_uid = rows$pitch_uid, description = NA_character_, x_front = rows$x_front,
                      z_front = rows$z_front, stringsAsFactors = FALSE))
  }
  v <- wh_query(ctx, "
    SELECT c.pitch_uid, c.description, c.plate_x_front AS x_front, c.plate_z_front AS z_front
    FROM abs.main_marts.v_called_pitch_open AS c
    WHERE c.level = 'mlb' AND c.game_type = 'R' AND c.analysis_set = 'open'
      AND c.official_date <= CAST(? AS DATE)")
  k <- match(rows$pitch_uid, v$pitch_uid)
  check("open view: every P0 pitch found by pitch_uid", !anyNA(k),
        sprintf("%s of %s P0 pitches in %s view rows", comma(sum(!is.na(k))), comma(nrow(rows)), comma(nrow(v))))
  v[k, , drop = FALSE]
}

# Called pitches of the open view that P0 does not carry, built into the analysis table's
# columns: the position players' pitches (game_type R) or the postseason's. Each batter takes the
# height P0 gives him in that season (H = roster + the table's offset, H_abs inside the cohort),
# so apply_heights() treats the rows as it treats P0's.
extra_rows <- function(ctx, base, game_types) {
  gt <- paste(sprintf("'%s'", game_types), collapse = ", ")
  v <- wh_query(ctx, sprintf("
    SELECT c.pitch_uid, CAST(c.game_pk AS INTEGER) AS game_pk, c.official_date, c.season, c.regime, c.analysis_set,
           c.umpire_hp_id, c.umpire_season, CAST(c.batter AS INTEGER) AS batter, CAST(c.pitcher AS INTEGER) AS pitcher,
           c.stand, c.balls, c.strikes, c.pitch_type, c.release_speed AS velo, c.plate_x_mid, c.plate_z_mid,
           c.call_original, c.description, c.game_type
    FROM abs.main_marts.v_called_pitch_open AS c
    WHERE c.level = 'mlb' AND c.game_type IN (%s) AND c.analysis_set = 'open'
      AND c.plate_x_mid IS NOT NULL AND c.plate_z_mid IS NOT NULL
      AND c.official_date <= CAST(? AS DATE)", gt))
  v <- v[!v$pitch_uid %in% base$pitch_uid & v$season %in% SEASONS, , drop = FALSE]
  v <- v[!v$game_pk %in% NO_ABS_HARDWARE_GAMES, , drop = FALSE]
  if (nrow(v) == 0L) return(v)
  v$official_date <- as.Date(v$official_date)
  hb <- unique(base[, c("batter", "season", "H", "H_abs")])
  hb <- hb[!duplicated(hb[, c("batter", "season")]), ]
  kb <- match(paste(v$batter, v$season), paste(hb$batter, hb$season))
  drop <- is.na(kb) | is.na(v$umpire_hp_id) | is.na(v$call_original) | !v$pitch_type %in% names(PITCH_GROUP_MAP) |
    !v$balls %in% 0:3 | !v$strikes %in% 0:2 | is.na(v$velo)
  record("extra rows dropped", sprintf("%d of %d: %d batter-seasons not in P0, %d no umpire, %d no original call, %d unmapped pitch type, %d bad count or no velocity",
                                       sum(drop), nrow(v), sum(is.na(kb)), sum(is.na(v$umpire_hp_id)), sum(is.na(v$call_original)),
                                       sum(!v$pitch_type %in% names(PITCH_GROUP_MAP)),
                                       sum(!v$balls %in% 0:3 | !v$strikes %in% 0:2 | is.na(v$velo))))
  v <- v[!drop, , drop = FALSE]; kb <- kb[!drop]
  H <- hb$H[kb]; Ha <- hb$H_abs[kb]
  out <- data.frame(pitch_uid = v$pitch_uid, game_pk = v$game_pk, official_date = v$official_date,
                    season = as.integer(v$season), regime = as.character(v$regime), analysis_set = as.character(v$analysis_set),
                    umpire_hp_id = as.integer(v$umpire_hp_id), umpire_season = as.character(v$umpire_season),
                    batter = as.integer(v$batter), pitcher = as.integer(v$pitcher), stand = as.character(v$stand), balls = as.integer(v$balls), strikes = as.integer(v$strikes),
                    count_class = CC_LEVELS[v$strikes + 1L], pitch_group = unname(PITCH_GROUP_MAP[v$pitch_type]),
                    pitch_type = v$pitch_type, velo = v$velo, x_mid = v$plate_x_mid, z_mid = v$plate_z_mid, H = H,
                    zn = z_norm(v$plate_z_mid, H),
                    d = signed_edge_in(v$plate_x_mid, v$plate_z_mid, abs_top_ft(H), abs_bot_ft(H)),
                    edge = nearest_edge(v$plate_x_mid, v$plate_z_mid, abs_top_ft(H), abs_bot_ft(H)),
                    cs = as.integer(v$call_original == "strike"), H_abs = Ha,
                    d_abs = ifelse(is.na(Ha), NA_real_, signed_edge_in(v$plate_x_mid, v$plate_z_mid, abs_top_ft(Ha), abs_bot_ft(Ha))),
                    stringsAsFactors = FALSE)
  bad <- c(if (!all(out$regime == REGIME_OF[as.character(out$season)])) "a regime that does not match its season",
           if (!all(out$analysis_set == "open")) "an analysis set other than open",
           if (any(out$official_date > ctx$last_open)) "a row after the last open day",
           if (!identical(out$umpire_season, paste0(out$umpire_hp_id, ":", out$season))) "umpire_season is not umpire:season")
  if (length(bad)) die("the extra rows fail: ", paste(bad, collapse = "; "))
  for (k in setdiff(names(base), names(out))) out[[k]] <- if (k == "challenged" || k == "is_overturned") FALSE else NA
  out[, names(base)]
}

## --- the rows of a cell --------------------------------------------------------------------------

LOAD_EXTRA <- c("batter", "pitcher", "challenged", "is_overturned", "x_front", "z_front")

# D-14's fitted r: the 2026 challenges of the open window on the ABS-measured d, a 0.01-in grid
# over [0, 2] in, the midpoint of the widest run of r values under which the most challenges are
# consistent with overturned == XOR(original strike, d_abs - r < 0).
fit_r <- function(d) {
  ch <- d[d$season == 2026L & !is.na(d$challenged) & d$challenged & !is.na(d$d_abs) & !is.na(d$is_overturned), , drop = FALSE]
  if (nrow(ch) == 0L) return(NULL)
  s0 <- ch$cs == 1L
  ov <- as.logical(ch$is_overturned)
  n_ok <- vapply(R_GRID, function(r) sum(ov == xor(s0, ch$d_abs - r < 0)), integer(1))
  best <- max(n_ok)
  at <- which(n_ok == best)
  runs <- split(at, cumsum(c(1L, diff(at) != 1L)))
  run <- runs[[which.max(lengths(runs))]]
  list(r = round(mean(R_GRID[range(run)]), 2), lo = R_GRID[min(run)], hi = R_GRID[max(run)], n = nrow(ch),
       n_consistent = best, n_runs = length(runs), n_at_primary = n_ok[which.min(abs(R_GRID - BALL_R_IN))])
}

# The per-batter ML offset (see the header): one delta_b per batter, from his 2022-2024 top- and
# bottom-edge calls under a pooled link per edge.
ml_offsets <- function(prim, min_n = ML_MIN_N) {
  pre <- prim[prim$season <= 2024L & prim$edge %in% c("top", "bot") & abs(prim$x_mid) <= PLATE_HALF_W_FT &
                abs(prim$d) <= BAND_SURF, c("batter", "edge", "d", "cs"), drop = FALSE]
  lut <- list()
  for (e in c("top", "bot")) {
    s <- pre[pre$edge == e, , drop = FALSE]
    m <- stats::glm(cs ~ splines::ns(d, df = LINK_DF), family = binomial(), data = s)
    lp <- stats::predict(m, data.frame(d = ML_U))
    lut[[e]] <- list(lg = plogis(lp, log.p = TRUE), l1g = plogis(lp, lower.tail = FALSE, log.p = TRUE))
    record(sprintf("ML offset link, %s edge", e), sprintf("glm(cs ~ ns(d, %d)) on %s 2022-2024 pitches; 50%% point at d = %.2f in",
                                                        LINK_DF, comma(nrow(s)), ML_U[which.min(abs(lp))]))
  }
  nb <- tapply(abs(pre$d) <= BAND_SHADOW, pre$batter, sum)
  elig <- sort(as.integer(names(nb)[nb >= min_n]))
  if (length(elig) == 0L) return(data.frame(batter = integer(0), delta = numeric(0), on_bound = logical(0), n_near = integer(0)))
  p <- pre[pre$batter %in% elig, , drop = FALSE]
  bi <- match(p$batter, elig)
  top <- p$edge == "top"
  y1 <- p$cs == 1L
  shift <- ifelse(top, -ABS_TOP_FRAC, ABS_BOT_FRAC)
  LL <- matrix(0, length(elig), length(ML_GRID))
  for (j in seq_along(ML_GRID)) {
    idx <- as.integer(round((p$d + shift * ML_GRID[j] - ML_U[1]) / 0.01)) + 1L
    idx <- pmin(pmax(idx, 1L), length(ML_U))
    ll <- ifelse(top, ifelse(y1, lut$top$lg[idx], lut$top$l1g[idx]), ifelse(y1, lut$bot$lg[idx], lut$bot$l1g[idx]))
    LL[, j] <- as.vector(rowsum(ll, bi, reorder = TRUE))
  }
  jb <- max.col(LL, ties.method = "first")
  data.frame(batter = elig, delta = ML_GRID[jb], on_bound = jb == 1L | jb == length(ML_GRID),
             n_near = as.integer(nb[as.character(elig)]), stringsAsFactors = FALSE)
}

recompute_geometry <- function(rows, H) {
  rows$H <- H
  rows$zn <- z_norm(rows$z_mid, H)
  rows$d <- signed_edge_in(rows$x_mid, rows$z_mid, abs_top_ft(H), abs_bot_ft(H))
  rows$edge <- nearest_edge(rows$x_mid, rows$z_mid, abs_top_ft(H), abs_bot_ft(H))
  rows
}

deferred <- function(note) list(status = "deferred", note = note)

# The rows of one configuration, every |d|, before the band restriction. Returns status "ok" with
# the rows and the r the shadow band uses, or status "deferred" with the reason.
cell_rows <- function(ctx, cfg, d, cal, opt) {
  info <- character(0)
  base <- d
  if (cfg$pp) {
    if (ctx$synthetic) return(deferred("synthetic table: no open view to add position players' pitches from"))
    ex <- extra_rows(ctx, base, "R")
    whole <- !any(unique(paste(ex$pitcher, ex$season)) %in% unique(paste(base$pitcher, base$season)))
    check("position players: every added pitch is a pitcher-season P0 removed", nrow(ex) > 0L && whole,
          sprintf("%s pitches from %d pitchers", comma(nrow(ex)), length(unique(ex$pitcher))))
    info <- c(info, sprintf("%s position-player pitches added", comma(nrow(ex))))
    base <- rbind(base, ex)
  }
  if (cfg$postseason) {
    if (ctx$synthetic) return(deferred("synthetic table: no open view to add postseason pitches from"))
    ex <- extra_rows(ctx, base, POSTSEASON_TYPES)
    if (nrow(ex) == 0L) {
      return(deferred(paste("the warehouse's open view holds no 2022-2025 postseason called pitch (game_type F, D, L, W):",
                            "the Statcast and schedule pulls cover game_type R only; the cell runs on the first pass that finds rows")))
    }
    info <- c(info, sprintf("%s postseason pitches added", comma(nrow(ex))))
    base <- rbind(base, ex)
  }
  rule <- if (cfg$height == "abs_cohort") "abs_cohort" else primary_height_rule(opt)
  rows <- apply_heights(base, rule, cal, ctx)
  if (cfg$height == "ml_offset") {
    min_n <- if (ctx$synthetic) ML_MIN_N_SYNTHETIC else ML_MIN_N
    off <- ml_offsets(rows, min_n)
    use <- off[!off$on_bound, , drop = FALSE]
    k <- match(rows$batter, use$batter)
    dl <- ifelse(is.na(k), 0, use$delta[k])
    rows <- recompute_geometry(rows, rows$H + dl)
    txt <- sprintf("%d batters with >= %d near-edge 2022-2024 pitches, %d on the grid bound kept the primary rule; median delta %+.2f in, IQR %.2f in; %.1f%% of rows re-heighted",
                   nrow(off), min_n, sum(off$on_bound), stats::median(use$delta), stats::IQR(use$delta), 100 * mean(!is.na(k)))
    record("per-batter ML offset", txt)
    check("per-batter ML offset: some batters estimated", nrow(use) > 0L, txt)
    info <- c(info, txt)
  }
  if (cfg$plane == "front") {
    v <- view_columns(ctx, rows)
    ok <- !is.na(v$x_front) & !is.na(v$z_front)
    check("front plane: every row has the front pair", all(ok), sprintf("%s of %s rows", comma(sum(ok)), comma(nrow(rows))))
    rows$x_mid <- v$x_front
    rows$z_mid <- v$z_front
    rows <- recompute_geometry(rows, rows$H)
    info <- c(info, "d, zn and edge on the front-of-plate pair")
  }
  if (!cfg$blocked_ball) {
    if (ctx$synthetic) return(deferred("synthetic table: no description column to find blocked_ball in"))
    v <- view_columns(ctx, rows)
    bb <- !is.na(v$description) & v$description == "blocked_ball"
    info <- c(info, sprintf("%s blocked_ball rows dropped", comma(sum(bb))))
    record("blocked_ball out", sprintf("%s of %s rows dropped", comma(sum(bb)), comma(nrow(rows))))
    rows <- rows[!bb, , drop = FALSE]
  }
  r <- cfg$r
  if (isTRUE(cfg$r_fitted)) {
    fr <- fit_r(d)
    if (is.null(fr)) return(deferred("no 2026 challenge with an ABS-measured d in the table: r cannot be fitted"))
    txt <- sprintf("fitted r = %.2f in (maximal run %.2f to %.2f in, %d run(s)); %s of %s 2026 challenges consistent at it, %s at r = 1.45",
                   fr$r, fr$lo, fr$hi, fr$n_runs, comma(fr$n_consistent), comma(fr$n), comma(fr$n_at_primary))
    record("D-14 fitted r", txt)
    info <- c(info, txt)
    r <- fr$r
  }
  list(status = "ok", rows = rows, r = r, note = paste(info, collapse = "; "))
}

band_rows <- function(rows, cfg) if (is.finite(cfg$band)) rows[abs(rows$d) <= cfg$band, , drop = FALSE] else rows
mix_season <- function(cfg) if (identical(cfg$mix, "2025")) "2025" else REF_SEASON
shadow_rows <- function(ref, cfg, r) ref[abs(ref$d - r) <= cfg$shadow_w, , drop = FALSE]
# Weights of the shadow-band reference pitches: equal per pitch, or equal per count-class x
# handedness cell under the unweighted mix.
shadow_weights <- function(sh, cfg) {
  key <- paste(sh$count_class, sh$stand)
  if (identical(cfg$mix, "unweighted")) {
    n <- table(key)
    return(1 / (length(n) * as.numeric(n[key])))
  }
  rep(1 / nrow(sh), nrow(sh))
}

## --- the binned logistic, the library's code with the band and the bin width set per cell --------

BIN_W_PRIMARY <- 0.5
with_bins <- function(B, bw, expr) {
  old <- list(D_BAND_IN = D_BAND_IN, BIN_W_IN = BIN_W_IN, N_BINS = N_BINS)
  nb <- as.integer(round(2 * B / bw))
  if (abs(nb * bw - 2 * B) > 1e-9) die(sprintf("bin width %g does not divide the band [-%g, %g]", bw, B, B))
  assign("D_BAND_IN", B, envir = globalenv())
  assign("BIN_W_IN", bw, envir = globalenv())
  assign("N_BINS", nb, envir = globalenv())
  on.exit(for (k in names(old)) assign(k, old[[k]], envir = globalenv()), add = TRUE)
  force(expr)
}

binned_shadow <- function(fits, sh, wt, Bd) {
  nd_ <- nrow(Bd[[1]])
  point <- stats::setNames(numeric(length(SEASON_LEVELS)), SEASON_LEVELS)
  draws <- matrix(0, nd_, length(SEASON_LEVELS), dimnames = list(NULL, SEASON_LEVELS))
  for (e in EDGE_LEVELS) {
    f <- fits[[e]]
    ie <- which(sh$edge == e)
    if (length(ie) == 0L) next
    bf <- factor(as.integer(bin_index(sh$d[ie])), levels = levels(f$model$bin_f))
    if (anyNA(bf)) die("a shadow-band pitch falls in a bin with no fitted coefficient at the ", e, " edge")
    tt <- stats::delete.response(stats::terms(f))
    Bt <- t(Bd[[e]])
    for (s in SEASON_LEVELS) {
      nd <- data.frame(bin_f = bf, season = factor(s, levels = SEASON_LEVELS),
                       count_class = factor(sh$count_class[ie], levels = CC_LEVELS),
                       stand = factor(sh$stand[ie], levels = STAND_LEVELS))
      X <- stats::model.matrix(tt, nd, contrasts.arg = f$contrasts)
      point[s] <- point[s] + sum(wt[ie] * plogis(as.vector(X %*% stats::coef(f))))
      for (st in seq(1L, length(ie), by = 5000L)) {
        ii <- st:min(length(ie), st + 4999L)
        draws[, s] <- draws[, s] + colSums(wt[ie][ii] * plogis(X[ii, , drop = FALSE] %*% Bt))
      }
    }
  }
  list(point = 100 * point, draws = 100 * draws)
}

binned_cell <- function(ctx, cfg, rows, r) {
  fitrows <- band_rows(rows, cfg)
  B <- if (is.finite(cfg$band)) cfg$band else BAND_SURF
  bw <- BIN_W_PRIMARY / cfg$k_scale
  ref <- fitrows[fitrows$season == as.integer(mix_season(cfg)), , drop = FALSE]
  with_bins(B, bw, {
    fits <- fit_binned(aggregate_bins(fitrows))
    ok <- all(vapply(fits, function(f) f$converged && !anyNA(stats::coef(f)), TRUE))
    check("binned: three edge glm fits converged, no aliased coefficient", ok,
          sprintf("bins %.4f in over [-%g, %g]%s; %s", bw, B, B, if (is.finite(cfg$band)) "" else ", end bins open-ended",
                  paste(sprintf("%s %d cells", EDGE_LEVELS, vapply(fits, function(f) nrow(f$model), 0L)), collapse = ", ")))
    w <- binned_ref_weights(ref)
    if (identical(cfg$mix, "unweighted")) w$w <- 1 / nrow(w)
    Bd <- binned_draws(fits, ctx$n_draws, DRAW_SEED)
    point <- t(vapply(SEASON_LEVELS, function(s) binned_estimands(fits, w, s)[1, ], numeric(4)))
    dl <- lapply(SEASON_LEVELS, function(s) binned_estimands(fits, w, s, Bd))
    sh <- shadow_rows(ref, cfg, r)
    shr <- binned_shadow(fits, sh, shadow_weights(sh, cfg), Bd)
  })
  draws <- lapply(stats::setNames(GEOM, GEOM), function(e) vapply(dl, function(m) m[, e], numeric(nrow(dl[[1]]))))
  draws$shadow_rate <- shr$draws
  point <- cbind(point, shadow_rate = shr$point)
  rownames(point) <- SEASON_LEVELS
  list(point = point[, GRID_ESTIMANDS, drop = FALSE], draws = draws[GRID_ESTIMANDS], n_rows = nrow(fitrows),
       n_shadow = nrow(sh), detail = sprintf("binned logistic (annex 5), bins %.4f in over [-%g, %g]%s, %s reference mix, glm N(beta, vcov) draws",
                                             bw, B, B, if (is.finite(cfg$band)) "" else " with open-ended end bins", cfg$mix))
}

## --- bam: the frozen specification refitted on the cell's rows ------------------------------------

scale_k <- function(f, s) {
  m <- gregexpr("k = c\\([0-9]+,[0-9]+\\)", f)
  parts <- regmatches(f, m)[[1]]
  regmatches(f, m) <- list(vapply(parts, function(p) {
    n <- as.integer(sub("^k = c\\(([0-9]+),.*$", "\\1", p))
    sprintf("k = c(%d,%d)", as.integer(round(n * s)), as.integer(round(n * s)))
  }, ""))
  v <- regmatches(f, regexpr("s\\(velo, k = [0-9]+\\)", f))
  if (length(v) != 1L || length(parts) != 4L) die("the frozen formula does not carry the four te k's and s(velo, k)")
  sub(v, sprintf("s(velo, k = %d)", as.integer(round(as.integer(sub("^.*k = ([0-9]+)\\)$", "\\1", v)) * s))), f, fixed = TRUE)
}

bam_cell <- function(ctx, cfg, rows, r) {
  fitrows <- band_rows(rows, cfg)
  spec <- make_spec("main")
  if (cfg$k_scale != 1) spec$formula <- scale_k(spec$formula, cfg$k_scale)
  record("bam formula", spec$formula)
  ft <- fit_surface(fit_frame(fitrows, spec), spec)
  check("bam converged", ft$converged, sprintf("%s rows, %s coefficients, edf %.1f, largest fREML gradient %.1e, %.0f s",
                                                comma(nrow(fitrows)), comma(ft$n_coef), ft$edf, ft$grad_max, ft$seconds))
  if (length(ft$warnings) > 0L) record("bam warnings", paste(ft$warnings, collapse = " | "))
  cd <- coef_draws(ft$m, ctx$n_draws, DRAW_SEED)
  ref <- fitrows[fitrows$season == as.integer(mix_season(cfg)), , drop = FALSE]
  mix <- ref_mix(ft$m, ft$spec, ref, mix_season(cfg))
  if (identical(cfg$mix, "unweighted")) for (i in seq_along(mix$cells)) mix$cells[[i]]$w <- 1 / length(mix$cells)
  sh <- shadow_rows(ref, cfg, r)
  key <- paste(sh$count_class, sh$stand)
  grp <- match(key, sort(unique(key)))
  ng <- tabulate(grp)
  W <- if (identical(cfg$mix, "unweighted")) rep(1 / length(ng), length(ng)) else ng / sum(ng)
  point <- matrix(NA_real_, length(SEASON_LEVELS), length(GRID_ESTIMANDS), dimnames = list(SEASON_LEVELS, GRID_ESTIMANDS))
  draws <- lapply(stats::setNames(GRID_ESTIMANDS, GRID_ESTIMANDS), function(e) matrix(NA_real_, nrow(cd), length(SEASON_LEVELS)))
  for (j in seq_along(SEASON_LEVELS)) {
    s <- SEASON_LEVELS[j]
    t0 <- proc.time()
    est <- surface_estimands(ft$m, ft$spec, mix, s, ref, cd, geom_only = TRUE)
    M <- group_means(ft$m, ft$spec, s, sh, grp, cd)
    rate <- 100 * colSums(W * M)
    point[s, GEOM] <- est$point[GEOM]
    point[s, "shadow_rate"] <- rate[1]
    for (e in GEOM) draws[[e]][, j] <- est$draws[, e]
    draws$shadow_rate[, j] <- rate[-1]
    record(sprintf("bam %s", s), sprintf("%s; %.0f s", paste(sprintf("%s %.3f", GRID_ESTIMANDS, point[s, ]), collapse = ", "),
                                         (proc.time() - t0)[["elapsed"]]))
  }
  list(point = point, draws = draws, n_rows = nrow(fitrows), n_shadow = nrow(sh),
       detail = sprintf("bam refit, %s; 1,000 draws of N(beta, Vc), seed %d; %s mix; 72-in batter",
                        if (cfg$k_scale != 1) sprintf("frozen specification with every k x %g", cfg$k_scale) else "frozen specification",
                        DRAW_SEED, cfg$mix))
}

# The bam primary and the ABS-measured arm, read from W3.14's fit and W3.15's draws when the fit's
# receipt names this table and this height rule. NULL otherwise, and the cell is refitted.
REUSABLE <- c(primary = "main", height_abs_cohort = "abs_cohort")
reuse_bam <- function(ctx, cell_id, opt) {
  fit <- REUSABLE[cell_id]
  if (is.na(fit)) return(NULL)
  p <- ctx$paths
  rp <- file.path(p$models, sprintf("surface_%s", fit), "provenance.json")
  f3 <- file.path(p$tab, "T3_estimands.csv")
  fd <- file.path(p$model, sprintf("estimand_draws_%s.csv", fit))
  if (!all(file.exists(c(rp, f3, fd)))) return(NULL)
  rc <- fromJSON(rp)
  want_rule <- if (fit == "abs_cohort") "abs_cohort" else primary_height_rule(opt)
  if (!identical(rc$table_sha256, sha256_file(ctx$table)) || !identical(rc$height_rule_key, want_rule)) return(NULL)
  t3 <- read_csv_plain(f3)
  t3 <- t3[t3$fit == fit, , drop = FALSE]
  D <- read_csv_plain(fd)
  point <- matrix(NA_real_, length(SEASON_LEVELS), length(GRID_ESTIMANDS), dimnames = list(SEASON_LEVELS, GRID_ESTIMANDS))
  draws <- list()
  for (e in GRID_ESTIMANDS) {
    for (s in SEASON_LEVELS) point[s, e] <- t3$point[t3$season == as.integer(s) & t3$estimand == e]
    draws[[e]] <- as.matrix(D[, paste(SEASON_LEVELS, e, sep = "_")])
  }
  if (!all(is.finite(point)) || nrow(D) != ctx$n_draws) return(NULL)
  record("bam reused", sprintf("W3.14 fit %s and W3.15 draws %s: the receipt names this table and height rule %s", fit, fd, want_rule))
  list(point = point, draws = draws, n_rows = rc$n_rows, n_shadow = NA_integer_,
       detail = sprintf("bam, W3.14 fit %s with W3.15's 1,000 draws of N(beta, Vc), seed %d, read, not refitted", fit, DRAW_SEED))
}

## --- the grid file -----------------------------------------------------------------------------------

COMP_COLS <- c("delta_buffer", "delta_abs")
HEAD_COLS <- c(
  "delta_buffer", "delta_buffer_lo95", "delta_buffer_hi95", "delta_abs", "delta_abs_lo95", "delta_abs_hi95",
  "delta_total", "delta_total_lo95", "delta_total_hi95", "g", "g_lo95", "g_hi95",
  "sum_components", "sum_lo95", "sum_hi95", "share_abs", "share_abs_lo95", "share_abs_hi95", "share_reported")
SIDE_COLS <- as.vector(t(outer(SIDE_ESTIMANDS, c("delta_buffer", "delta_buffer_lo95", "delta_buffer_hi95",
                                                 "delta_abs", "delta_abs_lo95", "delta_abs_hi95"), paste, sep = "_")))
DERIVED_COLS <- c("sign_buffer_vs_primary", "sign_abs_vs_primary", "buffer_ci_excludes_primary", "abs_ci_excludes_primary",
                  "headline_shift_sqin", "bam_selected", "edge_sign_flips")
GRID_COLS <- c("id", "cell_id", "factor", "value", "is_primary", "same_as_primary", "estimator", "status", "status_note",
               "headline_estimand", "units", HEAD_COLS, SIDE_COLS, "identity_residual_max", "n_rows", "n_shadow_ref",
               "n_draws", "n_complete_min", "seed", "r_in", "config", "estimator_detail", DERIVED_COLS,
               "git_sha", "code_sha256", "table_sha256", "written_madrid")

grid_path <- function(p) file.path(p$tab, "sensitivity_grid.csv")
t8_path <- function(p) file.path(p$tables, "T8_sensitivity_data.csv")
cell_meta <- function(cell_id) {
  if (identical(cell_id, "primary")) return(list(factor = "primary", value = "pre-registered primary"))
  i <- match(cell_id, CELLS$cell_id)
  list(factor = CELLS$factor[i], value = CELLS$value[i])
}

# One grid row from a cell's point matrix and draws. NA everywhere for a deferred cell.
grid_row <- function(ctx, cell_id, estimator, cfg, res, r, status, note) {
  row <- as.list(stats::setNames(rep(NA, length(GRID_COLS)), GRID_COLS))
  m <- cell_meta(cell_id)
  row[c("id", "cell_id", "factor", "value", "estimator")] <- list(paste(cell_id, estimator, sep = "|"), cell_id, m$factor,
                                                                   m$value, estimator)
  row$is_primary <- identical(cell_id, "primary")
  row$same_as_primary <- identical(cell_id, "primary") || isTRUE(CELLS$same_as_primary[match(cell_id, CELLS$cell_id)])
  row[c("status", "status_note", "headline_estimand", "units", "seed", "config")] <-
    list(status, note, HEADLINE, ESTIMAND_UNITS[[HEADLINE]], DRAW_SEED, cfg_text(cfg))
  row$r_in <- r
  row[c("git_sha", "code_sha256", "table_sha256", "written_madrid")] <-
    list(git_head(), sha256_text(paste(ctx$code_shas, collapse = "\n")), sha256_file(ctx$table), madrid_now())
  if (!identical(status, "ok")) return(as.data.frame(row, stringsAsFactors = FALSE, check.names = FALSE))
  dec <- lapply(stats::setNames(GRID_ESTIMANDS, GRID_ESTIMANDS), function(e) {
    decompose_estimand(res$point[, e], res$draws[[e]], e, ESTIMAND_UNITS[[e]])
  })
  tb <- dec[[HEADLINE]]$table
  pick <- function(tab, comp, col) tab[tab$component == comp, col]
  for (comp in c("delta_buffer", "delta_abs", "delta_total", "g")) {
    row[[comp]] <- pick(tb, comp, "point")
    row[[paste0(comp, "_lo95")]] <- pick(tb, comp, "lo95")
    row[[paste0(comp, "_hi95")]] <- pick(tb, comp, "hi95")
  }
  row[c("sum_components", "sum_lo95", "sum_hi95")] <- list(pick(tb, "sum_components", "point"), pick(tb, "sum_components", "lo95"),
                                                           pick(tb, "sum_components", "hi95"))
  row$share_reported <- isTRUE(dec[[HEADLINE]]$share_reported)
  if (row$share_reported) {
    row[c("share_abs", "share_abs_lo95", "share_abs_hi95")] <- list(pick(tb, "share_abs", "point"), pick(tb, "share_abs", "lo95"),
                                                                    pick(tb, "share_abs", "hi95"))
  }
  for (e in SIDE_ESTIMANDS) for (comp in COMP_COLS) {
    t <- dec[[e]]$table
    row[[sprintf("%s_%s", e, comp)]] <- pick(t, comp, "point")
    row[[sprintf("%s_%s_lo95", e, comp)]] <- pick(t, comp, "lo95")
    row[[sprintf("%s_%s_hi95", e, comp)]] <- pick(t, comp, "hi95")
  }
  row$identity_residual_max <- max(vapply(dec, function(x) x$identity_residual, 0))
  row$n_rows <- res$n_rows
  row$n_shadow_ref <- res$n_shadow
  row$n_draws <- nrow(res$draws[[1]])
  row$n_complete_min <- min(vapply(dec, function(x) x$table$n_draws[1], 0))
  row$estimator_detail <- res$detail
  check(sprintf("%s|%s: identity delta_buffer + delta_abs + 2g = delta_total", cell_id, estimator),
        row$identity_residual_max <= IDENTITY_TOL, sprintf("max residual %.1e over %d estimands", row$identity_residual_max,
                                                           length(dec)))
  check(sprintf("%s|%s: every season point finite", cell_id, estimator), all(is.finite(res$point)),
        paste(sprintf("%s %.3f", colnames(res$point), res$point["2026", ]), collapse = ", "))
  record(sprintf("%s|%s area", cell_id, estimator),
         sprintf("delta_buffer %.2f (%.2f to %.2f), delta_abs %.2f (%.2f to %.2f) sq in; share %s", row$delta_buffer,
                 row$delta_buffer_lo95, row$delta_buffer_hi95, row$delta_abs, row$delta_abs_lo95, row$delta_abs_hi95,
                 if (row$share_reported) sprintf("%.3f", row$share_abs) else "not reported (CH1-A9)"))
  as.data.frame(row, stringsAsFactors = FALSE, check.names = FALSE)
}

write_rows <- function(p, rows) {
  f <- grid_path(p)
  with_lock(p$tab, for (i in seq_len(nrow(rows))) upsert_row(f, rows[i, GRID_COLS, drop = FALSE], key = "id"))
  record("grid rows written", sprintf("%s: %s", f, paste(rows$id, collapse = ", ")))
}

read_grid <- function(p) {
  f <- grid_path(p)
  if (!file.exists(f)) return(NULL)
  g <- utils::read.csv(f, stringsAsFactors = FALSE, check.names = FALSE, na.strings = "")
  g
}

# A cell is done when its row is "ok" on this table and this code.
cell_done <- function(ctx, cell_id, estimator) {
  g <- read_grid(ctx$paths)
  if (is.null(g)) return(FALSE)
  i <- which(g$id == paste(cell_id, estimator, sep = "|"))
  length(i) == 1L && identical(g$status[i], "ok") && identical(g$table_sha256[i], sha256_file(ctx$table)) &&
    identical(g$code_sha256[i], sha256_text(paste(ctx$code_shas, collapse = "\n")))
}

run_cell <- function(ctx, cell_id, estimator, d, cal, opt) {
  cfg <- cell_cfg(cell_id)
  record("cell", sprintf("%s|%s: %s", cell_id, estimator, cfg_text(cfg)))
  n_fail0 <- length(.ch1$failures)
  t0 <- proc.time()
  res <- NULL
  if (estimator == "bam") res <- reuse_bam(ctx, cell_id, opt)
  cr <- if (is.null(res)) cell_rows(ctx, cfg, d, cal, opt) else list(status = "ok", r = cfg$r, note = "")
  if (!identical(cr$status, "ok")) {
    record("cell deferred", sprintf("%s|%s: %s", cell_id, estimator, cr$note))
    write_rows(ctx$paths, grid_row(ctx, cell_id, estimator, cfg, NULL, NA_real_, "deferred", cr$note))
    return(invisible(NULL))
  }
  if (is.null(res)) res <- if (estimator == "binned") binned_cell(ctx, cfg, cr$rows, cr$r) else bam_cell(ctx, cfg, cr$rows, cr$r)
  rows <- grid_row(ctx, cell_id, estimator, cfg, res, cr$r, "ok", cr$note)
  if (cell_id == "primary" && estimator == "binned") {
    compare_binned_primary(ctx, rows)
    same <- CELLS$cell_id[CELLS$same_as_primary]
    for (id in same) {
      x <- rows
      m <- cell_meta(id)
      x[c("id", "cell_id", "factor", "value")] <- list(paste(id, "binned", sep = "|"), id, m$factor, m$value)
      x$is_primary <- FALSE
      x$same_as_primary <- TRUE
      x$status_note <- "the primary's configuration: the primary row's numbers, computed once"
      rows <- rbind(rows, x)
    }
  }
  if (length(.ch1$failures) > n_fail0) {
    record("cell NOT written", sprintf("%s|%s: %d check(s) failed", cell_id, estimator, length(.ch1$failures) - n_fail0))
    return(invisible(NULL))
  }
  write_rows(ctx$paths, rows)
  record("cell time", sprintf("%s|%s %.0f s", cell_id, estimator, (proc.time() - t0)[["elapsed"]]))
  invisible(NULL)
}

# The binned primary must be W3.16's CH1-A5 binned arm (T4_decomposition_arms.csv) on the four
# geometric estimands' delta_buffer and delta_abs.
compare_binned_primary <- function(ctx, row) {
  f <- file.path(ctx$paths$tab, "T4_decomposition_arms.csv")
  if (!file.exists(f)) { record("binned primary against W3.16", "no T4_decomposition_arms.csv under --out; not compared"); return() }
  t4 <- read_csv_plain(f)
  t4 <- t4[t4$fit == "binned", , drop = FALSE]
  gap <- c()
  for (e in GEOM) for (comp in COMP_COLS) {
    mine <- if (e == HEADLINE) row[[comp]] else row[[sprintf("%s_%s", e, comp)]]
    ref <- t4$point[t4$estimand == e & t4$component == comp]
    gap <- c(gap, if (length(ref) == 1L) abs(mine - ref) else Inf)
  }
  check("binned primary reproduces W3.16's CH1-A5 binned arm", max(gap) <= 1e-6,
        sprintf("max |difference| %.2e over 8 components", max(gap)))
}

## --- selecting the four bam cells, and the summary ---------------------------------------------------

rank_for_bam <- function(g) {
  b <- g[g$estimator == "binned", , drop = FALSE]
  pr <- b[b$cell_id == "primary" & b$status == "ok", , drop = FALSE]
  if (nrow(pr) != 1L) return(NULL)
  cand <- b[b$status == "ok" & !b$same_as_primary & b$cell_id != "primary", , drop = FALSE]
  cand$shift <- pmax(abs(cand$delta_buffer - pr$delta_buffer), abs(cand$delta_abs - pr$delta_abs))
  cand$order <- match(cand$cell_id, CELLS$cell_id)
  cand <- cand[order(-cand$shift, cand$order), , drop = FALSE]
  list(primary = pr, ranked = cand, selected = utils::head(cand$cell_id, N_BAM_REFITS))
}

select_bam <- function(p) {
  g <- read_grid(p)
  if (is.null(g)) die("no grid at ", grid_path(p))
  rk <- rank_for_bam(g)
  if (is.null(rk)) die("the binned primary row is missing or not ok")
  for (i in seq_len(nrow(rk$ranked))) {
    x <- rk$ranked[i, ]
    cat(sprintf("RANK %2d %-22s shift %.3f sq in\n", i, x$cell_id, x$shift))
  }
  for (id in rk$selected) {
    x <- rk$ranked[rk$ranked$cell_id == id, ]
    heavy <- x$n_rows > BAM_HEAVY_ROWS * rk$primary$n_rows || cell_cfg(id)$k_scale > 1
    cat(sprintf("BAM %s %d\n", id, as.integer(heavy)))
  }
  quit(status = 0)
}

sgn <- function(x) ifelse(is.na(x), NA_character_, ifelse(x > 0, "+", ifelse(x < 0, "-", "0")))

summarise_grid <- function(p) {
  g <- read_grid(p)
  if (is.null(g)) die("no grid at ", grid_path(p))
  g <- g[, GRID_COLS]
  want <- c("primary", CELLS$cell_id)
  have_b <- g$cell_id[g$estimator == "binned"]
  miss <- setdiff(want, have_b)
  check("every SOP cell has a binned row, and the primary is labelled", length(miss) == 0L &&
          sum(g$is_primary & g$estimator == "binned") == 1L,
        if (length(miss)) paste("missing:", paste(miss, collapse = ", ")) else sprintf("%d binned rows", length(have_b)))
  bad <- g$id[!g$status %in% c("ok", "deferred")]
  check("every row is ok or deferred with a reason", length(bad) == 0L &&
          all(!is.na(g$status_note[g$status == "deferred"]) & nzchar(g$status_note[g$status == "deferred"])),
        sprintf("%d ok, %d deferred%s", sum(g$status == "ok"), sum(g$status == "deferred"),
                if (any(g$status == "deferred")) paste0(": ", paste(g$id[g$status == "deferred"], collapse = ", ")) else ""))
  rk <- rank_for_bam(g)
  sel <- if (is.null(rk)) character(0) else rk$selected
  bam_ok <- g$cell_id[g$estimator == "bam" & g$status == "ok"]
  check("bam: the primary and the four cells that move the headline most", "primary" %in% bam_ok &&
          all(sel %in% bam_ok) && length(sel) == min(N_BAM_REFITS, if (is.null(rk)) 0L else nrow(rk$ranked)),
        sprintf("selected %s; bam rows ok: %s", paste(sel, collapse = ", "), paste(bam_ok, collapse = ", ")))
  g$bam_selected <- g$cell_id %in% sel
  for (est in unique(g$estimator)) {
    pr <- g[g$estimator == est & g$cell_id == "primary" & g$status == "ok", , drop = FALSE]
    if (nrow(pr) != 1L) next
    i <- which(g$estimator == est & g$status == "ok")
    g$sign_buffer_vs_primary[i] <- ifelse(sgn(g$delta_buffer[i]) == sgn(pr$delta_buffer), "same", "flip")
    g$sign_abs_vs_primary[i] <- ifelse(sgn(g$delta_abs[i]) == sgn(pr$delta_abs), "same", "flip")
    g$buffer_ci_excludes_primary[i] <- g$delta_buffer_lo95[i] > pr$delta_buffer | g$delta_buffer_hi95[i] < pr$delta_buffer
    g$abs_ci_excludes_primary[i] <- g$delta_abs_lo95[i] > pr$delta_abs | g$delta_abs_hi95[i] < pr$delta_abs
    g$headline_shift_sqin[i] <- pmax(abs(g$delta_buffer[i] - pr$delta_buffer), abs(g$delta_abs[i] - pr$delta_abs))
    g$edge_sign_flips[i] <- vapply(i, function(k) {
      fl <- c()
      for (e in SIDE_ESTIMANDS) for (comp in COMP_COLS) {
        cn <- sprintf("%s_%s", e, comp)
        if (!identical(sgn(g[[cn]][k]), sgn(pr[[cn]]))) fl <- c(fl, sprintf("%s:%s", e, sub("delta_", "", comp)))
      }
      if (length(fl)) paste(fl, collapse = ";") else "none"
    }, "")
  }
  ord <- order(match(g$estimator, c("binned", "bam")), match(g$cell_id, want))
  g <- g[ord, GRID_COLS]
  write_csv_plain(g, grid_path(p))
  ok <- g[g$status == "ok", , drop = FALSE]
  verdict <- function(col) length(unique(sgn(ok[[col]]))) == 1L && !"0" %in% sgn(ok[[col]])
  vb <- verdict("delta_buffer"); va <- verdict("delta_abs")
  record("CH1-A9 sign of delta_buffer (area)", sprintf("%s over %d ok rows: %s", if (vb) "STABLE" else "NOT STABLE", nrow(ok),
                                                       paste(names(table(sgn(ok$delta_buffer))), table(sgn(ok$delta_buffer)), collapse = ", ")))
  record("CH1-A9 sign of delta_abs (area)", sprintf("%s over %d ok rows: %s", if (va) "STABLE" else "NOT STABLE", nrow(ok),
                                                    paste(names(table(sgn(ok$delta_abs))), table(sgn(ok$delta_abs)), collapse = ", ")))
  for (e in SIDE_ESTIMANDS) for (comp in COMP_COLS) {
    cn <- sprintf("%s_%s", e, comp)
    record(sprintf("sign of %s", cn), sprintf("%s: %s", if (verdict(cn)) "stable" else "NOT stable",
                                             paste(names(table(sgn(ok[[cn]]))), table(sgn(ok[[cn]])), collapse = ", ")))
  }
  record("share_abs", sprintf("reported on %d of %d ok rows, where the 95%% interval on the sum excludes zero (CH1-A9)",
                              sum(ok$share_reported %in% TRUE), nrow(ok)))
  record("CH1-A9 VERDICT", if (vb && va) "PASS: the sign of each component is stable across the multiverse"
                           else "FAIL: a component changes sign; the headline is reported as a range over the multiverse")
  t8 <- do.call(rbind, lapply(seq_len(nrow(g)), function(k) {
    x <- g[k, ]
    do.call(rbind, lapply(GRID_ESTIMANDS, function(e) {
      comps <- if (e == HEADLINE) c("delta_buffer", "delta_abs", "delta_total", "sum_components", "share_abs") else COMP_COLS
      do.call(rbind, lapply(comps, function(comp) {
        cn <- if (e == HEADLINE) comp else sprintf("%s_%s", e, comp)
        lo <- if (e == HEADLINE && comp == "sum_components") "sum_lo95" else paste0(cn, "_lo95")
        hi <- if (e == HEADLINE && comp == "sum_components") "sum_hi95" else paste0(cn, "_hi95")
        data.frame(cell_id = x$cell_id, factor = x$factor, value = x$value, estimator = x$estimator, is_primary = x$is_primary,
                   same_as_primary = x$same_as_primary, status = x$status, estimand = e,
                   units = if (comp == "share_abs") "ratio" else ESTIMAND_UNITS[[e]], component = comp,
                   point = x[[cn]], lo95 = x[[lo]], hi95 = x[[hi]],
                   reported = if (comp == "share_abs") isTRUE(x$share_reported) else identical(x$status, "ok"),
                   bam_selected = x$bam_selected, stringsAsFactors = FALSE)
      }))
    }))
  }))
  write_csv_plain(t8, t8_path(p))
  record("written", sprintf("%s (%d rows), %s (%d rows)", grid_path(p), nrow(g), t8_path(p), nrow(t8)))
  finish(STEP)
}

## --- main ------------------------------------------------------------------------------------------

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE), flags = c("list", "select-bam", "summarise", "force"))
  if (isTRUE(opt$list)) {
    for (id in RUN_CELLS) cat(sprintf("CELL %s\n", id))
    quit(status = 0)
  }
  p <- out_paths(opt_get(opt, "out", file.path(ROOT, "out")))
  if (isTRUE(opt[["select-bam"]])) select_bam(p)
  if (isTRUE(opt$summarise)) summarise_grid(p)
  cells <- strsplit(opt_get(opt, "cells", ""), ",")[[1]]
  est <- opt_get(opt, "estimator", "binned")
  if (!length(cells) || !all(cells %in% RUN_CELLS)) {
    die("--cells takes ids from --list: ", paste(setdiff(cells, RUN_CELLS), collapse = ","))
  }
  if (!est %in% c("binned", "bam")) die("--estimator takes binned or bam")
  opt$cells <- NULL
  opt$estimator <- NULL
  force_run <- isTRUE(opt$force)
  opt$force <- NULL
  ctx <- start_run(STEP, opt, SCRIPT)
  todo <- if (force_run) cells else cells[!vapply(cells, function(id) cell_done(ctx, id, est), TRUE)]
  if (length(todo) < length(cells)) record("already done", paste(setdiff(cells, todo), collapse = ", "))
  if (length(todo)) {
    cal <- read_calibration(ctx, opt)
    d <- load_table(ctx, extra = LOAD_EXTRA)
    for (id in todo) run_cell(ctx, id, est, d, cal, opt)
  }
  finish(STEP)
}

if (identical(environment(), globalenv()) && !interactive()) main()
