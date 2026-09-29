"""No tracked file carries the owner's personal email address or handle.

The repository is public. `abstract/FORM-FIELDS.md` carried the owner's personal
Gmail address three times from cd44758. `DECISIONS.md` carried it on one line from
74b995a: URL-encoded, in base64, and decoded. Both were replaced on 2026-09-29
(DEV-T1).
Git history still holds them; whether to scrub it is the owner's call.

The guard reads every file `git ls-files` lists and fails on either of two things:

  * an address at gmail.com, written with `@` or URL-encoded as `%40` or `%2540`;
  * the owner's handle, in any case.

What is not read, and why:

  * `renv.lock` and `uv.lock`, the two lockfiles. They are generated.
  * The pattern definitions. `quality/prose_lint.py` (WR-19), `quality/w612_check.sh`
    (the WR-15 blind grep) and `quality/wr-scope.md` (which documents WR-19) must
    name the handle to test for it. A handle there is allowed only on a line with no
    `@`, so an address written into one of them still fails.
  * A step or receipt file that quotes a command line naming `prose_lint.py`. The
    W7.2 and W7.6 verify commands carry the WR-19 pattern inline. In
    `quality/steps.yml`, `quality/steps.d/` and `quality/receipts/` a handle is
    allowed only on a line that names `prose_lint.py`.
  * This file. It assembles the handle from two parts, so it does not carry it,
    and it is excluded all the same.

An address at gmail.com has no exemption outside the lockfiles and this file.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF = "tests/guard/test_no_owner_address.py"

# Assembled so that this file does not carry the handle it looks for.
HANDLE = "hud" + "pag"
HANDLE_RE = re.compile(re.escape(HANDLE).encode(), re.IGNORECASE)
ADDRESS_RE = re.compile(rb"[A-Za-z0-9._%+-]+(?:@|%40|%2540)gmail\.com", re.IGNORECASE)

LOCKFILES = frozenset({"renv.lock", "uv.lock"})
PATTERN_FILES = frozenset({"quality/prose_lint.py", "quality/w612_check.sh", "quality/wr-scope.md"})
COMMAND_QUOTE_PREFIXES = ("quality/steps.d/", "quality/receipts/")
COMMAND_QUOTE_FILES = frozenset({"quality/steps.yml"})


def _tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    return [p.decode() for p in out.split(b"\0") if p]


def _handle_allowed(path: str, line: bytes) -> bool:
    if path in PATTERN_FILES:
        return b"@" not in line
    if path in COMMAND_QUOTE_FILES or path.startswith(COMMAND_QUOTE_PREFIXES):
        return b"prose_lint.py" in line
    return False


def scan(root: Path) -> list[tuple[str, int, str]]:
    """Every (path, line number, rule) hit in the tracked files under `root`."""
    hits: list[tuple[str, int, str]] = []
    for path in _tracked(root):
        if path in LOCKFILES or path == SELF:
            continue
        full = root / path
        if full.is_symlink() or not full.is_file():
            continue
        for n, line in enumerate(full.read_bytes().split(b"\n"), start=1):
            if ADDRESS_RE.search(line):
                hits.append((path, n, "gmail address"))
            if HANDLE_RE.search(line) and not _handle_allowed(path, line):
                hits.append((path, n, "owner handle"))
    return hits


def test_no_tracked_file_carries_the_owner_address() -> None:
    hits = scan(REPO_ROOT)
    assert not hits, f"the owner's address or handle is in a tracked file: {hits}"


def test_the_guard_fires_on_a_planted_violation(tmp_path: Path) -> None:
    """Plant violations and allowed lines in a throwaway repository, never in the tree."""
    at, pct, gmail = "@", "%40", "gmail" + ".com"
    files = {
        "notes.md": f"contact a.person{at}{gmail}\n",
        "enc.md": f"?contact=x{pct}{gmail}\n",
        "handle.md": f"signed in as {HANDLE.upper()}\n",
        "quality/prose_lint.py": f"PATTERN = r'{HANDLE}'\nmail = '{HANDLE}{at}example.invalid'\n",
        "quality/steps.yml": f"verify: 'python quality/prose_lint.py {HANDLE}'\nnote: {HANDLE}\n",
        "quality/receipts/W0.1.json": f'"cmd": "quality/prose_lint.py {HANDLE}"\n',
        "renv.lock": f"{HANDLE} {at}{gmail}\n",
        "clean.md": "someone@example.invalid\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    (tmp_path / "untracked.md").write_text(f"b{at}{gmail}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", *files], check=True, capture_output=True)

    assert sorted(scan(tmp_path)) == [
        ("enc.md", 1, "gmail address"),
        ("handle.md", 1, "owner handle"),
        ("notes.md", 1, "gmail address"),
        ("quality/prose_lint.py", 2, "owner handle"),
        ("quality/steps.yml", 2, "owner handle"),
    ]
