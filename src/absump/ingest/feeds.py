"""MLB GUMBO live-feed ingest and its resume logic. SOP step W2.6.

The step, verbatim from SOP section W2.6: one request per game at
``https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live``, gzipped on the
wire, zstd on disk, at the section 2.3 statsapi policy of 4 s spacing under a
3,000/day cap. The SOP sizes the 2026 pull at 2,512 games, a measured mean of
0.779 MB uncompressed, so about 1.96 GB uncompressed becoming ~0.19 GB on disk,
and about 3.2 hours: one overnight batch inside the daily cap.

The entry point is the command SOP W2.6 registers:

    uv run python -m absump.ingest.feeds --sport 1 --season 2026 --status Final --resume

Three things this module is, in order of importance.

1. A seal gate that happens to fetch. Under SOP section 2.4 a 2026 game whose
   ``officialDate`` is 2026-09-22 or later, and every 2026 postseason game
   (``gameType`` F, D, L or W), is sealed. A request for one is a phase
   failure, not a warning, so the queue is filtered before a URL is built and
   again after the body arrives, because a game can move into the sealed window
   after the schedule was read. Game ``823543`` did exactly that: it was
   scheduled for 2026-05-23, rained out, and replayed on 2026-09-22, so a copy
   pulled before the reschedule is a sealed game sitting in an open cache.
   ``paths.LAST_OPEN_DATE`` is the one date this module reads; it does not
   carry its own copy of 2026-09-21.

2. An importer. ``data/staging`` already holds feeds pulled under the same A3
   throttle. Every one of them is imported, re-validated and re-stored before
   the network is touched, so the pull is only ever the remainder. Provenance
   carries over; trust does not, so an imported body is parsed and checked
   exactly as a fetched one is.

3. A parser for the challenge traps. The regime marker is the presence of the
   ``absChallenges`` key in ``gameData``, tested as key presence and never by
   reading a field inside it. ``gameData.review`` is the manager replay counter
   and is a different object. ``reviewType`` is filtered to ``MJ``.
   ``playEvents[].details.hasReview`` and ``allPlays[].about.hasReview`` are two
   independent flags, and an ABS review attached to a pitch leaves
   ``about.hasReview`` False, so counting either alone undercounts. A fourth
   trap the SOP text does not name is handled here too: a play-level
   ``reviewDetails`` can carry ``additionalReviews``, a nested list, and an MJ
   challenge hides inside one in game ``822717``. ``iter_review_details`` walks
   that list, and with it the per-game reconciliation against
   ``gameData.absChallenges`` is exact on all 2,339 staged 2026 games.

Storage. One file per game at ``paths.raw_feed(...)``, zstandard level 10, the
compression SOP section 2.3 fixes for raw bytes. Raw bytes are immutable: an
existing valid file is never rewritten, which is what makes a second run of this
module change no bytes. Resume is the file itself: a game is done when its
stored file decompresses to a body between 0.3 MB and 3.0 MB, so the resume
check and the SOP's ``test_feed_size_sane`` assertion are the same test, and a
200-byte "game not found" body returned with HTTP 200 can never be mistaken for
a completed game.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import zstandard

from absump import http, paths

__all__ = [
    "ABS_REVIEW_TYPE",
    "FEED_URL",
    "MAX_FEED_BYTES",
    "MIN_FEED_BYTES",
    "NON_ABS_VENUE_GAME_PKS",
    "PRE_ABS_CONTROL_GAMES",
    "REGIME_MARKER",
    "REPLAY_REVIEW_TYPES",
    "SEALED_GAME_TYPES",
    "ScheduledGame",
    "abs_challenges",
    "challenge_totals",
    "feed_path",
    "has_abs_regime",
    "iter_review_details",
    "load_feed",
    "main",
    "plan",
    "schedule_games",
    "store_feed",
    "token_ledger",
]

# ---------------------------------------------------------------------------
# Endpoints. The only two URL templates this module knows.
# ---------------------------------------------------------------------------

#: One request per game (SOP W2.6). v1.1, not v1: v1 has no live feed.
FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"

#: The season schedule the queue is planned from. ``hydrate=officials`` is what
#: DT-14 reads later; this module only needs gamePk, gameType, officialDate and
#: status, and asks for the same URL the staging cache recorded so a copy
#: already in ``data/raw`` is reused rather than re-requested.
SCHEDULE_URL = (
    "https://statsapi.mlb.com/api/v1/schedule"
    "?sportId={sport_id}&season={season}&gameType=R&hydrate=officials"
)

# ---------------------------------------------------------------------------
# Contract facts. Every number here is either a study-design constant or comes
# with the line that measured it (SOP section 0.5 rule 4).
# ---------------------------------------------------------------------------

#: The ABS regime marker. Tested as key presence in ``gameData`` and never by
#: reading a field inside it: ``gameData.absChallenges["hasChallenges"]`` raises
#: KeyError on every pre-ABS game, which is the trap SOP W2.6 names first.
REGIME_MARKER = "absChallenges"

#: The ABS challenge review type. Everything else under ``reviewType`` is replay.
ABS_REVIEW_TYPE = "MJ"

#: The replay codes SOP W2.6 names by hand. The filter in this module is
#: positive -- keep MJ -- so this tuple is not the filter; it is the set the
#: tests assert never reaches a challenge count. The staged 2026 corpus carries
#: 30 further replay codes (MI, MV, MD, MO, MP, MS, ...), which is exactly why
#: the filter cannot be "exclude the known replay codes".
REPLAY_REVIEW_TYPES = ("MF", "MA", "MC", "NH")

#: SOP section 2.4, the sealed branch of the frozen analysis-set predicate.
SEALED_GAME_TYPES = ("F", "D", "L", "W")

#: SOP section 2.4, the excluded branch: spring, all-star, exhibition.
EXCLUDED_GAME_TYPES = ("S", "A", "E")

#: SOP W2.6 ``test_feed_size_sane``: every stored file decompresses to between
#: 0.3 and 3.0 MB. The lower bound is what catches a 200-byte "game not found"
#: body returned with HTTP 200. Measured over the 2,343 staged 2026 feeds:
#: min 621,465 B, max 1,156,227 B, mean 806,600 B.
MIN_FEED_BYTES = 300_000
MAX_FEED_BYTES = 3_000_000

#: Challenge tokens per team per game. SOP W2.6 ``test_token_start``:
#: ``remaining + usedFailed == 2`` for every team-game. A successful challenge
#: is retained and does not spend a token, which is why the identity uses
#: usedFailed and not usedSuccessful.
TOKEN_ALLOTMENT = 2

#: Measured on the staged 2026 corpus, 2026-09-23: 34 games, 36 team-games,
#: carry ``remaining + usedFailed == 3``, and every one of the 34 went past the
#: ninth. A team that has spent both tokens is granted a third in extra innings.
#: The SOP text states the allotment as 2 with no extra-innings clause; this
#: constant is the measured exception and is reported as an owner decision, not
#: folded silently into the assertion.
EXTRA_INNING_ALLOTMENT = 3
REGULATION_INNINGS = 9

#: Four Final 2026 regular-season games carry no ``absChallenges`` key at all,
#: measured over the staged corpus on 2026-09-23. All four are neutral-site
#: special events at parks with no ABS installation:
#:   823669  2026-08-13  Field of Dreams, Dyersville
#:   823745  2026-08-23  Journey Bank Ballpark, Williamsport
#:   825093  2026-04-25  Estadio Alfredo Harp Helu, Mexico City
#:   825094  2026-04-26  Estadio Alfredo Harp Helu, Mexico City
#: So the regime marker is venue-conditional, not unconditional on season, and
#: the SOP's "100% of Final 2026 MLB games" holds at 2,339 of 2,343. These games
#: are not pre-ABS: they are outside the ABS population and belong in neither
#: arm. Reported as an owner decision.
NON_ABS_VENUE_GAME_PKS = frozenset({823669, 823745, 825093, 825094})

#: SOP W2.6 ``test_regime_marker`` negative controls: the marker is absent on
#: MLB 2025 and on AAA 2023. gamePk -> (sport_id, season).
PRE_ABS_CONTROL_GAMES: dict[int, tuple[int, int]] = {
    776311: (1, 2025),
    722770: (11, 2023),
    723056: (11, 2023),
}

#: Where the pre-network cache lives. SOP: import from it before touching the
#: network, re-validate every imported byte.
STAGING_FEEDS = "data/staging/statsapi/feeds/sport{sport_id}/{season}"
STAGING_SCHEDULE = "data/staging/statsapi/schedule/sport{sport_id}-{season}.json"

_ZSTD_LEVEL = 10


class SealBreach(RuntimeError):
    """A sealed game reached a code path that requests or stores open data."""


# ---------------------------------------------------------------------------
# Feed parsing: the traps
# ---------------------------------------------------------------------------


def has_abs_regime(feed: dict[str, Any]) -> bool:
    """True when this game was played under ABS.

    Key presence in ``gameData``, and nothing else. Reading
    ``gameData.absChallenges["hasChallenges"]`` first raises KeyError on every
    pre-ABS game; reading ``hasChallenges`` after the presence test is also
    wrong, because it is False on an ABS game in which nobody challenged.
    """
    return REGIME_MARKER in feed.get("gameData", {})


def iter_review_details(node: Any) -> Iterator[dict[str, Any]]:
    """Yield ``node`` and every review nested under ``additionalReviews``.

    statsapi files a challenge that arrived alongside a manager replay as a
    nested record: in game ``822717`` an MJ challenge sits inside the
    ``additionalReviews`` list of a play-level ``MA`` replay record. A walk that
    reads only the top-level ``reviewType`` misses it and undercounts that game
    by one against ``gameData.absChallenges``.
    """
    if not isinstance(node, dict):
        return
    yield node
    for nested in node.get("additionalReviews") or ():
        yield from iter_review_details(nested)


@dataclass(frozen=True)
class Challenge:
    """One ABS challenge, located precisely enough to join to a pitch later."""

    game_pk: int
    at_bat_index: int
    play_event_index: int | None
    level: str
    team_id: int | None
    player_id: int | None
    is_overturned: bool
    inning: int | None


def abs_challenges(feed: dict[str, Any]) -> list[Challenge]:
    """Every ABS challenge in one feed, pitch-level and play-level together.

    Both flags are read because they are independent: ``about.hasReview`` is
    False on a play that carries a pitch-level ABS review (at-bats 30 and 65 of
    game ``824466``), and a play-level challenge leaves every
    ``playEvents[].details.hasReview`` False. Neither flag is used to decide
    what to count -- the record under ``reviewDetails`` is -- because the flags
    disagree with each other and the record does not.
    """
    game_pk = int(feed.get("gameData", {}).get("game", {}).get("pk", 0))
    out: list[Challenge] = []
    for play in feed.get("liveData", {}).get("plays", {}).get("allPlays", ()):
        about = play.get("about", {})
        at_bat = int(about.get("atBatIndex", -1))
        inning = about.get("inning")
        for index, event in enumerate(play.get("playEvents", ())):
            for review in iter_review_details(event.get("reviewDetails")):
                if review.get("reviewType") != ABS_REVIEW_TYPE:
                    continue
                out.append(
                    Challenge(
                        game_pk=game_pk,
                        at_bat_index=at_bat,
                        play_event_index=index,
                        level="pitch",
                        team_id=review.get("challengeTeamId"),
                        player_id=(review.get("player") or {}).get("id"),
                        is_overturned=bool(review.get("isOverturned")),
                        inning=inning,
                    )
                )
        for review in iter_review_details(play.get("reviewDetails")):
            if review.get("reviewType") != ABS_REVIEW_TYPE:
                continue
            out.append(
                Challenge(
                    game_pk=game_pk,
                    at_bat_index=at_bat,
                    play_event_index=None,
                    level="play",
                    team_id=review.get("challengeTeamId"),
                    player_id=(review.get("player") or {}).get("id"),
                    is_overturned=bool(review.get("isOverturned")),
                    inning=inning,
                )
            )
    return out


def token_ledger(feed: dict[str, Any]) -> dict[str, dict[str, int]]:
    """``gameData.absChallenges`` per side, as ints, or an empty dict.

    Never ``gameData.review``: that is the manager replay counter, a different
    object with different keys. Game ``822925`` carries both, and they say
    different things -- 2 ABS challenges under ``absChallenges``, 2 replay
    challenges under ``review`` -- and they reconcile independently.
    """
    marker = feed.get("gameData", {}).get(REGIME_MARKER)
    if not isinstance(marker, dict):
        return {}
    ledger: dict[str, dict[str, int]] = {}
    for side in ("away", "home"):
        entry = marker.get(side)
        if not isinstance(entry, dict):
            continue
        ledger[side] = {
            "usedSuccessful": int(entry.get("usedSuccessful", 0)),
            "usedFailed": int(entry.get("usedFailed", 0)),
            "remaining": int(entry.get("remaining", 0)),
        }
    return ledger


def challenge_totals(feed: dict[str, Any]) -> dict[str, int]:
    """The counts ``gameData.absChallenges`` declares, summed over both sides."""
    ledger = token_ledger(feed)
    used_successful = sum(side["usedSuccessful"] for side in ledger.values())
    used_failed = sum(side["usedFailed"] for side in ledger.values())
    return {
        "used_successful": used_successful,
        "used_failed": used_failed,
        "used": used_successful + used_failed,
    }


def final_inning(feed: dict[str, Any]) -> int:
    """The last inning played, from the linescore. 0 when there is none."""
    linescore = feed.get("liveData", {}).get("linescore", {})
    return int(linescore.get("currentInning") or 0)


def official_date(feed: dict[str, Any]) -> _dt.date:
    """The feed's own ``officialDate``, which is the seal key for this game."""
    value = feed.get("gameData", {}).get("datetime", {}).get("officialDate")
    if not value:
        raise ValueError("feed carries no gameData.datetime.officialDate")
    return paths.as_official_date(value)


def game_type(feed: dict[str, Any]) -> str:
    return str(feed.get("gameData", {}).get("game", {}).get("type", ""))


def game_season(feed: dict[str, Any]) -> int:
    return int(feed.get("gameData", {}).get("game", {}).get("season", 0))


# ---------------------------------------------------------------------------
# The seal
# ---------------------------------------------------------------------------


def is_sealed(season: int, game_type_code: str, day: _dt.date) -> bool:
    """SOP section 2.4, the sealed branch, read from one predicate.

    Sealed is season 2026 and gameType R and officialDate after
    ``paths.LAST_OPEN_DATE``, or season 2026 and gameType in F, D, L, W. The
    boundary date is asked of ``absump.paths`` so this module cannot drift from
    the lake layout that routes sealed days elsewhere.
    """
    if int(season) != 2026:
        return False
    if game_type_code in SEALED_GAME_TYPES:
        return True
    return game_type_code == "R" and paths.is_sealed(day)


def is_excluded(game_type_code: str) -> bool:
    """Spring, all-star and exhibition, which the analysis set drops outright."""
    return game_type_code in EXCLUDED_GAME_TYPES


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def feed_path(sport_id: int, season: int, day: _dt.date, game_pk: int) -> Path:
    """The stored path for one feed, minted by ``absump.paths``."""
    return paths.raw_feed(sport_id, season, day, game_pk)


def _decompress(path: Path) -> bytes:
    decompressor = zstandard.ZstdDecompressor()
    with path.open("rb") as handle, decompressor.stream_reader(handle) as reader:
        return reader.read()


def load_feed(path: Path) -> dict[str, Any]:
    """Read one stored feed back. The inverse of :func:`store_feed`."""
    return json.loads(_decompress(path).decode("utf-8"))


def body_is_sane(body: bytes) -> bool:
    """SOP W2.6 ``test_feed_size_sane``, applied to one uncompressed body."""
    return MIN_FEED_BYTES <= len(body) <= MAX_FEED_BYTES


def validate_body(body: bytes, game_pk: int) -> dict[str, Any]:
    """Parse one feed body and refuse it if it is not this game's full feed.

    A short body is refused before it is parsed, because the failure this
    catches -- a 200-byte "game not found" served with HTTP 200 -- parses
    perfectly well as JSON and would otherwise be stored as a completed game.
    """
    if not body_is_sane(body):
        raise ValueError(
            f"game {game_pk}: body is {len(body)} B, outside the "
            f"{MIN_FEED_BYTES}..{MAX_FEED_BYTES} B window SOP W2.6 fixes"
        )
    feed = json.loads(body.decode("utf-8"))
    seen = int(feed.get("gameData", {}).get("game", {}).get("pk", 0))
    if seen != int(game_pk):
        raise ValueError(f"game {game_pk}: body carries gamePk {seen}")
    return feed


def store_feed(sport_id: int, season: int, game_pk: int, body: bytes) -> Path:
    """Validate one body, refuse it if sealed, and write it once.

    The seal is re-tested here against the feed's own ``officialDate`` and
    ``gameType``, not against whatever the schedule said when the queue was
    planned. A game can only become more sealed between the two: ``823543`` was
    a 2026-05-23 game when it was first scheduled and is a 2026-09-22 game now.

    An existing file is never rewritten. Raw bytes are immutable (section 2.3),
    and that is also what makes a second run of this module change no bytes.
    """
    feed = validate_body(body, game_pk)
    day = official_date(feed)
    code = game_type(feed)
    season_seen = game_season(feed) or int(season)
    if is_sealed(season_seen, code, day):
        raise SealBreach(
            f"game {game_pk} is sealed (season {season_seen}, gameType {code}, "
            f"officialDate {day.isoformat()}); it must never reach the open lake"
        )
    destination = feed_path(sport_id, season, day, game_pk)
    paths.assert_minted(destination)
    if destination.exists() and body_is_sane(_decompress(destination)):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    compressor = zstandard.ZstdCompressor(level=_ZSTD_LEVEL)
    temporary = destination.with_suffix(".zst.part")
    temporary.write_bytes(compressor.compress(body))
    temporary.replace(destination)
    return destination


def stored_path(sport_id: int, season: int, game_pk: int) -> Path | None:
    """The stored file for this game, whatever day it is filed under, or None.

    The day is part of the path and a rescheduled game changes day, so resume
    globs rather than guessing. A file that does not decompress to a sane body
    is treated as not stored, so a truncated write is refetched instead of
    being trusted.
    """
    root = paths.raw_feed(sport_id, season, paths.LAST_OPEN_DATE, game_pk).parents[1]
    if not root.exists():
        return None
    for candidate in sorted(root.glob(f"date=*/gamepk={int(game_pk)}.json.zst")):
        try:
            if body_is_sane(_decompress(candidate)):
                return candidate
        except (OSError, zstandard.ZstdError):
            continue
    return None


# ---------------------------------------------------------------------------
# The schedule and the queue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduledGame:
    """One game as the schedule describes it, before its feed is on disk."""

    game_pk: int
    game_type: str
    season: int
    official_date: _dt.date
    abstract_state: str
    detailed_state: str
    game_date: str


def schedule_games(schedule: dict[str, Any]) -> list[ScheduledGame]:
    """Every distinct game in a schedule response, newest entry per gamePk.

    The schedule lists a postponed game twice, once on its original date and
    once on the date it was made up, with the same gamePk: the staged 2026
    response holds 2,459 entries for 2,430 distinct games. Requesting the feed
    once per entry would pay 29 times for nothing, and counting entries would
    put the season 29 games over. The entry kept is the one with the latest
    ``gameDate``, which is the one that was played.
    """
    latest: dict[int, ScheduledGame] = {}
    for date_block in schedule.get("dates", ()):
        for game in date_block.get("games", ()):
            pk = int(game.get("gamePk", 0))
            if not pk:
                continue
            status = game.get("status", {})
            record = ScheduledGame(
                game_pk=pk,
                game_type=str(game.get("gameType", "")),
                season=int(game.get("season", 0) or 0),
                official_date=paths.as_official_date(game["officialDate"]),
                abstract_state=str(status.get("abstractGameState", "")),
                detailed_state=str(status.get("detailedState", "")),
                game_date=str(game.get("gameDate", "")),
            )
            prior = latest.get(pk)
            if prior is None or record.game_date > prior.game_date:
                latest[pk] = record
    return sorted(latest.values(), key=lambda g: (g.official_date, g.game_pk))


@dataclass
class Plan:
    """What one invocation would do, before it does any of it."""

    scheduled: list[ScheduledGame] = field(default_factory=list)
    excluded: list[ScheduledGame] = field(default_factory=list)
    sealed: list[ScheduledGame] = field(default_factory=list)
    wrong_status: list[ScheduledGame] = field(default_factory=list)
    candidates: list[ScheduledGame] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "scheduled": len(self.scheduled),
            "excluded": len(self.excluded),
            "sealed": len(self.sealed),
            "wrong_status": len(self.wrong_status),
            "candidates": len(self.candidates),
        }


def plan(games: list[ScheduledGame], *, status: str = "Final") -> Plan:
    """Split the schedule into the games this step may request and the rest.

    Order matters. Excluded game types go first, then the seal, then status, so
    that a sealed game can never be reclassified as merely "not Final yet" and
    picked up by a later run. Postseason games are ``Preview`` until played and
    are sealed for 2026 whatever their status says.
    """
    out = Plan(scheduled=list(games))
    for game in games:
        if is_excluded(game.game_type):
            out.excluded.append(game)
        elif is_sealed(game.season, game.game_type, game.official_date):
            out.sealed.append(game)
        elif status != "any" and game.abstract_state != status:
            out.wrong_status.append(game)
        elif status == "Final" and game.detailed_state == "Postponed":
            # Abstract state Final covers a postponement that was never made
            # up. There is no played game behind it, and its feed is the short
            # body MIN_FEED_BYTES exists to catch.
            out.wrong_status.append(game)
        else:
            out.candidates.append(game)
    return out


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def staging_feed_path(sport_id: int, season: int, game_pk: int) -> Path:
    return (
        paths.REPO_ROOT
        / STAGING_FEEDS.format(sport_id=int(sport_id), season=int(season))
        / f"{int(game_pk)}.json"
    )


def staging_schedule_path(sport_id: int, season: int) -> Path:
    return paths.REPO_ROOT / STAGING_SCHEDULE.format(sport_id=int(sport_id), season=int(season))


def load_schedule(sport_id: int, season: int, *, allow_fetch: bool = True) -> dict[str, Any]:
    """The schedule for one sport and season: lake, then staging, then network.

    The lake copy is preferred because another step may already have stored it
    under the throttle. The staging copy is next, because it was pulled under
    the same A3 policy and costs nothing. The network is last and is one
    request, which section 10.1 budgets.
    """
    lake = paths.raw_schedule(sport_id, season)
    if lake.exists():
        return json.loads(_decompress(lake).decode("utf-8"))
    staged = staging_schedule_path(sport_id, season)
    if staged.exists():
        return json.loads(staged.read_text(encoding="utf-8"))
    if not allow_fetch:
        raise FileNotFoundError(
            f"no schedule for sport {sport_id} season {season} in the lake or in "
            f"staging, and fetching is disabled: {lake} / {staged}"
        )
    response = http.get(SCHEDULE_URL.format(sport_id=int(sport_id), season=int(season)))
    return response.json()


def import_staged(
    games: list[ScheduledGame], sport_id: int, season: int, *, report: list[str] | None = None
) -> dict[str, int]:
    """Store every candidate the staging cache already holds.

    Every imported byte is re-validated: the size window, the gamePk in the
    body, and the seal against the feed's own officialDate. The staging cache
    holds one sealed game (``823543``), and this is where it is refused.
    """
    counts = {"imported": 0, "already": 0, "sealed": 0, "invalid": 0, "absent": 0}
    for game in games:
        source = staging_feed_path(sport_id, season, game.game_pk)
        if not source.exists():
            counts["absent"] += 1
            continue
        if stored_path(sport_id, season, game.game_pk) is not None:
            counts["already"] += 1
            continue
        try:
            store_feed(sport_id, season, game.game_pk, source.read_bytes())
        except SealBreach as exc:
            counts["sealed"] += 1
            if report is not None:
                report.append(f"refused sealed {game.game_pk}: {exc}")
            continue
        except (ValueError, OSError) as exc:
            counts["invalid"] += 1
            if report is not None:
                report.append(f"refused invalid {game.game_pk}: {exc}")
            continue
        counts["imported"] += 1
    return counts


def remaining_after_import(
    games: list[ScheduledGame], sport_id: int, season: int
) -> list[ScheduledGame]:
    """The candidates with no sane stored file. This is the request queue."""
    return [g for g in games if stored_path(sport_id, season, g.game_pk) is None]


def fetch_games(
    games: list[ScheduledGame],
    sport_id: int,
    season: int,
    *,
    max_requests: int | None = None,
    report: list[str] | None = None,
) -> dict[str, int]:
    """Fetch one feed per game through the one HTTP chokepoint.

    ``absump.http.get`` enforces the 4 s statsapi spacing and the 3,000/day cap
    from ``config/throttle.yml``, caches the body so a re-run costs zero
    requests, and appends the manifest row. Nothing here sleeps, retries or
    counts a budget of its own: a second throttle is a second policy.
    """
    counts = {"fetched": 0, "skipped": 0, "sealed": 0, "failed": 0}
    for game in games:
        if max_requests is not None and counts["fetched"] >= max_requests:
            counts["skipped"] += 1
            continue
        if is_sealed(game.season, game.game_type, game.official_date):
            counts["sealed"] += 1
            if report is not None:
                report.append(f"refused sealed before request: {game.game_pk}")
            continue
        url = FEED_URL.format(game_pk=int(game.game_pk))
        try:
            response = http.get(url)
            if response.dry_run:
                counts["skipped"] += 1
                continue
            store_feed(sport_id, season, game.game_pk, response.content)
        except SealBreach as exc:
            counts["sealed"] += 1
            if report is not None:
                report.append(f"refused sealed after request: {game.game_pk}: {exc}")
            continue
        except (http.HttpError, ValueError, OSError) as exc:
            counts["failed"] += 1
            if report is not None:
                report.append(f"failed {game.game_pk}: {type(exc).__name__}: {exc}")
            continue
        counts["fetched"] += 1
    return counts


def fetch_controls(*, report: list[str] | None = None) -> dict[int, Path]:
    """Fetch the pre-ABS negative controls SOP W2.6 names, and store them.

    Three games, one request each, none of them in the 2026 pull: MLB 2025
    ``776311`` and AAA 2023 ``722770`` and ``723056``. They are the negative
    half of ``test_regime_marker``, and without them that test asserts only
    that the marker is present where it is expected, which any always-true
    implementation passes.
    """
    stored: dict[int, Path] = {}
    for game_pk, (sport_id, season) in sorted(PRE_ABS_CONTROL_GAMES.items()):
        existing = stored_path(sport_id, season, game_pk)
        if existing is not None:
            stored[game_pk] = existing
            continue
        try:
            response = http.get(FEED_URL.format(game_pk=game_pk))
            if response.dry_run:
                continue
            stored[game_pk] = store_feed(sport_id, season, game_pk, response.content)
        except (http.HttpError, SealBreach, ValueError, OSError) as exc:
            if report is not None:
                report.append(f"control {game_pk} failed: {type(exc).__name__}: {exc}")
    return stored


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_plan(the_plan: Plan, queue: int, sport_id: int, season: int, status: str) -> list[str]:
    counts = the_plan.counts()
    return [
        f"sport {sport_id} season {season} status {status}",
        f"  scheduled distinct games   {counts['scheduled']}",
        f"  excluded game types        {counts['excluded']}",
        f"  sealed, never requested    {counts['sealed']}",
        f"  status not {status:<14}  {counts['wrong_status']}",
        f"  candidates                 {counts['candidates']}",
        f"  queue after resume         {queue}",
        f"  estimated wall clock       {queue * 4.55 / 3600:.2f} h at 4 s spacing",
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m absump.ingest.feeds",
        description="Ingest statsapi GUMBO live feeds under the SOP A3 throttle (W2.6).",
    )
    parser.add_argument("--sport", type=int, required=True, help="statsapi sportId: 1 MLB, 11 AAA")
    parser.add_argument("--season", type=int, required=True, help="season year")
    parser.add_argument(
        "--status",
        default="Final",
        choices=("Final", "Live", "Preview", "any"),
        help="abstractGameState to queue; default Final",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip games already stored; a re-run then costs zero requests",
    )
    parser.add_argument(
        "--no-import-staging", action="store_true", help="do not import data/staging first"
    )
    parser.add_argument("--plan-only", action="store_true", help="print the plan and send nothing")
    parser.add_argument(
        "--max-requests", type=int, default=None, help="ceiling on requests this invocation issues"
    )
    parser.add_argument(
        "--controls",
        action="store_true",
        help="fetch the three pre-ABS negative-control feeds and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report: list[str] = []

    if args.controls:
        stored = fetch_controls(report=report)
        for line in report:
            print(line)
        for game_pk in sorted(PRE_ABS_CONTROL_GAMES):
            mark = "stored" if game_pk in stored else "MISSING"
            print(f"control {game_pk} {mark}")
        return 0 if len(stored) == len(PRE_ABS_CONTROL_GAMES) else 1

    schedule = load_schedule(args.sport, args.season, allow_fetch=not args.plan_only)
    games = schedule_games(schedule)
    the_plan = plan(games, status=args.status)

    if not args.no_import_staging:
        imported = import_staged(the_plan.candidates, args.sport, args.season, report=report)
        print(
            "staging import: "
            + " ".join(f"{key}={value}" for key, value in sorted(imported.items()))
        )

    queue = (
        remaining_after_import(the_plan.candidates, args.sport, args.season)
        if args.resume
        else list(the_plan.candidates)
    )
    for line in _format_plan(the_plan, len(queue), args.sport, args.season, args.status):
        print(line)

    if args.plan_only:
        for line in report:
            print(line)
        return 0

    fetched = fetch_games(
        queue, args.sport, args.season, max_requests=args.max_requests, report=report
    )
    print("fetch: " + " ".join(f"{key}={value}" for key, value in sorted(fetched.items())))
    for line in report:
        print(line)
    return 0 if fetched["failed"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    sys.exit(main())
