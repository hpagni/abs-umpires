"""The plate-plane re-projection. SOP step W3.3, section 2.5 item A1.

This module holds one public function. `R/lib/zone.R` holds the other
implementation of the same closed form, and `tests/ch1/test_zone.R` asserts the
two agree to 1e-12 ft on 100,000 real pitches. Nothing downstream re-derives
the projection.

THE GEOMETRY. Statcast kinematics `vx0, vy0, vz0, ax, ay, az` are defined at the
reference plane `y = 50` ft. The front of the plate is `y = 17/12` ft and the
middle is `y = 8.5/12` ft. Solving `y(t) = y_ref + vy0*t + 0.5*ay*t^2` for the
plate crossing and evaluating the same parabola in x and z gives

    t(y) = ( -vy0 - sqrt(vy0^2 - 2*ay*(y_ref - y)) ) / ay
    x(b) = plate_x + vx0*(tb - ta) + 0.5*ax*(tb^2 - ta^2)
    z(b) = plate_z + vz0*(tb - ta) + 0.5*az*(tb^2 - ta^2)

THE ROOT. Both roots of the quadratic are positive. For the data contract's own
pitch, `vy0 = -136.346` and `ay = 28.540`, they are 0.3707 s and 9.1839 s at
`y = 17/12`; the larger is the unphysical second crossing after the parabola
turns over, and taking it gives `dz = +17.2 in` instead of `-0.911 in`. Because
`vy0 < 0` and `ay > 0` the minus branch is the smaller root, so `_t_at_y` has no
branch and no root-selection logic. The round-trip identity does not catch the
wrong root, because the wrong root round-trips perfectly. UT-11's four extra
assertions do.

THE PLANES DIFFER BY SOURCE. MLB 2026 and AAA 2024 CSV `plate_x/plate_z` are
published at the middle plane; MLB 2015-2025 CSV and the Stats API `pX/pZ` at
the front. Mixing them injects a systematic -0.99 in shift in `plate_z`.

UT-12. `release_pos_x/y/z` are the release point, not the reference plane:
`release_pos_y == 54.18` against `y0 == 50.0022`, and substituting them breaks
the projection by up to 1.04 ft. A plane argument outside the plate region is
refused with `ValueError` rather than projected, because the failure is silent
otherwise.

Scalars and array-likes are both accepted. When any argument is an array-like
the whole call is evaluated with NumPy and the two components come back as
arrays.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

__all__ = ["reproject"]

# SOP section 2.5. The same seven constants as `R/lib/zone.R`.
PLATE_HALF_W_FT = 8.5 / 12  # 17-inch plate
Y_FRONT_FT = 17 / 12
Y_MID_FT = 8.5 / 12
Y_REF_FT = 50.0
ABS_TOP_FRAC = 0.535
ABS_BOT_FRAC = 0.27
BALL_R_IN = 1.45

# The two values UT-12 exists to keep apart, and the widest plane this function
# will project to. Every plate plane in the project is 17/12 ft or less; the
# release point is 54.18 ft and the API's reference plane is 50.0022 ft, so any
# argument above the bound is a substituted column and not a plane.
RELEASE_POS_Y_FT = 54.18
API_Y0_FT = 50.0022
PLANE_MAX_FT = 5.0


def _is_scalar(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _check_plane(name: str, y: Any) -> float:
    """UT-12. A plane argument is a plate plane or it is an error."""
    if not _is_scalar(y):
        raise ValueError(
            f"{name} must be a scalar plate plane in feet, got {type(y).__name__}. "
            f"The project's planes are {Y_FRONT_FT!r} (front) and {Y_MID_FT!r} (middle)."
        )
    y = float(y)
    if not math.isfinite(y):
        raise ValueError(f"{name} is not finite: {y!r}")
    if y < 0.0 or y > PLANE_MAX_FT:
        raise ValueError(
            f"{name}={y!r} ft is not a plate plane. The plate planes are "
            f"{Y_FRONT_FT!r} ft (front of plate) and {Y_MID_FT!r} ft (middle). "
            f"release_pos_y is {RELEASE_POS_Y_FT} ft and the Stats API reference "
            f"plane y0 is {API_Y0_FT} ft; release_pos_x/y/z are the release point, "
            f"not x0/y0/z0, and substituting them breaks the projection by up to "
            f"1.04 ft. SOP section 2.5, UT-12."
        )
    return y


def _t_at_y(y: float, vy0: Any, ay: Any) -> Any:
    """Smaller positive root, closed form. No root selection, no branch."""
    disc = vy0 * vy0 - 2.0 * ay * (Y_REF_FT - y)
    if _is_scalar(vy0) and _is_scalar(ay):
        if vy0 >= 0.0:
            raise ValueError(f"vy0 must be negative, got {vy0!r}")
        if ay <= 0.0:
            raise ValueError(f"ay must be positive, got {ay!r}")
        if disc < 0.0:
            raise ValueError(f"the pitch never reaches y={y!r} ft: discriminant {disc!r}")
        return (-vy0 - math.sqrt(disc)) / ay
    if not np.all(np.asarray(vy0) < 0.0):
        raise ValueError("every vy0 must be negative")
    if not np.all(np.asarray(ay) > 0.0):
        raise ValueError("every ay must be positive")
    if not np.all(disc >= 0.0):
        raise ValueError(f"some pitch never reaches y={y!r} ft: negative discriminant")
    return (-vy0 - np.sqrt(disc)) / ay


def reproject(
    plate_x: Any,
    plate_z: Any,
    vx0: Any,
    vy0: Any,
    vz0: Any,
    ax: Any,
    ay: Any,
    az: Any,
    y_from: float,
    y_to: float,
) -> dict[str, Any]:
    """Move a published plate crossing from one plate plane to another.

    `plate_x` and `plate_z` are the coordinates as published at `y_from`, and
    the six kinematic columns are the Statcast ones, defined at y = 50 ft. The
    result is `{"x": ..., "z": ...}` at `y_to`.

    Raises `ValueError` when a plane argument is not a plate plane, which is
    what a caller handing over `release_pos_y` (54.18 ft) or the API's `y0`
    (50.0022 ft) does, and when `vy0 >= 0` or `ay <= 0`.
    """
    y_from = _check_plane("y_from", y_from)
    y_to = _check_plane("y_to", y_to)
    scalar = all(_is_scalar(v) for v in (plate_x, plate_z, vx0, vy0, vz0, ax, ay, az))
    if not scalar:
        plate_x, plate_z, vx0, vy0, vz0, ax, ay, az = (
            np.asarray(v, dtype=float) for v in (plate_x, plate_z, vx0, vy0, vz0, ax, ay, az)
        )
    ta = _t_at_y(y_from, vy0, ay)
    tb = _t_at_y(y_to, vy0, ay)
    dt = tb - ta
    dq = tb * tb - ta * ta
    return {
        "x": plate_x + vx0 * dt + 0.5 * ax * dq,
        "z": plate_z + vz0 * dt + 0.5 * az * dq,
    }
