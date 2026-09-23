"""GD-06 and GD-10. The seal itself: what is under data/sealed/, and whether it moved.

SOP step W9.7, section 6.4.

    GD-06  seal immutability against quality/sealed_manifest.json. The manifest
           is the record of what was sealed. The guard recomputes the record
           from the directory and fails on drift in either direction: a file
           under the root that the manifest does not list, a listed file that
           is gone, or a listed file whose bytes changed. One-way: the manifest
           is written once, at the seal event, and never edited afterwards.
    GD-10  data/sealed/ holds zero *.parquet and zero *.json.zst, and the seal
           log carries no UNSEALED line.

WHY BOTH DIRECTIONS. A manifest that only checks "every listed file is still
there" catches a deletion and misses an insertion, and an insertion is how an
open row would reach the sealed side, or a sealed row an open directory, after
the count in the pre-registration was published.

PHASE 01 STATUS, AND ITS EXPIRY. Nothing has been sealed. data/sealed/ is empty
and the vacuity is declared rather than hidden (VacuousGuard). It is not
permanent: test_the_vacuity_expires_when_the_seal_carries_rows is inert while
the partition is empty and becomes a hard assertion the moment it is not, so
the phase-02 pull cannot land rows while GD-06 compares nothing to nothing.
The original note follows. data/sealed/ is empty and the
manifest lists nothing, so the recomputation compares two empty sets. That is a
real check of an empty state, not a check that was skipped, but it proves
nothing about a populated seal, so GD-10 says so through a warning that pytest
prints in its summary even under -q. The drift detector is exercised on
synthetic files in tmp_path, so the comparison itself is tested today.

data/ is gitignored and never enters git in any form (D-03). This file reads
the directory listing and file bytes under data/sealed/ only. It parses no
2026 datum, which phase 01 forbids: an encrypted archive has no rows to parse.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "quality" / "sealed_manifest.json"
CONFIG_PATH = REPO_ROOT / "config" / "seal.yml"
SEAL_LOG = REPO_ROOT / "docs" / "prereg" / "SEAL.md"

SCHEMA = "absump/sealed_manifest@1"
HASH_ALGORITHM = "sha256"
SEALED_ROOT = "data/sealed"
ENTRY_KEYS: tuple[str, ...] = ("path", "bytes", "sha256")

# GD-10: the two formats a row can arrive in. Neither may be under the root in
# plaintext; the sealed archive is encrypted and carries its own suffix.
BANNED_SEALED_PATTERNS: tuple[str, ...] = ("*.parquet", "*.json.zst")

# Not data: the directory placeholder git needs to keep an empty directory.
IGNORED_NAMES: frozenset[str] = frozenset({".gitkeep", ".DS_Store"})


class VacuousGuard(UserWarning):
    """A guard check that is true today only because there is nothing to check."""


def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def files_under(root: Path) -> list[Path]:
    """Every real file under the root, minus placeholders. Sorted, recursive."""
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink() and p.name not in IGNORED_NAMES
    )


def drift(root: Path, entries: list[dict[str, Any]], base: Path) -> list[str]:
    """Recompute the manifest from the directory and report every disagreement.

    `root` is the directory to walk, `base` the directory the entry paths are
    written relative to. Returns one line per disagreement, empty when the
    manifest and the directory are the same set with the same bytes.
    """
    problems: list[str] = []
    on_disk = {str(p.relative_to(base)): p for p in files_under(root)}
    listed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = str(entry.get("path", ""))
        if name in listed:
            problems.append(f"listed twice: {name}")
        listed[name] = entry

    for name in sorted(set(on_disk) - set(listed)):
        problems.append(f"under the seal and not in the manifest: {name}")
    for name in sorted(set(listed) - set(on_disk)):
        problems.append(f"in the manifest and not under the seal: {name}")
    for name in sorted(set(listed) & set(on_disk)):
        path, entry = on_disk[name], listed[name]
        size = path.stat().st_size
        if int(entry.get("bytes", -1)) != size:
            problems.append(f"size changed: {name} manifest={entry.get('bytes')} disk={size}")
            continue
        if str(entry.get(HASH_ALGORITHM, "")) != sha256_of(path):
            problems.append(f"bytes changed: {name}")
    return problems


# ===================================================================== GD-06
def test_the_manifest_exists_and_parses() -> None:
    assert MANIFEST_PATH.is_file(), (
        "quality/sealed_manifest.json is absent; GD-06 has no record to check"
    )
    loaded = manifest()
    assert loaded["schema"] == SCHEMA
    assert loaded["hash_algorithm"] == HASH_ALGORITHM
    assert loaded["root"] == SEALED_ROOT
    assert isinstance(loaded["entries"], list)
    assert isinstance(loaded["game_count"], int) and loaded["game_count"] >= 0


def test_the_manifest_agrees_with_the_seal_config() -> None:
    """SOP rule 0.5.4: the constants live in config/seal.yml, here by reference."""
    loaded, config = manifest(), _config()
    assert loaded["seal_start_date"] == str(config["seal_start_date"])
    assert loaded["prereg_tag"] == str(config["prereg_tag"])
    assert loaded["seal_start_date_source"].startswith("config/seal.yml")
    assert loaded["prereg_tag_source"].startswith("config/seal.yml")


def test_every_entry_is_well_formed() -> None:
    bad: list[str] = []
    for index, entry in enumerate(manifest()["entries"]):
        absent = [key for key in ENTRY_KEYS if key not in entry]
        if absent:
            bad.append(f"entry {index}: missing {', '.join(absent)}")
            continue
        name = str(entry["path"])
        if not name.startswith(f"{SEALED_ROOT}/"):
            bad.append(f"entry {index}: {name} is not under {SEALED_ROOT}/")
        if len(str(entry[HASH_ALGORITHM])) != 64:
            bad.append(f"entry {index}: {name} has no {HASH_ALGORITHM} digest")
    assert not bad, "GD-06 FAIL:\n" + "\n".join(bad)


def test_the_manifest_matches_the_directory_in_both_directions() -> None:
    entries = manifest()["entries"]
    problems = drift(REPO_ROOT / SEALED_ROOT, entries, REPO_ROOT)
    assert not problems, "GD-06 FAIL: the seal and its manifest disagree:\n" + "\n".join(problems)
    if not entries:
        assert manifest()["game_count"] == 0, "an empty manifest claims a game count"
        assert manifest()["frozen_at"] is None, "an empty manifest claims a freeze time"


@pytest.mark.parametrize(
    "tamper",
    ["insert", "delete", "edit"],
    ids=["a file appears", "a file disappears", "bytes change"],
)
def test_the_drift_detector_catches_tampering(tmp_path: Path, tamper: str) -> None:
    """The comparison, on synthetic files. Nothing in data/ is touched."""
    root = tmp_path / SEALED_ROOT
    root.mkdir(parents=True)
    kept = root / "archive.tar.age"
    kept.write_bytes(b"ciphertext")
    entries = [
        {
            "path": f"{SEALED_ROOT}/archive.tar.age",
            "bytes": kept.stat().st_size,
            HASH_ALGORITHM: sha256_of(kept),
        }
    ]
    assert drift(root, entries, tmp_path) == [], "a truthful manifest reported drift"

    if tamper == "insert":
        (root / "extra.tar.age").write_bytes(b"who put this here")
    elif tamper == "delete":
        kept.unlink()
    else:
        kept.write_bytes(b"ciphertext, edited")

    problems = drift(root, entries, tmp_path)
    assert problems, f"the drift detector missed {tamper}"


# ===================================================================== GD-10
def test_the_seal_holds_no_readable_rows() -> None:
    root = REPO_ROOT / SEALED_ROOT
    found: list[str] = []
    for pattern in BANNED_SEALED_PATTERNS:
        found.extend(str(p.relative_to(REPO_ROOT)) for p in root.rglob(pattern))
    assert not found, "GD-10 FAIL: readable rows under the seal:\n" + "\n".join(sorted(found))
    if not files_under(root):
        warnings.warn(
            "GD-10 vacuous: no sealed rows yet, data/sealed/ is empty in phase 01",
            VacuousGuard,
            stacklevel=1,
        )


def test_the_vacuity_expires_when_the_seal_carries_rows() -> None:
    """The expiry. Phase 01 declares GD-06/GD-10 vacuous because data/sealed/ is empty.

    That is honest now and dangerous later: the moment the phase-02 pull seals real
    rows, an empty manifest would let `drift` compare nothing against nothing and
    report GD-06 green while the containment check slept. This test is the alarm
    clock. It is inert while the partition is empty and becomes a hard assertion
    the instant it is not, so phase 02 cannot begin with the guard asleep.
    """
    sealed = files_under(REPO_ROOT / SEALED_ROOT)
    if not sealed:
        return
    loaded = manifest()
    entries = loaded["entries"]
    assert entries, (
        f"GD-06 FAIL: {SEALED_ROOT}/ carries {len(sealed)} file(s) but "
        "quality/sealed_manifest.json lists no entries. The vacuity declared for "
        "phase 01 has expired: the manifest must record what was sealed before the "
        "drift check means anything."
    )
    assert loaded["game_count"] > 0, (
        "GD-06 FAIL: the seal carries rows and the manifest claims game_count 0"
    )
    assert loaded["frozen_at"] is not None, (
        "GD-06 FAIL: the seal carries rows and the manifest records no freeze time"
    )


def test_the_seal_log_records_no_unsealing() -> None:
    assert SEAL_LOG.is_file(), (
        f"{SEAL_LOG.relative_to(REPO_ROOT)} is absent; GD-10 has no log to read"
    )
    # An event line is appended at column zero and carries real values. The
    # indented line in the "The unseal" section is the form, with placeholders
    # in angle brackets, and is not an event.
    opened = [
        f"{number}: {line.strip()}"
        for number, line in enumerate(SEAL_LOG.read_text(encoding="utf-8").splitlines(), start=1)
        if line.strip().startswith("UNSEALED") and "<" not in line
    ]
    assert not opened, "GD-10 FAIL: the seal log records an unsealing:\n" + "\n".join(opened)
