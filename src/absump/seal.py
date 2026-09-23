"""The seal: one module that knows which rows are held out, and one gate.

SOP step W1.8, section 2.4, and layers 1 and 2 of the four-layer guard (W9.7).

This file is one of exactly two paths the static scan in
`tests/guard/test_no_sealed_reads.py` allowlists (GD-04, GD-05). The other is
`quality/sql/analysis_set.sql`. Those two are allowed to name the held-out set
because they are the only two places that define it. Every other file in the
repository fails the scan if it names it, whatever directory it sits in.

Nothing here is a second copy of the rule. The boundary date, the game-type
codes and the tag string come from `config/seal.yml`, which W2.4 froze as the
Python-side mirror of the SQL predicate; UT-17 asserts the two agree. This
module reads that file and derives the rest.

Public surface, exactly as W1.8 names it:

    assert_unsealed(df, date_col)   raise unless every row is open
    sealed_only(df, date_col)       the held-out rows, only behind _unlocked()
    frame(name, set=...)            read one warehouse view for one set
    _unlocked()                     the six preconditions of SOP phase 5

Every W3/W4/W5/W8 fit function takes `stage: Literal["dev","sealed"]`. On
`dev` it calls `assert_unsealed` on its training frame before fitting. `Stage`
below is that type, exported so every fit function spells it the same way.

This module never sets ABS_SEAL_UNLOCK (rule 0.5.1), issues no request
(rule 0.5.2), hard-codes no number that came from an endpoint (rule 0.5.4),
and reads no data at import time.
"""

from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import os as _os
import subprocess as _subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from absump import paths
from absump.paths import LAST_OPEN_DATE, REPO_ROOT, SealViolation

# SEAL_START_DATE and PREREG_TAG are lazy module attributes, resolved by
# `__getattr__` below so that importing this module opens no file. They are
# read as `seal.SEAL_START_DATE` and `seal.PREREG_TAG`, not by star import.
__all__ = [
    "VIEWS",
    "SealViolation",
    "Stage",
    "assert_unsealed",
    "frame",
    "sealed_only",
    "unlock_report",
]

# The unlock switch. Named once, read once, never written. SOP rule 0.5.1: only
# the owner sets it, in one shell, after the W9.7 ceremony.
UNLOCK_ENV: str = "ABS_SEAL_UNLOCK"

CONFIG_PATH: Path = REPO_ROOT / "config" / "seal.yml"
PREREG_DOC: Path = REPO_ROOT / "PREREGISTRATION.md"
PREREG_LOCK: Path = REPO_ROOT / "quality" / "prereg.lock"

# The four warehouse frames. SOP section 3: model code reads only the open
# views, one per fact table, each `SELECT * FROM fct_... WHERE analysis_set`
# restricted to the open label.
VIEWS: tuple[str, ...] = ("pitch", "called_pitch", "challenge", "opportunity")

# The two stages every fit function takes.
Stage = Literal["dev", "sealed"]

# The three labels the frozen predicate can return. Spelled here, in the one
# allowlisted Python file, so that no other module has to spell them.
OPEN: str = "open"
HELD_OUT: str = "sealed"

_REMOTE: str = "origin"
_GIT_TIMEOUT_S: float = 20.0


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    """`config/seal.yml`, parsed once. W2.4 owns the file; this only reads it."""
    import yaml

    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"{CONFIG_PATH} is missing; W2.4 owns that file")
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{CONFIG_PATH} did not parse to a mapping")
    return loaded


def _config_date(key: str) -> _dt.date:
    return paths.as_official_date(_config()[key])


def __getattr__(name: str) -> Any:
    """Module-level constants that need the config file, resolved on demand.

    Import stays pure: a bare `import absump.seal` opens no file. The first
    read of `SEAL_START_DATE` or `PREREG_TAG` parses `config/seal.yml`.
    """
    if name == "SEAL_START_DATE":
        return _config_date("seal_start_date")
    if name == "PREREG_TAG":
        return str(_config()["prereg_tag"])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _prereg_tag() -> str:
    return str(_config()["prereg_tag"])


def _first_held_out_date() -> _dt.date:
    """The first day on the far side of the boundary, from the config file.

    `paths.LAST_OPEN_DATE` is the day before it. The two are asserted to agree,
    because a drift between them would move the boundary silently.
    """
    start = _config_date("seal_start_date")
    if start != LAST_OPEN_DATE + _dt.timedelta(days=1):
        raise SealViolation(
            f"config/seal.yml seal_start_date={start.isoformat()} is not the day "
            f"after paths.LAST_OPEN_DATE={LAST_OPEN_DATE.isoformat()}"
        )
    return start


# --------------------------------------------------------------- frame access
def _columns(df: Any) -> tuple[str, ...]:
    """Column names, for polars, pandas, pyarrow or a mapping of sequences."""
    names = getattr(df, "column_names", None)  # pyarrow.Table
    if names is not None:
        return tuple(names)
    names = getattr(df, "columns", None)  # polars, pandas
    if names is not None:
        return tuple(names)
    if isinstance(df, dict):
        return tuple(df.keys())
    raise TypeError(f"{type(df).__name__} does not expose column names")


def _values(df: Any, date_col: str) -> list[Any]:
    """One column, as a plain Python list, without importing a dataframe library.

    Accepts a polars DataFrame or LazyFrame, a pandas DataFrame, a pyarrow
    Table, or a mapping of column name to sequence. A LazyFrame is collected,
    one column only.
    """
    if hasattr(df, "collect") and hasattr(df, "select"):  # polars LazyFrame
        df = df.select(date_col).collect()
    if date_col not in _columns(df):
        raise ValueError(f"{date_col!r} is not a column; columns are {_columns(df)}")
    if hasattr(df, "column") and hasattr(df, "num_rows"):  # pyarrow.Table
        return list(df.column(date_col).to_pylist())
    if hasattr(df, "get_column"):  # polars DataFrame
        return list(df.get_column(date_col).to_list())
    column = df[date_col]
    if hasattr(column, "tolist"):  # pandas Series, numpy array
        return list(column.tolist())
    return list(column)


def _held_out_mask(df: Any, date_col: str) -> list[bool]:
    """True for every row on the far side of the boundary. A null date is True.

    A null official date cannot be shown to be open, so it is treated as held
    out rather than as open. The frozen SQL predicate sends a null to the open
    label, which `tests/unit/test_seal_classifier.py` records as a leak path
    whose fix is upstream: `officialDate` is NOT NULL in the data contract.
    Python is the side that can afford to be strict, so it is.
    """
    boundary = _first_held_out_date()
    mask: list[bool] = []
    for value in _values(df, date_col):
        if value is None:
            mask.append(True)
            continue
        mask.append(paths.as_official_date(value) >= boundary)
    return mask


def _filter(df: Any, mask: list[bool]) -> Any:
    """Apply a boolean mask, in whatever library the frame came from."""
    if hasattr(df, "collect") and hasattr(df, "select"):  # polars LazyFrame
        df = df.collect()
    if hasattr(df, "filter") and hasattr(df, "get_column"):  # polars DataFrame
        import polars as pl

        return df.filter(pl.Series(mask))
    if hasattr(df, "filter") and hasattr(df, "num_rows"):  # pyarrow.Table
        import pyarrow as pa

        return df.filter(pa.array(mask))
    if hasattr(df, "loc"):  # pandas DataFrame
        return df.loc[mask]
    if isinstance(df, dict):
        return {
            k: [v for v, keep in zip(vals, mask, strict=True) if keep] for k, vals in df.items()
        }
    raise TypeError(f"{type(df).__name__} cannot be filtered by this module")


def assert_unsealed(df: Any, date_col: str) -> None:
    """Raise `SealViolation` unless every row of `df` is inside the open window.

    This is layer 1 of the guard at the one place it can be checked cheaply:
    the training frame, immediately before a fit. Every W3/W4/W5/W8 fit
    function with `stage="dev"` calls it.
    """
    mask = _held_out_mask(df, date_col)
    offenders = sum(mask)
    if offenders == 0:
        return
    dates = [v for v, keep in zip(_values(df, date_col), mask, strict=True) if keep]
    shown = sorted({"null" if d is None else paths.as_official_date(d).isoformat() for d in dates})
    raise SealViolation(
        f"{offenders} of {len(mask)} rows in column {date_col!r} fall on or after "
        f"{_first_held_out_date().isoformat()}: {', '.join(shown[:5])}"
        f"{' ...' if len(shown) > 5 else ''}. "
        "A dev-stage fit trains on the open window only."
    )


def sealed_only(df: Any, date_col: str) -> Any:
    """The rows on the far side of the boundary. Refuses unless `_unlocked()`.

    The only way to get a held-out frame in this codebase, and it is shut until
    all six preconditions of SOP phase 5 hold at once.
    """
    if not _unlocked():
        raise SealViolation(
            "the held-out set is closed: " + "; ".join(unlock_report()["failed"]) + ". "
            "Only the owner opens it, after the W9.7 ceremony."
        )
    return _filter(df, _held_out_mask(df, date_col))


def frame(name: str = "pitch", *, set: str = OPEN, con: Any = None) -> Any:
    """Read one warehouse view for one analysis set, as a polars DataFrame.

    `name` is one of `VIEWS`. `set` is `"open"` or the held-out label. The view
    name is built here and nowhere else, so no other module spells it.

    The held-out branch goes through `_unlocked()` first. It is the runtime
    half of the guard (GD-03): even with the database on disk and the view
    defined, this call raises until the six preconditions hold.

    The keyword is `set` because SOP W1.8 names it `set`. It shadows the
    builtin inside this one function and nowhere else.
    """
    if name not in VIEWS:
        raise ValueError(f"name={name!r} is not one of {VIEWS}")
    if set not in (OPEN, HELD_OUT):
        raise ValueError(f"set={set!r} is not {OPEN!r} or {HELD_OUT!r}")
    if set == HELD_OUT and not _unlocked():
        raise SealViolation(
            f"v_{name}_{set} is closed: " + "; ".join(unlock_report()["failed"]) + ". "
            "Only the owner opens it, after the W9.7 ceremony."
        )
    view = f"v_{name}_{set}"
    if con is not None:
        return con.execute(f"SELECT * FROM {view}").pl()
    from absump import db

    connection = db.connect(read_only=True)
    try:
        return connection.execute(f"SELECT * FROM {view}").pl()
    finally:
        connection.close()


# ------------------------------------------------------------------ the gate
def _git(*args: str, timeout: float = _GIT_TIMEOUT_S) -> tuple[int, str]:
    """Run one git command in the repository. Never raises; 127 means no git."""
    try:
        done = _subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, _subprocess.SubprocessError):
        return 127, ""
    return done.returncode, done.stdout.strip()


def _git_bytes(*args: str) -> tuple[int, bytes]:
    """The same, for content that must be hashed byte for byte."""
    try:
        done = _subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, _subprocess.SubprocessError):
        return 127, b""
    return done.returncode, done.stdout


def _tag_exists(tag: str) -> bool:
    return _git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")[0] == 0


def _is_ancestor(earlier: str, later: str) -> bool:
    return _git("merge-base", "--is-ancestor", earlier, later)[0] == 0


def _worktree_clean() -> bool:
    code, out = _git("status", "--porcelain")
    return code == 0 and out == ""


def _tag_is_pushed(remote: str = _REMOTE) -> bool:
    """The pre-registration must be public, not merely local.

    `git ls-remote --tags <remote> refs/tags/<tag>` must return the same object
    sha as the local ref. A network failure is a failed check, not a pass: the
    gate is closed by default.
    """
    tag = _prereg_tag()
    local_code, local_sha = _git("rev-parse", f"refs/tags/{tag}")
    if local_code != 0 or not local_sha:
        return False
    code, out = _git("ls-remote", "--tags", remote, f"refs/tags/{tag}", timeout=30.0)
    if code != 0 or not out:
        return False
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == f"refs/tags/{tag}" and parts[0] == local_sha:
            return True
    return False


def _prereg_hash_matches() -> bool:
    """`quality/prereg.lock` against the tagged PREREGISTRATION.md and annexes.

    The lock is `shasum -a 256` output: one `<sha256>  <path>` line per file.
    Each path is re-hashed from the tagged blob, not from the worktree, so an
    edit after the tag cannot satisfy it.
    """
    tag = _prereg_tag()
    if not PREREG_LOCK.is_file():
        return False
    lines = [ln for ln in PREREG_LOCK.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return False
    seen_root = False
    for line in lines:
        parts = line.split(None, 1)
        if len(parts) != 2:
            return False
        expected, path = parts[0].strip(), parts[1].strip().lstrip("*")
        if path == PREREG_DOC.name:
            seen_root = True
        code, blob = _git_bytes("show", f"{tag}:{path}")
        if code != 0:
            return False
        if _hashlib.sha256(blob).hexdigest() != expected:
            return False
    return seen_root


def unlock_report() -> dict[str, Any]:
    """The six preconditions, each with its own verdict. Diagnostics, not a gate.

    SOP phase 5 lists them; SOP W9.7 layer 2 writes them as one `and` chain.
    `_unlocked()` is that chain. This function reports which clause failed so a
    refusal can say so in one line.
    """
    tag = _prereg_tag()
    checks: dict[str, bool] = {
        f"{UNLOCK_ENV}=1 in this shell": _os.environ.get(UNLOCK_ENV) == "1",
        f"tag {tag} exists": _tag_exists(tag),
        f"tag {tag} is an ancestor of HEAD": _is_ancestor(tag, "HEAD"),
        "worktree is clean": _worktree_clean(),
        f"quality/prereg.lock matches {tag}": _prereg_hash_matches(),
        f"tag {tag} is pushed to {_REMOTE}": _tag_is_pushed(),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "failed": [name for name, ok in checks.items() if not ok],
    }


def _unlocked() -> bool:
    """SOP W9.7, layer 2, verbatim: all six preconditions, or closed.

    Short-circuits on the environment variable, so the ordinary case costs no
    subprocess. This function never sets `ABS_SEAL_UNLOCK`; only the owner
    does, in one shell, after the W9.7 ceremony (rule 0.5.1).
    """
    tag = _prereg_tag()
    return (
        _os.environ.get(UNLOCK_ENV) == "1"
        and _tag_exists(tag)
        and _is_ancestor(tag, "HEAD")
        and _worktree_clean()
        and _prereg_hash_matches()
        and _tag_is_pushed(_REMOTE)
    )


# ---------------------------------------------------------------- self check
_REQUIRED_NAMES: tuple[str, ...] = ("assert_unsealed", "sealed_only", "frame", "_unlocked")


def _selfcheck() -> int:
    """Seven checks over this module. Reads no data, opens no database.

    `python -m absump.seal --selfcheck` is the registered verify command for
    W1.8. It is safe in phase 01: every frame below is built in memory from
    literal tuples, and nothing touches the warehouse or the network.
    """
    failures: list[str] = []
    total = 7

    missing = [n for n in _REQUIRED_NAMES if not hasattr(_module(), n)]
    if missing:
        failures.append(f"1/7 missing public name(s): {', '.join(missing)}")

    try:
        boundary = _first_held_out_date()
        tag = _prereg_tag()
    except Exception as exc:
        boundary, tag = None, "?"
        failures.append(f"2/7 config/seal.yml: {exc}")

    for path in (Path(__file__).resolve(), REPO_ROOT / "quality" / "sql" / "analysis_set.sql"):
        if not path.is_file():
            failures.append(f"3/7 allowlisted path missing: {path}")

    open_frame = {"official_date": ["2026-09-20", "2026-09-21", _dt.date(2025, 10, 29)]}
    try:
        assert_unsealed(open_frame, "official_date")
    except SealViolation as exc:
        failures.append(f"4/7 an open frame was rejected: {exc}")

    mixed = {"official_date": ["2026-09-21", "2026-09-23"]}
    try:
        assert_unsealed(mixed, "official_date")
        failures.append("5/7 a frame past the boundary was accepted")
    except SealViolation:
        pass

    if _os.environ.get(UNLOCK_ENV) is not None:
        failures.append(f"6/7 {UNLOCK_ENV} is set in this shell; SOP rule 0.5.1 forbids it here")
    else:
        try:
            sealed_only(mixed, "official_date")
            failures.append("6/7 sealed_only returned rows while the gate is shut")
        except SealViolation:
            pass

    try:
        frame("pitch", set=HELD_OUT)
        failures.append("7/7 frame returned rows while the gate is shut")
    except SealViolation:
        pass
    except Exception as exc:
        failures.append(f"7/7 frame raised {type(exc).__name__} instead of SealViolation: {exc}")

    if failures:
        for line in failures:
            print(f"SEAL MODULE FAIL {line}")
        print(f"SEAL MODULE FAILED ({len(failures)} of {total})")
        return 1
    stamp = boundary.isoformat() if boundary is not None else "?"
    print(f"SEAL MODULE OK ({total}/{total}) boundary {stamp}, tag {tag}, gate shut")
    return 0


def _module() -> Any:
    import sys

    return sys.modules[__name__]


if __name__ == "__main__":
    import sys

    argv = sys.argv[1:]
    if argv and argv != ["--selfcheck"]:
        print("usage: python -m absump.seal [--selfcheck]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(_selfcheck())
