"""The challenge table and its reconciliation. SOP step W2.16.

UT-04 the union of the three review locations, each record counted once.
UT-05 the two `hasReview` flags are read independently and neither is a filter.
UT-06 a play-level MJ resolves to the last `isPitch` event, call code in
      {C, B, *B}.
UT-07 `call_original = call_final` XOR `is_overturned`.
UT-08 `result.description` is never text-matched.
UT-09 a record whose `reviewType` is not MJ is excluded.
UT-10 an MJ record with no `player` key yields a null `challenger_id` and the
      role `unknown`, and does not crash.

DT-08 the starting allotment per team-game, with every exception enumerated in
      `out/tables/aaa_allotment_audit.csv`.
DT-09 every play-level MJ resolves to a pitch whose call code is in
      {C, B, *B}, on the built corpus.
DT-10 no non-MJ review reaches `feed_challenge`, and the dropped types are
      counted.
DT-15 the league overturn count reconstructed from the table equals the sum of
      `usedSuccessful` over the same games.

The seven UT tests read `tests/fixtures/generated/mlb_feed.json`,
`tests/fixtures/generated/aaa_feed.json` and the two ground-truth files beside
them, all four committed, so they run from a clean clone with no 2026 datum on
disk. The four DT tests sweep what is on disk and skip when the lake is empty.

The DT tests belong in `tests/data/test_challenges.py` by the SOP layout. W2.16
may write `tests/unit/test_challenges.py` and no other test path, so they are
here and carry their own ids.
"""

from __future__ import annotations

import csv
import datetime as _dt
import glob
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from absump import paths
from absump.challenges import (
    ALLOTMENT_COLUMNS,
    ALLOTMENT_PATH,
    AT_BAT_ENDING_EVENT_TYPES,
    BALL_CODES,
    CALLED_STRIKE_CODES,
    DATASET,
    FAIL_CLAUSES,
    FEED_CHALLENGE_SCHEMA,
    MJ,
    RECONCILIATION_COLUMNS,
    RECONCILIATION_PATH,
    build_day,
    build_season,
    call_side,
    catcher_map,
    challenge_rows,
    challenger_role,
    check_season,
    feed_files,
    game_review_records,
    game_tally,
    last_pitch_event,
    load_feed,
    main,
    modal_allotment,
    official_date,
    original_call,
    reconcile_game,
    review_records,
    standing_side,
    standing_team,
    starting_allotment,
    write_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"
MLB_FEED = FIXTURE_DIR / "generated" / "mlb_feed.json"
AAA_FEED = FIXTURE_DIR / "generated" / "aaa_feed.json"
EXPECTED_CHALLENGES = FIXTURE_DIR / "expected" / "challenges.json"
EXPECTED_ALLOTMENT = FIXTURE_DIR / "expected" / "aaa_allotment.json"

MODULE_SOURCE = (REPO_ROOT / "src" / "absump" / "challenges.py").read_text(encoding="utf-8")

# The synthetic game the fixture generator writes, and its catcher.
FIXTURE_GAME_PK = 999001
FIXTURE_CATCHER_ID = 7003

# The two corpora built on this machine. Each sweep skips when its parts are
# absent, which is what a clean clone has.
CORPORA = (("mlb", 2026), ("aaa", 2024))


def _feed(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def mlb_feed() -> dict[str, Any]:
    return _feed(MLB_FEED)


@pytest.fixture
def aaa_feed() -> dict[str, Any]:
    return _feed(AAA_FEED)


@pytest.fixture
def expected_challenges() -> dict[str, Any]:
    return json.loads(EXPECTED_CHALLENGES.read_text(encoding="utf-8"))


@pytest.fixture
def expected_allotment() -> dict[str, Any]:
    return json.loads(EXPECTED_ALLOTMENT.read_text(encoding="utf-8"))


@pytest.fixture
def catchers() -> dict[tuple[int, int], int]:
    """Statcast `fielder_2` for every at-bat of the fixture game."""
    return {(FIXTURE_GAME_PK, at_bat): FIXTURE_CATCHER_ID for at_bat in range(1, 21)}


def _parts(level: str, season: int) -> list[Path]:
    root = paths.lake_path(DATASET, level, season, paths.LAST_OPEN_DATE).parents[1]
    return sorted(Path(part) for part in glob.glob(str(root / "date=*/part-*.parquet")))


def _built_rows(level: str, season: int) -> list[dict[str, Any]]:
    return [row for part in _parts(level, season) for row in pq.read_table(part).to_pylist()]


def _report_rows(path: Path, columns: tuple[str, ...], level: str, season: int) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != list(columns):
            return []
        return [
            row for row in reader if row.get("level") == level and row.get("season") == str(season)
        ]


def _play(feed: dict[str, Any], at_bat_index: int) -> dict[str, Any]:
    return next(
        item
        for item in feed["liveData"]["plays"]["allPlays"]
        if item["about"]["atBatIndex"] == at_bat_index
    )


def _reviewed_event(play: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in play["playEvents"] if "reviewDetails" in item)


# ---------------------------------------------------------------------------
# UT-04. The union of the three review locations, each record counted once.
# ---------------------------------------------------------------------------


def test_review_records_unions_the_three_locations(mlb_feed, expected_challenges):
    """UT-04. Five review objects, in play order, with their locations."""
    found = game_review_records(mlb_feed)
    projection = [
        {
            "at_bat_number": record["at_bat_number"],
            "locations": record["review_locations"],
            "review_type": record["review_type"],
        }
        for record in found
    ]
    assert projection == expected_challenges["review_records"]
    assert len(found) == expected_challenges["n_review_records"]


def test_game_review_records_counts_each_object_once(mlb_feed):
    """UT-04. One record per object, never one per flag and never two per play."""
    found = game_review_records(mlb_feed)
    keys = [(record["at_bat_index"], record["review_location"]) for record in found]
    assert len(keys) == len(set(keys))
    assert [record["review_location"] for record in found] == [
        "playEvents[].reviewDetails",
        "allPlays[].reviewDetails",
        "playEvents[].reviewDetails",
        "allPlays[].reviewDetails",
        "playEvents[].reviewDetails",
    ]


def test_review_records_reads_additional_reviews(mlb_feed):
    """UT-04. A second review on one object is its own record, counted once.

    `reviewDetails.additionalReviews[]` is the third location. Dropping it
    loses 1 record on MLB 2026 and 82 on AAA 2024, and one MLB game stops
    reconciling, so the union is not two locations plus a rounding error.
    """
    play = _play(mlb_feed, 3)
    before = len(review_records(play))
    event = _reviewed_event(play)
    event["reviewDetails"]["additionalReviews"] = [
        {"isOverturned": True, "reviewType": MJ, "challengeTeamId": 900, "inProgress": False}
    ]
    after = review_records(play)
    assert len(after) == before + 1
    extra = [item for item in after if item["review_location"].endswith("additionalReviews[]")]
    assert len(extra) == 1
    assert extra[0]["review_locations"][-1] == "reviewDetails.additionalReviews[]"
    assert extra[0]["resolved_by"] == "event"


# ---------------------------------------------------------------------------
# UT-05. The two hasReview flags are read independently.
# ---------------------------------------------------------------------------


def test_review_records_reads_both_has_review_flags_independently(mlb_feed, catchers):
    """UT-05. Neither flag is the filter, and each is recorded on its own.

    At-bat 4 carries `details.hasReview` true on the pitch while
    `about.hasReview` is false on the play, so a reader that trusts the play
    flag loses that challenge. At-bat 5 is the reverse.
    """
    by_at_bat = {record["at_bat_number"]: record for record in game_review_records(mlb_feed)}
    pitch_level = by_at_bat[4]
    assert "about.hasReview" not in pitch_level["review_locations"]
    assert "playEvents[].details.hasReview" in pitch_level["review_locations"]
    play_level = by_at_bat[5]
    assert "about.hasReview" in play_level["review_locations"]
    assert "playEvents[].details.hasReview" not in play_level["review_locations"]
    assert {4, 5} <= {row["at_bat_number"] for row in challenge_rows(mlb_feed, catchers)}


def test_challenge_rows_survive_both_flags_being_false(mlb_feed, catchers):
    """UT-05. The flags are recorded, never selected on."""
    for play in mlb_feed["liveData"]["plays"]["allPlays"]:
        play["about"]["hasReview"] = False
        for event in play["playEvents"]:
            if isinstance(event.get("details"), dict):
                event["details"]["hasReview"] = False
    rows = challenge_rows(mlb_feed, catchers)
    assert len(rows) == 4
    for row in rows:
        assert "hasReview" not in row["review_locations"]


# ---------------------------------------------------------------------------
# UT-06. A play-level MJ resolves to the last isPitch event.
# ---------------------------------------------------------------------------


def test_last_pitch_event_picks_the_last_is_pitch(mlb_feed):
    """UT-06. The rule is the last `isPitch == true` event, by event index."""
    plays = {
        play["about"]["atBatIndex"]: play for play in mlb_feed["liveData"]["plays"]["allPlays"]
    }
    resolved = last_pitch_event(plays[4])
    assert resolved["playId"] == "00000000-0000-4000-8000-999001004003"
    assert resolved["details"]["call"]["code"] == "C"
    assert last_pitch_event({"about": {"atBatIndex": 0}, "playEvents": []}) is None
    action_only = {
        "about": {"atBatIndex": 0},
        "playEvents": [{"index": 0, "type": "action", "isPitch": False}],
    }
    assert last_pitch_event(action_only) is None


def test_challenge_rows_resolve_play_level_to_the_last_pitch(mlb_feed, catchers):
    """UT-06. The resolved pitch carries a call code in {C, B, *B}."""
    rows = {row["at_bat_number"]: row for row in challenge_rows(mlb_feed, catchers)}
    play_level = rows[5]
    assert play_level["resolved_by"] == "last_isPitch"
    assert play_level["pitch_slot"] == 3
    assert play_level["play_id"] == "00000000-0000-4000-8000-999001004003"
    assert play_level["call_code_stored"] in CALLED_STRIKE_CODES | BALL_CODES
    assert rows[4]["resolved_by"] == "event"


# ---------------------------------------------------------------------------
# UT-07. call_original = call_final XOR is_overturned.
# ---------------------------------------------------------------------------


def test_original_call_is_the_final_call_xor_overturned():
    """UT-07. The reconstruction, stated as a table."""
    assert original_call("strike", False) == "strike"
    assert original_call("ball", False) == "ball"
    assert original_call("strike", True) == "ball"
    assert original_call("ball", True) == "strike"
    assert original_call(None, True) is None
    assert original_call(None, False) is None
    assert original_call("strike", None) == "strike"


def test_call_side_maps_only_the_three_called_codes():
    """UT-07. C is a strike, B and *B are balls, everything else is null."""
    assert call_side("C") == "strike"
    assert call_side("B") == "ball"
    assert call_side("*B") == "ball"
    for code in ("S", "F", "X", "D", "VB", "", None):
        assert call_side(code) is None


def test_challenge_rows_emit_three_separate_call_columns(mlb_feed, catchers, expected_challenges):
    """UT-07. `call_original`, `call_final` and `is_overturned` are three columns.

    At-bat 6 is the decisive one: the feed stores C, the post-challenge call,
    and the challenge was overturned, so the umpire called a ball. A model that
    reads `call_final` as the umpire's call scores that overturn as correct.
    """
    for name in ("call_original", "call_final", "is_overturned"):
        assert name in FEED_CHALLENGE_SCHEMA.names
    rows = {row["at_bat_number"]: row for row in challenge_rows(mlb_feed, catchers)}
    overturned = rows[6]
    assert overturned["call_code_stored"] == "C"
    assert overturned["call_final"] == "strike"
    assert overturned["is_overturned"] is True
    assert overturned["call_original"] == "ball"
    for expected in expected_challenges["challenges"]:
        row = rows[expected["at_bat_number"]]
        assert row["call_final"] == expected["call_final"]
        assert row["call_original"] == expected["call_original"]
        assert row["is_overturned"] == expected["is_overturned"]


def test_standing_side_reads_the_original_call():
    """UT-07. Only the batting team may challenge a called strike."""
    assert standing_side("strike") == "batting"
    assert standing_side("ball") == "fielding"
    assert standing_side(None) is None


def test_standing_team_names_one_team_per_half_inning():
    """UT-07. The standing rule, resolved to a team id."""
    assert standing_team("strike", True, 901, 900) == 901
    assert standing_team("ball", True, 901, 900) == 900
    assert standing_team("strike", False, 901, 900) == 900
    assert standing_team("ball", False, 901, 900) == 901
    assert standing_team(None, True, 901, 900) is None
    assert standing_team("strike", None, 901, 900) is None


def test_challenge_rows_standing_agrees_with_challenge_team_id(mlb_feed, catchers):
    """UT-07. The reconstruction is checked against a fact the feed states apart.

    The standing implied by `call_original` names one team and that team is
    `challengeTeamId` on all four fixture challenges. The same rule read on
    `call_final` names the wrong team on the overturned one.
    """
    rows = challenge_rows(mlb_feed, catchers)
    assert all(row["standing_team_id"] == row["challenge_team_id"] for row in rows)
    overturned = [row for row in rows if row["is_overturned"]]
    assert overturned
    for row in overturned:
        naive = standing_team(row["call_final"], row["is_top_inning"], 901, 900)
        assert naive != row["challenge_team_id"]


# ---------------------------------------------------------------------------
# UT-08. result.description is never text-matched.
# ---------------------------------------------------------------------------

#: Three real overturned descriptions. None of them carries a marker, which is
#: why a text match on the description loses the challenge.
DECOY_DESCRIPTIONS = (
    "Juan Brito walks.",
    "Everson Pereira called out on strikes.",
    "Luke Ritter walks.",
)


def test_challenge_rows_ignore_result_description(mlb_feed, catchers):
    """UT-08. Rewriting every description changes no row and drops no record."""
    before = challenge_rows(mlb_feed, catchers)
    for index, play in enumerate(mlb_feed["liveData"]["plays"]["allPlays"]):
        play["result"]["description"] = DECOY_DESCRIPTIONS[index % len(DECOY_DESCRIPTIONS)]
    after = challenge_rows(mlb_feed, catchers)
    assert after == before
    assert len(after) == 4


def _code_strings(source: str) -> set[str]:
    """Every string literal in a module that is not a docstring."""
    import ast

    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_challenge_rows_carry_no_description_column(mlb_feed, catchers):
    """UT-08. The description is not a column and the module never reads it.

    The assertion is on the module's own string literals, with docstrings and
    comments excluded: no code path in `absump.challenges` names
    `description`, so none of them can match on one.
    """
    assert "result_description" not in FEED_CHALLENGE_SCHEMA.names
    assert "description" not in FEED_CHALLENGE_SCHEMA.names
    literals = _code_strings(MODULE_SOURCE)
    assert "description" not in literals
    assert not any("challenged" in literal for literal in literals)
    rows = challenge_rows(mlb_feed, catchers)
    assert all("description" not in key for row in rows for key in row)


# ---------------------------------------------------------------------------
# UT-09. A review that is not MJ is excluded.
# ---------------------------------------------------------------------------


def test_challenge_rows_exclude_non_mj_reviews(mlb_feed, catchers, expected_challenges):
    """UT-09. The MF record at at-bat 7 is seen, counted and dropped."""
    records = game_review_records(mlb_feed)
    assert (
        sum(1 for record in records if record["review_type"] != MJ)
        == (expected_challenges["n_filtered_non_mj"])
    )
    rows = challenge_rows(mlb_feed, catchers)
    assert len(rows) == expected_challenges["n_challenges"]
    assert {row["review_type"] for row in rows} == {MJ}
    assert 7 not in {row["at_bat_number"] for row in rows}


def test_challenge_rows_exclude_every_non_mj_type(mlb_feed, catchers):
    """UT-09. The filter is on the value MJ, not on a prefix or a substring."""
    play = _play(mlb_feed, 3)
    event = _reviewed_event(play)
    for review_type in ("MA", "MF", "NH", "MI", "mj", "MJX", ""):
        event["reviewDetails"]["reviewType"] = review_type
        assert len(challenge_rows(mlb_feed, catchers)) == 3
    event["reviewDetails"]["reviewType"] = MJ
    assert len(challenge_rows(mlb_feed, catchers)) == 4


# ---------------------------------------------------------------------------
# UT-10. An MJ record with no player key.
# ---------------------------------------------------------------------------


def test_challenge_rows_handle_an_mj_record_with_no_player(mlb_feed, catchers):
    """UT-10. Null challenger id, role `unknown`, no crash."""
    rows = {row["at_bat_number"]: row for row in challenge_rows(mlb_feed, catchers)}
    no_player = rows[8]
    assert no_player["challenger_id"] is None
    assert no_player["challenger_role"] == "unknown"


def test_challenger_role_resolves_the_three_people():
    """UT-10. Batter, pitcher and Statcast `fielder_2`, in that order."""
    assert challenger_role(6004, 6004, 5001, 7003) == "batter"
    assert challenger_role(5001, 6004, 5001, 7003) == "pitcher"
    assert challenger_role(7003, 6004, 5001, 7003) == "catcher"
    assert challenger_role(1234, 6004, 5001, 7003) == "other"
    assert challenger_role(7003, 6004, 5001, None) == "other"
    assert challenger_role(None, 6004, 5001, 7003) == "unknown"


def test_challenge_rows_on_the_aaa_shape_without_player(aaa_feed, expected_allotment):
    """UT-10. Every AAA MJ record lacks `player`, and the AAA arm is team level."""
    rows = challenge_rows(aaa_feed)
    assert len(rows) == expected_allotment["n_mj_records_without_player"]
    assert all(row["challenger_id"] is None for row in rows)
    assert all(row["challenger_role"] == "unknown" for row in rows)
    assert all(row["challenge_team_id"] is not None for row in rows)


# ---------------------------------------------------------------------------
# The rest of the public surface.
# ---------------------------------------------------------------------------


def test_game_tally_reads_the_abs_challenges_block(mlb_feed, aaa_feed):
    """`n_tally` is the sum of usedSuccessful and usedFailed over both sides."""
    absent = game_tally(mlb_feed)
    assert absent["has_block"] is False
    assert absent["n_tally"] is None
    present = game_tally(aaa_feed)
    assert present["has_block"] is True
    assert present["home_used_failed"] == 2
    assert present["away_used_failed"] == 0
    assert present["n_tally"] == 2


def test_reconcile_game_counts_both_locations_and_the_delta():
    """The reconciliation row: both counts, the delta and a status."""
    feed = {
        "gameData": {
            "game": {"pk": 1},
            "absChallenges": {
                "away": {"usedSuccessful": 1, "usedFailed": 1, "remaining": 0},
                "home": {"usedSuccessful": 0, "usedFailed": 1, "remaining": 1},
            },
        }
    }
    rows = [
        {"review_location": "playEvents[].reviewDetails"},
        {"review_location": "playEvents[].reviewDetails"},
        {"review_location": "allPlays[].reviewDetails"},
    ]
    ok = reconcile_game(feed, rows)
    assert (ok["n_pitch_level"], ok["n_play_level"], ok["n_additional"]) == (2, 1, 0)
    assert ok["n_challenges"] == 3
    assert ok["n_tally"] == 3
    assert ok["delta"] == 0
    assert ok["status"] == "ok"
    short = reconcile_game(feed, rows[:1])
    assert short["delta"] == -2
    assert short["status"] == "delta"
    no_block = reconcile_game({"gameData": {"game": {"pk": 1}}}, rows)
    assert no_block["status"] == "no_abs_block"
    assert no_block["delta"] is None


def test_starting_allotment_reports_both_estimators(aaa_feed, expected_allotment):
    """DT-08 at the unit level: the play-by-play maximum and the end block."""
    found = starting_allotment(aaa_feed)
    by_playbyplay = {side: found[side]["allotment_playbyplay_max"] for side in ("home", "away")}
    by_end_block = {side: found[side]["allotment_end_block"] for side in ("home", "away")}
    assert by_playbyplay == expected_allotment["allotment_by_playbyplay_max"]
    assert by_end_block == expected_allotment["allotment_implied_by_end_block"]
    assert found["away"]["allotment"] == expected_allotment["expected_allotment"]
    disagreeing = [
        side
        for side in ("away", "home")
        if found[side]["allotment_playbyplay_max"] != found[side]["allotment_end_block"]
    ]
    assert disagreeing == expected_allotment["audit_rows"]


def test_modal_allotment_picks_the_most_common_value():
    """The season mode, with the lower value winning a tie."""
    assert modal_allotment([{"allotment": 3}, {"allotment": 3}, {"allotment": 4}]) == 3
    assert modal_allotment([{"allotment": 2}, {"allotment": 3}]) == 2
    assert modal_allotment([{"allotment": None}]) is None
    assert modal_allotment([]) is None


def test_catcher_map_is_empty_without_a_statcast_part():
    """With no part on disk the role falls back to `other`, never a guess."""
    assert catcher_map("mlb", 1990, _dt.date(1990, 4, 1)) == {}


def test_feed_files_is_empty_for_a_season_with_no_feed():
    """The lake first, the staging cache second, an empty mapping otherwise."""
    assert feed_files(1, 1990) == {}


def test_load_feed_reads_plain_and_compressed_bytes(tmp_path, mlb_feed):
    """The lake stores zstd, the staging cache stores plain JSON."""
    import zstandard

    plain = tmp_path / "gamepk=999001.json"
    plain.write_text(json.dumps(mlb_feed), encoding="utf-8")
    assert load_feed(plain)["gameData"]["game"]["pk"] == FIXTURE_GAME_PK
    packed = tmp_path / "gamepk=999001.json.zst"
    packed.write_bytes(zstandard.ZstdCompressor().compress(json.dumps(mlb_feed).encode()))
    assert load_feed(packed)["gameData"]["game"]["pk"] == FIXTURE_GAME_PK


def test_official_date_reads_the_feeds_own_date(mlb_feed):
    """officialDate, never gameDate and never the file name."""
    assert official_date(mlb_feed) == _dt.date(2025, 6, 15)


def test_build_day_extracts_one_day_without_writing(tmp_path, mlb_feed):
    """One officialDate is one part and one unit of idempotence."""
    stored = tmp_path / "gamepk=999001.json"
    stored.write_text(json.dumps(mlb_feed), encoding="utf-8")
    stats = build_day(1, 2025, _dt.date(2025, 6, 15), [stored], write=False)
    assert stats["games"] == 1
    assert stats["rows"] == 4
    assert stats["written"] == 0
    assert stats["misfiled"] == 0
    assert stats["unreadable"] == []
    assert stats["review_types"] == {MJ: 4, "MF": 1}
    assert len(stats["reconciliation"]) == 1
    assert len(stats["allotment"]) == 2


def test_build_season_reports_zero_for_a_season_with_no_feed():
    """A clean clone builds nothing and says so."""
    totals = build_season("mlb", 1990, procs=1, write=False)
    assert totals["dates"] == 0
    assert totals["games"] == 0
    assert totals["rows"] == 0
    assert totals["games_not_reconciling"] == 0
    assert totals["source"] == "none"


def test_check_season_passes_with_no_part_on_disk():
    """The check reports zero parts and no breach on a machine with no data."""
    report = check_season("mlb", 1990)
    assert report["detail"]["parts"] == 0
    assert all(report["counts"][name] == 0 for name in FAIL_CLAUSES)


def test_write_report_replaces_its_scope_and_keeps_the_rest(tmp_path):
    """A rebuild of one level-season never drops another one's rows."""
    path = tmp_path / "report.csv"
    columns = ("game_pk", "level", "season", "official_date", "status")
    write_report(
        path,
        columns,
        [
            {
                "game_pk": 1,
                "level": "mlb",
                "season": 2026,
                "official_date": "2026-04-01",
                "status": "ok",
            }
        ],
        {("mlb", 2026)},
    )
    write_report(
        path,
        columns,
        [
            {
                "game_pk": 2,
                "level": "aaa",
                "season": 2024,
                "official_date": "2024-04-01",
                "status": "ok",
            }
        ],
        {("aaa", 2024)},
    )
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["game_pk"] for row in rows] == ["2", "1"]
    total = write_report(
        path,
        columns,
        [
            {
                "game_pk": 3,
                "level": "mlb",
                "season": 2026,
                "official_date": "2026-04-02",
                "status": "ok",
            }
        ],
        {("mlb", 2026)},
    )
    assert total == 2
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["game_pk"] for row in rows] == ["2", "3"]


def test_main_checks_a_season_with_no_data_and_returns_zero():
    """The command line, in check mode, on a season this machine has not pulled."""
    assert main(["--check", "--level", "mlb", "--season", "1990"]) == 0


# ---------------------------------------------------------------------------
# The four data tests. Each sweeps what is on disk and skips when it is absent.
# ---------------------------------------------------------------------------

#: The starting allotment the SOP records per level. MLB 2026 is two challenges
#: per team. AAA 2024 is three, which is D-12 reversing the earlier 4x4 read.
EXPECTED_MODAL_ALLOTMENT = {"mlb": 2, "aaa": 3}


@pytest.mark.parametrize(("level", "season"), CORPORA)
def test_dt08_starting_allotment_with_every_exception_enumerated(level, season):
    """DT-08. The modal allotment per season, exceptions in the audit table.

    MLB 2026: 4,640 of 4,676 team-games imply 2 and 36 imply 3. All 36 are
    extra-inning games with usedFailed 3 and remaining 0, which is the extra
    token an extra-inning game grants. Restricted to nine innings or fewer the
    allotment is 2 on 4,266 of 4,266 team-games. AAA 2024: the mode is 3 over
    712 team-games with a block, with 21 exceptions.
    """
    if not _parts(level, season):
        pytest.skip(f"no {DATASET} part for {level} {season}")
    audit = _report_rows(ALLOTMENT_PATH, ALLOTMENT_COLUMNS, level, season)
    games = _report_rows(RECONCILIATION_PATH, RECONCILIATION_COLUMNS, level, season)
    with_block = [row for row in games if row["status"] != "no_abs_block"]
    assert with_block, "the reconciliation report holds no game with an absChallenges block"
    modes = {row["modal_allotment"] for row in audit}
    assert modes == {str(EXPECTED_MODAL_ALLOTMENT[level])}
    for row in audit:
        assert row["reason"]
        assert row["allotment"] != row["modal_allotment"] or "disagrees" in row["reason"]
        assert row["side"] in ("away", "home")
    # The exceptions are a small, enumerated minority of the team-games.
    assert len(audit) < len(with_block) * 2 * 0.05
    if level == "mlb":
        assert all(int(row["max_inning"]) > 9 for row in audit)
        assert all(row["reason"] == "above_modal_allotment" for row in audit)
        assert all(int(row["allotment"]) == 3 for row in audit)


@pytest.mark.parametrize(("level", "season"), CORPORA)
def test_dt09_play_level_mj_resolves_to_the_last_pitch(level, season):
    """DT-09. 100%: every play-level record lands on a C, B or *B pitch."""
    rows = _built_rows(level, season)
    if not rows:
        pytest.skip(f"no {DATASET} part for {level} {season}")
    play_level = [row for row in rows if row["resolved_by"] == "last_isPitch"]
    assert play_level
    unresolved = [row for row in play_level if row["pitch_slot"] is None]
    assert unresolved == []
    codes = {row["call_code_stored"] for row in play_level}
    assert codes <= CALLED_STRIKE_CODES | BALL_CODES, codes
    assert all(row["call_final"] in ("strike", "ball") for row in play_level)
    ending = {row["result_event_type"] for row in play_level}
    assert ending <= AT_BAT_ENDING_EVENT_TYPES, ending


@pytest.mark.parametrize(("level", "season"), CORPORA)
def test_dt10_no_non_mj_review_reaches_the_table(level, season):
    """DT-10. 0 leaks, and the dropped types are counted rather than ignored."""
    rows = _built_rows(level, season)
    if not rows:
        pytest.skip(f"no {DATASET} part for {level} {season}")
    assert {row["review_type"] for row in rows} == {MJ}
    locations = {row["review_location"] for row in rows}
    assert locations <= {
        "playEvents[].reviewDetails",
        "allPlays[].reviewDetails",
        "reviewDetails.additionalReviews[]",
    }
    games = _report_rows(RECONCILIATION_PATH, RECONCILIATION_COLUMNS, level, season)
    counted = sum(int(row["n_challenges"]) for row in games)
    assert counted == len(rows)


@pytest.mark.parametrize(("level", "season"), CORPORA)
def test_dt15_overturn_count_equals_used_successful(level, season):
    """DT-15. 0 record difference between the table and the gameData tallies.

    A successful challenge is an overturned call, so the overturn count
    reconstructed from `is_overturned` has to equal the sum of `usedSuccessful`
    over the same games. MLB 2026: 5,490 against 5,490. AAA 2024: 994 against
    994. The games with no `absChallenges` block are excluded from both sides,
    and they carry no MJ record on either corpus.
    """
    rows = _built_rows(level, season)
    if not rows:
        pytest.skip(f"no {DATASET} part for {level} {season}")
    games = _report_rows(RECONCILIATION_PATH, RECONCILIATION_COLUMNS, level, season)
    assert games
    with_block = {int(row["game_pk"]) for row in games if row["status"] != "no_abs_block"}
    assert [row for row in games if row["status"] == "delta"] == []
    used_successful = sum(
        int(row["away_used_successful"] or 0) + int(row["home_used_successful"] or 0)
        for row in games
        if int(row["game_pk"]) in with_block
    )
    overturned = sum(1 for row in rows if row["is_overturned"] and row["game_pk"] in with_block)
    assert overturned == used_successful
    assert all(row["game_pk"] in with_block for row in rows)


@pytest.mark.parametrize(("level", "season"), CORPORA)
def test_check_season_finds_no_breach_on_the_built_corpus(level, season):
    """The six W2.16 clauses, re-read from what is on disk."""
    if not _parts(level, season):
        pytest.skip(f"no {DATASET} part for {level} {season}")
    report = check_season(level, season)
    breaches = {name: report["counts"][name] for name in FAIL_CLAUSES if report["counts"][name]}
    assert breaches == {}
