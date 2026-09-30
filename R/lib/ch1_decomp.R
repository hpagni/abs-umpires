# R/lib/ch1_decomp.R - the W3.16 decomposition, the binned-logistic secondary estimator, and
# the small helpers W3.17, W3.21, W6.7 and W6.8 share. Sourced by R/lib/ch1_fits.R.
#
# THE DECOMPOSITION, SOP W3.14-W3.17 and PREREGISTRATION.md section 8, verbatim in intent:
#   g         the 2022-2024 pre-trend: a precision-weighted linear season slope, weights
#             1 / var(theta_s) over the draws, s = 2022, 2023, 2024
#   Delta_buffer = theta_2025 - (theta_2024 + g)
#   Delta_ABS    = theta_2026 - (theta_2025 + g)
#   Delta_total  = theta_2026 - theta_2024
#   share_ABS    = Delta_ABS / (Delta_ABS + Delta_buffer), reported only when the 95% interval on
#                  Delta_ABS + Delta_buffer excludes zero (CH1-A9, D-59)
# Every interval comes from the joint draws: each draw's five season values give that draw's
# g and components. The weights are fixed once, from the draws, and used for the point and for
# every draw. Identity: Delta_buffer + Delta_ABS + 2g - Delta_total = 0 to 1e-9.

COMPONENTS <- c("g", "delta_buffer", "delta_abs", "delta_total", "sum_components", "share_abs")
IDENTITY_TOL <- 1e-9

# Annex 8.7 and D-R0-04: three recovery clauses were not met, and the owner's answer is to
# disclose them beside the intervals they qualify. The counts are the annex's table, from the
# synthetic recovery; nothing here is estimated. tests/ch1/test_ch1_sprint.R checks the annex still
# carries them. W3.16 writes them to T4's recovery_disclosure column.
RECOVERY_NOTE <- c(
  top_in = paste("annex 8.7, D-R0-04: in the synthetic recovery the top edge's 95% interval covered the truth in",
                 "91 of 100 injected replicates (bound 93), and its null 90% interval lay inside +/-0.10 in in 44 of",
                 "50 (bound 47), so an equivalence reading of the top edge is underpowered"),
  half_width_in = paste("annex 8.7, D-R0-04: in the synthetic recovery the half-width's null 90% interval covered zero",
                        "in 42 of 50 replicates (bound 43)"))

pretrend_weights <- function(draws_pre) {
  v <- apply(draws_pre, 2, stats::var, na.rm = TRUE)
  if (any(!is.finite(v)) || any(v <= 0)) die("a pre-trend season has no draw variance")
  1 / v
}

# theta: a draws x 5 matrix (or a 1 x 5 matrix for the point), columns 2022..2026.
decompose <- function(theta, w) {
  theta <- as.matrix(theta)
  stopifnot(ncol(theta) == 5L)
  s <- 2022:2024
  sb <- sum(w * s) / sum(w)
  pre <- theta[, 1:3, drop = FALSE]
  tb <- as.vector(pre %*% w) / sum(w)
  g <- as.vector((pre - tb) %*% (w * (s - sb))) / sum(w * (s - sb)^2)
  d_buf <- theta[, 4] - (theta[, 3] + g)
  d_abs <- theta[, 5] - (theta[, 4] + g)
  d_tot <- theta[, 5] - theta[, 3]
  sm <- d_abs + d_buf
  data.frame(g = g, delta_buffer = d_buf, delta_abs = d_abs, delta_total = d_tot,
             sum_components = sm, share_abs = d_abs / sm,
             identity_residual = d_buf + d_abs + 2 * g - d_tot)
}

# One estimand's decomposition: the point, the draws, and a row per component.
decompose_estimand <- function(point5, draws5, estimand, units) {
  ok <- stats::complete.cases(draws5)
  dr <- draws5[ok, , drop = FALSE]
  w <- pretrend_weights(dr[, 1:3, drop = FALSE])
  P <- decompose(matrix(point5, nrow = 1L), w)
  D <- decompose(dr, w)
  resid <- max(abs(c(P$identity_residual, D$identity_residual)))
  s95 <- qint(D$sum_components, 0.95)
  share_ok <- is.finite(s95[1]) && (s95[1] > 0 || s95[2] < 0)
  rows <- lapply(COMPONENTS, function(k) {
    i95 <- qint(D[[k]], 0.95); i90 <- qint(D[[k]], 0.90)
    data.frame(estimand = estimand, component = k, point = P[[k]], lo95 = i95[1], hi95 = i95[2],
               lo90 = i90[1], hi90 = i90[2],
               units = if (k == "share_abs") "ratio" else if (k == "g") paste(units, "per season") else units,
               reported = if (k == "share_abs") share_ok else TRUE,
               n_draws = nrow(dr), identity_residual = resid, stringsAsFactors = FALSE)
  })
  out <- do.call(rbind, rows)
  out$weights_2022_2023_2024 <- paste(fmt(w / sum(w), 4), collapse = ";")
  list(table = out, draws = D, point = P, weights = w, identity_residual = resid, share_reported = share_ok)
}

## --- the binned logistic, annex section 5 (the CH1-A5 secondary estimator) ------------------------
# d in 0.5 in bins over [-8, +8], 32 bins; cbind(strikes, balls) per bin x season x count_class x
# stand x edge; glm(cbind(strikes, balls) ~ 0 + bin + season + count_class + stand, binomial)
# per edge. A season's edge is the d where the probability, standardised to the 2024 mix of
# count_class and stand, crosses 0.5 on the logit scale, by linear interpolation between bin
# centres, walking outward from the deepest inside bin. Code of R/ch1/20_spec_dev.R (W3.11).
# Its draws come from N(beta, vcov) of each edge's glm.

D_BAND_IN <- 8; BIN_W_IN <- 0.5; N_BINS <- 32L
bin_index <- function(d) pmin(pmax(floor((d + D_BAND_IN) / BIN_W_IN), 0), N_BINS - 1L)
bin_centre <- function(j) -D_BAND_IN + BIN_W_IN * (j + 0.5)

aggregate_bins <- function(df) {
  df$bin <- as.integer(bin_index(df$d))
  df |>
    group_by(edge, bin, season, count_class, stand) |>
    summarise(strikes = sum(cs), balls = n() - sum(cs), .groups = "drop") |>
    as.data.frame()
}
fit_binned <- function(agg) {
  fits <- list()
  for (e in EDGE_LEVELS) {
    a <- agg[agg$edge == e, ]
    a$bin_f <- factor(a$bin, levels = sort(unique(a$bin)))
    a$season <- factor(as.character(a$season), levels = SEASON_LEVELS)
    a$count_class <- factor(a$count_class, levels = CC_LEVELS)
    a$stand <- factor(a$stand, levels = STAND_LEVELS)
    fits[[e]] <- glm(cbind(strikes, balls) ~ 0 + bin_f + season + count_class + stand,
                     family = binomial(), data = a)
  }
  fits
}
binned_ref_weights <- function(ref) {
  w <- as.data.frame(table(factor(ref$count_class, levels = CC_LEVELS),
                           factor(ref$stand, levels = STAND_LEVELS)), stringsAsFactors = FALSE)
  names(w) <- c("count_class", "stand", "n")
  w$w <- w$n / sum(w$n)
  w[w$n > 0, ]
}
# Season estimands of the binned logistic: point (B = NULL) or a draws x 4 matrix. A draw's
# crossing is read inside BIN_WIN_IN of the point crossing, as the bam draws are (the harness's
# window rule): a sparse bin far from the edge can be nearly separated, and its coefficient's
# huge variance must not move a draw's crossing.
BIN_WIN_IN <- 3
binned_estimands <- function(fits, w, season, B = NULL) {
  out <- list()
  for (e in EDGE_LEVELS) {
    f <- fits[[e]]
    bins <- as.integer(levels(f$model$bin_f))
    ctr <- bin_centre(bins)
    tt <- stats::delete.response(stats::terms(f))
    X <- lapply(seq_len(nrow(w)), function(r) {
      nd <- data.frame(bin_f = factor(bins, levels = bins), season = factor(season, levels = SEASON_LEVELS),
                       count_class = factor(w$count_class[r], levels = CC_LEVELS),
                       stand = factor(w$stand[r], levels = STAND_LEVELS))
      stats::model.matrix(tt, nd, contrasts.arg = f$contrasts)
    })
    prob <- function(C) Reduce(`+`, lapply(seq_len(nrow(w)), function(r) w$w[r] * plogis(X[[r]] %*% C)))
    v0 <- as.vector(qlogis(prob(matrix(stats::coef(f), ncol = 1))))
    j0 <- which(v0 > 0)[1]
    x0 <- if (is.na(j0)) NA_real_ else crossing(v0, ctr, j0, +1L)
    if (is.null(B)) { out[[e]] <- x0; next }
    win <- which(abs(ctr - x0) <= BIN_WIN_IN)
    V <- qlogis(prob(t(B[[e]])))
    out[[e]] <- apply(V[win, , drop = FALSE], 2, function(v) first_cross(v, ctr[win]))
  }
  top <- ABS_TOP_FRAC * REF_HEIGHT_IN + out[["top"]]
  bot <- ABS_BOT_FRAC * REF_HEIGHT_IN - out[["bot"]]
  hw <- PLATE_HALF_W_FT * 12 + out[["side"]]
  cbind(top_in = top, bot_in = bot, half_width_in = hw, area_sqin = 2 * hw * (top - bot))
}
binned_draws <- function(fits, n, seed) {
  set.seed(seed)
  lapply(fits, function(f) MASS::mvrnorm(n, stats::coef(f), stats::vcov(f)))
}

## --- CSV rows that more than one step writes -----------------------------------------------------

# Replace this writer's row (keyed on id) or append it; every other line stays byte for byte.
upsert_row <- function(path, row, key = "id") {
  stopifnot(nrow(row) == 1L)
  con <- textConnection("line", "w", local = TRUE)
  utils::write.table(row, con, sep = ",", row.names = FALSE, col.names = FALSE, qmethod = "double", na = "")
  close(con)
  if (!file.exists(path)) {
    ensure_dir(dirname(path))
    con <- textConnection("hdr", "w", local = TRUE)
    utils::write.table(row[0, , drop = FALSE], con, sep = ",", row.names = FALSE, qmethod = "double")
    close(con)
    writeLines(c(hdr, line), path)
    return(invisible("created"))
  }
  old <- readLines(path, warn = FALSE)
  cur <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character")
  if (!identical(names(cur), names(row))) die(path, " has columns ", paste(names(cur), collapse = ","),
                                              "; this writer's are ", paste(names(row), collapse = ","))
  i <- which(cur[[key]] == row[[key]])
  if (length(i) > 1L) die(path, " carries ", length(i), " rows with ", key, " = ", row[[key]])
  if (length(i) == 1L) {
    if (length(old) != nrow(cur) + 1L) die(path, " has a multi-line row; it cannot be edited line by line")
    old[i + 1L] <- line
    writeLines(old, path)
    return(invisible("replaced"))
  }
  writeLines(c(old, line), path)
  invisible("appended")
}

# The ledger, docs/numbers.json, regenerated by tools/comms/export_numbers.R (W7.24) after W6.7
# and W6.8. A synthetic run writes <dir>/docs/numbers.json beside <dir>/out instead. The exporter
# refuses a synthetic run that starts from docs/numbers.json, so a synthetic ledger starts from an
# empty base the first time and from itself after that. Returns the ledger's path.
ledger_path <- function(ctx) {
  if (ctx$synthetic) file.path(dirname(normalizePath(ctx$out)), "docs", "numbers.json") else file.path(ROOT, "docs", "numbers.json")
}
run_exporter <- function(ctx) {
  args <- file.path(ROOT, "tools", "comms", "export_numbers.R")
  led <- ledger_path(ctx)
  if (ctx$synthetic) {
    if (basename(normalizePath(ctx$out)) != "out") die("a synthetic run needs --out <dir>/out, so the exporter reads <dir>/out/")
    inputs <- dirname(normalizePath(ctx$out))
    base <- led
    if (!file.exists(base)) {
      base <- file.path(inputs, "docs", "numbers-base.SYNTHETIC.json")
      write_json_file(list(`_what` = "SYNTHETIC ledger base for a Chapter 1 dry run. No real entry.", entries = list()), base)
    }
    args <- c(args, "--inputs", inputs, "--base", base, "--out", led, "--synthetic")
  } else if (!identical(normalizePath(ctx$out), normalizePath(file.path(ROOT, "out"), mustWork = FALSE))) {
    die("a real run regenerates docs/numbers.json from out/; --out must be the repository's out/")
  }
  st <- system2("Rscript", args)
  check("docs/numbers.json regenerated by tools/comms/export_numbers.R", st == 0L, sprintf("exit %d", st))
  led
}

HEADLINE_COLS <- c("id", "step", "chapter", "sentence", "estimand", "point", "lo95", "hi95", "units",
                   "estimator", "source_csv", "source_row")

# Signed number for a sentence: two decimals for inches, one for square inches and points.
num_digits <- function(units) if (units %in% c("in", "in per season")) 2L else 1L
num_txt <- function(x, units) {
  s <- formatC(x, format = "f", digits = num_digits(units))
  sub("^-(0(\\.0+)?)$", "\\1", s)
}
ci_txt <- function(lo, hi, units) sprintf("95%% CI %s to %s", num_txt(lo, units), num_txt(hi, units))

# W6.7's headline, the template of SOP W3.14-W3.17: "Of the N square inches by which the called
# zone contracted between 2024 and 2026, X (95% CI a-b) is attributable to the 2025 grading-buffer
# cut and Y (95% CI c-d) to the ABS challenge system." N carries its own interval. An expansion
# reads "expanded", and every number is signed in the direction of the total change, so the
# sentence reads correctly either way and X + Y + 2g = N. causal = FALSE, when P1 or P2 failed,
# swaps the attribution for the seasons (PREREGISTRATION.md section 8). tot, buf and ab are the
# area_sqin rows of T4 for delta_total, delta_buffer and delta_abs.
headline_sentence <- function(tot, buf, ab, causal) {
  sg <- if (tot$point <= 0) -1 else 1
  iv <- function(x) {
    v <- sort(c(sg * x$lo95, sg * x$hi95))
    ci_txt(v[1], v[2], "sq in")
  }
  verb <- if (causal) c("is attributable to the 2025 grading-buffer cut", "to the ABS challenge system")
          else c("falls in the 2025 buffer season", "in the 2026 ABS season")
  sprintf("Of the %s square inches (%s) by which the called zone %s between 2024 and 2026, %s (%s) %s and %s (%s) %s.",
          num_txt(sg * tot$point, "sq in"), iv(tot), if (sg < 0) "contracted" else "expanded",
          num_txt(sg * buf$point, "sq in"), iv(buf), verb[1], num_txt(sg * ab$point, "sq in"), iv(ab), verb[2])
}

# D-P4-04, part 3: the ABS-measured arm must agree in sign with the primary on the buffer and ABS
# components, or the primary is reported as sensitive to the height cohort. W3.16 reads it on
# the area (CLAUSE_ESTIMAND) and writes the verdict to T4's height_cohort_flag column, one of
# the two strings below; W6.7 reads that column and nothing else to decide the wording.
CLAUSE_ESTIMAND <- "area_sqin"
CLAUSE_AGREE <- "agree"
CLAUSE_SENSITIVE <- "primary is sensitive to the height cohort"
CLAUSE_NOT_EVALUATED <- "not evaluated: the ABS-measured arm is missing"
height_cohort_flag <- function(agree) {
  agree <- as.logical(agree)
  if (length(agree) != 2L || anyNA(agree)) return(CLAUSE_NOT_EVALUATED)
  if (all(agree)) CLAUSE_AGREE else CLAUSE_SENSITIVE
}

# W6.7's sentence for the clause, from the flag W3.16 wrote. buf and ab are T4's area rows.
cohort_sentence <- function(buf, ab) {
  flag <- unique(c(buf$height_cohort_flag, ab$height_cohort_flag))
  if (length(flag) != 1L || !flag %in% c(CLAUSE_AGREE, CLAUSE_SENSITIVE)) {
    die("T4's height_cohort_flag is missing or reads ", paste(format(flag), collapse = " / "),
        "; D-P4-04's clause needs W3.16's verdict")
  }
  arm <- function(x) sprintf("%s sq in (%s)", num_txt(x$abs_cohort_point, "sq in"),
                             ci_txt(x$abs_cohort_lo95, x$abs_cohort_hi95, "sq in"))
  if (identical(flag, CLAUSE_AGREE)) {
    return(sprintf("The ABS-measured-height arm agrees in sign on both components: %s in 2025 and %s in 2026 (D-P4-04).",
                   arm(buf), arm(ab)))
  }
  sprintf(paste("The ABS-measured-height arm gives %s in 2025 and %s in 2026, against the primary in sign.",
                "The primary is therefore reported as sensitive to the height cohort (D-P4-04)."), arm(buf), arm(ab))
}
