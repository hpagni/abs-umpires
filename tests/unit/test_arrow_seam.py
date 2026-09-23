"""W9.2 cross-language Parquet seam. Gate RP-05.

SOP section 6.1 states RP-05 as: "arrow versions equal on both sides --
``pyarrow.__version__ == packageVersion("arrow") == "25.0.1"``; seam values agree
to 1e-12."

The seam is the only place Python and R exchange data: Python writes Parquet,
R reads it with ``arrow::read_parquet()``, and nothing is passed as CSV. Two
different Arrow builds can both be valid and still disagree on how a decimal, a
timestamp or a nested type lands on disk, so the versions are pinned equal and
this test is what proves they still are. Checking that a round trip merely works
is not enough: a round trip works between mismatched versions right up to the day
it silently does not.

What runs here:

1. ``pyarrow.__version__`` is "25.0.1" (SOP section 2.2, Python pins).
2. R's ``packageVersion("arrow")`` is "25.0.1" (renv.lock).
3. The two strings are equal to each other.
4. Python writes ``data/tmp/seam.parquet`` with one float64 column and one int64
   column, R reads it back, and the values agree to 1e-12 while the Arrow types
   come back identical -- ``double`` and ``int64``, read off the file's own
   schema rather than off R's data-frame classes, because R downcasts int64 to
   integer when it fits and that conversion is not what RP-05 is about.

The file is written under ``data/``, which never enters git (D-03). The test
creates ``data/tmp/`` if it is absent and overwrites the seam file each run.

Phase 01 reads no 2026 datum. Both values below are synthetic constants chosen by
W9.2: -0.0822 is the float the SOP names for this seam, and the game_pk is a
made-up seven-digit integer that matches no real game. Nothing here touches
``data/staging/``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SEAM_PATH = REPO_ROOT / "data" / "tmp" / "seam.parquet"

PINNED_ARROW = "25.0.1"

# SOP W9.2 names the float64 value for this seam. The game_pk is synthetic: it is
# not read from any feed, and phase 01 pulls nothing.
SEAM_FLOAT = -0.0822
SEAM_GAME_PK = 7460001

TOLERANCE = 1e-12

# Printed by R, parsed by Python. %.17g round-trips an IEEE-754 double exactly.
R_READER = r"""
suppressMessages(library(arrow))
args <- commandArgs(trailingOnly = TRUE)
path <- args[length(args)]
tbl <- arrow::read_parquet(path, as_data_frame = FALSE)
df <- as.data.frame(tbl)
out <- list(
  arrow_version = as.character(packageVersion("arrow")),
  type_zone_edge_ft = tbl$schema$GetFieldByName("zone_edge_ft")$type$ToString(),
  type_game_pk = tbl$schema$GetFieldByName("game_pk")$type$ToString(),
  value_zone_edge_ft = sprintf("%.17g", df$zone_edge_ft[1]),
  value_game_pk = format(df$game_pk[1], scientific = FALSE),
  nrow = nrow(df)
)
cat("ABSUMP_SEAM_JSON ", jsonlite::toJSON(out, auto_unbox = TRUE), "\n", sep = "")
"""


def _write_seam() -> pa.Table:
    """Write the seam file from Python and return the table that was written."""
    table = pa.table(
        {
            "zone_edge_ft": pa.array([SEAM_FLOAT], type=pa.float64()),
            "game_pk": pa.array([SEAM_GAME_PK], type=pa.int64()),
        }
    )
    SEAM_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, SEAM_PATH)
    return table


def _read_seam_from_r() -> dict:
    """Run the R reader against the seam file and return its parsed report."""
    if shutil.which("Rscript") is None:
        pytest.fail("Rscript is not on PATH; RP-05 needs both sides of the seam")
    proc = subprocess.run(
        ["Rscript", "-e", R_READER, "--args", str(SEAM_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"the R side of the seam failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    marker = "ABSUMP_SEAM_JSON "
    line = next(
        (ln for ln in proc.stdout.splitlines() if ln.startswith(marker)),
        None,
    )
    if line is None:
        pytest.fail(f"no seam report in R output\nstdout:\n{proc.stdout}")
    return json.loads(line[len(marker) :])


@pytest.fixture(scope="module")
def seam() -> tuple[pa.Table, dict]:
    table = _write_seam()
    return table, _read_seam_from_r()


def pyarrow_version() -> str:
    return pa.__version__


def test_pyarrow_is_pinned() -> None:
    assert pyarrow_version() == PINNED_ARROW


def test_r_arrow_is_pinned(seam: tuple[pa.Table, dict]) -> None:
    _, report = seam
    assert report["arrow_version"] == PINNED_ARROW


def test_arrow_versions_are_equal_on_both_sides(seam: tuple[pa.Table, dict]) -> None:
    """The load-bearing assertion: the two strings are the same string."""
    _, report = seam
    assert pyarrow_version() == report["arrow_version"], (
        "Arrow versions differ across the seam: "
        f"pyarrow {pyarrow_version()} vs R arrow {report['arrow_version']}. "
        "One Parquet dialect, or nothing."
    )


def test_seam_file_is_written_where_the_sop_says() -> None:
    _write_seam()
    assert SEAM_PATH.is_file()
    assert SEAM_PATH.relative_to(REPO_ROOT) == Path("data/tmp/seam.parquet")


def test_seam_types_survive_the_crossing(seam: tuple[pa.Table, dict]) -> None:
    table, report = seam
    assert str(table.schema.field("zone_edge_ft").type) == "double"
    assert str(table.schema.field("game_pk").type) == "int64"
    assert report["type_zone_edge_ft"] == "double"
    assert report["type_game_pk"] == "int64"


def test_seam_values_agree_to_1e_12(seam: tuple[pa.Table, dict]) -> None:
    _, report = seam
    assert report["nrow"] == 1
    r_float = float(report["value_zone_edge_ft"])
    assert abs(r_float - SEAM_FLOAT) <= TOLERANCE, (
        f"float64 drifted across the seam: python {SEAM_FLOAT!r} vs R {r_float!r}"
    )
    r_int = int(report["value_game_pk"])
    assert r_int == SEAM_GAME_PK, (
        f"int64 drifted across the seam: python {SEAM_GAME_PK} vs R {r_int}"
    )


def test_float_round_trip_is_bit_exact(seam: tuple[pa.Table, dict]) -> None:
    """1e-12 is the SOP's tolerance; the seam should in fact be exact."""
    _, report = seam
    assert float(report["value_zone_edge_ft"]) == SEAM_FLOAT
