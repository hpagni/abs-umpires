"""W1.2 layout test.

Asserts the section 2.1 repository tree exists on disk, that the five private
directories are git-ignored, and that git tracks nothing under them.

SOP W1.2 names three ignored paths (data/, research/, logs/). The fleet's D-03
extension adds sop/ and fleet/, which are private planning material of the same
class, so this test asserts five, not three.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Section 2.1, directories that git tracks. Each carries a .gitkeep so the
# directory survives a clone.
TRACKED_DIRS = [
    ".github/workflows",
    "config",
    "contracts",
    "contracts/schemas",
    "docs",
    "docs/prereg",
    "docs/memo",
    "docs/memo/figs",
    "docs/portfolio",
    "docs/resume",
    "docs/p8",
    "src/absump",
    "src/absump/ingest",
    "src/absump/zone",
    "src/absump/skill",
    "src/absump/dp",
    "src/absump/market",
    "src/absump/qa",
    "src/absump/verify",
    "src/absump/ch3",
    "src/absump/p8",
    "R",
    "R/lib",
    "R/ch1",
    "R/ch2",
    "R/ch3",
    "R/p8",
    "sql",
    "quality",
    "quality/receipts",
    "quality/sql",
    "quality/checklists",
    "quality/schemas",
    "ops",
    "scripts",
    "tools",
    "tools/comms",
    "dbt",
    "dbt/models",
    "dbt/models/staging",
    "dbt/models/intermediate",
    "dbt/models/marts",
    "dbt/seeds",
    "dbt/tests",
    "tests",
    "tests/unit",
    "tests/data",
    "tests/model",
    "tests/guard",
    "tests/fixtures",
    "tests/golden",
    "tests/testthat",
    "tests/ch1",
    "tests/ch2",
    "tests/ch3",
    "tests/p8",
    "app",
    "app/R",
    "app/data",
    "app/www",
    "fixtures",
    "fixtures/prior_art",
    "fixtures/prior_art/uiloi",
    "abstract",
    "submissions",
    "submissions/ssac2027",
    "notebooks",
    "out",
    "out/ch1",
    "out/ch1/fig",
    "out/ch1/tab",
    "out/ch1/model",
    "out/ch1/log",
    "out/ch2",
    "out/ch2/fig",
    "out/ch2/tab",
    "out/ch2/model",
    "out/ch2/log",
    "out/ch3",
    "out/ch3/fig",
    "out/ch3/tab",
    "out/ch3/model",
    "out/ch3/log",
    "out/p8",
    "out/p8/fig",
    "out/p8/tab",
    "out/p8/model",
    "out/p8/log",
    "out/tables",
    "out/figures",
    "out/models",
    "out/audit",
    "out/sealed",
    "out/exports",
]

# Section 2.1, directories git never tracks. They exist on the working machine
# and are absent from a clone by design.
IGNORED_DIRS = [
    "warehouse",
    "data",
    "data/raw",
    "data/interim",
    "data/marts",
    "data/sealed",
    "data/tmp",
    "data/p8",
    "research",
    "logs",
    "logs/evidence",
    "sop",
    "fleet",
]

# SOP W1.2 names three; D-03 as extended by this fleet makes it five.
PRIVATE_PATHS = ["data/raw", "research", "logs", "sop", "fleet"]

PRIVATE_PREFIX_RE = re.compile(r"^(data|research|logs|sop|fleet)/")

# Every pattern SOP W1.2 requires .gitignore to cover.
REQUIRED_GITIGNORE_PATTERNS = [
    "data/",
    "research/",
    "logs/",
    "out/**/*.parquet",
    "out/models/**/*.rds",
    "out/models/**/*.npz",
    ".env",
    ".Renviron",
    ".venv/",
    "renv/library/",
    "renv/staging/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    "*.duckdb",
    "*.duckdb.wal",
    "*.xlsx",
    "warehouse/",
    "dbt/target/",
    "dbt/dbt_packages/",
    "dbt/logs/",
    ".DS_Store",
    # D-03 extension, this fleet.
    "sop/",
    "fleet/",
]

MLBAM_NOTICE = (
    "Copyright 2026 MLB Advanced Media, L.P.  Use of any content on this page "
    "acknowledges agreement to the terms posted here "
    "http://gdx.mlb.com/components/copyright.txt"
)

MLBAM_SENTENCE = (
    "Only individual, non-commercial, non-bulk use of the Materials is permitted"
)

RETROSHEET_STATEMENT = (
    "The information used here was obtained free of\n"
    "     charge from and is copyrighted by Retrosheet.  Interested\n"
    '     parties may contact Retrosheet at "www.retrosheet.org".'
)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_repo_is_a_git_repository_on_main():
    assert (REPO_ROOT / ".git").is_dir(), f"no git repository at {REPO_ROOT}"
    head = (REPO_ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    assert head == "ref: refs/heads/main", f"HEAD is {head!r}, expected refs/heads/main"


@pytest.mark.parametrize("rel", TRACKED_DIRS + IGNORED_DIRS)
def test_directory_exists(rel: str):
    path = REPO_ROOT / rel
    assert path.is_dir(), f"missing directory: {rel}"


@pytest.mark.parametrize("rel", TRACKED_DIRS)
def test_tracked_directory_has_a_gitkeep(rel: str):
    keep = REPO_ROOT / rel / ".gitkeep"
    assert keep.is_file(), f"missing .gitkeep in tracked directory: {rel}"


@pytest.mark.parametrize("rel", PRIVATE_PATHS)
def test_private_path_is_git_ignored(rel: str):
    """git check-ignore -q data/raw research logs sop fleet all exit 0."""
    result = git("check-ignore", "-q", rel)
    assert result.returncode == 0, (
        f"git check-ignore -q {rel} exited {result.returncode}; "
        "the path is not ignored and would be published"
    )


def test_private_paths_are_ignored_in_one_call():
    """The SOP writes the check as one command over several paths.

    git 2.50.1 rejects `--quiet` with more than one pathname
    ("fatal: --quiet is only valid with a single pathname"), so the multi-path
    form runs without -q and every path must come back listed as ignored. The
    per-path test above is the literal `git check-ignore -q <path>` the SOP asks
    for, run once per path.
    """
    result = git("check-ignore", *PRIVATE_PATHS)
    assert result.returncode == 0, result.stderr
    reported = set(result.stdout.split())
    assert reported == set(PRIVATE_PATHS), (
        f"git check-ignore reported {sorted(reported)}, expected {sorted(PRIVATE_PATHS)}"
    )


def test_git_tracks_nothing_under_a_private_path():
    """git ls-files | grep -E '^(data|research|logs|sop|fleet)/' returns nothing."""
    result = git("ls-files")
    assert result.returncode == 0, result.stderr
    offenders = [
        line for line in result.stdout.splitlines() if PRIVATE_PREFIX_RE.match(line)
    ]
    assert offenders == [], f"private paths are tracked by git: {offenders}"


@pytest.mark.parametrize("pattern", REQUIRED_GITIGNORE_PATTERNS)
def test_gitignore_covers_pattern(pattern: str):
    gitignore = REPO_ROOT / ".gitignore"
    assert gitignore.is_file(), "no .gitignore at the repository root"
    lines = [
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert pattern in lines, f".gitignore does not cover {pattern!r}"


def test_license_is_mit():
    text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License"), "LICENSE is not the MIT license"
    assert "Permission is hereby granted, free of charge" in text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in text


def test_data_license_carries_the_mlbam_notice_verbatim():
    text = (REPO_ROOT / "DATA_LICENSE.md").read_text(encoding="utf-8")
    assert MLBAM_NOTICE in text, "the MLBAM notice is not verbatim in DATA_LICENSE.md"
    assert MLBAM_SENTENCE in text, "the MLBAM non-bulk sentence is missing"


def test_data_license_carries_the_retrosheet_notice_verbatim():
    text = (REPO_ROOT / "DATA_LICENSE.md").read_text(encoding="utf-8")
    assert RETROSHEET_STATEMENT in text, (
        "the Retrosheet statement from https://www.retrosheet.org/notice.txt "
        "is not verbatim in DATA_LICENSE.md"
    )
    assert "Retrosheet makes no guarantees of accuracy" in text


def test_data_license_carries_the_no_redistribution_paragraph():
    text = (REPO_ROOT / "DATA_LICENSE.md").read_text(encoding="utf-8")
    assert "## No redistribution" in text
    assert "This repository redistributes no raw feed data." in text


def test_no_2026_data_is_parsed_by_this_step():
    """Phase 01 forbids reading, pulling or joining a single 2026 datum.

    data/staging/ holds a throttled raw cache. This test asserts only that the
    cache is outside git; it opens nothing inside it.
    """
    result = git("check-ignore", "-q", "data/staging")
    assert result.returncode == 0, "the staging cache is not git-ignored"
