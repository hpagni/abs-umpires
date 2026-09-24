#!/usr/bin/env python3
"""W6.4. The SSAC sprint checkpoint on the corrected join.

SOP section W6, dependency line `W6.4  corrected join      -> W2.15`.

W2.15 builds the join and owns its gate. W6.4 does not rebuild it. W6.4 asks the
one question the sprint needs answered before the abstract is drafted: is the
corrected join standing, and what are the two join slots the Methods sentence
reads from `docs/numbers.json`.

    <<N_CALLED>> called pitches in <<N_GAMES>> games through 21 September 2026,
    from batters with an ABS-measured height.

THE CORRECTION. SOP W6, "The 2026 original call": Statcast `description` and the
feed's `details.call` both carry the final, post-challenge call, so a challenged
pitch reads as a correct umpire call unless the overturns are flipped. Those
pitches sit in the shadow band where the contour is estimated (R-05). This module
measures the flip on the mart the study reads, and reports the three counts that
would be non-zero if it were missing or half applied.

THE BRIDGE. SOP W6 names the Savant ABS drawer as the bridge, joined on
(`game_pk`, round(`plate_X`, 2), round(`plate_Z`, 2)), with DT-28 asserting a
100% match and the 2,512-game feed pull as the fallback (D-62). On this machine
the fallback is already ingested, so the 2026 original call does not rest on the
bridge. DT-28 is refreshed here as a measurement of the key on the real corpus.
It is owned by `tests/data/test_join.py` and refreshed by
`tests/data/test_warehouse_pack.py`; this module records the same counts in the
sprint status so the checkpoint states them rather than implying them.

WRITES. Two paths and no others:
    docs/numbers.json         the join slots, keyed on `slot`, regenerated in
                              place. Every other entry is left untouched.
    abstract/SPRINT-STATUS.md the W6.4 block, delimited by HTML comment markers
                              so the other W6 checkpoints can hold their own
                              blocks in the same file without a collision.

Both writes are byte-compared first and skipped when nothing changed, so a
re-run leaves the tree as the first run left it.

    uv run --locked python ops/sprint_join_checkpoint.py            write
    uv run --locked python ops/sprint_join_checkpoint.py --check    verify only

--check recomputes from the warehouse when it is on disk and compares it with
the ledger. With no datum on disk it still gates the committed ledger against
the committed status block, so a clean clone proves the step. Exit 0 clean, 1 on
a failed condition or drift, 2 on a usage error.
"""

from __future__ import annotations

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
JOIN_REPORT = os.path.join(ROOT, "out", "tables", "join_report.csv")
WAREHOUSE = os.path.join(ROOT, WAREHOUSE_REL)

BEGIN = "<!-- W6.4:begin -->"
END = "<!-- W6.4:end -->"

#: The join slots, in the order they are written. `slot` is the key: a re-run
#: replaces an entry with the same slot and never appends a second copy.
SLOT_ORDER = (
    "N_CALLED",
    "N_GAMES",
    "N_JOIN_GAMES_2026",
    "N_JOIN_PITCHES_2026",
    "N_JOIN_UNMATCHED_2026",
    "N_BRIDGE_CHALLENGED_2026",
    "N_BRIDGE_NO_KEY_2026",
    "N_BRIDGE_AMBIGUOUS_2026",
)

SLOT_META = {
    "N_CALLED": (
        "counts",
        f"{WAREHOUSE_REL} main_marts.fct_called_pitch",
        "W2.17",
        "MLB regular-season called pitches, open set, batters with an ABS-measured height",
    ),
    "N_GAMES": (
        "counts",
        f"{WAREHOUSE_REL} main_marts.fct_called_pitch",
        "W2.17",
        "distinct games behind N_CALLED",
    ),
    "N_JOIN_GAMES_2026": (
        "counts",
        "out/tables/join_report.csv",
        "W2.15",
        "MLB 2026 games in the join report",
    ),
    "N_JOIN_PITCHES_2026": (
        "counts",
        "out/tables/join_report.csv",
        "W2.15",
        "MLB 2026 pitches matched on both sides of the join",
    ),
    "N_JOIN_UNMATCHED_2026": (
        "counts",
        "out/tables/join_report.csv",
        "W2.15",
        "MLB 2026 rows unmatched on either side of the join",
    ),
    "N_BRIDGE_CHALLENGED_2026": (
        "counts",
        f"{WAREHOUSE_REL} main_marts.fct_challenge",
        "W2.16",
        "challenged MLB 2026 pitches offered to the drawer bridge",
    ),
    "N_BRIDGE_NO_KEY_2026": (
        "counts",
        f"{WAREHOUSE_REL} main_staging.stg_statcast_pitches",
        "W2.14",
        "challenged MLB 2026 pitches with no bridge key",
    ),
    "N_BRIDGE_AMBIGUOUS_2026": (
        "counts",
        f"{WAREHOUSE_REL} main_staging.stg_statcast_pitches",
        "W2.14",
        "challenged MLB 2026 pitches sharing a bridge key with another called "
        "pitch in the same game",
    ),
}


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------

SQL_METHODS = """
SELECT count(*), count(DISTINCT game_pk), min(official_date), max(official_date)
FROM main_marts.fct_called_pitch
WHERE level = 'mlb' AND game_type = 'R' AND analysis_set = 'open'
  AND height_source = 'abs_measured'
"""

SQL_CORRECTION = """
SELECT count(*),
       count(*) FILTER (WHERE is_overturned),
       count(*) FILTER (WHERE call_original IS NULL),
       count(*) FILTER (WHERE is_overturned AND call_original = call_final),
       count(*) FILTER (WHERE NOT is_overturned AND call_original <> call_final)
FROM main_marts.fct_called_pitch WHERE challenged AND analysis_set = 'open'
"""

SQL_BRIDGE = """
WITH called AS (
  SELECT pitch_uid, game_pk, round(plate_x, 2) AS rx, round(plate_z, 2) AS rz,
         description
  FROM main_staging.stg_statcast_pitches
  WHERE level = 'mlb' AND season = 2026 AND plate_x IS NOT NULL
), keyed AS (
  SELECT pitch_uid,
         count(*) OVER (PARTITION BY game_pk, rx, rz) AS n_all,
         count(*) FILTER (description IN ('ball', 'called_strike'))
           OVER (PARTITION BY game_pk, rx, rz) AS n_called
  FROM called
), challenged AS (
  SELECT pitch_uid FROM main_marts.fct_challenge
  WHERE level = 'mlb' AND season = 2026 AND pitch_matched
    AND analysis_set = 'open'
)
SELECT (SELECT count(*) FROM challenged),
       (SELECT count(*) FROM challenged c LEFT JOIN keyed k USING (pitch_uid)
         WHERE k.pitch_uid IS NULL),
       (SELECT count(*) FROM challenged c JOIN keyed k USING (pitch_uid)
         WHERE k.n_called > 1),
       (SELECT count(*) FROM challenged c JOIN keyed k USING (pitch_uid)
         WHERE k.n_all > 1),
       (SELECT count(*) FROM main_staging.stg_feed_pitch
         WHERE level = 'mlb' AND season = 2026)
"""

SQL_JOIN_REPORT = """
SELECT count(*), sum(n_api), sum(n_csv), sum(n_matched),
       sum(n_api_only), sum(n_csv_only)
FROM read_csv_auto('{path}')
WHERE level = 'mlb' AND season = 2026
"""


def measure():
    """Every number this checkpoint states, or None when no datum is on disk."""
    if not os.path.exists(WAREHOUSE) or not os.path.exists(JOIN_REPORT):
        return None
    try:
        import duckdb
    except ImportError:
        return None
    con = duckdb.connect(WAREHOUSE, read_only=True)
    try:
        n_called, n_games, first_day, last_day = con.execute(SQL_METHODS).fetchone()
        ch, over, null_orig, bad_flip, bad_keep = con.execute(SQL_CORRECTION).fetchone()
        br_ch, no_key, amb_called, amb_all, fallback = con.execute(SQL_BRIDGE).fetchone()
        report = os.path.relpath(JOIN_REPORT, ROOT)
        games, api, csv, matched, api_only, csv_only = con.execute(
            SQL_JOIN_REPORT.format(path=report)
        ).fetchone()
    finally:
        con.close()
    return {
        "N_CALLED": int(n_called),
        "N_GAMES": int(n_games),
        "N_JOIN_GAMES_2026": int(games),
        "N_JOIN_PITCHES_2026": int(matched),
        "N_JOIN_UNMATCHED_2026": int(api_only) + int(csv_only),
        "N_BRIDGE_CHALLENGED_2026": int(br_ch),
        "N_BRIDGE_NO_KEY_2026": int(no_key),
        "N_BRIDGE_AMBIGUOUS_2026": int(amb_called),
        "_first_day": str(first_day),
        "_last_day": str(last_day),
        "_n_api": int(api),
        "_n_csv": int(csv),
        "_challenged": int(ch),
        "_overturned": int(over),
        "_null_original": int(null_orig),
        "_bad_flip": int(bad_flip),
        "_bad_keep": int(bad_keep),
        "_ambiguous_any": int(amb_all),
        "_fallback_rows": int(fallback),
    }


def conditions(m) -> list:
    """The checkpoint's own acceptance conditions. Empty list means standing."""
    bad = []
    if m["_n_api"] != m["_n_csv"]:
        bad.append(f"join report: n_api {m['_n_api']} against n_csv {m['_n_csv']}")
    if m["N_JOIN_PITCHES_2026"] != m["_n_api"]:
        bad.append("join report: matched rows do not equal the feed-side rows")
    if m["N_JOIN_UNMATCHED_2026"] != 0:
        bad.append(f"join report: {m['N_JOIN_UNMATCHED_2026']} unmatched rows")
    if m["_null_original"] != 0:
        bad.append(f"{m['_null_original']} challenged pitches carry no call_original")
    if m["_bad_flip"] != 0:
        bad.append(f"{m['_bad_flip']} overturns were not flipped")
    if m["_bad_keep"] != 0:
        bad.append(f"{m['_bad_keep']} upheld calls were flipped")
    if m["_overturned"] <= 0:
        bad.append("no overturn is reconstructed, so the correction did not run")
    if m["N_BRIDGE_NO_KEY_2026"] != 0:
        bad.append(f"{m['N_BRIDGE_NO_KEY_2026']} challenged pitches have no bridge key")
    if m["_fallback_rows"] <= 0:
        bad.append("the feed-pull fallback D-62 names is not ingested")
    if m["N_CALLED"] <= 0 or m["N_GAMES"] <= 0:
        bad.append("the Methods slots are empty")
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
    """The ledger with the join slots replaced in place, as bytes."""
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
                "carried_by": "W6.4",
            }
        )
    data["entries"] = kept + fresh
    data["_join_slots"] = (
        "The entries carrying a `slot` key from SLOT_ORDER in "
        "ops/sprint_join_checkpoint.py are the join slots. W6.4 regenerates them "
        "in place and leaves every other entry alone. A later generator that "
        "rewrites `entries` wholesale must carry them forward or re-run W6.4."
    )
    data["_state"] = (
        "The join slots are filled. W6.4 carried them from the join and the "
        "warehouse. The chapter-one model slots are still empty and fill on the "
        "first export run."
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
    s = slots
    lines = [
        BEGIN,
        "",
        "## W6.4 The corrected join",
        "",
        "Generator: `ops/sprint_join_checkpoint.py`. Dependency: W2.15.",
        "",
        "The corrected join is standing. The Methods sentence of the abstract reads",
        "its two slots from `docs/numbers.json`, and they are filled: {a} called".format(
            a=f"{s['N_CALLED']:,}"
        ),
        "pitches in {b} games, MLB regular seasons, open set, batters with an".format(
            b=f"{s['N_GAMES']:,}"
        ),
        "ABS-measured height.",
        "",
        "The correction is the flip of the overturned calls. Statcast `description`",
        "and the feed's `details.call` both record the final call, so an unflipped",
        "challenged pitch reads as a correct umpire call. Those pitches sit in the",
        "shadow band where the contour is estimated, which is R-05. Every challenged",
        "pitch in the mart carries `call_original`, `call_final` and `is_overturned`",
        "as three columns, and no row disagrees with the rule in either direction.",
        "",
        "| measure | value | source |",
        "|---|---|---|",
        "| join, MLB 2026 games | {v} | `out/tables/join_report.csv` |".format(
            v=f"{s['N_JOIN_GAMES_2026']:,}"
        ),
        "| join, pitches matched both sides | {v} | `out/tables/join_report.csv` |".format(
            v=f"{s['N_JOIN_PITCHES_2026']:,}"
        ),
        "| join, rows unmatched either side | {v} | `out/tables/join_report.csv` |".format(
            v=f"{s['N_JOIN_UNMATCHED_2026']:,}"
        ),
        "| called pitches, ABS-measured height | {v} | `fct_called_pitch` |".format(
            v=f"{s['N_CALLED']:,}"
        ),
        "| games behind that count | {v} | `fct_called_pitch` |".format(v=f"{s['N_GAMES']:,}"),
        "| DT-28, challenged pitches keyed | {v} | `stg_statcast_pitches` |".format(
            v=f"{s['N_BRIDGE_CHALLENGED_2026']:,}"
        ),
        "| DT-28, challenged pitches with no key | {v} | `stg_statcast_pitches` |".format(
            v=f"{s['N_BRIDGE_NO_KEY_2026']:,}"
        ),
        "| DT-28, key shared with another called pitch | {v} | `stg_statcast_pitches` |".format(
            v=f"{s['N_BRIDGE_AMBIGUOUS_2026']:,}"
        ),
        "",
        "DT-28 is refreshed here, not owned here. It is owned by",
        "`tests/data/test_join.py` and refreshed on the warehouse by",
        "`tests/data/test_warehouse_pack.py`. The Savant ABS drawer that DT-28's",
        "full clause needs is W4.2's pull and is not on this machine, so the clause",
        "that requires a drawer row skips. What is measured instead is the bridge key",
        "itself on the real corpus. Every challenged pitch has one. A small share of",
        "them share that key with another called pitch in the same game, and the share",
        "is published in the table above rather than assumed away.",
        "",
        "That ambiguity does not reach the sprint. D-62 names the season-wide feed pull",
        "as the fallback for the bridge, and the feed pull is already ingested on this",
        "machine. The 2026 original call is reconstructed from the feed review records,",
        "not from the drawer, so the drawer is a cross-check and not a dependency.",
        "",
        "Open item for the sprint floor: the reconciled challenge counts are W2.16's,",
        "the zone gate is W3.8's, and the three-regime number with an interval is",
        "W3.16's. W6.4 states only that the join those three read from is correct.",
        "",
        END,
    ]
    return "\n".join(lines) + "\n"


def splice(existing: str, block: str) -> str:
    """Replace the W6.4 block, or append it, leaving every other block alone."""
    if BEGIN in existing and END in existing:
        head, rest = existing.split(BEGIN, 1)
        _old, tail = rest.split(END, 1)
        return head + block.rstrip("\n") + tail
    body = existing if existing.strip() else HEADER
    if not body.endswith("\n"):
        body += "\n"
    return body + "\n" + block


def write_if_changed(path: str, text: str) -> bool:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            if fh.read() == text:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".w64.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


# --------------------------------------------------------------------------


def report(m) -> None:
    print(
        "W6.4 join: {g:,} games, {p:,} pitches matched both sides, {u} unmatched".format(
            g=m["N_JOIN_GAMES_2026"],
            p=m["N_JOIN_PITCHES_2026"],
            u=m["N_JOIN_UNMATCHED_2026"],
        )
    )
    print(
        "W6.4 correction: {c:,} challenged called pitches, {o:,} overturned and "
        "flipped, {n} without an original call".format(
            c=m["_challenged"], o=m["_overturned"], n=m["_null_original"]
        )
    )
    print(
        "W6.4 DT-28 refresh: {c:,} challenged pitches, {k} without a bridge key, "
        "{a} sharing it with another called pitch, {b} with any pitch".format(
            c=m["N_BRIDGE_CHALLENGED_2026"],
            k=m["N_BRIDGE_NO_KEY_2026"],
            a=m["N_BRIDGE_AMBIGUOUS_2026"],
            b=m["_ambiguous_any"],
        )
    )
    print(
        "W6.4 slots: N_CALLED {a:,}, N_GAMES {b:,}, {d0} to {d1}".format(
            a=m["N_CALLED"], b=m["N_GAMES"], d0=m["_first_day"], d1=m["_last_day"]
        )
    )


def main(argv) -> int:
    args = argv[1:]
    if args not in ([], ["--check"]):
        print("usage: python ops/sprint_join_checkpoint.py [--check]", file=sys.stderr)
        return 2
    check = args == ["--check"]

    if not os.path.exists(LEDGER):
        print("W6.4 FAIL: docs/numbers.json is absent")
        return 1
    data = load_ledger()
    committed = ledger_slots(data)
    measured = measure()

    if measured is None:
        if check:
            missing = [s for s in SLOT_ORDER if s not in committed]
            if missing:
                print("W6.4 FAIL: no datum on disk and the ledger is missing " + ", ".join(missing))
                return 1
            print("W6.4: no warehouse on disk, gating the committed ledger and block")
            slots = committed
        else:
            print("W6.4 FAIL: no warehouse on disk, nothing to carry into the ledger")
            return 1
    else:
        bad = conditions(measured)
        if bad:
            for line in bad:
                print(f"W6.4 FAIL: {line}")
            return 1
        slots = {s: measured[s] for s in SLOT_ORDER}
        report(measured)
        if check and committed != slots:
            for slot in SLOT_ORDER:
                if committed.get(slot) != slots[slot]:
                    print(
                        f"W6.4 FAIL: ledger {slot} is {committed.get(slot)}, "
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
                drift.append("docs/numbers.json join slots are stale")
        if existing != status_text:
            drift.append("abstract/SPRINT-STATUS.md W6.4 block is stale or absent")
        for line in drift:
            print(f"W6.4 FAIL: {line}")
        if drift:
            return 1
        print("W6.4 OK: the corrected join is standing and both artifacts are current")
        return 0

    for path, text in ((LEDGER, ledger_text), (STATUS, status_text)):
        rel = os.path.relpath(path, ROOT)
        print(f"W6.4 {'wrote' if write_if_changed(path, text) else 'unchanged'} {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
