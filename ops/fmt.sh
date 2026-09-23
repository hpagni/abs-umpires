#!/bin/sh
# ops/fmt.sh -- SOP step W1.14. The body of `make fmt`.
#
# Formats in place. The same two ruff 0.16.8 passes the pre-commit hooks run
# (SOP W1.13): ruff-format then ruff-check --fix.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

uv run --locked ruff format .
uv run --locked ruff check --fix .
echo "FMT OK"
