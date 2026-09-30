#!/usr/bin/env bash
# ops/run_sensitivity_grid.sh - SOP W3.22, the Chapter 1 sensitivity grid, one cell per process.
#
#   bash ops/run_sensitivity_grid.sh                       the whole grid on the real analysis table
#   bash ops/run_sensitivity_grid.sh --cells primary,shadow_2 --no-bam --no-summary
#                                                          a subset, the smoke test
#   --table <parquet> --out <root>                         passed to R/ch1/50_sensitivity.R (a
#                                                          synthetic table writes outside the repo)
#
# Detached, as the fleet launches it:
#   nohup bash ops/run_sensitivity_grid.sh > logs/w3_22_grid.log 2>&1 & echo $! > logs/w3_22_grid.pid
#
# THE ORDER.
#   1. binned: the primary and every non-primary cell, one Rscript each, at most CH1_BIN_PAR at
#      once (default 4, never more: a binned cell loads the 1.8M-row table, about 1.5 GB). Cells
#      that exit non-zero get one more try after a minute (a warehouse write lock or an origin
#      timeout in the GD-12 check are the usual causes).
#   2. bam: `--select-bam` ranks the binned cells by how far they move the headline and names the
#      four to refit. The bam primary (W3.15's draws, not refitted) and the four run at most
#      CH1_MAX_PAR at once (default 2, never more: a bam fit on the band peaks at about 5.2 GB,
#      measured 2026-09-30). A cell with 1.3 x the primary's rows, or k x 1.5, runs alone.
#   3. `--summarise`: the sign and interval comparisons, T8, and the CH1-A9 verdict.
# The last line is "W3.22 GRID FINISHED clean" or "W3.22 GRID FINISHED with failures: ...".
#
# RESUMING. Run the same command again. R/ch1/50_sensitivity.R skips a cell whose row in
# out/ch1/tab/sensitivity_grid.csv is "ok" on this table and this code, so only the missing cells
# run. A "deferred" cell (postseason, while the open view holds no postseason pitch) is re-checked
# every pass.
#
# Every Rscript runs single-threaded (bam's nthreads is a no-op on this Mac; the BLAS and Stan
# thread counts are pinned to 1 for determinism) under /usr/bin/time -l, so the log records each
# process's peak resident memory. Every line of the log is stamped with Europe/Madrid time.
#
# Exit 0 clean, 1 a cell or the summary failed, 2 usage.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT" || exit 2

export STAN_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

R_SCRIPT="R/ch1/50_sensitivity.R"
BIN_PAR="${CH1_BIN_PAR:-4}"
BAM_PAR="${CH1_MAX_PAR:-2}"
case "$BIN_PAR$BAM_PAR" in *[!0-9]*) echo "CH1_BIN_PAR and CH1_MAX_PAR take a whole number" >&2; exit 2 ;; esac
[ "$BIN_PAR" -ge 1 ] && [ "$BAM_PAR" -ge 1 ] || { echo "CH1_BIN_PAR and CH1_MAX_PAR must be at least 1" >&2; exit 2; }
[ "$BIN_PAR" -gt 4 ] && { echo "CH1_BIN_PAR=$BIN_PAR capped at 4 (memory)"; BIN_PAR=4; }
[ "$BAM_PAR" -gt 2 ] && { echo "CH1_MAX_PAR=$BAM_PAR capped at 2 (a bam fit peaks at 5.2 GB)"; BAM_PAR=2; }

CELLS=""
NO_BAM=0
NO_SUMMARY=0
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --cells) CELLS="${2:-}"; shift 2 ;;
    --no-bam) NO_BAM=1; shift ;;
    --no-summary) NO_SUMMARY=1; shift ;;
    --table | --out | --height-rule | --calibration) PASS+=("$1" "${2:-}"); shift 2 ;;
    *) echo "usage: ops/run_sensitivity_grid.sh [--cells a,b] [--no-bam] [--no-summary] [--table T --out O]" >&2; exit 2 ;;
  esac
done

stamp() { TZ=Europe/Madrid date -Iseconds; }
say() { echo "$(stamp) $*"; }

RUNDIR="$(mktemp -d "${TMPDIR:-/tmp}/w3_22_grid.XXXXXX")" || exit 2
trap 'rm -rf "$RUNDIR"' EXIT

PIDS=()
alive_count() {
  local n=0 p
  for p in ${PIDS[@]+"${PIDS[@]}"}; do kill -0 "$p" 2>/dev/null && n=$((n + 1)); done
  echo "$n"
}
wait_slots() { while [ "$(alive_count)" -ge "$1" ]; do sleep 5; done; }
wait_all() {
  local p
  for p in ${PIDS[@]+"${PIDS[@]}"}; do wait "$p" 2>/dev/null; done
  PIDS=()
}

# launch LABEL ARGS...: one Rscript in the background, every output line stamped and labelled; its
# exit code lands in $RUNDIR/LABEL.rc.
launch() {
  local label="$1"
  shift
  (
    /usr/bin/time -l Rscript "$R_SCRIPT" ${PASS[@]+"${PASS[@]}"} "$@" 2>&1 |
      perl -MPOSIX -ne 'BEGIN { $| = 1; $ENV{TZ} = "Europe/Madrid"; POSIX::tzset(); $l = shift @ARGV }
                        print strftime("%Y-%m-%dT%H:%M:%S%z ", localtime), "[$l] ", $_' "$label"
    echo "${PIPESTATUS[0]}" > "$RUNDIR/$label.rc"
  ) &
  PIDS+=("$!")
  say "started $label (pid $!)"
}
rc_of() { if [ -f "$RUNDIR/$1.rc" ]; then cat "$RUNDIR/$1.rc"; else echo 99; fi; }

# run_pool PAR ESTIMATOR CELL...: every cell, at most PAR at once; echoes the failed cells.
run_pool() {
  local par="$1" est="$2" c
  shift 2
  for c in "$@"; do
    wait_slots "$par"
    launch "$c.$est" --cells "$c" --estimator "$est"
  done
  wait_all
  FAILED=()
  for c in "$@"; do
    [ "$(rc_of "$c.$est")" = 0 ] || FAILED+=("$c")
  done
}

say "W3.22 grid start: binned at most $BIN_PAR at once, bam at most $BAM_PAR; STAN_NUM_THREADS=$STAN_NUM_THREADS OMP_NUM_THREADS=$OMP_NUM_THREADS; HEAD $(git rev-parse --short HEAD)"

# ---------------------------------------------------------------------------------- 1. binned
if [ -n "$CELLS" ]; then
  BIN_CELLS=($(echo "$CELLS" | tr ',' ' '))
else
  BIN_CELLS=($(Rscript "$R_SCRIPT" --list | awk '$1 == "CELL" { print $2 }'))
fi
[ "${#BIN_CELLS[@]}" -gt 0 ] || { say "W3.22 GRID FINISHED with failures: no cell to run"; exit 1; }
say "binned cells (${#BIN_CELLS[@]}): ${BIN_CELLS[*]}"
# The primary first and alone: the primary-valued cells are written with it.
case " ${BIN_CELLS[*]} " in
  *" primary "*)
    run_pool 1 binned primary
    PRIMARY_FAIL=${#FAILED[@]}
    ;;
  *) PRIMARY_FAIL=0 ;;
esac
REST=()
for c in "${BIN_CELLS[@]}"; do [ "$c" = primary ] || REST+=("$c"); done
BAD=()
[ "$PRIMARY_FAIL" -eq 0 ] || BAD+=(primary)
if [ "${#REST[@]}" -gt 0 ]; then
  run_pool "$BIN_PAR" binned "${REST[@]}"
  BAD+=(${FAILED[@]+"${FAILED[@]}"})
fi
if [ "${#BAD[@]}" -gt 0 ]; then
  say "binned: ${#BAD[@]} cell(s) failed (${BAD[*]}); one more try in 60 s"
  sleep 60
  run_pool "$BIN_PAR" binned "${BAD[@]}"
  BAD=(${FAILED[@]+"${FAILED[@]}"})
fi
FAILS=()
[ "${#BAD[@]}" -eq 0 ] || FAILS+=("binned: ${BAD[*]}")

# ------------------------------------------------------------------------------------- 2. bam
if [ "$NO_BAM" = 0 ]; then
  SEL="$(Rscript "$R_SCRIPT" ${PASS[@]+"${PASS[@]}"} --select-bam 2>&1)"
  src=$?
  echo "$SEL" | sed "s/^/$(stamp) [select-bam] /"
  if [ $src -ne 0 ]; then
    FAILS+=("select-bam exited $src")
  else
    LIGHT=(primary)
    HEAVY=()
    while read -r tag id heavy; do
      [ "$tag" = BAM ] || continue
      if [ "$heavy" = 1 ]; then HEAVY+=("$id"); else LIGHT+=("$id"); fi
    done <<< "$SEL"
    say "bam: light ${LIGHT[*]}; alone ${HEAVY[*]+${HEAVY[*]}}"
    run_pool "$BAM_PAR" bam "${LIGHT[@]}"
    BBAD=(${FAILED[@]+"${FAILED[@]}"})
    for c in ${HEAVY[@]+"${HEAVY[@]}"}; do
      run_pool 1 bam "$c"
      BBAD+=(${FAILED[@]+"${FAILED[@]}"})
    done
    if [ "${#BBAD[@]}" -gt 0 ]; then
      say "bam: ${#BBAD[@]} cell(s) failed (${BBAD[*]}); one more try each, alone, in 60 s"
      sleep 60
      RETRY=("${BBAD[@]}")
      BBAD=()
      for c in "${RETRY[@]}"; do
        run_pool 1 bam "$c"
        BBAD+=(${FAILED[@]+"${FAILED[@]}"})
      done
    fi
    [ "${#BBAD[@]}" -eq 0 ] || FAILS+=("bam: ${BBAD[*]}")
  fi
fi

# ------------------------------------------------------------------------------- 3. the summary
if [ "$NO_SUMMARY" = 0 ]; then
  launch summary --summarise
  wait_all
  [ "$(rc_of summary)" = 0 ] || FAILS+=("summary exited $(rc_of summary)")
fi

if [ "${#FAILS[@]}" -eq 0 ]; then
  say "W3.22 GRID FINISHED clean"
  exit 0
fi
say "W3.22 GRID FINISHED with failures: ${FAILS[*]}"
exit 1
