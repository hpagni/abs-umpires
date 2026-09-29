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
#                                        [--tag T] [--synthetic] [--check]
#
# --inputs DIR reads the CSVs under DIR instead of the repository (the RP-08 cold build
# and the synthetic dry run use it). --tag T reads each input with ".T" before its
# extension, so the dry run's inputs carry SYNTHETIC in their names. --synthetic marks
# every entry, refuses to write docs/numbers.json and refuses to start from it: a
# synthetic ledger starts from an empty --base, so no real entry is carried into it.
# --check regenerates in memory and exits 1 if --out would change.
# Exit 0 written or unchanged, 1 drift under --check, 2 usage or input error.

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

print_block <- function(p, lo, hi, d, negate = FALSE) {
  if (negate) {
    t <- c(-p, -hi, -lo)
    p <- t[1]; lo <- t[2]; hi <- t[3]
  }
  out <- list()
  if (!is.na(p)) out$point <- fmt(p, d)
  if (!is.na(lo)) out$lo95 <- fmt(lo, d)
  if (!is.na(hi)) out$hi95 <- fmt(hi, d)
  out
}

make_entry <- function(slot, p, lo, hi, units, what, source, row, step, synthetic) {
  d <- spec$slots[[slot]]$digits %||% digits_for(units)
  e <- list(slot = slot, value = p)
  if (!is.na(lo)) e$lo95 <- lo
  if (!is.na(hi)) e$hi95 <- hi
  e$units <- units %||% NULL
  e$what <- what %||% NULL
  e$source <- source
  e$source_row <- row
  e$produced_by <- step
  e$carried_by <- "W7.24"
  e$print <- print_block(p, lo, hi, d)
  s <- spec$slots[[slot]]
  if (!is.null(s) && identical(s$orient, "contraction")) {
    e$print_contraction <- print_block(p, lo, hi, d, negate = TRUE)
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
  unname(out)
}

# ------------------------------------------------------------------ main

main <- function(args) {
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
  sources <- list(
    list("out/tables/abstract_slots_ch1.csv", "W6.7", "slots"),
    list("out/tables/abstract_slots_ch2.csv", "W6.9", "slots"),
    list("out/ch1/tab/umpire_eb_summary.csv", "W6.8", "slots"),
    list("out/ch1/tab/T4_decomposition.csv", "W3.16", "cells"),
    list("out/ch1/tab/T4_plane_component.csv", "W3.17", "plane")
  )
  fresh <- list()
  for (s in sources) {
    path <- file.path(inputs, in_name(s[[1]]))
    if (!file.exists(path)) {
      cat(sprintf("export_numbers: absent %s (%s not run yet)\n", in_name(s[[1]]), s[[2]]))
      next
    }
    got <- if (s[[3]] == "slots") read_slots(path, in_name(s[[1]]), s[[2]], synthetic)
           else read_cells(path, in_name(s[[1]]), s[[2]], synthetic, s[[3]] == "plane")
    cat(sprintf("export_numbers: read %s, %d entr%s\n", in_name(s[[1]]), length(got),
                if (length(got) == 1) "y" else "ies"))
    for (e in got) fresh[[e$slot]] <- e
  }
  entries <- base$entries
  slots <- vapply(entries, function(e) e$slot %||% "", "")
  for (k in names(fresh)) {
    at <- match(k, slots)
    if (is.na(at)) entries[[length(entries) + 1]] <- fresh[[k]] else entries[[at]] <- fresh[[k]]
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
