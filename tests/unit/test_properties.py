"""Property tests. SOP section 6.2, step W9.5.

SOP section 6.2 closes the unit pack with two property tests under hypothesis:
the counter is monotone and gap-free for any random event sequence, and the
re-projection is an involution for any `vy0` in [-150, -110] and `ay` in
[20, 40].

The counter half is here, over `absump.joinkey.pitch_keys`. The re-projection
half is in `tests/unit/test_geometry_reproject.py`, beside the UT-11 and UT-12
assertions it belongs with.

The example-based counter tests in `test_joinkey.py` fix two real shapes from
game 776311, the pitch timer violation and the four-event intentional walk.
These generate the shape instead: any interleaving of pitches, `no_pitch`
slots, `action`, `pickoff` and `stepoff` events, in any list order, with the
`index` field carrying the true order. The invariants asserted are the ones
UT-01 states, so a regression in the counter fails here on a sequence nobody
wrote down.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from absump.joinkey import NO_PITCH, is_key_event, pitch_keys

GAME_PK = 999_002

# The five `playEvents` kinds the counter has to tell apart. The first two
# occupy a pitch slot; the last three do not.
KEY_KINDS = ("pitch", NO_PITCH)
SKIP_KINDS = ("action", "pickoff", "stepoff")

kinds = st.lists(st.sampled_from(KEY_KINDS + SKIP_KINDS), min_size=0, max_size=40)


def _event(index: int, kind: str) -> dict[str, Any]:
    """One `playEvents` entry of the given kind, at the given true position."""
    event: dict[str, Any] = {"index": index, "type": kind}
    if kind == "pitch":
        event["isPitch"] = True
        event["type"] = "pitch"
        event["pitchNumber"] = index + 1
    elif kind == NO_PITCH:
        # A `no_pitch` slot carries no tracking data and repeats the previous
        # number, which is exactly why the naive key breaks on it.
        event["isPitch"] = False
        event["pitchNumber"] = index
    else:
        event["isPitch"] = False
    return event


def _play(kind_list: list[str], at_bat_index: int, rotation: int) -> dict[str, Any]:
    """A play whose `playEvents` list is rotated away from `index` order."""
    events = [_event(i, kind) for i, kind in enumerate(kind_list)]
    if events:
        cut = rotation % len(events)
        events = events[cut:] + events[:cut]
    return {"about": {"atBatIndex": at_bat_index}, "playEvents": events}


@given(
    kind_list=kinds,
    at_bat_index=st.integers(min_value=0, max_value=69),
    rotation=st.integers(min_value=0, max_value=39),
)
@settings(max_examples=300, deadline=None)
def test_the_counter_is_monotone_and_gap_free(
    kind_list: list[str], at_bat_index: int, rotation: int
) -> None:
    """UT-01 as a property: 1, 2, 3, ... with no repeat and no gap."""
    play = _play(kind_list, at_bat_index, rotation)
    slots = [key[2] for key, _ in pitch_keys(play, GAME_PK)]
    expected = list(range(1, sum(1 for k in kind_list if k in KEY_KINDS) + 1))
    assert slots == expected


@given(
    kind_list=kinds,
    at_bat_index=st.integers(min_value=0, max_value=69),
    rotation=st.integers(min_value=0, max_value=39),
)
@settings(max_examples=300, deadline=None)
def test_the_counter_ignores_every_non_slot_event(
    kind_list: list[str], at_bat_index: int, rotation: int
) -> None:
    """`action`, `pickoff` and `stepoff` never take a slot, in any interleaving."""
    play = _play(kind_list, at_bat_index, rotation)
    taken = [event for _, event in pitch_keys(play, GAME_PK)]
    assert all(is_key_event(event) for event in taken)
    assert len(taken) == sum(1 for k in kind_list if k in KEY_KINDS)


@given(
    kind_list=kinds,
    at_bat_index=st.integers(min_value=0, max_value=69),
    rotation=st.integers(min_value=0, max_value=39),
)
@settings(max_examples=300, deadline=None)
def test_the_key_carries_the_game_and_the_one_based_at_bat(
    kind_list: list[str], at_bat_index: int, rotation: int
) -> None:
    """Every key is `(game_pk, atBatIndex + 1, slot)`, and the keys are distinct."""
    play = _play(kind_list, at_bat_index, rotation)
    keys = [key for key, _ in pitch_keys(play, GAME_PK)]
    assert all(key[0] == GAME_PK for key in keys)
    assert all(key[1] == at_bat_index + 1 for key in keys)
    assert len(set(keys)) == len(keys)


@given(
    kind_list=kinds,
    at_bat_index=st.integers(min_value=0, max_value=69),
    rotation=st.integers(min_value=0, max_value=39),
)
@settings(max_examples=300, deadline=None)
def test_the_counter_reads_index_order_not_list_order(
    kind_list: list[str], at_bat_index: int, rotation: int
) -> None:
    """Rotating the list leaves the slot assignment untouched."""
    ordered = _play(kind_list, at_bat_index, 0)
    rotated = _play(kind_list, at_bat_index, rotation)
    by_index = {key: event["index"] for key, event in pitch_keys(ordered, GAME_PK)}
    rotated_by_index = {key: event["index"] for key, event in pitch_keys(rotated, GAME_PK)}
    assert by_index == rotated_by_index
    # Slot order follows `index` order, which is the point of the sort.
    indices = [by_index[key] for key in sorted(by_index)]
    assert indices == sorted(indices)
