"""UT-17. ``config/seal.yml`` agrees with ``quality/sql/analysis_set.sql``.

SOP section 2.4 keeps one predicate in one file and mirrors its constants in
``config/seal.yml`` so Python and R do not re-derive them. Two copies of a rule
drift. This test is the thing that stops the drift: it checks the constants
against the SQL text, and then checks that a classifier built only from the YAML
returns the same label as the SQL for every combination of season, game-type
code and boundary date in a 168-row grid.

No 2026 row is read. The grid is literal tuples built in memory.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import duckdb
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PREDICATE_PATH = REPO_ROOT / "quality" / "sql" / "analysis_set.sql"
CONFIG_PATH = REPO_ROOT / "config" / "seal.yml"

SEALED = "sealed"
OPEN = "open"
EXCLUDED = "excluded"

# The regular-season code. The SQL header comment is the authority: "R regular".
# It is the one sealed code that is also gated on the date, because the 2026
# regular season straddles the seal start; the postseason rounds do not.
REGULAR = "R"

EXPECTED_KEYS = {
    "seal_start_date",
    "regular_season_end",
    "postseason_end_estimate",
    "sealed_game_types",
    "excluded_game_types",
    "prereg_tag",
}

D = dt.date.fromisoformat


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def predicate_text() -> str:
    return PREDICATE_PATH.read_text(encoding="utf-8")


def sql_in_list(branch_label: str) -> list[str]:
    """The codes in the ``IN (...)`` list of the branch whose THEN is given."""
    text = predicate_text()
    pattern = re.compile(r"IN\s*\(([^)]*)\)[^\n]*THEN\s*'" + branch_label + r"'", re.IGNORECASE)
    match = pattern.search(text)
    assert match is not None, f"no IN-list branch returning {branch_label!r}"
    return re.findall(r"'([A-Z])'", match.group(1))


def classify_sql(rows: list[tuple[int, str, dt.date]]) -> list[str]:
    """Run the frozen predicate over ``rows`` in DuckDB."""
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE game (season INTEGER, game_type VARCHAR, official_date DATE)")
        con.executemany("INSERT INTO game VALUES (?, ?, ?)", [list(r) for r in rows])
        return [row[0] for row in con.execute(f"SELECT {predicate_text()} FROM game").fetchall()]
    finally:
        con.close()


def classify_config(cfg: dict, season: int, game_type: str, official_date: dt.date) -> str:
    """The same rule, built only from ``config/seal.yml``.

    This is what a Python or R caller would write from the YAML alone. If it
    disagrees with the SQL on any row, the mirror is wrong.
    """
    if game_type in cfg["excluded_game_types"]:
        return EXCLUDED
    sealed_season = D(cfg["seal_start_date"]).year
    if season == sealed_season:
        if game_type == REGULAR and official_date >= D(cfg["seal_start_date"]):
            return SEALED
        if game_type in [t for t in cfg["sealed_game_types"] if t != REGULAR]:
            return SEALED
    return OPEN


# ------------------------------------------------------------------ the shapes
def test_config_has_exactly_the_six_keys() -> None:
    cfg = load_config()
    assert set(cfg) == EXPECTED_KEYS
    for key in ("sealed_game_types", "excluded_game_types"):
        assert isinstance(cfg[key], list)
        assert all(isinstance(code, str) and len(code) == 1 for code in cfg[key])
    assert isinstance(cfg["prereg_tag"], str)


def test_dates_parse_and_are_ordered() -> None:
    cfg = load_config()
    start = D(cfg["seal_start_date"])
    reg_end = D(cfg["regular_season_end"])
    post_end = D(cfg["postseason_end_estimate"])
    assert start <= reg_end < post_end
    assert start.year == reg_end.year == post_end.year


def test_code_sets_are_disjoint_and_cover_the_sql_code_table() -> None:
    """Every code the SQL header documents is either sealed or excluded."""
    cfg = load_config()
    sealed = set(cfg["sealed_game_types"])
    excluded = set(cfg["excluded_game_types"])
    assert sealed & excluded == set()
    # The header comment line: "R regular, F wild card, D division, ..."
    header = [ln for ln in predicate_text().splitlines() if ln.startswith("--   R ")]
    assert len(header) == 1, "the SQL header's gameType code table moved"
    documented = set(re.findall(r"(?:^|\s)([A-Z]) [a-z]", header[0]))
    assert documented == sealed | excluded


# -------------------------------------------------------- constant by constant
def test_excluded_codes_match_the_sql() -> None:
    assert sql_in_list(EXCLUDED) == load_config()["excluded_game_types"]


def test_sealed_codes_match_the_sql() -> None:
    cfg = load_config()
    # The date-gated branch names the regular-season code on its own; the other
    # branch lists the postseason rounds.
    assert re.search(r"game_type\s*=\s*'R'", predicate_text()) is not None
    from_sql = [REGULAR, *sql_in_list(SEALED)]
    assert from_sql == cfg["sealed_game_types"]


def test_seal_start_date_matches_the_sql_literal() -> None:
    cfg = load_config()
    literals = re.findall(r"DATE\s*'(\d{4}-\d{2}-\d{2})'", predicate_text())
    assert literals == [cfg["seal_start_date"]], "one date literal, and it is the mirror"


def test_sealed_season_matches_the_sql_literal() -> None:
    cfg = load_config()
    seasons = {int(s) for s in re.findall(r"season\s*=\s*(\d{4})", predicate_text())}
    assert seasons == {D(cfg["seal_start_date"]).year}
    assert seasons == {D(cfg["regular_season_end"]).year}


def test_prereg_tag_matches_the_sql_header() -> None:
    cfg = load_config()
    assert f"Frozen at tag {cfg['prereg_tag']}." in predicate_text()
    # SOP resolution table: the literal tag string, not prereg-v1.0.
    assert cfg["prereg_tag"] == "prereg-v1"


# ------------------------------------------------------------ case by case
def grid() -> list[tuple[int, str, dt.date]]:
    cfg = load_config()
    codes = sorted(set(cfg["sealed_game_types"]) | set(cfg["excluded_game_types"]))
    start = D(cfg["seal_start_date"])
    dates = [
        start - dt.timedelta(days=180),
        start - dt.timedelta(days=1),
        start,
        start + dt.timedelta(days=1),
        D(cfg["regular_season_end"]),
        D(cfg["regular_season_end"]) + dt.timedelta(days=3),
        D(cfg["postseason_end_estimate"]),
    ]
    seasons = [start.year - 2, start.year - 1, start.year]
    return [(season, code, day) for season in seasons for code in codes for day in dates]


def test_grid_is_the_expected_size() -> None:
    rows = grid()
    assert len(rows) == 168
    assert len(set(rows)) == 168


def test_config_and_sql_agree_on_every_grid_row() -> None:
    cfg = load_config()
    rows = grid()
    from_sql = classify_sql(rows)
    from_cfg = [classify_config(cfg, *row) for row in rows]
    mismatches = [(row, a, b) for row, a, b in zip(rows, from_sql, from_cfg, strict=True) if a != b]
    assert not mismatches, f"{len(mismatches)} rows disagree, first: {mismatches[:3]}"


def test_the_grid_exercises_all_three_labels() -> None:
    """A vacuous agreement test would pass if everything came back open."""
    labels = set(classify_sql(grid()))
    assert labels == {SEALED, OPEN, EXCLUDED}


@pytest.mark.parametrize("path", [PREDICATE_PATH, CONFIG_PATH])
def test_both_files_exist(path: Path) -> None:
    assert path.is_file(), f"{path} is half of the mirror UT-17 checks"
