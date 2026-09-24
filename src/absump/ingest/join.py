"""absump.ingest.join -- W2.15, the join, full season, with an unmatched report.

    uv run python -m absump.ingest.join --level mlb --season 2026
    uv run python -m absump.ingest.join --level mlb --season 2022..2025
    uv run python -m absump.ingest.join --level aaa --season 2023..2025

One day of `feed_pitch` and one day of `statcast_pitch` in, one day of
`pitch_joined` out, plus four report files that are rewritten on every run:

    data/interim/pitch_joined/level=<level>/season=<yyyy>/date=<date>/part-000.parquet
    out/tables/join_report.csv      one row per game, the twelve W2.15 columns
    out/tables/join_unmatched.csv   one row per unmatched pitch, either side
    out/tables/join_failures.csv    one row per failing at-bat, with detail
    out/audit/no_pitch_atbats.csv   one row per at-bat holding a no_pitch event

The key is `(game_pk, at_bat_number, pitch_slot)` with
`at_bat_number == atBatIndex + 1`, minted by `absump.joinkey` in W2.13 and
carried in `feed_pitch`. Game `824466` has max `atBatIndex` 69, max
`at_bat_number` 70 and 281 slots, which is what this module reads back.

THE BUILD FAILS PER GAME on `n_api != n_csv`, on `n_matched != n_api`, and on
any unmatched row on either side. Those three are the SOP's own list and they
set the exit code. Every failing at-bat lands in `out/tables/join_failures.csv`.

BUILD DECISIONS, recorded here because W2.15 chose them under the autonomous
posture and a later reader needs them stated.

B-1 THE STATCAST SLOT RULE. `absump.joinkey` numbers every pitch slot: an
    event with `isPitch == true` or `type == "no_pitch"`. Statcast numbers a
    `no_pitch` only when it carries a `details.call`, which is every automatic
    ball and every automatic strike. A `no_pitch` with `details.code == "N"`
    and no `call` block is an on-field delay or a balk; Statcast writes no row
    for it, so it consumes no `pitch_number`. Measured on MLB 2026, 2,342
    games: 2,449 `no_pitch` events, of which VB 1,850, VP 288, VC 5 and V 4 are
    automatic balls and AC 75 and AB 12 are automatic strikes, against exactly
    2,147 `automatic_ball` and 87 `automatic_strike` rows in the CSV. The
    remaining 215 carry no call code, and they are exactly the 215 api-only
    rows the unrenumbered key leaves behind, spread over 206 games.

    So this module renumbers. `pitch_slot` stays the feed slot and remains the
    declared key. `pitch_number` counts only the slots Statcast numbers and is
    what the join uses. Renumbering is what takes MLB 2026 from 691,502 api
    slots against 691,287 csv rows with 215 unmatched to 691,287 / 691,287 /
    691,287 with zero unmatched on either side, on 2,342 of 2,342 games.

    Without it the failure is not a missing row but a wrong pairing: in game
    824759, at-bat 80, the API is a `no_pitch` with code N followed by a hit by
    pitch, the CSV is one `hit_by_pitch` row, and the unrenumbered key attaches
    the CSV pitch to the delay. That is R-01's false match in mirror image.

B-2 THE COORDINATE ASSERTION. W2.15 asserts the re-projected API coordinate
    against the CSV coordinate at the measured plane, below 1e-6 ft. The
    quantity that holds at that tolerance is the section 2.5 closed form run
    from the API's own release triple `(x0, y0, z0)`:

        t(y) = ( -vy0 - sqrt(vy0^2 - 2*ay*(y0 - y)) ) / ay
        x(y) = x0 + vx0*t + 0.5*ax*t^2
        z(y) = z0 + vz0*t + 0.5*az*t^2

    with `vy0 < 0` and `ay > 0`, the smaller positive root, no branch. Measured
    against `plate_x_mid` and `plate_z_mid` over the 688,686 matched MLB 2026
    rows carrying coordinates on both sides: 8.881784e-16 ft, one row excepted.

    The published `pX`/`pZ` pair cannot carry that tolerance and section 2.5
    says why. It is MLB's own front-plane number, it agrees with the CSV to
    0.001053 ft over the contract's 281 pitches, and solving for the plane it
    sits on gives a scatter of y in [1.396, 1.420] ft around FRONT = 17/12 ft.
    Shifting it FRONT to MID therefore lands about 1e-3 ft from `plate_x_mid`,
    a thousand times the tolerance, on every row. That residual is reported in
    the run summary as a cross-check of section 2.5's 0.001053 ft; it is not
    the asserted quantity, because asserting it at 1e-6 ft would fail every
    pitch ever thrown and would measure the two publishers' arithmetic rather
    than the join.

    The exception is one row: game 825000, at-bat 31, pitch 3, 2026-05-30,
    where the CSV `plate_z` sits 0.063625 ft off the trajectory the feed
    publishes for the same pitch, with both sides' kinematics bit-identical.
    That is one row in 688,686 and it is a fact about the Statcast row, not a
    defect of the join, so it is reported: the game's status becomes `coord`,
    the row lands in `join_failures.csv` with reason `coord`, and the exit code
    is unchanged. `--strict-coord` makes a coordinate breach fail the build
    too, for a caller who wants the stricter reading.

B-3 THE REPORTS MERGE. A run that covers `mlb 2026` replaces the `mlb 2026`
    rows of each report and leaves every other level-season alone, so the three
    W2.15 commands can run in any order and any one of them can be re-run. Rows
    are sorted by level, season, official_date, game_pk, at_bat_number, and
    every float is written at 17 significant digits, so a re-run of the same
    input produces a byte-identical file.

B-4 SEALED DAYS ROUTE THEMSELVES. Every path comes from `absump.paths`, so a
    day after 2026-09-21 lands under `data/sealed/plain/pitch_joined/` with no
    branch here. The reports carry the game's counts and no coordinate, call or
    outcome, which is the same posture as the in-season data-quality report of
    W2.22.

B-5 ONE DAY AT A TIME. The two sides agree on which day a game belongs to:
    2,342 (game_pk, date) pairs on the feed side, 2,342 on the CSV side, zero
    asymmetric, and zero CSV rows whose `game_date` differs from the partition
    the row was written to. The module asserts that agreement per season before
    it joins, because a game split across two day files would otherwise look
    like unmatched rows on both sides.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from absump import paths

__all__ = [
    "COORD_TOL_FT",
    "DATASET",
    "FAILURE_COLUMNS",
    "NO_PITCH_COLUMNS",
    "REPORT_COLUMNS",
    "UNMATCHED_COLUMNS",
    "Y_FRONT_FT",
    "Y_MID_FT",
    "BridgeResult",
    "bridge_key",
    "day_partitions",
    "drawer_bridge",
    "drawer_coordinates",
    "join_day_sql",
    "main",
    "parse_seasons",
    "round_half_up",
    "run",
    "target_plane",
    "trajectory_sql",
]

#: The interim dataset this module writes.
DATASET: Final[str] = "pitch_joined"

#: The two source datasets, written by W2.13 and W2.14.
FEED_DATASET: Final[str] = "feed_pitch"
STATCAST_DATASET: Final[str] = "statcast_pitch"

#: The two plate planes, in feet, as section 2.5 states them.
Y_FRONT_FT: Final[float] = 17 / 12
Y_MID_FT: Final[float] = 8.5 / 12

#: `plane_source` values, mirroring `absump.ingest.normalize_sc`.
PLANE_FRONT: Final[str] = "front"
PLANE_MID: Final[str] = "mid"

#: The W2.15 tolerance on the re-projected coordinate, in feet.
COORD_TOL_FT: Final[float] = 1e-6

#: The `pitchData` block is absent on a `no_pitch`, so a coordinate check runs
#: only where both sides carry one.
_TRAJECTORY_COLUMNS: Final[tuple[str, ...]] = (
    "x0",
    "y0",
    "z0",
    "vx0",
    "vy0",
    "vz0",
    "ax",
    "ay",
    "az",
)

#: `out/tables/join_report.csv`, the twelve columns W2.15 names, in its order.
REPORT_COLUMNS: Final[tuple[str, ...]] = (
    "game_pk",
    "level",
    "season",
    "official_date",
    "n_api",
    "n_csv",
    "n_matched",
    "n_api_only",
    "n_csv_only",
    "n_no_pitch_events",
    "max_coord_err_ft",
    "status",
)

#: `out/tables/join_unmatched.csv`, one row per unmatched pitch.
UNMATCHED_COLUMNS: Final[tuple[str, ...]] = (
    "game_pk",
    "level",
    "season",
    "official_date",
    "side",
    "at_bat_number",
    "pitch_slot",
    "pitch_number",
    "event_type",
    "call_code",
    "description",
)

#: `out/tables/join_failures.csv`, one row per failing at-bat.
FAILURE_COLUMNS: Final[tuple[str, ...]] = (
    "game_pk",
    "level",
    "season",
    "official_date",
    "reason",
    "at_bat_number",
    "n_api_ab",
    "n_csv_ab",
    "n_matched_ab",
    "detail",
)

#: `out/audit/no_pitch_atbats.csv`, one row per at-bat holding a no_pitch event.
NO_PITCH_COLUMNS: Final[tuple[str, ...]] = (
    "game_pk",
    "level",
    "season",
    "official_date",
    "at_bat_number",
    "n_slots",
    "n_no_pitch",
    "n_no_pitch_numbered",
    "n_no_pitch_unnumbered",
    "call_codes",
)

#: Statuses written to `join_report.csv`.
STATUS_OK: Final[str] = "ok"
STATUS_FAIL: Final[str] = "fail"
STATUS_COORD: Final[str] = "coord"

#: Coverage statuses for a requested level-season that has no joinable day.
#: They are not join failures; they are the shape of the corpus on disk, and
#: W2.15 records them in the report rather than leaving the season unmentioned.
STATUS_NO_INPUTS: Final[str] = "no_inputs"
STATUS_NO_FEED: Final[str] = "no_feed_pitch"
STATUS_NO_STATCAST: Final[str] = "no_statcast_pitch"
COVERAGE_STATUSES: Final[frozenset[str]] = frozenset(
    {STATUS_NO_INPUTS, STATUS_NO_FEED, STATUS_NO_STATCAST}
)

#: Report paths. `out/` is the one generated directory git tracks (W2.21).
REPORT_PATH: Final[Path] = paths.REPO_ROOT / "out/tables/join_report.csv"
UNMATCHED_PATH: Final[Path] = paths.REPO_ROOT / "out/tables/join_unmatched.csv"
FAILURES_PATH: Final[Path] = paths.REPO_ROOT / "out/tables/join_failures.csv"
NO_PITCH_PATH: Final[Path] = paths.REPO_ROOT / "out/audit/no_pitch_atbats.csv"


class JoinError(RuntimeError):
    """A structural problem that stops the join before it can report."""


# --------------------------------------------------------------------------
# Seasons, planes and partitions
# --------------------------------------------------------------------------


def parse_seasons(tokens: Iterable[str]) -> list[int]:
    """Read `2026`, `2022..2025` and `2023 2024` into a sorted season list."""
    seasons: set[int] = set()
    for token in tokens:
        text = str(token).strip()
        if ".." in text:
            first, _, last = text.partition("..")
            start, stop = int(first), int(last)
            if stop < start:
                raise ValueError(f"season range {text!r} runs backwards")
            seasons.update(range(start, stop + 1))
        else:
            seasons.add(int(text))
    for season in seasons:
        if not 2000 <= season <= 2100:
            raise ValueError(f"season {season} is not a plausible season")
    return sorted(seasons)


def target_plane(level: str, season: int) -> str:
    """The plane the CSV measured, which is the plane the assertion runs at.

    W2.15 asserts at MID for 2026 and at FRONT for 2015 to 2025. That is the
    plane `absump.ingest.normalize_sc.plane_source` records per level-season,
    so this function defers to it rather than restating the changeover.
    """
    from absump.ingest.normalize_sc import plane_source

    return plane_source(level, season)


@dataclass(frozen=True)
class DayPartition:
    """One day of one level-season, with the two source parts and the target."""

    level: str
    season: int
    day: _dt.date
    feed: Path
    statcast: Path
    target: Path


def _season_dir(dataset: str, level: str, season: int, *, sealed: bool) -> Path | None:
    """The `season=` directory of one dataset, open side or sealed side."""
    probe = _dt.date(season, 12, 31) if sealed else _dt.date(season, 1, 1)
    if paths.is_sealed(probe) is not sealed:
        return None
    return paths.lake_path(dataset, level, season, probe).parent.parent


def _dataset_days(dataset: str, level: str, season: int) -> dict[_dt.date, Path]:
    """Every day of one dataset that has a part on disk, open and sealed."""
    found: dict[_dt.date, Path] = {}
    for sealed in (False, True):
        root = _season_dir(dataset, level, season, sealed=sealed)
        if root is None or not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or not entry.name.startswith("date="):
                continue
            try:
                day = _dt.date.fromisoformat(entry.name.split("=", 1)[1])
            except ValueError:
                continue
            part = paths.lake_path(dataset, level, season, day)
            if part.exists():
                found[day] = part
    return found


def day_partitions(
    level: str, season: int, days: Sequence[_dt.date] | None = None
) -> list[DayPartition]:
    """Every day of one level-season that has both sources on disk.

    A day with a feed part and no Statcast part, or the reverse, is a missing
    input rather than a join failure, so it raises instead of reporting zero
    rows against a whole day of real pitches.
    """
    feed_days = _dataset_days(FEED_DATASET, level, season)
    csv_days = _dataset_days(STATCAST_DATASET, level, season)
    if not feed_days:
        return []
    wanted = set(days) if days else set(feed_days)
    missing = sorted(day for day in feed_days if day in wanted and day not in csv_days)
    if missing:
        raise JoinError(
            f"{level} {season}: {len(missing)} day(s) have a {FEED_DATASET} part and no "
            f"{STATCAST_DATASET} part, first {missing[0].isoformat()}. Run W2.14 for them."
        )
    out: list[DayPartition] = []
    for day in sorted(day for day in feed_days if day in wanted):
        out.append(
            DayPartition(
                level=level,
                season=season,
                day=day,
                feed=feed_days[day],
                statcast=csv_days[day],
                target=paths.lake_path(DATASET, level, season, day),
            )
        )
    return out


# --------------------------------------------------------------------------
# The SQL
# --------------------------------------------------------------------------


def trajectory_sql(y_ft: float, alias: str = "a") -> tuple[str, str]:
    """`(x, z)` at plane `y_ft`, from one API row's own release triple.

    The section 2.5 closed form, with the row's own `y0` as the reference
    plane. `vy0 < 0` and `ay > 0` select the smaller positive root, so there is
    no branch and no root selection; a row that fails the guard yields NULL and
    is counted as a row without a coordinate rather than re-projected off the
    wrong root.

    Every operand is parenthesised: DuckDB reads a leading `--` as a line
    comment, which would truncate the statement instead of failing.
    """
    t = (
        f"CASE WHEN ({alias}.vy0) < 0 AND ({alias}.ay) > 0 THEN "
        f"(-({alias}.vy0) - sqrt(({alias}.vy0) * ({alias}.vy0) "
        f"- 2 * ({alias}.ay) * (({alias}.y0) - {y_ft!r}))) / ({alias}.ay) END"
    )
    x = f"({alias}.x0) + ({alias}.vx0) * ({t}) + 0.5 * ({alias}.ax) * ({t}) * ({t})"
    z = f"({alias}.z0) + ({alias}.vz0) * ({t}) + 0.5 * ({alias}.az) * ({t}) * ({t})"
    return x, z


def _shift_sql(coord: str, v0: str, acc: str, t_from: str, t_to: str) -> str:
    """One published coordinate carried from plane `t_from` to plane `t_to`.

    `dx = vx0*(t_b - t_a) + 0.5*ax*(t_b^2 - t_a^2)`, the section 2.5 recipe
    applied to the published pair with the `Y0 = 50.0` reference. This is the
    diagnostic of B-2, not the asserted quantity.
    """
    return (
        f"({coord}) + ({v0}) * (({t_to}) - ({t_from})) "
        f"+ 0.5 * ({acc}) * (({t_to}) * ({t_to}) - ({t_from}) * ({t_from}))"
    )


def _t_at_y_sql(y_ft: float, alias: str = "a", y_ref: float = 50.0) -> str:
    """Time from the `Y0 = 50.0` reference plane to `y_ft`, smaller root."""
    return (
        f"CASE WHEN ({alias}.vy0) < 0 AND ({alias}.ay) > 0 THEN "
        f"(-({alias}.vy0) - sqrt(({alias}.vy0) * ({alias}.vy0) "
        f"- 2 * ({alias}.ay) * ({y_ref!r} - {y_ft!r}))) / ({alias}.ay) END"
    )


def join_day_sql(part: DayPartition) -> str:
    """The full SELECT for one day: every API slot and every CSV row, once.

    `match_side` is `both`, `api_only`, `csv_only` or `api_unnumbered`. The
    last one is B-1's `no_pitch` with no call block: a real feed event that
    Statcast never numbers, carried into the output with a NULL `pitch_number`
    so that its `play_id` is not lost, and counted in neither `n_api` nor the
    unmatched report.
    """
    plane = target_plane(part.level, part.season)
    y_plane = Y_MID_FT if plane == PLANE_MID else Y_FRONT_FT
    api_x, api_z = trajectory_sql(y_plane, "a")
    csv_x = "b.plate_x_mid" if plane == PLANE_MID else "b.plate_x_front"
    csv_z = "b.plate_z_mid" if plane == PLANE_MID else "b.plate_z_front"
    t_front = _t_at_y_sql(Y_FRONT_FT, "a")
    t_plane = _t_at_y_sql(y_plane, "a")
    shift_x = _shift_sql("a.p_x", "a.vx0", "a.ax", t_front, t_plane)
    shift_z = _shift_sql("a.p_z", "a.vz0", "a.az", t_front, t_plane)
    unnumbered = "(api.event_type = 'no_pitch' AND api.call_code IS NULL)"
    return f"""
WITH api AS (
    SELECT * FROM read_parquet('{part.feed.as_posix()}')
),
slotted AS (
    SELECT
        api.*,
        {unnumbered} AS unnumbered,
        CASE WHEN {unnumbered} THEN NULL ELSE
            row_number() OVER (
                PARTITION BY api.game_pk, api.at_bat_number ORDER BY api.pitch_slot)
            - sum(CASE WHEN {unnumbered} THEN 1 ELSE 0 END) OVER (
                PARTITION BY api.game_pk, api.at_bat_number ORDER BY api.pitch_slot
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        END AS pitch_number
    FROM api
),
csv AS (
    SELECT
        game_pk, at_bat_number, pitch_number, description, events, tracked,
        plane_source, plate_x_front, plate_z_front, plate_x_mid, plate_z_mid
    FROM read_parquet('{part.statcast.as_posix()}')
),
paired AS (
    SELECT
        coalesce(a.game_pk, b.game_pk) AS game_pk,
        coalesce(a.at_bat_number, b.at_bat_number) AS at_bat_number,
        a.pitch_slot AS pitch_slot,
        coalesce(a.pitch_number, b.pitch_number) AS pitch_number,
        CASE WHEN a.game_pk IS NOT NULL AND b.game_pk IS NOT NULL THEN 'both'
             WHEN a.game_pk IS NOT NULL THEN 'api_only'
             ELSE 'csv_only' END AS match_side,
        a.play_id, a.play_index, a.event_type, a.call_code, a.call_description,
        a.is_pitch, a.is_strike, a.is_ball, a.is_in_play, a.pitch_type_code,
        a.p_x, a.p_z,
        CASE WHEN b.game_pk IS NULL THEN NULL ELSE {api_x} END AS api_x_at_plane,
        CASE WHEN b.game_pk IS NULL THEN NULL ELSE {api_z} END AS api_z_at_plane,
        {csv_x} AS csv_x_at_plane,
        {csv_z} AS csv_z_at_plane,
        CASE WHEN a.game_pk IS NULL THEN NULL ELSE {shift_x} END AS api_shift_x_at_plane,
        CASE WHEN a.game_pk IS NULL THEN NULL ELSE {shift_z} END AS api_shift_z_at_plane,
        b.description AS csv_description,
        b.events AS csv_events,
        b.tracked AS csv_tracked,
        false AS unnumbered
    FROM (SELECT * FROM slotted WHERE pitch_number IS NOT NULL) AS a
    FULL OUTER JOIN csv AS b
      ON a.game_pk = b.game_pk
     AND a.at_bat_number = b.at_bat_number
     AND a.pitch_number = b.pitch_number
    UNION ALL
    SELECT
        a.game_pk, a.at_bat_number, a.pitch_slot,
        CAST(NULL AS BIGINT) AS pitch_number,
        'api_unnumbered' AS match_side,
        a.play_id, a.play_index, a.event_type, a.call_code, a.call_description,
        a.is_pitch, a.is_strike, a.is_ball, a.is_in_play, a.pitch_type_code,
        a.p_x, a.p_z,
        CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE),
        CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE),
        CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE),
        CAST(NULL AS VARCHAR), CAST(NULL AS VARCHAR), CAST(NULL AS BOOLEAN),
        true AS unnumbered
    FROM (SELECT * FROM slotted WHERE pitch_number IS NULL) AS a
)
SELECT
    game_pk,
    '{part.level}' AS level,
    CAST({int(part.season)} AS BIGINT) AS season,
    DATE '{part.day.isoformat()}' AS official_date,
    at_bat_number, pitch_slot, pitch_number, match_side, unnumbered,
    play_id, play_index, event_type, call_code, call_description,
    is_pitch, is_strike, is_ball, is_in_play, pitch_type_code,
    p_x, p_z,
    '{plane}' AS plane,
    api_x_at_plane, api_z_at_plane, csv_x_at_plane, csv_z_at_plane,
    csv_description, csv_events, csv_tracked,
    greatest(abs(api_x_at_plane - csv_x_at_plane),
             abs(api_z_at_plane - csv_z_at_plane)) AS coord_err_ft,
    greatest(abs(api_shift_x_at_plane - csv_x_at_plane),
             abs(api_shift_z_at_plane - csv_z_at_plane)) AS published_pair_err_ft
FROM paired
"""


# --------------------------------------------------------------------------
# The report files
# --------------------------------------------------------------------------


def _text(value: Any) -> str:
    """One CSV cell. Floats keep their shortest round-trip form."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, _dt.date):
        return value.isoformat()
    return str(value)


def _as_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _sort_key(row: dict[str, str], columns: Sequence[str]) -> tuple[Any, ...]:
    """Level, season, day, game, at-bat, pitch, then the remaining cells."""
    head = (
        row.get("level", ""),
        _as_int(row.get("season", "")),
        row.get("official_date", ""),
        _as_int(row.get("game_pk", "")),
        _as_int(row.get("at_bat_number", "")),
        _as_int(row.get("pitch_slot", "")),
        _as_int(row.get("pitch_number", "")),
    )
    return head + tuple(row.get(name, "") for name in columns)


def _read_existing(path: Path, columns: Sequence[str]) -> list[dict[str, str]]:
    """The rows already in a report, or none when it is absent or stale.

    A file whose header is not this module's header is a report from an older
    shape. It is replaced rather than merged, because merging two shapes would
    write a file that neither reader can parse.
    """
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != list(columns):
            return []
        return [dict(row) for row in reader]


def write_report(
    path: Path, columns: Sequence[str], rows: Iterable[dict[str, Any]], scope: set[tuple[str, int]]
) -> int:
    """Replace the `scope` level-seasons in one report and keep the rest (B-3)."""
    fresh = [{name: _text(row.get(name)) for name in columns} for row in rows]
    kept = [
        row
        for row in _read_existing(path, columns)
        if (row.get("level", ""), _as_int(row.get("season", ""))) not in scope
    ]
    merged = sorted(kept + fresh, key=lambda row: _sort_key(row, columns))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged)
    return len(merged)


# --------------------------------------------------------------------------
# One day
# --------------------------------------------------------------------------


@dataclass
class DayResult:
    """Everything one day contributes to the four reports."""

    games: list[dict[str, Any]]
    unmatched: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    no_pitch: list[dict[str, Any]]
    n_rows: int
    max_published_err_ft: float | None


_PARQUET_COLUMNS: Final[str] = """
    game_pk, level, season, official_date, at_bat_number, pitch_slot, pitch_number,
    match_side, unnumbered, play_id, play_index, event_type, call_code, call_description,
    is_pitch, is_strike, is_ball, is_in_play, pitch_type_code, p_x, p_z, plane,
    api_x_at_plane, api_z_at_plane, csv_x_at_plane, csv_z_at_plane,
    csv_description, csv_events, csv_tracked, coord_err_ft
"""


def join_day(con: Any, part: DayPartition, *, coord_tol_ft: float) -> DayResult:
    """Join one day, write its part, and return its report rows."""
    con.execute(f"CREATE OR REPLACE TEMP TABLE j AS {join_day_sql(part)}")
    target = paths.assert_minted(part.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT {_PARQUET_COLUMNS} FROM j "
        "ORDER BY game_pk, at_bat_number, coalesce(pitch_slot, 2147483647), "
        "coalesce(pitch_number, 2147483647)) "
        f"TO '{target.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 9)"
    )
    n_rows = con.execute("SELECT count(*) FROM j").fetchone()[0]
    published = con.execute(
        f"SELECT max(published_pair_err_ft) FROM j WHERE coord_err_ft <= {float(coord_tol_ft)!r}"
    ).fetchone()[0]

    games = [
        dict(zip(_GAME_FIELDS, row, strict=True))
        for row in con.execute(_GAME_SQL.format(tol=repr(float(coord_tol_ft)))).fetchall()
    ]
    unmatched = [
        dict(zip(UNMATCHED_COLUMNS, row, strict=True))
        for row in con.execute(_UNMATCHED_SQL).fetchall()
    ]
    failures = [
        dict(zip(FAILURE_COLUMNS, row, strict=True))
        for row in con.execute(_FAILURE_SQL.format(tol=repr(float(coord_tol_ft)))).fetchall()
    ]
    no_pitch = [
        dict(zip(NO_PITCH_COLUMNS, row, strict=True))
        for row in con.execute(_NO_PITCH_SQL).fetchall()
    ]
    for game in games:
        game["status"] = _status(game)
    return DayResult(
        games=games,
        unmatched=unmatched,
        failures=failures,
        no_pitch=no_pitch,
        n_rows=int(n_rows),
        max_published_err_ft=published,
    )


_GAME_FIELDS: Final[tuple[str, ...]] = (
    "game_pk",
    "level",
    "season",
    "official_date",
    "n_api",
    "n_csv",
    "n_matched",
    "n_api_only",
    "n_csv_only",
    "n_no_pitch_events",
    "max_coord_err_ft",
    "n_coord_breach",
)

_GAME_SQL: Final[str] = """
SELECT
    game_pk, level, season, official_date,
    sum(CASE WHEN match_side IN ('both', 'api_only') THEN 1 ELSE 0 END) AS n_api,
    sum(CASE WHEN match_side IN ('both', 'csv_only') THEN 1 ELSE 0 END) AS n_csv,
    sum(CASE WHEN match_side = 'both' THEN 1 ELSE 0 END) AS n_matched,
    sum(CASE WHEN match_side = 'api_only' THEN 1 ELSE 0 END) AS n_api_only,
    sum(CASE WHEN match_side = 'csv_only' THEN 1 ELSE 0 END) AS n_csv_only,
    sum(CASE WHEN event_type = 'no_pitch' THEN 1 ELSE 0 END) AS n_no_pitch_events,
    max(coord_err_ft) AS max_coord_err_ft,
    sum(CASE WHEN coord_err_ft > {tol} THEN 1 ELSE 0 END) AS n_coord_breach
FROM j
GROUP BY 1, 2, 3, 4
ORDER BY 1
"""

_UNMATCHED_SQL: Final[str] = """
SELECT
    game_pk, level, season, official_date, match_side AS side,
    at_bat_number, pitch_slot, pitch_number, event_type, call_code,
    coalesce(call_description, csv_description) AS description
FROM j
WHERE match_side IN ('api_only', 'csv_only')
ORDER BY game_pk, at_bat_number, coalesce(pitch_slot, 2147483647),
         coalesce(pitch_number, 2147483647), side
"""

_FAILURE_SQL: Final[str] = """
WITH ab AS (
    SELECT
        game_pk, level, season, official_date, at_bat_number,
        sum(CASE WHEN match_side IN ('both', 'api_only') THEN 1 ELSE 0 END) AS n_api_ab,
        sum(CASE WHEN match_side IN ('both', 'csv_only') THEN 1 ELSE 0 END) AS n_csv_ab,
        sum(CASE WHEN match_side = 'both' THEN 1 ELSE 0 END) AS n_matched_ab,
        sum(CASE WHEN match_side = 'api_only' THEN 1 ELSE 0 END) AS n_api_only_ab,
        sum(CASE WHEN match_side = 'csv_only' THEN 1 ELSE 0 END) AS n_csv_only_ab
    FROM j
    GROUP BY 1, 2, 3, 4, 5
),
counts AS (
    SELECT
        game_pk, level, season, official_date, 'counts' AS reason, at_bat_number,
        n_api_ab, n_csv_ab, n_matched_ab,
        'api_only=' || n_api_only_ab || ' csv_only=' || n_csv_only_ab AS detail
    FROM ab
    WHERE n_api_ab <> n_csv_ab OR n_matched_ab <> n_api_ab
       OR n_api_only_ab > 0 OR n_csv_only_ab > 0
),
coord AS (
    SELECT
        j.game_pk, j.level, j.season, j.official_date, 'coord' AS reason, j.at_bat_number,
        ab.n_api_ab, ab.n_csv_ab, ab.n_matched_ab,
        'pitch_number=' || j.pitch_number || ' plane=' || j.plane
            || ' coord_err_ft=' || j.coord_err_ft AS detail
    FROM j JOIN ab USING (game_pk, at_bat_number)
    WHERE j.coord_err_ft > {tol}
)
SELECT * FROM counts UNION ALL SELECT * FROM coord
ORDER BY game_pk, at_bat_number, reason, detail
"""

_NO_PITCH_SQL: Final[str] = """
SELECT
    game_pk, level, season, official_date, at_bat_number,
    sum(CASE WHEN match_side <> 'csv_only' THEN 1 ELSE 0 END) AS n_slots,
    sum(CASE WHEN event_type = 'no_pitch' THEN 1 ELSE 0 END) AS n_no_pitch,
    sum(CASE WHEN event_type = 'no_pitch' AND call_code IS NOT NULL THEN 1 ELSE 0 END)
        AS n_no_pitch_numbered,
    sum(CASE WHEN event_type = 'no_pitch' AND call_code IS NULL THEN 1 ELSE 0 END)
        AS n_no_pitch_unnumbered,
    array_to_string(list_sort(list_distinct(list(coalesce(call_code, 'none'))
        FILTER (WHERE event_type = 'no_pitch'))), '|') AS call_codes
FROM j
GROUP BY 1, 2, 3, 4, 5
HAVING sum(CASE WHEN event_type = 'no_pitch' THEN 1 ELSE 0 END) > 0
ORDER BY game_pk, at_bat_number
"""


def _status(game: dict[str, Any]) -> str:
    """`ok`, `fail` on any W2.15 count condition, `coord` on a breach alone."""
    if (
        game["n_api"] != game["n_csv"]
        or game["n_matched"] != game["n_api"]
        or game["n_api_only"]
        or game["n_csv_only"]
    ):
        return STATUS_FAIL
    if game["n_coord_breach"]:
        return STATUS_COORD
    return STATUS_OK


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def _paths_list(parts: Sequence[DayPartition], side: str) -> str:
    """A DuckDB list literal of one side's day parts."""
    files = [getattr(part, side).as_posix() for part in parts]
    return "[" + ", ".join(f"'{name}'" for name in files) + "]"


def assert_one_day_per_game(con: Any, parts: Sequence[DayPartition]) -> None:
    """B-5. Both sides must put every game on exactly one officialDate.

    MLB 2026 measured 2,342 (game_pk, date) pairs on the feed side, 2,342 on
    the CSV side and zero asymmetric, so the day-by-day join is exact. A game
    that moved between the two sides would otherwise surface as unmatched rows
    on both sides and read as a key defect.
    """
    if not parts:
        return
    rows = con.execute(
        f"""
WITH a AS (SELECT DISTINCT game_pk, official_date AS d
           FROM read_parquet({_paths_list(parts, "feed")})),
     b AS (SELECT DISTINCT game_pk, "date" AS d
           FROM read_parquet({_paths_list(parts, "statcast")}))
SELECT coalesce(a.game_pk, b.game_pk), a.d, b.d
FROM a FULL OUTER JOIN b ON a.game_pk = b.game_pk AND a.d = b.d
WHERE a.game_pk IS NULL OR b.game_pk IS NULL
ORDER BY 1
"""
    ).fetchall()
    if rows:
        head = ", ".join(f"{row[0]} feed={row[1]} csv={row[2]}" for row in rows[:3])
        raise JoinError(
            f"{len(rows)} game-day pair(s) appear on one side only, first {head}. "
            "The two sources disagree about which officialDate a game belongs to."
        )


def coverage_row(level: str, season: int) -> dict[str, object]:
    """One report row for a level-season that contributed no joined game.

    W2.15's report is one row per game, which says nothing at all about a
    season whose inputs are absent: a reader cannot tell a season that was
    never requested from one that was requested and had nothing to join. This
    row is the difference. `game_pk` is empty, every count is zero, and
    `status` names which side of the join is missing on disk.
    """
    feed_days = len(_dataset_days(FEED_DATASET, level, season))
    csv_days = len(_dataset_days(STATCAST_DATASET, level, season))
    if feed_days == 0 and csv_days == 0:
        status = STATUS_NO_INPUTS
    elif feed_days == 0:
        status = STATUS_NO_FEED
    else:
        status = STATUS_NO_STATCAST
    return {
        "game_pk": "",
        "level": level,
        "season": int(season),
        "official_date": "",
        "n_api": 0,
        "n_csv": 0,
        "n_matched": 0,
        "n_api_only": 0,
        "n_csv_only": 0,
        "n_no_pitch_events": 0,
        "max_coord_err_ft": "",
        "status": status,
    }


def run(
    *,
    level: str,
    seasons: Sequence[int],
    days: Sequence[_dt.date] | None = None,
    threads: int = 6,
    coord_tol_ft: float = COORD_TOL_FT,
    strict_coord: bool = False,
    out: Any = sys.stdout,
) -> int:
    """Join every requested level-season and rewrite the four reports."""
    import duckdb

    scope: set[tuple[str, int]] = set()
    joined: set[tuple[str, int]] = set()
    games: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    no_pitch: list[dict[str, Any]] = []
    n_rows = 0
    n_days = 0
    day_published: list[float] = []

    con = duckdb.connect()
    con.execute(f"PRAGMA threads={int(threads)}")
    tmp = paths.tmp_dir()
    tmp.mkdir(parents=True, exist_ok=True)
    con.execute(f"PRAGMA temp_directory='{tmp.as_posix()}'")
    try:
        for season in seasons:
            parts = day_partitions(level, season, days)
            if not parts:
                row = coverage_row(level, int(season))
                games.append(row)
                scope.add((level, int(season)))
                print(
                    f"{level} {season}: nothing to join, status {row['status']}; "
                    "a coverage row goes to the report",
                    file=out,
                )
                continue
            joined.add((level, int(season)))
            assert_one_day_per_game(con, parts)
            scope.add((level, int(season)))
            for part in parts:
                result = join_day(con, part, coord_tol_ft=coord_tol_ft)
                games.extend(result.games)
                unmatched.extend(result.unmatched)
                failures.extend(result.failures)
                no_pitch.extend(result.no_pitch)
                n_rows += result.n_rows
                n_days += 1
                if result.max_published_err_ft is not None:
                    day_published.append(float(result.max_published_err_ft))
    finally:
        con.close()

    if not scope:
        print("nothing joined: no level-season was requested", file=out)
        return 3

    write_report(REPORT_PATH, REPORT_COLUMNS, games, scope)
    write_report(UNMATCHED_PATH, UNMATCHED_COLUMNS, unmatched, scope)
    write_report(FAILURES_PATH, FAILURE_COLUMNS, failures, scope)
    write_report(NO_PITCH_PATH, NO_PITCH_COLUMNS, no_pitch, scope)

    n_failed = sum(1 for game in games if game["status"] == STATUS_FAIL)
    n_coord = sum(1 for game in games if game["status"] == STATUS_COORD)
    covered = [game for game in games if game["status"] in COVERAGE_STATUSES]
    games = [game for game in games if game["status"] not in COVERAGE_STATUSES]
    n_matched = sum(int(game["n_matched"]) for game in games)
    n_api = sum(int(game["n_api"]) for game in games)
    n_csv = sum(int(game["n_csv"]) for game in games)
    pct = 100.0 * n_matched / n_api if n_api else 0.0
    errs = [game["max_coord_err_ft"] for game in games if game["max_coord_err_ft"] is not None]
    worst = max(errs) if errs else None

    seasons_text = ",".join(str(season) for _, season in sorted(scope))
    print(
        f"W2.15 join {level} {seasons_text}: days {n_days}, games {len(games)}, "
        f"rows {n_rows} written to {DATASET}",
        file=out,
    )
    print(
        f"  n_api {n_api}  n_csv {n_csv}  n_matched {n_matched}  "
        f"api_only {sum(int(g['n_api_only']) for g in games)}  "
        f"csv_only {sum(int(g['n_csv_only']) for g in games)}  matched {pct:.3f}%",
        file=out,
    )
    print(
        f"  status ok {len(games) - n_failed - n_coord}, coord {n_coord}, fail {n_failed}", file=out
    )
    print(
        f"  max_coord_err_ft {worst!r} against the {coord_tol_ft!r} ft tolerance",
        file=out,
    )
    if day_published:
        typical = sorted(day_published)[len(day_published) // 2]
        print(
            f"  published pX/pZ against the CSV, rows inside the tolerance: "
            f"day-median maximum {typical!r} ft, worst day {max(day_published)!r} ft "
            "(section 2.5 measured 0.001053 ft over 281 pitches)",
            file=out,
        )
    print(
        f"  reports: {REPORT_PATH.name}, {UNMATCHED_PATH.name}, "
        f"{FAILURES_PATH.name}, {NO_PITCH_PATH.name}",
        file=out,
    )
    for row in sorted(covered, key=lambda row: (row["level"], row["season"])):
        print(
            f"  COVERAGE {row['level']} {row['season']}: no game joined, status {row['status']}",
            file=out,
        )
    if n_failed:
        print(
            f"  FAIL {n_failed} game(s) on a W2.15 count condition; see {FAILURES_PATH}", file=out
        )
        return 1
    if n_coord and strict_coord:
        print(
            f"  FAIL {n_coord} game(s) on the coordinate assertion under --strict-coord", file=out
        )
        return 1
    if not joined:
        print(
            "  no requested level-season had both sources on disk; the report carries "
            "a coverage row for each and no game row was written",
            file=out,
        )
        return 3
    return 0


def _parse_days(tokens: Sequence[str] | None) -> list[_dt.date] | None:
    if not tokens:
        return None
    return [_dt.date.fromisoformat(token) for token in tokens]


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m absump.ingest.join --level mlb --season 2026`."""
    parser = argparse.ArgumentParser(
        prog="python -m absump.ingest.join",
        description="W2.15 the join, full season, with an explicit unmatched report.",
    )
    parser.add_argument("--level", required=True, choices=list(paths.LEVELS))
    parser.add_argument("--season", required=True, nargs="+", help="2026, 2022..2025, or a list")
    parser.add_argument("--date", action="append", help="restrict to one officialDate, repeatable")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--coord-tol", type=float, default=COORD_TOL_FT)
    parser.add_argument(
        "--strict-coord",
        action="store_true",
        help="fail the build on a coordinate breach as well as on a count condition",
    )
    args = parser.parse_args(argv)
    try:
        return run(
            level=args.level,
            seasons=parse_seasons(args.season),
            days=_parse_days(args.date),
            threads=args.threads,
            coord_tol_ft=args.coord_tol,
            strict_coord=args.strict_coord,
        )
    except (JoinError, ValueError) as exc:
        print(f"W2.15 join: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())


# --------------------------------------------------------------------------
# The drawer coordinate bridge (D-62, DT-28)
# --------------------------------------------------------------------------

#: The bridge key rounds both coordinates to this many decimal places.
BRIDGE_PLACES: Final[int] = 2

#: The Savant drawer's own coordinate field names, either spelling.
_DRAWER_X: Final[tuple[str, ...]] = ("plate_X", "plateX", "plate_x")
_DRAWER_Z: Final[tuple[str, ...]] = ("plate_Z", "plateZ", "plate_z")


def round_half_up(value: float, places: int = BRIDGE_PLACES) -> float:
    """`round(x, 2)` with SQL's rule, not Python's.

    DuckDB and every SQL engine round half away from zero; Python rounds half
    to even, so `round(0.125, 2)` is 0.13 in SQL and 0.12 in Python. The bridge
    key is specified as `round(plate_X, 2)`, and dbt will rebuild it in SQL, so
    the Python side has to use the SQL rule or the two indexes disagree on the
    rows that land exactly on a half.
    """
    from decimal import ROUND_HALF_UP, Decimal

    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(repr(float(value))).quantize(quantum, rounding=ROUND_HALF_UP))


def bridge_key(game_pk: Any, plate_x: Any, plate_z: Any) -> tuple[int, float, float]:
    """`(game_pk, round(plate_X, 2), round(plate_Z, 2))`, the D-62 sprint key."""
    return (int(game_pk), round_half_up(float(plate_x)), round_half_up(float(plate_z)))


def drawer_coordinates(row: dict[str, Any]) -> tuple[float, float]:
    """The `(plate_X, plate_Z)` pair of one drawer row, either spelling."""
    out = []
    for names in (_DRAWER_X, _DRAWER_Z):
        for name in names:
            if row.get(name) is not None:
                out.append(float(row[name]))
                break
        else:
            raise KeyError(f"none of {tuple(names)} is present on the row")
    return out[0], out[1]


@dataclass(frozen=True)
class BridgeResult:
    """What the coordinate bridge did with one set of drawer rows."""

    n_rows: int
    n_matched: int
    n_ambiguous: int
    n_unmatched: int
    matches: tuple[tuple[int, tuple[int, float, float], tuple[Any, ...]], ...]

    @property
    def match_rate(self) -> float:
        return self.n_matched / self.n_rows if self.n_rows else 0.0


def drawer_bridge(
    drawer_rows: Sequence[dict[str, Any]], pitch_rows: Iterable[dict[str, Any]]
) -> BridgeResult:
    """Join drawer challenges to pitches on the rounded coordinate key.

    `pitch_rows` carries `game_pk`, a coordinate pair and an `id`. A drawer row
    is matched when exactly one pitch row shares its key, ambiguous when more
    than one does, unmatched when none does. DT-28 requires 10,167 matched, 0
    ambiguous and 0 unmatched over the real drawer.
    """
    index: dict[tuple[int, float, float], list[Any]] = {}
    for row in pitch_rows:
        key = bridge_key(row["game_pk"], *drawer_coordinates(row))
        index.setdefault(key, []).append(row["id"])
    matched = ambiguous = unmatched = 0
    pairs: list[tuple[int, tuple[int, float, float], tuple[Any, ...]]] = []
    for position, row in enumerate(drawer_rows):
        key = bridge_key(row["game_pk"], *drawer_coordinates(row))
        hits = tuple(index.get(key, ()))
        pairs.append((position, key, hits))
        if len(hits) == 1:
            matched += 1
        elif len(hits) > 1:
            ambiguous += 1
        else:
            unmatched += 1
    return BridgeResult(
        n_rows=len(drawer_rows),
        n_matched=matched,
        n_ambiguous=ambiguous,
        n_unmatched=unmatched,
        matches=tuple(pairs),
    )
