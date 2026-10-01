# tests/testthat/test-ch1-aaa.R - SOP W3.20, the AAA arm and the level difference-in-differences.
#
#   Rscript -e 'testthat::test_dir("tests/testthat", filter = "ch1-aaa", stop_on_failure = TRUE)'
#
# The test re-reads what R/ch1/40_aaa_arm.R wrote and refits nothing. It checks the SOP's clauses
# one by one: the three uses in descending strength and in that order (the machine-drift placebo,
# the within-week alternation, the level DiD); the within-week frame, and the DiD series in the
# changeover season, strictly before the D-57 changeover date read from the rule-version table
# out/tables/aaa_format.csv and never written in the script (DT-29's DiD-frame clause); "The DiD is
# a supporting arm, not the identification." in every artifact; the parallel-trends assumption
# stated explicitly and called strong, with its four named differences; the pre-trend rule applied
# as written; the DiD as an estimate with its own 95% interval; P3's two one-sided tests re-derived;
# no causal wording, since placebo P1 failed; the seal; and every two-decimal number of the prose
# traced to a cell of the four tables.

find_root <- function() {
  r <- Sys.getenv("ABSUMP_ROOT", "")
  if (nzchar(r)) return(normalizePath(r))
  d <- normalizePath(getwd())
  repeat {
    if (file.exists(file.path(d, "R", "ch1", "40_aaa_arm.R"))) return(d)
    p <- dirname(d)
    if (identical(p, d)) stop("cannot find the repository root above ", getwd())
    d <- p
  }
}
ROOT <- find_root()
OUT <- file.path(ROOT, "out")
SCRIPT <- file.path(ROOT, "R", "ch1", "40_aaa_arm.R")
THIS <- file.path(ROOT, "tests", "testthat", "test-ch1-aaa.R")
F_PLACEBO <- file.path(OUT, "tables", "aaa_placebo.csv")
F_WEEK <- file.path(OUT, "ch1", "tab", "aaa_withinweek.csv")
F_PRETREND <- file.path(OUT, "ch1", "tab", "aaa_pretrend.csv")
F_DID <- file.path(OUT, "ch1", "tab", "aaa_did.csv")
F_PROSE <- file.path(OUT, "ch1", "prose", "aaa.md")
F_FORMAT <- file.path(OUT, "tables", "aaa_format.csv")
F_T5 <- file.path(OUT, "ch1", "tab", "T5_placebos.csv")
rd <- function(f) utils::read.csv(f, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character")
num <- function(x) suppressWarnings(as.numeric(x))
txt_of <- function(f) paste(readLines(f, warn = FALSE), collapse = "\n")
ROLE <- "The DiD is a supporting arm, not the identification."
CAUSAL <- paste0("\\b(attributable|attributes?|caused by|causes|causal effect|because of|due to|effect of|",
                 "effects of|impact|led to|drove|driven by|resulted in|results in|treatment effect)\\b")
TOL <- 2e-6   # the tables print six decimals

changeover <- function() {
  f <- rd(F_FORMAT)
  r <- f[f$level == "aaa" & f$rule_version == "format_challenge_tue_thu", ]
  stopifnot(nrow(r) == 1L)
  list(date = as.Date(r$changeover_date), season = as.integer(r$season))
}
seal_start <- function() {
  l <- grep("^seal_start_date:", readLines(file.path(ROOT, "config", "seal.yml")), value = TRUE)
  as.Date(gsub('[" ]', "", sub("^seal_start_date:", "", l)))
}
# "2023 2023-04-28 to 2023-05-14; 2024 2024-04-28 to 2024-05-18" -> season, first, last
date_spans <- function(x) {
  m <- regmatches(x, gregexpr("(\\d{4}) (\\d{4}-\\d{2}-\\d{2}) to (\\d{4}-\\d{2}-\\d{2})", x))[[1]]
  do.call(rbind, lapply(m, function(s) {
    p <- strsplit(s, " ")[[1]]
    data.frame(season = as.integer(p[1]), first = as.Date(p[2]), last = as.Date(p[4]))
  }))
}

test_that("every output of the step is on disk", {
  for (f in c(SCRIPT, F_PLACEBO, F_WEEK, F_PRETREND, F_DID, F_PROSE, F_FORMAT, F_T5)) expect_true(file.exists(f), info = f)
})

test_that("the changeover date is read from the rule-version table, never written in the script", {
  co <- changeover()
  expect_false(is.na(co$date))
  expect_identical(as.integer(format(co$date, "%Y")), co$season)
  s <- txt_of(SCRIPT)
  expect_false(grepl(format(co$date), s, fixed = TRUE))
  expect_false(grepl(format(co$date, "%Y%m%d"), s, fixed = TRUE))
  expect_true(grepl('FORMAT_ROW      <- "format_challenge_tue_thu"', s, fixed = TRUE))
  expect_true(grepl('file.path(ROOT, "out", "tables", "aaa_format.csv")', s, fixed = TRUE))
  w <- rd(F_WEEK)
  expect_true(all(w$changeover_date == format(co$date)))
  expect_true(all(w$changeover_source == "out/tables/aaa_format.csv, rule_version format_challenge_tue_thu"))
  expect_true(grepl(sprintf("strictly before the changeover date, %s.", format(co$date)), txt_of(F_PROSE), fixed = TRUE))
})

test_that("DT-29: the within-week frame and the DiD series hold no date on or after the changeover", {
  co <- changeover()
  w <- rd(F_WEEK)
  expect_true(nrow(w) >= 1L)
  expect_true(all(as.Date(w$frame_last_date) < co$date))
  expect_true(all(as.Date(w$frame_first_date) <= as.Date(w$frame_last_date)))
  for (f in c(F_PRETREND, F_DID)) {
    t <- rd(f)
    t <- t[nzchar(t$aaa_dates), ]
    expect_true(nrow(t) > 0L, info = f)
    for (x in t$aaa_dates) {
      sp <- date_spans(x)
      expect_equal(nrow(sp), 2L, info = x)
      expect_true(all(sp$first <= sp$last), info = x)
      expect_true(all(format(sp$first, "%Y") == sp$season & format(sp$last, "%Y") == sp$season), info = x)
      cs <- sp[sp$season == co$season, ]
      if (nrow(cs)) expect_true(all(cs$last < co$date), info = paste(basename(f), x))
    }
  }
})

test_that("the three uses are reported in descending strength and in the SOP's order", {
  p <- txt_of(F_PROSE)
  h <- c("## 1. The machine-drift placebo", "## 2. The within-week alternation", "## 3. The level difference-in-differences")
  at <- vapply(h, function(x) regexpr(x, p, fixed = TRUE)[1], 0)
  expect_true(all(at > 0))
  expect_true(all(diff(at) > 0))
  expect_true(grepl(paste("The arm has three uses, reported in descending strength. First comes the machine-drift placebo.",
                          "Second comes the within-week alternation. Third comes the level difference-in-differences"),
                    p, fixed = TRUE))
  expect_true(all(grepl("^Use 1 of 3, the strongest: the machine-drift placebo\\.", rd(F_PLACEBO)$note)))
  expect_true(all(grepl("^Use 2 of 3: the within-week alternation\\.", rd(F_WEEK)$note)))
})

test_that("The DiD is a supporting arm, not the identification, in every artifact", {
  for (f in c(F_PROSE, SCRIPT, THIS)) expect_true(grepl(ROLE, txt_of(f), fixed = TRUE), info = f)
  expect_true(grepl(paste0("**", ROLE, "**"), txt_of(F_PROSE), fixed = TRUE))
  expect_true(all(rd(F_DID)$role == ROLE))
  expect_true(all(rd(F_PRETREND)$role == ROLE))
  expect_true(all(grepl(ROLE, rd(F_WEEK)$note, fixed = TRUE)))
  expect_true(all(grepl(ROLE, rd(F_PLACEBO)$note, fixed = TRUE)))
})

test_that("parallel trends is stated explicitly, and stated as strong, with its four differences", {
  need <- c("umpire populations", "parks", "Hawk-Eye installations", "machine-set zone in AAA")
  for (f in c(F_DID, F_PRETREND)) {
    pt <- unique(rd(f)$parallel_trends)
    expect_length(pt, 1L)
    expect_true(startsWith(pt, "Parallel trends, stated explicitly:"), info = f)
    expect_true(grepl("This assumption is strong", pt, fixed = TRUE), info = f)
    for (n in need) expect_true(grepl(n, pt, fixed = TRUE), info = paste(f, n))
  }
  p <- txt_of(F_PROSE)
  expect_true(grepl("**Parallel trends.**", p, fixed = TRUE))
  expect_true(grepl("This assumption is strong.", p, fixed = TRUE))
  for (n in c("umpire populations", "parks", "Hawk-Eye installations", "machine-set")) expect_true(grepl(n, p, fixed = TRUE), info = n)
})

test_that("the pre-trend rule is applied as written: a 95% interval on 2023 to 2024 containing 0, or descriptive", {
  pt <- rd(F_PRETREND)
  expect_true(all(pt$test == "pre-trend" & pt$contrast == "2023_to_2024"))
  expect_true(all(grepl("must have a 95% interval containing 0, or the DiD is reported as descriptive", pt$rule, fixed = TRUE)))
  lo <- num(pt$lo95); hi <- num(pt$hi95); pnt <- num(pt$point)
  expect_true(all(is.finite(lo) & is.finite(hi) & lo < hi))
  cz <- lo <= 0 & hi >= 0
  expect_identical(pt$contains_zero, ifelse(cz, "TRUE", "FALSE"))
  expect_identical(pt$verdict, ifelse(cz, "pass", "fail"))
  expect_identical(pt$consequence, ifelse(cz, "interval contains 0: the pre-trend test passes",
                                          "interval excludes 0: the DiD is reported as descriptive"))
  expect_equal(pnt, num(pt$mlb_change) - num(pt$aaa_change), tolerance = TOL)
  expect_true(all(num(pt$n_draws) >= 990))
  prim <- pt[pt$primary == "TRUE", ]
  expect_equal(nrow(prim), 1L)
  expect_identical(c(prim$estimand, prim$mlb_estimator, prim$aaa_window), c("area_sqin", "binned", "window"))
  expect_setequal(unique(pt$estimand), c("top_in", "bot_in", "half_width_in", "area_sqin"))
})

test_that("the DiD is an estimate with its own 95% interval, read as the pre-trend and P1 require", {
  d <- rd(F_DID)
  pt <- rd(F_PRETREND)
  est <- d[d$contrast == "2024_to_2025", ]
  expect_equal(nrow(est), nrow(pt))
  expect_true(all(est$status == "estimated"))
  lo <- num(est$lo95); hi <- num(est$hi95); pnt <- num(est$point)
  expect_true(all(is.finite(pnt) & is.finite(lo) & is.finite(hi) & lo < hi))
  expect_true(all(num(est$n_draws) >= 990))
  expect_equal(pnt, num(est$mlb_change) - num(est$aaa_change), tolerance = TOL)
  k <- match(paste(est$estimand, est$mlb_estimator, est$aaa_window), paste(pt$estimand, pt$mlb_estimator, pt$aaa_window))
  expect_false(anyNA(k))
  expect_equal(num(est$pretrend_point), num(pt$point[k]), tolerance = TOL)
  expect_equal(num(est$pretrend_lo95), num(pt$lo95[k]), tolerance = TOL)
  expect_equal(num(est$pretrend_hi95), num(pt$hi95[k]), tolerance = TOL)
  expect_identical(est$pretrend_verdict, pt$verdict[k])
  t5 <- rd(F_T5)
  p1_failed <- any(t5$placebo_verdict[t5$placebo == "P1"] == "fail")
  expect_true(p1_failed)
  want <- vapply(est$pretrend_verdict, function(v) {
    r <- c(if (p1_failed) "placebo P1 failed", if (v == "fail") "the pre-trend 95% interval excludes 0")
    if (length(r) == 0) "estimate: the pre-trend 95% interval contains 0" else paste0("descriptive: ", paste(r, collapse = "; "))
  }, "")
  expect_identical(unname(est$reading), unname(want))
  prim <- est[est$primary == "TRUE", ]
  expect_equal(nrow(prim), 1L)
  expect_identical(c(prim$estimand, prim$mlb_estimator, prim$aaa_window), c("area_sqin", "binned", "window"))
  nx <- d[d$contrast == "2025_to_2026", ]
  expect_true(nrow(nx) > 0 && all(startsWith(nx$status, "not estimated")) && all(!nzchar(nx$point)))
})

test_that("P3, the machine-drift placebo, re-derives: rule-net area and two one-sided tests at +/-3 sq in", {
  p <- rd(F_PLACEBO)
  s <- p[p$row_type == "season" & p$verdict == "measured", ]
  expect_true(nrow(s) >= 2L)
  expect_equal(num(s$estimate), num(s$contour_area) - num(s$rule_area), tolerance = TOL)
  expect_true(all(num(s$n_boot) == 1000))
  ch <- p[p$row_type == "change", ]
  expect_equal(nrow(ch), 2L)
  for (i in seq_len(nrow(ch))) {
    r <- ch[i, ]
    if (r$verdict == "not evaluable") {
      expect_false(nzchar(r$estimate))
      next
    }
    a <- s[s$season_from == r$season_from, ]; b <- s[s$season_from == r$season_to, ]
    expect_equal(num(r$estimate), num(b$estimate) - num(a$estimate), tolerance = TOL)
    expect_equal(num(r$margin_sqin), 3)
    ok <- num(r$lo90) > -3 && num(r$hi90) < 3
    expect_identical(r$verdict, if (ok) "pass" else "fail")
    expect_true(num(r$lo95) <= num(r$lo90) && num(r$hi90) <= num(r$hi95))
  }
})

test_that("the within-week alternation is the same umpire's own season with week fixed effects", {
  w <- rd(F_WEEK)
  expect_true(all(w$use == "within-week alternation"))
  expect_true(all(grepl("umpire x season", w$model, fixed = TRUE) & grepl("+ week", w$model, fixed = TRUE)))
  pooled <- w[w$season_scope == "pooled" & w$edge_scope == "all", ]
  expect_equal(nrow(pooled), 1L)
  n <- function(x) as.integer(x)
  expect_equal(n(w$n_pitches), n(w$n_pitches_challenge) + n(w$n_pitches_full_abs))
  expect_equal(sum(n(w$n_pitches[w$season_scope != "pooled"])), n(pooled$n_pitches))
  expect_equal(sum(n(w$n_pitches[w$season_scope == "pooled" & w$edge_scope != "all"])), n(pooled$n_pitches))
  ok <- is.finite(num(w$estimate))
  expect_true(all(ok))
  expect_true(all(num(w$lo95) < num(w$estimate) & num(w$estimate) < num(w$hi95)))
  expect_true(all(n(w$n_games_challenge) > 0 & n(w$n_games_full_abs) > 0 & n(w$n_umpires) > 1))
})

test_that("no causal wording anywhere, since placebo P1 failed", {
  p <- txt_of(F_PROSE)
  expect_false(grepl(CAUSAL, p, ignore.case = TRUE, perl = TRUE))
  expect_true(grepl("Placebo P1 failed (T5). Every contrast here is therefore descriptive and names no cause.", p, fixed = TRUE))
  for (f in c(F_PLACEBO, F_WEEK, F_PRETREND, F_DID)) {
    t <- rd(f)
    chr <- unlist(t[, vapply(t, function(v) any(grepl("[A-Za-z]", v)), TRUE), drop = FALSE])
    expect_false(any(grepl(CAUSAL, chr, ignore.case = TRUE, perl = TRUE)), info = f)
  }
})

test_that("the seal: no output carries a date on or after the seal start", {
  seal <- seal_start()
  expect_false(is.na(seal))
  for (f in c(F_PLACEBO, F_WEEK, F_PRETREND, F_DID, F_PROSE)) {
    t <- txt_of(f)
    ds <- as.Date(unique(regmatches(t, gregexpr("\\b20\\d{2}-\\d{2}-\\d{2}\\b", t))[[1]]))
    expect_true(all(ds < seal), info = f)
  }
  s <- txt_of(SCRIPT)
  expect_true(grepl("AAA_SEASONS     <- 2023:2025", s, fixed = TRUE))
})

test_that("every two-decimal number of the prose traces to a cell of the four tables", {
  p <- txt_of(F_PROSE)
  cells <- unlist(lapply(c(F_PLACEBO, F_WEEK, F_PRETREND, F_DID), function(f) {
    t <- rd(f)
    v <- num(unlist(t))
    v <- v[is.finite(v)]
    c(sprintf("%+.2f", v), sprintf("%.2f", v))
  }))
  # a step id such as W3.20 is not a number of the prose
  found <- regmatches(p, gregexpr("(?<![A-Za-z0-9.])[+-]?\\d+\\.\\d{2}\\b", p, perl = TRUE))[[1]]
  expect_true(length(found) >= 20L)
  miss <- setdiff(found, cells)
  expect_identical(miss, character(0))
  # the headline sentences, rebuilt from their rows
  ci <- function(pt, lo, hi, unit) sprintf("%+.2f %s (95%% CI %+.2f to %+.2f)", num(pt), unit, num(lo), num(hi))
  pr <- rd(F_PRETREND); pr <- pr[pr$primary == "TRUE", ]
  expect_true(grepl(sprintf("On area the AAA-versus-MLB 2023 to 2024 coefficient is %s.", ci(pr$point, pr$lo95, pr$hi95, "sq in")),
                    p, fixed = TRUE))
  expect_true(grepl(if (pr$contains_zero == "TRUE") "The interval contains 0, so the pre-trend test passes."
                    else "The interval excludes 0, so the DiD is reported as descriptive.", p, fixed = TRUE))
  dd <- rd(F_DID); dd <- dd[dd$primary == "TRUE", ]
  expect_true(grepl(sprintf("The DiD, MLB's change minus AAA's, is %s.", ci(dd$point, dd$lo95, dd$hi95, "sq in")), p, fixed = TRUE))
  w <- rd(F_WEEK); w <- w[w$season_scope == "pooled" & w$edge_scope == "all", ]
  expect_true(grepl(sprintf("the full-ABS rate is %s.", ci(w$estimate, w$lo95, w$hi95, "pp")), p, fixed = TRUE))
  pl <- rd(F_PLACEBO); pl <- pl[pl$row_type == "change" & pl$verdict != "not evaluable", ][1, ]
  expect_true(grepl(sprintf("it changes by %+.2f sq in (90%% CI %+.2f to %+.2f).", num(pl$estimate), num(pl$lo90), num(pl$hi90)),
                    p, fixed = TRUE))
})

test_that("the script opens no network and reads only the tables and lake it names", {
  s <- txt_of(SCRIPT)
  expect_false(grepl("https?://|download\\.file|curl|httr|url\\(", s))
  expect_true(grepl("It makes no request of any host.", s, fixed = TRUE))
})
