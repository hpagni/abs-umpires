#!/usr/bin/env Rscript
# R/ch1/26_placebos.R - SOP W3.21, placebos P1 to P4.
#
#   Rscript R/ch1/26_placebos.R --table data/marts/ch1_called.parquet --out out
#
# P1  2023 -> 2024, both under the 2-inch-outside-the-edge buffer (CH1-A3). Two one-sided
#     equivalence tests on W3.15's primary draws: the 90% interval on the shadow-rate difference
#     lies entirely inside +/-0.5 pp AND the 90% interval on the area difference lies entirely
#     inside +/-3 sq in. No zero-coverage clause.
# P2  within-season false boundaries at each All-Star break: per season, the frozen
#     specification with the half-season in place of the season, fitted on that season's rows;
#     the placebo is second half minus first half on the standardised surface. The five give the
#     empirical null; the headline delta_abs (area) must exceed the 95th percentile of |placebo|
#     (R's default quantile, type 7). The edges are read the same way and reported.
# P3  AAA full-ABS days across seasons. Not run: SOP W3.20's AAA arm is blocked on D-11, D-12
#     and D-57, W3.9 is deferred (DEV-55), and the analysis table holds MLB pitches only.
# P4  pitches with |d| > 6 in: the called-strike rate outside (d > 6) and inside (d < -6), per
#     season, with Wilson 95% intervals. The SOP's rule, "rate about 0 or 1 and stable", carries
#     no number in the pre-registration, so P4 is reported as a table and its verdict is left to
#     the reader; no threshold is chosen after seeing the rates.
#
# Pre-registered consequence (PREREGISTRATION.md section 8): if P1 or P2 fails, the three-regime
# decomposition is reported as descriptive, the causal language is removed from every artifact,
# and the failure is the headline finding. W6.7 reads the verdicts from T5.
#
# WRITES, under --out: ch1/tab/T5_placebos.csv (one row per test), ch1/tab/T5_placebos_detail.csv
# (P2 per season, P4 per season), and the P2 fits under ch1/model/ with their receipts.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

P1_MARGIN <- c(shadow_rate = 0.5, area_sqin = 3)   # pp and sq in, CH1-A3
P2_Q <- 0.95
P4_D <- 6
MIN_HALF_ROWS <- 1000L

wilson <- function(k, n, z = 1.959964) {
  if (n == 0) return(c(NA_real_, NA_real_))
  ph <- k / n
  c0 <- (ph + z^2 / (2 * n)) / (1 + z^2 / n)
  h <- z * sqrt(ph * (1 - ph) / n + z^2 / (4 * n^2)) / (1 + z^2 / n)
  c(c0 - h, c0 + h)
}

test_row <- function(placebo, test, quantity, units, estimate, lo, hi, level, margin, headline, verdict, note) {
  data.frame(placebo = placebo, test = test, quantity = quantity, units = units, estimate = estimate, lo = lo, hi = hi,
             interval_level = level, margin_or_threshold = margin, headline_value = headline, verdict = verdict,
             note = note, stringsAsFactors = FALSE)
}

p1_tests <- function(ctx) {
  dm <- read_csv_plain(file.path(ctx$paths$model, "estimand_draws_main.csv"))
  t3 <- read_csv_plain(file.path(ctx$paths$tab, "T3_estimands.csv"))
  out <- list()
  for (q in names(P1_MARGIN)) {
    pt <- function(s) t3$point[t3$fit == "main" & t3$season == s & t3$estimand == q]
    est <- pt(2024) - pt(2023)
    dr <- dm[[paste("2024", q, sep = "_")]] - dm[[paste("2023", q, sep = "_")]]
    i90 <- qint(dr, 0.90)
    ok <- is.finite(i90[1]) && i90[1] > -P1_MARGIN[[q]] && i90[2] < P1_MARGIN[[q]]
    units <- if (q == "shadow_rate") "pp" else "sq in"
    out[[q]] <- test_row("P1", sprintf("TOST, 90%% interval inside +/-%s %s", P1_MARGIN[[q]], units),
                         paste(q, "2024 minus 2023"), units, est, i90[1], i90[2], 0.90, P1_MARGIN[[q]], NA,
                         if (ok) "pass" else "fail", "W3.15 primary draws; no zero-coverage clause (CH1-A3)")
    record(sprintf("P1 %s", q), sprintf("%s %s, 90%% CI %s to %s against +/-%s: %s", num_txt(est, units), units,
                                        num_txt(i90[1], units), num_txt(i90[2], units), P1_MARGIN[[q]], if (ok) "pass" else "FAIL"))
  }
  do.call(rbind, out)
}

p2_fits <- function(ctx, prim, ref) {
  vals <- list()
  for (s in SEASONS) {
    rows <- surface_rows(prim[prim$season == s, ])
    rows$half <- season_half(rows)
    rows <- rows[!is.na(rows$half), ]
    nh <- table(factor(rows$half, levels = c("first", "second")))
    if (any(nh < MIN_HALF_ROWS)) {
      record(sprintf("P2 %d", s), sprintf("not estimable: %d first-half and %d second-half rows", nh[1], nh[2]))
      next
    }
    spec <- make_spec("half")
    ft <- fit_surface(fit_frame(rows, spec), spec)
    check(sprintf("P2 %d: bam converged", s), ft$converged,
          sprintf("%s rows (%s first half, %s second), %.0f s", comma(nrow(rows)), comma(nh[1]), comma(nh[2]), ft$seconds))
    mix <- ref_mix(ft$m, ft$spec, ref, "first")
    e1 <- surface_estimands(ft$m, ft$spec, mix, "first", ref, geom_only = TRUE)$point
    e2 <- surface_estimands(ft$m, ft$spec, mix, "second", ref, geom_only = TRUE)$point
    vals[[as.character(s)]] <- e2[GEOM] - e1[GEOM]
    name <- sprintf("placebo_p2_%d", s)
    f <- file.path(ctx$paths$model, sprintf("surface_%s.rds", name))
    ensure_dir(ctx$paths$model)
    saveRDS(list(m = ft$m, spec = ft$spec, fit = name, n_rows = nrow(rows)), f)
    write_receipt(ctx, provenance(ctx, sprintf("surface_%s", name), rows, NA, ctx$paths$model,
                                  extra = list(formula = spec$formula, n_coef = ft$n_coef, edf = ft$edf,
                                               fit_seconds = ft$seconds, files = list(basename(f)))),
                  ctx$paths$model)
    record(sprintf("P2 %d second minus first", s), paste(sprintf("%s %.3f", GEOM, vals[[as.character(s)]]), collapse = ", "))
  }
  vals
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE))
  ctx <- start_run("W3.21", opt, "R/ch1/26_placebos.R")
  p <- ctx$paths
  cal <- read_calibration(ctx, opt)
  d <- load_table(ctx)
  prim <- apply_heights(d, primary_height_rule(opt), cal, ctx)
  ref <- surface_rows(prim[prim$season == as.integer(REF_SEASON), ])
  t4 <- read_csv_plain(file.path(p$tab, "T4_decomposition.csv"))

  rows <- list(p1_tests(ctx))
  p1_ok <- all(rows[[1]]$verdict == "pass")

  vals <- p2_fits(ctx, prim, ref)
  detail <- list()
  p2_ok <- NA
  for (e in GEOM) {
    v <- vapply(vals, function(x) x[[e]], 0)
    q95 <- if (length(v) > 0L) unname(stats::quantile(abs(v), P2_Q, type = 7)) else NA_real_
    dabs <- t4$point[t4$estimand == e & t4$component == "delta_abs"]
    ok <- is.finite(q95) && abs(dabs) > q95
    units <- ESTIMAND_UNITS[[e]]
    rows[[length(rows) + 1L]] <- test_row(
      "P2", sprintf("|delta_abs| > 95th percentile of |placebo| over %d All-Star-break boundaries", length(v)),
      paste(e, "second half minus first half"), units, if (length(v)) mean(v) else NA, if (length(v)) min(v) else NA,
      if (length(v)) max(v) else NA, NA, q95, dabs, if (!is.finite(q95)) "not run" else if (ok) "pass" else "fail",
      sprintf("estimate, lo, hi: mean, min and max of the %d placebos; %s", length(v),
              if (e == "area_sqin") "the headline test" else "reported beside the headline"))
    if (e == "area_sqin") p2_ok <- is.finite(q95) && ok
    for (s in names(v)) detail[[length(detail) + 1L]] <- data.frame(placebo = "P2", season = as.integer(s), quantity = e,
                                                                     value = v[[s]], n = NA, lo95 = NA, hi95 = NA,
                                                                     stringsAsFactors = FALSE)
    record(sprintf("P2 %s", e), sprintf("|delta_abs| %.3f against the 95th percentile of |placebo| %.3f: %s", abs(dabs), q95,
                                        if (!is.finite(q95)) "not run" else if (ok) "pass" else "FAIL"))
  }
  rows[[length(rows) + 1L]] <- test_row("P3", "machine zone does not move, net of each season's published rule (D-P4-29)",
                                        "AAA full-ABS rule-net area", "sq in", NA, NA, NA, 0.90, 3, NA, "not run",
                                        "SOP W3.20's AAA arm is blocked on D-11, D-12 and D-57 (DEV-55); the analysis table holds MLB pitches only")
  for (side in c("outside", "inside")) {
    r <- prim[if (side == "outside") prim$d > P4_D else prim$d < -P4_D, ]
    per <- lapply(SEASONS, function(s) {
      k <- sum(r$cs[r$season == s]); n <- sum(r$season == s)
      w <- wilson(k, n)
      data.frame(placebo = "P4", season = s, quantity = sprintf("called-strike rate, d %s %d in", if (side == "outside") ">" else "< -", P4_D),
                 value = if (n > 0) k / n else NA, n = n, lo95 = w[1], hi95 = w[2], stringsAsFactors = FALSE)
    })
    per <- do.call(rbind, per)
    detail[[length(detail) + 1L]] <- per
    rows[[length(rows) + 1L]] <- test_row(
      "P4", "rate about 0 or 1 and stable across seasons; no numeric threshold is pre-registered",
      per$quantity[1], "rate", NA, min(per$value, na.rm = TRUE), max(per$value, na.rm = TRUE), NA, NA, NA, "reported",
      sprintf("lo, hi: the lowest and highest season rate; per season in T5_placebos_detail.csv; largest season-to-season change %.4f",
              max(abs(diff(per$value)), na.rm = TRUE)))
    record(sprintf("P4 %s", side), paste(sprintf("%d %.4f (n %s)", per$season, per$value, comma(per$n)), collapse = "; "))
  }
  t5 <- do.call(rbind, rows)
  t5$placebo_verdict <- ifelse(t5$placebo == "P1", if (p1_ok) "pass" else "fail",
                        ifelse(t5$placebo == "P2", if (isTRUE(p2_ok)) "pass" else if (is.na(p2_ok)) "not run" else "fail",
                        ifelse(t5$placebo == "P3", "not run", "reported")))
  descriptive <- !(p1_ok && isTRUE(p2_ok))
  t5$decomposition_reading <- if (descriptive) "descriptive" else "as pre-registered"
  write_csv_plain(t5, file.path(p$tab, "T5_placebos.csv"))
  write_csv_plain(do.call(rbind, detail), file.path(p$tab, "T5_placebos_detail.csv"))
  record("P1 (CH1-A3)", if (p1_ok) "pass" else "FAIL")
  record("P2", if (isTRUE(p2_ok)) "pass" else if (is.na(p2_ok)) "not run" else "FAIL")
  if (descriptive) {
    cat(paste("CONSEQUENCE  P1 or P2 did not pass. Pre-registered: the three-regime decomposition is reported as",
              "descriptive, the causal language is removed from every artifact, and the failure is the headline",
              "finding. Record it in docs/DEVIATIONS.md with a Madrid stamp and raise it as an owner item.\n"))
  }
  step_receipt(ctx, rows = d, inputs = c(file.path(p$tab, "T3_estimands.csv"), file.path(p$tab, "T4_decomposition.csv"),
                                         file.path(p$model, "estimand_draws_main.csv")),
               outputs = c(file.path(p$tab, "T5_placebos.csv"), file.path(p$tab, "T5_placebos_detail.csv")))
  finish("W3.21")
}

if (identical(environment(), globalenv()) && !interactive()) main()
