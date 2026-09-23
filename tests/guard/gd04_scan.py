"""GD-04 / GD-05, the static scan engine. SOP step W9.7, layer 3.

The scan walks the whole repository -- every file git ships, plus every file
that sits in a code or notebook directory the SOP names, whether git tracks it
or not -- and fails on four behaviours, not four spellings.

WHAT IT WALKS.  The union of two listings:

  * `git ls-files --cached --others --exclude-standard`, the whole repository,
    which is what SOP line 1679 asks for; and
  * a filesystem walk of `R/`, `src/`, `dbt/`, `notebooks/`, `scripts/`,
    `ops/`, `app/`, `tests/`, `tools/`, `sql/`, `config/`, `quality/sql/` and
    `contracts/`, which adds anything a `.gitignore` line would otherwise hide
    inside a directory that executes.

WHAT IT NEVER WALKS.  `quality/receipts/` and `logs/` are excluded by prefix.
Those two directories hold this guard's own transcripts, and a transcript quotes
the failure text verbatim; without the exclusion every red-team run wrote the
file that made the next run red, which is exactly what happened in phase 01.
Excluding them is safe because neither directory is importable, runnable or
compiled: nothing under either one can read a row.  No other
directory is excluded, and none that executes ever is.

WHAT IT FAILS ON.

  1. the routing column compared to the held-out label: as a quoted literal, as
     a label assembled from fragments or held in a variable, or as the
     complement of the open label, which selects exactly the held-out rows.
  2. the held-out pitch view, by name, by assembled name, or through a variable
     that was built from one.
  3. a read of a raw fact table that the enclosing statement does not restrict
     to the open label.  Statement-scoped and comment-blind: a comment cannot
     forgive a read, and a formatter that breaks `FROM` and the table name onto
     two lines does not hide one.
  4. a literal date comparison that can select a day on or after the boundary
     day in `config/seal.yml` -- any such day, not only the boundary itself.

WHAT IS ALLOWLISTED.  Exactly two paths, by exact path: `src/absump/seal.py`
and `quality/sql/analysis_set.sql`.  GD-05's count is two.

Every banned token here is assembled at import time, so this file carries none
of the literals it bans and does not need to be allowlisted into silence.

Run it directly for a precise, machine-readable answer:

    uv run python tests/guard/gd04_scan.py             # the whole repository
    uv run python tests/guard/gd04_scan.py --path P    # one path only

Exit 0 when clean, 1 when it finds something, 2 when it cannot run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "seal.yml"

ALLOWLIST: frozenset[str] = frozenset(
    {
        "src/absump/seal.py",
        "quality/sql/analysis_set.sql",
    }
)

# The R1 directory list, kept empty on purpose. A test asserts it is empty.
SCANNED_DIR_SKIPS: frozenset[str] = frozenset()

# Directories that execute. Walked from the filesystem as well as from git, so
# a .gitignore line inside one of them cannot hide a read.
WALKED_ROOTS: tuple[str, ...] = (
    "R",
    "src",
    "dbt",
    "notebooks",
    "scripts",
    "ops",
    "app",
    "tests",
    "tools",
    "sql",
    "config",
    "contracts",
    "quality/sql",
)

# Excluded by prefix. Evidence only, and exactly two directories: a receipt and
# a gate log quote this guard's own failure text verbatim, so scanning them made
# every red-team run write the file that turned the next run red. Neither
# directory is importable, runnable or compiled, so excluding them removes no
# read. Nothing that executes is excluded, and a test asserts that.
EXCLUDED_PREFIXES: tuple[str, ...] = (
    "quality/receipts/",
    "logs/",
)

# Never descended into during the filesystem walk.
SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".ipynb_checkpoints",
        ".venv",
        "node_modules",
        "target",
        "library",
        "renv.cache",
    }
)

NON_CODE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".md",
        ".txt",
        ".rst",
        ".lock",
        ".csv",
        ".tsv",
        ".parquet",
        ".rds",
        ".zst",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".duckdb",
        ".xlsx",
        ".p8",
        ".pyc",
        ".patch",
        ".diff",
    }
)

# Read ceiling, to bound memory on a pathological file. It is not a skip: a
# file longer than this is still scanned, up to this many bytes. Phase 01's
# largest scanned file is far under it.
MAX_READ_BYTES = 64_000_000

# A base64 blob -- a notebook's embedded plot -- carries no read, and a long
# unbroken run of it turns every later regex into a crawl. The run is redacted
# in place, by shape, never by file size: the same notebook is scanned at
# 330 bytes and at 2.1 MB, and the source line beside the blob is scanned with
# its real line number intact.
_BLOB_MIN = 512
_BLOB = re.compile(r"[A-Za-z0-9+/=]{" + str(_BLOB_MIN) + r",}")

# Taint only reads assignments, which are short and start a line. Anchoring the
# pattern and capping the length keeps a minified line from costing quadratic time.
_TAINT_MAX_LINE = 4000


# ----------------------------------------------------------------- the tokens
# Assembled from ordinals, so this file carries the strings it bans neither
# whole nor as fragments that the seam-joiner below would close back up. If the
# label were written here in two quoted pieces, this file would fail its own
# rule 1, and allowlisting it would make GD-05's count three.
# The known limit: a scan that must not flag itself cannot also ban ordinal
# arithmetic. An author who spells the label with chr() evades rule 1, and the
# receipt says so.
_HELD = "".join(chr(code) for code in (115, 101, 97, 108, 101, 100))
_VIEW = "v_" + "pitch_" + _HELD
_FACT = "".join(chr(code) for code in (102, 99, 116, 95))
_QUOTED_HELD = rf"['\"]{_HELD}['\"]"

# A seam is a closing quote, an optional concatenation operator or comma, and
# an opening quote. Removing seams turns paste0("seal", "ed") into
# paste0("sealed") and "seal" + "ed" into "sealed", which is how a label spelled
# in two pieces stops being invisible.
_SEAM = re.compile(r"['\"]\s*(?:,|\+|\.|&|\|\|)?\s*['\"]")

# 1. The routing column meeting the held-out label on one line.
RULE_ANALYSIS_SET = re.compile(
    rf"analysis_set\b[^\n]{{0,60}}{_QUOTED_HELD}|{_QUOTED_HELD}[^\n]{{0,60}}\banalysis_set\b"
)

# 1b. The complement. `!= 'open'` selects exactly the held-out rows and never
#     writes the held-out label. An author told "only the open set is allowed"
#     writes this.
RULE_COMPLEMENT = re.compile(
    r"analysis_set\b\s*(?:!=|<>|~=|NOT\s+IN|not\s+in)\s*\(?\s*['\"]open['\"]"
    r"|analysis_set\b[^\n]{0,20}\bNOT\s+IN\b[^\n]{0,20}['\"]open['\"]",
    re.IGNORECASE,
)

# 2. The held-out view by name.
RULE_VIEW = re.compile(rf"\b{_VIEW}\b")

# 2b. The view name built by interpolation or concatenation from a variable.
_VIEW_STEM = re.compile(r"v_pitch_[\"']?\s*[,+]?\s*\{?\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}?")

# 3. A read of a raw fact table, spanning newlines.
RULE_RAW_FACT = re.compile(
    rf"(?:\bFROM\b|\bJOIN\b|\bref\s*\(|\bsource\s*\(|read_parquet|\.table\s*\()"
    rf"[^;]{{0,120}}?\b{_FACT}[a-z0-9_]+\b",
    re.IGNORECASE | re.DOTALL,
)

# The only thing that forgives rule 3: an equality, or an IN, against the open
# label. `!= 'open'` is not a restriction to the open set, so it is not here.
QUALIFIES_OPEN = re.compile(
    r"analysis_set\b\s*(?:=|==|IN|in)\s*\(?\s*['\"]open['\"]",
    re.IGNORECASE,
)

# A date literal in a comparison, either ISO or a three-integer constructor.
_ISO = r"(\d{4})-(\d{2})-(\d{2})"
RULE_DATE_CMP = re.compile(
    rf"(>=|<=|>|<|=|\bBETWEEN\b|\bAND\b)\s*"
    rf"(?:DATE\s+|TIMESTAMP\s+|as\.Date\s*\(\s*|pl\.date\s*\(\s*|date\s*\(\s*|datetime\s*\(\s*)?"
    rf"['\"]?{_ISO}",
    re.IGNORECASE,
)
RULE_DATE_CTOR = re.compile(
    r"(>=|<=|>|<|=)\s*[A-Za-z_.]*[Dd]ate(?:time)?\s*\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)"
)

# The complement operators, in ordinal form for the same reason as the tokens:
# the tests import them so that the test file can spell an evasion without
# failing its own rule 1.
_COMPLEMENT_OPS: tuple[str, ...] = tuple(
    "".join(chr(code) for code in codes) for codes in ((33, 61), (60, 62), (78, 79, 84, 32, 73, 78))
)

_ASSIGN = re.compile(
    r"^[ \t\"',]*(?P<name>[A-Za-z_][A-Za-z0-9_.]*)\s*(?:<-|:=|=)\s*(?P<rhs>[^=].*)$"
)
_HELD_TOKEN = re.compile(rf"(?<![A-Za-z0-9_]){_HELD}(?![A-Za-z0-9_])")

_SQL_LINE_COMMENT = re.compile(r"--[^\n]*")
_HASH_COMMENT = re.compile(r"(?<!['\"])#[^\n]*")
_SLASH_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def boundary_date() -> str:
    """The first held-out day, from `config/seal.yml`. W2.4 owns that file."""
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return str(loaded["seal_start_date"])


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    text: str

    def __str__(self) -> str:
        return f"GD-04 FAIL: {self.path}:{self.line} {self.rule} -- {self.text.strip()[:90]}"


def redact_blobs(line: str) -> str:
    """The line with any long base64 run replaced by a marker, in place."""
    if len(line) <= _BLOB_MIN:
        return line
    return _BLOB.sub("<blob>", line)


def join_seams(text: str) -> str:
    """Close the seams between adjacent string fragments, repeatedly."""
    previous = None
    joined = text
    for _ in range(6):
        if joined == previous:
            break
        previous = joined
        joined = _SEAM.sub("", joined)
    return joined


def strip_comments(line: str, relative: str) -> str:
    """The line with its comments removed, so a comment can forgive nothing."""
    suffix = Path(relative).suffix.lower()
    bare = _BLOCK_COMMENT.sub(" ", line)
    if suffix in {".sql", ".yml", ".yaml"} or suffix == "":
        bare = _SQL_LINE_COMMENT.sub("", bare)
    else:
        bare = _SQL_LINE_COMMENT.sub("", bare)
    if suffix in {".py", ".r", ".sh", ".yml", ".yaml", ".toml", ".ipynb", ""}:
        bare = _HASH_COMMENT.sub("", bare)
    if suffix in {".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".java", ".scala"}:
        bare = _SLASH_COMMENT.sub("", bare)
    return bare


def _held_literal_in(text: str) -> bool:
    """True when the text carries the held-out label as a quoted literal."""
    return bool(re.search(_QUOTED_HELD, text))


def collect_taint(lines: list[str]) -> tuple[set[str], set[str]]:
    """Names that carry the held-out label, and names that carry its view.

    A label spelled in two pieces, or parked in a variable, is still the label.
    Three passes, so the order of the assignments does not matter.
    """
    held: set[str] = set()
    viewy: set[str] = set()
    for _ in range(3):
        for raw in lines:
            if len(raw) > _TAINT_MAX_LINE or ("=" not in raw and "<-" not in raw):
                continue
            found = _ASSIGN.search(raw)
            if not found:
                continue
            name = found.group("name")
            rhs = join_seams(found.group("rhs"))
            if _held_literal_in(rhs):
                held.add(name)
            for other in list(held):
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(other)}(?![A-Za-z0-9_])", rhs):
                    stem = _VIEW_STEM.search(rhs)
                    if stem and stem.group(1) == other:
                        viewy.add(name)
            if RULE_VIEW.search(rhs):
                viewy.add(name)
            for other in list(viewy):
                if re.fullmatch(rf"\s*{re.escape(other)}\s*", rhs):
                    viewy.add(name)
    return held, viewy


def _statement_end(text: str, start: int, line_starts: list[int]) -> int:
    """Where the statement carrying `start` ends: a `;`, a blank line, or six lines."""
    stop = len(text)
    semicolon = text.find(";", start)
    if semicolon != -1:
        stop = min(stop, semicolon)
    blank = re.search(r"\n[ \t]*\n", text[start:])
    if blank:
        stop = min(stop, start + blank.start())
    index = _line_of(line_starts, start)
    if index + 6 < len(line_starts):
        stop = min(stop, line_starts[index + 6])
    return stop


def _line_of(line_starts: list[int], offset: int) -> int:
    low, high = 0, len(line_starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if line_starts[mid] <= offset:
            low = mid
        else:
            high = mid - 1
    return low


def _date_violates(operator: str, day: date, boundary: date) -> bool:
    """True when this comparison can select a day on or after the boundary."""
    operator = operator.upper()
    if operator in {">=", "=", "BETWEEN", "AND"}:
        return day >= boundary
    if operator == ">":
        return day >= boundary - timedelta(days=1)
    if operator == "<=":
        return day >= boundary
    if operator == "<":
        return day > boundary
    return False


def scan_text(relative: str, text: str, boundary: str) -> list[Violation]:
    """The four rules over one file's text. The allowlist is applied by the caller."""
    boundary_day = date.fromisoformat(str(boundary))
    raw_lines = text.splitlines()
    lines = [redact_blobs(line) for line in raw_lines]
    bare_lines = [strip_comments(line, relative) for line in lines]
    held, viewy = collect_taint(lines)
    found: list[Violation] = []

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        joined = join_seams(line)
        bare = bare_lines[number - 1]

        # Both spellings are read: closing a seam can join two fragments into
        # the banned token, and it can also swallow a quote that a rule needs.
        hit_label = any(
            rule.search(text)
            for rule in (RULE_ANALYSIS_SET, RULE_COMPLEMENT)
            for text in (line, joined)
        )
        if not hit_label and "analysis_set" in line:
            for name in held:
                near = (
                    rf"analysis_set\b[^\n]{{0,60}}"
                    rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
                )
                if re.search(near, line):
                    hit_label = True
                    break
        if hit_label:
            found.append(Violation(relative, number, "reads the held-out analysis set", line))

        hit_view = bool(RULE_VIEW.search(joined)) or bool(RULE_VIEW.search(line))
        if not hit_view and "v_pitch_" in joined:
            stem = _VIEW_STEM.search(joined)
            if stem and stem.group(1) in held:
                hit_view = True
        if not hit_view and viewy:
            for name in viewy:
                use = (
                    rf"(?:\bFROM\b|\bJOIN\b|\.table\s*\(|\bexecute\s*\(|\bref\s*\()"
                    rf"[^\n]{{0,40}}(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
                )
                if re.search(use, bare, re.IGNORECASE):
                    hit_view = True
                    break
        if hit_view:
            found.append(Violation(relative, number, "names the held-out pitch view", line))

        for rule in (RULE_DATE_CMP, RULE_DATE_CTOR):
            for match in rule.finditer(bare):
                groups = match.groups()
                try:
                    day = date(int(groups[1]), int(groups[2]), int(groups[3]))
                except ValueError:
                    continue
                if _date_violates(groups[0], day, boundary_day):
                    found.append(
                        Violation(relative, number, "literal boundary-date comparison", line)
                    )
                    break
            else:
                continue
            break

    # Rule 3 is statement-scoped, and reads the text with its comments removed.
    bare_text = "\n".join(bare_lines)
    line_starts = [0]
    for line in bare_lines[:-1]:
        line_starts.append(line_starts[-1] + len(line) + 1)
    for match in RULE_RAW_FACT.finditer(bare_text):
        table = re.search(rf"\b{_FACT}[a-z0-9_]+\b", match.group(0), re.IGNORECASE)
        if table is None:
            continue
        at = match.start() + table.start()
        window = bare_text[match.end() : _statement_end(bare_text, at, line_starts)]
        if QUALIFIES_OPEN.search(window):
            continue
        number = _line_of(line_starts, at) + 1
        found.append(
            Violation(relative, number, "unqualified raw fact-table read", lines[number - 1])
        )

    found.sort(key=lambda v: (v.line, v.rule))
    return found


def _git_listing(root: Path) -> set[str]:
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        if root == REPO_ROOT:
            raise RuntimeError(f"git ls-files failed in {root}: {done.stderr.strip()}")
        # A scratch root in a test is not a repository; the walk still covers it.
        return set()
    return {line for line in done.stdout.splitlines() if line.strip()}


def _walk_listing(root: Path) -> set[str]:
    """Every file under the directories that execute, tracked or not."""
    out: set[str] = set()
    for name in WALKED_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        stack = [base]
        while stack:
            here = stack.pop()
            try:
                entries = list(here.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.name in SKIP_DIR_NAMES:
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    stack.append(entry)
                    continue
                try:
                    out.add(str(entry.relative_to(root)))
                except ValueError:
                    continue
    return out


def is_excluded(relative: str) -> bool:
    """Receipts and logs only. Neither is importable, runnable or compiled."""
    return any(relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def shipped_files(root: Path = REPO_ROOT) -> list[str]:
    """Every file the scan considers: git's listing, plus the directories that execute."""
    return sorted(
        path for path in (_git_listing(root) | _walk_listing(root)) if not is_excluded(path)
    )


def is_scannable(relative: str, root: Path = REPO_ROOT) -> bool:
    """True when the file is code this scan can read.

    Format, and whether the bytes are there to read. Not size, and not whether
    the path is a symlink: a symlink into an ignored directory is importable,
    so it is followed and scanned.
    """
    path = root / relative
    if Path(relative).suffix.lower() in NON_CODE_SUFFIXES:
        return False
    return path.is_file()


def read_scannable(relative: str, root: Path = REPO_ROOT) -> str | None:
    """The file's text, with a notebook's embedded blobs left where they are."""
    path = root / relative
    try:
        with path.open("rb") as handle:
            blob = handle.read(MAX_READ_BYTES)
    except OSError:
        return None
    if b"\x00" in blob[:8192]:
        return None
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("utf-8", errors="replace")


def scan_repository(
    root: Path = REPO_ROOT,
    allowlist: frozenset[str] = ALLOWLIST,
    only: str | None = None,
) -> list[Violation]:
    """The whole repository, minus the allowlist, minus non-code formats."""
    boundary = boundary_date()
    found: list[Violation] = []
    for relative in shipped_files(root):
        if only is not None and relative != only:
            continue
        if relative in allowlist:
            continue
        if not is_scannable(relative, root):
            continue
        text = read_scannable(relative, root)
        if text is None:
            continue
        found.extend(scan_text(relative, text, boundary))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GD-04, the static scan.")
    parser.add_argument("--path", default=None, help="scan this one repository-relative path")
    parser.add_argument(
        "--no-allowlist", action="store_true", help="scan the two defining files too"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    allowlist = frozenset() if args.no_allowlist else ALLOWLIST
    found = scan_repository(allowlist=allowlist, only=args.path)
    if args.json:
        print(
            json.dumps(
                [
                    {"path": v.path, "line": v.line, "rule": v.rule, "text": v.text.strip()[:120]}
                    for v in found
                ],
                indent=2,
            )
        )
    else:
        for violation in found:
            print(violation)
        scope = args.path if args.path else "the repository"
        print(f"GD-04: {len(found)} violation(s) in {scope}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
