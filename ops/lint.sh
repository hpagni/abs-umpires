#!/bin/sh
# ops/lint.sh -- SOP step W1.14. The body of `make lint`.
#
# Three checks, all offline, all reported before the script exits:
#   ruff check .
#   ruff format --check .
#   ops/lint_http.sh   -- SOP rule 0.5.2, the one HTTP call site
#
# ops/lint_http.sh is W1.7's file. W2.3 wired it in here, hard: a missing linter
# is a failure, not a skip, because W2.3's whole content is the guarantee that
# the two call sites in src/absump/http.py and R/lib/http.R are the only ones.
# See docs/data-contract.md, "HTTP delegation (W2.3)", and docs/legal.md.
set -u

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 1
fails=0

echo "== ruff check"
uv run --locked ruff check . || fails=$((fails + 1))

echo "== ruff format --check"
uv run --locked ruff format --check . || fails=$((fails + 1))

echo "== http call sites"
if [ -f ops/lint_http.sh ]; then
  sh ops/lint_http.sh || fails=$((fails + 1))
else
  echo "ops/lint_http.sh is missing; SOP rule 0.5.2 cannot be checked" >&2
  fails=$((fails + 1))
fi

if [ "$fails" -ne 0 ]; then
  echo "LINT FAILED ($fails check(s))" >&2
  exit 1
fi
echo "LINT OK"
