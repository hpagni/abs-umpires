"""GD-12, SOP W7.10: the seal-order tripwire fires on every bad ordering.

ops/check_seal_order.sh (reached through tools/comms/check_seal_order.sh) must
fail whenever a fit receipt under out/ does not descend from prereg-v1 as pushed
to origin. test_seal_receipts.py runs it on the real repository, where before the
tag it is vacuous. This file plants each ordering in a scratch repository with
its own bare origin and asserts the exit status, so the tripwire is proven to
fire before any real receipt exists.

Nothing here reads data, touches the real repository's refs, or uses a network.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ops" / "check_seal_order.sh"
ENTRY = REPO_ROOT / "tools" / "comms" / "check_seal_order.sh"
TAG = "prereg-v1"


def git(cwd: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.org",
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(cwd),
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    }
    out = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    (work / "ops").mkdir()
    (work / "config").mkdir()
    (work / "tools" / "comms").mkdir(parents=True)
    shutil.copy(SCRIPT, work / "ops" / "check_seal_order.sh")
    shutil.copy(ENTRY, work / "tools" / "comms" / "check_seal_order.sh")
    (work / "config" / "seal.yml").write_text(f'prereg_tag: "{TAG}"\n', encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "c0")
    git(work, "remote", "add", "origin", str(origin))
    return work


def commit(work: Path, name: str) -> str:
    (work / f"{name}.txt").write_text(name, encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", name)
    return git(work, "rev-parse", "HEAD")


def receipt(work: Path, name: str, sha: str | None) -> None:
    d = work / "out" / "models" / name
    d.mkdir(parents=True, exist_ok=True)
    body = {} if sha is None else {"git_sha": sha}
    (d / "provenance.json").write_text(json.dumps(body), encoding="utf-8")


def run(work: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(work / "tools" / "comms" / "check_seal_order.sh")],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def tag_and_push(work: Path) -> str:
    git(work, "tag", "-a", TAG, "-m", "prereg")
    git(work, "push", "-q", "origin", "main", f"refs/tags/{TAG}")
    return git(work, "rev-parse", "HEAD")


def test_no_tag_no_receipt_is_a_vacuous_pass(repo: Path) -> None:
    res = run(repo)
    assert res.returncode == 0 and "0 fit receipts" in res.stdout, res.stdout + res.stderr


def test_receipt_with_no_tag_fails(repo: Path) -> None:
    receipt(repo, "m1", commit(repo, "fit"))
    assert run(repo).returncode == 1


def test_local_only_tag_fails(repo: Path) -> None:
    git(repo, "tag", "-a", TAG, "-m", "prereg")
    receipt(repo, "m1", commit(repo, "fit"))
    res = run(repo)
    assert res.returncode == 1 and "not pushed" in res.stderr, res.stdout + res.stderr


def test_receipt_descending_from_pushed_tag_passes(repo: Path) -> None:
    tag_and_push(repo)
    receipt(repo, "m1", commit(repo, "fit"))
    res = run(repo)
    assert res.returncode == 0 and "1/1 fit receipt(s) descend" in res.stdout, res.stderr


def test_receipt_on_the_commit_before_the_tag_fails(repo: Path) -> None:
    before = commit(repo, "fit-before")
    commit(repo, "plan")
    tag_and_push(repo)
    receipt(repo, "early", before)
    receipt(repo, "late", commit(repo, "fit-after"))
    res = run(repo)
    assert res.returncode == 1 and "1 of 2" in res.stderr, res.stdout + res.stderr


def test_receipt_naming_no_commit_fails(repo: Path) -> None:
    tag_and_push(repo)
    receipt(repo, "m1", "0" * 40)
    assert run(repo).returncode == 1


def test_receipt_without_git_sha_fails(repo: Path) -> None:
    tag_and_push(repo)
    receipt(repo, "m1", None)
    assert run(repo).returncode == 1


def test_tag_moved_after_push_fails(repo: Path) -> None:
    tag_and_push(repo)
    commit(repo, "later")
    git(repo, "tag", "-f", "-a", TAG, "-m", "moved")
    receipt(repo, "m1", commit(repo, "fit"))
    res = run(repo)
    assert res.returncode == 1 and "not pushed" in res.stderr, res.stdout + res.stderr
