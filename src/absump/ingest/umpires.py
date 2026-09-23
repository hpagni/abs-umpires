"""Umpire assignments resolved to the per-game home-plate umpire. SOP step W6.2.

W6.2 has no body paragraph of its own. It is two canonical lines,

    W6.2  umpire assignments  -> W2.5
    W2.5 / W6.2 schedule and umpire pulls, five calls, one per season.

plus the `game_official` half of W2.5. W2.5 owns the call and the two interim
tables. W6.2 owns what the study actually runs on: one home-plate umpire per
played game, and the season-level counts published to
`out/tables/umpire_season_counts.csv`.

INPUT. `data/interim/game_official` and `data/interim/schedule_game`, written by
`absump.ingest.schedule`. Nothing here sends anything; both tables are already on
disk and the module reads them and nothing else. The raw season payloads in
`data/raw/statsapi/schedule` are read too, but only as a control (see below).

SELECTION IS BY `officialType`, NEVER BY ARRAY INDEX. The schedule orders the
crew HP, 2B, 1B, 3B and the boxscore orders it HP, 1B, 2B, 3B, so a reader that
takes element 0 silently returns a base umpire and never raises. Measured over
the eight payloads on disk, the Home Plate entry sits at every index from 0 to 3
and an index-0 reader names the wrong umpire in 1,123 to 2,184 games a season:
MLB 2022 2,184 of 2,430, MLB 2026 1,408 of 2,342, AAA 2024 1,126 of 2,232. That
is not a corner case, it is most of the study. `control_season` recomputes both
readings from the payload on every check, so the trap stays proved rather than
remembered, and the check fails if the Home Plate entry ever stops moving around
the array, because a fixed position is the one condition under which an index
read would look correct.

WHAT IS ASSERTED, per level and season:

  DT-14, regression refresh. Exactly one Home Plate official per played game,
  `missing_hp` 0. DT-14 is owned by W2.5 and is re-run here against the interim
  tables rather than the payload, so a defect introduced between the extractor
  and the table the study reads is caught on this side too.
  Stability. `official_id` is one-to-one with `official_name` inside a season,
  checked in both directions.
  Count. 75 to 110 distinct home-plate umpires per season, the band from W2.5.
  AAA 2023 and AAA 2025 sit below it, at 71 and 70, because Triple-A works
  three-umpire crews from a smaller roster. Both are pinned to the exact
  measured number in `schedule.UMPIRE_COUNT_EXCEPTIONS`, so drift still fails.
  Agreement. The umpire resolved from `game_official` equals the umpire the
  payload labels Home Plate, in every game, in every season.
  Seal. No resolved row falls after the cutoff in `paths.LAST_OPEN_DATE`. The
  interim writer drops sealed days, and the payload control drops them again, so
  the published counts are computed on open days only. For MLB 2026 the 90
  sealed rows carry no umpire who does not also appear on an open day, so the
  seal costs this table nothing: 91 distinct umpires either way.

Every measured number above is recomputed on each run and none of them is a
threshold in the code. The thresholds are the band and the two pinned AAA
counts, and both are imported from `absump.ingest.schedule` so this module and
W2.5 cannot drift apart.

IDEMPOTENCE. The CSV is rendered from sorted rows and written only when the
bytes differ, so a second run changes no file and no mtime. `--check` writes
nothing at all and requires the published file to equal the recomputed one byte
for byte.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import pyarrow.dataset as pads

from absump import paths
from absump.ingest import schedule

__all__ = [
    "CSV_COLUMNS",
    "SEASON_COUNTS_CSV",
    "InterimMissing",
    "band_status",
    "check",
    "control_season",
    "publish",
    "render_csv",
    "resolve_season",
    "season_counts",
    "targets",
]

SEASON_COUNTS_CSV: Final[Path] = paths.REPO_ROOT / "out" / "tables" / "umpire_season_counts.csv"

CSV_COLUMNS: Final[tuple[str, ...]] = (
    "level",
    "season",
    "games_played",
    "games_with_home_plate_umpire",
    "missing_home_plate",
    "distinct_umpires",
    "band_low",
    "band_high",
    "recorded_exception",
    "band_status",
    "max_games_one_umpire",
    "min_games_one_umpire",
    "first_official_date",
    "last_official_date",
)

# The two interim tables W2.5 writes.
GAME_TABLE: Final[str] = "schedule_game"
OFFICIAL_TABLE: Final[str] = "game_official"


class InterimMissing(RuntimeError):
    """One season has no interim partition on disk."""


# ---------------------------------------------------------------------------
# Reading the interim tables
# ---------------------------------------------------------------------------


def targets() -> list[tuple[int, int]]:
    """Every (sport_id, season) W2.5 lands, in a fixed order."""
    return [
        (sport, season) for sport in sorted(schedule.SEASONS) for season in schedule.SEASONS[sport]
    ]


def _season_dir(table: str, level: str, season: int) -> Path:
    """The `level=<level>/season=<season>` directory of one interim table."""
    anchor = paths.interim(table, level, season, _dt.date(int(season), 1, 1))
    return anchor.parent.parent


def _read_interim(table: str, level: str, season: int) -> list[dict[str, Any]]:
    """Every row of one interim table for one season, in stored order."""
    root = _season_dir(table, level, season)
    if not root.is_dir():
        raise InterimMissing(
            f"{table} has no partition for {level} {season} at {root}. "
            "Run absump.ingest.schedule first; W2.5 owns that table."
        )
    parts = sorted(root.glob("date=*/part-*.parquet"))
    if not parts:
        raise InterimMissing(f"{root} holds no part file")
    return pads.dataset([str(part) for part in parts], format="parquet").to_table().to_pylist()


def _as_date(value: Any) -> _dt.date:
    return paths.as_official_date(value)


# ---------------------------------------------------------------------------
# The resolution
# ---------------------------------------------------------------------------


def resolve_season(level: str, season: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One home-plate umpire per played game, plus every number W6.2 asserts.

    Returns (rows, stats). `rows` is one record per played game that carries
    exactly one Home Plate official, sorted by official_date then game_pk, so
    the output is a function of the tables on disk and of nothing else.
    """
    level = str(level)
    season = int(season)
    games = _read_interim(GAME_TABLE, level, season)
    officials = _read_interim(OFFICIAL_TABLE, level, season)

    # The one line this step exists for: the crew member whose officialType is
    # Home Plate. Never officials[0], never a position in the array.
    home_plate = [row for row in officials if row["official_type"] == schedule.HOME_PLATE]

    hp_by_game: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in home_plate:
        hp_by_game[row["game_pk"]].append(row)

    played = [row for row in games if row["status_coded"] in schedule.PLAYED_CODES]
    missing = [row for row in played if len(hp_by_game.get(row["game_pk"], ())) != 1]
    final_no_hp = [
        row
        for row in games
        if row["status_abstract"] == "Final" and len(hp_by_game.get(row["game_pk"], ())) != 1
    ]
    unexplained = [
        row for row in final_no_hp if row["status_coded"] not in schedule.NEVER_PLAYED_CODES
    ]

    rows: list[dict[str, Any]] = []
    for game in played:
        crew = hp_by_game.get(game["game_pk"], ())
        if len(crew) != 1:
            continue
        umpire = crew[0]
        rows.append(
            {
                "game_pk": game["game_pk"],
                "level": level,
                "season": season,
                "game_type": game["game_type"],
                "official_date": _as_date(game["official_date"]),
                "status_coded": game["status_coded"],
                "status_abstract": game["status_abstract"],
                "away_team_id": game["away_team_id"],
                "home_team_id": game["home_team_id"],
                "venue_id": game["venue_id"],
                "umpire_id": umpire["official_id"],
                "umpire_name": umpire["official_name"],
            }
        )
    rows.sort(key=lambda row: (row["official_date"], row["game_pk"]))

    names_by_id: dict[int, set[str]] = defaultdict(set)
    ids_by_name: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        names_by_id[row["umpire_id"]].add(row["umpire_name"])
        ids_by_name[row["umpire_name"]].add(row["umpire_id"])

    per_umpire = Counter(row["umpire_id"] for row in rows)
    dates = sorted({row["official_date"] for row in rows})
    stats = {
        "level": level,
        "season": season,
        "games": len(games),
        "played": len(played),
        "official_rows": len(officials),
        "home_plate_rows": len(home_plate),
        "resolved": len(rows),
        "missing_hp": len(missing),
        "missing_hp_game_pks": sorted(row["game_pk"] for row in missing),
        "final_without_hp_unexplained": sorted(row["game_pk"] for row in unexplained),
        "distinct_umpires": len(per_umpire),
        "names_with_two_ids": sorted(name for name, ids in ids_by_name.items() if len(ids) > 1),
        "ids_with_two_names": sorted(ump for ump, names in names_by_id.items() if len(names) > 1),
        "max_games_one_umpire": max(per_umpire.values(), default=0),
        "min_games_one_umpire": min(per_umpire.values(), default=0),
        "first_official_date": dates[0] if dates else None,
        "last_official_date": dates[-1] if dates else None,
        "sealed_rows": sum(1 for row in rows if paths.is_sealed(row["official_date"])),
        "duplicate_game_pks": len(rows) - len({row["game_pk"] for row in rows}),
    }
    return rows, stats


# ---------------------------------------------------------------------------
# The control: the same season read straight off the payload, two ways
# ---------------------------------------------------------------------------


def control_season(sport_id: int, season: int) -> dict[str, Any]:
    """Read the payload by officialType and by array index, and compare.

    The type reading is the answer. The index reading is the mistake this step
    exists to prevent, computed so the size of the mistake is in the evidence
    log rather than in a comment. Sealed days are dropped on both sides.
    """
    payload, source = schedule.load_payload(int(sport_id), int(season))
    by_type: dict[int, int] = {}
    by_index: dict[int, int | None] = {}
    index_histogram: Counter[int] = Counter()
    for day in payload.get("dates") or ():
        for game in day.get("games") or ():
            official_date = game.get("officialDate")
            if not official_date or paths.is_sealed(_as_date(official_date)):
                continue
            crew = list(game.get("officials") or ())
            positions = [
                index
                for index, entry in enumerate(crew)
                if entry.get("officialType") == schedule.HOME_PLATE
            ]
            if len(positions) != 1:
                continue
            game_pk = int(game["gamePk"])
            index_histogram[positions[0]] += 1
            by_type.setdefault(game_pk, int(crew[positions[0]]["official"]["id"]))
            first = crew[0].get("official") or {}
            by_index.setdefault(game_pk, first.get("id"))

    wrong = sum(1 for game_pk, umpire in by_type.items() if by_index.get(game_pk) != umpire)
    return {
        "sport_id": int(sport_id),
        "season": int(season),
        "level": schedule.LEVEL_BY_SPORT[int(sport_id)],
        "source": source,
        "open_games_with_home_plate": len(by_type),
        "home_plate_index_histogram": dict(sorted(index_histogram.items())),
        "index_zero_wrong": wrong,
        "by_type": by_type,
    }


# ---------------------------------------------------------------------------
# The published table
# ---------------------------------------------------------------------------


def band_status(level: str, season: int, distinct: int) -> tuple[str, int | None]:
    """(status, recorded exception) for one season's distinct-umpire count."""
    pinned = schedule.UMPIRE_COUNT_EXCEPTIONS.get((level, int(season)))
    low, high = schedule.UMPIRES_PER_SEASON
    if pinned is not None:
        return ("recorded_exception" if distinct == pinned else "out_of_band", pinned)
    return ("in_band" if low <= distinct <= high else "out_of_band", None)


def _csv_row(stats: dict[str, Any]) -> dict[str, str]:
    low, high = schedule.UMPIRES_PER_SEASON
    status, pinned = band_status(stats["level"], stats["season"], stats["distinct_umpires"])
    first, last = stats["first_official_date"], stats["last_official_date"]
    return {
        "level": stats["level"],
        "season": str(stats["season"]),
        "games_played": str(stats["played"]),
        "games_with_home_plate_umpire": str(stats["resolved"]),
        "missing_home_plate": str(stats["missing_hp"]),
        "distinct_umpires": str(stats["distinct_umpires"]),
        "band_low": str(low),
        "band_high": str(high),
        "recorded_exception": "" if pinned is None else str(pinned),
        "band_status": status,
        "max_games_one_umpire": str(stats["max_games_one_umpire"]),
        "min_games_one_umpire": str(stats["min_games_one_umpire"]),
        "first_official_date": first.isoformat() if first else "",
        "last_official_date": last.isoformat() if last else "",
    }


def season_counts() -> tuple[
    list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]], list[str]
]:
    """Resolve every season on disk. Returns (csv rows, stats, controls, absent).

    A season with no interim partition is reported, not raised on: an empty lake
    is a clean clone, and a lake holding seven seasons of eight is a defect. The
    caller decides which it is looking at.
    """
    csv_rows: list[dict[str, str]] = []
    collected: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    absent: list[str] = []
    for sport_id, season in targets():
        level = schedule.LEVEL_BY_SPORT[sport_id]
        try:
            rows, stats = resolve_season(level, season)
            control = control_season(sport_id, season)
        except (InterimMissing, schedule.PayloadMissing) as missing:
            absent.append(f"{level} {season}: {missing}")
            continue
        stats["resolved_rows"] = rows
        collected.append(stats)
        controls.append(control)
        csv_rows.append(_csv_row(stats))
    csv_rows.sort(key=lambda row: (row["level"], int(row["season"])))
    return csv_rows, collected, controls, absent


def render_csv(rows: Sequence[dict[str, str]]) -> str:
    """The published table, as bytes. No quoting: no field can hold a comma."""
    lines = [",".join(CSV_COLUMNS)]
    for row in rows:
        values = [row[column] for column in CSV_COLUMNS]
        bad = [value for value in values if "," in value or "\n" in value or '"' in value]
        if bad:
            raise ValueError(f"a field would need quoting: {bad!r}")
        lines.append(",".join(values))
    return "\n".join(lines) + "\n"


def publish(text: str, target: Path = SEASON_COUNTS_CSV) -> bool:
    """Write the table atomically, and only when the bytes change."""
    body = text.encode("utf-8")
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


# ---------------------------------------------------------------------------
# The assertions
# ---------------------------------------------------------------------------


def check_season(stats: dict[str, Any], control: dict[str, Any]) -> list[str]:
    """Every W6.2 assertion for one season. Returns the failures, in order."""
    failures: list[str] = []
    tag = f"{stats['level']} {stats['season']}"

    # DT-14, regression refresh. W2.5 owns it; this runs it again on the table
    # the study reads, not on the payload W2.5 read it from.
    if stats["missing_hp"]:
        failures.append(
            f"DT-14 {tag}: missing_hp={stats['missing_hp']} of {stats['played']} played games, "
            f"first game_pks {stats['missing_hp_game_pks'][:5]}"
        )
    if stats["final_without_hp_unexplained"]:
        failures.append(
            f"DT-14 {tag}: {len(stats['final_without_hp_unexplained'])} Final games carry no "
            "Home Plate official and were neither cancelled nor postponed: "
            f"{stats['final_without_hp_unexplained'][:5]}"
        )
    if stats["resolved"] != stats["played"]:
        failures.append(
            f"DT-14 {tag}: {stats['resolved']} games resolved out of {stats['played']} played"
        )
    if stats["duplicate_game_pks"]:
        failures.append(f"{tag}: {stats['duplicate_game_pks']} game_pk resolved more than once")

    # official_id is stable within a season for a given official_name, both ways.
    if stats["names_with_two_ids"]:
        failures.append(f"{tag}: one name, two ids: {stats['names_with_two_ids'][:5]}")
    if stats["ids_with_two_names"]:
        failures.append(f"{tag}: one id, two names: {stats['ids_with_two_names'][:5]}")

    # 75 to 110 distinct umpires per season, with the two pinned AAA counts.
    status, pinned = band_status(stats["level"], stats["season"], stats["distinct_umpires"])
    if status == "out_of_band":
        low, high = schedule.UMPIRES_PER_SEASON
        expected = f"the recorded exception {pinned}" if pinned is not None else f"{low} to {high}"
        failures.append(
            f"{tag}: {stats['distinct_umpires']} distinct home-plate umpires, expected {expected}"
        )

    # Selection by officialType, proved against the payload on every run.
    disagree = sorted(
        row["game_pk"]
        for row in stats["resolved_rows"]
        if control["by_type"].get(row["game_pk"]) != row["umpire_id"]
    )
    if disagree:
        failures.append(
            f"{tag}: {len(disagree)} games where the resolved umpire is not the one the payload "
            f"labels Home Plate: {disagree[:5]}"
        )
    if len(control["by_type"]) != stats["resolved"]:
        failures.append(
            f"{tag}: the payload carries {len(control['by_type'])} open games with a Home Plate "
            f"official, the interim table resolves {stats['resolved']}"
        )
    # A fixed position is the one condition under which an index read would look
    # correct. If the feed ever settles down, this assertion is the warning.
    if len(control["home_plate_index_histogram"]) < 2:
        failures.append(
            f"{tag}: the Home Plate official sits at one array index in every game "
            f"({control['home_plate_index_histogram']}); an index read would now be "
            "indistinguishable from a type read and this guard has stopped guarding"
        )
    if control["index_zero_wrong"] <= 0:
        failures.append(f"{tag}: an index-0 read names the right umpire in every game")

    # The seal. Nothing after the cutoff reaches the published counts.
    if stats["sealed_rows"]:
        failures.append(
            f"{tag}: {stats['sealed_rows']} resolved rows fall after "
            f"{paths.LAST_OPEN_DATE.isoformat()}"
        )
    last = stats["last_official_date"]
    if last is not None and paths.is_sealed(last):
        failures.append(f"{tag}: last official_date {last.isoformat()} is sealed")
    return failures


def check(
    stats_by_season: Sequence[dict[str, Any]], controls: Sequence[dict[str, Any]]
) -> list[str]:
    """Every per-season assertion, plus the ones that span seasons."""
    failures: list[str] = []
    for stats, control in zip(stats_by_season, controls, strict=True):
        failures.extend(check_season(stats, control))
    seen = {(stats["level"], stats["season"]) for stats in stats_by_season}
    if len(seen) != len(stats_by_season):
        failures.append(f"{len(stats_by_season) - len(seen)} season(s) checked twice")
    return failures


def check_published(text: str) -> list[str]:
    """Read the published table back and re-assert what it claims, on its own.

    This runs with no lake on disk, so a clean clone still gates the committed
    numbers against the band and the two recorded exceptions.
    """
    failures: list[str] = []
    if not SEASON_COUNTS_CSV.exists():
        return [f"{SEASON_COUNTS_CSV} does not exist"]
    published = SEASON_COUNTS_CSV.read_text(encoding="utf-8")
    lines = published.splitlines()
    if not lines or lines[0] != ",".join(CSV_COLUMNS):
        failures.append(f"{SEASON_COUNTS_CSV.name}: header is not the W6.2 column list")
        return failures
    for line in lines[1:]:
        values = line.split(",")
        if len(values) != len(CSV_COLUMNS):
            failures.append(f"{SEASON_COUNTS_CSV.name}: {len(values)} fields in {line!r}")
            continue
        row = dict(zip(CSV_COLUMNS, values, strict=True))
        tag = f"{row['level']} {row['season']}"
        distinct = int(row["distinct_umpires"])
        status, pinned = band_status(row["level"], int(row["season"]), distinct)
        if status != row["band_status"]:
            failures.append(
                f"{tag}: published band_status {row['band_status']}, recomputed {status}"
            )
        if status == "out_of_band":
            failures.append(f"{tag}: {distinct} distinct home-plate umpires is out of band")
        if (pinned is not None and row["recorded_exception"] != str(pinned)) or (
            pinned is None and row["recorded_exception"] != ""
        ):
            failures.append(f"{tag}: recorded_exception {row['recorded_exception']!r} is wrong")
        if int(row["missing_home_plate"]):
            failures.append(f"DT-14 {tag}: published missing_home_plate is not 0")
        if row["games_with_home_plate_umpire"] != row["games_played"]:
            failures.append(
                f"DT-14 {tag}: {row['games_with_home_plate_umpire']} of {row['games_played']} "
                "played games carry a home-plate umpire"
            )
        if paths.is_sealed(row["last_official_date"]):
            failures.append(f"{tag}: published last_official_date is sealed")
    if text and published != text:
        failures.append(f"{SEASON_COUNTS_CSV.name} differs from the table recomputed from the lake")
    return failures


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _print_stats(stats: dict[str, Any], control: dict[str, Any], stream: Any) -> None:
    stream.write(
        "{level} {season}  played={played:<5} resolved={resolved:<5} "
        "umpires={distinct_umpires:<4} missing_hp={missing_hp}  "
        "hp_index={index} index0_wrong={wrong}\n".format(
            index=control["home_plate_index_histogram"],
            wrong=control["index_zero_wrong"],
            **{key: value for key, value in stats.items() if key != "resolved_rows"},
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="absump.ingest.umpires",
        description=(
            "Resolve umpire assignments to the per-game home-plate umpire and publish "
            "out/tables/umpire_season_counts.csv. SOP W6.2. Reads local files only."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run the W6.2 assertions against whatever is on disk and write nothing",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    csv_rows, collected, controls, absent = season_counts()

    if not collected:
        # No interim table at all is a clean clone. The committed table still
        # gates, on its own arithmetic, with no data on disk.
        failures = check_published("")
        for line in failures:
            sys.stdout.write(f"FAIL {line}\n")
        sys.stdout.write(f"W6.2 no interim table on disk, {len(absent)} season(s) absent\n")
        sys.stdout.write(f"W6.2 published table checked alone, {len(failures)} failure(s)\n")
        return 1 if failures else 0

    for stats, control in zip(collected, controls, strict=True):
        _print_stats(stats, control, sys.stdout)

    text = render_csv(csv_rows)
    failures = check(collected, controls)
    if absent:
        failures.append(
            f"{len(absent)} season(s) have no interim table while {len(collected)} do: {absent[:3]}"
        )

    if not args.check:
        changed = publish(text)
        sys.stdout.write(
            f"W6.2 {SEASON_COUNTS_CSV.relative_to(paths.REPO_ROOT)} "
            f"{'rewritten' if changed else 'unchanged'}\n"
        )
    failures.extend(check_published(text))

    for line in failures:
        sys.stdout.write(f"FAIL {line}\n")
    resolved = sum(stats["resolved"] for stats in collected)
    sys.stdout.write(
        f"W6.2 {len(collected)} season(s), {resolved} games resolved to a home-plate umpire, "
        f"DT-14 missing_hp={sum(stats['missing_hp'] for stats in collected)}, "
        f"{len(failures)} failure(s)\n"
    )
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
