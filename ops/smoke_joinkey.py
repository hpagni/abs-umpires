"""Smoke check 6: the join-key trap, offline. SOP step W1.15.

The trap. Statcast ``pitch_number`` counts every pitch slot in an at-bat,
including the ``automatic_ball`` rows that carry no tracking data. The Stats API
``playEvents[].pitchNumber`` counts only ``isPitch`` events, repeats the previous
number on a ``no_pitch``, and is 0 on an intentional walk. Keying a join on
``pitchNumber`` therefore matches the wrong rows and drops real ones, with no
error. SOP step W2.13 records the two shapes in game 776311 that break it.

``absump.joinkey`` implements the corrected key: a pitch slot is an event with
``isPitch == true`` or ``type == "no_pitch"``, counted in ``index`` order,
restarting at 1 each at-bat. ``absump.joinkey.naive_pitch_keys`` is the bug,
written down once, so it can be asserted to false-match.

This check asserts both sides on a fixture. It reads no feed from the lake, makes
no request, and is safe to re-run.

THE FIXTURE. SOP W1.15 names ``tests/fixtures/synthetic_feed_no_pitch.json``.
That path is owned by the fixtures step, not by W1.15, and this script does not
write outside ``ops/`` and ``data/tmp/``. So: the named fixture is used when it
is present, and when it is absent an equivalent feed is built here, written to
``data/tmp/smoke/synthetic_feed_no_pitch.json``, and the substitution is printed
on its own line rather than hidden. The built feed carries the three shapes W2.13
records and nothing from any real response: no tracking data, no player, no name.

Run: uv run --locked python ops/smoke_joinkey.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from absump.joinkey import (  # noqa: E402
    at_bat_number,
    game_pitch_keys,
    is_key_event,
    naive_pitch_keys,
    pitch_keys,
)

SOP_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "synthetic_feed_no_pitch.json"
FALLBACK_FIXTURE = REPO_ROOT / "data" / "tmp" / "smoke" / "synthetic_feed_no_pitch.json"

# Synthetic. Seven digits, matches no real game.
GAME_PK = 7460002


def _pitch(index: int, pitch_number: int, code: str, description: str) -> dict[str, Any]:
    return {
        "index": index,
        "isPitch": True,
        "type": "pitch",
        "pitchNumber": pitch_number,
        "details": {"call": {"code": code, "description": description}},
    }


def _no_pitch(index: int, pitch_number: int, code: str, description: str) -> dict[str, Any]:
    return {
        "index": index,
        "isPitch": False,
        "type": "no_pitch",
        "pitchNumber": pitch_number,
        "details": {"call": {"code": code, "description": description}},
    }


def _other(index: int, kind: str) -> dict[str, Any]:
    return {"index": index, "isPitch": False, "type": kind}


def build_feed() -> dict[str, Any]:
    """A GUMBO-shaped feed carrying the three shapes SOP W2.13 records."""
    # at-bat 1: three pitches, plus a pickoff and a stepoff that are not slots.
    plain = {
        "about": {"atBatIndex": 0},
        "playEvents": [
            _pitch(0, 1, "C", "Called Strike"),
            _other(1, "pickoff"),
            _pitch(2, 2, "B", "Ball"),
            _other(3, "stepoff"),
            _pitch(4, 3, "X", "In play, out(s)"),
        ],
    }
    # at-bat 2: the pitch timer violation. A no_pitch repeats pitchNumber 4.
    timer = {
        "about": {"atBatIndex": 1},
        "playEvents": [
            _pitch(0, 1, "C", "Called Strike"),
            _pitch(1, 2, "B", "Ball"),
            _pitch(2, 3, "S", "Swinging Strike"),
            _other(3, "action"),
            _pitch(4, 4, "F", "Foul"),
            _no_pitch(5, 4, "VP", "Automatic Ball - Pitcher Pitch Timer Violation"),
            _pitch(6, 5, "E", "In play, run(s)"),
        ],
    }
    # at-bats 77 and 81: four no_pitch events, every pitchNumber 0.
    walks = [
        {
            "about": {"atBatIndex": ab_index},
            "playEvents": [_no_pitch(i, 0, "VB", "Automatic Ball - Intentional") for i in range(4)],
        }
        for ab_index in (76, 80)
    ]
    return {
        "gameData": {"game": {"pk": GAME_PK}},
        "liveData": {"plays": {"allPlays": [plain, timer, *walks]}},
    }


def load_feed() -> tuple[dict[str, Any], Path, bool]:
    if SOP_FIXTURE.is_file():
        return json.loads(SOP_FIXTURE.read_text(encoding="utf-8")), SOP_FIXTURE, False
    feed = build_feed()
    FALLBACK_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FALLBACK_FIXTURE.write_text(json.dumps(feed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return feed, FALLBACK_FIXTURE, True


def _play_by_at_bat(feed: dict[str, Any], number: int) -> dict[str, Any]:
    for play in feed["liveData"]["plays"]["allPlays"]:
        if at_bat_number(play) == number:
            return play
    raise KeyError(f"no play with at_bat_number {number} in the fixture")


def main() -> int:
    feed, path, substituted = load_feed()
    if substituted:
        print(
            f"smoke-joinkey: {SOP_FIXTURE.relative_to(REPO_ROOT)} is absent, so an equivalent "
            f"feed was built at {path.relative_to(REPO_ROOT)}"
        )

    failures: list[str] = []

    # 1. action, pickoff and stepoff are not pitch slots. isPitch is read with
    #    `is True`, so a string or a null is not silently counted.
    for kind in ("action", "pickoff", "stepoff"):
        if is_key_event({"index": 0, "isPitch": False, "type": kind}):
            failures.append(f"{kind} was counted as a pitch slot")
    if is_key_event({"index": 0, "isPitch": "true", "type": "pitch"}):
        failures.append('isPitch == "true" (a string) was counted as a pitch slot')

    # 2. Every at-bat's slots are gap-free 1..n, in index order.
    total_slots = 0
    for play in feed["liveData"]["plays"]["allPlays"]:
        slots = [key[2] for key, _ in pitch_keys(play, GAME_PK)]
        if slots != list(range(1, len(slots) + 1)):
            failures.append(f"at-bat {at_bat_number(play)} slots are {slots}, not gap-free from 1")
        total_slots += len(slots)

    # 3. The pitch timer violation: six slots, and the naive key collides.
    timer_play = _play_by_at_bat(feed, 2)
    timer_slots = [key for key, _ in pitch_keys(timer_play, GAME_PK)]
    timer_naive = [key for key, _ in naive_pitch_keys(timer_play, GAME_PK)]
    if len(timer_slots) != 6:
        failures.append(f"at-bat 2 has {len(timer_slots)} slots, expected 6")
    if len(set(timer_naive)) != 5:
        failures.append(
            f"at-bat 2 naive key gives {len(set(timer_naive))} distinct keys, expected 5"
        )
    if len(set(timer_naive)) >= len(timer_slots):
        failures.append("at-bat 2 naive key did not collide, so the trap is not reproduced")

    # 4. The intentional walks: four slots each, and the naive key collapses
    #    all four onto pitchNumber 0.
    for number in (77, 81):
        walk = _play_by_at_bat(feed, number)
        slots = [key for key, _ in pitch_keys(walk, GAME_PK)]
        naive = {key for key, _ in naive_pitch_keys(walk, GAME_PK)}
        if len(slots) != 4:
            failures.append(f"at-bat {number} has {len(slots)} slots, expected 4")
        if len(naive) != 1:
            failures.append(f"at-bat {number} naive key gives {len(naive)} keys, expected 1")
        if naive != {(GAME_PK, number, 0)}:
            failures.append(f"at-bat {number} naive key is {sorted(naive)}, expected slot 0")

    # 5. Whole-feed: the corrected key is one key per slot, the naive key is not.
    corrected = [key for key, _, _ in game_pitch_keys(feed)]
    if len(corrected) != total_slots or len(set(corrected)) != total_slots:
        failures.append(
            f"whole feed: {len(corrected)} keys, {len(set(corrected))} distinct, "
            f"{total_slots} slots"
        )
    naive_all = {
        key
        for play in feed["liveData"]["plays"]["allPlays"]
        for key, _ in naive_pitch_keys(play, GAME_PK)
    }
    if len(naive_all) >= total_slots:
        failures.append(
            f"whole feed: naive key gives {len(naive_all)} distinct keys against "
            f"{total_slots} slots, so it did not lose a row"
        )

    # 6. game_pk comes from the feed's own statement, never from the file name.
    if corrected and {key[0] for key in corrected} != {GAME_PK}:
        failures.append("game_pk was not read from gameData.game.pk")

    if failures:
        print("smoke-joinkey FAIL:")
        for line in failures:
            print(f"  {line}")
        return 1

    print(
        f"smoke-joinkey OK: {total_slots} pitch slots over 4 at-bats, corrected key gives "
        f"{len(set(corrected))} distinct keys, naive key gives {len(naive_all)} and loses "
        f"{total_slots - len(naive_all)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
