# Legal posture and published request policy

This file states what this project sends to other people's servers, how often it
sends it, and what it does with what comes back. It is the published form of
`config/throttle.yml`. The code reads that file; this page restates it so the
policy can be read without reading code, and a test asserts the two agree.

Ownership of the data itself is a separate question and is covered in
`DATA_LICENSE.md`. Nothing here grants a right to the data.

## One client, two call sites

Every HTTP request this project makes is issued by one of two functions.

| Language | File | Entry point |
|---|---|---|
| Python | `src/absump/http.py` | `absump.http.get()` |
| R | `R/lib/http.R` | `absump_http_get()` |

Nothing else in this repository opens a connection. `ops/lint_http.sh` greps
`src/`, `R/`, `tools/` and `notebooks/` for the request idioms of both languages
and exits 1 on a hit outside those two files. `ops/lint.sh` runs it, and
`make lint` runs `ops/lint.sh`. A pull written outside the client fails the build.
It is not a review comment.

Both files read `config/throttle.yml` and nothing else. No delay, no daily cap
and no User-Agent string is written anywhere else in the repository.

## Rate policy

| Host | Delay between requests | Requests per day |
|---|---|---|
| `statsapi.mlb.com` | 4 s | 3,000 |
| `baseballsavant.mlb.com` | 10 s | 800 |
| every other host | 10 s | 500 |

"Every other host" is Retrosheet, Sportsbook Reviews Online, The Odds API and
Kalshi. The list with its per-host values is `config/throttle.yml`.

The delay is per host and is enforced between consecutive requests to that host.
It is not an average, and it is not shortened by a burst allowance. The daily cap
is per host per UTC day, counted in `data/raw/_budget.json`. When a host reaches
its cap the client raises `BudgetExceeded` and the run stops. It does not slow
down and continue.

4 s against `statsapi.mlb.com` is the published number because 0.5 requests per
second sustained for hours is what MLB's terms describe as automated bulk access.
The 10 s figure for `baseballsavant.mlb.com` stands on its own: Savant publishes
no rate limit and no service level, and the measured time to first byte on a
one-day CSV is about 7 s, so 10 s is close to serial anyway.

This project runs one request at a time. There is no parallel fetch, no
connection pool spread across hosts, and no second process pulling the same host.

## Identification

One User-Agent on every request, from both languages:

```
abs-umpires-research/0.1 (academic research project; polite single-day pulls; github.com/hpagni/abs-umpires)
```

It names the project, says what it is, and links to the source, so an operator
who sees it in a log can read the code that produced the request.

No email address is ever sent to any host. Not in the User-Agent, not in a `From`
header, not in a query parameter. The User-Agent is not rotated, not randomised
and not disguised as a browser. No proxy is used.

`Accept-Encoding: gzip, deflate` is sent on every request, which takes a large
share of the bytes off the origin's servers where the origin compresses.
`Accept: application/json` is sent to `statsapi.mlb.com`, which returns HTTP 406
without it.

## Failure handling

At most 4 attempts per URL, and only for a timeout or a 5xx. A 4xx is never
retried. HTTP 403 is fatal: the run stops, and the response is treated as the
host declining. Nothing in this project works around a 403, changes its headers
after one, or tries a second route to the same resource. Backoff between attempts
is exponential from a 4 s base.

## What is stored, and where

Every completed request appends one row to `data/raw/_manifest.csv`:
`fetched_at_utc, host, url, http_status, wire_bytes, disk_bytes, sha256,
attempt, elapsed_s, dest_path`. That file is the audit trail for this policy. It
is also the resume log: a URL already in the manifest is served from the local
cache and is not requested again. Re-running a pull does not re-pull.

Raw response bytes are written under `data/`, compressed, and never rewritten in
place. `data/` is excluded from git by `.gitignore`, a pre-commit hook refuses
any staged path under it, and a test asserts `git ls-files data/` is empty. No
raw third-party response is published from this repository, in any form, at any
time. What is published is code and derived aggregates, under the terms in
`DATA_LICENSE.md`.

## What this project does not do

It does not log in anywhere, create accounts, or send credentials. It does not
read anything behind a paywall or an authentication wall. It does not scrape
rendered pages where a documented endpoint exists. It does not run on a
schedule faster than the policy above. It does not redistribute raw material.

## If you operate one of these hosts

Open an issue at `https://github.com/hpagni/abs-umpires/issues` and this project
will stop pulling from your host, or slow down to whatever rate you name. The
throttle is one file and the change is one line.
