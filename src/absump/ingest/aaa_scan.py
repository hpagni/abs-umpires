"""The AAA regime scans D-11 and D-57. SOP step W2.8, revision R2.

D-11, verbatim from the SOP decision table: run the full 2023 AAA scan first; if
the season-wide count of ``absChallenges`` keys is zero, the challenge arm is
2024-2025 only. Every Final regular-season 2023 AAA game on disk is scanned, not
a sample. The row is closed only when every such game in the schedule has been
scanned.

D-57, verbatim: binary-search the 2024 AAA schedule for the first Tue/Wed/Thu
game carrying ``gameData.absChallenges``, about 40 feed requests, and record the
date in the rule-version table. The search is over Tue/Wed/Thu dates, not games:

1. The floor is the last Tue/Wed/Thu date through which every Final Tue/Wed/Thu
   game is already on disk with no key. Nothing at or below it is requested.
2. Above it, each probe reads the two lowest gamePks of the date. The date is a
   key date if either carries the key. The choice depends on the schedule alone,
   so a second run probes the same games, finds them on disk, and requests
   nothing.
3. The two dates the search ends between are then read in full: every Final
   game on the last Tue/Wed/Thu date without the key and on the first with it.
   The row closes only if the first is all key and the second all no-key with
   zero MJ reviews. A mixed boundary day leaves the row open and says why.

Every request goes through :func:`absump.ingest.feeds.fetch_games`, and through
it :func:`absump.http.get`: the 4 s spacing, the flock'd daily budget, the raw
cache and the manifest. This module holds no URL and imports no transport.

The scan columns are the SOP W2.8 columns ``R/ch1/12_aaa_formats.R`` writes, and
the per-game logic is the same, so a game both scans read gets a byte-identical
row: the key tested by presence only, MJ reviews counted at the event and play
level with ``additionalReviews`` walked, and ``max_remaining`` the D-12 starting
allotment (the play-by-play maximum of ``remainingChallenges`` per side, else the
end block's ``usedFailed + remaining``).

Command line::

    uv run --locked python -m absump.ingest.aaa_scan --plan-only
    uv run --locked python -m absump.ingest.aaa_scan --max-requests 60
    uv run --locked python -m absump.ingest.aaa_scan --check

``--check`` requests nothing and writes nothing: it recomputes every table from
the feeds on disk and exits 1 on a byte of drift or on a probe whose feed is
missing.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import io
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson
import zstandard

from absump import paths
from absump.ingest import feeds

__all__ = [
    "SEASONS",
    "SPORT_AAA",
    "TUE_THU",
    "ScanRow",
    "Search",
    "changeover_rows",
    "final_games",
    "format_row",
    "lake_index",
    "main",
    "scan_feed",
    "search_changeover",
]

SPORT_AAA = 11
#: D-11 is 2023 and D-57 is 2024. Nothing later is read by this module.
SEASONS = (2023, 2024)
D11_SEASON = 2023
D57_SEASON = 2024
TUE_THU = ("Tuesday", "Wednesday", "Thursday")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
#: Games read per probe date. The SOP asks for the boundary to be seen on two
#: games a side; the boundary days are then read in full.
PROBE_WIDTH = 2
#: The ceiling on requests one invocation may issue. The SOP sizes the search at
#: about 40; the budget file is the other ceiling and is enforced by absump.http.
DEFAULT_MAX_REQUESTS = 60

OUT = paths.REPO_ROOT / "out" / "tables"
SCAN_FILE = OUT / "aaa_regime_scan.csv"
CHANGE_FILE = OUT / "aaa_changeover.csv"
FORMAT_FILE = OUT / "aaa_format.csv"
SCAN_REL = "out/tables/aaa_regime_scan.csv"
CHANGE_REL = "out/tables/aaa_changeover.csv"

SCAN_COLS = (
    "game_pk",
    "season",
    "official_date",
    "weekday",
    "has_abs_challenges",
    "n_mj_event",
    "n_mj_play",
    "max_remaining",
)
CHANGE_COLS = (
    "decision",
    "level",
    "season",
    "status",
    "n_final_scheduled",
    "n_scanned",
    "n_with_key",
    "first_key_date",
    "last_no_key_date",
    "result",
    "evidence_path",
)
FORMAT_COLS = ("level", "season", "rule_version", "changeover_date", "source", "evidence_path")
#: Columns R's write.csv quotes: every character column. Integers are bare.
_QUOTED = {
    "official_date",
    "weekday",
    "has_abs_challenges",
    "decision",
    "level",
    "status",
    "first_key_date",
    "last_no_key_date",
    "result",
    "evidence_path",
    "rule_version",
    "changeover_date",
    "source",
}
#: The source tags of the rule-version rows this module owns. R/ch1/12_aaa_formats.R
#: keeps every aaa_format.csv row whose source does not begin "W3.9 " byte for byte,
#: and this module keeps every row whose source begins with neither tag.
D11_SOURCE_TAG = "D-11 scan:"
D57_SOURCE_TAG = "D-57 binary search:"
OWN_SOURCE_TAGS = (D11_SOURCE_TAG, D57_SOURCE_TAG)
D11_RULE_VERSION = "format_challenge_fri_to_mon_no_key_tue_thu"
D57_RULE_VERSION = "format_challenge_tue_thu"


# ---------------------------------------------------------------------------
# One game
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanRow:
    """One game's scan. The first eight fields are the table's columns."""

    game_pk: int
    season: int
    official_date: _dt.date
    weekday: str
    has_abs_challenges: bool
    n_mj_event: int
    n_mj_play: int
    max_remaining: int | None
    n_reviews_any: int = 0

    @property
    def n_mj(self) -> int:
        return self.n_mj_event + self.n_mj_play


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def weekday_of(day: _dt.date) -> str:
    """The English weekday name, independent of the process locale."""
    return WEEKDAYS[day.weekday()]


def scan_feed(feed: dict[str, Any]) -> ScanRow:
    """The SOP W2.8 scan columns for one GUMBO feed."""
    game_data = feed.get("gameData", {})
    snapshots: dict[str, list[int]] = {"away": [], "home": []}
    n_event = n_play = n_any = 0

    def take(review: dict[str, Any]) -> None:
        remaining = review.get("remainingChallenges")
        if isinstance(remaining, dict):
            for side in ("away", "home"):
                value = _int_or_none(remaining.get(side))
                if value is not None:
                    snapshots[side].append(value)

    for play in feed.get("liveData", {}).get("plays", {}).get("allPlays", ()) or ():
        for review in feeds.iter_review_details(play.get("reviewDetails")):
            take(review)
            n_any += 1
            n_play += review.get("reviewType") == feeds.ABS_REVIEW_TYPE
        for event in play.get("playEvents") or ():
            for review in feeds.iter_review_details(event.get("reviewDetails")):
                take(review)
                n_any += 1
                n_event += review.get("reviewType") == feeds.ABS_REVIEW_TYPE

    max_remaining: int | None = None
    block = game_data.get(feeds.REGIME_MARKER)
    if isinstance(block, (dict, list)):
        per_side: list[int] = []
        for side in ("away", "home"):
            if snapshots[side]:
                per_side.append(max(snapshots[side]))
                continue
            end = block.get(side) if isinstance(block, dict) else None
            end = end if isinstance(end, dict) else {}
            used_failed = _int_or_none(end.get("usedFailed"))
            remaining = _int_or_none(end.get("remaining"))
            if used_failed is not None and remaining is not None:
                per_side.append(used_failed + remaining)
        max_remaining = max(per_side) if per_side else None

    day = paths.as_official_date(game_data["datetime"]["officialDate"])
    return ScanRow(
        game_pk=int(game_data["game"]["pk"]),
        season=int(game_data["game"]["season"]),
        official_date=day,
        weekday=weekday_of(day),
        has_abs_challenges=feeds.has_abs_regime(feed),
        n_mj_event=int(n_event),
        n_mj_play=int(n_play),
        max_remaining=max_remaining,
        n_reviews_any=int(n_any),
    )


def read_feed(path: Path) -> dict[str, Any]:
    """One stored feed, refused if it is outside the SOP W2.6 size window."""
    with path.open("rb") as handle, zstandard.ZstdDecompressor().stream_reader(handle) as reader:
        body = reader.read()
    if not feeds.body_is_sane(body):
        raise ValueError(f"{path}: {len(body)} B is outside the SOP W2.6 size window")
    return orjson.loads(body)


# ---------------------------------------------------------------------------
# The schedule and the lake
# ---------------------------------------------------------------------------


def final_games(season: int) -> list[feeds.ScheduledGame]:
    """Every Final regular-season AAA game of ``season`` that was played.

    The lake copy of the schedule, split by :func:`absump.ingest.feeds.plan`,
    which drops Postponed and Cancelled games under abstract state Final.
    """
    if season not in SEASONS:
        raise ValueError(f"season {season}: this module reads {SEASONS} only")
    schedule = feeds.load_schedule(SPORT_AAA, season, allow_fetch=False)
    candidates = feeds.plan(feeds.schedule_games(schedule), status="Final").candidates
    return [g for g in candidates if g.game_type == "R" and g.season == season]


def lake_index(season: int) -> dict[int, Path]:
    """gamePk -> stored feed, for one season of the AAA lake."""
    root = paths.raw_feed(SPORT_AAA, season, _dt.date(season, 6, 1), 1).parents[1]
    out: dict[int, Path] = {}
    for path in sorted(root.glob("date=*/gamepk=*.json.zst")):
        pk = int(path.name.split("=", 1)[1].split(".", 1)[0])
        out.setdefault(pk, path)
    return out


# ---------------------------------------------------------------------------
# D-57: the search
# ---------------------------------------------------------------------------


@dataclass
class Search:
    """What the D-57 search read, and what it concluded."""

    floor_date: _dt.date | None = None
    floor_games: int = 0
    dates: list[_dt.date] = field(default_factory=list)
    probes: list[tuple[_dt.date, tuple[int, ...], bool]] = field(default_factory=list)
    first_key_date: _dt.date | None = None
    last_no_key_date: _dt.date | None = None
    boundary: dict[_dt.date, list[ScanRow]] = field(default_factory=dict)
    touched: set[int] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)

    @property
    def closed(self) -> bool:
        return self.first_key_date is not None and not self.problems


Reader = Callable[[list[feeds.ScheduledGame]], dict[int, ScanRow]]


def search_changeover(
    games: list[feeds.ScheduledGame], scanned: dict[int, ScanRow], read: Reader
) -> Search:
    """Binary-search the Tue/Wed/Thu dates of ``games`` for the first key date.

    ``scanned`` is what is already on disk. ``read`` returns the scan rows of the
    games it is given, pulling any that are not on disk (or raising, offline).
    """
    tt = sorted(
        (g for g in games if weekday_of(g.official_date) in TUE_THU),
        key=lambda g: (g.official_date, g.game_pk),
    )
    by_date: dict[_dt.date, list[feeds.ScheduledGame]] = {}
    for game in tt:
        by_date.setdefault(game.official_date, []).append(game)
    dates = sorted(by_date)
    out = Search()

    # 1. the floor: the fully scanned, keyless run of Tue/Wed/Thu dates
    floor = -1
    for index, day in enumerate(dates):
        rows = [scanned.get(g.game_pk) for g in by_date[day]]
        if any(r is None for r in rows):
            break
        if any(r.has_abs_challenges for r in rows if r is not None):
            break
        floor = index
    if floor >= 0:
        out.floor_date = dates[floor]
        out.floor_games = sum(len(by_date[d]) for d in dates[: floor + 1])
    out.dates = dates[floor + 1 :]
    if floor + 1 < len(dates) and all(g.game_pk in scanned for g in by_date[dates[floor + 1]]):
        # the first date above the floor is fully scanned and has a key: no search
        first = dates[floor + 1]
        out.first_key_date = first
        out.last_no_key_date = out.floor_date
        out.boundary[first] = [scanned[g.game_pk] for g in by_date[first]]
        out.touched.update(g.game_pk for g in by_date[first])
        _judge(out)
        return out

    # 2. the binary search over the dates above the floor
    lo, hi = -1, len(out.dates)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        day = out.dates[mid]
        chosen = sorted(by_date[day], key=lambda g: g.game_pk)[:PROBE_WIDTH]
        rows = read(chosen)
        key = any(rows[g.game_pk].has_abs_challenges for g in chosen)
        out.probes.append((day, tuple(g.game_pk for g in chosen), key))
        out.touched.update(g.game_pk for g in chosen)
        if key:
            hi = mid
        else:
            lo = mid
    if hi == len(out.dates):
        out.problems.append(
            "no Tue/Wed/Thu date after the floor carries the key: the 2024 changeover "
            "is not in the regular season"
        )
        return out
    out.first_key_date = out.dates[hi]
    out.last_no_key_date = out.dates[lo] if lo >= 0 else out.floor_date

    # 3. the two boundary days, read in full
    for day in (out.last_no_key_date, out.first_key_date):
        if day is None:
            continue
        rows = read(by_date[day])
        out.boundary[day] = [rows[g.game_pk] for g in by_date[day]]
        out.touched.update(g.game_pk for g in by_date[day])
    _judge(out)
    return out


def _judge(out: Search) -> None:
    first, last = out.first_key_date, out.last_no_key_date
    if first is not None and first in out.boundary:
        lacking = [r.game_pk for r in out.boundary[first] if not r.has_abs_challenges]
        if lacking:
            out.problems.append(
                f"{len(lacking)} of {len(out.boundary[first])} games on {first} lack the key: "
                + ", ".join(str(pk) for pk in lacking)
            )
    if last is not None and last in out.boundary:
        carrying = [r.game_pk for r in out.boundary[last] if r.has_abs_challenges or r.n_mj]
        if carrying:
            out.problems.append(
                f"{len(carrying)} of {len(out.boundary[last])} games on {last} carry the key "
                "or an MJ review: " + ", ".join(str(pk) for pk in carrying)
            )


# ---------------------------------------------------------------------------
# Reading, and pulling only what the search needs
# ---------------------------------------------------------------------------


class MissingFeed(RuntimeError):
    """A game the search must read has no feed on disk, and pulling is off."""


def budget_used(host: str = "statsapi.mlb.com") -> tuple[str, int]:
    """The UTC day and the count ``absump.http`` has spent on ``host`` today."""
    path = paths.data_root() / "raw" / "_budget.json"
    if not path.exists():
        return ("", 0)
    state = orjson.loads(path.read_bytes())
    return (str(state.get("utc_date", "")), int(state.get("used", {}).get(host, 0)))


@dataclass
class Puller:
    """The search's reader. Pulls through the project's feed puller, capped."""

    scanned: dict[int, ScanRow]
    allow_pull: bool
    max_requests: int
    pulled: list[int] = field(default_factory=list)
    report: list[str] = field(default_factory=list)

    def __call__(self, games: list[feeds.ScheduledGame]) -> dict[int, ScanRow]:
        missing = [g for g in games if g.game_pk not in self.scanned]
        if missing and not self.allow_pull:
            raise MissingFeed(
                "no feed on disk for "
                + ", ".join(f"{g.game_pk} ({g.official_date})" for g in missing)
                + "; run the build to pull them"
            )
        if missing:
            left = self.max_requests - len(self.pulled)
            if len(missing) > left:
                raise RuntimeError(
                    f"the search needs {len(missing)} more feeds and {left} of the "
                    f"{self.max_requests}-request ceiling are left"
                )
            counts = feeds.fetch_games(
                missing, SPORT_AAA, D57_SEASON, max_requests=left, report=self.report
            )
            if counts["fatal"] or counts["budget"]:
                raise RuntimeError("the puller stopped: " + "; ".join(self.report[-3:]))
            for game in missing:
                stored = feeds.stored_path(SPORT_AAA, D57_SEASON, game.game_pk)
                if stored is None:
                    raise RuntimeError(
                        f"game {game.game_pk} is not stored after the pull: "
                        + "; ".join(self.report[-3:])
                    )
                self.scanned[game.game_pk] = scan_feed(read_feed(stored))
                self.pulled.append(game.game_pk)
        return {g.game_pk: self.scanned[g.game_pk] for g in games}


# ---------------------------------------------------------------------------
# The tables
# ---------------------------------------------------------------------------


def _cell(column: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        value = "TRUE" if value else "FALSE"
    if isinstance(value, _dt.date):
        value = value.isoformat()
    if column in _QUOTED:
        return '"' + str(value).replace('"', '""') + '"'
    return str(value)


def csv_text(columns: Iterable[str], rows: Iterable[dict[str, Any]]) -> str:
    """The bytes R's ``utils::write.csv(row.names = FALSE, na = "")`` writes."""
    cols = tuple(columns)
    lines = [",".join(f'"{c}"' for c in cols)]
    lines += [",".join(_cell(c, row.get(c)) for c in cols) for row in rows]
    return "\n".join(lines) + "\n"


def scan_table(rows: Iterable[ScanRow]) -> str:
    ordered = sorted(rows, key=lambda r: (r.season, r.official_date, r.game_pk))
    return csv_text(SCAN_COLS, ({c: getattr(r, c) for c in SCAN_COLS} for r in ordered))


def comma(n: int) -> str:
    return f"{n:,}"


def d11_row(finals: list[feeds.ScheduledGame], rows: dict[int, ScanRow]) -> dict[str, Any]:
    """D-11: the 2023 key count over every Final regular-season game."""
    got = [rows[g.game_pk] for g in finals if g.game_pk in rows]
    keyed = [r for r in got if r.has_abs_challenges]
    unkeyed = [r for r in got if not r.has_abs_challenges]
    closed = len(got) == len(finals) and len(finals) > 0
    n_mj = sum(r.n_mj for r in got)
    n_any = sum(r.n_reviews_any for r in got)
    span = (
        f"{min(r.official_date for r in got)} to {max(r.official_date for r in got)}"
        if got
        else "no game"
    )
    if closed and not keyed:
        result = (
            f"absChallenges key on 0 of {comma(len(finals))} Final 2023 games, every one "
            f"scanned ({span}); {comma(n_mj)} MJ reviews at the event and play level and "
            f"{comma(n_any)} review records of any type: the challenge arm is 2024-2025 "
            "only, and 2023 is kept for zone geometry, not challenge behaviour"
        )
    elif closed:
        first = min(r.official_date for r in keyed)
        split = d11_split(got, first)
        result = (
            f"absChallenges key on {comma(len(keyed))} of {comma(len(finals))} Final 2023 "
            f"games, every one scanned ({span}), first on {first} ({weekday_of(first)}). "
            f"By weekday: 0 of {comma(split['tt'])} Tue/Wed/Thu games carry it; of the other "
            f"days, {split['early_keyed']} of {comma(split['early'])} games before {first} "
            f"and {comma(split['late_keyed'])} of {comma(split['late'])} on or after it. "
            f"{comma(n_mj)} MJ reviews, all on keyed games ({split['unkeyed_mj']} on a game "
            "without the key). The SOP's zero-key branch does not apply: the AAA challenge "
            f"arm includes 2023 from {first}, and a 2023 game's format is read from its key"
        )
    else:
        result = (
            f"absChallenges key on {comma(len(keyed))} of {comma(len(got))} games scanned; "
            f"{comma(len(finals) - len(got))} Final 2023 games are not on disk, so the "
            "season count is open"
        )
    return {
        "decision": "D-11",
        "level": "aaa",
        "season": D11_SEASON,
        "status": "closed" if closed else "open",
        "n_final_scheduled": len(finals),
        "n_scanned": len(got),
        "n_with_key": len(keyed),
        "first_key_date": min((r.official_date for r in keyed), default=None),
        "last_no_key_date": max((r.official_date for r in unkeyed), default=None),
        "result": result,
        "evidence_path": SCAN_REL,
    }


def d11_split(rows: list[ScanRow], first: _dt.date) -> dict[str, int]:
    """The 2023 key pattern by weekday, around the first key date."""
    tt = [r for r in rows if r.weekday in TUE_THU]
    other = [r for r in rows if r.weekday not in TUE_THU]
    early = [r for r in other if r.official_date < first]
    late = [r for r in other if r.official_date >= first]
    return {
        "tt": len(tt),
        "tt_keyed": sum(r.has_abs_challenges for r in tt),
        "early": len(early),
        "early_keyed": sum(r.has_abs_challenges for r in early),
        "late": len(late),
        "late_keyed": sum(r.has_abs_challenges for r in late),
        "unkeyed_mj": sum(r.n_mj for r in rows if not r.has_abs_challenges),
    }


def d11_format_row(
    finals: list[feeds.ScheduledGame], rows: dict[int, ScanRow]
) -> dict[str, Any] | None:
    """The 2023 rule-version row D-11 writes, when the closed scan finds the key.

    SOP D-11: write both results into the rule-version table. The row names what
    the key shows and nothing more: from its first date the key is on the games
    played Friday to Monday and never on a Tuesday, Wednesday or Thursday. Whether
    a keyless game was called by the machine or by the umpire is W3.9's agreement
    classification, not this scan's.
    """
    got = [rows[g.game_pk] for g in finals if g.game_pk in rows]
    keyed = [r for r in got if r.has_abs_challenges]
    if len(got) != len(finals) or not keyed:
        return None
    first = min(r.official_date for r in keyed)
    split = d11_split(got, first)
    if split["tt_keyed"]:
        return None
    return {
        "level": "aaa",
        "season": D11_SEASON,
        "rule_version": D11_RULE_VERSION,
        "changeover_date": first,
        "source": (
            f"{D11_SOURCE_TAG} absChallenges key on {comma(split['late_keyed'])} of "
            f"{comma(split['late'])} Friday-to-Monday games from this date and on "
            f"{split['early_keyed']} of {comma(split['early'])} before it, and on 0 of "
            f"{comma(split['tt'])} Tue/Wed/Thu games all season; every one of the "
            f"{comma(len(finals))} Final 2023 games scanned; D-11 row of "
            "out/tables/aaa_changeover.csv"
        ),
        "evidence_path": SCAN_REL,
    }


def pattern_breaks(rows: Iterable[ScanRow], first: _dt.date) -> list[str]:
    """DT-29 on a set of Tue/Wed/Thu rows: before ``first`` no key and 0 MJ, after it the key."""
    out = []
    for r in rows:
        if r.official_date < first and (r.has_abs_challenges or r.n_mj):
            out.append(f"{r.game_pk} ({r.official_date}) before {first} carries the key or MJ")
        if r.official_date >= first and not r.has_abs_challenges:
            out.append(f"{r.game_pk} ({r.official_date}) on or after {first} lacks the key")
    return out


def d57_row(
    finals: list[feeds.ScheduledGame], rows: dict[int, ScanRow], search: Search
) -> dict[str, Any]:
    """D-57: the first Tue/Wed/Thu 2024 game with the key, by binary search."""
    tt_final = [g for g in finals if weekday_of(g.official_date) in TUE_THU]
    got = [rows[g.game_pk] for g in tt_final if g.game_pk in rows]
    keyed = [r for r in got if r.has_abs_challenges]
    unkeyed = [r for r in got if not r.has_abs_challenges]
    first = search.first_key_date
    problems = list(search.problems)
    if first is not None:
        problems += pattern_breaks(got, first)
    closed = first is not None and not problems
    if closed and first is not None:
        last = search.last_no_key_date
        on_first = search.boundary.get(first, [])
        on_last = search.boundary.get(last, []) if last is not None else []
        before = [r for r in got if r.official_date < first]
        after = [r for r in got if r.official_date >= first]
        probes = "; ".join(
            f"{day} {'key' if key else 'no key'}" for day, _pks, key in search.probes
        )
        result = (
            f"first Tue/Wed/Thu game with the absChallenges key is on {first}. Binary "
            f"search over the {len(search.dates)} Tue/Wed/Thu dates "
            f"{search.dates[0]} to {search.dates[-1]} above the floor {search.floor_date} "
            f"(every one of the {comma(search.floor_games)} Final Tue/Wed/Thu games through "
            f"it scanned with no key): {len(search.probes)} probes of the two lowest gamePks "
            f"({probes}), then both boundary days read in full: {len(on_first)} of "
            f"{len(on_first)} games on {first} carry the key; {len(on_last)} of "
            f"{len(on_last)} games on {last}, the Tue/Wed/Thu date before it, carry "
            f"neither the key nor an MJ review. Of the {comma(len(got))} Tue/Wed/Thu games "
            f"scanned, the {comma(len(before))} before {first} carry no key and 0 MJ reviews "
            f"and the {comma(len(after))} on or after it all carry the key; the search "
            f"touched {len(search.touched)} games. The within-week contrast uses dates "
            f"strictly before {first}"
        )
    elif first is None:
        result = "the search found no Tue/Wed/Thu key date: " + "; ".join(problems)
    else:
        result = (
            f"the search ends on {first} but the pattern breaks, so the date is not "
            "settled: " + "; ".join(problems[:5])
        )
    return {
        "decision": "D-57",
        "level": "aaa",
        "season": D57_SEASON,
        "status": "closed" if closed else "open",
        "n_final_scheduled": len(tt_final),
        "n_scanned": len(got),
        "n_with_key": len(keyed),
        "first_key_date": first,
        "last_no_key_date": search.last_no_key_date
        if closed
        else max((r.official_date for r in unkeyed), default=None),
        "result": result,
        "evidence_path": SCAN_REL,
    }


def format_row(search: Search, d57: dict[str, Any]) -> dict[str, Any] | None:
    """The rule-version row W3.20 reads. None until the D-57 row is closed."""
    first, last = search.first_key_date, search.last_no_key_date
    if d57.get("status") != "closed" or first is None or last is None:
        return None
    n_first = len(search.boundary.get(first, []))
    n_last = len(search.boundary.get(last, []))
    return {
        "level": "aaa",
        "season": D57_SEASON,
        "rule_version": D57_RULE_VERSION,
        "changeover_date": first,
        "source": (
            f"{D57_SOURCE_TAG} Tue/Wed/Thu games carry the absChallenges key from this date: "
            f"{n_first} of {n_first} games on {first}, 0 of {n_last} on {last}, the "
            "Tue/Wed/Thu date before it and the last keyless Tue/Wed/Thu date of "
            "format_full_abs_tue_thu_challenge_fri_sun; the within-week contrast uses dates "
            "strictly before this date; D-57 row of out/tables/aaa_changeover.csv"
        ),
        "evidence_path": CHANGE_REL,
    }


def format_text(existing: str | None, own: list[dict[str, Any] | None]) -> str:
    """aaa_format.csv with this module's rows replaced; every other line kept byte for byte."""
    header = ",".join(f'"{c}"' for c in FORMAT_COLS)
    lines = (existing or header + "\n").rstrip("\n").split("\n")
    if lines[0].replace('"', "") != ",".join(FORMAT_COLS):
        raise ValueError(f"aaa_format.csv has a header this module does not write: {lines[0]}")
    kept = [lines[0]]
    for line in lines[1:]:
        parsed = next(csv.DictReader(io.StringIO(lines[0] + "\n" + line + "\n")))
        if not str(parsed.get("source", "")).startswith(OWN_SOURCE_TAGS):
            kept.append(line)
    rows = [row for row in own if row is not None]
    if rows:
        kept += csv_text(FORMAT_COLS, rows).rstrip("\n").split("\n")[1:]
    return "\n".join(kept) + "\n"


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


@dataclass
class Run:
    finals: dict[int, list[feeds.ScheduledGame]]
    rows: dict[int, dict[int, ScanRow]]
    search: Search
    puller: Puller
    texts: dict[Path, str]


def scan_lake(season: int, finals: list[feeds.ScheduledGame]) -> dict[int, ScanRow]:
    """Scan every Final regular-season game of ``season`` whose feed is on disk."""
    index = lake_index(season)
    rows: dict[int, ScanRow] = {}
    for game in finals:
        path = index.get(game.game_pk)
        if path is None:
            continue
        row = scan_feed(read_feed(path))
        if row.game_pk != game.game_pk or row.season != season:
            raise ValueError(f"{path}: the feed is game {row.game_pk} season {row.season}")
        rows[game.game_pk] = row
    return rows


def run(*, allow_pull: bool, max_requests: int) -> Run:
    finals = {s: final_games(s) for s in SEASONS}
    rows = {s: scan_lake(s, finals[s]) for s in SEASONS}
    puller = Puller(rows[D57_SEASON], allow_pull=allow_pull, max_requests=max_requests)
    search = search_changeover(finals[D57_SEASON], rows[D57_SEASON], puller)
    all_rows = [r for s in SEASONS for r in rows[s].values()]
    d57 = d57_row(finals[D57_SEASON], rows[D57_SEASON], search)
    change = [d11_row(finals[D11_SEASON], rows[D11_SEASON]), d57]
    existing = FORMAT_FILE.read_text(encoding="utf-8") if FORMAT_FILE.exists() else None
    own = [d11_format_row(finals[D11_SEASON], rows[D11_SEASON]), format_row(search, d57)]
    texts = {
        SCAN_FILE: scan_table(all_rows),
        CHANGE_FILE: csv_text(CHANGE_COLS, change),
        FORMAT_FILE: format_text(existing, own),
    }
    return Run(finals, rows, search, puller, texts)


def changeover_rows(path: Path = CHANGE_FILE) -> dict[str, dict[str, str]]:
    """The committed aaa_changeover.csv, keyed on decision."""
    with path.open(newline="", encoding="utf-8") as handle:
        return {r["decision"]: r for r in csv.DictReader(handle)}


def _report(result: Run) -> list[str]:
    s = result.search
    lines = []
    for season in SEASONS:
        n_f, n_d = len(result.finals[season]), len(result.rows[season])
        n_k = sum(r.has_abs_challenges for r in result.rows[season].values())
        lines.append(f"coverage {season}: {n_d} of {n_f} Final games scanned, {n_k} with the key")
    lines.append(
        f"D-57 floor {s.floor_date} ({s.floor_games} Tue/Wed/Thu games, all scanned, no key)"
    )
    lines.append(
        f"D-57 search dates {len(s.dates)}: {s.dates[0] if s.dates else '-'} to "
        f"{s.dates[-1] if s.dates else '-'}"
    )
    for day, pks, key in s.probes:
        lines.append(
            f"D-57 probe {day} {weekday_of(day)} games {list(pks)} -> {'KEY' if key else 'no key'}"
        )
    for day, rows in sorted(s.boundary.items()):
        keyed = sum(r.has_abs_challenges for r in rows)
        mj = sum(r.n_mj for r in rows)
        lines.append(
            f"D-57 boundary {day} {weekday_of(day)}: key on {keyed} of {len(rows)}, "
            f"MJ reviews {mj}: "
            + " ".join(f"{r.game_pk}:{'K' if r.has_abs_challenges else '-'}{r.n_mj}" for r in rows)
        )
    lines.append(
        f"D-57 first key {s.first_key_date}, last no key {s.last_no_key_date}, "
        f"touched {len(s.touched)}, problems {len(s.problems)}"
    )
    lines += [f"PROBLEM {p}" for p in s.problems]
    lines.append(f"pulled {len(result.puller.pulled)} feeds: {result.puller.pulled}")
    lines += [f"puller: {line}" for line in result.puller.report]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m absump.ingest.aaa_scan", description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="recompute offline, compare, write nothing"
    )
    mode.add_argument(
        "--plan-only", action="store_true", help="print the floor and dates, send nothing"
    )
    parser.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    args = parser.parse_args(argv)

    if args.plan_only:
        finals = final_games(D57_SEASON)
        rows = scan_lake(D57_SEASON, finals)
        per_date: dict[_dt.date, int] = {}
        for g in finals:
            if weekday_of(g.official_date) in TUE_THU:
                per_date[g.official_date] = per_date.get(g.official_date, 0) + 1
        try:
            done = search_changeover(finals, rows, Puller(rows, allow_pull=False, max_requests=0))
            print(f"plan: nothing to pull; first key {done.first_key_date}")
        except MissingFeed as exc:
            print(f"plan: the first probe needs a pull: {exc}")
        steps = max(1, (len(per_date)).bit_length())
        print(
            f"plan: {len(per_date)} Tue/Wed/Thu dates in 2024; at most {steps} probes of "
            f"{PROBE_WIDTH} games plus two boundary days of at most {max(per_date.values())} "
            f"games; ceiling {args.max_requests} requests; budget {budget_used()}"
        )
        return 0

    before = budget_used()
    try:
        result = run(allow_pull=not args.check, max_requests=args.max_requests)
    except MissingFeed as exc:
        print(f"FAIL a feed the search reads is not on disk: {exc}")
        return 1
    after = budget_used()
    for line in _report(result):
        print(line)
    spent = after[1] - before[1] if after[0] == before[0] else f"{before} -> {after}"
    print(f"statsapi requests spent by this run (budget file delta): {spent}")

    failed = 0
    for path, text in result.texts.items():
        disk = path.read_text(encoding="utf-8") if path.exists() else None
        rel = path.relative_to(paths.REPO_ROOT)
        if args.check:
            same = disk == text
            print(f"{'PASS' if same else 'FAIL'} {rel} matches a rebuild")
            failed += not same
        elif disk == text:
            print(f"{rel} unchanged")
        else:
            tmp = path.with_suffix(".csv.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
            print(f"{rel} written, {len(text.encode()):,} bytes")
    for row in csv.DictReader(io.StringIO(result.texts[CHANGE_FILE])):
        print(f"{row['decision']} {row['status']}: {row['result']}")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    sys.exit(main())
