# MLB's called strike zone shrank in 2025 and 2026

## Introduction

In 2025 the umpire grading buffer narrowed from two inches outside the edge to three-quarters of an inch either side (Andrews, FanGraphs, 5 May 2025); in 2026 regular-season ABS challenges began. Framing and location models start from the called zone, so each shrink's timing and size matter. I found no published estimate with intervals on both steps against old-rule seasons. The zone lost width mostly in 2025 and height mostly in 2026.

## Methods

I re-projected 2022-2025 pitches to Statcast's 2026 plate midpoint, with one height rule throughout. Sample: <<N_CALLED>> called pitches in <<N_GAMES>> regular-season games, 2022 through 21 September 2026. I fitted a binomial GAM of the umpire's original call, before any challenge, to location by season, umpire effects partially pooled. Each season's zone is its 50 percent contour. The rebuilt zone geometry, not the fitted model, matched <<N_CHAL_AGREE>> of <<N_CHAL>> ABS challenge verdicts. I measured both steps net of the 2022-2024 trend. The placebo pair, 2023 and 2024, had no change to the zone or umpire grading, although 2024 changed the clock and running lane.

## Results

The pre-registered placebo failed: the zone grew <<P1_AREA>> square inches, beyond its ±3 margin, so every step is descriptive. Net of the trend, the area fell <<D_BUF>> square inches in 2025 and <<D_ABS>> in 2026 (Figure 1). The half-width fell <<HW_BUF_LOSS>> inches in 2025. In 2026 the bottom rose <<BOT_ABS_PT>> and the top fell <<T1_ABS_TOP>>, after rising <<DRIFT_2324_TOP_PT>> from 2023 to 2024 (Table 1). Within 3 inches of the edge, the called-strike rate fell <<SHADOW_TOT_LOSS>> points, 2024 to 2026. One published range, <<A_PUB_LOSS>> (Clemens, FanGraphs, 28 April 2026), reads 2025 at the plate front and 2026 at mid-plate. That convention gives a loss of <<A_CONV>> square inches; with both at mid-plate it is <<A_CORR_LOSS>>. Every interval is model-conditional, from 1,000 coefficient draws, omitting season-to-season variation. A binned estimator gave larger steps, <<BIN_BUF_LOSS>> and <<BIN_ABS_LOSS>> square inches, beyond the ±<<A5_TOL>> tolerance; top-edge intervals covered <<COV_TOP_HIT>> of <<COV_TOP_N>> recovery runs (bound <<COV_TOP_BOUND>>).

## Conclusion

<<CALL>> On model-conditional intervals the 2026 step was the larger, <<SHARE_ABS>> percent of the two combined (95% CI <<SHARE_ABS_CI>>). But the gap, <<D_GAP_LOSS>> square inches, is about the size of the 2023-to-2024 change and not established. Main limit: the failed placebo; the design cannot assign either step to its rule. The sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened. That set, games from 22 September 2026 on, is unopened; it tests calibration after the postseason.
