"""The corrected pitch key. SOP step W2.13.

One at-bat in a GUMBO feed is a list of `playEvents`. Only some of them are
pitch slots. The API's own `playEvents[].pitchNumber` cannot be used as the key
because it counts only `isPitch` events and repeats the previous number on a
`no_pitch`, while Statcast `pitch_number` counts every pitch slot including the
`automatic_ball` rows. Keying on `pitchNumber` therefore joins the wrong rows
and drops real ones, silently.

The rule, and the only rule this module implements: a pitch slot is an event
with `isPitch == true` **or** `type == "no_pitch"`. `action`, `pickoff` and
`stepoff` are ignored. Events are read in `index` order and the slot counter
restarts at 1 for every at-bat.

Two shapes in real data show why both halves of the disjunction are needed.

Game 776311, at-bat 2 (the Schwarber home run). API index 0 to 2 are pitches 1
to 3, index 3 is an `action`, index 4 is pitch 4 Foul, index 5 is a `no_pitch`
carrying `pitchNumber` 4 and call code VP "Automatic Ball - Pitcher Pitch Timer
Violation", index 6 is pitch 5 "In play, run(s)". The Statcast CSV for the same
at-bat runs 1, 2, 3, 4, 5 (`automatic_ball`, blank `plate_x`), 6
(`hit_into_play`, `events == home_run`). Under the naive key Statcast
`pitch_number` 5 joins to the API's home-run pitch and the real home-run row is
dropped.

Game 776311, at-bats 77 and 81 (`atBatIndex` 76 and 80). Four `no_pitch` events
each, every one with `pitchNumber` 0 and `details.call.code` VB "Automatic Ball
- Intentional", and zero `isPitch` events, against four Statcast rows each. The
naive key collapses all four to one.

Counts on the four games the SOP verified, corrected key, api / csv / matched:
776311 MLB 2025 331 / 331 / 331, where the naive key gave 322 / 331 / 322 with
nine csv-only rows and one false match; 824466 MLB 2026 281 / 281 / 281;
822925 MLB 2026 225 / 225 / 225; 753191 AAA 2024 224 / 224 / 224.

`naive_pitch_keys` is here on purpose. It is the bug, written down once, so
UT-02 can assert that it false-matches and the bug cannot be reintroduced
without a test going red.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

__all__ = [
    "NO_PITCH",
    "PitchKey",
    "at_bat_number",
    "game_pitch_keys",
    "is_key_event",
    "naive_pitch_keys",
    "pitch_keys",
]

#: The `playEvents[].type` value that is a pitch slot without being a pitch.
#: An automatic ball, whether from a timer violation or an intentional walk,
#: occupies a slot in the Statcast numbering and carries no tracking data.
NO_PITCH: Final[str] = "no_pitch"

#: `(game_pk, at_bat_number, pitch_slot)`. `at_bat_number` is one-based,
#: `atBatIndex + 1`. `pitch_slot` is one-based within the at-bat.
PitchKey = tuple[int, int, int]


def is_key_event(event: Mapping[str, Any]) -> bool:
    """True when this `playEvents` entry occupies a pitch slot.

    `isPitch` is read with `is True` rather than for truthiness so that a
    missing key, a null or the string "true" is not silently counted. `action`,
    `pickoff` and `stepoff` events return False.
    """
    return event.get("isPitch") is True or event.get("type") == NO_PITCH


def at_bat_number(play: Mapping[str, Any]) -> int:
    """The one-based at-bat number for one play: `about.atBatIndex + 1`.

    Statcast `at_bat_number` is one-based and the feed's `atBatIndex` is
    zero-based. This conversion is the reason the two sources line up at all,
    so it lives in one function and is never written inline.
    """
    return int(play["about"]["atBatIndex"]) + 1


def pitch_keys(
    play: Mapping[str, Any], game_pk: int
) -> Iterator[tuple[PitchKey, Mapping[str, Any]]]:
    """Yield `((game_pk, at_bat_number, pitch_slot), event)` for one play.

    Events are sorted by their own `index` field, not by list order, because
    the slot number is defined by the order the events happened in. The counter
    increments on `isPitch == true` or `type == "no_pitch"` and on nothing else.
    """
    ab = at_bat_number(play)
    n = 0
    for ev in sorted(play["playEvents"], key=lambda e: e["index"]):
        if is_key_event(ev):
            n += 1
            yield (int(game_pk), ab, n), ev


def naive_pitch_keys(
    play: Mapping[str, Any], game_pk: int
) -> Iterator[tuple[PitchKey, Mapping[str, Any]]]:
    """The broken key: `playEvents[].pitchNumber` used as the slot.

    Kept so that UT-02 can assert it produces fewer distinct keys than there
    are pitch slots on the two shapes that break it. Nothing in the pipeline
    calls this. A caller that does is writing the bug back in.
    """
    ab = at_bat_number(play)
    for ev in sorted(play["playEvents"], key=lambda e: e["index"]):
        if is_key_event(ev):
            yield (int(game_pk), ab, int(ev.get("pitchNumber") or 0)), ev


def game_pitch_keys(
    feed: Mapping[str, Any],
) -> Iterator[tuple[PitchKey, Mapping[str, Any], Mapping[str, Any]]]:
    """Yield `(key, play, event)` for every pitch slot in one whole feed.

    `game_pk` is read from `gameData.game.pk`, the feed's own statement of
    which game it is, never from the file name.
    """
    game_pk = int(feed["gameData"]["game"]["pk"])
    plays: Sequence[Mapping[str, Any]] = feed["liveData"]["plays"]["allPlays"]
    for play in plays:
        for key, event in pitch_keys(play, game_pk):
            yield key, play, event
