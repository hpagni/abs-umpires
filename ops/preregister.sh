#!/bin/sh
# ops/preregister.sh -- SOP step W1.8. The body of `make preregister`.
#
# THE ONE-WAY DOOR. It belongs to MILESTONE M1, at the end of D3
# (Fri 2026-09-25, hard backstop D5, Sun 2026-09-27), in phase 04. It is not a
# phase 01 script. Running it freezes PREREGISTRATION.md and its four annexes,
# writes quality/prereg.lock, commits, tags prereg-v1, pushes the tag and
# publishes a GitHub release. None of that can be undone.
#
# It refuses today. PREREGISTRATION.md does not exist yet, and MILESTONE M1 has
# not been reached, so every path below ends in a refusal that names M1 and
# tags nothing.
#
# Two things make the door deliberate rather than accidental:
#   1. every M1 precondition below must hold, and
#   2. the owner must pass --confirm, by hand, after owner review R0.
# An agent never passes --confirm. SOP D-67 puts the tag BEFORE the first
# Chapter 1 fit of any kind, so M1 precedes every fit, and
# ops/check_seal_order.sh (GD-12) is what proves afterwards that it did.
#
# Usage:
#   bash ops/preregister.sh            the door: report the preconditions, refuse
#   bash ops/preregister.sh --check    report the preconditions, change nothing
#   bash ops/preregister.sh --confirm  MILESTONE M1, owner only, irreversible
#
# Exit: 0 --check ran, 1 the door refused, 2 the arguments are wrong.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2

mode="door"
case "${1:-}" in
  "") ;;
  --check) mode="check" ;;
  --confirm) mode="confirm" ;;
  -h|--help)
    sed -n '25,29p' "$0"
    exit 0
    ;;
  *)
    echo "preregister: unknown argument $1" >&2
    exit 2
    ;;
esac

TAG=$(sed -n 's/^prereg_tag:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' config/seal.yml \
      | tr -d ' "' | head -n 1)
PREREG="PREREGISTRATION.md"
MANIFEST="quality/sealed_manifest.json"
LOCK="quality/prereg.lock"
NOTES="docs/prereg/RELEASE_NOTES.md"
REPO="hpagni/abs-umpires"

missing=0
report() {
  if [ "$2" = "ok" ]; then
    echo "  OK      $1"
  else
    echo "  MISSING $1"
    missing=$((missing + 1))
  fi
}

echo "MILESTONE M1 preconditions (SOP phase 04, D3 end of day):"

[ -n "$TAG" ] && report "prereg_tag in config/seal.yml" ok || report "prereg_tag in config/seal.yml" no
[ -f "$PREREG" ] && report "$PREREG on disk" ok || report "$PREREG on disk" no

annexes=$(find docs/prereg -maxdepth 1 -name '*.md' ! -name 'SEAL.md' ! -name 'RELEASE_NOTES.md' \
          2>/dev/null | wc -l | tr -d ' ')
if [ "${annexes:-0}" -ge 4 ]; then
  report "four chapter annexes under docs/prereg/ (found $annexes)" ok
else
  report "four chapter annexes under docs/prereg/ (found ${annexes:-0})" no
fi

[ -f "$MANIFEST" ] && report "$MANIFEST frozen" ok || report "$MANIFEST frozen" no
[ -f "$NOTES" ] && report "$NOTES written" ok || report "$NOTES written" no

if [ -d .git ]; then
  report "git repository" ok
  if [ -z "$(git status --porcelain)" ]; then
    report "worktree clean" ok
  else
    report "worktree clean" no
  fi
  if git rev-parse --verify --quiet "refs/tags/$TAG" >/dev/null 2>&1; then
    echo "  DONE    tag $TAG already exists; the door is closed behind you"
    missing=$((missing + 1))
  else
    report "tag $TAG not yet created" ok
  fi
  if git remote get-url origin >/dev/null 2>&1; then
    report "remote origin configured" ok
  else
    report "remote origin configured" no
  fi
else
  report "git repository" no
fi

if [ "$mode" = "check" ]; then
  echo "preregister --check: $missing precondition(s) outstanding. Nothing was changed."
  exit 0
fi

if [ "$missing" -ne 0 ] || [ "$mode" = "door" ]; then
  echo ""
  echo "REFUSED. This is MILESTONE M1, the one-way door, and it has not been reached."
  if [ "$missing" -ne 0 ]; then
    echo "$missing precondition(s) above are outstanding."
  else
    echo "Every precondition holds. M1 is the owner's call: rerun with --confirm,"
    echo "after owner review R0, and only when no Chapter 1 fit has been run yet."
  fi
  echo "Nothing was committed, tagged or pushed."
  exit 1
fi

# ------------------------------------------------- MILESTONE M1, owner, once
echo ""
echo "MILESTONE M1. Freezing the pre-registration. This cannot be undone."
set -e
shasum -a 256 "$PREREG" docs/prereg/*.md > "$LOCK"
git add "$PREREG" docs/prereg "$LOCK" "$MANIFEST" \
        docs/writing-checklist.md tools/comms quality R/ch1 tests/ch1 renv.lock
git commit -m "Pre-registration v1.0: three-regime zone study, skill model, two-sided DP, acceptance criteria"
git tag -a "$TAG" -m "Pre-registration v1.0, frozen $(TZ=Europe/Madrid date -Iseconds). Sealed set: MLB games from 2026-09-22 plus the 2026 postseason."
git push origin main --tags
gh release create "$TAG" --repo "$REPO" \
  --title "Pre-registration v1.0" --notes-file "$NOTES" \
  "$PREREG" "$MANIFEST"
mkdir -p out/ch1/log
shasum -a 256 R/ch1/*.R tests/ch1/*.R src/absump/*.py > out/ch1/log/prereg_hashes.txt
git add out/ch1/log/prereg_hashes.txt
git commit -m "Frozen script hashes for prereg-v1"
git push
set +e
echo "MILESTONE M1 done. $TAG is tagged and pushed."
echo "Run ops/check_seal_order.sh after every fit from here on (GD-12)."
