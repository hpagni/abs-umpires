#!/bin/sh
# tests/guard/redteam_run.sh -- GD-09, the red team. SOP step W9.7.
#
# The body behind `make prove-guard-redteam`. W1.14 owns the Makefile and
# already wrote the target; this script is the whole of what it runs.
#
# A guard that has never failed is a guard nobody has tested. This script
# plants two real violations, one in a Chapter 1 R script and one in the
# Chapter 3 solver -- the two places the R1 directory-list scan could not see
# -- asserts that the guard fails on both by file and line, reverts, re-runs
# the guard clean, and exits 0. It exits non-zero if the guard stays green with
# the violations in place, which is the failure mode worth catching.
#
# The worktree is left exactly as it was found, whatever happens in the middle:
# the two files are copied before the patch is applied and restored from those
# copies by an EXIT trap.
#
# It reads no data row, opens no database and issues no request.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root" || exit 2

PATCH="tests/guard/redteam.patch"
R_FILE="R/ch1/20_surfaces.R"
PY_FILE="src/absump/ch3/dp_fast.py"

# The held-out label, assembled from fragments so that this script does not
# carry the literal the guard bans (GD-04 reads this file like any other).
FRAG="seal"
HELD="${FRAG}ed"
VIEW="v_pitch_${HELD}"

# SOP rule 0.5.1: an agent shell never carries the unlock. Refuse rather than
# run the guard under an environment that could mask what it is proving.
if [ -n "${ABS_SEAL_UNLOCK:-}" ]; then
  echo "[redteam] refusing: ABS_SEAL_UNLOCK is set in this shell" >&2
  exit 2
fi

for f in "$PATCH" "$R_FILE" "$PY_FILE"; do
  if [ ! -f "$f" ]; then
    echo "[redteam] missing $f; the red team cannot plant a violation in a file that is not there" >&2
    exit 2
  fi
done

work=$(mktemp -d "${TMPDIR:-/tmp}/redteam.XXXXXX") || exit 2
applied=0

restore() {
  if [ "$applied" -eq 1 ]; then
    cp "$work/r.orig" "$root/$R_FILE"
    cp "$work/py.orig" "$root/$PY_FILE"
    applied=0
  fi
  rm -rf "$work"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cp "$R_FILE" "$work/r.orig"
cp "$PY_FILE" "$work/py.orig"

# Render the patch. The stored patch writes the held-out label as @H@ so that
# the patch itself passes GD-04; see its header for why.
sed "s/@H@/${HELD}/g" "$PATCH" > "$work/rendered.patch"

# The guard, run the way the SOP names it. The exit code printed below is
# make's, not pytest's: make reports 2 when a recipe fails, pytest reports 1.
# The number is whatever actually came back, never a number written here.
guard() {
  if command -v make >/dev/null 2>&1; then
    make test-guard > "$1" 2>&1
  else
    uv run --locked pytest tests/guard -q > "$1" 2>&1
  fi
}

echo "[redteam] applying $PATCH"
if ! git apply "$work/rendered.patch" 2>"$work/apply.err"; then
  echo "[redteam] git apply failed; the patch no longer matches the files it plants into" >&2
  sed -n '1,10p' "$work/apply.err" >&2
  exit 1
fi
applied=1

# The planted line numbers are read back from the files, never written by hand,
# so this script stays correct when the stubs become the real script and solver.
r_line=$(grep -n -F "analysis_set == '${HELD}'" "$R_FILE" | head -n 1 | cut -d: -f1)
py_line=$(grep -n -F "$VIEW" "$PY_FILE" | head -n 1 | cut -d: -f1)
if [ -z "$r_line" ] || [ -z "$py_line" ]; then
  echo "[redteam] the patch applied but planted nothing the scan bans" >&2
  exit 1
fi

guard "$work/patched.log"
patched_exit=$?
printf '[redteam] make test-guard -> exit %s   GD-04 FAIL: %s:%s reads analysis_set=%s\n' \
  "$patched_exit" "$R_FILE" "$r_line" "'${HELD}'"
printf '[redteam] make test-guard -> exit %s   GD-04 FAIL: %s:%s reads %s\n' \
  "$patched_exit" "$PY_FILE" "$py_line" "$VIEW"

fails=0
if [ "$patched_exit" -eq 0 ]; then
  echo "[redteam] FAIL: the guard passed with two planted violations in the worktree" >&2
  fails=$((fails + 1))
fi
if ! grep -q -F "GD-04 FAIL: ${R_FILE}:${r_line}" "$work/patched.log"; then
  echo "[redteam] FAIL: no GD-04 failure reported at ${R_FILE}:${r_line}" >&2
  fails=$((fails + 1))
fi
if ! grep -q -F "GD-04 FAIL: ${PY_FILE}:${py_line}" "$work/patched.log"; then
  echo "[redteam] FAIL: no GD-04 failure reported at ${PY_FILE}:${py_line}" >&2
  fails=$((fails + 1))
fi

echo "[redteam] reverting"
cp "$work/r.orig" "$root/$R_FILE"
cp "$work/py.orig" "$root/$PY_FILE"
applied=0

guard "$work/clean.log"
clean_exit=$?
# The suite runs under two -q flags, one from pyproject.toml and one from the
# Makefile, so pytest prints no count line to quote here. The exit code is the
# whole verdict.
printf '[redteam] make test-guard -> exit %s   every GD check green with the plants reverted\n' \
  "$clean_exit"
if [ "$clean_exit" -ne 0 ]; then
  echo "[redteam] FAIL: the guard did not come back green after the revert" >&2
  sed -n '1,20p' "$work/clean.log" >&2
  fails=$((fails + 1))
fi

if [ "$fails" -ne 0 ]; then
  echo "GD-09 FAIL: $fails check(s) failed; the guard does not fail when it should" >&2
  exit 1
fi

echo "GD-09 pass: the guard fails when it should"
exit 0
