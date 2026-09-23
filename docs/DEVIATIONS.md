# Deviations from the SOP

Every entry here is a place where the work departs from SOP-final.md, what was done instead,
and what closes it. An entry is written before the pre-registration tag, not after, so a
reader of the tagged repository sees the departure in the record rather than inferring it
from a missing file.

Status values: OPEN (not closed yet), CLOSED (with the date and what closed it).

---

## DEV-01 — W1.16: the CI workflow files are parked at `ops/ci-pending/`, not `.github/workflows/`

Raised 2026-09-23 (Europe/Madrid). Status: OPEN. Owner action outstanding.

SOP W1.16 puts `ci.yml` and `seal-guard.yml` at `.github/workflows/`. Both files are written
and validated, but they live at `ops/ci-pending/` and `.github/` is absent from the tree.

Reason. The GitHub token on the build machine carries `gist, read:org, repo`. GitHub rejects
any push that adds or updates a path under `.github/workflows/` without the `workflow` scope,
and it applies that rule to every path under the directory, not only to `.yml` files, so even
a `.gitkeep` there blocks the first push of an otherwise ordinary commit. Granting the scope
means `gh auth refresh`, which is interactive: a one-time device code and a browser
confirmation only the account owner can give. This fleet runs unattended and is forbidden
from running interactive commands, so the files were parked where they break no push.

What is true of the parked files. Both parse as YAML. `ci.yml` declares exactly the six jobs
W1.16 names: lint, python, r, dbt, guard, secrets. Every Makefile target and every script the
jobs call exists in this repository. Neither file reads a 2026 datum or contacts an MLB or
Savant host. Evidence: `logs/evidence/W1.16.log`.

What closes it. The owner runs the one sequence in `ops/ci-pending/README.md`: refresh the
scope, `mkdir -p .github/workflows`, `git mv` both files there, commit and push. The two files
move unchanged. `quality/steps.yml` already registers W1.16 against
`.github/workflows/ci.yml` and `.github/workflows/seal-guard.yml`, so its verify command
starts passing on the move with no edit.

Not done, and why. Writing `.github/workflows/` locally anyway was rejected: it would have
blocked every later push in phase 01 behind the same scope error, including pushes that carry
nothing to do with CI. Editing the registered verify in `quality/steps.yml` to point at the
parked paths was rejected too: the registration describes the step's finished state, and
changing it would hide the deviation instead of recording it.

## DEV-02 — W1.3: the `gh auth refresh` and the proof push are deferred to the owner

Raised 2026-09-23 (Europe/Madrid). Status: OPEN. Owner action outstanding.

SOP W1.3 (SOP-final.md:828) asks for `gh auth refresh -h github.com -s
workflow,repo,read:org,gist`, then an assertion that the token's scopes contain `workflow`,
then an end-to-end proof: a push that adds `.github/workflows/ci.yml`.

Reason. The refresh is interactive, for the reason in DEV-01. Nothing else in the step can be
done without it: the scope assertion fails until the refresh happens, and the proof push
carries the file the missing scope forbids. The read-only half was run and recorded:
`X-Oauth-Scopes: gist, read:org, repo`, and `hpagni/abs-umpires` is empty with no branch.

What closes it. The same owner sequence as DEV-01. Afterwards the registered verify for W1.3
exits 0 unedited, and `gh api repos/hpagni/abs-umpires/contents/.github/workflows/ci.yml
--jq '.name,.size'` returns the file, which is the SOP's end-to-end proof.

Evidence: `logs/evidence/W1.3.log`.

## DEV-03 — W1.16 and W1.3 receipts carry `PENDING-OWNER`, a status the receipt writer cannot emit

Raised 2026-09-23 (Europe/Madrid). Status: OPEN.

`quality/write_receipt.py` derives `status` from an exit code and emits only `PASS` or `FAIL`.
Neither fits DEV-01 or DEV-02: the work is complete and validated, and what is outstanding is a
human credential action. `FAIL` would read as a defect in the builder's product and would put
two steps on the remediation list that need no further building.

The receipts at `quality/receipts/W1.16.json` and `quality/receipts/W1.3.json` were therefore
written by hand with `"status": "PENDING-OWNER"`, the exact owner command, and the commands
that will prove each step once it is run. Both carry a `written_by` field saying so.

Consequence to expect. A later `scripts/prove.sh` sweep rewrites both receipts as `FAIL`,
because the writer has no such status. The gate logs are the durable record until
`quality/write_receipt.py` and `scripts/prove.sh` learn a third status. That change belongs to
the SOP W9.1 owner, not here.

The same applies one level up: `logs/evidence/W1.16.log` and `logs/evidence/W1.3.log` end with
`GATE RESULT: PENDING-OWNER` rather than the usual `PASS` or `FAIL`. Any reader or script that
greps for the two-value form should treat `PENDING-OWNER` as not-yet-passed and read the owner
action in the same log.
