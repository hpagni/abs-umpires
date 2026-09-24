#!/bin/sh
# ops/verify_contract.sh -- the recipe body behind `make verify-contract`.
#
# Owner: SOP step W9.4. The Makefile target already delegates here, so this step
# replaces this file and edits no Makefile. It runs the warehouse contract
# checker over SOP section 2.6, table by table, and exits with the checker's own
# exit code.
#
#   0  no check failed
#   1  at least one check failed
#   2  the contract file or the warehouse could not be read
#
# Arguments pass straight through, so `sh ops/verify_contract.sh --json` prints
# the machine-readable report and `--database PATH` points at another build.
#
# On a machine with no warehouse file the checker reports SKIP for the checks
# that read it, still runs the two that read only the repository, and exits 0.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

exec uv run --locked python quality/verify_contract.py "$@"
