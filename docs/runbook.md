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
