# tools/comms/export_numbers.R -- SOP W7.24, number traceability. Fleet phase 06 seeds it
# for W6.10; phase 12 owns it from then on.
#
# Writes docs/numbers.json, the one ledger the number gate (quality/check_numbers.py) and
# the abstract filler (tools/comms/fill_slots.R) read. Every entry is carried from a
# committed CSV under out/, with the file and the row it came from. Nothing is typed in.
#
# INPUTS. Every input is optional; the run prints what it read and what was absent.
#   out/tables/abstract_slots_ch1.csv   W6.7, one row per Chapter 1 slot
#   out/tables/abstract_slots_ch2.csv   W6.9, one row per Chapter 2 slot (CH2_*)
#   out/ch1/tab/umpire_eb_summary.csv   W6.8, SD_UMP, REL_UMP and N_UMP
#   out/ch1/tab/T4_decomposition.csv    W3.16, the table1 cells T1_{PRE,BUF,ABS}_*
#   out/ch1/tab/T4_plane_component.csv  W3.17, the table1 cells T1_PLANE_*
#   out/ch1/tab/T1_sample.csv           W3.5, N_CALLED_P0 (row P0) and N_GAMES_P0 (row
#                                       Z_games), column total: the Methods counts
#   out/ch1/tab/T2_zone_gate.csv        W3.8, N_CHAL (row overall, column n)
#   out/ch1/tab/T5_placebos.csv         W3.21, the placebo slots the descriptive variant
#                                       prints: P1_AREA and P1_SHADOW (90% intervals, the
#                                       CH1-A3 test level, with their margins) and
#                                       P2_AREA_MAX, the largest of the five P2 area placebos
#   out/ch1/tab/T3_estimands.csv        W3.15, AREA_2022 to AREA_2026: the fitted area of
#                                       each season's zone (fit main, arm primary); with
#                                       out/ch1/model/estimand_draws_main.csv beside it, also
#                                       the six post-tag exploratory entries of DEV-82
#                                       (DRIFT_2223_AREA, DRIFT_2324_TOP/_BOT/_HW,
#                                       BASE_MEAN_BUF, BASE_2023_BUF), not pre-registered
# The owner-voice variant (abstract/variants/ssac2027_abstract.owner.md, 2026-09-30) also
# prints, from tables already read: D_TOTAL and SHARE_ABS from T4's delta_total and
# share_abs area rows (share_abs is carried as a percentage, 100 times T4's ratio, with the
# ratio kept beside it and the CH1-A9 test on the sum's interval recorded), A_CONV from the
# plane table's published-convention column, and N_CHAL_AGREE from T2's n_agree.
# The Methods counts are P0's, the primary sample (D-R0-02, D-P4-05, DEV-47). The ledger's
# N_CALLED and N_GAMES are W6.4's ABS-measured-cohort counts, which W6.4's --check owns, so
# these are written under their own names and abstract_slots.json maps the slots to them.
#
# GD-12. The first five inputs and T5_placebos.csv are fit results. Outside --synthetic the exporter refuses to
# read any of them unless `git merge-base --is-ancestor <prereg tag> HEAD` succeeds, the
# tag named in config/seal.yml, so no pre-registration-era number reaches the ledger. T1
# and T2 are sample counts and a gate score, committed before the tag, and are not gated.
#
# ORDER. W6.3 writes its feed slots first and W6.4 its join slots last, and each checks
# the ledger byte for byte. A new entry therefore goes in before the first W6.4 entry, so
# an export never moves another generator's bytes.
#
# The three slot files share one layout, the W6.7 contract:
#   slot, point, lo95, hi95, units, estimator, source_csv, source_row
# lo95 and hi95 are empty for a count. The two T4 tables are read by column role:
#   quantity  one of quantity, estimand, edge    (top_in, bot_in, half_width_in, area_sqin)
#   component one of component, term             (g, delta_buffer, delta_abs; T4 only)
#   point     one of point, estimate, est
#   lo95/hi95 one of lo95/lower/lo and hi95/upper/hi
#
# ROUNDING happens here and nowhere else. tools/comms/abstract_slots.json sets digits
# by units and the orientation of each abstract slot. The printed strings go into the
# ledger beside the value, so the gate sees exactly the number the abstract prints.
#
# CARRY-FORWARD. Entries this exporter does not produce (the W6.3 feed slots, the W6.4
# join slots) are kept byte for byte, in place. Output is Python json.dumps(indent=2,
# ensure_ascii=False) plus a newline, the format the W6.3 and W6.4 generators write, so
# their --check stays green after an export.
#
# W6.8's summary may also be one wide row: columns SD_UMP, REL_UMP and N_UMP, each with
# optional <SLOT>_lo95 and <SLOT>_hi95 columns. Both layouts are read.
#
# app/data/*.rds (W7.12, the app's aggregates) is the ledger's second source under SOP
# 2.8. The app is not built during the sprint; the run says whether app/data exists and
# that this exporter does not read it yet. Phase 12 adds that reader with the app.
#
#   Rscript tools/comms/export_numbers.R [--inputs DIR] [--base FILE] [--out FILE]
#                                        [--tag T] [--synthetic] [--check] [--list-inputs]
#
# --inputs DIR reads the CSVs under DIR instead of the repository (the RP-08 cold build
# and the synthetic dry run use it). --tag T reads each input with ".T" before its
# extension, so the dry run's inputs carry SYNTHETIC in their names. --synthetic marks
# every entry, refuses to write docs/numbers.json and refuses to start from it: a
# synthetic ledger starts from an empty --base, so no real entry is carried into it.
# --check regenerates in memory and exits 1 if --out would change. --list-inputs prints
# the input paths, one per line, and exits; ops/coldbuild.sh deletes them in its clone so
# each one has to be rebuilt there.
# Exit 0 written or unchanged, 1 drift under --check, 2 usage or input error, 4 refused
# by GD-12 (a fit-result input exists and HEAD does not descend from the prereg tag).

suppressPackageStartupMessages(library(jsonlite))

script_dir <- function() {
  a <- grep("^--file=", commandArgs(FALSE), value = TRUE)
  normalizePath(dirname(sub("^--file=", "", a[1])))
}
ROOT <- normalizePath(file.path(script_dir(), "..", ".."))

opt <- function(args, name, default = NULL) {
  i <- match(name, args)
  if (is.na(i)) return(default)
  if (i == length(args)) stop("missing value for ", name)
  args[i + 1]
}

# ------------------------------------------------------------------ JSON, Python-shaped

py_num <- function(x) {
  if (!is.finite(x)) stop("non-finite number in the ledger")
  if (x == round(x) && abs(x) < 1e15) return(formatC(x, format = "f", digits = 0))
  for (d in 1:17) {
    s <- sprintf(paste0("%.", d, "g"), x)
    if (as.numeric(s) == x) break
  }
  # Python repr writes a two-digit exponent and no leading zeros beyond that.
  s <- sub("e([+-])0*([0-9]{2,})$", "e\\1\\2", s)
  sub("e([+-])([0-9])$", "e\\10\\2", s)
}

py_str <- function(s) {
  map <- c("\\" = "\\\\", "\"" = "\\\"", "\n" = "\\n", "\r" = "\\r", "\t" = "\\t",
           "\b" = "\\b", "\f" = "\\f")
  ch <- strsplit(enc2utf8(s), "")[[1]]
  out <- vapply(ch, function(c) {
    if (!is.na(map[c])) return(unname(map[c]))
    cp <- utf8ToInt(c)
    if (length(cp) == 1 && cp < 32) return(sprintf("\\u%04x", cp))
    c
  }, "")
  paste0("\"", paste(out, collapse = ""), "\"")
}

py_json <- function(x, ind = 0) {
  pad <- strrep(" ", ind + 2)
  end <- strrep(" ", ind)
  if (is.null(x)) return("null")
  if (is.list(x)) {
    if (length(x) == 0) return(if (is.null(names(x))) "[]" else "{}")
    items <- vapply(seq_along(x), function(i) py_json(x[[i]], ind + 2), "")
    if (is.null(names(x))) {
      return(paste0("[\n", paste0(pad, items, collapse = ",\n"), "\n", end, "]"))
    }
    keys <- vapply(names(x), py_str, "")
    return(paste0("{\n", paste0(pad, keys, ": ", items, collapse = ",\n"), "\n", end, "}"))
  }
  if (length(x) != 1) stop("vectors must be lists before serialising")
  if (is.na(x)) return("null")
  if (is.logical(x)) return(if (x) "true" else "false")
  if (is.numeric(x)) return(py_num(x))
  py_str(as.character(x))
}

# ------------------------------------------------------------------ printing

spec <- fromJSON(file.path(ROOT, "tools", "comms", "abstract_slots.json"), simplifyVector = FALSE)

digits_for <- function(units) {
  d <- spec$digits[[units %||% ""]]
  if (is.null(d)) 2 else d
}
`%||%` <- function(a, b) if (is.null(a) || length(a) == 0 || (length(a) == 1 && is.na(a)) ||
                               identical(a, "")) b else a

fmt <- function(x, d) {
  s <- formatC(round(x, d), format = "f", digits = d, big.mark = if (d == 0) "," else "")
  sub("^-(0(\\.0+)?)$", "\\1", s)
}

# A ledger entry carries print_contraction when the abstract slot of the same name asks
# for it, or when any abstract slot that reads this entry through ledger_slot does
# (A_CORR_LOSS reads A_CORR, A_PUB_LOSS reads A_PUB, HW_BUF_LOSS reads T1_BUF_HW). The
# signed print stays beside it, so the other variants print the entry as before.
CONTRACTION_ENTRIES <- unique(unlist(lapply(names(spec$slots), function(k) {
  s <- spec$slots[[k]]
  if (identical(s$orient, "contraction")) s$ledger_slot %||% k else character()
})))

# An interval is stored under keys that name its level: lo95/hi95, or lo90/hi90 for the
# 90% intervals of the CH1-A3 equivalence tests. A 90% interval is never filed as a 95% one.
print_block <- function(p, lo, hi, d, negate = FALSE, level = 95) {
  if (negate) {
    t <- c(-p, -hi, -lo)
    p <- t[1]; lo <- t[2]; hi <- t[3]
  }
  out <- list()
  if (!is.na(p)) out$point <- fmt(p, d)
  if (!is.na(lo)) out[[paste0("lo", level)]] <- fmt(lo, d)
  if (!is.na(hi)) out[[paste0("hi", level)]] <- fmt(hi, d)
  out
}

make_entry <- function(slot, p, lo, hi, units, what, source, row, step, synthetic,
                       level = 95, extra = list()) {
  d <- spec$slots[[slot]]$digits %||% digits_for(units)
  e <- list(slot = slot, value = p)
  if (!is.na(lo)) e[[paste0("lo", level)]] <- lo
  if (!is.na(hi)) e[[paste0("hi", level)]] <- hi
  for (k in names(extra)) e[[k]] <- extra[[k]]
  e$units <- units %||% NULL
  e$what <- what %||% NULL
  e$source <- source
  e$source_row <- row
  e$produced_by <- step
  e$carried_by <- "W7.24"
  e$print <- print_block(p, lo, hi, d, level = level)
  if (slot %in% CONTRACTION_ENTRIES) {
    e$print_contraction <- print_block(p, lo, hi, d, negate = TRUE, level = level)
  }
  if (synthetic) e$synthetic <- TRUE
  Filter(Negate(is.null), e)
}

# ------------------------------------------------------------------ readers

num <- function(v) suppressWarnings(as.numeric(v))

pick <- function(df, roles) {
  hit <- roles[roles %in% names(df)]
  if (length(hit) == 0) NULL else df[[hit[1]]]
}

# One wide row, SD_UMP, SD_UMP_lo95, SD_UMP_hi95, REL_UMP, ..., to the slot layout.
long_from_wide <- function(df) {
  base <- grep("^[A-Z][A-Z0-9_]*[A-Z0-9]$", names(df), value = TRUE)
  base <- base[!grepl("_(lo95|hi95)$", base)]
  if (nrow(df) != 1 || length(base) == 0) return(NULL)
  col <- function(k) if (k %in% names(df)) df[[k]][1] else NA
  data.frame(slot = base,
             point = vapply(base, function(b) num(col(b)), 0),
             lo95 = vapply(base, function(b) num(col(paste0(b, "_lo95"))), 0),
             hi95 = vapply(base, function(b) num(col(paste0(b, "_hi95"))), 0),
             estimator = vapply(base, function(b) as.character(col(paste0(b, "_estimator"))), ""),
             source_row = 1L, stringsAsFactors = FALSE)
}

read_slots <- function(path, rel, step, synthetic) {
  df <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, na.strings = c("", "NA"))
  if (!"slot" %in% names(df)) df <- long_from_wide(df) %||% df
  if (!all(c("slot", "point") %in% names(df))) {
    stop(rel, ": needs the columns slot and point (the W6.7 contract)")
  }
  lapply(seq_len(nrow(df)), function(i) {
    r <- df[i, , drop = FALSE]
    make_entry(r$slot, num(r$point), num(r$lo95 %||% NA), num(r$hi95 %||% NA),
               r$units %||% spec$slots[[r$slot]]$units %||% NA, r$estimator %||% NA,
               r$source_csv %||% rel, if (is.null(r$source_row) || is.na(r$source_row)) i else r$source_row,
               step, synthetic)
  })
}

QMAP <- c(top = "TOP", bot = "BOT", width = "HW", half = "HW", area = "AREA")
CMAP <- list(PRE = "^(g|pre|pre_trend|pretrend|trend)", BUF = "buf", ABS = "^(delta_)?abs")

read_cells <- function(path, rel, step, synthetic, plane) {
  df <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  q <- pick(df, c("quantity", "estimand", "edge"))
  comp <- if (plane) rep("PLANE", nrow(df)) else pick(df, c("component", "term"))
  p <- num(pick(df, c("point", "estimate", "est")))
  lo <- num(pick(df, c("lo95", "lower", "lo")))
  hi <- num(pick(df, c("hi95", "upper", "hi")))
  if (is.null(q) || is.null(comp) || length(p) == 0) {
    stop(rel, ": needs a quantity column, a component column and a point column")
  }
  out <- list()
  for (i in seq_len(nrow(df))) {
    qk <- QMAP[vapply(names(QMAP), function(k) grepl(k, tolower(q[i])), TRUE)]
    ck <- if (plane) "PLANE" else names(CMAP)[vapply(CMAP, function(rx) {
      grepl(rx, tolower(comp[i])) && !grepl("share|total", tolower(comp[i]))
    }, TRUE)]
    if (length(qk) == 0 || length(ck) == 0) next
    units <- if (qk[1] == "AREA") "sq in" else "in"
    slot <- paste0("T1_", ck[1], "_", qk[1])
    out[[slot]] <- make_entry(slot, p[i], lo[i] %||% NA, hi[i] %||% NA, units,
                              paste(q[i], if (plane) "plane" else comp[i]), rel, i, step, synthetic)
  }
  area <- grepl("area", tolower(q))
  if (!plane) {
    # The owner-voice variant's two extra T4 rows, area only. A T4 without them (the
    # synthetic dry run's) writes neither. The fit and arm columns, where present, keep
    # the read on the main fit's primary arm.
    fit <- pick(df, c("fit")); arm <- pick(df, c("arm"))
    primary <- if (is.null(fit) || is.null(arm)) rep(TRUE, nrow(df)) else (fit == "main" & arm == "primary")
    i_tot <- which(primary & area & comp == "delta_total")
    i_sum <- which(primary & area & comp == "sum_components")
    i_sh <- which(primary & area & comp == "share_abs")
    if (length(i_tot) == 1L) {
      out[["D_TOTAL"]] <- make_entry(
        "D_TOTAL", p[i_tot], lo[i_tot], hi[i_tot], "sq in",
        "delta_total, area: the 2024-to-2026 change in the 50 percent contour's area (delta_buffer + delta_abs + 2 g)",
        rel, i_tot, step, synthetic)
    }
    if (length(i_sh) == 1L && length(i_sum) == 1L) {
      # CH1-A9: share_abs is reported only when the 95% interval on delta_buffer + delta_abs
      # excludes zero. The entry records that test beside the number.
      reportable <- isTRUE(hi[i_sum] < 0) || isTRUE(lo[i_sum] > 0)
      out[["SHARE_ABS"]] <- make_entry(
        "SHARE_ABS", 100 * p[i_sh], 100 * lo[i_sh], 100 * hi[i_sh], "percent",
        paste("share_abs, area: the 2026 step as a percentage of the two steps combined,",
              "delta_abs / (delta_abs + delta_buffer), 100 times T4's ratio (kept as ratio);",
              "CH1-A9 reportable only when the 95% interval on the sum (sum_lo95, sum_hi95) excludes zero"),
        rel, i_sh, step, synthetic,
        extra = list(ratio = p[i_sh], ratio_lo95 = lo[i_sh], ratio_hi95 = hi[i_sh],
                     sum_lo95 = lo[i_sum], sum_hi95 = hi[i_sum], sum_row = i_sum,
                     reportable = reportable))
    }
  } else {
    # The published-convention change, 2025 at the plate front against 2026 at mid-plate,
    # area row. Absent from a plane table without the column (the synthetic dry run's).
    pc <- num(pick(df, c("published_convention_change_point")))
    pl <- num(pick(df, c("published_convention_change_lo95")))
    ph <- num(pick(df, c("published_convention_change_hi95")))
    i_area <- which(area)
    if (length(pc) == nrow(df) && length(pl) == nrow(df) && length(ph) == nrow(df) && length(i_area) == 1L) {
      out[["A_CONV"]] <- make_entry(
        "A_CONV", pc[i_area], pl[i_area], ph[i_area], "sq in",
        paste("2025-to-2026 area change on the published convention, 2025 at the plate front and",
              "2026 at mid-plate; T9_published_comparison.csv row 1 carries the same numbers"),
        rel, i_area, step, synthetic)
    }
  }
  unname(out)
}

# W3.15's T3_estimands.csv: the fitted area of each season's zone, main fit, primary arm.
# With W3.15's committed draws beside it (out/ch1/model/estimand_draws_main.csv), the six
# post-tag exploratory entries below are re-derived too; without them (the synthetic dry run)
# only the five areas are written.
read_t3 <- function(path, rel, step, synthetic, draws = NULL, draws_rel = NULL, t4 = NULL) {
  df <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  need <- c("fit", "arm", "season", "estimand", "point", "lo95", "hi95", "units")
  if (!all(need %in% names(df))) stop(rel, ": needs the columns ", paste(need, collapse = ", "))
  out <- lapply(2022:2026, function(yr) {
    i <- which(df$fit == "main" & df$arm == "primary" & df$estimand == "area_sqin" & df$season == yr)
    if (length(i) != 1L) stop(rel, ": expected one main/primary area_sqin row for ", yr, ", found ", length(i))
    make_entry(paste0("AREA_", yr), num(df$point[i]), num(df$lo95[i]), num(df$hi95[i]), df$units[i],
               paste0("fitted area of the 50 percent contour, ", yr,
                      ", 72-inch batter, 2024 pitch mix, mid-plate"),
               rel, i, step, synthetic)
  })
  if (is.null(draws) || !file.exists(draws)) return(out)
  c(out, read_exploratory(df, rel, draws, draws_rel, t4, step, synthetic))
}

# POST-TAG EXPLORATORY ADDITIONS (docs/DEVIATIONS.md, DEV-82), added 2026-09-30 at an
# external reviewer's request and not pre-registered. They are re-derivations from W3.15's
# committed outputs, not fits: each point is a difference of T3 points (main fit, primary
# arm), and each interval is the type-7 percentile interval of the same difference over the
# 1,000 joint draws, the way W3.21 reads P1 (R/ch1/26_placebos.R). The level is in the key.
#   DRIFT_2223_AREA  area, 2023 minus 2022, 90% (the other old-rule season pair, read as P1 is)
#   DRIFT_2324_TOP, _BOT, _HW  the 2024 minus 2023 edge changes, 95% (P1 by edge)
#   BASE_MEAN_BUF    the 2025 area step against the mean of the 2022-2024 areas plus one
#                    season of the trend g, 95%; g per draw exactly as R/lib/ch1_decomp.R
#   BASE_2023_BUF    the 2025 area step against the 2023 area alone, 95%
EXPLORATORY <- paste("POST-TAG EXPLORATORY ADDITION, not pre-registered: re-derived from W3.15's",
                     "committed T3 points and draws, added after the tag at an external reviewer's",
                     "request; docs/DEVIATIONS.md, DEV-82")

read_exploratory <- function(df, rel, draws, draws_rel, t4, step, synthetic) {
  dr <- utils::read.csv(draws, check.names = FALSE)
  row <- function(yr, q) {
    i <- which(df$fit == "main" & df$arm == "primary" & df$estimand == q & df$season == yr)
    if (length(i) != 1L) stop(rel, ": expected one main/primary ", q, " row for ", yr)
    i
  }
  col <- function(yr, q) {
    k <- paste(yr, q, sep = "_")
    if (!k %in% names(dr)) stop(draws_rel, ": no column ", k)
    num(dr[[k]])
  }
  qint <- function(v, lev) {
    a <- (1 - lev) / 2
    unname(stats::quantile(v[is.finite(v)], c(a, 1 - a), names = FALSE, type = 7))
  }
  entry <- function(slot, p, v, lev, units, what, rows, cols) {
    iv <- qint(v, lev)
    make_entry(slot, p, iv[1], iv[2], units, paste0(what, ". ", EXPLORATORY), rel, rows[length(rows)],
               step, synthetic, level = round(100 * lev),
               extra = list(source_rows = paste0(rel, " rows ", paste(rows, collapse = " and "), "; ",
                                                 draws_rel, " columns ", paste(cols, collapse = ", ")),
                            n_draws = sum(is.finite(v)), not_preregistered = TRUE))
  }
  pair <- function(slot, q, y0, y1, lev, units, what) {
    i0 <- row(y0, q); i1 <- row(y1, q)
    entry(slot, num(df$point[i1]) - num(df$point[i0]), col(y1, q) - col(y0, q), lev, units, what,
          c(i0, i1), paste(c(y0, y1), q, sep = "_"))
  }
  out <- list(
    pair("DRIFT_2223_AREA", "area_sqin", 2022, 2023, 0.90, "sq in",
         "called-zone area, 2023 minus 2022, the other pair of old-rule seasons"),
    pair("DRIFT_2324_TOP", "top_in", 2023, 2024, 0.95, "in", "top edge, 2024 minus 2023 (P1 by edge)"),
    pair("DRIFT_2324_BOT", "bot_in", 2023, 2024, 0.95, "in", "bottom edge, 2024 minus 2023 (P1 by edge)"),
    pair("DRIFT_2324_HW", "half_width_in", 2023, 2024, 0.95, "in", "half-width, 2024 minus 2023 (P1 by edge)")
  )
  # The 2025 area step against two other baselines. g is R/lib/ch1_decomp.R's precision-weighted
  # 2022-2024 slope, weights 1 / var over the draws, applied to the point and to every draw.
  yrs <- 2022:2025
  i_a <- vapply(yrs, row, 0L, q = "area_sqin")
  a <- num(df$point[i_a])
  D <- vapply(yrs, col, numeric(nrow(dr)), q = "area_sqin")
  w <- 1 / apply(D[, 1:3, drop = FALSE], 2, stats::var)
  s <- 2022:2024
  sb <- sum(w * s) / sum(w)
  slope <- function(pre) {
    tb <- as.vector(pre %*% w) / sum(w)
    as.vector((pre - tb) %*% (w * (s - sb))) / sum(w * (s - sb)^2)
  }
  g <- slope(matrix(a[1:3], nrow = 1L))
  gd <- slope(D[, 1:3, drop = FALSE])
  if (!is.null(t4) && file.exists(t4)) {
    t4d <- utils::read.csv(t4, stringsAsFactors = FALSE, check.names = FALSE)
    k <- which(t4d$fit == "main" & t4d$arm == "primary" & t4d$estimand == "area_sqin" & t4d$component == "g")
    if (length(k) == 1L && abs(num(t4d$point[k]) - g) > 1e-9) {
      stop(draws_rel, ": the re-derived g ", g, " is not T4's ", t4d$point[k])
    }
  }
  cols <- paste(yrs, "area_sqin", sep = "_")
  c(out, list(
    entry("BASE_MEAN_BUF", a[4] - (mean(a[1:3]) + g), D[, 4] - (rowMeans(D[, 1:3]) + gd), 0.95, "sq in",
          paste("the 2025 area step against the mean of the 2022-2024 areas plus one season of the",
                "2022-2024 trend g: area 2025 - (mean(area 2022, 2023, 2024) + g)"),
          i_a, cols),
    entry("BASE_2023_BUF", a[4] - a[2], D[, 4] - D[, 2], 0.95, "sq in",
          "the 2025 area step against the 2023 area alone: area 2025 - area 2023",
          i_a[c(2, 4)], cols[c(2, 4)])
  ))
}

# One count from a keyed table: the row whose `key` is `id`, the column `col`. A missing
# row, a missing column or a non-count stops the export: a Methods count is never guessed.
read_count <- function(df, rel, key, id, col, slot, what, step, synthetic) {
  if (!all(c(key, col) %in% names(df))) stop(rel, ": needs the columns ", key, " and ", col)
  i <- which(df[[key]] == id)
  if (length(i) != 1L) stop(rel, ": expected one row with ", key, " = ", id, ", found ", length(i))
  v <- num(df[[col]][i])
  if (!is.finite(v) || v < 0 || v != round(v)) stop(rel, ": ", id, " ", col, " is not a count")
  make_entry(slot, v, NA, NA, "counts", what, rel, i, step, synthetic)
}

# W3.5's T1_sample.csv: P0 and the games behind it, all five seasons.
read_t1 <- function(path, rel, step, synthetic) {
  df <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  list(
    read_count(df, rel, "row_id", "P0", "total", "N_CALLED_P0",
               "P0, the Chapter 1 primary sample: MLB regular-season called pitches, 2022 to 2026-09-21 (D-P4-05)",
               step, synthetic),
    read_count(df, rel, "row_id", "Z_games", "total", "N_GAMES_P0",
               "games with at least one P0 pitch", step, synthetic)
  )
}

# W3.8's T2_zone_gate.csv: the challenged pitches the zone was scored against.
read_t2 <- function(path, rel, step, synthetic) {
  df <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  list(read_count(df, rel, "row_id", "overall", "n", "N_CHAL",
                  "MLB 2026 challenged pitches the zone-truth gate scored, overall row", step, synthetic),
       read_count(df, rel, "row_id", "overall", "n_agree", "N_CHAL_AGREE",
                  "of those, pitches on which the zone agreed with the ABS verdict, overall row", step, synthetic))
}

# W3.21's T5_placebos.csv. CH1-A3 tests P1 with 90% intervals against fixed margins, so
# P1's two entries carry lo90/hi90 and the margin. P2's area row carries the five
# placebos' mean, min and max in estimate, lo and hi; the largest placebo is its hi.
read_t5 <- function(path, rel, step, synthetic) {
  df <- utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
  need <- c("placebo", "quantity", "units", "estimate", "lo", "hi", "margin_or_threshold", "verdict")
  if (!all(need %in% names(df))) stop(rel, ": needs the columns ", paste(need, collapse = ", "))
  row <- function(pl, rx) {
    i <- which(df$placebo == pl & grepl(rx, df$quantity))
    if (length(i) != 1L) stop(rel, ": expected one ", pl, " row matching ", rx, ", found ", length(i))
    i
  }
  p1 <- function(slot, rx, what) {
    i <- row("P1", rx)
    make_entry(slot, num(df$estimate[i]), num(df$lo[i]), num(df$hi[i]), df$units[i],
               paste0(what, "; CH1-A3 verdict ", df$verdict[i]), rel, i, step, synthetic,
               level = 90, extra = list(margin = num(df$margin_or_threshold[i])))
  }
  i2 <- row("P2", "^area_sqin")
  list(
    p1("P1_AREA", "^area_sqin", "P1, called-zone area, 2024 minus 2023, two seasons under one rule"),
    p1("P1_SHADOW", "^shadow_rate", "P1, shadow-band called-strike rate, 2024 minus 2023"),
    make_entry("P2_AREA_MAX", num(df$hi[i2]), NA, NA, df$units[i2],
               paste0("P2, the largest of the five All-Star-break area placebos, one per season ",
                      "2022 to 2026; verdict ", df$verdict[i2]),
               rel, i2, step, synthetic,
               extra = list(threshold_p95 = num(df$margin_or_threshold[i2])))
  )
}

# ------------------------------------------------------------------ GD-12

prereg_tag <- function() {
  l <- grep("^prereg_tag:", readLines(file.path(ROOT, "config", "seal.yml"), warn = FALSE), value = TRUE)
  if (length(l) != 1L) stop("config/seal.yml names no prereg_tag")
  gsub('[" ]', "", sub("#.*$", "", sub("^prereg_tag:", "", l)))
}

# `git merge-base --is-ancestor <tag> HEAD` must exit 0, as in R/lib/ch1_fits.R.
gd12_ancestry <- function() {
  tag <- prereg_tag()
  st <- suppressWarnings(system2("git", c("-C", shQuote(ROOT), "merge-base", "--is-ancestor",
                                          shQuote(tag), "HEAD"), stdout = FALSE, stderr = FALSE))
  list(ok = identical(as.integer(st), 0L), tag = tag, status = as.integer(st))
}

# ------------------------------------------------------------------ main

# W3.15's committed draws, read beside T3 (not a SOURCES entry of its own: the cold build
# rebuilds it with T3, and the dry run has neither). Only the post-tag exploratory entries
# read it (read_exploratory, DEV-82).
DRAWS_T3 <- "out/ch1/model/estimand_draws_main.csv"

# path, producing step, reader kind, fit result (gated by GD-12)
SOURCES <- list(
  list("out/tables/abstract_slots_ch1.csv", "W6.7", "slots", TRUE),
  list("out/tables/abstract_slots_ch2.csv", "W6.9", "slots", TRUE),
  list("out/ch1/tab/umpire_eb_summary.csv", "W6.8", "slots", TRUE),
  list("out/ch1/tab/T4_decomposition.csv", "W3.16", "cells", TRUE),
  list("out/ch1/tab/T4_plane_component.csv", "W3.17", "plane", TRUE),
  list("out/ch1/tab/T1_sample.csv", "W3.5", "t1", FALSE),
  list("out/ch1/tab/T2_zone_gate.csv", "W3.8", "t2", FALSE),
  list("out/ch1/tab/T5_placebos.csv", "W3.21", "t5", TRUE),
  list("out/ch1/tab/T3_estimands.csv", "W3.15", "t3", TRUE)
)

main <- function(args) {
  if ("--list-inputs" %in% args) {
    cat(vapply(SOURCES, `[[`, "", 1), sep = "\n")
    return(0L)
  }
  inputs <- normalizePath(opt(args, "--inputs", ROOT), mustWork = TRUE)
  base_path <- opt(args, "--base", file.path(ROOT, "docs", "numbers.json"))
  out_path <- opt(args, "--out", base_path)
  synthetic <- "--synthetic" %in% args
  check <- "--check" %in% args
  tag <- opt(args, "--tag", "")
  real_ledger <- normalizePath(file.path(ROOT, "docs", "numbers.json"), mustWork = FALSE)
  if (synthetic && normalizePath(out_path, mustWork = FALSE) == real_ledger) {
    message("export_numbers: --synthetic refuses to write docs/numbers.json")
    return(2L)
  }
  if (synthetic && normalizePath(base_path, mustWork = FALSE) == real_ledger) {
    message("export_numbers: --synthetic refuses to start from docs/numbers.json; pass --base")
    return(2L)
  }
  if (!synthetic && nzchar(tag)) {
    message("export_numbers: --tag names dry-run inputs and needs --synthetic")
    return(2L)
  }
  in_name <- function(p) if (nzchar(tag)) sub("(\\.[a-z]+)$", paste0(".", tag, "\\1"), p) else p
  app <- file.path(inputs, "app", "data")
  cat(sprintf("export_numbers: %s\n", if (dir.exists(app))
    "app/data exists; its *.rds aggregates are not read until phase 12 adds that reader (W7.24)"
    else "absent app/data (W7.12 not built); the ledger is carried from out/ alone"))
  base <- fromJSON(base_path, simplifyVector = FALSE)
  if (!is.list(base$entries)) {
    message("export_numbers: ", base_path, " has no entries list")
    return(2L)
  }
  present <- vapply(SOURCES, function(s) file.exists(file.path(inputs, in_name(s[[1]]))), TRUE)
  fit_inputs <- present & vapply(SOURCES, `[[`, TRUE, 4)
  if (!synthetic && any(fit_inputs)) {
    g <- gd12_ancestry()
    if (!g$ok) {
      message(sprintf(paste0("export_numbers: REFUSED (GD-12): %s exist(s), and `git merge-base ",
                             "--is-ancestor %s HEAD` exited %d. No fit result enters the ledger ",
                             "from a commit that does not descend from the pre-registration tag."),
                      paste(vapply(SOURCES[fit_inputs], `[[`, "", 1), collapse = ", "), g$tag, g$status))
      return(4L)
    }
    cat(sprintf("export_numbers: GD-12 ok, HEAD descends from %s\n", g$tag))
  }
  fresh <- list()
  for (k in seq_along(SOURCES)) {
    s <- SOURCES[[k]]
    path <- file.path(inputs, in_name(s[[1]]))
    if (!present[k]) {
      cat(sprintf("export_numbers: absent %s (%s not run yet)\n", in_name(s[[1]]), s[[2]]))
      next
    }
    got <- switch(s[[3]],
      slots = read_slots(path, in_name(s[[1]]), s[[2]], synthetic),
      t1 = read_t1(path, in_name(s[[1]]), s[[2]], synthetic),
      t2 = read_t2(path, in_name(s[[1]]), s[[2]], synthetic),
      t3 = read_t3(path, in_name(s[[1]]), s[[2]], synthetic,
                   draws = file.path(inputs, in_name(DRAWS_T3)), draws_rel = in_name(DRAWS_T3),
                   t4 = file.path(inputs, in_name("out/ch1/tab/T4_decomposition.csv"))),
      t5 = read_t5(path, in_name(s[[1]]), s[[2]], synthetic),
      read_cells(path, in_name(s[[1]]), s[[2]], synthetic, s[[3]] == "plane"))
    cat(sprintf("export_numbers: read %s, %d entr%s\n", in_name(s[[1]]), length(got),
                if (length(got) == 1) "y" else "ies"))
    for (e in got) fresh[[e$slot]] <- e
  }
  entries <- base$entries
  for (k in names(fresh)) {
    slots <- vapply(entries, function(e) e$slot %||% "", "")
    at <- match(k, slots)
    if (!is.na(at)) {
      entries[[at]] <- fresh[[k]]
      next
    }
    # A new entry goes in before W6.4's join slots, which W6.4 keeps last (ORDER above).
    join <- which(vapply(entries, function(e) identical(e$carried_by, "W6.4"), TRUE))
    at <- if (length(join)) join[1] else length(entries) + 1L
    entries <- append(entries, list(fresh[[k]]), after = at - 1L)
  }
  base$entries <- entries
  if (synthetic) {
    base[["_synthetic"]] <- paste("SYNTHETIC LEDGER. Round numbers for the abstract dry run.",
                                  "No entry is a result. Never copy this file to docs/numbers.json.")
  }
  text <- paste0(py_json(base), "\n")
  old <- if (file.exists(out_path)) paste(readLines(out_path, warn = FALSE, encoding = "UTF-8"), collapse = "\n") else ""
  same <- identical(paste0(old, "\n"), text)
  if (check) {
    cat(sprintf("export_numbers --check: %s %s\n", out_path, if (same) "unchanged" else "WOULD CHANGE"))
    return(if (same) 0L else 1L)
  }
  if (!same) {
    tmp <- paste0(out_path, ".tmp")
    con <- file(tmp, open = "wb")
    writeBin(charToRaw(enc2utf8(text)), con)
    close(con)
    file.rename(tmp, out_path)
  }
  cat(sprintf("export_numbers: %s, %d entries, %d from this run, %s\n", out_path,
              length(entries), length(fresh), if (same) "unchanged" else "written"))
  0L
}

if (sys.nframe() == 0L) {
  status <- tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
    message("export_numbers: ", conditionMessage(e))
    2L
  })
  quit(status = status)
}
