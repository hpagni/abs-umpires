#!/usr/bin/env Rscript
# tests/ch1/test_ch1_sprint.R - unit tests for the Chapter 1 sprint fits, SOP W3.14 to W3.18, W3.21,
# W6.7 and W6.8, on synthetic inputs only. No bam fit, no real row, about a minute.
#
#   Rscript tests/ch1/test_ch1_sprint.R
#
# One line per clause, PASS or FAIL, exit 1 after reporting every failure. The end-to-end dry run
# on a synthetic table, fits included, is tests/model/test_mt_ch1_sprint.py.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
setwd(ROOT)
source(file.path(ROOT, "R", "lib", "ch1_fits.R"))
TMP <- tempfile("ch1_sprint_")
dir.create(TMP)
norm <- function(s) gsub("\\s+", " ", trimws(s))

## 1. the frozen specification and its three forms
md <- readLines(file.path(ROOT, "docs", "prereg", "ch1.md"))
i0 <- which(md == "## 2. The frozen specification")
fence <- which(startsWith(md, "```"))
fence <- fence[fence > i0][1:2]
annex <- paste(md[(fence[1] + 1):(fence[2] - 1)], collapse = " ")
check("FROZEN_FORMULA_TEXT is the annex section 2 block", identical(norm(annex), norm(FROZEN_FORMULA_TEXT)), norm(annex))
fs <- spec_formula("single"); fh <- spec_formula("half")
check("single: no season terms, no s(umpire_season)", !grepl("season", fs) && grepl("s(umpire_hp_id", fs, fixed = TRUE), fs)
check("half: half, half_o and s(umpire_half) replace the season terms",
      grepl("cs ~ half +", fh, fixed = TRUE) && grepl("by = half_o", fh, fixed = TRUE) &&
        grepl("s(umpire_half", fh, fixed = TRUE) && !grepl("season", fh), fh)
fu <- spec_formula("undersmooth")
check("undersmooth: the frozen text with the season by-term alone at k = 24 (annex 8.7)",
      identical(norm(fu), norm(sub("k = c(18,18), by = season_o)", "k = c(24,24), by = season_o)", FROZEN_FORMULA_TEXT, fixed = TRUE))) &&
        !identical(norm(fu), norm(FROZEN_FORMULA_TEXT)) && lengths(regmatches(fu, gregexpr("k = c(24,24)", fu, fixed = TRUE))) == 2L &&
        grepl("k = c(12,12), by = count_class_o", fu, fixed = TRUE) && identical(make_spec("undersmooth")$period, "season"), fu)
md87 <- paste(md, collapse = " ")
check("annex 8.7 pre-registers SENS-B1-UNDERSMOOTH at season k = 24", grepl("SENS-B1-UNDERSMOOTH", md87, fixed = TRUE) &&
        grepl("season by-term at k = 24 instead of 18", md87, fixed = TRUE), "docs/prereg/ch1.md")
tab87 <- md[grepl("^\\| (CH1-A7|MT-04): .*\\*\\*not met\\*\\*", md)]
check("W3.16's recovery disclosure carries the annex 8.7 rows that are not met (D-R0-04)",
      length(tab87) == 3L && any(grepl("\\| top \\| 91 of 100 \\|", tab87)) && any(grepl("\\| top \\| 44 of 50", tab87)) &&
        any(grepl("\\| half-width \\| 42 of 50 \\|", tab87)) && grepl("91 of 100", RECOVERY_NOTE[["top_in"]], fixed = TRUE) &&
        grepl("44 of 50", RECOVERY_NOTE[["top_in"]], fixed = TRUE) &&
        grepl("42 of 50", RECOVERY_NOTE[["half_width_in"]], fixed = TRUE), paste(length(tab87), "rows not met"))
check("grid is 301 x 276", length(XG) == 301L && length(ZG) == 276L, sprintf("%d x %d", length(XG), length(ZG)))
check("zn = 0.4025 lies between the two middle rows", ZG[J_MID_LO] < ZN_MID && ZN_MID < ZG[J_MID_HI],
      sprintf("%.3f < 0.4025 < %.3f", ZG[J_MID_LO], ZG[J_MID_HI]))
check("51 columns with |x| <= 0.25 ft", length(I_CENTRE) == 51L, sprintf("%d", length(I_CENTRE)))

## 2. the contour geometry on an analytic surface: logit = 2 - D, D the signed distance in inches
## (72-inch batter) from the rectangle top 38.9, bottom 18.6, half-width 9.0; the 50% contour is
## that rectangle pushed out 2 in with rounded corners of radius 2 in.
rect <- c(top = 38.9, bot = 18.6, hw = 9.0)
sd_in <- function(u, v) {
  dx <- abs(u) - rect[["hw"]]; dz <- pmax(rect[["bot"]] - v, v - rect[["top"]])
  ifelse(dx > 0 & dz > 0, sqrt(dx^2 + dz^2), pmax(dx, dz))
}
L <- outer(XG, ZG, function(x, z) 2 - sd_in(12 * x, 72 * z))
s <- list(grid = plogis(L), line = plogis(2 - sd_in(12 * XG, 72 * ZN_MID)))
met <- edge_metrics(s)
area_true <- 2 * (rect[["hw"]] + 2) * (rect[["top"]] - rect[["bot"]] + 4) - (4 - pi) * 4
check("top_in on the analytic surface", abs(met[["top_in"]] - 40.9) < 1e-6, sprintf("%.6f against 40.9", met[["top_in"]]))
check("bot_in on the analytic surface", abs(met[["bot_in"]] - 16.6) < 1e-6, sprintf("%.6f against 16.6", met[["bot_in"]]))
check("half_width_in on the analytic surface", abs(met[["half_width_in"]] - 11.0) < 1e-6, sprintf("%.6f against 11.0", met[["half_width_in"]]))
check("area_sqin by marching squares within 0.1 sq in", abs(met[["area_sqin"]] - area_true) < 0.1,
      sprintf("%.3f against %.3f", met[["area_sqin"]], area_true))
check("no closed contour around the centre gives NA", is.na(contour_area(-abs(L) - 1)), "")

## 3. the tabulated quantile mixture used for the draws
set.seed(11)
q <- sort(stats::rnorm(NQ, 0, 0.4))
tb <- mix_table(q)
E <- matrix(stats::runif(2000, -12, 12), 40)
exact <- matrix(rowMeans(plogis(outer(as.vector(E), q, "+"))), 40)
check("mixture table error below 1e-8", tb$err < 1e-8 && max(abs(mix_eval(tb, E) - exact)) < 1e-8,
      sprintf("table %.1e, evaluated %.1e", tb$err, max(abs(mix_eval(tb, E) - exact))))

## 4. the decomposition
th <- matrix(stats::rnorm(5000, 500, 3), 1000, 5)
w <- pretrend_weights(th[, 1:3])
D <- decompose(th, w)
check("identity to 1e-9 on 1,000 random draws", max(abs(D$identity_residual)) < 1e-9, sprintf("%.1e", max(abs(D$identity_residual))))
lin <- matrix(c(10, 10.5, 11, 12, 12.1), 1)
check("g is the slope of a linear pre-trend whatever the weights", abs(decompose(lin, c(1, 5, 2))$g - 0.5) < 1e-12 &&
        abs(decompose(lin, c(1, 5, 2))$delta_buffer - 0.5) < 1e-12 && abs(decompose(lin, c(1, 5, 2))$delta_abs - (-0.4)) < 1e-12,
      "g 0.5, delta_buffer 0.5, delta_abs -0.4")
de <- decompose_estimand(c(500, 500, 500, 501, 499), cbind(matrix(stats::rnorm(3000, 500, 1), 1000), stats::rnorm(1000, 501, 1),
                                                          stats::rnorm(1000, 499, 1)), "area_sqin", "sq in")
check("share_abs withheld when the 95% interval on the sum includes zero",
      !de$table$reported[de$table$component == "share_abs"], "CH1-A9")
de2 <- decompose_estimand(c(500, 500, 500, 490, 480), cbind(matrix(stats::rnorm(3000, 500, 0.5), 1000),
                                                           stats::rnorm(1000, 490, 0.5), stats::rnorm(1000, 480, 0.5)), "area_sqin", "sq in")
check("share_abs reported when that interval excludes zero", de2$table$reported[de2$table$component == "share_abs"], "CH1-A9")

## 5. B1 on simulated cells with a known link, and B3
u <- seq(U_MIN, U_MAX, by = U_STEP)
lp <- matrix(rep(1.8 - 0.9 * u, length(LINK_COLS)), ncol = length(LINK_COLS), dimnames = list(NULL, LINK_COLS))
lut <- make_lut(lp)
set.seed(12)
n <- 3000L
cells <- data.frame(umpire_hp_id = rep(1:6, each = n / 6), season = 2025L, edge = "top", stringsAsFactors = FALSE)
true <- c(-0.6, -0.2, 0, 0.1, 0.4, 0.8)
dd <- stats::runif(n, -3, 3)
y <- as.integer(stats::runif(n) < plogis(1.8 - 0.9 * (dd - true[cells$umpire_hp_id])))
b1 <- b1_cells(cells, lut_base(link_col("top", "buffer_2025"), dd, lut), y, lut)
z <- (b1$delta - true) / b1$se_delta
check("B1 recovers six known offsets within 3.5 SE", all(abs(z) < 3.5),
      paste(sprintf("%.2f (se %.2f)", b1$delta, b1$se_delta), collapse = ", "))
se_an <- 1 / (0.9 * sqrt(sum(plogis(1.8 - 0.9 * dd[1:500]) * (1 - plogis(1.8 - 0.9 * dd[1:500])))))
check("B1 profile SE near the analytic SE", abs(b1$se_delta[1] / se_an - 1) < 0.25, sprintf("%.3f against %.3f", b1$se_delta[1], se_an))
h <- expand.grid(umpire_hp_id = 1:20, season = c(2025L, 2026L), edge = EDGE_LEVELS, half = c("odd", "even"),
                 stringsAsFactors = FALSE)
resp <- stats::rnorm(20, 0, 0.3)
h$delta <- ifelse(h$season == 2026L, resp[h$umpire_hp_id], 0) + stats::rnorm(nrow(h), 0, 0.02)
h$se_delta <- 0.02; h$n <- 100L; h$at_bound <- FALSE
sph <- split_half(h)
check("B3 split-half of a clean response is near 1", sph$sb_response > 0.95 && sph$n_umpires == 20L,
      sprintf("SB %.3f over %d umpires", sph$sb_response, sph$n_umpires))

## 6. the binned logistic on cells with known crossings
set.seed(13)
cellsb <- expand.grid(edge = EDGE_LEVELS, bin = 0:31, season = SEASONS, count_class = CC_LEVELS, stand = STAND_LEVELS,
                      stringsAsFactors = FALSE)
d50 <- c(side = 2.2, top = 1.95, bot = 2.42)
pr <- plogis(-1.0 * (bin_centre(cellsb$bin) - d50[cellsb$edge]))
cellsb$strikes <- stats::rbinom(nrow(cellsb), 400, pr); cellsb$balls <- 400 - cellsb$strikes
bf <- fit_binned(cellsb)
bw <- binned_ref_weights(data.frame(count_class = rep(CC_LEVELS, 2), stand = rep(STAND_LEVELS, each = 3)))
be <- binned_estimands(bf, bw, "2024")
check("binned: top_in = 0.535 x 72 + d50 within 0.1 in", abs(be[1, "top_in"] - (0.535 * 72 + 1.95)) < 0.1,
      sprintf("%.3f against %.3f", be[1, "top_in"], 0.535 * 72 + 1.95))
check("binned: half_width_in = 8.5 + d50 within 0.1 in", abs(be[1, "half_width_in"] - 10.7) < 0.1,
      sprintf("%.3f against 10.7", be[1, "half_width_in"]))

## 7. samples: the balanced panel, the All-Star split, the game halves
toy <- expand.grid(umpire_hp_id = 1:3, season = SEASONS, game = 1:16)
toy$game_pk <- toy$season * 1000 + toy$umpire_hp_id * 100 + toy$game
toy <- toy[!(toy$umpire_hp_id == 3 & toy$season == 2024 & toy$game > 10), ]
check("panel: >= 15 home-plate games in every season", identical(panel_umpires(toy), 1:2), paste(panel_umpires(toy), collapse = ","))
hs <- season_half(data.frame(season = c(2025L, 2025L, 2023L), official_date = as.Date(c("2025-07-14", "2025-07-18", "2023-07-10"))))
check("All-Star split: last first-half day and first second-half day", identical(hs, c("first", "second", NA)), paste(hs, collapse = ","))
gh <- game_halves(data.frame(umpire_hp_id = 1L, season = 2025L, official_date = as.Date("2025-05-01") + 0:3, game_pk = 4:1))
check("game halves alternate by date order", identical(gh, c("odd", "even", "odd", "even")), paste(gh, collapse = ","))

## 8. the height rule
hd <- data.frame(x_mid = c(0.2, -0.9, 0.1, 0.85), z_mid = c(3.5, 1.6, 2.4, 2.0), H = c(74.002, 72.002, 70.002, 76.002),
                 H_abs = c(74.1, NA, 69.8, NA))
hd$d <- signed_edge_in(hd$x_mid, hd$z_mid, abs_top_ft(hd$H), abs_bot_ft(hd$H))
hd$d_abs <- ifelse(is.na(hd$H_abs), NA, signed_edge_in(hd$x_mid, hd$z_mid, abs_top_ft(hd$H_abs), abs_bot_ft(hd$H_abs)))
tfile <- file.path(TMP, "h.parquet")
tbh <- arrow::arrow_table(data.frame(a = 1))
tbh$metadata$w37_height <- "H = h_roster_in + o, o = 0.002000000000 in"
arrow::write_parquet(tbh, tfile)
ctx_h <- list(table = tfile)
ph <- apply_heights(hd, "primary", list(offset_in = 0.002, offset_noncohort_in = -0.35), ctx_h)
check("primary: non-cohort rows move by the D-P4-04 offset, cohort rows keep theirs",
      isTRUE(all.equal(ph$H, c(74.002, 71.65, 70.002, 75.65))) &&
        isTRUE(all.equal(ph$d, signed_edge_in(hd$x_mid, hd$z_mid, abs_top_ft(ph$H), abs_bot_ft(ph$H)))),
      paste(ph$H, collapse = ", "))
err <- tryCatch({apply_heights(hd, "primary", list(offset_in = 0.002), ctx_h); "no error"}, error = function(e) conditionMessage(e))
check("primary refuses without D-P4-04's offset", grepl("offset_noncohort_in", err), substr(err, 1, 80))
pa <- apply_heights(hd, "abs", list(offset_in = 0.002), ctx_h)
check("abs arm: P1 rows on H_abs", nrow(pa) == 2L && identical(pa$H, c(74.1, 69.8)), paste(pa$H, collapse = ", "))

## 9. rows other steps share
hf <- file.path(TMP, "headline.csv")
r1 <- data.frame(id = "A", note = "one, with a comma", stringsAsFactors = FALSE)
r2 <- data.frame(id = "B", note = "two", stringsAsFactors = FALSE)
upsert_row(hf, r1); upsert_row(hf, r2)
before <- readLines(hf)
upsert_row(hf, data.frame(id = "A", note = "one again", stringsAsFactors = FALSE))
after <- readLines(hf)
check("upsert replaces only its own row", length(after) == 3L && after[3] == before[3] && grepl("one again", after[2]),
      paste(after, collapse = " | "))

## 10. CH1-A6's gate, read off the committed curve
g <- ch1a6_gate()
check("CH1-A6 gate: c* 0.20, not attainable (annex 8.4)", identical(g$c_star, 0.20) && identical(g$attainable, FALSE), g$detail)

## 11. the guards, run as the entry points run them
syn <- file.path(TMP, "syn")
st <- system2("Rscript", c(file.path(ROOT, "R/ch1/29_synthetic_table.R"), "--make", "--out", syn, "--scale", "tiny"),
              stdout = FALSE, stderr = FALSE)
check("the synthetic generator runs", st == 0L, syn)
tb <- file.path(syn, "ch1_synth.parquet")
out_in <- suppressWarnings(system2("Rscript", c(file.path(ROOT, "R/ch1/20_surfaces.R"), "--table", tb, "--out", file.path(ROOT, "out"),
                               "--fits", "binned"), stdout = TRUE, stderr = TRUE))
check("a synthetic run may not write inside the repository", identical(attr(out_in, "status"), 4L) &&
        any(grepl("REFUSED", out_in)), tail(out_in, 1))
real <- file.path(TMP, "real.parquet")
x <- as.data.frame(arrow::read_parquet(tb))
x$is_synthetic <- NULL
arrow::write_parquet(x, real)
anc <- suppressWarnings(system2("git", c("-C", ROOT, "merge-base", "--is-ancestor", prereg_tag(), "HEAD"),
                                stdout = FALSE, stderr = FALSE))
out_r <- suppressWarnings(system2("Rscript", c(file.path(ROOT, "R/ch1/20_surfaces.R"), "--table", real, "--out", file.path(TMP, "out"),
                              "--fits", "binned"), stdout = TRUE, stderr = TRUE))
if (!identical(as.integer(anc), 0L)) {
  check("a table without the synthetic marker is refused before prereg-v1 (GD-12)",
        identical(attr(out_r, "status"), 4L) && any(grepl("GD-12", out_r)), tail(out_r, 1))
} else {
  check("after prereg-v1 a real table runs only with committed code", any(grepl("GD-12|REFUSED|mode", out_r)), tail(out_r, 1))
}
out_d <- suppressWarnings(system2("Rscript", c(file.path(ROOT, "R/ch1/20_surfaces.R"), "--table", real, "--out", file.path(TMP, "out"),
                              "--draws", "50"), stdout = TRUE, stderr = TRUE))
check("a real table refuses a dry-run setting", identical(attr(out_d, "status"), 4L) && any(grepl("--draws", out_d)),
      tail(out_d, 1))
# D-67: the tag must be on origin at the local commit. Throwaway repositories under TMP only.
tp <- file.path(TMP, "tagrepo")
dir.create(tp)
gsys <- function(dir, ...) system2("git", c("-C", shQuote(dir), "-c", "user.name=t", "-c", "user.email=t@t", ...),
                                   stdout = FALSE, stderr = FALSE)
gsys(tp, "init", "-q", "-b", "main", "src")
gsys(file.path(tp, "src"), "commit", "-q", "--allow-empty", "-m", "one")
gsys(tp, "clone", "-q", "--bare", "src", "origin.git")
gsys(tp, "clone", "-q", "origin.git", "work")
root_saved <- ROOT
ROOT <- file.path(tp, "work")
t_none <- tag_pushed("prereg-v1")$ok
gsys(ROOT, "tag", "-a", "prereg-v1", "-m", "t")
t_local <- tag_pushed("prereg-v1")$ok
gsys(ROOT, "push", "-q", "origin", "refs/tags/prereg-v1")
t_pushed <- tag_pushed("prereg-v1")$ok
ROOT <- root_saved
check("D-67: no tag or an unpushed tag refuses; the tag on origin at the local commit passes",
      identical(c(t_none, t_local, t_pushed), c(FALSE, FALSE, TRUE)), paste(t_none, t_local, t_pushed))

## 12. the ledger generator: model slots land before the W6.4 join slots, and a re-run is a no-op
inp <- file.path(TMP, "inputs")
dir.create(file.path(inp, "out", "tables"), recursive = TRUE)
write_csv_plain(data.frame(slot = c("D_BUF", "D_ABS"), point = c(-3.21, -7.654), lo95 = c(-5.5, -9.9), hi95 = c(-1.1, -5.4),
                           units = "sq in", estimator = "test", source_csv = "out/ch1/tab/T4_decomposition.csv",
                           source_row = c(2L, 3L)), file.path(inp, "out", "tables", "abstract_slots_ch1.csv"))
led <- file.path(inp, "docs", "numbers.json")
ex <- c(file.path(ROOT, "tools/comms/export_numbers.R"), "--inputs", inp, "--base", file.path(ROOT, "docs/numbers.json"),
        "--out", led, "--synthetic")
st1 <- system2("Rscript", ex, stdout = FALSE, stderr = FALSE)
lj <- fromJSON(led, simplifyVector = FALSE)
carried <- vapply(lj$entries, function(e) if (is.null(e$carried_by)) "" else e$carried_by, "")
slots <- vapply(lj$entries, function(e) e$slot, "")
first_join <- which(carried == "W6.4")[1]
check("model slots sit after the W6.3 slots and before the W6.4 join slots",
      st1 == 0L && all(which(slots %in% c("D_BUF", "D_ABS")) < first_join) &&
        all(which(slots %in% c("D_BUF", "D_ABS")) > max(which(carried == "W6.3"))), paste(slots, collapse = ","))
e1 <- lj$entries[[which(slots == "D_ABS")]]
check("an entry carries the printed numbers", identical(e1$print$value, "-7.7") && identical(e1$print$lo95, "-9.9"),
      toJSON(e1$print, auto_unbox = TRUE))
st2 <- system2("Rscript", c(ex[1:7], "--check", "--synthetic"), stdout = FALSE, stderr = FALSE)
check("a regeneration is a no-op (--check exits 0)", st2 == 0L, sprintf("exit %d", st2))
st3 <- system2("Rscript", c(file.path(ROOT, "tools/comms/export_numbers.R"), "--synthetic"), stdout = FALSE, stderr = FALSE)
check("--synthetic refuses to write docs/numbers.json", st3 == 2L, sprintf("exit %d", st3))

## 13. the two shadow bands, the draws object and the receipts
check("shadow_rate band is |d - 1.45| <= 3 in (D-P4-09)", identical(shadow_band(c(-1.6, -1.5, 4.4, 4.5)), c(FALSE, TRUE, TRUE, FALSE)),
      "d = -1.6, -1.5, 4.4, 4.5")
check("B1 band is |d| <= 3 in on the ball-centre d (annex 8.1)", identical(b1_band(c(-3.1, -3, 3, 3.1)), c(FALSE, TRUE, TRUE, FALSE)),
      "d = -3.1, -3, 3, 3.1")
fake <- list(coefficients = c(a = 1, b = -2), Vc = diag(c(0.04, 0.09)), Vp = diag(2))
cd <- coef_draws(structure(fake, class = "fake"), 500L, DRAW_SEED)
check("draws: a 500 x 2 matrix named by coefficient, Vc and the seed attached",
      is.matrix(cd) && identical(dim(cd), c(500L, 2L)) && identical(colnames(cd), c("a", "b")) &&
        identical(attr(cd, "covariance"), "Vc") && identical(attr(cd, "seed"), DRAW_SEED) &&
        abs(stats::sd(cd[, 2]) - 0.3) < 0.03, sprintf("sd %.3f against 0.3", stats::sd(cd[, 2])))
h1 <- git_out(c("rev-parse", "HEAD~1"))$out[1]; h0 <- git_head()
check("the union receipt's git_sha is the earliest fit commit", identical(earliest_sha(c(h0, h1, h0)), h1),
      substr(h1, 1, 12))
ctx_r <- list(step = "W9.99", out = file.path(TMP, "rc", "out"), paths = out_paths(file.path(TMP, "rc", "out")),
              code_shas = c(x = "00"), gd12 = list(detail = "test"), synthetic = TRUE, table = "t.parquet")
rr <- data.frame(game_pk = c(1L, 1L, 2L), official_date = as.Date(c("2024-05-01", "2024-05-01", "2025-06-02")),
                 analysis_set = "open")
step_receipt(ctx_r, rows = rr, outputs = tfile)
rj <- fromJSON(file.path(TMP, "rc", "out", "models", "ch1_W9_99", "provenance.json"))
check("a run receipt carries the nine section 1.4 keys and one git_sha",
      all(c("n_games", "n_rows", "min_official_date", "max_official_date", "game_pk_sha256", "analysis_sets_touched",
            "seed", "code_sha256", "git_sha") %in% names(rj)) && rj$n_games == 2L && rj$max_official_date == "2025-06-02" &&
        grepl("^[0-9a-f]{40}$", rj$git_sha), sprintf("%d games, last %s", rj$n_games, rj$max_official_date))
out_na <- suppressWarnings(system2("Rscript", file.path(ROOT, "R/ch1/23_decomposition.R"), stdout = TRUE, stderr = TRUE))
if (!identical(as.integer(anc), 0L)) {
  check("with no arguments a script targets the real table and is refused before prereg-v1",
        identical(attr(out_na, "status"), 4L) && any(grepl("REFUSED W3.16: real data, and GD-12", out_na)), tail(out_na, 1))
}

## 14. W6.7's sentences, both directions and both readings
rw <- function(p, lo, hi, ap = NA, alo = NA, ahi = NA, ag = NA) {
  data.frame(point = p, lo95 = lo, hi95 = hi, abs_cohort_point = ap, abs_cohort_lo95 = alo, abs_cohort_hi95 = ahi,
             sign_agrees_abs_cohort = ag)
}
s_c <- headline_sentence(rw(-12.34, -15, -9.5), rw(-4.44, -6, -2.1), rw(-6.66, -9, -4.2), causal = TRUE)
check("causal template: contraction, magnitudes in its direction", identical(s_c, paste(
  "Of the 12.3 square inches (95% CI 9.5 to 15.0) by which the called zone contracted between 2024 and 2026,",
  "4.4 (95% CI 2.1 to 6.0) is attributable to the 2025 grading-buffer cut and 6.7 (95% CI 4.2 to 9.0) to the ABS challenge system.")),
  s_c)
s_d <- headline_sentence(rw(3.2, 1.1, 5.3), rw(-0.4, -2, 1.3), rw(2.5, 0.2, 4.4), causal = FALSE)
check("descriptive reading: expansion, no cause named", grepl("expanded", s_d) && grepl("-0.4 (95% CI -2.0 to 1.3) falls in", s_d, fixed = TRUE) &&
        !grepl("caus|attributable", s_d), s_d)
c_ok <- cohort_sentence(rw(-4, -6, -2, -3.5, -6.1, -0.9, TRUE), rw(-6, -9, -4, -5.2, -8.8, -1.6, TRUE))
c_no <- cohort_sentence(rw(-4, -6, -2, 0.7, -1.9, 3.3, FALSE), rw(-6, -9, -4, -5.2, -8.8, -1.6, TRUE))
check("D-P4-04 sentence: agreement, and the sensitivity reading when a sign differs",
      grepl("agrees in sign on both components", c_ok) && grepl("sensitive to the height cohort", c_no), c_no)

unlink(TMP, recursive = TRUE)
finish("tests/ch1/test_ch1_sprint.R")
