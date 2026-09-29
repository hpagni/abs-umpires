# Pre-registration annex: Chapter 1

This is the Chapter 1 annex to `PREREGISTRATION.md`, version 1.0. It is frozen by the `prereg-v1` tag. After the tag, any change is a logged deviation in `docs/DEVIATIONS.md`, not an edit.

Sections 1 to 7 come from SOP step W3.11, specification development. The code is `R/ch1/20_spec_dev.R`. Its diagnostics are in `out/dev/ch1_spec/`, which is not committed.

## 1. Specification development used 2022–2024 only

The Chapter 1 surface specification was developed on MLB regular-season called pitches from 2022, 2023 and 2024. No row from 2025 or 2026 entered any fit in this step. We disclose this restriction here because the development data is also the pre-trend window of the design.

The development sample is P0 (SOP W3.5) with |d| ≤ 8.0 in: 687,496 called pitches. By season: 2022 226,578; 2023 233,595; 2024 227,323. The last official date in the sample is 2024-09-30.

The script reads the analysis table once. That read filters to the three seasons inside the arrow scan, so no 2025 or 2026 row reaches the R session. The script then asserts the seasons, the last official date, the regime (`pre_buffer`) and the analysis set (`open`) before any fit runs. Every fit record in `out/dev/ch1_spec/fits/` repeats that check.

What the development saw, in full:

- Every development fit used all three seasons.
- The dry run in section 5 evaluated standardised surfaces for 2022 and 2023. No 2024 surface was evaluated.
- The CH1-A3 placebo statistic, 2023 to 2024, was not computed in this step.
- Earlier steps published 2022–2024 numbers before the tag. W3.4 wrote pooled contour areas per season to `out/tables/height_coverage.csv`. W3.5 wrote raw shadow-band called-strike rates to `out/ch1/tab/T1_sample.csv`.
- No quantity for 2025 or 2026 was estimated.

Batter height in every development fit is roster height plus the one calibration offset of DECISIONS.md D-R0-02. D-P4-04 refined that rule before the tag. Section 1.1 states the rule the primary analysis uses, and section 1.2 lists the steps that ran under the single offset. The ABS-measured cohort was fitted once, as a sensitivity row in section 7.

### 1.1 The height rule: D-R0-02, refined by D-P4-04

The primary batter height is roster height plus an offset, in every season from 2022 to 2026 (D-R0-02). DECISIONS.md D-P4-04 gives the offset one value inside the ABS-measured cohort and one outside it:

- Inside the cohort, H = roster height + 0.0022 in. This is D-R0-02's calibration: the mean of measured minus roster height over the 658 batters who carry both in 2026, SD 0.2909 in.
- Outside the cohort, H = roster height − 0.347 in (SE 0.155 in). One value serves every season.

Both offsets are added to roster height. `data/interim/dim_batter_season/calibration.json` holds them as `offset_in` and `offset_noncohort_in`, with a `convention` string that says so. `R/ch1/03_heights.R` (SOP W3.4) computes the second value, and its `--check` recomputes it from the inputs.

Why the cohort's offset cannot serve outside it. Inside the cohort, roster height is the measured height rounded to the inch, for 658 of 658 batters. D-R0-02's offset therefore measures rounding. It cannot see a listing error outside the cohort, where no measured height exists.

The estimate uses 2022–2024 only and reads no call. For each season, every batter-season with at least 200 pitches carrying `sz_top` gives its median `sz_top`, the zone top that Hawk-Eye set before ABS. One least-squares fit regresses it on height and on an indicator for batters outside the cohort. Height is measured inside the cohort and listed outside it. Listed minus true height outside the cohort is minus the indicator's coefficient over the height slope. Its SE is the coefficient's SE over the slope. The three seasons are pooled by inverse variance, and the offset is minus the pooled value. The method is the W3.4 stat verifier's (`logs/evidence/W3.4.verify-stat.log`, section G), and it reproduces the verifier's per-season values.

| season | batters outside the cohort | batters inside | listed minus true, in | SE, in | age-adjusted, in | SE, in |
|---|---:|---:|---:|---:|---:|---:|
| 2022 | 270 | 272 | 0.475 | 0.248 | 0.388 | 0.264 |
| 2023 | 204 | 335 | 0.255 | 0.269 | 0.177 | 0.291 |
| 2024 | 132 | 389 | 0.276 | 0.295 | 0.205 | 0.312 |
| pooled | 606 batter-seasons | | 0.347 | 0.155 | 0.268 | 0.166 |

The age-adjusted fit adds the batter-season mean of Statcast's `age_bat` as a third covariate. It gives an offset of −0.268 in (SE 0.166 in). It is reported and not used. D-P4-04 and the verifier's log report both estimates and choose neither, so the primary takes the fit with fewer modelling choices.

What the evidence supports, stated plainly. It is indirect: it infers height from where the zone top was set, not from a measurement. The pooled bias sits 2.2 standard errors from zero. The 606 batter-seasons are 328 batters, and the three seasons share them, so the pooled SE, which treats the seasons as independent, is too small.

The offset is one value for every season, so it cannot by itself create a difference between regimes. Its weight in a season's pooled zone scales with that season's share of called pitches from batters outside the cohort, and that share falls from 2022 to 2025. The table gives the size of the correction. For those batters the zone top moves by 53.5% and the bottom by 27% of the height change, −0.349 in, which is the non-cohort offset minus the cohort offset.

| season | called pitches | from batters outside the cohort | share | zone top shift for those batters, in | zone bottom shift, in |
|---|---:|---:|---:|---:|---:|
| 2022 | 367,145 | 149,286 | 0.4066 | -0.187 | -0.094 |
| 2023 | 374,523 | 102,459 | 0.2736 | -0.187 | -0.094 |
| 2024 | 367,017 | 64,129 | 0.1747 | -0.187 | -0.094 |
| 2025 | 368,925 | 27,693 | 0.0751 | -0.187 | -0.094 |

In 2026, 2 of 358,461 called pitches come from batters outside the cohort (DT-30). The zone moves down in feet. In the normalised coordinate zn = z × 12 / H, the same pitches move up, so a fitted contour read for a 72-inch batter moves the other way.

**Two arms beside the primary, both pre-registered.**

- The ABS-measured arm: P1, with the measured height `H_abs` (D-R0-02). The listing bias cannot reach it.
- SENS-HEIGHT-SINGLE: P0, with roster height plus D-R0-02's 0.0022 in for every batter. This is the rule as the owner first answered it. It is reported beside the primary, never in its place.

**The sign-agreement clause.** DECISIONS.md D-P4-04, part 3, verbatim:

> The ABS-measured-only robustness arm, which this bias cannot reach, must agree in sign with the primary on the buffer and ABS components. Otherwise the primary is reported as sensitive to the height cohort.

The buffer and ABS components are `Δ_buffer` and `Δ_ABS` of `PREREGISTRATION.md` section 8.

### 1.2 Steps before the tag that ran under the single offset

Every Chapter 1 step before D-P4-04 was implemented gave a batter outside the cohort roster height plus D-R0-02's one offset. The table lists each step whose input held such a batter's zn or d, and what was done. The deviation is DEV-68.

| step | input under the single offset | decision |
|---|---|---|
| W3.11, sections 1 to 7 | zn and d of 2022–2024, 687,496 rows | k.check re-run under D-P4-04, below. The rest is not re-run. |
| W3.12(c), the power curve | the design's d, 2022–2026; the link and the variance components, fitted on 2022–2024 | not re-run |
| W3.12(a), recovery | zn and d of the 2024 rows | not re-run |
| W3.12(b), SBC | the design's d | not re-run |
| MT-01's prior predictive, section 8.8 | the link and the 2022–2024 band | not re-run |
| W3.4, the selection effect in `out/tables/height_coverage.csv` | the all-batter arm, 2022–2024 | not re-run |
| W3.5, the band rows of `out/ch1/tab/T1_sample.csv`, d within 8.0 in and 3.0 in, and the raw shadow-band rates | d, 2022–2026 | not re-run |

W3.11's k.check, re-run on 2026-09-29. `Rscript R/ch1/20_spec_dev.R --check-noncohort` refits the frozen specification and the rung above it on the development sample under D-P4-04. That sample holds 687,366 rows: 2022 226,513; 2023 233,551; 2024 227,302. The same table under the single offset holds 687,485.

- Every group stays stable at the frozen k. The largest k-index change between the frozen fit and the rung above it is 0.0007, against the 0.01 rule. No k changes.
- The `te()` k-indices read 0.964 to 0.972, against 0.956 to 0.962 in section 3, each with a permutation p-value below 0.01. The reading of section 3 stands: residual structure, not a basis that is too small.
- `s(velo)` reads 0.986 with p = 0.025, against 0.996 and 0.2675. Its k-index does not move from k 10 to k 20.
- The two runs differ in more than the height rule. D-P4-08 moved 11 rows, and k.check draws its 20,000-row sub-sample from a different row set.
- The 2023-minus-2022 dry run of section 5 moves from −0.172 to −0.199 in at the top edge, and from −9.89 to −10.26 sq in in area. No acceptance criterion reads that contrast.

The comparison is in `out/dev/ch1_spec/noncohort/`, which is not committed.

Why the W3.12 simulations are not re-run. They measure the estimator's operating characteristics on simulated calls. The height rule moves the zone of a minority of batters by the amounts in section 1.1, and it does not change the estimator. The 150 recovery replicates, the SBC and the power curve take hours, and the values DECISIONS.md D-R0-04 disclosed stay as run. MT-01's margin is thin: the prior's boundary is s = 0.3013 against the 0.30 chosen. Its inputs would move under D-P4-04 and were not recomputed, so that margin stands under the single offset.

Why W3.4 and W3.5 are not re-run. The selection effect holds one height rule fixed across its two arms, which is how SOP W3.4 defines it. The W3.4 stat verifier sized a D-P4-04 correction on it (DECISIONS.md D-P4-04). The T1 rows are descriptive counts on the analysis table's d. The Chapter 1 fit code recomputes d under D-P4-04 at fit time and reports its own row counts.

Not affected, checked by reading how each is computed:

- P0 and P1. P0 filters on game type, date, call type, coordinates and the pitcher's role, never on height. P1 is P0's rows with a measured height.
- The join and the challenge counts, which read no height.
- The DT-21 zone gate. It reads measured heights, and all 10,168 challenged pitches come from batters inside the cohort. Its roster-height row, 10,043 of 10,168, therefore uses the cohort offset, which D-P4-04 leaves unchanged.
- DT-30, which counts called pitches by cohort, not by height.
- The analysis table. It stores H with D-R0-02's one offset, and the fit code moves the rows outside the cohort at fit time. No mart is rebuilt.

## 2. The frozen specification

```r
cs ~ season + count_class + stand + pitch_group
   + te(x_mid, zn, bs = c("cr","cr"), k = c(24,24))
   + te(x_mid, zn, bs = c("cr","cr"), k = c(18,18), by = season_o)
   + te(x_mid, zn, bs = c("cr","cr"), k = c(12,12), by = count_class_o)
   + te(x_mid, zn, bs = c("cr","cr"), k = c(12,12), by = stand_o)
   + s(velo, k = 10)
   + s(umpire_hp_id, bs = "re")
   + s(umpire_season, bs = "re")
```

It is fitted with `mgcv::bam(family = binomial, discrete = TRUE, method = "fREML")` under mgcv 1.9.4 and R 4.5.2. The `nthreads` argument is not set, because it does nothing on this machine (section 4).

The terms, the basis types and every k are the SOP W3.11 formula. The one change is the coding of the three by-factors.

`season_o`, `count_class_o` and `stand_o` are ordered copies of `season`, `count_class` and `stand`. The parametric terms keep the unordered factors with treatment contrasts.

The reason is identifiability. With an unordered by-factor, mgcv fits one smooth per level beside the main `te()` over the same covariates. The level smooths then sum to a second copy of the main smooth. With an ordered by-factor, mgcv fits one difference smooth for each level after the reference. The main `te()` is then the reference-level surface.

Reference levels: season 2022, count_class 0-strike, stand L. In the full fit the season factor has five levels, 2022 to 2026, and 2022 stays the reference.

The evidence, on the development sample, with the SOP k:

| coding | coefficients | edf | fit wall time | max abs difference in standardised probability |
|---|---:|---:|---:|---:|
| unordered, as the SOP writes it | 2,663 | 553.0 | 1,430 s | 0.0033 |
| ordered, frozen | 2,054 | 548.5 | 493 s | reference |

The two codings give the same surfaces to 0.0033 in probability on the 2022 and 2023 grids. The unordered fit shows the confounding in its edf. Its stand smooths split 30.0 (L) against 4.6 (R), and its count smooths 31.7, 3.0 and 15.7. The ordered fit is 2.9 times faster.

## 3. Basis dimension

The k values are the SOP values: 24 for the main `te()`, 18 for the season by-term, 12 for the count_class and stand by-terms, and 10 for `s(velo)`. They never change after the tag.

The rule was fixed in the script before any fit. k rises one rung at a time on these ladders:

- main `te()`: 24, 32, 40, 48
- season by-term: 18, 24, 30, 36
- count_class and stand by-terms, one group: 12, 16, 20, 24
- `s(velo)`: 10, 20, 30, 40

A group is stable when every one of its terms changes its k-index by less than 0.01 between two rungs, with the other groups held at the SOP k. `k.check()` runs on a seeded sub-sample of 20,000 rows with 400 permutations, so every fit is scored on the same rows.

| group | k from | k to | largest k-index change | stable |
|---|---:|---:|---:|---|
| main | 24 | 32 | 0.0003 | yes |
| season | 18 | 24 | 0.0010 | yes |
| count_class and stand | 12 | 16 | 0.0002 | yes |
| velo | 10 | 20 | 0.0000 | yes |

Every group was stable at the SOP k. A fit with every group one rung up at once (k 32, 24, 16, 20) moved no k-index by more than 0.0011.

`k.check()` on the frozen fit:

| term | k' | edf | k-index | p-value |
|---|---:|---:|---:|---:|
| `te(x_mid,zn)` | 575 | 203.9 | 0.962 | 0.0000 |
| `te(x_mid,zn):season_o2023` | 323 | 13.4 | 0.956 | 0.0000 |
| `te(x_mid,zn):season_o2024` | 323 | 18.6 | 0.962 | 0.0000 |
| `te(x_mid,zn):count_class_o1-strike` | 143 | 16.2 | 0.962 | 0.0000 |
| `te(x_mid,zn):count_class_o2-strike` | 143 | 23.3 | 0.956 | 0.0000 |
| `te(x_mid,zn):stand_oR` | 143 | 35.1 | 0.958 | 0.0000 |
| `s(velo)` | 9 | 5.6 | 0.996 | 0.2675 |
| `s(umpire_hp_id)` | 106 | 81.4 | n/a | n/a |
| `s(umpire_season)` | 280 | 142.0 | n/a | n/a |

The k-index of every `te()` term sits between 0.956 and 0.962 with a permutation p-value below 0.01. It does not move when k rises. Every edf is far below its k': 203.9 of 575 for the main surface. So the low k-index is not a basis that is too small. It is residual structure in a binary outcome that no smooth in (x_mid, zn) absorbs. It is recorded here and not chased with a larger k.

`gam.check()` on the frozen fit reports fREML convergence with every gradient component below 1e-4. Its output is `out/dev/ch1_spec/gam_check_k24-18-12-10_ord_d8.txt`.

## 4. Re-benchmark on the actual specification

Measured 2026-09-25 on the MacBook Pro M3 Pro, 18 GB. Times are for the `bam()` call. Peak memory is the process peak from `/usr/bin/time -l`. The fits ran four at a time on 11 cores.

| run | rows | coefficients | fit wall time | CPU time over wall time | peak memory |
|---|---:|---:|---:|---:|---:|
| frozen specification, 2022–2024 | 687,496 | 2,054 | 493 s | 0.99 | 2.42 GB |
| frozen specification, 80% of games | 549,897 | 2,053 | 397 s | 0.99 | 2.04 GB |
| frozen specification, ABS-measured cohort | 490,002 | 2,054 | 342 s | 0.99 | 2.63 GB |
| frozen specification, five-level scale test | 1,153,697 | 2,952 | 585 s | 0.99 | 2.62 GB |
| every k one rung up | 687,496 | 3,352 | 564 s | 0.99 | 3.93 GB |
| SOP 14.1 s formula, synthetic | 1,200,000 | 700 | 28.7 s | 1.00 | 1.45 GB |
| SOP 14.1 s formula, synthetic, vecLib at one thread | 1,200,000 | 700 | 26.0 s | 1.00 | 1.86 GB |
| SOP 8.0 s formula, synthetic | 300,000 | 700 | 17.6 s | 1.00 | 1.38 GB |

Every run was single-threaded. CPU time over wall time was between 0.99 and 1.00 in all 13 runs. R on this Mac has no OpenMP, and `bam(nthreads = 2)` warns `openMP not available: single threaded computation only`. The BLAS is Apple vecLib. Pinning it to one thread with `VECLIB_MAXIMUM_THREADS=1` changed the 1,200,000-row run from 28.7 s to 26.0 s, so vecLib added no parallel work.

The scale test resamples the 2022–2024 rows to 1,153,697, the five-season surface-sample size in `T1_sample.csv`. It carries five synthetic season labels and 530 umpire-season levels. It measures cost only and estimates nothing.

What the numbers change:

- The SOP's 14.1 s figure is for a 700-coefficient formula. It is not the cost of this specification. The frozen specification costs 493 s on 687,496 rows, not 14.1 s on 1.2 million.
- The SOP's formula re-ran at 28.7 s for 1,200,000 rows and 17.6 s for 300,000, single-threaded, under the same four-process load. The SOP's 14.1 s and 8.0 s are not reproduced at that load.
- W3.14's five-season surface on about 1.15 million rows should take about 10 minutes and 2.6 GB per fit, from the scale test.
- W3.12's injected-effect recovery fits 454,646 rows per replicate if it uses the 2024 |d| ≤ 8 in rows twice, once as 2024 and once as synthetic 2026. From the 490,002-row fit at 342 s, that is about 5 minutes per replicate and about 8 to 9 CPU hours for 100 replicates. This is an extrapolation, not a measurement.
- The 1.85 million-row framing surface uses W3.19's formula, which this step does not fit.

## 5. The secondary estimator and the pre-registered agreement tolerance

The secondary estimator is a binned logistic. Bin `d` into 0.5 in bins over [−8, +8], 32 bins. Aggregate to `cbind(strikes, balls)` per bin × season × count_class × stand × edge. Fit `glm(cbind(strikes, balls) ~ 0 + bin + season + count_class + stand, family = binomial)` separately for each edge. That is one binomial glm with every term interacted with edge.

The edge position for a season is the `d` at which the fitted probability crosses 0.5. The probability is standardised to the 2024 mix of count_class and stand. The crossing is read on the logit scale by linear interpolation between bin centres. For a 72-inch batter:

- top_in = 0.535 × 72 + d at the top edge
- bot_in = 0.27 × 72 − d at the bottom edge
- half_width_in = 8.5 + d at the side edge
- area_sqin = 2 × half_width_in × (top_in − bot_in)

The `bam` side uses the SOP W3.14 definitions: the 50% contour of the standardised surface, `top_in` and `bot_in` averaged over |x| ≤ 0.25 ft, `half_width_in` at zn = 0.4025, and area by marching squares. The binned area is a rectangle and the contour has rounded corners. So the two estimators are compared on changes between seasons, never on levels.

**Pre-registered agreement tolerance, CH1-A5.** The headline from the binned logistic falls inside the `bam` 95% interval, and the two point estimates differ by ≤0.15 in on edge shifts and ≤3 sq in on area. Wider disagreement is reported as a limitation, not silently resolved.

The comparison covers `Δ_buffer` and `Δ_ABS` for top_in, bot_in, half_width_in and area_sqin, which is eight quantities. The binned side applies the same decomposition to its own season estimates, with its own pre-trend slope `g`. The interval clause uses the 1,000 `Vc` draws of W3.15 (section 8.7).

Dry run on 2023 minus 2022. No acceptance criterion uses this contrast. It tests the point clause only.

| quantity | bam 2022 | bam 2023 | bam change | binned 2022 | binned 2023 | binned change | difference | tolerance | within |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| top_in | 40.89 | 40.72 | -0.172 | 40.42 | 40.25 | -0.170 | 0.002 | 0.15 | yes |
| bot_in | 16.65 | 16.62 | -0.031 | 17.00 | 16.96 | -0.039 | 0.008 | 0.15 | yes |
| half_width_in | 11.10 | 10.92 | -0.179 | 10.77 | 10.61 | -0.158 | 0.021 | 0.15 | yes |
| area_sqin | 492.63 | 482.75 | -9.886 | 504.49 | 494.29 | -10.192 | 0.306 | 3 | yes |

All four changes agree inside the tolerance. The levels differ by up to 11.9 sq in and 0.47 in, which is why the tolerance is stated on changes.

## 6. Baseline comparison

A game-level holdout inside 2022–2024. 1,458 of 7,288 games, drawn with a fixed seed, are held out. Every model is fitted on the other 549,897 pitches and scored on 137,523 held-out pitches. 76 held-out pitches whose umpire-season never appears in training are dropped.

| model | log loss | Brier | ECE, 10 equal-count bins |
|---|---:|---:|---:|
| league base rate | 0.6931 | 0.2500 | 0.0041 |
| ABS rulebook zone, two rates | 0.3677 | 0.1084 | 0.0044 |
| pooled surface, W3.4 form, `te(x_mid, zn)` with k = 16 | 0.2476 | 0.0771 | 0.0029 |
| binned logistic, section 5 | 0.2546 | 0.0794 | 0.0030 |
| frozen specification | 0.2380 | 0.0741 | 0.0023 |

The rulebook zone assigns one training rate inside the ABS zone (0.931) and one outside (0.171). The frozen specification has the lowest log loss, Brier score and ECE of the five.

## 7. Sensitivity

Each row is one fit on 2022–2024. The last five columns are the 2023-minus-2022 dry-run changes. "Max abs dp" is the largest difference in standardised probability from the frozen fit over the 2022 and 2023 grids, 83,076 points each.

| fit | rows | coefficients | edf | min k-index | max abs dp | top in | bot in | half-width in | area sq in |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| frozen, k 24, 18, 12, 10, ordered | 687,496 | 2,054 | 548.5 | 0.956 | 0 | -0.172 | -0.031 | -0.179 | -9.89 |
| main k 32 | 687,496 | 2,502 | 586.4 | 0.957 | 0.0138 | -0.168 | -0.031 | -0.177 | -9.88 |
| season k 24 | 687,496 | 2,558 | 549.2 | 0.956 | 0.0002 | -0.171 | -0.032 | -0.180 | -9.89 |
| count_class and stand k 16 | 687,496 | 2,390 | 554.8 | 0.956 | 0.0008 | -0.172 | -0.031 | -0.180 | -9.89 |
| velo k 20 | 687,496 | 2,064 | 549.7 | 0.956 | 0.0001 | -0.171 | -0.031 | -0.179 | -9.88 |
| every k one rung up | 687,496 | 3,352 | 594.7 | 0.957 | 0.0138 | -0.168 | -0.031 | -0.178 | -9.88 |
| unordered by-factors, as the SOP writes it | 687,496 | 2,663 | 553.0 | 0.954 | 0.0033 | -0.171 | -0.028 | -0.187 | -9.96 |
| ABS-measured cohort, height from H_abs | 490,002 | 2,054 | 502.6 | 0.959 | 0.0319 | -0.227 | -0.039 | -0.186 | -11.39 |

No k change moves an edge change by more than 0.004 in or the area change by more than 0.01 sq in. The largest probability difference from a k change, 0.0138, comes from the main k at 32. The ABS-measured cohort moves the top-edge change by 0.055 in and the area change by 1.51 sq in. That cohort is a different set of batters with a different height rule, so the gap is a cohort effect, not a basis effect.

No fitted model object from this step is saved. GD-01 fails on a fitted object under `out/` with no `provenance.json` beside it. GD-12 fails on any `provenance.json` before `prereg-v1` is pushed. `Rscript R/ch1/20_spec_dev.R --check` refits the frozen specification and the rung above it, and compares both with this file.

## 8. Umpire heterogeneity: the D-60 power curve and the CH1-A6 thresholds

Section 8 comes from SOP step W3.12(c) and decision D-60. The code is `R/ch1/21_synthetic.R`. The curve is `out/tables/ch1_power_curve.csv`. The raw draws of every seed are in `out/dev/ch1_synth/power/`, which is not committed. The curve was run before the `prereg-v1` tag and before any heterogeneity fit on real 2025 or 2026 data.

It was run twice: the first run on 2026-09-25, the second from 2026-09-25 to 2026-09-29. The second run replaces the first, for three reasons fixed before any seed of it ran. D-P4-08 moved 36 pitches out of P0, so the inputs were rebuilt: the design went from 498,059 to 498,055 pitches, and the link and calibration were refitted on 687,485 pitches instead of 687,496. The sampler settings of section 8.2 replace the SOP's, under which the first run failed MT-05. The prior of section 8.8 replaces the SOP's on `abs_step`, under which MT-01 failed for 2026. The first run's draws are kept in `out/dev/ch1_synth/first_curve_run/`. Every number in section 8 is the second run's unless it says otherwise.

### 8.1 What was simulated

The design is every real called pitch of 2022–2026 in the B1 band, |d| ≤ 3.0 in on the ball-centre d: 498,055 pitches from 114 umpires in 12,060 games. That d is under the single offset of section 1.2. Each pitch keeps its umpire, season, game, edge and d. Only the call is simulated. The script reads no call from 2025 or 2026: its design read selects no outcome column, and `--check` asserts that.

Two inputs come from 2022–2024 calls, and from nothing later:

- The link g_e(d), one per edge: `glm(cs ~ ns(d, 6), binomial)` on 687,485 pitches with |d| ≤ 8 in. The 50% point sits at d = 2.20 in (side), 1.95 in (top) and 2.42 in (bottom). The slope there is 0.99, 0.84 and 0.90 logit per inch.
- The nuisance variance components. B1 ran on the real 2022–2024 shadow-band calls, and a `brms` fit on its 825 umpire-season-edge offsets returned four posterior medians. The umpire level is 0.111 in. A persistent umpire-by-edge tendency is 0.217 in. An umpire-by-season shift common to the three edges is 0.097 in. The residual is 0.136 in.

The generating offset of umpire u in season s at edge e is the sum of those four terms, plus b_u in 2025 and 2026, plus c_u in 2026. The ABS response c_u and the buffer response b_u are each drawn with SD τ. Five seeds were run at each τ ∈ {0.10, 0.20, 0.30} in.

The same link serves all five seasons. The SOP measured 1.405 logit per inch on 2026-09-15; the 2022–2024 link is flatter. So the per-cell standard errors in the curve are, if anything, larger than 2025 and 2026 will give.

**Two shadow bands.** d is the signed distance from the ball's centre to the zone edge, negative inside, and d − 1.45 is the radius-adjusted signed edge distance of D-14. The B1 band above, |d| ≤ 3.0 in on the ball-centre d, is the band of the design, the SBC and the CH1-A6 thresholds, and W3.18's stage B1 uses it. W3.15's `shadow_rate`, and with it placebo P1, reads a different band: D-P4-09's |d − 1.45| ≤ 3.0 in, which covers ball-centre d from −1.55 to 4.45 in. D-P4-09 moved the shadow rate there. B1 stays on the band the curve was built on, because the CH1-A6 thresholds hold for the estimator the curve measured. `PREREGISTRATION.md` section 7 names both.

### 8.2 The estimator the curve measures

The whole SOP W3.18 estimator runs on each simulated league.

- B1: for each umpire-season-edge, δ maximises the binomial likelihood of y ~ g_e(d − δ) over [−4, 4] in by 0.01 in. The SE is the profile half-width where the log likelihood falls by 0.5. B2 keeps cells with at least 30 pitches whose δ is not at the grid bound.
- B2: the SOP formula and priors, with two changes made before the tag: the prior on the three `edge:abs_step` coefficients is `normal(0, 0.30)` (section 8.8), and the sampler settings are the ones below. Seed 20260922. Regime enters as two step contrasts, `buf_step` (1 in 2025 and 2026) and `abs_step` (1 in 2026). This is the SOP's `edge:regime` and `(1 + regime | umpire_hp_id)` re-coded, so the nine edge-by-regime means are unchanged. The `abs_step` slope is each umpire's 2025-to-2026 response, and its SD is τ. W3.18 uses this coding, so the thresholds below apply to the fit it runs. The re-coding is not neutral for the prior: section 8.8.
- B3: each umpire-season's plate games are split odd and even by game index, and B1 runs on each half. The per-umpire response is 2026 minus 2025, centred per edge and pooled over edges by precision. It is correlated across halves and Spearman-Brown corrected. MT-07 makes the variance-components reliability the gating value. For the response it is 1 minus the mean posterior variance of the umpire's `abs_step` over the posterior mean of τ².

**The W3.18 link, pre-registered.** SOP W3.18 says to "take the fitted link `g_{e,r}(d)` from the pooled surface". W3.18 reads that as one link per edge and regime: `glm(cs ~ ns(d, 6), binomial)` on that edge's pitches of that regime with |d| ≤ 8 in, pooled over umpires. It is the form of the calibration link of section 8.1, and the power curve and the SBC were built on that link, so the CH1-A6 thresholds apply to a B1 that uses it. The W3.14 `bam` surface does not serve as the link. It is a surface in (x_mid, zn) with umpire and count terms, and the curve never measured B1 against it. In the curve one link, fitted on 2022–2024, served every season. At W3.18 each regime has its own link, so δ is an umpire's offset from his regime's league link. B2's league steps then sit near zero, and τ, the SD of the umpires' responses, is unchanged.

The curve measures two estimators on the same simulated leagues. `sop` is B2 as above. `ue_us` adds `(1 | umpire_hp_id:edge) + (1 | umpire_hp_id:season)`, the two nuisance terms the calibration found. A rule written in the script before any `ue_us` seed ran chose which one sets CH1-A6. It is `sop` if its 95% interval for τ covers the true τ in at least 13 of 15 seeds. Failing that it is `ue_us` on the same test, and failing both, neither.

**Sampler settings, pre-registered.** SOP W3.18 writes 4 chains × 2,000 iterations: 1,000 warmup and 1,000 draws a chain, the MT-05 minimum, at CmdStan's default `adapt_delta` of 0.80. The first curve ran at exactly that. 3 of its 15 `sop` fits had divergent transitions, 6 in total, all at τ = 0.10 in. All 15 `ue_us` fits failed MT-05 on R-hat or ESS: worst R-hat 1.051, lowest bulk ESS 106.

Before any seed of the second curve ran, the failing fits were re-run on their own simulated leagues. At `adapt_delta` 0.95 the three divergent `sop` fits had none, but one fell to a bulk ESS of 383. At 0.99 none diverged. The worst of them, τ = 0.10 in seed 5, gave R-hat 1.0037 and bulk ESS 940 at 2,000 draws a chain. The six divergences had not gathered at small τ: they sat between the 6th and 98th percentile of τ's posterior, four of them in one chain. `ue_us` needed longer chains as well. At 0.99 with 2,000 warmup and 4,000 draws a chain, its three worst fits gave R-hat 1.008, 1.0067 and 1.0039 and bulk ESS 595, 699 and 908.

| estimator | chains | warmup a chain | draws a chain | `adapt_delta` | `max_treedepth` |
|---|---:|---:|---:|---:|---:|
| `sop` | 4 | 1,000 | 2,000 | 0.99 | 10 |
| `ue_us` | 4 | 2,000 | 6,000 | 0.99 | 10 |

These are the pre-registered settings for the curve, SBC and W3.18. `ue_us` keeps 6,000 draws a chain, a margin over the 4,000 at which its worst fit reached R-hat 1.008. The 2022–2024 calibration fit carries `ue_us`'s two nuisance terms and uses its settings. `R/ch1/21_synthetic.R` holds them in `STAN_SETTINGS`, and every fit records the settings it ran with.

**The MT-05 escalation, pre-registered for the curve and W3.18.** It covers a reported fit with no divergence, no tree-depth hit and E-BFMI of at least 0.2. If that fit's R-hat is above 1.01 or its ESS is below 400, it is run again from the same seed with the draws a chain doubled, at most twice. A fit with a divergence, or still short after two doublings, is reported as failed. Every attempt is recorded. SBC fits are not reported fits and never escalate. The rule was added when one fit of the second curve, `ue_us` at τ = 0.30 in seed 1, reached R-hat 1.0133 at 6,000 draws a chain. The rule was written before that fit was re-run, and it is the one W3.18 applies. Under it the fit met MT-05 after one doubling (section 8.6).

### 8.3 The curve

Five seeds per cell. "Fired" counts the seeds in which P(τ ≥ 0.20 in | data) ≥ 0.90. Reliability is the five-seed mean.

| estimator | true τ, in | fired | posterior median of τ, in | 95% interval covers τ | variance-components reliability | split-half reliability |
|---|---:|---:|---:|---:|---:|---:|
| `sop` | 0.10 | 0/5 | 0.062 | 5/5 | 0.139 | 0.658 |
| `sop` | 0.20 | 0/5 | 0.158 | 3/5 | 0.313 | 0.763 |
| `sop` | 0.30 | 4/5 | 0.288 | 5/5 | 0.494 | 0.859 |
| `ue_us` | 0.10 | 0/5 | 0.076 | 5/5 | 0.147 | 0.658 |
| `ue_us` | 0.20 | 0/5 | 0.188 | 5/5 | 0.374 | 0.763 |
| `ue_us` | 0.30 | 5/5 | 0.296 | 5/5 | 0.512 | 0.859 |

The table is the second run, which `out/tables/ch1_power_curve.csv` holds. `sop` covered the true τ in 13 of 15 seeds and `ue_us` in 15 of 15. By the rule in section 8.2, `sop` sets CH1-A6. `ue_us` is a pre-registered sensitivity row.

### 8.4 How the curve becomes thresholds

The script fixes the rule. Write F_c(t) for the number of seeds, of five, at true τ = t in which P(τ ≥ c | data) ≥ 0.90.

1. The materiality threshold c* is the smallest c in {0.20, 0.25, 0.30} in with F_c(0.10) ≤ 1. `sop` gives F_0.20 = 0, 0, 4 at τ = 0.10, 0.20, 0.30 in, so c* = 0.20 in.
2. The materiality claim is powered when F_c*(0.30) ≥ 4. It is: 4 of 5.
3. The reliability gate is the variance-components reliability of the per-umpire response, as MT-07 requires, at the 0.50 floor D-60 names. It is attainable when some grid τ where the rule is powered reaches 0.50. `sop` reaches 0.494 at τ = 0.30 in. The gate is not attainable, so no per-umpire table is published.
4. When the rule does not fire, the bounded null is the reportable result. The `sop` one-sided 95% upper bound fell below the true τ in 2 of 5 seeds at τ = 0.20 in. So the bound is the larger of the `sop` and `ue_us` bounds.

One step of this rule was revised after the `sop` curve and before any `ue_us` seed. The first version gated the table on split-half alone, at the `sop` split-half for τ = 0.20 in, 0.76. The first curve showed a split-half of 0.690 at τ = 0.10 in, above the 0.50 floor at half the materiality threshold. Split-half counts each umpire's season-specific shift as signal, and the shrunken per-umpire response does not. MT-07 names the variance-components value as the gate, so step 3 now uses it.

### 8.5 CH1-A6 as pre-registered

| CH1-A6 item | pre-registered value |
|---|---|
| estimator that sets the thresholds | `sop`: SOP W3.18 B2, with the `abs_step` prior `normal(0, 0.30)` of section 8.8 |
| materiality rule | material only if P(τ ≥ 0.20 in) ≥ 0.90 |
| firing rate of the rule at τ = 0.10 / 0.20 / 0.30 in | 0/5, 0/5, 4/5 |
| 95% interval for τ covers the true τ, at τ = 0.10 / 0.20 / 0.30 in | 5/5, 3/5, 5/5 |
| one-sided 95% upper bound at or above the true τ, at τ = 0.10 / 0.20 / 0.30 in | 5/5, 3/5, 5/5 |
| powered for the materiality claim | yes: 4 of 5 seeds fire at τ = 0.30 in, 0 of 5 at τ = 0.10 in |
| variance-components reliability of the response at τ = 0.10 / 0.20 / 0.30 in | 0.139 / 0.313 / 0.494 |
| split-half reliability of the response at τ = 0.10 / 0.20 / 0.30 in | 0.658 / 0.763 / 0.859 |
| reliability gate attainable | no |
| per-umpire table | no per-umpire table: the curve does not reach a variance-components reliability of 0.50 at any τ where the rule is powered |
| reportable result when the rule does not fire | bounded null: the posterior median of τ and the larger of the one-sided 95% upper bounds from `sop` and `ue_us`, because the `sop` bound fell below the true τ in 2 of 15 seeds; the curve's mean 95% upper bound is 0.130 / 0.225 / 0.356 in at τ = 0.10 / 0.20 / 0.30 in |
| bounded null is the primary reportable result | no |

Stated in words: τ is reported with its 95% interval. "Material" is declared only if P(τ ≥ 0.20 in | data) ≥ 0.90 in the `sop` fit. The study is powered for τ = 0.30 in, 4 of 5 seeds, and not for τ = 0.20 in, 0 of 5. If the rule does not fire, the reportable result is the bounded null in the table above, as D-42 does for Chapter 3. No per-umpire table is published, under D-21, whatever the fit returns. The split-half and variance-components reliability are reported side by side, with their difference as a number.

### 8.6 What the curve changes

- The SOP's analytic sketch put the reliability of the per-umpire response near 0.8 at τ = 0.25 in. The simulated split-half agrees: 0.763 at τ = 0.20 in and 0.859 at τ = 0.30 in. The variance-components reliability is 0.313 and 0.494.
- The two differ because the calibration found an umpire-by-season shift of 0.097 in, common to the three edges. A split half shares it; the umpire's true ABS response does not include it.
- The squared correlation between each umpire's shrunken `sop` response and his true response is 0.318 at τ = 0.20 in and 0.519 at τ = 0.30 in. A named table would rank umpires mostly on noise at τ = 0.20 in.
- `sop` puts τ low: a mean posterior median of 0.158 in at a true 0.20 in, where `ue_us` gives 0.188 in. The likely cause is the persistent umpire-by-edge tendency of 0.217 in, which `sop` leaves to its residual SD.
- MT-05 on the 30 fits. In the first run, 3 of 15 `sop` fits had divergent transitions, 6 in total, all at τ = 0.10 in. All 15 `ue_us` fits failed on R-hat or ESS, the worst at R-hat 1.051 and bulk ESS 106. At the settings of section 8.2 none of the 30 fits diverges, and all 30 meet MT-05. Every `sop` fit meets it at once: worst R-hat 1.0072, lowest bulk ESS 982, lowest tail ESS 1,313. 14 of the 15 `ue_us` fits meet it at 6,000 draws a chain. The fifteenth, τ = 0.30 in seed 1, reached R-hat 1.0133 and bulk ESS 572 there, so the escalation rule doubled its draws. That re-run was lost when the Mac hibernated from 2026-09-26 to 2026-09-29. It ran again on 2026-09-29, from the same seed at 12,000 draws a chain, and met MT-05. It had no divergence and no tree-depth hit, lowest E-BFMI 0.593, R-hat 1.0066, bulk ESS 1,106 and tail ESS 2,644. Over the 15 `ue_us` fits the worst R-hat is 1.0082, the lowest bulk ESS 897 and the lowest tail ESS 1,074. The re-run left the `ue_us` rows of section 8.3 unchanged. Nothing on this point is deferred to W3.18 (DECISIONS.md D-P4-35, DEV-64).
- The 2022–2024 calibration fit, at `ue_us`'s settings, reached R-hat 1.0059 and bulk ESS 1,670; in the first run, R-hat 1.021 and bulk ESS 384. It sets simulation inputs only and is not a reported estimate.

### 8.7 Injected-effect recovery and SBC, SOP W3.12(a) and (b)

Recovery. The 2024 called pitches with |d| ≤ 8 in, 227,323 rows, are used twice: as 2024 and as synthetic 2026. A generating surface is fitted once on the real 2024 calls. Both copies then get new calls from it. The 2026 copy uses the surface with the zone deformed: top down 0.60 in, bottom up 0.30 in, half-width in 0.10 in. The truth, read off the generating surfaces with the W3.14 estimand code, is −0.599, +0.299 and −0.103 in. Each replicate fits the frozen specification on 454,646 rows, and its 95% and 90% intervals come from 1,000 draws from N(β, Vc), where Vc is `mgcv`'s covariance corrected for smoothing-parameter uncertainty. A null replicate draws both copies from the undeformed surface.

Pre-registered acceptance, SOP W3.12(a), CH1-A7 and MT-03/MT-04:

- over 100 injected replicates, each shift's mean error lies within ±0.10 in;
- each shift's 95% interval covers the truth in at least 93 of 100;
- over 50 null replicates, each shift's 95% interval excludes zero in at most 7%;
- CH1-A7's equivalence form: in at least 93% of the null replicates, each shift's 90% interval lies inside ±0.10 in.

One replicate of each kind ran as a pilot, before the 90% interval was added to the output. The pilot's injected estimates are −0.620, +0.309 and −0.096 in, its null estimates are −0.012, −0.006 and +0.009 in, and all six intervals cover the truth. A replicate costs about 5 minutes, 230–250 s of it for the fit.

**The interval method, changed before the tag.** The first full run, on 2026-09-25, drew each replicate's intervals from N(β, Vp). Vp treats the estimated smoothing parameters as known. That run failed four of the twelve clauses above. The top edge's 95% interval covered the truth in 91 of 100 replicates. The null 95% interval excluded zero for the bottom edge in 4 of 50 and for the half-width in 6 of 50. The top edge's null 90% interval lay inside ±0.10 in in 45 of 50. The half-width's null sampling SD was 1.30 times its posterior SD, with a 95% interval of 1.09 to 1.62.

The intervals now come from Vc, `mgcv`'s covariance corrected for smoothing-parameter uncertainty (Wood, Pya and Säfken, 2016). The SOP's fitter exposes it. `bam(discrete = TRUE, method = "fREML")` returns Vc = Vp + J V_ρ Jᵀ, where J is the derivative of the coefficients with respect to the log smoothing parameters and V_ρ is the inverse Hessian of the fREML criterion. It leaves out the second-order term that `gam(method = "REML")` adds. So no parametric bootstrap was needed. W3.15's 1,000 draws use the same Vc. The 150 replicates were run again with the same seeds and the same fits. All 150 point estimates equal the Vp run's, so only the intervals differ. No bound was changed.

**The result under Vc.** The run finished on 2026-09-29. The truth is −0.5991 in at the top (injected −0.60), +0.2989 in at the bottom (+0.30) and −0.1027 in for the half-width (−0.10). Over the 100 injected replicates the mean error is +0.0155, −0.0064 and +0.0089 in. The mean absolute error is 0.0329, 0.0212 and 0.0173 in. The table holds every clause `tests/model/test_mt_ch1_03_recovery.py` asserts, recounted from the per-replicate files.

| clause | quantity | measured | bound | result |
|---|---|---:|---|---|
| CH1-A7: mean error, injected | top | +0.0155 in | within ±0.10 in | met |
| CH1-A7: mean error, injected | bottom | −0.0064 in | within ±0.10 in | met |
| CH1-A7: mean error, injected | half-width | +0.0089 in | within ±0.10 in | met |
| CH1-A7: 95% interval covers the truth, injected | top | 91 of 100 | at least 93 of 100 | **not met** |
| CH1-A7: 95% interval covers the truth, injected | bottom | 98 of 100 | at least 93 of 100 | met |
| CH1-A7: 95% interval covers the truth, injected | half-width | 97 of 100 | at least 93 of 100 | met |
| CH1-A7: null 95% interval excludes zero | top | 3 of 50, 6% | at most 7% | met |
| CH1-A7: null 95% interval excludes zero | bottom | 3 of 50, 6% | at most 7% | met |
| CH1-A7: null 95% interval excludes zero | half-width | 3 of 50, 6% | at most 7% | met |
| CH1-A7: null 90% interval inside ±0.10 in | top | 44 of 50, 88% | at least 93%, 47 of 50 | **not met** |
| CH1-A7: null 90% interval inside ±0.10 in | bottom | 50 of 50 | at least 93%, 47 of 50 | met |
| CH1-A7: null 90% interval inside ±0.10 in | half-width | 50 of 50 | at least 93%, 47 of 50 | met |
| MT-03: 95% coverage, injected | top | 0.91 | in [0.80, 0.98] | met |
| MT-03: 95% coverage, injected | bottom | 0.98 | in [0.80, 0.98] | met |
| MT-03: 95% coverage, injected | half-width | 0.97 | in [0.80, 0.98] | met |
| MT-03: mean absolute error, injected | top | 0.0329 in | at most 0.15 in | met |
| MT-03: mean absolute error, injected | bottom | 0.0212 in | at most 0.15 in | met |
| MT-03: mean absolute error, injected | half-width | 0.0173 in | at most 0.15 in | met |
| MT-03: mean absolute error of τ, 15 `sop` seeds of section 8.3 | τ | 0.0364 in | at most 0.10 in | met |
| MT-04: the rule fires, null | top | 3 of 50 | at most 5 of 50 | met |
| MT-04: the rule fires, null | bottom | 3 of 50 | at most 5 of 50 | met |
| MT-04: the rule fires, null | half-width | 3 of 50 | at most 5 of 50 | met |
| MT-04: null 90% interval covers zero | top | 45 of 50 | at least 43 of 50 | met |
| MT-04: null 90% interval covers zero | bottom | 46 of 50 | at least 43 of 50 | met |
| MT-04: null 90% interval covers zero | half-width | 42 of 50 | at least 43 of 50 | **not met** |
| power: 95% interval excludes zero, injected | top, bottom, half-width | 100, 100, 100 of 100 | 100 of 100 | met |

The rule that fires under MT-04 is the zero-effect rule, a 95% interval that excludes zero. 10 of the 12 CH1-A7 clauses are met, and 12 of the 13 MT-03 and MT-04 clauses. The owner's answer on the three not met is DECISIONS.md D-R0-04: disclose all three and tag, with the bounds and the method as written (DEV-67).

**What is not met, and what follows.**

- The top edge's 95% interval covers the truth in 91 of 100. The estimate is biased 0.0155 in toward zero, consistent with a penalised smooth shrinking an abrupt shift. Vc corrects the variance and cannot remove a bias. The estimates' SD, 0.0384 in, is close to the mean posterior SD, 0.0421 in. A one-sided exact binomial test gives P(X ≤ 91 | n = 100, p = 0.95) = 0.0631, and a calibrated method falls below 93 with probability 0.1280. The clause is not met regardless. Consequence: every Chapter 1 top-edge interval is read as slightly too narrow, and every top-edge statement carries that caveat.
- The top edge's null 90% interval lies inside ±0.10 in in 44 of 50. The cause is width, a precision limit: the null SD of the top-edge estimate is 0.0309 in. Consequence: a top-edge equivalence result from the primary fit is read knowing that the design returns "equivalent" for a true zero in 88% of replicates, short of the 93% asked for. The study is underpowered to declare no change at the top edge. The equivalence test stays in the analysis as written.
- The half-width's null 90% interval covers zero in 42 of 50, one replicate below its bound. The same quantity's null 95% interval covers zero in 47 of 50, and its null 95% interval excludes zero in 3 of 50. P(X ≤ 42 | n = 50, p = 0.90) = 0.1221. Consequence: the half-width's 90% interval is reported with that shortfall stated beside it.

**SENS-B1-UNDERSMOOTH, pre-registered.** W3.14 refits the surfaces with the season by-term at k = 24 instead of 18. Every other k stays at section 3's values. It reports the top-edge estimate and interval beside the primary's. The season by-term carries the shift between seasons, and in the recovery fit it carries the whole injected deformation. 24 is the next rung on section 3's season ladder, where 18 to 24 was stable, largest k-index change 0.0010. On 2022–2024 that rung moved the 2023-minus-2022 top-edge change by 0.001 in (section 7). A larger basis is expected to trade bias for width. So the arm cannot rescue the equivalence clause, and it is reported beside the primary, never in place of it. The primary analysis is unchanged.

SBC. Parameters are drawn from the B2 prior and δ is drawn from the B2 likelihood at the real design: 1,367 umpire-season-edge cells, each with its analytic SE at its real pitch locations. B2 is refitted, and the rank of each true value among 199 thinned draws is binned into 10 bins. Pre-registered acceptance, CH1-A8 and MT-02, over 200 replicates:

- a chi-square uniformity test at α = 0.05 passes for τ and for the regime mean, the mean of the three edge `abs_step` coefficients;
- the worst Benjamini-Hochberg-adjusted p across ten tracked quantities exceeds 0.01;
- no quantity leaves the 95% simultaneous ECDF band.

The 200 replicates ran on 2026-09-25 for `sop`, the estimator that sets CH1-A6. The chi-square p is 0.770 for τ and 0.993 for the regime mean. The worst Benjamini-Hochberg-adjusted p is 0.441, for the residual SD. All ten quantities stay inside the ECDF band. 25 of the 200 fits had divergent transitions, 58 in total. That run used the SOP's `normal(0, 1)` on `abs_step` and the first curve's sampler settings.

The SBC at the prior of section 8.8 and the settings of section 8.2 started on 2026-09-26. The hibernation stopped it with 37 of the 200 replicates on disk, and it finished on 2026-09-29 (DECISIONS.md D-P4-36, DEV-65). Over all 200 replicates, the chi-square p is 0.8906 for τ and 0.7695 for the regime mean. Across the ten quantities it runs from 0.1538, for the residual SD, to 0.8906. The worst Benjamini-Hochberg-adjusted p is 0.8130. All ten quantities stay inside the 95% simultaneous ECDF band. None of the 200 fits had a divergent transition. CH1-A8 is met, and so are MT-02's clauses at L = 200. MT-02's L = 1,000 run is due by 2026-12-04.

### 8.8 The prior on the 2025-to-2026 league step, and MT-01

MT-01 requires B2's prior to put the implied shadow-zone called-strike rate in [0.10, 0.90] in at least 95% of draws. `tests/model/test_mt_ch1_01_prior_predictive.py` reads it at the league level. A draw's rate is the mean of the 2022–2024 link g_e(d − δ) over each edge's 2022–2024 shadow-band pitches, where δ is the edge's league offset in the regime. The three edges are pooled by their pitch counts. No 2025 or 2026 row is read. The share is computed exactly: the rate rises with each edge's offset, so the bottom edge's offset is integrated in closed form and the other two by Gauss-Hermite quadrature. The 20,000-draw Monte Carlo the test used first is kept as a cross-check.

The link puts the 50% point 1.9 to 2.4 in outside the rulebook edge, so at δ = 0 the pooled rate is already high, and a wide offset pushes it past 0.90. With the step coding of section 8.2, the 2026 league offset of an edge is b + b_buf + b_abs. Under the SOP's `normal(0, 1)` on every b, its prior is N(0, 1.73 in). Under the SOP's own treatment coding it would be b + b_2026, N(0, 1.41 in). So the re-coding, not the SOP, widened the 2026 prior. The exact shares under the SOP prior:

| regime | league-offset prior | share of the prior inside [0.10, 0.90] |
|---|---|---:|
| pre-buffer, 2022–2024 | N(0, 1.00 in) | 0.9852 |
| buffer, 2025 | N(0, 1.41 in) | 0.9525 |
| ABS, 2026 | N(0, 1.73 in) | 0.9288 |

The derivation, written before any fit used it. Only `abs_step` enters 2026 alone, so the change is confined to its prior: `normal(0, s)` on the three `edge:abs_step` coefficients, which gives the 2026 offset N(0, sqrt(2 + s²)). The pre-buffer and 2025 shares do not move. s is the largest multiple of 0.05 in at which all three regimes clear 0.95. The 2026 share is 0.95079 at s = 0.25, 0.95002 at s = 0.30 and 0.94913 at s = 0.35; the boundary is s = 0.3013. So s = 0.30, and the 2026 league offset's prior is N(0, 1.45 in). Changing the quadrature from 100 to 300 nodes moves the share at 0.30 by at most 0.00002, and it stays above 0.95.

The prior is on a league-level step that W3.18 estimates from about 110 umpires. Its posterior SD there is a few hundredths of an inch, so a prior SD of 0.30 in costs the estimate almost nothing. It matters for the prior predictive, which is what MT-01 checks.

The SOP's `normal(0, 1)` on `abs_step` is the pre-registered sensitivity arm SENS-B2-ABS-PRIOR. W3.18 fits B2 under both priors and reports both. The power curve, SBC and CH1-A6 use `normal(0, 0.30)`. The SD clause of MT-01 is unaffected: P(τ < 3.0 in) is 1 − e⁻⁶ = 0.9975 under B2's `exponential(2)`.
