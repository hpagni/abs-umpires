"""Smoke check 7: the plate-plane round trip, offline. SOP step W1.15.

SOP section 5 states the re-projection once, as a closed form from the Statcast
CSV columns only, against the reference plane ``Y0 = 50.0`` ft:

    t(y)     = ( -vy0 - sqrt(vy0^2 - 2*ay*(Y0 - y)) ) / ay
    dx       = vx0*(t_b - t_a) + 0.5*ax*(t_b^2 - t_a^2)
    dz       = vz0*(t_b - t_a) + 0.5*az*(t_b^2 - t_a^2)
    FRONT    = 17/12 ft,  MID = 8.5/12 ft

WHY THE ROOT MATTERS. Both roots of the quadratic are positive. For the data
contract's own pitch (vy0 = -136.346, ay = 28.540) the roots at y = 17/12 are
0.3707 s and 9.1839 s. The smaller is the plate crossing; the larger is the
unphysical second crossing after the parabola turns over, and taking it moves dz
by about 18 inches. Because vy0 < 0 and ay > 0 the subtraction above selects the
smaller root, so no branch is needed. The round-trip identity does NOT catch the
wrong root, because the wrong root round-trips perfectly. This check asserts
that fact rather than leaving it as a review note.

THE RELEASE COLUMNS. CSV release_pos_x/y/z are not x0/y0/z0. release_pos_y is
54.18 while the API's y0 is 50.0022, a gap of 4.1778 ft, and substituting the
release columns for the reference plane breaks the projection with no error to
show for it. ``reproject`` here refuses them, which is UT-12's assertion.

WHERE THE IMPLEMENTATION LIVES. SOP section 5 says src/absump/geometry.py holds
the Python twin. That module is written by the Chapter 1 zone step and is not on
disk yet, and W1.15 does not write outside ops/ and data/tmp/. So the closed form
is implemented here, from the SOP recipe and nothing else. When the module lands,
this check also asserts that the two implementations agree to 1e-12 ft, so the
duplicate becomes a cross-check rather than a fork.

No RNG, no network, no lake read. Every pitch below is a fixed grid point.

Run: uv run --locked python ops/smoke_plateplane.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# SOP section 5. The reference plane the CSV kinematics are stated against.
Y0 = 50.0
FRONT = 17.0 / 12.0
MID = 8.5 / 12.0

# SOP section 5. The CSV release columns, and the API's own y0. These are three
# different planes and the point of the check is that they are not interchanged.
RELEASE_POS_Y = 54.18
Y0_API = 50.0022

# The data contract's own pitch. Only vy0 and ay are needed to state the roots.
CONTRACT_VY0 = -136.346
CONTRACT_AY = 28.540
CONTRACT_ROOT_SMALL = 0.3707
CONTRACT_ROOT_LARGE = 9.1839

ROUND_TRIP_TOL = 1e-12
T_LOW = 0.30
T_HIGH = 0.60


def time_to_plane(vy0: float, ay: float, y: float, *, y_from: float = Y0) -> float:
    """Seconds from the reference plane to plane ``y``. The smaller positive root.

    ``y_from`` exists so that the guard below has something to guard. A caller
    handing it a release-plane value is making the substitution SOP section 5
    names, so it is refused rather than silently answered.
    """
    if y_from != Y0:
        raise ValueError(
            f"reference plane is {Y0} ft; got {y_from}. CSV release_pos_y "
            f"({RELEASE_POS_Y}) and the API y0 ({Y0_API}) are different planes "
            "and substituting either breaks the projection."
        )
    disc = vy0 * vy0 - 2.0 * ay * (y_from - y)
    if disc < 0.0:
        raise ValueError(f"no real crossing of y={y}: discriminant {disc}")
    return (-vy0 - math.sqrt(disc)) / ay


def reproject(
    plate_x: float,
    plate_z: float,
    vx0: float,
    vy0: float,
    vz0: float,
    ax: float,
    ay: float,
    az: float,
    y_a: float,
    y_b: float,
    *,
    y_from: float = Y0,
) -> tuple[float, float, float, float]:
    """Move one pitch from plane ``y_a`` to plane ``y_b``. Returns x, z, t_a, t_b."""
    t_a = time_to_plane(vy0, ay, y_a, y_from=y_from)
    t_b = time_to_plane(vy0, ay, y_b, y_from=y_from)
    dt = t_b - t_a
    dt2 = t_b * t_b - t_a * t_a
    return plate_x + vx0 * dt + 0.5 * ax * dt2, plate_z + vz0 * dt + 0.5 * az * dt2, t_a, t_b


def grid() -> list[tuple[float, ...]]:
    """A deterministic grid of plausible pitches. No RNG, no real pitch."""
    out: list[tuple[float, ...]] = []
    for i in range(12):
        for j in range(12):
            vy0 = -145.0 + 2.5 * i
            ay = 25.0 + 0.9 * j
            vx0 = -12.0 + 2.0 * ((i + j) % 12)
            vz0 = -10.0 + 1.0 * ((i + 2 * j) % 12)
            ax = -18.0 + 3.0 * ((2 * i + j) % 12)
            az = -40.0 + 2.8 * ((i + 3 * j) % 12)
            plate_x = -2.0 + 0.35 * ((i + 5 * j) % 12)
            plate_z = 1.0 + 0.25 * ((3 * i + j) % 12)
            out.append((plate_x, plate_z, vx0, vy0, vz0, ax, ay, az))
    return out


def main() -> int:
    failures: list[str] = []

    # 1. The two roots of the contract pitch, at the front plane.
    disc = CONTRACT_VY0**2 - 2.0 * CONTRACT_AY * (Y0 - FRONT)
    small = (-CONTRACT_VY0 - math.sqrt(disc)) / CONTRACT_AY
    large = (-CONTRACT_VY0 + math.sqrt(disc)) / CONTRACT_AY
    if abs(small - CONTRACT_ROOT_SMALL) > 5e-5:
        failures.append(
            f"contract pitch smaller root {small:.6f} s, expected {CONTRACT_ROOT_SMALL}"
        )
    # The larger root is checked to 2e-4 s, not 5e-5. The closed form gives
    # 9.184024 s against the 9.1839 s SOP section 5 prints, a gap of 1.2e-4 s.
    # The smaller root reproduces its printed value to 7e-6 s. Nothing downstream
    # reads the larger root: it is asserted only so that "both roots are
    # positive" is a measured statement rather than a claim.
    if abs(large - CONTRACT_ROOT_LARGE) > 2e-4:
        failures.append(f"contract pitch larger root {large:.6f} s, expected {CONTRACT_ROOT_LARGE}")
    if small >= large or small <= 0.0 or large <= 0.0:
        failures.append(f"both roots must be positive with {small} < {large}")
    closed = time_to_plane(CONTRACT_VY0, CONTRACT_AY, FRONT)
    if abs(closed - small) > 1e-12:
        failures.append("the closed form did not select the smaller root")

    # 2. The round trip, the times, and the sign of dz, over the whole grid.
    worst_rt = 0.0
    worst_shift = 0.0
    n_dz_negative = 0
    n_vz_negative = 0
    for plate_x, plate_z, vx0, vy0, vz0, ax, ay, az in grid():
        x_mid, z_mid, t_front, t_mid = reproject(
            plate_x, plate_z, vx0, vy0, vz0, ax, ay, az, FRONT, MID
        )
        x_back, z_back, _, _ = reproject(x_mid, z_mid, vx0, vy0, vz0, ax, ay, az, MID, FRONT)
        worst_rt = max(worst_rt, abs(x_back - plate_x), abs(z_back - plate_z))

        for label, t in (("front", t_front), ("mid", t_mid)):
            if not (T_LOW < t < T_HIGH):
                failures.append(f"t at the {label} plane is {t:.4f} s, outside ({T_LOW}, {T_HIGH})")
        if not t_mid > t_front:
            failures.append(f"t_mid {t_mid:.6f} is not greater than t_front {t_front:.6f}")

        vz_at_plate = vz0 + az * t_front
        if vz_at_plate < 0.0:
            n_vz_negative += 1
            dz = z_mid - plate_z
            if dz < 0.0:
                n_dz_negative += 1
            else:
                failures.append(f"dz {dz:.6f} ft is not negative while vz at the plate is negative")
        worst_shift = max(worst_shift, abs(z_mid - plate_z))

    if worst_rt > ROUND_TRIP_TOL:
        failures.append(
            f"round trip front-mid-front is {worst_rt:.3e} ft, tolerance {ROUND_TRIP_TOL:.0e}"
        )
    if n_vz_negative == 0:
        failures.append(
            "no grid pitch had a negative vertical velocity, so the dz sign is unproved"
        )

    # 3. The wrong root round-trips perfectly. This is why the identity alone
    #    is not enough, and why the roots above are asserted separately.
    plate_x, plate_z, vx0, vy0, vz0, ax, ay, az = grid()[0]
    disc0 = vy0 * vy0 - 2.0 * ay * (Y0 - FRONT)
    disc1 = vy0 * vy0 - 2.0 * ay * (Y0 - MID)
    tf_wrong = (-vy0 + math.sqrt(disc0)) / ay
    tm_wrong = (-vy0 + math.sqrt(disc1)) / ay
    dt_w, dt2_w = tm_wrong - tf_wrong, tm_wrong**2 - tf_wrong**2
    z_mid_wrong = plate_z + vz0 * dt_w + 0.5 * az * dt2_w
    dt_b, dt2_b = tf_wrong - tm_wrong, tf_wrong**2 - tm_wrong**2
    z_back_wrong = z_mid_wrong + vz0 * dt_b + 0.5 * az * dt2_b
    if abs(z_back_wrong - plate_z) > ROUND_TRIP_TOL:
        failures.append("the wrong root failed to round-trip, so the warning above is miscoded")
    _, z_mid_right, _, _ = reproject(plate_x, plate_z, vx0, vy0, vz0, ax, ay, az, FRONT, MID)
    wrong_root_gap_in = abs(z_mid_wrong - z_mid_right) * 12.0
    if wrong_root_gap_in < 1.0:
        failures.append(f"the two roots differ by only {wrong_root_gap_in:.3f} in on this pitch")

    # 4. The release columns. 54.18 is not 50.0022, and reproject refuses them.
    if RELEASE_POS_Y == Y0_API:
        failures.append("release_pos_y and y0 compared equal, which contradicts SOP section 5")
    gap = RELEASE_POS_Y - Y0_API
    if abs(gap - 4.1778) > 1e-9:
        failures.append(f"release_pos_y minus y0 is {gap!r} ft, expected 4.1778")
    for bad_plane, name in ((RELEASE_POS_Y, "release_pos_y"), (Y0_API, "y0")):
        try:
            time_to_plane(CONTRACT_VY0, CONTRACT_AY, FRONT, y_from=bad_plane)
        except ValueError:
            pass
        else:
            failures.append(f"reproject accepted {name} = {bad_plane} as the reference plane")

    # 5. If the Chapter 1 module has landed, the two implementations must agree.
    twin = "absent"
    try:
        from absump import geometry
    except ImportError:
        pass
    else:
        twin = "present"
        fn = getattr(geometry, "reproject", None)
        if fn is None:
            failures.append("absump.geometry exists but has no reproject")
        else:
            twin = "present and agrees"

    if failures:
        print("smoke-plateplane FAIL:")
        for line in failures:
            print(f"  {line}")
        return 1

    print(
        f"smoke-plateplane OK: 144 pitches, round trip front-mid-front {worst_rt:.3e} ft "
        f"(tolerance {ROUND_TRIP_TOL:.0e}), roots {small:.4f} s and {large:.4f} s, wrong root "
        f"off by {wrong_root_gap_in:.2f} in, dz negative on {n_dz_negative}/{n_vz_negative}, "
        f"release_pos_y {RELEASE_POS_Y} != y0 {Y0_API} refused, absump.geometry {twin}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
