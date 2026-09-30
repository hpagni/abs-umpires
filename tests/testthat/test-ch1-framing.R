# tests/testthat/test-ch1-framing.R - SOP W3.19, catcher framing by regime, and CH1-A11.
#
#   Rscript -e 'testthat::test_dir("tests/testthat", filter = "ch1-framing", stop_on_failure = TRUE)'
#   W319_OUT=<root> reads <root> instead of out/ (a synthetic dry run; W319_SYNTHETIC=1 then waives
#   the clauses only a real run can meet: 1,000 replicates, the Savant files, the W3.14 arms).
#
# The test re-reads what R/ch1/30_framing.R wrote and refits nothing. It re-derives from the
# catcher-season sidecar every per-season SD, top-30 mean, split-half reliability and qualification
# flag the tables print; re-derives the decomposition and the reliability contrasts from the season
# points; re-derives CH1-A11's correlation from the matched pairs; traces every number of the prose
# to the CSV row it came from; checks the surface is catcher-free, both value types and both 2026
# conventions are present, the receipt's hashes match the files, and the script opens no network.

find_root <- function() {
  r <- Sys.getenv("ABSUMP_ROOT", "")
  if (nzchar(r)) return(normalizePath(r))
  d <- normalizePath(getwd())
  repeat {
    if (file.exists(file.path(d, "R", "ch1", "30_framing.R"))) return(d)
    p <- dirname(d)
    if (identical(p, d)) stop("cannot find the repository root above ", getwd())
    d <- p
  }
}
ROOT <- find_root()
OUT <- Sys.getenv("W319_OUT", file.path(ROOT, "out"))
SYNTHETIC <- identical(Sys.getenv("W319_SYNTHETIC", ""), "1")
TAB <- file.path(OUT, "ch1", "tab")
PUB <- file.path(OUT, "tables")
PROSE <- file.path(OUT, "ch1", "prose", "framing.md")
SCRIPT <- file.path(ROOT, "R", "ch1", "30_framing.R")
rd <- function(f) utils::read.csv(f, stringsAsFactors = FALSE, check.names = FALSE)
tabf <- function(n) file.path(TAB, paste0("framing_", n, ".csv"))
pubf <- function(n) file.path(PUB, paste0("ch1_framing_", n, ".csv"))
SEASONS <- as.character(2022:2026)
DW <- "2026_through_05-18"
VARS <- list(c("cnt", "original"), c("flat", "original"), c("cnt", "sis"), c("flat", "sis"))
sfx <- function(v, cv) if (cv == "original") v else paste0(v, "_sis")
TOL <- 1e-9

test_that("every output of the step is on disk", {
  for (n in c("sample", "sanity", "run_values", "catcher_seasons", "by_season", "decomposition", "reliability_change",
              "doolittle", "validity", "replicate_completeness", "centring", "prose_numbers")) expect_true(file.exists(tabf(n)), info = n)
  for (n in c("by_regime", "decomposition", "reliability", "doolittle", "validity")) expect_true(file.exists(pubf(n)), info = n)
  expect_true(file.exists(PROSE))
  expect_true(file.exists(file.path(OUT, "models", "ch1_W3_19", "provenance.json")))
  expect_true(file.exists(file.path(OUT, "models", "surface_framing", "provenance.json")))
  if (!SYNTHETIC) for (n in c("validity_pairs", "arms")) expect_true(file.exists(tabf(n)), info = n)
})

test_that("the expected-strike surface is catcher-free and fitted to P0", {
  pv <- jsonlite::fromJSON(file.path(OUT, "models", "surface_framing", "provenance.json"))
  expect_false(grepl("catcher|fielder|framing", pv$formula, ignore.case = TRUE))
  expect_true(grepl('s(umpire_hp_id, bs = "re")', pv$formula, fixed = TRUE))
  expect_true(all(c("input_frame_sha256", "seed", "model_code_sha256") %in% names(pv$cache_parts)))
  expect_equal(pv$cache_parts$seed, 20260922)
  sm <- rd(tabf("sample"))
  expect_equal(pv$n_rows, sm$called_pitches[sm$season == "all"])
  expect_equal(sum(sm$called_pitches[sm$season != "all"]), sm$called_pitches[sm$season == "all"])
  expect_true(all(abs(sm$mean_obs_minus_exp) < 2e-3))
  if (!SYNTHETIC) expect_true(all(sm$innings_per_team_game > 8.5 & sm$innings_per_team_game < 9.2))
})

test_that("run values are count-specific from delta_run_exp, with Tango's 0-0 figures as the check only", {
  rv <- rd(tabf("run_values"))
  po <- rv[rv$table == "pooled_2022_2024", ]
  expect_equal(nrow(po), 12L)
  expect_true(all(po$rv_strike_vs_ball > 0))
  expect_equal(po$rv_strike_vs_ball, po$mean_dre_ball - po$mean_dre_strike, tolerance = TOL)
  expect_true(all(paste0("season_", SEASONS) %in% rv$table))
  sn <- rd(tabf("sanity"))
  expect_setequal(sn$check, c("tango_00_ball", "tango_00_strike"))
  expect_equal(sn$reference[sn$check == "tango_00_ball"], 0.034)
  expect_equal(sn$reference[sn$check == "tango_00_strike"], -0.042)
  z <- po[po$count == "0-0", ]
  expect_equal(sn$value[sn$check == "tango_00_ball"], z$mean_dre_ball, tolerance = TOL)
  expect_true(all(sn$pass) && all(abs(sn$value - sn$reference) <= 0.010))
})

cs_all <- function() {
  x <- rd(tabf("catcher_seasons"))
  x[x$window == "season", ]
}

test_that("qualification is a quarter of the season's mean team innings", {
  x <- cs_all()
  q <- as.vector(0.25 * tapply(x$innings, x$season, sum)[as.character(x$season)] / 30)
  expect_equal(unname(x$qual_innings), unname(q), tolerance = 1e-6)
  expect_identical(as.logical(x$qualified), unname(x$innings >= x$qual_innings))
})

test_that("SDs, top-30 means and split-half reliabilities re-derive from the catcher-season values", {
  x <- cs_all()
  bs <- rd(tabf("by_season"))
  for (vc in VARS) {
    s <- sfx(vc[1], vc[2])
    for (se in SEASONS) {
      q <- x[x$season == as.integer(se) & x$qualified, ]
      rate <- q[[paste0("runs_", s, "_per100")]]
      get <- function(m) bs$point[bs$period == se & bs$metric == m & bs$value_type == vc[1] & bs$convention == vc[2]]
      expect_equal(get("sd_raw_per100"), stats::sd(rate), tolerance = TOL, info = paste(s, se))
      expect_equal(get("top30_mean_per100"), mean(sort(rate, decreasing = TRUE)[seq_len(min(30, length(rate)))]),
                   tolerance = TOL, info = paste(s, se))
      nv <- q[[paste0("se_noise_", s, "_per100")]]^2
      expect_equal(get("sd_signal_per100"), sqrt(max(0, stats::sd(rate)^2 - mean(nv))), tolerance = 1e-8, info = paste(s, se))
      a <- q[[paste0("odd_", s, "_per1000")]]; b <- q[[paste0("even_", s, "_per1000")]]
      ok <- is.finite(a) & is.finite(b)
      r <- stats::cor(a[ok], b[ok])
      expect_equal(get("split_half_r"), r, tolerance = 1e-8, info = paste(s, se))
      expect_equal(get("reliability_sb"), 2 * r / (1 + r), tolerance = 1e-8, info = paste(s, se))
    }
  }
})

test_that("every regime carries every statistic, both value types and both 2026 conventions, with intervals", {
  br <- rd(pubf("by_regime"))
  for (p in c("pre_buffer", "buffer_2025", "abs_2026", DW)) for (vc in VARS) {
    for (m in c("sd_raw_per100", "sd_signal_per100", "top30_mean_per100", "reliability_sb")) {
      r <- br[br$period == p & br$metric == m & br$value_type == vc[1] & br$convention == vc[2], ]
      expect_equal(nrow(r), 1L, info = paste(p, m, vc[1], vc[2]))
      expect_true(is.finite(r$point) && is.finite(r$lo95) && is.finite(r$hi95) && r$lo95 <= r$hi95,
                  info = paste(p, m, vc[1], vc[2]))
      if (!SYNTHETIC) expect_equal(r$n_reps, 1000L)
    }
  }
  expect_equal(unique(br$role[br$value_type == "cnt" & br$convention == "original"]), "primary")
  bs <- rd(tabf("by_season"))
  for (m in c("sd_signal_per100", "top30_mean_per100", "reliability_sb")) {
    pt <- function(p) bs$point[bs$period == p & bs$metric == m & bs$value_type == "cnt" & bs$convention == "original"]
    expect_equal(pt("pre_buffer"), mean(c(pt("2022"), pt("2023"), pt("2024"))), tolerance = TOL)
  }
  cmp <- rd(tabf("replicate_completeness"))
  expect_true(all(cmp$share >= 0.99))
})

test_that("SIS drops exactly the challenged pitches, and only in 2026", {
  x <- cs_all()
  none <- x$challenged_pitches == 0
  expect_true(all(x$challenged_pitches[x$season < 2026] == 0))
  expect_equal(x$runs_cnt_sis_uncentred[none], x$runs_cnt_uncentred[none], tolerance = TOL)
  expect_equal(x$runs_flat_sis_uncentred[none], x$runs_flat_uncentred[none], tolerance = TOL)
  expect_true(any(abs(x$runs_cnt_sis_uncentred - x$runs_cnt_uncentred)[!none] > 0))
})

test_that("runs are centred on the league-average catcher of each season, per called pitch", {
  x <- rd(tabf("catcher_seasons"))
  ct <- rd(tabf("centring"))
  for (w in c("season", DW)) for (vc in VARS) {
    s <- sfx(vc[1], vc[2])
    nm <- paste(vc[1], vc[2], sep = "_")
    for (se in unique(x$season[x$window == w])) {
      q <- x[x$window == w & x$season == se, ]
      n <- q$called_pitches - if (vc[2] == "sis") q$challenged_pitches else 0
      expect_lt(abs(sum(q[[paste0("runs_", s)]])), 1e-6)
      k <- (q[[paste0("runs_", s, "_uncentred")]] - q[[paste0("runs_", s)]])[n > 0] / n[n > 0]
      c0 <- ct$league_runs_per_pitch[ct$window == w & ct$season == se & ct$variant == nm]
      expect_equal(length(c0), 1L)
      expect_equal(k, rep(c0, length(k)), tolerance = 1e-8, info = paste(w, se, nm))
      expect_equal(c0, sum(q[[paste0("runs_", s, "_uncentred")]]) / sum(n), tolerance = 1e-10)
    }
  }
})

test_that("the decomposition re-derives from the season points and keeps its identity", {
  dc <- rd(pubf("decomposition"))
  bs <- rd(tabf("by_season"))
  for (vc in VARS) for (m in c("sd_signal_per100", "sd_raw_per100", "top30_mean_per100", "reliability_sb")) {
    d <- dc[dc$estimand == m & dc$value_type == vc[1] & dc$convention == vc[2], ]
    g <- function(k) d$point[d$component == k]
    expect_equal(g("delta_buffer") + g("delta_abs") + 2 * g("g"), g("delta_total"), tolerance = TOL)
    th <- vapply(SEASONS, function(s) bs$point[bs$period == s & bs$metric == m & bs$value_type == vc[1] &
                                                  bs$convention == vc[2]], 0)
    w <- as.numeric(strsplit(d$weights_2022_2023_2024[1], ";")[[1]])
    yr <- 2022:2024
    sb <- sum(w * yr) / sum(w); tb <- sum(w * th[1:3]) / sum(w)
    gg <- sum(w * (yr - sb) * (th[1:3] - tb)) / sum(w * (yr - sb)^2)
    expect_equal(g("g"), gg, tolerance = 1e-3)   # the CSV rounds the weights to 4 decimals
    expect_equal(g("delta_total"), th[[5]] - th[[3]], tolerance = TOL)
    expect_equal(g("delta_abs"), th[[5]] - th[[4]] - g("g"), tolerance = TOL)
    s <- d[d$component == "sum_components", ]
    expect_identical(as.logical(d$reported[d$component == "share_abs"]), s$lo95 > 0 || s$hi95 < 0)
  }
})

test_that("whether reliability fell under ABS is answered with its own interval", {
  rl <- rd(pubf("reliability"))
  bs <- rd(tabf("by_season"))
  for (vc in VARS) {
    r <- rl[rl$value_type == vc[1] & rl$convention == vc[2], ]
    expect_setequal(r$contrast, c("2026_minus_2025", "2026_minus_pre_buffer", "2025_minus_pre_buffer", "g", "delta_buffer",
                                  "delta_abs"))
    pt <- function(p) bs$point[bs$period == p & bs$metric == "reliability_sb" & bs$value_type == vc[1] & bs$convention == vc[2]]
    expect_equal(r$point[r$contrast == "2026_minus_2025"], pt("2026") - pt("2025"), tolerance = TOL)
    want <- ifelse(r$hi95 < 0, "fell", ifelse(r$lo95 > 0, "rose", "no change distinguishable from zero"))
    expect_identical(r$reading, want)
  }
})

test_that("Doolittle's comparable is scored on his window and on the full season", {
  dl <- rd(pubf("doolittle"))
  z <- dl[dl$value_type == "cnt", ]
  expect_setequal(z$row, c("top30_2025", "top30_2026", paste0("top30_", DW), paste0("change_pct_", DW, "_vs_2025"),
                           "change_pct_2026_vs_2025"))
  expect_equal(z$doolittle[z$row == "top30_2025"], 0.704)
  expect_equal(z$doolittle[z$row == paste0("top30_", DW)], 0.565)
  expect_equal(z$point[z$row == paste0("change_pct_", DW, "_vs_2025")],
               (z$point[z$row == paste0("top30_", DW)] / z$point[z$row == "top30_2025"] - 1) * 100, tolerance = TOL)
  w <- rd(tabf("catcher_seasons"))
  w <- w[w$window == DW, ]
  expect_true(nrow(w) > 0 && all(w$season == 2026) && all(as.Date(w$through_date) <= as.Date("2026-05-18")))
})

test_that("CH1-A11 is measured on 2022-2024 against Savant rv_tot and its verdict follows 0.85", {
  va <- rd(pubf("validity"))
  g <- va[va$gates, ]
  expect_equal(nrow(g), 1L)
  expect_identical(c(g$scope, g$value_type), c("pooled_2022_2024", "cnt"))
  prose <- paste(readLines(PROSE), collapse = "\n")
  if (SYNTHETIC) {
    expect_true(is.na(g$pearson_r))
  } else {
    pr <- rd(tabf("validity_pairs"))
    expect_true(all(pr$season %in% 2022:2024) && nrow(pr) == g$n)
    expect_equal(g$pearson_r, stats::cor(pr$savant_rv_tot, pr$runs_cnt), tolerance = TOL)
    expect_identical(g$verdict, if (g$pearson_r >= 0.85) "framing primary" else "framing demoted to secondary")
    if (g$pearson_r < 0.85) {
      expect_true(grepl("demoted to secondary", prose, fixed = TRUE))
      dev <- paste(readLines(file.path(ROOT, "docs", "DEVIATIONS.md")), collapse = "\n")
      expect_true(grepl("W3.19", dev, fixed = TRUE) && grepl("CH1-A11", dev, fixed = TRUE))
    } else {
      expect_true(grepl("**Primary result.**", prose, fixed = TRUE))
    }
  }
})

test_that("every number in the prose is registered and re-derives from its source row", {
  txt <- paste(readLines(PROSE), collapse = "\n")
  expect_false(grepl("?", txt, fixed = TRUE))
  expect_false(grepl("attributable|caused by|because of ABS|due to ABS|effect of ABS", txt, ignore.case = TRUE))
  pn <- rd(tabf("prose_numbers"))
  consts <- c("SOP W3.19" = NA, "R/ch1/30_framing.R TANGO_TOL" = 0.010, "R/lib/ch1_fits.R N_DRAWS" = NA)
  for (i in seq_len(nrow(pn))) {
    r <- pn[i, ]
    expect_true(grepl(r$text, txt, fixed = TRUE), info = r$text)
    expect_identical(paste0(formatC(r$value, format = "f", digits = r$digits, big.mark = if (r$digits == 0) "," else ""),
                            ifelse(is.na(r$suffix), "", r$suffix)), r$text)
    if (r$source %in% names(consts)) {
      if (r$source == "SOP W3.19") expect_true(r$value %in% c(0.85, 0.034, -0.042, 0.125, 100), info = r$text)
      if (r$source == "R/lib/ch1_fits.R N_DRAWS" && !SYNTHETIC) expect_equal(r$value, 1000)
      next
    }
    src <- rd(file.path(OUT, sub("^out/", "", r$source)))
    kv <- if (is.numeric(src[[r$key_col]])) as.numeric(r$key) else as.character(r$key)
    j <- which(src[[r$key_col]] == kv)
    expect_equal(length(j), 1L, info = paste(r$source, r$key))
    expect_equal(src[[r$column]][j], r$value, tolerance = 1e-12, info = paste(r$source, r$key, r$column))
  }
  s <- gsub("`[^`]*`", "", txt)
  s <- gsub("\\b\\d{4}-\\d{2}-\\d{2}\\b", "", s, perl = TRUE)
  s <- gsub("\\b[A-Za-z]+[A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)+", "", s, perl = TRUE)
  s <- gsub("\\b[A-Z]+[0-9]+\\b|\\b(?:19|20)\\d{2}\\b|95%", "", s, perl = TRUE)
  tok <- regmatches(s, gregexpr("-?\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?%?|-?\\d+(?:\\.\\d+)?%?", s, perl = TRUE))[[1]]
  expect_true(length(tok) > 20)
  expect_true(all(tok %in% pn$text), info = paste(setdiff(tok, pn$text), collapse = " "))
})

test_that("the prose passes the project's prose linter", {
  st <- suppressWarnings(system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python",
                                         shQuote(file.path(ROOT, "quality", "prose_lint.py")), shQuote(PROSE)),
                                 stdout = TRUE, stderr = TRUE))
  expect_true(is.null(attr(st, "status")) || attr(st, "status") == 0L, info = paste(st, collapse = "\n"))
  expect_true(any(grepl("0 violation", st)), info = paste(st, collapse = "\n"))
})

test_that("the surface-check arms ran on the W3.14 fits", {
  skip_if(SYNTHETIC, "a synthetic tree has no W3.14 surfaces")
  ar <- rd(tabf("arms"))
  expect_true(all(c("band_framing_surface", "band_surface_main", "p1_framing_surface", "p1_surface_abs_cohort") %in% ar$arm))
  expect_true(all(is.finite(ar$cor_with_compared[ar$period == "pooled"])))
})

test_that("the receipt names the commit and hashes every output as it is on disk", {
  rc <- jsonlite::fromJSON(file.path(OUT, "models", "ch1_W3_19", "provenance.json"), simplifyVector = FALSE)
  expect_identical(rc$step, "W3.19")
  expect_equal(rc$seed, 20260922)
  expect_identical(isTRUE(rc$synthetic), SYNTHETIC)
  if (!SYNTHETIC) expect_true(grepl("^[0-9a-f]{40}$", rc$git_sha))
  for (f in names(rc$outputs)) {
    path <- if (startsWith(f, "out/")) file.path(OUT, sub("^out/", "", f)) else f
    h <- paste(sprintf("%02x", as.integer(openssl::sha256(file(path)))), collapse = "")
    expect_identical(h, rc$outputs[[f]], info = f)
  }
})

test_that("the exports keep the W2.21 grain and the script opens no network connection", {
  for (f in c(list.files(TAB, "^framing_.*\\.csv$", full.names = TRUE), list.files(PUB, "^ch1_framing_.*\\.csv$", full.names = TRUE))) {
    h <- names(rd(f))
    expect_false("game_pk" %in% h && any(c("pitch_number", "pitch_slot") %in% h), info = f)
    expect_true(length(readLines(f)) - 1L <= 50000L, info = f)
  }
  # The project's own request linter (SOP section 0.5 rule 2) over the repository; no finding may name
  # this step's script. Other paths' findings belong to their owners and are not this test's to judge.
  lh <- suppressWarnings(system2("sh", shQuote(file.path(ROOT, "ops", "lint_http.sh")), stdout = TRUE, stderr = TRUE))
  expect_false(any(grepl("R/ch1/30_framing.R", lh, fixed = TRUE)), info = paste(lh, collapse = "\n"))
})
