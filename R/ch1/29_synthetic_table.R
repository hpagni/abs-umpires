#!/usr/bin/env Rscript
# R/ch1/29_synthetic_table.R - a seeded synthetic Chapter 1 analysis table, for the dry runs of
# SOP W3.14 to W3.18, W3.21, W6.7 and W6.8 before the prereg-v1 tag, and the score of a dry run
# against the table's known truth.
#
#   Rscript R/ch1/29_synthetic_table.R --make  --out DIR [--scale dry|tiny] [--seed N]
#   Rscript R/ch1/29_synthetic_table.R --score --table DIR/ch1_synth.parquet --out OUTROOT
#
# --make writes DIR/ch1_synth.parquet, DIR/ch1_synth.calibration.json and
# DIR/ch1_synth.truth.json. It reads no data file: every pitch, umpire, batter and call is drawn
# from the seed. The table has the analysis table's columns (R/ch1/10_build_analysis_table.R),
# is_synthetic = TRUE on every row, and x_front and z_front for W3.17.
#
# THE GENERATING MODEL. Coordinates are inches for a 72-inch batter: u = 12 x_mid, v = 72 zn,
# with zn on the batter's TRUE height. Season s has a rectangle [-hw_s, hw_s] x [bot_s, top_s];
# D is the signed distance from it, Euclidean at the corners, negative inside. The call is
# Bernoulli(plogis(eta)) with
#   eta = ALPHA - SLOPE * D + count class + handedness + pitch group + velocity + SLOPE * delta,
# where delta is the umpire-season-edge offset at the pitch's nearest edge: an umpire level, a
# persistent umpire x edge tendency, an umpire x season shift, a residual, and the umpire's
# buffer response (2025 and 2026, SD TAU_BUF) and ABS response (2026, SD TAU_ABS). Offsets are
# centred to mean zero over each season's umpires at each edge, so the league surface is the
# delta = 0 surface. The rectangle moves by a linear pre-trend g every season, by the injected
# buffer shift in 2025 and by the injected ABS shift in 2026:
#   top -0.60, bottom +0.30, half-width -0.10 in for ABS, the W3.12(a) injection;
#   top -0.30, bottom +0.15, half-width +0.05 in for the buffer; g = -0.05, +0.03, -0.04 in.
# The standardised 50% contour is a level set of D, so the contour's edges move by exactly the
# rectangle's shifts. --score reads the truth off the generating function with the W3.15
# estimand code, as the W3.12 harness did, and checks each interval against it.
#
# HEIGHTS. Batters active in 2025 or 2026 carry a measured height (the cohort, H_abs); their
# roster height is round(true height). Other batters are listed LIST_BIAS = 0.35 in tall. The
# table's H is roster + 0.002 in, as W3.7 stores it. The calibration file follows the real file's
# convention (R/lib/ch1_fits.R CAL_CONVENTION, the same string): both offsets are ADDED to roster
# height, so it carries offset_in 0.002 and offset_noncohort_in = -LIST_BIAS = -0.35 in, and the
# loader's primary rule gives a batter outside the cohort roster - 0.35 in, his true height up to
# rounding. SENS-HEIGHT-SINGLE (roster + 0.002 in for every batter) leaves the bias in.

args <- commandArgs(trailingOnly = TRUE)
ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))
opt <- parse_cli(args, flags = c("make", "score"))

SEED_DEFAULT <- 4290L
ALPHA <- 2.0          # logit at the rectangle edge; the 50% contour sits about 2 in outside it
SLOPE <- 1.0          # logit per inch
RECT_2022 <- c(top = 38.9, bot = 18.6, hw = 9.0)
G_IN   <- c(top = -0.05, bot = 0.03, hw = -0.04)
BUF_IN <- c(top = -0.30, bot = 0.15, hw = 0.05)
ABS_IN <- c(top = -0.60, bot = 0.30, hw = -0.10)
EFF_CC <- c("0-strike" = 0.25, "1-strike" = 0, "2-strike" = -0.35)
EFF_STAND <- c(L = 0, R = 0.05)
EFF_PG <- c(FF = 0, "SI/FC" = -0.05, BRK = 0.10, OFFSP = 0.02)
EFF_VELO <- 0.015
SD_LEVEL <- 0.10; SD_UMP_EDGE <- 0.15; SD_UMP_SEASON <- 0.08; SD_RESID <- 0.08
TAU_BUF <- 0.25; TAU_ABS <- 0.25
LIST_BIAS <- 0.35     # listed minus true height outside the cohort, in: listings run tall
O_COHORT <- 0.002
O_NONCOHORT <- -LIST_BIAS   # added to roster height, so negative when listings run tall
SCALES <- list(
  dry  = list(full = 20L, retire = 4L, join = 4L, part = 2L, gpu = 17L, gpu_part = 6L, ppg = 80L, batters = 420L),
  tiny = list(full = 8L, retire = 2L, join = 2L, part = 1L, gpu = 15L, gpu_part = 4L, ppg = 45L, batters = 160L))

rect_of <- function(season) {
  k <- season - 2022
  r <- RECT_2022 + G_IN * k
  if (season >= 2025) r <- r + BUF_IN
  if (season >= 2026) r <- r + ABS_IN
  r
}
signed_dist <- function(u, v, r) {
  dx <- abs(u) - r[["hw"]]
  dz <- pmax(r[["bot"]] - v, v - r[["top"]])
  ifelse(dx > 0 & dz > 0, sqrt(dx^2 + dz^2), pmax(dx, dz))
}
nearest_rect_edge <- function(u, v, r) {
  m <- cbind(side = abs(u) - r[["hw"]], top = v - r[["top"]], bot = r[["bot"]] - v)
  EDGE_LEVELS[max.col(m, ties.method = "first")]
}
fixed_eta <- function(cc, st, pg, velo) {
  unname(EFF_CC[as.character(cc)] + EFF_STAND[as.character(st)] + EFF_PG[as.character(pg)] +
           EFF_VELO * (velo - 90))
}
# The truth for the estimand code: eta with no umpire effect, on the analysis zn.
truth_fn <- function(season_col = "season") {
  function(nd) {
    s <- as.integer(as.character(nd[[season_col]]))
    out <- numeric(nrow(nd))
    for (ss in unique(s)) {
      i <- which(s == ss)
      out[i] <- ALPHA - SLOPE * signed_dist(12 * nd$x_mid[i], 72 * nd$zn[i], rect_of(ss)) +
        fixed_eta(nd$count_class[i], nd$stand[i], nd$pitch_group[i], nd$velo[i])
    }
    out
  }
}

make_table <- function(dir, scale, seed) {
  sc <- SCALES[[scale]]
  if (is.null(sc)) die("unknown scale ", scale)
  set.seed(seed)
  ump <- data.frame(umpire_hp_id = 500L + seq_len(sc$full + sc$retire + sc$join + sc$part),
                    kind = rep(c("full", "retire", "join", "part"), c(sc$full, sc$retire, sc$join, sc$part)))
  active <- function(kind, s) kind == "full" | kind == "part" | (kind == "retire" & s <= 2024) | (kind == "join" & s >= 2025)
  bat <- data.frame(batter = 600000L + seq_len(sc$batters), H_true = stats::rnorm(sc$batters, 73, 2.3),
                    stand = sample(STAND_LEVELS, sc$batters, TRUE, c(0.42, 0.58)),
                    start = sample(2019:2026, sc$batters, TRUE), len = sample(1:8, sc$batters, TRUE))
  bat$end <- bat$start + bat$len - 1L
  bat$cohort <- bat$end >= 2025
  bat$H_abs <- ifelse(bat$cohort, round(bat$H_true, 1), NA_real_)
  bat$roster <- ifelse(bat$cohort, round(bat$H_true), round(bat$H_true + LIST_BIAS))
  # umpire offsets, inches
  U <- nrow(ump)
  a_u <- stats::rnorm(U, 0, SD_LEVEL); b_u <- stats::rnorm(U, 0, TAU_BUF); c_u <- stats::rnorm(U, 0, TAU_ABS)
  h_ue <- matrix(stats::rnorm(U * 3, 0, SD_UMP_EDGE), U, 3, dimnames = list(NULL, EDGE_LEVELS))
  rows <- list()
  game_pk <- 0L
  off <- list()
  for (s in SEASONS) {
    ua <- ump[active(ump$kind, s), ]
    ng <- ifelse(ua$kind == "part", sc$gpu_part, sc$gpu)
    games <- data.frame(umpire_hp_id = rep(ua$umpire_hp_id, ng))
    days <- seq(as.Date(sprintf("%d-04-01", s)), as.Date(sprintf("%d-09-21", s)), by = "day")
    asb <- ASB[ASB$season == s, ]
    days <- days[days <= as.Date(paste0(s, "-", asb$asb_last)) | days >= as.Date(paste0(s, "-", asb$asb_first))]
    games$official_date <- sort(sample(days, nrow(games), TRUE))[sample.int(nrow(games))]
    games$game_pk <- s * 100000L + seq_len(nrow(games))
    ui <- match(ua$umpire_hp_id, ump$umpire_hp_id)
    w_us <- stats::rnorm(length(ui), 0, SD_UMP_SEASON)
    dlt <- sapply(EDGE_LEVELS, function(e) {
      x <- a_u[ui] + h_ue[ui, e] + w_us + stats::rnorm(length(ui), 0, SD_RESID) +
        b_u[ui] * (s >= 2025) + c_u[ui] * (s == 2026)
      x - mean(x)
    })
    off[[as.character(s)]] <- data.frame(umpire_hp_id = ua$umpire_hp_id, season = s, dlt)
    np <- stats::rpois(nrow(games), sc$ppg) + 1L
    gi <- rep(seq_len(nrow(games)), np)
    n <- length(gi)
    pool <- bat[bat$start <= s & bat$end >= s, ]
    bi <- sample.int(nrow(pool), n, TRUE)
    b <- pool[bi, ]
    pg <- sample(PG_LEVELS, n, TRUE, c(0.35, 0.25, 0.28, 0.12))
    velo <- ifelse(pg == "FF", stats::rnorm(n, 94, 2), ifelse(pg == "SI/FC", stats::rnorm(n, 92, 2.5),
                   ifelse(pg == "BRK", stats::rnorm(n, 83, 3.5), stats::rnorm(n, 85, 3))))
    ptype <- ifelse(pg == "FF", "FF", ifelse(pg == "SI/FC", sample(c("SI", "FC"), n, TRUE),
                    ifelse(pg == "BRK", sample(c("SL", "CU", "ST", "KC"), n, TRUE), sample(c("CH", "FS"), n, TRUE))))
    strikes <- sample(0:2, n, TRUE, c(0.45, 0.30, 0.25))
    balls <- sample(0:3, n, TRUE, c(0.40, 0.30, 0.20, 0.10))
    near <- stats::runif(n) < 0.55
    x_mid <- ifelse(near, stats::rnorm(n, 0, 0.55), stats::rnorm(n, 0, 0.9))
    zn_t <- ifelse(near, stats::rnorm(n, 0.40, 0.12), stats::rnorm(n, 0.42, 0.22))
    x_mid <- pmin(pmax(x_mid, -2.5), 2.5)
    zn_t <- pmin(pmax(zn_t, 0.02), 1.2)
    z_mid <- zn_t * b$H_true / 12
    r <- rect_of(s)
    u <- 12 * x_mid; v <- 72 * zn_t
    e_near <- nearest_rect_edge(u, v, r)
    um <- games$umpire_hp_id[gi]
    dl <- off[[as.character(s)]]
    dd <- as.matrix(dl[match(um, dl$umpire_hp_id), EDGE_LEVELS])[cbind(seq_len(n), match(e_near, EDGE_LEVELS))]
    cc <- CC_LEVELS[strikes + 1L]
    eta <- ALPHA - SLOPE * signed_dist(u, v, r) + fixed_eta(cc, b$stand, pg, velo) + SLOPE * dd
    cs <- as.integer(stats::runif(n) < plogis(eta))
    dz_in <- -0.425 - 0.09 * (96 - velo) + ifelse(pg == "BRK", -0.25, 0) + stats::rnorm(n, 0, 0.12)
    dx_in <- stats::rnorm(n, 0, 0.05)
    H <- b$roster + O_COHORT
    top_ft <- abs_top_ft(H); bot_ft <- abs_bot_ft(H)
    at_bat <- stats::ave(seq_len(n), gi, FUN = function(k) (seq_along(k) - 1L) %/% 4L + 1L)
    pnum <- stats::ave(seq_len(n), gi, FUN = seq_along)
    rows[[as.character(s)]] <- data.frame(
      pitch_uid = sprintf("%d:%d:%d", games$game_pk[gi], at_bat, pnum),
      game_pk = games$game_pk[gi], official_date = games$official_date[gi], season = s,
      regime = REGIME_OF[[as.character(s)]], analysis_set = "open",
      umpire_hp_id = um, umpire_season = paste0(um, ":", s), catcher = 700000L + sample.int(40L, n, TRUE),
      batter = b$batter, pitcher = 800000L + sample.int(300L, n, TRUE), stand = b$stand,
      p_throws = sample(c("L", "R"), n, TRUE, c(0.3, 0.7)), balls = balls, strikes = strikes,
      count_class = cc, pitch_type = ptype, pitch_group = pg, velo = velo, x_mid = x_mid, z_mid = z_mid,
      H = H, top_ft = top_ft, bot_ft = bot_ft, zn = z_norm(z_mid, H),
      d = signed_edge_in(x_mid, z_mid, top_ft, bot_ft), edge = nearest_edge(x_mid, z_mid, top_ft, bot_ft),
      cs = cs, H_abs = b$H_abs,
      d_abs = ifelse(is.na(b$H_abs), NA_real_, signed_edge_in(x_mid, z_mid, abs_top_ft(b$H_abs), abs_bot_ft(b$H_abs))),
      challenged = FALSE, is_overturned = FALSE, delta_run_exp = 0,
      x_front = x_mid - dx_in / 12, z_front = z_mid - dz_in / 12, is_synthetic = TRUE,
      stringsAsFactors = FALSE)
  }
  df <- do.call(rbind, rows)
  df <- df[order(df$season, df$game_pk, df$pitch_uid), ]
  rownames(df) <- NULL
  df$regime <- factor(df$regime, levels = REGIMES)
  df$analysis_set <- factor(df$analysis_set, levels = "open")
  df$umpire_season <- factor(df$umpire_season)
  df$stand <- factor(df$stand, levels = STAND_LEVELS)
  df$count_class <- factor(df$count_class, levels = CC_LEVELS)
  df$pitch_group <- factor(df$pitch_group, levels = PG_LEVELS)
  df$edge <- factor(df$edge, levels = EDGE_LEVELS)
  ensure_dir(dir)
  path <- file.path(dir, "ch1_synth.parquet")
  tb <- arrow::arrow_table(df)
  tb$metadata$w37_height <- sprintf("H = h_roster_in + o, o = %.12f in (synthetic)", O_COHORT)
  tb$metadata$synthetic <- sprintf("R/ch1/29_synthetic_table.R, scale %s, seed %d", scale, seed)
  arrow::write_parquet(tb, path)
  write_json_file(list(convention = CAL_CONVENTION, offset_in = O_COHORT, offset_noncohort_in = O_NONCOHORT,
                       synthetic = TRUE,
                       note = sprintf("synthetic: listings outside the cohort run %.2f in tall; both offsets are added to roster height",
                                      LIST_BIAS)),
                  file.path(dir, "ch1_synth.calibration.json"))
  offs <- do.call(rbind, off)
  truth <- list(seed = seed, scale = scale, n_rows = nrow(df), alpha = ALPHA, slope = SLOPE,
                rectangles = lapply(setNames(SEASONS, SEASON_LEVELS), function(s) as.list(rect_of(s))),
                injected = list(g = as.list(G_IN), buffer = as.list(BUF_IN), abs = as.list(ABS_IN)),
                tau_abs = TAU_ABS, tau_buf = TAU_BUF,
                realised_sd_abs_response = stats::sd(c_u[ump$kind != "retire"]),
                umpires = nrow(ump), offsets_centred_per_season_edge = TRUE)
  write_json_file(truth, file.path(dir, "ch1_synth.truth.json"))
  cat(sprintf("wrote %s: %s rows, %d umpires, %d batters, seasons %s\n", path, comma(nrow(df)), nrow(ump),
              nrow(bat), paste(SEASONS, collapse = " ")))
  cat(sprintf("called-strike rate %.3f; |d| <= 8 in on %.1f%% of rows; P1 share %.3f\n", mean(df$cs),
              100 * mean(abs(df$d) <= 8), mean(!is.na(df$H_abs))))
  invisible(path)
}

## --- the score: the dry run's estimates against the generating truth --------------------------

truth_thetas <- function(ctx, cal, rule) {
  df <- apply_heights(load_table(ctx), rule, cal, ctx)
  ref <- surface_rows(df)
  ref <- ref[ref$season == 2024L, ]
  spec <- make_spec("main")
  tf <- truth_fn()
  mix <- ref_mix(tf, spec, ref, REF_SEASON)
  th <- t(vapply(SEASON_LEVELS, function(s) surface_estimands(tf, spec, mix, s, ref)$point, numeric(6)))
  colnames(th) <- ESTIMANDS
  th
}

score_rows <- function(tab, th, label) {
  out <- list()
  for (e in intersect(unique(tab$estimand), colnames(th))) {
    te <- tab[tab$estimand == e, ]
    w <- as.numeric(strsplit(te$weights_2022_2023_2024[1], ";")[[1]])
    tr <- decompose(matrix(th[, e], nrow = 1L), w)
    for (k in c("g", "delta_buffer", "delta_abs", "delta_total")) {
      r <- te[te$component == k, ]
      out[[length(out) + 1L]] <- data.frame(
        fit = label, estimand = e, component = k, truth = tr[[k]], point = r$point, lo95 = r$lo95,
        hi95 = r$hi95, error = r$point - tr[[k]], covered = r$lo95 <= tr[[k]] & tr[[k]] <= r$hi95,
        stringsAsFactors = FALSE)
    }
  }
  do.call(rbind, out)
}

score_run <- function(opt) {
  ctx <- start_run("W3.12-dryrun-score", opt, "R/ch1/29_synthetic_table.R")
  if (!ctx$synthetic) refuse(ctx$step, "the score reads a synthetic table only")
  truth <- fromJSON(sub("\\.parquet$", ".truth.json", ctx$table))
  cal <- read_calibration(ctx, opt)
  th <- truth_thetas(ctx, cal, "primary")
  for (s in SEASON_LEVELS) record(sprintf("truth %s", s), paste(sprintf("%s %.3f", ESTIMANDS, th[s, ]), collapse = ", "))
  inj <- rbind(g = unlist(truth$injected$g), buffer = unlist(truth$injected$buffer), abs = unlist(truth$injected$abs))
  code_read <- c(top_in = th["2026", "top_in"] - th["2025", "top_in"],
                 bot_in = th["2026", "bot_in"] - th["2025", "bot_in"],
                 half_width_in = th["2026", "half_width_in"] - th["2025", "half_width_in"])
  record("ABS shift read off the truth by the estimand code",
         sprintf("2025 to 2026 change: top %.4f, bottom %.4f, half-width %.4f in (injected ABS %.2f, %.2f, %.2f plus g %.2f, %.2f, %.2f)",
                 code_read[1], code_read[2], code_read[3], inj["abs", "top"], inj["abs", "bot"], inj["abs", "hw"],
                 inj["g", "top"], inj["g", "bot"], inj["g", "hw"]))
  p <- ctx$paths
  prim <- read_csv_plain(file.path(p$tab, "T4_decomposition.csv"))
  sc <- score_rows(prim, th, "primary")
  arms_path <- file.path(p$tab, "T4_decomposition_arms.csv")
  if (file.exists(arms_path)) {
    arms <- read_csv_plain(arms_path)
    for (f in unique(arms$fit)) {
      # Each arm's truth on its own sample and height rule; the geometric truths do not depend
      # on either, the shadow rate and count bias read the arm's own reference pitches.
      th_f <- if (f %in% c("abs_cohort", "single_offset")) truth_thetas(ctx, cal, f) else th
      sc <- rbind(sc, score_rows(arms[arms$fit == f, ], th_f, f))
    }
  }
  write_csv_plain(sc, file.path(p$log, "dryrun_score.csv"))
  inj_ok <- c(delta_buffer = "buffer", delta_abs = "abs", g = "g")
  for (i in seq_len(nrow(sc))) {
    r <- sc[i, ]
    lab <- sprintf("%s %s %s", r$fit, r$estimand, r$component)
    det <- sprintf("truth %.3f, estimate %.3f (95%% CI %.3f to %.3f), error %+.3f", r$truth, r$point, r$lo95, r$hi95, r$error)
    if (r$fit == "primary" && r$estimand %in% c("top_in", "bot_in", "half_width_in") &&
        r$component %in% c("delta_buffer", "delta_abs")) {
      # Coverage is the gate. CH1-A7's +/-0.10 in is a mean error over 100 replicates, which one
      # dry run cannot test, so the error is recorded beside it.
      check(sprintf("covers truth: %s", lab), r$covered, det)
      record(sprintf("error %s 0.10 in: %s", if (abs(r$error) <= 0.10) "within" else "OUTSIDE", lab), det)
    } else {
      record(sprintf("%s %s", if (isTRUE(r$covered)) "covered" else "MISSED", lab), det)
    }
  }
  # D-P4-04's clause. Every batter shares the generating zone, so the ABS-measured arm's true
  # components have the primary's signs, and W3.16's flag must read "agree".
  t4 <- prim[prim$estimand == CLAUSE_ESTIMAND & prim$component %in% c("delta_buffer", "delta_abs"), ]
  tr_sign <- sign(decompose(matrix(th[, CLAUSE_ESTIMAND], nrow = 1L),
                            as.numeric(strsplit(t4$weights_2022_2023_2024[1], ";")[[1]]))[, c("delta_buffer", "delta_abs")])
  check("D-P4-04 flag reads agree, as the generating truth implies", identical(unique(prim$height_cohort_flag), CLAUSE_AGREE),
        sprintf("height_cohort_flag %s; true area signs %s; ABS-measured arm %s", paste(unique(prim$height_cohort_flag), collapse = "/"),
                paste(unlist(tr_sign), collapse = ", "), paste(sprintf("%+.2f", t4$abs_cohort_point), collapse = ", ")))
  so_rows <- prim$component %in% c("delta_buffer", "delta_abs") & prim$estimand %in% GEOM
  record("SENS-HEIGHT-SINGLE signs against the primary", sprintf("%d of %d geometric components agree",
                                                               sum(prim$sign_agrees_single_offset[so_rows], na.rm = TRUE), sum(so_rows)))
  prim_rows <- sc$fit == "primary" & sc$component %in% c("g", "delta_buffer", "delta_abs")
  record("primary coverage", sprintf("%d of %d intervals (g, buffer, ABS over six estimands) cover the truth",
                                     sum(sc$covered[prim_rows]), sum(prim_rows)))
  het <- file.path(p$tab, "T6_heterogeneity.csv")
  if (file.exists(het)) {
    h <- read_csv_plain(het)
    r <- h[h$fit == "sop" & h$quantity == "tau_abs", ]
    if (nrow(r) == 1L) record("tau_abs against its generating SD",
                              sprintf("true SD %.2f in (realised %.3f); sop median %.3f, 95%% CI %.3f to %.3f",
                                      truth$tau_abs, truth$realised_sd_abs_response, r$median, r$lo95, r$hi95))
  }
  finish(ctx$step)
}

if (isTRUE(opt$make)) {
  make_table(opt_get(opt, "out", die("--make needs --out DIR")), opt_get(opt, "scale", "dry"),
             opt_int(opt, "seed", SEED_DEFAULT))
} else if (isTRUE(opt$score)) {
  score_run(opt)
} else {
  cat("usage: 29_synthetic_table.R --make --out DIR [--scale dry|tiny] [--seed N]\n",
      "       29_synthetic_table.R --score --table PARQUET --out OUTROOT\n", file = stderr())
  quit(status = 2)
}
