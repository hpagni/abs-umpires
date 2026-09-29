#!/usr/bin/env Rscript
# R/ch1/20_surfaces.R - SOP W3.14, the Chapter 1 called-strike surfaces.
#
#   Rscript R/ch1/20_surfaces.R --table data/marts/ch1_called.parquet --out out
#   Rscript R/ch1/20_surfaces.R --table <table> --out <root> --fits main,abs_cohort,panel,binned,undersmooth
#
# WHAT IT FITS. The frozen specification of docs/prereg/ch1.md section 2, with mgcv::bam(family =
# binomial, discrete = TRUE, method = "fREML"), on the open window 2022-01-01 to the last open
# day, |d| <= 8.0 in, the four games without ABS hardware removed (PREREGISTRATION.md section 7):
#   main        P0 on the primary height rule, roster + cohort-specific offset (D-R0-02, D-P4-04)
#   abs_cohort  P1 on H_abs, the D-R0-02 robustness arm, for D-P4-04's sign-agreement clause
#   panel       the CH1-A14 balanced umpire panel: >= 15 home-plate games in every season
#   binned      the binned logistic of annex section 5, the CH1-A5 secondary estimator
#   undersmooth SENS-B1-UNDERSMOOTH (annex 8.7, D-R0-04): main's rows, the season by-term at
#               k = 24 and every other k as frozen; W3.16 reports its top edge beside the primary
# Season enters as a five-level factor with 2022 as the reference, and s(umpire_hp_id) and
# s(umpire_season) carry the umpire effects. The smooth is on the re-projected mid-plane pair,
# x_mid and zn, never on the raw plate_x and plate_z: Statcast publishes those at the front of
# the plate through 2025 and at the middle from 2026, so a surface on the raw pair would read
# the plane change as a zone change.
#
# WHAT IT WRITES, under --out (out/ for the real run):
#   ch1/model/surface_<fit>.rds    the fitted object, its spec and the height rule
#   ch1/model/draws_vc_<fit>.rds   1,000 draws from N(beta, Vc) by MASS::mvrnorm, seed 20260922,
#                                  a 1,000 x coefficients matrix. Vc is the covariance corrected
#                                  for smoothing-parameter uncertainty (annex 8.7, DEV-60), so the
#                                  file is draws_vc, not the draws_vp of the fleet's older gate.
#                                  W3.15 to W3.21 take every interval from these draws and never
#                                  refit for one.
#   ch1/model/surface_binned.rds   the three per-edge glm fits
#   ch1/model/provenance.json      the union of this directory's fit receipts (GD-01)
#   models/surface_<fit>/provenance.json, one receipt per fit, the SOP section 1.4 keys
# surface_framing.rds is SOP W3.19's and is not fitted here.
#
# GUARDS. start_run() refuses a real table unless `git merge-base --is-ancestor prereg-v1 HEAD`
# succeeds and the fit code is committed (GD-12), and refuses to write a synthetic run inside the
# repository. The loader reads no row after the last open day (the seal). Exit 0 when every check
# passes, 1 when one fails, 4 when a guard refuses.
#
# COST. The annex section 4 scale test puts one five-season fit on about 1.15 million rows at
# about 10 minutes and 2.6 GB, single-threaded. The fits can run as separate processes with
# --fits; each writes its own files, and the receipt union is rewritten under a lock.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

ALL_FITS <- c("main", "abs_cohort", "panel", "binned", "undersmooth")

# The one read: the analysis table, open rows only, through the loader's scan filter.
surface_frame <- function(ctx) {
  load_table(ctx)
}

fit_one <- function(ctx, name, rows, height_rule, kind = "main") {
  p <- ctx$paths
  spec <- make_spec(kind)
  ff <- fit_frame(rows, spec)
  ft <- fit_surface(ff, spec)
  check(sprintf("%s: bam converged", name), ft$converged,
        sprintf("%s rows, %s coefficients, edf %.1f, largest fREML gradient %.1e, %.0f s", comma(nrow(rows)),
                comma(ft$n_coef), ft$edf, ft$grad_max, ft$seconds))
  if (length(ft$warnings) > 0L) record(sprintf("%s: bam warnings", name), paste(ft$warnings, collapse = " | "))
  cd <- coef_draws(ft$m, ctx$n_draws, DRAW_SEED)
  sdr <- sqrt(diag(ft$m[[INTERVAL_COV]]) / diag(ft$m$Vp))
  check(sprintf("%s: %d draws from N(beta, %s)", name, ctx$n_draws, INTERVAL_COV),
        identical(dim(cd), c(ctx$n_draws, ft$n_coef)) && all(is.finite(cd)),
        sprintf("sd(Vc)/sd(Vp) median %.3f, max %.3f", stats::median(sdr), max(sdr)))
  ensure_dir(p$model)
  fit_file <- file.path(p$model, sprintf("surface_%s.rds", name))
  draw_file <- file.path(p$model, sprintf("draws_vc_%s.rds", name))
  saveRDS(list(m = ft$m, spec = ft$spec, fit = name, height_rule = height_rule, n_rows = nrow(rows),
               seconds = ft$seconds, warnings = ft$warnings), fit_file)
  saveRDS(cd, draw_file)
  prov <- provenance(ctx, sprintf("surface_%s", name), rows, DRAW_SEED, p$model,
                     extra = list(formula = spec$formula, family = "binomial", method = "fREML", discrete = TRUE,
                                  n_coef = ft$n_coef, edf = ft$edf, fit_seconds = ft$seconds,
                                  converged = ft$converged, freml_grad_max = ft$grad_max,
                                  height_rule = height_rule, n_draws = ctx$n_draws, interval_cov = INTERVAL_COV,
                                  draw_seed = DRAW_SEED, files = list(basename(fit_file), basename(draw_file)),
                                  n_umpires = length(unique(rows$umpire_hp_id)),
                                  rows_by_season = as.list(table(rows$season))))
  write_receipt(ctx, prov, p$model)
  record(sprintf("%s: written", name), sprintf("%s (%.0f MB), %s", fit_file, file.size(fit_file) / 1e6, draw_file))
  invisible(NULL)
}

fit_surfaces <- function(ctx, opt) {
  d <- surface_frame(ctx)
  cal <- read_calibration(ctx, opt)
  allow_single <- identical(opt_get(opt, "height-rule"), "single-offset")
  fits <- strsplit(opt_get(opt, "fits", paste(ALL_FITS, collapse = ",")), ",")[[1]]
  if (!all(fits %in% ALL_FITS)) die("unknown fit in --fits: ", paste(setdiff(fits, ALL_FITS), collapse = ","))
  prim <- apply_heights(d, "primary", cal, ctx, allow_single)
  hr <- attr(prim, "height_rule")
  if ("main" %in% fits) fit_one(ctx, "main", surface_rows(prim), hr)
  if ("undersmooth" %in% fits) {
    fit_one(ctx, "undersmooth", surface_rows(prim),
            sprintf("%s; SENS-B1-UNDERSMOOTH, season by-term k = %d", hr, UNDERSMOOTH_SEASON_K), kind = "undersmooth")
  }
  if ("panel" %in% fits) {
    u <- panel_umpires(prim)
    record("CH1-A14 balanced panel", sprintf("%d umpires with >= %d home-plate games in each of %s (%d at the freeze)",
                                             length(u), PANEL_MIN_GAMES, paste(SEASONS, collapse = ", "), PANEL_PREREG_N))
    if (!ctx$synthetic && length(u) != PANEL_PREREG_N) {
      record("CH1-A14 panel count differs from PREREGISTRATION.md section 7", sprintf("%d, not %d", length(u), PANEL_PREREG_N))
    }
    check("CH1-A14 panel is not empty", length(u) >= 3L, sprintf("%d umpires", length(u)))
    fit_one(ctx, "panel", surface_rows(prim[prim$umpire_hp_id %in% u, ]), paste(hr, "; balanced umpire panel"))
  }
  if ("abs_cohort" %in% fits) {
    p1 <- apply_heights(d, "abs", cal, ctx)
    fit_one(ctx, "abs_cohort", surface_rows(p1), attr(p1, "height_rule"))
  }
  if ("binned" %in% fits) {
    rows <- surface_rows(prim)
    agg <- aggregate_bins(rows)
    bf <- fit_binned(agg)
    ok <- all(vapply(bf, function(f) f$converged && !anyNA(stats::coef(f)), TRUE))
    check("binned: three edge glm fits converged, no aliased coefficient", ok,
          paste(sprintf("%s %d cells", EDGE_LEVELS, vapply(bf, function(f) nrow(f$model), 0L)), collapse = ", "))
    f_bin <- file.path(ctx$paths$model, "surface_binned.rds")
    ensure_dir(ctx$paths$model)
    saveRDS(list(fits = bf, height_rule = hr, n_rows = nrow(rows)), f_bin)
    prov <- provenance(ctx, "surface_binned", rows, NA, ctx$paths$model,
                       extra = list(formula = "glm(cbind(strikes, balls) ~ 0 + bin + season + count_class + stand), per edge",
                                    bins = "0.5 in over [-8, 8], 32 bins", height_rule = hr,
                                    files = list(basename(f_bin))))
    write_receipt(ctx, prov, ctx$paths$model)
    record("binned: written", f_bin)
  }
  invisible(NULL)
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE))
  ctx <- start_run("W3.14", opt, "R/ch1/20_surfaces.R")
  fit_surfaces(ctx, opt)
  finish("W3.14")
}

if (identical(environment(), globalenv()) && !interactive()) main()
