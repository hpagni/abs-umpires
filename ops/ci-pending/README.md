# CI workflows, parked until the `workflow` token scope exists

`ci.yml` and `seal-guard.yml` are the two files SOP step W1.16 specifies. They belong at
`.github/workflows/`. They are parked here because the GitHub token on this machine carries
`gist, read:org, repo` and not `workflow`, and GitHub rejects any push that adds or updates a
path under `.github/workflows/` without that scope. The rule applies to every path under that
directory, not only to `.yml` files, so `.github/` was removed from the tree rather than left
as a `.gitkeep` that blocks the first push on its own.

Nothing else about these two files is provisional. Both parse as YAML, `ci.yml` declares
exactly the six jobs W1.16 names (lint, python, r, dbt, guard, secrets), and every Makefile
target and script they call exists in this repository. The validation is in
`logs/evidence/W1.16.log`.

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
```

The first command answers W1.3, which asks for a push carrying a workflow file to be proved end
to end. The second and third answer W1.16. `quality/steps.yml` still registers both steps
against `.github/workflows/...`; those registered verify commands start passing on the same
move, and nothing in them needs editing.

## Note on the dbt job

`ci.yml`'s dbt job needs `dbt/dbt_project.yml`, `dbt/packages.yml` and real models under
`dbt/models/`. Phase 01 wrote `dbt/profiles.yml.example` and the directory tree only, so that
job is red until SOP W1.11 and W2 land the project file and the models. This is a phase
ordering fact, not a defect in the workflow file.
