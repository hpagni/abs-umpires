#!/usr/bin/env bash
# ops/lint_prose.sh -- the prose gate's shell entry. Owner: SOP step W9.13.
#
# SOP section 2.8 settles the two linters on ONE implementation, quality/prose_lint.py:
# "Two linters with two ban lists is how a rule quietly stops being enforced." Phase 01
# wrote a stand-in here with its own copy of the ban list and three rules (WR-01, WR-03,
# WR-05). W9.13 retires that copy. This file now runs quality/prose_lint.py, which
# carries W7's rules 1 to 11, the WR pack as quality/wr-scope.md scopes it, and the P8
# ban list. Every caller keeps working: the W4.1, W7.2 and W9.13 verify commands and
# the CI job (ops/ci-pending/ci.yml) all pass ABS_PROSE_FILES, one path per line, and
# the linter honours it.
#
#   bash ops/lint_prose.sh              the default scope, or ABS_PROSE_FILES if set
#   bash ops/lint_prose.sh PATH ...     the named paths
#   bash ops/lint_prose.sh --selftest   the linter's fixture test
#
# PYTHON overrides the interpreter (CI sets it); otherwise uv runs the locked env.
# Exit 0 clean, 1 on any violation, 2 on a usage error.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
if [ -n "${PYTHON:-}" ]; then
  exec "$PYTHON" quality/prose_lint.py "$@"
fi
exec uv run --locked python quality/prose_lint.py "$@"
