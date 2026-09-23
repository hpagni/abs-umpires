"""absump.ingest.savant_framing -- the Savant catcher-framing export, 2015-2026.

SOP step W4.4. Twelve requests, one per season, the last leg of the 100 drawer,
leaderboard and framing requests on Savant (SOP section 10.1: 12 requests, about
2 minutes at the A3 Savant policy of 10 s between requests under an 800/day cap).
Every request goes through ``absump.http.get``, so the interval, the daily cap,
the raw cache and ``data/raw/_manifest.csv`` all apply, and a re-run of a finished
pull costs zero requests.

This module owns DT-26, the framing data test, and holds it in one place:

    framing CSV: text/csv, 13,808 B, 58 rows, 21 columns, min(pitches) == 2573,
    min=1 byte-identical.

The ``min=`` parameter is the point of the last clause. ``min=1`` returns the same
13,808 bytes as ``min=q``, so the parameter is ignored and the export is qualified
catchers only. The public framing benchmark therefore covers 58 catchers, not the
107 in the ABS catcher view (DT-24). That is a published limitation of the source,
recorded in owner decision D-35, and it is not something the puller works around.

Two endpoint facts are written down here so nobody re-learns them:

* The framing endpoint is ``/leaderboard/catcher-framing`` and it takes the
  ``year=`` form with ``csv=true``. The ``season[]=`` form and the refusal of
  ``csv=true`` in ``absump.http`` are scoped to ``/leaderboard/abs-challenges``,
  a different endpoint with the opposite contract (SOP W2.11, W4.2). Do not
  "correct" this URL to match that one.
* Every Savant CSV carries a UTF-8 BOM, so every body here is decoded with
  ``utf-8-sig`` and never with plain ``utf-8`` (UT-14).

The module issues nothing at import. ``pull()`` is the only function that can
reach the network, and it does so only through ``absump.http.get``.

RECORDED CAUTION, 2026 (for the owner, not decided here). The export is a
season-to-date aggregate and the endpoint has no date parameter, so a 2026 pull
taken after 2026-09-21 necessarily includes games inside the sealed window. The
phase cutoff cannot be expressed in this request. The pull date is in
``data/raw/_manifest.csv`` for every row, which is what lets the aggregate be
dated; the same fact makes the exact 13,808 B figure a measurement of the file as
it stood on the SOP's measurement date rather than a constant of the endpoint.
"""

from __future__ import annotations

import csv
import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from absump import http

__all__ = [
    "ABS_VIEW_CATCHERS",
    "COLUMNS",
    "CONTRACT_SEASON",
    "MIN_ONE",
    "MIN_QUALIFIED",
    "QUALIFIED_CATCHERS",
    "SEASONS",
    "Check",
    "ContractError",
    "FramingTable",
    "SeasonPull",
    "assert_contract",
    "cached_body",
    "framing_url",
    "parse",
    "probe_min_ignored",
    "pull",
    "report",
    "season_urls",
    "verify_contract",
]

# --------------------------------------------------------------------------
# The request. SOP section 6.1, step W4.4, states this URL literally.
# --------------------------------------------------------------------------

HOST = "baseballsavant.mlb.com"

#: The W4.4 URL, with the season and the ``min=`` value as the only variables.
#: SOP W4.4 gives the 2026 form verbatim; ``framing_url(2026)`` reproduces it
#: character for character and ``tests/data/test_framing.py`` asserts that.
URL_TEMPLATE = (
    "https://baseballsavant.mlb.com/leaderboard/catcher-framing"
    "?year={season}&team=&min={min_param}&type=catcher&sort=4&sortDir=desc&csv=true"
)

#: The qualified-catcher form, the one the twelve-request pull uses.
MIN_QUALIFIED = "q"

#: The twin used once to prove the parameter is ignored (DT-26, last clause).
MIN_ONE = "1"

FIRST_SEASON = 2015
LAST_SEASON = 2026

#: SOP W4.4: "Repeat for 2015-2026." Twelve seasons, twelve requests, which is
#: the row section 10.1 budgets as "Savant catcher framing 2015-2026 | 12 | 2 min".
SEASONS: tuple[int, ...] = tuple(range(FIRST_SEASON, LAST_SEASON + 1))

# --------------------------------------------------------------------------
# The contract. Every number below came from the endpoint and carries the SOP
# line that measured it (section 0.5 rule 4).
# --------------------------------------------------------------------------

#: SOP W4.4, the column list, in this order. Five identity and total columns and
#: then a run-value / percentage pair for each of the eight shadow zones.
COLUMNS: tuple[str, ...] = (
    "id",
    "name",
    "pitches",
    "rv_tot",
    "pct_tot",
    "rv_11",
    "pct_11",
    "rv_12",
    "pct_12",
    "rv_13",
    "pct_13",
    "rv_14",
    "pct_14",
    "rv_16",
    "pct_16",
    "rv_17",
    "pct_17",
    "rv_18",
    "pct_18",
    "rv_19",
    "pct_19",
)

#: SOP W4.4 and DT-26: 21 columns.
N_COLUMNS = 21

#: The season the SOP measured. Every exact figure below is that season's file.
CONTRACT_SEASON = 2026

#: SOP W4.4: "HTTP 200, text/csv, 13,808 B, UTF-8 BOM, 58 rows".
CONTRACT_STATUS = 200
CONTRACT_CONTENT_TYPE = "text/csv"
CONTRACT_BYTES = 13_808
CONTRACT_ROWS = 58

#: SOP W4.4: "pitches 2,573-8,769". DT-26 gates the lower bound exactly.
CONTRACT_MIN_PITCHES = 2_573
CONTRACT_MAX_PITCHES = 8_769

#: SOP W4.4: "rv_tot -10.72 to +7.78".
CONTRACT_MIN_RV_TOT = -10.72
CONTRACT_MAX_RV_TOT = 7.78

#: SOP W4.4: the export is qualified catchers only, so the public framing
#: benchmark covers 58 catchers.
QUALIFIED_CATCHERS = 58

#: DT-24: the ABS catcher view carries 107 catchers. The gap between these two
#: numbers is the published limitation D-35 records, not a bug to work around.
ABS_VIEW_CATCHERS = 107

#: The UTF-8 BOM every Savant CSV carries (UT-14).
BOM = b"\xef\xbb\xbf"

#: Clauses that only a live response can carry. A cached body has no response
#: headers, so ``pull()`` requires these on the wire and ``cached_body()`` does
#: not. Stated rather than silently skipped.
LIVE_CLAUSES: tuple[str, ...] = ("status", "content_type")

#: The repository root, so the manifest is found from any working directory.
#: ``absump.http`` resolves its own cache root the same way.
REPO_ROOT = Path(__file__).resolve().parents[3]

_MANIFEST = Path("data") / "raw" / "_manifest.csv"


class ContractError(RuntimeError):
    """A framing export that does not meet the W4.4 contract."""


@dataclass(frozen=True)
class Check:
    """One clause of DT-26 or UT-14, and what was observed."""

    test_id: str
    clause: str
    passed: bool
    observed: str


@dataclass(frozen=True)
class FramingTable:
    """One parsed framing export."""

    season: int
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    byte_length: int
    had_bom: bool

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    def column(self, name: str) -> tuple[str, ...]:
        index = self.columns.index(name)
        return tuple(row[index] for row in self.rows)

    def records(self) -> tuple[dict[str, str], ...]:
        return tuple(dict(zip(self.columns, row, strict=True)) for row in self.rows)


@dataclass(frozen=True)
class SeasonPull:
    """What ``pull()`` returns for one season."""

    season: int
    url: str
    table: FramingTable | None
    checks: tuple[Check, ...]
    from_cache: bool
    dry_run: bool


# --------------------------------------------------------------------------
# URLs
# --------------------------------------------------------------------------


def framing_url(season: int, *, min_param: str = MIN_QUALIFIED) -> str:
    """The W4.4 export URL for one season.

    ``min_param`` is ``"q"`` for the twelve-request pull and ``"1"`` for the
    DT-26 twin that proves the parameter is ignored.
    """
    year = int(season)
    if year < FIRST_SEASON or year > LAST_SEASON:
        raise ValueError(f"season {year} is outside the W4.4 range {FIRST_SEASON}-{LAST_SEASON}")
    return URL_TEMPLATE.format(season=year, min_param=min_param)


def season_urls(seasons: tuple[int, ...] = SEASONS) -> tuple[str, ...]:
    """The URLs the pull sends: one per season, twelve for the default range."""
    return tuple(framing_url(season) for season in seasons)


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def decode(raw: bytes) -> str:
    """Decode a Savant body with ``utf-8-sig`` so the BOM never leaks (UT-14)."""
    return raw.decode(http.SAVANT_CSV_ENCODING)


def parse(raw: bytes, *, season: int = CONTRACT_SEASON) -> FramingTable:
    """Parse one framing export into a :class:`FramingTable`.

    The body is read with the stdlib CSV reader, not a dataframe library: the
    contract is about bytes, columns and row counts, and a reader that infers
    types would hide exactly the failures DT-26 is looking for.
    """
    text = decode(raw)
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    if not rows:
        raise ContractError("the framing export is empty")
    header = tuple(field.strip() for field in rows[0])
    body = tuple(tuple(field for field in row) for row in rows[1:])
    return FramingTable(
        season=int(season),
        columns=header,
        rows=body,
        byte_length=len(raw),
        had_bom=raw.startswith(BOM),
    )


def _as_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except (AttributeError, ValueError):
        return None


def _as_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except (AttributeError, ValueError):
        return None


# --------------------------------------------------------------------------
# DT-26
# --------------------------------------------------------------------------


def verify_contract(
    season: int,
    raw: bytes,
    *,
    status_code: int | None = None,
    content_type: str | None = None,
    min_one_raw: bytes | None = None,
) -> tuple[Check, ...]:
    """Check one framing export against W4.4 and return one Check per clause.

    Every season is checked for the UTF-8 BOM, the 21 columns in the SOP order,
    at least one row, a rectangular body, and numeric ``pitches`` and ``rv_tot``.
    The exact figures -- 13,808 bytes, 58 rows, the pitch bounds and the
    ``rv_tot`` bounds -- are the 2026 measurement, so they are checked on 2026
    and not imposed on the other eleven seasons.

    ``status_code`` and ``content_type`` are checked only when they were
    observed, because a body served from the raw cache carries no response
    headers. ``pull()`` requires them on a live fetch; see :data:`LIVE_CLAUSES`.

    ``min_one_raw`` is the ``min=1`` twin. When it is given, the last DT-26
    clause is checked: the two bodies must be byte-identical.
    """
    season = int(season)
    checks: list[Check] = []

    if status_code is not None:
        checks.append(
            Check(
                "DT-26",
                "status",
                status_code == CONTRACT_STATUS,
                f"HTTP {status_code}, expected {CONTRACT_STATUS}",
            )
        )
    if content_type is not None:
        observed = content_type.split(";")[0].strip().lower()
        checks.append(
            Check(
                "DT-26",
                "content_type",
                observed == CONTRACT_CONTENT_TYPE,
                f"{observed!r}, expected {CONTRACT_CONTENT_TYPE!r}",
            )
        )

    checks.append(
        Check(
            "UT-14",
            "bom",
            raw.startswith(BOM),
            "UTF-8 BOM present" if raw.startswith(BOM) else "no UTF-8 BOM",
        )
    )

    try:
        table = parse(raw, season=season)
    except (ContractError, UnicodeDecodeError) as exc:
        checks.append(Check("DT-26", "parse", False, str(exc)))
        return tuple(checks)

    checks.append(
        Check(
            "DT-26",
            "columns",
            table.columns == COLUMNS,
            f"{len(table.columns)} columns, "
            + ("in the SOP order" if table.columns == COLUMNS else f"{list(table.columns)}"),
        )
    )
    ragged = sorted({len(row) for row in table.rows if len(row) != N_COLUMNS})
    checks.append(
        Check(
            "DT-26",
            "rectangular",
            not ragged,
            "every row has 21 fields" if not ragged else f"row widths seen: {ragged}",
        )
    )

    if table.columns != COLUMNS or ragged:
        return tuple(checks)

    pitches = [_as_int(value) for value in table.column("pitches")]
    rv_tot = [_as_float(value) for value in table.column("rv_tot")]
    bad_pitches = sum(1 for value in pitches if value is None)
    bad_rv = sum(1 for value in rv_tot if value is None)
    checks.append(
        Check(
            "DT-26",
            "numeric",
            bad_pitches == 0 and bad_rv == 0,
            f"{bad_pitches} non-integer pitches, {bad_rv} non-numeric rv_tot",
        )
    )
    checks.append(
        Check("DT-26", "non_empty", table.n_rows > 0, f"{table.n_rows} rows"),
    )

    if season == CONTRACT_SEASON and bad_pitches == 0 and bad_rv == 0 and table.n_rows:
        checks.append(
            Check(
                "DT-26",
                "bytes",
                table.byte_length == CONTRACT_BYTES,
                f"{table.byte_length:,} B, expected {CONTRACT_BYTES:,} B",
            )
        )
        checks.append(
            Check(
                "DT-26",
                "rows",
                table.n_rows == CONTRACT_ROWS,
                f"{table.n_rows} rows, expected {CONTRACT_ROWS}",
            )
        )
        checks.append(
            Check(
                "DT-26",
                "pitches_min",
                min(pitches) == CONTRACT_MIN_PITCHES,
                f"min(pitches) {min(pitches):,}, expected {CONTRACT_MIN_PITCHES:,}",
            )
        )
        checks.append(
            Check(
                "DT-26",
                "pitches_max",
                max(pitches) == CONTRACT_MAX_PITCHES,
                f"max(pitches) {max(pitches):,}, expected {CONTRACT_MAX_PITCHES:,}",
            )
        )
        checks.append(
            Check(
                "DT-26",
                "rv_tot_min",
                round(min(rv_tot), 2) == CONTRACT_MIN_RV_TOT,
                f"min(rv_tot) {min(rv_tot)}, expected {CONTRACT_MIN_RV_TOT}",
            )
        )
        checks.append(
            Check(
                "DT-26",
                "rv_tot_max",
                round(max(rv_tot), 2) == CONTRACT_MAX_RV_TOT,
                f"max(rv_tot) {max(rv_tot)}, expected {CONTRACT_MAX_RV_TOT}",
            )
        )
        checks.append(
            Check(
                "DT-26",
                "qualified_only",
                table.n_rows == QUALIFIED_CATCHERS,
                f"{table.n_rows} catchers, not the {ABS_VIEW_CATCHERS} in the ABS "
                "catcher view (D-35)",
            )
        )

    if min_one_raw is not None:
        identical = min_one_raw == raw
        checks.append(
            Check(
                "DT-26",
                "min_ignored",
                identical,
                f"min=1 returned {len(min_one_raw):,} B and min=q returned "
                f"{len(raw):,} B, " + ("byte-identical" if identical else "and the bodies differ"),
            )
        )

    return tuple(checks)


def report(checks: tuple[Check, ...]) -> str:
    """One line per clause, the format the verify command prints."""
    return "\n".join(
        f"{'PASS' if check.passed else 'FAIL'} {check.test_id} {check.clause}: {check.observed}"
        for check in checks
    )


def assert_contract(season: int, checks: tuple[Check, ...]) -> None:
    """Raise :class:`ContractError` naming every failed clause."""
    failed = [check for check in checks if not check.passed]
    if failed:
        raise ContractError(
            f"season {season} framing export fails the W4.4 contract:\n" + report(tuple(failed))
        )


# --------------------------------------------------------------------------
# The cache, read without spending a request
# --------------------------------------------------------------------------


def _manifest_rows(root: Path | None = None) -> list[dict[str, str]]:
    path = (root or REPO_ROOT) / _MANIFEST
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def cached_body(url: str, *, root: Path | None = None) -> bytes | None:
    """The cached body for ``url``, or ``None`` when nothing is on disk.

    The manifest is consulted first and the destination file is checked for
    existence, so this never causes a request: ``absump.http.get`` is called
    only once both say the bytes are already cached, in which case it returns
    the cached copy without touching the network.
    """
    base = root or REPO_ROOT
    for row in _manifest_rows(base):
        if row.get("url") != url:
            continue
        dest = row.get("dest_path") or ""
        if not dest:
            continue
        path = Path(dest)
        if not path.is_absolute():
            path = base / path
        if path.exists():
            return http.get(url).content
    return None


# --------------------------------------------------------------------------
# The pull
# --------------------------------------------------------------------------


def pull(
    seasons: tuple[int, ...] = SEASONS,
    *,
    min_param: str = MIN_QUALIFIED,
    strict: bool = True,
) -> tuple[SeasonPull, ...]:
    """Fetch one framing export per season and check each one against W4.4.

    Twelve seasons means twelve requests, about 2 minutes at the 10 s Savant
    interval. A season already in ``data/raw`` costs no request:
    ``absump.http.get`` returns the cached copy.

    ``strict`` raises on the first season that fails its contract. A live fetch
    additionally requires the two clauses only a live response can carry, so a
    response served as ``text/html`` cannot pass unnoticed.
    """
    results: list[SeasonPull] = []
    for season in seasons:
        url = framing_url(season, min_param=min_param)
        response = http.get(url)
        if response.dry_run:
            results.append(SeasonPull(season, url, None, (), False, True))
            continue
        content_type = response.headers.get("content-type") if response.headers else None
        checks = verify_contract(
            season,
            response.content,
            status_code=None if response.from_cache else response.status_code,
            content_type=content_type,
        )
        if not response.from_cache:
            seen = {check.clause for check in checks}
            for clause in LIVE_CLAUSES:
                if clause not in seen:
                    checks = (
                        *checks,
                        Check("DT-26", clause, False, "not observed on a live response"),
                    )
        table = parse(response.content, season=season) if response.content else None
        if strict:
            assert_contract(season, checks)
        results.append(SeasonPull(season, url, table, checks, response.from_cache, False))
    return tuple(results)


def probe_min_ignored(season: int = CONTRACT_SEASON) -> tuple[Check, ...]:
    """The last DT-26 clause, against the endpoint.

    Fetches the ``min=1`` twin for one season and compares it byte for byte with
    the ``min=q`` body. This is one request beyond the twelve the SOP budgets,
    which is why it is a separate function and not part of :func:`pull`. Both
    bodies come from the raw cache when they are already there.
    """
    url_q = framing_url(season, min_param=MIN_QUALIFIED)
    url_one = framing_url(season, min_param=MIN_ONE)
    body_q = http.get(url_q).content
    body_one = http.get(url_one).content
    return verify_contract(season, body_q, min_one_raw=body_one)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

_USAGE = """usage: python -m absump.ingest.savant_framing [--plan | --dry-run] [--season YYYY]

  --plan          print the twelve URLs and exit. Nothing is read, nothing is sent.
  --dry-run       run the pull under absump.http's dry-run planner: no request
                  leaves the machine and the plan is printed.
  --season YYYY   restrict to one season. Repeatable.
  --probe-min     also send the min=1 twin for the contract season and check the
                  DT-26 byte-identity clause. One request beyond the twelve.

Without a flag the twelve seasons 2015-2026 are fetched through absump.http.get,
under the 10 s Savant interval and the 800/day cap of config/throttle.yml.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    seasons: list[int] = []
    plan = dry_run = probe = False
    while args:
        arg = args.pop(0)
        if arg == "--plan":
            plan = True
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--probe-min":
            probe = True
        elif arg == "--season":
            if not args:
                print(_USAGE, file=sys.stderr)
                return 2
            seasons.append(int(args.pop(0)))
        else:
            print(_USAGE, file=sys.stderr)
            return 2

    wanted = tuple(seasons) if seasons else SEASONS

    if plan:
        for url in season_urls(wanted):
            print(url)
        print(f"{len(wanted)} requests, 0 sent.")
        return 0

    if dry_run:
        os.environ["ABSUMP_DRY_RUN"] = "1"

    try:
        for result in pull(wanted):
            if result.dry_run:
                continue
            source = "cache" if result.from_cache else "wire "
            rows = result.table.n_rows if result.table else 0
            print(f"{result.season} {source} {rows} rows")
            print(report(result.checks))
        if probe:
            print(report(probe_min_ignored()))
    except ContractError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
