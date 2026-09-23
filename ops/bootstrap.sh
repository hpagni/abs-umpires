#!/bin/sh
# ops/bootstrap.sh -- SOP step W1.14. The body of `make bootstrap`.
#
# Preflight, then both environments, in that order. Idempotent: every step is a
# no-op on a machine that is already set up.
#   1. ops/preflight.sh          disk floor, PATH, DYLD_LIBRARY_PATH, CmdStan
#   2. uv sync --locked --all-groups   the Python environment from uv.lock
#   3. renv::restore(prompt = FALSE)   the R library from renv.lock
#
# Needs the network on a cold cache. Not run by any gate.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

sh ops/preflight.sh
uv sync --locked --all-groups
Rscript -e 'renv::restore(prompt = FALSE)'
echo "BOOTSTRAP OK"
