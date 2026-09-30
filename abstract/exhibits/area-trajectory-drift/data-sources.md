# Data sources, area-trajectory-drift

Every number on the figure is read by `make_exhibit.py` from these committed tables under
`out/ch1/tab/`. No file under `data/` and no model object is read; no fit is run. Printed
values are the table values rounded to one decimal by the script.

## Files, rows and columns read

- `T3_estimands.csv`, rows `fit=main`, `arm=primary`, `estimand=area_sqin`, `season` 2022 to 2026:
  columns `point`, `lo95`, `hi95`, `units` (checked equal to `sq in`).
- `T4_decomposition.csv`, rows `fit=main`, `arm=primary`, `estimand=area_sqin`, `component` in
  {`g`, `delta_buffer`, `delta_abs`}: columns `point`, `lo95`, `hi95`, `units` (checked).
- `T5_placebos.csv`, row `placebo=P1`, `quantity=area_sqin 2024 minus 2023`: columns `estimate`,
  `lo`, `hi`, `interval_level`, `margin_or_threshold`, `verdict`, `units` (checked).

## Numbers that appear on the figure, its caption and its alt text

Fenced as code: these are table cells and raw values, provenance rather than printed results, so quality/check_numbers.py does not read them.

```text
| Printed | Value in table | Source |
|---|---:|---|
| 494.6 (bar 490.4 to 498.7) | 494.641599 [490.384479, 498.655538] | T3_estimands.csv, season 2022, point, lo95, hi95 |
| 484.3 (bar 480.1 to 488.1) | 484.309032 [480.128224, 488.075370] | T3_estimands.csv, season 2023, point, lo95, hi95 |
| 495.1 (bar 490.8 to 499.1) | 495.095380 [490.814981, 499.120908] | T3_estimands.csv, season 2024, point, lo95, hi95 |
| 471.9 (bar 468.0 to 475.7) | 471.918904 [468.008368, 475.722054] | T3_estimands.csv, season 2025, point, lo95, hi95 |
| 439.1 (bar 435.3 to 442.4) | 439.072874 [435.256732, 442.383231] | T3_estimands.csv, season 2026, point, lo95, hi95 |
| trend +0.3 per season (95%: −1.6 to 2.2), caption only | 0.255104 [-1.647455, 2.199646] | T4_decomposition.csv, component g |
| 2025 step −23.4 (95%: −28.3 to −18.6) | -23.431580 [-28.318017, -18.572489] | T4_decomposition.csv, component delta_buffer |
| 2026 step −33.1 (95%: −37.5 to −28.7) | -33.101134 [-37.455995, -28.740883] | T4_decomposition.csv, component delta_abs |
| 2023 to 2024 +10.8 on the small bracket; (90%: 7.7 to 13.9) and the verdict in the caption | 10.786347 [7.727318, 13.941274], level 0.9, margin 3.0, verdict fail | T5_placebos.csv, P1, estimate, lo, hi, interval_level, margin_or_threshold, verdict |
```

## Derived positions (not printed)

Fenced as code: these are table cells and raw values, provenance rather than printed results, so quality/check_numbers.py does not read them.

```text
- Step baselines, where each bracket and each drift bar start: 2024 level + g = 495.350484; 2025 level + g = 472.174008.
  The script checks that level minus baseline equals the T4 step to 1e-6.
- Drift bars: 10.786347 sq in tall, hanging from each baseline, so they end at 484.564136 and 461.387661.
  The script checks that the P1 estimate equals the 2024 minus 2023 level to 1e-6.
- The small bracket runs from the 2023 level to the 2024 level.
- Period band labels are the study's period names; no number in them is a statistic.
```

## Not drawn

The All-Star-break placebo tick is not on the figure: it sat beside no bracket. The abstract's Results print the largest All-Star-break swing.

## Seal

The tables read were committed before this exhibit was built (`git log -- out/ch1/tab`) and
T1_sample.csv records the last open 2026 date as 2026-09-21. The script reads nothing else.
