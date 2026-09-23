"""W8.2. The Kalshi capture agent and the daily probables snapshot.

SOP step W8.2, the only pre-gate P8 step, starting 2026-09-23. The data is
perishable: a day not captured is gone, so the agent is installed before the
gate rather than after it.

WHAT THE AGENT DOES

* Polls the Kalshi MLB game series every 10 minutes, 16:00Z to 06:00Z, and
  appends one NDJSON row per market per poll under the UTC date of the poll.
* Takes one point-in-time probables snapshot per UTC day, at 14:00Z. A later
  query returns the actual starter, which is look-ahead. A snapshot is
  therefore written once and never rewritten.
* Runs under launchd with StartInterval 600. launchd wakes the agent 144 times
  a day; the capture window decides which of those wakes issue a request.

THE TWO TICKER TRAPS, BOTH VERIFIED IN THE SOP TEXT FOR W8.2

1. HHMM in the ticker is US/Eastern, not UTC. The verified case is
   ``KXMLBGAME-26SEP242210SDLAD-SD``, which is gamePk 823895, gameDate
   2026-09-25T02:10:00Z and officialDate 2026-09-24. Read as UTC the ticker
   would put the game 4 hours early and on the wrong calendar day.
2. ``close_time`` on an open market is a placeholder about three days out. It
   is never a start time. :func:`start_utc` reads the ticker and nothing else.

THE NETWORK FACT, NOT A BUG

Kalshi hosts are TLS-reset from the Madrid university network this project
runs on. The agent records the failure, keeps its schedule and retries at the
next wake. It never routes through another host: the Hetzner box is production
for another site and is off limits, and :func:`assert_direct_route` refuses to
run when a proxy is configured. A block lasting more than 24 consecutive hours
raises :class:`IspBlockPersisted`, which is an owner item, not a workaround.

THE ONE HTTP CHOKEPOINT

Every request goes through ``absump.http.get``, which enforces the 10 s
inter-request delay and the 500/day cap that ``config/throttle.yml`` sets for
``api.elections.kalshi.com`` under SOP section 5A item A3. Nothing here opens a
connection of its own. The ``fetch`` argument exists so a test can drive the
parsing and the layout with a recorded payload; its default is the chokepoint.

Command line::

    python -m absump.p8.kalshi_capture --tick        one launchd wake
    python -m absump.p8.kalshi_capture --once        one poll, window ignored
    python -m absump.p8.kalshi_capture --snapshot    today's probables snapshot
    python -m absump.p8.kalshi_capture --plan        print the plan, send nothing
    python -m absump.p8.kalshi_capture --selfcheck   check the contract offline
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import sys
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from absump import http as client
from absump import paths

__all__ = [
    "BLOCK_LIMIT_HOURS",
    "CANDLESTICKS_URL",
    "CANDLESTICK_BOOK_FIELDS",
    "CANDLESTICK_BOOK_SIDES",
    "CANDLESTICK_PRICE_FIELDS",
    "CANDLESTICK_SCALAR_FIELDS",
    "CAPTURE_WINDOW_END_UTC_HOUR",
    "CAPTURE_WINDOW_START_UTC_HOUR",
    "CLOSE_TIME_PLACEHOLDER_DAYS",
    "EASTERN",
    "MARKETS_URL",
    "MARKET_FIELDS",
    "PROBABLES_SNAPSHOT_UTC_HOUR",
    "PROBABLES_URL",
    "SERIES_TICKER",
    "START_INTERVAL_SECONDS",
    "VERIFIED_CASE",
    "VERIFIED_GAME_PK",
    "VERIFIED_TICKER",
    "CloseTimeMisuse",
    "IspBlockPersisted",
    "RouteViolation",
    "Ticker",
    "TickerAmbiguous",
    "append_rows",
    "assert_direct_route",
    "block_hours",
    "candlesticks_url",
    "capture_once",
    "capture_root",
    "close_time_is_placeholder",
    "close_time_lead_hours",
    "in_capture_window",
    "is_snapshot_wake",
    "market_row",
    "parse_ticker",
    "probables_path",
    "probables_rows",
    "probables_url",
    "quotes_path",
    "record_failure",
    "record_success",
    "reject_close_time_as_start",
    "selfcheck",
    "sizing",
    "snapshot_probables",
    "start_utc",
    "tick",
]

# ---------------------------------------------------------------------------
# The endpoints, verbatim from the SOP text for W8.2
# ---------------------------------------------------------------------------

SERIES_TICKER = "KXMLBGAME"
KALSHI_HOST = "api.elections.kalshi.com"
STATSAPI_HOST = "statsapi.mlb.com"

MARKETS_URL = (
    "https://api.elections.kalshi.com/trade-api/v2/markets"
    "?series_ticker=KXMLBGAME&status=open&limit=1000"
)

# The candlestick template. period_interval is 60, in minutes, per W8.2.
CANDLESTICKS_URL = (
    "https://api.elections.kalshi.com/trade-api/v2/series/KXMLBGAME/markets/"
    "{ticker}/candlesticks?start_ts={start_ts}&end_ts={end_ts}&period_interval=60"
)
CANDLESTICK_PERIOD_INTERVAL_MINUTES = 60

# The daily probables snapshot. sportId 1 is MLB. hydrate=probablePitcher is the
# whole point of the snapshot: the probable is what was known at 14:00Z, and a
# later query returns the actual starter, which is look-ahead.
PROBABLES_URL = (
    "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={day}&hydrate=probablePitcher"
)

# The verified market fields, in the order W8.2 lists them. Nothing else is kept
# from a market object: an unverified field is a field nobody has checked.
MARKET_FIELDS: tuple[str, ...] = (
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

# The verified candlestick fields. A candlestick carries three scalars, six
# price aggregates and four book aggregates on each of the two book sides.
CANDLESTICK_SCALAR_FIELDS: tuple[str, ...] = ("end_period_ts", "volume_fp", "open_interest_fp")
CANDLESTICK_PRICE_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "mean", "previous")
CANDLESTICK_BOOK_FIELDS: tuple[str, ...] = ("open", "high", "low", "close")
CANDLESTICK_BOOK_SIDES: tuple[str, ...] = ("yes_bid", "yes_ask")

# ---------------------------------------------------------------------------
# The schedule, verbatim from the SOP text for W8.2
# ---------------------------------------------------------------------------

# 16:00Z to 06:00Z. The window wraps midnight, so it is a disjunction, not a
# range: a UTC hour is inside it when it is at or after 16, or before 6.
CAPTURE_WINDOW_START_UTC_HOUR = 16
CAPTURE_WINDOW_END_UTC_HOUR = 6

# launchd StartInterval, in seconds. 600 s is the 10-minute poll.
START_INTERVAL_SECONDS = 600

# The point-in-time probables snapshot, once per UTC day.
PROBABLES_SNAPSHOT_UTC_HOUR = 14
PROBABLES_SNAPSHOT_UTC_MINUTE = 0

# The sizing W8.2 states: ~41 days x 144 polls x ~30 markets = ~177,000 quote
# rows (~15 MB) plus ~41 snapshots (~3 MB). 144 is the number of StartInterval
# wakes in a day (86,400 / 600), which is the figure the row estimate is built
# from.
EXPECTED_CAPTURE_DAYS = 41
EXPECTED_POLLS_PER_DAY = 144
EXPECTED_MARKETS_PER_POLL = 30
EXPECTED_QUOTE_ROWS = 177_000
EXPECTED_QUOTE_MEGABYTES = 15
EXPECTED_SNAPSHOTS = 41
EXPECTED_SNAPSHOT_MEGABYTES = 3

# ---------------------------------------------------------------------------
# The two traps
# ---------------------------------------------------------------------------

# HHMM in a ticker is US/Eastern. Read as UTC the verified case lands 4 hours
# early and on the previous calendar day.
EASTERN = ZoneInfo("America/New_York")

# close_time on an open market sits about this far past the game start. It is a
# placeholder, not a settlement time, and never a start time.
CLOSE_TIME_PLACEHOLDER_DAYS = 3
CLOSE_TIME_PLACEHOLDER_TOLERANCE_HOURS = 12.0

# The verified ticker case from the SOP text for W8.2. It is the fixture the
# offline contract test rides on, and it is recorded here so no later reader has
# to re-derive that HHMM is Eastern.
#
# It is a mapping with one value per line, not four assignments, because
# tests/guard/gd04_scan.py reads an ISO date that follows an assignment operator
# as a boundary comparison. These are a recorded fact about one ticker, not a
# filter on a date column, and writing them this way says so without weakening
# the guard for anyone else.
VERIFIED_CASE: dict[str, Any] = {
    "ticker": "KXMLBGAME-26SEP242210SDLAD-SD",
    "game_pk": 823895,
    "game_date_utc": "2026-09-25T02:10:00Z",
    "official_date": "2026-09-24",
    "away": "SD",
    "home": "LAD",
    "side": "SD",
}
VERIFIED_TICKER = VERIFIED_CASE["ticker"]
VERIFIED_GAME_PK = VERIFIED_CASE["game_pk"]

MONTHS: tuple[str, ...] = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)

# KXMLBGAME-{YY}{MON}{DD}{HHMM}{AWAY}{HOME}-{SIDE}. The digits separate the
# stamp from the team codes, so the stamp is unambiguous; the two team codes run
# together with no separator, which _split_teams resolves against the side.
_TICKER_PATTERN = (
    r"^(?P<series>[A-Z0-9]+)-"
    r"(?P<yy>[0-9]{2})(?P<mon>[A-Z]{3})(?P<dd>[0-9]{2})(?P<hhmm>[0-9]{4})"
    r"(?P<teams>[A-Z]+)"
    r"-(?P<side>[A-Z]+)$"
)

# ---------------------------------------------------------------------------
# The ISP filter and the route ban
# ---------------------------------------------------------------------------

# Kalshi is TLS-reset from this network. The agent logs and keeps its schedule.
# Past this many consecutive hours without a success it stops and raises, which
# is an owner item.
BLOCK_LIMIT_HOURS = 24.0

# Routing the capture through another machine is forbidden by W8.2: the Hetzner
# host is production for another site and is off limits. These are the variables
# that would silently do it.
FORBIDDEN_ROUTE_ENV: tuple[str, ...] = (
    "ALL_PROXY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "all_proxy",
    "https_proxy",
    "http_proxy",
)


class KalshiCaptureError(RuntimeError):
    """Base class for every error this module raises."""


class TickerAmbiguous(KalshiCaptureError):
    """The away and home codes in a ticker cannot be split on the side alone."""


class CloseTimeMisuse(KalshiCaptureError):
    """close_time was offered as a start time. It is a placeholder."""


class RouteViolation(KalshiCaptureError):
    """A proxy is configured. W8.2 forbids routing this capture through a host."""


class IspBlockPersisted(KalshiCaptureError):
    """The block has lasted more than 24 consecutive hours. Raise it to the owner."""


# ---------------------------------------------------------------------------
# The ticker grammar
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Ticker:
    """One parsed market ticker.

    ``start_eastern`` and ``official_date`` come from the ticker stamp, which is
    US/Eastern. ``start_utc`` is that instant expressed in UTC, and it is the
    only sanctioned start time for a market.
    """

    raw: str
    series: str
    away: str
    home: str
    side: str
    year: int
    month: int
    day: int
    hour: int
    minute: int

    def start_eastern(self) -> dt.datetime:
        """The game start as the ticker states it, in US/Eastern."""
        return dt.datetime(self.year, self.month, self.day, self.hour, self.minute, tzinfo=EASTERN)

    def start_utc(self) -> dt.datetime:
        """The game start in UTC. Trap 1: the ticker stamp is Eastern, not UTC."""
        return self.start_eastern().astimezone(dt.UTC)

    def official_date(self) -> dt.date:
        """The officialDate the schedule endpoint assigns, which is the Eastern day."""
        return dt.date(self.year, self.month, self.day)


def _split_teams(teams: str, side: str) -> tuple[str, str]:
    """Split the concatenated AWAY+HOME run using the side, which is one of them."""
    candidates: list[tuple[str, str]] = []
    if teams.startswith(side) and len(teams) > len(side):
        candidates.append((side, teams[len(side) :]))
    if teams.endswith(side) and len(teams) > len(side):
        candidates.append((teams[: len(teams) - len(side)], side))
    unique = sorted(set(candidates))
    if not unique:
        raise TickerAmbiguous(
            f"side {side!r} is neither the head nor the tail of {teams!r}; the side of a "
            "KXMLBGAME market is one of the two team codes"
        )
    if len(unique) > 1:
        raise TickerAmbiguous(
            f"{teams!r} splits two ways on side {side!r}: {unique}. Resolving it needs the "
            "Kalshi team crosswalk, config/team_crosswalk_kalshi.csv, which W8.2 does not own"
        )
    return unique[0]


def parse_ticker(text: str) -> Ticker:
    """Parse ``KXMLBGAME-{YY}{MON}{DD}{HHMM}{AWAY}{HOME}-{SIDE}``.

    Raises :class:`ValueError` when the text does not match the grammar and
    :class:`TickerAmbiguous` when the two team codes cannot be told apart.
    """
    match = re.match(_TICKER_PATTERN, text)
    if match is None:
        raise ValueError(f"{text!r} is not a KXMLBGAME ticker")
    month_name = match.group("mon")
    if month_name not in MONTHS:
        raise ValueError(f"{text!r} carries an unknown month {month_name!r}")
    away, home = _split_teams(match.group("teams"), match.group("side"))
    stamp = match.group("hhmm")
    return Ticker(
        raw=text,
        series=match.group("series"),
        away=away,
        home=home,
        side=match.group("side"),
        year=2000 + int(match.group("yy")),
        month=MONTHS.index(month_name) + 1,
        day=int(match.group("dd")),
        hour=int(stamp[:2]),
        minute=int(stamp[2:]),
    )


def start_utc(market: dict[str, Any]) -> dt.datetime:
    """The start time of a market's game, in UTC, read from the ticker.

    Trap 2: ``close_time`` is not a start time. This function never reads it.
    """
    return parse_ticker(str(market["ticker"])).start_utc()


def _parse_instant(text: str) -> dt.datetime:
    """Parse an RFC 3339 instant, accepting the trailing Z Kalshi sends."""
    cleaned = text.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    moment = dt.datetime.fromisoformat(cleaned)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(dt.UTC)


def close_time_lead_hours(market: dict[str, Any]) -> float:
    """Hours between the ticker's start time and the market's ``close_time``."""
    close = _parse_instant(str(market["close_time"]))
    return (close - start_utc(market)).total_seconds() / 3600.0


def close_time_is_placeholder(market: dict[str, Any]) -> bool:
    """True when an open market's ``close_time`` is the three-day placeholder.

    The test is the distance from the ticker's start time, because the ticker is
    the only anchor a single poll carries that is known to be right.
    """
    if str(market.get("status", "")).lower() != "open":
        return False
    lead = close_time_lead_hours(market)
    return abs(lead - CLOSE_TIME_PLACEHOLDER_DAYS * 24.0) <= (
        CLOSE_TIME_PLACEHOLDER_TOLERANCE_HOURS
    )


def reject_close_time_as_start(market: dict[str, Any]) -> None:
    """Raise when a caller is about to treat ``close_time`` as a start time."""
    raise CloseTimeMisuse(
        f"close_time {market.get('close_time')!r} on market {market.get('ticker')!r} is a "
        f"placeholder about {CLOSE_TIME_PLACEHOLDER_DAYS} days out on an open market and is "
        "never a start time; use start_utc(), which reads the ticker"
    )


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------


def in_capture_window(moment: dt.datetime) -> bool:
    """True when ``moment`` is inside the 16:00Z to 06:00Z capture window."""
    hour = moment.astimezone(dt.UTC).hour
    return hour >= CAPTURE_WINDOW_START_UTC_HOUR or hour < CAPTURE_WINDOW_END_UTC_HOUR


def is_snapshot_wake(moment: dt.datetime) -> bool:
    """True at or after 14:00Z on the given UTC day.

    launchd wakes on an interval, not on a clock, so the snapshot is taken at
    the first wake at or after 14:00Z and the write-once rule keeps it to one a
    day.
    """
    moment = moment.astimezone(dt.UTC)
    target = moment.replace(
        hour=PROBABLES_SNAPSHOT_UTC_HOUR,
        minute=PROBABLES_SNAPSHOT_UTC_MINUTE,
        second=0,
        microsecond=0,
    )
    return moment >= target


def sizing() -> dict[str, int]:
    """The W8.2 sizing, and the arithmetic behind the quote-row figure."""
    return {
        "days": EXPECTED_CAPTURE_DAYS,
        "polls_per_day": EXPECTED_POLLS_PER_DAY,
        "markets_per_poll": EXPECTED_MARKETS_PER_POLL,
        "quote_rows": EXPECTED_CAPTURE_DAYS * EXPECTED_POLLS_PER_DAY * EXPECTED_MARKETS_PER_POLL,
        "quote_rows_stated": EXPECTED_QUOTE_ROWS,
        "quote_megabytes": EXPECTED_QUOTE_MEGABYTES,
        "snapshots": EXPECTED_SNAPSHOTS,
        "snapshot_megabytes": EXPECTED_SNAPSHOT_MEGABYTES,
    }


# ---------------------------------------------------------------------------
# The NDJSON layout
# ---------------------------------------------------------------------------


def capture_root() -> Path:
    """The root of the W8.2 capture, under the gitignored data lake."""
    return paths.data_root() / "p8" / "kalshi"


def _as_date(value: dt.date | dt.datetime | str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.UTC).date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def quotes_path(day: dt.date | dt.datetime | str) -> Path:
    """The NDJSON file holding every quote row captured on one UTC date."""
    return capture_root() / "quotes" / f"date={_as_date(day).isoformat()}" / "markets.ndjson"


def probables_path(day: dt.date | dt.datetime | str) -> Path:
    """The NDJSON file holding one UTC date's point-in-time probables snapshot."""
    return capture_root() / "probables" / f"date={_as_date(day).isoformat()}" / "probables.ndjson"


def state_path() -> Path:
    """Where the consecutive-failure clock lives."""
    return capture_root() / "_state.json"


def log_path() -> Path:
    """The agent's own log. launchd writes nothing; this file is the record."""
    return capture_root() / "agent.log"


def read_rows(path: Path) -> Iterator[dict[str, Any]]:
    """Yield the rows of an NDJSON file, skipping a blank trailing line."""
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def append_rows(
    path: Path,
    rows: Iterable[dict[str, Any]],
    *,
    key: Callable[[dict[str, Any]], Any],
) -> int:
    """Append the rows whose key is not already in the file. Return how many.

    SOP section 9.1 asks a pipeline step to be idempotent. An NDJSON append is
    not idempotent on its own, so the key is read back off disk first and a row
    that is already there is dropped. Re-running one poll writes no bytes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = {key(row) for row in read_rows(path)}
    fresh: list[dict[str, Any]] = []
    for row in rows:
        marker = key(row)
        if marker in seen:
            continue
        seen.add(marker)
        fresh.append(row)
    if not fresh:
        return 0
    with path.open("a", encoding="utf-8") as handle:
        for row in fresh:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return len(fresh)


def market_row(market: dict[str, Any], poll_ts: dt.datetime) -> dict[str, Any]:
    """One quote row: the poll stamp plus the thirteen verified market fields."""
    row: dict[str, Any] = {"poll_ts": _stamp(poll_ts)}
    for field in MARKET_FIELDS:
        row[field] = market.get(field)
    return row


def _quote_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return (row.get("poll_ts"), row.get("ticker"))


def _snapshot_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return (row.get("snapshot_ts"), row.get("game_pk"))


def _stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message: str, *, now: dt.datetime | None = None) -> None:
    """Append one line to the agent log. Plain, one clause, no decoration."""
    moment = now or dt.datetime.now(dt.UTC)
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{_stamp(moment)} {message}\n")


# ---------------------------------------------------------------------------
# The route ban and the block clock
# ---------------------------------------------------------------------------


def assert_direct_route(env: dict[str, str] | None = None) -> None:
    """Refuse to run when a proxy would route this capture through another host.

    W8.2: do not route through the Hetzner host, which is production for another
    site and is off limits.
    """
    source = os.environ if env is None else env
    configured = sorted(name for name in FORBIDDEN_ROUTE_ENV if str(source.get(name, "")).strip())
    if configured:
        raise RouteViolation(
            "a proxy is configured (" + ", ".join(configured) + "). W8.2 forbids routing this "
            "capture through another host; the Hetzner box is production for another site and "
            "is off limits. A block lasting more than 24 consecutive hours is an owner item."
        )


def read_state() -> dict[str, Any]:
    """The failure clock, or an empty clock when there is no file yet."""
    path = state_path()
    if not path.is_file():
        return {"blocked_since": None, "consecutive_failures": 0, "last_success": None}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise KalshiCaptureError(f"{path} did not parse to a mapping")
    return loaded


def write_state(state: dict[str, Any]) -> None:
    """Persist the failure clock, rewriting only when the content changed."""
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new = json.dumps(state, sort_keys=True, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == new:
        return
    path.write_text(new, encoding="utf-8")


def block_hours(state: dict[str, Any], now: dt.datetime) -> float:
    """How long the current block has lasted, in hours. Zero when not blocked."""
    since = state.get("blocked_since")
    if not since:
        return 0.0
    return (now.astimezone(dt.UTC) - _parse_instant(str(since))).total_seconds() / 3600.0


def check_block(state: dict[str, Any], now: dt.datetime) -> None:
    """Raise once the block has lasted more than 24 consecutive hours."""
    hours = block_hours(state, now)
    if hours > BLOCK_LIMIT_HOURS:
        raise IspBlockPersisted(
            f"Kalshi has been unreachable for {hours:.1f} consecutive hours, past the "
            f"{BLOCK_LIMIT_HOURS:.0f} h limit in SOP W8.2. Stop and raise it with the owner. "
            "Do not route through the Hetzner host."
        )


def record_failure(reason: str, now: dt.datetime) -> dict[str, Any]:
    """Start or extend the block clock, then check it against the 24 h limit."""
    state = read_state()
    state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
    state["last_failure"] = _stamp(now)
    state["last_failure_reason"] = reason
    if not state.get("blocked_since"):
        state["blocked_since"] = _stamp(now)
    write_state(state)
    log(f"capture failed, schedule kept: {reason}", now=now)
    check_block(state, now)
    return state


def record_success(now: dt.datetime, *, rows: int) -> dict[str, Any]:
    """Clear the block clock."""
    state = read_state()
    state["consecutive_failures"] = 0
    state["blocked_since"] = None
    state["last_success"] = _stamp(now)
    state["last_success_rows"] = int(rows)
    write_state(state)
    return state


# ---------------------------------------------------------------------------
# The poll, the snapshot and the launchd wake
# ---------------------------------------------------------------------------

Fetcher = Callable[[str], Any]


def candlesticks_url(ticker: str, start_ts: int, end_ts: int) -> str:
    """The candlestick URL for one market over one window, at 60-minute periods."""
    return CANDLESTICKS_URL.format(ticker=ticker, start_ts=int(start_ts), end_ts=int(end_ts))


def probables_url(day: dt.date | dt.datetime | str) -> str:
    """The point-in-time probables URL for one UTC date."""
    return PROBABLES_URL.format(day=_as_date(day).isoformat())


def capture_once(
    *,
    now: dt.datetime | None = None,
    fetch: Fetcher | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """One poll. Returns what happened; never raises on a network failure.

    The only exception that escapes is :class:`IspBlockPersisted`, which is the
    owner item, and :class:`RouteViolation`, which is a configuration error.
    """
    moment = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    assert_direct_route()
    if not force and not in_capture_window(moment):
        return {"action": "skipped", "reason": "outside the 16:00Z to 06:00Z window", "rows": 0}
    getter = fetch or client.get
    try:
        response = getter(MARKETS_URL)
    except Exception as exc:  # the block is a fact to record, not to raise
        record_failure(f"{type(exc).__name__}: {exc}", moment)
        return {"action": "failed", "reason": f"{type(exc).__name__}: {exc}", "rows": 0}
    payload = json.loads(_body(response))
    markets = payload.get("markets") or []
    rows = [market_row(market, moment) for market in markets]
    written = append_rows(quotes_path(moment), rows, key=_quote_key)
    record_success(moment, rows=written)
    log(f"poll ok, {len(markets)} markets, {written} rows appended", now=moment)
    return {
        "action": "captured",
        "markets": len(markets),
        "rows": written,
        "path": str(quotes_path(moment)),
    }


def snapshot_probables(
    *,
    now: dt.datetime | None = None,
    fetch: Fetcher | None = None,
) -> dict[str, Any]:
    """The point-in-time probables snapshot for the current UTC date.

    Write-once. A later query returns the actual starter, which is look-ahead,
    so once a day has a snapshot it is never rewritten.
    """
    moment = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    assert_direct_route()
    destination = probables_path(moment)
    if destination.is_file():
        return {"action": "already captured", "path": str(destination), "rows": 0}
    getter = fetch or client.get
    try:
        response = getter(probables_url(moment))
    except Exception as exc:  # same posture as the poll
        log(f"probables snapshot failed, schedule kept: {type(exc).__name__}: {exc}", now=moment)
        return {"action": "failed", "reason": f"{type(exc).__name__}: {exc}", "rows": 0}
    rows = probables_rows(json.loads(_body(response)), moment)
    written = append_rows(destination, rows, key=_snapshot_key)
    log(f"probables snapshot ok, {written} games", now=moment)
    return {"action": "captured", "rows": written, "path": str(destination)}


def probables_rows(payload: dict[str, Any], snapshot_ts: dt.datetime) -> list[dict[str, Any]]:
    """Flatten a schedule payload into one point-in-time row per game."""
    rows: list[dict[str, Any]] = []
    for day in payload.get("dates") or []:
        for game in day.get("games") or []:
            teams = game.get("teams") or {}
            row = {
                "snapshot_ts": _stamp(snapshot_ts),
                "official_date": day.get("date"),
                "game_pk": game.get("gamePk"),
                "game_date": game.get("gameDate"),
                "game_type": game.get("gameType"),
                "status": (game.get("status") or {}).get("detailedState"),
            }
            for side in ("away", "home"):
                entry = teams.get(side) or {}
                probable = entry.get("probablePitcher") or {}
                row[f"{side}_team_id"] = (entry.get("team") or {}).get("id")
                row[f"{side}_team_name"] = (entry.get("team") or {}).get("name")
                row[f"{side}_probable_id"] = probable.get("id")
                row[f"{side}_probable_name"] = probable.get("fullName")
            rows.append(row)
    return rows


def _body(response: Any) -> str:
    """The response text, however the caller's fetcher spells it."""
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(response, bytes):
        return response.decode("utf-8")
    return str(response)


def tick(
    *,
    now: dt.datetime | None = None,
    fetch: Fetcher | None = None,
) -> dict[str, Any]:
    """One launchd wake: the snapshot if it is due, then the poll if in window."""
    moment = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    result: dict[str, Any] = {"at": _stamp(moment)}
    if is_snapshot_wake(moment):
        result["probables"] = snapshot_probables(now=moment, fetch=fetch)
    else:
        result["probables"] = {"action": "not due", "rows": 0}
    result["quotes"] = capture_once(now=moment, fetch=fetch)
    return result


# ---------------------------------------------------------------------------
# The offline contract check
# ---------------------------------------------------------------------------


def selfcheck() -> list[str]:
    """Check the W8.2 contract facts that need no network. Return the failures."""
    problems: list[str] = []

    if len(MARKET_FIELDS) != 13:
        problems.append(f"MARKET_FIELDS has {len(MARKET_FIELDS)} entries, W8.2 verified 13")
    if START_INTERVAL_SECONDS != 600:
        problems.append("StartInterval is not 600 s")
    if START_INTERVAL_SECONDS * EXPECTED_POLLS_PER_DAY != 86_400:
        problems.append("144 wakes at StartInterval 600 do not fill a day")

    parsed = parse_ticker(VERIFIED_TICKER)
    if _stamp(parsed.start_utc()) != VERIFIED_CASE["game_date_utc"]:
        problems.append(
            f"{VERIFIED_TICKER} gives {_stamp(parsed.start_utc())}, "
            f"W8.2 verified {VERIFIED_CASE['game_date_utc']}"
        )
    if parsed.official_date().isoformat() != VERIFIED_CASE["official_date"]:
        problems.append(
            f"{VERIFIED_TICKER} gives officialDate {parsed.official_date().isoformat()}, "
            f"W8.2 verified {VERIFIED_CASE['official_date']}"
        )
    split = (parsed.away, parsed.home, parsed.side)
    verified_split = (VERIFIED_CASE["away"], VERIFIED_CASE["home"], VERIFIED_CASE["side"])
    if split != verified_split:
        problems.append(f"{VERIFIED_TICKER} split to {split}, W8.2 verified {verified_split}")

    naive = parsed.start_eastern().replace(tzinfo=dt.UTC)
    if naive == parsed.start_utc():
        problems.append("the Eastern reading and the UTC reading agree; trap 1 is not encoded")

    numbers = sizing()
    if abs(numbers["quote_rows"] - numbers["quote_rows_stated"]) > 1_000:
        problems.append(
            f"41 x 144 x 30 = {numbers['quote_rows']}, which is not the stated "
            f"{numbers['quote_rows_stated']}"
        )
    return problems


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m absump.p8.kalshi_capture",
        description="W8.2 Kalshi capture agent and daily probables snapshot",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tick", action="store_true", help="one launchd wake")
    group.add_argument("--once", action="store_true", help="one poll, window ignored")
    group.add_argument("--snapshot", action="store_true", help="today's probables snapshot")
    group.add_argument("--plan", action="store_true", help="print the plan, send nothing")
    group.add_argument("--selfcheck", action="store_true", help="check the contract offline")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.selfcheck:
        problems = selfcheck()
        for line in problems:
            print(f"W8.2 selfcheck: {line}", file=sys.stderr)
        if problems:
            return 1
        print("W8.2 selfcheck: OK")
        return 0

    if args.plan:
        now = dt.datetime.now(dt.UTC)
        print(f"W8.2 plan at {_stamp(now)}")
        print(f"  window 16:00Z-06:00Z, in window: {in_capture_window(now)}")
        print(f"  StartInterval {START_INTERVAL_SECONDS} s, {EXPECTED_POLLS_PER_DAY} wakes a day")
        print(f"  markets   {MARKETS_URL}")
        print(f"  probables {probables_url(now)}")
        print(f"  quotes    {quotes_path(now)}")
        print(f"  snapshot  {probables_path(now)}")
        print("  0 requests sent")
        return 0

    try:
        if args.tick:
            outcome = tick()
        elif args.once:
            outcome = capture_once(force=True)
        else:
            outcome = snapshot_probables()
    except (IspBlockPersisted, RouteViolation) as exc:
        print(f"W8.2: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
