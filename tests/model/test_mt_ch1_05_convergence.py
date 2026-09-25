"""MT-05, Chapter 1: convergence of the fits whose output the repo reports.

SOP 6.5: "MT-05 convergence on every reported fit: 4 chains x 1,000/1,000 minimum,
rank-normalised split R-hat <= 1.01, ess_bulk >= 400, ess_tail >= 400, divergent transitions
== 0, max-treedepth hits == 0, E-BFMI >= 0.2 per chain ... A fit with any divergence is
reparameterised or reported as failed, never reported with a footnote."

Before the tag, Chapter 1's reported Stan fits are the 30 behind the D-60 power curve, 15 per
estimator: out/tables/ch1_power_curve.csv reports their firing rates, and `sop`'s set CH1-A6.
Each seed's summary.json holds the diagnostics diagnostics() in R/ch1/21_synthetic.R computed
from nuts_params() and posterior::summarise_draws() over the b_, sd_, cor_ and sigma
parameters; tau_draws.csv.gz holds 4,000 draws, 4 chains of 1,000 after 1,000 warmup
(iter = 2000). The 200 SBC fits (MT-02 governs them) and the 2022-2024 calibration fit, which
sets simulation inputs only (docs/prereg/ch1.md 8.6), are not reported fits and are not gated.
"""

import pytest
from mt_ch1_common import CURVE_CSV, N_SEEDS, POWER, TAUS, need, read_json, seed_dir, tau_draws

pytestmark = pytest.mark.fast
need(POWER / "sop", POWER / "ue_us", CURVE_CSV)
LIMITS = {
    "rhat_max": ("<=", 1.01),
    "ess_bulk_min": (">=", 400),
    "ess_tail_min": (">=", 400),
    "divergent": ("==", 0),
    "treedepth_hits": ("==", 0),
    "ebfmi_min": (">=", 0.2),
}


def breaches(d):
    ok = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "==": lambda a, b: a == b}
    return [f"{k} {d[k]:.5g}" for k, (op, lim) in LIMITS.items() if not ok[op](d[k], lim)]


def fits(est):
    return [
        (t, s, read_json(seed_dir(est, t, s) / "summary.json"))
        for t in TAUS
        for s in range(1, N_SEEDS + 1)
    ]


@pytest.mark.parametrize("est", ["sop", "ue_us"])
def test_every_power_fit_has_4000_draws_and_a_diagnostic_record(est):
    for t, s, x in fits(est):
        assert set(LIMITS) <= set(x["diagnostics"]), f"{est} tau {t} seed {s}"
        assert len(tau_draws(est, t, s)) == 4000, f"{est} tau {t} seed {s}"


@pytest.mark.parametrize("est", ["sop", "ue_us"])
def test_mt05_every_power_fit_converged(est):
    bad = [
        f"tau {t} seed {s}: " + ", ".join(b)
        for t, s, x in fits(est)
        if (b := breaches(x["diagnostics"]))
    ]
    assert not bad, (
        f"{est}: {len(bad)} of 15 fits fail MT-05 and feed ch1_power_curve.csv\n  "
        + "\n  ".join(bad)
    )
