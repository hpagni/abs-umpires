"""UT-16. The seal classifier.

SOP section 2.4 puts the rule in one predicate, in one file,
``quality/sql/analysis_set.sql``, frozen at the tag ``prereg-v1``. This test
executes that file. It does not reimplement the rule in Python, because a second
implementation is a second thing to drift.

The four cases SOP W9.5 names for UT-16:

    (2026, 'R', 2026-09-22)  -> sealed
    (2026, 'W', any date)    -> sealed
    (2026, 'R', 2026-09-21)  -> open
    ('S',  any season, any date) -> excluded

The rest of the cases here pin the two things the predicate exists to stop:
R-29 spring-training leakage, which is why the filter is on explicit game-type
codes and not on a date alone, and the 2026-only scope, which is why a 2025
postseason game is open training data rather than held-out data.

No 2026 row is read. Every case is a literal tuple built in memory.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PREDICATE_PATH = REPO_ROOT / "quality" / "sql" / "analysis_set.sql"

# The three labels the predicate can return. Named once so no assertion below
# has to spell one next to the column name.
SEALED = "sealed"
OPEN = "open"
EXCLUDED = "excluded"

# The frozen first line of the file. If this changes, the predicate was edited
# after the tag, which SOP rule 0.5.6 sends to DEVIATIONS.md instead.
FROZEN_HEADER = (
    "-- ANALYSIS SET v1. OWNER DECISION 2026-09-22. Frozen at tag prereg-v1. Do not edit after."
)

D = dt.date.fromisoformat


def predicate_text() -> str:
    """The predicate file, read whole. It is nine lines and one expression."""
    return PREDICATE_PATH.read_text(encoding="utf-8")


def classify(rows: list[tuple[int, str, dt.date | None]]) -> list[str]:
    """Run the frozen predicate over ``rows`` in DuckDB and return its labels.

    ``rows`` are ``(season, game_type, official_date)``. The date column is a
    real DATE, because the predicate compares against a DATE literal and a
    string comparison would sort 2026-09-9 after 2026-09-22.
    """
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE game (season INTEGER, game_type VARCHAR, official_date DATE)")
        con.executemany("INSERT INTO game VALUES (?, ?, ?)", [list(r) for r in rows])
        result = con.execute(f"SELECT {predicate_text()} FROM game")
        assert result.description is not None
        # The predicate aliases itself; every caller in the warehouse selects it
        # by that name.
        assert result.description[0][0] == "analysis_set"
        return [row[0] for row in result.fetchall()]
    finally:
        con.close()


def test_predicate_file_exists_and_is_frozen() -> None:
    assert PREDICATE_PATH.is_file(), f"{PREDICATE_PATH} is the one place the rule lives"
    text = predicate_text()
    assert text.splitlines()[0] == FROZEN_HEADER
    # One expression, not a script: no statement separator, one CASE, one END.
    assert ";" not in text
    assert text.count("CASE") == 1
    assert text.count("END AS") == 1


# --------------------------------------------------------------- the UT-16 four
UT16_CASES = [
    ("regular season on the seal date", 2026, "R", D("2026-09-22"), SEALED),
    ("world series, date irrelevant", 2026, "W", D("2026-10-28"), SEALED),
    ("regular season one day before", 2026, "R", D("2026-09-21"), OPEN),
    ("spring training", 2026, "S", D("2026-03-05"), EXCLUDED),
]


@pytest.mark.parametrize(
    ("label", "season", "game_type", "official_date", "expected"),
    UT16_CASES,
    ids=[c[0] for c in UT16_CASES],
)
def test_ut16_four_cases(
    label: str,
    season: int,
    game_type: str,
    official_date: dt.date,
    expected: str,
) -> None:
    assert classify([(season, game_type, official_date)]) == [expected]


# ------------------------------------------------------------- scope and R-29
EXTRA_CASES = [
    # Postseason 2026, every round, including a date before the seal date. The
    # date branch is not what seals these; the game-type branch is.
    ("wild card", 2026, "F", D("2026-09-29"), SEALED),
    ("division series", 2026, "D", D("2026-10-05"), SEALED),
    ("championship series", 2026, "L", D("2026-10-14"), SEALED),
    ("postseason with an impossible early date", 2026, "D", D("2026-04-01"), SEALED),
    # Regular season 2026, both sides of the boundary and the last scheduled day.
    ("day after the seal date", 2026, "R", D("2026-09-23"), SEALED),
    ("last scheduled regular-season day", 2026, "R", D("2026-09-27"), SEALED),
    ("opening day", 2026, "R", D("2026-03-26"), OPEN),
    # Scope: 2026 only. Prior seasons are training data, postseason included.
    ("2025 world series", 2025, "W", D("2025-10-29"), OPEN),
    ("2025 late regular season", 2025, "R", D("2025-09-25"), OPEN),
    ("2024 regular season", 2024, "R", D("2024-09-24"), OPEN),
    # R-29. The 2025 regular season opened 2025-03-18 in Tokyo, before spring
    # training ended 2025-03-25, and spring 2025 ran an ABS trial in some parks.
    # A date-only filter would have put both of these in the same bucket.
    ("2025 Tokyo opener, regular season", 2025, "R", D("2025-03-18"), OPEN),
    ("2025 spring game after that opener", 2025, "S", D("2025-03-20"), EXCLUDED),
    ("2024 Seoul opener, regular season", 2024, "R", D("2024-03-20"), OPEN),
    ("2024 spring game after that opener", 2024, "S", D("2024-03-24"), EXCLUDED),
    # Excluded types are excluded in every season, sealed window or not.
    ("all-star game", 2026, "A", D("2026-07-14"), EXCLUDED),
    ("exhibition inside the sealed window", 2026, "E", D("2026-09-24"), EXCLUDED),
    ("spring training, prior season", 2019, "S", D("2019-03-01"), EXCLUDED),
]


@pytest.mark.parametrize(
    ("label", "season", "game_type", "official_date", "expected"),
    EXTRA_CASES,
    ids=[c[0] for c in EXTRA_CASES],
)
def test_scope_and_leakage(
    label: str,
    season: int,
    game_type: str,
    official_date: dt.date,
    expected: str,
) -> None:
    assert classify([(season, game_type, official_date)]) == [expected]


def test_batch_classification_is_row_wise() -> None:
    """The predicate is an expression, so a batch is the same as row by row."""
    rows = [(s, g, d) for _, s, g, d, _ in UT16_CASES + EXTRA_CASES]
    expected = [e for *_, e in UT16_CASES + EXTRA_CASES]
    assert classify(rows) == expected


def test_null_official_date_is_not_sealed() -> None:
    """A 2026 regular-season game with no officialDate falls through to open.

    SQL three-valued logic: the date comparison on NULL is NULL, so the sealed
    branch does not fire and the row lands in the open set. That is a leak path,
    and the fix is upstream, not here: the predicate is frozen at prereg-v1 and
    `officialDate` is NOT NULL in the data contract and in `dim_game`. This test
    exists so the behaviour is written down rather than discovered later.
    """
    assert classify([(2026, "R", None)]) == [OPEN]
    # A postseason game is sealed by its type, with or without a date.
    assert classify([(2026, "W", None)]) == [SEALED]
