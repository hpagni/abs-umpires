# R/lib/zone.R -- the zone and kinematics module. SOP step W3.3, section 2.5.
#
# Shared by Chapter 1 (W3), Chapter 2 (W4) and Chapter 3 (W5). Source it, do not
# copy it: nothing downstream re-derives the re-projection or the edge rule.
#
#   source("R/lib/zone.R")
#
# THE ROOT (section 2.5 item A1, architect blocker 1). Statcast kinematics are
# defined at the reference plane y = 50 ft. Both roots of
# 0.5*ay*t^2 + vy0*t + (y_ref - y) = 0 are positive; for the data contract's own
# pitch (vy0 = -136.346, ay = 28.540) they are 0.3707 s and 9.1839 s at
# y = 17/12. The larger root is the unphysical second crossing after the
# parabola turns over, and taking it gives dz = +17.2 in instead of -0.911 in.
# Because vy0 < 0 and ay > 0, the minus branch of the quadratic formula IS the
# smaller root, so t_at_y has no branch, no ifelse and no root selection. The
# round-trip identity test does not catch the wrong root, because the wrong root
# round-trips perfectly; UT-11's t-range, t_mid > t_front, dz < 0 and
# brute-force assertions in tests/ch1/test_zone.R are what catch it.
#
# THE PLANES. Front of plate y = 17/12 ft, middle y = 8.5/12 ft. MLB 2026 and
# AAA 2024 Savant CSV plate_x/plate_z are published at the middle; MLB 2015-2025
# CSV and the Stats API pX/pZ at the front. Mixing the two injects a systematic
# -0.99 in shift in plate_z, the same order as the effect Chapter 1 measures.
#
# THE EDGE (D-14). r = 1.45 in, any-part-of-ball, Euclidean at the corners.
# The ABS zone-truth predicate is signed_edge_in(...) - BALL_R_IN < 0, which is
# exactly Savant's edge_dist_calc < 0.
#
# The Python twin is src/absump/geometry.py. tests/ch1/test_zone.R asserts the
# two agree to 1e-12 ft on 100,000 real pitches.

PLATE_HALF_W_FT <- 8.5/12      # 17-inch plate
Y_FRONT_FT      <- 17/12
Y_MID_FT        <- 8.5/12
Y_REF_FT        <- 50.0
ABS_TOP_FRAC    <- 0.535
ABS_BOT_FRAC    <- 0.27
BALL_R_IN       <- 1.45

# Smaller positive root, closed form (section 2.5, item A1). vy0 < 0 and ay > 0,
# so the minus branch IS the smaller root: no root selection, no ifelse.
t_at_y <- function(y, vy0, ay, y_ref = Y_REF_FT) {
  stopifnot(all(vy0 < 0), all(ay > 0))
  (-vy0 - sqrt(vy0^2 - 2 * ay * (y_ref - y))) / ay
}

reproject <- function(plate_x, plate_z, vx0, vy0, vz0, ax, ay, az, y_from, y_to) {
  ta <- t_at_y(y_from, vy0, ay); tb <- t_at_y(y_to, vy0, ay)
  dt <- tb - ta; dq <- tb^2 - ta^2
  list(x = plate_x + vx0 * dt + 0.5 * ax * dq,
       z = plate_z + vz0 * dt + 0.5 * az * dq)
}

abs_top_ft <- function(h_in) ABS_TOP_FRAC * h_in / 12
abs_bot_ft <- function(h_in) ABS_BOT_FRAC * h_in / 12

signed_edge_in <- function(x_ft, z_ft, top_ft, bot_ft, hw_ft = PLATE_HALF_W_FT) {
  dx <- abs(x_ft) - hw_ft
  dz <- pmax(bot_ft - z_ft, z_ft - top_ft)
  ifelse(dx > 0 & dz > 0, sqrt(dx^2 + dz^2), pmax(dx, dz)) * 12
}
nearest_edge <- function(x_ft, z_ft, top_ft, bot_ft, hw_ft = PLATE_HALF_W_FT) {
  d <- cbind(side = abs(x_ft) - hw_ft, top = z_ft - top_ft, bot = bot_ft - z_ft)
  c("side","top","bot")[max.col(d, ties.method = "first")]
}
z_norm <- function(z_ft, h_in) z_ft * 12 / h_in
