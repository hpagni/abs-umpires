# Sensitivity grid

Read from `out/ch1/tab/sensitivity_grid.csv`: 26 binned and 5 `bam` rows ran; `postseason_in` is deferred. Area in sq in, 95% intervals in brackets.

**Sign stability, over the 31 computed rows only.** Delta_buffer and Delta_ABS each keep one sign on area, every edge and shadow rate, and no 95% interval crosses zero.

**CH1-A9 is NOT MET, because the multiverse is incomplete.** The missing cell is `postseason_in`: the Statcast and schedule pulls cover regular-season games only, so the warehouse holds no 2022 to 2025 postseason called pitch.

**Against the same estimator's primary.** The binned primary is Delta_buffer -29.5 [-32.6, -26.4] and Delta_ABS -40.7 [-43.6, -38.0]. On area only `plane_front` Delta_ABS excludes it, -37.6 [-40.4, -35.0]. On shadow rate, `plane_front` Delta_ABS and both components of `r_0`, `shadow_2` and `shadow_4` exclude it; those three change only the shadow zone. No `bam` row excludes the `bam` primary.

**Against the other estimator's primary, the CH1-A5 gap, reported as a limitation.** The `bam` primary is Delta_buffer -23.4 [-28.3, -18.6] and Delta_ABS -33.1 [-37.5, -28.7]. Every binned row, the binned primary included, excludes it on area (both components) and on half-width Delta_ABS; `k_0.75x` and `mix_unweighted` also on half-width Delta_buffer. On shadow rate, every binned row but `k_0.75x`, `plane_front` and `r_0` excludes it on Delta_buffer, and every one but those, `height_abs_cohort`, `mix_unweighted` and `pp_in` on Delta_ABS. On top-edge Delta_ABS every one but `band_6`, `height_abs_cohort`, `height_ml_offset`, `plane_front` and `pp_in` does; on the bottom edge only `plane_front` Delta_ABS. The other binned rows: `r_1.0`, `r_1.45`, `r_fitted`, `height_roster_offset`, `shadow_3`, `band_8`, `band_unrestricted`, `plane_mid`, `blocked_ball_in`, `blocked_ball_out`, `pp_out`, `postseason_out`, `k_1.5x`, `mix_2024`, `mix_2025`.

All five `bam` rows (primary, `height_abs_cohort`, `plane_front`, `k_0.75x`, `mix_unweighted`) exclude the binned primary on area, both components; `plane_front` also on shadow-rate Delta_ABS.
