# Prior art

Scope: public work on the 2026 MLB ABS challenge system, on challenger skill, and on
change in the called strike zone under human umpires. Everything below was read at the
source and dated. Items marked [second-hand] were taken from another project's public
literature notes and were not read at the source.

Compiled 2026-09-22. Not re-verified since that date. Two upstream sources rebuild
nightly, so their numbers drift: `AyanArora29/use-it-or-lose-it` republishes a rolling
release every night, and `ilan-goodman/mlb-abs-xwpa` runs a nightly Action. Figures from
those two carry the date they were read.

Provenance. This file is the citable part of a longer working ledger. The raw ledger, the
dossier and the review notes stay out of this repository under decision D-03, because they
carry long quotations from paywalled sources. Every claim repeated here keeps the citation
that supports it. Nothing here is a number produced by this project.

This project's own claims and its list of things it may not claim are in section 7.

---

## 1. The nearest public work: `AyanArora29/use-it-or-lose-it`

Public repository, MIT licence, default branch `main`. Its README states: "Submission to
the MIT Sloan Sports Analytics Conference 2027 Research Paper Competition (Baseball
track). Author information is withheld from this README during blind review."

`METHODS.md` is a dated pre-registration, version v0.3c, 2026-08-18. Five commits, all
2026-08-17 and 2026-08-18. No code has been committed since 2026-08-18. A `nightly-rebuild`
workflow still runs and re-publishes every result to a rolling release tagged `data`, so
the outputs below are live through 2026-09-21 and were read on 2026-09-22.

### 1.1 Implemented and running

| Component | Published result (release `data`, read 2026-09-22) |
|---|---|
| Challenge extraction | ABS challenges are `reviewType` "MJ". 10,168 events over 2,342 games and 689,053 pitches, 2026-03-25 to 2026-09-21. Games not reconciling against `gameData.absChallenges`: 0. |
| Statcast join | Key `(game_pk, at_bat_number = atBatIndex + 1, pitch_number)`. Match rate 100.000% of feed pitches, of called pitches and of challenged pitches. |
| Zone truth | Any-part-of-ball rule, mid-plate plane, 53.5% and 27% of certified height, ball radius 1.45 in. Agrees with the ABS verdict on 99.75% of 10,155 challenged pitches, and 99.99% outside a plus or minus 0.5 in band (n = 7,538). Their pre-registered threshold was 90%. |
| Win probability | Count-composed cube: r = 0.837, MAE = 0.215 pp against the original call's change in win probability. Direct model: r = 0.702, MAE = 0.429 pp. Pre-pitch win probability against Savant `home_win_exp`: r = 0.9981. |
| Dynamic program | Value of two tokens at the first pitch of a tie game V(2) = 2.48 pp. Marginal token values MTV1 = 1.53 and MTV2 = 0.86 in inning 1; MTV2 falls to 0.41 by inning 9. |
| Policy comparison | 2,338 games, 341,865 opportunities. Information-constrained optimum 2.57 pp per team-game, about 4.16 wins per 162. Teams realised 2.12 pp, about 3.43 wins. Capture ratio 0.826, game-clustered bootstrap 95% interval [0.797, 0.854]. Optimum divided by oracle 0.399. |
| Challenge card | 24 cells: inning band by leverage tercile by plate-appearance-ending versus count-changing, for two tokens and for one, each with a bootstrap interval. |
| Perception | Pooled probit with cell thresholds: sigma_bat = 3.02 in, sigma_fld = 1.90 in. Hurdle variant: sigma_bat 2.76 with pi 0.782, sigma_fld 1.80 with pi 0.883. Two-way probit: bat sigma = 2.87 in over 324 players with player-effect SD 0.99 in; fld sigma = 1.86 in over 97 players with SD 0.43 in. Role overturn rates: catcher 58.8% (n = 5,376), batter 49.0% (n = 4,606), pitcher 39.3% (n = 173). |
| Reliability, weak form | Signal shares from a fixed-effects probit plus a method-of-moments correction. Catchers, at least 10 challenges, n = 92: threshold 0.80, overturn rate 0.33. Batters: 0.73 and 0.13. Between-team SD of the raw capture ratio 0.097, and 0.034 after empirical-Bayes shrinkage, against their own pre-registered threshold of 0.10. |
| Dump test | Overturn rate by tokens in hand in innings 9 and later: 0.449 with one token (n = 819), 0.366 with two (n = 716), against 0.558 and 0.565 before the ninth. Weighted dump index about 0.0000 to 0.0003 pp per team-game, which is a null. |
| Counterfactuals | Token counts one to four, retention on and off. Three tokens retained 3.173 pp; two tokens without retention 1.956 pp. |
| Robustness | 13 rows, including a leakage-free split fitted to 31 July and evaluated on August, capture 0.862. |
| Bootstrap | 100 game-clustered replicates of the full pipeline, including a perception refit and a re-solve of the dynamic program. |

Their own stated identification trap, which this project repeats in its limitations: the
capture ratio is a mechanical function of sigma, and sigma from a pooled probit is an
upper bound on perception noise.

### 1.2 Pre-registered but not implemented

Verified on 2026-09-22 by searching their `code/`, `tutorials/` and `.github/` trees for
the terms `gam`, `framing`, `umpire`, `placebo`, `count bias`, `rdd` and `discontinuity`.
There were no substantive hits.

1. Section 8, the entire umpire-response chapter. No GAM, no count-bias contrast, no 2026
   against 2025 fit, no 2024 to 2025 placebo, no regression discontinuity, no zone-geometry
   contour, no spring-2025 park comparison, no Triple-A rotation. Their own plan places it
   in the 4 December full paper, not the 1 October abstract.
2. Section 9, the entire framing chapter.
3. The two-sided dynamic program. `METHODS.md` says "opponent tokens t_opp treated as
   independent in the primary solution and included (3x3) as a robustness solve, reporting
   the difference". Their code carries own tokens only.
4. The rule-version table for Triple-A and spring training, described as "filled from
   documentation before use", was never written. Their Triple-A and spring arms are gated
   on it and were demoted to exploratory.
5. No Triple-A data of any kind is pulled. No minors Statcast, no `sportId = 11` feeds.
6. The 200-pitch manual audit against video-independent sources has no artifact.
7. Per-batter effective-height offsets, pre-registered as maximum likelihood with
   hierarchical shrinkage, are not implemented. The multi-season zone preparation module
   exists but nothing in their pipeline calls it.
8. The Tier-2 structural likelihood exists only as a file with a synthetic self-test.
   Production fits a binary probit with cell thresholds. The pre-registered
   simulation-recovery test, which their own methods say "must pass before Tier 2 is
   reported", has no artifact.
9. The promised hierarchical variance-components model with player and team random effects
   is not built. What runs is a fixed-effects probit plus a method-of-moments signal share.
   Player effects are computed in memory and only their standard deviation is exported.
10. Their claimed per-player reconciliation against Savant's ABS leaderboards is not
    supported by their own artifacts. Their download log records HTTP 500 on all 28
    `abs-challenges` CSV pulls, and the reconciliation lines are absent from their current
    verification report.
11. No benchmark against Savant's expected-challenge or expected-runs metrics anywhere.
    They downloaded the metric documentation and did not use it.
12. No calibration analysis of challenge success probabilities. Calibration and Brier
    scores appear in their repository only for the win-probability holdout.
13. Two independent implementations were promised for both section 3 and section 6. Only
    section 6 has a twin.

### 1.3 Their section 8 design, and its placebo problem

Their pre-registered primary estimand, verbatim: "change in the count-bias contrast,
P(strike | d = {-1, 0, +1} in, 3-ball) minus P(strike | same d, 2-strike), evaluated on the
fitted called-strike GAM surface, 2026 vs 2025, with 2024 to 2025 as the placebo pair (the
2025 evaluation-buffer cut from 2 in to 0.75 in and the 2026 zone redefinition are level
shifts to be reported, not absorbed)."

The problem is the placebo. A placebo pair is supposed to be untreated. The 2024 to 2025
pair is the treated pair for the grading change. The December 2024 umpire labor agreement
cut the grading buffer from two inches outside the zone edge to three-quarters of an inch on
either side of it. That change acts on the same borderline lean, conditional on count, that
their estimand measures.

Their own literature notes state the mechanism, dated 2026-08-17. On a grading tolerance of
plus or minus 0.75 in they write, verbatim:

> means there is no longer a penalty for calling a ball in the very interior

They also write that "the accountability shock we study in 2026 sits on top of a
2025 grading shock; identification must difference both". Their notes name the objection
directly: "Your
umpire-accountability effect is the 2025 grading-buffer change and the 2026 coordinate
change, not challenges."

This project is not first to notice that confound (lit/04, lit/06, lit/22 and
METHODS_REVIEW B5, dated 2026-08-17). It is public, in four of their literature files and
in their methods review. This project's claim is to resolve
it with a third, untreated baseline regime.

---

## 2. Public work on challenge strategy and challenger skill

### 2.1 TapToChallenge (Nate Burke), taptochallenge.com

The most complete independent public treatment. A live site, not a paper. It covers
challengers and umpires.

| Page | Date | Method | Result | Does not do |
|---|---|---|---|---|
| "Understanding the Run Value of ABS Challenges" | 2026-03-13 | RE288, defined as "3 out states x 8 runner on base states x 12 count states = 288 states"; empirical tally plus a Markov chain and Monte Carlo, "500,000 times per state". Breakeven is average cost divided by average cost plus swing. | Spring 2026: 51.7% win rate, 0.042 challenges per team per out, 0.181 runs per successful challenge. | Umpire identity. The page lists "Who is the umpire, and how often are they being challenged?" as future work. |
| "Understanding the Win Value of ABS Challenges" | 2026-03-21 | Win expectancy over "288 x 9 innings x 2 halves x 21 score differentials: 108,864 distinct game states", simulating 500,000 half innings from each of the 288 starting states. Opportunity cost keyed to outs and challenges remaining. | Mean win-probability added per overturn about 2% in close games and about 0.24% at seven runs or more. Call leverage index 1.58 on average, maximum about 30x. | No opponent tokens, no dynamic program, no stated validation, no intervals, no limitations section. |
| /umpires leaderboard | live | Per-umpire accuracy, expected accuracy, accuracy over expected, average miss distance, incorrect called strikes and balls, challenges faced, overturn rate, expected challenges, challenges over expected, win-probability added, average leverage index. | The only per-umpire ABS-era leaderboard found. | 2026 only. No zone geometry, no shrinkage, no cross-season contrast. |

### 2.2 `ilan-goodman/mlb-abs-xwpa` and ilangoodman.dev/mlb-abs-xwpa

Repository created 2026-05-01, last push 2026-09-22. No licence. Nightly GitHub Action.
Sources: the Savant ABS leaderboard, an undocumented Savant drawer service, and the Stats
API live feed.

Method: rebuild base, out, count and score state for each challenged pitch; fit a
season-to-date run-distribution win-probability model; take expected win-probability added
as win probability after the corrected call minus win probability after the original call,
from the challenging team's point of view. A proxy term converts Savant's lost-challenge
run penalty to wins "using a 10 runs-per-win rule of thumb".

Results read 2026-09-22: 1,928 regular-season challenges, 53.4% overturn rate, plus 1,890.4
expected win-probability points league-wide. Team leader CWS plus 1.135 challenge wins.
Catcher leader Edgar Quero plus 72.0; hitter leader Kevin McGonigle plus 17.7.

It also publishes a "challenged against" table for catchers and pitchers, with challenges
against, failed challenges against, the failed rate, and the win probability at stake.

Does not do: no decision model, no policy, no opponent tokens, no optimal stopping, nothing
on umpires. Self-described limits: "an independent model, not an official MLB or Statcast
metric", early-season noise in rare states, an unvalidated inventory penalty, and
incomplete catcher attribution on missed opportunities.

### 2.3 `channychanny/MLB-ABS-Optimal-Challenge-Strategy`

Created 2026-09-16, last push 2026-09-17. README in Traditional Chinese. Python standard
library only. Goal: maximise expected win probability under the two-token 2026 rule.

A data-feasibility gate passed on 2026-09-12 over 12 audited games, three each for Triple-A
2023, 2024 and 2025 and for MLB 2026. Its 61 attempts and 30 overturns reconcile exactly
with `gameData.absChallenges`.

One verified detail worth citing: when a challenge succeeds, the live feed stores the
corrected call in `details.call` and sets `reviewDetails.isOverturned` to true. The
umpire's original call is therefore the opposite of the stored call, and is not stored.

Does not do: the README states plainly that the dynamic policy is not finished and must not
be described as a result, and that no win-probability model has been trained or calibrated.
Opponent tokens are not in the state. No umpire work.

### 2.4 `cmartinez131/sabr-abs-challenge` (SABR Analytics 2026, student track SP7)

Christopher Martinez, Georgia Tech. Created 2026-01-12, last push 2026-08-28. The deck is
committed to the repository.

Data: Statcast June to September 2024. The author states: "Since the ABS challenge system
wasn't fully deployed in MLB during this period, I simulate challenge outcomes using pitch
location as ground truth."

Method: a Markov decision process solved by tabular Q-learning over about 2,500 states, with
inning bucketed, outs, count, runners, score differential, challenges remaining and distance
from the zone edge. Reward is the change in RE24 with a small penalty for a failed
challenge. Split by game, not by pitch.

Result: expected runs per game and projected wins. Q-learning 0.1146 and plus 1.86;
conservative coach 0.0584 and plus 0.95; situational threshold 0.0438 and plus 0.71; greedy
0.0365 and plus 0.59.

Does not do: the author lists simulated rather than real challenge outcomes as the first
limitation, and no pitcher or batter features. The reward is runs, not win probability. No
opponent tokens, no umpire analysis.

### 2.5 Tom Tango, tangotiger.com

Newest first. No ABS post exists on that site after 2026-08-31.

| Date | Title | Method | Result |
|---|---|---|---|
| 2026-08-31 | "Probably-Right Valuation for ABS Challenge Skill: Is JT the best, or worst, in the league?" | Four valuation tiers. The "probably-right" tier uses an ABS challenge model fitted on Triple-A 2025 and MLB 2026, adjusting for count, runners, outs and challenges remaining. Lost-challenge cost is outs remaining times 0.004 runs. | 4,716 overturns and 4,067 lost challenges through games of 29 August. Average 1.15 overturns per team per game. The average team left about 136 challenges unused. Average overturn 0.186 runs, or 0.135 unleveraged. |
| 2026-06-26 | "Creating a Naive ABS Challenge Strategy Model" | A threshold policy on inches from the zone by run value, with perception reverse-engineered: batters see strikes about 1 in inside, catchers about 0.6 in outside. | Best threshold at 0.10 runs per overturn: plus 0.39 runs per game on 3.2 challenges. Team range 33 runs down to 11. [second-hand] Explicitly omits count, inning, challenges remaining and leverage. |
| 2026-06-23 | "Do players think strategically when issuing an ABS Challenge?" | Success by run-impact bucket. | Pitchers 54, 31, 32, 15%; catchers 62, 62, 61, 48%; batters 50, 53, 41, 40%. [second-hand] No model. |
| 2026-04-02 | "ABS Challenge Run Values" | RE288 chart. | A strikeout turned into a 2-2 count is worth 0.93 runs. Nominal lost-challenge cost 0.2 runs. [second-hand] |
| 2026-03-25 | "ABS Challenge Rates by Proximity to Border of Strike Zone" | Tabulation by inches from the zone by count. | Catchers challenge 30 to 40% of misses of 3 in or more on the first pitch, against 70% of misses of 2 in or more on full counts. [second-hand] |
| 2026-02-15 to 2026-02-19 | "Cost/Benefit Analysis of Making an ABS Challenge", parts 1 to 3 | Breakeven equals cost divided by cost plus benefit, on RE12, RE24 and RE288. | Bases loaded and 3-2: be right about 10% of the time. Bases empty, two out, first pitch: about 88%. A second challenge is worth only 0.01 more than one. On an 0-0 count, plus 0.034 runs for a ball and minus 0.042 for a strike. [second-hand] No win probability. |
| 2025-11-29 | "Bayesian Strike Zone" | Conceptual only: the rulebook zone, the umpire's called zone on takes, and the batter's swing zone. | No data and no numbers. The post says it is "just laying my thoughts on the hope someone else picks up the baton". It is an open research prompt. |
| 2025-11-25 | "Statcast: Move over Framing Skill, make room for Challenging Skill" | Back-of-envelope arithmetic: about 75 takes and about 30 challengeable calls per game at about 70% umpire accuracy, so about 9 wrong calls per game. | Good framers are worth about plus or minus 120 calls a year, about 15 runs. A challenger improving from 50% to 55% gains about 0.2 to 0.5 corrected calls per game. Predicts framing value falls about 10% under ABS. No data, no model, no estimate of realised framing loss. |
| 2025-10-17, updated 2026-02-15 | "ABS Challenge Considerations" | A multiplicative expected-challenge model on side, proximity bucket, lost challenges remaining, outs remaining and leverage index, with later count and runner multipliers. | The design of Savant's expected-challenge model. [second-hand] A descriptive propensity model, not a policy. |

### 2.6 FanGraphs

| Author and post | Date | Data and method | Result | Does not do |
|---|---|---|---|---|
| Ben Clemens, "The Strike Zone Is Shrinking. Here's How." https://blogs.fangraphs.com/the-strike-zone-is-shrinking-heres-how/ | 2026-04-28 | Called pitches through 25 April in 2025 and 2026, restricted to batters appearing in both seasons, with 2026 official heights used for both years. Height-normalised vertical location, Nadaraya-Watson kernel regression on a 121 by 121 grid, 50% called-strike contour, 100 bootstrap resamples clustered by game, and inverse probability weighting for count splits. | The best public estimate of the 2026 change. Numbers are in section 6.3. | Does not correct for the plate-plane change described in section 6.4, and does not separate the 2025 grading change, because 2025 is its baseline. |
| Clemens, "An Early, Nerdy Look At The Challenge System" https://blogs.fangraphs.com/an-early-nerdy-look-at-the-challenge-system/ | 2026-04-01 | 227 challenges through 30 March, RE288 run values by leverage bucket. | 54% overall, 124 of 227. Catchers 57.6%, hitters 50.5%. Hitters challenge on 2.4% of low-leverage called pitches against 10.2% of high-leverage. Runs per high-leverage challenge 0.26 for hitters, 0.22 for catchers. | Rejects win probability outright: "Because you don't get to take your challenges home with you." Lists umpire identity among the questions he did not answer. |
| Davy Andrews, "Strike Zone Update Part 2: How the Zone Has Tightened" https://blogs.fangraphs.com/strike-zone-update-part-2-how-the-zone-has-tightened/ | 2025-05-06 | March and April 2024 against March and April 2025. Descriptive: shadow-zone accuracy and rates, heat maps. | The public source for the grading change. The buffer went from two inches outside the zone edge before 2025 to "three-quarters of an inch on either side" from 2025, under the new umpire labor agreement. Accuracy 92.53% in 2024 and 92.63% in early 2025. | Reports no zone-area or edge estimate in inches or square inches. |
| Andrews, "Your Final Pre-Robo-Zone Umpire Accuracy Update" https://blogs.fangraphs.com/your-final-pre-robo-zone-umpire-accuracy-update/ | 2025-11-20 | Full 2025 season, descriptive. | Record 92.83% overall accuracy. In-zone accuracy fell 1.7 percentage points and has fallen four straight years. 68% of calls were on pitches outside the zone. Shadow-zone accuracy 82.2% in MLB and 81.6% in the minors. The 2025 record came from calling more balls. | No per-umpire numbers at all. No zone geometry. |
| Andrews, "Do Catchers Challenge Well Where They Frame Well?" | 2026-06-10 | Statcast framing plus early 2026, about 10 catchers per framing-strength bundle. | Success about 10 points higher on the side where they frame worse, 63% against 51% at the top of the zone. [second-hand] | No shrinkage, small samples. |
| Andrews, "Maybe James Wood Just Thinks He Has a Really Tiny Strike Zone" | 2026-05-28 | Savant leaderboard, reasonable-challenge share and a spatial map. | Wood 3 of 13, 23%, against a league rate of 47%. Reasonable share 23% against 66%. [second-hand] | Year-to-year validity unknown. |
| Andrews, "Maybe There's No Such Thing as a Perfectly Fair Strike Zone" https://blogs.fangraphs.com/maybe-theres-no-such-thing-as-a-perfectly-fair-strike-zone/ | 2024-12-05 | Rulebook and ABS geometry. Area = (22.9 x (26.5% of height + 5.9)) - 7.4, with a ball diameter of 2.944 in. | A 6 ft 7 in batter gets 606.5 sq in against 527.7 sq in for a 5 ft 6 in batter, a gap of 78.9 sq in. | Geometry only, no called-strike data. |
| Kiri Oler, "Never Use an ABS Challenge in This One Weird Count" | 2026-06-22 | Savant through 20 June, RE288 buckets by three-inning blocks. | High-leverage pitches are under 10% of pitches but 15% of challenges, at 45.9% success and 0.49 runs per overturn. Low-leverage is 54.4% of challenges at 0.07 runs per overturn. [second-hand] | Rejects leverage index because challenges do not roll over, and ignores score differential. Does not quantify the cost of a failed challenge. |
| Michael Baumann, "Who's Getting Their Money's Worth From the ABS Challenge System?" https://blogs.fangraphs.com/whos-getting-their-moneys-worth-from-the-abs-challenge-system/ | 2026-08-11 | Through 9 August. Run value per successful challenge, by player and team. | Langeliers plus 7.19 runs on defense, 52 of 86. Raleigh plus 2.70. Wood minus 3.65. Minnesota 328 challenges and plus 33.6 runs. Cincinnati 0.114 runs per challenge on 263 challenges at 63.1%. Best-to-worst spread about one win. | No decision model. |
| Matt Martell, "To Challenge, or Not To Challenge, That Is the Question" https://blogs.fangraphs.com/to-challenge-or-not-to-challenge-that-is-the-question/ | 2026-06-19 | 40 interviews across nine teams: 27 players, 7 managers, 1 bench coach and club officials, plus compiled league challenge data. | League challenge rate 2.8% of called pitches. Bases loaded 5.1%, runners in scoring position 3.7%, no runners 2.4%. On 3-2 counts 9.4%, on 3-0 counts 2.0%. 77.4% of challenges come with a score differential of 0 to 3 runs. | Qualitative and descriptive. No model. |

### 2.7 MLB.com and Baseball Savant

- ABS metrics documentation, https://baseballsavant.mlb.com/abs-metrics-documentation.
  A challenge opportunity is "Any pitch where a player is allowed, by the rulebook, to make
  a challenge." A reasonable pitch is a challenge opportunity where the call was mistaken,
  or was correct but within 3 inches with a run value of at least plus 0.30 on RE288, or
  was correct but had a high challenge expectation. This page defines the expected-challenge
  and expected-runs metrics that this project benchmarks against.
- Mike Petriello, "Think you know who's been good at using ABS? It's not so simple",
  https://www.mlb.com/news/how-to-know-who-is-good-at-using-abs-2026-mlb, 2026-04-30. Model
  inputs, verbatim:

  > the location of the pitch and challenges remaining, as well as the leverage of the
  > situation (meaning runners on, score, inning, and ball/strike/out situation)

  The page requires a browser user agent; a plain fetch returns HTTP 406.
- Petriello, 2026-02-26, a Triple-A 2025 breakdown over about 861,000 pitches and 9,432
  challenges: about 50% overturn overall, batters 45%, fielders about 55%; 3% of
  challengeable pitches challenged; challenge rate rising from 2.1% to about 5% by late
  innings. 121 catchers with at least 10 challenges showed no framing-to-challenge
  relationship. [second-hand]

### 2.8 ESPN

Bradford Doolittle, "MLB 2026: What we've learned so far about ABS", 2026-05-19.
Descriptive, using Savant run values. Minnesota 124 challenges against Boston 63. Minnesota
and Colorado plus 4.4 runs above expectation; Texas minus 1.6. Carson Kelly 21 of 25, 84%,
plus 2.6 runs. Framing: the top 30 framers fell from 0.704 runs per 100 innings in 2025 to
0.565 in 2026, a drop of nearly 20%. In-zone pitch rate 47.3% in 2026 against 50.6% in
2025, a 17-season low. Walk rate 9.4%, the highest in more than 25 years. Aggregates only,
2025 against 2026, with no umpire-level estimate.

### 2.9 FanSided

Pete Dwyer, "ABS is changing MLB umpire behavior more than anyone expected", 2026-05-27,
https://fansided.com/mlb/abs-is-changing-mlb-umpire-behavior-more-than-anyone-expected.
A descriptive Statcast series, 2022 to 2026. Shadow-zone called strikes as a share of all
pitches: 2.3% in 2022, 2.1% in 2023, 2.1% in 2024, 1.6% in 2025, 1.5% in the first third of
2026. Chase-zone called strikes fell from 0.077% in 2022 to 0.032% in 2025 and 0.022% in
2026. His conclusion: "Umpires started calling fewer borderline strikes on their own in
2025." The piece never mentions the 2025 grading change, so it attributes the whole 2024 to
2025 move to anticipation of ABS. That attribution is untested.

---

## 3. Peer-reviewed and preprint literature

- Lee, K. and Ko, J., "Auditing Contextual Bias in Human Ball-Strike Calls Using KBO's
  Automated Umpiring Transition", arXiv:2609.03786, submitted 2026-09-03. KBO 2021 to 2026,
  with a human baseline in 2022 and 2023 and full ABS from 2024. Humans called 17.17
  percentage points fewer strikes at 0-2 and 6.61 more at 3-0, relative to 0-0. Both effects
  are about zero under ABS. A two-regime human-to-machine comparison in a league with no
  grading-buffer analogue.
- Lee, Han and Ko, arXiv:2407.15779, July 2024, revised December 2025. KBO, 2,515 games,
  human against ABS gray-zone calls. [second-hand]
- Hwang, Kim and Lee, Proceedings of the IMechE Part P, doi:10.1177/17543371251395162,
  2025-11-25. KBO 2021 to 2024, a game-level neural counterfactual. [second-hand]
- Song, Kang and Paulsen, European Sport Management Quarterly,
  doi:10.1080/16184742.2026.2681111, 2026-07-09. Player-level difference in differences on
  KBO 2023 against 2024, 148 batters and 112 pitchers. Full ABS hurt high-status batters
  relative to low-status. No pitch-level calls, no umpire heterogeneity. [second-hand]
- Post, R., Tang, J. and Zimmerman, D. L. (2025), "On the evolution of the accuracy,
  within-game consistency, and geometry of the called strike zone in MLB from 2008 to 2023",
  Journal of Sports Analytics 11, doi:10.1177/22150218251389237. 5,083,585 called pitches
  over 36,527 games. Accuracy rose from 85.5% in 2008 to 91.9% in 2023. Called-zone
  half-width fell from 1.106 to 0.907 ft and half-height rose from 0.860 to 1.001 ft, with
  area rising from 3.153 to 3.272 sq ft against a 3.004 sq ft rulebook zone. No umpire
  identifiers, and the series ends in 2023.
- Zimmerman, D. L., Tang, J. and Huang, R. (2019), "Outline analyses of the called strike
  zone in MLB", Annals of Applied Statistics 13(4), doi:10.1214/19-AOAS1285. PITCHf/x 2008
  to 2016, more than 3 million called pitches, elliptic-Fourier outline models with variance
  components. Verbatim: "We also establish that variation in the horizontal center, width
  and area of an individual umpire's CSZ pitch to pitch is smaller than variation among CSZs
  from different umpires." This is the peer-reviewed between-umpire variance result that
  Chapter 1 extends into the ABS era.
- Shinya, M. and Tomomura, M. (2026), "Bayesian sensory integration explains ball-count bias
  in MLB umpires", Research Square preprint, doi:10.21203/rs.3.rs-9598750/v1, posted
  2026-06-10. 450,460 called pitches from 2015 to 2024, four-seam right-on-right only, with
  per-umpire probit psychometric functions for 88 umpires. Higher sigma goes with a larger
  flat-count point of subjective equality displacement, r = 0.235, p = 0.029, and larger
  count bias, r = 0.220, p = 0.041. The authors propose a pre- and post-2026 comparison as
  future work.
- Flannagan, Mills and Goldstone (2024), Scientific Reports 14:2735. Hierarchical Bayesian
  psychometric fits on 3,001,019 pitches and 121 umpires, 2008 to 2015. [second-hand]

---

## 4. Umpire-accuracy sites

Umpire Scorecards, umpscorecards.com. Per-game accuracy, expected accuracy, consistency and
favor, with per-umpire and per-team pages. For 2026 it switched to the official ABS zone,
17 in wide with 53.5% and 27% height bounds and no tolerance. That dropped its own series by
roughly 1.5 to 2 percentage points and broke comparability with 2015 to 2025, because the
historical data was left on the old method. Its scorecards are computed on pre-challenge
calls. It publishes no zone-edge estimate.

---

## 5. Saberseminar 2026

Saberseminar 2026, 29 and 30 August, Illinois Institute of Technology, Chicago.
https://www.saberseminar.com/schedule/ publishes titles and speakers. It publishes no
abstracts. Four talks are in scope:

- [20] Ryan Ilan and Jordan Gottlieb, California State University Northridge, "When Should
  You Challenge? Estimating ABS Challenge Value Using Matchup-Level RE288 Projections".
  Public repository `rilan270/Matchup-Level-ABS-Challenge-Value`, RE288-based. [second-hand]
- [21] Sam Cowan and Ethan Cappelleri, Boston University, "Modeling ABS Challenges as
  Pitch-level State Transitions". No public materials found. [second-hand]
- [22] Steven Pappas and Gregory J. Matthews, Loyola University Chicago, "ABS Are Made in
  the Model: A Model-Based Analysis of Year One of the ABS Challenge System". Public
  repositories `spappas9000/abs_challenge`, a propensity model with RE covariates, and
  `gjm112/ABS_optimal_stopping`, which was still template stubs on 2026-09-13. [second-hand]
- [54] Aidan Gilbert, Syracuse University, "Quantifying Umpire Positioning and its Influence
  on Ball-Strike Decisions". No public materials found. [second-hand]

Recorded risk. Talks [21], [22] and [54] have no public abstract. Slides must be obtained
before this project makes any novelty claim about pitch-level state transitions or about
umpire-level ball and strike modelling. Requests to [21] and [54] are logged in
`docs/slide-requests.md`.

---

## 6. The regime question

### 6.1 Separating the 2025 grading change from the 2026 ABS effect

No published work separates the two. The evidence for that statement is the list below,
which is every public treatment of either transition found on 2026-09-22.

1. Clemens, FanGraphs, 2026-04-28, is the only published estimate of the 2026 zone change,
   and it is a 2025 against 2026 contrast. Because 2025 is its baseline, the grading change
   is differenced out by construction. The piece does not mention it.
2. Andrews, FanGraphs, 2025-05-05 and 2025-05-06, is the only published treatment of the
   grading change. It is descriptive, covering accuracy and shadow-zone rates for March and
   April 2024 against March and April 2025, and reports no estimate in inches or square
   inches.
3. Dwyer, FanSided, 2026-05-27, puts 2022 to 2026 on one axis and dates the shift to 2025,
   but never mentions the grading change, so the piece reads the 2024 to 2025 drop as
   anticipation of ABS.
4. Doolittle, ESPN, 2026-05-19, gives 2025 against 2026 aggregates only.
5. `use-it-or-lose-it` METHODS.md section 8, v0.3c, 2026-08-18, is the only design that
   tries. It is a 2026 against 2025 count-bias contrast with 2024 to 2025 as its placebo
   pair, and that pair is the treated pair for the grading change. It is scheduled for their
   4 December paper and has no output in their release as of 2026-09-22.
6. The KBO literature (Lee and Ko 2026; Song, Kang and Paulsen 2026) is a two-regime human
   to machine comparison in a league with no grading-buffer analogue.

### 6.2 Umpire-level heterogeneity in the response

No public work reports a per-umpire 2025 or 2026 zone change, a between-umpire standard
deviation of the response, or the reliability of it, as of 2026-09-22. The public work that
comes closest is listed here.

- TapToChallenge /umpires is the only per-umpire ABS-era leaderboard. It is 2026 only, with
  no zone geometry, no shrinkage and no cross-season contrast.
- Umpire Scorecards publishes per-umpire per-game accuracy, consistency and favor, but
  changed its zone definition for 2026 and publishes no zone-edge estimate.
- `use-it-or-lose-it` section 8 uses each umpire-season's own contour only to define
  borderline, and runs a within-umpire regression discontinuity on the next 20 called
  pitches after an overturn. That is within-umpire dynamics. Their plan has no umpire random
  effects.
- Clemens (2026-04-01) lists umpire identity among the questions he did not answer.
  Doolittle flags crew inconsistency. Neither measures it.
- The peer-reviewed antecedents are umpire-level but stop before these regimes: Zimmerman
  et al. 2019 (2008 to 2016), Shinya and Tomomura 2026 (88 umpires, 2015 to 2024, proposing
  2026 as future work), Flannagan et al. 2024 (121 umpires, 2008 to 2015). Post et al. 2025
  has no umpire identifiers and ends in 2023.

### 6.3 The best public numbers, by regime

2024 to 2025, the grading change. The December 2024 umpire labor agreement cut the buffer
from two inches outside the zone edge to three-quarters of an inch on either side of it.
Source: Andrews, FanGraphs, 5 and 6 May 2025, unless noted.

- Overall accuracy: 92.44% in 2022 [second-hand], 92.81% in 2023, 92.53% in 2024, 92.83% in
  2025.
- Shadow-zone accuracy: 81.8% in 2023, 81.3% in 2024, 82.2% in 2025. Minors 81.6% in 2025.
- In-zone accuracy fell 1.7 percentage points in 2025, its lowest since 2016, after falling
  four straight years. The 2025 accuracy record came entirely from calling more balls.
- Shadow-zone called-strike rate 42.7% in 2025, described as the lowest ever recorded, with
  44.9% of shadow pitches actually in the zone, a 10-year high.
- Shadow-zone called strikes as a share of all pitches: 2.3%, 2.1%, 2.1%, 1.6% for 2022 to
  2025 (Dwyer, FanSided, 2026-05-27).
- There is no public estimate of the 2025 change in inches of edge movement or in square
  inches of zone area. Andrews, the only source for that transition, reports neither
  (FanGraphs, 2025-05-05 and 2025-05-06).

2025 to 2026, the ABS challenge system. Source: Clemens, FanGraphs, 2026-04-28, through
25 April of each season, unless noted.

- Six-foot batter, top of zone: 3.448 to 3.475 ft, falling to 3.369 to 3.396 ft.
- Bottom: 1.514 to 1.541 ft, falling to 1.461 to 1.488 ft.
- Width: 1.725 to 1.775 ft, falling to 1.700 to 1.725 ft.
- Area: 448 to 460 sq in, falling to 435 to 442 sq in. The 95% interval on the change is
  minus 8 to minus 22 sq in, or 2 to 5%, with a point estimate near minus 14 sq in.
- 95% intervals on the edges: top minus 0.067 to minus 0.033 ft, bottom minus 0.033 to
  minus 0.017 ft, width minus 0.075 to 0 ft.
- Fastballs over the plate 0 to 4 in above the 53.5% line: called strikes fell from 54.3% to
  40.8%.
- Count-conditional, with inverse probability weighting: zero-strike counts 8% smaller,
  two-strike counts 1% smaller, three-ball counts slightly larger and indistinguishable from
  2025.
- Reverting all challenged calls to the umpire's original call moves the estimate only
  slightly, so the contraction is umpire behaviour rather than the overturns themselves.
- Supporting aggregates: in-zone pitch rate 47.3% against 50.6%, a 17-season low, and a walk
  rate of 9.4% (Doolittle, ESPN, 2026-05-19). Shadow-zone called strikes 1.5% of all pitches
  in the first third of 2026 (Dwyer).
- Framing: the top 30 framers fell from 0.704 to 0.565 runs per 100 innings, about minus 20%
  (Doolittle). Tango predicted about minus 10% in November 2025.

### 6.4 A measurement break in the public estimates

Statcast's `plate_x` and `plate_z` are measured at the front of the plate through 2025 and
at the middle of the plate from 2026. This is a project data fact recorded in
`docs/data-contract.md`, and it is corroborated by `use-it-or-lose-it` METHODS.md section
3.1, which propagates 2015 to 2025 coordinates forward and reports agreement with Savant's
2026 values to 0.001 to 0.002 in.

Clemens compares 2025 front-plane coordinates with 2026 middle-plane coordinates and applies
no propagation. His height normalisation correctly sidesteps a second break, that `sz_top`
and `sz_bot` are operator-set per pitch through 2025 and fixed at 53.5% and 27% of measured
height from 2026. The plane change is not sidestepped by height normalisation.

---

## 7. What this project claims as new, and the citation that bounds each claim

Each claim below names the public thing it must beat. The list of things this project may
not claim follows it. Both lists are binding on every human-facing artifact in this
repository.

Chapter 1, the headline.

- A third regime. `use-it-or-lose-it` METHODS.md v0.3c section 8 pre-registers a 2026
  against 2025 contrast whose only placebo pair is 2024 to 2025, which is the treated pair
  for the grading change. This project adds 2022 to 2024 under the earlier buffer of two
  inches outside the zone edge, so 2022 to 2024 against 2025 identifies the grading change
  on the same estimand, and 2025 against 2026 identifies ABS net of it, with a genuinely
  untreated placebo pair inside 2022 to 2024.
- Zone geometry as the headline quantity, in square inches and signed edge inches. Their
  section 8 demotes geometry to a secondary result and headlines the count-bias contrast.
- Umpire heterogeneity as an estimand, with shrinkage and reliability. Their per-umpire
  contour is a normalisation only, and the antecedents in section 3 stop in 2023 or earlier.
- The plate-plane correction of section 6.4, which Clemens (2026-04-28) does not apply.
- A Triple-A arm that is actually pulled, using the within-week format alternation. Their
  Triple-A arm is pre-registered, demoted to exploratory, gated on a rule-version table they
  never wrote, and has no data.

Chapter 2, challenger skill.

- Partial pooling, where theirs is a fixed-effects probit plus a method-of-moments signal
  share, although their METHODS.md section 5 promises a hierarchical variance-components
  model.
- A random effect for the player challenged against, which appears nowhere in their model or
  code.
- Split-half reliability reported beside variance components. Their METHODS.md section 5
  explicitly rejects split-half correlations.
- Calibration curves for the probability that a challenge succeeds. Calibration and Brier
  scores appear in their repository only for the win-probability holdout.
- A published leaderboard with shrunken estimates and intervals. They export only the
  standard deviation of the player effects.
- A benchmark against Savant's expected-challenge and expected-runs metrics, which they
  never attempt and whose documentation they downloaded and did not use.

Chapter 3, the dynamic program.

- Both teams' remaining challenges in the state, and the win-probability difference between
  the two-sided and one-sided solutions on the same 2026 streams. Their METHODS.md section 6
  promises exactly that comparison as a robustness solve and their code does not contain it.
- Presented as a benchmark replication first. The published values in section 1.1 are the
  correctness bar this project must reproduce before claiming any difference.

This project may not claim:

- Being first to notice the confound between the grading change and ABS. That is public and
  dated 2026-08-17 in four of their literature files and in their methods review.
- The count-bias contrast or the overturn regression discontinuity as new. Their METHODS.md
  section 8 pre-registers both.
- That challenge accuracy is mostly noise. Published: signal shares 0.80 and 0.33 for
  catchers, 0.73 and 0.13 for batters, team capture reliability 0.32, and a shrunken
  between-team SD of 0.034 against their own 0.10 threshold.
- A first perception-noise model or first role-level accounting (published 2026-08-18).
  Published: sigma_bat 3.02
  in and sigma_fld 1.90 in, the hurdle variant, the two-way probit, and the role overturn
  rates in section 1.1.
- The capture ratio, the challenge card, the dump test, the value of a token in wins, or the
  rule counterfactuals as headline results. All five are published and dated 2026-08-18.

---

## 8. Credit

The work in section 1 is the nearest public antecedent to Chapters 2 and 3 of this project,
and it sets the correctness bar for both. Its zone reconstruction, which agrees with ABS
verdicts on 99.75% of 10,155 challenged pitches, is the public benchmark that any zone truth
in this project must match or beat. Its dual implementation of the dynamic program is the
reproducibility standard this project follows.

Clemens (FanGraphs, 2026-04-28) is the public estimate of the 2026 zone change that
Chapter 1 is built to extend, and Andrews (FanGraphs, 5 and 6 May 2025) is the public record
of the grading change that Chapter 1 is built to separate from it. TapToChallenge and
`ilan-goodman/mlb-abs-xwpa` are the public leaderboards this project compares against.

Corrections to this file are welcome as issues on the repository.
