"""W6.0. The Statcast backfill runner: newest first, two nights, one chain.

SOP W6.0. The Python port of the draft's shell loop, routed through
``absump.http``. It drives the W2.9 day puller across the 2022-2026 game-days
with the 2026 cutoff at 2026-09-21. It owns the order, the resume and the stop;
it owns no endpoint, no throttle and no retry. ``absump.ingest.statcast_day``
owns the URL and the per-day assertions, ``absump.http`` owns the 10 s spacing
and the 800/day Savant cap from ``config/throttle.yml``. A second throttle
would be a second policy.

What this module guarantees, and how.

  NEWEST FIRST. The day list is derived from the schedule payloads in the lake
  and sorted descending. SOP section 10.1: "The Statcast day pull is ordered
  newest-first so 2026, 2025, 2024 and 2023 are all on disk after night one",
  which is what keeps Chapter 1's first fits from waiting on 2022.

  IDEMPOTENT. A day already in the raw lake is never requested again, and a day
  the staging manifest records as ok is never requested at all. Re-running a
  finished night costs zero requests and writes no bytes.

  RESUMABLE. The queue is recomputed from what is on disk, so an interruption
  needs no state to recover. The resume marker is written for the operator and
  for night two's log; it is a record of where the chain stopped, never the
  source of truth about what is done.

  UNDER THE CAP. The live budget is re-read before every day. The runner stops
  cleanly at the cap with a stop reason; it does not push into
  ``BudgetExceeded`` and call the traceback a plan. Two nights, not 2.8 hours.

  ONE CHAIN. The mutex is a directory under ``data/tmp``, taken here rather
  than in ``ops/night_savant.sh``, because the requests are issued here: a
  second copy started by hand, and not by the night script, is caught too.

This module starts nothing on import and nothing on ``--check``. The launch
phase runs ``ops/night_savant.sh``.

Usage:
  python -m absump.ingest.pull_statcast --check        assertions, no request
  python -m absump.ingest.pull_statcast --plan         the plan, no request
  python -m absump.ingest.pull_statcast --run          the sequential chain
  python -m absump.ingest.pull_statcast --run --max-requests 200
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as _dt
import io
import itertools
import json
import os
import sys
import tempfile
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo

from absump import http as client
from absump import paths
from absump.ingest import schedule, statcast_day

__all__ = [
    "MADRID",
    "SCOPE_SEASONS",
    "SEASONS",
    "SOP_DAY_ESTIMATE",
    "SOP_DAY_TOLERANCE",
    "SPORT_ID",
    "STEP",
    "CapState",
    "ChainBusy",
    "Plan",
    "RunReport",
    "Scope",
    "ScopeReport",
    "all_days",
    "cap_state",
    "check",
    "done_days",
    "ensure_schedules",
    "final_game_pks_by_date",
    "make_scope",
    "newest_first",
    "parse_scope",
    "plan",
    "queue",
    "read_marker",
    "resume_marker_path",
    "run",
    "run_scopes",
    "savant_host",
    "season_days",
    "staging_ok_days",
    "verify_scope",
    "write_marker",
]

STEP: Final[str] = "W6.0"

#: statsapi sportId 1 is MLB. The seasons are the ones W2.5 pulled schedules
#: for, read from that module so the two lists cannot drift apart.
SPORT_ID: Final[int] = 1
SEASONS: Final[tuple[int, ...]] = tuple(schedule.SEASONS[SPORT_ID])

#: The level this runner drives. AAA days are a different step's list.
LEVEL: Final[str] = statcast_day.LEVEL

MADRID: Final[ZoneInfo] = ZoneInfo("Europe/Madrid")

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

#: The night log directory, alongside ops/night_statsapi.sh's. logs/ is
#: gitignored, so the marker never reaches the public repository.
NIGHT_LOG_DIR: Final[Path] = REPO_ROOT / "logs" / "night_savant"

#: One chain per host. mkdir is atomic on APFS; flock is not.
LOCK_NAME: Final[str] = ".savant_night.lock"

#: A header that drifted or an endpoint that started serving an error page
#: fails every day after it too. Three in a row stops the chain rather than
#: spending the night's whole cap on the same defect.
MAX_CONSECUTIVE_FAILURES: Final[int] = 3

#: SOP W6.0 sizes the pull at "About 920 day-requests" and section 10.1 at
#: "~920". The real list is derived from the schedule and is never this number;
#: the check asserts the two agree to the tolerance the word "about" implies.
SOP_DAY_ESTIMATE: Final[int] = 920
SOP_DAY_TOLERANCE: Final[float] = 0.10

#: Why the chain stopped. Written to the marker, read by the night two log.
STOP_QUEUE_EMPTY: Final[str] = "queue-empty"
STOP_DAILY_CAP: Final[str] = "daily-cap"
STOP_MAX_REQUESTS: Final[str] = "max-requests"
STOP_FAILURES: Final[str] = "consecutive-failures"
STOP_FATAL: Final[str] = "fatal"


class ChainBusy(RuntimeError):
    """Another copy of the chain holds the mutex. One chain per host."""


# ---------------------------------------------------------------------------
# The cap, read from the one client that enforces it
# ---------------------------------------------------------------------------


def savant_host() -> str:
    """The host the W2.9 day URL names.

    Taken from that URL rather than written here, so this file carries no host
    literal and cannot name a host the day puller does not use.
    """
    return client._host_of(statcast_day.day_url(paths.LAST_OPEN_DATE))


@dataclasses.dataclass(frozen=True)
class CapState:
    """The daily cap for one host and what is left of it right now."""

    host: str
    cap: int
    used: int

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)


def cap_state(host: str | None = None) -> CapState:
    """The live cap state for the Savant host.

    The cap and the running count come from ``absump.http``, which reads
    ``config/throttle.yml`` and nothing else (SOP section 2.3: no delay, cap or
    User-Agent literal appears anywhere else in the repository). Reading the
    config again here would be a second reader of the one policy file, which is
    exactly the drift A3 was written to end.
    """
    name = host or savant_host()
    state = client._read_budget()
    used = state.get("used") if isinstance(state, dict) else None
    count = 0
    if isinstance(used, dict):
        try:
            count = int(used.get(name, 0))
        except (TypeError, ValueError):
            count = 0
    return CapState(host=name, cap=int(client._daily_cap(name)), used=count)


# ---------------------------------------------------------------------------
# The day list. Derived, never enumerated by hand.
# ---------------------------------------------------------------------------


def season_days(season: int, *, sport_id: int = SPORT_ID) -> list[_dt.date]:
    """Every open game-day of one season at one level, ascending.

    A day is in scope when a game was played on it. The schedule payload is the
    source: W2.5 stores it, this reads it, and no day list is written down in
    two places. Sealed days are dropped here as well as at the URL, so the
    cutoff is enforced before a request is planned rather than after.
    """
    payload, _source = schedule.load_payload(int(sport_id), int(season))
    games, _officials, _stats = schedule.extract(
        payload, sport_id=int(sport_id), season=int(season)
    )
    return sorted(
        {
            row["official_date"]
            for row in games
            if row["status_coded"] in schedule.PLAYED_CODES
            and row["game_type"] in schedule.GAME_TYPES
            and not paths.is_sealed(row["official_date"])
        }
    )


def all_days(seasons: Sequence[int] | None = None) -> list[_dt.date]:
    """Every open game-day 2022-2026, ascending, deduplicated."""
    found: set[_dt.date] = set()
    for season in seasons if seasons is not None else SEASONS:
        found.update(season_days(int(season)))
    return sorted(found)


def newest_first(days: Iterable[_dt.date]) -> list[_dt.date]:
    """The pull order. Descending, deduplicated, and the whole point of W6.0."""
    return sorted(set(days), reverse=True)


# ---------------------------------------------------------------------------
# What is already done
# ---------------------------------------------------------------------------


def done_days(*, level: str = LEVEL) -> set[_dt.date]:
    """Every day already in the raw lake. These are never requested again."""
    return {day for day, _path in statcast_day.raw_days(level=level)}


def staging_manifest_path(staging_root: Path | str | None = None) -> Path:
    """The staging cache's provenance file, data/staging/manifest.jsonl."""
    root = Path(staging_root) if staging_root is not None else paths.data_root() / "staging"
    return root / "manifest.jsonl"


def staging_ok_days(staging_root: Path | str | None = None, *, level: str = LEVEL) -> set[_dt.date]:
    """Every day the staging manifest records as ok, for this level.

    One JSON record per request, with `url`, `path`, `status`, `bytes` and
    `ok`. A day was retried inside the staging run, so the LAST record for a
    day wins: the three 2026 days that were saved under an early URL shape and
    marked not ok were re-pulled later in the same file and are ok.

    A record whose file is gone is not a cached day, so the file has to be
    there as well. Provenance carries over, trust does not: these days are
    re-validated against UT-14, UT-15, DT-01 and DT-02 by
    ``statcast_day.import_staging_tree`` before they reach the lake.
    """
    manifest = staging_manifest_path(staging_root)
    if not manifest.is_file():
        return set()
    marker = f"/statcast/{level}/"
    verdict: dict[_dt.date, bool] = {}
    with manifest.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            stored = str(record.get("path") or "")
            if marker not in stored:
                continue
            try:
                day = _dt.date.fromisoformat(Path(stored).stem)
            except ValueError:
                continue
            verdict[day] = bool(record.get("ok")) and Path(stored).is_file()
    return {day for day, ok in verdict.items() if ok}


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Plan:
    """The whole scope, what is done, what is queued and what tonight holds."""

    level: str
    days: tuple[_dt.date, ...]
    in_lake: frozenset[_dt.date]
    staged_ok: frozenset[_dt.date]
    queue: tuple[_dt.date, ...]
    cap: CapState

    @property
    def tonight(self) -> tuple[_dt.date, ...]:
        """The prefix of the queue that fits inside what is left of the cap."""
        return self.queue[: self.cap.remaining]

    @property
    def later(self) -> tuple[_dt.date, ...]:
        """The rest. Night two, at the next cap reset."""
        return self.queue[self.cap.remaining :]

    @property
    def nights(self) -> int:
        """Whole nights this queue needs at the cap, from a full budget."""
        if not self.queue:
            return 0
        return -(-len(self.queue) // self.cap.cap)

    def seasons_outstanding(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for day in self.queue:
            counts[day.year] = counts.get(day.year, 0) + 1
        return dict(sorted(counts.items(), reverse=True))

    def lines(self) -> list[str]:
        outstanding = self.seasons_outstanding()
        spread = " ".join(f"{season}:{count}" for season, count in outstanding.items()) or "none"
        first = self.queue[0].isoformat() if self.queue else "-"
        last = self.queue[-1].isoformat() if self.queue else "-"
        return [
            f"level {self.level} seasons {SEASONS[0]}-{SEASONS[-1]} cutoff "
            f"{paths.LAST_OPEN_DATE.isoformat()}",
            f"  game-days in scope         {len(self.days)}",
            f"  already in the lake        {len(self.in_lake)}",
            f"  recorded ok in staging     {len(self.staged_ok)}",
            f"  queue, newest first        {len(self.queue)}  {first} .. {last}",
            f"  outstanding by season      {spread}",
            f"  {self.cap.host} cap        {self.cap.used}/{self.cap.cap} used, "
            f"{self.cap.remaining} left",
            f"  tonight                    {len(self.tonight)}",
            f"  after the next cap reset   {len(self.later)}",
            f"  whole nights at the cap    {self.nights}",
        ]


def queue(
    *,
    level: str = LEVEL,
    staging_root: Path | str | None = None,
    seasons: Sequence[int] | None = None,
) -> list[_dt.date]:
    """The days still to request, newest first."""
    outstanding = set(all_days(seasons))
    outstanding -= done_days(level=level)
    outstanding -= staging_ok_days(staging_root, level=level)
    return newest_first(outstanding)


def plan(
    *,
    level: str = LEVEL,
    staging_root: Path | str | None = None,
    seasons: Sequence[int] | None = None,
) -> Plan:
    """Build the plan from disk. No request, no write."""
    days = all_days(seasons)
    lake = done_days(level=level)
    staged = staging_ok_days(staging_root, level=level)
    return Plan(
        level=level,
        days=tuple(newest_first(days)),
        in_lake=frozenset(lake),
        staged_ok=frozenset(staged),
        queue=tuple(queue(level=level, staging_root=staging_root, seasons=seasons)),
        cap=cap_state(),
    )


# ---------------------------------------------------------------------------
# The resume marker
# ---------------------------------------------------------------------------


def resume_marker_path() -> Path:
    """Where the chain records its stop. logs/ is gitignored."""
    return NIGHT_LOG_DIR / f"{STEP}-resume.json"


def madrid_stamp(moment: _dt.datetime | None = None) -> str:
    """A Madrid-stamped timestamp from the tz database. Never an offset by hand."""
    now = moment or _dt.datetime.now(tz=MADRID)
    return now.astimezone(MADRID).isoformat(timespec="seconds")


def write_marker(payload: dict[str, Any], path: Path | str | None = None) -> Path:
    """Write the resume marker atomically. Sorted keys, one trailing newline."""
    dest = Path(path) if path is not None else resume_marker_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest


def read_marker(path: Path | str | None = None) -> dict[str, Any] | None:
    """The last marker, or None when the chain has not run here yet."""
    src = Path(path) if path is not None else resume_marker_path()
    try:
        loaded = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


# ---------------------------------------------------------------------------
# The mutex. One sequential chain, never five parallel jobs.
# ---------------------------------------------------------------------------


def lock_path() -> Path:
    return paths.tmp_dir() / LOCK_NAME


def take_lock() -> Path:
    """Claim the chain. Raises ChainBusy when another copy already holds it."""
    target = lock_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.mkdir()
    except FileExistsError as exc:
        raise ChainBusy(
            f"another Savant chain holds {target}; this copy does nothing. "
            "Two chains against one host break the spacing section 2.3 fixes."
        ) from exc
    return target


def release_lock(target: Path) -> None:
    with contextlib.suppress(OSError):
        target.rmdir()


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class RunReport:
    """What one night did."""

    level: str = LEVEL
    attempted: int = 0
    pulled: int = 0
    failed: int = 0
    stop_reason: str = STOP_QUEUE_EMPTY
    queue_at_start: int = 0
    last_day_done: _dt.date | None = None
    next_day: _dt.date | None = None
    queue_remaining: int = 0
    cap_before: CapState | None = None
    cap_after: CapState | None = None
    notes: list[str] = dataclasses.field(default_factory=list)

    def marker(self) -> dict[str, Any]:
        """The marker payload. Night two reads this to say where night one stopped."""
        before = self.cap_before
        after = self.cap_after
        return {
            "step": STEP,
            "level": self.level,
            "ts_madrid": madrid_stamp(),
            "stop_reason": self.stop_reason,
            "queue_at_start": self.queue_at_start,
            "days_attempted": self.attempted,
            "days_pulled": self.pulled,
            "days_failed": self.failed,
            "last_day_done": self.last_day_done.isoformat() if self.last_day_done else None,
            "next_day": self.next_day.isoformat() if self.next_day else None,
            "queue_remaining": self.queue_remaining,
            "host": after.host if after else (before.host if before else ""),
            "cap": after.cap if after else (before.cap if before else 0),
            "used_before": before.used if before else 0,
            "used_after": after.used if after else 0,
            "notes": list(self.notes),
        }

    def lines(self) -> list[str]:
        return [
            f"run: attempted={self.attempted} pulled={self.pulled} failed={self.failed} "
            f"stop={self.stop_reason}",
            f"run: last day done {self.last_day_done.isoformat() if self.last_day_done else '-'}, "
            f"next day {self.next_day.isoformat() if self.next_day else '-'}, "
            f"{self.queue_remaining} left",
        ]


def run(
    *,
    level: str = LEVEL,
    staging_root: Path | str | None = None,
    seasons: Sequence[int] | None = None,
    max_requests: int | None = None,
    import_staging: bool = True,
    marker_path: Path | str | None = None,
    stream: Any = None,
) -> RunReport:
    """Drive the day puller over the queue, newest first, under the cap.

    One day, one request, one chain. The budget is re-read before every day, so
    the cap is respected even when another step spent part of it earlier in the
    same UTC day.
    """
    out = stream if stream is not None else sys.stdout
    lock = take_lock()
    report = RunReport(level=level)
    try:
        if import_staging:
            root = Path(staging_root) if staging_root is not None else paths.data_root() / "staging"
            if root.is_dir():
                statcast_day.import_staging_tree(root, level=level, stream=out)
            else:
                print(f"import: no staging cache at {root}", file=out)

        the_plan = plan(level=level, staging_root=staging_root, seasons=seasons)
        for line in the_plan.lines():
            print(line, file=out)

        report.queue_at_start = len(the_plan.queue)
        report.cap_before = the_plan.cap
        consecutive = 0

        for day in the_plan.queue:
            if max_requests is not None and report.attempted >= max_requests:
                report.stop_reason = STOP_MAX_REQUESTS
                break
            live = cap_state(the_plan.cap.host)
            if live.remaining <= 0:
                report.stop_reason = STOP_DAILY_CAP
                break
            report.attempted += 1
            try:
                day_report = statcast_day.pull_day(day, level=level)
            except client.BudgetExceeded as exc:
                report.attempted -= 1
                report.stop_reason = STOP_DAILY_CAP
                report.notes.append(f"{day.isoformat()}: {exc}")
                break
            except client.Fatal as exc:
                # A 403 is the host telling this client to stop. Not one bad
                # day to count towards three: the chain ends here.
                report.failed += 1
                report.stop_reason = STOP_FATAL
                note = f"FATAL {day.isoformat()}: {type(exc).__name__}: {exc}"
                report.notes.append(note)
                print(note, file=out)
                break
            except (
                client.HttpError,
                statcast_day.DayContractError,
                paths.SealViolation,
                OSError,
                ValueError,
            ) as exc:
                report.failed += 1
                consecutive += 1
                note = f"failed {day.isoformat()}: {type(exc).__name__}: {exc}"
                report.notes.append(note)
                print(note, file=out)
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    report.stop_reason = STOP_FAILURES
                    break
                continue
            consecutive = 0
            report.pulled += 1
            report.last_day_done = day
            print(
                f"pull: {day.isoformat()} {day_report.n_rows} rows, "
                f"{len(day_report.game_pks)} games, {day_report.n_untracked} untracked",
                file=out,
            )
        else:
            report.stop_reason = STOP_QUEUE_EMPTY

        left = [day for day in the_plan.queue if day not in done_days(level=level)]
        report.queue_remaining = len(left)
        report.next_day = left[0] if left else None
        report.cap_after = cap_state(the_plan.cap.host)
    finally:
        release_lock(lock)

    written = write_marker(report.marker(), marker_path)
    for line in report.lines():
        print(line, file=out)
    print(f"marker: {written}", file=out)
    return report


# ---------------------------------------------------------------------------
# The check. Every assertion this step owns, offline.
# ---------------------------------------------------------------------------


def _check_scope(the_plan: Plan, failures: list[str], notes: list[str]) -> None:
    total = len(the_plan.days)
    if total == 0:
        failures.append(
            "K-01 no game-day in scope. The schedule payloads are missing; run "
            "`python -m absump.ingest.schedule` first."
        )
        return
    sealed = [day for day in the_plan.days if paths.is_sealed(day)]
    if sealed:
        failures.append(f"K-01 {len(sealed)} day(s) past the cutoff in scope: {sealed[:5]}")
    seasons = sorted({day.year for day in the_plan.days})
    if seasons != sorted(SEASONS):
        failures.append(f"K-01 seasons in scope {seasons}, expected {sorted(SEASONS)}")
    slack = int(SOP_DAY_ESTIMATE * SOP_DAY_TOLERANCE)
    if abs(total - SOP_DAY_ESTIMATE) > slack:
        failures.append(
            f"K-01 {total} game-days in scope; SOP W6.0 sizes the pull at about "
            f"{SOP_DAY_ESTIMATE} (tolerance {slack})"
        )
    notes.append(f"K-01 scope {total} game-days, seasons {seasons[0]}-{seasons[-1]}, none sealed")


def _check_order(the_plan: Plan, failures: list[str], notes: list[str]) -> None:
    for name, sequence in (("scope", the_plan.days), ("queue", the_plan.queue)):
        bad = [(a, b) for a, b in itertools.pairwise(sequence) if a <= b]
        if bad:
            failures.append(f"K-02 {name} is not strictly newest-first at {bad[:3]}")
    if the_plan.queue and the_plan.days:
        newest_outstanding = max(
            (day for day in the_plan.days if day not in the_plan.in_lake | the_plan.staged_ok),
            default=None,
        )
        if newest_outstanding != the_plan.queue[0]:
            failures.append(
                f"K-02 queue starts at {the_plan.queue[0]}, newest outstanding day is "
                f"{newest_outstanding}"
            )
    head = the_plan.queue[0].isoformat() if the_plan.queue else "-"
    notes.append(f"K-02 newest-first holds; queue head {head}")


def _check_idempotence(the_plan: Plan, failures: list[str], notes: list[str]) -> None:
    repeated = sorted(day for day in the_plan.queue if day in the_plan.in_lake)
    if repeated:
        failures.append(
            f"K-03 {len(repeated)} day(s) already in the lake are queued: {repeated[:5]}"
        )
    restaged = sorted(day for day in the_plan.queue if day in the_plan.staged_ok)
    if restaged:
        failures.append(
            f"K-03 {len(restaged)} day(s) recorded ok in staging are queued: {restaged[:5]}"
        )
    if not the_plan.in_lake and not the_plan.staged_ok:
        failures.append(
            "K-03 nothing on disk and nothing in staging, so idempotence is not exercised. "
            "Import the staging cache first."
        )
    notes.append(
        f"K-03 {len(the_plan.in_lake)} day(s) in the lake and "
        f"{len(the_plan.staged_ok)} recorded ok in staging are all subtracted"
    )


def _check_cap(the_plan: Plan, failures: list[str], notes: list[str]) -> None:
    cap = the_plan.cap
    if cap.cap <= 0:
        failures.append(f"K-04 {cap.host} has no daily cap in config/throttle.yml")
        return
    if len(the_plan.tonight) > cap.remaining:
        failures.append(
            f"K-04 tonight holds {len(the_plan.tonight)} day(s) against {cap.remaining} left"
        )
    if tuple(the_plan.tonight) + tuple(the_plan.later) != the_plan.queue:
        failures.append("K-04 tonight and the remainder do not reconstruct the queue")
    if the_plan.tonight and the_plan.tonight != the_plan.queue[: len(the_plan.tonight)]:
        failures.append("K-04 tonight is not a prefix of the queue, so the order is lost")
    notes.append(
        f"K-04 {cap.host} {cap.used}/{cap.cap} used, tonight {len(the_plan.tonight)}, "
        f"later {len(the_plan.later)}"
    )


def _check_two_nights(the_plan: Plan, failures: list[str], notes: list[str]) -> None:
    """The SOP's claim about night one, checked against an empty lake.

    SOP W6.0: night D0 takes the cap ordered newest-first, night D1 takes the
    remaining days of 2022. Section 10.1: 2026, 2025, 2024 and 2023 are all on
    disk after night one. Checked from an empty lake, because that is the claim
    -- with 799 days already imported it would hold for any order at all.
    """
    cap = the_plan.cap.cap
    if cap <= 0 or not the_plan.days:
        return
    simulated = list(the_plan.days)
    night_one = simulated[:cap]
    night_two = simulated[cap:]
    nights = -(-len(simulated) // cap)
    if nights != 2:
        failures.append(f"K-05 the scope needs {nights} night(s) at a cap of {cap}, not 2")
    oldest_season = min(SEASONS)
    late = sorted({day.year for day in night_one})
    missed = sorted(day for day in simulated if day.year > oldest_season and day not in night_one)
    if missed:
        failures.append(
            f"K-05 {len(missed)} day(s) after {oldest_season} are not in night one: {missed[:5]}"
        )
    spill = sorted({day.year for day in night_two})
    if spill and spill != [oldest_season]:
        failures.append(f"K-05 night two spans {spill}, expected only {oldest_season}")
    notes.append(
        f"K-05 from an empty lake: night one {len(night_one)} day(s), seasons "
        f"{late[0]}-{late[-1]}, night two {len(night_two)} day(s) of {oldest_season}"
    )


def _check_lake(the_plan: Plan, failures: list[str], notes: list[str]) -> None:
    """DT-01, DT-02 and UT-14 over every day this runner has stored.

    ``verify_lake`` raises on the first day that breaks the contract. A check
    reports; it does not traceback. The exception is caught and named, so the
    gate reads one FAIL line and the receipt records which day it was.
    """
    try:
        reports = statcast_day.verify_lake(level=the_plan.level, stream=io.StringIO())
    except statcast_day.DayContractError as exc:
        failures.append(f"K-06 a stored day breaks the contract: {type(exc).__name__}: {exc}")
        return
    if not reports:
        failures.append(
            "K-06 no Statcast day in the lake, so DT-01 and DT-02 ran on nothing. "
            "The runner is not proved by an empty lake."
        )
        return
    over_cap = [r.game_date.isoformat() for r in reports if r.n_rows >= statcast_day.ROW_CAP]
    if over_cap:
        failures.append(f"K-06 DT-01 rows at or above the cap on {over_cap[:5]}")
    expected = statcast_day.expected_header_sha256()
    drifted = [r.game_date.isoformat() for r in reports if r.header_sha256 != expected]
    if drifted:
        failures.append(f"K-06 DT-02 header drift on {drifted[:5]}")
    wide = [r.game_date.isoformat() for r in reports if r.n_columns != statcast_day.COLUMN_COUNT]
    if wide:
        failures.append(f"K-06 DT-02 column count is not {statcast_day.COLUMN_COUNT} on {wide[:5]}")
    crossed = [r.game_date.isoformat() for r in reports if paths.is_sealed(r.game_date)]
    if crossed:
        failures.append(f"K-06 a stored day is past the cutoff: {crossed[:5]}")
    widest = max(reports, key=lambda report: report.n_rows)
    notes.append(
        f"K-06 DT-01 and DT-02 over {len(reports)} stored day(s): 1 header digest, "
        f"max {widest.n_rows} rows on {widest.game_date.isoformat()}, cap {statcast_day.ROW_CAP}"
    )


def _check_resume(the_plan: Plan, failures: list[str], notes: list[str]) -> None:
    """The marker round-trips, and a stopped night names the right next day."""
    stop_at = min(3, len(the_plan.queue))
    done_here = list(the_plan.queue[:stop_at])
    left = list(the_plan.queue[stop_at:])
    sample = RunReport(
        level=the_plan.level,
        attempted=stop_at,
        pulled=stop_at,
        stop_reason=STOP_DAILY_CAP,
        queue_at_start=len(the_plan.queue),
        last_day_done=done_here[-1] if done_here else None,
        next_day=left[0] if left else None,
        queue_remaining=len(left),
        cap_before=the_plan.cap,
        cap_after=the_plan.cap,
    )
    payload = sample.marker()
    with tempfile.TemporaryDirectory() as tmp:
        written = write_marker(payload, Path(tmp) / "resume.json")
        again = read_marker(written)
    if again != payload:
        failures.append("K-07 the resume marker does not round-trip")
        return
    expected_next = left[0].isoformat() if left else None
    if again.get("next_day") != expected_next:
        failures.append(
            f"K-07 the marker names next_day {again.get('next_day')}, expected {expected_next}"
        )
    if done_here and left and not (done_here[-1] > left[0]):
        failures.append("K-07 the resume point is not newest-first across the stop")
    notes.append(
        f"K-07 marker round-trips; a stop after {stop_at} day(s) resumes at {expected_next or '-'}"
    )


def check(
    *,
    level: str = LEVEL,
    staging_root: Path | str | None = None,
    seasons: Sequence[int] | None = None,
    stream: Any = None,
) -> list[str]:
    """Run every W6.0 assertion offline. Returns the failures, writes nothing."""
    out = stream if stream is not None else sys.stdout
    the_plan = plan(level=level, staging_root=staging_root, seasons=seasons)
    failures: list[str] = []
    notes: list[str] = []
    for step in (
        _check_scope,
        _check_order,
        _check_idempotence,
        _check_cap,
        _check_two_nights,
        _check_lake,
        _check_resume,
    ):
        step(the_plan, failures, notes)
    for line in the_plan.lines():
        print(line, file=out)
    for line in notes:
        print(line, file=out)
    for line in failures:
        print(f"FAIL {line}", file=out)
    print(
        f"check: {len(notes)} assertion group(s) reported, {len(failures)} failure(s)",
        file=out,
    )
    return failures


# ---------------------------------------------------------------------------
# W2.10 and the W2.9 backfill: ordered scopes, admission, header skip
# ---------------------------------------------------------------------------
#
# SOP W2.10 pulls the AAA minors CSV for 2023-2025 and the W2.9 backfill pulls
# MLB 2015-2021, the seasons before W6.0's scope. Both run as one chain under
# the same mutex as W6.0, through the same day puller and the same client, so
# the 10 s Savant spacing is one process-wide clock across both levels and the
# 800/day cap is the one in config/throttle.yml.
#
# Three rules W6.0 does not have:
#
#   ADMISSION. A day enters the lake only if its game_pk set is a subset of the
#   stored schedule's Final games for that officialDate: sportId=11 for AAA,
#   sportId=1 for MLB. The minors CSV has no level column, so for AAA this is
#   the level check. A refused day is written to the evidence log and not
#   stored; its bytes stay in the client's raw cache, so judging it again costs
#   no request.
#
#   HEADER. DT-02 holds the header byte-identical to the committed fixture. A
#   season whose header differs is recorded in the evidence log and skipped,
#   one request spent, and the chain moves to the next season. The header is
#   never "fixed".
#
#   STOPS. The daily cap ends the chain cleanly (exit 0). A 403, or any other
#   http.Fatal, ends it at once with exit 3: the host has refused this client.

SCOPE_STEP: Final[str] = "W2.10"

#: statsapi sportId per level, the schedule the admission check reads.
SPORT_BY_LEVEL: Final[dict[str, int]] = {"mlb": 1, "aaa": 11}

#: The seasons run_scopes may pull, per level. AAA is W2.5's AAA list; MLB is
#: the W2.9 backfill, every season before W6.0's 2022-2026 scope. No 2026 day,
#: sealed or open, can be named here.
SCOPE_SEASONS: Final[dict[str, tuple[int, ...]]] = {
    "aaa": tuple(schedule.SEASONS[11]),
    "mlb": tuple(range(2015, 2022)),
}

#: The evidence directory. logs/ is gitignored, like the night logs.
EVIDENCE_DIR: Final[Path] = REPO_ROOT / "logs" / "evidence"

#: ops/night_statsapi.sh's mutex, one statsapi chain at a time. The 2015-2021
#: MLB schedules are statsapi calls, so they wait for it the way that script's
#: second copy would, and take it while they run.
STATSAPI_LOCK_NAME: Final[str] = ".statsapi_night.lock"
SCHEDULE_WAIT_S: Final[float] = 6 * 3600.0
SCHEDULE_POLL_S: Final[float] = 30.0

STOP_SCHEDULE: Final[str] = "schedule-unavailable"


class ScheduleUnavailable(RuntimeError):
    """A season's schedule is not stored and could not be pulled."""


@dataclasses.dataclass(frozen=True)
class Scope:
    """One level and its seasons, in the order the chain takes them."""

    level: str
    seasons: tuple[int, ...]

    @property
    def sport_id(self) -> int:
        return SPORT_BY_LEVEL[self.level]

    def label(self) -> str:
        return f"{self.level}:{','.join(str(season) for season in self.seasons)}"


def make_scope(level: str, seasons: Iterable[int]) -> Scope:
    """A validated scope. Refuses a season outside SCOPE_SEASONS[level]."""
    name = str(level).strip().lower()
    if name not in SCOPE_SEASONS:
        raise ValueError(f"level {level!r} is not one of {sorted(SCOPE_SEASONS)}")
    years = tuple(int(season) for season in seasons)
    if not years:
        raise ValueError(f"scope {name} names no season")
    if len(set(years)) != len(years):
        raise ValueError(f"scope {name} names a season twice: {years}")
    outside = [year for year in years if year not in SCOPE_SEASONS[name]]
    if outside:
        raise ValueError(
            f"scope {name}: seasons {outside} are outside {SCOPE_SEASONS[name]}. "
            "This chain never pulls 2026, and MLB 2022-2026 is W6.0's scope."
        )
    return Scope(level=name, seasons=years)


def parse_scope(text: str) -> Scope:
    """``aaa:2024,2025,2023`` -> Scope('aaa', (2024, 2025, 2023))."""
    level, sep, years = str(text).partition(":")
    if not sep:
        raise ValueError(f"scope {text!r} is not LEVEL:YEAR,YEAR,...")
    return make_scope(level, [int(year) for year in years.split(",") if year.strip()])


def final_game_pks_by_date(sport_id: int, season: int) -> dict[_dt.date, frozenset[int]]:
    """officialDate -> every game_pk the stored schedule lists as Final that day.

    Every occurrence counts, not one row per game_pk: a suspended game is
    listed on the day it started and on the day it finished, and its pitches
    may carry either date. Abstract state Final also covers a cancelled game,
    which has no pitches and so can never make a day fail a subset test.
    Reads the stored payload only; this never sends a request.
    """
    payload, _source = schedule.load_payload(int(sport_id), int(season))
    found: dict[_dt.date, set[int]] = {}
    for block in payload.get("dates") or ():
        for game in block.get("games") or ():
            status = game.get("status") or {}
            if status.get("abstractGameState") != "Final":
                continue
            pk, day = game.get("gamePk"), game.get("officialDate")
            if not pk or not day:
                continue
            found.setdefault(paths.as_official_date(day), set()).add(int(pk))
    return {day: frozenset(pks) for day, pks in found.items()}


def statsapi_lock_path() -> Path:
    return paths.tmp_dir() / STATSAPI_LOCK_NAME


def schedule_stored(sport_id: int, season: int) -> bool:
    return (
        paths.raw_schedule(sport_id, season).exists()
        or schedule.staging_payload_path(sport_id, season).exists()
    )


def ensure_schedules(
    sport_id: int,
    seasons: Iterable[int],
    *,
    wait_s: float = SCHEDULE_WAIT_S,
    poll_s: float = SCHEDULE_POLL_S,
    stream: Any = None,
    sleep: Any = None,
    monotonic: Any = None,
) -> list[int]:
    """Store every missing schedule, one statsapi call per season.

    The calls go through ``absump.ingest.schedule.load_payload``, which goes
    through ``absump.http``, under the statsapi night mutex. If a statsapi
    batch holds it, this waits for it the way a second copy of
    ops/night_statsapi.sh would, polling, for up to ``wait_s`` seconds, and
    then raises ScheduleUnavailable. Returns the seasons it pulled.
    """
    out = stream if stream is not None else sys.stdout
    nap = sleep if sleep is not None else time.sleep
    clock = monotonic if monotonic is not None else time.monotonic
    missing = [int(season) for season in seasons if not schedule_stored(sport_id, season)]
    if not missing:
        return []
    lock = statsapi_lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = clock() + float(wait_s)
    announced = False
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if clock() >= deadline:
                raise ScheduleUnavailable(
                    f"sport {sport_id} seasons {missing}: {lock} was held for "
                    f"{wait_s:.0f} s by another statsapi batch"
                ) from None
            if not announced:
                print(
                    f"schedules: {lock} is held by a statsapi batch; waiting for it "
                    f"(poll {poll_s:.0f} s, up to {wait_s:.0f} s)",
                    file=out,
                )
                announced = True
            nap(poll_s)
    try:
        for season in missing:
            _payload, source = schedule.load_payload(sport_id, season, allow_network=True)
            print(f"schedules: sport {sport_id} season {season} stored from {source}", file=out)
    finally:
        release_lock(lock)
    return missing


def evidence_path(step: str = SCOPE_STEP) -> Path:
    return EVIDENCE_DIR / f"{step}.log"


def completion_path(level: str, step: str = SCOPE_STEP) -> Path:
    """Written when every day of every SCOPE_SEASONS[level] season is judged."""
    return EVIDENCE_DIR / f"{step}-{level}-complete.json"


def _evidence(path: Path | None, line: str, out: Any) -> None:
    text = f"{madrid_stamp()} {line}"
    print(text, file=out)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


@dataclasses.dataclass
class ScopeReport:
    """What one run over one or more scopes did."""

    scopes: tuple[str, ...] = ()
    attempted: int = 0
    wire: int = 0
    cached: int = 0
    stored: int = 0
    rechecked: int = 0
    skipped_in_lake: int = 0
    refused: list[str] = dataclasses.field(default_factory=list)
    empty: list[str] = dataclasses.field(default_factory=list)
    header_skipped: list[str] = dataclasses.field(default_factory=list)
    failed: int = 0
    stop_reason: str = STOP_QUEUE_EMPTY
    next_day: str | None = None
    cap_before: CapState | None = None
    cap_after: CapState | None = None
    notes: list[str] = dataclasses.field(default_factory=list)

    def marker(self) -> dict[str, Any]:
        after = self.cap_after or self.cap_before
        return {
            "step": SCOPE_STEP,
            "scopes": list(self.scopes),
            "ts_madrid": madrid_stamp(),
            "stop_reason": self.stop_reason,
            "days_attempted": self.attempted,
            "requests_on_the_wire": self.wire,
            "days_from_cache": self.cached,
            "days_stored": self.stored,
            "days_rechecked": self.rechecked,
            "days_already_in_lake": self.skipped_in_lake,
            "days_refused": list(self.refused),
            "days_empty": list(self.empty),
            "seasons_header_skipped": list(self.header_skipped),
            "days_failed": self.failed,
            "next_day": self.next_day,
            "host": after.host if after else "",
            "cap": after.cap if after else 0,
            "used_before": self.cap_before.used if self.cap_before else 0,
            "used_after": self.cap_after.used if self.cap_after else 0,
            "notes": list(self.notes),
        }

    def lines(self) -> list[str]:
        return [
            f"run: attempted={self.attempted} wire={self.wire} cached={self.cached} "
            f"stored={self.stored} rechecked={self.rechecked} refused={len(self.refused)} "
            f"empty={len(self.empty)} header_skipped={len(self.header_skipped)} "
            f"failed={self.failed} stop={self.stop_reason}",
            f"run: next day {self.next_day or '-'}",
        ]


def scope_marker_path() -> Path:
    return NIGHT_LOG_DIR / f"{SCOPE_STEP}-resume.json"


def _manifested(url: str) -> bool:
    """True when the client already paid for this URL and its body is on disk."""
    row = client._manifest_index().get(url)
    return row is not None and client._dest_path(url).exists()


def run_scopes(
    scopes: Sequence[Scope],
    *,
    resume: bool = True,
    max_requests: int | None = None,
    marker_path: Path | str | None = None,
    evidence: Path | str | None = None,
    stream: Any = None,
    schedule_wait_s: float = SCHEDULE_WAIT_S,
    schedule_poll_s: float = SCHEDULE_POLL_S,
) -> ScopeReport:
    """Drive the day puller over each scope's seasons, in the order given.

    Inside a season the days go newest first, as in W6.0. With ``resume`` a
    day already in the lake is skipped outright; without it the stored file is
    read back and judged again, which costs no request. A day whose URL the
    client already paid for is judged from the raw cache, also at no cost, so
    a refused day stays refused and a drifted season is skipped again without
    a second request. ``max_requests`` counts calls that reached the wire.
    """
    out = stream if stream is not None else sys.stdout
    log = Path(evidence) if evidence is not None else evidence_path()
    lock = take_lock()
    report = ScopeReport(scopes=tuple(scope.label() for scope in scopes))
    host = savant_host()
    report.cap_before = cap_state(host)
    judged: dict[str, set[_dt.date]] = {}
    skipped_seasons: dict[str, set[int]] = {}
    stop = False
    try:
        _evidence(
            log,
            f"{SCOPE_STEP} start scopes={' '.join(report.scopes)} resume={resume} "
            f"cap {report.cap_before.used}/{report.cap_before.cap}",
            out,
        )
        for scope in scopes:
            if stop:
                break
            if scope.level == "mlb":
                try:
                    ensure_schedules(
                        scope.sport_id,
                        scope.seasons,
                        wait_s=schedule_wait_s,
                        poll_s=schedule_poll_s,
                        stream=out,
                    )
                except (ScheduleUnavailable, client.HttpError) as exc:
                    report.stop_reason = STOP_SCHEDULE
                    _evidence(log, f"STOP {scope.label()}: schedules unavailable: {exc}", out)
                    break
            for season in scope.seasons:
                if stop:
                    break
                try:
                    allowed = final_game_pks_by_date(scope.sport_id, season)
                    days = newest_first(season_days(season, sport_id=scope.sport_id))
                except schedule.PayloadMissing as exc:
                    report.stop_reason = STOP_SCHEDULE
                    _evidence(log, f"STOP {scope.level} {season}: {exc}", out)
                    stop = True
                    break
                in_lake = done_days(level=scope.level)
                seen = judged.setdefault(scope.level, set())
                for day in days:
                    if day in in_lake and resume:
                        report.skipped_in_lake += 1
                        seen.add(day)
                        continue
                    url = statcast_day.day_url(day, level=scope.level)
                    free = day in in_lake or _manifested(url)
                    if not free:
                        if max_requests is not None and report.wire >= max_requests:
                            report.stop_reason = STOP_MAX_REQUESTS
                            report.next_day = day.isoformat()
                            stop = True
                            break
                        if cap_state(host).remaining <= 0:
                            report.stop_reason = STOP_DAILY_CAP
                            report.next_day = day.isoformat()
                            stop = True
                            break
                    report.attempted += 1
                    tag = f"{scope.level} {season} {day.isoformat()}"
                    try:
                        if day in in_lake:
                            day_report = statcast_day.validate_day(
                                statcast_day.read_day(
                                    statcast_day.raw_path(day, level=scope.level)
                                ),
                                day,
                            )
                            statcast_day.admit(day_report, allowed.get(day, frozenset()))
                            report.rechecked += 1
                            seen.add(day)
                            continue
                        day_report = statcast_day.pull_day(
                            day, level=scope.level, allowed_game_pks=allowed.get(day, frozenset())
                        )
                    except client.BudgetExceeded as exc:
                        report.attempted -= 1
                        report.stop_reason = STOP_DAILY_CAP
                        report.next_day = day.isoformat()
                        report.notes.append(f"{tag}: {exc}")
                        stop = True
                        break
                    except client.Fatal as exc:
                        report.failed += 1
                        report.stop_reason = STOP_FATAL
                        report.next_day = day.isoformat()
                        _evidence(log, f"FATAL {tag}: {type(exc).__name__}: {exc}", out)
                        stop = True
                        break
                    except statcast_day.HeaderDrift as exc:
                        if not free:
                            report.wire += 1
                        report.header_skipped.append(f"{scope.level}:{season}")
                        skipped_seasons.setdefault(scope.level, set()).add(season)
                        _evidence(
                            log,
                            f"HEADER {tag}: DT-02 refused, season {season} skipped, the "
                            f"header is recorded and not fixed: {exc}",
                            out,
                        )
                        break
                    except statcast_day.NotInSchedule as exc:
                        if not free:
                            report.wire += 1
                        else:
                            report.cached += 1
                        report.refused.append(f"{scope.level}:{day.isoformat()}")
                        seen.add(day)
                        _evidence(log, f"REFUSED {tag}: {exc}", out)
                        continue
                    except (
                        client.HttpError,
                        statcast_day.DayContractError,
                        paths.SealViolation,
                        OSError,
                        ValueError,
                    ) as exc:
                        report.failed += 1
                        _evidence(log, f"FAILED {tag}: {type(exc).__name__}: {exc}", out)
                        continue
                    if day_report.from_cache:
                        report.cached += 1
                    else:
                        report.wire += 1
                    report.stored += 1
                    seen.add(day)
                    if not day_report.game_pks:
                        report.empty.append(f"{scope.level}:{day.isoformat()}")
                        _evidence(log, f"EMPTY {tag}: 0 rows under the header; stored", out)
                    print(
                        f"pull: {tag} {day_report.n_rows} rows, {len(day_report.game_pks)} "
                        f"games, {'cache' if day_report.from_cache else 'wire'}",
                        file=out,
                    )
        report.cap_after = cap_state(host)
        for level in sorted({scope.level for scope in scopes}):
            _write_completion(level, scopes, judged.get(level, set()), skipped_seasons, report, out)
    finally:
        release_lock(lock)

    written = write_marker(report.marker(), marker_path or scope_marker_path())
    for line in report.lines():
        print(line, file=out)
    _evidence(
        log,
        f"{SCOPE_STEP} stop={report.stop_reason} wire={report.wire} cached={report.cached} "
        f"stored={report.stored} refused={len(report.refused)} "
        f"header_skipped={','.join(report.header_skipped) or '-'} failed={report.failed} "
        f"cap {report.cap_after.used if report.cap_after else '?'}/"
        f"{report.cap_after.cap if report.cap_after else '?'} marker {written}",
        out,
    )
    return report


def _write_completion(
    level: str,
    scopes: Sequence[Scope],
    judged: set[_dt.date],
    skipped: dict[str, set[int]],
    report: ScopeReport,
    out: Any,
) -> None:
    """Stamp a level complete when this run judged every day of every season.

    Complete means: every played day of every SCOPE_SEASONS[level] season is in
    the lake, or was refused by the admission check, or belongs to a season
    skipped for header drift. Only a run that covered all of those seasons can
    say so. The stamp is what the W2.10 registration needs before its verify
    runs, so the step reads MISSING, not FAIL, while the pull is in progress.
    """
    covered = {season for scope in scopes if scope.level == level for season in scope.seasons}
    if covered != set(SCOPE_SEASONS[level]) or report.stop_reason not in (STOP_QUEUE_EMPTY,):
        return
    outstanding: list[str] = []
    per_season: dict[str, int] = {}
    for season in SCOPE_SEASONS[level]:
        days = season_days(season, sport_id=SPORT_BY_LEVEL[level])
        per_season[str(season)] = len(days)
        if season in skipped.get(level, set()):
            continue
        outstanding.extend(day.isoformat() for day in days if day not in judged)
    if outstanding:
        print(f"complete: {level} not complete, {len(outstanding)} day(s) unjudged", file=out)
        return
    payload = {
        "step": SCOPE_STEP,
        "level": level,
        "seasons": list(SCOPE_SEASONS[level]),
        "ts_madrid": madrid_stamp(),
        "days_in_scope": per_season,
        "days_in_lake": len(done_days(level=level)),
        "days_refused": sorted(d for d in report.refused if d.startswith(f"{level}:")),
        "days_empty": sorted(d for d in report.empty if d.startswith(f"{level}:")),
        "seasons_header_skipped": sorted(skipped.get(level, set())),
    }
    path = write_marker(payload, completion_path(level))
    print(f"complete: {level} stamped {path}", file=out)


def verify_scope(level: str, *, stream: Any = None) -> list[str]:
    """W2.10's offline verify: every stored day of the level, and completeness.

    For every day on disk: DT-01, DT-02 and UT-14 (``validate_day``), and the
    admission check against the stored schedule. Then completeness against the
    completion stamp: every played day of every season is in the lake or named
    in the stamp as refused, or its season is named as header-skipped. Returns
    the failures; sends nothing and writes nothing.
    """
    out = stream if stream is not None else sys.stdout
    failures: list[str] = []
    name = make_scope(level, SCOPE_SEASONS[level]).level
    stamp = read_marker(completion_path(name))
    if stamp is None:
        failures.append(f"V-00 no completion stamp at {completion_path(name)}")
        stamp = {}
    refused = {d.split(":", 1)[1] for d in stamp.get("days_refused", [])}
    skipped = {int(s) for s in stamp.get("seasons_header_skipped", [])}
    stored = dict(statcast_day.raw_days(level=name))
    checked = 0
    for season in SCOPE_SEASONS[name]:
        allowed = final_game_pks_by_date(SPORT_BY_LEVEL[name], season)
        for day in season_days(season, sport_id=SPORT_BY_LEVEL[name]):
            path = stored.get(day)
            if path is None:
                if season not in skipped and day.isoformat() not in refused:
                    failures.append(f"V-01 {name} {day.isoformat()} neither stored nor refused")
                continue
            try:
                day_report = statcast_day.validate_day(statcast_day.read_day(path), day)
                statcast_day.admit(day_report, allowed.get(day, frozenset()))
            except statcast_day.DayContractError as exc:
                failures.append(f"V-02 {name} {day.isoformat()} {type(exc).__name__}: {exc}")
                continue
            checked += 1
    strays = sorted(
        day.isoformat()
        for day in stored
        if day.year not in SCOPE_SEASONS[name] and not (name == "mlb" and day.year >= 2022)
    )
    if strays:
        failures.append(f"V-03 {name} days outside the scope seasons on disk: {strays[:5]}")
    print(
        f"verify {name}: {checked} stored day(s) pass DT-01, DT-02, UT-14 and admission; "
        f"{len(refused)} refused, {len(skipped)} season(s) header-skipped, "
        f"{len(failures)} failure(s)",
        file=out,
    )
    for line in failures:
        print(f"FAIL {line}", file=out)
    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m absump.ingest.pull_statcast",
        description="W6.0. The Statcast backfill runner: newest first, two nights, one chain.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run every W6.0 assertion against what is on disk. No request, no write.",
    )
    parser.add_argument("--plan", action="store_true", help="print the plan and send nothing")
    parser.add_argument(
        "--run", action="store_true", help="drive the queue, newest first, under the daily cap"
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="ceiling on the days this invocation attempts, below the daily cap",
    )
    parser.add_argument(
        "--no-import-staging", action="store_true", help="do not import data/staging first"
    )
    parser.add_argument(
        "--staging",
        default=None,
        help="the staging cache root (default: data/staging)",
    )
    parser.add_argument("--marker", default=None, help="where to write the resume marker")
    parser.add_argument(
        "--level",
        choices=sorted(SCOPE_SEASONS),
        default=None,
        help="W2.10 aaa or the W2.9 mlb backfill; with --season, one scope for --run",
    )
    parser.add_argument(
        "--season",
        type=int,
        nargs="+",
        default=None,
        help="seasons for --level, taken in the order given",
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=None,
        metavar="LEVEL:YEAR,YEAR",
        help="a scope for --run, repeatable, taken in order: aaa:2024,2025,2023",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="with a scope: skip days already in the lake instead of judging them again",
    )
    parser.add_argument(
        "--evidence", default=None, help="the evidence log (default logs/evidence/W2.10.log)"
    )
    parser.add_argument(
        "--schedules",
        type=int,
        nargs="+",
        default=None,
        metavar="YEAR",
        help="store the MLB schedules for these backfill seasons, under the statsapi mutex",
    )
    parser.add_argument(
        "--verify-scope",
        choices=sorted(SCOPE_SEASONS),
        default=None,
        help="W2.10's offline verify for one level. No request, no write.",
    )
    return parser


def _scopes(args: argparse.Namespace) -> list[Scope]:
    scopes = [parse_scope(text) for text in args.scope or ()]
    if args.level or args.season:
        if not (args.level and args.season):
            raise ValueError("--level and --season go together")
        scopes.append(make_scope(args.level, args.season))
    return scopes


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        scopes = _scopes(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.verify_scope:
        return 1 if verify_scope(args.verify_scope) else 0
    if args.schedules:
        try:
            make_scope("mlb", args.schedules)
            pulled = ensure_schedules(SPORT_BY_LEVEL["mlb"], args.schedules)
        except (ValueError, ScheduleUnavailable, client.HttpError) as exc:
            print(f"schedules: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(
            f"schedules: {len(pulled)} pulled, {len(args.schedules) - len(pulled)} already stored"
        )
        return 0
    if scopes:
        if not args.run:
            print("a scope runs only with --run", file=sys.stderr)
            return 2
        try:
            scoped = run_scopes(
                scopes,
                resume=args.resume,
                max_requests=args.max_requests,
                marker_path=args.marker,
                evidence=args.evidence,
            )
        except ChainBusy as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if scoped.stop_reason == STOP_FATAL:
            return 3
        if scoped.stop_reason == STOP_SCHEDULE:
            return 4
        return 1 if scoped.failed else 0
    if not (args.check or args.plan or args.run):
        _parser().print_help()
        return 2

    if args.plan:
        for line in plan(staging_root=args.staging).lines():
            print(line)

    if args.check:
        failures = check(staging_root=args.staging)
        if failures:
            return 1

    if args.run:
        try:
            report = run(
                staging_root=args.staging,
                max_requests=args.max_requests,
                import_staging=not args.no_import_staging,
                marker_path=args.marker,
            )
        except ChainBusy as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if report.failed:
            return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main())
