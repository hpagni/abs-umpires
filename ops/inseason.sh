#!/usr/bin/env bash
# ops/inseason.sh -- yesterday and today. SOP step W2.22.
#
# `make inseason` delegates here. Schedule, feeds, Statcast, dbt build, tests,
# for two days: yesterday and today, both read from `TZ=Europe/Madrid date`.
# No offset is computed here and no date is written down here.
#
# THE ROUTING. config/seal.yml fixes seal_start_date at 2026-09-22 and the
# regular season ends 2026-09-27, so every remaining 2026 date is past the seal
# and every in-season day routes to the sealed side. The routing itself is not
# decided here: absump.paths.lake_path is the one function that knows the
# sealed branch, and absump.ingest.normalize_sc calls it for every day it
# converts. This script classifies the two days, says which side each one goes
# to, and then asserts the classification held on disk.
#
# THE LEAK CHECK. After the build it re-runs the open-set tests: the GD-* guard
# pack and the DT-* data pack. A sealed day that reached the open lake, an open
# extract that grew a sealed row, or a dbt model that read past the seal turns
# those red. Proving nothing leaked is the point of running them again on a
# night whose only new data is sealed.
#
# THE FRESHNESS ASSERTION (SOP risk R-26). Inside the active window a missed
# night is a hole in exactly the pre-registered data. After the build this
# script checks that the newest officialDate on disk is within --freshness-days
# of today and fails loudly when it is not, so a silent gap becomes a red run.
#
# Usage:
#   ops/inseason.sh                      yesterday and today
#   ops/inseason.sh --plan-only          classify and plan, send nothing
#   ops/inseason.sh --date 2026-09-23    one explicit day; repeatable
#   ops/inseason.sh --freshness-days 2   the R-26 window, default 2
#   ops/inseason.sh --skip-tests         leave the leak check out
#
# Exit codes: 0 every stage ran, 2 bad usage or a refused seal, 3 a stage
# failed, 4 a stage is blocked on a capability that is not built yet.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

PLAN_ONLY=0
SKIP_TESTS=0
FRESHNESS_DAYS=2
DAYS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --plan-only)      PLAN_ONLY=1; shift ;;
    --skip-tests)     SKIP_TESTS=1; shift ;;
    --freshness-days) FRESHNESS_DAYS="$2"; shift 2 ;;
    --date)           DAYS+=("$2"); shift 2 ;;
    -h|--help)        sed -n '2,36p' "$0"; exit 0 ;;
    *)                echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$FRESHNESS_DAYS" in
  ''|*[!0-9]*) echo "--freshness-days takes a whole number: $FRESHNESS_DAYS" >&2; exit 2 ;;
esac

# The seal is absolute. This script routes sealed days to the sealed side; it
# never reads them and never runs with the seal open.
if [ -n "${ABS_SEAL_UNLOCK:-}" ]; then
  echo "ABS_SEAL_UNLOCK is set. The in-season run does not work under an unlocked seal." >&2
  exit 2
fi

# Yesterday and today, from the shell, in Madrid. `date -v-1d` is the BSD form
# that ships with macOS 26.6.
TODAY="$(TZ=Europe/Madrid date '+%Y-%m-%d')"
YESTERDAY="$(TZ=Europe/Madrid date -v-1d '+%Y-%m-%d')"
if [ "${#DAYS[@]}" -eq 0 ]; then
  DAYS=("$YESTERDAY" "$TODAY")
fi

for day in "${DAYS[@]}"; do
  case "$day" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
    *) echo "--date takes YYYY-MM-DD: $day" >&2; exit 2 ;;
  esac
done

SEASON="${DAYS[0]%%-*}"

STAMP="$(TZ=Europe/Madrid date '+%Y-%m-%dT%H-%M-%S')"
LOGDIR="$ROOT/logs/inseason"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/W2.22-inseason-${STAMP}.log"

MODE=run
[ "$PLAN_ONLY" -eq 1 ] && MODE=plan

{
  echo "start   $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "step    W2.22"
  echo "mode    $MODE"
  echo "days    ${DAYS[*]}"
  echo "season  $SEASON"
  echo "lake    ${ABS_DATA_ROOT:-$ROOT/data}"
  echo "policy  config/throttle.yml, SOP section 2.3 item A3. No delay or cap is named here."
} | tee -a "$LOG"

RC_TOTAL=0
BLOCKED=0

note() { echo "$*" | tee -a "$LOG"; }

# ---------------------------------------------------------------- classify

# The side each day goes to, read from config/seal.yml through absump.paths.
# The script never compares dates itself: one predicate, one file.
classify() {
  uv run --locked python - "$@" <<'PY'
import sys
from absump import paths

for value in sys.argv[1:]:
    day = paths.as_official_date(value)
    print(f"{day.isoformat()} {'sealed' if paths.is_sealed(day) else 'open'}")
PY
}

note "--- classify"
CLASSES="$(classify "${DAYS[@]}" 2>&1)"
rc=$?
if [ "$rc" -ne 0 ]; then
  note "$CLASSES"
  note "classification failed. Nothing is routed on a guess."
  exit 3
fi
note "$CLASSES"

SEALED_DAYS=()
OPEN_DAYS=()
while read -r day side; do
  [ -z "$day" ] && continue
  if [ "$side" = sealed ]; then
    SEALED_DAYS+=("$day")
  else
    OPEN_DAYS+=("$day")
  fi
done <<< "$CLASSES"

note "sealed  ${SEALED_DAYS[*]-none}"
note "open    ${OPEN_DAYS[*]-none}"

# ---------------------------------------------------------------- schedule

note "--- stage schedule"
if [ "$PLAN_ONLY" -eq 1 ]; then
  uv run --locked python -m absump.ingest.schedule --sport 1 --season "$SEASON" --plan 2>&1 | tee -a "$LOG"
else
  uv run --locked python -m absump.ingest.schedule --sport 1 --season "$SEASON" 2>&1 | tee -a "$LOG"
fi
rc=${PIPESTATUS[0]}
[ "$rc" -ne 0 ] && { note "schedule exited $rc"; RC_TOTAL=3; }

# ---------------------------------------------------------------- feeds and Statcast

# Owner decision D-23: sealed games are pulled during the sprint, into
# data/sealed/, guarded. The guard exists and the sealed write does not.
# absump.ingest.feeds refuses to store a sealed game (it quarantines it) and
# absump.ingest.statcast_day refuses to build a URL for a day past
# absump.paths.LAST_OPEN_DATE. Both refusals are correct for the open backfill
# and both are owned elsewhere: W2.6 and W2.9. Until the sealed write branch
# lands in those two modules there is no code path that puts a sealed raw feed
# or a sealed Statcast day on disk, so this script reports the stage blocked
# and does not pretend the night succeeded.
if [ "${#SEALED_DAYS[@]}" -gt 0 ]; then
  note "--- stage feeds, sealed days ${SEALED_DAYS[*]}"
  note "blocked: absump.ingest.feeds quarantines a sealed game rather than storing it."
  note "blocked: absump.ingest.statcast_day refuses to build a URL past the cutoff."
  note "owner:   the sealed write branch belongs to SOP W2.6 and W2.9, not to W2.22."
  note "effect:  no request is issued for these days and no sealed row is written."
  BLOCKED=1
fi

if [ "${#OPEN_DAYS[@]}" -gt 0 ]; then
  note "--- stage feeds, open days ${OPEN_DAYS[*]}"
  if [ "$PLAN_ONLY" -eq 1 ]; then
    uv run --locked python -m absump.ingest.feeds --sport 1 --season "$SEASON" \
      --status Final --resume --plan-only 2>&1 | tee -a "$LOG"
  else
    uv run --locked python -m absump.ingest.feeds --sport 1 --season "$SEASON" \
      --status Final --resume 2>&1 | tee -a "$LOG"
  fi
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && { note "feeds exited $rc"; RC_TOTAL=3; }

  note "--- stage statcast, open days ${OPEN_DAYS[*]}"
  if [ "$PLAN_ONLY" -eq 1 ]; then
    uv run --locked python -m absump.ingest.statcast_day --plan "${OPEN_DAYS[@]}" 2>&1 | tee -a "$LOG"
  else
    uv run --locked python -m absump.ingest.statcast_day --pull "${OPEN_DAYS[@]}" 2>&1 | tee -a "$LOG"
  fi
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && { note "statcast exited $rc"; RC_TOTAL=3; }
fi

# ---------------------------------------------------------------- normalize and build

if [ "$PLAN_ONLY" -eq 0 ]; then
  note "--- stage normalize"
  bash ops/normalize_statcast.sh --level mlb --season "$SEASON" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && { note "normalize exited $rc"; RC_TOTAL=3; }

  note "--- stage dbt"
  bash ops/dbt.sh 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && { note "dbt exited $rc"; RC_TOTAL=3; }
else
  note "--- stage normalize: ops/normalize_statcast.sh would run for season $SEASON."
  note "--- stage dbt: ops/dbt.sh would run deps, parse and build."
fi

# ---------------------------------------------------------------- the routing assertion

# The classification above is a claim. This is the check. For every sealed day,
# no Parquet part may exist under the open lake, and any part that does exist
# must be under the sealed root. paths.lake_path is asked where the day belongs;
# the filesystem is asked where it went.
note "--- assert routing"
uv run --locked python - "${DAYS[@]}" <<'PY' 2>&1 | tee -a "$LOG"
import sys
from absump import paths

DATASET = "statcast_pitch"
LEVEL = "mlb"
bad = []
for value in sys.argv[1:]:
    day = paths.as_official_date(value)
    season = day.year
    sealed = paths.is_sealed(day)
    routed = paths.lake_path(DATASET, LEVEL, season, day, 0)
    under_sealed = paths._is_under(routed, paths.sealed_root())
    if sealed != under_sealed:
        bad.append(f"{day.isoformat()} sealed={sealed} but lake_path gave {routed}")
        continue
    print(f"{day.isoformat()} {'sealed' if sealed else 'open'} -> {routed} exists={routed.exists()}")
    if sealed:
        open_part = paths.data_root() / "interim" / DATASET / f"level={LEVEL}" / \
            f"season={season}" / f"date={day.isoformat()}" / "part-000.parquet"
        if open_part.exists():
            bad.append(f"{day.isoformat()} is sealed and has an open part at {open_part}")
for line in bad:
    print(f"ROUTING FAILURE {line}")
raise SystemExit(1 if bad else 0)
PY
rc=${PIPESTATUS[0]}
[ "$rc" -ne 0 ] && { note "routing assertion exited $rc"; RC_TOTAL=3; }

# ---------------------------------------------------------------- freshness, R-26

if [ "$PLAN_ONLY" -eq 0 ]; then
  note "--- assert freshness, within $FRESHNESS_DAYS days"
  uv run --locked python - "$FRESHNESS_DAYS" <<'PY' 2>&1 | tee -a "$LOG"
import datetime as dt
import sys
from absump import paths

window = int(sys.argv[1])
today = dt.datetime.now(dt.timezone.utc).date()
root = paths.data_root() / "raw" / "statcast"
days = []
for part in root.rglob("*"):
    name = part.stem.split(".")[0]
    try:
        days.append(dt.date.fromisoformat(name[-10:]))
    except ValueError:
        continue
if not days:
    print("freshness: the lake holds no Statcast day. Nothing to age.")
    raise SystemExit(0)
newest = max(days)
age = (today - newest).days
print(f"freshness: newest stored day {newest.isoformat()}, {age} days old, window {window}")
if age > window:
    print("FRESHNESS FAILURE: the nightly has a gap. SOP risk R-26.")
    raise SystemExit(1)
PY
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && { note "freshness assertion exited $rc"; RC_TOTAL=3; }
fi

# ---------------------------------------------------------------- the leak check

if [ "$SKIP_TESTS" -eq 0 ] && [ "$PLAN_ONLY" -eq 0 ]; then
  note "--- open-set tests, GD-* guard pack"
  uv run --locked pytest tests/guard -q 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && { note "guard pack exited $rc"; RC_TOTAL=3; }

  note "--- open-set tests, DT-* data pack"
  uv run --locked pytest tests/data -q 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && { note "data pack exited $rc"; RC_TOTAL=3; }
else
  note "--- open-set tests: skipped in this mode."
fi

if [ "$RC_TOTAL" -eq 0 ] && [ "$BLOCKED" -eq 1 ]; then
  RC_TOTAL=4
fi

{
  echo "end     $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "exit    $RC_TOTAL"
} | tee -a "$LOG"

echo "log: $LOG"
exit "$RC_TOTAL"
