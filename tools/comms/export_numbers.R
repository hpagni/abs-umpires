#!/usr/bin/env Rscript
# tools/comms/export_numbers.R - the generator of docs/numbers.json (SOP section 3, the number
# gate; quality/check_numbers.py reads the file it writes). The smallest form the fleet's number
# rule allows: it carries the model slots from committed CSVs under out/ and nothing else.
#
#   Rscript tools/comms/export_numbers.R                   regenerate docs/numbers.json
#   Rscript tools/comms/export_numbers.R --check           exit 1 if a regeneration would change it
#   Rscript tools/comms/export_numbers.R --inputs DIR --base FILE --out FILE --synthetic
#
# INPUTS, each optional, read under --inputs (the repository by default), all in the W6.7 slot
# layout (slot, point, lo95, hi95, units, estimator, source_csv, source_row):
#   out/tables/abstract_slots_ch1.csv    W6.7, the Chapter 1 result slots
#   out/ch1/tab/umpire_eb_summary.csv    W6.8, SD_UMP, REL_UMP and N_UMP
#   out/tables/abstract_slots_ch2.csv    W6.9, the Chapter 2 slots, when that step has run
# A row with no point and no interval is an unfilled slot and is not carried.
#
# OUTPUT. One ledger entry per slot: value, lo95, hi95, units, what, source, source_row,
# produced_by, carried_by, and a print block holding each number as the abstract prints it
# (inches and reliabilities to 2 decimals, square inches and points to 1, counts to 0), so the
# gate sees exactly the printed number. Every other entry stays byte for byte where it is. New
# slots go after the W6.3 feed slots and before the W6.4 join slots, the one order both of those
# generators' --check modes accept; the splice and the JSON are Python's json.dumps(indent=2,
# ensure_ascii=False), the format they write.
#
# --synthetic marks every carried entry and refuses to write docs/numbers.json: a dry run writes
# its ledger beside its own outputs. Exit 0 written or unchanged, 1 drift under --check, 2 usage.

ROOT <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", grep("^--file=", a, value = TRUE))
  normalizePath(file.path(dirname(f), "..", ".."))
})
suppressPackageStartupMessages(library(jsonlite))

SOURCES <- list(
  list(path = "out/tables/abstract_slots_ch1.csv", step = "W6.7"),
  list(path = "out/ch1/tab/umpire_eb_summary.csv", step = "W6.8"),
  list(path = "out/tables/abstract_slots_ch2.csv", step = "W6.9"))
DIGITS <- c("in" = 2, "in per season" = 2, "sq in" = 1, "sq in per season" = 1, "pp" = 1, "pct" = 1,
            "reliability" = 2, "correlation" = 2, "counts" = 0)

args <- commandArgs(trailingOnly = TRUE)
opt <- function(name, default = NULL) {
  i <- match(name, args)
  if (is.na(i)) return(default)
  if (i == length(args)) { message("missing value for ", name); quit(status = 2) }
  args[i + 1L]
}
inputs <- normalizePath(opt("--inputs", ROOT), mustWork = TRUE)
base <- opt("--base", file.path(ROOT, "docs", "numbers.json"))
out <- opt("--out", base)
synthetic <- "--synthetic" %in% args
check_only <- "--check" %in% args
real_ledger <- normalizePath(file.path(ROOT, "docs", "numbers.json"), mustWork = FALSE)
if (synthetic && identical(normalizePath(out, mustWork = FALSE), real_ledger)) {
  message("export_numbers: --synthetic refuses to write docs/numbers.json")
  quit(status = 2)
}

num <- function(v) suppressWarnings(as.numeric(v))
printed <- function(x, units) {
  if (!is.finite(x)) return(NULL)
  d <- if (units %in% names(DIGITS)) DIGITS[[units]] else 2
  s <- formatC(round(x, d), format = "f", digits = d)
  sub("^-(0(\\.0+)?)$", "\\1", s)
}

entries <- list()
for (src in SOURCES) {
  f <- file.path(inputs, src$path)
  if (!file.exists(f)) {
    cat(sprintf("export_numbers: absent %s (%s has not run)\n", src$path, src$step))
    next
  }
  df <- utils::read.csv(f, stringsAsFactors = FALSE, check.names = FALSE, na.strings = c("", "NA"))
  need <- c("slot", "point", "lo95", "hi95", "units", "estimator", "source_csv", "source_row")
  miss <- setdiff(need, names(df))
  if (length(miss) > 0L) { message(src$path, " lacks ", paste(miss, collapse = ", ")); quit(status = 2) }
  n <- 0L
  for (i in seq_len(nrow(df))) {
    r <- df[i, ]
    p <- num(r$point); lo <- num(r$lo95); hi <- num(r$hi95)
    if (!is.finite(p) && !is.finite(lo) && !is.finite(hi)) next
    e <- list(slot = r$slot)
    if (is.finite(p)) e$value <- p
    if (is.finite(lo)) e$lo95 <- lo
    if (is.finite(hi)) e$hi95 <- hi
    e$units <- r$units
    e$what <- r$estimator
    e$source <- r$source_csv
    e$source_row <- as.integer(r$source_row)
    e$produced_by <- src$step
    e$carried_by <- "tools/comms/export_numbers.R"
    e$print <- Filter(Negate(is.null), list(value = printed(p, r$units), lo95 = printed(lo, r$units),
                                            hi95 = printed(hi, r$units)))
    if (synthetic) e$synthetic <- TRUE
    entries[[length(entries) + 1L]] <- e
    n <- n + 1L
  }
  cat(sprintf("export_numbers: %s, %d slot(s)\n", src$path, n))
}

tmp <- tempfile(fileext = ".json")
writeLines(toJSON(entries, auto_unbox = TRUE, digits = NA, null = "null"), tmp)
py <- '
import json, sys
base, fresh_path, out, check = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1"
with open(base, encoding="utf-8") as fh:
    data = json.load(fh)
with open(fresh_path, encoding="utf-8") as fh:
    fresh = json.load(fh)
entries = data.get("entries", [])
slots = [e.get("slot") for e in entries]
new = []
for e in fresh:
    if e["slot"] in slots:
        entries[slots.index(e["slot"])] = e
    else:
        new.append(e)
at = next((i for i, e in enumerate(entries) if e.get("carried_by") == "W6.4"), len(entries))
data["entries"] = entries[:at] + new + entries[at:]
data["_model_slots"] = ("The entries carried by tools/comms/export_numbers.R are the model slots, "
                        "from committed CSVs under out/. It regenerates them in place, puts new ones "
                        "after the W6.3 feed slots and before the W6.4 join slots, and leaves every "
                        "other entry alone.")
text = json.dumps(data, indent=2, ensure_ascii=False) + "\\n"
try:
    with open(out, encoding="utf-8") as fh:
        old = fh.read()
except FileNotFoundError:
    old = None
if check:
    print("export_numbers: " + ("unchanged" if old == text else "DRIFT: a regeneration changes " + out))
    sys.exit(0 if old == text else 1)
if old == text:
    print("export_numbers: unchanged " + out)
else:
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("export_numbers: wrote %s, %d model slot(s), %d new" % (out, len(fresh), len(new)))
'
pyf <- tempfile(fileext = ".py")
writeLines(py, pyf)
dir.create(dirname(out), recursive = TRUE, showWarnings = FALSE)
st <- system2("uv", c("run", "--locked", "--project", shQuote(ROOT), "python", shQuote(pyf), shQuote(base),
                      shQuote(tmp), shQuote(out), if (check_only) "1" else "0"))
quit(status = st)
