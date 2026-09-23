"""Path minting for the abs-umpires data lake (SOP W1.6).

This module is the only place in the repository where a lake path string is
written. Every other module asks for a path by name. A writer that assembles a
path by concatenating strings gets `SealViolation`, because concatenation is how
a sealed row reaches an open directory, or an open row reaches the sealed one,
with nothing on the way to catch it.

The Hive layout, rooted at `data_root()` (the gitignored `data/` directory
unless `ABS_DATA_ROOT` moves it to another volume):

    raw/statsapi/schedule/sport=1/season=2026/schedule.json.zst
    raw/statsapi/feed/sport=1/season=2026/date=2026-09-15/gamepk=824466.json.zst
    raw/statsapi/feed/sport=11/season=2024/date=2024-07-12/gamepk=753191.json.zst
    raw/statcast/level=mlb/season=2026/date=2026-09-15/pitches.csv.zst
    raw/statcast/level=aaa/season=2024/date=2024-07-12/pitches.csv.zst
    raw/savant/absdata/level=mlb/chal_type=batter/season=2026/page.html.zst
    raw/savant/abs_drawer/mlb_2026_147.json
    raw/retrosheet/plays/2025plays.zip
    interim/<dataset>/level=<mlb|aaa>/season=<yyyy>/date=<yyyy-mm-dd>/part-000.parquet
    marts/<name>.parquet
    tmp/                        DuckDB spill

`date` is always `officialDate`, never `gameDate`: a game that starts after
midnight UTC belongs to the day the schedule endpoint assigns it.

The warehouse file is `warehouse/abs.duckdb` under the repository root, not
under the data root, and it is gitignored (SOP section 2.1 resolution).
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Any, Final

__all__ = [
    "DUCKDB_PATH",
    "LAST_OPEN_DATE",
    "LEVELS",
    "REPO_ROOT",
    "SealViolation",
    "assert_minted",
    "data_root",
    "interim",
    "is_sealed",
    "lake_path",
    "mart",
    "minted_paths",
    "raw_feed",
    "raw_retrosheet_plays",
    "raw_savant_absdata",
    "raw_savant_drawer",
    "raw_schedule",
    "raw_statcast",
    "sealed_root",
    "templates",
    "tmp_dir",
]


class SealViolation(RuntimeError):
    """A path was built by hand instead of minted here.

    Raised when a caller passes a component that already contains a path
    separator or a Hive `key=value` marker, when a writer asks for the open
    lake with a sealed date, and when a path under the data root reaches a
    writer without having come from this module.
    """


REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

# The one copy of the layout. Every string below appears exactly once in this
# repository, here; `tests/unit/test_paths.py` reads this dict at runtime and
# greps the source tree to prove it. The two entries that name the warehouse
# file and the spill directory are additionally mirrored in
# `dbt/profiles.yml.example`, which SOP W1.6 names as their mirror.
_TEMPLATES: Final[dict[str, str]] = {
    "raw_schedule": "raw/statsapi/schedule/sport={sport_id}/season={season}/schedule.json.zst",
    "raw_feed": "raw/statsapi/feed/sport={sport_id}/season={season}/date={official_date}/gamepk={game_pk}.json.zst",  # noqa: E501
    "raw_statcast": "raw/statcast/level={level}/season={season}/date={game_date}/pitches.csv.zst",
    "raw_savant_absdata": "raw/savant/absdata/level={level}/chal_type={chal_type}/season={season}/page.html.zst",  # noqa: E501
    "raw_savant_drawer": "raw/savant/abs_drawer/{level}_{season}_{team_id}.json",
    "raw_retrosheet_plays": "raw/retrosheet/plays/{season}plays.zip",
    "interim": "interim/{dataset}/level={level}/season={season}/date={official_date}/part-{part:03d}.parquet",  # noqa: E501
    "sealed": "sealed/plain/{dataset}/level={level}/season={season}/date={official_date}/part-{part:03d}.parquet",  # noqa: E501
    "mart": "marts/{name}.parquet",
    # Short and generic on purpose; excluded from the uniqueness scan because a
    # bare "tmp" or "sealed" matches ordinary prose and the section 2.1 tree.
    "tmp": "tmp",
    "sealed_root": "sealed",
    "duckdb": "warehouse/abs.duckdb",
}

LEVELS: Final[tuple[str, ...]] = ("mlb", "aaa")

# The seal boundary. An officialDate on or before this day is open; a later one
# is sealed. GD-02 states the rule as `max_official_date > 2026-09-21`, and the
# dbt var `seal_start_date` is the day after this date. A study-design constant,
# not a number read from an endpoint (section 0.5 rule 4).
LAST_OPEN_DATE: Final[_dt.date] = _dt.date(2026, 9, 21)

DUCKDB_PATH: Final[Path] = REPO_ROOT / _TEMPLATES["duckdb"]

_MINTED: set[str] = set()

# Anything that says the caller already glued a path together. `=` is in the
# list because every Hive key is written here and nowhere else, so a component
# that carries one came from a hand-built fragment such as "level=mlb".
_CONCAT_MARKERS: Final[tuple[str, ...]] = ("/", "\\", os.sep, "=", "..", "\n", "\r", "\x00")


def templates() -> dict[str, str]:
    """A copy of the layout templates, for the uniqueness test."""
    return dict(_TEMPLATES)


def data_root() -> Path:
    """The lake root: `ABS_DATA_ROOT` when set, else `data/` under the repo."""
    override = os.environ.get("ABS_DATA_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT / "data"


def tmp_dir() -> Path:
    """The DuckDB spill directory."""
    return _mint(data_root() / _TEMPLATES["tmp"])


def sealed_root() -> Path:
    """The root under which sealed rows live until the W9.7 unseal ceremony."""
    return data_root() / _TEMPLATES["sealed_root"]


def _mint(path: Path) -> Path:
    _MINTED.add(str(path))
    return path


def minted_paths() -> frozenset[str]:
    """Every path this module has handed out in this process."""
    return frozenset(_MINTED)


def _component(value: Any, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} is empty")
    for marker in _CONCAT_MARKERS:
        if marker in text:
            raise SealViolation(
                f"{field}={value!r} carries {marker!r}, so it is a hand-built path "
                "fragment. Ask absump.paths for the whole path; never concatenate one."
            )
    return text


def _level(value: Any) -> str:
    text = _component(value, "level").lower()
    if text not in LEVELS:
        raise ValueError(f"level={value!r} is not one of {LEVELS}")
    return text


def _season(value: Any) -> str:
    text = _component(value, "season")
    try:
        year = int(text)
    except ValueError as exc:
        raise ValueError(f"season={value!r} is not a year") from exc
    if not 1900 <= year <= 2100:
        raise ValueError(f"season={value!r} is not a plausible season")
    return str(year)


def _positive_int(value: Any, field: str) -> str:
    text = _component(value, field)
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError(f"{field}={value!r} is not an integer") from exc
    if number <= 0:
        raise ValueError(f"{field}={value!r} is not positive")
    return str(number)


def as_official_date(value: Any) -> _dt.date:
    """Coerce a date, a datetime or an ISO `yyyy-mm-dd` string to a date."""
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = _component(value, "official_date") if not isinstance(value, str) else value.strip()
    try:
        return _dt.date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"official_date={value!r} is not an ISO yyyy-mm-dd date") from exc


def _date_str(value: Any) -> str:
    return as_official_date(value).isoformat()


def _part(value: Any) -> int:
    number = int(value)
    if number < 0:
        raise ValueError(f"part={value!r} is negative")
    return number


def is_sealed(official_date: Any) -> bool:
    """True when this officialDate falls inside the sealed window."""
    return as_official_date(official_date) > LAST_OPEN_DATE


def raw_schedule(sport_id: Any, season: Any) -> Path:
    """The compressed schedule response for one sport and season."""
    return _mint(
        data_root()
        / _TEMPLATES["raw_schedule"].format(
            sport_id=_positive_int(sport_id, "sport_id"), season=_season(season)
        )
    )


def raw_feed(sport_id: Any, season: Any, official_date: Any, game_pk: Any) -> Path:
    """The compressed GUMBO feed for one game. `official_date` is officialDate."""
    return _mint(
        data_root()
        / _TEMPLATES["raw_feed"].format(
            sport_id=_positive_int(sport_id, "sport_id"),
            season=_season(season),
            official_date=_date_str(official_date),
            game_pk=_positive_int(game_pk, "game_pk"),
        )
    )


def raw_statcast(level: Any, season: Any, game_date: Any) -> Path:
    """One day of compressed Statcast pitch rows at one level."""
    return _mint(
        data_root()
        / _TEMPLATES["raw_statcast"].format(
            level=_level(level), season=_season(season), game_date=_date_str(game_date)
        )
    )


def raw_savant_absdata(level: Any, chal_type: Any, season: Any) -> Path:
    """One compressed Savant ABS leaderboard page."""
    return _mint(
        data_root()
        / _TEMPLATES["raw_savant_absdata"].format(
            level=_level(level),
            chal_type=_component(chal_type, "chal_type"),
            season=_season(season),
        )
    )


def raw_savant_drawer(level: Any, season: Any, team_id: Any) -> Path:
    """One Savant challenge-drawer response, stored uncompressed."""
    return _mint(
        data_root()
        / _TEMPLATES["raw_savant_drawer"].format(
            level=_level(level),
            season=_season(season),
            team_id=_positive_int(team_id, "team_id"),
        )
    )


def raw_retrosheet_plays(season: Any) -> Path:
    """The Retrosheet play-by-play archive for one season."""
    return _mint(data_root() / _TEMPLATES["raw_retrosheet_plays"].format(season=_season(season)))


def interim(table: Any, level: Any, season: Any, date: Any, part: Any = 0) -> Path:
    """One interim Parquet part for an open day.

    A sealed officialDate raises `SealViolation`: sealed rows are routed by
    `lake_path`, which is the only function that knows the sealed branch.
    """
    official_date = as_official_date(date)
    if is_sealed(official_date):
        raise SealViolation(
            f"{official_date.isoformat()} is inside the sealed window "
            f"(after {LAST_OPEN_DATE.isoformat()}). Route it with lake_path()."
        )
    return _mint(
        data_root()
        / _TEMPLATES["interim"].format(
            dataset=_component(table, "table"),
            level=_level(level),
            season=_season(season),
            official_date=official_date.isoformat(),
            part=_part(part),
        )
    )


def mart(name: Any) -> Path:
    """One mart Parquet file."""
    return _mint(data_root() / _TEMPLATES["mart"].format(name=_component(name, "name")))


def lake_path(dataset: Any, level: Any, season: Any, official_date: Any, part: Any = 0) -> Path:
    """Route one day of one dataset to the open lake or to the sealed one.

    Sealed days land under `sealed_root()`, in the `plain` subtree that the
    W9.7 ceremony tars, encrypts and deletes (SOP: `tar -C data/sealed -cf -
    plain | age -p`). GD-10 asserts that subtree is gone, so nothing sealed is
    left in the clear once the seal closes.
    """
    day = as_official_date(official_date)
    key = "sealed" if is_sealed(day) else "interim"
    return _mint(
        data_root()
        / _TEMPLATES[key].format(
            dataset=_component(dataset, "dataset"),
            level=_level(level),
            season=_season(season),
            official_date=day.isoformat(),
            part=_part(part),
        )
    )


def _is_under(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root)
    except (AttributeError, ValueError):  # pragma: no cover - 3.12 always has it
        return str(path).startswith(str(root) + os.sep)


def assert_minted(path: str | os.PathLike[str]) -> Path:
    """Assert this path came from this module, and return it.

    Every writer calls this before it opens a file for writing. A path under
    the data root or the warehouse directory that this module did not mint was
    built by concatenation, so it raises `SealViolation`.
    """
    candidate = Path(path)
    if str(candidate) in _MINTED:
        return candidate
    resolved = candidate.expanduser().resolve()
    if str(resolved) in _MINTED:
        return resolved
    if _is_under(resolved, data_root()) or _is_under(resolved, DUCKDB_PATH.parent):
        raise SealViolation(
            f"{candidate} was not minted by absump.paths. A lake path that this module "
            "did not build is a path built by concatenation; ask for it by name instead."
        )
    raise ValueError(f"{candidate} is outside the data lake and the warehouse directory")


_mint(DUCKDB_PATH)
