"""Smoke check 2: the Python pins. SOP step W1.15.

The four versions SOP section 2.2 pins and W1.4 verifies: Python 3.12.14, duckdb
1.5.5, polars 1.44.2, pyarrow 25.0.1. Printed on one line, in that order, and
compared against the expected line as a whole rather than field by field, so a
reordering is a failure too.

WHY IT IS A FILE AND NOT A ONE-LINER. ops/lint_http.sh rule SH-PYTHON-C reads an
interpreter started from a shell script as a possible request call site, and
reads its program text over the whole file. A `python -c` inside ops/smoke.sh
therefore fails the http-etiquette hook, which smoke check 11 runs. Moving the
three lines into a file that ops/smoke.sh runs by path removes the idiom instead
of asking for an exemption.

pyarrow is the pin that matters most here. SOP section 2.2 fixes it to 25.0.1 to
match R arrow 25.0.1 exactly, so that both sides of the seam write and read one
Parquet dialect. Check 4 asserts the two version strings are the same string.
duckdb is pinned explicitly rather than inherited from dbt-duckdb, because
dbt-duckdb declares duckdb>=1.0.0 and a routine lock upgrade could otherwise move
the Python duckdb off the version the duckdb CLI is on.

Run: uv run --locked python ops/smoke_pins.py
"""

from __future__ import annotations

import sys

import duckdb
import polars
import pyarrow

EXPECTED = "3.12.14 1.5.5 1.44.2 25.0.1"


def main() -> int:
    got = " ".join(
        (
            "{}.{}.{}".format(*sys.version_info[:3]),
            duckdb.__version__,
            polars.__version__,
            pyarrow.__version__,
        )
    )
    if got != EXPECTED:
        print(f"smoke-pins FAIL: python duckdb polars pyarrow are {got!r}, expected {EXPECTED!r}")
        return 1
    print(f"smoke-pins OK: python duckdb polars pyarrow {got}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
