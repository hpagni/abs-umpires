"""MT-03 and MT-04, Chapter 1: injected-effect recovery and null injection, over the full run.

The runs are W3.12(a)'s: 100 injected and 50 null replicates of the frozen W3.11 surface, each
with a 95% and a 90% interval from 1,000 draws of N(beta, Vc), mgcv's smoothing-parameter-
corrected covariance (out/dev/ch1_synth/recovery/). The interval method changed from Vp to Vc
before the tag, with the same seeds and fits (docs/prereg/ch1.md 8.7); the Vp run's record is
out/dev/ch1_synth/recovery_vp_run4/.
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

Three clauses are NOT MET and disclosed under the owner's answer DECISIONS.md D-R0-04 (DEV-67):
top-edge 95% coverage 91 of 100 (bound 93), top-edge CH1-A7 null equivalence 44 of 50 (bound
47, i.e. 93%), half-width MT-04 null 90% coverage of zero 42 of 50 (bound 43). The bounds and
the method are unchanged. For those three the test pins the measured value exactly, so a change
in either direction fails; checks that the pre-registration still states the bound and that
D-R0-04 and the not-met row of docs/prereg/ch1.md 8.7 exist; and prints NOT MET on every run.
Every other clause is asserted against its bound.
"""

import statistics

import pytest
from mt_ch1_common import (
    INJECTED,
    N_SEEDS,
    POWER,
    PREREG_MD,
    PREREG_ROOT,
    REC,
    ROOT,
    SHIFTS,
    TAUS,
    need,
    read_json,
    reps,
)

pytestmark = pytest.mark.fast
need(REC / "truth.json", REC / "inject", REC / "null")
INJ, NUL = reps(REC / "inject", 100), reps(REC / "null", 50)
TRUTH = read_json(REC / "truth.json")


# (clause, shift) -> (disclosed measured value, bound, bound sentence in the pre-registration,
# the file it is in, the not-met row of docs/prereg/ch1.md 8.7). D-R0-04, 2026-09-29.
DISCLOSED = {
    ("coverage95", "top_in"): (
        91,
        93,
        "- each shift's 95% interval covers the truth in at least 93 of 100;",
        PREREG_MD,
        "| CH1-A7: 95% interval covers the truth, injected | top | 91 of 100 "
        "| at least 93 of 100 | **not met** |",
    ),
    ("ch1_a7_equivalence", "top_in"): (
        44,
        47,
        "- CH1-A7's equivalence form: in at least 93% of the null replicates, each shift's 90% "
        "interval lies inside ±0.10 in.",
        PREREG_MD,
        "| CH1-A7: null 90% interval inside ±0.10 in | top | 44 of 50, 88% "
        "| at least 93%, 47 of 50 | **not met** |",
    ),
    ("mt04_null90_covers_zero", "half_width_in"): (
        42,
        43,
        "> MT-04 null injection: the decision rule fires in ≤5 of 50 and the 90% interval covers "
        "zero in ≥43 of 50.",
        PREREG_ROOT,
        "| MT-04: null 90% interval covers zero | half-width | 42 of 50 "
        "| at least 43 of 50 | **not met** |",
    ),
}


def section_8_7():
    t = PREREG_MD.read_text(encoding="utf-8")
    return t[t.index("### 8.7 ") : t.index("### 8.8 ")]


def disclosed(clause, q, k, capsys):
    """A clause the owner disclosed as not met under D-R0-04: pinned, not passed."""
    value, bound, sentence, doc, row = DISCLOSED[(clause, q)]
    with capsys.disabled():
        print(f"\nNOT MET, DISCLOSED UNDER D-R0-04: {clause} {q}: measured {k}, bound {bound}")
    assert k == value, (
        f"{clause} {q}: measured {k}, but D-R0-04 disclosed {value}; the disclosure no longer "
        "describes the run"
    )
    assert k < bound, f"{clause} {q}: {k} now meets {bound}; the disclosure is stale"
    assert sentence in doc.read_text(encoding="utf-8"), (
        f"{clause} {q}: the bound {bound} is no longer stated in {doc.name}"
    )
    decisions = (ROOT / "DECISIONS.md").read_text(encoding="utf-8")
    assert "### D-R0-04 OWNER ANSWER, W3.12 recovery" in decisions, "D-R0-04 is missing"
    assert '**The answer: (a), "Disclose all three and tag".**' in decisions
    assert row in section_8_7(), f"{clause} {q}: docs/prereg/ch1.md 8.7 lacks the not-met row"


def err(q):
    return [r["estimate"][q] - r["truth"][q] for r in INJ]


def covers(rs, q, lo, hi, at=None):
    return sum(r[lo][q] <= (r["truth"][q] if at is None else at) <= r[hi][q] for r in rs)


def excludes_zero(rs, q, lo="lo95", hi="hi95"):
    return sum(r[lo][q] > 0 or r[hi][q] < 0 for r in rs)


def test_the_run_is_complete_and_is_the_sop_design():
    assert TRUTH["injected"] == INJECTED
    assert all(r.get("interval_cov") == "Vc" for r in INJ + NUL), (
        "a replicate's interval is not from Vc"
    )
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
def test_prereg_95_coverage_at_least_93_of_100(q, capsys):
    k = covers(INJ, q, "lo95", "hi95")
    if ("coverage95", q) in DISCLOSED:
        return disclosed("coverage95", q, k, capsys)
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
def test_prereg_ch1_a7_null_equivalence_at_least_93pct(q, capsys):
    k = sum(r["lo90"][q] >= -0.10 and r["hi90"][q] <= 0.10 for r in NUL)
    if ("ch1_a7_equivalence", q) in DISCLOSED:
        return disclosed("ch1_a7_equivalence", q, k, capsys)
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
def test_mt04_null_90_interval_covers_zero_at_least_43_of_50(q, capsys):
    k = covers(NUL, q, "lo90", "hi90", at=0.0)
    if ("mt04_null90_covers_zero", q) in DISCLOSED:
        return disclosed("mt04_null90_covers_zero", q, k, capsys)
    assert k >= 43, f"{q}: null 90% interval covers zero in {k} of 50"
