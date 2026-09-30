#!/bin/sh
# tools/comms/check_seal_order.sh -- SOP W7.10, the seal-order tripwire (GD-12, D-67).
#
# GD-12: every fit receipt in out/, sealed or open, carries a git_sha that descends
# from the pushed prereg-v1 tag.
#
# Every other layer of the seal is keyed to sealed rows. Nothing in them stops the tag
# from being written after the open-set fits that produce the abstract's numbers. This
# script is the ordering check.
#
# What it does, in order:
#   1. Reads the tag name from config/seal.yml.
#   2. Reads the PUSHED tag from origin with one `git ls-remote` (the tag object and the
#      commit it peels to). The ancestry base is that pushed commit, never the local
#      tag. A local tag that differs from origin fails.
#   3. Walks every out/**/provenance.json (SOP 1.4: the canonical fit receipt), sealed
#      or open, and requires its git_sha to be a commit here that descends from the
#      pushed commit.
#
# D-63. When origin is a network host, the one ls-remote goes through the throttle in
# quality/check_prereg.py: 10 s gap and 500 per day to github.com (config/throttle.yml),
# one JSON line per request in data/ops/git_remote_ledger.jsonl. A local-path origin
# (the scratch repositories in tests/guard/test_seal_order_tripwire.py) sends no
# network request and is not throttled.
#
# ops/check_seal_order.sh (W1.8) is the W1 guard's copy of GD-12. It takes the ancestry
# base from the local tag after checking that origin has the same tag object. This file
# takes it from origin directly and logs the request. When the local tag exists, the
# two give the same verdict, because one tag object peels to one commit. Without a
# local tag (a clone that did not fetch tags) the W1.8 copy fails and this file checks
# the receipts against origin's tag.
#
# It reads no data row and opens no database. It is safe in any phase.
#
# Exit 0 the ordering holds. Exit 1 it does not, and the abstract keeps the narrow
# sentence (D-67): "the sealed-set definition and acceptance criteria were committed
# publicly before the sealed set was opened." Exit 2 usage.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 2
cd "$root" || exit 2

case "${1:-}" in
  "") ;;
  -h|--help)
    echo "usage: bash tools/comms/check_seal_order.sh"
    echo "GD-12: every fit receipt under out/ descends from the prereg tag as pushed to origin."
    exit 0
    ;;
  *)
    echo "check_seal_order: unknown argument $1" >&2
    exit 2
    ;;
esac

fail() { echo "SEAL-ORDER FAIL: $*" >&2; }
narrow() {
  echo "  D-67: the abstract uses the narrow sentence -- the sealed-set definition and" >&2
  echo "  acceptance criteria were committed publicly before the sealed set was opened." >&2
}

# ------------------------------------------------------------------ the tag name
TAG=$(sed -n 's/^prereg_tag:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' config/seal.yml 2>/dev/null \
      | tr -d ' "' | head -n 1)
if [ -z "$TAG" ]; then
  fail "no prereg_tag in config/seal.yml"
  exit 1
fi

# A git worktree has a .git file, not a directory, so ask git itself.
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "$root is not a git repository, so no ordering can be proven"
  exit 1
fi

# ------------------------------------------------------------------ the receipts
receipts=$(find out -type f -name provenance.json 2>/dev/null | LC_ALL=C sort)
n_receipts=$(printf "%s" "$receipts" | grep -c . || true)

# ------------------------------------------------------------------ the local tag
local_obj=$(git rev-parse -q --verify "refs/tags/$TAG" 2>/dev/null || true)
local_commit=""
[ -n "$local_obj" ] && local_commit=$(git rev-parse -q --verify "refs/tags/$TAG^{commit}" 2>/dev/null || true)

# ------------------------------------------------------------------ the pushed tag
# One request. Network origins go through the D-63 throttle and ledger.
origin_url=$(git remote get-url origin 2>/dev/null || true)
network=0
case "$origin_url" in
  "" | file://* | /* | ./* | ../*) network=0 ;;
  *://*) network=1 ;;
  *:*) [ -e "$origin_url" ] || network=1 ;;
esac

remote_out=""
remote_err=""
remote_rc=1
if [ -z "$origin_url" ]; then
  remote_err="no origin remote"
elif [ "$network" -eq 0 ]; then
  remote_out=$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags origin "refs/tags/$TAG" "refs/tags/$TAG^{}" \
               </dev/null 2>/dev/null)
  remote_rc=$?
elif ! command -v uv >/dev/null 2>&1 || [ ! -f quality/check_prereg.py ]; then
  remote_err="no uv or no quality/check_prereg.py, so the request cannot go through the D-63 throttle; not sent"
else
  remote_out=$(GIT_TERMINAL_PROMPT=0 uv run --locked --quiet python -c '
import os, subprocess as sp, sys
sys.path.insert(0, "quality")
import check_prereg as C
tag, url = sys.argv[1], sys.argv[2]
host = C.remote_host(url) or "default"
refs = ["refs/tags/" + tag, "refs/tags/" + tag + "^{}"]
what = "GD-12 tools/comms/check_seal_order.sh: git ls-remote --tags origin " + " ".join(refs)
env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
try:
    with C.project_throttle().slot(host, what) as oc:
        r = sp.run(["git", "ls-remote", "--tags", "origin", *refs], capture_output=True, text=True,
                   stdin=sp.DEVNULL, env=env, timeout=C.LS_REMOTE_TIMEOUT_S)
        oc["exit"] = r.returncode
except C.BudgetSpent as e:
    sys.exit("D-63 budget spent: %s" % e)
except sp.TimeoutExpired:
    sys.exit("git ls-remote timed out after %.0f s" % C.LS_REMOTE_TIMEOUT_S)
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
sys.exit(r.returncode)
' "$TAG" "$origin_url" </dev/null 2>"${TMPDIR:-/tmp}/check_seal_order.$$.err")
  remote_rc=$?
  remote_err=$(tail -n 3 "${TMPDIR:-/tmp}/check_seal_order.$$.err" 2>/dev/null | tr '\n' ' ')
  rm -f "${TMPDIR:-/tmp}/check_seal_order.$$.err"
fi

pushed_obj=""
pushed_commit=""
if [ "$remote_rc" -eq 0 ]; then
  pushed_obj=$(printf "%s\n" "$remote_out" | awk -v r="refs/tags/$TAG" '$2 == r {print $1}' | head -n 1)
  pushed_commit=$(printf "%s\n" "$remote_out" | awk -v r="refs/tags/$TAG^{}" '$2 == r {print $1}' | head -n 1)
  # A lightweight tag has no peeled line: the tag names the commit itself.
  [ -n "$pushed_obj" ] && [ -z "$pushed_commit" ] && pushed_commit=$pushed_obj
fi

# ------------------------------------------------------------------ not on origin
if [ -z "$pushed_obj" ]; then
  why="not on origin"
  [ "$remote_rc" -ne 0 ] && why="origin not read (exit $remote_rc${remote_err:+: $remote_err})"
  if [ "$n_receipts" -eq 0 ]; then
    if [ -z "$local_obj" ]; then
      echo "SEAL-ORDER OK (0 fit receipts, $TAG not tagged yet, nothing has been fit)"
    else
      echo "SEAL-ORDER OK (0 fit receipts, $TAG tagged at $local_commit, pushed=0: $why)"
    fi
    exit 0
  fi
  if [ -z "$local_obj" ]; then
    fail "$n_receipts fit receipt(s) under out/ and no $TAG tag ($why)."
    echo "  The pre-registration was not written before the fits." >&2
  else
    fail "$TAG is not pushed to origin ($why), and $n_receipts fit receipt(s) already exist."
    echo "  local=$local_obj remote=none. A local-only tag proves nothing." >&2
  fi
  narrow
  exit 1
fi

# ------------------------------------------------------------------ on origin
if [ -n "$local_obj" ] && [ "$local_obj" != "$pushed_obj" ]; then
  fail "the local $TAG is not pushed: local=$local_obj, origin=$pushed_obj."
  echo "  The tag was moved after it was pushed. The public tag is the pre-registration." >&2
  narrow
  exit 1
fi
if ! git cat-file -e "${pushed_commit}^{commit}" 2>/dev/null; then
  fail "origin's $TAG peels to $pushed_commit, which is not a commit in this repository."
  echo "  Run: git fetch origin --tags" >&2
  exit 1
fi

fails=0
checked=0
while IFS= read -r receipt; do
  [ -n "$receipt" ] || continue
  checked=$((checked + 1))
  if command -v jq >/dev/null 2>&1; then
    sha=$(jq -r '.git_sha // empty' "$receipt" 2>/dev/null || true)
  else
    sha=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("git_sha",""))' \
          "$receipt" 2>/dev/null || true)
  fi
  if [ -z "$sha" ]; then
    fail "$receipt carries no git_sha (GD-01)"
    fails=$((fails + 1))
    continue
  fi
  if ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then
    fail "$receipt names git_sha $sha, which is not a commit in this repository"
    fails=$((fails + 1))
    continue
  fi
  if ! git merge-base --is-ancestor "$pushed_commit" "$sha" 2>/dev/null; then
    fail "$receipt was fit at $sha, which does not descend from the pushed $TAG ($pushed_commit)"
    fails=$((fails + 1))
  fi
done <<EOF
$receipts
EOF

if [ "$fails" -ne 0 ]; then
  echo "SEAL-ORDER FAILED ($fails of $checked fit receipt(s) predate the pre-registration)" >&2
  narrow
  exit 1
fi

if [ "$checked" -eq 0 ]; then
  echo "SEAL-ORDER OK (0 fit receipts, $TAG tagged at $pushed_commit, pushed=1, read from origin)"
else
  echo "SEAL-ORDER OK ($checked/$checked fit receipt(s) descend from $TAG $pushed_commit, read from origin)"
fi
exit 0
