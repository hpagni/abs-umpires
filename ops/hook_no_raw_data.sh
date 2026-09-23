#!/bin/sh
# ops/hook_no_raw_data.sh -- the `no-raw-data` pre-commit hook. SOP step W1.13,
# enforcing SOP section 0.5 rule 3 and owner decision D-03.
#
# D-03: data/, research/ and logs/ never enter git in any form. .gitignore is the
# first line and this hook is the second, because .gitignore is silent about a
# path that is added with `git add -f` and silent about a path that was tracked
# before the ignore rule was written. A hook that reads the staged list catches
# both.
#
# The fleet extends D-03 to sop/ and fleet/ (private planning material of the
# same class) and to RUNLOG.md (it names fleet/ paths and step internals). Those
# are refused here too. Refusing more than rule 3 names is safe; refusing less is
# not.
#
# app/data/ and tests/data/ are source, not data. They are re-included in
# .gitignore and they are NOT refused here: the match is on the first path
# segment, so `app/data/park_factors.csv` is fine and `data/raw/x.parquet` is not.
#
# Usage:
#   ops/hook_no_raw_data.sh [PATH ...]
# pre-commit passes the staged paths as arguments. With no arguments the hook
# reads the staged list itself, so it is also usable by hand and from CI.
#
# Exit 0 clean, 1 on a refused path, 2 on a usage error.
# POSIX sh. No network, no package load.

set -u

if [ "$#" -gt 0 ]; then
    PATHS=$(printf '%s\n' "$@")
else
    PATHS=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
fi

[ -n "$PATHS" ] || exit 0

HITS=""
# IFS is set to newline only so a path with a space in it survives the loop.
OLD_IFS=$IFS
IFS='
'
for path in $PATHS; do
    [ -n "$path" ] || continue
    # Strip a leading ./ so `./data/x` and `data/x` are the same path.
    case "$path" in ./*) path=${path#./} ;; esac
    # IFS is newline here, so an unquoted word-split list would not split. The
    # glob list is expanded by `case` itself, which is unaffected by IFS.
    case "$path" in
        data/*|research/*|logs/*|sop/*|fleet/*|RUNLOG.md)
            HITS="$HITS$path
"
            ;;
    esac
done
IFS=$OLD_IFS

if [ -n "$HITS" ]; then
    printf 'NO RAW DATA FAIL: a staged path is under a directory that never enters git.\n' >&2
    printf '%s' "$HITS" >&2
    printf 'D-03 and SOP section 0.5 rule 3: data/, research/ and logs/ are private, and\n' >&2
    printf 'this fleet adds sop/, fleet/ and RUNLOG.md. Unstage the path with\n' >&2
    printf '  git restore --staged <path>\n' >&2
    printf 'and, if it is tracked, remove it from the index with\n' >&2
    printf '  git rm --cached <path>\n' >&2
    printf 'The repository is public from its first commit (D-02), so this is not\n' >&2
    printf 'recoverable by a later commit.\n' >&2
    exit 1
fi

exit 0
