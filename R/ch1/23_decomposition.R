#!/usr/bin/env Rscript
# R/ch1/23_decomposition.R - SOP W3.16, the three-regime decomposition.
#
#   Rscript R/ch1/23_decomposition.R --table data/marts/ch1_called.parquet --out out
#
# For each estimand theta_s of W3.15 (2022-24 pre-buffer, 2025 buffer, 2026 ABS):
#   g            the 2022-2024 pre-trend, a precision-weighted linear season slope
#   delta_buffer theta_2025 - (theta_2024 + g)
#   delta_abs    theta_2026 - (theta_2025 + g)
#   delta_total  theta_2026 - theta_2024
#   share_abs    delta_abs / (delta_abs + delta_buffer), reported only when the 95% interval on
#                delta_abs + delta_buffer excludes zero (CH1-A9, D-59)
# Every interval is a percentile interval over the joint draws of W3.15: each draw's five season
# values give that draw's g and components (R/lib/ch1_decomp.R). The two components, each with
# its 95% interval, are the primary result (CH1-A4); the identity delta_buffer + delta_abs + 2g =
# delta_total is asserted to 1e-9 on every row and written as its own column.
#
# Beside each primary row, the pre-registered comparisons:
#   abs_cohort_*  the ABS-measured arm, with sign_agrees_abs_cohort on each component row.
#                 D-P4-04, part 3: it must agree in sign with the primary on the buffer and ABS
#                 components, or the primary is reported as sensitive to the height cohort. The
#                 verdict is read on area_sqin, the quantity of the headline and of D_BUF and
#                 D_ABS; the edges' signs are reported beside it. height_cohort_flag carries the
#                 verdict on every row: "agree" or "primary is sensitive to the height cohort".
#                 W6.7 reads it.
#   single_offset_* SENS-HEIGHT-SINGLE (PREREGISTRATION.md section 7), with
#                 sign_agrees_single_offset on each component row. Its signs are reported only:
#                 the pre-registration gives this arm no clause.
#   panel_*       the CH1-A14 balanced umpire panel, with panel minus primary as a number
#   binned_*      the CH1-A5 cross-check: the binned logistic's own decomposition, inside the bam
#                 95% interval and within 0.15 in (edges) or 3 sq in (area)
#   undersmooth_* SENS-B1-UNDERSMOOTH (annex 8.7): the top edge from the fit with the season
#                 by-term at k = 24, on the top_in rows only, beside the primary and never in
#                 its place
#   recovery_disclosure  on the top_in and half_width_in rows, the recovery clauses annex 8.7
#                 reports as not met, disclosed beside the intervals they qualify (D-R0-04)
#
# WRITES, under --out:
#   ch1/tab/T4_decomposition.csv       the primary, one row per estimand and component
#   ch1/tab/T4_decomposition_arms.csv  the full decomposition of every other fit, each labelled
#                                      with its arm (ARM_LABEL) beside the fit name
#   tables/headline.csv                W3.16's row, keyed CH1_W316: one descriptive sentence.
#                                      W3.21 reads CH1-A3 later, so no sentence here claims more
#                                      than a decomposition of the change.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

A5_TOL <- c(top_in = 0.15, bot_in = 0.15, half_width_in = 0.15, area_sqin = 3)   # annex 5, CH1-A5
EST_LABEL <- c(main = "bam primary: P0, roster + cohort-specific offset",
               abs_cohort = "bam ABS-measured arm: P1, H_abs",
               single_offset = "bam SENS-HEIGHT-SINGLE: P0, roster + D-R0-02's one offset for every batter",
               panel = "bam balanced umpire panel (CH1-A14)",
               binned = "binned logistic (annex 5, CH1-A5)",
               undersmooth = "bam SENS-B1-UNDERSMOOTH: P0, season by-term k = 24 (annex 8.7)")
ARMS <- setdiff(FIT_ARMS, "main")

decompose_fit <- function(ctx, t3, fit) {
  f <- file.path(ctx$paths$model, sprintf("estimand_draws_%s.csv", fit))
  if (!file.exists(f)) return(NULL)
  dr <- read_csv_plain(f)
  pts <- t3[t3$fit == fit, ]
  out <- list()
  for (e in unique(pts$estimand)) {
    p5 <- vapply(SEASON_LEVELS, function(s) pts$point[pts$season == as.integer(s) & pts$estimand == e], 0)
    d5 <- as.matrix(dr[, paste(SEASON_LEVELS, e, sep = "_")])
    res <- decompose_estimand(p5, d5, e, ESTIMAND_UNITS[[e]])
    tb <- res$table
    tb$ci95_half_width <- (tb$hi95 - tb$lo95) / 2
    src <- if (fit == "binned") "each edge glm's N(beta, vcov)" else "N(beta, Vc), W3.14"
    tb$estimator <- sprintf("%s; 95%% percentile interval over %d joint draws of %s", EST_LABEL[[fit]],
                            res$table$n_draws[1], src)
    out[[e]] <- cbind(fit = fit, arm = ARM_LABEL[[fit]], tb, stringsAsFactors = FALSE)
  }
  do.call(rbind, out)
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE))
  ctx <- start_run("W3.16", opt, "R/ch1/23_decomposition.R")
  p <- ctx$paths
  t3 <- read_csv_plain(file.path(p$tab, "T3_estimands.csv"))
  dec <- lapply(setNames(c("main", ARMS), c("main", ARMS)), function(f) decompose_fit(ctx, t3, f))
  if (is.null(dec$main)) die("no W3.15 draws for the primary fit")
  missing_arms <- ARMS[vapply(ARMS, function(a) is.null(dec[[a]]), TRUE)]
  check("every pre-registered arm has W3.15 draws", length(missing_arms) == 0L,
        if (length(missing_arms)) paste("missing:", paste(missing_arms, collapse = ", ")) else paste(ARMS, collapse = ", "))
  prim <- dec$main
  resid <- max(abs(unlist(lapply(Filter(Negate(is.null), dec), function(x) x$identity_residual))))
  check("identity delta_buffer + delta_abs + 2g = delta_total", resid < IDENTITY_TOL,
        sprintf("max |residual| %.2e over every fit, estimand, point and draw", resid))

  key <- function(x) paste(x$estimand, x$component)
  side <- function(arm, cols) {
    a <- dec[[arm]]
    if (is.null(a)) return(matrix(NA_real_, nrow(prim), length(cols)))
    as.matrix(a[match(key(prim), key(a)), cols])
  }
  ab <- side("abs_cohort", c("point", "lo95", "hi95"))
  prim$abs_cohort_point <- ab[, 1]; prim$abs_cohort_lo95 <- ab[, 2]; prim$abs_cohort_hi95 <- ab[, 3]
  comp_rows <- prim$component %in% c("delta_buffer", "delta_abs")
  prim$sign_agrees_abs_cohort <- ifelse(comp_rows & is.finite(prim$abs_cohort_point),
                                        sign(prim$point) == sign(prim$abs_cohort_point), NA)
  so <- side("single_offset", c("point", "lo95", "hi95"))
  prim$single_offset_point <- so[, 1]; prim$single_offset_lo95 <- so[, 2]; prim$single_offset_hi95 <- so[, 3]
  prim$sign_agrees_single_offset <- ifelse(comp_rows & is.finite(prim$single_offset_point),
                                           sign(prim$point) == sign(prim$single_offset_point), NA)
  # D-P4-04, part 3, read on the area's two components; one verdict, on every row.
  ag <- prim$sign_agrees_abs_cohort[prim$estimand == CLAUSE_ESTIMAND & prim$component %in% c("delta_buffer", "delta_abs")]
  prim$height_cohort_flag <- height_cohort_flag(ag)
  prim$height_cohort_flag_read_on <- sprintf("%s delta_buffer and delta_abs, ABS-measured arm against the primary",
                                             CLAUSE_ESTIMAND)
  pn <- side("panel", c("point", "lo95", "hi95"))
  prim$panel_point <- pn[, 1]; prim$panel_lo95 <- pn[, 2]; prim$panel_hi95 <- pn[, 3]
  prim$panel_minus_primary <- prim$panel_point - prim$point
  bn <- side("binned", c("point", "lo95", "hi95"))
  prim$binned_point <- bn[, 1]
  prim$binned_minus_bam <- prim$binned_point - prim$point
  prim$binned_inside_bam95 <- prim$binned_point >= prim$lo95 & prim$binned_point <= prim$hi95
  prim$ch1_a5_tolerance <- ifelse(comp_rows & prim$estimand %in% names(A5_TOL), A5_TOL[prim$estimand], NA)
  prim$ch1_a5_within <- ifelse(is.na(prim$ch1_a5_tolerance), NA,
                               prim$binned_inside_bam95 & abs(prim$binned_minus_bam) <= prim$ch1_a5_tolerance)
  us <- side("undersmooth", c("point", "lo95", "hi95"))
  prim$undersmooth_point <- us[, 1]; prim$undersmooth_lo95 <- us[, 2]; prim$undersmooth_hi95 <- us[, 3]
  prim$undersmooth_minus_primary <- prim$undersmooth_point - prim$point
  prim$recovery_disclosure <- ifelse(prim$estimand %in% names(RECOVERY_NOTE), unname(RECOVERY_NOTE[prim$estimand]), "")
  write_csv_plain(prim, file.path(p$tab, "T4_decomposition.csv"))
  arms <- do.call(rbind, dec[ARMS])
  if (!is.null(arms)) write_csv_plain(arms, file.path(p$tab, "T4_decomposition_arms.csv"))

  # the pre-registered readings, printed; none of them changes a number
  a <- prim[prim$estimand == "area_sqin", ]
  row <- function(k) a[a$component == k, ]
  for (k in c("g", "delta_buffer", "delta_abs", "delta_total")) {
    r <- row(k)
    record(sprintf("area_sqin %s", k), sprintf("%s (%s)", num_txt(r$point, "sq in"), ci_txt(r$lo95, r$hi95, "sq in")))
  }
  for (e in c("top_in", "bot_in", "half_width_in")) for (k in c("delta_buffer", "delta_abs")) {
    r <- prim[prim$estimand == e & prim$component == k, ]
    record(sprintf("%s %s", e, k), sprintf("%s in (%s)", num_txt(r$point, "in"), ci_txt(r$lo95, r$hi95, "in")))
  }
  sh <- row("share_abs")
  record("CH1-A9 share_abs", if (isTRUE(sh$reported)) sprintf("reported: %.3f (95%% CI %.3f to %.3f)", sh$point, sh$lo95, sh$hi95)
         else "not reported: the 95% interval on delta_abs + delta_buffer includes zero")
  for (k in c("delta_buffer", "delta_abs")) {
    r <- row(k)
    record(sprintf("CH1-A4 area %s", k), sprintf("95%% half-width %.2f sq in; %s", r$ci95_half_width,
           if (r$lo95 <= 0 && r$hi95 >= 0) sprintf("a null, reportable when the half-width is <= 3 sq in (%s)",
                                                    if (r$ci95_half_width <= 3) "it is" else "it is not")
           else "the interval excludes zero"))
  }
  flag <- prim$height_cohort_flag[1]
  check("D-P4-04 clause evaluated", flag %in% c(CLAUSE_AGREE, CLAUSE_SENSITIVE), flag)
  if (!is.null(dec$abs_cohort)) {
    ag <- prim[comp_rows & prim$estimand %in% GEOM, ]
    record("D-P4-04 sign agreement, ABS-measured arm", sprintf("height_cohort_flag: %s (area, both components); %d of %d geometric components agree in sign",
           flag, sum(ag$sign_agrees_abs_cohort, na.rm = TRUE), nrow(ag)))
    if (identical(flag, CLAUSE_SENSITIVE)) cat("OWNER   D-P4-04: the ABS-measured arm disagrees in sign; the primary is sensitive to the height cohort.\n")
  }
  if (!is.null(dec$single_offset)) {
    for (k in c("delta_buffer", "delta_abs")) {
      r <- row(k)
      record(sprintf("SENS-HEIGHT-SINGLE area %s", k), sprintf("%s sq in (%s); sign %s the primary's (reported, no clause)",
             num_txt(r$single_offset_point, "sq in"), ci_txt(r$single_offset_lo95, r$single_offset_hi95, "sq in"),
             if (isTRUE(r$sign_agrees_single_offset)) "agrees with" else "DIFFERS from"))
    }
    so_ag <- prim[comp_rows & prim$estimand %in% GEOM, ]
    record("SENS-HEIGHT-SINGLE signs", sprintf("%d of %d geometric components agree in sign with the primary",
                                              sum(so_ag$sign_agrees_single_offset, na.rm = TRUE), nrow(so_ag)))
  }
  if (!is.null(dec$panel)) {
    for (k in c("delta_buffer", "delta_abs")) record(sprintf("CH1-A14 panel minus primary, area %s", k),
                                                     sprintf("%s sq in", num_txt(row(k)$panel_minus_primary, "sq in")))
  }
  if (!is.null(dec$binned)) {
    b <- prim[!is.na(prim$ch1_a5_within), ]
    record("CH1-A5 binned logistic against bam", sprintf("%d of %d quantities within tolerance and inside the bam 95%% interval%s",
           sum(b$ch1_a5_within), nrow(b), if (all(b$ch1_a5_within)) "" else "; the rest are a limitation, reported as such"))
  }
  if (!is.null(dec$undersmooth)) {
    for (k in c("delta_buffer", "delta_abs")) {
      r <- prim[prim$estimand == "top_in" & prim$component == k, ]
      record(sprintf("SENS-B1-UNDERSMOOTH top_in %s", k),
             sprintf("season k = 24: %s in (%s); primary, k = 18: %s in (%s)", num_txt(r$undersmooth_point, "in"),
                     ci_txt(r$undersmooth_lo95, r$undersmooth_hi95, "in"), num_txt(r$point, "in"), ci_txt(r$lo95, r$hi95, "in")))
    }
  }

  # W3.16's headline row: the two components, descriptive. W3.21 has not read CH1-A3 yet, so
  # the sentence claims no cause. 33 words at most, under the 34-word rule.
  buf <- row("delta_buffer"); abs_ <- row("delta_abs")
  sentence <- sprintf(paste("Net of the 2022-2024 trend, the standardised called-zone area changed by %s sq in (%s)",
                            "in 2025 and by %s sq in (%s) in 2026."),
                      num_txt(buf$point, "sq in"), ci_txt(buf$lo95, buf$hi95, "sq in"),
                      num_txt(abs_$point, "sq in"), ci_txt(abs_$lo95, abs_$hi95, "sq in"))
  hl <- data.frame(id = "CH1_W316", step = "W3.16", chapter = "1", sentence = sentence, estimand = "area_sqin delta_abs",
                   point = abs_$point, lo95 = abs_$lo95, hi95 = abs_$hi95, units = "sq in",
                   estimator = abs_$estimator, source_csv = "out/ch1/tab/T4_decomposition.csv",
                   source_row = which(prim$estimand == "area_sqin" & prim$component == "delta_abs"),
                   stringsAsFactors = FALSE)
  f_hl <- file.path(p$tables, "headline.csv")
  how <- upsert_row(f_hl, hl)
  record("headline", sprintf("%s: %s", how, sentence))
  step_receipt(ctx, inputs = c(file.path(p$tab, "T3_estimands.csv"),
                               file.path(p$model, sprintf("estimand_draws_%s.csv", names(Filter(Negate(is.null), dec))))),
               outputs = c(file.path(p$tab, "T4_decomposition.csv"), file.path(p$tab, "T4_decomposition_arms.csv"), f_hl))
  finish("W3.16")
}

if (identical(environment(), globalenv()) && !interactive()) main()
