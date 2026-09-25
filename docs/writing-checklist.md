# Writing checklist

Every human-facing text in this repository follows the rules below. SOP step W7.2 sets them. Each rule names the check that enforces it and the label that check prints on a finding. No rule rests on a reader's memory.

The linter is `quality/prose_lint.py`. With no path, it reads `README.md`, `DECISIONS.md`, `PREREGISTRATION.md`, `docs/` and `abstract/`. It skips code, block quotes, tables and HTML comments. The number gate is `quality/check_numbers.py`.

Thresholds appear in code spans. They quote SOP W7.2 and SOP section 6.6 word for word, and they equal the constants in the linter. They are rule parameters, not results.

## The eleven rules

1. **One claim per sentence.** A sentence carries one claim. The SOP limit is `≤34 words, file median ≤22`. WR-03 separately fails a `sentence over 35 words`. Check: `quality/prose_lint.py`, label `rule 1`, with `WR-03` added past the WR-03 limit.
2. **No rhetorical questions.** A question mark may stand only on a line that begins `Q1.` to `Qn.` or `H1.` to `Hn.` in the pre-registration. The linter reads the pre-registration as `PREREGISTRATION.md` and `docs/prereg/`. Check: `quality/prose_lint.py`, label `rule 2, WR-02`.
3. **No hype or filler.** No entry of the ban list may appear, matched as a whole word or phrase and ignoring case. The list is `quality/banned.txt`. Its `[p8]` entries apply to `docs/p8/` only, and there no heading may contain `roi`. The entry `robust` counts only as a hype adjective, so `robust standard errors` stays legal. Check: `quality/prose_lint.py`, label `rule 3, WR-01`, and label `P8 ban list` under `docs/p8/`.
4. **No em dash.** Neither `U+2014` nor a hyphen with a space on each side may serve as a sentence dash. A hyphen between two digits, as in a score, is not a dash. Check: `quality/prose_lint.py`, label `rule 4, WR-09`.
5. **Every result number carries a bound.** A sentence that reports a result also carries `95%`, `90%`, `[`, `±` or `n = `. The rule covers the memo, the README, the portfolio page, the resume entry and the SSAC abstract. A labelled number, such as a section or version number, is not a result. Check: `quality/prose_lint.py`, label `rule 5`.
6. **Every number is traceable.** Each numeric literal in `abstract/` and `docs/memo/` appears in one of three files. `docs/numbers.json` holds model output. `docs/priorart-numbers.txt` holds numbers from published work. `docs/numbers-allow.txt` holds the rest, each with a reason. Check: `quality/check_numbers.py`, label `WR-07`.
7. **No first person in the memo.** `docs/memo/memo.html` uses none of `we`, `our`, `my`, `us` or `I`. Check: `quality/prose_lint.py`, label `rule 7, WR-10`.
8. **The attribution string is present.** Every artifact that shows a number derived from MLB data carries `Data: MLB Advanced Media and Baseball Savant.` exactly. Check: `quality/prose_lint.py --ship`, label `rule 8, WR-11`.
9. **Prior art is credited in the same breath as the delta.** Where a text states what this project adds, the same passage names `use-it-or-lose-it`. It quotes 99.75% agreement across 10,155 challenged pitches. It dates the buffer confound to 2026-08-17, as `lit/04`, `lit/06`, `lit/22` and `METHODS_REVIEW` item `B5` record. Check: `quality/prose_lint.py --ship`, label `rule 9, WR-12`.
10. **Nothing ships without a result.** No page carries an unfilled `{{slot}}` or a `coming soon` notice. Under `--ship`, every artifact the ship gate names must exist. Check: `quality/prose_lint.py`, label `rule 10`.
11. **The direction sentence.** `README.md` and the portfolio page state who directed the work, in the SOP's words: `research questions, validation design, acceptance criteria and result calls are [owner]'s; Claude Code implemented against them`. The published sentence carries the owner's first name in place of `[owner]`. The linter holds that exact string. While `quality/review-window.lock` exists, WR-19 suspends this rule on both files, and the linter prints a line that says so. Check: `quality/prose_lint.py --ship`, label `rule 11`.

## Two rules added in revision R2

- **WR-20, the buffer rule.** Any sentence containing "buffer" and "two inches" must also contain "outside". It applies to `abstract/`, `PREREGISTRATION.md`, `docs/prior-art.md`, `docs/memo/` and `docs/ch1.md`. The December 2024 umpire labor agreement cut the grading buffer from two inches outside the zone edge to three-quarters of an inch on either side of it. The old buffer sat outside the zone only, and that asymmetry is the mechanism under study. A sentence that drops "outside" describes a symmetric change, and a symmetric change does not imply the interior effect. Check: the W7.2 row of `quality/steps.yml` runs this rule over that scope and over this file.
- **WR-19, author blinding.** While `quality/review-window.lock` exists, no file reachable from the repository root may name the author. The reach is `README.md`, `LICENSE`, `CITATION.cff`, `docs/`, `app/`, `.github/` and any file they link to, one hop deep. Check: `tools/comms/check_blind.py`, which step W7.42 builds. Until it exists, the W7.2 row checks that this file and `quality/banned.txt` never name the author and link to no file that does.

## Other checks in the same linter

SOP section 6.6 adds four checks that run on every file.

- WR-04: `significantly` needs a p-value, an interval or an effect size in the same sentence.
- WR-05: a novelty claim built on `first`, `the only`, `nobody` or `no public work` needs a citation on its line or the next.
- WR-06, a warning: a bare percentage or count needs a denominator. The linter checks percentages.
- WR-08, a warning: the share of passive sentences in a file must not rise `above 20%`.

## Running the checks

```sh
uv run --locked python quality/prose_lint.py
uv run --locked python quality/prose_lint.py --ship
uv run --locked python quality/check_numbers.py
make lint-prose
```

A path argument narrows either tool to the files named. The `--ship` flag adds the three rules that ask whether a finished artifact carries a required string: the attribution, the prior-art credit and the direction sentence. The ship gate passes that flag.
