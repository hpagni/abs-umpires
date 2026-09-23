"""The DuckDB connection for abs-umpires (SOP W1.6).

`connect()` is the only place Python opens the warehouse. It applies the six
statements SOP W1.6 specifies, in that order, and `dbt/profiles.yml.example`
mirrors them for the dbt targets:

    SET memory_limit = '12GB';          -- 18 GB machine, leave 6 for R/Stan
    SET threads = 8;                    -- 11 cores, leave 3 for the OS and an R fit
    SET temp_directory = 'data/tmp';
    SET preserve_insertion_order = false;
    INSTALL httpfs; LOAD httpfs;
    INSTALL parquet; LOAD parquet;

`preserve_insertion_order = false` is not only a memory setting: DuckDB refuses
`ROW_GROUP_SIZE_BYTES` while insertion order is preserved, so the Parquet write
contract below depends on it.

GD-11 is gated here. Every connection this module opens is checked against
`duckdb_databases()`, and an attached database that resolves under the sealed
root raises `SealViolation` before the caller gets the connection back.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

import duckdb

from . import paths
from .paths import SealViolation

__all__ = [
    "EXTENSIONS",
    "MEMORY_LIMIT",
    "PARQUET_COMPRESSION",
    "PARQUET_COMPRESSION_LEVEL",
    "PARQUET_DICTIONARY_COLUMNS",
    "PARQUET_ROW_GROUP_SIZE_BYTES",
    "PRESERVE_INSERTION_ORDER",
    "THREADS",
    "assert_no_sealed_attachment",
    "connect",
    "copy_to_parquet",
    "parquet_copy_options",
    "pyarrow_parquet_options",
    "settings_sql",
]

# 18 GB machine, leave 6 for R/Stan (SOP W1.6).
MEMORY_LIMIT: Final[str] = "12GB"
# 11 cores, leave 3 for the OS and an R fit (SOP W1.6).
THREADS: Final[int] = 8
PRESERVE_INSERTION_ORDER: Final[bool] = False
EXTENSIONS: Final[tuple[str, ...]] = ("httpfs", "parquet")

# Parquet write contract (SOP W1.6): ZSTD level 9, row groups of 128 MB, and
# dictionary encoding on five low-cardinality columns. DuckDB dictionary-encodes
# strings on its own and exposes no per-column switch, so the column list is
# applied on the PyArrow writer path and is the documented intent on both.
PARQUET_COMPRESSION: Final[str] = "zstd"
PARQUET_COMPRESSION_LEVEL: Final[int] = 9
PARQUET_ROW_GROUP_SIZE_BYTES: Final[str] = "128MB"
PARQUET_DICTIONARY_COLUMNS: Final[tuple[str, ...]] = (
    "pitch_type",
    "description",
    "home_team",
    "stand",
    "p_throws",
)


def settings_sql(temp_directory: str | os.PathLike[str] | None = None) -> tuple[str, ...]:
    """The four SET statements, in the order SOP W1.6 writes them."""
    temp = Path(temp_directory) if temp_directory is not None else paths.tmp_dir()
    return (
        f"SET memory_limit = '{MEMORY_LIMIT}';",
        f"SET threads = {THREADS};",
        f"SET temp_directory = '{temp}';",
        f"SET preserve_insertion_order = {str(PRESERVE_INSERTION_ORDER).lower()};",
    )


def _load_extension(con: duckdb.DuckDBPyConnection, name: str) -> None:
    """LOAD the extension, installing it first only if it is not there yet.

    SOP W1.6 writes `INSTALL x; LOAD x;`. INSTALL reaches the extension
    repository over the network, and this machine sits behind a university
    network that resets some TLS connections, so LOAD is tried first: an
    already-installed extension then needs no request at all.
    """
    try:
        con.execute(f"LOAD {name};")
        return
    except duckdb.Error:
        pass
    con.execute(f"INSTALL {name};")
    con.execute(f"LOAD {name};")


def assert_no_sealed_attachment(con: duckdb.DuckDBPyConnection) -> None:
    """GD-11: no attached database may resolve under the sealed root."""
    sealed = paths.sealed_root()
    rows = con.execute("SELECT database_name, path FROM duckdb_databases();").fetchall()
    for database_name, path in rows:
        if not path:
            continue
        resolved = Path(str(path)).expanduser()
        resolved = resolved if resolved.is_absolute() else (Path.cwd() / resolved)
        resolved = Path(os.path.normpath(resolved))
        if resolved == sealed or resolved.is_relative_to(sealed):
            raise SealViolation(
                f"GD-11: database {database_name!r} is attached at {resolved}, "
                f"which resolves under the sealed root {sealed}."
            )


def connect(
    database: str | os.PathLike[str] | None = None,
    *,
    read_only: bool = False,
    check_seal: bool = True,
) -> duckdb.DuckDBPyConnection:
    """Open the warehouse with the W1.6 settings applied.

    `database` defaults to `paths.DUCKDB_PATH`. Pass `":memory:"` for a
    throwaway connection. The spill directory is created if it is missing,
    because DuckDB will not create it itself.
    """
    target = paths.DUCKDB_PATH if database is None else Path(database)
    in_memory = str(target) == ":memory:"
    if not in_memory:
        paths.assert_minted(target)
        target.parent.mkdir(parents=True, exist_ok=True)
    temp_directory = paths.tmp_dir()
    temp_directory.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(target), read_only=read_only)
    try:
        for statement in settings_sql(temp_directory):
            con.execute(statement)
        for extension in EXTENSIONS:
            _load_extension(con, extension)
        if check_seal:
            assert_no_sealed_attachment(con)
    except Exception:
        con.close()
        raise
    return con


def parquet_copy_options() -> str:
    """The COPY option list for a DuckDB Parquet write."""
    return (
        f"FORMAT parquet, COMPRESSION {PARQUET_COMPRESSION}, "
        f"COMPRESSION_LEVEL {PARQUET_COMPRESSION_LEVEL}, "
        f"ROW_GROUP_SIZE_BYTES '{PARQUET_ROW_GROUP_SIZE_BYTES}'"
    )


def pyarrow_parquet_options() -> dict[str, Any]:
    """The same contract for `pyarrow.parquet.write_table`."""
    return {
        "compression": PARQUET_COMPRESSION,
        "compression_level": PARQUET_COMPRESSION_LEVEL,
        "use_dictionary": list(PARQUET_DICTIONARY_COLUMNS),
        "write_statistics": True,
    }


def copy_to_parquet(
    con: duckdb.DuckDBPyConnection, source_sql: str, destination: str | os.PathLike[str]
) -> Path:
    """Write one relation to Parquet under the W1.6 write contract.

    `destination` must be a path minted by `absump.paths`.
    """
    target = paths.assert_minted(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({source_sql}) TO '{target}' ({parquet_copy_options()});")
    return target
