"""SOP step W1.13. The pre-commit config is a guard, so it gets a test.

`pre-commit run --all-files` proves the hooks pass on today's tree. It does not
prove the right hooks are configured: a hook deleted from the config makes the
run greener, not redder. These tests pin the hook set, the pinned revs and the
two flags the SOP names, `--maxkb=5120` and `--branch main`, and they exercise
the three local hooks against a tree built for the purpose.

`no-commit-to-branch` is the reason this file exists. It declares always_run, so
a run from a checkout of main always fails and the W1.13 verify command skips it
by name. Test 1 is what keeps that skip honest.
"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".pre-commit-config.yaml"

EXPECTED_REVS = {
    "https://github.com/pre-commit/pre-commit-hooks": "v6.0.0",
    "https://github.com/astral-sh/ruff-pre-commit": "v0.16.8",
    "https://github.com/gitleaks/gitleaks": "v8.30.1",
}

EXPECTED_HOOKS = {
    "trailing-whitespace",
    "end-of-file-fixer",
    "check-yaml",
    "check-toml",
    "check-merge-conflict",
    "check-added-large-files",
    "detect-private-key",
    "no-commit-to-branch",
    "ruff-check",
    "ruff-format",
    "no-raw-data",
    "http-etiquette",
    "nb-clean",
}


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def hooks(config):
    return {h["id"]: h for repo in config["repos"] for h in repo["hooks"]}


def test_every_sop_hook_is_configured(hooks):
    missing = EXPECTED_HOOKS - set(hooks)
    assert not missing, f"hooks named by SOP W1.13 are absent: {sorted(missing)}"


def test_gitleaks_is_configured(hooks):
    # Either id is the same gitleaks binary at the same tag. gitleaks-system uses
    # the one on PATH instead of building it with a Go toolchain this machine
    # does not have.
    assert {"gitleaks", "gitleaks-system"} & set(hooks)


def test_revs_are_the_pinned_tags(config):
    revs = {repo["repo"]: repo.get("rev") for repo in config["repos"]}
    for url, tag in EXPECTED_REVS.items():
        assert revs.get(url) == tag, f"{url} must stay pinned at {tag}"


def test_large_file_ceiling_is_5120_kb(hooks):
    assert hooks["check-added-large-files"]["args"] == ["--maxkb=5120"]


def test_main_is_protected(hooks):
    args = hooks["no-commit-to-branch"]["args"]
    assert args == ["--branch", "main"], "W1.13: main is reachable only through a pull request"


RENV_ACTIVATE = r"^renv/activate\.R$"


def test_trailing_whitespace_excludes_renv_activate(hooks):
    # renv::restore() regenerates renv/activate.R with trailing whitespace on
    # 344 lines, so without this exclude the first `make prove` of a fresh clone
    # fails W1.13 and the hook then repairs the file, hiding the cause from
    # every later run. renv owns that file's formatting; the hook does not.
    assert hooks["trailing-whitespace"].get("exclude") == RENV_ACTIVATE


def test_the_renv_exclude_is_the_only_one(config):
    # An exclude is an escape hatch. Exactly one path has earned it, and a
    # second one arriving without a test is the regression this pins.
    excluded = {
        h["id"]: h["exclude"] for repo in config["repos"] for h in repo["hooks"] if h.get("exclude")
    }
    assert excluded == {"trailing-whitespace": RENV_ACTIVATE}
    assert not config.get("exclude"), "a top-level exclude would silence every hook at once"


def test_renv_activate_is_committed_as_renv_writes_it(hooks):
    # The companion half of the exclude: the tracked file already carries the
    # trailing whitespace renv emits, so `renv::restore()` on a clean clone
    # rewrites it byte for byte and leaves the tree clean. If this ever reads
    # zero, someone stripped the file by hand and bootstrap will dirty the tree
    # again on the next restore.
    activate = ROOT / "renv" / "activate.R"
    lines = activate.read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if line != line.rstrip()) > 0


def test_ruff_check_fixes(hooks):
    assert "--fix" in hooks["ruff-check"]["args"]


def test_http_etiquette_runs_the_linter(hooks):
    assert hooks["http-etiquette"]["entry"] == "ops/lint_http.sh"


def test_local_hook_scripts_exist_and_are_executable(hooks):
    for hook_id in ("no-raw-data", "http-etiquette", "nb-clean"):
        script = ROOT / hooks[hook_id]["entry"]
        assert script.is_file(), f"{hook_id} points at a missing script: {script}"
        assert script.stat().st_mode & 0o111, f"{script} is not executable"


@pytest.mark.parametrize(
    "path",
    ["data/raw/statcast.parquet", "research/notes.md", "logs/evidence/W1.1.log", "RUNLOG.md"],
)
def test_no_raw_data_refuses(path):
    hook = ROOT / "ops" / "hook_no_raw_data.sh"
    assert subprocess.run([hook, path], capture_output=True, check=False).returncode == 1


@pytest.mark.parametrize(
    "path",
    ["app/data/park_factors.csv", "tests/data/dt_zone.csv", "src/absump/http.py", "datapack/x.md"],
)
def test_no_raw_data_allows(path):
    # app/data/ and tests/data/ are source. The match is on a first path segment,
    # so `datapack/` is not a `data/` hit either.
    hook = ROOT / "ops" / "hook_no_raw_data.sh"
    assert subprocess.run([hook, path], capture_output=True, check=False).returncode == 0


def test_nb_clean_strips_outputs_and_is_idempotent(tmp_path):
    hook = ROOT / "ops" / "hook_nb_clean.py"
    nb = tmp_path / "scratch.ipynb"
    nb.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "execution_count": 7,
                        "metadata": {"collapsed": True},
                        "outputs": [
                            {"output_type": "stream", "name": "stdout", "text": ["SECRET\n"]}
                        ],
                        "source": ["print(1)"],
                    }
                ],
                "metadata": {"widgets": {"state": "big"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    first = subprocess.run([hook, str(nb)], capture_output=True, check=False)
    assert first.returncode == 1, "a fixing hook exits non-zero so the commit stops"

    cleaned = json.loads(nb.read_text(encoding="utf-8"))
    cell = cleaned["cells"][0]
    assert cell["outputs"] == []
    assert cell["execution_count"] is None
    assert "collapsed" not in cell["metadata"]
    assert "widgets" not in cleaned["metadata"]
    assert "SECRET" not in nb.read_text(encoding="utf-8")

    second = subprocess.run([hook, str(nb)], capture_output=True, check=False)
    assert second.returncode == 0, "a second pass must find nothing left to strip"
