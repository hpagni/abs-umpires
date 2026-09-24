# Attribution

One section per source, each carrying the attribution string that source requires.
The code license is in `LICENSE`. The data notices and the redistribution posture
in full are in `DATA_LICENSE.md`. SOP step W2.21 fixes what this file must carry,
and `tests/unit/test_exports.py` asserts that each item below is still here.

Written 2026-09-24. Source terms read 2026-09-22.

## MLB Advanced Media

Schedule, feed and Statcast data comes from `statsapi.mlb.com` and
`baseballsavant.mlb.com` and is owned by MLB Advanced Media, L.P. The notice is
carried as MLBAM publishes it:

```
Copyright 2026 MLB Advanced Media, L.P.  Use of any content on this page acknowledges agreement to the terms posted here http://gdx.mlb.com/components/copyright.txt
```

That copyright text states its own limit. Only individual, non-commercial,
non-bulk use of the materials is permitted, and any other use needs prior written
authorization from MLBAM.

## Posture

This project is individual, non-commercial academic work. Every request goes
through `src/absump/http.py` or `R/lib/http.R`, which are the only two call sites
allowed to open a socket. Both read the per-host delay and the daily cap from
`config/throttle.yml` and from nothing else. `ops/lint_http.sh` refuses a commit
that adds a third call site. Pulls run a day or a game at a time, and a day
already cached is not pulled again. Raw responses stay in a private cache under
`data/`, which git ignores.

This repository redistributes no raw feed data. It publishes code and aggregates.
The aggregates live under `out/`, and `tests/unit/test_exports.py` fails the build
on any file there that carries a `game_pk` column beside a `pitch_number` or
`pitch_slot` column, and on any export past 50,000 rows. Anyone who wants the
underlying pitch data pulls it from the source, under that source's terms and
under a throttle of their own.

## Retrosheet

Play-by-play data for 2015 to 2025 comes from Retrosheet and is read as a
cross-check on the feed. The notice is carried verbatim from
`https://www.retrosheet.org/notice.txt`:

```
Recipients of Retrosheet data are free to make any desired use of
the information, including (but not limited to) selling it,
giving it away, or producing a commercial product based upon the
data.  Retrosheet has one requirement for any such transfer of
data or product development, which is that the following
statement must appear prominently:

     The information used here was obtained free of
     charge from and is copyrighted by Retrosheet.  Interested
     parties may contact Retrosheet at "www.retrosheet.org".

Retrosheet makes no guarantees of accuracy for the information
that is supplied. Much effort is expended to make our website
as correct as possible, but Retrosheet shall not be held
responsible for any consequences arising from the use of the
material presented here. All information is subject to corrections
as additional data are received. We are grateful to anyone who
discovers discrepancies and we appreciate learning of the details.
```

The statement that notice requires, carried prominently:

The information used here was obtained free of charge from and is copyrighted by
Retrosheet.  Interested parties may contact Retrosheet at "www.retrosheet.org".

## Baseball Savant

The ABS challenge leaderboard is published by Baseball Savant at:

```
https://baseballsavant.mlb.com/leaderboard/abs-challenges?level=mlb&challengeType=batter&season%5B%5D=2026
```

Credit to Baseball Savant for that leaderboard. Chapter 2 compares its own
shrunken challenger-skill estimates against the expectation columns published
there, and every such comparison names Savant as the source of the benchmark.

The metric definitions come from `baseballsavant.mlb.com/abs-metrics-documentation`:
Challenge Opportunity, Reasonable Pitch, Confidence Level, and the breakeven rule
for a challenge. Credit to Baseball Savant for those definitions. Where this
project uses a different definition, the difference is stated at the point of use
rather than left implicit.

## Phase 2 sources

Phase 2 scores game forecasts against closing lines and market prices. Nothing in
this section is published as raw odds or raw prices.

Pre-game and closing odds come from The Odds API at `api.the-odds-api.com`, under
a paid plan. Credit to The Odds API for those lines. Only de-vigged, derived
aggregates reach `out/`.

Market prices come from Kalshi. Credit to Kalshi. Kalshi market data is never
collected, cached, aggregated, stored or published beyond what the Kalshi
Developer Agreement permits for one's own trading.

Historical closing lines for 2010 to 2021 come from the SBRO archive. Credit to
SBRO for that archive.
