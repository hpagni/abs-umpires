"""MT-09, Chapter 1 umpire-heterogeneity power, from the raw per-seed draws.

SOP 6.5: "MT-09 ... the D-60 curve exists, out/tables/ch1_power_curve.csv reports the firing
rate of P(tau >= 0.20 in) >= 0.90 and the simulated split-half at tau in {0.10, 0.20, 0.30} in
over 5 seeds each, and the CH1-A6 thresholds in PREREGISTRATION.md are the ones that file
implies." The firing rate is re-derived from each seed's 4,000 stored tau draws, not read from
the csv. CH1-A6 is checked in docs/prereg/ch1.md (the table) and in PREREGISTRATION.md, whose
CH1-A6 lines must cite that table or state the rule at the threshold thresholds.json carries.
"""

import csv

import pytest
from mt_ch1_common import (
    CURVE_CSV,
    ESTIMATORS,
    N_SEEDS,
    POWER,
    PREREG_MD,
    PREREG_ROOT,
    TAUS,
    need,
    read_json,
    seed_dir,
    tau_draws,
)

pytestmark = pytest.mark.fast
need(CURVE_CSV, POWER / "thresholds.json", PREREG_MD, PREREG_ROOT)
ROWS = {
    (r["estimator"], r["tau_true_in"]): r for r in csv.DictReader(CURVE_CSV.open(encoding="utf-8"))
}
TH = read_json(POWER / "thresholds.json")


def share_ge(draws, c):
    return sum(x >= c for x in draws) / len(draws)


def test_curve_has_every_cell_at_five_seeds():
    assert set(ROWS) == {(e, t) for e in ESTIMATORS for t in TAUS}
    for key, r in ROWS.items():
        assert int(r["n_seeds"]) == N_SEEDS and r["rule"] == "P(tau >= 0.20 in) >= 0.90", key
        assert len(r["split_half_response_by_seed"].split(";")) == N_SEEDS, key
        assert r["split_half_response_mean"] not in ("", "NA"), key


@pytest.mark.parametrize("est", ESTIMATORS)
@pytest.mark.parametrize("tau", TAUS)
def test_firing_rate_rederived_from_raw_draws(est, tau):
    p = [share_ge(tau_draws(est, tau, s), 0.20) for s in range(1, N_SEEDS + 1)]
    fired = [int(v >= 0.90) for v in p]
    r = ROWS[(est, tau)]
    assert r["fired_by_seed"] == ";".join(map(str, fired)), (est, tau, p)
    assert (
        int(r["n_fired"]) == sum(fired)
        and abs(float(r["firing_rate"]) - sum(fired) / N_SEEDS) < 0.005
    )
    assert all(
        abs(float(a) - b) < 5e-5
        for a, b in zip(r["p_tau_ge_020_by_seed"].split(";"), p, strict=False)
    ), (
        est,
        tau,
    )
    sh = [
        read_json(seed_dir(est, tau, s) / "summary.json")["split_half"]["sb_response"]
        for s in range(1, N_SEEDS + 1)
    ]
    assert all(
        abs(float(a) - b) < 5e-4
        for a, b in zip(r["split_half_response_by_seed"].split(";"), sh, strict=False)
    )


def test_ch1_a6_is_set_by_one_estimator_the_curve_supports():
    est = TH["estimator"]
    assert [e for e in ESTIMATORS if ROWS[(e, "0.10")]["sets_ch1_a6"] == "yes"] == [est]
    assert TH["c_star_in"] == 0.2 and TH["prob"] == 0.9
    assert int(ROWS[(est, "0.10")]["n_fired"]) <= 1, (
        "the rule false-fires in more than 1 of 5 seeds at tau 0.10"
    )


def test_ch1_a6_in_the_annex_and_in_preregistration():
    rule = f"P(τ ≥ {TH['c_star_in']:.2f} in) ≥ {TH['prob']:.2f}"
    assert rule in PREREG_MD.read_text(encoding="utf-8"), (
        f"docs/prereg/ch1.md does not state {rule}"
    )
    a6 = [ln for ln in PREREG_ROOT.read_text(encoding="utf-8").splitlines() if "CH1-A6" in ln]
    assert a6, "PREREGISTRATION.md carries no CH1-A6 line"
    bad = [ln[:120] for ln in a6 if "docs/prereg/ch1.md" not in ln and rule not in ln]
    assert not bad, f"CH1-A6 lines that neither cite docs/prereg/ch1.md nor state {rule}: {bad}"
