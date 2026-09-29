#!/usr/bin/env Rscript
# R/ch1/24_plane.R - SOP W3.17, the mechanical plate-plane component, per edge (CH1-A13, D-56).
#
#   Rscript R/ch1/24_plane.R --table data/marts/ch1_called.parquet --out out
#   Rscript R/ch1/24_plane.R --table <table> --out <root> --plane-table <parquet of pitch_uid, x_front, z_front>
#
# WHAT IT ESTIMATES. SOP W3.17: fit the 2025 contour twice, once on the raw front-plane
# coordinates (what Clemens used) and once re-projected to mid-plate. Both fits use the same
# rows (2025, P0 on the primary height rule, |d| <= 8.0 in on the mid-plane d), the same
# single-season form of the frozen specification, and the same 2024 reference mix; only the
# location pair differs. For each of top_in, bot_in and half_width_in, and area_sqin:
#   plane_component = theta_2025(mid) - theta_2025(front)
# which is the published-convention 2025-to-2026 change minus the corrected one:
#   corrected change             theta_2026 - theta_2025, both mid-plane: W3.15's primary fit
#   published-convention change  theta_2026(mid) - theta_2025(front) = corrected + plane
# The component is the velocity-and-break-weighted shift at each edge, because the contour at
# an edge is set by the pitches thrown there (D-56). It is a separate waterfall line, subtracted
# once, from the published-convention change. delta_buffer and delta_abs are untouched: they are
# on mid-plane coordinates in every season already.
#
# INTERVALS. Each fit's 1,000 draws come from its own N(beta, Vc), with separate seeds, and the
# component's draws are their differences. The two fits share the 2025 outcomes, so their
# errors are positively correlated and this interval is conservative (wider than the joint one).
# The corrected change keeps W3.15's draws.
#
# FRONT COORDINATES. The analysis table carries the mid-plane pair only. On a real table the
# 2025 front-plane pair is read from the warehouse's open view, attached read-only, by pitch_uid:
# plate_x_front and plate_z_front, plane_source "front" on every 2025 row. --plane-table names a
# parquet of pitch_uid, x_front and z_front to use instead. A synthetic table carries x_front and
# z_front itself.
#
# WRITES, under --out:
#   ch1/tab/T4_plane_component.csv     one row per quantity, with the corrected and the
#                                      published-convention change beside the component
#   ch1/tab/T9_published_comparison.csv the published figures, attributed, beside ours
#   ch1/fig/F_dz_by_pitch_type.png and .csv   the front-to-middle dz by pitch type, 2025
#   ch1/model/surface_plane2025_{mid,front}.rds, draws_vc_plane2025_{mid,front}.rds, receipts

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

SEED_MID <- DRAW_SEED + 17L
SEED_FRONT <- DRAW_SEED + 29L
SUBTRACTED_FROM <- "the 2025-to-2026 change on the published convention (2025 front plane, 2026 mid plane)"
# Published figures, as docs/prior-art.md section 6.3 quotes them (Clemens, FanGraphs,
# 2026-04-28, through 25 April of each season). Edges in feet there; inches here.
PUB <- data.frame(
  quantity = c("area_sqin", "top_in", "bot_in", "half_width_in"),
  published_lo95 = c(-22, -0.067 * 12, -0.033 * 12, -0.075 * 12 / 2),
  published_hi95 = c(-8, -0.033 * 12, -0.017 * 12, 0),
  published_note = c("95% interval on the zone-area change, sq in",
                     "95% interval on the top-edge change, -0.067 to -0.033 ft",
                     "95% interval on the bottom-edge change, -0.033 to -0.017 ft",
                     "95% interval on the width change, -0.075 to 0 ft, halved for the half-width"),
  stringsAsFactors = FALSE)
PUB_SOURCE <- "Clemens, FanGraphs, The Strike Zone Is Shrinking, 2026-04-28 (docs/prior-art.md section 6.3)"

duckdb_path <- function() {
  code <- "from absump.paths import DUCKDB_PATH; print(DUCKDB_PATH)"
  out <- suppressWarnings(system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python", "-c", shQuote(code)),
                                  stdout = TRUE, stderr = TRUE))
  trimws(out[length(out)])
}

# The 2025 front-plane pair from the warehouse's open view, read-only, the query W3.7 reads it by
# (R/ch1/10_build_analysis_table.R), restricted to 2025 and the last open day.
warehouse_front <- function(ctx) {
  con <- suppressMessages(DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:"))
  on.exit(try(DBI::dbDisconnect(con, shutdown = TRUE), silent = TRUE), add = TRUE)
  db <- duckdb_path()
  ok <- FALSE
  for (attempt in 1:10) {
    ok <- tryCatch({
      DBI::dbExecute(con, sprintf("ATTACH %s AS abs (READ_ONLY)", DBI::dbQuoteString(con, db)))
      TRUE
    }, error = function(e) { record("warehouse attach", sprintf("attempt %d: %s", attempt, conditionMessage(e))); FALSE })
    if (ok) break
    Sys.sleep(3)
  }
  if (!ok) die("could not attach the warehouse read-only at ", db)
  pl <- DBI::dbGetQuery(con, "
    SELECT c.pitch_uid, c.plate_x_front AS x_front, c.plate_z_front AS z_front, c.plane_source
    FROM abs.main_marts.v_called_pitch_open AS c
    WHERE c.level = 'mlb' AND c.game_type = 'R' AND c.analysis_set = 'open'
      AND c.season = 2025 AND c.official_date <= CAST(? AS DATE)", params = list(format(ctx$last_open)))
  check("warehouse front pair: every 2025 row on the front plane", nrow(pl) > 0L && all(pl$plane_source == "front"),
        sprintf("%s rows from %s", comma(nrow(pl)), db))
  pl
}

front_coords <- function(ctx, opt, rows) {
  if (all(c("x_front", "z_front") %in% names(rows))) return(rows[, c("x_front", "z_front")])
  p <- opt_get(opt, "plane-table")
  pl <- if (!is.null(p)) as.data.frame(arrow::read_parquet(p)) else warehouse_front(ctx)
  k <- match(rows$pitch_uid, pl$pitch_uid)
  check("the front pair covers every 2025 row", !anyNA(k) && all(is.finite(pl$x_front[k]) & is.finite(pl$z_front[k])),
        sprintf("%d of %s rows missing", sum(is.na(k)), comma(nrow(rows))))
  if (anyNA(k)) die("the front-plane pair is missing for ", sum(is.na(k)), " 2025 rows")
  pl[k, c("x_front", "z_front")]
}

fit_plane <- function(ctx, name, rows, ref, seed, hr) {
  spec <- make_spec("single")
  ft <- fit_surface(fit_frame(rows, spec), spec)
  check(sprintf("%s: bam converged", name), ft$converged,
        sprintf("%s rows, %s coefficients, edf %.1f, largest fREML gradient %.1e, %.0f s", comma(nrow(rows)),
                comma(ft$n_coef), ft$edf, ft$grad_max, ft$seconds))
  cd <- coef_draws(ft$m, ctx$n_draws, seed)
  mix <- ref_mix(ft$m, ft$spec, ref, NULL)
  est <- surface_estimands(ft$m, ft$spec, mix, NULL, ref, cd, geom_only = TRUE)
  share <- est$diag$n_complete / nrow(cd)
  check(sprintf("%s: >= %.0f%% of draws complete", name, 100 * MIN_COMPLETE_SHARE), share >= MIN_COMPLETE_SHARE,
        sprintf("%d of %d", est$diag$n_complete, nrow(cd)))
  p <- ctx$paths
  f_fit <- file.path(p$model, sprintf("surface_%s.rds", name)); f_dr <- file.path(p$model, sprintf("draws_vc_%s.rds", name))
  ensure_dir(p$model)
  saveRDS(list(m = ft$m, spec = ft$spec, fit = name, height_rule = hr, n_rows = nrow(rows)), f_fit)
  saveRDS(cd, f_dr)
  write_receipt(ctx, provenance(ctx, sprintf("surface_%s", name), rows, seed, p$model,
                                extra = list(formula = spec$formula, n_coef = ft$n_coef, edf = ft$edf,
                                             fit_seconds = ft$seconds, converged = ft$converged,
                                             freml_grad_max = ft$grad_max, height_rule = hr, n_draws = ctx$n_draws,
                                             interval_cov = INTERVAL_COV, files = list(basename(f_fit), basename(f_dr)))),
                p$model)
  record(sprintf("%s point", name), paste(sprintf("%s %.3f", GEOM, est$point[GEOM]), collapse = ", "))
  est
}

dz_table <- function(rows, fr) {
  dz <- (rows$z_mid - fr$z_front) * 12
  s <- split(seq_along(dz), rows$pitch_type)
  out <- do.call(rbind, lapply(names(s), function(k) {
    v <- dz[s[[k]]]
    q <- stats::quantile(v, c(0.05, 0.25, 0.5, 0.75, 0.95), names = FALSE)
    data.frame(pitch_type = k, n = length(v), mean_velo_mph = mean(rows$velo[s[[k]]]), mean_dz_in = mean(v),
               sd_dz_in = stats::sd(v), p05_dz_in = q[1], p25_dz_in = q[2], p50_dz_in = q[3], p75_dz_in = q[4],
               p95_dz_in = q[5], stringsAsFactors = FALSE)
  }))
  out <- out[out$n >= 100L, ]
  out[order(out$p50_dz_in, decreasing = TRUE), ]
}

# Dot-and-range figure, one series, so no legend: the title names it. Dataviz reference palette
# slot 1 (#2a78d6, all six checks pass on the #fcfcfb surface), the median dot filled with a
# surface ring, a hairline recessive grid, text in ink tokens. Drawn 3.4 in wide at 8 pt, so it
# reads at the 8 cm column width of the SOP's figure rule; the two bar weights keep the 50% and
# 90% ranges apart in grayscale. The sidecar CSV is the table view.
plot_dz <- function(tab, path) {
  suppressPackageStartupMessages(library(ggplot2))
  tab$pitch_type <- factor(tab$pitch_type, levels = rev(tab$pitch_type))
  ink <- "#0b0b0b"; ink2 <- "#52514e"; series <- "#2a78d6"; surface <- "#fcfcfb"; grid <- "#e4e3df"
  g <- ggplot(tab, aes(y = pitch_type)) +
    geom_linerange(aes(xmin = p05_dz_in, xmax = p95_dz_in), linewidth = 0.5, colour = series, alpha = 0.45) +
    geom_linerange(aes(xmin = p25_dz_in, xmax = p75_dz_in), linewidth = 1.6, colour = series) +
    geom_point(aes(x = p50_dz_in), size = 2.4, shape = 21, fill = series, colour = surface, stroke = 0.7) +
    geom_text(aes(x = p05_dz_in, label = format(n, big.mark = ",")), hjust = 1.15, size = 2.2, colour = ink2) +
    scale_x_continuous(expand = expansion(mult = c(0.22, 0.04))) +
    labs(title = "Front-to-middle dz by pitch type, 2025",
         subtitle = "Dot: median. Thick bar: middle 50%. Thin bar: middle 90%. Number: pitches.",
         x = "dz, in (z at mid-plate minus z at the front)", y = NULL) +
    theme_minimal(base_size = 8) +
    theme(plot.background = element_rect(fill = surface, colour = NA), panel.grid.major.y = element_blank(),
          panel.grid.minor = element_blank(), panel.grid.major.x = element_line(colour = grid, linewidth = 0.25),
          plot.title = element_text(colour = ink, face = "bold", size = 8.5),
          plot.subtitle = element_text(colour = ink2, size = 6.5), axis.text = element_text(colour = ink2),
          axis.title = element_text(colour = ink2, size = 7), plot.title.position = "plot")
  ensure_dir(dirname(path))
  ggsave(path, g, width = 3.4, height = 1.0 + 0.2 * nrow(tab), dpi = 300, device = ragg::agg_png)
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE))
  ctx <- start_run("W3.17", opt, "R/ch1/24_plane.R")
  p <- ctx$paths
  cal <- read_calibration(ctx, opt)
  d <- load_table(ctx, seasons = c(2024L, 2025L), extra = c("x_front", "z_front"))
  prim <- apply_heights(d, "primary", cal, ctx, identical(opt_get(opt, "height-rule"), "single-offset"))
  hr <- attr(prim, "height_rule")
  all25 <- prim[prim$season == 2025L, ]
  fr_all <- front_coords(ctx, opt, all25)
  rows <- surface_rows(all25)
  fr <- fr_all[abs(all25$d) <= BAND_SURF, ]
  ref <- surface_rows(prim[prim$season == 2024L, ])
  est_mid <- fit_plane(ctx, "plane2025_mid", rows, ref, SEED_MID, hr)
  front <- rows
  front$x_mid <- fr$x_front
  front$zn <- z_norm(fr$z_front, front$H)
  est_front <- fit_plane(ctx, "plane2025_front", front, ref, SEED_FRONT, paste(hr, "; front-plane pair"))

  t3 <- read_csv_plain(file.path(p$tab, "T3_estimands.csv"))
  dm <- read_csv_plain(file.path(p$model, "estimand_draws_main.csv"))
  dz <- (all25$z_mid - fr_all$z_front) * 12
  near <- abs(all25$d) <= BAND_SHADOW
  out <- list()
  for (e in GEOM) {
    pc <- est_mid$point[[e]] - est_front$point[[e]]
    pd <- est_mid$draws[, e] - est_front$draws[, e]
    pt <- function(s) t3$point[t3$fit == "main" & t3$season == s & t3$estimand == e]
    cc <- pt(2026) - pt(2025)
    cd <- dm[[paste("2026", e, sep = "_")]] - dm[[paste("2025", e, sep = "_")]]
    n <- min(length(pd), length(cd))
    pub <- cd[seq_len(n)] + pd[seq_len(n)]
    edge <- switch(e, top_in = "top", bot_in = "bot", half_width_in = NA, area_sqin = NA)
    out[[e]] <- data.frame(
      estimand = e, component = "plane", point = pc, lo95 = qint(pd)[1], hi95 = qint(pd)[2],
      units = ESTIMAND_UNITS[[e]],
      estimator = sprintf("bam single-season 2025 fits, mid-plane minus front-plane pair; 95%% interval from %d independent N(beta, Vc) draws of each fit (conservative)", length(pd)),
      theta_2025_mid = est_mid$point[[e]], theta_2025_front = est_front$point[[e]],
      corrected_change_point = cc, corrected_change_lo95 = qint(cd)[1], corrected_change_hi95 = qint(cd)[2],
      published_convention_change_point = cc + pc, published_convention_change_lo95 = qint(pub)[1],
      published_convention_change_hi95 = qint(pub)[2],
      mean_dz_in_shadow_band_at_edge = if (is.na(edge)) NA_real_ else mean(dz[near & all25$edge == edge]),
      subtracted_from = SUBTRACTED_FROM,
      not_subtracted_from = "delta_buffer and delta_abs, which use mid-plane coordinates in every season",
      stringsAsFactors = FALSE)
    record(sprintf("plane component %s", e), sprintf("%s (%s); corrected 2025-2026 change %s; published-convention change %s",
           num_txt(pc, ESTIMAND_UNITS[[e]]), ci_txt(qint(pd)[1], qint(pd)[2], ESTIMAND_UNITS[[e]]),
           num_txt(cc, ESTIMAND_UNITS[[e]]), num_txt(cc + pc, ESTIMAND_UNITS[[e]])))
  }
  tab <- do.call(rbind, out)
  check("CH1-A13: top, bottom and width rows, each with a 95% interval",
        all(c("top_in", "bot_in", "half_width_in") %in% tab$estimand) && all(is.finite(c(tab$lo95, tab$hi95))),
        sprintf("%d rows", nrow(tab)))
  write_csv_plain(tab, file.path(p$tab, "T4_plane_component.csv"))

  # T9: the published figures, attributed, beside ours
  t9 <- merge(PUB, tab[, c("estimand", "point", "lo95", "hi95", "corrected_change_point", "corrected_change_lo95",
                           "corrected_change_hi95", "published_convention_change_point",
                           "published_convention_change_lo95", "published_convention_change_hi95")],
              by.x = "quantity", by.y = "estimand", sort = FALSE)
  names(t9)[names(t9) %in% c("point", "lo95", "hi95")] <- c("plane_component_point", "plane_component_lo95", "plane_component_hi95")
  t9$published_source <- PUB_SOURCE
  t9$published_convention <- "2025 front-plane against 2026 mid-plane coordinates, through 25 April, batters in both seasons, 2026 heights in both"
  t9$convention_share_at_published_lo95 <- t9$plane_component_point / t9$published_lo95
  t9$convention_share_at_published_hi95 <- ifelse(t9$published_hi95 == 0, NA, t9$plane_component_point / t9$published_hi95)
  t9$reading <- paste("The plane component is the part of a published-convention change that is convention rather",
                      "than umpire behaviour; its share of the published figure may exceed 1 or change sign.")
  write_csv_plain(t9, file.path(p$tab, "T9_published_comparison.csv"))
  a <- t9[t9$quantity == "area_sqin", ]
  record("T9 area", sprintf("published %s to %s sq in (attributed); plane component %s sq in; share of the published figure %.2f to %.2f",
                            a$published_lo95, a$published_hi95, num_txt(a$plane_component_point, "sq in"),
                            a$convention_share_at_published_lo95, a$convention_share_at_published_hi95))

  dzt <- dz_table(all25, fr_all)
  write_csv_plain(dzt, file.path(p$fig, "F_dz_by_pitch_type.csv"))
  plot_dz(dzt, file.path(p$fig, "F_dz_by_pitch_type.png"))
  record("figure", sprintf("%s and its sidecar CSV, %d pitch types", file.path(p$fig, "F_dz_by_pitch_type.png"), nrow(dzt)))
  finish("W3.17")
}

if (identical(environment(), globalenv()) && !interactive()) main()
