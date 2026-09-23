"""GD-11. The dev DuckDB target has no attached database resolving under data/sealed/.

SOP step W9.7, section 6.4.

Layer 1 of the guard says model code reads only the open views. That holds only
if the warehouse the models run against cannot see a sealed file at all. A
dbt-duckdb target can `attach:` another database and expose its tables under a
schema, and a model reading `sealed_db.main.something` would never mention the
held-out view, the held-out label or the boundary date, so the static scan
would not see it either. This is the hole that layer 1 alone leaves open.

The rule: no target may attach, or point its own path at, anything that
resolves under `data/sealed/`. The exception, by name, is the `sealed` target,
which exists for the post-unseal build the owner runs by hand after the
ceremony, and which is checked only for its path, not silenced.

Every profiles file on this machine that defines the project's profile is
checked: the committed example, an uncommitted `dbt/profiles.yml`, and
`~/.dbt/profiles.yml` when it exists. A leak in any of them is a leak.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_NAME = "absump"
SEALED_ROOT = "data/sealed"
GUARDED_TARGETS: tuple[str, ...] = ("dev", "ci", "prod")

CANDIDATE_PROFILES: tuple[Path, ...] = (
    REPO_ROOT / "dbt" / "profiles.yml.example",
    REPO_ROOT / "dbt" / "profiles.yml",
    Path.home() / ".dbt" / "profiles.yml",
)


def profile_files() -> list[Path]:
    return [p for p in CANDIDATE_PROFILES if p.is_file()]


def outputs(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile = loaded.get(PROFILE_NAME) or {}
    return profile.get("outputs") or {}


def strings_in(value: Any) -> list[str]:
    """Every string anywhere in a nested mapping or list."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in strings_in(item)]
    if isinstance(value, (list, tuple)):
        return [s for item in value for s in strings_in(item)]
    return []


def resolves_under_seal(value: str) -> bool:
    """True when the string names a path under the sealed root, however written."""
    text = value.strip()
    if not text or text.startswith("md:") or text == ":memory:":
        return False
    candidate = Path(text)
    absolute = candidate if candidate.is_absolute() else (REPO_ROOT / candidate)
    try:
        resolved = absolute.resolve()
    except OSError:
        return False
    sealed = (REPO_ROOT / SEALED_ROOT).resolve()
    return resolved == sealed or sealed in resolved.parents


def test_a_profile_exists_to_check() -> None:
    assert profile_files(), "no dbt profile on this machine; GD-11 has nothing to check"


@pytest.mark.parametrize("target", GUARDED_TARGETS)
def test_no_guarded_target_attaches_a_database(target: str) -> None:
    """dbt-duckdb `attach:` is the quiet path to a sealed table. No target takes it."""
    failures: list[str] = []
    for path in profile_files():
        config = outputs(path).get(target)
        if not isinstance(config, dict):
            continue
        attached = config.get("attach")
        if attached:
            failures.append(f"{path}: target {target} attaches {attached}")
    assert not failures, "GD-11 FAIL:\n" + "\n".join(failures)


@pytest.mark.parametrize("target", GUARDED_TARGETS)
def test_no_guarded_target_resolves_under_the_seal(target: str) -> None:
    """Not just `path`: any string in the target that lands under data/sealed/."""
    failures: list[str] = []
    for path in profile_files():
        config = outputs(path).get(target)
        if not isinstance(config, dict):
            continue
        for value in strings_in(config):
            if resolves_under_seal(value):
                failures.append(
                    f"{path}: target {target} names {value}, which is under {SEALED_ROOT}/"
                )
    assert not failures, "GD-11 FAIL:\n" + "\n".join(failures)


def test_the_dev_target_is_defined_and_is_the_default() -> None:
    """The check is worth nothing if `dev` is not the target a bare dbt run uses."""
    for path in profile_files():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        profile = loaded.get(PROFILE_NAME)
        if not profile:
            continue
        assert profile.get("target") == "dev", f"{path}: the default target is not dev"
        assert "dev" in (profile.get("outputs") or {}), f"{path}: no dev target"


def test_the_seal_resolver_is_not_vacuous(tmp_path: Path) -> None:
    """The predicate itself, on strings that must and must not trip it.

    The warehouse path is read from the profile rather than written here: the
    one-copy rule of W1.6 keeps every layout string in src/absump/paths.py, and
    tests/unit/test_paths.py fails on a second copy anywhere in the tree.
    """
    assert resolves_under_seal(f"{SEALED_ROOT}/mlb-2026.duckdb")
    assert resolves_under_seal(f"./{SEALED_ROOT}/nested/inner.duckdb")
    assert resolves_under_seal(str(REPO_ROOT / SEALED_ROOT / "abs.duckdb"))
    assert not resolves_under_seal(":memory:")
    assert not resolves_under_seal("md:absump")
    assert not resolves_under_seal(str(tmp_path / "elsewhere.duckdb"))
    warehouse = str(outputs(profile_files()[0]).get("dev", {}).get("path", ""))
    assert warehouse, "the dev target names no path"
    assert not resolves_under_seal(warehouse), f"the dev path {warehouse} is under the seal"
