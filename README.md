# abs-umpires

Decompose the change in the MLB called strike zone between 2024 and 2026 into a 2025
umpire-grading component and a 2026 ABS component. Both sit on one scale: square inches of
the 50% called-strike contour, and signed edge shifts in inches.

The 2026 rollout of the ABS challenge system did not land on a stable baseline. The December
2024 umpire labor agreement had already cut the grading buffer from two inches outside the
zone edge to three-quarters of an inch on either side of it. Every published estimate of the
2026 zone change uses 2025 as its baseline, so the 2025 change is differenced out rather
than measured. This project adds 2022 to 2024 as a third regime under the earlier rule. One
transition then identifies the grading change and the other identifies ABS net of it, and a
genuinely untreated placebo pair sits inside 2022 to 2024. The evidence that no published work
does this is in [docs/prior-art.md](docs/prior-art.md), section 6.1.

## What is here

- **Chapter 1.** The three-regime decomposition, a plate-plane correction for the 2026
  Statcast coordinate change, umpire-level heterogeneity with shrinkage and reliability, the
  framing split, and a Triple-A arm that uses the within-week format alternation.
- **Chapter 2.** A partially pooled challenger-skill leaderboard with a random effect for
  the player challenged against, and split-half reliability reported beside variance
  components. Calibration curves for the probability a challenge succeeds, and a benchmark
  against Baseball Savant's published expectation.
- **Chapter 3.** A dynamic program that carries both teams' remaining challenges in the
  state, presented as a benchmark replication of the published single-sided solution plus
  one new number.
- A second phase on calibrated game forecasts, scored against de-vigged closing lines.
  Success there is calibration and honest closing-line value, not profit.

## Status

Pre-analysis. No result is published yet, and no 2026 datum has been read.

The order is fixed and enforced in code. The analysis set is sealed, the pre-registration is
frozen and tagged, and only then is data read. `make seal-check` runs the sealed-side checks
that need no data. `make unseal` refuses unless the pre-registration tag is an ancestor of
the current commit. The pre-registration tag is not yet cut.

Continuous integration runs on Linux. The authoritative gate is `make prove` on the
development machine, which is arm64 macOS. A green badge is not a reproduction.

## Reproducing

    make bootstrap      # disk floor, PATH, CmdStan, then the Python and R environments
    make verify-env     # the environment gate, expects 6/6 OK
    make smoke          # 12 checks, no request to any MLB or Savant host
    make test           # the offline suites: unit, fixtures, guard
    make prove          # every registered step's verify command, one line each

Python is managed with uv against `uv.lock`, on Python 3.12. R is managed with renv against
`renv.lock`. Bayesian fits use CmdStan 2.40.0 through brms. The warehouse is DuckDB, built
from Parquet, with the transformation layer in dbt. `make help` prints every target with a
one-line description.

## Data policy

No data file enters this repository, in any form. `data/` is ignored and a pre-commit hook
refuses a commit that reaches into it. Terms and attribution for each source are in
[DATA_LICENSE.md](DATA_LICENSE.md).

Every pull is throttled from one place, `config/throttle.yml`, which is the only file in the
repository carrying a delay, a budget or a user-agent string. The current policy is a 10
second minimum interval and 800 requests a day to Baseball Savant. It is 4 seconds and 3,000
a day to the MLB Stats API, and 10 seconds and 500 a day to every other host. Requests run through
a single client module, and a lint step fails the build on an HTTP call from anywhere else.

## How results are checked

Every piece of work has a step id and a registered verify command in `quality/steps.yml`.
`make prove` runs them and writes a receipt per step. A step is not done because someone
says so; it is done when its command exits zero. Numbers that reach human-facing text are
traced back to a source file by a checker. Prose is linted for the writing rules this
project holds itself to, including a rule that any novelty claim carries a citation on the
same line.

## Prior art

[docs/prior-art.md](docs/prior-art.md) is a dated ledger of the public work this project
builds on, with what each piece does and what it does not do. It also has a section listing
what this project may not claim because someone published it first. The nearest public
antecedent, `AyanArora29/use-it-or-lose-it`, sets the correctness bar for Chapters 2 and 3,
and its zone reconstruction is the benchmark this project's zone truth must match or beat.

## Documentation

- [docs/data-contract.md](docs/data-contract.md), every field this project relies on, with
  the check that verified it.
- [docs/prior-art.md](docs/prior-art.md), the prior-art ledger.
- [docs/runbook.md](docs/runbook.md), operating notes and deadlines.
- [docs/legal.md](docs/legal.md), terms of use and what follows from them.

Every decision this project made, with its reason and its date, is in `DECISIONS.md` at the
repository root. It is not linked from here while the review window is open, because it
names the author.

## Licence and authorship

Code is MIT, see [LICENSE](LICENSE). Data terms are separate, see
[DATA_LICENSE.md](DATA_LICENSE.md).

Author information is withheld from this README while the conference review window is open,
under decision D-69. It will be added on the day finalists are announced.
