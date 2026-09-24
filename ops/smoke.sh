#!/bin/sh
# ops/smoke.sh -- SOP step W1.15. The 12-check smoke test. `make smoke`.
#
# Replaces the placeholder W1.14 parked here. The Makefile target already
# delegates to this script and is not edited.
#
# WHAT IT IS FOR. One command that answers "is this machine still able to build
# the project". It touches every seam the pipeline depends on and nothing else:
# the disk floor, the Python pins, the Parquet dialect, the Python-to-R seam,
# CmdStan, mgcv, the two offline traps, dbt, the mirror, the hooks. It is the
# check to run after an upgrade, after a reboot, and before a long pull.
#
# ZERO REQUESTS TO ANY MLB OR SAVANT HOST. That is asserted, not promised. The
# throttle chokepoint keeps two files: data/raw/_budget.json, the per-host
# per-UTC-day counter, and data/raw/_manifest.csv, the append-only audit trail.
# Every request this repository is allowed to make goes through absump.http or
# R/lib/http.R and moves both. This script digests both before the first check
# and after the last, and a changed digest fails the run. A check that reached a
# host through the chokepoint is therefore caught, and a check that reached one
# around the chokepoint is what ops/lint_http.sh exists for, which check 11 runs.
#
# THE TWELVE CHECKS, in SOP order.
#    1 preflight    the 15 GiB floor, PATH, empty DYLD_LIBRARY_PATH, CmdStan
#    2 pins         Python 3.12.14, duckdb 1.5.5, polars 1.44.2, pyarrow 25.0.1
#    3 parquet      100,000 rows, Polars out, DuckDB in, hive_partitioning=true
#    4 seam         data/tmp/seam.parquet, float64 and int64, Python to R, RP-05
#    5 r            2-chain CmdStan fit rhat < 1.01, then mgcv::bam, RP-04
#    6 joinkey      the join-key trap, offline
#    7 plateplane   the plate-plane round trip, offline
#    8 dbt          deps, parse, build --target ci --select tag:smoke
#    9 b2           the B2 canary                      SKIPPABLE
#   10 motherduck   dbt debug --target prod            SKIPPABLE
#   11 precommit    pre-commit run --all-files
#   12 disk         the 15 GiB floor and the disk report
#
# WHY TWELVE AND NOT THIRTEEN. The SOP paragraph lists thirteen clauses and then
# prints two totals, SMOKE OK (12/12) and SMOKE OK (10/12, 2 skipped: b2,
# motherduck), which together fix ten always-run checks and two skippable ones.
# Check 5 is where the arithmetic closes: the CmdStan fit and the mgcv::bam are
# both R, and running them in one session is the cheapest grouping of any pair on
# the list, because loading the renv library is the fixed cost. Both clauses run
# and both are asserted. Nothing on the SOP list was dropped to reach twelve.
#
# THE TWO SKIPS. They are owner items, not failures. The B2 canary needs
# B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY; dbt debug --target prod needs
# MOTHERDUCK_TOKEN. With a name unset the check prints SKIP and the run can still
# pass, which is the convention .env.example states for every empty name. A skip
# counts as a pass in the smoke total, and every skipped check is named on the
# last line, so a reader is never told twelve without being told which two of
# them nobody actually ran.
#
# THE DATA LAKE. No check reads it. Every check that needs bytes makes its own
# under data/tmp/, and the one lake path this script touches at all is the
# request ledger, which it digests as "absent" when it is absent. So a fresh
# clone with no data/ directory runs all twelve, and the header says so rather
# than leaving the reader to infer it from a run that did not fail.
#
# BUDGET. Target under 5 minutes warm, 8 to 12 minutes on a first run, where the
# first run pays for the CmdStan compile, the dbt package download and the
# pre-commit hook environments. Warm on this machine the run is dominated by
# check 11.
#
# Exit: 0 pass, including a pass with skips. 1 a failed check. 2 misuse.
#
# Usage: ops/smoke.sh [-v|--verbose] [-h|--help]
#   -v  print the full output of every check, not only of the ones that fail.
#
# POSIX sh.

set -u

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2
cd "$REPO_ROOT" || exit 2

VERBOSE=0
while [ $# -gt 0 ]; do
  case "$1" in
    -v | --verbose) VERBOSE=1 ;;
    -h | --help)
      sed -n '2,60p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      printf 'smoke: unknown option %s\n' "$1" >&2
      exit 2
      ;;
  esac
  shift
done

TOTAL=12
PASSED=0
SKIPPED=""
FAILED=""

RUN=$(mktemp -d "${TMPDIR:-/tmp}/absump_smoke.XXXXXX") || exit 2
trap 'rm -rf "$RUN"' EXIT INT TERM

# A cache of its own, so a pytest running beside this one cannot collide.
PYTEST_ADDOPTS="${PYTEST_ADDOPTS:--o cache_dir=${TMPDIR:-/tmp}/pytest-cache-W1.15}"
export PYTEST_ADDOPTS

# Scratch. Rebuilt by the checks that use it, so the run is safe to repeat.
mkdir -p data/tmp/smoke

# ---------------------------------------------------------------- the ledger

ledger_digest() {
  for f in data/raw/_budget.json data/raw/_manifest.csv; do
    if [ -f "$f" ]; then
      printf '%s %s\n' "$(shasum -a 256 <"$f" | awk '{print $1}')" "$f"
    else
      printf 'absent %s\n' "$f"
    fi
  done
}

# ---------------------------------------------------------------- the checks
#
# Each returns 0 pass, 1 fail, 3 skip. Output is captured and shown on failure,
# or on every check under --verbose.

check_preflight() {
  sh ops/preflight.sh -q
}

check_pins() {
  uv run --locked python ops/smoke_pins.py
}

check_parquet() {
  uv run --locked python ops/smoke_parquet.py
}

check_seam() {
  # RP-05. The test writes data/tmp/seam.parquet with a float64 of -0.0822 and
  # an int64 game_pk, reads it back through Rscript with arrow::read_parquet,
  # and asserts the values to 1e-12, the Arrow types, and that the two arrow
  # version strings are the same string.
  uv run --locked python -m pytest tests/unit/test_arrow_seam.py -q
}

check_r() {
  Rscript ops/smoke_r.R
}

check_joinkey() {
  uv run --locked python ops/smoke_joinkey.py
}

check_plateplane() {
  uv run --locked python ops/smoke_plateplane.py
}

check_dbt() {
  # config/seal.yml is the one file that defines the boundary day, and
  # dbt/dbt_project.yml reads it from the environment. Same contract as
  # ops/dbt.sh. The target is ci, always: the dev target reads the lake, which
  # is not what this check is about.
  ABS_SEAL_START_DATE=$(sed -n 's/^seal_start_date: *"\(.*\)" *$/\1/p' config/seal.yml)
  export ABS_SEAL_START_DATE
  [ -n "$ABS_SEAL_START_DATE" ] || {
    echo "dbt: config/seal.yml has no seal_start_date"
    return 1
  }

  # The ci target is ':memory:' over the seed, so this check needs no lake and
  # no warehouse file. What it does need is a profile, which dbt resolves from
  # DBT_PROFILES_DIR or ~/.dbt, and a fresh clone has neither until W1.6 is
  # done. That is an environment item, not a credential, so it fails rather than
  # skips, and it says which file to copy instead of letting dbt print a stack.
  if [ ! -f "${DBT_PROFILES_DIR:-$HOME/.dbt}/profiles.yml" ]; then
    echo "dbt: no profiles.yml under ${DBT_PROFILES_DIR:-$HOME/.dbt}"
    echo "dbt: copy dbt/profiles.yml.example there, SOP W1.6. Not a skip: the ci"
    echo "dbt: target is an in-memory build over the seed and needs no lake."
    return 1
  fi

  seed_lines=$(wc -l < dbt/seeds/seed_synthetic_pitches.csv | tr -d ' ')
  [ "$seed_lines" = "201" ] || {
    echo "dbt: the seed has $seed_lines lines, expected 201 (200 rows and a header)"
    return 1
  }

  uv run --locked dbt --no-use-colors deps --project-dir dbt || return 1
  uv run --locked dbt --no-use-colors parse --project-dir dbt || return 1
  uv run --locked dbt --no-use-colors build --project-dir dbt \
    --target ci --select tag:smoke >"$RUN/dbt_build.out" 2>&1 || {
    cat "$RUN/dbt_build.out"
    return 1
  }
  cat "$RUN/dbt_build.out"

  # The Done line is the build's own verdict. ERROR and SKIP are what matter
  # here; the PASS count is W1.11's assertion, not this one, so a model added
  # to tag:smoke later must not turn this check red.
  done_line=$(sed -E 's/^[0-9]{2}:[0-9]{2}:[0-9]{2} +//' "$RUN/dbt_build.out" \
    | grep -E '^Done\. PASS=' | tail -1)
  [ -n "$done_line" ] || {
    echo "dbt: the build printed no Done line"
    return 1
  }
  printf 'dbt: %s\n' "$done_line"
  printf '%s' "$done_line" | grep -qE 'ERROR=0 SKIP=0' || {
    echo "dbt: the ci build over the 200-row seed did not finish clean"
    return 1
  }
}

check_b2() {
  if [ -z "${B2_APPLICATION_KEY_ID:-}" ] || [ -z "${B2_APPLICATION_KEY:-}" ]; then
    echo "b2: B2_APPLICATION_KEY_ID or B2_APPLICATION_KEY is unset, so the canary is skipped."
    echo "b2: the credentials are an owner item. A skip is a pass."
    return 3
  fi
  sh ops/b2_check.sh
}

check_motherduck() {
  if [ -z "${MOTHERDUCK_TOKEN:-}" ]; then
    echo "motherduck: MOTHERDUCK_TOKEN is unset, so dbt debug --target prod is skipped."
    echo "motherduck: the token is an owner item. The local dev target needs nothing."
    return 3
  fi
  uv run --locked dbt --no-use-colors debug --project-dir dbt --target prod \
    >"$RUN/dbt_debug.out" 2>&1 || {
    cat "$RUN/dbt_debug.out"
    return 1
  }
  cat "$RUN/dbt_debug.out"
  grep -q 'Connection test: OK' "$RUN/dbt_debug.out"
}

check_precommit() {
  # no-commit-to-branch is a commit-time hook. Running it here would fail on the
  # default branch for a reason that has nothing to do with the tree, which is
  # the same exemption quality/steps.yml W1.13 takes.
  SKIP=no-commit-to-branch uv run --locked pre-commit run --all-files
}

check_disk() {
  sh ops/disk_check.sh || return 1
  sh ops/disk.sh
}

# ---------------------------------------------------------------- the runner

run_check() {
  n=$1
  id=$2
  label=$3
  fn=$4
  show=$5 # last | all

  log="$RUN/$id.log"
  t_start=$(date +%s)
  "$fn" >"$log" 2>&1
  rc=$?
  t_end=$(date +%s)
  secs=$((t_end - t_start))

  case "$rc" in
    0)
      PASSED=$((PASSED + 1))
      printf '%2d/%d  %-11s OK    %4d s\n' "$n" "$TOTAL" "$id" "$secs"
      ;;
    3)
      SKIPPED="$SKIPPED $id"
      printf '%2d/%d  %-11s SKIP  %4d s\n' "$n" "$TOTAL" "$id" "$secs"
      ;;
    *)
      FAILED="$FAILED $id"
      printf '%2d/%d  %-11s FAIL  %4d s  (%s)\n' "$n" "$TOTAL" "$id" "$secs" "$label"
      ;;
  esac

  if [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ]; then
    sed 's/^/          /' "$log"
  elif [ "$VERBOSE" -eq 1 ] || [ "$show" = "all" ] || [ "$rc" -eq 3 ]; then
    sed 's/^/          /' "$log"
  else
    tail -1 "$log" | sed 's/^/          /'
  fi
}

# ---------------------------------------------------------------- the run

started=$(date +%s)
ledger_digest >"$RUN/ledger.before"

printf 'smoke: SOP W1.15, %d checks, zero requests to any MLB or Savant host\n' "$TOTAL"
printf 'smoke: %s\n' "$REPO_ROOT"

# The lake is not an input. Saying which of the two worlds this run is in costs
# one line and answers the question a fresh clone always raises.
if [ -d data/raw ] || [ -d data/staging ] || [ -d data/sealed ]; then
  printf 'smoke: a data lake is present and no check reads it; all twelve run\n\n'
else
  printf 'smoke: no data lake here, which skips nothing: no check reads one\n\n'
fi

run_check  1 preflight  'disk floor, PATH, DYLD, CmdStan'          check_preflight  last
run_check  2 pins       'Python, duckdb, polars, pyarrow pins'     check_pins       last
run_check  3 parquet    'Polars out, DuckDB in, hive partitions'   check_parquet    last
run_check  4 seam       'the cross-language Arrow seam, RP-05'     check_seam       last
run_check  5 r          'CmdStan rhat and mgcv::bam, RP-04'        check_r          all
run_check  6 joinkey    'the join-key trap, offline'               check_joinkey    all
run_check  7 plateplane 'the plate-plane round trip, offline'      check_plateplane last
run_check  8 dbt        'deps, parse, ci build on the 200-row seed' check_dbt       last
run_check  9 b2         'the B2 canary'                            check_b2         last
run_check 10 motherduck 'dbt debug --target prod'                  check_motherduck last
run_check 11 precommit  'pre-commit run --all-files'               check_precommit  last
run_check 12 disk       'the 15 GiB floor and the disk report'     check_disk       all

ledger_digest >"$RUN/ledger.after"
elapsed=$(($(date +%s) - started))

printf '\n'
if cmp -s "$RUN/ledger.before" "$RUN/ledger.after"; then
  printf 'smoke: request ledger unchanged, so no host was reached through the chokepoint\n'
else
  printf 'smoke: THE REQUEST LEDGER MOVED. A check reached a host.\n' >&2
  diff "$RUN/ledger.before" "$RUN/ledger.after" | sed 's/^/          /' >&2
  FAILED="$FAILED ledger"
fi

n_skipped=0
skip_list=""
for id in $SKIPPED; do
  n_skipped=$((n_skipped + 1))
  if [ -z "$skip_list" ]; then skip_list="$id"; else skip_list="$skip_list, $id"; fi
done

printf 'smoke: %d s\n' "$elapsed"

# Two totals, and they are deliberately not the same total. SMOKE OK is the
# SOP's own string and carries nothing else, so a caller can match it whole; it
# counts only the checks that ran, which is why the SOP's own example of it
# reads 10/12 with two skipped. The smoke line under it is the gate's total,
# where a skip counts as a pass, because an unset owner credential is a fact
# about this laptop and not a defect in this tree. It names the skipped checks
# on the same line, so the twelve is never printed bare.
accounted=$((PASSED + n_skipped))

if [ -n "$FAILED" ]; then
  printf 'SMOKE FAIL (%d/%d passed, failing:%s)\n' "$PASSED" "$TOTAL" "$FAILED" >&2
  printf 'smoke: %d/%d FAIL, failing:%s\n' "$accounted" "$TOTAL" "$FAILED" >&2
  exit 1
fi

if [ "$n_skipped" -eq 0 ]; then
  printf 'SMOKE OK (%d/%d)\n' "$PASSED" "$TOTAL"
  printf 'smoke: %d/%d (all twelve ran, nothing skipped)\n' "$accounted" "$TOTAL"
else
  printf 'SMOKE OK (%d/%d, %d skipped: %s)\n' "$PASSED" "$TOTAL" "$n_skipped" "$skip_list"
  printf 'smoke: %d/%d (%d ran and passed, %d skipped and counted as passes: %s)\n' \
    "$accounted" "$TOTAL" "$PASSED" "$n_skipped" "$skip_list"
fi
exit 0
