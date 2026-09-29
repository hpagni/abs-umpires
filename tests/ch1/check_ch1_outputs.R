#!/usr/bin/env Rscript
# tests/ch1/check_ch1_outputs.R - the verify half of SOP W3.14 to W3.18, W3.21, W6.7 and W6.8.
#
#   Rscript tests/ch1/check_ch1_outputs.R --out out --step W3.16
#   Rscript tests/ch1/check_ch1_outputs.R --out <dry-run root>/out --step all --synthetic
#
# It reads the outputs a step wrote, refits nothing, and re-derives what can be re-derived:
#   W3.14  every fit has its object, its 1,000 Vc draws and a receipt with the SOP section 1.4
#          keys; the union receipt sits beside the objects (GD-01); on real outputs every
#          receipt's git_sha descends from prereg-v1 (GD-12) and no max_official_date passes the
#          last open day
#   W3.15  T3 has five seasons and six estimands for the primary fit, and every interval equals
#          the quantiles of its draws column
#   W3.16  T4 re-derived from T3 and the draws to 1e-9; the identity residual under 1e-9; the
#          share reported only under the CH1-A9 rule; W3.16's headline row present
#   W3.17  top, bottom, width and area rows, each with a 95% interval (CH1-A13); one quantity named
#          as the one the component was subtracted from; T9 present; the figure and its CSV
#   W3.18  T6 and umpire_eb.csv present, no per-umpire column, CH1-A6 stated, MT-05 on real fits
#   W3.21  P1 to P4 present, P1 scored as two one-sided tests against 0.5 pp and 3 sq in
#   W6.7   every slot has a 95% interval and matches its source row digit for digit; the ledger
#          is what tools/comms/export_numbers.R --check regenerates; CALL and BREAK_YEAR absent
#   W6.8   SD_UMP, REL_UMP and N_UMP match umpire_eb.csv; REL_UMP is the response's reliability
# Exit 0 when every check passes, 1 otherwise.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))
opt <- parse_cli(commandArgs(trailingOnly = TRUE), flags = "synthetic")
OUT <- opt_get(opt, "out", file.path(ROOT, "out"))
P <- out_paths(OUT)
STEPS <- c("W3.14", "W3.15", "W3.16", "W3.17", "W3.18", "W3.21", "W6.7", "W6.8")
want <- opt_get(opt, "step", "all")
steps <- if (want == "all") STEPS else strsplit(want, ",")[[1]]
REAL <- !isTRUE(opt$synthetic)
CONTRACT <- c("n_games", "n_rows", "min_official_date", "max_official_date", "game_pk_sha256",
              "analysis_sets_touched", "seed", "code_sha256", "git_sha")
has <- function(f) check(sprintf("present: %s", sub(paste0("^", OUT, "/"), "", f)), file.exists(f), "")
csv <- function(f) if (file.exists(f)) read_csv_plain(f) else NULL
same <- function(a, b, tol = 1e-9) length(a) == length(b) && all(is.na(a) == is.na(b)) &&
  all(abs(a[!is.na(a)] - b[!is.na(b)]) <= tol)

receipts <- function() {
  fs <- list.files(P$models, pattern = "^provenance\\.json$", recursive = TRUE, full.names = TRUE)
  c(fs, list.files(P$model, pattern = "^provenance\\.json$", full.names = TRUE))
}

chk_w314 <- function() {
  for (fit in c("main", "abs_cohort", "panel")) {
    has(file.path(P$model, sprintf("surface_%s.rds", fit)))
    f <- file.path(P$model, sprintf("draws_vc_%s.rds", fit))
    if (has(f)) {
      cd <- readRDS(f)
      check(sprintf("%s draws: a 1,000-row matrix from N(beta, Vc)", fit),
            is.matrix(cd) && identical(attr(cd, "covariance"), "Vc") && (nrow(cd) == N_DRAWS || !REAL) &&
              all(is.finite(cd)), sprintf("%d x %d, %s", NROW(cd), NCOL(cd), attr(cd, "covariance")))
    }
  }
  has(file.path(P$model, "surface_binned.rds"))
  has(file.path(P$model, "provenance.json"))
  last <- if (REAL) format(last_open_date()) else "9999-12-31"
  tag_ok <- function(sha) {
    st <- suppressWarnings(system2("git", c("-C", ROOT, "merge-base", "--is-ancestor", prereg_tag(), sha),
                                   stdout = FALSE, stderr = FALSE))
    identical(as.integer(st), 0L)
  }
  for (f in receipts()) {
    r <- fromJSON(f)
    lab <- sub(paste0("^", OUT, "/"), "", f)
    check(sprintf("GD-01 keys: %s", lab), all(CONTRACT %in% names(r)), paste(setdiff(CONTRACT, names(r)), collapse = ", "))
    check(sprintf("seal: %s", lab), is.null(r$max_official_date) || is.na(r$max_official_date) ||
            r$max_official_date <= last, format(r$max_official_date))
    # ops/check_seal_order.sh reads git_sha as one commit
    check(sprintf("one git_sha: %s", lab), is.character(r$git_sha) && length(r$git_sha) == 1L &&
            grepl("^[0-9a-f]{40}$", r$git_sha), format(r$git_sha))
    if (REAL) check(sprintf("GD-12: %s", lab), tag_ok(r$git_sha), r$git_sha)
  }
}

chk_w315 <- function() {
  t3 <- csv(file.path(P$tab, "T3_estimands.csv"))
  if (!has(file.path(P$tab, "T3_estimands.csv"))) return()
  m <- t3[t3$fit == "main", ]
  check("T3 primary: five seasons x six estimands", nrow(m) == 30L && setequal(m$season, SEASONS) &&
          setequal(m$estimand, ESTIMANDS), sprintf("%d rows", nrow(m)))
  for (fit in unique(t3$fit)) {
    dr <- csv(file.path(P$model, sprintf("estimand_draws_%s.csv", fit)))
    if (is.null(dr)) { check(sprintf("draws for %s", fit), FALSE, "absent"); next }
    tt <- t3[t3$fit == fit, ]
    lo <- hi <- numeric(nrow(tt))
    for (i in seq_len(nrow(tt))) {
      q <- qint(dr[[paste(tt$season[i], tt$estimand[i], sep = "_")]])
      lo[i] <- q[1]; hi[i] <- q[2]
    }
    check(sprintf("T3 %s: intervals are the draws' quantiles", fit), same(lo, tt$lo95, 1e-6) && same(hi, tt$hi95, 1e-6),
          sprintf("%d rows, %d draws", nrow(tt), nrow(dr)))
  }
}

chk_w316 <- function() {
  f4 <- file.path(P$tab, "T4_decomposition.csv")
  if (!has(f4)) return()
  t4 <- csv(f4); t3 <- csv(file.path(P$tab, "T3_estimands.csv"))
  dr <- csv(file.path(P$model, "estimand_draws_main.csv"))
  check("identity residual below 1e-9 on every row", max(abs(t4$identity_residual)) < IDENTITY_TOL,
        sprintf("max %.2e", max(abs(t4$identity_residual))))
  ok <- TRUE
  for (e in unique(t4$estimand)) {
    p5 <- vapply(SEASON_LEVELS, function(s) t3$point[t3$fit == "main" & t3$season == as.integer(s) & t3$estimand == e], 0)
    res <- decompose_estimand(p5, as.matrix(dr[, paste(SEASON_LEVELS, e, sep = "_")]), e, ESTIMAND_UNITS[[e]])$table
    got <- t4[t4$estimand == e, ]
    ok <- ok && same(res$point, got$point[match(res$component, got$component)], 1e-9) &&
      same(res$lo95, got$lo95[match(res$component, got$component)], 1e-9) &&
      identical(res$reported, as.logical(got$reported[match(res$component, got$component)]))
  }
  check("T4 re-derived from T3 and the W3.15 draws", ok, "points, intervals and the CH1-A9 share rule")
  has(file.path(P$models, "ch1_W3_16", "provenance.json"))
  hl <- csv(file.path(P$tables, "headline.csv"))
  check("headline.csv carries W3.16's row", !is.null(hl) && "CH1_W316" %in% hl$id, "")
  if (!is.null(hl) && "CH1_W316" %in% hl$id) {
    s <- hl$sentence[hl$id == "CH1_W316"]
    check("W3.16's sentence is descriptive", !grepl("caus(al|ed|es)|attributable|because of ABS", s, ignore.case = TRUE), s)
  }
}

chk_w317 <- function() {
  fp <- file.path(P$tab, "T4_plane_component.csv")
  if (!has(fp)) return()
  tp <- csv(fp)
  check("CH1-A13: top, bottom and width rows, each with a 95% interval",
        all(c("top_in", "bot_in", "half_width_in") %in% tp$estimand) && all(is.finite(c(tp$lo95, tp$hi95))), "")
  check("one quantity named as the one the component was subtracted from", length(unique(tp$subtracted_from)) == 1L,
        unique(tp$subtracted_from))
  has(file.path(P$tab, "T9_published_comparison.csv"))
  has(file.path(P$fig, "F_dz_by_pitch_type.png"))
  has(file.path(P$fig, "F_dz_by_pitch_type.csv"))
}

chk_w318 <- function() {
  t6 <- csv(file.path(P$tab, "T6_heterogeneity.csv"))
  eb <- csv(file.path(P$tab, "umpire_eb.csv"))
  if (!has(file.path(P$tab, "T6_heterogeneity.csv")) || !has(file.path(P$tab, "umpire_eb.csv"))) return()
  check("no per-umpire column in the published tables", !any(c("umpire_hp_id", "umpire") %in% c(names(t6), names(eb))), "")
  check("CH1-A6 stated", all(nzchar(t6$ch1_a6)), unique(t6$ch1_a6))
  if (REAL) for (k in c("sop", "ue_us")) {
    r <- t6[t6$fit == k & t6$quantity == "tau_abs", ]
    check(sprintf("MT-05 %s", k), nrow(r) == 1L && isTRUE(as.logical(r$mt05_pass)), "")
  }
}

chk_w321 <- function() {
  t5 <- csv(file.path(P$tab, "T5_placebos.csv"))
  if (!has(file.path(P$tab, "T5_placebos.csv"))) return()
  check("P1 to P4 present", all(c("P1", "P2", "P3", "P4") %in% t5$placebo), "")
  p1 <- t5[t5$placebo == "P1", ]
  check("P1 is two one-sided tests at 0.5 pp and 3 sq in, 90% intervals", nrow(p1) == 2L &&
          setequal(p1$margin_or_threshold, c(0.5, 3)) && all(p1$interval_level == 0.90), "")
}

chk_w67 <- function() {
  fs <- file.path(P$tables, "abstract_slots_ch1.csv")
  if (!has(fs)) return()
  sl <- csv(fs)
  check("CALL and BREAK_YEAR unfilled", !any(c("CALL", "BREAK_YEAR") %in% sl$slot), "")
  t5 <- csv(file.path(P$tab, "T5_placebos.csv")); hl <- csv(file.path(P$tables, "headline.csv"))
  if (!is.null(t5) && !is.null(hl)) {
    causal_ok <- all(t5$placebo_verdict[t5$placebo %in% c("P1", "P2")] == "pass")
    s67 <- hl$sentence[hl$id == "CH1_W67"]
    check("W6.7's sentence names a cause only when P1 and P2 passed", length(s67) == 1L &&
            (causal_ok || !grepl("caus(al|ed|es)|attributable|because of ABS", s67, ignore.case = TRUE)), s67)
    check("W6.7 states D-P4-04's sign-agreement reading", "CH1_W67_COHORT" %in% hl$id, "")
  }
  check("every slot carries a 95% interval", all(is.finite(sl$lo95) & is.finite(sl$hi95)), "")
  for (i in seq_len(nrow(sl))) {
    src <- csv(file.path(dirname(OUT), sl$source_csv[i]))
    cols <- strsplit(sl$source_columns[i], ";")[[1]]
    v <- vapply(cols, function(cn) src[[cn]][sl$source_row[i]], 0)
    mine <- c(if (length(cols) == 3L) sl$point[i], sl$lo95[i], sl$hi95[i])
    check(sprintf("%s traces to %s row %d", sl$slot[i], sl$source_csv[i], sl$source_row[i]), same(v, mine, 0), "")
  }
  led <- if (REAL) file.path(ROOT, "docs", "numbers.json") else file.path(dirname(OUT), "docs", "numbers.json")
  args <- c(file.path(ROOT, "tools", "comms", "export_numbers.R"), "--check", "--inputs", dirname(OUT),
            "--base", led, "--out", led, if (!REAL) "--synthetic")
  check("the ledger is the exporter's output", system2("Rscript", args, stdout = FALSE) == 0L, led)
}

chk_w68 <- function() {
  f <- file.path(P$tab, "umpire_eb_summary.csv")
  if (!has(f)) return()
  s <- csv(f); eb <- csv(file.path(P$tab, "umpire_eb.csv"))
  q <- c(SD_UMP = "tau_abs", REL_UMP = "split_half_response", N_UMP = "n_umpires_behind_both")
  for (k in names(q)) {
    r <- s[s$slot == k, ]; e <- eb[eb$quantity == q[[k]], ]
    check(sprintf("%s matches umpire_eb.csv", k), nrow(r) == 1L && nrow(e) == 1L && same(c(r$point, r$lo95, r$hi95),
                                                                                        c(e$point, e$lo95, e$hi95), 0), "")
  }
  check("REL_UMP is the reliability of the response", grepl("RESPONSE", s$estimator[s$slot == "REL_UMP"]), "")
}

for (st in steps) {
  cat(sprintf("\n== %s\n", st))
  switch(st, W3.14 = chk_w314(), W3.15 = chk_w315(), W3.16 = chk_w316(), W3.17 = chk_w317(), W3.18 = chk_w318(),
         W3.21 = chk_w321(), W6.7 = chk_w67(), W6.8 = chk_w68(), die("unknown step ", st))
}
finish(paste("check", want))
