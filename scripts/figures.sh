#!/usr/bin/env bash
# scripts/figures.sh -- `make figures`. SOP section 9.1: a figure is produced only by `make figures`.
#
# Owner: SOP step W3.24, fleet phase 08. Runs R/ch1/70_figures.R: the compute stage, which rebuilds
# the primary sample and reads the fitted surface for F1's ray bands and F7's calibration bins and is
# a cache hit when its inputs, code and outputs are unchanged, then the render stage, which writes
# out/figures/F1..F8 (.png and .pdf), out/tables/<figure-id>_data.csv and the figure manifest.
#
# Exit status is the script's: 0 when all eight figures are real, 3 when every buildable figure was
# written but a placeholder remains (F5 waits on W3.20, F8 on W3.23), 1 on a failed check, 4 when
# GD-12 refuses the run. One R process at a time; the compute stage peaks near 4.1 GB.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export STAN_NUM_THREADS=1 OMP_NUM_THREADS=1
exec Rscript R/ch1/70_figures.R --stage all "$@"
