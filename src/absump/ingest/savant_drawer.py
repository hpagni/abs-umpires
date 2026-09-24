"""The Savant per-team ABS challenge drawer. SOP step W4.2, assertion DT-25.

Chapter 2's spine. One request per team-season returns every ABS challenge that
team was party to, with geometry, roles, opponents, counts, innings, scores, the
umpire's original call, Savant's own expectation and -- uniquely for AAA --
``challenging_player_id``, which the Stats API feed does not carry. That is what
makes Chapter 2 Tier 1 independent of W2.

THE PARAMETER FORM IS THE CONTRACT. The data contract recorded this service as
unverified. It works, but only with the ``year=`` / ``gameType=regular`` form.
The ``season[]`` / ``gameType[]=R`` form that the leaderboard page itself
declares returns HTTP 200 with an 11-byte body, ``{"data":[]}``. A wrong
parameter form therefore fails silently, with a 200 and no rows, so every fetch
asserts against the empty envelope rather than trusting the status code.

WHAT THIS MODULE DOES. It builds the 60-target plan offline, it pulls each
target through ``absump.http`` under the section 5A.A3 throttle, it caches the
raw JSON, and it checks the four facts W4.2 derived from 1,276 cached rows:

  1. ``original_isStrike_ump`` exists, so the data contract's section 2.7 is
     true of the Stats API and the CSV but not of this service.
  2. ``edge_dist_calc`` is exactly reproducible by the SOP section 2.5 formula.
  3. Overturn is deterministic:
     ``is_challengeABS_overturned == XOR(original_isStrike_ump == 1,
     edge_dist_calc < 0)``.
  4. Role resolves without ambiguity from ``challenging_player_id`` matched
     against ``player_at_bat``, ``fielder_2`` and ``pitcher``.

``team_summary_mode`` is never read. It has four values only and buckets the 3
CIN pitcher challenges under ``catcher-for``, so it cannot carry role.

THE CUTOFF. The drawer is season-scoped: the endpoint has no date parameter, so
a 2026 request returns every regular-season row the service holds, including
rows dated past the phase cutoff of 2026-09-21. The request itself does not
cross the cutoff and cannot be made to stop short of it. The reader is the gate:
:func:`open_rows` drops every 2026 row past ``absump.paths.LAST_OPEN_DATE`` and
every analysis path in this module runs on its output. :func:`pull` reports the
count it dropped per file so the number is visible rather than assumed.

THIS MODULE ISSUES NO REQUEST OF ITS OWN. Every byte comes through
``absump.http.get``, which owns the delay, the daily cap, the cache and the
manifest. SOP section 0.5 rule 2.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from absump import http, paths

__all__ = [
    "DrawerError",
    "EmptyEnvelope",
    "Finding",
    "Target",
    "check_all",
    "contract",
    "drawer_url",
    "dt25",
    "edge_dist_in",
    "forbidden_keys",
    "load",
    "open_rows",
    "plan",
    "pull",
    "role_of",
]

REPO_ROOT: Path = Path(__file__).resolve().parents[3]
CONTRACT_PATH: Path = REPO_ROOT / "contracts" / "savant_drawer.yml"

#: The two team-seasons W4.2 pulls, in plan order. Both numbers come from the
#: contract file; neither is written here twice.
LEVEL_ORDER: tuple[str, ...] = ("mlb", "aaa")

#: Query keys the leaderboard page declares and this service ignores. A URL
#: carrying either one is refused before it can spend a request on an empty
#: body. SOP W4.2.
REFUSED_QUERY_KEYS: tuple[str, ...] = ("season[]", "gameType[]")

#: Role name to the row field whose value equals ``challenging_player_id`` when
#: that role challenged. Priority order, so a tie is reported rather than
#: silently resolved.
ROLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("batter", "player_at_bat"),
    ("catcher", "fielder_2"),
    ("pitcher", "pitcher"),
)

_CONTRACT: dict[str, Any] | None = None


class DrawerError(RuntimeError):
    """A drawer response or a drawer file broke the contract."""


class EmptyEnvelope(DrawerError):
    """HTTP 200 with no rows: the wrong parameter form, failing silently."""


# --------------------------------------------------------------------------
# The contract file
# --------------------------------------------------------------------------


def contract() -> dict[str, Any]:
    """``contracts/savant_drawer.yml``, read once per process."""
    global _CONTRACT
    if _CONTRACT is None:
        loaded = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise DrawerError(f"{CONTRACT_PATH} is not a YAML mapping")
        _CONTRACT = loaded
    return _CONTRACT


def _endpoint() -> dict[str, Any]:
    return contract()["endpoint"]


def teams(level: str) -> tuple[dict[str, Any], ...]:
    """The team index for one level, from the contract, sorted by id."""
    table = contract()["teams"][level]
    return tuple(sorted(table, key=lambda row: int(row["id"])))


def forbidden_keys() -> tuple[str, ...]:
    """The row fields W4.2 forbids, from the contract.

    The names are read from the contract rather than written here, so that this
    module's own source carries no read site for them and
    :func:`check_no_forbidden_key` can scan it honestly.
    """
    return tuple(str(key) for key in contract()["schema"]["forbidden_keys"])


def season_of(level: str) -> int:
    """The season W4.2 pulls for one level: MLB 2026, AAA 2025."""
    for row in contract()["pull"]["levels"]:
        if row["level"] == level:
            return int(row["season"])
    raise DrawerError(f"no pull season for level {level!r}")


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """One team-season: one request, one JSON file."""

    level: str
    season: int
    team_id: int
    team_name: str
    url: str
    path: Path

    @property
    def label(self) -> str:
        return f"{self.level} {self.season} {self.team_id} {self.team_name}"


def drawer_url(team_id: int | str, season: int | str, level: str) -> str:
    """Build the one form that returns rows, and refuse the one that does not."""
    if level not in LEVEL_ORDER:
        raise DrawerError(f"level must be one of {LEVEL_ORDER}, not {level!r}")
    url = str(_endpoint()["url_template"]).format(
        team_id=int(team_id), season=int(season), level=level
    )
    assert_working_form(url)
    return url


def assert_working_form(url: str) -> None:
    """Refuse a drawer URL that carries the form the page declares.

    SOP W4.2: the ``season[]`` / ``gameType[]=R`` form returns HTTP 200 and
    ``{"data":[]}``. It is refused here, before a request is spent on it.
    """
    for key in REFUSED_QUERY_KEYS:
        if key in url:
            raise DrawerError(
                f"{key} is the form the leaderboard page declares and the drawer "
                f"service ignores: it returns HTTP 200 with an empty data array. "
                f"Use year= and gameType=regular."
            )
    for key in ("year=", "challengeType=team-summary", "gameType=regular", "level="):
        if key not in url:
            raise DrawerError(f"drawer URL is missing {key!r}: {url}")


def plan(levels: Sequence[str] = LEVEL_ORDER) -> list[Target]:
    """The 60 team-seasons, offline. No request, no file read but the contract."""
    out: list[Target] = []
    for level in levels:
        season = season_of(level)
        for row in teams(level):
            team_id = int(row["id"])
            out.append(
                Target(
                    level=level,
                    season=season,
                    team_id=team_id,
                    team_name=str(row["name"]),
                    url=drawer_url(team_id, season, level),
                    path=paths.raw_savant_drawer(level, season, team_id),
                )
            )
    return out


# --------------------------------------------------------------------------
# Reading a response and a file
# --------------------------------------------------------------------------


def rows_of(payload: Any) -> list[dict[str, Any]]:
    """The ``data`` array, or raise :class:`EmptyEnvelope` when it is empty."""
    if not isinstance(payload, dict):
        raise DrawerError("drawer payload is not a JSON object")
    key = str(contract()["endpoint"]["payload_key"])
    data = payload.get(key)
    if not isinstance(data, list):
        raise DrawerError(f"drawer payload has no {key!r} array")
    if not data:
        raise EmptyEnvelope(
            "HTTP 200 with an empty data array. That is what the wrong parameter "
            "form returns, so it is a contract failure and not an empty season."
        )
    return [row for row in data if isinstance(row, dict)]


def load(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Read one cached drawer file and return its rows."""
    return rows_of(json.loads(Path(path).read_text(encoding="utf-8")))


def load_plan(targets: Iterable[Target]) -> dict[Target, list[dict[str, Any]]]:
    """Every target whose JSON file is on disk, with its rows."""
    return {target: load(target.path) for target in targets if target.path.exists()}


# --------------------------------------------------------------------------
# The cutoff
# --------------------------------------------------------------------------

#: The last open day. ``absump.paths`` owns it; nothing here restates it.
OPEN_THROUGH: _dt.date = paths.LAST_OPEN_DATE


def game_date_of(row: dict[str, Any]) -> _dt.date:
    """The row's game date, from the first ten characters of ``game_date``."""
    raw = str(row.get("game_date") or "")[:10]
    try:
        return _dt.date.fromisoformat(raw)
    except ValueError as exc:
        raw_date = row.get("game_date")
        raise DrawerError(f"drawer row has no readable game_date: {raw_date!r}") from exc


def open_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop every row past the cutoff.

    The drawer has no date parameter, so a 2026 pull returns rows past
    ``OPEN_THROUGH``. Seasons before 2026 are untouched: the cutoff is a 2026
    rule. ``gameType=regular`` is in the URL, so the postseason arm of the rule
    cannot appear in this feed.
    """
    kept: list[dict[str, Any]] = []
    for row in rows:
        # Parsed on every row, not only the ones the cutoff can reach: a row
        # whose date cannot be read is an error at every level, not a pass.
        played = game_date_of(row)
        earlier_season = int(row.get("year") or OPEN_THROUGH.year) < OPEN_THROUGH.year
        if earlier_season or played <= OPEN_THROUGH:
            kept.append(row)
    return kept


# --------------------------------------------------------------------------
# The four facts
# --------------------------------------------------------------------------


def _number(row: dict[str, Any], key: str) -> float:
    aliases = contract()["schema"].get("aliases") or {}
    for name in (key, aliases.get(key)):
        if name is not None and row.get(name) is not None:
            return float(row[name])
    raise DrawerError(f"drawer row has no {key!r}")


def _flag(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool):
        return int(value)
    if value is None:
        raise DrawerError(f"drawer row has no {key!r}")
    if isinstance(value, str):
        return int(value.strip().lower() in ("1", "true", "t", "yes"))
    return int(int(value) != 0)


def edge_dist_in(row: dict[str, Any]) -> float:
    """Savant's ``edge_dist_calc``, recomputed. SOP section 2.5.

    The any-part-of-ball rule on a 17-inch zone with a 1.45-inch ball radius,
    Euclidean at the corners. Reproduces the service's own column with max
    absolute error 0.000000 in on 1,276/1,276 rows.

    ``absump.zone`` is the production home for this formula. It does not exist
    yet, and W4.2 owns no path there, so this copy is the drawer's own
    verification of the service's column. When ``absump.zone`` lands, it imports
    this function or this function imports it; the formula is not written twice.
    """
    inches = float(contract()["facts"]["edge"]["feet_to_inches"])
    radius = float(contract()["facts"]["edge"]["ball_radius_in"])
    half_width = _number(row, "widthinches") / 2.0
    dx = abs(_number(row, "plateX")) * inches - half_width
    plate_z = _number(row, "plateZ") * inches
    dz = max(
        _number(row, "strikeZoneBottom") * inches - plate_z,
        plate_z - _number(row, "strikeZoneTop") * inches,
    )
    dist = math.hypot(dx, dz) if dx > 0 and dz > 0 else max(dx, dz)
    return dist - radius


def role_of(row: dict[str, Any]) -> str:
    """Who challenged: ``batter``, ``catcher`` or ``pitcher``.

    ``challenging_player_id`` matched against ``player_at_bat``, ``fielder_2``
    and ``pitcher``. Never ``team_summary_mode``: it has four values and buckets
    the 3 CIN pitcher challenges under ``catcher-for``.

    Raises :class:`DrawerError` on a row that matches none of the three or more
    than one of them. W4.2 measured 708/708 and 568/568 classified with zero
    unresolved, so an exception here is a contract change, not a data quirk.
    """
    challenger = row.get("challenging_player_id")
    if challenger is None:
        raise DrawerError("drawer row has no challenging_player_id")
    hits = [name for name, field in ROLE_FIELDS if row.get(field) == challenger]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise DrawerError(
            f"challenging_player_id {challenger!r} matches no role field "
            f"{[field for _, field in ROLE_FIELDS]}"
        )
    raise DrawerError(f"challenging_player_id {challenger!r} matches {hits}, which is ambiguous")


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One assertion's outcome, in the shape a receipt records."""

    id: str
    desc: str
    passed: bool
    observed: str

    def line(self) -> str:
        return f"{'PASS' if self.passed else 'FAIL'}  {self.id}  {self.desc}: {self.observed}"


def _no_rows(check_id: str, desc: str) -> Finding:
    """An empty row set fails. A check with nothing to read has proved nothing."""
    return Finding(check_id, desc, False, "0 rows to check")


def check_schema(rows: Sequence[dict[str, Any]]) -> Finding:
    """Fact 1 and the key count: every required key on every row."""
    desc = "drawer 66-key schema, 45 named keys required"
    if not rows:
        return _no_rows("DT-25.schema", desc)
    required = list(contract()["schema"]["required_keys"])
    aliases = contract()["schema"].get("aliases") or {}
    missing: set[str] = set()
    for row in rows:
        for key in required:
            if key in row or aliases.get(key) in row:
                continue
            missing.add(key)
    original = contract()["facts"]["original_call_key"]
    if original in missing:
        observed = f"{original} absent, so the drawer cannot carry the original call"
    elif missing:
        observed = f"{len(missing)} required key(s) absent: {sorted(missing)}"
    else:
        observed = f"{len(required)}/{len(required)} required keys present on {len(rows)} rows"
    return Finding("DT-25.schema", desc, not missing, observed)


def check_edge(rows: Sequence[dict[str, Any]]) -> Finding:
    """Fact 2: ``edge_dist_calc`` reproduced by the section 2.5 formula.

    The tolerance stays at 1e-6 in. Two AAA 2025 plays are named exceptions:
    the service's own ``edge_dist_calc`` disagrees with the ``plateX``,
    ``plateZ``, ``strikeZoneTop`` and ``strikeZoneBottom`` it publishes for the
    same play, by 0.766860 in and 0.529350 in. That is a fact about those two
    upstream rows, not about this formula or its column choice, and it is the
    same posture W2.15/DEV-35 takes to game 825000: name the play, hold the bar
    for every other one, and keep the breach visible in the observed line.
    """
    desc = "edge_dist_calc reproduced by SOP section 2.5"
    if not rows:
        return _no_rows("DT-25.edge", desc)
    spec = contract()["facts"]["edge"]
    tolerance = float(spec["tolerance_in"])
    known = {str(k) for k in spec.get("known_exceptions", {})}
    worst = 0.0
    seen: set[str] = set()
    for row in rows:
        err = abs(edge_dist_in(row) - _number(row, "edge_dist_calc"))
        play_id = str(row.get("play_id"))
        if err > tolerance and play_id in known:
            seen.add(play_id)
            continue
        worst = max(worst, err)
    checked = len(rows)
    note = f" ({len(seen)} named exceptions)" if seen else ""
    return Finding(
        "DT-25.edge",
        desc,
        worst <= tolerance,
        f"max abs error {worst:.6f} in on {checked}/{checked} rows, tolerance {tolerance} in{note}",
    )


def check_overturn(rows: Sequence[dict[str, Any]]) -> Finding:
    """Fact 3: overturn is deterministic, inside and outside the band."""
    desc = "is_challengeABS_overturned == XOR(original_isStrike_ump == 1, edge_dist_calc < 0)"
    if not rows:
        return _no_rows("DT-25.overturn", desc)
    band = float(contract()["facts"]["overturn"]["band_in"])
    bad = 0
    outside = 0
    bad_outside = 0
    for row in rows:
        edge = _number(row, "edge_dist_calc")
        expected = bool(_flag(row, "original_isStrike_ump") == 1) ^ bool(edge < 0)
        agrees = bool(_flag(row, "is_challengeABS_overturned")) == expected
        if not agrees:
            bad += 1
        if abs(edge) > band:
            outside += 1
            if not agrees:
                bad_outside += 1
    return Finding(
        "DT-25.overturn",
        desc,
        bad == 0,
        f"{len(rows) - bad}/{len(rows)} rows, {outside - bad_outside}/{outside} outside "
        f"the +/- {band} in band",
    )


def check_role(rows: Sequence[dict[str, Any]]) -> Finding:
    """Fact 4: role resolves, and role == batter iff the call was a strike."""
    desc = "role from challenging_player_id, and role == batter iff original_isStrike_ump == 1"
    if not rows:
        return _no_rows("DT-25.role", desc)
    unresolved = 0
    batter = 0
    mismatched = 0
    for row in rows:
        try:
            role = role_of(row)
        except DrawerError:
            unresolved += 1
            continue
        called_strike = _flag(row, "original_isStrike_ump") == 1
        if role == "batter":
            batter += 1
        if (role == "batter") != called_strike:
            mismatched += 1
    passed = unresolved == 0 and mismatched == 0
    return Finding(
        "DT-25.role",
        desc,
        passed,
        f"{len(rows) - unresolved}/{len(rows)} classified, {unresolved} unresolved, "
        f"{batter} batter, {mismatched} role/call mismatches",
    )


def read_sites(source: str, key: str) -> list[str]:
    """Lines in ``source`` that read ``key`` off a mapping or an attribute.

    The three idioms a Python reader can use: a subscript, ``.get`` and an
    attribute. Prose and backticked documentation are not read sites, so the
    patterns all carry a quote or a dot.

    LIMIT, stated rather than implied. This is a text scan, so a name split
    across a concatenation reads the field without matching any idiom here. The
    behavioural backstop is :func:`check_role`: role resolved from the forbidden
    field buckets the 3 CIN pitcher challenges under catcher, so the identity
    role == batter iff ``original_isStrike_ump == 1`` breaks and the check goes
    red. Both were confirmed against a planted bypass.
    """
    idioms = [f".{key}"]
    for quote in ("'", '"'):
        idioms.append(f"[{quote}{key}{quote}]")
        idioms.append(f".get({quote}{key}{quote}")
        idioms.append(f"pop({quote}{key}{quote}")
    return [line for line in source.splitlines() if any(idiom in line for idiom in idioms)]


def check_no_forbidden_key(rows: Sequence[dict[str, Any]]) -> Finding:
    """The drawer still carries the field W4.2 forbids, and nothing reads it."""
    keys = forbidden_keys()
    source = Path(__file__).read_text(encoding="utf-8")
    reads = [line for key in keys for line in read_sites(source, key)]
    present = all(key in row for row in rows for key in keys) if rows else True
    return Finding(
        "DT-25.forbidden",
        f"{', '.join(keys)} present in the feed and read by nothing",
        not reads and present,
        f"{len(reads)} read site(s) in this module, key present on every row: {present}",
    )


def dt25(by_target: dict[Target, list[dict[str, Any]]]) -> Finding:
    """DT-25. Distinct ``play_id`` over ``against == False``, MLB 2026.

    The leaderboard's league totals are batting ``n_challenges`` 4,612 plus
    fielding ``n_challenges`` 5,555, so 10,167. Each challenge appears once in
    the challenging team's drawer with ``against`` False and once in the
    opponent's with ``against`` True, so the distinct count over ``against ==
    False`` across the 30 team-seasons is the league total. The batting and
    fielding split is recoverable from the drawer alone through fact 4's
    identity: role == batter iff ``original_isStrike_ump == 1``.

    The tolerance is the SOP's "+/- games between pulls", derived in the
    contract from CIN's measured 2.282 challenges per team-game.
    """
    spec = contract()["dt25"]
    level = str(spec["level"])
    season = int(spec["season"])
    wanted = [target for target in by_target if target.level == level and target.season == season]
    expected_teams = int(contract()["team_index"][level]["count"])

    own: dict[str, int] = {}
    for target in wanted:
        for row in open_rows(by_target[target]):
            if _flag(row, "against"):
                continue
            play_id = str(row.get("play_id") or "")
            if not play_id:
                raise DrawerError(f"{target.label}: a row with against False has no play_id")
            own[play_id] = _flag(row, "original_isStrike_ump")

    total = len(own)
    batting = sum(1 for flag in own.values() if flag == 1)
    fielding = total - batting
    tolerance = math.ceil(
        int(spec["tolerance_days"])
        * int(spec["games_per_day_max"])
        * 2
        * float(spec["challenges_per_team_game"])
    )
    expected = int(spec["expected_total"])
    passed = (
        len(wanted) == expected_teams
        and abs(total - expected) <= tolerance
        and abs(batting - int(spec["expected_batter_side"])) <= tolerance
        and abs(fielding - int(spec["expected_fielding_side"])) <= tolerance
    )
    return Finding(
        "DT-25",
        "drawer completeness: distinct play_id over against == False",
        passed,
        f"{len(wanted)}/{expected_teams} {level} {season} team-seasons, {total} distinct play_id "
        f"({batting} batting + {fielding} fielding) against {expected} "
        f"({spec['expected_batter_side']} + {spec['expected_fielding_side']}), "
        f"tolerance +/- {tolerance}",
    )


def dt25_applies(by_target: dict[Target, list[dict[str, Any]]]) -> bool:
    """True when DT-25's own level-season is among the cached targets."""
    spec = contract()["dt25"]
    return any(
        target.level == str(spec["level"]) and target.season == int(spec["season"])
        for target in by_target
    )


def check_all(by_target: dict[Target, list[dict[str, Any]]]) -> list[Finding]:
    """Every check, over every cached target. Row checks run on the open rows.

    DT-25 itself runs when its own level-season is present. It is left out, and
    never quietly passed, when it is not: a run restricted to AAA has nothing
    to say about the MLB 2026 league total.
    """
    rows: list[dict[str, Any]] = []
    for target_rows in by_target.values():
        rows.extend(open_rows(target_rows))
    findings = [
        check_schema(rows),
        check_edge(rows),
        check_overturn(rows),
        check_role(rows),
        check_no_forbidden_key(rows),
    ]
    if dt25_applies(by_target):
        findings.append(dt25(by_target))
    return findings


# --------------------------------------------------------------------------
# The pull
# --------------------------------------------------------------------------


def fetch(target: Target) -> list[dict[str, Any]]:
    """Fetch one target through the chokepoint and write its JSON file.

    Idempotent twice over: ``absump.http.get`` returns the cached body without
    a request when the URL is already in the manifest, and a target whose JSON
    file is already on disk is not rewritten.
    """
    response = http.get(target.url)
    if response.dry_run:
        return []
    if response.status_code != 200:
        raise DrawerError(f"{target.label}: HTTP {response.status_code}")
    rows = rows_of(response.json())
    if not target.path.exists():
        target.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.path.parent / (target.path.name + ".tmp")
        tmp.write_bytes(response.content)
        os.replace(tmp, target.path)
    return rows


def pull(
    targets: Sequence[Target] | None = None,
    *,
    stream: Any = None,
) -> list[Target]:
    """Pull every target that is not already on disk. Returns what it fetched."""
    out = stream if stream is not None else sys.stdout
    todo = list(targets) if targets is not None else plan()
    fetched: list[Target] = []
    for target in todo:
        if target.path.exists():
            print(f"  cached  {target.label} -> {target.path}", file=out)
            continue
        rows = fetch(target)
        if not target.path.exists():
            print(f"  planned {target.label}: dry run, nothing sent", file=out)
            continue
        dropped = len(rows) - len(open_rows(rows))
        print(
            f"  pulled  {target.label} -> {target.path}: {len(rows)} rows, "
            f"{dropped} past the {OPEN_THROUGH.isoformat()} cutoff",
            file=out,
        )
        fetched.append(target)
    return fetched


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def _print_plan(targets: Sequence[Target], out: Any) -> None:
    for target in targets:
        print(f"  {target.label}\n    {target.url}\n    -> {target.path}", file=out)
    savant = contract()["pull"]["requests"]
    print(
        f"{len(targets)} target(s), {savant} Savant requests when none is cached, "
        f"about 10 minutes at the configured 10 s spacing. Nothing sent.",
        file=out,
    )


def _iter_cached(targets: Sequence[Target]) -> Iterator[Target]:
    for target in targets:
        if target.path.exists():
            yield target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m absump.ingest.savant_drawer",
        description="SOP W4.2: the Savant per-team ABS challenge drawer, 60 team-seasons.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--plan", action="store_true", help="print the 60 targets and exit. No request."
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="run DT-25 and the four W4.2 facts over the cached files.",
    )
    group.add_argument(
        "--pull",
        action="store_true",
        help="fetch every target not already on disk, through absump.http.",
    )
    parser.add_argument(
        "--level",
        choices=LEVEL_ORDER,
        action="append",
        help="restrict to one level. Repeatable. Default: both.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    levels = tuple(args.level) if args.level else LEVEL_ORDER
    targets = plan(levels)

    if args.plan:
        _print_plan(targets, sys.stdout)
        return 0

    if args.pull:
        pull(targets)
        return 0

    cached = list(_iter_cached(targets))
    if not cached:
        print(
            f"0 of {len(targets)} drawer files on disk, so there is nothing to check. "
            f"Run --pull, or import from the staging cache first."
        )
        return 0
    by_target = load_plan(cached)
    findings = check_all(by_target)
    for finding in findings:
        print(finding.line())
    if not dt25_applies(by_target):
        spec = contract()["dt25"]
        print(f"NOTE  DT-25 not run: no {spec['level']} {spec['season']} team-season cached.")
    failed = [finding for finding in findings if not finding.passed]
    print(
        f"{len(findings) - len(failed)}/{len(findings)} assertions pass over "
        f"{len(cached)}/{len(targets)} cached team-seasons."
    )
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
