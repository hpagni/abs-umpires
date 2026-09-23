# Kalshi KXMLBGAME ticker grammar, and the two traps

SOP step W8.2. This file is the contract the capture agent encodes. The code is
`src/absump/p8/kalshi_capture.py`; the tests are `tests/p8/test_kalshi_capture.py`.

## The grammar

```
KXMLBGAME-{YY}{MON}{DD}{HHMM}{AWAY}{HOME}-{SIDE}
```

- `YY` two digits of the year, `MON` a three-letter month, `DD` the day of month.
- `HHMM` the start time, four digits.
- `AWAY` and `HOME` are team codes run together with no separator.
- `SIDE` after the second hyphen is the team the contract pays on.

The digits separate the stamp from the team codes, so the stamp is unambiguous.
The two team codes are not: `SDLAD` could be `SD`+`LAD` or `SDL`+`AD`. The side
resolves it, because the side is one of the two codes: if the run starts with
the side, the side is the away team; if it ends with the side, the side is the
home team. When both hold the split needs `config/team_crosswalk_kalshi.csv`,
which W8.2 does not own, and `parse_ticker` raises `TickerAmbiguous` rather than
guessing.

## Trap 1: HHMM is US/Eastern, not UTC

Verified case, from the SOP text for W8.2:

| Field | Value |
|---|---|
| ticker | `KXMLBGAME-26SEP242210SDLAD-SD` |
| gamePk | 823895 |
| gameDate | `2026-09-25T02:10:00Z` |
| officialDate | 2026-09-24 |

`2210` read as US/Eastern is 22:10 EDT on 24 September, which is
`2026-09-25T02:10:00Z`. That is the gameDate the schedule endpoint returns.
Read as UTC the same ticker would put the game four hours early and on the
previous calendar day, and it would disagree with officialDate as well, which
is the Eastern calendar date in the stamp.

`Ticker.start_eastern()`, `Ticker.start_utc()` and `Ticker.official_date()`
encode this. `selfcheck()` fails if the Eastern reading and the UTC reading ever
agree, because that would mean the timezone was dropped.

## Trap 2: close_time on an open market is a placeholder

On an open market `close_time` sits about three days past the game start. It is
not a settlement time and it is never a start time. The only sanctioned start
time is `start_utc(market)`, which reads the ticker.

`close_time_is_placeholder(market)` flags the three-day shape, measured from the
ticker's start time, which is the one anchor a single poll carries that is known
to be right. `reject_close_time_as_start(market)` exists so that a caller who
reaches for `close_time` gets an exception with the reason attached.

## The capture

- `GET https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXMLBGAME&status=open&limit=1000`
- every 10 minutes, 16:00Z to 06:00Z, under launchd `StartInterval 600`
- appended as NDJSON per UTC date

Verified market fields, thirteen, kept in this order and nothing else:

```
ticker, event_ticker, title, yes_bid_dollars, yes_ask_dollars, last_price_dollars,
volume_fp, open_interest_fp, open_time, close_time, result, status, rules_primary
```

Candlesticks:

```
GET /trade-api/v2/series/KXMLBGAME/markets/{ticker}/candlesticks?start_ts=&end_ts=&period_interval=60
```

return `end_period_ts`, `price.{open,high,low,close,mean,previous}_dollars`,
`yes_bid.{open,high,low,close}_dollars`, `yes_ask.{open,high,low,close}_dollars`,
`volume_fp` and `open_interest_fp`.

## The daily probables snapshot

One point-in-time snapshot per UTC day, at 14:00Z, because a later query returns
the *actual* starter, which is look-ahead. The snapshot is write-once: once a
UTC date has a snapshot file the agent never rewrites it.

launchd wakes on an interval, not on a clock, so the snapshot is taken at the
first wake at or after 14:00Z and the write-once rule keeps it to one a day.

## Layout

```
data/p8/kalshi/quotes/date=YYYY-MM-DD/markets.ndjson
data/p8/kalshi/probables/date=YYYY-MM-DD/probables.ndjson
data/p8/kalshi/_state.json
data/p8/kalshi/agent.log
data/p8/kalshi/launchd.log
```

All of `data/` is gitignored. A quote row is the poll stamp plus the thirteen
verified fields. Rows are keyed on `(poll_ts, ticker)` and a key already in the
file is dropped, so re-running one poll writes no bytes.

## Sizing

About 41 days, 144 wakes a day, about 30 markets a poll: 41 x 144 x 30 = 177,120,
so about 177,000 quote rows and about 15 MB, plus about 41 snapshots and about
3 MB.

144 is the number of `StartInterval 600` wakes in a day, 86,400 / 600. The
16:00Z to 06:00Z window admits 84 of those 144 wakes, so 177,000 rows is the
ceiling the SOP sizes against rather than the count the window will produce.
That gap is recorded here, not resolved: the window and the row estimate are
both SOP text for W8.2.

## The network fact

Kalshi hosts are TLS-reset from the Madrid university network this project runs
on. That is an environment fact, not a bug. The agent logs the failure, keeps
its schedule and retries at the next wake.

It never routes through another host. The Hetzner box is production for another
site and is off limits, and `assert_direct_route()` refuses to run when a proxy
variable is set. A block lasting more than 24 consecutive hours raises
`IspBlockPersisted`: stop and raise it with the owner.

Every request goes through `absump.http.get`, the one chokepoint, which enforces
the 10 s inter-request delay and the 500/day cap that `config/throttle.yml` sets
for `api.elections.kalshi.com` under SOP section 5A item A3.
