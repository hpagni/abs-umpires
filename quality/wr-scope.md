# The WR pack: what is enforced, where, and by which file

Owner: SOP step W9.13. The rule text is SOP section 6.6. This table is the scope the
checks implement, so the gate and its verifiers read the same scope. There is one prose
linter, `quality/prose_lint.py`, and one number gate, `quality/check_numbers.py` (SOP
section 2.8). `tools/comms/check_blind.py` is a front end to the linter for WR-15 and
WR-19. `quality/checks/wr20.py` is W7.4's WR-20 engine, which the linter imports.

`make lint-prose` runs the linter with no path. That run reads the default scope:
`README.md`, `DECISIONS.md`, `PREREGISTRATION.md`, `docs/` and `abstract/`. It then adds
the tree checks in the last column. A run given paths, or `ABS_PROSE_FILES`, applies the
per-file rules only and says so on its own line.

| rule | status | where it applies | implemented by |
|---|---|---|---|
| WR-01 | enforced | every file; the P8 list under `docs/p8/` | `prose_lint.py`, rule 3 |
| WR-02 | enforced | every file | `prose_lint.py`, rule 2 |
| WR-03 | enforced | every file, over 35 words | `prose_lint.py`, rule 1 |
| WR-04 | enforced | every file | `prose_lint.py` |
| WR-05 | enforced | every file; in `abstract/` the inline Clemens citation | `prose_lint.py` |
| WR-06 | warn | every file | `prose_lint.py` |
| WR-07 | enforced | `abstract/` and `docs/memo/` | `check_numbers.py` |
| WR-08 | warn | every file | `prose_lint.py` |
| WR-09 | enforced | every file | `prose_lint.py`, rule 4 |
| WR-10 | SKIP until W7 | `docs/memo/memo.html` | `prose_lint.py`, rule 7 |
| WR-11 | `--ship` | memo, README, portfolio, resume entry, abstract | `prose_lint.py`, rule 8 |
| WR-12 | `--ship` | memo, README, portfolio | `prose_lint.py`, rule 9 |
| WR-13 | SKIP until W7 | `docs/memo/memo.pdf`, exactly two pages | `prose_lint.py` tree check |
| WR-14 | enforced | every image in prose; `abstract/figure1*.alt.txt` | `prose_lint.py` |
| WR-15 | enforced | the submitted abstract files, listed below | `prose_lint.py`, `check_blind.py` |
| WR-16 | SKIP until W7 | `docs/resume/entry.html` | `prose_lint.py` tree check |
| WR-17 | SKIP until W8 | a write-up under `docs/p8/` | `prose_lint.py` tree check |
| WR-18 | enforced | the abstract's Conclusion; the memo once built | `prose_lint.py` |
| WR-19 | enforced while the lock exists | root reach and one link hop | `prose_lint.py`, `check_blind.py` |
| WR-20 | enforced | `wr20.py`'s scope, which includes `abstract/` | `wr20.py`, imported |

## Four rules wait for their targets

WR-10, WR-13, WR-16 and WR-17 check artifacts that W7 and W8 build. While the target is
absent the run prints `<RULE-ID>: SKIP (...)` with the path it looked for. The exit
status does not change. Once the target exists, the rule is enforced on the next run. No
skip is silent.

## The abstract

SSAC fixes four sections: Introduction, Methods, Results and Conclusion. Two rules adapt
to that format.

- WR-12, the prior-art credit, is the inline citation "(Clemens, FanGraphs, 28 April
  2026)". An SSAC abstract has no reference list, so the citation stays inline.
- WR-18, the named limitation, is a sentence inside the Conclusion. A Limitations heading
  would be a fifth section and would break the format. The check looks for "limit",
  "limitation", "cannot" or "caveat" in the Conclusion. While the Conclusion still holds
  the owner's `<<CALL>>` slot, the run prints a pending note and checks the filled text.

WR-11, the attribution string, is not required inside a 470-word SSAC abstract. The
`--ship` run still applies checklist rule 8 to `abstract/ssac2027_abstract.md`, as W7.2
wrote it. The two readings meet at review R1: the string costs 7 words.

## WR-15: which files are submitted text

WR-15 is the SOP's grep, `hudson|pagni|ucla|github\.com|hpagni|abs-umpires`, case
blind, on these files only:

- `abstract/ssac2027_abstract*.md`, including the filled text
- `abstract/variants/*.md`
- `abstract/table1*.md` and `abstract/figure1*.alt.txt`
- `submissions/ssac2027/submitted-abstract*.txt`

`abstract/FORM-FIELDS.md` is the owner's survey of the form. It names the submitting
account by design and is never pasted, so WR-15 does not read it. D-69 keeps it
unlinked from every file WR-19 reads.

## WR-19: the words it matches

The SOP lists `hudson`, `pagni`, `hudpag`, `hudsonpagni.com` and a UCLA affiliation. The
check matches `hudson`, `pagni` and `UCLA` as whole words, `hudpag` as a word start, and
the two literal strings. The repository handle `hpagni` is therefore not a WR-19 hit.
The SOP lists that handle under WR-15 only, and the public repository URL carries it.
The owner decides at review R2 whether that stays so.

## Where the abstract files sit

The abstract rules key on a file's role, not on the repository root. A path containing
`abstract/` or `submissions/ssac2027/` gets the same rules wherever that folder sits.
The dry run (`ops/abstract_dryrun.sh`) writes its SYNTHETIC copies under
`out/dev/abstract_dryrun/<variant>/abstract/`, and they are linted exactly as the real
files are. For the same reason WR-20 reads the pasted text,
`submissions/ssac2027/submitted-abstract*.txt`, as well as `wr20.py`'s own scope.

A folder walk reads `.md` and `.html`, plus the two plain-text files of the submission:
`figure1*.alt.txt` and `submitted-abstract*.txt`. The number lists under `docs/` are
data and are not linted as prose.

## One linter, one number gate

`ops/lint_prose.sh` was phase 01's stand-in, with its own ban list. W9.13 made it a thin
front end that runs `quality/prose_lint.py`, so the W4.1, W7.2 and W9.13 verify commands
and the CI job all reach the one implementation (SOP section 2.8).
`quality/check_numbers.py --ledger FILE` reads that ledger in place of
`docs/numbers.json`. The dry run passes its SYNTHETIC ledger; nothing else changes.
