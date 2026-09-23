"""W4.2 / DT-25: the Savant per-team ABS challenge drawer.

Nothing here sends a request. The transport is a mock, the clock is fake, and
the rows are synthetic: a full-scale MLB 2026 league of 10,167 challenges,
mirrored across 30 team drawers, built to satisfy the four facts W4.2 derived
from 1,276 cached rows.

The edge formula is written out here a second time, straight from SOP section
2.5, and never imported from the module under test. That is deliberate: a test
that reuses the implementation's own arithmetic asserts nothing. The generator
uses this copy, so a change to the module's formula fails the comparison.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import math
import random
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from absump import http as client
from absump import paths
from absump.ingest import savant_drawer as drawer

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "contracts" / "savant_drawer.yml"
THROTTLE_PATH = REPO_ROOT / "config" / "throttle.yml"
SAVANT = "baseballsavant.mlb.com"

SEED = 20260922


# --------------------------------------------------------------------------
# SOP section 2.5, written out independently of the module under test
# --------------------------------------------------------------------------


def sop_edge(
    plate_x: float, plate_z: float, sz_top: float, sz_bot: float, width_in: float
) -> float:
    """The edge rule, verbatim from SOP section 2.5, with hw = widthinches/2.

    dx   = |plateX|*12 - hw
    dz   = max(strikeZoneBottom*12 - plateZ*12, plateZ*12 - strikeZoneTop*12)
    dist = hypot(dx, dz) if dx > 0 and dz > 0 else max(dx, dz)
    edge_dist_calc = dist - 1.45
    """
    hw = width_in / 2.0
    dx = abs(plate_x) * 12 - hw
    dz = max(sz_bot * 12 - plate_z * 12, plate_z * 12 - sz_top * 12)
    dist = math.hypot(dx, dz) if dx > 0 and dz > 0 else max(dx, dz)
    return dist - 1.45


# --------------------------------------------------------------------------
# A synthetic league that satisfies the four facts
# --------------------------------------------------------------------------


def _row(
    *,
    challenge: int,
    role: str,
    bat_team: int,
    fld_team: int,
    against: bool,
    game_date: _dt.date,
    rng: random.Random,
    season: int,
    level: str,
) -> dict[str, Any]:
    plate_x = rng.uniform(-1.30, 1.30)
    plate_z = rng.uniform(0.70, 4.30)
    sz_top = round(rng.uniform(3.20, 3.60), 8)
    sz_bot = round(rng.uniform(1.45, 1.85), 8)
    width = 17.0
    edge = sop_edge(plate_x, plate_z, sz_top, sz_bot, width)

    batter = 600_000 + challenge * 3
    catcher = 600_001 + challenge * 3
    pitcher = 600_002 + challenge * 3
    challenger = {"batter": batter, "catcher": catcher, "pitcher": pitcher}[role]

    # Fact 5: role == batter iff the umpire called a strike.
    original_is_strike = 1 if role == "batter" else 0
    # Fact 3: overturn is deterministic.
    overturned = bool(original_is_strike == 1) ^ bool(edge < 0)

    return {
        "year": season,
        "game_pk": 800_000 + challenge // 4,
        "play_id": f"{challenge:08x}-0000-4000-8000-{challenge:012d}",
        "game_date": game_date.isoformat(),
        "event_inning": 1 + challenge % 9,
        "outs": challenge % 3,
        "pre_ball_count": challenge % 4,
        "pre_strike_count": challenge % 3,
        "bat_score": challenge % 7,
        "fld_score": challenge % 5,
        "bat_side": "L" if challenge % 2 else "R",
        "player_at_bat": batter,
        "pitcher": pitcher,
        "fielder_2": catcher,
        "challenging_player_id": challenger,
        "batter_name": f"Batter {challenge}",
        "pitcher_name": f"Pitcher {challenge}",
        "catcher_name": f"Catcher {challenge}",
        "bat_team_id": bat_team,
        "fld_team_id": fld_team,
        "opp_team": fld_team if not against else bat_team,
        "original_isStrike_ump": original_is_strike,
        "is_challengeABS_overturned": overturned,
        "is_challengeABS_reasonable_attempt": bool(abs(edge) < 1.0),
        "edge_dist_calc": edge,
        "sz_challenge_prob": round(rng.random(), 6),
        "sz_challenge_prob_gain": round(rng.random(), 6),
        "sz_challenge_prob_lost": round(rng.random(), 6),
        "chal_gained": int(overturned),
        "chal_lost": int(not overturned),
        "sz_challenge_runs": round(rng.uniform(-1, 1), 6),
        "sz_challenge_overturned_runs": round(rng.uniform(-1, 1), 6),
        "sz_challenge_lost_runs": round(rng.uniform(-1, 1), 6),
        "is_strike3_removed": False,
        "is_ball4_added": False,
        "is_strikeout_overturn": False,
        "is_walk_overturn": False,
        "plateX": plate_x,
        "plateZ": plate_z,
        "strikeZoneTop": sz_top,
        "strikeZoneBottom": sz_bot,
        "widthinches": width,
        "against": against,
        # Present in the feed, never read. The module is scanned for read sites.
        "team_summary_mode": "catcher-for",
        "level": level.upper(),
    }


def build_league(
    level: str = "mlb",
    *,
    total: int | None = None,
    batter_side: int | None = None,
    past_cutoff_per_team: int = 0,
) -> dict[drawer.Target, list[dict[str, Any]]]:
    """One row per (challenge, team), mirrored: against False then against True."""
    spec = drawer.contract()["dt25"]
    total = int(spec["expected_total"]) if total is None else total
    batter_side = int(spec["expected_batter_side"]) if batter_side is None else batter_side

    targets = {t.team_id: t for t in drawer.plan([level])}
    ids = sorted(targets)
    rows: dict[int, list[dict[str, Any]]] = {team_id: [] for team_id in ids}
    rng = random.Random(SEED)
    season = drawer.season_of(level)

    for challenge in range(total):
        role = "batter" if challenge < batter_side else ("catcher", "pitcher")[challenge % 2]
        own = ids[challenge % len(ids)]
        opponent = ids[(challenge * 7 + 13) % len(ids)]
        if opponent == own:
            opponent = ids[(challenge + 1) % len(ids)]
        game_date = paths.LAST_OPEN_DATE - _dt.timedelta(days=challenge % 170)
        common = {
            "challenge": challenge,
            "role": role,
            "rng": rng,
            "season": season,
            "level": level,
        }
        rows[own].append(
            _row(bat_team=own, fld_team=opponent, against=False, game_date=game_date, **common)
        )
        mirror = copy.deepcopy(rows[own][-1])
        mirror["against"] = True
        mirror["opp_team"] = own
        rows[opponent].append(mirror)

    if past_cutoff_per_team:
        beyond = paths.LAST_OPEN_DATE + _dt.timedelta(days=1)
        for n, team_id in enumerate(ids):
            for k in range(past_cutoff_per_team):
                marker = 10_000_000 + n * 1_000 + k
                rows[team_id].append(
                    _row(
                        challenge=marker,
                        role="batter",
                        bat_team=team_id,
                        fld_team=ids[(n + 1) % len(ids)],
                        against=False,
                        game_date=beyond,
                        rng=rng,
                        season=season,
                        level=level,
                    )
                )

    return {targets[team_id]: rows[team_id] for team_id in ids}


@pytest.fixture(scope="module")
def league() -> dict[drawer.Target, list[dict[str, Any]]]:
    return build_league("mlb")


# --------------------------------------------------------------------------
# The contract file itself
# --------------------------------------------------------------------------


def test_contract_parses_and_states_the_sop_numbers() -> None:
    loaded = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert loaded == drawer.contract()
    assert loaded["schema"]["key_count"] == 66
    assert len(loaded["schema"]["required_keys"]) == 45
    assert len(set(loaded["schema"]["required_keys"])) == 45
    assert loaded["facts"]["sample_rows"] == 708 + 568 == 1276
    assert loaded["facts"]["edge"]["ball_radius_in"] == 1.45
    assert loaded["facts"]["overturn"]["rows_outside_band"] == 953
    assert loaded["dt25"]["expected_total"] == 10167
    assert (
        loaded["dt25"]["expected_batter_side"] + loaded["dt25"]["expected_fielding_side"]
        == loaded["dt25"]["expected_total"]
    )
    assert loaded["pull"]["targets"] == 60
    assert loaded["team_index"]["mlb"]["count"] == loaded["team_index"]["aaa"]["count"] == 30
    assert loaded["team_index"]["aaa"]["body_bytes"] == 20380


def test_contract_names_the_forbidden_key_and_its_four_values() -> None:
    schema = drawer.contract()["schema"]
    assert drawer.forbidden_keys() == ("team_summary_mode",)
    assert sorted(schema["team_summary_mode_values"]) == [
        "batter-against",
        "batter-for",
        "catcher-against",
        "catcher-for",
    ]
    assert "team_summary_mode" in schema["required_keys"]


# --------------------------------------------------------------------------
# The parameter form: the year= / gameType=regular form, and the silent failure
# --------------------------------------------------------------------------


def test_drawer_url_is_the_working_form() -> None:
    url = drawer.drawer_url(113, 2026, "mlb")
    assert url.startswith("https://baseballsavant.mlb.com/leaderboard/services/abs/113?")
    for fragment in (
        "year=2026",
        "challengeType=team-summary",
        "gameType=regular",
        "level=mlb",
        "minChal=1",
        "minOppChal=0",
        "dataCount=runs",
        "groupBy=",
    ):
        assert fragment in url, fragment
    assert "season[]" not in url
    assert "gameType[]" not in url


def test_the_form_the_page_declares_is_refused_before_a_request_is_spent() -> None:
    for bad in (
        "https://baseballsavant.mlb.com/leaderboard/services/abs/113?season[]=2026"
        "&challengeType=team-summary&gameType=regular&level=mlb&year=2026",
        "https://baseballsavant.mlb.com/leaderboard/services/abs/113?year=2026"
        "&challengeType=team-summary&gameType[]=R&level=mlb&gameType=regular",
    ):
        with pytest.raises(drawer.DrawerError, match="empty data array"):
            drawer.assert_working_form(bad)


def test_a_drawer_url_missing_a_required_parameter_is_refused() -> None:
    with pytest.raises(drawer.DrawerError, match="missing"):
        drawer.assert_working_form(
            "https://baseballsavant.mlb.com/leaderboard/services/abs/113?year=2026&level=mlb"
        )


def test_an_empty_envelope_is_a_contract_failure_not_an_empty_season() -> None:
    envelope = drawer.contract()["endpoint"]["empty_envelope"].encode("utf-8")
    assert len(envelope) == drawer.contract()["endpoint"]["empty_envelope_bytes"] == 11
    with pytest.raises(drawer.EmptyEnvelope):
        drawer.rows_of(json.loads(envelope))


def test_level_must_be_mlb_or_aaa() -> None:
    with pytest.raises(drawer.DrawerError):
        drawer.drawer_url(113, 2026, "aa")


# --------------------------------------------------------------------------
# The plan: 60 team-seasons, offline
# --------------------------------------------------------------------------


def test_plan_is_sixty_team_seasons_thirty_of_each_level() -> None:
    targets = drawer.plan()
    assert len(targets) == drawer.contract()["pull"]["targets"] == 60
    mlb = [t for t in targets if t.level == "mlb"]
    aaa = [t for t in targets if t.level == "aaa"]
    assert len(mlb) == len(aaa) == 30
    assert {t.season for t in mlb} == {2026}
    assert {t.season for t in aaa} == {2025}
    assert len({t.url for t in targets}) == 60
    assert len({str(t.path) for t in targets}) == 60
    assert 113 in {t.team_id for t in mlb}
    assert 416 in {t.team_id for t in aaa}
    assert next(t for t in aaa if t.team_id == 416).team_name == "Louisville Bats"


def test_every_plan_path_is_minted_by_paths() -> None:
    for target in drawer.plan():
        assert paths.assert_minted(target.path) == target.path
        assert target.path.suffix == ".json"


def test_the_pull_fits_the_savant_throttle_and_cap() -> None:
    throttle = yaml.safe_load(THROTTLE_PATH.read_text(encoding="utf-8"))
    delay = float(throttle["min_interval_seconds"][SAVANT])
    cap = int(throttle["daily_request_budget"][SAVANT])
    requests = drawer.contract()["pull"]["requests"]
    assert requests == 60
    assert requests * delay / 60.0 == pytest.approx(10.0)
    assert requests <= cap


# --------------------------------------------------------------------------
# Fact 2: edge_dist_calc is exactly reproducible
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("plate_x", "plate_z", "sz_top", "sz_bot", "expected"),
    [
        # Dead centre: dx and dz both negative, so dist is max(dx, dz) = -8.5.
        (0.0, 2.5, 3.4, 1.6, -8.5 - 1.45),
        # Wide, vertically inside: dx = 12 - 8.5 = 3.5 in, dz negative.
        (1.0, 2.5, 3.4, 1.6, 3.5 - 1.45),
        # High and wide: both positive, Euclidean at the corner.
        (1.0, 3.8, 3.4, 1.6, math.sqrt(3.5**2 + 4.8**2) - 1.45),
        # Low and wide: dz = 19.2 - 6.0 = 13.2 in.
        (1.0, 0.5, 3.4, 1.6, math.sqrt(3.5**2 + 13.2**2) - 1.45),
        # Sign of plateX does not matter.
        (-1.0, 2.5, 3.4, 1.6, 3.5 - 1.45),
    ],
)
def test_edge_formula_against_hand_computed_geometry(
    plate_x: float, plate_z: float, sz_top: float, sz_bot: float, expected: float
) -> None:
    row = {
        "plateX": plate_x,
        "plateZ": plate_z,
        "strikeZoneTop": sz_top,
        "strikeZoneBottom": sz_bot,
        "widthinches": 17.0,
    }
    assert drawer.edge_dist_in(row) == pytest.approx(expected, abs=1e-12)
    assert sop_edge(plate_x, plate_z, sz_top, sz_bot, 17.0) == pytest.approx(expected, abs=1e-12)


def test_module_edge_matches_the_section_2_5_formula_on_the_league(league) -> None:
    finding = drawer.check_edge([row for rows in league.values() for row in rows])
    assert finding.passed, finding.line()
    assert "max abs error 0.000000 in" in finding.observed


def test_check_edge_fails_when_one_row_disagrees(league) -> None:
    rows = [copy.copy(row) for rows in league.values() for row in rows][:500]
    rows[17] = dict(rows[17], edge_dist_calc=rows[17]["edge_dist_calc"] + 0.01)
    finding = drawer.check_edge(rows)
    assert not finding.passed
    assert "0.010000" in finding.observed


def test_edge_reads_the_plate_x_alias(league) -> None:
    row = dict(next(iter(league.values()))[0])
    row["plate_X"] = row.pop("plateX")
    row["plate_Z"] = row.pop("plateZ")
    assert drawer.edge_dist_in(row) == pytest.approx(row["edge_dist_calc"], abs=1e-12)


# --------------------------------------------------------------------------
# Fact 1: original_isStrike_ump exists
# --------------------------------------------------------------------------


def test_schema_requires_the_original_call(league) -> None:
    rows = [row for rows in league.values() for row in rows]
    assert drawer.check_schema(rows).passed
    stripped = [dict(rows[0])]
    del stripped[0]["original_isStrike_ump"]
    finding = drawer.check_schema(stripped)
    assert not finding.passed
    assert "original_isStrike_ump absent" in finding.observed


def test_schema_fails_on_any_missing_named_key(league) -> None:
    row = dict(next(iter(league.values()))[0])
    del row["sz_challenge_prob"]
    finding = drawer.check_schema([row])
    assert not finding.passed
    assert "sz_challenge_prob" in finding.observed


# --------------------------------------------------------------------------
# Fact 3: overturn is deterministic
# --------------------------------------------------------------------------


def test_overturn_is_deterministic_on_the_league(league) -> None:
    rows = [row for rows in league.values() for row in rows]
    finding = drawer.check_overturn(rows)
    assert finding.passed, finding.line()
    assert f"{len(rows)}/{len(rows)} rows" in finding.observed
    assert "outside the +/- 0.5 in band" in finding.observed


def test_check_overturn_fails_on_a_single_flipped_row(league) -> None:
    rows = [dict(row) for rows in league.values() for row in rows][:800]
    rows[42]["is_challengeABS_overturned"] = not rows[42]["is_challengeABS_overturned"]
    assert not drawer.check_overturn(rows).passed


# --------------------------------------------------------------------------
# Fact 4: role resolves, and team_summary_mode is never read
# --------------------------------------------------------------------------


def test_role_resolves_for_every_row_with_zero_unresolved(league) -> None:
    rows = [row for rows in league.values() for row in rows]
    finding = drawer.check_role(rows)
    assert finding.passed, finding.line()
    assert "0 unresolved" in finding.observed
    assert {drawer.role_of(row) for row in rows[:2000]} <= {"batter", "catcher", "pitcher"}


def test_role_of_raises_when_the_challenger_matches_nothing(league) -> None:
    row = dict(next(iter(league.values()))[0])
    row["challenging_player_id"] = 1
    with pytest.raises(drawer.DrawerError, match="matches no role field"):
        drawer.role_of(row)


def test_role_of_raises_on_an_ambiguous_challenger(league) -> None:
    row = dict(next(iter(league.values()))[0])
    row["fielder_2"] = row["player_at_bat"]
    row["challenging_player_id"] = row["player_at_bat"]
    with pytest.raises(drawer.DrawerError, match="ambiguous"):
        drawer.role_of(row)


def test_batter_role_is_exactly_the_called_strike(league) -> None:
    rows = [row for rows in league.values() for row in rows]
    for row in rows[:3000]:
        assert (drawer.role_of(row) == "batter") == (row["original_isStrike_ump"] == 1)
    broken = [dict(rows[0])]
    broken[0]["original_isStrike_ump"] = 0
    broken[0]["is_challengeABS_overturned"] = not broken[0]["is_challengeABS_overturned"]
    finding = drawer.check_role(broken)
    assert not finding.passed
    assert "1 role/call mismatches" in finding.observed


def test_the_module_never_reads_team_summary_mode(league) -> None:
    rows = [row for rows in league.values() for row in rows]
    finding = drawer.check_no_forbidden_key(rows)
    assert finding.passed, finding.line()
    assert "0 read site(s)" in finding.observed


def test_the_read_site_scanner_catches_every_idiom_it_claims() -> None:
    key = drawer.forbidden_keys()[0]
    planted = "\n".join(
        [
            f'    mode = row["{key}"]',
            f"    mode = row['{key}']",
            f'    mode = row.get("{key}", None)',
            f'    mode = row.pop("{key}")',
            f"    mode = row.{key}",
        ]
    )
    assert len(drawer.read_sites(planted, key)) == 5
    assert drawer.read_sites(f"    # {key} is never read\n", key) == []


# --------------------------------------------------------------------------
# The cutoff
# --------------------------------------------------------------------------


def test_open_rows_keeps_the_last_open_day_and_drops_the_next(league) -> None:
    row = dict(next(iter(league.values()))[0])
    last_open = dict(row, game_date=paths.LAST_OPEN_DATE.isoformat())
    beyond = dict(row, game_date=(paths.LAST_OPEN_DATE + _dt.timedelta(days=1)).isoformat())
    assert drawer.open_rows([last_open, beyond]) == [last_open]


def test_open_rows_leaves_an_earlier_season_alone() -> None:
    aaa = build_league("aaa", total=40, batter_side=20)
    rows = [row for rows in aaa.values() for row in rows]
    assert drawer.open_rows(rows) == rows


def test_a_row_without_a_readable_game_date_is_an_error(league) -> None:
    row = dict(next(iter(league.values()))[0], game_date="")
    with pytest.raises(drawer.DrawerError, match="game_date"):
        drawer.open_rows([row])


# --------------------------------------------------------------------------
# DT-25
# --------------------------------------------------------------------------


def test_dt25_tolerance_is_derived_from_the_contract_not_chosen() -> None:
    spec = drawer.contract()["dt25"]
    assert spec["tolerance_days"] * spec["games_per_day_max"] * 2 == 60
    assert math.ceil(60 * spec["challenges_per_team_game"]) == 137


def test_dt25_passes_on_a_complete_league(league) -> None:
    finding = drawer.dt25(league)
    assert finding.passed, finding.line()
    assert finding.id == "DT-25"
    assert "30/30 mlb 2026 team-seasons" in finding.observed
    assert "10167 distinct play_id (4612 batting + 5555 fielding)" in finding.observed


def test_dt25_counts_each_challenge_once_not_twice(league) -> None:
    rows = [row for rows in league.values() for row in rows]
    assert len(rows) == 2 * 10167
    assert sum(1 for row in rows if not row["against"]) == 10167


def test_dt25_ignores_rows_past_the_cutoff() -> None:
    padded = build_league("mlb", past_cutoff_per_team=20)
    finding = drawer.dt25(padded)
    assert finding.passed, finding.line()
    assert "10167 distinct play_id" in finding.observed


def test_dt25_fails_when_a_team_season_is_missing(league) -> None:
    short = dict(league)
    short.pop(next(iter(short)))
    finding = drawer.dt25(short)
    assert not finding.passed
    assert "29/30" in finding.observed


def test_dt25_fails_when_the_league_total_falls_outside_the_tolerance(league) -> None:
    thinned = {
        target: [row for row in rows if row["against"] or int(row["play_id"][:8], 16) % 20]
        for target, rows in league.items()
    }
    finding = drawer.dt25(thinned)
    assert not finding.passed


def test_dt25_fails_when_the_batting_fielding_split_moves() -> None:
    skewed = build_league("mlb", total=10167, batter_side=4612 - 300)
    finding = drawer.dt25(skewed)
    assert not finding.passed
    assert "4312 batting" in finding.observed


def test_dt25_needs_a_play_id_on_every_own_row(league) -> None:
    broken = {target: [dict(row) for row in rows] for target, rows in league.items()}
    first = next(iter(broken))
    broken[first][0]["play_id"] = ""
    with pytest.raises(drawer.DrawerError, match="play_id"):
        drawer.dt25(broken)


def test_dt25_is_left_out_rather_than_passed_when_its_level_is_absent() -> None:
    aaa = build_league("aaa", total=40, batter_side=20)
    assert not drawer.dt25_applies(aaa)
    assert [finding.id for finding in drawer.check_all(aaa)] == [
        "DT-25.schema",
        "DT-25.edge",
        "DT-25.overturn",
        "DT-25.role",
        "DT-25.forbidden",
    ]


def test_check_all_runs_dt25_when_its_level_is_present(league) -> None:
    findings = drawer.check_all(league)
    assert [finding.id for finding in findings][-1] == "DT-25"
    assert all(finding.passed for finding in findings), [f.line() for f in findings]


# --------------------------------------------------------------------------
# The fetch, through the one chokepoint, with a mock transport
# --------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """absump.http with a mock transport, a fake clock and a private cache."""
    clock = FakeClock()
    calls: list[str] = []
    bodies: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=bodies.get(str(request.url), b'{"data":[]}'))

    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path / "lake"))
    client._reset_state(cache_dir=tmp_path / "cache", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client, "_sleep", clock.sleep)
    monkeypatch.setattr(client, "_monotonic", clock.monotonic)
    try:
        yield calls, bodies
    finally:
        client._reset_state()


def _payload(target: drawer.Target) -> bytes:
    league = build_league(target.level, total=40, batter_side=20)
    rows = next(rows for t, rows in league.items() if t.team_id == target.team_id)
    return json.dumps({"data": rows}).encode("utf-8")


def test_fetch_writes_the_json_once_and_the_second_call_sends_nothing(wired) -> None:
    calls, bodies = wired
    target = drawer.plan(["mlb"])[0]
    bodies[target.url] = _payload(target)

    rows = drawer.fetch(target)
    assert len(calls) == 1
    assert target.path.exists()
    assert len(rows) == len(drawer.load(target.path))
    first = target.path.read_bytes()

    assert drawer.fetch(target)
    assert len(calls) == 1, "a cached URL must cost zero requests"
    assert target.path.read_bytes() == first, "raw bytes are immutable"


def test_fetch_refuses_an_empty_envelope_and_writes_no_file(wired) -> None:
    calls, _ = wired
    target = drawer.plan(["mlb"])[0]
    with pytest.raises(drawer.EmptyEnvelope):
        drawer.fetch(target)
    assert len(calls) == 1
    assert not target.path.exists()


def test_pull_skips_a_target_already_on_disk(wired, capsys) -> None:
    calls, bodies = wired
    targets = drawer.plan(["mlb"])[:3]
    for target in targets:
        bodies[target.url] = _payload(target)

    assert len(drawer.pull(targets)) == 3
    assert len(calls) == 3
    assert drawer.pull(targets) == []
    assert len(calls) == 3
    assert capsys.readouterr().out.count("cached") == 3


def test_pull_reports_the_rows_it_would_have_to_drop(wired, capsys) -> None:
    _, bodies = wired
    target = drawer.plan(["mlb"])[0]
    league = build_league("mlb", total=40, batter_side=20, past_cutoff_per_team=2)
    rows = next(rows for t, rows in league.items() if t.team_id == target.team_id)
    bodies[target.url] = json.dumps({"data": rows}).encode("utf-8")
    drawer.pull([target])
    out = capsys.readouterr().out
    assert f"2 past the {paths.LAST_OPEN_DATE.isoformat()} cutoff" in out


# --------------------------------------------------------------------------
# The command line, which is what the verify command runs
# --------------------------------------------------------------------------


def test_plan_mode_sends_nothing_and_prints_sixty_targets(capsys) -> None:
    assert drawer.main(["--plan"]) == 0
    out = capsys.readouterr().out
    assert "60 target(s), 60 Savant requests" in out
    assert out.count("https://baseballsavant.mlb.com/leaderboard/services/abs/") == 60
    assert "Nothing sent." in out


def test_check_mode_is_green_and_explicit_on_a_clean_clone(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path / "empty"))
    assert drawer.main(["--check"]) == 0
    assert "0 of 60 drawer files on disk" in capsys.readouterr().out


def test_check_mode_runs_dt25_over_the_files_on_disk(tmp_path, monkeypatch, capsys, league) -> None:
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path / "lake"))
    for target, rows in league.items():
        written = paths.raw_savant_drawer(target.level, target.season, target.team_id)
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(json.dumps({"data": rows}), encoding="utf-8")

    assert drawer.main(["--check", "--level", "mlb"]) == 0
    out = capsys.readouterr().out
    assert "PASS  DT-25  drawer completeness" in out
    assert "6/6 assertions pass over 30/30 cached team-seasons." in out


def test_check_mode_is_red_when_a_team_season_is_missing(
    tmp_path, monkeypatch, capsys, league
) -> None:
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path / "lake"))
    for n, (target, rows) in enumerate(league.items()):
        if n == 0:
            continue
        written = paths.raw_savant_drawer(target.level, target.season, target.team_id)
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(json.dumps({"data": rows}), encoding="utf-8")

    assert drawer.main(["--check", "--level", "mlb"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  DT-25" in out
    assert "29/30 mlb 2026 team-seasons" in out


def test_check_mode_is_red_when_a_cached_row_breaks_a_fact(
    tmp_path, monkeypatch, capsys, league
) -> None:
    monkeypatch.setenv("ABS_DATA_ROOT", str(tmp_path / "lake"))
    for n, (target, rows) in enumerate(league.items()):
        payload = [dict(row) for row in rows]
        if n == 0:
            payload[0]["edge_dist_calc"] = payload[0]["edge_dist_calc"] + 0.25
        written = paths.raw_savant_drawer(target.level, target.season, target.team_id)
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(json.dumps({"data": payload}), encoding="utf-8")

    assert drawer.main(["--check", "--level", "mlb"]) == 1
    assert "FAIL  DT-25.edge" in capsys.readouterr().out


def test_an_empty_row_set_is_not_a_pass() -> None:
    """A check with nothing to read has proved nothing, so it is red."""
    for check in (
        drawer.check_schema,
        drawer.check_edge,
        drawer.check_overturn,
        drawer.check_role,
    ):
        finding = check([])
        assert not finding.passed, finding.line()
        assert finding.observed == "0 rows to check"


def test_pull_under_a_dry_run_sends_nothing_and_writes_nothing(wired, monkeypatch, capsys) -> None:
    calls, bodies = wired
    monkeypatch.setenv("ABSUMP_DRY_RUN", "1")
    target = drawer.plan(["mlb"])[0]
    bodies[target.url] = _payload(target)

    assert drawer.pull([target]) == []
    assert calls == []
    assert not target.path.exists()
    assert "dry run, nothing sent" in capsys.readouterr().out
