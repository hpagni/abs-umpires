#!/usr/bin/env python3
"""quality/check_prereg.py -- the pre-registration checker. SOP step W7.8.

SOP section 3 lists this step as `W7.8  prereg checker -> W7.6, W7.7`. SOP W7.42
makes it the second check `tools/comms/check_all.sh` runs. It implements the six
preconditions of SOP section 2.4, phase 5, which `absump.seal._unlocked()` guards
at runtime. The SOP text, verbatim:

    1. tag `prereg-v1` exists;
    2. it is pushed -- `git ls-remote --tags origin refs/tags/prereg-v1` returns
       the same sha as the local tag;
    3. it is an ancestor of `HEAD`;
    4. the worktree is clean;
    5. `quality/prereg.lock` matches `shasum -a 256` of
       `git show prereg-v1:PREREGISTRATION.md` and the annexes;
    6. the owner has set `ABS_SEAL_UNLOCK=1` in one shell and appended a dated
       line to `DECISIONS.md` recording the unlock and the manifest sha256.

Each precondition is its own function with its own verdict. No check stops
another from running, so one run reports every failing precondition.

WHAT EACH CHECK READS. The tag name comes from `config/seal.yml` (`prereg_tag`),
the file absump.seal reads. Tagged content is read with `git cat-file blob
refs/tags/<tag>:<path>`: the raw blob, the bytes `git show` prints for it, and a
refname that a branch of the same name cannot shadow.

  1. `refs/tags/<tag>` exists, is an annotated tag object and peels to a commit.
     Stricter than absump.seal, which accepts a lightweight tag. ops/preregister.sh
     cuts the tag with `git tag -a`, and PREREGISTRATION.md says the annotated
     tag's message carries the freeze time.
  2. The object sha of the local ref equals the sha on the `refs/tags/<tag>` line
     of `git ls-remote --tags origin refs/tags/<tag>`. A network failure fails
     the check. This is the only request the checker sends. It is throttled to
     the D-63 policy in config/throttle.yml (the host's row, or `default`) and
     logged, one JSON line per request, to data/ops/git_remote_ledger.jsonl.
     data/ is gitignored, so the log cannot dirty the worktree check 4 reads.
     A remote that is a local path, as in the self-test, sends no request.
  3. `git merge-base --is-ancestor refs/tags/<tag> HEAD`. Same as absump.seal.
  4. `git status --porcelain` prints nothing. Same as absump.seal.
  5. The worktree quality/prereg.lock, the file absump.seal reads, must
       a. be byte for byte the lock committed at the tag;
       b. hold only shasum output lines, `<64 hex>  <path>`, no path twice;
       c. give, for every path, the sha256 of that path's blob at the tag;
       d. list PREREGISTRATION.md, every annex on the `annexes:` line of the
          tagged PREREGISTRATION.md, and every docs/prereg/*.md at the tag,
          which is the set ops/preregister.sh hashes.
     Stricter than absump.seal, which checks b, c and the root document only,
     so it accepts a lock that leaves an annex out.
  6. Two halves, both required.
       a. ABS_SEAL_UNLOCK is exactly "1" in the calling environment. This file
          reads the variable and never writes it (SOP rule 0.5.1).
       b. A line of DECISIONS.md carries an ISO date, the token
          `ABS_SEAL_UNLOCK=1` and the sha256 of quality/sealed_manifest.json as
          `shasum -a 256` prints it now. The line is absent from DECISIONS.md at
          the tag, and its first date falls between the tag's date and today,
          both taken in Europe/Madrid. absump.seal does not check this half.
     "The manifest sha256" is read as the sha256 of the manifest file. That value
     pins the whole manifest, gamepks_sha256 and any postseason block included,
     so it is the stricter of the two readings. A line that passes:

       - YYYY-MM-DD: `ABS_SEAL_UNLOCK=1` set in one shell. Manifest sha256 `<64 hex>`.

CROSS-CHECK. When the repository checked is this one and absump is importable,
the run asks absump.seal the same questions for clauses 1, 3, 4, 5 and the
environment half of 6, through its predicate functions. Clause 2 is not asked
twice, so a run sends at most one request. If this file passes a clause that
absump.seal fails, this file is weaker than the runtime gate and the run exits 3.
A clause this file fails and absump.seal passes is printed as a NOTE: it is one of
the places named above where this file is stricter.

EXIT CODES. 0 every selected precondition holds. 1 at least one does not.
2 usage error or unreadable config/seal.yml. 3 the cross-check failed.

SELF-TEST. `--selftest` builds throwaway git repositories under a temporary
directory, each with a bare local `origin`, in which all six preconditions hold.
The environment half of check 6 is satisfied through an in-memory mapping passed
to the check, never through os.environ. Each case then plants one violation and
asserts that exactly the expected checks fail. Every check is caught failing in
at least one case, and alone in at least one case. The throttle is tested with a
fake clock and a temporary ledger. No request is sent and nothing in this
repository is written.

Usage:
    uv run --locked python quality/check_prereg.py               the six, this repository
    uv run --locked python quality/check_prereg.py --only 1,2,3,5
    uv run --locked python quality/check_prereg.py --root PATH   another clone, no cross-check
    uv run --locked python quality/check_prereg.py --selftest

Idempotent: a run writes nothing but one ledger line per request sent. Resumable:
the ledger is the only state carried between runs, and it is appended under an
exclusive lock, so an interrupted run leaves at most one extra line behind.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
MADRID = ZoneInfo("Europe/Madrid")

REMOTE = "origin"
UNLOCK_ENV = "ABS_SEAL_UNLOCK"
UNLOCK_VALUE = "1"
UNLOCK_TOKEN = UNLOCK_ENV + "=" + UNLOCK_VALUE

CONFIG = "config/seal.yml"
THROTTLE = "config/throttle.yml"
PREREG_DOC = "PREREGISTRATION.md"
ANNEX_DIR = "docs/prereg"
LOCK = "quality/prereg.lock"
MANIFEST = "quality/sealed_manifest.json"
DECISIONS = "DECISIONS.md"
LEDGER = "data/ops/git_remote_ledger.jsonl"

GIT_TIMEOUT_S = 20.0
LS_REMOTE_TIMEOUT_S = 30.0
CHECKS = (1, 2, 3, 4, 5, 6)

NAMES = {
    1: "tag {tag} exists",
    2: "tag {tag} is pushed to origin",
    3: "tag {tag} is an ancestor of HEAD",
    4: "the worktree is clean",
    5: "quality/prereg.lock matches {tag}",
    6: "ABS_SEAL_UNLOCK=1 and its DECISIONS.md line",
}

LOCK_LINE = re.compile(r"^([0-9a-f]{64}) [ *](\S.*)$")
ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(UNLOCK_TOKEN) + r"(?![A-Za-z0-9_])")
TAG_LINE = re.compile(r"""^prereg_tag:\s*["']?([^"'#\s]+)["']?\s*(?:#.*)?$""", re.M)


# ---------------------------------------------------------------------- git
class Git:
    """Run git in one repository, never interactively, never raising."""

    def __init__(self, root: Path, extra_env: Mapping[str, str] | None = None) -> None:
        self.root = Path(root)
        env = dict(os.environ)
        env.update({"GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1", "LC_ALL": "C"})
        env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
        if extra_env:
            env.update(extra_env)
        self.env = env

    def run(self, *args: str, timeout: float = GIT_TIMEOUT_S) -> tuple[int, bytes, str]:
        try:
            done = subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                env=self.env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return 124, b"", f"git {args[0]} timed out after {timeout:.0f} s"
        except OSError as exc:
            return 127, b"", f"git could not run: {exc}"
        return done.returncode, done.stdout, done.stderr.decode("utf-8", "replace").strip()

    def text(self, *args: str, timeout: float = GIT_TIMEOUT_S) -> tuple[int, str]:
        code, raw, _ = self.run(*args, timeout=timeout)
        return code, raw.decode("utf-8", "replace").strip()

    def blob(self, rev: str, path: str) -> bytes | None:
        code, raw, _ = self.run("cat-file", "blob", f"{rev}:{path}")
        return raw if code == 0 else None


# ----------------------------------------------------------------- throttle
class BudgetSpent(RuntimeError):
    """The host's daily request cap is used up; no request was sent."""


def read_policy(path: Path) -> dict[str, dict[str, float]]:
    """The two per-host tables of config/throttle.yml, read without a YAML library.

    The file is a flat mapping with two nested tables. Only those two are read.
    """
    tables: dict[str, dict[str, float]] = {"min_interval_seconds": {}, "daily_request_budget": {}}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not raw[:1].isspace():
            key = line.split(":", 1)[0].strip()
            current = key if key in tables else None
            continue
        if current is not None:
            key, _, value = line.strip().partition(":")
            tables[current][key.strip()] = float(value.strip())
    for name, table in tables.items():
        if "default" not in table:
            raise ValueError(f"{path.name}: {name} has no default row")
    return tables


def remote_host(url: str) -> str | None:
    """The network host a remote URL names, or None for a local repository."""
    scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://(?:[^@/?#]*@)?(\[[^\]]*\]|[^:/?#]*)", url)
    if scheme:
        host = scheme.group(2).strip("[]").lower()
        return None if scheme.group(1).lower() == "file" or not host else host
    scp = re.match(r"^(?:[^@/\s]+@)?([^:/\s]+):(?!/)", url)
    if scp and not Path(url).exists():
        return scp.group(1)
    return None


@dataclasses.dataclass
class Throttle:
    """D-63 for the one request this file sends: a gap per host and a daily cap.

    Both are persisted in the ledger, so they hold across processes. The ledger
    is locked for the whole read, wait, request and append, so two checkers run
    at once queue behind each other instead of firing together.
    """

    ledger: Path
    policy: Callable[[str], tuple[float, int]]
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep

    @contextlib.contextmanager
    def slot(self, host: str, what: str) -> Iterator[dict[str, Any]]:
        interval, cap = self.policy(host)
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger, "a+", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.seek(0)
            rows = []
            for line in fh:
                with contextlib.suppress(ValueError):
                    row = json.loads(line)
                    if isinstance(row, dict) and row.get("host") == host:
                        rows.append(row)
            now = self.clock()
            day = dt.datetime.fromtimestamp(now, dt.UTC).date().isoformat()
            used = sum(1 for r in rows if r.get("utc_day") == day)
            if used >= cap:
                raise BudgetSpent(f"{used} of {cap} requests to {host} used on {day} UTC")
            last = max((float(r["epoch"]) for r in rows if "epoch" in r), default=None)
            waited = 0.0
            if last is not None and now - last < interval:
                waited = interval - (now - last)
                self.sleep(waited)
                now = self.clock()
            stamp = dt.datetime.fromtimestamp(now, dt.UTC)
            row = {
                "epoch": round(now, 3),
                "utc_day": stamp.date().isoformat(),
                "madrid": stamp.astimezone(MADRID).isoformat(timespec="seconds"),
                "host": host,
                "request": what,
                "waited_s": round(waited, 3),
                "by": "quality/check_prereg.py",
            }
            outcome: dict[str, Any] = {}
            try:
                yield outcome
            finally:
                row["exit"] = outcome.get("exit")
                fh.seek(0, os.SEEK_END)
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                fh.flush()


def project_throttle() -> Throttle:
    """The throttle for real runs: this repository's policy file and ledger."""

    def policy(host: str) -> tuple[float, int]:
        tables = read_policy(REPO_ROOT / THROTTLE)
        gap, cap = tables["min_interval_seconds"], tables["daily_request_budget"]
        return gap.get(host, gap["default"]), int(cap.get(host, cap["default"]))

    return Throttle(ledger=REPO_ROOT / LEDGER, policy=policy)


# ------------------------------------------------------------------- checks
@dataclasses.dataclass(frozen=True)
class Result:
    number: int
    name: str
    ok: bool
    detail: str


@dataclasses.dataclass
class Context:
    git: Git
    root: Path
    tag: str
    env: Mapping[str, str]
    today: dt.date
    throttle: Throttle | None = None

    @property
    def ref(self) -> str:
        return f"refs/tags/{self.tag}"

    def tag_sha(self) -> str | None:
        code, out = self.git.text("rev-parse", "--verify", "--quiet", self.ref)
        return out if code == 0 and out else None

    def tag_commit(self) -> str | None:
        code, out = self.git.text("rev-parse", "--verify", "--quiet", self.ref + "^{commit}")
        return out if code == 0 and out else None

    def tag_date(self) -> dt.date | None:
        code, out = self.git.text("for-each-ref", "--format=%(creatordate:unix)", self.ref)
        if code != 0 or not out.strip().isdigit():
            return None
        return dt.datetime.fromtimestamp(int(out.strip()), MADRID).date()


def _result(ctx: Context, n: int, ok: bool, detail: str) -> Result:
    return Result(n, NAMES[n].format(tag=ctx.tag), ok, detail)


def check_1_tag_exists(ctx: Context) -> Result:
    sha = ctx.tag_sha()
    if sha is None:
        return _result(ctx, 1, False, f"no ref {ctx.ref} in this repository")
    _, kind = ctx.git.text("cat-file", "-t", sha)
    if kind != "tag":
        return _result(
            ctx,
            1,
            False,
            f"{ctx.ref} is a lightweight tag on {sha[:12]}; ops/preregister.sh cuts an "
            "annotated tag, git tag -a, whose message carries the freeze time",
        )
    commit = ctx.tag_commit()
    if commit is None:
        return _result(ctx, 1, False, f"tag object {sha[:12]} does not point to a commit")
    return _result(ctx, 1, True, f"annotated tag object {sha[:12]} on commit {commit[:12]}")


def check_2_tag_pushed(ctx: Context) -> Result:
    local = ctx.tag_sha()
    if local is None:
        return _result(ctx, 2, False, "no local tag, so there is nothing to compare with origin")
    code, url = ctx.git.text("remote", "get-url", REMOTE)
    if code != 0 or not url:
        return _result(ctx, 2, False, "this repository has no remote named origin")
    what = f"git ls-remote --tags {REMOTE} {ctx.ref}"
    host = remote_host(url)
    try:
        if host is None:
            code, raw, err = ctx.git.run(
                "ls-remote", "--tags", REMOTE, ctx.ref, timeout=LS_REMOTE_TIMEOUT_S
            )
        elif ctx.throttle is None:
            return _result(
                ctx, 2, False, f"origin is on {host} and no throttle is set, so no request was sent"
            )
        else:
            with ctx.throttle.slot(host, what) as outcome:
                code, raw, err = ctx.git.run(
                    "ls-remote", "--tags", REMOTE, ctx.ref, timeout=LS_REMOTE_TIMEOUT_S
                )
                outcome["exit"] = code
    except BudgetSpent as exc:
        return _result(ctx, 2, False, f"no request sent: {exc} (D-63, config/throttle.yml)")
    except (OSError, ValueError, KeyError) as exc:
        return _result(ctx, 2, False, f"no request sent: the D-63 throttle could not run: {exc}")
    if code != 0:
        first = err.splitlines()[0][:160] if err else "no message"
        return _result(ctx, 2, False, f"{what} exited {code}: {first}")
    remote = None
    for line in raw.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ctx.ref:
            remote = parts[0]
    if remote is None:
        return _result(ctx, 2, False, f"origin has no {ctx.ref}; the local tag is {local[:12]}")
    if remote != local:
        return _result(
            ctx, 2, False, f"origin has {ctx.ref} at {remote[:12]}, the local tag is {local[:12]}"
        )
    return _result(
        ctx, 2, True, f"origin returns {remote[:12]} for {ctx.ref}, the local tag object"
    )


def check_3_tag_is_ancestor(ctx: Context) -> Result:
    commit = ctx.tag_commit()
    if commit is None:
        return _result(ctx, 3, False, "no tagged commit, so no ancestry can be shown")
    code, _ = ctx.git.text("rev-parse", "--verify", "--quiet", "HEAD")
    if code != 0:
        return _result(ctx, 3, False, "HEAD does not resolve to a commit")
    code, _, err = ctx.git.run("merge-base", "--is-ancestor", commit, "HEAD")
    if code == 0:
        return _result(ctx, 3, True, f"tagged commit {commit[:12]} is an ancestor of HEAD")
    if code == 1:
        return _result(ctx, 3, False, f"tagged commit {commit[:12]} is not an ancestor of HEAD")
    return _result(ctx, 3, False, f"git merge-base exited {code}: {err[:160]}")


def check_4_worktree_clean(ctx: Context) -> Result:
    code, out = ctx.git.text("status", "--porcelain")
    if code != 0:
        return _result(ctx, 4, False, f"git status exited {code}")
    if out:
        return _result(
            ctx,
            4,
            False,
            "git status --porcelain is not empty: a tracked change or an untracked file is present",
        )
    return _result(ctx, 4, True, "git status --porcelain prints nothing")


def _annexes_named(doc: bytes) -> list[str]:
    """The paths on the `annexes:` line of the root document's front matter."""
    text = doc.decode("utf-8", "replace")
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---\n", 4)
    front = text[4:end] if end != -1 else ""
    found = re.search(r"^annexes:\s*(.*)$", front, re.M)
    if not found:
        return []
    return [posixpath.normpath(p.strip()) for p in found.group(1).split(",") if p.strip()]


def _annex_dir_at(ctx: Context) -> list[str]:
    """Every docs/prereg/*.md blob at the tag, as the shell glob would list it."""
    code, out = ctx.git.text("ls-tree", ctx.ref, ANNEX_DIR + "/")
    if code != 0:
        return []
    names = []
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        name = posixpath.basename(path)
        if meta.split()[1:2] == ["blob"] and name.endswith(".md") and not name.startswith("."):
            names.append(path)
    return names


def check_5_lock_matches(ctx: Context) -> Result:
    if ctx.tag_commit() is None:
        return _result(ctx, 5, False, "no tagged commit, so the lock has no blobs to match")
    lock_file = ctx.root / LOCK
    if not lock_file.is_file():
        return _result(ctx, 5, False, f"{LOCK} is missing from the worktree")
    work = lock_file.read_bytes()
    problems: list[str] = []
    tagged = ctx.git.blob(ctx.ref, LOCK)
    if tagged is None:
        problems.append(f"{LOCK} is not in {ctx.tag}")
    elif tagged != work:
        problems.append(f"the worktree {LOCK} differs from the copy committed at {ctx.tag}")
    entries: list[tuple[str, str]] = []
    for i, line in enumerate(work.decode("utf-8", "replace").splitlines(), 1):
        if not line.strip():
            continue
        parsed = LOCK_LINE.match(line)
        if parsed is None:
            problems.append(f"line {i} is not shasum output")
            continue
        entries.append((parsed.group(1), posixpath.normpath(parsed.group(2))))
    if not entries:
        problems.append("the lock holds no hash line")
    paths = [p for _, p in entries]
    twice = sorted({p for p in paths if paths.count(p) > 1})
    if twice:
        problems.append("listed twice: " + ", ".join(twice))
    absent = sorted(p for _, p in entries if ctx.git.blob(ctx.ref, p) is None)
    if absent:
        problems.append(f"not in {ctx.tag}: " + ", ".join(absent))
    wrong = sorted(
        p
        for sha, p in entries
        if p not in absent and hashlib.sha256(ctx.git.blob(ctx.ref, p) or b"").hexdigest() != sha
    )
    if wrong:
        problems.append(f"sha256 differs from the blob at {ctx.tag}: " + ", ".join(wrong))
    doc = ctx.git.blob(ctx.ref, PREREG_DOC)
    if doc is None:
        problems.append(f"{PREREG_DOC} is not in {ctx.tag}")
    named = _annexes_named(doc or b"")
    globbed = _annex_dir_at(ctx)
    required = {PREREG_DOC, *named, *globbed}
    missing = sorted(required - set(paths))
    if missing:
        problems.append("the lock leaves out " + ", ".join(missing))
    if problems:
        return _result(ctx, 5, False, "; ".join(problems))
    return _result(
        ctx,
        5,
        True,
        f"{len(entries)} files, each sha256 equal to its blob at {ctx.tag}; covers {PREREG_DOC}, "
        f"the {len(named)} annexes it names and the {len(globbed)} {ANNEX_DIR}/*.md files",
    )


def check_6_owner_unseal(ctx: Context) -> Result:
    problems: list[str] = []
    value = ctx.env.get(UNLOCK_ENV)
    if value is None:
        problems.append(f"{UNLOCK_ENV} is not set in this environment")
    elif value != UNLOCK_VALUE:
        problems.append(f"{UNLOCK_ENV} is set to {value[:20]!r}, not {UNLOCK_VALUE!r}")
    manifest = ctx.root / MANIFEST
    msha = hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None
    if msha is None:
        problems.append(f"{MANIFEST} is missing, so there is no sha256 to record")
    decisions = ctx.root / DECISIONS
    lines = (
        decisions.read_text(encoding="utf-8", errors="replace").splitlines()
        if decisions.is_file()
        else None
    )
    if lines is None:
        problems.append(f"{DECISIONS} is missing")
    tag_date = ctx.tag_date() if ctx.tag_sha() else None
    if tag_date is None:
        problems.append(f"no tag {ctx.tag}, so no line can be shown to postdate it")
    at_tag_blob = ctx.git.blob(ctx.ref, DECISIONS) if tag_date else None
    at_tag = {ln.rstrip() for ln in (at_tag_blob or b"").decode("utf-8", "replace").splitlines()}
    found: tuple[int, dt.date] | None = None
    last_reasons: list[str] = []
    candidates = [(i, ln) for i, ln in enumerate(lines or [], 1) if TOKEN_RE.search(ln)]
    for i, line in candidates:
        reasons: list[str] = []
        day = None
        for y, m, d in ISO_DATE.findall(line):
            with contextlib.suppress(ValueError):
                day = dt.date(int(y), int(m), int(d))
                break
        if day is None:
            reasons.append("carries no ISO date")
        elif tag_date is not None and day < tag_date:
            reasons.append(
                f"is dated {day.isoformat()}, before the tag date {tag_date.isoformat()}"
            )
        elif day > ctx.today:
            reasons.append(
                f"is dated {day.isoformat()}, after today {ctx.today.isoformat()} (Madrid)"
            )
        if msha is not None and not re.search(
            r"(?<![0-9a-f])" + msha + r"(?![0-9a-f])", line.lower()
        ):
            reasons.append(f"does not carry the manifest sha256 {msha}")
        if line.rstrip() in at_tag:
            reasons.append(
                f"was already in {DECISIONS} at {ctx.tag}, so it was not appended after it"
            )
        if not reasons and day is not None:
            found = (i, day)
        last_reasons = [f"line {i} " + r for r in reasons]
    if lines is not None and msha is not None and found is None:
        if not candidates:
            problems.append(
                f"{DECISIONS} has no line carrying {UNLOCK_TOKEN}; at the unseal the owner appends "
                f"one such as '- YYYY-MM-DD: `{UNLOCK_TOKEN}` set in one shell. "
                f"Manifest sha256 `{msha}`.'"
            )
        else:
            problems.extend(last_reasons)
    if problems:
        return _result(ctx, 6, False, "; ".join(problems))
    assert found is not None and msha is not None
    return _result(
        ctx,
        6,
        True,
        f"{UNLOCK_TOKEN} in this environment; {DECISIONS} line {found[0]}, dated "
        f"{found[1].isoformat()}, records it with manifest sha256 {msha[:12]}",
    )


CHECK_FUNCS: dict[int, Callable[[Context], Result]] = {
    1: check_1_tag_exists,
    2: check_2_tag_pushed,
    3: check_3_tag_is_ancestor,
    4: check_4_worktree_clean,
    5: check_5_lock_matches,
    6: check_6_owner_unseal,
}


def run_checks(ctx: Context, only: Sequence[int] = CHECKS) -> list[Result]:
    """Every selected check, each run whatever the others found."""
    return [CHECK_FUNCS[n](ctx) for n in only]


def read_tag(root: Path) -> str:
    text = (root / CONFIG).read_text(encoding="utf-8")
    found = TAG_LINE.search(text)
    if not found:
        raise ValueError(f"{CONFIG} has no prereg_tag line")
    return found.group(1)


def today_madrid() -> dt.date:
    return dt.datetime.now(MADRID).date()


# -------------------------------------------------------------- cross-check
def cross_check(results: list[Result]) -> tuple[list[str], bool]:
    """Compare with absump.seal on this repository. False when this file is weaker."""
    try:
        from absump import seal
    except Exception as exc:
        return [
            f"CROSS-CHECK absump.seal: not run, absump is not importable here "
            f"({type(exc).__name__}); run under uv run --locked"
        ], True
    tag = seal._prereg_tag()
    theirs: dict[int, bool] = {
        1: seal._tag_exists(tag),
        3: seal._is_ancestor(tag, "HEAD"),
        4: seal._worktree_clean(),
        5: seal._prereg_hash_matches(),
        6: os.environ.get(seal.UNLOCK_ENV) == "1",
    }
    mine = {r.number: r.ok for r in results}
    asked = [n for n in sorted(theirs) if n in mine]
    weaker = [n for n in asked if mine[n] and not theirs[n]]
    stricter = [n for n in asked if theirs[n] and not mine[n]]
    lines: list[str] = []
    label = ", ".join("6 (environment half)" if n == 6 else str(n) for n in asked)
    if weaker:
        lines.append(
            "CROSS-CHECK FAIL: this checker passes clause(s) "
            + ", ".join(map(str, weaker))
            + " and absump.seal fails them, so this checker is weaker than the runtime gate"
        )
    else:
        lines.append(
            f"CROSS-CHECK absump.seal: consistent on clauses {label or 'none selected'}; "
            "no clause passes here that absump.seal fails. Clause 2 is not asked twice, "
            "so a run sends at most one request"
        )
    for n in stricter:
        lines.append(
            f"NOTE clause {n}: absump.seal passes it and this checker fails it; "
            "the header of this file says where this checker is stricter"
        )
    return lines, not weaker


# --------------------------------------------------------------------- main
def parse_only(value: str) -> list[int]:
    if not value:
        return list(CHECKS)
    picked = sorted({int(x) for x in value.split(",") if x.strip()})
    if not picked or any(n not in CHECKS for n in picked):
        raise ValueError(value)
    return picked


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quality/check_prereg.py",
        description="SOP W7.8: the six preconditions of SOP section 2.4.",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="plant each violation and assert it is caught"
    )
    parser.add_argument("--only", default="", help="comma-separated check numbers, 1 to 6")
    parser.add_argument("--root", default=None, help="the repository to check; default this one")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        only = parse_only(args.only)
    except ValueError:
        print(f"check_prereg: --only takes numbers from 1 to 6, got {args.only!r}", file=sys.stderr)
        return 2
    root = Path(args.root).resolve() if args.root else REPO_ROOT
    try:
        tag = read_tag(root)
    except (OSError, ValueError) as exc:
        print(f"PREREG CHECK ERROR: {exc}")
        return 2
    ctx = Context(
        git=Git(root),
        root=root,
        tag=tag,
        env=os.environ if env is None else env,
        today=today_madrid(),
        throttle=project_throttle(),
    )
    results = run_checks(ctx, only)
    for r in results:
        print(f"PREREG {r.number}/6 {'PASS' if r.ok else 'FAIL'} {r.name}: {r.detail}")
    failed = [r.number for r in results if not r.ok]
    skipped = [n for n in CHECKS if n not in only]
    noun = "selected preconditions" if skipped else "preconditions"
    tail = f"; not checked: {', '.join(map(str, skipped))}" if skipped else ""
    if failed:
        print(
            f"PREREG CHECK FAILED: {len(failed)} of {len(only)} {noun} do not hold "
            f"({', '.join(map(str, failed))}){tail}"
        )
    else:
        print(f"PREREG CHECK OK: {len(only)} of {len(only)} {noun} hold{tail}")
    code = 1 if failed else 0
    if root == REPO_ROOT and env is None:
        lines, consistent = cross_check(results)
        for line in lines:
            print(line)
        if not consistent:
            code = 3
    return code


# ----------------------------------------------------------------- selftest
_SELFTEST_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "check_prereg selftest",
    "GIT_AUTHOR_EMAIL": "selftest",
    "GIT_COMMITTER_NAME": "check_prereg selftest",
    "GIT_COMMITTER_EMAIL": "selftest",
}
_TAG = "prereg-v1"


class SetupError(RuntimeError):
    pass


class Fixture:
    """A repository in which all six preconditions hold, with a bare local origin."""

    def __init__(
        self,
        base: Path,
        *,
        lock_edit: Callable[[list[str]], list[str]] | None = None,
        annex_edit_after_lock: bool = False,
        line_at_tag: bool = False,
        lightweight: bool = False,
    ) -> None:
        self.base = base
        self.work = base / "work"
        self.origin = base / "origin.git"
        self.work.mkdir()
        self.git = Git(self.work, _SELFTEST_GIT_ENV)
        self.env: dict[str, str] = {UNLOCK_ENV: UNLOCK_VALUE}
        self.sh("init", "-q", "--bare", "-b", "main", str(self.origin))
        self.sh("init", "-q", "-b", "main", ".")
        self.sh("remote", "add", REMOTE, str(self.origin))
        self.write(CONFIG, f'prereg_tag: "{_TAG}"\n')
        self.write(
            PREREG_DOC,
            "---\ntitle: selftest\nversion: 1.0\ntag: prereg-v1\n"
            "annexes: docs/prereg/ch1.md, docs/prereg/ch2.md\n---\n\n# Plan\n\nOne rule.\n",
        )
        self.write(f"{ANNEX_DIR}/ch1.md", "# Annex 1\n\nChapter 1 rules.\n")
        self.write(f"{ANNEX_DIR}/ch2.md", "# Annex 2\n\nChapter 2 rules.\n")
        self.write(f"{ANNEX_DIR}/SEAL.md", "# Seal log\n")
        self.write(MANIFEST, '{"regular_gamepks": [101, 102, 103]}\n')
        self.write(DECISIONS, "# Decisions\n\n- Selftest baseline.\n")
        self.write("README.md", "# Selftest\n")
        annexes = sorted(f"{ANNEX_DIR}/{p.name}" for p in (self.work / ANNEX_DIR).glob("*.md"))
        hashed = [PREREG_DOC, *annexes]
        lines = [f"{hashlib.sha256((self.work / p).read_bytes()).hexdigest()}  {p}" for p in hashed]
        if lock_edit is not None:
            lines = lock_edit(lines)
        self.write(LOCK, "".join(line + "\n" for line in lines))
        if annex_edit_after_lock:
            self.append(f"{ANNEX_DIR}/ch2.md", "Edited after the lock was written.\n")
        if line_at_tag:
            self.append(DECISIONS, self.unseal_line())
        self.commit("plan")
        if lightweight:
            self.sh("tag", _TAG)
        else:
            self.sh("tag", "-a", _TAG, "-m", "selftest freeze")
        self.sh("push", "-q", REMOTE, "main", f"refs/tags/{_TAG}")
        if not line_at_tag:
            self.append(DECISIONS, self.unseal_line())
            self.commit("record the unseal")

    def sh(self, *args: str) -> str:
        code, raw, err = self.git.run(*args)
        if code != 0:
            raise SetupError(f"git {' '.join(args[:3])} exited {code}: {err[:200]}")
        return raw.decode("utf-8", "replace").strip()

    def write(self, rel: str, text: str) -> None:
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def append(self, rel: str, text: str) -> None:
        with open(self.work / rel, "a", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, message: str) -> None:
        self.sh("add", "-A")
        self.sh("commit", "-q", "-m", message)

    def manifest_sha(self) -> str:
        return hashlib.sha256((self.work / MANIFEST).read_bytes()).hexdigest()

    def unseal_line(
        self, day: dt.date | None = None, sha: str | None = None, token: str = UNLOCK_TOKEN
    ) -> str:
        stamp = (day or today_madrid()).isoformat()
        sha = sha or self.manifest_sha()
        return f"- {stamp}: `{token}` set in one shell. Manifest sha256 `{sha}`.\n"

    def replace_last_decision(self, line: str) -> None:
        path = self.work / DECISIONS
        kept = path.read_text(encoding="utf-8").splitlines(keepends=True)[:-1]
        path.write_text("".join(kept) + line, encoding="utf-8")
        self.commit("rewrite the unseal line")

    def context(self, throttle: Throttle | None = None) -> Context:
        return Context(
            git=self.git,
            root=self.work,
            tag=read_tag(self.work),
            env=self.env,
            today=today_madrid(),
            throttle=throttle,
        )


def _drop(name: str) -> Callable[[list[str]], list[str]]:
    return lambda lines: [ln for ln in lines if not ln.endswith("  " + name)]


def _plant_remote_other_object(fx: Fixture) -> None:
    fx.sh("tag", "-a", "decoy", "-m", "another tag object", "HEAD~1")
    fx.sh("push", "-q", "-f", REMOTE, f"refs/tags/decoy:refs/tags/{_TAG}")
    fx.sh("tag", "-d", "decoy")


def _plant_orphan_head(fx: Fixture) -> None:
    fx.sh("checkout", "-q", "--orphan", "detour")
    fx.sh("commit", "-q", "-m", "same files, no history")


def _plant_reordered_lock(fx: Fixture) -> None:
    path = fx.work / LOCK
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(reversed(lines)), encoding="utf-8")
    fx.commit("reorder the lock after the tag")


def _plant_budget_spent(fx: Fixture, ledger: Path) -> Throttle:
    """origin on a network host whose daily cap is already spent: no request may leave."""
    fx.sh("remote", "set-url", REMOTE, "https://example.invalid/abs-umpires.git")
    now = time.time()
    day = dt.datetime.fromtimestamp(now, dt.UTC).date().isoformat()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps({"epoch": now - 3600, "utc_day": day, "host": "example.invalid", "exit": 0})
        + "\n",
        encoding="utf-8",
    )
    return Throttle(ledger=ledger, policy=lambda host: (0.0, 1))


@dataclasses.dataclass
class Case:
    cid: str
    target: int
    title: str
    expect: frozenset[int]
    build: dict[str, Any] = dataclasses.field(default_factory=dict)
    plant: Callable[[Fixture], Any] | None = None
    env: dict[str, str] | None = None


def _cases() -> list[Case]:
    def f(*n: int) -> frozenset[int]:
        return frozenset(n)

    def after_tag(fx: Fixture) -> dt.date:
        found = fx.context().tag_date()
        assert found is not None
        return found

    return [
        Case("base", 0, "all six hold", f()),
        Case(
            "1a",
            1,
            "tag deleted locally",
            f(1, 2, 3, 5, 6),
            plant=lambda fx: fx.sh("tag", "-d", _TAG),
        ),
        Case("1b", 1, "lightweight tag, pushed", f(1), build={"lightweight": True}),
        Case(
            "2a",
            2,
            "tag deleted on origin",
            f(2),
            plant=lambda fx: fx.sh("push", "-q", REMOTE, f":refs/tags/{_TAG}"),
        ),
        Case(
            "2b",
            2,
            "origin holds another tag object under the name",
            f(2),
            plant=_plant_remote_other_object,
        ),
        Case(
            "2c",
            2,
            "no remote named origin",
            f(2),
            plant=lambda fx: fx.sh("remote", "remove", REMOTE),
        ),
        Case("2d", 2, "origin on a network host, D-63 budget spent", f(2)),
        Case(
            "3a", 3, "HEAD on an orphan branch with the same files", f(3), plant=_plant_orphan_head
        ),
        Case("4a", 4, "untracked file", f(4), plant=lambda fx: fx.write("scratch.txt", "x\n")),
        Case(
            "4b",
            4,
            "modified tracked file",
            f(4),
            plant=lambda fx: fx.append("README.md", "more\n"),
        ),
        Case(
            "4c",
            4,
            "staged, uncommitted change",
            f(4),
            plant=lambda fx: (fx.append("README.md", "staged\n"), fx.sh("add", "README.md")),
        ),
        Case(
            "5a",
            5,
            "annex edited after the lock was hashed",
            f(5),
            build={"annex_edit_after_lock": True},
        ),
        Case(
            "5b",
            5,
            "lock leaves out a named annex",
            f(5),
            build={"lock_edit": _drop("docs/prereg/ch2.md")},
        ),
        Case(
            "5c",
            5,
            "lock leaves out docs/prereg/SEAL.md",
            f(5),
            build={"lock_edit": _drop("docs/prereg/SEAL.md")},
        ),
        Case(
            "5d",
            5,
            "lock leaves out PREREGISTRATION.md",
            f(5),
            build={"lock_edit": _drop(PREREG_DOC)},
        ),
        Case("5e", 5, "lock lines reordered after the tag", f(5), plant=_plant_reordered_lock),
        Case(
            "5f",
            5,
            "lock carries a comment line",
            f(5),
            build={"lock_edit": lambda lines: ["# generated", *lines]},
        ),
        Case("6a", 6, "ABS_SEAL_UNLOCK unset", f(6), env={}),
        Case("6b", 6, "ABS_SEAL_UNLOCK=true", f(6), env={UNLOCK_ENV: "true"}),
        Case(
            "6c",
            6,
            "line without the manifest sha256",
            f(6),
            plant=lambda fx: fx.replace_last_decision(fx.unseal_line(sha="0" * 64)),
        ),
        Case(
            "6d",
            6,
            "manifest changed after the line",
            f(6),
            plant=lambda fx: (
                fx.write(MANIFEST, '{"regular_gamepks": [101, 102, 103, 104]}\n'),
                fx.commit("change the manifest"),
            ),
        ),
        Case(
            "6e",
            6,
            "line with no date",
            f(6),
            plant=lambda fx: fx.replace_last_decision(
                fx.unseal_line().replace(today_madrid().isoformat(), "today")
            ),
        ),
        Case("6f", 6, "line already present at the tag", f(6), build={"line_at_tag": True}),
        Case(
            "6g",
            6,
            "line dated before the tag",
            f(6),
            plant=lambda fx: fx.replace_last_decision(
                fx.unseal_line(day=after_tag(fx) - dt.timedelta(days=1))
            ),
        ),
        Case(
            "6h",
            6,
            "line dated after today",
            f(6),
            plant=lambda fx: fx.replace_last_decision(
                fx.unseal_line(day=today_madrid() + dt.timedelta(days=1))
            ),
        ),
        Case(
            "6i",
            6,
            "line without ABS_SEAL_UNLOCK=1",
            f(6),
            plant=lambda fx: fx.replace_last_decision(fx.unseal_line(token="ABS_SEAL_UNLOCK=10")),
        ),
        Case(
            "6j",
            6,
            "no DECISIONS.md line at all",
            f(6),
            plant=lambda fx: fx.replace_last_decision("- Nothing recorded.\n"),
        ),
    ]


def _throttle_cases() -> list[tuple[str, bool, str]]:
    """The D-63 throttle, with a fake clock and a temporary ledger. No request is sent."""
    out: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="check_prereg.") as tmp:
        ledger = Path(tmp) / "ledger.jsonl"
        clock = {"t": 1000.0}
        slept: list[float] = []

        def fake_sleep(s: float) -> None:
            slept.append(s)
            clock["t"] += s

        th = Throttle(
            ledger=ledger, policy=lambda host: (10.0, 2), clock=lambda: clock["t"], sleep=fake_sleep
        )
        with th.slot("h.invalid", "one") as o:
            o["exit"] = 0
        rows = ledger.read_text(encoding="utf-8").splitlines()
        out.append(("T1", not slept and len(rows) == 1, "first request waits 0 s and is logged"))
        clock["t"] += 3.0
        with th.slot("h.invalid", "two") as o:
            o["exit"] = 0
        rows = ledger.read_text(encoding="utf-8").splitlines()
        out.append(
            (
                "T2",
                slept == [7.0] and len(rows) == 2,
                "second request 3 s later waits 7 s of the 10 s gap",
            )
        )
        clock["t"] += 1.0
        other = True
        try:
            with th.slot("other.invalid", "three") as o:
                o["exit"] = 0
        except BudgetSpent:
            other = False
        out.append(
            (
                "T3",
                other and slept == [7.0],
                "gap and cap are per host: another host 1 s later neither waits nor is refused",
            )
        )
        clock["t"] += 60.0
        refused = False
        try:
            with th.slot("h.invalid", "four"):
                pass
        except BudgetSpent:
            refused = True
        rows = ledger.read_text(encoding="utf-8").splitlines()
        out.append(
            (
                "T4",
                refused and len(rows) == 3 and slept == [7.0],
                "a third request to one host over a cap of 2 is refused and not logged",
            )
        )
    hosts = {
        "https://github.com/hpagni/abs-umpires.git": "github.com",
        "git@github.com:hpagni/abs-umpires.git": "github.com",
        "ssh://git@github.com/hpagni/abs-umpires.git": "github.com",
        "file:///srv/origin.git": None,
        "/srv/origin.git": None,
    }
    bad = [u for u, h in hosts.items() if remote_host(u) != h]
    out.append(
        (
            "T5",
            not bad,
            f"remote_host reads {len(hosts)} URL shapes" + (f"; wrong: {bad}" if bad else ""),
        )
    )
    try:
        tables = read_policy(REPO_ROOT / THROTTLE)
        ok = all("default" in t for t in tables.values())
    except (OSError, ValueError):
        ok = False
    out.append(("T6", ok, "config/throttle.yml gives both D-63 tables a default row"))
    return out


def _cli_cases() -> list[tuple[str, bool, str]]:
    """main() end to end on a fixture: --root, --only and the exit codes."""
    out: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="check_prereg.") as tmp:
        base = Path(tmp) / "a"
        base.mkdir()
        fx = Fixture(base)
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            full = main(["--root", str(fx.work)], env=fx.env)
            five = main(["--root", str(fx.work), "--only", "1,2,3,4,5"], env={})
            six = main(["--root", str(fx.work), "--only", "6"], env={})
            bad = main(["--root", str(fx.work), "--only", "7"], env={})
        out.append(("C1", full == 0, "main --root on the baseline exits 0"))
        out.append(
            (
                "C2",
                five == 0 and six == 1,
                "--only 1,2,3,4,5 exits 0 and --only 6 exits 1 with no variable",
            )
        )
        out.append(("C3", bad == 2, "--only 7 exits 2"))
        text = sink.getvalue()
        out.append(
            (
                "C4",
                "PREREG CHECK OK: 6 of 6 preconditions hold" in text
                and "not checked: 6" in text
                and "CROSS-CHECK" not in text,
                "the summary names what was not checked; no cross-check on another root",
            )
        )
    return out


def selftest() -> int:
    cases = _cases()
    total = len(cases) + 6 + 4
    failures: list[str] = []
    passed: list[Case] = []
    i = 0
    for case in cases:
        i += 1
        with tempfile.TemporaryDirectory(prefix="check_prereg.") as tmp:
            try:
                fx = Fixture(Path(tmp), **case.build)
                throttle = None
                if case.cid == "2d":
                    ledger = Path(tmp) / "ledger.jsonl"
                    throttle = _plant_budget_spent(fx, ledger)
                    before = ledger.read_bytes()
                elif case.plant is not None:
                    case.plant(fx)
                if case.env is not None:
                    fx.env = case.env
            except (SetupError, OSError, AssertionError) as exc:
                failures.append(f"{case.cid}: setup failed: {exc}")
                print(f"selftest {i:2d}/{total} FAIL {case.cid} {case.title}: setup failed")
                continue
            try:
                results = run_checks(fx.context(throttle))
            except Exception as exc:
                failures.append(f"{case.cid}: a check raised {type(exc).__name__}: {exc}")
                print(
                    f"selftest {i:2d}/{total} FAIL {case.cid} {case.title}: "
                    f"a check raised {type(exc).__name__}"
                )
                continue
            failed = frozenset(r.number for r in results if not r.ok)
            ok = failed == case.expect
            if case.cid == "2d":
                ok = ok and ledger.read_bytes() == before and "no request sent" in results[1].detail
            if case.target:
                ok = ok and bool(results[case.target - 1].detail)
            shown = ", ".join(map(str, sorted(failed))) or "none"
            print(
                f"selftest {i:2d}/{total} {'ok  ' if ok else 'FAIL'} {case.cid} "
                f"{case.title}: fails {shown}"
            )
            if ok:
                passed.append(case)
            else:
                want = ", ".join(map(str, sorted(case.expect))) or "none"
                failures.append(f"{case.cid}: expected {want}, got {shown}")
                for r in results:
                    print(f"    {r.number}/6 {'PASS' if r.ok else 'FAIL'} {r.detail}")
    extra: list[tuple[str, bool, str]] = []
    for group, size in ((_throttle_cases, 6), (_cli_cases, 4)):
        try:
            extra += group()
        except Exception as exc:
            extra += [
                (f"{group.__name__}[{k}]", False, f"raised {type(exc).__name__}: {exc}")
                for k in range(size)
            ]
    for cid, ok, title in extra:
        i += 1
        print(f"selftest {i:2d}/{total} {'ok  ' if ok else 'FAIL'} {cid} {title}")
        if not ok:
            failures.append(f"{cid}: {title}")
    caught = {c.target for c in passed if c.target}
    alone = {c.target for c in passed if c.expect == frozenset({c.target})}
    if caught != set(CHECKS) or alone != set(CHECKS):
        failures.append(
            f"coverage: caught {sorted(caught)}, caught alone {sorted(alone)}; "
            "every check 1 to 6 needs both"
        )
    if i != total:
        failures.append(f"ran {i} cases, expected {total}")
    if failures:
        for line in failures:
            print(f"SELFTEST FAIL {line}")
        print(f"check_prereg selftest: FAILED, {len(failures)} problem(s)")
        return 1
    n_plants = len([c for c in cases if c.target])
    print(
        f"check_prereg selftest: {total} of {total} cases pass. {n_plants} planted violations; "
        "each of checks 1 to 6 caught its own and failed alone in at least one case; "
        "the D-63 throttle waits, caps and logs; the command line exits 0, 1 and 2 as documented"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
