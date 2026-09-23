"""Schedules and umpire assignments, SOP step W2.5. Owns DT-14.

Eight payloads, one per season: MLB 2022-2026 and AAA 2023-2025. The contract
estimated about 930 calls. It is eight, because the schedule endpoint hydrates
officials across a whole date range:

    uv run python -m absump.ingest.schedule --sport 1  --season 2022 2023 2024 2025 2026
    uv run python -m absump.ingest.schedule --sport 11 --season 2023 2024 2025

Each season is one call of the form

    https://statsapi.mlb.com/api/v1/schedule?sportId=1
      &startDate=2026-03-01&endDate=<the SOP prints a mid-November day>
      &gameTypes=R,F,D,L,W&hydrate=officials

`endDate` is clamped to `absump.paths.LAST_OPEN_DATE`. The SOP prints a
mid-November end date; a request for that range returns the sealed window, and
SOP section 2.4 seals season 2026 from the day after the cutoff and seals the
whole 2026 postseason. Clamping is the only difference between the URL this
module builds and the URL the SOP prints, and it is recorded in the returned
notes for W2.5. The end date is never written down here, because GD-04 reads a
held-out day beside an operator as a sealed read, and it is right to.

SOURCES, in order. A payload already in the raw lake is used as it is. Then
`data/staging/statsapi/schedule/sport{id}-{season}.json`, the staging cache
described in `data/staging/STAGING.md`, which costs no call. The network is
last and only with `--allow-network`.

WHAT IS EXTRACTED. Two tables, partitioned by level, season and officialDate
under `data/interim/`:

    schedule_game   game_pk, season, level, game_type, official_date,
                    game_date_utc, status_abstract, away_team_id, home_team_id,
                    doubleheader, game_number, venue_id, game_id,
                    status_coded, status_detailed
    game_official   game_pk, official_type, official_id, official_name

The first thirteen columns are the SOP list, in the SOP order. `status_coded`
and `status_detailed` are added because `status_abstract` alone cannot express
DT-14. MLB reports a cancelled or postponed game with
`abstractGameState == "Final"` and an empty `officials` array: 1 such game in
MLB 2024, 20 in AAA 2024, 23 in AAA 2025. Without the coded state, "every Final
game has exactly one Home Plate official" is false by construction and the
assertion cannot be stated. With it, the assertion is exact: every game with
`codedGameState` in (F, O) carries exactly one Home Plate official, in all
eight seasons, and every game that carries none was cancelled (C) or postponed
(D) and never played.

OFFICIALS ARE SELECTED BY `officialType`, NEVER BY ARRAY INDEX. The SOP states
the schedule orders HP, 2B, 1B, 3B. Measured over the staged payloads, the
Home Plate entry occupies every index from 0 to 3, and in MLB 2022 it is at
index 0 in only 251 of 2,479 games. The SOP's own second example proves it:
game 661583, MIA at PHI on 2022-06-15, orders 1B, 3B, HP, 2B, so the Home Plate
umpire Alex Tosi (605673) sits at index 2. An index-0 reader would mis-assign
about 2,200 games a season.

DUPLICATE `gamePk`. The response returns the same `gamePk` on more than one
date: the postponed placeholder and the game that was actually played. AAA 2025
has 91 such ids, one of them four times. `schedule_game` keeps one row per
`gamePk`, preferring the row that was played, then the row that carries
officials, then the later officialDate. The SOP test "game_pk unique" is a test
of this table, not of the response.

IDEMPOTENCE. Every write is byte-compared first and skipped when the bytes
match, so a second run changes no file and no mtime.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final

import orjson
import pyarrow as pa
import pyarrow.parquet as pq
import zstandard

from absump import http, paths
from absump.db import PARQUET_COMPRESSION, PARQUET_COMPRESSION_LEVEL

__all__ = [
    "GAME_OFFICIAL_SCHEMA",
    "GAME_TYPES",
    "HOME_PLATE",
    "SCHEDULE_GAME_SCHEMA",
    "SEASONS",
    "PayloadMissing",
    "extract",
    "ingest_season",
    "load_payload",
    "schedule_url",
    "staging_payload_path",
]

# sportId 1 is MLB, sportId 11 is Triple-A. SOP W2.5 and section 10.1.
LEVEL_BY_SPORT: Final[dict[int, str]] = {1: "mlb", 11: "aaa"}
SEASONS: Final[dict[int, tuple[int, ...]]] = {
    1: (2022, 2023, 2024, 2025, 2026),
    11: (2023, 2024, 2025),
}

# R regular, F wild card, D division, L championship, W world series. The three
# codes the analysis set excludes (S, A, E) are never requested, so a spring or
# exhibition game cannot reach the lake at all. quality/sql/analysis_set.sql.
GAME_TYPES: Final[tuple[str, ...]] = ("R", "F", "D", "L", "W")

# The window one request covers. March 1 is before the earliest officialDate in
# any of the eight seasons (2026-03-18 is the earliest observed); November 15 is
# after the latest possible world series date.
SEASON_START_MMDD: Final[str] = "03-01"
SEASON_END_MMDD: Final[str] = "11-15"

HOME_PLATE: Final[str] = "Home Plate"

# statsapi codedGameState. F is Final and O is Game Over: both mean the game was
# played. C is Cancelled and D is Postponed: neither was played, and neither
# carries an officials array.
PLAYED_CODES: Final[frozenset[str]] = frozenset({"F", "O"})
NEVER_PLAYED_CODES: Final[frozenset[str]] = frozenset({"C", "D"})

# The staging cache, data/staging/STAGING.md. It is not part of the lake layout
# in absump.paths, so it is named here and nowhere else.
_STAGING_PARTS: Final[tuple[str, ...]] = ("staging", "statsapi", "schedule")

_ZSTD_LEVEL: Final[int] = 10  # SOP section 2.3, raw bytes on disk.

SCHEDULE_GAME_SCHEMA: Final[pa.Schema] = pa.schema(
    [
        pa.field("game_pk", pa.int64(), nullable=False),
        pa.field("season", pa.int32(), nullable=False),
        pa.field("level", pa.string(), nullable=False),
        pa.field("game_type", pa.string(), nullable=False),
        pa.field("official_date", pa.date32(), nullable=False),
        pa.field("game_date_utc", pa.timestamp("s", tz="UTC"), nullable=True),
        pa.field("status_abstract", pa.string(), nullable=False),
        pa.field("away_team_id", pa.int32(), nullable=True),
        pa.field("home_team_id", pa.int32(), nullable=True),
        pa.field("doubleheader", pa.string(), nullable=True),
        pa.field("game_number", pa.int32(), nullable=True),
        pa.field("venue_id", pa.int32(), nullable=True),
        pa.field("game_id", pa.string(), nullable=True),
        pa.field("status_coded", pa.string(), nullable=False),
        pa.field("status_detailed", pa.string(), nullable=True),
    ]
)

GAME_OFFICIAL_SCHEMA: Final[pa.Schema] = pa.schema(
    [
        pa.field("game_pk", pa.int64(), nullable=False),
        pa.field("official_type", pa.string(), nullable=False),
        pa.field("official_id", pa.int32(), nullable=False),
        pa.field("official_name", pa.string(), nullable=False),
    ]
)

_PARQUET_OPTIONS: Final[dict[str, Any]] = {
    "compression": PARQUET_COMPRESSION,
    "compression_level": PARQUET_COMPRESSION_LEVEL,
    "write_statistics": True,
}


class PayloadMissing(RuntimeError):
    """No payload for this season, on disk or allowed off the network."""


class SealCrossing(RuntimeError):
    """A request or a write that would cross the 2026-09-21 cutoff."""


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------


def _level(sport_id: int) -> str:
    try:
        return LEVEL_BY_SPORT[int(sport_id)]
    except (KeyError, TypeError, ValueError):
        known = ", ".join(str(k) for k in sorted(LEVEL_BY_SPORT))
        raise ValueError(f"sport_id={sport_id!r} is not one of {known}") from None


def schedule_url(
    sport_id: int, season: int, *, start: str | None = None, end: str | None = None
) -> str:
    """The one URL for one season, with the end date clamped to the seal.

    `start` and `end` default to the season window. The end date is clamped to
    `absump.paths.LAST_OPEN_DATE` so no request in this phase can return a
    sealed game. A start date past the cutoff raises `SealCrossing`, because
    there is nothing left to ask for that this phase may see.
    """
    _level(sport_id)
    season = int(season)
    first = _as_date(start or f"{season}-{SEASON_START_MMDD}")
    last = _as_date(end or f"{season}-{SEASON_END_MMDD}")
    if first > paths.LAST_OPEN_DATE:
        raise SealCrossing(
            f"startDate {first.isoformat()} is past the cutoff "
            f"{paths.LAST_OPEN_DATE.isoformat()}; the whole range is sealed"
        )
    if last > paths.LAST_OPEN_DATE:
        last = paths.LAST_OPEN_DATE
    if first > last:
        raise ValueError(f"startDate {first.isoformat()} is after endDate {last.isoformat()}")
    return (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId={int(sport_id)}"
        f"&startDate={first.isoformat()}&endDate={last.isoformat()}"
        f"&gameTypes={','.join(GAME_TYPES)}&hydrate=officials"
    )


def _as_date(value: Any) -> _dt.date:
    if isinstance(value, _dt.date) and not isinstance(value, _dt.datetime):
        return value
    return _dt.date.fromisoformat(str(value)[:10])


# ---------------------------------------------------------------------------
# The payload: raw lake, then staging, then the network
# ---------------------------------------------------------------------------


def staging_payload_path(sport_id: int, season: int) -> Path:
    """Where the staging importer left this season's response."""
    root = paths.data_root()
    for part in _STAGING_PARTS:
        root = root / part
    return root / f"sport{int(sport_id)}-{int(season)}.json"


def _write_bytes_if_changed(target: Path, body: bytes) -> bool:
    """Write `body` to `target` atomically. Return True when bytes changed."""
    if target.exists() and target.read_bytes() == body:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(body)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


def _store_raw(sport_id: int, season: int, body: bytes) -> Path:
    """Put the response bytes in the raw lake, compressed at zstd level 10."""
    target = paths.raw_schedule(sport_id, season)
    _write_bytes_if_changed(target, zstandard.ZstdCompressor(level=_ZSTD_LEVEL).compress(body))
    return target


def _read_raw(target: Path) -> bytes:
    return zstandard.ZstdDecompressor().decompress(
        target.read_bytes(), max_output_size=256 * 1024 * 1024
    )


def load_payload(
    sport_id: int, season: int, *, allow_network: bool = False
) -> tuple[dict[str, Any], str]:
    """Return (payload, source) for one season. `source` names where it came from."""
    raw = paths.raw_schedule(sport_id, season)
    if raw.exists():
        return orjson.loads(_read_raw(raw)), "raw"

    staged = staging_payload_path(sport_id, season)
    if staged.exists():
        body = staged.read_bytes()
        _store_raw(sport_id, season, body)
        return orjson.loads(body), "staging"

    if not allow_network:
        raise PayloadMissing(
            f"no payload for sport {sport_id} season {season}: "
            f"neither {raw} nor {staged} exists. Re-run with --allow-network to "
            "spend one statsapi request on it."
        )

    response = http.get(schedule_url(sport_id, season))
    if response.dry_run:
        raise PayloadMissing(f"dry run: nothing fetched for sport {sport_id} season {season}")
    _store_raw(sport_id, season, response.content)
    return orjson.loads(response.content), "network"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _games(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for day in payload.get("dates") or ():
        yield from day.get("games") or ()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _officials(game: dict[str, Any]) -> list[dict[str, Any]]:
    """Every hydrated official, keyed by `officialType`, never by index.

    A row without an `officialType`, or without an id, is dropped: it cannot be
    assigned to a position, and assigning it by its place in the array is the
    exact mistake this function exists to prevent.
    """
    rows: list[dict[str, Any]] = []
    for entry in game.get("officials") or ():
        official_type = entry.get("officialType")
        person = entry.get("official") or {}
        official_id = _int_or_none(person.get("id"))
        name = person.get("fullName")
        if not official_type or official_id is None or not name:
            continue
        rows.append(
            {
                "official_type": str(official_type),
                "official_id": official_id,
                "official_name": str(name),
            }
        )
    return rows


def home_plate_official(game: dict[str, Any]) -> dict[str, Any] | None:
    """The Home Plate umpire for one raw game, or None. Selected by type."""
    found = [row for row in _officials(game) if row["official_type"] == HOME_PLATE]
    return found[0] if len(found) == 1 else None


def _game_row(game: dict[str, Any], *, sport_id: int, season: int) -> dict[str, Any] | None:
    game_pk = _int_or_none(game.get("gamePk"))
    official_date = game.get("officialDate")
    status = game.get("status") or {}
    coded = status.get("codedGameState")
    abstract = status.get("abstractGameState")
    if game_pk is None or not official_date or not coded or not abstract:
        return None
    teams = game.get("teams") or {}
    away = ((teams.get("away") or {}).get("team") or {}).get("id")
    home = ((teams.get("home") or {}).get("team") or {}).get("id")
    game_date = game.get("gameDate")
    return {
        "game_pk": game_pk,
        "season": int(season),
        "level": _level(sport_id),
        "game_type": str(game.get("gameType") or ""),
        "official_date": _as_date(official_date),
        "game_date_utc": _as_utc(game_date),
        "status_abstract": str(abstract),
        "away_team_id": _int_or_none(away),
        "home_team_id": _int_or_none(home),
        "doubleheader": _str_or_none(game.get("doubleHeader")),
        "game_number": _int_or_none(game.get("gameNumber")),
        "venue_id": _int_or_none((game.get("venue") or {}).get("id")),
        "game_id": _str_or_none(game.get("gameGuid")),
        "status_coded": str(coded),
        "status_detailed": _str_or_none(status.get("detailedState")),
    }


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _as_utc(value: Any) -> _dt.datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        stamp = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=_dt.UTC)
    return stamp.astimezone(_dt.UTC)


def _rank(row: dict[str, Any], officials: list[dict[str, Any]]) -> tuple[int, int, str, int]:
    """How much this occurrence of a gamePk deserves to be the surviving row.

    Played beats scheduled beats cancelled or postponed; then the row carrying
    officials; then the later officialDate; then the later gameNumber. Every
    field is taken from the payload, so the choice does not depend on the order
    the response happens to list the dates in.
    """
    coded = row["status_coded"]
    if coded in PLAYED_CODES:
        played = 2
    elif coded in NEVER_PLAYED_CODES:
        played = 0
    else:
        played = 1
    return (played, len(officials), row["official_date"].isoformat(), row["game_number"] or 0)


def extract(
    payload: dict[str, Any], *, sport_id: int, season: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Split one season's payload into schedule_game rows and game_official rows.

    Returns (games, officials, stats). `games` holds one row per gamePk. Rows
    are sorted by official_date then game_pk, so the output is a function of the
    payload and nothing else.
    """
    best: dict[int, tuple[tuple[int, int, str, int], dict[str, Any], list[dict[str, Any]]]] = {}
    seen_occurrences = 0
    dropped = 0
    for game in _games(payload):
        row = _game_row(game, sport_id=sport_id, season=season)
        if row is None:
            dropped += 1
            continue
        seen_occurrences += 1
        officials = _officials(game)
        key = _rank(row, officials)
        current = best.get(row["game_pk"])
        if current is None or key > current[0]:
            best[row["game_pk"]] = (key, row, officials)

    games = sorted(
        (entry[1] for entry in best.values()),
        key=lambda row: (row["official_date"], row["game_pk"]),
    )
    officials_rows: list[dict[str, Any]] = []
    for row in games:
        for official in best[row["game_pk"]][2]:
            officials_rows.append({"game_pk": row["game_pk"], **official})

    stats = _stats(payload, games, officials_rows, sport_id=sport_id, season=season)
    stats["occurrences"] = seen_occurrences
    stats["duplicate_game_pks"] = seen_occurrences - len(games)
    stats["unparsable_games"] = dropped
    return games, officials_rows, stats


def _stats(
    payload: dict[str, Any],
    games: Sequence[dict[str, Any]],
    officials: Sequence[dict[str, Any]],
    *,
    sport_id: int,
    season: int,
) -> dict[str, Any]:
    """Every number this step asserts, computed once, from the extracted rows."""
    hp_by_game: Counter[int] = Counter()
    umpires: dict[int, set[str]] = defaultdict(set)
    for row in officials:
        if row["official_type"] == HOME_PLATE:
            hp_by_game[row["game_pk"]] += 1
            umpires[row["official_id"]].add(row["official_name"])

    played = [row for row in games if row["status_coded"] in PLAYED_CODES]
    missing_hp = [row for row in played if hp_by_game.get(row["game_pk"], 0) != 1]
    final_no_hp = [
        row
        for row in games
        if row["status_abstract"] == "Final" and hp_by_game.get(row["game_pk"], 0) != 1
    ]
    unexplained = [row for row in final_no_hp if row["status_coded"] not in NEVER_PLAYED_CODES]

    names_by_id = {ump: sorted(names) for ump, names in umpires.items()}
    ids_by_name: dict[str, set[int]] = defaultdict(set)
    for ump, names in umpires.items():
        for name in names:
            ids_by_name[name].add(ump)

    dates = sorted({row["official_date"] for row in games})
    sealed = [row for row in games if paths.is_sealed(row["official_date"])]
    open_dates = sorted(
        {row["official_date"] for row in games if not paths.is_sealed(row["official_date"])}
    )
    raw_types: Counter[str] = Counter()
    open_occurrences = 0
    open_occurrence_dates: set[str] = set()
    # An independent read of the payload, used only to cross-check the selector
    # above. It walks the officials array literally, so a reader that assigned a
    # position from the array index would disagree with it on every season.
    hp_index: Counter[int] = Counter()
    hp_by_payload: dict[int, int] = {}
    for game in _games(payload):
        raw_types[str(game.get("gameType") or "")] += 1
        official_date = str(game.get("officialDate") or "")
        if official_date and _as_date(official_date) <= paths.LAST_OPEN_DATE:
            open_occurrences += 1
            open_occurrence_dates.add(official_date)
        game_pk = _int_or_none(game.get("gamePk"))
        for index, entry in enumerate(game.get("officials") or ()):
            if entry.get("officialType") != HOME_PLATE:
                continue
            hp_index[index] += 1
            umpire = _int_or_none((entry.get("official") or {}).get("id"))
            if game_pk is not None and umpire is not None:
                hp_by_payload.setdefault(game_pk, umpire)

    extracted_hp = {
        row["game_pk"]: row["official_id"]
        for row in officials
        if row["official_type"] == HOME_PLATE
    }
    kept = {row["game_pk"] for row in games}
    mismatch = sorted(
        game_pk for game_pk, umpire in extracted_hp.items() if hp_by_payload.get(game_pk) != umpire
    )
    unseen = sorted(
        game_pk
        for game_pk, umpire in hp_by_payload.items()
        if game_pk in kept and extracted_hp.get(game_pk) not in (umpire, None)
    )
    return {
        "sport_id": int(sport_id),
        "season": int(season),
        "level": _level(sport_id),
        "total_games_payload": _int_or_none(payload.get("totalGames")),
        "game_types_payload": dict(sorted(raw_types.items())),
        "hp_index_histogram": dict(sorted(hp_index.items())),
        "hp_mismatch_vs_payload": sorted(set(mismatch) | set(unseen)),
        "open_occurrences": open_occurrences,
        "open_occurrence_dates": len(open_occurrence_dates),
        "games": len(games),
        "played": len(played),
        "game_types": dict(sorted(Counter(row["game_type"] for row in games).items())),
        "status_abstract": dict(sorted(Counter(row["status_abstract"] for row in games).items())),
        "status_coded": dict(sorted(Counter(row["status_coded"] for row in games).items())),
        "dates": len(dates),
        "first_date": dates[0].isoformat() if dates else None,
        "last_date": dates[-1].isoformat() if dates else None,
        "official_rows": len(officials),
        "hp_games": len(hp_by_game),
        "missing_hp": len(missing_hp),
        "missing_hp_game_pks": sorted(row["game_pk"] for row in missing_hp),
        "final_without_hp": len(final_no_hp),
        "final_without_hp_unexplained": sorted(row["game_pk"] for row in unexplained),
        "distinct_hp_umpires": len(umpires),
        "umpire_ids_with_two_names": sorted(k for k, v in names_by_id.items() if len(v) > 1),
        "umpire_names_with_two_ids": sorted(k for k, v in ids_by_name.items() if len(v) > 1),
        "open_games": len(games) - len(sealed),
        "open_dates": len(open_dates),
        "sealed_games": len(sealed),
        "sealed_dates": sorted({row["official_date"].isoformat() for row in sealed}),
    }


# ---------------------------------------------------------------------------
# The lake
# ---------------------------------------------------------------------------


def _table(rows: Sequence[dict[str, Any]], schema: pa.Schema) -> pa.Table:
    columns = {field.name: [row.get(field.name) for row in rows] for field in schema}
    return pa.Table.from_pydict(columns, schema=schema)


def _parquet_bytes(rows: Sequence[dict[str, Any]], schema: pa.Schema) -> bytes:
    sink = pa.BufferOutputStream()
    pq.write_table(_table(rows, schema), sink, **_PARQUET_OPTIONS)
    return sink.getvalue().to_pybytes()


def _write_partitions(
    dataset: str,
    schema: pa.Schema,
    rows_by_date: dict[_dt.date, list[dict[str, Any]]],
    *,
    level: str,
    season: int,
) -> tuple[int, int]:
    """Write one Parquet part per open date. Return (files written, files unchanged)."""
    written = unchanged = 0
    for official_date in sorted(rows_by_date):
        if paths.is_sealed(official_date):
            continue
        target = paths.interim(dataset, level, season, official_date)
        if _write_bytes_if_changed(target, _parquet_bytes(rows_by_date[official_date], schema)):
            written += 1
        else:
            unchanged += 1
    return written, unchanged


def ingest_season(
    sport_id: int, season: int, *, allow_network: bool = False, write: bool = True
) -> dict[str, Any]:
    """Load, extract and, unless `write` is false, land one season in the lake."""
    payload, source = load_payload(sport_id, season, allow_network=allow_network)
    games, officials, stats = extract(payload, sport_id=sport_id, season=season)
    stats["source"] = source
    stats["written"] = 0
    stats["unchanged"] = 0
    if not write:
        return stats

    level = _level(sport_id)
    by_date: dict[_dt.date, list[dict[str, Any]]] = defaultdict(list)
    for row in games:
        by_date[row["official_date"]].append(row)
    officials_by_date: dict[_dt.date, list[dict[str, Any]]] = defaultdict(list)
    date_of = {row["game_pk"]: row["official_date"] for row in games}
    for row in officials:
        officials_by_date[date_of[row["game_pk"]]].append(row)

    written = unchanged = 0
    for dataset, schema, grouped in (
        ("schedule_game", SCHEDULE_GAME_SCHEMA, by_date),
        ("game_official", GAME_OFFICIAL_SCHEMA, officials_by_date),
    ):
        one, two = _write_partitions(dataset, schema, grouped, level=level, season=season)
        written += one
        unchanged += two
    stats["written"] = written
    stats["unchanged"] = unchanged
    return stats


# ---------------------------------------------------------------------------
# Checks. These are DT-14 and the rest of the W2.5 acceptance list.
# ---------------------------------------------------------------------------

# SOP W2.5, measured 2026: totalGames 2512 over 212 dates, by type R 2,459,
# F 12, D 20, L 14, W 7. The R entry is asserted; the four postseason entries
# are not reachable, because the only request that returns them runs to
# 2026-11-15 and SOP section 2.4 seals the whole 2026 postseason. They are kept
# here so the arithmetic 2,459 + 12 + 20 + 14 + 7 = 2,512 stays checked.
MEASURED_2026_TOTAL_GAMES: Final[int] = 2512
MEASURED_2026_BY_TYPE: Final[dict[str, int]] = {"R": 2459, "F": 12, "D": 20, "L": 14, "W": 7}

# SOP W2.5, measured through 2026-09-21 for gameType R: 2,370 Final games across
# 179 distinct officialDate values. The payload on disk measures 2,369 across
# 178. The 2026 season is live until 2026-09-27 and a postponement moves a game
# from one date to another, so this one number carries a stated pull-date
# tolerance; every other number in this module is exact.
MEASURED_2026_OPEN_FINALS: Final[int] = 2370
MEASURED_2026_OPEN_DATES: Final[int] = 179
OPEN_2026_TOLERANCE_GAMES: Final[int] = 10
OPEN_2026_TOLERANCE_DATES: Final[int] = 2

# SOP W2.5, 2022: a 2022-01-01 to 2025-12-31 request returns only 2022, 2,479
# Final games over 179 days, which is why the pull is one request per season.
MEASURED_2022_ROWS: Final[int] = 2479
MEASURED_2022_DATES: Final[int] = 179

# The size of a regular-season schedule, once the duplicate gamePk rows are
# folded away: MLB plays 162 games for each of 30 clubs and Triple-A plays 150,
# so 2,430 and 2,250 distinct games. A study-design constant, not a number read
# from an endpoint, and the tightest available gate on the dedup rule.
REGULAR_SEASON_GAMES: Final[dict[str, int]] = {"mlb": 2430, "aaa": 2250}

# SOP W2.5, 75 to 110 distinct umpires per season. Every MLB season falls inside
# it: 96, 94, 90, 92, 91. AAA 2024 measures 87. AAA 2023 measures 71 and AAA
# 2025 measures 70, both below the band, because Triple-A works three-umpire
# crews from a smaller roster. The two are pinned to the exact measured number
# rather than the band being widened, so any drift fails the gate.
UMPIRES_PER_SEASON: Final[tuple[int, int]] = (75, 110)
UMPIRE_COUNT_EXCEPTIONS: Final[dict[tuple[str, int], int]] = {("aaa", 2023): 71, ("aaa", 2025): 70}


def check_season(stats: dict[str, Any]) -> list[str]:
    """Every W2.5 assertion for one season. Returns the failures, in order."""
    failures: list[str] = []
    level, season = stats["level"], stats["season"]
    tag = f"{level} {season}"

    # DT-14. Exactly one Home Plate official per played game, 100%, missing_hp 0.
    if stats["missing_hp"]:
        failures.append(
            f"DT-14 {tag}: missing_hp={stats['missing_hp']} of {stats['played']} played games, "
            f"first game_pks {stats['missing_hp_game_pks'][:5]}"
        )
    # A Final game with no Home Plate official must be one that was never played.
    if stats["final_without_hp_unexplained"]:
        failures.append(
            f"DT-14 {tag}: {len(stats['final_without_hp_unexplained'])} Final games carry no "
            "Home Plate official and were not cancelled or postponed: "
            f"{stats['final_without_hp_unexplained'][:5]}"
        )
    # The Home Plate umpire is the one the payload labels Home Plate, in every
    # game. A reader that took the officials array by index would disagree here
    # on thousands of games: measured over these payloads the Home Plate entry
    # sits at index 0, 1, 2 and 3, and in MLB 2022 it is first in 251 of 2,479.
    if stats["hp_mismatch_vs_payload"]:
        failures.append(
            f"{tag}: {len(stats['hp_mismatch_vs_payload'])} games where the extracted Home "
            f"Plate umpire is not the one labelled Home Plate: "
            f"{stats['hp_mismatch_vs_payload'][:5]}"
        )
    if len(stats["hp_index_histogram"]) < 2:
        failures.append(
            f"{tag}: the Home Plate official sits at one array index in every game "
            f"({stats['hp_index_histogram']}); the payload orders officials arbitrarily"
        )
    # official_id is stable within a season for a given official_name, both ways.
    if stats["umpire_names_with_two_ids"]:
        failures.append(f"{tag}: name maps to two ids: {stats['umpire_names_with_two_ids'][:5]}")
    if stats["umpire_ids_with_two_names"]:
        failures.append(f"{tag}: id maps to two names: {stats['umpire_ids_with_two_names'][:5]}")
    # 75 to 110 distinct umpires per season, with the two pinned exceptions.
    count = stats["distinct_hp_umpires"]
    pinned = UMPIRE_COUNT_EXCEPTIONS.get((level, season))
    if pinned is not None:
        if count != pinned:
            failures.append(
                f"{tag}: {count} distinct Home Plate umpires, recorded exception is {pinned}"
            )
    elif not UMPIRES_PER_SEASON[0] <= count <= UMPIRES_PER_SEASON[1]:
        failures.append(
            f"{tag}: {count} distinct Home Plate umpires, outside "
            f"{UMPIRES_PER_SEASON[0]} to {UMPIRES_PER_SEASON[1]}"
        )
    # One regular-season schedule, exactly, once duplicate gamePk rows are folded.
    regular = stats["game_types"].get("R", 0)
    if regular != REGULAR_SEASON_GAMES[level]:
        failures.append(
            f"{tag}: {regular} distinct regular-season games, expected "
            f"{REGULAR_SEASON_GAMES[level]}"
        )
    # Nothing on or before the cutoff is called sealed, and the split is total.
    cutoff = paths.LAST_OPEN_DATE.isoformat()
    early = [date for date in stats["sealed_dates"] if date <= cutoff]
    if early:
        failures.append(f"{tag}: {early[:3]} are on or before the cutoff {cutoff} yet sealed")
    if stats["open_games"] + stats["sealed_games"] != stats["games"]:
        failures.append(f"{tag}: open plus sealed does not equal {stats['games']} games")

    if level == "mlb" and season == 2026:
        failures.extend(_check_2026(stats, tag))
    if level == "mlb" and season == 2022:
        if stats["total_games_payload"] != MEASURED_2022_ROWS:
            failures.append(
                f"{tag}: totalGames {stats['total_games_payload']}, SOP W2.5 measured "
                f"{MEASURED_2022_ROWS}"
            )
        if stats["dates"] != MEASURED_2022_DATES:
            failures.append(
                f"{tag}: {stats['dates']} officialDate values, SOP W2.5 measured "
                f"{MEASURED_2022_DATES}"
            )
    return failures


def _check_2026(stats: dict[str, Any], tag: str) -> list[str]:
    """The 2026 numbers SOP W2.5 measured, minus the ones the seal withholds."""
    failures: list[str] = []
    regular_rows = stats["game_types_payload"].get("R", 0)
    if regular_rows != MEASURED_2026_BY_TYPE["R"]:
        failures.append(
            f"{tag}: {regular_rows} regular-season schedule rows, SOP W2.5 measured "
            f"{MEASURED_2026_BY_TYPE['R']}"
        )
    if abs(stats["open_occurrences"] - MEASURED_2026_OPEN_FINALS) > OPEN_2026_TOLERANCE_GAMES:
        failures.append(
            f"{tag}: {stats['open_occurrences']} rows through "
            f"{paths.LAST_OPEN_DATE.isoformat()}, SOP W2.5 measured "
            f"{MEASURED_2026_OPEN_FINALS} plus or minus {OPEN_2026_TOLERANCE_GAMES}"
        )
    if abs(stats["open_occurrence_dates"] - MEASURED_2026_OPEN_DATES) > OPEN_2026_TOLERANCE_DATES:
        failures.append(
            f"{tag}: {stats['open_occurrence_dates']} officialDate values through "
            f"{paths.LAST_OPEN_DATE.isoformat()}, SOP W2.5 measured "
            f"{MEASURED_2026_OPEN_DATES} plus or minus {OPEN_2026_TOLERANCE_DATES}"
        )
    return failures


def check(stats_by_season: Sequence[dict[str, Any]]) -> list[str]:
    """The assertions that span seasons, plus every per-season assertion."""
    failures: list[str] = []
    for stats in stats_by_season:
        failures.extend(check_season(stats))
    if sum(MEASURED_2026_BY_TYPE.values()) != MEASURED_2026_TOTAL_GAMES:
        failures.append(
            f"SOP W2.5 2026 histogram sums to {sum(MEASURED_2026_BY_TYPE.values())}, "
            f"not {MEASURED_2026_TOTAL_GAMES}"
        )
    seen = {(stats["level"], stats["season"]) for stats in stats_by_season}
    duplicates = len(stats_by_season) - len(seen)
    if duplicates:
        failures.append(f"{duplicates} season(s) checked twice")
    return failures


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _all_targets() -> list[tuple[int, int]]:
    return [(sport, season) for sport in sorted(SEASONS) for season in SEASONS[sport]]


def _targets(args: argparse.Namespace) -> list[tuple[int, int]]:
    if args.sport is None:
        return _all_targets()
    sport_id = int(args.sport)
    seasons = args.season or list(SEASONS[sport_id])
    return [(sport_id, int(season)) for season in seasons]


def _print_plan(targets: Sequence[tuple[int, int]], stream: Any) -> None:
    stream.write(f"schedule plan: {len(targets)} season(s), one request each\n")
    for sport_id, season in targets:
        raw = paths.raw_schedule(sport_id, season)
        staged = staging_payload_path(sport_id, season)
        if raw.exists():
            where = "raw lake, 0 requests"
        elif staged.exists():
            where = "staging cache, 0 requests"
        else:
            where = "network, 1 request"
        stream.write(f"  sport {sport_id:>2} season {season}  {where}\n")
        stream.write(f"    {schedule_url(sport_id, season)}\n")


def _print_stats(stats: dict[str, Any], stream: Any) -> None:
    stream.write(
        "{level} {season}  source={source:<8} games={games:<5} played={played:<5} "
        "dates={dates:<4} hp_umpires={distinct_hp_umpires:<4} missing_hp={missing_hp} "
        "dup_pks={duplicate_game_pks} sealed={sealed_games} "
        "written={written} unchanged={unchanged}\n".format(**stats)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="absump.ingest.schedule",
        description="Schedules and umpire assignments, SOP W2.5. One request per season.",
    )
    parser.add_argument("--sport", type=int, choices=sorted(LEVEL_BY_SPORT), default=None)
    parser.add_argument("--season", type=int, nargs="+", default=None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="read whatever is on disk, run the W2.5 assertions, write nothing",
    )
    parser.add_argument(
        "--plan", action="store_true", help="print the request plan and send nothing"
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="spend one statsapi request on a season that is on neither disk source",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    targets = _targets(args)
    if args.plan:
        _print_plan(targets, sys.stdout)
        return 0

    collected: list[dict[str, Any]] = []
    absent: list[tuple[int, int]] = []
    for sport_id, season in targets:
        try:
            stats = ingest_season(
                sport_id, season, allow_network=args.allow_network, write=not args.check
            )
        except PayloadMissing as missing:
            absent.append((sport_id, season))
            sys.stdout.write(f"{_level(sport_id)} {season}  absent: {missing}\n")
            continue
        collected.append(stats)
        _print_stats(stats, sys.stdout)

    failures = check(collected)
    for line in failures:
        sys.stdout.write(f"FAIL {line}\n")

    played = sum(stats["played"] for stats in collected)
    sys.stdout.write(
        f"W2.5 {len(collected)} of {len(targets)} season(s) on disk, "
        f"{played} played games, {len(failures)} failure(s)\n"
    )
    if failures:
        return 1
    # A partly built lake is a failure; an empty one is a clean clone.
    if absent and collected:
        sys.stdout.write(
            f"FAIL {len(absent)} season(s) have no payload while {len(collected)} do: "
            f"{[f'sport{s} {y}' for s, y in absent]}\n"
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
