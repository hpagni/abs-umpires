# R/lib/ch1_estimands.R - the W3.14 surfaces and the W3.15 estimands. Sourced by R/lib/ch1_fits.R.
#
# A "spec" names one fit's formula, its period factor and its random-effect terms:
#   main    the frozen specification with season as the period (annex section 2)
#   single  one season, so no season terms; s(umpire_season) equals s(umpire_hp_id) inside one
#           season and is dropped. This is the W3.12 recovery harness's generating formula.
#           W3.17 fits 2025 with it, once on each plate plane.
#   half    the frozen specification with the season replaced by the half-season, for P2.
#   undersmooth  the frozen specification with the season by-term at k = 24, SENS-B1-UNDERSMOOTH
#           (annex 8.7). Every other term and k is the frozen text.
# Every other term is the frozen text, so the four cannot drift apart.
#
# THE ESTIMANDS (SOP W3.14), for a 72-inch batter on the 301 x 276 grid, each season's surface
# standardised by g-computation to the 2024 reference mix, random effects at zero:
#   top_in, bot_in   the 50% crossing along zn, averaged over the 51 columns |x| <= 0.25 ft
#   half_width_in    half the distance between the two 50% crossings along x at zn = 0.4025
#   area_sqin        the area inside the closed 50% contour around (0, 0.4025), traced by
#                    marching squares (grDevices::contourLines), in square inches
#   shadow_rate      the standardised called-strike rate, percent, over the 2024 reference
#                    pitches in the D-P4-09 shadow band, |d - 1.45| <= 3.0 in (shadow_band()),
#                    each scored at its own location and covariates
#   count_bias       P(strike | 3-ball) - P(strike | 2-strike), percentage points, over the 2024
#                    reference pitches in the three 1-inch bins centred on d = -1, 0, +1 in, the
#                    bins weighted equally. The frozen specification has no balls term, so
#                    3-ball enters through the strike-count mix of the 2024 3-ball pitches.
# The reference mix follows the W3.12 harness and the W3.11 script: six (count class,
# handedness) cells, each with 51 quantiles of the pitch-group-and-velocity shift on the logit
# scale. The shift is exact at every location because pitch_group and s(velo) enter the frozen
# specification additively.
#
# DRAWS. Coefficients are drawn once, in W3.14, from N(beta, Vc) and never refitted. For a
# draw the standardised probability of a cell is F_c(eta) = mean_q plogis(eta + q_c). The point
# estimate evaluates F_c exactly. The draws read F_c from a table on a 5e-4 logit grid with
# linear interpolation, whose error is below 1e-8 in probability; mix_table() measures it.

SPEC_KINDS <- c("main", "single", "half", "undersmooth")

sub_once <- function(pattern, replacement, x) {
  y <- sub(pattern, replacement, x, fixed = TRUE)
  if (identical(y, x)) die("the frozen formula has no '", pattern, "'")
  y
}

spec_formula <- function(kind) {
  f <- FROZEN_FORMULA_TEXT
  switch(kind,
    main = f,
    single = {
      f <- sub_once("cs ~ season + ", "cs ~ ", f)
      f <- sub_once(' + te(x_mid, zn, bs = c("cr","cr"), k = c(18,18), by = season_o)', "", f)
      sub_once(' + s(umpire_season, bs = "re")', "", f)
    },
    half = {
      f <- sub_once("cs ~ season + ", "cs ~ half + ", f)
      f <- sub_once("by = season_o)", "by = half_o)", f)
      sub_once("s(umpire_season, ", "s(umpire_half, ", f)
    },
    undersmooth = sub_once("k = c(18,18), by = season_o)",
                           sprintf("k = c(%d,%d), by = season_o)", UNDERSMOOTH_SEASON_K, UNDERSMOOTH_SEASON_K), f),
    die("unknown spec ", kind))
}

make_spec <- function(kind, levels = NULL) {
  stopifnot(kind %in% SPEC_KINDS)
  period <- switch(kind, main = , undersmooth = "season", single = NULL, half = "half")
  lv <- if (!is.null(levels)) levels else switch(kind, main = , undersmooth = SEASON_LEVELS, single = NULL,
                                                  half = c("first", "second"))
  re_var <- switch(kind, main = , undersmooth = c("umpire_hp_id", "umpire_season"), single = "umpire_hp_id",
                   half = c("umpire_hp_id", "umpire_half"))
  list(kind = kind, formula = spec_formula(kind), period = period, levels = lv,
       re_terms = sprintf("s(%s)", re_var), re_vars = re_var, dummies = NULL)
}

# Factor coding. Ordered copies drive the by-smooths; the parametric terms keep the unordered
# factors with treatment contrasts (annex section 2).
code_covariates <- function(df) {
  df$count_class <- factor(as.character(df$count_class), levels = CC_LEVELS)
  df$stand <- factor(as.character(df$stand), levels = STAND_LEVELS)
  df$pitch_group <- factor(as.character(df$pitch_group), levels = PG_LEVELS)
  df$count_class_o <- factor(df$count_class, levels = CC_LEVELS, ordered = TRUE)
  df$stand_o <- factor(df$stand, levels = STAND_LEVELS, ordered = TRUE)
  df
}
code_period <- function(df, spec, value = NULL) {
  if (is.null(spec$period)) return(df)
  v <- if (is.null(value)) as.character(df[[spec$period]]) else rep(as.character(value), nrow(df))
  df[[spec$period]] <- factor(v, levels = spec$levels)
  df[[paste0(spec$period, "_o")]] <- factor(v, levels = spec$levels, ordered = TRUE)
  df
}

# The fit frame: covariates coded, the period coded, the random-effect factors built.
fit_frame <- function(df, spec) {
  df <- code_covariates(df)
  if (spec$kind %in% c("main", "undersmooth")) df$umpire_season <- paste(df$umpire_hp_id, df$season, sep = ":")
  if (spec$kind == "half") df$umpire_half <- paste(df$umpire_hp_id, df$half, sep = ":")
  df <- code_period(df, spec)
  for (v in spec$re_vars) df[[v]] <- factor(as.character(df[[v]]))
  bad <- vapply(c("count_class", "stand", "pitch_group", spec$period), function(v) anyNA(df[[v]]), TRUE)
  if (any(bad)) die("uncoded levels in ", paste(names(bad)[bad], collapse = ", "))
  df
}

# The formula lives in an empty environment. mgcv copies the formula's environment into the
# random-effect smooths and the discretisation record, and saveRDS then writes that frame, the
# whole fit frame included, into the model file: 412 MB for a 134,430-row synthetic fit.
fit_surface <- function(df, spec) {
  suppressPackageStartupMessages(library(mgcv))
  warn <- character(0)
  fml <- stats::as.formula(spec$formula, env = new.env(parent = globalenv()))
  pt0 <- proc.time()
  m <- withCallingHandlers(
    bam(fml, data = df, family = binomial(), discrete = TRUE, method = "fREML"),
    warning = function(w) {
      warn <<- c(warn, conditionMessage(w))
      invokeRestart("muffleWarning")
    })
  el <- unname((proc.time() - pt0)[["elapsed"]])
  if (is.null(m[[INTERVAL_COV]]) || !identical(dim(m[[INTERVAL_COV]]), dim(m$Vp))) {
    die("bam returned no ", INTERVAL_COV)
  }
  spec$dummies <- as.data.frame(lapply(setNames(spec$re_vars, spec$re_vars), function(v) {
    factor(levels(df[[v]])[1], levels = levels(df[[v]]))
  }))
  # bam's fREML reports converged and the criterion's gradient in the log smoothing parameters;
  # annex section 3 read every component below 1e-4 on the frozen development fit.
  grad <- m$outer.info$grad
  list(m = m, spec = spec, seconds = el, warnings = unique(warn), converged = isTRUE(m$converged),
       grad_max = if (length(grad)) max(abs(grad)) else NA_real_, n_coef = length(stats::coef(m)),
       edf = sum(m$edf))
}

# 1,000 coefficient draws from N(beta, Vc). Seeded, drawn once in W3.14, never refitted. A plain
# draws x coefficients matrix, columns named by coefficient, with the covariance and the seed as
# attributes, so dim(readRDS(<draws file>)) prints 1000 and the coefficient count.
coef_draws <- function(m, n = N_DRAWS, seed = DRAW_SEED) {
  V <- m[[INTERVAL_COV]]
  set.seed(seed)
  B <- MASS::mvrnorm(n, stats::coef(m), V)
  if (n == 1L) B <- matrix(B, nrow = 1L)
  colnames(B) <- names(stats::coef(m))
  attr(B, "covariance") <- INTERVAL_COV
  attr(B, "seed") <- seed
  B
}

## --- linear predictors, from a fitted model or from a known truth -----------------------------
# A truth is a function(newdata) returning the linear predictor with no random effect. The
# synthetic dry run reads its truth through this same code, as the W3.12 harness did.

# Exact prediction is predict.gam: predict.bam discretises covariates with many distinct values
# (0.02 logit on single W3.14 rows). On the grid, whose covariates take few values, predict.bam's
# discrete path equals predict.gam to 1e-13 and is sixty times faster; eta_grid() uses it and
# checks it against predict.gam on 400 evenly spaced grid points, falling back to predict.gam on any gap.
eta_of <- function(m, nd, spec) {
  if (is.function(m)) return(as.vector(m(nd)))
  as.vector(mgcv::predict.gam(m, nd, exclude = spec$re_terms))
}
GRID_CHECK_N <- 400L
GRID_CHECK_TOL <- 1e-8
eta_grid <- function(m, nd, spec) {
  if (is.function(m)) return(as.vector(m(nd)))
  fast <- as.vector(predict(m, nd, exclude = spec$re_terms))
  i <- unique(round(seq(1, nrow(nd), length.out = min(GRID_CHECK_N, nrow(nd)))))
  gap <- max(abs(fast[i] - as.vector(mgcv::predict.gam(m, nd[i, , drop = FALSE], exclude = spec$re_terms))))
  if (gap > GRID_CHECK_TOL) {
    record("grid prediction", sprintf("discrete path differs by %.2e on the check points; predict.gam used", gap))
    return(eta_of(m, nd, spec))
  }
  fast
}
# predict.gam builds the same lpmatrix as predict.bam (to 1e-15 on the W3.14 fits) about seven
# times faster; predict.bam's discrete link prediction is exact to 1e-13 and serves the points.
lp_of <- function(m, nd, spec) mgcv::predict.gam(m, nd, type = "lpmatrix", exclude = spec$re_terms)

new_frame <- function(pts, spec, level, pitch_group, velo, count_class, stand) {
  nd <- data.frame(x_mid = pts$x_mid, zn = pts$zn, pitch_group = pitch_group, velo = velo,
                   count_class = count_class, stand = stand, stringsAsFactors = FALSE)
  if (!is.null(spec$dummies)) nd <- cbind(nd, spec$dummies[rep(1L, nrow(nd)), , drop = FALSE])
  code_period(code_covariates(nd), spec, level)
}

# The 2024 reference mix: per (count class, handedness) cell, its share of the reference
# pitches and NQ quantiles of the pitch-group-and-velocity shift.
ref_mix <- function(m, spec, ref, level) {
  velo_ref <- stats::median(ref$velo)
  pts <- data.frame(x_mid = rep(0, nrow(ref)), zn = ZN_MID)
  base <- new_frame(pts, spec, level, as.character(ref$pitch_group), ref$velo,
                    as.character(ref$count_class), as.character(ref$stand))
  base0 <- new_frame(pts, spec, level, PG_LEVELS[1], velo_ref,
                     as.character(ref$count_class), as.character(ref$stand))
  delta <- eta_of(m, base, spec) - eta_of(m, base0, spec)
  cell <- paste(ref$count_class, ref$stand, sep = "|")
  probs <- (seq_len(NQ) - 0.5) / NQ
  cells <- lapply(split(seq_along(cell), cell), function(i) {
    list(cc = as.character(ref$count_class[i[1]]), st = as.character(ref$stand[i[1]]),
         w = length(i) / nrow(ref), q = unname(stats::quantile(delta[i], probs, type = 7)))
  })
  list(cells = cells, velo_ref = velo_ref, n_ref = nrow(ref))
}

cell_frame <- function(pts, mix, cl, spec, level) {
  new_frame(pts, spec, level, PG_LEVELS[1], mix$velo_ref, cl$cc, cl$st)
}

# F_c(eta) = mean_q plogis(eta + q) on a fine grid, for the draws.
MIX_LO <- -30; MIX_HI <- 30; MIX_H <- 5e-4
mix_table <- function(q) {
  eta <- seq(MIX_LO, MIX_HI, by = MIX_H)
  Fv <- rowMeans(plogis(outer(eta, q, "+")))
  mid <- eta[-length(eta)] + MIX_H / 2
  err <- max(abs(rowMeans(plogis(outer(mid, q, "+"))) - (Fv[-1] + Fv[-length(Fv)]) / 2))
  list(F = Fv, n = length(Fv), err = err)
}
mix_eval <- function(tab, E) {
  u <- (pmin(pmax(E, MIX_LO), MIX_HI) - MIX_LO) / MIX_H
  i <- pmin(floor(u), tab$n - 2)
  f <- u - i
  out <- (1 - f) * tab$F[i + 1] + f * tab$F[i + 2]
  dim(out) <- dim(E)
  out
}

std_surface <- function(m, spec, mix, level) {
  pts <- rbind(expand.grid(x_mid = XG, zn = ZG), data.frame(x_mid = XG, zn = ZN_MID))
  p <- numeric(nrow(pts))
  for (cl in mix$cells) {
    eta <- eta_grid(m, cell_frame(pts, mix, cl, spec, level), spec)
    p <- p + cl$w * rowMeans(plogis(outer(eta, cl$q, "+")))
  }
  ng <- length(XG) * length(ZG)
  list(grid = matrix(p[seq_len(ng)], nrow = length(XG)), line = p[ng + seq_along(XG)])
}

## --- the contour geometry ------------------------------------------------------------------------

crossing <- function(v, s, j0, step) {
  if (is.na(v[j0]) || v[j0] <= 0) return(NA_real_)
  idx <- if (step > 0) seq.int(j0 + 1L, length(v)) else seq.int(j0 - 1L, 1L)
  k <- which(v[idx] <= 0)[1]
  if (is.na(k)) return(NA_real_)
  j_out <- idx[k]
  j_in <- j_out - step
  s[j_in] + (s[j_out] - s[j_in]) * v[j_in] / (v[j_in] - v[j_out])
}

point_in_poly <- function(px, py, x, y) {
  n <- length(x)
  j <- c(n, seq_len(n - 1L))
  hit <- ((y > py) != (y[j] > py)) & (px < (x[j] - x) * (py - y) / (y[j] - y) + x)
  sum(hit, na.rm = TRUE) %% 2L == 1L
}

# The closed 0-logit contour that encloses (0, ZN_MID), the largest if several do.
# contourLines traces the level set by marching squares with linear interpolation on the cell
# edges. A contour that is not closed inside the grid does not count.
main_contour <- function(L) {
  if (is.na(L[I_ZERO, J_MID_LO]) || L[I_ZERO, J_MID_LO] <= 0) return(NULL)
  best <- NULL
  for (c in grDevices::contourLines(XG, ZG, L, levels = 0)) {
    n <- length(c$x)
    if (n < 4L || abs(c$x[1] - c$x[n]) > 1e-9 || abs(c$y[1] - c$y[n]) > 1e-9) next
    if (!point_in_poly(0, ZN_MID, c$x, c$y)) next
    c$area <- abs(sum(c$x[-n] * c$y[-1] - c$x[-1] * c$y[-n])) / 2
    if (is.null(best) || c$area > best$area) best <- c
  }
  best
}
# Its area in square inches for a 72-inch batter; NA when there is no such contour.
contour_area <- function(L) {
  c <- main_contour(L)
  if (is.null(c)) NA_real_ else c$area * 12 * REF_HEIGHT_IN
}

edge_metrics <- function(s) {
  lp <- unname(qlogis(s$grid))
  ll <- unname(qlogis(s$line))
  tops <- vapply(I_CENTRE, function(i) crossing(lp[i, ], ZG, J_MID_HI, +1L), 0)
  bots <- vapply(I_CENTRE, function(i) crossing(lp[i, ], ZG, J_MID_LO, -1L), 0)
  xr <- crossing(ll, XG, I_ZERO, +1L)
  xl <- crossing(ll, XG, I_ZERO, -1L)
  c(top_in = mean(tops) * REF_HEIGHT_IN, bot_in = mean(bots) * REF_HEIGHT_IN,
    half_width_in = (xr - xl) / 2 * 12, area_sqin = contour_area(lp))
}

## --- per-draw estimands ----------------------------------------------------------------------------

# Draw-by-draw standardised probability on a set of points. B is draws x coefficients.
draw_prob <- function(m, spec, mix, level, pts, B, chunk = 4000L) {
  tabs <- lapply(mix$cells, function(cl) mix_table(cl$q))
  P <- matrix(0, nrow(pts), nrow(B))
  for (st in seq(1L, nrow(pts), by = chunk)) {
    ii <- st:min(nrow(pts), st + chunk - 1L)
    for (k in seq_along(mix$cells)) {
      cl <- mix$cells[[k]]
      X <- lp_of(m, cell_frame(pts[ii, , drop = FALSE], mix, cl, spec, level), spec)
      P[ii, ] <- P[ii, ] + cl$w * mix_eval(tabs[[k]], X %*% t(B))
    }
  }
  attr(P, "mix_table_err") <- max(vapply(tabs, function(t) t$err, 0))
  P
}

first_cross <- function(v, s) {
  if (is.na(v[1]) || v[1] <= 0) return(NA_real_)
  k <- which(v <= 0)[1]
  if (is.na(k)) return(NA_real_)
  s[k - 1L] + (s[k] - s[k - 1L]) * v[k - 1L] / (v[k - 1L] - v[k])
}

# top_in, bot_in and half_width_in per draw, on narrow windows around the point crossings
# (the W3.12 harness's draw_edges).
draw_edges <- function(m, spec, mix, level, met, B) {
  zt <- met[["top_in"]] / REF_HEIGHT_IN; zb <- met[["bot_in"]] / REF_HEIGHT_IN
  hw <- met[["half_width_in"]] / 12
  zwt <- ZG[abs(ZG - zt) <= WIN_ZN + 1e-9]
  zwb <- rev(ZG[abs(ZG - zb) <= WIN_ZN + 1e-9])
  xr <- XG[abs(XG - hw) <= WIN_X + 1e-9]
  xl <- rev(XG[abs(XG + hw) <= WIN_X + 1e-9])
  xc <- XG[I_CENTRE]
  pts <- rbind(expand.grid(zn = zwt, x_mid = xc)[, c("x_mid", "zn")],
               expand.grid(zn = zwb, x_mid = xc)[, c("x_mid", "zn")],
               data.frame(x_mid = xr, zn = ZN_MID), data.frame(x_mid = xl, zn = ZN_MID))
  L <- qlogis(draw_prob(m, spec, mix, level, pts, B))
  nt <- length(zwt); nb <- length(zwb); nc <- length(xc)
  o_b <- nt * nc; o_r <- o_b + nb * nc; o_l <- o_r + length(xr)
  t(vapply(seq_len(ncol(L)), function(j) {
    v <- L[, j]
    tops <- vapply(seq_len(nc), function(i) first_cross(v[(i - 1L) * nt + seq_len(nt)], zwt), 0)
    bots <- vapply(seq_len(nc), function(i) first_cross(v[o_b + (i - 1L) * nb + seq_len(nb)], zwb), 0)
    r <- first_cross(v[o_r + seq_along(xr)], xr)
    l <- first_cross(v[o_l + seq_along(xl)], xl)
    c(top_in = mean(tops) * REF_HEIGHT_IN, bot_in = mean(bots) * REF_HEIGHT_IN,
      half_width_in = (r - l) / 2 * 12)
  }, numeric(3)))
}

# area_sqin per draw. The band is the grid points inside the main contour's bounding box,
# widened by BOX_X ft and BOX_ZN, whose point-estimate logit lies within L_BAND of zero. They
# are re-evaluated for every draw; every other point keeps its point value, which only fixes
# its side of the contour. If a draw changes sign anywhere on the band's rim (|logit| >= L_RIM)
# its contour could leave the band, so that draw is re-evaluated on the full grid.
BOX_X <- 0.25; BOX_ZN <- 0.05
draw_area <- function(m, spec, mix, level, L0, B) {
  mc <- main_contour(L0)
  if (is.null(mc)) die("the point surface has no closed 50% contour around the zone centre")
  gx <- rep(XG, times = length(ZG)); gz <- rep(ZG, each = length(XG))
  in_box <- gx >= min(mc$x) - BOX_X & gx <= max(mc$x) + BOX_X &
    gz >= min(mc$y) - BOX_ZN & gz <= max(mc$y) + BOX_ZN
  band <- which(abs(L0) <= L_BAND & in_box)
  g <- expand.grid(x_mid = XG, zn = ZG)
  Lb <- qlogis(draw_prob(m, spec, mix, level, g[band, , drop = FALSE], B))
  rim <- which(abs(L0[band]) >= L_RIM)
  flips <- which(vapply(seq_len(nrow(B)), function(j) any(sign(Lb[rim, j]) != sign(L0[band][rim])), TRUE))
  out <- vapply(seq_len(nrow(B)), function(j) {
    L <- L0
    L[band] <- Lb[, j]
    contour_area(L)
  }, 0)
  for (j in flips) {
    Lf <- qlogis(draw_prob(m, spec, mix, level, g, B[j, , drop = FALSE]))
    out[j] <- contour_area(matrix(Lf[, 1], nrow = length(XG)))
  }
  attr(out, "n_band") <- length(band)
  attr(out, "n_full_grid") <- length(flips)
  out
}

# Mean probability per group of reference pitches, each scored at its own covariates with the
# period set to `level` and random effects at zero. override replaces a covariate.
# Returns a groups x (1 + draws) matrix: the point estimate, then one column per draw.
group_means <- function(m, spec, level, rows, group, B = NULL, override = list(), chunk = 4000L) {
  cols <- list(pitch_group = as.character(rows$pitch_group), velo = rows$velo,
               count_class = as.character(rows$count_class), stand = as.character(rows$stand))
  for (nm in names(override)) cols[[nm]] <- rep(override[[nm]], nrow(rows))
  nd_all <- new_frame(data.frame(x_mid = rows$x_mid, zn = rows$zn), spec, level, cols$pitch_group,
                      cols$velo, cols$count_class, cols$stand)
  gi <- match(group, sort(unique(group)))
  ng <- max(gi)
  if (is.function(m)) {
    p <- plogis(eta_of(m, nd_all, spec))
    return(matrix(as.vector(rowsum(p, gi, reorder = TRUE)) / tabulate(gi, ng), ncol = 1))
  }
  C <- cbind(stats::coef(m), if (!is.null(B)) t(B))
  S <- matrix(0, ng, ncol(C))
  for (st in seq(1L, nrow(rows), by = chunk)) {
    ii <- st:min(nrow(rows), st + chunk - 1L)
    E <- lp_of(m, nd_all[ii, , drop = FALSE], spec) %*% C
    R <- rowsum(plogis(E), gi[ii], reorder = TRUE)
    k <- as.integer(rownames(R))
    S[k, ] <- S[k, ] + R
  }
  S / tabulate(gi, ng)
}

ESTIMANDS <- c("top_in", "bot_in", "half_width_in", "area_sqin", "shadow_rate", "count_bias")
GEOM <- c("top_in", "bot_in", "half_width_in", "area_sqin")
ESTIMAND_UNITS <- c(top_in = "in", bot_in = "in", half_width_in = "in", area_sqin = "sq in",
                    shadow_rate = "pct", count_bias = "pp")

# The 2024 strike-count mix of 3-ball pitches in a reference sample.
three_ball_mix <- function(ref) {
  r3 <- ref[ref$balls == 3L, , drop = FALSE]
  if (nrow(r3) == 0L) die("no 3-ball pitch in the reference sample")
  w <- table(factor(as.character(r3$count_class), levels = CC_LEVELS)) / nrow(r3)
  setNames(as.numeric(w), CC_LEVELS)
}

# The estimands of one surface (season or half), at the point estimate and for every draw.
#   ref   the 2024 reference pitches of this fit's sample, on the fit's own height rule
#   geom_only  TRUE for W3.17 and P2, which need the four geometric estimands only
#   edges_only TRUE for SENS-B1-UNDERSMOOTH: the draws cover top_in, bot_in and half_width_in,
#              with no area draws; the point still carries all four geometric estimands
surface_estimands <- function(m, spec, mix, level, ref, B = NULL, geom_only = FALSE, edges_only = FALSE) {
  s <- std_surface(m, spec, mix, level)
  met <- edge_metrics(s)
  point <- met
  draws <- NULL
  diag <- list()
  if (!is.null(B)) {
    de <- draw_edges(m, spec, mix, level, met, B)
    if (edges_only) {
      draws <- de
      diag <- list(n_band = 0L, n_full_grid_draws = 0L)
    } else {
      da <- draw_area(m, spec, mix, level, unname(qlogis(s$grid)), B)
      draws <- cbind(de, area_sqin = as.vector(da))
      diag <- list(n_band = attr(da, "n_band"), n_full_grid_draws = attr(da, "n_full_grid"))
    }
  }
  if (!geom_only && !edges_only) {
    w3 <- three_ball_mix(ref)
    sh <- ref[shadow_band(ref$d), , drop = FALSE]
    cb <- ref[ref$d >= -1.5 & ref$d < 1.5, , drop = FALSE]
    cb_bin <- floor(cb$d + 0.5)
    M_sh <- group_means(m, spec, level, sh, rep(1L, nrow(sh)), B)
    M_cc <- lapply(setNames(CC_LEVELS, CC_LEVELS), function(cc) {
      group_means(m, spec, level, cb, cb_bin, B, override = list(count_class = cc))
    })
    P3 <- Reduce(`+`, lapply(CC_LEVELS, function(cc) w3[[cc]] * M_cc[[cc]]))
    cbias <- 100 * colMeans(P3 - M_cc[["2-strike"]])
    point <- c(point, shadow_rate = 100 * M_sh[1, 1], count_bias = cbias[1])
    if (!is.null(B)) draws <- cbind(draws, shadow_rate = 100 * M_sh[1, -1], count_bias = cbias[-1])
    diag <- c(diag, list(n_shadow_ref = nrow(sh), n_count_bias_ref = nrow(cb), three_ball_mix = as.list(w3)))
  }
  if (!is.null(draws)) diag$n_complete <- sum(stats::complete.cases(draws))
  list(point = point, draws = draws, surface = s, diag = diag)
}
