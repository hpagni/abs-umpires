"""W2.10 and the W2.9 backfill: the minors URL, admission, header skip, stops.

SOP W2.10 pulls the Savant minors CSV for AAA 2023-2025, one request per
game-day, at the URL the SOP writes with its two mandatory parameters,
``minors=true`` and ``hfLevel=AAA%7C``. The minors CSV has no level column, so
a day enters the lake only when its game_pk set is a subset of the sportId=11
Final games the stored schedule lists for that date. The W2.9 backfill pulls
MLB 2015-2021 the same way against the sportId=1 schedule, and a season whose
header is not byte-identical to the committed fixture (DT-02) is recorded and
skipped, never "fixed".

Everything here is offline. The real client runs over an httpx MockTransport
with a temporary cache, a temporary lake and a fake clock, so the 10 s Savant
spacing is real arithmetic that costs no wall clock. No test reads data/.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import re
from pathlib import Path

import httpx
import pytest
import zstandard

from absump import http as client
from absump import paths
from absump.ingest import pull_statcast as runner
from absump.ingest import statcast_day as sc

DAY_IN_URL = re.compile(r"game_date_gt=(\d{4}-\d{2}-\d{2})")

#: SOP W2.10, the URL for 2024-07-12, joined from the SOP's four lines.
SOP_MINORS_URL = (
    "https://baseballsavant.mlb.com/statcast-search-minors/csv?all=true&type=details"
    "&player_type=batter&min_pitches=0&min_results=0&group_by=name"
    "&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
    "&minors=true&hfLevel=AAA%7C"
    "&game_date_gt=2024-07-12&game_date_lt=2024-07-12"
)

#: SOP W2.9, the URL for 2026-09-15, joined the same way.
SOP_MLB_URL = (
    "https://baseballsavant.mlb.com/statcast_search/csv?all=true&type=details"
    "&player_type=batter&min_pitches=0&min_results=0&group_by=name"
    "&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
    "&hfSea=2026%7C&game_date_gt=2026-09-15&game_date_lt=2026-09-15"
)


# ---------------------------------------------------------------------------
# Synthetic days and schedules
# ---------------------------------------------------------------------------


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def synth_day(day: dt.date, game_pks: list[int], *, columns=None) -> bytes:
    """A Savant-shaped CSV: BOM, quoted fields, LF, one tracked pitch per game."""
    names = tuple(columns) if columns is not None else sc.contract_columns()
    lines = [",".join(_quote(n) for n in names)]
    for pk in game_pks:
        row = {
            "pitch_type": "FF",
            "game_date": day.isoformat(),
            "description": "called_strike",
            "plate_x": "0.1",
            "plate_z": "2.5",
            "sz_top": "3.4",
            "sz_bot": "1.6",
            "game_pk": str(pk),
        }
        lines.append(",".join(_quote(row.get(n, "")) for n in names))
    return b"\xef\xbb\xbf" + "\n".join(lines).encode("utf-8")


def store_schedule(sport_id: int, season: int, games: list[tuple[int, str]]) -> None:
    """(game_pk, officialDate) rows, every one of them played and Final."""
    rows = [
        {
            "gamePk": pk,
            "gameGuid": f"g{pk}",
            "officialDate": day,
            "gameDate": f"{day}T23:05:00Z",
            "gameType": "R",
            "status": {"codedGameState": "F", "abstractGameState": "Final"},
            "teams": {"away": {"team": {"id": 1}}, "home": {"team": {"id": 2}}},
        }
        for pk, day in games
    ]
    body = json.dumps({"dates": [{"games": rows}]}).encode("utf-8")
    target = paths.raw_schedule(sport_id, season)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(zstandard.ZstdCompressor().compress(body))


def games_for(season: int, base: int, n_days: int = 3) -> list[tuple[int, str]]:
    """Two games a day on n_days consecutive days in July."""
    out = []
    for index in range(n_days):
        day = dt.date(season, 7, 10 + index).isoformat()
        out += [(base + 10 * index, day), (base + 10 * index + 1, day)]
    return out


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Wire(httpx.MockTransport):
    """Serves Savant days from a table and statsapi schedules on request."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.urls: list[str] = []
        self.times: list[float] = []
        self.days: dict[tuple[str, dt.date], list[int]] = {}
        self.columns: dict[int, tuple[str, ...]] = {}
        self.refuse_after: int | None = None
        self.schedules: dict[int, list[tuple[int, str]]] = {}
        super().__init__(self._respond)

    def _respond(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.urls.append(url)
        self.times.append(self.clock.monotonic())
        if "statsapi.mlb.com" in url:
            season = int(re.search(r"startDate=(\d{4})", url).group(1))
            rows = [
                {
                    "gamePk": pk,
                    "officialDate": day,
                    "gameDate": f"{day}T23:05:00Z",
                    "gameType": "R",
                    "status": {"codedGameState": "F", "abstractGameState": "Final"},
                }
                for pk, day in self.schedules[season]
            ]
            return httpx.Response(200, content=json.dumps({"dates": [{"games": rows}]}).encode())
        if self.refuse_after is not None and len(self.savant) > self.refuse_after:
            return httpx.Response(403, content=b"Forbidden")
        day = dt.date.fromisoformat(DAY_IN_URL.search(url).group(1))
        level = "aaa" if "statcast-search-minors" in url else "mlb"
        pks = self.days.get((level, day), [])
        return httpx.Response(200, content=synth_day(day, pks, columns=self.columns.get(day.year)))

    @property
    def savant(self) -> list[str]:
        return [u for u in self.urls if "baseballsavant" in u]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path / "lake"))
    monkeypatch.delenv("ABSUMP_DRY_RUN", raising=False)
    monkeypatch.setattr(runner, "EVIDENCE_DIR", tmp_path / "evidence")
    monkeypatch.setattr(runner, "NIGHT_LOG_DIR", tmp_path / "night")
    clock = FakeClock()
    wire = Wire(clock)
    client._reset_state(cache_dir=tmp_path / "cache", transport=wire)
    monkeypatch.setattr(client, "_monotonic", clock.monotonic)
    monkeypatch.setattr(client, "_sleep", clock.sleep)
    wire.tmp = tmp_path
    yield wire
    client._reset_state()


def aaa_world(wire: Wire, *, extra_on: dt.date | None = None) -> dict[int, list[tuple[int, str]]]:
    """Three AAA seasons, three days each, every game on Savant.

    With `extra_on`, that day's CSV also carries 999999, a game the sportId=11
    schedule does not know: an MLB or Florida State League row.
    """
    seasons = {}
    for season in (2023, 2024, 2025):
        games = games_for(season, 700000 + 1000 * (season - 2023))
        store_schedule(11, season, games)
        seasons[season] = games
        for pk, day in games:
            wire.days.setdefault(("aaa", dt.date.fromisoformat(day)), []).append(pk)
    if extra_on is not None:
        wire.days[("aaa", extra_on)].append(999999)
    return seasons


def evidence(wire: Wire) -> str:
    path = wire.tmp / "evidence" / "W2.10.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run(scopes, **kw):
    kw.setdefault("marker_path", runner.NIGHT_LOG_DIR / "marker.json")
    kw.setdefault("schedule_wait_s", 0.0)
    return runner.run_scopes(scopes, **kw)


AAA_ORDER = runner.make_scope("aaa", [2024, 2025, 2023])


# ---------------------------------------------------------------------------
# URL construction, both levels
# ---------------------------------------------------------------------------


def test_minors_url_is_the_sop_url_parameter_for_parameter():
    assert sc.day_url("2024-07-12", level="aaa") == SOP_MINORS_URL


def test_minors_url_carries_both_mandatory_parameters_and_no_season_filter():
    url = sc.day_url("2023-05-02", level="aaa")
    assert "&minors=true&" in url
    assert "&hfLevel=AAA%7C&" in url
    assert "hfSea" not in url
    assert "level=AAA&" not in url.replace("hfLevel=AAA", "")


def test_mlb_url_is_unchanged_by_the_level_argument():
    assert sc.day_url("2026-09-15") == SOP_MLB_URL
    assert sc.day_url("2026-09-15", level="mlb") == SOP_MLB_URL
    assert sc.day_url("2015-06-01", level="mlb").count("hfSea=2015%7C") == 1


def test_a_minors_template_without_a_mandatory_parameter_is_refused(monkeypatch):
    broken = sc._MINORS_DAY_URL.replace("&minors=true", "")
    monkeypatch.setattr(sc, "_MINORS_DAY_URL", broken)
    with pytest.raises(sc.DayContractError, match="minors=true"):
        sc.day_url("2024-07-12", level="aaa")


def test_an_unknown_level_and_a_sealed_day_are_refused():
    with pytest.raises(ValueError):
        sc.day_url("2024-07-12", level="aa")
    with pytest.raises(paths.SealViolation):
        sc.day_url("2026-09-22", level="aaa")


def test_no_scope_can_name_2026_or_the_w60_mlb_seasons():
    for level, season in (
        ("aaa", 2026),
        ("mlb", 2026),
        ("mlb", 2022),
        ("aaa", 2022),
        ("mlb", 2014),
    ):
        with pytest.raises(ValueError):
            runner.make_scope(level, [season])
    assert runner.parse_scope("mlb:2021,2020").seasons == (2021, 2020)
    assert runner.SCOPE_SEASONS["mlb"] == tuple(range(2015, 2022))
    assert runner.SCOPE_SEASONS["aaa"] == (2023, 2024, 2025)


# ---------------------------------------------------------------------------
# The admission check
# ---------------------------------------------------------------------------


def _report(day: str, pks: list[int]) -> sc.DayReport:
    return sc.validate_day(synth_day(dt.date.fromisoformat(day), pks), day)


def test_admit_accepts_a_subset_of_the_final_games():
    assert sc.admit(_report("2024-07-12", [1, 2]), {1, 2, 3}).game_pks == (1, 2)
    assert sc.admit(_report("2024-07-12", []), {1}).game_pks == ()


def test_admit_refuses_a_game_the_schedule_does_not_list():
    with pytest.raises(sc.NotInSchedule, match="999999"):
        sc.admit(_report("2024-07-12", [1, 999999]), {1, 2, 3})


def test_final_games_by_date_counts_every_final_occurrence(world):
    body = {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 5,
                        "officialDate": "2024-07-10",
                        "status": {"abstractGameState": "Final"},
                    },
                    {
                        "gamePk": 5,
                        "officialDate": "2024-07-11",
                        "status": {"abstractGameState": "Final"},
                    },
                    {
                        "gamePk": 6,
                        "officialDate": "2024-07-11",
                        "status": {"abstractGameState": "Preview"},
                    },
                ]
            }
        ]
    }
    target = paths.raw_schedule(11, 2024)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(zstandard.ZstdCompressor().compress(json.dumps(body).encode()))
    got = runner.final_game_pks_by_date(11, 2024)
    assert got == {dt.date(2024, 7, 10): frozenset({5}), dt.date(2024, 7, 11): frozenset({5})}


def test_a_day_with_a_foreign_game_is_refused_and_never_stored(world):
    bad = dt.date(2024, 7, 11)
    aaa_world(world, extra_on=bad)
    report = run([AAA_ORDER], resume=True)
    assert report.stop_reason == runner.STOP_QUEUE_EMPTY
    assert report.refused == [f"aaa:{bad.isoformat()}"]
    assert not sc.raw_path(bad, level="aaa").exists()
    assert report.stored == 8
    assert "REFUSED aaa 2024 2024-07-11" in evidence(world)
    stored = {day for day, _ in sc.raw_days(level="aaa")}
    assert len(stored) == 8 and bad not in stored
    assert sc.raw_days(level="mlb") == []


def test_the_chain_takes_the_seasons_in_the_order_given_newest_day_first(world):
    aaa_world(world)
    run([AAA_ORDER], resume=True)
    days = [DAY_IN_URL.search(u).group(1) for u in world.savant]
    assert days == [
        "2024-07-12",
        "2024-07-11",
        "2024-07-10",
        "2025-07-12",
        "2025-07-11",
        "2025-07-10",
        "2023-07-12",
        "2023-07-11",
        "2023-07-10",
    ]
    assert all("statcast-search-minors" in u for u in world.savant)


def test_the_gap_between_savant_requests_is_at_least_ten_seconds(world):
    aaa_world(world)
    run([AAA_ORDER], resume=True)
    gaps = [b - a for a, b in itertools.pairwise(world.times)]
    assert gaps and min(gaps) >= client._min_interval("baseballsavant.mlb.com") == 10.0


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def test_resume_sends_nothing_for_a_day_already_in_the_manifest(world):
    """A refused day is in the manifest but not in the lake. A resumed run
    judges it again from the raw cache and asks the wire for nothing."""
    bad = dt.date(2025, 7, 10)
    aaa_world(world, extra_on=bad)
    run([AAA_ORDER], resume=True)
    sent = len(world.urls)
    manifested = set(client._manifest_index())
    assert sc.day_url(bad, level="aaa") in manifested

    again = run([AAA_ORDER], resume=True)
    assert len(world.urls) == sent, "a resumed run asked the wire again"
    assert again.wire == 0
    assert again.cached == 1 and again.refused == [f"aaa:{bad.isoformat()}"]
    assert again.skipped_in_lake == 8
    assert not sc.raw_path(bad, level="aaa").exists()


def test_resume_picks_up_where_max_requests_stopped(world):
    aaa_world(world)
    first = run([AAA_ORDER], resume=True, max_requests=4)
    assert first.stop_reason == runner.STOP_MAX_REQUESTS and first.wire == 4
    assert first.next_day == "2025-07-11"
    second = run([AAA_ORDER], resume=True)
    assert second.wire == 5 and second.skipped_in_lake == 4
    assert len(world.savant) == len(set(world.savant)) == 9


def test_without_resume_a_stored_day_is_judged_again_from_disk_at_no_cost(world):
    aaa_world(world)
    run([AAA_ORDER], resume=True)
    sent = len(world.urls)
    again = run([AAA_ORDER], resume=False)
    assert len(world.urls) == sent
    assert again.rechecked == 9 and again.wire == 0


# ---------------------------------------------------------------------------
# Header drift: record, skip the year, move on
# ---------------------------------------------------------------------------


def backfill_world(wire: Wire, seasons=(2016, 2015)) -> None:
    for season in seasons:
        games = games_for(season, 400000 + 1000 * (season - 2015))
        wire.schedules[season] = games
        for pk, day in games:
            wire.days.setdefault(("mlb", dt.date.fromisoformat(day)), []).append(pk)


def test_a_drifted_header_skips_that_year_and_the_chain_moves_on(world):
    backfill_world(world)
    moved = list(sc.contract_columns())
    moved[0], moved[1] = moved[1], moved[0]
    world.columns[2016] = tuple(moved)
    report = run([runner.make_scope("mlb", [2016, 2015])], resume=True)
    assert report.header_skipped == ["mlb:2016"]
    assert report.stop_reason == runner.STOP_QUEUE_EMPTY
    seasons_asked = [DAY_IN_URL.search(u).group(1)[:4] for u in world.savant]
    assert seasons_asked == ["2016", "2015", "2015", "2015"], "2016 was not skipped after one day"
    assert not any(day.year == 2016 for day, _ in sc.raw_days(level="mlb"))
    assert sum(1 for day, _ in sc.raw_days(level="mlb") if day.year == 2015) == 3
    log = evidence(world)
    assert "HEADER mlb 2016 2016-07-12: DT-02 refused, season 2016 skipped" in log


def test_a_drifted_header_is_not_fixed_and_a_resume_costs_nothing_more(world):
    backfill_world(world, seasons=(2015,))
    world.columns[2015] = tuple(list(sc.contract_columns())[:-1])
    run([runner.make_scope("mlb", [2015])], resume=True)
    sent = len(world.savant)
    again = run([runner.make_scope("mlb", [2015])], resume=True)
    assert len(world.savant) == sent == 1
    assert again.header_skipped == ["mlb:2015"]
    assert sc.raw_days(level="mlb") == []


# ---------------------------------------------------------------------------
# The MLB 2015-2021 schedules, and the statsapi mutex
# ---------------------------------------------------------------------------


def test_missing_backfill_schedules_are_pulled_once_through_the_client(world):
    backfill_world(world)
    run([runner.make_scope("mlb", [2016, 2015])], resume=True)
    statsapi = [u for u in world.urls if "statsapi" in u]
    assert len(statsapi) == 2
    assert all("sportId=1&" in u for u in statsapi)
    assert paths.raw_schedule(1, 2015).exists() and paths.raw_schedule(1, 2016).exists()
    run([runner.make_scope("mlb", [2016, 2015])], resume=True)
    assert len([u for u in world.urls if "statsapi" in u]) == 2


def test_the_schedule_pull_waits_for_the_statsapi_mutex(world):
    backfill_world(world, seasons=(2015,))
    lock = runner.statsapi_lock_path()
    lock.mkdir(parents=True)
    naps: list[float] = []

    def nap(seconds: float) -> None:
        naps.append(seconds)
        if len(naps) == 3:
            lock.rmdir()  # the statsapi batch ends

    pulled = runner.ensure_schedules(1, [2015], poll_s=30.0, wait_s=3600.0, sleep=nap, stream=None)
    assert pulled == [2015]
    assert naps == [30.0, 30.0, 30.0]
    assert not lock.exists(), "the mutex was not released"


def test_the_schedule_pull_gives_up_when_the_mutex_is_never_released(world):
    backfill_world(world, seasons=(2015,))
    runner.statsapi_lock_path().mkdir(parents=True)
    ticks = iter(range(0, 10_000, 100))
    with pytest.raises(runner.ScheduleUnavailable):
        runner.ensure_schedules(
            1,
            [2015],
            poll_s=100.0,
            wait_s=250.0,
            sleep=lambda s: None,
            monotonic=lambda: float(next(ticks)),
        )
    assert [u for u in world.urls if "statsapi" in u] == []


# ---------------------------------------------------------------------------
# Stops: the cap is clean, a 403 is fatal
# ---------------------------------------------------------------------------


def test_the_daily_cap_stops_the_chain_cleanly(world):
    aaa_world(world)
    host = "baseballsavant.mlb.com"
    cap = client._daily_cap(host)
    client._write_budget({"utc_date": client._utc_day(), "used": {host: cap - 2}})
    report = run([AAA_ORDER], resume=True)
    assert report.stop_reason == runner.STOP_DAILY_CAP
    assert report.wire == 2 and len(world.savant) == 2
    assert report.next_day == "2024-07-10"
    assert report.failed == 0


def test_a_403_stops_the_chain_and_the_cli_exits_non_zero(world, capsys):
    aaa_world(world)
    world.refuse_after = 1
    code = runner.main(
        [
            "--run",
            "--scope",
            "aaa:2024,2025,2023",
            "--resume",
            "--marker",
            str(world.tmp / "m.json"),
            "--evidence",
            str(world.tmp / "e.log"),
        ]
    )
    assert code == 3
    assert len(world.savant) == 2, "a request was sent after the 403"
    assert "FATAL aaa 2024 2024-07-11" in (world.tmp / "e.log").read_text()


def test_the_cli_refuses_a_2026_scope_before_anything_runs(world, capsys):
    assert runner.main(["--run", "--scope", "aaa:2026"]) == 2
    assert world.urls == []


# ---------------------------------------------------------------------------
# Completion and the W2.10 verify
# ---------------------------------------------------------------------------


def test_a_complete_run_stamps_the_level_and_the_verify_passes(world):
    bad = dt.date(2023, 7, 12)
    aaa_world(world, extra_on=bad)
    run([AAA_ORDER], resume=True)
    stamp = json.loads(runner.completion_path("aaa").read_text())
    assert stamp["days_refused"] == [f"aaa:{bad.isoformat()}"]
    assert stamp["days_in_scope"] == {"2023": 3, "2024": 3, "2025": 3}
    assert runner.verify_scope("aaa") == []


def test_no_stamp_while_the_pull_is_partial_and_the_verify_says_why(world):
    aaa_world(world)
    run([AAA_ORDER], resume=True, max_requests=5)
    assert not runner.completion_path("aaa").exists()
    failures = runner.verify_scope("aaa")
    assert any(f.startswith("V-00") for f in failures)
    assert any(f.startswith("V-01") for f in failures)


def test_a_run_over_part_of_the_seasons_never_stamps_the_level(world):
    aaa_world(world)
    run([runner.make_scope("aaa", [2024])], resume=True)
    assert not runner.completion_path("aaa").exists()
