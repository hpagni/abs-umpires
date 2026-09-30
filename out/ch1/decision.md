# Chapter 1 decision memo (Phase 08, chapter1-full)

Written 2026-09-30T21:08:57+02:00 (Europe/Madrid) by the Phase 08 owner-handoff writer, at HEAD
d933a05. This memo reports and decides nothing that is the owner's to decide. Every number below
is copied from a file on disk, named beside it. No agent's prose is evidence: a step counts only
when `scripts/prove.sh <step-id>` exits 0 and `make prove` accepts `quality/receipts/<step-id>.json`.

## 1. What the chapter found

**The chapter is descriptive, not causal.** Placebo P1 failed (CH1-A3). With no rule change
between 2023 and 2024, the called zone still grew +10.79 sq in (90% CI 7.73 to 13.94, margin
+/-3) and the shadow-band strike rate rose +1.54 pp (90% CI 1.03 to 2.04, margin +/-0.5). Both
intervals lie wholly outside their equivalence margins. The pre-registered consequence converts
the three-regime decomposition into a description of what changed, and names no cause
(`out/tables/T5_placebos.csv`, `out/tables/headline.csv` row CH1_P1).

What is described. Between 2024 and 2026 the called zone contracted by 56.0 sq in (95% CI 52.0
to 59.6). Of that, 23.4 sq in (95% CI 18.6 to 28.3) falls in the 2025 buffer season and 33.1
(95% CI 28.7 to 37.5) in the 2026 ABS season. The top edge came down, the bottom edge came up
and the zone narrowed. The shadow-band strike rate fell 10.7 pp.

P2 passed. The All-Star-break placebo: the headline 2026 area change (-33.10 sq in) exceeds the
95th percentile of |placebo| over five within-season boundaries (6.69 sq in). P2 also passed on
every edge. P3 (AAA) was not run. P4 was reported with no threshold.

## 2. Estimands (primary: bam, roster height plus offset, mid-plane, 72-in batter)

Source: `out/tables/T4_decomposition.csv` (W3.16). The share of Δ_ABS is reported only where the
95% interval on Δ_buffer + Δ_ABS excludes zero, per the pre-registered CH1-A9 wording. It
excludes zero on every row below.

| Estimand | g (trend / season) | Δ_buffer (2025) [95% CI] | Δ_ABS (2026) [95% CI] | Δ_total 2024→2026 [95% CI] | Δ_buffer + Δ_ABS [95% CI] | share_ABS [95% CI] |
|---|---|---|---|---|---|---|
| Area, sq in | +0.26 [-1.65, 2.20] | -23.43 [-28.32, -18.57] | -33.10 [-37.46, -28.74] | -56.02 [-59.57, -51.98] | -56.53 [-62.78, -49.75] | 0.586 [0.527, 0.647] |
| Top edge, in | +0.135 [0.086, 0.180] | -0.183 [-0.321, -0.048] | -0.630 [-0.758, -0.504] | -0.544 [-0.652, -0.430] | -0.813 [-0.984, -0.637] | 0.774 [0.652, 0.924] |
| Bottom edge, in | +0.056 [0.016, 0.093] | +0.180 [0.077, 0.287] | +0.649 [0.554, 0.743] | +0.940 [0.853, 1.027] | +0.829 [0.690, 0.963] | 0.783 [0.683, 0.896] |
| Half-width, in | -0.032 [-0.060, -0.007] | -0.412 [-0.495, -0.326] | -0.246 [-0.321, -0.160] | -0.723 [-0.796, -0.645] | -0.658 [-0.764, -0.542] | 0.374 [0.269, 0.464] |
| Shadow rate, pp | -0.09 [-0.41, 0.24] | -4.46 [-5.28, -3.63] | -6.05 [-6.81, -5.31] | -10.69 [-11.28, -10.04] | -10.51 [-11.52, -9.41] | 0.575 [0.522, 0.631] |
| Count bias, pp | -0.02 [-0.08, 0.05] | +0.54 [0.36, 0.72] | +0.72 [0.56, 0.88] | +1.22 [1.07, 1.37] | +1.26 [1.00, 1.49] | 0.570 [0.483, 0.681] |

Arms beside the primary, all from the same file:
- **Balanced 62-umpire panel (CH1-A14).** Area Δ_ABS -33.82 [-38.58, -28.79], a difference of
  -0.71 from the primary. Δ_buffer -20.29 [-25.97, -13.96], a difference of +3.14. Δ_total
  differs by -0.45 sq in.
- **ABS-measured-height cohort (D-13 robustness arm).** Area Δ_buffer -23.84 and Δ_ABS -32.20.
  The sign agrees with the primary on every component.
- **Binned-logistic cross-check (CH1-A5).** Every edge falls inside the bam interval. Area does
  not: Δ_buffer is -29.45 against -23.43 (a difference of -6.02), and Δ_ABS is -40.72 against
  -33.10 (a difference of -7.62). Both lie outside the bam 95% CI and both exceed the 3 sq in
  tolerance.

### 2.1 Plane component, per edge (the D-56 estimand as built)

Source: `out/ch1/tab/T4_plane_component.csv` (W3.17). The first column is 2025 mid-plane minus
front-plane. The next two give the 2025→2026 change: first in the published convention (2025
front-plane against 2026 mid-plane), then plane-corrected (mid-plane in both seasons). Both use
batters seen in both seasons, through 25 April.

| Edge | Plane shift, 2025 mid − front [95% CI] | Change, published convention [95% CI] | Change, plane-corrected [95% CI] |
|---|---|---|---|
| Top, in | -0.767 [-0.935, -0.612] | -1.261 [-1.465, -1.077] | -0.495 [-0.615, -0.382] |
| Bottom, in | -1.106 [-1.238, -0.978] | -0.401 [-0.567, -0.243] | **+0.705 [0.620, 0.790]** |
| Half-width, in | +0.124 [-0.012, +0.254] | -0.154 [-0.308, +0.007] | -0.278 [-0.352, -0.199] |
| Area, sq in | +12.86 [6.25, 19.20] | -19.99 [-28.20, -12.99] | -32.85 [-36.64, -29.29] |

**The plane correction reverses the sign of the bottom-edge change.** In the published convention
the bottom edge moved down 0.40 in. Corrected to mid-plane, it moved up 0.70 in. Neither
interval includes zero. The corrected area contraction (-32.8 sq in) is about 1.6 times the
published-convention contraction (-20.0 sq in), and larger, not smaller. This is the situation
D-56 anticipated: no single scalar with a share in [0, 1] describes it. D-66 exists for the same
reason, because it provides a sign-reversal abstract variant.

### 2.2 Umpire heterogeneity (CH1-A6)

Source: `out/tables/T6_heterogeneity.csv` (W3.18). τ_ABS, the spread across umpires of the 2025
to 2026 response, has a median of 0.041 in (95% CI 0.002 to 0.100). P(τ ≥ 0.20 in) = 0.000, so
the spread is not material. The result is a bounded null with a one-sided 95% upper bound of
0.092 in. τ_buf is 0.056 in (95% CI 0.005 to 0.107). The split-half reliability of the response
is 0.169 (95% CI -0.272 to 0.457) over 88 umpires. D-60's curve shows the reliability gate is
not attainable, so no per-umpire table is published. F4 shows ranks only.

### 2.3 Framing by regime (W3.19, PASS receipt, qualified by its verifier)

Sources: `out/tables/ch1_framing_reliability.csv` and `out/tables/ch1_framing_by_regime.csv`.
The primary variant (count-specific, original) gives a 2026 − 2025 split-half reliability change
of -0.256 (95% CI -0.487 to -0.050). The verifier's qualification stands: "the reliability of
framing fell in 2026" holds in 1 of 4 variants. The other three include zero:
- flat/original: -0.126 [-0.295, +0.019]
- cnt/SIS: -0.091 [-0.240, +0.069]
- flat/SIS: -0.055 [-0.168, +0.069]

Framing validity (CH1-A11) passes. Across 2022-2024, r = 0.949 (95% CI 0.933 to 0.962) with
Savant `rv_tot`, n = 181.

### 2.4 Not estimated

- **AAA level difference-in-differences (W3.20): no estimate.** W3.20 is BLOCKED because D-11's
  2023 scan and D-57's 2024 changeover date have not landed (W2.8 and DT-29 belong to Phase 07).
  No DiD estimate, interval or pre-trend coefficient exists.
  `out/ch1/tab/aaa_did.csv` is absent. F5 is a placeholder.
- **Sealed-set prediction (W3.23, Phase 11): not run.** It runs once after 2026-11-01. F8 is a
  placeholder. Nothing here reads `out/sealed/`.

## 3. Sensitivity grid (W3.22, NOT PROVEN)

Source: `out/ch1/tab/sensitivity_grid.csv` (32 data rows; unverified). W3.22 has no receipt. Its
verifier REFUTED the step: `tests/testthat/test-ch1-sensitivity.R` fails at lines 171, 172 and
174, and W3.22 has no entry in `quality/steps.yml`. Treat what follows as unverified.
- **Sign flips: 0.** No component on area, top, bottom, half-width or shadow rate changes sign
  across the 31 computed rows. The `postseason_in` cell is deferred because the warehouse holds
  no 2022-2025 postseason called pitch.
- **20 cells lie outside the primary's interval.** Sixteen of them are not named in docs/ch1.md.
  Most compare the binned estimator against the bam primary, which is the CH1-A5 area gap again.
  Against the binned primary, `plane_front`, `r_0`, `shadow_2` and `shadow_4` move the shadow-rate
  and/or area components outside the interval, but none changes sign.
- **T8 is a placeholder** until W3.22 has a PASS receipt.

## 4. Acceptance criteria

Source: `out/tables/acceptance.csv` (14 rows, all evaluated, 2026-09-30).

| ID | Verdict | One line |
|---|---|---|
| CH1-A1 | PASS | Zone truth 99.9607% overall, 99.9868% outside ±0.5 in (hard gate) |
| CH1-A2 | PASS | 10,167 of 10,167 original calls recovered, 0 ambiguous (hard gate) |
| CH1-A3 | **FAIL** | P1 placebo: both TOST intervals lie outside their margins |
| CH1-A4 | PASS | All 12 component rows reported with 95% intervals |
| CH1-A5 | **FAIL** | Edges agree; area binned vs bam differs by -6.02 / -7.62 sq in |
| CH1-A6 | PASS | τ bounded null, not material; no per-umpire table |
| CH1-A7 | **FAIL** | Top-edge coverage 91/100 (bound 93); top null TOST 44/50 (bound 47) |
| CH1-A8 | PASS | SBC uniform (τ_abs p = 0.891, regime mean p = 0.770); L = 1,000 run due 2026-12-04 |
| CH1-A9 | **FAIL** | 0 sign flips over 31 rows, but not the whole multiverse; W3.22 unproven |
| CH1-A10 | **FAIL** | Not evaluable until W3.23 runs after 2026-11-01 |
| CH1-A11 | PASS | Framing r = 0.949 with Savant rv_tot |
| CH1-A12 | PASS | ABS-height coverage published before prereg-v1; D-13 decided |
| CH1-A13 | PASS | Plane component per edge with 95% intervals, plus the dz figure |
| CH1-A14 | PASS | Balanced-panel decomposition beside the headline, difference stated |

Result: 9 PASS and 5 FAIL. The two hard gates (A1, A2) pass. The closing clause also fails:
`make ch1 && make test-ch1` exits 0 but regenerates 0 figures and 0 tables, because
`scripts/ch1.sh` and `scripts/test_ch1.sh` are still W1.14 placeholder stubs. The second closing
clause, this memo's RESULT CALL line, is the owner item in section 8.

## 5. Pre-registered consequences that fired

1. **CH1-A3 FAIL: the chapter is descriptive.** Causal language was removed, and the P1 failure
   is the headline (headline.csv row 1). T5 reads `decomposition_reading = descriptive`. The scan
   found 0 causal claims. Recorded in DEV-77 and DEV-81.
2. **CH1-A5 FAIL on area: reported as a limitation, not resolved.** T4 carries
   `ch1_a5_within = false`, the limitation appears in docs/ch1.md, and the abstract is
   descriptive (DEV-81).
3. **CH1-A7 FAIL: the failure is reported as the finding, with an interval (SOP 9.6 item 8).**
   The top-edge caveat sits beside top-edge numbers and SENS-B1-UNDERSMOOTH beside the primary
   (D-R0-04, DEV-67, DEV-81).
4. **CH1-A9 FAIL: sign stability is stated over the 31 computed rows only.** `postseason_in` is
   reported as not run, and no whole-multiverse claim is made (DEV-81).
5. **CH1-A6 (PASS, but its consequence fired): no per-umpire table.** The D-60 curve shows the
   reliability gate cannot be attained (D-21). The bounded null is the result.
6. **CH1-A10: no consequence yet.** SOP 9.6 item 8 applies if the sealed rate falls outside the
   interval after W3.23.
7. **CH1-A11 PASS: framing stays primary.** The demotion did not fire.

## 6. Owner decisions raised (yes/no; SOP recommended default beside each)

These are raised, not decided. The artifacts above were built in the shape each default
describes. A "no" means rework, which is listed.

**D-56. The plane-correction estimand.** Is the plane correction reported per edge (top, bottom,
width)? Each edge would carry its own 95% interval and be defined as the velocity-and-break-
weighted shift at that edge. The share attributable to the plane would be allowed to exceed 1 or
change sign, and the `dz`-by-pitch-type figure would be published.
- *SOP default: YES.*
- *Why it matters now:* section 2.1 shows the bottom-edge sign reversal the SOP anticipated. A
  single scalar would misstate it.
- *If NO:* T4_plane_component, the A_CORR abstract slot and F2's plane bar need a scalar
  redesign, and CH1-A13's wording no longer applies.

**D-59. How share_ABS is reported.** Are Δ_buffer and Δ_ABS, each with a 95% interval, the
primary result? The share would be reported only when the 95% interval on Δ_ABS + Δ_buffer
excludes zero, and the IQR criterion would be replaced by sign stability on each component.
- *SOP default: YES.*
- *Why it matters now:* the sum excludes zero on all six estimands, so the share (area 0.586
  [0.527, 0.647]) is licensed today. Under the plane-corrected bottom edge, the components'
  signs differ from the published convention's.
- *If NO:* CH1-A9 reverts to the IQR criterion, and the grid summary must be recomputed.

**D-66. Heterogeneity and abstract-variant presentation.** Are the committed abstract variants in
`abstract/variants/` the only candidates? Those are main/owner, null-buffer, sign-reversal and a
fourth, descriptive, variant added per DECISIONS.md D-P4-44. Is the choice among them made at
review R1 as a result call, not a rewrite? And is heterogeneity presented as a bounded null (τ
upper bound 0.092 in), with ranks only and no per-umpire table?
- *SOP default: YES.*
- *Why it matters now:* CH1-A3 forces the descriptive reading, and section 2.1 shows a bottom-edge
  sign reversal. These point to the descriptive and/or sign-reversal variant, but choosing
  between them is the result call below.
- *If NO:* new abstract text has to go through the prose lint and the number tracer before any
  submission.

## 7. Phase exit artifacts

| Artifact | State |
|---|---|
| out/figures/F1-F4, F6, F7 + out/tables/F<n>_data.csv | Present and built (W3.24) |
| out/figures/F5 + F5_data.csv | **Placeholder**, blocked by W3.20 |
| out/figures/F8 + F8_data.csv | **Placeholder**, blocked by W3.23 (Phase 11, after 2026-11-01) |
| out/tables/T1-T7, T9 | Present and built; T7's sealed block pending W3.23 |
| out/tables/T8 | **Placeholder**, blocked by W3.22 (no receipt) |
| out/ch1/decision.md with RESULT CALL line | Present (this file); line awaits the owner |
| docs/ch1.md | Present; says aaa.md is absent |
| out/ch1/tab/sensitivity_grid.csv | Present, **unverified** (W3.22 refuted) |
| out/ch1/tab/aaa_did.csv | **MISSING** (W3.20 blocked) |
| out/tables/acceptance.csv | Present, 14 rows, 5 FAIL |
| Green CI badge, not presented as reproduction | README states "A green badge is not a reproduction", but **CI has never run**. Workflows are parked in ops/ci-pending/, and the gh token lacks the `workflow` scope (logs/evidence/W9.10.log, verdict FAIL) |

Step receipts: W3.19 PASS. W3.24 FAIL, on the completeness test naming F5, F8 and T8. W9.10
PASS, but that receipt covers only the static check; its clause 3 is unmeasured. W3.20 and W3.22
have no receipt.

## 8. RESULT CALL (OWNER)

The line below is the literal gate for Phase 14 (P8). Only Hudson writes it or approves it.
Agents must not fill it. An agent-written placeholder is not the owner's call.

RESULT CALL: descriptive. Placebo P1 failed (CH1-A3), so the 2025 and 2026 steps (-23.4 and -33.1 sq in, 95% CIs -28.3 to -18.6 and -37.5 to -28.7) are reported as departures from the 2022-2024 trend with no cause assigned, and the P1 failure is the headline; BREAK_YEAR 2025.

Approved verbatim by the owner, Hudson Pagni, on 2026-09-30T21:32:08+02:00 (Europe/Madrid), in answer to the question put to him by the main session; recorded as D-R0-05 in DECISIONS.md. No agent wrote or altered this line.
