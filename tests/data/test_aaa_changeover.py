"""DT-29, the AAA 2024 challenge-format changeover. SOP section 9, the data tests.

    DT-29  AAA 2024 challenge-format changeover: the binary-search date is
           recorded; before it, every Tue/Wed/Thu game has no `absChallenges`
           key and 0 MJ reviews; on and after it, the key is present.
           Gate: 100% on the 40 games the search touches, and the DiD frame
           contains no date on or after it.

The date is D-57's, written by ``absump.ingest.aaa_scan`` into the rule-version
table ``out/tables/aaa_format.csv``, which is where W3.20 reads it. Nothing here
carries the date as a literal: every clause reads it from that table.

Two kinds of test, the split ``tests/data/test_join.py`` uses. TABLE tests read
the committed tables under ``out/tables/`` and run in a clean clone. FEED tests
recompute the search from the AAA feeds in ``data/raw/``, which is gitignored,
so they skip and say so when the lake is absent. Neither requests anything: the
search runs with pulling switched off and fails if a probe's feed is missing.

The DiD-frame clause belongs to W3.20, which has not been built. It skips while
W3.20 is unregistered and fails once W3.20 is registered, until W3.20 points it
at its frame, so the clause cannot be forgotten.

    uv run --locked pytest tests/data/test_aaa_changeover.py -q -k dt29
"""

from __future__ import annotations

import csv
import datetime as dt
from functools import cache
from typing import Any

import pytest

from absump import paths
from absump.ingest import aaa_scan

TUE_THU = aaa_scan.TUE_THU


def _read(path: Any) -> list[dict[str, str]]:
    if not path.exists():
        pytest.fail(f"{path} is absent; run `python -m absump.ingest.aaa_scan`")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _changeover_row() -> dict[str, str]:
    rows = [
        r
        for r in _read(aaa_scan.FORMAT_FILE)
        if r["level"] == "aaa"
        and r["season"] == str(aaa_scan.D57_SEASON)
        and r["source"].startswith(aaa_scan.D57_SOURCE_TAG)
    ]
    assert len(rows) == 1, f"{len(rows)} D-57 rows in aaa_format.csv, want exactly 1"
    return rows[0]


def _changeover_date() -> dt.date:
    return dt.date.fromisoformat(_changeover_row()["changeover_date"])


def _tue_thu_2024() -> list[dict[str, str]]:
    return [
        r
        for r in _read(aaa_scan.SCAN_FILE)
        if r["season"] == str(aaa_scan.D57_SEASON) and r["weekday"] in TUE_THU
    ]


# ---------------------------------------------------------------------------
# TABLE tests: the committed tables, a clean clone
# ---------------------------------------------------------------------------


def test_dt29_the_changeover_date_is_recorded() -> None:
    row = _changeover_row()
    day = _changeover_date()
    assert row["rule_version"] == aaa_scan.D57_RULE_VERSION
    assert aaa_scan.weekday_of(day) in TUE_THU, f"{day} is not a Tue/Wed/Thu"
    d57 = aaa_scan.changeover_rows()["D-57"]
    assert d57["status"] == "closed", f"D-57 is {d57['status']}: {d57['result']}"
    assert d57["first_key_date"] == day.isoformat()
    assert dt.date.fromisoformat(d57["last_no_key_date"]) < day
    assert day.isoformat() in d57["result"]
    assert int(d57["n_scanned"]) <= int(d57["n_final_scheduled"])


def test_dt29_before_the_date_no_key_and_no_mj_reviews() -> None:
    day = _changeover_date()
    before = [r for r in _tue_thu_2024() if dt.date.fromisoformat(r["official_date"]) < day]
    assert before, "no Tue/Wed/Thu 2024 game before the date is in the scan table"
    bad = [
        f"{r['game_pk']} {r['official_date']} key={r['has_abs_challenges']} "
        f"mj={r['n_mj_event']}+{r['n_mj_play']}"
        for r in before
        if r["has_abs_challenges"] != "FALSE" or r["n_mj_event"] != "0" or r["n_mj_play"] != "0"
    ]
    assert not bad, f"{len(bad)} of {len(before)} Tue/Wed/Thu games before {day}: {bad[:10]}"


def test_dt29_on_and_after_the_date_the_key_is_present() -> None:
    day = _changeover_date()
    after = [r for r in _tue_thu_2024() if dt.date.fromisoformat(r["official_date"]) >= day]
    assert after, "no Tue/Wed/Thu 2024 game on or after the date is in the scan table"
    bad = [
        f"{r['game_pk']} {r['official_date']}" for r in after if r["has_abs_challenges"] != "TRUE"
    ]
    assert not bad, f"{len(bad)} of {len(after)} Tue/Wed/Thu games on or after {day}: {bad[:10]}"


def test_dt29_the_did_frame_holds_no_date_on_or_after_the_changeover() -> None:
    registry = (paths.REPO_ROOT / "quality" / "steps.yml").read_text(encoding="utf-8")
    if "- id: W3.20\n" not in registry:
        pytest.skip(
            "W3.20 is not built, so there is no DiD frame yet. When W3.20 registers, this "
            "clause fails until it reads W3.20's frame and asserts no date on or after "
            "the aaa_format.csv changeover date"
        )
    pytest.fail(
        "W3.20 is registered: point this clause at its DiD frame and assert that every "
        f"within-week contrast date is strictly before {_changeover_date()}"
    )


# ---------------------------------------------------------------------------
# FEED tests: the search recomputed from the lake, offline
# ---------------------------------------------------------------------------


@cache
def _offline_search() -> tuple[aaa_scan.Search, dict[int, aaa_scan.ScanRow], list[Any]]:
    try:
        finals = aaa_scan.final_games(aaa_scan.D57_SEASON)
    except FileNotFoundError as exc:
        pytest.skip(f"the AAA 2024 schedule is not in data/raw: {exc}")
    rows = aaa_scan.scan_lake(aaa_scan.D57_SEASON, finals)
    if not rows:
        pytest.skip("no AAA 2024 feed is in data/raw; the lake is gitignored")
    reader = aaa_scan.Puller(rows, allow_pull=False, max_requests=0)
    try:
        search = aaa_scan.search_changeover(finals, rows, reader)
    except aaa_scan.MissingFeed as exc:
        pytest.fail(f"a feed the search reads is not on disk: {exc}")
    return search, rows, finals


def test_dt29_the_search_reproduces_the_recorded_date_from_the_feeds() -> None:
    search, _rows, finals = _offline_search()
    assert not search.problems, search.problems
    assert search.first_key_date == _changeover_date()
    # a tight bracket: the last keyless date is the Tue/Wed/Thu date just before
    dates = sorted(
        {g.official_date for g in finals if aaa_scan.weekday_of(g.official_date) in TUE_THU}
    )
    assert dates[dates.index(search.first_key_date) - 1] == search.last_no_key_date


def test_dt29_every_game_the_search_touches_holds_the_pattern() -> None:
    search, rows, finals = _offline_search()
    touched = [rows[pk] for pk in sorted(search.touched)]
    assert 30 <= len(touched) <= 50, f"the search touched {len(touched)} games, SOP about 40"
    breaks = aaa_scan.pattern_breaks(touched, _changeover_date())
    assert not breaks, f"{len(breaks)} of {len(touched)} touched games break DT-29: {breaks[:10]}"
    # both boundary days are read in full, every Final game on them
    for day in (search.last_no_key_date, search.first_key_date):
        scheduled = {g.game_pk for g in finals if g.official_date == day}
        assert scheduled and scheduled <= search.touched, f"{day} is not read in full"


def test_dt29_the_tables_match_a_rebuild_from_the_feeds() -> None:
    _offline_search()
    result = aaa_scan.run(allow_pull=False, max_requests=0)
    assert not result.puller.pulled
    drift = [
        str(path.relative_to(paths.REPO_ROOT))
        for path, text in result.texts.items()
        if path.read_text(encoding="utf-8") != text
    ]
    assert not drift, f"out of date against the feeds on disk: {drift}"
