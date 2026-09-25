# Pre-registration annex: Chapter 3

This is the Chapter 3 annex to `PREREGISTRATION.md`, version 1.0. It is frozen by the `prereg-v1` tag. After the tag, any change is a logged deviation in `docs/DEVIATIONS.md`, not an edit.

SOP step W7.6 wrote it from the SOP's W5 text and the owner decisions in `DECISIONS.md`. No Chapter 3 solve has run. The only Chapter 3 step with a receipt is SOP W5.1, the prior-art pin.

## 1. What was seen before this annex

No dynamic program, win-probability surface or overturn model for Chapter 3 has been fitted or solved. SOP W5.1 pinned 3 files of the prior art's published release (section 10). Their values are published numbers, listed in `docs/prior-art.md` section 1.1.

## 2. Framing

Chapter 3 is a replication. The single-side dynamic program is public, running, MIT-licensed and dated 2026-08-18 (`docs/prior-art.md` section 1.1). The chapter reproduces its published values as a correctness check. It then adds one thing: both teams' remaining challenges in the state.

It adopts the prior art's two-implementation standard, `dp.py` beside `dp_fast.py`. It also adopts their extras-grant encoding, applied to the stored value function. For SSAC, Chapter 3 is one paragraph and one table in the paper, not a section of the abstract.

It may not headline the capture ratio, the challenge card, the dump test, the value of a token in wins, or the rule counterfactuals. All five are published and dated 2026-08-18 (`docs/prior-art.md` section 7).

## 3. The rule

The MLB 2026 rule text, from the MLB press release, as SOP W5 quotes it:

> **Rule text, fetched from the MLB press release** (HTTP 200, 304,071 bytes, browser UA; `WebFetch` gets 406, use `curl -A`): "Each club will start the game with **two challenges, and all successful challenges are retained**." / "**Only the pitcher, catcher or batter** may challenge an umpire's call of ball or strike." / "**In each extra inning, a team will be awarded a challenge if it has none remaining entering the inning.**" / zone 17 in wide, middle of home plate, 53.5% top and 27% bottom of certified height. / "The entire process takes approximately 15 seconds." This is the MLB 2026 rule. The AAA allotment is a separate question, settled per season from the feeds and the MiLB rule sheet under D-12.

**Tokens, as measured.** MLB 2026 starts each team with 2 tokens. Of 4,684 MLB 2026 team-games, 99.1% start with 2 and 0.8% show a third. Every one of the third-token games went to extra innings, which is the published extras grant (D-P2-02). The extra-inning token is modelled in the dynamic program, as D-P3-07 requires, and the sample is not restricted to regulation.

**AAA.** The owner's answer D-R0-01 settles D-12: AAA carries two challenge tokens, and the AAA solve is 3x3. It replaces the SOP's `{0,1,2,3}` token range for AAA 2024. If a full AAA feed pull later contradicts it, that becomes a `docs/DEVIATIONS.md` entry with the measurement, not a silent reversal. The AAA arm is team-level only, because `reviewDetails.player` is absent from every AAA challenge record.

## 4. Notation and state space

SOP W5, verbatim:

> **Notation.** The valid half-inning index is `h = 1..24`, stated once here and nowhere else: `h` odd = top, `h = 2·inning − 1`, `h ≥ 19` extras, anything past the 12th collapses into `h = 24`. Arrays are shaped `(26, …)` with rows 0 and 25 as zero pads, **matching the prior art's layout exactly**. Row 25 is a pad and carries no assertion, so the extras-grant identity is asserted only at odd `h ∈ {19, 21, 23}`; the earlier statement that included `h = 25` contradicted the pad and is withdrawn. `d` = home minus away runs clipped to `[−D, +D]`, `D = 10` primary (21 buckets), `D = 6` (13 buckets) for the regression solve. Tokens `(t_H, t_A)` each in `{0,1,2}` for MLB and `{0,1,2,3}` for AAA 2024 under D-12. `V(h, d, t_H, t_A)` is expected incremental home WP attributable to both teams' remaining rights; zero-sum. `V(h, d, 0, 0) ≠ 0` because the extras grant has option value; their array gives `V(1, 6, 0) = 0.0942 pp`. **Standing:** a called strike is challengeable only by the batting team, a called ball only by the fielding team; asserted in code, not assumed. Extras grant applied to the **stored** value function: at odd `h ∈ {19, 21, 23}`, `V[h, :, 0, :] = V[h, :, 1, :]` and `V[h, :, :, 0] = V[h, :, :, 1]`.

Two settings differ from that paragraph. AAA tokens are `{0,1,2}` under D-R0-01. The horizon is `HMAX = 24` for the primary solve with `HMAX = 30` as a robustness row, and the score clip is `D = 10` with `D = 6` for the regression (D-39).

## 5. The mechanism, stated before any solve

SOP W5, verbatim:

> **The mechanism, stated up front so a null is interpretable.** With both teams' tokens in the state, the DP **separates into two independent one-sided DPs if** the opportunity arrival process and the payoff distribution are independent of the score path. That is a sufficient condition and is stated as one; the necessity direction is not established, is not needed for the argument, and is not tested. The condition fails here for two reasons: an overturn changes the score path, which changes `d`, which changes both `g` and the marginal token value; and the extras grant couples the two token axes to the same half-inning clock. Both channels are small. **A near-null is the expected result and is pre-registered as reportable. The contribution is the bound, not the effect.**

## 6. The solver

SOP W5.7–W5.8, verbatim:

> **W5.7–W5.8 The solver**, NumPy, no numba (the twin supplies the independent check). The recursion branches on which side owns each opportunity, because separate decrement of `t_H` and `t_A` is the whole content of the chapter:
>
> ```
> bat(h)  = A if h odd else H          # the away team bats in the top half
> fld(h)  = H if h odd else A
> side(j) = bat(h) if call_j == strike else fld(h)     # asserted, not assumed
>
> g_j             = ΔWP_home if the challenge succeeds   # always signed in home units
> g_j^{(H)} = g_j ;  g_j^{(A)} = -g_j                    # the acting side's own units
>
> MTV_H(h,d,tH,tA) =   V(h,d,tH,tA) - V(h,d,tH-1,tA)      # >= 0
> MTV_A(h,d,tH,tA) = -[V(h,d,tH,tA) - V(h,d,tH,tA-1)]     # >= 0
>
> challenge_j = 1  iff  p̂_j * g_j^{(side(j))}
>                       >  (1 - p̂_j) * MTV_{side(j)}(h, d, tH, tA)
> breakeven   p*_j = MTV_{side(j)} / ( g_j^{(side(j))} + MTV_{side(j)} )
>
> token update: t'_H = tH - 1{side(j)==H and challenge failed}
>               t'_A = tA - 1{side(j)==A and challenge failed}
>
> C(h,d,o,tH,tA) = mean over pooled continuations ω of [
>       Σ_{j ∈ ω} 1{challenge_j} · realized ΔWP_j        # home units, whoever acted
>     + V(h+1, d'(ω), t'_H(ω), t'_A(ω)) ]
> V(h,d,tH,tA) = C(h,d,0,tH,tA)
> ```
>
> `MTV_H` and `MTV_A` are both non-negative by construction because `V` is non-decreasing in `t_H` and non-increasing in `t_A`. The sign convention is explicit so that `dp.py` and `dp_fast.py`, written independently from these equations, implement the same model; MT-08's "two implementations agree < 1e-9" is otherwise a comparison of two different models.
>
> The game is **alternating-move, not simultaneous** — a given pitch is challengeable by exactly one side — so backward induction gives the exact subgame-perfect solution and no minimax fixed point is needed beyond the extras recursion. `V (26, 21, 3, 3)` f64 = 4,914 cells, 38.4 KiB; `C (26, 21, 3, 3, 3)` = 14,742 cells, 115 KiB; about 49 M vectorised operations per sweep; **under 30 s per solve.** The AAA 2024 solve at `(26, 21, 4, 4)` is 8,736 cells and stays under the same bound. `src/absump/ch3/dp_fast.py` is an independent numba 0.67.0 reimplementation written from the equations, not translated.

The AAA 2024 solve is 3x3 under D-R0-01, not the `(26, 21, 4, 4)` array the quote sizes.

`src/absump/ch3/dp.py` is the NumPy solver. `src/absump/ch3/dp_fast.py` is an independent numba reimplementation written from the equations above, not translated. MT-08 compares the two.

## 7. Inputs and windows

- **The win-probability surface.** The primary is a count-composed cube; a `HistGradientBoostingClassifier` is the comparator (SOP W5.2–W5.6). CH3-A3 sets its bar.
- **The overturn model.** It is wired from Chapter 2 through `absump.ch2.predict`. The self-contained pooled-probit fallback, `src/absump/ch3/perception_fallback.py`, is flagged in the write-up if it is used.
- **The half-inning pool.** It is keyed on `(h, d, outs)`. Cells with fewer than 200 opportunities are filled from 2015–2025, reweighted to the 2026 run environment.
- **Count and bases.** They enter only through each opportunity's `(g, p̂)` in the primary solve. A pitch-level exact solve is a conditional robustness solve (D-40).
- **The fit window.** 2026-03-25 to 2026-09-21. The sealed window is an out-of-sample policy-evaluation row, scored once (D-43).

## 8. Estimands, materiality and uncertainty

SOP W5.10–W5.16, verbatim:

> **W5.10–W5.16.** The 72-cell breakeven card (the prior art's 24 cells × `t_opp ∈ {0,1,2}`), each with a game-clustered bootstrap interval; `out/ch3/mtv_two_sided.csv` with the signed one-sided difference and an explicit `acting_side` column; the four policy cells **E** (two-sided vs two-sided), **BR** (two-sided vs observed), **O** (observed vs observed), **1S** (one-sided vs observed) replayed on the same streams, reporting `BR − 1S` (the promised-and-unproduced number), `E − BR` (the deferred second-order term), `O / BR` (the honest capture denominator), and the share of the ~342,000 opportunities where the two policies disagree, profiled by `(t_own, t_opp, inning band)`; **pre-registered materiality 0.05 pp per team-game**, about 2% of `V(2)`, below which the result is "the opponent's token count does not materially change the optimal policy, bounded at X pp with 95% CI [a, b]"; the continuation-after-flip bound (PA-truncated and full-resample, with the primary lying between them); the AAA arm sized from the scan at the allotment D-12 establishes per season, **team-level only** because `reviewDetails.player` is absent from all AAA MJ records; the benchmark table with every published number traced to a URL and an access date; 300 game-clustered bootstrap replicates through the full pipeline, CI width for `BR − 1S` ≤ 0.10 pp; and `docs/ch3.md` framed as a replication in its first paragraph.

The headline is best response. Every capture denominator is best response, and `E − BR` is reported beside it (D-38). The materiality threshold is D-42's 0.05 WP points per team-game, fixed before the solve runs. The bootstrap seed is `ch3_dp_bootstrap: 19730317` in `config/seeds.yml`. MT-08's determinism clause runs at `--seed 20260922`.

A near-null is the expected result and is pre-registered as reportable. The contribution is the bound, not the effect.

## 9. Acceptance criteria

Each criterion quotes its threshold from SOP section 9.4 byte for byte. `PREREGISTRATION.md` section 12.3 lists the same criteria. The test definitions are in `PREREGISTRATION.md` section 13.

### 9.1 CH3-A1, the BR-1 regression, a hard gate

Threshold, SOP section 9.4, verbatim:

> CH3-A1 the BR-1 regression passes at ±5e-5 WP on `V` and ±0.01 on the capture ratio (hard gate).

- Test ids: BR-1.
- Checked by: SOP W5.9.
- If it fails: a hard gate. The chapter does not ship. The diagnosis runs in order: the WP surface, then perception, then the pool, then the recursion (SOP W5.9).

### 9.2 CH3-A2, the invariance battery

Threshold, SOP section 9.4, verbatim:

> CH3-A2 the full invariance battery passes with zero unexplained violations, concavity violations confined to `h ∈ {19..24}`, the extras grant exact at odd `h ∈ {19, 21, 23}`, rows 0 and 25 still zero pads, and the antisymmetry test green on a symmetrised pool.

- Test ids: MT-08, UT-22.
- Checked by: SOP W5.8.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.

### 9.3 CH3-A3, the win-probability surface

Threshold, SOP section 9.4, verbatim:

> CH3-A3 the WP surface reaches r ≥ 0.837 / MAE ≤ 0.215 pp against `delta_home_win_exp` and r ≥ 0.998 against `home_win_exp`.

- Test ids: BR-3.
- Checked by: SOP W5.3.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.

### 9.4 CH3-A4, the two-sided difference and its interval

Threshold, SOP section 9.4, verbatim:

> CH3-A4 `BR − 1S` is reported with a game-clustered 95% CI of width ≤0.10 pp, whether or not it clears 0.05 pp.

- Test ids: none in the SOP.
- Checked by: SOP W5.15, 300 game-clustered bootstrap replicates through the full pipeline.
- If it fails: not a pass-or-fail gate on the sign. The interval width is the bar, and the difference is reported whether or not it clears 0.05 pp.

### 9.5 CH3-A5, the second-order term and the flip bound

Threshold, SOP section 9.4, verbatim:

> CH3-A5 `E − BR` and the continuation-after-flip bound are both reported.

- Test ids: none in the SOP.
- Checked by: SOP W5.11 and W5.12.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.

### 9.6 CH3-A6, the benchmark table

Threshold, SOP section 9.4, verbatim:

> CH3-A6 the benchmark table has no empty cells and every published number carries a URL and an access date.

- Test ids: none in the SOP.
- Checked by: SOP W5.14.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.

### 9.7 CH3-A7, the write-up frames a replication

Threshold, SOP section 9.4, verbatim:

> CH3-A7 `docs/ch3.md` frames the chapter as a replication in its first paragraph, headlines none of the five published results, and states the separation condition as sufficient rather than biconditional.

- Test ids: none in the SOP.
- Checked by: SOP W5.16. MT-08 tests the separation condition in the sufficiency direction only.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.

### 9.8 CH3-A8, determinism

Threshold, SOP section 9.4, verbatim:

> CH3-A8 `make ch3` reproduces every output deterministically with identical sha256 at a fixed seed, at whatever AAA dimension D-12 settles.

- Test ids: RP-07, MT-08.
- Checked by: `make ch3`; RP-07 and MT-08's determinism clause.
- If it fails: SOP section 9.6 item 8 applies: the failure is reported as the finding, with an interval.

### 9.9 The benchmark tests, BR-1 to BR-3

SOP section 6.5, verbatim:

> **BR-1 (hard gate, their inputs, their configuration):** `V[1,6,2] = 0.02482455 ± 5e-5`; `MTV1(h=1) = 0.015292 ± 5e-5`; `MTV2(h=1) = 0.008591 ± 5e-5`; `MTV2(h=17) = 0.004106 ± 5e-5`; `optimal 0.0256647`, `observed 0.0211942`, `oracle 0.0643381 ± 2e-4`, `card 0.0237931`, `naive50 0.0118465`, `late50 0.0038184`, `observed_model 0.0190900`, `never 0.0`, each ±5e-5; `capture_ratio 0.8258 ± 0.01`; `optimum/oracle 0.399 ± 0.01`; the re-solved array shape `(26, 13, 3)` element-wise within 5e-5 for all `h ≤ 18`.

> **BR-2 (our inputs, our pipeline), ≥7 of 8 inside tolerance:** V(2) 2.48 ±0.10 pp; MTV1 1.53 and MTV2 0.86 (inning 1) ±0.10; MTV2 0.41 (inning 9) ±0.10; optimum 2.57 ±0.15 pp; observed 2.12 ±0.10 pp; capture inside [0.797, 0.854]; counterfactuals 3.173 and 1.956 ±0.15 pp; **σ_bat 3.02 and σ_fld 1.90 ±0.15 in on the probit scale**. **Any miss is written into `METHODS.md` with the observed value and a hypothesis, never silently absorbed.** The receipt records the pinned release asset date the comparison used.

> BR-3: the WP surface reaches r ≥ 0.837 and MAE ≤ 0.215 pp against `delta_home_win_exp`, and r ≥ 0.998 against `home_win_exp`; the de-vigged market's own log loss on SBRO 2010–2021 lies in [0.64, 0.70] nats, computed on the post-`NL`-drop denominator.

SOP section 9.6 item 6 makes two of them conditions of project completion: BR-1 passes, and BR-2 reproduces at least 7 of its 8 published values.

## 10. Open before the tag

1. **The prior-art pin is partial.** SOP W5.1 names 7 files of snapshot A, 2026-09-22T14:34Z. 3 are pinned byte for byte: `dp_V_2026.npy`, `tier1_results_2026.json` and `tier1_card_2026.csv`. `dp_C_2026.npy`, `tier1_teams_2026.csv`, `tier1_mtv_2026.csv` and `perception_fit_2026.json` were replaced upstream on 2026-09-23 and are not on this machine (`fixtures/prior_art/uiloi/PROVENANCE.txt`).
2. **BR-1's own input is not pinned.** BR-1 re-solves on the prior art's `opps_2026.parquet`, which D-41 fetches on demand. Upstream rebuilds its release every night, and its 2026-09-24 build no longer matches snapshot A. That build already aggregates games inside the seal, so this annex does not report its drift in the published `V` (D-P4-20). A BR-1 run on a later `opps_2026.parquet` therefore compares a later input with snapshot A's values.
3. **The re-pin.** SOP W5.1 re-pins once after 2026-09-27 and records both snapshots. Snapshot B takes the four missing files.
4. **Criteria with no SOP test id.** CH3-A4, CH3-A5, CH3-A6 and CH3-A7 name the step that checks them. Assigning test ids is SOP W9.8 and W9.11 work.
5. **The AAA dimension.** The SOP text says 4x4 for AAA 2024. The owner's answer D-R0-01 says 3x3. This annex follows the owner.
