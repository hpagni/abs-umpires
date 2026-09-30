# tools/comms/fill_slots.R -- SOP W6.10. Fills the SSAC abstract template from the ledger.
#
# The template is abstract/ssac2027_abstract.md, the SOP W6 text with slots written <<NAME>>
# and two departures, both listed for the owner in the R1 agenda:
#   1. Results: the SOP's first sentence is 40 words filled, over WR-03, so the pre-trend
#      is its own sentence, "The 2022-to-2024 pre-trend is <<D_PRE>> square inches per
#      year", printed signed because it no longer names the contraction.
#   2. Methods: D-R0-02 makes roster height plus a calibration offset primary in all five
#      seasons, and D-P4-05 and DEV-47 make <<N_CALLED>> report P0. The SOP's "from
#      batters with an ABS-measured height" and "from ABS-measured batter height" describe
#      the robustness arm, so the first is dropped and the second reads "from roster
#      height calibrated to ABS-measured height" (docs/harmonized_zone.md, finding F2).
# D-66 adds two variants under abstract/variants/: null-buffer, for a
# buffer component whose interval covers zero, and sign-reversal, for a plane correction
# that enlarges the published contraction instead of explaining part of it (R-44). Each
# edge keeps its own signed number in all three, so a flipped edge reads correctly.
# Choosing among the three is the owner's result call at review R1, not a rewrite.
# A fourth, descriptive, is for a failed placebo P1 or P2. PREREGISTRATION.md section 8
# and CH1-A3 then make the decomposition descriptive, remove the causal language and make
# the failure the headline finding. The three D-66 variants all say "accounts for", so
# none can carry that case. P1 failed, and DECISIONS.md (2026-09-30, under D-R0-03's
# delegation) records the fourth variant; scripts/abstract.sh fills it by default.
#
# Every number comes from docs/numbers.json, as the string tools/comms/export_numbers.R
# printed there. This script does no arithmetic and no rounding, so the number gate
# (quality/check_numbers.py) finds every printed number in the ledger. How each slot is
# printed is tools/comms/abstract_slots.json, and so is the ledger entry a slot reads when
# the names differ: N_CALLED and N_GAMES print P0's counts, N_CALLED_P0 and N_GAMES_P0
# (D-R0-02, D-P4-05, DEV-47), not W6.4's ABS-measured-cohort N_CALLED and N_GAMES.
#
# CALL and BREAK_YEAR are the owner's. They come only from the owner's file,
# abstract/owner-calls.json, {"CALL": "<one or more sentences>", "BREAK_YEAR": "<year>"}.
# While it is absent they stay as slots, and the word count reserves 25 words for CALL
# and 1 for BREAK_YEAR.
#
# The pre-registration sentence stays the narrow one. The wide one is used only when
# the caller passes --prereg-sentence wide AND --seal-order-ok, which scripts/abstract.sh
# passes only after tools/comms/check_seal_order.sh exits 0 (GD-12, D-67).
#
# The cap is 470 words, counted by the SOP word counter on this markdown as written, so
# the "#" marks count and the pasted text (title, section names, body) is 5 words under.
# Over the cap, the SOP cut ladder is applied in its order and no other: the pre-trend clause, then the reliability clause,
# then the second edge in the plane sentence. Every cut is recorded in the report.
#
#   Rscript tools/comms/fill_slots.R [--ledger F] [--variant main|null-buffer|sign-reversal|descriptive]
#       [--calls F] [--out F] [--report F] [--prereg-sentence narrow|wide] [--seal-order-ok]
#       [--extra-words N]
#
# --extra-words N counts N more words against the cap. scripts/abstract.sh passes the
# inline table's length for the body a form with no upload field receives (SOP W6.12),
# so the cut ladder makes room for the table in that copy and in no other.
#
# Exit 0 filled and within the cap; 1 a non-owner slot has no ledger entry (a reportable
# gap, never a value this script invents); 3 over the cap after every rung; 2 usage.

suppressPackageStartupMessages(library(jsonlite))

script_dir <- function() {
  a <- grep("^--file=", commandArgs(FALSE), value = TRUE)
  normalizePath(dirname(sub("^--file=", "", a[1])))
}
ROOT <- normalizePath(file.path(script_dir(), "..", ".."))
`%||%` <- function(a, b) if (is.null(a) || length(a) == 0 || identical(a, "")) b else a
opt <- function(args, name, default = NULL) {
  i <- match(name, args)
  if (is.na(i)) default else args[i + 1]
}
rp <- function(p) if (grepl("^/", p)) p else file.path(ROOT, p)

NARROW <- paste("The sealed-set definition and acceptance criteria were committed publicly",
                "before the sealed set was opened.")
WIDE <- paste("The analysis plan, acceptance criteria and sealed-set definition were committed",
              "publicly before estimation.")
VARIANTS <- c(main = "abstract/ssac2027_abstract.md",
              "null-buffer" = "abstract/variants/ssac2027_abstract.null-buffer.md",
              "sign-reversal" = "abstract/variants/ssac2027_abstract.sign-reversal.md",
              descriptive = "abstract/variants/ssac2027_abstract.descriptive.md")

# The SOP cut ladder, in order. Each rung is a clause of the filled text.
LADDER <- list(
  list(name = "the pre-trend clause",
       rx = " The 2022-to-2024 pre-trend is [^.]*?(\\.[0-9][^.]*?)*? per year\\.",
       to = ""),
  list(name = "the reliability clause",
       rx = ", split-half reliability [^.]*?(\\.[0-9][^.]*?)*? across [0-9,]+ umpires(?=\\.)",
       to = ""),
  list(name = "the second edge in the plane sentence",
       rx = paste0("(at the top edge) and [^.]*?(\\.[0-9][^.]*?)*? at the bottom(?=\\.)",
                   "|(the top edge by [^,]*? inches) and the bottom edge by [^,]*?(?=,)"),
       to = "\\1\\3")
)

# The SOP counter, len(text.split()), on the markdown as written: the heading marks
# count, so the cap holds on this file and on the pasted text, which is 5 words shorter.
words <- function(md) length(strsplit(trimws(md), "\\s+")[[1]])

render <- function(slot, s, e) {
  if (s$kind == "count") {
    return(formatC(as.numeric(e$value), format = "f", digits = 0, big.mark = ","))
  }
  pr <- if (identical(s$orient, "contraction")) e$print_contraction else e$print
  if (is.null(pr)) stop(slot, ": the ledger entry has no printed form; re-run export_numbers.R")
  if (s$kind == "range") {
    return(paste0(pr$lo95, " to ", pr$hi95, s$suffix %||% ""))
  }
  if (s$kind == "value") {
    if (is.null(pr$point)) stop(slot, ": the ledger entry has no printed point")
    return(paste0(pr$point, s$suffix %||% ""))
  }
  if (s$kind == "estimate90") {
    # CH1-A3's equivalence tests are read on 90% intervals; the level is printed as it is.
    if (is.null(pr$lo90) || is.null(pr$hi90)) stop(slot, ": the ledger entry has no 90% interval")
    return(paste0(pr$point, " (90% CI ", pr$lo90, " to ", pr$hi90, ")", s$suffix %||% ""))
  }
  if (is.null(pr$lo95) || is.null(pr$hi95)) {
    stop(slot, ": an estimate with no 95% interval is not printed (SSAC wants actual results)")
  }
  paste0(pr$point, " (95% CI ", pr$lo95, " to ", pr$hi95, ")", s$suffix %||% "")
}

main <- function(args) {
  variant <- opt(args, "--variant", "main")
  if (is.na(VARIANTS[variant])) {
    message("fill_slots: --variant is one of ", paste(names(VARIANTS), collapse = ", "))
    return(2L)
  }
  template_path <- rp(opt(args, "--template", VARIANTS[[variant]]))
  ledger_path <- rp(opt(args, "--ledger", "docs/numbers.json"))
  calls_path <- rp(opt(args, "--calls", "abstract/owner-calls.json"))
  out_path <- rp(opt(args, "--out", "abstract/ssac2027_abstract.filled.md"))
  report_path <- rp(opt(args, "--report", "out/tables/abstract_fill_report.json"))
  cap <- as.integer(opt(args, "--cap", "470"))
  extra <- as.integer(opt(args, "--extra-words", "0"))
  want_wide <- identical(opt(args, "--prereg-sentence", "narrow"), "wide")
  seal_ok <- "--seal-order-ok" %in% args

  spec <- fromJSON(file.path(ROOT, "tools", "comms", "abstract_slots.json"), simplifyVector = FALSE)
  ledger <- fromJSON(ledger_path, simplifyVector = FALSE)
  by_slot <- list()
  for (e in ledger$entries) if (!is.null(e$slot)) by_slot[[e$slot]] <- e
  calls <- if (file.exists(calls_path)) fromJSON(calls_path, simplifyVector = FALSE) else list()
  text <- paste(readLines(template_path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  found <- unique(regmatches(text, gregexpr("<<[A-Z0-9_]+>>", text))[[1]])

  filled <- character(); missing <- character(); pending <- character(); reserve <- 0L
  printed <- list()
  for (tok in found) {
    slot <- gsub("[<>]", "", tok)
    s <- spec$slots[[slot]]
    if (is.null(s)) {
      missing <- c(missing, slot)
      next
    }
    if (s$kind == "owner") {
      v <- calls[[slot]] %||% ""
      if (!nzchar(trimws(v))) {
        pending <- c(pending, slot)
        reserve <- reserve + as.integer(s$reserve_words) - 1L
        next
      }
      value <- trimws(v)
    } else {
      # ledger_slot: N_CALLED and N_GAMES print P0's counts (abstract_slots.json).
      key <- s$ledger_slot %||% slot
      e <- by_slot[[key]]
      if (is.null(e)) {
        missing <- c(missing, if (identical(key, slot)) slot else paste0(slot, " (ledger ", key, ")"))
        next
      }
      value <- render(slot, s, e)
    }
    text <- gsub(tok, value, text, fixed = TRUE)
    filled <- c(filled, slot)
    printed[[slot]] <- value
  }

  prereg <- "narrow"
  if (want_wide && seal_ok && grepl(NARROW, text, fixed = TRUE)) {
    text <- sub(NARROW, WIDE, text, fixed = TRUE)
    prereg <- "wide"
  } else if (want_wide) {
    message("fill_slots: wide pre-registration sentence refused; GD-12 did not pass in this run")
  }

  count <- words(text) + reserve + extra
  cuts <- list()
  for (rung in LADDER) {
    if (count <= cap) break
    if (!grepl(rung$rx, text, perl = TRUE)) {
      cuts[[length(cuts) + 1]] <- list(rung = rung$name, applied = FALSE,
                                       why = "the clause is not in this text")
      next
    }
    before <- count
    text <- sub(rung$rx, rung$to, text, perl = TRUE)
    count <- words(text) + reserve + extra
    cuts[[length(cuts) + 1]] <- list(rung = rung$name, applied = TRUE, words_saved = before - count)
  }

  dir.create(dirname(out_path), recursive = TRUE, showWarnings = FALSE)
  writeLines(text, out_path, useBytes = TRUE)
  ledger_sha <- unname(tools::md5sum(ledger_path))
  sha256 <- tryCatch(system2("shasum", c("-a", "256", shQuote(ledger_path)), stdout = TRUE),
                     error = function(e) "")
  report <- list(
    variant = variant, template = sub(paste0(ROOT, "/"), "", template_path),
    ledger = sub(paste0(ROOT, "/"), "", ledger_path),
    ledger_sha256 = sub(" .*$", "", sha256[1] %||% ledger_sha),
    out = sub(paste0(ROOT, "/"), "", out_path),
    words_filled = words(text), owner_reserve = reserve, extra_words = extra,
    words_counted = count, cap = cap,
    within_cap = count <= cap, prereg_sentence = prereg,
    filled = as.list(filled), missing = as.list(missing), owner_pending = as.list(pending),
    printed = printed, cuts = cuts
  )
  dir.create(dirname(report_path), recursive = TRUE, showWarnings = FALSE)
  writeLines(toJSON(report, auto_unbox = TRUE, pretty = TRUE), report_path)
  cat(sprintf(paste0("fill_slots: %s variant, %d slot(s) filled, %d missing, %d owner slot(s) ",
                     "pending; %d words (%d written + %d reserved + %d extra) against a cap of %d; ",
                     "%s pre-registration sentence; %d cut(s)\n"),
              variant, length(filled), length(missing), length(pending), count, words(text),
              reserve, extra, cap, prereg, sum(vapply(cuts, function(k) isTRUE(k$applied), TRUE))))
  if (length(missing)) cat("fill_slots: MISSING from the ledger:", paste(missing, collapse = ", "), "\n")
  if (length(pending)) cat("fill_slots: owner slots pending review R1:", paste(pending, collapse = ", "), "\n")
  if (length(missing)) return(1L)
  if (count > cap) return(3L)
  0L
}

if (sys.nframe() == 0L) {
  status <- tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
    message("fill_slots: ", conditionMessage(e))
    2L
  })
  quit(status = status)
}
