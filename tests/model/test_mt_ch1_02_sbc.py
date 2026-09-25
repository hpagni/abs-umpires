"""MT-02 and CH1-A8, Chapter 1: SBC of B2, re-scored from the stored ranks.

SOP 6.5: "MT-02 SBC, L = 200, worst Benjamini-Hochberg-adjusted uniformity p > 0.01, 0
parameters outside the 95% simultaneous ECDF band; one L = 1,000 full-scale run before
2026-12-04." SOP W3.12(b) and CH1-A8 (docs/prereg/ch1.md section 8.7): a chi-square uniformity
test at alpha = 0.05 passes for tau and for the regime mean.

The ranks are W3.12's, 200 replicates of `sop` (the estimator that sets CH1-A6), each the rank
of the true value among 199 thinned draws, so 0..199, binned into 10 bins of 20. This file
scores them with scipy, independently of score_sbc() in R/ch1/21_synthetic.R. The ECDF band is
Saeilynoja et al. (2022): 19 evaluation points, the pointwise binomial level gamma simulated
from uniform ranks so that the band holds simultaneously at 95%.
"""

import datetime

import numpy as np
import pytest
from mt_ch1_common import SBC, need, reps
from scipy import stats

pytestmark = pytest.mark.fast
need(SBC / "sop")
L, DRAWS, BINS = 200, 199, 10
QUANTITIES = (
    "tau_abs",
    "tau_buf",
    "sd_intercept",
    "sigma",
    "cor_buf_abs",
    "b_side_abs",
    "b_top_abs",
    "b_bot_abs",
    "regime_mean_abs",
    "regime_mean_buf",
)
REPS = reps(SBC / "sop", L)
RANKS = {q: np.array([r["ranks"][q] for r in REPS]) for q in QUANTITIES}


def chisq_p(r):
    obs = np.bincount(r // ((DRAWS + 1) // BINS), minlength=BINS)
    return float(stats.chisquare(obs).pvalue)


def ecdf_gamma(n, K=20, nsim=4000, seed=31399):
    rng, z = np.random.default_rng(seed), np.arange(1, K) / K
    mins = np.empty(nsim)
    for i in range(nsim):
        u = (rng.integers(0, DRAWS + 1, n) + 0.5) / (DRAWS + 1)
        cnt = np.array([(u <= zz).sum() for zz in z])
        p = np.minimum(stats.binom.cdf(cnt, n, z), 1 - stats.binom.cdf(cnt - 1, n, z))
        mins[i] = (2 * p).min()
    return float(np.quantile(mins, 0.05))


P = {q: chisq_p(RANKS[q]) for q in QUANTITIES}


def test_sbc_replicates_complete():
    assert len({r["seed"] for r in REPS}) == L
    assert all(r["n_draws"] == DRAWS and r["estimator"] == "sop" for r in REPS)
    for q in QUANTITIES:
        assert RANKS[q].min() >= 0 and RANKS[q].max() <= DRAWS, q


@pytest.mark.parametrize("q", ["tau_abs", "regime_mean_abs"])
def test_ch1_a8_chisquare_uniform_at_005(q):
    assert P[q] > 0.05, f"{q}: chi-square p {P[q]:.4f} over {L} replicates, {BINS} bins"


def test_mt02_worst_bh_adjusted_p_above_001():
    adj = stats.false_discovery_control([P[q] for q in QUANTITIES], method="bh")
    worst = int(np.argmin(adj))
    assert adj[worst] > 0.01, f"worst BH-adjusted p {adj[worst]:.4f} ({QUANTITIES[worst]})"


def test_mt02_no_quantity_outside_simultaneous_ecdf_band():
    K, n = 20, L
    z = np.arange(1, K) / K
    g = ecdf_gamma(n)
    lo, hi = stats.binom.ppf(g / 2, n, z), stats.binom.ppf(1 - g / 2, n, z)
    out = [
        q
        for q in QUANTITIES
        if not np.all(
            (c := np.array([(((RANKS[q] + 0.5) / (DRAWS + 1)) <= zz).sum() for zz in z])) >= lo
        )
        or not np.all(c <= hi)
    ]
    assert not out, f"outside the 95% simultaneous ECDF band (gamma {g:.5f}): {out}"


# SOP MT-02 asks for one L = 1,000 full-scale SBC run before this day. It is a
# deadline read against the wall clock, not a data boundary: nothing here selects
# rows by date.
MT02_FULL_SCALE_DUE = datetime.date.fromisoformat("2026-12-04")


def test_mt02_full_scale_run_by_2026_12_04():
    if datetime.date.today() < MT02_FULL_SCALE_DUE:
        pytest.skip("MT-02's L = 1,000 full-scale SBC run is due by 2026-12-04, not yet")
    big = [
        d
        for d in SBC.parent.rglob("sbc*")
        if d.is_dir() and len(list(d.rglob("rep*.json"))) >= 1000
    ]
    assert big, "no SBC directory under out/dev/ch1_synth holds 1,000 replicates"
