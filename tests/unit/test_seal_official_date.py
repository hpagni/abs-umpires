"""`assert_unsealed` derives the date column itself, and a datetime fails closed.

Two findings, one root. The module's own rule, stated at `paths.py` line 24, is
that the date is always the official date and never the game date. Until now
nothing enforced it at the boundary check:

  * `assert_unsealed(df, date_col)` took the column NAME from the caller and
    applied the boundary to whatever it named. A future caller handing it the
    typed game-date column would have partitioned on the game date with nothing
    to stop it.
  * a game-date STRING already failed closed, because `paths.as_official_date`
    refuses an ISO timestamp. A game-date DATETIME did not: it was truncated to
    its UTC calendar day and silently accepted. Game 825030 is the standing
    example -- official date 2026-09-15, game date 2026-09-16T01:40:00Z -- so the
    truncation can move a row to the other side of the boundary.

The boundary date is never written here. It is read from the module, so this
file states no date rule of its own and cannot drift from the one in the config.
"""

from __future__ import annotations

import datetime as dt

import pytest

from absump import seal
from absump.paths import SealViolation

BOUNDARY = seal._first_held_out_date()
OPEN_DAY = (BOUNDARY - dt.timedelta(days=1)).isoformat()
HELD_DAY = BOUNDARY.isoformat()

# The shape of game 825030: an official date one day earlier than the UTC
# calendar day of its first pitch. Built from the boundary, not from a feed.
LATE_GAME_OFFICIAL = (BOUNDARY - dt.timedelta(days=7)).isoformat()
LATE_GAME_UTC = dt.datetime.combine(BOUNDARY - dt.timedelta(days=6), dt.time(1, 40), tzinfo=dt.UTC)


def test_the_column_is_derived_when_none_is_named() -> None:
    seal.assert_unsealed({"official_date": [OPEN_DAY, OPEN_DAY]})
    with pytest.raises(SealViolation):
        seal.assert_unsealed({"official_date": [OPEN_DAY, HELD_DAY]})


def test_the_camel_case_spelling_is_derived_too() -> None:
    seal.assert_unsealed({"officialDate": [OPEN_DAY]})
    with pytest.raises(SealViolation):
        seal.assert_unsealed({"officialDate": [HELD_DAY]})


def test_a_caller_chosen_game_date_column_is_refused() -> None:
    """The refutation, directly. A caller cannot nominate the column."""
    frame = {"game_date_utc": [OPEN_DAY], "official_date": [OPEN_DAY]}
    with pytest.raises(SealViolation, match="not an official-date column"):
        seal.assert_unsealed(frame, "game_date_utc")
    with pytest.raises(SealViolation, match="not an official-date column"):
        seal.assert_unsealed({"date": [OPEN_DAY]}, "date")


def test_the_official_column_is_chosen_even_when_a_game_date_sits_beside_it() -> None:
    """Both columns present, the game date past the boundary, the official date
    inside the open window. The frame is open, because the official date is."""
    frame = {"official_date": [LATE_GAME_OFFICIAL], "game_date_utc": [HELD_DAY]}
    seal.assert_unsealed(frame)


def test_a_frame_with_no_official_date_column_is_refused() -> None:
    with pytest.raises(SealViolation, match="no official-date column"):
        seal.assert_unsealed({"game_date_utc": [OPEN_DAY]})


def test_two_official_date_spellings_at_once_are_refused() -> None:
    """Ambiguity fails closed rather than picking one."""
    with pytest.raises(SealViolation, match="ambiguous"):
        seal.assert_unsealed({"official_date": [OPEN_DAY], "officialDate": [OPEN_DAY]})


def test_a_named_column_that_is_absent_still_raises() -> None:
    with pytest.raises(ValueError, match="is not a column"):
        seal.assert_unsealed({"officialDate": [OPEN_DAY]}, "official_date")


def test_a_game_date_string_fails_closed() -> None:
    """This already held. It is pinned so it keeps holding."""
    with pytest.raises(ValueError, match="not an ISO"):
        seal.assert_unsealed({"official_date": [LATE_GAME_UTC.isoformat()]})


def test_a_datetime_fails_closed_exactly_like_the_string() -> None:
    """The refutation, directly. Truncation to the UTC day is not a coercion."""
    with pytest.raises(SealViolation, match="datetime"):
        seal.assert_unsealed({"official_date": [LATE_GAME_UTC]})
    with pytest.raises(SealViolation, match="datetime"):
        seal.assert_unsealed({"official_date": [dt.datetime(2026, 4, 1, 12, 0)]})


def test_a_plain_date_object_is_still_accepted() -> None:
    """A date is not a datetime. The strictness is about the timestamp only."""
    seal.assert_unsealed({"official_date": [BOUNDARY - dt.timedelta(days=30)]})
    with pytest.raises(SealViolation):
        seal.assert_unsealed({"official_date": [BOUNDARY]})


def test_a_null_date_is_still_held_out() -> None:
    """Unchanged behaviour, restated: a date that cannot be shown to be open is
    treated as being on the far side."""
    with pytest.raises(SealViolation):
        seal.assert_unsealed({"official_date": [OPEN_DAY, None]})


def test_the_held_out_reader_derives_the_same_column() -> None:
    """`sealed_only` refuses first, because the gate is shut. The point is that
    it refuses for the gate's reason and not for a column it was handed."""
    with pytest.raises(SealViolation, match="closed"):
        seal.sealed_only({"official_date": [HELD_DAY]})


def test_a_lazy_frame_is_handled_without_resolving_its_schema_twice() -> None:
    """polars asks for `collect_schema()`, not `.columns`, on a LazyFrame. The
    derivation goes through that door, so the guard costs no warning and no
    second schema resolution on the frames the fits actually pass it."""
    import warnings

    import polars as pl

    frame = pl.LazyFrame({"official_date": [OPEN_DAY], "game_date_utc": [HELD_DAY]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        seal.assert_unsealed(frame)
        with pytest.raises(SealViolation):
            seal.assert_unsealed(pl.LazyFrame({"official_date": [HELD_DAY]}))
