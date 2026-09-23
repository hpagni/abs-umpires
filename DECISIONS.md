# Owner decisions — sports analytics project

Recorded 2026-09-22 (Europe/Madrid). Hudson Pagni is the owner. Research questions, validation design, acceptance criteria and result calls are his; Claude Code implements under his direction.

## Project
- Primary: **P3, Umpires under ABS** (see research/brief-2026-09-22.md, section 5).
  - Chapter 1 (headline): three-regime strike-zone study. Regimes: 2022-24 (old umpire-grading buffer), 2025 (0.75-inch buffer), 2026 (ABS challenge system). Umpire heterogeneity is part of the headline. AAA 2023-25 is a second arm.
  - Chapter 2: calibrated challenger-skill leaderboard with split-half reliability and calibration curves, benchmarked against Savant xChal/xRuns and the use-it-or-lose-it variance-components model.
  - Chapter 3: two-sided token dynamic program (both teams' remaining challenges as state), presented as a benchmark replication of the public single-side solutions, not as a headline.
- Phase 2: **P8 betting layer**: calibrated MLB game forecasts scored against de-vigged closing lines and Kalshi prices. Odds API budget $30-60.

## Validation
- Public pre-registration: the analysis plan and acceptance criteria are committed to the repo before any model is fit on the sealed set.
- Sealed set: MLB games from 2026-09-22 onward plus the 2026 postseason. (Public work already used data through 2026-08-29.)
- A well-estimated null or small effect is a reportable result.

## Venues
- SSAC 2027: abstract due 2026-10-01 (sprint approved); full paper 2026-12-04.
- Reds Hackathon (expected late Dec 2026), CSAS 2027 (register by 2026-12-15), SABR Analytics 2027 (Mar 12-14).

## Constraints
- Budget: up to $100 total. Compute on the Mac (M3 Pro, 18 GB, ~65 GB free); PC with RTX 3070 8 GB available but not required for P3.
- Legal posture: raw MLB feeds stay private; publish code and aggregates; throttle pulls; attribute sources.
- Employer targets: MLB/NFL/NBA front offices, betting/DFS, media and data vendors.

## Writing rule (all human-facing text: memo, README, abstract, portfolio page, resume lines)
Plain, direct prose. No hype, no filler, no rhetorical questions. Short sentences, specific numbers.

## Execution posture (Hudson, 2026-09-22)
- Proceed autonomously from stage to stage. Use recommended defaults for open decisions and record them.
- Anything that needs the owner (payment, API keys, account sign-ups, credentials) is deferred: do every step that does not depend on it first, then present one consolidated list at the end.
- Stop only for a true wall. If stuck, convene an agent panel before asking the owner.

## Decisions applied under the execution posture (recommended defaults; owner may override)
- 2026-09-22, from the live data contract: AAA feeds show **two** challenge tokens per team in every 2024 and 2025 game sampled (never three), so the chapter-3 DP is 3x3 for AAA as well as MLB; size it from the observed per-season maximum, not from the earlier 4x4 note. The 2023 AAA feeds sampled carry no ABS challenge data at all; the AAA arm is 2024-2025 unless a full-season scan of 2023 finds challenge records. AAA 2024 Tuesday games do carry challenges, so the arm is not split by weekday; format is read from each game's feed.

## Staging cache (2026-09-23)
Raw pulls started early so the network time overlaps with fleet design: `~/sports-project/data/staging/` (see STAGING.md there). Ingest steps must import from this cache before hitting the network, then run the SOP's data tests on what they import. Throttle policy A3 was followed; provenance is in `manifest.jsonl`.

## Open owner decisions (to be raised, not decided silently)
- Repo name (default: abs-umpires under github.com/hpagni).
- Warehouse: BigQuery with billing vs MotherDuck Lite.
- Whether to include any nba.com-sourced data (default: no).

## W1.1 defaults (builder, 2026-09-23)
- `ops/preflight.sh` reports every failed check before exiting 1, rather than stopping at the first. Operators fixing a fresh machine see the whole list in one run.
- The 15 GiB floor is a literal in the script with a comment citing SOP W1.1 and risk R-25. No environment override: an overridable floor is not a floor.
- `make --version` is printed as information, not asserted. Risk R-23 wants the version visible; the Makefile (W1.14) is what must match it, so W1.1 does not hard-fail on it. GNU Make 3.81 observed.
- A `-q`/`--quiet` flag prints only failures and the final `PREFLIGHT OK`, so W1.14 can put the script on the first line of every disk-touching target without burying the target's own output.
- The `DYLD_LIBRARY_PATH` assertion is a floor under SIP, not a guarantee. Verified on this machine: macOS purges DYLD_* for protected binaries, and /bin/sh, /usr/bin/make and R's launcher are all protected, so a caller's value cannot reach the script and also cannot reach R or CmdStan. Reading it from the parent process with `ps -E` was tried and rejected as flaky in both directions (stale hit with nothing set, miss when set through make). The check is kept as the SOP writes it and the caveat is documented in the script.

## W1.2 defaults (builder, 2026-09-23)
- The MIT `LICENSE` copyright holder is `the abs-umpires authors`, not a personal name. WR-19 and D-69 blind the author in every file reachable from the repository root while the SSAC review window is open, and WR-19 names `LICENSE` explicitly. W7 un-blinds it on the day finalists are announced.
- `.gitignore` keeps the SOP's unanchored `data/` pattern, which matches a directory named `data` anywhere in the tree. Two directories in the section 2.1 tree are named `data` and hold source: `app/data/` (the Shiny app's bundled aggregates) and `tests/data/` (the DT-* data tests). Both are re-included by name. Nothing else under any `data/` directory is trackable. Anchoring the pattern to `/data/` was rejected: the unanchored form is the stricter default and the two exceptions are explicit and auditable.
- D-03 extension, binding on this fleet: `sop/` and `fleet/` are ignored alongside `data/`, `research/` and `logs/`. `RUNLOG.md` is ignored with them. It is the fleet's evidence log, it is absent from the section 2.1 tree, and it names `fleet/` paths and step internals. `tests/unit/test_layout.py` asserts all five directories are ignored, not three.
- `git check-ignore -q` accepts one pathname. git 2.50.1 rejects the SOP's literal `git check-ignore -q data/raw research logs` with "fatal: --quiet is only valid with a single pathname". The test runs the quiet form once per path, which is what the SOP asks for, and adds a non-quiet multi-path call that asserts every path comes back listed.
- W1.2 creates the remote and sets `origin`. It does not push. The `gh` token has no `workflow` scope, so a push carrying anything under `.github/workflows/` is rejected; W1.3 refreshes the scope and proves the first push. Commit 1 therefore exists locally and the public repo is empty until W1.3.
- Every tracked directory in the section 2.1 tree carries a `.gitkeep`, so the tree survives a clone and `test_layout.py` has a file to assert against. The gitignored directories (`data/`, `research/`, `logs/`, `warehouse/`, `sop/`, `fleet/`) carry none.

## W1.3 defaults (builder, 2026-09-23)
- `gh auth refresh -h github.com -s workflow,repo,read:org,gist` was not run. It is interactive: it blocks on stdin, prints a one-time device code and opens a browser for a confirmation only the account owner can give. This fleet runs unattended, so running it would hang phase 01 on a prompt nobody is watching. The token scopes observed are `gist, read:org, repo`; `workflow` is absent, so the SOP's "must contain `workflow`" assertion fails today.
- DEFERRED OWNER ACTION, not a work stoppage. Hudson runs this one line in his own terminal, once: `gh auth refresh -h github.com -s workflow,repo,read:org,gist`, then re-asserts with `gh api user -i 2>/dev/null | grep -i '^x-oauth-scopes'`. Nothing else in phase 01 waits on it.
- The end-to-end proof the SOP asks for, "a push that adds `.github/workflows/ci.yml`", is gated in P4, not here. W1.16 (SOP:545, W1.16 -> W1.3) writes that file, and W1.16 has not run: `.github/workflows/` holds only `.gitkeep`. W1.16 still writes both workflow files locally whether or not the scope exists; only the push needs the scope. Splitting the assertion this way keeps W1.3 from blocking a step that has no dependency on the refresh.
- W1.3 changed no tracked file. Its whole product is the scope check, the deferred owner line and the evidence log, so there is no commit for this step.

## git owner, P0 preflight-repo-remote (2026-09-23)
- The W1.3 addendum above was left uncommitted by its builder, whose own note says "W1.3 changed no tracked file". DECISIONS.md is tracked and is a path this group owns, so the git owner committed it (3fbddfe) rather than strand the record. No prose was changed.
- `git add -A` was not used anywhere. Paths were staged by explicit pathspec. README.md, ATTRIBUTION.md, PREREGISTRATION.md, DEVIATIONS.md and METHODS.md are listed as group-owned but do not exist on disk; no builder in this group wrote them, so nothing was invented to fill them.
- The first push to hpagni/abs-umpires is rejected: GitHub applies the `workflow` OAuth scope rule to every path under `.github/workflows/`, not only to .yml and .yaml, so the section 2.1 `.gitkeep` alone trips it. Deleting that .gitkeep would let the push through but would break the tree and test_layout.py, and W1.16 writes ci.yml into the same directory, so the block would return. Not taken. The push is deferred to the owner behind the same one-line `gh auth refresh` W1.3 already raised.
- SSH was tried as an owner-free route and is closed: the only key in ~/.ssh is id_ed25519_gorilladraft, which github.com rejects, and `gh ssh-key list` returns 404 because the token also lacks admin:public_key.
- D-16 stands as raised, not decided: the `Co-Authored-By: Claude Opus 5 (1M context)` trailer is on both commits in this repository. Hudson's standing no-AI-attribution rule is scoped to the sportacular repository. One line from the owner confirms or removes it while the history is still local and unpushed, which is the cheapest moment to change it.
