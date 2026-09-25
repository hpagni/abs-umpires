"""The Chapter 1 MT pack's bounds are the SOP's and the annex's, word for word.

Each tests/model/test_mt_ch1_*.py file encodes a bound quoted from sop/SOP-final.md section 6.5
or W3.12(a), or from the acceptance docs/prereg/ch1.md section 8.7 pre-registers. This file
fails if either text changes under the pack, so a bound cannot drift from its source unnoticed.
Both files are in git, so it runs on a clean clone, where the artefact tests skip.
"""

import pytest
from mt_ch1_common import PREREG_MD, ROOT

pytestmark = pytest.mark.fast
SOP_BOUNDS = [
    "implied shadow-zone called-strike rate in [0.10, 0.90] for ≥95% of draws, "
    "implied between-umpire SD "
    "of the top-edge shift < 3.0 in for ≥99%",
    "MT-02 SBC, L = 200, worst Benjamini-Hochberg-adjusted uniformity p > 0.01, "
    "0 parameters outside the 95% "
    "simultaneous ECDF band; one L = 1,000 full-scale run before 2026-12-04",
    "MT-03 recovery: Ch1 injected −0.60 in top / +0.30 in bottom / −0.10 in width recovered within "  # noqa: RUF001
    "±0.10 in with coverage 46/50 in [0.80, 0.98] and mean |bias| ≤0.15 in (edge) and 0.10 in (SD)",
    "MT-04 null injection: the decision rule fires in ≤5 of 50 and the 90% interval covers zero in "
    "≥43 of 50",
    "rank-normalised split R-hat ≤1.01, `ess_bulk` ≥400, `ess_tail` ≥400, "
    "**divergent "
    "transitions == 0**, max-treedepth hits == 0, E-BFMI ≥0.2 per chain",
    "the D-60 curve exists, `out/tables/ch1_power_curve.csv` reports the firing rate of "
    "`P(τ ≥ 0.20 in) "
    "≥ 0.90` and the simulated split-half at τ ∈ {0.10, 0.20, 0.30} in over 5 seeds each",
    "Acceptance: each injected shift recovered within ±0.10 in and the 95% interval "
    "covers truth in ≥93 "
    "of 100 replicates; the zero-effect false-positive rate ≤7%",
    "rank histogram passing a chi-square uniformity test at α = 0.05 for `τ` and the regime mean",  # noqa: RUF001
]
PREREG_BOUNDS = [
    "over 100 injected replicates, each shift's mean error lies within ±0.10 in;",
    "each shift's 95% interval covers the truth in at least 93 of 100;",
    "over 50 null replicates, each shift's 95% interval excludes zero in at most 7%;",
    "CH1-A7's equivalence form: in at least 93% of the null replicates, "
    "each shift's 90% interval lies inside "
    "±0.10 in.",
]


@pytest.mark.parametrize("text", SOP_BOUNDS, ids=lambda t: t[:40])
def test_bound_is_quoted_from_the_sop(text):
    assert text in (ROOT / "sop" / "SOP-final.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("text", PREREG_BOUNDS, ids=lambda t: t[:40])
def test_bound_is_quoted_from_the_annex(text):
    assert text in PREREG_MD.read_text(encoding="utf-8")
