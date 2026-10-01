#!/usr/bin/env bash
# scripts/ch1.sh -- `make ch1`: regenerate every Chapter 1 figure and table from the cached fits.
#
# Owner: the closing clause of SOP W3.24 (SOP 9.2: "make ch1 && make test-ch1 regenerates every
# figure and table and exits 0"), fleet phase 08. It replaces W1.14's ABSUMP_PLACEHOLDER stub.
#
#   make ch1                                  from the repository root
#   bash scripts/ch1.sh --write-guard <file>  write the no-fit R profile only (scripts/test_ch1.sh uses it)
#
# WHAT IT RUNS, through W3.24's own entry points and nothing else:
#   1. scripts/figures.sh  R/ch1/70_figures.R --stage all: the compute stage (a cache hit when its
#                          inputs, code and outputs are unchanged) and the render stage, which writes
#                          out/figures/F1..F8 (.png, .pdf), out/tables/F<n>_data.csv, the figure manifest
#   2. scripts/tables.sh   70_figures.R --stage compute (a cache hit after step 1), then
#                          R/ch1/71_tables.R: out/tables/T1..T9, the table manifest, docs/ch1.md
# then prints, from the two manifests, every figure and table and the files this run wrote.
#
# IT NEVER FITS A MODEL. The fits are W3.14's surface, W3.15's draws and W3.18's umpire model,
# cached under out/ch1/model. Two guards:
#   - the preflight below checks every cached fit and upstream table the two R scripts read; a
#     missing one stops the run (exit 2) and names the step that writes it;
#   - every R process started here, children included, loads a profile (R_PROFILE_USER) that first
#     loads what R would have loaded anyway (./.Rprofile, else ~/.Rprofile) and then replaces
#     mgcv's bam, gam and gamm and brms' brm and brm_multiple with a stop(). A cache miss that ever
#     reached a fit fails in seconds instead of holding 5 GB for 3 to 8 minutes (out/ch1/log).
#
# CONCURRENCY. Refuses to start (exit 2) while another R/ch1/70_figures.R or R/ch1/71_tables.R is
# running: both write the same files. One R process at a time; the compute stage peaks near 4.1 GB
# on a cache miss.
#
# EXIT STATUS. 0 every figure and table built, F8 aside while it is pending by design (DEV-90: the
# sealed run, W3.23, runs once after the season, and F8 is a dated pending panel until its receipt
# exists); 3 every buildable one written but a placeholder remains, so SOP 9.2's "exits 0" is not met; 1 a failed check; 2 the preflight refused; 4 GD-12 refused the run; any
# other code is the R process's own.
set -euo pipefail

write_guard() {
  cat > "$1" <<'GUARD'
# No-fit guard written by scripts/ch1.sh. R reads R_PROFILE_USER instead of ./.Rprofile or
# ~/.Rprofile, so this file loads whichever of them R would have loaded, in R's own order.
if (file.exists(".Rprofile")) source(".Rprofile") else if (file.exists("~/.Rprofile")) source("~/.Rprofile")
local({
  arm <- function(pkg, fns) {
    trap <- function(...) {
      ns <- asNamespace(pkg)
      for (f in intersect(fns, ls(ns, all.names = TRUE))) {
        msg <- sprintf(paste0(
          "make ch1 fits no model, and %s::%s was called. A cached fit is missing or stale: ",
          "rerun the step that writes it (W3.14 surfaces, W3.15 draws, W3.18 umpire model) ",
          "on its own, then make ch1 again."), pkg, f)
        stopper <- eval(bquote(function(...) stop(.(msg), call. = FALSE)), baseenv())
        unlockBinding(f, ns); assign(f, stopper, envir = ns); lockBinding(f, ns)
      }
    }
    if (isNamespaceLoaded(pkg)) trap() else setHook(packageEvent(pkg, "onLoad"), trap)
  }
  arm("mgcv", c("bam", "gam", "gamm"))
  arm("brms", c("brm", "brm_multiple"))
})
GUARD
}

if [ "${1:-}" = "--write-guard" ]; then
  [ -n "${2:-}" ] || { echo "usage: bash scripts/ch1.sh --write-guard <file>" >&2; exit 2; }
  write_guard "$2"
  exit 0
fi
[ "$#" -eq 0 ] || { echo "ch1: takes no arguments (got: $*)" >&2; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ -f Makefile ] && [ -f R/ch1/70_figures.R ] && [ -f R/ch1/71_tables.R ] || {
  echo "ch1: $ROOT is not the repository root (no Makefile, R/ch1/70_figures.R or R/ch1/71_tables.R)" >&2
  exit 2
}
export STAN_NUM_THREADS=1 OMP_NUM_THREADS=1

stamp() { TZ=Europe/Madrid date -Iseconds; }
echo "ch1: start $(stamp) in $ROOT (STAN_NUM_THREADS=$STAN_NUM_THREADS OMP_NUM_THREADS=$OMP_NUM_THREADS)"

# --- concurrency ---------------------------------------------------------------------------------
if others="$(pgrep -fl 'R/ch1/7[01]_(figures|tables)\.R' 2>/dev/null)" && [ -n "$others" ]; then
  echo "ch1: REFUSED. Another figures or tables run is live and writes the same files:" >&2
  printf '  %s\n' "$others" >&2
  echo "ch1: wait for it to finish, then run make ch1 again." >&2
  exit 2
fi

# --- preflight: the cached fits and upstream tables, never a fit -------------------------------------
# The owner of each cached fit is its receipt's step (out/models/<fit>/provenance.json).
missing=0
need_fit() {  # need_fit <path> <step> <what>
  if [ ! -s "$1" ]; then
    echo "ch1: CACHE MISS $1 ($3). make ch1 never fits: run $2 on its own first." >&2
    missing=$((missing + 1))
  fi
}
need_fit out/ch1/model/surface_main.rds        W3.14 "the primary bam surface"
need_fit out/ch1/model/draws_vc_main.rds       W3.14 "the primary surface's Vc draws"
need_fit out/models/surface_main/provenance.json W3.14 "the primary surface's receipt"
need_fit out/ch1/model/estimand_draws_main.csv W3.15 "the primary estimand draws"
need_fit out/ch1/model/umpire_me.rds           W3.18 "the umpire response model"

# The step whose receipt lists <path> among its outputs, from out/models/*/provenance.json.
writer_of() {
  local pv s
  for pv in out/models/*/provenance.json; do
    s="$(jq -r --arg p "$1" 'if ((.outputs // {}) | type) == "object" and (.outputs | has($p)) then .step else empty end' "$pv" 2>/dev/null || true)"
    [ -n "$s" ] && printf '%s\n' "$s"
  done | sort -u | paste -sd, -
}
for f in out/ch1/tab/T1_sample.csv out/ch1/tab/T2_zone_gate.csv out/ch1/tab/T3_estimands.csv \
         out/ch1/tab/T4_decomposition.csv out/ch1/tab/T4_plane_component.csv out/ch1/tab/T5_placebos.csv \
         out/ch1/tab/T6_heterogeneity.csv out/ch1/tab/T9_published_comparison.csv \
         out/ch1/tab/framing_catcher_seasons.csv out/ch1/tab/framing_doolittle.csv out/ch1/prose/framing.md; do
  if [ ! -s "$f" ]; then
    w="$(writer_of "$f")"
    echo "ch1: MISSING INPUT $f (written by ${w:-an upstream W3 step}). make ch1 does not run upstream steps." >&2
    missing=$((missing + 1))
  fi
done
if [ "$missing" -gt 0 ]; then
  echo "ch1: REFUSED. $missing cached input(s) missing; nothing was run and nothing was fitted." >&2
  exit 2
fi
echo "ch1: preflight ok: 5 cached fit files and 11 upstream tables present; no model is fitted by this run"

GUARD_FILE="$(mktemp "${TMPDIR:-/tmp}/ch1_nofit.XXXXXX")"
MARK="$(mktemp "${TMPDIR:-/tmp}/ch1_mark.XXXXXX")"  # its mtime is the start line for "written by this run"
REPORT_R="$(mktemp "${TMPDIR:-/tmp}/ch1_report.XXXXXX")"
WRITTEN="$(mktemp "${TMPDIR:-/tmp}/ch1_written.XXXXXX")"
trap 'rm -f "$GUARD_FILE" "$MARK" "$REPORT_R" "$WRITTEN"' EXIT
write_guard "$GUARD_FILE"
export R_PROFILE_USER="$GUARD_FILE"

# --- the run ---------------------------------------------------------------------------------------
rc=0
run_stage() {  # run_stage <name> <script>: runs it, leaves its exit status in rc
  local t0=$SECONDS
  echo "ch1: == $1: bash $2 (start $(stamp))"
  set +e
  bash "$2"
  rc=$?
  set -e
  echo "ch1: == $1: exit $rc after $((SECONDS - t0)) s"
}

run_stage figures scripts/figures.sh
rc_fig=$rc
rc_tab=
case "$rc_fig" in
  0|3) run_stage tables scripts/tables.sh; rc_tab=$rc ;;
  *) echo "ch1: figures failed (exit $rc_fig), so tables did not run: 71_tables.R reads the figure manifest" >&2 ;;
esac

# --- what this run regenerated, from the two manifests ---------------------------------------------
# A file counts as regenerated only if this run wrote it (mtime at or after MARK's).
echo "ch1: == regenerated by this run (a figure: .png, .pdf and sidecar; a table: its CSV)"
cat > "$REPORT_R" <<'REPORT'
mark <- file.mtime(commandArgs(TRUE)[1])
written <- character(0)
fresh <- function(p) {
  ok <- length(p) > 0L && all(nzchar(p)) && all(file.exists(p)) && all(file.mtime(p) >= mark)
  if (ok) written <<- c(written, p)
  ok
}
rd <- function(f) if (file.exists(f)) utils::read.csv(f, stringsAsFactors = FALSE, na.strings = character(0)) else NULL
show <- function(kind, ids, man, idcol, filecols, manifest) {
  ok <- fresh(manifest)
  cat(sprintf("  %s manifest %s: %s\n", kind, manifest, if (ok) "regenerated" else "NOT WRITTEN by this run"))
  n <- 0L; built <- 0L; ph <- character(0); pend <- character(0)
  for (id in ids) {
    r <- if (is.null(man)) NULL else man[man[[idcol]] == id, , drop = FALSE]
    if (is.null(r) || nrow(r) != 1L) { cat(sprintf("  %-3s MISSING from the manifest\n", id)); next }
    files <- unlist(r[filecols], use.names = FALSE)
    w <- fresh(files)
    n <- n + w
    if (identical(r$status, "built")) built <- built + 1L
    else if (identical(r$status, "pending")) pend <- c(pend, id)
    else ph <- c(ph, id)
    note <- c(if (nzchar(r$blocked_by)) paste(if (identical(r$status, "pending")) "pending by design on" else "blocked on",
                                             r$blocked_by),
              if (!is.null(r$pending) && nzchar(r$pending)) paste("a block pending", r$pending))
    cat(sprintf("  %-3s %-11s %-11s %s%s\n", id, r$status, if (w) "regenerated" else "NOT WRITTEN",
                paste(files, collapse = " "), if (length(note)) paste0("  (", paste(note, collapse = "; "), ")") else ""))
  }
  list(n = n, built = built, ph = ph, pend = pend, ok = ok)
}
f <- show("figure", sprintf("F%d", 1:8), rd("out/figures/figures_manifest.csv"), "figure_id",
          c("png", "pdf", "sidecar"), "out/figures/figures_manifest.csv")
t <- show("table", sprintf("T%d", 1:9), rd("out/tables/tables_manifest.csv"), "table_id", "csv",
          "out/tables/tables_manifest.csv")
d <- fresh("docs/ch1.md")
cat(sprintf("  docs/ch1.md %s\n", if (d) "regenerated" else "NOT WRITTEN by this run"))
phs <- function(x) paste0(
  if (length(x$ph)) sprintf(", %d placeholder%s: %s", length(x$ph), if (length(x$ph) > 1L) "s" else "",
                            paste(x$ph, collapse = " ")) else "",
  if (length(x$pend)) sprintf(", pending by design (DEV-90): %s", paste(x$pend, collapse = " ")) else "")
cat(sprintf("ch1: figures %d of 8 regenerated (%d built%s); tables %d of 9 regenerated (%d built%s); docs/ch1.md %s\n",
            f$n, f$built, phs(f), t$n, t$built, phs(t), if (d) "regenerated" else "not regenerated"))
writeLines(unique(written), commandArgs(TRUE)[2])
quit(status = if (f$n == 8L && t$n == 9L && f$ok && t$ok && d) 0L else 1L)
REPORT
set +e
Rscript --vanilla "$REPORT_R" "$MARK" "$WRITTEN"
rc_rep=$?
set -e

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Only the files the report above found regenerated, never another lane's uncommitted edits.
  changed=""
  if [ -s "$WRITTEN" ]; then
    changed="$(tr '\n' '\0' < "$WRITTEN" | xargs -0 git status --short -- 2>/dev/null | grep -v '^??' || true)"
  fi
  if [ -n "$changed" ]; then
    echo "ch1: tracked files this run wrote that now differ from HEAD (W3.24 commits its own outputs;" \
         "this script commits nothing; a .pdf differs by its CreationDate alone when the sidecar is unchanged):"
    printf '%s\n' "$changed" | sed 's/^/  /'
  else
    echo "ch1: every tracked file this run wrote is byte-identical to HEAD"
  fi
fi

# --- exit status -----------------------------------------------------------------------------------
for s in "$rc_fig" "$rc_tab"; do
  case "$s" in
    ''|0|3) ;;
    *) echo "ch1: FAILED at $(stamp) (figures exit $rc_fig, tables exit ${rc_tab:-not run})" >&2; exit "$s" ;;
  esac
done
if [ "$rc_rep" -ne 0 ]; then
  echo "ch1: FAILED at $(stamp): figures exit $rc_fig, tables exit $rc_tab, but a figure, table or docs/ch1.md was not written by this run" >&2
  exit 1
fi
if [ "$rc_fig" -eq 3 ] || [ "$rc_tab" -eq 3 ]; then
  echo "ch1: INCOMPLETE at $(stamp): every buildable figure and table was regenerated, but a placeholder remains" \
       "(figures exit $rc_fig, tables exit $rc_tab). SOP 9.2's exit 0 waits on the steps named above. Exit 3."
  exit 3
fi
echo "ch1: DONE at $(stamp): 8 figures and 9 tables regenerated from cached fits, no placeholder. Exit 0."
exit 0
