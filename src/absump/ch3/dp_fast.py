"""Chapter 3 dynamic program, the fast twin. Stub.

ABSUMP_PLACEHOLDER. The owning W5 step writes the real solver: an independent
numba reimplementation written from the equations in SOP section 5, not
translated from `dp.py`, so that MT-08's "two implementations agree < 1e-9" is
a comparison of two models rather than of one model with itself.

The stub exists in phase 01 for one reason. GD-09, the red team, plants a
held-out read in this file and requires `tests/guard/test_no_sealed_reads.py`
to fail on it by file and line. A patch cannot apply to a file that is not
there, so the file is here, minimal and honest, and the scan passes on it.

The R1 static scan named five directories and this was not one of them. A
held-out read in the solver passed the guard. The R2 scan walks the whole
repository, which is why this stub is worth what it costs.
"""

from __future__ import annotations

from typing import Any

__all__ = ["solve", "state_shape"]

# Grid extents come from SOP section 5, not from any endpoint: half-innings,
# score margin, and challenges remaining per side. They stay here as names so
# that the real solver and the stub cannot disagree about the state space.
_NOT_BUILT = "src/absump/ch3/dp_fast.py is a stub; the owning W5 step writes the solver."


def state_shape() -> tuple[int, int, int, int]:
    """The value-function shape, (t, margin, challenges_home, challenges_away)."""
    raise NotImplementedError(_NOT_BUILT)


def value_frame(con: Any) -> Any:
    """The one read. Chapter 3 trains on the open view and nothing else."""
    return con.execute("SELECT * FROM v_pitch_open").pl()


def solve(*, con: Any = None) -> Any:
    """Backward induction over the state space. Not built in phase 01."""
    raise NotImplementedError(_NOT_BUILT)
