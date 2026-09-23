"""SOP step W1.14 gate: the Makefile.

Asserts four things, and nothing about what the delegated scripts do:

1. every target in the SOP W1.14 list exists and is reachable (`make -n <t>`);
2. the file is GNU Make 3.81 syntax, which is what ships with macOS (risk R-23);
3. the one-line-delegation rule holds -- every recipe is a single line that runs
   one command, so that the later steps which own a target's body write their
   script and never edit this file;
4. every script a target delegates to exists on disk and is not empty.

The canonical target list below is transcribed from SOP section W1.14. It is not
a number read from any endpoint. Adding a target to the Makefile without adding
it there fails `test_no_undeclared_targets`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"

# SOP W1.14, verbatim and in the SOP's own order.
SOP_TARGETS = [
    "help", "preflight", "bootstrap", "py", "r", "lint", "fmt",
    "test", "test-unit", "test-data", "test-model", "test-model-fast",
    "test-guard", "prove", "prove-guard-redteam", "determinism",
    "verify-env", "verify-contract",
    "smoke", "r-smoke", "dbt", "warehouse", "b2-push", "b2-pull",
    "disk", "disk-check", "seal-check", "preregister",
    "backfill", "inseason", "pull-today", "nightly", "canary", "lint-prose",
    "ch1", "test-ch1", "ch2", "test-ch2", "ch3", "test-ch3", "ch3-extract",
    "p8", "p8-test", "p8-odds-fetch", "p8-sealed",
    "app", "app-deploy", "abstract", "all",
    "clean", "clean-out", "clean-warehouse",
]  # fmt: skip

# `unseal` is SOP W2.4's target. It is not in the W1.14 list but the Makefile
# carries it for the same reason: W2.4 writes ops/unseal.sh, not this file.
EXTRA_TARGETS = ["unseal"]
ALL_TARGETS = SOP_TARGETS + EXTRA_TARGETS

# Targets that are cheap, offline and free of side effects, so the gate may run
# them for real. Everything else is proved by `make -n` only. `preregister` and
# `unseal` are one-way doors and are never run by a test.
RUNNABLE = ["help", "disk-check", "seal-check"]

# GNU Make 4 syntax. 3.81 either ignores these silently or errors on them.
MAKE4_SYNTAX = [
    (".ONESHELL", "recipe lines would stop being independent shells"),
    ("::=", "immediate assignment is GNU Make 4"),
    ("$(file", "the file function is GNU Make 4"),
    (".RECIPEPREFIX", "recipe prefix is GNU Make 3.82+"),
    (".SHELLFLAGS", "shell flags are GNU Make 3.82+"),
    ("&:", "grouped targets are GNU Make 4.3"),
]

# Shell logic that belongs in a script, not in a recipe.
LOGIC_TOKENS = ["&&", "||", ";", "|", "`", "$(shell", "if ", "for ", "while "]

MAKE = shutil.which("make")
needs_make = pytest.mark.skipif(MAKE is None, reason="make is not on PATH")


def read_makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def strip_comment(line: str) -> str:
    return line.split("##", 1)[0].split("#", 1)[0].rstrip()


def recipes() -> dict[str, list[str]]:
    """Map target name to its recipe lines, in file order."""
    out: dict[str, list[str]] = {}
    current = None
    for raw in read_makefile().splitlines():
        if raw.startswith("\t"):
            if current is not None:
                out[current].append(raw[1:])
            continue
        if raw.startswith(("#", " ")) or not raw.strip():
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*:(?!=)", raw)
        if match and not raw.startswith("."):
            current = match.group(1)
            out.setdefault(current, [])
        else:
            current = None
    return out


def test_makefile_exists() -> None:
    assert MAKEFILE.is_file(), f"{MAKEFILE} is missing"


def test_recipes_are_tab_indented() -> None:
    """No recipe is indented with spaces. Continuation lines of .PHONY are exempt."""
    bad = []
    continued = False
    for i, line in enumerate(read_makefile().splitlines(), 1):
        if not continued and line.startswith("    ") and not line.lstrip().startswith("#"):
            bad.append(i)
        continued = line.rstrip().endswith("\\")
    assert bad == [], f"space-indented recipe lines at {bad}; GNU Make needs tabs"


@pytest.mark.parametrize(("token", "why"), MAKE4_SYNTAX)
def test_no_gnu_make_4_syntax(token: str, why: str) -> None:
    body = "\n".join(strip_comment(line) for line in read_makefile().splitlines())
    assert token not in body, f"{token!r} is not GNU Make 3.81: {why}"


@pytest.mark.parametrize("target", ALL_TARGETS)
def test_target_is_defined(target: str) -> None:
    assert target in recipes(), f"target {target!r} is missing from the Makefile"


@pytest.mark.parametrize("target", ALL_TARGETS)
def test_target_is_phony(target: str) -> None:
    phony = " ".join(
        line for line in read_makefile().splitlines() if line.startswith((".PHONY", " " * 8))
    )
    assert f" {target} " in f" {phony.replace(chr(92), ' ')} ", f"{target} is not in .PHONY"


@pytest.mark.parametrize("target", ALL_TARGETS)
def test_recipe_is_one_delegating_line(target: str) -> None:
    body = recipes()[target]
    assert len(body) == 1, f"{target} has {len(body)} recipe lines; the rule is exactly one"
    line = body[0]
    assert line.strip(), f"{target} has an empty recipe; no target may silently do nothing"
    found = [t for t in LOGIC_TOKENS if t in line]
    assert found == [], f"{target} holds shell logic {found}; put it in the script"


def test_no_undeclared_targets() -> None:
    declared = set(ALL_TARGETS)
    found = set(recipes())
    assert found - declared == set(), "targets exist that the SOP list does not name"


def test_delegated_scripts_exist() -> None:
    missing = []
    for target, body in recipes().items():
        for word in body[0].split():
            if word.endswith((".sh", ".R")) and "/" in word:
                path = ROOT / word
                if not path.is_file() or path.stat().st_size == 0:
                    missing.append((target, word))
    assert missing == [], f"targets delegate to files that do not exist: {missing}"


@needs_make
@pytest.mark.parametrize("target", ALL_TARGETS)
def test_target_dry_runs(target: str) -> None:
    done = subprocess.run(
        [MAKE, "-n", target],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, f"make -n {target} failed: {done.stderr.strip()}"
    assert done.stdout.strip(), f"make -n {target} printed nothing"


@needs_make
def test_help_lists_every_target() -> None:
    done = subprocess.run(
        [MAKE, "help"], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    listed = {line.split()[0] for line in done.stdout.splitlines() if line.startswith("  ")}
    assert set(ALL_TARGETS) - listed == set(), "make help does not list every target"


@needs_make
@pytest.mark.parametrize("target", RUNNABLE)
def test_runnable_target_exits_zero(target: str) -> None:
    env = dict(os.environ)
    env.pop("ABS_SEAL_UNLOCK", None)
    done = subprocess.run(
        [MAKE, target],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env=env,
    )
    assert done.returncode == 0, f"make {target} exited {done.returncode}: {done.stderr.strip()}"
