#!/usr/bin/env bash
# ops/nightly.sh -- the local nightly. SOP step W2.22.
#
# `make nightly` delegates here, and so does the launchd agent in
# ops/com.absump.nightly.plist, which fires at 03:30 on the machine clock. That
# clock is Europe/Madrid on this laptop, which is what the SOP asks for. Every
# stamp written below is read from `TZ=Europe/Madrid date`, so a log line is
# correct even if the machine clock moves.
#
# NOT IN ACTIONS. SOP decision D-08: no MLB network from any runner. MLB's
# terms bar automated scripts and non-bulk use, and shared runners cannot honour
# the section 2.3 throttle across concurrent jobs. Actions runs ci.yml and
# seal-guard.yml only. This file is the whole of the scheduled ingest.
#
# WHAT IT DOES. One call to ops/inseason.sh, which does yesterday and today and
# runs the open-set tests. Then it commits, and it commits exactly two files:
#
#   out/tables/data_quality.md
#   docs/prereg/SEAL.md
#
# Nothing else is staged. `git add` is given those two paths and no other, on a
# clean index, so a nightly that found the worktree dirty commits the same two
# files it would have committed on a clean one and leaves the rest alone. data/
# is gitignored and never enters git in any form.
#
# Usage:
#   ops/nightly.sh                  the scheduled run
#   ops/nightly.sh --no-commit      run the pipeline, stage and commit nothing
#   ops/nightly.sh --plan-only      classify and plan, send nothing, commit nothing
#   ops/nightly.sh --push           push the branch after the commit; off by default
#
# Exit codes: 0 clean, 2 bad usage or a refused seal, 3 the in-season run
# failed, 4 the in-season run is blocked on a capability that is not built yet,
# 5 the commit failed. The launchd agent keeps its schedule whatever comes back;
# a failure is read in the log, not by a retry.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

COMMIT=1
PUSH=0
PASSTHROUGH=()

while [ $# -gt 0 ]; do
  case "$1" in
    --no-commit) COMMIT=0; shift ;;
    --push)      PUSH=1; shift ;;
    --plan-only) COMMIT=0; PASSTHROUGH+=(--plan-only); shift ;;
    --date)      PASSTHROUGH+=(--date "$2"); shift 2 ;;
    --skip-tests) PASSTHROUGH+=(--skip-tests); shift ;;
    -h|--help)   sed -n '2,37p' "$0"; exit 0 ;;
    *)           echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -n "${ABS_SEAL_UNLOCK:-}" ]; then
  echo "ABS_SEAL_UNLOCK is set. The nightly does not run under an unlocked seal." >&2
  exit 2
fi

STAMP="$(TZ=Europe/Madrid date '+%Y-%m-%dT%H-%M-%S')"
LOGDIR="$ROOT/logs/nightly"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/W2.22-nightly-${STAMP}.log"

COMMITTED=(out/tables/data_quality.md docs/prereg/SEAL.md)

{
  echo "start   $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "step    W2.22"
  echo "host    $(hostname -s)"
  echo "commit  ${COMMITTED[*]}"
} | tee -a "$LOG"

if [ "${#PASSTHROUGH[@]}" -gt 0 ]; then
  bash ops/inseason.sh "${PASSTHROUGH[@]}" 2>&1 | tee -a "$LOG"
else
  bash ops/inseason.sh 2>&1 | tee -a "$LOG"
fi
RC=${PIPESTATUS[0]}
echo "inseason exit $RC" | tee -a "$LOG"

# ---------------------------------------------------------------- the commit

if [ "$COMMIT" -eq 1 ]; then
  if ! git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    echo "no git repository here. Nothing is committed." | tee -a "$LOG"
  else
    # `git commit --only -- <paths>` commits the worktree state of exactly those
    # paths. It does not read the index and it does not write it, so a nightly
    # that ran while somebody had other work staged commits the same two files
    # and leaves that person's index alone. `git add` plus a reset would not:
    # the reset would throw their staging away.
    STAGE=()
    for path in "${COMMITTED[@]}"; do
      if [ -f "$ROOT/$path" ]; then
        STAGE+=("$path")
      else
        echo "absent, not committed: $path" | tee -a "$LOG"
      fi
    done

    if [ "${#STAGE[@]}" -eq 0 ]; then
      echo "neither committed file exists. Nothing is committed." | tee -a "$LOG"
    elif git -C "$ROOT" diff --quiet HEAD -- "${STAGE[@]}"; then
      echo "no change in either file. Nothing is committed." | tee -a "$LOG"
    else
      MSG="nightly: data quality and seal log, $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
      BEFORE="$(git -C "$ROOT" rev-parse HEAD)"
      git -C "$ROOT" commit --quiet --only -m "$MSG" -- "${STAGE[@]}" 2>&1 | tee -a "$LOG"
      if [ "${PIPESTATUS[0]}" -ne 0 ]; then
        echo "commit failed" | tee -a "$LOG"
        RC=5
      else
        AFTER="$(git -C "$ROOT" rev-parse HEAD)"
        # The commit is the list and nothing else. A third path in it means the
        # commit was not the one this script asked for, and that is a failure to
        # report, not a thing to leave in the history unremarked.
        EXTRA="$(git -C "$ROOT" diff --name-only "$BEFORE" "$AFTER" \
          | grep -v -x -F -f <(printf '%s\n' "${COMMITTED[@]}") || true)"
        if [ -n "$EXTRA" ]; then
          echo "the commit carried paths that are not on the list:" | tee -a "$LOG"
          echo "$EXTRA" | tee -a "$LOG"
          RC=5
        else
          echo "committed $(git -C "$ROOT" rev-parse --short HEAD)" | tee -a "$LOG"
          if [ "$PUSH" -eq 1 ]; then
            git -C "$ROOT" push 2>&1 | tee -a "$LOG"
            [ "${PIPESTATUS[0]}" -ne 0 ] && { echo "push failed" | tee -a "$LOG"; RC=5; }
          fi
        fi
      fi
    fi
  fi
fi

{
  echo "end     $(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M %Z')"
  echo "exit    $RC"
} | tee -a "$LOG"

echo "log: $LOG"
exit "$RC"
