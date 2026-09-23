"""W2.9. One Statcast game-day: the endpoint, the traps and the assertions.

SOP W2.9. Baseball Savant's Statcast Search CSV export, one request per
game-day, `type=details`, `player_type=batter`. This module owns that endpoint.
W6.0 owns the runner that drives it across 920 days; nothing here loops over a
season on its own.

What it enforces, on every day, whether the bytes came off the wire or out of
the staging cache:

  UT-14  the body is decoded with utf-8-sig. Savant BOMs every CSV, and plain
         utf-8 turns the first column name into U+FEFF + "pitch_type".
  UT-15  a day at or above 25,000 rows is refused. The cap is silent: a window
         wide enough to hit it returns exactly 25,000 rows, keeps the newest,
         drops the oldest days, and says nothing.
  DT-01  rows per day < 25,000. UT-15 is the guard; DT-01 is the sweep.
  DT-02  the header sha256 equals the committed fixture, every day, including
         2022 and 2023, which were unverified before this project.

The untracked rows. 20 of 4,427 rows on 2026-09-15 have blank `pitch_type`,
`plate_x`, `sz_bot` and `sz_top` -- blank together, never one without the
others. They are 19 `automatic_ball` (intentional walk, pitch timer) and one
untracked foul. They stay in the pitch table with `tracked = false` and are
excluded from the called-pitch mart. Left in, they inflated a "batters with
more than one distinct sz_top" count from 0 to 7.

The `umpire` column is present and empty, 0 of 4,427 non-empty, and csv-docs
calls it a deprecated field from the old tracking system. Umpires come from
W2.5. There is no ABS or challenge column of any kind in this CSV.

Every number above lives in contracts/statcast_csv.yml with the day it was
measured on, and this module reads it from there.

Command line:

    python -m absump.ingest.statcast_day --verify
    python -m absump.ingest.statcast_day --import-staging
    python -m absump.ingest.statcast_day --plan 2026-09-15 2026-09-16
    python -m absump.ingest.statcast_day --pull 2026-09-15

`--verify`, `--import-staging` and `--plan` issue no request. `--pull` is the
one live path; it goes through absump.http.get, which carries the A3 throttle,
the daily cap and the manifest row.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import io
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Final

import yaml
import zstandard

from absump import http as client
from absump import paths

__all__ = [
    "CALLED_DESCRIPTIONS",
    "COLUMN_COUNT",
    "EXCEPTION_COLUMNS",
    "ROW_CAP",
    "TRACKING_COLUMNS",
    "DayContractError",
    "DayReport",
    "HeaderDrift",
    "MissingBom",
    "RowCapReached",
    "columns_of",
    "contract",
    "day_exceptions",
    "day_url",
    "expected_header_sha256",
    "header_sha256",
    "import_staging_day",
    "import_staging_tree",
    "is_tracked",
    "parse_day",
    "pull_day",
    "raw_days",
    "read_day",
    "store_day",
    "validate_day",
    "verify_lake",
    "write_day_exceptions",
]

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
CONTRACT_PATH: Final[Path] = REPO_ROOT / "contracts" / "statcast_csv.yml"
HEADER_FIXTURE_PATH: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "statcast_header.sha256"

#: The silent truncation point. SOP W2.9: a 30-day window returns exactly
#: 25,000 rows with no truncation header and the oldest days missing. A day at
#: or above this is not a big day, it is a truncated answer to a wrong question.
ROW_CAP: Final[int] = 25_000

#: SOP W2.9 header stability: 119 columns, byte-identical 2015-2026 and
#: identical to the minors CSV.
COLUMN_COUNT: Final[int] = 119

#: The called-pitch population. Every pitch the plate umpire, or the ABS
#: system, actually had to call.
CALLED_DESCRIPTIONS: Final[frozenset[str]] = frozenset({"called_strike", "ball", "blocked_ball"})

#: Blank together on an untracked pitch, never one without the others.
TRACKING_COLUMNS: Final[tuple[str, ...]] = ("pitch_type", "plate_x", "sz_bot", "sz_top")

#: SOP section 2.3: raw bytes are immutable and compressed with zstandard
#: level 10. Not a number from an endpoint; a storage setting, stated there.
ZSTD_LEVEL: Final[int] = 10

#: The level this module pulls. The minors CSV is the same 119-column header
#: behind `minors=true&hfLevel=AAA|` and is a different step's day list.
LEVEL: Final[str] = "mlb"

_BOM: Final[bytes] = b"\xef\xbb\xbf"

# The SOP's URL, parameter for parameter and in the SOP's order. hfSea is
# "{season}|" percent-encoded. game_date_gt and game_date_lt are the same day,
# so the window is one day inclusive. There is deliberately NO hfGT: the
# default URL already includes the postseason, verified on 2025-10-25, which
# returned 224 rows for game_pk 813026, a gameType W game. The order and the
# spelling are fixed because absump.http keys its cache on the URL text, so a
# reordered query string is a second paid request for the same bytes.
_DAY_URL: Final[str] = (
    "https://baseballsavant.mlb.com/statcast_search/csv"
    "?all=true&type=details"
    "&player_type=batter&min_pitches=0&min_results=0&group_by=name"
    "&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
    "&hfSea={season}%7C&game_date_gt={day}&game_date_lt={day}"
)


class DayContractError(ValueError):
    """One day's CSV broke the contract in contracts/statcast_csv.yml."""


class MissingBom(DayContractError):
    """UT-14. The body did not start with a UTF-8 BOM."""


class HeaderDrift(DayContractError):
    """DT-02. The header sha256 is not the committed fixture's."""


class RowCapReached(DayContractError):
    """UT-15 and DT-01. The day is at or above the silent 25,000-row cap."""


# ---------------------------------------------------------------------------
# The contract file
# ---------------------------------------------------------------------------

_CONTRACT: dict[str, Any] | None = None


def contract() -> dict[str, Any]:
    """contracts/statcast_csv.yml, parsed once and returned as a copy."""
    global _CONTRACT
    if _CONTRACT is None:
        with CONTRACT_PATH.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if not isinstance(loaded, dict):
            raise DayContractError(f"{CONTRACT_PATH} is not a mapping")
        _CONTRACT = loaded
    return dict(_CONTRACT)


def contract_columns() -> tuple[str, ...]:
    """The 119 column names the contract commits to, in order."""
    names = contract()["header"]["names"]
    return tuple(str(name) for name in names)


def expected_header_sha256(*, with_bom: bool = True) -> str:
    """The committed header digest, from tests/fixtures/statcast_header.sha256.

    The puller reads the test fixture on purpose. DT-02 has to fire when a day
    is pulled, not only when the test pack runs: a header that moved mid-pull
    means every later day is a different table, and the cheapest place to stop
    is the request that found it. One fixture, one digest, both callers.
    """
    want = "statcast_csv_header" if with_bom else "statcast_csv_header_nobom"
    for line in HEADER_FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        parts = text.split()
        if len(parts) == 2 and parts[1] == want:
            return parts[0]
    raise DayContractError(f"{HEADER_FIXTURE_PATH} has no digest named {want!r}")


# ---------------------------------------------------------------------------
# The URL
# ---------------------------------------------------------------------------


def day_url(game_date: Any) -> str:
    """The SOP W2.9 URL for one game-day.

    Raises `absump.paths.SealViolation` for a day inside the sealed window.
    The 2026 cutoff for every pull in this phase is 2026-09-21 inclusive, and a
    request that would cross it is a phase failure, not a warning.
    """
    day = paths.as_official_date(game_date)
    if paths.is_sealed(day):
        raise paths.SealViolation(
            f"{day.isoformat()} is past the seal at "
            f"{paths.LAST_OPEN_DATE.isoformat()}; this module never builds that URL"
        )
    return _DAY_URL.format(season=day.year, day=day.isoformat())


# ---------------------------------------------------------------------------
# Reading one day
# ---------------------------------------------------------------------------


def header_line(body: bytes) -> bytes:
    """The first line as served: BOM included, line terminator excluded."""
    if not body.startswith(_BOM):
        raise MissingBom(
            "the body does not start with a UTF-8 BOM. Savant BOMs every CSV, so "
            "either this is not a Savant CSV or something decoded and re-encoded "
            "it. Read it with utf-8-sig and never with plain utf-8 (UT-14)"
        )
    cut = body.find(b"\n")
    line = body if cut < 0 else body[:cut]
    return line[:-1] if line.endswith(b"\r") else line


def header_sha256(body: bytes, *, with_bom: bool = True) -> str:
    """DT-02's digest. See tests/fixtures/statcast_header.sha256 for the rule."""
    line = header_line(body)
    if not with_bom:
        line = line.decode("utf-8-sig").encode("utf-8")
    return hashlib.sha256(line).hexdigest()


def decode(body: bytes) -> str:
    """UT-14. The one decoding this project ever applies to a Savant CSV."""
    if not body.startswith(_BOM):
        raise MissingBom("the body does not start with a UTF-8 BOM (UT-14)")
    return body.decode(client.SAVANT_CSV_ENCODING)


def columns_of(body: bytes) -> tuple[str, ...]:
    """The column names, BOM stripped, in order."""
    line = header_line(body).decode(client.SAVANT_CSV_ENCODING)
    return tuple(next(csv.reader([line])))


def iter_rows(body: bytes) -> Iterator[dict[str, str]]:
    """Stream the day's rows as dicts. One pass, no frame, no coercion."""
    handle = io.StringIO(decode(body), newline="")
    reader = csv.DictReader(handle)
    yield from reader


def parse_day(body: bytes) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """The columns and every row of one day."""
    return columns_of(body), list(iter_rows(body))


def is_tracked(row: dict[str, str]) -> bool:
    """False for a pitch the tracking system did not measure.

    `pitch_type`, `plate_x`, `sz_bot` and `sz_top` are blank together on such a
    row. Keep it, flag it, and keep it out of the called-pitch mart; never
    coerce it to a number.
    """
    return all(row.get(column, "").strip() != "" for column in TRACKING_COLUMNS)


def called_pitches(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """The tracked called pitches: the population the zone model is fit on."""
    return [
        row for row in rows if row.get("description", "") in CALLED_DESCRIPTIONS and is_tracked(row)
    ]


# ---------------------------------------------------------------------------
# The per-day report and its assertions
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class DayReport:
    """What one day's CSV says about itself once it has passed the contract."""

    game_date: date
    body_bytes: int
    n_rows: int
    n_columns: int
    header_sha256: str
    game_pks: tuple[int, ...]
    n_untracked: int
    n_called: int
    n_umpire: int
    description_counts: dict[str, int]
    source: str = ""

    @property
    def season(self) -> int:
        return self.game_date.year

    def as_row(self) -> dict[str, Any]:
        """One flat row, for a table or a log line."""
        return {
            "game_date": self.game_date.isoformat(),
            "season": self.season,
            "body_bytes": self.body_bytes,
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
            "n_games": len(self.game_pks),
            "n_untracked": self.n_untracked,
            "n_called": self.n_called,
            "n_umpire": self.n_umpire,
            "header_sha256": self.header_sha256,
            "source": self.source,
        }


def validate_day(body: bytes, game_date: Any, *, source: str = "") -> DayReport:
    """Run UT-14, UT-15, DT-01 and DT-02 on one day and report what it holds.

    Raises `MissingBom`, `HeaderDrift` or `RowCapReached` on the first failure.
    The order matters: the BOM is checked before anything is decoded, and the
    header before any row is read, so a drifted header is reported as a header
    problem and not as 119 missing fields.
    """
    day = paths.as_official_date(game_date)
    digest = header_sha256(body)  # UT-14 first: header_line refuses a bodiless BOM
    expected = expected_header_sha256()
    if digest != expected:
        raise HeaderDrift(
            f"{day.isoformat()}: header sha256 {digest} is not the committed "
            f"{expected}. DT-02 says the header is byte-identical 2015-2026; a "
            f"new digest is a new table. Fixture: {HEADER_FIXTURE_PATH}"
        )

    columns = columns_of(body)
    if len(columns) != COLUMN_COUNT:
        raise HeaderDrift(f"{day.isoformat()}: {len(columns)} columns, not {COLUMN_COUNT}")
    committed = contract_columns()
    if columns != committed:
        moved = [a for a, b in zip(columns, committed, strict=True) if a != b]
        raise HeaderDrift(
            f"{day.isoformat()}: column names differ from the contract at {moved[:5]}"
        )

    descriptions: Counter[str] = Counter()
    game_pks: set[int] = set()
    n_rows = 0
    n_untracked = 0
    n_called = 0
    n_umpire = 0
    for row in iter_rows(body):
        n_rows += 1
        if n_rows >= ROW_CAP:
            # UT-15. Stop at the cap rather than after it: the response is
            # truncated from the OLD end, so the rows already read are the new
            # ones and the missing days are invisible. Nothing here is usable.
            raise RowCapReached(
                f"{day.isoformat()}: at least {n_rows} rows, and Savant's cap is "
                f"{ROW_CAP}. The cap is silent and keeps the newest rows, so this "
                "response is missing its oldest rows with no header to say so. "
                "Narrow the window to one day; the maximum ever seen on a full "
                "slate is 4,501"
            )
        descriptions[row.get("description", "")] += 1
        if row.get("umpire", "").strip():
            # The column is a deprecated field from the old tracking system and
            # has been empty on every day this project has pulled. If it ever
            # fills, that is news, not a data source: umpires come from W2.5.
            n_umpire += 1
        if not is_tracked(row):
            n_untracked += 1
        elif row.get("description", "") in CALLED_DESCRIPTIONS:
            n_called += 1
        game_pk = row.get("game_pk", "").strip()
        if game_pk:
            game_pks.add(int(game_pk))

    return DayReport(
        game_date=day,
        body_bytes=len(body),
        n_rows=n_rows,
        n_columns=len(columns),
        header_sha256=digest,
        game_pks=tuple(sorted(game_pks)),
        n_untracked=n_untracked,
        n_called=n_called,
        n_umpire=n_umpire,
        description_counts=dict(descriptions),
        source=source,
    )


# ---------------------------------------------------------------------------
# The raw lake
# ---------------------------------------------------------------------------


def raw_path(game_date: Any, *, level: str = LEVEL) -> Path:
    """Where this day lives once it is ours. Minted by absump.paths, never glued."""
    day = paths.as_official_date(game_date)
    return paths.raw_statcast(level, day.year, day)


def store_day(body: bytes, game_date: Any, *, level: str = LEVEL) -> tuple[Path, bool]:
    """Write one validated day to the raw lake at zstd level 10.

    Returns the path and whether this call wrote it. Raw bytes are immutable:
    an existing file is never rewritten, so running this twice changes no
    bytes. The write is a temporary file and an os.replace, so an interrupted
    run leaves either the whole day or no day.
    """
    day = paths.as_official_date(game_date)
    if paths.is_sealed(day):
        raise paths.SealViolation(
            f"{day.isoformat()} is past the seal at {paths.LAST_OPEN_DATE.isoformat()}"
        )
    dest = paths.assert_minted(raw_path(day, level=level))
    if dest.exists():
        return dest, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    compressor = zstandard.ZstdCompressor(level=ZSTD_LEVEL)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tmp.write_bytes(compressor.compress(body))
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest, True


def read_day(path: Path) -> bytes:
    """Decompress one stored day. Streamed, so a frame with no content size in
    its header -- what arrow's CompressedOutputStream writes on the R side --
    is still readable here."""
    decompressor = zstandard.ZstdDecompressor()
    with Path(path).open("rb") as handle, decompressor.stream_reader(handle) as reader:
        return reader.read()


def raw_days(*, level: str = LEVEL) -> list[tuple[date, Path]]:
    """Every stored day at this level, oldest first."""
    root = paths.data_root() / "raw" / "statcast" / f"level={level}"
    if not root.is_dir():
        return []
    found: list[tuple[date, Path]] = []
    for path in root.glob("season=*/date=*/pitches.csv.zst"):
        stamp = path.parent.name.split("=", 1)[-1]
        try:
            found.append((date.fromisoformat(stamp), path))
        except ValueError:
            continue
    return sorted(found)


# ---------------------------------------------------------------------------
# Import from the staging cache
# ---------------------------------------------------------------------------


def staging_days(staging_root: Path, *, level: str = LEVEL) -> list[tuple[date, Path]]:
    """Every staged CSV for this level, oldest first.

    A `.err` sibling is an HTML error page saved under a CSV name, so that day
    still needs pulling: it is reported, never imported.
    """
    root = Path(staging_root) / "statcast" / level
    if not root.is_dir():
        return []
    found: list[tuple[date, Path]] = []
    for path in root.glob("*/*.csv"):
        try:
            found.append((date.fromisoformat(path.stem), path))
        except ValueError:
            continue
    return sorted(found)


def staging_errors(staging_root: Path, *, level: str = LEVEL) -> list[date]:
    """Days the staging puller saved as an error page. These still need pulling."""
    root = Path(staging_root) / "statcast" / level
    if not root.is_dir():
        return []
    days: list[date] = []
    for path in root.glob("*/*.err"):
        try:
            days.append(date.fromisoformat(path.stem))
        except ValueError:
            continue
    return sorted(days)


def import_staging_day(path: Path, game_date: Any, *, level: str = LEVEL) -> tuple[DayReport, bool]:
    """Re-validate one staged CSV and store it. Provenance carries over, trust
    does not: the staged bytes go through the same UT-14, UT-15, DT-01 and
    DT-02 as a live pull before they are allowed into the lake."""
    body = Path(path).read_bytes()
    report = validate_day(body, game_date, source=str(path))
    _, wrote = store_day(body, game_date, level=level)
    return report, wrote


def import_staging_tree(
    staging_root: Path, *, level: str = LEVEL, stream: Any = None
) -> list[DayReport]:
    """Import every staged day for this level. Idempotent: a day already in the
    lake is re-validated and not rewritten."""
    out = stream if stream is not None else sys.stdout
    reports: list[DayReport] = []
    wrote = 0
    for day, path in staging_days(staging_root, level=level):
        report, written = import_staging_day(path, day, level=level)
        reports.append(report)
        wrote += int(written)
    errors = staging_errors(staging_root, level=level)
    print(
        f"import: {len(reports)} staged day(s) validated, {wrote} written, "
        f"{len(reports) - wrote} already in the lake, {len(errors)} error page(s) skipped",
        file=out,
    )
    if errors:
        print(
            "import: these days are an HTML error page under a CSV name and still "
            "need pulling: " + ", ".join(day.isoformat() for day in errors),
            file=out,
        )
    return reports


# ---------------------------------------------------------------------------
# The live pull. One day, one request.
# ---------------------------------------------------------------------------


def pull_day(game_date: Any, *, level: str = LEVEL) -> DayReport:
    """Fetch one game-day through the one HTTP chokepoint, validate it, store it.

    absump.http.get carries the A3 throttle, the per-host daily cap, the cache
    that makes a re-run cost zero requests, and the manifest row. Nothing here
    touches the network itself.
    """
    day = paths.as_official_date(game_date)
    response = client.get(day_url(day))
    if response.dry_run:
        raise DayContractError("--dry-run prints a plan and returns no body")
    report = validate_day(response.content, day, source=response.url)
    store_day(response.content, day, level=level)
    return report


# ---------------------------------------------------------------------------
# Verify what is already on disk
# ---------------------------------------------------------------------------


def verify_lake(*, level: str = LEVEL, stream: Any = None) -> list[DayReport]:
    """Re-run UT-14, UT-15, DT-01 and DT-02 over every stored day.

    An empty lake is not a failure: the raw tree is gitignored, so a clean
    clone has none. A day that is present and wrong is a failure.
    """
    out = stream if stream is not None else sys.stdout
    days = raw_days(level=level)
    if not days:
        print("verify: no Statcast day on disk; nothing to check", file=out)
        return []
    reports = [validate_day(read_day(path), day, source=str(path)) for day, path in days]
    seasons = sorted({report.season for report in reports})
    widest = max(reports, key=lambda report: report.n_rows)
    digests = {report.header_sha256 for report in reports}
    print(
        f"verify: {len(reports)} day(s), seasons {seasons[0]}-{seasons[-1]}, "
        f"{len(digests)} header digest(s), max rows {widest.n_rows} on "
        f"{widest.game_date.isoformat()}, cap {ROW_CAP}",
        file=out,
    )
    return reports


#: The columns of out/tables/statcast_day_exceptions.csv.
EXCEPTION_COLUMNS: Final[tuple[str, ...]] = (
    "kind",
    "game_date",
    "n_scheduled_final",
    "n_in_csv",
    "missing_from_csv",
    "extra_in_csv",
)


def day_exceptions(
    reports: Sequence[DayReport], schedule: dict[date, set[int]]
) -> list[dict[str, Any]]:
    """Every disagreement between the day CSVs and the schedule, as CSV rows.

    `schedule` maps an officialDate to the game_pk of every Final game that
    day. The schedule is taken as authoritative over its own date span: a date
    inside the span and absent from the mapping had no Final games, which is
    what an off-day looks like, so an unexpected game_pk on such a day is
    reported rather than skipped. Reports outside the span are not judged.

    Two kinds of row:

      game_pk_mismatch  the day is on disk and its distinct game_pk set is not
                        the schedule's Final set. `missing_from_csv` is the
                        expected entry: a rained-out or cancelled game has an
                        officialDate and no pitches. `extra_in_csv` is not
                        expected and means the day list or the join key is
                        wrong.
      day_missing       the schedule has Final games that day and the day is
                        not on disk at all. Coverage, not correctness; W6.0's
                        backfill closes it.
    """
    if not schedule:
        return []
    first, last = min(schedule), max(schedule)
    rows: list[dict[str, Any]] = []
    on_disk = set()
    for report in reports:
        if not first <= report.game_date <= last:
            continue
        on_disk.add(report.game_date)
        want = schedule.get(report.game_date, set())
        have = set(report.game_pks)
        missing = sorted(want - have)
        extra = sorted(have - want)
        if missing or extra:
            rows.append(
                {
                    "kind": "game_pk_mismatch",
                    "game_date": report.game_date.isoformat(),
                    "n_scheduled_final": len(want),
                    "n_in_csv": len(have),
                    "missing_from_csv": " ".join(str(pk) for pk in missing),
                    "extra_in_csv": " ".join(str(pk) for pk in extra),
                }
            )
    for day in sorted(set(schedule) - on_disk):
        if not schedule[day]:
            continue
        rows.append(
            {
                "kind": "day_missing",
                "game_date": day.isoformat(),
                "n_scheduled_final": len(schedule[day]),
                "n_in_csv": "",
                "missing_from_csv": " ".join(str(pk) for pk in sorted(schedule[day])),
                "extra_in_csv": "",
            }
        )
    return sorted(rows, key=lambda row: (row["kind"], row["game_date"]))


def write_day_exceptions(rows: Sequence[dict[str, Any]], path: Path) -> Path:
    """Write the exceptions table. Sorted, so a re-run changes no bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(EXCEPTION_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m absump.ingest.statcast_day",
        description="W2.9. One Statcast game-day: the endpoint, the traps and the assertions.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="re-run UT-14, UT-15, DT-01 and DT-02 over every stored day. No request.",
    )
    parser.add_argument(
        "--import-staging",
        action="store_true",
        help="validate and store every day in the staging cache. No request.",
    )
    parser.add_argument(
        "--staging",
        default=str(paths.data_root() / "staging"),
        help="the staging cache root (default: data/staging)",
    )
    parser.add_argument(
        "--plan",
        nargs="+",
        metavar="DATE",
        default=None,
        help="print the URL for each day and send nothing",
    )
    parser.add_argument(
        "--pull",
        nargs="+",
        metavar="DATE",
        default=None,
        help="fetch each day through absump.http. One request per day.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not (args.verify or args.import_staging or args.plan or args.pull):
        _parser().print_help()
        return 2

    if args.plan:
        for stamp in args.plan:
            print(day_url(stamp))

    if args.import_staging:
        import_staging_tree(Path(args.staging))

    if args.pull:
        for stamp in args.pull:
            report = pull_day(stamp)
            print(
                f"pull: {report.game_date.isoformat()} {report.n_rows} rows, "
                f"{len(report.game_pks)} games, {report.n_untracked} untracked"
            )

    if args.verify:
        verify_lake()

    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main())
