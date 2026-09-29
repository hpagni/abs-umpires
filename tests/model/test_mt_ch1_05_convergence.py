"""MT-05, Chapter 1: convergence of the fits whose output the repo reports.

SOP 6.5: "MT-05 convergence on every reported fit: 4 chains x 1,000/1,000 minimum,
rank-normalised split R-hat <= 1.01, ess_bulk >= 400, ess_tail >= 400, divergent transitions
== 0, max-treedepth hits == 0, E-BFMI >= 0.2 per chain ... A fit with any divergence is
reparameterised or reported as failed, never reported with a footnote."

Before the tag, Chapter 1's reported Stan fits are the 30 behind the D-60 power curve, 15 per
estimator: out/tables/ch1_power_curve.csv reports their firing rates, and `sop`'s set CH1-A6.
Each seed's summary.json holds the diagnostics diagnostics() in R/ch1/21_synthetic.R computed
from nuts_params() and posterior::summarise_draws() over the b_, sd_, cor_ and sigma
parameters, and the sampler settings the fit ran with. The settings are pre-registered per
estimator in STAN_SETTINGS (docs/prereg/ch1.md 8.2): adapt_delta 0.99, 4 chains, 1,000 warmup
and 2,000 draws a chain for sop, 2,000 and 6,000 for ue_us. tau_draws.csv.gz holds every kept
draw. The 200 SBC fits (MT-02 governs them) and the 2022-2024 calibration fit, which
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


OPS = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "==": lambda a, b: a == b}


def breaches(d, only=None):
    """The MT-05 clauses d misses; with `only`, whether it misses that one clause."""
    if only is not None:
        op, lim = LIMITS[only]
        return not OPS[op](d[only], lim)
    return [f"{k} {d[k]:.5g}" for k, (op, lim) in LIMITS.items() if not OPS[op](d[k], lim)]


def fits(est):
    return [
        (t, s, read_json(seed_dir(est, t, s) / "summary.json"))
        for t in TAUS
        for s in range(1, N_SEEDS + 1)
    ]


SHORT_ONLY = ("rhat_max", "ess_bulk_min", "ess_tail_min")  # the clauses a longer run may fix


def base_and_attempts(x):
    """The first attempt's settings and every attempt, for a fit with or without escalation."""
    at = x.get("sampler_attempts") or [{**x["sampler"], **x["diagnostics"]}]
    keys = ("chains", "warmup", "sampling", "adapt_delta", "max_treedepth")
    return {k: at[0][k] for k in keys}, at


@pytest.mark.parametrize("est", ["sop", "ue_us"])
def test_every_power_fit_has_its_draws_and_a_diagnostic_record(est):
    """R/ch1/21_synthetic.R STAN_SETTINGS, and its MT-05 escalation: a fit short only on R-hat or
    ESS is re-run from the same seed with the draws a chain doubled, at most twice."""
    bases = []
    for t, s, x in fits(est):
        base, at = base_and_attempts(x)
        bases.append(tuple(sorted(base.items())))
        sm = x["sampler"]
        assert set(LIMITS) <= set(x["diagnostics"]), f"{est} tau {t} seed {s}"
        assert base["chains"] >= 4 and base["warmup"] >= 1000 and base["sampling"] >= 1000, (
            f"{est} tau {t} seed {s}: below MT-05's 4 chains x 1,000/1,000: {base}"
        )
        assert len(at) <= 3 and sm["sampling"] == base["sampling"] * 2 ** (len(at) - 1)
        for a in at[:-1]:
            short = [k for k in LIMITS if k not in SHORT_ONLY and breaches(a, k)]
            assert breaches(a) and not short, (
                f"{est} tau {t} seed {s}: escalated without cause: {a}"
            )
        n = sm["chains"] * sm["sampling"]
        assert len(tau_draws(est, t, s)) == n, f"{est} tau {t} seed {s}: expected {n} draws"
    assert len(set(bases)) == 1, f"{est}: the 15 fits started from different sampler settings"


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
