# CI workflows, parked until the `workflow` token scope exists

`ci.yml` and `seal-guard.yml` are the two files SOP steps W1.16 and W9.10 specify. They
belong at `.github/workflows/`. They wait here because the GitHub token on this machine
carries `gist, read:org, repo` and not `workflow`, and GitHub rejects any push that adds or
updates a path under `.github/workflows/` without that scope. The rule covers every path
under that directory, not only `.yml` files. So phase 01 took `.github/` out of the tree
rather than leave a `.gitkeep` there that would block the first push on its own.

Nothing else about these two files is provisional. `uv run --locked python ops/ci_check.py`
checks them on this machine (W9.10's registered verify) and reads them from
`.github/workflows/` once they are there, so it keeps working after the move:

- both parse, trigger on push and pull request, and never on a schedule;
- `ci.yml` has exactly the six jobs of the W1.16 table, lint, python, r, dbt, guard and
  secrets, on `ubuntu-latest`, none waiting on another, each capped at 8 minutes;
- every action is pinned: `actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.2.0`,
  `actions/cache@v6.1.0`, `actions/upload-artifact@v7.0.1`, `r-lib/actions/setup-r@v2`
  (`actions/setup-python@v7.0.0` is allowed and unused);
- each job runs the table's commands, and the r job restores renv and runs testthat with no
  Stan compile;
- the seal-guard provenance step passes on a clean clone of HEAD and fails on each of six
  planted violations.

## Zero network calls to MLB hosts

Every job's first step after checkout is `bash ops/ci_no_mlb.sh arm` and its last is
`bash ops/ci_no_mlb.sh audit`, under `if: always()`:

1. arm writes every MLB-family host the repository names into `/etc/hosts` as `0.0.0.0`,
   so a connection to one is refused on the runner and no packet leaves;
2. arm starts an observer on the runner's resolver, `resolvectl monitor` or a port 53
   capture, and proves it live with a canary lookup; if neither can be proved the job fails;
3. audit fails the job if any name in the MLB family was looked up, or if the sinkhole was
   removed, and the observer log is uploaded as the job's `no-mlb-dns-*` artifact.

`ops/ci_check.py` fails if a tracked file names an MLB-family host missing from the sinkhole
list. `bash ops/ci_no_mlb.sh selftest` proves the matcher on any machine.

## Owner step, once

Run in your own terminal. The first line is interactive: it prints a one-time device code and
opens a browser for a confirmation only the account owner can give, which is why no agent runs
it.

```sh
gh auth refresh -h github.com -s workflow,repo,read:org,gist
gh api user -i 2>/dev/null | grep -i '^x-oauth-scopes'   # must now list workflow

cd ~/sports-project
mkdir -p .github/workflows
git mv ops/ci-pending/ci.yml ops/ci-pending/seal-guard.yml .github/workflows/
git add .github/workflows/ci.yml .github/workflows/seal-guard.yml ops/ci-pending/README.md
git commit -m "W1.16 W1.3: move the CI workflows into .github/workflows"
git push -u origin HEAD
```

`gh auth refresh` adds a scope to the ones the token already holds, so the short form
`-s workflow` grants the same result; the full list above is the form SOP W1.3 writes.

## What proves it afterwards

```sh
gh api repos/hpagni/abs-umpires/contents/.github/workflows/ci.yml --jq '.name,.size'
gh workflow list --repo hpagni/abs-umpires        # expect ci and seal-guard
gh run list --repo hpagni/abs-umpires --limit 5   # expect runs, then green
gh run view <id> --repo hpagni/abs-umpires        # the measured wall clock, per job
```

The first command answers W1.3. The second and third answer W1.16. The fourth is the only
place SOP clause 3, green in under 8 minutes, can be measured: until then W9.10 registers
that clause as pending, never as passed. `quality/steps.yml` still registers W1.16 against
`.github/workflows/...`; that verify starts passing on the same move.

## Known red on first enablement

`uv run --locked python ops/ci_rehearse.py` runs each job's `run:` blocks from `ci.yml` on
its own clean clone of HEAD, on this Mac, and prints each job's exit and seconds. It is a
proxy: jobs run one after another, `uses:` steps are emulated, and the MLB sinkhole and the
gitleaks download are skipped because they need a Linux runner. It never measures clause 3.
The latest run is in `logs/evidence/W9.10-rehearsal.log`.

Four jobs are green there: lint, python, guard and secrets. The python and guard jobs needed
repairs in `ci.yml`, each explained in a comment above its job. `PYTHONPATH` carries
`tests/guard`, without which the xdist controller dies on the `VacuousGuard` warning. The
python job restores R with its renv library and installs the git hooks, which `tests/unit`
needs. The guard job sets `PYTEST_ADDOPTS=-n 4`, because the red team took 485 seconds
serial and about 200 with it. The dbt job's fixture step also bound its two paths in the
wrong order until it used named parameters.

Two jobs stay red for reasons outside these files, and will fail the same way on a runner
until their owners fix them:

- **dbt.** `dbt build --target ci` builds 85 nodes, then `int_challenge_resolved` errors
  because the ci branch of `stg_abs_challenges` (W1.11, W2.17) keeps `pitch_uid` and has no
  `pitch_slot`, which the intermediate model joins on. `--select tag:smoke`, W1.11's own gate,
  never reaches that model, which is why W1.11 passes.
- **r.** `tests/testthat/test-ch1-framing.R` (W3.19) and `test-ch1-sensitivity.R` (W3.22)
  assert that Chapter 1 outputs under `out/ch1/` exist. Those files are written by the model
  runs on the Mac and are not tracked, so a fresh checkout fails at the first
  `file.exists()`. Each test needs a skip when its output is absent.

CI runs on Linux and never exercises the arm64 macOS build (R-31). A green run is not a
reproduction; `make prove` on the Mac is the authoritative gate.
