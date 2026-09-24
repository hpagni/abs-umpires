#!/bin/sh
# ops/dbt.sh -- SOP step W1.11. The body of `make dbt`.
#
# Replaces the placeholder W1.14 parked here. The Makefile target already
# delegates to this script and is not edited.
#
# Order: deps, parse, then build. The build target depends on what is on disk.
# The lake is empty until W2 lands rows under interim/, so a dev build here
# would fail on a missing Parquet file rather than on anything wrong with the
# project. When the lake is empty this script builds the ci target over the
# 200-row synthetic seed instead and says so on one line.
#
# ABS_SEAL_START_DATE is exported from config/seal.yml, which is the one file
# that defines the boundary day. dbt/dbt_project.yml reads it into the
# seal_start_date variable. Nothing here writes the day down: GD-04 rule 5
# fails on a held-out day on the analysis surface, and the variable would be a
# second copy of a constant that already has one home.

set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

ABS_SEAL_START_DATE=$(sed -n 's/^seal_start_date: *"\(.*\)" *$/\1/p' config/seal.yml)
export ABS_SEAL_START_DATE
if [ -z "$ABS_SEAL_START_DATE" ]; then
  echo "dbt: config/seal.yml has no seal_start_date" >&2
  exit 1
fi

lake="${ABS_DATA_ROOT:-$root/data}"
threads="${DBT_THREADS:-8}"

uv run --locked dbt --no-use-colors deps --project-dir dbt
uv run --locked dbt --no-use-colors parse --project-dir dbt

# The dev build runs only when every dataset the models read is on disk. The
# test is per dataset, not "any Parquet anywhere": the lake already holds
# schedule_game, game_official and dim_batter_season while statcast_pitch and
# feed_challenge are still empty, and a dev build in that state fails on a
# missing file rather than on anything wrong with the project.
ready=1
for dataset in statcast_pitch feed_challenge; do
  if [ -z "$(find "$lake/interim/$dataset" -name '*.parquet' -print -quit 2>/dev/null)" ]; then
    echo "dbt: $lake/interim/$dataset holds no Parquet yet."
    ready=0
  fi
done

if [ "$ready" -eq 1 ]; then
  echo "dbt: lake at $lake/interim is ready, building the dev target."
  uv run --locked dbt --no-use-colors build --project-dir dbt --target dev --threads "$threads"
else
  echo "dbt: building the ci target over the synthetic seed instead. W2.14 fills the lake."
  uv run --locked dbt --no-use-colors build --project-dir dbt --target ci --select tag:smoke
fi
