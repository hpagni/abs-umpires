"""The challenge table and its reconciliation. SOP step W2.16.

    uv run python -m absump.challenges --level mlb --season 2026 --procs 8
    uv run python -m absump.challenges --check --level mlb --season 2026

No network. The input is the stored GUMBO feed, the same bytes W2.13 reads:
`data/raw/statsapi/feed/sport={id}/season={yyyy}/date={yyyy-mm-dd}/
gamepk={pk}.json.zst`. The output is one interim Parquet dataset,
`feed_challenge`, plus two CSV reports under `out/tables/`.

THE UNION OF THREE LOCATIONS. A judgment-call review record sits in one of
three places in the feed, and every one of them is read, each record counted
once:

    allPlays[].playEvents[].reviewDetails      pitch level
    allPlays[].reviewDetails                   play level, at-bat-ending pitch
    reviewDetails.additionalReviews[]          a second review on either object

Measured on MLB 2026, 2,342 games: 7,608 pitch level, 2,559 play level, 1 in
`additionalReviews`, 10,168 in total. Measured on AAA 2024, 665 games:
1,524 pitch level, 526 play level, 82 in `additionalReviews`, 2,132 in total.
Dropping `additionalReviews` loses 1 MLB record and 82 AAA records, and one
MLB game stops reconciling, so the third location is not optional.

Only `reviewType == "MJ"` reaches the table. The other 34 review types in the
MLB 2026 corpus, 1,366 records led by MA 490, MF 386, MI 123 and NH 121, are
counted and dropped.

THE TWO `hasReview` FLAGS ARE READ INDEPENDENTLY. `about.hasReview` on the play
and `details.hasReview` on the pitch are separate signals and neither one is
the filter. A pitch-level challenge can carry `about.hasReview == false`, so a
reader that trusts the play flag alone loses it. The flags are recorded in
`review_locations` and nothing is selected on them.

RESOLVING THE PITCH. A pitch-level record names its own pitch. A play-level
record carries no pitch pointer, and the rule is the last `isPitch == true`
event of that play. On MLB 2026 that resolves 2,559 of 2,559 play-level records
to a pitch whose call code is C, 1,832 times, or B, 728 times, and the result
event type is strikeout 1,826 times, strikeout_double_play 6 times and walk 728
times, which is `AT_BAT_ENDING_EVENT_TYPES` and not the narrower "a strikeout
or a walk" the first draft claimed. On AAA 2024 it resolves 526 of 526, C 358
and B 168; the 665 AAA 2024 games staged on this machine carry 602 play-level
records, strikeout 410, walk 190 and strikeout_double_play 2. No play-level
record fails to resolve.

NEVER TEXT-MATCH `result.description`. The description of an overturned
challenge reads `"Juan Brito walks."` (753191 at-bat 23) or `"Everson Pereira
called out on strikes."` (780583 at-bat 6) and carries no marker at all. This
module reads `result.eventType`, never the description, and the description is
not a column of the table.

RECONSTRUCTING THE ORIGINAL CALL. `playEvents[].details.call` holds the final,
post-challenge call, so the umpire's call is:

    call_original = call_final                 when is_overturned is false
    call_original = the other one              when is_overturned is true

`call_original`, `call_final` and `is_overturned` are three separate columns.
A model that reads `call_final` as the umpire's call scores every overturn as a
correct call, which on MLB 2026 is 5,490 of 10,168 records.

The reconstruction is checked against a fact the feed states separately. Only
the batting team may challenge a called strike and only the fielding team may
challenge a called ball, so the standing implied by `call_original` names one
team, and that team must be `challengeTeamId`. It is, on 10,168 of 10,168 MLB
2026 records. The same rule applied to `call_final` names the wrong team on
5,490 of them, which is the overturn count exactly. On AAA 2024 the same
cross-check disagrees on 81 of 2,132 records; see `FAIL_CLAUSES` for what those
81 are and why they do not fail the run.

RECONCILIATION. Per game, over the two sides:

    sum(usedSuccessful + usedFailed) == count of MJ records in the union

Measured on MLB 2026: 10,168 records against 10,168 gameData tallies, 0 games
not reconciling across 2,342 games, with 4 games excluded for carrying no
`absChallenges` block (825093, 825094, 823669, 823745). On AAA 2024: 2,132
against 2,132, 0 games not reconciling across 356 games with the block and 309
excluded without it. `out/tables/challenge_reconciliation.csv` carries one row
per game with both counts, the delta and a status.

THE STARTING ALLOTMENT (D-12, DT-08). The estimator is the per-game maximum of
`reviewDetails.remainingChallenges` observed across the play-by-play, and the
end-of-game block `usedFailed + remaining` is the fallback, because a
successful challenge is retained and does not spend a token. Neither MLB 2026
nor the AAA 2024 feeds on this machine carry `remainingChallenges` at all, so
every allotment below comes from the fallback and is recorded as such.

MLB 2026, 4,676 team-games in 2,338 games with the block: 4,640 imply 2 and 36
imply 3. All 36 are extra-inning games, every one with `usedFailed` 3 and
`remaining` 0, which is the extra token an extra-inning game grants. Restricted
to games of nine innings or fewer the allotment is 2 on 4,266 of 4,266
team-games, 100%. The 36 are audit rows, not silent drops.

CHOICES RECORDED (SOP execution posture, autonomous defaults).
1. `call_final` is derived from the call code alone: C is a strike, B and *B are
   balls, and any other code yields null rather than a guess. One AAA 2024
   record challenges a swinging strike, code S; it keeps `call_original` null
   and is counted in the check output.
2. `challenger_role` compares `reviewDetails.player.id` against the play's
   batter, the play's pitcher and Statcast `fielder_2` for that at-bat, read
   from `data/interim/statcast_pitch`. With no Statcast part on disk the role
   is `other` rather than a wrong `catcher`. A record with no `player` key, which
   is every AAA record, gets `challenger_id` null and role `unknown`. MLB 2026
   resolves to catcher 5,381, batter 4,613, pitcher 173 and other 1.
3. Feeds are read from the raw lake. When a level and season has no feed in the
   lake and the staging cache holds it, the staging copy is read instead and
   `source` records `staging`. Nothing is written outside `data/interim/
   feed_challenge/`, `out/tables/challenge_reconciliation.csv` and
   `out/tables/aaa_allotment_audit.csv`.
4. The allotment audit carries a `level` column and holds the MLB exceptions as
   well as the AAA ones. W2.16 may write no second audit path.
5. Sealed days are routed by `absump.paths.lake_path`, never by hand.

IDEMPOTENCE. Every Parquet part is built in memory, compared byte for byte with
what is on disk and written only when it differs. The two CSV reports replace
the level-seasons of this run and keep every other row. A second run changes no
file.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as _dt
import glob
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Final

import pyarrow as pa
import pyarrow.parquet as pq
import zstandard

from absump import paths
from absump.db import PARQUET_COMPRESSION, PARQUET_COMPRESSION_LEVEL
from absump.joinkey import pitch_keys

__all__ = [
    "ALLOTMENT_COLUMNS",
    "ALLOTMENT_PATH",
    "BALL_CODES",
    "CALLED_STRIKE_CODES",
    "CHECK_CLAUSES",
    "DATASET",
    "FAIL_CLAUSES",
    "FEED_CHALLENGE_SCHEMA",
    "LOCATION_ORDER",
    "MJ",
    "RECONCILIATION_COLUMNS",
    "RECONCILIATION_PATH",
    "FeedUnreadable",
    "build_day",
    "build_season",
    "call_side",
    "catcher_map",
    "challenge_rows",
    "challenger_role",
    "check_season",
    "feed_files",
    "game_review_records",
    "game_tally",
    "last_pitch_event",
    "load_feed",
    "main",
    "modal_allotment",
    "official_date",
    "original_call",
    "reconcile_game",
    "review_records",
    "standing_side",
    "standing_team",
    "starting_allotment",
    "write_report",
]

#: The only review type that is an ABS challenge.
MJ: Final[str] = "MJ"

#: Call codes that are a called strike, and call codes that are a ball. Any
#: other code yields a null `call_final`; the module never guesses.
CALLED_STRIKE_CODES: Final[frozenset[str]] = frozenset({"C"})
BALL_CODES: Final[frozenset[str]] = frozenset({"B", "*B"})

#: The `result.eventType` values a play-level MJ challenge can end an at-bat
#: on. The first drafts of this module and of the SOP said "a strikeout or a
#: walk", which is wrong: a called third strike that also retires a runner is
#: a `strikeout_double_play`, and it is a strikeout for every purpose this
#: project has. Measured on what is on disk on 2026-09-24: MLB 2026 resolves
#: 2,560 play-level records, strikeout 1,826, walk 728 and
#: strikeout_double_play 6; the 665 staged AAA 2024 games resolve 602,
#: strikeout 410, walk 190 and strikeout_double_play 2. The enumeration is a
#: constant so the claim is stated once and the test reads it rather than
#: repeating it.
AT_BAT_ENDING_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {"strikeout", "strikeout_double_play", "walk"}
)

#: The canonical order of the locations `review_locations` lists. The two
#: `hasReview` flags come first because they are signals, not records.
LOCATION_ORDER: Final[tuple[str, ...]] = (
    "about.hasReview",
    "playEvents[].details.hasReview",
    "allPlays[].reviewDetails",
    "playEvents[].reviewDetails",
    "reviewDetails.additionalReviews[]",
)

#: The interim dataset this step writes.
DATASET: Final[str] = "feed_challenge"

SPORT_BY_LEVEL: Final[dict[str, int]] = {"mlb": 1, "aaa": 11}
LEVEL_BY_SPORT: Final[dict[int, str]] = {1: "mlb", 11: "aaa"}

_PARQUET_OPTIONS: Final[dict[str, Any]] = {
    "compression": PARQUET_COMPRESSION,
    "compression_level": PARQUET_COMPRESSION_LEVEL,
    "write_statistics": True,
}

_MAX_FEED_BYTES: Final[int] = 64 * 1024 * 1024

_PARTITION_FIELDS: Final[list[pa.Field]] = [
    pa.field("level", pa.string(), nullable=False),
    pa.field("season", pa.int32(), nullable=False),
    pa.field("official_date", pa.date32(), nullable=False),
]

FEED_CHALLENGE_SCHEMA: Final[pa.Schema] = pa.schema(
    [
        pa.field("game_pk", pa.int64(), nullable=False),
        pa.field("at_bat_index", pa.int32(), nullable=False),
        pa.field("at_bat_number", pa.int32(), nullable=False),
        pa.field("pitch_slot", pa.int32(), nullable=True),
        pa.field("feed_pitch_number", pa.int32(), nullable=True),
        pa.field("play_index", pa.int32(), nullable=True),
        pa.field("play_id", pa.string(), nullable=True),
        pa.field("review_type", pa.string(), nullable=False),
        pa.field("review_location", pa.string(), nullable=False),
        pa.field("review_locations", pa.string(), nullable=False),
        pa.field("resolved_by", pa.string(), nullable=False),
        pa.field("is_overturned", pa.bool_(), nullable=False),
        pa.field("in_progress", pa.bool_(), nullable=False),
        pa.field("call_code_stored", pa.string(), nullable=True),
        pa.field("call_final", pa.string(), nullable=True),
        pa.field("call_original", pa.string(), nullable=True),
        pa.field("challenger_id", pa.int32(), nullable=True),
        pa.field("challenger_role", pa.string(), nullable=False),
        pa.field("challenge_team_id", pa.int32(), nullable=True),
        pa.field("standing_side", pa.string(), nullable=True),
        pa.field("standing_team_id", pa.int32(), nullable=True),
        pa.field("batter_id", pa.int32(), nullable=True),
        pa.field("pitcher_id", pa.int32(), nullable=True),
        pa.field("catcher_id", pa.int32(), nullable=True),
        pa.field("is_top_inning", pa.bool_(), nullable=True),
        pa.field("inning", pa.int32(), nullable=True),
        pa.field("result_event_type", pa.string(), nullable=True),
        *_PARTITION_FIELDS,
    ]
)

#: `out/tables/challenge_reconciliation.csv`, one row per game.
RECONCILIATION_COLUMNS: Final[tuple[str, ...]] = (
    "game_pk",
    "level",
    "season",
    "official_date",
    "n_pitch_level",
    "n_play_level",
    "n_additional",
    "n_challenges",
    "away_used_successful",
    "away_used_failed",
    "home_used_successful",
    "home_used_failed",
    "n_tally",
    "delta",
    "status",
)

#: `out/tables/aaa_allotment_audit.csv`, one row per team-game that deviates.
ALLOTMENT_COLUMNS: Final[tuple[str, ...]] = (
    "game_pk",
    "level",
    "season",
    "official_date",
    "side",
    "team_id",
    "max_inning",
    "allotment_playbyplay_max",
    "allotment_end_block",
    "allotment",
    "used_successful",
    "used_failed",
    "remaining",
    "modal_allotment",
    "reason",
)

RECONCILIATION_PATH: Final[Path] = paths.REPO_ROOT / "out/tables/challenge_reconciliation.csv"
ALLOTMENT_PATH: Final[Path] = paths.REPO_ROOT / "out/tables/aaa_allotment_audit.csv"

#: Reconciliation statuses.
STATUS_OK: Final[str] = "ok"
STATUS_DELTA: Final[str] = "delta"
STATUS_NO_BLOCK: Final[str] = "no_abs_block"


class FeedUnreadable(RuntimeError):
    """One stored feed could not be decompressed or parsed."""


# ---------------------------------------------------------------------------
# Small readers. Each one returns None rather than raising, because a feed that
# is missing one optional key must still yield its other rows.
# ---------------------------------------------------------------------------


def _get(node: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _events(play: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The play's events in the order they happened, by their own `index`."""
    events = play.get("playEvents")
    if not isinstance(events, Sequence):
        return []
    return sorted((e for e in events if isinstance(e, Mapping)), key=lambda e: e.get("index") or 0)


# ---------------------------------------------------------------------------
# The pure rules. Every one of them is a function so that a test can state it.
# ---------------------------------------------------------------------------


def call_side(code: Any) -> str | None:
    """`"strike"`, `"ball"` or None for one `details.call.code`.

    C is a called strike. B and *B are balls, *B being a ball in the dirt,
    which is how a walk can end on a pitch the catcher did not hold. Every
    other code returns None: a swinging strike or a ball put in play is not a
    call the umpire made on the pitch location, and this module does not guess
    one.
    """
    text = _str(code)
    if text is None:
        return None
    if text in CALLED_STRIKE_CODES:
        return "strike"
    if text in BALL_CODES:
        return "ball"
    return None


def original_call(call_final: Any, is_overturned: Any) -> str | None:
    """The umpire's call, reconstructed from the final call and the outcome.

    The feed and Statcast both record the final, post-challenge call, so an
    overturned challenge stores the call the umpire did not make. A measure of
    umpire accuracy that skips this scores every overturn as a correct call.
    """
    side = _str(call_final)
    if side not in ("strike", "ball"):
        return None
    if is_overturned is not True:
        return side
    return "ball" if side == "strike" else "strike"


def challenger_role(player_id: Any, batter_id: Any, pitcher_id: Any, catcher_id: Any = None) -> str:
    """Which of the three people on the pitch made the challenge.

    The comparison is `reviewDetails.player.id` against the play's batter, the
    play's pitcher and Statcast `fielder_2` for that at-bat, in that order. A
    record with no `player` key, which is every AAA record in the corpus on
    this machine, returns `unknown` and never raises. An id that matches none
    of the three returns `other`.
    """
    player = _int(player_id)
    if player is None:
        return "unknown"
    if _int(batter_id) is not None and player == _int(batter_id):
        return "batter"
    if _int(pitcher_id) is not None and player == _int(pitcher_id):
        return "pitcher"
    if _int(catcher_id) is not None and player == _int(catcher_id):
        return "catcher"
    return "other"


def standing_side(call_original: Any) -> str | None:
    """Which side has standing to challenge the umpire's original call.

    Only the batting team may challenge a called strike and only the fielding
    team may challenge a called ball. The rule reads `call_original`, never
    `call_final`: on MLB 2026 the same rule read on `call_final` names the
    wrong team on 5,490 of 10,168 records, which is the overturn count.
    """
    side = _str(call_original)
    if side == "strike":
        return "batting"
    if side == "ball":
        return "fielding"
    return None


def standing_team(call_original: Any, is_top_inning: Any, away_id: Any, home_id: Any) -> int | None:
    """The team id that `standing_side` names, given the half inning."""
    side = standing_side(call_original)
    if side is None or is_top_inning not in (True, False):
        return None
    batting = _int(away_id) if is_top_inning else _int(home_id)
    fielding = _int(home_id) if is_top_inning else _int(away_id)
    return batting if side == "batting" else fielding


def last_pitch_event(play: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The last `isPitch == true` event of one play, or None when it has none.

    This is the whole rule for resolving a play-level review to a pitch. The
    play-level object carries no pitch pointer, and an ABS challenge can only
    end an at-bat on a called strike or a ball that ends it, which is one of
    `AT_BAT_ENDING_EVENT_TYPES`: a strikeout, a strikeout that also retires a
    runner (`strikeout_double_play`), or a walk. So the pitch under review is
    the last one thrown.
    """
    pitches = [event for event in _events(play) if event.get("isPitch") is True]
    return pitches[-1] if pitches else None


# ---------------------------------------------------------------------------
# The union of the three locations
# ---------------------------------------------------------------------------


def _order_locations(names: Iterable[str]) -> list[str]:
    seen = {name for name in names if name in LOCATION_ORDER}
    return [name for name in LOCATION_ORDER if name in seen]


def _flags(play: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> list[str]:
    """The two `hasReview` flags, read independently and selected on by nothing.

    `about.hasReview` sits on the play and `details.hasReview` sits on the
    pitch. A pitch-level challenge can carry `about.hasReview == false`, so
    neither flag is a filter. They are recorded and nothing more.
    """
    found: list[str] = []
    if _get(play, "about", "hasReview") is True:
        found.append("about.hasReview")
    if any(_get(event, "details", "hasReview") is True for event in events):
        found.append("playEvents[].details.hasReview")
    return found


def review_records(play: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every review object on one play, each counted once, with its locations.

    The three locations are read in a fixed order: the play-level object, then
    its `additionalReviews`, then each pitch-level object in event order with
    its own `additionalReviews`. No review type is filtered here. The caller
    keeps `MJ` and counts the rest.
    """
    events = _events(play)
    flags = _flags(play, events)
    ab_index = _int(_get(play, "about", "atBatIndex"))
    if ab_index is None:
        return []
    base = {
        "at_bat_index": ab_index,
        "at_bat_number": ab_index + 1,
        "result_event_type": _str(_get(play, "result", "eventType")),
        "is_top_inning": _get(play, "about", "isTopInning") is True,
        "inning": _int(_get(play, "about", "inning")),
        "batter_id": _int(_get(play, "matchup", "batter", "id")),
        "pitcher_id": _int(_get(play, "matchup", "pitcher", "id")),
    }
    last = last_pitch_event(play)
    found: list[dict[str, Any]] = []

    def add(review: Mapping[str, Any], event: Any, location: str, resolved_by: str) -> None:
        found.append(
            {
                **base,
                "review": review,
                "event": event,
                "review_type": _str(review.get("reviewType")),
                "review_location": location,
                "review_locations": _order_locations([*flags, location]),
                "resolved_by": resolved_by,
            }
        )

    def add_additional(parent: Mapping[str, Any], event: Any, resolved_by: str) -> None:
        extra = parent.get("additionalReviews")
        if not isinstance(extra, Sequence):
            return
        for review in extra:
            if isinstance(review, Mapping):
                add(review, event, "reviewDetails.additionalReviews[]", resolved_by)

    play_review = play.get("reviewDetails")
    if isinstance(play_review, Mapping):
        add(play_review, last, "allPlays[].reviewDetails", "last_isPitch")
        add_additional(play_review, last, "last_isPitch")
    for event in events:
        event_review = event.get("reviewDetails")
        if isinstance(event_review, Mapping):
            add(event_review, event, "playEvents[].reviewDetails", "event")
            add_additional(event_review, event, "event")
    return found


def game_review_records(feed: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every review object in one feed, in play order, each counted once."""
    plays = _get(feed, "liveData", "plays", "allPlays") or []
    out: list[dict[str, Any]] = []
    for play in plays:
        if isinstance(play, Mapping):
            out.extend(review_records(play))
    return out


# ---------------------------------------------------------------------------
# The challenge rows
# ---------------------------------------------------------------------------


def _slot_map(play: Mapping[str, Any], game_pk: int) -> dict[int, int]:
    """`id(event) -> pitch_slot` for one play, from `absump.joinkey`."""
    return {id(event): key[2] for key, event in pitch_keys(play, game_pk)}


def challenge_rows(
    feed: Mapping[str, Any], catchers: Mapping[tuple[int, int], int] | None = None
) -> list[dict[str, Any]]:
    """Every `MJ` record in one feed, as rows of `FEED_CHALLENGE_SCHEMA`.

    `catchers` maps `(game_pk, at_bat_number)` to Statcast `fielder_2` and is
    the only input this function takes beyond the feed. With no map the role of
    a challenger who is neither batter nor pitcher is `other`, never a guessed
    `catcher`.
    """
    game_pk = _int(_get(feed, "gameData", "game", "pk"))
    if game_pk is None:
        raise FeedUnreadable("gameData.game.pk is absent")
    away_id = _int(_get(feed, "gameData", "teams", "away", "id"))
    home_id = _int(_get(feed, "gameData", "teams", "home", "id"))
    lookup = catchers or {}
    plays = _get(feed, "liveData", "plays", "allPlays") or []
    rows: list[dict[str, Any]] = []
    for play in plays:
        if not isinstance(play, Mapping):
            continue
        slots = _slot_map(play, game_pk)
        for record in review_records(play):
            if record["review_type"] != MJ:
                continue
            rows.append(_challenge_row(record, game_pk, away_id, home_id, slots, lookup))
    return rows


def _challenge_row(
    record: Mapping[str, Any],
    game_pk: int,
    away_id: int | None,
    home_id: int | None,
    slots: Mapping[int, int],
    catchers: Mapping[tuple[int, int], int],
) -> dict[str, Any]:
    review = record["review"]
    event = record["event"]
    code = _str(_get(event, "details", "call", "code")) if event is not None else None
    final = call_side(code)
    overturned = review.get("isOverturned") is True
    original = original_call(final, overturned)
    at_bat_number = int(record["at_bat_number"])
    catcher_id = catchers.get((int(game_pk), at_bat_number))
    challenger_id = _int(_get(review, "player", "id"))
    return {
        "game_pk": int(game_pk),
        "at_bat_index": int(record["at_bat_index"]),
        "at_bat_number": at_bat_number,
        "pitch_slot": slots.get(id(event)) if event is not None else None,
        "feed_pitch_number": _int(event.get("pitchNumber")) if event is not None else None,
        "play_index": _int(event.get("index")) if event is not None else None,
        "play_id": _str(event.get("playId")) if event is not None else None,
        "review_type": MJ,
        "review_location": record["review_location"],
        "review_locations": "|".join(record["review_locations"]),
        "resolved_by": record["resolved_by"],
        "is_overturned": overturned,
        "in_progress": review.get("inProgress") is True,
        "call_code_stored": code,
        "call_final": final,
        "call_original": original,
        "challenger_id": challenger_id,
        "challenger_role": challenger_role(
            challenger_id, record["batter_id"], record["pitcher_id"], catcher_id
        ),
        "challenge_team_id": _int(review.get("challengeTeamId")),
        "standing_side": standing_side(original),
        "standing_team_id": standing_team(original, record["is_top_inning"], away_id, home_id),
        "batter_id": record["batter_id"],
        "pitcher_id": record["pitcher_id"],
        "catcher_id": _int(catcher_id),
        "is_top_inning": record["is_top_inning"],
        "inning": record["inning"],
        "result_event_type": record["result_event_type"],
    }


# ---------------------------------------------------------------------------
# The reconciliation and the allotment
# ---------------------------------------------------------------------------


def game_tally(feed: Mapping[str, Any]) -> dict[str, Any]:
    """The `gameData.absChallenges` tally for one game.

    `n_tally` is `sum over {away, home} of (usedSuccessful + usedFailed)`, which
    is the count the challenge table has to match. A game with no
    `absChallenges` block has `has_block` false and `n_tally` None; it is
    excluded from the reconciliation rather than counted as zero. Four MLB 2026
    games are in that state: 823669, 823745, 825093 and 825094.
    """
    block = _get(feed, "gameData", "absChallenges")
    row: dict[str, Any] = {
        "has_block": isinstance(block, Mapping),
        "n_tally": None,
    }
    total = 0
    for side in ("away", "home"):
        used_successful = _int(_get(block, side, "usedSuccessful")) or 0
        used_failed = _int(_get(block, side, "usedFailed")) or 0
        row[f"{side}_used_successful"] = used_successful if row["has_block"] else None
        row[f"{side}_used_failed"] = used_failed if row["has_block"] else None
        row[f"{side}_remaining"] = (
            _int(_get(block, side, "remaining")) if row["has_block"] else None
        )
        total += used_successful + used_failed
    if row["has_block"]:
        row["n_tally"] = total
    return row


def reconcile_game(feed: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One row of `out/tables/challenge_reconciliation.csv`.

    `delta` is `n_challenges - n_tally`, so a positive delta means the feed
    holds more MJ records than the two sides say they spent. `status` is `ok`
    at delta 0, `delta` otherwise, and `no_abs_block` for a game that carries
    no tally to compare against.
    """
    counts = collections.Counter(row["review_location"] for row in rows)
    tally = game_tally(feed)
    n_pitch = counts["playEvents[].reviewDetails"]
    n_play = counts["allPlays[].reviewDetails"]
    n_additional = counts["reviewDetails.additionalReviews[]"]
    n_challenges = n_pitch + n_play + n_additional
    if not tally["has_block"]:
        status, delta = STATUS_NO_BLOCK, None
    else:
        delta = n_challenges - int(tally["n_tally"])
        status = STATUS_OK if delta == 0 else STATUS_DELTA
    return {
        "game_pk": _int(_get(feed, "gameData", "game", "pk")),
        "n_pitch_level": n_pitch,
        "n_play_level": n_play,
        "n_additional": n_additional,
        "n_challenges": n_challenges,
        "away_used_successful": tally["away_used_successful"],
        "away_used_failed": tally["away_used_failed"],
        "home_used_successful": tally["home_used_successful"],
        "home_used_failed": tally["home_used_failed"],
        "n_tally": tally["n_tally"],
        "delta": delta,
        "status": status,
    }


def starting_allotment(feed: Mapping[str, Any]) -> dict[str, Any]:
    """The starting challenge allotment per team-game, both estimators (D-12).

    The primary estimator is the per-game maximum of
    `reviewDetails.remainingChallenges` observed across the play-by-play. The
    fallback is the end-of-game block, `usedFailed + remaining`, because a
    successful challenge is retained and spends no token. Neither MLB 2026 nor
    the AAA 2024 feeds on this machine carry `remainingChallenges`, so the
    fallback is what the sweep reports, and `allotment_playbyplay_max` is None.
    A team-game where the two estimators disagree is an audit row.
    """
    plays = _get(feed, "liveData", "plays", "allPlays") or []
    seen: dict[str, list[int]] = {"away": [], "home": []}
    max_inning = 0
    for play in plays:
        if not isinstance(play, Mapping):
            continue
        max_inning = max(max_inning, _int(_get(play, "about", "inning")) or 0)
        for record in review_records(play):
            snapshot = record["review"].get("remainingChallenges")
            for side in ("away", "home"):
                value = _int(_get(snapshot, side))
                if value is not None:
                    seen[side].append(value)
    block = _get(feed, "gameData", "absChallenges")
    out: dict[str, Any] = {
        "game_pk": _int(_get(feed, "gameData", "game", "pk")),
        "max_inning": max_inning,
        "has_block": isinstance(block, Mapping),
    }
    for side in ("away", "home"):
        used_successful = _int(_get(block, side, "usedSuccessful"))
        used_failed = _int(_get(block, side, "usedFailed"))
        remaining = _int(_get(block, side, "remaining"))
        end_block = None
        if used_failed is not None and remaining is not None:
            end_block = used_failed + remaining
        pbp = max(seen[side]) if seen[side] else None
        out[side] = {
            "team_id": _int(_get(feed, "gameData", "teams", side, "id")),
            "allotment_playbyplay_max": pbp,
            "allotment_end_block": end_block,
            "allotment": pbp if pbp is not None else end_block,
            "used_successful": used_successful,
            "used_failed": used_failed,
            "remaining": remaining,
        }
    return out


def _allotment_reason(side: Mapping[str, Any], mode: int | None) -> str:
    reasons: list[str] = []
    pbp = side["allotment_playbyplay_max"]
    end = side["allotment_end_block"]
    if pbp is not None and end is not None and pbp != end:
        reasons.append("playbyplay_max_disagrees_with_end_block")
    value = side["allotment"]
    if mode is not None and value is not None and value != mode:
        reasons.append("above_modal_allotment" if value > mode else "below_modal_allotment")
    return ";".join(reasons)


# ---------------------------------------------------------------------------
# The lake
# ---------------------------------------------------------------------------

_STAGING_ROOT: Final[Path] = paths.REPO_ROOT / "data/staging/statsapi/feeds"


def official_date(feed: Mapping[str, Any]) -> _dt.date:
    """The feed's own officialDate, which is the day the lake files it under."""
    text = _str(_get(feed, "gameData", "datetime", "officialDate"))
    if text is None:
        raise FeedUnreadable("gameData.datetime.officialDate is absent")
    return _dt.date.fromisoformat(text)


def load_feed(path: Path) -> dict[str, Any]:
    """Read one stored feed, compressed in the lake or plain in the staging cache."""
    try:
        if path.suffix == ".zst":
            with path.open("rb") as handle:
                body = zstandard.ZstdDecompressor().stream_reader(handle).read(_MAX_FEED_BYTES)
        else:
            body = path.read_bytes()
        return json.loads(body.decode("utf-8"))
    except (OSError, ValueError, zstandard.ZstdError) as exc:
        raise FeedUnreadable(f"{path}: {exc}") from exc


def _lake_files(sport_id: int, season: int) -> dict[_dt.date, list[Path]]:
    root = paths.raw_feed(sport_id, season, paths.LAST_OPEN_DATE, 1).parents[1]
    by_date: dict[_dt.date, list[Path]] = {}
    if not root.is_dir():
        return by_date
    for path in sorted(root.glob("date=*/gamepk=*.json.zst")):
        try:
            day = _dt.date.fromisoformat(path.parent.name.split("=", 1)[1])
        except (IndexError, ValueError):
            continue
        by_date.setdefault(day, []).append(path)
    return {day: sorted(files) for day, files in sorted(by_date.items())}


def _staging_files(sport_id: int, season: int) -> dict[_dt.date, list[Path]]:
    """The staging cache, grouped by the officialDate each feed states.

    The staging layout is flat, one file per gamePk, so the day comes from the
    feed itself. This path is read only when the raw lake holds no feed for the
    level and season, which is how the AAA arm of DT-08 has data before phase
    02 imports it.
    """
    root = _STAGING_ROOT / f"sport{sport_id}" / str(season)
    by_date: dict[_dt.date, list[Path]] = {}
    if not root.is_dir():
        return by_date
    for path in sorted(root.glob("*.json")):
        try:
            day = official_date(load_feed(path))
        except (FeedUnreadable, ValueError):
            continue
        by_date.setdefault(day, []).append(path)
    return {day: sorted(files) for day, files in sorted(by_date.items())}


def feed_files(sport_id: Any, season: Any) -> dict[_dt.date, list[Path]]:
    """Every stored feed for one sport and season, grouped by officialDate.

    The raw lake first. The staging cache only when the lake holds nothing for
    that sport and season.
    """
    sport = int(sport_id)
    year = int(season)
    by_date = _lake_files(sport, year)
    if by_date:
        return by_date
    return _staging_files(sport, year)


def _source_of(files: Mapping[_dt.date, Sequence[Path]]) -> str:
    for paths_for_day in files.values():
        for path in paths_for_day:
            return "staging" if _STAGING_ROOT in path.parents else "lake"
    return "none"


def catcher_map(level: str, season: int, day: _dt.date) -> dict[tuple[int, int], int]:
    """`(game_pk, at_bat_number) -> fielder_2` for one day, from `statcast_pitch`.

    W2.13 records that the feed carries no per-pitch catcher:
    `liveData.linescore.defense.catcher` is end-of-game defence only. Statcast
    `fielder_2` is the catcher on the pitch, and W2.14 carries it. With no part
    on disk the map is empty and `challenger_role` returns `other` instead of a
    guessed `catcher`.
    """
    part = paths.lake_path("statcast_pitch", level, season, day)
    if not part.exists():
        return {}
    table = pq.read_table(part, columns=["game_pk", "at_bat_number", "fielder_2"])
    out: dict[tuple[int, int], int] = {}
    for game_pk, at_bat, catcher in zip(
        table.column("game_pk").to_pylist(),
        table.column("at_bat_number").to_pylist(),
        table.column("fielder_2").to_pylist(),
        strict=False,
    ):
        if game_pk is None or at_bat is None or catcher is None:
            continue
        out.setdefault((int(game_pk), int(at_bat)), int(catcher))
    return out


def _table(rows: Sequence[Mapping[str, Any]], schema: pa.Schema) -> pa.Table:
    columns = {field.name: [row.get(field.name) for row in rows] for field in schema}
    return pa.Table.from_pydict(columns, schema=schema)


def _parquet_bytes(rows: Sequence[Mapping[str, Any]], schema: pa.Schema) -> bytes:
    sink = pa.BufferOutputStream()
    pq.write_table(_table(rows, schema), sink, **_PARQUET_OPTIONS)
    return sink.getvalue().to_pybytes()


def _write_bytes_if_changed(target: Path, body: bytes) -> bool:
    """Write `body` to `target` atomically. Return True when the bytes changed."""
    if target.exists() and target.read_bytes() == body:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(body)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


_SORT_KEY = ("game_pk", "at_bat_index", "play_index", "review_location")


def _row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        int(row["game_pk"]),
        int(row["at_bat_index"]),
        -1 if row["play_index"] is None else int(row["play_index"]),
        str(row["review_location"]),
    )


# ---------------------------------------------------------------------------
# One day
# ---------------------------------------------------------------------------


def build_day(
    sport_id: Any,
    season: Any,
    day: _dt.date,
    files: Sequence[Path] | None = None,
    *,
    write: bool = True,
) -> dict[str, Any]:
    """Extract one officialDate and write its `feed_challenge` part.

    One date is one part, so this function is the unit of parallel work and the
    unit of idempotence. A feed that will not decompress or parse is reported
    and skipped; it does not stop the day. A day with no MJ record writes no
    part, which is how a day of games with no challenge stays absent rather
    than becoming an empty file.
    """
    sport = int(sport_id)
    year = int(season)
    level = LEVEL_BY_SPORT[sport]
    for_day = list(files) if files is not None else feed_files(sport, year).get(day, [])
    catchers = catcher_map(level, year, day)
    rows: list[dict[str, Any]] = []
    reconciliation: list[dict[str, Any]] = []
    allotment: list[dict[str, Any]] = []
    review_types: collections.Counter[str] = collections.Counter()
    unreadable: list[str] = []
    misfiled = 0
    games = 0
    for path in for_day:
        try:
            feed = load_feed(path)
            if official_date(feed) != day:
                misfiled += 1
            game_rows = challenge_rows(feed, catchers)
            for record in game_review_records(feed):
                review_types[record["review_type"] or "unknown"] += 1
            recon = reconcile_game(feed, game_rows)
            allot = starting_allotment(feed)
        except (FeedUnreadable, KeyError, TypeError, ValueError) as exc:
            unreadable.append(f"{path.name}: {exc}")
            continue
        games += 1
        for row in game_rows:
            row["level"] = level
            row["season"] = year
            row["official_date"] = day
        rows.extend(game_rows)
        recon.update({"level": level, "season": year, "official_date": day.isoformat()})
        reconciliation.append(recon)
        for side in ("away", "home"):
            allotment.append(
                {
                    "game_pk": allot["game_pk"],
                    "level": level,
                    "season": year,
                    "official_date": day.isoformat(),
                    "side": side,
                    "max_inning": allot["max_inning"],
                    "has_block": allot["has_block"],
                    **allot[side],
                }
            )

    written = unchanged = 0
    if write and rows:
        rows.sort(key=_row_sort_key)
        target = paths.lake_path(DATASET, level, season, day)
        if _write_bytes_if_changed(target, _parquet_bytes(rows, FEED_CHALLENGE_SCHEMA)):
            written += 1
        else:
            unchanged += 1
    return {
        "date": day.isoformat(),
        "games": games,
        "rows": len(rows),
        "written": written,
        "unchanged": unchanged,
        "unreadable": unreadable,
        "misfiled": misfiled,
        "review_types": dict(review_types),
        "reconciliation": reconciliation,
        "allotment": allotment,
    }


def _day_task(payload: tuple[int, int, str, list[str], bool]) -> dict[str, Any]:
    """The process-pool entry point. Only picklable types cross the boundary."""
    sport_id, season, day_text, file_texts, write = payload
    day = _dt.date.fromisoformat(day_text)
    return build_day(sport_id, season, day, [Path(text) for text in file_texts], write=write)


# ---------------------------------------------------------------------------
# The two CSV reports
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_existing(path: Path, columns: Sequence[str]) -> list[dict[str, str]]:
    """The rows already in a report, or none when it is absent or of an older shape."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != list(columns):
            return []
        return [dict(row) for row in reader]


def write_report(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    scope: set[tuple[str, int]],
) -> int:
    """Replace the `scope` level-seasons in one report and keep every other row."""
    fresh = [{name: _text(row.get(name)) for name in columns} for row in rows]
    kept = [
        row
        for row in _read_existing(path, columns)
        if (row.get("level", ""), _as_int(row.get("season", ""))) not in scope
    ]
    merged = sorted(
        kept + fresh,
        key=lambda row: (
            row.get("level", ""),
            _as_int(row.get("season", "")),
            row.get("official_date", ""),
            _as_int(row.get("game_pk", "")),
            row.get("side", ""),
        ),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged)
    return len(merged)


def modal_allotment(records: Iterable[Mapping[str, Any]]) -> int | None:
    """The most common starting allotment across a season's team-games."""
    values = collections.Counter(
        int(record["allotment"]) for record in records if record.get("allotment") is not None
    )
    if not values:
        return None
    top = max(values.values())
    return min(value for value, count in values.items() if count == top)


# ---------------------------------------------------------------------------
# One season
# ---------------------------------------------------------------------------


def build_season(
    level: str,
    season: Any,
    *,
    procs: int = 8,
    write: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Build `feed_challenge` and both reports for one level and season."""
    sport_id = SPORT_BY_LEVEL[level]
    year = int(season)
    by_date = feed_files(sport_id, year)
    source = _source_of(by_date)
    if limit is not None:
        trimmed: dict[_dt.date, list[Path]] = {}
        taken = 0
        for day, files in by_date.items():
            if taken >= limit:
                break
            trimmed[day] = files[: limit - taken]
            taken += len(trimmed[day])
        by_date = trimmed
    payloads = [
        (sport_id, year, day.isoformat(), [str(path) for path in files], write)
        for day, files in by_date.items()
    ]
    if not payloads:
        days: list[dict[str, Any]] = []
    elif max(1, min(int(procs), len(payloads))) == 1:
        days = [_day_task(payload) for payload in payloads]
    else:
        with ProcessPoolExecutor(max_workers=min(int(procs), len(payloads))) as pool:
            days = list(pool.map(_day_task, payloads))

    reconciliation = [row for day in days for row in day["reconciliation"]]
    allotment = [row for day in days for row in day["allotment"]]
    review_types: collections.Counter[str] = collections.Counter()
    for day in days:
        review_types.update(day["review_types"])

    with_block = [row for row in allotment if row["has_block"]]
    mode = modal_allotment(with_block)
    audit: list[dict[str, Any]] = []
    for row in with_block:
        reason = _allotment_reason(row, mode)
        if reason:
            audit.append({**row, "modal_allotment": mode, "reason": reason})

    # A run that found no feed replaces nothing. Without this guard, running the
    # build for a level and season whose feeds have moved would silently empty
    # that level-season out of both reports while its Parquet parts stayed on
    # disk, and the two would then disagree.
    scope = {(level, year)}
    if write and reconciliation:
        write_report(RECONCILIATION_PATH, RECONCILIATION_COLUMNS, reconciliation, scope)
        write_report(ALLOTMENT_PATH, ALLOTMENT_COLUMNS, audit, scope)

    not_reconciling = [row for row in reconciliation if row["status"] == STATUS_DELTA]
    return {
        "level": level,
        "season": year,
        "source": source,
        "dates": len(days),
        "games": sum(int(day["games"]) for day in days),
        "rows": sum(int(day["rows"]) for day in days),
        "written": sum(int(day["written"]) for day in days),
        "unchanged": sum(int(day["unchanged"]) for day in days),
        "misfiled": sum(int(day["misfiled"]) for day in days),
        "unreadable": [line for day in days for line in day["unreadable"]],
        "review_types": dict(review_types.most_common()),
        "n_pitch_level": sum(int(row["n_pitch_level"]) for row in reconciliation),
        "n_play_level": sum(int(row["n_play_level"]) for row in reconciliation),
        "n_additional": sum(int(row["n_additional"]) for row in reconciliation),
        "n_tally": sum(int(row["n_tally"] or 0) for row in reconciliation),
        "games_no_block": sum(1 for row in reconciliation if row["status"] == STATUS_NO_BLOCK),
        "games_not_reconciling": len(not_reconciling),
        "not_reconciling": [int(row["game_pk"]) for row in not_reconciling][:20],
        "modal_allotment": mode,
        "allotment_audit_rows": len(audit),
    }


# ---------------------------------------------------------------------------
# The check. It reads what is on disk and asserts the W2.16 clauses.
# ---------------------------------------------------------------------------

#: Everything `--check` counts. Each one is zero on a correct MLB 2026 build.
CHECK_CLAUSES: Final[tuple[str, ...]] = (
    "games_not_reconciling",
    "non_mj_rows",
    "play_level_unresolved",
    "play_level_bad_call_code",
    "standing_disagrees",
    "overturns_minus_used_successful",
    "duplicate_keys",
)

#: The clauses that set the exit code. They are the W2.16 conditions.
#:
#: `standing_disagrees` is counted and printed but does not fail the run. It is
#: a cross-check this module adds, not a W2.16 condition, and it separates the
#: two corpora: 0 of 10,168 on MLB 2026, 81 of 2,132 on AAA 2024. Of those 81,
#: 52 are play-level records, where AAA 2024 puts a mid-at-bat challenge on the
#: play object and the last-`isPitch` rule therefore resolves the wrong pitch;
#: game 752720 at-bat 48 is one, a called strike challenged by the batting team
#: in an at-bat that ended in a walk. The other 29 name their own pitch, so the
#: disagreement is in the AAA feed's own `challengeTeamId` and not in any rule
#: here. Chapter 1 reads MLB 2026, where the count is zero. Reported for
#: DEVIATIONS.md.
FAIL_CLAUSES: Final[tuple[str, ...]] = (
    "games_not_reconciling",
    "non_mj_rows",
    "play_level_unresolved",
    "play_level_bad_call_code",
    "overturns_minus_used_successful",
    "duplicate_keys",
)


def _dataset_parts(dataset: str, level: str, season: int) -> list[Path]:
    root = paths.lake_path(dataset, level, season, paths.LAST_OPEN_DATE).parents[1]
    return sorted(Path(part) for part in glob.glob(str(root / "date=*/part-*.parquet")))


def check_season(level: str, season: Any) -> dict[str, Any]:
    """Re-read the built artefacts for one level and season and count breaches.

    Offline and cheap: the whole MLB 2026 challenge table is about ten thousand
    rows. On a machine with no part on disk it reports zero parts and no
    breach, which is what a clean clone does.
    """
    year = int(season)
    parts = _dataset_parts(DATASET, level, year)
    counts = dict.fromkeys(CHECK_CLAUSES, 0)
    detail: dict[str, Any] = {"parts": len(parts), "rows": 0}
    keys: set[tuple[int, int, str, int]] = set()
    overturns = 0
    call_codes: collections.Counter[str] = collections.Counter()
    roles: collections.Counter[str] = collections.Counter()
    for part in parts:
        table = pq.read_table(part)
        detail["rows"] += table.num_rows
        rows = table.to_pylist()
        for row in rows:
            if row["review_type"] != MJ:
                counts["non_mj_rows"] += 1
            if row["resolved_by"] == "last_isPitch":
                if row["pitch_slot"] is None:
                    counts["play_level_unresolved"] += 1
                if row["call_code_stored"] not in CALLED_STRIKE_CODES | BALL_CODES:
                    counts["play_level_bad_call_code"] += 1
            if (
                row["standing_team_id"] is not None
                and row["challenge_team_id"] is not None
                and row["standing_team_id"] != row["challenge_team_id"]
            ):
                counts["standing_disagrees"] += 1
            key = (
                int(row["game_pk"]),
                int(row["at_bat_index"]),
                str(row["review_location"]),
                -1 if row["play_index"] is None else int(row["play_index"]),
            )
            if key in keys and row["review_location"] != "reviewDetails.additionalReviews[]":
                counts["duplicate_keys"] += 1
            keys.add(key)
            overturns += 1 if row["is_overturned"] else 0
            call_codes[str(row["call_code_stored"])] += 1
            roles[str(row["challenger_role"])] += 1

    used_successful = 0
    reconciled = 0
    for row in _read_existing(RECONCILIATION_PATH, RECONCILIATION_COLUMNS):
        if row.get("level") != level or _as_int(row.get("season")) != year:
            continue
        reconciled += 1
        if row.get("status") == STATUS_DELTA:
            counts["games_not_reconciling"] += 1
        used_successful += _as_int(row.get("away_used_successful")) + _as_int(
            row.get("home_used_successful")
        )
    if reconciled:
        counts["overturns_minus_used_successful"] = overturns - used_successful
    detail.update(
        {
            "games_in_report": reconciled,
            "overturns": overturns,
            "used_successful": used_successful,
            "call_codes": dict(call_codes.most_common()),
            "roles": dict(roles.most_common()),
        }
    )
    return {"level": level, "season": year, "counts": counts, "detail": detail}


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def _format_build(totals: Mapping[str, Any]) -> list[str]:
    lines = [
        f"{totals['level']} {totals['season']}: {totals['games']} games across "
        f"{totals['dates']} dates, source {totals['source']}",
        f"  MJ rows {totals['rows']}: pitch level {totals['n_pitch_level']}, "
        f"play level {totals['n_play_level']}, additionalReviews {totals['n_additional']}",
        f"  gameData tally {totals['n_tally']}, games not reconciling "
        f"{totals['games_not_reconciling']}, games with no absChallenges block "
        f"{totals['games_no_block']}",
        f"  parts written {totals['written']}, unchanged {totals['unchanged']}",
        f"  modal starting allotment {totals['modal_allotment']}, audit rows "
        f"{totals['allotment_audit_rows']}",
    ]
    dropped = {name: n for name, n in totals["review_types"].items() if name != MJ}
    if dropped:
        head = "  ".join(f"{name} {n}" for name, n in list(dropped.items())[:8])
        lines.append(f"  review types dropped, {sum(dropped.values())} records: {head}")
    if totals["not_reconciling"]:
        lines.append(f"  not reconciling: {totals['not_reconciling']}")
    if totals["misfiled"]:
        lines.append(f"  officialDate disagrees with the stored day on {totals['misfiled']} feeds")
    for line in totals["unreadable"][:10]:
        lines.append(f"  unreadable {line}")
    return lines


def _format_check(report: Mapping[str, Any]) -> list[str]:
    counts = report["counts"]
    detail = report["detail"]
    lines = [
        f"{report['level']} {report['season']}: {detail['parts']} parts, "
        f"{detail['rows']} rows, {detail['games_in_report']} games in the report",
        f"  overturned {detail['overturns']} against usedSuccessful {detail['used_successful']}",
        "  " + "  ".join(f"{name} {counts[name]}" for name in FAIL_CLAUSES),
        f"  standing_disagrees {counts['standing_disagrees']}, reported not gated",
    ]
    if detail["rows"]:
        lines.append(f"  call codes {detail['call_codes']}")
        lines.append(f"  challenger roles {detail['roles']}")
    return lines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m absump.challenges",
        description="Build feed_challenge from the union of the three review locations "
        "and reconcile it against the gameData tallies. SOP W2.16. No network.",
    )
    parser.add_argument("--level", choices=sorted(SPORT_BY_LEVEL), default="mlb")
    parser.add_argument("--season", type=int, nargs="+", default=[2026])
    parser.add_argument("--procs", type=int, default=8, help="parallel dates, default 8")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many feeds")
    parser.add_argument("--dry-run", action="store_true", help="build and count, write nothing")
    parser.add_argument(
        "--check",
        action="store_true",
        help="assert the W2.16 clauses against what is on disk, build nothing",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build the table, or check it. Returns 1 on any breach, 0 otherwise."""
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    failures = 0
    report: list[dict[str, Any]] = []
    for season in args.season:
        if args.check:
            result = check_season(args.level, int(season))
            if any(result["counts"][name] != 0 for name in FAIL_CLAUSES):
                failures += 1
            lines = _format_check(result)
        else:
            result = build_season(
                args.level,
                int(season),
                procs=int(args.procs),
                write=not args.dry_run,
                limit=args.limit,
            )
            if result["games_not_reconciling"] or result["unreadable"] or result["misfiled"]:
                failures += 1
            lines = _format_build(result)
        report.append(result)
        if not args.json:
            for line in lines:
                print(line)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
