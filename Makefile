# Makefile -- abs-umpires. SOP step W1.14.
#
# GNU Make 3.81 only. That is what ships with macOS 26.6 and it is what runs
# here: no .ONESHELL, no ::=, no $(file ...), no grouped targets (&:), no
# .RECIPEPREFIX. Recipe lines are tabs. Risk R-23 in the SOP is a Make 4 file
# mis-executing under 3.81, so `make --version` is checked in ops/preflight.sh
# and tests/unit/test_makefile.py rejects Make 4 syntax in this file.
#
# THE ONE-LINE-DELEGATION RULE. No target holds logic. Every target is exactly
# one recipe line that delegates to a script. Later SOP steps own the bodies of
# several of these targets and are built in parallel, so each of them writes its
# script and never edits this file. Where a script does not exist yet it is a
# placeholder that prints one line naming its owning step and exits 0, so both
# `make -n <target>` and `make <target>` work today. The comment above each
# target names the step and fleet phase that owns the body.
#
# Every target name below is the SOP W1.14 list, verbatim and complete, plus
# `unseal` (SOP W2.4). Target names are never invented and never renamed.

SHELL := /bin/sh
.DEFAULT_GOAL := help

.PHONY: help preflight bootstrap py r lint fmt test test-unit test-data \
        test-model test-model-fast test-guard prove prove-guard-redteam \
        determinism verify-env verify-contract smoke r-smoke dbt warehouse \
        normalize-statcast \
        b2-push b2-pull disk disk-check seal-check preregister unseal \
        backfill inseason pull-today nightly canary lint-prose \
        ch1 test-ch1 ch2 test-ch2 ch3 test-ch3 ch3-extract \
        p8 p8-test p8-odds-fetch p8-sealed \
        sprint-status \
        app app-deploy abstract all clean clean-out clean-warehouse

# ---------------------------------------------------------------- environment

# owner: SOP W1.14, fleet phase 01
help: ## print every target with its one-line description
	bash ops/help.sh

# owner: SOP W1.1, fleet phase 01
preflight: ## disk floor, PATH, empty DYLD_LIBRARY_PATH, CmdStan 2.40.0
	bash ops/preflight.sh

# owner: SOP W1.14, fleet phase 01
bootstrap: ## preflight, then the Python and R environments
	bash ops/bootstrap.sh

# owner: SOP W1.4, fleet phase 01
py: ## sync the Python environment from uv.lock, all groups
	uv sync --locked --all-groups

# owner: SOP W1.5, fleet phase 01
r: ## restore the R library from renv.lock
	Rscript -e 'renv::restore(prompt = FALSE)'

# owner: SOP W9.2, fleet phase 01 -- writes ops/verify_env.sh
verify-env: ## RP-01..RP-08, the environment gate, expects 6/6 OK
	bash ops/verify_env.sh

# owner: SOP W1.15, a later fleet phase -- writes ops/smoke.sh
smoke: ## the 12-check smoke test, no MLB or Savant request
	bash ops/smoke.sh

# owner: SOP W1.5, fleet phase 01
r-smoke: ## R stack, CmdStan fit, rhat < 1.01
	Rscript R/00_setup.R

# ---------------------------------------------------------------- lint and format

# owner: SOP W1.14, fleet phase 01 -- calls ops/lint_http.sh (SOP W1.7)
lint: ## ruff check, ruff format --check, HTTP call-site lint
	bash ops/lint.sh

# owner: SOP W1.14, fleet phase 01
fmt: ## ruff format and ruff check --fix, in place
	bash ops/fmt.sh

# owner: SOP W7.5, fleet phase 04 -- delegates to quality/prose_lint.py (SOP W7.1).
# SOP section 2.8 names one prose linter, quality/prose_lint.py: W7 rules 1 to 11,
# the ban list, WR-01 to WR-08 and the P8 ban list. CI sets ABS_PROSE_FILES, one
# path per line, and the linter reads it. ops/lint_prose.sh stays with W9.13.
lint-prose: ## prose lint for human-facing text, quality/prose_lint.py
	uv run --locked python quality/prose_lint.py

# ---------------------------------------------------------------- tests

# owner: SOP W1.14, fleet phase 01
test: ## the offline suites: unit, fixtures, guard
	bash ops/test.sh

# owner: SOP W9.5, a later fleet phase -- writes tests/unit
test-unit: ## UT-* unit tests, about 60 s
	uv run --locked pytest tests/unit -q

# owner: SOP W9.6, a later fleet phase -- writes tests/data
test-data: ## DT-* data tests, 75-180 s
	uv run --locked pytest tests/data -q

# owner: SOP W9.8, a later fleet phase -- writes tests/model
test-model: ## MT-* model gates, 30-70 min, outside the push gate
	uv run --locked pytest tests/model -q

# owner: SOP W9.8, a later fleet phase -- writes tests/model
test-model-fast: ## the MT-* subset marked fast
	uv run --locked pytest tests/model -q -m fast

# owner: SOP W9.7, fleet phase 01 -- writes tests/guard
test-guard: ## GD-* sealed-guard tests, git and file scan only
	uv run --locked pytest tests/guard -q

# owner: SOP W9.7, fleet phase 01 -- writes tests/guard/redteam_run.sh
prove-guard-redteam: ## the red-team run against the four-layer guard
	bash tests/guard/redteam_run.sh

# owner: SOP W9.1, fleet phase 01 -- writes scripts/prove.sh
prove: ## run every step's registered verify command
	bash scripts/prove.sh --all

# owner: SOP W9.9, a later fleet phase -- writes ops/determinism.sh
determinism: ## two clean runs of `all`, compare sidecars at 1e-8
	bash ops/determinism.sh

# owner: SOP W9.4, a later fleet phase -- writes ops/verify_contract.sh
verify-contract: ## the warehouse contract, table by table
	bash ops/verify_contract.sh

# ---------------------------------------------------------------- data and warehouse

# owner: SOP W1.11, fleet phase 01 -- writes ops/dbt.sh
dbt: ## dbt deps, parse and build against the local target
	bash ops/dbt.sh

# owner: SOP W2.14, fleet phase 03 -- writes ops/normalize_statcast.sh
normalize-statcast: ## W2.14 typed Statcast days, both plate planes, 799 days in 17 s
	bash ops/normalize_statcast.sh

# owner: SOP W2.14, fleet phase 03 -- writes ops/warehouse.sh
warehouse: ## build the DuckDB warehouse from Parquet
	bash ops/warehouse.sh

# owner: SOP W6.0, fleet phase 02 -- writes ops/backfill.sh
backfill: ## the full throttled backfill, resumable, safe to re-run
	bash ops/backfill.sh

# owner: SOP W2.22, fleet phase 03 -- writes ops/inseason.sh
inseason: ## yesterday and today: schedule, feeds, Statcast, dbt, tests
	bash ops/inseason.sh

# owner: SOP W2.22, fleet phase 03 -- writes ops/pull_today.sh
pull-today: ## today's schedule and feeds only
	bash ops/pull_today.sh

# owner: SOP W2.22, fleet phase 03 -- writes ops/nightly.sh
nightly: ## the local launchd nightly, 03:30 Europe/Madrid
	bash ops/nightly.sh

# owner: SOP W1.10, a later fleet phase -- writes ops/b2_push.sh
b2-push: ## push the raw cache to Backblaze B2
	bash ops/b2_push.sh

# owner: SOP W1.10, a later fleet phase -- writes ops/b2_pull.sh
b2-pull: ## pull the raw cache from Backblaze B2
	bash ops/b2_pull.sh

# owner: SOP W1.10, a later fleet phase -- writes ops/b2_check.sh
canary: ## the B2 canary: one small round trip, skippable
	bash ops/b2_check.sh

# ---------------------------------------------------------------- disk and seal

# owner: SOP W1.14, fleet phase 01
disk: ## report free disk and the size of the heavy directories
	bash ops/disk.sh

# owner: SOP W1.14, fleet phase 01
disk-check: ## fail below the 15 GiB floor (SOP W1.1, risk R-25)
	bash ops/disk_check.sh

# owner: SOP W1.14, fleet phase 01; extended by SOP W9.7, fleet phase 01
seal-check: ## sealed-side checks that need no data: lock, provenance, env
	bash ops/seal_check.sh

# owner: SOP W1.8, fleet phase 01 -- writes ops/preregister.sh
preregister: ## the one-way door: freeze PREREGISTRATION.md and tag prereg-v1
	bash ops/preregister.sh

# owner: SOP W2.4, fleet phase 01 -- writes ops/unseal.sh
unseal: ## the unseal gate; refuses unless the prereg tag is an ancestor
	bash ops/unseal.sh

# ---------------------------------------------------------------- chapters

# owner: SOP W3.x, fleet phase 08 -- writes scripts/ch1.sh
ch1: ## chapter 1 pipeline
	bash scripts/ch1.sh

# owner: SOP W3.x, fleet phase 08 -- writes scripts/test_ch1.sh
test-ch1: ## chapter 1 acceptance tests
	bash scripts/test_ch1.sh

# owner: SOP W4.x, fleet phase 09 -- writes scripts/ch2.sh
ch2: ## chapter 2 pipeline
	bash scripts/ch2.sh

# owner: SOP W4.x, fleet phase 09 -- writes scripts/test_ch2.sh
test-ch2: ## chapter 2 acceptance tests
	bash scripts/test_ch2.sh

# owner: SOP W5.x, fleet phase 10 -- writes scripts/ch3.sh
ch3: ## chapter 3 pipeline
	bash scripts/ch3.sh

# owner: SOP W5.x, fleet phase 10 -- writes scripts/test_ch3.sh
test-ch3: ## chapter 3 acceptance tests, including the BR-1 regression
	bash scripts/test_ch3.sh

# owner: SOP W5.x, fleet phase 10 -- writes scripts/ch3_extract.sh
ch3-extract: ## materialise the open-set extracts chapter 3 reads
	bash scripts/ch3_extract.sh

# ---------------------------------------------------------------- P8

# owner: SOP W8.x, fleet phase 14 -- writes scripts/p8.sh
p8: ## the P8 betting layer, open set only
	bash scripts/p8.sh

# owner: SOP W8.x, fleet phase 14 -- writes scripts/p8_test.sh
p8-test: ## P8 acceptance tests
	bash scripts/p8_test.sh

# owner: SOP W8.x, fleet phase 14 -- writes scripts/p8_odds_fetch.sh
p8-odds-fetch: ## fetch odds through the one HTTP client
	bash scripts/p8_odds_fetch.sh

# owner: SOP W8.x, fleet phase 14 -- writes scripts/p8_sealed.sh
p8-sealed: ## the sealed-window P8 run, after the W9.7 ceremony only
	bash scripts/p8_sealed.sh

# ---------------------------------------------------------------- deliverables

# owner: SOP W7.x, fleet phase 12 -- writes scripts/app.sh
app: ## run the Shiny app locally
	bash scripts/app.sh

# owner: SOP W7.x, fleet phase 12 -- writes scripts/app_deploy.sh
app-deploy: ## deploy the Shiny app
	bash scripts/app_deploy.sh

# owner: SOP W6.x, fleet phase 06 -- writes scripts/abstract.sh
abstract: ## build the SSAC abstract from its slots
	bash scripts/abstract.sh

# owner: SOP W6.4, fleet phase 03 -- writes ops/sprint_join_checkpoint.py
sprint-status: ## W6.4 refresh the SSAC sprint status and the join slots
	uv run --locked python ops/sprint_join_checkpoint.py

# owner: SOP W9.9, a later fleet phase -- writes scripts/all.sh
all: ## the whole pipeline, the unit determinism is checked on
	bash scripts/all.sh

# ---------------------------------------------------------------- clean

# owner: SOP W9.9, a later fleet phase -- writes ops/clean.sh
clean: ## clear data/tmp and the build caches, keep out/ and the warehouse
	bash ops/clean.sh

# owner: SOP W9.9, a later fleet phase -- writes ops/clean_out.sh
clean-out: ## clear out/, the generated-output root
	bash ops/clean_out.sh

# owner: SOP W9.9, a later fleet phase -- writes ops/clean_warehouse.sh
clean-warehouse: ## drop the local DuckDB warehouse
	bash ops/clean_warehouse.sh
