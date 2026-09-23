#!/bin/sh
# ops/unseal.sh -- SOP step W2.4, section 2.4. The body of `make unseal`.
#
# The one-way door out of the sealed regime. It refuses unless all six of the
# phase 5 preconditions it can check from here hold at once:
#
#   1. PREREGISTRATION.md is committed (present at HEAD, not merely on disk);
#   2. the tag prereg-v1 is an ancestor of HEAD;
#   3. `git status --porcelain` is empty;
#   4. ABS_SEAL_UNLOCK is set, in this shell, to the documented value 1;
#   5. the tag exists on origin, read back from the git host itself;
#   6. the local tag ref is the same object as the one on origin.
#
# Conditions 1 to 3 are the three SOP W2.4 lists. Conditions 4 to 6 are three of
# the six SOP phase 5 lists (SOP-final.md, phase 5, items 2 and 6), added here
# because a gate that writes the public record of the ceremony has to check the
# things that make the ceremony real. Without them the door could be opened with
# four local commands and a tag that no one else could ever see, and the UNSEALED
# line would be written anyway.
#
# A failed request to the git host is a FAILED CHECK, never a pass. If gh is
# missing, unauthenticated, offline or slow, condition 5 refuses. The gate is
# shut by default and opens only on a positive answer.
#
# THIS SCRIPT NEVER CREATES THE TAG. There is no `git tag <name>` anywhere in
# it, and it rejects any argument that asks for one. The tag comes from
# ops/preregister.sh, the one-way door, and from nowhere else; a tag made by
# hand is exactly the forgery condition 5 exists to catch.
#
# THIS SCRIPT NEVER SETS ABS_SEAL_UNLOCK. SOP rule 0.5.1: only the owner sets
# it, in one shell, after the W9.7 ceremony, with a dated DECISIONS.md line. It
# only reads it. Note that ops/seal_check.sh fails if that variable is set: that
# is the agent-shell rule, and it is not in tension with this one. An agent shell
# never carries the variable, and the owner's one ceremony shell is the only
# place this script is ever meant to run.
#
# On success it writes quality/receipts/unseal-<tag>.log and then appends one
# UNSEALED line to docs/prereg/SEAL.md carrying the
# UTC timestamp, the Europe/Madrid timestamp and the tag's commit SHA. It
# appends with >> and never rewrites that file.
#
# Usage:
#   bash ops/unseal.sh            run the gate; on success append the line
#   bash ops/unseal.sh --check    run the gate and report; append nothing
#
# Exit: 0 the gate passes, 1 the gate refuses, 2 the arguments are wrong.
#
# It reads no data, opens no database and reads no 2026 datum, so it is safe to
# run in any phase, including phase 01. Condition 5 is the one request it makes,
# and it asks the git host for a tag, not a feed for a row.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2

# SOP resolution table: the literal tag string is prereg-v1, not prereg-v1.0.
# It is the same string as prereg_tag in config/seal.yml and as the tag named
# in quality/sql/analysis_set.sql.
TAG="prereg-v1"
PREREG="PREREGISTRATION.md"
SEAL_DOC="docs/prereg/SEAL.md"
RECEIPT_DIR="quality/receipts"
REMOTE="origin"
UNLOCK_ENV="ABS_SEAL_UNLOCK"
UNLOCK_VALUE="1"
TOTAL=6

check_only=0
case "${1:-}" in
  --check) check_only=1 ;;
  -h|--help)
    sed -n '2,48p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") : ;;
  --tag|-t|tag|--preregister|--create-tag)
    echo "unseal: this script never creates a tag. $TAG comes from ops/preregister.sh," >&2
    echo "unseal: the one-way door, and from nowhere else." >&2
    exit 2
    ;;
  *)
    echo "unseal: unknown argument: $1 (expected --check or nothing)" >&2
    exit 2
    ;;
esac

fails=0

refuse() {
  echo "UNSEAL REFUSED $1/$TOTAL: $2" >&2
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
  refuse 1 "HEAD does not exist yet; there is no commit to check $PREREG against"
elif ! git cat-file -e "HEAD:$PREREG" 2>/dev/null; then
  refuse 1 "$PREREG is not committed at HEAD"
fi

# ---------------------------------------------------------------- condition 2
tag_sha=""
tag_object=""
if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
  refuse 2 "tag $TAG does not exist"
else
  tag_object=$(git rev-parse "refs/tags/$TAG" 2>/dev/null || echo "")
  tag_sha=$(git rev-list -n 1 "$TAG" 2>/dev/null || echo "")
  if [ -z "$tag_sha" ]; then
    refuse 2 "tag $TAG does not resolve to a commit"
  elif ! git rev-parse -q --verify HEAD >/dev/null 2>&1; then
    : # already reported as condition 1
  elif ! git merge-base --is-ancestor "$tag_sha" HEAD 2>/dev/null; then
    refuse 2 "tag $TAG ($tag_sha) is not an ancestor of HEAD"
  fi
fi

# ---------------------------------------------------------------- condition 3
dirty=$(git status --porcelain 2>/dev/null)
if [ -n "$dirty" ]; then
  n=$(printf '%s\n' "$dirty" | wc -l | tr -d ' ')
  refuse 3 "git status --porcelain is not empty ($n path(s)); commit or clean first"
fi

# ---------------------------------------------------------------- condition 4
# The documented value is the string 1 and nothing else. Set-but-empty, "true",
# "yes" and "0" are all refusals: the SOP writes ABS_SEAL_UNLOCK=1.
if [ "${ABS_SEAL_UNLOCK:-}" != "$UNLOCK_VALUE" ]; then
  if [ -z "${ABS_SEAL_UNLOCK:-}" ]; then
    refuse 4 "$UNLOCK_ENV is not set; the owner sets it to $UNLOCK_VALUE in one shell, after the ceremony"
  else
    refuse 4 "$UNLOCK_ENV is set to something other than $UNLOCK_VALUE"
  fi
fi

# ------------------------------------------------------------ conditions 5, 6
# The pre-registration must be PUBLIC, not merely local. Ask the git host for
# the tag and compare the object it names with the local ref. Any failure to get
# an answer -- no gh, not logged in, offline, empty repository, 404 -- refuses.
remote_sha=""
remote_why=""
origin_url=$(git remote get-url "$REMOTE" 2>/dev/null || echo "")
if [ -z "$origin_url" ]; then
  remote_why="no remote named $REMOTE"
else
  slug=$(printf '%s' "$origin_url" \
    | sed -e 's#^git@[^:]*:##' -e 's#^ssh://git@[^/]*/##' -e 's#^https\{0,1\}://[^/]*/##' -e 's#\.git$##')
  case "$slug" in
    */*) : ;;
    *) slug="" ;;
  esac
  if [ -z "$slug" ]; then
    remote_why="cannot read an owner/repo out of $origin_url"
  elif ! command -v gh >/dev/null 2>&1; then
    remote_why="gh is not installed, so the tag on $REMOTE cannot be read back"
  else
    # gh prints the error BODY to stdout on a 404, a 409 (empty repository) or
    # an auth failure, so a non-empty answer is not an answer. The reply counts
    # only if gh exited 0 and the text is a bare object name: 40 hex characters,
    # or 64 in a sha256 repository. Anything else is a failed check.
    if ! remote_sha=$(gh api "repos/$slug/git/ref/tags/$TAG" --jq '.object.sha' 2>/dev/null); then
      remote_sha=""
    fi
    remote_sha=$(printf '%s' "$remote_sha" | tr -d '[:space:]')
    case "$remote_sha" in
      *[!0-9a-f]*) remote_sha="" ;;
    esac
    if [ -n "$remote_sha" ] && [ ${#remote_sha} -ne 40 ] && [ ${#remote_sha} -ne 64 ]; then
      remote_sha=""
    fi
    if [ -z "$remote_sha" ]; then
      remote_why="gh api repos/$slug/git/ref/tags/$TAG returned no object name (absent, empty repository, offline, or unauthenticated)"
    fi
  fi
fi

if [ -z "$remote_sha" ]; then
  refuse 5 "tag $TAG is not readable on $REMOTE: $remote_why"
  refuse 6 "the local tag cannot be compared with $REMOTE while condition 5 fails"
else
  if [ -z "$tag_object" ]; then
    refuse 6 "there is no local $TAG to compare with $REMOTE ($remote_sha)"
  elif [ "$remote_sha" != "$tag_object" ] && [ "$remote_sha" != "$tag_sha" ]; then
    refuse 6 "local $TAG is $tag_object but $REMOTE has $remote_sha; they are different objects"
  fi
fi

# ------------------------------------------------------- the append target
# Not one of the conditions, but success has to write somewhere, and a silent
# success that records nothing is worse than a refusal.
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
  echo "UNSEAL CHECK OK ($TOTAL/$TOTAL): $PREREG committed, $TAG is an ancestor of HEAD,"
  echo "  worktree clean, $UNLOCK_ENV=$UNLOCK_VALUE, and $TAG on $REMOTE is $remote_sha."
  echo "unseal: --check appends nothing. Run without --check to record the event."
  exit 0
fi

RECEIPT="$RECEIPT_DIR/unseal-$TAG.log"
utc=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
madrid=$(TZ=Europe/Madrid date "+%Y-%m-%d %H:%M %Z")
head_sha=$(git rev-parse HEAD)

# GD-10, the pairing half. The receipt is written BEFORE the claim, so there is
# no window in which an UNSEALED line exists with nothing behind it. It carries
# the same commit=<sha> the line carries; tests/guard/test_unseal_receipt.py
# fails if the two disagree or the receipt is absent. One receipt per tag, never
# written by hand. Closes owner item O-G1.
mkdir -p "$RECEIPT_DIR"
if [ -e "$RECEIPT" ]; then
  echo "UNSEAL REFUSED: $RECEIPT already exists; one receipt per tag." >&2
  exit 1
fi
{
  printf 'UNSEAL RECEIPT\n'
  printf 'tag=%s\n' "$TAG"
  printf 'commit=%s\n' "$tag_sha"
  printf 'head=%s\n' "$head_sha"
  printf 'remote=%s\n' "$remote_sha"
  printf 'utc=%s\n' "$utc"
  printf 'madrid=%s\n' "$madrid"
  printf 'conditions=%s/%s\n' "$TOTAL" "$TOTAL"
  printf 'written_by=ops/unseal.sh\n'
} > "$RECEIPT"

printf 'UNSEALED | utc=%s | madrid=%s | tag=%s | commit=%s | head=%s | remote=%s\n' \
  "$utc" "$madrid" "$TAG" "$tag_sha" "$head_sha" "$remote_sha" >> "$SEAL_DOC"

echo "UNSEAL OK ($TOTAL/$TOTAL). Appended one UNSEALED line to $SEAL_DOC."
echo "  receipt  = $RECEIPT"
echo "  tag $TAG = $tag_sha (on $REMOTE as $remote_sha)"
echo "  HEAD     = $head_sha"
echo "  utc      = $utc"
echo "  madrid   = $madrid"
echo
echo "Still owed before a sealed row is read, and not checked here:"
echo "  - quality/prereg.lock matches shasum -a 256 of git show $TAG:$PREREG and the annexes"
echo "  - the dated DECISIONS.md line recording the unlock and the manifest sha256"
echo "  - commit $SEAL_DOC, so the event is in history and not only on this laptop"
exit 0
