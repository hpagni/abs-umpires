# Warehouse

The warehouse for the ABS umpires project. One section per SOP step.

<!-- begin W1.10 target -->
## Target

SOP step W1.10. The warehouse target is MotherDuck Lite. The local dev target is
the DuckDB file at `warehouse/abs.duckdb`. Both targets run the same engine, so a
model that builds locally builds in the cloud without a dialect change.

### MotherDuck Lite, the free tier

Verified 2026-09-22 on the MotherDuck pricing page.

| Item | Lite |
| --- | --- |
| Price | $0 per organization per month |
| Storage | 10 GB free |
| Compute | 10 Pulse hours per month |
| Internal active users | 3 |
| Service accounts | 2 |

Past those limits the published rates are $0.043 per GB per month for storage,
$0.73 per Pulse CU-hour and $2.93 per Standard hour. The marts are 2 to 3 GB, so
they sit inside the free storage limit.

### Why not BigQuery

BigQuery gives the first 10 GiB of storage and the first 1 TiB of query bytes
free. It needs a billing account and a service-account JSON key. Its sandbox has
no DML, so dbt incremental models and merge are unusable there. MotherDuck wins
on two counts. Dev and prod are the same engine, and `dbt-duckdb[md]==1.11.0`
pins `duckdb==1.5.5`, the version already installed on this machine.

### Accounts

One service account for CI, one spare. Humans sign in with the personal login.

### The token

`MOTHERDUCK_TOKEN` carries the service token. It is named in `.env.example` with
no value, read from the environment at run time, and never written into
`dbt/profiles.yml.example`. The prod output sets `motherduck_token` from
`env_var('MOTHERDUCK_TOKEN', '')`, which is an empty string when the variable is
unset.

### Tests

Two tests, both from SOP W1.10:

```
dbt debug --target prod          # reports "Connection test: OK"
duckdb -c "ATTACH 'md:absump'; SHOW DATABASES;"   # lists absump
```

Both skip with a printed message when `MOTHERDUCK_TOKEN` is unset. A skip is a
pass. The dev target needs no token, so the rest of the project builds while the
prod target waits for one. The registered check for W1.10 in
`quality/steps.yml` reads the variable first and prints the skip line.

The dbt project lives at `dbt/dbt_project.yml` and belongs to SOP W1.11, which
runs after this step. While that file is absent, the prod `dbt debug` is skipped
with the same kind of message and is proved by the W1.11 gate instead. The
`duckdb` attach test still runs whenever the token is set.
<!-- end W1.10 target -->

<!-- begin W9.4 contract -->
## The contract

SOP step W9.4, SOP section 2.6. One set of table names, one grain and one key
per table, and the required columns of each.

The machine-readable copy is `quality/warehouse_contract.yml`. The checker is
`quality/verify_contract.py`. `make verify-contract` runs it through
`ops/verify_contract.sh` and exits with its exit code.

```
make verify-contract                                  # the report
sh ops/verify_contract.sh --json                      # the same report as JSON
sh ops/verify_contract.sh --database warehouse/abs.duckdb
```

### Tables

Twelve tables, the section 2.6 list. Each is a dbt marts model and materialises
as a table. Row counts are the dev build of 2026-09-24.

| Table | Grain | Key | Rows |
| --- | --- | --- | --- |
| `dim_game` | game | `game_pk` | 18,817 |
| `dim_umpire_game` | game | `game_pk` | 18,754 |
| `dim_player` | player | `player_id` | 1,482 |
| `dim_batter_season` | batter-season | `(batter, season)` | 3,189 |
| `dim_aaa_format` | game | `game_pk` | 6,755 |
| `fct_pitch` | pitch | `(game_pk, at_bat_number, pitch_number)` | 3,108,070 |
| `fct_called_pitch` | pitch | `(game_pk, at_bat_number, pitch_number)` | 1,610,220 |
| `fct_challenge` | challenge | `(game_pk, at_bat_number, pitch_number, review_level)` | 12,300 |
| `fct_challenge_opportunity` | pitch | `(game_pk, at_bat_number, pitch_number, acting_side)` | 716,922 |
| `fct_team_game_tokens` | team-game | `(game_pk, team_id)` | 4,684 |
| `fct_re288` | state | `(outs, base_state, balls, strikes)` | 288 |
| `fct_wp_state` | state | `(half_inning, score_diff, outs, base_state, count)` | 83,762 |

The required columns of each table are in the contract file and are not repeated
here. They are the section 2.6 cells, verbatim and in the order the SOP writes
them. `fct_called_pitch` inherits the `fct_pitch` list, as section 2.6 states it,
and adds eleven columns of its own.

The `agg_*` row of section 2.6 lists "the published aggregates listed per
chapter". No chapter has published an aggregate yet, so no `agg_` table is gated.
The checker lists what it finds. Today that is `agg_closed_season_rowcount` and
`agg_closed_season_drift`, the DT-20 ledger and its comparison, plus
`mart_called_pitches`, which is W3's alias for `fct_called_pitch`.

### Views

Four views, each restricted to the open rows of its base table:
`v_pitch_open`, `v_called_pitch_open`, `v_challenge_open`, `v_opportunity_open`.
Model code reads only these. The checker tests both halves of that claim. It
compares each view's row count against the same restriction applied to the base
table, and it reads the stored view definition and fails when the restriction is
not in it. The second half matters because the dev warehouse holds no held-out
row today, so a view with no restriction at all would match on counts.

### Columns not written yet

Six columns of the section 2.6 lists are declared and not built. Each is a
derived quantity whose definition a later SOP step fixes. A definition written
here would fix a pre-registered quantity that no step has agreed. The checker
reports these as DEFERRED. A column missing and not on this list is a failure.

| Table | Column | Owner | Why |
| --- | --- | --- | --- |
| `fct_called_pitch` | `count_class` | W3.7 | The count bins are fixed in W3.7, with the Chapter 1 analysis table. |
| `fct_called_pitch` | `pitch_group` | W3.7 | The pitch-group bins are fixed in W3.7. |
| `fct_challenge` | `sz_challenge_prob` | W4.2 | A Savant drawer field. No feed record carries it. |
| `fct_challenge` | `sz_challenge_runs` | W4.2 | A Savant drawer field, and the D-32 Tier 1 value metric. |
| `fct_challenge_opportunity` | `m_star_in` | W5.2 to W5.6 | The perception threshold comes from the W4 overturn model. |
| `fct_challenge_opportunity` | `g_wp` | W5.2 to W5.6 | The win-probability gain comes from the W5 surface. |

### DT-18, key uniqueness

Twelve declared keys, 0 duplicate groups. One key holds over part of its table.

`fct_challenge` carries 2,132 AAA 2024 reviews with a null `pitch_number`,
because no AAA 2024 Statcast day is on disk to match against. Two reviews in the
same at-bat then collide on the declared four-column key. Measured 2026-09-24:
53 groups, 54 rows above one, every one of them AAA 2024 with a null
`pitch_number`. The contract states the exception as a scope,
`pitch_number is not null`, and a surrogate, `challenge_uid`. The checker does
not take the scope on trust. It fails if a duplicate group exists inside the
scope, if a duplicate group outside the scope has every key column populated, or
if the surrogate repeats or is null anywhere.

### DT-19, referential integrity

Eight edges, 0 orphans. Three are the edges section 6.3 names.

| Edge | Named by the SOP | Null child key |
| --- | --- | --- |
| `fct_challenge` to `fct_pitch` on `pitch_uid` | yes | allowed |
| `fct_pitch` to `dim_game` on `game_pk` | yes | denied |
| `fct_pitch` to `dim_umpire_game` on `(game_pk, umpire_hp_id)` | yes | allowed |
| `fct_called_pitch` to `fct_pitch` on `pitch_uid` | no | denied |
| `fct_challenge_opportunity` to `fct_pitch` on `pitch_uid` | no | denied |
| `fct_team_game_tokens` to `dim_game` on `game_pk` | no | denied |
| `dim_umpire_game` to `dim_game` on `game_pk` | no | denied |
| `dim_aaa_format` to `dim_game` on `game_pk` | no | denied |

An orphan is a key that points at a row that is not there, not a key that was
never set. Where a null child key is allowed, a null is not counted. The 2,132
AAA 2024 reviews are the only such keys today, and `int_regime` asserts
separately that every MLB challenge resolves to a pitch.

DT-19 writes the umpire edge as `fct_pitch.umpire_id`. The column section 2.6
declares, and the one the build writes, is `umpire_hp_id`. The edge is checked on
the pair `(game_pk, umpire_hp_id)`, so the umpire named on a pitch must be the
home-plate umpire of that same game.

### The read rule

"Model code reads only the `v_*_open` views." The checker reads every file under
`R/`, `sql/`, `notebooks/`, `app/`, `src/absump/ch1/`, `src/absump/ch2/` and
`src/absump/ch3/`. It fails on a read that reaches a contracted fact table by
name unless the same statement restricts it to the open label. `dbt/` is not on
that list, because dbt is what builds the tables. Measured 2026-09-24: 4 files on
that surface, 0 direct reads. The surface is nearly empty because the chapter
code is not written yet, so this check gets stronger as the chapters land.

### How the checker names tables

Every table name, column name, key and edge comes from
`quality/warehouse_contract.yml` at run time. `quality/verify_contract.py`
carries none of its own. A table renamed in the contract is a table renamed in
the check.

That has a second effect, stated here rather than left to be found. GD-04 rule 3
fails a read of a raw fact table that the enclosing statement does not restrict
to the open label. The reads this checker issues are built from the contract at
run time, so no such read is written down for the scan to find. They are also
unrestricted on purpose. DT-18 and DT-19 are assertions about the whole table,
and a key check that skipped part of a table would assert nothing about that
part. The control on held-out rows is the seal, not this checker, and the
checker opens the warehouse read-only and writes no row.

### Source endpoints, pull dates and licence

The warehouse is built from the Parquet lake under `data/`, which is built from
two endpoints. The pull ledger is `out/tables/pull_ledger.csv`.

| Endpoint | Requests | Pull dates |
| --- | --- | --- |
| `https://baseballsavant.mlb.com/statcast_search/csv` | 803 | 2026-09-22 to 2026-09-23 |
| `https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live` and `/api/v1/schedule` | 3,021 | 2026-09-22 to 2026-09-23 |

Both are MLB Advanced Media. The notice is carried verbatim in `DATA_LICENSE.md`:

```
Copyright 2026 MLB Advanced Media, L.P.  Use of any content on this page acknowledges agreement to the terms posted here http://gdx.mlb.com/components/copyright.txt
```

Use is individual, non-commercial and non-bulk. Every request goes through
`src/absump/http.py` or `R/lib/http.R` under the `config/throttle.yml` policy.
Retrosheet supplies the RE288 inputs behind `fct_re288` under the notice in
`DATA_LICENSE.md`. The raw responses stay in a private cache under `data/`, which
git ignores under D-03.

### Rebuild

The rebuild-from-scratch clause of SOP section 9.1 belongs to W2.18, which
builds the tables. The row counts above are the ones a rebuild must reproduce.
`make verify-contract` is the check to run after one.

### With no warehouse

On a machine with no `warehouse/abs.duckdb` the checker reports SKIP for the
checks that read it, runs the two that read only the repository, and exits 0. A
clean clone with no data proves the half of the contract that is on disk.
<!-- end W9.4 contract -->
