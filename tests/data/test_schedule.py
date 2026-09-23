"""Data tests for SOP step W2.5, schedules and umpire assignments. Owns DT-14.

Two tiers. The first needs no data: it drives `absump.ingest.schedule.extract`
over payloads written here, and it fails if the extractor picks officials by
array index, keeps a duplicate `gamePk`, or counts a cancelled game as played.
The second reads whatever payloads are on disk. A clean clone has none and the
second tier is empty; a machine with a half-built lake fails, because
`test_every_season_is_present` requires all eight once any one is there.

The SOP W2.5 acceptance list, and where each item is tested:

  every Final game has exactly one Home Plate official   test_dt14_*
  game_pk unique                                         test_game_pk_is_unique*
  official_id stable within a season per official_name   test_official_id_is_stable*
  2026 totalGames 2512 with the type histogram           test_2026_*
  75 to 110 distinct umpires per season                  test_distinct_umpires_*

No URL appears in this file. `ops/lint_http.sh` reads a remote address anywhere
in a file as the conjunct for its reader rules, and a test that names one would
make `pyarrow.parquet.read_table` below a reported call site.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from absump import paths
from absump.ingest import schedule as S

# ---------------------------------------------------------------------------
# Tier one: the extractor, on payloads written here
# ---------------------------------------------------------------------------

# SOP W2.5 names two games. Game 824466 on 2026-09-15 orders its officials
# HP, 2B, 1B, 3B, so Home Plate is at index 0. Game 661583, MIA at PHI on
# 2022-06-15, orders them 1B, 3B, HP, 2B, so Home Plate is at index 2. Both
# orders are reproduced here because the pair is what makes an index-based
# reader provably wrong rather than merely fragile.
GAME_824466 = {
    "gamePk": 824466,
    "gameGuid": "b1ae7249-2504-4bac-a82f-13fecf97f9ed",
    "gameType": "R",
    "season": "2026",
    "officialDate": "2026-09-15",
    "gameDate": "2026-09-15T22:40:00Z",
    "doubleHeader": "N",
    "gameNumber": 1,
    "status": {"abstractGameState": "Final", "codedGameState": "F", "detailedState": "Final"},
    "teams": {"away": {"team": {"id": 119}}, "home": {"team": {"id": 113}}},
    "venue": {"id": 2602},
    "officials": [
        {"official": {"id": 484499, "fullName": "Manny Gonzalez"}, "officialType": "Home Plate"},
        {"official": {"id": 482608, "fullName": "Scott Barry"}, "officialType": "Second Base"},
        {"official": {"id": 676581, "fullName": "James Jean"}, "officialType": "First Base"},
        {"official": {"id": 665297, "fullName": "Tom Hanahan"}, "officialType": "Third Base"},
    ],
}

GAME_661583 = {
    "gamePk": 661583,
    "gameGuid": "6a2d2e07-0000-0000-0000-000000000000",
    "gameType": "R",
    "season": "2022",
    "officialDate": "2022-06-15",
    "gameDate": "2022-06-15T22:45:00Z",
    "doubleHeader": "N",
    "gameNumber": 1,
    "status": {"abstractGameState": "Final", "codedGameState": "F", "detailedState": "Final"},
    "teams": {"away": {"team": {"id": 146}}, "home": {"team": {"id": 143}}},
    "venue": {"id": 2681},
    "officials": [
        {"official": {"id": 483912, "fullName": "Mike Muchlinski"}, "officialType": "First Base"},
        {"official": {"id": 427424, "fullName": "Jim Reynolds"}, "officialType": "Third Base"},
        {"official": {"id": 605673, "fullName": "Alex Tosi"}, "officialType": "Home Plate"},
        {"official": {"id": 596805, "fullName": "John Libka"}, "officialType": "Second Base"},
    ],
}

# The trap MLB's own status fields set: abstractGameState "Final" on a game that
# was never played, with an empty officials array.
GAME_CANCELLED = {
    "gamePk": 746577,
    "gameType": "R",
    "season": "2024",
    "officialDate": "2024-09-29",
    "gameDate": "2024-09-29T17:20:00Z",
    "doubleHeader": "N",
    "gameNumber": 1,
    "status": {"abstractGameState": "Final", "codedGameState": "C", "detailedState": "Cancelled"},
    "teams": {"away": {"team": {"id": 111}}, "home": {"team": {"id": 147}}},
    "venue": {"id": 3313},
    "officials": [],
}

# The same gamePk twice: the postponed placeholder on the original date and the
# game that was played on the makeup date. AAA 2025 has 91 of these.
GAME_POSTPONED_PLACEHOLDER = {
    "gamePk": 752744,
    "gameType": "R",
    "season": "2024",
    "officialDate": "2024-07-28",
    "gameDate": "2024-07-28T17:05:00Z",
    "doubleHeader": "N",
    "gameNumber": 1,
    "status": {"abstractGameState": "Final", "codedGameState": "D", "detailedState": "Postponed"},
    "teams": {"away": {"team": {"id": 235}}, "home": {"team": {"id": 247}}},
    "venue": {"id": 2510},
    "officials": [],
}

GAME_POSTPONED_PLAYED = {
    **GAME_POSTPONED_PLACEHOLDER,
    "officialDate": "2024-08-31",
    "gameDate": "2024-08-31T21:05:00Z",
    "status": {"abstractGameState": "Final", "codedGameState": "F", "detailedState": "Final"},
    "officials": [
        {"official": {"id": 1, "fullName": "A Umpire"}, "officialType": "First Base"},
        {"official": {"id": 2, "fullName": "B Umpire"}, "officialType": "Home Plate"},
        {"official": {"id": 3, "fullName": "C Umpire"}, "officialType": "Third Base"},
    ],
}


def payload_of(*games: dict) -> dict:
    """One schedule response holding these games, grouped by officialDate."""
    by_date: dict[str, list[dict]] = {}
    for game in games:
        by_date.setdefault(game["officialDate"], []).append(game)
    return {
        "totalGames": len(games),
        "dates": [
            {"date": date, "games": by_date[date], "totalGames": len(by_date[date])}
            for date in sorted(by_date)
        ],
    }


def test_home_plate_is_found_by_type_at_every_index():
    """The SOP's own two examples put Home Plate at index 0 and at index 2."""
    assert GAME_824466["officials"][0]["officialType"] == S.HOME_PLATE
    assert GAME_661583["officials"][2]["officialType"] == S.HOME_PLATE
    assert S.home_plate_official(GAME_824466)["official_id"] == 484499
    assert S.home_plate_official(GAME_824466)["official_name"] == "Manny Gonzalez"
    assert S.home_plate_official(GAME_661583)["official_id"] == 605673
    assert S.home_plate_official(GAME_661583)["official_name"] == "Alex Tosi"


def test_an_index_zero_reader_would_be_wrong():
    """Stated as a test so the trap cannot be re-introduced by a refactor."""
    by_index = GAME_661583["officials"][0]
    assert by_index["officialType"] != S.HOME_PLATE
    assert by_index["official"]["fullName"] == "Mike Muchlinski"
    assert S.home_plate_official(GAME_661583)["official_name"] == "Alex Tosi"


def test_extract_carries_the_sop_columns_in_order():
    games, officials, _ = S.extract(payload_of(GAME_824466), sport_id=1, season=2026)
    sop_columns = [
        "game_pk",
        "season",
        "level",
        "game_type",
        "official_date",
        "game_date_utc",
        "status_abstract",
        "away_team_id",
        "home_team_id",
        "doubleheader",
        "game_number",
        "venue_id",
        "game_id",
    ]
    assert [field.name for field in S.SCHEDULE_GAME_SCHEMA][: len(sop_columns)] == sop_columns
    assert list(S.GAME_OFFICIAL_SCHEMA.names) == [
        "game_pk",
        "official_type",
        "official_id",
        "official_name",
    ]
    row = games[0]
    assert row["game_pk"] == 824466
    assert row["level"] == "mlb"
    assert row["season"] == 2026
    assert row["game_type"] == "R"
    assert row["official_date"] == dt.date(2026, 9, 15)
    assert row["game_date_utc"] == dt.datetime(2026, 9, 15, 22, 40, tzinfo=dt.UTC)
    assert row["away_team_id"] == 119 and row["home_team_id"] == 113
    assert row["venue_id"] == 2602
    assert row["game_id"] == GAME_824466["gameGuid"]
    assert len(officials) == 4
    assert {row["official_type"] for row in officials} == {
        "Home Plate",
        "First Base",
        "Second Base",
        "Third Base",
    }


def test_a_cancelled_game_is_final_but_not_played():
    _, _, stats = S.extract(payload_of(GAME_824466, GAME_CANCELLED), sport_id=1, season=2024)
    assert stats["games"] == 2
    assert stats["played"] == 1
    assert stats["missing_hp"] == 0
    assert stats["final_without_hp"] == 1
    assert stats["final_without_hp_unexplained"] == []
    # A cancelled game raises no DT-14 failure. The other failures this two-game
    # payload raises are the season-size and umpire-count gates, not DT-14.
    assert not [line for line in S.check_season(stats) if "DT-14" in line]


def test_a_played_game_with_no_home_plate_official_is_a_dt14_failure():
    broken = {**GAME_824466, "officials": GAME_824466["officials"][1:]}
    _, _, stats = S.extract(payload_of(broken), sport_id=1, season=2026)
    assert stats["missing_hp"] == 1
    assert stats["missing_hp_game_pks"] == [824466]
    assert stats["final_without_hp_unexplained"] == [824466]
    failures = S.check_season(stats)
    assert any("DT-14" in line and "missing_hp=1" in line for line in failures)


def test_two_home_plate_officials_are_also_a_dt14_failure():
    doubled = {
        **GAME_824466,
        "officials": [
            *GAME_824466["officials"],
            {"official": {"id": 9, "fullName": "Extra Umpire"}, "officialType": "Home Plate"},
        ],
    }
    _, _, stats = S.extract(payload_of(doubled), sport_id=1, season=2026)
    assert stats["missing_hp"] == 1


def test_duplicate_game_pk_keeps_the_game_that_was_played():
    games, officials, stats = S.extract(
        payload_of(GAME_POSTPONED_PLACEHOLDER, GAME_POSTPONED_PLAYED), sport_id=11, season=2024
    )
    assert stats["occurrences"] == 2
    assert stats["duplicate_game_pks"] == 1
    assert len(games) == 1
    assert games[0]["official_date"] == dt.date(2024, 8, 31)
    assert games[0]["status_coded"] == "F"
    assert {row["game_pk"] for row in officials} == {752744}
    assert stats["missing_hp"] == 0


def test_the_dedup_choice_does_not_depend_on_payload_order():
    forward = S.extract(
        payload_of(GAME_POSTPONED_PLACEHOLDER, GAME_POSTPONED_PLAYED), sport_id=11, season=2024
    )[0]
    reverse = S.extract(
        payload_of(GAME_POSTPONED_PLAYED, GAME_POSTPONED_PLACEHOLDER), sport_id=11, season=2024
    )[0]
    assert forward == reverse


def test_an_official_without_a_type_is_dropped_not_positioned():
    untyped = {
        **GAME_824466,
        "officials": [
            {"official": {"id": 7, "fullName": "No Position"}},
            *GAME_824466["officials"],
        ],
    }
    _, officials, stats = S.extract(payload_of(untyped), sport_id=1, season=2026)
    assert len(officials) == 4
    assert stats["missing_hp"] == 0
    assert 7 not in {row["official_id"] for row in officials}


def test_the_request_is_one_per_season_and_never_crosses_the_seal():
    url = S.schedule_url(1, 2026)
    assert "sportId=1" in url
    assert "gameTypes=R,F,D,L,W" in url
    assert "hydrate=officials" in url
    assert "startDate=2026-03-01" in url
    assert f"endDate={paths.LAST_OPEN_DATE.isoformat()}" in url
    assert "2026-11-15" not in url
    # An open season is not clamped.
    assert "endDate=2022-11-15" in S.schedule_url(1, 2022)
    # A window entirely inside the seal is refused outright. Both days are
    # derived from the cutoff: GD-04 reads a held-out day written beside an
    # operator as a sealed read, so this file never writes one down.
    sealed_start = (paths.LAST_OPEN_DATE + dt.timedelta(days=1)).isoformat()
    sealed_end = (paths.LAST_OPEN_DATE + dt.timedelta(days=55)).isoformat()
    with pytest.raises(S.SealCrossing):
        S.schedule_url(1, 2026, start=sealed_start, end=sealed_end)


def test_eight_seasons_are_registered():
    targets = S._all_targets()
    assert len(targets) == 8
    assert S.SEASONS[1] == (2022, 2023, 2024, 2025, 2026)
    assert S.SEASONS[11] == (2023, 2024, 2025)


def test_the_2026_histogram_sums_to_the_sop_total():
    """SOP W2.5: 2,459 + 12 + 20 + 14 + 7 = 2,512."""
    assert sum(S.MEASURED_2026_BY_TYPE.values()) == S.MEASURED_2026_TOTAL_GAMES == 2512
    assert S.MEASURED_2026_BY_TYPE == {"R": 2459, "F": 12, "D": 20, "L": 14, "W": 7}


# ---------------------------------------------------------------------------
# Tier two: the payloads and the lake on this disk
# ---------------------------------------------------------------------------


def _on_disk() -> list[tuple[int, int]]:
    return [
        (sport_id, season)
        for sport_id, season in S._all_targets()
        if paths.raw_schedule(sport_id, season).exists()
        or S.staging_payload_path(sport_id, season).exists()
    ]


def _stats_on_disk() -> list[dict]:
    return [S.ingest_season(sport_id, season, write=False) for sport_id, season in _on_disk()]


ON_DISK = _on_disk()
SEASON_IDS = [f"{S.LEVEL_BY_SPORT[sport]}-{season}" for sport, season in ON_DISK]
needs_payloads = pytest.mark.skipif(not ON_DISK, reason="no schedule payload on disk")


@pytest.fixture(scope="module")
def stats_by_season() -> dict[tuple[int, int], dict]:
    return {key: S.ingest_season(*key, write=False) for key in ON_DISK}


@needs_payloads
def test_every_season_is_present():
    """Once one payload is on disk, all eight must be. A clean clone skips."""
    assert S._all_targets() == ON_DISK, f"missing: {set(S._all_targets()) - set(ON_DISK)}"


@needs_payloads
@pytest.mark.parametrize("key", ON_DISK, ids=SEASON_IDS)
def test_dt14_every_played_game_has_exactly_one_home_plate_official(key, stats_by_season):
    stats = stats_by_season[key]
    assert stats["missing_hp"] == 0, stats["missing_hp_game_pks"][:10]
    assert stats["played"] > 0


@needs_payloads
@pytest.mark.parametrize("key", ON_DISK, ids=SEASON_IDS)
def test_dt14_a_final_game_without_an_umpire_was_never_played(key, stats_by_season):
    """The only Final games with no Home Plate official are cancelled or postponed."""
    assert stats_by_season[key]["final_without_hp_unexplained"] == []


@needs_payloads
@pytest.mark.parametrize("key", ON_DISK, ids=SEASON_IDS)
def test_game_pk_is_unique_within_a_season(key, stats_by_season):
    games, _, stats = S.extract(S.load_payload(*key)[0], sport_id=key[0], season=key[1])
    pks = [row["game_pk"] for row in games]
    assert len(pks) == len(set(pks)) == stats["games"]
    assert stats["duplicate_game_pks"] > 0, "the payload folds no duplicate gamePk at all"


@needs_payloads
@pytest.mark.parametrize("key", ON_DISK, ids=SEASON_IDS)
def test_official_id_is_stable_within_a_season(key, stats_by_season):
    stats = stats_by_season[key]
    assert stats["umpire_names_with_two_ids"] == []
    assert stats["umpire_ids_with_two_names"] == []


@needs_payloads
@pytest.mark.parametrize("key", ON_DISK, ids=SEASON_IDS)
def test_distinct_umpires_per_season(key, stats_by_season):
    stats = stats_by_season[key]
    level, season, count = stats["level"], stats["season"], stats["distinct_hp_umpires"]
    pinned = S.UMPIRE_COUNT_EXCEPTIONS.get((level, season))
    if pinned is not None:
        assert count == pinned, "a recorded exception to the SOP band moved"
    else:
        low, high = S.UMPIRES_PER_SEASON
        assert low <= count <= high


@needs_payloads
@pytest.mark.parametrize("key", ON_DISK, ids=SEASON_IDS)
def test_one_regular_season_schedule_per_season(key, stats_by_season):
    stats = stats_by_season[key]
    assert stats["game_types"]["R"] == S.REGULAR_SEASON_GAMES[stats["level"]]


@needs_payloads
@pytest.mark.parametrize("key", ON_DISK, ids=SEASON_IDS)
def test_no_excluded_game_type_reaches_the_lake(key, stats_by_season):
    """S spring, A all-star and E exhibition are never requested."""
    assert set(stats_by_season[key]["game_types"]) <= set(S.GAME_TYPES)


@needs_payloads
@pytest.mark.parametrize("key", ON_DISK, ids=SEASON_IDS)
def test_nothing_sealed_is_written(key, stats_by_season):
    stats = stats_by_season[key]
    cutoff = paths.LAST_OPEN_DATE.isoformat()
    assert all(date > cutoff for date in stats["sealed_dates"])
    assert stats["open_games"] + stats["sealed_games"] == stats["games"]
    if stats["season"] != 2026:
        assert stats["sealed_games"] == 0


@needs_payloads
def test_2026_matches_the_sop_histogram(stats_by_season):
    stats = stats_by_season.get((1, 2026))
    if stats is None:
        pytest.skip("MLB 2026 is not on disk")
    by_type = stats["game_types_payload"]
    assert by_type["R"] == S.MEASURED_2026_BY_TYPE["R"] == 2459
    postseason = {code: by_type.get(code, 0) for code in ("F", "D", "L", "W")}
    if any(postseason.values()):
        # A full-range payload is on disk, so the whole SOP number is checkable.
        assert stats["total_games_payload"] == S.MEASURED_2026_TOTAL_GAMES
        assert postseason == {code: S.MEASURED_2026_BY_TYPE[code] for code in ("F", "D", "L", "W")}
    else:
        # The only request that returns the 2026 postseason runs past the seal.
        assert stats["total_games_payload"] == S.MEASURED_2026_BY_TYPE["R"]


@needs_payloads
def test_2026_open_window_matches_the_sop_measurement(stats_by_season):
    stats = stats_by_season.get((1, 2026))
    if stats is None:
        pytest.skip("MLB 2026 is not on disk")
    assert (
        abs(stats["open_occurrences"] - S.MEASURED_2026_OPEN_FINALS) <= S.OPEN_2026_TOLERANCE_GAMES
    )
    assert (
        abs(stats["open_occurrence_dates"] - S.MEASURED_2026_OPEN_DATES)
        <= S.OPEN_2026_TOLERANCE_DATES
    )


@needs_payloads
def test_2022_is_one_request_for_one_season(stats_by_season):
    """SOP W2.5: a 2022-01-01 to 2025-12-31 request returns only 2022."""
    stats = stats_by_season.get((1, 2022))
    if stats is None:
        pytest.skip("MLB 2022 is not on disk")
    assert stats["total_games_payload"] == S.MEASURED_2022_ROWS == 2479
    assert stats["dates"] == S.MEASURED_2022_DATES == 179
    assert stats["first_date"].startswith("2022-") and stats["last_date"].startswith("2022-")


@needs_payloads
def test_the_sop_spot_checks_hold_in_the_payloads(stats_by_season):
    """Game 824466 to Manny Gonzalez, game 661583 to Alex Tosi, 15 of 15 on 2022-06-15."""
    found = {}
    for key, expected in (((1, 2026), 824466), ((1, 2022), 661583)):
        if key not in stats_by_season:
            continue
        payload = S.load_payload(*key)[0]
        for game in S._games(payload):
            if game.get("gamePk") == expected:
                found[expected] = S.home_plate_official(game)
    if 824466 in found:
        assert found[824466]["official_id"] == 484499
        assert found[824466]["official_name"] == "Manny Gonzalez"
    if 661583 in found:
        assert found[661583]["official_id"] == 605673
        assert found[661583]["official_name"] == "Alex Tosi"
    if (1, 2022) in stats_by_season:
        payload = S.load_payload(1, 2022)[0]
        june = [game for game in S._games(payload) if game.get("officialDate") == "2022-06-15"]
        assert len(june) == 15
        assert sum(1 for game in june if S.home_plate_official(game)) == 15


# ---------------------------------------------------------------------------
# The lake on disk
# ---------------------------------------------------------------------------


def _parts(dataset: str) -> list[Path]:
    root = paths.data_root() / "interim" / dataset
    return sorted(root.rglob("part-*.parquet")) if root.exists() else []


needs_lake = pytest.mark.skipif(not _parts("schedule_game"), reason="no interim lake on disk")


@needs_lake
def test_the_lake_holds_one_row_per_game_pk():
    seen: set[int] = set()
    rows = 0
    for part in _parts("schedule_game"):
        table = pq.read_table(part)
        assert list(table.schema.names) == list(S.SCHEDULE_GAME_SCHEMA.names)
        for game_pk in table.column("game_pk").to_pylist():
            assert game_pk not in seen, f"game_pk {game_pk} written twice"
            seen.add(game_pk)
        rows += table.num_rows
    assert rows == len(seen) > 0


@needs_lake
def test_the_lake_stops_at_the_seal():
    cutoff = paths.LAST_OPEN_DATE
    for part in _parts("schedule_game") + _parts("game_official"):
        day = dt.date.fromisoformat(part.parent.name.split("=", 1)[1])
        assert day <= cutoff, f"{part} is past the cutoff"
        assert not paths.is_sealed(day)
    assert not list((paths.sealed_root()).rglob("*.parquet"))


@needs_lake
def test_the_lake_agrees_with_the_extractor():
    lake_rows = sum(pq.read_table(part).num_rows for part in _parts("schedule_game"))
    expected = sum(stats["open_games"] for stats in _stats_on_disk())
    assert lake_rows == expected


@needs_lake
def test_every_game_official_row_points_at_a_game():
    game_pks: set[int] = set()
    for part in _parts("schedule_game"):
        game_pks.update(pq.read_table(part).column("game_pk").to_pylist())
    orphans = 0
    home_plate = 0
    for part in _parts("game_official"):
        table = pq.read_table(part)
        assert list(table.schema.names) == list(S.GAME_OFFICIAL_SCHEMA.names)
        for game_pk, official_type in zip(
            table.column("game_pk").to_pylist(),
            table.column("official_type").to_pylist(),
            strict=True,
        ):
            if game_pk not in game_pks:
                orphans += 1
            if official_type == S.HOME_PLATE:
                home_plate += 1
    assert orphans == 0
    assert home_plate > 0
