"""RP-09: the throttle config and every budget table in the SOP agree.

SOP section 2.3 and section 5A item A3 state one policy per host, once. Owner
decision D-63. Section 10.1, W6.0, R-07 and R-08 are derived from it and never
restate it with different numbers. This test is the thing that keeps that true:
it holds the table, asserts ``config/throttle.yml`` matches it row by row, and
then asserts that every row of section 10.1's network table is what this table
implies, request count by request count.

The table lives here rather than being scraped out of the SOP because the SOP
is private planning material (D-03) and is not in the public repository, while
this test has to run in a clean clone (RP-08).
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest
import yaml

from absump import http as client

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "throttle.yml"

SAVANT = "baseballsavant.mlb.com"
STATSAPI = "statsapi.mlb.com"
RETROSHEET = "www.retrosheet.org"

USER_AGENT = (
    "abs-umpires-research/0.1 (academic research project; "
    "polite single-day pulls; github.com/hpagni/abs-umpires)"
)

# Section 2.3 / section 5A.A3, verbatim. Savant 10 s and 800/day, statsapi 4 s
# and 3,000/day, every other host 10 s and 500/day.
SECTION_2_3_DELAY = {
    SAVANT: 10.0,
    STATSAPI: 4.0,
    RETROSHEET: 10.0,
    "api.the-odds-api.com": 10.0,
    "api.elections.kalshi.com": 10.0,
    "statds.org": 10.0,
    "default": 10.0,
}
SECTION_2_3_CAP = {
    SAVANT: 800,
    STATSAPI: 3000,
    RETROSHEET: 500,
    "api.the-odds-api.com": 500,
    "api.elections.kalshi.com": 500,
    "statds.org": 500,
    "default": 500,
}

# Section 10.1, "Network and wall clock", row by row:
# (label, host, requests, stated wall clock, unit). Minutes are stated rounded
# up; hours are stated to one decimal.
SECTION_10_1 = [
    ("Schedules, MLB and AAA, with officials", STATSAPI, 8, 1, "min"),
    ("Batter heights via /api/v1/people", STATSAPI, 15, 1, "min"),
    ("AAA changeover binary search (D-57)", STATSAPI, 40, 3, "min"),
    ("MLB feeds, paper tier", STATSAPI, 2512, 2.8, "h"),
    ("AAA feeds", STATSAPI, 6450, 7.2, "h"),
    ("Statcast MLB days, sprint", SAVANT, 920, 2.6, "h"),
    ("Statcast MLB days, backfill", SAVANT, 1310, 3.6, "h"),
    ("Statcast AAA days", SAVANT, 450, 1.3, "h"),
    ("Savant ABS leaderboard, 28 views", SAVANT, 28, 5, "min"),
    ("Savant drawer, 30 MLB + 30 AAA teams", SAVANT, 60, 10, "min"),
    ("Savant catcher framing", SAVANT, 12, 2, "min"),
    ("Retrosheet plays", RETROSHEET, 11, 2, "min"),
]

# Section 10.1's own totals, which must fall out of the rows above.
TOTAL_REQUESTS = 11_816
TOTAL_HOURS = 17.8
BY_HOST_REQUESTS = {STATSAPI: 9025, SAVANT: 2780, RETROSHEET: 11}
BY_HOST_HOURS = {STATSAPI: 10.0, SAVANT: 7.7}
MINIMUM_CALENDAR_NIGHTS = 4

# Section 10.1, the sprint-critical subset: 920 Statcast days plus the 100
# drawer, leaderboard and framing requests on Savant, and 63 statsapi
# requests. The 2,512-game feed pull is not in it under D-62.
SPRINT_SAVANT = 920 + 60 + 28 + 12
SPRINT_STATSAPI = 8 + 15 + 40
SPRINT_REQUESTS = 1083
SPRINT_HOURS = 3.0

# Section 10.1 states a night count for the three pulls that exceed a cap.
SECTION_10_1_NIGHTS = {
    ("AAA feeds", STATSAPI, 6450): 3,
    ("Statcast MLB days, sprint", SAVANT, 920): 2,
    ("Statcast MLB days, backfill", SAVANT, 1310): 2,
}


def stated_hours(seconds: float) -> float:
    """Section 10.1 states hours to one decimal, rounded half up."""
    return float(Decimal(seconds / 3600.0).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The config is the table
# ---------------------------------------------------------------------------


def test_the_config_file_exists_and_has_exactly_the_expected_keys(config: dict) -> None:
    assert CONFIG_PATH.is_file()
    assert set(config) == {
        "user_agent",
        "timeout_seconds",
        "max_attempts",
        "backoff_base_seconds",
        "min_interval_seconds",
        "daily_request_budget",
        "cache_dir",
    }


def test_min_interval_seconds_matches_section_2_3_row_by_row(config: dict) -> None:
    assert config["min_interval_seconds"] == SECTION_2_3_DELAY
    for host, delay in SECTION_2_3_DELAY.items():
        assert isinstance(config["min_interval_seconds"][host], float)
        assert config["min_interval_seconds"][host] == delay


def test_daily_request_budget_matches_section_2_3_row_by_row(config: dict) -> None:
    assert config["daily_request_budget"] == SECTION_2_3_CAP
    for host, cap in SECTION_2_3_CAP.items():
        assert isinstance(config["daily_request_budget"][host], int)
        assert config["daily_request_budget"][host] == cap


def test_every_host_with_a_delay_also_has_a_cap(config: dict) -> None:
    assert set(config["min_interval_seconds"]) == set(config["daily_request_budget"])


def test_the_three_row_policy_holds_for_every_host_in_the_config(config: dict) -> None:
    delays = config["min_interval_seconds"]
    caps = config["daily_request_budget"]
    assert (delays[SAVANT], caps[SAVANT]) == (10.0, 800)
    assert (delays[STATSAPI], caps[STATSAPI]) == (4.0, 3000)
    for host in delays:
        if host in (SAVANT, STATSAPI):
            continue
        assert (delays[host], caps[host]) == (10.0, 500), f"{host} is not on the 10 s / 500 row"


def test_the_scalar_settings_are_section_2_3s(config: dict) -> None:
    assert config["user_agent"] == USER_AGENT
    assert config["timeout_seconds"] == 30
    assert config["max_attempts"] == 4
    assert config["backoff_base_seconds"] == 4
    assert config["cache_dir"] == "data/raw"


def test_the_user_agent_sends_no_email_address(config: dict) -> None:
    # Section 2.3: no email address is ever sent to any host.
    assert "@" not in config["user_agent"]
    assert config["user_agent"].startswith("abs-umpires-research/0.1")
    assert "github.com/hpagni/abs-umpires" in config["user_agent"]


# ---------------------------------------------------------------------------
# Section 10.1 is derived from the table, row by row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "host", "requests", "stated", "unit"), SECTION_10_1)
def test_section_10_1_wall_clock_is_the_config_delay_times_the_request_count(
    config: dict, label: str, host: str, requests: int, stated: float, unit: str
) -> None:
    seconds = requests * config["min_interval_seconds"][host]
    if unit == "min":
        assert math.ceil(seconds / 60.0) == stated, f"{label}: {seconds} s is not {stated} min"
    else:
        assert stated_hours(seconds) == stated, f"{label}: {seconds} s is not {stated} h"


@pytest.mark.parametrize(("key", "nights"), sorted(SECTION_10_1_NIGHTS.items()))
def test_section_10_1_night_counts_are_the_config_cap(
    config: dict, key: tuple[str, str, int], nights: int
) -> None:
    _label, host, requests = key
    assert math.ceil(requests / config["daily_request_budget"][host]) == nights


def test_section_10_1_totals_fall_out_of_the_rows(config: dict) -> None:
    delays = config["min_interval_seconds"]
    total_requests = sum(row[2] for row in SECTION_10_1)
    total_seconds = sum(row[2] * delays[row[1]] for row in SECTION_10_1)

    assert total_requests == TOTAL_REQUESTS
    assert stated_hours(total_seconds) == TOTAL_HOURS


@pytest.mark.parametrize("host", sorted(BY_HOST_REQUESTS))
def test_section_10_1_per_host_totals_fall_out_of_the_rows(config: dict, host: str) -> None:
    requests = sum(row[2] for row in SECTION_10_1 if row[1] == host)
    assert requests == BY_HOST_REQUESTS[host]
    if host in BY_HOST_HOURS:
        seconds = requests * config["min_interval_seconds"][host]
        assert stated_hours(seconds) == BY_HOST_HOURS[host]


def test_the_whole_pull_needs_at_least_four_calendar_nights(config: dict) -> None:
    caps = config["daily_request_budget"]
    nights = max(math.ceil(requests / caps[host]) for host, requests in BY_HOST_REQUESTS.items())
    assert nights >= MINIMUM_CALENDAR_NIGHTS


def test_the_sprint_subset_is_1083_requests_and_about_three_hours(config: dict) -> None:
    delays = config["min_interval_seconds"]
    assert SPRINT_SAVANT + SPRINT_STATSAPI == SPRINT_REQUESTS
    seconds = SPRINT_SAVANT * delays[SAVANT] + SPRINT_STATSAPI * delays[STATSAPI]
    # Section 10.1 states "about 3.0 h" for this subset.
    assert abs(seconds / 3600.0 - SPRINT_HOURS) <= 0.1
    # The 2,512-game feed pull is not in the sprint under D-62.
    assert SPRINT_REQUESTS < 2512


# ---------------------------------------------------------------------------
# The client reads the config and nothing else
# ---------------------------------------------------------------------------


def test_the_client_returns_the_config_rows(config: dict) -> None:
    client._reset_state()
    try:
        for host, delay in config["min_interval_seconds"].items():
            if host == "default":
                continue
            assert client._min_interval(host) == delay
            assert client._daily_cap(host) == config["daily_request_budget"][host]
        unknown = "a-host-in-no-table.example"
        assert client._min_interval(unknown) == config["min_interval_seconds"]["default"]
        assert client._daily_cap(unknown) == config["daily_request_budget"]["default"]
    finally:
        client._reset_state()


def test_the_client_has_no_baked_in_delay_or_cap(tmp_path: Path, config: dict) -> None:
    # If the client carried its own copy of the table, this would still return
    # the real numbers. Section 2.3: it reads config/throttle.yml and nothing
    # else.
    altered = dict(config)
    altered["min_interval_seconds"] = dict(config["min_interval_seconds"], **{SAVANT: 7.5})
    altered["daily_request_budget"] = dict(config["daily_request_budget"], **{SAVANT: 42})
    path = tmp_path / "throttle.yml"
    path.write_text(yaml.safe_dump(altered), encoding="utf-8")

    client._reset_state(config_path=path, cache_dir=tmp_path / "raw")
    try:
        assert client._min_interval(SAVANT) == 7.5
        assert client._daily_cap(SAVANT) == 42
    finally:
        client._reset_state()


def test_a_config_with_an_email_in_the_user_agent_is_refused(tmp_path: Path, config: dict) -> None:
    broken = dict(config, user_agent="abs-umpires-research/0.1 (contact: someone@example.com)")
    path = tmp_path / "throttle.yml"
    path.write_text(yaml.safe_dump(broken), encoding="utf-8")

    client._reset_state(config_path=path, cache_dir=tmp_path / "raw")
    try:
        with pytest.raises(client.HttpError, match="@"):
            client._load_config()
    finally:
        client._reset_state()


def test_a_host_with_a_delay_and_no_cap_is_refused(tmp_path: Path, config: dict) -> None:
    broken = dict(config)
    broken["min_interval_seconds"] = dict(config["min_interval_seconds"], **{"new.example": 10.0})
    path = tmp_path / "throttle.yml"
    path.write_text(yaml.safe_dump(broken), encoding="utf-8")

    client._reset_state(config_path=path, cache_dir=tmp_path / "raw")
    try:
        with pytest.raises(client.HttpError, match=r"new\.example"):
            client._load_config()
    finally:
        client._reset_state()


# ---------------------------------------------------------------------------
# The published number is the enforced number
# ---------------------------------------------------------------------------


def test_docs_legal_publishes_the_same_statsapi_policy(config: dict) -> None:
    legal = REPO_ROOT / "docs" / "legal.md"
    if not legal.is_file():
        pytest.skip("docs/legal.md is not written yet; it is not W1.7's file")
    text = legal.read_text(encoding="utf-8")
    assert "4 s" in text or "4 seconds" in text
    assert "3,000" in text or "3000" in text
    assert config["user_agent"] in text
