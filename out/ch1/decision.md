# Chapter 1 decision memo (Phase 08, chapter1-full)

Refreshed 2026-10-01T06:17:51+02:00 (Europe/Madrid) by the Phase 08 owner-handoff writer, at HEAD
88974f0. It replaces the memo of 2026-10-01T03:25:36+02:00 written at b783719, and the DEV-89
amendment to it of 03:48:57. Since then DEV-89 has landed (a15d4cb, 5f9426f), W3.24 has built F5
and the F8 pending panel (DEV-90; 0102517 to be834ef), and CH1-A1 to CH1-A14 were re-evaluated at
be834ef (DEV-91, 88974f0). A third auditor then checked DEV-91
(`logs/evidence/CH1-acceptance-verify-3.log`, local, finished 06:11:55). Its findings are folded
in below. This memo decides nothing that is the
owner's to decide. Every number below is copied from a file on disk, named beside it. No agent's
prose is evidence: a step counts only when `scripts/prove.sh <step-id>` exits 0 and `make prove`
accepts `quality/receipts/<step-id>.json`.

## 1. What the chapter found

**The chapter is descriptive, not causal.** Placebo P1 failed (CH1-A3). No rule changed
between 2023 and 2024, yet the called zone grew +10.79 sq in (90% CI 7.73 to 13.94, margin
+/-3). The shadow-band strike rate rose +1.54 pp (90% CI 1.03 to 2.04, margin +/-0.5). Both
intervals lie wholly outside their equivalence margins. The pre-registered consequence converts
the three-regime decomposition into a description of what changed, and names no cause
(`out/tables/T5_placebos.csv`, `out/tables/headline.csv` row CH1_P1).

What is described. Between 2024 and 2026 the called zone contracted by 56.0 sq in (95% CI 52.0
to 59.6). Net of the 2022-2024 trend, the 2025 buffer-season step is -23.4 sq in (95% CI -28.3
to -18.6), and the 2026 ABS-season step is -33.1 (95% CI -37.5 to -28.7). The two steps are not
parts of the 56.0. The total also carries the trend term 2g, +0.51 sq in (95% CI -3.29 to 4.40),
so -56.02 = +0.51 - 23.43 - 33.10 (`out/tables/F2_data.csv`). The top edge came down, the bottom
edge came up and the zone narrowed. The shadow-band strike rate fell 10.7 pp.

P2 passed. The All-Star-break placebo: the headline 2026 area change (-33.10 sq in) exceeds the
95th percentile of |placebo| over five within-season boundaries (6.69 sq in). P2 also passed on
every edge. P3 (AAA, W3.20) passed for 2023 to 2024: the rule-net machine-day contour changed
by +0.36 sq in (90% CI -0.44 to +1.22; 95% CI -0.54 to +1.33). The 90% interval lies inside the
+/-3 margin of its two one-sided tests. The 2024 to 2025 change is not evaluable, because 2025
has no keyless full-ABS game on disk (`out/tables/aaa_placebo.csv`, DEV-87 item 4). Both copies
of T5 carry both P3 rows, read from that table (DEV-89). P4 was reported with no threshold.

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

Δ_total equals 2g + Δ_buffer + Δ_ABS on every row, so Δ_buffer + Δ_ABS differs from Δ_total by
the trend term. Arms beside the primary, all from the same file:
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
not attainable, so no per-umpire table is published. F4 is anonymised, but it does not show ranks
only: it draws all 88 per-umpire medians with 90% intervals on an inch axis (`docs/ch1.md`, F4
caption; DEV-85 item 6). Section 6.2 item 4 puts that to the owner.

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

### 2.4 The AAA arm (W3.20, PASS receipt, tracked, last proved at 44ebf0a)

Sources: `out/tables/aaa_placebo.csv`, `out/ch1/tab/aaa_withinweek.csv`,
`out/ch1/tab/aaa_pretrend.csv`, `out/ch1/tab/aaa_did.csv`, prose `out/ch1/prose/aaa.md` (DEV-87,
DEV-89). The DiD is a supporting arm. P1 failed, so every contrast is descriptive.
- **P3, the strongest use:** passed for 2023 to 2024 (section 1); 2024 to 2025 not evaluable.
- **Within-week alternation:** challenge-format minus full-ABS called-strike rate in the shadow
  band, same umpire-season and week, +4.23 pp (95% CI 3.52 to 4.94), pooled 2023-2024.
- **Level DiD, 2024 to 2025, area (primary: binned, 04-28 to 05-18 window):** -19.23 sq in (95% CI
  -27.45 to -9.30). **The pre-trend test fails:** 2023 to 2024 gives +16.82 sq in (95% CI +5.58
  to +27.79), which excludes 0, so the DiD is reported as descriptive. All four area pre-trend
  rows fail. The parallel-trends text is now a description, and it still names the assumption
  as strong (DEV-89 item 2).
- **F5 draws these tables (DEV-90).** Its top panel holds the six within-week rows. Its lower
  panels hold the pre-trend rows from MLB's binned series against the primary AAA window. Top
  edge +0.69 in (95% CI 0.50 to 0.94) and area exclude 0. Bottom edge +0.11 in (95% CI -0.17 to
  0.41) and half-width +0.10 in (95% CI -0.08 to 0.27) contain it (`out/tables/F5_data.csv`).
  No contour is drawn, because W3.20's committed outputs hold areas only.
- **Not estimated:** the 2025 to 2026 DiD, because no AAA 2026 feed is on disk and `data/raw/`
  belongs to Phase 07. The AAA 2024 pull is incomplete (696 of 2,232 Final games, through
  2024-05-18), so the arm should be rerun once Phase 07 completes 2024 (DEV-87 item 2).

### 2.5 Not estimated

- **Sealed-set prediction (W3.23, Phase 11): not run.** It runs once after 2026-11-01. F8 is a
  dated panel with status `pending` by design, not a placeholder (DEV-90). It reads no sealed
  datum. Nothing here reads `out/sealed/`.

## 3. Sensitivity grid (W3.22, PASS receipt at 031a5e1, qualified by its verifier)

Sources: `out/ch1/tab/sensitivity_grid.csv` (32 rows, untracked), `out/tables/T8_sensitivity.csv`
(333 rows, tracked) and `out/ch1/prose/sensitivity.md`. The W3.22 receipt is PASS. The verifier's
verdict is qualified, not refuted (`logs/evidence/W3.22-verify.log`).
- **31 of 32 rows computed:** 26 binned rows and 5 bam rows (primary, ABS-measured cohort,
  k = 0.75x, unweighted mix, front plane). `postseason_in` is deferred and disclosed by the
  owner's choice (D-R0-05 item 5): the warehouse holds no 2022-2025 postseason called pitch.
- **Sign flips: 0.** No 95% interval crosses zero for either component on area, top, bottom,
  half-width or shadow rate. Area Δ_buffer runs -29.72 to -22.22 and Δ_ABS -41.05 to -31.57 sq in.
  share_ABS is licensed in 31 of 31 rows.
- **Fewer distinct area estimates than rows.** On area, 14 of the 25 binned rows beside the binned
  primary equal it exactly, interval included (T8). So 17 of the 31 computed rows are distinct
  area estimates (auditor #3, finding F8).
- **Cells outside the primary's interval: none changes sign, and the prose names every one.**
  Against the bam primary, every binned row's area lies outside: the CH1-A5 gap again (binned minus
  bam -4.46 to -7.95 sq in across rows, T8). Against the binned primary, `r_0`, `shadow_2` and
  `shadow_4` move both shadow-rate components outside, and `plane_front` moves area and shadow-rate
  Δ_ABS outside.
- **Verifier findings.** (a) Still open: `sensitivity_grid.csv` and
  `out/tables/T8_sensitivity_data.csv` are untracked at HEAD, so a clean checkout cannot pass
  W3.22 again. (b) Closed by DEV-89 item 4: `docs/ch1.md` folds the current `sensitivity.md`, and
  the trace test reads its numbers. No test asserts the fold line by line, as one does for framing.
  (c) Still open: two of the verifier's mutants pass the gate, an edge sign flip (`k_1.5x` top
  Δ_buffer) and a bottom-edge interval crossing 0 (`band_6`). The prose's claim that edge and
  shadow signs are stable is therefore ungated.

## 4. Acceptance criteria

Source: `out/tables/acceptance.csv` (14 rows, tracked), re-evaluated at be834ef on
2026-10-01T05:40:04+02:00 and committed in 88974f0. DEV-91 supersedes DEV-88's table.

| ID | Verdict | One line |
|---|---|---|
| CH1-A1 | PASS | Zone truth 99.9607% overall, 99.9868% outside ±0.5 in; `11_zone_gate.R --check` rerun at HEAD (hard gate) |
| CH1-A2 | PASS | 10,167 of 10,167 original calls recovered (10,139 bridge, 28 feed fallback), 0 ambiguous; recounted from the pre-seal artifact (hard gate) |
| CH1-A3 | **FAIL** | P1 placebo: both TOST intervals lie outside their margins; the consequence is applied |
| CH1-A4 | PASS | All 12 component rows reported with 95% intervals |
| CH1-A5 | **FAIL** | Edges agree; area binned vs bam differs by -6.02 / -7.62 sq in |
| CH1-A6 | PASS | τ bounded null, not material; no per-umpire table |
| CH1-A7 | **FAIL** | Top-edge coverage 91/100 (bound 93); top null TOST 44/50 (bound 47) |
| CH1-A8 | PASS | SBC uniform (τ_abs p = 0.891, regime mean p = 0.770); L = 1,000 run due 2026-12-04 |
| CH1-A9 | **FAIL** | 0 sign flips over 31 rows; multiverse incomplete, `postseason_in` deferred (D-R0-05) |
| CH1-A10 | PENDING (sealed run after 2026-11-01) | Not evaluable before W3.23 runs; not a calibration failure |
| CH1-A11 | PASS | Framing r = 0.949 with Savant rv_tot |
| CH1-A12 | PASS | ABS-height coverage published before prereg-v1; D-13 decided; the D5 chronology is a finding with no consequence |
| CH1-A13 | PASS | Plane component per edge with 95% intervals, plus the dz figure |
| CH1-A14 | PASS | Balanced-panel decomposition beside the headline, difference stated |

Result: 9 PASS, 4 FAIL and CH1-A10 PENDING. The two hard gates (A1, A2) pass. CH1-A10 moved from
FAIL to PENDING because it cannot be evaluated before the sealed run (auditor #2, D6). No other
verdict changed, and every number a verdict reads is the one DEV-88 read.

Auditor #3 reproduced all 14 verdicts under its own code and found no threshold newly exceeded. It
refuted two statements in DEV-91, neither of them a verdict:
1. **D2 is not closed at HEAD.** `tests/guard/test_no_owner_address.py` lines 4 and 5 still carry
   two pre-rewrite commit ids that are keys of the DEV-86 map. Their translation sits in the
   working tree, uncommitted.
2. **CH1-A3's consequence is not complete across the tracked tree.** `docs/slide-requests.md` line
   92, a draft request to a speaker, still claims the study splits the 2025 grading change from
   the 2026 rollout. The reason DEV-89 and DEV-91 gave for leaving one word in the three abstract
   templates is also false. That word describes Lee et al.'s trend, and the README dropped it. The
   submission is built from the owner variant, and `submissions/ssac2027/abstract.pdf` does not
   carry the word.

The two closing clauses of SOP 9.2:
- **`make ch1 && make test-ch1`: met as worded, with F8 pending by design (DEV-90).** `make ch1`
  ran at be834ef from caches and exited 0. `make test-ch1` reported FAIL 0 and exited 0 there,
  and auditor #3 got the same at 88974f0. One defect survives the suite: T1 in `docs/ch1.md` is
  malformed (section 6.3, W3.24 lane).
- **The RESULT CALL line: present.** Section 8 carries the owner's line, unchanged since ecc2879.

## 5. Pre-registered consequences that fired

1. **CH1-A3 FAIL: the chapter is descriptive.** Causal language was removed, and the P1 failure
   is the headline (headline.csv row 1). T5 reads `decomposition_reading = descriptive`. DEV-89
   applied the consequence to `docs/prior-art.md`, the README and the AAA arm's parallel-trends
   text. Sections 1.3, 6.1 and 7 of prior-art.md now describe each step as measured against 2022
   to 2024, and they state the P1 failure. Two places remain (section 4, auditor #3 item 2; lanes
   in section 6.3). Recorded in DEV-77, DEV-81, DEV-83, DEV-88, DEV-89 and DEV-91.
2. **CH1-A5 FAIL on area: reported as a limitation, not resolved.** T4 carries
   `ch1_a5_within = false`, the limitation appears in docs/ch1.md, and the abstract is
   descriptive (DEV-81).
3. **CH1-A7 FAIL: the failure is reported as the finding, with an interval (SOP 9.6 item 8).**
   The top-edge caveat sits beside top-edge numbers, in the F5 caption too, and
   SENS-B1-UNDERSMOOTH sits beside the primary (D-R0-04, DEV-67, DEV-81, DEV-90).
4. **CH1-A9 FAIL: sign stability is stated over the 31 computed rows only.** The owner deferred
   `postseason_in` and had it disclosed beside CH1-A9 (D-R0-05 item 5). No whole-multiverse claim
   is made (DEV-81, DEV-85, `out/ch1/prose/sensitivity.md`).
5. **CH1-A6 (PASS, but its consequence fired): no per-umpire table.** The D-60 curve shows the
   reliability gate cannot be attained (D-21). The bounded null is the result.
6. **CH1-A10 PENDING: no consequence yet.** SOP 9.6 item 8 applies if the sealed rate falls
   outside the interval after W3.23.
7. **CH1-A11 PASS: framing stays primary.** The demotion did not fire.
8. **W3.20's pre-trend rule fired: the AAA level DiD is descriptive.** The 2023 to 2024 pre-trend
   interval excludes 0 on all four area rows, so the 2024 to 2025 DiD is reported as a difference
   of changes only (DEV-87, DEV-89, `out/ch1/tab/aaa_pretrend.csv`).

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
  them is a result call. Heterogeneity is a bounded null (τ upper bound 0.092 in), with no
  per-umpire table. The answer also says "ranks only"; section 6.2 item 4 asks how F4 meets it.
- **Postseason cell: deferred and disclosed.** CH1-A9 is reported as not met, with
  `postseason_in` named as the missing cell. No new ingest.
- **The RESULT CALL line** (section 8).

### 6.2 Still open for the owner (none blocks the Chapter 1 numbers)

1. **CI workflow scope (W9.10).** The question is whether you will run `gh auth refresh -h
   github.com -s workflow`, so that `ops/ci-pending/ci.yml` can move to `.github/workflows/ci.yml`.
   Recommended default: yes. Until then CI has never run, W9.10's third clause stays unmeasured,
   and the README's badge has nothing behind it. It never blocks the chapter.
2. **AI-assistance disclosure for SSAC.** The question is whether the SSAC 2027 rules require
   entrants to disclose AI assistance. Recommended default: read the rules on the form and the
   conference page before submitting, and follow them. The repository already records the assistance, in
   DECISIONS.md D-16 and DEV-86.
3. **The SSAC abstract submission.** The project works to 05:59 Madrid on 2026-10-02, the earlier
   reading of the posted deadline (`submissions/ssac2027/README.md`). No confirmation or receipt
   is on disk at HEAD. Recommended default: submit the committed `submissions/ssac2027/abstract.pdf`
   as it stands, then follow the README's after-submitting steps.
4. **F4 and "ranks only".** D-R0-05 item 4 says heterogeneity is shown as ranks only. F4, the
   SOP's caterpillar, draws the 88 anonymised per-umpire medians with 90% intervals on an inch
   axis, and its vector PDF carries those values (auditor #3, finding F5). Recommended default:
   keep the SOP's anonymised caterpillar, and have the W3.24 lane correct the "ranks only"
   sentence in `docs/ch1.md` to say what F4 draws. The alternative is a rank-axis redraw from the
   cached draws, which needs no fit.

Owner-visible, no answer needed unless the owner wants a change:
- **DEV-90's two departures.** F5 draws W3.20's tables without contours; an AAA contour fit would
  be a new fit. F8 is pending by design, so SOP 9.2's first closing clause is met with F8 pending.
- **DEV-85 items 7 and 8, two agent-applied defaults.** Doolittle's comparable is reported as not
  reproduced and not headlined. Framing's reliability reading names the three variants whose
  interval includes zero.
- **The RESULT CALL's wording of record.** PREREGISTRATION.md says the line is "written by the
  owner"; D-R0-05 records it as approved verbatim (auditor #3, finding F6). The call is decided and
  is not raised again. If the owner wants the record to match the prereg's word, he can commit the
  line himself.

### 6.3 Open for the agent lanes (not owner items)

- **W3.24 lane.** T1 in `docs/ch1.md` is malformed: its header row does not match its body rows.
  The cause is `R/ch1/71_tables.R` line 152, which indexes `md[[SEASONS[i]]]` by the integer season; T3 uses
  `as.character(s)`. The phase gate's own check reads FAIL on it (`logs/evidence/W3.24.log`,
  05:31). `make test-ch1` passes anyway, because the tracer at `tests/testthat/test-ch1-figures.R`
  line 58 skips leading-dot tokens. `out/tables/T1_sample_construction.csv` is correct. `make
  tables` rebuilds from caches and fits nothing. Three smaller items sit in the same lane. The F2
  alt text in `docs/ch1.md` presents Δ_buffer and Δ_ABS as summing to Δ_total without the 2g bar.
  The `make ch1` summary counts "figures 8 of 8" and leaves F2b out. Item 4 of section 6.2 follows
  the owner's answer.
- **W6.7 lane.** `out/tables/headline.csv` row CH1_W67 presents the two steps as parts of the
  56.0 sq in total, as section 1 of this memo did until this refresh.
- **W6.10 lane.** The three abstract templates (`abstract/ssac2027_abstract.md` and the
  null-buffer and sign-reversal variants) keep the word the README dropped from its description of
  Lee et al. They also say clubs "need that split".
- **W6.1 lane.** `docs/slide-requests.md` line 92 (section 4, auditor #3 item 2).
- **Main session.** Commit the translated ids in `tests/guard/test_no_owner_address.py`, which
  closes D2. The working tree also holds DEV-91's `make ch1` residue: nine figure PDFs that differ
  by CreationDate, two W3.24 provenance files and the W3.24 receipt re-stamped at be834ef.
- **W3.22 lane.** Commit `out/ch1/tab/sensitivity_grid.csv` and `out/tables/T8_sensitivity_data.csv`,
  and gate the edge and shadow sign claim against the two mutants in section 3.
- **W3.21 lane.** T5's 2025-minus-2024 P3 row reads `verdict = not evaluable` but
  `placebo_verdict = pass`, because `R/ch1/26_placebos.R` rolls the P3 verdict up across rows.
- **W3.20 lane.** Rerun the arm once Phase 07 completes AAA 2024.
- **W2 lane.** Point DT-29's DiD-frame clause at `out/ch1/tab/aaa_withinweek.csv` (DEV-87 item
  6). `tests/data/test_aaa_changeover.py` still says W3.20 is not built.
- **W3.6 lane.** `R/ch1/02_original_call.R` parses the team drawer files in full and drops rows on
  or after the seal only after parsing (auditor #3, finding F7). DEV-91 did not rerun it for that
  reason.

## 7. Phase exit artifacts

| Artifact | State |
|---|---|
| out/figures/F1-F7, F2b + out/tables/F<n>_data.csv | Present and built (W3.24); F4's sidecar is local by design (DEV-83) |
| out/figures/F5 + F5_data.csv | Built from W3.20's within-week and pre-trend tables, with no contours (DEV-90) |
| out/figures/F8 + F8_data.csv | Status `pending` by design until W3.23 runs after 2026-11-01 (DEV-90) |
| out/tables/T1-T7, T9 | Present and built; T7's sealed block pending W3.23; T5 carries both P3 rows (DEV-89); T1's CSV is correct, but its markdown in docs/ch1.md is malformed |
| out/tables/T8_sensitivity.csv | Present and built from W3.22's grid (333 rows, tracked) |
| out/ch1/decision.md with RESULT CALL line | Present (this file); the line is the owner's (D-R0-05) |
| docs/ch1.md | Present; folds the current framing, sensitivity and AAA prose; F5 and F8 text current (DEV-90); T1 malformed (W3.24 lane) |
| out/ch1/tab/sensitivity_grid.csv | Present, W3.22 PASS, **untracked** |
| out/ch1/tab/aaa_did.csv, aaa_pretrend.csv, aaa_withinweek.csv, out/tables/aaa_placebo.csv | Present and tracked (W3.20; parallel-trends text revised under DEV-89) |
| out/tables/acceptance.csv | Present and tracked, 14 rows: 9 PASS, 4 FAIL, CH1-A10 PENDING (DEV-91) |
| Green CI badge, not presented as reproduction | README states "A green badge is not a reproduction", but **CI has never run**. Workflows are parked in ops/ci-pending/, and the gh token lacks the `workflow` scope (owner item 6.2.1) |

Step receipts as committed at HEAD: W3.19 PASS at 031a5e1. W3.20 and W3.21 PASS at 44ebf0a, both
tracked. W3.22 PASS at 031a5e1. W3.24 PASS at af0f5b3; the phase gate's check reads FAIL on T1, so
W3.24 is not closed for the fleet. W9.10 PASS, but that receipt covers only the static check; its
clause 3 is unmeasured. W3.23 has no receipt.

## 8. RESULT CALL (OWNER)

The line below is the literal gate for Phase 14 (P8). Only Hudson writes it or approves it.
Agents must not fill it. An agent-written placeholder is not the owner's call.

RESULT CALL: descriptive. Placebo P1 failed (CH1-A3), so the 2025 and 2026 steps (-23.4 and -33.1 sq in, 95% CIs -28.3 to -18.6 and -37.5 to -28.7) are reported as departures from the 2022-2024 trend with no cause assigned, and the P1 failure is the headline; BREAK_YEAR 2025.

Approved verbatim by the owner, Hudson Pagni, on 2026-09-30T21:32:08+02:00 (Europe/Madrid), in answer to the question put to him by the main session; recorded as D-R0-05 in DECISIONS.md. No agent wrote or altered this line.
