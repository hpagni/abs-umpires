#!/usr/bin/env bash
# scripts/tables.sh -- `make tables`. SOP section 9.1: a table is produced only by `make tables`.
#
# Owner: SOP step W3.24, fleet phase 08. Runs R/ch1/70_figures.R --stage compute first (a cache hit
# after `make figures`; T1 and T7 read what it writes), then R/ch1/71_tables.R, which writes
# out/tables/T1..T9, the table manifest and docs/ch1.md. It reads the figure manifest, so `make
# figures` runs before it.
#
# Exit status is 71_tables.R's: 0 when all nine tables are real, 3 when a placeholder remains (T8
# waits on W3.22's receipt), 1 on a failed check, 4 when GD-12 refuses the run.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export STAN_NUM_THREADS=1 OMP_NUM_THREADS=1
Rscript R/ch1/70_figures.R --stage compute
exec Rscript R/ch1/71_tables.R "$@"
