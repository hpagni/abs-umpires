"""UT-01, UT-02, UT-03. The corrected pitch key. SOP step W2.13.

UT-01 the corrected counter: it increments on `isPitch == true` or
`type == "no_pitch"`, ignores `action`, `pickoff` and `stepoff`, restarts at 1
for every at-bat, and is gap-free.

UT-02 the naive key is asserted to false-match. `playEvents[].pitchNumber`
repeats the previous number on a `no_pitch` and is 0 on an intentional walk, so
it produces fewer distinct keys than there are pitch slots. The assertion is
that it is broken, so the bug cannot be reintroduced silently.

UT-03 an intentional walk yields four keys, one per `no_pitch` event, against
the four Statcast rows the same at-bat produces.

No feed from the lake is read. The ground truth is
`tests/fixtures/expected/pitch_keys.json` and the generated fixture beside it,
both written by `tests/fixtures/synth_feed.py`, plus the two event sequences
below. Those two are built here, event by event, to the shapes SOP W2.13
records for game 776311: the pitch timer violation in at-bat 2, and the
four-event intentional walks in at-bats 77 and 81. They carry no tracking data
and no player, so nothing from a real response is reproduced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from absump.joinkey import (
    at_bat_number,
    game_pitch_keys,
    is_key_event,
    naive_pitch_keys,
    pitch_keys,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"
GENERATED_FEED = FIXTURE_DIR / "generated" / "mlb_feed.json"
EXPECTED_KEYS = FIXTURE_DIR / "expected" / "pitch_keys.json"

# The synthetic game_pk the fixture generator uses.
FIXTURE_GAME_PK = 999001

# A game_pk that appears in no fixture, used where the value only has to travel
# through the key unchanged.
ANY_GAME_PK = 424242


# ---------------------------------------------------------------------------
# The two shapes, built here.
# ---------------------------------------------------------------------------


def _event(index: int, kind: str, *, is_pitch: bool, pitch_number: int | None, code: str) -> dict:
    event: dict[str, Any] = {
        "index": index,
        "type": kind,
        "isPitch": is_pitch,
        "details": {"call": {"code": code}},
    }
    if pitch_number is not None:
        event["pitchNumber"] = pitch_number
    return event


def _play(at_bat_index: int, events: list[dict]) -> dict:
    return {"about": {"atBatIndex": at_bat_index}, "playEvents": events}


# SOP W2.13, game 776311 at-bat 2: three pitches, an action, a fourth pitch, a
# no_pitch that repeats pitchNumber 4, then the fifth pitch. Six pitch slots,
# seven events. The events are deliberately out of list order so that the sort
# on `index` is exercised rather than assumed.
TIMER_VIOLATION_PLAY = _play(
    1,
    [
        _event(6, "pitch", is_pitch=True, pitch_number=5, code="E"),
        _event(0, "pitch", is_pitch=True, pitch_number=1, code="F"),
        _event(1, "pitch", is_pitch=True, pitch_number=2, code="B"),
        _event(2, "pitch", is_pitch=True, pitch_number=3, code="S"),
        _event(3, "action", is_pitch=False, pitch_number=None, code="AC"),
        _event(4, "pitch", is_pitch=True, pitch_number=4, code="F"),
        _event(5, "no_pitch", is_pitch=False, pitch_number=4, code="VP"),
    ],
)

# SOP W2.13, game 776311 at-bats 77 and 81: four no_pitch events, every one
# pitchNumber 0 and call code VB, and no isPitch event at all.
INTENTIONAL_WALK_PLAY = _play(
    76,
    [_event(i, "no_pitch", is_pitch=False, pitch_number=0, code="VB") for i in range(4)],
)

# The three event types that never occupy a pitch slot.
IGNORED_PLAY = _play(
    9,
    [
        _event(0, "action", is_pitch=False, pitch_number=None, code="AC"),
        _event(1, "pickoff", is_pitch=False, pitch_number=None, code="PO"),
        _event(2, "pitch", is_pitch=True, pitch_number=1, code="C"),
        _event(3, "stepoff", is_pitch=False, pitch_number=None, code="SO"),
        _event(4, "pitch", is_pitch=True, pitch_number=2, code="B"),
    ],
)


@pytest.fixture(scope="module")
def generated_feed() -> dict:
    if not GENERATED_FEED.exists():
        pytest.skip(f"{GENERATED_FEED} is absent; run tests/fixtures/synth_feed.py")
    return json.loads(GENERATED_FEED.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def expected_keys() -> dict:
    if not EXPECTED_KEYS.exists():
        pytest.skip(f"{EXPECTED_KEYS} is absent; run tests/fixtures/synth_feed.py")
    return json.loads(EXPECTED_KEYS.read_text(encoding="utf-8"))


def _key_string(key: tuple[int, int, int]) -> str:
    return "{}-{}-{}".format(*key)


# ---------------------------------------------------------------------------
# UT-01. The corrected counter.
# ---------------------------------------------------------------------------


def test_ut01_counter_matches_the_expected_keys(generated_feed, expected_keys) -> None:
    """Every corrected key in the ground-truth file, in order, and no other."""
    produced = [_key_string(key) for key, _play, _event in game_pitch_keys(generated_feed)]
    expected = [row["corrected_key"] for row in expected_keys["keys"]]
    assert produced == expected
    assert len(produced) == expected_keys["n_pitch_events"]
    assert len(set(produced)) == expected_keys["n_distinct_corrected_keys"]


def test_ut01_counter_is_monotone_and_gap_free(generated_feed) -> None:
    """Within one at-bat the slot runs 1, 2, 3 with no gap and no repeat."""
    by_at_bat: dict[tuple[int, int], list[int]] = {}
    for (game_pk, ab, slot), _play, _event in game_pitch_keys(generated_feed):
        by_at_bat.setdefault((game_pk, ab), []).append(slot)
    assert by_at_bat
    for slots in by_at_bat.values():
        assert slots == list(range(1, len(slots) + 1))


def test_ut01_counter_counts_a_no_pitch_slot() -> None:
    """The timer violation is a slot. Six slots from seven events."""
    keys = [key for key, _event in pitch_keys(TIMER_VIOLATION_PLAY, ANY_GAME_PK)]
    assert keys == [(ANY_GAME_PK, 2, n) for n in range(1, 7)]


def test_ut01_counter_ignores_action_pickoff_and_stepoff() -> None:
    """Only the two pitches in a five-event play occupy slots."""
    slots = [(key, ev["type"]) for key, ev in pitch_keys(IGNORED_PLAY, ANY_GAME_PK)]
    assert slots == [((ANY_GAME_PK, 10, 1), "pitch"), ((ANY_GAME_PK, 10, 2), "pitch")]


def test_ut01_counter_restarts_at_one_for_every_at_bat() -> None:
    """Two at-bats in one feed both start at slot 1."""
    feed = {
        "gameData": {"game": {"pk": ANY_GAME_PK}},
        "liveData": {"plays": {"allPlays": [TIMER_VIOLATION_PLAY, IGNORED_PLAY]}},
    }
    firsts = {}
    for (_pk, ab, slot), _play, _event in game_pitch_keys(feed):
        firsts.setdefault(ab, slot)
    assert firsts == {2: 1, 10: 1}


def test_ut01_counter_reads_events_in_index_order_not_list_order() -> None:
    """The fixture play is shuffled. Slot order follows `index`."""
    indexes = [ev["index"] for _key, ev in pitch_keys(TIMER_VIOLATION_PLAY, ANY_GAME_PK)]
    assert indexes == [0, 1, 2, 4, 5, 6]


# ---------------------------------------------------------------------------
# UT-02. The naive key false-matches.
# ---------------------------------------------------------------------------


def test_ut02_naive_key_loses_keys_on_the_fixture(generated_feed, expected_keys) -> None:
    """Fewer distinct naive keys than pitch slots, and the collision is named."""
    naive: list[str] = []
    for play in generated_feed["liveData"]["plays"]["allPlays"]:
        naive.extend(_key_string(key) for key, _ev in naive_pitch_keys(play, FIXTURE_GAME_PK))
    assert len(naive) == expected_keys["n_pitch_events"]
    assert len(set(naive)) == expected_keys["n_distinct_naive_keys"]
    assert len(set(naive)) < expected_keys["n_distinct_corrected_keys"]
    collided = {key for key in naive if naive.count(key) > 1}
    assert collided == set(expected_keys["naive_key_collisions"])


def test_ut02_naive_key_repeats_a_number_on_a_no_pitch() -> None:
    """The Foul and the timer violation collide on pitchNumber 4."""
    naive = [key for key, _ev in naive_pitch_keys(TIMER_VIOLATION_PLAY, ANY_GAME_PK)]
    corrected = [key for key, _ev in pitch_keys(TIMER_VIOLATION_PLAY, ANY_GAME_PK)]
    assert len(corrected) == 6
    assert len(naive) == 6
    assert len(set(naive)) == 5
    assert naive.count((ANY_GAME_PK, 2, 4)) == 2


def test_ut02_naive_key_collapses_the_intentional_walk() -> None:
    """Four slots, one naive key, because every pitchNumber is 0."""
    naive = {key for key, _ev in naive_pitch_keys(INTENTIONAL_WALK_PLAY, ANY_GAME_PK)}
    assert naive == {(ANY_GAME_PK, 77, 0)}


# ---------------------------------------------------------------------------
# UT-03. The intentional walk.
# ---------------------------------------------------------------------------


def test_ut03_intentional_walk_yields_four_keys() -> None:
    """Zero isPitch events, four no_pitch events, four keys."""
    events = INTENTIONAL_WALK_PLAY["playEvents"]
    assert sum(1 for ev in events if ev.get("isPitch") is True) == 0
    assert all(ev["details"]["call"]["code"] == "VB" for ev in events)
    keys = [key for key, _ev in pitch_keys(INTENTIONAL_WALK_PLAY, ANY_GAME_PK)]
    assert keys == [(ANY_GAME_PK, 77, n) for n in (1, 2, 3, 4)]


def test_ut03_intentional_walk_in_the_fixture(generated_feed, expected_keys) -> None:
    """The fixture's own intentional walk: four corrected keys, one naive key."""
    walk = generated_feed["liveData"]["plays"]["allPlays"][2]
    corrected = [key for key, _ev in pitch_keys(walk, FIXTURE_GAME_PK)]
    naive = {key for key, _ev in naive_pitch_keys(walk, FIXTURE_GAME_PK)}
    assert len(corrected) == 4
    assert len(naive) == 1
    expected = [row["corrected_key"] for row in expected_keys["keys"] if row["at_bat_number"] == 3]
    assert [_key_string(key) for key in corrected] == expected


# ---------------------------------------------------------------------------
# One named test per public function, for the W9.5 coverage contract.
# ---------------------------------------------------------------------------


def test_is_key_event() -> None:
    assert is_key_event({"isPitch": True, "type": "pitch"}) is True
    assert is_key_event({"isPitch": False, "type": "no_pitch"}) is True
    assert is_key_event({"isPitch": False, "type": "action"}) is False
    assert is_key_event({"type": "pickoff"}) is False
    assert is_key_event({"type": "stepoff"}) is False
    # Truthiness is not enough: only the boolean true counts.
    assert is_key_event({"isPitch": "true", "type": "pitch"}) is False
    assert is_key_event({"isPitch": 1, "type": "pitch"}) is False


def test_at_bat_number() -> None:
    assert at_bat_number({"about": {"atBatIndex": 0}}) == 1
    assert at_bat_number({"about": {"atBatIndex": 76}}) == 77


def test_pitch_keys() -> None:
    pairs = list(pitch_keys(IGNORED_PLAY, ANY_GAME_PK))
    assert [key for key, _ev in pairs] == [(ANY_GAME_PK, 10, 1), (ANY_GAME_PK, 10, 2)]
    assert [ev["index"] for _key, ev in pairs] == [2, 4]


def test_naive_pitch_keys() -> None:
    pairs = list(naive_pitch_keys(IGNORED_PLAY, ANY_GAME_PK))
    assert [key for key, _ev in pairs] == [(ANY_GAME_PK, 10, 1), (ANY_GAME_PK, 10, 2)]


def test_game_pitch_keys() -> None:
    feed = {
        "gameData": {"game": {"pk": ANY_GAME_PK}},
        "liveData": {"plays": {"allPlays": [INTENTIONAL_WALK_PLAY]}},
    }
    rows = list(game_pitch_keys(feed))
    assert [key for key, _p, _e in rows] == [(ANY_GAME_PK, 77, n) for n in (1, 2, 3, 4)]
    assert all(play is INTENTIONAL_WALK_PLAY for _key, play, _ev in rows)
