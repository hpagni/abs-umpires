#!/usr/bin/env bash
# ops/night_savant.sh -- the overnight Savant day batch for SOP step W6.0.
#
# One sequential chain, one host. The launcher runs this; a builder does not.
# It drives absump.ingest.pull_statcast, which drives the W2.9 day puller,
# which calls absump.http. That is the only place in this repository that opens
# a connection. There is no fetch here, no retry here and no sleep here: a
# second throttle would be a second policy.
#
# The mutex lives in the Python runner, not here. ops/night_statsapi.sh takes
# its lock in the shell; this one does not, because the chain must also be one
# chain when somebody starts the module by hand. The lock is a directory under
# data/tmp, taken where the calls are issued, so both entry points queue behind
# the same door. A second copy exits 2 and does nothing.
#
# Two nights, not one run. The A3 policy is 10 s and 800/day against Savant, so
# the 2022-2026 day list does not fit in one night. The runner stops at the cap
# with a stop reason and writes logs/night_savant/W6.0-resume.json; the next
# night starts from what is on disk and needs no argument to resume.
#
# What it costs tonight, measured 2026-09-23: 110 day pulls, about 18 min of
# throttled wall clock. The staging cache already holds 799 of the 908 open
# game-days and those were imported into the lake, so the queue is the 2022
# tail, 2022-06-15 to 2022-10-05. Days after 2026-09-21 are sealed under
# section 2.4 and are never in the list at all.
#
# Usage:
#   ops/night_savant.sh                  import staging, then drive the queue
#   ops/night_savant.sh --plan-only      print the plan, send nothing
#   ops/night_savant.sh --check          run the W6.0 assertions, send nothing
#   ops/night_savant.sh --max-requests 200
#                                        stop after 200 days, for a shared night
#
# Exit codes: 0 done or nothing to do, 2 bad usage or another chain holds the
# mutex, 3 the runner reported a failed day.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

MODE=run
MAX_REQUESTS=""
IMPORT_STAGING=1

while [ $# -gt 0 ]; do
  case "$1" in
    --plan-only)         MODE=plan; shift ;;
    --check)             MODE=check; shift ;;
    --max-requests)      MAX_REQUESTS="$2"; shift 2 ;;
    --no-import-staging) IMPORT_STAGING=0; shift ;;
    -h|--help)           sed -n '2,35p' "$0"; exit 0 ;;
    *)                   echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# The seal is absolute. This script never sets it and refuses to run under it.
# A batch that inherited an unlocked seal would put days past 2026-09-21 in the
# open lake with nothing on the way to catch it.
if [ -n "${ABS_SEAL_UNLOCK:-}" ]; then
  echo "ABS_SEAL_UNLOCK is set. This batch does not run under an unlocked seal." >&2
  exit 2
fi

STAMP="$(TZ=Europe/Madrid date '+%Y-%m-%dT%H-%M-%S')"
LOGDIR="$ROOT/logs/night_savant"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/W6.0-${MODE}-${STAMP}.log"

{
  echo "start   $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "step    W6.0"
  echo "mode    $MODE"
  echo "policy  savant 10 s spacing, 800/day, from config/throttle.yml (SOP A3)"
  echo "cutoff  2026-09-21 inclusive; a later day is never in the list"
} | tee -a "$LOG"

ARGS=()
case "$MODE" in
  plan)  ARGS+=(--plan) ;;
  check) ARGS+=(--check) ;;
  run)   ARGS+=(--run) ;;
esac
if [ "$MODE" = run ]; then
  if [ "$IMPORT_STAGING" -eq 0 ]; then
    ARGS+=(--no-import-staging)
  fi
  if [ -n "$MAX_REQUESTS" ]; then
    ARGS+=(--max-requests "$MAX_REQUESTS")
  fi
fi

uv run --locked python -m absump.ingest.pull_statcast "${ARGS[@]}" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}

{
  echo "end     $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "exit    $RC"
} | tee -a "$LOG"

echo "log: $LOG"
case "$RC" in
  0) exit 0 ;;
  2) exit 2 ;;
  *) exit 3 ;;
esac
