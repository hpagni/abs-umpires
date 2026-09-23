#!/bin/sh
# ops/b2_check.sh -- SOP step W1.9. The B2 canary, the body of `make canary`.
#
# WHAT THE SOP ASKS FOR, VERBATIM: uploads a 1 KB canary to
# b2://abs-umpires-raw/_canary/<utc-timestamp>.txt, downloads it, compares
# sha256, deletes it with the admin key, and asserts `b2 bucket get
# abs-umpires-raw` shows both lifecycle prefixes.
#
# THE ADMIN KEY, NOT THE CI KEY. The CI key created by ops/b2_sync.sh
# --provision carries listBuckets,readFiles,writeFiles,listFiles and no
# deleteFiles, so it cannot remove the canary it just wrote. This check is run
# with the admin key. Run with the CI key it fails at the delete, correctly.
#
# COST. Upload is Class A, download is Class B, list and get are Class C. All
# three classes are free. The canary is 1024 bytes, so storage and egress round
# to $0.00 against the 10 GB and 3x-storage free tiers.
#
# USAGE
#   bash ops/b2_check.sh              the live round trip
#   bash ops/b2_check.sh --self-test  the same logic, offline, no account
#
# --self-test proves the parts that do not need an account: the canary is
# exactly 1024 bytes, the sha256 comparison accepts an identical copy and
# rejects a one-byte change, the object key has the shape the SOP fixes, and
# the lifecycle assertion accepts a bucket carrying both prefixes and rejects
# one carrying a single prefix. It writes only under a temporary directory.
#
# CREDENTIALS ARE AN OWNER ITEM. With B2_APPLICATION_KEY_ID or
# B2_APPLICATION_KEY unset the live mode prints SKIP and exits 0, which is the
# convention .env.example states for every empty name.
#
# Exit: 0 pass or skip, 1 a failed assertion, 2 misuse.
# POSIX sh. No HTTP call site: every remote move is a b2 subcommand.

set -u

BUCKET=${B2_BUCKET:-abs-umpires-raw}
CANARY_PREFIX=_canary
CANARY_BYTES=1024
KEY_SHAPE='^_canary/[0-9]{8}T[0-9]{6}Z\.txt$'

mode=live
for arg in "$@"; do
    case "$arg" in
        --self-test) mode=selftest ;;
        -h|--help)   sed -n '2,35p' "$0"; exit 0 ;;
        *) printf 'b2_check: unknown argument: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2

fail() {
    printf 'CANARY FAIL: %s\n' "$1" >&2
    exit 1
}

sha256_of() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{ print $1 }'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{ print $1 }'
    else
        printf 'b2_check: no sha256 tool on PATH\n' >&2
        return 1
    fi
}

# Write exactly CANARY_BYTES bytes: two labelled lines, then a pad of dots.
canary_write() {
    _dest=$1
    _stamp=$2
    {
        printf 'abs-umpires B2 canary %s\n' "$_stamp"
        printf 'SOP W1.9. One kilobyte up, down, compared, deleted.\n'
    } > "$_dest" || return 1
    _have=$(wc -c < "$_dest" | tr -d ' ')
    if [ "$_have" -gt "$CANARY_BYTES" ]; then
        return 1
    fi
    _pad=$((CANARY_BYTES - _have))
    if [ "$_pad" -gt 0 ]; then
        printf '%*s' "$_pad" '' | tr ' ' '.' >> "$_dest" || return 1
    fi
    _have=$(wc -c < "$_dest" | tr -d ' ')
    [ "$_have" -eq "$CANARY_BYTES" ]
}

# Both lifecycle prefixes, and exactly those two: "" for the whole bucket and
# "interim/" for the derived tree. Reads the JSON `b2 bucket get` prints.
lifecycle_both_prefixes() {
    _json=$1
    _n=$(printf '%s' "$_json" | jq -r '(.lifecycleRules // []) | length' 2>/dev/null)
    _root=$(printf '%s' "$_json" | jq -r \
        '[(.lifecycleRules // [])[] | select(.fileNamePrefix == "")] | length' 2>/dev/null)
    _interim=$(printf '%s' "$_json" | jq -r \
        '[(.lifecycleRules // [])[] | select(.fileNamePrefix == "interim/")] | length' 2>/dev/null)
    [ "${_n:-0}" = "2" ] && [ "${_root:-0}" = "1" ] && [ "${_interim:-0}" = "1" ]
}

tmp=$(mktemp -d "${TMPDIR:-/tmp}/b2canary.XXXXXX") || exit 2

# ---------------------------------------------------------------- self-test --
if [ "$mode" = selftest ]; then
    trap 'rm -rf "$tmp"' EXIT INT TERM
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    key="$CANARY_PREFIX/$stamp.txt"
    checks=0

    canary_write "$tmp/canary.txt" "$stamp" || fail "the canary is not $CANARY_BYTES bytes"
    checks=$((checks + 1))

    cp "$tmp/canary.txt" "$tmp/back.txt" || fail "could not copy the canary"
    up=$(sha256_of "$tmp/canary.txt") || fail "no sha256 for the canary"
    down=$(sha256_of "$tmp/back.txt") || fail "no sha256 for the copy"
    [ -n "$up" ] || fail "the sha256 of the canary is empty"
    [ "$up" = "$down" ] || fail "an identical copy did not compare equal"
    checks=$((checks + 1))

    printf 'x' >> "$tmp/back.txt"
    bad=$(sha256_of "$tmp/back.txt") || fail "no sha256 for the altered copy"
    [ "$up" != "$bad" ] || fail "a one-byte change compared equal"
    checks=$((checks + 1))

    printf '%s\n' "$key" | grep -Eq "$KEY_SHAPE" || fail "the object key shape is wrong: $key"
    checks=$((checks + 1))

    both='{"lifecycleRules":[{"fileNamePrefix":"","daysFromUploadingToHiding":null,"daysFromHidingToDeleting":30},{"fileNamePrefix":"interim/","daysFromUploadingToHiding":90,"daysFromHidingToDeleting":7}]}'
    one='{"lifecycleRules":[{"fileNamePrefix":"","daysFromUploadingToHiding":null,"daysFromHidingToDeleting":30}]}'
    lifecycle_both_prefixes "$both" || fail "both lifecycle prefixes were not recognised"
    checks=$((checks + 1))
    if lifecycle_both_prefixes "$one"; then
        fail "a bucket with one lifecycle prefix passed"
    fi
    checks=$((checks + 1))

    printf 'CANARY SELF-TEST OK (%s/6), key %s, %s bytes\n' "$checks" "$key" "$CANARY_BYTES"
    exit 0
fi

# --------------------------------------------------------------------- live --
if [ -z "${B2_APPLICATION_KEY_ID:-}" ] || [ -z "${B2_APPLICATION_KEY:-}" ]; then
    rm -rf "$tmp"
    printf 'CANARY SKIP: B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY are unset.\n'
    printf 'CANARY SKIP: the round trip needs the admin key. Run bash ops/b2_check.sh --self-test for the offline half.\n'
    exit 0
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
key="$CANARY_PREFIX/$stamp.txt"
uploaded=0

cleanup() {
    if [ "$uploaded" -eq 1 ]; then
        uv run b2 rm --versions --no-progress "b2://$BUCKET/$key" >/dev/null 2>&1
    fi
    rm -rf "$tmp"
}
trap cleanup EXIT INT TERM

uv run b2 account authorize "$B2_APPLICATION_KEY_ID" "$B2_APPLICATION_KEY" >/dev/null \
    || fail "could not authorize the account"

canary_write "$tmp/canary.txt" "$stamp" || fail "the canary is not $CANARY_BYTES bytes"
up=$(sha256_of "$tmp/canary.txt") || fail "no sha256 for the canary"

uv run b2 file upload --no-progress "$BUCKET" "$tmp/canary.txt" "$key" >/dev/null \
    || fail "upload failed for $key"
uploaded=1

uv run b2 file download --no-progress "b2://$BUCKET/$key" "$tmp/back.txt" >/dev/null \
    || fail "download failed for $key"

down=$(sha256_of "$tmp/back.txt") || fail "no sha256 for the downloaded copy"
[ "$up" = "$down" ] || fail "sha256 mismatch: sent $up, got back $down"

uv run b2 rm --versions --no-progress "b2://$BUCKET/$key" >/dev/null \
    || fail "delete failed for $key. The admin key is required; the CI key has no deleteFiles."
uploaded=0

info=$(uv run b2 bucket get "$BUCKET") || fail "could not read the bucket"
lifecycle_both_prefixes "$info" \
    || fail "b2 bucket get $BUCKET does not show exactly the two lifecycle prefixes, \"\" and interim/"

printf 'CANARY OK: %s bytes to b2://%s/%s, sha256 %s, deleted, both lifecycle prefixes present.\n' \
    "$CANARY_BYTES" "$BUCKET" "$key" "$up"
