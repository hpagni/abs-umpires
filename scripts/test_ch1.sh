#!/usr/bin/env bash
# scripts/test_ch1.sh -- `make test-ch1`: the Chapter 1 testthat files, tests/testthat/test-ch1-*.R.
#
# Owner: the closing clause of SOP W3.24 (SOP 9.2: "make ch1 && make test-ch1 regenerates every
# figure and table and exits 0"), fleet phase 08. It replaces W1.14's ABSUMP_PLACEHOLDER stub.
#
#   make test-ch1          from the repository root, after make ch1
#
# Every test-ch1-*.R file runs in one R process through testthat::test_dir. test_dir and test_file
# return normally when an expectation fails, so the exit status is computed here, twice over: from
# the results object (failed expectations plus errored tests, the reporter's FAIL count) and from
# the reporter's own final "[ FAIL n | WARN n | SKIP n | PASS n ]" line. Either one above zero, or
# a missing summary, fails the run. Skips and warnings are printed and do not fail it.
#
# The tests refit nothing. test-ch1-figures.R re-renders F1..F8 and T1..T9 into a temporary
# directory for its determinism check, and those child R processes load the same no-fit guard as
# make ch1 (scripts/ch1.sh --write-guard), so a cache miss can never become a bam fit here either.
#
# The switches that turn a test into a synthetic dry run or skip its determinism re-run (W319_*,
# W322_*, W324_*, ABSUMP_ROOT) are unset: make test-ch1 is the real verify command.
#
# EXIT STATUS. 0 no failure and no error; 1 a failure, an error or no parsable summary; 2 no test
# file or not the repository root.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ -f Makefile ] && [ -d tests/testthat ] && [ -f scripts/ch1.sh ] || {
  echo "test-ch1: $ROOT is not the repository root (no Makefile, tests/testthat or scripts/ch1.sh)" >&2
  exit 2
}
export STAN_NUM_THREADS=1 OMP_NUM_THREADS=1
stamp() { TZ=Europe/Madrid date -Iseconds; }

files=""
for f in tests/testthat/test-ch1-*.R; do [ -f "$f" ] && files="$files $f"; done
if [ -z "$files" ]; then
  echo "test-ch1: no tests/testthat/test-ch1-*.R file" >&2
  exit 2
fi
echo "test-ch1: start $(stamp) in $ROOT (STAN_NUM_THREADS=$STAN_NUM_THREADS OMP_NUM_THREADS=$OMP_NUM_THREADS)"
echo "test-ch1: files:$files"

for v in W319_OUT W319_SYNTHETIC W322_OUT W322_SYNTHETIC W324_OUT W324_DOCS W324_SKIP_RERUN ABSUMP_ROOT; do
  if [ -n "${!v:-}" ]; then echo "test-ch1: unsetting $v=${!v} (make test-ch1 is the real verify command)"; fi
  unset "$v"
done

GUARD_FILE="$(mktemp "${TMPDIR:-/tmp}/ch1_nofit.XXXXXX")"
LOG="$(mktemp "${TMPDIR:-/tmp}/test_ch1_out.XXXXXX")"
RUNNER="$(mktemp "${TMPDIR:-/tmp}/test_ch1_runner.XXXXXX")"
trap 'rm -f "$GUARD_FILE" "$LOG" "$RUNNER"' EXIT
bash scripts/ch1.sh --write-guard "$GUARD_FILE"
export R_PROFILE_USER="$GUARD_FILE"

cat > "$RUNNER" <<'RUNNER'
res <- testthat::test_dir("tests/testthat", filter = "^ch1-",
                          reporter = testthat::ProgressReporter$new(show_praise = FALSE),
                          stop_on_failure = FALSE, stop_on_warning = FALSE)
df <- as.data.frame(res)
agg <- function(x) c(expectations = sum(x$nb), passed = sum(x$passed), failed = sum(x$failed),
                     errored_tests = sum(x$error), skipped_tests = sum(x$skipped), warnings = sum(x$warning),
                     tests = nrow(x))
cat("\ntest-ch1: per file\n")
for (f in unique(df$file)) {
  a <- agg(df[df$file == f, , drop = FALSE])
  cat(sprintf("  %-26s tests %3d  PASS %4d  FAIL %3d  ERROR %2d  SKIP %2d  WARN %2d\n", f, a[["tests"]],
              a[["passed"]], a[["failed"]], a[["errored_tests"]], a[["skipped_tests"]], a[["warnings"]]))
}
a <- agg(df)
n_fail <- a[["failed"]] + a[["errored_tests"]]
cat(sprintf("test-ch1: RESULTS files %d  tests %d  PASS %d  FAIL %d (failed expectations %d + errored tests %d)  SKIP %d  WARN %d\n",
            length(unique(df$file)), a[["tests"]], a[["passed"]], n_fail, a[["failed"]], a[["errored_tests"]],
            a[["skipped_tests"]], a[["warnings"]]))
bad <- df[df$failed > 0 | df$error, c("file", "test"), drop = FALSE]
if (nrow(bad)) cat(sprintf("  FAILED %s: %s\n", bad$file, bad$test), sep = "")
quit(status = if (n_fail > 0) 1L else 0L)
RUNNER

set +e
Rscript "$RUNNER" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e

# The reporter's own summary: the last "[ FAIL n | ..." line.
summary="$(grep -E '\[ *FAIL [0-9]+ *\|' "$LOG" | tail -n 1 || true)"
reporter_fail="$(printf '%s' "$summary" | sed -nE 's/.*FAIL ([0-9]+).*/\1/p')"
echo "test-ch1: reporter summary: ${summary:-none found}"
status=0
if [ "$rc" -ne 0 ]; then
  echo "test-ch1: the test run exited $rc" >&2
  status=1
fi
if [ -z "$reporter_fail" ]; then
  echo "test-ch1: no [ FAIL n | ... ] summary line in the output" >&2
  status=1
elif [ "$reporter_fail" -gt 0 ]; then
  echo "test-ch1: the reporter counts FAIL $reporter_fail" >&2
  status=1
fi
if [ "$status" -ne 0 ]; then
  echo "test-ch1: FAILED at $(stamp)" >&2
  exit 1
fi
echo "test-ch1: PASSED at $(stamp): every test-ch1-*.R file ran with FAIL 0"
exit 0
