"""GD-09. The red team: the guard has to fail when it should.

SOP step W9.7, section 6.4.

A guard nobody has watched fail is a guard nobody has tested. GD-09 plants two
real violations and requires the static scan to report both, by file and line:

    R/ch1/20_surfaces.R          a Chapter 1 script reading the held-out label
    src/absump/ch3/dp_fast.py    the Chapter 3 solver reading the held-out view

Those two files are the point. The R1 scan named five directories and neither
`src/absump/ch3/` nor `tools/` nor `app/` was among them, so a held-out read in
the solver passed the guard. The R2 scan walks the whole repository.

WHAT RUNS WHERE. `bash tests/guard/redteam_run.sh`, behind
`make prove-guard-redteam`, does the real thing end to end: apply, assert the
two failures, revert, re-run clean, exit 0. This file does not run it, because
that script runs the guard suite and this file is in it. What this file checks
is that the patch still plants what it claims to plant, in the two files it
claims to plant it in, at lines the scan reports; and that the run script is
real rather than the placeholder the Makefile step left behind.

THE PLACEHOLDER IN THE PATCH. `tests/guard/redteam.patch` writes the held-out
label as `@H@` and the run script renders it at apply time. The patch has a
`.patch` suffix, the scan reads every format that can carry a read, and a
stored patch carrying the literal label would fail the guard it exists to test.
This file renders the same way, in memory, and asserts the rendered lines are
caught. No literal held-out token appears here either.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from test_no_sealed_reads import ALLOWLIST, boundary_date, scan_text

REPO_ROOT = Path(__file__).resolve().parents[2]
PATCH_PATH = REPO_ROOT / "tests" / "guard" / "redteam.patch"
RUN_SCRIPT = REPO_ROOT / "tests" / "guard" / "redteam_run.sh"

R_TARGET = "R/ch1/20_surfaces.R"
PY_TARGET = "src/absump/ch3/dp_fast.py"
TARGETS: tuple[str, ...] = (R_TARGET, PY_TARGET)

PLACEHOLDER = "@H@"
_HELD = "seal" + "ed"
_PLACEHOLDER_MARKER = "ABSUMP" + "_PLACEHOLDER"

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")


def patch_text() -> str:
    return PATCH_PATH.read_text(encoding="utf-8")


def rendered_patch() -> str:
    return patch_text().replace(PLACEHOLDER, _HELD)


def planted_lines(text: str) -> list[tuple[str, int, str]]:
    """Every added line in the patch, as (path, line number after the patch, text)."""
    found: list[tuple[str, int, str]] = []
    current = ""
    number = 0
    for line in text.splitlines():
        header = FILE_RE.match(line)
        if header:
            current = header.group(1)
            continue
        hunk = HUNK_RE.match(line)
        if hunk:
            number = int(hunk.group(1))
            continue
        if not current or not number:
            continue
        if line.startswith("+"):
            found.append((current, number, line[1:]))
            number += 1
        elif line.startswith("-"):
            continue
        elif line.startswith(" ") or line == "":
            number += 1
    return found


def test_the_patch_and_the_run_script_exist() -> None:
    assert PATCH_PATH.is_file(), "tests/guard/redteam.patch is absent; GD-09 has nothing to plant"
    assert RUN_SCRIPT.is_file(), "tests/guard/redteam_run.sh is absent; GD-09 has no runner"


def test_both_target_files_exist() -> None:
    """A patch cannot plant a violation in a file that is not there."""
    for relative in TARGETS:
        assert (REPO_ROOT / relative).is_file(), f"{relative} is absent; the red team cannot run"


def test_the_patch_touches_exactly_the_two_named_files() -> None:
    touched = sorted({path for path, _, _ in planted_lines(patch_text())})
    assert touched == sorted(TARGETS), f"the patch touches {touched}"


def test_the_stored_patch_carries_no_literal_label() -> None:
    """The patch is scanned like any other file. It must pass GD-04 as stored."""
    stored = patch_text()
    assert PLACEHOLDER in stored, "the patch no longer uses the placeholder"
    assert not scan_text("tests/guard/redteam.patch", stored, boundary_date()), (
        "the stored patch would fail the scan it exists to test"
    )


def test_the_rendered_patch_plants_one_violation_in_each_file() -> None:
    """The plants, rendered in memory, caught by the scan, at the lines they land on."""
    boundary = boundary_date()
    caught: dict[str, list[int]] = {relative: [] for relative in TARGETS}
    for path, number, text in planted_lines(rendered_patch()):
        if path not in caught:
            continue
        for violation in scan_text(path, text + "\n", boundary):
            caught[path].append(number)
            assert violation.line == 1, "scan_text numbers lines from the text it is given"
    for relative in TARGETS:
        assert caught[relative], f"the patch plants nothing the scan bans in {relative}"
        assert relative not in ALLOWLIST, f"{relative} is allowlisted; the plant would be silenced"


@pytest.mark.parametrize("relative", TARGETS)
def test_the_planted_line_is_reported_by_file_and_line(relative: str) -> None:
    """The line number the run script asserts on is the line the plant lands on."""
    source = (REPO_ROOT / relative).read_text(encoding="utf-8").splitlines()
    plants = [
        (number, text) for path, number, text in planted_lines(rendered_patch()) if path == relative
    ]
    assert plants, f"no plant for {relative}"
    number, text = plants[0]
    assert 1 <= number <= len(source) + 1, (
        f"{relative}: the plant lands at line {number}, outside the file"
    )
    found = scan_text(relative, text + "\n", boundary_date())
    assert found, f"{relative}: the planted line is not a violation any more"


def test_the_run_script_is_real_and_runnable() -> None:
    """Not the Makefile placeholder, valid shell, and it reverts what it applies."""
    text = RUN_SCRIPT.read_text(encoding="utf-8")
    assert _PLACEHOLDER_MARKER not in text, (
        "tests/guard/redteam_run.sh is still the W1.14 placeholder"
    )
    assert "tests/guard/redteam.patch" in text, "the run script does not name the patch"
    assert "trap" in text, "the run script does not restore the worktree on an early exit"
    done = subprocess.run(
        ["sh", "-n", str(RUN_SCRIPT)], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr


def test_the_worktree_is_clean_of_the_plant_right_now() -> None:
    """Whatever ran before this, neither target file is carrying a planted read.

    A red-team run that died in the middle would leave one here. The scan would
    also catch it, but this says which file and why in one line.
    """
    boundary = boundary_date()
    for relative in TARGETS:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        found = scan_text(relative, text, boundary)
        assert not found, (
            f"{relative} carries a planted read; a red-team run did not revert, "
            "or this is the patched half of one that is still running:\n"
            + "\n".join(str(violation) for violation in found)
        )
