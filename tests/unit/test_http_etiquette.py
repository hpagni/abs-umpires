"""W1.7: the request etiquette of SOP section 2.3, asserted end to end.

Every test here monkeypatches the transport and the clock. Nothing in this
file sends a request, and phase 01 is forbidden to read a single 2026 datum, so
the bodies are invented bytes and no real endpoint is named except in a URL
string that never leaves the process.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml

from absump import http as client

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "throttle.yml"

STATSAPI = "statsapi.mlb.com"
SAVANT = "baseballsavant.mlb.com"


class FakeClock:
    """A monotonic clock that only moves when the client sleeps.

    This is what makes a 10 s throttle testable: the gaps the client produces
    are real arithmetic on a real clock, they just cost no wall time.
    """

    def __init__(self) -> None:
        self.now = 1_000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0.0, "the client asked for a negative sleep"
        self.sleeps.append(seconds)
        self.now += seconds


class Harness:
    def __init__(self, clock: FakeClock, cache_dir: Path) -> None:
        self.clock = clock
        self.cache_dir = cache_dir
        self.calls: list[httpx.Request] = []
        self.call_times: list[float] = []
        self.responses: list[httpx.Response] = []
        self.default_response = httpx.Response(200, content=b"{}")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        self.call_times.append(self.clock.monotonic())
        if self.responses:
            return self.responses.pop(0)
        return httpx.Response(
            self.default_response.status_code, content=self.default_response.content
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    monkeypatch.delenv("ABSUMP_DRY_RUN", raising=False)
    clock = FakeClock()
    built = Harness(clock, tmp_path / "raw")
    client._reset_state(cache_dir=built.cache_dir, transport=built.transport())
    monkeypatch.setattr(client, "_monotonic", clock.monotonic)
    monkeypatch.setattr(client, "_sleep", clock.sleep)
    yield built
    client._reset_state()


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def url_for(host: str, n: int) -> str:
    return f"https://{host}/api/v1/probe?n={n}"


# ---------------------------------------------------------------------------
# Three requests to one host, and the gap between them
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", [STATSAPI, SAVANT])
def test_three_requests_to_one_host_hold_the_configured_gap(harness: Harness, host: str) -> None:
    minimum = client._min_interval(host)
    for n in range(3):
        client.get(url_for(host, n))

    assert len(harness.call_times) == 3
    gaps = [later - earlier for earlier, later in itertools.pairwise(harness.call_times)]
    assert len(gaps) == 2
    for gap in gaps:
        assert gap >= minimum, f"{host}: {gap} s gap is under the configured {minimum} s"


def test_the_first_request_to_a_host_is_not_delayed(harness: Harness) -> None:
    client.get(url_for(STATSAPI, 0))
    assert harness.clock.sleeps == []


def test_the_delay_and_cap_the_client_enforces_are_the_section_2_3_table() -> None:
    # RP-09 proves the config against the table row by row in
    # tests/unit/test_throttle_budget.py. This asserts the client actually
    # reads those rows, which is the half a config test cannot see.
    assert client._min_interval(SAVANT) == 10.0
    assert client._daily_cap(SAVANT) == 800
    assert client._min_interval(STATSAPI) == 4.0
    assert client._daily_cap(STATSAPI) == 3000
    assert client._min_interval("www.retrosheet.org") == 10.0
    assert client._daily_cap("www.retrosheet.org") == 500
    assert client._min_interval("a-host-that-is-in-no-table.example") == 10.0
    assert client._daily_cap("a-host-that-is-in-no-table.example") == 500


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------


def test_outgoing_user_agent_equals_the_config_string_exactly(
    harness: Harness, config: dict
) -> None:
    client.get(url_for(STATSAPI, 0))
    sent = harness.calls[0].headers

    assert sent["user-agent"] == config["user_agent"]
    assert sent.get_list("user-agent") == [config["user_agent"]]
    assert "python-httpx" not in sent["user-agent"]
    assert "github.com/hpagni/abs-umpires" in sent["user-agent"]


def test_no_header_name_or_value_contains_an_at_sign(harness: Harness) -> None:
    # Section 2.3: no email address is ever sent to any host. "@" is the one
    # character an address cannot be written without.
    client.get(url_for(STATSAPI, 0))
    client.get(url_for(SAVANT, 0))
    assert len(harness.calls) == 2
    for request in harness.calls:
        for name, value in request.headers.items():
            assert "@" not in name, f"{name}: header name carries an '@'"
            assert "@" not in value, f"{name}: {value!r} carries an '@'"


def test_accept_headers_follow_section_2_3(harness: Harness) -> None:
    client.get(url_for(STATSAPI, 0))
    client.get(url_for(SAVANT, 0))
    statsapi_headers, savant_headers = (call.headers for call in harness.calls)

    # statsapi returns 406 without it.
    assert statsapi_headers["accept"] == "application/json"
    assert savant_headers["accept"] == "*/*"
    for headers in (statsapi_headers, savant_headers):
        assert headers["accept-encoding"] == "gzip, deflate"


# ---------------------------------------------------------------------------
# 403 is fatal, on the first attempt
# ---------------------------------------------------------------------------


def test_403_raises_fatal_on_the_first_attempt_with_zero_retries(harness: Harness) -> None:
    harness.responses = [httpx.Response(403, content=b"forbidden")]

    with pytest.raises(client.Fatal) as raised:
        client.get(url_for(SAVANT, 0))

    assert len(harness.calls) == 1, "403 was retried; section 2.3 says it is fatal"
    assert harness.clock.sleeps == [], "403 went through the backoff ladder"
    assert "403" in str(raised.value)
    assert not (harness.cache_dir / "_manifest.csv").exists()


@pytest.mark.parametrize("status", [400, 404, 410, 451])
def test_a_4xx_is_never_retried(harness: Harness, status: int) -> None:
    harness.responses = [httpx.Response(status, content=b"no")]

    with pytest.raises(client.Fatal):
        client.get(url_for(STATSAPI, 0))

    assert len(harness.calls) == 1


def test_a_3xx_is_fatal_because_the_url_was_not_canonical(harness: Harness) -> None:
    harness.responses = [httpx.Response(301, headers={"location": "https://elsewhere.example/"})]

    with pytest.raises(client.Fatal) as raised:
        client.get(url_for(SAVANT, 0))

    assert len(harness.calls) == 1
    assert "elsewhere.example" in str(raised.value)


# ---------------------------------------------------------------------------
# 5xx and timeouts retry, bounded, and still throttled
# ---------------------------------------------------------------------------


def test_the_retry_status_set_is_the_one_section_2_3_names() -> None:
    assert set(client._RETRY_STATUS) == {429, 500, 502, 503, 504}
    assert set(client._FATAL_STATUS) == {403}


def test_a_5xx_is_retried_and_the_retries_are_still_throttled(harness: Harness) -> None:
    harness.responses = [
        httpx.Response(503, content=b""),
        httpx.Response(500, content=b""),
        httpx.Response(200, content=b"{}"),
    ]

    response = client.get(url_for(STATSAPI, 0))

    assert response.status_code == 200
    assert response.attempt == 3
    assert len(harness.calls) == 3
    gaps = [later - earlier for earlier, later in itertools.pairwise(harness.call_times)]
    for gap in gaps:
        assert gap >= client._min_interval(STATSAPI)


def test_retries_stop_at_max_attempts(harness: Harness, config: dict) -> None:
    attempts = int(config["max_attempts"])
    harness.responses = [httpx.Response(503, content=b"") for _ in range(attempts + 2)]

    with pytest.raises(client.Retryable):
        client.get(url_for(STATSAPI, 0))

    assert len(harness.calls) == attempts


def test_a_timeout_is_retried(harness: Harness) -> None:
    state = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        harness.calls.append(request)
        harness.call_times.append(harness.clock.monotonic())
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"{}")

    client._reset_state(cache_dir=harness.cache_dir, transport=httpx.MockTransport(flaky))
    response = client.get(url_for(STATSAPI, 0))

    assert response.attempt == 2
    assert len(harness.calls) == 2


# ---------------------------------------------------------------------------
# The cache: a re-run costs zero requests
# ---------------------------------------------------------------------------


def test_a_second_get_for_a_manifested_url_performs_zero_network_calls(harness: Harness) -> None:
    url = url_for(STATSAPI, 7)
    harness.default_response = httpx.Response(200, content=b'{"ok":true}')

    first = client.get(url)
    assert len(harness.calls) == 1
    assert first.from_cache is False

    second = client.get(url)
    assert len(harness.calls) == 1, "the second get() went to the network"
    assert second.from_cache is True
    assert second.content == first.content
    assert second.sha256 == first.sha256
    assert second.attempt == 0

    # And in a fresh process, which is what the resume logic actually faces:
    # the manifest row plus the file on disk are the whole memory.
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"a manifested URL was re-fetched: {request.url}")

    client._reset_state(cache_dir=harness.cache_dir, transport=httpx.MockTransport(explode))
    third = client.get(url)
    assert third.from_cache is True
    assert third.content == first.content


def test_the_manifest_is_the_audit_trail_section_2_3_specifies(harness: Harness) -> None:
    harness.default_response = httpx.Response(200, content=b'{"ok":true}')
    response = client.get(url_for(STATSAPI, 11))

    manifest = harness.cache_dir / "_manifest.csv"
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert rows[0] == [
        "fetched_at_utc",
        "host",
        "url",
        "http_status",
        "wire_bytes",
        "disk_bytes",
        "sha256",
        "attempt",
        "elapsed_s",
        "dest_path",
    ]
    assert len(rows) == 2
    row = dict(zip(rows[0], rows[1], strict=True))
    assert row["host"] == STATSAPI
    assert row["url"] == url_for(STATSAPI, 11)
    assert row["http_status"] == "200"
    assert row["sha256"] == response.sha256
    assert row["attempt"] == "1"
    assert row["fetched_at_utc"].endswith("Z")
    assert Path(row["dest_path"]).exists()


def test_raw_bytes_are_zstd_on_disk_and_never_rewritten(harness: Harness) -> None:
    harness.default_response = httpx.Response(200, content=b"x" * 4096)
    response = client.get(url_for(SAVANT, 3))

    raw = response.dest_path.read_bytes()
    assert raw[:4] == b"\x28\xb5\x2f\xfd", "raw cache is not a zstd frame"
    assert client._ZSTD_LEVEL == 10
    before = response.dest_path.stat().st_mtime_ns

    client.get(url_for(SAVANT, 3))
    assert response.dest_path.stat().st_mtime_ns == before


# ---------------------------------------------------------------------------
# The two contract facts encoded in the client
# ---------------------------------------------------------------------------


def test_the_savant_leaderboard_csv_export_is_refused(harness: Harness) -> None:
    url = (
        "https://baseballsavant.mlb.com/leaderboard/abs-challenges"
        "?level=mlb&challengeType=batter&season%5B%5D=2026&csv=true"
    )
    with pytest.raises(client.Fatal) as raised:
        client.get(url)

    assert harness.calls == []
    assert "500" in str(raised.value)


def test_the_savant_leaderboard_year_form_is_refused(harness: Harness) -> None:
    url = "https://baseballsavant.mlb.com/leaderboard/abs-challenges?level=mlb&year=2026"
    with pytest.raises(client.Fatal) as raised:
        client.get(url)

    assert harness.calls == []
    assert "season[]=" in str(raised.value)


def test_the_canonical_leaderboard_url_and_the_drawer_year_form_both_pass(
    harness: Harness,
) -> None:
    canonical = client.SAVANT_ABS_LEADERBOARD_URL.format(
        level="mlb", challenge_type="batter", season=2026
    )
    assert "season%5B%5D=" in canonical
    client.get(canonical)

    # The drawer service is a different endpoint and works ONLY with year=
    # (SOP W4.2). The contract check must not reach it.
    client.get(
        "https://baseballsavant.mlb.com/leaderboard/services/abs/113"
        "?year=2026&challengeType=team-summary&gameType=regular&level=mlb"
    )
    assert len(harness.calls) == 2


def test_savant_bodies_are_decoded_utf_8_sig(harness: Harness) -> None:
    assert client.SAVANT_CSV_ENCODING == "utf-8-sig"
    harness.default_response = httpx.Response(200, content="pitch_id\n1\n".encode("utf-8-sig"))

    response = client.get(url_for(SAVANT, 42))
    assert response.encoding == "utf-8-sig"
    assert response.text.startswith("pitch_id")
    assert "﻿" not in response.text

    statsapi_response = client.get(url_for(STATSAPI, 42))
    assert statsapi_response.encoding == "utf-8"


# ---------------------------------------------------------------------------
# --dry-run sends nothing
# ---------------------------------------------------------------------------


def test_dry_run_prints_the_plan_and_sends_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("ABSUMP_DRY_RUN", "1")
    url = url_for(SAVANT, 5)

    response = client.get(url)
    printed = capsys.readouterr().out

    assert harness.calls == []
    assert response.dry_run is True
    assert url in printed
    assert str(client._dest_path(url)) in printed
    assert "B on the wire" in printed
    assert "0 requests sent" in printed


def test_the_dry_run_cli_sends_nothing(harness: Harness, capsys: pytest.CaptureFixture) -> None:
    exit_code = client._main(["--dry-run", url_for(STATSAPI, 1), url_for(SAVANT, 1)])
    printed = capsys.readouterr().out

    assert exit_code == 0
    assert harness.calls == []
    assert printed.count("est ") >= 2
    assert client._main([]) == 2


def test_the_estimated_wall_clock_is_the_configured_interval(harness: Harness) -> None:
    plan = client._plan(url_for(SAVANT, 9))
    assert plan["estimated_wall_clock_s"] == client._min_interval(SAVANT)
    assert plan["estimated_wire_bytes"] > 0
    assert plan["cached"] is False


# ---------------------------------------------------------------------------
# Shape of the public surface
# ---------------------------------------------------------------------------


def test_the_module_exposes_exactly_one_public_function() -> None:
    public_functions = [
        name
        for name, value in vars(client).items()
        if not name.startswith("_")
        and callable(value)
        and not isinstance(value, type)
        and getattr(value, "__module__", "") == client.__name__
    ]
    assert public_functions == ["get"]


def test_the_budget_ceiling_is_enforced_per_host(harness: Harness) -> None:
    host_cap = client._daily_cap(STATSAPI)
    state = {"utc_date": client._utc_day(), "used": {STATSAPI: host_cap}}
    client._write_budget(state)

    with pytest.raises(client.BudgetExceeded):
        client.get(url_for(STATSAPI, 99))

    assert harness.calls == []

    # host_budget=False is for a single probe, not a bulk pull. It skips the
    # cap and never skips the delay.
    response = client.get(url_for(STATSAPI, 99), host_budget=False)
    assert response.status_code == 200
    assert len(harness.calls) == 1


def test_wall_clock_helpers_agree_with_math(harness: Harness) -> None:
    # 920 Statcast days at the Savant interval is 2.6 h and needs two nights
    # at the 800/day cap (SOP section 10.1, derived from section 2.3).
    interval = client._min_interval(SAVANT)
    assert math.isclose(920 * interval / 3600.0, 2.6, abs_tol=0.05)
    assert math.ceil(920 / client._daily_cap(SAVANT)) == 2


# ---------------------------------------------------------------------------
# ops/lint_http.sh: there is no second call site
# ---------------------------------------------------------------------------

LINT_HTTP = REPO_ROOT / "ops" / "lint_http.sh"


def run_lint(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(LINT_HTTP), *args], capture_output=True, text=True, check=False, timeout=120
    )


def test_lint_http_passes_on_this_repository() -> None:
    result = run_lint("-q")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "LINT HTTP OK" in result.stdout


def build_tree(root: Path) -> None:
    """A minimal tree with both allowed call sites present and legitimate."""
    (root / "src" / "absump").mkdir(parents=True)
    (root / "R" / "lib").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "notebooks").mkdir()
    (root / "src" / "absump" / "http.py").write_text(
        "import httpx\n\n\ndef get(url):\n"
        "    with httpx.Client() as c:\n        return c.get(url)\n"
    )
    (root / "R" / "lib" / "http.R").write_text("resp <- httr2::request(url)\n")


def test_lint_http_exempts_the_two_allowed_call_sites(tmp_path: Path) -> None:
    build_tree(tmp_path)
    result = run_lint("-q", str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("relative", "line"),
    [
        ("src/absump/ch3/dp_fast.py", "import urllib.request\n"),
        ("src/absump/ingest/pull.py", "resp = requests.get(url)\n"),
        ("tools/scrape.py", "client = httpx.Client()\n"),
        ("notebooks/scratch.py", "body = httpx.get(url).text\n"),
        ("R/ch1/fetch.R", 'resp <- httr2::request("https://example.com")\n'),
        ("R/lib/other.R", "system2('curl https://example.com')\n"),
    ],
)
def test_lint_http_fires_on_a_planted_call_site(tmp_path: Path, relative: str, line: str) -> None:
    build_tree(tmp_path)
    planted = tmp_path / relative
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(line)

    result = run_lint("-q", str(tmp_path))
    assert result.returncode == 1, f"{relative} passed the linter"
    assert relative in result.stderr


# ---------------------------------------------------------------------------
# One policy, two languages: R/lib/http.R agrees with absump.http
# ---------------------------------------------------------------------------

R_PARITY = """
source(Sys.getenv("ABSUMP_HTTP_R"))
.absump_reset_state(cache_dir = Sys.getenv("ABSUMP_SHARED_CACHE"))
url <- Sys.getenv("ABSUMP_PARITY_URL")
dest <- .absump_dest_path(url)
size <- .absump_write_raw(dest, charToRaw(Sys.getenv("ABSUMP_PARITY_BODY")))
cat(jsonlite::toJSON(list(
  user_agent = .absump_config()$user_agent,
  savant_delay = .absump_min_interval("baseballsavant.mlb.com"),
  statsapi_delay = .absump_min_interval("statsapi.mlb.com"),
  savant_cap = .absump_daily_cap("baseballsavant.mlb.com"),
  default_cap = .absump_daily_cap("a-host-in-no-table.example"),
  dest_path = dest,
  manifest_columns = .ABSUMP_MANIFEST_COLUMNS,
  zstd_level = .ABSUMP_ZSTD_LEVEL,
  disk_bytes = size
), auto_unbox = TRUE))
"""


def test_the_r_client_is_the_same_policy_and_shares_the_raw_cache(
    tmp_path: Path, config: dict
) -> None:
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not on PATH")

    shared = tmp_path / "raw"
    url = "https://baseballsavant.mlb.com/statcast_search/csv?all=true&day=1"
    body = b"parity bytes written by the R half of the one client"
    environment = dict(
        os.environ,
        ABSUMP_HTTP_R=str(REPO_ROOT / "R" / "lib" / "http.R"),
        ABSUMP_SHARED_CACHE=str(shared),
        ABSUMP_PARITY_URL=url,
        ABSUMP_PARITY_BODY=body.decode(),
        ABSUMP_REPO_ROOT=str(REPO_ROOT),
    )
    result = subprocess.run(
        ["Rscript", "-e", R_PARITY],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
        env=environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    reported = json.loads(result.stdout.strip().splitlines()[-1])

    assert reported["user_agent"] == config["user_agent"]
    assert reported["savant_delay"] == client._min_interval(SAVANT)
    assert reported["statsapi_delay"] == client._min_interval(STATSAPI)
    assert reported["savant_cap"] == client._daily_cap(SAVANT)
    assert reported["default_cap"] == client._daily_cap("a-host-in-no-table.example")
    assert reported["manifest_columns"] == list(client._MANIFEST_COLUMNS)
    assert reported["zstd_level"] == client._ZSTD_LEVEL

    # The two halves compute the same cache path for the same URL, and the
    # Python half can read the frame the R half wrote. A file fetched by
    # either is a cache hit for the other.
    client._reset_state(cache_dir=shared)
    try:
        assert reported["dest_path"] == str(client._dest_path(url))
        assert client._read_raw(Path(reported["dest_path"])) == body
    finally:
        client._reset_state()


@pytest.mark.parametrize("relative", ["R/lib/http.R", "src/absump/http.py", "config/throttle.yml"])
def test_no_call_site_names_an_email_address(relative: str) -> None:
    # Section 2.3: no email address is ever sent to any host. Both clients
    # check the config for an "@" at load time, so the literal character is
    # allowed to appear; an address is not.
    source = (REPO_ROOT / relative).read_text(encoding="utf-8")
    found = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", source)
    assert found == [], f"{relative} names {found}"


def test_both_clients_read_the_one_config() -> None:
    for relative in ("R/lib/http.R", "src/absump/http.py"):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "throttle.yml" in source
