#!/bin/sh
# ops/bootstrap.sh -- SOP step W1.14. The body of `make bootstrap`.
#
# Preflight, then both environments, in that order. Idempotent: every step is a
# no-op on a machine that is already set up.
#   1. ops/preflight.sh          disk floor, PATH, DYLD_LIBRARY_PATH, CmdStan
#   2. uv sync --locked --all-groups   the Python environment from uv.lock
#   3. pre-commit install              the W1.13 framework hook
#   4. ops/install_git_hooks.sh        the W2.1 no-raw-data guard, in front of it
#   5. renv::restore(prompt = FALSE)   the R library from renv.lock
#
# Steps 3 and 4 are in that order and must stay in it. `pre-commit install`
# overwrites .git/hooks/pre-commit, so the guard is installed after it;
# ops/install_git_hooks.sh preserves the framework hook as pre-commit.framework
# and execs it, so both still run. git does not track .git/hooks, so without
# these two steps a clean clone has no pre-commit hook at all and W2.1 is red
# until a human runs them by hand (D-PROVE-09).
#
# Needs the network on a cold cache. Not run by any gate.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

sh ops/preflight.sh
uv sync --locked --all-groups
uv run --locked pre-commit install
sh ops/install_git_hooks.sh
Rscript -e 'renv::restore(prompt = FALSE)'
echo "BOOTSTRAP OK"
