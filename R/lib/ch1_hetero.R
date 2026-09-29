# R/lib/ch1_hetero.R - W3.18 umpire heterogeneity, stages B1, B2 and B3. Sourced by
# R/lib/ch1_fits.R.
#
# The code is R/ch1/21_synthetic.R's (W3.12), the estimator the D-60 power curve measured, so
# the CH1-A6 thresholds of docs/prereg/ch1.md section 8.5 apply to the fit W3.18 runs:
#   B1  per umpire-season-edge, delta maximises the binomial likelihood of y ~ g_{e,r}(d - delta)
#       over [-4, 4] in by 0.01 in (a 0.1 in coarse pass, then +/- 1 in at 0.01), on the
#       shadow band |d| <= 3.0 in. The SE is the profile half-width where the log likelihood
#       falls by 0.5. B2 keeps cells with >= 30 pitches, a finite SE and delta off the bound.
#       The link g_{e,r}(d) is the pooled league link of edge e in regime r: glm(cs ~ ns(d, 6))
#       on that edge's |d| <= 8 in pitches of that regime, the form of the W3.12 calibration
#       link, fitted once per edge and regime as SOP W3.18 says.
#   B2  brms, the SOP formula with the step coding of annex 8.2 (buf_step 1 in 2025 and 2026,
#       abs_step 1 in 2026), priors normal(0, 1) on b except normal(0, 0.30) on the three
#       edge:abs_step coefficients (annex 8.8, DEV-62), exponential(2) on sd and sigma, lkj(2)
#       on cor. Sampler settings of annex 8.2 (DEV-63), seed 20260922, and the MT-05
#       escalation of annex 8.2.
#   B3  split-half: each umpire-season's plate games odd/even by game index in date order, B1
#       on each half, the 2025-to-2026 response pooled over edges by precision, correlated
#       across halves and Spearman-Brown corrected; the same for the level.

LINK_DF <- 6L
U_MIN <- -8; U_MAX <- 8; U_STEP <- 0.001      # link lookup grid, inches
DELTA_MIN <- -4; DELTA_MAX <- 4; DELTA_STEP <- 0.01
COARSE_STEP <- 0.1
FINE_HALF <- 1.0
N_MIN_CELL <- 30L
N_MIN_HALF <- 15L
RULE_TAU <- 0.20          # CH1-A6: material only if P(tau >= 0.20 in) >= 0.90
RULE_PROB <- 0.90
REL_FLOOR <- 0.50         # the reliability gate D-60 names (annex 8.4)
STAN_SEED <- 20260922L
STAN_SETTINGS <- list(
  sop   = list(chains = 4L, warmup = 1000L, sampling = 2000L, adapt_delta = 0.99, max_treedepth = 10L),
  ue_us = list(chains = 4L, warmup = 2000L, sampling = 6000L, adapt_delta = 0.99, max_treedepth = 10L))
STAN_ESCALATE_MAX <- 2L
ABS_STEP_PRIOR_SD <- 0.30
ABS_STEP_COEFS <- c("edgeside:abs_step", "edgetop:abs_step", "edgebot:abs_step")
B2_FORMULA_TEXT <- paste("delta | se(se_delta, sigma = TRUE) ~ 0 + edge + edge:buf_step +",
                         "edge:abs_step + (1 + buf_step + abs_step | umpire_hp_id)")
B2_UE_US_TEXT <- paste(B2_FORMULA_TEXT, "+ (1 | umpire_hp_id:edge) + (1 | umpire_hp_id:season)")
# The B2 fits W3.18 runs. sop is the primary and sets CH1-A6 (annex 8.3). SENS-B2-ABS-PRIOR is
# the SOP's normal(0, 1) on abs_step (annex 8.8). The SOP's prior-sensitivity rule refits with
# exponential(1) and exponential(4) on tau's prior, class sd. ue_us is the sensitivity
# estimator whose MT-05 is read here (DEV-64).
B2_FITS <- list(
  sop         = list(formula = B2_FORMULA_TEXT, abs_sd = ABS_STEP_PRIOR_SD, sd_rate = 2, settings = "sop",
                     label = "sop: SOP W3.18 B2, abs_step prior normal(0, 0.30), sd prior exponential(2)"),
  sens_abs_prior = list(formula = B2_FORMULA_TEXT, abs_sd = NA, sd_rate = 2, settings = "sop",
                        label = "SENS-B2-ABS-PRIOR: abs_step prior normal(0, 1)"),
  sens_sd_exp1 = list(formula = B2_FORMULA_TEXT, abs_sd = ABS_STEP_PRIOR_SD, sd_rate = 1, settings = "sop",
                      label = "prior sensitivity: sd prior exponential(1)"),
  sens_sd_exp4 = list(formula = B2_FORMULA_TEXT, abs_sd = ABS_STEP_PRIOR_SD, sd_rate = 4, settings = "sop",
                      label = "prior sensitivity: sd prior exponential(4)"),
  ue_us       = list(formula = B2_UE_US_TEXT, abs_sd = ABS_STEP_PRIOR_SD, sd_rate = 2, settings = "ue_us",
                     label = "ue_us: B2 plus (1 | umpire x edge) and (1 | umpire x season)"))
PRIOR_SENS_MAX <- 0.20    # SOP W3.18: the posterior median of tau moves by less than 20%

## --- the links g_{e,r}(d) and their lookup table -------------------------------------------------

LINK_COLS <- as.vector(outer(EDGE_LEVELS, REGIMES, paste, sep = "|"))
link_col <- function(edge, regime) match(paste(edge, regime, sep = "|"), LINK_COLS)

fit_links <- function(rows) {
  u <- seq(U_MIN, U_MAX, by = U_STEP)
  lp <- matrix(NA_real_, length(u), length(LINK_COLS), dimnames = list(NULL, LINK_COLS))
  info <- list()
  for (k in LINK_COLS) {
    er <- strsplit(k, "|", fixed = TRUE)[[1]]
    s <- rows[rows$edge == er[1] & rows$regime == er[2] & abs(rows$d) <= BAND_SURF, ]
    if (nrow(s) < 200L) die("too few pitches for the link ", k, ": ", nrow(s))
    m <- glm(cs ~ splines::ns(d, df = LINK_DF), family = binomial(), data = s)
    lp[, k] <- predict(m, data.frame(d = u))
    d50 <- u[which.min(abs(lp[, k]))]
    j50 <- which.min(abs(u - d50))
    info[[k]] <- list(n_fit = nrow(s), d50_in = d50,
                      slope_at_d50_logit_per_in = -(lp[j50 + 10L, k] - lp[j50 - 10L, k]) / (20 * U_STEP),
                      monotone_on_pm7 = all(diff(lp[abs(u) <= 7 + 1e-9, k]) < 0))
  }
  list(u = u, lp = lp, info = info)
}
make_lut <- function(lp) {
  list(lg = as.vector(plogis(lp, log.p = TRUE)),
       l1g = as.vector(plogis(lp, lower.tail = FALSE, log.p = TRUE)), nu = nrow(lp))
}
lut_base <- function(col, d, lut) (col - 1L) * lut$nu + as.integer(round((d - U_MIN) / U_STEP)) + 1L
to_steps <- function(delta) as.integer(round(delta / U_STEP))

## --- B1 --------------------------------------------------------------------------------------------

b1_estimate <- function(grp, base, y, lut) {
  G <- max(grp)
  stopifnot(identical(sort(unique(grp)), seq_len(G)))
  ll_sum <- function(steps) {
    idx <- base - steps
    v <- lut$l1g[idx]
    k <- y == 1L
    v[k] <- lut$lg[idx[k]]
    as.vector(rowsum(v, grp, reorder = TRUE))
  }
  coarse <- seq(DELTA_MIN, DELTA_MAX, by = COARSE_STEP)
  LLc <- vapply(to_steps(coarse), function(s) ll_sum(rep.int(s, length(y))), numeric(G))
  if (G == 1L) LLc <- matrix(LLc, nrow = 1L)
  centre <- coarse[max.col(LLc, ties.method = "first")]
  offs <- seq(-FINE_HALF, FINE_HALF, by = DELTA_STEP)
  fine <- round(pmin(pmax(outer(centre, offs, "+"), DELTA_MIN), DELTA_MAX), 2)
  fsteps <- matrix(to_steps(fine), nrow = G)
  LLf <- vapply(seq_along(offs), function(k) ll_sum(fsteps[grp, k]), numeric(G))
  if (G == 1L) LLf <- matrix(LLf, nrow = 1L)
  jm <- max.col(LLf, ties.method = "first")
  mle <- fine[cbind(seq_len(G), jm)]
  lmax <- LLf[cbind(seq_len(G), jm)]
  se <- vapply(seq_len(G), function(g) {
    l <- LLf[g, ]; x <- fine[g, ]; j <- jm[g]; tg <- lmax[g] - 0.5
    lo <- NA_real_; hi <- NA_real_
    if (j > 1L) {
      k <- which(l[seq_len(j - 1L)] < tg)
      if (length(k) > 0L) {
        k <- max(k)
        if (x[k + 1L] > x[k]) lo <- x[k] + (x[k + 1L] - x[k]) * (tg - l[k]) / (l[k + 1L] - l[k])
      }
    }
    if (j < length(l)) {
      k <- which(l[(j + 1L):length(l)] < tg)
      if (length(k) > 0L) {
        k <- j + min(k)
        if (x[k] > x[k - 1L]) hi <- x[k - 1L] + (x[k] - x[k - 1L]) * (l[k - 1L] - tg) / (l[k - 1L] - l[k])
      }
    }
    hw <- c(mle[g] - lo, hi - mle[g])
    if (all(is.na(hw))) NA_real_ else mean(hw, na.rm = TRUE)
  }, 0)
  data.frame(grp = seq_len(G), n = tabulate(grp, G), delta = mle, se_delta = se,
             at_bound = abs(mle) >= DELTA_MAX - 1e-9)
}

b1_cells <- function(keys, base, y, lut) {
  key <- do.call(paste, c(keys, sep = "|"))
  lev <- sort(unique(key))
  grp <- match(key, lev)
  est <- b1_estimate(grp, base, y, lut)
  first <- match(seq_along(lev), grp)
  out <- cbind(keys[first, , drop = FALSE], est[, c("n", "delta", "se_delta", "at_bound")])
  rownames(out) <- NULL
  out
}

b2_rows <- function(b1) {
  k <- b1$n >= N_MIN_CELL & !b1$at_bound & is.finite(b1$se_delta)
  out <- b1[k, c("umpire_hp_id", "season", "edge", "n", "delta", "se_delta")]
  out$edge <- factor(out$edge, levels = EDGE_LEVELS)
  out$buf_step <- as.numeric(out$season >= 2025)
  out$abs_step <- as.numeric(out$season == 2026)
  out$umpire_hp_id <- factor(out$umpire_hp_id)
  out$season <- factor(out$season)
  rownames(out) <- NULL
  out
}

## --- B3 --------------------------------------------------------------------------------------------

sb <- function(r) 2 * r / (1 + r)
pool_edges <- function(v, w, grp) {
  num <- rowsum(v * w, grp); den <- rowsum(w, grp)
  setNames(as.vector(num / den), rownames(num))
}
split_half <- function(b1h) {
  ok <- b1h$n >= N_MIN_HALF & !b1h$at_bound & is.finite(b1h$se_delta)
  h <- b1h[ok, ]
  resp <- list()
  for (hh in c("odd", "even")) {
    a <- h[h$half == hh & h$season == 2025, ]
    b <- h[h$half == hh & h$season == 2026, ]
    m <- merge(a, b, by = c("umpire_hp_id", "edge"), suffixes = c("_25", "_26"))
    m$r <- m$delta_26 - m$delta_25
    m$w <- 1 / (m$se_delta_25^2 + m$se_delta_26^2)
    ce <- pool_edges(m$r, m$w, m$edge)
    m$rc <- m$r - ce[m$edge]
    resp[[hh]] <- pool_edges(m$rc, m$w, m$umpire_hp_id)
  }
  u <- intersect(names(resp$odd), names(resp$even))
  r_resp <- if (length(u) >= 3L) stats::cor(resp$odd[u], resp$even[u]) else NA_real_
  lev <- list()
  for (hh in c("odd", "even")) {
    a <- h[h$half == hh, ]
    a$w <- 1 / a$se_delta^2
    key_se <- paste(a$season, a$edge)
    ce <- pool_edges(a$delta, a$w, key_se)
    a$dc <- a$delta - ce[key_se]
    lev[[hh]] <- pool_edges(a$dc, a$w, paste(a$umpire_hp_id, a$season))
  }
  v <- intersect(names(lev$odd), names(lev$even))
  r_lev <- if (length(v) >= 3L) stats::cor(lev$odd[v], lev$even[v]) else NA_real_
  list(n_umpires = length(u), r_response = r_resp, sb_response = sb(r_resp),
       n_umpire_seasons = length(v), r_level = r_lev, sb_level = sb(r_lev), umpires_response = u)
}

## --- B2 with brms ------------------------------------------------------------------------------------

load_brms <- function(stan_dir) {
  suppressPackageStartupMessages({
    library(brms)
    library(cmdstanr)
    library(posterior)
  })
  ensure_dir(stan_dir)
  options(cmdstanr_write_stan_file_dir = stan_dir, brms.backend = "cmdstanr")
}

b2_priors <- function(abs_sd = ABS_STEP_PRIOR_SD, sd_rate = 2) {
  p <- c(brms::prior(normal(0, 1), class = "b"),
         brms::set_prior(sprintf("exponential(%s)", format(sd_rate)), class = "sd"),
         brms::prior(exponential(2), class = "sigma"),
         brms::prior(lkj(2), class = "cor"))
  if (!is.na(abs_sd)) for (cf in ABS_STEP_COEFS)
    p <- c(p, brms::set_prior(sprintf("normal(0, %s)", format(abs_sd)), class = "b", coef = cf))
  p
}

fit_brms <- function(formula_text, data, priors, st) {
  warn <- character(0)
  pt0 <- proc.time()
  fit <- withCallingHandlers(
    brms::brm(brms::bf(as.formula(formula_text)), data = data, family = gaussian(),
              prior = priors, chains = st$chains, iter = st$warmup + st$sampling,
              warmup = st$warmup, cores = st$chains, backend = "cmdstanr", seed = STAN_SEED,
              control = list(adapt_delta = st$adapt_delta, max_treedepth = st$max_treedepth),
              refresh = 0, silent = 2),
    warning = function(w) {
      warn <<- c(warn, conditionMessage(w))
      invokeRestart("muffleWarning")
    },
    message = function(m) invokeRestart("muffleMessage"))
  list(fit = fit, warn = unique(warn), elapsed = unname((proc.time() - pt0)[["elapsed"]]))
}

diagnostics <- function(fit, pars, st) {
  np <- brms::nuts_params(fit)
  div <- sum(np$Value[np$Parameter == "divergent__"])
  td <- sum(np$Value[np$Parameter == "treedepth__"] >= st$max_treedepth)
  en <- np[np$Parameter == "energy__", ]
  ebfmi <- vapply(split(en$Value, en$Chain), function(e) sum(diff(e)^2) / length(e) / stats::var(e), 0)
  dr <- posterior::subset_draws(posterior::as_draws_array(fit), variable = pars)
  sm <- posterior::summarise_draws(dr, "rhat", "ess_bulk", "ess_tail")
  list(divergent = div, treedepth_hits = td, ebfmi_min = min(ebfmi),
       rhat_max = max(sm$rhat), ess_bulk_min = min(sm$ess_bulk), ess_tail_min = min(sm$ess_tail))
}
mt05_pass <- function(dg, min_chains = 4L, n_chains = 4L) {
  n_chains >= min_chains && dg$divergent == 0 && dg$treedepth_hits == 0 && dg$ebfmi_min >= 0.2 &&
    dg$rhat_max <= 1.01 && dg$ess_bulk_min >= 400 && dg$ess_tail_min >= 400
}
mt05_short <- function(dg) dg$divergent == 0 && dg$treedepth_hits == 0 && dg$ebfmi_min >= 0.2 &&
  (dg$rhat_max > 1.01 || dg$ess_bulk_min < 400 || dg$ess_tail_min < 400)
b2_pars <- function(dr) c(grep("^b_", names(dr), value = TRUE), grep("^sd_", names(dr), value = TRUE),
                          grep("^cor_", names(dr), value = TRUE), "sigma")

# One B2 fit with the MT-05 escalation of annex 8.2: a fit short only on R-hat or ESS is run
# again from the same seed with the draws a chain doubled, at most twice. Every attempt is kept.
fit_b2 <- function(key, dd, st, escalate = TRUE) {
  spec <- B2_FITS[[key]]
  attempts <- list()
  repeat {
    ft <- fit_brms(spec$formula, dd, b2_priors(spec$abs_sd, spec$sd_rate), st)
    dr <- posterior::as_draws_df(ft$fit)
    dg <- diagnostics(ft$fit, b2_pars(dr), st)
    attempts[[length(attempts) + 1L]] <- c(st, list(seed = STAN_SEED), dg, list(seconds = ft$elapsed))
    if (!escalate || !mt05_short(dg) || length(attempts) > STAN_ESCALATE_MAX) break
    st$sampling <- 2L * st$sampling
  }
  list(key = key, spec = spec, fit = ft$fit, draws = dr, diagnostics = dg, settings = st,
       attempts = attempts, warnings = ft$warn, mt05 = mt05_pass(dg, n_chains = st$chains))
}

# The quantities W3.18 reports from one B2 fit.
b2_summary <- function(res) {
  dr <- res$draws
  get <- function(v) if (v %in% names(dr)) dr[[v]] else NULL
  tau <- get("sd_umpire_hp_id__abs_step")
  tbuf <- get("sd_umpire_hp_id__buf_step")
  if (is.null(tau) || is.null(tbuf)) die("B2 draws lack the abs_step or buf_step SD")
  rn <- grep("^r_umpire_hp_id\\[.*,abs_step\\]$", names(dr), value = TRUE)
  rm <- as.matrix(as.data.frame(dr)[, rn, drop = FALSE])
  qs <- function(v) c(median = stats::median(v), lo95 = qint(v)[1], hi95 = qint(v)[2],
                      upper95 = unname(stats::quantile(v, 0.95)))
  out <- list(
    tau_abs = qs(tau), tau_buf = qs(tbuf),
    sd_intercept = qs(get("sd_umpire_hp_id__Intercept")),
    cor_buf_abs = qs(get("cor_umpire_hp_id__buf_step__abs_step")),
    sigma = qs(get("sigma")),
    p_tau_ge_rule = mean(tau >= RULE_TAU),
    fired = mean(tau >= RULE_TAU) >= RULE_PROB,
    reliability_vc_response = 1 - mean(apply(rm, 2, stats::var)) / mean(tau^2),
    n_umpires = length(rn),
    fps_sd_abs = qs(apply(rm, 1, stats::sd)))
  for (e in EDGE_LEVELS) out[[paste0("league_abs_step_", e)]] <- qs(get(sprintf("b_edge%s:abs_step", e)))
  out
}

## --- CH1-A6: the gate the power curve sets -------------------------------------------------------

CURVE_CSV <- file.path(ROOT, "out", "tables", "ch1_power_curve.csv")

# Annex 8.4's rule, read off the committed curve: c* is the smallest c with F_c(0.10) <= 1 of 5;
# powered when F_c*(0.30) >= 4 of 5; the gate is attainable when a powered grid tau reaches a
# variance-components reliability of the response of 0.50.
ch1a6_gate <- function(path = CURVE_CSV) {
  if (!file.exists(path)) return(list(attainable = FALSE, detail = paste("no curve at", path)))
  cv <- read_csv_plain(path)
  cv <- cv[cv$sets_ch1_a6 == "yes", ]
  if (nrow(cv) == 0L) return(list(attainable = FALSE, detail = "no estimator sets CH1-A6 on the curve"))
  fired <- function(c) {
    col <- switch(sprintf("%.2f", c), "0.20" = "n_fired", "0.25" = "firing_rate_c025", "0.30" = "firing_rate_c030")
    v <- as.numeric(cv[[col]])
    if (col == "n_fired") v else round(v * cv$n_seeds)
  }
  taus <- as.numeric(cv$tau_true_in)
  cstar <- NA_real_
  for (c in c(0.20, 0.25, 0.30)) if (fired(c)[abs(taus - 0.10) < 1e-9] <= 1) { cstar <- c; break }
  if (is.na(cstar)) return(list(attainable = FALSE, detail = "no materiality threshold c* on the curve"))
  powered <- fired(cstar) >= 4
  rel <- as.numeric(cv$reliability_vc_response_mean)
  att <- any(powered & rel >= REL_FLOOR)
  list(attainable = att, c_star = cstar, estimator = cv$estimator[1],
       detail = sprintf("%s: c* = %.2f in; powered at tau %s; variance-components reliability there %s; gate %s",
                        cv$estimator[1], cstar, paste(sprintf("%.2f", taus[powered]), collapse = ", "),
                        paste(sprintf("%.3f", rel[powered]), collapse = ", "),
                        if (att) "attainable" else "not attainable"))
}
