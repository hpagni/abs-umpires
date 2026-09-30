# tests/testthat/test-ch1-sensitivity.R - SOP W3.22, the Chapter 1 sensitivity grid, and CH1-A9.
#
#   Rscript -e 'testthat::test_dir("tests/testthat", filter = "ch1-sensitivity", stop_on_failure = TRUE)'
#   W322_OUT=<root> reads <root>/ch1/tab/sensitivity_grid.csv instead of out/ (a synthetic dry run;
#   W322_SYNTHETIC=1 then allows the cells a synthetic table cannot run to be deferred).
#
# The test re-reads what R/ch1/50_sensitivity.R wrote and refits nothing. It holds its own copy
# of the SOP's cell list, verbatim, so a cell dropped from the script is caught here. It checks:
# every factor and cell present with its value, the primary row labelled; every row ok, or
# deferred for want of data with the reason (only the postseason cell, and only while the open
# view holds no postseason pitch); seed, draws and the decomposition identity; share_abs only
# where CH1-A9 licenses it; the bam rows are the primary and the four cells that move the
# headline most, ranked again from the binned rows; the binned and bam primaries reproduce W3.16;
# CH1-A9 as D-59 revised it (the sign of delta_buffer and of delta_abs each stable over the
# multiverse, on the headline area); T8 agrees with the grid; the script reads the warehouse
# through v_*_open views only and passes GD-04.

find_root <- function() {
  r <- Sys.getenv("ABSUMP_ROOT", "")
  if (nzchar(r)) return(normalizePath(r))
  d <- normalizePath(getwd())
  repeat {
    if (file.exists(file.path(d, "R", "ch1", "50_sensitivity.R"))) return(d)
    p <- dirname(d)
    if (identical(p, d)) stop("cannot find the repository root above ", getwd())
    d <- p
  }
}
ROOT <- find_root()
OUT <- Sys.getenv("W322_OUT", file.path(ROOT, "out"))
SYNTHETIC <- identical(Sys.getenv("W322_SYNTHETIC", ""), "1")
GRID <- file.path(OUT, "ch1", "tab", "sensitivity_grid.csv")
T8 <- file.path(OUT, "tables", "T8_sensitivity_data.csv")
T4 <- file.path(OUT, "ch1", "tab", "T4_decomposition_arms.csv")
SEED <- 20260922
N_DRAWS <- 1000
N_BAM <- 4L

# SOP W3.22, verbatim: factor, value, and the id the grid writes it under. TRUE: the primary's value.
SOP_CELLS <- read.csv(text = '
factor,value,cell_id,primary
r,0,r_0,FALSE
r,1.0,r_1.0,FALSE
r,1.45,r_1.45,TRUE
r,fitted,r_fitted,FALSE
height source,ABS-measured cohort,height_abs_cohort,FALSE
height source,roster+offset,height_roster_offset,TRUE
height source,per-batter ML offset,height_ml_offset,FALSE
shadow band,2,shadow_2,FALSE
shadow band,3,shadow_3,TRUE
shadow band,4,shadow_4,FALSE
band restriction,6,band_6,FALSE
band restriction,8,band_8,TRUE
band restriction,unrestricted,band_unrestricted,FALSE
plane,mid,plane_mid,TRUE
plane,front,plane_front,FALSE
blocked_ball,in,blocked_ball_in,TRUE
blocked_ball,out,blocked_ball_out,FALSE
position-player pitchers,in,pp_in,FALSE
position-player pitchers,out,pp_out,TRUE
postseason,in,postseason_in,FALSE
postseason,out,postseason_out,TRUE
k,0.75x,k_0.75x,FALSE
k,1.5x,k_1.5x,FALSE
standardisation mix,2024,mix_2024,TRUE
standardisation mix,2025,mix_2025,FALSE
standardisation mix,unweighted,mix_unweighted,FALSE', stringsAsFactors = FALSE, colClasses = "character")
SOP_CELLS$primary <- SOP_CELLS$primary == "TRUE"
EDGES <- c("top_in", "bot_in", "half_width_in", "shadow_rate")
DEFERRABLE <- if (SYNTHETIC) c("postseason_in", "pp_in", "blocked_ball_out", "r_fitted") else "postseason_in"

read_grid <- function() utils::read.csv(GRID, stringsAsFactors = FALSE, check.names = FALSE, na.strings = "")
sgn <- function(x) ifelse(x > 0, 1L, ifelse(x < 0, -1L, 0L))

test_that("the grid exists and every row carries the columns W3.22 asks for", {
  expect_true(file.exists(GRID), info = GRID)
  g <- read_grid()
  need <- c("id", "cell_id", "factor", "value", "is_primary", "same_as_primary", "estimator", "status", "status_note",
            "headline_estimand", "delta_buffer", "delta_buffer_lo95", "delta_buffer_hi95", "delta_abs", "delta_abs_lo95",
            "delta_abs_hi95", "sum_lo95", "sum_hi95", "share_abs", "share_abs_lo95", "share_abs_hi95", "share_reported",
            "n_rows", "n_draws", "seed", "estimator_detail", "identity_residual_max",
            as.vector(outer(EDGES, c("delta_buffer", "delta_buffer_lo95", "delta_buffer_hi95", "delta_abs", "delta_abs_lo95",
                                     "delta_abs_hi95"), paste, sep = "_")))
  expect_equal(setdiff(need, names(g)), character(0))
  expect_true(all(g$headline_estimand == "area_sqin"))
  expect_false(anyDuplicated(g$id) > 0)
})

test_that("every SOP factor and cell is present with its verbatim value, and the primary row is labelled", {
  g <- read_grid()
  b <- g[g$estimator == "binned", ]
  for (i in seq_len(nrow(SOP_CELLS))) {
    x <- b[b$cell_id == SOP_CELLS$cell_id[i], ]
    expect_equal(nrow(x), 1L, info = SOP_CELLS$cell_id[i])
    expect_identical(c(x$factor, x$value), c(SOP_CELLS$factor[i], SOP_CELLS$value[i]), info = SOP_CELLS$cell_id[i])
    expect_identical(isTRUE(x$same_as_primary), SOP_CELLS$primary[i], info = SOP_CELLS$cell_id[i])
  }
  expect_equal(sort(unique(b$factor[b$cell_id != "primary"])), sort(unique(SOP_CELLS$factor)))
  pr <- g[g$is_primary %in% TRUE, ]
  expect_setequal(pr$estimator, c("binned", "bam"))
  expect_true(all(pr$cell_id == "primary" & pr$status == "ok"))
  same <- b[b$same_as_primary %in% TRUE & b$cell_id != "primary", ]
  p <- b[b$cell_id == "primary", ]
  for (k in c("delta_buffer", "delta_abs", "delta_buffer_lo95", "delta_abs_hi95")) expect_true(all(same[[k]] == p[[k]]), info = k)
})

test_that("every row is ok, or deferred for want of data with its reason", {
  g <- read_grid()
  expect_true(all(g$status %in% c("ok", "deferred")))
  d <- g[g$status == "deferred", ]
  expect_true(all(d$cell_id %in% DEFERRABLE), info = paste(d$id, collapse = ", "))
  expect_true(all(!is.na(d$status_note) & nzchar(d$status_note)))
  if ("postseason_in" %in% d$cell_id && !SYNTHETIC) {
    n <- tryCatch({
      con <- DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:")
      on.exit(DBI::dbDisconnect(con, shutdown = TRUE), add = TRUE)
      db <- file.path(ROOT, "warehouse", "abs.duckdb")
      DBI::dbExecute(con, sprintf("ATTACH %s AS abs (READ_ONLY)", DBI::dbQuoteString(con, db)))
      DBI::dbGetQuery(con, "SELECT count(*) AS n FROM abs.main_marts.v_called_pitch_open AS c
                            WHERE c.level = 'mlb' AND c.game_type IN ('F', 'D', 'L', 'W') AND c.analysis_set = 'open'")$n
    }, error = function(e) NA_real_)
    if (is.na(n)) {
      message("W3.22: the warehouse could not be attached; the postseason deferral is taken from the grid's note")
    } else {
      expect_equal(n, 0, info = "the open view now holds postseason pitches: the deferral has lapsed, rerun the grid")
    }
    message("W3.22 DEFERRED-PENDING-POSTSEASON-PULL: ", d$status_note[d$cell_id == "postseason_in"][1])
  }
})

test_that("each ok row: seed 20260922, 1,000 draws, rows, and the identity to 1e-9", {
  g <- read_grid()
  ok <- g[g$status == "ok", ]
  expect_true(all(ok$seed == SEED))
  expect_true(all(ok$n_draws == N_DRAWS))
  expect_true(all(ok$n_rows > 0))
  expect_true(all(ok$identity_residual_max <= 1e-9))
  expect_true(all(ok$delta_buffer_lo95 <= ok$delta_buffer_hi95 & ok$delta_abs_lo95 <= ok$delta_abs_hi95))
  expect_true(all(ok$estimator %in% c("binned", "bam")))
})

test_that("share_abs is reported exactly where the 95% interval on the sum excludes zero (CH1-A9)", {
  g <- read_grid()
  ok <- g[g$status == "ok", ]
  excl <- ok$sum_lo95 > 0 | ok$sum_hi95 < 0
  expect_identical(as.logical(ok$share_reported), excl)
  expect_identical(is.na(ok$share_abs), !excl)
  expect_identical(is.na(ok$share_abs_lo95), !excl)
})

test_that("bam refits the primary and the four cells that move the headline most", {
  g <- read_grid()
  b <- g[g$estimator == "binned", ]
  p <- b[b$cell_id == "primary", ]
  c <- b[b$status == "ok" & !(b$same_as_primary %in% TRUE) & b$cell_id != "primary", ]
  c$shift <- pmax(abs(c$delta_buffer - p$delta_buffer), abs(c$delta_abs - p$delta_abs))
  c <- c[order(-c$shift, match(c$cell_id, SOP_CELLS$cell_id)), ]
  top <- utils::head(c$cell_id, N_BAM)
  bam <- g[g$estimator == "bam" & g$status == "ok", ]
  expect_setequal(bam$cell_id, c("primary", top))
  expect_true(all(g$bam_selected[g$cell_id %in% top] %in% TRUE))
})

test_that("the binned and bam primaries reproduce W3.16's CH1-A5 binned arm and its primary", {
  skip_if_not(file.exists(T4), "no T4_decomposition_arms.csv beside the grid")
  g <- read_grid()
  t4 <- utils::read.csv(T4, stringsAsFactors = FALSE)
  for (pair in list(c("binned", "binned"), c("bam", "main"))) {
    p <- g[g$estimator == pair[1] & g$cell_id == "primary", ]
    a <- t4[t4$fit == pair[2] & t4$estimand == "area_sqin", ]
    expect_equal(p$delta_buffer, a$point[a$component == "delta_buffer"], tolerance = 1e-6, info = pair[1])
    expect_equal(p$delta_abs, a$point[a$component == "delta_abs"], tolerance = 1e-6, info = pair[1])
    e <- t4[t4$fit == pair[2] & t4$estimand == "top_in", ]
    expect_equal(p$top_in_delta_abs, e$point[e$component == "delta_abs"], tolerance = 1e-6, info = pair[1])
  }
})

test_that("CH1-A9: the sign of delta_buffer and of delta_abs is each stable across the multiverse", {
  g <- read_grid()
  ok <- g[g$status == "ok", ]
  for (e in EDGES) for (comp in c("delta_buffer", "delta_abs")) {
    s <- table(sgn(ok[[sprintf("%s_%s", e, comp)]]))
    message(sprintf("W3.22 %s_%s signs over %d ok rows: %s", e, comp, nrow(ok), paste(names(s), s, sep = " x", collapse = ", ")))
  }
  for (comp in c("delta_buffer", "delta_abs")) {
    s <- sgn(ok[[comp]])
    expect_true(length(unique(s)) == 1L && s[1] != 0L,
                info = sprintf("area %s changes sign: %s", comp, paste(ok$id[s != s[ok$cell_id == "primary" & ok$estimator == "bam"]],
                                                                       collapse = ", ")))
  }
})

test_that("T8 is the grid in long form", {
  expect_true(file.exists(T8), info = T8)
  g <- read_grid()
  t8 <- utils::read.csv(T8, stringsAsFactors = FALSE, na.strings = "")
  expect_equal(nrow(t8), nrow(g) * (5L + 2L * length(EDGES)))
  a <- t8[t8$cell_id == "primary" & t8$estimator == "bam" & t8$estimand == "area_sqin" & t8$component == "delta_abs", ]
  expect_equal(a$point, g$delta_abs[g$cell_id == "primary" & g$estimator == "bam"])
})

test_that("the grid reads the warehouse through v_*_open views only, and passes GD-04", {
  src <- readLines(file.path(ROOT, "R", "ch1", "50_sensitivity.R"))
  rel <- regmatches(src, regexpr("(FROM|JOIN)\\s+abs\\.[a-z_]+\\.[A-Za-z_]+", src))
  expect_true(length(rel) > 0L)
  expect_true(all(grepl("\\.v_[a-z_]+_open$", rel)), info = paste(rel, collapse = "; "))
  cmd <- sprintf("cd %s && uv run --locked python tests/guard/gd04_scan.py --path R/ch1/50_sensitivity.R 2>&1", shQuote(ROOT))
  out <- suppressWarnings(system(cmd, intern = TRUE))
  expect_null(attr(out, "status"), info = paste(out, collapse = "\n"))
})
