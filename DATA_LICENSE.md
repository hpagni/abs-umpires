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

This project is individual, non-commercial academic work. Every request it makes goes
through `src/absump/http.py` or `R/lib/http.R`, which are the only two call sites allowed
to open a socket, and both read their per-host delay and their daily cap from
`config/throttle.yml` and from nothing else. `ops/lint_http.sh` refuses a commit that adds
a third call site. Pulls are made a day or a game at a time and a day already cached is
not pulled again. The raw responses stay in a private local cache under `data/`, which git
ignores.

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
Anyone who wants the underlying pitch data must pull it from MLB Advanced Media, Baseball
Savant or Retrosheet directly, under those sources' own terms and under a throttle of
their own. The private cache and its off-site mirror are not shared.

These are the controls that exist at this commit, and this paragraph claims no others.
`data/` is in `.gitignore`, together with `research/`, `logs/`, `sop/` and `fleet/`, and
the pattern is unanchored, so a directory named `data` anywhere in the tree is ignored too.
The two directories in the published tree that are named `data` and hold source rather than
data, `app/data/` and `tests/data/`, are re-included by name and by nothing broader. A
pre-commit hook, `ops/hook_no_raw_data.sh`, refuses any staged path under `data/`,
`research/` or `logs/`; it is configured in `.pre-commit-config.yaml` and installed by
`ops/install_git_hooks.sh`. `tests/unit/test_layout.py` asserts that the five ignored roots
are ignored and that `git ls-files` returns no path under any of them.

Planned controls, not in force yet and not to be relied on by anyone reading this file
today: the two GitHub Actions workflows parked at `ops/ci-pending/` fail a build whose
`git ls-files` returns a path under `data/`, and they move to `.github/workflows/` once
the repository's token carries the `workflow` scope (see `ops/ci-pending/README.md`); a
test at `tests/unit/test_exports.py` will assert that everything published under `out/`
is a summary rather than a pitch-level or row-level dump, and until it is written the
only thing keeping a row-level file out of `out/` is review, since `.gitignore` excludes
only the heavy formats there; and `ATTRIBUTION.md` will carry the per-source attribution
strings that this file states in prose.

Kalshi market data is never collected, cached, aggregated, stored or published here beyond
what the Developer Agreement permits for one's own trading.
