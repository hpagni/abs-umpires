"""The daily budget is counted exactly when several pullers share it.

``data/raw/_budget.json`` is one file for every host and every process: the
statsapi feed batch, the Savant day chain and the Retrosheet pull each spend
their own host's cap out of it. The spend is a read-modify-write. Under a
thread lock alone, two processes could both read N and both write N + 1, so
the count came out low and a host's D-63 cap could be overshot. absump.http now
holds flock(2) on ``_budget.json.lock`` beside the file for the whole
read-modify-write, and writes through a per-process temporary name.

Nothing here opens a connection. ``_budget_take`` is the budget half of a
request and nothing else; the subprocesses call it directly against a
temporary cache directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from absump import http as client

REPO_ROOT = Path(__file__).resolve().parents[2]

# Each worker waits for the go file, then spends TAKES requests as fast as it
# can. Four workers at once is the contended case the old code lost counts in.
WORKERS = 4
TAKES = 150

_WORKER = textwrap.dedent(
    """
    import sys, time
    from pathlib import Path
    from absump import http as client

    cache, host, takes, go = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
    client._reset_state(cache_dir=cache)
    deadline = time.monotonic() + 30
    while not go.exists():
        if time.monotonic() > deadline:
            raise SystemExit("never told to go")
        time.sleep(0.001)
    for _ in range(takes):
        client._budget_take(host)
    """
)


def _spawn(cache: Path, host: str, takes: int, go: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [sys.executable, "-c", _WORKER, str(cache), host, str(takes), str(go)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _run_workers(cache: Path, hosts: list[str], takes: int) -> None:
    go = cache / "go"
    procs = [_spawn(cache, host, takes, go) for host in hosts]
    time.sleep(0.5)  # let every interpreter import and reach the wait loop
    go.write_text("go")
    for proc in procs:
        _out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err.decode()


@pytest.fixture
def cache(tmp_path: Path):
    root = tmp_path / "raw"
    root.mkdir()
    yield root
    client._reset_state()


def _used(cache: Path) -> dict[str, int]:
    state = json.loads((cache / "_budget.json").read_text(encoding="utf-8"))
    assert state["utc_date"] == client._utc_day()
    return {host: int(count) for host, count in state["used"].items()}


def test_concurrent_processes_on_one_host_never_lose_a_count(cache: Path) -> None:
    host = "statsapi.mlb.com"
    _run_workers(cache, [host] * WORKERS, TAKES)
    assert _used(cache) == {host: WORKERS * TAKES}


def test_concurrent_processes_on_different_hosts_never_lose_each_others_count(
    cache: Path,
) -> None:
    """The case the launch report named: two pullers, two hosts, one file."""
    hosts = ["statsapi.mlb.com", "baseballsavant.mlb.com", "www.retrosheet.org", "statsapi.mlb.com"]
    _run_workers(cache, hosts, TAKES)
    assert _used(cache) == {
        "statsapi.mlb.com": 2 * TAKES,
        "baseballsavant.mlb.com": TAKES,
        "www.retrosheet.org": TAKES,
    }


def test_no_temporary_file_is_left_behind(cache: Path) -> None:
    _run_workers(cache, ["statsapi.mlb.com"] * 2, 50)
    leftovers = sorted(p.name for p in cache.iterdir() if p.name.endswith(".tmp"))
    assert leftovers == []


def test_the_lock_file_sits_beside_the_budget_file(cache: Path) -> None:
    client._reset_state(cache_dir=cache)
    client._budget_take("statsapi.mlb.com")
    assert (cache / "_budget.json").is_file()
    assert (cache / "_budget.json.lock").is_file()


def test_the_temporary_name_is_per_process(cache: Path, monkeypatch) -> None:
    client._reset_state(cache_dir=cache)
    seen: list[str] = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append(Path(src).name)
        return real_replace(src, dst)

    monkeypatch.setattr(client.os, "replace", spy)
    client._write_budget({"utc_date": client._utc_day(), "used": {}})
    assert len(seen) == 1
    assert str(os.getpid()) in seen[0]
    assert seen[0] != "_budget.json.tmp"


def test_a_stale_overwrite_by_an_unlocked_writer_never_lowers_this_processs_count(
    cache: Path,
) -> None:
    """A writer without the flock (a process started before the fix, or the R
    half) can replace the file with an older count for this host. The count
    this process last wrote is a floor, so the cap is never overshot by it."""
    host = "baseballsavant.mlb.com"
    client._reset_state(cache_dir=cache)
    for _ in range(5):
        client._budget_take(host)
    stale = {"utc_date": client._utc_day(), "used": {host: 2, "statsapi.mlb.com": 40}}
    (cache / "_budget.json").write_text(json.dumps(stale), encoding="utf-8")
    left = client._budget_take(host)
    assert _used(cache) == {host: 6, "statsapi.mlb.com": 40}
    assert left == client._daily_cap(host) - 6


def test_the_cap_still_raises_under_the_lock(cache: Path) -> None:
    host = "www.retrosheet.org"
    client._reset_state(cache_dir=cache)
    cap = client._daily_cap(host)
    client._write_budget({"utc_date": client._utc_day(), "used": {host: cap - 1}})
    assert client._budget_take(host) == 0
    with pytest.raises(client.BudgetExceeded):
        client._budget_take(host)
    assert _used(cache) == {host: cap}
