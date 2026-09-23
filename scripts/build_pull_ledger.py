#!/usr/bin/env python3
"""Build out/tables/pull_ledger.csv, the phase 02 exit artifact.

One row per completed request, from both sources this phase has:

  data/staging/manifest.jsonl   the staging cache, pulled under the same A3
                                throttle before the phase opened
  data/raw/_manifest.csv        the SOP chokepoint, src/absump/http.py

The ledger is a per-request audit trail, not a per-URL index. A URL requested
twice gets two rows, distinguished by request_seq, because the throttle and the
daily cap are spent per request. An earlier hand-built copy of this file
collapsed repeats and under-counted Savant by three.

Every row carries analysis_set, computed from quality/sql/analysis_set.sql's
predicate over the schedule on disk. A sealed row is a phase failure that the
ledger must show, not hide: the 2026 cutoff for this phase is 2026-09-21
inclusive.

This script issues no request. It reads files and writes one CSV.

Usage:
  python3 scripts/build_pull_ledger.py            write out/tables/pull_ledger.csv
  python3 scripts/build_pull_ledger.py --check    compare, write nothing, exit 1 on a difference
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from absump import seal  # noqa: E402  -- the src path is set two lines up

STAGING = os.path.join(ROOT, "data", "staging", "manifest.jsonl")
RAW = os.path.join(ROOT, "data", "raw", "_manifest.csv")
SCHEDULE_DIR = os.path.join(ROOT, "data", "staging", "statsapi", "schedule")
OUT = os.path.join(ROOT, "out", "tables", "pull_ledger.csv")

FIELDS = [
    "host",
    "url",
    "dest_path",
    "http_status",
    "bytes",
    "sha256",
    "source",
    "fetched_at_utc",
    "game_date",
    "fetched_at_src",
    "rows",
    "request_seq",
    "kind",
    "analysis_set",
]

SEAL_CONFIG = os.path.join(ROOT, "config", "seal.yml")


def seal_start() -> str:
    """The boundary, read from config/seal.yml, never written here.

    W2.4 owns that file and `absump.seal` is the library reader, but this
    script is stdlib-only by design (it runs under a bare `python3`, before
    any environment exists) and `seal.SEAL_START_DATE` parses YAML. One
    anchored regex over the one line is enough, and it keeps the boundary out
    of this file, which GD-04 rule 5 requires of every file on the analysis
    surface.
    """
    with open(SEAL_CONFIG, encoding="utf-8") as fh:
        for line in fh:
            found = re.match(r"\s*seal_start_date\s*:\s*['\"]?(\d{4}-\d{2}-\d{2})", line)
            if found:
                return found.group(1)
    raise SystemExit(f"{SEAL_CONFIG} carries no seal_start_date")


SEAL_START = seal_start()
PHASE_CUTOFF = "2026-09-21"  # this phase's 2026 cutoff, inclusive

DAY_RE = re.compile(r"game_date_gt=(\d{4}-\d{2}-\d{2})")
PK_RE = re.compile(r"/game/(\d+)/feed/live")


def host_of(url: str) -> str:
    return url.split("//", 1)[-1].split("/", 1)[0]


def kind_of(url: str) -> str:
    if "statcast_search/csv" in url:
        return "statcast_day"
    if "/feed/live" in url:
        return "feed_live"
    if "/api/v1/schedule" in url:
        return "schedule"
    if "/api/v1/teams" in url:
        return "teams"
    if "/api/v1/people" in url:
        return "people"
    if "/leaderboard/services/abs/" in url:
        return "drawer"
    if "abs-challenges" in url:
        return "leaderboard"
    if "catcher-framing" in url:
        return "framing"
    return "other"


def schedule_index() -> dict[int, tuple[int, str, str]]:
    """gamePk -> (season, game_type, official_date), from the schedules on disk."""
    index: dict[int, tuple[int, str, str]] = {}
    if not os.path.isdir(SCHEDULE_DIR):
        return index
    for name in sorted(os.listdir(SCHEDULE_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(SCHEDULE_DIR, name), encoding="utf-8") as fh:
            payload = json.load(fh)
        for day in payload.get("dates", []):
            for game in day.get("games", []):
                pk = game.get("gamePk")
                if pk is None:
                    continue
                index[int(pk)] = (
                    int(game.get("season", 0)),
                    str(game.get("gameType", "")),
                    str(game.get("officialDate", "")),
                )
    return index


def analysis_set(season: int, game_type: str, official_date: str) -> str:
    """quality/sql/analysis_set.sql, frozen at prereg-v1, in Python."""
    if game_type in ("S", "A", "E"):
        return "excluded"
    if season == 2026 and game_type == "R" and official_date >= SEAL_START:
        return seal.HELD_OUT
    if season == 2026 and game_type in ("F", "D", "L", "W"):
        return seal.HELD_OUT
    return seal.OPEN


def feed_payload(path: str) -> dict | None:
    """Read one stored GUMBO feed. data/raw holds it zstandard-compressed."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            body = fh.read()
        if path.endswith(".zst"):
            import zstandard

            body = zstandard.ZstdDecompressor().decompress(body, max_output_size=256 << 20)
        return json.loads(body)
    except Exception:
        return None


def feed_facts(path: str) -> tuple[int, str, str] | None:
    """(season, game_type, official_date) read out of a stored feed."""
    payload = feed_payload(path)
    if not payload or "gameData" not in payload:
        return None
    game = payload["gameData"].get("game", {})
    when = payload["gameData"].get("datetime", {})
    return (
        int(game.get("season", 0)),
        str(game.get("type", "")),
        str(when.get("officialDate", "")),
    )


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mtime_utc(path: str) -> str:
    stamp = dt.datetime.fromtimestamp(os.path.getmtime(path), tz=dt.UTC)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def csv_rows(path: str) -> str:
    """Data rows in a Statcast day CSV, header excluded. Blank if unreadable."""
    try:
        with open(path, "rb") as fh:
            body = fh.read()
    except OSError:
        return ""
    text = body.decode("utf-8-sig", errors="replace")  # every Savant CSV carries a BOM
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return str(max(len(lines) - 1, 0))


def prior_ledger() -> dict[str, dict[str, str]]:
    """The previous ledger, keyed by url, so a digest already taken is reused."""
    if not os.path.exists(OUT):
        return {}
    with open(OUT, newline="", encoding="utf-8") as fh:
        return {row["url"]: row for row in csv.DictReader(fh)}


def build() -> list[dict[str, str]]:
    sched = schedule_index()
    prior = prior_ledger()
    seen: dict[str, int] = {}
    out: list[dict[str, str]] = []

    def classify(url: str, path: str) -> tuple[str, str]:
        """(game_date, analysis_set) for one request.

        A feed is classified from the schedule where the schedule knows the
        gamePk, and otherwise from the stored payload's own officialDate. The
        schedule is preferred because it is the source the seal filter reads.
        """
        kind = kind_of(url)
        if kind == "statcast_day":
            day = DAY_RE.search(url)
            date = day.group(1) if day else ""
            season = int(date[:4]) if date else 0
            return date, analysis_set(season, "R", date)
        if kind == "feed_live":
            pk = PK_RE.search(url)
            facts = sched.get(int(pk.group(1))) if pk else None
            if facts is None:
                facts = feed_facts(path)
            if facts is None:
                return "", "unresolved"
            season, game_type, date = facts
            return date, analysis_set(season, game_type, date)
        return "", "n/a"

    def add(url, dest, status, size, digest, source, fetched, src_kind, rows):
        seen[url] = seen.get(url, 0) + 1
        date, aset = classify(url, os.path.join(ROOT, dest))
        out.append(
            {
                "host": host_of(url),
                "url": url,
                "dest_path": dest,
                "http_status": str(status),
                "bytes": str(size),
                "sha256": digest,
                "source": source,
                "fetched_at_utc": fetched,
                "game_date": date,
                "fetched_at_src": src_kind,
                "rows": rows,
                "request_seq": str(seen[url]),
                "kind": kind_of(url),
                "analysis_set": aset,
            }
        )

    with open(STAGING, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            url = rec["url"]
            path = rec["path"]
            rel = os.path.relpath(path, ROOT) if os.path.isabs(path) else path
            was = prior.get(url, {})
            digest = was.get("sha256") or (sha256_of(path) if os.path.exists(path) else "")
            fetched = was.get("fetched_at_utc") or (mtime_utc(path) if os.path.exists(path) else "")
            rows = was.get("rows") or (
                csv_rows(path) if kind_of(url) == "statcast_day" and os.path.exists(path) else ""
            )
            add(
                url,
                rel,
                rec.get("status", ""),
                rec.get("bytes", ""),
                digest,
                "staging",
                fetched,
                "file_mtime",
                rows,
            )

    if os.path.exists(RAW):
        with open(RAW, newline="", encoding="utf-8") as fh:
            for rec in csv.DictReader(fh):
                path = rec.get("dest_path", "")
                rel = os.path.relpath(path, ROOT) if path.startswith("/") else path
                add(
                    rec["url"],
                    rel,
                    rec.get("http_status", ""),
                    rec.get("disk_bytes") or rec.get("wire_bytes", ""),
                    rec.get("sha256", ""),
                    "live",
                    rec.get("fetched_at_utc", ""),
                    "http_manifest",
                    "",
                )

    out.sort(key=lambda r: (r["source"], r["host"], r["kind"], r["url"], r["request_seq"]))
    return out


def write(rows: list[dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, OUT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare only, write nothing")
    args = parser.parse_args()

    rows = build()
    if args.check:
        current = []
        if os.path.exists(OUT):
            with open(OUT, newline="", encoding="utf-8") as fh:
                current = list(csv.DictReader(fh))
        same = current == [dict(r) for r in rows]
        print(
            f"pull_ledger --check: {len(rows)} row(s) built, on disk {len(current)}, "
            f"{'identical' if same else 'DIFFERENT'}"
        )
        return 0 if same else 1

    write(rows)
    labels: dict[str, int] = {}
    for r in rows:
        labels[r["analysis_set"]] = labels.get(r["analysis_set"], 0) + 1
    held_out = labels.get(seal.HELD_OUT, 0)
    hosts: dict[str, int] = {}
    for r in rows:
        hosts[r["host"]] = hosts.get(r["host"], 0) + 1
    print(f"pull_ledger: {len(rows)} request row(s) -> {os.path.relpath(OUT, ROOT)}")
    for host, n in sorted(hosts.items()):
        print(f"  {host:28s} {n}")
    print(f"  held-out rows {held_out} (phase cutoff {PHASE_CUTOFF} inclusive)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
