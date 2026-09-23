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

# ---------------------------------------------------------------- idempotence
# SOP section 9.1 asks every pipeline step to be safe to re-run: two runs in a
# row leave the tree as they found it. prove.sh used to fail that. It truncated
# quality/receipts/<id>.log on every run and the receipt json carries a
# timestamp, so every `make prove` dirtied about forty files. W1.13 runs
# pre-commit over all files, pre-commit's trailing-whitespace hook rewrote those
# same logs, and the step failed on churn it had caused itself.
#
# Two rules fix it, and both are content comparisons, not mtime comparisons:
#
#   1. The captured output is normalised first (terminal escape sequences
#      removed, no trailing whitespace on any line, exactly one final newline)
#      so that the trailing-whitespace and end-of-file-fixer hooks have nothing
#      left to fix, then written only if it differs from the log already on
#      disk. Escapes are colour, not content: the receipt log is a file, and a
#      file that carries them is neither diffable nor readable.
#
#      What is deliberately NOT normalised is any clock or duration a verify
#      command prints of its own accord. gitleaks stamps the hour, uv prints how
#      long a sync took. Those logs still change on every run, and that is the
#      command's output changing, not prove.sh rewriting an unchanged file.
#      Masking them here would edit evidence. The owning step fixes it by
#      quieting its own command.
#   2. The receipt json is compared against the one already on disk with the two
#      fields that move on their own removed, timestamp_madrid and duration_s.
#      If the proof is otherwise identical, the file on disk is left alone and
#      keeps the stamp of the run that established the current outcome. Every
#      other field, including exit, status, git_sha and git_dirty, is compared,
#      so a real change is still written.

# stable_log <captured> <destination> -- normalise, then write only on a change.
stable_log() {
  "$PY" - "$1" "$2" <<'EOF_STABLE_LOG'
import os
import re
import sys

src, dest = sys.argv[1], sys.argv[2]
with open(src, "rb") as fh:
    text = fh.read().decode("utf-8", "replace")
text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)
lines = [line.rstrip() for line in text.split("\n")]
while lines and lines[-1] == "":
    lines.pop()
new = "\n".join(lines) + "\n" if lines else ""
old = None
if os.path.exists(dest):
    with open(dest, encoding="utf-8", errors="replace") as fh:
        old = fh.read()
if old != new:
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(new)
EOF_STABLE_LOG
}

# stable_receipt <step> <cmd> <exit> <duration> -- write the receipt, then put
# the previous file back if the only differences are the stamp and the duration.
stable_receipt() {
  local step="$1" cmd="$2" code="$3" dur="$4" json saved
  json="$RECEIPTS/$step.json"
  saved=""
  if [ -f "$json" ]; then
    saved="$(mktemp "${TMPDIR:-/tmp}/absump-receipt-XXXXXX")"
    cp "$json" "$saved"
  fi
  "$PY" "$REG" --step "$step" --cmd "$cmd" --exit "$code" --duration "$dur" > /dev/null
  local rc=$?
  if [ -n "$saved" ]; then
    "$PY" - "$saved" "$json" <<'EOF_STABLE_RECEIPT'
import json
import shutil
import sys

VOLATILE = ("timestamp_madrid", "duration_s")
old_path, new_path = sys.argv[1], sys.argv[2]


def proof(path):
    with open(path, encoding="utf-8") as fh:
        return {k: v for k, v in json.load(fh).items() if k not in VOLATILE}


try:
    unchanged = proof(old_path) == proof(new_path)
except (OSError, ValueError):
    unchanged = False
if unchanged:
    shutil.copyfile(old_path, new_path)
EOF_STABLE_RECEIPT
    rm -f "$saved"
  fi
  return $rc
}

# run_step <id> <cmd> -- run the verify command, capture it, write both files.
# Echoes the command's own exit code on stdout.
run_step() {
  local step="$1" cmd="$2" start tmp code
  mkdir -p "$RECEIPTS"
  tmp="$(mktemp "${TMPDIR:-/tmp}/absump-log-XXXXXX")"
  start=$(date +%s)
  eval "$cmd" > "$tmp" 2>&1
  code=$?
  stable_log "$tmp" "$RECEIPTS/$step.log"
  rm -f "$tmp"
  stable_receipt "$step" "$cmd" "$code" "$(( $(date +%s) - start ))"
  echo "$code"
}

# run_one <id> <expect_exit> <cmd>  -- runs the verify command, writes the receipt,
# returns 0 when the command exited with the registered expect_exit.
run_one() {
  local step="$1" expect="$2" cmd="$3" exit_code
  exit_code=$(run_step "$step" "$cmd")
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
    # The receipt-writer selftest writes a receipt into a fresh temporary
    # directory and prints that path and the Madrid stamp it read back. Both
    # move on every run, and this step's own receipt log is what `make prove`
    # commits, so the two volatile substrings are masked here. Nothing is
    # weakened: write_receipt.py --selftest itself asserts the stamp matches the
    # Madrid pattern and exits non-zero when it does not, and its exit code is
    # still what decides this check.
    selftest_out=$("$PY" "$REG" --selftest 2>&1) || fail=1
    printf '%s\n' "$selftest_out" | sed -E \
      -e 's|-> /.*/(W[0-9.]+\.json)$|-> <temporary directory>/\1|' \
      -e 's|stamped [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} .*$|stamped <Madrid timestamp, pattern asserted by write_receipt.py --selftest>|'
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
EXIT=$(run_step "$STEP" "$CMD")
if [ "$EXIT" -eq "$EXPECT" ]; then
  printf "%-7s %-8s %s\n" "$STEP" "PASS" "$CMD"
else
  printf "%-7s %-8s %s (log %s)\n" "$STEP" "FAIL" "$CMD" "$RECEIPTS/$STEP.log"
fi
exit $EXIT
