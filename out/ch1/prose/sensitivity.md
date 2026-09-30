# Sensitivity grid

SOP W3.22. Every estimate is read from `out/ch1/tab/sensitivity_grid.csv`, which holds 27 binned rows and 5 `bam` rows. Area is in sq in, with 95% intervals in brackets.

**Sign stability, over the 31 computed rows only.** Delta_buffer and Delta_ABS each keep one sign on area, on every edge and on shadow rate. No 95% interval crosses zero. On area the highest 95% upper bounds are -16.8 for Delta_buffer and -27.6 for Delta_ABS.

**CH1-A9 is NOT MET, because the multiverse is incomplete.** The missing cell is `postseason_in`, deferred because the open view holds no 2022 to 2025 postseason called pitch. It can run once the phase 07 re-pull lands.

**Intervals that exclude the same estimator's primary.** The binned primary is Delta_buffer -29.5 [-32.6, -26.4] and Delta_ABS -40.7 [-43.6, -38.0]. On area only `plane_front` excludes it, with Delta_ABS -37.6 [-40.4, -35.0]. On shadow rate, `plane_front` Delta_ABS and both components of `r_0`, `shadow_2` and `shadow_4` exclude it. Those three change only the shadow zone, so their area and edges equal the primary's. No `bam` row excludes the `bam` primary.

**Intervals that exclude the other estimator's primary.** Every binned row excludes the pre-registered `bam` primary on area, Delta_buffer -23.4 [-28.3, -18.6] and Delta_ABS -33.1 [-37.5, -28.7]. This is the CH1-A5 gap, reported as a limitation. The rows, by factor:

- primary: the binned primary
- r: `r_0`, `r_1.0`, `r_1.45`, `r_fitted`
- height source: `height_abs_cohort`, `height_roster_offset`, `height_ml_offset`
- shadow band: `shadow_2`, `shadow_3`, `shadow_4`
- band restriction: `band_6`, `band_8`, `band_unrestricted`
- plane: `plane_mid`, `plane_front`
- blocked_ball: `blocked_ball_in`, `blocked_ball_out`
- position-player pitchers: `pp_in`, `pp_out`
- postseason: `postseason_out`
- k: `k_0.75x`, `k_1.5x`
- standardisation mix: `mix_2024`, `mix_2025`, `mix_unweighted`

All five `bam` rows exclude the binned primary on area: the `bam` primary, `height_abs_cohort`, `plane_front`, `k_0.75x` and `mix_unweighted`.
