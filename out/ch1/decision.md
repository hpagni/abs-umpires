# Chapter 1 decision memo (Phase 08, chapter1-full)

Refreshed 2026-10-01T03:25:36+02:00 (Europe/Madrid) by the Phase 08 owner-handoff writer, at HEAD
b783719. It replaces the memo of 2026-09-30T21:08:57+02:00 written at b9de83d (b9de83d after the
DEV-86 rewrite). Since then W3.20 and W3.22 have landed, CH1-A1 to CH1-A14 have been re-evaluated
(DEV-88), and the owner has answered the RESULT CALL, D-56, D-59, D-66 and the postseason cell
(D-R0-05). This memo reports and decides nothing that is the owner's to decide. Every number below
is copied from a file on disk, named beside it. No agent's prose is evidence: a step counts only
when `scripts/prove.sh <step-id>` exits 0 and `make prove` accepts `quality/receipts/<step-id>.json`.

## 1. What the chapter found

**The chapter is descriptive, not causal.** Placebo P1 failed (CH1-A3). No rule changed
between 2023 and 2024, yet the called zone grew +10.79 sq in (90% CI 7.73 to 13.94, margin
+/-3). The shadow-band strike rate rose +1.54 pp (90% CI 1.03 to 2.04, margin +/-0.5). Both
intervals lie wholly outside their equivalence margins. The pre-registered consequence converts
the three-regime decomposition into a description of what changed, and names no cause
(`out/tables/T5_placebos.csv`, `out/tables/headline.csv` row CH1_P1).

What is described. Between 2024 and 2026 the called zone contracted by 56.0 sq in (95% CI 52.0
to 59.6). Of that, 23.4 sq in (95% CI 18.6 to 28.3) falls in the 2025 buffer season and 33.1
(95% CI 28.7 to 37.5) in the 2026 ABS season. The top edge came down, the bottom edge came up
and the zone narrowed. The shadow-band strike rate fell 10.7 pp.

P2 passed. The All-Star-break placebo: the headline 2026 area change (-33.10 sq in) exceeds the
95th percentile of |placebo| over five within-season boundaries (6.69 sq in). P2 also passed on
every edge. P3 (AAA, W3.20) passed for 2023 to 2024: the rule-net machine-day contour changed
by +0.36 sq in (95% CI -0.54 to +1.33). The 2024 to 2025 change is not evaluable, because 2025
has no keyless full-ABS game on disk (`out/tables/aaa_placebo.csv`, DEV-87 item 4). P4 was
reported with no threshold.

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

### 2.4 The AAA arm (W3.20, PASS receipt at 694b593, verified PASS)

Sources: `out/tables/aaa_placebo.csv`, `out/ch1/tab/aaa_withinweek.csv`,
`out/ch1/tab/aaa_pretrend.csv`, `out/ch1/tab/aaa_did.csv`, prose `out/ch1/prose/aaa.md` (DEV-87).
The DiD is a supporting arm, not the identification. P1 failed, so every contrast is descriptive.
- **P3, the strongest use:** passed for 2023 to 2024 (section 1); 2024 to 2025 not evaluable.
- **Within-week alternation:** challenge-format minus full-ABS called-strike rate in the shadow
  band, same umpire-season and week, +4.23 pp (95% CI 3.52 to 4.94), pooled 2023-2024.
- **Level DiD, 2024 to 2025, area (primary: binned, 04-28 to 05-18 window):** -19.23 sq in (95% CI
  -27.45 to -9.30). **The pre-trend test fails:** 2023 to 2024 gives +16.82 sq in (95% CI +5.58
  to +27.79), which excludes 0, so the DiD is reported as descriptive. All four area pre-trend
  rows fail.
- **Not estimated:** the 2025 to 2026 DiD, because no AAA 2026 feed is on disk and `data/raw/`
  belongs to Phase 07. The AAA 2024 pull is incomplete (696 of 2,232 Final games, through
  2024-05-18), so the arm should be rerun once Phase 07 completes 2024 (DEV-87 item 2).

### 2.5 Not estimated

- **Sealed-set prediction (W3.23, Phase 11): not run.** It runs once after 2026-11-01. F8 is a
  placeholder. Nothing here reads `out/sealed/`.

## 3. Sensitivity grid (W3.22, PASS receipt at 031a5e1, qualified by its verifier)

Sources: `out/ch1/tab/sensitivity_grid.csv` (32 rows), `out/tables/T8_sensitivity.csv` (333 rows)
and `out/ch1/prose/sensitivity.md`. `scripts/prove.sh W3.22` exited 0, and the testthat file
printed 128 PASS, 0 FAIL (`logs/evidence/W3.22.log`). The verifier's verdict is qualified, not
refuted (`logs/evidence/W3.22-verify.log`).
- **31 of 32 rows computed:** 26 binned rows and 5 bam rows (primary, ABS-measured cohort,
  k = 0.75x, unweighted mix, front plane). `postseason_in` is deferred and disclosed by the
  owner's choice (D-R0-05 item 5): the warehouse holds no 2022-2025 postseason called pitch.
- **Sign flips: 0.** No 95% interval crosses zero for either component on area, top, bottom,
  half-width or shadow rate. Area Δ_buffer runs -29.72 to -22.22 and Δ_ABS -41.05 to -31.57 sq in.
  share_ABS is licensed in 31 of 31 rows.
- **Cells outside the primary's interval: none changes sign, and the prose names every one.**
  Against the bam primary, every binned row's area lies outside: the CH1-A5 gap again (binned minus
  bam -4.46 to -7.95 sq in across rows). Against the binned primary, `r_0`, `shadow_2` and
  `shadow_4` move both shadow-rate components outside, and `plane_front` moves area and shadow-rate
  Δ_ABS outside.
- **Verifier findings still open (they do not void the receipt):** (a) `sensitivity_grid.csv` and
  `out/tables/T8_sensitivity_data.csv` are untracked, so a clean checkout of 031a5e1 cannot pass
  W3.22 again. (b) `docs/ch1.md` still folds the prose from before 031a5e1 until the W3.24 lane
  re-runs `make tables`, and no test checks that fold. (c) Two of the verifier's mutants pass the
  gate: an edge sign flip (`k_1.5x` top Δ_buffer) and a bottom-edge interval crossing 0
  (`band_6`). The prose's claim that edge and shadow signs are stable is therefore ungated.

## 4. Acceptance criteria

Source: `out/tables/acceptance.csv` (14 rows, now tracked, re-evaluated at 694b593 on
2026-10-01T02:55:59+02:00; DEV-88 supersedes DEV-81's table). A second auditor reproduced all 14
verdicts and returned QUALIFIED (`logs/evidence/CH1-acceptance-verify-2.log`).

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
| CH1-A9 | **FAIL** | 0 sign flips over 31 rows; multiverse incomplete, `postseason_in` deferred (D-R0-05) |
| CH1-A10 | **FAIL** | Not yet evaluable (not a calibration failure); W3.23 runs after 2026-11-01 |
| CH1-A11 | PASS | Framing r = 0.949 with Savant rv_tot |
| CH1-A12 | PASS | ABS-height coverage published before prereg-v1; D-13 decided |
| CH1-A13 | PASS | Plane component per edge with 95% intervals, plus the dz figure |
| CH1-A14 | PASS | Balanced-panel decomposition beside the headline, difference stated |

Result: 9 PASS and 5 FAIL, the same verdicts as DEV-81. The two hard gates (A1, A2) pass. The
first closing clause is not met: `make ch1` regenerates every buildable figure and table but exits
3 on the F5 and F8 placeholders. `make test-ch1` reports FAIL 2, PASS 2003. One failure is W3.24's
completeness test. The other is the `docs/ch1.md` trace test: 34 numbers folded in from `aaa.md`
trace to no table in its pool (DEV-88). Both fixes belong to the W3.24 lane. The second closing
clause, the RESULT CALL line, is met: the owner approved it (section 8, D-R0-05).

## 5. Pre-registered consequences that fired

1. **CH1-A3 FAIL: the chapter is descriptive.** Causal language was removed, and the P1 failure
   is the headline (headline.csv row 1). T5 reads `decomposition_reading = descriptive`. The scan
   found 0 causal claims in the abstract, its variants and the README. **Not complete across the
   tree:** `docs/prior-art.md` (tracked, public) still says 2022-2025 "identifies the grading
   change" and 2025-2026 "identifies ABS net of it", at lines 137, 390, 393 and 519 to 522 (DEV-88,
   R1 open). Recorded in DEV-77, DEV-81, DEV-83 and DEV-88.
2. **CH1-A5 FAIL on area: reported as a limitation, not resolved.** T4 carries
   `ch1_a5_within = false`, the limitation appears in docs/ch1.md, and the abstract is
   descriptive (DEV-81).
3. **CH1-A7 FAIL: the failure is reported as the finding, with an interval (SOP 9.6 item 8).**
   The top-edge caveat sits beside top-edge numbers and SENS-B1-UNDERSMOOTH beside the primary
   (D-R0-04, DEV-67, DEV-81).
4. **CH1-A9 FAIL: sign stability is stated over the 31 computed rows only.** The owner deferred
   `postseason_in` and had it disclosed beside CH1-A9 (D-R0-05 item 5). No whole-multiverse claim
   is made (DEV-81, DEV-85, `out/ch1/prose/sensitivity.md`).
5. **CH1-A6 (PASS, but its consequence fired): no per-umpire table.** The D-60 curve shows the
   reliability gate cannot be attained (D-21). The bounded null is the result.
6. **CH1-A10: no consequence yet.** SOP 9.6 item 8 applies if the sealed rate falls outside the
   interval after W3.23.
7. **CH1-A11 PASS: framing stays primary.** The demotion did not fire.
8. **W3.20's pre-trend rule fired: the AAA level DiD is descriptive.** The 2023 to 2024 pre-trend
   interval excludes 0 on all four area rows, so the 2024 to 2025 DiD carries no causal reading
   (DEV-87, `out/ch1/tab/aaa_pretrend.csv`).

## 6. Owner decisions answered, and owner items still open

### 6.1 Answered on 2026-09-30T21:32:08+02:00 (D-R0-05); not to be raised again

The owner took the SOP default on each. The artifacts above were already built in that shape, so
no rework follows.
- **D-56, yes.** The plane correction is reported per edge with its own 95% interval. Its share
  may exceed 1 or change sign, and the dz-by-pitch-type figure is published (T4_plane_component,
  F2, F2b; section 2.1).
- **D-59, yes.** Δ_buffer and Δ_ABS, each with a 95% interval, are the primary result. share_ABS
  is reported only where the interval on their sum excludes zero. It does on all six estimands
  and in 31 of 31 grid rows. Sign stability per component replaces the IQR criterion.
- **D-66, yes.** The committed abstract variants are the only candidates, and the choice among
  them is a result call. Heterogeneity is a bounded null (τ upper bound 0.092 in), ranks only, no
  per-umpire table.
- **Postseason cell: deferred and disclosed.** CH1-A9 is reported as not met, with
  `postseason_in` named as the missing cell. No new ingest.
- **The RESULT CALL line** (section 8).

Two presentation defaults were applied by an agent in place of open Phase 08 questions, and the
owner may overturn either (DEV-85 items 7 and 8). Doolittle's comparable is reported as not
reproduced and not headlined. Framing's reliability reading names the three variants whose
interval includes zero. No answer is needed unless the owner wants a change.

### 6.2 Still open for the owner (none blocks the Chapter 1 numbers)

1. **CI workflow scope (W9.10).** The question: whether you will run `gh auth refresh -h github.com -s
   workflow`, so that `ops/ci-pending/ci.yml` can move to `.github/workflows/ci.yml`. Recommended
   default: yes. Blocked until then: CI has never run, W9.10's third clause stays unmeasured, and
   the README's badge has nothing behind it.
2. **The SSAC abstract form submission, due 2026-10-01** (abstract lane, open in D-R0-05). This
   memo cannot see whether it was sent. Recommended default: submit the committed abstract as it
   stands. Blocked until then: nothing in Chapter 1.

Not owner items. These are open for the agent lanes named:
- W3.24 lane: point F5 at the AAA arm (`R/ch1/70_figures.R` line 85 still marks it blocked); add
  the `aaa_*.csv` tables to the `docs/ch1.md` trace pool; re-run `make tables` so `docs/ch1.md`
  folds the current `sensitivity.md` and `aaa.md`. `out/tables/T5_placebos.csv` still says P3 was
  not run, and `docs/ch1.md` still calls the AAA arm blocked (second auditor, D1).
- W3.22 lane: commit `out/ch1/tab/sensitivity_grid.csv` and `out/tables/T8_sensitivity_data.csv`,
  and gate the edge and shadow sign claim against the two mutants in section 3.
- W3.20 lane: commit `quality/receipts/W3.20.json`, which is untracked. Rerun the arm once Phase 07
  completes AAA 2024.
- W2 lane: point DT-29's DiD-frame clause at `out/ch1/tab/aaa_withinweek.csv` (DEV-87 item 6).
- Main session: the 46 receipts re-stamped in the working tree by an interrupted `make prove`
  (same statuses, `git_sha` now 031a5e1) are uncommitted. 34 tracked `out/**/provenance.json` files
  still quote the pre-rewrite commit of `prereg-v1` (e438284, now e438284) in their `gd12` text
  (second auditor, D2). `docs/prior-art.md` keeps causal wording (section 5, item 1).

## 7. Phase exit artifacts

| Artifact | State |
|---|---|
| out/figures/F1-F4, F6, F7 + out/tables/F<n>_data.csv | Present and built (W3.24) |
| out/figures/F5 + F5_data.csv | **Placeholder**, although W3.20 has landed: `R/ch1/70_figures.R` line 85 still marks it blocked (W3.24 lane) |
| out/figures/F8 + F8_data.csv | **Placeholder**, blocked by W3.23 (Phase 11, after 2026-11-01) |
| out/tables/T1-T7, T9 | Present and built; T7's sealed block pending W3.23; T5 still says P3 was not run |
| out/tables/T8_sensitivity.csv | Present and built from W3.22's grid (333 rows, tracked) |
| out/ch1/decision.md with RESULT CALL line | Present (this file); the line is the owner's (D-R0-05) |
| docs/ch1.md | Present; folds pre-031a5e1 sensitivity prose and calls the AAA arm blocked until `make tables` is re-run (W3.24 lane) |
| out/ch1/tab/sensitivity_grid.csv | Present, W3.22 PASS, **untracked** |
| out/ch1/tab/aaa_did.csv, aaa_pretrend.csv, aaa_withinweek.csv, out/tables/aaa_placebo.csv | Present and tracked (W3.20, 694b593) |
| out/tables/acceptance.csv | Present and tracked, 14 rows, 9 PASS and 5 FAIL (DEV-88) |
| Green CI badge, not presented as reproduction | README states "A green badge is not a reproduction", but **CI has never run**. Workflows are parked in ops/ci-pending/, and the gh token lacks the `workflow` scope (owner item 6.2.1) |

Step receipts (working tree; the committed copies predate them): W3.19 PASS. W3.20 PASS at 694b593,
receipt untracked. W3.22 PASS at 031a5e1. W3.24 FAIL on the completeness test, which names F5 and
F8. W9.10 PASS, but that receipt covers only the static check; its clause 3 is unmeasured.

## 8. RESULT CALL (OWNER)

The line below is the literal gate for Phase 14 (P8). Only Hudson writes it or approves it.
Agents must not fill it. An agent-written placeholder is not the owner's call.

RESULT CALL: descriptive. Placebo P1 failed (CH1-A3), so the 2025 and 2026 steps (-23.4 and -33.1 sq in, 95% CIs -28.3 to -18.6 and -37.5 to -28.7) are reported as departures from the 2022-2024 trend with no cause assigned, and the P1 failure is the headline; BREAK_YEAR 2025.

Approved verbatim by the owner, Hudson Pagni, on 2026-09-30T21:32:08+02:00 (Europe/Madrid), in answer to the question put to him by the main session; recorded as D-R0-05 in DECISIONS.md. No agent wrote or altered this line.
