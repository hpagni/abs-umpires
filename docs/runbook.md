# Runbook

Operating notes for abs-umpires. Each section is written by the SOP step that owns
the procedure it describes.

<!-- W1.16: scheduled-workflow disablement -->

## Scheduled workflows on a public repository

Owner: SOP step W1.16. Related: D-08, D-09, R-32.

This repository has no `nightly.yml`. The nightly run is local, described in SOP
section 2.8. The rest of this section is recorded because it stays true for any
Actions cron added later.

GitHub's documented behaviour, quoted exactly: "In a public repository, scheduled
workflows are automatically disabled when no repository activity has occurred in
60 days".

Three further facts about `schedule` triggers:

- They run on the default branch only. A cron on a feature branch never fires.
- Their times are UTC. There is no local-time option, and no daylight-saving
  adjustment.
- A run can be delayed at the start of every hour, when the shared runner queue is
  busiest. Do not schedule work that has to start on the minute.

Re-enable a disabled workflow with:

    gh workflow enable <name> --repo hpagni/abs-umpires

Do not add a synthetic keepalive commit to keep a schedule alive. It pollutes the
history the seal depends on.

Calendar entry, 2027-02-15: check whether any scheduled workflow exists and is
still enabled. The gap between the end of the postseason and the start of spring
training is about 15 weeks, which is longer than the 60-day window.

<!-- W6.1: SSAC abstract deadline in both zones -->

## SSAC 2027 abstract deadline, in both zones

Owner: SOP step W6.1. Related: W6.12, R-27.

The conference page states the abstract deadline as **Oct. 1, 2026 11:59 p.m. EST**,
verified from sloansportsconference.com on 2026-09-22. That string is ambiguous, because on
1 October the eastern United States is on daylight time, not standard time. Both readings
are recorded here and the project works to the earlier one.

| Reading | Offset | Madrid equivalent |
|---|---|---|
| EDT, the zone actually in force on 1 October 2026 | UTC-4 | **05:59 CEST, 2026-10-02** |
| EST read literally, as the page writes it | UTC-5 | 06:59 CEST, 2026-10-02 |

**The working deadline is 05:59 Madrid on 2026-10-02.** Madrid is on CEST, UTC+2, until
2026-10-25, so no clock change falls between now and then.

Planned submission time is **12:00 Madrid on 2026-10-01** (SOP step W6.12), which leaves a
full clock day of margin against the earlier reading. The acceptance check for the owner
review before it runs at 20:00 Madrid on the day before.

Do not compute either figure by hand at the time. Use `TZ=Europe/Madrid date` for the
Madrid clock and `TZ=America/New_York date` for the conference clock.

The full paper is due **2026-12-04, 11:59 p.m.** on the same page. The page gives no zone
for that one, so it is not carried as verified beyond the literal string. Resolve it before
the December sprint rather than on the day.

Finalist, poster and conference dates are not published on that page and are not carried as
verified anywhere in this repository.

<!-- W6.3: feeds and challenges checkpoint -->

## Feeds and challenges, the sprint checkpoint

Owner: SOP step W6.3. Dependencies: W2.6, W2.13, W2.16. Related: D-12, D-62, R-05.

The checkpoint states whether the 2026 game feeds are on disk and extracted and
whether the challenge counts reconcile. It builds nothing. W2.6 pulls the feeds,
W2.13 extracts them on the corrected pitch key, and W2.16 builds the challenge
table and writes `out/tables/challenge_reconciliation.csv`.

Re-run it with:

    uv run --locked python ops/sprint_feed_checkpoint.py            write
    uv run --locked python ops/sprint_feed_checkpoint.py --check    verify only

The write form is the only thing allowed to move the feed and challenge slots in
`docs/numbers.json` or the W6.3 block in `abstract/SPRINT-STATUS.md`. Do not type
a number into either file. Both writes are byte-compared first, so a second run
in a row changes nothing.

Two generators share `docs/numbers.json`. `ops/sprint_feed_checkpoint.py` owns
the feed and challenge slots and writes them first; `ops/sprint_join_checkpoint.py`
owns the join slots and writes them last. Either may run first. A third generator
that rewrites `entries` wholesale has to carry both sets forward, or both steps
have to be re-run after it.

What `--check` fails on when the warehouse and the reconciliation report are on
disk: a feed stored after the last open day, an extraction that does not cover
every stored feed, a record difference between the challenge table and the
`gameData` tallies, a game that does not reconcile, a non-MJ review in the
challenge fact, an unresolved or unmatched challenge, a challenge with no
reconstructed original call, an overturn count that is not the sum of
`usedSuccessful`, a modal starting allotment other than two, and either published
artifact drifting from the data. On a clean clone with no datum on disk it gates
the committed ledger against the committed status block instead, so the step
still proves itself there.

DT-08 and DT-15 are refreshed by this step and owned elsewhere. Run them with:

    uv run --locked pytest tests/unit/test_challenges.py tests/data/test_warehouse_pack.py -q -k "dt08 or dt15"

The four MLB 2026 games with no `absChallenges` block in either source are
823669, 823745, 825093 and 825094. They hold no challenge, they are the same four
games DT-12 and DT-13 find off the ABS zone, and they are excluded from the
reconciled game count rather than counted as reconciling. Do not repair them by
hand.
