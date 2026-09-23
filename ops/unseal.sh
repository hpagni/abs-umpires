#!/bin/sh
# ops/unseal.sh -- SOP step W2.4, section 2.4. The body of `make unseal`.
#
# The one-way door out of the sealed regime. It refuses unless all three of the
# conditions SOP W2.4 names hold:
#
#   1. PREREGISTRATION.md is committed (present at HEAD, not merely on disk);
#   2. the tag prereg-v1 is an ancestor of HEAD;
#   3. `git status --porcelain` is empty.
#
# On success it appends one UNSEALED line to docs/prereg/SEAL.md carrying the
# UTC timestamp, the Europe/Madrid timestamp and the tag's commit SHA. It
# appends with >> and never rewrites that file.
#
# This script NEVER sets ABS_SEAL_UNLOCK. SOP rule 0.5.1: only the owner sets
# it, in one shell, after the W9.7 ceremony. This gate is the repository-state
# half of the door. The other half is `absump.seal._unlocked()`, which checks
# all six preconditions of SOP phase 5 -- the three above plus the tag being
# pushed to origin, quality/prereg.lock matching the tagged PREREGISTRATION.md,
# and the owner's own ABS_SEAL_UNLOCK shell with its dated DECISIONS.md line.
# Passing this script is necessary, not sufficient.
#
# Usage:
#   bash ops/unseal.sh            run the gate; on success append the line
#   bash ops/unseal.sh --check    run the gate and report; append nothing
#
# Exit: 0 the gate passes, 1 the gate refuses, 2 the arguments are wrong.
#
# It reads no data, opens no database and issues no request, so it is safe to
# run in any phase, including phase 01 where reading a 2026 datum is forbidden.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2

# SOP resolution table: the literal tag string is prereg-v1, not prereg-v1.0.
# It is the same string as prereg_tag in config/seal.yml and as the tag named
# in quality/sql/analysis_set.sql.
TAG="prereg-v1"
PREREG="PREREGISTRATION.md"
SEAL_DOC="docs/prereg/SEAL.md"

check_only=0
case "${1:-}" in
  --check) check_only=1 ;;
  -h|--help)
    sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") : ;;
  *)
    echo "unseal: unknown argument: $1 (expected --check or nothing)" >&2
    exit 2
    ;;
esac

fails=0

refuse() {
  echo "UNSEAL REFUSED $1: $2" >&2
  fails=$((fails + 1))
}

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "UNSEAL REFUSED: $root is not a git repository" >&2
  exit 1
fi

# ---------------------------------------------------------------- condition 1
# Committed means present at HEAD. A PREREGISTRATION.md that exists only in the
# working tree can still be edited after the fact, which is the whole thing the
# pre-registration is supposed to make impossible.
if ! git rev-parse -q --verify HEAD >/dev/null 2>&1; then
  refuse "1/3" "HEAD does not exist yet; there is no commit to check $PREREG against"
elif ! git cat-file -e "HEAD:$PREREG" 2>/dev/null; then
  refuse "1/3" "$PREREG is not committed at HEAD"
fi

# ---------------------------------------------------------------- condition 2
tag_sha=""
if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
  refuse "2/3" "tag $TAG does not exist"
else
  tag_sha=$(git rev-list -n 1 "$TAG" 2>/dev/null || echo "")
  if [ -z "$tag_sha" ]; then
    refuse "2/3" "tag $TAG does not resolve to a commit"
  elif ! git rev-parse -q --verify HEAD >/dev/null 2>&1; then
    : # already reported as condition 1
  elif ! git merge-base --is-ancestor "$tag_sha" HEAD 2>/dev/null; then
    refuse "2/3" "tag $TAG ($tag_sha) is not an ancestor of HEAD"
  fi
fi

# ---------------------------------------------------------------- condition 3
dirty=$(git status --porcelain 2>/dev/null)
if [ -n "$dirty" ]; then
  n=$(printf '%s\n' "$dirty" | wc -l | tr -d ' ')
  refuse "3/3" "git status --porcelain is not empty ($n path(s)); commit or clean first"
fi

# ------------------------------------------------------- the append target
# Not one of the SOP's three conditions, but success has to write somewhere,
# and a silent success that records nothing is worse than a refusal.
if [ ! -f "$SEAL_DOC" ]; then
  refuse "append" "$SEAL_DOC does not exist; the seal log is the record of this event"
elif [ -n "$tag_sha" ] && grep -q "^UNSEALED .*commit=$tag_sha" "$SEAL_DOC" 2>/dev/null; then
  # The unseal happens once and never twice (SOP phase 5). A second run against
  # the same tag is a mistake, so it refuses rather than logging a duplicate.
  refuse "once" "$SEAL_DOC already records an UNSEALED line for $TAG ($tag_sha)"
fi

if [ "$fails" -ne 0 ]; then
  echo "UNSEAL REFUSED ($fails failing condition(s)). Nothing was written." >&2
  exit 1
fi

if [ "$check_only" -eq 1 ]; then
  echo "UNSEAL CHECK OK (3/3): $PREREG committed, $TAG is an ancestor of HEAD, worktree clean."
  echo "unseal: --check appends nothing. Run without --check to record the event."
  exit 0
fi

utc=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
madrid=$(TZ=Europe/Madrid date "+%Y-%m-%d %H:%M %Z")
head_sha=$(git rev-parse HEAD)

printf 'UNSEALED | utc=%s | madrid=%s | tag=%s | commit=%s | head=%s\n' \
  "$utc" "$madrid" "$TAG" "$tag_sha" "$head_sha" >> "$SEAL_DOC"

echo "UNSEAL OK (3/3). Appended one UNSEALED line to $SEAL_DOC."
echo "  tag $TAG = $tag_sha"
echo "  HEAD     = $head_sha"
echo "  utc      = $utc"
echo "  madrid   = $madrid"
echo
echo "Still owed before a sealed row is read, and not checked here:"
echo "  - the tag is pushed: git ls-remote --tags origin refs/tags/$TAG matches $tag_sha"
echo "  - quality/prereg.lock matches shasum -a 256 of git show $TAG:$PREREG and the annexes"
echo "  - the owner sets ABS_SEAL_UNLOCK=1 in one shell and appends the dated line to DECISIONS.md"
echo "  - commit $SEAL_DOC, so the event is in history and not only on this laptop"
exit 0
