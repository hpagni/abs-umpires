"""absump.ledger: the request ledger's growth, attributed (W1.15 and W4.3.13).

Every test runs against a temporary cache and a temporary data root, so none of
them reads the real ledger or a puller's mutex, and none opens a connection.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from absump import http, ledger
from absump.ingest import pull_statcast

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = datetime.now(UTC).date()
STATSAPI = "statsapi.mlb.com"
SAVANT = "baseballsavant.mlb.com"


def _row(host: str, url: str, day: str | None = None) -> dict[str, str]:
    stamp = f"{day or TODAY.isoformat()}T10:00:00Z"
    return {
        "fetched_at_utc": stamp,
        "host": host,
        "url": url,
        "http_status": "200",
        "wire_bytes": "1",
        "disk_bytes": "1",
        "sha256": "0" * 64,
        "attempt": "1",
        "elapsed_s": "0.1",
        "dest_path": "x.zst",
    }


def _csv(rows: list[dict[str, str]], *, header: bool) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(http._MANIFEST_COLUMNS))
    if header:
        writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


@pytest.fixture
def lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache = tmp_path / "raw"
    cache.mkdir()
    monkeypatch.setattr(http, "_CACHE_DIR", cache)
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path))
    (tmp_path / "tmp").mkdir()
    return tmp_path


def _append(lake: Path, rows: list[dict[str, str]]) -> None:
    manifest = lake / "raw" / "_manifest.csv"
    header = not manifest.exists()
    with manifest.open("a", encoding="utf-8", newline="") as handle:
        handle.write(_csv(rows, header=header))


def _hold(lake: Path, host: str) -> None:
    (lake / "tmp" / ledger.PULLER_LOCKS[host]).mkdir()


def test_puller_locks_name_the_pullers_own_mutexes() -> None:
    assert ledger.PULLER_LOCKS[SAVANT] == pull_statcast.LOCK_NAME
    assert ledger.PULLER_LOCKS[STATSAPI] == pull_statcast.STATSAPI_LOCK_NAME
    script = (REPO_ROOT / "ops" / "night_statsapi.sh").read_text(encoding="utf-8")
    assert f"data/tmp/{ledger.PULLER_LOCKS[STATSAPI]}" in script


def test_mark_and_since_on_a_quiet_ledger(lake: Path) -> None:
    _append(lake, [_row(STATSAPI, "https://statsapi.mlb.com/a")])
    growth = ledger.since(ledger.mark())
    assert growth.quiet and growth.passed
    assert growth.lines() == ["manifest unchanged at 1 rows, no budget count moved"]


def test_since_attributes_rows_a_running_puller_added(lake: Path) -> None:
    _append(lake, [_row(STATSAPI, "https://statsapi.mlb.com/a")])
    _hold(lake, STATSAPI)
    _hold(lake, SAVANT)
    start = ledger.mark()
    _append(
        lake,
        [
            _row(STATSAPI, "https://statsapi.mlb.com/b"),
            _row(SAVANT, "https://baseballsavant.mlb.com/c"),
        ],
    )
    growth = ledger.since(start, own_urls={"https://baseballsavant.mlb.com/own"})
    assert growth.passed and not growth.quiet
    assert len(growth.added) == 2
    assert (growth.rows_before, growth.rows_after) == (1, 3)
    assert "none of the check's own 1 addresses" in growth.lines()[-1]


def test_since_ignores_a_half_written_last_line(lake: Path) -> None:
    _append(lake, [_row(STATSAPI, "https://statsapi.mlb.com/a")])
    start = ledger.mark()
    with (lake / "raw" / "_manifest.csv").open("a", encoding="utf-8") as handle:
        handle.write("2026-01-01T00:00:00Z,www.example.org,https://www.exa")
    assert ledger.since(start).quiet


def test_since_charges_a_row_the_check_itself_added(lake: Path) -> None:
    _hold(lake, SAVANT)
    _append(lake, [_row(STATSAPI, "https://statsapi.mlb.com/a")])
    start = ledger.mark()
    own = "https://baseballsavant.mlb.com/leaderboard/own"
    _append(lake, [_row(SAVANT, own)])
    growth = ledger.since(start, own_urls={own})
    assert not growth.passed
    assert any("the check's addresses" in line for line in growth.lines())


def test_since_charges_a_rewritten_manifest(lake: Path) -> None:
    _append(lake, [_row(STATSAPI, "https://statsapi.mlb.com/a")])
    start = ledger.mark()
    manifest = lake / "raw" / "_manifest.csv"
    manifest.write_text(_csv([_row(STATSAPI, "https://statsapi.mlb.com/z")], header=True))
    growth = ledger.since(start)
    assert not growth.prefix_intact and not growth.passed


def test_attribute_rows_names_each_test_a_row_fails() -> None:
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    rows = [
        _row("www.retrosheet.org", "https://www.retrosheet.org/x"),
        _row(SAVANT, "https://baseballsavant.mlb.com/y"),
        _row(STATSAPI, "https://statsapi.mlb.com/z", day=yesterday),
        _row(STATSAPI, "https://statsapi.mlb.com/own"),
        _row(STATSAPI, "https://statsapi.mlb.com/fine"),
    ]
    charged = ledger.attribute_rows(
        rows,
        held=[STATSAPI],
        days=[TODAY.isoformat()],
        own_urls=["https://statsapi.mlb.com/own"],
    )
    assert len(charged) == 4
    assert "no puller's host" in charged[0]
    assert ".savant_night.lock was not held" in charged[1]
    assert "not a UTC day the check spanned" in charged[2]
    assert "the check's addresses" in charged[3]


def test_attribute_budget_charges_a_host_no_puller_explains() -> None:
    day = TODAY.isoformat()
    moved, charged = ledger.attribute_budget(
        (day, {STATSAPI: 5, "www.retrosheet.org": 1}),
        (day, {STATSAPI: 7, "www.retrosheet.org": 2}),
        held=[STATSAPI],
    )
    assert moved == {STATSAPI: (5, 7), "www.retrosheet.org": (1, 2)}
    assert charged == [
        "budget: www.retrosheet.org moved 1 -> 2 and no running puller holds its mutex"
    ]


def test_held_mutexes_reads_the_lock_directories(lake: Path) -> None:
    assert ledger.held_mutexes() == ()
    _hold(lake, SAVANT)
    assert ledger.held_mutexes() == (SAVANT,)


def test_main_mark_then_since(
    lake: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _append(lake, [_row(STATSAPI, "https://statsapi.mlb.com/a")])
    budget = lake / "raw" / "_budget.json"
    budget.write_text(json.dumps({"utc_date": TODAY.isoformat(), "used": {STATSAPI: 1}}))
    target = tmp_path / "mark.json"
    assert ledger.main(["mark", str(target)]) == 0
    budget.write_text(json.dumps({"utc_date": TODAY.isoformat(), "used": {STATSAPI: 2}}))
    assert ledger.main(["since", str(target)]) == 1
    assert "no running puller holds its mutex" in capsys.readouterr().out
