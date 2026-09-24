#!/bin/sh
# ops/normalize_statcast.sh -- SOP step W2.14. The body of `make normalize-statcast`.
#
# Converts every raw Statcast day in the lake into one typed Parquet part under
# data/interim/statcast_pitch/, with both plate planes, the harmonised zone and
# the edge distance. Offline: it reads data/raw and data/staging and makes no
# request. Safe to re-run; a day whose bytes do not change is not rewritten.
#
# Arguments pass through, so a single season is
#   bash ops/normalize_statcast.sh --level mlb --season 2026
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root" || exit 1

if [ "$#" -gt 0 ]; then
  uv run --locked python -m absump.ingest.normalize_sc "$@"
else
  uv run --locked python -m absump.ingest.normalize_sc --level mlb --season 2015..2026 --threads 8
fi
