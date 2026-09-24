"""Feed extraction. SOP step W2.13.

    uv run python -m absump.ingest.extract_feed --level mlb --season 2026 --procs 8

Reads the GUMBO feeds W2.6 and W2.8 put in the raw lake and writes four interim
Parquet datasets: `feed_pitch`, `feed_play`, `feed_game`, `feed_player`.
`feed_challenge` is W2.16 and is not written here.

No network. The input is `data/raw/statsapi/feed/sport={id}/season={yyyy}/
date={yyyy-mm-dd}/gamepk={pk}.json.zst` and nothing else. A feed that is not on
disk is not pulled; it is reported as missing and the run continues.

GRAIN AND THE KEY. `feed_pitch` is one row per pitch slot,
`(game_pk, at_bat_number, pitch_slot)`. The slot comes from
`absump.joinkey.pitch_keys`, which increments on `isPitch == true` or
`type == "no_pitch"` and ignores `action`, `pickoff` and `stepoff`. That is the
whole point of this step: the API's own `pitchNumber` repeats on a `no_pitch`
and is 0 on an intentional walk, so it cannot be a key. `feed_play` is one row
per `(game_pk, at_bat_index)`, zero-based, as the SOP states it. The two grains
differ by one on purpose, and `at_bat_number = at_bat_index + 1`.

NO CATCHER. There is no catcher on the play object. `liveData.linescore.
defense.catcher` is end-of-game defence only, so it is not read here. The
per-pitch catcher is Statcast `fielder_2`, which W2.14 carries.

PARALLELISM. The unit of work is one officialDate, not one game, because one
date is also one Parquet part. `--procs 8` runs eight dates at a time. Measured
on this corpus: `json.loads` on a 781 KB feed takes 5.4 ms, and the whole MLB
2026 corpus extracts and writes in about 6 minutes.

IDEMPOTENCE. Every part is built in memory, compared byte for byte against what
is already on disk, and written only when it differs. A second run changes no
file and no mtime. Rows are sorted by their grain before the table is built, so
the bytes do not depend on the order the files were read.

CHOICES RECORDED (SOP execution posture, autonomous defaults).
1. `event_type` is `playEvents[].type`, the discriminator that tells a `pitch`
   slot from a `no_pitch` slot. `details.eventType` names an action and is
   absent on a pitch, so it would be null on nearly every row of this table.
2. Every dataset carries `level`, `season` and `official_date` as columns as
   well as Hive partitions, matching `schedule_game` from W2.5. DuckDB keeps
   the file column when a Hive key has the same name, so nothing is duplicated
   at read time.
3. `primary_position` is the position abbreviation, such as C or SS.
4. Sealed days are routed by `absump.paths.lake_path`, never by hand. No sealed
   feed is in the raw lake, because W2.6's writer refuses to store one, so in
   practice every part this module writes lands under `interim/`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Final

import pyarrow as pa
import pyarrow.parquet as pq
import zstandard

from absump import paths
from absump.db import PARQUET_COMPRESSION, PARQUET_COMPRESSION_LEVEL
from absump.heights import height_inches
from absump.joinkey import pitch_keys

__all__ = [
    "DATASETS",
    "FEED_GAME_SCHEMA",
    "FEED_PITCH_SCHEMA",
    "FEED_PLAYER_SCHEMA",
    "FEED_PLAY_SCHEMA",
    "LEVEL_BY_SPORT",
    "SPORT_BY_LEVEL",
    "FeedUnreadable",
    "extract_day",
    "extract_feed",
    "extract_season",
    "feed_files",
    "load_feed",
    "main",
    "official_date",
]

# sportId 1 is MLB, sportId 11 is Triple-A. SOP W2.5 and section 10.1.
SPORT_BY_LEVEL: Final[dict[str, int]] = {"mlb": 1, "aaa": 11}
LEVEL_BY_SPORT: Final[dict[int, str]] = {1: "mlb", 11: "aaa"}

#: The four datasets this step writes. feed_challenge is W2.16.
DATASETS: Final[tuple[str, ...]] = ("feed_pitch", "feed_play", "feed_game", "feed_player")

_PARQUET_OPTIONS: Final[dict[str, Any]] = {
    "compression": PARQUET_COMPRESSION,
    "compression_level": PARQUET_COMPRESSION_LEVEL,
    "write_statistics": True,
}

_MAX_FEED_BYTES: Final[int] = 64 * 1024 * 1024

_TS: Final[pa.DataType] = pa.timestamp("ms", tz="UTC")

_PARTITION_FIELDS: Final[list[pa.Field]] = [
    pa.field("level", pa.string(), nullable=False),
    pa.field("season", pa.int32(), nullable=False),
    pa.field("official_date", pa.date32(), nullable=False),
]


def _f64(*names: str) -> list[pa.Field]:
    return [pa.field(name, pa.float64(), nullable=True) for name in names]


FEED_PITCH_SCHEMA: Final[pa.Schema] = pa.schema(
    [
        pa.field("game_pk", pa.int64(), nullable=False),
        pa.field("at_bat_number", pa.int32(), nullable=False),
        pa.field("pitch_slot", pa.int32(), nullable=False),
        pa.field("play_index", pa.int32(), nullable=False),
        pa.field("is_pitch", pa.bool_(), nullable=False),
        pa.field("event_type", pa.string(), nullable=True),
        pa.field("call_code", pa.string(), nullable=True),
        pa.field("call_description", pa.string(), nullable=True),
        pa.field("pitch_type_code", pa.string(), nullable=True),
        pa.field("is_strike", pa.bool_(), nullable=True),
        pa.field("is_ball", pa.bool_(), nullable=True),
        pa.field("is_in_play", pa.bool_(), nullable=True),
        pa.field("play_id", pa.string(), nullable=True),
        pa.field("start_time_utc", _TS, nullable=True),
        # pitchData
        *_f64(
            "start_speed",
            "end_speed",
            "strike_zone_top",
            "strike_zone_bottom",
            "strike_zone_width",
            "strike_zone_depth",
        ),
        pa.field("zone", pa.int32(), nullable=True),
        *_f64("type_confidence", "plate_time", "extension"),
        # pitchData.coordinates
        *_f64(
            "p_x",
            "p_z",
            "x0",
            "y0",
            "z0",
            "vx0",
            "vy0",
            "vz0",
            "ax",
            "ay",
            "az",
            "pfx_x",
            "pfx_z",
            "x",
            "y",
        ),
        # pitchData.breaks
        *_f64(
            "break_angle",
            "break_length",
            "break_y",
            "break_vertical",
            "break_vertical_induced",
            "break_horizontal",
        ),
        pa.field("spin_rate", pa.int32(), nullable=True),
        pa.field("spin_direction", pa.int32(), nullable=True),
        *_PARTITION_FIELDS,
    ]
)

FEED_PLAY_SCHEMA: Final[pa.Schema] = pa.schema(
    [
        pa.field("game_pk", pa.int64(), nullable=False),
        pa.field("at_bat_index", pa.int32(), nullable=False),
        pa.field("batter_id", pa.int32(), nullable=True),
        pa.field("bat_side", pa.string(), nullable=True),
        pa.field("pitcher_id", pa.int32(), nullable=True),
        pa.field("pitch_hand", pa.string(), nullable=True),
        pa.field("result_event_type", pa.string(), nullable=True),
        pa.field("result_description", pa.string(), nullable=True),
        pa.field("last_pitch_slot", pa.int32(), nullable=False),
        pa.field("about_has_review", pa.bool_(), nullable=False),
        *_PARTITION_FIELDS,
    ]
)

FEED_GAME_SCHEMA: Final[pa.Schema] = pa.schema(
    [
        pa.field("game_pk", pa.int64(), nullable=False),
        pa.field("has_abs_challenges", pa.bool_(), nullable=False),
        pa.field("away_used_successful", pa.int32(), nullable=True),
        pa.field("away_used_failed", pa.int32(), nullable=True),
        pa.field("away_remaining", pa.int32(), nullable=True),
        pa.field("home_used_successful", pa.int32(), nullable=True),
        pa.field("home_used_failed", pa.int32(), nullable=True),
        pa.field("home_remaining", pa.int32(), nullable=True),
        pa.field("review_has_challenges", pa.bool_(), nullable=True),
        pa.field("review_away_used", pa.int32(), nullable=True),
        pa.field("review_away_remaining", pa.int32(), nullable=True),
        pa.field("review_home_used", pa.int32(), nullable=True),
        pa.field("review_home_remaining", pa.int32(), nullable=True),
        pa.field("attendance", pa.int32(), nullable=True),
        pa.field("game_duration_minutes", pa.int32(), nullable=True),
        pa.field("first_pitch_utc", _TS, nullable=True),
        pa.field("venue_id", pa.int32(), nullable=True),
        *_PARTITION_FIELDS,
    ]
)

FEED_PLAYER_SCHEMA: Final[pa.Schema] = pa.schema(
    [
        pa.field("game_pk", pa.int64(), nullable=False),
        pa.field("player_id", pa.int32(), nullable=False),
        pa.field("height_raw", pa.string(), nullable=True),
        pa.field("height_in", pa.float64(), nullable=True),
        pa.field("weight", pa.int32(), nullable=True),
        pa.field("primary_position", pa.string(), nullable=True),
        *_PARTITION_FIELDS,
    ]
)

_SCHEMAS: Final[dict[str, pa.Schema]] = {
    "feed_pitch": FEED_PITCH_SCHEMA,
    "feed_play": FEED_PLAY_SCHEMA,
    "feed_game": FEED_GAME_SCHEMA,
    "feed_player": FEED_PLAYER_SCHEMA,
}

# The grain each dataset is sorted on before its part is written, so a part's
# bytes do not depend on the order the day's files were read.
_SORT_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "feed_pitch": ("game_pk", "at_bat_number", "pitch_slot"),
    "feed_play": ("game_pk", "at_bat_index"),
    "feed_game": ("game_pk",),
    "feed_player": ("game_pk", "player_id"),
}


class FeedUnreadable(RuntimeError):
    """One stored feed could not be decompressed or parsed."""


# ---------------------------------------------------------------------------
# Small readers. Every one of them returns None rather than raising, because a
# feed that is missing one optional block must still yield its other rows.
# ---------------------------------------------------------------------------


def _get(node: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _utc(value: Any) -> _dt.datetime | None:
    """Parse an ISO-8601 instant. The feed writes both `Z` and `.000Z` forms."""
    text = _str(value)
    if text is None:
        return None
    try:
        stamp = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=_dt.UTC)
    return stamp.astimezone(_dt.UTC)


# ---------------------------------------------------------------------------
# Row builders. One function per dataset.
# ---------------------------------------------------------------------------


def _pitch_row(key: tuple[int, int, int], event: Mapping[str, Any]) -> dict[str, Any]:
    game_pk, ab, slot = key
    details = event.get("details") or {}
    data = event.get("pitchData") or {}
    coords = data.get("coordinates") or {}
    breaks = data.get("breaks") or {}
    return {
        "game_pk": game_pk,
        "at_bat_number": ab,
        "pitch_slot": slot,
        "play_index": _int(event.get("index")),
        "is_pitch": event.get("isPitch") is True,
        "event_type": _str(event.get("type")),
        "call_code": _str(_get(details, "call", "code")),
        "call_description": _str(_get(details, "call", "description")),
        "pitch_type_code": _str(_get(details, "type", "code")),
        "is_strike": _bool(details.get("isStrike")),
        "is_ball": _bool(details.get("isBall")),
        "is_in_play": _bool(details.get("isInPlay")),
        "play_id": _str(event.get("playId")),
        "start_time_utc": _utc(event.get("startTime")),
        "start_speed": _float(data.get("startSpeed")),
        "end_speed": _float(data.get("endSpeed")),
        "strike_zone_top": _float(data.get("strikeZoneTop")),
        "strike_zone_bottom": _float(data.get("strikeZoneBottom")),
        "strike_zone_width": _float(data.get("strikeZoneWidth")),
        "strike_zone_depth": _float(data.get("strikeZoneDepth")),
        "zone": _int(data.get("zone")),
        "type_confidence": _float(data.get("typeConfidence")),
        "plate_time": _float(data.get("plateTime")),
        "extension": _float(data.get("extension")),
        "p_x": _float(coords.get("pX")),
        "p_z": _float(coords.get("pZ")),
        "x0": _float(coords.get("x0")),
        "y0": _float(coords.get("y0")),
        "z0": _float(coords.get("z0")),
        "vx0": _float(coords.get("vX0")),
        "vy0": _float(coords.get("vY0")),
        "vz0": _float(coords.get("vZ0")),
        "ax": _float(coords.get("aX")),
        "ay": _float(coords.get("aY")),
        "az": _float(coords.get("aZ")),
        "pfx_x": _float(coords.get("pfxX")),
        "pfx_z": _float(coords.get("pfxZ")),
        "x": _float(coords.get("x")),
        "y": _float(coords.get("y")),
        "break_angle": _float(breaks.get("breakAngle")),
        "break_length": _float(breaks.get("breakLength")),
        "break_y": _float(breaks.get("breakY")),
        "break_vertical": _float(breaks.get("breakVertical")),
        "break_vertical_induced": _float(breaks.get("breakVerticalInduced")),
        "break_horizontal": _float(breaks.get("breakHorizontal")),
        "spin_rate": _int(breaks.get("spinRate")),
        "spin_direction": _int(breaks.get("spinDirection")),
    }


def _play_row(play: Mapping[str, Any], game_pk: int, last_slot: int) -> dict[str, Any]:
    matchup = play.get("matchup") or {}
    result = play.get("result") or {}
    return {
        "game_pk": game_pk,
        "at_bat_index": _int(_get(play, "about", "atBatIndex")),
        "batter_id": _int(_get(matchup, "batter", "id")),
        "bat_side": _str(_get(matchup, "batSide", "code")),
        "pitcher_id": _int(_get(matchup, "pitcher", "id")),
        "pitch_hand": _str(_get(matchup, "pitchHand", "code")),
        "result_event_type": _str(result.get("eventType")),
        "result_description": _str(result.get("description")),
        "last_pitch_slot": last_slot,
        "about_has_review": _get(play, "about", "hasReview") is True,
    }


def _game_row(feed: Mapping[str, Any], game_pk: int) -> dict[str, Any]:
    game_data = feed.get("gameData") or {}
    abs_challenges = game_data.get("absChallenges") or {}
    review = game_data.get("review") or {}
    info = game_data.get("gameInfo") or {}
    return {
        "game_pk": game_pk,
        "has_abs_challenges": abs_challenges.get("hasChallenges") is True,
        "away_used_successful": _int(_get(abs_challenges, "away", "usedSuccessful")),
        "away_used_failed": _int(_get(abs_challenges, "away", "usedFailed")),
        "away_remaining": _int(_get(abs_challenges, "away", "remaining")),
        "home_used_successful": _int(_get(abs_challenges, "home", "usedSuccessful")),
        "home_used_failed": _int(_get(abs_challenges, "home", "usedFailed")),
        "home_remaining": _int(_get(abs_challenges, "home", "remaining")),
        "review_has_challenges": _bool(review.get("hasChallenges")),
        "review_away_used": _int(_get(review, "away", "used")),
        "review_away_remaining": _int(_get(review, "away", "remaining")),
        "review_home_used": _int(_get(review, "home", "used")),
        "review_home_remaining": _int(_get(review, "home", "remaining")),
        "attendance": _int(info.get("attendance")),
        "game_duration_minutes": _int(info.get("gameDurationMinutes")),
        "first_pitch_utc": _utc(info.get("firstPitch")),
        "venue_id": _int(_get(game_data, "venue", "id")),
    }


def _player_rows(feed: Mapping[str, Any], game_pk: int) -> list[dict[str, Any]]:
    players = _get(feed, "gameData", "players") or {}
    rows: list[dict[str, Any]] = []
    for person in players.values():
        player_id = _int(person.get("id"))
        if player_id is None:
            continue
        height_raw = _str(person.get("height"))
        rows.append(
            {
                "game_pk": game_pk,
                "player_id": player_id,
                "height_raw": height_raw,
                "height_in": height_inches(height_raw),
                "weight": _int(person.get("weight")),
                "primary_position": _str(_get(person, "primaryPosition", "abbreviation")),
            }
        )
    return rows


def official_date(feed: Mapping[str, Any]) -> _dt.date:
    """The feed's own officialDate, which is the day the lake files it under."""
    text = _str(_get(feed, "gameData", "datetime", "officialDate"))
    if text is None:
        raise FeedUnreadable("gameData.datetime.officialDate is absent")
    return _dt.date.fromisoformat(text)


def extract_feed(feed: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Every row of all four datasets for one game, unpartitioned.

    The pitch rows come from `absump.joinkey.pitch_keys`, one per pitch slot.
    `last_pitch_slot` on the play row is that play's highest slot, and 0 for a
    play that has none, such as a stolen base or a pitching change.
    """
    game_pk = int(_get(feed, "gameData", "game", "pk"))
    plays: Sequence[Mapping[str, Any]] = _get(feed, "liveData", "plays", "allPlays") or []
    pitch_rows: list[dict[str, Any]] = []
    play_rows: list[dict[str, Any]] = []
    for play in plays:
        last_slot = 0
        for key, event in pitch_keys(play, game_pk):
            pitch_rows.append(_pitch_row(key, event))
            last_slot = key[2]
        play_rows.append(_play_row(play, game_pk, last_slot))
    return {
        "feed_pitch": pitch_rows,
        "feed_play": play_rows,
        "feed_game": [_game_row(feed, game_pk)],
        "feed_player": _player_rows(feed, game_pk),
    }


# ---------------------------------------------------------------------------
# The lake
# ---------------------------------------------------------------------------


def load_feed(path: Path) -> dict[str, Any]:
    """Read one stored feed back from the raw lake."""
    try:
        with path.open("rb") as handle:
            reader = zstandard.ZstdDecompressor().stream_reader(handle)
            body = reader.read(_MAX_FEED_BYTES)
        return json.loads(body.decode("utf-8"))
    except (OSError, ValueError, zstandard.ZstdError) as exc:
        raise FeedUnreadable(f"{path}: {exc}") from exc


def _season_root(sport_id: int, season: int) -> Path:
    """The `sport=.../season=...` directory, derived from a minted path."""
    return paths.raw_feed(sport_id, season, paths.LAST_OPEN_DATE, 1).parents[1]


def feed_files(sport_id: int, season: int) -> dict[_dt.date, list[Path]]:
    """Every stored feed for one sport and season, grouped by officialDate."""
    root = _season_root(sport_id, season)
    by_date: dict[_dt.date, list[Path]] = {}
    if not root.is_dir():
        return by_date
    for path in sorted(root.glob("date=*/gamepk=*.json.zst")):
        try:
            day = _dt.date.fromisoformat(path.parent.name.split("=", 1)[1])
        except (IndexError, ValueError):
            continue
        by_date.setdefault(day, []).append(path)
    return {day: sorted(files) for day, files in sorted(by_date.items())}


def _table(rows: Sequence[Mapping[str, Any]], schema: pa.Schema) -> pa.Table:
    columns = {field.name: [row.get(field.name) for row in rows] for field in schema}
    return pa.Table.from_pydict(columns, schema=schema)


def _parquet_bytes(rows: Sequence[Mapping[str, Any]], schema: pa.Schema) -> bytes:
    sink = pa.BufferOutputStream()
    pq.write_table(_table(rows, schema), sink, **_PARQUET_OPTIONS)
    return sink.getvalue().to_pybytes()


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


def _stamp(rows: list[dict[str, Any]], *, level: str, season: int, day: _dt.date) -> None:
    for row in rows:
        row["level"] = level
        row["season"] = season
        row["official_date"] = day


def extract_day(
    sport_id: int,
    season: int,
    day: _dt.date,
    files: Sequence[Path] | None = None,
    *,
    write: bool = True,
) -> dict[str, Any]:
    """Extract one officialDate and write its four Parquet parts.

    One date is one part per dataset, so this function is the unit of parallel
    work and the unit of idempotence. A feed that will not decompress or parse
    is reported and skipped; it does not stop the day.
    """
    level = LEVEL_BY_SPORT[int(sport_id)]
    paths_for_day = list(files) if files is not None else feed_files(sport_id, season).get(day, [])
    collected: dict[str, list[dict[str, Any]]] = {name: [] for name in DATASETS}
    unreadable: list[str] = []
    misfiled = 0
    games = 0
    for path in paths_for_day:
        try:
            feed = load_feed(path)
            rows = extract_feed(feed)
            if official_date(feed) != day:
                misfiled += 1
        except (FeedUnreadable, KeyError, TypeError, ValueError) as exc:
            unreadable.append(f"{path.name}: {exc}")
            continue
        games += 1
        for name, part in rows.items():
            _stamp(part, level=level, season=season, day=day)
            collected[name].extend(part)

    written = unchanged = 0
    for name in DATASETS:
        rows = collected[name]
        if not rows:
            continue
        rows.sort(key=lambda row, keys=_SORT_KEYS[name]: tuple(row[key] for key in keys))
        target = paths.lake_path(name, level, season, day)
        if not write:
            continue
        if _write_bytes_if_changed(target, _parquet_bytes(rows, _SCHEMAS[name])):
            written += 1
        else:
            unchanged += 1

    stats: dict[str, Any] = {
        "date": day.isoformat(),
        "games": games,
        "written": written,
        "unchanged": unchanged,
        "unreadable": unreadable,
        "misfiled": misfiled,
    }
    for name in DATASETS:
        stats[name] = len(collected[name])
    return stats


def _day_task(payload: tuple[int, int, str, list[str], bool]) -> dict[str, Any]:
    """The process-pool entry point. Only picklable types cross the boundary."""
    sport_id, season, day_text, file_texts, write = payload
    day = _dt.date.fromisoformat(day_text)
    return extract_day(sport_id, season, day, [Path(text) for text in file_texts], write=write)


def extract_season(
    level: str,
    season: int,
    *,
    procs: int = 8,
    write: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Extract every stored feed for one level and season."""
    sport_id = SPORT_BY_LEVEL[level]
    by_date = feed_files(sport_id, season)
    if limit is not None:
        trimmed: dict[_dt.date, list[Path]] = {}
        taken = 0
        for day, files in by_date.items():
            if taken >= limit:
                break
            room = limit - taken
            trimmed[day] = files[:room]
            taken += len(trimmed[day])
        by_date = trimmed
    payloads = [
        (sport_id, season, day.isoformat(), [str(path) for path in files], write)
        for day, files in by_date.items()
    ]
    if not payloads:
        return _totals(level, season, [])
    workers = max(1, min(int(procs), len(payloads)))
    if workers == 1:
        days = [_day_task(payload) for payload in payloads]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            days = list(pool.map(_day_task, payloads))
    return _totals(level, season, days)


def _totals(level: str, season: int, days: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {
        "level": level,
        "season": season,
        "dates": len(days),
        "games": sum(int(day["games"]) for day in days),
        "written": sum(int(day["written"]) for day in days),
        "unchanged": sum(int(day["unchanged"]) for day in days),
        "misfiled": sum(int(day["misfiled"]) for day in days),
        "unreadable": [line for day in days for line in day["unreadable"]],
    }
    for name in DATASETS:
        totals[name] = sum(int(day[name]) for day in days)
    totals["days"] = [dict(day) for day in days]
    return totals


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def _format_totals(totals: Mapping[str, Any]) -> list[str]:
    lines = [
        f"{totals['level']} {totals['season']}: {totals['games']} games "
        f"across {totals['dates']} dates",
        "  " + "  ".join(f"{name} {totals[name]}" for name in DATASETS),
        f"  parts written {totals['written']}, unchanged {totals['unchanged']}",
    ]
    if totals["misfiled"]:
        lines.append(f"  officialDate disagrees with the stored day on {totals['misfiled']} feeds")
    for line in totals["unreadable"][:10]:
        lines.append(f"  unreadable {line}")
    if len(totals["unreadable"]) > 10:
        lines.append(f"  unreadable, and {len(totals['unreadable']) - 10} more")
    return lines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m absump.ingest.extract_feed",
        description="Extract feed_pitch, feed_play, feed_game and feed_player from "
        "the stored GUMBO feeds. SOP W2.13. No network.",
    )
    parser.add_argument("--level", choices=sorted(SPORT_BY_LEVEL), default="mlb")
    parser.add_argument("--season", type=int, nargs="+", default=[2026])
    parser.add_argument("--procs", type=int, default=8, help="parallel dates, default 8")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many feeds")
    parser.add_argument(
        "--dry-run", action="store_true", help="extract and count, write no Parquet"
    )
    parser.add_argument("--json", action="store_true", help="print the totals as JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    seasons: Iterable[int] = args.season
    failures = 0
    report: list[dict[str, Any]] = []
    for season in seasons:
        totals = extract_season(
            args.level,
            int(season),
            procs=int(args.procs),
            write=not args.dry_run,
            limit=args.limit,
        )
        report.append(totals)
        if totals["unreadable"] or totals["misfiled"]:
            failures += 1
        if not args.json:
            for line in _format_totals(totals):
                print(line)
    if args.json:
        print(json.dumps([{k: v for k, v in t.items() if k != "days"} for t in report], indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
