# Data contract

What this project reads, from where, and through what. The machine-readable
schema contracts are `contracts/*.yml` and their pandera schemas in
`contracts/schemas/`; this file is the prose side, and each source section is
written by the SOP step that owns that source. The published request policy is
`docs/legal.md`. Data ownership is `DATA_LICENSE.md`.

## HTTP delegation (W2.3)

W2.3 adds no client. Its content is the proof that there is only one.

Every pull in this repository, present and planned, goes through
`absump.http.get()` in `src/absump/http.py` or `absump_http_get()` in
`R/lib/http.R`. Both were written once, in W1.7. Both read `config/throttle.yml`
and nothing else. A pull that does not go through one of them is outside the
per-host delay, outside the daily cap, and absent from `data/raw/_manifest.csv`,
which is the audit trail the legal posture rests on.

### Every planned pull, and the client it uses

| Step | Source | Host | Client |
|---|---|---|---|
| W2.5 | Schedules and umpire assignments | `statsapi.mlb.com` | `absump.http.get()` |
| W2.6 | MLB 2026 game feeds | `statsapi.mlb.com` | `absump.http.get()` |
| W2.7 | Batter heights | `statsapi.mlb.com` | `absump.http.get()` |
| W2.8 | AAA feeds and the three scans | `statsapi.mlb.com` | `absump.http.get()` |
| W2.9 | Statcast MLB days | `baseballsavant.mlb.com` | `absump.http.get()` |
| W2.10 | Statcast AAA days | `baseballsavant.mlb.com` | `absump.http.get()` |
| W2.11 | ABS challenge leaderboard | `baseballsavant.mlb.com` | `absump.http.get()` |
| W2.12 | Retrosheet | `www.retrosheet.org` | `absump.http.get()` |
| W4.2 | Savant per-team drawer service | `baseballsavant.mlb.com` | `absump.http.get()` |
| W8.2 | Kalshi markets and candlesticks | `api.elections.kalshi.com` | `absump.http.get()` |
| W8.3 | SBRO 2010-2021 workbooks | Sportsbook Reviews Online | `absump.http.get()` |
| W8.5 | The Odds API historical and live odds | `api.the-odds-api.com` | `absump.http.get()` |

No step reads a second host, and no step opens its own connection. Steps that
consume what a pull produced (W2.13 through W2.22, and everything downstream of
W2.15) read the local cache and the warehouse, never the network.

`R/lib/http.R` exists for the R side of the same policy. Where an R script needs
bytes from a host, it calls `absump_http_get()`; it does not call `httr2`,
`curl`, `download.file` or `read.csv` on a URL.

### How the delegation is enforced

`ops/lint_http.sh`, written in W1.7, greps `src/`, `R/`, `tools/` and
`notebooks/` for the request idioms of both languages
(`requests.`, `httpx.get`, `httpx.Client`, `urllib`, `curl `, `httr2::request`)
and exits 1 on any hit whose path is not `src/absump/http.py` or
`R/lib/http.R`. W2.3 wires that script into `ops/lint.sh`, which is the body of
the `lint` target in the Makefile, so `make lint` fails on a second call site.
The wiring is hard: if `ops/lint_http.sh` is missing, `ops/lint.sh` fails rather
than skipping the check.

`tests/unit/test_http_delegation.py` (W2.3) asserts that the script is wired in,
that `docs/legal.md` publishes the same numbers the client enforces, and that
the linter exits 0 on the current tree.

### Known limit of the linter's scope

`ops/lint_http.sh` scans `src/`, `R/`, `tools/` and `notebooks/`. It does not
scan `ops/` or `scripts/`, which are shell. The SOP's one shell `curl` is the
monthly manual check of the CSAS 2027 conference page for its announced topic.
That is an owner's read of a web page, not a data pull: nothing it returns
enters `data/`, the warehouse or any model. If that check is ever automated, or
if any other shell script needs bytes from a host, it calls the Python client
through `uv run` rather than `curl`, or the linter's scan list grows to cover
it. Recorded here so the gap is known rather than discovered.
