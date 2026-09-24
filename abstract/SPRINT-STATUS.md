# SSAC sprint status

Owner: SOP section `W6`. One block per sprint checkpoint, each delimited by its own
markers so the checkpoints can be written independently. Numbers in this file are
generated, not typed: the generator for each block is named in the block.

<!-- W6.3:begin -->

## W6.3 The feeds and the challenges

Generator: `ops/sprint_feed_checkpoint.py`. Dependencies: W2.6, W2.13, W2.16.

The 2026 feeds are on disk and extracted, and the challenge counts
reconcile. 2,342 MLB regular-season game feeds are stored through the last
open day, every one of them extracted on the corrected pitch key, and
691,502 pitch-slot rows come out of them.

Reconciliation is a record difference, not a rate. The challenge table is
built from three JSON locations, each filtered to reviewType MJ and each
record counted once, and the total is compared game by game with the
`absChallenges` tally the feed carries in `gameData`. 10,168 records meet
10,168 tallies across 2,338 games, with 0 games not reconciling. Four games
carry no `absChallenges` block in either source and hold no challenge, so
they are reported as excluded rather than counted as reconciled.

| measure | value | source |
|---|---|---|
| feed games stored, MLB 2026 | 2,342 | `stg_feed_game` |
| feed pitch rows extracted | 691,502 | `stg_feed_pitch` |
| challenge records, reviewType MJ | 10,168 | `out/tables/challenge_reconciliation.csv` |
| gameData tallies | 10,168 | `out/tables/challenge_reconciliation.csv` |
| games reconciled | 2,338 | `out/tables/challenge_reconciliation.csv` |
| games not reconciling | 0 | `out/tables/challenge_reconciliation.csv` |
| DT-15, overturns reconstructed | 5,490 | `fct_challenge` |
| DT-08, modal allotment per team-game | 2 | `fct_team_game_tokens` |
| DT-08, allotment exceptions, each an audit row | 44 | `fct_team_game_tokens` |

DT-08 and DT-15 are refreshed here, not owned here. They are owned by
`tests/unit/test_challenges.py` and refreshed on the warehouse by
`tests/data/test_warehouse_pack.py`.

DT-15 is the one the floor reads. The overturn count is reconstructed from
`call_original`, which the feed does not state directly, and it comes to
5,490, the sum of `usedSuccessful` exactly. That number is what makes the
2026 original call usable: Statcast `description` and the feed's
`details.call` both record the post-challenge call, so an unflipped
challenge reads as a correct umpire call, and those pitches sit in the
shadow band where the contour is estimated, which is R-05.

DT-08 takes the starting allotment from the per-game maximum of `remaining`
observed across the play-by-play, not from the end-of-game block, which is
D-12 as R2 reversed it. The modal MLB 2026 allotment is 2, and
44 team-games depart from it. Each departure is enumerated as an audit
row, never silently dropped: the ones that read higher are extra-innings games, and
the ones with no allotment evidence are the same four games that carry no
`absChallenges` block.

Sprint floor, SOP section 4: this checkpoint settles the first of the three
items, the reconciled 2026 challenge counts. The zone gate is W3.8's and the
three-regime number with an interval is W3.16's.

<!-- W6.3:end -->

<!-- W6.4:begin -->

## W6.4 The corrected join

Generator: `ops/sprint_join_checkpoint.py`. Dependency: W2.15.

The corrected join is standing. The Methods sentence of the abstract reads
its two slots from `docs/numbers.json`, and they are filled: 1,492,502 called
pitches in 12,061 games, MLB regular seasons, open set, batters with an
ABS-measured height.

The correction is the flip of the overturned calls. Statcast `description`
and the feed's `details.call` both record the final call, so an unflipped
challenged pitch reads as a correct umpire call. Those pitches sit in the
shadow band where the contour is estimated, which is R-05. Every challenged
pitch in the mart carries `call_original`, `call_final` and `is_overturned`
as three columns, and no row disagrees with the rule in either direction.

| measure | value | source |
|---|---|---|
| join, MLB 2026 games | 2,342 | `out/tables/join_report.csv` |
| join, pitches matched both sides | 691,287 | `out/tables/join_report.csv` |
| join, rows unmatched either side | 0 | `out/tables/join_report.csv` |
| called pitches, ABS-measured height | 1,492,502 | `fct_called_pitch` |
| games behind that count | 12,061 | `fct_called_pitch` |
| DT-28, challenged pitches keyed | 10,168 | `stg_statcast_pitches` |
| DT-28, challenged pitches with no key | 0 | `stg_statcast_pitches` |
| DT-28, key shared with another called pitch | 18 | `stg_statcast_pitches` |

DT-28 is refreshed here, not owned here. It is owned by
`tests/data/test_join.py` and refreshed on the warehouse by
`tests/data/test_warehouse_pack.py`. The Savant ABS drawer that DT-28's
full clause needs is W4.2's pull and is not on this machine, so the clause
that requires a drawer row skips. What is measured instead is the bridge key
itself on the real corpus. Every challenged pitch has one. A small share of
them share that key with another called pitch in the same game, and the share
is published in the table above rather than assumed away.

That ambiguity does not reach the sprint. D-62 names the season-wide feed pull
as the fallback for the bridge, and the feed pull is already ingested on this
machine. The 2026 original call is reconstructed from the feed review records,
not from the drawer, so the drawer is a cross-check and not a dependency.

Open item for the sprint floor: the reconciled challenge counts are W2.16's,
the zone gate is W3.8's, and the three-regime number with an interval is
W3.16's. W6.4 states only that the join those three read from is correct.

<!-- W6.4:end -->
