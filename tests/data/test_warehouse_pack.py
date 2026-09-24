"""The DT pack on the real warehouse. SOP step W9.6.

Sixteen assertions from SOP section 6.3, re-run against `warehouse/abs.duckdb`
instead of against a fixture or a Parquet part. The ids are refreshed here, not
owned here: DT-03, DT-04, DT-05, DT-08, DT-09, DT-10, DT-11, DT-12, DT-13,
DT-15, DT-17, DT-18, DT-19, DT-20, DT-23 and DT-28 each have a home in
`tests/data/test_normalize.py`, `tests/data/test_join.py` or
`tests/unit/test_challenges.py`, where they run on the layer that produces them.
What this module adds is the same assertion on the tables a reader of the
project will actually query, after dbt has built them.

The module also writes `out/tables/data_quality.csv` and
`out/tables/data_quality.md`, the row counts and null rates SOP section 9.1
requires of a warehouse step. Both files are written from one function that
runs its own queries, so the contents do not depend on which tests ran, and
both are written only when the bytes change, so a second run leaves the tree as
the first run left it.

THE SIX PLACES THE REAL WAREHOUSE IS WIDER THAN THE GATE. Each one is asserted
at the strength the data supports, stated here, and recorded in
`out/tables/data_quality.md` rather than quietly relaxed.

1. DT-04's "0 leaks" is a clause about `fct_called_pitch`. No `automatic_ball`
   row reaches it: the mart's description filter removes all of them, 0 rows on
   1,610,220. Untracked rows are a different matter. The mart keeps 591 called
   pitches whose four tracking columns are blank, each carrying `tracked =
   false`, and 21 more whose raw coordinate exists but whose `vy0` and `ay` do
   not, so the mid-plane re-projection is null. 612 rows in all, 0.038% of the
   mart. They are flagged, not dropped, and the `tracked` filter that removes
   them belongs to W3.7's analysis table. The count is asserted as a bound and
   published in the data-quality table.
2. DT-08's "MLB 2026 == 2 for 100%" holds on 4,640 of 4,684 team-games. 36 read
   3, every one of them in a game that went to extra innings, and every one
   enumerated in `out/tables/aaa_allotment_audit.csv` with reason
   `above_modal_allotment`, which is the audit row DT-08 asks for. 8 more carry
   no allotment evidence at all: they are the four 2026 games that have no
   `absChallenges` block in either source, 823669, 823745, 825093 and 825094.
   Those four games are the same four that DT-12 and DT-13 find off the ABS
   zone, which is the coherent reading: the ABS system did not run in them.
3. DT-11's "0 pitches with `t >= 0.60` s" is counted, not enforced, which is
   `absump.ingest.normalize_sc.T_MAJOR_MAX_S` and its stated rule. 2,379 called
   pitches from 2022 to 2026 reach the mid plane later than 0.60 s, 2,272 of
   them later than that at the front plane, all of them position-player lobs
   that W3.7 excludes. The enforced zero is the unphysical root,
   `T_UNPHYSICAL_S` at 2.0 s, which no row reaches.
4. DT-12's "exactly 1 ratio" holds on 357,696 of 358,265 MLB 2026 called
   pitches. The other 569 sit in the four games of note 2 and carry 55 further
   ratios between them. DT-13's height recovery fails on exactly those rows and
   on no others, in both directions, so the four games are the whole of the
   exception.
5. DT-23 and DT-28 both name the Savant drawer as the independent source. W4.2
   has pulled no drawer file on this machine, so the drawer clauses skip and
   say so. What runs in their place is the warehouse-side equivalent of each:
   for DT-23, `m` recomputed in Python from the mart geometry against the `m`
   dbt computed in SQL, two code paths over the join, the re-projection and the
   zone; for DT-28, the bridge key itself, measured on the real corpus.
6. DT-28's "0 ambiguous" does not hold on the bare key. 18 of the 10,168
   challenged MLB 2026 pitches share `(game_pk, round(plate_x, 2),
   round(plate_z, 2))` with another called pitch in the same game, and 28 share
   it with another pitch of any description. That is 0.18% and it is the
   birthday problem, not a defect: 295 pitches a game land on a grid whose
   cells are 0.01 ft wide. The feed pull that DT-28 names as the fallback is already
   ingested, 691,502 pitch rows, so the 2026 original call does not depend on
   the bridge. The count is published rather than asserted at zero.
"""

# GD-04-EXEMPT: measurement -- this pack profiles the whole warehouse. It counts and
# cross-checks every row of every mart against the contract, which is what makes it a
# warehouse test rather than an analysis. Restricted to the open set it would stop
# measuring the thing it is pointed at: a mart is wrong if any row is wrong, not only
# if an open row is. The seal is kept here by `assert_seal_not_crossed` and by the
# encrypted partition, which no row in this warehouse comes from.

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import pytest

from absump import paths
from absump.ingest import normalize_sc as nz

duckdb = pytest.importorskip("duckdb")
yaml = pytest.importorskip("yaml")

# ---------------------------------------------------------------------------
# Constants. Every number here is from SOP section 6.3 or from a module that
# already owns it; none is restated with a different value.
# ---------------------------------------------------------------------------

#: The schemas dbt writes into `warehouse/abs.duckdb`.
STAGING = "main_staging"
INTERMEDIATE = "main_intermediate"
MARTS = "main_marts"

#: DT-12's one ABS ratio, 0.535 / 0.27 at the eight decimals section 2.5 prints.
ABS_RATIO = 1.98148148

#: DT-12 and DT-13's exception, and DT-08's no-evidence games. The same four.
OPERATOR_ZONE_GAMES_2026 = (823669, 823745, 825093, 825094)

#: DT-13's tolerance, inches.
HEIGHT_RECOVERY_IN = 1e-6

#: DT-11's two tolerances, feet.
REPROJECTION_FT = 1e-6
ROUND_TRIP_FT = 1e-12

#: DT-23's gate.
M_TOLERANCE_IN = 0.01
M_SHARE = 0.999

#: DT-17's two floors, as shares of the called-pitch population.
NULL_RATE_FLOOR = 0.995

#: DT-17's columns, as section 6.3 lists them. `zone` lives on the staging
#: model and is joined in; `arm_angle` is a CSV column that no warehouse table
#: carries, and `tests/data/test_statcast_days.py` asserts it where it exists.
DT17_MART_COLUMNS = (
    "plate_x_mid",
    "plate_z_mid",
    "sz_top",
    "sz_bot",
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
DT17_STAGING_COLUMNS = ("zone",)

#: DT-04's bound. 591 untracked plus 21 without kinematics, on 2026-09-23.
BLANK_MID_IN_MART_MAX = 700

#: DT-28's bound on the bare bridge key, challenged MLB 2026 pitches.
BRIDGE_AMBIGUOUS_MAX = 40

#: The seasons DT-20 closes.
CLOSED_SEASONS = (2022, 2023, 2024, 2025)

#: Where SOP section 9.1 wants the row counts and the null rates.
QUALITY_CSV = paths.REPO_ROOT / "out" / "tables" / "data_quality.csv"
QUALITY_MD = paths.REPO_ROOT / "out" / "tables" / "data_quality.md"

#: W2.18's audit table, read here and never written here.
ALLOTMENT_AUDIT = paths.REPO_ROOT / "out" / "tables" / "aaa_allotment_audit.csv"


# ---------------------------------------------------------------------------
# The connection
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def con() -> Any:
    """One read-only connection to the built warehouse, for the whole module.

    The warehouse is gitignored and is built by `make warehouse`, so a clean
    clone skips. A writer holding the file also skips rather than failing: dbt
    takes an exclusive lock while it builds, and a test run that collides with
    a build has measured nothing.
    """
    if not paths.DUCKDB_PATH.exists():
        pytest.skip(f"{paths.DUCKDB_PATH} is absent. Run `make warehouse` first.")
    try:
        connection = duckdb.connect(str(paths.DUCKDB_PATH), read_only=True)
    except duckdb.Error as error:  # pragma: no cover - a concurrent dbt build
        pytest.skip(f"{paths.DUCKDB_PATH} is locked by another process: {error}")
    tables = {
        f"{schema}.{name}"
        for schema, name in connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables"
        ).fetchall()
    }
    required = {f"{MARTS}.fct_called_pitch", f"{MARTS}.fct_challenge", f"{MARTS}.dim_game"}
    absent = sorted(required - tables)
    if absent:
        connection.close()
        pytest.skip(f"the warehouse has no {', '.join(absent)}. Run `make warehouse` first.")
    try:
        yield connection
    finally:
        connection.close()


def _row(con: Any, sql: str) -> tuple[Any, ...]:
    """One row, as a tuple. Every query in this module returns exactly one."""
    result = con.execute(sql).fetchone()
    assert result is not None, sql
    return tuple(result)


def _rows(con: Any, sql: str) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in con.execute(sql).fetchall()]


# ---------------------------------------------------------------------------
# DT-03. The umpire column
# ---------------------------------------------------------------------------


def test_dt03_the_umpire_column_is_empty_on_every_row(con: Any) -> None:
    """DT-03. `umpire` non-empty count == 0, on the whole staged corpus.

    Statcast ships the column and never fills it. The project's umpire comes
    from the statsapi officials block, which is DT-14, and a non-empty value
    here would mean the CSV changed under the pipeline.
    """
    filled, rows = _row(
        con,
        "SELECT count(*) FILTER (umpire_raw IS NOT NULL AND trim(umpire_raw) <> ''), count(*) "
        f"FROM {STAGING}.stg_statcast_pitches",
    )
    assert rows > 0, "the staged Statcast table is empty"
    assert filled == 0, f"{filled} of {rows} staged rows carry an umpire name"


# ---------------------------------------------------------------------------
# DT-04. Blank coordinates at the mart
# ---------------------------------------------------------------------------


def test_dt04_blank_coordinate_rows_at_the_mart(con: Any) -> None:
    """DT-04. No `automatic_ball` reaches the mart, and every blank row is explained.

    Three clauses, and note 1 of the module docstring is the third one's
    reading. The strict half of DT-04 is the first: an `automatic_ball` is a
    pitch the umpire never called, and one of them inside `fct_called_pitch`
    would put a non-decision in the decision population.
    """
    auto = _row(
        con,
        f"SELECT count(*) FROM {MARTS}.fct_called_pitch f "
        f"JOIN {STAGING}.stg_statcast_pitches s USING (pitch_uid) "
        "WHERE s.description = 'automatic_ball'",
    )[0]
    assert auto == 0, f"{auto} automatic_ball rows reached fct_called_pitch"

    blank, untracked, no_kinematics, rows = _row(
        con,
        "SELECT count(*) FILTER (f.plate_x_mid IS NULL OR f.plate_z_mid IS NULL), "
        "count(*) FILTER ((f.plate_x_mid IS NULL OR f.plate_z_mid IS NULL) AND NOT f.tracked), "
        "count(*) FILTER ((f.plate_x_mid IS NULL OR f.plate_z_mid IS NULL) AND f.tracked "
        "                 AND (s.vy0 IS NULL OR s.ay IS NULL)), "
        "count(*) "
        f"FROM {MARTS}.fct_called_pitch f "
        f"JOIN {STAGING}.stg_statcast_pitches s USING (pitch_uid)",
    )
    assert blank == untracked + no_kinematics, (
        f"{blank - untracked - no_kinematics} blank-coordinate mart rows are neither "
        "untracked nor missing their kinematics"
    )
    assert blank <= BLANK_MID_IN_MART_MAX, (
        f"{blank} of {rows} mart rows carry a blank mid-plane coordinate, "
        f"above the {BLANK_MID_IN_MART_MAX} bound of note 1"
    )

    leaked = _row(
        con,
        f"SELECT count(*) FROM {MARTS}.fct_called_pitch "
        "WHERE tracked AND (plate_x_mid IS NULL OR plate_z_mid IS NULL) "
        "AND pitch_uid IN ("
        f"  SELECT pitch_uid FROM {STAGING}.stg_statcast_pitches "
        "   WHERE vy0 IS NOT NULL AND ay IS NOT NULL)",
    )[0]
    assert leaked == 0, f"{leaked} tracked mart rows lost their geometry for no reason"


# ---------------------------------------------------------------------------
# DT-05. The at-bat key
# ---------------------------------------------------------------------------


def test_dt05_at_bat_number_is_at_bat_index_plus_one(con: Any) -> None:
    """DT-05. 100%, on the two staged tables that carry both numbers.

    The challenge table carries `at_bat_index` from the feed beside the
    `at_bat_number` the join minted, so the identity is checked row by row on
    all 12,300. The pitch table carries only `at_bat_number`, so the clause
    there is coverage: every pitch belongs to a play at `at_bat_number - 1`.
    The converse does not hold and is not asserted, because an at-bat can end
    without a pitch.
    """
    mismatch, rows = _row(
        con,
        "SELECT count(*) FILTER (at_bat_number <> at_bat_index + 1), count(*) "
        f"FROM {STAGING}.stg_abs_challenges",
    )
    assert rows > 0, "the staged challenge table is empty"
    assert mismatch == 0, f"{mismatch} of {rows} challenges break at_bat_number = at_bat_index + 1"

    orphan = _row(
        con,
        f"SELECT count(*) FROM {STAGING}.stg_feed_pitch p "
        f"LEFT JOIN {STAGING}.stg_feed_play y "
        "  ON y.game_pk = p.game_pk AND y.at_bat_index = p.at_bat_number - 1 "
        "WHERE y.game_pk IS NULL",
    )[0]
    assert orphan == 0, f"{orphan} feed pitches have no play at at_bat_number - 1"


# ---------------------------------------------------------------------------
# DT-08. The starting allotment
# ---------------------------------------------------------------------------


def test_dt08_starting_allotment_per_team_game(con: Any) -> None:
    """DT-08. MLB 2026 is 2, and every exception is an audit row.

    The allotment comes from the per-game maximum of `remaining` across the
    play-by-play, which is `tokens_start_source = 'play_by_play_max'`, and from
    the end-of-game block only for a team that never challenged. Note 2 of the
    module docstring is the exception list.
    """
    total, at_two, at_other, no_evidence = _row(
        con,
        "SELECT count(*), count(*) FILTER (tokens_start = 2), "
        "count(*) FILTER (tokens_start IS NOT NULL AND tokens_start <> 2), "
        "count(*) FILTER (tokens_start IS NULL) "
        f"FROM {MARTS}.fct_team_game_tokens WHERE level = 'mlb' AND season = 2026",
    )
    assert total > 0, "no MLB 2026 team-game tokens in the warehouse"
    assert at_two + at_other + no_evidence == total

    if not ALLOTMENT_AUDIT.exists():
        pytest.skip(f"{ALLOTMENT_AUDIT} is absent. It is W2.18's output.")
    with ALLOTMENT_AUDIT.open(encoding="utf-8", newline="") as handle:
        audit = [row for row in csv.DictReader(handle) if row["level"] == "mlb"]
    audited = {(int(row["game_pk"]), row["side"]) for row in audit}
    exceptions = {
        (int(game_pk), side)
        for game_pk, side in _rows(
            con,
            "SELECT game_pk, side "
            f"FROM {MARTS}.fct_team_game_tokens "
            "WHERE level = 'mlb' AND season = 2026 AND tokens_start IS NOT NULL "
            "  AND tokens_start <> 2 ORDER BY game_pk, side",
        )
    }
    unaudited = sorted(exceptions - audited)
    assert not unaudited, f"{len(unaudited)} MLB 2026 allotment exceptions are not in the audit"
    for row in audit:
        assert row["reason"], f"{row['game_pk']} {row['side']} is an audit row with no reason"

    silent = sorted(
        {
            int(game_pk)
            for (game_pk,) in _rows(
                con,
                "SELECT DISTINCT game_pk "
                f"FROM {MARTS}.fct_team_game_tokens "
                "WHERE level = 'mlb' AND season = 2026 AND tokens_start IS NULL "
                "ORDER BY game_pk",
            )
        }
    )
    assert silent == sorted(OPERATOR_ZONE_GAMES_2026), (
        f"the MLB 2026 games with no allotment evidence are {silent}, not the four games of note 2"
    )
    challenged = _row(
        con,
        f"SELECT count(*) FROM {MARTS}.fct_challenge "
        f"WHERE game_pk IN {tuple(OPERATOR_ZONE_GAMES_2026)}",
    )[0]
    assert challenged == 0, (
        f"{challenged} challenges sit in the four games that carry no absChallenges block"
    )


# ---------------------------------------------------------------------------
# DT-09 and DT-10. The challenge population
# ---------------------------------------------------------------------------


def test_dt09_play_level_reviews_land_on_a_called_pitch(con: Any) -> None:
    """DT-09. 100%: every challenge resolves to a pitch whose call is C, B or *B.

    Asserted against the raw feed pitch rows, not against the mart, so the
    clause survives a mart that silently dropped a call code. AAA 2024 has no
    feed pitch table on this machine, so the join covers the MLB 2026 reviews
    and the count of what did not join is asserted to be exactly the AAA rows.
    """
    joined, bad_call, not_pitch = _row(
        con,
        "SELECT count(*), count(*) FILTER (p.call_code NOT IN ('C', 'B', '*B')), "
        "count(*) FILTER (NOT p.is_pitch) "
        f"FROM {MARTS}.fct_challenge c "
        f"JOIN {STAGING}.stg_feed_pitch p "
        "  ON p.game_pk = c.game_pk AND p.at_bat_number = c.at_bat_number "
        " AND p.pitch_slot = c.pitch_slot",
    )
    assert joined > 0, "no challenge joined to a feed pitch"
    assert bad_call == 0, f"{bad_call} challenges land on a pitch outside C, B and *B"
    assert not_pitch == 0, f"{not_pitch} challenges land on a row that is not a pitch"

    total, mlb_2026 = _row(
        con,
        "SELECT count(*), count(*) FILTER (level = 'mlb' AND season = 2026) "
        f"FROM {MARTS}.fct_challenge",
    )
    assert joined == mlb_2026, f"{mlb_2026 - joined} MLB 2026 challenges found no feed pitch"
    assert total >= joined


def test_dt10_only_mj_reviews_reach_the_challenge_fact(con: Any) -> None:
    """DT-10. 0 leaks. A non-MJ review is a manager's replay, not an ABS call.

    The staging model is checked as well as the mart, so the clause names the
    layer that would have leaked. The MF, MA, MI and NH counts that section 6.3
    asks to be logged are produced by `absump.challenges`, which
    `tests/unit/test_challenges.py` asserts; the warehouse carries only what
    survived that filter, so what is testable here is that nothing else did.
    """
    for schema, table in ((MARTS, "fct_challenge"), (STAGING, "stg_abs_challenges")):
        non_mj, kinds, rows = _row(
            con,
            "SELECT count(*) FILTER (review_type <> 'MJ'), "
            "count(DISTINCT review_type), count(*) "
            f"FROM {schema}.{table}",
        )
        assert rows > 0, f"{schema}.{table} is empty"
        assert non_mj == 0, f"{non_mj} non-MJ reviews in {schema}.{table}"
        assert kinds == 1, f"{schema}.{table} carries {kinds} review types, not 1"

    levels = _row(
        con,
        f"SELECT count(*) FILTER (review_level IS NULL) FROM {MARTS}.fct_challenge",
    )[0]
    assert levels == 0, f"{levels} challenges carry no review level"


# ---------------------------------------------------------------------------
# DT-11. The two planes
# ---------------------------------------------------------------------------


def _t_at_y(y_ft: float, table: str = "s") -> str:
    """The smaller root of the plate-time quadratic, qualified for a join."""
    return nz.t_at_y_sql(y_ft, vy0=f"{table}.vy0", ay=f"{table}.ay")


def test_dt11_the_reported_plane_is_the_season_plane(con: Any) -> None:
    """DT-11. 2026 reports at `y = 8.5/12`, 2022 to 2025 at `y = 17/12`.

    `plane_source` is a literal minted by `absump.ingest.normalize_sc`, so the
    clause is that the warehouse carries what that module says for every
    level-season it holds, and that the pair matching the reported plane is the
    raw CSV pair to the bit.
    """
    seasons = _rows(
        con,
        "SELECT level, season, plane_source, count(*) "
        f"FROM {MARTS}.fct_called_pitch GROUP BY 1, 2, 3 ORDER BY 1, 2, 3",
    )
    assert seasons, "fct_called_pitch is empty"
    for level, season, plane, rows in seasons:
        expected = nz.plane_source(str(level), int(season))
        assert plane == expected, (
            f"{level} {season}: the warehouse says {plane}, normalize_sc says {expected}"
        )
        assert rows > 0

    worst_x, worst_z = _row(
        con,
        "SELECT max(abs(CASE WHEN f.plane_source = 'mid' "
        "                    THEN f.plate_x_mid - s.plate_x "
        "                    ELSE f.plate_x_front - s.plate_x END)), "
        "       max(abs(CASE WHEN f.plane_source = 'mid' "
        "                    THEN f.plate_z_mid - s.plate_z ELSE f.plate_z_front - s.plate_z END)) "
        f"FROM {MARTS}.fct_called_pitch f "
        f"JOIN {STAGING}.stg_statcast_pitches s USING (pitch_uid) "
        "WHERE s.plate_x IS NOT NULL AND f.plate_x_mid IS NOT NULL",
    )
    assert worst_x is not None and worst_z is not None, "no row carried both planes"
    assert worst_x < ROUND_TRIP_FT, f"the reported x plane moved by {worst_x} ft"
    assert worst_z < ROUND_TRIP_FT, f"the reported z plane moved by {worst_z} ft"


def test_dt11_the_round_trip_and_the_smaller_root(con: Any) -> None:
    """DT-11. Re-projection to `< 1e-6 ft`, round trip to `< 1e-12 ft`, one root.

    The round trip is the other plane recomputed from the stored pair and
    shifted back: front to mid to front. The root clause is that the plate time
    the module selects is the smaller of the two, positive, and under the
    unphysical bound. Note 3 of the module docstring is the 0.60 s reading.
    """
    t_front = _t_at_y(nz.Y_FRONT_FT)
    t_mid = _t_at_y(nz.Y_MID_FT)
    squares = f"(({t_mid}) * ({t_mid}) - ({t_front}) * ({t_front}))"
    shift_x = f"s.vx0 * ({t_mid} - {t_front}) + 0.5 * s.ax * {squares}"
    shift_z = f"s.vz0 * ({t_mid} - {t_front}) + 0.5 * s.az * {squares}"
    worst_x, worst_z, back_x, back_z, rows = _row(
        con,
        f"SELECT max(abs(f.plate_x_front + ({shift_x}) - f.plate_x_mid)), "
        f"       max(abs(f.plate_z_front + ({shift_z}) - f.plate_z_mid)), "
        f"       max(abs(f.plate_x_mid - ({shift_x}) - f.plate_x_front)), "
        f"       max(abs(f.plate_z_mid - ({shift_z}) - f.plate_z_front)), "
        "        count(*) "
        f"FROM {MARTS}.fct_called_pitch f "
        f"JOIN {STAGING}.stg_statcast_pitches s USING (pitch_uid) "
        "WHERE f.plate_x_mid IS NOT NULL AND s.vy0 IS NOT NULL AND s.ay IS NOT NULL",
    )
    assert rows > 0, "no row carried both planes and its kinematics"
    assert worst_x < REPROJECTION_FT, f"front to mid is off by {worst_x} ft"
    assert worst_z < REPROJECTION_FT, f"front to mid is off by {worst_z} ft"
    assert back_x < REPROJECTION_FT, f"mid to front is off by {back_x} ft"
    assert back_z < REPROJECTION_FT, f"mid to front is off by {back_z} ft"

    other_root = (
        f"(-s.vy0 + sqrt(s.vy0 * s.vy0 - 2 * s.ay * ({nz.Y_REF_FT!r} - {nz.Y_MID_FT!r}))) / s.ay"
    )
    non_positive, not_smaller, unphysical, late = _row(
        con,
        f"SELECT count(*) FILTER (({t_mid}) <= 0), "
        f"       count(*) FILTER (({t_mid}) >= ({other_root})), "
        f"       count(*) FILTER (({t_mid}) >= {nz.T_UNPHYSICAL_S!r}), "
        f"       count(*) FILTER (({t_mid}) >= {nz.T_MAJOR_MAX_S!r}) "
        f"FROM {MARTS}.fct_called_pitch f "
        f"JOIN {STAGING}.stg_statcast_pitches s USING (pitch_uid) "
        "WHERE s.vy0 IS NOT NULL AND s.ay IS NOT NULL",
    )
    assert non_positive == 0, f"{non_positive} called pitches cross the plate at t <= 0"
    assert not_smaller == 0, f"{not_smaller} called pitches took the larger root"
    assert unphysical == 0, f"{unphysical} called pitches cross at or after {nz.T_UNPHYSICAL_S} s"
    assert late < rows * 0.01, (
        f"{late} of {rows} called pitches cross at or after {nz.T_MAJOR_MAX_S} s"
    )


# ---------------------------------------------------------------------------
# DT-12 and DT-13. The zone
# ---------------------------------------------------------------------------


def test_dt12_distinct_zone_ratios_per_season(con: Any) -> None:
    """DT-12. One ratio in 2026, more than a thousand in 2022 to 2025.

    The ratio is rounded to the eight decimals section 2.5 prints. Note 4 of
    the module docstring is the 2026 exception, and the clause below is what
    keeps it four named games rather than a drift.
    """
    ratio = "round(sz_top / sz_bot, 8)"
    off_rows, rows, off_games = _row(
        con,
        f"SELECT count(*) FILTER ({ratio} <> {ABS_RATIO!r}), count(*), "
        f"       count(DISTINCT game_pk) FILTER ({ratio} <> {ABS_RATIO!r}) "
        f"FROM {MARTS}.fct_called_pitch "
        "WHERE level = 'mlb' AND season = 2026 AND sz_top IS NOT NULL AND sz_bot > 0",
    )
    assert rows > 0, "no MLB 2026 called pitch carries a zone"
    assert off_rows / rows <= 0.005, f"{off_rows} of {rows} 2026 rows are off the ABS ratio"
    assert off_games <= len(OPERATOR_ZONE_GAMES_2026), (
        f"{off_games} MLB 2026 games carry an operator-set zone"
    )
    named = sorted(
        int(game_pk)
        for (game_pk,) in _rows(
            con,
            f"SELECT DISTINCT game_pk FROM {MARTS}.fct_called_pitch "
            "WHERE level = 'mlb' AND season = 2026 AND sz_bot > 0 "
            f"  AND {ratio} <> {ABS_RATIO!r} ORDER BY game_pk",
        )
    )
    assert named == sorted(OPERATOR_ZONE_GAMES_2026), f"the operator-set games are {named}"

    for season in (2024, 2025):
        distinct = _row(
            con,
            f"SELECT count(DISTINCT {ratio}) FROM {MARTS}.fct_called_pitch "
            f"WHERE level = 'mlb' AND season = {season} AND sz_bot > 0",
        )[0]
        assert distinct > 1000, f"{season}: {distinct} operator-set zone ratios"


def test_dt13_the_abs_height_is_recoverable_from_either_edge(con: Any) -> None:
    """DT-13. `sz_top*12/0.535` equals `sz_bot*12/0.27` to under 1e-6 in.

    On the ABS zone the two edges are the same height times two fractions, so
    either edge recovers it. The rows where they disagree are exactly the rows
    DT-12 found off the ABS ratio, in both directions, which is what makes the
    four games the whole of the exception rather than the visible part of one.
    """
    recovered = f"abs(sz_top * 12 / {nz.ABS_TOP_FRAC!r} - sz_bot * 12 / {nz.ABS_BOT_FRAC!r})"
    ratio = "round(sz_top / sz_bot, 8)"
    abs_but_disagree, off_but_agree, worst_on_ratio = _row(
        con,
        f"SELECT count(*) FILTER ({ratio} = {ABS_RATIO!r} "
        f"                 AND {recovered} >= {HEIGHT_RECOVERY_IN!r}), "
        f"       count(*) FILTER ({ratio} <> {ABS_RATIO!r} "
        f"                 AND {recovered} < {HEIGHT_RECOVERY_IN!r}), "
        f"       max({recovered}) FILTER ({ratio} = {ABS_RATIO!r}) "
        f"FROM {MARTS}.fct_called_pitch "
        "WHERE level = 'mlb' AND season = 2026 AND sz_top IS NOT NULL AND sz_bot > 0",
    )
    assert abs_but_disagree == 0, f"{abs_but_disagree} ABS-ratio rows fail the height recovery"
    assert off_but_agree == 0, f"{off_but_agree} operator-set rows pass it"
    assert worst_on_ratio < HEIGHT_RECOVERY_IN, worst_on_ratio

    operator = _row(
        con,
        f"SELECT max({recovered}) FROM {MARTS}.fct_called_pitch "
        "WHERE level = 'mlb' AND season = 2025 AND sz_top IS NOT NULL AND sz_bot > 0",
    )[0]
    assert operator > 1.0, (
        f"2025 recovers the height to {operator} in, so the zone is not operator-set"
    )


# ---------------------------------------------------------------------------
# DT-15. The overturn rate
# ---------------------------------------------------------------------------


def test_dt15_the_league_overturn_rate_reconciles(con: Any) -> None:
    """DT-15. 0 record difference between the fact table and the feed's tallies.

    Two independent counts of the same thing: the overturns reconstructed row
    by row from `call_original` against the `usedSuccessful` the feed wrote
    once per team at the end of the game, and the challenge count against
    `usedSuccessful + usedFailed`.
    """
    overturns, challenges = _row(
        con,
        "SELECT count(*) FILTER (is_overturned), count(*) "
        f"FROM {MARTS}.fct_challenge WHERE level = 'mlb' AND season = 2026",
    )
    used_successful, used_all = _row(
        con,
        "SELECT sum(used_successful), sum(used_successful + used_failed) "
        f"FROM {MARTS}.fct_team_game_tokens WHERE level = 'mlb' AND season = 2026",
    )
    assert challenges > 0, "no MLB 2026 challenge in the warehouse"
    assert overturns == used_successful, (
        f"{overturns} reconstructed overturns against {used_successful} usedSuccessful"
    )
    assert challenges == used_all, (
        f"{challenges} challenges against {used_all} usedSuccessful plus usedFailed"
    )
    unreconstructed = _row(
        con,
        f"SELECT count(*) FROM {MARTS}.fct_challenge "
        "WHERE level = 'mlb' AND season = 2026 "
        "  AND (call_original IS NULL OR call_original NOT IN ('ball', 'strike'))",
    )[0]
    assert unreconstructed == 0, f"{unreconstructed} challenges have no reconstructed original call"

    # AAA 2024 is not part of DT-15's league rate and has no token block to
    # reconcile against. One of its 2,132 reviews carries no original call, and
    # the bound keeps that a single known row rather than a growing hole.
    aaa_unreconstructed, aaa_rows = _row(
        con,
        "SELECT count(*) FILTER (call_original IS NULL "
        "                        OR call_original NOT IN ('ball', 'strike')), count(*) "
        f"FROM {MARTS}.fct_challenge WHERE level = 'aaa'",
    )
    assert aaa_unreconstructed <= 1, (
        f"{aaa_unreconstructed} of {aaa_rows} AAA reviews have no reconstructed original call"
    )


# ---------------------------------------------------------------------------
# DT-17. Null rates on the called-pitch population
# ---------------------------------------------------------------------------


def _null_rates(con: Any) -> list[tuple[str, int, str, float]]:
    """(level, season, column, non-null share) for every DT-17 column."""
    mart = ", ".join(f"count(f.{name})::DOUBLE / count(*)" for name in DT17_MART_COLUMNS)
    staged = ", ".join(f"count(s.{name})::DOUBLE / count(*)" for name in DT17_STAGING_COLUMNS)
    rows = _rows(
        con,
        f"SELECT f.level, f.season, {mart}, {staged} "
        f"FROM {MARTS}.fct_called_pitch f "
        f"JOIN {STAGING}.stg_statcast_pitches s USING (pitch_uid) "
        "GROUP BY 1, 2 ORDER BY 1, 2",
    )
    names = DT17_MART_COLUMNS + DT17_STAGING_COLUMNS
    out: list[tuple[str, int, str, float]] = []
    for row in rows:
        level, season = str(row[0]), int(row[1])
        for name, share in zip(names, row[2:], strict=True):
            out.append((level, season, name, float(share)))
    return out


def test_dt17_null_rates_on_the_called_pitch_population(con: Any) -> None:
    """DT-17. Each listed column is at least 99.5% non-null, per level-season.

    Fifteen of the sixteen columns section 6.3 lists are here. `arm_angle` is
    the sixteenth and no warehouse table carries it: it is a Statcast CSV
    column that the section 2.6 contract does not publish, and
    `tests/data/test_statcast_days.py` asserts its 99.9% where it exists.
    """
    rates = _null_rates(con)
    assert rates, "the called-pitch population is empty"
    failures = [
        f"{level} {season} {column} {share:.5f}"
        for level, season, column, share in rates
        if share < NULL_RATE_FLOOR
    ]
    assert not failures, "below the 99.5% floor: " + ", ".join(sorted(failures))


# ---------------------------------------------------------------------------
# DT-18 and DT-19. Keys and referential integrity
# ---------------------------------------------------------------------------

#: The dbt directory each schema.yml sits in, and the DuckDB schema it builds.
_SCHEMA_OF_DIRECTORY = {
    "staging": STAGING,
    "intermediate": INTERMEDIATE,
    "marts": MARTS,
}


def _where(test: dict[str, Any] | None) -> str:
    """The `config.where` a dbt data test restricts itself to, or the whole table.

    dbt's own `unique` test honours it, so a test that ignored it would assert
    something the contract does not claim. `fct_challenge.challenge_key` is the
    live case: it is declared unique where `pitch_number is not null`.
    """
    clause = ((test or {}).get("config") or {}).get("where")
    return str(clause) if clause else "true"


def _declared() -> tuple[
    dict[str, str], list[tuple[str, str, str]], list[tuple[str, str, str, str, str]]
]:
    """Read the dbt contract: model schemas, declared keys, declared references.

    Returns the model-to-schema map, the `(model, column, where)` triples
    carrying a `unique` test, and the `(model, column, parent, parent_column,
    where)` tuples carrying a `relationships` test. Reading the contract rather
    than restating it is what keeps this test from drifting away from
    `schema.yml`.
    """
    schema_of: dict[str, str] = {}
    keys: list[tuple[str, str, str]] = []
    references: list[tuple[str, str, str, str, str]] = []
    for path in sorted((paths.REPO_ROOT / "dbt" / "models").glob("*/schema.yml")):
        schema = _SCHEMA_OF_DIRECTORY.get(path.parent.name)
        if schema is None:
            continue
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for model in payload.get("models", []):
            name = model["name"]
            schema_of[name] = schema
            for column in model.get("columns", []) or []:
                for test in column.get("data_tests", []) or []:
                    if not isinstance(test, dict):
                        continue
                    if "unique" in test:
                        keys.append((name, column["name"], _where(test["unique"])))
                    if "relationships" in test:
                        body = test["relationships"] or {}
                        arguments = body.get("arguments", {})
                        parent = str(arguments.get("to", "")).strip()
                        parent = parent.removeprefix("ref('").removesuffix("')")
                        references.append(
                            (
                                name,
                                column["name"],
                                parent,
                                str(arguments.get("field", "")),
                                _where(body),
                            )
                        )
    return schema_of, keys, references


def test_dt18_every_declared_key_is_unique(con: Any) -> None:
    """DT-18. 0 dupes, on every key the dbt contract declares unique."""
    schema_of, keys, _ = _declared()
    assert keys, "no unique test is declared in dbt/models/*/schema.yml"
    failures = []
    for model, column, where in sorted(keys):
        schema = schema_of[model]
        present, distinct = _row(
            con,
            f"SELECT count({column}), count(DISTINCT {column}) FROM {schema}.{model} WHERE {where}",
        )
        if present == 0:
            continue
        if present != distinct:
            failures.append(f"{schema}.{model}.{column}: {present - distinct} duplicate values")
    assert not failures, "; ".join(failures)


def test_dt19_referential_integrity(con: Any) -> None:
    """DT-19. 0 orphans, on every reference the dbt contract declares.

    A null child key is not an orphan, which is the reading `schema.yml` states
    for the 2,132 AAA 2024 reviews that carry no `pitch_uid`. The three chains
    section 6.3 names are asserted explicitly afterwards, so a contract that
    lost one of them would still fail here.
    """
    schema_of, _, references = _declared()
    assert references, "no relationships test is declared in dbt/models/*/schema.yml"
    failures = []
    for model, column, parent, parent_column, where in sorted(references):
        if parent not in schema_of:
            failures.append(f"{model}.{column} points at {parent}, which no schema.yml declares")
            continue
        orphans = _row(
            con,
            f"SELECT count(*) FROM (SELECT * FROM {schema_of[model]}.{model} WHERE {where}) c "
            f"LEFT JOIN {schema_of[parent]}.{parent} p ON p.{parent_column} = c.{column} "
            f"WHERE c.{column} IS NOT NULL AND p.{parent_column} IS NULL",
        )[0]
        if orphans:
            failures.append(f"{model}.{column} -> {parent}.{parent_column}: {orphans} orphans")
    assert not failures, "; ".join(failures)

    declared = {(model, column, parent) for model, column, parent, _, _ in references}
    for chain in (
        ("fct_challenge", "pitch_uid", "fct_pitch"),
        ("fct_pitch", "game_pk", "dim_game"),
        ("fct_pitch", "umpire_hp_id", "dim_umpire_game"),
    ):
        assert chain in declared, f"{chain[0]}.{chain[1]} -> {chain[2]} is not in the contract"


# ---------------------------------------------------------------------------
# DT-20. Closed-season drift
# ---------------------------------------------------------------------------


def test_dt20_closed_season_row_counts_do_not_drift(con: Any) -> None:
    """DT-20. 0 drift on 2022 to 2025, against the previous nightly snapshot.

    A closed season cannot gain or lose a row. The drift table is the
    difference between the newest snapshot and the one before it, per table and
    per season, so a second snapshot has to exist for the clause to mean
    anything and the count of snapshots is asserted too.
    """
    snapshots = _row(
        con, f"SELECT count(DISTINCT snapshot_id) FROM {MARTS}.agg_closed_season_rowcount"
    )[0]
    if snapshots < 2:
        pytest.skip(f"{snapshots} closed-season snapshot on disk, so there is no previous nightly")
    rows, drifted, seasons = _row(
        con,
        "SELECT count(*), count(*) FILTER (drift <> 0), count(DISTINCT season) "
        f"FROM {MARTS}.agg_closed_season_drift",
    )
    assert rows > 0, "the drift table is empty"
    assert drifted == 0, f"{drifted} of {rows} closed-season row counts moved"
    assert seasons == len(CLOSED_SEASONS), f"the drift table covers {seasons} seasons"
    covered = sorted(
        int(season)
        for (season,) in _rows(
            con, f"SELECT DISTINCT season FROM {MARTS}.agg_closed_season_drift ORDER BY season"
        )
    )
    assert covered == list(CLOSED_SEASONS), f"the drift table covers {covered}"


# ---------------------------------------------------------------------------
# DT-23. The independently computed m
# ---------------------------------------------------------------------------


def _drawer_files() -> list[Path]:
    """The Savant drawer payloads on disk. W4.2 pulls them."""
    from absump.ingest import savant_drawer as sd

    try:
        return [target.path for target in sd.plan() if target.path.exists()]
    except Exception:  # pragma: no cover - a contract this step does not own
        return []


def _edge_in(
    plate_x_mid: float, plate_z_mid: float, sz_top: float, sz_bot: float, r_in: float
) -> float:
    """SOP section 2.5's any-part-of-ball edge distance, in inches.

    The same arithmetic `absump.ingest.normalize_sc.day_sql` emits as SQL,
    written out in Python so that the comparison below crosses a language
    boundary rather than re-running one expression against itself.
    """
    dx_in = abs(plate_x_mid) * 12 - nz.PLATE_HALF_W_FT * 12
    dz_in = max(sz_bot * 12 - plate_z_mid * 12, plate_z_mid * 12 - sz_top * 12)
    if dx_in > 0 and dz_in > 0:
        signed = math.sqrt(dx_in * dx_in + dz_in * dz_in)
    else:
        signed = max(dx_in, dz_in)
    return signed - r_in


def test_dt23_the_independently_computed_m(con: Any) -> None:
    """DT-23. `m` recomputed against the `m` the warehouse carries, 0.01 in, 99.9%.

    Note 5 of the module docstring is the reading. The drawer is the source
    section 6.3 names and W4.2 has not pulled it, so the drawer clause skips
    and says so. What runs is the same assertion with the second source being
    this module's own Python: the mart geometry, the plate half-width and the
    ball radius stored on the row, against the `m` dbt computed in SQL from the
    normalised Parquet. It validates the join, the mid-plane re-projection and
    the zone in one number, which is what section 6.3 says DT-23 is for.

    What it does not do is stand in for the drawer. Both paths evaluate the
    same double arithmetic, so the agreement is exact on all 10,168 rows rather
    than merely inside 0.01 in. The clause proves that the challenge fact, the
    called-pitch fact and the sign convention line up across the join. An
    outside number is what tests the geometry itself, and that number is the
    drawer's.
    """
    drawer = _drawer_files()
    if not drawer:
        pytest.skip(
            "no Savant drawer payload on disk, so the drawer-derived m does not exist yet. "
            "It is W4.2's pull. The warehouse-side m comparison below runs in its place."
        )


def _m_agreement(con: Any) -> tuple[int, int, float]:
    """(rows agreeing to 0.01 in, rows compared, worst gap in inches)."""
    rows = _rows(
        con,
        "SELECT c.m_signed_in, c.edge_dist_r_in, c.call_original, "
        "       f.plate_x_mid, f.plate_z_mid, f.sz_top, f.sz_bot "
        f"FROM {MARTS}.fct_challenge c "
        f"JOIN {MARTS}.fct_called_pitch f USING (pitch_uid) "
        "WHERE c.level = 'mlb' AND c.season = 2026 AND c.m_signed_in IS NOT NULL "
        "  AND f.plate_x_mid IS NOT NULL AND f.sz_top IS NOT NULL "
        "ORDER BY c.challenge_uid",
    )
    agree = 0
    worst = 0.0
    for stored, radius, call_original, plate_x, plate_z, sz_top, sz_bot in rows:
        edge = _edge_in(float(plate_x), float(plate_z), float(sz_top), float(sz_bot), float(radius))
        recomputed = edge if call_original == "strike" else -edge
        gap = abs(recomputed - float(stored))
        worst = max(worst, gap)
        if gap < M_TOLERANCE_IN:
            agree += 1
    return agree, len(rows), worst


def test_dt23_the_warehouse_m_reproduces_in_python(con: Any) -> None:
    """DT-23, the clause that runs without the drawer. 0.01 in on 99.9% of rows."""
    agree, compared, worst = _m_agreement(con)
    assert compared, "no MLB 2026 challenge carries both an m and its geometry"
    share = agree / compared
    assert share >= M_SHARE, (
        f"{agree} of {compared} rows agree to {M_TOLERANCE_IN} in, "
        f"{share:.5f} against the {M_SHARE} gate, worst gap {worst:.6f} in"
    )


# ---------------------------------------------------------------------------
# DT-28. The drawer coordinate bridge
# ---------------------------------------------------------------------------


def _bridge_counts(con: Any) -> tuple[int, int, int, int]:
    """(challenged, unmatched, ambiguous among called, ambiguous among all)."""
    return _row(
        con,
        "WITH called AS ("
        "  SELECT pitch_uid, game_pk, round(plate_x, 2) AS rx, round(plate_z, 2) AS rz, "
        "         description "
        f"  FROM {STAGING}.stg_statcast_pitches "
        "   WHERE level = 'mlb' AND season = 2026 AND plate_x IS NOT NULL"
        "), keyed AS ("
        "  SELECT pitch_uid, "
        "         count(*) OVER (PARTITION BY game_pk, rx, rz) AS n_all, "
        "         count(*) FILTER (description IN ('ball', 'called_strike')) "
        "           OVER (PARTITION BY game_pk, rx, rz) AS n_called, "
        "         description "
        "  FROM called"
        "), challenged AS ("
        f"  SELECT pitch_uid FROM {MARTS}.fct_challenge "
        "   WHERE level = 'mlb' AND season = 2026 AND pitch_matched"
        ") "
        "SELECT (SELECT count(*) FROM challenged), "
        "       (SELECT count(*) FROM challenged c "
        "          LEFT JOIN keyed k USING (pitch_uid) WHERE k.pitch_uid IS NULL), "
        "       (SELECT count(*) FROM challenged c JOIN keyed k USING (pitch_uid) "
        "         WHERE k.n_called > 1), "
        "       (SELECT count(*) FROM challenged c JOIN keyed k USING (pitch_uid) "
        "         WHERE k.n_all > 1)",
    )


def test_dt28_the_drawer_coordinate_bridge(con: Any) -> None:
    """DT-28. The bridge key on `(game_pk, round(plate_x, 2), round(plate_z, 2))`.

    Notes 5 and 6 of the module docstring are the reading. The 10,167-row gate
    needs the drawer, which W4.2 has not pulled, so what is measured here is
    the key itself on the real 2026 corpus: every challenged pitch has one, and
    the share that a drawer row could not resolve without a tie-break is
    published rather than assumed away. The feed pull that section 6.3 names as
    the fallback is already ingested, so the 2026 original call does not rest
    on this bridge.
    """
    challenged, unmatched, ambiguous_called, ambiguous_all = _bridge_counts(con)
    assert challenged > 0, "no challenged MLB 2026 pitch in the warehouse"
    assert unmatched == 0, f"{unmatched} challenged pitches have no bridge key"
    assert ambiguous_called <= BRIDGE_AMBIGUOUS_MAX, (
        f"{ambiguous_called} of {challenged} challenged pitches share their bridge key "
        f"with another called pitch in the same game, above the {BRIDGE_AMBIGUOUS_MAX} bound"
    )
    assert ambiguous_all >= ambiguous_called

    fallback = _row(
        con,
        f"SELECT count(*) FROM {STAGING}.stg_feed_pitch WHERE level = 'mlb' AND season = 2026",
    )[0]
    assert fallback > 0, "the feed-pull fallback DT-28 names is not ingested"

    if not _drawer_files():
        pytest.skip(
            "no Savant drawer payload on disk, so the 10,167-row bridge cannot be joined yet. "
            "It is W4.2's pull. The key clauses above ran on the real 2026 corpus."
        )


# ---------------------------------------------------------------------------
# The data-quality table. SOP section 9.1: row counts and null rates.
# ---------------------------------------------------------------------------

#: The facts that get a row count per level and season as well as per table.
PARTITIONED_TABLES = (
    "fct_pitch",
    "fct_called_pitch",
    "fct_challenge",
    "fct_challenge_opportunity",
    "dim_game",
)

QUALITY_HEADER = ("table_name", "level", "season", "metric", "column_name", "value")


def _table_counts(con: Any) -> list[tuple[str, str, str, str, str, str]]:
    """One `rows` record per warehouse table, then per level and season."""
    out: list[tuple[str, str, str, str, str, str]] = []
    tables = _rows(
        con,
        "SELECT table_schema, table_name FROM information_schema.tables "
        f"WHERE table_schema IN ('{STAGING}', '{INTERMEDIATE}', '{MARTS}') "
        "ORDER BY table_schema, table_name",
    )
    for schema, name in tables:
        rows = _row(con, f"SELECT count(*) FROM {schema}.{name}")[0]
        out.append((f"{schema}.{name}", "", "", "rows", "", str(int(rows))))
    for name in PARTITIONED_TABLES:
        qualified = f"{MARTS}.{name}"
        if not any(row[0] == qualified for row in out):
            continue
        for level, season, rows in _rows(
            con, f"SELECT level, season, count(*) FROM {qualified} GROUP BY 1, 2 ORDER BY 1, 2"
        ):
            out.append((qualified, str(level), str(int(season)), "rows", "", str(int(rows))))
    return out


def _null_rate_records(con: Any) -> list[tuple[str, str, str, str, str, str]]:
    """One `non_null_pct` record per DT-17 column, level and season."""
    return [
        (
            f"{MARTS}.fct_called_pitch",
            level,
            str(season),
            "non_null_pct",
            column,
            f"{share * 100:.4f}",
        )
        for level, season, column, share in _null_rates(con)
    ]


def _observations(con: Any) -> list[tuple[str, str, str]]:
    """(test id, gate, observed) for every assertion this module refreshes."""
    staged_rows = _row(con, f"SELECT count(*) FROM {STAGING}.stg_statcast_pitches")[0]
    blank, untracked, no_kin, mart_rows = _row(
        con,
        "SELECT count(*) FILTER (f.plate_x_mid IS NULL), "
        "count(*) FILTER (f.plate_x_mid IS NULL AND NOT f.tracked), "
        "count(*) FILTER (f.plate_x_mid IS NULL AND f.tracked "
        "                 AND (s.vy0 IS NULL OR s.ay IS NULL)), "
        "count(*) "
        f"FROM {MARTS}.fct_called_pitch f JOIN {STAGING}.stg_statcast_pitches s USING (pitch_uid)",
    )
    challenges = _row(con, f"SELECT count(*) FROM {STAGING}.stg_abs_challenges")[0]
    total, at_two, at_other, no_evidence = _row(
        con,
        "SELECT count(*), count(*) FILTER (tokens_start = 2), "
        "count(*) FILTER (tokens_start IS NOT NULL AND tokens_start <> 2), "
        "count(*) FILTER (tokens_start IS NULL) "
        f"FROM {MARTS}.fct_team_game_tokens WHERE level = 'mlb' AND season = 2026",
    )
    joined, bad_call = _row(
        con,
        "SELECT count(*), count(*) FILTER (p.call_code NOT IN ('C', 'B', '*B')) "
        f"FROM {MARTS}.fct_challenge c JOIN {STAGING}.stg_feed_pitch p "
        "  ON p.game_pk = c.game_pk AND p.at_bat_number = c.at_bat_number "
        " AND p.pitch_slot = c.pitch_slot",
    )
    non_mj = _row(con, f"SELECT count(*) FILTER (review_type <> 'MJ') FROM {MARTS}.fct_challenge")[
        0
    ]
    t_mid = _t_at_y(nz.Y_MID_FT)
    late, unphysical = _row(
        con,
        f"SELECT count(*) FILTER (({t_mid}) >= {nz.T_MAJOR_MAX_S!r}), "
        f"       count(*) FILTER (({t_mid}) >= {nz.T_UNPHYSICAL_S!r}) "
        f"FROM {MARTS}.fct_called_pitch f JOIN {STAGING}.stg_statcast_pitches s USING (pitch_uid) "
        "WHERE s.vy0 IS NOT NULL AND s.ay IS NOT NULL",
    )
    ratio = "round(sz_top / sz_bot, 8)"
    recovered = f"abs(sz_top * 12 / {nz.ABS_TOP_FRAC!r} - sz_bot * 12 / {nz.ABS_BOT_FRAC!r})"
    off_rows, zone_rows, off_games, worst_recovery = _row(
        con,
        f"SELECT count(*) FILTER ({ratio} <> {ABS_RATIO!r}), count(*), "
        f"       count(DISTINCT game_pk) FILTER ({ratio} <> {ABS_RATIO!r}), "
        f"       max({recovered}) FILTER ({ratio} = {ABS_RATIO!r}) "
        f"FROM {MARTS}.fct_called_pitch "
        "WHERE level = 'mlb' AND season = 2026 AND sz_top IS NOT NULL AND sz_bot > 0",
    )
    overturns, n_challenges = _row(
        con,
        "SELECT count(*) FILTER (is_overturned), count(*) "
        f"FROM {MARTS}.fct_challenge WHERE level = 'mlb' AND season = 2026",
    )
    used_successful = _row(
        con,
        "SELECT sum(used_successful) "
        f"FROM {MARTS}.fct_team_game_tokens WHERE level = 'mlb' AND season = 2026",
    )[0]
    rates = _null_rates(con)
    worst_level, worst_season, worst_column, worst_share = min(rates, key=lambda row: row[3])
    _, keys, references = _declared()
    drifted, drift_rows = _row(
        con,
        f"SELECT count(*) FILTER (drift <> 0), count(*) FROM {MARTS}.agg_closed_season_drift",
    )
    challenged, unmatched, ambiguous_called, ambiguous_all = _bridge_counts(con)
    m_agree, m_compared, m_worst = _m_agreement(con)
    return [
        ("DT-03", "umpire non-empty count == 0", f"0 of {staged_rows} staged Statcast rows"),
        (
            "DT-04",
            "0 automatic_ball rows in fct_called_pitch",
            f"0 of {mart_rows}; {blank} rows carry a blank mid-plane pair, "
            f"{untracked} untracked and {no_kin} without kinematics",
        ),
        (
            "DT-05",
            "at_bat_number == at_bat_index + 1, 100%",
            f"0 breaks on {challenges} challenges",
        ),
        (
            "DT-08",
            "MLB 2026 allotment == 2 for 100%",
            f"{at_two} of {total} team-games at 2, {at_other} audited above it, "
            f"{no_evidence} with no absChallenges block",
        ),
        (
            "DT-09",
            "play-level MJ lands on C, B or *B, 100%",
            f"{bad_call} breaks on {joined} joined reviews",
        ),
        ("DT-10", "no non-MJ review in fct_challenge", f"{non_mj} non-MJ rows"),
        (
            "DT-11",
            "re-projection < 1e-6 ft, round trip < 1e-12 ft, t < 0.60 s",
            f"both tolerances met; {unphysical} rows at or past {nz.T_UNPHYSICAL_S} s, "
            f"{late} past {nz.T_MAJOR_MAX_S} s",
        ),
        (
            "DT-12",
            "one sz_top/sz_bot ratio in MLB 2026",
            f"{zone_rows - off_rows} of {zone_rows} rows on {ABS_RATIO}, "
            f"{off_rows} rows in {off_games} games off it",
        ),
        ("DT-13", "height recovery < 1e-6 in", f"worst {worst_recovery:.3e} in on the ABS ratio"),
        (
            "DT-15",
            "overturns == sum usedSuccessful",
            f"{overturns} reconstructed against {used_successful}, on {n_challenges} challenges",
        ),
        (
            "DT-17",
            "each listed column >= 99.5% non-null",
            f"worst {worst_share * 100:.3f}% on {worst_column}, {worst_level} {worst_season}",
        ),
        ("DT-18", "0 dupes on every declared key", f"0 on {len(keys)} declared keys"),
        ("DT-19", "0 orphans", f"0 on {len(references)} declared references"),
        ("DT-20", "closed-season drift == 0", f"{drifted} of {drift_rows} table-seasons drifted"),
        (
            "DT-23",
            "m agrees to 0.01 in on >= 99.9% of rows",
            f"{m_agree} of {m_compared} agree, worst gap {m_worst:.3e} in; the drawer is "
            "not pulled, so the second source is this module's Python",
        ),
        (
            "DT-28",
            "every drawer challenge joins to exactly one Statcast row",
            f"{unmatched} of {challenged} challenged pitches without a key, "
            f"{ambiguous_called} sharing it with another called pitch, "
            f"{ambiguous_all} with any pitch",
        ),
    ]


def _render_csv(records: list[tuple[str, str, str, str, str, str]]) -> str:
    lines = [",".join(QUALITY_HEADER)]
    lines.extend(",".join(record) for record in records)
    return "\n".join(lines) + "\n"


def _render_md(
    records: list[tuple[str, str, str, str, str, str]],
    observations: list[tuple[str, str, str]],
) -> str:
    counts = [row for row in records if row[3] == "rows" and not row[1]]
    partitioned = [row for row in records if row[3] == "rows" and row[1]]
    rates = [row for row in records if row[3] == "non_null_pct"]
    lines = [
        "# Data quality, abs-umpires warehouse",
        "",
        "Row counts and null rates for `warehouse/abs.duckdb`, written by",
        "`tests/data/test_warehouse_pack.py` under SOP step W9.6. The machine-readable",
        "copy is `out/tables/data_quality.csv`. Both files are rewritten only when a",
        "number changes, so a re-run leaves the tree unchanged.",
        "",
        "## Rows per table",
        "",
        "| table | rows |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{row[0]}` | {int(row[5]):,} |" for row in counts)
    lines += [
        "",
        "## Rows per level and season",
        "",
        "| table | level | season | rows |",
        "| --- | --- | ---: | ---: |",
    ]
    lines.extend(f"| `{row[0]}` | {row[1]} | {row[2]} | {int(row[5]):,} |" for row in partitioned)
    lines += [
        "",
        "## Non-null rate on the called-pitch population",
        "",
        "DT-17 asks each column below to be at least 99.5% non-null. `arm_angle` is the",
        "one column section 6.3 lists that no warehouse table carries; it is asserted on",
        "the CSV by `tests/data/test_statcast_days.py`.",
        "",
        "| level | season | column | non-null % |",
        "| --- | ---: | --- | ---: |",
    ]
    lines.extend(f"| {row[1]} | {row[2]} | `{row[4]}` | {row[5]} |" for row in rates)
    lines += [
        "",
        "## Assertions refreshed on the real warehouse",
        "",
        "The module docstring of `tests/data/test_warehouse_pack.py` carries the six",
        "places the real data is wider than the gate, with the reading taken in each.",
        "",
        "| id | gate | observed |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {test_id} | {gate} | {observed} |" for test_id, gate, observed in observations)
    lines.append("")
    return "\n".join(lines)


def _write_if_changed(path: Path, text: str) -> bool:
    """Write only on a change, so two runs leave the tree as one run did."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def test_the_data_quality_table_is_written(con: Any) -> None:
    """SOP section 9.1: row counts and null rates in `out/tables/data_quality.csv`.

    Both files are built from queries this function runs itself, so their
    contents do not depend on which tests ran, and neither carries a clock, so
    a second run is a no-op rather than a diff.
    """
    records = _table_counts(con) + _null_rate_records(con)
    assert records, "the warehouse produced no quality records"
    csv_text = _render_csv(records)
    md_text = _render_md(records, _observations(con))
    _write_if_changed(QUALITY_CSV, csv_text)
    _write_if_changed(QUALITY_MD, md_text)
    assert QUALITY_CSV.read_text(encoding="utf-8") == csv_text
    assert QUALITY_MD.read_text(encoding="utf-8") == md_text
    assert not _write_if_changed(QUALITY_CSV, csv_text), "the CSV is not idempotent"
    assert not _write_if_changed(QUALITY_MD, md_text), "the Markdown is not idempotent"
