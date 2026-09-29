#!/usr/bin/env Rscript
# R/ch1/22_estimands.R - SOP W3.15, the estimands on the standardised grid.
#
#   Rscript R/ch1/22_estimands.R --table data/marts/ch1_called.parquet --out out
#   Rscript R/ch1/22_estimands.R --table <table> --out <root> --fits main,abs_cohort,panel,binned
#
# For each fit W3.14 wrote, each season 2022 to 2026 is evaluated on the 301 x 276 grid
# (x_mid -1.5 to 1.5 ft by 0.01, zn 0.15 to 0.70 by 0.002), standardised by g-computation to the
# 2024 reference mix of count class, handedness, pitch group and velocity of that fit's own
# sample, random effects at zero. From the 50% contour, for a 72-inch batter: top_in, bot_in,
# half_width_in, area_sqin (marching squares), shadow_rate and count_bias, defined in
# R/lib/ch1_estimands.R. count_bias is METHODS section 8's pre-registered estimand, reported here
# as a replication. Every interval comes from the 1,000 N(beta, Vc) draws W3.14 wrote; nothing
# is refitted. The binned logistic gives the four geometric estimands, with draws from each
# edge glm's own covariance, for the CH1-A5 comparison and its own pre-trend weights.
#
# WRITES, under --out:
#   ch1/tab/T3_estimands.csv                 one row per fit, season and estimand: point, 95% and
#                                            90% intervals, the estimator named
#   ch1/model/estimand_draws_<fit>.csv       one row per draw, one column per season x estimand;
#                                            W3.16 and W3.21 read their intervals from these
#
# It rebuilds each fit's sample with the loader and height rule W3.14 used and fails unless the
# row count and the table's sha256 match the fit's receipt.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

BAM_FITS <- c("main", "abs_cohort", "panel")
SAMPLE_OF <- c(main = "P0, roster + cohort-specific offset", abs_cohort = "P1, H_abs",
               panel = "P0 balanced umpire panel, roster + cohort-specific offset",
               binned = "P0, roster + cohort-specific offset")
BAM_LABEL <- "bam, frozen specification (annex 2); 95% interval from 1,000 draws of N(beta, Vc); 2024 reference mix; 72-in batter"
BIN_LABEL <- "binned logistic (annex 5), CH1-A5 secondary; interval from 1,000 draws of each edge glm's N(beta, vcov); 2024 count and stand mix"

fit_rows <- function(ctx, name, d, cal, opt) {
  allow_single <- identical(opt_get(opt, "height-rule"), "single-offset")
  if (name == "abs_cohort") return(surface_rows(apply_heights(d, "abs", cal, ctx)))
  prim <- apply_heights(d, "primary", cal, ctx, allow_single)
  if (name == "panel") prim <- prim[prim$umpire_hp_id %in% panel_umpires(prim), ]
  surface_rows(prim)
}

receipt_matches <- function(ctx, name, rows) {
  rp <- file.path(ctx$paths$models, sprintf("surface_%s", name), "provenance.json")
  if (!file.exists(rp)) die("no W3.14 receipt at ", rp)
  r <- fromJSON(rp)
  check(sprintf("%s: sample rebuilt as W3.14 fitted it", name),
        r$n_rows == nrow(rows) && identical(r$table_sha256, sha256_file(ctx$table)),
        sprintf("%s rows now, %s in the receipt; table sha256 %s", comma(nrow(rows)), comma(r$n_rows),
                if (identical(r$table_sha256, sha256_file(ctx$table))) "unchanged" else "CHANGED"))
}

t3_rows <- function(name, point, draws, estimator, n_rows) {
  out <- list()
  for (s in SEASON_LEVELS) for (e in colnames(point)) {
    v <- draws[, paste(s, e, sep = "_")]
    i95 <- qint(v, 0.95); i90 <- qint(v, 0.90)
    out[[length(out) + 1L]] <- data.frame(
      fit = name, sample = SAMPLE_OF[[name]], season = as.integer(s), regime = REGIME_OF[[s]], estimand = e,
      units = ESTIMAND_UNITS[[e]], point = point[s, e], lo95 = i95[1], hi95 = i95[2], lo90 = i90[1], hi90 = i90[2],
      n_draws = nrow(draws), n_complete = sum(is.finite(v)), estimator = estimator, n_rows_fit = n_rows,
      stringsAsFactors = FALSE)
  }
  do.call(rbind, out)
}

bam_estimands <- function(ctx, name, rows) {
  p <- ctx$paths
  obj <- readRDS(file.path(p$model, sprintf("surface_%s.rds", name)))
  cd <- readRDS(file.path(p$model, sprintf("draws_vc_%s.rds", name)))
  check(sprintf("%s: draws are %s draws of the fitted coefficients", name, attr(cd, "covariance")),
        identical(attr(cd, "covariance"), INTERVAL_COV) && identical(colnames(cd), names(stats::coef(obj$m))) &&
          nrow(cd) == ctx$n_draws,
        sprintf("%d x %d, seed %d", nrow(cd), ncol(cd), attr(cd, "seed")))
  ref <- rows[rows$season == as.integer(REF_SEASON), ]
  mix <- ref_mix(obj$m, obj$spec, ref, REF_SEASON)
  record(sprintf("%s: reference mix", name), sprintf("%s 2024 pitches, %d count x handedness cells, median velocity %.1f mph",
                                                     comma(nrow(ref)), length(mix$cells), mix$velo_ref))
  point <- matrix(NA_real_, length(SEASON_LEVELS), length(ESTIMANDS), dimnames = list(SEASON_LEVELS, ESTIMANDS))
  draws <- list()
  for (s in SEASON_LEVELS) {
    t0 <- proc.time()
    est <- surface_estimands(obj$m, obj$spec, mix, s, ref, cd)
    point[s, ] <- est$point[ESTIMANDS]
    dm <- est$draws[, ESTIMANDS, drop = FALSE]
    colnames(dm) <- paste(s, ESTIMANDS, sep = "_")
    draws[[s]] <- dm
    share <- est$diag$n_complete / nrow(cd)
    check(sprintf("%s %s: >= %.0f%% of draws complete", name, s, 100 * MIN_COMPLETE_SHARE), share >= MIN_COMPLETE_SHARE,
          sprintf("%d of %d; %d band points, %d draws re-read on the full grid; %.0f s", est$diag$n_complete, nrow(cd),
                  est$diag$n_band, est$diag$n_full_grid_draws, (proc.time() - t0)[["elapsed"]]))
    record(sprintf("%s %s point", name, s), paste(sprintf("%s %.3f", ESTIMANDS, point[s, ]), collapse = ", "))
  }
  check(sprintf("%s: every point estimate finite", name), all(is.finite(point)), "a closed 50% contour in every season")
  list(point = point, draws = do.call(cbind, draws), n_rows = obj$n_rows)
}

binned_block <- function(ctx, rows, n) {
  obj <- readRDS(file.path(ctx$paths$model, "surface_binned.rds"))
  w <- binned_ref_weights(rows[rows$season == as.integer(REF_SEASON), ])
  B <- binned_draws(obj$fits, n, DRAW_SEED)
  point <- t(vapply(SEASON_LEVELS, function(s) binned_estimands(obj$fits, w, s)[1, ], numeric(4)))
  draws <- do.call(cbind, lapply(SEASON_LEVELS, function(s) {
    m <- binned_estimands(obj$fits, w, s, B)
    colnames(m) <- paste(s, colnames(m), sep = "_")
    m
  }))
  check("binned: every point estimate finite", all(is.finite(point)), "four geometric estimands, five seasons")
  list(point = point, draws = draws, n_rows = obj$n_rows)
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE))
  ctx <- start_run("W3.15", opt, "R/ch1/22_estimands.R")
  fits <- strsplit(opt_get(opt, "fits", "main,abs_cohort,panel,binned"), ",")[[1]]
  cal <- read_calibration(ctx, opt)
  d <- load_table(ctx)
  t3 <- list()
  for (name in fits) {
    rows <- fit_rows(ctx, if (name == "binned") "main" else name, d, cal, opt)
    if (name == "binned") {
      res <- binned_block(ctx, rows, ctx$n_draws)
      est_label <- BIN_LABEL
    } else {
      receipt_matches(ctx, name, rows)
      res <- bam_estimands(ctx, name, rows)
      est_label <- BAM_LABEL
    }
    t3[[name]] <- t3_rows(name, res$point, res$draws, est_label, res$n_rows)
    write_csv_plain(data.frame(draw = seq_len(nrow(res$draws)), res$draws, check.names = FALSE),
                    file.path(ctx$paths$model, sprintf("estimand_draws_%s.csv", name)))
  }
  tab <- do.call(rbind, t3)
  f3 <- file.path(ctx$paths$tab, "T3_estimands.csv")
  # --fits lets the fits run as separate processes; each replaces its own rows under the lock.
  tab <- with_lock(ctx$paths$tab, {
    if (file.exists(f3) && !setequal(fits, c(BAM_FITS, "binned"))) {
      old <- read_csv_plain(f3)
      tab <- rbind(old[!old$fit %in% fits, names(tab)], tab)
      tab <- tab[order(match(tab$fit, c(BAM_FITS, "binned"))), ]
    }
    write_csv_plain(tab, f3)
    tab
  })
  m <- tab[tab$fit == "main", ]
  if (nrow(m) > 0L) {
    check("T3: five seasons and six estimands for the primary fit",
          setequal(m$season, SEASONS) && setequal(m$estimand, ESTIMANDS) && nrow(m) == 30L,
          sprintf("%d rows", nrow(m)))
  }
  record("written", sprintf("%s, %d rows", f3, nrow(tab)))
  step_receipt(ctx, rows = d, seed = DRAW_SEED,
               suffix = if (setequal(fits, c(BAM_FITS, "binned"))) "" else paste(fits, collapse = "_"),
               inputs = c(file.path(ctx$paths$model, sprintf("draws_vc_%s.rds", intersect(fits, BAM_FITS))),
                          if ("binned" %in% fits) file.path(ctx$paths$model, "surface_binned.rds")),
               outputs = c(f3, file.path(ctx$paths$model, sprintf("estimand_draws_%s.csv", fits))),
               extra = list(fits = as.list(fits)))
  finish("W3.15")
}

if (identical(environment(), globalenv()) && !interactive()) main()
