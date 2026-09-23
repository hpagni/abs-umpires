#!/bin/sh
# ops/lint_http.sh -- SOP section 0.5 rule 2, in executable form.
#
# There are exactly two places in this repository allowed to issue an HTTP
# request: src/absump/http.py on the Python side and R/lib/http.R on the R
# side. Both read config/throttle.yml, so both honour one User-Agent, one
# per-host delay and one daily cap. A third call site would put a pull outside
# the throttle, outside the daily budget and outside data/raw/_manifest.csv,
# which is the audit trail for the legal posture.
#
# This greps src/, R/, tools/ and notebooks/ for the request idioms of both
# languages and exits 1 on a hit outside those two files.
#
# Usage: ops/lint_http.sh [-q|--quiet] [ROOT]
#   -q     print only failures and the final line.
#   ROOT   scan this directory instead of the repository root. Used by
#          tests/unit/test_http_etiquette.py to plant a violation in a
#          temporary tree and prove the linter fires on it.
#
# POSIX sh. No network, no package load.

set -u

QUIET=0
ROOT=""
for arg in "$@"; do
    case "$arg" in
        -q|--quiet) QUIET=1 ;;
        -h|--help)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        -*)
            printf 'lint_http: unknown option: %s\n' "$arg" >&2
            exit 2
            ;;
        *) ROOT="$arg" ;;
    esac
done

if [ -z "$ROOT" ]; then
    ROOT=$(cd "$(dirname "$0")/.." && pwd)
fi
if [ ! -d "$ROOT" ]; then
    printf 'lint_http: not a directory: %s\n' "$ROOT" >&2
    exit 2
fi

# The idioms, exactly as section 2.3 lists them.
PATTERN='requests\.|httpx\.get|httpx\.Client|urllib|curl |httr2::request'

# The only two allowed call sites, by exact path and nothing else.
ALLOWED='^src/absump/http\.py:|^R/lib/http\.R:'

SCAN_DIRS=""
for dir in src R tools notebooks; do
    if [ -d "$ROOT/$dir" ]; then
        SCAN_DIRS="$SCAN_DIRS $dir"
    fi
done

if [ -z "$SCAN_DIRS" ]; then
    printf 'lint_http: nothing to scan under %s\n' "$ROOT" >&2
    exit 2
fi

# shellcheck disable=SC2086
HITS=$(cd "$ROOT" && grep -rnE --binary-files=without-match \
        --exclude-dir=__pycache__ --exclude-dir=.ipynb_checkpoints \
        --exclude-dir=.Rproj.user --exclude-dir=renv \
        "$PATTERN" $SCAN_DIRS 2>/dev/null | grep -vE "$ALLOWED")

if [ -n "$HITS" ]; then
    printf 'LINT HTTP FAIL: request idiom outside the two allowed call sites.\n' >&2
    printf '%s\n' "$HITS" >&2
    printf 'Allowed: src/absump/http.py and R/lib/http.R. Route the call through absump.http.get()\n' >&2
    printf 'or absump_http_get(), so it is throttled, budgeted and written to the manifest.\n' >&2
    exit 1
fi

if [ "$QUIET" -eq 0 ]; then
    printf 'scanned:%s under %s\n' "$SCAN_DIRS" "$ROOT"
fi
printf 'LINT HTTP OK\n'
exit 0
