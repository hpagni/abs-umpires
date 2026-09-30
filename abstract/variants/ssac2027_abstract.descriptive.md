# Three regimes of the called strike zone, 2022-2026: a descriptive split after a failed placebo

## Introduction

Published estimates of the 2025-to-2026 zone change take 2025 as the baseline (Clemens, FanGraphs, 28 April 2026) or fold 2025 into a 2015-2025 trend (Lee et al., arXiv, 22 September 2026). Neither separates 2025, under a smaller umpire grading buffer, from 2026, under ABS challenges.

## Methods

We fit called-strike probability to samples drawn from <<N_CALLED>> called pitches in <<N_GAMES>> MLB regular-season games through 21 September 2026. The regimes are 2022-2024 under a two-inch grading buffer outside the edge, 2025 under three-quarters of an inch, and 2026 under ABS challenges. We re-project 2022-2025 crossings to Statcast's 2026 plate midpoint, edge by edge. One zone, from roster height calibrated to ABS-measured height, covers all seasons. The zone is validated against the ABS verdict on <<N_CHAL>> challenged pitches. We measure the 50 percent contour's 2025 and 2026 steps against the 2022-2024 trend and partially pool umpires.

## Results

The pre-registered 2023-to-2024 placebo failed, so every comparison here is descriptive. With no rule change, the zone grew <<P1_AREA>> square inches, about half its 2025 step, and the shadow-band strike rate rose <<P1_SHADOW>> points. Net of the 2022-2024 trend, the zone shrank <<D_BUF>> square inches in 2025. It shrank <<D_ABS>> more in 2026, beyond every All-Star-break placebo, the largest <<P2_AREA_MAX>>, so the second placebo passed. The 2022-to-2024 pre-trend is <<D_PRE>> square inches per year. The top edge came down <<T1_BUF_TOP>> inches in 2025 and <<T1_ABS_TOP>> in 2026. Top-edge intervals are slightly too narrow. The bottom edge rose <<T1_BUF_BOT>> and <<T1_ABS_BOT>> inches. The plane change is <<D_PLANE_TOP>> inches at the top edge and <<D_PLANE_BOT>> at the bottom. After that correction the 2025-to-2026 area change is <<A_CORR>> against the published <<A_PUB>>. Umpires barely differ: the shrunken between-umpire standard deviation of the edge shift is <<SD_UMP>> inches, split-half reliability <<REL_UMP>> across <<N_UMP>> umpires.

## Conclusion

<<CALL>> Clubs valuing framing and designing pitches against the 2026 zone should date the break to <<BREAK_YEAR>>. The failed placebo is the main limitation: this design cannot assign either step to its rule change. A binned cross-check also misses its ±<<A5_TOL>>-square-inch tolerance, finding both losses <<A5_BUF>> and <<A5_ABS>> square inches larger. The sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened. Games from 22 September 2026 and the postseason are held out.
