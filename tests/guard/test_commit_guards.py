"""GD-07 and GD-08. What may never reach a commit.

SOP step W9.7, section 6.4.

    GD-07  the pre-commit hook blocks data/, research/, logs/ and any file over
           5 MB.
    GD-08  .gitignore covers the same ground, plus the private planning
           material and the secrets file, and does not swallow the two
           directories in the section 2.1 tree that are named data/ and hold
           source rather than data.

TWO CHECKS, NOT ONE. The hook is local: it does not travel with a clone, which
is why the SOP has CI repeat the check (section 0.5, rule 3). So this file
checks the hook where the hook exists, and checks the outcome always, against
the index itself: nothing under the three private roots is tracked, and no
tracked file is over the limit. The outcome check is the one that survives a
fresh clone, a hook that was never installed, and `git commit --no-verify`.

OWNERSHIP. The hook is not W9.7's file. `.pre-commit-config.yaml` belongs to
SOP step W1.13 and `.git/hooks/pre-commit` to W2.1. When neither is on disk yet
this file says so through a warning that pytest prints in its summary even
under -q, and still checks the outcome. It never reports a silent pass.
"""

from __future__ import annotations

import subprocess
import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The 5 MB limit, as `check-added-large-files --maxkb=5120` counts it.
MAX_KB = 5120
MAX_BYTES = MAX_KB * 1024

PRIVATE_ROOTS: tuple[str, ...] = ("data", "research", "logs")

# Paths that must be ignored, one per rule worth stating.
MUST_BE_IGNORED: tuple[str, ...] = (
    "data/raw/statsapi/schedule/sport=1/season=2026/schedule.json.zst",
    "data/sealed/mlb-2026.tar.age",
    "research/notes.md",
    "logs/evidence/W9.7.log",
    "sop/SOP-final.md",
    "fleet/PLAN.md",
    "RUNLOG.md",
    ".env",
)

# The two exceptions in the section 2.1 tree: directories named data/ that hold
# source. The unanchored data/ pattern would swallow both without a re-include.
MUST_NOT_BE_IGNORED: tuple[str, ...] = (
    "app/data/mart_called_pitches.csv",
    "tests/data/test_resume.py",
    "out/tables/headline.csv",
)

# Where the block can be written. The union of whatever exists is checked.
HOOK_SOURCES: tuple[str, ...] = (
    ".pre-commit-config.yaml",
    "ops/hook_no_raw_data.sh",
    ".git/hooks/pre-commit",
)


class GuardNotYetEnforced(UserWarning):
    """The outcome is checked, but the local hook that enforces it is not on disk."""


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def is_ignored(relative: str) -> bool:
    return git("check-ignore", "-q", "--no-index", relative).returncode == 0


def hook_sources() -> list[Path]:
    return [REPO_ROOT / name for name in HOOK_SOURCES if (REPO_ROOT / name).is_file()]


def hook_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in hook_sources())


def tracked_files() -> list[str]:
    done = git("ls-files", "--cached")
    assert done.returncode == 0, done.stderr
    return [line for line in done.stdout.splitlines() if line.strip()]


# ===================================================================== GD-07
def test_nothing_under_the_private_roots_is_tracked() -> None:
    """The outcome GD-07 exists to produce, checked against the index itself."""
    done = git("ls-files", "--cached", "--", *PRIVATE_ROOTS)
    assert done.returncode == 0, done.stderr
    tracked = [line for line in done.stdout.splitlines() if line.strip()]
    assert not tracked, "GD-07 FAIL: private material is tracked:\n" + "\n".join(tracked)


def test_no_tracked_file_is_over_the_limit() -> None:
    oversized: list[str] = []
    for relative in tracked_files():
        path = REPO_ROOT / relative
        if path.is_file() and not path.is_symlink() and path.stat().st_size > MAX_BYTES:
            oversized.append(f"{relative} ({path.stat().st_size // 1024} KB)")
    assert not oversized, f"GD-07 FAIL: tracked files over {MAX_KB} KB:\n" + "\n".join(oversized)


def test_the_pre_commit_block_is_written_somewhere() -> None:
    """The hook itself, when it exists. It is W1.13's file and W2.1's, not W9.7's."""
    sources = hook_sources()
    if not sources:
        warnings.warn(
            "GD-07 partial: no pre-commit hook on disk yet, so only the outcome is checked. "
            "The hook is written by SOP steps W1.13 (.pre-commit-config.yaml) and "
            "W2.1 (.git/hooks/pre-commit).",
            GuardNotYetEnforced,
            stacklevel=1,
        )
        return
    text = hook_text()
    absent = [root for root in PRIVATE_ROOTS if f"{root}/" not in text]
    assert not absent, (
        "GD-07 FAIL: the pre-commit block names no rule for "
        + ", ".join(f"{root}/" for root in absent)
        + f"\n  checked: {', '.join(str(p.relative_to(REPO_ROOT)) for p in sources)}"
    )
    assert str(MAX_KB) in text, f"GD-07 FAIL: no {MAX_KB} KB size limit in the pre-commit block"


# ===================================================================== GD-08
@pytest.mark.parametrize("relative", MUST_BE_IGNORED)
def test_the_gitignore_covers_it(relative: str) -> None:
    assert is_ignored(relative), f"GD-08 FAIL: {relative} is not ignored"


@pytest.mark.parametrize("relative", MUST_NOT_BE_IGNORED)
def test_the_gitignore_does_not_overreach(relative: str) -> None:
    assert not is_ignored(relative), f"GD-08 FAIL: {relative} is ignored and must not be"


def test_the_private_roots_are_ignored_as_directories() -> None:
    """D-03, extended by this fleet to the SOP and the fleet plan themselves."""
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines()}
    for root in (*PRIVATE_ROOTS, "sop", "fleet"):
        assert f"{root}/" in lines, f"GD-08 FAIL: .gitignore has no {root}/ line"


def test_the_check_is_not_vacuous() -> None:
    """A path that is neither private nor re-included must come back not ignored."""
    assert not is_ignored("README.md"), "git check-ignore reports everything ignored"
    assert is_ignored("data/anything.txt"), "git check-ignore reports nothing ignored"
