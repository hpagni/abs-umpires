"""The four fixes the W2.8 batch needed from absump.ingest.feeds.

The phase 07 launch ran the AAA feed pull and found four defects in the
command line and the fetch loop (logs of 2026-09-30):

  (a) ``--season`` took one int, so the SOP command
      ``--season 2023 2024 2025`` exited 2 before sending anything;
  (b) ``plan`` dropped Postponed games but not Cancelled ones, so 26 AAA 2023
      and 7 AAA 2024 Cancelled games were queued, paid for, and refused as
      short bodies;
  (c) ``fetch_games`` caught ``HttpError``, which includes ``Fatal``, and
      moved on to the next game after a 403;
  (d) at the daily cap every remaining game slept out the 4 s spacing and was
      refused one by one, and the process exited 1.

Everything here is offline. The real client runs over an httpx MockTransport
with a temporary cache and a temporary lake, and ``_sleep`` only records, so
the spacing is honoured in logic and costs no wall clock. No test reads data/.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx
import pytest
import zstandard

from absump import http as client
from absump import paths
from absump.ingest import feeds

GAME_IN_URL = re.compile(r"/game/(\d+)/feed/live")
STATSAPI = "statsapi.mlb.com"


def feed_body(game_pk: int, season: int, day: str) -> bytes:
    """A feed that passes validate_body: the right gamePk, over 300,000 B."""
    feed = {
        "gameData": {
            "game": {"pk": game_pk, "type": "R", "season": str(season)},
            "datetime": {"officialDate": day},
        },
        "liveData": {"plays": {"allPlays": []}, "pad": "x" * (feeds.MIN_FEED_BYTES + 1000)},
    }
    return json.dumps(feed).encode("utf-8")


def schedule_payload(season: int, games: list[tuple[int, str, str]]) -> bytes:
    """(game_pk, officialDate, detailedState) rows under abstract state Final."""
    rows = [
        {
            "gamePk": pk,
            "gameType": "R",
            "season": str(season),
            "officialDate": day,
            "gameDate": f"{day}T23:05:00Z",
            "status": {"abstractGameState": "Final", "detailedState": state},
        }
        for pk, day, state in games
    ]
    return json.dumps({"dates": [{"games": rows}]}).encode("utf-8")


def store_schedule(sport_id: int, season: int, games: list[tuple[int, str, str]]) -> None:
    target = paths.raw_schedule(sport_id, season)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(zstandard.ZstdCompressor().compress(schedule_payload(season, games)))


class Wire(httpx.MockTransport):
    """Serves one feed per game and records every URL it is actually asked for."""

    def __init__(self, days: dict[int, tuple[int, str]]) -> None:
        self.days = days
        self.urls: list[str] = []
        self.refuse: set[int] = set()
        super().__init__(self._respond)

    def _respond(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.urls.append(url)
        pk = int(GAME_IN_URL.search(url).group(1))
        if pk in self.refuse:
            return httpx.Response(403, content=b"Forbidden")
        season, day = self.days[pk]
        return httpx.Response(200, content=feed_body(pk, season, day))

    @property
    def game_pks(self) -> list[int]:
        return [int(GAME_IN_URL.search(url).group(1)) for url in self.urls]


# Two AAA seasons, three games each. 700003 is Cancelled and 700005 Postponed.
SEASON_GAMES = {
    2023: [
        (700001, "2023-05-01", "Final"),
        (700002, "2023-05-02", "Completed Early"),
        (700003, "2023-05-03", "Cancelled"),
    ],
    2024: [
        (700004, "2024-05-01", "Final"),
        (700005, "2024-05-02", "Postponed"),
        (700006, "2024-05-03", "Final"),
    ],
}


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path / "lake"))
    monkeypatch.delenv("ABSUMP_DRY_RUN", raising=False)
    days = {}
    for season, games in SEASON_GAMES.items():
        store_schedule(11, season, games)
        days.update({pk: (season, day) for pk, day, _ in games})
    wire = Wire(days)
    client._reset_state(cache_dir=tmp_path / "cache", transport=wire)
    sleeps: list[float] = []
    monkeypatch.setattr(client, "_sleep", sleeps.append)
    wire.sleeps = sleeps
    yield wire
    client._reset_state()


def run(*seasons: int, extra: tuple[str, ...] = ()) -> int:
    argv = ["--sport", "11", "--season", *map(str, seasons), "--status", "Final", "--resume"]
    return feeds.main([*argv, "--no-import-staging", *extra])


# ---------------------------------------------------------------------------
# (a) several seasons in one invocation
# ---------------------------------------------------------------------------


def test_a_the_season_flag_takes_several_seasons():
    args = feeds._build_parser().parse_args(["--sport", "11", "--season", "2023", "2024", "2025"])
    assert args.season == [2023, 2024, 2025]
    one = feeds._build_parser().parse_args(["--sport", "1", "--season", "2026"])
    assert one.season == [2026]


def test_a_the_sop_command_runs_every_season_in_order(world, capsys):
    assert run(2023, 2024) == feeds.EXIT_OK
    assert world.game_pks == [700001, 700002, 700004, 700006]
    out = capsys.readouterr().out
    assert "sport 11 season 2023 status Final" in out
    assert "sport 11 season 2024 status Final" in out


def test_a_a_second_run_over_several_seasons_sends_nothing(world):
    assert run(2023, 2024) == feeds.EXIT_OK
    sent = len(world.urls)
    assert run(2023, 2024) == feeds.EXIT_OK
    assert len(world.urls) == sent


# ---------------------------------------------------------------------------
# (b) Cancelled is dropped the way Postponed is
# ---------------------------------------------------------------------------


def test_b_plan_drops_cancelled_and_postponed_games():
    games = feeds.schedule_games(
        json.loads(
            schedule_payload(2023, SEASON_GAMES[2023] + [(700009, "2023-05-04", "Postponed")])
        )
    )
    the_plan = feeds.plan(games, status="Final")
    assert [g.game_pk for g in the_plan.candidates] == [700001, 700002]
    assert sorted(g.game_pk for g in the_plan.wrong_status) == [700003, 700009]


def test_b_a_cancelled_game_is_never_requested(world):
    assert run(2023) == feeds.EXIT_OK
    assert 700003 not in world.game_pks
    assert 700005 not in world.game_pks


# ---------------------------------------------------------------------------
# (c) a 403 stops the pull
# ---------------------------------------------------------------------------


def test_c_fatal_stops_the_queue_instead_of_moving_to_the_next_game(world):
    world.refuse = {700001}
    assert run(2023, 2024) == feeds.EXIT_FATAL
    assert world.game_pks == [700001], "a request was sent after the host refused the client"


def test_c_fatal_is_counted_and_reported(world):
    world.refuse = {700002}
    report: list[str] = []
    games = feeds.plan(
        feeds.schedule_games(json.loads(schedule_payload(2023, SEASON_GAMES[2023]))), status="Final"
    ).candidates
    counts = feeds.fetch_games(games, 11, 2023, report=report)
    assert counts["fetched"] == 1
    assert counts["fatal"] == 1
    assert counts["failed"] == 0
    assert any(line.startswith("FATAL 700002") for line in report)


def test_c_a_short_body_is_still_one_bad_game_and_the_loop_continues(world, monkeypatch):
    real = feed_body

    def short_for_first(pk, season, day):
        return b'{"gameData": {}}' if pk == 700001 else real(pk, season, day)

    monkeypatch.setattr(sys.modules[__name__], "feed_body", short_for_first)
    assert run(2023) == feeds.EXIT_FAILED_GAMES
    assert world.game_pks == [700001, 700002]


# ---------------------------------------------------------------------------
# (d) the daily cap is a clean stop
# ---------------------------------------------------------------------------


def _spend_to(remaining: int) -> None:
    cap = client._daily_cap(STATSAPI)
    client._write_budget({"utc_date": client._utc_day(), "used": {STATSAPI: cap - remaining}})


def test_d_the_cap_stops_the_batch_cleanly_and_exits_zero(world, capsys):
    _spend_to(1)
    assert run(2023, 2024) == feeds.EXIT_OK
    assert world.game_pks == [700001]
    out = capsys.readouterr().out
    assert "stop: daily-cap reached in season 2023" in out
    assert "Seasons not started: 2024" in out
    assert "Traceback" not in out


def test_d_the_cap_does_not_sleep_once_per_remaining_game(world):
    """Before the fix every remaining game slept 4 s and was then refused."""
    _spend_to(0)
    assert run(2023, 2024) == feeds.EXIT_OK
    assert world.urls == []
    assert len(world.sleeps) <= 1, f"slept {len(world.sleeps)} times at a spent cap"


def test_d_the_next_night_resumes_where_the_cap_stopped(world):
    _spend_to(2)
    assert run(2023, 2024) == feeds.EXIT_OK
    assert world.game_pks == [700001, 700002]
    client._write_budget({"utc_date": client._utc_day(), "used": {}})
    client._BUDGET_FLOOR.clear()  # a new UTC day, as the next night sees it
    assert run(2023, 2024) == feeds.EXIT_OK
    assert world.game_pks == [700001, 700002, 700004, 700006]
