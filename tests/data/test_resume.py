"""W6.0 tests for the Statcast backfill runner: order, resume, cap, one chain.

SOP W6.0 names what this file has to hold the runner to. It is idempotent, it
is resumable after an interruption, it is ordered NEWEST-FIRST, it subtracts
every day the staging manifest records as ok, it stops cleanly at the 800/day
Savant cap rather than exceeding it, and it writes a resume marker so night two
starts where night one stopped. One sequential chain, never five parallel jobs.

Everything here is SYNTHETIC and offline. The day list comes from a schedule
payload this file writes into a temporary lake, the CSV bodies are built from
the 119 column names committed in `contracts/statcast_csv.yml`, and the client
is a stub that counts what the runner asked for. Nothing opens a connection and
nothing reads `data/`, so this file runs in a clean clone (RP-08).

That is the point of the split. `python -m absump.ingest.pull_statcast --check`
is the data-bound half of the W6.0 gate: it runs DT-01 and DT-02 over every day
actually on disk and fails on an empty lake. This file is the logic half, and
it proves the guards fire, which no amount of real data can prove -- no real
day comes near the 25,000-row cap, and no real night stops at a cap of five.
"""

from __future__ import annotations

import datetime as dt
import io
import itertools
import json
import re
from pathlib import Path

import pytest
import yaml
import zstandard

from absump import http as client
from absump import paths
from absump.ingest import pull_statcast as runner
from absump.ingest import schedule
from absump.ingest import statcast_day as sc

DAY_IN_URL = re.compile(r"game_date_gt=(\d{4}-\d{2}-\d{2})")


# ---------------------------------------------------------------------------
# A synthetic day, built from the committed column list
# ---------------------------------------------------------------------------


def _quote(value: str) -> str:
    inner = value.replace('"', '""')
    return f'"{inner}"'


def synth_day(rows: list[dict[str, str]], *, bom: bool = True, columns=None) -> bytes:
    """A Savant-shaped CSV: BOM, every field quoted, LF, no trailing newline."""
    names = tuple(columns) if columns is not None else sc.contract_columns()
    lines = [",".join(_quote(name) for name in names)]
    for row in rows:
        lines.append(",".join(_quote(row.get(name, "")) for name in names))
    body = "\n".join(lines).encode("utf-8")
    return b"\xef\xbb\xbf" + body if bom else body


def tracked_row(**overrides: str) -> dict[str, str]:
    """One tracked called strike, with every column the guards look at filled."""
    row = {
        "pitch_type": "FF",
        "game_date": "2026-09-15",
        "description": "called_strike",
        "plate_x": "0.10",
        "plate_z": "2.50",
        "sz_top": "3.40",
        "sz_bot": "1.60",
        "zone": "5",
        "game_pk": "800001",
        "umpire": "",
    }
    row.update(overrides)
    return row


def one_good_day(day: dt.date) -> bytes:
    return synth_day([tracked_row(game_date=day.isoformat(), game_pk="800001")])


# ---------------------------------------------------------------------------
# A synthetic schedule payload, stored in a temporary lake
# ---------------------------------------------------------------------------


def schedule_payload(games: list[dict[str, str]]) -> bytes:
    """The shape absump.ingest.schedule.extract reads, and nothing more."""
    rows = []
    for index, game in enumerate(games):
        rows.append(
            {
                "gamePk": 700000 + index,
                "gameGuid": f"guid-{index}",
                "officialDate": game["date"],
                "gameDate": f"{game['date']}T23:05:00Z",
                "gameType": game.get("game_type", "R"),
                "status": {
                    "codedGameState": game.get("coded", "F"),
                    "abstractGameState": game.get("abstract", "Final"),
                    "detailedState": "Final",
                },
                "teams": {"away": {"team": {"id": 111}}, "home": {"team": {"id": 147}}},
                "venue": {"id": 3313},
                "doubleHeader": "N",
                "gameNumber": 1,
            }
        )
    return json.dumps({"dates": [{"games": rows}]}).encode("utf-8")


def store_schedule(season: int, games: list[dict[str, str]]) -> Path:
    return schedule._store_raw(runner.SPORT_ID, season, schedule_payload(games))


def season_span(season: int, count: int, *, last: dt.date) -> list[dt.date]:
    """`count` consecutive days ending on `last`, all inside `season`."""
    return [last - dt.timedelta(days=offset) for offset in range(count - 1, -1, -1)]


#: The real shape of the pull, day for day: 908 open game-days over five
#: seasons, the 2026 season stopping at the cutoff. The counts are the ones the
#: schedule payloads on this machine produce, so the synthetic world the cap and
#: the two-night split are checked against is the size of the real one.
FULL_SEASONS: dict[int, tuple[int, dt.date]] = {
    2022: (179, dt.date(2022, 10, 5)),
    2023: (182, dt.date(2023, 10, 1)),
    2024: (185, dt.date(2024, 9, 30)),
    2025: (184, dt.date(2025, 9, 28)),
    2026: (178, paths.LAST_OPEN_DATE),
}


def store_full_schedule() -> dict[int, list[dt.date]]:
    """Write one payload per season and return the day list per season."""
    by_season: dict[int, list[dt.date]] = {}
    for season, (count, last) in FULL_SEASONS.items():
        days = season_span(season, count, last=last)
        store_schedule(season, [{"date": day.isoformat()} for day in days])
        by_season[season] = days
    return by_season


# ---------------------------------------------------------------------------
# The stub client. It counts, it never connects.
# ---------------------------------------------------------------------------


class StubSavant:
    """Stands in for absump.http.get and for the daily budget it enforces."""

    def __init__(
        self, cap: int, *, bodies=None, host: str = "", trips_at: int | None = None
    ) -> None:
        self.cap = cap
        self.used = 0
        self.host = host
        self.urls: list[str] = []
        self.days: list[dt.date] = []
        self.trips_at = trips_at
        self.enforce_cap = True
        self._bodies = bodies or one_good_day

    def get(self, url: str, *, host_budget: bool = True) -> client.Response:
        match = DAY_IN_URL.search(url)
        assert match, f"the day URL carries no game_date_gt: {url}"
        day = dt.date.fromisoformat(match.group(1))
        if self.trips_at is not None and len(self.days) >= self.trips_at:
            raise client.BudgetExceeded(f"{self.host}: cap spent between the check and the call")
        if self.enforce_cap and self.used >= self.cap:
            raise client.BudgetExceeded(f"{self.host}: {self.used}/{self.cap} used")
        self.used += 1
        self.urls.append(url)
        self.days.append(day)
        body = self._bodies(day)
        return client.Response(
            url=url,
            host=self.host,
            status_code=200,
            content=body,
            dest_path=Path("unused"),
            sha256="",
            wire_bytes=len(body),
            disk_bytes=len(body),
            attempt=1,
            elapsed_s=0.0,
            from_cache=False,
        )

    def budget(self) -> dict:
        return {"utc_date": "2026-09-23", "used": {self.host: self.used}}


@pytest.fixture
def lake(tmp_path, monkeypatch):
    """A temporary data root, so no test reads or writes the real lake."""
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def stub(monkeypatch):
    """Install a stub client and a deterministic budget. Returns a factory."""

    def install(cap: int, *, bodies=None, trips_at: int | None = None) -> StubSavant:
        host = runner.savant_host()
        fake = StubSavant(cap, bodies=bodies, host=host, trips_at=trips_at)
        monkeypatch.setattr(client, "get", fake.get)
        monkeypatch.setattr(client, "_read_budget", fake.budget)
        monkeypatch.setattr(client, "_daily_cap", lambda name: fake.cap)
        return fake

    return install


def marker_path(lake: Path) -> Path:
    return lake / "night" / "resume.json"


# ---------------------------------------------------------------------------
# The day list. Derived from the schedule, never enumerated by hand.
# ---------------------------------------------------------------------------


def test_season_days_reads_the_schedule_payload(lake):
    store_schedule(
        2024,
        [
            {"date": "2024-04-01"},
            {"date": "2024-04-02"},
            {"date": "2024-04-02"},
        ],
    )
    assert runner.season_days(2024) == [dt.date(2024, 4, 1), dt.date(2024, 4, 2)]


def test_a_day_with_no_played_game_is_not_in_scope(lake):
    store_schedule(
        2024,
        [
            {"date": "2024-04-01"},
            {"date": "2024-04-02", "coded": "D", "abstract": "Preview"},
            {"date": "2024-04-03", "coded": "C", "abstract": "Final"},
        ],
    )
    assert runner.season_days(2024) == [dt.date(2024, 4, 1)]


def test_an_excluded_game_type_is_not_in_scope(lake):
    """S, A and E are excluded by quality/sql/analysis_set.sql, so they are
    never requested at all."""
    store_schedule(
        2024,
        [
            {"date": "2024-03-01", "game_type": "S"},
            {"date": "2024-03-02", "game_type": "E"},
            {"date": "2024-07-16", "game_type": "A"},
            {"date": "2024-10-01", "game_type": "D"},
        ],
    )
    assert runner.season_days(2024) == [dt.date(2024, 10, 1)]


def test_the_cutoff_is_2026_09_21_and_a_later_day_is_never_in_scope(lake):
    store_schedule(
        2026,
        [
            {"date": "2026-09-20"},
            {"date": "2026-09-21"},
            {"date": "2026-09-22"},
            {"date": "2026-09-28", "game_type": "F"},
        ],
    )
    assert runner.season_days(2026) == [dt.date(2026, 9, 20), paths.LAST_OPEN_DATE]
    assert sc.day_url(paths.LAST_OPEN_DATE).endswith(f"game_date_lt={paths.LAST_OPEN_DATE}")
    with pytest.raises(paths.SealViolation):
        sc.day_url("2026-09-22")


def test_newest_first_is_strictly_descending_and_deduplicated():
    days = [dt.date(2022, 4, 7), dt.date(2026, 9, 21), dt.date(2024, 5, 1), dt.date(2024, 5, 1)]
    ordered = runner.newest_first(days)
    assert ordered == [dt.date(2026, 9, 21), dt.date(2024, 5, 1), dt.date(2022, 4, 7)]
    assert all(a > b for a, b in itertools.pairwise(ordered))


def test_the_queue_is_newest_first(lake):
    days = season_span(2024, 6, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    assert runner.queue(seasons=[2024]) == sorted(days, reverse=True)


# ---------------------------------------------------------------------------
# Idempotence. A day that is already ours is never asked for again.
# ---------------------------------------------------------------------------


def test_a_day_already_in_the_lake_is_never_queued(lake):
    days = season_span(2024, 4, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    sc.store_day(one_good_day(days[-1]), days[-1])
    assert runner.done_days() == {days[-1]}
    assert days[-1] not in runner.queue(seasons=[2024])
    assert len(runner.queue(seasons=[2024])) == 3


def _write_manifest(lake: Path, records: list[dict]) -> Path:
    root = lake / "staging"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def _stage_csv(lake: Path, day: dt.date, *, level: str = "mlb") -> Path:
    path = lake / "staging" / "statcast" / level / str(day.year) / f"{day.isoformat()}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(one_good_day(day))
    return path


def test_a_day_the_staging_manifest_records_as_ok_is_subtracted(lake):
    day = dt.date(2024, 9, 30)
    path = _stage_csv(lake, day)
    _write_manifest(lake, [{"url": "x", "path": str(path), "status": 200, "ok": True, "rows": 1}])
    store_schedule(2024, [{"date": day.isoformat()}])
    assert runner.staging_ok_days() == {day}
    assert runner.queue(seasons=[2024]) == []


def test_a_staged_day_recorded_not_ok_is_still_queued(lake):
    day = dt.date(2024, 9, 30)
    path = _stage_csv(lake, day)
    _write_manifest(lake, [{"url": "x", "path": str(path), "status": 200, "ok": False, "rows": 0}])
    store_schedule(2024, [{"date": day.isoformat()}])
    assert runner.staging_ok_days() == set()
    assert runner.queue(seasons=[2024]) == [day]


def test_the_last_staging_record_for_a_day_wins(lake):
    """The real manifest holds three 2026 days saved under an early URL shape
    and marked not ok, re-pulled later in the same run and marked ok. The day
    is done, and asking for it again would spend a request for nothing."""
    day = dt.date(2026, 3, 25)
    path = _stage_csv(lake, day)
    _write_manifest(
        lake,
        [
            {"url": "old", "path": str(path), "status": 200, "ok": False, "rows": 0},
            {"url": "new", "path": str(path), "status": 200, "ok": True, "rows": 4427},
        ],
    )
    assert runner.staging_ok_days() == {day}


def test_a_staging_record_whose_file_is_gone_is_not_a_cached_day(lake):
    day = dt.date(2024, 9, 30)
    path = _stage_csv(lake, day)
    _write_manifest(lake, [{"url": "x", "path": str(path), "status": 200, "ok": True}])
    path.unlink()
    assert runner.staging_ok_days() == set()


def test_a_staging_record_for_another_level_is_not_subtracted(lake):
    day = dt.date(2024, 9, 30)
    path = _stage_csv(lake, day, level="aaa")
    _write_manifest(lake, [{"url": "x", "path": str(path), "status": 200, "ok": True}])
    assert runner.staging_ok_days(level="mlb") == set()
    assert runner.staging_ok_days(level="aaa") == {day}


def test_no_manifest_is_not_an_error(lake):
    assert runner.staging_ok_days() == set()


# ---------------------------------------------------------------------------
# The cap. Stop at it, never through it.
# ---------------------------------------------------------------------------


def test_the_chain_stops_at_the_cap_and_does_not_exceed_it(lake, stub):
    days = season_span(2024, 12, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    fake = stub(5)

    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert len(fake.days) == 5
    assert fake.used == 5 == fake.cap
    assert report.pulled == 5
    assert report.stop_reason == runner.STOP_DAILY_CAP
    assert report.queue_remaining == 7


def test_the_chain_takes_the_newest_days_first(lake, stub):
    days = season_span(2024, 12, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    fake = stub(5)

    runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert fake.days == sorted(days, reverse=True)[:5]
    assert all(a > b for a, b in itertools.pairwise(fake.days))


def test_a_spent_cap_asks_for_nothing(lake, stub):
    days = season_span(2024, 4, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    fake = stub(3)
    fake.used = 3

    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert fake.days == []
    assert report.attempted == 0
    assert report.stop_reason == runner.STOP_DAILY_CAP
    assert report.next_day == max(days)


def test_the_runner_stops_at_the_cap_without_waiting_to_be_refused(lake, stub):
    """The stop is the runner's own, not a rescue by the client.

    Here the stub would answer every day it is asked for -- its own ceiling is
    switched off -- and the budget says the cap is spent. Nothing but the
    runner's pre-flight check stands between the queue and 12 more day pulls,
    so if that check is removed this test is the one that fails.
    """
    days = season_span(2024, 12, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    fake = stub(6)
    fake.enforce_cap = False
    fake.used = 6

    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert fake.days == [], "the runner asked for a day with the cap already spent"
    assert report.attempted == 0
    assert report.stop_reason == runner.STOP_DAILY_CAP


def test_the_runner_stops_at_the_cap_partway_through_the_queue(lake, stub):
    """The same check, with part of the cap already spent by another step."""
    days = season_span(2024, 12, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    fake = stub(6)
    fake.enforce_cap = False
    fake.used = 2

    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert len(fake.days) == 4, "the runner spent more than the cap had left"
    assert fake.used == 6 == fake.cap
    assert report.stop_reason == runner.STOP_DAILY_CAP


def test_max_requests_stops_below_the_cap(lake, stub):
    days = season_span(2024, 12, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    fake = stub(800)

    report = runner.run(
        seasons=[2024],
        import_staging=False,
        max_requests=4,
        marker_path=marker_path(lake),
        stream=io.StringIO(),
    )

    assert len(fake.days) == 4
    assert report.stop_reason == runner.STOP_MAX_REQUESTS


def test_budget_exceeded_from_the_client_stops_the_chain_cleanly(lake, stub):
    """The client is the ceiling, not this runner's arithmetic. If the cap is
    spent between the check and the call, the chain stops; it does not retry
    and it does not treat the traceback as a plan."""
    days = season_span(2024, 6, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    fake = stub(800, trips_at=2)

    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert report.pulled == 2
    assert report.attempted == 2, "the refused day is not counted as a request"
    assert report.stop_reason == runner.STOP_DAILY_CAP
    assert len(fake.days) == 2


def test_the_cap_is_read_from_the_one_client_that_enforces_it(lake):
    """No cap literal in this runner. config/throttle.yml is the one source,
    and SOP section 5A item A3 is the one policy: Savant 800 a day."""
    state = runner.cap_state()
    config = yaml.safe_load(
        (Path(runner.__file__).resolve().parents[3] / "config" / "throttle.yml").read_text(
            encoding="utf-8"
        )
    )
    assert state.host == runner.savant_host()
    assert state.cap == client._daily_cap(state.host)
    assert state.cap == config["daily_request_budget"][state.host] == 800
    assert state.remaining == max(0, state.cap - state.used)


# ---------------------------------------------------------------------------
# Resume. Night two starts where night one stopped.
# ---------------------------------------------------------------------------


def test_an_interrupted_night_resumes_at_the_next_day(lake, stub):
    days = season_span(2024, 10, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    newest = sorted(days, reverse=True)

    first = stub(3)
    night_one = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )
    assert first.days == newest[:3]
    assert night_one.next_day == newest[3]

    marker = runner.read_marker(marker_path(lake))
    assert marker is not None, "night one wrote no resume marker"
    assert marker["next_day"] == newest[3].isoformat()
    assert marker["last_day_done"] == newest[2].isoformat()
    assert marker["stop_reason"] == runner.STOP_DAILY_CAP
    assert marker["queue_remaining"] == 7

    second = stub(800)
    night_two = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )
    assert second.days == newest[3:], "night two starts where night one stopped"
    assert night_two.stop_reason == runner.STOP_QUEUE_EMPTY
    assert night_two.next_day is None
    assert runner.queue(seasons=[2024]) == []


def test_the_resume_marker_round_trips(lake):
    payload = {"step": "W6.0", "next_day": "2022-10-05", "stop_reason": "daily-cap"}
    written = runner.write_marker(payload, marker_path(lake))
    assert runner.read_marker(written) == payload
    assert written.read_text(encoding="utf-8").endswith("\n")
    assert runner.read_marker(lake / "absent.json") is None


def test_the_marker_write_leaves_no_temporary_file(lake):
    written = runner.write_marker({"step": "W6.0"}, marker_path(lake))
    assert sorted(p.name for p in written.parent.iterdir()) == ["resume.json"]


def test_running_a_finished_night_again_costs_nothing_and_changes_no_bytes(lake, stub):
    days = season_span(2024, 4, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])

    first = stub(800)
    runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )
    assert len(first.days) == 4
    stored = {path: path.read_bytes() for _day, path in sc.raw_days()}
    assert len(stored) == 4

    second = stub(800)
    again = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert second.days == []
    assert again.attempted == 0
    assert again.stop_reason == runner.STOP_QUEUE_EMPTY
    assert {path: path.read_bytes() for _day, path in sc.raw_days()} == stored


# ---------------------------------------------------------------------------
# One sequential chain, never five parallel jobs
# ---------------------------------------------------------------------------


def test_a_second_chain_does_nothing(lake, stub):
    days = season_span(2024, 3, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    fake = stub(800)

    held = runner.take_lock()
    try:
        with pytest.raises(runner.ChainBusy):
            runner.run(
                seasons=[2024],
                import_staging=False,
                marker_path=marker_path(lake),
                stream=io.StringIO(),
            )
    finally:
        runner.release_lock(held)

    assert fake.days == [], "the second chain asked for nothing"


def test_the_lock_is_released_after_a_run(lake, stub):
    days = season_span(2024, 2, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    stub(800)
    runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )
    assert not runner.lock_path().exists()


def test_the_lock_is_released_when_the_run_raises(lake, stub, monkeypatch):
    days = season_span(2024, 2, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    stub(800)

    def explode(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(sc, "pull_day", explode)
    with pytest.raises(KeyboardInterrupt):
        runner.run(
            seasons=[2024],
            import_staging=False,
            marker_path=marker_path(lake),
            stream=io.StringIO(),
        )
    assert not runner.lock_path().exists()


# ---------------------------------------------------------------------------
# DT-01, DT-02 and UT-14 through the runner's own path
# ---------------------------------------------------------------------------


def test_dt01_a_day_at_the_row_cap_is_refused_and_not_stored(lake, stub):
    """25,000 rows is Savant's silent truncation, not a big day. The runner
    counts it as a failed day and stores nothing."""
    day = dt.date(2024, 9, 30)
    store_schedule(2024, [{"date": day.isoformat()}])

    def truncated(_day: dt.date) -> bytes:
        return synth_day([tracked_row(game_pk=str(800000 + i)) for i in range(sc.ROW_CAP)])

    stub(800, bodies=truncated)
    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert report.pulled == 0
    assert report.failed == 1
    assert sc.raw_days() == []
    assert "RowCapReached" in report.notes[0]


def test_dt01_a_day_under_the_cap_is_stored(lake, stub):
    day = dt.date(2024, 9, 30)
    store_schedule(2024, [{"date": day.isoformat()}])

    def wide(_day: dt.date) -> bytes:
        return synth_day([tracked_row(game_pk=str(800000 + i)) for i in range(sc.ROW_CAP - 1)])

    stub(800, bodies=wide)
    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert report.pulled == 1
    assert [d for d, _p in sc.raw_days()] == [day]


def test_dt02_a_drifted_header_is_refused(lake, stub):
    day = dt.date(2024, 9, 30)
    store_schedule(2024, [{"date": day.isoformat()}])
    columns = list(sc.contract_columns())
    columns[0] = "pitch_type_v2"

    def drifted(_day: dt.date) -> bytes:
        return synth_day([tracked_row()], columns=columns)

    stub(800, bodies=drifted)
    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert report.failed == 1
    assert sc.raw_days() == []
    assert "HeaderDrift" in report.notes[0]


def test_ut14_a_body_without_the_bom_is_refused(lake, stub):
    day = dt.date(2024, 9, 30)
    store_schedule(2024, [{"date": day.isoformat()}])

    stub(800, bodies=lambda d: synth_day([tracked_row()], bom=False))
    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert report.failed == 1
    assert "MissingBom" in report.notes[0]


def test_dt02_a_stored_day_carries_the_committed_header_digest(lake, stub):
    days = season_span(2024, 3, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    stub(800)
    runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    reports = sc.verify_lake(stream=io.StringIO())
    assert len(reports) == 3
    assert {r.header_sha256 for r in reports} == {sc.expected_header_sha256()}
    assert {r.n_columns for r in reports} == {sc.COLUMN_COUNT}
    assert all(r.n_rows < sc.ROW_CAP for r in reports)


def test_three_failures_in_a_row_stop_the_chain(lake, stub):
    """A drifted header fails every day after it too. The chain stops instead
    of spending the night's whole cap on one defect."""
    days = season_span(2024, 20, last=dt.date(2024, 9, 30))
    store_schedule(2024, [{"date": day.isoformat()} for day in days])
    columns = list(sc.contract_columns())
    columns[-1] = "renamed"

    fake = stub(800, bodies=lambda d: synth_day([tracked_row()], columns=columns))
    report = runner.run(
        seasons=[2024], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )

    assert report.failed == runner.MAX_CONSECUTIVE_FAILURES == 3
    assert len(fake.days) == 3
    assert report.stop_reason == runner.STOP_FAILURES


def test_a_sealed_day_is_never_requested_even_if_the_schedule_holds_one(lake, stub):
    store_schedule(
        2026,
        [{"date": "2026-09-21"}, {"date": "2026-09-22"}, {"date": "2026-09-23"}],
    )
    fake = stub(800)
    runner.run(
        seasons=[2026], import_staging=False, marker_path=marker_path(lake), stream=io.StringIO()
    )
    assert fake.days == [paths.LAST_OPEN_DATE]


# ---------------------------------------------------------------------------
# The SOP's two nights, checked against a full-size synthetic world
# ---------------------------------------------------------------------------


def test_night_one_puts_2023_to_2026_on_disk(lake, monkeypatch):
    """SOP section 10.1: "The Statcast day pull is ordered newest-first so
    2026, 2025, 2024 and 2023 are all on disk after night one." That is the
    claim the order exists to keep, so it is checked from an empty lake."""
    by_season = store_full_schedule()
    cap = client._daily_cap(runner.savant_host())
    the_plan = runner.plan()

    assert len(the_plan.days) == sum(len(days) for days in by_season.values()) == 908
    night_one = set(the_plan.queue[:cap])
    for season in (2023, 2024, 2025, 2026):
        missing = [day for day in by_season[season] if day not in night_one]
        assert missing == [], f"{season} is not complete after night one"
    night_two = the_plan.queue[cap:]
    assert {day.year for day in night_two} == {2022}
    assert the_plan.nights == 2


def test_the_derived_scope_agrees_with_the_sop_estimate(lake):
    store_full_schedule()
    total = len(runner.all_days())
    slack = int(runner.SOP_DAY_ESTIMATE * runner.SOP_DAY_TOLERANCE)
    assert runner.SOP_DAY_ESTIMATE == 920
    assert abs(total - runner.SOP_DAY_ESTIMATE) <= slack


# ---------------------------------------------------------------------------
# The check itself: green on a sound world, red on a broken one
# ---------------------------------------------------------------------------


def _sound_world(lake: Path) -> dict[int, list[dt.date]]:
    by_season = store_full_schedule()
    for day in by_season[2026][-5:]:
        sc.store_day(one_good_day(day), day)
    return by_season


def test_check_is_green_on_a_sound_world(lake):
    _sound_world(lake)
    assert runner.check(stream=io.StringIO()) == []


def test_check_is_red_when_the_order_is_reversed(lake, monkeypatch):
    """The mutation the whole step exists to prevent. If the runner pulls
    oldest-first, the verify command has to fail."""
    _sound_world(lake)
    monkeypatch.setattr(runner, "newest_first", lambda days: sorted(set(days)))
    failures = runner.check(stream=io.StringIO())
    assert failures, "an oldest-first queue passed the check"
    assert any(line.startswith("K-02") for line in failures)


def test_check_is_red_when_a_stored_day_is_queued_again(lake, monkeypatch):
    """Idempotence is an assertion, not a comment. A queue that forgot to
    subtract the lake has to turn the verify command red."""
    _sound_world(lake)
    monkeypatch.setattr(
        runner,
        "queue",
        lambda **kwargs: runner.newest_first(runner.all_days(kwargs.get("seasons"))),
    )
    failures = runner.check(stream=io.StringIO())
    assert any(line.startswith("K-03") for line in failures)


def test_check_is_red_on_an_empty_lake(lake):
    store_full_schedule()
    failures = runner.check(stream=io.StringIO())
    assert any(line.startswith("K-06") for line in failures), (
        "an empty lake must not pass: DT-01 and DT-02 would run on nothing"
    )


def test_check_is_red_when_a_stored_day_breaks_dt01(lake):
    by_season = _sound_world(lake)
    day = by_season[2025][-1]
    body = synth_day([tracked_row(game_pk=str(800000 + i)) for i in range(sc.ROW_CAP)])
    path = paths.raw_statcast("mlb", day.year, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zstandard.ZstdCompressor(level=10).compress(body))
    failures = runner.check(stream=io.StringIO())
    assert any(line.startswith("K-06") for line in failures)


def test_the_cli_refuses_to_do_anything_without_a_mode():
    assert runner.main([]) == 2


def test_the_cli_starts_no_pull_on_check_or_plan(lake, stub):
    store_full_schedule()
    fake = stub(800)
    assert runner.main(["--plan"]) == 0
    assert fake.days == [], "--plan sent a request"
