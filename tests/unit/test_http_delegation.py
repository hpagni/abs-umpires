"""W2.3: the delegation to W1.7's client is real and is enforced.

W2.3 adds no client. Its content is the proof that there is exactly one, that
the linter which enforces that is wired into the lint target, and that the
policy published in ``docs/legal.md`` is the policy the client enforces.

Everything here is offline. Nothing in this file opens a connection, and the
linter it runs does not either. See ``docs/data-contract.md``, section
"HTTP delegation (W2.3)".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

PY_CLIENT = REPO_ROOT / "src" / "absump" / "http.py"
R_CLIENT = REPO_ROOT / "R" / "lib" / "http.R"
LINT_HTTP = REPO_ROOT / "ops" / "lint_http.sh"
LINT = REPO_ROOT / "ops" / "lint.sh"
LEGAL = REPO_ROOT / "docs" / "legal.md"
CONTRACT = REPO_ROOT / "docs" / "data-contract.md"
THROTTLE = REPO_ROOT / "config" / "throttle.yml"


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(THROTTLE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# There are two call sites, and they are the ones named everywhere else
# ---------------------------------------------------------------------------


def test_the_two_call_sites_exist() -> None:
    assert PY_CLIENT.is_file(), "src/absump/http.py is missing (owner: W1.7)"
    assert R_CLIENT.is_file(), "R/lib/http.R is missing (owner: W1.7)"


def test_the_python_client_exports_get() -> None:
    from absump import http as client

    assert callable(client.get)
    assert "get" in client.__all__


def test_the_r_client_exports_absump_http_get() -> None:
    text = R_CLIENT.read_text(encoding="utf-8")
    assert "absump_http_get <- function(" in text


# ---------------------------------------------------------------------------
# The linter is wired into the lint target, and wired in hard
# ---------------------------------------------------------------------------


def test_lint_sh_runs_lint_http_sh() -> None:
    text = LINT.read_text(encoding="utf-8")
    assert "ops/lint_http.sh" in text, "ops/lint.sh does not run the http linter"


def test_a_missing_linter_fails_the_lint_run_rather_than_skipping() -> None:
    """The W1.7-era soft skip is gone. Absence of the linter is a failure."""
    text = LINT.read_text(encoding="utf-8")
    assert "not written yet" not in text
    assert "fails=$((fails + 1))" in text.split("http call sites", 1)[1]


def test_the_linter_passes_on_this_tree() -> None:
    assert LINT_HTTP.is_file(), "ops/lint_http.sh is missing (owner: W1.7)"
    done = subprocess.run(
        ["sh", str(LINT_HTTP), "-q", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "LINT HTTP OK" in done.stdout


def test_the_linter_still_fires_on_a_planted_call_site(tmp_path: Path) -> None:
    """A tree with a request idiom outside the two files must exit 1.

    Without this, a linter that silently scanned nothing would pass every
    other assertion in this file.
    """
    (tmp_path / "src" / "absump").mkdir(parents=True)
    (tmp_path / "src" / "absump" / "rogue.py").write_text(
        "import requests\n\n\ndef pull(url):\n    return requests.get(url)\n",
        encoding="utf-8",
    )
    done = subprocess.run(
        ["sh", str(LINT_HTTP), "-q", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "rogue.py" in done.stderr


# ---------------------------------------------------------------------------
# The published policy is the enforced policy
# ---------------------------------------------------------------------------


def test_legal_md_exists() -> None:
    assert LEGAL.is_file(), "docs/legal.md is missing (owner: W2.3)"


def test_legal_md_publishes_the_throttle_numbers(config: dict) -> None:
    text = LEGAL.read_text(encoding="utf-8")
    assert "4 s" in text
    assert "3,000" in text
    assert "10 s" in text
    assert "800" in text
    assert "500" in text
    assert config["user_agent"] in text


def test_legal_md_states_the_no_email_rule() -> None:
    text = LEGAL.read_text(encoding="utf-8")
    assert "No email address is ever sent" in text


def test_legal_md_sends_no_email_address() -> None:
    """The page that promises no email address must not carry one."""
    import re

    text = LEGAL.read_text(encoding="utf-8")
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)


def test_legal_md_names_both_call_sites() -> None:
    text = LEGAL.read_text(encoding="utf-8")
    assert "src/absump/http.py" in text
    assert "R/lib/http.R" in text


# ---------------------------------------------------------------------------
# The delegation is recorded where the next agent will look for it
# ---------------------------------------------------------------------------


def test_data_contract_records_the_delegation() -> None:
    assert CONTRACT.is_file(), "docs/data-contract.md is missing"
    text = CONTRACT.read_text(encoding="utf-8")
    assert "HTTP delegation (W2.3)" in text
    assert "absump.http.get()" in text
    assert "absump_http_get()" in text
    assert "ops/lint_http.sh" in text


@pytest.mark.parametrize(
    "step",
    ["W2.5", "W2.6", "W2.7", "W2.8", "W2.9", "W2.10", "W2.11", "W2.12", "W8.2", "W8.5"],
)
def test_every_planned_pulling_step_is_listed_with_its_client(step: str) -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    rows = [
        line
        for line in text.splitlines()
        if line.startswith("|") and line.split("|")[1].strip() == step
    ]
    assert len(rows) == 1, f"{step} is not listed once in the delegation table"
    assert "absump.http.get()" in rows[0]
