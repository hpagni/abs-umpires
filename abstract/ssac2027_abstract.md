# Three regimes of the called strike zone: the steps beside MLB's 2025 umpire grading change and the 2026 ABS challenge system

## Introduction

Published estimates of the 2025-to-2026 zone change either take 2025 as the baseline (Clemens, FanGraphs, 28 April 2026) or fold 2025 into a 2015-2025 trend (Lee et al., arXiv, 22 September 2026). Baseball America (22 September 2026) shows the 2025 zone smaller than any since 2015 but names no cause. The December 2024 umpire labor agreement cut the grading buffer from two inches outside the zone edge to three-quarters of an inch on either side of it. Neither design can separate the challenge system from the grading change that preceded it. Clubs and the league need that split.

## Methods

We fit called-strike probability on the 2022-2026 MLB regular seasons: <<N_CALLED>> called pitches in <<N_GAMES>> games through 21 September 2026. Three regimes: 2022-2024 under the two-inch buffer, 2025 under the three-quarter-inch buffer, 2026 under the challenge system. One zone definition is imposed on all five seasons. Statcast moved plate_x and plate_z from the front of the plate to its middle in 2026. It also replaced operator-set sz_top and sz_bot with fixed 53.5 and 27 percent height fractions. We re-project 2022-2025 crossings to the plate midpoint from vx0 through az and rebuild the zone from roster height calibrated to ABS-measured height. The re-projection shift depends on velocity and break, so we estimate it at each edge. The zone is validated against the ABS verdict on <<N_CHAL>> challenged pitches. We report the 50 percent contour by regime, split the 2024-to-2026 change into buffer and ABS components, and estimate per-umpire shifts with partial pooling.

## Results

The 2025 step, beside the buffer change, is <<D_BUF>> square inches, and the 2026 step, beside the challenge system, is <<D_ABS>>. The placebo failed, so neither step is assigned to its rule. The 2022-to-2024 pre-trend is <<D_PRE>> square inches per year. The plane change moves the top edge <<D_PLANE_TOP>> inches and the bottom <<D_PLANE_BOT>>. After that correction the 2025-to-2026 area change is <<A_CORR>> against the published <<A_PUB>>. After shrinkage the between-umpire standard deviation of the 2026 top-edge shift is <<SD_UMP>> inches, split-half reliability <<REL_UMP>> across <<N_UMP>> umpires.

## Conclusion

<<CALL>> Clubs valuing framing and designing pitches against the 2026 zone should date the break to <<BREAK_YEAR>>. The sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened. Games from 22 September 2026 and the postseason are held out.
