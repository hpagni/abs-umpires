"""DT-05, DT-18, DT-23, DT-28, and the UT-02 refresh. The join, SOP step W2.15.

    DT-05  `at_bat_number == atBatIndex + 1`, 100%
    DT-18  uniqueness of each declared key, 0 dupes
    DT-23  the independently computed `m` against the drawer-derived `m`,
           `< 0.01 in` on at least 99.9% of rows
    DT-28  the drawer coordinate bridge on
           `(game_pk, round(plate_X, 2), round(plate_Z, 2))`
    UT-02  refreshed on the real corpus: the naive `playEvents[].pitchNumber`
           key still false-matches, so the bug cannot come back quietly

Two kinds of test, the split `tests/data/test_normalize.py` uses. SYNTHETIC
tests build their own rows and run in a clean clone. SWEEP tests read the
corpus under `data/interim/`, which is gitignored, so they skip and say so when
it is absent. One DuckDB connection does the scanning.

WHERE THE DATA IS WIDER THAN THE GATE, reported here rather than relaxed.

1. DT-23 names the Savant drawer as the independent source. W4.2 has pulled no
   drawer file yet, so the drawer clause skips and says so, and the same
   assertion runs with the feed as the independent source: `m` computed from
   the API trajectory re-projected to the mid plane against `m` computed from
   the CSV's own mid-plate pair. That is the join, the re-projection and the
   zone in one number, which is what the SOP says DT-23 is for.
2. DT-28 is the same shape. Its 10,167-row gate needs the drawer, so it skips
   until the cache exists. What runs without it is the bridge implementation
   over real 2026 coordinates: every drawer-shaped row finds the pitch it was
   built from, and a within-game near tie is detected rather than silently
   matched.
3. DT-05's 100% is asserted against the raw GUMBO feeds of one full day, 15
   games, recomputed with `absump.joinkey`, plus game `824466`'s documented max
   `atBatIndex` 69 and max `at_bat_number` 70. The whole corpus is covered by
   the weaker structural clause that every game's at-bat numbers start at 1 and
   have no gap.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from absump import joinkey, paths
from absump.ingest import join as jn

LEVEL = "mlb"
SEASON = 2026
SPORT_ID = 1

#: The day DT-05 recomputes from raw JSON: 15 games, 4,472 pitch slots.
RAW_DAY = dt.date(2026, 9, 8)

#: SOP W2.15's reference game: max `atBatIndex` 69, max `at_bat_number` 70.
REFERENCE_GAME = 824466
REFERENCE_DAY = dt.date(2026, 9, 15)

#: The days the `m` comparison runs over. 2026-05-30 is here on purpose: it
#: carries the one row in the season where the CSV coordinate and the feed
#: trajectory disagree, so the 99.9% clause is exercised rather than assumed.
M_DAYS = (dt.date(2026, 4, 15), dt.date(2026, 5, 30), dt.date(2026, 9, 8))

#: DT-23's gate.
M_TOLERANCE_IN = 0.01
M_SHARE = 0.999

#: The 17-inch plate, as the drawer reports it.
PLATE_WIDTH_IN = 17.0


def _partitions() -> list[jn.DayPartition]:
    try:
        return jn.day_partitions(LEVEL, SEASON)
    except jn.JoinError:  # pragma: no cover - a missing source day
        return []


def _joined_parts() -> list[Path]:
    return [part.target for part in _partitions() if part.target.exists()]


@pytest.fixture(scope="module")
def parts() -> list[Path]:
    found = _joined_parts()
    if not found:
        pytest.skip(
            "data/interim/pitch_joined is empty. Run "
            "`uv run python -m absump.ingest.join --level mlb --season 2026` first."
        )
    return found


@pytest.fixture(scope="module")
def con(parts: list[Path]) -> Any:
    duckdb = pytest.importorskip("duckdb")
    connection = duckdb.connect()
    connection.execute("PRAGMA threads=4")
    connection.execute(f"CREATE VIEW j AS SELECT * FROM read_parquet({_sql_list(parts)})")
    try:
        yield connection
    finally:
        connection.close()


def _sql_list(items: list[Path]) -> str:
    return "[" + ", ".join(f"'{item.as_posix()}'" for item in items) + "]"


def _day_part(dataset: str, day: dt.date) -> Path:
    part = paths.lake_path(dataset, LEVEL, SEASON, day)
    if not part.exists():
        pytest.skip(f"{dataset} has no part for {day.isoformat()}")
    return part


def _feed(game_pk: int, day: dt.date) -> dict[str, Any]:
    zstandard = pytest.importorskip("zstandard")
    path = paths.raw_feed(SPORT_ID, SEASON, day, game_pk)
    if not path.exists():
        pytest.skip(f"the raw feed for {game_pk} on {day.isoformat()} is not cached")
    raw = zstandard.ZstdDecompressor().decompress(path.read_bytes(), max_output_size=64_000_000)
    return json.loads(raw)


def _drawer_files() -> list[Path]:
    probe = paths.raw_savant_drawer(LEVEL, SEASON, 147)
    root = probe.parent
    return sorted(root.glob("*.json")) if root.is_dir() else []


# --------------------------------------------------------------------------
# DT-05. at_bat_number == atBatIndex + 1
# --------------------------------------------------------------------------


def test_dt05_at_bat_number_is_at_bat_index_plus_one_on_the_raw_feeds(con: Any) -> None:
    """DT-05, 100%, recomputed from raw GUMBO for every game of one day."""
    part = _day_part(jn.DATASET, RAW_DAY)
    rows = con.execute(
        f"""
        SELECT game_pk, at_bat_number, pitch_slot
        FROM read_parquet('{part.as_posix()}')
        WHERE match_side <> 'csv_only'
        """
    ).fetchall()
    assert rows, "the joined day is empty"
    joined: dict[int, set[tuple[int, int]]] = {}
    for game_pk, at_bat_number, pitch_slot in rows:
        joined.setdefault(int(game_pk), set()).add((int(at_bat_number), int(pitch_slot)))

    checked = 0
    for game_pk, keys in sorted(joined.items()):
        feed = _feed(game_pk, RAW_DAY)
        expected = {(key[1], key[2]) for key, _play, _event in joinkey.game_pitch_keys(feed)}
        assert expected == keys, f"game {game_pk} disagrees with the raw feed"
        for play in feed["liveData"]["plays"]["allPlays"]:
            assert joinkey.at_bat_number(play) == int(play["about"]["atBatIndex"]) + 1
            checked += 1
    assert len(joined) == 15
    assert checked > 0


def test_dt05_reference_game_824466_matches_the_sop_counts(con: Any) -> None:
    """SOP W2.15: max `atBatIndex` 69, max `at_bat_number` 70, 281 slots."""
    part = _day_part(jn.DATASET, REFERENCE_DAY)
    n_api, n_matched, max_ab = con.execute(
        f"""
        SELECT
            sum(CASE WHEN match_side IN ('both', 'api_only') THEN 1 ELSE 0 END),
            sum(CASE WHEN match_side = 'both' THEN 1 ELSE 0 END),
            max(at_bat_number)
        FROM read_parquet('{part.as_posix()}')
        WHERE game_pk = {REFERENCE_GAME}
        """
    ).fetchone()
    assert (n_api, n_matched, max_ab) == (281, 281, 70)
    feed = _feed(REFERENCE_GAME, REFERENCE_DAY)
    indexes = [int(play["about"]["atBatIndex"]) for play in feed["liveData"]["plays"]["allPlays"]]
    assert max(indexes) == 69
    assert max_ab == max(indexes) + 1


def test_dt05_every_joined_at_bat_is_an_at_bat_index_plus_one(con: Any) -> None:
    """The corpus-wide half of DT-05, against W2.13's own play table.

    `feed_play` has grain `(game_pk, at_bat_index)`, so every at-bat in the
    join must appear there at `at_bat_index + 1`: 177,732 at-bats, 0 orphans
    over MLB 2026. The reverse direction is not equality. 37 plays carry no
    pitch slot at all, 36 pickoffs and one game advisory, and every one of them
    has `last_pitch_slot == 0`, so they are absent from a pitch table by
    construction rather than dropped by the key.
    """
    plays = _sql_list([part for part in _dataset_parts("feed_play")])
    orphans, pitchless, pitchless_with_slots = con.execute(
        f"""
        WITH a AS (SELECT DISTINCT game_pk, at_bat_number FROM j WHERE match_side <> 'csv_only'),
             p AS (SELECT game_pk, at_bat_index + 1 AS at_bat_number, last_pitch_slot
                   FROM read_parquet({plays}))
        SELECT
            (SELECT count(*) FROM a ANTI JOIN p USING (game_pk, at_bat_number)),
            (SELECT count(*) FROM p ANTI JOIN a USING (game_pk, at_bat_number)),
            (SELECT count(*) FROM (SELECT * FROM p ANTI JOIN a USING (game_pk, at_bat_number))
             WHERE last_pitch_slot <> 0)
        """
    ).fetchone()
    assert orphans == 0
    assert pitchless_with_slots == 0
    assert pitchless >= 0


def _dataset_parts(dataset: str) -> list[Path]:
    """Every day part of one interim dataset for the level-season under test."""
    days = [part.day for part in _partitions()]
    found = [paths.lake_path(dataset, LEVEL, SEASON, day) for day in days]
    return [path for path in found if path.exists()]


# --------------------------------------------------------------------------
# DT-18. Uniqueness of each declared key
# --------------------------------------------------------------------------


def test_dt18_declared_keys_are_unique(con: Any) -> None:
    """DT-18, 0 dupes, on the joined table and on both of its sources."""
    slot_dupes = con.execute(
        """
        SELECT count(*) FROM (
            SELECT game_pk, at_bat_number, pitch_slot FROM j
            WHERE pitch_slot IS NOT NULL
            GROUP BY 1, 2, 3 HAVING count(*) > 1)
        """
    ).fetchone()[0]
    number_dupes = con.execute(
        """
        SELECT count(*) FROM (
            SELECT game_pk, at_bat_number, pitch_number FROM j
            WHERE pitch_number IS NOT NULL
            GROUP BY 1, 2, 3 HAVING count(*) > 1)
        """
    ).fetchone()[0]
    assert (slot_dupes, number_dupes) == (0, 0)

    found = _partitions()
    for dataset, key, files in (
        (
            jn.FEED_DATASET,
            "game_pk, at_bat_number, pitch_slot",
            _sql_list([part.feed for part in found]),
        ),
        (
            jn.STATCAST_DATASET,
            "game_pk, at_bat_number, pitch_number",
            _sql_list([part.statcast for part in found]),
        ),
    ):
        dupes = con.execute(
            f"SELECT count(*) FROM (SELECT {key} FROM read_parquet({files}) "
            "GROUP BY 1, 2, 3 HAVING count(*) > 1)"
        ).fetchone()[0]
        assert dupes == 0, f"{dataset} has {dupes} duplicate keys"


def test_dt18_the_report_is_one_row_per_game_with_the_sop_columns() -> None:
    """`join_report.csv` carries W2.15's twelve columns and one row per game."""
    import csv

    if not jn.REPORT_PATH.exists():
        pytest.skip("out/tables/join_report.csv is absent. Run the join first.")
    with jn.REPORT_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == list(jn.REPORT_COLUMNS)
        rows = list(reader)
    keys = [(row["level"], row["season"], row["game_pk"]) for row in rows]
    assert len(keys) == len(set(keys))
    assert rows, "the report is empty"


# --------------------------------------------------------------------------
# UT-02 refreshed on the real corpus
# --------------------------------------------------------------------------


def test_ut02_refresh_the_naive_key_still_false_matches_on_the_real_corpus(con: Any) -> None:
    """UT-02 on real 2026 games, not on the fixture.

    `playEvents[].pitchNumber` repeats the previous number on a `no_pitch`, so
    on an at-bat that holds one the naive key yields fewer distinct keys than
    there are pitch slots, and the row that is left over joins to the wrong
    Statcast pitch. The corrected key plus the W2.15 renumbering yields one key
    per slot and matches every row.
    """
    part = _day_part(jn.DATASET, RAW_DAY)
    game_pks = [
        int(row[0])
        for row in con.execute(
            f"SELECT DISTINCT game_pk FROM read_parquet('{part.as_posix()}') ORDER BY 1"
        ).fetchall()
    ]
    naive_short = 0
    corrected_slots = 0
    naive_keys = 0
    for game_pk in game_pks:
        feed = _feed(game_pk, RAW_DAY)
        for play in feed["liveData"]["plays"]["allPlays"]:
            corrected = list(joinkey.pitch_keys(play, game_pk))
            naive = {key for key, _event in joinkey.naive_pitch_keys(play, game_pk)}
            corrected_slots += len(corrected)
            naive_keys += len(naive)
            if len(naive) < len(corrected):
                naive_short += 1
    assert corrected_slots > 0
    assert naive_short > 0, "no at-bat on this day exercises the trap"
    assert naive_keys < corrected_slots

    matched, api_only, csv_only = con.execute(
        f"""
        SELECT sum(CASE WHEN match_side = 'both' THEN 1 ELSE 0 END),
               sum(CASE WHEN match_side = 'api_only' THEN 1 ELSE 0 END),
               sum(CASE WHEN match_side = 'csv_only' THEN 1 ELSE 0 END)
        FROM read_parquet('{part.as_posix()}')
        """
    ).fetchone()
    assert (api_only, csv_only) == (0, 0)
    assert matched == corrected_slots - _unnumbered_on(con, part)


def _unnumbered_on(con: Any, part: Path) -> int:
    """B-1's `no_pitch` events with no call block, which Statcast never numbers."""
    return int(
        con.execute(
            f"SELECT count(*) FROM read_parquet('{part.as_posix()}') "
            "WHERE match_side = 'api_unnumbered'"
        ).fetchone()[0]
    )


def test_the_unnumbered_no_pitch_events_are_exactly_the_ones_without_a_call(con: Any) -> None:
    """B-1, on the corpus: a `no_pitch` takes a Statcast slot when it has a call.

    2,449 `no_pitch` events in MLB 2026. The 2,234 that carry a call code are
    the 2,147 `automatic_ball` and 87 `automatic_strike` rows of the CSV. The
    215 that carry none are on-field delays and balks, and Statcast writes no
    row for them.
    """
    total, with_call, without_call, unnumbered = con.execute(
        """
        SELECT
            sum(CASE WHEN event_type = 'no_pitch' THEN 1 ELSE 0 END),
            sum(CASE WHEN event_type = 'no_pitch' AND call_code IS NOT NULL THEN 1 ELSE 0 END),
            sum(CASE WHEN event_type = 'no_pitch' AND call_code IS NULL THEN 1 ELSE 0 END),
            sum(CASE WHEN match_side = 'api_unnumbered' THEN 1 ELSE 0 END)
        FROM j
        """
    ).fetchone()
    assert total == with_call + without_call
    assert unnumbered == without_call
    automatic = con.execute(
        """
        SELECT sum(CASE WHEN csv_description = 'automatic_ball' THEN 1 ELSE 0 END),
               sum(CASE WHEN csv_description = 'automatic_strike' THEN 1 ELSE 0 END)
        FROM j WHERE match_side = 'both'
        """
    ).fetchone()
    assert with_call == automatic[0] + automatic[1]
    assert (
        con.execute(
            "SELECT count(*) FROM j WHERE match_side = 'api_unnumbered' AND call_code IS NOT NULL"
        ).fetchone()[0]
        == 0
    )


def test_the_join_is_one_hundred_percent_on_every_game(con: Any) -> None:
    """W2.15's benchmark: 100.000%, and anything below it is a defect."""
    n_api, n_csv, n_matched, api_only, csv_only, games = con.execute(
        """
        SELECT sum(CASE WHEN match_side IN ('both', 'api_only') THEN 1 ELSE 0 END),
               sum(CASE WHEN match_side IN ('both', 'csv_only') THEN 1 ELSE 0 END),
               sum(CASE WHEN match_side = 'both' THEN 1 ELSE 0 END),
               sum(CASE WHEN match_side = 'api_only' THEN 1 ELSE 0 END),
               sum(CASE WHEN match_side = 'csv_only' THEN 1 ELSE 0 END),
               count(DISTINCT game_pk)
        FROM j
        """
    ).fetchone()
    assert (api_only, csv_only) == (0, 0)
    assert n_api == n_csv == n_matched
    assert games > 0
    per_game_defects = con.execute(
        """
        WITH g AS (
            SELECT game_pk,
                   sum(CASE WHEN match_side IN ('both', 'api_only') THEN 1 ELSE 0 END) AS n_api,
                   sum(CASE WHEN match_side IN ('both', 'csv_only') THEN 1 ELSE 0 END) AS n_csv,
                   sum(CASE WHEN match_side = 'both' THEN 1 ELSE 0 END) AS n_matched
            FROM j GROUP BY 1
        )
        SELECT count(*) FROM g WHERE n_api <> n_csv OR n_matched <> n_api
        """
    ).fetchone()[0]
    assert per_game_defects == 0


# --------------------------------------------------------------------------
# DT-23. The independently computed `m`
# --------------------------------------------------------------------------


def _m_of(plate_x: float, plate_z: float, sz_top: float, sz_bot: float) -> float:
    """The ABS margin in inches, from `absump.ingest.savant_drawer.edge_dist_in`.

    One implementation of the section 2.5 edge rule, called twice with
    independent coordinates. The formula is not written again here.
    """
    from absump.ingest.savant_drawer import edge_dist_in

    return edge_dist_in(
        {
            "plateX": plate_x,
            "plateZ": plate_z,
            "strikeZoneTop": sz_top,
            "strikeZoneBottom": sz_bot,
            "widthinches": PLATE_WIDTH_IN,
        }
    )


def _m_pairs(con: Any) -> list[tuple[Any, ...]]:
    """`m` from the feed trajectory and `m` from the CSV, on the sample days."""
    joined = _sql_list([_day_part(jn.DATASET, day) for day in M_DAYS])
    statcast = _sql_list([_day_part(jn.STATCAST_DATASET, day) for day in M_DAYS])
    return con.execute(
        f"""
        SELECT a.game_pk, a.at_bat_number, a.pitch_number,
               a.api_x_at_plane, a.api_z_at_plane, a.csv_x_at_plane, a.csv_z_at_plane,
               b.sz_top, b.sz_bot
        FROM read_parquet({joined}) AS a
        JOIN read_parquet({statcast}) AS b
          ON a.game_pk = b.game_pk
         AND a.at_bat_number = b.at_bat_number
         AND a.pitch_number = b.pitch_number
        WHERE a.match_side = 'both'
          AND a.api_x_at_plane IS NOT NULL AND a.csv_x_at_plane IS NOT NULL
          AND b.sz_top IS NOT NULL AND b.sz_bot IS NOT NULL
        ORDER BY 1, 2, 3
        """
    ).fetchall()


def test_dt23_m_from_the_feed_matches_m_from_the_csv(con: Any) -> None:
    """DT-23's assertion with the feed as the independent source.

    The drawer has not been pulled yet, so the second source is the Stats API
    trajectory re-projected to the mid plane. The comparison validates the
    join, the re-projection and the zone in one number, which is what the SOP
    says DT-23 is for. Gate: `< 0.01 in` on at least 99.9% of rows.
    """
    rows = _m_pairs(con)
    assert len(rows) > 10_000, f"only {len(rows)} rows to compare"
    breaches = []
    for game_pk, at_bat, pitch, api_x, api_z, csv_x, csv_z, sz_top, sz_bot in rows:
        gap = abs(_m_of(api_x, api_z, sz_top, sz_bot) - _m_of(csv_x, csv_z, sz_top, sz_bot))
        if gap >= M_TOLERANCE_IN:
            breaches.append((game_pk, at_bat, pitch, gap))
    share = 1.0 - len(breaches) / len(rows)
    assert share >= M_SHARE, f"{len(breaches)} of {len(rows)} rows are {M_TOLERANCE_IN} in apart"


def test_dt23_m_matches_the_drawer_derived_m(con: Any) -> None:
    """DT-23 as written, against the Savant drawer. Needs the W4.2 cache."""
    files = _drawer_files()
    if not files:
        pytest.skip("data/raw/savant/abs_drawer is empty. W4.2 has not pulled it yet.")
    from absump.ingest.savant_drawer import edge_dist_in, load

    drawer = [row for path in files for row in load(path)]
    statcast = _sql_list(_dataset_parts(jn.STATCAST_DATASET))
    pitches = {
        (int(game_pk), jn.round_half_up(x), jn.round_half_up(z)): (x, z, top, bot)
        for game_pk, x, z, top, bot in con.execute(
            f"SELECT game_pk, plate_x_mid, plate_z_mid, sz_top, sz_bot "
            f"FROM read_parquet({statcast}) WHERE plate_x_mid IS NOT NULL"
        ).fetchall()
    }
    compared = 0
    breaches = 0
    for row in drawer:
        key = jn.bridge_key(row["game_pk"], *jn.drawer_coordinates(row))
        hit = pitches.get(key)
        if hit is None:
            continue
        compared += 1
        if abs(edge_dist_in(row) - _m_of(*hit)) >= M_TOLERANCE_IN:
            breaches += 1
    assert compared > 0
    assert 1.0 - breaches / compared >= M_SHARE


# --------------------------------------------------------------------------
# DT-28. The drawer coordinate bridge
# --------------------------------------------------------------------------


def _bridge_sample(
    con: Any, day: dt.date, per_game: int = 4
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drawer-shaped rows built from real pitches, and the pitches to match."""
    part = _day_part(jn.STATCAST_DATASET, day)
    pitches = [
        {"game_pk": int(g), "plate_X": x, "plate_Z": z, "id": (int(g), int(ab), int(pn))}
        for g, ab, pn, x, z in con.execute(
            f"SELECT game_pk, at_bat_number, pitch_number, plate_x_mid, plate_z_mid "
            f"FROM read_parquet('{part.as_posix()}') WHERE plate_x_mid IS NOT NULL "
            "ORDER BY game_pk, at_bat_number, pitch_number"
        ).fetchall()
    ]
    seen: dict[int, int] = {}
    drawer: list[dict[str, Any]] = []
    for row in pitches:
        taken = seen.get(row["game_pk"], 0)
        if taken < per_game:
            seen[row["game_pk"]] = taken + 1
            drawer.append({k: row[k] for k in ("game_pk", "plate_X", "plate_Z")})
    return drawer, pitches


def test_dt28_the_bridge_finds_each_pitch_from_its_own_rounded_key(con: Any) -> None:
    """The DT-28 implementation over real 2026 coordinates.

    Every drawer-shaped row finds the pitch it was built from, nothing is
    unmatched, and the rows the 0.01-ft grid genuinely collides on are reported
    as ambiguous rather than matched to the first candidate. The ambiguous
    count is checked against the same count computed in SQL.
    """
    drawer, pitches = _bridge_sample(con, RAW_DAY)
    result = jn.drawer_bridge(drawer, pitches)
    assert result.n_rows == len(drawer) > 0
    assert result.n_unmatched == 0
    assert result.n_matched + result.n_ambiguous == result.n_rows
    for position, key, hits in result.matches:
        assert hits, f"row {position} with key {key} found nothing"
    part = _day_part(jn.STATCAST_DATASET, RAW_DAY)
    collisions = {
        (int(g), float(x), float(z))
        for g, x, z in con.execute(
            f"SELECT game_pk, round(plate_x_mid, 2), round(plate_z_mid, 2) "
            f"FROM read_parquet('{part.as_posix()}') WHERE plate_x_mid IS NOT NULL "
            "GROUP BY 1, 2, 3 HAVING count(*) > 1"
        ).fetchall()
    }
    expected = sum(1 for _position, key, _hits in result.matches if key in collisions)
    assert result.n_ambiguous == expected


def test_dt28_a_within_game_near_tie_stays_two_keys() -> None:
    """The R2 fixture's near tie, on the bridge itself. No data needed."""
    pitches = [
        {"game_pk": 999001, "plate_X": 0.1149, "plate_Z": 2.05, "id": "a"},
        {"game_pk": 999001, "plate_X": 0.1151, "plate_Z": 2.05, "id": "b"},
    ]
    drawer = [{k: row[k] for k in ("game_pk", "plate_X", "plate_Z")} for row in pitches]
    result = jn.drawer_bridge(drawer, pitches)
    assert (result.n_matched, result.n_ambiguous, result.n_unmatched) == (2, 0, 0)
    assert jn.bridge_key(999001, 0.1149, 2.05) != jn.bridge_key(999001, 0.1151, 2.05)


def test_dt28_drawer_coordinate_bridge(con: Any) -> None:
    """DT-28 as written: 100% matched, 0 ambiguous, 0 unmatched. Needs W4.2."""
    files = _drawer_files()
    if not files:
        pytest.skip("data/raw/savant/abs_drawer is empty. W4.2 has not pulled it yet.")
    from absump.ingest.savant_drawer import load

    drawer = [row for path in files for row in load(path)]
    statcast = _sql_list(_dataset_parts(jn.STATCAST_DATASET))
    pitches = [
        {"game_pk": int(g), "plate_X": x, "plate_Z": z, "id": (int(g), int(ab), int(pn))}
        for g, ab, pn, x, z in con.execute(
            f"SELECT game_pk, at_bat_number, pitch_number, plate_x_mid, plate_z_mid "
            f"FROM read_parquet({statcast}) WHERE plate_x_mid IS NOT NULL"
        ).fetchall()
    ]
    result = jn.drawer_bridge(drawer, pitches)
    assert (result.n_ambiguous, result.n_unmatched) == (0, 0)
    assert result.match_rate == 1.0


# --------------------------------------------------------------------------
# The reports. Synthetic, no data needed.
# --------------------------------------------------------------------------


def test_report_merge_replaces_one_level_season_and_keeps_the_rest(tmp_path: Path) -> None:
    """B-3: a 2026 run leaves the 2025 rows of the same report alone."""
    path = tmp_path / "join_report.csv"
    older = [
        {
            "game_pk": 1,
            "level": "mlb",
            "season": 2025,
            "official_date": "2025-04-01",
            "n_api": 1,
            "n_csv": 1,
            "n_matched": 1,
            "n_api_only": 0,
            "n_csv_only": 0,
            "n_no_pitch_events": 0,
            "max_coord_err_ft": 0.0,
            "status": jn.STATUS_OK,
        },
    ]
    jn.write_report(path, jn.REPORT_COLUMNS, older, {("mlb", 2025)})
    newer = [
        {
            "game_pk": 2,
            "level": "mlb",
            "season": 2026,
            "official_date": "2026-04-01",
            "n_api": 2,
            "n_csv": 2,
            "n_matched": 2,
            "n_api_only": 0,
            "n_csv_only": 0,
            "n_no_pitch_events": 1,
            "max_coord_err_ft": 1e-16,
            "status": jn.STATUS_OK,
        },
    ]
    assert jn.write_report(path, jn.REPORT_COLUMNS, newer, {("mlb", 2026)}) == 2
    first = path.read_bytes()
    assert jn.write_report(path, jn.REPORT_COLUMNS, newer, {("mlb", 2026)}) == 2
    assert path.read_bytes() == first, "a re-run rewrote the report differently"
    assert b"2025-04-01" in first and b"2026-04-01" in first
    assert jn.write_report(path, jn.REPORT_COLUMNS, [], {("mlb", 2025)}) == 1
