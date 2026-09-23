"""GD-04 and GD-05. Layer 3 of the four-layer guard: the static scan.

SOP step W1.8, inverted in revision R2.

WHAT THIS SCANS. The whole repository. Every file the repository ships --
`git ls-files` plus everything untracked that git would track -- minus the
formats that cannot execute a read (prose, data, images, lockfiles). There is
no directory list. The R1 rule named five directories and so did not cover
`src/absump/ch2/`, `src/absump/ch3/`, `tools/` or `app/`, which is exactly
where W5 puts the solver and the fallback and where W5.5 imports the Chapter 2
predictor from; a held-out read in either passed the guard. `SCANNED_DIR_SKIPS`
below is empty, and a test asserts it stays empty.

WHAT IT FAILS ON, four rules:

    1. `analysis_set` compared to the held-out label, within one line.
    2. the held-out pitch view, by name.
    3. a raw fact-table read that the file does not restrict to the open set.
    4. a literal date comparison against the boundary day in config/seal.yml.

WHAT IS ALLOWLISTED. Exactly two paths, by exact path and nothing else:
`src/absump/seal.py` and `quality/sql/analysis_set.sql`. They are the two files
that define the held-out set. GD-05's count is two, and a test asserts it.

WHY THE RULES ARE BUILT FROM FRAGMENTS. This file would otherwise fail its own
scan, and allowlisting it would make the count three. Every banned token below
is assembled at import time, so the literal never appears in this file. The
boundary date is read from `config/seal.yml`, which is also why no number here
is hard-coded (SOP rule 0.5.4).

GD-09, the red team, plants one violation in `R/ch1/20_surfaces.R` and a second
in `src/absump/ch3/dp_fast.py` and requires the guard to fail on both. The
planted-violation tests below are that mechanism in miniature, run on temporary
files so the working tree is never dirtied.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "seal.yml"

# ------------------------------------------------------------- the allowlist
# Exactly two, by exact repository-relative path. Not a prefix, not a glob, not
# a directory. GD-05's count is two.
ALLOWLIST: frozenset[str] = frozenset(
    {
        "src/absump/seal.py",
        "quality/sql/analysis_set.sql",
    }
)

# The R1 directory list, kept empty on purpose. A test asserts it is empty.
SCANNED_DIR_SKIPS: frozenset[str] = frozenset()

# Formats that carry no executable read: prose, tabular data, images, archives,
# lockfiles. The exclusion is by format, never by location.
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
    }
)

MAX_BYTES = 2_000_000

# ----------------------------------------------------------------- the rules
# Assembled so that this file contains none of the tokens it bans.
_HELD = "seal" + "ed"
_VIEW = "v_pitch_" + _HELD
_FACT = "fct_" + "pitch"
_QUOTED_HELD = rf"['\"]{_HELD}['\"]"
_QUOTED_OPEN = r"['\"]open['\"]"

# 1. The expression, not the vocabulary: the column and the held-out literal
#    have to meet on one line. A file may discuss the held-out set in prose; it
#    may not compare the routing column to it.
RULE_ANALYSIS_SET = re.compile(
    rf"analysis_set\b[^\n]{{0,60}}{_QUOTED_HELD}|{_QUOTED_HELD}[^\n]{{0,60}}\banalysis_set\b"
)

# 2. The held-out view, by name, anywhere.
RULE_VIEW = re.compile(rf"\b{_VIEW}\b")

# 3. A read of the raw fact table. `FROM`, `JOIN`, a dbt `ref()` or `source()`,
#    `read_parquet` or a `.table()` call, followed by the table name. It is
#    forgiven only when the same file restricts the routing column to the open
#    label, which is what the open views do.
RULE_RAW_FACT = re.compile(
    rf"(?:\bFROM\b|\bJOIN\b|\bref\s*\(|\bsource\s*\(|read_parquet|\.table\s*\()[^\n]{{0,80}}\b{_FACT}\b",
    re.IGNORECASE,
)
QUALIFIES_OPEN = re.compile(rf"analysis_set\b[^\n]{{0,40}}{_QUOTED_OPEN}", re.IGNORECASE)


def boundary_date() -> str:
    """The first held-out day, from `config/seal.yml`. W2.4 owns that file."""
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return str(loaded["seal_start_date"])


def _date_rule(boundary: str) -> re.Pattern[str]:
    """4. A literal date comparison against the boundary day.

    Both the ISO form, `>= DATE '<boundary>'` or `>= as.Date("<boundary>")`,
    and the three-integer constructor form that a date library would write. The
    date itself comes from the config file, so it is not written here, which is
    also why this file does not fail its own rule.
    """
    year, month, day = boundary.split("-")
    iso = re.escape(boundary)
    ctor = rf"[A-Za-z_.]*[Dd]ate\s*\(\s*{int(year)}\s*,\s*{int(month)}\s*,\s*{int(day)}\s*\)"
    prefix = r"(?:>=|>)\s*(?:DATE\s+|as\.Date\s*\(\s*|date\s*\(\s*|pl\.date\s*\(\s*)?"
    return re.compile(rf"{prefix}['\"]?{iso}|(?:>=|>)\s*{ctor}")


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    text: str

    def __str__(self) -> str:
        return f"GD-04 FAIL: {self.path}:{self.line} {self.rule} -- {self.text.strip()[:90]}"


def shipped_files(root: Path = REPO_ROOT) -> list[str]:
    """Every file the repository ships, relative to the root, sorted.

    Tracked plus untracked-not-ignored. A violation written but not yet
    committed still fails the guard. There is no directory filter here.
    """
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"git ls-files failed in {root}: {done.stderr.strip()}")
    return sorted({line for line in done.stdout.splitlines() if line.strip()})


def is_scannable(relative: str, root: Path = REPO_ROOT) -> bool:
    """True when the file is code this scan can read. Format only, never place."""
    path = root / relative
    if Path(relative).suffix.lower() in NON_CODE_SUFFIXES:
        return False
    if not path.is_file() or path.is_symlink():
        return False
    return path.stat().st_size <= MAX_BYTES


def scan_text(relative: str, text: str, boundary: str) -> list[Violation]:
    """The four rules, over one file's text. The allowlist is applied by the caller."""
    found: list[Violation] = []
    date_rule = _date_rule(boundary)
    qualified = bool(QUALIFIES_OPEN.search(text))
    for number, line in enumerate(text.splitlines(), start=1):
        if RULE_ANALYSIS_SET.search(line):
            found.append(Violation(relative, number, "reads the held-out analysis set", line))
        if RULE_VIEW.search(line):
            found.append(Violation(relative, number, "names the held-out pitch view", line))
        if RULE_RAW_FACT.search(line) and not qualified:
            found.append(Violation(relative, number, "unqualified raw fact-table read", line))
        if date_rule.search(line):
            found.append(Violation(relative, number, "literal boundary-date comparison", line))
    return found


def scan_repository(
    root: Path = REPO_ROOT,
    allowlist: frozenset[str] = ALLOWLIST,
) -> list[Violation]:
    """The whole repository, minus the allowlist, minus non-code formats."""
    boundary = boundary_date()
    found: list[Violation] = []
    for relative in shipped_files(root):
        if relative in allowlist:
            continue
        if not is_scannable(relative, root):
            continue
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found.extend(scan_text(relative, text, boundary))
    return found


# ===================================================================== GD-05
def test_allowlist_is_exactly_two_paths() -> None:
    """GD-05's count is two, by exact path, and nothing else."""
    assert len(ALLOWLIST) == 2
    assert sorted(ALLOWLIST) == ["quality/sql/analysis_set.sql", "src/absump/seal.py"]


def test_allowlisted_paths_exist() -> None:
    for relative in sorted(ALLOWLIST):
        assert (REPO_ROOT / relative).is_file(), f"{relative} is allowlisted but absent"


def test_allowlist_is_load_bearing() -> None:
    """Without the allowlist the scan fails, and only on allowlisted paths.

    If this ever finds nothing, the scan has stopped seeing the two files that
    define the held-out set, and a green run would mean nothing.
    """
    unfiltered = scan_repository(allowlist=frozenset())
    assert unfiltered, "the scan no longer flags the two files that define the held-out set"
    assert {v.path for v in unfiltered} <= ALLOWLIST, "\n".join(str(v) for v in unfiltered)


# ===================================================================== GD-04
def test_no_directory_is_skipped() -> None:
    """The R1 directory list is gone and stays gone (architect item 6)."""
    assert not SCANNED_DIR_SKIPS, f"a directory list came back: {sorted(SCANNED_DIR_SKIPS)}"


def test_every_shipped_file_is_dropped_only_for_its_format() -> None:
    """The one reason a shipped file is not scanned is that it is not code.

    This is the assertion that replaces the R1 directory list. `src/absump/ch2/`,
    `src/absump/ch3/`, `tools/` and `app/` are covered because nothing excludes
    them, not because they are named.
    """
    for relative in shipped_files():
        if is_scannable(relative):
            continue
        path = REPO_ROOT / relative
        reason_is_format = Path(relative).suffix.lower() in NON_CODE_SUFFIXES
        reason_is_size = path.is_file() and path.stat().st_size > MAX_BYTES
        reason_is_gone = not path.is_file() or path.is_symlink()
        assert reason_is_format or reason_is_size or reason_is_gone, (
            f"{relative} was skipped and no format, size or link rule explains it"
        )


def test_code_extensions_are_all_scanned() -> None:
    code = [p for p in shipped_files() if Path(p).suffix.lower() in {".py", ".r", ".sql", ".sh"}]
    assert len(code) > 10, "the scan found almost no code; git ls-files is probably wrong"
    for relative in code:
        assert is_scannable(relative), f"{relative} is code and must be scanned"


def test_repository_has_no_held_out_read() -> None:
    """The whole repository, every file it ships, minus two allowlisted paths."""
    found = scan_repository()
    assert not found, "\n".join(str(v) for v in found)


# ------------------------------------------------- the scan is not vacuous
def _planted() -> list[tuple[str, str]]:
    boundary = boundary_date()
    return [
        ("analysis set", f"SELECT game_pk FROM dim_game WHERE analysis_set = '{_HELD}'"),
        ("held-out view", f"rows = con.execute('SELECT * FROM {_VIEW}').pl()"),
        ("raw fact table", f"SELECT plate_x FROM {_FACT} WHERE balls = 0"),
        ("boundary date", f"SELECT * FROM dim_game WHERE official_date >= DATE '{boundary}'"),
    ]


@pytest.mark.parametrize(("label", "snippet"), _planted(), ids=[c[0] for c in _planted()])
def test_a_planted_violation_is_caught(label: str, snippet: str) -> None:
    found = scan_text("src/absump/ch3/dp_fast.py", snippet + "\n", boundary_date())
    assert found, f"the {label} rule no longer fires"


def test_gd09_plants_in_both_ch3_and_R_are_caught() -> None:
    """GD-09 plants one violation in R/ch1/ and one in src/absump/ch3/.

    The R1 directory list covered neither. Both must fail, and neither path may
    be allowlisted into silence.
    """
    plants = {
        "R/ch1/20_surfaces.R": f"d <- dplyr::filter(d, analysis_set == '{_HELD}')",
        "src/absump/ch3/dp_fast.py": f'rows = con.execute("SELECT * FROM {_VIEW}").pl()',
    }
    for relative, line in plants.items():
        assert relative not in ALLOWLIST
        found = scan_text(relative, line + "\n", boundary_date())
        assert found, f"the guard did not fail on the plant in {relative}"


def test_an_open_read_is_not_flagged() -> None:
    """The scan bans a held-out read, not the warehouse.

    Reading an open view is fine, and so is the view definition itself, which
    reads the fact table and restricts it to the open label in the same file.
    """
    open_read = "rows = con.execute('SELECT * FROM v_pitch_open').pl()\n"
    assert not scan_text("src/absump/ch2/predict.py", open_read, boundary_date())
    view_definition = (
        f"CREATE VIEW v_pitch_open AS\nSELECT * FROM {_FACT}\nWHERE analysis_set = 'open'\n"
    )
    assert not scan_text("dbt/models/marts/v_pitch_open.sql", view_definition, boundary_date())


def test_an_unqualified_fact_read_is_flagged() -> None:
    """The same read, without the open restriction, fails."""
    unqualified = f"CREATE VIEW v_all AS\nSELECT * FROM {_FACT}\n"
    found = scan_text("dbt/models/marts/v_all.sql", unqualified, boundary_date())
    assert found and found[0].rule == "unqualified raw fact-table read"


# ================================================== layer 2 and the ordering
def test_the_runtime_gate_is_shut() -> None:
    """GD-03. `_unlocked()` is False and the public surface is the one W1.8 names."""
    from absump import seal

    for name in ("assert_unsealed", "sealed_only", "frame", "_unlocked"):
        assert hasattr(seal, name), f"absump.seal is missing {name}"
    assert seal._unlocked() is False
    assert seal.unlock_report()["failed"], "the gate reports no failing precondition"


def test_the_one_way_door_refuses_and_tags_nothing() -> None:
    """GD-12. `ops/preregister.sh` is MILESTONE M1's door, and it stays shut.

    A bare run always refuses, before M1 and after it. Only the owner opens it,
    by hand, with --confirm.
    """
    before = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "tag"], capture_output=True, text=True, check=False
    ).stdout
    done = subprocess.run(
        ["bash", str(REPO_ROOT / "ops" / "preregister.sh")],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    after = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "tag"], capture_output=True, text=True, check=False
    ).stdout
    assert done.returncode != 0, "the one-way door did not refuse"
    assert "MILESTONE M1" in done.stdout + done.stderr
    assert before == after, "the door created or moved a tag"


def test_fit_receipts_descend_from_the_pre_registration() -> None:
    """GD-12, D-67. Every fit receipt under out/, open or held out."""
    done = subprocess.run(
        ["bash", str(REPO_ROOT / "ops" / "check_seal_order.sh")],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "SEAL-ORDER OK" in done.stdout
