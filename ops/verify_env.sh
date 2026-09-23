#!/bin/sh
# ops/verify_env.sh -- SOP W9.2, the environment gate. `make verify-env`.
#
# Six checks, RP-01 through RP-06 of SOP section 6.1. On success the last line is
# exactly `6/6 OK` and the exit status is 0. On failure the last line is `n/6 OK`
# with the failing ids named, and the exit status is 1; the captured output of
# each failing check is printed above it.
#
#   RP-01  lockfile current                 uv lock --check
#   RP-02  env installs from the lock alone  uv sync --locked --all-groups; import absump
#   RP-03  R env matches renv.lock           renv::status() -> "No issues found"
#   RP-04  CmdStan pinned, DYLD unset        cmdstan_version()=="2.40.0"
#   RP-05  arrow equal on both sides         tests/unit/test_arrow_seam.py
#   RP-06  every stochastic call seeded      tests/unit/test_seeds.py
#
# RP-07 (determinism) and RP-08 (cold rebuild) are not runnable in phase 01:
# `make all` has no content yet, so running them now would prove nothing and pass
# vacuously. They are printed as DEFERRED with the step and fleet phase that owns
# them, so that a reader of this output is never left thinking six is the whole
# reproducibility gate. They are not counted in the denominator.
#
# Nothing here touches the network and nothing here reads a 2026 datum.
#
# Usage: ops/verify_env.sh [-v|--verbose] [-h|--help]
#   -v   also print the captured output of the checks that pass.
#
# POSIX sh.

set -u

VERBOSE=0
while [ $# -gt 0 ]; do
  case "$1" in
    -v | --verbose) VERBOSE=1 ;;
    -h | --help)
      sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      printf 'verify-env: unknown option %s\n' "$1" >&2
      exit 2
      ;;
  esac
  shift
done

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 1
cd "$REPO_ROOT" || exit 1

TMP=$(mktemp "${TMPDIR:-/tmp}/absump_verify_env.XXXXXX") || exit 1
trap 'rm -f "$TMP"' EXIT INT TERM

PASSED=0
FAILED=""

# ---------------------------------------------------------------- the checks

rp01() {
  # RP-01: uv.lock is current for pyproject.toml. Does not touch the network.
  uv lock --check
}

rp02() {
  # RP-02: the environment installs from the lock alone, and the package it
  # installs is importable under the name the SOP fixed: absump, never "abs".
  #
  # D-PROVE-02. --all-groups is load-bearing, not decoration. W1.4's verify
  # command syncs every dependency group; a bare `uv sync --locked` here syncs
  # only the default groups and so UNINSTALLS the bayes group W1.4 had just
  # installed. The two steps then fought over the same .venv and whichever ran
  # last decided whether the next R or model step could import anything. Both
  # sides now name the same group set, so the environment is the same after
  # either one and `make prove` is order-independent.
  uv sync --locked --all-groups || return 1
  uv run --locked python -c 'import absump; print("import absump: ok")'
}

rp03() {
  # RP-03: the R library matches renv.lock. renv::status() exits 0 whether or not
  # it found something, so the wording is what decides.
  out=$(Rscript -e 'renv::status()' 2>&1) || {
    printf '%s\n' "$out"
    return 1
  }
  printf '%s\n' "$out"
  printf '%s' "$out" | grep -q 'No issues found'
}

rp04() {
  # RP-04: CmdStan is the pinned 2.40.0 and DYLD_LIBRARY_PATH is empty. .Rprofile
  # also refuses to start R with it set, so a non-empty value fails here twice.
  Rscript -e 'suppressMessages(library(cmdstanr));
    stopifnot(cmdstan_version() == "2.40.0");
    stopifnot(identical(Sys.getenv("DYLD_LIBRARY_PATH"), ""));
    cat("cmdstan", cmdstan_version(), "| DYLD_LIBRARY_PATH empty\n")'
}

rp05() {
  # RP-05: pyarrow and R arrow are the same version string, and a float64 and an
  # int64 cross the Parquet seam with their values and their Arrow types intact.
  uv run --locked python -m pytest tests/unit/test_arrow_seam.py -q
}

rp06() {
  # RP-06: no unseeded stochastic call in the production trees, and
  # config/seeds.yml holds the eight seeds SOP W9.2 names.
  uv run --locked python -m pytest tests/unit/test_seeds.py -q
}

# ---------------------------------------------------------------- the runner

run_check() {
  id=$1
  label=$2
  fn=$3
  if "$fn" >"$TMP" 2>&1; then
    PASSED=$((PASSED + 1))
    printf '%-6s OK        %s\n' "$id" "$label"
    if [ "$VERBOSE" -eq 1 ]; then
      sed 's/^/             /' "$TMP"
    fi
  else
    FAILED="$FAILED $id"
    printf '%-6s FAIL      %s\n' "$id" "$label"
    sed 's/^/             /' "$TMP"
  fi
}

printf 'verify-env: SOP W9.2, RP-01..RP-06, in %s\n' "$REPO_ROOT"

run_check RP-01 'lockfile current' rp01
run_check RP-02 'env installs from the lock alone' rp02
run_check RP-03 'R env matches renv.lock' rp03
run_check RP-04 'CmdStan 2.40.0 pinned, DYLD_LIBRARY_PATH unset' rp04
run_check RP-05 'arrow 25.0.1 on both sides, seam agrees to 1e-12' rp05
run_check RP-06 'every stochastic call seeded' rp06

printf 'RP-07  DEFERRED  determinism: make all twice, quality/compare_out.py --tol 1e-8\n'
printf '                 make all has no content in phase 01. Owner SOP W9.9, fleet phase 12,\n'
printf '                 app-and-memo. Not counted below.\n'
printf 'RP-08  DEFERRED  cold rebuild from a clean checkout\n'
printf '                 Owner SOP W6.11, fleet phase 06, abstract-freeze-and-submit.\n'
printf '                 Not counted below.\n'
printf 'RP-09  ELSEWHERE throttle config and budget table agree\n'
printf '                 pytest tests/unit/test_throttle_budget.py, runs under make test.\n'
printf '                 Not one of the six.\n'

if [ -z "$FAILED" ]; then
  printf '6/6 OK\n'
  exit 0
fi

printf '%d/6 OK -- failing:%s\n' "$PASSED" "$FAILED"
exit 1
