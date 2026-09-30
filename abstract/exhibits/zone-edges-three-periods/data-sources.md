# Data sources: zone-edges-three-periods

Written by build.R from the same filters that drew the figure. No model object was read; no fit was run.

## Files, rows and columns read

- `out/ch1/tab/T3_estimands.csv`: rows `fit == "main"`, `arm == "primary"`, `estimand` in
  {top_in, bot_in, half_width_in, area_sqin}, `season` 2022..2026 (20 rows); columns `season`,
  `estimand`, `units`, `point`, `lo95`, `hi95`.
- `out/ch1/tab/T4_decomposition.csv`: rows `fit == "main"`, `arm == "primary"`, `estimand` in
  {top_in, bot_in, half_width_in}, `component` in {delta_buffer, delta_abs} (6 rows); columns
  `estimand`, `component`, `units`, `point`, `lo95`, `hi95`.
- `R/lib/zone.R`: the assignment lines `PLATE_HALF_W_FT`, `ABS_TOP_FRAC`, `ABS_BOT_FRAC` (evaluated, not retyped).
- `R/lib/ch1_fits.R`: the assignment lines `REF_HEIGHT_IN`, `ZN_MID`, `CENTRE_X_FT` (evaluated, not retyped).

## Numbers that appear on the figure

Rule-book rectangle (constants):
  PLATE_HALF_W_FT x 12 = 8.50 in (printed as 17 in wide); bottom ABS_BOT_FRAC x REF_HEIGHT_IN = 19.44 in;
  top ABS_TOP_FRAC x REF_HEIGHT_IN = 38.52 in; centre window CENTRE_X_FT x 12 = 3 in; ZN_MID = 0.4025.

Fitted rectangles and whiskers (T3_estimands.csv, point [lo95, hi95], in):

| season | top_in | bot_in | half_width_in | area_sqin (label) |
|---|---|---|---|---|
| 2022 | 40.96 [40.87, 41.05] | 16.68 [16.61, 16.76] | 11.13 [11.05, 11.19] | 494.6 [490.4, 498.7] (494.6 sq in) |
| 2023 | 40.76 [40.67, 40.85] | 16.63 [16.56, 16.70] | 10.94 [10.87, 11.00] | 484.3 [480.1, 488.1] (484.3 sq in) |
| 2024 | 41.24 [41.14, 41.33] | 16.79 [16.72, 16.86] | 11.06 [10.99, 11.13] | 495.1 [490.8, 499.1] (495.1 sq in) |
| 2025 | 41.19 [41.09, 41.28] | 17.02 [16.95, 17.10] | 10.62 [10.55, 10.68] | 471.9 [468.0, 475.7] (471.9 sq in) |
| 2026 | 40.69 [40.59, 40.79] | 17.73 [17.65, 17.80] | 10.34 [10.27, 10.40] | 439.1 [435.3, 442.4] (439.1 sq in) |

Widest 95% half-interval over the fifteen edge rows (printed in the note): 0.10 in.

Inset, edge steps net of the 2022-2024 trend (T4_decomposition.csv, point [lo95, hi95], in; label prints the point):

| estimand | component | point | lo95 | hi95 |
|---|---|---|---|---|
| top_in | delta_buffer | -0.18 | -0.32 | -0.05 |
| top_in | delta_abs | -0.63 | -0.76 | -0.50 |
| bot_in | delta_buffer | 0.18 | 0.08 | 0.29 |
| bot_in | delta_abs | 0.65 | 0.55 | 0.74 |
| half_width_in | delta_buffer | -0.41 | -0.49 | -0.33 |
| half_width_in | delta_abs | -0.25 | -0.32 | -0.16 |

Period labels are descriptive: 2022-2024; 2025, grading buffer 0.75 in; 2026, ABS challenges.
The area intervals are not drawn (the label carries the point only); they are listed above for the record.
