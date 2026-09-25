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

Batter height is roster height plus the calibration offset, the primary cohort under DECISIONS.md D-R0-02. The ABS-measured cohort was fitted once, as a sensitivity row in section 7.

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

The comparison covers `Δ_buffer` and `Δ_ABS` for top_in, bot_in, half_width_in and area_sqin, which is eight quantities. The binned side applies the same decomposition to its own season estimates, with its own pre-trend slope `g`. The interval clause uses the 1,000 `Vp` draws of W3.15.

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

Section 8 comes from SOP step W3.12(c) and decision D-60. The code is `R/ch1/21_synthetic.R`. The curve is `out/tables/ch1_power_curve.csv`. The raw draws of every seed are in `out/dev/ch1_synth/power/`, which is not committed. The curve was run on 2026-09-25, before the `prereg-v1` tag and before any heterogeneity fit on real 2025 or 2026 data.

### 8.1 What was simulated

The design is every real called pitch of 2022–2026 in the shadow band, |d| ≤ 3.0 in: 498,059 pitches from 114 umpires in 12,060 games. Each pitch keeps its umpire, season, game, edge and d. Only the call is simulated. The script reads no call from 2025 or 2026: its design read selects no outcome column, and `--check` asserts that.

Two inputs come from 2022–2024 calls, and from nothing later:

- The link g_e(d), one per edge: `glm(cs ~ ns(d, 6), binomial)` on 687,496 pitches with |d| ≤ 8 in. The 50% point sits at d = 2.20 in (side), 1.95 in (top) and 2.42 in (bottom). The slope there is 0.99, 0.84 and 0.91 logit per inch.
- The nuisance variance components. B1 ran on the real 2022–2024 shadow-band calls, and a `brms` fit on its 825 umpire-season-edge offsets returned four posterior medians. The umpire level is 0.111 in. A persistent umpire-by-edge tendency is 0.217 in. An umpire-by-season shift common to the three edges is 0.097 in. The residual is 0.136 in.

The generating offset of umpire u in season s at edge e is the sum of those four terms, plus b_u in 2025 and 2026, plus c_u in 2026. The ABS response c_u and the buffer response b_u are each drawn with SD τ. Five seeds were run at each τ ∈ {0.10, 0.20, 0.30} in.

The same link serves all five seasons. The SOP measured 1.405 logit per inch on 2026-09-15; the 2022–2024 link is flatter. So the per-cell standard errors in the curve are, if anything, larger than 2025 and 2026 will give.

### 8.2 The estimator the curve measures

The whole SOP W3.18 estimator runs on each simulated league.

- B1: for each umpire-season-edge, δ maximises the binomial likelihood of y ~ g_e(d − δ) over [−4, 4] in by 0.01 in. The SE is the profile half-width where the log likelihood falls by 0.5. B2 keeps cells with at least 30 pitches whose δ is not at the grid bound.
- B2: the SOP formula and priors, 4 chains × 2,000 iterations, seed 20260922. Regime enters as two step contrasts, `buf_step` (1 in 2025 and 2026) and `abs_step` (1 in 2026). This is the SOP's `edge:regime` and `(1 + regime | umpire_hp_id)` re-coded, so the nine edge-by-regime means are unchanged. The `abs_step` slope is each umpire's 2025-to-2026 response, and its SD is τ. W3.18 uses this coding, so the thresholds below apply to the fit it runs.
- B3: each umpire-season's plate games are split odd and even by game index, and B1 runs on each half. The per-umpire response is 2026 minus 2025, centred per edge and pooled over edges by precision. It is correlated across halves and Spearman-Brown corrected. MT-07 makes the variance-components reliability the gating value. For the response it is 1 minus the mean posterior variance of the umpire's `abs_step` over the posterior mean of τ².

The curve measures two estimators on the same simulated leagues. `sop` is B2 as the SOP writes it. `ue_us` adds `(1 | umpire_hp_id:edge) + (1 | umpire_hp_id:season)`, the two nuisance terms the calibration found. A rule written in the script before any `ue_us` seed ran chose which one sets CH1-A6. It is `sop` if its 95% interval for τ covers the true τ in at least 13 of 15 seeds. Failing that it is `ue_us` on the same test, and failing both, neither.

### 8.3 The curve

Five seeds per cell. "Fired" counts the seeds in which P(τ ≥ 0.20 in | data) ≥ 0.90. Reliability is the five-seed mean.

| estimator | true τ, in | fired | posterior median of τ, in | 95% interval covers τ | variance-components reliability | split-half reliability |
|---|---:|---:|---:|---:|---:|---:|
| `sop` | 0.10 | 0/5 | 0.060 | 5/5 | 0.147 | 0.690 |
| `sop` | 0.20 | 0/5 | 0.153 | 4/5 | 0.307 | 0.768 |
| `sop` | 0.30 | 4/5 | 0.283 | 5/5 | 0.479 | 0.861 |
| `ue_us` | 0.10 | 0/5 | 0.068 | 5/5 | 0.141 | 0.690 |
| `ue_us` | 0.20 | 1/5 | 0.191 | 5/5 | 0.376 | 0.768 |
| `ue_us` | 0.30 | 5/5 | 0.292 | 5/5 | 0.501 | 0.861 |

`sop` covered the true τ in 14 of 15 seeds and `ue_us` in 15 of 15. By the rule in section 8.2, `sop` sets CH1-A6. `ue_us` is a pre-registered sensitivity row.

### 8.4 How the curve becomes thresholds

The script fixes the rule. Write F_c(t) for the number of seeds, of five, at true τ = t in which P(τ ≥ c | data) ≥ 0.90.

1. The materiality threshold c* is the smallest c in {0.20, 0.25, 0.30} in with F_c(0.10) ≤ 1. `sop` gives F_0.20 = 0, 0, 4 at τ = 0.10, 0.20, 0.30 in, so c* = 0.20 in.
2. The materiality claim is powered when F_c*(0.30) ≥ 4. It is: 4 of 5.
3. The reliability gate is the variance-components reliability of the per-umpire response, as MT-07 requires, at the 0.50 floor D-60 names. It is attainable when some grid τ where the rule is powered reaches 0.50. `sop` reaches 0.479 at τ = 0.30 in. The gate is not attainable, so no per-umpire table is published.
4. When the rule does not fire, the bounded null is the reportable result. The `sop` one-sided 95% upper bound fell below the true τ in 2 of 5 seeds at τ = 0.20 in and 1 of 5 at τ = 0.30 in. So the bound is the larger of the `sop` and `ue_us` bounds.

One step of this rule was revised after the `sop` curve and before any `ue_us` seed. The first version gated the table on split-half alone, at the `sop` split-half for τ = 0.20 in, 0.76. The curve showed a split-half of 0.690 at τ = 0.10 in, above the 0.50 floor at half the materiality threshold. Split-half counts each umpire's season-specific shift as signal, and the shrunken per-umpire response does not. MT-07 names the variance-components value as the gate, so step 3 now uses it.

### 8.5 CH1-A6 as pre-registered

| CH1-A6 item | pre-registered value |
|---|---|
| estimator that sets the thresholds | `sop`: SOP W3.18 B2 as written |
| materiality rule | material only if P(τ ≥ 0.20 in) ≥ 0.90 |
| firing rate of the rule at τ = 0.10 / 0.20 / 0.30 in | 0/5, 0/5, 4/5 |
| 95% interval for τ covers the true τ, at τ = 0.10 / 0.20 / 0.30 in | 5/5, 4/5, 5/5 |
| one-sided 95% upper bound at or above the true τ, at τ = 0.10 / 0.20 / 0.30 in | 5/5, 3/5, 4/5 |
| powered for the materiality claim | yes: 4 of 5 seeds fire at τ = 0.30 in, 0 of 5 at τ = 0.10 in |
| variance-components reliability of the response at τ = 0.10 / 0.20 / 0.30 in | 0.147 / 0.307 / 0.479 |
| split-half reliability of the response at τ = 0.10 / 0.20 / 0.30 in | 0.690 / 0.768 / 0.861 |
| reliability gate attainable | no |
| per-umpire table | no per-umpire table: the curve does not reach a variance-components reliability of 0.50 at any τ where the rule is powered |
| reportable result when the rule does not fire | bounded null: the posterior median of τ and the larger of the one-sided 95% upper bounds from `sop` and `ue_us`, because the `sop` bound fell below the true τ in 3 of 15 seeds; the curve's mean 95% upper bound is 0.124 / 0.223 / 0.350 in at τ = 0.10 / 0.20 / 0.30 in |
| bounded null is the primary reportable result | no |

Stated in words: τ is reported with its 95% interval. "Material" is declared only if P(τ ≥ 0.20 in | data) ≥ 0.90 in the `sop` fit. The study is powered for τ = 0.30 in, 4 of 5 seeds, and not for τ = 0.20 in, 0 of 5. If the rule does not fire, the reportable result is the bounded null in the table above, as D-42 does for Chapter 3. No per-umpire table is published, under D-21, whatever the fit returns. The split-half and variance-components reliability are reported side by side, with their difference as a number.

### 8.6 What the curve changes

- The SOP's analytic sketch put the reliability of the per-umpire response near 0.8 at τ = 0.25 in. The simulated split-half agrees: 0.768 at τ = 0.20 in and 0.861 at τ = 0.30 in. The variance-components reliability is 0.307 and 0.479.
- The two differ because the calibration found an umpire-by-season shift of 0.097 in, common to the three edges. A split half shares it; the umpire's true ABS response does not include it.
- The squared correlation between each umpire's shrunken `sop` response and his true response is 0.286 at τ = 0.20 in and 0.536 at τ = 0.30 in. A named table would rank umpires mostly on noise at τ = 0.20 in.
- `sop` puts τ low: a mean posterior median of 0.153 in at a true 0.20 in, where `ue_us` gives 0.191 in. The likely cause is the persistent umpire-by-edge tendency of 0.217 in, which `sop` leaves to its residual SD.
- `ue_us` did not converge at 4 chains × 2,000 iterations: R-hat up to 1.051 and bulk ESS down to 106 at τ = 0.30 in. W3.18 runs it longer until MT-05 holds, or reports it as failed.
- 3 of 15 `sop` fits had divergent transitions, 6 in total, all at τ = 0.10 in. MT-05 allows none on a reported fit. W3.18 reparameterises or reports the fit as failed, as MT-05 says.
- The 2022–2024 calibration fit reached R-hat 1.021 and bulk ESS 384. It sets simulation inputs only and is not a reported estimate.

### 8.7 Injected-effect recovery and SBC, SOP W3.12(a) and (b)

Recovery. The 2024 called pitches with |d| ≤ 8 in, 227,323 rows, are used twice: as 2024 and as synthetic 2026. A generating surface is fitted once on the real 2024 calls. Both copies then get new calls from it. The 2026 copy uses the surface with the zone deformed: top down 0.60 in, bottom up 0.30 in, half-width in 0.10 in. The truth, read off the generating surfaces with the W3.14 estimand code, is −0.599, +0.299 and −0.103 in. Each replicate fits the frozen specification on 454,646 rows, and its 95% intervals come from 1,000 draws from N(β, Vp). A null replicate draws both copies from the undeformed surface.

Pre-registered acceptance, SOP W3.12(a), CH1-A7 and MT-03/MT-04:

- over 100 injected replicates, each shift's mean error lies within ±0.10 in;
- each shift's 95% interval covers the truth in at least 93 of 100;
- over 50 null replicates, each shift's 95% interval excludes zero in at most 7%;
- CH1-A7's equivalence form: in at least 93% of the null replicates, each shift's 90% interval lies inside ±0.10 in.

One replicate of each kind ran as a pilot, before the 90% interval was added to the output. The pilot's injected estimates are −0.620, +0.309 and −0.096 in, its null estimates are −0.012, −0.006 and +0.009 in, and all six intervals cover the truth. A replicate costs about 5 minutes, 230–250 s of it for the fit. The full set started on 2026-09-25 and runs past the tag. Its results go to `out/dev/ch1_synth/recovery/` and the W3.12 receipt, not into this annex.

SBC. Parameters are drawn from the B2 prior and δ is drawn from the B2 likelihood at the real design: 1,367 umpire-season-edge cells, each with its analytic SE at its real pitch locations. B2 is refitted, and the rank of each true value among 199 thinned draws is binned into 10 bins. Pre-registered acceptance, CH1-A8 and MT-02, over 200 replicates:

- a chi-square uniformity test at α = 0.05 passes for τ and for the regime mean, the mean of the three edge `abs_step` coefficients;
- the worst Benjamini-Hochberg-adjusted p across ten tracked quantities exceeds 0.01;
- no quantity leaves the 95% simultaneous ECDF band.

The 200 replicates ran on 2026-09-25 for `sop`, the estimator that sets CH1-A6. The chi-square p is 0.770 for τ and 0.993 for the regime mean. The worst Benjamini-Hochberg-adjusted p is 0.441, for the residual SD. All ten quantities stay inside the ECDF band. 25 of the 200 fits had divergent transitions, 58 in total.
