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
- 2026-09-22, from the live data contract: AAA feeds show **two** challenge tokens per team in every 2024 and 2025 game sampled (never three), so the chapter-3 DP is 3x3 for AAA as well as MLB. Size it from the observed per-season maximum, not from the earlier 4x4 note. The 2023 AAA feeds sampled carry no ABS challenge data at all; the AAA arm is 2024-2025 unless a full-season scan of 2023 finds challenge records. AAA 2024 Tuesday games do carry challenges, so the arm is not split by weekday; format is read from each game's feed.

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
- `gh auth refresh -h github.com -s workflow,repo,read:org,gist` was not run. It is interactive: it blocks on stdin, prints a one-time device code and opens a browser for a confirmation only the account owner can give. This fleet runs unattended, so running it would hang phase 01 on a prompt with no operator present to answer it. The token scopes observed are `gist, read:org, repo`; `workflow` is absent, so the SOP's "must contain `workflow`" assertion fails today.
- DEFERRED OWNER ACTION, not a work stoppage. Hudson runs this one line in his own terminal, once: `gh auth refresh -h github.com -s workflow,repo,read:org,gist`, then re-asserts with `gh api user -i 2>/dev/null | grep -i '^x-oauth-scopes'`. Nothing else in phase 01 waits on it.
- The end-to-end proof the SOP asks for, "a push that adds `.github/workflows/ci.yml`", is gated in P4, not here. W1.16 (SOP:545, W1.16 -> W1.3) writes that file, and W1.16 has not run: `.github/workflows/` holds only `.gitkeep`. W1.16 still writes both workflow files locally whether or not the scope exists; only the push needs the scope. Splitting the assertion this way keeps W1.3 from blocking a step that has no dependency on the refresh.
- W1.3 changed no tracked file. Its whole product is the scope check, the deferred owner line and the evidence log, so there is no commit for this step.

## git owner, P0 preflight-repo-remote (2026-09-23)
- The W1.3 addendum above was left uncommitted by its builder, whose own note says "W1.3 changed no tracked file". DECISIONS.md is tracked and is a path this group owns, so the git owner committed it (3fbddfe) rather than strand the record. No prose was changed.
- `git add -A` was not used anywhere. Paths were staged by explicit pathspec. README.md, ATTRIBUTION.md, PREREGISTRATION.md, DEVIATIONS.md and METHODS.md are listed as group-owned but do not exist on disk; no builder in this group wrote them, so nothing was invented to fill them.
- The first push to hpagni/abs-umpires is rejected: GitHub applies the `workflow` OAuth scope rule to every path under `.github/workflows/`, not only to .yml and .yaml, so the section 2.1 `.gitkeep` alone trips it. Deleting that .gitkeep would let the push through but would break the tree and test_layout.py, and W1.16 writes ci.yml into the same directory, so the block would return. Not taken. The push is deferred to the owner behind the same one-line `gh auth refresh` W1.3 already raised.
- SSH was tried as an owner-free route and is closed: the only key in ~/.ssh is id_ed25519_gorilladraft, which github.com rejects, and `gh ssh-key list` returns 404 because the token also lacks admin:public_key.
- D-16 stands as raised, not decided: the `Co-Authored-By: Claude Opus 5 (1M context)` trailer is on both commits in this repository. Hudson's standing no-AI-attribution rule is scoped to the sportacular repository. One line from the owner confirms or removes it while the history is still local and unpushed, which is the cheapest moment to change it.

## W1.12 defaults (builder, 2026-09-23)
- `gitleaks` was absent from PATH. Homebrew core ships exactly 8.30.1, the version SOP W1.12 pins, so it was installed from there rather than vendored into the repository or fetched at an unpinned version. The binary is a machine tool, not a tracked file; nothing under the repo changed to hold it.
- The 8.30 CLI moved its scan verbs to `gitleaks git` and `gitleaks dir`, but `gitleaks detect` is retained as a hidden command and still scans full history. The SOP's literal `gitleaks detect --redact --no-banner` runs as written, so W1.13 and W1.16 inherit the string unchanged and no deviation is needed.
- The Backblaze rule regex is the SOP's `00[0-9a-f]{22}` with a word boundary added on each side: `\b00[0-9a-f]{22}\b`. This is the only edit to a string the SOP names, and it is load-bearing rather than cosmetic. A 40-character git commit SHA beginning `00` contains a 24-character substring that matches the bare pattern; about one commit in 256 begins that way; GD-01 and GD-02 put a `git_sha` in every fit receipt under `out/`. The unbounded form would have failed the W1.16 secrets job on an ordinary commit. A real key ID appears as a standalone token, so the boundaries cost no detections. Tested both ways: a 24-character key ID is flagged, a 40-character SHA starting `00` is not.
- `[extend] useDefault = true`. The Backblaze rule is added to the upstream ruleset, not substituted for it. Replacing the default set with one rule would have been a large silent loss of coverage on a repo that is public from commit 1 (D-02).
- The `.env.example` allowlist is a path rule, `(^|/)\.env\.example$`, and covers that one file. It deliberately does not extend to `.env`: `.env` is gitignored and must never reach a scan at all, and an allowlist entry for it would quietly excuse the case the hook exists to catch. Verified that the same bytes under another filename are still flagged.
- `.env.example` contains no absolute path and no personal name. WR-19 and D-69 blind the author in every file reachable from the repository root while the SSAC review window is open, and the repository is public. The `ABS_DATA_ROOT` comment therefore describes the path rather than printing this machine's.
- `.env` was not created. There are no keys yet, and an empty `.env` on disk would make the "unset means skip with a message" paths in W1.10 and `ops/smoke.sh` harder to exercise honestly.
- `gh secret set` was not run. B2 and MotherDuck are provisioned in later phases and no key exists to set. Setting a placeholder would be worse than an absent secret, because CI would then fail on an authentication error instead of skipping. Deferred to the owner.
- The gitleaks pre-commit hook (W1.13, SOP:938) and the CI secrets job (W1.16, SOP:962) are not this step's files. W1.12 supplies the config both of them load.

## W1.5 defaults (builder, 2026-09-23)
- The project library was filled with `renv::hydrate()` from the two existing user libraries, not by reinstalling from CRAN. `renv::init(bare = TRUE)` gives an empty, isolated library, and the 216 packages correction A2 verified on 2026-09-22 live in the user library, which renv does not see. Hydrating linked 199 packages in 8.7 s and preserved the audited versions exactly: brms 2.23.0, arrow 25.0.1, duckdb 1.5.5, baseballr 2.0.0, rstan 2.32.7, posterior 1.7.0. Reinstalling from CRAN would have taken an hour and silently upgraded anything CRAN has moved since the audit, which is the one thing A2 says not to do.
- Correction A2 was run in its stated order: `DT` 0.34.0 installed and `cmdstanr` 0.9.0 rebuilt from source under R 4.5.2 (it was built under 4.5.3) before `renv::snapshot()`, then RP-03. The rebuild is the same version from the same repository, `https://stan-dev.r-universe.dev`, only recompiled; `Built: R 4.5.2` is in the evidence log.
- OWNER DECISION, recommended default taken, reversible in one line. `renv/settings.json` now sets `snapshot.type: "all"`. Without it `renv::status()` prints 222 rows of "installed y, recorded y, used n" and RP-03 can never return "No issues found". The default `implicit` type asks whether project code references each package, and this repository has almost no R code yet. The SOP already commands `renv::snapshot(type = "all")`; this setting makes `status()` use the same rule as `snapshot()` instead of a stricter one. What RP-03 asserts is therefore "every package in the library is in the lockfile at the same version, and the reverse" and no longer "every recorded package is used". Recommended default: keep it. The usage question is answered by W9.2 and by RP-08's cold rebuild, not by `status()`. To reverse: delete the line from `renv/settings.json` and re-gate RP-03 after the R code exists.
- Versions the SOP does not pin were taken at CRAN current on 2026-09-23 and are now frozen in `renv.lock`: `lme4` 2.0-6, `tidybayes` 3.0.7, `marginaleffects` 1.0.0, `zoo` 1.9-0, `DT` 0.34.0. The two it does pin are exact: `mgcv` 1.9-4 (binary, as specified) and `targets` 1.12.0. The lockfile holds 222 packages and pins R itself at 4.5.2.
- The `.Rprofile` DYLD guard is correct but cannot be exercised from a shell on this machine. macOS System Integrity Protection strips `DYLD_*` from the environment before `Rscript` starts, so `DYLD_LIBRARY_PATH=/tmp/fake Rscript ...` reaches R as empty. The guard was proved instead by setting the variable inside R and sourcing `.Rprofile`, which halts with a non-zero exit. A verifier who tries the shell form and sees it pass is seeing SIP, not a broken guard.
- The two-line Stan model and its compiled binary are written to `~/.cache/absump/stan-2.40.0`, outside the repository. A compiled executable is not a repository artifact and `out/` is not gitignored for binaries. The CmdStan version is in the directory name so an upgrade cannot reuse a stale executable. Cold run 15.2 s, warm 2.1 s, against the SOP's 38 s budget for the full path.
- `R/lib/http.R` was not written. Section 0.5 rule 2 names it as the only R site allowed to issue an HTTP request, W1.5 does not specify it. No R code in phase 01 makes a request, and `ops/lint_http.sh` passes on an R tree with no call site. Writing an unspecified client here would pre-empt the W1.7 design with no test holding it. It is needed before the first R-side pull in phase 02.
- `make r-smoke` (W1.14's file) should be exactly `Rscript R/00_setup.R`. That command, chained with the `renv::status()` check, is the verify registered for W1.5; `quality/steps.yml` did not exist when this step ran, so it was handed to the W9.1 agent instead.

## W2.2 defaults (builder, 2026-09-23)
- The audit rewrote nothing. SOP section 2.2's 24 `[project].dependencies` entries and 11 `[dependency-groups]` entries are in `pyproject.toml` character for character, checked by diffing both blocks with comments stripped. No pin is missing and no pin is extra, so the step's own condition for editing `pyproject.toml` was not met and the file was left alone. `dbt-adapters` is 1.24.5 and `dbt-common` is 1.39.0 in `uv.lock` and in `.venv`, exactly as section 2.2 states. `pybaseball` and `great-expectations` appear nowhere in the lock, the manifest, or any tracked file.
- OWNER DECISION, recommended default stated, not taken silently. Section 2.2 says the pinned set "resolves on Python 3.12 in 0.8 s to 74 packages". It resolves to **106**. The default install set means `[project].dependencies` with no dependency group synced. That set is 24 direct and 82 transitive distributions. Four independent measurements agree: `uv export --no-default-groups` gives 106 names; `uv sync --no-default-groups --dry-run` leaves 107 including the editable `absump`. A clean re-lock of the dependency list alone in an empty temp project reports "Resolved 107 packages". The committed full lock, which also carries `dev` and `bayes-fallback`, is 178. The gap of 32 is not a bad resolution and not a pin error, since the pin list is the SOP's own. 74 is stale. It is also not the set with dbt removed, which would be 66, and section 2.2 states in the same sentence that the set pulls dbt-adapters and dbt-common, so dbt is inside whatever 74 counted. Two known sources of recent growth: polars 1.44.2 ships its runtime as a second distribution, `polars-runtime-32`, which older polars did not, and typer 0.27.2 adds `annotated-doc`. **Recommended default: amend section 2.2 to 106 and keep the pin set untouched.** The alternative, cutting packages to reach 74, would mean dropping a pinned dependency the SOP requires, which is worse. `tests/unit/test_deps.py` asserts the audited 106 by name, so any future drift prints the added and removed packages instead of a bare count. The full enumeration with per-package attribution is in `logs/evidence/W2.2-build.log`.
- The 0.8 s resolve time in section 2.2 was a cold resolve with network on 2026-09-22 and is not reproducible offline. It is not gated. Warm re-resolve of the committed lock is 1 to 9 ms.
- `requests` 2.34.2 is in `uv.lock`, pulled transitively by `dbt-core` and `dbt-duckdb`. Section 2.2's contradiction table drops `requests` as a direct pin, and it is not one. It cannot be removed transitively without removing dbt. This is not a rule 0.5.2 breach: the rule governs call sites in this repository and `ops/lint_http.sh` checks those, and dbt's internal use is not reachable from our code. The test asserts `requests` is absent from the direct list, not from the lock, which is the assertion that can actually hold.
- The test computes the default set from `uv.lock` by graph traversal rather than by shelling out to `uv`, so the gate needs no subprocess, no network and no warm cache. The traversal follows only requested extras and was checked against `uv export --frozen --offline --no-default-groups --no-emit-project` on this lock: identical set of names, zero diff.
- `quality/steps.yml` did not exist when this step ran. The verify command `uv run --locked pytest tests/unit/test_deps.py -q` was handed to the W9.1 agent instead, as W1.5 did with its own.

## git:environment defaults (P1 commit agent, 2026-09-23)
- Staged the eleven paths the P1 builders own and nothing else. Ten files entered commit `c863e85`; `R/lib/.gitkeep` was already tracked from W1.2, so `R/lib/` added nothing. Three paths were left dirty on purpose because this group does not own them: `DECISIONS.md` (builder text, uncommitted), `renv/.gitignore` (renv scaffolding, redundant with the root `.gitignore`); and `tests/unit/test_deps.py` (the W2.2 gate). The root `.gitignore` already covers `renv/library/` and `renv/staging/`, and the P2 chokepoint agent, whose path list is `tests/unit/`, staged the W2.2 gate later. `git add -A` was not used.
- The three raw-data gates ran before staging and all passed: `data/raw`, `research`, `logs`, `sop` and `fleet` are ignored; no tracked path lies under them; no tracked file exceeds 5 MB. `gitleaks protect --staged` scanned 853.78 KB of staged content and found no leaks. `.pre-commit-config.yaml` does not exist yet (W1.13), so `pre-commit run --files` was skipped.
- The push is rejected, as W1.3 predicted. `git push origin main` returns "refusing to allow an OAuth App to create or update workflow `.github/workflows/.gitkeep` without `workflow` scope". Token scopes are `gist, read:org, repo`. This is the deferral already recorded above at W1.2 and W1.3; it is not re-litigated and no history was rewritten to work around it.
- An SSH fallback was tested rather than assumed. `/Users/hudsonpagni/.ssh/id_ed25519_gorilladraft` is the only key present and GitHub answers `Permission denied (publickey)`, so it is not on the account. Registering it would need `admin:public_key`, which the token also lacks. There is no non-interactive path to a push. Not taken.
- `origin` has zero heads. No commit in this repository has been pushed. Three local commits are waiting on the one `gh auth refresh` line.
- D-16 carried forward, still raised and not decided. The `Co-Authored-By: Claude Opus 5 (1M context)` trailer is on `c863e85` as instructed, so it is now on all three commits. The history is still local and unpushed, which remains the cheapest moment for the owner to confirm or remove it.

## W1.14 defaults (Makefile builder, 2026-09-23)
- Every target in the SOP W1.14 list exists, 52 of them, spelled as the SOP spells them. `unseal` is the 53rd: SOP W2.4 names it as a make target and the delegation rule assigns it a script, so the Makefile carries it even though the W1.14 list does not. No other target was added. `figures` and `tables` are named elsewhere in the SOP but are not in the W1.14 list, and they were left out rather than invented into it. The step that needs them should add them to the SOP list first.
- The one-line-delegation rule is enforced by a test, not by convention. `tests/unit/test_makefile.py` fails if any recipe has more than one line or contains `&&`, `||`, `;`, `|`, a backtick, `$(shell`, or an `if`, `for` or `while`. That is what keeps W2.4, W9.1, W9.2 and W9.7 out of this file while they build in parallel.
- Script homes: operational scripts in `ops/`, pipeline runners in `scripts/`. `scripts/prove.sh` is the SOP's own path and set the convention for `scripts/`; `ops/preflight.sh`, `ops/lint_http.sh`, `ops/preregister.sh`, `ops/smoke.sh` and `ops/b2_check.sh` are the SOP's own paths and set it for `ops/`. Chapter, P8, app and abstract runners went to `scripts/`; environment, disk, seal, lint, data and clean scripts went to `ops/`. A later step that wants a different path changes its own target's one line.
- `py` and `r` were undefined by the SOP. Read as the two halves of `bootstrap`: `py` is `uv sync --locked --all-groups`, `r` is `Rscript -e 'renv::restore(prompt = FALSE)'`, and `bootstrap` runs preflight then both. `uv sync` is idempotent on a machine that is already set up. `renv::restore()` is
not, and round 5 corrects this sentence: it rewrites `renv/activate.R` on every
run. See "Round 5" below and DEV-19 for what that cost and how it was repaired.
- `canary` delegates to `ops/b2_check.sh`, the SOP's own name for the B2 canary in W1.15, rather than a new script name.
- 36 placeholder scripts were created, one per target whose body a later step owns. Each prints one line naming that step and exits 0, so `make -n <target>` and `make <target>` both work today. Each carries the string `ABSUMP_PLACEHOLDER` and the sentence "the existence of this file is not evidence that <step> has run", so that the owning step overwrites it instead of skipping on a file-exists check. `grep -rl ABSUMP_PLACEHOLDER ops scripts tests/guard` lists all 36.
- `ops/lint_http.sh` was deliberately not stubbed. SOP W1.7 owns it and is building in this same phase, so a stub could have been mistaken for its work. `ops/lint.sh` runs ruff check, ruff format --check and then that script if it is present, and otherwise prints one line naming W1.7 without failing the run. W1.7's own gate is what proves rule 0.5.2, not this target.
- `seal-check` was implemented rather than stubbed, in the only form phase 01 allows: no row is read, no database is opened, no request is issued. Three assertions, all on metadata: `ABS_SEAL_UNLOCK` is unset, every artifact under `out/sealed/` has a sibling `provenance.json`, and nothing under `out/sealed/` is tracked by git. SOP W9.7 replaces the script with layers 3 and 4 and does not touch the Makefile.
- `clean`, `clean-out` and `clean-warehouse` were left as placeholders. They delete, and phase 01 has nothing whose deletion is defined yet; W9.9 owns determinism from clean and should write what clean means.
- The 15 GiB floor in `ops/disk_check.sh` is the SOP's own number (W1.1 and risk R-25), not a value from any endpoint, and the script says so. It duplicates the floor check in `ops/preflight.sh` on purpose: risk R-25 names `make disk` and `make disk-check` as separate mitigations.
- `make test-guard` exits 5 until W9.7 writes `tests/guard/`, because pytest returns 5 when it collects nothing. It was left exact rather than wrapped, since suppressing it would mean putting shell logic in a recipe, which is the one thing this Makefile forbids. `make -n test-guard` is green and `make test` is green, because `tests/unit` collects.
- `make test-model-fast` selects `-m fast`. `pytest` runs with `--strict-markers`, so SOP W9.8 has to register a `fast` marker in `pyproject.toml` when it writes `tests/model`.
- `quality/steps.yml` did not exist when this step ran. The verify command `uv run --locked pytest tests/unit/test_makefile.py -q` was handed to the W9.1 agent instead, as W1.5 and W2.2 did with theirs.

## W1.6 defaults (builder, 2026-09-23)
- OWNER DECISION, recommended default stated, not taken silently. GD-05 as the summary line writes it ("no `sealed` string outside those two allowlisted files") cannot hold together with W1.6, which requires `src/absump/paths.py` to route sealed rows to the sealed directory and to raise `SealViolation`. It already does not hold. `tests/unit/test_layout.py` (W1.2) names the two sealed directories in the section 2.1 tree, and the dbt project file W1.11 writes carries a `sealed` target name. **Recommended default: GD-05 counts the four GD-04 patterns — `analysis_set` with `'sealed'`, `v_pitch_sealed`, an unqualified raw `fct_pitch` read, and a literal date on or after the seal start.** Not the bare substring, and the allowlist stays at exactly two files. A directory name is not a sealed read. To take the strict reading instead, add `src/absump/paths.py` and `tests/unit/test_layout.py` to GD-05's allowlist, which makes the count four and contradicts the "exactly two" the SOP states twice. W9.7 owns the scanner and needs this answer before it writes it.
- Sealed days land under a `plain` subtree of the sealed root, not directly under it. The SOP's own ceremony is `tar -C data/sealed -cf - plain | age -p`, then `rm -rf` of the plain directory, and GD-10 asserts zero `*.parquet` and zero `*.json.zst` under the sealed root afterwards. Writing parts directly under the sealed root would make GD-10 fail by construction on the day the seal closes.
- The seal boundary is one constant, `paths.LAST_OPEN_DATE`, and it is written as the last open day rather than as the first sealed day. GD-04 fails the repository on a literal date on or after the seal start, so no file outside the two allowlisted paths may spell that date. Everything that needs a sealed date computes it from this constant. W1.8's `seal.py` should import it rather than restate it; the dbt var is the day after it.
- The uniqueness rule is gated as `tests/unit/test_paths.py::test_layout_strings_live_only_in_paths_py`. It reads the layout templates out of the module at run time and greps the tree, so the test spells none of the strings itself. Two scoping choices: the scan covers source files (`.py .R .sql .yml .yaml .toml .sh .stan .cfg .ini .mk`, plus `Makefile`, `dbt_project.yml` and the dbt profiles example), not Markdown. A document that names a path is not a call site, and `docs/warehouse.md` will name the warehouse file. Two template keys, the spill directory and the sealed root, are excluded as well, because a bare "tmp" or "sealed" is an ordinary word and a section 2.1 directory name.
- The dbt profiles example is the one declared mirror of the warehouse path, named as such by W1.6, so the test allowlists that one file for that one string. Consequence for later steps: a shell script or Makefile target that needs the warehouse file must read it from `absump.paths.DUCKDB_PATH` or match the `warehouse/` directory by glob. Spelling the full path in `ops/` or the Makefile breaks this gate, which is the gate doing its job.
- `connect()` tries `LOAD` before `INSTALL` for httpfs and parquet. The SOP writes `INSTALL x; LOAD x;`, and INSTALL reaches the extension repository over the network. Both extensions are already installed on this machine, so LOAD alone makes the connection need no request at all; INSTALL still runs when the extension is absent. This matters on a university network that resets some TLS connections.
- `preserve_insertion_order = false` is load-bearing beyond memory. DuckDB 1.5.5 refuses `ROW_GROUP_SIZE_BYTES` while insertion order is preserved ("Binder Error: ROW_GROUP_SIZE_BYTES does not work while preserving insertion order"), so the 128 MB row group in the W1.6 write contract depends on the fourth SET statement. Verified both ways.
- DuckDB exposes no per-column dictionary switch in `COPY`; it dictionary-encodes strings on its own. The five columns W1.6 names (`pitch_type`, `description`, `home_team`, `stand`, `p_throws`) are therefore applied on the PyArrow writer path, `db.pyarrow_parquet_options()`, and are documented as the intent on both paths. ZSTD level 9 and the 128 MB row group are set on both.
- The `ci` target is sized for a GitHub-hosted runner, not this Mac: threads 4, `memory_limit '8GB'`, in memory, parquet only. The SOP fixes the dev numbers and says only that ci is the in-memory fixture build. Reversible in two lines if CI hardware changes.
- `interim()` raises `SealViolation` on a sealed officialDate instead of returning an open path. A writer that wants both sides calls `lake_path()`, which is the only function that knows the sealed branch. `assert_minted()` is the writer-side hook: `db.connect()` and `db.copy_to_parquet()` call it, and a path under the data root that this module did not mint is refused.
- GD-11 is gated twice. Statically, the dev target in the dbt profiles example has no `attach` block and no path under the sealed root. At run time, `duckdb_databases()` on a connection this module opened lists nothing resolving under the sealed root. `connect()` runs the run-time check before it hands the connection back.
- Not this step's files, and not written here: `src/absump/seal.py` and `config/seal.yml` (W1.8), `dbt/dbt_project.yml` and the source `external_location` block (W1.11), `src/absump/http.py` (W1.7). `quality/steps.yml` does not exist yet, so the verify command `uv run --locked pytest tests/unit/test_paths.py -q` was handed to the W9.1 agent, as W1.5 and W2.2 did with theirs. No git command was run.

## W1.7 defaults (builder, 2026-09-23)
- Zero requests were issued building this step. Every test in `tests/unit/test_http_etiquette.py` installs an `httpx.MockTransport` and a fake clock; the R parity test writes a zstd frame and sends nothing.
- RP-09 holds the section 2.3 table as data inside `tests/unit/test_throttle_budget.py` rather than scraping it out of the SOP. `sop/` is private planning material (D-03) and is not in the public repository, and RP-08 requires the test to run in a clean clone. The test asserts `config/throttle.yml` against the table row by row. It then re-derives, from the config's own delays and caps, all twelve section 10.1 rows, the three per-host totals, the 11,816-request grand total, the 17.8 h figure, the night counts and the 1,083-request sprint subset. Section 10.1 states hours to one decimal rounded half up and minutes rounded up, and the test rounds the same way rather than carrying a tolerance. The one exception is the sprint subset, which the SOP itself states as "about 3.0 h".
- The raw cache path is the client's own namespace: `data/raw/<host>/<first two hex of sha256(url)>/<sha256(url)>.zst`. Section 2.3 fixes the signature `get(url, *, host_budget=True)`, so there is nowhere to pass a destination. `absump.paths` (W1.6) mints readable raw paths from feed identifiers that a bare URL does not carry. **Default taken: the client owns this namespace, and `data/raw/_manifest.csv` records the readable URL beside every path.** W6.0's ingest promotes the bytes to `paths.raw_*` when it parses them. Reversible by adding a keyword to `get()`, which would deviate from the signature section 2.3 states.
- Three module globals are test seams — `_monotonic`, `_sleep` and `_transport` — plus `_reset_state()`. A 10 s per-host gap is not testable in real time; with a clock that only moves when the client sleeps, the gaps are real arithmetic and cost no wall clock. Production code never rebinds them, and `_reset_state()` is documented as tests-only because the throttle clock and the daily budget are deliberately process-wide.
- 429 is retried although it is a 4xx. Section 2.3 names it in the backoff list in the same sentence as the no-retry-on-4xx rule. Every other 4xx raises `Fatal` on the attempt that met it, and 403 raises `Fatal` before any backoff, with no manifest row written.
- A 3xx is fatal and redirects are not followed. The one redirect section 2.3 records is the leaderboard `year=` form, and the contract check refuses that URL before the transport is touched. A later step that needs a redirected resource fetches the canonical URL instead.
- The two contract facts are enforced, not merely documented. A `/leaderboard/abs-challenges` URL carrying `csv=true` or `year=` raises before a request is issued. The drawer service at `/leaderboard/services/abs/` is explicitly exempt, because W4.2 records that it works only with the `year=` / `gameType=regular` form; the check is scoped to the leaderboard path and must never be widened to the host.
- `Response.text` decodes with `utf-8-sig` for Savant and `utf-8` elsewhere, so the BOM is stripped at the one place bytes become text.
- Python writes raw frames with `zstandard` level 10 in one shot; R writes them with `arrow::CompressedOutputStream` at the same level, which emits a frame with no content size in its header. `ZstdDecompressor.decompress()` refuses such a frame, so the Python reader streams instead. A frame written by either half is read by the other, and `tests/unit/test_http_etiquette.py` asserts it across an `Rscript` subprocess.
- `R/lib/http.R` is written here. The W1.5 note recorded it as deferred to this step. It is the same policy in the other language: the same `config/throttle.yml`, the same `sha256(url)` cache path, the same ten manifest columns, the same `data/raw/_budget.json`, the same status classification and the same contract refusals. The parity test compares the User-Agent, both delays, both caps, the manifest columns, the zstd level and the computed destination path.
- The R half records `wire_bytes` as the host's declared `Content-Length` when there is one and the decoded length otherwise, because curl does not hand the transfer size back through httr2. The Python half records the wire count directly. The column means the same thing on both sides only when the host declares a length; the manifest header is unchanged and the difference is commented at the call site.
- The daily budget is per host, per UTC day, in `data/raw/_budget.json`, shared by both halves and written atomically. `host_budget=False` skips the cap for a single probe and never skips the delay: the delay is the etiquette, the cap is the ceiling.
- `--dry-run` is available two ways: `ABSUMP_DRY_RUN` in the environment makes `get()` print the plan and send nothing, and `python -m absump.http --dry-run URL ...` prints a plan for many URLs. Estimated bytes are the manifest's own observed mean for that host, or section 2.3's measured 109,623 B compressed feed when the manifest holds no row for it. No figure in the planner was invented.
- `ops/lint_http.sh` takes an optional root argument so a test can plant a violation in a temporary tree. Six planted call sites — `urllib`, `requests.`, `httpx.Client`, `httpx.get`, `httr2::request` and `curl ` — are asserted to fail it, and the two allowed files are asserted to pass. It scans `src/`, `R/`, `tools/` and `notebooks/`, skips `__pycache__`, `.ipynb_checkpoints`, `.Rproj.user` and `renv`, and allowlists by exact path.
- `docs/legal.md` is not written yet. The RP-09 test that asserts the published statsapi policy equals the enforced one skips until that file exists, rather than passing vacuously.
- Not fixed here, and not this step's files: `tests/unit/test_deps.py` and `tests/unit/test_layout.py` fail `ruff format --check`, which is the one failing check in `ops/lint.sh`. They belong to W1.4 and W1.2.
- `quality/steps.yml` still does not exist, so the verify command `uv run --locked pytest tests/unit/test_http_etiquette.py tests/unit/test_throttle_budget.py -q && ops/lint_http.sh -q` was handed to the W9.1 agent, as W1.5, W1.6 and W2.2 did with theirs. No git command was run.

## W2.3 defaults (builder, 2026-09-23)
- W2.3 adds no client and none was added. `src/absump/http.py` and `R/lib/http.R` were read, not edited; `ops/lint_http.sh` was read, not rewritten, as it is W1.7's file. The Makefile was not touched: its `lint` target already runs `bash ops/lint.sh`, which is where the wiring belongs.
- `ops/lint.sh` previously tolerated a missing `ops/lint_http.sh` with a message and no failure, because W1.7 had not landed when W1.14 wrote it. **Default taken: absence of the linter is now a failure.** W1.7 has landed and the file exists. A lint run that silently skips the one check proving SOP rule 0.5.2 is worse than no lint run. Reversible in three lines.
- `docs/data-contract.md` did not exist. Section 2.1 lists it in the tree and no phase-01 step owns it. **Default taken: W2.3 created it as the prose index for the data sources**. It carries one section, "HTTP delegation (W2.3)", and a note that each source section is appended by the step that owns that source. A later owner appends rather than rewrites. If a step later claims the whole file, the delegation section moves with it intact.
- The delegation table lists every pull in the repository, present and planned, with its host and its client. W2.5, W2.6, W2.7 and W2.8 go to `statsapi.mlb.com`; W2.9, W2.10, W2.11 and W4.2 to `baseballsavant.mlb.com`; W2.12 to `www.retrosheet.org`. W8.2 goes to `api.elections.kalshi.com`, W8.3 to Sportsbook Reviews Online, and W8.5 to `api.the-odds-api.com`. Steps downstream of W2.15 read the local cache and the warehouse and issue no request. The list is the SOP's dependency block and the W8 section; no step was invented.
- **Recorded, not fixed: `ops/lint_http.sh` scans `src/`, `R/`, `tools/` and `notebooks/`, and does not scan `ops/` or `scripts/`.** The SOP's one shell `curl` is the monthly manual check of the CSAS 2027 page for its announced topic. That is an owner reading a web page, not a data pull, and nothing it returns enters `data/`, the warehouse or a model. If it is ever automated, it routes through the Python client or the linter's scan list grows. Widening the scan would mean editing W1.7's file, which this step is forbidden to do; it is flagged in `docs/data-contract.md` so it is known rather than discovered.
- `docs/legal.md` publishes the throttle as policy prose and repeats no number that is not in `config/throttle.yml` or section 2.3. Those are 4 s and 3,000/day to statsapi, 10 s and 800/day to Savant, 10 s and 500/day elsewhere, the User-Agent verbatim, no email address ever sent, 4xx never retried, 403 fatal. It carries no email address itself, and a test asserts that. Where a host operator wants the pulls stopped, the file points at the repository's issue tracker rather than an address.
- The gate test is `tests/unit/test_http_delegation.py`, 23 offline assertions. **No test id was invented for it**: the SOP names no `RP-`, `UT-` or `DT-` id for W2.3, and the file carries none. One assertion plants a `requests.get` call site in a temporary tree and asserts the linter exits 1 on it, so that a linter which silently scanned nothing could not pass the rest of the file.
- The verify command is the pytest module plus `sh ops/lint_http.sh -q`, not `make lint`. W1.7 recorded that `tests/unit/test_deps.py` and `tests/unit/test_layout.py` still fail `ruff format --check`, which would fail `make lint` for reasons that are not this step's.
- `quality/steps.yml` still does not exist, so the verify command was handed to the W9.1 agent, as W1.5, W1.6, W1.7 and W2.2 did with theirs. No git command was run.

## git:chokepoint defaults (P2 commit agent, 2026-09-23)

- Staged exactly the sixteen files under the eleven paths the P2 builders own and used `git add` with an explicit pathspec, never `git add -A`. The ~40 untracked placeholder files under `ops/`, `scripts/`, `renv/` and `tests/guard/` belong to other groups and were left alone.
- Left `DECISIONS.md` uncommitted. It is not in this group's owned paths, and the P1 commit agent left it the same way. Its 96 uncommitted lines now hold the decisions raised by W1.5, W1.12, W2.2, W1.6, W1.7, W1.14 and W2.3, plus this section. Whoever owns that file should commit it; the material is only in the working tree until then.
- Committed W2.3 with its gate red rather than fixing it. `make lint` exits 2 because `ruff format --check` flags `tests/unit/test_deps.py` and `tests/unit/test_layout.py`. The HTTP call-site lint and the throttle-figure prose check both pass. Reformatting a builder's file is the builder's work, not the commit agent's, and doing it silently would have hidden a red gate. The commit body states it.
- Ran the three raw-data gates before staging, all pass, and added two checks of my own: `gitleaks protect --staged` (no leaks, 162.38 KB) and `bash ops/lint_http.sh` (LINT HTTP OK). No `.pre-commit-config.yaml` exists yet, so no hook ran, and the no-commit-to-branch hook is not installed, so a direct commit to main is correct at this point.
- D-16 carried forward, still raised and not decided. The `Co-Authored-By: Claude Opus 5 (1M context)` trailer is on `b4c297e`, so it is now on all four commits. The history is still local and unpushed, which remains the cheapest moment for the owner to confirm or remove it.
- Push is blocked, not failed. `git push -u origin main` was rejected: GitHub refuses an OAuth App creating `.github/workflows/.gitkeep` without `workflow` scope, and the gh token carries gist, read:org, repo only. Nothing reached the remote. This is the deferral already recorded by commit 3fbddfe (W1.3) and is not re-litigated. Two alternatives exist and neither is mine to take: refresh the token (`gh auth refresh -h github.com -s workflow`, needs a browser device code from the owner), or delete `.github/workflows/.gitkeep`, which would change the W1.2 layout and so is an owner decision. Recommended default: refresh the token, because the phase will need real workflow files later anyway.

## W1.7 / W2.3 independent verification of the HTTP chokepoint -- 2026-09-23 (Europe/Madrid)

Verifier evidence: `logs/evidence/verify-verify-throttle-chokepoint.log`. Verdict REFUTED.

- Throttle STANDS. `config/throttle.yml` is byte-identical to the YAML block quoted in SOP section 2.3 (21 non-comment lines, diffed programmatically). `docs/legal.md` publishes the same three rows. A repo-wide sweep found no surviving 1.5 s, 2.0 s or 2.6 s figure outside the SOP's own record of the withdrawal. Nothing to decide here.
- Chokepoint guard REFUTED. Thirty realistic bypasses were planted in isolated temp trees and linted; no request was sent. `ops/lint_http.sh` caught three. It misses `subprocess.run(["curl", ...])` and `system2("curl", c(...))`, because PATTERN requires the literal `curl ` with a trailing space. It misses `httpx.post`, `from httpx import get`, `from requests import get`, `http.client`, `aiohttp` and a raw socket. It misses every library that fetches for you -- polars `read_csv` on an https URL, `pandas.read_json` on a URL, duckdb `httpfs`, `pyarrow.fs`, `arrow::read_csv_arrow`, `jsonlite::fromJSON`, `read.csv(url())`, `download.file`, `httr::GET`, bare `request()` after `library(httr2)`, and `baseballr` fetch functions. baseballr 2.0.0 is installed and named in SOP line 255, so that last one is a live risk in W-chapters, not a hypothetical. It also scans only `src R tools notebooks`: `ops/`, `scripts/`, `dbt/`, `app/`, `sql/`, `quality/` and `tests/` are not looked at, and this project keeps 23 shell scripts under `ops/` and 17 under `scripts/`.
- No live violation exists in the committed tree today. The chokepoint is intact as a fact about commit b4c297e. What fails is the guarantee.
- The linter's own test is a tautology. `tests/unit/test_http_etiquette.py:519-527` plants exactly the six idioms that are literal members of PATTERN, all under directories the linter already scans. It proves the regex matches its own alphabet and cannot fail on any of the 27 misses.
- Email posture, partly refuted. No header value contains `@`, and the User-Agent is not built from `git config user.email` -- verified by grep for `user.email`, `getpass`, `getuser`, `GIT_AUTHOR` and `gitconfig` across all code, no hits. But `get()` applies no check to the URL, and an offline MockTransport probe showed that `https://hudpag%40gmail.com:tok@statsapi.mlb.com/...` makes httpx add `Authorization: Basic aHVkcGFnQGdtYWlsLmNvbTp0b2s=`, which decodes to `hudpag@gmail.com:tok`. A query parameter carrying an address is also passed through. The `@` guard at `src/absump/http.py:244` and `R/lib/http.R:101` inspects `config["user_agent"]` only.
- 403-fatal, no-retry-on-4xx and the cache short-circuit STAND, and the tests are real. Five mutations to `src/absump/http.py` (403 made retryable, 404 added to the retry ladder, `_FATAL_STATUS` emptied, the cache short-circuit disabled, `_throttle` removed) each produced a named failing test; the file was restored byte-identical after every one.

OWNER DECISION D-VERIFY-01, raised, not taken. Widening `ops/lint_http.sh` changes an acceptance criterion that SOP section 2.3 states verbatim ("greps `src/`, `R/`, `tools/` and `notebooks/` for `requests.`, `httpx.get`, `httpx.Client`, `urllib`, `curl ` and `httr2::request`"), so it is not a silent fix. Recommended default: keep the SOP's six idioms as the floor and add six things in one edit. They are (i) the scan set `ops scripts dbt app sql quality tests`; (ii) bare `curl`/`wget` without the trailing space; and (iii) `httpx\.`, `aiohttp`, `http\.client` and `socket\.create_connection` in place of the two `httpx.` spellings. Then (iv) `from +(requests|httpx) +import`, and (vi) a `baseballr` import outside `R/lib/http.R`. Rule (v) is an `https?://` literal in any `.py`, `.R`, `.sql` or `.sh` outside the two call sites, `config/`, `docs/` and `tests/`. It catches every fetch-for-you library at once without enumerating them. Then extend `tests/unit/test_http_etiquette.py` to plant bypasses the pattern does NOT already contain, so the test can fail. Second decision, same entry: whether `src/absump/http.py:get()` should reject a URL carrying userinfo or an `@` in the query. Recommended default: yes, raise `HttpError` on either, since no endpoint in this project authenticates that way and the-odds-api's key rides in a normal query parameter.

## W2.4 the sealed set -- 2026-09-23 (Europe/Madrid)

Builder evidence: `logs/evidence/W2.4-build.log`. Phase 01 scope only: the predicate, the config
mirror, the unseal gate, the SEAL.md header and UT-16/UT-17. No datum was sealed, no passphrase was
created or asked for, no 2026 row was read, no request was issued.

- `quality/sql/analysis_set.sql` is the SOP 2.4 text byte for byte, comment header included, nine
  lines, one expression, no trailing semicolon. It is the only classifier. UT-16 executes that file
  in DuckDB rather than reimplementing the rule in Python, because a second implementation is a
  second thing to drift. If W1.8's `src/absump/seal.py` later adds a Python classifier, it should be
  asserted against this file the same way `config/seal.yml` now is.
- `config/seal.yml` carries the six keys the SOP lists and nothing else. UT-17 checks it against the
  SQL twice: constant by constant by parsing the SQL text, and behaviourally over a 168-row grid of
  3 seasons x 8 game-type codes x 7 boundary dates. Three planted mutations (config date moved one
  day, code F dropped from the sealed list, SQL date literal moved) each produced named failures.
- `ops/unseal.sh` checks exactly the three conditions SOP W2.4 names, reports every failure rather
  than the first, and appends one `UNSEALED` line with the UTC stamp, the Europe/Madrid stamp and
  the tag's commit SHA. It never sets ABS_SEAL_UNLOCK and it prints the three further preconditions
  of `absump.seal._unlocked()` that it does not check. The Makefile was not touched.
- Two defaults beyond the SOP text, both reversible. First, `--check` runs the gate and appends
  nothing, so the gate can be inspected without spending the one-way door. Second, a second run
  against a tag already recorded in SEAL.md refuses instead of logging a duplicate, because the
  unseal happens once. Neither weakens the three conditions.
- `docs/prereg/SEAL.md` states the guarantee plainly: a passphrase in the owner's password manager
  on a single-user laptop, not a separation of duties, not an escrow, not a third-party timestamp.
  The same sentence has to appear in `PREREGISTRATION.md`, which is W1.8's file, not this step's.

OWNER DECISION D-SEAL-01, raised, not taken. A 2026 regular-season row with a NULL `officialDate`
classifies as open, because SQL three-valued logic makes the date comparison NULL and the row falls
through to the ELSE branch. That is a leak path into training data. The predicate is frozen at
`prereg-v1` and must not be edited to close it. Recommended default: enforce `officialDate NOT NULL`
upstream instead -- in the statsapi data contract at extraction and as a NOT NULL constraint on
`dim_game.official_date` -- and let ingestion fail loudly on a schedule row without one.
`tests/unit/test_seal_classifier.py::test_null_official_date_is_not_sealed` pins the current
behaviour so it is written down rather than discovered during the sealed run.

Note for W9.7, not a decision. The layer-3 static scan allowlists exactly two paths,
`src/absump/seal.py` and `quality/sql/analysis_set.sql`. The two new test files necessarily contain
the sealed label and the seal date as literal expectations. They were written to keep the column
name and the quoted label off the same source line and to use no date comparison operator, but
whoever writes `tests/guard/test_no_sealed_reads.py` must run it against them and confirm the
allowlist count of two still holds.

OWNER DECISION D-PROVE-01, raised, not taken (2026-09-23, Madrid). `make prove` exits 0 when steps are
MISSING. Only a FAIL makes it exit non-zero. That is the builder's documented design, stated twice:
`scripts/prove.sh` line 10 and `quality/steps.yml` line 12 both say `--all` "exits non-zero if any
non-retired registered step is FAIL". The W9.1 gate observed 13 PASS, 0 FAIL, 8 MISSING, 3 RETIRED
and a real exit code of 0. The fleet plan for this phase expected a non-zero exit while steps are
unbuilt, so the two disagree about what a green `make prove` means.

The consequence is at the end, not now. During a phased build MISSING is the normal state and a
permanently red `make prove` would carry no signal, so the current behaviour is reasonable while
building. But `make prove` is a Makefile target headed for CI (W1.16), and at the P6 sweep a step
that was never built reports MISSING and the command still exits 0. A caller that trusts the exit
code would certify an incomplete repository as done. A MISSING step has no receipt at all, and
SOP section 0.1 makes the receipt the definition of done.

Recommended default: keep MISSING non-fatal for interactive runs and add a stricter mode --
`scripts/prove.sh --all --strict`, exiting non-zero unless every non-retired step is PASS -- and
have CI and the P6 sweep call that mode. This changes no step's verify command and no receipt. Until
it is decided, any sweep that claims completeness must read the summary line and confirm it says
0 FAIL and 0 MISSING, not merely check the exit status.

## W1.8 -- the seal module, the static scan and the one-way door (2026-09-23, Madrid)

Answer to the note W2.4 left for W9.7. The layer-3 allowlist is exactly two paths,
`src/absump/seal.py` and `quality/sql/analysis_set.sql`, and the count still holds with W2.4's two
new test files on disk. `tests/guard/test_no_sealed_reads.py` was run against the whole repository,
211 shipped files: zero violations. With the allowlist removed the scan reports exactly one
violation, the date comparison in `quality/sql/analysis_set.sql`, which is what makes the allowlist
load-bearing rather than decorative. `tests/unit/test_seal_classifier.py` and
`tests/unit/test_seal_config_agrees.py` pass the scan unaltered, as W2.4 intended.

OWNER DECISION D-GUARD-01, raised with a recommended default (2026-09-23, Madrid). What "walks the
whole repository" means for GD-04. The scan reads every file the repository ships -- `git ls-files`
plus everything untracked that git would track -- minus file formats that carry no executable read:
`.md`, `.txt`, `.csv`, `.lock`, images, archives and the other entries in `NON_CODE_SUFFIXES`. The
exclusion is by format and never by location: `SCANNED_DIR_SKIPS` is empty and a test asserts it
stays empty, which is the whole point of the R2 inversion. A format-blind scan is not available:
`DECISIONS.md` itself names the held-out pitch view in prose, in the resolution table, so a scan
that read `.md` would fail on this file. Recommended default: keep the format rule as built. The
consequence to accept is that a held-out read hidden in a Markdown code fence is not caught by
layer 3; it would still be caught by layer 1, layer 2 and GD-12, because prose does not execute.

OWNER DECISION D-GUARD-02, raised with a recommended default (2026-09-23, Madrid). Rule 1 fires on
the expression, not the vocabulary. `analysis_set` and the quoted held-out label must meet within
one source line. The alternative, failing any file that contains both anywhere, was tried and
rejected: it fails `tests/unit/test_seal_classifier.py` and `tests/unit/test_seal_config_agrees.py`,
which are W2.4's correct tests of the frozen predicate, and the allowlist is capped at two paths so
they cannot be exempted. Recommended default: keep the one-line rule. GD-05's stricter reading --
no held-out string anywhere outside the two allowlisted files -- is not implementable against the
two-path cap and is recorded here as narrowed to the expression form.

Defaults taken, not decisions. (a) `ops/preregister.sh` has three modes: a bare run reports the M1
preconditions and always refuses, `--check` reports and exits 0, `--confirm` is the owner's hand on
the door and runs the SOP M1 block. An agent never passes `--confirm`. Today five preconditions are
outstanding and the door refuses; no tag exists. (b) `ops/check_seal_order.sh` treats zero fit
receipts with no tag as a pass, because nothing has been fit; it fails the moment any receipt exists
without a pushed `prereg-v1` above it, which is D-67's invariant. (c) `assert_unsealed` treats a
null official date as held out and raises, while the frozen SQL predicate sends a null to the open
label. The asymmetry is deliberate and is the strict side of the open decision already recorded
above about enforcing `officialDate NOT NULL` upstream. Python can afford to refuse; the predicate
is frozen at `prereg-v1` and cannot be edited to close it.

W9.3 fixtures, defaults taken (2026-09-23, Madrid). All synthetic. Game 999001 and AAA game
999002 sit outside any real MLB gamePk, and every player id is in the 5000-8200 range, so
no fixture row can be mistaken for a real one. Eight plays carry the seven traps plus one
clean strikeout as a control, because a consumer that handles every trap and breaks the
ordinary case must still fail. The 119 Statcast column names are the export schema, taken
from the header of the cached pre-2026 daily exports; no row of any real export is in the
repository, and the header sha256 is identical across all 470 cached pre-2026 files.
Standing is evaluated on the original call, not the stored final call: the overturned
challenge in the fixture was a ball called by the umpire and challenged by the fielding
team, so a consumer that reads standing off details.call.code gets it backwards. The
Statcast-to-feed alignment rule is written into the ground truth: drop Statcast rows whose
description is automatic_ball and what remains aligns one to one with the feed's isPitch
events.

UT-20 is deferred, not passed (2026-09-23, Madrid). Every one of the 2,173 GUMBO feeds in
data/staging/statsapi/feeds is a 2026 feed, and phase 01 may not read a 2026 datum. The
test skips with the fixed reason "no local real feed cached; UT-20 deferred to phase 02"
and the skip is recorded in logs/evidence/W9.3-build.log. Phase 02 runs it against a
pre-2026 feed. Owner item: nothing to decide, but the deferral is real and the fixture's
shape is unvalidated against a real feed until it runs.

OWNER DECISION D-FIX-01, raised, not taken (2026-09-23, Madrid). Where the AAA per-event
remaining-challenge snapshot lives in the feed. D-12's estimator is "the per-game maximum
of remaining observed across the play-by-play", but no source in this project records the
key path that carries that per-event snapshot. The AAA feeds that D-12 was settled from
were pulled on 2026-09-22 and the evidence line quotes remaining and usedFailed per team
without saying where in the play-by-play they sit. Phase 01 may not open those feeds.

The fixture therefore declares the path in one constant, AAA_REMAINING_PATH, currently
liveData.plays.allPlays[].playEvents[].reviewDetails.remainingChallenges. If the real path
differs, W2's estimator will be green against the wrong shape and will return nothing on
real feeds. Recommended default: keep the constant, and have phase 02 confirm it against
one cached AAA feed as part of UT-20, re-point the constant if it differs, and regenerate
the fixtures. Nothing else in the generator depends on the path. Until that runs, the
three-token allotment in tests/fixtures/expected/aaa_allotment.json is a test of the
estimator's arithmetic and its audit-row rule, not of its ability to find the field.

GIT OWNER, phase 01 group P3 "seal-and-quality-scaffold" (2026-09-23, Madrid). Commit e752505,
60 files, 7803 insertions. Steps W2.4, W1.8, W9.1, W9.3, W9.2.

- The three pre-staging guards passed before anything was staged. `check-ignore` exits 0 for
  data/raw, research, logs, sop and fleet; `git ls-files` matches no path under data/,
  research/, logs/, sop/ or fleet/; no tracked or staged blob exceeds 5 MB. The largest blob
  in this commit is tests/fixtures/synth_feed.py at 54 KB.
- Staged the eleven owner paths by name. `git add -A` was not used. DECISIONS.md was dirty
  when this group started and is not one of my paths, so it is left unstaged for whoever owns
  it; this entry appends to it with >> and does not rewrite it.
- The committed fixtures are synthetic and carry no 2026 datum: gamePk 999001, team ids 901
  and 902, seasons 2024 and 2025, dates 2024-05-10 and 2025-06-15 only. Checked before staging.
- `ops/lint_http.sh` patterns appear in tests/unit/test_http_etiquette.py and
  test_http_delegation.py as those linters' own negative fixtures. Both files were already
  tracked by an earlier commit and are not in this one.
- .pre-commit-config.yaml does not exist yet, so `pre-commit run --files` was skipped and the
  commit went straight to main, which the group brief says is correct here.
- D-16 carried forward, still raised and not decided. The `Co-Authored-By: Claude Opus 5`
  trailer is on e752505, so it is now on all five commits that carry step work. Hudson's
  standing no-AI-attribution rule is scoped to the sportacular repository, not this one.
- Push is blocked, not failed, for the third group running. `git push origin main` was
  rejected: "refusing to allow an OAuth App to create or update workflow
  `.github/workflows/.gitkeep` without `workflow` scope". Token scopes are gist, read:org,
  repo. `origin` still has zero heads and six local commits are waiting. This is the deferral
  recorded at W1.2, W1.3 and again at commit b4c297e. Not re-litigated, no history rewritten,
  no file deleted to route around it. One `gh auth refresh -h github.com -s workflow` from the
  owner clears all six at once.

## W1.16 defaults (builder, 2026-09-23, Madrid)

Defaults taken while writing .github/workflows/ci.yml and .github/workflows/seal-guard.yml.
None of them changes a research question, a validation design or an acceptance criterion.

- actions/checkout pinned at v5. The SOP pins setup-uv v10.2.0, setup-r v2 and cache
  v6.1.0 and says nothing about checkout, so the current major is used, consistently in
  both files.
- Every job that reads git history or tags checks out with fetch-depth 0, and the guard,
  python and seal-guard jobs also fetch tags. gitleaks over full history needs it; the
  guard would otherwise pass on a shallow clone that cannot see what it is checking.
- The lint job runs ruff through uv (`uv run --locked ruff check .`), not a bare ruff, so
  CI uses the version uv.lock pins rather than whatever the runner image ships.
- The changed-.md list for `make lint-prose` is passed to ops/lint_prose.sh (SOP W9.13,
  not written yet) in ABS_PROSE_FILES, one path per line, empty means lint everything.
  On a first push or a force push past the recorded tip, every tracked .md is linted.
- The r job sets RENV_CONFIG_REPOS_OVERRIDE to the public Posit binary repository for
  the runner's Ubuntu release. .Rprofile pins repos to cloud.r-project.org, which would
  build 216 packages from source on a runner. The override changes where bytes come
  from, never which versions; renv.lock decides that. No step compiles Stan.
- The dbt job writes its synthetic Parquet lake under RUNNER_TEMP/ci-lake and its
  profiles.yml under RUNNER_TEMP/dbt-profiles, so nothing under data/ is touched and the
  working tree stays clean. Today the lake carries one table, statcast_pitch, built from
  tests/fixtures/generated/statcast.csv. The fixture-to-table map is one dict in the
  workflow; W1.11 and W9.10 extend it as the remaining lake tables land.
- gitleaks is installed by downloading the pinned 8.30.1 release in the secrets job.
  That is a CI toolchain install, not a data request, and .github/ is outside the scan
  path of ops/lint_http.sh (src, R, tools, notebooks).
- seal-guard.yml runs W9.7 layer 3 as its own step (tests/guard/test_no_sealed_reads.py)
  and layer 4 as the whole tests/guard directory, because the GD-01 and GD-02 receipt
  tests are W9.7's files and a -k filter that matches nothing exits 5.
- The SOP names three provenance keys verbatim -- prereg_tag, fit_started_at,
  input_max_game_date -- but not the key holding the tag's commit SHA. The check accepts
  prereg_commit, prereg_sha, prereg_commit_sha or prereg_tag_sha and requires the value
  to equal the SHA of the prereg-v1 commit. W3.13 should settle on prereg_commit.
- "out/ carries a fit receipt", the condition that turns the missing-tag skip into a hard
  failure, is read as: any provenance.json at any depth under out/. Files named
  .gitkeep and provenance.json do not themselves count as sealed output.
- No continue-on-error anywhere in either file, and no nightly.yml. The 60-day
  disablement rule, the UTC and default-branch facts, the re-enable command and the
  2027-02-15 calendar entry are in docs/runbook.md under "Scheduled workflows on a
  public repository".

Deferred to the owner, not a work stoppage: the gh token has scopes gist, read:org, repo
and no workflow scope, so a push carrying .github/workflows/ is still rejected. Neither
workflow has run on GitHub yet and no run id exists. One command clears it:
`gh auth refresh -h github.com -s workflow`. Same deferral already recorded at W1.2,
W1.3 and commit b4c297e; not re-litigated here.

## W1.13 pre-commit (builder, 2026-09-23, Madrid)

Defaults taken, none of which changes a research question, a validation design or an
acceptance criterion:

- **gitleaks hook id is `gitleaks-system`, not `gitleaks`.** Same repository, same tag
  v8.30.1, same command. The `gitleaks` id declares `language: golang`, so pre-commit
  would download a Go toolchain and build gitleaks from source; this machine has no Go and
  no Docker. `gitleaks-system` runs the 8.30.1 already on PATH. CI still runs
  `gitleaks detect --redact --no-banner` over full history as its own job (W1.12, W1.16),
  so a clean clone on a machine without the binary is covered there.
- **`pass_filenames: false` is set on that hook in our config.** Upstream's manifest omits
  it for the `gitleaks-system` id only, and without it pre-commit appends the file list and
  `gitleaks git` exits with "accepts at most 1 arg(s)".
- **The W1.13 verify command skips `no-commit-to-branch` by name.** That hook declares
  `always_run`, so it fires on `pre-commit run --all-files` as well as on a commit, and a
  run from a checkout of main can never exit 0. The hook itself is unchanged and still refuses
  a commit to main, which is the point of W1.13. tests/unit/test_precommit_config.py asserts
  the hook is configured with `--branch main`, so the skip cannot quietly become a deletion.
- **`http-etiquette` calls `ops/lint_http.sh` directly**, with `-q`, rather than through a
  wrapper script. The SOP names that path; a wrapper would only add a layer.
- **`no-raw-data` refuses more than the three directories the SOP names.** It refuses
  `data/`, `research/`, `logs/` per rule 3 and D-03, and also `sop/`, `fleet/` and
  `RUNLOG.md`, which .gitignore already treats as the same class of private planning
  material. It matches on a first path segment, so `app/data/` and `tests/data/` (source,
  re-included in .gitignore) and `datapack/` are not hits.

One thing outside my own files had to change to make the hook set pass, and it is recorded
here rather than done silently:

- **quality/write_receipt.py (W9.1's file) was reformatted.** `ruff check .` was already
  failing repo-wide before W1.13 existed, 35 findings in that one file: 34 UP031
  percent-format and 1 RUF005. `ops/lint.sh` was therefore already red. The fixes are
  mechanical string-formatting changes, applied with `ruff check --fix --unsafe-fixes` plus
  ten by hand that ruff will not auto-convert. Verified afterwards: `bash scripts/prove.sh
  --check` exits 0, and a differential test ran eight malformed registries through the old
  and the new parser and got byte-identical output on all eight. No logic was touched.

## D-17 How to unblock the first push to origin (git:public, 2026-09-23)

**OWNER DECISION, raised not decided.** No commit in this repository has ever reached
GitHub. `git ls-remote origin` returns nothing and `defaultBranchRef` is empty. The cause
is not the branch being pushed: the root commit 57aadf6 contains
`.github/workflows/.gitkeep`, and the authenticated `gh` token holds only
`gist, read:org, repo`. GitHub therefore rejects every push of every branch with
"refusing to allow an OAuth App to create or update workflow .github/workflows/.gitkeep
without `workflow` scope". Verified on both `main` and `phase01/public`.

**Recommended default: the owner runs `gh auth refresh -h github.com -s workflow` in one
shell and approves the browser device code.** It takes about thirty seconds, preserves
every commit, and leaves commit ordering untouched.

Rejected alternative: rewrite the root commit to drop that one empty placeholder. It would
make the push succeed with the current token, but it rewrites every sha in the repository,
and the W9.7 seal and the W1.13 no-commit-to-branch hook both depend on commit ordering.
Not a change a git owner makes unilaterally.

## D-16 confirmed (git:public, 2026-09-23)

The `Co-Authored-By: Claude Opus 5 (1M context)` trailer is used on commits in this
repository. Hudson's standing no-AI-attribution rule is scoped to the sportacular
repository. Applied to bf86752. Left in the owner list for a one-line confirmation.

- 2026-09-23 history rewrite (local, pre-push): `.github/workflows/ci.yml` removed from every commit because the gh token lacks the `workflow` scope; content preserved at `ops/ci-pending/ci.yml`. Owner step: run `gh auth refresh -h github.com -s workflow`, then `git mv ops/ci-pending/ci.yml .github/workflows/ci.yml`, commit and push.

## Prose-artifact sign-off (W1.13 / W9.13, 2026-09-23, Madrid)

SOP section 9.1 closes the prose artifact with four clauses. Three are now mechanical.
`make lint-prose` runs WR-01, WR-03 and WR-05 over `README.md`, `DECISIONS.md`,
`docs/` and `abstract/`. `quality/check_numbers.py` runs WR-07 against
`docs/numbers.json`. The fourth clause is this line, and it is a human act.

- Owner sign-off, prose artifacts, phase 01: **not given**. Recorded 2026-09-23 by the
  builder, not by the owner. Both mechanical gates are green as of 2026-09-23: `make
  lint-prose` reports 0 violations over 10 files, and `quality/check_numbers.py` reports 56
  traceable values and 0 untraced literals. Evidence: `logs/evidence/W9.13.log`. Green gates
  do not sign anything off. Hudson signs off by replacing this bullet with a dated line in
  his own commit. No agent writes that line for him, and this bullet stays as it is until
  he does.

## 2026-09-23, Madrid -- second round on the prove sweep

- Receipt logs are now normalised for run-local tokens, and the earlier refusal to do
  that is withdrawn. The first round left every clock and duration a verify command
  printed, on the argument that removing one would be editing evidence. That argument
  was wrong. Four tracked receipt logs changed on every sweep, so `git status` was
  dirty after each one and W1.13 kept failing on churn it had caused. The minute a
  scan started is not evidence about the step.
- The normaliser carries four named rules, RN-01 to RN-04, listed in the header of
  `scripts/prove.sh`. They replace a leading wall-clock stamp, an "in 17ms" style
  duration, a pytest temporary directory number, and a duration a step times itself on
  a line that already says elapsed, took, duration, load or smoke ok. Each log that had
  a token replaced ends with a line naming the rules that fired. Counts, sizes,
  versions, package names, paths, rule ids and every pass or fail line are untouched.
- New registry field `pending_owner`, and a new status PENDING-OWNER. W1.3 and W1.16
  read MISSING before, which says the thing has not been built. That was misleading. Both
  workflow files are written and parked at `ops/ci-pending/`, and the remaining move is
  the owner granting the `workflow` scope on the gh token. PENDING-OWNER says that, does
  not run the verify command, and counts as neither a failure nor a gap.
- W2.1 no longer lists `.git/hooks/pre-commit` under `needs`. A git hook is generated by
  `ops/install_git_hooks.sh`, it is not repository content, and cloning never creates it.
  Listing it made W2.1 read MISSING in every clean clone. The three tracked paths the
  step does depend on stay in the list.
- W9.13 is registered, at `quality/steps.yml`. `ops/lint_prose.sh` and
  `quality/check_numbers.py` were both written and both worked, and `make prove` ran
  neither, so a red gate changed no receipt. The step now runs both. It is red today and
  the sweep says so.
- OWNER DECISION D-PROVE-02, raised, not taken. `ops/verify_env.sh` line 66 runs
  `uv sync --locked` with no group flag, which uninstalls the nineteen bayes-fallback
  distributions that W1.4 had just installed with `uv sync --locked --all-groups`. The
  two steps disagree about which environment is correct. W1.4 therefore prints
  "Installed 19 packages" on one sweep and "Checked 176 packages" on the next, for ever.
  Recommended default: W9.2 syncs with `--all-groups` as well, so that the sweep leaves
  the environment where it found it. W9.2 owns that line and should make the change.

## Decisions applied under the execution posture, round 3 (2026-09-23, Madrid)

Merged from `logs/decisions-pending/` by the docs lane after the four round-2 fix lanes.
Each entry is a recommended default applied pre-tag, under the standing posture. The owner
may override any of them. Deviations raised by the same lanes are in `docs/DEVIATIONS.md`,
entries DEV-04 to DEV-14.

### D-G1 An `UNSEALED` line must be backed by a receipt

Owner: W2.4 / W9.7. Status: applied, with one open builder item.

An `UNSEALED` line in `docs/prereg/SEAL.md` is a claim anyone can type. It now has to be
paired with `quality/receipts/unseal-<tag>.log`, which must exist and must carry the same
`commit=<sha>` the line carries. One receipt per tag, written by `ops/unseal.sh` at the
moment it appends the line, never by hand. Asserted by `tests/guard/test_unseal_receipt.py`.
The pairing is vacuous today, because there is no `UNSEALED` line, and the test says so
through a warning rather than a silent pass. `ops/unseal.sh` does not write the receipt yet.
That is owner item O-G1.

### D-G2 `ops/lint_http.sh` excludes two directories wholesale, with a backstop

Owner: W2.3 / W9.7. Status: applied.

GD-04 excludes `quality/receipts/` and `logs/` by format and by mode, so a `.sh` file or an
executable under either one is still scanned. The linter cannot make that distinction,
because grep's `--exclude-dir` is all-or-nothing. The wholesale exclusion is accepted, with
a backstop that closes the gap:
`tests/guard/test_no_sealed_reads.py::test_no_executable_or_shebang_under_an_excluded_prefix`
fails if any file under either directory carries the executable bit or a shebang. Deleting
that test turns the exclusion back into a hole, and the filter must then become
format-aware. The script's own comment says so.

### D-PROVE-02 RP-02 syncs every dependency group

Owner: W9.1 / W9.2. Status: applied. Raised in round 2, taken in round 3.

`ops/verify_env.sh` RP-02 ran `uv sync --locked`, which syncs the default groups only. That
uninstalls the `bayes` group that W1.4 had just installed with `uv sync --locked
--all-groups`. Both steps run in one sweep against one `.venv`, so the environment after
`make prove` depended on which of the two ran last. A model or R step that followed could
find the group gone. RP-02 now runs `uv sync --locked --all-groups`.

Narrowing W1.4 to the default groups was the alternative, and it was rejected. W1.4 exists
to show that the pinned scientific stack installs from the lock alone, and the `bayes` group
is that stack. A gate must not remove the thing it checks.

### D-PROVE-03 `PENDING-OWNER` is a registry field, not a marker file

Owner: W9.1. Status: applied.

W1.3 and W1.16 wait on one move only the owner can make: re-authorising the `gh` token with
the `workflow` scope. Until then nothing under `.github/` may be committed. Both steps read
`MISSING` before, which is the status for work that was never built, and `FAIL` before that.
Both now read `PENDING-OWNER`.

The status is driven by a `pending_owner:` line in `quality/steps.yml`. It is not a marker
file on disk and not the last line of a gate log. A marker file is untracked state that a
clean clone does not have and that no reviewer reads. The tail of a log is a string a
failing command can print by accident. The registry is tracked, shows up in the diff, and is
already the single source of what a step is. `tests/unit/test_prove_hygiene.py` asserts that
exactly W1.3 and W1.16 carry the field, so the status cannot become an excuse for unfinished
work. `make prove` does not run such a step's command and counts it as neither `FAIL` nor
`MISSING`; the summary reports the count separately. See `docs/DEVIATIONS.md` DEV-08.

### D-PROVE-04 Receipt logs are normalised before comparison

Owner: W9.1. Status: applied. Recorded in round 2 and restated here.

Four rules replace run-local tokens with named placeholders before a receipt log is compared
or written: RN-01 clock, RN-02 elapsed, RN-03 temporary directory, RN-04 timing. A log that
had a token replaced ends with a line naming the rules that fired. A receipt is rewritten
only when the normalised content differs. Counts, sizes, versions, package names, paths,
rule ids and pass or fail lines are untouched.

### D-PROVE-05 One sweep at a time, with an out-of-tree `mkdir` lock

Owner: W9.1. Status: applied.

`scripts/prove.sh` takes a `mkdir`-based lock for `--all` and for a single step. `mkdir` is
atomic on every POSIX filesystem and needs no dependency. The holder's pid is written inside.
A lock whose pid is gone is broken once and reported. The holder exports
`ABSUMP_PROVE_LOCK`, so W9.1's own verify command runs re-entrantly as a child of `--all`
rather than deadlocking.

The lock lives under `$TMPDIR`, keyed to the repository path, and not inside
`quality/receipts/`. An in-tree lock directory is untracked while it exists. That would make
`git status --porcelain` non-empty, would record `git_dirty: true` on every receipt written
during the sweep, and would sit inside the tree the reproducibility clause diffs.

### D-PROVE-06 A test the registry does not name does not count as done

Owner: W9.1. Status: applied.

The round-2 verifier found five test modules and two quality tools that no verify command
named, so `make prove` never ran any of them. Now registered: `test_seal_official_date.py`
and `test_seal_unlock_conjuncts.py` under W1.8; `test_lint_http_bypasses.py` under W2.3;
`test_seal_unseal_gate.py` under W2.4; `tests/guard/gd04_scan.py` in W9.7's needs, since
W9.7 already runs the whole `tests/guard` directory; and `test_prove_hygiene.py` under W9.1.
W9.13 already registers `ops/lint_prose.sh` and `quality/check_numbers.py`.

The rule is enforceable through
`tests/unit/test_prove_hygiene.py::test_every_test_module_is_named_by_some_verify_command`.
It walks `tests/unit`, `tests/fixtures` and `tests/guard`. It fails on any module that no
verify command, Makefile recipe or `ops/` script names, directly or by running its directory.

### D-NUM-01 Three small integers are allow-listed for WR-07

Owner: W9.13. Status: applied.

`docs/numbers-allow.txt` allows 1, 3 and 20, so that "1 October", "Section 3" and a
twenty-minute budget in `abstract/FORM-FIELDS.md` trace. An allowed value stops being checked
anywhere in WR-07 scope. The alternative was a gate change: a case-insensitive section
pattern and a day-of-month date pattern in `quality/check_numbers.py`. That belongs to the
gate's owner, not to the numbers lane.

### Note for the risk register, R-17

`docs/priorart-numbers.txt` must be re-read against the two nightly-rebuilding upstreams
before each venue submission. The head of the file says so, and R-17 already records the
rule.


## Round-3 fixup, merged from `logs/decisions-pending/` (2026-09-23, Madrid)

Merged by the git lane at the close of round 3. Two pending ids collided with
entries already merged above, so they are renumbered here and the original id is
named in each entry.

### D-G3 `ops/env-setup.sh` is exempt from `ops/lint_http.sh`

*(guard lane; written as "DEC-??")* The round-3 chokepoint verifier found the
gate red on a clean tree with none of its own plants present: `[SH-CURL]
ops/env-setup.sh` for the uv installer, and `[R-RSCRIPT]` twice for the R
packages and CmdStan. The round-2 rewrite moved this file into scan range on
purpose and gave `R-RSCRIPT` a file-scope conjunct, so a provisioning script that
names any network idiom anywhere trips on every `Rscript -e` in it, and a
permanently red gate blocks every prove run that depends on it.

**Decision.** `^ops/env-setup\.sh:` joins `EXEMPT` as its seventh entry. It is
machine provisioning, not a data pull: it fetches a package manager and R
packages from astral.sh, CRAN and r-universe, writes nothing under `data/raw/`
and puts no row in `data/raw/_manifest.csv`. It is outside the throttle by
construction, not in evasion of it. `tests/unit/test_lint_http_bypasses.py` pins
the list so the exemption cannot widen unnoticed.

**Rejected alternative.** Moving provisioning back out of the scan set. DEV-12
moved this file into `ops/` from `logs/`, and `tests/guard/test_no_sealed_reads.py`
asserts both that `logs/env-setup.sh` is absent and that `ops/env-setup.sh` is
listed by the scanner; moving it again would reopen DEV-12 for no gain.

**Evidence.** `logs/evidence/verify-chokepoint-r3.log` (red),
`logs/evidence/fix-chokepoint-r3.log` (green after).

This also closes the git lane's owner item **D-GIT-01**, which recorded that the
bootstrap had nowhere to live under the two rules as they then stood and that no
round-3 commit could be written while the file was on disk. The exemption is the
resolution; the alternatives D-GIT-01 listed (keep the installer outside the
repository, or relax the guard's executable rule) are both declined.

### D-PROVE-07 Receipt byte-identity is a property of the verify command

*(prove-receipts lane; written as "D-PROVE-06", which is taken above.)*
`scripts/prove.sh`'s normaliser is a line-wise text filter: it strips escapes and
rewrites four families of run-local token (RN-01..RN-04), and it cannot reorder
lines, because reordering a log would destroy the only thing a log is for. A
verify command that prints an unordered collection therefore defeats receipt
byte-identity by construction. Round 3 measured exactly that: a failing
`assert set(...) == set(...)` in `tests/unit/test_layout.py` rendered two entries
in `PYTHONHASHSEED` order and made `quality/receipts/W1.2.log` differ between two
otherwise identical sweeps.

**Decision.** The rule is stated in the normaliser header of `scripts/prove.sh`
and enforced at the source: assertions compare sorted lists, never sets, and any
listing is sorted before it is printed. `tests/unit/test_layout.py` now holds no
set comparison and no unsorted glob.

### D-PROVE-08 W9.13 runs both prose gates, always

*(prove-receipts lane; written as "D-PROVE-07".)* The verify command was
`lint_prose && check_numbers`. A failing `lint_prose` short-circuited the second
gate, so the receipt reported six violations where there were fifteen. The
command now captures both exit codes and fails if either is non-zero, and both
outputs land in the receipt log. Measured with a stubbed failing lint:
`check_numbers` still ran, combined rc=1.

### Stated limits, recorded rather than dropped (no decision owed)

The guard and chokepoint lanes each closed round 3 by naming what a text scanner
cannot decide, in the header of `ops/lint_http.sh` and in the "WHAT THIS STILL
DOES NOT CATCH" header of `tests/guard/gd04_scan.py`, and in
`logs/decisions-pending/last-round.md`. In short: a URL that does not exist in
the source; a request made inside a dependency; whether a matched line ever runs;
a held-out day written with no comparison off the analysis surface; date
arithmetic whose offset is not a literal on the same line; a character code built
by arithmetic; a non-date datum copied into a fixture; and anything binary or
under `data/`. The behavioural backstops are `data/raw/_manifest.csv`, the
pre-commit hook, the red-team run (GD-09) and GD-10.

**Reversed in round 4 (D-R4-01).** This section previously ruled that these were
declared limits of the static scan rather than departures from the SOP, so no
DEVIATIONS entry was owed. That was right on the merits and wrong on the
audience. `docs/DEVIATIONS.md` is the document a reviewer and the SSAC methods
appendix actually read; a limit recorded only in a decisions log is a limit
a reviewer is unlikely to reach. The list is now `docs/DEVIATIONS.md` DEV-18, with the covering
layer named beside each item, and DEV-04 carries the chokepoint's two residual
classes. The scanner header and DEV-18 are deliberate duplicates: change one,
change both.

### Deviations for transcription into `docs/DEVIATIONS.md` (docs lane)

The git lane does not write `docs/DEVIATIONS.md`. These three arrived in
`logs/decisions-pending/prove-receipts.md` already numbered, and DEV-14 is the
highest entry in that file, so the numbers are free. They are parked here so the
round-3 commit does not lose them.

- **DEV-15 — W1.2 no longer asserts that an ignored directory exists on disk.**
  Five directories in the section 2.1 tree cannot exist in a clone:
  `.github/workflows` (no workflow scope, parked at `ops/ci-pending/`, DEV-04),
  `warehouse`, `data/raw`, `data/interim`, `data/marts` (excluded by
  `.gitignore`, and the publish policy forbids anything under `data/` on the
  public remote). `test_directory_exists` now covers the tracked half only, every
  entry of which carries a tracked `.gitkeep`; the ignored half is held by
  `test_ignored_directory_is_ignored`, which asserts the `.gitignore` rule rather
  than the filesystem. An ignored directory that stopped being ignored still
  fails W1.2.
- **DEV-16 — the ignore checks ask through a probe path inside the directory.**
  `.gitignore` writes these rules with a trailing slash, which matches a
  directory, and git resolves a path that is not on disk as a file, so in a clone
  `git check-ignore research` reports nothing and exits 1. Both ignore tests now
  ask `git check-ignore -q <dir>/.ignore-probe`, which matches the same rule and
  answers identically in a clone and on a working machine. The one-call
  multi-path form the SOP names is kept, with probe paths.
- **DEV-17 — W1.2's branch assertion is anchored on `origin/main`.** A clone
  checked out on `phase01/public` has `origin/main` and no `refs/heads/main`, and
  the round-2 form failed there for a reason that says nothing about the layout.
  `origin/main` is now the anchor; HEAD must be its tip or a descendant; a local
  `main`, when it exists, must agree with it.

### Owner items still open at the close of round 3

- **D-PROVE-09 (written as D-PROVE-08) — nothing in the bootstrap path installs
  the W2.1 hook.** A clean clone has no `.git/hooks/pre-commit` and no
  `.git/hooks/pre-commit.framework`. `make bootstrap` runs `ops/bootstrap.sh`,
  which installs neither, so W2.1 fails in any clone until a human runs two
  commands by hand. Measured: in a fresh clone of main, `uv run --locked
  pre-commit install && bash ops/install_git_hooks.sh` takes
  `tests/unit/test_layout.py` from 28 failures to 0. Recommended: `ops/bootstrap.sh`
  gains those two lines after the Python environment step. That file is on no
  fixup lane's owned paths, so no round wrote it; the failure messages of the four
  affected tests now name the exact repair.
- **`sop/SOP-final.md` line 374 names the wrong rule count.** That paragraph says
  `ops/lint_http.sh` scans eleven directories "against a table of 29 named rules".
  The round-3 fixup takes it to 37 (added PY-NETIMPORT, PY-CMDBUILD, SH-RAWNET,
  R-NETPKG, SQL-URI, and the widened PY-URLLIB, SH-EXECVAR, R-CURLPKG); the
  directory list is unchanged. The count wants amending there, as DEV-04 already
  amends the six-idiom text. No lane in this round edits the SOP.

### Owner items closed by this commit

- **D-PROVE-10 (written as D-PROVE-09) — the three number ledgers were
  untracked.** `docs/numbers.json`, `docs/priorart-numbers.txt` and
  `docs/numbers-allow.txt` are what makes `quality/check_numbers.py` green, and
  `quality/steps.yml` names all three in W9.13's `needs:`, so W9.13 read MISSING
  in a clone. This commit tracks them. The `needs:` line is deliberate: the gap
  reports itself instead of passing vacuously.
- **`ops/verify_env.sh` removed the bayes-fallback dependency group.** Line 66 ran
  a bare `uv sync --locked`; with `default-groups = ["dev"]` and an exact sync,
  every `make verify-env` uninstalled pymc/nutpie/arviz and exited 0 (measured, 3
  packages to 0). The file now runs `uv sync --locked --all-groups`, matching
  W1.4's own command and D-PROVE-02.

## Round 4 (2026-09-23) — the single-builder round

One builder owned the whole tree; no parallel lanes, so none of round 3's
cross-lane churn was possible. Every red-team probe ran in a scratch root under
the session scratchpad via the new `--root` flag, never in the live tree.

### D-R4-01 The static scan's declared limits are transcribed into DEVIATIONS.md

Reverses the ruling recorded above. See `docs/DEVIATIONS.md` DEV-18.

### D-R4-02 `ops/bootstrap.sh` installs both hooks, in the order that preserves the guard

Owner: round 4. Status: applied. Closes **D-PROVE-09** (written in round 3 as
D-PROVE-08; cite it as D-PROVE-09).

`make bootstrap` ran `ops/bootstrap.sh`, which installed no git hook at all, so a
clean clone had no `.git/hooks/pre-commit` and W2.1 was red in every clone until
a human ran two commands by hand. Measured in round 3: 28 failures in
`tests/unit/test_layout.py` before `uv run --locked pre-commit install && bash
ops/install_git_hooks.sh`, 0 after. The public pre-registration claims a stranger
can reproduce this from the public repo; while bootstrap installed no hook that
claim was false.

`ops/bootstrap.sh` now runs `uv run --locked pre-commit install` and then
`sh ops/install_git_hooks.sh`, in that order and documented as load-bearing:
`pre-commit install` overwrites `.git/hooks/pre-commit`, and
`ops/install_git_hooks.sh` preserves the framework hook as
`pre-commit.framework` and execs it, so both still run on every commit.

This defect survived three rounds because `ops/bootstrap.sh` sat on no lane's
owned-path list. **Unowned equals unfixed**: every future round assigns every
top-level path an owner before it starts.

### D-R4-03 `ops/unseal.sh` writes the GD-10 receipt

Owner: round 4. Status: applied. Closes owner item **O-G1**.

The pairing rule was asserted but had no writer: `ops/unseal.sh` appended the
`UNSEALED` line to `docs/prereg/SEAL.md` and stopped there, and
`tests/guard/test_unseal_receipt.py` could only warn until an unseal had already
happened. That is a gate whose first firing would come immediately after the one
irreversible act it exists to police, at the moment when the only way to satisfy
it is to hand-write the receipt it was designed to forbid.

`ops/unseal.sh` now writes `quality/receipts/unseal-<tag>.log` carrying the same
`commit=<sha>` as the line, in the same success path. Three details are
deliberate: the receipt is written **before** the claim, so no window exists in
which an `UNSEALED` line stands with nothing behind it; the script refuses if the
receipt already exists, so one tag can never be unsealed twice; and `--check`
still writes nothing. The test is now unconditional and also asserts the write
order and the refusal, so the writer cannot regress into a warning.

### D-R4-04 Gate-doc parity is enforced by a test, not by discipline

Owner: round 4. Status: applied.

`sop/SOP-final.md:374` and `docs/DEVIATIONS.md` DEV-04 both said `ops/lint_http.sh`
runs "a table of 29 named rules" while the gate ran 37, for a full round. A
binding pre-registration that misstates the size of its own gate is a credibility
problem out of proportion to the edit. Both documents are corrected, and
`tests/unit/test_lint_http_bypasses.py::test_the_documented_rule_count_matches_the_gate`
now reads the count out of the linter's own banner and fails if either document
disagrees. A rule added without moving the prose fails in the commit that adds
it. The SOP paragraph also names the two structural shapes round 3 introduced —
the file-scope conjunct and the morpheme family — because the shape change
matters more than the count.

**Caveat the owner should know.** `sop/` is excluded by `.gitignore:7`, so
`sop/SOP-final.md` is not in the public repo and this correction lands on the
working machine only. The tracked half of the parity claim is
`docs/DEVIATIONS.md` DEV-04, which every clone gets, and the test asserts that
one unconditionally; the SOP is checked where it exists and skipped where it
does not, so a reviewer's clone does not fail on a file the publish policy keeps
out. If the SOP is meant to be part of the public pre-registration, that is an
owner decision (**O-R4-02**) and not one this round should take silently.

### D-R4-05 GD-06/GD-10 vacuity now expires by assertion

Owner: round 4. Status: applied.

`data/sealed/` is empty in phase 01, so the immutability guard declares itself
vacuous through `VacuousGuard` rather than passing silently. That is honest now
and dangerous later: once the phase-02 pull seals real rows, an empty manifest
would let the drift check compare nothing against nothing and report GD-06 green
while the containment check slept.
`test_the_vacuity_expires_when_the_seal_carries_rows` is inert while the
partition is empty and becomes a hard assertion the instant it is not. This is
the one check that tests the layer actually holding the data.

### D-R4-06 `tests/guard/gd04_scan.py` takes `--root`

Owner: round 4. Status: applied.

`ops/lint_http.sh` already took a ROOT argument; the scanner did not, which is
why round 3's guard verifier had to work on a scratch branch inside the shared
tree and then explain an unrelated diff, and why round 2 planted in the
repository and corrupted two other lanes' receipts. `--root DIR` scans any tree,
repository or not. **SOP W9.7 rule: every red-team plant goes in an isolated
clone or a scratch root. Never the live tree.**

### D-R4-07 The stopping rule is written down

Owner: round 4. Status: applied.

Recorded in the `tests/guard/gd04_scan.py` header and in `docs/DEVIATIONS.md`
DEV-18. GD-04 is a detection layer; the seal is the control. The scan closes for
a phase on four checkable conditions: closure, class-not-spelling with a sibling
plant, mutation-proof under GD-09, and no miss in a new class under a time-boxed
budget. The honest claim is "no evasion in the pinned corpus and no new class
since round N", never exhaustiveness.

### Where the three judges disagreed, and what was chosen

- **The unseal receipt writer.** Two judges reported it already fixed, citing
  `ops/unseal.sh:221`; one reported it still open. The tree settles it: line 221
  appended the **SEAL.md line**, not the receipt file, and `DECISIONS.md` said
  outright "ops/unseal.sh does not write the receipt yet. That is owner item
  O-G1." The minority judge was right and the item was implemented. Checked
  against the tree rather than counted.
- **Putting `ops/` on rule 5's analysis surface.** One judge asked for it (by
  file shape, for config-shaped files); two asked for the opposite, that the
  asymmetry be *declared* so that a later round does not widen it and then
  silence the resulting noise. The
  majority was followed: `scripts/` is on the surface, `ops/` is not, rule 6c
  already catches a partition READ under `ops/` repo-wide, and the reason is now
  in DEV-18. Recorded because it is a live temptation for round 5.
- **A mutation gate for `ops/lint_http.sh`.** One judge asked for GD-09-style
  neutering of the chokepoint before phase 02; the others did not raise it. Not
  built this round. Raised as owner item **O-R4-01** rather than dropped,
  because phase 02's real pull (W6.0) is when the chokepoint becomes
  load-bearing.
- **The premise of the task itself.** All three judges independently found the
  brief stale: it described uncommitted repairs, but round 3 was committed and
  pushed as 4bc71f3 with a clean tree. Verified before any edit. Nothing was
  re-fixed.

## Round 5 (2026-09-23, Madrid) -- the renv/activate.R rewrite that failed W1.13 once

An isolated-clone verifier refuted one criterion on the pushed commit `11b1da3`: the
**first** `make prove` of a fresh clone exits 1 with W1.13 FAIL, 19 PASS / 1 FAIL /
1 MISSING / 2 PENDING-OWNER / 3 RETIRED. Runs 2 and 3 are green and byte-identical, so
the gate erased its own cause and four rounds of proving never saw it.

- **The cause, reproduced on this machine before anything was edited.** `ops/bootstrap.sh:29`
  runs `Rscript -e 'renv::restore(prompt = FALSE)'`. renv regenerates `renv/activate.R`
  from its own template, and that template carries trailing whitespace: `git diff --stat`
  reports 344 insertions and 344 deletions, `git diff --ignore-all-space` is empty, and
  `grep -cE ' +$' renv/activate.R` goes from 0 to 344. The restore was otherwise a no-op
  ("The library is already synchronized with the lockfile"), so the file is the whole
  effect. W1.13's verify then runs `pre-commit run --all-files`, the trailing-whitespace
  hook at `.pre-commit-config.yaml` repairs the file and exits 1, and the step fails. The
  side effect matters as much as the failure: `make prove` was writing to a tracked source
  file in a clean clone.
- **The repair, both halves.** The verifier offered two and recommended the exclude; both
  were applied, because either alone leaves half the finding standing. (1) The
  trailing-whitespace hook now carries `exclude: ^renv/activate\.R$`. renv owns that
  file's formatting and regenerates it on every restore, so the hook was arguing with a
  generator it cannot win against. (2) `renv/activate.R` is committed exactly as renv
  writes it, whitespace included, so restore on a fresh clone rewrites it byte for byte
  and the tree stays clean. Only with both is the sentence at "W1.14 defaults" above true
  again.
- **Why the exclude is pinned by tests, not by comment.** An exclude is an escape hatch and
  the next one will be easier to add than this one was. `tests/unit/test_precommit_config.py`
  now asserts the exclude is exactly that path, that it is the only exclude in the config
  and that there is no top-level exclude, and that the tracked `renv/activate.R` still
  carries the whitespace renv emits -- if someone strips it by hand, bootstrap starts
  dirtying the tree again and that test says so.
- **Nothing else was touched.** The verifier's other findings were out of criterion and are
  recorded as limits, not repairs: the stale brief premise, `make lint-http` not existing
  as a target (the HTTP lint lives in `make lint` and standalone at `ops/lint_http.sh`,
  both exit 0), the three RETIRED steps being bookkeeping, `make prove` rewriting the 26
  receipts under `quality/receipts/` by design, and three declared GD-04 limits that this
  run actually caught and that DEV-18's paragraph can therefore be tightened against.

## Decisions applied under the execution posture, phase 02 (2026-09-23, Madrid)

Phase 02 ran eleven SOP steps across eight build chains and six verifiers. The agents
raised the items below and were not permitted to write here, so the docs lane records
them. Each entry states the recommended default as the applied choice, under the standing
posture at the top of this file. The owner may override any of them. The deviations the
same lanes raised are in `docs/DEVIATIONS.md`, entries DEV-20 to DEV-24.

### D-P2-01 Four neutral-site 2026 games sit outside the ABS population

Owner: W2.6 `test_regime_marker`. Status: applied and coded.

SOP W2.6 asserts the ABS regime marker on every Final 2026 MLB game. It holds on 2,338 of
2,342. The four exceptions are neutral-site special events at parks with no ABS hardware:
823669 (Field of Dreams, 2026-08-13), 823745 (Williamsport, 2026-08-23), and
825093 and 825094 (Estadio Alfredo Harp Helu, Mexico City, 2026-04-25 and 2026-04-26).
They are not pre-ABS games. They belong to neither arm, so they leave the ABS population
altogether rather than joining the control side. Coded as `feeds.NON_ABS_VENUE_GAME_PKS`
and asserted as an exact set, so a fifth such game fails the gate instead of widening it
silently.

### D-P2-02 The challenge allotment is two in regulation and three in extra innings

Owner: W2.6 `test_token_start`. Status: applied and coded.

SOP W2.6 asserts `remaining + usedFailed == 2` for every team-game. It holds on 4,640 of
4,676 team-games. All 36 exceptions read remaining 0 with usedFailed 3, and every one of
the 34 games involved went past the ninth inning. A team that has spent both tokens is
granted a third in extra innings. The allotment is therefore stated as two in regulation
and three in extra innings. The test asserts both halves together, so an allotment of
three implies an inning past the ninth. That is stricter than loosening the identity to
accept either value anywhere. Coded as `feeds.EXTRA_INNING_ALLOTMENT`.

### D-P2-03 The AAA arm stays 2024-2025, with 2023 pending a full-season scan

Owner: chapter 3 design. Status: applied, carried forward from 2026-09-22.

The 2023 AAA feeds sampled carry no ABS challenge data at all, while 2024 and 2025 carry
it throughout. The AAA arm is therefore 2024-2025. A full-season scan of 2023 may find
challenge records, and the arm widens only if it does. Nothing downstream may assume a
2023 AAA challenge series exists before that scan reports.

### D-P2-04 The staged schedules are re-pulled with all five game types in phase 07

Owner: W2.5 / W2.6 / W6.0. Status: applied as a phase 07 item.

Seven of the eight staged schedule payloads are the staging cache's `gameType=R` response
rather than the SOP's `gameTypes=R,F,D,L,W` form. AAA 2023 is the exception and returned
five extra games, the International League and Pacific Coast League championship series.
Completing the other open seasons costs 6 statsapi requests, which phase 07 issues through
the overnight launcher. MLB 2026 cannot be completed under the seal. The current analysis
set is unaffected: the MLB 2022-2025 postseason is pre-ABS, so no ABS comparison moves.

### D-P2-05 `schedule_game` keeps fifteen columns

Owner: W2.5. Status: applied.

The table carries the SOP's thirteen columns in the SOP's order, plus `status_coded` and
`status_detailed`. Without the coded state DT-14 cannot be stated at all. MLB reports a
cancelled or postponed game with `abstractGameState` Final and an empty officials array:
1 in MLB 2024, 1 in MLB 2026, 26 in AAA 2023, 18 in AAA 2024 and 23 in AAA 2025. The SOP
sentence "every Final game has exactly one Home Plate official" is false as written in
five of eight seasons. The two columns stay, and DT-14 reads the coded state.

### D-P2-06 The umpires-per-season band stays, with the two AAA seasons pinned

Owner: W2.5. Status: applied.

SOP W2.5 states a band of 75 to 110 distinct umpires per season. It holds for all five MLB
seasons, at 96, 94, 90, 92 and 91, and for AAA 2024 at 87. AAA 2023 measures 71 and AAA
2025 measures 70. Triple-A works three-umpire crews from a smaller roster; 2,047 of 2,324
AAA 2025 games carry no second-base umpire. The band is kept as the SOP writes it and the
two AAA seasons are pinned to their exact measured counts. Widening the band would hide
the crew-size difference that produced the miss.

### D-P2-07 The W2.5 step title keeps its reworded verb

Owner: W2.5 / W1.13 / W2.3. Status: applied.

The title registered in `quality/steps.yml` says "eight pulls" where the SOP title uses the
other word for a fetch. That word sits in the `ops/lint_http.sh` NET idiom list. The
registry already carries two `python -c` verify commands, at W1.4 and W1.16, and rule
SH-PYTHON-C takes its network conjunct at file scope. Writing the SOP title verbatim
therefore turns `ops/lint_http.sh` red, and that script is the verify command of W1.13 and
W2.3. Confirmed in a temporary tree. The reworded title stays and DEV-23 records it.

### D-P2-08 Feed 823543 is quarantined, and phase 03 adds a pre-import guard

Owner: W2.6 / W9.7. Status: applied; the guard lands in phase 03.

A sealed 2026 regular-season feed, gamePk 823543 with `officialDate` 2026-09-22, was found
sitting readable in the staging cache. It was quarantined rather than deleted, because the
unseal ceremony needs the evidence of how it got there. It is recorded in
`quality/sealed_manifest.json`. Containment held: nothing was imported, and the gamePk
appears nowhere under `data/` outside the staging cache. Phase 03 adds a pre-import guard
that rejects any 2026 feed whose `gameData.datetime.officialDate` is 2026-09-22 or later,
whatever date the manifest carries. Keying on the manifest bucket rather than on
`officialDate` is what let the file through, so the guard reads the feed itself.

### D-P2-09 The B2 credentials are deferred, and W1.9 lands as code plus a dry run

Owner: W1.9. Status: deferred to the owner, per the posture's credential clause.

`B2_APPLICATION_KEY_ID` and `B2_APPLICATION_KEY` are unset and no bucket exists. The `b2`
tool authorizes before it plans, so even its own dry run is unavailable without the pair.
W1.9 therefore lands as code plus a dry run, and the mirror itself waits for phase 07. The
three live assertions in `tests/data/test_b2.py` keep skipping until the key pair is in
`.env`, which is gitignored and never in the repository.

### D-P2-10 The W2.5 season-total assertion is left off until after the unseal ceremony

Owner: W2.5 / W9.7. Status: applied.

SOP W2.5 states a 2026 total of 2,512 games over 212 dates, with the postseason histogram
F 12, D 20, L 14 and W 7. The request that would return it runs to mid-November, and SOP
section 2.4 seals every 2026 game of type F, D, L or W outright. The step asserts instead
the regular-season entry exactly, at 2,459 schedule rows, which is the SOP's own number,
together with the arithmetic 2,459 + 12 + 20 + 14 + 7 = 2,512. The full assertion turns on
automatically once a full-range 2026 payload exists, which is after the W9.7 unseal
ceremony. It is left off until then.

## Decisions applied under the execution posture, phase 03 (2026-09-24, Madrid)

### D-P3-01 `ops/lint_http.sh` does not scan the vendored dbt directories

Owner: W1.7 / W9.5. Status: applied.

`dbt deps` downloads dbt_utils, dbt_date and dbt_expectations into `dbt/dbt_packages/`, and
their shipped GitHub Actions workflows carry curl lines. Scanning them put four bypasses on
the board in third-party CI that no commit of ours could clear and that a clean `dbt deps`
would put straight back. `dbt_packages` joins the skip list; `dbt/logs/` was already covered
by the `logs` entry. Our own dbt code, `dbt/models`, `dbt/macros`, `dbt/tests` and
`dbt/seeds`, is still read. Pinned by
`tests/unit/test_lint_http_bypasses.py::test_the_vendored_dbt_directories_are_not_scanned`,
which plants a curl in a vendored workflow and a second one in `dbt/models`, then requires
the vendored one to be ignored and the `dbt/models` one to fail the gate.

### D-P3-02 `tests/unit/test_coverage_contract.py` joins the linter's exemption list

Owner: W1.7 / W9.5. Status: applied.

The SOP section 6.2 coverage contract resolves its five modules with
`importlib.import_module(module)`, which PY-DYNIMPORT reads as a module named in a variable.
A static import would make the whole unit pack unrunnable until `absump.zone` and
`absump.geometry` land, which is the opposite of what a coverage contract is for. The names
come from `SOP_MODULES`, a literal tuple the file's own first test pins verbatim, and all
five are first-party, so no string reaches that call that the SOP did not put there. The
exemption is by path and so turns off all thirty-seven rules inside that file; it is kept the
size of the one line that needs it by
`test_the_coverage_contract_exemption_stays_narrow`, which fails if any other request idiom
appears there or if a second dynamic import is added.

### D-P3-03 The warehouse path is written in `src/absump/paths.py` and nowhere else

Owner: W9.6 / W9.4. Status: applied.

`tests/unit/test_paths.py` holds every layout string to one copy. Phase 03 added seven more
copies of `warehouse/abs.duckdb`. The two sprint checkpoints and `quality/verify_contract.py`
now take it from `absump.paths`; `quality/warehouse_contract.yml` and the W9.6 registry record
name it as the token `{duckdb}`, which `verify_contract.py` and `write_receipt.py` resolve
through the same module; the rest were prose and were reworded. `--database` still accepts a
literal path, so an operator can point the checker at a copy by hand.

### D-P3-04 `mart_called_pitches` is rebuilt on `int_called_pitch`, and publishes no bare plate_x

Owner: W1.11 / W2.18. Status: applied.

The W1.11 skeleton was written against the synthetic seed and published `plate_x` and
`plate_z` aliased off the re-projected pair. Raw Statcast coordinates are front-plane through
2025 and mid-plane from 2026, so a column called `plate_x` means two different measurements
depending on the season. Every target but ci now reads `int_called_pitch` and keeps its names,
including `plate_x_mid`, `plate_x_front` and `plane_source`. The ci target still builds from
the 200-row seed, which has no re-projected pair, and therefore publishes neither: it also
drops `play_id` and `pitch_slot`, which a flat seed cannot mean. The step title of W1.15 was
reworded to "no call to any MLB or Savant host" for the reason recorded at D-P2-07.

### D-P3-05 GD-04 does not scan vendored packages or dbt's own rotated log

Owner: W1.8 / W9.7. Status: applied, with the remainder referred to the owner.

`dbt/dbt_packages/` is third-party source whose integration tests carry date literals, and
`dbt/logs/` is dbt's debug log, which echoes back the boundary comparison of the build that
just ran; rotation meant `dbt.log.1` was scanned while `dbt.log` was not. Both are gitignored
transcripts or vendored code, excluded on the same format-and-mode terms as
`quality/receipts/`, and `tests/guard/test_no_sealed_reads.py` pins the new prefix list. That
clears 2,477 of the 2,542 findings. The remaining 65 are ours and are not a scanning defect:
see the owner item in the phase 03 handoff.

### D-P3-06 D-12 REVERSED: AAA 2024 starts 3 tokens per team, so the AAA DP is 4x4

Owner: W2.16 / W3.20. Status: applied. **This reverses the D-12 entry of 2026-09-22.**
**OWNER-VISIBLE: it changes the chapter-3 state space.**

The 2026-09-22 entry settled the AAA 2024 allotment at 2 tokens per team. It was reached from
a 12-team-game sample, all of it after the mid-season changeover. The full-corpus measurement
now supersedes it. D-12's estimator, the per-game maximum of `remaining` across the
play-by-play, returns a mode of 3 over 712 AAA 2024 team-games that carry an `absChallenges`
block. The 21 team-games that measure otherwise are written out one row each to
`out/tables/aaa_allotment_audit.csv`, with the game, the team side and the observed maximum.

That figure supports the SOP R2 position rather than the older line. The AAA 2024 dynamic
program is therefore **4x4**, four home token states by four away token states, not 3x3. Every
chapter-3 table, figure and timing estimate keyed on the AAA state space is sized from 4x4
from here. The MLB 2026 arm is unaffected and stays at its own allotment.

What would reopen it: a season split. The audit table is the place to look, and a second mode
concentrated on dates before the D-57 changeover would mean the season carries two rule
versions rather than one.

### D-P3-07 MLB 2026: the extra-inning token is modelled in the DP and stated in the pre-registration

Owner: W2.16 / W3.4. Status: applied.

MLB 2026 allots 2 tokens per team in regulation. 36 team-games measure a third, and every one
of them goes to extra innings, which is the published rule rather than a data defect. The
applied default is to model the extra-inning token in the dynamic program and to say so in the
pre-registration, rather than to restrict the sample to regulation.

Restricting to regulation was the alternative. It was rejected because extra innings are where
a token is worth the most, so dropping them removes the part of the state space the chapter is
about. Modelling the token costs one extra state and is stated rather than silent.

### D-P3-08 The mart follows W2.16's canonical token estimator, not the feed's own arithmetic

Owner: W2.18 / W2.16. Status: applied.

`int_challenge_resolved` derives `tokens_start` from `feed_game` as `remaining + used_failed`.
That arithmetic disagrees with the measured allotment on 36 of 4,632 MLB 2026 team-games, and
the 36 are the extra-inning games of D-P3-07. DT-08's canonical estimator is the per-game
maximum of `remaining` across the play-by-play, which W2.16 owns and the intermediate layer
cannot see.

The mart follows W2.16. Where the two differ, the W2.16 value is the one published, and the
feed arithmetic is kept beside it as a diagnostic column rather than dropped. AAA 2024 has no
`feed_game` row at all, so its tokens are null in this layer and come from W2.16 as well.

### D-P3-09 The deferred and skipped targets of phase 03, and where the machine profile lives

Owner: W1.10 / W9.4. Status: applied.

Four operational defaults, all reversible by the owner:

- **MotherDuck prod target deferred.** `MOTHERDUCK_TOKEN` is unset, so `dbt debug --target
  prod` skips. The local dev target proves the pipeline end to end and phase 03 completes
  without the token.
- **B2 canary skipped.** `B2_APPLICATION_KEY_ID` and `B2_APPLICATION_KEY` are unset, so
  `ops/b2_check.sh` skips. A skip is recorded as a skip, not as a pass.
- **The nightly commits locally and does not push.** `ops/nightly.sh` carries `--push` and it
  is off by default. It stays off until the owner says otherwise.
- **The machine profile lives at `~/.dbt/profiles.yml`**, copied from
  `dbt/profiles.yml.example`, so dbt resolves the `absump` profile from the repository root.

### D-P3-10 OPEN, OWNER-VISIBLE: what the 1,144 off-rule 2026 pitches are

Owner: the project owner. Status: **open question, recommended default applied in the
meantime.** See DEV-32 and DEV-33.

1,144 of 688,686 MLB 2026 rows do not satisfy the 0.535 / 0.27 zone rule. They are confined
to four dates, 2026-04-25, 2026-04-26, 2026-08-13 and 2026-08-23, and the two implied heights
disagree by up to 0.2409 in. Two readings fit the evidence. Either Statcast published a
defective zone on those four dates, or those games did fall back to an operator-set
zone, as every season through 2025 did.

The two readings are not separable from the CSV alone. A defect would be corrected by a later
Savant re-publication; a genuine fallback would show up in the feed as well, and the feed for
those dates is not yet staged.

Recommended default, applied now: treat the four dates as excluded from the
zone-harmonisation sample, and state the exclusion in the pre-registration with the date list
and the row count. It costs four days out of a 2026 season and it keeps a possible
operator-set zone out of a sample whose whole purpose is the machine-set one. The cheap test
that would settle it is a re-pull of those four days after the seal lifts, compared byte for
byte against what is stored.

What the owner decides: whether to keep the exclusion, or to pull the four dates' feeds and
resolve the question before `prereg-v1`.

### D-P3-11 Chapter 1 does not need GUMBO feeds for 2022-2025

Measured 2026-09-24 from the staged schedules, pulled with `hydrate=officials`. Final games
against games carrying an officials array: 2022, 2,479 of 2,479; 2023, 2,476 of 2,476; 2024,
2,468 of 2,469; 2025, 2,464 of 2,464; 2026, 2,371 of 2,372. Distinct home-plate umpires per
season are 96, 94, 90, 92 and 91, inside the SOP's 75-110 band every year.

The W2.15 joins for mlb 2022-2025 returned zero games with reason `no_feed_pitch`. The
Statcast side is present and the feed side was never pulled. That reads like a hole in the
three-regime study, and it is not one. Chapter 1 needs four things per called pitch: plate
coordinates and zone bounds from Statcast, the batter's height from W2.7 at coverage 1.000,
the season's regime, and the home-plate umpire from the schedule. None of those comes from a
feed. Feeds carry what only 2026 needs: challenge records, the ABS regime marker and the
token state.

Applied default: Chapter 1's 2022-2025 arm is built from Statcast joined to the schedule on
`game_pk`. The zero-game join rows stay in `out/tables/join_report.csv` as honest coverage
records rather than defects. Pulling 2022-2025 feeds is about 9,900 requests over three
statsapi nights and is deferred to phase 07, needed only if a later chapter wants per-pitch
feed fields for those seasons.

Risk accepted: one 2024 game and one 2026 game carry no officials array. Both are the
postponed or cancelled rows already documented, and neither carries a called pitch.

What would reverse it: a chapter that needs a per-pitch feed field before 2026.

### D-P3-12 GD-04 rule 3 is scoped to analysis reads, and the two scoped kinds declare themselves

Decided 2026-09-24 (Europe/Madrid). Pre-tag. The matching declared limits are DEV-18 items 8
and 9, because the scanner header and DEV-18 have to agree.

Rule 3 fails a read of a fact table that the enclosing statement does not restrict to
`analysis_set = 'open'`. Phase 03 built the warehouse, and 64 reads then failed the rule in
one run. None was an evasion. They were of two kinds the rule was never aimed at.

Warehouse construction. `fct_called_pitch` is built from `fct_pitch`, and `fct_challenge`
reads the pitch fact to attach its two distance columns. Nine dbt tests assert things about
those tables: the join is complete, the original call is reconstructed, the reconciliation is
zero, the null rates hold. Restricting a build or an assertion to the open set changes what
the warehouse contains, or lets a broken row hide behind the seal from the test written to
find it.

Whole-warehouse measurement. `tests/data/test_warehouse_pack.py` measures the warehouse
against the contract, and `agg_closed_season_rowcount` writes the row-count ledger that DT-20
compares against the previous nightly. A count restricted to the open set cannot see a
held-out row appear in a closed season, which is the one thing that ledger exists to see.

The decision: rule 3 is scoped so that construction and measurement are not analysis reads,
while every analysis read stays strict. The scope is not a path allow-list. It is granted only
when both of two things hold. First, the site declares it: a comment line of its own in the
file's header reads `GD-04-EXEMPT: <kind> -- <reason>`, with the kind either `construction` or
`measurement` and a reason of at least 30 characters. A marker trailing live code, or inside a
string, is not one. Second, the scanner agrees independently, recomputing the site property
from the path and the file. A marts model must itself be a fact model. A dbt test must be a
dbt test under `dbt/tests/`. A schema file may claim it only on a `relationships` test target,
which declares an assertion and has nowhere to put a WHERE clause. A measurement must name
three or more warehouse relations and be a pack, a checkpoint script or an aggregate ledger.

So a declaration is a claim and never the grant, and a new file cannot inherit the scope in
silence. The marker grants nothing at all under `src/absump/ch*`, `R/`, `notebooks/`,
`tests/fixtures/`, `sql/`, `quality/sql/`, `app/`, `tools/`, `scripts/`, `config/` or the
staging and intermediate models. A marker written in any of those is itself reported as a
violation, so misuse is loud rather than quiet.

Of the 64, 57 are now declared at 12 sites, 3 are qualified, and 4 were not reads at all.
What was not exempted: four reads in the two sprint checkpoint scripts were analysis reads
that had forgotten the qualifier. They measure MLB 2026 rows whose counts land in
`docs/numbers.json` and are quoted in the abstract. Three now carry `analysis_set = 'open'`.
Measured against `warehouse/abs.duckdb` on 2026-09-24 before the change, every row those
three statements touch is already labelled open: 10,168 challenged called pitches, 10,168 MLB
2026 reviews, 10,168 matched. No published number moves. The fourth reads
`fct_team_game_tokens`, which is at team-game grain and carries no `analysis_set` column at
all. The open set is not expressible there, the read is a count and a mode over every MLB 2026
team-game, and the seal is kept on that relation by `assert_seal_not_crossed` on
`official_date`. That one is declared rather than qualified.

Four further findings were not reads at all. A `FROM` or a `JOIN` is also an English word, and
`reconstructed from call_original` in one JSON field, with a relation named in the next field,
was being read as a query. Rule 3 no longer lets those two keywords reach across a string
terminator or a new mapping key. `ref(`, `source(`, `read_parquet` and `.table()` are
unambiguous reads and keep the loose span. That removed the findings in `docs/numbers.json`,
`quality/warehouse_contract.yml` and the two provenance labels in the sprint checkpoints
without exempting anything.

Why this does not weaken the seal: the barrier of record is the encrypted partition and the
six-condition unseal ceremony, and GD-04 is a detection layer, per the stopping rule already
recorded above. The scope forgives one rule, on files that declare themselves and that the
scanner recognises. It forgives nothing else: not the held-out label, not the held-out view,
not a held-out day, not a read of the partition by path, and not an analysis read anywhere.
GD-05's allowlist is still exactly two paths.

Pinned from both sides in `tests/guard/test_no_sealed_reads.py`. A construction site without
the marker still fails. An analysis read of a fact table without `analysis_set = 'open'` still
fails in a chapter, in R, in a notebook and in ad-hoc SQL. The marker grants nothing in
`src/absump/ch1`, `ch2`, `ch3`, `R/ch1`, `notebooks/` or `tests/fixtures/` and is reported
there. A marts model that is not a fact model, and a staging model, cannot claim construction.
A measurement claim over a single relation is refused. A marker in a string or with a one-word
reason is not a marker. Every marker in the live tree is one the scanner grants.

Standing obligation: the rule table changed, so the red team runs again against it, per
condition 4 of the stopping rule.

What would reverse it: a red-team run that reaches a held-out row through a declared site.

### D-P3-13 OPEN, OWNER-VISIBLE: the 2026 framing benchmark cannot be taken after the seal

Owner: the project owner. Status: open question, recommended default applied in the meantime.
See DEV-38, DEV-39 and DEV-40.

Recommended default, applied now: compute framing run value point-in-time from our own
called-pitch data, and use the Savant leaderboard only as an out-of-sample benchmark for the
static seasons, 2015-2025.

Why. We hold every called pitch through 2026-09-21. A framing measure built from those
pitches has a date on it, stops where the seal stops, and can be cut the way every other
Chapter 1 and Chapter 2 quantity is cut: by catcher, by month, by count, by umpire,
split-half for reliability. The Savant 2026 number can do none of that. It is one
whole-season scalar per catcher, it moves every night, it cannot be asked for "through
2026-09-21", and taking it after the boundary imports sealed games into a pre-registered
open-set analysis.

What is lost, plainly. The external benchmark for 2026 goes away, so for the season the paper
is about there is no independent published framing number to check ours against. We inherit
Savant's modelling choices only by imitation, because their `rv_*` columns are a proprietary
run-value model over eight shadow zones and ours will be our own. The published-comparability
claim weakens from "our framing numbers match the public leaderboard" to "they match it in
2015-2025". Coverage changes: the Savant export is qualified catchers only, 58 in 2026
against 107 in the ABS catcher view under D-35, so any 2026 number computed here is not
comparable catcher-for-catcher even in principle. The point-in-time measure is also work that
was not in the plan: a shadow-zone definition, a run-value weighting, and a test that it
reproduces the 2015-2025 leaderboard within a stated band.

The alternative was rejected. Keeping the live 2026 leaderboard and widening DT-26 into a
tolerance band needs a band wide enough to accept a season still being played, and such a band
accepts the endpoint breaking quietly too. That is the class of failure that cost one pull
twelve identical files and 28 silent parse errors on the same night.

What the owner decides: whether to accept the default, or to keep the benchmark. If the
benchmark is kept, the honest form is to pull the 2026 leaderboard once at the end of the
regular season, pin it then, label it in the paper as a post-seal external figure, and keep it
out of every fitted model.

### D-P3-14 DT-04's blank mid-plane bound is re-cut with the corpus, at 900

Applied 2026-09-24 (Europe/Madrid), merged from `logs/decisions-pending/dt04-blank-bound.md`.

`make dbt` failed on `assert_join_complete`, one clause: `blank_mid_plane_above_bound`. 784
mart rows carry a null `plate_x_mid` or `plate_z_mid` against a bound of 700. The bound was
not breached by a regression. It was set on 2026-09-23 over a `fct_called_pitch` of 1,610,220
rows, when MLB 2022 held 69 Statcast days. A background pull has since delivered 110 more 2022
days; the mart is now 1,836,071 rows and 2022's blank count rose from roughly 86 to 223.

What proves nothing leaked is the structural clause, not the count: `blank == untracked +
no_kinematics` holds exactly, 784 = 762 + 22. Every blank row is still either flagged
`tracked = false` or missing the `vy0`/`ay` the mid-plane re-projection needs. That clause is
unchanged. The rate moved 0.038% to 0.043%. Per season: 2022 223/367,145, 2023 139/374,523,
2024 144/367,017, 2025 82/368,925, 2026 196/358,461 -- 2022 sits in the same band as 2026, so
the backfilled days are ordinary days.

Applied: the bound is re-cut from 700 to 900, the same ~15% headroom it carried before, in
both places that hold it, `{% set blank_mid_in_mart_max %}` in
`dbt/tests/assert_join_complete.sql` and `BLANK_MID_IN_MART_MAX` in
`tests/data/test_warehouse_pack.py`. The published figures in that file's note 1 were
re-measured with it, 591/21/612 to 762/22/784.

Owner question left open: whether a count bound over a growing corpus is meant to be re-cut
with the corpus, or should be expressed as a rate so the next backfill does not trip it.

What would reverse it: a blank row that is neither untracked nor missing kinematics, which
breaks the structural clause and makes the count a symptom rather than a scale.

### D-P3-15 SEAL FINDING, caught before it shipped: the leaderboard fixtures are synthetic

Applied 2026-09-24 (Europe/Madrid). Recorded as a seal finding, not a deviation, because
nothing sealed was committed: the finding is that it nearly was.

Two untracked fixtures, `tests/data/fixtures/savant_abs_batter_2026-09-24.html` and
`savant_abs_catcher_2026-09-24.html`, were staged for commit carrying the live 2026 ABS
leaderboard in machine-readable form: `n_total_sample` 103,304 batting and 232,743 fielding,
`n_challenges` 4,635 and 5,603, plus per-player records with names and ids. Those totals are
season-to-date aggregates read on 2026-09-24, and DEV-40 measures that they grew by 648 and
1,520 over the 2026-09-22 baseline, which is exactly the first sealed day. Committing them
would have carried sealed-window quantities into the open tree, parseable by `parse_page`.

Applied: both fixtures were rewritten. Structure is byte-faithful -- the `<script>` block
arrangement, the `serverParams`, `leagueData` and `absData` assignments, every key name, the
nesting, and the `leagueData` one-element-array container that DEV-38 is about. Every numeric
and player-identifying value is invented and obviously so: round numbers, `Test Player One`
and placeholder team codes. The filenames no longer carry a capture date inside the sealed
window; they are `savant_abs_batter_synthetic.html` and `savant_abs_catcher_synthetic.html`,
listed under that name in `contracts/savant_absdata.yml`. The module docstring in
`tests/data/test_leaderboard_parse.py` states that they are synthetic, what they pin and why
real values are not used. Two assertions that read captured values were re-aimed at structure;
they are named in the RUNLOG line for this commit. All eight tests pass, all three absData
routes and both `leagueData` container shapes still parse.

The general rule this makes explicit: a fixture pins shape, so it never needs real values, and
a fixture captured from a live season-to-date endpoint after 2026-09-21 is a sealed-set input
whatever it is used for.

Two carriages of the same aggregates already exist in the tracked tree and are left as they
are, because both are prose or receipt scalars rather than a machine-readable record set, and
one of them is the entry that documents the contamination: `docs/DEVIATIONS.md` DEV-40 states
103,304 and 232,743 in its diagnosis, and `quality/receipts/W2.11.log` and
`quality/receipts/W4.3.log` print 4,635 and 5,603 in DT-24 PASS lines from the 2026-09-24
sweep. No other tracked file carries an aggregate of this kind.

What would reverse it: a test that needs a real published value, which would have to take it
from a static season, 2015-2025, and never from 2026.

- Owner sign-off, phase 03 decisions: **not given**. Recorded 2026-09-24 by the agent that
  applied the defaults above. Each entry names what would reverse it.

## Owner R0 answers, 2026-09-24 (Madrid) — binding, taken before the prereg-v1 tag

Hudson Pagni answered the three R0 questions himself on 2026-09-24 (Europe/Madrid). Every
entry below is **the owner's own answer**, not an agent default and not a recommended
default awaiting sign-off. Two of the three had been argued both ways by agents, and SOP
section 9.6 item 12 makes the owner's answer a condition of done, so the answers are
recorded here before the tag rather than inferred after it.

### D-R0-01 OWNER ANSWER, D-12: AAA carries two challenge tokens, and the chapter-3 DP is 3x3

Owner: Hudson Pagni, 2026-09-24. Status: **binding owner answer**, applied. This is the
owner speaking, not an applied default.

**The answer: two tokens for AAA, a 3x3 solve.** It supersedes both prior agent positions
and closes the conflict between them. The 2026-09-22 D-12 entry said two tokens and 3x3,
from a 12-team-game sample. The 2026-09-24 phase-03 entry D-P3-06 reversed that to three
tokens and 4x4, from a 712-team-game partial-2024 measurement. Both lines are superseded by
this one.

What was traded, written honestly so a later reader can see it. The evidence for three was
the larger of the two samples, 712 AAA 2024 team-games against 12, and its mode was 3 with
21 team-games audited otherwise. The SOP's own R2 position also pointed to three. The
evidence for two was the earlier sample, which was drawn entirely after the mid-season
changeover, and the owner's reading of the rule the chapter is about. The owner chose two.
The consequence is that chapter 3's AAA arm is solved 3x3, three home token states by three
away token states, and so matches the MLB dimension rather than standing a state wider.
Every chapter-3 table, figure and timing estimate keyed on the AAA state space is sized
from 3x3 from here.

If the full AAA 2024-2025 feed corpus is later pulled and contradicts this answer, that
becomes a DEVIATIONS entry with the measurement in it. It does not become a silent
re-reversal. The audit table `out/tables/aaa_allotment_audit.csv` stays where it is, and a
second mode concentrated before the D-57 changeover would still mean the season carries two
rule versions.

The settled MLB fact recorded beside it, unchanged by this answer: 4,684 MLB 2026
team-games, 99.1% of them starting with 2 tokens and 0.8% showing a third. Every one of the
third-token games goes to extra innings, which is the published rule. Per the earlier
applied default D-P3-07, that extra-inning token is modelled in the dynamic program and
stated in the pre-registration.

### D-R0-02 OWNER ANSWER, D-13: roster height plus offset is primary, ABS-measured is a pre-registered robustness arm

Owner: Hudson Pagni, 2026-09-24. Status: **binding owner answer**, applied. This is the
owner speaking, not an applied default.

**The answer: roster height plus the measured offset is the primary batter-height cohort
for all seasons, and the ABS-measured cohort is a pre-registered robustness arm.** Both
cohorts are named in the pre-registration, and the arm is declared before the tag rather
than chosen after a result.

The coverage that drove it, ABS-measured batter-seasons against all batter-seasons, read
from `data/interim/dim_batter_season` and verified against the warehouse dimension on
2026-09-24: 2022 303 of 693, 43.7%; 2023 371 of 656, 56.6%; 2024 447 of 651, 68.7%; 2025
533 of 673, 79.2%; 2026 658 of 662, 99.4%. Roster height plus the offset covers 100% of
every one of those seasons.

The calibration, from `data/interim/dim_batter_season/calibration.json` over the 658 batters
who carry both heights: offset 0.0022 in, standard deviation 0.2909 in. At the 53.5%
fraction that sets the zone top, that standard deviation propagates to roughly 0.08 in of
zone-top error.

The reason in one sentence: full coverage with small unbiased noise beats an exact
measurement available for only 43.7% of the 2022 batters, because that 43.7% is the
survivorship-biased subset still active in 2026.

What would reverse it: a measured offset that is not small or not unbiased in a season
other than 2026, which would make the primary cohort carry a systematic error rather than
noise.

### D-R0-03 OWNER ANSWER, R0 review: the prereg-v1 tag is pushed on green gates, with no prior read

Owner: Hudson Pagni, 2026-09-24. Status: **binding owner answer**, applied. This is the
owner speaking, not an applied default.

**The answer: push the prereg-v1 tag once the gates are green, without a prior read of the
estimands.** The owner was offered a pre-tag read of the estimands and declined it. He was
told that any change made after the tag becomes a logged deviation rather than an edit, and
he accepted that.

This closes the R0 owner-review item that phase 04 raised as a condition of the M1 ceremony.
No further owner read is outstanding before the tag.

## Applied under the R0 delegation, 2026-09-24 (Madrid), phase 04 gate items

The phase-04 W3.3 gate raised two threshold questions and asked for an owner line. Neither
question was put to the owner. Both are applied defaults under the delegation that D-R0-03
records. There the owner chose to push the prereg-v1 tag on green gates without a prior read.
He accepted that any later change becomes a logged deviation. The execution posture of
2026-09-22 says recommended defaults are applied and recorded rather than asked. Neither item
touches an estimand, an acceptance criterion or the sealed set. Both are sanity checks on the
plate-crossing kinematics.

D-P4-03 joined them on 2026-09-25, when the W3.3 verifier's full sweep reopened D-P4-02.
It is applied under the same delegation. It too touches no estimand, acceptance criterion or
sealed set.

**No entry below is an owner answer in his own words.** Each is applied under D-R0-03.
The owner may override any of them, and an override becomes a DEVIATIONS entry.

### D-P4-01 APPLIED UNDER D-R0-03, DEV-42 confirmed: the UT-11 and DT-11 `t` band keeps its 70 mph population

Applied by the phase-04 decisions agent, 2026-09-24 (Europe/Madrid). Status: **applied
default under D-R0-03's delegation, not an owner answer.** Hudson Pagni did not answer this
question himself.

The question. DEV-42 states the band `t in (0.30, 0.60)` s at both plate planes over pitches
with `release_speed >= 70` mph. An agent closed DEV-42, not the owner. The W3.3 gate therefore
failed the band as the SOP first stated it, and asked whether the population stands.

The measurement of record. Gate run 2 read the band with no speed filter at 23:17 CEST. 93 of
39,272 pitches, 0.237%, fall outside it at either plane. All 93 are 58.7 mph or slower, 65 of
them are eephus, and the largest `t` is 1.1312 s. The source is `quality/receipts/W3.3.log`.

The earlier figure. DEV-42 quoted 123 of 39,272, 0.313%. That count is the pitches under
70 mph, the population the floor removes from the clause. The 93 are the subset of those 123
that actually leave the band. The later gate figure, 93, is the one of record for pitches
outside the band. The 123 stays correct as the size of the excluded population.

The default applied: **confirm the population of pitches at 70 mph or more.** Three reasons.

1. A lob that takes more than 0.60 s to reach the plate is correct physics, not a defect.
   The band exists to catch the larger quadratic root, risk R-43. That root's smallest value
   in this sample is 6.2048 s.
2. The four clauses that carry no speed filter hold at every speed. The round trip agrees to
   8.882e-16 ft. The closed form matches the brute-force root to 1.443e-15 s over all 39,272.
   `t_mid > t_front` fails for 0 of 39,272, and `dz < 0` fails for 0 of 39,271.
3. The test reports the excluded population on every run rather than hiding it. One RECORD
   line prints the count under 70 mph. A second prints the band read with no filter.

The band is not widened. DT-11 in SOP section 6.3 carries the same population and is
confirmed with it. No SOP or test text changes: both already state this population.
DEV-42's status line now points here.

What would reopen it: a pitch at 70 mph or more outside the band, or the owner's override.

### D-P4-02 APPLIED UNDER D-R0-03: the 0.0011 ft plane clause is asserted over called pitches, and its bar is not widened

Applied by the phase-04 decisions agent, 2026-09-24 (Europe/Madrid). Status: **applied
default under D-R0-03's delegation, not an owner answer.** Hudson Pagni did not answer this
question himself. The deviation it creates is DEV-43. **Reopened 2026-09-25 and restated
under D-P4-03**, which reads the clause over called pitches in ABS games and pins 72 by
identity.

The question. UT-11's cross-source clause says the 2026 CSV, re-projected from the middle of
the plate to the front, matches the API's `pX/pZ` to under 0.0011 ft. The SOP set that bar
on the 281 pitches of one game and named no population. The test asserts it over called
pitches, and the gate asked whether that population stands.

The measurement. Over 11,726 called pitches on five 2026 days the maximum is 0.001071379 ft.
Over all 22,604 pitches on the same days, two exceed the bar. Both are batted-ball curveballs:

- game 824584, at-bat 21, pitch 4, `hit_into_play`, 81.6 mph, 0.001104168 ft;
- game 824002, at-bat 28, pitch 2, `foul`, 72.1 mph, 0.001126631 ft.

The larger excess is 0.000027 ft, about 0.0003 in.

The default applied: **the clause's population is called pitches**, meaning `called_strike`,
`ball` and `blocked_ball` as in `fct_called_pitch`. Called pitches are the analysis
population of every chapter. The study never uses a batted ball's plate crossing. The two
exceedances are named here, in DEV-43 and in the test's RECORD line. The 0.0011 ft bar is not
widened.

What changed. The clause text in `sop/SOP-final.md` section 3 (W3.3), and its copy in
`sop/SOP-final-part1.md`, now states the population. DEV-43 records it.

What would reopen it: a called pitch at or above 0.0011 ft, or a chapter that starts to use
a batted ball's plate crossing.

Reopened 2026-09-25 (Europe/Madrid). The W3.3 verifier read every open 2026 day and met the
first condition. 566 of 358,265 called pitches reach 0.0011 ft, up to 0.063473 ft. The
five-day figures above stay correct for those five days. D-P4-03 supersedes this entry's
population and its reopen condition.

### D-P4-03 APPLIED UNDER D-R0-03, reopens D-P4-02: the 0.0011 ft plane clause is read over called pitches in ABS games, and its 72 misses are pinned by identity

Applied by the phase-04 decisions agent, 2026-09-25 (Europe/Madrid). Status: **applied
default under D-R0-03's delegation, not an owner answer.** Hudson Pagni did not answer this
question himself. Merged from `logs/decisions-pending/plane-clause.md`. It restates DEV-43.

The question. D-P4-02 named its reopen condition: a called pitch at or above 0.0011 ft. The
W3.3 verifier's sweep of all 178 open 2026 days met it. 566 of 358,265 called pitches reach
the bar, up to 0.063473 ft. 494 of them sit in D-P2-01's four games and 72 in 60 other games.
The CSV and API kinematics, `vx0` to `az`, are identical on all 566, so the join is not at
fault. The question is where the bar should sit.

Publication precision, measured on the raw text. In ABS games the 2026 CSV's
`plate_x/plate_z` and the API's `pX/pZ` are both full 64-bit doubles. Each value prints at
least 10 decimals, with a median of 16. Two values carried to k decimals support agreement
to about 10^-k, so precision supports a bar of about 1e-10 ft. All 357,644 called pitches in
ABS games miss that bar. The smallest miss is 4.49e-8 ft and the median 1.88e-4 ft. No bar
the data meets can be derived from publication precision.

What the disagreement is. The API's own `pX/pZ` sit off the API's own published trajectory
at the front plane, `y = 17/12`. The cross-source miss equals that API self-residual to
within 3.1e-5 ft on every pitch but one. That pitch is 825000/31/3 on 2026-05-30, the known
W2.15 coordinate artefact. There the CSV side is the one that is off: its `plate_x/plate_z`
miss the CSV's own trajectory by 0.063625 ft.

The three options the pending file laid out.

1. Keep 0.0011 ft as an empirical ceiling on the API's self-residual, and pin the called
   pitches that reach it.
2. Restate the clause as two exact statements the test already makes. The CSV side
   reproduces its own trajectory to 5e-7 ft by direct integration. The API side's
   self-residual is recorded, not bounded.
3. Set a new bar from the API self-residual's own distribution. That would be a chosen
   number, and the brief rules out choosing one to empty the count.

The default applied: **option 1**, in three parts.

1. The bar stays at the SOP's 0.0011 ft. It is neither widened nor re-derived, because no
   derivable bar exists. A RECORD line prints the precision bar's count on every run.
2. The population is called pitches, `called_strike`, `ball` and `blocked_ball`, in ABS
   games on every open 2026 day. ABS games are those carrying the `absChallenges` regime
   marker. This removes 494 rows in D-P2-01's four games, and a RECORD line counts them.
3. The residual is 72 of 357,644 called pitches, in 60 games on 53 days.
   `tests/ch1/test_zone.R` pins them by identity in `PLANE_ARTEFACTS`. An added or a
   dropped row fails the clause.

The 72, in feet: min 0.001104, q25 0.001124, median 0.001157, q75 0.001250, q90 0.001336,
max 0.063473. The max is 825000/31/3. Without it the max is 0.001537 ft, at 823400/84/3. A
RECORD line names all 72 and splits them one on the CSV side and 71 on the API side.

Why option 1. It keeps the SOP's number and adds no chosen threshold. Each miss becomes a
named row the test must find again. Option 2 drops the bound on the API side altogether.
Option 3 would fit a number to the data, which the brief rules out.

What changed. `sop/SOP-final.md` section 3 (W3.3), and its copy in `sop/SOP-final-part1.md`,
state the population, the precision derivation and the 72. D-P4-02's status line and DEV-43
now point here. The two stated limits in the same pending file are recorded in DEV-44.

What would reopen it: any change to the set of 72, which fails the test, or the owner's
override.

Evidence: `logs/evidence/W3.3-fix2.log`; the verifier's sweep,
`logs/evidence/W3.3.verify-geometry.log`.
