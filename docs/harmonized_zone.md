# The harmonized zone

SOP step W6.5, the SSAC sprint view. SOP section 3 fixes its dependencies:
`W6.5  harmonized zone     -> W3.3, W3.4, W3.8`.

This page rebuilds nothing. W3.3 owns the zone module. W3.4 owns the height tables and DT-30. W3.8 owns the zone-truth gate, DT-21. All three are gated PASS with receipts at exit 0.

This page does four things. It states the zone the three steps share. It states the height rule each consumer reads. It publishes the DT-30 coverage table. It lists where Chapter 1, Chapter 2 and the abstract disagree. The disagreements are findings, and none of them is reconciled here.

Measured on 2026-09-25 (Madrid) over the open set: MLB regular season, `analysis_set = 'open'`, 2022-04-07 to 2026-09-21. No model was fitted. Every number below was read from files already on disk.

## 1. One zone definition

| part | value | constant |
|---|---|---|
| plate | 17 in wide, half-width 8.5/12 ft | `PLATE_HALF_W_FT` |
| plane | middle of the plate, y = 8.5/12 ft; 2022-2025 re-projected from the front, y = 17/12 ft | `Y_MID_FT`, `Y_FRONT_FT` |
| top | 0.535 × H / 12 ft | `ABS_TOP_FRAC` |
| bottom | 0.27 × H / 12 ft | `ABS_BOT_FRAC` |
| distance | `signed_edge_in`: ball centre to the zone edge, inches, negative inside, Euclidean past a corner | `R/lib/zone.R` |
| edge rule, D-14 | strike when `signed_edge_in - 1.45 < 0`: any part of the ball, r = 1.45 in | `BALL_R_IN` |

H is the batter height in inches. Section 2 says which H each consumer uses.

Three modules carry the constants. Each constant holds the same binary64 value in all three.

| constant | `R/lib/zone.R` | `src/absump/geometry.py` | `src/absump/ingest/normalize_sc.py` |
|---|---|---|---|
| `PLATE_HALF_W_FT` | 8.5/12 | 8.5/12 | 8.5/12 |
| `Y_FRONT_FT` | 17/12 | 17/12 | 17/12 |
| `Y_MID_FT` | 8.5/12 | 8.5/12 | 8.5/12 |
| `ABS_TOP_FRAC` | 0.535 | 0.535 | 0.535 |
| `ABS_BOT_FRAC` | 0.27 | 0.27 | 0.27 |
| `BALL_R_IN` | 1.45 | 1.45 | 1.45 |

W3.3 checked the D-14 rule against Savant's own `edge_dist_calc`. The error is 5.773e-15 in on 20,334 drawer rows, confirmed by the independent verifier's third run. W3.8 gated the same rule on 10,168 challenged 2026 pitches (section 4).

## 2. One height rule, and the D-13 fork

Three heights are in use.

- **Chapter 1 primary.** H is roster height plus the calibration offset, 0.0022 in, in all five seasons. This is the owner's answer D-R0-02 of 2026-09-24. The sample is P0, 1,830,267 called pitches.
- **Chapter 1 robustness arm.** H is the ABS-measured height, `sz_top * 12 / 0.535`. For 2022-2025 it is back-linked from the batter's 2026 appearance. The sample is P1, 1,487,942 called pitches.
- **ABS itself.** The 2026 system scores each pitch on the measured height. The W3.8 gate uses measured height for that reason.

**The D-13 fork is decided.** The SOP rule reads: if 2022 coverage is below 60%, either shorten the baseline to 2023-2024 or make the roster-height arm primary for the pre-trend. The 2022 share of called pitches with a measured height is 0.593387. That is 2,428 called pitches short of 0.60. The owner took the roster-height branch and applied it to all five seasons, not to the pre-trend alone.

D-R0-02 cites batter-season shares from `dim_batter_season`, 303 of 693 batters in 2022 (43.7%). It was written before the DT-30 table below. The table's called-pitch share triggers the same branch, so the decision stands on the SOP's own measure.

## 3. DT-30: ABS-height coverage per season

The share is a share of called pitches. The source is `out/tables/height_coverage.csv`, written by `R/ch1/03_heights.R` (W3.4) before `prereg-v1`. The W6.5 verify command checks every row below against that file.

| season | regime | dates | called pitches | ABS-measured | ABS-measured share | roster+offset share | batters with a measured height | below 0.60 | height link |
|---|---|---|---|---|---|---|---|---|---|
| 2022 | pre_buffer | 2022-04-07 to 2022-10-05 | 367,145 | 217,859 | 0.593387 | 1.000000 | 303 of 693 | yes | backlinked_from_2026 |
| 2023 | pre_buffer | 2023-03-30 to 2023-10-01 | 374,523 | 272,064 | 0.726428 | 1.000000 | 371 of 655 | no | backlinked_from_2026 |
| 2024 | pre_buffer | 2024-03-20 to 2024-09-30 | 367,017 | 302,888 | 0.825270 | 1.000000 | 446 of 650 | no | backlinked_from_2026 |
| 2025 | buffer_2025 | 2025-03-18 to 2025-09-28 | 368,925 | 341,232 | 0.924936 | 1.000000 | 533 of 673 | no | backlinked_from_2026 |
| 2026 | abs_2026 | 2026-03-25 to 2026-09-21 | 358,461 | 358,459 | 0.999994 | 1.000000 | 657 of 659 | no | measured_in_season |

The called-pitch counts are the warehouse's `fct_called_pitch`, before W3.5's exclusions. The batter counts are batters with at least one called pitch. D-R0-02 counts every batter-season in `dim_batter_season`, so its figures differ from these by 0 to 3 batters a season.

The selection effect is W3.4's number. In 2024 the surviving-batter restriction moves the pooled contour area by +1.01 sq in, conservative 95% interval -1.22 to +3.14, on an area of 500.29 sq in. The W3.4 verifier's batter bootstrap gives +0.15 to +1.98 sq in, which excludes zero.

## 4. DT-21: the zone-truth gate

The source is `out/ch1/tab/T2_zone_gate.csv`, written by `R/ch1/11_zone_gate.R` (W3.8). The population is the 10,168 MLB 2026 challenged pitches from 2026-03-25 to 2026-09-21. The zone is mid-plate, 53.5% and 27% of H, r = 1.45 in. Nothing was fitted.

| row | height | n | agree | disagree | agreement % | bar % | verdict |
|---|---|---|---|---|---|---|---|
| overall | ABS-measured height | 10,168 | 10,164 | 4 | 99.9607 | 99.75 | PASS |
| outside_band | ABS-measured height | 7,574 | 7,573 | 1 | 99.9868 | 99.95 | PASS |
| inside_band | ABS-measured height | 2,594 | 2,591 | 3 | 99.8843 | not gated | reported |
| edge_side | ABS-measured height | 4,980 | 4,979 | 1 | 99.9799 | not gated | reported |
| edge_top | ABS-measured height | 1,707 | 1,707 | 0 | 100.0000 | not gated | reported |
| edge_bot | ABS-measured height | 3,481 | 3,478 | 3 | 99.9138 | not gated | reported |
| arm_roster_offset_overall | roster height plus offset | 10,168 | 10,043 | 125 | 98.7707 | not gated | reported |
| arm_roster_offset_outside_band | roster height plus offset | 7,575 | 7,574 | 1 | 99.9868 | not gated | reported |

The band is `|e| <= 0.5 in`, where `e = signed_edge_in - 1.45`.

## 5. Where each consumer reads the zone

| consumer | where | plane | height | edge rule |
|---|---|---|---|---|
| Chapter 1, primary fit | `data/marts/ch1_called.parquet`: `d`, `top_ft`, `bot_ft`, `zn` | mid | roster + 0.0022 in | D-14, r = 1.45 in |
| Chapter 1, robustness arm | same file: `d_abs`, `H_abs` | mid | ABS-measured | D-14, r = 1.45 in |
| W3.8 gate | `out/ch1/tab/T2_zone_gate.csv` | mid | ABS-measured | D-14, r = 1.45 in |
| Chapter 2 | `fct_challenge`: `edge_dist_calc`, `m_signed_in` | mid | published 2026 zone, which is ABS-measured | D-14, r = 1.45 in |
| abstract, `N_CALLED` slot | `docs/numbers.json`, from `fct_called_pitch` where `height_source = 'abs_measured'` | n/a | ABS-measured cohort | n/a |
| abstract, Methods template | SOP abstract draft | mid | "rebuild the zone from ABS-measured batter height" | n/a |
| warehouse | `fct_called_pitch`: `d_signed_in`, equal to `edge_dist_in` | mid | published `sz_top` and `sz_bot` | D-14, r = 1.45 in, radius already subtracted |

## 6. What was measured on 2026-09-25

- **Constants.** The six constants are identical in all three modules (section 1).
- **Chapter 1 follows D-14.** `top_ft` equals 0.535 × H / 12 and `bot_ft` equals 0.27 × H / 12 on every one of 1,830,267 rows. `d` recomputed from the D-14 formula matches to 2.842e-14 in. `d_abs` matches to 1.137e-13 in.
- **Chapter 2 against the Chapter 1 arm.** All 10,168 challenged pitches join on `pitch_uid`. `edge_dist_calc` equals `d_abs - 1.45` to 8.748e-9 in. The in-or-out verdict differs on 0 pitches.
- **Chapter 2 against the Chapter 1 primary.** The verdict differs on 123 of 10,168 challenged pitches.
- **Chapter 1 primary against the measured-height zone, all open called pitches.** The verdict differs on 854 of 357,105 in 2026 (0.2391%). Over P1 rows it differs on 475, 650, 687 and 785 in 2022 to 2025, 0.2187% to 0.2396%.
- **The warehouse edge column.** `edge_dist_in` is D-14 on the published `sz_top` and `sz_bot`, to 1.137e-13 in, in every season. Against the harmonised `sz_top_h` and `sz_bot_h` the verdict differs on 12,392, 12,579, 13,312 and 14,643 pitches in 2022 to 2025. It differs on 0 in 2026.

## 7. Findings

The geometry agrees everywhere: one plane, one pair of height fractions, one edge rule, one r. The height does not. Each finding below is recorded, not reconciled.

**F1. Chapter 1 and Chapter 2 use different heights in 2026.** Chapter 1's primary H is roster plus offset under D-R0-02. Chapter 2 reads Savant's zone, which is the measured height, because that is the zone ABS scores. The two give different verdicts on 123 of 10,168 challenged pitches. On those pitches the roster+offset zone agrees with the ABS verdict on 98.7707%. That is under DT-21's 99.75% bar, though the row is not gated. The zone that passed DT-21 is the measured-height zone, which is Chapter 1's robustness arm and not its primary.

**F2. The abstract does not match Chapter 1.** The SOP's Methods template says the fit uses batters with an ABS-measured height. It says the zone is rebuilt from ABS-measured height. D-R0-02 makes roster plus offset primary, so Chapter 1's primary sample is P0, 1,830,267 called pitches. The `N_CALLED` slot holds 1,492,502, the measured-height cohort in `fct_called_pitch` before W3.5's exclusions. W3.5's P1, which the SOP says `N_CALLED` reports, is 1,487,942. The 4,560-row gap is rows W3.5 excludes; 639 of them have blank coordinates.

**F3. The letter d names two quantities.** Chapter 1's `d` is the ball-centre distance on the harmonised zone, with no radius taken off. The warehouse's `d_signed_in` has the 1.45 in radius taken off, and before 2026 it sits on the operator-set zone. W3.5's `|d| <= 8.0 in` filter and 3 in shadow band are on the ball-centre `d`. W3.8's 0.5 in band is on `e`, the radius-adjusted distance. Chapter 2 reads the warehouse column on MLB 2026 challenged pitches only, where the published zone is the ABS zone. Chapter 1 reads it in one place. W3.6's 2026 shadow-band overturn count in `R/ch1/02_original_call.R` uses `|d_signed_in| <= 3`, not the ball-centre `d`. The W3.6 stat verifier flagged the same line. The abstract does not read the column.

**F4. The warehouse carries a third height.** `fct_called_pitch.batter_height_in` is the measured height where one exists and roster plus offset otherwise. `sz_top_h` and `sz_bot_h` use that mix. Neither Chapter 1 arm uses it.

**F5. The D-13 record.** D-R0-02 was decided on batter-season coverage before the DT-30 table was written. The table triggers the same branch. The answer covers all five seasons, wider than the SOP's "primary for the pre-trend". The SOP's D-13 text makes measured height the headline. `docs/DEVIATIONS.md` has no entry for that change.

## 8. Scope

W6.5 writes this page and nothing else. It adds no table, dbt model or test. The data-deliverable clauses of SOP section 9.1 (dbt model, `schema.yml`, `data_quality.csv`, a rebuild from scratch, `docs/warehouse.md`) belong to W3.4 and the warehouse steps that built the inputs. DT-30 is re-proved by the W6.5 verify command, which runs `Rscript R/ch1/03_heights.R --check`.

The verify command registered in `quality/steps.yml` runs W3.4's and W3.8's check modes. It checks the D-14 constants in all three modules. It checks every row of the tables in sections 3 and 4 against the two CSVs. A change to either CSV that is not carried here fails it.
