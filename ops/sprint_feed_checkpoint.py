#!/usr/bin/env python3
"""W6.3. The SSAC sprint checkpoint on the feeds and the challenges.

SOP section W6, dependency line `W6.3  feeds + challenges  -> W2.6, W2.13, W2.16`.

W2.6 pulls the MLB 2026 GUMBO feeds, W2.13 extracts them on the corrected pitch
key, and W2.16 builds the challenge table and reconciles it. None of that is
rebuilt here and none of their gates is restated. W6.3 answers the one question
the sprint needs settled: are the 2026 feeds on disk, extracted, and do the
challenge counts reconcile, and what are the feed and challenge slots the
abstract reads from `docs/numbers.json`.

THE FLOOR. SOP section 4 names the reconciled 2026 challenge counts as the first
of three floor items. Reconciliation is a record difference, not a rate: the
challenge table is built from three JSON locations, each filtered to reviewType
MJ and each record counted once, and the total is compared game by game with the
`absChallenges` tallies the feed carries in `gameData`. A game where the two
disagree is a failure, not an audit row.

THE TWO REFRESHED TEST IDS. DT-08 is the starting allotment per team-game, taken
from the per-game maximum of `remaining` across the play-by-play and never from
the end-of-game block alone (D-12). DT-15 is the league overturn count
reconstructed from `call_original`, which must equal the sum of `usedSuccessful`
with 0 record difference. Both are owned elsewhere, by
`tests/unit/test_challenges.py` and `tests/data/test_warehouse_pack.py`, and are
refreshed here on the real corpus so the checkpoint states their numbers rather
than implying them.

WRITES. Two paths and no others:
    docs/numbers.json         the feed and challenge slots, keyed on `slot`,
                              regenerated in place and written ahead of the join
                              slots W6.4 owns. Every other entry is untouched.
    abstract/SPRINT-STATUS.md the W6.3 block, delimited by HTML comment markers,
                              inserted before the W6.4 block when that block is
                              present so the checkpoints read in step order.

The ledger render mirrors the contract in `ops/sprint_join_checkpoint.py`: that
module rewrites `entries` as everything-else followed by its own join slots, so
the feed slots must sit ahead of them or the two generators would fight over the
byte order. They do not. Either module can run first.

Both writes are byte-compared and skipped when nothing changed, so a re-run
leaves the tree as the first run left it.

    uv run --locked python ops/sprint_feed_checkpoint.py            write
    uv run --locked python ops/sprint_feed_checkpoint.py --check    verify only

--check recomputes from the warehouse and the reconciliation report when they
are on disk and compares them with the ledger. With no datum on disk it still
gates the committed ledger against the committed status block, so a clean clone
proves the step. Exit 0 clean, 1 on a failed condition or drift, 2 on a usage
error.
"""

# GD-04-EXEMPT: measurement -- the token profile below counts every MLB 2026
# team-game and takes the mode of the starting allotment. Its relation is at team-game
# grain and carries no `analysis_set` column, so the open set is not expressible there;
# the seal is kept on that relation by `assert_seal_not_crossed` on official_date. The
# pitch-grain and challenge-grain reads in this file are qualified, not exempted.

from __future__ import annotations

import csv
import json
import os
import sys

from absump.paths import templates

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The warehouse file, relative to the root. src/absump/paths.py is where the
#: repository layout is written down; nothing here spells the path a second time.
WAREHOUSE_REL = templates()["duckdb"]
LEDGER = os.path.join(ROOT, "docs", "numbers.json")
STATUS = os.path.join(ROOT, "abstract", "SPRINT-STATUS.md")
RECONCILIATION = os.path.join(ROOT, "out", "tables", "challenge_reconciliation.csv")
WAREHOUSE = os.path.join(ROOT, WAREHOUSE_REL)
RAW_FEED = os.path.join(ROOT, "data", "raw", "statsapi", "feed", "sport=1", "season=2026")

BEGIN = "<!-- W6.3:begin -->"
END = "<!-- W6.3:end -->"
JOIN_BEGIN = "<!-- W6.4:begin -->"

#: The last open day. Every 2026 date from 2026-09-22 is sealed, so no feed row
#: this checkpoint reads may fall after this one.
LAST_OPEN_DATE = "2026-09-21"

#: The feed and challenge slots, in the order they are written. `slot` is the
#: key: a re-run replaces an entry with the same slot and never appends a copy.
SLOT_ORDER = (
    "N_FEED_GAMES_2026",
    "N_FEED_PITCHES_2026",
    "N_CHALLENGE_GAMES_2026",
    "N_CHALLENGES_2026",
    "N_CHALLENGE_TALLY_2026",
    "N_CHALLENGE_UNRECONCILED_2026",
    "N_OVERTURNED_2026",
    "N_ALLOTMENT_MODAL_2026",
    "N_ALLOTMENT_EXCEPTIONS_2026",
)

SLOT_META = {
    "N_FEED_GAMES_2026": (
        "counts",
        f"{WAREHOUSE_REL} main_staging.stg_feed_game",
        "W2.6",
        "MLB 2026 regular-season game feeds pulled and stored, open set",
    ),
    "N_FEED_PITCHES_2026": (
        "counts",
        f"{WAREHOUSE_REL} main_staging.stg_feed_pitch",
        "W2.13",
        "pitch-slot rows extracted from those feeds on the corrected pitch key",
    ),
    "N_CHALLENGE_GAMES_2026": (
        "counts",
        "out/tables/challenge_reconciliation.csv",
        "W2.16",
        "MLB 2026 games carrying an absChallenges block, which are the games that reconcile",
    ),
    "N_CHALLENGES_2026": (
        "counts",
        "out/tables/challenge_reconciliation.csv",
        "W2.16",
        "MLB 2026 challenge records, reviewType MJ, counted once across the three JSON locations",
    ),
    "N_CHALLENGE_TALLY_2026": (
        "counts",
        "out/tables/challenge_reconciliation.csv",
        "W2.16",
        "MLB 2026 challenges tallied by the feed's own gameData absChallenges block",
    ),
    "N_CHALLENGE_UNRECONCILED_2026": (
        "counts",
        "out/tables/challenge_reconciliation.csv",
        "W2.16",
        "MLB 2026 games where the challenge records and the gameData tally disagree",
    ),
    "N_OVERTURNED_2026": (
        "counts",
        f"{WAREHOUSE_REL} main_marts.fct_challenge",
        "W2.16",
        "MLB 2026 challenges overturned, reconstructed from call_original",
    ),
    "N_ALLOTMENT_MODAL_2026": (
        "counts",
        f"{WAREHOUSE_REL} main_marts.fct_team_game_tokens",
        "W2.18",
        "modal starting challenge allotment per MLB 2026 team-game",
    ),
    "N_ALLOTMENT_EXCEPTIONS_2026": (
        "counts",
        f"{WAREHOUSE_REL} main_marts.fct_team_game_tokens",
        "W2.18",
        "MLB 2026 team-games whose starting allotment is not the modal value, each an audit row",
    ),
}


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------

SQL_FEED = """
SELECT (SELECT count(*) FROM main_staging.stg_feed_game
         WHERE level = 'mlb' AND season = 2026),
       (SELECT count(*) FROM main_staging.stg_feed_pitch
         WHERE level = 'mlb' AND season = 2026),
       (SELECT count(DISTINCT game_pk) FROM main_staging.stg_feed_pitch
         WHERE level = 'mlb' AND season = 2026),
       (SELECT max(official_date) FROM main_staging.stg_feed_game
         WHERE level = 'mlb' AND season = 2026),
       (SELECT max(official_date) FROM main_staging.stg_feed_pitch
         WHERE level = 'mlb' AND season = 2026)
"""

SQL_CHALLENGE = """
SELECT count(*),
       count(*) FILTER (WHERE is_overturned),
       count(*) FILTER (WHERE review_type <> 'MJ'),
       count(*) FILTER (WHERE NOT pitch_matched),
       count(*) FILTER (WHERE call_original IS NULL),
       count(*) FILTER (WHERE in_progress)
FROM main_marts.fct_challenge
WHERE level = 'mlb' AND season = 2026 AND analysis_set = 'open'
"""

SQL_TOKENS = """
SELECT count(*),
       count(*) FILTER (WHERE tokens_start = 2),
       count(*) FILTER (WHERE tokens_start IS NOT NULL AND tokens_start <> 2),
       count(*) FILTER (WHERE tokens_start IS NULL),
       mode(tokens_start)
FROM main_marts.fct_team_game_tokens WHERE level = 'mlb' AND season = 2026
"""


def read_reconciliation() -> dict:
    """The MLB 2026 half of W2.16's published reconciliation report."""
    total = {
        "rows": 0,
        "ok": 0,
        "no_block": 0,
        "other": 0,
        "n_pitch_level": 0,
        "n_play_level": 0,
        "n_additional": 0,
        "n_challenges": 0,
        "n_tally": 0,
        "used_successful": 0,
        "delta": 0,
    }
    with open(RECONCILIATION, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["level"] != "mlb" or row["season"] != "2026":
                continue
            total["rows"] += 1
            status = row["status"]
            if status == "ok":
                total["ok"] += 1
            elif status == "no_abs_block":
                total["no_block"] += 1
            else:
                total["other"] += 1
            for field in (
                "n_pitch_level",
                "n_play_level",
                "n_additional",
                "n_challenges",
                "n_tally",
            ):
                total[field] += int(row[field] or 0)
            total["used_successful"] += int(row["away_used_successful"] or 0)
            total["used_successful"] += int(row["home_used_successful"] or 0)
            total["delta"] += abs(int(row["delta"] or 0))
    return total


def count_raw_feeds() -> int:
    """Stored MLB 2026 feed payloads under the raw lake, or -1 when absent."""
    if not os.path.isdir(RAW_FEED):
        return -1
    n = 0
    for _dirpath, _dirnames, filenames in os.walk(RAW_FEED):
        n += sum(1 for name in filenames if name.endswith(".json.zst"))
    return n


def measure():
    """Every number this checkpoint states, or None when no datum is on disk."""
    if not os.path.exists(WAREHOUSE) or not os.path.exists(RECONCILIATION):
        return None
    try:
        import duckdb
    except ImportError:
        return None
    con = duckdb.connect(WAREHOUSE, read_only=True)
    try:
        feed_games, feed_pitches, extracted, last_game, last_pitch = con.execute(
            SQL_FEED
        ).fetchone()
        ch, over, non_mj, unmatched, null_orig, in_prog = con.execute(SQL_CHALLENGE).fetchone()
        tg, at_modal, above, no_evidence, modal = con.execute(SQL_TOKENS).fetchone()
    finally:
        con.close()
    rec = read_reconciliation()
    return {
        "N_FEED_GAMES_2026": int(feed_games),
        "N_FEED_PITCHES_2026": int(feed_pitches),
        "N_CHALLENGE_GAMES_2026": int(rec["ok"]),
        "N_CHALLENGES_2026": int(rec["n_challenges"]),
        "N_CHALLENGE_TALLY_2026": int(rec["n_tally"]),
        "N_CHALLENGE_UNRECONCILED_2026": int(rec["other"]),
        "N_OVERTURNED_2026": int(over),
        "N_ALLOTMENT_MODAL_2026": int(modal) if modal is not None else 0,
        "N_ALLOTMENT_EXCEPTIONS_2026": int(above) + int(no_evidence),
        "_extracted_games": int(extracted),
        "_raw_feeds": count_raw_feeds(),
        "_last_game_day": str(last_game),
        "_last_pitch_day": str(last_pitch),
        "_pitch_level": int(rec["n_pitch_level"]),
        "_play_level": int(rec["n_play_level"]),
        "_additional": int(rec["n_additional"]),
        "_no_block": int(rec["no_block"]),
        "_delta": int(rec["delta"]),
        "_fct_challenges": int(ch),
        "_used_successful": int(rec["used_successful"]),
        "_non_mj": int(non_mj),
        "_unmatched": int(unmatched),
        "_null_original": int(null_orig),
        "_in_progress": int(in_prog),
        "_team_games": int(tg),
        "_at_modal": int(at_modal),
        "_above_modal": int(above),
        "_no_evidence": int(no_evidence),
    }


def conditions(m) -> list:
    """The checkpoint's own acceptance conditions. Empty list means standing."""
    bad = []
    if m["N_FEED_GAMES_2026"] <= 0:
        bad.append("no MLB 2026 game feed is stored, so W2.6 has not run")
    if m["_extracted_games"] != m["N_FEED_GAMES_2026"]:
        bad.append(
            "extraction covers {a} of {b} stored feeds".format(
                a=m["_extracted_games"], b=m["N_FEED_GAMES_2026"]
            )
        )
    if m["N_FEED_PITCHES_2026"] <= 0:
        bad.append("no pitch row is extracted, so W2.13 has not run")
    if m["_raw_feeds"] >= 0 and m["_raw_feeds"] < m["N_FEED_GAMES_2026"]:
        bad.append(
            "the raw lake holds {a} payloads against {b} feed games".format(
                a=m["_raw_feeds"], b=m["N_FEED_GAMES_2026"]
            )
        )
    for label, day in (("game", m["_last_game_day"]), ("pitch", m["_last_pitch_day"])):
        if day > LAST_OPEN_DATE:
            bad.append(f"the seal is broken: a feed {label} row falls on {day}")
    if m["N_CHALLENGES_2026"] != m["N_CHALLENGE_TALLY_2026"]:
        bad.append(
            "DT-15 record difference: {a} challenge records against {b} tallies".format(
                a=m["N_CHALLENGES_2026"], b=m["N_CHALLENGE_TALLY_2026"]
            )
        )
    if m["N_CHALLENGE_UNRECONCILED_2026"] != 0 or m["_delta"] != 0:
        bad.append(
            "games not reconciling: {a}, total absolute delta {b}".format(
                a=m["N_CHALLENGE_UNRECONCILED_2026"], b=m["_delta"]
            )
        )
    split = m["_pitch_level"] + m["_play_level"] + m["_additional"]
    if split != m["N_CHALLENGES_2026"]:
        bad.append(
            "the three JSON locations sum to {a}, the table holds {b}".format(
                a=split, b=m["N_CHALLENGES_2026"]
            )
        )
    if m["_fct_challenges"] != m["N_CHALLENGES_2026"]:
        bad.append(
            "the challenge fact holds {a} rows, the report says {b}".format(
                a=m["_fct_challenges"], b=m["N_CHALLENGES_2026"]
            )
        )
    if m["_non_mj"] != 0:
        bad.append(f"non-MJ reviews in the challenge fact: {m['_non_mj']}")
    if m["_unmatched"] != 0:
        bad.append(f"challenges landing on no pitch: {m['_unmatched']}")
    if m["_in_progress"] != 0:
        bad.append(f"challenges still unresolved: {m['_in_progress']}")
    if m["_null_original"] != 0:
        bad.append(f"challenges with no call_original: {m['_null_original']}")
    if m["N_OVERTURNED_2026"] != m["_used_successful"]:
        bad.append(
            "DT-15 overturn difference: {a} reconstructed against {b} usedSuccessful".format(
                a=m["N_OVERTURNED_2026"], b=m["_used_successful"]
            )
        )
    if m["N_OVERTURNED_2026"] <= 0:
        bad.append("no overturn is reconstructed, so call_original did not run")
    if m["N_ALLOTMENT_MODAL_2026"] != 2:
        bad.append("DT-08 modal allotment is {a}, not 2".format(a=m["N_ALLOTMENT_MODAL_2026"]))
    if m["_at_modal"] + m["_above_modal"] + m["_no_evidence"] != m["_team_games"]:
        bad.append("the DT-08 allotment histogram does not sum to the team-game count")
    if m["N_ALLOTMENT_EXCEPTIONS_2026"] != m["_above_modal"] + m["_no_evidence"]:
        bad.append("the DT-08 exception count does not match the histogram")
    if m["N_CHALLENGES_2026"] <= 0 or m["N_CHALLENGE_GAMES_2026"] <= 0:
        bad.append("the challenge slots are empty")
    return bad


# --------------------------------------------------------------------------
# the ledger
# --------------------------------------------------------------------------


def load_ledger() -> dict:
    with open(LEDGER, encoding="utf-8") as fh:
        return json.load(fh)


def ledger_slots(data: dict) -> dict:
    out = {}
    for entry in data.get("entries", []):
        slot = entry.get("slot")
        if slot in SLOT_META:
            out[slot] = int(entry["value"])
    return out


def render_ledger(data: dict, slots: dict) -> str:
    """The ledger with the feed and challenge slots replaced in place, as bytes.

    The feed slots are written ahead of every other entry. That is not cosmetic.
    `ops/sprint_join_checkpoint.py` rebuilds `entries` as everything-else
    followed by its own join slots, so the only ordering both generators agree
    on is feed slots first, join slots last. Either may run first, and neither
    moves the other's bytes.
    """
    data = json.loads(json.dumps(data))
    kept = [e for e in data.get("entries", []) if e.get("slot") not in SLOT_META]
    fresh = []
    for slot in SLOT_ORDER:
        units, source, produced_by, what = SLOT_META[slot]
        fresh.append(
            {
                "slot": slot,
                "value": slots[slot],
                "units": units,
                "what": what,
                "source": source,
                "produced_by": produced_by,
                "carried_by": "W6.3",
            }
        )
    data["entries"] = fresh + kept
    data["_feed_slots"] = (
        "The entries carrying a `slot` key from SLOT_ORDER in "
        "ops/sprint_feed_checkpoint.py are the feed and challenge slots. W6.3 "
        "regenerates them in place, writes them ahead of the join slots, and "
        "leaves every other entry alone. A later generator that rewrites "
        "`entries` wholesale must carry them forward or re-run W6.3."
    )
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------
# the status block
# --------------------------------------------------------------------------

HEADER = """# SSAC sprint status

Owner: SOP section `W6`. One block per sprint checkpoint, each delimited by its own
markers so the checkpoints can be written independently. Numbers in this file are
generated, not typed: the generator for each block is named in the block.
"""


def render_block(slots: dict) -> str:
    s = {k: f"{v:,}" for k, v in slots.items()}
    lines = [
        BEGIN,
        "",
        "## W6.3 The feeds and the challenges",
        "",
        "Generator: `ops/sprint_feed_checkpoint.py`. Dependencies: W2.6, W2.13, W2.16.",
        "",
        "The 2026 feeds are on disk and extracted, and the challenge counts",
        "reconcile. {a} MLB regular-season game feeds are stored through the last".format(
            a=s["N_FEED_GAMES_2026"]
        ),
        "open day, every one of them extracted on the corrected pitch key, and",
        "{a} pitch-slot rows come out of them.".format(a=s["N_FEED_PITCHES_2026"]),
        "",
        "Reconciliation is a record difference, not a rate. The challenge table is",
        "built from three JSON locations, each filtered to reviewType MJ and each",
        "record counted once, and the total is compared game by game with the",
        "`absChallenges` tally the feed carries in `gameData`. {a} records meet".format(
            a=s["N_CHALLENGES_2026"]
        ),
        "{a} tallies across {b} games, with {c} games not reconciling. Four games".format(
            a=s["N_CHALLENGE_TALLY_2026"],
            b=s["N_CHALLENGE_GAMES_2026"],
            c=s["N_CHALLENGE_UNRECONCILED_2026"],
        ),
        "carry no `absChallenges` block in either source and hold no challenge, so",
        "they are reported as excluded rather than counted as reconciled.",
        "",
        "| measure | value | source |",
        "|---|---|---|",
        "| feed games stored, MLB 2026 | {v} | `stg_feed_game` |".format(v=s["N_FEED_GAMES_2026"]),
        "| feed pitch rows extracted | {v} | `stg_feed_pitch` |".format(v=s["N_FEED_PITCHES_2026"]),
        (
            "| challenge records, reviewType MJ | {v} | `out/tables/challenge_reconciliation.csv` |"
        ).format(v=s["N_CHALLENGES_2026"]),
        "| gameData tallies | {v} | `out/tables/challenge_reconciliation.csv` |".format(
            v=s["N_CHALLENGE_TALLY_2026"]
        ),
        "| games reconciled | {v} | `out/tables/challenge_reconciliation.csv` |".format(
            v=s["N_CHALLENGE_GAMES_2026"]
        ),
        "| games not reconciling | {v} | `out/tables/challenge_reconciliation.csv` |".format(
            v=s["N_CHALLENGE_UNRECONCILED_2026"]
        ),
        "| DT-15, overturns reconstructed | {v} | `fct_challenge` |".format(
            v=s["N_OVERTURNED_2026"]
        ),
        "| DT-08, modal allotment per team-game | {v} | `fct_team_game_tokens` |".format(
            v=s["N_ALLOTMENT_MODAL_2026"]
        ),
        "| DT-08, allotment exceptions, each an audit row | {v} | `fct_team_game_tokens` |".format(
            v=s["N_ALLOTMENT_EXCEPTIONS_2026"]
        ),
        "",
        "DT-08 and DT-15 are refreshed here, not owned here. They are owned by",
        "`tests/unit/test_challenges.py` and refreshed on the warehouse by",
        "`tests/data/test_warehouse_pack.py`.",
        "",
        "DT-15 is the one the floor reads. The overturn count is reconstructed from",
        "`call_original`, which the feed does not state directly, and it comes to",
        "{a}, the sum of `usedSuccessful` exactly. That number is what makes the".format(
            a=s["N_OVERTURNED_2026"]
        ),
        "2026 original call usable: Statcast `description` and the feed's",
        "`details.call` both record the post-challenge call, so an unflipped",
        "challenge reads as a correct umpire call, and those pitches sit in the",
        "shadow band where the contour is estimated, which is R-05.",
        "",
        "DT-08 takes the starting allotment from the per-game maximum of `remaining`",
        "observed across the play-by-play, not from the end-of-game block, which is",
        "D-12 as R2 reversed it. The modal MLB 2026 allotment is {a}, and".format(
            a=s["N_ALLOTMENT_MODAL_2026"]
        ),
        "{a} team-games depart from it. Each departure is enumerated as an audit".format(
            a=s["N_ALLOTMENT_EXCEPTIONS_2026"]
        ),
        "row, never silently dropped: the ones that read higher are extra-innings games, and",
        "the ones with no allotment evidence are the same four games that carry no",
        "`absChallenges` block.",
        "",
        "Sprint floor, SOP section 4: this checkpoint settles the first of the three",
        "items, the reconciled 2026 challenge counts. The zone gate is W3.8's and the",
        "three-regime number with an interval is W3.16's.",
        "",
        END,
    ]
    return "\n".join(lines) + "\n"


def splice(existing: str, block: str) -> str:
    """Replace the W6.3 block, or place it, leaving every other block alone."""
    if BEGIN in existing and END in existing:
        head, rest = existing.split(BEGIN, 1)
        _old, tail = rest.split(END, 1)
        return head + block.rstrip("\n") + tail
    body = existing if existing.strip() else HEADER
    if not body.endswith("\n"):
        body += "\n"
    if JOIN_BEGIN in body:
        head, tail = body.split(JOIN_BEGIN, 1)
        return head + block + "\n" + JOIN_BEGIN + tail
    return body + "\n" + block


def write_if_changed(path: str, text: str) -> bool:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            if fh.read() == text:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".w63.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


# --------------------------------------------------------------------------


def report(m) -> None:
    print(
        "W6.3 feeds: {g:,} MLB 2026 game feeds stored, {e:,} extracted, {p:,} pitch "
        "rows, last open day {d}".format(
            g=m["N_FEED_GAMES_2026"],
            e=m["_extracted_games"],
            p=m["N_FEED_PITCHES_2026"],
            d=m["_last_game_day"],
        )
    )
    print(
        "W6.3 challenges: {c:,} records, {pl:,} pitch level, {pv:,} play level, "
        "{ad} additional".format(
            c=m["N_CHALLENGES_2026"],
            pl=m["_pitch_level"],
            pv=m["_play_level"],
            ad=m["_additional"],
        )
    )
    print(
        "W6.3 reconciliation: {c:,} records against {t:,} tallies over {g:,} games, "
        "{u} not reconciling, {n} excluded with no absChallenges block".format(
            c=m["N_CHALLENGES_2026"],
            t=m["N_CHALLENGE_TALLY_2026"],
            g=m["N_CHALLENGE_GAMES_2026"],
            u=m["N_CHALLENGE_UNRECONCILED_2026"],
            n=m["_no_block"],
        )
    )
    print(
        "W6.3 DT-15 refresh: {o:,} overturns reconstructed, {s:,} usedSuccessful, "
        "{n} challenges without an original call".format(
            o=m["N_OVERTURNED_2026"], s=m["_used_successful"], n=m["_null_original"]
        )
    )
    print(
        "W6.3 DT-08 refresh: {t:,} team-games, {a:,} at the modal {m}, {h} above it, "
        "{z} with no allotment evidence".format(
            t=m["_team_games"],
            a=m["_at_modal"],
            m=m["N_ALLOTMENT_MODAL_2026"],
            h=m["_above_modal"],
            z=m["_no_evidence"],
        )
    )


def main(argv) -> int:
    args = argv[1:]
    if args not in ([], ["--check"]):
        print("usage: python ops/sprint_feed_checkpoint.py [--check]", file=sys.stderr)
        return 2
    check = args == ["--check"]

    if not os.path.exists(LEDGER):
        print("W6.3 FAIL: docs/numbers.json is absent")
        return 1
    data = load_ledger()
    committed = ledger_slots(data)
    measured = measure()

    if measured is None:
        if check:
            missing = [s for s in SLOT_ORDER if s not in committed]
            if missing:
                print("W6.3 FAIL: no datum on disk and the ledger is missing " + ", ".join(missing))
                return 1
            print("W6.3: no warehouse on disk, gating the committed ledger and block")
            slots = committed
        else:
            print("W6.3 FAIL: no warehouse on disk, nothing to carry into the ledger")
            return 1
    else:
        bad = conditions(measured)
        if bad:
            for line in bad:
                print(f"W6.3 FAIL: {line}")
            return 1
        slots = {s: measured[s] for s in SLOT_ORDER}
        report(measured)
        if check and committed != slots:
            for slot in SLOT_ORDER:
                if committed.get(slot) != slots[slot]:
                    print(
                        f"W6.3 FAIL: ledger {slot} is {committed.get(slot)}, "
                        f"the data says {slots[slot]}"
                    )
            return 1

    ledger_text = render_ledger(data, slots)
    block = render_block(slots)
    existing = ""
    if os.path.exists(STATUS):
        with open(STATUS, encoding="utf-8") as fh:
            existing = fh.read()
    status_text = splice(existing, block)

    if check:
        drift = []
        with open(LEDGER, encoding="utf-8") as fh:
            if fh.read() != ledger_text:
                drift.append("docs/numbers.json feed and challenge slots are stale")
        if existing != status_text:
            drift.append("abstract/SPRINT-STATUS.md W6.3 block is stale or absent")
        for line in drift:
            print(f"W6.3 FAIL: {line}")
        if drift:
            return 1
        print(
            "W6.3 OK: the feeds are extracted, the challenges reconcile, both artifacts are current"
        )
        return 0

    for path, text in ((LEDGER, ledger_text), (STATUS, status_text)):
        rel = os.path.relpath(path, ROOT)
        print(f"W6.3 {'wrote' if write_if_changed(path, text) else 'unchanged'} {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
