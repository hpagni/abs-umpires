#!/usr/bin/env bash
# scripts/prove.sh <step-id> | --all | --check
#
# Owner: SOP step W9.1, fleet phase 01. SOP section 0.1: an agent claims a step, does the
# work, then runs scripts/prove.sh <step-id>, which executes the registered verify command
# and writes a receipt. A workstream is not done until `make prove` shows its steps as PASS.
#
#   <step-id>  run one step's verify command, write quality/receipts/<step-id>.json,
#              exit with the command's own exit code
#   --all      run every registered step, print one line each, exit non-zero if any
#              non-retired registered step is FAIL. This is what `make prove` calls.
#   --check    validate the registry and the receipt writer. This is W9.1's own verify
#              command, so it must not recurse into --all.
#
# Statuses:
#   PASS     the verify command exited with the registered expect_exit
#   FAIL     it exited with something else
#   MISSING  a path in the step's `needs` is absent, or still carries the ABSUMP_PLACEHOLDER
#            marker W1.14 wrote into its stub, so the step is not built yet and its command
#            is not run
#   RETIRED  the id is registered, retired, and never runs again
#
# Two deviations from the snippet in SOP section 0.1, both deliberate:
#   1. yq is not installed on this machine and phase 01 adds no dependency for one line, so
#      the registry is read by python3 quality/write_receipt.py, which parses steps.yml with
#      a strict small-subset reader. The verify command still comes out of quality/steps.yml.
#   2. ROOT is derived from this script's own location rather than hard-coded to
#      $HOME/sports-project, so a clean clone under any path proves itself.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
REG="quality/write_receipt.py"
RECEIPTS="quality/receipts"
PY="${PYTHON:-python3}"

usage() {
  echo "usage: scripts/prove.sh <step-id> | --all | --check" >&2
  exit 2
}

# run_one <id> <expect_exit> <cmd>  -- runs the verify command, writes the receipt,
# returns the command's exit code.
run_one() {
  local step="$1" expect="$2" cmd="$3" start exit_code
  mkdir -p "$RECEIPTS"
  start=$(date +%s)
  eval "$cmd" > "$RECEIPTS/$step.log" 2>&1
  exit_code=$?
  "$PY" "$REG" --step "$step" --cmd "$cmd" --exit "$exit_code" \
       --duration "$(( $(date +%s) - start ))" > /dev/null
  if [ "$exit_code" -ne "$expect" ]; then
    return 1
  fi
  return 0
}

[ $# -eq 1 ] || usage

case "$1" in
  --check)
    fail=0
    "$PY" "$REG" --check || fail=1
    "$PY" "$REG" --selftest || fail=1
    [ -x scripts/prove.sh ] || { echo "scripts/prove.sh is not executable" >&2; fail=1; }
    [ -f "$RECEIPTS/.gitkeep" ] || { echo "$RECEIPTS/.gitkeep is absent" >&2; fail=1; }
    # Every live step's verify command must be a non-empty single line.
    while IFS=$'\x1f' read -r id owner retired expect needs label cmd; do
      [ "$retired" = "1" ] && continue
      case "$cmd" in
        "") echo "$id: empty verify command" >&2; fail=1 ;;
      esac
    done < <("$PY" "$REG" --registry)
    if [ "$fail" -ne 0 ]; then
      echo "W9.1 scaffold check: FAIL"
      exit 1
    fi
    echo "W9.1 scaffold check: OK"
    exit 0
    ;;
  --all)
    pass=0; failed=0; missing=0; retired_n=0; total=0
    printf "%-7s %-8s %s\n" "STEP" "STATUS" "DETAIL"
    while IFS=$'\x1f' read -r id owner retired expect needs label cmd; do
      total=$((total + 1))
      if [ "$retired" = "1" ]; then
        retired_n=$((retired_n + 1))
        printf "%-7s %-8s %s\n" "$id" "RETIRED" "$label"
        continue
      fi
      if [ -n "$needs" ]; then
        missing=$((missing + 1))
        printf "%-7s %-8s %s\n" "$id" "MISSING" "not built yet: $needs"
        continue
      fi
      start=$(date +%s)
      if run_one "$id" "$expect" "$cmd"; then
        pass=$((pass + 1))
        printf "%-7s %-8s %s (%ss)\n" "$id" "PASS" "$cmd" "$(( $(date +%s) - start ))"
      else
        failed=$((failed + 1))
        printf "%-7s %-8s %s (%ss, log %s)\n" "$id" "FAIL" "$cmd" \
               "$(( $(date +%s) - start ))" "$RECEIPTS/$id.log"
      fi
    done < <("$PY" "$REG" --registry)
    echo
    echo "make prove: $total registered, $pass PASS, $failed FAIL, $missing MISSING, $retired_n RETIRED"
    [ "$failed" -eq 0 ] || exit 1
    exit 0
    ;;
  -h|--help)
    usage
    ;;
esac

STEP="$1"
RETIRED=$("$PY" "$REG" --field retired --step "$STEP" 2>/dev/null) || {
  echo "$STEP is not registered in quality/steps.yml" >&2
  exit 3
}
if [ "$RETIRED" = "True" ]; then
  REASON=$("$PY" "$REG" --field reason --step "$STEP")
  printf "%-7s %-8s %s\n" "$STEP" "RETIRED" "$REASON"
  exit 0
fi
NEEDS_MISSING=$("$PY" - "$STEP" <<'EOF_NEEDS'
import sys
sys.path.insert(0, "quality")
from write_receipt import find, missing_needs
rec = find(sys.argv[1])
print(", ".join(missing_needs(rec)) if rec else "")
EOF_NEEDS
)
if [ -n "$NEEDS_MISSING" ]; then
  printf "%-7s %-8s %s\n" "$STEP" "MISSING" "not built yet: $NEEDS_MISSING"
  exit 1
fi
CMD=$("$PY" "$REG" --field verify --step "$STEP")
EXPECT=$("$PY" "$REG" --field expect_exit --step "$STEP")
START=$(date +%s)
mkdir -p "$RECEIPTS"
eval "$CMD" > "$RECEIPTS/$STEP.log" 2>&1
EXIT=$?
"$PY" "$REG" --step "$STEP" --cmd "$CMD" --exit "$EXIT" \
     --duration "$(( $(date +%s) - START ))"
if [ "$EXIT" -eq "$EXPECT" ]; then
  printf "%-7s %-8s %s\n" "$STEP" "PASS" "$CMD"
else
  printf "%-7s %-8s %s (log %s)\n" "$STEP" "FAIL" "$CMD" "$RECEIPTS/$STEP.log"
fi
exit $EXIT
