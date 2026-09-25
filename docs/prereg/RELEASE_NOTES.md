# Pre-registration v1.0

This release freezes the plan of the Umpires under ABS study before the sealed set is opened. The tag is `prereg-v1`. The tag message carries the freeze time in Europe/Madrid.

## What is frozen

- `PREREGISTRATION.md`, version 1.0: the design, the sealed set and every acceptance criterion, with its threshold and its test ids.
- Four annexes: `docs/prereg/ch1.md`, `docs/prereg/ch2.md`, `docs/prereg/ch3.md` and `docs/prereg/p8.md`.
- `docs/prereg/SEAL.md`, the seal log, and these notes. The seal log gains one line per seal event after the tag.
- `quality/prereg.lock`, the sha256 of each of those files at this tag.
- `quality/sql/analysis_set.sql`, the one predicate that defines the sealed set.

The release carries two files: `PREREGISTRATION.md` and `quality/sealed_manifest.json`.

## How to check it

```bash
git checkout prereg-v1
shasum -a 256 -c quality/prereg.lock
```

Every line should end in `OK`.

## The sealed set

MLB 2026 regular-season games with an official date on or after 2026-09-22, and every 2026 postseason game. `quality/sealed_manifest.json` lists 88 regular-season gamePks, from 2026-09-22 to 2026-09-27. Their `gamepks_sha256` is `ec40cdd5e643d478e54ff1f495281314a14353e525310b716f836a8ae399059e`. Before the unseal, one commit tagged `seal-postseason` adds the postseason gamePks and changes nothing else.

The seal is a passphrase on a single-user laptop, not a separation of duties. Opening it leaves a record: a git tag, a commit, and a line in `docs/prereg/SEAL.md`.

## What ran before this tag

The Chapter 1 specification was developed on 2022–2024 only. Every model fitted before this tag used 2022–2024 calls, simulated calls, or no outcome at all. `PREREGISTRATION.md` section 4 lists each fit and each read of 2025 or 2026 data.

The claim this release supports: the sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened.

## What is not in this release

- P8's full plan. Its own tag, `p8-prereg-v1`, freezes it later.
- Chapter 2's power grid. It had not run at this tag (`docs/prereg/ch2.md` section 10).

## After this tag

Every change to the plan is a dated entry in `docs/DEVIATIONS.md`, never an edit. A new version of the plan is tagged `prereg-v2`.

Data: MLB Advanced Media and Baseball Savant. Prior work: `AyanArora29/use-it-or-lose-it`, credited in `docs/prior-art.md`.
