#!/usr/bin/env bash
# ops/night_statsapi.sh -- the overnight statsapi batch for SOP step W2.6.
#
# One sequential chain, one host. The launcher runs this; a builder does not.
# Two copies running at once would put two request streams against one host and
# break the 4 s spacing that section 2.3 fixes, so the script takes a mutex
# first and exits 0 without working if it cannot have it.
#
# Everything this script does, it does by calling absump.ingest.feeds, which
# calls absump.http, which is the only place in this repository that opens a
# connection. There is no fetch here, no retry here and no sleep here: a second
# throttle is a second policy.
#
# What it costs tonight, measured 2026-09-23: nothing. The staging cache already
# holds every Final 2026 regular-season game with officialDate on or before
# 2026-09-21, and those were imported into the lake, so --resume finds an empty
# queue. The remaining games in the SOP's 2,512 are sealed under section 2.4 and
# must never be requested. The script still runs: a suspended game completed
# inside the open window, or a corrected status, puts a game back in the queue,
# and picking it up must not need a person.
#
# Usage:
#   ops/night_statsapi.sh                 import, then pull the open remainder
#   ops/night_statsapi.sh --plan-only     print the plan, send nothing
#   ops/night_statsapi.sh --max-requests 500
#                                         stop after 500, for a shared night
#
# Exit codes: 0 done or nothing to do, 2 bad usage or another copy holds the
# mutex, 3 the ingest reported a failed game.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

SPORT=1
SEASON=2026
STATUS=Final
PLAN_ONLY=0
MAX_REQUESTS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --plan-only)    PLAN_ONLY=1; shift ;;
    --sport)        SPORT="$2"; shift 2 ;;
    --season)       SEASON="$2"; shift 2 ;;
    --status)       STATUS="$2"; shift 2 ;;
    --max-requests) MAX_REQUESTS="$2"; shift 2 ;;
    -h|--help)      sed -n '2,28p' "$0"; exit 0 ;;
    *)              echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# The seal is absolute. This script never sets it and refuses to run under it,
# because a batch that inherited an unlocked seal would write sealed games into
# the open lake with nothing on the way to catch it.
if [ -n "${ABS_SEAL_UNLOCK:-}" ]; then
  echo "ABS_SEAL_UNLOCK is set. This batch does not run under an unlocked seal." >&2
  exit 2
fi

STAMP="$(TZ=Europe/Madrid date '+%Y-%m-%dT%H-%M-%S')"
LOGDIR="$ROOT/logs/night_statsapi"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/W2.6-sport${SPORT}-${SEASON}-${STAMP}.log"

# mkdir is atomic on APFS; flock is not. One chain per host, and the host is in
# the name so a second host's batch is not blocked by this one.
LOCK="$ROOT/data/tmp/.statsapi_night.lock"
mkdir -p "$(dirname "$LOCK")"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "another statsapi batch holds $LOCK; this copy does nothing" | tee -a "$LOG"
  exit 2
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
  echo "start   $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "step    W2.6"
  echo "sport   $SPORT"
  echo "season  $SEASON"
  echo "status  $STATUS"
  echo "policy  statsapi 4 s spacing, 3000/day, from config/throttle.yml (SOP A3)"
} | tee -a "$LOG"

ARGS=(--sport "$SPORT" --season "$SEASON" --status "$STATUS" --resume)
if [ "$PLAN_ONLY" -eq 1 ]; then
  ARGS+=(--plan-only)
fi
if [ -n "$MAX_REQUESTS" ]; then
  ARGS+=(--max-requests "$MAX_REQUESTS")
fi

uv run --locked python -m absump.ingest.feeds "${ARGS[@]}" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}

{
  echo "end     $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "exit    $RC"
} | tee -a "$LOG"

echo "log: $LOG"
if [ "$RC" -ne 0 ]; then
  exit 3
fi
exit 0
