"""absump.ledger -- what the request ledger gained while a check ran (W1.15, W4.3).

Two gates assert that they reach no host. ops/smoke.sh (W1.15) says zero
requests to any MLB or Savant host, and the W4.3 self-check
(`absump.ingest.savant_leaderboard_sweep --check`, clause W4.3.13) says its
offline path opened no connection. Both proved it by comparing the ledger before
and after, and both went red for a reason that had nothing to do with them: two
detached pulls were appending to the same data/raw/_manifest.csv through the
same chokepoint. "The ledger does not move during the check" is false whenever
a puller runs. The claim the gates need is narrower and still testable: nothing
the ledger gained during the check is the check's.

HOW GROWTH IS ATTRIBUTED. The manifest is append-only: absump.http appends,
R/lib/http.R appends, nothing rewrites. So `mark()` records the byte length of
the manifest up to its last complete line, the digest of those bytes, the
budget's per-host counts and which puller mutexes are held, and `since()`
proves the marked bytes are unchanged and reads only the rows after them. Every
added row must pass all four tests below, or it is charged to the check:

  1. its URL is not one the check names as its own (W4.3 names its 28 views);
  2. its host is one a detached puller works, statsapi.mlb.com or
     baseballsavant.mlb.com (the keys of PULLER_LOCKS);
  3. that host's puller mutex, the directory the puller takes under data/tmp,
     was held when the mark was taken or when the check ended;
  4. its fetched_at_utc falls on a UTC day the check spanned.

The budget file is rewritten in place rather than appended, so for it the rule
is per host: a host whose count moved must be a puller host whose mutex was
held. A quiet ledger adds no row and moves no count, which is the old clause
exactly. Nothing is skipped.

THE LIMIT, stated. A request the check itself made to a puller's host, while
that puller held its mutex, to an address the check does not name as its own,
would be attributed to the puller. W4.3 names all of its addresses and refuses
`absump.http.get` on its offline path besides. The smoke test has no address of
its own to name, so whenever a row is attributed the verdict carries that limit
in a line of its own, and a pass during a pull never reads as a quiet-ledger
pass.

Command line, for ops/smoke.sh:

    python -m absump.ledger mark FILE     write the mark to FILE
    python -m absump.ledger since FILE    attribute the growth; exit 0, or 1 if
                                          anything is charged to the check
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import io
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from absump import http, paths

__all__ = [
    "PULLER_LOCKS",
    "Growth",
    "Mark",
    "attribute_budget",
    "attribute_rows",
    "held_mutexes",
    "mark",
    "since",
]

#: The hosts a detached puller works, and the mutex directory each puller takes
#: under data/tmp: ops/night_statsapi.sh and absump.ingest.pull_statcast's
#: STATSAPI_LOCK_NAME for the statsapi chain, pull_statcast's LOCK_NAME for the
#: Savant chain. tests/unit/test_ledger.py pins both names to their owners.
PULLER_LOCKS: dict[str, str] = {
    "statsapi.mlb.com": ".statsapi_night.lock",
    "baseballsavant.mlb.com": ".savant_night.lock",
}

#: How many charged rows a verdict prints before it says how many more there are.
_SHOW = 10


def _utc_today() -> date:
    return datetime.now(UTC).date()


def held_mutexes() -> tuple[str, ...]:
    """The puller hosts whose mutex directory exists right now, in PULLER_LOCKS order."""
    root = paths.tmp_dir()
    return tuple(host for host, name in PULLER_LOCKS.items() if (root / name).is_dir())


def _manifest_bytes() -> bytes:
    try:
        data = http._manifest_path().read_bytes()
    except FileNotFoundError:
        return b""
    # Only whole lines: a puller may be half way through writing the last one.
    return data[: data.rfind(b"\n") + 1]


def _parse(data: bytes, *, header: bool) -> list[dict[str, str]]:
    text = io.StringIO(data.decode("utf-8"), newline="")
    fields = None if header else list(http._MANIFEST_COLUMNS)
    return [dict(row) for row in csv.DictReader(text, fieldnames=fields)]


def _budget() -> tuple[str | None, dict[str, int]]:
    try:
        state = json.loads(http._budget_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, {}
    if not isinstance(state, dict) or not isinstance(state.get("used"), dict):
        return None, {}
    return str(state.get("utc_date")), {str(k): int(v) for k, v in state["used"].items()}


@dataclasses.dataclass(frozen=True)
class Mark:
    """The ledger as a check found it."""

    manifest_bytes: int
    manifest_sha256: str
    manifest_rows: int
    budget_day: str | None
    budget_used: dict[str, int]
    held: tuple[str, ...]
    utc_day: str

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Mark:
        raw = json.loads(text)
        raw["held"] = tuple(raw["held"])
        return cls(**raw)


def mark() -> Mark:
    """Take the mark a check compares against when it ends."""
    data = _manifest_bytes()
    day, used = _budget()
    return Mark(
        manifest_bytes=len(data),
        manifest_sha256=hashlib.sha256(data).hexdigest(),
        manifest_rows=len(_parse(data, header=True)) if data else 0,
        budget_day=day,
        budget_used=used,
        held=held_mutexes(),
        utc_day=_utc_today().isoformat(),
    )


def _days(first: str, last: date) -> tuple[str, ...]:
    start = date.fromisoformat(first)
    return tuple(
        (start + timedelta(days=n)).isoformat() for n in range((last - start).days + 1)
    ) or (last.isoformat(),)


def attribute_rows(
    rows: Iterable[dict[str, str]],
    *,
    held: Iterable[str],
    days: Iterable[str],
    own_urls: Iterable[str] = (),
) -> list[str]:
    """One line per added row that is not a running puller's, naming the test it fails."""
    held_set, day_set, own = set(held), set(days), set(own_urls)
    charged: list[str] = []
    for number, row in enumerate(rows, start=1):
        host = row.get("host") or ""
        day = (row.get("fetched_at_utc") or "")[:10]
        if row.get("url") in own:
            charged.append(f"added row {number}: {row.get('url')} is one of the check's addresses")
        elif host not in PULLER_LOCKS:
            charged.append(f"added row {number}: host {host or '(none)'} is no puller's host")
        elif host not in held_set:
            charged.append(
                f"added row {number}: {host}, but {PULLER_LOCKS[host]} was not held "
                "at the start or the end of the check"
            )
        elif day not in day_set:
            charged.append(
                f"added row {number}: {host} fetched on {day or '(no date)'}, "
                f"not a UTC day the check spanned ({', '.join(sorted(day_set))})"
            )
    return charged


def attribute_budget(
    before: tuple[str | None, dict[str, int]],
    after: tuple[str | None, dict[str, int]],
    *,
    held: Iterable[str],
) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """Every host whose count moved, and one line for each that no running puller explains."""
    held_set = set(held)
    day_before, used_before = before
    day_after, used_after = after
    base = used_before if day_before == day_after else {}
    moved = {
        host: (base.get(host, 0), used_after.get(host, 0))
        for host in sorted(set(base) | set(used_after))
        if base.get(host, 0) != used_after.get(host, 0)
    }
    charged = [
        f"budget: {host} moved {old} -> {new} and no running puller holds its mutex"
        for host, (old, new) in moved.items()
        if host not in PULLER_LOCKS or host not in held_set
    ]
    return moved, charged


@dataclasses.dataclass(frozen=True)
class Growth:
    """What the ledger gained between a mark and now, and what of it is charged."""

    rows_before: int
    rows_after: int
    prefix_intact: bool
    added: tuple[dict[str, str], ...]
    budget_moved: dict[str, tuple[int, int]]
    held: tuple[str, ...]
    days: tuple[str, ...]
    own_urls: int
    charged: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.prefix_intact and not self.charged

    @property
    def quiet(self) -> bool:
        return self.prefix_intact and not self.added and not self.budget_moved

    def lines(self) -> list[str]:
        if self.quiet:
            return [f"manifest unchanged at {self.rows_after} rows, no budget count moved"]
        out: list[str] = []
        if not self.prefix_intact:
            out.append("the manifest bytes marked at the start changed: it was rewritten")
        by_host = Counter(row.get("host", "") for row in self.added)
        spread = ", ".join(f"{host} {n}" for host, n in sorted(by_host.items())) or "none"
        out.append(
            f"manifest grew from {self.rows_before} to {self.rows_after} rows during the check "
            f"({spread}); UTC days {', '.join(self.days)}; puller mutexes held: "
            f"{', '.join(PULLER_LOCKS[h] for h in self.held) or 'none'}"
        )
        if self.budget_moved:
            out.append(
                "budget moved: "
                + ", ".join(f"{h} {a} -> {b}" for h, (a, b) in self.budget_moved.items())
            )
        if self.passed:
            out.append(
                "every added row and every budget move is a running puller's: its host, its "
                "mutex held, dated a day the check spanned"
                + (f", none of the check's own {self.own_urls} addresses" if self.own_urls else "")
            )
            if not self.own_urls and self.added:
                out.append(
                    "limit: this check names no address of its own, so a request it made to "
                    "those hosts in this window would read as the puller's; the exact claim "
                    "is the quiet-ledger one"
                )
        else:
            out.extend(self.charged[:_SHOW])
            if len(self.charged) > _SHOW:
                out.append(f"... and {len(self.charged) - _SHOW} more charged to the check")
        return out


def since(start: Mark, *, own_urls: Iterable[str] = ()) -> Growth:
    """Attribute everything the ledger gained after `start` was taken."""
    own = frozenset(own_urls)
    data = _manifest_bytes()
    prefix_intact = (
        len(data) >= start.manifest_bytes
        and hashlib.sha256(data[: start.manifest_bytes]).hexdigest() == start.manifest_sha256
    )
    tail = data[start.manifest_bytes :] if prefix_intact else b""
    added = tuple(_parse(tail, header=start.manifest_bytes == 0)) if tail else ()
    held = tuple(h for h in PULLER_LOCKS if h in set(start.held) | set(held_mutexes()))
    days = _days(start.utc_day, _utc_today())
    charged = attribute_rows(added, held=held, days=days, own_urls=own)
    moved, budget_charged = attribute_budget(
        (start.budget_day, start.budget_used), _budget(), held=held
    )
    rows_after = len(_parse(data, header=True)) if data else 0
    return Growth(
        rows_before=start.manifest_rows,
        rows_after=rows_after,
        prefix_intact=prefix_intact,
        added=added,
        budget_moved=moved,
        held=held,
        days=days,
        own_urls=len(own),
        charged=tuple(charged + budget_charged),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="absump.ledger",
        description="Mark the request ledger, then attribute what it gained (W1.15, W4.3).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("mark", "since"):
        sub.add_parser(name).add_argument("file", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "mark":
        args.file.write_text(mark().to_json(), encoding="utf-8")
        return 0
    growth = since(Mark.from_json(args.file.read_text(encoding="utf-8")))
    for line in growth.lines():
        print(line)
    return 0 if growth.passed else 1


if __name__ == "__main__":
    sys.exit(main())
