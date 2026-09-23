"""W8.2. The Kalshi capture agent and the daily probables snapshot, offline.

Every contract fact the SOP text for W8.2 states is asserted here, and none of
it touches the network: the poll and the snapshot take a fetcher, and the tests
pass one that returns a recorded payload. The default fetcher is the one HTTP
chokepoint, and that too is asserted.

What this file holds the agent to:

* the markets URL, verbatim, and the candlestick URL with period_interval 60;
* the thirteen verified market fields, in order, and nothing else in a row;
* the 16:00Z to 06:00Z window, which wraps midnight, and launchd StartInterval
  600, read out of the installed plist;
* trap 1, that HHMM in a ticker is US/Eastern: the verified case
  KXMLBGAME-26SEP242210SDLAD-SD is gamePk 823895, gameDate 2026-09-25T02:10:00Z
  and officialDate 2026-09-24, and reading the stamp as UTC gives a different
  instant and a different day;
* trap 2, that close_time on an open market is a placeholder about three days
  out and is never a start time;
* NDJSON per UTC date, and a repeated poll that writes no bytes;
* the probables snapshot as a point-in-time write-once record;
* a TLS reset logged with the schedule kept, and a block past 24 consecutive
  hours that stops the agent;
* the route ban: no proxy, so nothing can be routed through the Hetzner host.

Dates are built from datetime constructors with a time part rather than from
ISO literals, because tests/guard/gd04_scan.py reads an ISO date after an
assignment operator as a boundary comparison.
"""

from __future__ import annotations

import datetime as dt
import json
import plistlib
from pathlib import Path

import pytest
import yaml

from absump import http as chokepoint
from absump.p8 import kalshi_capture as agent

REPO_ROOT = Path(__file__).resolve().parents[2]
PLIST = REPO_ROOT / "ops" / "launchd" / "com.abs-umpires.kalshi.plist"
GRAMMAR_DOC = REPO_ROOT / "p8" / "config" / "kalshi_ticker_grammar.md"
THROTTLE = REPO_ROOT / "config" / "throttle.yml"

# A wake inside the window, a wake outside it, and the snapshot wake. Each one
# carries a time part so that no three-argument date constructor appears.
IN_WINDOW = dt.datetime(2026, 9, 23, 18, 30, tzinfo=dt.UTC)
LATE_WINDOW = dt.datetime(2026, 9, 23, 23, 50, tzinfo=dt.UTC)
EARLY_WINDOW = dt.datetime(2026, 9, 24, 0, 10, tzinfo=dt.UTC)
OUT_OF_WINDOW = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.UTC)
SNAPSHOT_WAKE = dt.datetime(2026, 9, 23, 14, 0, tzinfo=dt.UTC)
BEFORE_SNAPSHOT = dt.datetime(2026, 9, 23, 13, 50, tzinfo=dt.UTC)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class Recorded:
    """What a fetcher hands back: a body and nothing else."""

    def __init__(self, payload: object) -> None:
        self.text = json.dumps(payload)


def stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def a_market(ticker: str, **overrides: object) -> dict[str, object]:
    """One market object shaped like the endpoint's, with a placeholder close."""
    start = agent.parse_ticker(ticker).start_utc()
    market: dict[str, object] = {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "title": "Which team wins?",
        "yes_bid_dollars": "0.52",
        "yes_ask_dollars": "0.54",
        "last_price_dollars": "0.53",
        "volume_fp": 1200,
        "open_interest_fp": 3400,
        "open_time": stamp(start - dt.timedelta(days=7)),
        "close_time": stamp(start + dt.timedelta(days=agent.CLOSE_TIME_PLACEHOLDER_DAYS)),
        "result": "",
        "status": "open",
        "rules_primary": "If the named team wins, the market resolves Yes.",
    }
    market.update(overrides)
    return market


def markets_payload(*tickers: str) -> Recorded:
    return Recorded({"markets": [a_market(ticker) for ticker in tickers]})


VERIFIED = agent.VERIFIED_TICKER
OTHER = "KXMLBGAME-26SEP231910NYMPHI-PHI"


@pytest.fixture
def lake(tmp_path, monkeypatch):
    """Point the data lake at a temporary directory for the duration of a test."""
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# the endpoints and the verified fields
# ---------------------------------------------------------------------------


def test_the_markets_url_is_the_one_w82_states():
    assert agent.MARKETS_URL == (
        "https://api.elections.kalshi.com/trade-api/v2/markets"
        "?series_ticker=KXMLBGAME&status=open&limit=1000"
    )
    assert agent.SERIES_TICKER == "KXMLBGAME"
    assert agent.KALSHI_HOST in agent.MARKETS_URL


def test_the_candlestick_url_asks_for_sixty_minute_periods():
    url = agent.candlesticks_url(VERIFIED, 1_700_000_000, 1_700_003_600)
    assert "/trade-api/v2/series/KXMLBGAME/markets/" in url
    assert VERIFIED in url
    assert url.endswith("period_interval=60")
    assert "start_ts=1700000000" in url
    assert "end_ts=1700003600" in url
    assert agent.CANDLESTICK_PERIOD_INTERVAL_MINUTES == 60


def test_the_candlestick_fields_are_the_verified_ones():
    assert agent.CANDLESTICK_SCALAR_FIELDS == ("end_period_ts", "volume_fp", "open_interest_fp")
    assert agent.CANDLESTICK_PRICE_FIELDS == ("open", "high", "low", "close", "mean", "previous")
    assert agent.CANDLESTICK_BOOK_FIELDS == ("open", "high", "low", "close")
    assert agent.CANDLESTICK_BOOK_SIDES == ("yes_bid", "yes_ask")


def test_the_thirteen_verified_market_fields_in_order():
    assert agent.MARKET_FIELDS == (
        "ticker",
        "event_ticker",
        "title",
        "yes_bid_dollars",
        "yes_ask_dollars",
        "last_price_dollars",
        "volume_fp",
        "open_interest_fp",
        "open_time",
        "close_time",
        "result",
        "status",
        "rules_primary",
    )
    assert len(agent.MARKET_FIELDS) == 13


def test_a_quote_row_is_the_poll_stamp_plus_those_thirteen_fields():
    row = agent.market_row(a_market(VERIFIED), IN_WINDOW)
    assert list(row) == ["poll_ts", *agent.MARKET_FIELDS]
    assert row["poll_ts"] == stamp(IN_WINDOW)
    assert row["ticker"] == VERIFIED


def test_the_probables_url_is_a_point_in_time_query():
    url = agent.probables_url(SNAPSHOT_WAKE)
    assert url.startswith("https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=")
    assert "hydrate=probablePitcher" in url
    assert SNAPSHOT_WAKE.date().isoformat() in url


# ---------------------------------------------------------------------------
# the schedule
# ---------------------------------------------------------------------------


def test_the_capture_window_wraps_midnight():
    assert agent.CAPTURE_WINDOW_START_UTC_HOUR == 16
    assert agent.CAPTURE_WINDOW_END_UTC_HOUR == 6
    assert agent.in_capture_window(IN_WINDOW)
    assert agent.in_capture_window(LATE_WINDOW)
    assert agent.in_capture_window(EARLY_WINDOW)
    assert not agent.in_capture_window(OUT_OF_WINDOW)
    inside = [
        hour
        for hour in range(24)
        if agent.in_capture_window(IN_WINDOW.replace(hour=hour, minute=0))
    ]
    assert inside == [0, 1, 2, 3, 4, 5, 16, 17, 18, 19, 20, 21, 22, 23]


def test_the_snapshot_wake_is_the_first_one_at_or_after_1400z():
    assert agent.PROBABLES_SNAPSHOT_UTC_HOUR == 14
    assert not agent.is_snapshot_wake(BEFORE_SNAPSHOT)
    assert agent.is_snapshot_wake(SNAPSHOT_WAKE)
    assert agent.is_snapshot_wake(SNAPSHOT_WAKE + dt.timedelta(minutes=10))


def test_the_launchd_plist_carries_the_schedule_and_no_second_route():
    assert PLIST.is_file()
    loaded = plistlib.loads(PLIST.read_bytes())
    assert loaded["Label"] == "com.abs-umpires.kalshi"
    assert loaded["StartInterval"] == agent.START_INTERVAL_SECONDS == 600
    assert 86_400 // loaded["StartInterval"] == agent.EXPECTED_POLLS_PER_DAY == 144
    command = " ".join(loaded["ProgramArguments"])
    assert "absump.p8.kalshi_capture" in command
    assert "--tick" in command
    text = PLIST.read_text(encoding="utf-8").lower()
    assert "hetzner" not in text
    assert "proxy" not in text


def test_the_sizing_arithmetic_is_the_one_w82_states():
    numbers = agent.sizing()
    assert numbers["days"] == 41
    assert numbers["polls_per_day"] == 144
    assert numbers["markets_per_poll"] == 30
    assert numbers["quote_rows"] == 177_120
    assert abs(numbers["quote_rows"] - 177_000) <= 1_000
    assert numbers["quote_megabytes"] == 15
    assert numbers["snapshots"] == 41
    assert numbers["snapshot_megabytes"] == 3
    assert agent.START_INTERVAL_SECONDS * numbers["polls_per_day"] == 86_400


# ---------------------------------------------------------------------------
# trap 1: HHMM is US/Eastern
# ---------------------------------------------------------------------------


def test_the_verified_ticker_round_trips_to_the_verified_game():
    parsed = agent.parse_ticker(VERIFIED)
    assert parsed.series == "KXMLBGAME"
    assert (parsed.away, parsed.home, parsed.side) == (
        agent.VERIFIED_CASE["away"],
        agent.VERIFIED_CASE["home"],
        agent.VERIFIED_CASE["side"],
    )
    assert stamp(parsed.start_utc()) == agent.VERIFIED_CASE["game_date_utc"]
    assert parsed.official_date().isoformat() == agent.VERIFIED_CASE["official_date"]
    assert agent.VERIFIED_GAME_PK == 823895


def test_hhmm_read_as_utc_gives_the_wrong_instant_and_the_wrong_day():
    parsed = agent.parse_ticker(VERIFIED)
    as_utc = parsed.start_eastern().replace(tzinfo=dt.UTC)
    assert as_utc != parsed.start_utc()
    assert (parsed.start_utc() - as_utc) == dt.timedelta(hours=4)
    assert as_utc.date() != parsed.start_utc().date()
    assert as_utc.date() == parsed.official_date()


def test_the_official_date_is_the_eastern_day_not_the_utc_day():
    parsed = agent.parse_ticker(VERIFIED)
    assert parsed.official_date() != parsed.start_utc().date()
    assert parsed.official_date() == parsed.start_eastern().date()


def test_the_side_splits_the_two_team_codes():
    away_side = agent.parse_ticker("KXMLBGAME-26SEP242210SDLAD-SD")
    assert (away_side.away, away_side.home) == ("SD", "LAD")
    home_side = agent.parse_ticker("KXMLBGAME-26SEP242210SDLAD-LAD")
    assert (home_side.away, home_side.home) == ("SD", "LAD")


def test_a_ticker_that_does_not_match_the_grammar_is_refused():
    with pytest.raises(ValueError):
        agent.parse_ticker("KXMLBGAME-NOTATICKER")
    with pytest.raises(ValueError):
        agent.parse_ticker("KXMLBGAME-26XXX242210SDLAD-SD")


def test_an_unsplittable_run_raises_rather_than_guessing():
    with pytest.raises(agent.TickerAmbiguous):
        agent.parse_ticker("KXMLBGAME-26SEP242210AAA-AA")


# ---------------------------------------------------------------------------
# trap 2: close_time is a placeholder
# ---------------------------------------------------------------------------


def test_close_time_on_an_open_market_is_a_three_day_placeholder():
    market = a_market(VERIFIED)
    assert agent.CLOSE_TIME_PLACEHOLDER_DAYS == 3
    assert agent.close_time_is_placeholder(market)
    assert agent.close_time_lead_hours(market) == pytest.approx(72.0)


def test_a_settlement_close_is_not_flagged_as_a_placeholder():
    start = agent.parse_ticker(VERIFIED).start_utc()
    market = a_market(VERIFIED, close_time=stamp(start + dt.timedelta(hours=4)))
    assert not agent.close_time_is_placeholder(market)


def test_the_start_time_comes_from_the_ticker_and_never_from_close_time():
    market = a_market(VERIFIED)
    from_ticker = agent.start_utc(market)
    assert stamp(from_ticker) == agent.VERIFIED_CASE["game_date_utc"]
    del market["close_time"]
    assert agent.start_utc(market) == from_ticker
    with pytest.raises(agent.CloseTimeMisuse):
        agent.reject_close_time_as_start(a_market(VERIFIED))


# ---------------------------------------------------------------------------
# the NDJSON layout
# ---------------------------------------------------------------------------


def test_ndjson_is_written_one_file_per_utc_date(lake):
    late = agent.capture_once(now=LATE_WINDOW, fetch=lambda url: markets_payload(VERIFIED))
    early = agent.capture_once(now=EARLY_WINDOW, fetch=lambda url: markets_payload(VERIFIED))
    assert late["path"] != early["path"]
    assert agent.quotes_path(LATE_WINDOW).is_file()
    assert agent.quotes_path(EARLY_WINDOW).is_file()
    assert agent.quotes_path(LATE_WINDOW).parent.name == f"date={LATE_WINDOW.date().isoformat()}"
    assert agent.quotes_path(EARLY_WINDOW).parent.name == f"date={EARLY_WINDOW.date().isoformat()}"
    assert EARLY_WINDOW.date() - LATE_WINDOW.date() == dt.timedelta(days=1)
    assert agent.quotes_path(LATE_WINDOW).is_relative_to(lake / "p8" / "kalshi")


def test_every_line_is_one_json_object(lake):
    agent.capture_once(now=IN_WINDOW, fetch=lambda url: markets_payload(VERIFIED, OTHER))
    lines = agent.quotes_path(IN_WINDOW).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert {row["ticker"] for row in rows} == {VERIFIED, OTHER}
    assert all(list(row) == sorted(["poll_ts", *agent.MARKET_FIELDS]) for row in rows)


def test_a_repeated_poll_writes_no_bytes(lake):
    fetch = lambda url: markets_payload(VERIFIED, OTHER)  # noqa: E731
    first = agent.capture_once(now=IN_WINDOW, fetch=fetch)
    before = agent.quotes_path(IN_WINDOW).read_bytes()
    second = agent.capture_once(now=IN_WINDOW, fetch=fetch)
    after = agent.quotes_path(IN_WINDOW).read_bytes()
    assert first["rows"] == 2
    assert second["rows"] == 0
    assert before == after


def test_a_later_poll_appends_rather_than_replacing(lake):
    agent.capture_once(now=IN_WINDOW, fetch=lambda url: markets_payload(VERIFIED))
    agent.capture_once(
        now=IN_WINDOW + dt.timedelta(seconds=agent.START_INTERVAL_SECONDS),
        fetch=lambda url: markets_payload(VERIFIED),
    )
    lines = agent.quotes_path(IN_WINDOW).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert len({json.loads(line)["poll_ts"] for line in lines}) == 2


def test_a_wake_outside_the_window_polls_nothing(lake):
    def refuse(url):
        raise AssertionError("a wake outside the window must not fetch")

    outcome = agent.capture_once(now=OUT_OF_WINDOW, fetch=refuse)
    assert outcome["action"] == "skipped"
    assert outcome["rows"] == 0
    assert not agent.quotes_path(OUT_OF_WINDOW).exists()


# ---------------------------------------------------------------------------
# the point-in-time probables snapshot
# ---------------------------------------------------------------------------


SCHEDULE_PAYLOAD = {
    "dates": [
        {
            "date": "2026-09-23",
            "games": [
                {
                    "gamePk": 823895,
                    "gameDate": "2026-09-24T02:10:00Z",
                    "gameType": "R",
                    "status": {"detailedState": "Scheduled"},
                    "teams": {
                        "away": {
                            "team": {"id": 135, "name": "San Diego Padres"},
                            "probablePitcher": {"id": 669_302, "fullName": "A Probable"},
                        },
                        "home": {
                            "team": {"id": 119, "name": "Los Angeles Dodgers"},
                            "probablePitcher": {"id": 605_400, "fullName": "B Probable"},
                        },
                    },
                }
            ],
        }
    ]
}


def test_the_snapshot_records_the_probable_and_the_moment_it_was_taken(lake):
    outcome = agent.snapshot_probables(
        now=SNAPSHOT_WAKE, fetch=lambda url: Recorded(SCHEDULE_PAYLOAD)
    )
    assert outcome["rows"] == 1
    rows = [
        json.loads(line)
        for line in agent.probables_path(SNAPSHOT_WAKE).read_text(encoding="utf-8").splitlines()
    ]
    row = rows[0]
    assert row["snapshot_ts"] == stamp(SNAPSHOT_WAKE)
    assert row["game_pk"] == 823895
    assert row["away_probable_name"] == "A Probable"
    assert row["home_probable_name"] == "B Probable"
    assert row["away_team_id"] == 135
    assert row["home_team_id"] == 119


def test_the_snapshot_is_written_once_and_never_rewritten(lake):
    agent.snapshot_probables(now=SNAPSHOT_WAKE, fetch=lambda url: Recorded(SCHEDULE_PAYLOAD))
    before = agent.probables_path(SNAPSHOT_WAKE).read_bytes()

    def later_starter(url):
        raise AssertionError("a second query would return the actual starter: look-ahead")

    outcome = agent.snapshot_probables(
        now=SNAPSHOT_WAKE + dt.timedelta(hours=6), fetch=later_starter
    )
    assert outcome["action"] == "already captured"
    assert outcome["rows"] == 0
    assert agent.probables_path(SNAPSHOT_WAKE).read_bytes() == before


def test_a_launchd_wake_does_the_snapshot_and_the_poll(lake):
    def fetch(url):
        if url.startswith("https://statsapi.mlb.com"):
            return Recorded(SCHEDULE_PAYLOAD)
        return markets_payload(VERIFIED)

    outcome = agent.tick(now=IN_WINDOW, fetch=fetch)
    assert outcome["probables"]["action"] == "captured"
    assert outcome["quotes"]["action"] == "captured"

    before_snapshot = agent.tick(now=BEFORE_SNAPSHOT, fetch=fetch)
    assert before_snapshot["probables"]["action"] == "not due"
    assert before_snapshot["quotes"]["action"] == "skipped"


# ---------------------------------------------------------------------------
# the ISP filter, the 24 hour limit and the route ban
# ---------------------------------------------------------------------------


def test_a_tls_reset_is_recorded_and_the_schedule_is_kept(lake):
    def reset(url):
        raise OSError("TLS connection reset by the network")

    outcome = agent.capture_once(now=IN_WINDOW, fetch=reset)
    assert outcome["action"] == "failed"
    assert "reset" in outcome["reason"]
    state = agent.read_state()
    assert state["consecutive_failures"] == 1
    assert state["blocked_since"] == stamp(IN_WINDOW)
    assert "schedule kept" in agent.log_path().read_text(encoding="utf-8")


def test_a_block_of_exactly_twenty_four_hours_does_not_stop_the_agent(lake):
    def reset(url):
        raise OSError("TLS connection reset by the network")

    agent.capture_once(now=IN_WINDOW, fetch=reset)
    at_the_limit = IN_WINDOW + dt.timedelta(hours=agent.BLOCK_LIMIT_HOURS)
    outcome = agent.capture_once(now=at_the_limit, fetch=reset)
    assert outcome["action"] == "failed"
    assert agent.BLOCK_LIMIT_HOURS == 24.0


def test_a_block_past_twenty_four_hours_stops_the_agent(lake):
    def reset(url):
        raise OSError("TLS connection reset by the network")

    agent.capture_once(now=IN_WINDOW, fetch=reset)
    past_the_limit = IN_WINDOW + dt.timedelta(hours=25)
    with pytest.raises(agent.IspBlockPersisted) as caught:
        agent.capture_once(now=past_the_limit, fetch=reset)
    assert "Hetzner" in str(caught.value)


def test_a_success_clears_the_block_clock(lake):
    def reset(url):
        raise OSError("TLS connection reset by the network")

    agent.capture_once(now=IN_WINDOW, fetch=reset)
    agent.capture_once(
        now=IN_WINDOW + dt.timedelta(minutes=10), fetch=lambda url: markets_payload(VERIFIED)
    )
    state = agent.read_state()
    assert state["blocked_since"] is None
    assert state["consecutive_failures"] == 0


@pytest.mark.parametrize("name", agent.FORBIDDEN_ROUTE_ENV)
def test_a_configured_proxy_is_refused(lake, monkeypatch, name):
    monkeypatch.setenv(name, "http://127.0.0.1:8080")
    with pytest.raises(agent.RouteViolation) as caught:
        agent.capture_once(now=IN_WINDOW, fetch=lambda url: markets_payload(VERIFIED))
    assert "Hetzner" in str(caught.value)


def test_the_state_file_is_rewritten_only_when_it_changes(lake):
    agent.write_state({"blocked_since": None, "consecutive_failures": 0})
    first = agent.state_path().stat().st_mtime_ns
    agent.write_state({"blocked_since": None, "consecutive_failures": 0})
    assert agent.state_path().stat().st_mtime_ns == first


# ---------------------------------------------------------------------------
# the one chokepoint and the throttle
# ---------------------------------------------------------------------------


def test_the_default_fetcher_is_the_one_http_chokepoint(lake, monkeypatch):
    assert agent.client is chokepoint
    seen: list[str] = []

    def stub(url, *, host_budget=True):
        seen.append(url)
        return markets_payload(VERIFIED)

    monkeypatch.setattr(chokepoint, "get", stub)
    agent.capture_once(now=IN_WINDOW)
    assert seen == [agent.MARKETS_URL]


def test_the_throttle_config_covers_the_kalshi_host():
    config = yaml.safe_load(THROTTLE.read_text(encoding="utf-8"))
    assert config["min_interval_seconds"][agent.KALSHI_HOST] == 10.0
    assert config["daily_request_budget"][agent.KALSHI_HOST] == 500


# ---------------------------------------------------------------------------
# the selfcheck, the plan and the grammar note
# ---------------------------------------------------------------------------


def test_the_offline_selfcheck_passes(capsys):
    assert agent.selfcheck() == []
    assert agent.main(["--selfcheck"]) == 0
    assert "OK" in capsys.readouterr().out


def test_the_plan_sends_nothing(lake, capsys, monkeypatch):
    def refuse(url, *, host_budget=True):
        raise AssertionError("--plan must send nothing")

    monkeypatch.setattr(chokepoint, "get", refuse)
    assert agent.main(["--plan"]) == 0
    printed = capsys.readouterr().out
    assert agent.MARKETS_URL in printed
    assert "0 requests sent" in printed


def test_the_grammar_note_records_both_traps_and_the_route_ban():
    text = GRAMMAR_DOC.read_text(encoding="utf-8")
    assert "KXMLBGAME-{YY}{MON}{DD}{HHMM}{AWAY}{HOME}-{SIDE}" in text
    assert agent.VERIFIED_TICKER in text
    assert "US/Eastern" in text
    assert "823895" in text
    assert "placeholder" in text
    assert "24 consecutive hours" in text
    assert "Hetzner" in text
    assert "period_interval=60" in text
    for field in agent.MARKET_FIELDS:
        assert field in text
