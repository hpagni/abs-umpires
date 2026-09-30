# The called strike zone shrank twice, and drifted with no rule change

## Introduction

The umpire grading buffer went from two inches outside the edge to three-quarters of an inch either side (Andrews, FanGraphs, 5 May 2025). The zone narrowed from the sides in 2025, the season umpire grading tightened, and shrank again at the top and bottom in 2026, when regular-season challenges began.

## Methods

I re-projected 2022-2025 pitches to Statcast's 2026 plate midpoint. I fitted called-strike probability near the edge on <<N_CALLED>> called pitches in <<N_GAMES>> regular-season games. Each season's zone is its 50 percent contour. With ABS-measured heights, the zone geometry matched <<N_CHAL_AGREE>> of <<N_CHAL>> challenge verdicts. I measured both steps net of the 2022-2024 trend, with umpire effects partially pooled. The placebo pair, 2023 and 2024, had no change to the zone or to umpire grading, although the pitch clock and shift limits arrived in 2023 and other rules changed in 2024.

## Results

In pre-registered checks, the placebo failed: the zone grew <<P1_AREA>> square inches, beyond its ±3 margin, so every step is descriptive. A binned cross-check found both steps <<A5_BUF>> and <<A5_ABS>> square inches larger, beyond its ±<<A5_TOL>> tolerance, and top-edge intervals read slightly too narrow in the recovery test. Every interval reflects pitch-level sampling, not season-to-season variation. From 2022 to 2023, not pre-registered, the zone shrank <<DRIFT_2223_AREA>>, so the 2025 step depends on its baseline (Table 1 footnote). As Figure 1 shows, the 2025 step was <<D_BUF>> square inches. The 2026 step, <<D_ABS>>, exceeded every All-Star-break swing, the largest <<P2_AREA_MAX>>. Each side came in 0.41 inches in 2025 (Table 1), over three times its 2023-to-2024 drift of <<DRIFT_2324_HW>>, not pre-registered. In 2026 the bottom rose 0.65 and the top fell 0.63, near its drift of <<DRIFT_2324_TOP>>, the largest, not pre-registered. With 2025 at the plate front, as in the published <<A_PUB_LOSS>> (Clemens, FanGraphs, 28 April 2026), the loss is <<A_CONV>> square inches. Both at mid-plate, it is <<A_CORR_LOSS>>. The standard deviation of umpire-specific 2026 shifts was <<SD_UMP>> inches.

## Conclusion

<<CALL>> On pitch-level intervals, the 2026 step is <<SHARE_ABS>> percent of the two combined (95% CI <<SHARE_ABS_CI>>). The gap between steps is about one season's drift, so the ranking is not established, a caveat for any two-season comparison. The limit is the failed placebo: the design cannot assign either step to its rule. The sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened. That set, games from 22 September 2026 and the postseason, stays sealed until it ends.
