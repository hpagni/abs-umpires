# tests/testthat/test-ch1-figures.R - SOP W3.24, the Chapter 1 figures F1 to F8, tables T1 to T9, docs/ch1.md.
#
#   Rscript -e 'testthat::test_dir("tests/testthat", filter = "ch1-figures", stop_on_failure = TRUE)'
#   W324_OUT=<root> reads <root> instead of out/; W324_DOCS=<path> reads that file instead of docs/ch1.md;
#   W324_SKIP_RERUN=1 skips the determinism re-run (for a quick local read only; the verify command never sets it).
#
# The test re-reads what `make figures` and `make tables` wrote and refits nothing. It checks the SOP
# section 9.1 clause for figures and tables: a sidecar per figure, 8 cm width, a grayscale-safe data
# palette, alt text, every caption and alt-text number present in the sidecar, and determinism (a
# second render into a temporary directory reproduces every sidecar and table CSV to 1e-8). It
# re-derives the figure facts from the step outputs they come from (T3, T4, T5, T6, W3.19's catcher
# seasons, W3.14's receipt), checks that F4 names no umpire (D-21), that T4 prints the share only
# under D-59's rule and carries CH1-A14's panel difference, that every T9 citation resolves in
# docs/prior-art.md, and that docs/ch1.md names every figure and table, folds framing.md verbatim and
# traces its numbers. It also holds the acceptance verifier's gaps closed (DEV-85): annex 8.7's
# caveat beside every top-edge and half-width row (R3), T8 from W3.22's grid with CH1-A9's verdict (R4,
# R5), F2b the dz-by-pitch-type figure (CH1-A13), the balanced-panel rows in headline.csv (CH1-A14),
# F4's local sidecar (D-21) and T9's Doolittle default. The last test fails while any figure or table
# is a placeholder: W3.24 is not done until F5 (W3.20) and F8 (W3.23) are real; T8 landed with W3.22.

find_root <- function() {
  r <- Sys.getenv("ABSUMP_ROOT", "")
  if (nzchar(r)) return(normalizePath(r))
  d <- normalizePath(getwd())
  repeat {
    if (file.exists(file.path(d, "R", "ch1", "70_figures.R"))) return(d)
    p <- dirname(d)
    if (identical(p, d)) stop("cannot find the repository root above ", getwd())
    d <- p
  }
}
ROOT <- find_root()
OUT <- Sys.getenv("W324_OUT", file.path(ROOT, "out"))
DOCS <- Sys.getenv("W324_DOCS", file.path(ROOT, "docs", "ch1.md"))
TAB <- file.path(OUT, "ch1", "tab")
PUB <- file.path(OUT, "tables")
FIGD <- file.path(OUT, "figures")
rd <- function(f) utils::read.csv(f, stringsAsFactors = FALSE, check.names = FALSE)
FIG_IDS <- c("F1", "F2", "F2b", sprintf("F%d", 3:8))  # F2b: the dz-by-pitch-type figure (CH1-A13)
TAB_IDS <- sprintf("T%d", 1:9)
BLOCKED <- c(F5 = "W3.20", F8 = "W3.23", T8 = "W3.22")
fman <- rd(file.path(FIGD, "figures_manifest.csv"))
tman <- rd(file.path(PUB, "tables_manifest.csv"))
side <- function(id) rd(file.path(PUB, paste0(id, "_data.csv")))
tabf <- function(id) file.path(OUT, sub("^out/", "", tman$csv[tman$table_id == id]))

# The tracer, written apart from the scripts' own: a number printed with k decimals traces when some
# value of the source rounds to it at k decimals (either sign when printed unsigned). Ids glued to
# letters or hyphens, years 1900 to 2039, ISO date parts and "section N" references are labels.
num_tokens <- function(txt) {
  txt <- gsub("−", "-", txt, fixed = TRUE)
  txt <- gsub("`[^`]*`", " ", txt)
  txt <- gsub("\\]\\([^)]*\\)", "] ", txt)
  txt <- gsub("(sections?|§) ?[0-9][0-9.]*( and [0-9][0-9.]*)?", " ", txt, perl = TRUE)
  m <- gregexpr("(?<![A-Za-z0-9_.\\-])-?[0-9][0-9,]*(\\.[0-9]+)?(?![A-Za-z0-9_])", txt, perl = TRUE)
  tok <- sub(",+$", "", unlist(regmatches(txt, m)))
  tok <- tok[nzchar(tok)]
  b <- gsub(",", "", tok)
  tok[!(grepl("^[0-9]{4}$", b) & as.numeric(b) >= 1900 & as.numeric(b) <= 2039)]
}
pool_of <- function(dfs) {
  v <- numeric(0)
  for (d in dfs) for (c in d) {
    if (is.numeric(c)) v <- c(v, c[is.finite(c)])
    else if (is.character(c)) v <- c(v, suppressWarnings(as.numeric(gsub(",", "", num_tokens(paste(c[!is.na(c)], collapse = " "))))))
  }
  v[is.finite(v)]
}
untraced <- function(txt, pool) {
  bad <- character(0)
  for (t in num_tokens(txt)) {
    b <- gsub(",", "", t)
    k <- if (grepl(".", b, fixed = TRUE)) nchar(sub("^[^.]*\\.", "", b)) else 0L
    v <- as.numeric(b)
    ok <- if (startsWith(b, "-")) any(abs(round(pool, k) - v) < 1e-9) else any(abs(round(abs(pool), k) - v) < 1e-9)
    if (!ok) bad <- c(bad, t)
  }
  unique(bad)
}

test_that("the manifests list F1 to F8 and T1 to T9, and only the blocked ids are placeholders", {
  expect_identical(fman$figure_id, FIG_IDS)
  expect_identical(tman$table_id, TAB_IDS)
  ph <- c(fman$figure_id[fman$status == "PLACEHOLDER"], tman$table_id[tman$status == "PLACEHOLDER"])
  expect_true(all(ph %in% names(BLOCKED)), info = paste(ph, collapse = ", "))
  expect_true(all(c(fman$status, tman$status) %in% c("built", "PLACEHOLDER")))
  for (id in ph) {
    by <- c(fman$blocked_by[fman$figure_id == id], tman$blocked_by[tman$table_id == id])
    expect_identical(by, BLOCKED[[id]], info = id)
  }
})

test_that("every figure has a PNG, a PDF, a sidecar, alt text and a caption, at 8 cm width", {
  for (i in seq_len(nrow(fman))) {
    m <- fman[i, ]
    for (f in c(m$png, m$pdf, m$sidecar)) {
      p <- file.path(OUT, sub("^out/", "", f))
      expect_true(file.exists(p) && file.size(p) > 0, info = p)
    }
    expect_identical(m$sidecar, sprintf("out/tables/%s_data.csv", m$figure_id))
    expect_equal(m$width_cm, 8)
    expect_gt(nchar(m$alt), 40)
    expect_gt(nchar(m$caption), 40)
    sha <- paste(sprintf("%02x", as.integer(openssl::sha256(file(file.path(PUB, paste0(m$figure_id, "_data.csv")))))), collapse = "")
    expect_identical(sha, m$sidecar_sha256, info = m$figure_id)
    expect_equal(nrow(side(m$figure_id)), m$sidecar_rows, info = m$figure_id)
  }
})

test_that("grayscale: every multi-colour data palette keeps an L* gap of at least 15", {
  for (i in seq_len(nrow(fman))) {
    pal <- unique(strsplit(fman$palette[i], ";", fixed = TRUE)[[1]])
    pal <- pal[nzchar(pal)]
    if (length(pal) < 2L) next
    l <- sort(farver::convert_colour(t(grDevices::col2rgb(pal)), "rgb", "lab")[, "l"])
    expect_gte(min(diff(l)), 15)
    expect_equal(min(diff(l)), fman$palette_min_lstar_gap[i], tolerance = 1e-6)
  }
})

test_that("every number in a caption or its alt text is in that figure's sidecar", {
  for (i in seq_len(nrow(fman))) {
    s <- side(fman$figure_id[i])
    bad <- untraced(paste(fman$caption[i], fman$alt[i]), pool_of(list(s)))
    expect_identical(bad, character(0), info = fman$figure_id[i])
  }
})

test_that("F1: three regimes, complete ray bands, the ABS rectangle, and edges equal to T3", {
  s <- side("F1")
  r <- s[s$element == "ray", ]
  expect_setequal(unique(r$season), 2024:2026)
  expect_equal(as.vector(table(r$season)), rep(120L, 3))
  expect_true(all(r$lo95 <= r$median & r$median <= r$hi95))
  expect_true(all(r$n >= 990))
  expect_lt(max(abs(r$value - r$r_contour)), 0.05)
  rect <- s[s$element == "abs_rectangle", ]
  expect_equal(range(rect$x), c(-8.5, 8.5))
  expect_equal(range(rect$y), c(0.27 * 72, 0.535 * 72))
  t3 <- rd(file.path(TAB, "T3_estimands.csv"))
  e <- s[s$element == "edge", ]
  m <- t3[t3$fit == "main", ]
  ref <- m$point[match(paste(e$season, e$key), paste(m$season, m$estimand))]
  expect_equal(e$value, ref, tolerance = 1e-12)
})

test_that("F2: the identity holds, and the plane bar is W3.17's, per edge and outside the sum", {
  s <- side("F2")
  b <- s[s$element == "bar", ]
  pc <- rd(file.path(TAB, "T4_plane_component.csv"))
  for (e in unique(b$estimand)) {
    x <- b[b$estimand == e, ]
    v <- setNames(x$value, x$key)
    expect_lt(abs(v[["trend_2g"]] + v[["delta_buffer"]] + v[["delta_abs"]] - v[["delta_total"]]), 1e-9)
    expect_false(as.logical(x$in_sum[x$key == "plane"]))
    expect_equal(v[["plane"]], pc$point[pc$estimand == e], tolerance = 1e-12)
  }
  expect_setequal(unique(b$estimand), c("top_in", "bot_in", "half_width_in", "area_sqin"))
})

test_that("F3: 2024 is the reference, the 2023 to 2024 placebo boundary is marked, P1 is T5's", {
  s <- side("F3")
  x <- s[s$element == "season", ]
  expect_true(all(x$value[x$season == 2024] == 0))
  bd <- s[s$element == "boundary", ]
  expect_equal(bd$x[bd$key == "P1 placebo"], 2023.5)
  t5 <- rd(file.path(TAB, "T5_placebos.csv"))
  p1 <- s[s$element == "p1", ]
  expect_equal(p1$value, t5$estimate[t5$placebo == "P1"], tolerance = 1e-12)
  expect_identical(p1$note, t5$verdict[t5$placebo == "P1"])
})

test_that("F4: no umpire is identified (D-21), and the tau inset is T6's sop posterior", {
  s <- side("F4")
  expect_false(any(grepl("umpire|id$|name", names(s), ignore.case = TRUE)))
  u <- s[s$element == "umpire", ]
  expect_identical(sort(as.integer(u$key)), seq_len(nrow(u)))
  expect_true(all(diff(u$value[order(as.integer(u$key))]) >= 0))
  eb <- rd(file.path(TAB, "umpire_eb.csv"))
  expect_equal(eb$point[eb$quantity == "per_umpire_table_published"], 0)
  expect_equal(nrow(u), eb$point[eb$quantity == "n_umpires_2025_and_2026"])
  t6 <- rd(file.path(TAB, "T6_heterogeneity.csv"))
  tau <- s[s$element == "tau", ]
  expect_equal(tau$value[tau$key == "tau_abs"], t6$median[t6$fit == "sop" & t6$quantity == "tau_abs"], tolerance = 1e-6)
  expect_equal(tau$value[tau$key == "p_tau_ge_020"], t6$median[t6$fit == "CH1-A6" & t6$quantity == "p_tau_ge_020"])
})

test_that("F6: the catcher-seasons are W3.19's qualified season rows, and the summaries re-derive", {
  s <- side("F6")
  fr <- rd(file.path(TAB, "framing_catcher_seasons.csv"))
  fr <- fr[fr$window == "season" & fr$qualified %in% c(TRUE, "TRUE"), ]
  cs <- s[s$element == "catcher_season", ]
  expect_equal(nrow(cs), nrow(fr))
  sm <- s[s$element == "summary", ]
  for (r in sm$regime) {
    v <- fr$runs_cnt_per100[fr$regime == r]
    expect_equal(sm$n[sm$regime == r], length(v))
    expect_equal(sm$value[sm$regime == r], unname(stats::quantile(v, 0.5, type = 7)), tolerance = 1e-12)
  }
})

test_that("F7 and T7: every fitted pitch once, 32 bins per regime, Wilson intervals re-derived", {
  s <- side("F7")
  b <- s[s$element == "bin", ]
  rec <- jsonlite::fromJSON(file.path(OUT, "models", "surface_main", "provenance.json"))
  expect_equal(sum(b$n), rec$n_rows)
  expect_equal(as.vector(table(b$regime)), rep(32L, 3))
  z <- stats::qnorm(0.975); p <- b$strikes / b$n
  lo <- (p + z^2 / (2 * b$n) - z * sqrt(p * (1 - p) / b$n + z^2 / (4 * b$n^2))) / (1 + z^2 / b$n)
  expect_equal(b$lo95, 100 * lo - b$fitted_pct, tolerance = 1e-9)
  t7 <- rd(tabf("T7"))
  o <- t7[t7$block == "open_in_sample", ]
  expect_equal(o$diff_pp, b$value, tolerance = 1e-12)
  expect_equal(o$n, b$n)
})

test_that("T4: the identity, D-59's share rule, and CH1-A14's panel difference as a number", {
  t4 <- rd(tabf("T4"))
  for (e in unique(t4$estimand)) {
    x <- t4[t4$estimand == e, ]
    v <- function(k) x$point[x$component == k]
    expect_lt(abs(v("delta_buffer") + v("delta_abs") + 2 * v("g") - v("delta_total")), 1e-9)
    sm <- x[x$component == "sum_components", ]
    excl <- sm$lo95 > 0 || sm$hi95 < 0
    sh <- x[x$component == "share_abs", ]
    expect_identical(as.logical(sh$reported), excl)
    if (!excl) expect_true(is.na(sh$point))
    for (k in c("delta_buffer", "delta_abs")) {
      r <- x[x$component == k, ]
      expect_true(is.finite(r$panel_minus_primary))
      expect_equal(r$panel_minus_primary, r$panel_point - r$point, tolerance = 1e-9)
    }
  }
  pl <- t4[t4$component == "plane_mechanical", ]
  expect_setequal(pl$estimand, c("top_in", "bot_in", "half_width_in", "area_sqin"))
})

test_that("T1 reconciles W3.5's counts with the fitted sample", {
  t1 <- rd(tabf("T1"))
  rec <- jsonlite::fromJSON(file.path(OUT, "models", "surface_main", "provenance.json"))
  expect_equal(as.numeric(t1$total[t1$row_id == "F_surface_rows"]), rec$n_rows)
  yc <- paste0("y", 2022:2026)
  expect_equal(as.numeric(t1[t1$row_id == "P0", yc]),
               as.numeric(t1[t1$row_id == "F_p0_loaded", yc]) + as.numeric(t1[t1$row_id == "F_dropped", yc]))
})

test_that("T9: each citation resolves to a section of the prior-art ledger that names the author and prints the number", {
  pa <- readLines(file.path(ROOT, "docs", "prior-art.md"), warn = FALSE)
  sect <- function(num) {
    h <- grep(sprintf("^#+ %s ", gsub(".", "\\.", num, fixed = TRUE)), pa)
    expect_length(h, 1L)
    nxt <- grep("^#{2,3} ", pa)
    end <- min(c(nxt[nxt > h], length(pa) + 1L)) - 1L
    paste(pa[h:end], collapse = " ")
  }
  t9 <- rd(tabf("T9"))
  expect_setequal(unique(t9$source), c("Clemens", "Andrews", "Dwyer", "Doolittle", "METHODS section 8"))
  for (i in seq_len(nrow(t9))) {
    nums <- regmatches(t9$citation[i], gregexpr("[0-9]+\\.[0-9]+", t9$citation[i]))[[1]]
    expect_gt(length(nums), 0)
    txt <- paste(vapply(nums, sect, ""), collapse = " ")
    who <- if (t9$source[i] == "METHODS section 8") "use-it-or-lose-it" else t9$source[i]
    expect_true(grepl(who, txt, fixed = TRUE), info = paste(t9$source[i], t9$citation[i]))
    for (t in num_tokens(t9$published_as_printed[i])) {
      expect_true(grepl(sub("^-", "", t), txt, fixed = TRUE), info = paste(t9$source[i], t))
    }
  }
})

test_that("the T8 builder names sign flips, zero crossings, excluded primaries and unrun cells", {
  e <- new.env()
  old <- getwd()
  on.exit(setwd(old), add = TRUE)
  Sys.setenv(ABSUMP_ROOT = ROOT)
  sys.source(file.path(ROOT, "R", "ch1", "71_tables.R"), envir = e)
  g <- data.frame(cell_id = c("primary", "a", "b", "c"), estimator = "binned", estimand = "area_sqin",
                  component = "delta_abs", is_primary = c(TRUE, FALSE, FALSE, FALSE), status = c("ok", "ok", "ok", "not run"),
                  point = c(-40, -35, 2, NA), lo95 = c(-43, -38, -1, NA), hi95 = c(-37, -32, 5, NA), stringsAsFactors = FALSE)
  bam <- data.frame(estimand = "area_sqin", component = "delta_abs", point = -33.1)
  out <- e$build_t8(g, bam)
  expect_identical(out$flagged, c(TRUE, TRUE, TRUE, TRUE))
  expect_true(out$flag_excludes_bam_primary[1])
  expect_true(out$flag_excludes_primary[2] && !out$flag_excludes_bam_primary[2])
  expect_true(out$flag_sign[3] && out$flag_crosses_zero[3])
  expect_true(out$flag_status[4])
})

test_that("docs/ch1.md names every figure and table, marks each placeholder, folds framing.md, and traces its numbers", {
  expect_true(file.exists(DOCS))
  L <- readLines(DOCS, warn = FALSE, encoding = "UTF-8")
  for (id in c(FIG_IDS, TAB_IDS)) expect_true(any(startsWith(L, sprintf("### %s. ", id))), info = id)
  ph <- c(fman$figure_id[fman$status == "PLACEHOLDER"], tman$table_id[tman$status == "PLACEHOLDER"])
  for (id in ph) {
    expect_true(any(grepl(sprintf("%s, .*placeholder, not a result.*blocked on %s", id, BLOCKED[[id]]), L)), info = id)
  }
  for (id in setdiff(c(FIG_IDS, TAB_IDS), ph)) {
    expect_false(any(grepl(sprintf("^- \\*\\*%s, .*placeholder, not a result", id), L)), info = paste(id, "is built"))
  }
  a <- which(L == "## Catcher framing by regime"); b <- which(L == "## The AAA arm")
  expect_length(a, 1L); expect_length(b, 1L)
  fr <- readLines(file.path(OUT, "ch1", "prose", "framing.md"), warn = FALSE, encoding = "UTF-8")
  fr <- fr[-1]; while (!nzchar(trimws(fr[1]))) fr <- fr[-1]
  fr <- sub("^(#+) ", "\\1# ", fr)
  body <- L[(a + 1L):(b - 1L)]
  expect_true(length(fr) > 0 && all(fr %in% body))
  k <- match(fr[1], body)
  expect_identical(body[k:(k + length(fr) - 1L)], fr)
  aaa <- file.path(OUT, "ch1", "prose", "aaa.md")
  if (!file.exists(aaa)) expect_true(any(grepl("^Not written\\. W3\\.20 is blocked", L[b:length(L)])))
  src <- c(list.files(PUB, pattern = "^F[1-8]b?_data\\.csv$", full.names = TRUE), file.path(OUT, sub("^out/", "", tman$csv)),
           file.path(FIGD, "figures_manifest.csv"), file.path(PUB, "tables_manifest.csv"))
  pool <- pool_of(lapply(src, rd))
  rest <- L[-((a + 1L):(b - 1L))]
  bad <- untraced(paste(rest, collapse = "\n"), pool)
  expect_identical(bad, character(0))
})

test_that("annex 8.7: the published T4 keeps W3.16's disclosure and undersmooth columns, and every top-edge row carries the caveat", {
  up <- rd(file.path(TAB, "T4_decomposition.csv")); up <- up[up$fit == "main", ]
  t4 <- rd(tabf("T4"))
  cols <- c("undersmooth_point", "undersmooth_lo95", "undersmooth_hi95", "undersmooth_minus_primary", "recovery_disclosure")
  expect_true(all(cols %in% names(t4)), info = paste(setdiff(cols, names(t4)), collapse = ", "))
  txt <- function(e) unique(up$recovery_disclosure[up$estimand == e & !is.na(up$recovery_disclosure) & nzchar(up$recovery_disclosure)])
  expect_length(txt("top_in"), 1L); expect_length(txt("half_width_in"), 1L)
  k <- match(paste(t4$estimand, t4$component), paste(up$estimand, up$component))
  s <- !is.na(k)
  expect_equal(t4$undersmooth_point[s], up$undersmooth_point[k[s]], tolerance = 1e-12)
  expect_true(any(is.finite(t4$undersmooth_point[t4$estimand == "top_in"])))
  # Every published table row about the top edge or the half-width carries annex 8.7's text.
  for (id in c("T3", "T4", "T5", "T8", "T9")) {
    x <- rd(tabf(id))
    expect_true("recovery_disclosure" %in% names(x), info = id)
    e <- if ("estimand" %in% names(x)) x$estimand else if (id == "T5") sub(" .*", "", x$quantity) else rep("", nrow(x))
    if (id == "T9") e <- ifelse(grepl("^Top edge", x$published_quantity), "top_in", ifelse(grepl("^Half-width", x$published_quantity), "half_width_in", ""))
    for (ed in c("top_in", "half_width_in")) {
      r <- which(e == ed)
      if (id %in% c("T3", "T4", "T9")) expect_gt(length(r), 0)
      expect_true(all(x$recovery_disclosure[r] == txt(ed)), info = paste(id, ed))
    }
  }
  # The chapter: each table row naming the top edge or the half-width has a filled Annex 8.7 cell,
  # and every caption of a figure whose alt text gives a top-edge number carries the caveat.
  L <- readLines(DOCS, warn = FALSE, encoding = "UTF-8")
  rows <- grep("^\\| (Top edge|Half-width)", L, value = TRUE)
  expect_gt(length(rows), 10)
  last <- vapply(strsplit(rows, " | ", fixed = TRUE), function(v) sub(" \\|$", "", v[length(v)]), "")
  expect_true(all(grepl("CI covered", last)), info = paste(rows[!grepl("CI covered", last)], collapse = "\n"))
  for (i in which(grepl("top edge", fman$alt, ignore.case = TRUE))) {
    expect_true(grepl("Top-edge caveat (annex 8.7", fman$caption[i], fixed = TRUE), info = fman$figure_id[i])
    expect_true(grepl("Half-width shortfall", fman$caption[i], fixed = TRUE), info = fman$figure_id[i])
  }
  expect_true(any(grepl("^- Top-edge caveat \\(annex 8\\.7, D-R0-04\\)", L)))
})

test_that("CH1-A13: F2b is W3.17's dz-by-pitch-type table, row for row, and sits in the chapter", {
  dz <- rd(file.path(OUT, "ch1", "fig", "F_dz_by_pitch_type.csv"))
  s <- side("F2b")
  r <- s[s$element == "pitch_type", ]
  expect_setequal(r$key, dz$pitch_type)
  m <- match(r$key, dz$pitch_type)
  expect_equal(r$n, dz$n[m])
  for (cc in c("p05", "p25", "p75", "p95")) expect_equal(r[[cc]], dz[[paste0(cc, "_dz_in")]][m], tolerance = 1e-12)
  expect_equal(r$value, dz$p50_dz_in[m], tolerance = 1e-12)
  expect_true(all(diff(r$value) <= 0))
  L <- readLines(DOCS, warn = FALSE, encoding = "UTF-8")
  expect_true(any(startsWith(L, "### F2b. ")))
})

test_that("CH1-A14: headline.csv carries the balanced-panel rows with the difference as a number", {
  hl <- rd(file.path(PUB, "headline.csv"))
  t4 <- rd(file.path(TAB, "T4_decomposition.csv")); t4 <- t4[t4$fit == "main" & t4$estimand == "area_sqin", ]
  ids <- c(delta_buffer = "CH1_W324_PANEL_BUF", delta_abs = "CH1_W324_PANEL_ABS", delta_total = "CH1_W324_PANEL_TOTAL")
  for (k in names(ids)) {
    h <- hl[hl$id == ids[[k]], ]
    r <- t4[t4$component == k, ]
    expect_equal(nrow(h), 1L, info = ids[[k]])
    expect_equal(h$point, r$panel_point, tolerance = 1e-9)
    expect_equal(c(h$lo95, h$hi95), c(r$panel_lo95, r$panel_hi95), tolerance = 1e-9)
    expect_true(grepl(sprintf("Panel minus primary: %+.2f sq in", r$panel_minus_primary), h$sentence, fixed = TRUE), info = h$sentence)
  }
  expect_identical(hl$id[1], "CH1_P1")
})

test_that("T8 reads W3.22's grid, and CH1-A9 is stated as not met while any cell did not run", {
  g <- rd(file.path(TAB, "sensitivity_grid.csv"))
  t8 <- rd(tabf("T8"))
  sm <- t8[t8$block == "summary", ]
  v <- function(k) sm$value[sm$key == k]
  expect_equal(v("n_grid_rows"), nrow(g))
  expect_equal(v("n_computed"), sum(g$status == "ok"))
  expect_equal(v("n_bam_ran"), sum(g$estimator == "bam" & g$status == "ok"))
  expect_equal(v("n_binned_ran"), sum(g$estimator == "binned" & g$status == "ok"))
  grid_rows <- t8[t8$block == "grid", ]
  expect_equal(nrow(grid_rows), 10L * nrow(g))
  L <- paste(readLines(DOCS, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  bad <- g$cell_id[g$status != "ok"]
  if (length(bad)) {
    expect_true(grepl("CH1-A9 is not met", L, fixed = TRUE))
    for (b in bad) expect_true(grepl(paste0("`", b, "`"), L, fixed = TRUE), info = b)
    expect_true(grepl(sprintf("over the %d computed rows only", sum(g$status == "ok")), L, fixed = TRUE))
  }
  expect_false(grepl("6 bam rows|six bam rows", L, ignore.case = TRUE))
})

test_that("D-21: F4's sidecar stays local, and the chapter says so", {
  gi <- readLines(file.path(ROOT, ".gitignore"), warn = FALSE)
  expect_true("out/tables/F4_data.csv" %in% trimws(gi))
  L <- readLines(DOCS, warn = FALSE, encoding = "UTF-8")
  expect_true(any(grepl("^Data: `out/tables/F4_data.csv`, kept local and not published", L)))
})

test_that("T9: Doolittle's comparable is reported as not reproduced and not headlined (DEV-85)", {
  t9 <- rd(tabf("T9"))
  d <- t9[t9$source == "Doolittle", ]
  expect_gt(nrow(d), 0)
  expect_true(all(d$reproduced == "no" & d$headlined == "no"))
  expect_true(any(grepl("not reproduced", d$reading, fixed = TRUE)))
})

test_that("determinism: a second render reproduces every sidecar and table CSV to 1e-8", {
  skip_if(identical(Sys.getenv("W324_SKIP_RERUN"), "1"), "W324_SKIP_RERUN=1")
  tmp <- tempfile("w324_")
  dir.create(tmp)
  on.exit(unlink(tmp, recursive = TRUE), add = TRUE)
  env <- c("STAN_NUM_THREADS=1", "OMP_NUM_THREADS=1")
  r1 <- suppressWarnings(system2("Rscript", c(file.path(ROOT, "R", "ch1", "70_figures.R"), "--stage", "render", "--dest", tmp),
                stdout = TRUE, stderr = TRUE, env = env))
  expect_true(is.null(attr(r1, "status")) || attr(r1, "status") %in% c(0L, 3L), info = paste(tail(r1, 5), collapse = "\n"))
  r2 <- suppressWarnings(system2("Rscript", c(file.path(ROOT, "R", "ch1", "71_tables.R"), "--dest", tmp, "--docs", file.path(tmp, "ch1.md")),
                stdout = TRUE, stderr = TRUE, env = env))
  expect_true(is.null(attr(r2, "status")) || attr(r2, "status") %in% c(0L, 3L), info = paste(tail(r2, 5), collapse = "\n"))
  files <- c(paste0(FIG_IDS, "_data.csv"), basename(tman$csv))
  for (f in files) {
    a <- rd(file.path(PUB, f)); b <- rd(file.path(tmp, "tables", f))
    expect_identical(names(a), names(b), info = f)
    expect_equal(nrow(a), nrow(b), info = f)
    for (c in names(a)) {
      if (is.numeric(a[[c]])) expect_equal(b[[c]], a[[c]], tolerance = 1e-8, info = paste(f, c))
      else expect_identical(b[[c]], a[[c]], info = paste(f, c))
    }
  }
  strip <- function(x) x[!grepl("\\]\\(|^Data: |^Source: ", x)]
  expect_identical(strip(readLines(file.path(tmp, "ch1.md"))), strip(readLines(DOCS)))
})

test_that("W3.24 is complete: no figure or table is a placeholder", {
  ph <- c(fman$figure_id[fman$status == "PLACEHOLDER"], tman$table_id[tman$status == "PLACEHOLDER"])
  msg <- paste(sprintf("%s blocked on %s", ph, BLOCKED[ph]), collapse = "; ")
  expect(length(ph) == 0L, sprintf("W3.24 INCOMPLETE, placeholders remain: %s", msg))
})
