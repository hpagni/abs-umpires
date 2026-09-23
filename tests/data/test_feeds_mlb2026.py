"""SOP W2.6 data tests: MLB 2026 GUMBO feeds.

The three tests SOP W2.6 names by id are ``test_regime_marker``,
``test_token_start`` and ``test_feed_size_sane``. Each of those three is here
under its own name. The rest pin the traps the SOP text spells out, plus one it
does not, and the seal.

These are data tests: they read the stored lake, not a synthetic fixture. A
fixture cannot fail the way this data fails. The four Final 2026 games with no
``absChallenges`` key, the 200-byte body a 200 response can carry, the game that
was rained out in May and replayed inside the sealed window -- none of those are
things a generator would have thought to emit.

Two counts below are pinned rather than recomputed: they are what the corpus
measured on 2026-09-23, and a change in either is a real change in the data, so
it should stop the gate and be looked at rather than slide through. They are
tolerant in the direction the corpus grows (a resumed pull adds games) and
exact in the direction that would mean a parser regression.
"""

from __future__ import annotations

import json

import pytest

from absump import paths, seal
from absump.ingest import feeds

SPORT_MLB = 1
SPORT_AAA = 11
SEASON = 2026

# Measured on the imported corpus, 2026-09-23 Madrid: 2,342 Final regular-season
# 2026 games with officialDate on or before 2026-09-21, which is every game the
# hard cut allows. The SOP sizes the step at 2,512 games; that figure is the
# schedule's totalGames (2,459, which counts a postponed game on both its
# original and its replayed date) plus the 53 postseason slots, and the
# postseason is sealed under section 2.4.
EXPECTED_GAMES = 2342

# The one game the schedule lists twice whose second entry falls in the sealed
# window: scheduled 2026-05-23, rained out, replayed 2026-09-22.
RESCHEDULED_INTO_SEAL = 823543

# Locators for the traps, from the SOP text and from the corpus.
GAME_WITH_BOTH_COUNTERS = 822925
GAME_WITH_PITCH_LEVEL_MJ = 824466
PITCH_LEVEL_MJ_AT_BATS = (30, 65)
GAME_WITH_NESTED_MJ = 822717


def _stored_2026_paths() -> list:
    root = paths.raw_feed(SPORT_MLB, SEASON, paths.LAST_OPEN_DATE, 1).parents[1]
    return sorted(root.glob("date=*/gamepk=*.json.zst"))


@pytest.fixture(scope="session")
def stored_paths() -> list:
    found = _stored_2026_paths()
    if not found:
        pytest.fail(
            "no stored 2026 MLB feeds. Run: uv run python -m absump.ingest.feeds "
            "--sport 1 --season 2026 --status Final --resume"
        )
    return found


@pytest.fixture(scope="session")
def corpus(stored_paths) -> list[dict]:
    """One compact record per stored game. The whole corpus is read once.

    The feeds are not held: 2,342 parsed feeds is about 2 GB of Python objects.
    Everything a test below needs is reduced here, in one pass.
    """
    records = []
    for path in stored_paths:
        body = feeds._decompress(path)
        feed = json.loads(body.decode("utf-8"))
        challenges = feeds.abs_challenges(feed)
        records.append(
            {
                "path": path,
                "bytes": len(body),
                "game_pk": int(feed["gameData"]["game"]["pk"]),
                "game_type": feeds.game_type(feed),
                "season": feeds.game_season(feed),
                "official_date": feeds.official_date(feed),
                "marker": feeds.has_abs_regime(feed),
                "ledger": feeds.token_ledger(feed),
                "totals": feeds.challenge_totals(feed),
                "n_challenges": len(challenges),
                "n_overturned": sum(1 for c in challenges if c.is_overturned),
                "final_inning": feeds.final_inning(feed),
                "review": feed["gameData"].get("review"),
            }
        )
    return records


@pytest.fixture(scope="session")
def controls() -> dict[int, dict]:
    """The three pre-ABS negative controls, read from the lake.

    Fetch them once with: uv run python -m absump.ingest.feeds --sport 1
    --season 2026 --controls. Three requests, cached, so a re-run costs zero.
    """
    out = {}
    for game_pk, (sport_id, season) in sorted(feeds.PRE_ABS_CONTROL_GAMES.items()):
        path = feeds.stored_path(sport_id, season, game_pk)
        if path is None:
            pytest.fail(
                f"pre-ABS control {game_pk} is not stored. Without it "
                "test_regime_marker asserts only the positive half, which an "
                "always-true implementation passes. Fetch it with --controls."
            )
        out[game_pk] = feeds.load_feed(path)
    return out


# ---------------------------------------------------------------------------
# The three tests SOP W2.6 names
# ---------------------------------------------------------------------------


def test_regime_marker(corpus, controls):
    """`"absChallenges" in gameData` for Final 2026 MLB games, False pre-ABS.

    The SOP states the positive half as 100%. It is 2,338 of 2,342. The four
    exceptions are neutral-site special events at parks with no ABS hardware --
    Field of Dreams, Williamsport, and two games in Mexico City -- so the
    marker is venue-conditional, not unconditional on season. The exception set
    is asserted exactly, so a fifth markerless game fails this test instead of
    widening a tolerance.
    """
    assert len(corpus) >= EXPECTED_GAMES

    markerless = {record["game_pk"] for record in corpus if not record["marker"]}
    assert markerless == set(feeds.NON_ABS_VENUE_GAME_PKS)

    with_marker = [record for record in corpus if record["marker"]]
    assert len(with_marker) == len(corpus) - len(feeds.NON_ABS_VENUE_GAME_PKS)

    for game_pk, feed in controls.items():
        assert feeds.has_abs_regime(feed) is False, game_pk
        assert feeds.REGIME_MARKER not in feed["gameData"], game_pk


def test_token_start(corpus):
    """`remaining + usedFailed == 2` for every team-game, about 4,700 of them.

    A successful challenge is retained, so the spent tokens are usedFailed and
    not usedSuccessful. The identity holds on every team-game played inside
    nine innings. It does not hold on 36 team-games, and every one of those is
    in a game that went past the ninth, where a team that has spent both tokens
    is granted a third. That exception is asserted as a rule -- allotment 3 and
    extra innings, together -- so a parser that read the wrong field would
    break it rather than hide in it.
    """
    team_games = 0
    exceptions = []
    for record in corpus:
        if not record["marker"]:
            continue
        for side, entry in record["ledger"].items():
            team_games += 1
            allotment = entry["remaining"] + entry["usedFailed"]
            if allotment != feeds.TOKEN_ALLOTMENT:
                exceptions.append((record["game_pk"], side, allotment, record["final_inning"]))

    assert team_games >= 4_600
    assert team_games <= 4_800

    for game_pk, side, allotment, inning in exceptions:
        assert allotment == feeds.EXTRA_INNING_ALLOTMENT, (game_pk, side, allotment)
        assert inning > feeds.REGULATION_INNINGS, (game_pk, side, inning)

    conforming = team_games - len(exceptions)
    assert conforming / team_games > 0.99


def test_feed_size_sane(corpus):
    """Every stored file decompresses to between 0.3 and 3.0 MB.

    The lower bound is the point of the test: a "game not found" body is about
    200 bytes and statsapi serves it with HTTP 200, so size is the only signal
    that separates it from a real feed.
    """
    for record in corpus:
        assert feeds.MIN_FEED_BYTES <= record["bytes"] <= feeds.MAX_FEED_BYTES, record["path"]

    sizes = [record["bytes"] for record in corpus]
    mean_mb = sum(sizes) / len(sizes) / 1e6
    # SOP W2.6 measures the mean at 0.779 MB. Anything near it is the same
    # population; a corpus of short bodies would land an order of magnitude low.
    assert 0.5 < mean_mb < 1.2
    assert feeds.body_is_sane(b"x" * 200) is False


# ---------------------------------------------------------------------------
# The traps
# ---------------------------------------------------------------------------


def test_regime_marker_is_key_presence_not_a_field_read(controls):
    """Reading inside `absChallenges` first raises KeyError on a pre-ABS game.

    This is the first trap SOP W2.6 names. It is asserted rather than described
    so that a future edit to `has_abs_regime` that reaches for `hasChallenges`
    fails here.
    """
    for game_pk, feed in controls.items():
        with pytest.raises(KeyError):
            assert feed["gameData"][feeds.REGIME_MARKER]["hasChallenges"] is not None
        assert feeds.has_abs_regime(feed) is False, game_pk


def test_review_is_the_replay_counter_not_the_abs_counter(corpus, controls):
    """`gameData.review` is a different object and must never stand in.

    Game 822925 is the SOP's own example: `absChallenges` records 2 ABS
    challenges, `review` records 2 manager replay challenges, and the two
    reconcile independently. The controls close the other half: every pre-ABS
    game carries `review` and none carries `absChallenges`, so a marker read
    from `review` would call 2023 and 2025 ABS seasons.
    """
    record = next(r for r in corpus if r["game_pk"] == GAME_WITH_BOTH_COUNTERS)
    assert record["review"] == {
        "hasChallenges": True,
        "away": {"used": 0, "remaining": 1},
        "home": {"used": 2, "remaining": 1},
    }
    assert record["totals"]["used"] == 2
    assert record["ledger"] == {
        "away": {"usedSuccessful": 1, "usedFailed": 0, "remaining": 2},
        "home": {"usedSuccessful": 0, "usedFailed": 1, "remaining": 1},
    }
    assert "usedFailed" not in record["review"]["away"]

    for feed in controls.values():
        assert "review" in feed["gameData"]
        assert feeds.REGIME_MARKER not in feed["gameData"]


def test_review_type_is_filtered_to_mj(corpus, stored_paths):
    """Only `reviewType == "MJ"` is a challenge; every other code is replay.

    The SOP names MF, MA, MC and NH. The corpus carries thirty more, which is
    why the filter keeps MJ rather than dropping a list of known replay codes.
    The test asserts both halves: the named replay codes are present in the
    data, and none of them is ever counted.
    """
    seen = set()
    counted = set()
    for path in stored_paths[:400]:
        feed = feeds.load_feed(path)
        for play in feed["liveData"]["plays"]["allPlays"]:
            for event in play.get("playEvents", ()):
                for review in feeds.iter_review_details(event.get("reviewDetails")):
                    seen.add(review.get("reviewType"))
            for review in feeds.iter_review_details(play.get("reviewDetails")):
                seen.add(review.get("reviewType"))
        counted.update(c.level for c in feeds.abs_challenges(feed))

    assert feeds.ABS_REVIEW_TYPE in seen
    assert set(feeds.REPLAY_REVIEW_TYPES) <= seen
    assert len(seen - {feeds.ABS_REVIEW_TYPE}) > len(feeds.REPLAY_REVIEW_TYPES)
    assert counted <= {"pitch", "play"}

    # A synthetic record with a replay code must not be counted.
    replay_only = {
        "gameData": {"game": {"pk": 1}},
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "about": {"atBatIndex": 0, "inning": 1, "hasReview": True},
                        "playEvents": [
                            {"details": {"hasReview": True}, "reviewDetails": {"reviewType": code}}
                        ],
                        "reviewDetails": {"reviewType": code},
                    }
                    for code in feeds.REPLAY_REVIEW_TYPES
                ]
            }
        },
    }
    assert feeds.abs_challenges(replay_only) == []


def test_both_has_review_flags_are_needed(corpus):
    """`about.hasReview` is False on a play carrying a pitch-level ABS review.

    Verified by the SOP on at-bats 30 and 65 of game 824466 and re-verified
    here. Counting plays by `about.hasReview` alone finds 1 of that game's 3
    challenges; counting pitch events alone finds 2. Either alone undercounts.
    """
    path = feeds.stored_path(SPORT_MLB, SEASON, GAME_WITH_PITCH_LEVEL_MJ)
    feed = feeds.load_feed(path)
    plays = {p["about"]["atBatIndex"]: p for p in feed["liveData"]["plays"]["allPlays"]}

    for at_bat in PITCH_LEVEL_MJ_AT_BATS:
        play = plays[at_bat]
        assert play["about"]["hasReview"] is False
        pitch_flags = [e.get("details", {}).get("hasReview") for e in play["playEvents"]]
        assert any(pitch_flags)

    challenges = feeds.abs_challenges(feed)
    assert len(challenges) == 3
    by_level = {"pitch": 0, "play": 0}
    for challenge in challenges:
        by_level[challenge.level] += 1
    assert by_level == {"pitch": 2, "play": 1}

    play_flag_only = sum(
        1 for p in feed["liveData"]["plays"]["allPlays"] if p["about"].get("hasReview")
    )
    assert play_flag_only == 1
    assert play_flag_only < len(challenges)

    record = next(r for r in corpus if r["game_pk"] == GAME_WITH_PITCH_LEVEL_MJ)
    assert record["totals"]["used"] == 3


def test_nested_additional_reviews_are_counted(corpus):
    """An MJ challenge can hide inside `reviewDetails.additionalReviews`.

    Game 822717 files one challenge as a nested record under a play-level MA
    replay. A walk that reads only the top-level `reviewType` returns 3 where
    `absChallenges` says 4. This trap is not in the SOP text; it is the reason
    the reconciliation below is exact rather than exact-but-one.
    """
    path = feeds.stored_path(SPORT_MLB, SEASON, GAME_WITH_NESTED_MJ)
    feed = feeds.load_feed(path)

    top_level_only = 0
    for play in feed["liveData"]["plays"]["allPlays"]:
        for event in play.get("playEvents", ()):
            details = event.get("reviewDetails") or {}
            top_level_only += details.get("reviewType") == feeds.ABS_REVIEW_TYPE
        details = play.get("reviewDetails") or {}
        top_level_only += details.get("reviewType") == feeds.ABS_REVIEW_TYPE

    assert top_level_only == 3
    assert len(feeds.abs_challenges(feed)) == 4
    record = next(r for r in corpus if r["game_pk"] == GAME_WITH_NESTED_MJ)
    assert record["totals"]["used"] == 4


def test_challenges_reconcile_with_the_counter(corpus):
    """Parsed challenges equal `absChallenges` on every ABS game, exactly.

    Two independent counts of the same thing: the per-challenge records dug out
    of `allPlays`, and the per-team totals statsapi puts in `gameData`. They are
    produced by different parts of the feed and agree on all 2,338 games, both
    in count and in how many were overturned. One mismatch would mean a trap is
    being handled wrongly; it is the strongest check in this file.
    """
    mismatched_count = []
    mismatched_overturns = []
    total = 0
    for record in corpus:
        if not record["marker"]:
            assert record["n_challenges"] == 0, record["game_pk"]
            continue
        total += record["n_challenges"]
        if record["n_challenges"] != record["totals"]["used"]:
            mismatched_count.append(record["game_pk"])
        if record["n_overturned"] != record["totals"]["used_successful"]:
            mismatched_overturns.append(record["game_pk"])

    assert mismatched_count == []
    assert mismatched_overturns == []
    # DT-25 puts the Savant drawer at 4,612 + 5,555 = 10,167 distinct play_ids
    # for 2026 MLB, pulled separately. Two sources, one population.
    assert 9_500 < total < 11_000


# ---------------------------------------------------------------------------
# The seal and the queue
# ---------------------------------------------------------------------------


def test_nothing_sealed_was_stored(corpus):
    """No stored 2026 game is inside the sealed window, by either branch."""
    for record in corpus:
        assert record["season"] == SEASON
        assert record["game_type"] not in feeds.SEALED_GAME_TYPES, record["game_pk"]
        assert record["official_date"] <= paths.LAST_OPEN_DATE, record["game_pk"]
        assert not feeds.is_sealed(
            record["season"], record["game_type"], record["official_date"]
        ), record["game_pk"]

    stored = {record["game_pk"] for record in corpus}
    assert RESCHEDULED_INTO_SEAL not in stored


def test_store_feed_refuses_a_sealed_body(tmp_path, monkeypatch):
    """A game that moved into the sealed window is refused at the writer.

    823543 was scheduled for 2026-05-23, rained out and replayed on 2026-09-22.
    The staging cache holds a copy. Its officialDate is the seal key, and the
    writer re-reads it from the body rather than trusting the plan, because the
    plan was made before the game moved.

    The data root is redirected to a temporary directory for the length of this
    test. If the seal ever stops holding, this test must fail, and a failing
    version of it must not be able to write a sealed game into the real lake --
    which is exactly what happened while this file was being written.
    """
    source = feeds.staging_feed_path(SPORT_MLB, SEASON, RESCHEDULED_INTO_SEAL)
    if not source.exists():
        pytest.skip("the staging copy of 823543 is not on this machine")
    body = source.read_bytes()
    feed = json.loads(body.decode("utf-8"))
    assert feed["gameData"]["datetime"]["officialDate"] == seal.SEAL_START_DATE.isoformat()

    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path))
    assert paths.data_root() == tmp_path.resolve()
    with pytest.raises(feeds.SealBreach):
        feeds.store_feed(SPORT_MLB, SEASON, RESCHEDULED_INTO_SEAL, body)
    assert list(tmp_path.rglob("*.json.zst")) == []

    # The same writer stores an open game, so the refusal above is the seal and
    # not a writer that refuses everything.
    open_source = feeds.staging_feed_path(SPORT_MLB, SEASON, GAME_WITH_BOTH_COUNTERS)
    written = feeds.store_feed(SPORT_MLB, SEASON, GAME_WITH_BOTH_COUNTERS, open_source.read_bytes())
    assert written.is_relative_to(tmp_path.resolve())


def test_plan_never_queues_a_sealed_game():
    """The queue is filtered before a URL is built, not after."""
    schedule = feeds.load_schedule(SPORT_MLB, SEASON, allow_fetch=False)
    games = feeds.schedule_games(schedule)
    the_plan = feeds.plan(games, status="Final")

    assert the_plan.candidates
    for game in the_plan.candidates:
        assert game.official_date <= paths.LAST_OPEN_DATE
        assert game.game_type not in feeds.SEALED_GAME_TYPES
        assert not feeds.is_sealed(game.season, game.game_type, game.official_date)

    sealed = {g.game_pk for g in the_plan.sealed}
    assert RESCHEDULED_INTO_SEAL in sealed
    assert the_plan.sealed
    for game in the_plan.sealed:
        assert feeds.is_sealed(game.season, game.game_type, game.official_date)

    assert feeds.is_sealed(2026, "R", paths.LAST_OPEN_DATE) is False
    for code in feeds.SEALED_GAME_TYPES:
        assert feeds.is_sealed(2026, code, paths.LAST_OPEN_DATE) is True
    assert feeds.is_sealed(2025, "R", paths.LAST_OPEN_DATE) is False


def test_schedule_lists_a_postponed_game_twice():
    """2,459 entries, 2,430 distinct games. Dedupe keeps the replayed entry.

    Counting entries would put the season 29 games over and would pay for 29
    requests that fetch a feed already on disk.
    """
    schedule = feeds.load_schedule(SPORT_MLB, SEASON, allow_fetch=False)
    entries = [g for block in schedule["dates"] for g in block["games"]]
    games = feeds.schedule_games(schedule)

    assert len(entries) > len(games)
    assert len(games) == len({g.game_pk for g in games})
    assert len(games) == 2430

    kept = next(g for g in games if g.game_pk == RESCHEDULED_INTO_SEAL)
    same_pk = [e for e in entries if e["gamePk"] == RESCHEDULED_INTO_SEAL]
    assert len(same_pk) == 2
    assert kept.game_date == max(e["gameDate"] for e in same_pk)
    assert kept.official_date == seal.SEAL_START_DATE


def test_the_sop_command_line_parses_and_the_launcher_exists():
    """The command SOP W2.6 registers is the command this module accepts.

    A step whose verify command passes while its documented invocation does not
    parse is a step that is green and broken, so the argv in the SOP text is
    parsed here verbatim.
    """
    parser = feeds._build_parser()
    args = parser.parse_args(["--sport", "1", "--season", "2026", "--status", "Final", "--resume"])
    assert args.sport == SPORT_MLB
    assert args.season == SEASON
    assert args.status == "Final"
    assert args.resume is True
    assert args.plan_only is False
    assert args.max_requests is None
    assert parser.parse_args(["--sport", "11", "--season", "2024"]).status == "Final"

    launcher = paths.REPO_ROOT / "ops" / "night_statsapi.sh"
    assert launcher.exists()
    assert launcher.stat().st_mode & 0o111
    text = launcher.read_text(encoding="utf-8")
    assert "absump.ingest.feeds" in text
    assert "ABS_SEAL_UNLOCK" in text


def test_resume_leaves_nothing_to_request():
    """`--resume` costs zero requests once the corpus is stored.

    The SOP's own words: manifested games are skipped, which is what makes a
    daily re-invocation free. Here the whole open 2026 universe is on disk, so
    the queue is empty and tonight's batch issues no request at all.
    """
    schedule = feeds.load_schedule(SPORT_MLB, SEASON, allow_fetch=False)
    the_plan = feeds.plan(feeds.schedule_games(schedule), status="Final")
    queue = feeds.remaining_after_import(the_plan.candidates, SPORT_MLB, SEASON)
    assert queue == []
    assert len(the_plan.candidates) >= EXPECTED_GAMES
