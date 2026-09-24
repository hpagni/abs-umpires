#!/usr/bin/env bash
# ops/backfill.sh -- the whole open-set backfill. SOP step W2.22.
#
# `make backfill` delegates here. Everything, resumable, safe to re-run. This
# script holds no fetch, no retry, no sleep and no URL. It runs the stages that
# already exist, in dependency order, and each of those stages derives its own
# queue from disk. That is where the resume lives: nothing here remembers what
# was done, so nothing here can remember it wrongly.
#
# WHY A RE-RUN COSTS ZERO REQUESTS. absump.http keeps an append-only manifest at
# data/raw/_manifest.csv. A URL in that manifest whose file is still on disk is
# served from the cache, and the client never opens a connection for it. On top
# of that the day and game queues subtract what is already in the lake and what
# data/staging/manifest.jsonl records as ok. So an interrupted backfill, re-run,
# asks only for what it never got. tests/data/test_resume.py asserts both halves:
# zero requests for already-manifested URLs, and byte-identical Parquet.
#
# THE SEAL. Every stage here is open-set only. The cutoff is
# absump.paths.LAST_OPEN_DATE and no argument of this script can move it. A day
# after the cutoff belongs to `make inseason`, which routes it to the sealed
# side. This script refuses to run under ABS_SEAL_UNLOCK.
#
# Usage:
#   ops/backfill.sh                      run every stage, in order
#   ops/backfill.sh --plan-only          print each stage's plan, send nothing
#   ops/backfill.sh --list               print the stage names and exit
#   ops/backfill.sh --stage statcast     run one stage; repeatable
#   ops/backfill.sh --max-files 50       stop each pulling stage after 50 files
#   ops/backfill.sh --skip-tests         leave the test stage out
#
# Exit codes: 0 every stage that ran succeeded, 2 bad usage or a refused seal,
# 3 a stage failed. A failed stage stops the run; the next run resumes at it.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

STAGES=(schedule umpires feeds statcast normalize warehouse dbt tests)

PLAN_ONLY=0
LIST_ONLY=0
SKIP_TESTS=0
MAX_FILES=""
WANTED=()

while [ $# -gt 0 ]; do
  case "$1" in
    --plan-only)  PLAN_ONLY=1; shift ;;
    --list)       LIST_ONLY=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --max-files)  MAX_FILES="$2"; shift 2 ;;
    --stage)      WANTED+=("$2"); shift 2 ;;
    -h|--help)    sed -n '2,32p' "$0"; exit 0 ;;
    *)            echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ "$LIST_ONLY" -eq 1 ]; then
  printf '%s\n' "${STAGES[@]}"
  exit 0
fi

if [ -n "$MAX_FILES" ]; then
  case "$MAX_FILES" in
    ''|*[!0-9]*) echo "--max-files takes a whole number: $MAX_FILES" >&2; exit 2 ;;
  esac
fi

for name in "${WANTED[@]-}"; do
  [ -z "$name" ] && continue
  found=0
  for known in "${STAGES[@]}"; do
    [ "$name" = "$known" ] && found=1
  done
  if [ "$found" -eq 0 ]; then
    echo "unknown stage: $name. Known stages: ${STAGES[*]}" >&2
    exit 2
  fi
done

# The seal is absolute. A backfill that inherited an unlocked seal would put
# days after the cutoff in the open lake with nothing on the way to catch it.
if [ -n "${ABS_SEAL_UNLOCK:-}" ]; then
  echo "ABS_SEAL_UNLOCK is set. The backfill does not run under an unlocked seal." >&2
  exit 2
fi

wanted() {
  if [ "${#WANTED[@]}" -eq 0 ]; then
    if [ "$1" = tests ] && [ "$SKIP_TESTS" -eq 1 ]; then
      return 1
    fi
    return 0
  fi
  for name in "${WANTED[@]}"; do
    [ "$1" = "$name" ] && return 0
  done
  return 1
}

STAMP="$(TZ=Europe/Madrid date '+%Y-%m-%dT%H-%M-%S')"
LOGDIR="$ROOT/logs/backfill"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/W2.22-backfill-${STAMP}.log"
LEDGER="$LOGDIR/W2.22-stages.tsv"
if [ ! -f "$LEDGER" ]; then
  printf 'madrid\tmode\tstage\texit\n' > "$LEDGER"
fi

MODE=run
[ "$PLAN_ONLY" -eq 1 ] && MODE=plan

{
  echo "start   $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "step    W2.22"
  echo "mode    $MODE"
  echo "lake    ${ABS_DATA_ROOT:-$ROOT/data}"
  echo "policy  config/throttle.yml, SOP section 2.3 item A3. No delay or cap is named here."
  echo "scope   open set only, up to the absump.paths cutoff. A later day is inseason work."
} | tee -a "$LOG"

record() {
  printf '%s\t%s\t%s\t%s\n' \
    "$(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')" "$MODE" "$1" "$2" >> "$LEDGER"
}

# One stage. Runs the command, tees it, records the exit code, stops the run on
# failure so the next invocation resumes at the stage that failed.
RC_TOTAL=0
stage() {
  name="$1"; shift
  if ! wanted "$name"; then
    return 0
  fi
  echo "--- stage $name  $(TZ=Europe/Madrid date '+%H:%M %Z')" | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  record "$name" "$rc"
  if [ "$rc" -ne 0 ]; then
    echo "stage $name exited $rc. The run stops here and resumes at this stage." | tee -a "$LOG"
    RC_TOTAL=3
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------- the stages

run_schedule() {
  if [ "$PLAN_ONLY" -eq 1 ]; then
    uv run --locked python -m absump.ingest.schedule --plan
  else
    uv run --locked python -m absump.ingest.schedule
  fi
}

run_umpires() {
  if [ "$PLAN_ONLY" -eq 1 ]; then
    uv run --locked python -m absump.ingest.umpires --check
  else
    uv run --locked python -m absump.ingest.umpires
  fi
}

run_feeds() {
  set -- --sport 1 --season 2026 --status Final --resume
  if [ "$PLAN_ONLY" -eq 1 ]; then
    uv run --locked python -m absump.ingest.feeds "$@" --plan-only
  elif [ -n "$MAX_FILES" ]; then
    uv run --locked python -m absump.ingest.feeds "$@" --max-requests "$MAX_FILES"
  else
    uv run --locked python -m absump.ingest.feeds "$@"
  fi
}

run_statcast() {
  if [ "$PLAN_ONLY" -eq 1 ]; then
    uv run --locked python -m absump.ingest.pull_statcast --plan
  elif [ -n "$MAX_FILES" ]; then
    bash ops/night_savant.sh --max-requests "$MAX_FILES"
  else
    bash ops/night_savant.sh
  fi
}

run_normalize() {
  if [ "$PLAN_ONLY" -eq 1 ]; then
    uv run --locked python -m absump.ingest.normalize_sc --level mlb --season 2015..2026 --list
  else
    bash ops/normalize_statcast.sh
  fi
}

run_warehouse() {
  if [ "$PLAN_ONLY" -eq 1 ]; then
    echo "warehouse: ops/warehouse.sh would run."
  else
    bash ops/warehouse.sh
  fi
}

run_dbt() {
  if [ "$PLAN_ONLY" -eq 1 ]; then
    echo "dbt: ops/dbt.sh would run deps, parse and build."
  else
    bash ops/dbt.sh
  fi
}

run_tests() {
  if [ "$PLAN_ONLY" -eq 1 ]; then
    echo "tests: tests/data would run."
  else
    uv run --locked pytest tests/data -q
  fi
}

stage schedule  run_schedule  &&
stage umpires   run_umpires   &&
stage feeds     run_feeds     &&
stage statcast  run_statcast  &&
stage normalize run_normalize &&
stage warehouse run_warehouse &&
stage dbt       run_dbt       &&
stage tests     run_tests

{
  echo "end     $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "exit    $RC_TOTAL"
  echo "ledger  $LEDGER"
} | tee -a "$LOG"

echo "log: $LOG"
exit "$RC_TOTAL"
