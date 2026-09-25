# Pre-registration annex: Chapter 2

This is the Chapter 2 annex to `PREREGISTRATION.md`, version 1.0. It is frozen by the `prereg-v1` tag. After the tag, any change is a logged deviation in `docs/DEVIATIONS.md`, not an edit.

It comes from SOP step W4.1. The M1 and M2 formulas in sections 4 and 5 are the SOP's W4.10 and W4.11 text, copied byte for byte. Measured numbers come from `out/ch2/log/prior_predictive.json` (W4.7) and `data/interim/ch2/challenges.parquet` (W4.5). Published numbers from other work cite `docs/prior-art.md`.

Section 10 lists eight items that must close before the tag. The largest is the power curve: the five-seed grid of section 8 has not run.

## 1. What was seen before this annex

Chapter 1 developed its specification on 2022–2024 data only. Chapter 2 has no development sample. The challenge system it studies has run in MLB only in 2026, so no earlier MLB season exists to tune on. The Chapter 2 specification is the SOP text, fixed before any Chapter 2 fit.

No model has been fitted to a Chapter 2 outcome. W4.7 sampled M1's prior with `sample_prior = "only"` and never read the outcome column.

Outcomes were read for data validation. Each read is listed here.

- W4.5 checked `overturned == 1{m > 0}` on all 19,469 rows of the frame, MLB 2026 and AAA 2025.
- The W4.5 verifier counted overturns by role on the MLB open set: 2,259 of 4,612 batter challenges, 3,163 of 5,382 catcher challenges and 68 of 173 pitcher challenges.
- Those counts round to 49.0%, 58.8% and 39.3%. They put the role-rate reproduction gate of section 7.6 inside its tolerance on the open set.
- While writing this annex, the builder printed the same counts for AAA 2025 from the frame. No AAA rate appears here.
- The SOP records a timing run of M1's shape, 58.5 s of sampling, and four single simulated fits of the opponent effect (section 8.1). Neither left output in this repository.
- The SOP does not say whether that timing run used real outcomes.

## 2. Estimand and sample

M1's estimand is `P(overturn | challenged, challenger)`. It marginalises over the challenger's unobserved perception of the pitch. That is the skill quantity the leaderboard reports (SOP W4.13, D-64).

M2's estimands are each challenger's perception noise `sigma_i` and criterion `tau_i`, in inches on the probit scale (section 5).

The headline sample is every MLB 2026 open-set challenge through 2026-09-21: 10,167 challenges. 4,612 are by the batting side and 5,555 by the fielding side (DT-25). The fielding side is 5,382 catcher challenges and 173 pitcher challenges.

Grouping levels in that sample, from the W4.7 design: 652 challengers, 589 opponents, 743 pitchers, 91 plate umpires and 30 teams. 133 challengers have 20 or more challenges.

AAA 2025 adds 9,302 challenges. Under D-28 they enter the variance-components and year-over-year arms only, never the headline. D-28 stays provisional until the W4.8 grid runs (section 8).

The source is the Savant ABS drawer (W4.2). The frame is W4.5, `data/interim/ch2/challenges.parquet`, which never enters git.

## 3. The exclusion rule: M1 does not condition on `m`

The signed evidence, in inches, from SOP W4.5:

```
m = +edge_dist_calc   if original_isStrike_ump == 1   (a called strike; the batter wants the ball outside)
m = -edge_dist_calc   if original_isStrike_ump == 0   (a called ball; the fielding side wants it inside)
```

Then `overturned == 1{m > 0}` exactly. W4.5 measured it on 19,469 of 19,469 rows, with 0 rows at `m == 0`.

**The rule: M1 does not condition on `m`.** It also does not condition on `edge_dist_calc`, or on any other measure of where the pitch crossed the plate.

Why. ABS is deterministic given the measured margin, so `P(overturn | challenged, m)` is a step function at `m = 0`. A model that conditions on `m` fits almost perfectly, and every random effect collapses to zero.

Its log loss would then beat Savant's `exp_rate_overturns`, which is ex ante, and prove nothing. Skill is choosing a pitch with `m > 0`, so M1 marginalises over `m`.

M1 may not read the 13 columns the W4.5 frame lists in its `w45_m1_excluded` metadata: `m`, `edge_dist_calc`, `edge_dist_rederived`, `edge_side`, `plate_x`, `plate_z`, `sz_top`, `sz_bot`, `reasonable_attempt`, `sz_challenge_prob`, `sz_challenge_runs`, `runs_at_stake_z` and `original_is_strike`.

Two of them need a reason beyond location. `runs_at_stake_z` is realised, not ex ante: its sign equals the outcome on every row. `original_is_strike` is collinear with `role`: the challenger is a batter exactly when the call was a strike, on 19,469 of 19,469 rows.

The rule binds M1 only. M2 models whether a challenge is made, not whether it succeeds, so `m` is its signal axis (section 5).

The step function `P(overturn | challenged, m-bucket)` is reported in `out/ch2/VERIFICATION.md` as a check on the zone and the join. It is never M1 and never a model check.

Enforcement. SOP W4.5 requires a failing test for this rule and gives it no test id. The test does not exist yet. On 2026-09-25 the W4.5 verifier cut `w45_m1_excluded` to 2 names, and `--check` still passed 22 of 22.

What the test must do: the W4.10 fit script stops before sampling if a listed column, or a column derived from one, enters the M1 design matrix. Section 10, item 4.

## 4. M1, accuracy

One row per challenge, N = 10,167 MLB 2026 open-set challenges. SOP W4.10, verbatim:

```r
f1 <- brms::bf(
  # D-64: EX-ANTE OBSERVABLE AT THE MOMENT OF DECISION ONLY.
  # edge_dist_calc, m, edge_side and every other post-hoc location measure are excluded.
  # orig_call is dropped as collinear with role: the batting side challenges called
  # strikes and the fielding side called balls.
  overturned ~ 1 + role + balls + strikes + inning_band + leverage_tercile +
    tokens_own + tokens_opp +
    (1 | challenger_id) + (1 | opponent_id) + (1 | pitcher_id) +
    (1 | ump_id) + (1 | team_id)
)
family <- brms::bernoulli("logit")
pr <- c(prior(normal(0, 1.5), class = "Intercept"),
        prior(normal(0, 1),   class = "b"),
        prior(exponential(4), class = "sd"))
```

### 4.1 Covariates

D-64 fixes the covariates as ex ante: each is observable to the challenger at the moment of decision.

| term | definition | built by |
|---|---|---|
| `role` | batter, catcher or pitcher: `challenging_player_id` matched against `player_at_bat`, `fielder_2` and `pitcher`. `team_summary_mode` is never read | W4.5 |
| `balls`, `strikes` | the count before the pitch, entered as numbers | W4.5 |
| `inning_band` | 1-3, 4-6, 7-8, 9+, the prior art's card bands (`fixtures/prior_art/uiloi/tier1_card_2026.csv`) | W4.7 |
| `leverage_tercile` | low, mid, high: the tercile of the call's win-probability stake, on the prior art's card bins | not built, section 10 item 3 |
| `tokens_own`, `tokens_opp` | challenges in hand before the pitch, entered as numbers, from the warehouse view `v_opportunity_open` | W4.7 |
| `challenger_id` | the challenging player | W4.5 |
| `opponent_id` | `fielder_2` when `role` is batter, else `player_at_bat` | W4.5 |
| `pitcher_id` | the pitcher, present on every row | W4.5 |
| `ump_id` | the plate umpire, from `dim_umpire_game` | W4.7 |
| `team_id` | the challenger's team | W4.7 |

`role`, `inning_band` and `leverage_tercile` are factors with treatment contrasts. `orig_call` is dropped as collinear with `role`, as the formula comment says.

On the 173 pitcher challenges the challenger and pitcher effects coincide. The effects stay identified off the other 9,994 rows. A sensitivity row drops the 173.

### 4.2 Sampler and convergence

4 chains × 2,000 iterations, `adapt_delta = 0.95`, `seed = 20260922`. brms 2.23.0 on CmdStan 2.40.0 through cmdstanr 0.9.0. M1 stays on the logit link, and its thresholds in section 7 are in logit units.

`config/seeds.yml` names a different Chapter 2 chain seed, `ch2_brms_chain_base: 424242`. M1 uses the W4.10 seed. Section 10, item 6.

Every reported fit meets MT-05. That means at least 4 chains × 1,000/1,000, rank-normalised split R-hat ≤1.01, `ess_bulk` ≥400 and `ess_tail` ≥400. It also means 0 divergent transitions, 0 max-treedepth hits and E-BFMI ≥0.2 per chain.

A fit with any divergence is reparameterised or reported as failed. It is never reported with a footnote.

## 5. M2, signal detection

One row per challenge opportunity: a called pitch where the role's team still held a token and the role was eligible. SOP W4.11, verbatim:

```r
f2 <- brms::bf(
  challenged ~ 1 + m + role + cell + (1 + m | challenger_id) + (1 | opponent_id)
)
family <- brms::bernoulli(link = "probit")   # fixed, never defaulted: see Part 2, W4.11 continued
pr <- c(prior(normal(0, 2), class = "Intercept"), prior(normal(0, 1), class = "b"),
        prior(exponential(4), class = "sd"), prior(lkj(2), class = "cor"))
```

The W4.11 continuation, verbatim:

```r
  family = bernoulli(link = "probit"),   # CHANGED R2: brms::bernoulli() defaults to logit
  prior  = c(prior(exponential(4), class = "sd"), prior(lkj(2), class = "cor"))
```

The opportunity frame is W4.6, `data/interim/ch2/opportunities.parquet`. It needs the 2,512-game feed pull and is paper tier.

The link is probit, fixed by D-55. `brms::bernoulli()` defaults to logit. The prior art's σ is on the probit scale (`docs/prior-art.md`, section 1.1). A logit fit's `1/slope` understates it by a factor of 1.702, so a true 1.90 in comes back as 1.116 in.

`cell` is `inning_band` × `leverage_tercile` × PA-ending, matching the prior art's cell thresholds so σ is comparable. PA-ending means the call would end the plate appearance; the other level is count-changing.

For challenger i with slope `s_i = b_m + r_m[i]` and intercept `a_i`:

- perception noise `sigma_i = 1 / s_i`, in inches, probit scale;
- criterion `tau_i = -a_i / s_i`, in inches, the willingness axis.

Every export carries `sigma_scale = "probit"`. σ is reported against the prior art's σ_bat = 3.02 in and σ_fld = 1.90 in. If the logit link is ever restored for sampling reasons, `sigma_i = 1.702 / s_i`, and METHODS says so beside every citation of 3.02 and 1.90.

Bandwidth. `|m| ≤ 3.0 in` is the primary. 2.0 and 4.0 in are multiverse rows. If the primary fit takes more than 4 h, the fallback is two-stage: `mgcv::bam` for the population curve and cells, then brms on per-challenger sufficient statistics.

The fallback is a robustness row, never the primary. The SOP's benchmark, still running at 41 minutes, was taken under logit. It is re-run under probit before the bandwidth choice counts as measured.

UT-21 pins the scale. It simulates 20,000 challenge decisions from a known probit σ = 1.90 in, fits them on the probit link and recovers σ within 0.1 in. The same simulation fitted on the logit link must return about 1.116 in.

## 6. Priors and the prior predictive check

| model | class | prior | link |
|---|---|---|---|
| M1 | `Intercept` | `normal(0, 1.5)` | logit |
| M1 | `b` | `normal(0, 1)` | logit |
| M1 | `sd` | `exponential(4)` | logit |
| M2 | `Intercept` | `normal(0, 2)` | probit |
| M2 | `b` | `normal(0, 1)` | probit |
| M2 | `sd` | `exponential(4)` | probit |
| M2 | `cor` | `lkj(2)` | probit |

The W4.11 continuation block restates only the `sd` and `cor` priors, and agrees with the W4.11 block on both. `exponential(4)` on `sd` has a prior mean of 0.25 and a 90th percentile of 0.576 on the link scale.

W4.7 sampled M1's prior only: 1,000 draws, seed 20260922, on the 10,167-row design, with 0 divergent transitions. It ran each gate on two links.

| arm | gate 1: 95% interval of the league overturn rate, must cover [0.10, 0.90] | gate 1: median, must lie in [0.35, 0.65] | gate 2: 90th percentile of the between-challenger SD, must be below 0.30 | result |
|---|---|---|---|---|
| probit, the scale MT-01 names | [0.0772, 0.9174] | 0.4950 | 0.1413 | both gates pass |
| logit, the link W4.10 fits | [0.1204, 0.8757] | 0.4988 | 0.1045 | gate 1 fails |

MT-01 reads the Chapter 2 gates on the probit scale, and there both pass. On the logit link that M1 is fitted on, gate 1 fails: the interval reaches neither 0.10 nor 0.90.

W4.7's rule, written before any draw, required both arms. Its receipt therefore records a failure.

This annex keeps the SOP priors unchanged. The choice between them and a wider M1 `Intercept` prior is the owner's. Section 10, item 2.

The W4.7 design carried a placeholder for `leverage_tercile`: balanced thirds from a permutation seeded at 20260922. Every `b` has the same prior, so the placeholder affects the check only through its marginal distribution.

## 7. Acceptance criteria

The thresholds are SOP section 9.3, unchanged. Each names the tests that check it. Where the SOP names no consequence of failure, the consequence given is this annex's default and is marked so.

### 7.1 CH2-H2a, accuracy is rankable

- Threshold: `P(sd_challenger > 0.10 logit | data) ≥ 0.80`, and split-half Spearman-Brown ≥0.40 for catchers with ≥20 challenges.
- Checked by: MT-05 on the M1 fit; MT-07 for the split-half; MT-03 for the recovery that gives a rank its meaning.
- If it fails (annex default): accuracy is reported as not rankable in one season. The leaderboard keeps shrunken estimates with 95% intervals and carries no accuracy rank.
- The split-half uses the chronological challenge index, with `r_SB = 2r/(1+r)` over challengers with ≥20 challenges. Section 10, item 5 records an ordering fault in that index.

### 7.2 CH2-H2b, willingness is rankable

- Threshold: `P(sd_tau > 0.20 probit | data) ≥ 0.80`, and the variance-components signal share ≥0.60.
- The split-half is reported beside it at ≥0.40 and is pre-registered as the lower of the two.
- The variance-components value is the gate (D-65). It is computed as the prior art computes it: `(Var(p̂) − mean binomial Var) / Var(p̂)`.
- The published comparison values are signal shares of 0.80 for the threshold and 0.33 for the overturn rate among catchers, and 0.73 and 0.13 among batters (`docs/prior-art.md`, section 1.1).
- A split-half below the variance-components value is expected and is not evidence of a bug. A ten-challenge half is a noisier estimator of the same quantity.
- Checked by: MT-07, MT-05, and UT-21 for the probit scale.
- If it fails (annex default): willingness is reported as not rankable in one season. `tau_i` is published with its interval and no rank.

### 7.3 CH2-H2c, the opponent effect

- Threshold: `P(sd_opponent > 0.10 logit | data) ≥ 0.80`.
- Checked by: MT-11 for the power curve; MT-05 on the fit.
- If it fails (SOP R-19): a posterior mean between 0.05 and 0.15 with P < 0.80 is reported as "not resolvable in one season". The five-seed firing-rate power curve of section 8 is printed beside it.
- That null is a reportable result, not a failure to hide.
- Any other failing case (annex default): the posterior mean and its 95% interval are reported, beside the same curve.

### 7.4 CH2-H2d, calibration

- Threshold, open set: on 10-fold CV grouped by `game_pk`, the Cox slope is in [0.80, 1.25] with its 95% CI containing 1, and `|α| ≤ 0.05` logit.
- Threshold, sealed set: calibration-in-the-large only, with `|α| ≤ 0.15`.
- Method: Cox calibration `glm(y ~ logit_phat, family = binomial)`, with α and β and their 95% CIs. A reliability diagram of 10 equal-count bins with Wilson intervals.
- Checked by: MT-06, which also requires ECE ≤0.03 over 10 equal-count bins; MT-10, which asserts training and evaluation row ids are disjoint.
- If it fails (annex default): M1's probabilities are reported as miscalibrated, with α, β and their intervals. No artifact presents them as calibrated. CH2-H2e is still reported.

### 7.5 CH2-H2e, M1 against Savant

- Threshold: M1's log loss beats Savant's `exp_rate_overturns` baseline, with a game-clustered 95% CI on the difference that excludes 0.
- M1 is restricted to D-64's ex-ante covariates, so the comparison is like for like.
- Method: Brier and log loss for M1, for `exp_rate_overturns` broadcast to each challenge, and for a role-only intercept baseline. A paired game-clustered bootstrap of 1,000 replicates.
- Checked by: MT-06, with its three named baselines: the league base rate, Savant `exp_rate_overturns`, and the prior art's role-level σ model. MT-10 for disjoint folds.
- If it fails (SOP): the reportable finding is that Savant's public expectation is already as well calibrated as a hierarchical model.

### 7.6 Blocking reproduction gates, before any novelty claim

- Role overturn rates reproduce 58.8 / 49.0 / 39.3 to ±0.3 pp (`docs/prior-art.md`, section 1.1). The SOP names no test id for this gate. Section 10, item 7.
- M2's σ_fld is within 0.4 in of 1.90 and σ_bat within 0.6 in of 3.02, both on the probit scale. Checked by BR-2 and UT-21.
- BR-2 carries its own row for the same two values at ±0.15 in, and passes when at least 7 of its 8 rows are inside tolerance. Both thresholds stand as the SOP writes them.
- The edge formula reproduces `edge_dist_calc` to 1e-6 on 100% of rows. Checked by the W4.5 check, which measured 5.773e-15 in on 19,469 of 19,469 rows, and by DT-23.
- DT-23 asserts W4's own `m` matches the drawer-derived `m` to < 0.01 in on ≥99.9% of the 10,167 rows.
- If any gate fails (SOP): Chapter 2 makes no novelty claim until it passes. A BR-2 miss is written into `METHODS.md` with the observed value and a hypothesis.

### 7.7 Also required by section 9.3

- T-01 through T-17 green in `out/ch2/VERIFICATION.md`.
- Every published row has a finite interval and a `sigma_scale` value.
- No pitcher carries a rank. Pitchers appear with `role == "pitcher"` and no rank, because none of the 104 pitchers has more than 8 challenges.
- No raw pitch rows under `out/`.

### 7.8 Model gates behind the criteria

- MT-01: section 6.
- MT-02, SBC (W4.8): 200 replications at N = 3,000, 2 chains × 1,000 iterations. Rank histograms for `Intercept`, `sd_challenger` and `sd_opponent` pass a chi-square uniformity test at α = 0.01 with 20 bins.
- MT-02 also requires the worst Benjamini-Hochberg-adjusted uniformity p above 0.01, and 0 parameters outside the 95% simultaneous ECDF band.
- MT-03, recovery (W4.9): Spearman ≥0.60 between simulated and recovered challenger accuracy, for challengers with ≥20 challenges.
- MT-03 also requires 90% of true `sigma_i` inside their 90% intervals, and the recovered population σ within 0.25 in of truth on the probit scale.

### 7.9 Secondary analyses, with their limits stated before they run

- W4.12 reliability: three estimators for accuracy and for willingness. Variance components gates; the chronological split-half and a `game_pk %% 2` split are reported beside it, with their agreement as a number (MT-07).
- W4.14 framing against challenging, on the 58 qualified catchers. At n = 58 the 95% CI on a correlation is about ±0.25. The test can separate zero from a moderate correlation, but not from |r| = 0.15.
- W4.15 year over year, AAA 2025 to MLB 2026, players with ≥10 challenges in each. The overlap count is printed before any correlation is computed.
- Below 25 players the cross-level correlation is descriptive only, and the within-2026 split becomes the headline persistence number.

## 8. The power curve

### 8.1 What is measured

Four single fits, from SOP W4.8, ran in 221.6 s. Each is one replication. None is an error rate.

| N | true σ_opp | posterior mean | 95% CrI | posterior P(σ_opp > 0.10), one replication |
|---|---|---|---|---|
| 10,167 | 0.00 | 0.046 | [0.002, 0.129] | 0.09 |
| 10,167 | 0.12 | 0.117 | [0.008, 0.221] | 0.62 |
| 10,167 | 0.25 | 0.246 | [0.169, 0.320] | 1.00 |
| 20,000 | 0.12 | 0.160 | [0.098, 0.217] | 0.97 |

### 8.2 What those fits fix

The decision rule is a posterior probability, not a credible-interval bound. At a true σ_opp of 0.12 the 95% CrI lower bound came back at 0.008. A rule of "lower bound above 0.10" has almost no power there.

The rule is `P(σ > 0.10 | data) ≥ 0.80`. It is the form of CH2-H2a and CH2-H2c.

### 8.3 What is not measured

No error rate is established. A false-positive rate is the share of null replications whose posterior probability clears 0.80. On this evidence that is 0 of 1.

Power at σ_opp = 0.12 is the share of alternative replications that clear it. It is unknown. The values 0.09 and 0.62 are posterior probabilities from one dataset each, not rates.

Under R-19 no power number is quoted until the grid in section 8.4 runs.

### 8.4 The grid, pre-registered

- Cells: σ_opp ∈ {0, 0.06, 0.12, 0.25} × σ_ch ∈ {0.10, 0.23}, 5 seeds per cell, at N = 10,167 and at N = 20,000.
- Seed: `ch2_power_grid: 7003` in `config/seeds.yml`.
- Each fit reports `P(σ_opp > 0.10 | data)`. A cell's firing rate is the share of its 5 seeds where that probability is ≥0.80.
- `power_curve.csv` carries each firing rate, the number of replications behind it and a Wilson interval (MT-11).
- The SOP costs 40 fits at about 37 minutes. The grid as written is 40 fits at each N.
- The curve is printed beside CH2-H2c. D-28's pooling justification and R-19's power statement are re-derived from it before either is committed.

### 8.5 Status on 2026-09-25

The grid has not run. `out/ch2/power_curve.csv` does not exist. SOP W4.8 and W4.18 require the grid before `prereg-v1`.

The fleet plan runs W4.8 in phase 09, which starts only after the tag. Section 10, item 1.

## 9. The sealed set

One predicate, in `quality/sql/analysis_set.sql`, frozen at the `prereg-v1` tag:

```sql
CASE
  WHEN game_type IN ('S','A','E')                                        THEN 'excluded'
  WHEN season = 2026 AND game_type = 'R' AND official_date >= DATE '2026-09-22' THEN 'sealed'
  WHEN season = 2026 AND game_type IN ('F','D','L','W')                  THEN 'sealed'
  ELSE 'open'
END AS analysis_set
```

`config/seal.yml` mirrors it: `seal_start_date` 2026-09-22, `regular_season_end` 2026-09-27, `postseason_end_estimate` 2026-11-01. Sealed game types are R, F, D, L and W; excluded types are S, A and E. UT-17 asserts the two files agree, and UT-16 asserts the rule.

The partition uses `officialDate`, never `gameDate`. Game 825030 is a 2026-09-15 game whose `gameDate` reads 2026-09-16T01:40:00Z.

Only MLB 2026 is sealed. AAA 2025 is open.

Chapter 2's sealed sample (W4.17). After 2026-11-01, re-pull the drawer and take the challenges in sealed games: the regular season from 2026-09-22, plus the postseason. Expected: 520 to 570 challenges.

W4.17 writes the date rule as `game_date >= 2026-09-22`. Membership is decided by the predicate on `game_pk`, so a drawer date that disagrees with `officialDate` does not move a game.

The frozen posterior is scored once. No refitting and no covariate changes. Any change goes in `docs/DEVIATIONS.md`.

The sealed set tests CH2-H2d's calibration-in-the-large, `|α| ≤ 0.15`, and no other criterion in section 7.

Before the unseal, this chapter commits a power addendum stating the detectable α on the sealed sample (SOP section 4, phase 5).

Sealed pitch and challenge rows are not in this repository. They are encrypted under `data/sealed/`. GD-02, GD-06 and GD-12 guard those files and the order of events.

That protection is a passphrase on a single-user laptop, not a separation of duties (`docs/prereg/SEAL.md`).

## 10. Open before the tag

1. **The W4.8 power grid.** Section 8 has no firing rates, and MT-11 checks for them. SOP W4.8, W4.18, D-28 and R-19 require them before `prereg-v1`. The fleet runs W4.8 in phase 09, after the tag. Either the grid runs first and its table enters section 8, or the owner records the change.
2. **W4.7 gate 1 on the logit link.** Keep the SOP priors and read MT-01 on the probit scale, as its text says. Or widen M1's `Intercept` prior and rerun W4.7. This is the owner's choice.
3. **`leverage_tercile` is not built.** It needs W5's win-probability surface and the prior art's cut points. W4.7 used balanced thirds as a placeholder. The cut points are written into section 4.1 before the tag.
4. **The M1 exclusion test does not exist** (section 3). The SOP gives it no test id.
5. **The chronological challenge index is out of game order on 29 rows.** The W4.5 verifier found `game_pk` order reversing `game_number` in doubleheaders. CH2-H2a's split-half reads that index.
6. **Seed conflict.** W4.10 sets `seed = 20260922`; `config/seeds.yml` sets `ch2_brms_chain_base: 424242`. One is recorded as M1's seed.
7. **The role-rate reproduction gate has no test id.** Section 7.6.
8. **Owner sign-off.** SOP section 9.1 closes a prose artifact with a dated owner line in `DECISIONS.md`. It has not been given.
