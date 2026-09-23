"""W1.7 / W2.3. ops/lint_http.sh must catch every realistic way to leave the chokepoint.

SOP section 0.5 rule 2 allows exactly two files to issue an HTTP request:
``src/absump/http.py`` and ``R/lib/http.R``. The W1.7 / W2.3 verifier planted
thirty realistic bypasses and the linter caught three, so this module is the
test that can actually fail: every fixture under
``tests/unit/fixtures/lint_http/bypass`` is a file at a realistic repository
path whose second line leaves the chokepoint, and each one is asserted to be
reported with its own path and line number.

The fixtures live on disk rather than as string literals here, so the planted
material is all in one place: ``tests/unit/fixtures/lint_http/`` is exempt
because it is the planted material, and this module is exempt because the
receipt-log test below has to quote the linter's own recorded output back at
it. Nothing else under ``tests/`` is exempt.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_HTTP = REPO_ROOT / "ops" / "lint_http.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lint_http"
BYPASS = FIXTURES / "bypass"
ALLOWED = FIXTURES / "allowed"
MANIFEST = FIXTURES / "MANIFEST.tsv"

# The scan set the linter must cover, and the two allowed call sites.
EXPECTED_SCAN_DIRS = [
    "ops",
    "scripts",
    "R",
    "src",
    "app",
    "dbt",
    "notebooks",
    "tests",
    "tools",
    "sql",
    "quality",
]
EXPECTED_EXEMPT = (
    "ops/lint_http.sh",
    "ops/ci-pending/",
    "ops/env-setup.sh",
    "tests/unit/fixtures/lint_http/",
    "tests/unit/test_lint_http[a-z_]*.py",
    "tests/unit/test_http_etiquette.py",
    "tests/unit/test_http_delegation.py",
)


def read_manifest() -> list[tuple[str, int, str, str]]:
    rows = []
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        relpath, line, rule, note = raw.split("\t", 3)
        rows.append((relpath, int(line), rule, note))
    return rows


MANIFEST_ROWS = read_manifest()


def run_lint(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(LINT_HTTP), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


@pytest.fixture(scope="module")
def planted(tmp_path_factory: pytest.TempPathFactory) -> subprocess.CompletedProcess:
    """Copy every bypass fixture into one tree, with both allowed sites present."""
    root = tmp_path_factory.mktemp("planted")
    shutil.copytree(ALLOWED, root, dirs_exist_ok=True)
    shutil.copytree(BYPASS, root, dirs_exist_ok=True)
    result = run_lint("-q", str(root))
    assert result.returncode == 1, (
        "the linter passed a tree holding every planted bypass\n" + result.stdout
    )
    return result


def test_the_manifest_is_not_empty_and_matches_the_fixture_tree() -> None:
    on_disk = {
        str(p.relative_to(BYPASS))
        for p in BYPASS.rglob("*")
        if p.is_file() and p.name != ".DS_Store"
    }
    assert on_disk, "no bypass fixtures on disk"
    assert on_disk == {row[0] for row in MANIFEST_ROWS}, (
        "MANIFEST.tsv and the fixture tree disagree"
    )
    assert len(MANIFEST_ROWS) >= 30, "the verifier planted thirty; cover at least that"


@pytest.mark.parametrize(
    ("relpath", "line", "rule"),
    [(r[0], r[1], r[2]) for r in MANIFEST_ROWS],
    ids=[r[0] for r in MANIFEST_ROWS],
)
def test_each_planted_bypass_is_flagged_with_file_and_line(
    planted: subprocess.CompletedProcess, relpath: str, line: int, rule: str
) -> None:
    """Every fixture is reported as path:line, by the rule the manifest names."""
    stderr = planted.stderr
    needle = f"{relpath}:{line}:"
    assert needle in stderr, f"not flagged at all: {needle}"
    hit = [ln for ln in stderr.splitlines() if needle in ln]
    assert any(f"[{rule}]" in ln for ln in hit), f"{needle} was flagged, but not by {rule}: {hit}"


def test_the_two_allowed_call_sites_are_never_flagged(tmp_path: Path) -> None:
    """A tree holding only the chokepoint files passes, idioms and all."""
    shutil.copytree(ALLOWED, tmp_path, dirs_exist_ok=True)
    result = run_lint("-q", str(tmp_path))
    assert result.returncode == 0, "the two allowed call sites were flagged\n" + result.stderr
    assert "LINT HTTP OK" in result.stdout


def test_the_allowed_sites_are_not_flagged_even_beside_a_bypass(
    planted: subprocess.CompletedProcess,
) -> None:
    for allowed in ("src/absump/http.py:", "R/lib/http.R:"):
        assert allowed not in planted.stderr, f"{allowed} was reported"


def test_the_linter_scans_every_directory_that_holds_code() -> None:
    text = LINT_HTTP.read_text(encoding="utf-8")
    listed = run_lint("-l")
    assert listed.returncode == 0, listed.stderr
    for name in EXPECTED_SCAN_DIRS:
        assert f" {name}" in listed.stdout.split("scan dirs:")[1], f"{name}/ is not in the scan set"
    assert "scan files: Makefile" in listed.stdout, "the Makefile is not scanned"
    assert "src/absump/http\\.py" in text and "R/lib/http\\.R" in text


def test_the_exemption_list_is_exactly_the_six_documented_paths() -> None:
    """Exemptions are how this guard is quietly disabled, so they are pinned."""
    text = LINT_HTTP.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith("EXEMPT="))
    raw = line.split("=", 1)[1].strip("'")
    got = [part.lstrip("^").replace("\\", "").rstrip(":") for part in raw.split("|")]
    assert sorted(got) == sorted(EXPECTED_EXEMPT), f"the exemption list changed: {got}"


def test_the_six_idioms_section_2_3_names_are_still_rules() -> None:
    """Widening the guard must not drop the SOP's own acceptance criterion."""
    text = LINT_HTTP.read_text(encoding="utf-8")
    for idiom in ("requests", "httpx", "urllib", "curl", "httr2"):
        assert idiom in text, f"section 2.3 names {idiom} and it is not a rule"


# What a receipt log holds after a failing run: this linter's own output, one
# "[RULE] path:line:text" line per hit, naming files that may since have gone.
RECORDED_FAILURE = """LINT HTTP FAIL: request idiom outside the two allowed call sites.
  [ANY-URLREAD] src/absump/ingest/deleted.py:3:frame = read_csv_auto('https://statsapi.mlb.com/feed.csv')
  [ANY-HTTPFS] sql/deleted.sql:2:INSTALL httpfs; SELECT * FROM read_csv_auto('https://statsapi.mlb.com/feed.csv');
  [ANY-USERINFO] tools/deleted.py:1:URL = "https://someone:token@statsapi.mlb.com/api/v1/schedule"
  [ANY-ODDSKEY] tools/deleted.py:2:ODDS = "https://api.the-odds-api.com/v4/sports?apiKey=xxxxxxxxxxxxxxxx"
Allowed: src/absump/http.py and R/lib/http.R.
"""


def test_a_receipt_log_does_not_trigger_the_linter_on_its_own_output(
    tmp_path: Path,
) -> None:
    """One failing run must not disable the gate for good.

    quality/ is scanned, and quality/receipts/<step>.log records this linter's
    own failure output verbatim. The round-2 verifier found that after a single
    failure the linter read its own complaint back and failed on it every run
    afterwards, naming files that no longer existed, so the gate could only be
    cleared by restoring a receipt by hand. A receipt is evidence, not code.
    """
    shutil.copytree(ALLOWED, tmp_path, dirs_exist_ok=True)
    receipts = tmp_path / "quality" / "receipts"
    receipts.mkdir(parents=True)
    (receipts / "W1.7.log").write_text(RECORDED_FAILURE, encoding="utf-8")
    (receipts / "W1.7.json").write_text(
        '{"step": "W1.7", "status": "FAIL", "log": "quality/receipts/W1.7.log"}\n',
        encoding="utf-8",
    )
    result = run_lint("-q", str(tmp_path))
    assert result.returncode == 0, (
        "the linter read a receipt log and failed on its own recorded output\n" + result.stderr
    )


def test_the_round_two_shapes_are_each_a_named_rule() -> None:
    """The three shapes the round-2 verifier got through with, pinned by rule id."""
    listed = run_lint("-l")
    assert listed.returncode == 0, listed.stderr
    for rule_id in ("PY-DYNIMPORT", "SH-EXECVAR", "SH-CONCAT", "SH-PYTHON-C"):
        assert rule_id in listed.stdout, f"{rule_id} is not in the rule table"
    text = LINT_HTTP.read_text(encoding="utf-8")
    python_c = next(ln for ln in text.splitlines() if ln.startswith("rule SH-PYTHON-C"))
    body = text.split(python_c, 1)[1].split("rule R-RSCRIPT", 1)[0]
    assert body.rstrip().endswith("file"), (
        "SH-PYTHON-C reads its conjunct on the matched line, so a here-doc whose "
        "program text is on the following lines is invisible to it"
    )


def test_the_live_repository_is_clean() -> None:
    result = run_lint()
    assert result.returncode == 0, result.stderr
    assert "LINT HTTP OK" in result.stdout
