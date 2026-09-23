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

WHAT IT SKIPS, AND HOW LITTLE.  Under `quality/receipts/` and `logs/` a file is
skipped only when it is in a transcript format (`.log`, `.json`, `.txt`, and the
rest of `EVIDENCE_SUFFIXES`) and is not executable.  Those two directories hold
this guard's own transcripts, and a transcript quotes the failure text verbatim;
without the skip every red-team run wrote the file that made the next run red,
which is what happened in phase 01.  The skip is by format and mode, never by
path alone, because the R2 verifier found `logs/env-setup.sh` sitting there at
mode 755: a runnable script under an excluded prefix could read every held-out
row in silence.  That installer now lives at `ops/env-setup.sh`, and a test
fails if any file under either directory carries the executable bit or a
shebang, so nothing runnable is there to skip.  Both directories are now
walked from the filesystem, and
anything runnable or code-shaped in them is scanned like any other file.  A test
walks them on disk and asserts it, rather than repeating the claim in prose.

EVERY RULE READS EVERY SPELLING (R3).  Identifiers are matched without regard
to case, because DuckDB folds them: the view SHOUTED is still the view.  Every
rule
reads the line as written, with its seams closed, with `chr(118)`-style
character codes decoded, with `\x65`, `\u0065` and octal escapes decoded, with
three-fragment dates fused, and with whatever a short base64 run decodes to.

WHAT IT STILL DOES NOT SEE (R2, honestly).  The rules do not see: a query
assembled across several lines through
variables the taint pass does not model; a jinja `~` concatenation of a FACT
TABLE name (the label and the view are tracked, a table name is not); a blob run
that abuts an identifier with no quote between them, where `redact_blobs` eats
the leading character; a held-out row copied into a fixture as DATA rather than
as a query, except for its date, which rule 5 reads; and any read performed by a
binary or a compiled artefact.  Rule 5 runs only on the analysis surface, so a
held-out date in a receipt or a README is not a violation.  The pre-commit hook
and the red-team run are the layers that cover what a static line-scan cannot.

WHAT IT FAILS ON.

  1. the routing column compared to the held-out label: as a quoted literal, as
     a label assembled from fragments or held in a variable, or as the
     complement of the open label, which selects exactly the held-out rows.
  2. the held-out pitch view, by name, by assembled name, or through a variable
     that was built from one.
  3. a read of a raw fact table that the enclosing statement does not restrict
     to the open label.  Statement-scoped and comment-blind: a comment cannot
     forgive a read, and a formatter that breaks `FROM` and the table name onto
     two lines does not hide one.  On the analysis surface below, a table name
     parked in a jinja or shell variable and read through it counts too.
  4. a literal date comparison that can select a day on or after the boundary
     day in `config/seal.yml` -- any such day, not only the boundary itself.
     Read over three spellings of the line, the same three the label rules read:
     as written, with its string seams closed, and with quoted date fragments
     fused back into the ISO day they spell, so `"2026-09-2" + "2"` and
     `paste("2026", "09", "22", sep = "-")` are the literal the SOP names.  An
     assignment (`=`, `<-`, `:=`) counts as a comparison: the day lands in a
     name and the comparison happens a line later, against the name.  A day
     REACHED by arithmetic counts too: a date constructor three days short of
     the boundary, plus `timedelta(days=3)`, or the R spelling `as.Date(<three
     days short>) + 3`, lands on the boundary without writing a held-out day.
  5. ON THE ANALYSIS SURFACE ONLY: a held-out day written down with no
     comparison at all.  `end: "2026-09-30"` in a config the nightly pull reads,
     or `"officialDate": "2026-09-24"` in a fixture, selects held-out rows and
     no operator appears anywhere near it.  A date that rule 4 has already read
     and let through is rule 4's business and is not reported twice.
  6. ON THE ANALYSIS SURFACE ONLY: GD-05.  The held-out label as a quoted string
     literal or as a path segment, with no read beside it.  `split = "<label>"`
     in chapter code names the held-out set, and
     `read_parquet('data/<label>/...')` reads the partition off disk without
     naming a view or a fact table.  A glob standing in for part of the label
     inside a path segment (`data/seal*/pitch/*.parquet`) opens the same
     partition and is read as the label.
  6c. EVERYWHERE: GD-05, a READ of that partition by path.  `ops/` holds the
     pull, the seal and the deploy, and `read_parquet('data/<label>/...')` there
     reads held-out rows exactly as a chapter would.  Scoped to a read call or a
     SQL `FROM`/`ATTACH`, because the seal machinery legitimately names
     `out/<label>/` as the directory it writes, lists and tars.

Every line is also read with any short base64 run decoded, so a query carried as
a blob and decoded at runtime is read as the query it is; and the view name is
looked for in the raw line as a plain substring, because redacting a blob by
shape can otherwise swallow the first character of an identifier abutting it.

THE ANALYSIS SURFACE.  `ANALYSIS_SURFACE`: R/, dbt/, notebooks/, sql/,
quality/sql/, app/, tools/, config/, scripts/, src/absump/ch*, tests/fixtures/.
Rules 1 to 4 run over the whole repository.  Rules 5 and 6 run here only, and the
reason is on disk: outside this surface the same spelling is a receipt stamp
(`quality/steps.yml`), a tag message (`ops/preregister.sh`), a dbt target name
(`dbt/profiles.yml.example`) or a seal module doing its job
(`src/absump/paths.py`), and a rule that cried wolf there would be switched off
within a week.  `config/seal.yml` is exempt from rule 5 and from nothing else:
the guard reads its own boundary day out of that file.

WHAT THIS STILL DOES NOT CATCH, stated so that no one has to find it twice: a
held-out DAY written with no comparison outside the analysis surface (rule 5 is
surface-only; rules 1 to 4 and 6c still apply everywhere, and a READ of the
held-out partition by path is now a violation anywhere in the repository,
including `ops/`); the bare label as a literal outside the surface, where it is
a receipt stamp or a tag message; date arithmetic whose offset is not a literal
on the same line (`CUT = date(2026, 9, 19) + timedelta(days=n)` with `n`
computed elsewhere, or a boundary reached by a loop); a character code built by
arithmetic rather than written down (`chr(115 + 3)`); a datum other than a date
copied into a fixture (a `gamePk` alone is not a spelling any rule can read);
and anything under `data/` or `research/`, which D-03 keeps out of git entirely.
A character code built by arithmetic is the honest counterpart to catching one
written down: this file assembles its own banned tokens from ordinals so that it
does not flag itself, and it cannot ban ordinal arithmetic without flagging
itself.  Also uncaught: a query assembled across several lines through variables
the taint pass does not model, a jinja `~` concatenation of a FACT TABLE name
(the label and the view are tracked, a table name is not), and a base64 blob
abutting an identifier with no quote between them, where `redact_blobs` eats the
leading character.  The pre-commit hook, the red-team run and GD-10 are the
layers that cover what a static line-scan cannot.  The same list is in
`docs/DEVIATIONS.md` DEV-18, which is the copy a reviewer reaches; if you change
one, change both.

WHAT THIS IS, AND THE STOPPING RULE.  GD-04 is a DETECTION layer, not the
control.  The control is the seal: the held-out rows are in an encrypted
partition, a deliberate read must run `ops/unseal.sh`, which is irreversible and
six-gated, and GD-10 pairs every UNSEALED line to a receipt that script writes
itself.  This scan's claim is bounded and testable, and is not exhaustiveness:
it catches the ACCIDENT -- a chapter reaching past the boundary day by habit --
and every evasion CLASS ever demonstrated against it, at file and line, before
the commit lands.  A scanner asked to defeat an author who already holds the
decryption key cannot succeed, and claiming otherwise is the one thing here that
would be dishonest; it is also how a gate gets switched off.

The scan is CLOSED for a phase when four conditions hold, each checkable:

  1. CLOSURE.  Every evasion any verifier has demonstrated is either caught with
     file and line and pinned BOTH as a unit regression test and as a plant in
     tests/guard/redteam_run.sh, or is written as a declared limit both above
     and in docs/DEVIATIONS.md, naming the layer that covers it.  Zero misses
     sit in neither place.
  2. CLASS, NOT SPELLING.  Each repair is made at the class level -- case
     folding, escape and ordinal decoding, file-scope conjunct, morpheme family,
     glob-tolerant path segment, read-call scope -- and ships with at least one
     SIBLING plant from the same class that nobody demonstrated.  A finding that
     can only be closed by one regex per spelling is a declared limit, not a
     repair.
  3. MUTATION-PROOF.  GD-09 fails when any rule is neutered, and every new rule
     adds a GD-09 check, so the table cannot rot into a no-op.
  4. NO NEW CLASS.  One independent, time-boxed red team per round, run in an
     isolated clone or under --root, never in the live tree.  A round ends when
     a full budget yields no miss in a NEW class; a new spelling inside a class
     already declared is fine and does not reopen the scanner.  Two consecutive
     no-new-class rounds close the scanner for the phase.

The honest finish line is "no evasion in the pinned corpus, and no new class
since round N", never "no evasion exists".  Standing obligation, so this is not
a permanent exemption: the red team runs again at each phase boundary and on any
change to the rule table, and the limit list above is re-read at the same time.

NOT A MISS, recorded so round 5 does not re-report it: a date literal reduced by
an offset (`date(2026, 9, 25) - timedelta(days=1)`) is caught, because a base at
or after the boundary is already a rule 4 violation on its own; and an offset
that lands BEFORE the boundary (`date(2026, 9, 20) + timedelta(days=1)`) is not
a violation at all.  Rule 4b reading a written `+` offset is therefore closed at
the class level, not by spelling.

WHAT IS ALLOWLISTED.  Exactly two paths, by exact path: `src/absump/seal.py`
and `quality/sql/analysis_set.sql`.  GD-05's count is two.

Every banned token here is assembled at import time, so this file carries none
of the literals it bans and does not need to be allowlisted into silence.

Run it directly for a precise, machine-readable answer:

    uv run python tests/guard/gd04_scan.py             # the whole repository
    uv run python tests/guard/gd04_scan.py --path P    # one path only
    uv run python tests/guard/gd04_scan.py --root DIR  # another tree entirely

`--root` exists so that nobody ever has to plant an evasion in the live tree to
test the scanner. It matches the ROOT argument `ops/lint_http.sh` already takes.
Round 2 planted in the repository and corrupted two other lanes' receipts; SOP
W9.7 now requires an isolated clone or a scratch root for every red-team run.

Exit 0 when clean, 1 when it finds something, 2 when it cannot run.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
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
    # Walked so that anything runnable under an evidence directory is listed.
    # The transcripts themselves are dropped again by is_excluded().
    "quality/receipts",
    "logs",
)

# Two directories hold this guard's own transcripts, and a transcript quotes the
# failure text verbatim, so scanning them made every red-team run write the file
# that turned the next run red. The exclusion is by FORMAT inside those two
# directories, never by path alone: only a transcript is skipped, and only when
# it is not executable. `ops/env-setup.sh`, mode 755, moved out of `logs/` in
# the R2 fixup; anything like it left behind is scanned like any other
# script, and so is a chmod +x file dropped under `quality/receipts/`. A test
# walks both directories on disk and asserts it.
EXCLUDED_PREFIXES: tuple[str, ...] = (
    "quality/receipts/",
    "logs/",
)

# The only formats the two evidence directories may hide behind. A transcript,
# a receipt, a note. Nothing here is importable, runnable or compiled, and an
# executable bit overrides the whole list.
EVIDENCE_SUFFIXES: frozenset[str] = frozenset(
    {".log", ".json", ".txt", ".md", ".out", ".err", ".jsonl", ".csv", ".tsv", ".diff", ".patch"}
)

# Where a date literal or the held-out label, written down with no comparison at
# all, still selects held-out rows: configs the pull reads, models, notebooks,
# fixtures, chapter code. Rules 1 to 4 run over the whole repository; rules 5 and
# 6 run here, because outside this surface the same spelling is prose, a receipt
# stamp or a target name, and a rule that cried wolf there would be turned off.
ANALYSIS_SURFACE: tuple[str, ...] = (
    "R/",
    "dbt/",
    "notebooks/",
    "sql/",
    "quality/sql/",
    "app/",
    "tools/",
    "config/",
    "scripts/",
    "src/absump/ch",
    "tests/fixtures/",
)

# The one file on that surface that must name the boundary day: the guard reads
# its own boundary out of it. It is exempt from rule 5 and from nothing else.
BOUNDARY_CONFIG = "config/seal.yml"

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
_SEAM = re.compile(r"['\"]\s*(?:,|\+|\.|&|~|\|\||\|)?\s*['\"]")

# A date spelled as three quoted fragments: paste("2026", "09", "22", sep = "-")
# in R, and the same idea with + in python. Closing an ordinary seam would give
# 20260922, which no date rule reads, so the fragments are fused back into the
# ISO spelling instead.
_FRAGMENT_DATE = re.compile(
    r"['\"](\d{4})['\"]\s*[,+.&~|]{0,2}\s*['\"](\d{1,2})['\"]\s*[,+.&~|]{0,2}\s*['\"](\d{1,2})['\"]"
)

# 1. The routing column meeting the held-out label on one line.
RULE_ANALYSIS_SET = re.compile(
    rf"analysis_set\b[^\n]{{0,60}}{_QUOTED_HELD}|{_QUOTED_HELD}[^\n]{{0,60}}\banalysis_set\b",
    re.IGNORECASE,
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
RULE_VIEW = re.compile(rf"\b{_VIEW}\b", re.IGNORECASE)

# 2b. The view name built by interpolation or concatenation from a variable.
_VIEW_STEM = re.compile(
    r"v_pitch_[\"']?\s*[,+]?\s*\{?\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}?", re.IGNORECASE
)

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
    rf"(>=|<=|<-|:=|>|<|=|\bBETWEEN\b|\bAND\b)\s*"
    rf"(?:DATE\s+|TIMESTAMP\s+|as\.Date\s*\(\s*|pl\.date\s*\(\s*|date\s*\(\s*|datetime\s*\(\s*)?"
    rf"['\"]?{_ISO}",
    re.IGNORECASE,
)
RULE_DATE_CTOR = re.compile(
    r"(>=|<=|>|<|=)\s*[A-Za-z_.]*[Dd]ate(?:time)?\s*\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)"
)

# 4b. A date literal that reaches the boundary by arithmetic rather than by
#     being written down: `date(2026, 9, 19) + timedelta(days=3)`, or
#     `as.Date("2026-09-19") + 3`. Rules 4 and 5 both want the far day written.
RULE_DATE_OFFSET = re.compile(
    r"(?:['\"](\d{4})-(\d{2})-(\d{2})['\"]"
    r"|[Dd]ate(?:time)?\s*\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\))"
    r"\s*\)?\s*\+\s*(?:[A-Za-z_.]{0,24}\s*\(\s*)?(?:days?\s*=\s*)?(\d{1,4})\b",
    re.IGNORECASE,
)
_OFFSET_MAX_DAYS = 3650

# The complement operators, in ordinal form for the same reason as the tokens:
# the tests import them so that the test file can spell an evasion without
# failing its own rule 1.
_COMPLEMENT_OPS: tuple[str, ...] = tuple(
    "".join(chr(code) for code in codes) for codes in ((33, 61), (60, 62), (78, 79, 84, 32, 73, 78))
)

_ASSIGN = re.compile(
    r"^[ \t\"',{%$]*(?:set\s+|let\s+|const\s+|var\s+|local\s+|export\s+)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_.]*)\s*(?:<-|:=|=)\s*(?P<rhs>[^=].*)$"
)
_HELD_TOKEN = re.compile(rf"(?<![A-Za-z0-9_]){_HELD}(?![A-Za-z0-9_])", re.IGNORECASE)

# 5. A held-out date written down with no comparison at all: a window in a
#    config, a game copied into a fixture, a manifest, a command-line argument.
#    Rule 4 needs an operator; `end: "2026-09-30"` has none and reads eight
#    held-out days.
_ISO_ANY = re.compile(r"(?<![0-9])(\d{4})-(\d{2})-(\d{2})(?![0-9])")

# 6. GD-05 on the analysis surface: the held-out label as a quoted literal or as
#    a path segment. `split = "<label>"` names it with no read beside it, and
#    read_parquet('data/<label>/...') reads the partition off disk without ever
#    naming a view or a fact table.
RULE_LABEL_LITERAL = re.compile(_QUOTED_HELD, re.IGNORECASE)

# 6b. The label as a path segment, with a glob standing in for any part of it:
#     `data/seal*/pitch/*.parquet` opens exactly the partition `data/sealed/`
#     does, and RULE_LABEL_PATH alone wants the whole label between separators.
_HELD_GLOBS: tuple[str, ...] = tuple(
    re.escape(_HELD[:i]) + r"[*?]+" + re.escape(_HELD[j:])
    for i in range(len(_HELD))
    for j in range(i + 1, len(_HELD) + 1)
    if len(_HELD[:i]) + len(_HELD[j:]) >= 3
)
_HELD_SEG = "(?:" + "|".join((re.escape(_HELD), *_HELD_GLOBS)) + ")"
RULE_LABEL_PATH = re.compile(
    rf"/{_HELD_SEG}(?![A-Za-z0-9_])|(?<![A-Za-z0-9_]){_HELD_SEG}/", re.IGNORECASE
)

# 6c. A READ of that partition, anywhere in the repository and not only on the
#     analysis surface: the pull, seal and deploy scripts live in `ops/`, and
#     `read_parquet('data/<label>/...')` there reads held-out rows exactly as it
#     would in a chapter. Scoped to a read because the seal machinery itself
#     legitimately names `out/<label>/` as the directory it writes and lists.
_READ_CALLS = (
    r"(?:read_parquet|read_csv|read_json|read_ipc|read_delta|scan_parquet|scan_csv"
    r"|scan_ipc|from_parquet|ParquetFile|ParquetDataset|open_dataset|dataset|i?glob"
    r"|open|load|pl\.read\w*|pd\.read\w*|duckdb\.\w+|arrow\.\w+|read\.\w+|fread)"
    r"\s*\(|\bATTACH\b|\bFROM\b"
)
RULE_SEALED_PARTITION_READ = re.compile(
    rf"(?:{_READ_CALLS})[^\n]{{0,80}}?"
    rf"(?:/{_HELD_SEG}(?![A-Za-z0-9_])|(?<![A-Za-z0-9_]){_HELD_SEG}/)",
    re.IGNORECASE,
)

# A base64 payload short enough to be a query rather than a plot. The long runs
# are already redacted by shape; what is left is decoded and scanned as text.
_B64_PAYLOAD = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{16,504}={0,2}(?![A-Za-z0-9+/=])")
_B64_MAX_LINE = 200_000
_B64_MAX_PAYLOADS = 24

# A character code written as a call, in the four languages this repository
# uses. The argument must be a numeric literal: `chr(code)` over a variable,
# which this file itself writes, is left alone.
_ORDINAL = re.compile(
    r"(?:chr|CHAR|CHR|String\.fromCharCode|intToUtf8)\s*\(\s*(\d{1,3})\s*\)",
)
_ORDINAL_MAX = 200

# A character written as an escape inside a string: "seal\x65d" is the label.
_ESCAPE = re.compile(r"\\x([0-9A-Fa-f]{2})|\\u([0-9A-Fa-f]{4})|\\([0-7]{2,3})")

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
    code: str = "GD-04"

    def __str__(self) -> str:
        return f"{self.code} FAIL: {self.path}:{self.line} {self.rule} -- {self.text.strip()[:90]}"


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


def decode_ordinals(text: str, limit: int = _ORDINAL_MAX) -> str:
    """Character codes written as calls, replaced by the characters they spell.

    A query that spells the first characters of the held-out view as `chr(118)`
    and `chr(95)` and abuts the rest as a string is that view; decoding the codes
    and closing the seam says so. Only a numeric literal argument in the
    printable ASCII range is decoded, so this file's own `chr(code)` generators,
    which take a variable, are untouched.
    """
    if "(" not in text:
        return text
    seen = 0

    def one(match: re.Match[str]) -> str:
        nonlocal seen
        if seen >= limit:
            return match.group(0)
        code = int(match.group(1))
        if not 32 <= code <= 126:
            return match.group(0)
        seen += 1
        return "'" + chr(code) + "'"

    return _ORDINAL.sub(one, text)


def decode_escapes(text: str, limit: int = _ORDINAL_MAX) -> str:
    """Hex, unicode and octal escapes replaced by the characters they spell."""
    if "\\" not in text:
        return text
    seen = 0

    def one(match: re.Match[str]) -> str:
        nonlocal seen
        hexed, uni, octal = match.groups()
        if seen >= limit:
            return match.group(0)
        code = int(hexed or uni, 16) if (hexed or uni) else int(octal, 8)
        if not 32 <= code <= 126:
            return match.group(0)
        seen += 1
        return chr(code)

    return _ESCAPE.sub(one, text)


def fuse_fragment_dates(text: str) -> str:
    """Three quoted fragments fused back into the ISO date they spell.

    `paste("2026", "09", "22", sep = "-")` and `"2026" + "09" + "22"` are the
    same day as the literal the SOP names. Closing an ordinary seam gives
    20260922, which no date rule reads, so the dashes are put back here.
    """

    def fuse(match: re.Match[str]) -> str:
        year, month, day = match.group(1), match.group(2), match.group(3)
        return f"'{year}-{int(month):02d}-{int(day):02d}'"

    return _FRAGMENT_DATE.sub(fuse, text)


def spellings(line: str) -> list[str]:
    """One line as written, with its seams closed, and with its ordinals decoded.

    Three readings, not three rules: a token spelled in fragments, in character
    codes, or in both is the same token, and every rule reads all of them.
    """
    ordinal = decode_escapes(decode_ordinals(line))
    out: list[str] = [line]
    for candidate in (join_seams(line), ordinal, join_seams(ordinal)):
        if candidate not in out:
            out.append(candidate)
    return out


def date_spellings(bare: str) -> list[str]:
    """The comment-stripped line, its seams closed, and its date fragments fused.

    The seam-joiner is what defeats a label spelled in two pieces. A date
    spelled in two pieces is the same evasion one rule over, so the date rules
    read the same three spellings the label rules read.
    """
    out = [bare]
    ordinal = decode_escapes(decode_ordinals(bare))
    for candidate in (
        join_seams(bare),
        fuse_fragment_dates(bare),
        fuse_fragment_dates(join_seams(bare)),
        ordinal,
        fuse_fragment_dates(join_seams(ordinal)),
    ):
        if candidate not in out:
            out.append(candidate)
    return out


def decoded_payloads(text: str, limit: int = _B64_MAX_PAYLOADS) -> list[str]:
    """Whatever short base64 runs on the line decode to, as text.

    A notebook that carries its query as a blob and decodes it at runtime reads
    the same rows as a notebook that spells it out. The long runs are redacted
    by shape before this sees them, so what is offered here is query-sized.
    """
    out: list[str] = []
    if len(text) > _B64_MAX_LINE:
        return out
    for match in _B64_PAYLOAD.finditer(text):
        chunk = match.group(0)
        if len(chunk) % 4:
            continue
        try:
            raw = base64.b64decode(chunk, validate=True)
        except (binascii.Error, ValueError):
            continue
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not decoded or not all(ch.isprintable() or ch in "\n\t" for ch in decoded):
            continue
        out.append(decoded)
        if len(out) >= limit:
            break
    return out


def on_analysis_surface(relative: str) -> bool:
    """True where a date or a label written with no comparison still selects rows."""
    return any(relative.startswith(prefix) for prefix in ANALYSIS_SURFACE)


def strip_comments(line: str, relative: str) -> str:
    """The line with its comments removed, so a comment can forgive nothing."""
    suffixes = [part.lower() for part in Path(relative).suffixes]
    suffix = suffixes[-1] if suffixes else ""
    if suffix in {".example", ".sample", ".template", ".tmpl", ".in", ".bak", ".orig"}:
        # `dbt/profiles.yml.example` is a YAML file; read the suffix that says so.
        suffix = suffixes[-2] if len(suffixes) > 1 else ""
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
    return bool(re.search(_QUOTED_HELD, text, re.IGNORECASE))


def collect_taint(lines: list[str]) -> tuple[set[str], set[str], set[str]]:
    """Names that carry the held-out label, its view, and a raw fact table.

    A label spelled in two pieces, or parked in a variable, is still the label,
    and a table name parked in a jinja variable is still that table. Three
    passes, so the order of the assignments does not matter.
    """
    held: set[str] = set()
    viewy: set[str] = set()
    facty: set[str] = set()
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
            if re.search(rf"['\"]?\b{_FACT}[a-z0-9_]+\b", rhs, re.IGNORECASE):
                facty.add(name)
            for other in list(facty):
                if re.fullmatch(rf"\s*['\"{{}}\s]*{re.escape(other)}['\"{{}}\s]*\s*", rhs):
                    facty.add(name)
    return held, viewy, facty


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
    # An assignment is a comparison for this purpose: the day lands in a name
    # and the comparison happens a line later, against that name.
    if operator in {">=", "=", "<-", ":=", "BETWEEN", "AND"}:
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
    held, viewy, facty = collect_taint(lines)
    surface = on_analysis_surface(relative)
    found: list[Violation] = []

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        raw = raw_lines[number - 1]
        bare = bare_lines[number - 1]
        # As written, seams closed, ordinals decoded, and both at once.
        readings = spellings(line)
        bare_readings = spellings(bare)
        # What the line carries once a short base64 run is decoded. A query
        # carried as a blob and decoded at runtime reads the same rows.
        payloads = decoded_payloads(line)

        # Both spellings are read: closing a seam can join two fragments into
        # the banned token, and it can also swallow a quote that a rule needs.
        hit_label = any(
            rule.search(text)
            for rule in (RULE_ANALYSIS_SET, RULE_COMPLEMENT)
            for text in (*readings, *payloads)
        )
        if not hit_label and "analysis_set" in line.lower():
            for name in held:
                near = (
                    rf"analysis_set\b[^\n]{{0,60}}"
                    rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
                )
                if re.search(near, line, re.IGNORECASE):
                    hit_label = True
                    break
        if hit_label:
            found.append(Violation(relative, number, "reads the held-out analysis set", line))

        # The raw line is read as a plain substring as well: redacting a blob
        # by shape can swallow the first character of an identifier that abuts
        # it, and no base64 alphabet carries the underscores the view name has.
        hit_view = _VIEW in raw.lower() or any(
            RULE_VIEW.search(text) for text in (*readings, *payloads)
        )
        if not hit_view and "v_pitch_" in join_seams(decode_ordinals(line)).lower():
            stem = _VIEW_STEM.search(join_seams(decode_ordinals(line)))
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

        # Rule 4, over the same three spellings the label rules read, plus
        # anything a short base64 run decoded to.
        hit_date = False
        candidates = date_spellings(bare)
        candidates.extend(text for text in payloads if text not in candidates)
        for candidate in candidates:
            for match in RULE_DATE_OFFSET.finditer(candidate):
                groups = match.groups()
                parts = groups[0:3] if groups[0] else groups[3:6]
                try:
                    base = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    offset = int(groups[6])
                except (TypeError, ValueError):
                    continue
                if offset > _OFFSET_MAX_DAYS:
                    continue
                if base + timedelta(days=offset) >= boundary_day:
                    hit_date = True
                    break
            if hit_date:
                break
            for rule in (RULE_DATE_CMP, RULE_DATE_CTOR):
                for match in rule.finditer(candidate):
                    groups = match.groups()
                    try:
                        day = date(int(groups[1]), int(groups[2]), int(groups[3]))
                    except ValueError:
                        continue
                    if _date_violates(groups[0], day, boundary_day):
                        hit_date = True
                        break
                if hit_date:
                    break
            if hit_date:
                break
        if hit_date:
            found.append(Violation(relative, number, "literal boundary-date comparison", line))

        # Rule 5. A held-out day written down with no comparison at all: a
        # window in a config, a game copied into a fixture, an argument. Rule 4
        # needs an operator; this one does not, and it runs on the surface where
        # such a date selects rows rather than stamping a receipt.
        if surface and not hit_date and relative != BOUNDARY_CONFIG:
            for candidate in candidates:
                # A date that rule 4 has already read is rule 4's business: it
                # judged the operator and let this one through, and
                # `official_date < DATE '<boundary>'` is an open-set read.
                compared = [
                    (match.start(), match.end())
                    for rule in (RULE_DATE_CMP, RULE_DATE_CTOR)
                    for match in rule.finditer(candidate)
                ]
                stop = False
                for match in _ISO_ANY.finditer(candidate):
                    if any(start <= match.start() < end for start, end in compared):
                        continue
                    try:
                        day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                    except ValueError:
                        continue
                    if day >= boundary_day:
                        found.append(Violation(relative, number, "held-out date literal", line))
                        stop = True
                        break
                if stop:
                    break

        # Rule 6, GD-05. The held-out label as a quoted literal or as a path
        # segment, anywhere on the analysis surface. It needs no read beside it:
        # naming the label in chapter code is itself the violation, and a sealed
        # partition read by path names it and nothing else.
        if surface:
            for candidate in (*bare_readings, *payloads):
                if RULE_LABEL_LITERAL.search(candidate) or RULE_LABEL_PATH.search(candidate):
                    found.append(
                        Violation(
                            relative,
                            number,
                            "the held-out label outside the two allowlisted files",
                            line,
                            "GD-05",
                        )
                    )
                    break

        # Rule 6c, GD-05, everywhere. A read of the held-out partition by path,
        # off the analysis surface too: `ops/` holds the pull, the seal and the
        # deploy, and read_parquet there reads the same rows a chapter would.
        if not surface:
            for candidate in (*bare_readings, *payloads):
                if RULE_SEALED_PARTITION_READ.search(candidate):
                    found.append(
                        Violation(
                            relative,
                            number,
                            "reads the held-out partition off disk",
                            line,
                            "GD-05",
                        )
                    )
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

    # A raw fact table parked in a name and read through it. Rule 3 reads the
    # table by its own name anywhere in the repository; this reads it through a
    # jinja or shell variable, and it runs on the analysis surface, where a
    # `{{ tbl }}` after a FROM is a read rather than a generator writing a plant.
    for name in sorted(facty) if surface else []:
        use = re.compile(
            rf"(?:\bFROM\b|\bJOIN\b|\bref\s*\(|\bsource\s*\(|read_parquet|\.table\s*\()"
            rf"[^;]{{0,120}}?(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])",
            re.IGNORECASE | re.DOTALL,
        )
        for match in use.finditer(bare_text):
            at = match.start()
            window = bare_text[match.end() : _statement_end(bare_text, at, line_starts)]
            if QUALIFIES_OPEN.search(window):
                continue
            number = _line_of(line_starts, at) + 1
            found.append(
                Violation(relative, number, "unqualified raw fact-table read", lines[number - 1])
            )

    seen: set[tuple[int, str, str]] = set()
    unique: list[Violation] = []
    for violation in found:
        key = (violation.line, violation.rule, violation.code)
        if key in seen:
            continue
        seen.add(key)
        unique.append(violation)
    unique.sort(key=lambda v: (v.line, v.code, v.rule))
    return unique


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


def is_excluded(relative: str, root: Path = REPO_ROOT) -> bool:
    """A transcript under one of the two evidence directories, and nothing else.

    The prefix is necessary and not sufficient. The file must also be in a
    transcript format and must not be executable, so a `.sh` dropped under
    `logs/`, or a chmod +x file under `quality/receipts/`, is scanned like any
    other file in the repository. The claim that nothing runnable is excluded is
    made true here rather than asserted in prose.
    """
    if not any(relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    if Path(relative).suffix.lower() not in EVIDENCE_SUFFIXES:
        return False
    path = root / relative
    try:
        if path.is_file() and os.access(path, os.X_OK):
            return False
    except OSError:
        return False
    return True


def shipped_files(root: Path = REPO_ROOT) -> list[str]:
    """Every file the scan considers: git's listing, plus the directories that execute."""
    return sorted(
        path for path in (_git_listing(root) | _walk_listing(root)) if not is_excluded(path, root)
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
    parser.add_argument(
        "--root",
        default=None,
        help="scan this tree instead of the repository: a clone, or any scratch directory. "
        "Red-team plants belong here, never in the live tree (SOP W9.7).",
    )
    args = parser.parse_args(argv)
    allowlist = frozenset() if args.no_allowlist else ALLOWLIST
    root = Path(args.root).resolve() if args.root else REPO_ROOT
    if not root.is_dir():
        print(f"GD-04: --root {root} is not a directory", file=sys.stderr)
        return 2
    found = scan_repository(root=root, allowlist=allowlist, only=args.path)
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
