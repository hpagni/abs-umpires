"""absump.ingest.savant_leaderboard -- the Savant ABS leaderboard parser (SOP W2.11).

The CSV export is dead. `?...&csv=true` returns HTTP 500 with a text/html body
even with the exact canonical parameters the page's own `serverParams` declare,
and the `year=` form fails the same way, so two independent parameter forms
fail. `absump.http` refuses both spellings, so nobody re-learns it.

The data therefore comes out of the page HTML. The page carries its own rows in
a script block:

    var absData = [ {...}, {...}, ... ];

which is read with the regex SOP W2.11 states, then `json.loads`. `serverParams`
and `leagueData` sit in the same block and are captured too; both are nested
objects, so they are read with a balanced JSON scan rather than a regex.

Every endpoint number this module asserts lives in `contracts/savant_absdata.yml`
and is read from there at runtime. SOP section 0.5 rule 4: a number that came
from an endpoint belongs in a contract, not in a module.

This module owns assertion DT-24:

    len(absData) == 524 (batter), 107 (catcher), 104 (pitcher); 86/87 keys;
    n_overturns + n_fails == n_challenges per record; view sum equals leagueData

with the pull-date tolerance the contract states: exact on the contract's pull
date, and afterwards a floor that may be exceeded by up to 6.0 percent, because
the regular season is still running.

THE SELF-CHECK, which is this step's verify command.

    python -m absump.ingest.savant_leaderboard --check

runs with no network and no 2026 datum on disk, so a clean clone proves it. It
does four things:

  1. checks the contract against itself: the view sums, the leagueData blocks
     and the league totals are one arithmetic system and must agree;
  2. builds a synthetic page from the contract, parses it with the real parser
     and runs the real DT-24 check over it, which must pass;
  3. mutates that page six ways and requires the DT-24 check to catch each one
     by the right assertion id. A gutted checker passes step 2 and fails here;
  4. runs DT-24 over every real page already in the raw cache, under the
     pull-date tolerance. There are none on a clean clone, and the launcher's
     28-view pull is what puts them there.

The synthetic page is a SHAPE fixture, not a data fixture. Its record counts,
key counts, sums, thresholds and maxima are the contract's, and its first batter
record is the contract's first record; the rest of its key names and values are
constructed, because the real key names beyond the ones the contract records
were never measured. DT-24 asserts the key COUNT, which was measured.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from absump import http
from absump import paths as lake

__all__ = [
    "ABSDATA_RE",
    "CONTRACT_PATH",
    "Finding",
    "ParsedPage",
    "check_dt24",
    "contract",
    "fetch_page",
    "page_url",
    "parse_page",
    "plan",
    "render_probe_table",
]

CONTRACT_PATH = lake.REPO_ROOT / "contracts" / "savant_absdata.yml"

#: SOP W2.11, verbatim. `_check_regex_matches_contract` asserts this literal is
#: the string `contracts/savant_absdata.yml` records, so the specification and
#: the code cannot drift apart.
ABSDATA_PATTERN = r"(?:var|const|let)\s+absData\s*=\s*(\[.*?\]);\s*\n"
ABSDATA_RE = re.compile(ABSDATA_PATTERN, re.S)

_OBJECT_RE = "(?:var|const|let)\\s+%s\\s*=\\s*"

_DECODER = json.JSONDecoder()


class ContractError(RuntimeError):
    """The contract file is absent, unreadable or internally inconsistent."""


class ParseError(RuntimeError):
    """The page does not carry the block this parser is specified to read."""


# ------------------------------------------------------------------ contract
_CONTRACT_CACHE: dict[str, Any] = {}


def contract(path: Path | None = None) -> dict[str, Any]:
    """The parsed contract, read once per process."""
    source = path or CONTRACT_PATH
    key = str(source)
    if key not in _CONTRACT_CACHE:
        if not source.exists():
            raise ContractError(f"{source} does not exist")
        with source.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if not isinstance(loaded, dict):
            raise ContractError(f"{source} is not a mapping")
        _CONTRACT_CACHE[key] = loaded
    return _CONTRACT_CACHE[key]


def _dt24(spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return dict((spec or contract())["dt24"])


def baseline_pull_date(spec: Mapping[str, Any] | None = None) -> date:
    """The day every count in the contract was measured."""
    return date.fromisoformat(str(_dt24(spec)["pull_date"]))


def tolerance_fraction(spec: Mapping[str, Any] | None = None) -> float:
    """The pull-date tolerance as a fraction, for a pull after the pull date."""
    return float(_dt24(spec)["tolerance_percent"]) / 100.0


# ----------------------------------------------------------------------- url
def page_url(level: str, challenge_type: str, season: int | str) -> str:
    """The canonical page URL for one view, from the constant in absump.http."""
    return http.SAVANT_ABS_LEADERBOARD_URL.format(
        level=level, challenge_type=challenge_type, season=season
    )


def plan(spec: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """The 28 page fetches this step schedules, in a fixed order.

    Seven challenge types, two levels, two seasons. SOP section 10.1 costs the
    same 28 at the A3 Savant delay. The delay and the cap are not repeated here:
    absump.http reads them from config/throttle.yml.
    """
    spec = spec or contract()
    selectors = spec["selectors"]
    rows: list[dict[str, Any]] = []
    for level in selectors["ddlLevel"]:
        for season in selectors["seasons"]:
            for challenge_type in selectors["ddlChalType"]:
                rows.append(
                    {
                        "level": level,
                        "season": int(season),
                        "challenge_type": challenge_type,
                        "url": page_url(level, challenge_type, season),
                        "dest": str(lake.raw_savant_absdata(level, challenge_type, season)),
                    }
                )
    return rows


# -------------------------------------------------------------------- parser
@dataclasses.dataclass(frozen=True)
class ParsedPage:
    """One leaderboard page, split into the three blocks it carries."""

    view: str
    abs_data: list[dict[str, Any]]
    server_params: dict[str, Any]
    league_data: dict[str, Any]
    pull_date: date | None = None


def _json_object_after(html: str, name: str) -> dict[str, Any]:
    """Read one named JS object with a balanced scan from its first brace.

    A non-greedy brace regex truncates `serverParams` at its first nested `}`,
    so the value is decoded with the JSON decoder itself, which knows where the
    object ends.
    """
    match = re.search(_OBJECT_RE % re.escape(name), html)
    if match is None:
        raise ParseError(f"the page carries no {name} assignment")
    start = match.end()
    while start < len(html) and html[start] in " \t\r\n":
        start += 1
    if start >= len(html) or html[start] != "{":
        raise ParseError(f"{name} is not assigned an object")
    try:
        value, _ = _DECODER.raw_decode(html, start)
    except ValueError as exc:
        raise ParseError(f"{name} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ParseError(f"{name} did not decode to an object")
    return value


def parse_page(html: str, *, view: str = "", pull_date: date | None = None) -> ParsedPage:
    """Split one leaderboard page into absData, serverParams and leagueData.

    absData is read with the regex SOP W2.11 states, verbatim, then json.loads.
    """
    match = ABSDATA_RE.search(html)
    if match is None:
        raise ParseError("the page carries no absData array")
    try:
        rows = json.loads(match.group(1))
    except ValueError as exc:
        raise ParseError(f"absData is not valid JSON: {exc}") from exc
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ParseError("absData is not an array of objects")
    return ParsedPage(
        view=view or str(_json_object_after(html, "serverParams").get("challengeType", "")),
        abs_data=rows,
        server_params=_json_object_after(html, "serverParams"),
        league_data=_json_object_after(html, "leagueData"),
        pull_date=pull_date,
    )


def fetch_page(level: str, challenge_type: str, season: int | str) -> ParsedPage:
    """Fetch one view through the chokepoint and parse it.

    Every throttle, budget, cache and manifest concern belongs to
    `absump.http.get`. This function adds the parse and nothing else.
    """
    response = http.get(page_url(level, challenge_type, season))
    return parse_page(response.text, view=challenge_type, pull_date=date.today())


def cached_pages(spec: Mapping[str, Any] | None = None) -> dict[str, ParsedPage]:
    """Every MLB 2026 view already in the raw cache, keyed by challenge type.

    The raw cache is keyed on the URL digest by `absump.http`, so the pages are
    found by asking the chokepoint where each planned URL lands. A view that has
    not been pulled is simply absent.
    """
    spec = spec or contract()
    views = set(_dt24(spec)["views"])
    season = int(spec["server_params"]["season"][0])
    level = str(spec["server_params"]["level"])
    found: dict[str, ParsedPage] = {}
    for row in plan(spec):
        if row["level"] != level or row["season"] != season:
            continue
        if row["challenge_type"] not in views:
            continue
        body = _cached_body(row["url"])
        if body is None:
            continue
        found[row["challenge_type"]] = parse_page(
            body, view=row["challenge_type"], pull_date=_cached_pull_date(row["url"])
        )
    return found


def _raw_cache_path(url: str) -> Path:
    """Where the chokepoint parked this URL's body.

    The three helpers below read private members of `absump.http`. They read the
    cache and the manifest; they never fetch. Every fetch goes through
    `absump.http.get`, which is the one call site rule 0.5.2 allows.
    """
    return http._dest_path(url)


def _cached_body(url: str) -> str | None:
    path = _raw_cache_path(url)
    if not path.exists():
        return None
    return http._read_raw(path).decode(http.SAVANT_CSV_ENCODING)


def _cached_pull_date(url: str) -> date | None:
    """The day the chokepoint fetched this URL, out of its own manifest."""
    row = http._manifest_index().get(url)
    if not row:
        return None
    stamp = str(row.get("fetched_at_utc") or "")
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").date()
    except ValueError:
        return None


# --------------------------------------------------------------------- DT-24
@dataclasses.dataclass(frozen=True)
class Finding:
    """One DT-24 clause and what the data said about it."""

    assertion: str
    passed: bool
    detail: str

    def line(self) -> str:
        return f"{'PASS' if self.passed else 'FAIL':4s} {self.assertion} {self.detail}"


def _band(
    expected: int, exact: bool, tolerance: float, scale: int | None = None
) -> tuple[int, int]:
    """The accepted range for a count: exact on the pull date, else a floor.

    `scale` is the quantity the tolerance is a fraction OF. It is the count
    itself for a total, and the view's record count for a count of records over
    a threshold, because such a count can be zero at the baseline and a fraction
    of zero is zero, which would refuse a pitcher who crosses ten challenges in
    the closing week. The rounding is up, so a nonzero baseline always gets at
    least one unit of room.
    """
    if exact:
        return expected, expected
    return expected, expected + math.ceil(tolerance * (expected if scale is None else scale))


def _within(
    observed: int, expected: int, exact: bool, tolerance: float, scale: int | None = None
) -> bool:
    low, high = _band(expected, exact, tolerance, scale)
    return low <= observed <= high


def _rate_near(observed: float, expected: float, exact: bool, epsilon: float, tolerance: float):
    """A rate matches to `epsilon` on the pull date, and to the band afterwards.

    An overturn rate is a ratio, not a count, so it drifts as the season runs
    rather than growing. On a later pull it is read against the same tolerance,
    applied to the rate itself.
    """
    limit = epsilon if exact else max(epsilon, tolerance * expected)
    return abs(observed - expected) <= limit, limit


def _league_side(league_data: Mapping[str, Any], side: str) -> Mapping[str, Any] | None:
    for key, value in league_data.items():
        if key.lower() == side and isinstance(value, dict):
            return value
    return None


def _sum(rows: Iterable[Mapping[str, Any]], key: str) -> int:
    total = 0
    for row in rows:
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        total += int(value)
    return total


def check_dt24(
    pages: Mapping[str, ParsedPage],
    *,
    spec: Mapping[str, Any] | None = None,
    pull_date: date | None = None,
) -> list[Finding]:
    """Run DT-24 over one set of views. Returns one Finding per clause, in order.

    `pages` is keyed by challenge type. A view the contract names and `pages`
    does not carry is reported as a failure, so a partial pull cannot pass by
    being quiet.
    """
    spec = spec or contract()
    dt24 = _dt24(spec)
    views = dt24["views"]
    baseline = baseline_pull_date(spec)
    observed_date = pull_date or baseline
    exact = observed_date <= baseline
    tolerance = tolerance_fraction(spec)
    epsilon = float(dt24["rate_epsilon_points"])
    required = list(dt24["required_keys"])
    findings: list[Finding] = []

    band_note = "exact" if exact else f"floor +{dt24['tolerance_percent']} percent"

    for view in sorted(views):
        want = views[view]
        page = pages.get(view)
        if page is None:
            findings.append(Finding("DT-24.1", False, f"{view} view absent from this pull"))
            continue
        rows = page.abs_data

        findings.append(
            Finding(
                "DT-24.1",
                _within(len(rows), int(want["records"]), exact, tolerance),
                f"{view} records {len(rows)}, contract {want['records']}, {band_note}",
            )
        )

        widths = sorted({len(row) for row in rows})
        findings.append(
            Finding(
                "DT-24.2",
                widths == [int(want["keys"])],
                f"{view} keys {widths}, contract [{want['keys']}]",
            )
        )

        broken = sum(
            1
            for row in rows
            if int(row.get("n_overturns", 0)) + int(row.get("n_fails", 0))
            != int(row.get("n_challenges", -1))
        )
        findings.append(
            Finding(
                "DT-24.3",
                broken == 0,
                f"{view} records where n_overturns + n_fails != n_challenges: {broken}",
            )
        )

        missing = sorted(key for key in required if any(key not in row for row in rows))
        findings.append(
            Finding(
                "DT-24.7",
                not missing,
                f"{view} required keys absent from at least one record: {missing}",
            )
        )

        challenges = _sum(rows, "n_challenges")
        overturns = _sum(rows, "n_overturns")
        findings.append(
            Finding(
                "DT-24.4",
                _within(challenges, int(want["sum_n_challenges"]), exact, tolerance)
                and _within(overturns, int(want["sum_n_overturns"]), exact, tolerance),
                f"{view} sum n_challenges {challenges} contract {want['sum_n_challenges']}, "
                f"sum n_overturns {overturns} contract {want['sum_n_overturns']}, {band_note}",
            )
        )

        rate = 100.0 * overturns / challenges if challenges else 0.0
        rate_ok, limit = _rate_near(
            rate, float(want["overturn_rate_percent"]), exact, epsilon, tolerance
        )
        findings.append(
            Finding(
                "DT-24.5",
                rate_ok,
                f"{view} overturn rate {rate:.4f} percent, contract "
                f"{want['overturn_rate_percent']}, limit {limit:.4f} points",
            )
        )

        ge10 = sum(1 for row in rows if int(row.get("n_challenges", 0)) >= 10)
        ge20 = sum(1 for row in rows if int(row.get("n_challenges", 0)) >= 20)
        biggest = max((int(row.get("n_challenges", 0)) for row in rows), default=0)
        scale = int(want["records"])
        max_ok = True
        max_note = "not measured"
        if want.get("max_n_challenges") is not None:
            max_ok = _within(biggest, int(want["max_n_challenges"]), exact, tolerance)
            max_note = str(want["max_n_challenges"])
        findings.append(
            Finding(
                "DT-24.6",
                _within(ge10, int(want["records_ge_10_challenges"]), exact, tolerance, scale)
                and _within(ge20, int(want["records_ge_20_challenges"]), exact, tolerance, scale)
                and max_ok,
                f"{view} >=10 chal {ge10} contract {want['records_ge_10_challenges']}, "
                f">=20 chal {ge20} contract {want['records_ge_20_challenges']}, "
                f"max {biggest} contract {max_note}, {band_note}",
            )
        )

    findings.extend(_check_league(pages, spec, exact, tolerance, epsilon))
    return findings


def _check_league(
    pages: Mapping[str, ParsedPage],
    spec: Mapping[str, Any],
    exact: bool,
    tolerance: float,
    epsilon: float,
) -> list[Finding]:
    """DT-24.8: the view sums reconcile to leagueData and to the league totals.

    Every view's page carries the same leagueData, so every copy is read and all
    of them must agree. Reading one page's copy and trusting it would let a
    single disagreeing page through, which is exactly the shape of a pull that
    straddled a game going final.
    """
    dt24 = _dt24(spec)
    views = dt24["views"]
    league = dt24["league_data"]
    totals = dt24["totals"]
    findings: list[Finding] = []

    if not pages:
        return [Finding("DT-24.8", False, "no view in this pull, so leagueData was never read")]

    for side in sorted(league):
        seen: dict[str, int] = {}
        absent: list[str] = []
        for view in sorted(pages):
            block = _league_side(pages[view].league_data, side)
            if block is None or "n_challenges" not in block:
                absent.append(view)
            else:
                seen[view] = int(block["n_challenges"])
        if absent:
            findings.append(
                Finding(
                    "DT-24.8",
                    False,
                    f"{side}: views {absent} carry no leagueData {side} n_challenges",
                )
            )
            continue
        members = sorted(view for view in views if views[view]["league_side"] == side)
        present = [view for view in members if view in pages]
        challenges = sum(_sum(pages[view].abs_data, "n_challenges") for view in present)
        stated = sorted(set(seen.values()))
        contract_challenges = int(league[side]["n_challenges"])
        findings.append(
            Finding(
                "DT-24.8",
                len(stated) == 1
                and _within(stated[0], contract_challenges, exact, tolerance)
                and len(present) == len(members)
                and _within(challenges, contract_challenges, exact, tolerance)
                and _within(challenges, stated[0], exact, tolerance),
                f"{side} views {present} sum n_challenges {challenges}, page leagueData "
                f"{stated}, contract {contract_challenges}",
            )
        )

    every = sorted(views)
    if all(view in pages for view in every):
        challenges = sum(_sum(pages[view].abs_data, "n_challenges") for view in every)
        overturns = sum(_sum(pages[view].abs_data, "n_overturns") for view in every)
        fails = challenges - overturns
        rate = 100.0 * overturns / challenges if challenges else 0.0
        rate_ok, limit = _rate_near(
            rate, float(totals["overturn_rate_percent"]), exact, epsilon, tolerance
        )
        findings.append(
            Finding(
                "DT-24.9",
                _within(challenges, int(totals["n_challenges"]), exact, tolerance)
                and _within(overturns, int(totals["n_overturns"]), exact, tolerance)
                and _within(fails, int(totals["n_fails"]), exact, tolerance)
                and rate_ok,
                f"league totals challenges {challenges} contract {totals['n_challenges']}, "
                f"overturns {overturns} contract {totals['n_overturns']}, "
                f"fails {fails} contract {totals['n_fails']}, "
                f"rate {rate:.4f} percent contract {totals['overturn_rate_percent']}, "
                f"limit {limit:.4f} points",
            )
        )
    else:
        findings.append(Finding("DT-24.9", False, "not every view was pulled, so no league total"))
    return findings


# ------------------------------------------------------- the contract's algebra
# DT-24 as SOP section 6.3 writes the assertion row, and the league totals SOP
# W2.11 states in bold. These are the acceptance criterion, not loose endpoint
# numbers, and they are mirrored here on purpose: the contract and the assertion
# are then two independent statements, and CT-11 and CT-12 fail if either one is
# edited alone. They cite `dt24.views` and `dt24.totals` of
# contracts/savant_absdata.yml, which is where the measurement lives (SOP
# section 0.5 rule 4).
_DT24_RECORDS_AND_KEYS = {
    "batter": (524, 86),
    "catcher": (107, 87),
    "pitcher": (104, 87),
}
_DT24_LEAGUE_TOTALS = {"n_challenges": 10167, "n_overturns": 5490, "n_fails": 4677}


def check_contract_algebra(spec: Mapping[str, Any] | None = None) -> list[Finding]:
    """The contract's own numbers are one arithmetic system. Check it closes.

    This runs before any page is looked at. It is what catches a transcription
    slip in the contract, which would otherwise make every later assertion agree
    with the wrong number.
    """
    spec = spec or contract()
    dt24 = _dt24(spec)
    views = dt24["views"]
    league = dt24["league_data"]
    totals = dt24["totals"]
    epsilon = float(dt24["rate_epsilon_points"])
    findings: list[Finding] = []

    for side in sorted(league):
        members = sorted(view for view in views if views[view]["league_side"] == side)
        summed = sum(int(views[view]["sum_n_challenges"]) for view in members)
        findings.append(
            Finding(
                "CT-1",
                summed == int(league[side]["n_challenges"]),
                f"{side}: views {members} sum n_challenges {summed}, "
                f"leagueData {league[side]['n_challenges']}",
            )
        )
        if "n_overturns" in league[side]:
            summed_ov = sum(int(views[view]["sum_n_overturns"]) for view in members)
            findings.append(
                Finding(
                    "CT-2",
                    summed_ov == int(league[side]["n_overturns"]),
                    f"{side}: views sum n_overturns {summed_ov}, "
                    f"leagueData {league[side]['n_overturns']}",
                )
            )
        if "n_fails" in league[side] and "n_overturns" in league[side]:
            closes = int(league[side]["n_overturns"]) + int(league[side]["n_fails"]) == int(
                league[side]["n_challenges"]
            )
            findings.append(
                Finding("CT-3", closes, f"{side}: leagueData n_overturns + n_fails = n_challenges")
            )

    all_challenges = sum(int(views[view]["sum_n_challenges"]) for view in views)
    all_overturns = sum(int(views[view]["sum_n_overturns"]) for view in views)
    findings.append(
        Finding(
            "CT-4",
            all_challenges == int(totals["n_challenges"])
            and all_overturns == int(totals["n_overturns"])
            and all_challenges - all_overturns == int(totals["n_fails"]),
            f"totals: challenges {all_challenges}/{totals['n_challenges']}, "
            f"overturns {all_overturns}/{totals['n_overturns']}, "
            f"fails {all_challenges - all_overturns}/{totals['n_fails']}",
        )
    )

    for view in sorted(views):
        want = views[view]
        rate = 100.0 * int(want["sum_n_overturns"]) / int(want["sum_n_challenges"])
        findings.append(
            Finding(
                "CT-5",
                abs(rate - float(want["overturn_rate_percent"])) <= epsilon,
                f"{view}: rate {rate:.4f} percent, contract {want['overturn_rate_percent']}",
            )
        )
        findings.append(
            Finding(
                "CT-6",
                int(want["records_ge_20_challenges"])
                <= int(want["records_ge_10_challenges"])
                <= int(want["records"]),
                f"{view}: >=20 {want['records_ge_20_challenges']} <= >=10 "
                f"{want['records_ge_10_challenges']} <= records {want['records']}",
            )
        )

    rate = 100.0 * int(totals["n_overturns"]) / int(totals["n_challenges"])
    findings.append(
        Finding(
            "CT-7",
            abs(rate - float(totals["overturn_rate_percent"])) <= epsilon,
            f"totals: rate {rate:.4f} percent, contract {totals['overturn_rate_percent']}",
        )
    )

    first = dt24["first_record"]
    findings.append(
        Finding(
            "CT-8",
            int(first["n_overturns"]) + int(first["n_fails"]) == int(first["n_challenges"]),
            f"first record {first['player_name']}: "
            f"{first['n_overturns']} + {first['n_fails']} = {first['n_challenges']}",
        )
    )

    findings.append(
        Finding(
            "CT-9",
            len(plan(spec)) == int(spec["pull"]["views"]),
            f"plan is {len(plan(spec))} page fetches, contract {spec['pull']['views']}",
        )
    )

    findings.append(
        Finding(
            "CT-10",
            str(spec["parse"]["absdata_regex"]) == ABSDATA_PATTERN,
            "the absData regex in this module is the one the contract states",
        )
    )

    stated = {view: (int(views[view]["records"]), int(views[view]["keys"])) for view in views}
    findings.append(
        Finding(
            "CT-11",
            stated == _DT24_RECORDS_AND_KEYS,
            f"records and keys per view {dict(sorted(stated.items()))}, "
            f"DT-24 {dict(sorted(_DT24_RECORDS_AND_KEYS.items()))}",
        )
    )

    stated_totals = {key: int(totals[key]) for key in _DT24_LEAGUE_TOTALS}
    findings.append(
        Finding(
            "CT-12",
            stated_totals == _DT24_LEAGUE_TOTALS,
            f"league totals {dict(sorted(stated_totals.items()))}, "
            f"W2.11 {dict(sorted(_DT24_LEAGUE_TOTALS.items()))}",
        )
    )
    return findings


# ------------------------------------------------------- the synthetic fixture
_IDENTITY_KEYS = (
    "year",
    "player_name",
    "player_at_bat",
    "id",
    "team_abbr",
    "player_team",
    "parent_org",
    "parent_org_code",
    "level",
    "levelCode",
)


def _counts(
    n: int, total: int, ge10: int, ge20: int, biggest: int | None, fixed: Sequence[int]
) -> list[int]:
    """A deterministic multiset of per-record challenge counts fitting DT-24.

    Three tiers, because the contract states how many records clear 10 and 20:
    `ge20` records at 20 or more, `ge10 - ge20` between 10 and 19, the rest
    between 1 and 9 (serverParams pins minChal to 1). Each tier starts at its
    floor, the stated maximum is placed once when there is one, and the
    remainder is spread evenly over the top tier.
    """
    fixed = list(fixed)
    n -= len(fixed)
    total -= sum(fixed)
    ge10 -= sum(1 for value in fixed if value >= 10)
    ge20 -= sum(1 for value in fixed if value >= 20)
    if min(n, ge10, ge20) < 0 or ge20 > ge10 or ge10 > n or total < 0:
        raise ContractError("the contract's thresholds cannot be realised")

    tiers = [
        [20, biggest if biggest is not None else 999, ge20],
        [10, 19 if biggest is None else min(19, biggest), ge10 - ge20],
        [1, 9 if biggest is None else min(9, biggest), n - ge10],
    ]
    values: list[int] = []
    for floor, _cap, count in tiers:
        values.extend([floor] * count)
    remainder = total - sum(values)
    if remainder < 0:
        raise ContractError("the contract's sums are below the threshold floors")

    where = next((i for i, tier in enumerate(tiers) if tier[2] > 0), None)
    if where is None:
        if remainder:
            raise ContractError("no record to carry the remaining challenges")
        return sorted(fixed + values, reverse=True)
    floor, cap, count = tiers[where]
    start = sum(tier[2] for tier in tiers[:where])
    if biggest is not None and remainder >= cap - floor:
        values[start] = cap
        remainder -= cap - floor
        start += 1
        count -= 1
    if count > 0 and remainder:
        share, extra = divmod(remainder, count)
        for offset in range(count):
            bump = share + (1 if offset < extra else 0)
            if values[start + offset] + bump > cap:
                raise ContractError("the contract's sums exceed the stated maximum")
            values[start + offset] += bump
        remainder = 0
    if remainder:
        raise ContractError("the contract's sums do not fit the stated thresholds")
    return sorted(fixed + values, reverse=True)


def _overturns(counts: Sequence[int], total: int) -> list[int]:
    """Split `total` overturns across `counts`, proportionally and deterministically."""
    grand = sum(counts)
    if grand <= 0:
        return [0] * len(counts)
    shares = [value * total // grand for value in counts]
    order = sorted(
        range(len(counts)),
        key=lambda i: (-((counts[i] * total) % grand), i),
    )
    short = total - sum(shares)
    for i in order:
        if short <= 0:
            break
        if shares[i] < counts[i]:
            shares[i] += 1
            short -= 1
    if short:
        raise ContractError("the contract's overturns exceed its challenges")
    return shares


def _key_names(width: int, spec: Mapping[str, Any]) -> list[str]:
    """A deterministic key list of exactly `width` names.

    The first names are the ones the contract records, then their `*_against`
    mirrors, then the sort column, then filler. The filler is named `pad_NN` on
    purpose: these are not endpoint key names and must never be mistaken for
    them. DT-24 asserts the key count, which was measured, and the presence of
    the required keys, which were.
    """
    dt24 = _dt24(spec)
    first = dt24["first_record"]
    suffix = str(dt24["mirrored_key_suffix"])
    base = [key for key in first if key != "view"]
    names = list(base)
    names.extend(key + suffix for key in base if key not in _IDENTITY_KEYS)
    names.append("overturns_vs_exp")
    names.append("overturns_vs_exp" + suffix)
    index = 0
    while len(names) < width:
        index += 1
        names.append(f"pad_{index:02d}")
    if len(names) > width:
        raise ContractError(f"the contract names more than {width} keys")
    return names


def synthetic_page(view: str, spec: Mapping[str, Any] | None = None) -> str:
    """A page whose absData satisfies every DT-24 clause for one view.

    A shape fixture. It carries the contract's record count, key count, sums,
    thresholds and maximum, and for the batter view the contract's own first
    record. Everything else is constructed.
    """
    spec = spec or contract()
    dt24 = _dt24(spec)
    want = dt24["views"][view]
    first = dt24["first_record"]
    width = int(want["keys"])
    names = _key_names(width, spec)

    fixed: list[int] = []
    head: dict[str, Any] | None = None
    if str(first["view"]) == view:
        fixed = [int(first["n_challenges"])]
        head = {key: value for key, value in first.items() if key != "view"}

    counts = _counts(
        int(want["records"]),
        int(want["sum_n_challenges"]),
        int(want["records_ge_10_challenges"]),
        int(want["records_ge_20_challenges"]),
        want.get("max_n_challenges"),
        fixed,
    )
    if head is not None:
        counts.remove(int(first["n_challenges"]))
        counts.insert(0, int(first["n_challenges"]))
    overturns = _overturns(counts, int(want["sum_n_overturns"]))
    if head is not None:
        wanted = int(first["n_overturns"])
        delta = wanted - overturns[0]
        if delta > 0:
            donors = (i for i in range(1, len(counts)) if overturns[i] >= delta)
        else:
            donors = (i for i in range(1, len(counts)) if counts[i] - overturns[i] >= -delta)
        donor = next(donors, None) if delta else 0
        if donor is None:
            raise ContractError("the first record's overturns cannot be honoured")
        if delta:
            overturns[donor] -= delta
            overturns[0] = wanted

    rows: list[dict[str, Any]] = []
    for index, (challenges, over) in enumerate(zip(counts, overturns, strict=True)):
        row: dict[str, Any] = {}
        for name in names:
            row[name] = 0.0 if name.startswith(("rate_", "exp_", "net_", "runs_")) else 0
        row.update(
            {
                "year": int(first["year"]),
                "player_name": f"Player {index:04d}",
                "player_at_bat": 600000 + index,
                "id": 600000 + index,
                "team_abbr": "WSH",
                "player_team": int(first["player_team"]),
                "parent_org": "WSH",
                "parent_org_code": int(first["parent_org_code"]),
                "level": str(first["level"]),
                "levelCode": int(first["levelCode"]),
                "n_total_sample": 100 * challenges,
                "n_challenges": challenges,
                "n_overturns": over,
                "n_fails": challenges - over,
            }
        )
        if index == 0 and head is not None:
            for key, value in head.items():
                row[key] = value
        rows.append(row)

    params = dict(spec["server_params"])
    params["challengeType"] = view
    league = {side: dict(block) for side, block in dt24["league_data"].items()}
    return (
        "<!DOCTYPE html>\n<html><head><title>ABS challenges</title></head><body>\n"
        "<script>\n"
        f"var serverParams = {json.dumps(params, sort_keys=True)};\n"
        f"var leagueData = {json.dumps(league, sort_keys=True)};\n"
        f"var absData = {json.dumps(rows)};\n"
        "</script>\n</body></html>\n"
    )


def synthetic_pages(spec: Mapping[str, Any] | None = None) -> dict[str, ParsedPage]:
    spec = spec or contract()
    return {
        view: parse_page(synthetic_page(view, spec), view=view)
        for view in sorted(_dt24(spec)["views"])
    }


# ------------------------------------------------------------- the probe table
def render_probe_table(spec: Mapping[str, Any] | None = None) -> str:
    """The CSV probe table, rendered from the contract so the two cannot drift."""
    spec = spec or contract()
    block = spec["csv_export"]
    columns = list(block["columns"])
    lines = [",".join(columns)]
    for probe in block["probes"]:
        cells = []
        for column in columns:
            value = probe.get(column, "")
            text = "" if value is None else str(value)
            cells.append(f'"{text}"' if ("," in text or '"' in text) else text)
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def probe_table_path(spec: Mapping[str, Any] | None = None) -> Path:
    return lake.REPO_ROOT / str((spec or contract())["csv_export"]["table"])


def write_probe_table(spec: Mapping[str, Any] | None = None) -> bool:
    """Write the probe table only when it would change. Returns True if written."""
    spec = spec or contract()
    path = probe_table_path(spec)
    body = render_probe_table(spec)
    if path.exists() and path.read_text(encoding="utf-8") == body:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return True


def probe_csv_export(level: str, challenge_type: str, season: int | str) -> str:
    """Re-probe the dead CSV export through the chokepoint and say what happened.

    SOP W2.11 asks for one re-test in November, recorded either way. The result
    is printed and goes into `contracts/savant_absdata.yml` under
    `csv_export.probes`, which is what renders the probe table; nothing is
    appended to the table directly, so the contract stays the one source.
    """
    url = page_url(level, challenge_type, season) + "&csv=true"
    try:
        response = http.get(url)
    except http.Fatal as exc:
        return f"refused before the wire: {type(exc).__name__}: {exc}"
    return (
        f"status {response.status_code}, "
        f"content-type {response.headers.get('content-type', 'unknown')}, "
        f"{len(response.content)} bytes"
    )


# -------------------------------------------------------------- the self-check
_MUTATIONS = (
    ("drop one record", "DT-24.1"),
    ("add a key to one record", "DT-24.2"),
    ("break n_overturns + n_fails", "DT-24.3"),
    ("move a record over the 10-challenge line", "DT-24.6"),
    ("rewrite leagueData n_challenges", "DT-24.8"),
    ("rename a required key", "DT-24.7"),
)


def _mutate(pages: Mapping[str, ParsedPage], what: str) -> dict[str, ParsedPage]:
    """One targeted corruption of the synthetic pages, by deep copy."""
    copied = {
        view: ParsedPage(
            view=page.view,
            abs_data=json.loads(json.dumps(page.abs_data)),
            server_params=json.loads(json.dumps(page.server_params)),
            league_data=json.loads(json.dumps(page.league_data)),
        )
        for view, page in pages.items()
    }
    page = copied["catcher"]
    if what == "drop one record":
        page.abs_data.pop()
    elif what == "add a key to one record":
        page.abs_data[0]["an_extra_key"] = 1
    elif what == "break n_overturns + n_fails":
        page.abs_data[0]["n_fails"] = int(page.abs_data[0]["n_fails"]) + 1
    elif what == "move a record over the 10-challenge line":
        low = next(row for row in page.abs_data if int(row["n_challenges"]) < 10)
        high = next(row for row in page.abs_data if int(row["n_challenges"]) > 11)
        moved = 10 - int(low["n_challenges"])
        low["n_challenges"] += moved
        low["n_fails"] += moved
        high["n_challenges"] -= moved
        high["n_fails"] -= moved
    elif what == "rewrite leagueData n_challenges":
        for side in page.league_data.values():
            if isinstance(side, dict) and "n_challenges" in side:
                side["n_challenges"] = int(side["n_challenges"]) + 1
    elif what == "rename a required key":
        page.abs_data[0]["n_total_sample_renamed"] = page.abs_data[0].pop("n_total_sample")
    else:  # pragma: no cover - the table above is the whole set
        raise ValueError(what)
    return copied


def self_check(stream: Any) -> int:
    """The verify command. No network, no 2026 datum, deterministic output."""
    spec = contract()
    dt24 = _dt24(spec)
    failures = 0
    checks = 0

    def emit(text: str = "") -> None:
        print(text, file=stream)

    emit("W2.11 Savant ABS leaderboard, DT-24")
    emit(f"contract      {CONTRACT_PATH.relative_to(lake.REPO_ROOT)}")
    emit(f"pull date     {dt24['pull_date']}")
    emit(f"tolerance     {dt24['tolerance_percent']} percent above the floor for a later pull")
    emit(f"views         {', '.join(sorted(dt24['views']))}")
    emit()

    emit("contract algebra")
    for finding in check_contract_algebra(spec):
        checks += 1
        failures += 0 if finding.passed else 1
        emit("  " + finding.line())
    emit()

    emit("synthetic page, every clause must pass")
    pages = synthetic_pages(spec)
    for finding in check_dt24(pages, spec=spec):
        checks += 1
        failures += 0 if finding.passed else 1
        emit("  " + finding.line())
    emit()

    emit("mutated page, each corruption must be caught by its clause")
    for what, assertion in _MUTATIONS:
        checks += 1
        caught = {
            finding.assertion
            for finding in check_dt24(_mutate(pages, what), spec=spec)
            if not finding.passed
        }
        ok = assertion in caught
        failures += 0 if ok else 1
        emit(f"  {'PASS' if ok else 'FAIL':4s} {assertion} {what}, caught {sorted(caught)}")
    emit()

    emit("parser refuses a page it cannot read")
    for label, body in (
        ("no absData block", "<html><script>var other = [];\n</script></html>"),
        ("absData is not an array", "<html><script>var absData = {};\n</script></html>"),
    ):
        checks += 1
        try:
            parse_page(body)
        except ParseError:
            emit(f"  PASS ParseError {label}")
        else:
            failures += 1
            emit(f"  FAIL ParseError {label}, the parser accepted it")
    emit()

    emit("chokepoint refuses the two dead parameter forms")
    for label, url in (
        ("csv=true", page_url("mlb", "batter", 2026) + "&csv=true"),
        ("year=", page_url("mlb", "batter", 2026).replace("season%5B%5D=", "year=")),
    ):
        checks += 1
        try:
            http.get(url)
        except http.Fatal:
            emit(f"  PASS refused {label}")
        else:
            failures += 1
            emit(f"  FAIL accepted {label}")
    emit()

    emit("probe table")
    path = probe_table_path(spec)
    checks += 1
    if not path.exists():
        failures += 1
        emit(f"  FAIL {path.relative_to(lake.REPO_ROOT)} does not exist")
    elif path.read_text(encoding="utf-8") != render_probe_table(spec):
        failures += 1
        emit(f"  FAIL {path.relative_to(lake.REPO_ROOT)} is not what the contract renders")
    else:
        rows = len(spec["csv_export"]["probes"])
        emit(f"  PASS {path.relative_to(lake.REPO_ROOT)} matches the contract, {rows} probes")
    emit()

    emit("pages in the raw cache")
    found = cached_pages(spec)
    if not found:
        emit("  none on disk; the 28-view pull has not run here")
    else:
        dates = sorted({page.pull_date for page in found.values() if page.pull_date})
        observed = dates[-1] if dates else None
        emit(f"  views {sorted(found)}, pull date {observed or 'unknown'}")
        for finding in check_dt24(found, spec=spec, pull_date=observed):
            checks += 1
            failures += 0 if finding.passed else 1
            emit("  " + finding.line())
    emit()

    emit(f"DT-24: {checks} checks, {checks - failures} passed, {failures} failed")
    return 1 if failures else 0


# ---------------------------------------------------------------- command line
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="absump.ingest.savant_leaderboard",
        description="Savant ABS leaderboard parser and DT-24 gate (SOP W2.11).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="run DT-24; this step's verify command")
    group.add_argument("--plan", action="store_true", help="print the 28 planned page fetches")
    group.add_argument("--write-probe", action="store_true", help="render the CSV probe table")
    group.add_argument(
        "--probe-csv",
        action="store_true",
        help="re-probe the dead csv=true export through the chokepoint and print the result",
    )
    group.add_argument(
        "--fetch",
        nargs=3,
        metavar=("LEVEL", "CHALLENGE_TYPE", "SEASON"),
        help="fetch and parse one view through absump.http",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.check:
        return self_check(sys.stdout)

    if args.plan:
        for row in plan():
            print(f"{row['level']} {row['season']} {row['challenge_type']} {row['url']}")
        print(f"{len(plan())} page fetches")
        return 0

    if args.write_probe:
        changed = write_probe_table()
        path = probe_table_path().relative_to(lake.REPO_ROOT)
        print(f"{path} {'written' if changed else 'unchanged'}")
        return 0

    if args.probe_csv:
        print(probe_csv_export("mlb", "batter", 2026))
        return 0

    level, challenge_type, season = args.fetch
    page = fetch_page(level, challenge_type, season)
    print(f"{challenge_type} {len(page.abs_data)} records, {len(page.server_params)} serverParams")
    return 0


if __name__ == "__main__":
    sys.exit(main())
