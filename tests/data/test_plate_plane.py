"""Which plate plane the published coordinates sit on, checked from the release point.

SOP section 2.5 says Statcast publishes `plate_x` and `plate_z` at the front of
the plate (y = 17/12 ft) through 2025 and at its middle (y = 8.5/12 ft) from
2026. `absump.ingest.normalize_sc.plane_source` encodes that sentence, and the
DT-11 tests in test_normalize.py and test_warehouse_pack.py assert that the
normalised columns agree with it. None of them checks the sentence against the
data. This file does, with a point on each pitch's path that the plate
coordinates do not enter: the release point. DECISIONS.md D-P4-46 records why.

THE CHECK. Statcast's nine trajectory parameters describe a flight of constant
acceleration referenced at y = 50 ft: y(t) = 50 + vy0 t + ay t^2 / 2, and the
same form in x and z. `release_pos_x`, `release_pos_y` and `release_pos_z` are
a point on that path. For each pitch:

  1. solve y(t) = release_pos_y for the root nearer zero, which is negative,
     because release lies beyond 50 ft;
  2. back out the position at y = 50 ft from the release point;
  3. carry the path forward to the front plane and to the middle plane, taking
     the first crossing of each;
  4. take the gap between each crossing and the published `plate_x`, `plate_z`.

The root nearer zero of a t^2 + b t + c = 0, with b = vy0 < 0, is
2c / (-b + sqrt(b^2 - 4ac)). It is the same expression at the release point,
where c < 0, and at a plane, where c > 0. It shares no code with
`absump.geometry` or `normalize_sc.t_at_y_sql`.

The published pair lies on the plane whose gap is small. The gap is not zero:
on 2026-09-29 its median in z was 0.030 in at the published plane in every
season, against 0.938 to 0.952 in at the other.

WHAT IT READS. Kinematic columns only, from the open side of the converted
lake, through `normalize_sc.parts()`: the release point, the nine parameters and
`plate_x`, `plate_z`. No description, no call and no outcome. A part dated after
the last open day is dropped by its path before any file is opened, so 2026
stops at the last open day. A row with any of those columns null is left out,
and so is a row whose path, as its parameters describe it, never reaches the
middle plane.

WHAT IT ASSERTS, for each MLB season 2022 to 2026:

  - at the plane `plane_source` names, the median gap in z is under 0.10 in;
  - at the other plane it is over 0.50 in.

WHAT IT WRITES. `out/tables/plate_plane_check.csv`, one row per season: the
days and pitches read, the plane `plane_source` names, the nearer plane, and
the median gap in x and in z at each plane, in inches.
`docs/harmonized_zone.md` section 9 quotes it. The file is rewritten only when
its content changes.

THE LIMIT. The lake is the project's own Statcast Search pull of 2026-09-22 and
2026-09-23 (docs/warehouse.md). A public note (Cowshal, 2026-09-05) reports a
2024 game at mid-plate on a different Savant endpoint. This test says nothing
about any endpoint but the one the lake came from.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest

from absump import paths
from absump.ingest import normalize_sc as nz

duckdb = pytest.importorskip("duckdb")

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "out" / "tables" / "plate_plane_check.csv"

LEVEL = "mlb"
SEASONS = (2022, 2023, 2024, 2025, 2026)

#: Statcast's reference plane for the nine parameters, ft.
Y_REF_FT = 50.0

#: The two planes, from the module that names them, so a change there moves
#: this test too.
PLANES = {nz.PLANE_FRONT: nz.Y_FRONT_FT, nz.PLANE_MID: nz.Y_MID_FT}

#: The gates, in inches. Measured 2026-09-29 on the whole open lake, the median
#: gap in z is 0.030 in at the published plane in every season, and 0.938 to
#: 0.952 in at the other.
AT_PUBLISHED_MAX_IN = 0.10
AT_OTHER_MIN_IN = 0.50

_DATE_IN_PATH = re.compile(r"date=(\d{4}-\d{2}-\d{2})")

_COLUMNS = (
    "release_pos_x",
    "release_pos_y",
    "release_pos_z",
    "vx0",
    "vy0",
    "vz0",
    "ax",
    "ay",
    "az",
    "plate_x",
    "plate_z",
)


def _open_parts(season: int) -> list[str]:
    """The season's converted parts, with every part past the last open day dropped."""
    kept = []
    for part in nz.parts(LEVEL, season):
        found = _DATE_IN_PATH.search(part.as_posix())
        if found is None or paths.is_sealed(found.group(1)):
            continue
        kept.append(str(part))
    return kept


def _t_sql(y_ft: float) -> str:
    """Time to reach y, the root nearer zero, as a DuckDB expression."""
    c = f"({Y_REF_FT!r} - {y_ft!r})"
    return f"(2 * {c} / (-vy0 + sqrt(vy0 * vy0 - 2 * ay * {c})))"


def _season_row(con, season: int, files: list[str]) -> dict[str, object]:
    not_null = " AND ".join(f"{name} IS NOT NULL" for name in _COLUMNS)
    t_rel = (
        f"(2 * ({Y_REF_FT!r} - release_pos_y) / "
        f"(-vy0 + sqrt(vy0 * vy0 - 2 * ay * ({Y_REF_FT!r} - release_pos_y))))"
    )
    gaps = []
    for name, y_ft in PLANES.items():
        t = _t_sql(y_ft)
        gaps.append(
            f"median(abs(x50 + vx0 * {t} + 0.5 * ax * {t} * {t} - plate_x)) * 12 AS gap_x_{name}"
        )
        gaps.append(
            f"median(abs(z50 + vz0 * {t} + 0.5 * az * {t} * {t} - plate_z)) * 12 AS gap_z_{name}"
        )
    sql = f"""
        WITH k AS (
            SELECT CAST(game_date AS DATE) AS game_date, {", ".join(_COLUMNS)}
            FROM read_parquet($files)
            WHERE {not_null} AND vy0 < 0
              AND vy0 * vy0 - 2 * ay * ({Y_REF_FT!r} - {nz.Y_MID_FT!r}) > 0
        ),
        r AS (SELECT *, {t_rel} AS t_rel FROM k),
        p AS (
            SELECT *,
                release_pos_x - vx0 * t_rel - 0.5 * ax * t_rel * t_rel AS x50,
                release_pos_z - vz0 * t_rel - 0.5 * az * t_rel * t_rel AS z50
            FROM r
        )
        SELECT count(DISTINCT game_date) AS n_days, count(*) AS n_pitches,
               max(game_date) AS last_day, {", ".join(gaps)}
        FROM p
    """
    row = con.execute(sql, {"files": files}).fetchone()
    names = [d[0] for d in con.description]
    return dict(zip(names, row, strict=True))


def _render(rows: list[dict[str, object]]) -> str:
    header = [
        "season",
        "n_days",
        "n_pitches",
        "plane_named",
        "plane_nearest",
        "median_gap_z_front_in",
        "median_gap_z_mid_in",
        "median_gap_x_front_in",
        "median_gap_x_mid_in",
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[name] for name in header])
    return buffer.getvalue()


@pytest.fixture(scope="module")
def measured() -> list[dict[str, object]]:
    seasons = {season: _open_parts(season) for season in SEASONS}
    if not any(seasons.values()):
        pytest.skip("data/interim/statcast_pitch holds no MLB part; run make normalize-statcast")
    missing = [season for season, files in seasons.items() if not files]
    assert not missing, f"no converted part on the open side for {missing}"
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    rows = []
    try:
        for season, files in seasons.items():
            got = _season_row(con, season, files)
            assert got["last_day"] <= paths.LAST_OPEN_DATE, f"{season} read past the last open day"
            named = nz.plane_source(LEVEL, season)
            nearest = min(PLANES, key=lambda name: got[f"gap_z_{name}"])
            rows.append(
                {
                    "season": season,
                    "n_days": got["n_days"],
                    "n_pitches": got["n_pitches"],
                    "plane_named": named,
                    "plane_nearest": nearest,
                    "median_gap_z_front_in": f"{got['gap_z_' + nz.PLANE_FRONT]:.3f}",
                    "median_gap_z_mid_in": f"{got['gap_z_' + nz.PLANE_MID]:.3f}",
                    "median_gap_x_front_in": f"{got['gap_x_' + nz.PLANE_FRONT]:.3f}",
                    "median_gap_x_mid_in": f"{got['gap_x_' + nz.PLANE_MID]:.3f}",
                }
            )
    finally:
        con.close()
    text = _render(rows)
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
    return rows


@pytest.mark.parametrize("season", SEASONS)
def test_the_published_plane_is_the_one_plane_source_names(
    measured: list[dict[str, object]], season: int
) -> None:
    row = next(row for row in measured if row["season"] == season)
    named = str(row["plane_named"])
    other = next(name for name in PLANES if name != named)
    at_named = float(row[f"median_gap_z_{named}_in"])
    at_other = float(row[f"median_gap_z_{other}_in"])
    assert at_named < AT_PUBLISHED_MAX_IN, (
        f"{season}: plate_z sits {at_named} in from the {named} plane, which plane_source names"
    )
    assert at_other > AT_OTHER_MIN_IN, (
        f"{season}: plate_z sits only {at_other} in from the {other} plane"
    )
    assert row["plane_nearest"] == named


def test_the_check_reads_no_part_past_the_last_open_day() -> None:
    for season in SEASONS:
        for part in _open_parts(season):
            found = _DATE_IN_PATH.search(part)
            assert found is not None
            assert not paths.is_sealed(found.group(1)), part
