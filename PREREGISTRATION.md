---
title: "Umpires under ABS: pre-registration"
version: 1.0
tag: prereg-v1
annexes: docs/prereg/ch1.md, docs/prereg/ch2.md, docs/prereg/ch3.md, docs/prereg/p8.md
lock: quality/prereg.lock
---

# Umpires under ABS: pre-registration

Version 1.0. This is the root document of the project's pre-registration. The annotated git tag `prereg-v1` freezes it, and the tag message carries the freeze time in Europe/Madrid.

One root document and four annexes make up the plan. `quality/prereg.lock` holds the sha256 of this file and of every `docs/prereg/*.md` file, read from the tagged blobs.

| part | file | written by | frozen by |
|---|---|---|---|
| design, sealed set, every acceptance criterion | `PREREGISTRATION.md` | SOP step W7.6 | `prereg-v1` |
| Chapter 1 annex: specification development, the agreement tolerance, the curve-set thresholds | `docs/prereg/ch1.md` | SOP steps W3.11 and W3.12 | `prereg-v1` |
| Chapter 2 annex: M1, M2 and CH2-H2a to CH2-H2e | `docs/prereg/ch2.md` | SOP step W4.1 | `prereg-v1` |
| Chapter 3 annex: the two-sided token dynamic program, CH3-A1 to CH3-A8 | `docs/prereg/ch3.md` | SOP step W7.6, from SOP W5 | `prereg-v1` |
| Phase 2 annex: P8-A1 to P8-A6 and the P8 rules already fixed | `docs/prereg/p8.md` | SOP step W7.6, from SOP W8 | `prereg-v1`, then `p8-prereg-v1` |
| seal log | `docs/prereg/SEAL.md` | SOP step W2.4 | append-only |
| release notes | `docs/prereg/RELEASE_NOTES.md` | SOP step W7.6 | `prereg-v1` |

Data: MLB Advanced Media and Baseball Savant.

## 1. Change control

- After the tag, a change to any file above is a dated entry in `docs/DEVIATIONS.md`. It is never an edit. The one exception is the seal log, which gains one line per seal event.
- A later version of the plan is a new document under the tag `prereg-v2`.
- `absump.seal._prereg_hash_matches()` re-hashes each file named in `quality/prereg.lock` from `git show prereg-v1:<path>`. An edit made after the tag cannot satisfy it.
- P8 has its own seal and its own later tag, `p8-prereg-v1`. SOP step W8.1 extends `docs/prereg/p8.md` under a new heading before that tag. The text frozen here is not edited.
- The SOP this plan is drawn from is not in the public repository. Every threshold below is therefore quoted here in full, with the SOP section it comes from.

## 2. Research questions

Q1. How much of the change in the MLB called strike zone between 2024 and 2026 comes from the 2025 umpire-grading change, and how much from the 2026 ABS challenge system?

Q2. How much do plate umpires differ in their response to each change?

Q3. Is a challenger's skill measurable and rankable in one season, and does a hierarchical model beat Savant's public expectation?

Q4. Does holding both teams' remaining challenges in the state change the optimal challenge policy by a material amount?

Chapter 1 answers Q1 and Q2. Chapter 2 answers Q3. Chapter 3 answers Q4. The P8 question is in `docs/prereg/p8.md`.

Chapter 1 splits the change in the called zone between 2024 and 2026 into two components. One is the 2025 grading change. The other is the 2026 ABS challenge system. Both are measured on one scale: square inches of the 50% called-strike contour, and signed edge shifts in inches. The seasons 2022, 2023 and 2024 supply an untreated pre-trend and a placebo.

## 3. The buffer rule

SOP section 1, verbatim:

> **The buffer rule, stated once, exactly (architect item 18; revision R2 WR-20).** The December 2024 umpire labor agreement cut the grading buffer **from two inches outside the zone edge to three-quarters of an inch on either side of it**. The pre-2025 buffer was outside-only; the 2025 buffer is ±0.75 in. The asymmetry is the mechanism: under the old rule there was no grading penalty for a ball called in the interior, and ±0.75 in removes that. Any sentence anywhere in this project that contains "buffer" and "two inches" must also contain "outside" — a prose-lint rule (WR-20) applied to `abstract/`, `PREREGISTRATION.md`, `docs/prior-art.md`, `docs/memo/` and `docs/ch1.md`. A symmetric-tightening description does not imply the interior effect this study is built to detect, and a reviewer who knows the collective bargaining change will flag it.

The three regimes follow from it.

| regime | seasons | umpire grading | ABS challenge system |
|---|---|---|---|
| `pre_buffer` | 2022, 2023, 2024 | the buffer sat two inches outside the zone edge, outside only | no |
| `buffer_2025` | 2025 | ±0.75 in on either side of the edge | no |
| `abs_2026` | 2026 | ±0.75 in on either side of the edge | yes |

`quality/checks/wr20.py` enforces WR-20 on this file, on every file in `docs/prereg/`, and on the other paths SOP section 6.6 names.

## 4. What was done before the freeze

**Specification development used 2022–2024 only.** The Chapter 1 surface specification was developed on the 2022, 2023 and 2024 regular seasons. No row from 2025 or 2026 entered any specification fit. `docs/prereg/ch1.md` section 1 lists what that development saw, fit by fit.

Every model fitted before this tag used 2022–2024 calls, simulated calls, or no outcome at all:

- SOP W3.11 fitted the frozen `bam` specification and its k ladder on 687,496 called pitches from 2022–2024 (`docs/prereg/ch1.md` sections 1 to 7).
- SOP W3.4 fitted pooled contours for 2022, 2023 and 2024 to size the surviving-batter effect. Its 2025 and 2026 rows in `out/tables/height_coverage.csv` read `not_fitted_before_prereg`.
- SOP W3.12 fitted the link and the nuisance variance components on 2022–2024 calls only. Its power curve, SBC and recovery fits use simulated calls (`docs/prereg/ch1.md` section 8).
- SOP W4.7 sampled M1's prior only, with `sample_prior = "only"`, and never read the outcome (`docs/prereg/ch2.md` section 6).

Some steps read 2025 or 2026 data without fitting a model:

- DT-21, the zone-truth gate: the ABS verdict against the zone of section 7 on 10,168 challenged 2026 pitches.
- SOP W3.6: the 2026 original call, recovered for 10,167 of 10,167 drawer challenges.
- DT-30: the ABS-measured share of called pitches in each season from 2022 to 2026.
- SOP W3.10: pitch-level plane displacements from the trajectory columns, with no call read.
- SOP W3.12: the location, umpire, season, game and edge of 498,059 shadow-band pitches from 2022–2026, as the design of the power curve, with no call read.
- SOP W3.5: sample counts for every season. Its raw shadow-band called-strike rates are published for 2022–2024 only, and the 2025 and 2026 cells of `out/ch1/tab/T1_sample.csv` stay empty until this tag.
- SOP W4.5: overturn counts by role on the 2026 open set (`docs/prereg/ch2.md` section 1).
- SOP W3.9: AAA 2023–2025 called pitches against the zone, game by game, to classify each game's format.

Published work already reports descriptive 2025 and 2026 numbers. `docs/prior-art.md` lists them with their sources.

**What this supports.** SOP D-67 asks for the tag before the first Chapter 1 fit of any kind. The fits listed above ran before it, on 2022–2024 calls and simulated calls. D-67 allows a wider sentence only if `ops/check_seal_order.sh` (GD-12) shows every fit receipt in `out/` descending from the pushed tag. Otherwise the abstract uses the narrow sentence D-67 names:

> the sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened

Whether the fits above count against D-67's ordering is the owner's call (section 14, item 13).

## 5. Prior work

`docs/prior-art.md` is the ledger of prior work, and every claim here is bounded by it. The nearest public work is `AyanArora29/use-it-or-lose-it` (MIT), described in `docs/prior-art.md` section 1. Its zone agrees with the ABS verdict on 99.75% of 10,155 challenged pitches (`docs/prior-art.md` section 1.1). It named the 2025 buffer confound in public on 2026-08-17, in `lit/04`, `lit/06`, `lit/22` and `METHODS_REVIEW` item `B5` (`docs/prior-art.md` section 1.3).

This project adds the 2022–2024 regime so that the confound can be resolved on the same estimand (`docs/prior-art.md` section 7). It does not claim to have noticed the confound. It does not claim the count-bias contrast or the overturn discontinuity as new. `docs/prior-art.md` section 7 lists each claim with the citation that bounds it.

## 6. The sealed set

The rule is one predicate, in `quality/sql/analysis_set.sql`, frozen at this tag:

```sql
CASE
  WHEN game_type IN ('S','A','E')                                        THEN 'excluded'
  WHEN season = 2026 AND game_type = 'R' AND official_date >= DATE '2026-09-22' THEN 'sealed'
  WHEN season = 2026 AND game_type IN ('F','D','L','W')                  THEN 'sealed'
  ELSE 'open'
END AS analysis_set
```

`config/seal.yml` mirrors it for Python and R: `seal_start_date` 2026-09-22, `regular_season_end` 2026-09-27, `postseason_end_estimate` 2026-11-01. Sealed game types are R, F, D, L and W; excluded types are S, A and E. UT-17 asserts the two files agree, and UT-16 asserts the rule.

The partition reads `gameData.datetime.officialDate`, never `gameDate`. Game 825030 is a 2026-09-15 game whose `gameDate` reads 2026-09-16T01:40:00Z.

Only MLB 2026 is sealed. AAA and MLB 2015–2025 are prior-regime data that the public literature has had for months.

`quality/sealed_manifest.json` records the regular-season tail: 88 gamePks with official dates from 2026-09-22 to 2026-09-27. Their `gamepks_sha256` is `ec40cdd5e643d478e54ff1f495281314a14353e525310b716f836a8ae399059e`. Before the unseal, one commit tagged `seal-postseason` adds the postseason gamePks. That commit changes nothing but `postseason_gamepks`, `postseason_appended_at` and the hash.

SOP phase 5, verbatim:

> **Sealed-set size, stated honestly.** Roughly 80–100 remaining regular-season games (2026-09-22 to 09-27) plus about 32–43 postseason games ≈ **115–131 games ≈ 17,500 called pitches ≈ 4,900 in the ±3 in shadow band ≈ 520–570 challenges.** The standard error on the shadow-band rate is about 0.7 pp; on the challenge overturn rate about 2.2 pp. **The sealed set cannot estimate a contour and cannot resolve a small model-versus-market or model-versus-baseline difference. It is a confirmatory prediction and calibration check, and every artifact says so.**

**What the seal is.** The sealed archive is protected by a passphrase held in the owner's password manager on a single-user laptop. That is all it is. It is not a separation of duties, not an escrow, not a third-party timestamp, and not a custody chain. The same person can decrypt the archive, edit the analysis and re-encrypt it. What the seal buys is that opening it leaves a record: a git tag, a commit, and a line in `docs/prereg/SEAL.md`. In one line: the seal is a passphrase on a single-user laptop, not a separation of duties.

**The unseal.** `absump.seal._unlocked()` requires all six conditions of SOP phase 5:

1. the tag `prereg-v1` exists;
2. it is pushed, and `git ls-remote --tags origin refs/tags/prereg-v1` returns the same sha as the local tag;
3. it is an ancestor of `HEAD`;
4. the worktree is clean;
5. `quality/prereg.lock` matches the sha256 of `git show prereg-v1:PREREGISTRATION.md` and of the annexes;
6. the owner has set `ABS_SEAL_UNLOCK=1` in one shell and appended a dated line to `DECISIONS.md` with the manifest sha256.

No agent sets that variable. Before the unseal, each chapter commits a power addendum that states the difference its sealed sample can detect.

Each sealed analysis runs once and never twice: SOP W3.23, W4.17 and the W5.11 sealed row. `src/absump/sealed_run.py` refuses to run if `out/sealed/.lock` exists.

**A known gap in the predicate.** A 2026 regular-season row with a NULL `officialDate` classifies as open, because SQL's three-valued logic sends it to the `ELSE` branch. The predicate is frozen and is not edited to close the gap. The recommended default enforces `officialDate` as NOT NULL upstream, and the owner has not yet taken that decision. `tests/unit/test_seal_classifier.py::test_null_official_date_is_not_sealed` pins the current behaviour.

## 7. Chapter 1 sample, zone and heights

**The zone.** One zone serves every season. The plane is the middle of the plate, with 2022–2025 crossings re-projected from the front. The top is 0.535 × H / 12 ft and the bottom 0.27 × H / 12 ft, where H is the batter height in inches. The edge rule is D-14: a strike when any part of the ball, radius 1.45 in, touches the 17-inch zone, Euclidean at the corners. `docs/harmonized_zone.md` states the constants and where each consumer reads them.

**The samples.** SOP D-61 defines two, once:

- P0 is every called pitch with `game_type == 'R'`, official date 2022-01-01 to 2026-09-21, and non-null re-projected coordinates. It holds 1,830,267 rows at the freeze.
- P1 is P0 restricted to the ABS-measured-height cohort. It holds 1,487,942 rows at the freeze.

`out/ch1/tab/T1_sample.csv` carries both, season by season, with one row per exclusion.

**The height rule.** The owner's answer D-R0-02 makes roster height plus the calibration offset the primary batter height, in all five seasons. The primary sample is therefore P0. The ABS-measured height is a pre-registered robustness arm, on P1. This departs from the SOP's D-13 text, which made measured height the headline. The owner's answer replaces that text before the tag.

The D-13 fork turns on DT-30, the ABS-measured share of called pitches, published before this tag (CH1-A12):

| season | regime | called pitches | ABS-measured | ABS-measured share | roster+offset share | below 0.60 |
|---|---|---|---|---|---|---|
| 2022 | `pre_buffer` | 367,145 | 217,859 | 0.593387 | 1.000000 | yes |
| 2023 | `pre_buffer` | 374,523 | 272,064 | 0.726428 | 1.000000 | no |
| 2024 | `pre_buffer` | 367,017 | 302,888 | 0.825270 | 1.000000 | no |
| 2025 | `buffer_2025` | 368,925 | 341,232 | 0.924936 | 1.000000 | no |
| 2026 | `abs_2026` | 358,461 | 358,459 | 0.999994 | 1.000000 | no |

The 2022 share is below the 0.60 trigger. The fork's roster-height branch is the one taken, and D-R0-02 applies it to all five seasons.

**Exclusions.** Each is a row in `out/ch1/tab/T1_sample.csv`: `game_type != "R"`; the postseason, held out of the primary as a separate pre-registered secondary; `automatic_ball`, `pitchout`, `hit_by_pitch` and blank-coordinate rows; pitches thrown by position players. `blocked_ball` is kept as a genuine ball call. The surface fit uses `|d| ≤ 8.0 in` on the harmonised zone. The shadow band `|d| ≤ 3.0 in` is a reporting region and a sensitivity factor, not a filter.

**Four games without ABS hardware.** Games 823669, 823745, 825093 and 825094 were played at neutral sites with no ABS hardware (D-P2-01). They were played on 2026-04-25, 2026-04-26, 2026-08-13 and 2026-08-23. They join neither the 2026 regime nor a control regime, and every Chapter 1 estimate excludes them. They are also the four dates of D-P3-10, which carry the 1,144 of 688,686 MLB 2026 rows that break the 0.535 / 0.27 zone rule. D-P3-10 asked for this exclusion to be stated here with its dates and row count. At the freeze the Chapter 1 analysis table still holds their 621 called pitches (section 14, item 3).

**The 2026 original call.** Statcast and the game feed both store the call after a challenge. Chapter 1 models the original call. SOP W3.6 recovers it (CH1-A2), and it differs from the published call on 5,490 rows of the analysis table.

**The balanced umpire panel.** Umpires with at least 15 home-plate games in every season from 2022 to 2026: 62 of them. CH1-A14 reports the decomposition on this panel beside the headline.

## 8. Chapter 1 plan

**The estimator.** The primary estimator is the frozen `mgcv::bam` specification in `docs/prereg/ch1.md` section 2. Its basis dimensions are in `docs/prereg/ch1.md` section 3 and never change after the tag. The fit uses the open window, 2022-01-01 through 2026-09-21. Intervals come from 1,000 posterior coefficient draws from the `bam` covariance `Vp`, and the model is never refitted for an interval. The secondary estimator is the binned logistic of `docs/prereg/ch1.md` section 5.

**The estimands.** SOP W3.14–W3.17, verbatim:

> **W3.14–W3.17.** Fit the surfaces on 2022-01-01 through 2026-09-21 (about 45 minutes); save `out/ch1/model/{surface_main,surface_binned,surface_framing}.rds` plus 1,000 posterior coefficient draws from `mgcv` `Vp` via `MASS::mvrnorm` and never refit for intervals. Evaluate each season on a grid `x_mid ∈ [−1.5, 1.5]` ft in 0.01-ft steps (301 points) × `zn ∈ [0.15, 0.70]` in 0.002 steps (276 points), **standardised to a fixed reference pitch mix** (the 2024 distribution of count, handedness, pitch group and velocity) by g-computation. Standardisation is not optional: the in-zone pitch rate fell from 50.6% to 47.3% between 2025 and 2026, so raw rates confound pitcher behaviour with umpire behaviour, and no public treatment adjusts for it.
>
> Per season, from the 50% contour by marching squares, reported for a 72-inch batter: `top_in`, `bot_in` (contour height at `|x| ≤ 0.25` ft), `half_width_in` (contour `|x|` at `zn = 0.4025`), `area_sqin`, `shadow_rate` (standardised called-strike rate over `|d| ≤ 3.0 in`), and `count_bias` = `P(strike | d ∈ {−1,0,+1} in, 3-ball) − P(strike | same d, 2-strike)`, **cited to METHODS §8 as their pre-registered estimand and reported as a replication**.

**The decomposition and the headline template.** SOP W3.14–W3.17, verbatim:

> Decomposition. Let `θ_s` be an estimand in season `s`; fit the pre-trend on 2022–2024 as a precision-weighted linear season slope `g`:
>
> ```
> Δ_buffer = θ_2025 − (θ_2024 + g)
> Δ_ABS    = θ_2026 − (θ_2025 + g)
> Δ_total  = θ_2026 − θ_2024
> share_ABS = Δ_ABS / (Δ_ABS + Δ_buffer)
> ```
>
> with a CI from the joint posterior draws. **The two components `Δ_buffer` and `Δ_ABS`, each with a 95% interval, are the primary result; `share_ABS` is reported only when the 95% interval on `Δ_ABS + Δ_buffer` excludes zero, and otherwise the components are reported alone** (architect item 8; revision R2 D-59, CH1-A9). The denominator can cross zero, so the share is unbounded and can change sign when the components partly offset; an interquartile range across the multiverse is not a meaningful quantity for it and that criterion is withdrawn. Sign stability is required of **each component separately**, not of the share. Headline template: *"Of the N square inches by which the called zone contracted between 2024 and 2026, X (95% CI a–b) is attributable to the 2025 grading-buffer cut and Y (95% CI c–d) to the ABS challenge system."* Test: `Δ_buffer + Δ_ABS + 2g == Δ_total` to 1e-9.

The primary result is the pair `Δ_buffer` and `Δ_ABS`, each with a 95% interval (D-59).

**The plane component.** SOP W3.10 and W3.14–W3.17, verbatim:

> **The plane shift is heterogeneous, so it is not a scalar and not a level shift (architect item 3; CH1-A13).** Measured front-to-middle `dz`: **−0.425 in** for a 96 mph four-seam, **−0.909 in** at 94 mph, **−1.451 in** for an 85 mph slider, **−2.015 in** for a 78 mph curve, **−2.583 in** at 72 mph. The top edge of the called zone is fastball-dominated and the bottom edge is breaking-ball-dominated, so correcting 2025 to mid-plate moves the two edges by **very different amounts**. Worked against the published 2025→2026 estimate, the corrected top-edge contraction largely vanishes while the bottom edge moves up on the order of 1 in, which makes the corrected height contraction **several times larger** than published rather than smaller. Therefore: **pre-register the plane component per edge — top, bottom, width — each with its own 95% interval**, and state the estimand as the **velocity-and-break-weighted shift at each edge**, not a mean over all pitches. The share it represents may exceed 1 and may change sign, and every sentence that reports it must read correctly in either direction. The `dz`-by-pitch-type distribution is published as a figure in its own right, because it is a stronger result than the scalar.
>
> Plane component: fit the 2025 contour twice, on raw front-plane coordinates (what Clemens used) and re-projected to mid-plate; report `Δ_mechanical` and the corrected 2025→2026 contraction with the share of the published −8 to −22 sq in that is convention rather than behaviour.

**Umpire heterogeneity.** The estimator is SOP W3.18, stages B1 to B3, as `docs/prereg/ch1.md` section 8.2 codes it. The prior-sensitivity rule, SOP W3.18, verbatim:

> Prior sensitivity: refit with `exponential(1)` and `exponential(4)` and require the posterior median of `τ` to move by less than 20%.

No per-umpire table is published: the power curve does not reach the reliability gate (`docs/prereg/ch1.md` section 8.5, and D-21).

**Framing.** SOP W3.19. The primary 2026 convention scores every pitch at its original call. The robustness convention excludes challenged pitches. The external validity test and its consequence, SOP W3.19, verbatim:

> External validity test: 2022–2024 per-catcher values correlate ≥0.85 with Savant's published `catcher-framing` `rv_tot`; below that the framing result is demoted to secondary.

**The AAA arm.** SOP W3.20 is blocked until D-11, D-12 and D-57 land. D-12 is settled by the owner's answer D-R0-01: two challenge tokens in AAA. The arm supports the identification and does not carry it. Its pre-trend rule, SOP W3.20, verbatim:

> Pre-trend test: the AAA-versus-MLB 2023→2024 coefficient must have a 95% interval containing 0, or the DiD is reported as descriptive.

**Placebos.** SOP W3.21, verbatim:

> | # | Placebo | Expectation | Decision rule |
> |---|---|---|---|
> | P1 | **2023 → 2024**, both under the 2-inch-outside-the-edge buffer | null | **two one-sided equivalence tests**: the 90% interval on the shadow-rate difference lies entirely inside ±0.5 pp *and* the 90% interval on the area difference lies entirely inside ±3 sq in. **No zero-coverage clause** |
> | P2 | Within-season false boundaries at each All-Star break | null × 5 | the five estimates give the empirical null; the headline `Δ_ABS` must exceed the 95th percentile of `|placebo|` |
> | P3 | AAA full-ABS days across seasons | null | machine zone does not move |
> | P4 | Pitches with `|d| > 6 in` | null | rate ≈ 0 or 1 and stable; movement indicates tracking drift |

**Pre-registered consequence.** SOP W3.21 requires this sentence here verbatim:

> if P1 or P2 fails, the three-regime decomposition is reported as **descriptive**, the causal language is removed from every artifact, and the failure is the headline finding.

**The sensitivity grid.** SOP W3.22 defines the multiverse that CH1-A9 reads. Its cells, verbatim:

> One factor at a time from the pre-registered primary, using the binned-logistic estimator for the full grid and re-fitting `bam` for the four configurations that move the headline most: `r ∈ {0, 1.0, 1.45, fitted}`; height source ∈ {ABS-measured cohort, roster+offset, per-batter ML offset}; shadow band ∈ {2, 3, 4} in; band restriction ∈ {6, 8, unrestricted} in; plane ∈ {mid, front}; `blocked_ball` in/out; position-player pitchers in/out; postseason in/out; `k` at 0.75× and 1.5×; standardisation mix ∈ {2024, 2025, unweighted}.

CH1-A9 sets the acceptance rule for this grid. The interquartile-range rule that SOP W3.22 also states is withdrawn by CH1-A9 and D-59.

**The sealed run.** SOP W3.23 runs once, after 2026-11-01, from a worktree that descends from `prereg-v1` with no modified frozen script. It predicts the sealed-set shadow-band rate with a 95% predictive interval from the open-window model. No refit and no re-specification follow it. CH1-A10 deletes the per-umpire rank-correlation clause that SOP W3.23 also states.

## 9. Chapter 2 plan

`docs/prereg/ch2.md` is the plan. It carries the M1 and M2 formulas byte for byte from the SOP, the priors, the covariates and the sealed sample.

- M1 estimates `P(overturn | challenged, challenger)`. **M1 does not condition on `m`** or on any other measure of where the pitch crossed the plate (`docs/prereg/ch2.md` section 3, D-64).
- M2 estimates each challenger's perception noise and criterion on the probit scale, with the link fixed by D-55 (`docs/prereg/ch2.md` section 5).
- The variance-components signal share gates willingness, and split-half is reported beside it (D-65).
- The sealed set carries calibration-in-the-large only (D-31, `docs/prereg/ch2.md` section 9).

## 10. Chapter 3 plan

`docs/prereg/ch3.md` is the plan. Chapter 3 is a replication of the public single-side challenge dynamic program, plus one number: the change in win probability when both teams' remaining challenges are in the state. The pre-registered materiality threshold is 0.05 WP points per team-game (D-42). Below it, the result is a bounded null with its interval.

## 11. Phase 2, P8

`docs/prereg/p8.md` fixes the P8 acceptance criteria and the P8 rules the SOP already set. P8's full plan and its own seal come later, under `p8-prereg-v1`. P8 work past the free capture waits for the Chapter 1 result call and the tag `ssac-paper-2026-12-04`.

## 12. Acceptance criteria

Each criterion quotes its threshold from SOP section 9 byte for byte. The ids are the SOP's. Each entry names the test ids that check it. Where the SOP names no test id, the entry says so and names the step whose verify command checks it; section 14 lists those gaps.

### 12.1 Chapter 1, SOP section 9.2

#### CH1-A1, zone truth, a hard gate

Threshold, SOP section 9.2, verbatim:

> CH1-A1 zone truth ≥99.75% overall and ≥99.95% outside ±0.5 in on 2026 challenged pitches (hard gate).

- Test ids: DT-21.
- Checked by: SOP W3.8, `Rscript R/ch1/11_zone_gate.R --check`, which writes `out/ch1/tab/T2_zone_gate.csv`.
- If it fails: a hard gate. No surface is fitted until `r` is re-fitted and the gate passes (SOP W3.8).
- At the freeze: 99.9607% overall, 10,164 of 10,168; 99.9868% outside the band, 7,573 of 7,574. Both clear their bars (`out/ch1/tab/T2_zone_gate.csv`).

#### CH1-A2, the 2026 original call, a hard gate

Threshold, SOP section 9.2, verbatim:

> CH1-A2 the 2026 original call is recovered for 100% of the 10,167 challenges, by DT-28's drawer bridge or by the feed fallback, with 0 ambiguous matches (hard gate).

- Test ids: DT-28, DT-22, UT-07.
- Checked by: SOP W3.6, `Rscript R/ch1/02_original_call.R --check`. DT-22 is paper tier under D-62.
- If it fails: a hard gate. The feed pull is the fallback route (SOP W3.6, D-62).
- At the freeze: 10,167 of 10,167 recovered: 10,139 through the DT-28 bridge and 28 through the feed fallback, with 0 ambiguous and 0 unrecovered. DT-28 as written did not pass, because those 28 were ambiguous at 2-decimal rounding.

#### CH1-A3, the 2023 to 2024 placebo

Threshold, SOP section 9.2, verbatim:

> CH1-A3 the 2023→2024 placebo passes **two one-sided equivalence tests**: the 90% interval on the shadow-rate difference lies entirely inside ±0.5 pp and the 90% interval on the area difference lies entirely inside ±3 sq in. There is no zero-coverage clause, because with about 740k called pitches the interval is 1 to 2 sq in wide and the zone moved every year from 2008 to 2023, so a real 2 sq in drift would fail a zero-coverage test on precision rather than confounding. **Failure converts the chapter to descriptive and removes the causal language, and that failure is then the headline finding.**

- Test ids: none in the SOP.
- Checked by: SOP W3.21, placebo P1 in section 8.
- If it fails: the quote above states it. Section 8 carries the same consequence for P1 and P2.

#### CH1-A4, both components, whatever the sign

Threshold, SOP section 9.2, verbatim:

> CH1-A4 `Δ_buffer` and `Δ_ABS` are reported with 95% intervals whatever the sign, and a null with half-width ≤3 sq in is a reportable result.

- Test ids: none in the SOP.
- Checked by: SOP W3.16. Its identity check, `Δ_buffer + Δ_ABS + 2g == Δ_total` to 1e-9, has no test id either.
- If it fails: not a pass-or-fail gate. Both components are reported with 95% intervals whatever their sign.

#### CH1-A5, the binned-logistic cross-check

Threshold, SOP section 9.2, verbatim:

> CH1-A5 the binned-logistic estimate sits inside the `bam` interval and differs by ≤0.15 in on edges and ≤3 sq in on area.

- Test ids: none in the SOP.
- Checked by: SOP W3.11, `Rscript R/ch1/20_spec_dev.R --check`, for the dry run; SOP W3.22 for the headline.
- If it fails: wider disagreement is reported as a limitation, not silently resolved.
- Detail: `docs/prereg/ch1.md` section 5 states the tolerance and its dry run.

#### CH1-A6, umpire heterogeneity, thresholds in `docs/prereg/ch1.md` section 8.5

Threshold, SOP section 9.2, verbatim:

> CH1-A6 `τ` is reported with its interval; "material" is declared only if `P(τ ≥ 0.20 in) ≥ 0.90`, **at a threshold set by D-60's power curve rather than chosen in advance**, and a per-umpire table is published only if the split-half reliability of the response clears the value that curve shows to be achievable.

- Test ids: MT-09, MT-07, MT-05, MT-01.
- Checked by: SOP W3.12, `Rscript R/ch1/21_synthetic.R --check`, which re-derives the thresholds from `out/tables/ch1_power_curve.csv`. SOP W3.18 applies them.
- If it fails: when the rule does not fire, the bounded null of the Chapter 1 annex, section 8.5, is the reportable result.
- Detail: the Chapter 1 annex, section 8.5, holds the thresholds the D-60 curve sets. They are not restated here.

#### CH1-A7, injected-effect recovery

Threshold, SOP section 9.2, verbatim:

> CH1-A7 injected shifts of 0.60 / 0.30 / 0.10 in are recovered within ±0.10 in with coverage ≥93/100, and the zero-effect criterion is an equivalence test in the same form as CH1-A3 rather than a bare false-positive rate.

- Test ids: MT-03, MT-04.
- Checked by: SOP W3.12, `Rscript R/ch1/21_synthetic.R --check`.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: `docs/prereg/ch1.md` section 8.7 fixes the replicate design and the equivalence form of the null.

#### CH1-A8, simulation-based calibration

Threshold, SOP section 9.2, verbatim:

> CH1-A8 SBC rank histograms are uniform at α = 0.05 for `τ` and the regime mean.

- Test ids: MT-02.
- Checked by: SOP W3.12, `Rscript R/ch1/21_synthetic.R --check`.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: `docs/prereg/ch1.md` section 8.7.

#### CH1-A9, sign stability, and when the share is reported

Threshold, SOP section 9.2, verbatim:

> CH1-A9 the sign of `Δ_ABS` **and** the sign of `Δ_buffer` are each stable across the whole multiverse; `share_ABS` is reported **only when the 95% interval on `Δ_ABS + Δ_buffer` excludes zero**, and otherwise the components are reported alone. The IQR criterion is withdrawn, because the share's denominator can cross zero and its interquartile range is then not a meaningful quantity.

- Test ids: none in the SOP.
- Checked by: SOP W3.22, over the grid in section 8.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.

#### CH1-A10, calibration on the sealed set

Threshold, SOP section 9.2, verbatim:

> CH1-A10 on the sealed set the observed shadow rate falls inside the model's predictive interval. **The per-umpire rank-correlation clause is deleted**: D-15's sealed set is about 115 to 131 games with roughly 4,900 shadow-band pitches, which over the 70 to 90 home-plate umpires working the last week plus the postseason is 55 to 70 shadow pitches each, an order of magnitude short of the 200 the criterion demanded, so it could not pass whether or not the model is correct. Calibration-in-the-large is what the sealed set can carry, exactly as D-31 restricts Chapter 2.

- Test ids: none in the SOP.
- Checked by: SOP W3.23, `Rscript R/ch1/60_sealed_run.R`, once. GD-02 and GD-12 guard the order of events; they do not check the calibration clause.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: Chapter 1 commits its power addendum before the unseal (section 6).

#### CH1-A11, framing against Savant

Threshold, SOP section 9.2, verbatim:

> CH1-A11 2022–2024 per-catcher framing values correlate ≥0.85 with Savant `rv_tot`.

- Test ids: none in the SOP.
- Checked by: SOP W3.19.
- If it fails: the framing result is demoted to secondary (SOP W3.19, quoted in section 8).

#### CH1-A12, height coverage before the tag

Threshold, SOP section 9.2, verbatim:

> CH1-A12 per-season ABS-height coverage as a share of called pitches is published before `prereg-v1`, and D-13's fork is decided from it.

- Test ids: DT-30.
- Checked by: SOP W3.4, `Rscript R/ch1/03_heights.R --check`.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- At the freeze: published in `out/tables/height_coverage.csv` and in section 7. The owner's answer D-R0-02 decides D-13.

#### CH1-A13, the plane component, per edge

Threshold, SOP section 9.2, verbatim:

> CH1-A13 the plane component is reported **per edge** with its own 95% interval, plus the `dz`-by-pitch-type figure.

- Test ids: none in the SOP.
- Checked by: SOP W3.17, from the SOP W3.10 displacements.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: Section 8 quotes the estimand.

#### CH1-A14, the balanced umpire panel

Threshold, SOP section 9.2, verbatim:

> CH1-A14 the balanced-umpire-panel decomposition is reported beside the headline, with the difference between them stated as a number.

- Test ids: none in the SOP.
- Checked by: SOP W3.16, on the 62-umpire panel of section 7.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.

#### The rest of SOP section 9.2, the chapter build and the result call

Threshold, SOP section 9.2, verbatim:

> Plus: `make ch1 && make test-ch1` regenerates every figure and table and exits 0; and the `out/ch1/decision.md` file carries a line beginning `RESULT CALL:` written by the owner.

- Test ids: none in the SOP.
- Checked by: `make ch1 && make test-ch1`.
- If it fails: the chapter is not done. The `RESULT CALL:` line is the owner's, and no agent writes it.

### 12.2 Chapter 2, SOP section 9.3

`docs/prereg/ch2.md` section 7 carries these criteria with the tests and failure rules its author assigned. The quotes below are the thresholds; the annex holds the detail.

#### CH2-H2a, accuracy is rankable

Threshold, SOP section 9.3, verbatim:

> CH2-H2a accuracy is rankable: `P(sd_challenger > 0.10 logit | data) ≥ 0.80` **and** split-half Spearman-Brown ≥0.40 for catchers with ≥20 challenges.

- Test ids: MT-05, MT-07, MT-03.
- Detail, checks and failure rule: `docs/prereg/ch2.md` section 7.1.

#### CH2-H2b, willingness is rankable

Threshold, SOP section 9.3, verbatim:

> CH2-H2b willingness is rankable: `P(sd_tau > 0.20 probit | data) ≥ 0.80` **and the variance-components signal share ≥0.60**, with split-half reported beside it at ≥0.40 and pre-registered as the lower of the two. A split-half below the variance-components value is expected and is not evidence of a bug; the R1 claim that it "would contradict a public result" is withdrawn, because the public 0.80 is a method-of-moments signal share from a fixed-effects probit on all of a player's challenges and a ten-challenge half is a far noisier estimator of the same quantity.

- Test ids: MT-07, MT-05, UT-21.
- Detail, checks and failure rule: `docs/prereg/ch2.md` section 7.2.

#### CH2-H2c, the opponent effect

Threshold, SOP section 9.3, verbatim:

> CH2-H2c the opponent effect: `P(sd_opponent > 0.10 logit | data) ≥ 0.80`, with the under-powered case pre-declared as a reportable null printed beside the **five-seed firing-rate** power curve.

- Test ids: MT-11, MT-05.
- Detail, checks and failure rule: `docs/prereg/ch2.md` section 7.3.

#### CH2-H2d, calibration

Threshold, SOP section 9.3, verbatim:

> CH2-H2d calibration: on 10-fold game-grouped CV the Cox slope is in [0.80, 1.25] with its 95% CI containing 1 and `|α| ≤ 0.05` logit; on the sealed set, calibration-in-the-large only with `|α| ≤ 0.15`.

- Test ids: MT-06, MT-10.
- Detail, checks and failure rule: `docs/prereg/ch2.md` section 7.4.

#### CH2-H2e, M1 against Savant

Threshold, SOP section 9.3, verbatim:

> CH2-H2e M1's log loss beats Savant's `exp_rate_overturns` baseline with a game-clustered 95% CI excluding 0, **with M1 restricted to D-64's ex-ante covariates so the comparison is like for like** — **and if it does not, the reportable finding is that Savant's public expectation is already as well calibrated as a hierarchical model, which is a service to the field.**

- Test ids: MT-06, MT-10.
- Detail, checks and failure rule: `docs/prereg/ch2.md` section 7.5.

#### Blocking reproduction gates, before any novelty claim

Threshold, SOP section 9.3, verbatim:

> **Blocking reproduction gates before any novelty claim:** role overturn rates reproduce 58.8 / 49.0 / 39.3 to ±0.3 pp; **M2's σ_fld is within 0.4 in of 1.90 and σ_bat within 0.6 in of 3.02, both on the probit scale**; the edge formula reproduces `edge_dist_calc` to 1e-6 on 100% of rows.

- Test ids: BR-2, UT-21 and DT-23. The role-rate gate has no SOP test id.
- Detail, checks and failure rule: `docs/prereg/ch2.md` section 7.6.

#### The rest of SOP section 9.3, also required

Threshold, SOP section 9.3, verbatim:

> Plus: T-01 through T-17 green in `out/ch2/VERIFICATION.md`; every published row has a finite interval and a `sigma_scale` value; no pitcher carries a rank; no raw pitch rows under `out/`.

- Test ids: none in the SOP. T-01 to T-17 are the chapter's own test ids, reported in `out/ch2/VERIFICATION.md`.
- Detail, checks and failure rule: `docs/prereg/ch2.md` section 7.7.

### 12.3 Chapter 3, SOP section 9.4

`docs/prereg/ch3.md` section 9 carries these criteria with their checks in detail.

#### CH3-A1, the BR-1 regression, a hard gate

Threshold, SOP section 9.4, verbatim:

> CH3-A1 the BR-1 regression passes at ±5e-5 WP on `V` and ±0.01 on the capture ratio (hard gate).

- Test ids: BR-1.
- Checked by: SOP W5.9.
- If it fails: a hard gate. The chapter does not ship. The diagnosis runs in order: the WP surface, then perception, then the pool, then the recursion (SOP W5.9).
- Detail: `docs/prereg/ch3.md` section 9.1.

#### CH3-A2, the invariance battery

Threshold, SOP section 9.4, verbatim:

> CH3-A2 the full invariance battery passes with zero unexplained violations, concavity violations confined to `h ∈ {19..24}`, the extras grant exact at odd `h ∈ {19, 21, 23}`, rows 0 and 25 still zero pads, and the antisymmetry test green on a symmetrised pool.

- Test ids: MT-08, UT-22.
- Checked by: SOP W5.8.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: `docs/prereg/ch3.md` section 9.2.

#### CH3-A3, the win-probability surface

Threshold, SOP section 9.4, verbatim:

> CH3-A3 the WP surface reaches r ≥ 0.837 / MAE ≤ 0.215 pp against `delta_home_win_exp` and r ≥ 0.998 against `home_win_exp`.

- Test ids: BR-3.
- Checked by: SOP W5.3.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: `docs/prereg/ch3.md` section 9.3.

#### CH3-A4, the two-sided difference and its interval

Threshold, SOP section 9.4, verbatim:

> CH3-A4 `BR − 1S` is reported with a game-clustered 95% CI of width ≤0.10 pp, whether or not it clears 0.05 pp.

- Test ids: none in the SOP.
- Checked by: SOP W5.15, 300 game-clustered bootstrap replicates through the full pipeline.
- If it fails: not a pass-or-fail gate on the sign. The interval width is the bar, and the difference is reported whether or not it clears 0.05 pp.
- Detail: `docs/prereg/ch3.md` section 9.4.

#### CH3-A5, the second-order term and the flip bound

Threshold, SOP section 9.4, verbatim:

> CH3-A5 `E − BR` and the continuation-after-flip bound are both reported.

- Test ids: none in the SOP.
- Checked by: SOP W5.11 and W5.12.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: `docs/prereg/ch3.md` section 9.5.

#### CH3-A6, the benchmark table

Threshold, SOP section 9.4, verbatim:

> CH3-A6 the benchmark table has no empty cells and every published number carries a URL and an access date.

- Test ids: none in the SOP.
- Checked by: SOP W5.14.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: `docs/prereg/ch3.md` section 9.6.

#### CH3-A7, the write-up frames a replication

Threshold, SOP section 9.4, verbatim:

> CH3-A7 `docs/ch3.md` frames the chapter as a replication in its first paragraph, headlines none of the five published results, and states the separation condition as sufficient rather than biconditional.

- Test ids: none in the SOP.
- Checked by: SOP W5.16. MT-08 tests the separation condition in the sufficiency direction only.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: `docs/prereg/ch3.md` section 9.7.

#### CH3-A8, determinism

Threshold, SOP section 9.4, verbatim:

> CH3-A8 `make ch3` reproduces every output deterministically with identical sha256 at a fixed seed, at whatever AAA dimension D-12 settles.

- Test ids: RP-07, MT-08.
- Checked by: `make ch3`; RP-07 and MT-08's determinism clause.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.
- Detail: `docs/prereg/ch3.md` section 9.8.

### 12.4 Phase 2, SOP section 9.5

`docs/prereg/p8.md` section 2 carries P8-A1 to P8-A6 byte for byte.

## 13. Test ids cited, SOP section 6 verbatim

Every test id this document names is the SOP's. Their definitions follow, quoted byte for byte from SOP section 6.

> | id | Assertion | Command |
> |---|---|---|
> | RP-07 | determinism | `make all && cp -r out out.a && make clean-out && make all && python quality/compare_out.py out.a out --tol 1e-8` |

> UT-07 `call_original = call_final XOR is_overturned`

> UT-16 the seal classifier on `(2026,'R','2026-09-22')`→sealed, `(2026,'W',*)`→sealed, `(2026,'R','2026-09-21')`→open, `'S'`→excluded

> UT-17 `config/seal.yml` agrees with `quality/sql/analysis_set.sql`

> **UT-21 M2 scale: simulate 20,000 challenge decisions from a known probit σ = 1.90 in, fit with `family = bernoulli(link = "probit")`, assert `1/s` recovers σ within 0.1 in; the same simulation fitted on the logit link must return about 1.116 in, which is the assertion that documents the bug**

> **UT-22 DP standing and sign: `side(j)` is the batting team on a called strike and the fielding team on a called ball; `MTV_H ≥ 0` and `MTV_A ≥ 0` on a random `V` satisfying the monotonicity constraints; `g_j^{(A)} == -g_j^{(H)}` identically**

> | id | Assertion | Gate |
> |---|---|---|
> | DT-21 | **zone truth**: reconstructed ABS verdict agrees with the observed challenge outcome on challenged MLB-2026 pitches | **≥99.75% overall, ≥99.95% outside ±0.5 in** |
> | DT-22 | feed-reconstructed `call_original` equals Savant drawer `original_isStrike_ump` | 100% of joined challenges; paper tier under D-62 |
> | DT-23 | W4's independently computed `m` matches the drawer-derived `m` | `< 0.01 in` on ≥99.9% of 10,167 rows |
> | DT-28 | **drawer coordinate bridge**: every drawer challenge joins to exactly one Statcast row on (`game_pk`, `round(plate_X,2)`, `round(plate_Z,2)`) | **100% of 10,167, 0 ambiguous, 0 unmatched**; this is the sprint's gate on the 2026 original call, and a failure triggers the feed-pull fallback |
> | DT-30 | **ABS-height coverage** per season, as a share of called pitches | reported as a table, and the D-13 fork is decided from it before `prereg-v1` |

> GD-02 no artifact touching sealed rows or with `max_official_date > 2026-09-21` unless its `git_sha` descends from a pushed `prereg-v1`

> **GD-12 pre-registration ordering: every fit receipt in `out/`, sealed or open, carries a `git_sha` that descends from the pushed `prereg-v1` tag**

> MT-01 prior predictive (Ch1: implied shadow-zone called-strike rate in [0.10, 0.90] for ≥95% of draws, implied between-umpire SD of the top-edge shift < 3.0 in for ≥99%; Ch2: the two gates in W4.7, on the probit scale).

> MT-02 SBC, L = 200, worst Benjamini-Hochberg-adjusted uniformity p > 0.01, 0 parameters outside the 95% simultaneous ECDF band; one L = 1,000 full-scale run before 2026-12-04.

> MT-03 recovery: Ch1 injected −0.60 in top / +0.30 in bottom / −0.10 in width recovered within ±0.10 in with coverage 46/50 in [0.80, 0.98] and mean |bias| ≤0.15 in (edge) and 0.10 in (SD); Ch2 Spearman ≥0.60, 90% of true σ_i covered, and the UT-21 probit-scale recovery within 0.1 in.

> MT-04 null injection: the decision rule fires in ≤5 of 50 and the 90% interval covers zero in ≥43 of 50.

> MT-05 convergence on every reported fit: 4 chains × 1,000/1,000 minimum, rank-normalised split R-hat ≤1.01, `ess_bulk` ≥400, `ess_tail` ≥400, **divergent transitions == 0**, max-treedepth hits == 0, E-BFMI ≥0.2 per chain via `fit$diagnostic_summary()`. A fit with any divergence is reparameterised or reported as failed, never reported with a footnote.

> MT-06 calibration: ECE ≤0.03 over 10 equal-count bins, PIT inside a 90% simultaneous band, Brier and log loss against **three named baselines** — the league base rate, Savant `exp_rate_overturns`, and the competitor's role-level σ model.

> MT-07 reliability: variance components and split-half both reported with their agreement as a number; the variance-components value is the one that gates.

> MT-08 DP: residual < 1e-10; monotone in own tokens and non-increasing in opponent tokens; the two implementations agree < 1e-9 WP; the one-sided restriction reproduces the one-sided solve < 1e-9; **the solve is antisymmetric under swapping the two teams on a symmetrised pool, to 1e-12**; **the separation condition is tested in the sufficiency direction only** — it collapses exactly to 1e-12 on a synthetic pool satisfying the condition, and the necessity direction is neither claimed nor tested; the analytic Uniform(0,1) toy matches `[0.5, 0.625, 0.6953125, 0.741729736328125, 0.7750815008766949, 0.800375666500635, 0.8203006037631678, 0.8364465402671089]` to 1e-12; concavity violations confined to `h ∈ {19..24}`; the extras grant is exact at odd `h ∈ {19, 21, 23}` and rows 0 and 25 stay zero pads; determinism bit-identical at `--seed 20260922`.

> **MT-09 Chapter 1 umpire-heterogeneity power: the D-60 curve exists, `out/tables/ch1_power_curve.csv` reports the firing rate of `P(τ ≥ 0.20 in) ≥ 0.90` and the simulated split-half at τ ∈ {0.10, 0.20, 0.30} in over 5 seeds each, and the CH1-A6 thresholds in `PREREGISTRATION.md` are the ones that file implies.**

> MT-10 leakage: training and evaluation row-id sets hashed and asserted disjoint.

> **MT-11 Chapter 2 power: `power_curve.csv` reports firing rates over 5 seeds per cell, with the replication count and a Wilson interval on every rate; no single-replication posterior probability is reported as an error rate anywhere in the repo.**

> **BR-1 (hard gate, their inputs, their configuration):** `V[1,6,2] = 0.02482455 ± 5e-5`; `MTV1(h=1) = 0.015292 ± 5e-5`; `MTV2(h=1) = 0.008591 ± 5e-5`; `MTV2(h=17) = 0.004106 ± 5e-5`; `optimal 0.0256647`, `observed 0.0211942`, `oracle 0.0643381 ± 2e-4`, `card 0.0237931`, `naive50 0.0118465`, `late50 0.0038184`, `observed_model 0.0190900`, `never 0.0`, each ±5e-5; `capture_ratio 0.8258 ± 0.01`; `optimum/oracle 0.399 ± 0.01`; the re-solved array shape `(26, 13, 3)` element-wise within 5e-5 for all `h ≤ 18`.

> **BR-2 (our inputs, our pipeline), ≥7 of 8 inside tolerance:** V(2) 2.48 ±0.10 pp; MTV1 1.53 and MTV2 0.86 (inning 1) ±0.10; MTV2 0.41 (inning 9) ±0.10; optimum 2.57 ±0.15 pp; observed 2.12 ±0.10 pp; capture inside [0.797, 0.854]; counterfactuals 3.173 and 1.956 ±0.15 pp; **σ_bat 3.02 and σ_fld 1.90 ±0.15 in on the probit scale**. **Any miss is written into `METHODS.md` with the observed value and a hypothesis, never silently absorbed.** The receipt records the pinned release asset date the comparison used.

> BR-3: the WP surface reaches r ≥ 0.837 and MAE ≤ 0.215 pp against `delta_home_win_exp`, and r ≥ 0.998 against `home_win_exp`; the de-vigged market's own log loss on SBRO 2010–2021 lies in [0.64, 0.70] nats, computed on the post-`NL`-drop denominator.

> **WR-20 any sentence containing "buffer" and "two inches" must also contain "outside"**, applied to `abstract/`, `PREREGISTRATION.md`, `docs/prior-art.md`, `docs/memo/` and `docs/ch1.md`.

## 14. Open at the freeze

1. **The Chapter 2 power grid has not run.** `docs/prereg/ch2.md` section 10, item 1. SOP W4.8, W4.18, D-28 and R-19 require it before this tag. The owner decides whether the tag waits for it.
2. **The other Chapter 2 items.** `docs/prereg/ch2.md` section 10, items 2 to 8, among them the W4.7 prior-predictive result on the logit link.
3. **The four games without ABS hardware are still in the analysis table.** Section 7 excludes them. SOP W3.7 must drop their 621 called pitches before SOP W3.14 fits.
4. **The Chapter 1 recovery replicates were still running at the freeze.** Their results go to the W3.12 receipt, not into `docs/prereg/ch1.md` (section 8.7 there).
5. **Criteria with no SOP test id.** CH1-A3, CH1-A4, CH1-A5, CH1-A9, CH1-A10's calibration clause, CH1-A11, CH1-A13, CH1-A14, CH3-A4, CH3-A5, CH3-A6, CH3-A7, and the Chapter 2 role-rate gate. Each names the step that checks it. Assigning test ids is SOP W9.8 and W9.11 work.
6. **Two statements of the Chapter 1 recovery rule.** MT-03 and MT-04 state coverage over 50 replicates. CH1-A7 states coverage over 100. Both are SOP text and both apply as written.
7. **The NULL `officialDate` gap in the sealed predicate** (section 6) is raised and not decided.
8. **The SOP is not public.** `sop/` is outside git, so this document quotes each threshold in full. Whether the SOP joins the public pre-registration is an owner decision.
9. **The prior-art pin is partial.** 3 of the 7 files SOP W5.1 names are pinned byte for byte, and the Chapter 3 regression input is not pinned (`docs/prereg/ch3.md` section 10).
10. **The number gate cannot vouch for this file.** `quality/check_numbers.py` reads three ledgers, and none of them carries a pre-registration source. The W7.6 verify command traces every number here to a named file instead.
11. **Owner sign-off.** SOP section 9.1 closes a prose artifact with a dated owner line in `DECISIONS.md`. It has not been given.
12. **The Chapter 1 annex covers SOP W3.11 and W3.12 only.** Sections 7, 8 and 12 of this document carry the rest of the Chapter 1 plan from the SOP text.
13. **D-67 and the fits before the tag.** The 2022–2024 specification fits and the simulated fits of section 4 ran before this tag. Whether they break D-67's ordering, and so whether the abstract may use the wider sentence, is the owner's call.
