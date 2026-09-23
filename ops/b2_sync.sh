#!/bin/sh
# ops/b2_sync.sh -- SOP step W1.9. The Backblaze B2 private mirror of data/raw.
#
# WHY B2 AND NOT A GITHUB RELEASE. hpagni/abs-umpires is a public repository, so
# a Release asset is world-readable, and a world-readable asset of MLB-derived
# raw bytes is redistribution. A private bucket is not. Verified pricing
# 2026-09-22: $6.95/TB/month ($0.00695/GB/month), first 10 GB always free, free
# egress up to 3x average monthly storage then $0.01/GB, Class A/B/C API calls
# free, Class D $0.004 per 10,000 with the first 2,500/day free. At the
# project's ~7 GB the bill is $0.00.
#
# THE FOUR COMMANDS, VERBATIM FROM SOP W1.9. This script runs them and nothing
# else. The defaults below reproduce the last line byte for byte.
#
#   uv run b2 account authorize "$B2_APPLICATION_KEY_ID" "$B2_APPLICATION_KEY"
#   uv run b2 bucket create abs-umpires-raw allPrivate \
#     --lifecycle-rule '{"fileNamePrefix":"","daysFromUploadingToHiding":null,"daysFromHidingToDeleting":30}' \
#     --lifecycle-rule '{"fileNamePrefix":"interim/","daysFromUploadingToHiding":90,"daysFromHidingToDeleting":7}' \
#     --default-server-side-encryption SSE-B2
#   uv run b2 key create --bucket abs-umpires-raw abs-umpires-ci listBuckets,readFiles,writeFiles,listFiles
#   uv run b2 sync --delete --threads 4 data/raw b2://abs-umpires-raw/raw
#
# THE CI KEY HAS NO deleteFiles. That is deliberate and it interacts with
# --delete: raw bytes are immutable under SOP section 2.3, so a sync that has
# something to delete is a sync that should stop. With the CI key it stops,
# because the capability is absent. Only the admin key can remove a remote
# object, and only by hand.
#
# NEVER MIRRORED, CHECKED BEFORE ANYTHING IS SENT. Two things must never leave
# this machine: the plain held-out partition, and the DuckDB file. Neither
# lives under data/raw, so the SOP command already excludes them by scope. This
# script adds a refusal rather than an exclusion: an exclusion ships a partial
# mirror in silence, a refusal stops and names the path. Exit 1, nothing sent.
#
# USAGE
#   bash ops/b2_sync.sh                 mirror data/raw to the bucket
#   bash ops/b2_sync.sh --dry-run       print the plan, send nothing
#   bash ops/b2_sync.sh --provision     create the bucket and the CI key
#   bash ops/b2_sync.sh --provision --dry-run
#                                       print the provisioning commands
#   bash ops/b2_sync.sh --dry-run --source=DIR
#                                       plan against another tree. Rehearsal
#                                       only: --source is refused without
#                                       --dry-run, so it can never send.
#
# CREDENTIALS ARE AN OWNER ITEM. With B2_APPLICATION_KEY_ID or
# B2_APPLICATION_KEY unset the script prints DEFERRED and exits 0. The local
# plan is still computed and printed, because it needs no account.
#
# Exit: 0 done or deferred, 1 a refusal or a failed command, 2 misuse.
# POSIX sh. No HTTP call site: every remote move is a b2 subcommand.

set -u

BUCKET=${B2_BUCKET:-abs-umpires-raw}
PREFIX=raw
CI_KEY_NAME=abs-umpires-ci
CI_KEY_CAPS=listBuckets,readFiles,writeFiles,listFiles
LIFECYCLE_ROOT='{"fileNamePrefix":"","daysFromUploadingToHiding":null,"daysFromHidingToDeleting":30}'
LIFECYCLE_INTERIM='{"fileNamePrefix":"interim/","daysFromUploadingToHiding":90,"daysFromHidingToDeleting":7}'
SSE=SSE-B2
THREADS=4

# The two paths that must never be mirrored, as extended regular expressions
# tested against the full path of every candidate file.
PLAIN_RE='(^|/)sealed/plain(/|$)'
DUCKDB_RE='\.duckdb(-wal|\.wal)?$'

PLAN_LIST_MAX=50

dry=0
mode=sync
source_arg=""

for arg in "$@"; do
    case "$arg" in
        --dry-run)   dry=1 ;;
        --provision) mode=provision ;;
        --source=*)  source_arg=${arg#--source=} ;;
        -h|--help)   sed -n '2,50p' "$0"; exit 0 ;;
        *) printf 'b2_sync: unknown argument: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2

if [ -n "$source_arg" ] && [ "$dry" -eq 0 ]; then
    printf 'b2_sync: --source is accepted only with --dry-run\n' >&2
    exit 2
fi

src=${source_arg:-data/$PREFIX}

have_creds=0
if [ -n "${B2_APPLICATION_KEY_ID:-}" ] && [ -n "${B2_APPLICATION_KEY:-}" ]; then
    have_creds=1
fi

deferred() {
    printf 'DEFERRED: B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY are unset.\n'
    printf 'DEFERRED: %s\n' "$1"
    printf 'DEFERRED: the owner sets both in .env, which is gitignored. No key is ever written into the repository.\n'
}

authorize() {
    uv run b2 account authorize "$B2_APPLICATION_KEY_ID" "$B2_APPLICATION_KEY"
}

# ---------------------------------------------------------------- provision --
if [ "$mode" = provision ]; then
    printf 'b2_sync: provision, bucket %s\n' "$BUCKET"
    printf 'command: uv run b2 bucket create %s allPrivate --lifecycle-rule %s --lifecycle-rule %s --default-server-side-encryption %s\n' \
        "$BUCKET" "$LIFECYCLE_ROOT" "$LIFECYCLE_INTERIM" "$SSE"
    printf 'command: uv run b2 key create --bucket %s %s %s\n' \
        "$BUCKET" "$CI_KEY_NAME" "$CI_KEY_CAPS"
    printf 'note: the CI key capability list has no deleteFiles.\n'
    if [ "$dry" -eq 1 ]; then
        printf 'b2_sync: dry run, nothing sent.\n'
        exit 0
    fi
    if [ "$have_creds" -eq 0 ]; then
        deferred "provisioning needs the admin key once. Nothing was created."
        exit 0
    fi
    authorize || exit 1
    uv run b2 bucket create "$BUCKET" allPrivate \
        --lifecycle-rule "$LIFECYCLE_ROOT" \
        --lifecycle-rule "$LIFECYCLE_INTERIM" \
        --default-server-side-encryption "$SSE" || exit 1
    printf 'b2_sync: the next line prints the CI key secret once. Put it in .env. Never in the repository.\n'
    uv run b2 key create --bucket "$BUCKET" "$CI_KEY_NAME" "$CI_KEY_CAPS" || exit 1
    printf 'b2_sync: provisioned.\n'
    exit 0
fi

# ----------------------------------------------------------------- the plan --
if [ ! -d "$src" ]; then
    printf 'b2_sync: no such directory: %s\n' "$src" >&2
    exit 1
fi

printf 'b2_sync: source %s\n' "$src"
printf 'b2_sync: destination b2://%s/%s\n' "$BUCKET" "$PREFIX"

# The refusal runs before the plan is printed and before anything is sent.
plain_hits=$(find "$src" -type f 2>/dev/null | grep -E "$PLAIN_RE" | sort)
db_hits=$(find "$src" -type f 2>/dev/null | grep -E "$DUCKDB_RE" | sort)

if [ -n "$plain_hits" ] || [ -n "$db_hits" ]; then
    printf 'b2_sync: REFUSED. A path under the source is one this mirror never carries.\n' >&2
    if [ -n "$plain_hits" ]; then
        printf '%s\n' "$plain_hits" | sed 's/^/  held-out plain partition: /' >&2
    fi
    if [ -n "$db_hits" ]; then
        printf '%s\n' "$db_hits" | sed 's/^/  duckdb file: /' >&2
    fi
    printf 'b2_sync: nothing was sent. Move the path out of the source tree and run again.\n' >&2
    exit 1
fi

files=$(find "$src" -type f 2>/dev/null | sort)
if [ -z "$files" ]; then
    count=0
    bytes=0
else
    count=$(printf '%s\n' "$files" | wc -l | tr -d ' ')
    bytes=$(printf '%s\n' "$files" | tr '\n' '\0' | xargs -0 wc -c 2>/dev/null \
            | awk 'NF == 2 && $2 == "total" { next } { s += $1 } END { printf "%d\n", s + 0 }')
fi

printf 'b2_sync: never-mirror check OK (0 held-out plain paths, 0 duckdb files)\n'
printf 'b2_sync: plan %s file(s), %s byte(s)\n' "$count" "$bytes"
if [ "$count" -gt 0 ]; then
    printf '%s\n' "$files" | head -n "$PLAN_LIST_MAX" | sed 's/^/  upload /'
    if [ "$count" -gt "$PLAN_LIST_MAX" ]; then
        printf '  ... and %s more\n' "$((count - PLAN_LIST_MAX))"
    fi
else
    printf '  the source tree is empty. The overnight pulls have not landed yet.\n'
fi

printf 'command: uv run b2 sync --delete --threads %s %s b2://%s/%s\n' \
    "$THREADS" "$src" "$BUCKET" "$PREFIX"

# ------------------------------------------------------------------ execute --
if [ "$have_creds" -eq 0 ]; then
    if [ "$dry" -eq 1 ]; then
        deferred "the b2 side of the dry run needs an account: b2 authorizes before it plans."
    else
        deferred "nothing was mirrored."
    fi
    exit 0
fi

authorize || exit 1

if [ "$dry" -eq 1 ]; then
    uv run b2 sync --dry-run --no-progress --delete --threads "$THREADS" \
        "$src" "b2://$BUCKET/$PREFIX"
    exit $?
fi

uv run b2 sync --delete --threads "$THREADS" "$src" "b2://$BUCKET/$PREFIX"
rc=$?
if [ "$rc" -eq 0 ]; then
    printf 'b2_sync: mirrored %s file(s).\n' "$count"
fi
exit "$rc"
