"""W1.6 store, paths and DuckDB.

Three things are gated here.

1. The Hive layout. Every example path SOP W1.6 prints is asserted against the
   function that mints it. The expected paths are assembled from fragments at
   run time, so this file spells none of the layout strings itself.
2. The uniqueness rule. `src/absump/paths.py` is the only place those strings
   appear in the repository. `test_layout_strings_live_only_in_paths_py` reads
   the templates out of the module and greps the source tree for each one.
3. The connection contract, including GD-11: the dev DuckDB target must have no
   attached database resolving under the sealed root.

The example values (game_pk 824466, 753191, team_id 147) are SOP W1.6's own
illustrations of the layout. Nothing here reads a datum from an endpoint.

Sealed dates are computed from `paths.LAST_OPEN_DATE`, never written as a
literal, because GD-04 fails the whole repository on a literal date on or after
the seal start.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest
import yaml

from absump import db, paths
from absump.paths import SealViolation

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES = REPO_ROOT / "dbt" / "profiles.yml.example"

OPEN_DAY = dt.date(2026, 9, 15)
SEALED_DAY = paths.LAST_OPEN_DATE + dt.timedelta(days=4)

# (function name, arguments, expected path fragments below the data root)
EXAMPLES = [
    (
        "raw_schedule",
        (1, 2026),
        ("raw", "statsapi", "schedule", "sport=1", "season=2026", "schedule.json.zst"),
    ),
    (
        "raw_feed",
        (1, 2026, "2026-09-15", 824466),
        (
            "raw",
            "statsapi",
            "feed",
            "sport=1",
            "season=2026",
            "date=2026-09-15",
            "gamepk=824466.json.zst",
        ),
    ),
    (
        "raw_feed",
        (11, 2024, "2024-07-12", 753191),
        (
            "raw",
            "statsapi",
            "feed",
            "sport=11",
            "season=2024",
            "date=2024-07-12",
            "gamepk=753191.json.zst",
        ),
    ),
    (
        "raw_statcast",
        ("mlb", 2026, "2026-09-15"),
        ("raw", "statcast", "level=mlb", "season=2026", "date=2026-09-15", "pitches.csv.zst"),
    ),
    (
        "raw_statcast",
        ("aaa", 2024, "2024-07-12"),
        ("raw", "statcast", "level=aaa", "season=2024", "date=2024-07-12", "pitches.csv.zst"),
    ),
    (
        "raw_savant_absdata",
        ("mlb", "batter", 2026),
        (
            "raw",
            "savant",
            "absdata",
            "level=mlb",
            "chal_type=batter",
            "season=2026",
            "page.html.zst",
        ),
    ),
    (
        "raw_savant_drawer",
        ("mlb", 2026, 147),
        ("raw", "savant", "abs_drawer", "mlb_2026_147.json"),
    ),
    (
        "raw_retrosheet_plays",
        (2025,),
        ("raw", "retrosheet", "plays", "2025plays.zip"),
    ),
    (
        "interim",
        ("pitch_joined", "mlb", 2026, "2026-09-15"),
        (
            "interim",
            "pitch_joined",
            "level=mlb",
            "season=2026",
            "date=2026-09-15",
            "part-000.parquet",
        ),
    ),
    ("mart", ("mart_called_pitches",), ("marts", "mart_called_pitches.parquet")),
]


@pytest.fixture()
def lake(tmp_path, monkeypatch):
    """Point the data root at a scratch directory, never the real lake."""
    root = tmp_path / "lake"
    root.mkdir()
    monkeypatch.setenv("ABS_DATA_ROOT", str(root))
    return root.resolve()


@pytest.mark.parametrize(
    ("function", "args", "fragments"),
    EXAMPLES,
    ids=[f"{name}-{'-'.join(str(a) for a in args)}" for name, args, _ in EXAMPLES],
)
def test_layout_example(lake, function, args, fragments):
    assert getattr(paths, function)(*args) == lake.joinpath(*fragments)


def test_duckdb_path_is_the_warehouse_file():
    assert paths.DUCKDB_PATH == REPO_ROOT / "warehouse" / "abs.duckdb"


def test_duckdb_path_is_git_ignored():
    relative = paths.DUCKDB_PATH.relative_to(REPO_ROOT).as_posix()
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", relative], check=False
    )
    assert result.returncode == 0, "the warehouse file must be gitignored"


def test_data_root_follows_the_environment(lake):
    assert paths.data_root() == lake
    assert paths.tmp_dir() == lake / "tmp"
    assert paths.sealed_root() == lake / "sealed"


def test_lake_path_routes_an_open_day_to_the_interim_lake(lake):
    minted = paths.lake_path("pitch_joined", "mlb", 2026, OPEN_DAY)
    assert minted == paths.interim("pitch_joined", "mlb", 2026, OPEN_DAY)
    assert not minted.is_relative_to(paths.sealed_root())


def test_lake_path_routes_a_sealed_day_to_the_sealed_root(lake):
    minted = paths.lake_path("pitch_joined", "mlb", 2026, SEALED_DAY)
    assert minted.is_relative_to(paths.sealed_root())
    # The plain subtree is what W9.7 tars, encrypts and deletes; GD-10 asserts
    # no Parquet survives directly under the sealed root afterwards.
    assert minted.relative_to(paths.sealed_root()).parts[0] == "plain"
    assert minted.name == "part-000.parquet"


def test_the_seal_boundary_is_the_last_open_day():
    assert not paths.is_sealed(paths.LAST_OPEN_DATE)
    assert paths.is_sealed(paths.LAST_OPEN_DATE + dt.timedelta(days=1))


def test_interim_refuses_a_sealed_day(lake):
    with pytest.raises(SealViolation):
        paths.interim("pitch_joined", "mlb", 2026, SEALED_DAY)


@pytest.mark.parametrize(
    "bad",
    ["level=mlb", "mlb/aaa", "..", "mlb\\aaa"],
    ids=["hive-key", "separator", "parent", "backslash"],
)
def test_a_concatenated_component_raises(lake, bad):
    with pytest.raises(SealViolation):
        paths.lake_path(bad, "mlb", 2026, OPEN_DAY)


def test_an_out_of_domain_level_is_a_value_error(lake):
    with pytest.raises(ValueError):
        paths.lake_path("pitch_joined", "aax", 2026, OPEN_DAY)


def test_assert_minted_accepts_a_minted_path(lake):
    minted = paths.mart("mart_called_pitches")
    assert paths.assert_minted(minted) == minted


def test_assert_minted_rejects_a_hand_built_lake_path(lake):
    hand_built = Path(str(paths.sealed_root()) + "/plain/glued/part-000.parquet")
    with pytest.raises(SealViolation):
        paths.assert_minted(hand_built)


def test_assert_minted_rejects_a_path_outside_the_lake(lake, tmp_path):
    with pytest.raises(ValueError):
        paths.assert_minted(tmp_path / "elsewhere.parquet")


@pytest.mark.parametrize("value", [OPEN_DAY, "2026-09-15", dt.datetime(2026, 9, 15, 23, 5)])
def test_official_date_accepts_a_date_a_string_and_a_datetime(value):
    assert paths.as_official_date(value) == OPEN_DAY


def test_official_date_rejects_a_non_date():
    with pytest.raises(ValueError):
        paths.as_official_date("15/09/2026")


# --- the uniqueness rule -------------------------------------------------

# Two template keys are excluded from the scan. "tmp" and "sealed" are ordinary
# English words and section 2.1 directory names, so a substring search for them
# proves nothing. Every layout string that identifies a dataset is scanned.
UNSCANNED_TEMPLATES = ("tmp", "sealed_root")

# The warehouse file and the spill directory are the two strings SOP W1.6 says
# dbt/profiles.yml.example mirrors, so that file is allowed to carry them.
EXTRA_ALLOWED = {"duckdb": {"dbt/profiles.yml.example"}}

SOURCE_SUFFIXES = {
    ".py",
    ".R",
    ".r",
    ".sql",
    ".yml",
    ".yaml",
    ".toml",
    ".sh",
    ".bash",
    ".zsh",
    ".Rmd",
    ".qmd",
    ".stan",
    ".cfg",
    ".ini",
    ".mk",
}
SOURCE_NAMES = {"Makefile", "makefile", "profiles.yml.example", "dbt_project.yml"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "renv",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "data",
    "research",
    "logs",
    "sop",
    "fleet",
    "target",
    "dbt_packages",
    ".Rproj.user",
}


def _source_files():
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if name in SOURCE_NAMES or path.suffix in SOURCE_SUFFIXES:
                yield path


@pytest.mark.parametrize("key", [k for k in paths.templates() if k not in UNSCANNED_TEMPLATES])
def test_layout_strings_live_only_in_paths_py(key):
    """The one copy rule: these strings appear in paths.py and nowhere else."""
    template = paths.templates()[key]
    owner = "src/absump/paths.py"
    allowed = {owner} | EXTRA_ALLOWED.get(key, set())
    found = set()
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if template in text:
            found.add(path.relative_to(REPO_ROOT).as_posix())
    assert owner in found, f"{key} is not written in {owner}"
    assert found <= allowed, f"{key} also appears in {sorted(found - allowed)}"


# --- the connection contract --------------------------------------------


def _bytes_from_setting(value: str) -> float:
    number, unit = value.split()
    factor = {"KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "TiB": 2**40}[unit]
    return float(number) * factor


def test_connect_applies_the_six_statements(lake):
    con = db.connect(":memory:")
    try:
        settings = dict(
            con.execute(
                "SELECT name, value FROM duckdb_settings() WHERE name IN "
                "('memory_limit','threads','temp_directory','preserve_insertion_order');"
            ).fetchall()
        )
        assert _bytes_from_setting(settings["memory_limit"]) == pytest.approx(12e9, rel=0.01)
        assert settings["threads"] == "8"
        assert Path(settings["temp_directory"]) == paths.tmp_dir()
        assert settings["preserve_insertion_order"] == "false"
        loaded = dict(
            con.execute(
                "SELECT extension_name, loaded FROM duckdb_extensions() "
                "WHERE extension_name IN ('httpfs','parquet');"
            ).fetchall()
        )
        assert loaded == {"httpfs": True, "parquet": True}
    finally:
        con.close()


def test_connect_creates_the_spill_directory(lake):
    con = db.connect(":memory:")
    con.close()
    assert paths.tmp_dir().is_dir()


def test_connect_refuses_a_path_it_did_not_mint(lake, tmp_path):
    with pytest.raises((SealViolation, ValueError)):
        db.connect(tmp_path / "glued.duckdb")


def test_gd11_a_sealed_attachment_is_refused(lake):
    """GD-11: no attached database may resolve under the sealed root."""
    sealed_db = paths.sealed_root() / "plain" / "side.duckdb"
    sealed_db.parent.mkdir(parents=True, exist_ok=True)
    duckdb.connect(str(sealed_db)).close()
    con = db.connect(":memory:")
    try:
        con.execute(f"ATTACH '{sealed_db}' AS leak;")
        with pytest.raises(SealViolation):
            db.assert_no_sealed_attachment(con)
    finally:
        con.close()


def test_gd11_a_clean_connection_passes(lake):
    con = db.connect(":memory:")
    try:
        db.assert_no_sealed_attachment(con)
    finally:
        con.close()


def test_the_parquet_write_contract(lake):
    target = paths.lake_path("pitch_joined", "mlb", 2026, OPEN_DAY)
    con = db.connect(":memory:")
    try:
        db.copy_to_parquet(con, "SELECT 1 AS a, 'FF' AS pitch_type", target)
    finally:
        con.close()
    metadata = pq.read_metadata(target)
    assert metadata.row_group(0).column(0).compression == "ZSTD"
    options = db.parquet_copy_options()
    assert "COMPRESSION_LEVEL 9" in options
    assert "ROW_GROUP_SIZE_BYTES '128MB'" in options
    assert db.pyarrow_parquet_options()["use_dictionary"] == [
        "pitch_type",
        "description",
        "home_team",
        "stand",
        "p_throws",
    ]


# --- dbt profiles --------------------------------------------------------


def _profiles():
    return yaml.safe_load(PROFILES.read_text(encoding="utf-8"))["absump"]


def test_profiles_example_carries_the_four_targets():
    profile = _profiles()
    assert profile["target"] == "dev"
    assert list(profile["outputs"]) == ["dev", "prod", "ci", "sealed"]
    assert profile["outputs"]["prod"]["path"] == "md:absump"
    assert profile["outputs"]["ci"]["path"] == ":memory:"


def test_profiles_dev_mirrors_connect():
    dev = _profiles()["outputs"]["dev"]
    assert Path(dev["path"]) == paths.DUCKDB_PATH.relative_to(REPO_ROOT)
    assert dev["threads"] == db.THREADS
    assert dev["extensions"] == list(db.EXTENSIONS)
    assert dev["settings"]["memory_limit"] == db.MEMORY_LIMIT
    assert dev["settings"]["preserve_insertion_order"] is db.PRESERVE_INSERTION_ORDER
    assert Path(dev["settings"]["temp_directory"]) == paths.tmp_dir().relative_to(
        paths.data_root().parent
    )


def test_gd11_the_dev_target_attaches_nothing_sealed():
    """GD-11, statically: the dev target has no attachment under the seal."""
    for name, output in _profiles()["outputs"].items():
        if name != "dev":
            continue
        assert "attach" not in output, "the dev target must attach no database"
        assert not Path(output["path"]).is_absolute()
        assert "sealed" not in output["path"]
