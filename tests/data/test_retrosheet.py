"""W2.12 Retrosheet and DT-27: the eleven plays archives, the header, the notice, RE288.

SOP W2.12: per-season ``{YEAR}plays.zip`` for 2015-2025, 11 archives; "the first
job after unzipping is to assert the header is identical across all eleven
years and write it to a committed fixture"; the attribution string from
``notice.txt`` goes verbatim in ATTRIBUTION.md.

SOP section 6.3, DT-27, quoted (the SOP prints the year range with an en dash):

    | DT-27 | Retrosheet header identical 2015-2025; RE288 built from it
    reproduces `delta_run_exp` | ≤0.01 runs per base-out-count cell |

The first clause is asserted here against the files on disk. The second is
``absump.verify.re288_crosscheck``, which writes out/tables/re288_crosscheck.csv;
the tests below hold that table to the quoted bar cell by cell and pin the
verdict it records, so the verdict cannot change without this file changing.

These tests were ``data/raw/retrosheet/w212_verify.py``, the W2.12 builder's
verify, written under data/ because that builder could write nowhere else. The
assertions are the same, R1 to R7. They read what is on disk and the manifest
and send nothing. The pull is never repeated: it ran on 2026-09-30, twelve
calls, and every URL is in data/raw/_manifest.csv. The data-bound tests skip
in a clean clone, where data/ is absent; the W2.12 registration needs the raw
plays directory, so ``make prove`` reads MISSING there rather than PASS.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import zipfile
import zlib
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from absump import paths
from absump.ingest import retrosheet
from absump.verify import re288_crosscheck as re288

REPO = paths.REPO_ROOT
BASE = retrosheet.base_dir()
PLAYS = BASE / "plays"
MANIFEST = paths.data_root() / "raw" / "_manifest.csv"
ATTRIBUTION = REPO / "ATTRIBUTION.md"
HOST = "www.retrosheet.org"
YEARS = retrosheet.YEARS

#: SOP W2.12: 2025plays.zip is exactly 7,496,795 B (HEAD, 2026-09-22).
VERIFIED_2025_BYTES = 7_496_795
#: config/throttle.yml, www.retrosheet.org: 10 s and 500 a day. The manifest
#: stamp is whole seconds and taken after the body is written, hence 2 s slack.
POLICY_S = 10.0
GAP_ALLOWANCE_S = 2.0
CAP = 500

#: SOP DT-27, the gate column, quoted: "≤0.01 runs per base-out-count cell".
DT27_BAR_TEXT = "≤0.01 runs per base-out-count cell"
DT27_BAR = 0.01

on_disk = pytest.mark.skipif(
    not PLAYS.is_dir(), reason="data/raw/retrosheet is absent (a clean clone); W2.12 reads MISSING"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _crc(path: Path) -> int:
    crc = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            crc = zlib.crc32(block, crc)
    return crc & 0xFFFFFFFF


@pytest.fixture(scope="module")
def rows() -> list[dict[str, str]]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("host") == HOST]


@pytest.fixture(scope="module")
def by_url(rows) -> dict[str, list[dict[str, str]]]:
    found: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        found.setdefault(row["url"], []).append(row)
    return found


@pytest.fixture(scope="module")
def record() -> dict:
    path = BASE / "_pull" / "record.json"
    return json.loads(path.read_text()) if path.exists() else {}


# ---------------------------------------------------------------------------
# R1-R3: one manifest row per archive, the archive is that body, CRCs hold
# ---------------------------------------------------------------------------


@on_disk
@pytest.mark.parametrize("year", YEARS)
def test_r1_one_manifest_row_per_archive_and_the_file_is_its_body(year, by_url):
    got = by_url.get(retrosheet.PLAYS_URL.format(year=year), [])
    assert len(got) == 1, f"{len(got)} manifest rows for {year}"
    assert got[0]["http_status"] == "200"
    zpath = paths.raw_retrosheet_plays(year)
    assert zpath.exists()
    assert _sha256(zpath) == got[0]["sha256"]


@on_disk
@pytest.mark.parametrize("year", YEARS)
def test_r2_r3_one_member_its_crc_holds_and_the_unzipped_file_matches(year):
    with zipfile.ZipFile(paths.raw_retrosheet_plays(year)) as archive:
        infos = archive.infolist()
        assert archive.testzip() is None
        assert [i.filename for i in infos] == [f"{year}plays.csv"]
        info = infos[0]
    out = retrosheet.unzipped_csv(year)
    assert out.exists() and out.stat().st_size == info.file_size
    assert _crc(out) == info.CRC


# ---------------------------------------------------------------------------
# R4: DT-27 clause one, the header, and the committed fixture
# ---------------------------------------------------------------------------


def _headers() -> dict[int, bytes]:
    found = {}
    for year in YEARS:
        path = retrosheet.unzipped_csv(year)
        if path.exists():
            with path.open("rb") as handle:
                found[year] = handle.readline().rstrip(b"\r\n")
    return found


@on_disk
def test_r4_dt27_the_header_is_identical_across_all_eleven_years():
    headers = _headers()
    assert sorted(headers) == list(YEARS)
    assert len(set(headers.values())) == 1


@on_disk
def test_r4_the_header_is_the_committed_fixture():
    header = next(iter(set(_headers().values())))
    fixture = retrosheet.FIXTURE.read_bytes()
    assert fixture == header + b"\n"
    assert fixture.count(b"\n") == 1


def test_r4_the_fixture_is_177_distinct_columns_from_gid_and_event():
    """Committed, so this half runs in a clean clone too."""
    columns = retrosheet.FIXTURE.read_bytes().rstrip(b"\n").decode("utf-8").split(",")
    assert len(columns) == 177
    assert [c for c, n in Counter(columns).items() if n > 1] == []
    assert columns[:2] == ["gid", "event"]
    for needed in (
        "outs_pre",
        "br1_pre",
        "br2_pre",
        "br3_pre",
        "pitches",
        "pa",
        "runs",
        "gametype",
    ):
        assert needed in columns, f"the RE288 build reads {needed}"


# ---------------------------------------------------------------------------
# R5: the HEAD-verified size and the pull record
# ---------------------------------------------------------------------------


@on_disk
def test_r5_2025_is_the_head_verified_size_or_the_change_is_recorded(record):
    y25 = record.get("years", {}).get("2025", {})
    changes = [c for c in record.get("size_changes", []) if c.get("year") == 2025]
    assert y25.get("bytes") == VERIFIED_2025_BYTES or changes


@on_disk
def test_r5_the_record_agrees_with_the_files(record):
    for year in YEARS:
        assert record["years"][str(year)]["sha256"] == _sha256(paths.raw_retrosheet_plays(year))


# ---------------------------------------------------------------------------
# R6: the notice and ATTRIBUTION.md
# ---------------------------------------------------------------------------


def _statement(text: str) -> str:
    lines = text.split("\n")
    start = next((i + 1 for i, line in enumerate(lines) if "must appear prominently" in line), None)
    if start is None:
        return ""
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    end = start
    while end < len(lines) and lines[end].strip() != "":
        end += 1
    return "\n".join(lines[start:end]) + "\n"


@on_disk
def test_r6_the_notice_is_the_manifested_body(by_url):
    got = by_url.get(retrosheet.NOTICE_URL, [])
    notice = (BASE / "notice.txt").read_bytes()
    assert len(got) == 1
    assert hashlib.sha256(notice).hexdigest() == got[0]["sha256"]


@on_disk
def test_r6_the_statement_is_byte_exact_in_attribution():
    text = (BASE / "notice.txt").read_bytes().decode("utf-8")
    statement = _statement(text)
    assert statement.strip()
    assert statement in ATTRIBUTION.read_text(encoding="utf-8")


@on_disk
def test_r6_the_full_notice_is_in_a_fenced_block_with_its_url():
    text = (BASE / "notice.txt").read_bytes().decode("utf-8")
    folded = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n") + "\n"
    attribution = ATTRIBUTION.read_text(encoding="utf-8")
    assert "```\n" + folded + "```" in attribution
    assert retrosheet.NOTICE_URL in attribution


# ---------------------------------------------------------------------------
# R7: throttled to D-63, nothing fetched twice
# ---------------------------------------------------------------------------


@on_disk
def test_r7_the_gap_between_calls_held_the_ten_second_policy(rows):
    starts = sorted(
        datetime.strptime(r["fetched_at_utc"], "%Y-%m-%dT%H:%M:%SZ").timestamp()
        - float(r["elapsed_s"])
        for r in rows
    )
    gaps = [b - a for a, b in itertools.pairwise(starts)]
    assert gaps and min(gaps) >= POLICY_S - GAP_ALLOWANCE_S


@on_disk
def test_r7_under_the_daily_cap_and_every_url_once(rows, by_url):
    per_day = Counter(r["fetched_at_utc"][:10] for r in rows)
    assert all(n <= CAP for n in per_day.values())
    expected = {retrosheet.PLAYS_URL.format(year=y) for y in YEARS} | {retrosheet.NOTICE_URL}
    assert set(by_url) == expected
    assert all(len(v) == 1 for v in by_url.values())
    assert all(int(r["attempt"]) <= 4 for r in rows)


# ---------------------------------------------------------------------------
# DT-27 clause two: the RE288 build, synthetic, runs everywhere
# ---------------------------------------------------------------------------


def test_re288_count_path_reads_the_retrosheet_pitch_codes():
    assert re288.count_path("BCX") == [(0, 0), (1, 0), (1, 1)]
    # A foul at two strikes leaves the count; a foul tip does not.
    assert re288.count_path("CCFFB") == [(0, 0), (0, 1), (0, 2), (0, 2), (0, 2)]
    assert re288.count_path("CCT") == [(0, 0), (0, 1), (0, 2)]
    # Markers are not pitches: pickoff throws, the runner going, a block, a play.
    assert re288.count_path(">B1*B.C+2X") == [(0, 0), (1, 0), (2, 0), (2, 1)]
    # V and A are the pitch-clock automatic ball and strike, 2023 onwards.
    assert re288.count_path("VAX") == [(0, 0), (1, 0), (1, 1)]
    assert re288.count_path("IIII") == [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert re288.count_path("BU") is None


def _row(half, pa, outs_pre, outs_post, bases, score, runs, pitches, gid="G1", inning="1"):
    first, second, third = (b if b != "-" else None for b in bases)
    sv, sh = (score, "0") if half == "0" else ("0", score)
    return (gid, inning, half, pa, outs_pre, outs_post, first, second, third, sv, sh, runs, pitches)


def test_re288_pitch_rows_splits_a_plate_appearance_at_a_stolen_base():
    """The pitches before the steal are thrown with the runner on first, the
    rest with him on second, and the runs to the end of the half count from
    the row each pitch belongs to."""
    rows = [
        _row("0", "1", "0", "0", "---", "0", "0", "BX"),  # single
        _row("0", "0", "0", "0", "r--", "0", "0", ">B"),  # SB2 on the first pitch
        _row("0", "1", "0", "0", "-r-", "0", "1", ">B.CX"),  # single, the runner scores
        _row("0", "1", "0", "1", "r--", "1", "0", "CCS"),  # strikeout
        _row("0", "1", "1", "3", "r--", "1", "0", "X"),  # double play, three out
    ]
    got = re288.pitch_rows(rows)
    assert [cell for cell, _ in got] == [
        (0, "---", 0, 0),
        (0, "---", 1, 0),
        (0, "1--", 0, 0),
        (0, "-2-", 1, 0),
        (0, "-2-", 1, 1),
        (0, "1--", 0, 0),
        (0, "1--", 0, 1),
        (0, "1--", 0, 2),
        (1, "1--", 0, 0),
    ]
    assert [rest for _, rest in got] == [1, 1, 1, 1, 1, 0, 0, 0, 0]


def test_re288_a_walk_off_half_inning_is_left_out():
    rows = [
        _row("1", "1", "0", "0", "---", "3", "1", "X", inning="9"),  # home run, game over
    ]
    assert re288.pitch_rows(rows) == []


def test_re288_a_substitution_row_does_not_reset_the_plate_appearance():
    rows = [
        _row("0", "0", "0", "0", "r--", "0", "0", "CB"),  # wild pitch on the B
        _row("0", "0", "0", "0", "-r-", "0", "0", None),  # a pinch runner comes in
        _row("0", "1", "0", "3", "-r-", "0", "0", "CB.X"),  # triple play, three outs
    ]
    cells = [cell for cell, _ in re288.pitch_rows(rows)]
    assert cells == [(0, "1--", 0, 0), (0, "1--", 0, 1), (0, "-2-", 1, 1)]


def test_re288_the_grid_is_288_cells():
    assert len(re288.CELLS) == 288
    assert len(set(re288.CELLS)) == 288
    assert re288.BAR_RUNS == DT27_BAR


# ---------------------------------------------------------------------------
# DT-27 clause two: the table the cross-check wrote, held to the quoted bar
# ---------------------------------------------------------------------------

TABLE = re288.OUT_PATH
table_written = pytest.mark.skipif(
    not TABLE.exists(), reason="out/tables/re288_crosscheck.csv has not been written"
)


@pytest.fixture(scope="module")
def table() -> list[dict[str, str]]:
    with TABLE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@table_written
def test_dt27_the_table_has_one_row_per_cell_and_quotes_the_bar(table):
    assert len(table) == 288
    assert {
        (int(r["outs"]), r["base_state"], int(r["balls"]), int(r["strikes"])) for r in table
    } == set(re288.CELLS)
    assert {r["bar"] for r in table} == {f"{DT27_BAR:.2f}"}, DT27_BAR_TEXT


@table_written
def test_dt27_every_cell_verdict_is_its_difference_against_the_bar(table):
    for r in table:
        if r["abs_diff"] == "":
            # 3-2 has no pure count move: a ball walks and a strike strikes out.
            assert (int(r["balls"]), int(r["strikes"])) == (3, 2) and r["pass"] == ""
            continue
        assert r["pass"] == ("true" if float(r["abs_diff"]) <= DT27_BAR else "false")


@table_written
def test_dt27_the_retrosheet_table_matches_the_statcast_built_table_on_dense_cells(table):
    """Reported, not the DT-27 gate: the Retrosheet 2022-2025 RE288 against the
    warehouse's own Statcast-built fct_re288, over cells with 10,000 pitches
    or more on the Statcast side (77 cells on 2026-09-30: median 0.0034, max
    0.029 runs). This is what shows the build is sound."""
    dense = [r for r in table if int(r["n_warehouse"]) >= 10_000 and r["diff_re_warehouse"] != ""]
    assert len(dense) >= 70
    gaps = np.abs([float(r["diff_re_warehouse"]) for r in dense])
    assert float(np.median(gaps)) <= DT27_BAR
    assert float(np.max(gaps)) <= 0.03


#: The verdict out/tables/re288_crosscheck.csv records, pinned. The cross-check
#: ran on 2026-09-30 against Statcast 2022-2025: 218 of the 264 cells that
#: have a pure count move are over the 0.01 bar, the largest 0.354 runs at 0
#: out, bases loaded, 2-2. DT-27's second clause FAILS at the SOP's bar. This
#: is a finding, not a defect of the build: Savant's delta_run_exp on a pure
#: count move is a smoothed table's difference (a ball at 2-2 with the bases
#: loaded and nobody out is worth +0.111 to Savant and +0.465 in the raw
#: Retrosheet table), and the raw Retrosheet table agrees with the raw
#: Statcast one (the test above). SOP risk R-35 defers the cross-check; the
#: bar is an owner decision. If the table changes, this pin fails and the new
#: verdict has to be read and recorded here.
RECORDED_CELLS_OVER_BAR = 218
RECORDED_CELLS_COMPARED = 264


@table_written
def test_dt27_the_recorded_verdict_is_the_one_in_the_table(table):
    compared = [r for r in table if r["abs_diff"] != ""]
    over = [r for r in compared if r["pass"] == "false"]
    assert len(compared) == RECORDED_CELLS_COMPARED
    assert len(over) == RECORDED_CELLS_OVER_BAR
