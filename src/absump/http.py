"""absump.http -- the one HTTP call site for the Python half of abs-umpires.

SOP section 2.3, step W1.7. Rule 0.5.2 forbids any other Python file in this
repository from issuing a request; ``ops/lint_http.sh`` fails CI on a second
call site. The R half has exactly one counterpart, ``R/lib/http.R``.

The module is the legal posture in executable form. Everything it enforces is
read from ``config/throttle.yml`` and nothing else:

* one User-Agent on every request, from every language, with no email address
  and no other identifying header;
* a per-host minimum interval between requests, on a process-wide monotonic
  clock;
* a per-host daily request budget, counted in UTC days and persisted across
  processes, which raises :class:`BudgetExceeded` at zero;
* bounded retry with ``tenacity`` on 5xx and timeouts, no retry on a 4xx, and
  403 fatal on the first attempt;
* an immutable raw cache, so a re-run of a completed pull costs zero requests;
* an append-only manifest at ``data/raw/_manifest.csv``, the audit trail for
  the legal posture and the input to the resume logic.

Public API: the single function :func:`get`, the three exception classes
:class:`Fatal`, :class:`Retryable` and :class:`BudgetExceeded`, the
:class:`Response` it returns, and the two Savant contract constants. Everything
else is private and may change.

Command line::

    python -m absump.http --dry-run URL [URL ...]

prints the full request plan -- URL, destination, estimated bytes, estimated
wall clock -- and sends nothing.

Importing this module issues no request, reads no network state and creates no
directory. It is safe to import inside phase 01, which is forbidden to touch a
single 2026 datum.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import tenacity
import yaml
import zstandard

__all__ = [
    "SAVANT_ABS_LEADERBOARD_URL",
    "SAVANT_CSV_ENCODING",
    "BudgetExceeded",
    "Fatal",
    "HttpError",
    "Response",
    "Retryable",
    "get",
]

# --------------------------------------------------------------------------
# Contract facts, encoded here so nobody re-learns them (SOP section 2.3).
# --------------------------------------------------------------------------

#: The canonical Savant ABS leaderboard URL. The ``season[]=`` form is the one
#: the page's own serverParams declare; the ``year=`` form 301-redirects, and
#: the ``csv=true`` export returns HTTP 500 with an 80,549-byte text/html body
#: even with the exact canonical parameters (SOP W2.11). Both are refused here
#: rather than re-discovered.
SAVANT_ABS_LEADERBOARD_URL = (
    "https://baseballsavant.mlb.com/leaderboard/abs-challenges"
    "?level={level}&challengeType={challenge_type}&season%5B%5D={season}"
)

#: Every Savant CSV carries a UTF-8 BOM, so every Savant CSV is read with this
#: encoding and never with plain "utf-8" (SOP section 2.3; UT-14).
SAVANT_CSV_ENCODING = "utf-8-sig"

_SAVANT_HOST = "baseballsavant.mlb.com"
_STATSAPI_HOST = "statsapi.mlb.com"

# The leaderboard page. The drawer service at /leaderboard/services/abs/ is a
# different endpoint that works ONLY with the year= / gameType=regular form
# (SOP W4.2), so the contract check below is scoped to the page and must never
# be widened to the whole host.
_SAVANT_LEADERBOARD_PATH = "/leaderboard/abs-challenges"

# Section 2.3: "exponential 2/4/8/16/32 on 429, 500, 502, 503, 504". 429 is a
# 4xx and is nevertheless retried; that one exception is stated in the same
# sentence as the no-retry-on-4xx rule and is not a licence to retry any other.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

# Section 2.3: "a 403 is FATAL". No retry, no backoff, first attempt.
_FATAL_STATUS = frozenset({403})

# Section 2.3, storage: raw bytes are immutable and compressed with zstandard
# level 10 (about 10x on Stats API JSON, 6-8x on Statcast CSV).
_ZSTD_LEVEL = 10

# Section 2.3, measured: statsapi feed 822925 is 689,790 B uncompressed and
# 109,623 B with Accept-Encoding honoured. The dry-run planner uses the
# measured compressed figure only when the manifest holds no row for the host,
# in which case the manifest's own observed mean is used instead.
_MEASURED_FEED_WIRE_BYTES = 109_623

_MANIFEST_NAME = "_manifest.csv"
_BUDGET_NAME = "_budget.json"

#: Manifest columns, in order, exactly as SOP section 2.3 states them.
_MANIFEST_COLUMNS = (
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
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "throttle.yml"


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------


class HttpError(RuntimeError):
    """Base class for every error this module raises."""


class Fatal(HttpError):
    """Unrecoverable. Raised on 403 and on every other non-retryable 4xx.

    A 403 means the host has told us to stop. The pull stops; it does not back
    off and try again with the same User-Agent.
    """


class Retryable(HttpError):
    """A 5xx, a 429 or a timeout that survived ``max_attempts`` tries."""


class BudgetExceeded(HttpError):
    """The host's daily request budget from ``config/throttle.yml`` is spent."""


class ContractViolation(Fatal):
    """A URL that section 2.3's recorded endpoint contract says cannot work."""


# --------------------------------------------------------------------------
# Test seams. Bound at module level so a test can replace them without a
# network stack and without waiting out a 10 s throttle in real time. Nothing
# in production code rebinds them.
# --------------------------------------------------------------------------

_monotonic = time.monotonic
_sleep = time.sleep

#: An ``httpx.BaseTransport`` installed by a test. ``None`` means the real
#: network. Every test in this repository sets this; none of them sends.
_transport: httpx.BaseTransport | None = None

_LOCK = threading.RLock()
_CONFIG: dict[str, Any] | None = None
_CONFIG_PATH: Path = _DEFAULT_CONFIG_PATH
_CACHE_DIR: Path | None = None
_LAST_REQUEST_AT: dict[str, float] = {}
_MANIFEST_INDEX: dict[str, dict[str, str]] = {}
_MANIFEST_STAMP: tuple[int, int] | None = None


def _reset_state(
    *,
    config_path: Path | None = None,
    cache_dir: Path | None = None,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Drop every cached piece of module state. Tests only.

    Production code never calls this: the throttle clock and the daily budget
    are deliberately process-wide, and forgetting them would let a caller issue
    two requests to one host inside the configured interval.
    """
    global _CONFIG, _CONFIG_PATH, _CACHE_DIR, _MANIFEST_STAMP, _transport
    with _LOCK:
        _CONFIG = None
        _CONFIG_PATH = config_path if config_path is not None else _DEFAULT_CONFIG_PATH
        _CACHE_DIR = Path(cache_dir) if cache_dir is not None else None
        _LAST_REQUEST_AT.clear()
        _MANIFEST_INDEX.clear()
        _MANIFEST_STAMP = None
        _transport = transport


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

_REQUIRED_KEYS = (
    "user_agent",
    "timeout_seconds",
    "max_attempts",
    "backoff_base_seconds",
    "min_interval_seconds",
    "daily_request_budget",
    "cache_dir",
)


def _load_config() -> dict[str, Any]:
    """Read ``config/throttle.yml`` once per process and validate its shape."""
    global _CONFIG
    with _LOCK:
        if _CONFIG is not None:
            return _CONFIG
        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise HttpError(f"{_CONFIG_PATH} is not a YAML mapping")
        missing = [k for k in _REQUIRED_KEYS if k not in raw]
        if missing:
            raise HttpError(f"{_CONFIG_PATH} is missing {', '.join(missing)}")
        intervals = raw["min_interval_seconds"]
        budgets = raw["daily_request_budget"]
        for table, name in ((intervals, "min_interval_seconds"), (budgets, "daily_request_budget")):
            if not isinstance(table, dict) or "default" not in table:
                raise HttpError(f"{_CONFIG_PATH}: {name} needs a mapping with a 'default' row")
        unbudgeted = sorted(set(intervals) - set(budgets))
        if unbudgeted:
            raise HttpError(f"{_CONFIG_PATH}: no daily cap for {', '.join(unbudgeted)}")
        if "@" in str(raw["user_agent"]):
            # Section 2.3: no email address is ever sent to any host.
            raise HttpError(f"{_CONFIG_PATH}: user_agent contains '@'")
        _CONFIG = raw
        return _CONFIG


def _min_interval(host: str) -> float:
    table = _load_config()["min_interval_seconds"]
    return float(table.get(host, table["default"]))


def _daily_cap(host: str) -> int:
    table = _load_config()["daily_request_budget"]
    return int(table.get(host, table["default"]))


def _cache_dir() -> Path:
    """The raw cache root, from config, resolved against the repository root."""
    with _LOCK:
        if _CACHE_DIR is not None:
            return _CACHE_DIR
        configured = Path(str(_load_config()["cache_dir"]))
        return configured if configured.is_absolute() else _REPO_ROOT / configured


def _host_of(url: str) -> str:
    host = httpx.URL(url).host
    if not host:
        raise HttpError(f"no host in URL: {url}")
    return host


# --------------------------------------------------------------------------
# Response
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    """What :func:`get` returns, whether the bytes came off the wire or disk."""

    url: str
    host: str
    status_code: int
    content: bytes
    dest_path: Path
    sha256: str
    wire_bytes: int
    disk_bytes: int
    attempt: int
    elapsed_s: float
    from_cache: bool
    dry_run: bool = False
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def encoding(self) -> str:
        """``utf-8-sig`` for Savant, which BOMs every CSV it serves."""
        return SAVANT_CSV_ENCODING if self.host == _SAVANT_HOST else "utf-8"

    @property
    def text(self) -> str:
        """The body decoded with :attr:`encoding`, so the BOM never leaks."""
        return self.content.decode(self.encoding)

    def json(self) -> Any:
        return json.loads(self.text)


# --------------------------------------------------------------------------
# Throttle: a process-wide monotonic clock, one gap per host
# --------------------------------------------------------------------------


def _throttle(host: str) -> None:
    """Sleep until ``min_interval_seconds[host]`` has passed since the last
    request to that host, then stamp the clock.

    The stamp is taken before the request is issued, so the measured gap
    between two consecutive requests is at least the configured interval even
    when the first one is slow. The lock is held across the sleep on purpose:
    two threads pulling the same host must queue behind one another, not sleep
    concurrently and then fire together.
    """
    interval = _min_interval(host)
    with _LOCK:
        last = _LAST_REQUEST_AT.get(host)
        now = _monotonic()
        if last is not None:
            wait = interval - (now - last)
            if wait > 0:
                _sleep(wait)
                now = _monotonic()
        _LAST_REQUEST_AT[host] = now


# --------------------------------------------------------------------------
# Daily budget: per host, per UTC day, persisted so a restart cannot reset it
# --------------------------------------------------------------------------


def _utc_day() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _budget_path() -> Path:
    return _cache_dir() / _BUDGET_NAME


def _read_budget() -> dict[str, Any]:
    path = _budget_path()
    today = _utc_day()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"utc_date": today, "used": {}}
    if not isinstance(state, dict) or state.get("utc_date") != today:
        return {"utc_date": today, "used": {}}
    used = state.get("used")
    return {"utc_date": today, "used": used if isinstance(used, dict) else {}}


def _write_budget(state: dict[str, Any]) -> None:
    path = _budget_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _budget_take(host: str) -> int:
    """Spend one request against ``host``'s daily cap. Returns what is left."""
    cap = _daily_cap(host)
    with _LOCK:
        state = _read_budget()
        used = int(state["used"].get(host, 0))
        if used >= cap:
            raise BudgetExceeded(
                f"{host}: {used}/{cap} requests used on {state['utc_date']} UTC; "
                "config/throttle.yml is the only place this cap is set"
            )
        state["used"][host] = used + 1
        _write_budget(state)
        return cap - (used + 1)


# --------------------------------------------------------------------------
# Raw cache and manifest
# --------------------------------------------------------------------------


def _url_digest(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _dest_path(url: str) -> Path:
    """Where the compressed body for ``url`` lives.

    ``<cache_dir>/<host>/<first two hex of sha256(url)>/<sha256(url)>.zst``.
    The URL digest, not the URL path, so a query string can never collide with
    a directory name and no host can write outside its own subtree. The
    manifest carries the readable URL beside the path.
    """
    digest = _url_digest(url)
    return _cache_dir() / _host_of(url) / digest[:2] / f"{digest}.zst"


def _manifest_path() -> Path:
    return _cache_dir() / _MANIFEST_NAME


def _manifest_index() -> dict[str, dict[str, str]]:
    """``url -> manifest row`` for every completed request, reloaded on change.

    This is the resume logic: a URL in here whose file is still on disk is a
    request this project has already paid for and must never pay for twice.
    """
    global _MANIFEST_STAMP
    path = _manifest_path()
    with _LOCK:
        try:
            stat = path.stat()
        except OSError:
            _MANIFEST_INDEX.clear()
            _MANIFEST_STAMP = None
            return _MANIFEST_INDEX
        stamp = (stat.st_size, stat.st_mtime_ns)
        if stamp == _MANIFEST_STAMP:
            return _MANIFEST_INDEX
        _MANIFEST_INDEX.clear()
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                url = row.get("url")
                if url:
                    _MANIFEST_INDEX[url] = row
        _MANIFEST_STAMP = stamp
        return _MANIFEST_INDEX


def _manifest_append(row: dict[str, Any]) -> None:
    """Append one row. The client is the only writer; nothing ever edits."""
    global _MANIFEST_STAMP
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(_MANIFEST_COLUMNS))
            if new:
                writer.writeheader()
            writer.writerow({column: row[column] for column in _MANIFEST_COLUMNS})
        _MANIFEST_STAMP = None


def _write_raw(dest: Path, body: bytes) -> int:
    """Compress and write once. Raw bytes are immutable: an existing file is
    never rewritten, only superseded by deleting it and fetching again, which
    appends a second manifest row.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest.stat().st_size
    compressor = zstandard.ZstdCompressor(level=_ZSTD_LEVEL)
    tmp = dest.with_suffix(".zst.tmp")
    tmp.write_bytes(compressor.compress(body))
    os.replace(tmp, dest)
    return dest.stat().st_size


def _read_raw(dest: Path) -> bytes:
    # Streamed, not ZstdDecompressor.decompress(): a frame written by the R
    # half through arrow's CompressedOutputStream carries no content size in
    # its header, and the one-shot call refuses such a frame. Either half must
    # be able to read what the other wrote.
    decompressor = zstandard.ZstdDecompressor()
    with dest.open("rb") as handle, decompressor.stream_reader(handle) as reader:
        return reader.read()


# --------------------------------------------------------------------------
# Endpoint contract
# --------------------------------------------------------------------------


def _check_contract(url: str, host: str) -> None:
    """Refuse a URL that section 2.3's recorded contract says cannot work."""
    if host != _SAVANT_HOST:
        return
    parsed = httpx.URL(url)
    if not parsed.path.startswith(_SAVANT_LEADERBOARD_PATH):
        return
    query = parsed.params
    if "csv" in query and str(query["csv"]).lower() == "true":
        raise ContractViolation(
            "the Savant ABS leaderboard csv=true export returns HTTP 500 with a "
            "text/html body even with the page's own serverParams; parse the "
            "page's absData block instead (SOP W2.11)"
        )
    if "year" in query:
        raise ContractViolation(
            "the Savant ABS leaderboard year= form 301-redirects; use the "
            f"canonical season[]= form: {SAVANT_ABS_LEADERBOARD_URL}"
        )


# --------------------------------------------------------------------------
# The request itself
# --------------------------------------------------------------------------


def _headers(host: str) -> dict[str, str]:
    """The complete outgoing header set this project adds.

    One User-Agent, from config, on every request from every language. No
    email address, and no other identifying header: section 2.3 is explicit
    that nothing which could identify a person leaves this machine.
    """
    headers = {
        "User-Agent": str(_load_config()["user_agent"]),
        # 6.3x less bandwidth off MLB's servers and about 70x less wall clock
        # on the measured feed; Savant's CSV endpoint does not compress, so
        # its cost is fixed (section 2.3).
        "Accept-Encoding": "gzip, deflate",
    }
    # statsapi returns 406 without it (section 2.3).
    headers["Accept"] = "application/json" if host == _STATSAPI_HOST else "*/*"
    return headers


def _client(host: str) -> httpx.Client:
    config = _load_config()
    return httpx.Client(
        transport=_transport,
        timeout=httpx.Timeout(float(config["timeout_seconds"])),
        headers=_headers(host),
        follow_redirects=False,
    )


class _RetrySignal(Retryable):
    """Internal: a 429, a 5xx or a timeout that tenacity should try again."""


def _is_retryable_status(status: int) -> bool:
    # Section 2.3 names 429, 500, 502, 503, 504. Every other 5xx is the same
    # class of failure and is retried on the same ladder; no other 4xx is.
    return status in _RETRY_STATUS or 500 <= status < 600


def _attempt(
    client: httpx.Client,
    url: str,
    host: str,
    *,
    host_budget: bool,
    counter: dict[str, int],
) -> tuple[httpx.Response, float]:
    counter["attempt"] += 1
    _throttle(host)
    if host_budget:
        _budget_take(host)
    started = _monotonic()
    try:
        response = client.get(url)
    except httpx.TimeoutException as exc:
        raise _RetrySignal(f"timeout from {host} on attempt {counter['attempt']}: {url}") from exc
    elapsed = _monotonic() - started
    status = response.status_code
    if status in _FATAL_STATUS:
        raise Fatal(
            f"{status} from {host} on attempt {counter['attempt']}: the host has "
            f"refused this client. Stop the pull. URL: {url}"
        )
    if _is_retryable_status(status):
        raise _RetrySignal(f"{status} from {host} on attempt {counter['attempt']}: {url}")
    if 400 <= status < 500:
        raise Fatal(f"{status} from {host}: a 4xx is never retried. URL: {url}")
    if 300 <= status < 400:
        raise Fatal(
            f"{status} from {host} to {response.headers.get('location', '?')}: this URL "
            f"is not canonical. Fetch the canonical form. URL: {url}"
        )
    return response, elapsed


def _fetch(url: str, host: str, *, host_budget: bool) -> tuple[httpx.Response, float, int]:
    config = _load_config()
    counter = {"attempt": 0}
    retrying = tenacity.Retrying(
        stop=tenacity.stop_after_attempt(int(config["max_attempts"])),
        # Section 2.3: exponential 2/4/8/16/32, capped at backoff_base_seconds
        # x 8 = 32 s. max_attempts 4 means three waits, so 2/4/8 in practice.
        wait=tenacity.wait_exponential(
            multiplier=1,
            exp_base=2,
            min=2,
            max=float(config["backoff_base_seconds"]) * 8,
        ),
        retry=tenacity.retry_if_exception_type(_RetrySignal),
        sleep=lambda seconds: _sleep(seconds),
        reraise=True,
    )
    with _client(host) as client:
        response, elapsed = retrying(
            _attempt, client, url, host, host_budget=host_budget, counter=counter
        )
    return response, elapsed, counter["attempt"]


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------


def _dry_run_enabled() -> bool:
    return os.environ.get("ABSUMP_DRY_RUN", "").strip().lower() not in ("", "0", "false", "no")


def _estimated_wire_bytes(host: str) -> int:
    """The manifest's own mean for this host, or section 2.3's measured feed.

    Nothing here is a number invented for a plan: it is either something this
    client already measured and wrote down, or the one figure section 2.3
    records from the 822925 feed measurement.
    """
    observed = [
        int(row["wire_bytes"])
        for row in _manifest_index().values()
        if row.get("host") == host and str(row.get("wire_bytes", "")).isdigit()
    ]
    if observed:
        return round(sum(observed) / len(observed))
    return _MEASURED_FEED_WIRE_BYTES


def _plan(url: str) -> dict[str, Any]:
    host = _host_of(url)
    dest = _dest_path(url)
    cached = url in _manifest_index() and dest.exists()
    return {
        "url": url,
        "host": host,
        "dest_path": str(dest),
        "cached": cached,
        "estimated_wire_bytes": 0 if cached else _estimated_wire_bytes(host),
        "estimated_wall_clock_s": 0.0 if cached else _min_interval(host),
    }


def _print_plan(plans: list[dict[str, Any]], stream: Any) -> None:
    to_send = [plan for plan in plans if not plan["cached"]]
    total_bytes = sum(int(plan["estimated_wire_bytes"]) for plan in plans)
    total_seconds = sum(float(plan["estimated_wall_clock_s"]) for plan in plans)
    print(f"DRY RUN: {len(plans)} URLs, {len(to_send)} would be fetched, 0 sent.", file=stream)
    for plan in plans:
        state = "cached" if plan["cached"] else "fetch "
        print(
            f"  {state}  {plan['url']}\n"
            f"          -> {plan['dest_path']}\n"
            f"          est {plan['estimated_wire_bytes']:,} B on the wire, "
            f"est {plan['estimated_wall_clock_s']:.1f} s at the configured interval",
            file=stream,
        )
    print(
        f"TOTAL est {total_bytes:,} B, est {total_seconds / 60.0:.1f} min, 0 requests sent.",
        file=stream,
    )


# --------------------------------------------------------------------------
# The one public function
# --------------------------------------------------------------------------


def get(url: str, *, host_budget: bool = True) -> Response:
    """Fetch ``url`` under the project's throttle, budget and cache policy.

    Returns the cached copy without touching the network when the URL is
    already in ``data/raw/_manifest.csv`` and its file is still on disk, so a
    re-run of a completed pull costs zero requests.

    ``host_budget=False`` skips the daily-cap decrement for a request that is
    not part of a bulk pull, such as a single resume probe. It never skips the
    inter-request delay: the delay is the etiquette, the cap is the ceiling.

    Raises :class:`BudgetExceeded` when the host's daily cap is spent,
    :class:`Fatal` on 403 and on every other non-retryable 4xx, and
    :class:`Retryable` when a 429, a 5xx or a timeout survives ``max_attempts``.
    """
    host = _host_of(url)
    _check_contract(url, host)
    dest = _dest_path(url)

    if _dry_run_enabled():
        _print_plan([_plan(url)], sys.stdout)
        return Response(
            url=url,
            host=host,
            status_code=0,
            content=b"",
            dest_path=dest,
            sha256="",
            wire_bytes=0,
            disk_bytes=0,
            attempt=0,
            elapsed_s=0.0,
            from_cache=False,
            dry_run=True,
        )

    cached_row = _manifest_index().get(url)
    if cached_row is not None and dest.exists():
        body = _read_raw(dest)
        return Response(
            url=url,
            host=host,
            status_code=int(cached_row.get("http_status") or 200),
            content=body,
            dest_path=dest,
            sha256=cached_row.get("sha256") or hashlib.sha256(body).hexdigest(),
            wire_bytes=int(cached_row.get("wire_bytes") or 0),
            disk_bytes=dest.stat().st_size,
            attempt=0,
            elapsed_s=0.0,
            from_cache=True,
        )

    response, elapsed, attempt = _fetch(url, host, host_budget=host_budget)
    body = response.content
    wire_bytes = int(getattr(response, "num_bytes_downloaded", 0) or len(body))
    disk_bytes = _write_raw(dest, body)
    digest = hashlib.sha256(body).hexdigest()
    _manifest_append(
        {
            "fetched_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "host": host,
            "url": url,
            "http_status": response.status_code,
            "wire_bytes": wire_bytes,
            "disk_bytes": disk_bytes,
            "sha256": digest,
            "attempt": attempt,
            "elapsed_s": f"{elapsed:.3f}",
            "dest_path": str(dest),
        }
    )
    return Response(
        url=url,
        host=host,
        status_code=response.status_code,
        content=body,
        dest_path=dest,
        sha256=digest,
        wire_bytes=wire_bytes,
        disk_bytes=disk_bytes,
        attempt=attempt,
        elapsed_s=elapsed,
        from_cache=False,
        headers={key.lower(): value for key, value in response.headers.items()},
    )


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

_USAGE = """usage: python -m absump.http [--dry-run] URL [URL ...]

  --dry-run   print the request plan (URL, destination, estimated bytes,
              estimated wall clock) and send nothing.

Without --dry-run each URL is fetched through get(), under the throttle, the
daily budget and the raw cache of config/throttle.yml.
"""


def _main(argv: list[str]) -> int:
    urls = [arg for arg in argv if not arg.startswith("-")]
    flags = {arg for arg in argv if arg.startswith("-")}
    if not urls or flags - {"--dry-run"}:
        print(_USAGE, file=sys.stderr)
        return 2
    if "--dry-run" in flags:
        _print_plan([_plan(url) for url in urls], sys.stdout)
        return 0
    for url in urls:
        response = get(url)
        source = "cache" if response.from_cache else "wire "
        print(f"{response.status_code} {source} {len(response.content):,} B  {url}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main(sys.argv[1:]))
