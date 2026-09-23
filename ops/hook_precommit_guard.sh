#!/bin/sh
# ops/hook_precommit_guard.sh -- the no-raw-data guard. SOP step W2.1, enforcing
# SOP section 0.5 rule 3 and owner decision D-03.
#
# This file is the tracked source. ops/install_git_hooks.sh copies it to
# .git/hooks/pre-commit, which git itself never tracks. A clone reinstates the
# local guard with:  bash ops/install_git_hooks.sh
#
# W2.1 asks for two independent checks of the same rule:
#   1. this hook, which refuses any staged path under data/ before a commit is
#      written, and
#   2. tests/unit/test_layout.py::test_no_data_tracked, which asserts
#      `git ls-files data/ | wc -l == 0` in CI.
# Both exist because a hook does not travel with a clone. A fresh clone of
# hpagni/abs-umpires has no .git/hooks/pre-commit at all, so CI has to repeat
# the check rather than trust it.
#
# This is the raw shell hook, distinct from the pre-commit framework hook that
# W1.13 installed. The framework's hook was moved to .git/hooks/pre-commit.framework
# and this hook execs it once the data check passes, so both run on every commit
# and neither is lost. If pre-commit.framework is absent (a fresh clone, or a
# checkout where `pre-commit install` has not been run), this hook still refuses
# raw data on its own.
#
# Refused first path segments: data/, research/, logs/, sop/, fleet/ and the file
# RUNLOG.md. Rule 3 names the first three; D-03 as this fleet extends it adds
# sop/ and fleet/ (private planning material of the same class) and RUNLOG.md
# (it names fleet/ paths and step internals). Refusing more than rule 3 names is
# safe. Refusing less is not.
#
# app/data/ and tests/data/ are source, not data, and are NOT refused: the match
# is on the first path segment, so `app/data/park_factors.csv` passes and
# `data/raw/x.parquet` does not.
#
# Deletions are not refused (--diff-filter=ACMR). Removing a tracked data path
# with `git rm --cached` is how a violation gets fixed, so the fix must commit.
#
# Usage:
#   .git/hooks/pre-commit                  git's own call: read the staged list,
#                                          refuse raw data, then chain
#   .git/hooks/pre-commit --check PATH...  check the named paths only, no chain
# The --check form is what tests/unit/test_layout.py drives. It reads no index
# and runs no other hook, so it cannot alter the repository.
#
# Exit 0 clean, 1 on a refused path. POSIX sh. No network, no package load.

set -u

HOOK_DIR=$(dirname "$0")
CHAIN="$HOOK_DIR/pre-commit.framework"

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
    CHECK_ONLY=1
    shift
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
    if [ "$#" -gt 0 ]; then
        PATHS=$(printf '%s\n' "$@")
    else
        PATHS=""
    fi
else
    PATHS=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
fi

HITS=""
if [ -n "$PATHS" ]; then
    # IFS is newline only so a path with a space in it survives the loop.
    OLD_IFS=$IFS
    IFS='
'
    for path in $PATHS; do
        [ -n "$path" ] || continue
        # Strip a leading ./ so `./data/x` and `data/x` are the same path.
        case "$path" in ./*) path=${path#./} ;; esac
        # The glob list is expanded by `case` itself, which IFS does not affect.
        case "$path" in
            data/*|research/*|logs/*|sop/*|fleet/*|RUNLOG.md)
                HITS="$HITS$path
"
                ;;
        esac
    done
    IFS=$OLD_IFS
fi

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

# --check is a check, not a commit. It stops here and runs no other hook.
[ "$CHECK_ONLY" -eq 1 ] && exit 0

# Chain to the pre-commit framework hook that W1.13 installed, if it is present.
if [ -x "$CHAIN" ]; then
    exec "$CHAIN" "$@"
fi

exit 0
