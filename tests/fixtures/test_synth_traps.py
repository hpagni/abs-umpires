"""W9.3. The synthetic fixtures carry all seven traps, and the generator is deterministic.

These tests validate the fixture and its ground truth against each other. They do not
import the production readers -- `absump.joinkey` and `absump.challenges` are W2's, and the
UT-01 to UT-10 tests that consume these fixtures live with them. What this file guarantees
is that when those readers arrive, the thing they are tested against is correct, complete
and reproducible.

UT-20 is here because it is the one test that touches a real response. It validates the
generator's shape against one locally cached real feed. It fails locally if MLB changes the
feed shape and stays green in CI, which never sees real data. When no pre-2026 feed is
cached it skips with a fixed reason, and a skip is recorded as a skip.
"""

from __future__ import annotations

import csv
import hashlib
import json
import pathlib

import pytest
import synth_feed

FIXTURES = pathlib.Path(__file__).resolve().parent
REPO_ROOT = FIXTURES.parents[1]
GENERATED = FIXTURES / "generated"
EXPECTED = FIXTURES / "expected"


def _json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def feed():
    return _json(GENERATED / "mlb_feed.json")


@pytest.fixture(scope="module")
def plays(feed):
    return feed["liveData"]["plays"]["allPlays"]


@pytest.fixture(scope="module")
def challenges():
    return _json(EXPECTED / "challenges.json")


# --- the generator itself ---------------------------------------------------


def test_generator_is_deterministic():
    first = synth_feed.generate()
    second = synth_feed.generate()
    assert first == second


def test_committed_fixtures_match_the_generator():
    for rel, text in synth_feed.generate().items():
        path = FIXTURES / rel
        assert path.exists(), f"{rel} is not committed; run synth_feed.py"
        encoding = synth_feed.STATCAST_ENCODING if path.suffix == ".csv" else "utf-8"
        with path.open(encoding=encoding, newline="") as fh:
            assert fh.read() == text, rel


def test_no_real_response_bytes_landed_in_the_fixtures():
    """Synthetic only. Every game and player id is outside any real MLB range, and no
    fixture file is large enough to be a real response."""
    assert synth_feed.GAME_PK == 999001
    assert synth_feed.AAA_GAME_PK == 999002
    for path in sorted(FIXTURES.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        assert path.stat().st_size < 256_000, path
    feed = _json(GENERATED / "mlb_feed.json")
    assert feed["gamePk"] == synth_feed.GAME_PK
    assert "Synthetic" in feed["gameData"]["teams"]["home"]["name"]


# --- the seven traps --------------------------------------------------------


def test_expected_lists_exactly_seven_traps():
    traps = _json(EXPECTED / "traps.json")
    assert traps["n_traps"] == 7
    assert [t["id"] for t in traps["traps"]] == [1, 2, 3, 4, 5, 6, 7]


def test_trap_1_automatic_ball_offsets_the_pitch_number(plays):
    action = plays[1]["playEvents"][1]
    assert action["isPitch"] is False
    assert action["details"]["eventType"] == "automatic_ball"
    assert "pitchNumber" not in action
    keys = {
        (k["at_bat_number"], k["pitch_seq"]): k for k in _json(EXPECTED / "pitch_keys.json")["keys"]
    }
    assert keys[(2, 2)]["feed_pitch_number"] == 2
    assert keys[(2, 2)]["statcast_pitch_number"] == 3


def test_trap_2_intentional_walk_is_four_events_with_pitch_number_zero(plays):
    events = plays[2]["playEvents"]
    assert len(events) == 4
    assert all(e["pitchNumber"] == 0 for e in events)
    assert all(e["details"]["call"]["code"] == "VB" for e in events)
    keys = [k for k in _json(EXPECTED / "pitch_keys.json")["keys"] if k["at_bat_number"] == 3]
    assert len({k["corrected_key"] for k in keys}) == 4
    assert len({k["naive_key"] for k in keys}) == 1


def test_trap_3_pitch_level_flag_with_the_play_level_flag_false(plays):
    play = plays[3]
    assert play["about"]["hasReview"] is False
    assert play["playEvents"][2]["details"]["hasReview"] is True


def test_trap_4_play_level_mj_without_the_word_challenged(plays):
    play = plays[4]
    assert play["about"]["hasReview"] is True
    assert play["reviewDetails"]["reviewType"] == "MJ"
    assert not any(e["details"].get("hasReview") for e in play["playEvents"])
    assert "challenge" not in play["result"]["description"].lower()


def test_trap_5_overturned_challenge_stores_the_post_challenge_call(plays):
    event = plays[5]["playEvents"][2]
    assert event["reviewDetails"]["isOverturned"] is True
    assert event["details"]["call"]["code"] == "C"


def test_trap_6_mf_replay_record_is_present(plays):
    assert plays[6]["reviewDetails"]["reviewType"] == "MF"


def test_trap_7_aaa_shaped_mj_has_no_player_key(plays):
    review = plays[7]["playEvents"][1]["reviewDetails"]
    assert review["reviewType"] == "MJ"
    assert "player" not in review


# --- ground truth -----------------------------------------------------------


def test_review_locations_union_counts_each_play_once(challenges):
    assert challenges["n_review_records"] == 5
    assert challenges["n_challenges"] == 4
    assert challenges["n_filtered_non_mj"] == 1
    overturned = next(c for c in challenges["challenges"] if c["at_bat_number"] == 6)
    assert set(overturned["review_locations"]) == {
        "about.hasReview",
        "playEvents[].details.hasReview",
        "playEvents[].reviewDetails",
    }


def test_play_level_mj_resolves_to_the_last_is_pitch(challenges, plays):
    row = next(c for c in challenges["challenges"] if c["resolved_by"] == "last_isPitch")
    assert row["at_bat_number"] == 5
    pitches = [e for e in plays[4]["playEvents"] if e["isPitch"]]
    assert row["pitch_seq"] == len(pitches)
    assert row["call_code_stored"] in synth_feed.CALLED_CODES


def test_original_call_is_the_final_call_flipped_when_overturned(challenges):
    for row in challenges["challenges"]:
        flipped = "ball" if row["call_final"] == "strike" else "strike"
        assert row["call_original"] == (flipped if row["is_overturned"] else row["call_final"])
    overturned = [c for c in challenges["challenges"] if c["is_overturned"]]
    assert len(overturned) == 1
    assert overturned[0]["call_final"] == "strike"
    assert overturned[0]["call_original"] == "ball"


def test_standing_is_evaluated_on_the_original_call(challenges):
    assert challenges["standing_is_evaluated_on"] == "call_original"
    for row in challenges["challenges"]:
        expected = "batting" if row["call_original"] == "strike" else "fielding"
        assert row["standing_side"] == expected
        assert row["challenge_team_id"] == row["standing_team_id"]


def test_mj_without_player_yields_a_null_challenger(challenges):
    row = next(c for c in challenges["challenges"] if c["at_bat_number"] == 8)
    assert row["challenger_id"] is None
    assert row["challenger_role"] == "unknown"
    roles = {c["challenger_role"] for c in challenges["challenges"]}
    assert {"batter", "catcher", "unknown"} <= roles


def test_corrected_counter_is_monotone_gap_free_and_beats_the_naive_key():
    keys = _json(EXPECTED / "pitch_keys.json")
    assert keys["n_pitch_events"] == 23
    assert keys["n_distinct_corrected_keys"] == 23
    assert keys["n_distinct_naive_keys"] == 20
    assert keys["naive_key_collisions"] == ["999001-3-0"]
    assert keys["n_offset_pitches"] == 6
    by_play: dict[int, list[int]] = {}
    for row in keys["keys"]:
        by_play.setdefault(row["at_bat_number"], []).append(row["pitch_seq"])
    for at_bat, seqs in by_play.items():
        assert seqs == list(range(1, len(seqs) + 1)), at_bat


# --- the Statcast CSV -------------------------------------------------------


def test_statcast_csv_is_119_columns_read_utf_8_sig():
    path = GENERATED / "statcast.csv"
    with path.open(encoding=synth_feed.STATCAST_ENCODING, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows[0]) == 119
    assert all(len(r) == 119 for r in rows)
    assert len(rows) == 24
    assert next(iter(rows[0])) == "pitch_type"


def test_statcast_csv_carries_the_bom_that_ut_14_exists_for():
    raw = (GENERATED / "statcast.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    naive = raw.decode("utf-8").splitlines()[0].split(",")[0]
    assert naive != '"pitch_type"'


def test_statcast_header_sha256_matches_the_expected_fixture():
    expected = _json(EXPECTED / "statcast_header.json")
    assert expected["n_columns"] == 119
    assert expected["columns"] == synth_feed.STATCAST_COLUMNS
    assert expected["header_sha256"] == synth_feed.header_sha256(synth_feed.STATCAST_COLUMNS)
    with (GENERATED / "statcast.csv").open(encoding=synth_feed.STATCAST_ENCODING) as fh:
        line = fh.readline().rstrip("\r\n")
    assert hashlib.sha256(line.encode("utf-8")).hexdigest() == expected["header_sha256"]


def test_untracked_rows_are_blank_not_zero():
    """The data contract's trap: automatic_ball and intent_ball rows carry blank sz_top,
    sz_bot, plate_x and pitch_type. Coercing them to numbers is the bug."""
    with (GENERATED / "statcast.csv").open(encoding=synth_feed.STATCAST_ENCODING, newline="") as fh:
        rows = list(csv.DictReader(fh))
    untracked = [r for r in rows if r["description"] in ("automatic_ball", "intent_ball")]
    assert len(untracked) == 5
    for row in untracked:
        for column in ("sz_top", "sz_bot", "plate_x", "plate_z", "pitch_type"):
            assert row[column] == ""


def test_zone_height_identity_holds_on_every_tracked_row():
    """UT-13's identity. The top edge is 53.5% of the certified height and the bottom 27%,
    so sz_top*12/0.535 and sz_bot*12/0.27 are the same number."""
    with (GENERATED / "statcast.csv").open(encoding=synth_feed.STATCAST_ENCODING, newline="") as fh:
        rows = list(csv.DictReader(fh))
    tracked = [r for r in rows if r["sz_top"] != ""]
    assert len(tracked) == 19
    for row in tracked:
        top = float(row["sz_top"]) * 12 / 0.535
        bottom = float(row["sz_bot"]) * 12 / 0.27
        assert abs(top - bottom) < 1e-6


# --- the two R2 fixtures ----------------------------------------------------


def test_aaa_feed_gives_a_three_token_allotment_with_one_audit_row():
    """D-12. The allotment is the per-game maximum of `remaining` across the play-by-play.
    The end-of-game block is not a reliable estimator, and a disagreement with it is an
    audit row rather than a correction."""
    expected = _json(EXPECTED / "aaa_allotment.json")
    assert expected["expected_allotment"] == 3
    assert expected["allotment_by_playbyplay_max"] == {"home": 3, "away": 3}
    assert expected["allotment_implied_by_end_block"] == {"home": 3, "away": 2}
    assert expected["audit_rows"] == ["away"]
    aaa = _json(GENERATED / "aaa_feed.json")
    assert aaa["gameData"]["game"]["season"] == "2024"
    assert expected["n_mj_records_without_player"] == 3


def test_drawer_bridge_matches_every_challenge_with_no_ambiguity():
    """DT-28. 100% matched, 0 ambiguous, 0 unmatched, including the within-game near-tie."""
    bridge = _json(EXPECTED / "drawer_bridge.json")
    assert bridge["join_key"] == "(game_pk, round(plate_X, 2), round(plate_Z, 2))"
    assert bridge["n_drawer_rows"] == 4
    assert bridge["n_matched"] == 4
    assert bridge["n_ambiguous"] == 0
    assert bridge["n_unmatched"] == 0
    assert bridge["match_rate"] == 1.0


def test_the_near_tie_is_a_real_near_tie_that_still_resolves():
    bridge = _json(EXPECTED / "drawer_bridge.json")
    raw = bridge["near_tie_raw_plate_x"]
    assert len(raw) == 2
    assert abs(raw[0] - raw[1]) < 0.001
    assert len(set(bridge["near_tie_rounded_plate_x"])) == 2
    assert len(bridge["near_tie_play_ids"]) == 2


def test_drawer_rows_carry_the_fields_the_drawer_returns():
    rows = _json(GENERATED / "drawer_rows.json")
    assert len(rows) == 4
    for row in rows:
        assert tuple(row) == synth_feed.DRAWER_FIELDS
        assert row["game_pk"] == synth_feed.GAME_PK


# --- the attestation --------------------------------------------------------


def test_attest_records_shape_and_hashes_and_no_content():
    attest = _json(REPO_ROOT / "quality" / "fixtures_attest.json")
    assert attest["schema"] == "fixtures_attest/1"
    assert attest["step"] == "W9.3"
    assert attest["fixture_header_sha256"] == synth_feed.header_sha256(synth_feed.STATCAST_COLUMNS)
    allowed = {
        "statcast_export_header": {
            "kind",
            "season",
            "n_files",
            "n_distinct_header_sha256",
            "header_sha256",
            "n_columns",
            "encoding",
        },
        "statsapi_schedule": {"kind", "path", "bytes", "sha256", "top_level_keys"},
    }
    assert attest["sources"], "the attestation has no sources"
    for source in attest["sources"]:
        assert set(source) == allowed[source["kind"]], source["kind"]
        if source["kind"] == "statcast_export_header":
            assert int(source["season"]) < synth_feed.ATTEST_CUTOFF_SEASON
            assert source["n_distinct_header_sha256"] == 1
            assert source["n_columns"] == 119
        else:
            assert not source["path"].endswith("2026.json")


def test_attest_agrees_with_the_local_cache_when_there_is_one():
    attest = _json(REPO_ROOT / "quality" / "fixtures_attest.json")
    headers = [s for s in attest["sources"] if s["kind"] == "statcast_export_header"]
    if not headers:
        pytest.skip("no local Statcast export cached")
    assert attest["fixture_header_matches_cache"] is True


# --- UT-20 ------------------------------------------------------------------


def _cached_pre_2026_feed() -> pathlib.Path | None:
    """One locally cached real GUMBO feed from a 2025-or-earlier season, taken from the
    staging manifest. Phase 01 may not read a 2026 datum, so a 2026 feed does not count."""
    manifest = REPO_ROOT / "data" / "staging" / "manifest.jsonl"
    if not manifest.exists():
        return None
    with manifest.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") != 200:
                continue
            path = pathlib.Path(row.get("path", ""))
            if "feed" not in str(path) or path.suffix != ".json":
                continue
            season = next((p for p in path.parts if p.isdigit() and len(p) == 4), None)
            if season is None or int(season) >= synth_feed.ATTEST_CUTOFF_SEASON:
                continue
            if path.exists():
                return path
    return None


def test_ut20_generator_shape_against_one_local_real_feed():
    """UT-20. Fails locally if MLB changes the feed shape. CI never sees real data, so CI
    stays green, which is correct."""
    real_path = _cached_pre_2026_feed()
    if real_path is None:
        print(synth_feed.UT20_DEFERRED_REASON)
        pytest.skip(synth_feed.UT20_DEFERRED_REASON)
    real = json.loads(real_path.read_text(encoding="utf-8"))
    synthetic = _json(GENERATED / "mlb_feed.json")

    def paths(node, prefix=""):
        out = set()
        if isinstance(node, dict):
            for key, value in node.items():
                out.add(f"{prefix}.{key}" if prefix else key)
                out |= paths(value, f"{prefix}.{key}" if prefix else key)
        elif isinstance(node, list) and node:
            out |= paths(node[0], f"{prefix}[]")
        return out

    missing = sorted(p for p in paths(synthetic) if p not in paths(real))
    assert not missing, (
        f"the generator emits key paths the real feed does not have: {missing}. "
        f"The feed shape changed, or the generator drifted. Real feed: {real_path}"
    )
