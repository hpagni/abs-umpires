"""Synthetic fixtures for the ABS umpire project. SOP step W9.3.

Nothing here is a real MLB response. The public repository must never carry a raw MLB
feed, so every byte this module emits is generated from the constants below. The only
real artefact the project keeps is `quality/fixtures_attest.json`, which records the
sha256 and the shape of locally cached responses and none of their content.

What it emits, into an output directory (default `tests/fixtures/generated/`):

  mlb_feed.json     a GUMBO-shaped MLB live feed carrying all seven traps of W9.3
  statcast.csv      a 119-column Statcast CSV matching that feed, written utf-8-sig
  aaa_feed.json     R2 fixture: an AAA-shaped feed with a three-token allotment (D-12)
  drawer_rows.json  R2 fixture: Savant ABS drawer rows for the DT-28 coordinate bridge,
                    including a within-game coordinate near-tie

The seven traps, in the order SOP W9.3 lists them, each with its locator in the feed:

  1 automatic_ball pitch-number offset   play 1: a non-pitch automatic_ball action sits
                                         between two pitches, so Statcast pitch_number
                                         runs one ahead of the feed pitchNumber
  2 four-event intentional walk          play 2: four playEvents, every one pitchNumber 0
                                         and details.call.code "VB"
  3 pitch-level MJ                       play 3: details.hasReview true on the pitch while
                                         about.hasReview is false on the same play
  4 play-level MJ                        play 4: about.hasReview true, play-level
                                         reviewDetails, and a result.description that does
                                         not contain the word "challenged"
  5 overturned challenge                 play 5: reviewDetails.isOverturned true while
                                         details.call.code holds the POST-challenge call
  6 "MF" replay record                   play 6: reviewDetails.reviewType "MF", filtered
  7 AAA-shaped MJ with no player         play 7: reviewDetails with no "player" key

Ground truth for all of it lives in `tests/fixtures/expected/`. The generator is
deterministic: no clock, no randomness, no network. Regenerating must reproduce every
byte, and `tests/fixtures/test_synth_traps.py` asserts exactly that.

Run:  uv run --locked python tests/fixtures/synth_feed.py --out tests/fixtures/generated
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import pathlib

# ---------------------------------------------------------------------------
# Shape constants.
# ---------------------------------------------------------------------------

# 119 columns. The data contract records the Statcast export header as byte-identical
# across 2024, 2025 and 2026 and identical to the minors CSV, and DT-02 asserts the
# header sha256 against a committed fixture. The names below are that header's column
# names -- schema, not observations. Their sha256 is recorded in
# quality/fixtures_attest.json against a locally cached pre-2026 export.
STATCAST_COLUMNS = [
    "pitch_type",
    "game_date",
    "release_speed",
    "release_pos_x",
    "release_pos_z",
    "player_name",
    "batter",
    "pitcher",
    "events",
    "description",
    "spin_dir",
    "spin_rate_deprecated",
    "break_angle_deprecated",
    "break_length_deprecated",
    "zone",
    "des",
    "game_type",
    "stand",
    "p_throws",
    "home_team",
    "away_team",
    "type",
    "hit_location",
    "bb_type",
    "balls",
    "strikes",
    "game_year",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "on_3b",
    "on_2b",
    "on_1b",
    "outs_when_up",
    "inning",
    "inning_topbot",
    "hc_x",
    "hc_y",
    "tfs_deprecated",
    "tfs_zulu_deprecated",
    "umpire",
    "sv_id",
    "vx0",
    "vy0",
    "vz0",
    "ax",
    "ay",
    "az",
    "sz_top",
    "sz_bot",
    "hit_distance_sc",
    "launch_speed",
    "launch_angle",
    "effective_speed",
    "release_spin_rate",
    "release_extension",
    "game_pk",
    "fielder_2",
    "fielder_3",
    "fielder_4",
    "fielder_5",
    "fielder_6",
    "fielder_7",
    "fielder_8",
    "fielder_9",
    "release_pos_y",
    "estimated_ba_using_speedangle",
    "estimated_woba_using_speedangle",
    "woba_value",
    "woba_denom",
    "babip_value",
    "iso_value",
    "launch_speed_angle",
    "at_bat_number",
    "pitch_number",
    "pitch_name",
    "home_score",
    "away_score",
    "bat_score",
    "fld_score",
    "post_away_score",
    "post_home_score",
    "post_bat_score",
    "post_fld_score",
    "if_fielding_alignment",
    "of_fielding_alignment",
    "spin_axis",
    "delta_home_win_exp",
    "delta_run_exp",
    "bat_speed",
    "swing_length",
    "miss_distance",
    "estimated_slg_using_speedangle",
    "delta_pitcher_run_exp",
    "hyper_speed",
    "home_score_diff",
    "bat_score_diff",
    "home_win_exp",
    "bat_win_exp",
    "age_pit_legacy",
    "age_bat_legacy",
    "age_pit",
    "age_bat",
    "n_thruorder_pitcher",
    "n_priorpa_thisgame_player_at_bat",
    "pitcher_days_since_prev_game",
    "batter_days_since_prev_game",
    "pitcher_days_until_next_game",
    "batter_days_until_next_game",
    "api_break_z_with_gravity",
    "api_break_x_arm",
    "api_break_x_batter_in",
    "arm_angle",
    "attack_angle",
    "attack_direction",
    "swing_path_tilt",
    "intercept_ball_minus_batter_pos_x_inches",
    "intercept_ball_minus_batter_pos_y_inches",
]

# The Savant CSV carries a UTF-8 BOM, so it is read with encoding="utf-8-sig" and the
# fixture is written the same way. UT-14 is the test that pins this.
STATCAST_ENCODING = "utf-8-sig"

# Synthetic identifiers. Deliberately outside any real MLB gamePk or player id range so
# that a fixture row can never be mistaken for a real one.
GAME_PK = 999001
AAA_GAME_PK = 999002

HOME_TEAM_ID = 900
AWAY_TEAM_ID = 901
HOME_TEAM_CODE = "SYH"
AWAY_TEAM_CODE = "SYA"

PITCHER_ID = 5001
BATTER_IDS = {1: 6001, 2: 6002, 3: 6003, 4: 6004, 5: 6005, 6: 6006, 7: 6007, 8: 6008}
CATCHER_ID = 7003

# Pre-2026 on purpose. Phase 01 may not read or write a 2026 datum, and the repository
# guard fails on a literal date at or after the cut date, so every synthetic date here is
# a 2025 or 2024 date.
OFFICIAL_DATE = "2025-06-15"
SEASON = "2025"
AAA_OFFICIAL_DATE = "2024-05-10"
AAA_SEASON = "2024"

# The ABS certified-height identity: the top edge is 53.5% of the batter's height and the
# bottom edge 27%, so sz_top*12/0.535 and sz_bot*12/0.27 are the same number. UT-13 asserts
# the two agree within 1e-6 inches, so the fixture carries enough decimals to satisfy it.
SZ_TOP = 3.40
SZ_BOT = round(SZ_TOP * 0.27 / 0.535, 8)

# The two near-tie coordinates for DT-28. They differ by 0.0002 ft in plate_x, which is far
# below any plausible measurement distinction, and they round to 0.11 and 0.12 at two
# decimals -- so the coordinate bridge must still resolve each to exactly one row and report
# zero ambiguous matches. This is the hardest case the bridge has to survive.
NEAR_TIE_X_A = 0.1149
NEAR_TIE_X_B = 0.1151
NEAR_TIE_Z = 2.0500

# D-12: the AAA starting allotment for 2024 is three challenges per team, estimated as the
# per-game maximum of `remaining` observed across the play-by-play. The end-of-game block is
# not a reliable estimator and disagreement with it is an audit row, not a correction.
AAA_ALLOTMENT = 3

# The play-by-play path that carries the per-event remaining-challenge snapshot in the AAA
# fixture. Declared once so that phase 02 can re-point it at the real AAA key path after
# UT-20 has run against a cached AAA feed, without touching the rest of the generator.
AAA_REMAINING_PATH = "liveData.plays.allPlays[].playEvents[].reviewDetails.remainingChallenges"

# Call codes that a called (non-swung, non-in-play) pitch can carry. UT-06 requires the
# pitch a play-level MJ resolves to be one of these.
CALLED_CODES = ("C", "B", "*B")

_JSON_KWARGS = {"indent": 2, "sort_keys": False, "ensure_ascii": True}


def _player(pid: int, name: str) -> dict:
    return {"id": pid, "fullName": name, "link": f"/api/v1/people/{pid}"}


def _pitch_event(
    *,
    index: int,
    pitch_number: int,
    code: str,
    call_description: str,
    plate_x: float | None,
    plate_z: float | None,
    balls: int,
    strikes: int,
    outs: int,
    play_id: str,
    has_review: bool = False,
    review_details: dict | None = None,
    pitch_type: str = "FF",
    start_speed: float = 93.4,
) -> dict:
    """One isPitch playEvent, GUMBO-shaped."""
    details = {
        "call": {"code": code, "description": call_description},
        "description": call_description,
        "code": code,
        "isInPlay": code == "X",
        "isStrike": code in ("C", "S", "F"),
        "isBall": code in ("B", "*B", "VB"),
        "type": {"code": pitch_type, "description": "Four-Seam Fastball"},
        "hasReview": has_review,
    }
    if plate_x is None:
        # An untracked event -- an intentional ball or an automatic ball. Hawk-Eye emits no
        # coordinates, and the matching Statcast row has blank sz_top, sz_bot, plate_x and
        # pitch_type. Coercing these to numbers is the bug the data contract warns about.
        pitch_data: dict = {"coordinates": {}}
    else:
        pitch_data = {
            "startSpeed": start_speed,
            "coordinates": {"pX": plate_x, "pZ": plate_z},
            "strikeZoneTop": SZ_TOP,
            "strikeZoneBottom": SZ_BOT,
        }
    event = {
        "details": details,
        "count": {"balls": balls, "strikes": strikes, "outs": outs},
        "pitchData": pitch_data,
        "index": index,
        "playId": play_id,
        "pitchNumber": pitch_number,
        "isPitch": True,
        "type": "pitch",
    }
    if review_details is not None:
        event["reviewDetails"] = review_details
    return event


def _action_event(
    *, index: int, event_type: str, description: str, balls: int, strikes: int, outs: int
) -> dict:
    """A non-pitch action event. isPitch is false, and there is no pitchNumber at all."""
    return {
        "details": {
            "description": description,
            "event": description,
            "eventType": event_type,
            "hasReview": False,
        },
        "count": {"balls": balls, "strikes": strikes, "outs": outs},
        "index": index,
        "isPitch": False,
        "type": "action",
    }


def _play(
    *,
    at_bat_index: int,
    event: str,
    event_type: str,
    description: str,
    balls: int,
    strikes: int,
    outs: int,
    has_review: bool,
    play_events: list,
    review_details: dict | None = None,
) -> dict:
    batter_id = BATTER_IDS[at_bat_index + 1]
    play = {
        "result": {
            "type": "atBat",
            "event": event,
            "eventType": event_type,
            "description": description,
            "rbi": 0,
            "awayScore": 0,
            "homeScore": 0,
        },
        "about": {
            "atBatIndex": at_bat_index,
            "halfInning": "top",
            "isTopInning": True,
            "inning": 1 + at_bat_index // 3,
            "isComplete": True,
            "isScoringPlay": False,
            "hasReview": has_review,
            "hasOut": event_type in ("strikeout", "field_out"),
        },
        "count": {"balls": balls, "strikes": strikes, "outs": outs},
        "matchup": {
            "batter": _player(batter_id, f"Synthetic Batter {at_bat_index + 1}"),
            "batSide": {"code": "R", "description": "Right"},
            "pitcher": _player(PITCHER_ID, "Synthetic Pitcher"),
            "pitchHand": {"code": "R", "description": "Right"},
        },
        "pitchIndex": [e["index"] for e in play_events if e["isPitch"]],
        "actionIndex": [e["index"] for e in play_events if not e["isPitch"]],
        "runnerIndex": [],
        "playEvents": play_events,
        "playEndTime": f"{OFFICIAL_DATE}T20:{10 + at_bat_index:02d}:00.000Z",
        "atBatIndex": at_bat_index,
    }
    if review_details is not None:
        play["reviewDetails"] = review_details
    return play


def _play_id(at_bat_index: int, pitch_seq: int) -> str:
    """A deterministic, obviously synthetic UUID-shaped play id."""
    return f"00000000-0000-4000-8000-{GAME_PK:06d}{at_bat_index:03d}{pitch_seq:03d}"


# ---------------------------------------------------------------------------
# The MLB feed: eight plays carrying the seven traps.
# ---------------------------------------------------------------------------


def build_mlb_feed() -> dict:
    plays = []

    # Play 0. A clean strikeout. No trap. It is here so that a consumer that gets every
    # trap right but breaks the ordinary case still fails.
    plays.append(
        _play(
            at_bat_index=0,
            event="Strikeout",
            event_type="strikeout",
            description="Synthetic Batter 1 strikes out swinging.",
            balls=1,
            strikes=3,
            outs=1,
            has_review=False,
            play_events=[
                _pitch_event(
                    index=0,
                    pitch_number=1,
                    code="C",
                    call_description="Called Strike",
                    plate_x=0.20,
                    plate_z=2.30,
                    balls=0,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(0, 1),
                ),
                # "*B" is a called ball in the dirt. It is a called pitch and UT-06 admits it,
                # so the fixture carries one to keep it out of nobody's classifier.
                _pitch_event(
                    index=1,
                    pitch_number=2,
                    code="*B",
                    call_description="Ball In Dirt",
                    plate_x=-1.20,
                    plate_z=1.10,
                    balls=1,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(0, 2),
                ),
                _pitch_event(
                    index=2,
                    pitch_number=3,
                    code="S",
                    call_description="Swinging Strike",
                    plate_x=0.40,
                    plate_z=1.50,
                    balls=1,
                    strikes=2,
                    outs=0,
                    play_id=_play_id(0, 3),
                ),
            ],
        )
    )

    # TRAP 1. The automatic_ball pitch-number offset. The pitch-timer violation is an
    # action event, so it carries no pitchNumber and the feed's pitchNumber sequence runs
    # 1, 2, 3 over the three pitches. Statcast emits a row for it, so Statcast pitch_number
    # runs 1, 2, 3, 4 and is one ahead from the automatic ball onward. Joining on
    # (game_pk, at_bat_number, pitch_number) silently pairs the wrong rows.
    plays.append(
        _play(
            at_bat_index=1,
            event="Groundout",
            event_type="field_out",
            description="Synthetic Batter 2 grounds out, shortstop to first baseman.",
            balls=2,
            strikes=1,
            outs=1,
            has_review=False,
            play_events=[
                _pitch_event(
                    index=0,
                    pitch_number=1,
                    code="C",
                    call_description="Called Strike",
                    plate_x=0.10,
                    plate_z=2.60,
                    balls=0,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(1, 1),
                ),
                _action_event(
                    index=1,
                    event_type="automatic_ball",
                    description="Automatic Ball - Pitch Timer",
                    balls=1,
                    strikes=1,
                    outs=0,
                ),
                _pitch_event(
                    index=2,
                    pitch_number=2,
                    code="B",
                    call_description="Ball",
                    plate_x=-1.05,
                    plate_z=3.60,
                    balls=2,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(1, 2),
                ),
                _pitch_event(
                    index=3,
                    pitch_number=3,
                    code="X",
                    call_description="In play, out(s)",
                    plate_x=0.00,
                    plate_z=2.20,
                    balls=2,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(1, 3),
                ),
            ],
        )
    )

    # TRAP 2. The four-event intentional walk. Every event carries pitchNumber 0 and
    # details.call.code "VB", so the naive key collapses four events into one. The
    # corrected counter must still produce four distinct keys.
    plays.append(
        _play(
            at_bat_index=2,
            event="Intent Walk",
            event_type="walk",
            description="Synthetic Batter 3 intentionally walks.",
            balls=4,
            strikes=0,
            outs=0,
            has_review=False,
            play_events=[
                _pitch_event(
                    index=i,
                    pitch_number=0,
                    code="VB",
                    call_description="Intent Ball",
                    plate_x=None,
                    plate_z=None,
                    balls=i + 1,
                    strikes=0,
                    outs=0,
                    play_id=_play_id(2, i + 1),
                )
                for i in range(4)
            ],
        )
    )

    # TRAP 3. A pitch-level MJ. details.hasReview is true on the third pitch while
    # about.hasReview is false on the same play. A consumer that reads only the play-level
    # flag loses this challenge entirely. Standing: the call is a strike, so only the
    # batting team may challenge, and in a top half that is the away team.
    plays.append(
        _play(
            at_bat_index=3,
            event="Strikeout",
            event_type="strikeout",
            description="Synthetic Batter 4 called out on strikes.",
            balls=1,
            strikes=3,
            outs=1,
            has_review=False,
            play_events=[
                _pitch_event(
                    index=0,
                    pitch_number=1,
                    code="B",
                    call_description="Ball",
                    plate_x=-1.30,
                    plate_z=2.10,
                    balls=1,
                    strikes=0,
                    outs=0,
                    play_id=_play_id(3, 1),
                ),
                _pitch_event(
                    index=1,
                    pitch_number=2,
                    code="C",
                    call_description="Called Strike",
                    plate_x=0.55,
                    plate_z=2.90,
                    balls=1,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(3, 2),
                ),
                _pitch_event(
                    index=2,
                    pitch_number=3,
                    code="C",
                    call_description="Called Strike",
                    plate_x=NEAR_TIE_X_A,
                    plate_z=NEAR_TIE_Z,
                    balls=1,
                    strikes=2,
                    outs=0,
                    play_id=_play_id(3, 3),
                    has_review=True,
                    review_details={
                        "isOverturned": False,
                        "reviewType": "MJ",
                        "challengeTeamId": AWAY_TEAM_ID,
                        "player": _player(BATTER_IDS[4], "Synthetic Batter 4"),
                        "inProgress": False,
                    },
                ),
            ],
        )
    )

    # TRAP 4. A play-level MJ. about.hasReview is true and reviewDetails sits on the play,
    # not on any pitch, so the challenged pitch has to be resolved as the last isPitch
    # event. result.description says nothing about a challenge, which is why UT-08 forbids
    # text-matching it.
    plays.append(
        _play(
            at_bat_index=4,
            event="Strikeout",
            event_type="strikeout",
            description="Synthetic Batter 5 called out on strikes.",
            balls=0,
            strikes=3,
            outs=1,
            has_review=True,
            review_details={
                "isOverturned": False,
                "reviewType": "MJ",
                "challengeTeamId": AWAY_TEAM_ID,
                "player": _player(BATTER_IDS[5], "Synthetic Batter 5"),
                "inProgress": False,
            },
            play_events=[
                _pitch_event(
                    index=0,
                    pitch_number=1,
                    code="C",
                    call_description="Called Strike",
                    plate_x=0.30,
                    plate_z=2.40,
                    balls=0,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(4, 1),
                ),
                _pitch_event(
                    index=1,
                    pitch_number=2,
                    code="S",
                    call_description="Swinging Strike",
                    plate_x=0.60,
                    plate_z=1.40,
                    balls=0,
                    strikes=2,
                    outs=0,
                    play_id=_play_id(4, 2),
                ),
                _pitch_event(
                    index=2,
                    pitch_number=3,
                    code="C",
                    call_description="Called Strike",
                    plate_x=-0.83,
                    plate_z=1.82,
                    balls=0,
                    strikes=3,
                    outs=1,
                    play_id=_play_id(4, 3),
                ),
            ],
        )
    )

    # TRAP 5. An overturned challenge. details.call.code holds "C", the call AFTER the
    # challenge. The umpire called a ball, the fielding team challenged, and the call was
    # overturned to a strike. Anything that reads details.call.code as the umpire's call
    # scores this pitch as a correct strike call, which is the R-05 bias.
    plays.append(
        _play(
            at_bat_index=5,
            event="Strikeout",
            event_type="strikeout",
            description="Synthetic Batter 6 called out on strikes.",
            balls=1,
            strikes=3,
            outs=1,
            has_review=True,
            play_events=[
                _pitch_event(
                    index=0,
                    pitch_number=1,
                    code="B",
                    call_description="Ball",
                    plate_x=-1.50,
                    plate_z=2.80,
                    balls=1,
                    strikes=0,
                    outs=0,
                    play_id=_play_id(5, 1),
                ),
                _pitch_event(
                    index=1,
                    pitch_number=2,
                    code="C",
                    call_description="Called Strike",
                    plate_x=0.62,
                    plate_z=2.70,
                    balls=1,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(5, 2),
                ),
                _pitch_event(
                    index=2,
                    pitch_number=3,
                    code="C",
                    call_description="Called Strike",
                    plate_x=NEAR_TIE_X_B,
                    plate_z=NEAR_TIE_Z,
                    balls=1,
                    strikes=2,
                    outs=0,
                    play_id=_play_id(5, 3),
                    has_review=True,
                    review_details={
                        "isOverturned": True,
                        "reviewType": "MJ",
                        "challengeTeamId": HOME_TEAM_ID,
                        "player": _player(CATCHER_ID, "Synthetic Catcher"),
                        "inProgress": False,
                    },
                ),
            ],
        )
    )

    # TRAP 6. An "MF" replay record. It is a review, so it belongs to the union of review
    # locations, but reviewType is not "MJ" and it must not become a challenge.
    plays.append(
        _play(
            at_bat_index=6,
            event="Single",
            event_type="single",
            description="Synthetic Batter 7 singles on a line drive to left fielder.",
            balls=0,
            strikes=0,
            outs=0,
            has_review=True,
            review_details={
                "isOverturned": True,
                "reviewType": "MF",
                "challengeTeamId": AWAY_TEAM_ID,
                "inProgress": False,
            },
            play_events=[
                _pitch_event(
                    index=0,
                    pitch_number=1,
                    code="X",
                    call_description="In play, no out",
                    plate_x=0.00,
                    plate_z=2.50,
                    balls=0,
                    strikes=0,
                    outs=0,
                    play_id=_play_id(6, 1),
                ),
            ],
        )
    )

    # TRAP 7. An AAA-shaped MJ record: reviewDetails with no "player" key at all. The
    # consumer must yield a null challenger id and the role "unknown", and must not crash
    # on the missing key. D-12's evidence is that reviewDetails.player is absent from every
    # AAA MJ record, which is why the AAA arm is team-level only.
    plays.append(
        _play(
            at_bat_index=7,
            event="Flyout",
            event_type="field_out",
            description="Synthetic Batter 8 flies out to center fielder.",
            balls=1,
            strikes=1,
            outs=1,
            has_review=False,
            play_events=[
                _pitch_event(
                    index=0,
                    pitch_number=1,
                    code="B",
                    call_description="Ball",
                    plate_x=-1.10,
                    plate_z=3.50,
                    balls=1,
                    strikes=0,
                    outs=0,
                    play_id=_play_id(7, 1),
                ),
                _pitch_event(
                    index=1,
                    pitch_number=2,
                    code="C",
                    call_description="Called Strike",
                    plate_x=0.91,
                    plate_z=3.30,
                    balls=1,
                    strikes=1,
                    outs=0,
                    play_id=_play_id(7, 2),
                    has_review=True,
                    review_details={
                        "isOverturned": False,
                        "reviewType": "MJ",
                        "challengeTeamId": AWAY_TEAM_ID,
                        "inProgress": False,
                    },
                ),
                _pitch_event(
                    index=2,
                    pitch_number=3,
                    code="X",
                    call_description="In play, out(s)",
                    plate_x=0.05,
                    plate_z=2.45,
                    balls=1,
                    strikes=1,
                    outs=1,
                    play_id=_play_id(7, 3),
                ),
            ],
        )
    )

    return {
        "gamePk": GAME_PK,
        "gameData": {
            "game": {"pk": GAME_PK, "type": "R", "season": SEASON},
            "datetime": {"officialDate": OFFICIAL_DATE, "dayNight": "night"},
            "teams": {
                "away": {
                    "id": AWAY_TEAM_ID,
                    "abbreviation": AWAY_TEAM_CODE,
                    "name": "Synthetic Away",
                },
                "home": {
                    "id": HOME_TEAM_ID,
                    "abbreviation": HOME_TEAM_CODE,
                    "name": "Synthetic Home",
                },
            },
        },
        "liveData": {
            "plays": {"allPlays": plays, "playsByInning": []},
            "boxscore": {
                "teams": {
                    "home": {
                        "players": {
                            f"ID{PITCHER_ID}": {
                                "person": _player(PITCHER_ID, "Synthetic Pitcher"),
                                "position": {"code": "1", "abbreviation": "P"},
                            },
                            f"ID{CATCHER_ID}": {
                                "person": _player(CATCHER_ID, "Synthetic Catcher"),
                                "position": {"code": "2", "abbreviation": "C"},
                            },
                        }
                    },
                    "away": {
                        "players": {
                            f"ID{pid}": {
                                "person": _player(pid, f"Synthetic Batter {n}"),
                                "position": {"code": "7", "abbreviation": "LF"},
                            }
                            for n, pid in sorted(BATTER_IDS.items())
                        }
                    },
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# The matching Statcast CSV.
# ---------------------------------------------------------------------------

# Feed call code -> Statcast `description`. Statcast holds the FINAL, post-challenge call,
# exactly as the feed's details.call does, which is the whole reason the original call has
# to be reconstructed rather than read.
CODE_TO_DESCRIPTION = {
    "C": "called_strike",
    "B": "ball",
    "*B": "blocked_ball",
    "S": "swinging_strike",
    "F": "foul",
    "X": "hit_into_play",
    "VB": "intent_ball",
}

# Feed call code -> Statcast `type`.
CODE_TO_TYPE = {"C": "S", "S": "S", "F": "S", "B": "B", "*B": "B", "VB": "B", "X": "X"}

# The Statcast row set differs from the feed's isPitch set by exactly the automatic_ball
# rows: the feed records a pitch-timer violation as a non-pitch action, Statcast emits a
# row for it. Drop these and the two sequences align one to one, in order. This is the
# alignment rule the corrected counter has to implement.
STATCAST_ONLY_DESCRIPTIONS = ("automatic_ball",)


def _statcast_row(**kw) -> dict:
    """A 119-column row. Every column Savant leaves empty is written empty here too."""
    row = dict.fromkeys(STATCAST_COLUMNS, "")
    for k, v in kw.items():
        if k not in row:
            raise KeyError(f"{k} is not a Statcast column")
        row[k] = v
    return row


def build_statcast_rows(feed: dict) -> list[dict]:
    rows: list[dict] = []
    for play in feed["liveData"]["plays"]["allPlays"]:
        at_bat_number = play["about"]["atBatIndex"] + 1
        batter = play["matchup"]["batter"]
        pitch_number = 0
        pre_balls, pre_strikes = 0, 0
        for event in play["playEvents"]:
            if event["isPitch"]:
                code = event["details"]["call"]["code"]
                description = CODE_TO_DESCRIPTION[code]
                coords = event["pitchData"].get("coordinates", {})
                tracked = "pX" in coords
            elif event["details"].get("eventType") in STATCAST_ONLY_DESCRIPTIONS:
                code = None
                description = event["details"]["eventType"]
                coords = {}
                tracked = False
            else:
                continue
            pitch_number += 1
            last = event is play["playEvents"][-1]
            rows.append(
                _statcast_row(
                    pitch_type="FF" if tracked else "",
                    game_date=OFFICIAL_DATE,
                    release_speed=event["pitchData"]["startSpeed"] if tracked else "",
                    player_name="Pitcher, Synthetic",
                    batter=batter["id"],
                    pitcher=PITCHER_ID,
                    events=play["result"]["eventType"] if last else "",
                    description=description,
                    des=play["result"]["description"] if last else "",
                    game_type="R",
                    stand="R",
                    p_throws="R",
                    home_team=HOME_TEAM_CODE,
                    away_team=AWAY_TEAM_CODE,
                    type=CODE_TO_TYPE[code] if code else "B",
                    balls=pre_balls,
                    strikes=pre_strikes,
                    game_year=SEASON,
                    plate_x=f"{coords['pX']:.4f}" if tracked else "",
                    plate_z=f"{coords['pZ']:.4f}" if tracked else "",
                    outs_when_up=0,
                    inning=play["about"]["inning"],
                    inning_topbot="Top",
                    sz_top=f"{SZ_TOP:.8f}" if tracked else "",
                    sz_bot=f"{SZ_BOT:.8f}" if tracked else "",
                    game_pk=GAME_PK,
                    fielder_2=CATCHER_ID,
                    at_bat_number=at_bat_number,
                    pitch_number=pitch_number,
                    pitch_name="4-Seam Fastball" if tracked else "",
                    home_score=0,
                    away_score=0,
                )
            )
            pre_balls = event["count"]["balls"]
            pre_strikes = event["count"]["strikes"]
    return rows


def render_statcast_csv(rows: list[dict]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf, fieldnames=STATCAST_COLUMNS, quoting=csv.QUOTE_ALL, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# R2 fixture one: an AAA-shaped feed with a three-token allotment (D-12).
# ---------------------------------------------------------------------------


def _aaa_mj_event(
    *,
    index: int,
    pitch_number: int,
    code: str,
    plate_x: float,
    plate_z: float,
    overturned: bool,
    team_id: int,
    remaining_home: int,
    remaining_away: int,
) -> dict:
    """An AAA MJ event. Note there is no "player" key: D-12 records that
    reviewDetails.player is absent from every AAA MJ record, which is why the AAA arm is
    team-level only."""
    event = _pitch_event(
        index=index,
        pitch_number=pitch_number,
        code=code,
        call_description="Called Strike" if code == "C" else "Ball",
        plate_x=plate_x,
        plate_z=plate_z,
        balls=0,
        strikes=1,
        outs=0,
        play_id=f"00000000-0000-4000-8000-{AAA_GAME_PK:06d}{index:03d}000",
        has_review=True,
        review_details={
            "isOverturned": overturned,
            "reviewType": "MJ",
            "challengeTeamId": team_id,
            "inProgress": False,
            # The per-event snapshot D-12's estimator reads. The per-game maximum of
            # `remaining` over the play-by-play is the allotment; the end-of-game block in
            # gameData.absChallenges is not, and a disagreement is an audit row.
            "remainingChallenges": {"home": remaining_home, "away": remaining_away},
        },
    )
    return event


def build_aaa_feed() -> dict:
    """Home reaches remaining 3 and its end-of-game block agrees at 3. Away also reaches
    remaining 3 but its end-of-game block implies 2, so away is the audit row."""
    specs = [
        # index, team, overturned, remaining_home, remaining_away
        (0, HOME_TEAM_ID, False, 3, 3),
        (1, AWAY_TEAM_ID, True, 2, 3),
        (2, HOME_TEAM_ID, False, 2, 3),
    ]
    plays = []
    for n, (index, team, overturned, rh, ra) in enumerate(specs):
        plays.append(
            {
                "result": {
                    "type": "atBat",
                    "event": "Strikeout",
                    "eventType": "strikeout",
                    "description": f"AAA Synthetic Batter {n + 1} called out on strikes.",
                },
                "about": {
                    "atBatIndex": n,
                    "halfInning": "top" if n % 2 == 0 else "bottom",
                    "isTopInning": n % 2 == 0,
                    "inning": n + 1,
                    "isComplete": True,
                    "hasReview": True,
                },
                "count": {"balls": 0, "strikes": 3, "outs": 1},
                "matchup": {
                    "batter": _player(8000 + n, f"AAA Synthetic Batter {n + 1}"),
                    "pitcher": _player(8100 + n, f"AAA Synthetic Pitcher {n + 1}"),
                },
                "pitchIndex": [0],
                "actionIndex": [],
                "playEvents": [
                    _aaa_mj_event(
                        index=index,
                        pitch_number=1,
                        code="C",
                        plate_x=0.35 + 0.01 * n,
                        plate_z=2.10 + 0.01 * n,
                        overturned=overturned,
                        team_id=team,
                        remaining_home=rh,
                        remaining_away=ra,
                    ),
                ],
                "atBatIndex": n,
            }
        )
    return {
        "gamePk": AAA_GAME_PK,
        "gameData": {
            "game": {"pk": AAA_GAME_PK, "type": "R", "season": AAA_SEASON},
            "datetime": {"officialDate": AAA_OFFICIAL_DATE},
            "teams": {
                "away": {"id": AWAY_TEAM_ID, "abbreviation": "SYA", "name": "Synthetic AAA Away"},
                "home": {"id": HOME_TEAM_ID, "abbreviation": "SYH", "name": "Synthetic AAA Home"},
            },
            # The end-of-game block. Home implies 3 and agrees with the play-by-play
            # maximum. Away implies 2 and does not, so away becomes an audit row rather
            # than a correction to the estimate.
            "absChallenges": {
                "home": {"remaining": 1, "usedFailed": 2},
                "away": {"remaining": 2, "usedFailed": 0},
            },
        },
        "liveData": {"plays": {"allPlays": plays, "playsByInning": []}},
    }


# ---------------------------------------------------------------------------
# R2 fixture two: drawer rows for the DT-28 coordinate bridge.
# ---------------------------------------------------------------------------

# The fields the Savant ABS challenge drawer returns, per D-62. isOverturned is carried
# because the drawer is what supplies the flip; the coordinate bridge exists to attach it
# to a Statcast row without the feed's playId.
DRAWER_FIELDS = (
    "game_pk",
    "play_id",
    "plate_X",
    "plate_Z",
    "strikeZoneTop",
    "strikeZoneBottom",
    "pre_ball_count",
    "pre_strike_count",
    "pitcher",
    "fielder_2",
    "isOverturned",
)


def build_drawer_rows(feed: dict, statcast_rows: list[dict]) -> list[dict]:
    """One drawer row per MJ challenge, carrying the same coordinates as the Statcast row
    it must bridge to. Two of them are the within-game near-tie."""
    out = []
    for ch in derive_challenges(feed)["challenges"]:
        sc = next(
            r
            for r in statcast_rows
            if r["at_bat_number"] == ch["at_bat_number"]
            and r["pitch_number"] == ch["statcast_pitch_number"]
        )
        out.append(
            {
                "game_pk": GAME_PK,
                "play_id": ch["play_id"],
                "plate_X": float(sc["plate_x"]),
                "plate_Z": float(sc["plate_z"]),
                "strikeZoneTop": SZ_TOP,
                "strikeZoneBottom": SZ_BOT,
                "pre_ball_count": int(sc["balls"]),
                "pre_strike_count": int(sc["strikes"]),
                "pitcher": PITCHER_ID,
                "fielder_2": CATCHER_ID,
                "isOverturned": ch["is_overturned"],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Ground truth. Everything under tests/fixtures/expected/ is produced here.
# ---------------------------------------------------------------------------


def _side(call: str) -> str:
    """Standing. A called strike is challengeable only by the batting team, a called ball
    only by the fielding team. It is asserted, never assumed."""
    return "batting" if call == "strike" else "fielding"


def _role(feed: dict, play: dict, player_id: int | None) -> str:
    if player_id is None:
        return "unknown"
    if player_id == play["matchup"]["pitcher"]["id"]:
        return "pitcher"
    if player_id == play["matchup"]["batter"]["id"]:
        return "batter"
    for team in feed["liveData"]["boxscore"]["teams"].values():
        entry = team["players"].get(f"ID{player_id}")
        if entry and entry["position"]["abbreviation"] == "C":
            return "catcher"
    return "unknown"


def derive_challenges(feed: dict) -> dict:
    """UT-04 through UT-10 in one pass, over the three review locations."""
    challenges, review_records = [], []
    for play in feed["liveData"]["plays"]["allPlays"]:
        at_bat_number = play["about"]["atBatIndex"] + 1
        pitches = [e for e in play["playEvents"] if e["isPitch"]]
        event_rd = next((e for e in play["playEvents"] if "reviewDetails" in e), None)
        event_flag = next((e for e in play["playEvents"] if e["details"].get("hasReview")), None)
        play_rd = play.get("reviewDetails")
        locations = []
        if play["about"]["hasReview"]:
            locations.append("about.hasReview")
        if event_flag is not None:
            locations.append("playEvents[].details.hasReview")
        if event_rd is not None:
            locations.append("playEvents[].reviewDetails")
        elif play_rd is not None:
            locations.append("allPlays[].reviewDetails")
        if not locations:
            continue
        rd = event_rd["reviewDetails"] if event_rd is not None else play_rd
        # Each play contributes exactly one review record, whichever of the three
        # locations flagged it and however many flagged it at once.
        review_records.append(
            {
                "at_bat_number": at_bat_number,
                "locations": locations,
                "review_type": rd["reviewType"],
            }
        )
        if rd["reviewType"] != "MJ":
            continue  # UT-09
        target = event_rd or event_flag
        resolved_by = "event"
        if target is None:
            target = pitches[-1]  # UT-06
            resolved_by = "last_isPitch"
        code = target["details"]["call"]["code"]
        assert code in CALLED_CODES, code
        call_final = "strike" if code == "C" else "ball"
        is_overturned = bool(rd["isOverturned"])
        call_original = (
            ("ball" if call_final == "strike" else "strike") if is_overturned else call_final
        )
        player = rd.get("player")
        player_id = player["id"] if player else None
        pitch_seq = pitches.index(target) + 1
        n_auto = sum(
            1
            for e in play["playEvents"][: play["playEvents"].index(target)]
            if not e["isPitch"] and e["details"].get("eventType") in STATCAST_ONLY_DESCRIPTIONS
        )
        challenges.append(
            {
                "at_bat_number": at_bat_number,
                "pitch_seq": pitch_seq,
                "statcast_pitch_number": pitch_seq + n_auto,
                "feed_pitch_number": target["pitchNumber"],
                "play_id": target["playId"],
                "review_locations": locations,
                "resolved_by": resolved_by,
                "review_type": "MJ",
                "call_code_stored": code,
                "call_final": call_final,
                "is_overturned": is_overturned,
                "call_original": call_original,
                "challenger_id": player_id,
                "challenger_role": _role(feed, play, player_id),
                "challenge_team_id": rd["challengeTeamId"],
                "standing_side": _side(call_original),
                "standing_team_id": (
                    AWAY_TEAM_ID if _side(call_original) == "batting" else HOME_TEAM_ID
                ),
            }
        )
    return {
        "n_review_records": len(review_records),
        "n_challenges": len(challenges),
        "n_filtered_non_mj": len(review_records) - len(challenges),
        "standing_is_evaluated_on": "call_original",
        "review_records": review_records,
        "challenges": challenges,
    }


def derive_pitch_keys(feed: dict, statcast_rows: list[dict]) -> dict:
    keys, naive_counts = [], {}
    for play in feed["liveData"]["plays"]["allPlays"]:
        at_bat_number = play["about"]["atBatIndex"] + 1
        pitches = [e for e in play["playEvents"] if e["isPitch"]]
        sc = [
            r
            for r in statcast_rows
            if r["at_bat_number"] == at_bat_number
            and r["description"] not in STATCAST_ONLY_DESCRIPTIONS
        ]
        assert len(pitches) == len(sc), (at_bat_number, len(pitches), len(sc))
        for seq, (event, row) in enumerate(zip(pitches, sc, strict=True), start=1):
            naive = f"{GAME_PK}-{at_bat_number}-{event['pitchNumber']}"
            naive_counts[naive] = naive_counts.get(naive, 0) + 1
            keys.append(
                {
                    "at_bat_number": at_bat_number,
                    "pitch_seq": seq,
                    "feed_pitch_number": event["pitchNumber"],
                    "statcast_pitch_number": row["pitch_number"],
                    "tracked": row["plate_x"] != "",
                    "corrected_key": f"{GAME_PK}-{at_bat_number}-{seq}",
                    "naive_key": naive,
                }
            )
    collisions = sorted(k for k, v in naive_counts.items() if v > 1)
    return {
        "alignment_rule": (
            "Drop Statcast rows whose description is automatic_ball. What remains aligns "
            "one to one, in order, with the feed's isPitch events."
        ),
        "n_pitch_events": len(keys),
        "n_distinct_corrected_keys": len({k["corrected_key"] for k in keys}),
        "n_distinct_naive_keys": len(naive_counts),
        "naive_key_collisions": collisions,
        "n_offset_pitches": sum(
            1 for k in keys if k["feed_pitch_number"] != k["statcast_pitch_number"]
        ),
        "keys": keys,
    }


def derive_aaa_allotment(aaa_feed: dict) -> dict:
    """D-12's estimator: the per-game maximum of `remaining` across the play-by-play."""
    seen = {"home": 0, "away": 0}
    for play in aaa_feed["liveData"]["plays"]["allPlays"]:
        for event in play["playEvents"]:
            rem = event.get("reviewDetails", {}).get("remainingChallenges")
            if rem:
                for side, value in rem.items():
                    seen[side] = max(seen[side], value)
    block = aaa_feed["gameData"]["absChallenges"]
    implied = {s: block[s]["remaining"] + block[s]["usedFailed"] for s in ("home", "away")}
    audit = sorted(s for s in ("home", "away") if implied[s] != seen[s])
    return {
        "remaining_path": AAA_REMAINING_PATH,
        "allotment_by_playbyplay_max": seen,
        "allotment_implied_by_end_block": implied,
        "expected_allotment": AAA_ALLOTMENT,
        "audit_rows": audit,
        "n_mj_records_without_player": sum(
            1
            for play in aaa_feed["liveData"]["plays"]["allPlays"]
            for e in play["playEvents"]
            if e.get("reviewDetails", {}).get("reviewType") == "MJ"
            and "player" not in e["reviewDetails"]
        ),
    }


def derive_drawer_bridge(drawer_rows: list[dict], statcast_rows: list[dict]) -> dict:
    """DT-28. Join on (game_pk, round(plate_X, 2), round(plate_Z, 2)) and require exactly
    one Statcast row per drawer row, with zero ambiguous and zero unmatched."""
    index: dict[tuple, list] = {}
    for row in statcast_rows:
        if row["plate_x"] == "":
            continue
        key = (row["game_pk"], round(float(row["plate_x"]), 2), round(float(row["plate_z"]), 2))
        index.setdefault(key, []).append(row["pitch_number"])
    matches, ambiguous, unmatched = [], [], []
    for row in drawer_rows:
        key = (row["game_pk"], round(row["plate_X"], 2), round(row["plate_Z"], 2))
        hits = index.get(key, [])
        if len(hits) == 1:
            matches.append({"play_id": row["play_id"], "key": list(key)})
        elif len(hits) > 1:
            ambiguous.append(row["play_id"])
        else:
            unmatched.append(row["play_id"])
    near_tie = [r["play_id"] for r in drawer_rows if r["plate_X"] in (NEAR_TIE_X_A, NEAR_TIE_X_B)]
    return {
        "join_key": "(game_pk, round(plate_X, 2), round(plate_Z, 2))",
        "n_drawer_rows": len(drawer_rows),
        "n_matched": len(matches),
        "n_ambiguous": len(ambiguous),
        "n_unmatched": len(unmatched),
        "match_rate": len(matches) / len(drawer_rows),
        "near_tie_play_ids": near_tie,
        "near_tie_raw_plate_x": [NEAR_TIE_X_A, NEAR_TIE_X_B],
        "near_tie_rounded_plate_x": [round(NEAR_TIE_X_A, 2), round(NEAR_TIE_X_B, 2)],
        "matches": matches,
        "ambiguous_play_ids": ambiguous,
        "unmatched_play_ids": unmatched,
    }


# The seven traps, with the exact locator of each one in the emitted MLB feed. A consumer
# test can point straight at these paths instead of searching the feed.
TRAPS = [
    {
        "id": 1,
        "name": "automatic_ball pitch-number offset",
        "locator": "liveData.plays.allPlays[1].playEvents[1]",
        "assertion": "isPitch false, details.eventType automatic_ball, no pitchNumber; "
        "Statcast emits a row for it, so pitch_number runs one ahead",
        "tests": ["UT-01", "UT-02"],
    },
    {
        "id": 2,
        "name": "four-event intentional walk",
        "locator": "liveData.plays.allPlays[2].playEvents[0:4]",
        "assertion": "every event pitchNumber 0 and details.call.code VB; four corrected "
        "keys, one naive key",
        "tests": ["UT-02", "UT-03"],
    },
    {
        "id": 3,
        "name": "pitch-level MJ with the play-level flag false",
        "locator": "liveData.plays.allPlays[3].playEvents[2].details.hasReview",
        "assertion": "details.hasReview true while allPlays[3].about.hasReview is false",
        "tests": ["UT-04", "UT-05"],
    },
    {
        "id": 4,
        "name": "play-level MJ with no challenge word in the description",
        "locator": "liveData.plays.allPlays[4].reviewDetails",
        "assertion": "reviewType MJ at play level, resolves to the last isPitch, and "
        "result.description does not contain 'challenged'",
        "tests": ["UT-06", "UT-08"],
    },
    {
        "id": 5,
        "name": "overturned challenge storing the post-challenge call",
        "locator": "liveData.plays.allPlays[5].playEvents[2].reviewDetails",
        "assertion": "isOverturned true while details.call.code holds C, the call after "
        "the challenge; the original call was a ball",
        "tests": ["UT-07"],
    },
    {
        "id": 6,
        "name": "MF replay record that must be filtered",
        "locator": "liveData.plays.allPlays[6].reviewDetails.reviewType",
        "assertion": "reviewType MF; it is a review record but not a challenge",
        "tests": ["UT-09"],
    },
    {
        "id": 7,
        "name": "AAA-shaped MJ record with no player key",
        "locator": "liveData.plays.allPlays[7].playEvents[1].reviewDetails",
        "assertion": "reviewType MJ with no 'player' key; challenger_id null, "
        "challenger_role unknown, no crash",
        "tests": ["UT-10"],
    },
]


def header_line(columns: list[str]) -> str:
    """The Statcast header as one line, quoted the way Savant quotes it, BOM stripped and
    newline stripped. This exact string is what DT-02 hashes."""
    buf = io.StringIO(newline="")
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="").writerow(columns)
    return buf.getvalue()


def header_sha256(columns: list[str]) -> str:
    return hashlib.sha256(header_line(columns).encode("utf-8")).hexdigest()


def _dumps(obj) -> str:
    return json.dumps(obj, **_JSON_KWARGS) + "\n"


def generate() -> dict[str, str]:
    """Every file this generator owns, as {relative path: text}. Deterministic."""
    feed = build_mlb_feed()
    statcast_rows = build_statcast_rows(feed)
    aaa_feed = build_aaa_feed()
    drawer_rows = build_drawer_rows(feed, statcast_rows)
    return {
        "generated/mlb_feed.json": _dumps(feed),
        "generated/statcast.csv": render_statcast_csv(statcast_rows),
        "generated/aaa_feed.json": _dumps(aaa_feed),
        "generated/drawer_rows.json": _dumps(drawer_rows),
        "expected/traps.json": _dumps({"n_traps": len(TRAPS), "traps": TRAPS}),
        "expected/pitch_keys.json": _dumps(derive_pitch_keys(feed, statcast_rows)),
        "expected/challenges.json": _dumps(derive_challenges(feed)),
        "expected/aaa_allotment.json": _dumps(derive_aaa_allotment(aaa_feed)),
        "expected/drawer_bridge.json": _dumps(derive_drawer_bridge(drawer_rows, statcast_rows)),
        "expected/statcast_header.json": _dumps(
            {
                "n_columns": len(STATCAST_COLUMNS),
                "encoding": STATCAST_ENCODING,
                "header_sha256": header_sha256(STATCAST_COLUMNS),
                "columns": STATCAST_COLUMNS,
            }
        ),
    }


def write(root: pathlib.Path) -> list[pathlib.Path]:
    written = []
    for rel, text in generate().items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        encoding = STATCAST_ENCODING if path.suffix == ".csv" else "utf-8"
        path.write_text(text, encoding=encoding, newline="")
        written.append(path)
    return written


# ---------------------------------------------------------------------------
# The attestation. sha256 and shape of the real cached responses, never their content.
# ---------------------------------------------------------------------------

# Phase 01 may not read a 2026 datum, so the attestation covers pre-2026 caches only. The
# 2026 exports and feeds in the cache are counted from manifest metadata and nothing else.
ATTEST_CUTOFF_SEASON = 2026

# The exact skip reason UT-20 prints when no pre-2026 real feed is cached. Fixed string.
UT20_DEFERRED_REASON = "no local real feed cached; UT-20 deferred to phase 02"


def _staging_root(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "data" / "staging"


def build_attest(repo_root: pathlib.Path, stamp: str) -> dict:
    """Read locally cached responses for their sha256 and their shape only. No value from
    any response is recorded, and nothing under data/ is copied anywhere."""
    staging = _staging_root(repo_root)
    sources: list[dict] = []

    statcast = staging / "statcast" / "mlb"
    if statcast.is_dir():
        for season_dir in sorted(p for p in statcast.iterdir() if p.is_dir()):
            if int(season_dir.name) >= ATTEST_CUTOFF_SEASON:
                continue
            files = sorted(season_dir.glob("*.csv"))
            if not files:
                continue
            shas = set()
            for f in files:
                with f.open(encoding=STATCAST_ENCODING) as fh:
                    shas.add(
                        hashlib.sha256(fh.readline().rstrip("\r\n").encode("utf-8")).hexdigest()
                    )
            sources.append(
                {
                    "kind": "statcast_export_header",
                    "season": season_dir.name,
                    "n_files": len(files),
                    "n_distinct_header_sha256": len(shas),
                    "header_sha256": sorted(shas),
                    "n_columns": len(STATCAST_COLUMNS),
                    "encoding": STATCAST_ENCODING,
                }
            )

    schedule = staging / "statsapi" / "schedule"
    if schedule.is_dir():
        for f in sorted(schedule.glob("*.json")):
            if f.stem.endswith(str(ATTEST_CUTOFF_SEASON)):
                continue
            raw = f.read_bytes()
            sources.append(
                {
                    "kind": "statsapi_schedule",
                    "path": str(f.relative_to(repo_root)),
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "top_level_keys": sorted(json.loads(raw).keys()),
                }
            )

    feeds = staging / "statsapi" / "feeds"
    pre_2026, from_2026 = 0, 0
    if feeds.is_dir():
        for season_dir in sorted(p for p in feeds.rglob("*") if p.is_dir() and p.name.isdigit()):
            n = len(list(season_dir.glob("*.json")))
            if int(season_dir.name) >= ATTEST_CUTOFF_SEASON:
                from_2026 += n
            else:
                pre_2026 += n

    fixture_sha = header_sha256(STATCAST_COLUMNS)
    cached_shas = {
        s
        for src in sources
        if src["kind"] == "statcast_export_header"
        for s in src["header_sha256"]
    }
    return {
        "schema": "fixtures_attest/1",
        "step": "W9.3",
        "stamp": stamp,
        # The stamp is when this attestation was generated. It is not a data filter and
        # nothing in the repository compares a row's date against it. Noted for the W9.7
        # static scan, which fails on a literal date used as a cut.
        "stamp_is_generation_time_not_a_data_filter": True,
        "generated_by": "tests/fixtures/synth_feed.py --attest",
        "policy": (
            "sha256 and shape of locally cached responses, never their content. Phase 01 "
            "may not read a 2026 datum, so only pre-2026 caches are read; 2026 caches are "
            "counted and nothing more. Nothing under data/ is ever copied into the "
            "repository, and no fixture is derived from a real response."
        ),
        "fixture_header_sha256": fixture_sha,
        "fixture_header_matches_cache": bool(cached_shas) and cached_shas == {fixture_sha},
        "sources": sources,
        "ut20": {
            "status": "deferred" if pre_2026 == 0 else "available",
            "reason": UT20_DEFERRED_REASON if pre_2026 == 0 else "",
            "pre_2026_gumbo_feeds_cached": pre_2026,
            "gumbo_feeds_cached_from_2026": from_2026,
            "note": (
                "UT-20 validates the generator against one locally cached real feed. It "
                "fails locally if the feed shape changes and stays green in CI, which "
                "never sees real data. A skip is recorded as a skip, not as a pass."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=str(pathlib.Path(__file__).resolve().parent),
        help="directory holding generated/ and expected/ (default: tests/fixtures)",
    )
    parser.add_argument(
        "--attest",
        default=None,
        metavar="PATH",
        help="also write the attestation to PATH, reading pre-2026 caches under data/",
    )
    parser.add_argument("--stamp", default="", help="Madrid stamp for the attestation")
    args = parser.parse_args(argv)
    for path in write(pathlib.Path(args.out)):
        print(path)
    if args.attest:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        target = pathlib.Path(args.attest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dumps(build_attest(repo_root, args.stamp)), encoding="utf-8")
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
