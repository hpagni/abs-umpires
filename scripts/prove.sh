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
#   PENDING-OWNER
#            the step carries a `pending_owner` note in the registry: the work is done as
#            far as this machine may take it and the remaining move belongs to the owner,
#            so the command is not run and the status is not a failure. This is how the
#            two parked GitHub Actions steps are told apart from work nobody started
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

# ---------------------------------------------------------------------- the lock
# W9.1. Two sweeps must not interleave. They share quality/receipts/, and each
# one rewrites a receipt only when the normalised content changed, so a second
# sweep running inside the first sees half-written logs, compares against them
# and can persist a receipt that describes neither run. The verifier also caught
# a concurrent agent moving the branch under a sweep, which the receipt records
# in git_branch; one writer at a time is the only way that field means anything.
#
# mkdir is the primitive: on every POSIX filesystem it creates the directory and
# fails, atomically, if it already exists. No flock, no lockfile utility, no
# dependency. The PID is written inside so a stale directory can be identified,
# and a lock whose PID is gone is broken once, reported, and retaken -- a crashed
# sweep must not wedge the gate forever.
#
# Re-entrancy is required, not optional: W9.1's own verify command is
# `bash scripts/prove.sh --check`, which `--all` runs as a child. The holder
# exports its lock path, so a nested prove.sh sees the variable, takes no lock
# and releases nothing.
#
# The lock lives outside the repository, keyed to the repository path, for two
# reasons the receipts themselves make: an in-tree lock directory is untracked
# while it exists, so `git status --porcelain` is non-empty and every receipt
# written during the sweep would record git_dirty true because of the lock; and
# the clause under test is that quality/receipts/ is byte-identical between two
# runs, which a directory that appears and disappears inside it does not help.
LOCK_DIR="${TMPDIR:-/tmp}/absump-prove$(printf '%s' "$ROOT" | tr '/ ' '--').lock"
LOCK_HELD=0

release_lock() {
  [ "$LOCK_HELD" -eq 1 ] || return 0
  LOCK_HELD=0
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}

take_lock() {
  if [ -n "${ABSUMP_PROVE_LOCK:-}" ]; then
    return 0                      # a parent sweep already holds it
  fi
  mkdir -p "$RECEIPTS"
  local tries=0 holder
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    holder="$(cat "$LOCK_DIR/pid" 2>/dev/null || echo '')"
    if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then
      echo "prove: breaking a stale lock left by pid $holder" >&2
      rm -f "$LOCK_DIR/pid"
      rmdir "$LOCK_DIR" 2>/dev/null || true
      continue
    fi
    tries=$((tries + 1))
    if [ "$tries" -ge 60 ]; then
      echo "prove: another run holds $LOCK_DIR (pid ${holder:-unknown}); giving up" >&2
      exit 4
    fi
    sleep 1
  done
  echo $$ > "$LOCK_DIR/pid"
  LOCK_HELD=1
  export ABSUMP_PROVE_LOCK="$LOCK_DIR"
  trap 'release_lock' EXIT INT TERM
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
#      A first attempt left every clock and duration a verify command printed
#      of its own accord, on the argument that masking them would edit
#      evidence. That was wrong twice over. It left the clause unmet, because
#      gitleaks stamps the hour on every line it prints, uv prints how many
#      milliseconds a sync took and pytest prints the number of the temporary
#      directory it made, so four tracked receipt logs changed on every run and
#      `git status` was dirty after every sweep. And it was not evidence: the
#      minute a scan started and the width of a temporary directory's counter
#      prove nothing about the step. So the normaliser now also replaces those
#      three families of run-local token with a named placeholder, one family
#      per rule, and appends a line naming the rules that fired. The reader can
#      see exactly what was replaced and why, which is the opposite of masking.
#      Nothing that carries meaning is touched: counts, sizes, versions,
#      package names, file paths, rule ids, pass and fail lines all survive
#      byte for byte.
#
#        RN-01 clock      a leading wall-clock stamp, 6:54AM INF -> <clock> INF
#        RN-02 elapsed    "in 17ms", "in 1.63s" -> "in <elapsed>"
#        RN-03 tmpdir     a pytest temporary directory, pytest-411 -> pytest-<n>
#        RN-04 timing     a duration a step times itself, on a line that already says
#                         elapsed, took, duration, load or smoke ok, so that a delay or a
#                         budget printed as seconds is left alone: "stack load: 1.8 s" ->
#                         "stack load: <elapsed> s". The same id also covers a duration in
#                         the tail position of a comma-separated status line, which is how
#                         the R smoke fit reports its sampler: ", 0.6 s" -> ", <elapsed> s"
#
#        RN-05 freespace  the free-space quantity a disk check prints, which moves with
#                         whatever else the machine is doing: "34.9 GiB free" ->
#                         "<free> GiB free". Only the quantity before "GiB free" is
#                         replaced; the floor it is compared against, the volume name and
#                         the ok/fail verdict all survive byte for byte
#        RN-06 checktime  the per-check seconds column in ops/smoke.sh output, whose lines
#                         carry none of RN-04's words: " 2/12  pins  OK  1 s" ->
#                         " 2/12  pins  OK  <elapsed> s". Anchored on the "<n>/<n> <name>
#                         <verdict>" prefix, so only that one column is touched and any
#                         parenthesised detail after it is kept
#        RN-07 objaddr    a CPython object address in a default repr, which is the id() of
#                         a fresh object and so differs every run: "<_duckdb.DuckDBPy
#                         Connection object at 0x109dbcab0>" -> "... at 0x<addr>>". Only
#                         the hex digits after the literal " object at " are replaced, so
#                         the class name and the rest of the line survive
#
#        RN-08 dfcolumn   the moving columns of a `df` data row, which the disk check
#                         prints under "free space" as context for the floor it already
#                         asserted on the line above: "460Gi 389Gi 36Gi 92% 3.0M 373M 1%"
#                         -> "<df> ..." per column. The device and the mount point are
#                         kept, and the floor verdict itself is RN-05's line, untouched
#        RN-09 dirsize    a `du -sh` size for a directory the run itself writes into, so
#                         two sweeps differ by whatever the first sweep built:
#                         "2.6G\t/path/warehouse" -> "<size>\t/path/warehouse". Only the
#                         size token is replaced; every path stays
#        RN-10 canarykey  the object key of the B2 canary, which is stamped with the UTC
#                         second it was written: "_canary/20260924T033010Z.txt" ->
#                         "_canary/<stamp>.txt". The 6/6 result and the byte count stay
#
#      If a step's own command grows a further kind of run-local token, the rule
#      for it belongs here, with an id, not in a one-off sed in that step.
#
#      STATED LIMIT, by construction. The normaliser is a line-wise text filter.
#      It can delete a token and it can rewrite one, but it cannot reorder lines,
#      because reordering a log would destroy the only thing a log is for. So any
#      verify command that prints an UNORDERED collection -- a Python set, a dict
#      before 3.7 ordering, a bare os.listdir, a glob, a parallel worker's
#      interleaving -- can defeat receipt byte-identity and the normaliser will
#      never catch it. That is not hypothetical: a failing `assert set(...) ==
#      set(...)` in tests/unit/test_layout.py rendered its members in
#      PYTHONHASHSEED order and made quality/receipts/W1.2.log differ between two
#      otherwise identical sweeps. The fix belongs in the verify command, not
#      here: sort before you print, and compare sorted lists rather than sets, so
#      the failure message is ordered too. A step whose output is unordered is a
#      step whose receipt is unreproducible, and no filter downstream can repair
#      it.
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

# Run-local tokens, one rule per family. See the RN table in the header
# comment. Each rule is (id, pattern, replacement); a rule that changes
# nothing is not reported.
RULES = (
    ("RN-01 clock", re.compile(r"(?m)^\d{1,2}:\d{2}(?:AM|PM) (?=INF |WRN |ERR |DBG )"), "<clock> "),
    ("RN-02 elapsed", re.compile(r"\bin \d+(?:\.\d+)?(?:ns|us|\u00b5s|ms|s|m)\b"), "in <elapsed>"),
    ("RN-03 tmpdir", re.compile(r"\bpytest-\d+\b"), "pytest-<n>"),
    (
        "RN-04 timing",
        re.compile(
            r"(?mi)^(.*\b(?:elapsed|took|duration|load|smoke ok)\b[^0-9\n]*?)"
            r"\d+(?:\.\d+)?(\s*(?:ms|s)\b)"
        ),
        r"\1<elapsed>\2",
    ),
    (
        "RN-04 timing",
        re.compile(r"(?m),\s\d+(?:\.\d+)?\s(ms|s)$"),
        r", <elapsed> \1",
    ),
    (
        "RN-05 freespace",
        re.compile(r"\b\d+(?:\.\d+)?(?= GiB free\b)"),
        "<free>",
    ),
    (
        "RN-06 checktime",
        re.compile(
            r"(?m)^(\s*\d+/\d+\s+\S+\s+(?:OK|FAIL|SKIP)\s+)\d+(?:\.\d+)?(\s+s\b)"
        ),
        r"\1<elapsed>\2",
    ),
    (
        "RN-06 checktime",
        re.compile(r"(?m)^(smoke: )\d+(?:\.\d+)?( s)$"),
        r"\1<elapsed>\2",
    ),
    (
        "RN-07 objaddr",
        re.compile(r"(?<= object at )0x[0-9a-fA-F]+"),
        "0x<addr>",
    ),
    (
        "RN-08 dfcolumn",
        re.compile(r"(?m)^(\s*/dev/\S+)((?:\s+\S+){7})(\s+/\S*)$"),
        lambda m: m.group(1) + re.sub(r"\S+", "<df>", m.group(2)) + m.group(3),
    ),
    (
        "RN-09 dirsize",
        re.compile(r"(?m)^(\s*)\d+(?:\.\d+)?[BKMGTP](?=\t/)"),
        r"\1<size>",
    ),
    (
        "RN-10 canarykey",
        re.compile(r"(?<=_canary/)\d{8}T\d{6}Z(?=\.txt)"),
        "<stamp>",
    ),
)
fired = []
for name, pattern, repl in RULES:
    text, hits = pattern.subn(repl, text)
    if hits and name not in fired:
        fired.append(name)

lines = [line.rstrip() for line in text.split("\n")]
while lines and lines[-1] == "":
    lines.pop()
if fired:
    lines.append("")
    lines.append(
        "-- scripts/prove.sh normalised run-local tokens in this log: "
        + ", ".join(fired)
    )
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
    take_lock
    pass=0; failed=0; missing=0; retired_n=0; pending=0; total=0
    printf "%-7s %-13s %s\n" "STEP" "STATUS" "DETAIL"
    while IFS=$'\x1f' read -r id owner retired expect needs label cmd pending_owner; do
      total=$((total + 1))
      if [ "$retired" = "1" ]; then
        retired_n=$((retired_n + 1))
        printf "%-7s %-13s %s\n" "$id" "RETIRED" "$label"
        continue
      fi
      # A step parked on a decision the owner has taken and recorded reads
      # PENDING-OWNER, not MISSING. MISSING means nobody has built it yet and
      # someone still should. PENDING-OWNER means the work is done as far as
      # this machine may take it and the remaining move is the owner's.
      if [ -n "$pending_owner" ]; then
        pending=$((pending + 1))
        printf "%-7s %-13s %s\n" "$id" "PENDING-OWNER" "$pending_owner"
        continue
      fi
      if [ -n "$needs" ]; then
        missing=$((missing + 1))
        printf "%-7s %-13s %s\n" "$id" "MISSING" "not built yet: $needs"
        continue
      fi
      start=$(date +%s)
      if run_one "$id" "$expect" "$cmd"; then
        pass=$((pass + 1))
        printf "%-7s %-13s %s (%ss)\n" "$id" "PASS" "$cmd" "$(( $(date +%s) - start ))"
      else
        failed=$((failed + 1))
        printf "%-7s %-13s %s (%ss, log %s)\n" "$id" "FAIL" "$cmd" \
               "$(( $(date +%s) - start ))" "$RECEIPTS/$id.log"
      fi
    done < <("$PY" "$REG" --registry)
    echo
    echo "make prove: $total registered, $pass PASS, $failed FAIL, $missing MISSING, $pending PENDING-OWNER, $retired_n RETIRED"
    [ "$failed" -eq 0 ] || exit 1
    exit 0
    ;;
  -h|--help)
    usage
    ;;
esac

STEP="$1"
take_lock
RETIRED=$("$PY" "$REG" --field retired --step "$STEP" 2>/dev/null) || {
  echo "$STEP is not registered in quality/steps.yml" >&2
  exit 3
}
if [ "$RETIRED" = "True" ]; then
  REASON=$("$PY" "$REG" --field reason --step "$STEP")
  printf "%-7s %-13s %s\n" "$STEP" "RETIRED" "$REASON"
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
PENDING_OWNER=$("$PY" "$REG" --field pending_owner --step "$STEP" 2>/dev/null || true)
if [ -n "$PENDING_OWNER" ] && [ "$PENDING_OWNER" != "None" ]; then
  printf "%-7s %-13s %s\n" "$STEP" "PENDING-OWNER" "$PENDING_OWNER"
  exit 0
fi
if [ -n "$NEEDS_MISSING" ]; then
  printf "%-7s %-13s %s\n" "$STEP" "MISSING" "not built yet: $NEEDS_MISSING"
  exit 1
fi
CMD=$("$PY" "$REG" --field verify --step "$STEP")
EXPECT=$("$PY" "$REG" --field expect_exit --step "$STEP")
EXIT=$(run_step "$STEP" "$CMD")
if [ "$EXIT" -eq "$EXPECT" ]; then
  printf "%-7s %-13s %s\n" "$STEP" "PASS" "$CMD"
else
  printf "%-7s %-13s %s (log %s)\n" "$STEP" "FAIL" "$CMD" "$RECEIPTS/$STEP.log"
fi
exit $EXIT
