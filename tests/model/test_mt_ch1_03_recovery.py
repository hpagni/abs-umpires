"""MT-03 and MT-04, Chapter 1: injected-effect recovery and null injection, over the full run.

The runs are W3.12(a)'s: 100 injected and 50 null replicates of the frozen W3.11 surface, each
with a 95% and a 90% interval from 1,000 draws of N(beta, Vp) (out/dev/ch1_synth/recovery/).
Every count below is re-derived from the per-replicate estimates and intervals, not from a
summary. Two sets of bounds apply and both are tested, each under its own name:

  pre-registered, docs/prereg/ch1.md 8.7 (SOP W3.12(a) and CH1-A7): each shift's mean error
    within +/-0.10 in; its 95% interval covers the truth in >= 93 of 100; over the null
    replicates its 95% interval excludes zero in <= 7%; CH1-A7, its 90% interval lies inside
    +/-0.10 in in >= 93% of null replicates.
  SOP 6.5 as worded: MT-03 "recovered within +/-0.10 in with coverage ... in [0.80, 0.98] and
    mean |bias| <= 0.15 in (edge) and 0.10 in (SD)"; MT-04 "the decision rule fires in <= 5 of
    50 and the 90% interval covers zero in >= 43 of 50". The rule that fires is the zero-effect
    rule the annex pre-registers, a 95% interval that excludes zero. The SD clause reads the
    between-umpire SD tau across the 15 `sop` power seeds, the estimator that sets CH1-A6.
"""

import statistics

import pytest
from mt_ch1_common import INJECTED, N_SEEDS, POWER, REC, SHIFTS, TAUS, need, read_json, reps

pytestmark = pytest.mark.fast
need(REC / "truth.json", REC / "inject", REC / "null")
INJ, NUL = reps(REC / "inject", 100), reps(REC / "null", 50)
TRUTH = read_json(REC / "truth.json")


def err(q):
    return [r["estimate"][q] - r["truth"][q] for r in INJ]


def covers(rs, q, lo, hi, at=None):
    return sum(r[lo][q] <= (r["truth"][q] if at is None else at) <= r[hi][q] for r in rs)


def excludes_zero(rs, q, lo="lo95", hi="hi95"):
    return sum(r[lo][q] > 0 or r[hi][q] < 0 for r in rs)


def test_the_run_is_complete_and_is_the_sop_design():
    assert TRUTH["injected"] == INJECTED
    assert len({r["seed"] for r in INJ + NUL}) == 150
    assert all(r["n_draws_complete"] == r["n_draws"] == 1000 for r in INJ + NUL)
    for q in SHIFTS:
        assert all(abs(r["truth"][q] - TRUTH["truth"][q]) < 1e-12 for r in INJ), q
        assert all(r["truth"][q] == 0 for r in NUL), q


@pytest.mark.parametrize("q", SHIFTS)
def test_injected_effect_is_detected(q):
    k = excludes_zero(INJ, q)
    assert k == 100, f"{q}: the 95% interval excludes zero in {k} of 100 injected replicates"


@pytest.mark.parametrize("q", SHIFTS)
def test_prereg_and_mt03_mean_error_within_010(q):
    b = statistics.fmean(err(q))
    assert abs(b) <= 0.10, f"{q}: mean error {b:+.4f} in"


@pytest.mark.parametrize("q", SHIFTS)
def test_prereg_95_coverage_at_least_93_of_100(q):
    k = covers(INJ, q, "lo95", "hi95")
    assert k >= 93, (
        f"{q}: 95% interval covers the truth {TRUTH['truth'][q]:+.4f} in in {k} of 100; "
        f"mean error {statistics.fmean(err(q)):+.4f} in, SD of estimates "
        f"{statistics.stdev(err(q)):.4f} in"
    )


@pytest.mark.parametrize("q", SHIFTS)
def test_prereg_null_false_positive_rate_at_most_7pct(q):
    k = excludes_zero(NUL, q)
    assert k / 50 <= 0.07, f"{q}: null 95% interval excludes zero in {k} of 50 ({k / 50:.0%})"


@pytest.mark.parametrize("q", SHIFTS)
def test_prereg_ch1_a7_null_equivalence_at_least_93pct(q):
    k = sum(r["lo90"][q] >= -0.10 and r["hi90"][q] <= 0.10 for r in NUL)
    assert k >= 47, (
        f"{q}: null 90% interval inside +/-0.10 in in {k} of 50 ({k / 50:.0%}), needs >= 93%"
    )


@pytest.mark.parametrize("q", SHIFTS)
def test_mt03_coverage_in_080_098(q):
    c = covers(INJ, q, "lo95", "hi95") / 100
    assert 0.80 <= c <= 0.98, f"{q}: 95% coverage {c:.2f}"


@pytest.mark.parametrize("q", SHIFTS)
def test_mt03_mean_abs_bias_edge_at_most_015(q):
    m = statistics.fmean(abs(e) for e in err(q))
    assert m <= 0.15, f"{q}: mean |error| {m:.4f} in"


def test_mt03_mean_abs_bias_sd_at_most_010():
    s = [
        read_json(POWER / "sop" / f"tau{t}_seed{i}" / "summary.json")
        for t in TAUS
        for i in range(1, N_SEEDS + 1)
    ]
    m = statistics.fmean(abs(x["tau_median"] - x["tau_true"]) for x in s)
    assert len(s) == 15 and m <= 0.10, (
        f"tau: mean |posterior median - truth| {m:.4f} in over {len(s)} seeds"
    )


@pytest.mark.parametrize("q", SHIFTS)
def test_mt04_rule_fires_at_most_5_of_50(q):
    k = excludes_zero(NUL, q)
    assert k <= 5, (
        f"{q}: the zero-effect rule (95% interval excludes zero) fires in {k} of 50 null replicates"
    )


@pytest.mark.parametrize("q", SHIFTS)
def test_mt04_null_90_interval_covers_zero_at_least_43_of_50(q):
    k = covers(NUL, q, "lo90", "hi90", at=0.0)
    assert k >= 43, f"{q}: null 90% interval covers zero in {k} of 50"
