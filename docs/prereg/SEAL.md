# Seal log

SOP section 2.4, step W2.4. This file is the append-only record of every seal
event in this project: each time sealed data is encrypted, and the one time the
seal is opened.

Nothing has been sealed yet. As of 2026-09-23 this repository holds no MLB 2026
row of any kind, and the event log at the bottom of this file is empty.

## What is sealed

Only MLB 2026. AAA and MLB 2015-2025 are prior-regime data that the public
literature has had for months; sealing them would cost this project its own
training data and buy no credibility.

Within MLB 2026, a game is sealed if it is a regular-season game played on or
after 2026-09-22, or any postseason game: wild card, division, championship,
world series. Spring training, the all-star game and exhibitions are excluded
from the analysis entirely, in every season.

The rule lives in one place, `quality/sql/analysis_set.sql`, frozen at the tag
`prereg-v1`. `config/seal.yml` mirrors its constants for Python and R.
`tests/unit/test_seal_config_agrees.py` (UT-17) asserts the two agree case by
case, and `tests/unit/test_seal_classifier.py` (UT-16) asserts the rule itself.

Partitioning uses `gameData.datetime.officialDate`, never `gameDate`. Game
825030 is a 2026-09-15 game whose `gameDate` reads `2026-09-16T01:40:00Z`.
Partitioning on the UTC timestamp would put it on the wrong side of the seal.

The filter is on explicit game-type codes, not on a date alone. The 2024 and
2025 regular seasons started before spring training ended (2024-03-20 in Seoul
against a spring end of 2024-03-26; 2025-03-18 in Tokyo against 2025-03-25),
and spring 2025 ran an ABS trial in a subset of parks. A date-only filter would
leak treated games into the 2025 control regime.

## Where sealed rows live

Sealed game identity and outcome come from the schedule endpoint and land in
`dim_game` with the sealed label, because `GD-06` has to recompute the seal
manifest from `dim_game`. Sealed pitch and challenge rows are not materialised
into `fct_pitch` or `fct_challenge` until the unseal. Their raw feeds and CSVs
live in `data/sealed/`, encrypted. `data/` is gitignored and never enters git in
any form.

## What this guarantee is, stated plainly

The sealed archive is protected by a passphrase held in the owner's password
manager on a single-user laptop. That is all it is. It is not a separation of
duties, not an escrow, not a third-party timestamp, and not a custody chain. The
same person can decrypt the archive, edit the analysis and re-encrypt it. What
the seal actually buys is that opening it leaves a record: a git tag, a commit,
and a line in this file. The pre-registration says the same thing in the same
words. Overclaiming the guarantee is worse than the guarantee being modest.

## The encryption ceremony

Run from the repository root, once per seal event. The passphrase is typed by
the owner into `age`'s prompt and is never passed on a command line, never put
in a file, and never typed into a shell an agent can read.

    cd ~/sports-project
    tar -C data/sealed -cf - plain | age -p > data/sealed/sealed-mlb-2026.tar.age
    shasum -a 256 data/sealed/sealed-mlb-2026.tar.age | tee -a docs/prereg/SEAL.md
    rm -rf data/sealed/plain

Fallback if `age` cannot be installed, using the OpenSSL 3.6.3 already at
`/opt/homebrew/bin/openssl`:

    openssl enc -aes-256-ctr -pbkdf2 -iter 600000 -salt -in - -out data/sealed/sealed-mlb-2026.tar.enc

The `shasum` line above appends the ciphertext hash to this file on its own. The
operator adds the rest of the event by hand, on one line, in this form:

    SEALED | utc=<YYYY-MM-DDTHH:MM:SSZ> | madrid=<YYYY-MM-DD HH:MM TZ> | sha256=<64 hex> | games=<n> | dates=<first officialDate>..<last officialDate>

Use `TZ=Europe/Madrid date` for the Madrid stamp. Never hand-compute an offset
from UTC.

## The unseal

`make unseal` runs `ops/unseal.sh`. It refuses unless all three hold:

1. `PREREGISTRATION.md` is committed, meaning present at `HEAD`;
2. the tag `prereg-v1` is an ancestor of `HEAD`;
3. `git status --porcelain` is empty.

On success it appends one line to this file, in this form:

    UNSEALED | utc=<YYYY-MM-DDTHH:MM:SSZ> | madrid=<YYYY-MM-DD HH:MM TZ> | tag=prereg-v1 | commit=<40 hex> | head=<40 hex>

Passing that gate is necessary, not sufficient. Three further preconditions are
checked by `absump.seal._unlocked()` before any sealed row is read: the tag is
pushed and matches `origin`, `quality/prereg.lock` matches the tagged
pre-registration and its annexes, and the owner has set `ABS_SEAL_UNLOCK=1` in
one shell and appended a dated line to `DECISIONS.md`. No agent ever sets that
variable.

The unseal happens once. `ops/unseal.sh` refuses a second run against the same
tag rather than writing a duplicate line.

## Event log

One line per event, appended, never edited. Lines written by `shasum` carry the
hash and the path and nothing else; the operator's `SEALED` line and the
script's `UNSEALED` line carry the rest. Commit this file after every event.

No seal event has been recorded.
