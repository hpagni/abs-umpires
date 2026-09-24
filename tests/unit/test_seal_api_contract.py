"""A named test for each public function of `absump.seal`. SOP section 6.2, W9.5.

`absump.seal` exports four public functions: `assert_unsealed`, `sealed_only`,
`frame` and `unlock_report`. All four were exercised before this file existed,
in `test_seal_official_date.py`, `test_seal_unlock_conjuncts.py` and
`test_seal_unseal_gate.py`, but under test names that describe the behaviour
rather than the function, so `tests/unit/test_coverage_contract.py` could not
see them. This file carries one test per function, named after the function,
and asserts the part of its contract that the behaviour files do not: the
argument checks at the door.

Nothing here opens the seal. `_unlocked` is monkeypatched in the two places
that need a positive branch, and the real gate is left shut. Nothing here
reaches the network or the warehouse: `unlock_report`'s six probes are replaced
with fixed values, and `frame` is only ever driven to its refusals, which all
fire before any database connection is made.

The boundary date is read from the module. This file states no date rule of its
own, so it cannot drift from `config/seal.yml`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from absump import seal
from absump.paths import SealViolation

BOUNDARY = seal._first_held_out_date()
OPEN_DAY = (BOUNDARY - dt.timedelta(days=1)).isoformat()
HELD_DAY = BOUNDARY.isoformat()


def test_assert_unsealed() -> None:
    """Returns None inside the open window, raises `SealViolation` outside it."""
    assert seal.assert_unsealed({"official_date": [OPEN_DAY, OPEN_DAY]}) is None
    with pytest.raises(SealViolation) as raised:
        seal.assert_unsealed({"official_date": [OPEN_DAY, HELD_DAY]})
    message = str(raised.value)
    assert HELD_DAY in message, message
    assert "1 of 2 rows" in message, message
    # The column is derived, never taken from the caller on trust.
    with pytest.raises(SealViolation, match="not an official-date column"):
        seal.assert_unsealed({"game_date_utc": [OPEN_DAY]}, "game_date_utc")


def test_sealed_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuses while the gate is shut, and returns only held-out rows when open."""
    rows = {"official_date": [OPEN_DAY, HELD_DAY, OPEN_DAY], "n": [1, 2, 3]}
    with pytest.raises(SealViolation) as raised:
        seal.sealed_only(rows)
    assert "the held-out set is closed" in str(raised.value)

    monkeypatch.setattr(seal, "_unlocked", lambda: True)
    kept = seal.sealed_only(rows)
    assert kept == {"official_date": [HELD_DAY], "n": [2]}
    # The input is not mutated by the filter.
    assert rows["n"] == [1, 2, 3]


def test_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checks `name` and `set` before it touches a database, and stays shut."""
    with pytest.raises(ValueError, match="is not one of"):
        seal.frame("no_such_view")
    with pytest.raises(ValueError, match="is not 'open'"):
        seal.frame("pitch", set="everything")
    with pytest.raises(SealViolation) as raised:
        seal.frame("pitch", set=seal.HELD_OUT)
    # The view name is built from the module's own label, never written down
    # here: GD-04 rule 2 fails on that name anywhere outside the two allowlisted
    # files, and the assertion is exact either way.
    assert f"v_pitch_{seal.HELD_OUT} is closed" in str(raised.value)

    class _Cursor:
        def __init__(self, sql: str) -> None:
            self.sql = sql

        def pl(self) -> str:
            return self.sql

    class _Connection:
        def execute(self, sql: str) -> _Cursor:
            return _Cursor(sql)

    # The open branch builds the view name here and nowhere else.
    for name in seal.VIEWS:
        assert seal.frame(name, con=_Connection()) == f"SELECT * FROM v_{name}_open"


def test_unlock_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reports the six preconditions, and names the ones that failed."""
    monkeypatch.setattr(seal, "_prereg_tag", lambda: "prereg-test")
    monkeypatch.setattr(seal, "_tag_exists", lambda tag: True)
    monkeypatch.setattr(seal, "_is_ancestor", lambda earlier, later: True)
    monkeypatch.setattr(seal, "_worktree_clean", lambda: True)
    monkeypatch.setattr(seal, "_prereg_hash_matches", lambda: True)
    monkeypatch.setattr(seal, "_tag_is_pushed", lambda remote=seal._REMOTE: True)

    monkeypatch.delenv(seal.UNLOCK_ENV, raising=False)
    shut: dict[str, Any] = seal.unlock_report()
    assert shut["ok"] is False
    assert len(shut["checks"]) == 6
    assert shut["failed"] == [f"{seal.UNLOCK_ENV}=1 in this shell"]

    monkeypatch.setenv(seal.UNLOCK_ENV, "1")
    open_report: dict[str, Any] = seal.unlock_report()
    assert open_report["ok"] is True
    assert open_report["failed"] == []
    assert list(open_report["checks"]) == list(shut["checks"])


def test_the_real_gate_is_still_shut_after_this_file_runs() -> None:
    """No monkeypatch above leaks. The seal is shut in this repository."""
    assert seal._unlocked() is False
    with pytest.raises(SealViolation):
        seal.sealed_only({"official_date": [HELD_DAY]})
