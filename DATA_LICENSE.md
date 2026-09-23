# Data license and notices

The MIT license in `LICENSE` covers the code in this repository. It does not cover
the data. The data this project reads is owned by third parties and is governed by
the notices below. Read this file before you clone, fork or re-use anything here.

## MLB Advanced Media

The following notice is carried verbatim, as MLB Advanced Media publishes it:

```
Copyright 2026 MLB Advanced Media, L.P.  Use of any content on this page acknowledges agreement to the terms posted here http://gdx.mlb.com/components/copyright.txt
```

That copyright text states its own limit:

> "Only individual, non-commercial, non-bulk use of the Materials is permitted and any other use of the Materials is prohibited without prior written authorization from MLBAM."

This project is individual, non-commercial academic work. It reads MLB Advanced Media
feeds through `src/absump/http.py` and `R/lib/http.R` under a per-host throttle with a
daily cap, at single-day and single-game granularity, and it re-pulls nothing. The raw
responses stay in a private local cache that git never sees.

## Retrosheet

The following notice is carried verbatim from `https://www.retrosheet.org/notice.txt`:

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

The information used here was obtained free of charge from and is copyrighted by
Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".

## No redistribution

This repository redistributes no raw feed data. It publishes code and aggregates only.
Nothing under `data/` is committed, in any form, at any time: `data/` is in `.gitignore`,
a pre-commit hook blocks raw rows, and CI fails the build if `git ls-files` returns a path
under `data/`. Published aggregates under `out/` are summaries, never pitch-level or
row-level dumps; `tests/unit/test_exports.py` enforces that mechanically. The private
cache and its mirror are not shared. Anyone who wants the underlying pitch data must pull
it from MLB Advanced Media, Baseball Savant or Retrosheet directly, under those sources'
own terms, using the throttle policy in `config/throttle.yml`. Kalshi market data is
never collected, cached, aggregated, stored or published here beyond what the Developer
Agreement permits for one's own trading.
