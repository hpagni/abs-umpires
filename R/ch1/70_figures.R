#!/usr/bin/env Rscript
# R/ch1/70_figures.R - SOP W3.24, the Chapter 1 figures F1 to F8. `make figures` runs it; nothing else
# may produce a figure (SOP section 9.1).
#
#   make figures                                  scripts/figures.sh: --stage compute, then --stage render
#   Rscript R/ch1/70_figures.R --stage compute [--force]
#   Rscript R/ch1/70_figures.R --stage render [--dest <dir>]
#
# THE EIGHT FIGURES, as SOP W3.24 lists them, plus F2b (CH1-A13):
#   F1  50% contours by regime with 95% bands and the ABS rectangle. The regimes are drawn at their
#       decomposition anchors: 2024 (pre-buffer, the season Delta_total starts from), 2025 (buffer
#       cut) and 2026 (ABS challenge). Point contour: marching squares on the W3.15 grid, the same
#       code as T3. Band: pointwise 95% interval of the 50% crossing along 120 rays from the zone
#       centre (0, 0.4025 x 72 in), from the 1,000 N(beta, Vc) draws W3.14 wrote. Zoom panels on
#       the top, bottom and side edges, where the bands are wide enough to see.
#   F2  the decomposition waterfall per edge and area: 2g, Delta_buffer, Delta_ABS, Delta_total,
#       and the mechanical plane component (W3.17, D-56, CH1-A13) as a separate bar outside the sum.
#   F2b the dz-by-pitch-type figure CH1-A13 and D-56 ask for beside the plane component: the drop
#       between the front of the plate and mid-plate, 2025 called pitches, from W3.17's table
#       out/ch1/fig/F_dz_by_pitch_type.csv. The id follows F2, whose plane bar it explains; no
#       existing figure is renumbered.
#   F3  the edge event study: theta_s - theta_2024 per edge, 95% intervals from the joint draws,
#       with the 2023->2024 placebo boundary (P1) marked, and the two regime boundaries.
#   F4  the umpire caterpillar of the 2025->2026 response (W3.18's sop fit) with the tau posterior
#       inset. CH1-A6's reliability gate is not met, so under D-21 no umpire is named: the sidecar
#       carries ranks, never an umpire id. Intervals are 90%, as D-21 sets for per-umpire rows.
#   F5  the AAA arm. SOP W3.24 names "AAA challenge-format versus full-ABS contours", but W3.20's
#       committed outputs hold no contour coordinates (aaa_placebo.csv carries areas only), so F5
#       draws what they support (DEV-90): the within-week alternation from aaa_withinweek.csv
#       (challenge-format minus full-ABS called-strike rate, pooled, by season and by edge) and the
#       2023 to 2024 pre-trend from aaa_pretrend.csv (binned series, primary AAA window), each with
#       its 95% interval. Descriptive (DEV-77): placebo P1 failed.
#   F6  framing distribution by regime: W3.19's qualified catcher-seasons, count-specific runs per
#       100 innings, the primary 2026 convention (original calls).
#   F7  surface calibration by 0.5-inch d bin: in-sample, observed called-strike rate minus the
#       primary surface's mean fitted probability, per regime, 95% Wilson intervals.
#   F8  sealed prediction versus outcome. W3.23, the sealed run, runs once after 2026-11-01. Until
#       quality/receipts/W3.23.json exists F8 is a deliberate, dated "sealed run pending" panel with
#       status `pending` (DEV-90): it reads no sealed datum, and the closing clause is met with F8
#       pending by design. Once that receipt exists and F8 still has no builder, F8 turns into a
#       PLACEHOLDER and the run exits 3.
#
# ANNEX 8.7 (D-R0-04). Every top-edge interval is read as slightly too narrow, every top-edge
# statement carries that caveat, and the half-width's recovery shortfall is stated beside its
# interval. F1, F2 and F3 print edge numbers, so their captions carry both sentences. The counts
# are parsed from T4's recovery_disclosure column (W3.16, from R/lib/ch1_decomp.R), never typed
# here, and each lands in the sidecar as a constant row.
#
# DESIGN (the dataviz skill, loaded before this file was written). Every figure is drawn at 8 cm
# width, base type 7 pt, so "legible at 8 cm" holds by construction. Grayscale: the three regimes use
# one ordinal blue ramp (#86b6ef, #2a78d6, #104281; the skill's validator passes it with --ordinal
# on white), so the order survives grayscale, and line type repeats the identity. Figures with one
# series use one hue. Text is ink, never a series colour. Gridlines are solid hairlines. The manifest
# records each figure's data palette and its minimum CIE L* gap, which the test holds at >= 15.
#
# SIDECARS. Every figure writes out/tables/<figure-id>_data.csv (SOP W9.9): the plotted rows plus
# `constant` rows for every number a caption or alt text prints, so the test can trace them.
# Determinism is checked on the sidecars, never on the images.
#
# EXIT STATUS. 0 when every figure (F1 to F8 and F2b) is built, F8 aside while it is pending by design
# (no W3.23 receipt). 3 when every buildable figure was written but at least one is a placeholder (none
# today; F8 once W3.23's receipt exists and F8 is still undrawn), so `make figures` fails loudly.
#
# WRITES
#   --stage compute   out/ch1/fig/W3_24_F1_rays.csv, W3_24_F1_contours.csv, W3_24_F7_bins.csv,
#                     W3_24_fit_sample.csv, W3_24_compute_key.json; receipt models/ch1_W3_24_compute
#   --stage render    <dest>/figures/F<n>.png and .pdf, <dest>/tables/F<n>_data.csv (F2b included),
#                     <dest>/figures/figures_manifest.csv; receipt models/ch1_W3_24_figures
#
# F4's sidecar, out/tables/F4_data.csv, holds 88 anonymised per-umpire rows with intervals. Under
# D-21 and annex 8.5 no per-umpire table is published, so .gitignore keeps it local (DEV-83) and
# nothing here stages any file.

ROOT <- local({
  r <- Sys.getenv("ABSUMP_ROOT", "")
  if (nzchar(r)) return(normalizePath(r))
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

SCRIPT <- "R/ch1/70_figures.R"
FIG_IDS <- c("F1", "F2", "F2b", sprintf("F%d", 3:8))
FIG_TITLES <- c(F1 = "Called-zone contours by regime", F2 = "Decomposition waterfall",
                F2b = "Plate-plane drop by pitch type",
                F3 = "Edge event study", F4 = "Umpire caterpillar",
                F5 = "AAA challenge format versus full ABS", F6 = "Framing by regime",
                F7 = "Surface calibration by d bin", F8 = "Sealed prediction versus outcome")
# F8 is pending by design until the sealed run's receipt exists (DEV-90). The panel's two dates are
# read from DEV-90's schedule line in docs/DEVIATIONS.md, never from the clock, so the render stays
# deterministic and no date past the open window is written into analysis code (GD-04 rule 5).
SEALED_RECEIPT <- file.path("quality", "receipts", "W3.23.json")
DEV_F8 <- "DEV-90"
f8_schedule <- function() {
  x <- readLines(file.path(ROOT, "docs", "DEVIATIONS.md"), warn = FALSE, encoding = "UTF-8")
  m <- regmatches(x, regexec("^F8 pending panel: recorded ([0-9]{4}-[0-9]{2}-[0-9]{2}); W3\\.23 runs once after ([0-9]{4}-[0-9]{2}-[0-9]{2})\\.$", x))
  m <- m[lengths(m) == 3L]
  if (length(m) != 1L) die("docs/DEVIATIONS.md has ", length(m), " F8 schedule lines; ", DEV_F8, " gives exactly one")
  c(recorded = m[[1]][2], runs_after = m[[1]][3])
}
PENDING <- list(
  F8 = list(step = "W3.23", gate = SEALED_RECEIPT, dev = DEV_F8,
            why = "W3.23, the sealed run, runs once after the season; no sealed output exists and none is read here"))
sealed_run_done <- function() file.exists(file.path(ROOT, SEALED_RECEIPT))
# The blocked figures and the step each waits on. A figure listed here is drawn as a placeholder and
# the run exits 3. F8 joins it only once W3.23's receipt exists while F8 has no builder.
BLOCKED <- if (sealed_run_done()) {
  list(F8 = list(step = "W3.23", why = paste("quality/receipts/W3.23.json exists, so F8 must now be drawn from the",
                                             "sealed outputs, and R/ch1/70_figures.R has no F8 builder yet")))
} else list()

# F1's rays.
F1_SEASONS <- c("2024", "2025", "2026")
RAY_K <- 120L          # rays from the zone centre, 3 degrees apart
RAY_HALF <- 0.6        # in: each draw's crossing is sought within +/- 0.6 in of the point crossing
RAY_STEP <- 0.03       # in
ZC_IN <- ZN_MID * REF_HEIGHT_IN

# Palette (dataviz reference instance; print surface white).
INK <- "#0b0b0b"; INK2 <- "#52514e"; MUTED <- "#898781"; GRID <- "#e1e0d9"; AXIS <- "#c3c2b7"
B250 <- "#86b6ef"; B450 <- "#2a78d6"; B650 <- "#104281"; LIGHT <- "#c3c2b7"
REGIME_COL <- c(pre_buffer = B250, buffer_2025 = B450, abs_2026 = B650)
REGIME_LT  <- c(pre_buffer = "solid", buffer_2025 = "22", abs_2026 = "solid")
REGIME_LAB <- c(pre_buffer = "Pre-buffer", buffer_2025 = "Buffer cut", abs_2026 = "ABS challenge")
FIG_W_CM <- 8

fig_paths <- function(p) {
  list(rays = file.path(p$fig, "W3_24_F1_rays.csv"), contours = file.path(p$fig, "W3_24_F1_contours.csv"),
       bins = file.path(p$fig, "W3_24_F7_bins.csv"), sample = file.path(p$fig, "W3_24_fit_sample.csv"),
       key = file.path(p$fig, "W3_24_compute_key.json"))
}

## --- compute: the two inputs that need the fitted surface ------------------------------------------

# The largest t > 0 at which the ray t * (cos a, sin a) from the origin meets the closed polygon.
ray_polygon_radius <- function(px, pz, a) {
  ux <- cos(a); uz <- sin(a)
  n <- length(px)
  x1 <- px[-n]; z1 <- pz[-n]; ex <- px[-1] - x1; ez <- pz[-1] - z1
  den <- ux * ez - uz * ex
  ok <- abs(den) > 1e-14
  t <- (x1 * ez - z1 * ex) / den
  s <- (x1 * uz - z1 * ux) / den
  hit <- ok & t > 0 & s >= -1e-12 & s <= 1 + 1e-12
  if (!any(hit)) return(NA_real_)
  max(t[hit])
}

f1_season <- function(obj, B, mix, s, t3) {
  sg <- std_surface(obj$m, obj$spec, mix, s)
  met <- edge_metrics(sg)
  pt3 <- t3[t3$fit == "main" & t3$season == as.integer(s), ]
  gap <- max(abs(met[c("top_in", "bot_in", "half_width_in", "area_sqin")] -
                   pt3$point[match(c("top_in", "bot_in", "half_width_in", "area_sqin"), pt3$estimand)]))
  check(sprintf("F1 %s: the point contour reproduces T3's four geometric estimands", s), gap < 1e-6,
        sprintf("largest difference %.2e", gap))
  mc <- main_contour(unname(qlogis(sg$grid)))
  if (is.null(mc)) die("F1 ", s, ": no closed 50% contour around the zone centre")
  cx <- mc$x * 12; cz <- mc$y * REF_HEIGHT_IN - ZC_IN
  ang <- 2 * pi * (seq_len(RAY_K) - 1L) / RAY_K
  r0 <- vapply(ang, function(a) ray_polygon_radius(cx, cz, a), 0)
  if (anyNA(r0)) die("F1 ", s, ": a ray misses the point contour")
  off <- seq(-RAY_HALF, RAY_HALF, by = RAY_STEP)
  nr <- length(off)
  rr <- as.vector(outer(off, r0, "+"))
  aa <- rep(ang, each = nr)
  pts <- data.frame(x_mid = rr * cos(aa) / 12, zn = (ZC_IN + rr * sin(aa)) / REF_HEIGHT_IN)
  Bp <- rbind(stats::coef(obj$m), B)
  L <- qlogis(draw_prob(obj$m, obj$spec, mix, s, pts, Bp))
  rays <- do.call(rbind, lapply(seq_len(RAY_K), function(k) {
    idx <- (k - 1L) * nr + seq_len(nr)
    cr <- apply(L[idx, , drop = FALSE], 2, first_cross, s = rr[idx])
    d <- cr[-1]
    q <- qint(d, 0.95)
    data.frame(season = as.integer(s), regime = REGIME_OF[[s]], ray = k, angle_deg = (k - 1L) * 360 / RAY_K,
               r_contour = r0[k], r_point = cr[1], r_median = stats::median(d, na.rm = TRUE),
               r_lo95 = q[1], r_hi95 = q[2], n_draws = length(d), n_complete = sum(is.finite(d)))
  }))
  share <- min(rays$n_complete) / nrow(B)
  check(sprintf("F1 %s: every ray has >= %.0f%% of draws crossing inside its window", s, 100 * MIN_COMPLETE_SHARE),
        share >= MIN_COMPLETE_SHARE, sprintf("lowest share %.4f over %d rays", share, RAY_K))
  dpt <- max(abs(rays$r_point - rays$r_contour))
  check(sprintf("F1 %s: the ray crossing at beta agrees with the marching-squares contour", s), dpt < 0.05,
        sprintf("largest gap %.4f in", dpt))
  n <- length(mc$x)
  cont <- data.frame(season = as.integer(s), regime = REGIME_OF[[s]], vertex = seq_len(n),
                     x_in = mc$x * 12, z_in = mc$y * REF_HEIGHT_IN)
  list(rays = rays, contour = cont, met = met)
}

compute_key <- function(ctx) {
  p <- ctx$paths
  list(step = "W3.24", table_sha256 = sha256_file(ctx$table),
       surface_main_sha256 = sha256_file(file.path(p$model, "surface_main.rds")),
       draws_vc_main_sha256 = sha256_file(file.path(p$model, "draws_vc_main.rds")),
       t3_sha256 = sha256_file(file.path(p$tab, "T3_estimands.csv")),
       code_sha256 = sha256_text(paste(ctx$code_shas, collapse = "\n")),
       rays = list(k = RAY_K, half_in = RAY_HALF, step_in = RAY_STEP, seasons = F1_SEASONS))
}

compute_stage <- function(ctx, opt) {
  p <- ctx$paths
  fp <- fig_paths(p)
  ensure_dir(p$fig)
  key <- compute_key(ctx)
  outs <- c(fp$rays, fp$contours, fp$bins, fp$sample)
  if (is.null(opt$force) && file.exists(fp$key) && all(file.exists(outs))) {
    old <- fromJSON(fp$key, simplifyVector = FALSE)
    same_in <- identical(toJSON(old$key, auto_unbox = TRUE, digits = NA), toJSON(key, auto_unbox = TRUE, digits = NA))
    same_out <- identical(unlist(old$outputs), vapply(outs, sha256_file, "", USE.NAMES = FALSE))
    if (same_in && same_out) {
      record("compute", "cache hit: inputs, code and outputs unchanged; nothing recomputed")
      return(invisible(FALSE))
    }
  }
  cal <- read_calibration(ctx, opt)
  d <- load_table(ctx)
  rk <- fit_height_rule("main", opt)
  hr <- apply_heights(d, rk, cal, ctx)
  rows <- surface_rows(hr)
  rp <- fromJSON(file.path(p$models, "surface_main", "provenance.json"))
  check("F1/F7: the primary sample is rebuilt as W3.14 fitted it",
        rp$n_rows == nrow(rows) && identical(rp$table_sha256, key$table_sha256) && identical(rp$height_rule_key, rk),
        sprintf("%s rows now, %s in the W3.14 receipt; height rule %s", comma(nrow(rows)), comma(rp$n_rows), rk))
  obj <- readRDS(file.path(p$model, "surface_main.rds"))
  B <- readRDS(file.path(p$model, "draws_vc_main.rds"))
  check("F1: the draws are W3.14's Vc draws of the primary fit",
        identical(attr(B, "covariance"), INTERVAL_COV) && identical(colnames(B), names(stats::coef(obj$m))) &&
          nrow(B) == N_DRAWS, sprintf("%d x %d", nrow(B), ncol(B)))
  m <- obj$m
  aligned <- length(m$y) == nrow(rows) && all(m$y == rows$cs) && max(abs(m$model$x_mid - rows$x_mid)) < 1e-12 &&
    max(abs(m$model$zn - rows$zn)) < 1e-12
  check("F7: the fitted values align row by row with the rebuilt sample", aligned,
        sprintf("%s fitted values; response, x_mid and zn identical", comma(length(m$y))))
  # F7: in-sample calibration by 0.5-inch d bin (the binned estimator's bins, annex 5).
  bins <- data.frame(season = as.integer(rows$season), bin = as.integer(bin_index(rows$d)), cs = rows$cs,
                     fitted = as.numeric(m$fitted.values))
  agg <- bins |>
    group_by(season, bin) |>
    summarise(n = n(), strikes = sum(cs), fitted_sum = sum(fitted), .groups = "drop") |>
    arrange(season, bin) |>
    as.data.frame()
  agg$regime <- unname(REGIME_OF[as.character(agg$season)])
  agg$d_centre <- bin_centre(agg$bin)
  check("F7: 32 bins in every season, every fitted pitch counted once",
        nrow(agg) == N_BINS * length(SEASONS) && sum(agg$n) == nrow(rows),
        sprintf("%d season-bins, %s pitches", nrow(agg), comma(sum(agg$n))))
  write_csv_plain(agg[, c("season", "regime", "bin", "d_centre", "n", "strikes", "fitted_sum")], fp$bins)
  # T1's reconciliation of the W3.5 counts with the fitted sample.
  smp <- data.frame(season = SEASONS,
                    p0_loaded = as.integer(table(factor(d$season, levels = SEASONS))),
                    p0_heights = as.integer(table(factor(hr$season, levels = SEASONS))),
                    surface_rows = as.integer(table(factor(rows$season, levels = SEASONS))),
                    games = vapply(SEASONS, function(s) length(unique(rows$game_pk[rows$season == s])), 0L))
  write_csv_plain(smp, fp$sample)
  # F1: the ray bands.
  t3 <- read_csv_plain(file.path(p$tab, "T3_estimands.csv"))
  ref <- rows[rows$season == as.integer(REF_SEASON), ]
  mix <- ref_mix(m, obj$spec, ref, REF_SEASON)
  res <- lapply(F1_SEASONS, function(s) {
    t0 <- proc.time()
    r <- f1_season(obj, B, mix, s, t3)
    record(sprintf("F1 %s", s), sprintf("%d rays, %.0f s", RAY_K, (proc.time() - t0)[["elapsed"]]))
    r
  })
  write_csv_plain(do.call(rbind, lapply(res, `[[`, "rays")), fp$rays)
  write_csv_plain(do.call(rbind, lapply(res, `[[`, "contour")), fp$contours)
  write_json_file(list(key = key, outputs = as.list(vapply(outs, sha256_file, "", USE.NAMES = FALSE)),
                       written_madrid = madrid_now()), fp$key)
  step_receipt(ctx, rows = rows, seed = DRAW_SEED, suffix = "compute",
               inputs = c(file.path(p$model, "surface_main.rds"), file.path(p$model, "draws_vc_main.rds"),
                          file.path(p$tab, "T3_estimands.csv")),
               outputs = outs)
  invisible(TRUE)
}

## --- render helpers -----------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(ggplot2)
  library(patchwork)
})

theme_fig <- function() {
  theme_minimal(base_size = 7, base_family = "Helvetica") +
    theme(text = element_text(colour = INK),
          axis.text = element_text(colour = INK2, size = 6),
          axis.title = element_text(colour = INK2, size = 6.5),
          panel.grid.major = element_line(colour = GRID, linewidth = 0.25),
          panel.grid.minor = element_blank(),
          axis.ticks = element_line(colour = AXIS, linewidth = 0.25),
          strip.text = element_text(colour = INK, size = 6.5, hjust = 0, face = "bold", margin = margin(2, 0, 2, 0)),
          legend.position = "bottom", legend.title = element_blank(),
          legend.text = element_text(size = 6, colour = INK2),
          legend.key.width = unit(0.7, "cm"), legend.key.height = unit(0.25, "cm"),
          legend.margin = margin(0, 0, 0, 0), legend.box.margin = margin(0, 0, 0, 0),
          plot.title = element_text(size = 6.5, colour = INK, face = "bold", margin = margin(0, 0, 2, 0)),
          plot.margin = margin(3, 5, 3, 3),
          plot.background = element_rect(fill = "white", colour = NA),
          panel.background = element_rect(fill = "white", colour = NA))
}

save_fig <- function(p, id, dest, h_cm) {
  fd <- file.path(dest, "figures")
  ensure_dir(fd)
  png <- file.path(fd, paste0(id, ".png"))
  pdf <- file.path(fd, paste0(id, ".pdf"))
  ggsave(png, p, width = FIG_W_CM, height = h_cm, units = "cm", dpi = 600, device = ragg::agg_png, bg = "white")
  ggsave(pdf, p, width = FIG_W_CM, height = h_cm, units = "cm", device = grDevices::cairo_pdf, bg = "white")
  c(png = png, pdf = pdf)
}

const_rows <- function(fig, v) {
  data.frame(figure = fig, element = "constant", key = names(v), value = unname(as.numeric(v)), stringsAsFactors = FALSE)
}

# Every number a caption or alt text prints, as the test reads it: a signed or unsigned decimal,
# thousands commas allowed; ids glued to letters (F1, CH1-A6, D-21, W3.23, P1), years 1900 to 2039
# and the parts of ISO dates are labels, not numbers.
num_tokens <- function(txt) {
  txt <- gsub("−", "-", txt, fixed = TRUE)
  m <- gregexpr("(?<![A-Za-z0-9_.\\-])-?[0-9][0-9,]*(\\.[0-9]+)?(?![A-Za-z0-9_])", txt, perl = TRUE)
  tok <- sub(",+$", "", regmatches(txt, m)[[1]])
  tok <- tok[nzchar(tok)]
  bare <- gsub(",", "", tok)
  year <- grepl("^[0-9]{4}$", bare) & as.numeric(bare) >= 1900 & as.numeric(bare) <= 2039
  tok[!year]
}
untraced <- function(txt, side) {
  vals <- unlist(lapply(side, function(c) if (is.numeric(c)) c[is.finite(c)] else numeric(0)), use.names = FALSE)
  bad <- character(0)
  for (t in num_tokens(txt)) {
    b <- gsub(",", "", t)
    k <- if (grepl(".", b, fixed = TRUE)) nchar(sub("^[^.]*\\.", "", b)) else 0L
    v <- as.numeric(b)
    hit <- if (startsWith(b, "-")) any(abs(round(vals, k) - v) < 1e-9)
           else any(abs(round(abs(vals), k) - v) < 1e-9)
    if (!hit) bad <- c(bad, t)
  }
  bad
}

# L* of each colour, for the manifest's grayscale gap.
lstar <- function(hex) farver::convert_colour(t(grDevices::col2rgb(hex)), "rgb", "lab")[, "l"]
min_lgap <- function(hex) {
  hex <- unique(hex)
  if (length(hex) < 2L) return(NA_real_)
  l <- sort(lstar(hex))
  min(diff(l))
}
f_d <- function(x, d) formatC(x, format = "f", digits = d)

# Annex 8.7's three unmet recovery clauses, parsed from T4's recovery_disclosure column. A change in
# that wording stops the run rather than printing a stale count.
recovery_counts <- function(p) {
  t4 <- read_csv_plain(file.path(p$tab, "T4_decomposition.csv"))
  txt <- function(e) {
    x <- unique(t4$recovery_disclosure[t4$estimand == e & !is.na(t4$recovery_disclosure) & nzchar(t4$recovery_disclosure)])
    if (length(x) != 1L) die("T4 carries ", length(x), " recovery_disclosure texts for ", e, "; annex 8.7 gives one")
    x
  }
  m1 <- regmatches(txt("top_in"), regexec(paste0(
    "covered the truth in ([0-9]+) of ([0-9]+) injected replicates \\(bound ([0-9]+)\\).*",
    "inside \\+/-([0-9.]+) in in ([0-9]+) of ([0-9]+) \\(bound ([0-9]+)\\)"), txt("top_in")))[[1]]
  m2 <- regmatches(txt("half_width_in"), regexec("covered zero in ([0-9]+) of ([0-9]+) replicates \\(bound ([0-9]+)\\)",
                                                  txt("half_width_in")))[[1]]
  if (length(m1) != 8L || length(m2) != 4L) die("T4's recovery_disclosure no longer reads as annex 8.7's three clauses")
  stats::setNames(as.numeric(c(m1[-1], m2[-1])),
                  c("top_cover_hits", "top_cover_n", "top_cover_bound", "top_null_margin_in", "top_null_hits",
                    "top_null_n", "top_null_bound", "hw_null_hits", "hw_null_n", "hw_null_bound"))
}

# The caption sentences annex 8.7 requires beside top-edge and half-width numbers.
recovery_caption <- function(rc) {
  paste0(
    " Top-edge caveat (annex 8.7, D-R0-04): every top-edge interval here is read as slightly too narrow. ",
    "In the synthetic recovery the top edge's 95% interval covered the truth in ", rc[["top_cover_hits"]], " of ",
    rc[["top_cover_n"]], " replicates, against a bound of ", rc[["top_cover_bound"]], ". Its null 90% interval lay ",
    "within ", f_d(rc[["top_null_margin_in"]], 2), " in of zero for ", rc[["top_null_hits"]], " of ", rc[["top_null_n"]],
    ", against ", rc[["top_null_bound"]], ", so a top-edge equivalence reading is underpowered. Half-width shortfall ",
    "(annex 8.7): its null 90% interval covered zero in ", rc[["hw_null_hits"]], " of ", rc[["hw_null_n"]],
    " replicates, against a bound of ", rc[["hw_null_bound"]], ".")
}
recovery_rows <- function(fig, rc) const_rows(fig, c(rc, recovery_ci_pct = 95, recovery_null_ci_pct = 90, annex_section = 8.7))

## --- F1 ----------------------------------------------------------------------------------------

rounded_rect <- function(hw, bot, top, r, n = 16L) {
  arc <- function(cx, cz, a0) {
    a <- seq(a0, a0 + pi / 2, length.out = n)
    data.frame(x = cx + r * cos(a), y = cz + r * sin(a))
  }
  out <- rbind(arc(hw, top, 0), arc(-hw, top, pi / 2), arc(-hw, bot, pi), arc(hw, bot, 3 * pi / 2))
  rbind(out, out[1, ])
}

fig_f1 <- function(p) {
  fp <- fig_paths(p)
  rc <- recovery_counts(p)
  rays <- read_csv_plain(fp$rays)
  cont <- read_csv_plain(fp$contours)
  t3 <- read_csv_plain(file.path(p$tab, "T3_estimands.csv"))
  t3 <- t3[t3$fit == "main" & t3$season %in% as.integer(F1_SEASONS), ]
  a <- rays$angle_deg * pi / 180
  # Each band is one simple polygon: the outer ring forward, then the inner ring backward, joined
  # at the first ray, so no polygon carries a hole.
  band <- do.call(rbind, lapply(split(seq_len(nrow(rays)), rays$season), function(i) {
    i <- i[order(rays$ray[i])]
    o <- data.frame(x = rays$r_hi95[i] * cos(a[i]), y = ZC_IN + rays$r_hi95[i] * sin(a[i]))
    n <- data.frame(x = rays$r_lo95[i] * cos(a[i]), y = ZC_IN + rays$r_lo95[i] * sin(a[i]))
    data.frame(season = rays$season[i[1]], regime = rays$regime[i[1]],
               rbind(o, o[1, ], n[1, ], n[rev(seq_len(nrow(n))), ]))
  }))
  lab <- setNames(sprintf("%s, %s", F1_SEASONS, c("pre-buffer", "buffer cut", "ABS")), REGIME_OF[F1_SEASONS])
  for (df in c("band", "cont")) {
    x <- get(df)
    x$regime <- factor(x$regime, levels = names(REGIME_COL))
    assign(df, x)
  }
  hw <- PLATE_HALF_W_FT * 12
  zb <- ABS_BOT_FRAC * REF_HEIGHT_IN; zt <- ABS_TOP_FRAC * REF_HEIGHT_IN
  rect <- data.frame(x = c(-hw, hw, hw, -hw, -hw), y = c(zb, zb, zt, zt, zb))
  ball <- rounded_rect(hw, zb, zt, BALL_R_IN)
  pt <- function(e) t3$point[t3$estimand == e]
  win <- list(top = c(-6, 6, min(pt("top_in")) - 1.2, max(pt("top_in")) + 1.2),
              bottom = c(-6, 6, min(pt("bot_in")) - 1.2, max(pt("bot_in")) + 1.2),
              side = c(min(pt("half_width_in")) - 1.2, max(pt("half_width_in")) + 1.2, ZC_IN - 6, ZC_IN + 6))
  base <- function() {
    ggplot() +
      geom_polygon(data = band, aes(x, y, group = regime, fill = regime), alpha = 0.35) +
      geom_path(data = rect, aes(x, y), colour = INK2, linewidth = 0.35) +
      geom_path(data = ball, aes(x, y), colour = MUTED, linewidth = 0.3, linetype = "11") +
      geom_path(data = cont, aes(x_in, z_in, group = regime, colour = regime, linetype = regime), linewidth = 0.45) +
      scale_fill_manual(values = REGIME_COL, labels = lab, name = NULL) +
      scale_colour_manual(values = REGIME_COL, labels = lab, name = NULL) +
      scale_linetype_manual(values = REGIME_LT, labels = lab, name = NULL) +
      theme_fig()
  }
  main <- base() + coord_equal(xlim = c(-13, 13), ylim = c(14, 44), expand = FALSE) +
    labs(x = "Horizontal position, in (catcher's view)", y = "Height, in (72-in batter)")
  zoom <- function(w, ttl) {
    base() + coord_cartesian(xlim = w[1:2], ylim = w[3:4], expand = FALSE) + labs(title = ttl, x = NULL, y = NULL) +
      theme(legend.position = "none", axis.text = element_text(size = 5.5))
  }
  pl <- main / (zoom(win$top, "Top edge") | zoom(win$bottom, "Bottom edge") | zoom(win$side, "Side edge")) +
    plot_layout(heights = c(3.3, 1), guides = "collect") & theme(legend.position = "bottom")
  consts <- c(contour_pct = 50, batter_height_in = REF_HEIGHT_IN, ci_pct = 95, n_rays = RAY_K, n_draws = N_DRAWS,
              plate_width_in = 2 * hw, abs_bot_pct = 100 * ABS_BOT_FRAC, abs_top_pct = 100 * ABS_TOP_FRAC,
              ball_radius_in = BALL_R_IN, ray_window_in = RAY_HALF)
  side <- dplyr::bind_rows(
    data.frame(figure = "F1", element = "ray", season = rays$season, regime = rays$regime, key = as.character(rays$ray),
               x = rays$angle_deg, value = rays$r_point, lo95 = rays$r_lo95, hi95 = rays$r_hi95,
               median = rays$r_median, r_contour = rays$r_contour, n = rays$n_complete, stringsAsFactors = FALSE),
    data.frame(figure = "F1", element = "contour", season = cont$season, regime = as.character(cont$regime),
               key = as.character(cont$vertex), x = cont$x_in, y = cont$z_in, stringsAsFactors = FALSE),
    data.frame(figure = "F1", element = "abs_rectangle", key = as.character(seq_len(nrow(rect))), x = rect$x, y = rect$y),
    data.frame(figure = "F1", element = "ball_boundary", key = as.character(seq_len(nrow(ball))), x = ball$x, y = ball$y),
    data.frame(figure = "F1", element = "zoom_window", key = names(win), xmin = vapply(win, `[`, 0, 1),
               xmax = vapply(win, `[`, 0, 2), ymin = vapply(win, `[`, 0, 3), ymax = vapply(win, `[`, 0, 4)),
    data.frame(figure = "F1", element = "edge", season = t3$season, regime = t3$regime, key = t3$estimand,
               value = t3$point, lo95 = t3$lo95, hi95 = t3$hi95, stringsAsFactors = FALSE),
    const_rows("F1", consts), recovery_rows("F1", rc))
  e <- function(s, k) t3$point[t3$season == s & t3$estimand == k]
  caption <- paste0(
    "Contours where the called-strike probability is 50% for a 72-inch batter, standardised to the 2024 pitch mix, ",
    "in 2024 (pre-buffer), 2025 (buffer cut) and 2026 (ABS challenge). Shading is the pointwise 95% interval of ",
    "the contour along 120 rays from the zone centre, from 1,000 coefficient draws. The grey rectangle is the ABS ",
    "zone, 17 in wide and 27% to 53.5% of height; the dotted line is where the ball touches it, 1.45 in outside. ",
    "The lower panels enlarge the top, bottom and side edges and do not keep the aspect ratio.", recovery_caption(rc))
  alt <- paste0(
    "Three nested closed curves over a strike-zone rectangle, lightest for 2024 and darkest for 2026. ",
    "The 2026 curve's top edge sits at ", f_d(e(2026, "top_in"), 1), " in against ", f_d(e(2024, "top_in"), 1),
    " in for 2024, and its bottom edge at ", f_d(e(2026, "bot_in"), 1), " in against ", f_d(e(2024, "bot_in"), 1),
    " in. Its half-width is ", f_d(e(2026, "half_width_in"), 1), " in against ", f_d(e(2024, "half_width_in"), 1),
    " in. In 2025 the three are ", f_d(e(2025, "top_in"), 1), ", ", f_d(e(2025, "bot_in"), 1), " and ",
    f_d(e(2025, "half_width_in"), 1), " in. The interval bands are thin, visible mainly in the enlarged edge panels.")
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 13.2, palette = unname(REGIME_COL))
}

## --- F2 ----------------------------------------------------------------------------------------

EST_GEOM <- c("top_in", "bot_in", "half_width_in", "area_sqin")
EST_LAB <- c(top_in = "Top edge (in)", bot_in = "Bottom edge (in)", half_width_in = "Half-width (in)",
             area_sqin = "Area (sq in)")

fig_f2 <- function(p) {
  t4 <- read_csv_plain(file.path(p$tab, "T4_decomposition.csv"))
  t4 <- t4[t4$fit == "main", ]
  pc <- read_csv_plain(file.path(p$tab, "T4_plane_component.csv"))
  rows <- list()
  for (e in EST_GEOM) {
    r <- function(cmp) t4[t4$estimand == e & t4$component == cmp, ]
    g <- r("g"); b <- r("delta_buffer"); a <- r("delta_abs"); tot <- r("delta_total")
    pl <- pc[pc$estimand == e, ]
    if (nrow(g) != 1L || nrow(b) != 1L || nrow(a) != 1L || nrow(tot) != 1L || nrow(pl) != 1L) die("F2: T4 rows missing for ", e)
    resid <- b$point + a$point + 2 * g$point - tot$point
    check(sprintf("F2 %s: Delta_buffer + Delta_ABS + 2g == Delta_total", e), abs(resid) < 1e-9, sprintf("residual %.1e", resid))
    s1 <- 2 * g$point; s2 <- s1 + b$point
    rows[[e]] <- data.frame(
      figure = "F2", element = "bar", estimand = e, units = tot$units,
      key = c("trend_2g", "delta_buffer", "delta_abs", "delta_total", "plane"),
      label = c("2g", "Buffer", "ABS", "Total", "Plane"),
      pos = c(1, 2, 3, 4, 5.5),
      start = c(0, s1, s2, 0, 0),
      end = c(s1, s2, tot$point, tot$point, pl$point),
      value = c(2 * g$point, b$point, a$point, tot$point, pl$point),
      lo95 = c(2 * g$lo95, b$lo95, a$lo95, tot$lo95, pl$lo95),
      hi95 = c(2 * g$hi95, b$hi95, a$hi95, tot$hi95, pl$hi95),
      in_sum = c(TRUE, TRUE, TRUE, FALSE, FALSE),
      identity_residual = resid, stringsAsFactors = FALSE)
  }
  d <- do.call(rbind, rows)
  d$whisk_lo <- ifelse(d$key %in% c("delta_buffer", "delta_abs"), d$start + d$lo95, d$lo95)
  d$whisk_hi <- ifelse(d$key %in% c("delta_buffer", "delta_abs"), d$start + d$hi95, d$hi95)
  d$fill <- ifelse(d$key == "delta_total", "total", ifelse(d$key == "plane", "plane", "component"))
  d$panel <- factor(EST_LAB[d$estimand], levels = EST_LAB)
  fills <- c(component = B450, total = B650, plane = LIGHT)
  pl <- ggplot(d) +
    geom_hline(yintercept = 0, colour = INK2, linewidth = 0.25) +
    geom_vline(xintercept = 4.75, colour = AXIS, linewidth = 0.25) +
    geom_rect(aes(xmin = pos - 0.32, xmax = pos + 0.32, ymin = pmin(start, end), ymax = pmax(start, end), fill = fill)) +
    geom_segment(aes(x = pos, xend = pos, y = whisk_lo, yend = whisk_hi), colour = INK, linewidth = 0.35) +
    scale_fill_manual(values = fills, guide = "none") +
    scale_x_continuous(breaks = c(1, 2, 3, 4, 5.5), labels = c("2g", "Buffer", "ABS", "Total", "Plane")) +
    facet_wrap(~panel, ncol = 2, scales = "free_y") +
    labs(x = NULL, y = "Change, 2024 to 2026") +
    theme_fig() + theme(panel.grid.major.x = element_blank(), axis.text.x = element_text(size = 5.5))
  rc <- recovery_counts(p)
  side <- dplyr::bind_rows(d[, setdiff(names(d), c("panel", "fill"))], const_rows("F2", c(ci_pct = 95)),
                           recovery_rows("F2", rc))
  v <- function(e, k, dg) f_d(d$value[d$estimand == e & d$key == k], dg)
  mv <- function(e) {
    x <- d$value[d$estimand == e & d$key == "delta_total"]
    paste(if (x < 0) "moves down by" else "moves up by", f_d(abs(x), 2))
  }
  caption <- paste0(
    "The change from 2024 to 2026 in each edge and in area, split by the identity Total = 2g + Buffer + ABS. ",
    "2g is two seasons of the 2022 to 2024 trend; Buffer and ABS are the departures from that trend in 2025 and ",
    "2026 (Delta_buffer and Delta_ABS). Each of those bars starts where the one before it ends, and whiskers are 95% ",
    "intervals. Plane, right of the rule, is the mechanical plate-plane component of 2025, the mid-plate contour ",
    "minus the front-plate contour. It sits outside the sum, because the decomposition uses mid-plate coordinates in ",
    "every season; it is what a front-plate 2025 against mid-plate 2026 comparison adds. F2b shows the drop between ",
    "the two planes by pitch type. Placebo P1 failed, so the components describe departures and name no cause.",
    recovery_caption(rc))
  alt <- paste0(
    "Four small bar charts, one each for the top edge, bottom edge, half-width and area. In area, Buffer is ",
    v("area_sqin", "delta_buffer", 1), " sq in and ABS ", v("area_sqin", "delta_abs", 1), " sq in, for a total of ",
    v("area_sqin", "delta_total", 1), " sq in, while the separate plane bar is ", v("area_sqin", "plane", 1),
    " sq in. The top edge ", mv("top_in"), " in in total and the bottom edge ", mv("bot_in"),
    " in; the plane bars are ", v("top_in", "plane", 2), " in at the top and ", v("bot_in", "plane", 2), " in at the bottom.")
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 9, palette = unname(fills))
}

## --- F2b ---------------------------------------------------------------------------------------

# W3.17's front-to-middle dz table, one row per pitch type, 2025 called pitches after the primary
# height rule. dz is z at mid-plate minus z at the front, in inches, so a drop is negative.
PITCH_NAME <- c(FF = "Four-seam", SI = "Sinker", FC = "Cutter", CH = "Changeup", ST = "Sweeper", SL = "Slider",
                FS = "Splitter", SV = "Slurve", CS = "Slow curve", FO = "Forkball", KC = "Knuckle curve",
                CU = "Curveball")
dz_path <- function(p) file.path(p$fig, "F_dz_by_pitch_type.csv")

fig_f2b <- function(p) {
  d <- read_csv_plain(dz_path(p))
  need <- c("pitch_type", "n", "mean_velo_mph", "mean_dz_in", "sd_dz_in", "p05_dz_in", "p25_dz_in", "p50_dz_in",
            "p75_dz_in", "p95_dz_in")
  if (!all(need %in% names(d))) die("F2b: W3.17's dz table lacks ", paste(setdiff(need, names(d)), collapse = ", "))
  check("F2b: W3.17's dz table has ordered quantiles on every row",
        nrow(d) > 0L && all(d$p05_dz_in <= d$p25_dz_in & d$p25_dz_in <= d$p50_dz_in & d$p50_dz_in <= d$p75_dz_in &
                              d$p75_dz_in <= d$p95_dz_in),
        sprintf("%d pitch types, %s pitches", nrow(d), comma(sum(d$n))))
  d <- d[order(-d$p50_dz_in, d$pitch_type), ]
  nm <- ifelse(d$pitch_type %in% names(PITCH_NAME), PITCH_NAME[d$pitch_type], d$pitch_type)
  d$label <- sprintf("%s (%s)", nm, d$pitch_type)
  d$row <- factor(d$label, levels = rev(d$label))
  pl <- ggplot(d, aes(y = row)) +
    geom_vline(xintercept = 0, colour = INK2, linewidth = 0.25) +
    geom_linerange(aes(xmin = p05_dz_in, xmax = p95_dz_in), colour = B450, linewidth = 0.35) +
    geom_linerange(aes(xmin = p25_dz_in, xmax = p75_dz_in), colour = B450, linewidth = 1.5) +
    geom_point(aes(x = p50_dz_in), shape = 21, size = 1.6, fill = B650, colour = "white", stroke = 0.5) +
    scale_x_continuous(breaks = seq(-2, 0, by = 0.5), limits = c(min(-2, floor(2 * min(d$p05_dz_in)) / 2), 0.05),
                       expand = expansion(mult = c(0.01, 0.01))) +
    labs(x = "dz, in: height at mid-plate minus height at the front", y = NULL) +
    theme_fig() + theme(panel.grid.major.y = element_blank())
  side <- dplyr::bind_rows(
    data.frame(figure = "F2b", element = "pitch_type", key = d$pitch_type, label = nm, n = d$n, x = d$mean_velo_mph,
               value = d$p50_dz_in, mean = d$mean_dz_in, sd = d$sd_dz_in, p05 = d$p05_dz_in, p25 = d$p25_dz_in,
               p75 = d$p75_dz_in, p95 = d$p95_dz_in, source = "out/ch1/fig/F_dz_by_pitch_type.csv (W3.17)",
               stringsAsFactors = FALSE),
    const_rows("F2b", c(n_pitch_types = nrow(d), n_pitches = sum(d$n), pct_lo = 5, pct_q1 = 25, pct_median = 50,
                        pct_q3 = 75, pct_hi = 95)))
  hi <- d[1, ]; lo <- d[nrow(d), ]
  nm1 <- function(r) tolower(ifelse(r$pitch_type %in% names(PITCH_NAME), PITCH_NAME[[r$pitch_type]], r$pitch_type))
  q <- function(r) sprintf("median %s in (IQR %s to %s)", f_d(r$p50_dz_in, 2), f_d(r$p25_dz_in, 2), f_d(r$p75_dz_in, 2))
  caption <- paste0(
    "The drop in the ball's height between the front of the plate and mid-plate, dz, for ", comma(sum(d$n)),
    " 2025 called pitches by pitch type, from W3.17's plane table. Each dot is the median, the thick bar the ",
    "interquartile range and the thin bar the 5th to 95th percentiles. Rows run from the smallest median drop to ",
    "the largest. The ", nm1(hi), " (", hi$pitch_type, ") drops least, ", q(hi), ", and the ", nm1(lo), " (",
    lo$pitch_type, ") most, ", q(lo), ". This is the by-pitch-type figure D-56 and CH1-A13 ask for; the per-edge ",
    "plane component is F2's Plane bar and T4's plane row.")
  alt <- paste0(
    "A dot-and-bar chart with one row per pitch type, ", nrow(d), " rows. Medians run from ", f_d(hi$p50_dz_in, 2),
    " in for the ", nm1(hi), " at the top to ", f_d(lo$p50_dz_in, 2), " in for the ", nm1(lo), " at the bottom. ",
    if (all(d$p95_dz_in < 0)) "Every bar lies left of zero, so every pitch type drops between the two planes."
    else "Some bars reach zero.")
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 7, palette = B450)
}

## --- F3 ----------------------------------------------------------------------------------------

EST_EDGE <- c("top_in", "bot_in", "half_width_in")

fig_f3 <- function(p) {
  dr <- read_csv_plain(file.path(p$model, "estimand_draws_main.csv"))
  t3 <- read_csv_plain(file.path(p$tab, "T3_estimands.csv"))
  t3 <- t3[t3$fit == "main", ]
  t4 <- read_csv_plain(file.path(p$tab, "T4_decomposition.csv"))
  t4 <- t4[t4$fit == "main", ]
  t5 <- read_csv_plain(file.path(p$tab, "T5_placebos.csv"))
  pts <- list()
  for (e in EST_EDGE) for (s in SEASON_LEVELS) {
    dd <- dr[[paste(s, e, sep = "_")]] - dr[[paste(REF_SEASON, e, sep = "_")]]
    q <- if (s == REF_SEASON) c(0, 0) else qint(dd, 0.95)
    pts[[length(pts) + 1L]] <- data.frame(
      figure = "F3", element = "season", estimand = e, season = as.integer(s), regime = REGIME_OF[[s]],
      value = t3$point[t3$estimand == e & t3$season == as.integer(s)] -
        t3$point[t3$estimand == e & t3$season == as.integer(REF_SEASON)],
      lo95 = q[1], hi95 = q[2], n = sum(is.finite(dd)), stringsAsFactors = FALSE)
  }
  d <- do.call(rbind, pts)
  g <- t4[t4$component == "g" & t4$estimand %in% EST_EDGE, c("estimand", "point")]
  tr <- do.call(rbind, lapply(EST_EDGE, function(e) {
    data.frame(figure = "F3", element = "trend", estimand = e, season = 2024:2026,
               value = g$point[g$estimand == e] * (0:2), stringsAsFactors = FALSE)
  }))
  mk <- data.frame(figure = "F3", element = "boundary", key = c("P1 placebo", "Buffer cut", "ABS"),
                   x = c(2023.5, 2024.5, 2025.5), note = c("placebo", "regime", "regime"), stringsAsFactors = FALSE)
  p1 <- t5[t5$placebo == "P1", ]
  p1d <- data.frame(figure = "F3", element = "p1", key = p1$quantity, value = p1$estimate, lo90 = p1$lo, hi90 = p1$hi,
                    margin = p1$margin_or_threshold, note = p1$verdict, stringsAsFactors = FALSE)
  d$panel <- factor(EST_LAB[d$estimand], levels = EST_LAB[EST_EDGE])
  tr$panel <- factor(EST_LAB[tr$estimand], levels = EST_LAB[EST_EDGE])
  lab <- mk
  lab$panel <- factor(EST_LAB[["top_in"]], levels = EST_LAB[EST_EDGE])
  ytop <- max(c(d$hi95[d$estimand == "top_in"], tr$value[tr$estimand == "top_in"])) + 0.1
  pl <- ggplot(d, aes(season, value)) +
    geom_hline(yintercept = 0, colour = AXIS, linewidth = 0.25) +
    geom_vline(data = mk[mk$note == "regime", ], aes(xintercept = x), colour = INK2, linewidth = 0.3) +
    geom_vline(data = mk[mk$note == "placebo", ], aes(xintercept = x), colour = INK2, linewidth = 0.35, linetype = "11") +
    geom_label(data = lab, aes(x = x, y = ytop, label = key), inherit.aes = FALSE, size = 5.5 / .pt, colour = INK2,
               fill = "white", linewidth = 0, label.padding = unit(0.6, "pt"), hjust = 0.5, vjust = 0.5) +
    geom_line(data = tr, aes(season, value), colour = MUTED, linewidth = 0.4, linetype = "42") +
    geom_errorbar(aes(ymin = lo95, ymax = hi95), width = 0, colour = B450, linewidth = 0.45) +
    geom_point(colour = B450, size = 1.4) +
    scale_x_continuous(breaks = SEASONS, limits = c(2021.6, 2026.4)) +
    scale_y_continuous(expand = expansion(mult = c(0.08, 0.14))) +
    facet_wrap(~panel, ncol = 1, scales = "free_y") +
    labs(x = NULL, y = "Change from 2024, in") +
    theme_fig() + theme(panel.grid.major.x = element_blank())
  rc <- recovery_counts(p)
  side <- dplyr::bind_rows(d[, setdiff(names(d), "panel")], tr[, setdiff(names(tr), "panel")], mk, p1d,
                           const_rows("F3", c(ci_pct = 95, batter_height_in = REF_HEIGHT_IN)), recovery_rows("F3", rc))
  v <- function(e, s) f_d(d$value[d$estimand == e & d$season == s], 2)
  caption <- paste0(
    "Each edge's change from 2024 by season, for a 72-inch batter, with 95% intervals from the joint coefficient ",
    "draws. The dotted rule is the 2023 to 2024 placebo boundary (P1), where no rule changed; the solid rules are ",
    "the 2025 buffer cut and the 2026 ABS challenge. The dashed line extends the 2024 level by the 2022 to 2024 ",
    "trend. P1 fails its equivalence test on area and on the shadow rate (T5), so the departures after 2024 are ",
    "descriptive.", recovery_caption(rc))
  alt <- paste0(
    "Three stacked panels of five season points each, for the top edge, the bottom edge and the half-width. ",
    "The top edge is ", v("top_in", 2023), " in from its 2024 level in 2023 and ", v("top_in", 2026),
    " in in 2026; the bottom edge is ", v("bot_in", 2026), " in in 2026; the half-width is ",
    v("half_width_in", 2026), " in in 2026.")
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 11, palette = B450)
}

## --- F4 ----------------------------------------------------------------------------------------

TAU_MATERIAL <- 0.20   # CH1-A6, annex 8.5

fig_f4 <- function(p) {
  suppressPackageStartupMessages({
    library(brms)
    library(posterior)
  })
  fit <- readRDS(file.path(p$model, "umpire_me.rds"))
  dat <- fit$data
  u25 <- unique(as.character(dat$umpire_hp_id[dat$buf_step == 1 & dat$abs_step == 0]))
  u26 <- unique(as.character(dat$umpire_hp_id[dat$abs_step == 1]))
  both <- intersect(u25, u26)
  dm <- posterior::as_draws_matrix(fit, variable = "^r_umpire_hp_id\\[.*,abs_step\\]$", regex = TRUE)
  ids <- sub("^r_umpire_hp_id\\[(.*),abs_step\\]$", "\\1", colnames(dm))
  dm <- dm[, ids %in% both, drop = FALSE]
  q <- function(v, pr) unname(stats::quantile(v, pr, type = 7))
  st <- data.frame(median = apply(dm, 2, stats::median), lo90 = apply(dm, 2, q, 0.05), hi90 = apply(dm, 2, q, 0.95),
                   lo95 = apply(dm, 2, q, 0.025), hi95 = apply(dm, 2, q, 0.975))
  st <- st[order(st$median, st$lo90, st$hi90), ]
  st$rank <- seq_len(nrow(st))
  rownames(st) <- NULL
  tau <- as.numeric(posterior::as_draws_matrix(fit, variable = "sd_umpire_hp_id__abs_step"))
  t6 <- read_csv_plain(file.path(p$tab, "T6_heterogeneity.csv"))
  t6m <- t6$median[t6$fit == "sop" & t6$quantity == "tau_abs"]
  p_ge <- mean(tau >= TAU_MATERIAL)
  t6p <- t6$median[t6$fit == "CH1-A6" & t6$quantity == "p_tau_ge_020"]
  check("F4: 88-umpire panel of W3.18's 2025 and 2026 cells", length(both) == nrow(st) && nrow(st) > 0L,
        sprintf("%d umpires with both seasons (%d with 2025, %d with 2026)", nrow(st), length(u25), length(u26)))
  check("F4: the tau inset is T6's sop posterior", abs(stats::median(tau) - t6m) < 1e-6 && abs(p_ge - t6p) < 1e-12,
        sprintf("median %.6f against T6 %.6f; P(tau >= %.2f) %.3f against %.3f", stats::median(tau), t6m,
                TAU_MATERIAL, p_ge, t6p))
  den <- stats::density(tau, from = 0, to = max(0.25, q(tau, 0.999)), n = 256)
  n_excl <- sum(st$lo90 > 0 | st$hi90 < 0)
  tq <- q(tau, c(0.025, 0.975))
  main <- ggplot(st, aes(rank, median)) +
    geom_hline(yintercept = 0, colour = INK2, linewidth = 0.25) +
    geom_errorbar(aes(ymin = lo90, ymax = hi90), width = 0, colour = B450, linewidth = 0.3) +
    geom_point(colour = B650, size = 0.55) +
    scale_y_continuous(breaks = c(-0.1, 0, 0.1), limits = c(min(st$lo90) - 0.01, max(st$hi90) + 0.32)) +
    labs(x = "Umpires, ranked by posterior median (names withheld)", y = "2025 to 2026 response vs league, in") +
    theme_fig() + theme(panel.grid.major.x = element_blank())
  dd <- data.frame(x = den$x, y = den$y)
  inset <- ggplot(dd, aes(x, y)) +
    geom_area(fill = B450, alpha = 0.15) +
    geom_line(colour = B450, linewidth = 0.4) +
    geom_vline(xintercept = TAU_MATERIAL, colour = INK2, linewidth = 0.3, linetype = "22") +
    annotate("text", x = TAU_MATERIAL, y = max(dd$y) * 0.95, label = "0.20 in", hjust = -0.1, size = 5 / .pt,
             colour = INK2) +
    scale_x_continuous(breaks = c(0, 0.1, 0.2)) +
    labs(title = "tau, between-umpire SD (in)", x = NULL, y = NULL) +
    theme_fig() +
    theme(axis.text.y = element_blank(), axis.ticks.y = element_blank(), panel.grid.major = element_blank(),
          axis.text.x = element_text(size = 5), plot.title = element_text(size = 5.5, face = "plain"),
          plot.background = element_rect(fill = "white", colour = GRID, linewidth = 0.25),
          plot.margin = margin(2, 3, 1, 2))
  pl <- main + inset_element(inset, left = 0.02, bottom = 0.62, right = 0.5, top = 1, align_to = "panel")
  side <- dplyr::bind_rows(
    data.frame(figure = "F4", element = "umpire", key = as.character(st$rank), value = st$median, lo90 = st$lo90,
               hi90 = st$hi90, lo95 = st$lo95, hi95 = st$hi95, stringsAsFactors = FALSE),
    data.frame(figure = "F4", element = "tau_density", key = as.character(seq_along(den$x)), x = den$x, y = den$y),
    data.frame(figure = "F4", element = "tau", key = c("tau_abs", "p_tau_ge_020"),
               value = c(stats::median(tau), p_ge), lo95 = c(tq[1], NA), hi95 = c(tq[2], NA),
               n = length(tau), stringsAsFactors = FALSE),
    const_rows("F4", c(ci_pct_umpire = 90, ci_pct_tau = 95, n_umpires = nrow(st), tau_material_in = TAU_MATERIAL,
                       n_excluding_zero_90 = n_excl)))
  caption <- paste0(
    "Each umpire's 2025 to 2026 response relative to the league's, in inches, as a posterior median with a 90% ",
    "interval from W3.18's primary model, for the ", nrow(st), " umpires with cells in both seasons, ranked. ",
    "No umpire is named: CH1-A6's reliability gate was not met, so under D-21 no per-umpire row is published. ",
    "The inset is the posterior of tau, the between-umpire SD of the response. Its rule marks CH1-A6's ",
    "materiality threshold, 0.20 in, and P(tau >= 0.20 in) is ", f_d(p_ge, 3), ".")
  alt <- paste0(
    "A caterpillar plot of ", nrow(st), " short vertical intervals, ranked from lowest to highest, centred close to ",
    "zero; ", n_excl, " of the 90% intervals exclude zero. An inset density of tau has a median of ",
    f_d(stats::median(tau), 3), " in, and ", if (p_ge < 0.05) "lies almost entirely left of" else "extends past",
    " the 0.20 in threshold.")
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 8, palette = B450)
}

## --- F6 ----------------------------------------------------------------------------------------

fig_f6 <- function(p) {
  fr <- read_csv_plain(file.path(p$tab, "framing_catcher_seasons.csv"))
  fr <- fr[fr$window == "season" & fr$qualified %in% c(TRUE, "TRUE"), ]
  fr$regime <- factor(fr$regime, levels = names(REGIME_COL))
  fr <- fr[order(fr$regime, fr$runs_cnt_per100, fr$season, fr$catcher), ]
  fr$rk <- stats::ave(seq_len(nrow(fr)), fr$regime, FUN = seq_along)
  fr$ypos <- 4 - as.integer(fr$regime) + ((fr$rk * 0.6180339887) %% 1 - 0.5) * 0.36
  sm <- do.call(rbind, lapply(levels(fr$regime), function(r) {
    v <- fr$runs_cnt_per100[fr$regime == r]
    qq <- unname(stats::quantile(v, c(0.25, 0.5, 0.75), type = 7))
    data.frame(regime = r, n = length(v), q25 = qq[1], median = qq[2], q75 = qq[3], iqr = qq[3] - qq[1],
               min = min(v), max = max(v), stringsAsFactors = FALSE)
  }))
  sm$y <- 4 - match(sm$regime, names(REGIME_COL)) + 0.3
  pl <- ggplot() +
    geom_vline(xintercept = 0, colour = AXIS, linewidth = 0.25) +
    geom_point(data = fr, aes(runs_cnt_per100, ypos), colour = B450, alpha = 0.6, size = 0.7, stroke = 0) +
    geom_segment(data = sm, aes(x = q25, xend = q75, y = y, yend = y), colour = INK, linewidth = 0.6) +
    geom_point(data = sm, aes(median, y), shape = 124, size = 2.6, colour = INK) +
    geom_text(data = sm, aes(x = -Inf, y = y + 0.2, label = sprintf("%s (n = %d)", REGIME_LAB[regime], n)),
              hjust = -0.02, size = 6 / .pt, colour = INK) +
    scale_y_continuous(breaks = NULL, limits = c(0.75, 3.6)) +
    labs(x = "Framing runs per 100 innings vs the league-average catcher", y = NULL) +
    theme_fig() + theme(panel.grid.major.y = element_blank())
  side <- dplyr::bind_rows(
    data.frame(figure = "F6", element = "catcher_season", key = as.character(fr$catcher), season = fr$season,
               regime = as.character(fr$regime), value = fr$runs_cnt_per100, y = fr$ypos, stringsAsFactors = FALSE),
    data.frame(figure = "F6", element = "summary", regime = sm$regime, n = sm$n, q25 = sm$q25, value = sm$median,
               q75 = sm$q75, iqr = sm$iqr, min = sm$min, max = sm$max, stringsAsFactors = FALSE),
    const_rows("F6", c(per_innings = 100)))
  s <- function(r, k, d = 2) f_d(sm[[k]][sm$regime == r], d)
  caption <- paste0(
    "Framing runs per 100 innings for each qualified catcher-season, relative to the league-average catcher of ",
    "its season, from W3.19's catcher-free surface at count-specific run values, with every 2026 pitch kept at its ",
    "original call. The strips hold ", sm$n[1], ", ", sm$n[2], " and ", sm$n[3], " catcher-seasons; the bar above ",
    "each strip spans the interquartile range and the tick marks the median.")
  alt <- paste0(
    "Three horizontal strips of dots, one per regime. The interquartile range is ",
    s("pre_buffer", "iqr"), " runs before the buffer cut, ", s("buffer_2025", "iqr"), " in 2025 and ",
    s("abs_2026", "iqr"), " in 2026, and the medians sit at ", s("pre_buffer", "median"), ", ",
    s("buffer_2025", "median"), " and ", s("abs_2026", "median"), ".")
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 6.5, palette = B450)
}

## --- F7 ----------------------------------------------------------------------------------------

wilson <- function(k, n, z = stats::qnorm(0.975)) {
  ph <- k / n
  den <- 1 + z^2 / n
  c0 <- (ph + z^2 / (2 * n)) / den
  h <- z * sqrt(ph * (1 - ph) / n + z^2 / (4 * n^2)) / den
  cbind(c0 - h, c0 + h)
}

fig_f7 <- function(p) {
  b <- read_csv_plain(fig_paths(p)$bins)
  a <- b |>
    group_by(regime, bin, d_centre) |>
    summarise(n = sum(n), strikes = sum(strikes), fitted_sum = sum(fitted_sum), .groups = "drop") |>
    as.data.frame()
  a$regime <- factor(a$regime, levels = names(REGIME_COL))
  a <- a[order(a$regime, a$bin), ]
  a$observed_pct <- 100 * a$strikes / a$n
  a$fitted_pct <- 100 * a$fitted_sum / a$n
  w <- wilson(a$strikes, a$n)
  a$value <- a$observed_pct - a$fitted_pct
  a$lo95 <- 100 * w[, 1] - a$fitted_pct
  a$hi95 <- 100 * w[, 2] - a$fitted_pct
  a$panel <- factor(REGIME_LAB[as.character(a$regime)], levels = REGIME_LAB)
  n_tot <- sum(a$n)
  worst <- a[which.max(abs(a$value)), ]
  n_cover <- sum(a$lo95 <= 0 & a$hi95 >= 0)
  pl <- ggplot(a, aes(d_centre, value)) +
    geom_hline(yintercept = 0, colour = INK2, linewidth = 0.25) +
    geom_vline(xintercept = 0, colour = AXIS, linewidth = 0.25) +
    geom_errorbar(aes(ymin = lo95, ymax = hi95), width = 0, colour = B450, linewidth = 0.35) +
    geom_point(colour = B450, size = 0.9) +
    scale_x_continuous(breaks = seq(-8, 8, by = 2)) +
    facet_wrap(~panel, ncol = 1) +
    labs(x = "d, ball-centre distance outside the zone edge, in (negative inside)",
         y = "Observed minus fitted, percentage points") +
    theme_fig()
  side <- dplyr::bind_rows(
    data.frame(figure = "F7", element = "bin", regime = as.character(a$regime), key = as.character(a$bin),
               x = a$d_centre, n = a$n, strikes = a$strikes, fitted_pct = a$fitted_pct, observed_pct = a$observed_pct,
               value = a$value, lo95 = a$lo95, hi95 = a$hi95, stringsAsFactors = FALSE),
    const_rows("F7", c(bin_width_in = BIN_W_IN, band_in = D_BAND_IN, ci_pct = 95, n_fitted = n_tot,
                       n_bins = N_BINS, n_intervals_covering_zero = n_cover, n_cells = nrow(a))))
  caption <- paste0(
    "In-sample calibration of the primary surface by 0.5-inch bins of d, the signed distance of the ball centre ",
    "from the zone edge, over +/-8 in. Each point is the observed called-strike rate minus the mean fitted ",
    "probability, in percentage points, with a 95% Wilson interval on the observed rate. ", comma(n_tot), " fitted pitches; the ",
    "fitted probabilities include the umpire effects. Out-of-sample calibration is F8's, on the sealed set.")
  alt <- paste0(
    "Three stacked panels of ", N_BINS, " points each, one per regime, scattered around zero. ", n_cover, " of the ",
    nrow(a), " intervals cover zero. The largest gap is ", f_d(worst$value, 2), " percentage points, at d = ",
    f_d(worst$d_centre, 2), " in, in the ", REGIME_LAB[as.character(worst$regime)], " panel.")
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 10, palette = B450)
}

## --- F5 ----------------------------------------------------------------------------------------

# W3.20's committed outputs. They hold no contour coordinates, so F5 is the two of W3.20's three uses
# that carry an interval per row: the within-week alternation and the 2023 to 2024 pre-trend (DEV-90).
F5_WW_ROWS <- data.frame(
  season_scope = c("pooled", "2023", "2024", "pooled", "pooled", "pooled"),
  edge_scope = c("all", "all", "all", "side", "top", "bot"),
  label = c("Pooled", "2023 only", "2024 only", "Side edge", "Top edge", "Bottom edge"),
  group = c("season", "season", "season", "edge", "edge", "edge"),
  stringsAsFactors = FALSE)
F5_PT_LAB <- c(top_in = "Top edge", bot_in = "Bottom edge", half_width_in = "Half-width", area_sqin = "Area")

fig_f5 <- function(p) {
  ww <- read_csv_plain(file.path(p$tab, "aaa_withinweek.csv"))
  pt <- read_csv_plain(file.path(p$tab, "aaa_pretrend.csv"))
  rc <- recovery_counts(p)
  # Within-week rows, in a fixed order; each must exist exactly once.
  w <- do.call(rbind, lapply(seq_len(nrow(F5_WW_ROWS)), function(i) {
    k <- F5_WW_ROWS[i, ]
    r <- ww[ww$use == "within-week alternation" & as.character(ww$season_scope) == k$season_scope &
              ww$edge_scope == k$edge_scope, ]
    if (nrow(r) != 1L) die("F5: aaa_withinweek.csv has ", nrow(r), " rows for ", k$season_scope, "/", k$edge_scope)
    data.frame(k, r[, c("estimate", "lo95", "hi95", "n_pitches", "n_umpire_weeks", "n_umpires", "changeover_date",
                        "frame_first_date", "frame_last_date")], stringsAsFactors = FALSE)
  }))
  check("F5: every within-week row has an ordered 95% interval",
        all(w$lo95 <= w$estimate & w$estimate <= w$hi95), sprintf("%d rows", nrow(w)))
  # Pre-trend rows: MLB's binned series against the primary AAA window, as aaa.md reports first.
  q <- pt[pt$test == "pre-trend" & pt$mlb_estimator == "binned" & pt$aaa_window == "window", ]
  q <- q[match(names(F5_PT_LAB), q$estimand), ]
  if (anyNA(q$estimand)) die("F5: aaa_pretrend.csv lacks a binned primary-window row for an estimand")
  check("F5: the pre-trend verdict is 'fail' exactly when the 95% interval excludes 0",
        all((q$verdict == "fail") == (q$lo95 > 0 | q$hi95 < 0)), paste(q$estimand, q$verdict, collapse = "; "))
  check("F5: the area pre-trend is W3.20's primary row", isTRUE(as.logical(q$primary[q$estimand == "area_sqin"])),
        "aaa_pretrend.csv primary column")
  # Layout: one row per estimate, a gap between the season rows and the edge rows.
  w$y <- c(8, 7, 6, 4.5, 3.5, 2.5)
  q$panel <- ifelse(q$estimand == "area_sqin", "area", "edge")
  q$label <- unname(F5_PT_LAB[q$estimand])
  q$y <- c(3, 2, 1, 1)
  q$excludes0 <- q$lo95 > 0 | q$hi95 < 0
  q$tag <- ifelse(q$excludes0, "excludes 0", "contains 0")
  pt_x <- function(d) c(min(0, d$lo95), max(0, d$hi95))
  ww_plot <- ggplot(w, aes(y = y)) +
    geom_vline(xintercept = 0, colour = INK2, linewidth = 0.25) +
    geom_linerange(aes(xmin = lo95, xmax = hi95), colour = B450, linewidth = 0.45) +
    geom_point(aes(x = estimate), shape = 21, size = 1.6, fill = B650, colour = "white", stroke = 0.4) +
    scale_y_continuous(breaks = w$y, labels = w$label, limits = c(2, 8.5)) +
    scale_x_continuous(limits = c(0, max(w$hi95) * 1.05), expand = expansion(mult = c(0, 0.02))) +
    labs(title = "Within-week alternation: challenge format minus full ABS", x = "Called-strike rate difference, pp",
         y = NULL) +
    theme_fig() + theme(panel.grid.major.y = element_blank())
  pt_plot <- function(d, ttl, xl) {
    xr <- pt_x(d)
    ggplot(d, aes(y = y)) +
      geom_vline(xintercept = 0, colour = INK2, linewidth = 0.25) +
      geom_linerange(aes(xmin = lo95, xmax = hi95), colour = B450, linewidth = 0.45) +
      geom_point(aes(x = point, fill = tag), shape = 21, size = 1.6, colour = B650, stroke = 0.5) +
      geom_text(aes(x = hi95, label = tag), hjust = -0.15, size = 5.5 / .pt, colour = INK2) +
      scale_fill_manual(values = c(`excludes 0` = B650, `contains 0` = "white"), guide = "none") +
      scale_y_continuous(breaks = d$y, labels = d$label, limits = c(min(d$y) - 0.5, max(d$y) + 0.5)) +
      scale_x_continuous(limits = c(xr[1], xr[2] + 0.35 * diff(xr)), expand = expansion(mult = c(0.03, 0))) +
      labs(title = ttl, x = xl, y = NULL) +
      theme_fig() + theme(panel.grid.major.y = element_blank())
  }
  pe <- pt_plot(q[q$panel == "edge", ], "Pre-trend, 2023 to 2024: MLB change minus AAA change", "in")
  pa <- pt_plot(q[q$panel == "area", ], NULL, "sq in")
  pl <- ww_plot / pe / pa + plot_layout(heights = c(5, 2.6, 0.9))
  side <- dplyr::bind_rows(
    data.frame(figure = "F5", element = "withinweek", key = paste(w$season_scope, w$edge_scope, sep = "/"),
               label = w$label, value = w$estimate, lo95 = w$lo95, hi95 = w$hi95, n = w$n_pitches,
               n_umpire_weeks = w$n_umpire_weeks, n_umpires = w$n_umpires, y = w$y,
               note = sprintf("frame %s to %s, strictly before the %s changeover", w$frame_first_date, w$frame_last_date,
                              w$changeover_date),
               source = "out/ch1/tab/aaa_withinweek.csv (W3.20)", stringsAsFactors = FALSE),
    data.frame(figure = "F5", element = "pretrend", key = q$estimand, label = q$label, units = q$units,
               value = q$point, lo95 = q$lo95, hi95 = q$hi95, n = q$n_draws, y = q$y, verdict = q$verdict,
               primary = as.logical(q$primary), mlb_change = q$mlb_change, aaa_change = q$aaa_change,
               note = "MLB binned series, primary AAA window", source = "out/ch1/tab/aaa_pretrend.csv (W3.20)",
               stringsAsFactors = FALSE),
    const_rows("F5", c(ci_pct = 95, n_withinweek_rows = nrow(w), n_pretrend_rows = nrow(q))),
    recovery_rows("F5", rc))
  v <- function(x, d = 2) f_d(x, d)
  wp <- w[w$season_scope == "pooled" & w$edge_scope == "all", ]
  wt <- w[w$edge_scope == "top", ]; wb <- w[w$edge_scope == "bot", ]
  qa <- q[q$estimand == "area_sqin", ]; qt <- q[q$estimand == "top_in", ]
  # The alt text below states these four facts in words; each is checked so the words cannot go stale.
  check("F5 alt: every within-week interval lies right of zero", all(w$lo95 > 0), sprintf("lowest lo95 %.3f", min(w$lo95)))
  check("F5 alt: the top edge row is the largest within-week estimate and the bottom edge row the smallest",
        which.max(w$estimate) == which(w$edge_scope == "top") && which.min(w$estimate) == which(w$edge_scope == "bot"),
        paste(sprintf("%s %.3f", w$label, w$estimate), collapse = "; "))
  check("F5 alt: area and top edge pre-trend intervals exclude 0; bottom edge and half-width contain it",
        identical(setNames(q$excludes0, q$estimand), c(top_in = TRUE, bot_in = FALSE, half_width_in = FALSE, area_sqin = TRUE)),
        paste(q$estimand, q$tag, collapse = "; "))
  caption <- paste0(
    "W3.20's AAA arm. Its committed outputs hold no contour coordinates, so the contours SOP W3.24 names are not ",
    "drawn (DEV-90). The top panel is the within-week alternation. It shows the challenge-format minus full-ABS ",
    "called-strike rate in the shadow band, for the same plate umpire, season and week. Points are in percentage ",
    "points with 95% intervals, ", comma(wp$n_pitches), " pitches pooled. The frame ends before the ",
    wp$changeover_date, " changeover. The lower panels are the pre-trend: MLB's 2023 to 2024 change minus AAA's, ",
    "binned series, primary AAA window, with 95% intervals. Area is the primary row. A filled point marks an interval ",
    "that excludes 0, and there the DiD is reported as descriptive. Placebo P1 failed, so every row is descriptive.",
    recovery_caption(rc))
  alt <- paste0(
    "Three stacked dot-and-interval panels. In the top panel every within-week interval lies right of zero. ",
    "Pooled, the challenge-format rate is ", v(wp$estimate), " pp above the full-ABS rate (95% CI ", v(wp$lo95), " to ",
    v(wp$hi95), "). The top edge row is the largest, at ", v(wt$estimate), " pp, and the bottom edge row the smallest, at ",
    v(wb$estimate), " pp. In the pre-trend panels two intervals exclude zero: area, ", v(qa$point), " sq in (", v(qa$lo95),
    " to ", v(qa$hi95), "), and the top edge, ", v(qt$point), " in (", v(qt$lo95), " to ", v(qt$hi95),
    "). The bottom edge and half-width intervals contain zero.")
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 9.5, palette = B450)
}

## --- F8 while the sealed run is pending ------------------------------------------------------------

# A deliberate panel, not a result: it says the sealed run is pending and when it runs, and it reads
# nothing from the sealed set (DEV-90).
fig_pending <- function(id) {
  b <- c(PENDING[[id]], as.list(f8_schedule()))
  pl <- ggplot() +
    annotate("rect", xmin = 0, xmax = 1, ymin = 0, ymax = 1, fill = "#f0efec", colour = NA) +
    annotate("label", x = 0.5, y = 0.74, fill = "white", linewidth = 0, label = "SEALED RUN PENDING: NOT A RESULT",
             size = 8.5 / .pt, fontface = "bold", colour = INK) +
    annotate("label", x = 0.5, y = 0.57, fill = "white", linewidth = 0, label = sprintf("%s  %s", id, FIG_TITLES[[id]]),
             size = 7 / .pt, colour = INK) +
    annotate("label", x = 0.5, y = 0.42, fill = "white", linewidth = 0,
             label = sprintf("%s, the sealed run, runs once after %s", b$step, b$runs_after), size = 6.5 / .pt, colour = INK2) +
    annotate("label", x = 0.5, y = 0.28, fill = "white", linewidth = 0,
             label = sprintf("Pending by design since %s (%s); no sealed datum is read", b$recorded, b$dev),
             size = 6 / .pt, colour = INK2) +
    coord_cartesian(xlim = c(0, 1), ylim = c(0, 1), expand = FALSE) +
    theme_void() + theme(plot.background = element_rect(fill = "white", colour = NA))
  side <- data.frame(figure = id, element = "pending", key = "status", blocked_by = b$step, gate = b$gate,
                     recorded = b$recorded, runs_after = b$runs_after, deviation = b$dev,
                     note = sprintf("Sealed run pending, not a result: %s", b$why), stringsAsFactors = FALSE)
  caption <- sprintf(paste("Sealed run pending, not a result. %s, %s, is drawn from the sealed set once %s has run, after %s.",
                           "Until %s exists this panel is drawn on purpose and reads no sealed datum (%s, recorded %s)."),
                     id, tolower(FIG_TITLES[[id]]), b$step, b$runs_after, b$gate, b$dev, b$recorded)
  alt <- sprintf("A plain grey panel reading: sealed run pending, not a result; %s runs once after %s.", b$step, b$runs_after)
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 5, palette = character(0))
}

## --- the placeholders ----------------------------------------------------------------------------

fig_placeholder <- function(id) {
  b <- BLOCKED[[id]]
  pl <- ggplot() +
    annotate("rect", xmin = 0, xmax = 1, ymin = 0, ymax = 1, fill = "#f0efec", colour = NA) +
    geom_abline(slope = 1, intercept = seq(-1, 1, by = 0.1), colour = AXIS, linewidth = 0.2) +
    annotate("label", x = 0.5, y = 0.66, fill = "white", linewidth = 0, label = "PLACEHOLDER: NOT A RESULT", size = 9 / .pt, fontface = "bold",
             colour = INK) +
    annotate("label", x = 0.5, y = 0.5, fill = "white", linewidth = 0, label = sprintf("%s  %s", id, FIG_TITLES[[id]]), size = 7 / .pt, colour = INK) +
    annotate("label", x = 0.5, y = 0.36, fill = "white", linewidth = 0, label = sprintf("Blocked on %s", b$step), size = 6.5 / .pt, colour = INK2) +
    coord_cartesian(xlim = c(0, 1), ylim = c(0, 1), expand = FALSE) +
    theme_void() + theme(plot.background = element_rect(fill = "white", colour = NA))
  side <- data.frame(figure = id, element = "placeholder", key = "status", blocked_by = b$step,
                     note = sprintf("PLACEHOLDER, not a result: %s", b$why), stringsAsFactors = FALSE)
  caption <- sprintf("PLACEHOLDER, not a result. %s, %s, is drawn once %s lands: %s.", id, tolower(FIG_TITLES[[id]]),
                     b$step, b$why)
  alt <- sprintf("A grey hatched panel reading: placeholder, not a result; %s is blocked on %s.", id, b$step)
  list(plot = pl, data = side, caption = caption, alt = alt, h_cm = 5, palette = character(0), placeholder = TRUE)
}

## --- the render stage ------------------------------------------------------------------------------

BUILDERS <- list(F1 = fig_f1, F2 = fig_f2, F2b = fig_f2b, F3 = fig_f3, F4 = fig_f4, F5 = fig_f5, F6 = fig_f6, F7 = fig_f7)

render_stage <- function(ctx, dest) {
  p <- ctx$paths
  ensure_dir(file.path(dest, "figures"))
  ensure_dir(file.path(dest, "tables"))
  man <- list()
  outs <- character(0)
  for (id in FIG_IDS) {
    t0 <- proc.time()
    ph <- id %in% names(BLOCKED)
    pend <- !ph && id %in% names(PENDING) && is.null(BUILDERS[[id]])
    if (!ph && !pend && is.null(BUILDERS[[id]])) die(id, " has no builder, is not pending and is not blocked")
    f <- if (ph) fig_placeholder(id) else if (pend) fig_pending(id) else BUILDERS[[id]](p)
    status <- if (ph) "PLACEHOLDER" else if (pend) "pending" else "built"
    sp <- file.path(dest, "tables", paste0(id, "_data.csv"))
    write_csv_plain(f$data, sp)
    side <- read_csv_plain(sp)
    bad <- c(untraced(f$caption, side), untraced(f$alt, side))
    check(sprintf("%s: every caption and alt-text number is in its sidecar", id), length(bad) == 0L,
          if (length(bad)) paste("untraced:", paste(unique(bad), collapse = ", ")) else basename(sp))
    fl <- save_fig(f$plot, id, dest, f$h_cm)
    outs <- c(outs, sp, fl)
    gap <- min_lgap(f$palette)
    man[[id]] <- data.frame(
      figure_id = id, title = FIG_TITLES[[id]], status = status,
      blocked_by = if (ph) BLOCKED[[id]]$step else if (pend) PENDING[[id]]$step else "", png = out_rel(ctx, fl[["png"]]), pdf = out_rel(ctx, fl[["pdf"]]),
      sidecar = out_rel(ctx, sp), width_cm = FIG_W_CM, height_cm = f$h_cm, caption = f$caption, alt = f$alt,
      palette = paste(f$palette, collapse = ";"), palette_min_lstar_gap = gap,
      sidecar_rows = nrow(side), sidecar_sha256 = sha256_file(sp), stringsAsFactors = FALSE)
    record(id, sprintf("%s, %d sidecar rows, %.0f s", status, nrow(side),
                       (proc.time() - t0)[["elapsed"]]))
  }
  mf <- file.path(dest, "figures", "figures_manifest.csv")
  write_csv_plain(do.call(rbind, man), mf)
  if (!identical(normalizePath(dest, mustWork = FALSE), normalizePath(ctx$out, mustWork = FALSE))) {
    record("receipt", "not written: a --dest render is a check, not the published run")
    return(names(BLOCKED))
  }
  step_receipt(ctx, suffix = "figures", seed = DRAW_SEED,
               inputs = c(unlist(fig_paths(p)[c("rays", "contours", "bins")]), dz_path(p),
                          file.path(p$tab, c("T3_estimands.csv", "T4_decomposition.csv", "T4_plane_component.csv",
                                             "T5_placebos.csv", "T6_heterogeneity.csv", "framing_catcher_seasons.csv",
                                             "aaa_withinweek.csv", "aaa_pretrend.csv")),
                          file.path(p$model, c("estimand_draws_main.csv", "umpire_me.rds"))),
               outputs = c(outs, mf))
  names(BLOCKED)
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE), flags = "force")
  stage <- opt_get(opt, "stage", "all")
  if (!stage %in% c("compute", "render", "all")) die("--stage takes compute, render or all, not ", stage)
  Sys.setenv(STAN_NUM_THREADS = "1", OMP_NUM_THREADS = "1")
  ctx <- start_run("W3.24", opt, SCRIPT)
  if (stage %in% c("compute", "all")) compute_stage(ctx, opt)
  ph <- character(0)
  if (stage %in% c("render", "all")) ph <- render_stage(ctx, opt_get(opt, "dest", ctx$out))
  cat(sprintf("\nW3.24 figures: %d PASS, %d FAIL, %.0f s\n", .ch1$n_pass, length(.ch1$failures), elapsed_s()))
  if (length(.ch1$failures) > 0L) {
    cat("failures:\n", paste0("  ", .ch1$failures, "\n"), sep = "")
    quit(status = 1)
  }
  if (stage %in% c("render", "all") && !sealed_run_done()) {
    for (id in names(PENDING)) cat(sprintf("PENDING BY DESIGN %s %s: %s has not run (no %s); %s\n", id, FIG_TITLES[[id]],
                                           PENDING[[id]]$step, PENDING[[id]]$gate, PENDING[[id]]$dev))
  }
  if (length(ph) > 0L) {
    for (id in ph) cat(sprintf("PLACEHOLDER %s %s: blocked on %s. %s\n", id, FIG_TITLES[[id]], BLOCKED[[id]]$step,
                               BLOCKED[[id]]$why))
    cat(sprintf("W3.24 figures INCOMPLETE: %d of %d are placeholders (%s); exit 3\n", length(ph), length(FIG_IDS), paste(ph, collapse = ", ")))
    quit(status = 3)
  }
  quit(status = 0)
}

if (identical(environment(), globalenv()) && !interactive()) main()
