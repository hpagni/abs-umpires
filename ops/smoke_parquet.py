"""Smoke check 3: the Parquet round trip. SOP step W1.15.

Polars writes 100,000 rows into a hive-partitioned directory under
``data/tmp/smoke/parquet/``. DuckDB reads the same bytes back with
``hive_partitioning=true``. The codec is asserted to be ZSTD.

WHAT IS BEING PROVED. Three things that a plain "it wrote a file" check misses.

1. The two engines agree on one Parquet dialect. Polars writes it, DuckDB reads
   it, and the float64 column comes back bit-for-bit, not to some tolerance.
2. The hive partition columns survive as columns. A hive layout encodes
   ``season`` and ``level`` in directory names; read without
   ``hive_partitioning=true`` they are gone, and every downstream partition
   filter silently scans everything. The check asserts the distinct values, not
   only the row count.
3. The codec is ZSTD, per SOP section 2.2. A default codec change in either
   library would otherwise pass unnoticed until the lake had been rewritten.

ONE DEVIATION FROM THE SOP TEXT, STATED. W1.15 says the ZSTD codec is asserted
"via pyarrow.parquet.read_schema". ``read_schema`` returns the Arrow schema and
carries no compression field: the codec lives in the Parquet file footer, per
column chunk, and ``read_metadata`` is the call that reads it. Both calls run
here. ``read_schema`` asserts the column names and the Arrow types, and
``read_metadata`` asserts the codec on every column chunk of every part file,
which is a stricter statement than one call on one file could make.

No RNG. Every value is a fixed arithmetic function of the row index, so two runs
write identical bytes and the check is safe to re-run.

Nothing here touches the network and nothing here reads ``data/staging/``,
``data/raw/`` or ``data/sealed/``.

Run: uv run --locked python ops/smoke_parquet.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import duckdb
import polars as pl
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "tmp" / "smoke" / "parquet"

N_ROWS = 100_000
CODEC = "ZSTD"
SEASONS = (2022, 2023, 2024, 2025, 2026)
LEVELS = ("mlb", "aaa")

# The float the SOP names for the plate-plane shift, reused here so that the
# column carries a value with a known decimal expansion rather than noise.
BASE_FLOAT = -0.0822


def build_frame() -> pl.DataFrame:
    """100,000 rows, every value a function of the row index. No RNG."""
    idx = range(N_ROWS)
    return pl.DataFrame(
        {
            "season": pl.Series([SEASONS[i % len(SEASONS)] for i in idx], dtype=pl.Int32),
            "level": pl.Series([LEVELS[i % len(LEVELS)] for i in idx], dtype=pl.Utf8),
            "game_pk": pl.Series([746_000 + i for i in idx], dtype=pl.Int64),
            "plate_z_shift_ft": pl.Series(
                [BASE_FLOAT + (i % 997) * 1e-6 for i in idx], dtype=pl.Float64
            ),
        }
    )


def main() -> int:
    frame = build_frame()
    if frame.height != N_ROWS:
        print(f"smoke-parquet FAIL: built {frame.height} rows, expected {N_ROWS}")
        return 1

    # Idempotent: the directory is rebuilt from scratch on every run.
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(OUT_DIR, compression="zstd", partition_by=["season", "level"])

    parts = sorted(OUT_DIR.rglob("*.parquet"))
    expected_parts = len(SEASONS) * len(LEVELS)
    if len(parts) != expected_parts:
        print(f"smoke-parquet FAIL: {len(parts)} part files, expected {expected_parts}")
        return 1

    # --- pyarrow.parquet.read_schema: the column names and the Arrow types ---
    expected_types = {
        "season": "int32",
        "level": "large_string",
        "game_pk": "int64",
        "plate_z_shift_ft": "double",
    }
    for part in parts:
        schema = pq.read_schema(part)
        got = {name: str(schema.field(name).type) for name in schema.names}
        if got != expected_types:
            print(f"smoke-parquet FAIL: {part} schema is {got}, expected {expected_types}")
            return 1

    # --- pyarrow.parquet.read_metadata: the codec, per column chunk -----------
    chunks = 0
    for part in parts:
        meta = pq.read_metadata(part)
        for g in range(meta.num_row_groups):
            group = meta.row_group(g)
            for c in range(group.num_columns):
                codec = group.column(c).compression
                if codec != CODEC:
                    print(f"smoke-parquet FAIL: {part} column {c} codec {codec}, not {CODEC}")
                    return 1
                chunks += 1
    if chunks == 0:
        print("smoke-parquet FAIL: no column chunk was inspected, so the codec is unproved")
        return 1

    # --- DuckDB reads it back with hive_partitioning=true ---------------------
    glob = str(OUT_DIR / "**" / "*.parquet")
    con = duckdb.connect()
    try:
        rows, seasons, levels = con.execute(
            "select count(*), count(distinct season), count(distinct level) "
            f"from read_parquet('{glob}', hive_partitioning=true)"
        ).fetchone()
        if (rows, seasons, levels) != (N_ROWS, len(SEASONS), len(LEVELS)):
            print(
                f"smoke-parquet FAIL: DuckDB read {rows} rows, {seasons} seasons, "
                f"{levels} levels; expected {N_ROWS}, {len(SEASONS)}, {len(LEVELS)}"
            )
            return 1

        # The partition columns are readable as columns, not only as paths.
        got_seasons = [
            r[0]
            for r in con.execute(
                f"select distinct season from read_parquet('{glob}', hive_partitioning=true) "
                "order by season"
            ).fetchall()
        ]
        if [int(s) for s in got_seasons] != list(SEASONS):
            print(f"smoke-parquet FAIL: partition seasons {got_seasons}, expected {list(SEASONS)}")
            return 1

        # The float64 column is bit-for-bit, not within a tolerance.
        #
        # The comparison is over the DISTINCT values, not over a sum. A sum
        # compares two accumulation orders as well as two decodings, and the
        # two engines add the 100,000 doubles in different orders, so a sum
        # differs in the last bit while every stored value is identical. That
        # would be a false failure about IEEE-754 addition, not about Parquet.
        duck_values = [
            r[0]
            for r in con.execute(
                "select distinct plate_z_shift_ft "
                f"from read_parquet('{glob}', hive_partitioning=true) "
                "order by plate_z_shift_ft"
            ).fetchall()
        ]
    finally:
        con.close()

    polars_values = sorted(set(frame["plate_z_shift_ft"].to_list()))
    if duck_values != polars_values:
        n_diff = sum(1 for a, b in zip(duck_values, polars_values, strict=False) if a != b)
        print(
            "smoke-parquet FAIL: float64 values differ across the engines: "
            f"{len(duck_values)} DuckDB values vs {len(polars_values)} Polars values, "
            f"{n_diff} unequal"
        )
        return 1

    print(
        f"smoke-parquet OK: {N_ROWS} rows, {len(parts)} hive parts, {chunks} column chunks "
        f"{CODEC}, DuckDB hive_partitioning=true agrees on every distinct float64"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
