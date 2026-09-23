"""W1.2 layout test and the W2.1 no-raw-data guard.

Asserts the section 2.1 repository tree exists on disk, that the five private
directories are git-ignored, and that git tracks nothing under them.

SOP W1.2 names three ignored paths (data/, research/, logs/). The fleet's D-03
extension adds sop/ and fleet/, which are private planning material of the same
class, so this test asserts five, not three.

W2.1 adds test_no_data_tracked, the CI half of the no-raw-data guard, and the
tests of .git/hooks/pre-commit, its local half.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Section 2.1, directories that git tracks. Each carries a .gitkeep so the
# directory survives a clone.
# ".github/workflows" is deliberately absent: the gh token this project runs with has no
# workflow scope, so the two workflow files are parked under ops/ci-pending/ (DECISIONS.md)
# until a scoped token lands. test_ci_is_either_wired_or_parked below holds them to account.
TRACKED_DIRS = [
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

MLBAM_SENTENCE = "Only individual, non-commercial, non-bulk use of the Materials is permitted"

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


def test_repo_is_a_git_repository_on_the_main_line():
    """W1.2. The branch model actually in use is: work on phase01/<x>, fast-forward main
    onto it, push main. So HEAD is not always the literal ref refs/heads/main, and pinning
    it there failed on every working branch. What must hold is that main exists, that
    origin/main agrees with it, and that HEAD is on the main line rather than off it."""
    assert (REPO_ROOT / ".git").is_dir(), f"no git repository at {REPO_ROOT}"

    origin = git("rev-parse", "--verify", "refs/remotes/origin/main")
    assert origin.returncode == 0, f"origin/main does not resolve: {origin.stderr.strip()}"
    main_tip = origin.stdout.strip()

    # A local branch main is not guaranteed: a clone checked out on phase01/public
    # has origin/main and no refs/heads/main, and requiring the local ref failed
    # there for a reason that says nothing about the layout. origin/main is the
    # anchor; a local main, when it exists, must agree with it.
    local = git("rev-parse", "--verify", "refs/heads/main")
    if local.returncode == 0:
        assert local.stdout.strip() == main_tip, (
            f"origin/main is {main_tip[:12]} but local main is {local.stdout.strip()[:12]}; "
            "main was not pushed, or the remote moved ahead"
        )

    head_tip = git("rev-parse", "HEAD").stdout.strip()
    on_main_line = head_tip == main_tip or (
        git("merge-base", "--is-ancestor", main_tip, head_tip).returncode == 0
    )
    assert on_main_line, (
        f"HEAD {head_tip[:12]} is neither origin/main's tip nor a descendant of it "
        f"{main_tip[:12]}: this branch has diverged from the main line"
    )


def _listing(path: Path) -> object:
    return sorted(q.name for q in path.glob("*")) if path.is_dir() else "absent"


def test_ci_is_either_wired_or_parked():
    """W1.2 / W1.3 / W1.16. The gh token in use has no workflow scope, so pushing
    .github/workflows/ is refused. DECISIONS.md parks the two workflow files under
    ops/ci-pending/ until a scoped token exists. Either location satisfies this test;
    losing a file from both does not."""
    wired = REPO_ROOT / ".github" / "workflows"
    parked = REPO_ROOT / "ops" / "ci-pending"
    wired_ok = all((wired / n).is_file() for n in ("ci.yml", "seal-guard.yml"))
    parked_ok = all((parked / n).is_file() for n in ("ci.yml", "seal-guard.yml", "README.md"))
    assert wired_ok or parked_ok, (
        "CI is neither wired nor parked: expected .github/workflows/ to hold ci.yml and "
        "seal-guard.yml, or ops/ci-pending/ to hold ci.yml, seal-guard.yml and README.md. "
        f"Found .github/workflows={_listing(wired)}; ops/ci-pending={_listing(parked)}"
    )


@pytest.mark.parametrize("rel", TRACKED_DIRS)
def test_directory_exists(rel: str):
    """W1.2. Only the tracked half of section 2.1 can be asserted to exist.

    The ignored half (IGNORED_DIRS) is excluded by .gitignore by design, so a
    fresh clone never carries it and requiring it here made W1.2 unpassable
    anywhere but the one machine that had already created the directories by
    hand. Worse, it asked for .github/workflows and data/ from a repository the
    same task forbids to hold either. The ignored half is held to account by
    test_ignored_directory_is_ignored below, which checks the .gitignore rule
    rather than the filesystem and therefore reads the same in a clone.
    """
    path = REPO_ROOT / rel
    assert path.is_dir(), f"missing directory: {rel}"


@pytest.mark.parametrize("rel", IGNORED_DIRS)
def test_ignored_directory_is_ignored(rel: str):
    """W1.2. Checked through a probe path INSIDE the directory, never the bare name.

    .gitignore writes these rules with a trailing slash (`research/`), which matches
    a directory. git resolves a path that does not exist on disk as a file, so in a
    clone -- where every ignored directory is absent by design -- `git check-ignore
    research` reports nothing and exits 1, while `git check-ignore research/probe`
    matches the same rule and exits 0. The probe form therefore reads the same in a
    clone and on a working machine, which is what W1.2 is asserting.
    """
    result = git("check-ignore", "-q", ignore_probe(rel))
    assert result.returncode == 0, (
        f"git check-ignore -q {rel} exited {result.returncode}; the directory is named "
        "in IGNORED_DIRS but .gitignore does not cover it, so its contents would publish"
    )


@pytest.mark.parametrize("rel", TRACKED_DIRS)
def test_tracked_directory_has_a_gitkeep(rel: str):
    keep = REPO_ROOT / rel / ".gitkeep"
    assert keep.is_file(), f"missing .gitkeep in tracked directory: {rel}"


def ignore_probe(rel: str) -> str:
    """A path inside `rel`, so a trailing-slash .gitignore rule matches whether or not
    the directory exists on this machine. See test_ignored_directory_is_ignored."""
    return f"{rel}/.ignore-probe"


@pytest.mark.parametrize("rel", PRIVATE_PATHS)
def test_private_path_is_git_ignored(rel: str):
    """git check-ignore -q over data/raw research logs sop fleet, one path per call.

    Each is asked through a probe path inside it, for the reason given in
    test_ignored_directory_is_ignored: the bare name answers differently in a clone.
    """
    probe = ignore_probe(rel)
    result = git("check-ignore", "-q", probe)
    assert result.returncode == 0, (
        f"git check-ignore -q {probe} exited {result.returncode}; "
        f"{rel} is not ignored and its contents would be published"
    )


def test_private_paths_are_ignored_in_one_call():
    """The SOP writes the check as one command over several paths.

    git 2.50.1 rejects `--quiet` with more than one pathname
    ("fatal: --quiet is only valid with a single pathname"), so the multi-path
    form runs without -q and every path must come back listed as ignored. The
    per-path test above is the literal `git check-ignore -q <path>` the SOP asks
    for, run once per path.
    """
    probes = [ignore_probe(rel) for rel in PRIVATE_PATHS]
    result = git("check-ignore", *probes)
    assert result.returncode == 0, result.stderr
    # sorted lists, never sets: pytest renders a failing set comparison in
    # PYTHONHASHSEED order, which made this step's receipt log differ byte for
    # byte between two otherwise identical `make prove` runs.
    reported = sorted(result.stdout.split())
    assert reported == sorted(probes), (
        f"git check-ignore reported {reported}, expected {sorted(probes)}"
    )


def test_git_tracks_nothing_under_a_private_path():
    """git ls-files | grep -E '^(data|research|logs|sop|fleet)/' returns nothing."""
    result = git("ls-files")
    assert result.returncode == 0, result.stderr
    offenders = [line for line in result.stdout.splitlines() if PRIVATE_PREFIX_RE.match(line)]
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


# ---------------------------------------------------------------------------
# W2.1, the no-raw-data guard.
#
# The step asks for two independent checks of one rule. test_no_data_tracked is
# the CI half, written as the SOP writes it: `git ls-files data/ | wc -l == 0`.
# The hook tests below are the local half. Both exist because a hook does not
# travel with a clone: a fresh clone of hpagni/abs-umpires has no
# .git/hooks/pre-commit at all, so CI cannot trust that one ran.
# ---------------------------------------------------------------------------

HOOK = REPO_ROOT / ".git" / "hooks" / "pre-commit"
FRAMEWORK_HOOK = REPO_ROOT / ".git" / "hooks" / "pre-commit.framework"

# First path segments that never enter git. D-03 and SOP section 0.5 rule 3 name
# data/, research/ and logs/; this fleet adds sop/, fleet/ and RUNLOG.md.
REFUSED_PATHS = [
    "data/raw/statcast_2026.parquet",
    "data/staging/manifest.jsonl",
    "data/x",
    "research/notes.md",
    "logs/evidence/W2.1.log",
    "sop/SOP-final.md",
    "fleet/PLAN.md",
    "RUNLOG.md",
    "./data/raw/statcast_2026.parquet",
]

# Paths that look like the refused ones but are source, not data. The match is on
# the first path segment, so these pass.
ALLOWED_PATHS = [
    "app/data/park_factors.csv",
    "tests/data/DT-01_expected.csv",
    "src/absump/http.py",
    "R/lib/http.R",
    "docs/prereg/prereg-v1.md",
    "quality/steps.yml",
    "mydata/x.csv",
    "logsomething.py",
]


def run_hook(*args: str) -> subprocess.CompletedProcess[str]:
    """Drive the hook in its --check form.

    --check reads no index and chains to no other hook, so it cannot alter the
    repository. The git-invoked form is covered end to end in a throwaway
    repository by test_hook_blocks_a_real_commit.
    """
    return subprocess.run(
        [str(HOOK), "--check", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_data_tracked():
    """SOP W2.1: `git ls-files data/ | wc -l == 0`.

    This is the half of the guard that survives a clone. The hook is local to one
    working copy; this assertion runs in CI on every push.
    """
    result = git("ls-files", "data/")
    assert result.returncode == 0, result.stderr
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(tracked) == 0, (
        f"git tracks {len(tracked)} path(s) under data/: {tracked[:10]}. "
        "The repository is public from its first commit (D-02), so a raw feed "
        "path in the index is not recoverable by a later commit."
    )


def test_hook_exists_and_is_executable():
    assert HOOK.is_file(), (
        f"no pre-commit hook at {HOOK}; a fresh clone has none. "
        "Install it with `bash ops/install_git_hooks.sh`, which is also the repair for a "
        "hook that `pre-commit install` has overwritten"
    )
    assert HOOK.stat().st_mode & 0o111, f"{HOOK} is not executable"


def test_hook_is_the_w2_1_guard_not_only_the_framework_hook():
    """W1.13 installed the pre-commit framework hook. W2.1 adds a raw one.

    The framework hook is generated by `pre-commit install` and carries that
    banner. If .git/hooks/pre-commit still carries it, the W2.1 guard was
    overwritten, most likely by a later `pre-commit install`.
    """
    text = HOOK.read_text(encoding="utf-8")
    assert "generated by pre-commit" not in text, (
        "the W2.1 hook was replaced by the pre-commit framework hook; "
        "run `bash ops/install_git_hooks.sh` to reinstate the guard, which chains to it"
    )
    assert "NO RAW DATA FAIL" in text


def test_hook_chains_to_the_framework_hook():
    """The W2.1 hook must not cost the repository the W1.13 hooks."""
    assert FRAMEWORK_HOOK.is_file(), (
        f"no preserved framework hook at {FRAMEWORK_HOOK}; the W1.13 hooks would "
        "not run on a commit. A fresh clone has neither hook: install both with "
        "`uv run --locked pre-commit install && bash ops/install_git_hooks.sh`"
    )
    assert "generated by pre-commit" in FRAMEWORK_HOOK.read_text(encoding="utf-8")
    assert FRAMEWORK_HOOK.stat().st_mode & 0o111, f"{FRAMEWORK_HOOK} is not executable"
    assert 'exec "$CHAIN"' in HOOK.read_text(encoding="utf-8")


def test_hooks_are_not_redirected_elsewhere():
    """core.hooksPath set anywhere would silently disable .git/hooks/."""
    result = git("config", "--get", "core.hooksPath")
    assert result.returncode != 0, (
        f"core.hooksPath is set to {result.stdout.strip()!r}; .git/hooks/pre-commit would never run"
    )


@pytest.mark.parametrize("rel", REFUSED_PATHS)
def test_hook_refuses_a_private_path(rel: str):
    result = run_hook(rel)
    assert result.returncode == 1, f"the hook accepted {rel!r}"
    assert "NO RAW DATA FAIL" in result.stderr


def test_hook_refuses_a_data_path_with_a_space_in_it():
    result = run_hook("data/raw/a b/c.parquet")
    assert result.returncode == 1
    assert "data/raw/a b/c.parquet" in result.stderr


@pytest.mark.parametrize("rel", ALLOWED_PATHS)
def test_hook_allows_a_source_path(rel: str):
    result = run_hook(rel)
    assert result.returncode == 0, (
        f"the hook refused {rel!r}, which is source, not data: {result.stderr}"
    )


def test_hook_allows_an_empty_staged_list():
    result = run_hook()
    assert result.returncode == 0, result.stderr


def test_hook_refuses_a_mixed_list():
    """One bad path in a large clean commit still fails the whole commit."""
    result = run_hook("src/absump/http.py", "data/raw/x.parquet", "R/lib/http.R")
    assert result.returncode == 1
    assert "data/raw/x.parquet" in result.stderr
    assert "src/absump/http.py" not in result.stderr


def test_hook_reads_the_staged_list_when_git_calls_it():
    """git passes a pre-commit hook no arguments, so the hook must ask git."""
    assert "git diff --cached --name-only --diff-filter=ACMR" in HOOK.read_text(encoding="utf-8")


def _init_throwaway_repo(root: Path) -> list[str]:
    """A repository outside this one, so the end-to-end test stages nothing here.

    Returns the git prefix that pins identity and hooks path. Staging a data file
    in this repository would write a blob for it into .git/objects, which is
    exactly what the guard exists to prevent, so the real index is never touched.
    """
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(root)],
        capture_output=True,
        text=True,
        check=True,
    )
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HOOK, hooks / "pre-commit")
    (hooks / "pre-commit").chmod(0o755)
    return [
        "git",
        "-c",
        "user.name=W2.1 test",
        "-c",
        "user.email=w21@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        f"core.hooksPath={hooks}",
    ]


def test_hook_blocks_a_real_commit(tmp_path: Path):
    """End to end: git itself calls the hook, with no arguments, and the commit fails.

    The throwaway repository has no pre-commit.framework hook, which is also the
    state of a fresh clone. The guard still has to fire.
    """
    root = tmp_path / "throwaway"
    prefix = _init_throwaway_repo(root)

    (root / "src").mkdir()
    (root / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (root / "data" / "raw").mkdir(parents=True)
    (root / "data" / "raw" / "x.parquet").write_text("not really a parquet\n", encoding="utf-8")

    add = subprocess.run(
        [*prefix, "add", "-A"], cwd=root, capture_output=True, text=True, check=False
    )
    assert add.returncode == 0, add.stderr

    commit = subprocess.run(
        [*prefix, "commit", "-m", "should never land"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert commit.returncode != 0, "the hook let a commit containing data/ through"
    assert "NO RAW DATA FAIL" in commit.stderr
    assert "data/raw/x.parquet" in commit.stderr

    log = subprocess.run(
        [*prefix, "log", "--oneline"], cwd=root, capture_output=True, text=True, check=False
    )
    assert log.stdout.strip() == "", f"a commit was written anyway: {log.stdout!r}"


def test_hook_lets_a_clean_commit_through(tmp_path: Path):
    """The guard must not block ordinary work."""
    root = tmp_path / "throwaway-clean"
    prefix = _init_throwaway_repo(root)

    (root / "src").mkdir()
    (root / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (root / "app" / "data").mkdir(parents=True)
    (root / "app" / "data" / "park_factors.csv").write_text("park,factor\n", encoding="utf-8")

    add = subprocess.run(
        [*prefix, "add", "-A"], cwd=root, capture_output=True, text=True, check=False
    )
    assert add.returncode == 0, add.stderr

    commit = subprocess.run(
        [*prefix, "commit", "-m", "first commit"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert commit.returncode == 0, f"the hook blocked a clean commit: {commit.stderr}"

    tracked = subprocess.run(
        [*prefix, "ls-files"], cwd=root, capture_output=True, text=True, check=False
    )
    assert "app/data/park_factors.csv" in tracked.stdout


# ---------------------------------------------------------------------------
# The guard's tracked source. git never tracks .git/hooks, so the local half of
# the guard does not survive a clone. ops/hook_precommit_guard.sh is the tracked
# copy and ops/install_git_hooks.sh puts it back.
# ---------------------------------------------------------------------------

GUARD_SOURCE = REPO_ROOT / "ops" / "hook_precommit_guard.sh"
INSTALLER = REPO_ROOT / "ops" / "install_git_hooks.sh"


def test_guard_source_is_tracked_and_executable():
    assert GUARD_SOURCE.is_file(), f"no tracked guard source at {GUARD_SOURCE}"
    assert GUARD_SOURCE.stat().st_mode & 0o111, f"{GUARD_SOURCE} is not executable"
    result = git("ls-files", "--error-unmatch", "ops/hook_precommit_guard.sh")
    if result.returncode != 0:
        pytest.skip("the W2 commit has not run yet; the guard source is not staged")


def test_installer_exists_and_is_executable():
    assert INSTALLER.is_file(), f"no installer at {INSTALLER}"
    assert INSTALLER.stat().st_mode & 0o111, f"{INSTALLER} is not executable"


def test_installed_hook_matches_its_tracked_source():
    """A drifted hook means the installed guard is not the reviewed one."""
    installed = HOOK.read_text(encoding="utf-8")
    source = GUARD_SOURCE.read_text(encoding="utf-8")
    assert installed == source, (
        "the installed hook differs from ops/hook_precommit_guard.sh; "
        "run `bash ops/install_git_hooks.sh` to reinstate it"
    )


def test_installer_is_idempotent():
    """Running it twice must leave the same hook and must not disturb the chain."""
    assert HOOK.is_file() and FRAMEWORK_HOOK.is_file(), (
        "both hooks must be installed before idempotence can be asserted; a fresh clone "
        "has neither. Run `uv run --locked pre-commit install && bash ops/install_git_hooks.sh`"
    )
    before = HOOK.read_bytes()
    chain_before = FRAMEWORK_HOOK.read_bytes()
    for _ in range(2):
        result = subprocess.run(
            ["bash", str(INSTALLER)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    assert HOOK.read_bytes() == before
    assert FRAMEWORK_HOOK.read_bytes() == chain_before
    assert HOOK.stat().st_mode & 0o111


def test_guard_source_makes_no_http_request():
    """SOP section 0.5 rule 2. The guard reads the index and nothing else."""
    text = GUARD_SOURCE.read_text(encoding="utf-8") + INSTALLER.read_text(encoding="utf-8")
    for token in ("curl", "wget", "http://", "https://"):
        assert token not in text, f"{token!r} appears in the W2.1 hook scripts"
