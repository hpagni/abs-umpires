#!/usr/bin/env Rscript
# R/ch1/71_tables.R - SOP W3.24, the Chapter 1 tables T1 to T9, and docs/ch1.md. `make tables` runs it;
# nothing else may produce a table (SOP section 9.1).
#
#   make tables                            scripts/tables.sh: 70_figures.R --stage compute (a cache hit
#                                          after `make figures`), then this script
#   Rscript R/ch1/71_tables.R [--dest <dir>] [--docs <path>]
#
# THE NINE TABLES, as SOP W3.24 lists them, each written to <dest>/tables/T<n>_<name>.csv:
#   T1  sample construction: W3.5's rules and counts, plus the rows that reconcile them with the
#       sample the primary surface was fitted on (70_figures.R --stage compute rebuilds it)
#   T2  the zone gate, W3.8 (CH1-A1)
#   T3  the estimands by season, the primary fit, W3.15
#   T4  the decomposition, W3.16: g, Delta_buffer, Delta_ABS, Delta_total and the share only where
#       the 95% interval on Delta_buffer + Delta_ABS excludes zero (D-59, CH1-A9); the plane
#       component per edge (W3.17, D-56, CH1-A13); the balanced-panel row beside each component with
#       the difference as a number (CH1-A14); the binned estimate and CH1-A5's verdict
#   T5  the placebos, W3.21 (P3 not run: the AAA arm is blocked)
#   T6  umpire heterogeneity, W3.18 (CH1-A6)
#   T7  calibration by 0.5-inch d bin, in-sample, the rows F7 plots; the sealed-set calibration of
#       W3.23 is a separate block that is empty until that run
#   T8  the sensitivity grid. BUILT ONLY WHEN quality/receipts/W3.22.json IS PASS. Until then a
#       placeholder that fails loudly: the grid on disk is unverified and no row of it is read.
#   T9  comparison with Clemens, Andrews, Dwyer, Doolittle and use-it-or-lose-it METHODS section 8,
#       every published number cited to its section of docs/prior-art.md
#
# docs/ch1.md is assembled here from the figure manifest, these tables and the sibling prose
# (out/ch1/prose/framing.md, W3.19; out/ch1/prose/aaa.md, W3.20, folded in when it exists).
#
# EXIT STATUS. 0 when all nine tables are built, 3 when a placeholder was written (T8 today),
# 1 on a failed check.

ROOT <- local({
  r <- Sys.getenv("ABSUMP_ROOT", "")
  if (nzchar(r)) return(normalizePath(r))
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

SCRIPT <- "R/ch1/71_tables.R"
TAB_IDS <- sprintf("T%d", 1:9)
TAB_FILE <- c(T1 = "T1_sample_construction", T2 = "T2_zone_gate", T3 = "T3_estimands_by_season",
              T4 = "T4_decomposition", T5 = "T5_placebos", T6 = "T6_heterogeneity", T7 = "T7_calibration",
              T8 = "T8_sensitivity", T9 = "T9_prior_work")
TAB_TITLES <- c(T1 = "Sample construction", T2 = "Zone gate", T3 = "Estimands by season", T4 = "Decomposition",
                T5 = "Placebos", T6 = "Umpire heterogeneity", T7 = "Calibration by d bin", T8 = "Sensitivity grid",
                T9 = "Comparison with published work")
ESTS <- c("top_in", "bot_in", "half_width_in", "area_sqin", "shadow_rate", "count_bias")
EST_NAME <- c(top_in = "Top edge", bot_in = "Bottom edge", half_width_in = "Half-width", area_sqin = "Area",
              shadow_rate = "Shadow-band called-strike rate", count_bias = "Count bias")
UNIT_DIG <- c("in" = 2L, "sq in" = 1L, "pp" = 2L, "in per season" = 3L)
REGIME_LAB <- c(pre_buffer = "Pre-buffer", buffer_2025 = "Buffer cut", abs_2026 = "ABS challenge")

tab_paths <- function(p) {
  list(bins = file.path(p$fig, "W3_24_F7_bins.csv"), sample = file.path(p$fig, "W3_24_fit_sample.csv"))
}
digits_for <- function(u) if (!is.na(UNIT_DIG[u])) UNIT_DIG[[u]] else 2L
f_d <- function(x, d) ifelse(is.na(x), "", sprintf("%.*f", as.integer(d), as.numeric(x)))
ci_s <- function(pt, lo, hi, d) ifelse(is.na(pt), "", sprintf("%s (%s to %s)", f_d(pt, d), f_d(lo, d), f_d(hi, d)))
md_table <- function(df) {
  esc <- function(x) gsub("|", "\\|", as.character(x), fixed = TRUE)
  c(paste0("| ", paste(esc(names(df)), collapse = " | "), " |"),
    paste0("|", paste(rep("---", ncol(df)), collapse = "|"), "|"),
    vapply(seq_len(nrow(df)), function(i) paste0("| ", paste(esc(unlist(df[i, ], use.names = FALSE)), collapse = " | "), " |"), ""))
}
rd <- function(...) read_csv_plain(file.path(...))

## --- T1 ---------------------------------------------------------------------------------------------

tab_t1 <- function(p) {
  t1 <- rd(p$tab, "T1_sample.csv")
  fs <- read_csv_plain(tab_paths(p)$sample)
  rec <- fromJSON(file.path(p$models, "surface_main", "provenance.json"))
  yc <- paste0("y", SEASONS)
  base <- data.frame(block = t1$block, row_id = t1$row_id, rule = t1$rule, unit = t1$unit, t1[, yc], total = t1$total,
                     source = "out/ch1/tab/T1_sample.csv (W3.5)", stringsAsFactors = FALSE, check.names = FALSE)
  add <- function(id, rule, unit, v) {
    r <- data.frame(block = "fit", row_id = id, rule = rule, unit = unit, stringsAsFactors = FALSE)
    for (i in seq_along(SEASONS)) r[[yc[i]]] <- as.character(v[i])
    r$total <- sum(v)
    r$source <- "out/ch1/fig/W3_24_fit_sample.csv (W3.24 compute, the W3.14 loader)"
    r
  }
  fit <- rbind(
    add("F_dropped", "P0 rows of the games without ABS hardware, dropped by the fit code (PREREGISTRATION.md section 7)",
        "pitches", as.numeric(t1[t1$row_id == "P0", yc]) - fs$p0_loaded),
    add("F_p0_loaded", "P0 as the fit code loads it", "pitches", fs$p0_loaded),
    add("F_p0_heights", "P0 after the primary height rule (roster plus cohort-specific offset, D-P4-04)", "pitches", fs$p0_heights),
    add("F_surface_rows", "|d| <= 8.0 in rows the primary surface was fitted on (W3.14 main)", "pitches", fs$surface_rows),
    add("F_surface_games", "games with a surface row", "games", fs$games))
  out <- rbind(base, fit)
  check("T1: the fitted rows equal W3.14's receipt", sum(fs$surface_rows) == rec$n_rows,
        sprintf("%s rows against %s", comma(sum(fs$surface_rows)), comma(rec$n_rows)))
  drop <- as.numeric(t1[t1$row_id == "P0", yc]) - fs$p0_loaded
  check("T1: the loaded P0 is W3.5's P0 less the dropped games, never more", all(drop >= 0),
        sprintf("%s rows dropped: %s", comma(sum(drop)), paste(drop, collapse = ", ")))
  keep <- out$block %in% c("sample", "band", "size", "cohort", "panel", "fit") & !grepl("^X_game_type$|^X_postseason$", out$row_id)
  show <- out[keep, ]
  cnt <- function(x, u) ifelse(u %in% c("pitches", "games", "umpires") & grepl("^[0-9.]+$", x),
                               comma(round(as.numeric(x))), x)
  md <- data.frame(Row = show$row_id, Rule = show$rule, check.names = FALSE, stringsAsFactors = FALSE)
  for (i in seq_along(SEASONS)) md[[SEASONS[i]]] <- cnt(as.character(show[[yc[i]]]), show$unit)
  md$Total <- cnt(ifelse(is.na(show$total), "", as.character(show$total)), show$unit)
  list(data = out, md = md_table(md),
       note = paste("The W3.5 rows count the whole open lake; the fit rows are the sample the primary surface",
                    "was fitted on. Regime dates are in the CSV."))
}

## --- T2 ---------------------------------------------------------------------------------------------

tab_t2 <- function(p) {
  t2 <- rd(p$tab, "T2_zone_gate.csv")
  t2$source <- "out/ch1/tab/T2_zone_gate.csv (W3.8)"
  md <- data.frame(Row = t2$row_id, Challenged = comma(t2$n), Agree = comma(t2$n_agree),
                   Disagree = comma(t2$n_disagree), `Agreement, %` = f_d(t2$agreement_pct, 2),
                   `Threshold, %` = ifelse(is.na(t2$threshold_pct), "", f_d(t2$threshold_pct, 2)), Verdict = t2$verdict,
                   check.names = FALSE, stringsAsFactors = FALSE)
  check("T2: CH1-A1's two gates pass", all(t2$verdict[t2$row_id %in% c("overall", "outside_band")] == "PASS"),
        paste(t2$row_id[1:2], t2$verdict[1:2], collapse = "; "))
  list(data = t2, md = md_table(md), note = paste("MLB 2026 challenged pitches: the harmonised zone against the ABS",
                                                 "call. CH1-A1 is a hard gate."))
}

## --- T3 ---------------------------------------------------------------------------------------------

tab_t3 <- function(p) {
  t3 <- rd(p$tab, "T3_estimands.csv")
  t3 <- t3[t3$fit == "main", c("estimand", "units", "season", "regime", "point", "lo95", "hi95", "n_draws", "n_complete", "estimator")]
  t3 <- t3[order(match(t3$estimand, ESTS), t3$season), ]
  check("T3: six estimands by five seasons", nrow(t3) == 30L && all(t3$n_complete >= 0.99 * t3$n_draws), sprintf("%d rows", nrow(t3)))
  md <- data.frame(Estimand = sprintf("%s (%s)", EST_NAME[ESTS], t3$units[match(ESTS, t3$estimand)]), stringsAsFactors = FALSE)
  for (s in SEASONS) {
    r <- t3[t3$season == s, ][match(ESTS, t3$estimand[t3$season == s]), ]
    md[[as.character(s)]] <- ci_s(r$point, r$lo95, r$hi95, vapply(r$units, digits_for, 0L))
  }
  list(data = t3, md = md_table(md),
       note = paste("Primary fit, a 72-inch batter, standardised to the 2024 pitch mix; point estimate and 95% interval",
                    "from the 1,000 coefficient draws. Shadow rate and count bias are in percentage points."))
}

## --- T4 ---------------------------------------------------------------------------------------------

tab_t4 <- function(p) {
  t4 <- rd(p$tab, "T4_decomposition.csv")
  t4 <- t4[t4$fit == "main", ]
  pc <- rd(p$tab, "T4_plane_component.csv")
  rows <- list()
  for (e in ESTS) {
    r <- function(cmp) t4[t4$estimand == e & t4$component == cmp, ]
    g <- r("g"); b <- r("delta_buffer"); a <- r("delta_abs"); tot <- r("delta_total"); sm <- r("sum_components")
    sh <- r("share_abs")
    resid <- b$point + a$point + 2 * g$point - tot$point
    check(sprintf("T4 %s: Delta_buffer + Delta_ABS + 2g == Delta_total to 1e-9", e), abs(resid) < 1e-9, sprintf("%.1e", resid))
    excl <- sm$lo95 > 0 || sm$hi95 < 0
    check(sprintf("T4 %s: the share is reported exactly when the sum's 95%% interval excludes zero", e),
          identical(excl, isTRUE(as.logical(sh$reported))), sprintf("sum %s to %s; reported %s", f_d(sm$lo95, 3), f_d(sm$hi95, 3), sh$reported))
    pick <- rbind(g, b, a, tot, sm, sh)
    pick$point[pick$component == "share_abs" & !excl] <- NA
    pick$lo95[pick$component == "share_abs" & !excl] <- NA
    pick$hi95[pick$component == "share_abs" & !excl] <- NA
    x <- data.frame(estimand = e, component = pick$component, units = ifelse(pick$component == "share_abs", "share", pick$units),
                    point = pick$point, lo95 = pick$lo95, hi95 = pick$hi95,
                    reported = ifelse(pick$component == "share_abs", excl, TRUE),
                    panel_point = pick$panel_point, panel_lo95 = pick$panel_lo95, panel_hi95 = pick$panel_hi95,
                    panel_minus_primary = pick$panel_minus_primary, binned_point = pick$binned_point,
                    binned_minus_bam = pick$binned_minus_bam, ch1_a5_within = pick$ch1_a5_within,
                    abs_cohort_point = pick$abs_cohort_point, sign_agrees_abs_cohort = pick$sign_agrees_abs_cohort,
                    source = "out/ch1/tab/T4_decomposition.csv (W3.16)", stringsAsFactors = FALSE)
    if (e %in% pc$estimand) {
      q <- pc[pc$estimand == e, ]
      x <- rbind(x, data.frame(estimand = e, component = "plane_mechanical", units = q$units, point = q$point, lo95 = q$lo95,
                               hi95 = q$hi95, reported = TRUE, panel_point = NA, panel_lo95 = NA, panel_hi95 = NA,
                               panel_minus_primary = NA, binned_point = NA, binned_minus_bam = NA, ch1_a5_within = NA,
                               abs_cohort_point = NA, sign_agrees_abs_cohort = NA,
                               source = "out/ch1/tab/T4_plane_component.csv (W3.17, D-56)", stringsAsFactors = FALSE))
    }
    rows[[e]] <- x
  }
  out <- do.call(rbind, rows)
  rownames(out) <- NULL
  comp_lab <- c(g = "g, per season", delta_buffer = "Delta_buffer", delta_abs = "Delta_ABS", delta_total = "Delta_total",
                sum_components = "Delta_buffer + Delta_ABS", share_abs = "share_ABS", plane_mechanical = "Plane, mechanical")
  show <- out[out$component %in% names(comp_lab) & !(out$component == "share_abs" & !out$reported), ]
  dg <- ifelse(show$units == "share", 2L, vapply(show$units, digits_for, 0L))
  md <- data.frame(Estimand = EST_NAME[show$estimand], Component = comp_lab[show$component],
                   `Primary (95% CI)` = ci_s(show$point, show$lo95, show$hi95, dg),
                   `Balanced panel (95% CI)` = ci_s(show$panel_point, show$panel_lo95, show$panel_hi95, dg),
                   `Panel minus primary` = f_d(show$panel_minus_primary, dg),
                   `Binned` = f_d(show$binned_point, dg),
                   `CH1-A5` = ifelse(is.na(show$ch1_a5_within), "", ifelse(show$ch1_a5_within %in% c(TRUE, "TRUE"), "within", "outside")),
                   check.names = FALSE, stringsAsFactors = FALSE)
  list(data = out, md = md_table(md),
       note = paste("Placebo P1 failed (T5), so the components are descriptive departures from the 2022 to 2024 trend",
                    "and name no cause. The plane row is the 2025 mid-plate minus front-plate contour, outside the sum."))
}

## --- T5 ---------------------------------------------------------------------------------------------

tab_t5 <- function(p) {
  t5 <- rd(p$tab, "T5_placebos.csv")
  t5$source <- "out/ch1/tab/T5_placebos.csv (W3.21)"
  dig <- ifelse(t5$units == "rate", 4L, ifelse(t5$units == "sq in", 1L, 2L))
  md <- data.frame(Placebo = t5$placebo, Quantity = t5$quantity, Units = t5$units,
                   Estimate = f_d(t5$estimate, dig), Interval = ifelse(is.na(t5$lo), "", sprintf("%s to %s", f_d(t5$lo, dig), f_d(t5$hi, dig))),
                   Level = ifelse(is.na(t5$interval_level), "", f_d(100 * t5$interval_level, 0)),
                   `Margin or threshold` = f_d(t5$margin_or_threshold, dig), Verdict = t5$verdict,
                   check.names = FALSE, stringsAsFactors = FALSE)
  check("T5: P3 is marked not run while the AAA arm is blocked", all(t5$verdict[t5$placebo == "P3"] == "not run"), "W3.20")
  list(data = t5, md = md_table(md),
       note = paste("P1 is two one-sided equivalence tests at 90% (CH1-A3). P2's estimate is the mean of five All-Star",
                    "break boundaries, with their range as the interval. P4's interval is the range of season rates."))
}

## --- T6 ---------------------------------------------------------------------------------------------

tab_t6 <- function(p) {
  t6 <- rd(p$tab, "T6_heterogeneity.csv")
  keep <- t6$fit == "sop" | (t6$quantity == "tau_abs") | t6$fit %in% c("B3", "CH1-A6") |
    grepl("tau_median_change_vs_sop", t6$quantity)
  out <- t6[keep, ]
  out$source <- "out/ch1/tab/T6_heterogeneity.csv (W3.18)"
  dig <- ifelse(out$quantity %in% c("p_tau_ge_020"), 3L, 3L)
  md <- data.frame(Fit = out$fit, Quantity = out$quantity, Units = ifelse(is.na(out$units), "", out$units),
                   `Median (95% CI)` = ifelse(is.na(out$lo95), f_d(out$median, dig), ci_s(out$median, out$lo95, out$hi95, dig)),
                   `MT-05` = ifelse(is.na(out$mt05_pass), "", ifelse(out$mt05_pass %in% c(TRUE, "TRUE"), "pass", "fail")),
                   check.names = FALSE, stringsAsFactors = FALSE)
  a6 <- t6$median[t6$fit == "CH1-A6" & t6$quantity == "p_tau_ge_020"]
  check("T6: CH1-A6 is read from the sop fit", length(a6) == 1L, sprintf("P(tau >= 0.20 in) = %.3f", a6))
  list(data = out, md = md_table(md),
       note = paste("tau is the between-umpire SD of the 2025 to 2026 response, in inches. CH1-A6 calls it material",
                    "only if P(tau >= 0.20 in) >= 0.90; the reading is a bounded null."))
}

## --- T7 ---------------------------------------------------------------------------------------------

wilson <- function(k, n, z = stats::qnorm(0.975)) {
  ph <- k / n
  den <- 1 + z^2 / n
  c0 <- (ph + z^2 / (2 * n)) / den
  h <- z * sqrt(ph * (1 - ph) / n + z^2 / (4 * n^2)) / den
  cbind(c0 - h, c0 + h)
}

tab_t7 <- function(p) {
  b <- read_csv_plain(tab_paths(p)$bins)
  a <- b |>
    group_by(regime, bin, d_centre) |>
    summarise(n = sum(n), strikes = sum(strikes), fitted_sum = sum(fitted_sum), .groups = "drop") |>
    as.data.frame()
  a <- a[order(match(a$regime, names(REGIME_LAB)), a$bin), ]
  w <- wilson(a$strikes, a$n)
  fit <- 100 * a$fitted_sum / a$n
  out <- data.frame(block = "open_in_sample", regime = a$regime, bin = a$bin, d_centre = a$d_centre, n = a$n,
                    strikes = a$strikes, observed_pct = 100 * a$strikes / a$n, fitted_pct = fit,
                    diff_pp = 100 * a$strikes / a$n - fit, lo95_pp = 100 * w[, 1] - fit, hi95_pp = 100 * w[, 2] - fit,
                    stringsAsFactors = FALSE)
  out$covers_zero <- out$lo95_pp <= 0 & out$hi95_pp >= 0
  sm <- do.call(rbind, lapply(names(REGIME_LAB), function(r) {
    x <- out[out$regime == r, ]
    i <- which.max(abs(x$diff_pp))
    data.frame(block = "open_summary", regime = r, n = sum(x$n), bins = nrow(x), bins_covering_zero = sum(x$covers_zero),
               max_abs_diff_pp = abs(x$diff_pp[i]), max_abs_d_centre = x$d_centre[i],
               mean_abs_diff_pp = sum(x$n * abs(x$diff_pp)) / sum(x$n), stringsAsFactors = FALSE)
  }))
  sealed <- data.frame(block = "sealed_W3.23", regime = NA, status = "pending: W3.23, the sealed run, runs once after the season",
                       stringsAsFactors = FALSE)
  data <- dplyr::bind_rows(out, sm, sealed)
  check("T7: every fitted pitch counted once", sum(out$n) == sum(b$n), comma(sum(out$n)))
  md <- data.frame(Regime = REGIME_LAB[sm$regime], Pitches = comma(sm$n),
                   `Bins covering zero` = sprintf("%d of %d", sm$bins_covering_zero, sm$bins),
                   `Mean absolute gap, pp` = f_d(sm$mean_abs_diff_pp, 3),
                   `Largest gap, pp` = f_d(sm$max_abs_diff_pp, 2), `At d, in` = f_d(sm$max_abs_d_centre, 2),
                   check.names = FALSE, stringsAsFactors = FALSE)
  list(data = data, md = md_table(md), pending = "W3.23",
       note = paste("In-sample, by 0.5-inch bin of d over +/-8 in: observed called-strike rate minus the mean fitted",
                    "probability, with 95% Wilson intervals. Every bin is in the CSV; F7 plots them. The sealed-set",
                    "block is empty until W3.23 runs."))
}

## --- T8 ---------------------------------------------------------------------------------------------

w322_status <- function() {
  f <- file.path(ROOT, "quality", "receipts", "W3.22.json")
  if (!file.exists(f)) return("absent")
  s <- tryCatch(fromJSON(f)$status, error = function(e) "unreadable")
  if (is.null(s)) "unreadable" else as.character(s)
}

# The T8 builder W3.22's landing switches on. It reads W3.22's long grid and names every flagged
# cell: a status other than ok, a sign different from the same estimator's primary, a 95% interval
# that crosses zero, one that excludes the same estimator's primary point, or one that excludes the
# pre-registered bam primary; plus any cell listed in out/ch1/tab/sensitivity_flags.csv, the
# verifier's own list, when that file exists.
build_t8 <- function(grid, bam_primary, flags = NULL) {
  g <- grid[grid$component %in% c("delta_buffer", "delta_abs"), ]
  key <- function(d) paste(d$estimator, d$estimand, d$component)
  prim <- g[g$is_primary %in% c(TRUE, "TRUE") & g$status == "ok", ]
  pp <- prim$point[match(key(g), key(prim))]
  bp <- bam_primary$point[match(paste(g$estimand, g$component), paste(bam_primary$estimand, bam_primary$component))]
  ok <- g$status == "ok"
  g$flag_status <- !ok
  g$flag_sign <- ok & !is.na(pp) & sign(g$point) != sign(pp)
  g$flag_crosses_zero <- ok & g$lo95 <= 0 & g$hi95 >= 0
  g$flag_excludes_primary <- ok & !is.na(pp) & (pp < g$lo95 | pp > g$hi95)
  g$flag_excludes_bam_primary <- ok & !is.na(bp) & (bp < g$lo95 | bp > g$hi95)
  g$flag_verifier <- FALSE
  if (!is.null(flags) && nrow(flags) > 0L) g$flag_verifier <- g$cell_id %in% flags$cell_id
  fl <- grep("^flag_", names(g), value = TRUE)
  g$flagged <- Reduce(`|`, g[fl])
  g$flag_reasons <- apply(g[fl], 1, function(r) paste(sub("^flag_", "", fl[as.logical(r)]), collapse = ";"))
  g
}

tab_t8 <- function(p) {
  st <- w322_status()
  if (!identical(st, "PASS")) {
    why <- sprintf(paste("W3.22 has not landed: quality/receipts/W3.22.json is %s, and the verifier refuted the grid.",
                         "T8 is built from W3.22's grid only once that receipt is PASS; no row of the",
                         "unverified grid is read or printed here."), st)
    data <- data.frame(table = "T8", element = "placeholder", key = "status", blocked_by = "W3.22",
                       note = paste("PLACEHOLDER, not a result.", why), stringsAsFactors = FALSE)
    return(list(data = data, placeholder = TRUE, blocked_by = "W3.22", why = why,
                md = c("**PLACEHOLDER, not a result.**", "", why), note = ""))
  }
  grid <- read_csv_plain(file.path(p$tables, "T8_sensitivity_data.csv"))
  t4 <- rd(p$tab, "T4_decomposition.csv")
  ff <- file.path(p$tab, "sensitivity_flags.csv")
  g <- build_t8(grid, t4[t4$fit == "main", ], if (file.exists(ff)) read_csv_plain(ff) else NULL)
  hd <- g[g$estimand == "area_sqin", ]
  md <- data.frame(Cell = hd$cell_id, Estimator = hd$estimator, Component = hd$component,
                   `Point (95% CI)` = ci_s(hd$point, hd$lo95, hd$hi95, 1L), Flags = hd$flag_reasons,
                   check.names = FALSE, stringsAsFactors = FALSE)
  list(data = g, md = md_table(md), note = sprintf("%d flagged rows, every one named in the CSV.", sum(g$flagged)))
}

## --- T9 ---------------------------------------------------------------------------------------------

CITE_63 <- "docs/prior-art.md section 6.3"
SRC <- list(
  clemens = c(source = "Clemens", author_date = "Ben Clemens, FanGraphs, 2026-04-28", citation = CITE_63),
  andrews = c(source = "Andrews", author_date = "Davy Andrews, FanGraphs, 2025-05-05 and 2025-05-06", citation = CITE_63),
  dwyer = c(source = "Dwyer", author_date = "Pete Dwyer, FanSided, 2026-05-27", citation = CITE_63),
  doolittle = c(source = "Doolittle", author_date = "Bradford Doolittle, ESPN, 2026-05-19", citation = CITE_63),
  methods8 = c(source = "METHODS section 8", author_date = "AyanArora29/use-it-or-lose-it METHODS.md section 8, v0.3c, 2026-08-18", citation = "docs/prior-art.md sections 1.3 and 6.1"))

t9_row <- function(src, published_quantity, as_printed, pub_point, pub_lo, pub_hi, pub_units, ours_quantity, o_pt, o_lo, o_hi,
                   o_units, ours_source, basis, reading, extra = list()) {
  s <- SRC[[src]]
  r <- data.frame(source = s[["source"]], author_date = s[["author_date"]], citation = s[["citation"]],
                  published_quantity = published_quantity, published_as_printed = as_printed, published_point = pub_point,
                  published_lo95 = pub_lo, published_hi95 = pub_hi, published_units = pub_units, ours_quantity = ours_quantity,
                  ours_point = o_pt, ours_lo95 = o_lo, ours_hi95 = o_hi, ours_units = o_units, ours_source = ours_source,
                  basis = basis, reading = reading, stringsAsFactors = FALSE)
  for (k in names(extra)) r[[k]] <- extra[[k]]
  r
}

tab_t9 <- function(p) {
  pc <- rd(p$tab, "T9_published_comparison.csv")
  t3 <- rd(p$tab, "T3_estimands.csv"); t3 <- t3[t3$fit == "main", ]
  t4 <- rd(p$tab, "T4_decomposition.csv"); t4 <- t4[t4$fit == "main", ]
  fd <- rd(p$tab, "framing_doolittle.csv"); fd <- fd[fd$value_type == "cnt", ]
  dr <- rd(p$model, "estimand_draws_main.csv")
  rows <- list()
  printed <- c(area_sqin = "-22 to -8 sq in, point near -14 sq in", top_in = "-0.067 to -0.033 ft",
               bot_in = "-0.033 to -0.017 ft", half_width_in = "-0.075 to 0 ft in width, halved")
  for (q in c("area_sqin", "top_in", "bot_in", "half_width_in")) {
    r <- pc[pc$quantity == q, ]
    u <- if (q == "area_sqin") "sq in" else "in"
    d <- digits_for(u)
    inside <- r$published_convention_change_point >= r$published_lo95 && r$published_convention_change_point <= r$published_hi95
    rows[[q]] <- t9_row(
      "clemens", sprintf("%s, 2025 to 2026 change, 95%% interval", EST_NAME[[q]]), printed[[q]],
      if (q == "area_sqin") -14 else NA, r$published_lo95, r$published_hi95, u,
      "the same change on Clemens's convention (2025 front plate, 2026 mid plate), full season",
      r$published_convention_change_point, r$published_convention_change_lo95, r$published_convention_change_hi95, u,
      "out/ch1/tab/T9_published_comparison.csv (W3.17)",
      "his window ends 25 April; ours is the full open season, standardised to the 2024 mix",
      sprintf("On his convention the change is %s (95%% CI %s to %s), %s his interval. On mid-plate coordinates in both seasons it is %s (95%% CI %s to %s); the plane component is %s.",
              f_d(r$published_convention_change_point, d), f_d(r$published_convention_change_lo95, d),
              f_d(r$published_convention_change_hi95, d), if (inside) "a point inside" else "a point outside",
              f_d(r$corrected_change_point, d), f_d(r$corrected_change_lo95, d), f_d(r$corrected_change_hi95, d),
              f_d(r$plane_component_point, d)),
      extra = list(ours_corrected_point = r$corrected_change_point, ours_corrected_lo95 = r$corrected_change_lo95,
                   ours_corrected_hi95 = r$corrected_change_hi95, plane_component_point = r$plane_component_point))
  }
  sh <- function(s) t3[t3$estimand == "shadow_rate" & t3$season == s, ]
  ch <- dr[["2025_shadow_rate"]] - dr[["2024_shadow_rate"]]
  chq <- qint(ch, 0.95)
  chp <- sh(2025)$point - sh(2024)$point
  rows$andrews <- t9_row(
    "andrews", "shadow-zone called-strike rate, 2025, March and April", "42.7% in 2025, the lowest recorded", 42.7, NA, NA,
    "percent", "shadow-band called-strike rate, 2025, standardised", sh(2025)$point, sh(2025)$lo95, sh(2025)$hi95, "percent",
    "out/ch1/tab/T3_estimands.csv (W3.15); the change from out/ch1/model/estimand_draws_main.csv",
    "Statcast's shadow zone against the band |d - 1.45| <= 3.0 in, standardised; the levels are not comparable",
    sprintf("The 2025 rate here is %s pp from 2024 (95%% CI %s to %s), %s a record low.", f_d(chp, 2), f_d(chq[1], 2),
            f_d(chq[2], 2), if (chq[2] < 0) "the same direction as" else "not clearly in the direction of"),
    extra = list(ours_change_2025_2024 = chp, ours_change_lo95 = chq[1], ours_change_hi95 = chq[2]))
  tb <- function(e, cmp) t4[t4$estimand == e & t4$component == cmp, ]
  b <- tb("shadow_rate", "delta_buffer"); a <- tb("shadow_rate", "delta_abs")
  rows$dwyer <- t9_row(
    "dwyer", "shadow-zone called strikes as a share of all pitches, 2022 to 2026",
    "2.3%, 2.1%, 2.1%, 1.6% for 2022 to 2025; 1.5% in the first third of 2026", 1.6, NA, NA, "percent of all pitches",
    "Delta_buffer on the shadow-band called-strike rate", b$point, b$lo95, b$hi95, "pp",
    "out/ch1/tab/T4_decomposition.csv (W3.16)",
    "a share of all pitches against a rate within the band; only the timing compares",
    sprintf("Both show the drop at the 2024 to 2025 boundary: here the 2025 departure from trend is %s pp (95%% CI %s to %s) and the 2026 one %s pp (95%% CI %s to %s). The piece reads 2025 as anticipation of ABS and does not name the buffer cut.",
            f_d(b$point, 2), f_d(b$lo95, 2), f_d(b$hi95, 2), f_d(a$point, 2), f_d(a$lo95, 2), f_d(a$hi95, 2)),
    extra = list(ours_abs_point = a$point, ours_abs_lo95 = a$lo95, ours_abs_hi95 = a$hi95))
  dl <- function(r) fd[fd$row == r, ]
  for (k in c("top30_2025", "top30_2026_through_05-18")) {
    r <- dl(k)
    ins <- r$doolittle >= r$lo95 && r$doolittle <= r$hi95
    rows[[k]] <- t9_row(
      "doolittle", sprintf("top-30 framers, runs per 100 innings, %s", if (k == "top30_2025") "2025" else "2026 through 2026-05-18"),
      if (k == "top30_2025") "0.704" else "0.565", r$doolittle, NA, NA, "runs per 100 innings",
      "top-30 mean of W3.19's count-specific framing runs", r$point, r$lo95, r$hi95, "runs per 100 innings",
      "out/ch1/tab/framing_doolittle.csv (W3.19)", "both relative to the average catcher; his source is Savant's leaderboard",
      sprintf("His figure is %s the 95%% interval here, %s to %s.", if (ins) "inside" else "outside", f_d(r$lo95, 3), f_d(r$hi95, 3)))
  }
  r <- dl("change_pct_2026_through_05-18_vs_2025")
  ins <- r$doolittle >= r$lo95 && r$doolittle <= r$hi95
  rows$doolittle_change <- t9_row(
    "doolittle", "top-30 framers, change from 2025 to 2026 through 2026-05-18", "0.704 to 0.565, about -20%", r$doolittle,
    NA, NA, "percent", "the same change in W3.19's top-30 mean", r$point, r$lo95, r$hi95, "percent",
    "out/ch1/tab/framing_doolittle.csv (W3.19)", "the same windows",
    sprintf("The change here is %s%% (95%% CI %s%% to %s%%), an interval that %s his %s%%.", f_d(r$point, 1), f_d(r$lo95, 1),
            f_d(r$hi95, 1), if (ins) "includes" else "excludes", f_d(r$doolittle, 1)))
  cb <- tb("count_bias", "delta_buffer"); ca <- tb("count_bias", "delta_abs")
  nul <- cb$lo95 <= 0 && cb$hi95 >= 0
  rows$m8_buffer <- t9_row(
    "methods8", "count bias, the 2024 to 2025 placebo pair of their design", "a proposal with no output when the ledger was rechecked", NA, NA, NA,
    "pp", "Delta_buffer on count bias", cb$point, cb$lo95, cb$hi95, "pp", "out/ch1/tab/T4_decomposition.csv (W3.16)",
    "their estimand, pre-registered here and reported as a replication",
    sprintf("Their placebo pair is the buffer-cut pair. Its departure from trend here is %s pp (95%% CI %s to %s), so the pair is %s.",
            f_d(cb$point, 2), f_d(cb$lo95, 2), f_d(cb$hi95, 2), if (nul) "consistent with a null pair" else "not a null pair"))
  rows$m8_abs <- t9_row(
    "methods8", "count bias, 2026 against 2025", "a proposal with no output when the ledger was rechecked", NA, NA, NA, "pp",
    "Delta_ABS on count bias, trend-adjusted", ca$point, ca$lo95, ca$hi95, "pp", "out/ch1/tab/T4_decomposition.csv (W3.16)",
    "their contrast is 2026 against 2025 without a trend; ours removes the 2022 to 2024 trend",
    sprintf("The 2026 departure from trend on count bias is %s pp (95%% CI %s to %s).", f_d(ca$point, 2), f_d(ca$lo95, 2), f_d(ca$hi95, 2)))
  out <- dplyr::bind_rows(rows)
  pub <- ifelse(grepl(" ft", out$published_as_printed) & !is.na(out$published_lo95),
                sprintf("%s, that is %s to %s in", out$published_as_printed, f_d(out$published_lo95, 3), f_d(out$published_hi95, 3)),
                out$published_as_printed)
  md <- data.frame(Source = sprintf("%s (%s)", out$source, out$citation), Published = pub,
                   Here = ci_s(out$ours_point, out$ours_lo95, out$ours_hi95,
                               ifelse(out$ours_units == "sq in", 1L, ifelse(out$ours_units == "runs per 100 innings", 3L,
                                                                            ifelse(out$ours_units == "percent" & out$source == "Doolittle", 1L, 2L)))),
                   Units = out$ours_units, Reading = out$reading, check.names = FALSE, stringsAsFactors = FALSE)
  list(data = out, md = md_table(md),
       note = paste("Every published number is quoted as the prior-art ledger prints it, with its section. Each reading",
                    "states where the definitions differ."))
}

## --- docs/ch1.md ------------------------------------------------------------------------------------

fold_prose <- function(path) {
  x <- readLines(path, warn = FALSE, encoding = "UTF-8")
  if (length(x) && grepl("^# ", x[1])) x <- x[-1]
  while (length(x) && !nzchar(trimws(x[1]))) x <- x[-1]
  sub("^(#+) ", "\\1# ", x)
}

assemble_docs <- function(ctx, dest, tman, fman, res) {
  p <- ctx$paths
  rel <- function(f) if (startsWith(f, "out/")) paste0("../", f) else f
  t5 <- rd(p$tab, "T5_placebos.csv")
  p1_fail <- any(t5$placebo == "P1" & t5$placebo_verdict == "fail")
  built_f <- fman$figure_id[fman$status == "built"]; built_t <- tman$table_id[tman$status == "built"]
  ph <- rbind(data.frame(id = fman$figure_id, title = fman$title, status = fman$status, by = fman$blocked_by, stringsAsFactors = FALSE),
              data.frame(id = tman$table_id, title = tman$title, status = tman$status, by = tman$blocked_by, stringsAsFactors = FALSE))
  ph <- ph[ph$status == "PLACEHOLDER", ]
  L <- c("# Chapter 1: the called zone across three regimes", "",
         paste("This file is generated by `make tables` (`R/ch1/71_tables.R`, SOP W3.24) from the figure manifest, the",
               "table CSVs and the sibling prose. Edit those sources, not this file."), "",
         "## Status", "",
         sprintf("- Built: figures %s; tables %s.", paste(built_f, collapse = ", "), paste(built_t, collapse = ", ")))
  for (i in seq_len(nrow(ph))) {
    L <- c(L, sprintf("- **%s, %s: placeholder, not a result.** It is blocked on %s, and `make %s` exits 3 until it lands.",
                      ph$id[i], ph$title[i], ph$by[i], if (startsWith(ph$id[i], "F")) "figures" else "tables"))
  }
  pend <- tman[nzchar(tman$pending), ]
  for (i in seq_len(nrow(pend))) L <- c(L, sprintf("- %s is built for the open window; its sealed-set block waits on %s.",
                                                     pend$table_id[i], pend$pending[i]))
  if (p1_fail) {
    L <- c(L, paste("- Reading: placebo P1 failed (T5). Under the pre-registered consequence (PREREGISTRATION.md section 8,",
                    "DEV-77) every regime contrast in this chapter is descriptive and names no cause."))
  }
  L <- c(L, "", "## Figures", "",
         paste("Every figure is drawn at 8 cm width for grayscale print, and writes its sidecar CSV. Each caption's numbers",
               "are rows of that sidecar."), "")
  for (i in seq_len(nrow(fman))) {
    m <- fman[i, ]
    L <- c(L, sprintf("### %s. %s", m$figure_id, m$title), "", sprintf("![%s](%s)", m$alt, rel(m$png)), "", m$caption, "",
           sprintf("Data: `%s`. Vector: `%s`.", m$sidecar, m$pdf), "")
  }
  L <- c(L, "## Tables", "")
  for (id in TAB_IDS) {
    m <- tman[tman$table_id == id, ]
    r <- res[[id]]
    L <- c(L, sprintf("### %s. %s", id, m$title), "")
    if (nzchar(r$note)) L <- c(L, r$note, "")
    L <- c(L, r$md, "", sprintf("Source: `%s`.", m$csv), "")
  }
  fr <- file.path(p$root, "ch1", "prose", "framing.md")
  aa <- file.path(p$root, "ch1", "prose", "aaa.md")
  L <- c(L, "## Catcher framing by regime", "",
         paste("Folded in from `out/ch1/prose/framing.md` (W3.19) with its headings moved down one level. W3.19's test",
               "traces each of its numbers to `out/ch1/tab/framing_prose_numbers.csv`."), "")
  L <- c(L, if (file.exists(fr)) fold_prose(fr) else "Not written: `out/ch1/prose/framing.md` does not exist.", "")
  L <- c(L, "## The AAA arm", "")
  if (file.exists(aa)) {
    L <- c(L, "Folded in from `out/ch1/prose/aaa.md` (W3.20) with its headings moved down one level.", "", fold_prose(aa), "")
  } else {
    L <- c(L, paste("Not written. W3.20 is blocked on D-11's 2023 scan and D-57's 2024 changeover date (DT-29).",
                    "This section folds in `out/ch1/prose/aaa.md` when the sibling builder writes it. F5 and placebo P3",
                    "wait on the same step."), "")
  }
  L <- c(L, "## How this chapter is built", "",
         "- `make figures` runs `R/ch1/70_figures.R`: a cached compute stage, which needs the fitted surface, then the render.",
         "- `make tables` runs the same compute stage, a cache hit, then `R/ch1/71_tables.R`, which also writes this file.",
         "- Determinism is checked on the sidecars and table CSVs, never on the images.",
         "- `tests/testthat/test-ch1-figures.R` re-reads every output and fails while any placeholder remains.")
  L
}

## --- main -------------------------------------------------------------------------------------------

`%||%` <- function(a, b) if (is.null(a)) b else a
BUILDERS <- list(T1 = tab_t1, T2 = tab_t2, T3 = tab_t3, T4 = tab_t4, T5 = tab_t5, T6 = tab_t6, T7 = tab_t7, T8 = tab_t8,
                 T9 = tab_t9)

tables_stage <- function(ctx, dest, docs) {
  p <- ctx$paths
  need <- unlist(tab_paths(p))
  if (!all(file.exists(need))) die("the W3.24 compute outputs are missing (", paste(need[!file.exists(need)], collapse = ", "),
                                   "); run `make figures` first")
  fm <- file.path(dest, "figures", "figures_manifest.csv")
  if (!file.exists(fm)) die("no figure manifest at ", fm, "; run `make figures` first")
  ensure_dir(file.path(dest, "tables"))
  res <- list(); man <- list(); outs <- character(0)
  for (id in TAB_IDS) {
    r <- BUILDERS[[id]](p)
    f <- file.path(dest, "tables", paste0(TAB_FILE[[id]], ".csv"))
    write_csv_plain(r$data, f)
    ph <- isTRUE(r$placeholder)
    man[[id]] <- data.frame(table_id = id, title = TAB_TITLES[[id]], status = if (ph) "PLACEHOLDER" else "built",
                            blocked_by = r$blocked_by %||% "", pending = r$pending %||% "", csv = out_rel(ctx, f),
                            rows = nrow(r$data), sha256 = sha256_file(f), stringsAsFactors = FALSE)
    res[[id]] <- r
    outs <- c(outs, f)
    record(id, sprintf("%s, %d rows", if (ph) "PLACEHOLDER" else "built", nrow(r$data)))
  }
  tman <- do.call(rbind, man)
  mf <- file.path(dest, "tables", "tables_manifest.csv")
  write_csv_plain(tman, mf)
  fman <- read_csv_plain(fm)
  L <- assemble_docs(ctx, dest, tman, fman, res)
  ensure_dir(dirname(docs))
  con <- file(docs, open = "w", encoding = "UTF-8")
  writeLines(L, con)
  close(con)
  record("docs", sprintf("%s, %d lines", out_rel(ctx, docs), length(L)))
  if (!identical(normalizePath(dest, mustWork = FALSE), normalizePath(ctx$out, mustWork = FALSE))) {
    record("receipt", "not written: a --dest run is a check, not the published run")
    return(tman)
  }
  step_receipt(ctx, suffix = "tables",
               inputs = c(unlist(tab_paths(p)), fm,
                          file.path(p$tab, c("T1_sample.csv", "T2_zone_gate.csv", "T3_estimands.csv", "T4_decomposition.csv",
                                             "T4_plane_component.csv", "T5_placebos.csv", "T6_heterogeneity.csv",
                                             "T9_published_comparison.csv", "framing_doolittle.csv")),
                          file.path(p$model, "estimand_draws_main.csv"),
                          file.path(p$root, "ch1", "prose", c("framing.md", "aaa.md"))),
               outputs = c(outs, mf, docs))
  tman
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE))
  ctx <- start_run("W3.24", opt, SCRIPT)
  dest <- opt_get(opt, "dest", ctx$out)
  docs <- opt_get(opt, "docs", file.path(ROOT, "docs", "ch1.md"))
  tman <- tables_stage(ctx, dest, docs)
  cat(sprintf("\nW3.24 tables: %d PASS, %d FAIL, %.0f s\n", .ch1$n_pass, length(.ch1$failures), elapsed_s()))
  if (length(.ch1$failures) > 0L) {
    cat("failures:\n", paste0("  ", .ch1$failures, "\n"), sep = "")
    quit(status = 1)
  }
  ph <- tman[tman$status == "PLACEHOLDER", ]
  if (nrow(ph) > 0L) {
    for (i in seq_len(nrow(ph))) cat(sprintf("PLACEHOLDER %s %s: blocked on %s\n", ph$table_id[i], ph$title[i], ph$blocked_by[i]))
    cat(sprintf("W3.24 tables INCOMPLETE: %d of 9 are placeholders (%s); exit 3\n", nrow(ph), paste(ph$table_id, collapse = ", ")))
    quit(status = 3)
  }
  quit(status = 0)
}

if (identical(environment(), globalenv()) && !interactive()) main()
