"""DT gate for SOP step W1.9, the Backblaze B2 private mirror of data/raw.

The SOP fixes three live assertions for this file: bucketType == allPrivate,
that 20 random objects match their manifest sha256, and that no object key
carries the held-out plain partition. All three need an account, and the
account is an owner item, so all three skip when B2_APPLICATION_KEY_ID and
B2_APPLICATION_KEY are unset.

Everything the SOP fixes that does NOT need an account is asserted here too,
against the shipped scripts and against their behaviour on a planted tree: the
bucket type literal, the two lifecycle rules field by field, the CI key
capability list and the absence of deleteFiles, the sync source and
destination, the canary key shape and its round-trip comparison, and the
refusal that stops the mirror before a byte is sent. Those run everywhere, so
the gate is red when the step is broken whether or not a key is on the machine.

No credential is read from the repository and none is ever written to it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "ops" / "b2_sync.sh"
CHECK = ROOT / "ops" / "b2_check.sh"
ENV_EXAMPLE = ROOT / ".env.example"
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "_manifest.csv"

BUCKET = "abs-umpires-raw"
PREFIX = "raw"

# The held-out plain partition, as one string, so no test builds it beside a
# reader call. It is never mirrored and no object key may carry it.
PLAIN_PARTITION = "sealed/plain"

# SOP W1.9, the fourth command, byte for byte. ops/b2_sync.sh prints this line
# on a default dry run.
SYNC_COMMAND = "uv run b2 sync --delete --threads 4 data/raw b2://abs-umpires-raw/raw"

# SOP W1.9, the third command. No deleteFiles.
CI_KEY_NAME = "abs-umpires-ci"
CI_KEY_CAPS = "listBuckets,readFiles,writeFiles,listFiles"

# SOP W1.9, the two lifecycle rules of the second command.
LIFECYCLE_EXPECTED = [
    {
        "fileNamePrefix": "",
        "daysFromUploadingToHiding": None,
        "daysFromHidingToDeleting": 30,
    },
    {
        "fileNamePrefix": "interim/",
        "daysFromUploadingToHiding": 90,
        "daysFromHidingToDeleting": 7,
    },
]

# A B2 application key id is "00" followed by lowercase hex. This is the shape
# .gitleaks.toml carries for the same rule, SOP W1.12: \b00[0-9a-f]{22}\b.
KEY_ID_SHAPE = re.compile(r"\b00[0-9a-f]{22,}\b")

HAVE_CREDS = bool(os.environ.get("B2_APPLICATION_KEY_ID")) and bool(
    os.environ.get("B2_APPLICATION_KEY")
)
needs_account = pytest.mark.skipif(
    not HAVE_CREDS,
    reason="B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY are unset; the account is an owner item",
)


def offline_env() -> dict[str, str]:
    """The process environment with both B2 names removed.

    The offline tests must behave the same on a machine that has the key and on
    one that does not, so they strip it rather than hope it is absent.
    """
    env = dict(os.environ)
    env.pop("B2_APPLICATION_KEY_ID", None)
    env.pop("B2_APPLICATION_KEY", None)
    return env


def run_script(script: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(ROOT),
        env=env if env is not None else offline_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )


def sync_source() -> str:
    return SYNC.read_text(encoding="utf-8")


def lifecycle_rules_in_sync() -> list[dict]:
    """The two lifecycle rules ops/b2_sync.sh passes to b2 bucket create."""
    found = []
    for line in sync_source().splitlines():
        match = re.match(r"^LIFECYCLE_[A-Z]+='(\{.*\})'$", line)
        if match:
            found.append(json.loads(match.group(1)))
    return found


def every_lifecycle_literal() -> list[dict]:
    """Every lifecycle JSON literal anywhere in the script, comments included."""
    pattern = r"'(\{\"fileNamePrefix\"[^']*\})'"
    return [json.loads(m.group(1)) for m in re.finditer(pattern, sync_source())]


def key_create_lines() -> list[str]:
    """Every line of ops/b2_sync.sh that names the b2 key create subcommand."""
    return [ln for ln in sync_source().splitlines() if "b2 key create" in ln]


# ---------------------------------------------------------------- the files --


def test_both_scripts_exist_and_are_executable():
    for script in (SYNC, CHECK):
        assert script.is_file(), f"{script} is missing"
        assert os.access(script, os.X_OK), f"{script} is not executable"


def test_no_b2_credential_is_written_into_the_repository():
    for path in (SYNC, CHECK, ENV_EXAMPLE, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert not KEY_ID_SHAPE.search(text), f"{path} carries something shaped like a B2 key id"


def test_env_example_carries_both_names_with_no_value():
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    for name in ("B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY"):
        assert f"{name}=" in lines, f".env.example has no empty {name} line"


# ------------------------------------------------------- the bucket contract --


def test_the_bucket_is_created_private():
    text = sync_source()
    assert "allPrivate" in text, "ops/b2_sync.sh does not create the bucket allPrivate"
    assert "allPublic" not in text, "ops/b2_sync.sh names a public bucket type"


def test_server_side_encryption_is_sse_b2():
    assert "SSE-B2" in sync_source()


def test_the_two_lifecycle_rules_are_the_sop_rules():
    rules = lifecycle_rules_in_sync()
    assert rules == LIFECYCLE_EXPECTED, f"lifecycle rules drifted from SOP W1.9: {rules}"


def test_no_lifecycle_literal_anywhere_in_the_script_disagrees():
    literals = every_lifecycle_literal()
    assert literals, "ops/b2_sync.sh carries no lifecycle rule"
    for rule in literals:
        assert rule in LIFECYCLE_EXPECTED, f"a lifecycle literal drifted from SOP W1.9: {rule}"


def test_the_ci_key_has_no_delete_capability():
    text = sync_source()
    assert CI_KEY_NAME in text, "the CI key name is not in ops/b2_sync.sh"
    assert f"CI_KEY_CAPS={CI_KEY_CAPS}\n" in text, f"the capability list is not {CI_KEY_CAPS}"
    assert "deleteFiles" not in CI_KEY_CAPS
    lines = key_create_lines()
    assert lines, "ops/b2_sync.sh never runs b2 key create"
    for line in lines:
        assert "deleteFiles" not in line, f"a key create line carries deleteFiles: {line}"


def test_provision_prints_the_bucket_and_key_commands():
    done = run_script(SYNC, "--provision", "--dry-run")
    assert done.returncode == 0, done.stderr
    out = done.stdout
    assert f"uv run b2 bucket create {BUCKET} allPrivate" in out
    created = f"uv run b2 key create --bucket {BUCKET} {CI_KEY_NAME} {CI_KEY_CAPS}"
    assert created in out
    for line in out.splitlines():
        if "b2 key create" in line:
            assert "deleteFiles" not in line, line


# ------------------------------------------------------------ the dry run ----


def test_the_dry_run_prints_the_sop_sync_command():
    done = run_script(SYNC, "--dry-run")
    assert done.returncode == 0, done.stderr
    printed = [ln for ln in done.stdout.splitlines() if ln.startswith("command: ")]
    # Whole line, not a substring: b2://abs-umpires-raw/raw-oops contains the
    # right destination as a prefix and is the wrong destination.
    assert printed == [f"command: {SYNC_COMMAND}"], done.stdout
    assert "DEFERRED" in done.stdout


def test_the_dry_run_sends_nothing_and_changes_no_byte(tmp_path):
    # Against a tree this test owns, not data/raw: the overnight puller writes
    # into data/raw while the gate runs, and a race is not an assertion.
    plant(tmp_path, "statsapi.mlb.com", "10", "one.zst")
    before = {
        q.relative_to(tmp_path).as_posix(): q.read_bytes()
        for q in tmp_path.rglob("*")
        if q.is_file()
    }
    done = run_script(SYNC, "--dry-run", f"--source={tmp_path}")
    assert done.returncode == 0, done.stderr
    after = {
        q.relative_to(tmp_path).as_posix(): q.read_bytes()
        for q in tmp_path.rglob("*")
        if q.is_file()
    }
    assert before == after


def test_source_is_refused_without_dry_run(tmp_path):
    done = run_script(SYNC, f"--source={tmp_path}")
    assert done.returncode == 2
    assert "--dry-run" in done.stderr


# --------------------------------------------------------- the never-mirror --


def plant(tmp_path: Path, *parts: str) -> Path:
    target = tmp_path.joinpath(*parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x" * 16)
    return target


def test_a_clean_tree_passes_the_never_mirror_check(tmp_path):
    plant(tmp_path, "statcast", "2026-09-21.csv.zst")
    done = run_script(SYNC, "--dry-run", f"--source={tmp_path}")
    assert done.returncode == 0, done.stderr
    assert "never-mirror check OK" in done.stdout
    assert "plan 1 file(s)" in done.stdout


def test_the_held_out_plain_partition_refuses_the_whole_sync(tmp_path):
    plant(tmp_path, "statcast", "2026-09-21.csv.zst")
    plant(tmp_path, *PLAIN_PARTITION.split("/"), "pitch.parquet")
    done = run_script(SYNC, "--dry-run", f"--source={tmp_path}")
    assert done.returncode == 1, done.stdout
    assert "REFUSED" in done.stderr
    assert "pitch.parquet" in done.stderr
    assert "nothing was sent" in done.stderr
    assert SYNC_COMMAND not in done.stdout


def test_a_duckdb_file_refuses_the_whole_sync(tmp_path):
    plant(tmp_path, "statcast", "2026-09-21.csv.zst")
    plant(tmp_path, "abs.duckdb")
    done = run_script(SYNC, "--dry-run", f"--source={tmp_path}")
    assert done.returncode == 1, done.stdout
    assert "REFUSED" in done.stderr
    assert "abs.duckdb" in done.stderr


def test_a_duckdb_write_ahead_log_refuses_the_whole_sync(tmp_path):
    plant(tmp_path, "abs.duckdb.wal")
    done = run_script(SYNC, "--dry-run", f"--source={tmp_path}")
    assert done.returncode == 1, done.stdout
    assert "REFUSED" in done.stderr


# ---------------------------------------------------------------- the canary --


def test_the_canary_self_test_passes():
    done = run_script(CHECK, "--self-test")
    assert done.returncode == 0, done.stderr
    assert "CANARY SELF-TEST OK (6/6)" in done.stdout


def test_the_canary_key_is_one_kilobyte_under_the_canary_prefix():
    done = run_script(CHECK, "--self-test")
    assert done.returncode == 0, done.stderr
    assert "1024 bytes" in done.stdout
    key = re.search(r"key (\S+),", done.stdout)
    assert key is not None, done.stdout
    assert re.fullmatch(r"_canary/\d{8}T\d{6}Z\.txt", key.group(1)), key.group(1)


def test_the_canary_skips_without_an_account():
    done = run_script(CHECK)
    assert done.returncode == 0, done.stderr
    assert "CANARY SKIP" in done.stdout


def test_the_canary_asserts_both_lifecycle_prefixes():
    text = CHECK.read_text(encoding="utf-8")
    assert "lifecycle_both_prefixes" in text
    assert 'uv run b2 bucket get "$BUCKET"' in text
    assert "interim/" in text


# ------------------------------------------------------------ live, account --


def b2_json(*args: str) -> object:
    done = subprocess.run(
        ["uv", "run", "b2", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def manifest_sha256() -> dict[str, str]:
    """dest_path -> sha256, from the client's own append-only manifest."""
    table: dict[str, str] = {}
    if not MANIFEST.is_file():
        return table
    with MANIFEST.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            dest = (row.get("dest_path") or "").strip()
            digest = (row.get("sha256") or "").strip()
            if dest and digest:
                table[dest] = digest
    return table


@pytest.mark.network
@needs_account
def test_bucket_type_is_all_private():
    info = b2_json("bucket", "get", BUCKET)
    assert isinstance(info, dict)
    assert info["bucketType"] == "allPrivate"


@pytest.mark.network
@needs_account
def test_no_object_key_carries_the_held_out_plain_partition():
    listing = b2_json("ls", "--json", "-r", f"b2://{BUCKET}")
    keys = [entry["fileName"] for entry in listing]
    offenders = [key for key in keys if PLAIN_PARTITION in key]
    assert offenders == [], offenders
    assert not [key for key in keys if key.endswith(".duckdb")]


@pytest.mark.network
@needs_account
def test_twenty_random_objects_match_their_manifest_sha256(tmp_path):
    table = manifest_sha256()
    if not table:
        pytest.skip("data/raw/_manifest.csv is empty; the overnight pulls have not landed")
    listing = b2_json("ls", "--json", "-r", f"b2://{BUCKET}/{PREFIX}")
    keys = [entry["fileName"] for entry in listing]
    checkable = [key for key in keys if f"data/{key}" in table]
    if len(checkable) < 20:
        pytest.skip(f"only {len(checkable)} mirrored object(s) carry a manifest sha256")
    sample = random.sample(checkable, 20)
    for number, key in enumerate(sample):
        local = tmp_path / f"object{number}"
        done = subprocess.run(
            [
                "uv",
                "run",
                "b2",
                "file",
                "download",
                "--no-progress",
                f"b2://{BUCKET}/{key}",
                str(local),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert done.returncode == 0, done.stderr
        digest = hashlib.sha256(local.read_bytes()).hexdigest()
        assert digest == table[f"data/{key}"], key
