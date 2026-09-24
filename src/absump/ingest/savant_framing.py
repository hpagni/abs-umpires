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
import hashlib
import io
import os
import sys
from dataclasses import dataclass
from datetime import date
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
#: The form SOP W4.4 records, kept for the record and no longer sent. Measured
#: 2026-09-24: `year=` is ACCEPTED AND IGNORED. Twelve separate requests, one per
#: season 2015-2026, ten seconds apart, all returned the same sha256
#: (03cdbf7e881c01da...), 13,796 B, the live 2026 table. `season=` does the same.
#: Nothing in the response says so: HTTP 200, `text/csv`, a well-formed body.
#: serverParams on the page echoes `"year":"2015"` while reporting
#: `"seasonStart":2026,"seasonEnd":2026`, which is the tell.
URL_TEMPLATE_YEAR_IGNORED = (
    "https://baseballsavant.mlb.com/leaderboard/catcher-framing"
    "?year={season}&team=&min={min_param}&type=catcher&sort=4&sortDir=desc&csv=true"
)

#: The form that actually selects a season, read off the page's own selects
#: (`ddlSeasonStart`, `ddlSeasonEnd`) and its serverParams. Verified 2026-09-24:
#: `seasonStart=2015&seasonEnd=2015` returns 12,138 B and 56 rows, a different
#: body from the 2026 table, so the parameter is live.
URL_TEMPLATE = (
    "https://baseballsavant.mlb.com/leaderboard/catcher-framing"
    "?seasonStart={season}&seasonEnd={season}&team=&min={min_param}"
    "&type=catcher&sort=4&sortDir=desc&csv=true"
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

#: THE SEAL, AND WHY 2026 CANNOT BE PINNED TO A BYTE COUNT.
#:
#: The export is a season-to-date aggregate and the endpoint has no date
#: parameter, so what the 2026 file contains is decided by the day it is pulled
#: and by nothing the caller can say. Every number the SOP records for 2026 was
#: measured on 2026-09-22. The 2026-09-24 pull reads 13,796 B, max(pitches)
#: 8,832 against 8,769, max(rv_tot) 8.13 against 7.78 -- every quantity larger,
#: which is only possible if games were added. The ABS leaderboard, the same
#: host on the same night, says how many: batting n_total_sample 102,656 ->
#: 103,304 (+648) and fielding 231,223 -> 232,743 (+1,520), which at the
#: baseline's own per-game rates is 14.8 and 15.4 games. Fifteen games were
#: played on 2026-09-22 (16 scheduled, one postponed; 2026-09-23's 16 were still
#: in progress in the US when the pull ran at 01:47 UTC on 2026-09-24).
#:
#: 2026-09-22 is INSIDE the sealed window (DECISIONS.md: the sealed set is MLB
#: games from 2026-09-22 onward). So a 2026 framing aggregate pulled after
#: 2026-09-21 is not a stale constant to re-baseline; it is a sealed-set input.
#: It is captured, marked, and never pinned.
STATIC_LAST_SEASON = 2025

#: Seasons that are finished and cannot move. These keep byte-exact pinning.
STATIC_SEASONS: tuple[int, ...] = tuple(range(FIRST_SEASON, STATIC_LAST_SEASON + 1))

#: The season that is still being played, whose aggregate advances with it.
LIVE_SEASONS: tuple[int, ...] = tuple(range(STATIC_LAST_SEASON + 1, LAST_SEASON + 1))

#: The seal boundary. A live-season aggregate pulled after this date includes
#: sealed games. DECISIONS.md owns the date; it is restated, not decided, here.
SEAL_LAST_OPEN_DATE = date(2026, 9, 21)

#: Byte-exact baselines for the static seasons, measured 2026-09-24 through
#: `absump.http` with the `seasonStart`/`seasonEnd` form. A static season cannot
#: move, so any later difference is the endpoint changing under us and is a hard
#: failure. Filled by `--rebaseline`; empty means never measured, which is
#: reported and is not a pass.
CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "savant_framing.yml"


def _load_static_baselines() -> dict[int, dict[str, object]]:
    """The pinned static-season baselines from `contracts/savant_framing.yml`.

    Absent file or absent section means nothing is pinned, which every static
    season then reports as a failing `pinned` clause. Silence is never a pass.
    """
    if not CONTRACT_PATH.exists():
        return {}
    import yaml

    doc = yaml.safe_load(CONTRACT_PATH.read_text()) or {}
    rows = (doc.get("static_baselines") or {}) if isinstance(doc, dict) else {}
    return {int(season): dict(values) for season, values in rows.items()}


STATIC_BASELINES: dict[int, dict[str, object]] = _load_static_baselines()

#: The pin a static season carries, in the order it is written and read.
_BASELINE_KEYS: tuple[str, ...] = (
    "bytes",
    "rows",
    "sha256",
    "pitches_min",
    "pitches_max",
    "rv_tot_min",
    "rv_tot_max",
)


#: The day SOP W4.4 measured the 2026 file. Every exact 2026 figure is that day,
#: and that day is the seal boundary, so this module does not write it down:
#: GD-04 rule 4 fails on the boundary day anywhere in the repository, and W2.4
#: owns the one file that may name it. Read on demand, so importing this module
#: still opens no file.
def sop_baseline_date() -> str:
    """The W4.4 baseline day, read from `config/seal.yml` through the seal API."""
    from absump import seal

    return str(seal.SEAL_START_DATE)


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
    #: True when this is a live-season aggregate pulled after the seal boundary,
    #: so the file mixes open-window games with sealed ones and cannot be used
    #: as an open-set input. Captured and marked; never silently promoted.
    sealed_contaminated: bool = False


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


def season_class(season: int) -> str:
    """ "static" for a finished season, "live" for one still being played."""
    return "static" if int(season) in STATIC_SEASONS else "live"


def is_sealed_contaminated(season: int, pulled_on: date | None = None) -> bool:
    """Whether a pull of this season on this day mixes sealed games in.

    A static season cannot: it finished before the boundary existed. A live
    season does the moment the pull is taken after the last open day, because
    the endpoint carries no date parameter and serves season-to-date.
    """
    if season_class(season) == "static":
        return False
    return (pulled_on or date.today()) > SEAL_LAST_OPEN_DATE


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

    ready = bad_pitches == 0 and bad_rv == 0 and bool(table.n_rows)
    if ready and season_class(season) == "static":
        baseline = STATIC_BASELINES.get(int(season))
        if baseline is None:
            checks.append(
                Check(
                    "DT-26",
                    "pinned",
                    False,
                    f"season {season} is static and has no recorded baseline; "
                    "run --rebaseline once and commit the numbers",
                )
            )
        else:
            for key, observed in (
                ("bytes", table.byte_length),
                ("rows", table.n_rows),
                ("sha256", hashlib.sha256(raw).hexdigest()),
                ("pitches_min", min(pitches)),
                ("pitches_max", max(pitches)),
            ):
                expected = baseline[key]
                checks.append(
                    Check(
                        "DT-26",
                        key,
                        observed == expected,
                        f"{observed!r}, pinned {expected!r}",
                    )
                )
            for key, observed in (
                ("rv_tot_min", round(min(rv_tot), 2)),
                ("rv_tot_max", round(max(rv_tot), 2)),
            ):
                expected = baseline[key]
                checks.append(
                    Check("DT-26", key, observed == expected, f"{observed!r}, pinned {expected!r}")
                )
    elif ready:
        # A LIVE SEASON IS NOT PINNED. Every figure below is reported and none
        # of them is asserted, because the aggregate advances with the season
        # and a byte count measured yesterday is a measurement, not a contract.
        # The one thing that IS asserted is that the numbers never go backwards
        # against the last measurement the SOP holds, which is what a truncated
        # or swapped file would look like.
        checks.append(
            Check(
                "DT-26",
                "live_not_pinned",
                True,
                f"season {season} is still being played: {table.byte_length:,} B, "
                f"{table.n_rows} rows, pitches {min(pitches):,}-{max(pitches):,}, "
                f"rv_tot {round(min(rv_tot), 2)} to {round(max(rv_tot), 2)}; "
                f"the W4.4 baseline of {sop_baseline_date()} was {CONTRACT_BYTES:,} B, "
                f"{CONTRACT_ROWS} rows, pitches {CONTRACT_MIN_PITCHES:,}-"
                f"{CONTRACT_MAX_PITCHES:,}, rv_tot {CONTRACT_MIN_RV_TOT} to "
                f"{CONTRACT_MAX_RV_TOT} -- not an assertion",
            )
        )
        checks.append(
            Check(
                "DT-26",
                "live_monotone",
                max(pitches) >= CONTRACT_MAX_PITCHES and table.n_rows >= CONTRACT_ROWS,
                f"max(pitches) {max(pitches):,} >= {CONTRACT_MAX_PITCHES:,} and "
                f"{table.n_rows} rows >= {CONTRACT_ROWS}: a season-to-date "
                "aggregate may grow and may not shrink",
            )
        )
        checks.append(
            Check(
                "DT-26",
                "qualified_only",
                table.n_rows < ABS_VIEW_CATCHERS,
                f"{table.n_rows} catchers, fewer than the {ABS_VIEW_CATCHERS} in "
                "the ABS catcher view (D-35)",
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
        contaminated = is_sealed_contaminated(season)
        # A LIVE SEASON NEVER FAILS THE LEG. Its numbers are not a contract, and
        # 2015-2025 must not be lost to a season that is still being played.
        if strict and season_class(season) == "static":
            assert_contract(season, checks)
        results.append(
            SeasonPull(season, url, table, checks, response.from_cache, False, contaminated)
        )
    return tuple(results)


def write_static_baselines(seasons: tuple[int, ...] = STATIC_SEASONS) -> int:
    """Measure each finished season once and write its pin to the contract.

    A finished season cannot move, so one honest measurement is a contract for
    every pull afterwards. This is the only way a byte count becomes a pin here:
    it is never copied from a season that is still being played.
    """
    rows: dict[int, dict[str, object]] = {}
    for season in seasons:
        if season_class(season) != "static":
            raise ContractError(f"season {season} is not static and cannot be pinned")
        raw = http.get(framing_url(season)).content
        table = parse(raw, season=season)
        pitches = [_as_int(v) for v in table.column("pitches")]
        rv_tot = [_as_float(v) for v in table.column("rv_tot")]
        rows[season] = {
            "bytes": table.byte_length,
            "rows": table.n_rows,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "pitches_min": min(pitches),
            "pitches_max": max(pitches),
            "rv_tot_min": round(min(rv_tot), 2),
            "rv_tot_max": round(max(rv_tot), 2),
        }
        print(f"{season} pinned: {table.byte_length:,} B, {table.n_rows} rows")
    lines = [
        "# contracts/savant_framing.yml -- the Savant catcher-framing export (SOP W4.4, DT-26).",
        "#",
        "# WHAT THIS FILE IS FOR. DT-26 as the SOP writes it pins one season, 2026, to a byte",
        "# count. 2026 is still being played and the endpoint serves season-to-date with no date",
        "# parameter, so that pin fails every day the league plays and says nothing true when it",
        "# does. The distinction this file makes is between a season that is finished, which can",
        "# be pinned exactly and forever, and a season that is not, which cannot be pinned at all.",
        "#",
        "# THE ADDRESS. `year=` is accepted and ignored (measured 2026-09-24: twelve requests,",
        "# 2015-2026, all one sha256, all the live 2026 table). The page's own selects are",
        "# `ddlSeasonStart` and `ddlSeasonEnd`, and `seasonStart=`/`seasonEnd=` select for real.",
        "",
        "schema: absump/contracts/savant_framing/1",
        "owner: W4.4",
        "assertion: DT-26",
        "",
        "url_template: >-",
        "  " + URL_TEMPLATE,
        "year_parameter_is_ignored: true",
        "",
        "# The last day of the open window. A live-season aggregate pulled after it",
        "# mixes sealed games in. DECISIONS.md owns this date; it is restated here.",
        f'seal_last_open_date: "{SEAL_LAST_OPEN_DATE}"',
        f"static_seasons: [{STATIC_SEASONS[0]}, {STATIC_SEASONS[-1]}]",
        f"live_seasons: [{', '.join(str(s) for s in LIVE_SEASONS)}]",
        "",
        "# Measured once each, through absump.http, with the seasonStart/seasonEnd form.",
        "# A finished season cannot move, so a later difference is the endpoint changing.",
        "static_baselines:",
    ]
    for season in sorted(rows):
        values = rows[season]
        lines.append(f"  {season}:")
        for key in _BASELINE_KEYS:
            value = values[key]
            rendered = f'"{value}"' if isinstance(value, str) else value
            lines.append(f"    {key}: {rendered}")
    CONTRACT_PATH.write_text("\n".join(lines) + "\n")
    print(f"wrote {CONTRACT_PATH} with {len(rows)} static seasons")
    return 0


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
  --rebaseline    measure the static seasons 2015-2025 and write their pinned
                  baselines to contracts/savant_framing.yml. Run once, when the
                  endpoint's own shape has been shown to have changed.
  --probe-min     also send the min=1 twin for the contract season and check the
                  DT-26 byte-identity clause. One request beyond the twelve.

Without a flag the twelve seasons 2015-2026 are fetched through absump.http.get,
under the 10 s Savant interval and the 800/day cap of config/throttle.yml.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    seasons: list[int] = []
    plan = dry_run = probe = rebaseline = False
    while args:
        arg = args.pop(0)
        if arg == "--plan":
            plan = True
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--probe-min":
            probe = True
        elif arg == "--rebaseline":
            rebaseline = True
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

    if rebaseline:
        return write_static_baselines(tuple(s for s in wanted if season_class(s) == "static"))

    if dry_run:
        os.environ["ABSUMP_DRY_RUN"] = "1"

    try:
        for result in pull(wanted):
            if result.dry_run:
                continue
            source = "cache" if result.from_cache else "wire "
            rows = result.table.n_rows if result.table else 0
            mark = ""
            if result.sealed_contaminated:
                mark = (
                    "  SEALED-CONTAMINATED: a season-to-date aggregate pulled after "
                    f"{SEAL_LAST_OPEN_DATE}; benchmark only, never an open-set input"
                )
            print(f"{result.season} {source} {rows} rows [{season_class(result.season)}]{mark}")
            print(report(result.checks))
        if probe:
            print(report(probe_min_ignored()))
    except ContractError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
