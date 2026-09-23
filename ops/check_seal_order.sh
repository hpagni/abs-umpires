#!/bin/sh
# ops/check_seal_order.sh -- SOP step W1.8, decision D-67, test GD-12.
#
# Ordering, not just scope. Every other layer of the guard is keyed to held-out
# rows: GD-02 demands prereg-v1 ancestry only for an artifact whose
# max_official_date is past 2026-09-21, and absump.seal._unlocked() gates only
# the held-out read. The sprint fits entirely on data through 2026-09-21, so
# none of that stops the tag from being written AFTER the fits that produce
# every number in the abstract. The pre-registration sentence would then be
# false with every test green (risk R-47).
#
# This script closes that hole. It asserts that EVERY fit receipt under out/,
# open or held out, carries a git_sha descending from the PUSHED prereg-v1 tag.
#
# A fit receipt is out/**/provenance.json (SOP section 1.4: provenance.json is
# canonical; out/ch1/log/fit_ledger.csv is generated from those records).
#
# Exit 0 the ordering holds, 1 it does not, 2 the arguments are wrong.
#
# If this ever fails, the public claim narrows to what the guard actually
# proves -- "the sealed-set definition and acceptance criteria were committed
# publicly before the sealed set was opened" -- rather than the broader
# sentence. That narrowing is D-67, and it is a decision, not a bug fix.
#
# It reads no data row, opens no database and issues no request except the one
# `git ls-remote` that proves the tag is public, so it is safe in any phase,
# including phase 01.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2

case "${1:-}" in
  "") ;;
  -h|--help)
    echo "usage: bash ops/check_seal_order.sh"
    echo "GD-12: every fit receipt under out/ descends from the pushed prereg tag."
    exit 0
    ;;
  *)
    echo "check_seal_order: unknown argument $1" >&2
    exit 2
    ;;
esac

# The tag string comes from config/seal.yml, the one place it is written.
# config/seal.yml is a flat mapping, so one sed is a sufficient reader.
TAG=$(sed -n 's/^prereg_tag:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' config/seal.yml \
      | tr -d ' "' | head -n 1)
if [ -z "$TAG" ]; then
  echo "SEAL-ORDER FAIL: no prereg_tag in config/seal.yml" >&2
  exit 1
fi

if [ ! -d .git ]; then
  echo "SEAL-ORDER FAIL: $root is not a git repository, so no ordering can be proven" >&2
  exit 1
fi

# --------------------------------------------------------------- the receipts
receipts=$(find out -type f -name provenance.json 2>/dev/null | sort)
n_receipts=$(printf "%s" "$receipts" | grep -c . || true)

tag_sha=$(git rev-list -n 1 "$TAG" 2>/dev/null || true)
tag_ref=$(git rev-parse "refs/tags/$TAG" 2>/dev/null || true)

if [ -z "$tag_sha" ]; then
  if [ "$n_receipts" -eq 0 ]; then
    echo "SEAL-ORDER OK (0 fit receipts, $TAG not tagged yet, nothing has been fit)"
    exit 0
  fi
  echo "SEAL-ORDER FAIL: $n_receipts fit receipt(s) under out/ and no $TAG tag." >&2
  echo "  The pre-registration was not written before the fits. D-67 applies:" >&2
  echo "  the abstract uses the narrow sentence." >&2
  exit 1
fi

# The tag must be public, not merely local. A pre-registration nobody can see
# is not a pre-registration.
pushed=0
remote_line=$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags origin "refs/tags/$TAG" 2>/dev/null || true)
remote_sha=$(printf "%s\n" "$remote_line" | awk -v r="refs/tags/$TAG" '$2 == r {print $1}' | head -n 1)
if [ -n "$remote_sha" ] && [ "$remote_sha" = "$tag_ref" ]; then
  pushed=1
fi

if [ "$pushed" -eq 0 ] && [ "$n_receipts" -gt 0 ]; then
  echo "SEAL-ORDER FAIL: $TAG is not pushed to origin with the same sha as the local tag," >&2
  echo "  and $n_receipts fit receipt(s) already exist. local=$tag_ref remote=${remote_sha:-none}" >&2
  echo "  A local-only tag proves nothing. Push it, or D-67's narrow sentence applies." >&2
  exit 1
fi

fails=0
checked=0
for receipt in $receipts; do
  checked=$((checked + 1))
  if command -v jq >/dev/null 2>&1; then
    sha=$(jq -r '.git_sha // empty' "$receipt" 2>/dev/null || true)
  else
    sha=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("git_sha",""))' \
          "$receipt" 2>/dev/null || true)
  fi
  if [ -z "$sha" ]; then
    echo "SEAL-ORDER FAIL: $receipt carries no git_sha (GD-01)" >&2
    fails=$((fails + 1))
    continue
  fi
  if ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then
    echo "SEAL-ORDER FAIL: $receipt names git_sha $sha, which is not a commit in this repository" >&2
    fails=$((fails + 1))
    continue
  fi
  if ! git merge-base --is-ancestor "$tag_sha" "$sha" 2>/dev/null; then
    echo "SEAL-ORDER FAIL: $receipt was fit at $sha, which does not descend from $TAG ($tag_sha)" >&2
    fails=$((fails + 1))
  fi
done

if [ "$fails" -ne 0 ]; then
  echo "SEAL-ORDER FAILED ($fails of $checked fit receipt(s) predate the pre-registration)" >&2
  echo "  D-67: the abstract uses the narrow sentence -- the sealed-set definition and" >&2
  echo "  acceptance criteria were committed publicly before the sealed set was opened." >&2
  exit 1
fi

if [ "$checked" -eq 0 ]; then
  echo "SEAL-ORDER OK (0 fit receipts, $TAG tagged at $tag_sha, pushed=$pushed)"
else
  echo "SEAL-ORDER OK ($checked/$checked fit receipt(s) descend from $TAG $tag_sha)"
fi
