"""W9.1. The three properties `make prove` has to have, each one pinned by a test.

The round-2 verifier refuted the sweep on three counts and this module is the
answer to all three:

  * a step parked on an owner decision must read PENDING-OWNER, not FAIL and not
    MISSING, because MISSING means nobody built it and someone still should;
  * a receipt must not churn: two sweeps with the same outcome leave
    quality/receipts/ byte-identical, which means the run-local tokens a verify
    command prints of its own accord (a clock, a duration, `Installed 41
    packages in 17ms`, a pytest temporary directory) are normalised away before
    anything is compared or written;
  * a test file no verify command names is a test `make prove` never runs. The
    verifier found five of those in the tree.

None of these run a verify command or touch the network. The normaliser and the
lock are exercised directly, in a temporary directory.
"""

import os
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROVE = os.path.join(ROOT, "scripts", "prove.sh")
sys.path.insert(0, os.path.join(ROOT, "quality"))

from write_receipt import find, load_registry  # noqa: E402


def _harness(tmpdir):
    """prove.sh with its argument dispatch removed, so its functions can be run.

    The shebang, the BASH_SOURCE-derived ROOT and the cd are dropped and ROOT is
    supplied by the caller; everything from `usage()` to the dispatch line --
    the lock and the two stabilisers -- is kept verbatim, so what these tests
    exercise is the shipped code and not a copy of it.
    """
    with open(PROVE, encoding="utf-8") as fh:
        src = fh.read()
    body = src.split("[ $# -eq 1 ] || usage")[0]
    kept = [
        line for line in body.splitlines() if not line.startswith(("#!", "ROOT=", 'cd "$ROOT"'))
    ]
    path = os.path.join(str(tmpdir), "prove_functions.sh")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"ROOT={ROOT}\n" + "\n".join(kept) + "\n")
    return path


def _sh(tmpdir, script, *args, real_lock=False):
    """Run `script` with prove.sh's functions in scope and no inherited lock.

    ABSUMP_PROVE_LOCK is removed from the environment on purpose: under `make
    prove` these tests run as a grandchild of a sweep that already holds the
    lock, and take_lock is re-entrant, so a test of the exclusion itself has to
    start from no lock held.
    """
    env = {k: v for k, v in os.environ.items() if k != "ABSUMP_PROVE_LOCK"}
    lock_dir = os.path.join(str(tmpdir), "prove-test.lock")
    redirect = "" if real_lock else f"LOCK_DIR={lock_dir!r}\n"
    return subprocess.run(
        [
            "bash",
            "-c",
            f"set -uo pipefail\nsource {_harness(tmpdir)!r}\n{redirect}{script}",
            "prove-test",
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


# ------------------------------------------------------------------ PENDING-OWNER
PARKED = ("W1.3", "W1.16")


@pytest.mark.parametrize("step", PARKED)
def test_parked_steps_carry_a_pending_owner_line(step):
    rec = find(step)
    assert rec is not None, f"{step} is not registered"
    note = str(rec.get("pending_owner", "")).strip()
    assert note, f"{step} must carry a pending_owner line, not fall through to MISSING"
    assert len(note) > 40, f"{step}: pending_owner must say which move the owner makes"


@pytest.mark.parametrize("step", PARKED)
def test_parked_steps_report_pending_owner_not_missing(step):
    out = subprocess.run(["bash", PROVE, step], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, f"{step} must not fail the gate: {out.stderr}"
    assert "PENDING-OWNER" in out.stdout, out.stdout
    assert "MISSING" not in out.stdout, out.stdout


def test_pending_owner_is_reserved_for_finished_build_work():
    """Only the two parked GitHub Actions steps may use it, so it cannot become
    a way of quietly excusing unfinished work."""
    carrying = [r["id"] for r in load_registry() if str(r.get("pending_owner", "")).strip()]
    assert sorted(carrying) == sorted(PARKED), carrying


# -------------------------------------------------------------------- normalising
CHURN = (
    ("6:54AM INF scan started", "clock"),
    ("Installed 41 packages in 17ms", "elapsed"),
    ("Resolved 93 packages in 1.63s", "elapsed"),
    ("basetemp=/private/var/folders/x/pytest-411/test_x0", "tmpdir"),
    ("stack load: 1.8 s", "timing"),
)


def _normalise(tmp_path, text):
    src, dest = tmp_path / "captured", tmp_path / "receipt.log"
    src.write_text(text, encoding="utf-8")
    res = _sh(tmp_path, 'stable_log "$1" "$2"', str(src), str(dest))
    assert res.returncode == 0, res.stderr
    return dest.read_text(encoding="utf-8") if dest.exists() else ""


@pytest.mark.parametrize("line,family", CHURN)
def test_run_local_tokens_are_masked(tmp_path, line, family):
    got = _normalise(tmp_path, line + "\n")
    assert not re.search(r"\d{1,2}:\d{2}(AM|PM)", got), got
    assert "pytest-411" not in got, got
    assert re.search(r"<clock>|<elapsed>|pytest-<n>", got), got
    assert "normalised run-local tokens" in got, got


def test_meaning_bearing_numbers_survive(tmp_path):
    got = _normalise(tmp_path, "Installed 41 packages in 17ms\n2 failed, 38 passed\n")
    assert "41 packages" in got and "2 failed, 38 passed" in got, got


def test_escapes_and_trailing_whitespace_are_stripped(tmp_path):
    got = _normalise(tmp_path, "\x1b[32mgreen\x1b[0m   \n\n\n")
    assert got == "green\n", repr(got)


def test_a_log_is_rewritten_only_when_the_content_changes(tmp_path):
    dest = tmp_path / "receipt.log"
    _normalise(tmp_path, "6:54AM INF scanning\n")
    first = dest.stat().st_mtime_ns
    # A later run of the same step, one minute on the clock and nothing else.
    src = tmp_path / "captured"
    src.write_text("6:55AM INF scanning\n", encoding="utf-8")
    assert _sh(tmp_path, 'stable_log "$1" "$2"', str(src), str(dest)).returncode == 0
    assert dest.stat().st_mtime_ns == first, "an unchanged receipt log was rewritten"


# --------------------------------------------------------------------- the lock
def test_the_lock_is_mkdir_based_and_excludes_a_second_run(tmp_path):
    with open(PROVE, encoding="utf-8") as fh:
        src = fh.read()
    assert 'mkdir "$LOCK_DIR"' in src, "the lock must be mkdir, the atomic primitive"
    res = _sh(
        tmp_path, 'take_lock; mkdir "$LOCK_DIR" 2>/dev/null && echo TOOK-IT-TWICE || echo EXCLUDED'
    )
    assert "EXCLUDED" in res.stdout, res.stdout + res.stderr


def test_the_lock_is_released_and_is_re_entrant_for_a_nested_prove(tmp_path):
    res = _sh(
        tmp_path,
        'take_lock; echo "$ABSUMP_PROVE_LOCK"; release_lock;'
        ' test -d "$LOCK_DIR" && echo LEAKED || echo RELEASED',
    )
    assert "RELEASED" in res.stdout, res.stdout
    res = _sh(
        tmp_path,
        "ABSUMP_PROVE_LOCK=/tmp/parent take_lock;"
        ' test -d "$LOCK_DIR" && echo TOOK || echo DEFERRED',
    )
    assert "DEFERRED" in res.stdout, res.stdout


def test_the_lock_lives_outside_the_repository(tmp_path):
    """An in-tree lock would make git_dirty true in every receipt written during
    the sweep, and would appear inside the tree the reproducibility clause diffs."""
    res = _sh(tmp_path, 'echo "$LOCK_DIR"', real_lock=True)
    assert not res.stdout.strip().startswith(ROOT), res.stdout


# ---------------------------------------------------------------- registration
def _gate_text():
    parts = [pathlib.Path(os.path.join(ROOT, "quality", "steps.yml")).read_text(encoding="utf-8")]
    for rel in ("Makefile",):
        parts.append(pathlib.Path(os.path.join(ROOT, rel)).read_text(encoding="utf-8"))
    ops = os.path.join(ROOT, "ops")
    for name in sorted(os.listdir(ops)):
        if name.endswith((".sh", ".py")):
            parts.append(
                pathlib.Path(os.path.join(ops, name)).read_text(encoding="utf-8", errors="replace")
            )
    return "\n".join(parts)


def _test_modules():
    for sub in ("tests/unit", "tests/fixtures", "tests/guard"):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith("test_") and name.endswith(".py"):
                yield f"{sub}/{name}"


def test_every_test_module_is_named_by_some_verify_command():
    """The verifier's finding, generalised: a tool or a test the gate does not
    name is a tool or a test the gate does not run."""
    text = _gate_text()
    directory_runs = [
        d for d in ("tests/guard", "tests/unit", "tests/fixtures") if f"pytest {d} " in text
    ]
    orphans = [
        rel
        for rel in _test_modules()
        if rel not in text
        and os.path.basename(rel) not in text
        and os.path.dirname(rel) not in directory_runs
    ]
    assert orphans == [], f"registered in no verify command: {orphans}"


def test_the_two_registry_gated_quality_tools_are_registered():
    text = pathlib.Path(os.path.join(ROOT, "quality", "steps.yml")).read_text(encoding="utf-8")
    for tool in ("ops/lint_prose.sh", "quality/check_numbers.py"):
        assert tool in text, f"{tool} exists, is red, and no step runs it"
