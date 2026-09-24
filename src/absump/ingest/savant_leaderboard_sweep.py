"""absump.ingest.savant_leaderboard_sweep -- the 28-view leaderboard sweep (SOP W4.3).

W4.3 has no body paragraph of its own. It is two canonical lines -- the step
`leaderboard pull -> W1.7`, and the 60 + 28 + 12 = 100 Savant views of W4.2,
W4.3 and W4.4 scheduled on night D1 behind W6.0's 800-day first batch -- plus
the 28-view sweep of the W2.11 endpoint. So this module holds exactly three
things and borrows everything else:

  1. the enumeration of the 28 views, in config/leaderboard_views.yml, from the
     selector domains W2.11 verified;
  2. the leg the launcher runs, ordered, resumable and offline to build;
  3. the DT-24 refresh over the swept views.

WHAT IT DOES NOT HOLD. The page contract, the parser, the synthetic page and
DT-24 itself belong to W2.11 and live in `absump.ingest.savant_leaderboard` and
`contracts/savant_absdata.yml`. This module imports them. A second parser or a
second copy of a DT-24 clause would be a second specification, and the two would
disagree on the night they mattered. The delay and the daily cap belong to
config/throttle.yml and `absump.http`; the canonical address belongs to the one
constant in `absump.http`. Nothing here restates any of them.

THE ORDER OF THE LEG IS LOAD-BEARING. The three views DT-24 baselines -- MLB
2026 batter, catcher and pitcher -- are swept first. A leg cut short by the
daily cap, by an interruption or by --max-views then still leaves DT-24
refreshable, and the remaining 25 views carry no baseline anyone measured. The
enumeration check asserts the ordering, so a reshuffle that buries the DT-24
views fails the step.

THIS MODULE STARTS NOTHING. A builder does not open the night. `sweep()` is the
only function that can reach the network and it does so only through
`absump.http.get`, one view at a time, in leg order, which is what keeps one
sequential chain per host. The launcher runs it as the second leg of the Savant
chain, after W4.2's 60 and before W4.4's 12. Every body is cached by
`absump.http` under its own address, so a resumed leg costs only the views not
yet on disk and a finished leg re-runs for nothing.

WHAT THE 25 UNMEASURED VIEWS ASSERT. Nothing numeric. Record counts, key counts
and sums were measured for the three DT-24 views and for no other, and a number
nobody measured is not an assertion (SOP section 0.5 rule 4). Over every swept
view this module asserts only what is arithmetic rather than measured:
`n_overturns + n_fails == n_challenges` wherever a record carries all three
keys. An empty view is reported, not failed: serverParams declares
`validSeasons: [2026]` for MLB, so the MLB 2025 views may hold no records at
all, and the SOP counts them among the 28 regardless.

A PAGE ON DISK THAT DOES NOT PARSE IS A FAILURE, including for an unmeasured
view. The step is to sweep 28 views through the W2.11 parser; a view that does
not go through it is a sweep that did not happen. If a view turns out to render
without an `absData` block, that is a contract fact to record in
contracts/savant_absdata.yml with the owner, not a case for this gate to wave
through.

WHAT A 2026 VIEW IS. The page is a whole-season aggregate with no date
parameter, so a 2026 view taken after 2026-09-21 necessarily aggregates days
inside the sealed window, and the phase cutoff cannot be expressed in the
address. The contract records the same fact under
`pull.season_2026_is_a_season_aggregate`. Every 2026 view is marked a sealed-set
input in the leg and in the refresh, so the aggregate is dated rather than
assumed. That is W2.11's recorded fact carried through, not a new decision.

THE SELF-CHECK, which is this step's verify command.

    python -m absump.ingest.savant_leaderboard_sweep --check

runs with no network and no datum on disk, so a clean clone proves it. It:

  1. checks the enumeration against the contract's verified selector domains,
     against the contract's own view count and against W2.11's plan;
  2. builds the leg and asserts its order, its addresses and its resume state;
  3. runs the DT-24 refresh over synthetic pages built from the contract by
     W2.11, which must pass every clause;
  4. mutates the enumeration five ways and the swept pages four ways, and
     requires each corruption to be caught by the right clause. A gutted checker
     passes steps 1 to 3 and fails here;
  5. runs the refresh over whatever the launcher has actually swept onto disk;
  6. proves the whole offline path opened no connection, by refusing
     `absump.http.get` for its duration and by re-reading the manifest.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import sys
from collections.abc import Iterator, Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from absump import http
from absump import paths as lake
from absump.ingest import savant_leaderboard as board

__all__ = [
    "CONFIG_PATH",
    "ConfigError",
    "Finding",
    "View",
    "check_enumeration",
    "config",
    "leg",
    "refresh_dt24",
    "report",
    "swept_pages",
    "views",
]

CONFIG_PATH = lake.REPO_ROOT / "config" / "leaderboard_views.yml"

#: One finding shape for the whole step. W2.11 defines it and DT-24 already
#: reads this way, so the W4.3 clauses print in the same column layout.
Finding = board.Finding

#: The three keys the one arithmetic identity is written over.
IDENTITY_KEYS = ("n_challenges", "n_overturns", "n_fails")


class ConfigError(RuntimeError):
    """config/leaderboard_views.yml is absent, unreadable or malformed."""


class SweepError(RuntimeError):
    """A swept page could not be taken through the W2.11 parser."""


# ------------------------------------------------------------------- the file
_CONFIG_CACHE: dict[str, Any] = {}


def config(path: Path | None = None) -> dict[str, Any]:
    """The parsed enumeration, read once per process."""
    source = path or CONFIG_PATH
    key = str(source)
    if key not in _CONFIG_CACHE:
        if not source.exists():
            raise ConfigError(f"{source} does not exist")
        with source.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if not isinstance(loaded, dict) or "views" not in loaded:
            raise ConfigError(f"{source} is not a mapping carrying a views list")
        _CONFIG_CACHE[key] = loaded
    return _CONFIG_CACHE[key]


@dataclasses.dataclass(frozen=True)
class View:
    """One leaderboard view: a level, a season and a challenge type."""

    order: int
    id: str
    level: str
    season: int
    challenge_type: str
    dt24: bool

    @property
    def url(self) -> str:
        """The canonical address, rendered from the one constant in absump.http."""
        return board.page_url(self.level, self.challenge_type, self.season)

    @property
    def dest(self) -> Path:
        """Where this view's page belongs in the lake."""
        return lake.raw_savant_absdata(self.level, self.challenge_type, self.season)


def views(doc: Mapping[str, Any] | None = None) -> list[View]:
    """The enumerated views, in leg order."""
    doc = doc or config()
    rows: list[View] = []
    for raw in doc["views"]:
        try:
            rows.append(
                View(
                    order=int(raw["order"]),
                    id=str(raw["id"]),
                    level=str(raw["level"]),
                    season=int(raw["season"]),
                    challenge_type=str(raw["challenge_type"]),
                    dt24=bool(raw["dt24"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"malformed view row {raw!r}: {exc}") from exc
    return sorted(rows, key=lambda row: row.order)


def domains(doc: Mapping[str, Any] | None = None) -> dict[str, list[Any]]:
    """The selector domains the enumeration claims to be the cross product of."""
    doc = doc or config()
    declared = doc.get("selector_domains") or {}
    return {key: list(value) for key, value in declared.items()}


def sealed_set_seasons(doc: Mapping[str, Any] | None = None) -> set[int]:
    """The seasons whose views aggregate days inside the sealed window."""
    doc = doc or config()
    return {int(season) for season in doc.get("sealed_set_seasons") or []}


# ------------------------------------------------------------- the enumeration
def _cross_product(declared: Mapping[str, Sequence[Any]]) -> list[tuple[str, int, str]]:
    return [
        (str(level), int(season), str(chal))
        for level in declared.get("ddlLevel", [])
        for season in declared.get("seasons", [])
        for chal in declared.get("ddlChalType", [])
    ]


def _contract_dt24_ids(spec: Mapping[str, Any]) -> set[str]:
    """The ids of the views the contract carries baseline counts for."""
    level = str(spec["server_params"]["level"])
    season = int(spec["server_params"]["season"][0])
    return {f"{level}-{season}-{view}" for view in spec["dt24"]["views"]}


def check_enumeration(
    rows: Sequence[View] | None = None,
    *,
    declared: Mapping[str, Sequence[Any]] | None = None,
    spec: Mapping[str, Any] | None = None,
) -> list[Finding]:
    """Assert the 28 are the 28: one Finding per clause, in order.

    Every number this reads comes from contracts/savant_absdata.yml, which is
    W2.11's record of what the page declared on the pull date. This function
    holds none of its own.
    """
    rows = list(rows if rows is not None else views())
    declared = dict(declared if declared is not None else domains())
    spec = spec or board.contract()
    contract_views = int(spec["pull"]["views"])
    product = _cross_product(declared)
    findings: list[Finding] = []

    findings.append(
        Finding(
            "W4.3.1",
            len(rows) == contract_views == len(product),
            f"enumerated {len(rows)}, contract pull.views {contract_views}, "
            f"selector cross product {len(product)}",
        )
    )

    selectors = spec["selectors"]
    wanted = {
        "ddlLevel": [str(value) for value in selectors["ddlLevel"]],
        "seasons": [int(value) for value in selectors["seasons"]],
        "ddlChalType": [str(value) for value in selectors["ddlChalType"]],
    }
    have = {
        "ddlLevel": [str(value) for value in declared.get("ddlLevel", [])],
        "seasons": [int(value) for value in declared.get("seasons", [])],
        "ddlChalType": [str(value) for value in declared.get("ddlChalType", [])],
    }
    drifted = sorted(key for key in wanted if wanted[key] != have[key])
    findings.append(
        Finding(
            "W4.3.2",
            not drifted,
            f"selector domains against the contract: {drifted if drifted else 'identical'}",
        )
    )

    axes = [(row.level, row.season, row.challenge_type) for row in rows]
    missing = sorted(set(product) - set(axes))
    strangers = sorted(set(axes) - set(product))
    duplicates = sorted({axis for axis in axes if axes.count(axis) > 1})
    planned = {
        (row["level"], int(row["season"]), row["challenge_type"]) for row in board.plan(spec)
    }
    off_plan = sorted(set(axes) ^ planned)
    findings.append(
        Finding(
            "W4.3.3",
            not missing and not strangers and not duplicates and not off_plan,
            f"coverage: missing {missing}, off-domain {strangers}, duplicated {duplicates}, "
            f"differing from the W2.11 plan {off_plan}",
        )
    )

    misnamed = sorted(
        row.id for row in rows if row.id != f"{row.level}-{row.season}-{row.challenge_type}"
    )
    ids = [row.id for row in rows]
    orders = [row.order for row in rows]
    findings.append(
        Finding(
            "W4.3.4",
            not misnamed and len(set(ids)) == len(ids) and orders == list(range(1, len(rows) + 1)),
            f"ids misnamed {misnamed}, distinct ids {len(set(ids))} of {len(ids)}, "
            f"order 1..{len(rows)} contiguous {orders == list(range(1, len(rows) + 1))}",
        )
    )

    scoped = {row.id for row in rows if row.dt24}
    head = {row.id for row in rows[: len(scoped)] if scoped}
    findings.append(
        Finding(
            "W4.3.5",
            scoped == _contract_dt24_ids(spec) and head == scoped,
            f"DT-24 scope {sorted(scoped)}, contract {sorted(_contract_dt24_ids(spec))}, "
            f"first {len(scoped)} of the leg {sorted(head)}",
        )
    )

    urls = [row.url for row in rows]
    dests = [str(row.dest) for row in rows]
    canonical = [
        url for url in urls if "season%5B%5D=" not in url or "year=" in url or "csv=" in url
    ]
    findings.append(
        Finding(
            "W4.3.6",
            len(set(urls)) == len(rows) and len(set(dests)) == len(rows) and not canonical,
            f"distinct addresses {len(set(urls))}, distinct lake paths {len(set(dests))}, "
            f"non-canonical {len(canonical)}",
        )
    )
    return findings


# ---------------------------------------------------------------------- the leg
def _is_cached(url: str) -> bool:
    """True when absump.http already holds this address. Reads, never sends."""
    return url in http._manifest_index() and http._dest_path(url).exists()


def leg(rows: Sequence[View] | None = None, doc: Mapping[str, Any] | None = None) -> list[dict]:
    """The ordered leg the launcher runs, built offline.

    One row per view, in the order they go out: the position, the view, the
    address, where the body lands in the lake, whether it is already on disk,
    and whether the view is a sealed-set input.
    """
    rows = list(rows if rows is not None else views(doc))
    sealed = sealed_set_seasons(doc)
    return [
        {
            "position": row.order,
            "id": row.id,
            "level": row.level,
            "season": row.season,
            "challenge_type": row.challenge_type,
            "dt24": row.dt24,
            "sealed_set_input": row.season in sealed,
            "url": row.url,
            "dest": str(row.dest),
            "cached": _is_cached(row.url),
        }
        for row in rows
    ]


def render_leg(rows: Sequence[dict], stream: Any) -> None:
    """Print the leg for the launcher: one tab-separated line per view."""
    print("position\tid\tstate\tset\turl", file=stream)
    for row in rows:
        state = "on-disk" if row["cached"] else "queued"
        marker = "sealed" if row["sealed_set_input"] else "open"
        print(f"{row['position']}\t{row['id']}\t{state}\t{marker}\t{row['url']}", file=stream)
    queued = sum(1 for row in rows if not row["cached"])
    print(
        f"{len(rows)} views, {queued} queued, {len(rows) - queued} already on disk, "
        "spacing and daily cap from config/throttle.yml",
        file=stream,
    )


# -------------------------------------------------------------- the swept pages
def cached_page(row: View) -> board.ParsedPage | None:
    """One swept view off the disk, through the W2.11 parser, or None.

    The two readers below belong to W2.11 and read `data/raw` and the manifest
    that `absump.http` writes. They never open a connection. A second cache
    reader here would be a second policy.
    """
    body = board._cached_body(row.url)
    if body is None:
        return None
    try:
        return board.parse_page(
            body, view=row.challenge_type, pull_date=board._cached_pull_date(row.url)
        )
    except board.ParseError as exc:
        raise SweepError(f"{row.id} is on disk and does not parse: {exc}") from exc


def swept_pages(
    rows: Sequence[View] | None = None,
) -> tuple[dict[str, board.ParsedPage], list[str]]:
    """Every enumerated view already on disk, keyed by view id, plus the failures."""
    rows = list(rows if rows is not None else views())
    found: dict[str, board.ParsedPage] = {}
    broken: list[str] = []
    for row in rows:
        try:
            page = cached_page(row)
        except SweepError as exc:
            broken.append(str(exc))
            continue
        if page is not None:
            found[row.id] = page
    return found, broken


def sweep_pull_date(pages: Mapping[str, board.ParsedPage]) -> date | None:
    """The latest day any swept page was taken, out of the manifest."""
    stamps = sorted({page.pull_date for page in pages.values() if page.pull_date})
    return stamps[-1] if stamps else None


# ------------------------------------------------------------ the DT-24 refresh
def _identity_counts(page: board.ParsedPage) -> tuple[int, int, int]:
    """Records checked, records broken, records skipped for want of the keys."""
    checked = broken = skipped = 0
    for record in page.abs_data:
        values = []
        for key in IDENTITY_KEYS:
            value = record.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                values = []
                break
            values.append(int(value))
        if len(values) != len(IDENTITY_KEYS):
            skipped += 1
            continue
        checked += 1
        challenges, overturns, fails = values
        if overturns + fails != challenges:
            broken += 1
    return checked, broken, skipped


def refresh_dt24(
    pages: Mapping[str, board.ParsedPage],
    *,
    rows: Sequence[View] | None = None,
    spec: Mapping[str, Any] | None = None,
    pull_date: date | None = None,
    broken: Sequence[str] = (),
    sealed: set[int] | None = None,
) -> list[Finding]:
    """Re-run DT-24 over the swept views. W2.11 owns the assertion; this refreshes it.

    The count clauses are DT-24's and are run by W2.11's own checker over the
    three views the contract baselines. The clauses this step adds are about the
    sweep rather than about the numbers: that every swept page parsed, that the
    DT-24 scope is complete whenever anything was swept, and that the one
    arithmetic identity holds over every swept view including the 25 nobody
    measured.
    """
    rows = list(rows if rows is not None else views())
    spec = spec or board.contract()
    by_id = {row.id: row for row in rows}
    findings: list[Finding] = []

    unknown = sorted(set(pages) - set(by_id))
    findings.append(
        Finding(
            "W4.3.9",
            not broken and not unknown,
            f"every page on disk parsed and is an enumerated view: {len(pages)} parsed, "
            f"{len(broken)} refused, {len(unknown)} outside the enumeration"
            + ("" if not broken else f" -- {list(broken)}")
            + ("" if not unknown else f" -- {unknown}"),
        )
    )

    if not pages:
        findings.append(Finding("W4.3.8", True, "no view on disk; the leg has not run here"))
        return findings

    scope = [row for row in rows if row.dt24]
    present = {row.challenge_type: pages[row.id] for row in scope if row.id in pages}
    absent = sorted(row.id for row in scope if row.id not in pages)
    findings.append(
        Finding(
            "W4.3.8",
            not absent,
            f"swept {len(pages)} of {len(rows)} views; DT-24 scope "
            f"{len(present)} of {len(scope)}, absent {absent}",
        )
    )

    # W4.3.10 is about the direction that matters. A 2026 view taken after the
    # open cutoff aggregates sealed days, so leaving it unmarked is the failure;
    # marking a view the config calls sealed is conservative and is not.
    sealed = sealed_set_seasons() if sealed is None else set(sealed)
    cutoff = lake.LAST_OPEN_DATE
    marked = sorted(
        view_id for view_id in pages if view_id in by_id and by_id[view_id].season in sealed
    )
    unmarked = sorted(
        view_id
        for view_id, page in pages.items()
        if view_id in by_id
        and by_id[view_id].season == cutoff.year
        and by_id[view_id].season not in sealed
        and page.pull_date is not None
        and page.pull_date > cutoff
    )
    findings.append(
        Finding(
            "W4.3.10",
            not unmarked,
            f"{len(marked)} swept views marked sealed-set inputs; taken after "
            f"{cutoff.isoformat()} and left unmarked: {unmarked}",
        )
    )

    for view_id in sorted(pages):
        checked, wrong, skipped = _identity_counts(pages[view_id])
        findings.append(
            Finding(
                "W4.3.7",
                wrong == 0,
                f"{view_id} n_overturns + n_fails == n_challenges: {checked} records checked, "
                f"{wrong} broken, {skipped} without the three keys",
            )
        )

    if present:
        findings.extend(board.check_dt24(present, spec=spec, pull_date=pull_date))
    return findings


def report(stream: Any, *, rows: Sequence[View] | None = None) -> list[Finding]:
    """The refresh over whatever the launcher has swept onto disk."""
    rows = list(rows if rows is not None else views())
    pages, broken = swept_pages(rows)
    observed = sweep_pull_date(pages)
    findings = refresh_dt24(pages, rows=rows, pull_date=observed, broken=broken)
    print(
        f"swept views on disk: {len(pages)} of {len(rows)}, pull date {observed or 'unknown'}",
        file=stream,
    )
    for finding in findings:
        print("  " + finding.line(), file=stream)
    return findings


# --------------------------------------------------------------------- the pull
class SweepPages(dict):
    """The pages a sweep captured, carrying the views it could not capture.

    A plain dict of view id to page, so every existing reader is unchanged, plus
    `refused`, the list of views that were refused or did not parse. The 03:13
    run of 2026-09-24 lost all 28 views to a `leagueData` shape change and still
    exited 0, because the refusals were printed and then dropped on the floor.
    They are carried now, and `main` exits non-zero when the list is not empty.
    """

    refused: list[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.refused = []


def sweep(
    rows: Sequence[View] | None = None,
    *,
    max_views: int | None = None,
    stream: Any = sys.stdout,
) -> SweepPages:
    """Run the leg. The launcher calls this; a builder does not.

    One view at a time, in leg order, each through `absump.http.get`, which owns
    the interval, the daily cap, the cache and the manifest. A view already on
    disk costs nothing and does not count against --max-views.

    A view that fails is recorded and the leg carries on, because 25 of the 28
    carry no baseline and one dead view must not cost the other 27 or the leg
    that follows this one. A spent daily cap is the exception: it stops the leg
    where it stands, which is the cap doing its job rather than an error to work
    around.
    """
    rows = list(rows if rows is not None else views())
    sealed = sealed_set_seasons()
    pages = SweepPages()
    refused: list[str] = pages.refused
    sent = 0
    planned = 0
    for row in rows:
        if max_views is not None and sent >= max_views and not _is_cached(row.url):
            print(
                f"stopping at {sent} views, as asked; {row.id} and the rest stay queued",
                file=stream,
            )
            break
        try:
            response = http.get(row.url)
        except http.BudgetExceeded as exc:
            print(
                f"daily cap spent at {row.id}; the rest of the leg stays queued: {exc}", file=stream
            )
            break
        except http.HttpError as exc:
            refused.append(f"{row.id}: {exc}")
            print(f"{row.order:2d}/{len(rows)} {row.id:24s} refused: {exc}", file=stream)
            continue
        if response.dry_run:
            planned += 1
            continue
        if not response.from_cache:
            sent += 1
        try:
            page = board.parse_page(
                response.text, view=row.challenge_type, pull_date=board._cached_pull_date(row.url)
            )
        except board.ParseError as exc:
            refused.append(f"{row.id}: {exc}")
            print(f"{row.order:2d}/{len(rows)} {row.id:24s} does not parse: {exc}", file=stream)
            continue
        pages[row.id] = page
        marker = " sealed-set input" if row.season in sealed else ""
        source = "cache" if response.from_cache else "wire"
        print(
            f"{row.order:2d}/{len(rows)} {row.id:24s} {len(page.abs_data):5d} records "
            f"from {source}{marker}",
            file=stream,
        )
    if planned:
        print(f"{planned} views planned, none sent", file=stream)
    else:
        print(
            f"{len(pages)} views parsed, {sent} taken off the wire, {len(refused)} refused",
            file=stream,
        )
    for note in refused:
        print(f"  refused {note}", file=stream)
    return pages


# ---------------------------------------------------------------- the self-check
@contextlib.contextmanager
def _offline() -> Iterator[None]:
    """Refuse the chokepoint for the duration, so an offline claim is proved.

    The self-check says it opens no connection. This makes that a test rather
    than a promise: `absump.http.get` raises for the whole offline path, and the
    manifest is re-read afterwards to show no row was added.
    """
    original = http.get

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the W4.3 offline path tried to open a connection")

    http.get = refuse  # type: ignore[assignment]
    try:
        yield
    finally:
        http.get = original  # type: ignore[assignment]


def _shape_page(records: Sequence[tuple[int, int]]) -> board.ParsedPage:
    """A page for a view nobody measured: arithmetic only, no endpoint number.

    It carries no record count, key count or sum that claims to be the page's.
    It exists to exercise the one identity clause, which is arithmetic.
    """
    rows = [
        {
            "year": 2026,
            "player_name": f"Shape {index:02d}",
            "id": 900000 + index,
            "n_challenges": challenges,
            "n_overturns": overturns,
            "n_fails": challenges - overturns,
        }
        for index, (challenges, overturns) in enumerate(records)
    ]
    return board.ParsedPage(
        view="shape", abs_data=[dict(row) for row in rows], server_params={}, league_data={}
    )


def _synthetic_sweep(spec: Mapping[str, Any]) -> dict[str, board.ParsedPage]:
    """A swept set keyed by view id: the three DT-24 views plus one unmeasured view."""
    level = str(spec["server_params"]["level"])
    season = int(spec["server_params"]["season"][0])
    pages = {f"{level}-{season}-{view}": page for view, page in board.synthetic_pages(spec).items()}
    pages[f"{level}-{season}-league"] = _shape_page([(10, 6), (4, 1), (0, 0)])
    return pages


def _drop_record(
    pages: Mapping[str, board.ParsedPage], view_id: str
) -> dict[str, board.ParsedPage]:
    out = dict(pages)
    page = out[view_id]
    out[view_id] = dataclasses.replace(page, abs_data=list(page.abs_data[1:]))
    return out


def _break_identity(
    pages: Mapping[str, board.ParsedPage], view_id: str
) -> dict[str, board.ParsedPage]:
    out = dict(pages)
    page = out[view_id]
    records = [dict(record) for record in page.abs_data]
    records[0]["n_fails"] = int(records[0].get("n_fails", 0)) + 1
    out[view_id] = dataclasses.replace(page, abs_data=records)
    return out


def _dated(pages: Mapping[str, board.ParsedPage], when: date) -> dict[str, board.ParsedPage]:
    return {key: dataclasses.replace(page, pull_date=when) for key, page in pages.items()}


def _without(pages: Mapping[str, board.ParsedPage], view_id: str) -> dict[str, board.ParsedPage]:
    return {key: value for key, value in pages.items() if key != view_id}


def _renumbered(rows: Sequence[View]) -> list[View]:
    return [dataclasses.replace(row, order=index) for index, row in enumerate(rows, start=1)]


def self_check(stream: Any) -> int:
    """The verify command. No network, no datum on disk, deterministic output."""
    spec = board.contract()
    rows = views()
    doc = config()
    failures = 0
    checks = 0

    def emit(text: str = "") -> None:
        print(text, file=stream)

    def run(findings: Sequence[Finding], indent: str = "  ") -> None:
        nonlocal failures, checks
        for finding in findings:
            checks += 1
            failures += 0 if finding.passed else 1
            emit(indent + finding.line())

    manifest_rows_before = len(http._manifest_index())

    emit("W4.3 Savant ABS leaderboard sweep, 28 views")
    emit(f"enumeration   {CONFIG_PATH.relative_to(lake.REPO_ROOT)}")
    emit(f"contract      {board.CONTRACT_PATH.relative_to(lake.REPO_ROOT)}")
    emit("parser        absump.ingest.savant_leaderboard (W2.11), assertion DT-24")
    emit(
        f"leg           {doc['sweep']['chain']} chain, position {doc['sweep']['leg_position']}, "
        f"after {doc['sweep']['leg_after']}, before {doc['sweep']['leg_before']}"
    )
    emit()

    with _offline():
        emit("enumeration")
        run(check_enumeration(rows, spec=spec))
        emit()

        emit("the leg")
        built = leg(rows)
        head = [row["id"] for row in built[:3]]
        checks += 1
        ordered = [row["position"] for row in built] == list(range(1, len(built) + 1))
        dt24_first = all(row["dt24"] for row in built[:3])
        if ordered and dt24_first:
            emit(f"  PASS W4.3.11 leg of {len(built)}, DT-24 views first: {head}")
        else:
            failures += 1
            emit(f"  FAIL W4.3.11 leg order {ordered}, DT-24 views first {dt24_first}, head {head}")
        checks += 1
        sealed = [row["id"] for row in built if row["sealed_set_input"]]
        expected_sealed = [row.id for row in rows if row.season in sealed_set_seasons(doc)]
        if sealed == expected_sealed:
            emit(f"  PASS W4.3.12 {len(sealed)} views marked sealed-set inputs")
        else:
            failures += 1
            emit(f"  FAIL W4.3.12 sealed-set marks {sealed}, expected {expected_sealed}")
        emit()

        emit("DT-24 refresh over synthetic pages, every clause must pass")
        pages = _synthetic_sweep(spec)
        run(refresh_dt24(pages, rows=rows, spec=spec, pull_date=board.baseline_pull_date(spec)))
        emit()

        emit("mutated enumeration, each corruption must be caught by its clause")
        level = str(spec["server_params"]["level"])
        season = int(spec["server_params"]["season"][0])
        enumeration_mutations = (
            ("drop a view", "W4.3.1", _renumbered(rows[:-1]), None),
            ("duplicate a view", "W4.3.3", _renumbered([*rows, rows[-1]]), None),
            (
                "a challenge type off the verified domain",
                "W4.3.3",
                [
                    dataclasses.replace(
                        rows[-1],
                        challenge_type="umpire",
                        id=f"{rows[-1].level}-{rows[-1].season}-umpire",
                    ),
                    *rows[:-1],
                ],
                None,
            ),
            (
                "bury a DT-24 view",
                "W4.3.5",
                _renumbered(list(rows[3:]) + list(rows[:3])),
                None,
            ),
            (
                "flip a dt24 flag",
                "W4.3.5",
                [
                    dataclasses.replace(row, dt24=not row.dt24) if row.order == 4 else row
                    for row in rows
                ],
                None,
            ),
            (
                "a selector domain that drifted from the contract",
                "W4.3.2",
                rows,
                {**domains(doc), "ddlLevel": ["mlb"]},
            ),
        )
        for label, assertion, mutated, declared in enumeration_mutations:
            checks += 1
            caught = {
                finding.assertion
                for finding in check_enumeration(mutated, declared=declared, spec=spec)
                if not finding.passed
            }
            ok = assertion in caught
            failures += 0 if ok else 1
            emit(f"  {'PASS' if ok else 'FAIL':4s} {assertion} {label}, caught {sorted(caught)}")
        emit()

        emit("mutated sweep, each corruption must be caught by its clause")
        sweep_mutations = (
            (
                "a DT-24 view missing from the sweep",
                "W4.3.8",
                _without(pages, f"{level}-{season}-catcher"),
                False,
            ),
            (
                "break the identity in an unmeasured view",
                "W4.3.7",
                _break_identity(pages, f"{level}-{season}-league"),
                False,
            ),
            (
                "break the identity in a DT-24 view",
                "DT-24.3",
                _break_identity(pages, f"{level}-{season}-batter"),
                False,
            ),
            (
                "drop a record from a DT-24 view",
                "DT-24.1",
                _drop_record(pages, f"{level}-{season}-batter"),
                False,
            ),
            (
                "a view taken after the cutoff and left unmarked",
                "W4.3.10",
                _dated(pages, lake.LAST_OPEN_DATE + timedelta(days=1)),
                True,
            ),
        )
        for label, assertion, mutated_pages, unsealed in sweep_mutations:
            checks += 1
            caught = {
                finding.assertion
                for finding in refresh_dt24(
                    mutated_pages,
                    rows=rows,
                    spec=spec,
                    pull_date=board.baseline_pull_date(spec),
                    sealed=set() if unsealed else None,
                )
                if not finding.passed
            }
            ok = assertion in caught
            failures += 0 if ok else 1
            emit(f"  {'PASS' if ok else 'FAIL':4s} {assertion} {label}, caught {sorted(caught)}")
        emit()

        checks += 1
        caught = {
            finding.assertion
            for finding in refresh_dt24(
                pages, rows=rows, spec=spec, broken=["a page on disk that does not parse"]
            )
            if not finding.passed
        }
        ok = "W4.3.9" in caught
        failures += 0 if ok else 1
        emit(
            f"  {'PASS' if ok else 'FAIL':4s} W4.3.9 a page that does not parse, "
            f"caught {sorted(caught)}"
        )
        emit()

        emit("the sweep on disk")
        # report() prints its own findings, so they are counted here and not
        # emitted a second time.
        for finding in report(stream, rows=rows):
            checks += 1
            failures += 0 if finding.passed else 1
        emit()

    checks += 1
    manifest_rows_after = len(http._manifest_index())
    if manifest_rows_after == manifest_rows_before:
        emit(f"  PASS W4.3.13 offline: manifest unchanged at {manifest_rows_after} rows")
    else:
        failures += 1
        emit(
            f"  FAIL W4.3.13 the manifest grew from {manifest_rows_before} to "
            f"{manifest_rows_after} rows"
        )
    emit()

    emit(f"W4.3: {checks} checks, {checks - failures} passed, {failures} failed")
    return 1 if failures else 0


# ---------------------------------------------------------------- command line
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="absump.ingest.savant_leaderboard_sweep",
        description="The 28-view Savant ABS leaderboard sweep and its DT-24 refresh (SOP W4.3).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="run the W4.3 gate; the verify command")
    group.add_argument("--leg", action="store_true", help="print the ordered leg for the launcher")
    group.add_argument(
        "--dry-run", action="store_true", help="print the plan through absump.http and send nothing"
    )
    group.add_argument("--refresh", action="store_true", help="refresh DT-24 over the swept views")
    group.add_argument(
        "--sweep",
        action="store_true",
        help="run the leg; the launcher does this, a builder does not",
    )
    parser.add_argument(
        "--max-views", type=int, default=None, help="stop the sweep after this many new views"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.check:
        return self_check(sys.stdout)

    if args.leg:
        render_leg(leg(), sys.stdout)
        return 0

    if args.dry_run:
        import os

        previous = os.environ.get("ABSUMP_DRY_RUN")
        os.environ["ABSUMP_DRY_RUN"] = "1"
        try:
            sweep(max_views=args.max_views)
        finally:
            if previous is None:
                os.environ.pop("ABSUMP_DRY_RUN", None)
            else:
                os.environ["ABSUMP_DRY_RUN"] = previous
        return 0

    if args.refresh:
        findings = report(sys.stdout)
        return 1 if any(not finding.passed for finding in findings) else 0

    pages = sweep(max_views=args.max_views)
    findings = refresh_dt24(pages, pull_date=sweep_pull_date(pages))
    for finding in findings:
        print("  " + finding.line())
    refused = list(getattr(pages, "refused", []))
    expected = len(views())
    if refused:
        print(
            f"{len(refused)} of {expected} views did not come back: " + "; ".join(refused),
            file=sys.stderr,
        )
        return 1
    if not pages:
        print("the sweep captured no view at all", file=sys.stderr)
        return 1
    return 1 if any(not finding.passed for finding in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
