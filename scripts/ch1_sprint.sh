#!/usr/bin/env bash
# scripts/ch1_sprint.sh - the Chapter 1 post-tag chain, SOP W3.14 to W6.8, in one command.
#
#   scripts/ch1_sprint.sh                   the real run: data/marts/ch1_called.parquet into out/
#   scripts/ch1_sprint.sh dry-run           the same chain on the synthetic table, into a scratch
#                                           directory outside the repository
#   scripts/ch1_sprint.sh status [dry-run]  which steps are done, and which W3.14 and W3.15 fits
#
# Run the real chain in the main tree, after prereg-v1 is cut and pushed and this branch is
# merged, under `caffeinate -i`. It takes about two hours on the M3 Pro.
#
# THE ORDER (logs/prebuild-review-ch1-fits.md, as the review corrected it):
#   W3.14  six fits, one process each: main, undersmooth, abs_cohort, single_offset, panel and
#          binned. At most CH1_MAX_PAR processes at once (default 2: 18 GB of RAM).
#   W3.15  the estimands, one process per fit, at most CH1_EST_PAR at once (default CH1_MAX_PAR)
#   W3.16 beside W3.17
#   W3.18 beside W3.21
#   W6.7, then W6.8
#   dry-run only: R/ch1/29_synthetic_table.R --score, the estimates against the generating truth
#   tests/ch1/check_ch1_outputs.R --out <out> --step all
# Processes that run side by side are joined as `A & p=$!; B; wait $p`, so no step starts before
# everything it reads is written.
#
# RESUMING. Run the same command again after a failure. A step is skipped when its last run
# exited 0 (a marker in <out>/ch1/log/.done/), its outputs exist and are no older than what it
# reads, no step it depends on ran in this call, and its check (tests/ch1/check_ch1_outputs.R
# --step <step>) passes. A step that wrote its outputs and then exited 1 is run again. In W3.14
# and W3.15 each fit is skipped on its own. A step that runs makes every step that reads it run
# too.
#
# PRECONDITIONS, checked before any fit. The script refuses, exit 3, with one line:
#   1. HEAD descends from prereg-v1, and origin carries the tag at the same commit (GD-12, D-67).
#      dry-run skips this one and says so in the first line of its log.
#   2. git status is clean under R/ch1, R/lib and tools/comms, so every receipt names the code.
#   3. the calibration file carries offset_in, offset_noncohort_in and the convention string the
#      fit code applies (R/lib/ch1_fits.R, check_calibration()).
#   4. the analysis table exists and its last official date is on or before
#      absump.paths.LAST_OPEN_DATE, the last open day.
#
# LOGS. <out>/ch1/log/<step>.log for each step and <step>_<fit>.log for each W3.14 and W3.15
# fit, every line stamped with Europe/Madrid time. <out>/ch1/log/ch1_sprint.log is this call's own
# log, rewritten each call. Every Rscript runs under /usr/bin/time -l, so each log records its
# process's peak resident memory, and the summary at the end gives each step's time and peak.
#
# ENVIRONMENT.
#   CH1_MAX_PAR      W3.14 processes at once, default 2
#   CH1_EST_PAR      W3.15 processes at once, default CH1_MAX_PAR
#   CH1_HEIGHT_RULE  "single-offset" only on the owner's override of D-P4-04 (PREREGISTRATION.md
#                    section 14, item 14): every step gets --height-rule single-offset. The
#                    calibration file may keep its D-P4-04 keys.
#   CH1_DRY_DIR      dry-run's scratch directory, default $TMPDIR/ch1_sprint_dry; it must lie
#                    outside the repository, where a synthetic run may not write
#   CH1_DRY_DRAWS    dry-run's draws per fit, default the pre-registered 1,000
#
# Exit 0 done; 1 a step or its check failed; 2 usage; 3 a precondition refused.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT" || exit 2

usage() {
  echo "usage: scripts/ch1_sprint.sh [dry-run | status [dry-run]]" >&2
  exit 2
}

MODE="run"
DRY=0
case "${1:-}" in
  "") ;;
  dry-run) DRY=1 ;;
  status)
    MODE="status"
    case "${2:-}" in "") ;; dry-run) DRY=1 ;; *) usage ;; esac
    ;;
  *) usage ;;
esac

MAX_PAR="${CH1_MAX_PAR:-2}"
EST_PAR="${CH1_EST_PAR:-$MAX_PAR}"
case "$MAX_PAR$EST_PAR" in *[!0-9]*) echo "CH1_MAX_PAR and CH1_EST_PAR take a whole number" >&2; exit 2 ;; esac
[ "$MAX_PAR" -ge 1 ] && [ "$EST_PAR" -ge 1 ] || { echo "CH1_MAX_PAR and CH1_EST_PAR must be at least 1" >&2; exit 2; }

BAM_FITS="main undersmooth abs_cohort single_offset panel"
ALL_FITS="$BAM_FITS binned"
STEPS="W3.14 W3.15 W3.16 W3.17 W3.18 W3.21 W6.7 W6.8"

# ------------------------------------------------------------------ where the run reads and writes
if [ "$DRY" = 1 ]; then
  DRY_DIR="${CH1_DRY_DIR:-${TMPDIR:-/tmp}/ch1_sprint_dry}"
  mkdir -p "$DRY_DIR" || exit 2
  DRY_DIR="$(cd "$DRY_DIR" && pwd -P)"
  case "$DRY_DIR/" in
    "$ROOT"/*) echo "CH1_DRY_DIR $DRY_DIR lies inside the repository; a synthetic run may not write there" >&2; exit 2 ;;
  esac
  SYN="$DRY_DIR/syn"
  TABLE="$SYN/ch1_synth.parquet"
  CAL="$SYN/ch1_synth.calibration.json"
  OUT="$DRY_DIR/run/out"
  SYNFLAG="--synthetic"
else
  TABLE="$(uv run --locked --project "$ROOT" python -c "from absump.paths import mart; print(mart('ch1_called'))" | tail -n 1)"
  CAL="$ROOT/data/interim/dim_batter_season/calibration.json"
  OUT="$ROOT/out"
  SYNFLAG=""
fi
LOG="$OUT/ch1/log"
MODEL="$OUT/ch1/model"
TAB="$OUT/ch1/tab"
MODELS="$OUT/models"

COMMON=(--table "$TABLE" --out "$OUT")
case "${CH1_HEIGHT_RULE:-}" in
  "" | primary) ;;
  single-offset) COMMON+=(--height-rule single-offset) ;;
  *) echo "CH1_HEIGHT_RULE takes single-offset (the owner's override of D-P4-04) or nothing" >&2; exit 2 ;;
esac
DRAWS=()
STAN=()
if [ "$DRY" = 1 ]; then
  [ -n "${CH1_DRY_DRAWS:-}" ] && DRAWS=(--draws "$CH1_DRY_DRAWS")
  STAN=(--stan-chains 2 --stan-warmup 250 --stan-sampling 250)
fi

RUNDIR="$(mktemp -d "${TMPDIR:-/tmp}/ch1_sprint.XXXXXX")" || exit 2
trap 'rm -rf "$RUNDIR"' EXIT

# ------------------------------------------------------------------------------------ logging
madrid() { TZ=Europe/Madrid date '+%Y-%m-%dT%H:%M:%S%z'; }
stamp() {
  perl -MPOSIX -ne 'BEGIN { $| = 1; $ENV{TZ} = "Europe/Madrid"; POSIX::tzset(); }
                    print strftime("%Y-%m-%dT%H:%M:%S%z ", localtime), $_;'
}
SPRINT_LOG=""
say() {
  if [ -n "$SPRINT_LOG" ]; then
    echo "$(madrid) $*" | tee -a "$SPRINT_LOG"
  else
    echo "$(madrid) $*"
  fi
}
stop() { say "STOP: $*"; exit 1; }
refuse() { say "REFUSED: $*"; exit 3; }

# run_r LOG ARGS...: one Rscript, its output and its /usr/bin/time report stamped into LOG. The
# peak resident memory in bytes is appended to $RUNDIR/rss_<log name>. Returns Rscript's exit.
run_r() {
  local log="$1"
  shift
  local tf="$RUNDIR/time.$$.$RANDOM"
  (
    echo "start: Rscript $*"
    [ "$DRY" = 1 ] && echo "DRY RUN: synthetic table $TABLE"
    if [ -x /usr/bin/time ]; then
      /usr/bin/time -l -o "$tf" Rscript "$@" 2>&1
    else
      Rscript "$@" 2>&1
    fi
    rc=$?
    [ -f "$tf" ] && cat "$tf"
    echo "exit $rc"
    exit "$rc"
  ) 2>&1 | stamp >> "$log"
  local rc="${PIPESTATUS[0]}"
  if [ -f "$tf" ]; then
    awk '/maximum resident set size/ { print $1 }' "$tf" >> "$RUNDIR/rss_$(basename "$log" .log)"
    rm -f "$tf"
  fi
  return "$rc"
}

# check_step STEP LOG: the step's verify half; exit 0 when it passes.
check_step() {
  local args=(tests/ch1/check_ch1_outputs.R --out "$OUT" --step "$1")
  [ -n "$SYNFLAG" ] && args+=("$SYNFLAG")
  run_r "$2" "${args[@]}"
}

# The bookkeeping of one call: which steps and fits ran, and each step's seconds.
mark_ran() { touch "$RUNDIR/ran_$1"; }
# The success markers, kept across calls: set when a step or fit exits 0 (and a step's check
# passes), cleared when it starts.
DONE="$LOG/.done"
clear_done() { rm -f "$DONE/$1"; }
set_done() { mkdir -p "$DONE" && echo "$(madrid) $(git rev-parse --short HEAD)" > "$DONE/$1"; }
is_done() { [ -e "$DONE/$1" ]; }
ran() { [ -e "$RUNDIR/ran_$1" ]; }
any_ran() {
  local s
  for s in "$@"; do ran "$s" && return 0; done
  return 1
}
note() { echo "$1|$2|$3" >> "$RUNDIR/summary"; }

# exist FILE...: every file is there
exist() {
  local f
  for f in "$@"; do [ -e "$f" ] || return 1; done
  return 0
}
# not_older "OUTPUTS" "INPUTS": no input is newer than any output
not_older() {
  local o i
  for o in $1; do
    for i in $2; do
      [ -e "$i" ] || continue
      [ "$i" -nt "$o" ] && return 1
    done
  done
  return 0
}

# ------------------------------------------------------------------------- outputs of each step
fit_outputs() {
  if [ "$1" = binned ]; then
    echo "$MODEL/surface_binned.rds $MODELS/surface_binned/provenance.json"
  else
    echo "$MODEL/surface_$1.rds $MODEL/draws_vc_$1.rds $MODELS/surface_$1/provenance.json"
  fi
}
fit_inputs() {
  if [ "$1" = binned ]; then echo "$MODEL/surface_binned.rds"; else echo "$MODEL/draws_vc_$1.rds"; fi
}
est_draws() { echo "$MODEL/estimand_draws_$1.csv"; }
t3_has() { [ -f "$TAB/T3_estimands.csv" ] && grep -q "^\"$1\"," "$TAB/T3_estimands.csv"; }
all_est_draws() {
  local f out=""
  for f in $ALL_FITS; do out="$out $(est_draws "$f")"; done
  echo "$out"
}
step_outputs() {
  case "$1" in
    W3.14) local f out="$MODEL/provenance.json"; for f in $ALL_FITS; do out="$out $(fit_outputs "$f")"; done; echo "$out" ;;
    W3.15) echo "$TAB/T3_estimands.csv $(all_est_draws)" ;;
    W3.16) echo "$TAB/T4_decomposition.csv $TAB/T4_decomposition_arms.csv $OUT/tables/headline.csv $MODELS/ch1_W3_16/provenance.json" ;;
    W3.17) echo "$TAB/T4_plane_component.csv $TAB/T9_published_comparison.csv $OUT/ch1/fig/F_dz_by_pitch_type.csv $OUT/ch1/fig/F_dz_by_pitch_type.png" ;;
    W3.18) echo "$TAB/T6_heterogeneity.csv $TAB/umpire_eb.csv $MODEL/umpire_me.rds" ;;
    W3.21) echo "$TAB/T5_placebos.csv" ;;
    W6.7) echo "$OUT/tables/abstract_slots_ch1.csv" ;;
    W6.8) echo "$TAB/umpire_eb_summary.csv" ;;
    score) echo "$LOG/dryrun_score.csv" ;;
  esac
}
step_inputs() {
  case "$1" in
    W3.16) echo "$TAB/T3_estimands.csv $(all_est_draws)" ;;
    W3.17 | W3.21) echo "$TAB/T3_estimands.csv $(est_draws main)" ;;
    W6.7) echo "$TAB/T4_decomposition.csv $TAB/T4_plane_component.csv $TAB/T9_published_comparison.csv $TAB/T5_placebos.csv $TAB/T2_zone_gate.csv" ;;
    W6.8) echo "$TAB/umpire_eb.csv" ;;
    score) echo "$TAB/T4_decomposition.csv $TAB/T4_decomposition_arms.csv $TAB/T6_heterogeneity.csv" ;;
    *) echo "" ;;
  esac
}
step_deps() {
  case "$1" in
    W3.16 | W3.17 | W3.21) echo "W3.15" ;;
    W6.7) echo "W3.16 W3.17 W3.21" ;;
    W6.8) echo "W3.18" ;;
    score) echo "W3.16 W3.18" ;;
    *) echo "" ;;
  esac
}
step_script() {
  case "$1" in
    W3.16) echo R/ch1/23_decomposition.R ;;
    W3.17) echo R/ch1/24_plane.R ;;
    W3.18) echo R/ch1/25_heterogeneity.R ;;
    W3.21) echo R/ch1/26_placebos.R ;;
    W6.7) echo R/ch1/27_abstract_ch1.R ;;
    W6.8) echo R/ch1/28_umpire_summary.R ;;
    score) echo R/ch1/29_synthetic_table.R ;;
  esac
}
step_args() {
  case "$1" in
    W3.17) echo "${DRAWS[*]+${DRAWS[*]}}" ;;
    W3.18) echo "${STAN[*]+${STAN[*]}}" ;;
    score) echo "--score" ;;
    *) echo "" ;;
  esac
}

# ------------------------------------------------------------------------------- one plain step
# do_step STEP: skip it if it is done, else run it and its check. Returns non-zero on failure.
do_step() {
  local s="$1" log="$LOG/$1.log" t0 rc deps extra
  deps="$(step_deps "$s")"
  # shellcheck disable=SC2046,SC2086
  if [ "$s" != score ] && is_done "$s" && ! any_ran $deps && exist $(step_outputs "$s") &&
    not_older "$(step_outputs "$s")" "$(step_inputs "$s")" && check_step "$s" "$log"; then
    say "$s: done before, skipped (outputs present, check passes)"
    note "$s" skipped 0
    return 0
  fi
  say "$s: running, log $log"
  clear_done "$s"
  t0=$(date +%s)
  extra="$(step_args "$s")"
  # shellcheck disable=SC2086
  run_r "$log" "$(step_script "$s")" "${COMMON[@]}" $extra
  rc=$?
  mark_ran "$s"
  if [ "$rc" -ne 0 ]; then
    note "$s" "FAILED (exit $rc)" $(($(date +%s) - t0))
    say "$s: exit $rc, see $log"
    return 1
  fi
  # The dry-run score has no step in the checker: its own exit is its check.
  if [ "$s" != score ] && ! check_step "$s" "$log"; then
    note "$s" "FAILED its check" $(($(date +%s) - t0))
    say "$s: ran, but its check failed, see $log"
    return 1
  fi
  set_done "$s"
  note "$s" ran $(($(date +%s) - t0))
  say "$s: done in $(($(date +%s) - t0)) s"
  return 0
}

# ------------------------------------------------------------------ W3.14 and W3.15, fit by fit
# fit_cost STEP FIT: the relative cost of one fit, from the dry runs. In W3.14 undersmooth took
# 1.55 times main; in W3.15 it reads the top edge alone.
fit_cost() {
  case "$1:$2" in
    W3.14:undersmooth) echo 15 ;;
    *:main | *:single_offset) echo 10 ;;
    *:abs_cohort) echo 8 ;;
    W3.14:panel) echo 5 ;;
    W3.15:panel) echo 7 ;;
    W3.15:undersmooth) echo 3 ;;
    *) echo 1 ;;
  esac
}
# plan_groups STEP N FIT...: at most N groups, largest first into the lightest group; prints one
# line per group.
plan_groups() {
  local step="$1" n="$2" f g i best
  shift 2
  local loads=() groups=()
  for ((i = 0; i < n; i++)); do loads[i]=0; groups[i]=""; done
  for f in $(for f in "$@"; do echo "$(fit_cost "$step" "$f") $f"; done | sort -rn | awk '{ print $2 }'); do
    best=0
    for ((g = 1; g < n; g++)); do [ "${loads[g]}" -lt "${loads[best]}" ] && best=$g; done
    loads[best]=$((loads[best] + $(fit_cost "$step" "$f")))
    groups[best]="${groups[best]} $f"
  done
  for ((i = 0; i < n; i++)); do [ -n "${groups[i]}" ] && echo "${groups[i]}"; done
  return 0
}
# run_fit_group STEP SCRIPT FIT...: the fits one after another, one process each; stops at the
# first failure.
run_fit_group() {
  local step="$1" script="$2" f rc
  shift 2
  for f in "$@"; do
    say "$step $f: running, log $LOG/${step}_$f.log"
    clear_done "${step}_$f"
    # shellcheck disable=SC2086
    run_r "$LOG/${step}_$f.log" "$script" "${COMMON[@]}" --fits "$f" ${DRAWS[@]+"${DRAWS[@]}"}
    rc=$?
    mark_ran "${step}_$f"
    if [ "$rc" -ne 0 ]; then
      say "$step $f: exit $rc, see $LOG/${step}_$f.log"
      return 1
    fi
    set_done "${step}_$f"
    say "$step $f: done"
  done
  return 0
}
# run_fits STEP SCRIPT PAR FIT...: at most PAR groups at once. Every group but the first runs in
# the background and the first in the foreground; then each background group is waited for.
run_fits() {
  local step="$1" script="$2" par="$3" rc=0 p line first=""
  shift 3
  local pids=()
  [ "$#" -eq 0 ] && return 0
  while read -r line; do
    if [ -z "$first" ]; then
      first="$line"
    else
      # shellcheck disable=SC2086
      run_fit_group "$step" "$script" $line < /dev/null &
      pids+=($!)
    fi
  done <<EOF
$(plan_groups "$step" "$par" "$@")
EOF
  # shellcheck disable=SC2086
  run_fit_group "$step" "$script" $first || rc=1
  for p in ${pids[@]+"${pids[@]}"}; do wait "$p" || rc=1; done
  return "$rc"
}

step_w314() {
  local log="$LOG/W3.14.log" todo="" f t0
  for f in $ALL_FITS; do
    # shellcheck disable=SC2046
    is_done "W3.14_$f" && exist $(fit_outputs "$f") || todo="$todo $f"
  done
  if [ -z "$todo" ] && check_step W3.14 "$log"; then
    say "W3.14: done before, skipped (six fits present, check passes)"
    note W3.14 skipped 0
    return 0
  fi
  [ -z "$todo" ] && todo="$ALL_FITS"
  t0=$(date +%s)
  say "W3.14: fitting$todo in at most $MAX_PAR processes at once"
  # shellcheck disable=SC2086
  run_fits W3.14 R/ch1/20_surfaces.R "$MAX_PAR" $todo || {
    note W3.14 FAILED $(($(date +%s) - t0))
    return 1
  }
  mark_ran W3.14
  check_step W3.14 "$log" || {
    note W3.14 "FAILED its check" $(($(date +%s) - t0))
    say "W3.14: its check failed, see $log"
    return 1
  }
  note W3.14 ran $(($(date +%s) - t0))
  say "W3.14: done in $(($(date +%s) - t0)) s"
}

step_w315() {
  local log="$LOG/W3.15.log" todo="" f t0
  for f in $ALL_FITS; do
    if ran "W3.14_$f" || ! is_done "W3.15_$f" || ! exist "$(est_draws "$f")" ||
      ! not_older "$(est_draws "$f")" "$(fit_inputs "$f")" || ! t3_has "$f"; then
      todo="$todo $f"
    fi
  done
  if [ -z "$todo" ] && check_step W3.15 "$log"; then
    say "W3.15: done before, skipped (six fits present, check passes)"
    note W3.15 skipped 0
    return 0
  fi
  [ -z "$todo" ] && todo="$ALL_FITS"
  t0=$(date +%s)
  say "W3.15: estimands for$todo in at most $EST_PAR processes at once"
  # shellcheck disable=SC2086
  run_fits W3.15 R/ch1/22_estimands.R "$EST_PAR" $todo || {
    note W3.15 FAILED $(($(date +%s) - t0))
    return 1
  }
  mark_ran W3.15
  check_step W3.15 "$log" || {
    note W3.15 "FAILED its check" $(($(date +%s) - t0))
    say "W3.15: its check failed, see $log"
    return 1
  }
  note W3.15 ran $(($(date +%s) - t0))
  say "W3.15: done in $(($(date +%s) - t0)) s"
}

# pair A B: A in the background, B in the foreground, then wait for A.
pair() {
  local rc=0 p
  do_step "$1" &
  p=$!
  do_step "$2" || rc=1
  wait "$p" || rc=1
  return "$rc"
}

# ------------------------------------------------------------------------------- preconditions
preconditions() {
  local tag loc rem peeled dirty pf
  if [ "$DRY" = 0 ]; then
    tag="$(sed -n 's/^prereg_tag:[[:space:]]*"\{0,1\}\([^"#[:space:]]*\).*/\1/p' config/seal.yml | head -n 1)"
    [ -n "$tag" ] || refuse "config/seal.yml names no prereg_tag"
    git merge-base --is-ancestor "$tag" HEAD 2>/dev/null ||
      refuse "HEAD $(git rev-parse --short HEAD) does not descend from $tag (GD-12)"
    loc="$(git rev-parse --verify --quiet "refs/tags/$tag^{commit}")" || refuse "no local tag $tag"
    rem="$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags origin "refs/tags/$tag" "refs/tags/$tag^{}")" ||
      refuse "git ls-remote --tags origin refs/tags/$tag failed; the tag must be on origin before any fit (D-67)"
    peeled="$(echo "$rem" | awk -v r="refs/tags/$tag^{}" '$2 == r { print $1 }')"
    [ -n "$peeled" ] || peeled="$(echo "$rem" | awk -v r="refs/tags/$tag" '$2 == r { print $1 }')"
    [ -n "$peeled" ] || refuse "$tag is not on origin (git ls-remote --tags origin refs/tags/$tag is empty)"
    [ "$peeled" = "$loc" ] || refuse "$tag is on origin at ${peeled:0:12}, not at the local ${loc:0:12}"
    say "precondition 1: HEAD $(git rev-parse --short HEAD) descends from $tag, which origin carries at ${loc:0:12}"
  fi
  dirty="$(git status --porcelain -- R/ch1 R/lib tools/comms)"
  [ -z "$dirty" ] || refuse "the fit code is not committed: $(echo "$dirty" | tr '\n' ';')"
  say "precondition 2: R/ch1, R/lib and tools/comms are clean at $(git rev-parse --short HEAD)"
  pf="$(ABSUMP_ROOT="$ROOT" Rscript -e 'source("R/lib/ch1_fits.R"); a <- commandArgs(TRUE); cat(sprint_preflight(a[1], a[2]), "\n")' \
    "$TABLE" "$CAL" 2>&1)"
  if echo "$pf" | grep -q '^ok: '; then
    say "preconditions 3 and 4: $(echo "$pf" | grep -m 1 '^ok: ' | cut -c 5-)"
  else
    refuse "$(echo "$pf" | tr '\n' ' ' | cut -c 1-600)"
  fi
}

# -------------------------------------------------------------------------------------- status
# step_marked STEP: its last run exited 0; for W3.14 and W3.15, every fit's did.
step_marked() {
  local f
  case "$1" in
    W3.14 | W3.15) for f in $ALL_FITS; do is_done "$1_$f" || return 1; done ;;
    *) is_done "$1" || return 1 ;;
  esac
  return 0
}

status() {
  local s f n have o
  echo "Chapter 1 chain, $([ "$DRY" = 1 ] && echo "dry run in $DRY_DIR" || echo "real run in $OUT")"
  if [ ! -d "$OUT" ]; then echo "  nothing run yet: no $OUT"; return 0; fi
  for s in $STEPS; do
    n=0; have=0
    for o in $(step_outputs "$s"); do n=$((n + 1)); [ -e "$o" ] && have=$((have + 1)); done
    if [ "$have" -eq 0 ]; then
      printf '  %-6s not run\n' "$s"
    elif [ "$have" -lt "$n" ]; then
      printf '  %-6s partial, %d of %d outputs\n' "$s" "$have" "$n"
    elif ! step_marked "$s"; then
      printf '  %-6s outputs present, but its last run did not exit 0\n' "$s"
    elif check_step "$s" "$RUNDIR/status_$s.log" >/dev/null 2>&1; then
      printf '  %-6s done, check passes\n' "$s"
    else
      printf '  %-6s outputs present, check FAILS (%s)\n' "$s" "$(grep -m 1 'FAIL ' "$RUNDIR/status_$s.log" | cut -c 26-120)"
    fi
    if [ "$s" = W3.14 ] || [ "$s" = W3.15 ]; then
      for f in $ALL_FITS; do
        if [ "$s" = W3.14 ]; then
          # shellcheck disable=SC2046
          is_done "W3.14_$f" && exist $(fit_outputs "$f") && printf '           %-14s fitted\n' "$f" || printf '           %-14s not fitted\n' "$f"
        else
          is_done "W3.15_$f" && exist "$(est_draws "$f")" && t3_has "$f" && printf '           %-14s done\n' "$f" || printf '           %-14s not done\n' "$f"
        fi
      done
    fi
  done
}

if [ "$MODE" = status ]; then
  status
  exit 0
fi

# ------------------------------------------------------------------------------------ the run
mkdir -p "$LOG" "$TAB" || exit 2
SPRINT_LOG="$LOG/ch1_sprint.log"
: > "$SPRINT_LOG"
LOCK="$LOG/.ch1_sprint.lock"
mkdir "$LOCK" 2>/dev/null || { echo "another scripts/ch1_sprint.sh holds $LOCK; remove it if no run is live" >&2; exit 2; }
trap 'rm -rf "$RUNDIR" "$LOCK"' EXIT

if [ "$DRY" = 1 ]; then
  say "DRY RUN on the synthetic table, into $OUT: the prereg-v1 preconditions (ancestry, tag on origin) are SKIPPED"
else
  say "REAL RUN on $TABLE, into $OUT, at $(git rev-parse --short HEAD)"
fi
[ -n "${CH1_HEIGHT_RULE:-}" ] && say "CH1_HEIGHT_RULE=$CH1_HEIGHT_RULE: the owner's override of D-P4-04; every step runs --height-rule single-offset"
say "W3.14 at most $MAX_PAR processes at once, W3.15 at most $EST_PAR"

if [ "$DRY" = 1 ]; then
  if [ ! -f "$TABLE" ]; then
    say "making the synthetic table: R/ch1/29_synthetic_table.R --make --scale dry --seed 4290"
    run_r "$LOG/synthetic_table.log" R/ch1/29_synthetic_table.R --make --out "$SYN" --scale dry --seed 4290 ||
      stop "the synthetic generator failed, see $LOG/synthetic_table.log"
  fi
  # W6.7 reads N_CHAL from W3.8's zone-gate table. A dry run gets the synthetic fixture.
  cmp -s tests/ch1/fixtures/T2_zone_gate_synthetic.csv "$TAB/T2_zone_gate.csv" ||
    cp tests/ch1/fixtures/T2_zone_gate_synthetic.csv "$TAB/T2_zone_gate.csv" || exit 2
  say "N_CHAL on the dry run comes from tests/ch1/fixtures/T2_zone_gate_synthetic.csv"
fi

preconditions

step_w314 || stop "W3.14 failed; see $LOG/W3.14*.log"
step_w315 || stop "W3.15 failed; see $LOG/W3.15*.log"
pair W3.16 W3.17 || stop "W3.16 or W3.17 failed; see $LOG/W3.16.log and $LOG/W3.17.log"
pair W3.18 W3.21 || stop "W3.18 or W3.21 failed; see $LOG/W3.18.log and $LOG/W3.21.log"
do_step W6.7 || stop "W6.7 failed; see $LOG/W6.7.log"
do_step W6.8 || stop "W6.8 failed; see $LOG/W6.8.log"
if [ "$DRY" = 1 ]; then
  do_step score || stop "the dry-run score failed; see $LOG/score.log"
fi
say "check: tests/ch1/check_ch1_outputs.R --out $OUT --step all${SYNFLAG:+ $SYNFLAG}"
t0=$(date +%s)
check_step all "$LOG/check_all.log" || stop "the output check failed; see $LOG/check_all.log"
note check ran $(($(date +%s) - t0))

# the summary: each step's time and the peak resident memory of its largest process
say "summary (seconds; peak resident memory of the step's largest process):"
for s in W3.14 W3.15 W3.16 W3.17 W3.18 W3.21 W6.7 W6.8 score check; do
  line="$(grep "^$s|" "$RUNDIR/summary" 2>/dev/null | tail -n 1)"
  [ -n "$line" ] || continue
  peak="$(cat "$RUNDIR"/rss_"$s"* 2>/dev/null | sort -n | tail -n 1)"
  [ "$s" = check ] && peak="$(sort -n "$RUNDIR/rss_check_all" 2>/dev/null | tail -n 1)"
  case "$line" in *"|skipped|"*) peak="" ;; esac
  say "  $(echo "$line" | awk -F'|' '{ printf "%-6s %-22s %6s s", $1, $2, $3 }')  $([ -n "$peak" ] && echo "$((peak / 1048576)) MB" || echo "-")"
done
say "done: every step exited 0 and tests/ch1/check_ch1_outputs.R --step all passes"
