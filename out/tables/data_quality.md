# Data quality, abs-umpires warehouse

Row counts and null rates for `warehouse/abs.duckdb`, written by
`tests/data/test_warehouse_pack.py` under SOP step W9.6. The machine-readable
copy is `out/tables/data_quality.csv`. Both files are rewritten only when a
number changes, so a re-run leaves the tree unchanged.

## Rows per table

| table | rows |
| --- | ---: |
| `main_intermediate.int_called_pitch` | 1,836,071 |
| `main_intermediate.int_challenge_opportunity` | 716,922 |
| `main_intermediate.int_challenge_resolved` | 12,300 |
| `main_intermediate.int_pitch` | 3,546,608 |
| `main_intermediate.int_re288_state` | 288 |
| `main_intermediate.int_regime` | 18,817 |
| `main_marts.agg_closed_season_drift` | 28 |
| `main_marts.agg_closed_season_rowcount` | 420 |
| `main_marts.dim_aaa_format` | 6,755 |
| `main_marts.dim_batter_season` | 3,335 |
| `main_marts.dim_game` | 18,817 |
| `main_marts.dim_player` | 1,482 |
| `main_marts.dim_umpire_game` | 18,754 |
| `main_marts.fct_called_pitch` | 1,836,071 |
| `main_marts.fct_challenge` | 12,300 |
| `main_marts.fct_challenge_opportunity` | 716,922 |
| `main_marts.fct_pitch` | 3,546,608 |
| `main_marts.fct_re288` | 288 |
| `main_marts.fct_team_game_tokens` | 4,684 |
| `main_marts.fct_wp_state` | 85,486 |
| `main_marts.mart_called_pitches` | 1,836,071 |
| `main_marts.v_called_pitch_open` | 1,836,071 |
| `main_marts.v_challenge_open` | 12,300 |
| `main_marts.v_opportunity_open` | 716,922 |
| `main_marts.v_pitch_open` | 3,546,608 |
| `main_staging.seed_synthetic_pitches` | 200 |
| `main_staging.stg_abs_challenges` | 12,300 |
| `main_staging.stg_abs_leaderboard` | 0 |
| `main_staging.stg_feed_game` | 2,342 |
| `main_staging.stg_feed_pitch` | 691,502 |
| `main_staging.stg_feed_play` | 177,769 |
| `main_staging.stg_feed_player` | 122,494 |
| `main_staging.stg_game_official` | 69,069 |
| `main_staging.stg_pitch_joined` | 691,502 |
| `main_staging.stg_schedule_game` | 18,817 |
| `main_staging.stg_statcast_pitches` | 3,546,608 |

## Rows per level and season

| table | level | season | rows |
| --- | --- | ---: | ---: |
| `main_marts.fct_pitch` | mlb | 2022 | 710,210 |
| `main_marts.fct_pitch` | mlb | 2023 | 720,684 |
| `main_marts.fct_pitch` | mlb | 2024 | 711,899 |
| `main_marts.fct_pitch` | mlb | 2025 | 712,528 |
| `main_marts.fct_pitch` | mlb | 2026 | 691,287 |
| `main_marts.fct_called_pitch` | mlb | 2022 | 367,145 |
| `main_marts.fct_called_pitch` | mlb | 2023 | 374,523 |
| `main_marts.fct_called_pitch` | mlb | 2024 | 367,017 |
| `main_marts.fct_called_pitch` | mlb | 2025 | 368,925 |
| `main_marts.fct_called_pitch` | mlb | 2026 | 358,461 |
| `main_marts.fct_challenge` | aaa | 2024 | 2,132 |
| `main_marts.fct_challenge` | mlb | 2026 | 10,168 |
| `main_marts.fct_challenge_opportunity` | mlb | 2026 | 716,922 |
| `main_marts.dim_game` | aaa | 2023 | 2,255 |
| `main_marts.dim_game` | aaa | 2024 | 2,250 |
| `main_marts.dim_game` | aaa | 2025 | 2,250 |
| `main_marts.dim_game` | mlb | 2022 | 2,430 |
| `main_marts.dim_game` | mlb | 2023 | 2,430 |
| `main_marts.dim_game` | mlb | 2024 | 2,430 |
| `main_marts.dim_game` | mlb | 2025 | 2,430 |
| `main_marts.dim_game` | mlb | 2026 | 2,342 |

## Non-null rate on the called-pitch population

DT-17 asks each column below to be at least 99.5% non-null. `arm_angle` is the
one column section 6.3 lists that no warehouse table carries; it is asserted on
the CSV by `tests/data/test_statcast_days.py`.

| level | season | column | non-null % |
| --- | ---: | --- | ---: |
| mlb | 2022 | `plate_x_mid` | 99.9393 |
| mlb | 2022 | `plate_z_mid` | 99.9393 |
| mlb | 2022 | `sz_top` | 99.9444 |
| mlb | 2022 | `sz_bot` | 99.9444 |
| mlb | 2022 | `fielder_2` | 100.0000 |
| mlb | 2022 | `delta_run_exp` | 99.9984 |
| mlb | 2022 | `delta_home_win_exp` | 100.0000 |
| mlb | 2022 | `balls` | 100.0000 |
| mlb | 2022 | `strikes` | 100.0000 |
| mlb | 2022 | `outs_when_up` | 100.0000 |
| mlb | 2022 | `inning` | 100.0000 |
| mlb | 2022 | `inning_topbot` | 100.0000 |
| mlb | 2022 | `stand` | 100.0000 |
| mlb | 2022 | `p_throws` | 100.0000 |
| mlb | 2022 | `zone` | 99.9444 |
| mlb | 2023 | `plate_x_mid` | 99.9629 |
| mlb | 2023 | `plate_z_mid` | 99.9629 |
| mlb | 2023 | `sz_top` | 99.9632 |
| mlb | 2023 | `sz_bot` | 99.9632 |
| mlb | 2023 | `fielder_2` | 100.0000 |
| mlb | 2023 | `delta_run_exp` | 99.9984 |
| mlb | 2023 | `delta_home_win_exp` | 100.0000 |
| mlb | 2023 | `balls` | 100.0000 |
| mlb | 2023 | `strikes` | 100.0000 |
| mlb | 2023 | `outs_when_up` | 100.0000 |
| mlb | 2023 | `inning` | 100.0000 |
| mlb | 2023 | `inning_topbot` | 100.0000 |
| mlb | 2023 | `stand` | 100.0000 |
| mlb | 2023 | `p_throws` | 100.0000 |
| mlb | 2023 | `zone` | 99.9632 |
| mlb | 2024 | `plate_x_mid` | 99.9608 |
| mlb | 2024 | `plate_z_mid` | 99.9608 |
| mlb | 2024 | `sz_top` | 99.9608 |
| mlb | 2024 | `sz_bot` | 99.9608 |
| mlb | 2024 | `fielder_2` | 100.0000 |
| mlb | 2024 | `delta_run_exp` | 99.9997 |
| mlb | 2024 | `delta_home_win_exp` | 100.0000 |
| mlb | 2024 | `balls` | 100.0000 |
| mlb | 2024 | `strikes` | 100.0000 |
| mlb | 2024 | `outs_when_up` | 100.0000 |
| mlb | 2024 | `inning` | 100.0000 |
| mlb | 2024 | `inning_topbot` | 100.0000 |
| mlb | 2024 | `stand` | 100.0000 |
| mlb | 2024 | `p_throws` | 100.0000 |
| mlb | 2024 | `zone` | 99.9608 |
| mlb | 2025 | `plate_x_mid` | 99.9778 |
| mlb | 2025 | `plate_z_mid` | 99.9778 |
| mlb | 2025 | `sz_top` | 99.9783 |
| mlb | 2025 | `sz_bot` | 99.9783 |
| mlb | 2025 | `fielder_2` | 100.0000 |
| mlb | 2025 | `delta_run_exp` | 99.9992 |
| mlb | 2025 | `delta_home_win_exp` | 100.0000 |
| mlb | 2025 | `balls` | 100.0000 |
| mlb | 2025 | `strikes` | 100.0000 |
| mlb | 2025 | `outs_when_up` | 100.0000 |
| mlb | 2025 | `inning` | 100.0000 |
| mlb | 2025 | `inning_topbot` | 100.0000 |
| mlb | 2025 | `stand` | 100.0000 |
| mlb | 2025 | `p_throws` | 100.0000 |
| mlb | 2025 | `zone` | 99.9783 |
| mlb | 2026 | `plate_x_mid` | 99.9453 |
| mlb | 2026 | `plate_z_mid` | 99.9453 |
| mlb | 2026 | `sz_top` | 99.9453 |
| mlb | 2026 | `sz_bot` | 99.9453 |
| mlb | 2026 | `fielder_2` | 100.0000 |
| mlb | 2026 | `delta_run_exp` | 99.9992 |
| mlb | 2026 | `delta_home_win_exp` | 100.0000 |
| mlb | 2026 | `balls` | 100.0000 |
| mlb | 2026 | `strikes` | 100.0000 |
| mlb | 2026 | `outs_when_up` | 100.0000 |
| mlb | 2026 | `inning` | 100.0000 |
| mlb | 2026 | `inning_topbot` | 100.0000 |
| mlb | 2026 | `stand` | 100.0000 |
| mlb | 2026 | `p_throws` | 100.0000 |
| mlb | 2026 | `zone` | 99.9453 |

## Assertions refreshed on the real warehouse

The module docstring of `tests/data/test_warehouse_pack.py` carries the six
places the real data is wider than the gate, with the reading taken in each.

| id | gate | observed |
| --- | --- | --- |
| DT-03 | umpire non-empty count == 0 | 0 of 3546608 staged Statcast rows |
| DT-04 | 0 automatic_ball rows in fct_called_pitch | 0 of 1836071; 784 rows carry a blank mid-plane pair, 762 untracked and 22 without kinematics |
| DT-05 | at_bat_number == at_bat_index + 1, 100% | 0 breaks on 12300 challenges |
| DT-08 | MLB 2026 allotment == 2 for 100% | 4640 of 4684 team-games at 2, 36 audited above it, 8 with no absChallenges block |
| DT-09 | play-level MJ lands on C, B or *B, 100% | 0 breaks on 10168 joined reviews |
| DT-10 | no non-MJ review in fct_challenge | 0 non-MJ rows |
| DT-11 | re-projection < 1e-6 ft, round trip < 1e-12 ft, t < 0.60 s | both tolerances met; 0 rows at or past 2.0 s, 2628 past 0.6 s |
| DT-12 | one sz_top/sz_bot ratio in MLB 2026 | 357696 of 358265 rows on 1.98148148, 569 rows in 4 games off it |
| DT-13 | height recovery < 1e-6 in | worst 3.240e-08 in on the ABS ratio |
| DT-15 | overturns == sum usedSuccessful | 5490 reconstructed against 5490, on 10168 challenges |
| DT-17 | each listed column >= 99.5% non-null | worst 99.939% on plate_x_mid, mlb 2022 |
| DT-18 | 0 dupes on every declared key | 0 on 14 declared keys |
| DT-19 | 0 orphans | 0 on 5 declared references |
| DT-20 | closed-season drift == 0 | 0 of 28 table-seasons drifted |
| DT-23 | m agrees to 0.01 in on >= 99.9% of rows | 10168 of 10168 agree, worst gap 0.000e+00 in; the drawer is not pulled, so the second source is this module's Python |
| DT-28 | every drawer challenge joins to exactly one Statcast row | 0 of 10168 challenged pitches without a key, 18 sharing it with another called pitch, 28 with any pitch |
