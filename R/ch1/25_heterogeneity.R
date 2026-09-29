#!/usr/bin/env Rscript
# R/ch1/25_heterogeneity.R - SOP W3.18, umpire heterogeneity: stages B1, B2 and B3.
#
#   Rscript R/ch1/25_heterogeneity.R --table data/marts/ch1_called.parquet --out out
#
# B1  delta per umpire-season-edge on the shadow band of annex 8.1, |d| <= 3.0 in on the
#     ball-centre d (b1_band()), against the pooled league link g_{e,r}(d) of its edge and regime,
#     over [-4, 4] in by 0.01 in, with a profile SE. The link is glm(cs ~ ns(d, 6)) on that edge's
#     |d| <= 8 in pitches of that regime, pooled over umpires: the form of the W3.12 calibration
#     link, one per edge and regime as SOP W3.18 writes g_{e,r}. delta is then each umpire's offset
#     from his regime's league link, so the league steps in B2 sit near zero and tau is unchanged.
# B2  five brms fits on the B1 cells (annex 8.2 and 8.8, R/lib/ch1_hetero.R B2_FITS):
#       sop             the primary; it sets CH1-A6
#       sens_abs_prior  SENS-B2-ABS-PRIOR, the SOP's normal(0, 1) on abs_step
#       sens_sd_exp1/4  the SOP's prior sensitivity, exponential(1) and exponential(4) on tau
#       ue_us           the sensitivity estimator; its MT-05 is read here (DEV-64)
#     Sampler settings of annex 8.2, seed 20260922, the MT-05 escalation on every fit.
# B3  split-half, odd and even plate games by game index within umpire-season, Spearman-Brown
#     corrected, for the 2025-to-2026 response and for the level.
#
# CH1-A6 as annex 8.5 pre-registers it: tau is reported with its interval; "material" only if
# P(tau >= 0.20 in) >= 0.90 in the sop fit; otherwise the bounded null, the posterior median of
# tau and the larger of the sop and ue_us one-sided 95% upper bounds. The per-umpire table is
# published only if out/tables/ch1_power_curve.csv shows the reliability gate attainable; the
# curve at the tag does not (annex 8.4 step 3), so under D-21 no per-umpire row leaves
# ch1/model/, which git ignores.
#
# WRITES, under --out:
#   ch1/tab/T6_heterogeneity.csv   every B2 fit's tau, tau_buf, correlation, sigma, league steps,
#                                  MT-05 diagnostics; B3; the prior-sensitivity reading; CH1-A6
#   ch1/tab/umpire_eb.csv          the empirical-Bayes summary W6.8 reads: aggregate rows only
#                                  unless the gate is attainable
#   ch1/model/umpire_me.rds        the sop fit; umpire_me_<fit>.rds for the others; b1 cells
#   models/umpire_me*/provenance.json and ch1/model/provenance.json

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))

sampler_settings <- function(ctx, opt, key) {
  st <- STAN_SETTINGS[[B2_FITS[[key]]$settings]]
  if (ctx$synthetic) {
    for (k in c("chains", "warmup", "sampling")) {
      v <- opt[[paste0("stan-", k)]]
      if (!is.null(v)) st[[k]] <- as.integer(v)
    }
  }
  st
}

t6_rows <- function(key, res, s, n_cells) {
  q <- c("tau_abs", "tau_buf", "sd_intercept", "cor_buf_abs", "sigma", "fps_sd_abs",
         paste0("league_abs_step_", EDGE_LEVELS))
  dg <- res$diagnostics
  do.call(rbind, lapply(q, function(k) data.frame(
    fit = key, prior = res$spec$label, quantity = k, median = s[[k]][["median"]], lo95 = s[[k]][["lo95"]],
    hi95 = s[[k]][["hi95"]], upper95 = s[[k]][["upper95"]], units = if (k == "cor_buf_abs") "correlation" else "in",
    n_umpires = s$n_umpires, n_cells = n_cells, chains = res$settings$chains, warmup = res$settings$warmup,
    sampling = res$settings$sampling, adapt_delta = res$settings$adapt_delta, attempts = length(res$attempts),
    divergent = dg$divergent, treedepth_hits = dg$treedepth_hits, ebfmi_min = dg$ebfmi_min, rhat_max = dg$rhat_max,
    ess_bulk_min = dg$ess_bulk_min, ess_tail_min = dg$ess_tail_min, mt05_pass = res$mt05, stringsAsFactors = FALSE)))
}

main <- function() {
  opt <- parse_cli(commandArgs(trailingOnly = TRUE))
  ctx <- start_run("W3.18", opt, "R/ch1/25_heterogeneity.R")
  p <- ctx$paths
  cal <- read_calibration(ctx, opt)
  d <- load_table(ctx)
  prim <- apply_heights(d, "primary", cal, ctx, identical(opt_get(opt, "height-rule"), "single-offset"))
  prim$half <- game_halves(prim)

  # B1
  t0 <- proc.time()
  lk <- fit_links(prim)
  # Monotonicity is recorded, as the W3.12 harness records it for the estimator the D-60 curve
  # measured; it is not a gate. B1's likelihood reads the link over u = d - delta in [-7, 7] in.
  for (k in names(lk$info)) {
    i <- lk$info[[k]]
    record(sprintf("link %s", k), sprintf("%s pitches; 50%% point d = %.2f in, slope %.2f logit/in; monotone on [-7, 7] %s",
                                          comma(i$n_fit), i$d50_in, i$slope_at_d50_logit_per_in,
                                          if (i$monotone_on_pm7) "yes" else sprintf("no, rising on u %.2f to %.2f in",
                                                                                   i$nonmonotone_u_in[1], i$nonmonotone_u_in[2])))
  }
  lut <- make_lut(lk$lp)
  sh <- prim[b1_band(prim$d), ]
  base <- lut_base(link_col(sh$edge, sh$regime), sh$d, lut)
  keys <- data.frame(umpire_hp_id = sh$umpire_hp_id, season = sh$season, edge = sh$edge, stringsAsFactors = FALSE)
  b1 <- b1_cells(keys, base, as.integer(sh$cs), lut)
  b1h <- b1_cells(cbind(keys, half = sh$half), base, as.integer(sh$cs), lut)
  dd <- b2_rows(b1)
  record("B1", sprintf("%s shadow-band pitches; %d umpire-season-edge cells, %d kept for B2 (n >= %d, finite SE, off the bound); %.0f s",
                       comma(nrow(sh)), nrow(b1), nrow(dd), N_MIN_CELL, (proc.time() - t0)[["elapsed"]]))
  ensure_dir(p$model)
  saveRDS(list(b1 = b1, b1_halves = b1h, links = lk$info), file.path(p$model, "umpire_b1_cells.rds"))

  # B3
  sph <- split_half(b1h)
  record("B3 split-half", sprintf("response r %.3f, Spearman-Brown %.3f over %d umpires; level r %.3f, Spearman-Brown %.3f over %d umpire-seasons",
                                  sph$r_response, sph$sb_response, sph$n_umpires, sph$r_level, sph$sb_level, sph$n_umpire_seasons))

  # B2
  keys_b2 <- names(B2_FITS)
  if (ctx$synthetic && !is.null(opt[["b2-fits"]])) keys_b2 <- strsplit(opt[["b2-fits"]], ",")[[1]]
  if (!ctx$synthetic && !is.null(opt[["b2-fits"]])) refuse("W3.18", "--b2-fits is a dry-run setting; real data runs all five B2 fits")
  load_brms(file.path(tools::R_user_dir("absump", "cache"), "ch1_w318_stan"))
  res <- list(); summ <- list(); t6 <- list()
  for (key in keys_b2) {
    st <- sampler_settings(ctx, opt, key)
    dry <- !identical(st, STAN_SETTINGS[[B2_FITS[[key]]$settings]])
    r <- fit_b2(key, dd, st, escalate = !dry)
    s <- b2_summary(r)
    res[[key]] <- r; summ[[key]] <- s
    t6[[key]] <- t6_rows(key, r, s, nrow(dd))
    dg <- r$diagnostics
    det <- sprintf("%d chains x %d draws after %d attempt(s): divergent %d, treedepth %d, E-BFMI min %.2f, R-hat max %.4f, ESS bulk %.0f, tail %.0f",
                   st$chains, r$settings$sampling, length(r$attempts), dg$divergent, dg$treedepth_hits, dg$ebfmi_min,
                   dg$rhat_max, dg$ess_bulk_min, dg$ess_tail_min)
    if (st$chains == 4L) check(sprintf("MT-05 %s", key), r$mt05, det) else record(sprintf("MT-05 %s (dry-run sampler)", key), det)
    record(sprintf("%s tau_abs", key), sprintf("median %.3f in, 95%% CI %.3f to %.3f, one-sided 95%% upper %.3f; P(tau >= %.2f) = %.3f",
                                               s$tau_abs[["median"]], s$tau_abs[["lo95"]], s$tau_abs[["hi95"]], s$tau_abs[["upper95"]],
                                               RULE_TAU, s$p_tau_ge_rule))
    f <- file.path(p$model, if (key == "sop") "umpire_me.rds" else sprintf("umpire_me_%s.rds", key))
    saveRDS(r$fit, f)
    write_receipt(ctx, provenance(ctx, if (key == "sop") "umpire_me" else sprintf("umpire_me_%s", key), sh, STAN_SEED, p$model,
                                  extra = list(formula = r$spec$formula, prior = r$spec$label, sampler = r$settings,
                                               attempts = r$attempts, n_cells = nrow(dd), files = list(basename(f)))),
                  p$model)
  }
  tab <- do.call(rbind, t6)

  # readings
  s0 <- summ$sop
  gate <- ch1a6_gate()
  record("CH1-A6 gate from the power curve", gate$detail)
  up <- max(s0$tau_abs[["upper95"]], if (!is.null(summ$ue_us)) summ$ue_us$tau_abs[["upper95"]] else -Inf)
  a6 <- if (isTRUE(s0$fired)) sprintf("material: P(tau >= %.2f in) = %.3f >= %.2f", RULE_TAU, s0$p_tau_ge_rule, RULE_PROB)
        else sprintf("bounded null: tau median %.3f in, one-sided 95%% upper bound %.3f in (larger of sop and ue_us); P(tau >= %.2f in) = %.3f",
                     s0$tau_abs[["median"]], up, RULE_TAU, s0$p_tau_ge_rule)
  record("CH1-A6", a6)
  sens <- list()
  for (k in c("sens_sd_exp1", "sens_sd_exp4")) if (!is.null(summ[[k]])) {
    ch <- summ[[k]]$tau_abs[["median"]] / s0$tau_abs[["median"]] - 1
    sens[[k]] <- ch
    check(sprintf("prior sensitivity %s: tau median moves < 20%%", k), abs(ch) < PRIOR_SENS_MAX,
          sprintf("%+.1f%% (%.3f against %.3f in)", 100 * ch, summ[[k]]$tau_abs[["median"]], s0$tau_abs[["median"]]))
  }
  extra_rows <- data.frame(
    fit = c("B3", "B3", "sop", "sop", "CH1-A6", "CH1-A6"),
    prior = c("odd/even plate games by game index, Spearman-Brown", "odd/even plate games by game index, Spearman-Brown",
              B2_FITS$sop$label, B2_FITS$sop$label, "annex 8.5", "annex 8.5"),
    quantity = c("split_half_response", "split_half_level", "reliability_vc_response", "split_half_minus_vc_response",
                 "p_tau_ge_020", "bounded_null_upper95"),
    median = c(sph$sb_response, sph$sb_level, s0$reliability_vc_response, sph$sb_response - s0$reliability_vc_response,
               s0$p_tau_ge_rule, if (isTRUE(s0$fired)) NA else up),
    units = c("reliability", "reliability", "reliability", "reliability", "probability", "in"),
    n_umpires = c(sph$n_umpires, sph$n_umpire_seasons, s0$n_umpires, sph$n_umpires, s0$n_umpires, s0$n_umpires),
    stringsAsFactors = FALSE)
  for (k in names(sens)) extra_rows <- rbind(extra_rows, data.frame(
    fit = k, prior = B2_FITS[[k]]$label, quantity = "tau_median_change_vs_sop", median = sens[[k]], units = "ratio",
    n_umpires = s0$n_umpires, stringsAsFactors = FALSE))
  miss <- setdiff(names(tab), names(extra_rows))
  for (m in miss) extra_rows[[m]] <- NA
  tab <- rbind(tab, extra_rows[, names(tab)])
  tab$ch1_a6 <- a6
  write_csv_plain(tab, file.path(p$tab, "T6_heterogeneity.csv"))

  # the empirical-Bayes summary, aggregate unless the gate is attainable
  d56 <- dd[as.character(dd$season) %in% c("2025", "2026"), ]
  tt <- table(factor(as.character(d56$umpire_hp_id)), factor(as.character(d56$season), levels = c("2025", "2026")))
  both <- rownames(tt)[tt[, "2025"] > 0 & tt[, "2026"] > 0]
  n_both <- length(intersect(both, sph$umpires_response))
  zci <- if (is.finite(sph$r_response) && sph$n_umpires > 3L) {
    z <- atanh(sph$r_response); se <- 1 / sqrt(sph$n_umpires - 3)
    sb(tanh(z + c(-1, 1) * stats::qnorm(0.975) * se))
  } else c(NA_real_, NA_real_)
  eb <- data.frame(
    quantity = c("tau_abs", "fps_sd_abs", "split_half_response", "reliability_vc_response", "n_umpires_b2",
                 "n_umpires_2025_and_2026", "n_umpires_split_half", "n_umpires_behind_both", "per_umpire_table_published"),
    estimator = c(sprintf("%s; posterior median, 95%% interval", B2_FITS$sop$label),
                  "sop: SD across umpires of their 2025-to-2026 responses, per posterior draw",
                  paste("B3: odd/even plate games by game index within umpire-season, B1 per half, Spearman-Brown",
                        "corrected; 95% interval from Fisher's z on the half-sample correlation, then Spearman-Brown"),
                  "sop: 1 - mean posterior variance of the response / posterior mean of tau^2 (MT-07's gating value)",
                  "umpires with a B2 cell", "umpires with B2 cells in 2025 and in 2026",
                  "umpires in the split-half correlation of the response",
                  "umpires behind both tau's 2025-to-2026 response and the split-half response",
                  paste("CH1-A6 and D-21:", gate$detail)),
    point = c(s0$tau_abs[["median"]], s0$fps_sd_abs[["median"]], sph$sb_response, s0$reliability_vc_response,
              s0$n_umpires, length(both), sph$n_umpires, n_both, as.numeric(isTRUE(gate$attainable))),
    lo95 = c(s0$tau_abs[["lo95"]], s0$fps_sd_abs[["lo95"]], zci[1], NA, NA, NA, NA, NA, NA),
    hi95 = c(s0$tau_abs[["hi95"]], s0$fps_sd_abs[["hi95"]], zci[2], NA, NA, NA, NA, NA, NA),
    units = c("in", "in", "reliability", "reliability", "counts", "counts", "counts", "counts", "flag"),
    ch1_a6 = a6, stringsAsFactors = FALSE)
  write_csv_plain(eb, file.path(p$tab, "umpire_eb.csv"))
  record("umpire_eb", sprintf("%d aggregate rows; per-umpire rows %s", nrow(eb),
                              if (isTRUE(gate$attainable)) "would be published: the gate is attainable, and this script does not write them without a new decision"
                              else "not published (CH1-A6, D-21)"))
  finish("W3.18")
}

if (identical(environment(), globalenv()) && !interactive()) main()
