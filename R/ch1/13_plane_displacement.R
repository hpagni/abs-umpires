#!/usr/bin/env Rscript
# R/ch1/13_plane_displacement.R - SOP step W3.10, pitch-level plane displacements.
#
# Run from the repository root so that .Rprofile activates renv:
#
#   Rscript R/ch1/13_plane_displacement.R           build the table, write
#                                                    data/interim/ch1/plane_displacement.csv
#   Rscript R/ch1/13_plane_displacement.R --check   build it again, compare with the file on
#                                                    disk, write nothing
#
# WHAT IT MEASURES. Statcast published plate_x and plate_z at the front of the
# plate (y = 17/12 ft) through 2025 and at the middle (y = 8.5/12 ft) from 2026
# (SOP section 2.5). For every called pitch this script moves the pitch from the
# front plane to the middle plane with reproject() from R/lib/zone.R and keeps
# the two displacements, in inches:
#
#   dz      z_mid - z_front. Negative for a descending pitch.
#   dx      x_mid - x_front, catcher's view, signed as Statcast signs plate_x.
#           Its sign follows vx0, so it moves left- and right-handed pitchers'
#           pitches in opposite directions and the pooled mean hides it.
#   dabsx   |x_mid| - |x_front|: the change in distance from the plate's centre
#           line. This is the displacement that moves the side edge.
#
# Nothing is fitted. No call, no strike indicator and no outcome is read. The
# prereg-v1 tag does not exist yet; this step is mechanical and runs before it.
#
# THE BREAKDOWNS (SOP W3.10: by velocity decile, pitch group and vertical
# break; mean, sd, 5th and 95th percentiles of dz and dx). One row per cell, for
# the pooled population and for each season:
#
#   all             every pitch in the population
#   season          pooled population only
#   velo_decile     release_speed deciles, edges set once on the pooled P0
#   pitch_group     W3.7's four groups: FF, SI/FC, BRK, OFFSP
#   vbreak_decile   vertical-break deciles, edges set once on the pooled P0
#   pitch_type      pooled population only; the dz-by-pitch-type distribution
#                   the SOP publishes as a figure (W3.24 draws it)
#   p_throws        L and R, which shows the sign of dx
#   shadow_edge     pitches in the shadow band, |d| <= 3 in (SOP W3.5), split by
#                   W3.7's nearest edge: side, top, bot. The mean at an edge is
#                   the mean over that edge's own velocity and break mix, which is
#                   the pitch-level form of the per-edge estimand in SOP W3.10.
#                   The 95% interval on the plane component per edge is W3.17's,
#                   from the fit; this table gives no interval
#   shadow_edge_pitch_group
#                   the same shadow band split by edge and pitch group, level
#                   "<edge>:<group>". It separates the pitch mix at an edge from
#                   the location effect within a group: a pitch that crosses high
#                   descends less steeply than the same pitch crossing low
#
# Each decile covers (lo, hi]; the first covers [lo, hi]. release_speed is
# recorded to 0.1 mph, so the decile counts are not exactly equal.
#
# VERTICAL BREAK. The warehouse carries the CSV kinematics and not Statcast's
# pfx_z. vbreak is the induced vertical break computed from them: the vertical
# displacement from spin alone over the flight from y = 50 ft to the front of
# the plate, 12 * 0.5 * (az + g) * t_front^2 inches, g = 32.174 ft/s^2. It is
# not Statcast's pfx_z, which uses Statcast's own flight window.
#
# THE POPULATION. P0 from the W3.7 analysis table (SOP W3.5: every called pitch,
# game_type R, open dates, non-null re-projected coordinates), joined by
# pitch_uid to the kinematics in abs.main_marts.v_called_pitch_open, restricted
# to analysis_set = 'open' in the same statement.
#
# CHECKS, each a PASS/FAIL line:
#   - every P0 pitch joins exactly one open-view row with complete kinematics
#   - reproject() front to middle reproduces the warehouse mid-plate pair (W2.14,
#     the Python twin) to 1e-9 ft, and W3.7's x_mid and z_mid to 1e-9 ft
#   - t_mid > t_front on every pitch
#   - dz < 0 on every pitch that is descending at both planes
#   - mean dz on every 2022-2025 day lies in [-1.10, -0.90] in (SOP W3.3)
#   - every breakdown partitions its population, and the shadow-band rows
#     partition the shadow band
#
# RECORDS, printed and not gated: the pooled rows by pitch group, the
# shadow-band rows by season, and the SOP section 2.5 and W3.10 reference
# values beside the matching cells here. The SOP's five dz values are single
# pitches; the cells here are means over 1-mph bins, so they are compared, not
# asserted.
#
# READS. abs.main_marts.v_called_pitch_open, restricted to analysis_set = 'open'
# in its own statement, on a read-only attach; data/marts/ch1_called.parquet.
#
# WRITES. data/interim/ch1/plane_displacement.csv, and only when its content
# changes, so a second run leaves the file as the first run left it. Check mode
# writes nothing. data/ never enters git (D-03).
#
# Exit 0 when every check passes, 1 otherwise, 2 on a usage error.

options(warn = 1, digits = 12)
invisible(Sys.setlocale("LC_COLLATE", "C"))
t_start <- Sys.time()

args_all <- commandArgs(trailingOnly = FALSE)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) > 1 || (length(args) == 1 && !identical(args, "--check"))) {
  cat("usage: Rscript R/ch1/13_plane_displacement.R [--check]\n", file = stderr())
  quit(status = 2)
}
CHECK_ONLY <- identical(args, "--check")

file_arg <- grep("^--file=", args_all, value = TRUE)
ROOT <- if (length(file_arg) == 1) {
  normalizePath(file.path(dirname(sub("^--file=", "", file_arg)), "..", ".."))
} else {
  normalizePath(getwd())
}
setwd(ROOT)

suppressPackageStartupMessages({
  library(DBI)
  library(duckdb)
  library(arrow)
})

source("R/lib/zone.R")

## --- the harness -------------------------------------------------------------

n_pass <- 0L
failures <- character(0)
check <- function(label, ok, detail) {
  if (isTRUE(ok)) {
    n_pass <<- n_pass + 1L
    cat(sprintf("PASS   %-46s %s\n", label, detail))
  } else {
    failures <<- c(failures, sprintf("%s -- %s", label, detail))
    cat(sprintf("FAIL   %-46s %s\n", label, detail))
  }
}
record <- function(label, detail) cat(sprintf("RECORD %-46s %s\n", label, detail))
comma <- function(x) formatC(as.numeric(x), format = "d", big.mark = ",")
finish <- function() {
  cat(sprintf("W3.10 %s: %d PASS, %d FAIL, %.1f s\n",
              if (CHECK_ONLY) "check" else "build", n_pass, length(failures),
              as.numeric(difftime(Sys.time(), t_start, units = "secs"))))
  if (length(failures) > 0) {
    cat("FAILED CLAUSES:\n", paste0("  ", failures, "\n"), sep = "")
    quit(status = 1)
  }
  quit(status = 0)
}

## --- constants -----------------------------------------------------------------

G_FT_S2     <- 32.174       # gravity, ft/s^2, for the induced vertical break
SHADOW_IN   <- 3.0          # SOP W3.5: the |d| <= 3 in shadow band
DAY_LO_IN   <- -1.10        # SOP W3.3: mean dz on any 2022-2025 MLB day in [-1.10, -0.90]
DAY_HI_IN   <- -0.90
TOL_FT      <- 1e-9         # reproject() against the warehouse and W3.7 coordinates
GROUP_LEVELS <- c("FF", "SI/FC", "BRK", "OFFSP")
EDGE_LEVELS  <- c("side", "top", "bot")
POOLED       <- "2022-2026"

OUT_FILE <- file.path(ROOT, "data", "interim", "ch1", "plane_displacement.csv")

## --- paths from absump.paths -----------------------------------------------------

paths_from_python <- function() {
  code <- paste(
    "from absump.paths import DUCKDB_PATH, LAST_OPEN_DATE, mart",
    "print(DUCKDB_PATH)", "print(LAST_OPEN_DATE)", "print(mart('ch1_called'))", sep = "; "
  )
  out <- suppressWarnings(system2(
    "uv", c("run", "--locked", "python", "-c", shQuote(code)),
    stdout = TRUE, stderr = TRUE
  ))
  status <- attr(out, "status")
  if (is.null(status)) status <- 0L
  if (status != 0L || length(out) < 3L) {
    stop("could not read the layout from absump.paths (exit ", status, "): ",
         paste(out, collapse = " "), call. = FALSE)
  }
  n <- length(out)
  list(duckdb = trimws(out[n - 2L]), last_open = as.Date(trimws(out[n - 1L])),
       mart = trimws(out[n]))
}
lay <- paths_from_python()
record("layout", sprintf("warehouse %s; last open day %s; analysis table %s",
                         lay$duckdb, format(lay$last_open), lay$mart))

for (f in c(lay$duckdb, lay$mart)) check("input present", file.exists(f), f)
if (CHECK_ONLY) check("table present for comparison", file.exists(OUT_FILE), OUT_FILE)
if (length(failures) > 0) finish()

## --- 1. P0 from the analysis table, W3.7 --------------------------------------------

p0 <- as.data.frame(arrow::read_parquet(
  lay$mart, col_select = c("pitch_uid", "official_date", "season", "pitch_type", "pitch_group",
                           "velo", "p_throws", "x_mid", "z_mid", "d", "edge")))
p0 <- p0[order(p0$pitch_uid), ]
rownames(p0) <- NULL
p0$official_date <- as.Date(p0$official_date)
p0$pitch_group <- as.character(p0$pitch_group)
p0$edge <- as.character(p0$edge)
p0$p_throws <- as.character(p0$p_throws)
N <- nrow(p0)
record("P0 read", sprintf("%s pitches, seasons %s, %s to %s", comma(N),
                          paste(sort(unique(p0$season)), collapse = " "),
                          format(min(p0$official_date)), format(max(p0$official_date))))
check("P0 keys unique and complete", N > 0 && !anyNA(p0$pitch_uid) && !anyDuplicated(p0$pitch_uid) &&
        max(p0$official_date) <= lay$last_open,
      sprintf("%s distinct pitch_uid, last day %s <= last open day %s", comma(length(unique(p0$pitch_uid))),
              format(max(p0$official_date)), format(lay$last_open)))
check("P0 bins present", !anyNA(p0$velo) && all(p0$pitch_group %in% GROUP_LEVELS) &&
        all(p0$edge %in% EDGE_LEVELS) && !anyNA(p0$d) && all(p0$p_throws %in% c("L", "R")),
      "velo, pitch_group, edge, d and p_throws on every row")
if (length(failures) > 0) finish()

## --- 2. kinematics from the open view --------------------------------------------

con <- suppressMessages(DBI::dbConnect(duckdb::duckdb(), dbdir = ":memory:"))
attached <- FALSE
for (attempt in 1:30) {
  attached <- tryCatch({
    DBI::dbExecute(con, sprintf("ATTACH %s AS abs (READ_ONLY)",
                                DBI::dbQuoteString(con, lay$duckdb)))
    TRUE
  }, error = function(e) {
    cat(sprintf("RECORD warehouse attach attempt %d failed: %s\n", attempt, conditionMessage(e)))
    FALSE
  })
  if (attached) break
  Sys.sleep(2)
}
check("warehouse attached read-only", attached, lay$duckdb)
if (!attached) finish()

kin <- DBI::dbGetQuery(con, "
  SELECT p.pitch_uid, p.level, p.game_type, p.plane_source, p.release_speed,
         p.plate_x_front, p.plate_z_front, p.plate_x_mid, p.plate_z_mid,
         p.vx0, p.vy0, p.vz0, p.ax, p.ay, p.az
  FROM abs.main_marts.v_called_pitch_open AS p
  WHERE p.analysis_set = 'open' AND p.level = 'mlb' AND p.plate_x_mid IS NOT NULL
  ORDER BY p.pitch_uid")
try(DBI::dbDisconnect(con, shutdown = TRUE), silent = TRUE)

k_idx <- match(p0$pitch_uid, kin$pitch_uid)
check("every P0 pitch joins the open view once",
      !anyNA(k_idx) && !anyDuplicated(kin$pitch_uid),
      sprintf("%s P0 pitches, %d not found, %d duplicate pitch_uid in %s open-view rows",
              comma(N), sum(is.na(k_idx)), sum(duplicated(kin$pitch_uid)), comma(nrow(kin))))
if (length(failures) > 0) finish()
k <- kin[k_idx, ]
rownames(k) <- NULL
rm(kin)

KCOLS <- c("plate_x_front", "plate_z_front", "plate_x_mid", "plate_z_mid",
           "vx0", "vy0", "vz0", "ax", "ay", "az", "release_speed")
n_na <- vapply(KCOLS, function(cc) sum(is.na(k[[cc]])), integer(1))
check("kinematics complete", all(n_na == 0L) && all(k$game_type %in% "R"),
      sprintf("%d missing values over %d columns; game_type R on every row", sum(n_na), length(KCOLS)))
check("velo is release_speed", identical(p0$velo, k$release_speed),
      sprintf("%s rows", comma(N)))
check("vy0 < 0 and ay > 0 on every pitch", all(k$vy0 < 0) && all(k$ay > 0),
      sprintf("max vy0 %.3f ft/s, min ay %.3f ft/s^2", max(k$vy0), min(k$ay)))
if (length(failures) > 0) finish()
record("plane_source", paste(sprintf("%s %s", names(table(k$plane_source)), comma(table(k$plane_source))),
                             collapse = ", "))

## --- 3. the displacements --------------------------------------------------------

rp <- reproject(k$plate_x_front, k$plate_z_front, k$vx0, k$vy0, k$vz0, k$ax, k$ay, k$az,
                Y_FRONT_FT, Y_MID_FT)
err_wh <- max(abs(rp$x - k$plate_x_mid), abs(rp$z - k$plate_z_mid))
check("reproject() equals the warehouse mid-plate pair", err_wh <= TOL_FT,
      sprintf("max |reproject - plate_{x,z}_mid| %.3g ft over %s pitches, bar %.0e ft",
              err_wh, comma(N), TOL_FT))
err_37 <- max(abs(rp$x - p0$x_mid), abs(rp$z - p0$z_mid))
check("reproject() equals W3.7 x_mid and z_mid", err_37 <= TOL_FT,
      sprintf("max |reproject - {x,z}_mid| %.3g ft, bar %.0e ft", err_37, TOL_FT))

t_front <- t_at_y(Y_FRONT_FT, k$vy0, k$ay)
t_mid   <- t_at_y(Y_MID_FT, k$vy0, k$ay)
check("t_mid > t_front on every pitch", all(t_mid > t_front),
      sprintf("min t_mid - t_front %.6f s", min(t_mid - t_front)))

dz    <- (rp$z - k$plate_z_front) * 12
dx    <- (rp$x - k$plate_x_front) * 12
dabsx <- (abs(rp$x) - abs(k$plate_x_front)) * 12
vbreak <- 12 * 0.5 * (k$az + G_FT_S2) * t_front^2
velo  <- p0$velo

desc <- (k$vz0 + k$az * t_front < 0) & (k$vz0 + k$az * t_mid < 0)
check("dz < 0 on every pitch descending at both planes", all(dz[desc] < 0),
      sprintf("%s descending pitches, %d with dz >= 0; %d pitches not descending at both planes",
              comma(sum(desc)), sum(dz[desc] >= 0), sum(!desc)))

pre26 <- p0$season <= 2025L
day_mean <- tapply(dz[pre26], p0$official_date[pre26], mean)
check("mean dz on every 2022-2025 day in [-1.10, -0.90] in",
      length(day_mean) > 0 && all(day_mean >= DAY_LO_IN & day_mean <= DAY_HI_IN),
      sprintf("%d days, %d outside, range %.4f to %.4f in", length(day_mean),
              sum(day_mean < DAY_LO_IN | day_mean > DAY_HI_IN), min(day_mean), max(day_mean)))
if (length(failures) > 0) finish()

## --- 4. the bins --------------------------------------------------------------------

decile_edges <- function(v) quantile(v, probs = seq(0, 1, 0.1), type = 7, names = FALSE)
decile_of <- function(v, q) findInterval(v, q[2:10], left.open = TRUE) + 1L
q_velo <- decile_edges(velo)
q_vb   <- decile_edges(vbreak)
velo_dec <- decile_of(velo, q_velo)
vb_dec   <- decile_of(vbreak, q_vb)
record("velo decile edges, mph", paste(sprintf("%.1f", q_velo), collapse = " "))
record("vbreak decile edges, in", paste(sprintf("%.2f", q_vb), collapse = " "))
shadow <- abs(p0$d) <= SHADOW_IN
EDGE_GROUP_LEVELS <- as.vector(t(outer(EDGE_LEVELS, GROUP_LEVELS, paste, sep = ":")))
edge_group <- paste(p0$edge, p0$pitch_group, sep = ":")

## --- 5. the table -------------------------------------------------------------------

f4 <- function(x) sprintf("%.4f", x)
stats_row <- function(i) {
  q <- function(v, p) quantile(v[i], p, type = 7, names = FALSE)
  c(n = as.character(length(i)),
    dz_mean_in = f4(mean(dz[i])), dz_sd_in = f4(sd(dz[i])),
    dz_p05_in = f4(q(dz, 0.05)), dz_p95_in = f4(q(dz, 0.95)),
    dx_mean_in = f4(mean(dx[i])), dx_sd_in = f4(sd(dx[i])),
    dx_p05_in = f4(q(dx, 0.05)), dx_p95_in = f4(q(dx, 0.95)),
    dabsx_mean_in = f4(mean(dabsx[i])), dabsx_sd_in = f4(sd(dabsx[i])),
    dabsx_p05_in = f4(q(dabsx, 0.05)), dabsx_p95_in = f4(q(dabsx, 0.95)),
    velo_mean_mph = f4(mean(velo[i])), vbreak_mean_in = f4(mean(vbreak[i])))
}
rows <- list()
add_rows <- function(pop, breakdown, idx, key, levels, lo = NULL, hi = NULL) {
  parts <- split(idx, factor(key[idx], levels = levels))
  for (j in seq_along(levels)) {
    i <- parts[[j]]
    if (length(i) == 0L) next
    rows[[length(rows) + 1L]] <<- c(population = pop, breakdown = breakdown, level = as.character(levels[j]),
                                    lo = if (is.null(lo)) "" else lo[j],
                                    hi = if (is.null(hi)) "" else hi[j], stats_row(i))
  }
  sum(lengths(parts))
}
dec_lo <- function(q) sprintf("%.2f", q[1:10])
dec_hi <- function(q) sprintf("%.2f", q[2:11])
all_key <- rep("all", N)
seasons <- sort(unique(p0$season))
types <- sort(unique(p0$pitch_type))
parts_ok <- TRUE
for (pop in c(POOLED, as.character(seasons))) {
  idx <- if (pop == POOLED) seq_len(N) else which(p0$season == as.integer(pop))
  n_pop <- length(idx)
  got <- c(add_rows(pop, "all", idx, all_key, "all"),
           if (pop == POOLED) add_rows(pop, "season", idx, p0$season, seasons),
           add_rows(pop, "velo_decile", idx, velo_dec, 1:10, dec_lo(q_velo), dec_hi(q_velo)),
           add_rows(pop, "pitch_group", idx, p0$pitch_group, GROUP_LEVELS),
           add_rows(pop, "vbreak_decile", idx, vb_dec, 1:10, dec_lo(q_vb), dec_hi(q_vb)),
           if (pop == POOLED) add_rows(pop, "pitch_type", idx, p0$pitch_type, types),
           add_rows(pop, "p_throws", idx, p0$p_throws, c("L", "R")))
  sh <- idx[shadow[idx]]
  got_sh <- c(add_rows(pop, "shadow_edge", sh, p0$edge, EDGE_LEVELS),
              add_rows(pop, "shadow_edge_pitch_group", sh, edge_group, EDGE_GROUP_LEVELS))
  parts_ok <- parts_ok && all(got == n_pop) && all(got_sh == length(sh))
}
tab <- as.data.frame(do.call(rbind, rows), stringsAsFactors = FALSE)
check("every breakdown partitions its population", parts_ok,
      sprintf("%d rows over %d populations; shadow band %s of %s pooled pitches",
              nrow(tab), length(seasons) + 1L, comma(sum(shadow)), comma(N)))

## --- 6. records ------------------------------------------------------------------------

show <- function(pop, breakdown) {
  s <- tab[tab$population == pop & tab$breakdown == breakdown, ]
  for (r in seq_len(nrow(s))) {
    record(sprintf("%s %s %s", pop, breakdown, s$level[r]),
           sprintf("n %s; dz mean %s sd %s p05 %s p95 %s; dabsx mean %s; velo %s; vbreak %s",
                   comma(s$n[r]), s$dz_mean_in[r], s$dz_sd_in[r], s$dz_p05_in[r], s$dz_p95_in[r],
                   s$dabsx_mean_in[r], s$velo_mean_mph[r], s$vbreak_mean_in[r]))
  }
}
show(POOLED, "all")
show(POOLED, "pitch_group")
show(POOLED, "p_throws")
for (pop in c(POOLED, as.character(seasons))) show(pop, "shadow_edge")

top_bot <- tab[tab$breakdown == "shadow_edge" & tab$level %in% c("top", "bot"), ]
for (pop in c(POOLED, as.character(seasons))) {
  tz <- as.numeric(top_bot$dz_mean_in[top_bot$population == pop & top_bot$level == "top"])
  bz <- as.numeric(top_bot$dz_mean_in[top_bot$population == pop & top_bot$level == "bot"])
  record(sprintf("%s shadow top minus bot", pop),
         sprintf("dz %.4f - (%.4f) = %+.4f in", tz, bz, tz - bz))
}

# The pitch-group mix at each edge, as shares of the shadow-band pitches there.
sg <- tab[tab$breakdown == "shadow_edge_pitch_group", ]
for (pop in c(POOLED, "2025")) {
  for (e in EDGE_LEVELS) {
    s <- sg[sg$population == pop & startsWith(sg$level, paste0(e, ":")), ]
    ne <- sum(as.integer(s$n))
    record(sprintf("%s shadow %s mix and dz", pop, e),
           paste(sprintf("%s %.1f%% dz %s", sub("^[a-z]+:", "", s$level), 100 * as.integer(s$n) / ne,
                         s$dz_mean_in), collapse = "; "))
  }
}

# SOP W3.10: five single-pitch dz values. Compared with the mean over P0
# 2022-2025 in the matching pitch type and 1-mph bin.
ref <- data.frame(label = c("FF 96 mph", "FF 94 mph", "SL 85 mph", "CU 78 mph", "CU 72 mph"),
                  type = c("FF", "FF", "SL", "CU", "CU"), mph = c(96, 94, 85, 78, 72),
                  sop = c(-0.425, -0.909, -1.451, -2.015, -2.583), stringsAsFactors = FALSE)
for (r in seq_len(nrow(ref))) {
  i <- which(pre26 & p0$pitch_type == ref$type[r] & velo > ref$mph[r] - 0.5 & velo <= ref$mph[r] + 0.5)
  record(sprintf("SOP W3.10 %s", ref$label[r]),
         sprintf("SOP single pitch %.3f in; P0 2022-2025 %s in (%.1f, %.1f] mph: n %s, mean %.3f, median %.3f in",
                 ref$sop[r], ref$type[r], ref$mph[r] - 0.5, ref$mph[r] + 0.5, comma(length(i)),
                 if (length(i)) mean(dz[i]) else NA_real_, if (length(i)) median(dz[i]) else NA_real_))
}
# SOP section 2.5: two whole called-pitch days.
for (dd in c("2024-09-15", "2025-09-15")) {
  i <- which(p0$official_date == as.Date(dd))
  record(sprintf("SOP 2.5 day %s", dd),
         sprintf("P0 n %s, dz mean %.3f sd %.3f, range %.2f to %.2f in", comma(length(i)),
                 mean(dz[i]), sd(dz[i]), min(dz[i]), max(dz[i])))
}
record("SOP 2.5 reference", "2025-09-15 n 1,438 mean -0.997 sd 0.313 range -2.19 to -0.26; 2024-09-15 n 2,235 mean -0.975 sd 0.301")

## --- 7. write or compare ---------------------------------------------------------

tc <- textConnection("csv_lines", "w", local = TRUE)
utils::write.csv(tab, tc, row.names = FALSE, na = "")
close(tc)
csv_text <- paste0(paste(csv_lines, collapse = "\n"), "\n")

if (CHECK_ONLY) {
  on_disk <- paste0(paste(readLines(OUT_FILE, warn = FALSE), collapse = "\n"), "\n")
  check("table on disk equals the rebuild", identical(on_disk, csv_text),
        sprintf("%s, %d rows", OUT_FILE, nrow(tab)))
} else {
  dir.create(dirname(OUT_FILE), recursive = TRUE, showWarnings = FALSE)
  old <- if (file.exists(OUT_FILE)) paste0(paste(readLines(OUT_FILE, warn = FALSE), collapse = "\n"), "\n") else NA
  if (!identical(old, csv_text)) {
    tmp <- paste0(OUT_FILE, ".tmp")
    writeLines(csv_lines, tmp)
    file.rename(tmp, OUT_FILE)
    record("table written", sprintf("%s, %d rows", OUT_FILE, nrow(tab)))
  } else {
    record("table unchanged", sprintf("%s, %d rows, content identical", OUT_FILE, nrow(tab)))
  }
}

finish()
