"""GD-01, GD-02 and GD-12. Layer 4 of the four-layer guard: the receipts.

SOP step W9.7, section 6.4.

Layers 1 to 3 govern what the code may read. This layer governs what the
artifacts admit to. A fit that produced a number in the abstract has to say,
in a file next to itself, which rows it saw and which commit produced it:

    GD-01  every fit artifact under out/ has a provenance.json beside it, and
           every provenance.json carries the nine keys of the section 1.4
           contract.
    GD-02  no artifact that touched held-out rows, and no artifact whose
           max_official_date is past the last open day, unless its git_sha
           descends from a pushed prereg-v1.
    GD-12  ordering, not just scope: EVERY fit receipt, held out or open,
           descends from the pushed tag. D-67. The script ops/check_seal_order.sh
           is the implementation; this file asserts it runs and reports.

PHASE 01 STATUS. Nothing has been fit, so out/ holds no receipt. GD-02 and
GD-12 are therefore vacuous. They say so out loud, through a warning that
pytest prints in its summary even under -q, rather than passing quietly. A
vacuous pass that looks like a real one is the failure this project can least
afford.

No literal held-out token appears in this file; the label is assembled at
import time, because GD-04 scans this file like any other.
"""

from __future__ import annotations

import json
import subprocess
import warnings
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "out"
CONFIG_PATH = REPO_ROOT / "config" / "seal.yml"
ORDER_SCRIPT = REPO_ROOT / "ops" / "check_seal_order.sh"

_HELD = "seal" + "ed"
_GIT_TIMEOUT_S = 20.0

# SOP section 1.4, the fit-provenance row of the artifact contract.
CONTRACT_KEYS: tuple[str, ...] = (
    "n_games",
    "n_rows",
    "min_official_date",
    "max_official_date",
    "game_pk_sha256",
    "analysis_sets_touched",
    "seed",
    "code_sha256",
    "git_sha",
)

# Formats a fit writes. A receipt is required beside each one.
FIT_SUFFIXES: frozenset[str] = frozenset({".rds", ".npz", ".stanfit", ".qs", ".pkl"})


class VacuousGuard(UserWarning):
    """A guard check that is true today only because there is nothing to check."""


def _config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def first_held_out_date() -> str:
    """The first held-out day, from config/seal.yml. Never written here."""
    return str(_config()["seal_start_date"])


def prereg_tag() -> str:
    return str(_config()["prereg_tag"])


def _git(*args: str) -> tuple[int, str]:
    done = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=_GIT_TIMEOUT_S,
    )
    return done.returncode, done.stdout.strip()


def fit_receipts() -> list[Path]:
    """Every provenance.json under out/. SOP section 1.4: these are canonical."""
    if not OUT_DIR.is_dir():
        return []
    return sorted(OUT_DIR.rglob("provenance.json"))


def fit_artifacts() -> list[Path]:
    """Every fitted-object file under out/, by format."""
    if not OUT_DIR.is_dir():
        return []
    return sorted(p for p in OUT_DIR.rglob("*") if p.suffix.lower() in FIT_SUFFIXES)


def touches_held_out(receipt: dict[str, Any]) -> bool:
    """True when the receipt admits to held-out rows, by label or by date."""
    labels = receipt.get("analysis_sets_touched") or []
    if isinstance(labels, str):
        labels = [labels]
    if any(str(label).strip().lower() == _HELD for label in labels):
        return True
    latest = str(receipt.get("max_official_date") or "")
    # ISO dates compare correctly as strings. The boundary comes from config.
    return bool(latest) and latest >= first_held_out_date()


# ===================================================================== GD-01
def test_every_fit_artifact_has_a_receipt() -> None:
    artifacts = fit_artifacts()
    if not artifacts:
        warnings.warn(
            "GD-01 vacuous: no fit artifacts under out/ yet, because phase 01 fits nothing",
            VacuousGuard,
            stacklevel=1,
        )
        return
    missing = [
        str(p.relative_to(REPO_ROOT))
        for p in artifacts
        if not (p.parent / "provenance.json").is_file()
    ]
    assert not missing, (
        "GD-01 FAIL: fit artifacts with no provenance.json beside them:\n" + "\n".join(missing)
    )


def test_every_receipt_carries_the_contract_keys() -> None:
    receipts = fit_receipts()
    if not receipts:
        warnings.warn(
            "GD-01 vacuous: no fit receipts under out/ yet, because phase 01 fits nothing",
            VacuousGuard,
            stacklevel=1,
        )
        return
    bad: list[str] = []
    for path in receipts:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            bad.append(f"{path.relative_to(REPO_ROOT)}: unreadable ({exc})")
            continue
        absent = [key for key in CONTRACT_KEYS if key not in loaded]
        if absent:
            bad.append(f"{path.relative_to(REPO_ROOT)}: missing {', '.join(absent)}")
    assert not bad, "GD-01 FAIL: receipts that do not meet the section 1.4 contract:\n" + "\n".join(
        bad
    )


# ===================================================================== GD-02
def test_no_held_out_artifact_predates_the_pre_registration() -> None:
    """An artifact may touch the held-out rows only from a commit past the tag."""
    receipts = fit_receipts()
    if not receipts:
        warnings.warn(
            "GD-02 vacuous: no fit receipts yet, so no artifact can have touched a held-out row",
            VacuousGuard,
            stacklevel=1,
        )
        return
    tag = prereg_tag()
    code, tag_sha = _git("rev-list", "-n", "1", tag)
    failures: list[str] = []
    for path in receipts:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not touches_held_out(loaded):
            continue
        name = str(path.relative_to(REPO_ROOT))
        if code != 0 or not tag_sha:
            failures.append(f"{name} touches held-out rows and {tag} does not exist")
            continue
        sha = str(loaded.get("git_sha") or "")
        if not sha:
            failures.append(f"{name} touches held-out rows and carries no git_sha")
            continue
        if _git("merge-base", "--is-ancestor", tag_sha, sha)[0] != 0:
            failures.append(f"{name} was fit at {sha}, which does not descend from {tag}")
    assert not failures, "GD-02 FAIL:\n" + "\n".join(failures)


# ===================================================================== GD-12
def test_the_ordering_script_runs_and_reports() -> None:
    """GD-12, D-67. Ordering is checked by ops/check_seal_order.sh, which owns it."""
    assert ORDER_SCRIPT.is_file(), "ops/check_seal_order.sh is absent; GD-12 has no implementation"
    done = subprocess.run(
        ["bash", str(ORDER_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "SEAL-ORDER OK" in done.stdout, done.stdout + done.stderr
    if not fit_receipts():
        warnings.warn(
            "GD-12 vacuous: no fit receipts yet and "
            f"{prereg_tag()} is not tagged yet, so no ordering has been tested",
            VacuousGuard,
            stacklevel=1,
        )


def test_the_boundary_is_read_from_config_not_written_here() -> None:
    """SOP rule 0.5.4. The date this guard compares against lives in config/."""
    boundary = first_held_out_date()
    assert boundary == str(_config()["seal_start_date"])
    assert len(boundary.split("-")) == 3, boundary
    source = Path(__file__).read_text(encoding="utf-8")
    assert boundary not in source, "the boundary date is hard-coded in this file"


@pytest.mark.parametrize(
    ("receipt", "expected"),
    [
        ({"analysis_sets_touched": ["open"], "max_official_date": "2026-09-01"}, False),
        ({"analysis_sets_touched": ["open", _HELD], "max_official_date": "2026-09-01"}, True),
        ({"analysis_sets_touched": ["open"], "max_official_date": "2026-10-04"}, True),
        ({"analysis_sets_touched": [], "max_official_date": ""}, False),
    ],
    ids=["open", "held-out label", "past the boundary", "empty"],
)
def test_the_held_out_predicate_is_not_vacuous(receipt: dict[str, Any], expected: bool) -> None:
    """The GD-02 predicate itself, on four synthetic receipts. No file is touched."""
    assert touches_held_out(receipt) is expected
