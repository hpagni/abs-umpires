"""absump.ingest.normalize_sc -- W2.14, Statcast normalisation with both planes.

    uv run python -m absump.ingest.normalize_sc --level mlb --season 2015..2026 --threads 8

One raw Statcast day CSV in, one typed Parquet part out:

    data/raw/statcast/level=<level>/season=<yyyy>/date=<date>/pitches.csv.zst
    data/interim/statcast_pitch/level=<level>/season=<yyyy>/date=<date>/part-000.parquet

The conversion is the COPY in SOP W2.14, `read_csv_auto(header=true,
sample_size=-1)` into `FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 9`,
with the geometry and height columns W2.14 requires added to the select list.

WHAT THIS MODULE EMITS BEYOND THE RAW COLUMNS

    plane_source        the plane the raw `plate_x`/`plate_z` were measured at
    plate_x_front, plate_z_front    the pair at y = 17/12 ft
    plate_x_mid,   plate_z_mid      the pair at y = 8.5/12 ft
    batter_height_in, height_source from W2.7's dim_batter_season
    sz_top_h = 0.535*H/12, sz_bot_h = 0.27*H/12   the harmonised zone, in feet
    tracked             false on a blank-coordinate row
    in_zone_center      centre of the ball inside the published zone, mid plane
    edge_dist_in        the W4-verified any-part-of-ball distance, r configurable
    edge_dist_r_in      the ball radius that produced `edge_dist_in`

Both planes are emitted for every row, so no downstream model has to touch raw
`plate_x`, which is the R-02 mitigation. The pair that matches `plane_source` is
the measured one; the other is re-projected.

THE GEOMETRY

SOP section 2.5, with `Y0 = 50.0` ft and `y` in feet:

    t(y)     = ( -vy0 - sqrt(vy0^2 - 2*ay*(Y0 - y)) ) / ay
    dx       = vx0*(t_b - t_a) + 0.5*ax*(t_b^2 - t_a^2)
    dz       = vz0*(t_b - t_a) + 0.5*az*(t_b^2 - t_a^2)

`vy0 < 0` and `ay > 0`, so the subtraction is the smaller positive root and no
branch is needed (section 2.5 item A1, R-43). A row whose kinematics do not
satisfy both inequalities gets NULL geometry and is counted in the summary
rather than re-projected off the wrong root.

BUILD DECISIONS, recorded here because W2.14 chose them under the autonomous
posture and a later reader needs them stated:

B-1 One implementation, in SQL. SOP W2.14 says to use `src/absump/geometry.py`
    and section 2.5 says nothing re-derives that function. `geometry.py` is
    W3.3, which the fleet plan schedules for the next phase, while the W2.14
    dependency line is W2.9, W2.10, W2.7. So the re-projection lives here once,
    as the SQL this module generates, and `tests/data/test_normalize.py` checks
    it against a brute-force smallest-positive-root solve. The same test picks
    up `absump.geometry` the moment W3.3 lands and asserts agreement to 1e-12,
    which is the seam that keeps the two from drifting.
B-2 Typed schema contract. `read_csv_auto` infers a column that is empty on a
    given day as VARCHAR, so day files disagree on type across seasons: 40 of
    the 119 columns come back VARCHAR on one day and BIGINT or DOUBLE on
    another. Every column is therefore CAST to the frozen type in
    `COLUMN_TYPES`, which was read off DuckDB's own inference over 35 days
    spread across 2022 to 2026. One Parquet schema for the whole corpus.
B-3 Partition columns from the path. `date`, `level` and `season` are written
    as literals minted by `absump.paths`, not read from the CSV, so a staging
    CSV that predates those three columns converts the same way a lake day
    does. `game_date` is kept as the CSV reported it and rows where the two
    disagree are counted in the summary.
B-4 The published zone drives `edge_dist_in` and `in_zone_center`. That is the
    pair the W4 drawer check reproduced to 0.000000 in on 1,276 rows, so it is
    the one that can be verified against an outside source. The harmonised
    `sz_top_h`/`sz_bot_h` are emitted beside it and any downstream convention
    can be rebuilt from the columns in the table. W2 bakes in no edge rule.
B-5 `r` is stored per row. `edge_dist_in` means nothing without the radius that
    produced it, and a partial re-run under a different `--ball-radius-in`
    would otherwise leave a corpus that mixes two conventions silently.
B-6 Raw `plate_x`/`plate_z` stay in the interim table. The SOP COPY selects the
    raw columns and the rule is that no model touches them, not that the
    interim layer drops them. The dbt staging model publishes the two planes.
B-7 Idempotent by content. Every part is written to a temporary file and
    replaced only when the bytes differ, so a second run over a converted day
    leaves the tree byte for byte as the first run left it.
"""

from __future__ import annotations

import argparse
import concurrent.futures as _futures
import datetime as _dt
import hashlib
import json
import os
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final

import duckdb

from absump import heights, paths
from absump.ingest import statcast_day as sc

__all__ = [
    "ABS_BOT_FRAC",
    "ABS_TOP_FRAC",
    "BALL_R_IN",
    "COLUMN_TYPES",
    "DATASET",
    "PLANE_FRONT",
    "PLANE_MID",
    "PLATE_HALF_W_FT",
    "T_MAJOR_MAX_S",
    "T_UNPHYSICAL_S",
    "Y_FRONT_FT",
    "Y_MID_FT",
    "Y_REF_FT",
    "ZERO_CLAUSES",
    "PlaneUndetermined",
    "build",
    "day_files",
    "day_sql",
    "derived_columns",
    "normalize_day",
    "out_path",
    "plane_source",
    "read_day",
    "read_summary",
    "summary_path",
    "t_at_y_sql",
]

#: The dataset name under `data/interim/`, and the W2.14 output path stem.
DATASET: Final[str] = "statcast_pitch"

#: Section 2.5 geometry, the same constants as `R/lib/zone.R` in W3.3.
PLATE_HALF_W_FT: Final[float] = 8.5 / 12  # 17-inch plate
Y_FRONT_FT: Final[float] = 17 / 12
Y_MID_FT: Final[float] = 8.5 / 12
Y_REF_FT: Final[float] = 50.0
ABS_TOP_FRAC: Final[float] = 0.535
ABS_BOT_FRAC: Final[float] = 0.27

#: The W4-verified ball radius. `--ball-radius-in` overrides it; the value that
#: produced a row lands in that row's `edge_dist_r_in`.
BALL_R_IN: Final[float] = 1.45

#: `plane_source` values. The plane the raw CSV coordinates were measured at.
PLANE_FRONT: Final[str] = "front"
PLANE_MID: Final[str] = "mid"

#: Parquet settings from the SOP W2.14 COPY.
PARQUET_COMPRESSION: Final[str] = "ZSTD"
PARQUET_COMPRESSION_LEVEL: Final[int] = 9

#: The part number every day writes. One file per day.
PART: Final[int] = 0


class PlaneUndetermined(RuntimeError):
    """The reference plane for a level-season has not been established.

    Section 2.5 states the MLB changeover (front through 2025, middle from
    2026) and that the AAA CSV is already middle-of-plate in 2024. It states
    nothing about AAA before 2024, and guessing there would move every
    coordinate of that season by about an inch in the direction of the effect
    under study. The AAA changeover date is W2.8's D-57 binary search and
    DT-29; until that lands, an undetermined level-season fails loudly.
    """


# --------------------------------------------------------------------------
# The typed schema contract (B-2)
# --------------------------------------------------------------------------

#: One DuckDB type per CSV column, in the order `statcast_day.contract_columns()`
#: declares. Read off DuckDB 1.5.5's own `read_csv_auto(sample_size=-1)`
#: inference over 35 MLB day files spread across 2022 to 2026, resolving the 40
#: columns that come back VARCHAR on a day where they are empty to the type the
#: other days infer. `tests/data/test_normalize.py` asserts the key set equals
#: the 119 contract columns, so a header change fails here as well as in DT-02.
COLUMN_TYPES: Final[dict[str, str]] = {
    "pitch_type": "VARCHAR",
    "game_date": "DATE",
    "release_speed": "DOUBLE",
    "release_pos_x": "DOUBLE",
    "release_pos_z": "DOUBLE",
    "player_name": "VARCHAR",
    "batter": "BIGINT",
    "pitcher": "BIGINT",
    "events": "VARCHAR",
    "description": "VARCHAR",
    "spin_dir": "VARCHAR",
    "spin_rate_deprecated": "VARCHAR",
    "break_angle_deprecated": "VARCHAR",
    "break_length_deprecated": "VARCHAR",
    "zone": "BIGINT",
    "des": "VARCHAR",
    "game_type": "VARCHAR",
    "stand": "VARCHAR",
    "p_throws": "VARCHAR",
    "home_team": "VARCHAR",
    "away_team": "VARCHAR",
    "type": "VARCHAR",
    "hit_location": "BIGINT",
    "bb_type": "VARCHAR",
    "balls": "BIGINT",
    "strikes": "BIGINT",
    "game_year": "BIGINT",
    "pfx_x": "DOUBLE",
    "pfx_z": "DOUBLE",
    "plate_x": "DOUBLE",
    "plate_z": "DOUBLE",
    "on_3b": "BIGINT",
    "on_2b": "BIGINT",
    "on_1b": "BIGINT",
    "outs_when_up": "BIGINT",
    "inning": "BIGINT",
    "inning_topbot": "VARCHAR",
    "hc_x": "DOUBLE",
    "hc_y": "DOUBLE",
    "tfs_deprecated": "VARCHAR",
    "tfs_zulu_deprecated": "VARCHAR",
    "umpire": "VARCHAR",
    "sv_id": "VARCHAR",
    "vx0": "DOUBLE",
    "vy0": "DOUBLE",
    "vz0": "DOUBLE",
    "ax": "DOUBLE",
    "ay": "DOUBLE",
    "az": "DOUBLE",
    "sz_top": "DOUBLE",
    "sz_bot": "DOUBLE",
    "hit_distance_sc": "BIGINT",
    "launch_speed": "DOUBLE",
    "launch_angle": "BIGINT",
    "effective_speed": "DOUBLE",
    "release_spin_rate": "BIGINT",
    "release_extension": "DOUBLE",
    "game_pk": "BIGINT",
    "fielder_2": "BIGINT",
    "fielder_3": "BIGINT",
    "fielder_4": "BIGINT",
    "fielder_5": "BIGINT",
    "fielder_6": "BIGINT",
    "fielder_7": "BIGINT",
    "fielder_8": "BIGINT",
    "fielder_9": "BIGINT",
    "release_pos_y": "DOUBLE",
    "estimated_ba_using_speedangle": "DOUBLE",
    "estimated_woba_using_speedangle": "DOUBLE",
    "woba_value": "DOUBLE",
    "woba_denom": "BIGINT",
    "babip_value": "BIGINT",
    "iso_value": "BIGINT",
    "launch_speed_angle": "BIGINT",
    "at_bat_number": "BIGINT",
    "pitch_number": "BIGINT",
    "pitch_name": "VARCHAR",
    "home_score": "BIGINT",
    "away_score": "BIGINT",
    "bat_score": "BIGINT",
    "fld_score": "BIGINT",
    "post_away_score": "BIGINT",
    "post_home_score": "BIGINT",
    "post_bat_score": "BIGINT",
    "post_fld_score": "BIGINT",
    "if_fielding_alignment": "VARCHAR",
    "of_fielding_alignment": "VARCHAR",
    "spin_axis": "BIGINT",
    "delta_home_win_exp": "DOUBLE",
    "delta_run_exp": "DOUBLE",
    "bat_speed": "DOUBLE",
    "swing_length": "DOUBLE",
    "miss_distance": "DOUBLE",
    "estimated_slg_using_speedangle": "DOUBLE",
    "delta_pitcher_run_exp": "DOUBLE",
    "hyper_speed": "DOUBLE",
    "home_score_diff": "BIGINT",
    "bat_score_diff": "BIGINT",
    "home_win_exp": "DOUBLE",
    "bat_win_exp": "DOUBLE",
    "age_pit_legacy": "BIGINT",
    "age_bat_legacy": "BIGINT",
    "age_pit": "BIGINT",
    "age_bat": "BIGINT",
    "n_thruorder_pitcher": "BIGINT",
    "n_priorpa_thisgame_player_at_bat": "BIGINT",
    "pitcher_days_since_prev_game": "BIGINT",
    "batter_days_since_prev_game": "BIGINT",
    "pitcher_days_until_next_game": "BIGINT",
    "batter_days_until_next_game": "BIGINT",
    "api_break_z_with_gravity": "DOUBLE",
    "api_break_x_arm": "DOUBLE",
    "api_break_x_batter_in": "DOUBLE",
    "arm_angle": "DOUBLE",
    "attack_angle": "DOUBLE",
    "attack_direction": "DOUBLE",
    "swing_path_tilt": "DOUBLE",
    "intercept_ball_minus_batter_pos_x_inches": "DOUBLE",
    "intercept_ball_minus_batter_pos_y_inches": "DOUBLE",
}

#: Written from the minted path, never read from the CSV (B-3).
PARTITION_TYPES: Final[dict[str, str]] = {"date": "DATE", "level": "VARCHAR", "season": "BIGINT"}


def derived_columns() -> tuple[str, ...]:
    """The columns W2.14 adds, in the order they appear in the Parquet file."""
    return (
        "plane_source",
        "plate_x_front",
        "plate_z_front",
        "plate_x_mid",
        "plate_z_mid",
        "batter_height_in",
        "height_source",
        "sz_top_h",
        "sz_bot_h",
        "tracked",
        "in_zone_center",
        "edge_dist_in",
        "edge_dist_r_in",
    )


def output_columns() -> tuple[str, ...]:
    """Every column of the interim table, in order."""
    return tuple(COLUMN_TYPES) + tuple(PARTITION_TYPES) + derived_columns()


# --------------------------------------------------------------------------
# The reference plane (section 2.5)
# --------------------------------------------------------------------------


def plane_source(level: str, season: int) -> str:
    """The plane the raw `plate_x`/`plate_z` of one level-season were measured at.

    MLB: front of the plate through 2025, middle of the plate from 2026, which
    is the csv-docs sentence quoted in section 2.5. AAA: middle of the plate
    from 2024, measured on 2024-07-12. Anything else raises `PlaneUndetermined`.
    """
    level = str(level).lower()
    season = int(season)
    if level == "mlb":
        return PLANE_FRONT if season <= 2025 else PLANE_MID
    if level == "aaa" and season >= 2024:
        return PLANE_MID
    raise PlaneUndetermined(
        f"the reference plane for level={level} season={season} is not established "
        "in SOP section 2.5; W2.8's AAA changeover search (D-57, DT-29) settles it"
    )


# --------------------------------------------------------------------------
# The SQL (B-1)
# --------------------------------------------------------------------------


def t_at_y_sql(y_ft: float, vy0: str = "vy0", ay: str = "ay") -> str:
    """Time from the y = 50.0 ft reference plane to `y_ft`, smaller positive root.

    The closed form of section 2.5 item A1, with no root selection and no
    branch. Guarded by `vy0 < 0 AND ay > 0`: the guard is what makes the
    subtraction the smaller root, so a row that fails it yields NULL.
    """
    # Every operand is parenthesised. A caller may pass a literal, and DuckDB
    # reads `--136.346` as a line comment, which silently truncates the rest of
    # the statement instead of failing.
    return (
        f"CASE WHEN ({vy0}) < 0 AND ({ay}) > 0 THEN "
        f"(-({vy0}) - sqrt(({vy0}) * ({vy0}) - 2 * ({ay}) * ({Y_REF_FT!r} - {y_ft!r}))) "
        f"/ ({ay}) END"
    )


def _shift_sql(coord: str, v0: str, acc: str, t_to: str, t_from: str) -> str:
    """One coordinate carried from plane `t_from` to plane `t_to`.

    `dx = vx0*(t_b - t_a) + 0.5*ax*(t_b^2 - t_a^2)`. When the two planes are the
    same column both differences are exactly zero, so the measured pair comes
    out of the re-projection bit for bit.
    """
    return (
        f"({coord}) + ({v0}) * (({t_to}) - ({t_from})) "
        f"+ 0.5 * ({acc}) * (({t_to}) * ({t_to}) - ({t_from}) * ({t_from}))"
    )


def day_sql(
    *,
    source: str,
    level: str,
    season: int,
    day: _dt.date,
    ball_radius_in: float = BALL_R_IN,
    heights_relation: str | None = None,
) -> str:
    """The full SELECT for one day file.

    `source` is the CSV path, `heights_relation` the name of a registered
    relation with `batter, height_in, height_source` or None when W2.7 has no
    dimension for that level-season.
    """
    plane = plane_source(level, season)
    casts = ",\n        ".join(
        f'CAST("{name}" AS {kind}) AS "{name}"' for name, kind in COLUMN_TYPES.items()
    )
    t_src = "t_front" if plane == PLANE_FRONT else "t_mid"
    if heights_relation is None:
        joined = (
            "SELECT geo.*, CAST(NULL AS DOUBLE) AS batter_height_in, "
            "CAST(NULL AS VARCHAR) AS height_source FROM geo"
        )
    else:
        joined = (
            "SELECT geo.*, dim.height_in AS batter_height_in, dim.height_source AS height_source "
            f"FROM geo LEFT JOIN {heights_relation} AS dim ON dim.batter = geo.batter"
        )
    tracked = " AND ".join(f'"{column}" IS NOT NULL' for column in sc.TRACKING_COLUMNS)
    select = ",\n        ".join(f'"{name}"' for name in COLUMN_TYPES)
    return f"""
WITH raw AS (
    SELECT
        {casts}
    FROM read_csv_auto('{source}', header = true, sample_size = -1)
),
kin AS (
    SELECT
        raw.*,
        {t_at_y_sql(Y_FRONT_FT)} AS t_front,
        {t_at_y_sql(Y_MID_FT)} AS t_mid
    FROM raw
),
geo AS (
    SELECT
        kin.*,
        {_shift_sql("plate_x", "vx0", "ax", "t_front", t_src)} AS plate_x_front,
        {_shift_sql("plate_z", "vz0", "az", "t_front", t_src)} AS plate_z_front,
        {_shift_sql("plate_x", "vx0", "ax", "t_mid", t_src)} AS plate_x_mid,
        {_shift_sql("plate_z", "vz0", "az", "t_mid", t_src)} AS plate_z_mid
    FROM kin
),
withh AS (
    {joined}
),
edge AS (
    SELECT
        withh.*,
        abs(plate_x_mid) * 12 - {PLATE_HALF_W_FT * 12!r} AS dx_in,
        greatest(sz_bot * 12 - plate_z_mid * 12, plate_z_mid * 12 - sz_top * 12) AS dz_in
    FROM withh
),
signed AS (
    SELECT
        edge.*,
        CASE WHEN dx_in > 0 AND dz_in > 0 THEN sqrt(dx_in * dx_in + dz_in * dz_in)
             ELSE greatest(dx_in, dz_in) END AS signed_edge_in
    FROM edge
)
SELECT
    {select},
    DATE '{day.isoformat()}' AS "date",
    '{level}' AS "level",
    CAST({int(season)} AS BIGINT) AS "season",
    '{plane}' AS plane_source,
    plate_x_front,
    plate_z_front,
    plate_x_mid,
    plate_z_mid,
    batter_height_in,
    height_source,
    {ABS_TOP_FRAC!r} * batter_height_in / 12 AS sz_top_h,
    {ABS_BOT_FRAC!r} * batter_height_in / 12 AS sz_bot_h,
    ({tracked}) AS tracked,
    signed_edge_in <= 0 AS in_zone_center,
    signed_edge_in - {float(ball_radius_in)!r} AS edge_dist_in,
    CAST({float(ball_radius_in)!r} AS DOUBLE) AS edge_dist_r_in
FROM signed
"""


# --------------------------------------------------------------------------
# Paths and day lists
# --------------------------------------------------------------------------


def out_path(level: str, season: int, day: Any) -> Path:
    """The minted Parquet part for one day, open lake or sealed side.

    `paths.lake_path` is the only function that knows the sealed branch. Every
    date on or before `paths.LAST_OPEN_DATE` lands in `data/interim/`; a later
    one lands under `data/sealed/plain/`, which is what W2.22's in-season run
    needs and what GD-10 later removes.
    """
    return paths.lake_path(DATASET, level, season, day, PART)


def summary_path() -> Path:
    """The build summary, one file for the whole dataset."""
    return paths.data_root() / "interim" / DATASET / "summary.json"


def day_files(level: str, season: int) -> list[tuple[_dt.date, Path]]:
    """Every source day for one level-season, lake first, staging as fallback.

    The lake is `data/raw/statcast/level=<level>/season=<yyyy>/date=<date>/`,
    the staging cache is `data/staging/statcast/<level>/<season>/<date>.csv`.
    A date present in both is taken from the lake, so no day is converted twice.
    """
    chosen: dict[str, Path] = {}
    lake = paths.data_root() / "raw" / "statcast" / f"level={level}" / f"season={season}"
    for path in sorted(lake.glob("date=*/pitches.csv.zst")):
        chosen[path.parent.name.split("=", 1)[1]] = path
    staging = paths.data_root() / "staging" / "statcast" / str(level) / str(season)
    for path in sorted(staging.glob("*.csv")):
        chosen.setdefault(path.stem, path)
    return [(_dt.date.fromisoformat(date), chosen[date]) for date in sorted(chosen)]


def _write_if_changed(target: Path, tmp: Path) -> bool:
    """Replace `target` with `tmp` only when the bytes differ. True when written."""
    payload = tmp.read_bytes()
    if target.exists():
        existing = target.read_bytes()
        if hashlib.sha256(existing).digest() == hashlib.sha256(payload).digest():
            tmp.unlink()
            return False
    os.replace(tmp, target)
    return True


# --------------------------------------------------------------------------
# Day statistics, read back off the part that was written
# --------------------------------------------------------------------------

#: The unphysical second crossing. The quadratic has two positive roots and the
#: larger one is 9.1839 s for the data contract's own pitch (section 2.5 item
#: A1). The slowest tracked pitch in the MLB 2022 to 2026 lake crosses in
#: 1.9615 s, a 21.7 mph position-player lob, so a plate time at or above 2.0 s
#: is the wrong root rather than a slow pitch.
T_UNPHYSICAL_S: Final[float] = 2.0

#: The plate time the SOP states for a major-league pitch, section 2.5 item A1.
#: Pitches thrown by position players run past it and are excluded from the
#: analysis sample by SOP W3.7, so this is counted, not enforced.
T_MAJOR_MAX_S: Final[float] = 0.60

#: Counted per day and summed per season. Every clause `check` reads.
_CALLED_TUPLE: Final[str] = str(tuple(sorted(sc.CALLED_DESCRIPTIONS)))
_BLANK_ALL: Final[str] = " AND ".join(f'"{column}" IS NULL' for column in sc.TRACKING_COLUMNS)
_BLANK_ANY: Final[str] = " OR ".join(f'"{column}" IS NULL' for column in sc.TRACKING_COLUMNS)
_T_MID_SQL: Final[str] = f"(-vy0 - sqrt(vy0 * vy0 - 2 * ay * ({Y_REF_FT!r} - {Y_MID_FT!r}))) / ay"

_STATS_SQL: Final[str] = f"""
SELECT
    count(*) AS n_rows,
    count(*) FILTER (tracked) AS n_tracked,
    count(*) FILTER (description IN {_CALLED_TUPLE}) AS n_called,
    count(*) FILTER (tracked AND description IN {_CALLED_TUPLE}) AS n_called_tracked,
    count(*) FILTER (NOT tracked AND description IN {_CALLED_TUPLE}) AS n_untracked_called,
    count(*) FILTER (({_BLANK_ANY}) AND NOT ({_BLANK_ALL})) AS n_partial_blank,
    count(*) FILTER (
        tracked AND plate_x_mid IS NULL AND vy0 IS NOT NULL AND ay IS NOT NULL
        AND vy0 < 0 AND ay > 0
    ) AS n_geometry_unexplained,
    count(*) FILTER (vy0 IS NOT NULL AND ay IS NOT NULL AND NOT (vy0 < 0 AND ay > 0))
        AS n_kin_invalid,
    count(*) FILTER (game_date <> "date") AS n_game_date_mismatch,
    count(*) FILTER (batter_height_in IS NOT NULL) AS n_height,
    count(*) FILTER (plate_x_mid IS NOT NULL) AS n_geometry,
    count(*) FILTER (tracked AND {_T_MID_SQL} >= {T_MAJOR_MAX_S!r}) AS n_t_ge_major,
    count(*) FILTER (tracked AND {_T_MID_SQL} >= {T_UNPHYSICAL_S!r}) AS n_t_unphysical
FROM read_parquet('{{part}}')
"""

#: The four clauses that are always zero on a correct build. `n_t_ge_major` and
#: `n_untracked_called` are counted and reported, never enforced: the first is
#: position-player lobs, the second is the tracking dropout the called-pitch
#: mart excludes (DT-04's leak is at the mart, not here).
ZERO_CLAUSES: Final[tuple[str, ...]] = (
    "n_partial_blank",
    "n_geometry_unexplained",
    "n_kin_invalid",
    "n_game_date_mismatch",
    "n_t_unphysical",
)

_STAT_NAMES: Final[tuple[str, ...]] = (
    "n_rows",
    "n_tracked",
    "n_called",
    "n_called_tracked",
    "n_untracked_called",
    "n_partial_blank",
    "n_geometry_unexplained",
    "n_kin_invalid",
    "n_game_date_mismatch",
    "n_height",
    "n_geometry",
    "n_t_ge_major",
    "n_t_unphysical",
)


def _day_stats(con: duckdb.DuckDBPyConnection, part: Path) -> dict[str, int]:
    row = con.execute(_STATS_SQL.format(part=part)).fetchone()
    return {name: int(value) for name, value in zip(_STAT_NAMES, row or (), strict=True)}


def normalize_day(
    con: duckdb.DuckDBPyConnection,
    *,
    level: str,
    season: int,
    day: _dt.date,
    source: Path,
    ball_radius_in: float = BALL_R_IN,
    heights_relation: str | None = None,
) -> dict[str, Any]:
    """Convert one day file. Returns the day's statistics plus `written`."""
    target = out_path(level, season, day)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp.parquet")
    if tmp.exists():
        tmp.unlink()
    select = day_sql(
        source=str(source),
        level=level,
        season=season,
        day=day,
        ball_radius_in=ball_radius_in,
        heights_relation=heights_relation,
    )
    con.execute(
        f"COPY ({select}) TO '{tmp}' "
        f"(FORMAT PARQUET, COMPRESSION {PARQUET_COMPRESSION}, "
        f"COMPRESSION_LEVEL {PARQUET_COMPRESSION_LEVEL})"
    )
    written = _write_if_changed(target, tmp)
    stats = _day_stats(con, target)
    stats["written"] = int(written)
    stats["date"] = day.isoformat()
    return stats


# --------------------------------------------------------------------------
# The build
# --------------------------------------------------------------------------

_HEIGHTS_RELATION: Final[str] = "dim_heights"


def _connection(heights_frame: Any = None) -> duckdb.DuckDBPyConnection:
    """One DuckDB connection for one worker.

    `threads = 1` on purpose. The parallelism is one day per worker, which keeps
    each CSV scan single-threaded and therefore keeps row order, and so the
    Parquet bytes, stable between runs (B-7).
    """
    con = duckdb.connect()
    con.execute("SET threads TO 1")
    con.execute("SET preserve_insertion_order TO true")
    if heights_frame is not None:
        con.register(_HEIGHTS_RELATION, heights_frame)
    return con


def _season_heights(level: str, season: int) -> Any:
    """W2.7's batter-season heights for one level-season, or None when absent."""
    try:
        dim = heights.read_dim(level)
    except Exception:  # pragma: no cover - a missing dimension is not fatal here
        return None
    if dim.is_empty():
        return None
    frame = dim.filter(dim["season"] == int(season))
    if frame.is_empty():
        return None
    return frame.select(["batter", "height_in", "height_source"])


def _chunks(items: Sequence[Any], parts: int) -> list[list[Any]]:
    parts = max(1, int(parts))
    out: list[list[Any]] = [[] for _ in range(parts)]
    for index, item in enumerate(items):
        out[index % parts].append(item)
    return [chunk for chunk in out if chunk]


def build(
    *,
    levels: Iterable[str] = ("mlb",),
    seasons: Iterable[int] = (),
    threads: int = 8,
    ball_radius_in: float = BALL_R_IN,
    stream: Any = None,
) -> dict[str, Any]:
    """Convert every day of every requested level-season. Idempotent.

    Returns the summary fragment this run produced. The file on disk merges it
    over whatever earlier runs recorded, so converting one season does not drop
    another season's counts.
    """
    # Resolved at call time. A default bound to `sys.stdout` at import time
    # writes past any redirection the caller set up.
    stream = sys.stdout if stream is None else stream
    report: dict[str, Any] = {}
    for level in levels:
        for season in sorted({int(value) for value in seasons}):
            days = day_files(level, int(season))
            if not days:
                continue
            plane = plane_source(level, int(season))
            frame = _season_heights(level, int(season))
            started = time.monotonic()
            stats: list[dict[str, Any]] = []

            def run(
                chunk: list[tuple[_dt.date, Path]],
                _level: str = level,
                _season: int = int(season),
                _frame: Any = frame,
            ) -> list[dict[str, Any]]:
                con = _connection(_frame)
                try:
                    return [
                        normalize_day(
                            con,
                            level=_level,
                            season=_season,
                            day=day,
                            source=source,
                            ball_radius_in=ball_radius_in,
                            heights_relation=None if _frame is None else _HEIGHTS_RELATION,
                        )
                        for day, source in chunk
                    ]
                finally:
                    con.close()

            parts = _chunks(days, threads)
            if len(parts) == 1:
                stats.extend(run(parts[0]))
            else:
                with _futures.ThreadPoolExecutor(max_workers=len(parts)) as pool:
                    for result in pool.map(run, parts):
                        stats.extend(result)
            elapsed = time.monotonic() - started
            totals = {
                key: sum(int(row[key]) for row in stats)
                for key in stats[0]
                if key not in {"date", "written"}
            }
            totals["n_days"] = len(stats)
            totals["n_written"] = sum(int(row["written"]) for row in stats)
            totals["plane_source"] = plane
            totals["ball_radius_in"] = float(ball_radius_in)
            totals["first_date"] = min(row["date"] for row in stats)
            totals["last_date"] = max(row["date"] for row in stats)
            report.setdefault(level, {})[str(season)] = totals
            print(
                f"W2.14 {level} {season}: {totals['n_days']} days, {totals['n_rows']} rows, "
                f"{totals['n_written']} parts written, plane {plane}, {elapsed:.1f} s",
                file=stream,
            )
    _merge_summary(report)
    return report


def _merge_summary(report: dict[str, Any]) -> bool:
    """Merge this run's counts into `summary.json`. True when the file changed."""
    path = summary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    seasons = dict(current.get("seasons", {}))
    for level, by_season in report.items():
        merged = dict(seasons.get(level, {}))
        merged.update(by_season)
        seasons[level] = merged
    payload = {"dataset": DATASET, "part": PART, "seasons": seasons}
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if path.exists() and path.read_bytes() == body:
        return False
    tmp = path.with_suffix(".tmp.json")
    tmp.write_bytes(body)
    os.replace(tmp, path)
    return True


def read_summary() -> dict[str, Any]:
    """The build summary on disk, or an empty skeleton."""
    path = summary_path()
    if not path.exists():
        return {"dataset": DATASET, "part": PART, "seasons": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def parts(level: str | None = None, season: int | None = None) -> list[Path]:
    """Every converted part on the open side, sorted."""
    root = paths.data_root() / "interim" / DATASET
    pattern = f"level={level or '*'}/season={season or '*'}/date=*/part-{PART:03d}.parquet"
    return sorted(root.glob(pattern))


def read_day(
    level: str, season: int, day: Any, con: duckdb.DuckDBPyConnection | None = None
) -> Any:
    """One converted day as a DuckDB relation."""
    owned = con is None
    con = con or _connection()
    try:
        return con.execute(
            f"SELECT * FROM read_parquet('{out_path(level, season, day)}')"
        ).to_arrow_table()
    finally:
        if owned:
            con.close()


# --------------------------------------------------------------------------
# --check: the clauses the data tests assert, run from the command line
# --------------------------------------------------------------------------


def check(
    *, levels: Iterable[str] = ("mlb",), seasons: Iterable[int] = (), stream: Any = None
) -> int:
    """0 when the built corpus satisfies W2.14. One line per failed clause."""
    stream = sys.stdout if stream is None else stream
    failures: list[str] = []
    summary = read_summary().get("seasons", {})
    for level in levels:
        for season in sorted({int(value) for value in seasons}):
            days = day_files(level, season)
            if not days:
                continue
            missing = [
                day.isoformat() for day, _ in days if not out_path(level, season, day).exists()
            ]
            if missing:
                failures.append(
                    f"{level} {season}: {len(missing)} days not converted, first {missing[0]}"
                )
            recorded = summary.get(level, {}).get(str(season))
            if recorded is None:
                failures.append(f"{level} {season}: no summary entry")
                continue
            if recorded["n_days"] != len(days):
                failures.append(
                    f"{level} {season}: summary records {recorded['n_days']} days, "
                    f"disk holds {len(days)}"
                )
            for clause in ZERO_CLAUSES:
                if recorded.get(clause, 0) != 0:
                    failures.append(f"{level} {season}: {clause} is {recorded[clause]}, expected 0")
            if recorded.get("plane_source") != plane_source(level, season):
                failures.append(
                    f"{level} {season}: plane_source {recorded.get('plane_source')!r} on disk"
                )
    sample = parts()
    if sample:
        con = _connection()
        try:
            got = tuple(
                row[0]
                for row in con.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{sample[-1]}')"
                ).fetchall()
            )
        finally:
            con.close()
        if got != output_columns():
            failures.append(f"{sample[-1]}: column list does not match the W2.14 contract")
    for line in failures:
        print(f"W2.14 check: {line}", file=stream)
    if not failures:
        print(f"W2.14 check: {len(sample)} parts, every clause holds", file=stream)
    return 1 if failures else 0


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def parse_seasons(text: str) -> tuple[int, ...]:
    """`2026`, `2015..2026` and `2022,2024` all parse. Sorted, deduplicated."""
    out: set[int] = set()
    for piece in str(text).split(","):
        piece = piece.strip()
        if not piece:
            continue
        if ".." in piece:
            first, last = piece.split("..", 1)
            out.update(range(int(first), int(last) + 1))
        else:
            out.add(int(piece))
    return tuple(sorted(out))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m absump.ingest.normalize_sc",
        description="W2.14. Typed Statcast days with both plate planes and the harmonised zone.",
    )
    parser.add_argument("--level", default="mlb", help="mlb, aaa, or a comma separated list")
    parser.add_argument("--season", default="2015..2026", help="2026, 2015..2026 or 2022,2024")
    parser.add_argument("--threads", type=int, default=8, help="days converted in parallel")
    parser.add_argument(
        "--ball-radius-in",
        type=float,
        default=BALL_R_IN,
        help=f"r for edge_dist_in, W4 verified at {BALL_R_IN}",
    )
    parser.add_argument(
        "--check", action="store_true", help="verify a built corpus, convert nothing"
    )
    parser.add_argument("--list", action="store_true", help="print the day count and exit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    levels = tuple(piece.strip() for piece in str(args.level).split(",") if piece.strip())
    seasons = parse_seasons(args.season)
    if args.list:
        for level in levels:
            for season in seasons:
                days = day_files(level, season)
                if days:
                    print(f"{level} {season}: {len(days)} days")
        return 0
    if args.check:
        return check(levels=levels, seasons=seasons)
    build(levels=levels, seasons=seasons, threads=args.threads, ball_radius_in=args.ball_radius_in)
    return check(levels=levels, seasons=seasons)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
