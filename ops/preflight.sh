#!/bin/sh
# ops/preflight.sh -- SOP step W1.1, preflight and disk floor.
#
# Asserts, in order:
#   1. at least 15 GiB free on /System/Volumes/Data
#   2. uv R Rscript duckdb git gh jq curl make are all on PATH
#   3. DYLD_LIBRARY_PATH is empty
#   4. ~/.cmdstan/cmdstan-2.40.0 exists
# Prints PREFLIGHT OK and exits 0 when every check passes. Exits 1 otherwise,
# after reporting every failed check, not only the first.
#
# POSIX sh. No bashisms. Runs in well under 5 s: no network, no package load.
# This is the first line of every make target that touches disk.
#
# The 15 GiB floor is the SOP's (W1.1, and risk R-25: free disk is 57 GiB, not
# 65). It is not derived from any endpoint. W6.0 adds about 0.5 GB and W2.6
# about 0.19 GB on later nights, so the floor is asserted on every run rather
# than assumed from the 2026-09-22 machine audit.
#
# Usage: ops/preflight.sh [-q|--quiet]
#   -q  print only failures and the final PREFLIGHT OK line.

set -u

FLOOR_GIB=15
FLOOR_KIB=15728640          # 15 * 1024 * 1024
DATA_VOLUME=/System/Volumes/Data
CMDSTAN_DIR="$HOME/.cmdstan/cmdstan-2.40.0"
REQUIRED_TOOLS="uv R Rscript duckdb git gh jq curl make"

QUIET=0
for arg in "$@"; do
    case "$arg" in
        -q|--quiet) QUIET=1 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            printf 'preflight: unknown argument: %s\n' "$arg" >&2
            exit 2
            ;;
    esac
done

FAILURES=0

say() {
    # informational line, suppressed by --quiet
    if [ "$QUIET" -eq 0 ]; then
        printf '%s\n' "$1"
    fi
}

fail() {
    printf 'FAIL  %s\n' "$1" >&2
    FAILURES=$((FAILURES + 1))
}

# --- check 1: disk floor on /System/Volumes/Data ------------------------------

if [ ! -d "$DATA_VOLUME" ]; then
    fail "disk: $DATA_VOLUME does not exist (expected macOS data volume)"
else
    FREE_KIB=$(df -Pk "$DATA_VOLUME" 2>/dev/null | awk 'NR==2 {print $4}')
    case "$FREE_KIB" in
        ''|*[!0-9]*)
            fail "disk: could not read free space on $DATA_VOLUME"
            ;;
        *)
            FREE_GIB_INT=$((FREE_KIB / 1048576))
            FREE_GIB_TENTH=$(((FREE_KIB % 1048576) * 10 / 1048576))
            if [ "$FREE_KIB" -lt "$FLOOR_KIB" ]; then
                fail "disk: ${FREE_GIB_INT}.${FREE_GIB_TENTH} GiB free on $DATA_VOLUME, floor is ${FLOOR_GIB} GiB"
            else
                say "ok    disk: ${FREE_GIB_INT}.${FREE_GIB_TENTH} GiB free on $DATA_VOLUME (floor ${FLOOR_GIB} GiB)"
            fi
            ;;
    esac
fi

# --- check 2: required tools on PATH ------------------------------------------

for tool in $REQUIRED_TOOLS; do
    tool_path=$(command -v "$tool" 2>/dev/null) || tool_path=""
    if [ -z "$tool_path" ]; then
        fail "path: $tool is not on PATH"
    else
        say "ok    path: $tool -> $tool_path"
    fi
done

# GNU Make 3.81 is what ships with macOS and what the Makefile is written to
# (risk R-23: a Make 4 Makefile mis-executes under 3.81). Reported, not asserted.
if command -v make >/dev/null 2>&1; then
    MAKE_VERSION=$(make --version 2>/dev/null | head -1)
    say "info  make: ${MAKE_VERSION:-unknown}"
fi

# --- check 3: DYLD_LIBRARY_PATH is empty --------------------------------------
#
# Caveat, verified on this machine on 2026-09-23 with SIP enabled: macOS purges
# DYLD_* from the environment of a protected binary, and /bin/sh, /bin/dash,
# /usr/bin/env, /usr/bin/make and R's own launcher script are all protected. So
# a value set by the caller is already gone by the time this script starts, and
# gone again before R or CmdStan load a dylib. The check below is therefore a
# floor: it catches the case that matters on a machine with SIP disabled, and it
# passes trivially under SIP. Reading the caller's value out of the parent
# process with `ps -E` was tried and rejected: it reported a stale value when
# nothing was set and nothing when the variable was set through make, so it
# would make this gate flaky in both directions.

if [ -n "${DYLD_LIBRARY_PATH:-}" ]; then
    fail "env: DYLD_LIBRARY_PATH is set to '${DYLD_LIBRARY_PATH}', it must be empty"
else
    say "ok    env: DYLD_LIBRARY_PATH is empty"
fi

# --- check 4: CmdStan 2.40.0 present ------------------------------------------

if [ ! -d "$CMDSTAN_DIR" ]; then
    fail "cmdstan: $CMDSTAN_DIR does not exist"
else
    say "ok    cmdstan: $CMDSTAN_DIR"
fi

# --- verdict ------------------------------------------------------------------

if [ "$FAILURES" -ne 0 ]; then
    printf 'PREFLIGHT FAILED (%d check(s))\n' "$FAILURES" >&2
    exit 1
fi

printf 'PREFLIGHT OK\n'
exit 0
