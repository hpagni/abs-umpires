# The D-67 ordering and the abstract sentence

SOP step W6.6, the sprint view of W3.13 (milestone M1). Recorded `2026-09-30 04:45 CEST`, Madrid.

This file records which pre-registration sentence the SSAC abstract may carry. It checks the ceremony that W3.13 ran. It does not run it again.

## The choice

Chosen sentence: narrow.

> the sealed-set definition and acceptance criteria were committed publicly before the sealed set was opened

D-67 names this sentence for the case where the ordering was not achieved. The abstract carries it, with a capital first letter, in `abstract/ssac2027_abstract.md` and in both files under `abstract/variants/`.

The wide sentence is refused. It is the `WIDE` string in `tools/comms/fill_slots.R`, and it says the plan was committed publicly before estimation. For `prereg-v1` that is false.

## The rule

D-67 says: tag and push `prereg-v1` before the first Chapter 1 fit of any kind. GD-12 asserts that every fit receipt in `out/`, sealed or open, carries a `git_sha` that descends from the pushed tag. If that ordering is not achieved, the abstract uses the narrow sentence.

## What W3.13 achieved

- `prereg-v1` is the annotated tag object `980db5f` on commit `e438284` (before the 2026-10-01 message rewrite recorded in quality/commit-map-2026-10-01.json it was `a1b06d1` on `7c2add9`; same tree, same tagger date). The tagger date is `2026-09-30T04:17:58+02:00`.
- `git ls-remote origin` returns the same tag object and the same peeled commit. The tag is public.
- The W3.13 receipt reads PASS with exit 0. The W3.13 gate agent wrote its pass line.
- GD-12, `bash tools/comms/check_seal_order.sh`, exits 0. On `2026-09-30` it printed `SEAL-ORDER OK (0 fit receipts, prereg-v1 tagged at 7c2add9... (now e438284...), pushed=1)`.

## Why the ordering was not achieved

GD-12 counts files named `provenance.json` under `out/`. Before the tag there were 0 of them, so its pass tests no ordering. Chapter 1 fits did run before the tag. None of them wrote a `provenance.json`, so GD-12 cannot see them.

- The tagged `PREREGISTRATION.md` says so in its section on work before the freeze: "The fits listed above ran before it, on 2022–2024 calls and simulated calls."
- W3.4 fitted pooled contours on 2022–2024. Its first receipt, committed in `c01c931`, is stamped `2026-09-25 13:00:11 CEST` at `git_sha` `d8e0fe9`. Commit `d8e0fe9` does not descend from `prereg-v1`.
- W3.11 left 15 fit records in `out/dev/ch1_spec/`, written from `2026-09-25 14:53` to `2026-09-29 21:56` CEST. 11 of them fit 2022–2024 called pitches, at most 687,496 rows each. The other 4 fit simulated data. None carries a `git_sha`.

The first Chapter 1 fit ran more than four days before the tag existed. D-67 asks for the tag before the first fit "of any kind", and this record reads the 2022–2024 and simulated fits as fits. The ordering was not achieved, so the narrow sentence is the one the abstract may use.

The tagged pre-registration leaves one question to the owner: whether these fits count against D-67 (its list of items open at the freeze, the D-67 item). Until the owner rules in `DECISIONS.md`, the SOP default holds, and the default is the narrow sentence.

## What a later GD-12 pass does not change

The sealed fits will write `provenance.json` records that descend from the tag. GD-12 will then print a nonzero count that all descend, and `scripts/abstract.sh` will allow the wide sentence if `ABS_PREREG_SENTENCE=wide` is set. The fits above will still predate the tag. That later pass does not widen the claim.

The W6.6 check in `quality/steps.yml` fails if the wide sentence appears in `abstract/` or `submissions/`. It also recomputes each count in this file from its source.
