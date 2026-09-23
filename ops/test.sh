#!/bin/sh
# ops/test.sh -- SOP step W1.14. The body of `make test`.
#
# The offline suites, in one pytest process: tests/unit, tests/fixtures,
# tests/guard. This is the set the `python` and `guard` CI jobs run (SOP W1.16).
# tests/data, tests/model and the chapter suites have their own targets because
# they need data or 30-70 minutes; they are not in the push gate (risk R-14).
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

exec uv run --locked pytest tests/unit tests/fixtures tests/guard -q
