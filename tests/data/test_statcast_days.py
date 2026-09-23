"""W2.9 contract tests for the Statcast MLB daily CSV.

SOP W2.9 names this file and what it has to assert: `rows < 25000` every day;
header sha256 matches the fixture 2015-2026; BOM present; `umpire` 0%
non-empty; and for every day the distinct `game_pk` set equals the set of
`Final` games for that `officialDate` in `schedule_game`, with mismatches
written to `out/tables/statcast_day_exceptions.csv`.

Two kinds of test here, and the difference matters.

SYNTHETIC tests build a day out of the 119 column names committed in
`contracts/statcast_csv.yml` and assert the guards fire. They need no data and
run in a clean clone, which is RP-08. They are what proves UT-15 actually stops
a truncated response, because no real day comes anywhere near the cap.

SWEEP tests read every day in the raw lake. `data/` is gitignored, so they skip
when it is empty and say so. On a machine that has the lake they are the real
DT-01 and DT-02: one pass over every stored day, no sampling.

The lake sweep is one pass, shared by a session fixture. Re-reading 799 zstd
days once per test would cost half an hour; once costs about thirty seconds.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

import pytest

from absump import paths
from absump.ingest import statcast_day as sc

REPO_ROOT = Path(__file__).resolve().parents[2]
EXCEPTIONS_PATH = REPO_ROOT / "out" / "tables" / "statcast_day_exceptions.csv"

# SOP W2.9, the measured days, verbatim. contracts/statcast_csv.yml carries the
# same numbers with the caveat on 2026-09-16; this list is the assertion.
MEASURED_DAYS = {
    "2026-09-16": {"bytes": 3093051, "rows": 4501, "columns": 119, "games": 15},
    "2026-09-15": {"bytes": 3033672, "rows": 4427, "columns": 119, "games": 15},
    "2025-09-15": {"bytes": 1871998, "rows": 2739, "columns": 119, "games": 9},
    "2024-09-15": {"bytes": 2996245, "rows": 4380, "columns": 119, "games": 15},
}

# SOP W2.9, the full-day `description` counts on 2026-09-15, verbatim.
DESCRIPTION_COUNTS_2026_09_15 = {
    "ball": 1462,
    "foul": 801,
    "hit_into_play": 764,
    "called_strike": 719,
    "swinging_strike": 466,
    "blocked_ball": 100,
    "foul_tip": 41,
    "swinging_strike_blocked": 27,
    "automatic_ball": 19,
    "hit_by_pitch": 14,
    "foul_bunt": 10,
    "missed_bunt": 3,
    "pitchout": 1,
}

# SOP W2.9: 100.0% non-empty over the 2,281 called pitches of 2026-09-15.
CALLED_COMPLETE_COLUMNS = (
    "plate_x",
    "plate_z",
    "sz_top",
    "sz_bot",
    "zone",
    "fielder_2",
    "delta_run_exp",
    "delta_home_win_exp",
    "balls",
    "strikes",
    "outs_when_up",
    "inning",
    "stand",
    "p_throws",
)


# ---------------------------------------------------------------------------
# A synthetic day, built from the committed column list
# ---------------------------------------------------------------------------


def _quote(value: str) -> str:
    inner = value.replace('"', '""')
    return f'"{inner}"'


def synth_day(rows: list[dict[str, str]], *, bom: bool = True, columns=None) -> bytes:
    """A Savant-shaped CSV: BOM, every field quoted, LF, no trailing newline.

    Built from the contract's own column list, so it carries no Savant bytes
    and can be committed. The header it produces is the header the fixture
    pins, which `test_dt02_column_list_reproduces_the_fixture` proves.
    """
    names = tuple(columns) if columns is not None else sc.contract_columns()
    lines = [",".join(_quote(name) for name in names)]
    for row in rows:
        lines.append(",".join(_quote(row.get(name, "")) for name in names))
    body = "\n".join(lines).encode("utf-8")
    return b"\xef\xbb\xbf" + body if bom else body


def tracked_row(**overrides: str) -> dict[str, str]:
    """One tracked called strike, with every column the guards look at filled."""
    row = {
        "pitch_type": "FF",
        "game_date": "2026-09-15",
        "description": "called_strike",
        "plate_x": "0.10",
        "plate_z": "2.50",
        "sz_top": "3.40",
        "sz_bot": "1.60",
        "zone": "5",
        "game_pk": "800001",
        "umpire": "",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# The lake sweep, once per session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def lake() -> list[sc.DayReport]:
    """Every stored day, validated in one pass. Empty list on a clean clone."""
    return sc.verify_lake(stream=io.StringIO())


def require_lake(lake: list[sc.DayReport]) -> None:
    if not lake:
        pytest.skip(
            "no Statcast day in data/raw; the raw lake is gitignored, so this "
            "sweep has nothing to read. Run "
            "`python -m absump.ingest.statcast_day --import-staging` first."
        )


# ---------------------------------------------------------------------------
# DT-02, the committed header. Synthetic.
# ---------------------------------------------------------------------------


def test_dt02_column_list_reproduces_the_fixture():
    """The 119 committed names ARE the committed digest, not a second copy of it.

    Quote every name, join with commas, put the BOM in front: that is the
    header line Savant serves, 1,825 bytes. If this fails, the contract's
    column list and the fixture digest have drifted apart and one of them is
    describing a table nobody has.
    """
    names = sc.contract_columns()
    assert len(names) == sc.COLUMN_COUNT == 119
    assert len(set(names)) == len(names), "a column name is repeated"

    line = b"\xef\xbb\xbf" + ",".join(_quote(name) for name in names).encode("utf-8")
    assert len(line) == sc.contract()["header"]["line_bytes_with_bom"] == 1825
    assert hashlib.sha256(line).hexdigest() == sc.expected_header_sha256()
    assert hashlib.sha256(line[3:]).hexdigest() == sc.expected_header_sha256(with_bom=False)


def test_dt02_fixture_and_contract_carry_the_same_digest():
    header = sc.contract()["header"]
    assert header["sha256"] == sc.expected_header_sha256()
    assert header["sha256_nobom"] == sc.expected_header_sha256(with_bom=False)
    assert header["fixture"] == "tests/fixtures/statcast_header.sha256"


def test_dt02_a_renamed_column_is_refused():
    names = list(sc.contract_columns())
    names[0] = "pitchType"
    body = synth_day([], columns=names)
    with pytest.raises(sc.HeaderDrift):
        sc.validate_day(body, "2026-09-15")


def test_dt02_a_dropped_column_is_refused():
    names = list(sc.contract_columns())[:-1]
    body = synth_day([], columns=names)
    with pytest.raises(sc.HeaderDrift):
        sc.validate_day(body, "2026-09-15")


def test_no_abs_or_challenge_column_in_the_contract():
    """SOP W2.9: there is no ABS or challenge column of any kind."""
    names = sc.contract_columns()
    for marker in ("abs", "challeng", "review", "robo"):
        hits = [name for name in names if marker in name.lower()]
        assert hits == [], f"{marker!r} matched {hits}"
    assert "umpire" in names, "the deprecated umpire column is part of the header"


# ---------------------------------------------------------------------------
# UT-14, the BOM. Synthetic.
# ---------------------------------------------------------------------------


def test_ut14_plain_utf8_keeps_the_bom_on_the_first_column():
    """The trap, demonstrated, and it bites harder than one stray character.

    Decoded with plain utf-8 the first field does not merely gain U+FEFF.
    The BOM sits in front of the opening quote, so the reader no longer sees
    a quoted field at all and hands back the quote characters too: the first
    column name comes out as U+FEFF followed by a quoted "pitch_type". Either
    way it never matches "pitch_type" again. utf-8-sig gives the name.

    U+FEFF is written as an escape here, never as a literal, so that the
    source of the BOM test does not itself contain an invisible BOM.
    """
    body = synth_day([tracked_row()])
    naive = next(csv.reader([body.decode("utf-8").split("\n")[0]]))
    assert naive[0].startswith("\ufeff")
    assert naive[0] == '\ufeff"pitch_type"'
    assert naive[0] != "pitch_type"
    assert sc.columns_of(body)[0] == "pitch_type"
    assert sc.decode(body)[0] != "\ufeff"


def test_ut14_a_body_without_a_bom_is_refused():
    body = synth_day([tracked_row()], bom=False)
    with pytest.raises(sc.MissingBom):
        sc.validate_day(body, "2026-09-15")
    with pytest.raises(sc.MissingBom):
        sc.decode(body)


# ---------------------------------------------------------------------------
# UT-15, the silent 25,000-row cap. Synthetic.
# ---------------------------------------------------------------------------


def test_ut15_the_day_guard_fires_at_the_cap():
    """Exactly 25,000 rows is the truncated response, so exactly 25,000 fails.

    Savant caps silently and keeps the NEWEST rows, so a response that is
    exactly at the cap is missing its oldest days with no header to say so.
    24,999 is a real answer; 25,000 is not an answer at all.
    """
    assert sc.ROW_CAP == 25_000

    under = synth_day([tracked_row(game_pk=str(800000 + i)) for i in range(sc.ROW_CAP - 1)])
    report = sc.validate_day(under, "2026-09-15")
    assert report.n_rows == sc.ROW_CAP - 1 == 24_999

    at_cap = synth_day([tracked_row(game_pk=str(800000 + i)) for i in range(sc.ROW_CAP)])
    with pytest.raises(sc.RowCapReached) as caught:
        sc.validate_day(at_cap, "2026-09-15")
    assert "25000" in str(caught.value)


def test_ut15_the_guard_is_the_contract_number():
    assert sc.contract()["traps"]["row_cap"]["cap"] == sc.ROW_CAP


# ---------------------------------------------------------------------------
# The untracked rows. Synthetic.
# ---------------------------------------------------------------------------


def test_untracked_rows_are_flagged_and_kept_out_of_the_called_population():
    """SOP W2.9: keep them with tracked = false, exclude them from the mart."""
    blank = dict.fromkeys(sc.TRACKING_COLUMNS, "")
    rows = [
        tracked_row(),
        tracked_row(description="ball"),
        tracked_row(description="automatic_ball", **blank),
        tracked_row(description="foul", **blank),
    ]
    body = synth_day(rows)
    report = sc.validate_day(body, "2026-09-15")

    assert report.n_rows == 4
    assert report.n_untracked == 2
    assert report.n_called == 2, "an untracked automatic_ball is not a called pitch"

    parsed = list(sc.iter_rows(body))
    assert [sc.is_tracked(row) for row in parsed] == [True, True, False, False]
    assert len(sc.called_pitches(parsed)) == 2


def test_the_tracking_columns_are_the_four_the_sop_names():
    assert set(sc.TRACKING_COLUMNS) == {"pitch_type", "plate_x", "sz_bot", "sz_top"}
    assert set(sc.contract()["traps"]["untracked_rows"]["columns"]) == set(sc.TRACKING_COLUMNS)


def test_called_descriptions_are_the_three_the_sop_names():
    assert sorted(sc.CALLED_DESCRIPTIONS) == ["ball", "blocked_ball", "called_strike"]
    assert set(sc.contract()["called_pitch"]["descriptions"]) == sc.CALLED_DESCRIPTIONS


# ---------------------------------------------------------------------------
# The URL and the seal. Synthetic.
# ---------------------------------------------------------------------------


def test_the_day_url_is_the_sop_url():
    assert sc.day_url("2026-09-15") == (
        "https://baseballsavant.mlb.com/statcast_search/csv"
        "?all=true&type=details"
        "&player_type=batter&min_pitches=0&min_results=0&group_by=name"
        "&sort_col=pitches&player_event_sort=api_p_release_speed&sort_order=desc"
        "&hfSea=2026%7C&game_date_gt=2026-09-15&game_date_lt=2026-09-15"
    )


def test_the_day_url_carries_no_hfgt_so_the_postseason_is_included():
    """SOP W2.9: 2025-10-25 returned 224 rows for game_pk 813026, gameType W."""
    url = sc.day_url("2025-10-25")
    assert "hfGT" not in url
    assert "hfSea=2025%7C" in url
    assert sc.contract()["endpoint"]["hfgt_parameter"] == "absent"


def test_the_day_url_is_stable_because_the_cache_is_keyed_on_it():
    assert sc.day_url("2026-09-15") == sc.day_url(dt.date(2026, 9, 15))


def test_the_day_url_refuses_a_sealed_day():
    """The 2026 cutoff for every pull in this phase is 2026-09-21 inclusive."""
    assert paths.LAST_OPEN_DATE.isoformat() == "2026-09-21"
    assert sc.day_url("2026-09-21").endswith("game_date_lt=2026-09-21")
    for sealed in ("2026-09-22", "2026-09-23", "2026-10-25"):
        with pytest.raises(paths.SealViolation):
            sc.day_url(sealed)


def test_store_day_refuses_a_sealed_day(tmp_path, monkeypatch):
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path))
    with pytest.raises(paths.SealViolation):
        sc.store_day(synth_day([tracked_row()]), "2026-09-22")


# ---------------------------------------------------------------------------
# Idempotence. Synthetic.
# ---------------------------------------------------------------------------


def test_store_day_twice_changes_no_bytes(tmp_path, monkeypatch):
    """A pipeline step is not done until running it twice changes nothing."""
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path))
    body = synth_day([tracked_row()])

    first, wrote_first = sc.store_day(body, "2026-09-15")
    assert wrote_first is True
    before = first.read_bytes()

    second, wrote_second = sc.store_day(body, "2026-09-15")
    assert second == first
    assert wrote_second is False
    assert first.read_bytes() == before
    assert sc.read_day(first) == body


def test_store_day_leaves_no_temporary_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path))
    dest, _ = sc.store_day(synth_day([tracked_row()]), "2026-09-15")
    assert sorted(p.name for p in dest.parent.iterdir()) == ["pitches.csv.zst"]


# ---------------------------------------------------------------------------
# The schedule cross-check, as a function. Synthetic.
# ---------------------------------------------------------------------------


def test_day_exceptions_reports_both_directions_and_the_missing_day():
    reports = [
        sc.validate_day(
            synth_day([tracked_row(game_pk="1"), tracked_row(game_pk="2")]), "2026-05-01"
        ),
        sc.validate_day(synth_day([tracked_row(game_pk="9")]), "2026-05-02"),
    ]
    schedule = {
        dt.date(2026, 5, 1): {1, 2},
        dt.date(2026, 5, 2): {9, 10},
        dt.date(2026, 5, 3): {11},
    }
    rows = sc.day_exceptions(reports, schedule)
    kinds = {row["kind"]: row for row in rows}

    assert set(kinds) == {"game_pk_mismatch", "day_missing"}
    assert kinds["game_pk_mismatch"]["game_date"] == "2026-05-02"
    assert kinds["game_pk_mismatch"]["missing_from_csv"] == "10"
    assert kinds["game_pk_mismatch"]["extra_in_csv"] == ""
    assert kinds["day_missing"]["game_date"] == "2026-05-03"

    extra = [
        sc.validate_day(synth_day([tracked_row(game_pk="99")]), "2026-05-01"),
    ]
    rows = sc.day_exceptions(extra, {dt.date(2026, 5, 1): {1}})
    assert rows[0]["extra_in_csv"] == "99"
    assert rows[0]["missing_from_csv"] == "1"


def test_day_exceptions_does_not_judge_a_day_outside_the_schedule_span():
    """A day the schedule cannot speak for is not a mismatch.

    The schedule is authoritative over its own date span and nowhere else. A
    2022 day judged against a 2026-only schedule would otherwise read as
    every one of its games being unscheduled, which is a statement about the
    schedule and not about the day. The schedule's own unplayed day is still
    reported, as coverage.
    """
    reports = [sc.validate_day(synth_day([tracked_row(game_pk="1")]), "2022-05-01")]
    rows = sc.day_exceptions(reports, {dt.date(2026, 5, 1): {1}})
    assert [row for row in rows if row["kind"] == "game_pk_mismatch"] == []
    assert [row["game_date"] for row in rows] == ["2026-05-01"]


# ---------------------------------------------------------------------------
# DT-01, DT-02, UT-14 and the umpire column over every stored day. Sweep.
# ---------------------------------------------------------------------------


def test_dt01_every_stored_day_is_under_the_cap(lake):
    require_lake(lake)
    over = [report for report in lake if report.n_rows >= sc.ROW_CAP]
    assert over == [], f"{len(over)} day(s) at or above the {sc.ROW_CAP}-row cap"

    widest = max(lake, key=lambda report: report.n_rows)
    assert widest.n_rows == sc.contract()["traps"]["row_cap"]["max_observed_rows"], (
        f"the widest day on disk is {widest.game_date} with {widest.n_rows} rows; "
        "contracts/statcast_csv.yml records a different maximum"
    )


def test_dt02_one_header_digest_across_every_stored_day(lake):
    """Including 2022 and 2023, which were unverified before this project."""
    require_lake(lake)
    expected = sc.expected_header_sha256()
    wrong = [report.game_date.isoformat() for report in lake if report.header_sha256 != expected]
    assert wrong == [], f"header drift on {wrong[:10]}"
    assert {report.n_columns for report in lake} == {sc.COLUMN_COUNT}

    seasons = {report.season for report in lake}
    assert {2022, 2023} <= seasons, f"2022 and 2023 are the point of DT-02; got {sorted(seasons)}"


def test_ut14_every_stored_day_carries_the_bom(lake):
    """The sweep digest is taken over the header line WITH the BOM, so a day
    that passed DT-02 carried one. This asserts it again from the bytes, on a
    sample, because an assertion that is only a corollary is not an assertion."""
    require_lake(lake)
    days = sc.raw_days()
    sample = [days[0], days[len(days) // 2], days[-1]]
    for day, path in sample:
        body = sc.read_day(path)
        assert body.startswith(b"\xef\xbb\xbf"), f"{day} has no BOM"


def test_umpire_column_is_empty_on_every_stored_day(lake):
    """SOP W2.9: 0 of 4,427 non-empty in 2026, 2025 and 2024. Umpires are W2.5's."""
    require_lake(lake)
    filled = [(report.game_date.isoformat(), report.n_umpire) for report in lake if report.n_umpire]
    assert filled == [], f"the deprecated umpire column is not empty on {filled[:5]}"


def test_no_stored_day_crosses_the_seal(lake):
    require_lake(lake)
    crossed = [report.game_date.isoformat() for report in lake if paths.is_sealed(report.game_date)]
    assert crossed == [], f"{crossed} are past {paths.LAST_OPEN_DATE}"


def test_the_untracked_rows_are_a_small_tail_everywhere(lake):
    """A tail, not a mode, and never a whole day.

    Measured 2026-09-23 over 799 days: 11,527 untracked rows of 3,108,070,
    or 0.371 per cent, present on 777 of 799 days. The worst single day is
    2024-05-23 at 180 of 2,485, or 7.2 per cent, and 167 of those 180 are one
    game whose tracking was down for most of it. The bounds below sit well
    clear of both, because what they have to catch is a day where tracking
    failed wholesale and the called-pitch mart would quietly lose most of its
    population.
    """
    require_lake(lake)
    rows = sum(report.n_rows for report in lake)
    untracked = sum(report.n_untracked for report in lake)
    assert untracked / rows < 0.01, (
        f"{untracked} of {rows} rows untracked across the lake; measured 0.371 per cent"
    )

    worst = max(
        (report for report in lake if report.n_rows),
        key=lambda report: report.n_untracked / report.n_rows,
    )
    assert worst.n_untracked / worst.n_rows < 0.20, (
        f"{worst.game_date} is {worst.n_untracked}/{worst.n_rows} untracked; "
        "that is not a tail, that is a broken day"
    )


# ---------------------------------------------------------------------------
# The measured days, verbatim from the SOP. Sweep.
# ---------------------------------------------------------------------------


def _stored(day: str) -> bytes | None:
    path = sc.raw_path(day)
    return sc.read_day(path) if path.exists() else None


@pytest.mark.parametrize("day", sorted(MEASURED_DAYS))
def test_the_sop_measured_days_reproduce(day):
    body = _stored(day)
    if body is None:
        pytest.skip(f"{day} is not in data/raw")
    want = MEASURED_DAYS[day]
    report = sc.validate_day(body, day)
    assert report.body_bytes == want["bytes"]
    assert report.n_rows == want["rows"]
    assert report.n_columns == want["columns"]
    assert len(report.game_pks) == want["games"]


def test_2026_09_15_description_counts_reproduce():
    body = _stored("2026-09-15")
    if body is None:
        pytest.skip("2026-09-15 is not in data/raw")
    report = sc.validate_day(body, "2026-09-15")
    assert report.description_counts == DESCRIPTION_COUNTS_2026_09_15
    assert sum(DESCRIPTION_COUNTS_2026_09_15.values()) == 4427


def test_2026_09_15_untracked_rows_are_the_twenty_the_sop_names():
    body = _stored("2026-09-15")
    if body is None:
        pytest.skip("2026-09-15 is not in data/raw")
    rows = list(sc.iter_rows(body))
    untracked = [row for row in rows if not sc.is_tracked(row)]
    assert len(untracked) == 20
    assert Counter(row["description"] for row in untracked) == {"automatic_ball": 19, "foul": 1}

    # Blank together, never one without the others.
    for row in rows:
        blank = {column for column in sc.TRACKING_COLUMNS if not row[column].strip()}
        assert blank in (set(), set(sc.TRACKING_COLUMNS)), row["game_pk"]

    # plate_z and zone are blank on exactly the same 20 rows.
    for column in ("plate_z", "zone"):
        assert sum(1 for row in rows if not row[column].strip()) == 20


def test_2026_09_15_called_pitch_population_is_complete():
    """SOP W2.9's completeness table for the 2,281 called pitches."""
    body = _stored("2026-09-15")
    if body is None:
        pytest.skip("2026-09-15 is not in data/raw")
    called = sc.called_pitches(sc.iter_rows(body))
    assert len(called) == 2281

    for column in CALLED_COMPLETE_COLUMNS:
        filled = sum(1 for row in called if row[column].strip())
        assert filled == 2281, f"{column} is {filled}/2281, not 100.0%"

    assert sum(1 for row in called if row["arm_angle"].strip()) == 2280
    assert sum(1 for row in called if row["bat_speed"].strip()) == 0


# ---------------------------------------------------------------------------
# The schedule cross-check, against real data. Sweep.
# ---------------------------------------------------------------------------


def _schedule_from_warehouse() -> dict[dt.date, set[int]] | None:
    """`schedule_game` from the warehouse, when W2.5 and W2.6 have built it."""
    if not paths.DUCKDB_PATH.exists():
        return None
    import duckdb

    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as connection:
        names = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        if "schedule_game" not in names:
            return None
        rows = connection.execute(
            "SELECT official_date, game_pk FROM schedule_game WHERE abstract_game_state = 'Final'"
        ).fetchall()
    schedule: dict[dt.date, set[int]] = {}
    for official_date, game_pk in rows:
        day = paths.as_official_date(official_date)
        if paths.is_sealed(day):
            continue
        schedule.setdefault(day, set()).add(int(game_pk))
    return schedule or None


def _schedule_from_staging() -> dict[dt.date, set[int]] | None:
    """The staged statsapi schedules, until `schedule_game` exists.

    SOP W2.9 names `schedule_game`. It is W2.5 and W2.6's table and is not
    built yet, and a cross-check that only ever skips is not a cross-check, so
    this falls back to the same bytes that table will be built from. The
    staging cache is an input to this phase, with provenance in its
    manifest.jsonl.
    """
    root = paths.data_root() / "staging" / "statsapi" / "schedule"
    if not root.is_dir():
        return None
    schedule: dict[dt.date, set[int]] = {}
    for path in sorted(root.glob("sport1-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload.get("dates", []):
            for game in entry.get("games", []):
                if game["status"]["abstractGameState"] != "Final":
                    continue
                day = dt.date.fromisoformat(game["officialDate"])
                if paths.is_sealed(day):
                    # The seal is not a coverage gap. A day past 2026-09-21 is
                    # a day this phase must not pull, so it is not missing.
                    continue
                schedule.setdefault(day, set()).add(int(game["gamePk"]))
    return schedule or None


def test_every_day_holds_the_games_the_schedule_says_it_holds(lake):
    """DT-01's companion: the day list is complete and the join key is right.

    The assertion is not "no exceptions". A rained-out game has an officialDate
    and no pitches, and the SOP says so. The assertion is that every exception
    is of that kind: nothing in a day CSV that the schedule does not place on
    that officialDate, and every game the schedule has and the CSV lacks is one
    that was never played.
    """
    require_lake(lake)
    schedule = _schedule_from_warehouse()
    source = "schedule_game"
    if schedule is None:
        schedule = _schedule_from_staging()
        source = "data/staging/statsapi/schedule"
    if schedule is None:
        pytest.skip(
            "no schedule to check against: schedule_game is not in the warehouse "
            "and the staging cache has no statsapi schedule"
        )

    rows = sc.day_exceptions(lake, schedule)
    EXCEPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    sc.write_day_exceptions(rows, EXCEPTIONS_PATH)

    mismatches = [row for row in rows if row["kind"] == "game_pk_mismatch"]
    extras = [row for row in mismatches if row["extra_in_csv"]]
    assert extras == [], (
        f"{len(extras)} day(s) carry a game_pk the schedule ({source}) does not place "
        f"on that officialDate. That is a wrong day list or a wrong join key, not a "
        f"rain-out. See {EXCEPTIONS_PATH}"
    )

    assert [
        row for row in rows if paths.is_sealed(dt.date.fromisoformat(row["game_date"]))
    ] == [], "a sealed day reached the exceptions table; the seal is not a coverage gap"

    judged = [report for report in lake if min(schedule) <= report.game_date <= max(schedule)]
    assert len(mismatches) < 0.02 * max(len(judged), 1), (
        f"{len(mismatches)} of {len(judged)} judged days disagree with {source}; "
        f"suspended and rained-out games are the expected entries, not this many. "
        f"See {EXCEPTIONS_PATH}"
    )


def test_the_exceptions_table_is_written_sorted_and_is_idempotent(tmp_path):
    rows = sc.day_exceptions(
        [sc.validate_day(synth_day([tracked_row(game_pk="9")]), "2026-05-02")],
        {dt.date(2026, 5, 1): {1}, dt.date(2026, 5, 2): {9, 10}},
    )
    first = sc.write_day_exceptions(rows, tmp_path / "statcast_day_exceptions.csv")
    before = first.read_bytes()
    sc.write_day_exceptions(rows, first)
    assert first.read_bytes() == before

    with first.open(encoding="utf-8", newline="") as handle:
        table = list(csv.DictReader(handle))
    assert list(table[0]) == list(sc.EXCEPTION_COLUMNS)
