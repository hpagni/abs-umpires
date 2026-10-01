# The AAA arm

SOP W3.20. The tables are `out/tables/aaa_placebo.csv`, `out/ch1/tab/aaa_withinweek.csv`, `out/ch1/tab/aaa_pretrend.csv` and `out/ch1/tab/aaa_did.csv`, written by `R/ch1/40_aaa_arm.R`.

The arm has three uses, reported in descending strength. First comes the machine-drift placebo. Second comes the within-week alternation. Third comes the level difference-in-differences with AAA as the control series.

Placebo P1 failed (T5). Every contrast here is therefore descriptive and names no cause.

**Coverage.** The lake holds these AAA feeds: 2023: all 2,224 Final games; 2024: 696 of 2,232 Final games, complete through 2024-05-18; 2025: all 2,232 Final games. The 2024 pull is still open in phase 07, so 2024 is read only as far as its feeds are complete.

## 1. The machine-drift placebo (P3)

Machine days are keyless full-ABS games, where the machine makes every call. Rule-net area is the area inside the machine-day 0.5 contour minus the published zone's area, for a 72-inch batter.

In 2023 the rule-net area is -0.19 sq in over 836 games. In 2024 the rule-net area is +0.17 sq in over 316 games.

From 2023 to 2024 it changes by +0.36 sq in (90% CI -0.44 to +1.22). P3 passes its two one-sided tests at +/-3 sq in.

The 2024 to 2025 change is not evaluable, since 2025 has no keyless full-ABS game on disk.

## 2. The within-week alternation

The frame holds only dates strictly before the changeover date, 2024-06-25. That date is read from the `format_challenge_tue_thu` row of `out/tables/aaa_format.csv`.

It keeps 941 umpire-weeks in which one plate umpire worked both formats. They cover 72 umpires, 962 full-ABS games and 965 challenge-format games, from 2023-04-25 to 2024-05-19.

The frame has 96,554 shadow-band pitches. Their challenge-format called-strike rate minus the full-ABS rate is +4.23 pp (95% CI +3.52 to +4.94).

The comparison is within the umpire's own season, with week fixed effects. It also holds location, count and handedness fixed.

On a full-ABS day the call is the machine's. The contrast therefore reads as the umpire's departure from the machine zone at the same location.

In 2023 alone it is +4.65 pp (95% CI +3.84 to +5.45). In 2024 alone it is +3.09 pp (95% CI +1.96 to +4.21).

On the side edge it is +4.22 pp (95% CI +3.25 to +5.19). On the top edge it is +6.95 pp (95% CI +5.40 to +8.51). On the bottom edge it is +2.22 pp (95% CI +1.09 to +3.35).

## 3. The level difference-in-differences

**The DiD is a supporting arm, not the identification.** The chapter's design is the three-regime MLB comparison. AAA gives a second, weaker reading of the same seasons.

**Parallel trends.** The DiD is MLB's 2024 to 2025 called-zone change minus AAA's challenge-format change over the same seasons. Reading it as more than that difference needs the two series to share one trend. This assumption is strong. The two series differ in umpire populations, parks and Hawk-Eye installations, and AAA's zone is machine-set. Placebo P1 failed, so the DiD is reported as the measured difference only.

Both series use the annex section 5 binned logistic. MLB comes from W3.15's cached draws, and AAA from a bootstrap of games within season. AAA's edges are net of its published rule, which changed from 2023 to 2024.

The primary AAA window is 04-28 to 05-18 of each season, the span every season covers. Every challenge-format game on disk is a robustness row.

In 2024 both AAA series keep only dates strictly before the changeover date, 2024-06-25. The challenge-format games on disk after it are binary-search probes, not a season sample.

**Pre-trend.** Pre-trend test (SOP W3.20): the AAA-versus-MLB 2023 to 2024 coefficient must have a 95% interval containing 0, or the DiD is reported as descriptive.

On area the AAA-versus-MLB 2023 to 2024 coefficient is +16.82 sq in (95% CI +5.58 to +27.79). The interval excludes 0, so the DiD is reported as descriptive.

On the top edge the coefficient is +0.69 in (95% CI +0.50 to +0.94), and the test fails. On the bottom edge the coefficient is +0.11 in (95% CI -0.17 to +0.41), and the test passes. On the half-width the coefficient is +0.10 in (95% CI -0.08 to +0.27), and the test passes.

With MLB's binned series and every AAA challenge-format game on disk, the area coefficient is +20.87 sq in (95% CI +14.98 to +26.91). With MLB's bam series and the primary window, the area coefficient is +14.74 sq in (95% CI +3.07 to +26.18). With MLB's bam series and every AAA challenge-format game on disk, the area coefficient is +18.79 sq in (95% CI +12.27 to +25.17).

**Estimate.** From 2024 to 2025, MLB's area changes by -28.48 sq in and AAA's by -9.25 sq in. The DiD, MLB's change minus AAA's, is -19.23 sq in (95% CI -27.45 to -9.30).

It is reported as descriptive. Its reading in `aaa_did.csv` is "descriptive: placebo P1 failed; the pre-trend 95% interval excludes 0".

With MLB's binned series and every AAA challenge-format game on disk, the DiD is -19.20 sq in (95% CI -24.87 to -13.36). With MLB's bam series and the primary window, the DiD is -13.92 sq in (95% CI -22.54 to -3.34). With MLB's bam series and every AAA challenge-format game on disk, the DiD is -13.89 sq in (95% CI -20.47 to -7.31).

The 2025 to 2026 step is not estimated. No AAA 2026 feed is in the lake, and this phase makes no request.
