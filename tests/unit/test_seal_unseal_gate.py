"""`make unseal` refuses unless the unlock variable, the pushed tag and the local
tag all agree -- and it never creates the tag itself.

The verifier opened the door in four commands, with ABS_SEAL_UNLOCK unset, using
a tag made by hand that was never pushed anywhere, and the script wrote the
UNSEALED line into the public seal log regardless. Three things were missing:
the environment variable, the tag read back from the git host, and the
comparison of that answer with the local ref. All three are conditions now, and
a failure to reach the host is a failed check, not a pass.

Every case below runs against a throwaway repository under pytest's tmp_path,
with a copy of the script and a fake `gh` on PATH. The real repository is read
once, only to confirm the real gate is shut. ABS_SEAL_UNLOCK is set for the
sandbox subprocess only, never in this process and never in the real repository:
SOP rule 0.5.1 is about the owner's own shell, and the sandbox has no data, no
remote and no seal to open.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ops" / "unseal.sh"
TAG = "prereg-v1"


def build(tmp_path: Path, *, tag: bool = True, gh_stdout: str = "", gh_exit: int = 0) -> Path:
    """A throwaway repository holding a copy of the script, plus a fake `gh`."""
    root = tmp_path / "repo"
    (root / "ops").mkdir(parents=True)
    (root / "docs" / "prereg").mkdir(parents=True)
    bin_dir = tmp_path / "bin"  # outside the repository, so it never dirties it
    bin_dir.mkdir(exist_ok=True)
    shutil.copy2(SCRIPT, root / "ops" / "unseal.sh")
    (root / "PREREGISTRATION.md").write_text("# Pre-registration\n\nplaceholder\n")
    (root / "docs" / "prereg" / "SEAL.md").write_text("# Seal log\n")
    fake_gh(root, gh_stdout, gh_exit)

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(root)],
        check=True,
        capture_output=True,
    )
    git("config", "user.email", "sandbox@example.invalid")
    git("config", "user.name", "sandbox")
    git("add", "PREREGISTRATION.md", "docs/prereg/SEAL.md", "ops/unseal.sh")
    git("commit", "-q", "-m", "prereg")
    git("remote", "add", "origin", "https://github.com/example/sandbox.git")
    if tag:
        git("tag", TAG)
    return root


def fake_gh(root: Path, stdout: str, exit_code: int = 0) -> None:
    """The git host's answer, stubbed. It lives beside the repository, never in
    it, so rewriting it between cases cannot dirty the worktree."""
    gh = root.parent / "bin" / "gh"
    gh.write_text(f'#!/bin/sh\nprintf "%s" "{stdout}"\nexit {exit_code}\n')
    gh.chmod(0o755)


def run(root: Path, *args: str, unlock: str | None = "1", with_gh: bool = True):
    env = dict(os.environ)
    env.pop("ABS_SEAL_UNLOCK", None)
    if unlock is not None:
        env["ABS_SEAL_UNLOCK"] = unlock
    env["PATH"] = f"{root.parent / 'bin'}:{env['PATH']}" if with_gh else "/usr/bin:/bin"
    return subprocess.run(
        ["bash", str(root / "ops" / "unseal.sh"), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def local_tag_sha(root: Path) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), "rev-parse", f"refs/tags/{TAG}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def tags(root: Path) -> list[str]:
    done = subprocess.run(
        ["git", "-C", str(root), "tag", "--list"], capture_output=True, text=True, check=True
    )
    return done.stdout.split()


# ------------------------------------------------------------------ the real repo
def test_the_real_gate_is_shut() -> None:
    done = subprocess.run(
        ["bash", str(SCRIPT), "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    assert done.returncode == 1, done.stdout


# -------------------------------------------------------------- the control case
def test_the_gate_passes_only_when_all_six_hold(tmp_path: Path) -> None:
    """Without this, a gate that always refuses would satisfy every other test."""
    root = build(tmp_path)
    fake_gh(root, local_tag_sha(root))
    done = run(root, "--check")
    assert done.returncode == 0, done.stderr
    assert "UNSEAL CHECK OK (6/6)" in done.stdout


# ----------------------------------------------------------------- condition 4
@pytest.mark.parametrize("unlock", [None, "", "0", "true", "yes", "TRUE", " 1"])
def test_the_unlock_variable_must_carry_the_documented_value(
    tmp_path: Path, unlock: str | None
) -> None:
    root = build(tmp_path)
    fake_gh(root, local_tag_sha(root))
    done = run(root, "--check", unlock=unlock)
    assert done.returncode == 1
    assert "UNSEAL REFUSED 4/6" in done.stderr, done.stderr


# -------------------------------------------------------------- conditions 5, 6
def test_a_local_only_tag_does_not_open_the_door(tmp_path: Path) -> None:
    """The verifier's four commands, exactly: everything local is satisfied and
    the tag exists nowhere else. The host answers 404 and the gate stays shut."""
    root = build(tmp_path, gh_stdout='{"message":"Not Found","status":"404"}', gh_exit=1)
    done = run(root, "--check")
    assert done.returncode == 1
    assert "UNSEAL REFUSED 5/6" in done.stderr, done.stderr


def test_an_error_body_on_stdout_is_not_an_answer(tmp_path: Path) -> None:
    """gh prints the error body to stdout. A non-empty reply is not a sha."""
    root = build(tmp_path, gh_stdout='{"message":"Git Repository is empty."}', gh_exit=0)
    done = run(root, "--check")
    assert done.returncode == 1
    assert "UNSEAL REFUSED 5/6" in done.stderr, done.stderr


def test_a_failure_to_reach_the_host_is_a_failed_check(tmp_path: Path) -> None:
    root = build(tmp_path, gh_stdout="", gh_exit=7)
    done = run(root, "--check")
    assert done.returncode == 1
    assert "UNSEAL REFUSED 5/6" in done.stderr, done.stderr


def test_a_missing_gh_is_a_failed_check(tmp_path: Path) -> None:
    root = build(tmp_path, gh_stdout="deadbeef" * 5)
    done = run(root, "--check", with_gh=False)
    assert done.returncode == 1
    assert "UNSEAL REFUSED 5/6" in done.stderr, done.stderr


def test_a_different_object_on_the_host_is_refused(tmp_path: Path) -> None:
    """The host answers, with a sha that is not the local tag's."""
    root = build(tmp_path, gh_stdout="0" * 40)
    done = run(root, "--check")
    assert done.returncode == 1
    assert "UNSEAL REFUSED 6/6" in done.stderr, done.stderr
    assert "different objects" in done.stderr


def test_no_local_tag_is_refused_even_when_the_host_has_one(tmp_path: Path) -> None:
    root = build(tmp_path, tag=False, gh_stdout="a" * 40)
    done = run(root, "--check")
    assert done.returncode == 1
    assert "UNSEAL REFUSED 2/6" in done.stderr
    assert "UNSEAL REFUSED 6/6" in done.stderr


# ------------------------------------------------- the tag comes from one door
def test_the_script_never_creates_a_tag(tmp_path: Path) -> None:
    """Static, over the code and not the comments: no tag is written anywhere."""
    code = "\n".join(
        line
        for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    for forbidden in (r"git\s+tag\s+[^-]", r"update-ref\s+refs/tags", r"git\s+push"):
        assert not re.search(forbidden, code), f"{forbidden} appears in ops/unseal.sh"


def test_the_script_refuses_to_be_asked_for_a_tag(tmp_path: Path) -> None:
    root = build(tmp_path, tag=False)
    for argument in ("--tag", "tag", "--create-tag"):
        done = run(root, argument)
        assert done.returncode == 2, done.stdout
        assert "never creates a tag" in done.stderr
        assert "preregister.sh" in done.stderr
        assert tags(root) == []


def test_a_refused_run_creates_no_tag_and_writes_nothing(tmp_path: Path) -> None:
    root = build(tmp_path, tag=False, gh_stdout="", gh_exit=1)
    seal_doc = root / "docs" / "prereg" / "SEAL.md"
    before = seal_doc.read_text()
    done = run(root)
    assert done.returncode == 1
    assert tags(root) == []
    assert seal_doc.read_text() == before


def test_a_successful_run_records_the_event_and_still_creates_no_tag(tmp_path: Path) -> None:
    root = build(tmp_path)
    sha = local_tag_sha(root)
    fake_gh(root, sha)
    seal_doc = root / "docs" / "prereg" / "SEAL.md"
    done = run(root)
    assert done.returncode == 0, done.stderr
    line = [ln for ln in seal_doc.read_text().splitlines() if ln.startswith("UNSEALED")]
    assert len(line) == 1
    assert f"tag={TAG}" in line[0] and f"remote={sha}" in line[0]
    assert tags(root) == [TAG], "the ceremony must not mint the tag it checks"
