#!/bin/sh
# ops/guard_scan.sh -- GD-04 at the commit boundary. SOP step W9.7, layer 3.
#
# One line of delegation: the scan itself is tests/guard/gd04_scan.py, which is
# the same engine `make test-guard` runs, so the hook and the test suite cannot
# drift apart. Called by the `sealed-read-guard` pre-commit hook and runnable by
# hand:
#
#   bash ops/guard_scan.sh              the whole repository
#   bash ops/guard_scan.sh --path P     one path
#
# It exits 1 with a file:line for every read of the held-out set it finds, 0
# when the tree is clean. It reads no data row and opens no database.
set -u
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 2
if command -v uv >/dev/null 2>&1; then
  exec uv run --locked python tests/guard/gd04_scan.py "$@"
fi
exec python3 tests/guard/gd04_scan.py "$@"
