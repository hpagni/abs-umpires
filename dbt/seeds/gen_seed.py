"""Deterministic generator for dbt/seeds/seed_synthetic_pitches.csv (SOP W1.11).

No RNG. Every field is a closed-form function of the row index, so two runs
write the same bytes. Every official_date is on or before 2026-09-21, the last
open day, so the seed carries no held-out day.
"""

from __future__ import annotations

import csv
import datetime as dt
import sys

MLB_BASE = {
    2022: dt.date(2022, 5, 10),
    2023: dt.date(2023, 6, 14),
    2024: dt.date(2024, 7, 9),
    2025: dt.date(2025, 8, 5),
    2026: dt.date(2026, 9, 10),
}
AAA_BASE = {
    2023: dt.date(2023, 7, 18),
    2024: dt.date(2024, 6, 11),
    2025: dt.date(2025, 5, 20),
}
LAST_OPEN = dt.date(2026, 9, 21)
DESCRIPTIONS = [
    "called_strike",
    "ball",
    "blocked_ball",
    "foul",
    "hit_into_play",
    "swinging_strike",
]
PITCH_TYPES = ["FF", "SL", "CH", "CU", "SI", "FC"]

FIELDS = [
    "game_pk",
    "at_bat_number",
    "pitch_number",
    "season",
    "game_type",
    "official_date",
    "level",
    "has_abs_challenges",
    "inning",
    "inning_topbot",
    "balls",
    "strikes",
    "outs_when_up",
    "batter",
    "pitcher",
    "fielder_2",
    "stand",
    "p_throws",
    "pitch_type",
    "release_speed",
    "plate_x",
    "plate_z",
    "sz_top",
    "sz_bot",
    "description",
    "play_id",
    "delta_run_exp",
    "challenged",
    "review_level",
    "challenge_team_id",
    "challenger_id",
    "challenger_role",
    "tokens_remaining_before",
    "call_original",
    "call_final",
    "is_overturned",
]


def plan() -> list[tuple[str, int]]:
    """160 MLB rows, 32 per season, then 40 AAA rows across three seasons."""
    rows: list[tuple[str, int]] = []
    for season in (2022, 2023, 2024, 2025, 2026):
        rows.extend([("mlb", season)] * 32)
    for season, n in ((2023, 14), (2024, 13), (2025, 13)):
        rows.extend([("aaa", season)] * n)
    return rows


def build() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for i, (level, season) in enumerate(plan()):
        base = MLB_BASE[season] if level == "mlb" else AAA_BASE[season]
        official_date = base + dt.timedelta(days=i % 11)
        assert official_date <= LAST_OPEN, official_date
        has_abs = (level == "mlb" and season == 2026) or (level == "aaa" and season >= 2024)
        if i % 25 == 0:
            game_type = "S"
        elif i % 31 == 0 and season != 2026:
            game_type = "D"
        else:
            game_type = "R"
        description = DESCRIPTIONS[i % 6]
        called = description in ("called_strike", "ball", "blocked_ball")
        challenged = has_abs and called and i % 4 == 0
        overturned = challenged and i % 3 == 0
        if not challenged:
            call_original = ""
            call_final = ""
            review_level = ""
            challenge_team_id = ""
            challenger_id = ""
            challenger_role = ""
            tokens = ""
            is_overturned = ""
        else:
            call_original = description
            if overturned:
                call_final = "ball" if description == "called_strike" else "called_strike"
            else:
                call_final = description
            review_level = "event"
            challenge_team_id = 100 + (i % 30)
            challenger_role = ("batter", "pitcher", "catcher")[i % 3]
            challenger_id = 600000 + (i % 37) if challenger_role == "batter" else 500000 + (i % 29)
            tokens = 2 - (i % 3)
            is_overturned = "true" if overturned else "false"
        out.append(
            {
                "game_pk": 700000 + i * 7,
                "at_bat_number": 1 + (i % 9),
                "pitch_number": 1 + (i % 6),
                "season": season,
                "game_type": game_type,
                "official_date": official_date.isoformat(),
                "level": level,
                "has_abs_challenges": "true" if has_abs else "false",
                "inning": 1 + (i % 9),
                "inning_topbot": "Top" if i % 2 == 0 else "Bot",
                "balls": i % 4,
                "strikes": i % 3,
                "outs_when_up": i % 3,
                "batter": 600000 + (i % 37),
                "pitcher": 500000 + (i % 29),
                "fielder_2": 450000 + (i % 17),
                "stand": "L" if i % 3 == 0 else "R",
                "p_throws": "L" if i % 5 == 0 else "R",
                "pitch_type": PITCH_TYPES[i % 6],
                "release_speed": round(88.0 + (i % 70) / 10.0, 1),
                "plate_x": round(-0.9 + (i % 19) * 0.1, 2),
                "plate_z": round(1.4 + (i % 23) * 0.05, 2),
                "sz_top": round(3.30 + (i % 7) * 0.03, 2),
                "sz_bot": round(1.52 + (i % 5) * 0.02, 2),
                "description": description,
                "play_id": f"{i:08d}-0000-4000-8000-{i:012d}",
                "delta_run_exp": round(-0.20 + (i % 41) * 0.01, 3),
                "challenged": "true" if challenged else "false",
                "review_level": review_level,
                "challenge_team_id": challenge_team_id,
                "challenger_id": challenger_id,
                "challenger_role": challenger_role,
                "tokens_remaining_before": tokens,
                "call_original": call_original,
                "call_final": call_final,
                "is_overturned": is_overturned,
            }
        )
    return out


def main() -> int:
    rows = build()
    assert len(rows) == 200, len(rows)
    n_chal = sum(1 for r in rows if r["challenged"] == "true")
    n_called = sum(1 for r in rows if r["description"] in ("called_strike", "ball", "blocked_ball"))
    with open(sys.argv[1], "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"rows 200, called {n_called}, challenged {n_chal}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
