"""DT-04, DT-11, DT-12, DT-13, DT-17. The normalised Statcast pitch table, SOP step W2.14.

The step emits both plate planes explicitly, the harmonised zone and the edge
distance, and this file is where its five test ids live:

    DT-04  blank-coordinate rows are exactly `automatic_ball` plus untracked,
           and the `tracked` filter keeps every one of them out of the
           called-pitch population
    DT-11  2026 reprojects at `y = 8.5/12`, 2025 at `y = 17/12`; round trip
           identity; smaller-root selection
    DT-12  distinct `sz_top/sz_bot` ratios, one for 2026, more than a thousand
           for 2022 to 2025
    DT-13  `sz_top*12/0.535` against `sz_bot*12/0.27`
    DT-17  null rates on the called-pitch population

Two kinds of test, the same split `tests/data/test_statcast_days.py` uses.

SYNTHETIC tests build their own kinematics and assert the geometry the module
generates. They need no data and run in a clean clone, which is RP-08.

SWEEP tests read the converted corpus under `data/interim/statcast_pitch/`.
`data/` is gitignored, so they skip when it is absent and say so. One shared
DuckDB connection does the scanning, and the whole-corpus clauses are gathered
into single queries: 799 parts and 3,108,070 rows are read a handful of times,
not once per assertion.

THE THREE PLACES THE DATA IS WIDER THAN THE GATE, each asserted where the SOP
verified it and reported here rather than quietly relaxed:

1. DT-11's "0 pitches with `t >= 0.60` s" holds on the called-pitch population
   of 2024-09-15, 2025-09-15 and 2026-09-15, the days section 2.5 measured, and
   the whole corpus stays far from the unphysical root. It does not hold over
   every pitch of every day: 4,343 tracked pitches from 2022 to 2026, every one
   of them thrown at 60.2 mph or less, cross later than that, the slowest at
   1.9615 s. Those are the position-player lobs SOP W3.7 excludes from the
   analysis sample. The wrong root would put the same pitch at 9.1839 s, so the
   corpus clause is asserted at 2.0 s.
2. DT-04's "0 leaks" is a clause about `fct_called_pitch`, which W2.18 builds.
   What this layer can prove is that the filter exists and works: 591 rows from
   2022 to 2026 have blank coordinates and a called description, and all 591
   are `tracked = false`, so the mart's `tracked` filter removes them.
3. DT-17's `arm_angle >= 99.9%` is a day figure, 2,280 of 2,281 on 2026-09-15,
   and it is asserted on that day. Per season the called-pitch population runs
   99.03% (2023) to 99.83% (2025), and 99.45% over the corpus. The fourteen
   other columns clear 99.5% in every season.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any

import pytest

from absump import paths
from absump.ingest import normalize_sc as nz
from absump.ingest import statcast_day as sc

duckdb = pytest.importorskip("duckdb")
np = pytest.importorskip("numpy")

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The days section 2.5 and W2.9 measured. Every sweep clause that quotes a
#: number quotes it for one of these.
DAY_2026 = dt.date(2026, 9, 15)
DAY_2025 = dt.date(2025, 9, 15)
DAY_2024 = dt.date(2024, 9, 15)

#: SOP section 2.5: the ABS ratio, 0.535/0.27, printed to eight decimals.
ABS_RATIO = 1.98148148

#: The called-pitch population, from W2.9's contract module.
CALLED = tuple(sorted(sc.CALLED_DESCRIPTIONS))


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def con() -> Any:
    connection = duckdb.connect()
    connection.execute("SET threads TO 4")
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def corpus() -> str:
    """The glob over every converted part, or a skip when nothing is built."""
    parts = nz.parts()
    if not parts:
        pytest.skip("data/interim/statcast_pitch is empty; run make normalize-statcast")
    root = paths.data_root() / "interim" / nz.DATASET
    return str(root / f"level=*/season=*/date=*/part-{nz.PART:03d}.parquet")


def _day(day: dt.date, level: str = "mlb") -> str:
    path = nz.out_path(level, day.year, day)
    if not path.exists():
        pytest.skip(f"{path} is not built")
    return str(path)


def _fetch(con: Any, sql: str) -> tuple:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row


def _arrays(con: Any, sql: str) -> dict[str, Any]:
    table = con.execute(sql).to_arrow_table()
    return {
        name: np.asarray(table[name].to_numpy(zero_copy_only=False)) for name in table.column_names
    }


# --------------------------------------------------------------------------
# An independent re-projection, written from the SOP text and nothing else
# --------------------------------------------------------------------------


def _brute_force_t(y_ft: float, vy0: float, ay: float, y_ref: float = 50.0) -> float:
    """The smallest positive root of 0.5*ay*t^2 + vy0*t + (y_ref - y) = 0.

    Scanned, bracketed and bisected, with no closed form anywhere in it. This is
    the test that separates the two roots: the larger one is nine seconds away
    and a bisection that starts at zero can never reach it first.
    """

    def f(t: float) -> float:
        return 0.5 * ay * t * t + vy0 * t + (y_ref - y_ft)

    step = 1e-4
    low = 0.0
    while low < 20.0:
        high = low + step
        if f(low) == 0.0:
            return low
        if f(low) * f(high) < 0:
            for _ in range(200):
                mid = 0.5 * (low + high)
                if f(low) * f(mid) <= 0:
                    high = mid
                else:
                    low = mid
            return 0.5 * (low + high)
        low = high
    raise AssertionError("no positive root below 20 s")


def _t_at_y(y_ft: float, vy0: Any, ay: Any) -> Any:
    """The closed form of section 2.5 item A1, in numpy, for the array checks."""
    return (-vy0 - np.sqrt(vy0 * vy0 - 2 * ay * (50.0 - y_ft))) / ay


def _double(value: float) -> str:
    """A float as a DuckDB DOUBLE literal.

    A bare decimal literal is DECIMAL in DuckDB, and `vy0 * vy0` then overflows
    DECIMAL(18,17). The production SQL reads DOUBLE columns and never meets it.
    """
    return f"CAST({value!r} AS DOUBLE)"


def _carry(coord: Any, v0: Any, acc: Any, t_to: Any, t_from: Any) -> Any:
    return coord + v0 * (t_to - t_from) + 0.5 * acc * (t_to * t_to - t_from * t_from)


# --------------------------------------------------------------------------
# Synthetic: the schema contract and the generated SQL
# --------------------------------------------------------------------------


def test_schema_contract_covers_the_119_columns() -> None:
    """The typed contract names exactly the columns W2.9 committed to."""
    assert tuple(nz.COLUMN_TYPES) == sc.contract_columns()
    assert len(nz.COLUMN_TYPES) == sc.COLUMN_COUNT


def test_output_column_order() -> None:
    """Raw columns, then the three partition columns, then the W2.14 columns."""
    columns = nz.output_columns()
    assert columns[: sc.COLUMN_COUNT] == sc.contract_columns()
    assert columns[sc.COLUMN_COUNT : sc.COLUMN_COUNT + 3] == ("date", "level", "season")
    assert columns[sc.COLUMN_COUNT + 3 :] == nz.derived_columns()
    for required in (
        "plate_x_front",
        "plate_z_front",
        "plate_x_mid",
        "plate_z_mid",
        "plane_source",
        "batter_height_in",
        "height_source",
        "sz_top_h",
        "sz_bot_h",
        "in_zone_center",
        "edge_dist_in",
    ):
        assert required in columns, required


def test_plane_source_follows_section_2_5() -> None:
    """Front through 2025, middle from 2026, AAA middle from 2024."""
    assert nz.plane_source("mlb", 2015) == nz.PLANE_FRONT
    assert nz.plane_source("mlb", 2025) == nz.PLANE_FRONT
    assert nz.plane_source("mlb", 2026) == nz.PLANE_MID
    assert nz.plane_source("aaa", 2024) == nz.PLANE_MID
    assert nz.plane_source("aaa", 2026) == nz.PLANE_MID
    with pytest.raises(nz.PlaneUndetermined):
        nz.plane_source("aaa", 2023)


def test_geometry_constants_match_the_sop() -> None:
    assert nz.Y_FRONT_FT == 17 / 12
    assert nz.Y_MID_FT == 8.5 / 12
    assert nz.Y_REF_FT == 50.0
    assert nz.PLATE_HALF_W_FT == 8.5 / 12
    assert (nz.ABS_TOP_FRAC, nz.ABS_BOT_FRAC) == (0.535, 0.27)
    assert nz.BALL_R_IN == 1.45
    assert round(nz.ABS_TOP_FRAC / nz.ABS_BOT_FRAC, 8) == ABS_RATIO


def test_closed_form_root_matches_a_brute_force_solve(con: Any) -> None:
    """The generated SQL selects the smaller positive root, section 2.5 item A1.

    The contract's own pitch is in the grid: `vy0 = -136.346`, `ay = 28.540`,
    whose roots at `y = 17/12` are 0.3707 s and 9.1839 s.
    """
    cases = [(-136.346, 28.540), (-110.0, 20.0), (-150.0, 40.0), (-95.0, 24.0), (-125.5, 31.25)]
    for y_ft in (nz.Y_FRONT_FT, nz.Y_MID_FT):
        for vy0, ay in cases:
            sql = nz.t_at_y_sql(y_ft, vy0=_double(vy0), ay=_double(ay))
            got = _fetch(con, f"SELECT {sql}")[0]
            want = _brute_force_t(y_ft, vy0, ay)
            assert abs(got - want) < 1e-12, (y_ft, vy0, ay, got, want)
    slow = _fetch(
        con,
        f"SELECT {nz.t_at_y_sql(nz.Y_FRONT_FT, vy0=_double(-136.346), ay=_double(28.540))}",
    )[0]
    assert 0.3706 < slow < 0.3708, slow


def test_the_guard_nulls_a_row_the_root_would_not_hold_for(con: Any) -> None:
    """`vy0 >= 0` or `ay <= 0` yields NULL, never a root off the wrong branch."""
    for vy0, ay in ((0.0, 28.540), (136.346, 28.540), (-136.346, 0.0)):
        vy0, ay = _double(vy0), _double(ay)
        assert _fetch(con, f"SELECT {nz.t_at_y_sql(nz.Y_MID_FT, vy0=vy0, ay=ay)}")[0] is None


def test_edge_distance_on_four_hand_computed_points(con: Any) -> None:
    """The W4 rule: any part of the ball, Euclidean at a corner, `r = 1.45`.

    Zone half width 8.5 in, bottom 1.5 ft, top 3.5 ft. Centre of the plate at
    2.5 ft is 8.5 in inside the side edge and 12 in from either horizontal edge,
    so the nearest edge is the side: `-8.5 - 1.45`. A pitch 2 in off the side
    edge at mid height is `2 - 1.45`. A pitch 3 in above the top over the middle
    is `3 - 1.45`. A corner miss 3 in out and 4 in high is `5 - 1.45`.
    """
    rows = [
        (0.0, 2.5, -8.5),
        ((8.5 + 2.0) / 12, 2.5, 2.0),
        (0.0, 3.5 + 3.0 / 12, 3.0),
        ((8.5 + 3.0) / 12, 3.5 + 4.0 / 12, 5.0),
    ]
    for x_ft, z_ft, want_signed in rows:
        dx_in = abs(x_ft) * 12 - 8.5
        dz_in = max(1.5 * 12 - z_ft * 12, z_ft * 12 - 3.5 * 12)
        signed = math.hypot(dx_in, dz_in) if dx_in > 0 and dz_in > 0 else max(dx_in, dz_in)
        assert abs(signed - want_signed) < 1e-12, (x_ft, z_ft, signed)
        assert abs((signed - nz.BALL_R_IN) - (want_signed - 1.45)) < 1e-12
        assert (signed <= 0) == (want_signed <= 0)


def test_parse_seasons() -> None:
    assert nz.parse_seasons("2026") == (2026,)
    assert nz.parse_seasons("2015..2026") == tuple(range(2015, 2027))
    assert nz.parse_seasons("2022,2024") == (2022, 2024)


# --------------------------------------------------------------------------
# DT-04. Blank coordinates
# --------------------------------------------------------------------------


def test_dt04_blank_coordinate_rows(con: Any, corpus: str) -> None:
    """DT-04. Blank rows are `automatic_ball` plus untracked, and none leak.

    The four tracking columns are blank together or not at all, every blank row
    carries `tracked = false`, and no row that survives the `tracked` filter has
    a blank coordinate. That filter is what keeps them out of `fct_called_pitch`.
    """
    blank_all = " AND ".join(f"{column} IS NULL" for column in sc.TRACKING_COLUMNS)
    blank_any = " OR ".join(f"{column} IS NULL" for column in sc.TRACKING_COLUMNS)
    row = _fetch(
        con,
        f"""
        SELECT
            count(*),
            count(*) FILTER (({blank_any}) AND NOT ({blank_all})),
            count(*) FILTER (({blank_all}) AND tracked),
            count(*) FILTER (({blank_all}) AND description IN {CALLED}),
            count(*) FILTER (({blank_all}) AND description IN {CALLED} AND tracked),
            count(*) FILTER (tracked AND description IN {CALLED} AND ({blank_any})),
            count(*) FILTER (NOT tracked AND NOT ({blank_all}))
        FROM read_parquet('{corpus}')
        """,
    )
    (
        n_rows,
        partial,
        blank_tracked,
        blank_called,
        blank_called_tracked,
        leaks,
        untracked_with_data,
    ) = row
    assert n_rows > 0
    assert partial == 0, f"{partial} rows blank one tracking column but not the others"
    assert blank_tracked == 0, f"{blank_tracked} blank-coordinate rows are marked tracked"
    assert untracked_with_data == 0, f"{untracked_with_data} untracked rows still carry coordinates"
    assert blank_called_tracked == 0
    assert leaks == 0, f"{leaks} tracked called pitches carry a blank coordinate"
    assert blank_called > 0, "the untracked called pitches that the mart filter has to remove"


def test_dt04_the_verified_day(con: Any) -> None:
    """DT-04 on 2026-09-15: 20 blank rows of 4,427, 19 `automatic_ball`, 1 foul."""
    counts = dict(
        con.execute(
            f"SELECT description, count(*) FROM read_parquet('{_day(DAY_2026)}') "
            "WHERE NOT tracked GROUP BY 1"
        ).fetchall()
    )
    assert counts == {"automatic_ball": 19, "foul": 1}, counts
    n_rows, n_called = _fetch(
        con,
        f"SELECT count(*), count(*) FILTER (description IN {CALLED}) "
        f"FROM read_parquet('{_day(DAY_2026)}')",
    )
    assert (n_rows, n_called) == (4427, 2281), (n_rows, n_called)


# --------------------------------------------------------------------------
# DT-11. Both planes
# --------------------------------------------------------------------------


_GEOM_COLUMNS = (
    "plate_x, plate_z, vx0, vy0, vz0, ax, ay, az, "
    "plate_x_front, plate_z_front, plate_x_mid, plate_z_mid"
)


def test_dt11_the_measured_plane_is_returned_bit_for_bit(con: Any) -> None:
    """DT-11. 2026 reprojects at `y = 8.5/12`, 2025 at `y = 17/12`.

    The pair `plane_source` names is the measured one, so re-projecting it to
    its own plane is the identity and the emitted column equals raw `plate_x`
    and `plate_z` exactly, not to a tolerance.
    """
    mid = _fetch(
        con,
        f"SELECT max(abs(plate_x_mid - plate_x)), max(abs(plate_z_mid - plate_z)), "
        f"any_value(plane_source) FROM read_parquet('{_day(DAY_2026)}') WHERE tracked",
    )
    assert mid[2] == nz.PLANE_MID
    assert mid[0] == 0.0 and mid[1] == 0.0, mid
    front = _fetch(
        con,
        f"SELECT max(abs(plate_x_front - plate_x)), max(abs(plate_z_front - plate_z)), "
        f"any_value(plane_source) FROM read_parquet('{_day(DAY_2025)}') WHERE tracked",
    )
    assert front[2] == nz.PLANE_FRONT
    assert front[0] == 0.0 and front[1] == 0.0, front


def test_dt11_reprojection_against_an_independent_implementation(con: Any) -> None:
    """DT-11's `< 1e-6 ft`. The other plane, recomputed from the SOP recipe."""
    for day, y_src, y_dst, dst_x, dst_z in (
        (DAY_2026, nz.Y_MID_FT, nz.Y_FRONT_FT, "plate_x_front", "plate_z_front"),
        (DAY_2025, nz.Y_FRONT_FT, nz.Y_MID_FT, "plate_x_mid", "plate_z_mid"),
    ):
        data = _arrays(
            con,
            f"SELECT {_GEOM_COLUMNS} FROM read_parquet('{_day(day)}') "
            "WHERE tracked AND vy0 IS NOT NULL",
        )
        t_src = _t_at_y(y_src, data["vy0"], data["ay"])
        t_dst = _t_at_y(y_dst, data["vy0"], data["ay"])
        want_x = _carry(data["plate_x"], data["vx0"], data["ax"], t_dst, t_src)
        want_z = _carry(data["plate_z"], data["vz0"], data["az"], t_dst, t_src)
        assert np.max(np.abs(data[dst_x] - want_x)) < 1e-6
        assert np.max(np.abs(data[dst_z] - want_z)) < 1e-6
        assert np.all(t_dst > t_src) if y_dst < y_src else np.all(t_dst < t_src)


def test_dt11_round_trip_identity(con: Any) -> None:
    """DT-11's `< 1e-12 ft`. Front to middle and back is the identity."""
    data = _arrays(
        con,
        f"SELECT {_GEOM_COLUMNS} FROM read_parquet('{_day(DAY_2025)}') "
        "WHERE tracked AND vy0 IS NOT NULL",
    )
    t_front = _t_at_y(nz.Y_FRONT_FT, data["vy0"], data["ay"])
    t_mid = _t_at_y(nz.Y_MID_FT, data["vy0"], data["ay"])
    back_x = _carry(data["plate_x_mid"], data["vx0"], data["ax"], t_front, t_mid)
    back_z = _carry(data["plate_z_mid"], data["vz0"], data["az"], t_front, t_mid)
    assert np.max(np.abs(back_x - data["plate_x_front"])) < 1e-12
    assert np.max(np.abs(back_z - data["plate_z_front"])) < 1e-12


def test_dt11_smaller_root_selection(con: Any) -> None:
    """DT-11's root clause, against a brute-force solve and on the sign of `dz`.

    The 200 rows are a stride sample of one day, which is what a Python
    bisection can carry. The corpus clause is the `t` count below.
    """
    data = _arrays(
        con,
        f"SELECT {_GEOM_COLUMNS} FROM read_parquet('{_day(DAY_2025)}') "
        "WHERE tracked AND vy0 IS NOT NULL ORDER BY plate_x",
    )
    step = max(1, len(data["vy0"]) // 200)
    for index in range(0, len(data["vy0"]), step):
        vy0 = float(data["vy0"][index])
        ay = float(data["ay"][index])
        for y_ft in (nz.Y_FRONT_FT, nz.Y_MID_FT):
            closed = float(_t_at_y(y_ft, vy0, ay))
            assert abs(closed - _brute_force_t(y_ft, vy0, ay)) < 1e-12, (vy0, ay, y_ft)
    t_mid = _t_at_y(nz.Y_MID_FT, data["vy0"], data["ay"])
    t_front = _t_at_y(nz.Y_FRONT_FT, data["vy0"], data["ay"])
    assert np.all(t_mid > t_front)
    falling = data["vz0"] + data["az"] * t_mid < 0
    dz = data["plate_z_mid"] - data["plate_z_front"]
    assert np.all(dz[falling] < 0), "a falling pitch cannot gain height between the planes"
    mean_dz_in = float(np.mean(dz) * 12)
    assert -1.10 <= mean_dz_in <= -0.90, mean_dz_in


def test_dt11_plate_times_stay_physical(con: Any, corpus: str) -> None:
    """DT-11's `t` clause: on the measured days, and away from the wrong root.

    0 pitches at or above 0.60 s on the called-pitch population of the three
    days section 2.5 measured. Over the corpus the clause is 2.0 s, because the
    position-player lobs W3.7 excludes cross as late as 1.9615 s while the
    unphysical root sits at 9.1839 s.
    """
    t_mid = f"(-vy0 - sqrt(vy0 * vy0 - 2 * ay * ({nz.Y_REF_FT!r} - {nz.Y_MID_FT!r}))) / ay"
    for day in (DAY_2024, DAY_2025, DAY_2026):
        late, n_called, slowest = _fetch(
            con,
            f"SELECT count(*) FILTER ({t_mid} >= {nz.T_MAJOR_MAX_S!r}), count(*), max({t_mid}) "
            f"FROM read_parquet('{_day(day)}') WHERE tracked AND description IN {CALLED}",
        )
        assert late == 0, f"{day}: {late} called pitches at or past {nz.T_MAJOR_MAX_S} s"
        assert n_called > 1000 and slowest < nz.T_MAJOR_MAX_S
    unphysical, late, slowest = _fetch(
        con,
        f"SELECT count(*) FILTER ({t_mid} >= {nz.T_UNPHYSICAL_S!r}), "
        f"count(*) FILTER ({t_mid} >= {nz.T_MAJOR_MAX_S!r}), max({t_mid}) "
        f"FROM read_parquet('{corpus}') WHERE tracked",
    )
    assert unphysical == 0, f"{unphysical} pitches cross at or after {nz.T_UNPHYSICAL_S} s"
    assert slowest < nz.T_UNPHYSICAL_S, slowest
    assert late > 0, "the position-player lobs are still in the corpus, and still counted"


def test_dt11_agrees_with_the_geometry_twin() -> None:
    """The seam to W3.3. `src/absump/geometry.py` is the shared module the SOP
    names, and it belongs to the next phase. The moment it lands this compares
    it to the SQL this step generates, on the same closed form, to 1e-12 s.
    """
    geometry = pytest.importorskip(
        "absump.geometry", reason="W3.3 has not built src/absump/geometry.py yet"
    )
    t_at_y = getattr(geometry, "t_at_y", None)
    if t_at_y is None:  # pragma: no cover - depends on W3.3's final surface
        pytest.skip("absump.geometry has no t_at_y")
    for vy0, ay in ((-136.346, 28.540), (-110.0, 20.0), (-150.0, 40.0)):
        for y_ft in (nz.Y_FRONT_FT, nz.Y_MID_FT):
            assert abs(float(t_at_y(y_ft, vy0, ay)) - _brute_force_t(y_ft, vy0, ay)) < 1e-12


# --------------------------------------------------------------------------
# DT-12 and DT-13. The zone
# --------------------------------------------------------------------------


def _season_glob(level: str, season: int) -> str:
    root = paths.data_root() / "interim" / nz.DATASET
    glob = root / f"level={level}" / f"season={season}" / "date=*" / f"part-{nz.PART:03d}.parquet"
    if not nz.parts(level, season):
        pytest.skip(f"{level} {season} is not built")
    return str(glob)


def test_dt12_distinct_zone_ratios(con: Any) -> None:
    """DT-12. One ratio in 2026, more than a thousand in 2022 to 2025.

    The ratio is rounded to the eight decimals section 2.5 prints, which is the
    resolution the figure 1.98148148 is stated at. Unrounded, the last bits of
    two rounded CSV fields differ and 2026-09-15 shows 216 ratios rather than 1.

    Section 2.5 verified "exactly 1" on 2026-09-15 and that holds. Over the
    whole 2026 season it does not: 1,144 of 688,686 tracked rows, 0.17%, carry
    an operator-set ratio, and every one of them is inside four games, 825093
    and 825094 at AZ on 2026-04-25 and 2026-04-26, 823669 at MIN on 2026-08-13
    and 823745 at MIL on 2026-08-23. The bound below is what keeps that a
    handful of named games rather than a drift.
    """
    ratio = "round(sz_top / sz_bot, 8)"
    distinct, value = _fetch(
        con,
        f"SELECT count(DISTINCT {ratio}), any_value({ratio}) "
        f"FROM read_parquet('{_day(DAY_2026)}') WHERE tracked",
    )
    assert distinct == 1, f"2026-09-15 carries {distinct} zone ratios"
    assert value == ABS_RATIO, value
    n_rows, n_off, n_games = _fetch(
        con,
        f"SELECT count(*), count(*) FILTER ({ratio} <> {ABS_RATIO!r}), "
        f"count(DISTINCT game_pk) FILTER ({ratio} <> {ABS_RATIO!r}) "
        f"FROM read_parquet('{_season_glob('mlb', 2026)}') WHERE tracked",
    )
    assert n_off / n_rows <= 0.005, f"{n_off} of {n_rows} 2026 rows are not on the ABS ratio"
    assert n_games <= 10, f"{n_games} games in 2026 carry an operator-set zone"
    for day in (DAY_2024, DAY_2025):
        distinct = _fetch(
            con,
            f"SELECT count(DISTINCT {ratio}) FROM read_parquet('{_day(day)}') WHERE tracked",
        )[0]
        assert distinct > 1000, f"{day}: {distinct} operator-set zone ratios"


def test_dt13_the_abs_height_is_recoverable_from_either_edge(con: Any) -> None:
    """DT-13. `sz_top*12/0.535` equals `sz_bot*12/0.27` to under 1e-6 in.

    True of the fixed ABS zone, which is 2026 at MLB, and asserted on the day
    section 2.5 measured. Over the 2026 season the rows where the two edges
    disagree are exactly the rows DT-12 found off the ABS ratio, in both
    directions, so those four games are the whole of the exception and there is
    no second failure mode hiding behind them.

    The operator-set seasons are the reason the harmonised zone exists: on
    2025-09-15 the same subtraction is off by inches, not by a millionth.
    """
    recovered = "abs(sz_top * 12 / 0.535 - sz_bot * 12 / 0.27)"
    worst = _fetch(
        con, f"SELECT max({recovered}) FROM read_parquet('{_day(DAY_2026)}') WHERE tracked"
    )[0]
    assert worst < 1e-6, worst
    ratio = "round(sz_top / sz_bot, 8)"
    abs_but_disagree, off_but_agree = _fetch(
        con,
        f"SELECT count(*) FILTER ({ratio} = {ABS_RATIO!r} AND {recovered} >= 1e-6), "
        f"count(*) FILTER ({ratio} <> {ABS_RATIO!r} AND {recovered} < 1e-6) "
        f"FROM read_parquet('{_season_glob('mlb', 2026)}') WHERE tracked",
    )
    assert abs_but_disagree == 0, f"{abs_but_disagree} ABS-ratio rows fail the height recovery"
    assert off_but_agree == 0, f"{off_but_agree} operator-set rows pass it"
    operator = _fetch(
        con, f"SELECT max({recovered}) FROM read_parquet('{_day(DAY_2025)}') WHERE tracked"
    )[0]
    assert operator > 1.0, operator


def test_the_harmonised_zone_is_the_height_times_the_fractions(con: Any) -> None:
    """`sz_top_h = 0.535*H/12` and `sz_bot_h = 0.27*H/12`, for every season.

    And on the ABS season the harmonised zone reproduces the published one:
    99.82% of 2026 rows agree to 1e-6 ft. The rest are the stale non-ABS rows
    W2.7's modal rule already refused to take a height from.
    """
    for season in (2022, 2026):
        root = paths.data_root() / "interim" / nz.DATASET
        glob = f"{root}/level=mlb/season={season}/date=*/part-{nz.PART:03d}.parquet"
        worst_top, worst_bot, n_height, n_rows = _fetch(
            con,
            f"SELECT max(abs(sz_top_h - {nz.ABS_TOP_FRAC!r} * batter_height_in / 12)), "
            f"max(abs(sz_bot_h - {nz.ABS_BOT_FRAC!r} * batter_height_in / 12)), "
            "count(batter_height_in), count(*) "
            f"FROM read_parquet('{glob}')",
        )
        assert worst_top == 0.0 and worst_bot == 0.0, (season, worst_top, worst_bot)
        assert n_height == n_rows, f"{season}: {n_rows - n_height} rows without a height"
    share = _fetch(
        con,
        "SELECT 1.0 * count(*) FILTER (abs(sz_top_h - sz_top) < 1e-6) / count(*) "
        f"FROM read_parquet('{paths.data_root() / 'interim' / nz.DATASET}"
        f"/level=mlb/season=2026/date=*/part-{nz.PART:03d}.parquet') "
        "WHERE tracked AND height_source = 'abs_measured'",
    )[0]
    assert share >= 0.995, share


def test_edge_distance_and_in_zone_center_agree(con: Any) -> None:
    """`in_zone_center` is `edge_dist_in + r <= 0`, and `r` is on every row."""
    rows, disagree, radii, iz = _fetch(
        con,
        "SELECT count(*), "
        "count(*) FILTER (in_zone_center <> (edge_dist_in + edge_dist_r_in <= 0)), "
        "count(DISTINCT edge_dist_r_in), count(*) FILTER (in_zone_center) "
        f"FROM read_parquet('{_day(DAY_2026)}') WHERE tracked",
    )
    assert disagree == 0
    assert radii == 1
    assert 0 < iz < rows
    assert (
        _fetch(con, f"SELECT any_value(edge_dist_r_in) FROM read_parquet('{_day(DAY_2026)}')")[0]
        == nz.BALL_R_IN
    )


# --------------------------------------------------------------------------
# DT-17. Null rates on the called-pitch population
# --------------------------------------------------------------------------

_DT17_COLUMNS = (
    "plate_x_mid",
    "plate_z_mid",
    "sz_top",
    "sz_bot",
    "zone",
    "fielder_2",
    "delta_run_exp",
    "delta_home_win_exp",
    "balls",
    "strikes",
    "outs_when_up",
    "inning",
    "inning_topbot",
    "stand",
    "p_throws",
)


def test_dt17_null_rates_on_the_called_pitch_population(con: Any, corpus: str) -> None:
    """DT-17. Each listed column is at least 99.5% non-null, per season.

    `plate_x_mid` and `plate_z_mid` are the re-projected pair, which is what the
    models read. Raw `plate_x` never leaves this layer (R-02).
    """
    select = ", ".join(f"1.0 * count({column}) / count(*)" for column in _DT17_COLUMNS)
    rows = con.execute(
        f"SELECT season, count(*), {select} FROM read_parquet('{corpus}') "
        f"WHERE description IN {CALLED} GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert rows, "no called pitches in the corpus"
    for row in rows:
        season, n_called = row[0], row[1]
        assert n_called > 0
        for column, share in zip(_DT17_COLUMNS, row[2:], strict=True):
            assert share >= 0.995, f"{season} {column}: {share:.6f} non-null"


def test_dt17_arm_angle(con: Any, corpus: str) -> None:
    """DT-17's `arm_angle >= 99.9%`, asserted where section 2.5 measured it.

    2,280 of 2,281 called pitches on 2026-09-15. Over whole seasons the column
    is thinner: 99.03% in 2023, 99.45% across 2022 to 2026. The season floor
    below is a regression guard measured on this corpus, not the DT-17 gate.
    """
    n_called, non_null = _fetch(
        con,
        f"SELECT count(*), count(arm_angle) FROM read_parquet('{_day(DAY_2026)}') "
        f"WHERE description IN {CALLED}",
    )
    assert (n_called, non_null) == (2281, 2280), (n_called, non_null)
    assert non_null / n_called >= 0.999
    rows = con.execute(
        f"SELECT season, 1.0 * count(arm_angle) / count(*) FROM read_parquet('{corpus}') "
        f"WHERE description IN {CALLED} GROUP BY 1 ORDER BY 1"
    ).fetchall()
    for season, share in rows:
        assert share >= 0.99, f"{season} arm_angle: {share:.6f} non-null"


# --------------------------------------------------------------------------
# The build itself
# --------------------------------------------------------------------------


def test_every_source_day_has_a_part() -> None:
    """One Parquet part per raw day, for every season the lake holds."""
    seen = 0
    for season in range(2015, 2027):
        days = nz.day_files("mlb", season)
        if not days:
            continue
        seen += len(days)
        missing = [
            day.isoformat() for day, _ in days if not nz.out_path("mlb", season, day).exists()
        ]
        assert not missing, f"{season}: {len(missing)} days not converted, first {missing[0]}"
    if seen == 0:
        pytest.skip("no raw Statcast days on this machine")
    assert len(nz.parts()) >= seen


def test_the_plane_recorded_on_disk_is_the_plane_for_that_season(con: Any, corpus: str) -> None:
    """One `plane_source` per season, and it is the one section 2.5 states."""
    rows = con.execute(
        f"SELECT level, season, count(DISTINCT plane_source), any_value(plane_source) "
        f"FROM read_parquet('{corpus}') GROUP BY 1, 2 ORDER BY 1, 2"
    ).fetchall()
    assert rows
    for level, season, distinct, plane in rows:
        assert distinct == 1, (level, season, distinct)
        assert plane == nz.plane_source(level, season), (level, season, plane)


def test_converting_a_day_twice_writes_nothing(con: Any) -> None:
    """B-7. A second run leaves the tree byte for byte as the first left it."""
    import hashlib

    target = nz.out_path("mlb", 2026, DAY_2026)
    if not target.exists():
        pytest.skip("2026-09-15 is not built")
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    source = dict((day, path) for day, path in nz.day_files("mlb", 2026))[DAY_2026]
    frame = nz._season_heights("mlb", 2026)
    connection = nz._connection(frame)
    try:
        stats = nz.normalize_day(
            connection,
            level="mlb",
            season=2026,
            day=DAY_2026,
            source=source,
            heights_relation=None if frame is None else nz._HEIGHTS_RELATION,
        )
    finally:
        connection.close()
    assert stats["written"] == 0, "the second conversion replaced the part"
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before
    assert not list(target.parent.glob("*.tmp.parquet")), "a temporary part was left behind"


def test_the_summary_records_the_zero_clauses() -> None:
    """Every season on disk reports the clauses `--check` enforces."""
    summary = nz.read_summary().get("seasons", {})
    if not summary:
        pytest.skip("no build summary on this machine")
    for level, by_season in summary.items():
        for season, totals in by_season.items():
            for clause in nz.ZERO_CLAUSES:
                assert totals[clause] == 0, f"{level} {season} {clause} is {totals[clause]}"
            assert totals["n_days"] > 0
            assert totals["ball_radius_in"] == nz.BALL_R_IN
            assert totals["plane_source"] == nz.plane_source(level, int(season))


def test_check_passes_on_the_built_corpus(capsys: Any) -> None:
    """`--check` is the command line form of the clauses above."""
    seasons = [season for season in range(2015, 2027) if nz.day_files("mlb", season)]
    if not seasons:
        pytest.skip("no raw Statcast days on this machine")
    assert nz.check(levels=("mlb",), seasons=seasons) == 0
    assert "every clause holds" in capsys.readouterr().out
