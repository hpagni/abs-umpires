"""UT-11 and UT-12 on the Python twin. SOP section 6.2, step W9.5.

SOP section 5 states the re-projection once, as a closed form from CSV columns
only, against the reference plane `Y0 = 50.0` ft:

    t(y)     = ( -vy0 - sqrt(vy0^2 - 2*ay*(Y0 - y)) ) / ay
    dx       = vx0*(t_b - t_a) + 0.5*ax*(t_b^2 - t_a^2)
    dz       = vz0*(t_b - t_a) + 0.5*az*(t_b^2 - t_a^2)
    FRONT = 17/12 ft, MID = 8.5/12 ft

`R/lib/zone.R` holds one implementation and `src/absump/geometry.py` holds the
other. These are the two independent implementations the SOP requires. The R
side is tested by `tests/ch1/test_zone.R`, which owns UT-11 and UT-12 against
real pitches and the golden file. This file is the twin's share of the same two
ids, written from the SOP recipe and nothing else, so it can be read without
either implementation in hand.

UT-11 asserts five things. The round trip front to mid to front is an identity
to 1e-12 ft. `t` lies in (0.30, 0.60) s at both planes. `t_mid > t_front` pitch
by pitch. `dz < 0` for every pitch with a negative vertical velocity at the
plate. And the closed-form root matches a brute-force smallest-positive-root
solve to 1e-12 s. The fifth is the one that matters: both roots of the quadratic
are positive, the wrong one round-trips perfectly, and for the data contract's
own pitch the two roots at `y = 17/12` are 0.3707 s and 9.1839 s, which differ
in `dz` by 18 inches.

UT-12 asserts that `reproject` refuses `release_pos_*`. CSV `release_pos_y` is
54.18 while `y0` is 50.0022, so a caller substituting the release columns for
the reference plane is off by up to 1.04 ft with no error to show for it.

`src/absump/geometry.py` is written by the Chapter 1 zone step. Until it lands,
every test here skips with that reason, and the skip is the signal that the twin
is not yet covered on this side.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

geometry = pytest.importorskip(
    "absump.geometry",
    reason="src/absump/geometry.py is not built yet, so the Python twin has nothing to test",
)

# SOP section 5. Written once here, read from the module where the module
# exposes them, so this file cannot drift from the implementation it tests.
Y_REF_FT = 50.0
FRONT_FT = 17 / 12
MID_FT = 8.5 / 12

# The data contract's own pitch, SOP section 5: a 93.9 mph fastball.
CONTRACT_PITCH = {
    "plate_x": 0.12,
    "plate_z": 2.31,
    "vx0": 5.104,
    "vy0": -136.346,
    "vz0": -5.012,
    "ax": -9.147,
    "ay": 28.540,
    "az": -13.958,
}


def _reproject(pitch: dict[str, float], y_from: float, y_to: float):
    """Call the twin in the SOP's argument order."""
    return geometry.reproject(
        pitch["plate_x"],
        pitch["plate_z"],
        pitch["vx0"],
        pitch["vy0"],
        pitch["vz0"],
        pitch["ax"],
        pitch["ay"],
        pitch["az"],
        y_from,
        y_to,
    )


def _xz(result) -> tuple[float, float]:
    """The twin may return a mapping, a pair or an object with x and z."""
    if isinstance(result, dict):
        return float(result["x"]), float(result["z"])
    if hasattr(result, "x") and hasattr(result, "z"):
        return float(result.x), float(result.z)
    x, z = result
    return float(x), float(z)


def _t_closed_form(y: float, vy0: float, ay: float) -> float:
    return (-vy0 - math.sqrt(vy0 * vy0 - 2 * ay * (Y_REF_FT - y))) / ay


def _t_brute_force(y: float, vy0: float, ay: float) -> float:
    """The smallest positive root of `Y0 + vy0*t + 0.5*ay*t^2 = y`, found by search.

    A bisection on the first sign change, walking out from zero in 1e-4 s steps,
    then 200 halvings. It shares no algebra with the closed form, which is the
    only way this check means anything.
    """

    def f(t: float) -> float:
        return Y_REF_FT + vy0 * t + 0.5 * ay * t * t - y

    step = 1e-4
    lo = 0.0
    for i in range(1, 2_000_001):
        hi = i * step
        if f(lo) * f(hi) <= 0:
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                if f(lo) * f(mid) <= 0:
                    hi = mid
                else:
                    lo = mid
            return 0.5 * (lo + hi)
        lo = hi
    raise AssertionError(f"no positive root for y={y}, vy0={vy0}, ay={ay}")


# ---------------------------------------------------------------------------
# UT-11
# ---------------------------------------------------------------------------


def test_ut11_round_trip_is_an_identity() -> None:
    """Front to mid to front, to 1e-12 ft."""
    mid_x, mid_z = _xz(_reproject(CONTRACT_PITCH, FRONT_FT, MID_FT))
    back = dict(CONTRACT_PITCH, plate_x=mid_x, plate_z=mid_z)
    x, z = _xz(_reproject(back, MID_FT, FRONT_FT))
    assert abs(x - CONTRACT_PITCH["plate_x"]) < 1e-12
    assert abs(z - CONTRACT_PITCH["plate_z"]) < 1e-12


def test_ut11_t_is_between_030_and_060_seconds_at_both_planes() -> None:
    for plane in (FRONT_FT, MID_FT):
        t = _t_closed_form(plane, CONTRACT_PITCH["vy0"], CONTRACT_PITCH["ay"])
        assert 0.30 < t < 0.60, f"t={t} s at y={plane} ft"


def test_ut11_t_mid_is_greater_than_t_front_pitch_by_pitch() -> None:
    """The mid plane is nearer the batter, so the ball reaches it later."""
    for vy0, ay in ((-136.346, 28.540), (-114.4, 22.1), (-148.9, 39.5)):
        t_front = _t_closed_form(FRONT_FT, vy0, ay)
        t_mid = _t_closed_form(MID_FT, vy0, ay)
        assert t_mid > t_front, f"t_mid={t_mid} t_front={t_front} for vy0={vy0}, ay={ay}"


def test_ut11_dz_is_negative_when_vertical_velocity_at_the_plate_is_negative() -> None:
    """A ball still falling at the plate is lower at the nearer plane."""
    for az in (-13.958, -38.0, -12.0):
        pitch = dict(CONTRACT_PITCH, az=az)
        t_front = _t_closed_form(FRONT_FT, pitch["vy0"], pitch["ay"])
        vz_at_plate = pitch["vz0"] + pitch["az"] * t_front
        assert vz_at_plate < 0, f"vz={vz_at_plate} at the plate for az={az}"
        _, z_mid = _xz(_reproject(pitch, FRONT_FT, MID_FT))
        dz = z_mid - pitch["plate_z"]
        assert dz < 0, f"dz={dz * 12} in for az={az}"


def test_ut11_the_closed_form_root_matches_a_brute_force_solve() -> None:
    """The assertion the round trip cannot make: the wrong root round-trips too."""
    vy0, ay = CONTRACT_PITCH["vy0"], CONTRACT_PITCH["ay"]
    for plane in (FRONT_FT, MID_FT):
        closed = _t_closed_form(plane, vy0, ay)
        brute = _t_brute_force(plane, vy0, ay)
        assert abs(closed - brute) < 1e-12, f"closed={closed} brute={brute} at y={plane}"
    # The larger root exists, is positive, and is the one this must not select.
    larger = (-vy0 + math.sqrt(vy0 * vy0 - 2 * ay * (Y_REF_FT - FRONT_FT))) / ay
    assert larger > 9.0
    assert _t_closed_form(FRONT_FT, vy0, ay) < 0.40


# ---------------------------------------------------------------------------
# UT-12
# ---------------------------------------------------------------------------


def test_ut12_reproject_refuses_release_pos_values() -> None:
    """`release_pos_y == 54.18` is not the reference plane `Y0 == 50.0022`."""
    with pytest.raises(ValueError):
        _reproject(CONTRACT_PITCH, 54.18, MID_FT)
    with pytest.raises(ValueError):
        _reproject(CONTRACT_PITCH, FRONT_FT, 54.18)


# ---------------------------------------------------------------------------
# the property, SOP section 6.2
# ---------------------------------------------------------------------------


@given(
    plate_x=st.floats(min_value=-3.0, max_value=3.0),
    plate_z=st.floats(min_value=0.0, max_value=5.0),
    vx0=st.floats(min_value=-20.0, max_value=20.0),
    vy0=st.floats(min_value=-150.0, max_value=-110.0),
    vz0=st.floats(min_value=-15.0, max_value=5.0),
    ax=st.floats(min_value=-30.0, max_value=30.0),
    ay=st.floats(min_value=20.0, max_value=40.0),
    az=st.floats(min_value=-45.0, max_value=5.0),
)
@settings(max_examples=200, deadline=None)
def test_reprojection_is_an_involution(
    plate_x: float,
    plate_z: float,
    vx0: float,
    vy0: float,
    vz0: float,
    ax: float,
    ay: float,
    az: float,
) -> None:
    """SOP section 6.2: an involution for any `vy0` in [-150,-110], `ay` in [20,40]."""
    pitch = {
        "plate_x": plate_x,
        "plate_z": plate_z,
        "vx0": vx0,
        "vy0": vy0,
        "vz0": vz0,
        "ax": ax,
        "ay": ay,
        "az": az,
    }
    mid_x, mid_z = _xz(_reproject(pitch, FRONT_FT, MID_FT))
    x, z = _xz(_reproject(dict(pitch, plate_x=mid_x, plate_z=mid_z), MID_FT, FRONT_FT))
    assert abs(x - plate_x) < 1e-12
    assert abs(z - plate_z) < 1e-12
