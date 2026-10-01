# The Zone Moved First: A Pre-registered Measurement of MLB's Called Strike Zone, 2022–2026

## Introduction

For clubs evaluating catchers and pitchers, framing and pitch-location comparisons across seasons must account for changes in what umpires call strikes. Public estimates of the 2026 shrink circulated within weeks (Clemens, FanGraphs, 28 April 2026). In 2025 the umpire grading buffer narrowed from two inches outside the edge to three-quarters of an inch either side (Andrews, FanGraphs, 5 May 2025); in 2026 regular-season ABS challenges began. The question is how much the zone changed at each step, against three old-rule seasons on one measurement plane; no published estimate I found gives both with intervals.

## Methods

I re-projected 2022-2025 pitches to Statcast's 2026 plate midpoint. The main height rule used roster height plus a fixed offset throughout. Sample, from Statcast and the MLB game feed: <<N_CALLED>> called pitches in <<N_GAMES>> regular-season games, 2022 through 21 September 2026. Near the edge, I fitted a binomial GAM to the umpire's original, pre-challenge call by location and season, with umpire effects partially pooled. Each season's zone is its 50 percent contour; model-conditional intervals (95% unless marked 90%) use 1,000 coefficient draws and omit season-to-season variation. With ABS-measured heights, the rebuilt geometry, not the fitted model, matched <<N_CHAL_AGREE>> of <<N_CHAL>> ABS challenge verdicts. I measured both steps net of the 2022-2024 trend. The placebo pair, 2023 and 2024, had no change to the zone or umpire grading.

## Results

The pre-registered placebo failed: the zone grew <<P1_AREA>> square inches, beyond its ±3 margin, so every step is descriptive. Net of the trend, the area fell <<D_BUF>> square inches in 2025 and <<D_ABS>> in 2026 (Figure 1). The zone lost width mostly in 2025 and height mostly in 2026 (Table 1). Within 3 inches of the rule-book zone's edge, the called-strike rate fell <<SHADOW_TOT_LOSS>> percentage points from 2024 to 2026. Clemens's comparison reads 2025 at the plate front and 2026 at mid-plate. That convention gives a loss of <<A_CONV>> square inches; with both at mid-plate it is <<A_CORR_LOSS>>. The binned estimator failed the ±<<A5_TOL>> agreement tolerance, giving contractions of <<BIN_BUF_LOSS>> and <<BIN_ABS_LOSS>> square inches. Top-edge intervals covered <<COV_TOP_HIT>> of <<COV_TOP_N>> recovery runs, below the <<COV_TOP_BOUND>> bound.

## Conclusion

<<CALL>> Table 1's shifts serve three uses: season-adjusted framing and pitch-location baselines, edge targets for pitchers, and the plane correction for 2025-to-2026 Statcast comparisons. Main limit: the failed placebo; the design cannot assign either step to its rule. The sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened. Games from 22 September 2026 on remain sealed for a confirmatory calibration check after the postseason.
