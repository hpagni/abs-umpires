# MLB's called strike zone: a failed placebo and two contractions

## Introduction

For clubs evaluating catchers and pitchers, framing and pitch-location comparisons across seasons must account for changes in what umpires call strikes. Public estimates of the 2026 shrink circulated within weeks (Clemens, FanGraphs, 28 April 2026). In 2025 the umpire grading buffer narrowed from two inches outside the edge to three-quarters of an inch either side (Andrews, FanGraphs, 5 May 2025); in 2026 regular-season ABS challenges began. The question is how much the zone changed at each step, against three old-rule seasons on one measurement plane; no published estimate I found gives both with intervals.

## Methods

I re-projected 2022-2025 pitches to Statcast's 2026 plate midpoint. The main height rule used roster height plus a fixed offset throughout. Sample, from Statcast and the MLB game feed: 1,830,231 called pitches in 12,060 regular-season games, 2022 through 21 September 2026. Near the edge, I fitted a binomial GAM to the umpire's original, pre-challenge call by location and season, with umpire effects partially pooled. Each season's zone is its 50 percent contour; model-conditional intervals (95% unless marked 90%) use 1,000 coefficient draws and omit season-to-season variation. With ABS-measured heights, the rebuilt geometry, not the fitted model, matched 10,164 of 10,168 ABS challenge verdicts. I measured both steps net of the 2022-2024 trend. The placebo pair, 2023 and 2024, had no change to the zone or umpire grading.

## Results

The pre-registered placebo failed: the zone grew 10.8 (90% CI 7.7 to 13.9) square inches, beyond its ±3 margin, so every step is descriptive. Net of the trend, the area fell 23.4 (95% CI 18.6 to 28.3) square inches in 2025 and 33.1 (95% CI 28.7 to 37.5) in 2026 (Figure 1). The zone lost width mostly in 2025 and height mostly in 2026 (Table 1). Within 3 inches of the rule-book zone's edge, the called-strike rate fell 10.69 (95% CI 10.04 to 11.28) percentage points from 2024 to 2026. Clemens's comparison reads 2025 at the plate front and 2026 at mid-plate. That convention gives a loss of 20.0 (95% CI 13.0 to 28.2) square inches; with both at mid-plate it is 32.8 (95% CI 29.3 to 36.6). The binned estimator failed the ±3 agreement tolerance, giving contractions of 29.5 and 40.7 square inches. Top-edge intervals covered 91 of 100 recovery runs, below the 93 bound.

## Conclusion

The 2025 zone was already smaller than any 2022-2024 zone, before regular-season challenges began, so framing and location baselines that start from 2025 miss that step. Table 1's shifts serve three uses: season-adjusted framing and pitch-location baselines, edge targets for pitchers, and the plane correction for 2025-to-2026 Statcast comparisons. Main limit: the failed placebo; the design cannot assign either step to its rule. The sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened. Games from 22 September 2026 on remain sealed for a confirmatory calibration check after the postseason.
